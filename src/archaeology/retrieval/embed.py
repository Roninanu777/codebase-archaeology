from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from archaeology.retrieval.chunking import (
    ChunkDraft,
    commit_chunks,
    pr_chunks,
    render_chunk_text,
)
from archaeology.retrieval.liveness import head_paths, liveness_score
from archaeology.storage.models import DiscussionChunk, Repo

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = ""


@dataclass(slots=True)
class EmbedStats:
    chunks: int = 0
    skipped_existing: int = 0
    duration_s: float = 0.0
    model: str = EMBEDDING_MODEL


class Embedder:
    def __init__(self) -> None:
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            try:
                self._model = SentenceTransformer(EMBEDDING_MODEL, device="mps")
            except Exception:
                self._model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(
            texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True
        )
        return [v.tolist() for v in vectors]


def embed_repo(
    engine: Any,
    repo_name: str,
    limit: int | None = None,
    batch_size: int = 256,
    force: bool = False,
    progress: Any = print,
    embedder: Embedder | None = None,
) -> EmbedStats:
    import pygit2

    stats = EmbedStats()
    started = time.monotonic()
    embedder = embedder or Embedder()

    with Session(engine) as session:
        db_repo = session.scalars(select(Repo).where(Repo.name == repo_name)).first()
        if db_repo is None or not db_repo.local_path:
            raise ValueError(f"repo {repo_name!r} not ingested with a local_path")
        repo_id = int(db_repo.id)

        existing: set[tuple[str, str]] = set()
        if not force:
            rows = session.execute(
                select(DiscussionChunk.source_type, DiscussionChunk.source_id).where(
                    DiscussionChunk.repo_id == repo_id
                )
            ).all()
            existing = {(source_type, source_id) for source_type, source_id in rows}

        git_repo: Any = pygit2.Repository(db_repo.local_path)
        alive_paths = head_paths(git_repo, db_repo.head_sha or "")

        def flush(batch: list[tuple[ChunkDraft, list[float]]]) -> None:
            for draft, vec in batch:
                authored = datetime.fromisoformat(draft.authored_at) if draft.authored_at else None
                session.add(
                    DiscussionChunk(
                        repo_id=repo_id,
                        source_type=draft.source_type,
                        source_id=draft.source_id,
                        authored_at=authored,
                        title=draft.title[:500],
                        body=render_chunk_text(draft),
                        embedding=vec,
                        files_touched=draft.files_touched,
                        linked_commits=draft.linked_commits,
                        liveness_score=liveness_score(draft.files_touched, alive_paths),
                        embedding_model=EMBEDDING_MODEL,
                    )
                )
            session.commit()

        pending_batch: list[tuple[ChunkDraft, list[float]]] = []
        buffer_texts: list[str] = []
        buffer_drafts: list[ChunkDraft] = []

        drafts_iter = itertools.chain(
            commit_chunks(session, repo_id, limit=limit, exclude_source_ids=existing),
            pr_chunks(session, repo_id, limit=limit, exclude_source_ids=existing),
        )
        for draft in drafts_iter:
            buffer_texts.append(render_chunk_text(draft))
            buffer_drafts.append(draft)
            if len(buffer_texts) >= batch_size:
                vectors = embedder.encode(buffer_texts)
                pending_batch = list(zip(buffer_drafts, vectors, strict=True))
                flush(pending_batch)
                stats.chunks += len(pending_batch)
                buffer_texts.clear()
                buffer_drafts.clear()
                progress(f"  embedded {stats.chunks} chunks")

        if buffer_texts:
            vectors = embedder.encode(buffer_texts)
            flush(list(zip(buffer_drafts, vectors, strict=True)))
            stats.chunks += len(vectors)

        if engine.dialect.name == "postgresql":
            session.execute(
                sql_text(
                    "UPDATE discussion_chunks SET tsv = "
                    "to_tsvector('english', coalesce(title,'') || ' ' || body) "
                    "WHERE repo_id = :r AND tsv IS NULL"
                ),
                {"r": repo_id},
            )
            session.commit()

        stats.skipped_existing = len(existing)
    stats.duration_s = time.monotonic() - started
    return stats
