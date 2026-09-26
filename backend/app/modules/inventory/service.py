from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.dates import parse_expiry
from app.core.responses import ConflictError, NotFoundError, ValidationAppError
from app.models import Batch, MovementType, Product, StockMovement, Supplier, User
from app.core.schemas import (
    BatchCreate,
    BatchOut,
    BatchPurchaseOrderOut,
    BatchSupplierOut,
    MovementOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    StockAdjustIn,
)
from app.modules.inventory.stock import apply_stock_change
from app.modules.inventory.traceability import BatchProvenance, resolve_batch_provenance, resolve_purchase_refs


def stock_status(qty: int, reorder: int) -> str:
    if qty <= max(int(reorder * 0.4), 0) and reorder > 0:
        return "critical"
    if qty <= reorder:
        return "low"
    return "healthy"


def _batch_out(batch: Batch, provenance: BatchProvenance | None = None) -> BatchOut:
    prov = provenance or BatchProvenance()
    supplier = None
    if prov.supplier_id and prov.supplier_name:
        supplier = BatchSupplierOut(id=prov.supplier_id, name=prov.supplier_name)
    purchase_order = None
    if prov.purchase_order_id:
        purchase_order = BatchPurchaseOrderOut(
            id=prov.purchase_order_id,
            po_number=prov.po_number or "",
        )
    return BatchOut(
        id=batch.id,
        batch_number=batch.batch_number,
        expiry_date=batch.expiry_date,
        quantity=batch.quantity,
        cost_price=batch.cost_price,
        supplier=supplier,
        purchase_order=purchase_order,
        received_at=prov.received_at,
    )


def to_product_out(
    product: Product,
    db: Session | None = None,
    provenance: dict[str, BatchProvenance] | None = None,
) -> ProductOut:
    active_batches = [b for b in product.batches if b.is_active]
    nearest = min(active_batches, key=lambda b: b.expiry_date) if active_batches else None
    if provenance is None and db is not None and active_batches:
        provenance = resolve_batch_provenance(db, [b.id for b in active_batches])
    provenance = provenance or {}
    return ProductOut(
        id=product.id,
        sku=product.sku or "",
        barcode=product.barcode or "",
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
        deleted_at=product.deleted_at,
        status=stock_status(product.quantity_on_hand, product.reorder_threshold),
        nearest_expiry=nearest.expiry_date if nearest else None,
        nearest_batch=nearest.batch_number if nearest else None,
        batches=[_batch_out(b, provenance.get(b.id)) for b in active_batches],
    )


def products_to_out(db: Session, products: list[Product]) -> list[ProductOut]:
    """Build ProductOut list with a single batch-provenance query (avoids N+1)."""
    batch_ids = [b.id for p in products for b in p.batches if b.is_active]
    provenance = resolve_batch_provenance(db, batch_ids)
    return [to_product_out(p, provenance=provenance) for p in products]


def movements_to_out(db: Session, rows: list[StockMovement]) -> list[MovementOut]:
    po_ids = [m.reference_id for m in rows if m.reference_type == "purchase_order" and m.reference_id]
    refs = resolve_purchase_refs(db, po_ids)
    items: list[MovementOut] = []
    for m in rows:
        ref = refs.get(m.reference_id) if m.reference_type == "purchase_order" else None
        items.append(
            MovementOut(
                id=m.id,
                product_id=m.product_id,
                product_name=m.product.name if m.product else None,
                batch_id=m.batch_id,
                quantity=m.quantity,
                previous_quantity=m.previous_quantity,
                resulting_quantity=m.resulting_quantity,
                movement_type=m.movement_type.value,
                reference_type=m.reference_type,
                reference_id=m.reference_id,
                reason=m.reason,
                created_at=m.created_at,
                user_id=m.user_id,
                po_number=ref.po_number if ref else None,
                supplier_id=ref.supplier_id if ref else None,
                supplier_name=ref.supplier_name if ref else None,
            )
        )
    return items


def _get(db: Session, product_id: str, *, include_archived: bool = False) -> Product:
    query = (
        db.query(Product)
        .options(joinedload(Product.supplier), joinedload(Product.batches))
        .filter(Product.id == product_id)
    )
    if not include_archived:
        query = query.filter(Product.deleted_at.is_(None))
    product = query.first()
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
    archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    sort: str = "name",
    order: str = "asc",
) -> tuple[list[Product], int]:
    query = db.query(Product).options(joinedload(Product.supplier), joinedload(Product.batches))
    if archived:
        query = query.filter(Product.deleted_at.is_not(None))
    else:
        query = query.filter(Product.deleted_at.is_(None))
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
    if status and status != "All" and not archived:
        products = [p for p in products if stock_status(p.quantity_on_hand, p.reorder_threshold) == status]

    reverse = order == "desc"
    if sort == "quantity":
        products.sort(key=lambda p: p.quantity_on_hand, reverse=reverse)
    elif sort == "expiry":
        products.sort(key=lambda p: (p.batches[0].expiry_date.isoformat() if p.batches else "9999"), reverse=reverse)
    elif sort == "archived" and archived:
        products.sort(key=lambda p: p.deleted_at or datetime.min.replace(tzinfo=timezone.utc), reverse=reverse)
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


