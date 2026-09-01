# Codebase Archaeology — Build Writeup

Answers "why does this code exist?" from git history, PR discussions, and linked
issues — every claim cited to a commit or comment, and every *tool claim* in this
document traceable to a file in `evals/reports/` or a test in this repo.
Architecture lives in [`DESIGN.md`](../DESIGN.md); glossary in
[`CONTEXT.md`](../CONTEXT.md). This document covers what was built, what broke,
which tradeoffs were made under uncertainty, and the measured numbers.

---

## 1. What exists

The full pipeline, both query paths, four surfaces, and a measurement harness:

```
                    ┌─ tier-1 git graph (pygit2, idempotent, rename-tracked)
repo ──ingest───────┼─ tier-2 GitHub GraphQL PRs + discussions (checkpointed,
                    │   rate-limit aware, resumable cursors)
                    └─ significance: floor (language-blind) ⊕ AST layer (JS/TSX)
                                    features cached → labels derived as pure fn

Path A (symbol):  tree-sitter resolve → git log -L walk (cached) → DB hydrate
                  → floor filter → abstention gate → cited timeline → synthesis*
Path B (question): chunk (4 source types) → local embeddings → HNSW dense ⊕
                  tsvector sparse → RRF fuse → cross-encoder rerank → liveness

*synthesis = OpenRouter client; must emit INSUFFICIENT_EVIDENCE rather than
guess; every prompt/response traced to the `traces` table.

Surfaces: CLI · FastAPI REST · MCP server · Next.js web UI
Repos indexed during the build: facebook/react (21,649 commits, 13,048 PRs),
reactjs/rfcs, pallets/click (unseen-repo E2E).
```

Everything except synthesis runs locally and keyless. Embeddings:
`BAAI/bge-small-en-v1.5` pinned per chunk; reranker `bge-reranker-base`
(chosen by measurement, §4).

## 2. The results board

Final harness run (`evals/cases-v1.jsonl`, 39 cases, two repos):

| Axis | Score | Note |
|---|---|---|
| Attribution accuracy | **11/11** | introducing commits match a hand-dug study |
| Abstention correctness | 2/2 | incl. cross-repo no-code case |
| Retrieval recall@k | **17/17** | react + rfcs corpora |
| Known-gap detection | 2/2 | verified-absent knowledge |
| Synthesis citation accuracy | 5/5 measured (+6 ready) | deterministic sha check |

Supporting measurements:

- Cold-start on an unseen repo (`pallets/click`): clone → ingest → classify →
  1,063 PRs → embed 4,033 chunks → answerable in **~2.5 minutes**; second runs
  skip instantly.
- Abstention cost cut **9.1s → 0.85s** by refusing to parse files that cannot
  contain the symbol (substring guard).
- Significance yield on react: floor alone flags 3.6%; the JS/TSX AST layer
  adds 203 format-only commits (4.5% total) while deliberately passing
  type-annotation churn that could be semantic.
- Corpus: 18,295 → 54,691 chunks across three source generations, re-embedded
  incrementally without touching git or cached lineage walks.

## 3. What broke (and what each break taught)

These are ordered by how much they changed the design. Every one is real;
several are documented against themselves in `evals/reports/`.

1. **Blobless clones make `git log -L` network-bound.** The hand-dig timed out
   at >5 minutes per function; a full clone runs the same walk in <1s. The
   finding was written into the dig notes — and then reproduced *exactly* on
   the second repository weeks later. Prediction confirmed is worth more than
   a fix applied silently.
2. **My own report contained invented rationale.** Milestone 7's report claimed
   a PR carried "11.7KB of lanes rationale." I had measured chunk length and
   never read content. Later verification showed zero mentions of "lane" — the
   discussion was devtools debugging. The correction is a permanent part of
   the record (`report-2026-08-26.md`, Addendum 2). A tool built to prevent
   invented rationale caught its author doing it; the eval's known_gap
   machinery now carries VERIFIED ABSENT evidence instead of assumptions.
