#!/usr/bin/env bash
# Deploy the API to a Hugging Face Space (Docker SDK).
# Usage: HF_TOKEN=hf_... ./scripts/deploy_api.sh <hf-owner> <space-name>
set -euo pipefail

OWNER=${1:?usage: deploy_api.sh <hf-owner> <space-name>}
SPACE=${2:?usage: deploy_api.sh <hf-owner> <space-name>}
: "${HF_TOKEN:?set HF_TOKEN (write scope)}"

echo "== creating space (idempotent)"
curl -s -X POST https://huggingface.co/api/repos/create \
  -H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\":\"$SPACE\",\"type\":\"space\",\"sdk\":\"docker\",\"private\":false}" \
  >/dev/null || true

TMP=$(mktemp -d)
echo "== staging API subset -> $TMP"
tar cf - \
  --exclude .venv --exclude web --exclude .git --exclude evals \
  --exclude tests --exclude .scratch --exclude .github --exclude data \
  --exclude .pytest_cache --exclude .ruff_cache --exclude .mypy_cache \
  --exclude __pycache__ --exclude node_modules \
  Dockerfile .dockerignore pyproject.toml uv.lock alembic.ini \
  src migrations scripts docs README.md WRITEUP.md \
  | (cd "$TMP" && tar xf -)

cat > "$TMP/README.md" <<'EOF'
---
title: Codebase Archaeology
emoji: 🏺
colorFrom: gray
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

API for Codebase Archaeology — why does this code exist? See the repository
for the full project and docs/HOSTING.md for the deployment spec.
EOF

cd "$TMP"
git init -q -b main
git add -A
git -c user.email=deploy@localhost -c user.name=deploy commit -q -m "deploy api"
git remote add hf "https://user:${HF_TOKEN}@huggingface.co/spaces/${OWNER}/${SPACE}"
echo "== pushing (force, space repo is generated)"
git push -f -q hf main

echo "space: https://huggingface.co/spaces/${OWNER}/${SPACE}"
echo "url:   https://${OWNER}-${SPACE}.hf.space"
echo "remember the Space secrets:"
echo "  ARCHAEOLOGY_DATABASE_URL OPENROUTER_API_KEY SYNTHESIS_TOKEN GITHUB_TOKEN"
echo "  ARCHAEOLOGY_CORS_ORIGINS=<pages-domain> ARCHAEOLOGY_HALFVEC=1"
