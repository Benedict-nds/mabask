"""po review comment and CHANGES_REQUESTED status

Revision ID: 003_po_review
Revises: 002_user_last_login
Create Date: 2026-09-22
"""

import sqlalchemy as sa
from alembic import op

revision = "003_po_review"
down_revision = "002_user_last_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE postatus ADD VALUE IF NOT EXISTS 'CHANGES_REQUESTED'"))

    with op.batch_alter_table("purchase_orders") as batch_op:
        batch_op.add_column(sa.Column("review_comment", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("review_requested_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_po_review_requested_by", "users", ["review_requested_by"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("purchase_orders") as batch_op:
        batch_op.drop_constraint("fk_po_review_requested_by", type_="foreignkey")
        batch_op.drop_column("review_requested_at")
        batch_op.drop_column("review_requested_by")
        batch_op.drop_column("review_comment")
    # PostgreSQL cannot cheaply remove an enum value; CHANGES_REQUESTED remains on the type.
