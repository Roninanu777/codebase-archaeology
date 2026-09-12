#!/usr/bin/env bash
# Ship a slimmed query-snapshot of the local database to a remote Postgres.
# Usage: ./scripts/db_ship.sh "postgresql://...supabase...?sslmode=require"
set -euo pipefail

TARGET=${1:?usage: db_ship.sh <target-postgres-uri>}
CONTAINER=${ARCHAEOLOGY_DB_CONTAINER:-app-db-1}
SHIP=archaeology_ship

echo "== preflight: target reachable"
if ! docker exec -i "$CONTAINER" psql "$TARGET" -c "SELECT 1" >/dev/null 2>&1; then
  echo "ERROR: cannot connect to target (does the database exist? is the pooler URI right?)"
  exit 1
fi

echo "== ensuring pgvector on target"
docker exec -i "$CONTAINER" psql "$TARGET" -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

# NOTE: use the Supabase *session pooler* URI (IPv4, session semantics).
# Direct db.<ref>.supabase.co connections are IPv6-only on new projects.

echo "== building slim scratch copy ($SHIP)"
docker exec -i "$CONTAINER" psql -U archaeology -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS $SHIP;" -c "CREATE DATABASE $SHIP;"
docker exec -i "$CONTAINER" bash -c \
  "pg_dump -U archaeology archaeology | psql -q -U archaeology -d $SHIP"

echo "== applying hosted_slim.sql"
docker exec -i "$CONTAINER" psql -U archaeology -d "$SHIP" -v ON_ERROR_STOP=1 \
  < scripts/hosted_slim.sql

SIZE_MB=$(docker exec -i "$CONTAINER" psql -U archaeology -d "$SHIP" -t -A \
  -c "SELECT pg_database_size(current_database()) / 1024 / 1024")
CHUNKS=$(docker exec -i "$CONTAINER" psql -U archaeology -d "$SHIP" -t -A \
  -c "SELECT count(*) FROM discussion_chunks")
echo "== slim snapshot: ${SIZE_MB} MB, ${CHUNKS} chunks"
if [ "$SIZE_MB" -gt 450 ]; then
  echo "WARN: snapshot exceeds 450 MB; remove a repo from scripts/hosted_slim.sql"
fi

echo "== restoring to target"
docker exec -i "$CONTAINER" bash -c \
  "pg_dump -U archaeology --no-owner --no-acl --clean --if-exists $SHIP | psql -q $TARGET"

echo "== target verification"
docker exec -i "$CONTAINER" psql "$TARGET" -t -A \
  -c "SELECT pg_size_pretty(pg_database_size(current_database()));
      SELECT count(*) FROM discussion_chunks;
      SELECT count(*) FROM commits;"

echo "== dropping scratch copy"
docker exec -i "$CONTAINER" psql -U archaeology -d postgres \
  -c "DROP DATABASE IF EXISTS $SHIP;" >/dev/null
