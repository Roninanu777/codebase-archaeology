from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}/[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"([A-Za-z0-9][A-Za-z0-9_.-]{0,80})/"
    r"([A-Za-z0-9][A-Za-z0-9_.-]{0,80}?)(?:\.git)?(?:[/?#].*)?$"
)


class ProvisionError(RuntimeError):
    pass


@dataclass(slots=True)
class ProvisionResult:
    path: Path
    head_sha: str
    commit_count: int
    reused: bool


def validate_slug(raw: str) -> str:
    raw = raw.strip()
    if _SLUG_RE.match(raw) and not raw.lower().startswith(("github.com/", "www.github.com/")):
        return raw
    match = _URL_RE.match(raw)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    raise ProvisionError(f"invalid repo {raw!r}; expected owner/repo or a github.com URL")


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ProvisionError(f"{' '.join(cmd)} failed: {proc.stderr.strip()[:300]}")


def _run_head(path: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ProvisionError(f"rev-parse failed: {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def _count_commits(path: Path) -> int:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ProvisionError(f"rev-count failed: {proc.stderr.strip()[:200]}")
    return int(proc.stdout.strip())


def provision_clone(
    slug: str,
    clones_dir: Path,
    max_commit_count: int = 50_000,
) -> ProvisionResult:
    validate_slug(slug)
    target = clones_dir / slug.split("/")[-1]
    url = f"https://github.com/{slug}.git"

    if (target / ".git").exists():
        _run(["git", "-C", str(target), "fetch", "origin", "--refetch"])
        return ProvisionResult(
            path=target,
            head_sha=_run_head(target),
            commit_count=_count_commits(target),
            reused=True,
        )

    clones_dir.mkdir(parents=True, exist_ok=True)
    try:
        _run(["git", "clone", "--filter=blob:none", url, str(target)])
        _run(["git", "-C", str(target), "config", "remote.origin.partialclonefilter", ""])
        _run(["git", "-C", str(target), "fetch", "origin", "--refetch"])
        head = _run_head(target)
        count = _count_commits(target)
        if count > max_commit_count:
            raise ProvisionError(f"repo has {count} commits, exceeding cap {max_commit_count}")
        return ProvisionResult(path=target, head_sha=head, commit_count=count, reused=False)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
