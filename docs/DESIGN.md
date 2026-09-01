# Codebase Archaeology

A tool that answers "why does this code exist" by reconstructing the reasoning from git history, PR discussions, and linked issues, with every claim traced back to a specific commit or comment.

Target: portfolio project for full-stack senior/staff roles. Roughly two months.

---

## 1. The pitch, and the honest objection

Point it at a repo. Ask why a function exists, or why a design decision was made. Get an answer assembled from history, with citations.

**The objection you will get in every interview: can't Claude Code already do this?**

For the common case, largely yes. Claude Code runs git log, reads files, pulls a PR through the gh CLI, and gives a good answer. A tool that only does that is a worse version of something people already have.

The gap is structural and comes from a deliberate design choice. Claude Code does not index the repo or build a vector store. It traverses the filesystem, greps, reads files, and follows references, entirely locally. Good tradeoff: no stale index, no embedding pipeline. But three things stay out of reach:

1. **Anything needing a full pass over history.** "Which subsystems changed most in two years and have no design doc" means scanning thousands of commits. That is a batch job against a precomputed table, not an agent session.
2. **Deep attribution chains.** Blame gives the last commit that touched a line, usually a rename or formatting sweep. The commit that explains the line is often several rewrites back. Walking that chain live burns enormous context.
3. **Joined PR and issue data at scale.** Fetching one PR is easy. Joining thousands of PRs to their commits and linked issues, then querying across them, is a different problem.

**The positioning that follows: build the MCP server, not a competitor.** This tool does the offline indexing Claude Code deliberately does not do, and exposes it as tools the agent calls. You handle the batch pass and the joins. The agent handles reasoning and conversation.

---

## 2. Two query paths

The router sends questions down one of two paths, sometimes both.

### Path A: symbol-anchored

For questions with a concrete anchor. "Why does this function exist."

```
Resolve symbol      Function name to line range at HEAD
      |
Lineage walk        Trace lines back through renames
      |
Significance filter Drop formatting-only commits
      |
Abstention gate     Is the evidence good enough?
      |
Synthesis           Answer with commit citations
```

Only the last stage touches a model. Everything above is deterministic, which keeps cost and latency predictable and makes each component unit testable.

### Path B: retrieval

For open-ended questions with no anchor. "Why do we use eventual consistency for notifications." "Was there ever a reason we don't cache this."

```
Hybrid retrieval    Dense plus BM25, fused ranking
      |
Liveness scoring    Does the linked code still exist?
      |
Temporal rerank     Order candidates into a timeline
      |
Contradiction check Do top candidates disagree?
      |
Synthesis           Present the arc, cite each source
```

### The router

Rules first, model second. If the question resolves to a symbol or names a file present at HEAD, use Path A. If it contains no resolvable entity, use Path B. Only ambiguous cases get a small classification call.

Log every routing decision with its outcome. Router accuracy is an eval axis, and rules-first means most decisions cost nothing.

Questions like "why does this retry loop use exponential backoff" have both an anchor and a design rationale. Run both paths, merge at synthesis.

---

## 3. The two hard problems

These are what make the project worth building. Everything else is plumbing.

### Problem 1: noise

Most commits that touch a line explain nothing. A prettier run, a license header sweep, a mass import reorder, a rename. Blame lands on those constantly.

So the core of Path A is a **layered** significance classifier. The floor is language-blind and universal: any commit touching only whitespace and comments is insignificant. On top sits an opt-in per-language AST layer — a tree-sitter diff ignoring format-only node changes — JS/TSX first. Per-commit features are cached at ingest; labels are a pure function over those features. Revising the definition is a seconds-long relabel of one table, not another walk over history, and rival definitions can be A/B'd in the eval.

Error costs are asymmetric. Dropping the commit that introduced the line kills attribution accuracy outright; letting noise through only costs synthesis tokens. So the classifier is recall-biased by design — its job is killing the obvious floor of noise, not adjudicating subtlety. Tractable enough to build, hard enough that a naive version visibly fails. Gives a clean eval axis.

### Problem 2: the answer often does not exist

Real repos are full of commits that say "fix" and PRs with empty bodies. A large fraction of "why" questions have no recorded reasoning anywhere.

A bad tool invents a plausible rationale from reading the code. A good one says the reasoning was never written down, here is what did happen, here is the closest related discussion.

Build abstention in from the start and make it a headline metric. Correctly saying "unknown" is a real result and almost nothing in this space does it.

### The RAG-specific version of problem 2: superseded decisions

Naive retrieval over history is confidently wrong about reversed decisions. A 2019 PR explains why the team chose library X. A 2023 PR quietly rips it out. Vanilla similarity search returns the 2019 discussion with high confidence and no indication it is dead.

Handling this is the actual product differentiator:

