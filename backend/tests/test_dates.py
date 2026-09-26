from datetime import date

from app.core.dates import parse_expiry
from app.core.schemas import BatchCreate, ProductCreate


def test_parse_zero_padded_year():
    assert parse_expiry("0027-09-16") == date(2027, 9, 16)


def test_parse_ghana_short_year():
    assert parse_expiry("15/09/27") == date(2027, 9, 15)
    assert parse_expiry("15/09/2027") == date(2027, 9, 15)
    assert parse_expiry("15.09.27") == date(2027, 9, 15)


def test_parse_iso_and_short_iso():
    assert parse_expiry("2027-09-16") == date(2027, 9, 16)
    assert parse_expiry("27-09-16") == date(2027, 9, 16)


def test_parse_date_object_with_ancient_year():
    assert parse_expiry(date(27, 9, 16)) == date(2027, 9, 16)


def test_schema_normalizes_short_years():
    batch = BatchCreate(batch_number="RCV-1", expiry_date="0027-09-16", quantity=1)
    assert batch.expiry_date == date(2027, 9, 16)
    product = ProductCreate(
        sku="MD-EXP",
        barcode="111",
        name="Test",
        category="Antibiotics",
        cost_price="0.50",
        selling_price="1.00",
        reorder_threshold=0,
        expiry_date="15/09/27",
        batch_number="B1",
        initial_quantity=1,
    )
    assert product.expiry_date == date(2027, 9, 15)


def test_repair_rewrites_ancient_years(db):
    from decimal import Decimal

    from app.core.dates import repair_short_year_expiries
    from app.models import Batch, Product

    product = db.query(Product).first()
    row = Batch(
        product_id=product.id,
        batch_number="ANCIENT",
        expiry_date=date(27, 9, 16),
        quantity=1,
        cost_price=Decimal("0.18"),
    )
    db.add(row)
    db.commit()
    assert repair_short_year_expiries(db) >= 1
    db.refresh(row)
    assert row.expiry_date == date(2027, 9, 16)
