"""sale correction requests

Revision ID: 004_sale_corrections
Revises: 003_po_review
Create Date: 2026-09-22
"""

import sqlalchemy as sa
from alembic import op

revision = "004_sale_corrections"
down_revision = "003_po_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sale_correction_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sale_id", sa.String(length=36), sa.ForeignKey("sales.id"), nullable=False),
        sa.Column("requested_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("return_id", sa.String(length=36), sa.ForeignKey("returns.id"), nullable=True),
        sa.Column("corrected_sale_id", sa.String(length=36), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("approval_idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("approval_idempotency_key", name="uq_sale_correction_approval_idempotency"),
    )
    op.create_index("ix_sale_correction_requests_sale_id", "sale_correction_requests", ["sale_id"])
    op.create_index("ix_sale_corrections_status_created", "sale_correction_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_sale_corrections_status_created", table_name="sale_correction_requests")
    op.drop_index("ix_sale_correction_requests_sale_id", table_name="sale_correction_requests")
    op.drop_table("sale_correction_requests")
