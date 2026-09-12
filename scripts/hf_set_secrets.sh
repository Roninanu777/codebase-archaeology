#!/usr/bin/env bash
# Set Hugging Face Space secrets via the API.
# Usage: HF_TOKEN=hf_... ./scripts/hf_set_secrets.sh <owner> <space> <db-url> <openrouter-key> <synthesis-token> [github-token] [cors-origins]
set -euo pipefail

OWNER=${1:?usage: hf_set_secrets.sh <owner> <space> <db-url> <or-key> <syn-token> [gh-token] [cors]}
SPACE=${2:?}
DB_URL=${3:?}
OR_KEY=${4:?}
SYN_TOKEN=${5:?}
GH_TOKEN=${6:-}
CORS=${7:-http://localhost:3000}
: "${HF_TOKEN:?set HF_TOKEN (write scope)}"

set_secret() {
  local key="$1" value="$2"
  local code
  code=$(python3 - "$OWNER" "$SPACE" "$HF_TOKEN" "$key" "$value" <<'PY'
import json, sys, urllib.request
owner, space, token, key, value = sys.argv[1:6]
req = urllib.request.Request(
    f"https://huggingface.co/api/spaces/{owner}/{space}/secrets",
    data=json.dumps({"key": key, "value": value}).encode(),
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(resp.status)
except Exception as exc:  # noqa: BLE001
    print(f"ERR {exc}")
PY
)
  echo "  $key -> $code"
}

echo "== setting Space secrets for $OWNER/$SPACE"
set_secret ARCHAEOLOGY_DATABASE_URL "$DB_URL"
set_secret OPENROUTER_API_KEY "$OR_KEY"
set_secret SYNTHESIS_TOKEN "$SYN_TOKEN"
if [ -n "$GH_TOKEN" ]; then
  set_secret GITHUB_TOKEN "$GH_TOKEN"
else
  echo "  GITHUB_TOKEN -> not provided (hosted indexing will skip the PR stage)"
fi
set_secret ARCHAEOLOGY_CORS_ORIGINS "$CORS"
set_secret ARCHAEOLOGY_HALFVEC "1"
echo "== done; the Space restarts automatically on secret changes"
