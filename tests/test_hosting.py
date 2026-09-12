from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from archaeology.api.auth import require_synthesis_token
from archaeology.api.main import create_app
from archaeology.retrieval.search import build_dense_sql, build_sparse_sql
from archaeology.routes.synthesis import SynthesisResult
from archaeology.storage.base import Base


def test_require_token_opens_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SYNTHESIS_TOKEN", raising=False)
    require_synthesis_token(None)


def test_require_token_enforces_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNTHESIS_TOKEN", "sekrit")
    with pytest.raises(HTTPException) as exc:
        require_synthesis_token(None)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        require_synthesis_token("wrong")
    require_synthesis_token("sekrit")


def _client(tmp_path: Path) -> TestClient:
    url = f"sqlite:///{tmp_path / 'hosting.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return TestClient(create_app(url))


def test_answer_endpoint_token_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_answer_any(engine, name, query, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "path": "A",
            "synthesis": SynthesisResult(
                status="answered", symbol=query, repo=name, answer="x", model="test"
            ),
            "evidence": None,
        }

    monkeypatch.setattr("archaeology.api.main.answer_any", fake_answer_any)
    client = _client(tmp_path)

    monkeypatch.delenv("SYNTHESIS_TOKEN", raising=False)
    assert client.post("/repos/t/js/answer", json={"query": "calc"}).status_code == 200

    monkeypatch.setenv("SYNTHESIS_TOKEN", "sekrit")
    assert client.post("/repos/t/js/answer", json={"query": "calc"}).status_code == 403
    assert (
        client.post(
            "/repos/t/js/answer",
            json={"query": "calc"},
            headers={"X-Archaeology-Token": "wrong"},
        ).status_code
        == 403
    )
    ok = client.post(
        "/repos/t/js/answer",
        json={"query": "calc"},
        headers={"X-Archaeology-Token": "sekrit"},
    )
    assert ok.status_code == 200
    assert ok.json()["path"] == "A"


def test_index_remote_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path)
    monkeypatch.setenv("SYNTHESIS_TOKEN", "sekrit")
    resp = client.post("/repos/index-remote", json={"repo": "a/b"})
    assert resp.status_code == 403


def test_read_endpoints_stay_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path)
    monkeypatch.setenv("SYNTHESIS_TOKEN", "sekrit")
    assert client.get("/healthz").status_code == 200
    assert client.get("/repos").status_code == 200


def test_resolve_github_token_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from archaeology.ingest import github

    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setattr(github, "gh_cli_token", lambda: "cli-token")
    assert github.resolve_github_token() == "env-token"

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert github.resolve_github_token() == "cli-token"


def test_halfvec_sql_switch() -> None:
    dense_vec = str(build_dense_sql(halfvec=False))
    dense_half = str(build_dense_sql(halfvec=True))
    assert "AS vector" in dense_vec
    assert "AS halfvec" in dense_half

    sparse = str(build_sparse_sql())
    assert "d.tsv @@ q" in sparse


def test_github_available_reflects_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from archaeology.jobs import runner

    monkeypatch.setattr(
        "archaeology.ingest.github.resolve_github_token",
        lambda: (_ for _ in ()).throw(RuntimeError("no token")),
    )
    assert runner.github_available() is False

    monkeypatch.setattr("archaeology.ingest.github.resolve_github_token", lambda: "tok")
    assert runner.github_available() is True
