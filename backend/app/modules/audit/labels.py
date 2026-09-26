"""Human-readable references for audit rows, resolved in one query per entity type."""

import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import (
    AuditLog,
    Batch,
    Product,
    PurchaseOrder,
    Return,
    Sale,
    SaleCorrectionRequest,
    Supplier,
    User,
)

_SENSITIVE = re.compile(r"pass(word)?|token|secret|hash|api[_-]?key|credential", re.IGNORECASE)


def redact(details: Any) -> Any:
    """Defensive: never return secret-looking values even if a caller logged them."""
    if isinstance(details, dict):
        return {k: ("[redacted]" if _SENSITIVE.search(str(k)) else redact(v)) for k, v in details.items()}
    if isinstance(details, list):
        return [redact(v) for v in details]
    return details


def _labels_for(db: Session, entity_type: str, ids: list[str]) -> dict[str, str]:
    if entity_type == "purchase_order":
        rows = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.supplier)).filter(PurchaseOrder.id.in_(ids)).all()
        return {r.id: f"{r.po_number}" + (f" · {r.supplier.name}" if r.supplier else "") for r in rows}
    if entity_type == "product":
        rows = db.query(Product.id, Product.name, Product.sku).filter(Product.id.in_(ids)).all()
        return {r[0]: f"{r[1]} ({r[2]})" if r[2] else r[1] for r in rows}
    if entity_type == "batch":
        rows = db.query(Batch).options(joinedload(Batch.product)).filter(Batch.id.in_(ids)).all()
        return {r.id: f"Batch {r.batch_number}" + (f" · {r.product.name}" if r.product else "") for r in rows}
    if entity_type == "sale":
        rows = db.query(Sale.id, Sale.sale_number).filter(Sale.id.in_(ids)).all()
        return {r[0]: r[1] for r in rows}
    if entity_type == "return":
        rows = db.query(Return.id, Return.return_number).filter(Return.id.in_(ids)).all()
        return {r[0]: r[1] for r in rows}
    if entity_type == "sale_correction":
        rows = (
            db.query(SaleCorrectionRequest)
            .options(joinedload(SaleCorrectionRequest.sale))
            .filter(SaleCorrectionRequest.id.in_(ids))
            .all()
        )
        return {
            r.id: f"CR-{r.id.replace('-', '')[:8].upper()}" + (f" · sale {r.sale.sale_number}" if r.sale else "")
            for r in rows
        }
    if entity_type == "supplier":
        rows = db.query(Supplier.id, Supplier.name).filter(Supplier.id.in_(ids)).all()
        return {r[0]: r[1] for r in rows}
    if entity_type == "user":
        rows = db.query(User.id, User.full_name, User.email).filter(User.id.in_(ids)).all()
        return {r[0]: f"{r[1]} ({r[2]})" for r in rows}
    return {}


def resolve_entity_labels(db: Session, rows: list[AuditLog], details_by_id: dict[str, dict]) -> dict[str, str | None]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.entity_id:
            grouped[row.entity_type].add(row.entity_id)
    resolved: dict[tuple[str, str], str] = {}
    for entity_type, ids in grouped.items():
        for entity_id, label in _labels_for(db, entity_type, list(ids)).items():
            resolved[(entity_type, entity_id)] = label
    out: dict[str, str | None] = {}
    for row in rows:
        label = resolved.get((row.entity_type, row.entity_id))
        if label is None:
            details = details_by_id.get(row.id) or {}
            label = (
                details.get("reference")
                or details.get("po_number")
                or details.get("sale_number")
                or details.get("name")
                or (row.entity_id if row.entity_type == "settings" else None)
            )
        out[row.id] = label
    return out
