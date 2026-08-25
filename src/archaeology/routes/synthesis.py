from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from archaeology.llm.client import chat_completion, synthesis_model
from archaeology.llm.tracing import trace_call
from archaeology.routes.path_a import PathAResult, why_symbol

MAX_EVIDENCE_COMMITS = 20
MAX_BODY_CHARS = 400
MAX_BUNDLE_CHARS = 7_000

SYSTEM_PROMPT = """You answer "why does this code exist" questions using ONLY the supplied evidence.

Rules:
- Cite evidence with its short sha in brackets like [b8f825877] at every factual claim.
- Present the arc chronologically when decisions changed over time.
- If the evidence does not contain the reasoning, reply with exactly one line:
  INSUFFICIENT_EVIDENCE: <what is missing>
- Never invent rationale. Never use knowledge outside the evidence bundle."""


@dataclass(slots=True)
class SynthesisResult:
    status: str
    symbol: str
    repo: str
    answer: str | None = None
    abstained_reason: str | None = None
    citations: list[str] = field(default_factory=list)
    model: str | None = None


def render_evidence(result: PathAResult) -> str:
    lines: list[str] = [
        f"Question: why does {result.symbol} exist?",
        f"Anchor: {result.rel_path}:{result.span.start_line}-{result.span.end_line}"
        if result.span
        else "Anchor: unresolved",
        "",
        "Evidence (chronological):",
    ]
    for ev in result.timeline[:MAX_EVIDENCE_COMMITS]:
        prs = f" (PR #{', #'.join(str(p) for p in ev.pr_refs)})" if ev.pr_refs else ""
        date = f" {ev.committed_at}" if ev.committed_at else ""
        lines.append(f"[{ev.sha}]{date} {ev.author or 'unknown'}{prs}: {ev.subject}")
        body = (ev.body or "").strip()
        if body and len(result.timeline) <= MAX_EVIDENCE_COMMITS:
            trimmed = body[:MAX_BODY_CHARS]
            if len(body) > MAX_BODY_CHARS:
                trimmed += "..."
            for body_line in trimmed.splitlines():
                if body_line.strip():
                    lines.append(f"    {body_line.strip()}")
        lines.append("")
    bundle = "\n".join(lines)
    return bundle[:MAX_BUNDLE_CHARS]


def synthesize_why(
    engine: Any,
    repo_name: str,
    symbol: str,
    file: str | None = None,
    model: str | None = None,
    poster: Any = None,
) -> SynthesisResult:
    result = why_symbol(engine, repo_name, symbol, rel_path=file)

    if result.status != "answered":
        return SynthesisResult(
            status=result.status,
            symbol=symbol,
            repo=repo_name,
            abstained_reason=result.reason,
        )

    chosen_model = model or synthesis_model()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": render_evidence(result)},
    ]
    completion = chat_completion(messages, model=chosen_model, poster=poster)

    with Session(engine) as session:
        trace_call(
            session,
            stage="synthesis",
            model=completion.model,
            prompt=messages[1]["content"],
            response=completion.content,
            latency_ms=completion.latency_ms,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        )
        session.commit()

    if completion.content.startswith("INSUFFICIENT_EVIDENCE"):
        return SynthesisResult(
            status="abstained",
            symbol=symbol,
            repo=repo_name,
            abstained_reason=completion.content,
            model=completion.model,
        )

    citations = [ev.sha for ev in result.timeline if f"[{ev.sha}" in completion.content]
    return SynthesisResult(
        status="answered",
        symbol=symbol,
        repo=repo_name,
        answer=completion.content,
        citations=citations,
        model=completion.model,
    )
