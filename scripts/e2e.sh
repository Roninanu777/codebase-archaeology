#!/usr/bin/env zsh
# End-to-end: clone unseen repo -> full pipeline -> tier checks -> surfaces.
# Usage: ./scripts/e2e.sh <owner/repo> [path-in-repo-for-symbol-test]
set -euo pipefail

REPO=${1:?usage: e2e.sh owner/repo [file-for-symbol-probe]}
SYMBOL=${3:-}
FILE=${2:-}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SLUG=${REPO//\//-}

cd "$ROOT"
echo "== cloning $REPO (then un-filtering for lineage work)"
git clone --filter=blob:none "https://github.com/$REPO" ".scratch/$SLUG"
git -C ".scratch/$SLUG" config remote.origin.partialclonefilter ""
git -C ".scratch/$SLUG" fetch --refetch origin

echo "== tier-1 ingest"
time uv run python -m archaeology.cli ingest "../.scratch/$SLUG" --name "$REPO" --url "https://github.com/$REPO"

echo "== significance layers"
uv run python -m archaeology.cli classify --name "$REPO"

echo "== tier-2 PR backfill"
time uv run python -m archaeology.cli backfill-prs --name "$REPO"

echo "== embedding"
time uv run python -m archaeology.cli embed --name "$REPO"

if [[ -n "$FILE" && -n "$SYMBOL" ]]; then
  echo "== Path A probe ($SYMBOL @ $FILE) - expect answer on js/ts, abstain otherwise"
  uv run python -m archaeology.cli why "$REPO" "$SYMBOL" --file "$FILE" || true
fi

echo "== Path B probe"
uv run python -m archaeology.cli ask "$REPO" "why was this design introduced" -n 5 || true

echo "== idempotence: second runs must skip"
uv run python -m archaeology.cli ingest "../.scratch/$SLUG" --name "$REPO"
uv run python -m archaeology.cli embed --name "$REPO"

echo "== done: $REPO indexed and answerable"
