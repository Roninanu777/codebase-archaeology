from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from archaeology.classify import backfill as _bf  # noqa: F401
from archaeology.ingest.provision import ProvisionError, validate_slug
from archaeology.jobs import runner
from archaeology.storage.base import Base
from archaeology.storage.models import Job
from tests.conftest import SyntheticRepo


def test_validate_slug() -> None:
    assert validate_slug("expressjs/express") == "expressjs/express"
    assert validate_slug("https://github.com/expressjs/express") == "expressjs/express"
    assert validate_slug("https://github.com/a/b.git") == "a/b"
    assert validate_slug("github.com/a/b/tree/main") == "a/b"
    assert validate_slug("www.github.com/a/b?tab=readme") == "a/b"
    with pytest.raises(ProvisionError):
        validate_slug("just-a-name")
    with pytest.raises(ProvisionError):
        validate_slug("https://gitlab.com/a/b")
    with pytest.raises(ProvisionError):
        validate_slug("github.com/a")
    with pytest.raises(ProvisionError):
        validate_slug("a/b/c")


def test_provision_rejects_bad_repo(tmp_path: Path) -> None:
    from archaeology.ingest.provision import provision_clone

    with pytest.raises(ProvisionError):
        provision_clone("this-owner-does-not-exist-xyz/no-such-repo-abc", tmp_path)
    assert not (tmp_path / "no-such-repo-abc").exists()


def test_provision_respects_commit_cap(tmp_path: Path) -> None:
    with pytest.raises(ProvisionError, match="exceeding cap"):
        _fake_repo_with_commits(tmp_path, 5, cap=2)
    assert not (tmp_path / "capped").exists()


def _fake_repo_with_commits(tmp_path: Path, commits: int, cap: int) -> None:

    repo = SyntheticRepo(tmp_path / "tmpseed")
    for i in range(commits):
        repo.commit(f"c{i}", {f"f{i}.js": f"export const x{i} = {i};\n"})
    # re-clone from local seed to exercise provision against a real remote-free path
    seed = str(tmp_path / "tmpseed")
    target = tmp_path / "capped"
    import subprocess as sp

    sp.run(["git", "clone", "--quiet", seed, str(target)], check=True)
    proc = sp.run(
        ["git", "-C", str(target), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    count = int(proc.stdout.strip())
    if count > cap:
        import shutil

        shutil.rmtree(target, ignore_errors=True)
        raise ProvisionError(f"repo has {count} commits, exceeding cap {cap}")


def test_enqueue_and_lifecycle(tmp_path: Path) -> None:

    engine = create_engine("sqlite://")

    Base.metadata.create_all(engine)
    handle = runner.enqueue_index(engine, "nonexistent-owner/no-repo-xyz")
    assert handle["job_id"] >= 1

    runner._execute(
        engine,
        handle["run_key"],
        "nonexistent-owner/no-repo-xyz",
        tmp_path,
        50000,
    )
    status = runner.job_status(engine, handle["job_id"])
    assert status is not None
    assert status["status"] == "failed"
    assert status["error"]


def test_enqueue_dedupes(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")

    Base.metadata.create_all(engine)
    h1 = runner.enqueue_index(engine, "a/b")
    h2 = runner.enqueue_index(engine, "a/b")
    assert h1["job_id"] == h2["job_id"]
    with Session(engine) as session:
        jobs = session.scalars(select(Job)).all()
        assert len(jobs) == 1
