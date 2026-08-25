from __future__ import annotations

from archaeology.symbols.resolver import resolve_symbol

JS_FN = b"""
function helper() { return 1; }

export function calc(a, b) {
  return a + b;
}
"""

JS_ARROW = b"""
const handler = (evt) => {
  return evt.type;
};

module.exports = { handler };
"""

TS_METHOD = b"""
class Store {
  constructor() { this.n = 0; }
  increment(step: number): number {
    this.n += step;
    return this.n;
  }
}
"""


def test_function_declaration_span() -> None:
    span = resolve_symbol(JS_FN, "x.js", "calc")
    assert span is not None
    assert span.kind == "function_declaration"
    assert span.start_line == 4
    assert span.end_line == 6


def test_arrow_const_declarator_span() -> None:
    span = resolve_symbol(JS_ARROW, "x.js", "handler")
    assert span is not None
    assert span.kind == "variable_declarator"
    assert span.start_line == 2
    assert span.end_line == 4


def test_ts_method_resolution() -> None:
    span = resolve_symbol(TS_METHOD, "store.ts", "increment")
    assert span is not None
    assert span.kind == "method_definition"
    assert span.start_line == 4
    assert span.end_line == 7


def test_unknown_symbol_returns_none() -> None:
    assert resolve_symbol(JS_FN, "x.js", "nope") is None


FLOW_SRC = (
    b"/** @flow */\n"
    b"\n"
    b"opaque type Handler = (event: Event) => void;\n"
    b"\n"
    b"export type RootType = {\n"
    b"  render(children: ReactNodeList): void,\n"
    b"};\n"
    b"\n"
    b"export function createRoot(\n"
    b"  container: Element,\n"
    b"  callback: ?() => mixed,\n"
    b"): RootType {\n"
    b"  return root;\n"
    b"}\n"
)


def test_flow_file_falls_back_to_regex_anchor() -> None:
    span = resolve_symbol(FLOW_SRC, "flow.js", "createRoot")
    assert span is not None
    assert span.kind == "regex_fallback"
    assert span.start_line == 9
    assert span.end_line == 14
