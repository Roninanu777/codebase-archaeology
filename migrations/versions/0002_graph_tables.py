"""graph tables: repos, commits, parents, file changes, features, significance, lineage, jobs

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("url", sa.Text()),
        sa.Column("default_branch", sa.Text()),
        sa.Column("head_sha", sa.Text()),
        sa.Column("indexed_through_sha", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "commits",
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repos.id"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("sha", sa.Text(), nullable=False, primary_key=True),
        sa.Column("author_name", sa.Text()),
        sa.Column("author_email", sa.Text()),
        sa.Column("authored_at", sa.DateTime(timezone=True)),
        sa.Column("committer_name", sa.Text()),
        sa.Column("committer_email", sa.Text()),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("subject", sa.Text()),
        sa.Column("body", sa.Text()),
    )
    op.create_index("ix_commits_repo_committed", "commits", ["repo_id", "committed_at"])
    op.create_table(
        "commit_parents",
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repos.id"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("child_sha", sa.Text(), nullable=False, primary_key=True),
        sa.Column("parent_sha", sa.Text(), nullable=False, primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_table(
        "file_changes",
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repos.id"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("sha", sa.Text(), nullable=False, primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("old_path", sa.Text()),
        sa.Column("additions", sa.Integer()),
        sa.Column("deletions", sa.Integer()),
    )
    op.create_index("ix_file_changes_repo_path", "file_changes", ["repo_id", "path"])
    op.create_table(
        "commit_features",
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repos.id"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("sha", sa.Text(), nullable=False, primary_key=True),
        sa.Column("files_changed", sa.Integer()),
        sa.Column("additions", sa.Integer()),
        sa.Column("deletions", sa.Integer()),
        sa.Column("binary_files", sa.Integer()),
        sa.Column("renamed_files", sa.Integer()),
        sa.Column("whitespace_only", sa.Boolean()),
        sa.Column("comment_only", sa.Boolean()),
        sa.Column("pure_rename", sa.Boolean()),
        sa.Column("extractor_version", sa.Text()),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "commit_significance",
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repos.id"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("sha", sa.Text(), nullable=False, primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
    )
    op.create_index("ix_significance_repo_label", "commit_significance", ["repo_id", "label"])
    op.create_table(
        "lineage_cache",
        sa.Column(
            "repo_id",
            sa.Integer(),
            sa.ForeignKey("repos.id"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("file", sa.Text(), nullable=False, primary_key=True),
        sa.Column("symbol", sa.Text(), nullable=False, primary_key=True),
        sa.Column("head_sha", sa.Text(), nullable=False, primary_key=True),
        sa.Column("commit_shas", sa.JSON()),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("run_key", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("run_key", name="uq_jobs_run_key"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("lineage_cache")
    op.drop_index("ix_significance_repo_label", table_name="commit_significance")
    op.drop_table("commit_significance")
    op.drop_table("commit_features")
    op.drop_index("ix_file_changes_repo_path", table_name="file_changes")
    op.drop_table("file_changes")
    op.drop_table("commit_parents")
    op.drop_index("ix_commits_repo_committed", table_name="commits")
    op.drop_table("commits")
    op.drop_table("repos")
