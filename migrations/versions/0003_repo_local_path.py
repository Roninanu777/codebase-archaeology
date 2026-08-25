"""repos.local_path

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("local_path", sa.Text()))


def downgrade() -> None:
    op.drop_column("repos", "local_path")
