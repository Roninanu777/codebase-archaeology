from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from archaeology.ingest.git import ingest_repository
from archaeology.routes.path_a import why_symbol
from tests.conftest import SyntheticRepo


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    from archaeology.storage.base import Base

    Base.metadata.create_all(engine)
    return engine


def test_path_a_end_to_end(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> None:
    engine = _engine()
    ingest_repository(engine, tmp_path / "jsrepo", name="t/js")

    result = why_symbol(engine, "t/js", "calc", rel_path="src/calc.js")

    assert result.status == "answered"
    assert result.span is not None
    assert result.span.start_line == 1
    assert result.noise_dropped == 2
    introduced = result.introduced
    assert introduced is not None
    assert introduced.subject == "add calc"
    subjects = [ev.subject for ev in result.timeline]
    assert subjects == ["add calc", "clamp result"]


def test_path_a_uses_cache_on_second_call(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> None:
    engine = _engine()
    ingest_repository(engine, tmp_path / "jsrepo", name="t/js")

    first = why_symbol(engine, "t/js", "calc", rel_path="src/calc.js")
    second = why_symbol(engine, "t/js", "calc", rel_path="src/calc.js")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert [ev.sha for ev in second.timeline] == [ev.sha for ev in first.timeline]


def test_path_a_abstains_on_unknown_symbol(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path
) -> None:
    engine = _engine()
    ingest_repository(engine, tmp_path / "jsrepo", name="t/js")

    result = why_symbol(engine, "t/js", "definitely_not_here", rel_path="src/calc.js")
    assert result.status == "abstained"
    assert result.reason == "symbol_not_found"


def test_path_a_finds_file_without_hint(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> None:
    engine = _engine()
    ingest_repository(engine, tmp_path / "jsrepo", name="t/js")

    result = why_symbol(engine, "t/js", "calc")
    assert result.status == "answered"
    assert result.rel_path == "src/calc.js"


def test_path_a_low_confidence_single_commit(tmp_path: Path) -> None:
    engine = _engine()
    repo = SyntheticRepo(tmp_path / "solo")
    repo.commit("just a function", {"only.js": "function solo() {\n  return 1;\n}\n"})
    ingest_repository(engine, tmp_path / "solo", name="t/solo")

    result = why_symbol(engine, "t/solo", "solo", rel_path="only.js")
    assert result.status == "low_confidence"
    assert result.reason == "single_uncited_commit"

    with Session(engine) as session:
        from archaeology.storage.models import LineageCache

        rows = session.query(LineageCache).all()
        assert len(rows) == 1