- **Liveness scoring.** Boost candidates whose linked code still exists at HEAD. If every file a discussion touched has been deleted, that is a strong staleness signal available for free from data already in the tables.
- **Contradiction detection.** Two retrieved chunks disagreeing about the same subsystem is a finding, not noise.
- **Present the arc.** "Decided in 2019, revisited in 2021, reversed in 2023" beats any single chunk.

Nobody else does this. It only works because the commit graph sits next to the vector index.

---

## 4. Architecture

### Surfaces

Two clients, one core:

- **Web app** for the demo and shareable links
- **MCP server** exposing `index_repo`, `why_does_this_exist`, `history_of_symbol`, `search_decisions`

The MCP server is a thin adapter over the same HTTP API, not a parallel implementation. Should be under 200 lines.

### Ingest, in tiers

**Tier 1: git-derived, fast.** Blobless clone (`--filter=blob:none`), walk the commit graph, write commits, parents, and file changes with rename tracking. Parse HEAD with tree-sitter for symbol boundaries. Repo becomes answerable in about a minute.

Treeless (`--filter=tree:0`) is faster but makes tree traversal network-bound, which you do constantly. Blobless is the right default. Shallow clones are useless since history is the point.

**Tier 2: platform-derived, slow.** PRs, review comments, linked issues via GitHub GraphQL. Rate-limit aware, checkpointed. Runs for hours in the background.

This means the query path must answer against a partially built index and label what is missing. That is the design, not a wart.

**Tier 3: significance classification.** Offline, cached per commit. Computed once, reused by every query forever.

**Tier 4: chunking and embedding.** See section 6.

### Storage

- **Postgres** for the graph, metadata, full text search, pgvector, and the job queue
- **Object storage (R2)** for the bare git cache and checkpoint state

Core tables:

```
repos
commits
commit_parents
file_changes          (with rename from/to)
symbols
pull_requests
issues
commit_pr_links
commit_significance
lineage_cache
discussion_chunks
jobs
traces
```

### Jobs

Postgres as the queue rather than adding a broker. `SELECT ... FOR UPDATE SKIP LOCKED` gives a solid worker queue in about a hundred lines.

The argument if challenged: enqueueing a job and writing its parent row happen in one transaction. With a separate broker you get to invent your own outbox pattern to avoid orphaned jobs. Fewer services and stronger guarantees is not a tradeoff.

Dedupe by repo plus head SHA so concurrent requests attach to one job. Workers idempotent, checkpointed per stage.

---

## 5. Path A detail

**Resolve symbol.** Tree-sitter index maps a function name to a line range at HEAD.

**Lineage walk.** `git log -L <start>,<end>:<file> --follow` gives candidate commits. Expensive. Cache by (repo, file, symbol, head SHA).

Lazy, not precomputed. Precomputing every line is lines times history, which does not finish.

**Significance filter.** Applied from the cached per-commit classification.

**Rank.** The introducing commit matters most, plus any commit with substantial linked discussion.

**Abstention gate.** A cheap deterministic check on evidence quality runs before synthesis, so questions with no recorded answer never reach a model call. Saves money and makes honesty the default path rather than something you prompt for.

**Synthesis.** Hard token budget on the evidence bundle. Cite commit SHAs.

---

## 6. Path B detail

### Chunking

Sources: commit message bodies (not just subjects, the body is where reasoning hides), PR titles and descriptions, review threads grouped by thread root, issues with comments, markdown design docs in the repo.

**Chunk on thread boundaries, never token count.** A PR discussion is a coherent argumentative unit: someone proposes, someone objects, they resolve. Split that at 512 tokens and you retrieve half an argument. If a thread is genuinely oversized, split at a comment boundary, never mid-comment.

**Filter bots aggressively.** Dependabot, CI status, coverage bots, auto-generated changelogs. On a mature repo this is often a third or more of all comments and it is pure retrieval poison.

**Enrich before embedding.** Prepend a short synthetic header with date, subsystem paths touched, and linked commit subjects. Retrieval quality improves noticeably because the embedding carries structural context the raw prose does not.

### Schema

```sql
discussion_chunks(
  id, repo_id, source_type, source_id, thread_id,
  authored_at, body, embedding, tsv,
  files_touched[], linked_commits[], liveness_score
)
```

### Why pgvector, not a dedicated vector store

Every stage after retrieval joins chunks back to commits, file changes, and HEAD state. A separate vector store means retrieve, round-trip to Postgres to enrich, then filter, and you lose the ability to push predicates into the query. With pgvector you filter by repo, date range, and liveness in one statement. HNSW index. At this scale the performance argument for a dedicated store does not apply.

### Retrieval mechanics

**Hybrid.** Dense top 50 and BM25 top 50, fused with reciprocal rank fusion, cut to 20.

