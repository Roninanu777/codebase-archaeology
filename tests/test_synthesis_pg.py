from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine

from archaeology.config import DATABASE_URL


def _pg_available() -> bool:
    if os.environ.get("SKIP_PG_TESTS"):
        return False
    try:
        with create_engine(DATABASE_URL).connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="postgres not reachable")


def test_path_b_synthesis_cites_retrieved_hits() -> None:
    from archaeology.retrieval.embed import Embedder
    from archaeology.routes.synthesis import answer_any

    engine = create_engine(DATABASE_URL)
    question = "why was useMutableSource removed and replaced by useSyncExternalStore"
    canned = (
        "useMutableSource was removed because useSyncExternalStore covers its "
        "use cases with better tearing guarantees [pr:22292]. The replacement "
        "landed after the RFC process [80d9a4011]."
    )

    def fake_poster(
        url: str, payload: dict[str, str], headers: dict[str, str]
    ) -> dict[str, object]:
        return {
            "model": "test/model",
            "choices": [{"message": {"content": canned}}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 80},
        }

    routed = answer_any(
        engine,
        "facebook/react",
        question,
        poster=fake_poster,
        embedder=Embedder(),
        reranker=None,
    )

    assert routed["path"] == "B"
    result = routed["synthesis"]
    assert result.status == "answered"
    assert "pr:22292" in result.citations
    assert routed["evidence"] is not None
    assert len(routed["evidence"].hits) > 0


def test_path_b_abstains_when_model_says_insufficient() -> None:
    from archaeology.retrieval.embed import Embedder
    from archaeology.routes.synthesis import answer_any

    engine = create_engine(DATABASE_URL)
    canned = "INSUFFICIENT_EVIDENCE: retrieved chunks do not answer the question"

    def fake_poster(
        url: str, payload: dict[str, str], headers: dict[str, str]
    ) -> dict[str, object]:
        return {
            "model": "test/model",
            "choices": [{"message": {"content": canned}}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 20},
        }

    routed = answer_any(
        engine,
        "facebook/react",
        "what color was the bikeshed in the original scheduler discussion",
        poster=fake_poster,
        embedder=Embedder(),
        reranker=None,
    )
    assert routed["path"] == "B"
    assert routed["synthesis"].status == "abstained"
    assert (routed["synthesis"].abstained_reason or "").startswith("INSUFFICIENT_EVIDENCE")


def test_router_sends_symbol_down_path_a() -> None:
    from archaeology.retrieval.embed import Embedder
    from archaeology.routes.synthesis import answer_any

    engine = create_engine(DATABASE_URL)
    canned = "forwardRef exists to forward refs [bc70441c8]."

    def fake_poster(
        url: str, payload: dict[str, str], headers: dict[str, str]
    ) -> dict[str, object]:
        return {
            "model": "test/model",
            "choices": [{"message": {"content": canned}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 40},
        }

    routed = answer_any(
        engine,
        "facebook/react",
        "forwardRef",
        file="packages/react/src/ReactForwardRef.js",
        poster=fake_poster,
        embedder=Embedder(),
    )
    assert routed["path"] == "A"
    assert routed["synthesis"].status == "answered"
