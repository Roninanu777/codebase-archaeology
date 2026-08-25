from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from archaeology.storage.models import Commit, FileChange

SOURCE_COMMIT = "commit_message"

MIN_BODY_CHARS = 20
_MERGE_PREFIXES = ("Merge ", "Revert ")
_HEADER_PATH_LIMIT = 5


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
    cleaned = (body or "").strip()
    if len(cleaned) < MIN_BODY_CHARS and not subject.startswith(("Fix ", "Fixes ")):
        return True
    return False


def commit_chunks(
    session: Session,
    repo_id: int,
    limit: int | None = None,
    exclude_source_ids: set[str] | None = None,
) -> Iterator[ChunkDraft]:
    exclude = exclude_source_ids or set()
    paths_by_sha: dict[str, list[str]] = {}
    path_rows = session.execute(
        select(FileChange.sha, FileChange.path).where(FileChange.repo_id == repo_id)
    ).all()
    for sha, path in path_rows:
        paths_by_sha.setdefault(sha, []).append(path)

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
        if sha in exclude:
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


def count_chunkable(session: Session, repo_id: int) -> int:
    total = session.scalar(
        select(func.count()).select_from(Commit).where(Commit.repo_id == repo_id)
    )
    return int(total or 0)
