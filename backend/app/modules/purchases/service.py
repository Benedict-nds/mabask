from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.dates import parse_expiry
from app.core.responses import NotFoundError, ValidationAppError
from app.models import Batch, MovementType, POStatus, Product, PurchaseOrder, PurchaseOrderItem, User
from app.core.schemas import ImportReceiveIn, POCreate, POItemIn, POOut, ReceiveIn, ReceiveLineIn
from app.modules.sales.numbering import next_po_number
from app.modules.inventory.stock import apply_stock_change


def to_po_out(po: PurchaseOrder) -> POOut:
    return POOut(
        id=po.id,
        po_number=po.po_number,
        supplier_id=po.supplier_id,
        supplier_name=po.supplier.name if po.supplier else None,
        status=po.status.value,
        notes=po.notes,
        subtotal=po.subtotal,
        total=po.total,
        created_by=po.created_by,
        approved_by=po.approved_by,
        created_at=po.created_at,
        items=po.items,
    )


def _load(db: Session, po_id: str) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.items), joinedload(PurchaseOrder.supplier))
        .filter(PurchaseOrder.id == po_id)
        .first()
    )
    if po is None:
        raise NotFoundError("Purchase order not found")
    return po


def _totals(items: list[POItemIn] | list[PurchaseOrderItem]) -> Decimal:
    total = Decimal("0")
    for item in items:
        total += Decimal(item.quantity_ordered) * Decimal(item.unit_cost)
    return total.quantize(Decimal("0.01"))


def list_pos(db: Session, status: str | None = None, supplier_id: str | None = None) -> list[POOut]:
    query = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.items), joinedload(PurchaseOrder.supplier))
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
    record_audit(db, user=actor, action="PURCHASE_ORDER_CREATED", entity_type="purchase_order", entity_id=po.id)
    db.commit()
    return to_po_out(_load(db, po.id))


def update_draft(db: Session, po_id: str, data: POCreate, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status != POStatus.DRAFT:
        raise ValidationAppError("Only draft purchase orders can be edited")
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
    db.commit()
    return to_po_out(_load(db, po.id))


def submit_po(db: Session, po_id: str, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status != POStatus.DRAFT:
        raise ValidationAppError("Only drafts can be submitted")
    po.status = POStatus.SUBMITTED
    po.submitted_at = datetime.now(timezone.utc)
    record_audit(db, user=actor, action="PURCHASE_ORDER_SUBMITTED", entity_type="purchase_order", entity_id=po.id)
    db.commit()
    return to_po_out(po)


def approve_po(db: Session, po_id: str, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status not in {POStatus.DRAFT, POStatus.SUBMITTED}:
        raise ValidationAppError("This purchase order cannot be approved")
    po.status = POStatus.APPROVED
    po.approved_by = actor.id
    po.approved_at = datetime.now(timezone.utc)
    record_audit(db, user=actor, action="PURCHASE_ORDER_APPROVED", entity_type="purchase_order", entity_id=po.id)
    db.commit()
    return to_po_out(po)


def cancel_po(db: Session, po_id: str, actor: User) -> POOut:
    po = _load(db, po_id)
    if po.status in {POStatus.RECEIVED, POStatus.CANCELLED}:
        raise ValidationAppError("This purchase order cannot be cancelled")
    po.status = POStatus.CANCELLED
    po.cancelled_at = datetime.now(timezone.utc)
    record_audit(db, user=actor, action="PURCHASE_ORDER_CANCELLED", entity_type="purchase_order", entity_id=po.id)
    db.commit()
    return to_po_out(po)


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
    for line in data.lines:
        item = items_by_id.get(line.item_id)
        if item is None:
            raise ValidationAppError("Unknown purchase order line", {"item_id": line.item_id})
        remaining = item.quantity_ordered - item.quantity_received
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
        batch = _upsert_batch(db, product, batch_number, expiry, cost)
        apply_stock_change(
            db,
            product=product,
            delta=line.quantity,
            movement_type=MovementType.PURCHASE,
            user=actor,
            batch=batch,
            reference_type="purchase_order",
            reference_id=po.id,
            reason=f"Received {po.po_number}",
        )
        bumped = db.execute(
            update(PurchaseOrderItem)
            .where(
                PurchaseOrderItem.id == item.id,
                PurchaseOrderItem.quantity_ordered - PurchaseOrderItem.quantity_received >= line.quantity,
            )
            .values(quantity_received=PurchaseOrderItem.quantity_received + line.quantity)
        )
        if bumped.rowcount != 1:
            raise ValidationAppError(
                f"Cannot receive more than {remaining} remaining units of {item.product_name}",
                {"item_id": item.id, "remaining": remaining},
            )
        db.refresh(item)
        product.cost_price = cost

    fully = all(i.quantity_received >= i.quantity_ordered for i in po.items)
    any_received = any(i.quantity_received > 0 for i in po.items)
    po.status = POStatus.RECEIVED if fully else POStatus.PARTIALLY_RECEIVED if any_received else po.status
    if fully:
        po.received_at = datetime.now(timezone.utc)
    record_audit(db, user=actor, action="PURCHASE_ORDER_RECEIVED", entity_type="purchase_order", entity_id=po.id)


def receive_po(db: Session, po_id: str, data: ReceiveIn, actor: User) -> POOut:
    locked = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).with_for_update().first()
    if locked is None:
        raise NotFoundError("Purchase order not found")
    po = _load(db, po_id)
    _apply_receive(db, po, data, actor)
    db.commit()
    return to_po_out(_load(db, po.id))


def import_invoice(db: Session, data: ImportReceiveIn, actor: User) -> POOut:
    if not data.items:
        raise ValidationAppError("Nothing to import")
    for item in data.items:
        if item.product_id is None:
            raise ValidationAppError(f"{item.product_name} is not matched to inventory")
        if item.expiry_date is None or not item.batch_number:
            raise ValidationAppError(f"Batch and expiry are required for {item.product_name}")

    po = _build_po(db, POCreate(supplier_id=data.supplier_id, notes="Invoice import", items=data.items), actor, POStatus.APPROVED)
    po.approved_by = actor.id
    po.approved_at = datetime.now(timezone.utc)
    record_audit(db, user=actor, action="PURCHASE_ORDER_CREATED", entity_type="purchase_order", entity_id=po.id)
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
    db.commit()
    return to_po_out(_load(db, po.id))
