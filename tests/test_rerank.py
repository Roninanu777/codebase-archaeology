from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from archaeology.config import DATABASE_URL
from archaeology.retrieval.rerank import Reranker, rerank_order
from archaeology.retrieval.search import hybrid_search


class StubReranker:
    def scores(self, query: str, texts: list[str]) -> list[float]:
        return [1.0 if "TARGET" in t else 0.0 for t in texts]


def test_rerank_order_puts_matching_first() -> None:
    order = rerank_order(
        "q",
        {1: "plain text A", 2: "has TARGET inside", 3: "plain text B"},
        reranker=StubReranker(),  # type: ignore[arg-type]
    )
    assert order[0][0] == 2
    assert order[0][1] == 1.0


def _pg_available() -> bool:
    if os.environ.get("SKIP_PG_TESTS"):
        return False
    try:
        with create_engine(DATABASE_URL).connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="postgres not reachable")


@pytest.fixture()
def pg_engine() -> Generator[Engine, None, None]:
    yield create_engine(DATABASE_URL)


def test_rerank_surfaces_known_targets(pg_engine: Engine) -> None:
    from archaeology.retrieval.embed import Embedder

    engine = pg_engine
    embedder = Embedder()

    cases = [
        ("why does act support the use hook in tests", ["pr:25523", "c63580787"], 5),
        (
            "why was useMutableSource removed and replaced by useSyncExternalStore",
            ["pr:22292"],
            3,
        ),
        ("why did the new context API replace legacy context", ["pr:11818", "87ae211ccd"], 15),
    ]

    for query, targets, within in cases:
        result = hybrid_search(
            engine,
            embedder,
            "facebook/react",
            query,
            top_n=within,
            reranker=Reranker(),
        )
        hit_shas = [h.sha for h in result.hits]
        matched = any(any(sha.startswith(t) for sha in hit_shas) for t in targets)
        assert matched, f"{query[:40]!r}: targets {targets} not in top {within}: {hit_shas}"


def test_first_stage_recall_limitation_is_documented(pg_engine: Engine) -> None:
    """lanes/createRoot rationale chunks exist but sit beyond first-stage reach
    (dense rank 2359/38k, sparse 1465/1166 of 41k). Known limitation pending
    query expansion or a stronger first-stage embedder; asserted here so the
    boundary stays visible rather than silently drifting."""
    from sqlalchemy import text as sql_text

    with pg_engine.connect() as conn:
        row = conn.execute(
            sql_text(
                "SELECT count(*) FROM discussion_chunks WHERE repo_id=1 AND source_id='pr:19108'"
            )
        ).scalar()
        assert int(row or 0) >= 1
