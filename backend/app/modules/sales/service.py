from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
import csv

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.responses import NotFoundError, ValidationAppError
from app.models import (
    Batch,
    Customer,
    MovementType,
    PaymentMethod,
    Product,
    Return,
    ReturnItem,
    Sale,
    SaleCorrectionRequest,
    SaleItem,
    SaleStatus,
    StockMovement,
    User,
    CorrectionStatus,
)
from app.core.schemas import (
    SaleCorrectionLinkOut,
    SaleCreate,
    SaleItemOut,
    SaleMovementOut,
    SaleOut,
    SaleReturnItemOut,
    SaleReturnSummaryOut,
)
from app.modules.sales.customers import get_or_create_walkin
from app.modules.sales.numbering import next_sale_number
from app.modules.settings.service import get_tax_rate
from app.modules.inventory.stock import apply_stock_change
from app.modules.inventory.traceability import resolve_batch_provenance

TWOPLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _link_out(row: SaleCorrectionRequest, *, original: Sale | None, corrected: Sale | None) -> SaleCorrectionLinkOut:
    ret = row.return_record
    refund = ret.refund_amount if ret else None
    financial_difference = None
    if refund is not None and corrected is not None:
        financial_difference = money(Decimal(corrected.total) - Decimal(refund))
    return SaleCorrectionLinkOut(
        request_id=row.id,
        reference=f"CR-{row.id.replace('-', '')[:8].upper()}",
        status=row.status.value,
        corrected_sale_id=row.corrected_sale_id,
        corrected_sale_number=corrected.sale_number if corrected else None,
        original_sale_id=row.sale_id,
        original_sale_number=original.sale_number if original else None,
        financial_difference=financial_difference,
        return_id=row.return_id,
        return_number=ret.return_number if ret else None,
        refund_amount=refund,
        reason=row.reason,
        requested_by_name=row.requester.full_name if row.requester else None,
        requested_at=row.created_at,
        reviewed_by_name=row.reviewer.full_name if row.reviewer else None,
        reviewed_at=row.reviewed_at,
        review_note=row.review_note or "",
    )


def _correction_links_bulk(
    db: Session, sales: list[Sale]
) -> dict[str, tuple[SaleCorrectionLinkOut | None, SaleCorrectionLinkOut | None]]:
    """Correction linkage for many sales in two queries (latest request per original sale)."""
    ids = [s.id for s in sales]
    if not ids:
        return {}
    by_id = {s.id: s for s in sales}
    options = (
        joinedload(SaleCorrectionRequest.sale),
        joinedload(SaleCorrectionRequest.corrected_sale),
        joinedload(SaleCorrectionRequest.return_record),
        joinedload(SaleCorrectionRequest.requester),
        joinedload(SaleCorrectionRequest.reviewer),
    )
    as_original: dict[str, SaleCorrectionLinkOut] = {}
    for row in (
        db.query(SaleCorrectionRequest)
        .options(*options)
        .filter(SaleCorrectionRequest.sale_id.in_(ids))
        .order_by(SaleCorrectionRequest.created_at.desc())
        .all()
    ):
        if row.sale_id in as_original:
            continue
        as_original[row.sale_id] = _link_out(row, original=by_id[row.sale_id], corrected=row.corrected_sale)
    as_corrected: dict[str, SaleCorrectionLinkOut] = {}
    for row in (
        db.query(SaleCorrectionRequest)
        .options(*options)
        .filter(SaleCorrectionRequest.corrected_sale_id.in_(ids))
        .all()
    ):
        as_corrected[row.corrected_sale_id] = _link_out(row, original=row.sale, corrected=by_id[row.corrected_sale_id])
    return {sid: (as_original.get(sid), as_corrected.get(sid)) for sid in ids}


def _correction_links(db: Session, sale: Sale) -> tuple[SaleCorrectionLinkOut | None, SaleCorrectionLinkOut | None]:
    return _correction_links_bulk(db, [sale])[sale.id]


