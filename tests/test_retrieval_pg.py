import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from archaeology.config import DATABASE_URL


def _pg_available() -> bool:
    if os.environ.get("SKIP_PG_TESTS"):
        return False
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_available(), reason="postgres (pgvector) not reachable")


@pytest.fixture()
def pg_engine() -> Generator[Engine, None, None]:
    engine = create_engine(DATABASE_URL)
    yield engine


def test_pg_has_vector_and_chunks(pg_engine: Engine) -> None:
    inspector = inspect(pg_engine)
    tables = set(inspector.get_table_names())
    assert "discussion_chunks" in tables
    columns = {c["name"]: c for c in inspector.get_columns("discussion_chunks")}
    assert "embedding" in columns and "tsv" in columns
