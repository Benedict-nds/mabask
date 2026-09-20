from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.responses import ValidationAppError
from app.models import Batch, MovementType, Product, StockMovement, User


def apply_stock_change(
    db: Session,
    *,
    product: Product,
    delta: int,
    movement_type: MovementType,
    user: User | None,
    batch: Batch | None = None,
    reference_type: str = "",
    reference_id: str = "",
    reason: str = "",
) -> StockMovement:
    """Apply a quantity change with an atomic UPDATE so concurrent sales cannot oversell."""
    if delta == 0:
        raise ValidationAppError("Quantity delta cannot be zero")

    product_stmt = update(Product).where(Product.id == product.id)
    if delta < 0:
        product_stmt = product_stmt.where(Product.quantity_on_hand >= -delta)
    product_stmt = product_stmt.values(quantity_on_hand=Product.quantity_on_hand + delta)
    product_result = db.execute(product_stmt)
    if product_result.rowcount != 1:
        raise ValidationAppError(
            f"Insufficient stock for {product.name}",
            {"product_id": product.id, "available": product.quantity_on_hand, "requested": abs(delta)},
        )

    if batch is not None:
        batch_stmt = update(Batch).where(Batch.id == batch.id)
        if delta < 0:
            batch_stmt = batch_stmt.where(Batch.quantity >= -delta)
        batch_stmt = batch_stmt.values(quantity=Batch.quantity + delta)
        batch_result = db.execute(batch_stmt)
        if batch_result.rowcount != 1:
            raise ValidationAppError(
                f"Insufficient batch quantity for {product.name} ({batch.batch_number})",
                {"batch_id": batch.id, "available": batch.quantity, "requested": abs(delta)},
            )
        db.refresh(batch)

    db.refresh(product)
    resulting = product.quantity_on_hand
    previous = resulting - delta
    movement = StockMovement(
        product_id=product.id,
        batch_id=batch.id if batch else None,
        quantity=delta,
        previous_quantity=previous,
        resulting_quantity=resulting,
        movement_type=movement_type,
        reference_type=reference_type,
        reference_id=reference_id,
        user_id=user.id if user else None,
        reason=reason,
    )
    db.add(movement)
    return movement
