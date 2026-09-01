# Codebase Archaeology

Answers "why does this code exist" from git history, PR discussions, and linked issues — every
claim cited to a commit or comment. See [docs/DESIGN.md](docs/DESIGN.md) for architecture
and [docs/CONTEXT.md](docs/CONTEXT.md) for the glossary.

## Layout

- `src/archaeology/` — core package; `api/`, `mcp/` (later), and worker entry points stay thin
- `migrations/` — Alembic schema migrations
- `docker-compose.yml` — Postgres 16 + pgvector for local development

## Development

```sh
uv sync                      # install deps into .venv
docker compose up -d db      # start Postgres
uv run alembic upgrade head  # apply migrations
uv run pytest                # tests (sqlite in-memory, no services needed)
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

## Indexing a repo

```sh
uv run python -m archaeology.cli ingest ../.scratch/react --name facebook/react --url https://github.com/facebook/react
uv run python -m archaeology.cli classify --name facebook/react          # JS/TSX AST significance layer
uv run python -m archaeology.cli embed --name facebook/react             # chunk + embed commit messages (Path B)
uv run python -m archaeology.cli why facebook/react createRoot --file packages/react-dom/src/client/ReactDOMRoot.js
uv run python -m archaeology.cli ask facebook/react "why does the scheduler use lanes"
```

`why` resolves the symbol at HEAD (tree-sitter, with regex fallback for Flow
files), walks its lineage (`git log -L`, cached), drops floor-insignificant
commits, and prints a cited timeline. Abstains when evidence is too thin.

`ask` runs hybrid retrieval (pgvector dense + BM25 ts_rank_cd, fused with RRF)
over enriched commit-message chunks. Liveness scores flag hits whose files no
longer exist at HEAD; all-stale results carry an explicit staleness note.

## Surfaces

```sh
uv run python -m archaeology.api.main --port 8000   # REST API
uv run python -m archaeology.mcp.server             # MCP server (stdio)
```

REST: `POST /repos/index`, `GET /repos/{name}/status`,
`GET /repos/{name}/why/{symbol}?file=`, `GET /repos/{name}/ask?q=&n=`,
`GET /repos/{name}/answer/{symbol}` (LLM synthesis).
Every answer carries an `index_status` footer so partial indexes are visible.

MCP tools: `why_does_this_exist`, `history_of_symbol`, `search_decisions`.
Point any MCP client at the stdio server; both surfaces wrap the same core.

## LLM synthesis (optional)

```sh
export OPENROUTER_API_KEY="sk-or-..."        # https://openrouter.ai/keys
export ARCHAEOLOGY_SYNTHESIS_MODEL="deepseek/deepseek-v4-flash-0731"   # optional override
uv run python -m archaeology.cli answer facebook/react createRoot --file packages/react-dom/src/client/ReactDOMRoot.js
```

Synthesis reads only the assembled evidence bundle, must cite sha brackets,
and answers INSUFFICIENT_EVIDENCE rather than guessing. Every prompt/response
is traced to the `traces` table. Without a key, everything except `answer`
works fully locally.
