import pytest

from app.core.responses import ValidationAppError
from app.models import Batch, MovementType, Product
from app.modules.inventory.stock import apply_stock_change


def test_atomic_deductions_cannot_oversell(db):
    product = db.query(Product).filter(Product.name == "Amoxicillin 500mg").one()
    batch = db.query(Batch).filter(Batch.product_id == product.id).first()
    starting = product.quantity_on_hand
    assert starting == 100

    apply_stock_change(
        db,
        product=product,
        delta=-80,
        movement_type=MovementType.SALE,
        user=None,
        batch=batch,
        reason="first deduction",
    )
    db.flush()
    db.refresh(product)
    assert product.quantity_on_hand == 20

    with pytest.raises(ValidationAppError, match="Insufficient stock"):
        apply_stock_change(
            db,
            product=product,
            delta=-80,
            movement_type=MovementType.SALE,
            user=None,
            batch=batch,
            reason="second deduction",
        )
    db.refresh(product)
    db.refresh(batch)
    assert product.quantity_on_hand == 20
    assert batch.quantity == 20
