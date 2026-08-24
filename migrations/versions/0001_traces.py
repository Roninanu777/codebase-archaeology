"""traces table

Revision ID: 0001
Revises:
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("model", sa.Text()),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response", sa.Text()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("eval_case_id", sa.Text()),
        sa.Column("repo_id", sa.Integer()),
        sa.Column("extra", sa.JSON()),
    )


def downgrade() -> None:
    op.drop_table("traces")