def _sale_returns(db: Session, sale_id: str) -> list[SaleReturnSummaryOut]:
    rows = (
        db.query(Return)
        .options(
            joinedload(Return.items).joinedload(ReturnItem.product),
            joinedload(Return.cashier),
        )
        .filter(Return.sale_id == sale_id)
        .order_by(Return.created_at.desc())
        .all()
    )
    return [
        SaleReturnSummaryOut(
            id=r.id,
            return_number=r.return_number,
            reason=r.reason,
            refund_amount=r.refund_amount,
            restock=r.restock,
            created_at=r.created_at,
            processed_by_name=r.cashier.full_name if r.cashier else None,
            items=[
                SaleReturnItemOut(
                    product_id=i.product_id,
                    product_name=i.product.name if i.product else None,
                    quantity=i.quantity,
                    unit_price=i.unit_price,
                )
                for i in r.items
            ],
        )
        for r in rows
    ]


def _sale_movements(db: Session, sale: Sale, returns: list[SaleReturnSummaryOut]) -> list[SaleMovementOut]:
    ref_ids = [sale.id] + [r.id for r in returns]
    if not ref_ids:
        return []
    rows = (
        db.query(StockMovement)
        .options(joinedload(StockMovement.product), joinedload(StockMovement.batch))
        .filter(
            or_(
                (StockMovement.reference_type == "sale") & (StockMovement.reference_id == sale.id),
                (StockMovement.reference_type == "return") & (StockMovement.reference_id.in_([r.id for r in returns])),
            )
        )
        .order_by(StockMovement.created_at.asc())
        .all()
    )
    return [
        SaleMovementOut(
            id=m.id,
            product_id=m.product_id,
            product_name=m.product.name if m.product else None,
            batch_id=m.batch_id,
            batch_number=m.batch.batch_number if m.batch else None,
            quantity=m.quantity,
            movement_type=m.movement_type.value,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            reason=m.reason,
            created_at=m.created_at,
        )
        for m in rows
    ]


def sales_to_out(db: Session, sales: list[Sale]) -> list[SaleOut]:
    """List serialization with batch provenance and correction links resolved in bulk (no N+1)."""
    batch_ids = [item.batch_id for sale in sales for item in sale.items if item.batch_id]
    provenance = resolve_batch_provenance(db, batch_ids)
    links = _correction_links_bulk(db, sales)
    return [to_sale_out(sale, db, provenance=provenance, links=links.get(sale.id, (None, None))) for sale in sales]


def to_sale_out(
    sale: Sale,
    db: Session | None = None,
    *,
    detail: bool = False,
    provenance: dict | None = None,
    links: tuple[SaleCorrectionLinkOut | None, SaleCorrectionLinkOut | None] | None = None,
) -> SaleOut:
    if provenance is None:
        provenance = {}
        if db is not None:
            batch_ids = [item.batch_id for item in sale.items if item.batch_id]
            provenance = resolve_batch_provenance(db, batch_ids)

    items = []
    for item in sale.items:
        prov = provenance.get(item.batch_id) if item.batch_id else None
        items.append(
            SaleItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                product_sku=item.product.sku if item.product else None,
                barcode=item.product.barcode if item.product else None,
                batch_id=item.batch_id,
                batch_number=item.batch.batch_number if item.batch else None,
                batch_expiry=item.batch.expiry_date if item.batch else None,
                batch_cost_price=item.batch.cost_price if item.batch else None,
                batch_supplier_id=prov.supplier_id if prov else None,
                batch_supplier_name=prov.supplier_name if prov else None,
                batch_po_id=prov.purchase_order_id if prov else None,
                batch_po_number=prov.po_number if prov else None,
                quantity=item.quantity,
                quantity_returned=item.quantity_returned,
                unit_price=item.unit_price,
                line_total=item.line_total,
                returnable=item.quantity - item.quantity_returned,
            )
        )
    correction = None
    is_correction_of = None
    returns: list[SaleReturnSummaryOut] = []
    movements: list[SaleMovementOut] = []
    if links is not None:
        correction, is_correction_of = links
    elif db is not None:
        correction, is_correction_of = _correction_links(db, sale)
    if db is not None:
        if detail:
            returns = _sale_returns(db, sale.id)
            movements = _sale_movements(db, sale, returns)
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
        correction=correction,
        is_correction_of=is_correction_of,
        returns=returns,
        stock_movements=movements,
    )


