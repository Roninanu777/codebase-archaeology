from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from archaeology.ingest.git import ingest_repository
from archaeology.routes.synthesis import render_evidence, synthesize_why
from archaeology.storage.base import Base
from archaeology.storage.models import Trace
from tests.conftest import SyntheticRepo


def _setup(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> Engine:
    url = f"sqlite:///{tmp_path / 'syn.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    ingest_repository(engine, tmp_path / "jsrepo", name="t/js")
    return engine


def _fake_poster(canned: str) -> Any:
    def post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        assert payload["messages"][0]["role"] == "system"
        return {
            "model": payload["model"],
            "choices": [{"message": {"content": canned}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    return post


def test_synthesis_never_needs_key_when_poster_injected(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    engine = _setup(synthetic_js_repo, tmp_path)
    result = synthesize_why(
        engine,
        "t/js",
        "calc",
        file="src/calc.js",
        model="test/model",
        poster=_fake_poster("answer [3f93ca1c8]"),
    )
    assert result.status == "answered"


def test_synthesis_answers_with_citations_and_trace(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path
) -> None:
    engine = _setup(synthetic_js_repo, tmp_path)
    canned = (
        "calc exists to add numbers [add calc's sha is unknown] citing [7bee9fbdd] and [3f93ca1c8]."
    )
    result = synthesize_why(
        engine,
        "t/js",
        "calc",
        file="src/calc.js",
        model="test/model",
        poster=_fake_poster(canned),
    )

    assert result.status == "answered"
    assert result.model == "test/model"
    assert isinstance(result.citations, list)

    with Session(engine) as session:
        trace = session.scalars(select(Trace)).one()
        assert trace.stage == "synthesis"
        assert trace.model == "test/model"
        assert trace.prompt_tokens == 100


def test_evidence_bundle_contains_shas_and_anchor(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path
) -> None:
    engine = _setup(synthetic_js_repo, tmp_path)
    from archaeology.routes.path_a import why_symbol

    path_a = why_symbol(engine, "t/js", "calc", rel_path="src/calc.js")
    bundle = render_evidence(path_a)
    for ev in path_a.timeline:
        assert f"[{ev.sha}]" in bundle
    assert "src/calc.js" in bundle
    assert len(bundle) <= 7000


def test_abstention_short_circuits_without_llm_call(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path
) -> None:
    engine = _setup(synthetic_js_repo, tmp_path)

    def exploding_poster(
        url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        raise AssertionError("LLM must not be called on abstention path")

    result = synthesize_why(
        engine,
        "t/js",
        "definitely_not_here",
        file="src/calc.js",
        poster=exploding_poster,
    )
    assert result.status == "abstained"
    with Session(engine) as session:
        count = session.scalar(select(text_func_count()))
        assert count == 0


def text_func_count() -> Any:
    from sqlalchemy import func

    return func.count(Trace.id)


def test_insufficient_evidence_response_becomes_abstention(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path
) -> None:
    engine = _setup(synthetic_js_repo, tmp_path)
    canned = "INSUFFICIENT_EVIDENCE: no recorded rationale in commit bodies"
    result = synthesize_why(engine, "t/js", "calc", file="src/calc.js", poster=_fake_poster(canned))
    assert result.status == "abstained"
    reason = result.abstained_reason or ""
    assert reason.startswith("INSUFFICIENT_EVIDENCE")


def test_router_sends_symbols_and_prose_down_different_paths() -> None:
    from archaeology.routes.synthesis import looks_like_symbol

    assert looks_like_symbol("createRoot") is True
    assert looks_like_symbol("React.memo") is True
    assert looks_like_symbol("can you tell me how does the reconciler work?") is False
    assert looks_like_symbol("why lanes") is False


def test_mermaid_block_extracted_and_stripped(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path
) -> None:
    engine = _setup(synthetic_js_repo, tmp_path)
    from archaeology.routes.path_a import why_symbol

    path_a = why_symbol(engine, "t/js", "calc", rel_path="src/calc.js")
    assert path_a.introduced is not None
    real_sha = path_a.introduced.sha
    canned = (
        f"calc adds numbers [{real_sha}].\n\n"
        f"```mermaid\nflowchart TD\n  A[{real_sha}] --> B[calc]\n```\n"
    )
    result = synthesize_why(
        engine,
        "t/js",
        "calc",
        file="src/calc.js",
        model="test/model",
        poster=_fake_poster(canned),
    )
    assert result.status == "answered"
    assert "```" not in (result.answer or "")
    assert result.mermaid is not None
    assert result.mermaid.startswith("flowchart TD")
    assert real_sha in result.citations
