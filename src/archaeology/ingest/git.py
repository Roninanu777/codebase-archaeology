from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pygit2
import pygit2.enums
from sqlalchemy import delete as sa_delete
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from archaeology.classify.features import (
    FEATURE_EXTRACTOR_VERSION,
    ChangeFeatures,
    extract_features,
    make_diff,
)
from archaeology.classify.labels import RULE_VERSION_FLOOR_V1, label_from_features
from archaeology.storage.base import Base
from archaeology.storage.models import (
    Commit,
    CommitFeature,
    CommitParent,
    CommitSignificance,
    FileChange,
    Repo,
)


@dataclass(slots=True)
class IngestStats:
    commits: int = 0
    file_changes: int = 0
    skipped: bool = False
    duration_s: float = 0.0
    degraded: int = 0
    label_counts: dict[str, int] = field(default_factory=dict)


def open_repository(repo_path: str | Path) -> Any:
    path = Path(repo_path).expanduser().resolve()
    if not (path / ".git").exists() and not (path / "HEAD").exists():
        msg = f"not a git repository: {path}"
        raise FileNotFoundError(msg)
    return pygit2.Repository(str(path))


def _dt(epoch: int) -> datetime | None:
    return datetime.fromtimestamp(epoch, tz=UTC) if epoch else None


def ingest_repository(
    engine: Any,
    repo_path: str | Path,
    name: str | None = None,
    url: str | None = None,
    batch_size: int = 500,
    progress_every: int = 2000,
    progress: Any = print,
) -> IngestStats:
    repo = open_repository(repo_path)
    head = str(repo.head.target)
    resolved_path = Path(repo_path).expanduser().resolve()
    resolved_name = name or resolved_path.name

    stats = IngestStats()
    started = time.monotonic()

    with Session(engine) as session:
        db_repo = session.scalars(select(Repo).where(Repo.name == resolved_name)).first()
        if db_repo is not None and db_repo.head_sha == head == db_repo.indexed_through_sha:
            if resolved_path and db_repo.local_path != str(resolved_path):
                db_repo.local_path = str(resolved_path)
                session.commit()
            stats.skipped = True
            stats.duration_s = time.monotonic() - started
            return stats

        if db_repo is None:
            db_repo = Repo(name=resolved_name, url=url, local_path=str(resolved_path))
            session.add(db_repo)
            session.flush()
        else:
            if url:
                db_repo.url = url
            db_repo.local_path = str(resolved_path)
        db_repo.default_branch = repo.head.shorthand
        db_repo.head_sha = head
        repo_id = int(db_repo.id)

        walker = repo.walk(
            repo.head.target,
            int(pygit2.enums.SortMode.TOPOLOGICAL) | int(pygit2.enums.SortMode.REVERSE),
        )

        degraded_count = 0

        commit_rows: list[dict[str, Any]] = []
        parent_rows: list[dict[str, Any]] = []
        change_rows: list[dict[str, Any]] = []
        feature_rows: list[dict[str, Any]] = []
        significance_rows: list[dict[str, Any]] = []

        def flush() -> None:
            if commit_rows:
                shas_in_batch = {row["sha"] for row in commit_rows}
                existing = set(
                    session.scalars(
                        select(Commit.sha).where(
                            Commit.repo_id == repo_id, Commit.sha.in_(shas_in_batch)
                        )
                    )
                )
                fresh_shas = {row["sha"] for row in commit_rows if row["sha"] not in existing}
                if fresh_shas:
                    fresh_commits = [r for r in commit_rows if r["sha"] in fresh_shas]
                    fresh_parents = [r for r in parent_rows if r["child_sha"] in fresh_shas]
                    fresh_changes = [r for r in change_rows if r["sha"] in fresh_shas]
                    fresh_features = [r for r in feature_rows if r["sha"] in fresh_shas]
                    fresh_sig = [r for r in significance_rows if r["sha"] in fresh_shas]
                    session.execute(insert(Commit), fresh_commits)
                    if fresh_parents:
                        session.execute(insert(CommitParent), fresh_parents)
                    if fresh_changes:
                        session.execute(insert(FileChange), fresh_changes)
                    if fresh_features:
                        session.execute(insert(CommitFeature), fresh_features)
                    if fresh_sig:
                        session.execute(insert(CommitSignificance), fresh_sig)
                    stats.commits += len(fresh_commits)
                    stats.file_changes += len(fresh_changes)
                    for row in fresh_sig:
                        stats.label_counts[row["label"]] = (
                            stats.label_counts.get(row["label"], 0) + 1
                        )
                session.commit()
            commit_rows.clear()
            parent_rows.clear()
            change_rows.clear()
            feature_rows.clear()
            significance_rows.clear()

        for count, commit in enumerate(walker, start=1):
            sha = str(commit.id)
            commit_rows.append(
                {
                    "repo_id": repo_id,
                    "sha": sha,
                    "author_name": commit.author.name,
                    "author_email": commit.author.email,
                    "authored_at": _dt(commit.author.time),
                    "committer_name": commit.committer.name,
                    "committer_email": commit.committer.email,
                    "committed_at": _dt(commit.commit_time),
                    "subject": commit.message.split("\n", 1)[0],
                    "body": commit.message,
                }
            )
            for position, parent_id in enumerate(commit.parent_ids):
                parent_rows.append(
                    {
                        "repo_id": repo_id,
                        "child_sha": sha,
                        "parent_sha": str(parent_id),
                        "position": position,
                    }
                )

            degraded_this = False
            try:
                diff = make_diff(repo, commit)
                features = extract_features(diff)
            except Exception:
                features = ChangeFeatures(files_changed=0)
                degraded_count += 1
                degraded_this = True

            for seq, fd in enumerate(features.per_file):
                change_rows.append(
                    {
                        "repo_id": repo_id,
                        "sha": sha,
                        "seq": seq,
                        "status": fd.status,
                        "path": fd.path,
                        "old_path": fd.old_path,
                        "additions": fd.additions,
                        "deletions": fd.deletions,
                    }
                )
            _fr = _feature_row(repo_id, sha, features)
            if degraded_this:
                _fr["extractor_version"] = FEATURE_EXTRACTOR_VERSION + "+degraded"
            feature_rows.append(_fr)
            significance_rows.append(
                {
                    "repo_id": repo_id,
                    "sha": sha,
                    "label": label_from_features(features),
                    "rule_version": RULE_VERSION_FLOOR_V1,
                }
            )

            if count % batch_size == 0:
                flush()
            if progress_every and count % progress_every == 0:
                progress(f"  ingested {count} commits")

        flush()
        stats.degraded = degraded_count
        db_repo.indexed_through_sha = head
        session.commit()

    stats.duration_s = time.monotonic() - started
    return stats


