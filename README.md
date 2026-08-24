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
