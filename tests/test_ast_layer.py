from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from archaeology.classify.backfill import backfill_ast_features
from archaeology.ingest.git import ingest_repository
from archaeology.storage.models import Commit, CommitFeature, CommitSignificance
from tests.conftest import SyntheticRepo

_V1 = "export function calc(a) {\n  const label = 'total';\n  return a + 1; // running total\n}\n"
_WS = "export function calc(a) {\n\tconst label = 'total';\n\treturn a + 1; // running total\n}\n"
_QUOTES = (
    'export function calc(a) {\n  const label = "total";\n  return a + 1; // running total\n}\n'
)
_SEMICOLONS_AND_COMMENT_MOVE = (
    "export function calc(a) {\n  const label = 'total';\n  return a + 1;\n}\n/* running total */\n"
)
_RENAME = "export function calc(a) {\n  const tag = 'total';\n  return a + 1; // running total\n}\n"


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    from archaeology.storage.base import Base

    Base.metadata.create_all(engine)
    return engine


def _label_for(engine: Engine, sha: str) -> str:
    with Session(engine) as session:
        row = session.scalars(select(CommitSignificance).where(CommitSignificance.sha == sha)).one()
        return row.label


def _shas_by_subject(engine: Engine) -> dict[str, str]:
    with Session(engine) as session:
        rows = session.scalars(select(Commit)).all()
        return {str(r.subject): r.sha for r in rows}


def test_ast_layer_labels(synthetic_repo: None, tmp_path: Path) -> None:  # noqa: ARG001
    engine = _engine()
    repo = SyntheticRepo(tmp_path / "ast")
    repo.commit("base", {"m.js": _V1})
    repo.commit("tabs", {"m.js": _WS})
    repo.commit("quotes", {"m.js": _QUOTES})
    repo.commit("comment moved out", {"m.js": _SEMICOLONS_AND_COMMENT_MOVE})
    repo.commit("rename local var", {"m.js": _RENAME})
    ingest_repository(engine, tmp_path / "ast", name="t/ast")

    stats = backfill_ast_features(engine, "t/ast")
    assert stats.processed == 5

    shas = _shas_by_subject(engine)
    assert _label_for(engine, shas["base"]) == "significant"
    assert _label_for(engine, shas["tabs"]) == "insignificant_whitespace"
    assert _label_for(engine, shas["quotes"]) == "insignificant_format"
    assert _label_for(engine, shas["comment moved out"]) == "insignificant_format"
    assert _label_for(engine, shas["rename local var"]) == "significant"

    with Session(engine) as session:
        flagged = session.scalars(
            select(CommitFeature).where(CommitFeature.ast_format_only.is_(True))
        ).all()
        assert len(flagged) >= 2
        versions = {fr.ast_extractor_version for fr in session.scalars(select(CommitFeature)).all()}
        assert versions == {"v1.ast-js"}


def test_backfill_idempotent_second_run(synthetic_repo: None, tmp_path: Path) -> None:
    engine = _engine()
    repo = SyntheticRepo(tmp_path / "ast2")
    repo.commit("base", {"m.js": _V1})
    ingest_repository(engine, tmp_path / "ast2", name="t/ast2")
    backfill_ast_features(engine, "t/ast2")
    second = backfill_ast_features(engine, "t/ast2")
    assert second.processed == 0
