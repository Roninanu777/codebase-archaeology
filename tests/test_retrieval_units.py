from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from archaeology.retrieval.chunking import (
    SOURCE_COMMIT,
    ChunkDraft,
    commit_chunks,
    render_chunk_text,
)
from archaeology.retrieval.liveness import liveness_score
from archaeology.retrieval.search import rrf_fuse
from archaeology.storage.base import Base
from archaeology.storage.models import Commit


def _seed(engine: Engine) -> int:
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        from archaeology.storage.models import Repo

        repo_row = Repo(name="t/chunks")
        session.add(repo_row)
        session.flush()
        rid = int(repo_row.id)

        def add(sha: str, subject: str, body: str | None, committed_at: str) -> None:
            session.add(
                Commit(
                    repo_id=rid,
                    sha=sha,
                    subject=subject,
                    body=body,
                    committer_name="a",
                    author_name="a",
                )
            )

        add(
            "1" * 40,
            "Add lanes scheduler",
            "We use 31-bit lanes so updates can be\nsplit across priority ranges.",
            "2020-06-11T00:00:00",
        )
        add("2" * 40, "Merge pull request #100", None, "2020-06-12T00:00:00")
        add("3" * 40, "typo", "fix typo", "2020-06-13T00:00:00")
        add(
            "4" * 40,
            "Explain backoff",
            "Retry uses exponential backoff because thundering\nherd was observed in practice.",
            "2021-01-01T00:00:00",
        )
        session.commit()
        return rid


def test_commit_chunks_filters_merges_and_tiny_bodies() -> None:
    engine = _sqlite_engine()
    _seed(engine)
    with Session(engine) as session:
        rid = 1
        drafts = list(commit_chunks(session, rid))
        subjects = [d.title for d in drafts]
        assert "Merge pull request #100" not in subjects
        assert "typo" not in subjects
        assert set(subjects) == {"Add lanes scheduler", "Explain backoff"}
        assert all(d.source_type == SOURCE_COMMIT for d in drafts)


def test_render_chunk_text_includes_header_title_and_body() -> None:
    draft = ChunkDraft(
        source_type=SOURCE_COMMIT,
        source_id="a" * 40,
        authored_at="2020-07-01T10:00:00",
        title="Use lanes",
        body="Because ranges.",
        files_touched=["src/a.js", "src/b.js"],
        linked_commits=["a" * 40],
    )
    text = render_chunk_text(draft)
    assert text.startswith("[2020-07-01] src/a.js, src/b.js")
    assert "Use lanes" in text and "Because ranges." in text.split("---")[-1]


def test_rrf_fusion_prefers_items_in_both_lists() -> None:
    fused = rrf_fuse([[1, 2, 3], [2, 5, 1]])
    assert fused[2] > fused[3]
    assert fused[2] > fused[5]
    assert fused[1] > fused[3]


def test_liveness_fraction() -> None:
    existing = {"src/a.js"}
    assert liveness_score(["src/a.js", "src/gone.js"], existing) == 0.5
    assert liveness_score([], existing) == 0.0


def _sqlite_engine() -> Engine:
    return create_engine("sqlite://")
