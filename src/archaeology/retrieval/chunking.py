from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pygit2
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from archaeology.storage.models import Commit, CommitPrLink, FileChange, PullRequest

SOURCE_COMMIT = "commit_message"
SOURCE_PR_BODY = "pr_body"
SOURCE_PR_DISCUSSION = "pr_discussion"
SOURCE_DOC = "doc_file"

MIN_BODY_CHARS = 20
_MERGE_PREFIXES = ("Merge ", "Revert ")
_HEADER_PATH_LIMIT = 5
_MAX_DISCUSSION_CHARS = 16_000
_COMMENT_SEPARATOR = "\n---\n"
MAX_SUBCHUNK_CHARS = 1_600


@dataclass(slots=True)
class ChunkDraft:
    source_type: str
    source_id: str
    authored_at: str | None
    title: str
    body: str
    files_touched: list[str] = field(default_factory=list)
    linked_commits: list[str] = field(default_factory=list)


def render_chunk_text(draft: ChunkDraft) -> str:
    header_parts: list[str] = []
    if draft.authored_at:
        header_parts.append(f"[{draft.authored_at[:10]}]")
    if draft.files_touched:
        shown = draft.files_touched[:_HEADER_PATH_LIMIT]
        more = len(draft.files_touched) - len(shown)
        suffix = f" (+{more} more)" if more > 0 else ""
        header_parts.append(", ".join(shown) + suffix)
    header = " ".join(header_parts).strip()
    pieces = [header, draft.title, "---", draft.body]
    return "\n".join(p.strip() for p in pieces if p and p.strip())


def _is_noise_commit(subject: str, body: str | None) -> bool:
    if subject.startswith(_MERGE_PREFIXES):
        return True
    if re.search(r"#\d+\)", subject):
        return False
    cleaned = (body or "").strip()
    return len(cleaned) < MIN_BODY_CHARS


def _paths_by_sha(session: Session, repo_id: int) -> dict[str, list[str]]:
    path_rows = session.execute(
        select(FileChange.sha, FileChange.path).where(FileChange.repo_id == repo_id)
    ).all()
    paths: dict[str, list[str]] = {}
    for sha, path in path_rows:
        paths.setdefault(sha, []).append(path)
    return paths


def commit_chunks(
    session: Session,
    repo_id: int,
    limit: int | None = None,
    exclude_source_ids: set[tuple[str, str]] | None = None,
) -> Iterator[ChunkDraft]:
    exclude = exclude_source_ids or set()
    paths_by_sha = _paths_by_sha(session, repo_id)

    stmt = (
        select(Commit)
        .where(Commit.repo_id == repo_id)
        .order_by(Commit.committed_at.desc().nullslast())
    )
    if limit is not None:
        stmt = stmt.limit(limit * 2)

    rows = list(session.scalars(stmt))
    produced = 0
    for row in rows:
        sha = row.sha
        if (SOURCE_COMMIT, sha) in exclude:
            continue
        body = (row.body or "").strip()
        subject = (row.subject or "").strip()
        if _is_noise_commit(subject, body):
            continue
        yield ChunkDraft(
            source_type=SOURCE_COMMIT,
            source_id=sha,
            authored_at=row.committed_at.isoformat() if row.committed_at else None,
            title=subject,
            body=body or subject,
            files_touched=sorted(set(paths_by_sha.get(sha, []))),
            linked_commits=[sha],
        )
        produced += 1
        if limit is not None and produced >= limit:
            return


def split_discussion(discussion: str) -> list[str]:
    """Pack comment-aligned segments into bins under MAX_SUBCHUNK_CHARS.

    A single oversized segment is hard-split on blank lines. Never drops text.
    """
    segments = [s.strip() for s in discussion.split(_COMMENT_SEPARATOR) if s.strip()]
    if not segments:
        return []

    bins: list[str] = []
    current: list[str] = []
    size = 0
    for segment in segments:
        while len(segment) > MAX_SUBCHUNK_CHARS:
            if current:
                bins.append(_COMMENT_SEPARATOR.join(current))
                current, size = [], 0
            cut = segment.rfind("\n\n", 0, MAX_SUBCHUNK_CHARS)
            if cut <= 0:
                cut = MAX_SUBCHUNK_CHARS
            bins.append(segment[:cut].strip())
            segment = segment[cut:].strip()
        if size + len(segment) > MAX_SUBCHUNK_CHARS and current:
            bins.append(_COMMENT_SEPARATOR.join(current))
            current, size = [], 0
        current.append(segment)
        size += len(segment) + len(_COMMENT_SEPARATOR)
    if current:
        bins.append(_COMMENT_SEPARATOR.join(current))
    return bins