def _load(db: Session, sale_id: str) -> Sale:
    sale = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.items).joinedload(SaleItem.batch),
            joinedload(Sale.customer),
            joinedload(Sale.cashier),
        )
        .filter(Sale.id == sale_id)
        .first()
    )
    if sale is None:
        raise NotFoundError("Sale not found")
    return sale


def _sales_query(
    db: Session,
    *,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cashier_id: str | None = None,
    payment_method: str | None = None,
    status: str | None = None,
    product_id: str | None = None,
    correction: str | None = None,
):
    query = db.query(Sale).options(
        joinedload(Sale.items).joinedload(SaleItem.product),
        joinedload(Sale.items).joinedload(SaleItem.batch),
        joinedload(Sale.customer),
        joinedload(Sale.cashier),
    )
    if date_from:
        query = query.filter(Sale.created_at >= _day_start(date_from))
    if date_to:
        query = query.filter(Sale.created_at <= _day_end(date_to))
    if cashier_id:
        query = query.filter(Sale.cashier_id == cashier_id)
    if payment_method:
        try:
            query = query.filter(Sale.payment_method == PaymentMethod(payment_method))
        except ValueError as exc:
            raise ValidationAppError("Invalid payment method") from exc
    if status:
        try:
            query = query.filter(Sale.status == SaleStatus(status))
        except ValueError as exc:
            raise ValidationAppError("Invalid sale status") from exc
    if product_id:
        query = query.filter(Sale.items.any(SaleItem.product_id == product_id))
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Sale.sale_number.ilike(term),
                Sale.items.any(SaleItem.product.has(Product.name.ilike(term))),
                Sale.items.any(SaleItem.product.has(Product.sku.ilike(term))),
            )
        )
    if correction:
        key = correction.strip().lower()
        if key == "normal":
            query = query.filter(
                ~Sale.id.in_(db.query(SaleCorrectionRequest.sale_id)),
                ~Sale.id.in_(
                    db.query(SaleCorrectionRequest.corrected_sale_id).filter(
                        SaleCorrectionRequest.corrected_sale_id.isnot(None)
                    )
                ),
            )
        elif key == "corrected":
            query = query.filter(
                Sale.id.in_(
                    db.query(SaleCorrectionRequest.sale_id).filter(
                        SaleCorrectionRequest.status == CorrectionStatus.APPROVED
                    )
                )
            )
        elif key in {"correction_sale", "correction-related", "correction_related"}:
            if key == "correction_sale":
                query = query.filter(
                    Sale.id.in_(
                        db.query(SaleCorrectionRequest.corrected_sale_id).filter(
                            SaleCorrectionRequest.corrected_sale_id.isnot(None)
                        )
                    )
                )
            else:
                query = query.filter(
                    or_(
                        Sale.id.in_(db.query(SaleCorrectionRequest.sale_id)),
                        Sale.id.in_(
                            db.query(SaleCorrectionRequest.corrected_sale_id).filter(
                                SaleCorrectionRequest.corrected_sale_id.isnot(None)
                            )
                        ),
                    )
                )
        elif key in {"pending", "rejected"}:
            wanted = CorrectionStatus.PENDING if key == "pending" else CorrectionStatus.REJECTED
            query = query.filter(
                Sale.id.in_(db.query(SaleCorrectionRequest.sale_id).filter(SaleCorrectionRequest.status == wanted))
            )
        elif key == "refunded":
            query = query.filter(Sale.status.in_([SaleStatus.REFUNDED, SaleStatus.PARTIALLY_REFUNDED]))
        elif key not in {"all", ""}:
            raise ValidationAppError("Invalid correction filter")
    return query


def list_sales(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    cashier_id: str | None = None,
    payment_method: str | None = None,
    status: str | None = None,
    product_id: str | None = None,
    correction: str | None = None,
) -> tuple[list[Sale], int]:
    query = _sales_query(
        db,
        q=q,
        date_from=date_from,
        date_to=date_to,
        cashier_id=cashier_id,
        payment_method=payment_method,
        status=status,
        product_id=product_id,
        correction=correction,
    )
    total = query.count()
    rows = query.order_by(Sale.created_at.desc()).offset(offset).limit(limit).all()
    return rows, total


