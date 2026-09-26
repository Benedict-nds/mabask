"""Derive batch → purchase order → supplier from existing stock movements.

Does not store supplier_id on Batch. Resolves via the earliest PURCHASE movement
with reference_type='purchase_order' for each batch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models import MovementType, PurchaseOrder, StockMovement


@dataclass(frozen=True, slots=True)
class BatchProvenance:
    supplier_id: str | None = None
    supplier_name: str | None = None
    purchase_order_id: str | None = None
    po_number: str | None = None
    received_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PurchaseRef:
    purchase_order_id: str | None = None
    po_number: str | None = None
    supplier_id: str | None = None
    supplier_name: str | None = None


def resolve_batch_provenance(db: Session, batch_ids: Sequence[str]) -> dict[str, BatchProvenance]:
    """Map batch_id → originating PO/supplier from the earliest purchase receive."""
    ids = list(dict.fromkeys(bid for bid in batch_ids if bid))
    if not ids:
        return {}

    movements = (
        db.query(StockMovement)
        .filter(
            StockMovement.batch_id.in_(ids),
            StockMovement.reference_type == "purchase_order",
            StockMovement.movement_type == MovementType.PURCHASE,
        )
        .order_by(StockMovement.created_at.asc())
        .all()
    )

    first_by_batch: dict[str, StockMovement] = {}
    for movement in movements:
        if movement.batch_id and movement.batch_id not in first_by_batch:
            first_by_batch[movement.batch_id] = movement

    po_ids = {m.reference_id for m in first_by_batch.values() if m.reference_id}
    orders = _load_orders(db, po_ids)

    result: dict[str, BatchProvenance] = {}
    for batch_id in ids:
        movement = first_by_batch.get(batch_id)
        if movement is None:
            result[batch_id] = BatchProvenance()
            continue
        order = orders.get(movement.reference_id) if movement.reference_id else None
        if order is None:
            result[batch_id] = BatchProvenance(
                purchase_order_id=movement.reference_id or None,
                received_at=movement.created_at,
            )
            continue
        result[batch_id] = BatchProvenance(
            supplier_id=order.supplier_id,
            supplier_name=order.supplier.name if order.supplier else None,
            purchase_order_id=order.id,
            po_number=order.po_number,
            received_at=movement.created_at,
        )
    return result


def resolve_purchase_refs(db: Session, po_ids: Sequence[str]) -> dict[str, PurchaseRef]:
    """Map purchase_order id → display fields for stock movement enrichment."""
    ids = list(dict.fromkeys(pid for pid in po_ids if pid))
    if not ids:
        return {}
    orders = _load_orders(db, set(ids))
    out: dict[str, PurchaseRef] = {}
    for po_id in ids:
        order = orders.get(po_id)
        if order is None:
            out[po_id] = PurchaseRef(purchase_order_id=po_id)
            continue
        out[po_id] = PurchaseRef(
            purchase_order_id=order.id,
            po_number=order.po_number,
            supplier_id=order.supplier_id,
            supplier_name=order.supplier.name if order.supplier else None,
        )
    return out


def _load_orders(db: Session, po_ids: set[str]) -> dict[str, PurchaseOrder]:
    if not po_ids:
        return {}
    rows = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.supplier))
        .filter(PurchaseOrder.id.in_(po_ids))
        .all()
    )
    return {row.id: row for row in rows}
