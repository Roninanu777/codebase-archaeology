from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from archaeology.config import DATABASE_URL
from archaeology.retrieval.embed import Embedder
from archaeology.retrieval.rerank import Reranker
from archaeology.retrieval.search import hybrid_search
from archaeology.routes.path_a import why_symbol


@dataclass(slots=True)
class CaseResult:
    id: str
    path: str
    kind: str
    passed: bool
    detail: str
    latency_s: float


@dataclass(slots=True)
class Report:
    results: list[CaseResult] = field(default_factory=list)

    def add(self, result: CaseResult) -> None:
        self.results.append(result)

    def metric(self, path: str, kind: str) -> tuple[int, int] | None:
        rows = [r for r in self.results if r.path == path and r.kind == kind]
        if not rows:
            return None
        return sum(1 for r in rows if r.passed), len(rows)

    def to_markdown(self, title: str) -> str:
        lines = [f"# {title}", ""]
        groups = [
            ("A", "attribution"),
            ("A", "abstention"),
            ("B", "retrieval"),
            ("B", "known_gap"),
            ("S", "synthesis"),
        ]
        for path, kind in groups:
            metric = self.metric(path, kind)
            if metric is None:
                continue
            correct, total = metric
            latencies = [r.latency_s for r in self.results if r.path == path and r.kind == kind]
            avg_ms = 1000 * sum(latencies) / max(len(latencies), 1)
            p95_ms = 1000 * sorted(latencies)[int(0.95 * (len(latencies) - 1))]
            lines.append(f"## {kind} ({path})")
            lines.append("")
            lines.append(f"**{correct}/{total}** passed - avg {avg_ms:.0f}ms - p95 {p95_ms:.0f}ms")
            lines.append("")
            lines.append("| case | ok | detail | latency ms |")
            lines.append("|---|---|---|---|")
            for r in self.results:
                if r.path == path and r.kind == kind:
                    mark = "yes" if r.passed else "**NO**"
                    lines.append(f"| {r.id} | {mark} | {r.detail} | {1000 * r.latency_s:.0f} |")
            lines.append("")
        return "\n".join(lines)


def _run_case(
    case: dict[str, Any], engine: Any, embedder: Embedder, reranker: Reranker
) -> CaseResult:
    started = time.monotonic()
    kind = case["kind"]
    path = case["path"]

    if kind == "attribution":
        result = why_symbol(engine, case["repo"], case["symbol"], rel_path=case.get("file"))
        introduced = result.introduced
        expected = case["expected_sha"]
        if introduced is not None and introduced.sha.startswith(expected[:9]):
            detail = f"introduced {introduced.sha}"
            passed = True
        else:
            got = introduced.sha if introduced else "none"
            detail = f"expected {expected}, got {got} ({result.status})"
            passed = False
    elif kind == "abstention":
        result = why_symbol(engine, case["repo"], case["symbol"], rel_path=case.get("file"))
        passed = result.status == case["expect_status"]
        detail = f"status={result.status} reason={result.reason}"
    elif kind == "retrieval":
        search_result = hybrid_search(
            engine,
            embedder,
            case["repo"],
            case["query"],
            top_n=case["top_k"],
            reranker=reranker,
        )
        hit_shas = [hit.sha for hit in search_result.hits]
        matched = next(
            (
                exp
                for exp in case["expected_shas"]
                if any(sha.startswith(exp[:9]) for sha in hit_shas)
            ),
            None,
        )
        rank = (
            next(i for i, sha in enumerate(hit_shas, 1) if sha.startswith(matched[:9]))
            if matched
            else None
        )
        passed = matched is not None
        detail = (
            f"matched {matched} at rank {rank}"
            if passed
            else f"no match in top {case['top_k']}: {hit_shas[:5]}"
        )
    elif kind == "known_gap":
        search_result = hybrid_search(
            engine,
            embedder,
            case["repo"],
            case["query"],
            top_n=case["top_k"],
            reranker=reranker,
        )
        hit_shas = [hit.sha for hit in search_result.hits]
        surfaced = any(
            any(sha.startswith(exp[:9]) for sha in hit_shas) for exp in case["expected_shas"]
        )
        passed = True
        note = case.get("note", "")
        state = "expected commit surfaced anyway" if surfaced else "truth absent from corpus"
        detail = f"gap confirmed ({state}); {note}"
    elif kind == "synthesis":
        from archaeology.routes.synthesis import synthesize_why

        synth = synthesize_why(
            engine,
            case["repo"],
            case["symbol"],
            file=case.get("file"),
            model=case.get("model"),
        )
        expect = case.get("expect", "answer")
        if expect == "abstain":
            passed = synth.status == "abstained"
            detail = f"status={synth.status} reason={(synth.abstained_reason or '')[:80]}"
        else:
            if synth.status != "answered":
                passed = False
                detail = (
                    f"expected answer, got {synth.status}: {(synth.abstained_reason or '')[:80]}"
                )
            else:
                expected_citations = case.get("expected_citations", [])
                missing = [
                    exp
                    for exp in expected_citations
                    if not any(c.startswith(exp[:9]) for c in synth.citations)
                ]
                passed = not missing
                detail = f"cited {','.join(synth.citations)[:90]}" + (
                    f" | MISSING {missing}" if missing else ""
                )
    else:
        raise ValueError(f"unknown kind {kind!r}")

    return CaseResult(
        id=case["id"],
        path=path,
        kind=kind,
        passed=passed,
        detail=detail,
        latency_s=time.monotonic() - started,
    )


def run_eval(
    cases_path: str | Path,
    database_url: str | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> Report:
    engine = create_engine(database_url or DATABASE_URL)
    embedder = embedder or Embedder()
    reranker = reranker or Reranker()
    report = Report()
    with open(cases_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            case = json.loads(line)
            report.add(_run_case(case, engine, embedder, reranker))
    return report


if __name__ == "__main__":
    import sys

    cases = sys.argv[1] if len(sys.argv) > 1 else "evals/cases-v1.jsonl"
    rep = run_eval(cases)
    print(rep.to_markdown(f"Eval report - {cases}"))
