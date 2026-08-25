from __future__ import annotations

from typing import Any


def head_paths(repo: Any, head_sha: str) -> set[str]:
    root = repo[head_sha].tree
    paths: list[str] = []
    stack: list[tuple[Any, str]] = [(root, "")]
    while stack:
        tree, prefix = stack.pop()
        for entry in tree:
            full = f"{prefix}{entry.name}"
            if int(entry.type) == 2:
                stack.append((repo[entry.id], f"{full}/"))
            else:
                paths.append(full)
    return set(paths)


def liveness_score(paths: list[str], existing: set[str]) -> float:
    if not paths:
        return 0.0
    alive = sum(1 for p in paths if p in existing)
    return alive / len(paths)
