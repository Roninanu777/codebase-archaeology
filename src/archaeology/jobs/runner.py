from __future__ import annotations

import threading
import traceback
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from archaeology.storage.models import Job, Repo

_lock = threading.Lock()
_worker_started = False


def _load_job(session: Session, run_key: str) -> Job | None:
    return session.scalars(select(Job).where(Job.run_key == run_key)).first()


def github_available() -> bool:
    from archaeology.ingest.github import resolve_github_token

    try:
        resolve_github_token()
        return True
    except RuntimeError:
        return False


def enqueue_index(engine: Any, slug: str) -> dict[str, Any]:
    from archaeology.ingest.provision import validate_slug

    normalized = validate_slug(slug)
    run_key = f"index-remote:{normalized}"
    with Session(engine) as session:
        existing = _load_job(session, run_key)
        if existing is not None and existing.status in ("pending", "running", "done"):
            return {"job_id": int(existing.id), "run_key": run_key, "status": existing.status}
        if existing is not None and existing.status == "failed":
            existing.status = "pending"
            existing.payload = {**(existing.payload or {}), "stage": "queued"}
            existing.last_error = None
            session.commit()
            handle = {"job_id": int(existing.id), "run_key": run_key, "status": "pending"}
            _ensure_worker(engine)
            return handle
        job = Job(
            kind="index_remote",
            payload={"slug": normalized, "stage": "queued"},
            status="pending",
            run_key=run_key,
        )
        session.add(job)
        session.commit()
        handle = {"job_id": int(job.id), "run_key": run_key, "status": "pending"}
    _ensure_worker(engine)
    return handle


def job_status(engine: Any, job_id: int) -> dict[str, Any] | None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            return None
        payload = job.payload or {}
        return {
            "job_id": int(job.id),
            "run_key": job.run_key,
            "status": job.status,
            "stage": payload.get("stage"),
            "detail": payload.get("detail"),
            "error": job.last_error,
        }


def _set_stage(engine: Any, run_key: str, stage: str, detail: str | None = None) -> None:
    with Session(engine) as session:
        job = _load_job(session, run_key)
        if job is None:
            return
        job.payload = {**(job.payload or {}), "stage": stage, "detail": detail}
        if stage == "done":
            job.status = "done"
        session.commit()


def _fail(engine: Any, run_key: str, message: str) -> None:
    tb = traceback.format_exc()[-1200:]
    with Session(engine) as session:
        job = _load_job(session, run_key)
        if job is not None:
            job.status = "failed"
            job.payload = {**(job.payload or {}), "stage": "failed", "detail": message[:300]}
            job.last_error = f"{message[:200]}\n{tb}"
            session.commit()


def _execute(engine: Any, run_key: str, slug: str, clones_dir: Any, max_commit_count: int) -> None:
    from archaeology.classify.backfill import backfill_ast_features
    from archaeology.ingest.git import ingest_repository
    from archaeology.ingest.provision import provision_clone
    from archaeology.ingest.tier2 import backfill_pull_requests
    from archaeology.retrieval.embed import embed_repo

    def stage(name: str, detail: str | None = None) -> None:
        with Session(engine) as session:
            job = _load_job(session, run_key)
            if job is not None:
                job.payload = {**(job.payload or {}), "stage": name, "detail": detail}
                session.commit()

    try:
        stage("cloning", None)
        result = provision_clone(slug, clones_dir, max_commit_count)

        stage("commits", f"{result.commit_count} commits")
        stats = ingest_repository(engine, result.path, name=slug, url=f"https://github.com/{slug}")

        stage("significance", f"{stats.commits} commits")
        backfill_ast_features(engine, slug, progress=lambda _m: None)

        if github_available():
            stage("prs", None)
            backfill_pull_requests(engine, slug, progress=lambda _m: None)
        else:
            stage("prs", "skipped (no GITHUB_TOKEN)")

        stage("embedding", None)
        emb = embed_repo(engine, slug, progress=lambda _m: None)

        with Session(engine) as session:
            repo_row = session.scalars(select(Repo).where(Repo.name == slug)).first()
            if repo_row is not None:
                repo_row.local_path = str(result.path)
                session.commit()

        _set_stage(engine, run_key, "done", f"{stats.commits} commits, {emb.chunks} chunks")
    except Exception as exc:
        _fail(engine, run_key, str(exc))


def _run_one_pending(engine: Any, clones_dir: Any, max_commit_count: int) -> bool:
    with Session(engine) as session:
        job = session.scalars(
            select(Job).where(Job.kind == "index_remote", Job.status == "pending")
        ).first()
        if job is None:
            return False
        slug = (job.payload or {}).get("slug")
        run_key = job.run_key or f"index-remote:{slug}"
        if not slug:
            job.status = "failed"
            job.last_error = "job payload missing slug"
            session.commit()
            return True
        job.status = "running"
        session.commit()

    _execute(engine, run_key, str(slug), clones_dir, max_commit_count)
    return True


def _ensure_worker(engine: Any) -> None:
    global _worker_started
    with _lock:
        if _worker_started:
            return

        from archaeology.config import CLONES_DIR, MAX_COMMIT_COUNT

        def loop() -> None:
            import time

            while True:
                progressed = _run_one_pending(engine, CLONES_DIR, MAX_COMMIT_COUNT)
                if not progressed:
                    time.sleep(2.0)

        thread = threading.Thread(target=loop, daemon=True, name="index-worker")
        thread.start()
        _worker_started = True
