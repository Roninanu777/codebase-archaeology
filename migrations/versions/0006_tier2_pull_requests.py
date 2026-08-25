"""tier-2: pull_requests and commit_pr_links

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pull_requests",
        sa.Column("repo_id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("author", sa.Text()),
        sa.Column("state", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("merged_at", sa.DateTime(timezone=True)),
        sa.Column("merge_sha", sa.Text()),
        sa.Column("comment_count", sa.Integer()),
        sa.Column("discussion", sa.Text()),
        sa.UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),
    )
    op.create_index("ix_pr_repo_merged", "pull_requests", ["repo_id", "merged_at"])
    op.create_table(
        "commit_pr_links",
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repos.id"), primary_key=True),
        sa.Column("sha", sa.Text(), primary_key=True),
        sa.Column("pr_number", sa.Integer(), primary_key=True),
    )
    op.create_index("ix_cpl_pr", "commit_pr_links", ["repo_id", "pr_number"])


def downgrade() -> None:
    op.drop_table("commit_pr_links")
    op.drop_index("ix_pr_repo_merged", table_name="pull_requests")
    op.drop_table("pull_requests")
