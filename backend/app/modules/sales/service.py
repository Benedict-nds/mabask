from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.responses import ConflictError, NotFoundError, ValidationAppError
from app.models import Batch, Customer, MovementType, PaymentMethod, Product, Sale, SaleItem, User
from app.core.schemas import SaleCreate, SaleItemOut, SaleOut
from app.modules.sales.customers import get_or_create_walkin
from app.modules.sales.numbering import next_sale_number
from app.modules.settings.service import get_tax_rate
from app.modules.inventory.stock import apply_stock_change

TWOPLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def to_sale_out(sale: Sale) -> SaleOut:
    items = []
    for item in sale.items:
        items.append(
            SaleItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                barcode=item.product.barcode if item.product else None,
                quantity=item.quantity,
                quantity_returned=item.quantity_returned,
                unit_price=item.unit_price,
                line_total=item.line_total,
                returnable=item.quantity - item.quantity_returned,
            )
        )
    return SaleOut(
        id=sale.id,
        sale_number=sale.sale_number,
        customer_id=sale.customer_id,
        customer_name=sale.customer.name if sale.customer else None,
        cashier_id=sale.cashier_id,
        cashier_name=sale.cashier.full_name if sale.cashier else None,
        status=sale.status.value,
        subtotal=sale.subtotal,
        discount_percent=sale.discount_percent,
        discount_amount=sale.discount_amount,
        tax_rate=sale.tax_rate,
        tax_amount=sale.tax_amount,
        total=sale.total,
        payment_method=sale.payment_method.value,
        amount_tendered=sale.amount_tendered,
        change_due=sale.change_due,
        created_at=sale.created_at,
        items=items,
    )


def _load(db: Session, sale_id: str) -> Sale:
    sale = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.customer),
            joinedload(Sale.cashier),
        )
        .filter(Sale.id == sale_id)
        .first()
    )
    if sale is None:
        raise NotFoundError("Sale not found")
    return sale


def list_sales(db: Session, limit: int = 50, offset: int = 0, q: str | None = None) -> tuple[list[Sale], int]:
    query = db.query(Sale).options(
        joinedload(Sale.items).joinedload(SaleItem.product),
        joinedload(Sale.customer),
        joinedload(Sale.cashier),
    )
    if q:
        query = query.filter(Sale.sale_number.ilike(f"%{q}%"))
    total = query.count()
    rows = query.order_by(Sale.created_at.desc()).offset(offset).limit(limit).all()
    return rows, total


def get_sale(db: Session, sale_id: str) -> SaleOut:
    return to_sale_out(_load(db, sale_id))


def _fefo_batches(db: Session, product: Product, needed: int) -> list[tuple[Batch, int]]:
    batches = (
        db.query(Batch)
        .filter(
            Batch.product_id == product.id,
            Batch.is_active.is_(True),
            Batch.quantity > 0,
            Batch.expiry_date >= date.today(),
        )
        .order_by(Batch.expiry_date.asc(), Batch.id.asc())
        .with_for_update()
        .all()
    )
    remaining = needed
    allocated: list[tuple[Batch, int]] = []
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.quantity, remaining)
        allocated.append((batch, take))
        remaining -= take
    if remaining > 0:
        raise ValidationAppError(
            f"Insufficient stock for {product.name}",
            {"product_id": product.id, "available": product.quantity_on_hand, "requested": needed},
        )
    return allocated


def complete_sale(db: Session, data: SaleCreate, actor: User) -> SaleOut:
    existing = db.query(Sale).filter(Sale.idempotency_key == data.idempotency_key).first()
    if existing:
        return to_sale_out(_load(db, existing.id))
    if not data.items:
        raise ValidationAppError("Cart is empty")
    if data.discount_percent < 0 or data.discount_percent > 100:
        raise ValidationAppError("Discount must be between 0 and 100")
    if data.tax_rate is not None and (data.tax_rate < 0 or data.tax_rate > 100):
        raise ValidationAppError("Tax must be between 0 and 100")
    try:
        method = PaymentMethod(data.payment_method)
    except ValueError as exc:
        raise ValidationAppError("Invalid payment method") from exc

    # collapse duplicate product lines
    qty_by_product: dict[str, int] = {}
    for line in data.items:
        qty_by_product[line.product_id] = qty_by_product.get(line.product_id, 0) + line.quantity

    tax_rate = Decimal(data.tax_rate) if data.tax_rate is not None else get_tax_rate(db)
    subtotal = Decimal("0")
    allocations: list[tuple[Product, Batch, int, Decimal]] = []

    for product_id in sorted(qty_by_product):
        qty = qty_by_product[product_id]
        product = (
            db.query(Product)
            .filter(Product.id == product_id, Product.deleted_at.is_(None))
            .with_for_update()
            .first()
        )
        if product is None or not product.is_active:
            raise NotFoundError("One or more products are no longer available")
        if qty < 1:
            raise ValidationAppError("Quantity must be at least 1")
        for batch, take in _fefo_batches(db, product, qty):
            unit = Decimal(product.selling_price)
            allocations.append((product, batch, take, unit))
            subtotal += unit * take

    subtotal = money(subtotal)
    discount_amount = money(subtotal * Decimal(data.discount_percent) / Decimal("100"))
    taxable = subtotal - discount_amount
    tax_amount = money(taxable * tax_rate / Decimal("100"))
    total = money(taxable + tax_amount)

    tendered = Decimal(data.amount_tendered) if data.amount_tendered is not None else total
    if method == PaymentMethod.CASH and tendered < total:
        raise ValidationAppError("Cash tendered is less than the total")
    change = money(max(tendered - total, Decimal("0"))) if method == PaymentMethod.CASH else Decimal("0")

    customer_id = data.customer_id
    if customer_id is None and data.customer_name:
        customer_id = get_or_create_walkin(db, data.customer_name).id

    sale = Sale(
        sale_number=next_sale_number(db),
        customer_id=customer_id,
        cashier_id=actor.id,
        subtotal=subtotal,
        discount_percent=data.discount_percent,
        discount_amount=discount_amount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total=total,
        payment_method=method,
        amount_tendered=tendered,
        change_due=change,
        idempotency_key=data.idempotency_key,
        notes=data.notes,
    )
    db.add(sale)
    db.flush()

    for product, batch, take, unit in allocations:
        apply_stock_change(
            db,
            product=product,
            delta=-take,
            movement_type=MovementType.SALE,
            user=actor,
            batch=batch,
            reference_type="sale",
            reference_id=sale.id,
            reason=f"Sale {sale.sale_number}",
        )
        db.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                batch_id=batch.id,
                quantity=take,
                unit_price=unit,
                line_total=money(unit * take),
            )
        )

    record_audit(
        db,
        user=actor,
        action="SALE_COMPLETED",
        entity_type="sale",
        entity_id=sale.id,
        details={"sale_number": sale.sale_number, "total": str(total)},
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        replay = db.query(Sale).filter(Sale.idempotency_key == data.idempotency_key).first()
        if replay:
            return to_sale_out(_load(db, replay.id))
        raise
    return to_sale_out(_load(db, sale.id))


def customer_sales(db: Session, customer_id: str) -> list[SaleOut]:
    if db.get(Customer, customer_id) is None:
        raise NotFoundError("Customer not found")
    rows = (
        db.query(Sale)
        .options(joinedload(Sale.items).joinedload(SaleItem.product), joinedload(Sale.customer), joinedload(Sale.cashier))
        .filter(Sale.customer_id == customer_id)
        .order_by(Sale.created_at.desc())
        .all()
    )
    return [to_sale_out(s) for s in rows]
