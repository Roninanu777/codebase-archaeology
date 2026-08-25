# Codebase Archaeology

Answers "why does this code exist" from git history, PR discussions, and linked issues — every
claim cited to a commit or comment. See the parent directory's DESIGN.md for architecture.

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
