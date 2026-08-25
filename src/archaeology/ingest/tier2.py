from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from archaeology.ingest.github import (
    COMMENTS_PER_PR,
    MIN_RATE_REMAINING,
    PAGE_SIZE,
    PRS_QUERY,
    PrPage,
    gh_cli_token,
    graphql_post,
    parse_pr_page,
    store_pr_page,
)
from archaeology.storage.models import Job, Repo


@dataclass(slots=True)
class BackfillStats:
    fetched: int = 0
    stored_new: int = 0
    pages: int = 0
    complete: bool = False
    duration_s: float = 0.0
    rate_remaining: int | None = None


def _get_or_create_job(session: Session, run_key: str, repo_id: int) -> Job:
    job = session.scalars(select(Job).where(Job.run_key == run_key)).first()
    if job is None:
        job = Job(kind="tier2_backfill", payload={"repo_id": repo_id}, run_key=run_key)
        session.add(job)
        session.commit()
    return job


def backfill_pull_requests(
    engine: Any,
    repo_name: str,
    max_pages: int | None = None,
    sleep_s: float = 0.5,
    progress: Callable[[str], None] = print,
    poster: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> BackfillStats:
    stats = BackfillStats()
    started = time.monotonic()
    owner, _, name = repo_name.partition("/")
    if not name:
        raise ValueError(f"repo name must be 'owner/repo', got {repo_name!r}")

    post = poster or graphql_post(gh_cli_token())
    run_key = f"tier2:{repo_name}"

    with Session(engine) as session:
        db_repo = session.scalars(select(Repo).where(Repo.name == repo_name)).first()
        if db_repo is None:
            raise ValueError(f"unknown repo {repo_name!r}; ingest tier-1 first")
        repo_id = int(db_repo.id)

        job = _get_or_create_job(session, run_key, repo_id)
        cursor: str | None = (job.payload or {}).get("cursor")
        if (job.payload or {}).get("complete"):
            stats.complete = True
            stats.duration_s = time.monotonic() - started
            return stats

        while True:
            if stats.rate_remaining is not None and stats.rate_remaining < MIN_RATE_REMAINING:
                progress(f"rate limit low ({stats.rate_remaining}); stopping for this run")
                break

            data = post(
                PRS_QUERY,
                {
                    "owner": owner,
                    "name": name,
                    "cursor": cursor,
                    "first": PAGE_SIZE,
                    "cFirst": COMMENTS_PER_PR,
                },
            )
            page: PrPage = parse_pr_page(data)
            stats.pages += 1
            stats.fetched += len(page.prs)
            stats.stored_new += store_pr_page(session, repo_id, page)
            stats.rate_remaining = page.rate_remaining

            cursor = page.end_cursor
            job.payload = {**(job.payload or {}), "cursor": cursor}
            session.commit()

            if stats.pages % 10 == 0:
                progress(
                    f"  page {stats.pages}: fetched {stats.fetched} "
                    f"(new {stats.stored_new}), rate={page.rate_remaining}"
                )

            if max_pages is not None and stats.pages >= max_pages:
                break
            if not page.has_next:
                job.payload = {**(job.payload or {}), "complete": True}
                session.commit()
                stats.complete = True
                break

            time.sleep(sleep_s)

    stats.duration_s = time.monotonic() - started
    return stats
