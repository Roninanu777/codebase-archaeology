from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from archaeology.llm.client import chat_completion, synthesis_model
from archaeology.llm.tracing import trace_call
from archaeology.routes.path_a import PathAResult, why_symbol

MAX_EVIDENCE_COMMITS = 14
MAX_BODY_CHARS = 400
MAX_BUNDLE_CHARS = 9_000
MAX_DISCUSSION_SNIPPETS = 3
SNIPPET_CHARS = 700

MAX_QUESTION_HITS = 8
MAX_HIT_BODY_CHARS = 500

_SYMBOL_RE = re.compile(r"^[\w$]+(\.\w+)?$")


def looks_like_symbol(query: str) -> bool:
    return bool(_SYMBOL_RE.match(query.strip())) and len(query.strip()) > 1


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
        if body:
            trimmed = body[:MAX_BODY_CHARS]
            if len(body) > MAX_BODY_CHARS:
                trimmed += "..."
            for body_line in trimmed.splitlines():
                if body_line.strip():
                    lines.append(f"    {body_line.strip()}")
        lines.append("")
    bundle = "\n".join(lines)
    return bundle[:MAX_BUNDLE_CHARS]


def _pr_discussion_snippets(
    session: Any, repo_name: str, timeline: list[Any]
) -> list[tuple[str, str]]:
    from sqlalchemy import select

    from archaeology.storage.models import CommitPrLink, DiscussionChunk, Repo

    sha_prefixes = [ev.sha for ev in timeline if not ev.sha.startswith("pr:")]
    if not sha_prefixes:
        return []

    repo_row = session.scalars(select(Repo).where(Repo.name == repo_name)).first()
    if repo_row is None:
        return []
    conditions = [
        (CommitPrLink.repo_id == int(repo_row.id)) & (CommitPrLink.sha.like(f"{prefix}%"))
        for prefix in sha_prefixes
    ]
    from sqlalchemy import or_

    links = session.execute(select(CommitPrLink.pr_number).where(or_(*conditions))).all()
    pr_numbers = sorted({int(n) for (n,) in links})
    if not pr_numbers:
        return []

    snippets: list[tuple[str, str]] = []
    for pr_number in pr_numbers[:MAX_DISCUSSION_SNIPPETS]:
        chunk = session.scalars(
            select(DiscussionChunk)
            .where(
                DiscussionChunk.repo_id == int(repo_row.id),
                DiscussionChunk.source_type == "pr_discussion",
                DiscussionChunk.source_id.like(f"pr:{pr_number}#%"),
            )
            .order_by(DiscussionChunk.source_id)
        ).first()
        if chunk is None:
            continue
        text = (chunk.body or "").strip()[:SNIPPET_CHARS]
        if text:
            snippets.append((f"PR #{pr_number}", text))
    return snippets


def render_evidence_with_discussions(engine: Any, result: PathAResult) -> tuple[str, list[str]]:
    bundle = render_evidence(result)
    with Session(engine) as session:
        snippets = _pr_discussion_snippets(session, result.repo, result.timeline)
    if not snippets:
        return bundle, []

    lines = [bundle, "", "Linked PR discussion excerpts:"]
    labels: list[str] = []
    for label, text in snippets:
        lines.append(f"[{label}]")
        lines.append(text)
        lines.append("")
        labels.append(label.lower().replace(" ", ""))
    enriched = "\n".join(lines)[: MAX_BUNDLE_CHARS + 3 * SNIPPET_CHARS]
    return enriched, labels


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
    bundle, discussion_labels = render_evidence_with_discussions(engine, result)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": bundle},
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

    if not completion.content.strip():
        return SynthesisResult(
            status="abstained",
            symbol=symbol,
            repo=repo_name,
            abstained_reason="empty_generation: model returned no content",
            model=completion.model,
        )

    citable = [ev.sha for ev in result.timeline] + [
        label for label in discussion_labels if not label.startswith("PR #")
    ]
    citations = [sha for sha in citable if f"[{sha}" in completion.content]
    return SynthesisResult(
        status="answered",
        symbol=symbol,
        repo=repo_name,
        answer=completion.content,
        citations=citations,
        model=completion.model,
    )


