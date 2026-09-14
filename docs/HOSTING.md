# Hosting Spec — $0/month deployment

Status: proposed · Owner: maintainer · Scope: put the query surface on a public
URL for free, without changing the local-first indexing model.

## 1. Goal and non-goals

**Goal.** A public URL where anyone can Trace (Path A/B retrieval + timelines)
and, with a shared token, Explain (LLM synthesis) and add public repos —
running entirely on free tiers.

**Non-goals.** Multi-tenant auth, uptime guarantees, on-demand indexing of
arbitrary repos at scale (DESIGN §9), sandboxed execution of untrusted repo
content, custom domains, paid hosting.

## 2. Architecture

```
            ┌──────────────────────── Cloudflare Pages (free) ───────────┐
            │ Next.js static export (`web/out`), NEXT_PUBLIC_API_BASE    │
            └──────────────────────────────┬─────────────────────────────┘
                                           │ HTTPS + CORS
            ┌──────────────────────────────▼─────────────────────────────┐
            │ Modal (free $30/mo compute, scale-to-zero, ASGI)            │
            │  uvicorn: FastAPI + MCP streamable-http at /mcp            │
            │  boot: alembic upgrade → background re-clone repos         │
            │  image: models baked in (bge-small + bge-reranker-base)    │
            │  disk: ephemeral — clones re-fetched on every cold start   │
            └──────────────────────────────┬─────────────────────────────┘
                                           │ psycopg (pooler, TLS)
            ┌──────────────────────────────▼─────────────────────────────┐
            │ Supabase Postgres 16 + pgvector (free, 500 MB)             │
            │  slim query-snapshot: chunks, commits, significance,       │
            │  PR links, lineage cache, traces, jobs                     │
            └────────────────────────────────────────────────────────────┘

 Indexing stays local: `scripts/e2e.sh` / `index-remote` write into the
 Supabase DATABASE_URL from the developer machine. The Space only serves
 queries. (Hosted add-repo still works — see §7.4 — just slowly on CPU.)
```

| Component | Platform | Free limit we rely on |
|---|---|---|
| API + MCP | **Modal** (Dockerfile-based image, ASGI app) | $30/mo included compute, scale-to-zero, volumes |
| Web | Cloudflare Pages (static export) | unlimited requests/bandwidth |
| DB | Supabase free | 500 MB storage, 5 GB egress/mo |
| LLM | OpenRouter (deepseek-v4-flash) | pay-per-token, ~$0.0002/answer |
| Keepalive | GitHub Actions cron (public repo) | unlimited minutes |

## 3. Measured baseline (why slimming is mandatory)

Local DB today — **1,289 MB across 6 repos, 144,847 chunks** — is 2.6× the
Supabase free cap. `oven-sh/bun` (57,031 chunks) was added via the UI during
testing; the curated set (react, rfcs, click, sqlite-utils, yt-dlp) is 87,816
chunks.

| Relation | Size now | Query-time need |
|---|---|---|
| `discussion_chunks` | 979 MB | **required** (body 90, tsv 125, embedding 213, files\_touched 31, HNSW 283, GIN 70, misc 24) |
| `file_changes` | 147 MB | no — used only by chunker/liveness at embed time |
| `pull_requests` | 59 MB | no — chunker only; synthesis reads discussion chunks |
| `commits` (+parents) | 41 MB | **required** (hydration, PR refs) |
| `commit_features` | ~20 MB | no — features are an input to labels |
| `commit_significance` | ~11 MB | **required** (Path A filter) |
| `commit_pr_links` | ~3 MB | **required** (Path A discussion enrichment) |
| `lineage_cache`, `jobs`, `traces` | small | **required** |

## 4. Storage budget and slimming plan

Lever table (measured savings, curated 5-repo set):

| Lever | Action | Saves |
|---|---|---|
| Exclude `oven-sh/bun` + `t/js` rows | DELETE rows (+VACUUM FULL) | ~400 MB |
| Drop embeddings to `halfvec(384)` | `ALTER … USING embedding::halfvec(384)`; rebuild HNSW with `halfvec_cosine_ops` | ~50 MB col + ~140 MB index |
| Replace `tsv` column with expression index | `DROP COLUMN tsv`; GIN on `to_tsvector('english', coalesce(title,'')‖' '‖body)` | ~76 MB column |
| Delete `file_changes` rows (keep schema) | `DELETE FROM file_changes` | ~90 MB |
| Delete `commit_features`, `pull_requests` rows (keep schema) | DELETE | ~45 MB |

**Projected hosted size ≈ 350–400 MB** (target ≤400 MB for headroom:
WAL/autovacuum need slack under the 500 MB cap).

