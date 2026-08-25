from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from archaeology.storage.models import CommitPrLink, PullRequest

GITHUB_GRAPHQL = "https://api.github.com/graphql"
PAGE_SIZE = 100
COMMENTS_PER_PR = 50
MIN_RATE_REMAINING = 200
MAX_BODY_CHARS = 60_000
MAX_DISCUSSION_CHARS = 16_000
MAX_COMMENT_CHARS = 2_000

PRS_QUERY = """query($owner:String!, $name:String!, $cursor:String, $first:Int!, $cFirst:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequests(first:$first, after:$cursor, states:MERGED,
                 orderBy:{field:CREATED_AT, direction:ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body state createdAt mergedAt
        author { login }
        mergeCommit { oid }
        comments(first:$cFirst) { totalCount nodes { author { login } body createdAt } }
      }
    }
  }
  rateLimit { remaining resetAt }
}"""


@dataclass(slots=True)
class PrComment:
    author: str | None
    body: str
    created_at: str | None


@dataclass(slots=True)
class PullRequestNode:
    number: int
    title: str | None
    body: str | None
    author: str | None
    created_at: str | None
    merged_at: str | None
    merge_sha: str | None
    comment_count: int
    discussion: str | None = None
    comments: list[PrComment] = field(default_factory=list)


@dataclass(slots=True)
class PrPage:
    prs: list[PullRequestNode]
    end_cursor: str | None
    has_next: bool
    rate_remaining: int


Poster = Callable[[str, dict[str, Any]], dict[str, Any]]


def gh_cli_token() -> str:
    out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
    token = out.stdout.strip()
    if not token:
        raise RuntimeError("no GitHub token; run `gh auth login` or set GITHUB_TOKEN")
    return token


def graphql_post(token: str) -> Poster:
    def post(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            GITHUB_GRAPHQL,
            json={"query": query, "variables": variables},
            headers={"Authorization": f"bearer {token}"},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"graphql errors: {payload['errors'][:2]}")
        data: dict[str, Any] = payload["data"]
        return data

    return post


def parse_pr_page(data: dict[str, Any]) -> PrPage:
    connection = data["repository"]["pullRequests"]
    nodes: list[PullRequestNode] = []
    for node in connection["nodes"]:
        comments = [
            PrComment(
                author=(c.get("author") or {}).get("login"),
                body=(c.get("body") or "")[:MAX_COMMENT_CHARS],
                created_at=c.get("createdAt"),
            )
            for c in node["comments"]["nodes"]
        ]
        parts = [f"{c.author or 'unknown'}: {c.body}" for c in comments if c.body.strip()]
        discussion = "\n---\n".join(parts)[:MAX_DISCUSSION_CHARS] or None
        nodes.append(
            PullRequestNode(
                number=int(node["number"]),
                title=node.get("title"),
                body=(node.get("body") or "")[:MAX_BODY_CHARS] or None,
                author=(node.get("author") or {}).get("login"),
                created_at=node.get("createdAt"),
                merged_at=node.get("mergedAt"),
                merge_sha=(node.get("mergeCommit") or {}).get("oid"),
                comment_count=int(node["comments"]["totalCount"]),
                discussion=discussion,
                comments=comments,
            )
        )
    page_info = connection["pageInfo"]
    return PrPage(
        prs=nodes,
        end_cursor=page_info.get("endCursor"),
        has_next=bool(page_info.get("hasNextPage")),
        rate_remaining=int(data["rateLimit"]["remaining"]),
    )


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def store_pr_page(session: Session, repo_id: int, page: PrPage) -> int:
    stored = 0
    for pr in page.prs:
        existing = session.scalars(
            select(PullRequest).where(
                PullRequest.repo_id == repo_id, PullRequest.number == pr.number
            )
        ).first()
        if existing is None:
            session.add(
                PullRequest(
                    repo_id=repo_id,
                    number=pr.number,
                    title=pr.title,
                    body=pr.body,
                    author=pr.author,
                    state="MERGED",
                    created_at=_parse_dt(pr.created_at),
                    merged_at=_parse_dt(pr.merged_at),
                    merge_sha=pr.merge_sha,
                    comment_count=pr.comment_count,
                    discussion=pr.discussion,
                )
            )
            stored += 1
        elif existing.discussion is None and pr.discussion:
            existing.discussion = pr.discussion
        if pr.merge_sha:
            link_exists = session.scalars(
                select(CommitPrLink).where(
                    CommitPrLink.repo_id == repo_id,
                    CommitPrLink.sha == pr.merge_sha,
                    CommitPrLink.pr_number == pr.number,
                )
            ).first()
            if link_exists is None:
                session.add(CommitPrLink(repo_id=repo_id, sha=pr.merge_sha, pr_number=pr.number))
    session.commit()
    return stored
