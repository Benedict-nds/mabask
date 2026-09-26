from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.dates import parse_expiry
from app.core.permissions import has_permission
from app.core.responses import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Batch, MovementType, POStatus, Product, PurchaseOrder, PurchaseOrderItem, Supplier, User
from app.core.schemas import (
    AdhocReceiveIn,
    ImportReceiveIn,
    POCreate,
    POItemIn,
    POOut,
    ReceiptLineOut,
    ReceiptOut,
    ReceiveIn,
    ReceiveLineIn,
    RequestChangesIn,
)
from app.modules.sales.numbering import next_po_number
from app.modules.inventory.stock import apply_stock_change


EDITABLE_STATUSES = {POStatus.DRAFT, POStatus.CHANGES_REQUESTED}


def to_po_out(po: PurchaseOrder) -> POOut:
    return POOut(
        id=po.id,
        po_number=po.po_number,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier.name if po.supplier else None,
        status=po.status.value,
        notes=po.notes,
        review_comment=po.review_comment or "",
        review_requested_by=po.review_requested_by,
        review_requested_by_name=po.reviewer.full_name if po.reviewer else None,
        review_requested_at=po.review_requested_at,
        subtotal=po.subtotal,
        total=po.total,
        created_by=po.created_by,
        created_by_name=po.creator.full_name if po.creator else None,
        approved_by=po.approved_by,
        created_at=po.created_at,
        items=po.items,
    )


def _po_options():
    return (
        joinedload(PurchaseOrder.items),
        joinedload(PurchaseOrder.supplier),
        joinedload(PurchaseOrder.creator),
        joinedload(PurchaseOrder.reviewer),
    )


def _load(db: Session, po_id: str) -> PurchaseOrder:
    po = db.query(PurchaseOrder).options(*_po_options()).filter(PurchaseOrder.id == po_id).first()
    if po is None:
        raise NotFoundError("Purchase order not found")
    return po


def _audit_po(
    db: Session,
    *,
    actor: User,
    action: str,
    po: PurchaseOrder,
    previous_status: str,
    reason: str | None = None,
    changes: list[str] | None = None,
    extra: dict | None = None,
) -> None:
    details: dict = {
        "po_number": po.po_number,
        "previous_status": previous_status,
        "new_status": po.status.value,
    }
    if reason:
        details["reason"] = reason
    if changes is not None:
        details["changes"] = changes[:25]
    if extra:
        details.update(extra)
    record_audit(db, user=actor, action=action, entity_type="purchase_order", entity_id=po.id, details=details)


def _totals(items: list[POItemIn] | list[PurchaseOrderItem]) -> Decimal:
    total = Decimal("0")
    for item in items:
        total += Decimal(item.quantity_ordered) * Decimal(item.unit_cost)
    return total.quantize(Decimal("0.01"))


def list_pos(db: Session, status: str | None = None, supplier_id: str | None = None) -> list[POOut]:
    query = db.query(PurchaseOrder).options(*_po_options())
    if status:
        query = query.filter(PurchaseOrder.status == POStatus(status))
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    return [to_po_out(po) for po in query.order_by(PurchaseOrder.created_at.desc()).all()]


def _build_po(db: Session, data: POCreate, actor: User, status: POStatus) -> PurchaseOrder:
    if not data.items:
        raise ValidationAppError("A purchase order needs at least one line")
    total = _totals(data.items)
    po = PurchaseOrder(
        po_number=next_po_number(db),
        supplier_id=data.supplier_id,
        status=status,
        notes=data.notes,
        subtotal=total,
        total=total,
        created_by=actor.id,
    )
    db.add(po)
    db.flush()
    for item in data.items:
        db.add(
            PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity_ordered=item.quantity_ordered,
                unit_cost=item.unit_cost,
                batch_number=item.batch_number,
                expiry_date=item.expiry_date,
            )
        )
    db.flush()
    return po


def create_po(db: Session, data: POCreate, actor: User) -> POOut:
    po = _build_po(db, data, actor, POStatus.DRAFT)
    record_audit(
        db,
        user=actor,
        action="PURCHASE_ORDER_CREATED",
        entity_type="purchase_order",
        entity_id=po.id,
        details={"po_number": po.po_number, "new_status": po.status.value, "lines": len(data.items)},
    )
    db.commit()
    return to_po_out(_load(db, po.id))