Slimming happens on a **local scratch copy**, never on the working DB:
`scripts/db_ship.sh` → `createdb archaeology_ship` inside the container,
`pg_dump | psql` restore, run `scripts/hosted_slim.sql`, `VACUUM FULL`, then
`pg_dump archaeology_ship` piped to the Supabase pooler. Local richness
(features, file changes, full PR table) is preserved for re-embedding.

Verification after restore (must pass before deploy):
```sql
SELECT pg_size_pretty(pg_database_size(current_database()));          -- ≤ 400 MB
SELECT count(*) FROM discussion_chunks;                               -- 87,816
SELECT count(*) FROM commits;                                        -- 50,316
```

## 5. Code changes required

| # | Change | Files | Notes |
|---|---|---|---|
| 1 | **Token gate**: `SYNTHESIS_TOKEN` env; `X-Archaeology-Token` header required on `/answer`, `/repos/index-remote`, `/repos/index` when set; 403 otherwise. Unset ⇒ open (local dev unchanged). | `api/auth.py`, `api/main.py` | read endpoints stay public |
| 2 | **CORS from env**: `ARCHAEOLOGY_CORS_ORIGINS` comma list, default localhost pair; add Pages domain at deploy. | `api/main.py` | |
| 3 | **MCP over HTTP**: mount `mcp.streamable_http_app()` at `/mcp` on the FastAPI app. | `api/main.py`, `mcp/server.py` | read-only tools; no auth v1 |
| 4 | **halfvec switch**: `ARCHAEOLOGY_HALFVEC=1` swaps the dense cast to `halfvec` (sparse always uses the indexed `tsv` column). Default off (local vector schema unchanged). | `retrieval/search.py` | `build_dense_sql`/`build_sparse_sql` |
| 5 | **GitHub token resolution**: `GITHUB_TOKEN` env first, `gh` CLI fallback. | `ingest/github.py` | needed in-container; PAT with public-repo read |
| 6 | **Static export**: `output: "export"`, API base from `NEXT_PUBLIC_API_BASE`; settings popover for the synthesis token (localStorage) injected as header. | `web/next.config.ts`, `lib/api.ts`, `components/Settings.tsx` | verified all components are client-side |
| 7 | **HF boot script**: alembic upgrade (no-op on restored DB), then background re-clone of every repo in `repos` (skips present), then uvicorn. Health is up immediately; Path A lights up as clones land (`index_status.local_path_present` already surfaces this). | `scripts/hf_boot.sh`, `Dockerfile` | idempotent; tolerant of cold starts |
| 8 | **Keepalive cron**: daily curl of `/healthz` and `/repos` (public repo Actions). | `.github/workflows/keepalive.yml` | prevents HF 48 h sleep and Supabase 7 d pause |
| 9 | **Deploy scripts**: `scripts/deploy_api.sh` (rsync API subset → HF Space git remote → push), `scripts/deploy_web.sh` (export build → `wrangler pages deploy`). | `scripts/` | documented in runbook |

Dockerfile outline (HF Space):
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
# bake models into the image so cold starts need no HF network
RUN uv run python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
    SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('BAAI/bge-reranker-base')"
COPY src migrations alembic.ini scripts ./
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ARCHAEOLOGY_CLONES_DIR=/data/clones
EXPOSE 7860
CMD ["bash", "scripts/hf_boot.sh"]
```
(≈2 GB image; first boot is slow to pull, cold starts after that are disk-local.)

## 6. Configuration matrix

| Variable | Local dev | Hosted Space |
|---|---|---|
| `ARCHAEOLOGY_DATABASE_URL` | localhost:5433 | Supabase **session pooler** URI, `?sslmode=require` |
| `OPENROUTER_API_KEY` | shell env | secret |
| `ARCHAEOLOGY_SYNTHESIS_MODEL` | `deepseek/deepseek-v4-flash-0731` | same |
| `SYNTHESIS_TOKEN` | unset (open) | random 32-byte hex secret |
| `GITHUB_TOKEN` | unset (gh CLI) | fine-grained PAT, public read |
| `ARCHAEOLOGY_CORS_ORIGINS` | `http://localhost:3000` | `https://<project>.pages.dev` |
| `ARCHAEOLOGY_HALFVEC` | unset | `1` |
| `ARCHAEOLOGY_CLONES_DIR` | `../.scratch/` | `/data/clones` |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | `https://<user>-<space>.hf.space` |

Supabase connection: use the **session pooler** (port 5432 on the pooler
host); if the transaction pooler is used instead, set
`connect_args={"prepare_threshold": None}` for psycopg3.

## 7. Free-tier operational realities

