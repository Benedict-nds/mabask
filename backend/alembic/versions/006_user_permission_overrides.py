"""per-user permission overrides

Adds user_permission_overrides (one row per user + permission code, effect ALLOW or DENY).
No rows are created, so every existing user keeps exactly their role's permissions.
Only a new table is created; no existing table is altered or rebuilt.

Revision ID: 006_user_permission_overrides
Revises: 005_optional_sku_barcode
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "006_user_permission_overrides"
down_revision = "005_optional_sku_barcode"
branch_labels = None
depends_on = None

TABLE = "user_permission_overrides"


def upgrade() -> None:
    # 001_initial builds the schema from the current models, so a fresh database already has it.
    if sa.inspect(op.get_bind()).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission_code", sa.String(length=64), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False),
        sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "permission_code", name="uq_user_permission_override"),
        sa.CheckConstraint("effect IN ('ALLOW', 'DENY')", name="ck_user_permission_override_effect"),
    )
    op.create_index("ix_user_permission_overrides_user_id", TABLE, ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_permission_overrides_user_id", table_name=TABLE)
    op.drop_table(TABLE)
