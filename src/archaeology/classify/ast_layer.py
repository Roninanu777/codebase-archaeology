from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pygit2
import pygit2.enums
import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

AST_EXTRACTOR_VERSION = "v1.ast-js"

_CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}
_MAX_BLOB_BYTES = 500_000


@dataclass(slots=True)
class AstVerdict:
    applicable: bool
    format_only: bool
    files_judged: int


def _primary_language(path: str) -> Language | None:
    suffix = path.lower().rsplit(".", 1)[-1]
    if suffix == "ts":
        return Language(tree_sitter_typescript.language_typescript())
    if suffix == "tsx":
        return Language(tree_sitter_typescript.language_tsx())
    if suffix in ("js", "jsx"):
        return Language(tree_sitter_javascript.language())
    return None


def _parser(lang: Language) -> Parser:
    try:
        return Parser(lang)
    except TypeError:
        parser = Parser()
        parser.language = lang
        return parser


def _normalize_string(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] in "'\"`" and stripped[-1] == stripped[0]:
        return "string:" + stripped[1:-1]
    return "string:" + stripped


def _serialize(node: Node, source: bytes, out: list[tuple[str, str | None]]) -> None:
    if node.type == "comment":
        return
    named_children = node.named_children
    raw = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    if node.type == "string":
        out.append(("string", _normalize_string(raw)))
        return
    if not named_children:
        out.append((node.type, raw))
        return
    out.append((node.type, None))
    for child in named_children:
        _serialize(child, source, out)


def serialize_tree(root: Node, source: bytes) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    _serialize(root, source, out)
    return out


def _blob_data(repo: Any, oid: Any) -> bytes | None:
    try:
        obj = repo[oid]
    except (KeyError, ValueError):
        return None
    data: bytes | None = getattr(obj, "data", None)
    if data is None or len(data) > _MAX_BLOB_BYTES:
        return None
    return data


def file_is_format_only(repo: Any, old_oid: Any, new_oid: Any, path: str) -> bool | None:
    lang = _primary_language(path)
    if lang is None:
        return None
    old_src = _blob_data(repo, old_oid)
    new_src = _blob_data(repo, new_oid)
    if old_src is None or new_src is None or old_src == new_src:
        return None if old_src != new_src else True
    parser = _parser(lang)
    old_tree = parser.parse(old_src)
    new_tree = parser.parse(new_src)
    return serialize_tree(old_tree.root_node, old_src) == serialize_tree(
        new_tree.root_node, new_src
    )


_ELIGIBLE_STATUSES = {int(pygit2.enums.DeltaStatus.MODIFIED)}


def commit_ast_feature(repo: Any, diff: Any) -> AstVerdict:
    applicable = False
    format_only = True
    judged = 0
    for patch in diff:
        delta = patch.delta
        status = int(delta.status)
        if status not in _ELIGIBLE_STATUSES:
            continue
        path = delta.new_file.path or delta.old_file.path
        if not path or os.path.splitext(path)[1].lower() not in _CODE_SUFFIXES:
            continue
        applicable = True
        verdict = file_is_format_only(repo, delta.old_file.id, delta.new_file.id, path)
        if verdict is None or verdict is False:
            format_only = False
            break
        judged += 1
    return AstVerdict(
        applicable=applicable, format_only=applicable and format_only, files_judged=judged
    )
