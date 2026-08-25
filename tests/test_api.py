from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from archaeology.api.main import create_app
from archaeology.ingest.git import ingest_repository
from archaeology.storage.base import Base
from tests.conftest import SyntheticRepo


def _client_with_repo(
    synthetic_js_repo: SyntheticRepo, tmp_path: Path
) -> tuple[TestClient, Engine]:
    db_path = tmp_path / "api.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    ingest_repository(engine, tmp_path / "jsrepo", name="t/js")
    return TestClient(create_app(url)), engine


def test_status_and_why_endpoints(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> None:
    client, _ = _client_with_repo(synthetic_js_repo, tmp_path)

    response = client.get("/repos/t/js/status")
    assert response.status_code == 200
    body = response.json()
    assert body["commits"] == 4
    assert body["complete_at_head"] is True
    assert body["significance"]["significant"] >= 2

    response = client.get("/repos/t/js/why/calc")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["introduced"]["subject"] == "add calc"
    assert body["index_status"]["name"] == "t/js"

    missing = client.get("/repos/nope/why/thing")
    assert missing.status_code == 200
    assert missing.json()["status"] == "abstained"


def test_index_endpoint_idempotent(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> None:
    client, _ = _client_with_repo(synthetic_js_repo, tmp_path)

    response = client.post(
        "/repos/index",
        json={"path": str(tmp_path / "jsrepo"), "name": "t/js", "classify": False},
    )
    assert response.status_code == 200
    assert response.json()["ingest"]["skipped"] is True


def test_unknown_repo_status_404() -> None:
    client = TestClient(create_app())
    assert client.get("/repos/ghost/status").status_code == 404