def pr_chunks(
    session: Session,
    repo_id: int,
    limit: int | None = None,
    exclude_source_ids: set[tuple[str, str]] | None = None,
) -> Iterator[ChunkDraft]:
    exclude = exclude_source_ids or set()
    paths_by_sha = _paths_by_sha(session, repo_id)

    merge_links: dict[int, str] = {}
    link_rows = session.execute(
        select(CommitPrLink.pr_number, CommitPrLink.sha).where(CommitPrLink.repo_id == repo_id)
    ).all()
    for pr_number, sha in link_rows:
        merge_links.setdefault(pr_number, sha)

    rows = list(
        session.scalars(
            select(PullRequest)
            .where(PullRequest.repo_id == repo_id)
            .order_by(PullRequest.merged_at.desc().nullslast())
        )
    )

    produced = 0
    for pr in rows:
        source_id = f"pr:{pr.number}"

        title = (pr.title or "").strip() or f"PR #{pr.number}"
        merged_iso = pr.merged_at.isoformat() if pr.merged_at else None
        merge_sha = merge_links.get(pr.number)
        linked = [merge_sha] if merge_sha else []
        touched = sorted(set(paths_by_sha.get(merge_sha or "", [])))

        body_text = (pr.body or "").strip()
        if body_text and (SOURCE_PR_BODY, source_id) not in exclude:
            yield ChunkDraft(
                source_type=SOURCE_PR_BODY,
                source_id=source_id,
                authored_at=merged_iso,
                title=f"PR #{pr.number}: {title}",
                body=body_text,
                files_touched=touched,
                linked_commits=linked,
            )
            produced += 1

        discussion = (pr.discussion or "").strip()
        if discussion:
            bins = split_discussion(discussion)
            for index, bin_text in enumerate(bins, start=1):
                if (SOURCE_PR_DISCUSSION, f"{source_id}#{index}") in exclude:
                    continue
                suffix = f"#{index}" if len(bins) > 1 else "#1"
                yield ChunkDraft(
                    source_type=SOURCE_PR_DISCUSSION,
                    source_id=f"{source_id}{suffix}",
                    authored_at=merged_iso,
                    title=f"PR #{pr.number} discussion: {title}",
                    body=bin_text,
                    files_touched=touched,
                    linked_commits=linked,
                )
                produced += 1

        if limit is not None and produced >= limit:
            return


def split_markdown(text: str, max_chars: int = MAX_SUBCHUNK_CHARS) -> list[str]:
    """Split markdown on heading boundaries into bins under max_chars."""
    lines = text.splitlines(keepends=True)
    sections: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            sections.append("".join(current).strip())

    for line in lines:
        if line.startswith("## ") and current:
            flush()
            current = []
        current.append(line)
    flush()

    bins: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            bins.append(section)
            continue
        paragraphs = section.split("\n\n")
        bin_text = ""
        for para in paragraphs:
            if bin_text and len(bin_text) + len(para) + 2 > max_chars:
                bins.append(bin_text.strip())
                bin_text = ""
            bin_text += para + "\n\n"
        if bin_text.strip():
            bins.append(bin_text.strip())
    return [b for b in bins if b]


def doc_chunks(
    repo: Any,
    head_sha: str,
    exclude_source_ids: set[tuple[str, str]] | None = None,
) -> Iterator[ChunkDraft]:

    exclude = exclude_source_ids or set()
    root = repo[head_sha].tree
    stack: list[tuple[Any, str]] = [(root, "")]
    md_files: list[str] = []
    while stack:
        tree, prefix = stack.pop()
        for entry in tree:
            full = f"{prefix}{entry.name}"
            if int(entry.type) == 2:
                stack.append((repo[entry.id], f"{full}/"))
            elif entry.name.lower().endswith(".md"):
                md_files.append(full)

    last_commit_date: dict[str, str] = {}
    for commit in repo.walk(repo.head.target, int(pygit2.enums.SortMode.TIME)):
        iso = _commit_iso(commit)
        if iso is None:
            continue
        for touched_path in _commit_touched_paths(repo, commit):
            if touched_path not in last_commit_date:
                last_commit_date[touched_path] = iso

    for rel_path in sorted(md_files):
        try:
            blob = repo[root[rel_path].id]
        except KeyError:
            continue
        text = blob.data.decode("utf-8", errors="replace")
        title_source = text.lstrip("# ").splitlines()[0] if text.strip() else rel_path
        base_title = title_source[:120] or rel_path
        authored = last_commit_date.get(rel_path)

        bins = split_markdown(text)
        for index, bin_text in enumerate(bins, start=1):
            source_id = f"{rel_path}#{index}" if len(bins) > 1 else rel_path
            if (SOURCE_DOC, source_id) in exclude:
                continue
            yield ChunkDraft(
                source_type=SOURCE_DOC,
                source_id=source_id,
                authored_at=authored,
                title=f"{rel_path}: {base_title}",
                body=bin_text,
                files_touched=[rel_path],
                linked_commits=[],
            )


def _commit_iso(commit: Any) -> str | None:
    from datetime import UTC, datetime

    ts = getattr(commit, "commit_time", 0)
    return datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else None


def _commit_touched_paths(repo: Any, commit: Any) -> list[str]:
    paths: list[str] = []
    try:
        parents = commit.parent_ids
        base = repo[parents[0]].tree if parents else None
        diff = base.diff_to_tree(commit.tree) if base else commit.tree.diff_to_tree()
        for delta in diff.deltas:
            path = delta.new_file.path or delta.old_file.path
            if path:
                paths.append(path)
    except Exception:
        pass
    return paths


def count_chunkable(session: Session, repo_id: int) -> int:
    total = session.scalar(
        select(func.count()).select_from(Commit).where(Commit.repo_id == repo_id)
    )
    return int(total or 0)