1. **HF Spaces sleep after ~48 h idle** → first request pays a cold start
   (image already pulled; boot ≈ 20–60 s + background clones ≈ 1–3 min for the
   full set, react's 1.1 GB dominating). UI already shows `partial` index
   status until clones land. Keepalive cron keeps it warm.
2. **Supabase free pauses projects after ~7 days of inactivity** → same cron.
3. **Ephemeral disk**: clones are re-fetched on every cold start (by design;
   the DB is the durable state). `lineage_cache` survives in Postgres, so
   repeated Path A queries after a warm-up are fast.
4. **Hosted add-repo works but is CPU-bound**: embedding yt-dlp-scale repos
   takes tens of minutes versus ~10 on the MPS laptop. The 50k-commit cap and
   single-worker queue still apply. Recommended posture: index locally, ship
   the snapshot, keep hosted add-repo for small repos.
5. **OpenRouter quota** is the only variable cost; the token gate plus the
   cheap default model keep misuse bounded. `traces` gives per-call accounting.

## 8. Security posture

- Only read paths are public. Explain and index-remote require the token.
- Clones: strict `owner/repo` normalization (no arbitrary URLs), github.com
  only, commit caps, single concurrent job.
- Repo *content* flows into LLM prompts (README/commit text) — prompt
  injection is possible; the synthesis system prompt is least-privilege
  ("only the evidence"), citations are mechanically checked, and the token
  gate bounds spend. Documented, not solved.
- Secrets live only in HF Space secrets and Supabase; never in the repo.

## 9. Deployment runbook (after accounts exist — §10)

```sh
# 0. prerequisites: supabase project + pgvector enabled; HF account+write token; CF login
# 1. ship the database
./scripts/db_ship.sh "$SUPABASE_DATABASE_URL"      # slim copy -> dump -> restore
# 2. deploy API
export HF_TOKEN=...                                # write-scope
./scripts/deploy_api.sh <hf-username> <space-name> # creates Space, pushes, waits for build
# 3. deploy web
export NEXT_PUBLIC_API_BASE=https://<user>-<space>.hf.space
./scripts/deploy_web.sh <pages-project>            # wrangler pages deploy web/out
# 4. secrets on the Space
#    ARCHAEOLOGY_DATABASE_URL, OPENROUTER_API_KEY, SYNTHESIS_TOKEN,
#    GITHUB_TOKEN, ARCHAEOLOGY_CORS_ORIGINS, ARCHAEOLOGY_HALFVEC=1
# 5. keepalive
gh variable set HOSTED_API_URL --body https://<user>-<space>.hf.space
```

## 10. What I need from you (accounts, ~5 minutes)

1. **Supabase**: project created → copy the *session pooler* connection URI
   (Project Settings → Database → Connection string → URI; port 5432 on the
   pooler host) and the DB password.
2. **Hugging Face**: account + **write** access token
   (Settings → Access Tokens) and your username.
3. **Cloudflare**: account (free) — `npx wrangler login` will open a browser
   once, no token to paste.

Nothing else is billable; all three tiers are $0 for this workload.

## 11. Post-deploy verification checklist

| # | Check | Expected |
|---|---|---|
| 1 | `GET /healthz` | `{"status":"ok"}` |
| 2 | `GET /repos` | 5 repos, chunk counts matching §4 |
| 3 | `GET /repos/facebook/react/why/memo?file=…` | `answered` after clones land |
| 4 | `GET /repos/facebook/react/ask?q=why was useMutableSource removed` | `pr:22292` in top hits |
| 5 | `POST /repos/facebook/react/answer` **without** token | 403 |
| 6 | same **with** `X-Archaeology-Token` | cited answer, `deepseek-v4-flash-0731` |
| 7 | `POST /mcp` initialize | MCP handshake |
| 8 | Pages URL in a browser | picker populated, Trace works, Explain gated |
| 9 | Cold start (after 48 h or manual restart) | health < 60 s, Path A within ~3 min |

## 12. Cost and risks

| Item | Cost |
|---|---|
| HF Space (CPU basic) | $0 |
| Cloudflare Pages | $0 |
| Supabase (500 MB, 5 GB egress) | $0 |
| GitHub Actions keepalive | $0 (public repo) |
| OpenRouter | ~$0.0002 per answer |
| **Total** | **≈ $0** |

| Risk | Likelihood | Mitigation |
|---|---|---|
| Slim DB still >400 MB | low (measured projection) | drop `files_touched`, or exclude yt-dlp (−90 MB) |
| Supabase egress from rerank-heavy traffic | low | rerank happens server-side; egress is DB→Space intra-query only |
| HF build rejects 2 GB image | low | split model bake to a second `RUN` layer; or download at first boot instead |
| Project paused / Space slept | medium | daily keepalive cron (§5.8) |
| halfvec code path diverges from local | medium | pg-gated test matrix runs both (`ARCHAEOLOGY_HALFVEC` ∈ {unset,1}) |

## 13. P0 record (completed)

P0 scaffolding is built, CI-green, and locally verified:

| Item | Verification |
|---|---|
| Token gate | 403 without / 200 with `X-Archaeology-Token`; read paths open (`test_hosting.py`) |
| MCP streamable-http | mounted at `/mcp` (307 redirect to `/mcp/`), session manager in app lifespan |
| halfvec switch | `build_dense_sql` cast switch unit-tested; slim copy measured at **433 MB** |
| `GITHUB_TOKEN` | env-first resolution unit-tested |
| Storage plan | `hosted_slim.sql` run against a real scratch copy: 87,816 chunks, 50,316 commits, 433–435 MB |
| **Ship path (end-to-end)** | `db_ship.sh` against a real second database: slim → dump → restore → **431 MB / 87,816 chunks / 50,316 commits**, 3m41s |
| **Hosted query path** | retrieval against the restored halfvec schema (`ARCHAEOLOGY_HALFVEC=1`): dense+sparse ranks populated, cross-repo top hit = the verified `80d9a4011` ground truth |
| Docker image | builds in ~9 min; container smoke: migrations run, health, 7 repos listed, gated answer 403, retrieval via baked models in `HF_HUB_OFFLINE=1` |
| Static export | `web/out` (5.5 MB) builds with `output: "export"` |
| Scripts | `db_ship.sh`, `deploy_api.sh`, `deploy_web.sh`, `hf_boot.sh`, keepalive workflow |

Two implementation corrections found during P0 (both reflected above):
Dockerfile needed `--no-install-project` before `COPY src` and the offline envs
after the model bake; the `tsv` column stays (ORM coupling).

## 13b. Phases

- **P0 — local-verifiable scaffolding** (no accounts): token gate + tests,
  CORS env, MCP mount, halfvec switch + pg-gated tests, static export,
  Dockerfile, `hf_boot.sh`, `db_ship.sh`/`hosted_slim.sql`, deploy scripts,
  keepalive workflow. Everything CI-green.
- **P1 — accounts + ship** (§10): run §9 runbook.
- **P2 — verify + document**: run §11, add a hosting section to
  `WRITEUP.md` (the free-tier mechanics are writeup material).

## 14. Deployment record — what actually shipped

The spec above was written for a Hugging Face Space. That premise died during
deployment: **HF now requires a PRO subscription for Docker Spaces** ("Static
Spaces are free for everyone, but hosting Gradio and Docker Spaces on free
cpu-basic requires a PRO subscription"). Static Spaces cannot run the Python
API, so the API moved to **Modal** (Starter: $30/month included compute, no
card required, scale-to-zero, volumes). The Dockerfile is reused verbatim as
the image, so the runtime is identical to the locally smoke-tested container.

| Piece | Where it lives now | Notes |
|---|---|---|
| API + MCP | Modal app `codebase-archaeology` → `Web.fastapi_app` | image from `Dockerfile`; clones in the `archaeology-data` volume (persist across cold starts — better than the HF ephemeral plan) |
| DB | Supabase `us-east-2` pooler, 428 MB | `halfvec(384)`, HNSW + GIN; shipped via `db_ship.sh` |
| Web | Cloudflare Pages | static export; API base baked at build |
| Secrets | Modal secret `archaeology-secrets` | DB URI, OpenRouter key, `SYNTHESIS_TOKEN` (generate once; never store in the repo), CORS origins, `ARCHAEOLOGY_HALFVEC=1`, `ARCHAEOLOGY_MCP_DNS_REBINDING=0` |
| Keepalive | GitHub Actions cron | pings `/healthz` + `/repos` (keeps Supabase past its 7-day idle pause; Modal cold-starts are ~15 s) |

### Findings worth keeping

1. **psycopg scheme matters**: SQLAlchemy defaults `postgresql://` to psycopg2;
   the shipped URI must be `postgresql+psycopg://`. This never surfaced locally
   because local dev always used the explicit scheme.
2. **`repos.local_path` is environment-specific**: the shipped DB carries the
   indexing machine's paths. `resolve_clone_path()` now falls back to
   `CLONES_DIR/<repo>`, and the Modal warmup rewrites `local_path` per
   environment.
3. **MCP transport security is a trap on public hosts**: the SDK's
   locally-created session manager wins over the `transport_security=`
   argument (lazy singleton); the fix is to mutate its settings object in
   place, driven by `ARCHAEOLOGY_MCP_DNS_REBINDING`.
4. **Modal volumes refuse non-empty mount paths**: the Dockerfile must not
   pre-create `/data`.
5. **Container stdout is block-buffered**: print-based diagnostics appear late;
   use an HTTP debug route for ground truth (removed after use).
6. **Container smoke tests earned their keep again**: five of these six issues
   were caught before any user saw the deployment.
