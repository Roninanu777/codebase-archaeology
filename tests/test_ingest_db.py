from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from archaeology.ingest.git import ingest_repository
from archaeology.storage.base import Base
from archaeology.storage.models import (
    Commit,
    CommitFeature,
    CommitSignificance,
    FileChange,
)
from tests.conftest import SyntheticRepo


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def test_ingest_roundtrip_and_idempotence(synthetic_repo: SyntheticRepo, tmp_path: Path) -> None:
    engine = _engine()
    stats = ingest_repository(engine, tmp_path / "repo", name="test/synthetic")

    assert stats.skipped is False
    assert stats.commits == 5
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Commit)) == 5
        label_rows = session.execute(
            select(CommitSignificance.label, func.count()).group_by(CommitSignificance.label)
        ).all()
        labels: dict[str, int] = {str(label): int(count) for label, count in label_rows}
        assert labels["insignificant_whitespace"] == 1
        assert labels["insignificant_comment"] == 1
        assert labels["significant"] == 3

        renamed = session.scalars(select(FileChange).where(FileChange.status == "renamed")).one()
        assert renamed.old_path == "app.py"
        assert renamed.path == "calc.py"

        feature_rows = session.scalars(select(CommitFeature)).all()
        assert len(feature_rows) == 5
        assert all(fr.extractor_version for fr in feature_rows)

    rerun = ingest_repository(engine, tmp_path / "repo", name="test/synthetic")
    assert rerun.skipped is True
    assert rerun.commits == 0


def test_incremental_reingest_new_commits(synthetic_repo: SyntheticRepo, tmp_path: Path) -> None:
    engine = _engine()
    ingest_repository(engine, tmp_path / "repo", name="test/synthetic")
    synthetic_repo.commit("post-index commit", {"extra.py": "# just a comment\n"})
    stats = ingest_repository(engine, tmp_path / "repo", name="test/synthetic")
    assert stats.skipped is False
    assert stats.commits == 1
