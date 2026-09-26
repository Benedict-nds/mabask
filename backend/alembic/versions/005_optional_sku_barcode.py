"""make product sku and barcode optional

Supplier invoices carry no SKU or barcode, so new medicines store NULL instead of a
placeholder. Existing values are left untouched; unique constraints still apply to
non-NULL values on both SQLite and PostgreSQL.

Revision ID: 005_optional_sku_barcode
Revises: 004_sale_corrections
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op

revision = "005_optional_sku_barcode"
down_revision = "004_sale_corrections"
branch_labels = None
depends_on = None


def _guard_sqlite_foreign_keys() -> None:
    # SQLite batch mode rebuilds the products table (copy, drop, rename). With foreign keys
    # enforced, dropping the old table would cascade-delete batches, so refuse to run.
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    enforced = bind.exec_driver_sql("PRAGMA foreign_keys").scalar()
    if enforced:
        raise RuntimeError("Refusing to rebuild products while SQLite foreign_keys=ON; run via alembic/app migrate.")


def upgrade() -> None:
    _guard_sqlite_foreign_keys()
    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column("sku", existing_type=sa.String(length=40), nullable=True)
        batch_op.alter_column("barcode", existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    _guard_sqlite_foreign_keys()
    # NOT NULL needs a value; downgrade fills blanks with id-derived placeholders.
    op.execute(sa.text("UPDATE products SET sku = 'NOSKU-' || substr(id, 1, 8) WHERE sku IS NULL"))
    op.execute(sa.text("UPDATE products SET barcode = 'NOBAR-' || substr(id, 1, 8) WHERE barcode IS NULL"))
    with op.batch_alter_table("products") as batch_op:
        batch_op.alter_column("sku", existing_type=sa.String(length=40), nullable=False)
        batch_op.alter_column("barcode", existing_type=sa.String(length=64), nullable=False)
