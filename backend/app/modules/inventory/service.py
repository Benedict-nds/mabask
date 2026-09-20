from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.dates import parse_expiry
from app.core.responses import ConflictError, NotFoundError, ValidationAppError
from app.models import Batch, MovementType, Product, StockMovement, Supplier, User
from app.core.schemas import BatchCreate, ProductCreate, ProductOut, ProductUpdate, StockAdjustIn
from app.modules.inventory.stock import apply_stock_change


def stock_status(qty: int, reorder: int) -> str:
    if qty <= max(int(reorder * 0.4), 0) and reorder > 0:
        return "critical"
    if qty <= reorder:
        return "low"
    return "healthy"


def to_product_out(product: Product) -> ProductOut:
    active_batches = [b for b in product.batches if b.is_active]
    nearest = min(active_batches, key=lambda b: b.expiry_date) if active_batches else None
    return ProductOut(
        id=product.id,
        sku=product.sku,
        barcode=product.barcode,
        name=product.name,
        generic_name=product.generic_name,
        brand=product.brand,
        category=product.category,
        description=product.description,
        dosage_form=product.dosage_form,
        strength=product.strength,
        unit=product.unit,
        cost_price=product.cost_price,
        selling_price=product.selling_price,
        quantity_on_hand=product.quantity_on_hand,
        reorder_threshold=product.reorder_threshold,
        supplier_id=product.supplier_id,
        supplier_name=product.supplier.name if product.supplier else None,
        is_active=product.is_active,
        status=stock_status(product.quantity_on_hand, product.reorder_threshold),
        nearest_expiry=nearest.expiry_date if nearest else None,
        nearest_batch=nearest.batch_number if nearest else None,
        batches=active_batches,
    )


def _get(db: Session, product_id: str) -> Product:
    product = (
        db.query(Product)
        .options(joinedload(Product.supplier), joinedload(Product.batches))
        .filter(Product.id == product_id, Product.deleted_at.is_(None))
        .first()
    )
    if product is None:
        raise NotFoundError("Product not found")
    return product


def list_products(
    db: Session,
    *,
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    supplier_id: str | None = None,
    barcode: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "name",
    order: str = "asc",
) -> tuple[list[Product], int]:
    query = db.query(Product).options(joinedload(Product.supplier), joinedload(Product.batches)).filter(
        Product.deleted_at.is_(None)
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Product.name.ilike(like),
                Product.brand.ilike(like),
                Product.sku.ilike(like),
                Product.barcode.ilike(like),
                Product.generic_name.ilike(like),
            )
        )
    if category and category != "All":
        query = query.filter(Product.category == category)
    if supplier_id:
        query = query.filter(Product.supplier_id == supplier_id)
    if barcode:
        query = query.filter(Product.barcode == barcode)

    products = query.all()
    if status and status != "All":
        products = [p for p in products if stock_status(p.quantity_on_hand, p.reorder_threshold) == status]

    reverse = order == "desc"
    if sort == "quantity":
        products.sort(key=lambda p: p.quantity_on_hand, reverse=reverse)
    elif sort == "expiry":
        products.sort(key=lambda p: (p.batches[0].expiry_date.isoformat() if p.batches else "9999"), reverse=reverse)
    else:
        products.sort(key=lambda p: p.name.lower(), reverse=reverse)

    total = len(products)
    return products[offset : offset + limit], total


def get_by_barcode(db: Session, code: str) -> Product:
    product = (
        db.query(Product)
        .options(joinedload(Product.supplier), joinedload(Product.batches))
        .filter(Product.barcode == code, Product.deleted_at.is_(None), Product.is_active.is_(True))
        .first()
    )
    if product is None:
        raise NotFoundError("No product matches that barcode")
    return product


def create_product(db: Session, data: ProductCreate, actor: User) -> ProductOut:
    if db.query(Product).filter(Product.sku == data.sku, Product.deleted_at.is_(None)).first():
        raise ConflictError("SKU already exists")
    if db.query(Product).filter(Product.barcode == data.barcode, Product.deleted_at.is_(None)).first():
        raise ConflictError("Barcode already exists")
    if data.supplier_id and db.get(Supplier, data.supplier_id) is None:
        raise ValidationAppError("Unknown supplier")

    product = Product(
        sku=data.sku,
        barcode=data.barcode,
        name=data.name,
        generic_name=data.generic_name,
        brand=data.brand,
        category=data.category,
        description=data.description,
        dosage_form=data.dosage_form,
        strength=data.strength,
        unit=data.unit,
        cost_price=data.cost_price,
        selling_price=data.selling_price,
        reorder_threshold=data.reorder_threshold,
        supplier_id=data.supplier_id,
        is_active=data.is_active,
        quantity_on_hand=0,
    )
    db.add(product)
    db.flush()

    if data.initial_quantity:
        if not data.batch_number or not data.expiry_date:
            raise ValidationAppError("Batch number and expiry are required when seeding stock")
        batch = Batch(
            product_id=product.id,
            batch_number=data.batch_number,
            expiry_date=parse_expiry(data.expiry_date, required=True),
            quantity=0,
            cost_price=data.cost_price,
        )
        db.add(batch)
        db.flush()
        apply_stock_change(
            db,
            product=product,
            delta=data.initial_quantity,
            movement_type=MovementType.ADJUSTMENT,
            user=actor,
            batch=batch,
            reference_type="product",
            reference_id=product.id,
            reason="Initial stock",
        )

    record_audit(db, user=actor, action="PRODUCT_CREATED", entity_type="product", entity_id=product.id, details={"sku": product.sku})
    db.commit()
    return to_product_out(_get(db, product.id))