def list_sale_cashiers(db: Session) -> list[dict[str, str]]:
    rows = (
        db.query(User.id, User.full_name)
        .join(Sale, Sale.cashier_id == User.id)
        .distinct()
        .order_by(User.full_name.asc())
        .all()
    )
    return [{"id": r[0], "full_name": r[1]} for r in rows]


def export_sales_csv(
    db: Session,
    *,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cashier_id: str | None = None,
    payment_method: str | None = None,
    status: str | None = None,
    product_id: str | None = None,
    correction: str | None = None,
    limit: int = 5000,
) -> str:
    query = _sales_query(
        db,
        q=q,
        date_from=date_from,
        date_to=date_to,
        cashier_id=cashier_id,
        payment_method=payment_method,
        status=status,
        product_id=product_id,
        correction=correction,
    )
    rows = query.order_by(Sale.created_at.desc()).limit(limit).all()
    outs = sales_to_out(db, rows)
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "date_time",
            "sale_number",
            "cashier",
            "status",
            "payment_method",
            "product",
            "sku",
            "quantity",
            "unit_price",
            "discount_percent",
            "line_total",
            "batch",
            "expiry",
            "batch_cost",
            "batch_supplier",
            "batch_po_number",
            "correction_status",
            "related_sale_number",
            "financial_difference",
        ]
    )
    for out in outs:
        corr_status = None
        related = None
        financial_difference = None
        if out.correction:
            corr_status = out.correction.status
            related = out.correction.corrected_sale_number
            financial_difference = out.correction.financial_difference
        elif out.is_correction_of:
            corr_status = "CORRECTION_SALE"
            related = out.is_correction_of.original_sale_number
            financial_difference = out.is_correction_of.financial_difference
        for item in out.items:
            writer.writerow(
                [
                    out.created_at.isoformat(),
                    out.sale_number,
                    out.cashier_name or "",
                    out.status,
                    out.payment_method,
                    item.product_name or "",
                    item.product_sku or "",
                    item.quantity,
                    str(item.unit_price),
                    str(out.discount_percent),
                    str(item.line_total),
                    item.batch_number or "",
                    item.batch_expiry.isoformat() if item.batch_expiry else "",
                    str(item.batch_cost_price) if item.batch_cost_price is not None else "",
                    item.batch_supplier_name or "",
                    item.batch_po_number or "",
                    corr_status or "",
                    related or "",
                    str(financial_difference) if financial_difference is not None else "",
                ]
            )
        if not out.items:
            writer.writerow(
                [
                    out.created_at.isoformat(),
                    out.sale_number,
                    out.cashier_name or "",
                    out.status,
                    out.payment_method,
                    "",
                    "",
                    "",
                    "",
                    str(out.discount_percent),
                    str(out.total),
                    "",
                    "",
                    "",
                    "",
                    "",
                    corr_status or "",
                    related or "",
                    str(financial_difference) if financial_difference is not None else "",
                ]
            )
    return buf.getvalue()


def get_sale(db: Session, sale_id: str) -> SaleOut:
    return to_sale_out(_load(db, sale_id), db, detail=True)


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


def complete_sale(db: Session, data: SaleCreate, actor: User, *, commit: bool = True) -> SaleOut:
    existing = db.query(Sale).filter(Sale.idempotency_key == data.idempotency_key).first()
    if existing:
        return to_sale_out(_load(db, existing.id), db)
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
    if not commit:
        db.flush()
        return to_sale_out(_load(db, sale.id), db)
    try:
        db.commit()
    except Exception:
        db.rollback()
        replay = db.query(Sale).filter(Sale.idempotency_key == data.idempotency_key).first()
        if replay:
            return to_sale_out(_load(db, replay.id), db)
        raise
    return to_sale_out(_load(db, sale.id), db)


def customer_sales(db: Session, customer_id: str) -> list[SaleOut]:
    if db.get(Customer, customer_id) is None:
        raise NotFoundError("Customer not found")
    rows = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.product),
            joinedload(Sale.items).joinedload(SaleItem.batch),
            joinedload(Sale.customer),
            joinedload(Sale.cashier),
        )
        .filter(Sale.customer_id == customer_id)
        .order_by(Sale.created_at.desc())
        .all()
    )
    return sales_to_out(db, rows)