Vocabulary mismatch is the whole reason for embeddings (user says "retry logic", PR author wrote "backoff"). But exact matching on identifiers, error codes, and library names still matters enormously and dense retrieval is bad at those.

**Rerank.** Cross-encoder between fusion and liveness scoring. Take fused top 50, rerank, keep 20. Cross-encoders substantially outperform bi-encoder similarity on relevance and are small enough to run locally.

**Liveness.** For each chunk, what fraction of `files_touched` still exists at HEAD, and are `linked_commits` still ancestors of HEAD. Compute once per chunk per head SHA. Nearly free, and this single number kills most of the confidently-stale-answer problem before any model sees it.

**Temporal rerank.** Group survivors by overlapping paths, sort by date, keep the endpoints: the earliest chunk that decided something and the latest that touched the same paths. The middle of a long argument is usually least informative.

**Contradiction detection.** Heuristic first, not a model call. If a later chunk's commits deleted files an earlier chunk's commits added, that is a reversal, detectable from existing tables. Escalate to a model only when ambiguous.

**Synthesis.** Emit a timeline, not a paragraph. Every claim carries a source id. If liveness is low across all candidates, abstain and say the discussion found is about code that no longer exists.

---

## 7. Models

Most of the pipeline uses no model at all. That is the point. Four call sites need one.

| Stage | Model | Why |
|---|---|---|
| Significance classifier | **None** | Layered: universal whitespace/comment floor plus an opt-in tree-sitter AST layer per language (JS/TSX first). Features cached per commit at ingest; labels derived as a pure function over them. Deterministic, instant, free, testable, recall-biased by design. A model here would be slower, pricier, less consistent. |
| Router | Haiku 4.5 | Rare ambiguous cases only. Three-way classification, structured output. If you want something bigger, your rules are wrong. |
| Contradiction check | Haiku 4.5 | Escalation only. One boolean plus a reason. |
| Synthesis | Sonnet 5 default, Opus 5 behind a flag | Genuinely hard: read evidence, build a timeline, cite SHAs, abstain when thin. Weak models fabricate rationale here, the exact failure this project exists to prevent. |

Run the eval with both synthesis models. If Opus does not move the numbers, ship Sonnet and put that in the writeup. "I measured and the cheaper model sufficed" is a stronger signal than defaulting to the biggest thing available.

### Embeddings and reranking: local

Use `sentence-transformers` with the MPS backend on the M3 Pro. Load a model, call `.encode()` on batches, write vectors to Postgres. No server, no GUI, about fifteen lines.

Embedding models are a few hundred megabytes, not tens of gigabytes, so chip generation barely matters. Batch-embedding 100,000 short chunks is about an hour, unattended. The cross-encoder only ever sees 50 candidates at query time.

Pick from the BGE, E5, or GTE families at small or base size. Check the current MTEB leaderboard before committing. Two things matter more than which one: use a **general text** embedding model, not a code-specific one (you are embedding prose about code), and match the reranker to the same family where possible.

**Pin the model version and record it alongside eval numbers.** Swapping embedding models invalidates the entire index.

Do not plan on running a generative model locally.

### Eval judge

Different family than the generator, to avoid self-preference bias. Better still, make most of the eval deterministic. "Did it cite the correct commit SHA" is a string comparison, not a judgment call. Reserve model grading for parts that genuinely need it.

### Cost note

A repo with 30,000 PRs produces maybe 100,000 chunks. Embed tier-two data lazily, only for repos someone actually queries, and batch aggressively.

---

## 8. Tech stack

**Backend: Python, FastAPI.** Not a real choice. Tree-sitter bindings, sentence-transformers, and git tooling all live in Python. Splitting languages for a nicer API layer costs a week and buys nothing.

**Git access:** pygit2 for the commit graph walk. Subprocess overhead per commit is brutal at 50,000 commits. But shell out to `git log -L` for the lineage walk specifically, since libgit2's line-history support is weak. Mixing the two deliberately is worth a paragraph in the writeup.

**Postgres for everything.** Graph, FTS, pgvector, job queue.

**Workers as a separate process, same image.** Web stays responsive, worker does the multi-hour indexing.

**Frontend: Next.js on Vercel.** Four screens: repo input, job progress, question box, timeline output with citations. Do not build a dashboard. Spend frontend time on output rendering, because a well-designed timeline with inline commit links is what makes the demo land.

**Hosting:** Fly.io for API and workers (persistent volumes for the git clone cache, process groups so web and worker run from one image). Postgres from Supabase or Neon, both support pgvector. Cloudflare R2 for the bare repo cache, no egress fees. Under thirty dollars a month total.

**Observability:** a `traces` table from day one. Every model call: prompt, response, model, tokens, latency, eval case id. The project's whole thesis is measurement, so having your own trace store is on-brand and queryable with SQL. Add Langfuse later if you want a UI. Do not start there.