def _line_key(product_id: str | None, product_name: str) -> str:
    return product_id or f"name:{product_name.strip().lower()}"


def _diff_items(old: list[PurchaseOrderItem], new: list[POItemIn]) -> list[str]:
    before = {_line_key(i.product_id, i.product_name): i for i in old}
    after = {_line_key(i.product_id, i.product_name): i for i in new}
    changes: list[str] = []
    for key, item in after.items():
        prev = before.get(key)
        if prev is None:
            changes.append(f"Added {item.product_name} x{item.quantity_ordered} @ {Decimal(item.unit_cost):.2f}")
            continue
        if prev.quantity_ordered != item.quantity_ordered:
            changes.append(f"{item.product_name}: qty {prev.quantity_ordered} -> {item.quantity_ordered}")
        if Decimal(prev.unit_cost).quantize(Decimal("0.0001")) != Decimal(item.unit_cost).quantize(Decimal("0.0001")):
            changes.append(f"{item.product_name}: cost {Decimal(prev.unit_cost):.2f} -> {Decimal(item.unit_cost):.2f}")
    for key, item in before.items():
        if key not in after:
            changes.append(f"Removed {item.product_name}")
    return changes


def _replace_lines(db: Session, po: PurchaseOrder, data: POCreate) -> list[str]:
    if not data.items:
        raise ValidationAppError("A purchase order needs at least one line")
    changes = _diff_items(list(po.items), data.items)
    if data.supplier_id != po.supplier_id:
        changes.insert(0, "Supplier changed")
    for item in list(po.items):
        db.delete(item)
    db.flush()
    po.supplier_id = data.supplier_id
    po.notes = data.notes
    for item in data.items:
        db.add(
            PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=item.product_id,
                product_name=item.product_name,
                quantity_ordered=item.quantity_ordered,
                unit_cost=item.unit_cost,
                batch_number=item.batch_number,
                expiry_date=item.expiry_date,
            )
        )
    po.subtotal = po.total = _totals(data.items)
    return changes


