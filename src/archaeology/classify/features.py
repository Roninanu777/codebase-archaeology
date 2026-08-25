from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pygit2.enums

FEATURE_EXTRACTOR_VERSION = "v1.floor"

_COMMENT_PREFIXES = ("//", "/*", "*", "#", "<!--", "%", ";", "--")
_DOC_EXTENSIONS = {".md", ".markdown", ".mdx", ".rst", ".txt"}
_SKIP_PATCH_PREFIXES = ("+++", "---", "@@", "diff ", "index ", "\\ No newline")

_STATUS_NAMES: dict[int, str] = {
    int(pygit2.enums.DeltaStatus.ADDED): "added",
    int(pygit2.enums.DeltaStatus.DELETED): "deleted",
    int(pygit2.enums.DeltaStatus.MODIFIED): "modified",
    int(pygit2.enums.DeltaStatus.RENAMED): "renamed",
    int(pygit2.enums.DeltaStatus.COPIED): "copied",
    int(pygit2.enums.DeltaStatus.TYPECHANGE): "typechange",
}


@dataclass(slots=True)
class FileDelta:
    path: str
    status: str
    old_path: str | None
    additions: int
    deletions: int


@dataclass(slots=True)
class ChangeFeatures:
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    binary_files: int = 0
    renamed_files: int = 0
    whitespace_only: bool = False
    comment_only: bool = False
    pure_rename: bool = False
    per_file: list[FileDelta] = field(default_factory=list)


def _is_commentish(line: str, suffix: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith(_COMMENT_PREFIXES):
        return False
    if stripped.startswith("#") and suffix in _DOC_EXTENSIONS:
        return False
    return True


def _normalize(line: str) -> str:
    return " ".join(line.split())


def _split_patch_lines(patch_text: str) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    added: list[str] = []
    for raw in patch_text.splitlines():
        if raw.startswith(_SKIP_PATCH_PREFIXES):
            continue
        if raw.startswith("+"):
            added.append(raw[1:])
        elif raw.startswith("-"):
            removed.append(raw[1:])
    return removed, added


def _iter_patches(diff: Any) -> Iterator[Any]:
    return iter(diff)


def extract_features(diff: Any) -> ChangeFeatures:
    out = ChangeFeatures()

    total_removed: list[str] = []
    total_added: list[str] = []
    saw_text_change = False
    saw_nonblank_change = False
    all_patches_commentish = True

    for patch in _iter_patches(diff):
        delta = patch.delta
        out.files_changed += 1
        status = int(delta.status)

        new_path = getattr(delta.new_file, "path", None)
        old_path = getattr(delta.old_file, "path", None)
        display_path = new_path or old_path or ""

        renamed = status == int(pygit2.enums.DeltaStatus.RENAMED) or status == int(
            pygit2.enums.DeltaStatus.COPIED
        )
        if renamed:
            out.renamed_files += 1

        is_binary = bool(getattr(delta, "flags", 0) & int(pygit2.enums.DiffFlag.BINARY))
        if patch.text is None or is_binary:
            out.binary_files += 1
            saw_text_change = True
            all_patches_commentish = False
            out.per_file.append(FileDelta(display_path, "binary", None, 0, 0))
            continue

        removed, added = _split_patch_lines(patch.text)
        out.additions += len(added)
        out.deletions += len(removed)
        total_removed.extend(removed)
        total_added.extend(added)

        if removed or added:
            saw_text_change = True

        suffix = os.path.splitext(display_path)[1].lower()
        nonblank = [line for line in removed + added if line.strip()]
        if nonblank:
            saw_nonblank_change = True
            if not all(_is_commentish(line, suffix) for line in nonblank):
                all_patches_commentish = False

        status_name = "renamed" if renamed else _STATUS_NAMES.get(status, "other")
        out.per_file.append(
            FileDelta(display_path, status_name, old_path, len(added), len(removed))
        )

    normalized_removed = [_normalize(line) for line in total_removed if line.strip()]
    normalized_added = [_normalize(line) for line in total_added if line.strip()]

    out.whitespace_only = saw_text_change and normalized_removed == normalized_added
    out.comment_only = (
        saw_text_change
        and not out.whitespace_only
        and saw_nonblank_change
        and all_patches_commentish
    )
    out.pure_rename = (
        out.files_changed > 0
        and out.renamed_files == out.files_changed
        and out.binary_files == 0
        and not saw_text_change
    )
    return out


def make_diff(repo: Any, commit: Any) -> Any:
    if commit.parent_ids:
        parent = repo[commit.parent_ids[0]]
        diff = parent.tree.diff_to_tree(commit.tree)
    else:
        diff = commit.tree.diff_to_tree()
    diff.find_similar()
    return diff
