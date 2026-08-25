from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from archaeology.storage.models import Commit, CommitPrLink, FileChange, PullRequest

SOURCE_COMMIT = "commit_message"
SOURCE_PR_BODY = "pr_body"
SOURCE_PR_DISCUSSION = "pr_discussion"

MIN_BODY_CHARS = 20
_MERGE_PREFIXES = ("Merge ", "Revert ")
_HEADER_PATH_LIMIT = 5
_MAX_DISCUSSION_CHARS = 16_000


@dataclass(slots=True)
class ChunkDraft:
    source_type: str
    source_id: str
    authored_at: str | None
    title: str
    body: str
    files_touched: list[str] = field(default_factory=list)
    linked_commits: list[str] = field(default_factory=list)


def render_chunk_text(draft: ChunkDraft) -> str:
    header_parts: list[str] = []
    if draft.authored_at:
        header_parts.append(f"[{draft.authored_at[:10]}]")
    if draft.files_touched:
        shown = draft.files_touched[:_HEADER_PATH_LIMIT]
        more = len(draft.files_touched) - len(shown)
        suffix = f" (+{more} more)" if more > 0 else ""
        header_parts.append(", ".join(shown) + suffix)
    header = " ".join(header_parts).strip()
    pieces = [header, draft.title, "---", draft.body]
    return "\n".join(p.strip() for p in pieces if p and p.strip())


def _is_noise_commit(subject: str, body: str | None) -> bool:
    if subject.startswith(_MERGE_PREFIXES):
        return True
    if re.search(r"#\d+\)", subject):
        return False
    cleaned = (body or "").strip()
    return len(cleaned) < MIN_BODY_CHARS


def _paths_by_sha(session: Session, repo_id: int) -> dict[str, list[str]]:
    path_rows = session.execute(
        select(FileChange.sha, FileChange.path).where(FileChange.repo_id == repo_id)
    ).all()
    paths: dict[str, list[str]] = {}
    for sha, path in path_rows:
        paths.setdefault(sha, []).append(path)
    return paths


def commit_chunks(
    session: Session,
    repo_id: int,
    limit: int | None = None,
    exclude_source_ids: set[tuple[str, str]] | None = None,
) -> Iterator[ChunkDraft]:
    exclude = exclude_source_ids or set()
    paths_by_sha = _paths_by_sha(session, repo_id)

    stmt = (
        select(Commit)
        .where(Commit.repo_id == repo_id)
        .order_by(Commit.committed_at.desc().nullslast())
    )
    if limit is not None:
        stmt = stmt.limit(limit * 2)

    rows = list(session.scalars(stmt))
    produced = 0
    for row in rows:
        sha = row.sha
        if (SOURCE_COMMIT, sha) in exclude:
            continue
        body = (row.body or "").strip()
        subject = (row.subject or "").strip()
        if _is_noise_commit(subject, body):
            continue
        yield ChunkDraft(
            source_type=SOURCE_COMMIT,
            source_id=sha,
            authored_at=row.committed_at.isoformat() if row.committed_at else None,
            title=subject,
            body=body or subject,
            files_touched=sorted(set(paths_by_sha.get(sha, []))),
            linked_commits=[sha],
        )
        produced += 1
        if limit is not None and produced >= limit:
            return


def pr_chunks(
    session: Session,
    repo_id: int,
    limit: int | None = None,
    exclude_source_ids: set[tuple[str, str]] | None = None,
) -> Iterator[ChunkDraft]:
    exclude = exclude_source_ids or set()
    paths_by_sha = _paths_by_sha(session, repo_id)

    merge_links: dict[int, str] = {}
    link_rows = session.execute(
        select(CommitPrLink.pr_number, CommitPrLink.sha).where(CommitPrLink.repo_id == repo_id)
    ).all()
    for pr_number, sha in link_rows:
        merge_links.setdefault(pr_number, sha)

    rows = list(
        session.scalars(
            select(PullRequest)
            .where(PullRequest.repo_id == repo_id)
            .order_by(PullRequest.merged_at.desc().nullslast())
        )
    )

    produced = 0
    for pr in rows:
        source_id = f"pr:{pr.number}"

        title = (pr.title or "").strip() or f"PR #{pr.number}"
        merged_iso = pr.merged_at.isoformat() if pr.merged_at else None
        merge_sha = merge_links.get(pr.number)
        linked = [merge_sha] if merge_sha else []
        touched = sorted(set(paths_by_sha.get(merge_sha or "", [])))

        body_text = (pr.body or "").strip()
        if body_text and (SOURCE_PR_BODY, source_id) not in exclude:
            yield ChunkDraft(
                source_type=SOURCE_PR_BODY,
                source_id=source_id,
                authored_at=merged_iso,
                title=f"PR #{pr.number}: {title}",
                body=body_text,
                files_touched=touched,
                linked_commits=linked,
            )
            produced += 1

        discussion = (pr.discussion or "").strip()
        if discussion and (SOURCE_PR_DISCUSSION, source_id) not in exclude:
            yield ChunkDraft(
                source_type=SOURCE_PR_DISCUSSION,
                source_id=source_id,
                authored_at=merged_iso,
                title=f"PR #{pr.number} discussion: {title}",
                body=discussion,
                files_touched=touched,
                linked_commits=linked,
            )
            produced += 1

        if limit is not None and produced >= limit:
            return


def count_chunkable(session: Session, repo_id: int) -> int:
    total = session.scalar(
        select(func.count()).select_from(Commit).where(Commit.repo_id == repo_id)
    )
    return int(total or 0)
