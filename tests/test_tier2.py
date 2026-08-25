from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from archaeology.ingest.git import ingest_repository
from archaeology.ingest.github import parse_pr_page, store_pr_page
from archaeology.ingest.tier2 import backfill_pull_requests
from archaeology.retrieval.chunking import commit_chunks, pr_chunks
from archaeology.storage.base import Base
from tests.conftest import SyntheticRepo

PAGE_JSON = json.loads(Path("tests/fixtures/pr_page.json").read_text())


def _seed_repo_with_pr(engine: Engine, tmp_path: Path) -> None:
    repo = SyntheticRepo(tmp_path / "prrepo")
    repo.commit(
        "Merge pull request #7 from dev/feature\n\nAdd widget (#7)",
        {"w.js": "export const w = 1;\n"},
    )
    Base.metadata.create_all(engine)
    ingest_repository(engine, tmp_path / "prrepo", name="t/pr")
    with Session(engine) as session:
        from archaeology.storage.models import Repo

        row = session.scalars(select(Repo).where(Repo.name == "t/pr")).one()
        page = parse_pr_page(PAGE_JSON["data"])
        store_pr_page(session, int(row.id), page)
        session.commit()


def test_parse_pr_page_extracts_discussion() -> None:
    page = parse_pr_page(PAGE_JSON["data"])
    assert len(page.prs) == 2
    first = page.prs[0]
    assert first.number == 7
    assert "seb: why this approach" in (first.discussion or "")
    assert first.merge_sha is not None
    assert page.has_next is True


def test_store_and_chunk_prs(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    _seed_repo_with_pr(engine, tmp_path)

    with Session(engine) as session:
        drafts = list(pr_chunks(session, 1))
    kinds = {d.source_type for d in drafts}
    assert kinds == {"pr_body", "pr_discussion"}
    body_draft = next(d for d in drafts if d.source_type == "pr_body")
    assert body_draft.source_id == "pr:7"
    assert body_draft.title.startswith("PR #7:")
    # files_touched come from the linked merge commit's file changes
    assert isinstance(body_draft.linked_commits, list)


def test_backfill_checkpoint_resume(synthetic_js_repo: SyntheticRepo, tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    ingest_repository(engine, tmp_path / "jsrepo", name="t/js2")

    pages: list[dict[str, Any]] = [PAGE_JSON["data"]]
    calls: list[dict[str, Any]] = []

    def fake_post(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append(variables)
        if len(calls) == 1:
            return pages[0]
        last = json.loads(json.dumps(pages[0]))
        prs = last["repository"]["pullRequests"]
        prs["pageInfo"] = {"hasNextPage": False, "endCursor": "c2"}
        result: dict[str, Any] = last
        return result

    stats = backfill_pull_requests(engine, "t/js2", poster=fake_post)
    assert stats.complete is True
    assert stats.fetched >= 4

    stats2 = backfill_pull_requests(engine, "t/js2", poster=fake_post)
    assert stats2.complete is True
    assert stats2.pages == 0


def test_commit_chunks_still_works_after_refactor() -> None:
    engine = create_engine("sqlite://")
    from sqlalchemy.orm import Session as S

    from archaeology.storage.base import Base as B
    from archaeology.storage.models import Commit, Repo

    B.metadata.create_all(engine)
    with S(engine) as session:
        r = Repo(name="x")
        session.add(r)
        session.flush()
        session.add(
            Commit(
                repo_id=r.id,
                sha="a" * 40,
                subject="Real change",
                body="This explains the reason for the decision in enough text.",
            )
        )
        session.commit()
        drafts = list(commit_chunks(session, r.id))
        assert len(drafts) == 1
        assert drafts[0].source_type == "commit_message"