def _feature_row(repo_id: int, sha: str, features: ChangeFeatures) -> dict[str, Any]:
    return {
        "repo_id": repo_id,
        "sha": sha,
        "files_changed": features.files_changed,
        "additions": features.additions,
        "deletions": features.deletions,
        "binary_files": features.binary_files,
        "renamed_files": features.renamed_files,
        "whitespace_only": features.whitespace_only,
        "comment_only": features.comment_only,
        "pure_rename": features.pure_rename,
        "extractor_version": FEATURE_EXTRACTOR_VERSION,
    }


def recompute_degraded_features(engine: Any, repo_name: str) -> tuple[int, int]:
    with Session(engine) as session:
        repo_row = session.scalars(select(Repo).where(Repo.name == repo_name)).first()
        if repo_row is None:
            return 0, 0
        repo_id = int(repo_row.id)
        local = repo_row.local_path
        if not local:
            return 0, 0
        degraded_shas = session.scalars(
            select(CommitFeature.sha).where(
                CommitFeature.repo_id == repo_id,
                CommitFeature.extractor_version.like("%+degraded"),
            )
        ).all()
        if not degraded_shas:
            return 0, 0
        session.execute(
            sa_delete(CommitFeature).where(
                CommitFeature.repo_id == repo_id,
                CommitFeature.sha.in_(degraded_shas),
            )
        )
        session.execute(
            sa_delete(CommitSignificance).where(
                CommitSignificance.repo_id == repo_id,
                CommitSignificance.sha.in_(degraded_shas),
            )
        )
        session.execute(
            sa_delete(FileChange).where(
                FileChange.repo_id == repo_id,
                FileChange.sha.in_(degraded_shas),
            )
        )
        session.commit()

    repo = open_repository(local)
    recomputed = 0
    still_degraded = 0
    with Session(engine) as session:
        for i in range(0, len(degraded_shas), 200):
            batch = degraded_shas[i : i + 200]
            for sha in batch:
                commit = repo[sha]
                try:
                    diff = make_diff(repo, commit)
                    features = extract_features(diff)
                except Exception:
                    features = ChangeFeatures(files_changed=0)
                    still_degraded += 1
                session.execute(insert(CommitFeature), [_feature_row(repo_id, sha, features)])
                session.execute(
                    insert(CommitSignificance),
                    [
                        {
                            "repo_id": repo_id,
                            "sha": sha,
                            "label": label_from_features(features),
                            "rule_version": RULE_VERSION_FLOOR_V1,
                        }
                    ],
                )
                for seq, fd in enumerate(features.per_file):
                    session.execute(
                        insert(FileChange),
                        [
                            {
                                "repo_id": repo_id,
                                "sha": sha,
                                "seq": seq,
                                "status": fd.status,
                                "path": fd.path,
                                "old_path": fd.old_path,
                                "additions": fd.additions,
                                "deletions": fd.deletions,
                            }
                        ],
                    )
                recomputed += 1
            session.commit()
    return recomputed, still_degraded


def create_all(engine: Any) -> None:
    Base.metadata.create_all(engine)