def optional_code(value: str | None) -> str | None:
    """SKU/barcode are optional: blank means NULL so unique constraints only bind real codes."""
    cleaned = (value or "").strip()
    return cleaned or None


def category_or_default(value: str | None) -> str:
    return (value or "").strip() or "General"


def ensure_codes_available(db: Session, sku: str | None, barcode: str | None, exclude_id: str | None = None) -> None:
    for column, value, label in ((Product.sku, sku, "SKU"), (Product.barcode, barcode, "Barcode")):
        if value is None:
            continue
        query = db.query(Product.id).filter(column == value)
        if exclude_id:
            query = query.filter(Product.id != exclude_id)
        if query.first():
            raise ConflictError(f"{label} already exists")


def create_product(db: Session, data: ProductCreate, actor: User) -> ProductOut:
    if not data.name.strip():
        raise ValidationAppError("Medicine name is required")
    sku = optional_code(data.sku)
    barcode = optional_code(data.barcode)
    ensure_codes_available(db, sku, barcode)
    if data.supplier_id and db.get(Supplier, data.supplier_id) is None:
        raise ValidationAppError("Unknown supplier")

    product = Product(
        sku=sku,
        barcode=barcode,
        name=data.name.strip(),
        generic_name=data.generic_name,
        brand=data.brand,
        category=category_or_default(data.category),
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

    record_audit(
        db,
        user=actor,
        action="PRODUCT_CREATED",
        entity_type="product",
        entity_id=product.id,
        details={"sku": product.sku, "name": product.name},
    )
    db.commit()
    return to_product_out(_get(db, product.id), db)


_REQUIRED_ON_UPDATE = ("name", "cost_price", "selling_price", "reorder_threshold", "generic_name", "brand", "description", "dosage_form", "strength", "unit", "is_active")


def update_product(db: Session, product_id: str, data: ProductUpdate, actor: User) -> ProductOut:
    product = _get(db, product_id)
    payload = data.model_dump(exclude_unset=True)
    for key in _REQUIRED_ON_UPDATE:
        if key in payload and payload[key] is None:
            payload.pop(key)
    if "name" in payload:
        payload["name"] = payload["name"].strip()
        if not payload["name"]:
            raise ValidationAppError("Medicine name is required")
    if "sku" in payload:
        payload["sku"] = optional_code(payload["sku"])
    if "barcode" in payload:
        payload["barcode"] = optional_code(payload["barcode"])
    if "category" in payload:
        payload["category"] = category_or_default(payload["category"])
    ensure_codes_available(
        db,
        payload.get("sku") if payload.get("sku") != product.sku else None,
        payload.get("barcode") if payload.get("barcode") != product.barcode else None,
        exclude_id=product.id,
    )
    for key, value in payload.items():
        setattr(product, key, value)
    action = "PRODUCT_DEACTIVATED" if payload.get("is_active") is False else "PRODUCT_UPDATED"
    record_audit(db, user=actor, action=action, entity_type="product", entity_id=product.id)
    db.commit()
    return to_product_out(_get(db, product.id), db)


def deactivate_product(db: Session, product_id: str, actor: User) -> ProductOut:
    """Legacy soft-deactivate via is_active=False. Does not archive (deleted_at stays null)."""
    return update_product(db, product_id, ProductUpdate(is_active=False), actor)


def archive_product(db: Session, product_id: str, actor: User) -> ProductOut:
    """Soft-archive: set deleted_at. Preserves is_active, stock, batches, and history."""
    product = _get(db, product_id, include_archived=True)
    if product.deleted_at is not None:
        raise ConflictError("Product is already archived")
    product.deleted_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user=actor,
        action="PRODUCT_ARCHIVED",
        entity_type="product",
        entity_id=product.id,
        details={"sku": product.sku, "name": product.name},
    )
    db.commit()
    return to_product_out(_get(db, product.id, include_archived=True), db)


def restore_product(db: Session, product_id: str, actor: User) -> ProductOut:
    """Restore archived product to the catalog. Does not create stock or alter history."""
    product = _get(db, product_id, include_archived=True)
    if product.deleted_at is None:
        raise ConflictError("Product is not archived")
    product.deleted_at = None
    record_audit(
        db,
        user=actor,
        action="PRODUCT_RESTORED",
        entity_type="product",
        entity_id=product.id,
        details={"sku": product.sku, "name": product.name, "is_active": product.is_active},
    )
    db.commit()
    return to_product_out(_get(db, product.id), db)


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
    return to_product_out(_get(db, product.id), db)


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
    return to_product_out(_get(db, product.id), db)


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
