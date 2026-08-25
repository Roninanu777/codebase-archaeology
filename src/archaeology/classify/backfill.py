from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pygit2
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from archaeology.classify.ast_layer import AST_EXTRACTOR_VERSION, commit_ast_feature
from archaeology.classify.features import ChangeFeatures, make_diff
from archaeology.classify.labels import RULE_VERSION_AST_JS_V1, label_from_features_v2
from archaeology.storage.models import Commit, CommitFeature, CommitSignificance, Repo


@dataclass(slots=True)
class BackfillStats:
    processed: int = 0
    relabeled: int = 0
    duration_s: float = 0.0
    label_counts: dict[str, int] = field(default_factory=dict)


def _features_from_row(row: CommitFeature) -> ChangeFeatures:
    return ChangeFeatures(
        files_changed=row.files_changed or 0,
        additions=row.additions or 0,
        deletions=row.deletions or 0,
        binary_files=row.binary_files or 0,
        renamed_files=row.renamed_files or 0,
        whitespace_only=bool(row.whitespace_only),
        comment_only=bool(row.comment_only),
        pure_rename=bool(row.pure_rename),
    )


def backfill_ast_features(
    engine: Any,
    repo_name: str,
    force: bool = False,
    limit: int | None = None,
    batch_size: int = 500,
    progress: Any = print,
) -> BackfillStats:
    stats = BackfillStats()
    started = time.monotonic()

    with Session(engine) as session:
        db_repo = session.scalars(select(Repo).where(Repo.name == repo_name)).first()
        if db_repo is None or not db_repo.local_path:
            raise ValueError(f"repo {repo_name!r} not ingested with a local_path")
        repo_id = int(db_repo.id)
        git_repo: Any = pygit2.Repository(db_repo.local_path)

        stmt = (
            select(CommitFeature, Commit.sha)
            .join(
                Commit,
                (Commit.repo_id == CommitFeature.repo_id) & (Commit.sha == CommitFeature.sha),
            )
            .where(CommitFeature.repo_id == repo_id)
        )
        if not force:
            stmt = stmt.where(CommitFeature.ast_extractor_version.is_(None))
        if limit is not None:
            stmt = stmt.limit(limit)

        pending: list[tuple[CommitFeature, str]] = [
            (row, sha) for row, sha in session.execute(stmt).all()
        ]

        feature_updates: list[dict[str, Any]] = []
        significance_updates: list[dict[str, Any]] = []

        def flush() -> None:
            if feature_updates:
                session.execute(
                    update(CommitFeature),
                    feature_updates,
                )
                session.execute(
                    update(CommitSignificance),
                    significance_updates,
                )
                session.commit()
            feature_updates.clear()
            significance_updates.clear()

        for count, (feature_row, sha) in enumerate(pending, start=1):
            commit_obj = git_repo[sha]
            diff = make_diff(git_repo, commit_obj)
            verdict = commit_ast_feature(git_repo, diff)
            features = _features_from_row(feature_row)
            new_label = label_from_features_v2(
                features, verdict.format_only if verdict.applicable else None
            )

            ast_flag = bool(verdict.applicable) and verdict.format_only
            feature_updates.append(
                {
                    "repo_id": repo_id,
                    "sha": sha,
                    "ast_format_only": ast_flag if verdict.applicable else None,
                    "ast_extractor_version": AST_EXTRACTOR_VERSION,
                }
            )
            old_label_row = session.get(CommitSignificance, (repo_id, sha))
            old_label = old_label_row.label if old_label_row else None
            if old_label != new_label:
                stats.relabeled += 1
            stats.label_counts[new_label] = stats.label_counts.get(new_label, 0) + 1
            significance_updates.append(
                {
                    "repo_id": repo_id,
                    "sha": sha,
                    "label": new_label,
                    "rule_version": RULE_VERSION_AST_JS_V1,
                }
            )
            stats.processed += 1

            if count % batch_size == 0:
                flush()
                progress(f"  classified {count}/{len(pending)} commits")

        flush()

    stats.duration_s = time.monotonic() - started
    return stats
