"""add users.last_login_at

Revision ID: 002_user_last_login
Revises: 001_initial
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op

revision = "002_user_last_login"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
