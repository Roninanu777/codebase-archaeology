from __future__ import annotations

import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from archaeology.config import DATABASE_URL
from archaeology.retrieval.embed import Embedder
from archaeology.retrieval.search import hybrid_search
from archaeology.routes.path_a import why_symbol
from archaeology.storage.status import repo_status

mcp = MCPServer(
    name="codebase-archaeology",
    description="Reconstructs why code exists from git history, with citations.",
)

_engine: Any = None


def _get_engine() -> Any:
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine

        _engine = create_engine(DATABASE_URL)
    return _engine


def _set_engine(engine: Any) -> None:
    global _engine
    _engine = engine


@mcp.tool()
def why_does_this_exist(repo: str, symbol: str, file: str | None = None) -> dict[str, Any]:
    """Trace a symbol to the commits that introduced and shaped it, with citations."""
    result = why_symbol(_get_engine(), repo, symbol, rel_path=file)
    from sqlalchemy.orm import Session

    with Session(_get_engine()) as session:
        status = repo_status(session, repo)
    payload: dict[str, Any] = {
        "status": result.status,
        "reason": result.reason,
        "symbol": result.symbol,
        "rel_path": result.rel_path,
        "span": None
        if result.span is None
        else {
            "start_line": result.span.start_line,
            "end_line": result.span.end_line,
            "kind": result.span.kind,
        },
        "introduced": None
        if result.introduced is None
        else {
            "sha": result.introduced.sha,
            "subject": result.introduced.subject,
            "author": result.introduced.author,
            "date": result.introduced.committed_at,
            "pr_refs": result.introduced.pr_refs,
        },
        "timeline": [
            {
                "sha": ev.sha,
                "role": ev.role,
                "subject": ev.subject,
                "date": ev.committed_at,
                "pr_refs": ev.pr_refs,
            }
            for ev in result.timeline
        ],
        "noise_dropped": result.noise_dropped,
        "index_status": status,
    }
    return payload


@mcp.tool()
def history_of_symbol(
    repo: str, symbol: str, file: str | None = None, n: int = 20
) -> list[dict[str, Any]]:
    """The commit timeline for a symbol, newest last; introducing commit first."""
    result = why_symbol(_get_engine(), repo, symbol, rel_path=file)
    return [
        {
            "sha": ev.sha,
            "role": ev.role,
            "subject": ev.subject,
            "date": ev.committed_at,
            "pr_refs": ev.pr_refs,
        }
        for ev in result.timeline[:n]
    ]


@mcp.tool()
def search_decisions(repo: str, question: str, n: int = 10) -> dict[str, Any]:
    """Hybrid retrieval over the repo's recorded decision corpus (commit messages for now)."""
    result = hybrid_search(_get_engine(), Embedder(), repo, question, top_n=n)
    from sqlalchemy.orm import Session

    with Session(_get_engine()) as session:
        status = repo_status(session, repo)
    return {
        "query": result.query,
        "abstained_reason": result.abstained_reason,
        "hits": [
            {
                "sha": hit.sha,
                "title": hit.title,
                "date": hit.authored_at,
                "liveness_score": hit.liveness_score,
                "stale": hit.stale,
                "dense_rank": hit.dense_rank,
                "sparse_rank": hit.sparse_rank,
            }
            for hit in result.hits[:n]
        ],
        "index_status": status,
    }


def main() -> int:
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