3. **A live LLM refused my evidence bundle — correctly.** Synthesis abstained
   on createRoot because the bundle contained subjects but no bodies: a broken
   conditional dropped bodies whenever a timeline exceeded 20 commits. The
   mechanical-honesty protocol (INSUFFICIENT_EVIDENCE ⇒ abstain) worked before
   I knew the pipeline underneath it was wrong.
4. **The wrong-language E2E caught hallucinated anchors.** On pallets/click,
   the JS regex fallback matched Python's `class Command(` and traced it to
   "Initial commit 2014" — precisely the invented-attribution failure this
   project exists to prevent, in my own tool. Resolver now gates to supported
   languages; unvalidated ones get discussion-only behavior per the glossary,
   enforced by a regression test.
5. **Retrieval was quietly AND-semantics.** `websearch_to_tsquery` treats
   spaces as `&`, so questions containing the word "why" matched almost
   nothing. Fixed by OR-token joins; two failing cases went to rank 1.
6. **The corpus silently excluded subject-only commits.** "New context API
   (#11818)" — the single best citation for its own question — never got
   embedded because its body was short. PR-referencing subjects are now always
   included; incremental embedding recovered them without a re-index.
7. **Small sharp edges**, each caught by tests or smoke runs rather than users:
   pygit2 1.20 API drift (`update_all` removed, integer object types,
   `DiffFile.id`), the `mcp` dependency silently failing to install while a
   mypy override masked it, MCP SDK v2 renaming `FastMCP`, slashed repo names
   404-ing on Starlette routes, per-engine in-memory SQLite isolating tests
   from the app, an env-var-keyed eval crashing when the OpenRouter key hit
   its credit ceiling mid-session (now degrades to skipped cases).

## 4. Tradeoffs made under uncertainty

**Recall-biased significance.** Over-filtering deletes the introducing commit
and attribution dies; under-filtering merely costs synthesis tokens. So the
floor is high-precision, the AST layer upgrades only provably-format-only
diffs, and flow-bump churn *survives by design* — annotation changes can be
semantic. Measured consequence: 4.5% filtered instead of a hoped ~9%. That gap
is documented as a deliberate conservative choice, not a miss.

**Features cached, labels derived.** Commit features land in their own table;
labels are a pure function over them. When the contested definition of
"significant" evolved (it started the project flagged *Contested* in the
glossary), relabeling 21,649 commits took seconds and no re-walk — and the
cached lineage walks upgraded automatically. This split paid for itself the
first time it was used.

**Chunk on thread boundaries, then sub-chunk long threads.** §6's rule stands,
but 16KB discussions produced diluted embeddings *and* fell outside the
cross-encoder's 512-token window. Comment-aligned bins (≤1600 chars) fixed the
truncation half; the dilution half turned out to matter less than whether the
underlying text contained rationale at all (see §3.2).

**Postgres for everything, including vectors.** Dense top-k, lexical top-k,
joins back to commits/files/liveness, and the job queue live in one engine;
no round-trips to a separate vector store. At 54k chunks HNSW latency is
single-digit milliseconds; the tradeoff gets revisited only if recall demands
outgrow it.

**Reranker chosen by experiment, not reputation.** ms-marco-MiniLM (the
default choice everywhere) scored probe targets [1, 1, 18]; family-matched
bge-reranker-base scored [1, 2, 12]. The doc's "match the family" guidance won
on evidence. Model identity is pinned and env-overridable so the next A/B is
one flag.

**Mechanical honesty at the synthesis boundary.** The model must emit
INSUFFICIENT_EVIDENCE rather than guess; upstream gates (unresolved symbol,
no significant history, single uncited commit) short-circuit before any token
is spent. Citation checking stays deterministic (string comparison against
hand-dug truth) — necessary-but-not-sufficient for quality, and recorded as
such rather than dressed up as a faithfulness metric.

**Solo-scale contracts.** Provenance is a convention (`.sha`/`.source_id`
fields plus one SHA-resolution test), tracing is one 20-line helper, index
status is a response footer. The goals survived; the ceremony didn't.

## 5. Honest limitations

- **First-stage recall ceilings.** The lanes rationale is unreachable not
  because ranking fails but because the text does not exist in any GitHub
  corpus — verified three independent ways. It lives in blog posts and talks.
  Closing such gaps needs external-corpus support, not better ranking.
- **Cross-file lineage stops at extraction commits.** `throwException`'s true
  origin sits one rename/extraction behind what `git log -L` reports.
  Labelled honestly today; properly solved by following def-site moves.
- **512-token truncation** still penalizes long *unsplit* documents in
  reranking; summarization-augmented chunks are the candidate fix.
- **Incremental updates assume append history.** Force-push repair (§9's hard
  problem) is unimplemented; re-index from scratch is the current answer.
- **Citation presence ≠ faithfulness.** An LLM-judged pass over bundles is the
  obvious next eval axis.
- **Case 40** is deliberately unwritten; it belongs to the "how I'd grow this"
  conversation, not to a script.

## 6. Reproducing everything

```sh
uv sync && docker compose up -d db && uv run alembic upgrade head

# any GitHub repo, cold:
./scripts/e2e.sh pallets/click src/click/core.py Command

# surfaces
uv run python -m archaeology.api.main --port 8000     # REST
uv run python -m archaeology.mcp.server               # MCP (stdio)
cd web && npm run dev                                 # web UI

# measurement
export OPENROUTER_API_KEY=...        # optional; synthesis axis skips without it
uv run python -m archaeology.evaluation.harness evals/cases-v1.jsonl
```

Test suite: 49 green under ruff + mypy `strict`; CI mirrors the same gates.

## 6. Addendum — the live phase (M18–21)

The four milestones after this document's first draft were driven by actually
using the tool, and they produced the most instructive findings of the build:

**The model caught my pipeline bugs twice more.** Switching synthesis to
`stealth/ox-alpha` (owner choice; Sonnet 5 remains the measured reference),
the model responded to a thin-looking bundle with an INSUFFICIENT_EVIDENCE
that was precisely correct: binned discussions were losing 11 of 12 bodies to
a `source_id[:9]` truncation collision, so the bundle really did contain
titles only. A second abstention correctly identified that the removal-PRs
never argued rationale — the why lives in RFC 0214, in the *other* repo.
Both were pipeline defects my evals had not caught, surfaced by the honesty
protocol doing its job.

**Cross-repo synthesis required per-repo retrieval, not a bigger pool.**
Naively widening the dense/sparse candidate pool to the union of all repos
diluted per-corpus recall — RFC 0214 ranked first *within* reactjs/rfcs yet
never reached the reranker from the 59k-chunk union. The fix: retrieve per
repo, then merge candidates and rerank once across the combined pool. Each
corpus contributes its best before the cross-encoder arbitrates.

**A browser-only failure class.** The UI worked in every curl smoke test and
failed for every human: FastAPI had no CORS middleware, and curl bypasses
CORS by construction. Fixed, and the lesson recorded: smoke-test the client
surface the client actually uses.

**The router gap.** The UI's Explain button called Path A regardless of input
shape — because Path B synthesis did not exist. `answer_any` now routes
symbol-shaped queries to Path A and prose to Path B (searching every indexed
repo), completing the "merge at synthesis" design.

**Free-tier mechanics, handled mechanically.** Paid models 402 on a free-tier
key; free models throttled or hung; empty generations arrived as blank 200s.
The system's answer is uniform: visible abstention reasons, one retry on
429/empty, bounded timeouts, and errors surfaced as messages — no blank
boxes, no invented prose.

## 7. Milestone ledger

Scaffold+dig (M0) · tier-1 ingest+floor (1) · Path A (2) · AST layer (3) ·
hybrid retrieval (4) · eval harness v1, first numbers (5) · REST+MCP (6) ·
tier-2 PRs, 54k-chunk corpus corrections (7) · rerank (8) · sub-chunking +
self-correction (9) · OpenRouter synthesis (10) · web UI (11) · live cited
answers + enrichment (12) · synthesis axis, all axes measured (13) · second
repo, gaps resolved-or-verified (14) · 39-case board (15) · unseen-repo E2E
(16) · this document (17) · synthesis model A/B, model catches bugs again
(18) · web surfaces live; CORS + router fixes (19) · cross-repo synthesis
+ per-repo merge (20) · UI overhaul: markdown answers, provenance badges,
evidence-first rendering (21).
