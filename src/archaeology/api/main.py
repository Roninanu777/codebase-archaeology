from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from archaeology.classify.backfill import backfill_ast_features
from archaeology.config import DATABASE_URL
from archaeology.ingest.git import ingest_repository
from archaeology.retrieval.embed import Embedder
from archaeology.retrieval.search import hybrid_search
from archaeology.routes.path_a import why_symbol
from archaeology.routes.synthesis import synthesize_why
from archaeology.storage.status import repo_status


class IndexRequest(BaseModel):
    path: str
    name: str
    url: str | None = None
    classify: bool = True


def _engine(url: str | None = None) -> Any:
    return create_engine(url or DATABASE_URL)


def _payload(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj):
        return dict(asdict(cast(Any, obj)))
    if isinstance(obj, dict):
        return dict(obj)
    raise TypeError(f"cannot serialize {type(obj)!r}")


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="Codebase Archaeology", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    engine = _engine(database_url)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/repos")
    def list_repos() -> list[dict[str, Any]]:
        from sqlalchemy import select

        from archaeology.storage.models import Repo as RepoModel

        with Session(engine) as session:
            names = session.scalars(select(RepoModel.name).order_by(RepoModel.name)).all()
        return [repo_status(session, name) or {"name": name} for name in names]

    @app.post("/repos/index")
    def index_repo(request: IndexRequest) -> dict[str, Any]:
        try:
            stats = ingest_repository(engine, request.path, name=request.name, url=request.url)
            classification: dict[str, Any] | None = None
            if request.classify and not stats.skipped:
                cls_stats = backfill_ast_features(engine, request.name)
                classification = {
                    "processed": cls_stats.processed,
                    "relabeled": cls_stats.relabeled,
                    "label_counts": cls_stats.label_counts,
                }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ingest": {
                "commits": stats.commits,
                "file_changes": stats.file_changes,
                "skipped": stats.skipped,
                "duration_s": round(stats.duration_s, 2),
            },
            "classification": classification,
        }

    @app.get("/repos/{name:path}/status")
    def get_status(name: str) -> dict[str, Any]:
        with Session(engine) as session:
            status = repo_status(session, name)
        if status is None:
            raise HTTPException(status_code=404, detail=f"unknown repo {name!r}")
        return status

    @app.get("/repos/{name:path}/why/{symbol}")
    def get_why(name: str, symbol: str, file: str | None = None) -> dict[str, Any]:
        result = why_symbol(engine, name, symbol, rel_path=file)
        with Session(engine) as session:
            status = repo_status(session, name)
        payload = _payload(result)
        payload["index_status"] = status
        return payload

    @app.get("/repos/{name:path}/answer/{symbol}")
    def get_answer(name: str, symbol: str, file: str | None = None) -> dict[str, Any]:
        try:
            result = synthesize_why(engine, name, symbol, file=file)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _payload(result)

    @app.get("/repos/{name:path}/ask")
    def post_ask(name: str, q: str, n: int = 10) -> dict[str, Any]:
        try:
            result = hybrid_search(engine, Embedder(), name, q, top_n=n)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        with Session(engine) as session:
            status = repo_status(session, name)
        payload = _payload(result)
        payload["index_status"] = status
        return payload

    return app


app = create_app()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archaeology-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(create_app(args.database_url), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
