#!/usr/bin/env bash
# Build the static web export and deploy it to Cloudflare Pages.
# Usage: NEXT_PUBLIC_API_BASE=https://<owner>-<space>.hf.space ./scripts/deploy_web.sh <pages-project>
set -euo pipefail

PROJECT=${1:?usage: deploy_web.sh <pages-project>}
: "${NEXT_PUBLIC_API_BASE:?set NEXT_PUBLIC_API_BASE to the hosted API URL}"

# --force skips wrangler's OpenNext delegation; this is a static export
npx --yes wrangler pages project create "$PROJECT" --production-branch main --force 2>&1 | tail -2 || true

cd web
NEXT_PUBLIC_API_BASE="$NEXT_PUBLIC_API_BASE" npm run build
npx --yes wrangler pages deploy out --project-name "$PROJECT" --commit-dirty=true --force
