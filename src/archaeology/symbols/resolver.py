from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser


@dataclass(slots=True)
class SymbolSpan:
    name: str
    kind: str
    file: str
    start_line: int
    end_line: int


_DECLARATION_KINDS = {
    "function_declaration",
    "generator_function_declaration",
    "function_signature",
    "abstract_class_declaration",
    "class_declaration",
}
_METHOD_KINDS = {"method_definition", "method_signature", "abstract_method_signature"}
_VALUE_FUNCTION_KINDS = {"arrow_function", "function_expression", "generator_function"}
_DECLARATOR_KINDS = {"variable_declarator"}


def _languages_for(path: str) -> list[Language]:
    suffix = path.lower().rsplit(".", 1)[-1]
    if suffix == "ts":
        return [Language(tree_sitter_typescript.language_typescript())]
    if suffix == "tsx":
        return [Language(tree_sitter_typescript.language_tsx())]
    if suffix == "jsx":
        return [
            Language(tree_sitter_javascript.language()),
            Language(tree_sitter_typescript.language_tsx()),
        ]
    return [
        Language(tree_sitter_javascript.language()),
        Language(tree_sitter_typescript.language_typescript()),
    ]


def _parse_best(source: bytes, path: str) -> Any:
    from tree_sitter import Tree

    tree: Tree | None = None
    for lang in _languages_for(path):
        try:
            parser = Parser(lang)
        except TypeError:
            parser = Parser()
            parser.language = lang
        candidate = parser.parse(source)
        if tree is None:
            tree = candidate
        if not candidate.root_node.has_error:
            return candidate
    assert tree is not None
    return tree


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def resolve_symbol(
    source: bytes,
    path: str,
    symbol: str,
) -> SymbolSpan | None:
    if symbol.encode() not in source:
        return None
    tree = _parse_best(source, path)
    best: SymbolSpan | None = None
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        kind = node.type

        name_node = node.child_by_field_name("name")
        if name_node is not None and _node_text(name_node, source) == symbol:
            span_kind: str | None = None
            end_node: Node = node
            if kind in _DECLARATION_KINDS or kind in _METHOD_KINDS:
                span_kind = kind
            elif kind in _DECLARATOR_KINDS:
                value = node.child_by_field_name("value")
                if value is not None and value.type in _VALUE_FUNCTION_KINDS:
                    span_kind = "variable_declarator"
                    end_node = value
            if span_kind is not None:
                candidate = SymbolSpan(
                    name=symbol,
                    kind=span_kind,
                    file=path,
                    start_line=node.start_point[0] + 1,
                    end_line=end_node.end_point[0] + 1,
                )
                if best is None or candidate.start_line < best.start_line:
                    best = candidate

        for child in reversed(node.children):
            stack.append(child)

    if best is None and tree.root_node.has_error:
        return _fallback_span(source, path, symbol)
    return best


def _declaration_pattern(symbol: str) -> re.Pattern[str]:
    escaped = re.escape(symbol)
    return re.compile(
        rf"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function\*?\s+{escaped}\b"
        rf"|(?:abstract\s+)?class\s+{escaped}\b"
        rf"|(?:const|let|var)\s+{escaped}\s*=[^=]"
        rf"|(?:public|private|protected|static|readonly|\*)*\s*{escaped}\s*[(<])"
    )


def _fallback_span(source: bytes, path: str, symbol: str) -> SymbolSpan | None:
    pattern = _declaration_pattern(symbol)
    lines = source.decode("utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if not pattern.search(line):
            continue
        depth = 0
        seen_brace = False
        end = index
        for j in range(index, len(lines)):
            for ch in lines[j]:
                if ch == "{":
                    depth += 1
                    seen_brace = True
                elif ch == "}":
                    depth -= 1
                    if seen_brace and depth == 0:
                        end = j
                        break
            else:
                if seen_brace and depth == 0:
                    break
                continue
            break
        return SymbolSpan(
            name=symbol,
            kind="regex_fallback",
            file=path,
            start_line=index + 1,
            end_line=end + 1,
        )
    return None


def resolve_in_repo(
    repo: Any,
    head_sha: str,
    rel_path: str,
    symbol: str,
) -> SymbolSpan | None:
    commit_obj = repo[head_sha]
    entry = commit_obj.tree[rel_path]
    blob = repo[entry.id]
    return resolve_symbol(blob.data, rel_path, symbol)