**Eval harness: pytest plus a JSONL file.** Labeled cases in JSONL, a script that runs them and emits a markdown report. Do not adopt an eval framework. The harness is fifty lines and you want full control over the metrics.

**Testing the lineage walker:** generate small synthetic git repos in fixtures with history you constructed yourself. Deterministic, fast, and it catches rename-tracking bugs that real repos hide.

---

## 9. On-demand indexing

The hard milestone. Turns a data project into a distributed systems project, which is exactly why it is the better interview story, and exactly why it goes last.

**Cold start.** Full history for a large repo is gigabytes. Blobless clone pulls the commit graph fast and fetches file contents lazily.

**GitHub API limits.** PR bodies, review comments, and issue links are not in git. Authenticated REST caps around 5,000 requests an hour (verify current numbers). A repo with 30,000 PRs at one request each is a full day. Use GraphQL with 100-node pages, request only needed fields. This constraint shapes the architecture more than anything else.

**Partial answerability.** Follows directly from the two-tier design. Answer against a partially built index, label what is missing.

**Lineage cannot be precomputed.** Lazy per query, cached. Changes the latency story and the cache design.

**Unbounded work per request.** Nothing stops someone pasting the Linux kernel. Size estimation before accepting a job, hard caps, queue with fair scheduling, dedupe so two requests for the same repo attach to one job.

**Checkpointing.** A forty minute job that dies at 90% must resume, not restart. Sounds boring, will cost a weekend.

**Incremental updates and force pushes.** Reindexing from the last known SHA is easy until someone rebases and the append-only assumption breaks. Detecting divergence and repairing only affected ranges is subtle.

**Storage and eviction.** Per-repo indexes add up. LRU policy, plus confidence that anything evicted can be rebuilt.

**Untrusted repos.** Cloning arbitrary code. Disable git filters and hooks, sandbox the worker, cap file sizes, watch for symlink escapes. And the one people miss: repo contents flow into model prompts, so a repo can contain text aimed at the agent. Handle deliberately.

### The embedding gap

The embedding model runs on the laptop, so the server cannot embed new chunks for on-demand repos.

Three options:

1. Ship on-demand for Path A only, keep Path B to pre-indexed repos. Honest, clearly documented.
2. Run the embedding model in the Fly worker. Costs more, slower on CPU, closes the loop.
3. Embedding API for on-demand traffic, local embedding for bulk backfill.

Take option 1 for the initial launch and write up why. A documented limitation with a clear reason reads as judgment. An undocumented one reads as an oversight.

---

## 10. Eval plan

Roughly forty questions where you dug through history yourself and know the true answer.

Axes:

- **Attribution accuracy.** Did it name the right commit? Deterministic string check.
- **Abstention correctness.** Did it say unknown when the reasoning was never recorded?
- **Router accuracy.** Right path for the question?
- **Retrieval recall@20** on the labeled set.
- **Staleness detection.** On questions where a decision was later reversed, does the output surface the reversal? Build twenty of these cases deliberately.
- **Latency.**

That last axis is the headline of the writeup. Nobody else measures it.

---

## 11. Scope

**Cut ruthlessly.** One language. GitHub only. Public repos only. No auth, no teams, no settings, no dashboard.

**Seed: facebook/react.** First symbol-anchored language is JS/TSX (tree-sitter-typescript). React's deepest rationale often lives in the external `reactjs/rfcs` repo — out of crawl scope for v1; chunks cite `reactjs/rfcs#N` through existing link tables only.

Pre-index three or four well-known repos so anyone can try it instantly with zero setup.

### Milestones

| Weeks | Work |
|---|---|
| 1-2 | Ingest tier 1, schema, significance classifier, eval set built by hand |
| 3-4 | Path A end to end, abstention gate, web UI, deployed against pre-indexed repos |
| 5-6 | Tier 2 backfill, chunking, embeddings, Path B, router |
| 7 | MCP server, eval harness, run the numbers |
| 8 | On-demand indexing as far as it gets, writeup |

### The deliverable that matters most

Not the repo. A writeup covering what you tried, what broke, the specific tradeoffs made under uncertainty, and the eval numbers before and after. That is what a staff interviewer actually reads, and almost nobody writes it.

---

## 12. Next step

Before any architecture: pick one repo you know, pick ten functions, and dig through the history by hand to find the real answer for each. An afternoon of tedious work.

That is the eval set, and it tells you within a day whether the significance classifier idea holds up on real commits or falls apart. Cheaper to find out now than in week six.

### Open decisions

- Significance classifier feature set (nail this before writing code, the eval numbers live or die on it)
- Which repo and language to target first
- Exact embedding and reranker models, after checking the current leaderboard