def update_draft(db: Session, po_id: str, data: POCreate, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status not in EDITABLE_STATUSES:
        raise ValidationAppError("Only draft or changes-requested purchase orders can be edited")
    previous = po.status.value
    changes = _replace_lines(db, po, data)
    if po.status == POStatus.CHANGES_REQUESTED:
        po.status = POStatus.DRAFT
    _audit_po(db, actor=actor, action="PURCHASE_ORDER_UPDATED", po=po, previous_status=previous, changes=changes)
    db.commit()
    return to_po_out(_load(db, po.id))


def review_edit(db: Session, po_id: str, data: POCreate, reason: str, actor: User) -> POOut:
    """Reviewer adjusts a SUBMITTED PO in place; it stays SUBMITTED and awaits approval."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationAppError("A reason is required when editing a submitted purchase order")
    po = _load(db, po_id)
    if po.status != POStatus.SUBMITTED:
        raise ValidationAppError("Only submitted purchase orders can be edited during review")
    if po.created_by == actor.id and actor.role.name != "admin":
        raise ForbiddenError("You cannot review-edit a purchase order you created; request changes instead")
    previous = po.status.value
    changes = _replace_lines(db, po, data)
    _audit_po(
        db,
        actor=actor,
        action="PURCHASE_ORDER_UPDATED",
        po=po,
        previous_status=previous,
        reason=reason,
        changes=changes,
        extra={"reviewer_edit": True},
    )
    db.commit()
    return to_po_out(_load(db, po.id))


def submit_po(db: Session, po_id: str, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status != POStatus.DRAFT:
        raise ValidationAppError("Only drafts can be submitted")
    previous = po.status.value
    po.status = POStatus.SUBMITTED
    po.submitted_at = datetime.now(timezone.utc)
    _audit_po(db, actor=actor, action="PURCHASE_ORDER_SUBMITTED", po=po, previous_status=previous)
    db.commit()
    return to_po_out(_load(db, po.id))


def approve_po(db: Session, po_id: str, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status != POStatus.SUBMITTED:
        raise ValidationAppError("Only submitted purchase orders can be approved")
    previous = po.status.value
    po.status = POStatus.APPROVED
    po.approved_by = actor.id
    po.approved_at = datetime.now(timezone.utc)
    _audit_po(db, actor=actor, action="PURCHASE_ORDER_APPROVED", po=po, previous_status=previous)
    db.commit()
    return to_po_out(_load(db, po.id))


def request_changes(db: Session, po_id: str, data: RequestChangesIn, actor: User) -> POOut:
    reason = (data.reason or "").strip()
    if not reason:
        raise ValidationAppError("A reason is required to request changes")
    po = _load(db, po_id)
    if po.status != POStatus.SUBMITTED:
        raise ValidationAppError("Changes can only be requested on submitted purchase orders")
    previous = po.status.value
    po.status = POStatus.CHANGES_REQUESTED
    po.review_comment = reason
    po.review_requested_by = actor.id
    po.review_requested_at = datetime.now(timezone.utc)
    _audit_po(
        db,
        actor=actor,
        action="PURCHASE_ORDER_CHANGES_REQUESTED",
        po=po,
        previous_status=previous,
        reason=reason,
    )
    db.commit()
    return to_po_out(_load(db, po.id))


def cancel_po(db: Session, po_id: str, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status in {POStatus.RECEIVED, POStatus.CANCELLED}:
        raise ValidationAppError("This purchase order cannot be cancelled")
    previous = po.status.value
    po.status = POStatus.CANCELLED
    po.cancelled_at = datetime.now(timezone.utc)
    _audit_po(db, actor=actor, action="PURCHASE_ORDER_CANCELLED", po=po, previous_status=previous)
    db.commit()
    return to_po_out(_load(db, po.id))


def _upsert_batch(db: Session, product: Product, batch_number: str, expiry, cost) -> Batch:
    expiry = parse_expiry(expiry, required=True)
    batch = db.query(Batch).filter(Batch.product_id == product.id, Batch.batch_number == batch_number).first()
    if batch is None:
        batch = Batch(
            product_id=product.id,
            batch_number=batch_number,
            expiry_date=expiry,
            quantity=0,
            cost_price=cost,
        )
        db.add(batch)
        db.flush()
    return batch


def _apply_receive(db: Session, po: PurchaseOrder, data: ReceiveIn, actor: User) -> None:
    if po.status not in {POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED}:
        raise ValidationAppError("Only approved purchase orders can be received")
    if not data.lines:
        raise ValidationAppError("Nothing to receive")

    items_by_id = {item.id: item for item in po.items}
    prepared: list[tuple] = []
    remaining_by_item: dict[str, int] = {
        item.id: item.quantity_ordered - item.quantity_received for item in po.items
    }

    for line in data.lines:
        item = items_by_id.get(line.item_id)
        if item is None:
            raise ValidationAppError("Unknown purchase order line", {"item_id": line.item_id})
        remaining = remaining_by_item.get(item.id, 0)
        if line.quantity > remaining:
            raise ValidationAppError(
                f"Cannot receive more than {remaining} remaining units of {item.product_name}",
                {"item_id": item.id, "remaining": remaining},
            )
        if item.product_id is None:
            raise ValidationAppError(f"{item.product_name} is not matched to a catalog product")
        product = (
            db.query(Product)
            .filter(Product.id == item.product_id)
            .with_for_update()
            .first()
        )
        if product is None:
            raise NotFoundError(f"Product for {item.product_name} was deleted")

        batch_number = line.batch_number or item.batch_number or f"RCV-{po.po_number}"
        try:
            expiry = parse_expiry(line.expiry_date or item.expiry_date, required=True)
        except ValueError as exc:
            raise ValidationAppError(f"{item.product_name}: {exc}") from exc
        cost = line.unit_cost or item.unit_cost
        remaining_by_item[item.id] = remaining - line.quantity
        reason = f"Received {po.po_number}"
        if line.notes.strip():
            reason = f"{reason}: {line.notes.strip()}"[:255]
        prepared.append((item, product, line.quantity, batch_number, expiry, cost, reason))

    for item, product, quantity, batch_number, expiry, cost, reason in prepared:
        batch = _upsert_batch(db, product, batch_number, expiry, cost)
        apply_stock_change(
            db,
            product=product,
            delta=quantity,
            movement_type=MovementType.PURCHASE,
            user=actor,
            batch=batch,
            reference_type="purchase_order",
            reference_id=po.id,
            reason=reason,
        )
        bumped = db.execute(
            update(PurchaseOrderItem)
            .where(
                PurchaseOrderItem.id == item.id,
                PurchaseOrderItem.quantity_ordered - PurchaseOrderItem.quantity_received >= quantity,
            )
            .values(quantity_received=PurchaseOrderItem.quantity_received + quantity)
        )
        if bumped.rowcount != 1:
            raise ValidationAppError(
                f"Cannot receive more than remaining units of {item.product_name}",
                {"item_id": item.id},
            )
        db.refresh(item)
        product.cost_price = cost

    fully = all(i.quantity_received >= i.quantity_ordered for i in po.items)
    any_received = any(i.quantity_received > 0 for i in po.items)
    po.status = POStatus.RECEIVED if fully else POStatus.PARTIALLY_RECEIVED if any_received else po.status
    if fully:
        po.received_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user=actor,
        action="PURCHASE_ORDER_RECEIVED",
        entity_type="purchase_order",
        entity_id=po.id,
        details={
            "po_number": po.po_number,
            "new_status": po.status.value,
            "lines": len(prepared),
            "units": sum(p[2] for p in prepared),
        },
    )


def receive_po(db: Session, po_id: str, data: ReceiveIn, actor: User) -> POOut:
    locked = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).with_for_update().first()
    if locked is None:
        raise NotFoundError("Purchase order not found")
    po = _load(db, po_id)
    _apply_receive(db, po, data, actor)
    db.commit()
    return to_po_out(_load(db, po.id))


def import_invoice(db: Session, data: ImportReceiveIn, actor: User, *, commit: bool = True) -> POOut:
    if not data.items:
        raise ValidationAppError("Nothing to import")
    for item in data.items:
        if item.product_id is None:
            raise ValidationAppError(f"{item.product_name} is not matched to inventory")
        if item.expiry_date is None or not item.batch_number:
            raise ValidationAppError(f"Batch and expiry are required for {item.product_name}")

    po = _build_po(
        db,
        POCreate(supplier_id=data.supplier_id, notes=data.notes or "Invoice import", items=data.items),
        actor,
        POStatus.APPROVED,
    )
    po.approved_by = actor.id
    po.approved_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user=actor,
        action="PURCHASE_ORDER_CREATED",
        entity_type="purchase_order",
        entity_id=po.id,
        details={"po_number": po.po_number, "new_status": po.status.value, "source": data.notes or "Invoice import"},
    )
    db.flush()
    po = _load(db, po.id)
    _apply_receive(
        db,
        po,
        ReceiveIn(
            lines=[
                ReceiveLineIn(
                    item_id=item.id,
                    quantity=item.quantity_ordered,
                    batch_number=item.batch_number,
                    expiry_date=item.expiry_date,
                    unit_cost=item.unit_cost,
                )
                for item in po.items
            ]
        ),
        actor,
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return to_po_out(_load(db, po.id))


def receive_adhoc(db: Session, data: AdhocReceiveIn, actor: User, *, commit: bool = True) -> ReceiptOut:
    """Multi-line receipt without a prior PO.

    With a supplier, an approved PO is created and received so provenance is real. Without one,
    stock is booked against a receipt reference and supplier/PO stay unrecorded (never invented).
    Every line is validated before any stock moves, so a bad line rejects the whole receipt.
    """
    if not data.items:
        raise ValidationAppError("Add at least one line to receive")

    product_ids = {line.product_id for line in data.items}
    products = {
        p.id: p
        for p in db.query(Product).filter(Product.id.in_(product_ids)).with_for_update().all()
    }
    prepared: list[tuple] = []
    seen_expiry: dict[tuple[str, str], object] = {}
    for index, line in enumerate(data.items, start=1):
        product = products.get(line.product_id)
        if product is None:
            raise ValidationAppError(f"Line {index}: medicine not found", {"line": index})
        if product.deleted_at is not None:
            raise ValidationAppError(f"Line {index}: {product.name} is archived; restore it before receiving", {"line": index})
        batch_number = line.batch_number.strip()
        if not batch_number:
            raise ValidationAppError(f"Line {index}: batch number is required for {product.name}", {"line": index})
        try:
            expiry = parse_expiry(line.expiry_date, required=True)
        except ValueError as exc:
            raise ValidationAppError(f"Line {index}: {product.name}: {exc}", {"line": index}) from exc
        existing = (
            db.query(Batch).filter(Batch.product_id == product.id, Batch.batch_number == batch_number).first()
        )
        if existing is not None and existing.expiry_date != expiry:
            raise ValidationAppError(
                f"Line {index}: batch {batch_number} of {product.name} already exists with expiry "
                f"{existing.expiry_date.isoformat()}",
                {"line": index},
            )
        if seen_expiry.setdefault((product.id, batch_number), expiry) != expiry:
            raise ValidationAppError(
                f"Line {index}: batch {batch_number} of {product.name} is entered twice with different expiries",
                {"line": index},
            )
        prepared.append((product, line, batch_number, expiry))

    supplier = None
    if data.supplier_id:
        supplier = db.get(Supplier, data.supplier_id)
        if supplier is None:
            raise ValidationAppError("Supplier not found")

    if supplier is not None:
        notes = data.notes.strip() or "Manual receiving"
        line_notes = [f"{product.name}: {line.notes.strip()}" for product, line, _, _ in prepared if line.notes.strip()]
        if line_notes:
            notes = f"{notes} | {'; '.join(line_notes)}"
        po_out = import_invoice(
            db,
            ImportReceiveIn(
                supplier_id=supplier.id,
                notes=notes,
                items=[
                    POItemIn(
                        product_id=product.id,
                        product_name=product.name,
                        quantity_ordered=line.quantity,
                        unit_cost=line.unit_cost,
                        batch_number=batch_number,
                        expiry_date=expiry,
                    )
                    for product, line, batch_number, expiry in prepared
                ],
            ),
            actor,
            commit=commit,
        )
        batches = {
            (b.product_id, b.batch_number): b
            for b in db.query(Batch).filter(Batch.product_id.in_(product_ids)).all()
        }
        return ReceiptOut(
            reference=po_out.po_number,
            purchase_order_id=po_out.id,
            po_number=po_out.po_number,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            units_received=sum(line.quantity for _, line, _, _ in prepared),
            lines=[
                ReceiptLineOut(
                    product_id=product.id,
                    product_name=product.name,
                    batch_id=batches[(product.id, batch_number)].id,
                    batch_number=batch_number,
                    expiry_date=expiry,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                )
                for product, line, batch_number, expiry in prepared
            ],
        )

    receipt_id = str(uuid4())
    reference = f"RCPT-{datetime.now(timezone.utc):%Y%m%d}-{receipt_id[:6].upper()}"
    header_note = data.notes.strip()
    out_lines: list[ReceiptLineOut] = []
    for product, line, batch_number, expiry in prepared:
        batch = _upsert_batch(db, product, batch_number, expiry, line.unit_cost)
        reason = f"Received {reference} (no PO, supplier not recorded)"
        note = line.notes.strip() or header_note
        if note:
            reason = f"{reason}: {note}"
        apply_stock_change(
            db,
            product=product,
            delta=line.quantity,
            movement_type=MovementType.PURCHASE,
            user=actor,
            batch=batch,
            reference_type="manual_receipt",
            reference_id=receipt_id,
            reason=reason[:255],
        )
        product.cost_price = line.unit_cost
        out_lines.append(
            ReceiptLineOut(
                product_id=product.id,
                product_name=product.name,
                batch_id=batch.id,
                batch_number=batch_number,
                expiry_date=expiry,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
            )
        )
    units = sum(line.quantity for _, line, _, _ in prepared)
    record_audit(
        db,
        user=actor,
        action="STOCK_RECEIVED",
        entity_type="manual_receipt",
        entity_id=receipt_id,
        details={
            "reference": reference,
            "supplier": "Not recorded",
            "purchase_order": "Not recorded",
            "lines": len(out_lines),
            "units": units,
            "notes": header_note,
            "items": [f"{l.product_name} x{l.quantity} (batch {l.batch_number})" for l in out_lines][:25],
        },
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return ReceiptOut(reference=reference, receipt_id=receipt_id, units_received=units, lines=out_lines)