def update_product(db: Session, product_id: str, data: ProductUpdate, actor: User) -> ProductOut:
    product = _get(db, product_id)
    payload = data.model_dump(exclude_unset=True)
    if "sku" in payload and payload["sku"] != product.sku:
        if db.query(Product).filter(Product.sku == payload["sku"], Product.id != product.id, Product.deleted_at.is_(None)).first():
            raise ConflictError("SKU already exists")
    if "barcode" in payload and payload["barcode"] != product.barcode:
        if db.query(Product).filter(Product.barcode == payload["barcode"], Product.id != product.id, Product.deleted_at.is_(None)).first():
            raise ConflictError("Barcode already exists")
    for key, value in payload.items():
        setattr(product, key, value)
    action = "PRODUCT_DEACTIVATED" if payload.get("is_active") is False else "PRODUCT_UPDATED"
    record_audit(db, user=actor, action=action, entity_type="product", entity_id=product.id)
    db.commit()
    return to_product_out(_get(db, product.id))


def deactivate_product(db: Session, product_id: str, actor: User) -> ProductOut:
    return update_product(db, product_id, ProductUpdate(is_active=False), actor)


def add_batch(db: Session, product_id: str, data: BatchCreate, actor: User) -> ProductOut:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.deleted_at.is_(None))
        .with_for_update()
        .first()
    )
    if product is None:
        raise NotFoundError("Product not found")
    existing = (
        db.query(Batch)
        .filter(Batch.product_id == product.id, Batch.batch_number == data.batch_number)
        .first()
    )
    if existing:
        raise ConflictError("That batch number already exists for this product")
    batch = Batch(
        product_id=product.id,
        batch_number=data.batch_number,
        expiry_date=parse_expiry(data.expiry_date, required=True),
        quantity=0,
        cost_price=data.cost_price if data.cost_price is not None else product.cost_price,
    )
    db.add(batch)
    db.flush()
    if data.quantity:
        apply_stock_change(
            db,
            product=product,
            delta=data.quantity,
            movement_type=MovementType.ADJUSTMENT,
            user=actor,
            batch=batch,
            reference_type="batch",
            reference_id=batch.id,
            reason="Opening batch quantity",
        )
    record_audit(
        db,
        user=actor,
        action="BATCH_CREATED",
        entity_type="batch",
        entity_id=batch.id,
        details={"product_id": product.id, "batch_number": batch.batch_number, "quantity": data.quantity},
    )
    db.commit()
    return to_product_out(_get(db, product.id))


def adjust_stock(db: Session, product_id: str, data: StockAdjustIn, actor: User) -> ProductOut:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.deleted_at.is_(None))
        .with_for_update()
        .first()
    )
    if product is None:
        raise NotFoundError("Product not found")
    try:
        movement_type = MovementType(data.movement_type)
    except ValueError as exc:
        raise ValidationAppError("Invalid movement type") from exc
    if movement_type not in {MovementType.ADJUSTMENT, MovementType.DAMAGE, MovementType.EXPIRY, MovementType.TRANSFER}:
        raise ValidationAppError("This endpoint only accepts ADJUSTMENT, DAMAGE, EXPIRY, or TRANSFER")
    if not data.reason.strip():
        raise ValidationAppError("A reason is required for stock adjustments")

    batch = None
    if data.batch_id:
        batch = (
            db.query(Batch)
            .filter(Batch.id == data.batch_id, Batch.product_id == product.id)
            .with_for_update()
            .first()
        )
        if batch is None:
            raise NotFoundError("Batch not found")
    elif data.quantity_delta > 0:
        raise ValidationAppError("Positive adjustments must target a batch")

    apply_stock_change(
        db,
        product=product,
        delta=data.quantity_delta,
        movement_type=movement_type,
        user=actor,
        batch=batch,
        reference_type="adjustment",
        reference_id=product.id,
        reason=data.reason,
    )
    record_audit(
        db,
        user=actor,
        action="STOCK_ADJUSTED",
        entity_type="product",
        entity_id=product.id,
        details={"delta": data.quantity_delta, "reason": data.reason, "type": movement_type.value},
    )
    db.commit()
    return to_product_out(_get(db, product.id))


def list_movements(db: Session, product_id: str | None, limit: int, offset: int) -> tuple[list[StockMovement], int]:
    query = db.query(StockMovement).options(joinedload(StockMovement.product)).order_by(StockMovement.created_at.desc())
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return rows, total


def status_counts(db: Session) -> dict[str, int]:
    products = db.query(Product).filter(Product.deleted_at.is_(None), Product.is_active.is_(True)).all()
    counts = {"total": len(products), "healthy": 0, "low": 0, "critical": 0}
    for product in products:
        counts[stock_status(product.quantity_on_hand, product.reorder_threshold)] += 1
    return counts


def low_stock(db: Session) -> list[Product]:
    products = (
        db.query(Product)
        .options(joinedload(Product.supplier), joinedload(Product.batches))
        .filter(Product.deleted_at.is_(None), Product.is_active.is_(True))
        .all()
    )
    return [p for p in products if stock_status(p.quantity_on_hand, p.reorder_threshold) in {"low", "critical"}]


def expiring(db: Session, days: int = 30) -> list[Batch]:
    cutoff = date.today() + timedelta(days=days)
    return (
        db.query(Batch)
        .options(joinedload(Batch.product))
        .filter(Batch.is_active.is_(True), Batch.quantity > 0, Batch.expiry_date <= cutoff)
        .order_by(Batch.expiry_date)
        .all()
    )


def categories(db: Session) -> list[str]:
    rows = (
        db.query(Product.category)
        .filter(Product.deleted_at.is_(None))
        .distinct()
        .order_by(Product.category)
        .all()
    )
    return [r[0] for r in rows]
