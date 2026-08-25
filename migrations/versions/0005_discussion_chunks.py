"""discussion_chunks with pgvector

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE discussion_chunks (
            id serial PRIMARY KEY,
            repo_id integer NOT NULL REFERENCES repos(id),
            source_type text NOT NULL,
            source_id text NOT NULL,
            thread_id text,
            authored_at timestamptz,
            title text,
            body text NOT NULL,
            embedding vector(384),
            tsv tsvector,
            files_touched jsonb NOT NULL DEFAULT '[]'::jsonb,
            linked_commits jsonb NOT NULL DEFAULT '[]'::jsonb,
            liveness_score real,
            embedding_model text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_chunks_source ON discussion_chunks "
        "(repo_id, source_type, source_id)"
    )
    op.execute("CREATE INDEX ix_chunks_repo ON discussion_chunks (repo_id)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON discussion_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_chunks_tsv ON discussion_chunks USING gin (tsv)")


def downgrade() -> None:
    op.drop_table("discussion_chunks")
