from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from archaeology.storage.models import Commit, CommitSignificance, DiscussionChunk, Repo


def repo_status(session: Session, name: str) -> dict[str, Any] | None:
    row = session.scalars(select(Repo).where(Repo.name == name)).first()
    if row is None:
        return None

    total_commits = session.scalar(
        select(func.count()).select_from(Commit).where(Commit.repo_id == row.id)
    )
    label_rows = session.execute(
        select(CommitSignificance.label, func.count())
        .where(CommitSignificance.repo_id == row.id)
        .group_by(CommitSignificance.label)
    ).all()

    chunk_rows = session.execute(
        select(func.count(), func.count(DiscussionChunk.embedding))
        .select_from(DiscussionChunk)
        .where(DiscussionChunk.repo_id == row.id)
    ).one()
    models = session.scalars(
        select(DiscussionChunk.embedding_model).where(DiscussionChunk.repo_id == row.id).distinct()
    ).all()

    return {
        "name": row.name,
        "head_sha": row.head_sha,
        "indexed_through_sha": row.indexed_through_sha,
        "local_path_present": bool(row.local_path),
        "commits": int(total_commits or 0),
        "significance": {label: int(count) for label, count in label_rows},
        "chunks": int(chunk_rows[0] or 0),
        "embedded_chunks": int(chunk_rows[1] or 0),
        "embedding_models": sorted(m for m in models if m),
        "complete_at_head": bool(row.head_sha and row.head_sha == row.indexed_through_sha),
    }
