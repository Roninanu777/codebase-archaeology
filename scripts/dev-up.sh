#!/usr/bin/env zsh
# Launch backend + web UI detached. Logs in /tmp. Usage: ./scripts/dev-up.sh [port]
set -x
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8000}"

lsof -ti:"$PORT",3000 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

cd "$ROOT"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 nohup uv run python -m archaeology.api.main --port "$PORT" > /tmp/archaeology-api.log 2>&1 &

cd "$ROOT/web"
nohup npm run dev > /tmp/archaeology-web.log 2>&1 &

sleep 12
curl -s "localhost:$PORT/healthz" && echo && curl -s -o /dev/null -w "web:%{http_code}\n" localhost:3000
