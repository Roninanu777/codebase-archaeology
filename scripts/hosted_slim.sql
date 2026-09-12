-- Hosted slim pass: run against a scratch copy (see scripts/db_ship.sh),
-- never against the working database.
--
-- Removes test/demo repos, prunes query-time-unneeded row data, and halves
-- embedding storage via halfvec. Schema is kept intact so the hosted instance
-- can still index new repos.
--
-- Edit DROP_REPOS to change the shipped set (bun/yt-dlp are the big ones).

\set ON_ERROR_STOP on
CREATE EXTENSION IF NOT EXISTS vector;

-- index rebuilds on the slim copy are heavy; Supabase sessions may be capped
-- serial build: parallel HNSW workers exhaust small /dev/shm (containers)
SET maintenance_work_mem = '512MB';
SET max_parallel_maintenance_workers = 0;
SET statement_timeout = 0;

-- 1. drop test repos entirely
DELETE FROM discussion_chunks   WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM commit_parents      WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM commits             WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM commit_significance WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM commit_pr_links     WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM commit_features     WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM file_changes        WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM pull_requests       WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM lineage_cache       WHERE repo_id IN (SELECT id FROM repos WHERE name IN ('oven-sh/bun', 't/js'));
DELETE FROM repos               WHERE name IN ('oven-sh/bun', 't/js');

-- 2. prune row data that only matters at (local) embedding time
DELETE FROM file_changes;
DELETE FROM commit_features;
DELETE FROM pull_requests;

-- 3. halve embedding storage (float32 vector -> float16 halfvec)
DROP INDEX IF EXISTS ix_chunks_embedding_hnsw;
ALTER TABLE discussion_chunks
    ALTER COLUMN embedding TYPE halfvec(384) USING embedding::halfvec(384);
CREATE INDEX ix_chunks_embedding_hnsw
    ON discussion_chunks USING hnsw (embedding halfvec_cosine_ops);

ANALYZE;
VACUUM FULL;