def render_hits_bundle(question: str, hits: list[Any], bodies: dict[str, str]) -> str:
    lines = [f"Question: {question}", "", "Evidence (ranked by relevance):"]
    for hit in hits:
        source_id = hit.sha
        date = f" {hit.authored_at}" if hit.authored_at else ""
        lines.append(f"[{source_id}]{date} {hit.title}")
        body = bodies.get(source_id, "").strip()
        if body:
            trimmed = body[:MAX_HIT_BODY_CHARS]
            if len(body) > MAX_HIT_BODY_CHARS:
                trimmed += "..."
            lines.append(f"    {trimmed}")
        lines.append("")
    return "\n".join(lines)[:MAX_BUNDLE_CHARS]


def synthesize_question(
    engine: Any,
    repo_name: str,
    question: str,
    n: int = MAX_QUESTION_HITS,
    model: str | None = None,
    poster: Any = None,
    embedder: Any = None,
    reranker: Any = None,
) -> tuple[SynthesisResult, Any]:
    from archaeology.retrieval.search import hybrid_search

    search_result = hybrid_search(engine, embedder, repo_name, question, top_n=n, reranker=reranker)

    def abstain(reason: str) -> tuple[SynthesisResult, Any]:
        return (
            SynthesisResult(
                status="abstained",
                symbol=question,
                repo=repo_name,
                abstained_reason=reason,
            ),
            search_result,
        )

    if search_result.abstained_reason == "no_hits" or not search_result.hits:
        return abstain("no_hits")

    from sqlalchemy import select

    from archaeology.storage.models import DiscussionChunk

    with Session(engine) as session:
        chunk_rows = session.scalars(
            select(DiscussionChunk).where(
                DiscussionChunk.id.in_([h.chunk_id for h in search_result.hits])
            )
        ).all()
    bodies = {str(c.source_id)[:9]: (c.body or "") for c in chunk_rows}

    chosen_model = model or synthesis_model()
    bundle = render_hits_bundle(question, search_result.hits, bodies)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": bundle},
    ]
    completion = chat_completion(messages, model=chosen_model, poster=poster)

    with Session(engine) as session:
        trace_call(
            session,
            stage="synthesis",
            model=completion.model,
            prompt=bundle,
            response=completion.content,
            latency_ms=completion.latency_ms,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        )
        session.commit()

    if completion.content.startswith("INSUFFICIENT_EVIDENCE"):
        return (
            SynthesisResult(
                status="abstained",
                symbol=question,
                repo=repo_name,
                abstained_reason=completion.content,
                model=completion.model,
            ),
            search_result,
        )

    if not completion.content.strip():
        return (
            SynthesisResult(
                status="abstained",
                symbol=question,
                repo=repo_name,
                abstained_reason="empty_generation: model returned no content",
                model=completion.model,
            ),
            search_result,
        )

    hit_ids = [h.sha for h in search_result.hits]
    citations = [sid for sid in hit_ids if f"[{sid}" in completion.content]
    return (
        SynthesisResult(
            status="answered",
            symbol=question,
            repo=repo_name,
            answer=completion.content,
            citations=citations,
            model=completion.model,
        ),
        search_result,
    )


def answer_any(
    engine: Any,
    repo_name: str,
    query: str,
    file: str | None = None,
    model: str | None = None,
    poster: Any = None,
    embedder: Any = None,
    reranker: Any = None,
) -> dict[str, Any]:
    """Router: symbol-looking queries go to Path A, prose to Path B."""
    if looks_like_symbol(query):
        result = synthesize_why(engine, repo_name, query, file=file, model=model, poster=poster)
        return {"path": "A", "synthesis": result, "evidence": None}
    result, search_result = synthesize_question(
        engine,
        repo_name,
        query,
        model=model,
        poster=poster,
        embedder=embedder,
        reranker=reranker,
    )
    return {"path": "B", "synthesis": result, "evidence": search_result}
