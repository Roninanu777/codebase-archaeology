from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from archaeology.storage.models import LineageCache


@dataclass(slots=True)
class LineageCommit:
    sha: str
    authored_at: str
    subject: str


@dataclass(slots=True)
class LineageResult:
    commits: list[LineageCommit] = field(default_factory=list)
    cache_hit: bool = False


def walk_lineage(
    repo_path: str,
    rel_path: str,
    start_line: int,
    end_line: int,
    timeout_s: int = 300,
) -> list[LineageCommit]:
    spec = f"-L {start_line},{end_line}:{rel_path}"
    cmd = [
        "git",
        "-C",
        repo_path,
        "log",
        spec,
        "--no-patch",
        "--format=%H%x1f%aI%x1f%s%x1e",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        msg = f"git log -L failed: {proc.stderr.strip()[:500]}"
        raise RuntimeError(msg)

    commits: list[LineageCommit] = []
    for record in proc.stdout.split("\x1e"):
        parts = record.strip("\n").split("\x1f")
        if len(parts) == 3 and parts[0]:
            commits.append(LineageCommit(sha=parts[0], authored_at=parts[1], subject=parts[2]))
    return commits


def cached_lineage(
    session: Session,
    engine: Any,
    repo_id: int,
    head_sha: str,
    rel_path: str,
    symbol: str,
    start_line: int,
    end_line: int,
    repo_path: str,
) -> LineageResult:
    existing = session.scalars(
        select(LineageCache).where(
            LineageCache.repo_id == repo_id,
            LineageCache.file == rel_path,
            LineageCache.symbol == symbol,
            LineageCache.head_sha == head_sha,
        )
    ).first()
    if existing is not None and existing.commit_shas:
        return LineageResult(
            commits=[
                LineageCommit(sha=str(s), authored_at="", subject="") for s in existing.commit_shas
            ],
            cache_hit=True,
        )

    walked = walk_lineage(repo_path, rel_path, start_line, end_line)
    if walked:
        row = LineageCache(
            repo_id=repo_id,
            file=rel_path,
            symbol=symbol,
            head_sha=head_sha,
            commit_shas=[c.sha for c in walked],
        )
        session.add(row)
        session.commit()
    return LineageResult(commits=walked, cache_hit=False)
