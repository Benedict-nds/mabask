from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.responses import NotFoundError, ValidationAppError
from app.models import Batch, MovementType, Product, Return, ReturnItem, Sale, SaleItem, SaleStatus, User
from app.core.schemas import ReturnCreate, ReturnOut
from app.modules.sales.numbering import next_return_number
from app.modules.sales.service import money
from app.modules.inventory.stock import apply_stock_change


def process_return(db: Session, data: ReturnCreate, actor: User) -> ReturnOut:
    if db.query(Sale).filter(Sale.id == data.sale_id).with_for_update().first() is None:
        raise NotFoundError("Sale not found")
    sale = (
        db.query(Sale)
        .options(joinedload(Sale.items).joinedload(SaleItem.product))
        .filter(Sale.id == data.sale_id)
        .first()
    )
    if sale is None:
        raise NotFoundError("Sale not found")
    if not data.items:
        raise ValidationAppError("Select at least one item to return")
    if not data.reason.strip():
        raise ValidationAppError("A return reason is required")

    items_by_id = {item.id: item for item in sale.items}
    refund = Decimal("0")
    prepared: list[tuple[SaleItem, int]] = []

    for line in data.items:
        item = items_by_id.get(line.sale_item_id)
        if item is None:
            raise ValidationAppError("Sale item does not belong to this transaction")
        returnable = item.quantity - item.quantity_returned
        if line.quantity > returnable:
            raise ValidationAppError(
                f"Cannot return more than {returnable} units of {item.product.name if item.product else 'item'}",
                {"sale_item_id": item.id, "returnable": returnable},
            )
        prepared.append((item, line.quantity))
        refund += Decimal(item.unit_price) * line.quantity

    # apply discount/tax proportionally to the original sale
    if sale.subtotal > 0:
        share = refund / sale.subtotal
        refund = money(refund - (sale.discount_amount * share) + (sale.tax_amount * share))
    else:
        refund = money(refund)

    record = Return(
        return_number=next_return_number(db),
        sale_id=sale.id,
        cashier_id=actor.id,
        reason=data.reason,
        refund_amount=refund,
        restock=data.restock,
    )
    db.add(record)
    db.flush()

    for item, qty in prepared:
        item.quantity_returned += qty
        db.add(
            ReturnItem(
                return_id=record.id,
                sale_item_id=item.id,
                product_id=item.product_id,
                batch_id=item.batch_id,
                quantity=qty,
                unit_price=item.unit_price,
            )
        )
        if data.restock:
            product = db.query(Product).filter(Product.id == item.product_id).with_for_update().first()
            batch = (
                db.query(Batch).filter(Batch.id == item.batch_id).with_for_update().first()
                if item.batch_id
                else None
            )
            if product is None:
                raise NotFoundError("Product no longer exists")
            apply_stock_change(
                db,
                product=product,
                delta=qty,
                movement_type=MovementType.RETURN,
                user=actor,
                batch=batch,
                reference_type="return",
                reference_id=record.id,
                reason=data.reason,
            )

    total_sold = sum(i.quantity for i in sale.items)
    total_returned = sum(i.quantity_returned for i in sale.items)
    sale.status = SaleStatus.REFUNDED if total_returned >= total_sold else SaleStatus.PARTIALLY_REFUNDED

    record_audit(
        db,
        user=actor,
        action="SALE_REFUNDED",
        entity_type="return",
        entity_id=record.id,
        details={"sale_id": sale.id, "amount": str(refund)},
    )
    db.commit()
    db.refresh(record)
    return ReturnOut(
        id=record.id,
        return_number=record.return_number,
        sale_id=record.sale_id,
        reason=record.reason,
        refund_amount=record.refund_amount,
        restock=record.restock,
        created_at=record.created_at,
    )
