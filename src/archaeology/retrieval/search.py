from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from archaeology.retrieval.embed import QUERY_PREFIX
from archaeology.storage.models import DiscussionChunk, Repo

RRF_K = 60
STALE_THRESHOLD = 0.34


@dataclass(slots=True)
class SearchHit:
    chunk_id: int
    sha: str
    title: str
    authored_at: str | None
    score: float
    dense_rank: int | None
    sparse_rank: int | None
    liveness_score: float | None

    @property
    def stale(self) -> bool:
        return self.liveness_score is not None and self.liveness_score < STALE_THRESHOLD


@dataclass(slots=True)
class SearchResult:
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    duration_s: float = 0.0
    abstained_reason: str | None = None


def rrf_fuse(rank_lists: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rank_lists:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def _repo_id(session: Session, repo_name: str) -> int:
    row = session.scalars(select(Repo).where(Repo.name == repo_name)).first()
    if row is None:
        raise ValueError(f"unknown repo {repo_name!r}")
    return int(row.id)


def hybrid_search(
    engine: Any,
    embedder: Any,
    repo_name: str,
    query: str,
    k_dense: int = 50,
    k_sparse: int = 50,
    top_n: int = 20,
) -> SearchResult:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("hybrid_search requires PostgreSQL (pgvector + tsvector)")

    started = time.monotonic()
    with Session(engine) as session:
        repo_id = _repo_id(session, repo_name)

    qvec = embedder.encode([QUERY_PREFIX + query])[0]
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"

    dense_sql = sql_text(
        "SELECT id FROM discussion_chunks "
        "WHERE repo_id = :r AND embedding IS NOT NULL "
        "ORDER BY embedding <=> CAST(:v AS vector) LIMIT :k"
    )
    sparse_sql = sql_text(
        "SELECT id FROM discussion_chunks, websearch_to_tsquery('english', :q) q "
        "WHERE repo_id = :r AND tsv @@ q "
        "ORDER BY ts_rank_cd(tsv, q) DESC LIMIT :k"
    )

    with engine.connect() as conn:
        dense_rows = conn.execute(dense_sql, {"r": repo_id, "v": vec_literal, "k": k_dense}).all()
        sparse_rows = conn.execute(sparse_sql, {"r": repo_id, "q": query, "k": k_sparse}).all()

    dense_ids = [int(r[0]) for r in dense_rows]
    sparse_ids = [int(r[0]) for r in sparse_rows]

    fused = rrf_fuse([dense_ids, sparse_ids])
    ordered = sorted(fused.items(), key=lambda kv: -kv[1])[:top_n]

    result = SearchResult(query=query)

    if not ordered:
        result.abstained_reason = "no_hits"
        return result

    with Session(engine) as session:
        chunks = session.scalars(
            select(DiscussionChunk).where(DiscussionChunk.id.in_([i for i, _ in ordered]))
        ).all()
        by_id = {c.id: c for c in chunks}

    for chunk_id, score in ordered:
        chunk = by_id.get(chunk_id)
        if chunk is None:
            continue
        result.hits.append(
            SearchHit(
                chunk_id=chunk.id,
                sha=str(chunk.source_id)[:9],
                title=(chunk.title or "")[:120],
                authored_at=(chunk.authored_at.date().isoformat() if chunk.authored_at else None),
                score=score,
                dense_rank=dense_ids.index(chunk.id) + 1 if chunk.id in dense_ids else None,
                sparse_rank=sparse_ids.index(chunk.id) + 1 if chunk.id in sparse_ids else None,
                liveness_score=chunk.liveness_score,
            )
        )

    result.duration_s = time.monotonic() - started
    if all(hit.stale for hit in result.hits):
        result.abstained_reason = "all_stale"
    return result
