from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pygit2
import pygit2.enums
from sqlalchemy import select
from sqlalchemy.orm import Session

from archaeology.classify.labels import (
    INSIGNIFICANT_COMMENT,
    INSIGNIFICANT_WHITESPACE,
    SIGNIFICANT,
)
from archaeology.lineage.walker import cached_lineage
from archaeology.storage.models import Commit, CommitSignificance, Repo
from archaeology.symbols.resolver import SymbolSpan, resolve_in_repo, resolve_symbol

_PR_REF = re.compile(r"\(#(\d+)\)")

_FLOOR_LABELS = {INSIGNIFICANT_WHITESPACE, INSIGNIFICANT_COMMENT}
_CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}
_MAX_SEARCH_FILES = 4000


@dataclass(slots=True)
class CommitEvidence:
    sha: str
    role: str
    subject: str
    author: str | None
    committed_at: str | None
    body: str | None
    pr_refs: list[int] = field(default_factory=list)
    label: str = SIGNIFICANT


@dataclass(slots=True)
class PathAResult:
    status: str
    reason: str | None
    repo: str
    symbol: str
    rel_path: str | None = None
    span: SymbolSpan | None = None
    introduced: CommitEvidence | None = None
    timeline: list[CommitEvidence] = field(default_factory=list)
    noise_dropped: int = 0
    cache_hit: bool = False


def _abstain(repo_name: str, symbol: str, reason: str) -> PathAResult:
    return PathAResult(status="abstained", reason=reason, repo=repo_name, symbol=symbol)


def _find_symbol_file(repo: Any, head_sha: str, symbol: str) -> tuple[str, SymbolSpan] | None:
    root_tree = repo[head_sha].tree
    is_tree = int(pygit2.enums.ObjectType.TREE)
    stack: list[tuple[Any, str]] = [(root_tree, "")]
    checked = 0
    while stack and checked < _MAX_SEARCH_FILES:
        tree, prefix = stack.pop()
        for entry in tree:
            if int(entry.type) == is_tree:
                stack.append((repo[entry.id], f"{prefix}{entry.name}/"))
                continue
            suffix = entry.name.rsplit(".", 1)[-1].lower()
            if f".{suffix}" not in _CODE_SUFFIXES:
                continue
            checked += 1
            blob = repo[entry.id]
            span = resolve_symbol(blob.data, f"{prefix}{entry.name}", symbol)
            if span is not None:
                return f"{prefix}{entry.name}", span
    return None


def why_symbol(
    engine: Any,
    repo_name: str,
    symbol: str,
    rel_path: str | None = None,
    repo_path_override: str | None = None,
    head_override: str | None = None,
) -> PathAResult:
    with Session(engine) as session:
        db_repo = session.scalars(select(Repo).where(Repo.name == repo_name)).first()
        if db_repo is None:
            return _abstain(repo_name, symbol, "unknown_repo")

        repo_path = repo_path_override or db_repo.local_path
        if not repo_path:
            return _abstain(repo_name, symbol, "missing_local_clone")

        try:
            pygit2_repo: Any = pygit2.Repository(str(repo_path))
        except Exception:
            return _abstain(repo_name, symbol, "local_clone_unreadable")

        resolved_head = head_override or str(pygit2_repo.head.target)

        located: tuple[str, SymbolSpan] | None = None
        if rel_path:
            span = resolve_in_repo(pygit2_repo, resolved_head, rel_path, symbol)
            if span is not None:
                located = (rel_path, span)
        else:
            located = _find_symbol_file(pygit2_repo, resolved_head, symbol)

        if located is None:
            return _abstain(repo_name, symbol, "symbol_not_found")
        found_path, span = located

        lineage = cached_lineage(
            session=session,
            engine=engine,
            repo_id=int(db_repo.id),
            head_sha=resolved_head,
            rel_path=found_path,
            symbol=symbol,
            start_line=span.start_line,
            end_line=span.end_line,
            repo_path=str(repo_path),
        )

        shas = [c.sha for c in lineage.commits]
        rows: dict[str, Commit] = {}
        if shas:
            fetched = session.scalars(
                select(Commit).where(Commit.repo_id == int(db_repo.id), Commit.sha.in_(shas))
            ).all()
            rows = {c.sha: c for c in fetched}

        sig_rows = session.execute(
            select(CommitSignificance.sha, CommitSignificance.label).where(
                CommitSignificance.repo_id == int(db_repo.id),
                CommitSignificance.sha.in_(shas),
            )
        ).all()
        labels = {sha: label for sha, label in sig_rows}

    evidence: list[CommitEvidence] = []
    noise_dropped = 0
    for index, sha in enumerate(reversed(shas)):
        label = labels.get(sha, SIGNIFICANT)
        if label != SIGNIFICANT:
            noise_dropped += 1
            continue
        row = rows.get(sha)
        subject = (row.subject if row else "") or ""
        match = _PR_REF.search(subject)
        evidence.append(
            CommitEvidence(
                sha=sha[:9],
                role="introduced" if index == 0 else "modified",
                subject=subject,
                author=row.author_name if row else None,
                committed_at=(
                    row.committed_at.date().isoformat() if row and row.committed_at else None
                ),
                body=row.body if row else None,
                pr_refs=[int(match.group(1))] if match else [],
            )
        )

    introduced = next((ev for ev in evidence if ev.role == "introduced"), None)
    status = "answered"
    reason: str | None = None
    if not evidence:
        status, reason = "abstained", "no_significant_history"
    elif introduced is not None:
        body_clean = (introduced.body or "").strip()
        subject_only = body_clean in ("", introduced.subject.strip())
        if len(evidence) == 1 and not introduced.pr_refs and subject_only:
            status, reason = "low_confidence", "single_uncited_commit"

    return PathAResult(
        status=status,
        reason=reason,
        repo=repo_name,
        symbol=symbol,
        rel_path=found_path,
        span=span,
        introduced=introduced,
        timeline=evidence,
        noise_dropped=noise_dropped,
        cache_hit=lineage.cache_hit,
    )
