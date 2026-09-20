from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import MovementType, PaymentMethod, Product, PurchaseOrder, Sale, SaleItem, StockMovement, Supplier


def _range(name: str, start: date | None, end: date | None) -> tuple[datetime, datetime]:
    today = date.today()
    if start and end:
        return datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc), datetime.combine(
            end, datetime.max.time()
        ).replace(tzinfo=timezone.utc)
    if name == "daily":
        d0 = today
        d1 = today
    elif name == "monthly":
        d0 = today.replace(day=1)
        d1 = today
    else:
        d0 = today - timedelta(days=6)
        d1 = today
    return datetime.combine(d0, datetime.min.time()).replace(tzinfo=timezone.utc), datetime.combine(
        d1, datetime.max.time()
    ).replace(tzinfo=timezone.utc)


def sales_report(db: Session, range_name: str = "weekly", start: date | None = None, end: date | None = None) -> dict:
    t0, t1 = _range(range_name, start, end)
    sales = db.query(Sale).filter(Sale.created_at >= t0, Sale.created_at <= t1).all()
    revenue = sum((s.total for s in sales), Decimal("0"))
    count = len(sales)
    avg = (revenue / count) if count else Decimal("0")

    pay = {m.value: Decimal("0") for m in PaymentMethod}
    for s in sales:
        pay[s.payment_method.value] += s.total

    top = (
        db.query(
            Product.name,
            func.sum(SaleItem.quantity).label("units"),
            func.sum(SaleItem.line_total).label("revenue"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= t0, Sale.created_at <= t1)
        .group_by(Product.name)
        .order_by(func.sum(SaleItem.line_total).desc())
        .limit(8)
        .all()
    )

    # daily trend across the window
    trend_rows = (
        db.query(func.date(Sale.created_at).label("day"), func.coalesce(func.sum(Sale.total), 0))
        .filter(Sale.created_at >= t0, Sale.created_at <= t1)
        .group_by(func.date(Sale.created_at))
        .order_by(func.date(Sale.created_at))
        .all()
    )
    trend = [{"label": str(r[0]), "value": float(r[1])} for r in trend_rows]

    category_rows = (
        db.query(Product.category, func.coalesce(func.sum(SaleItem.line_total), 0))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= t0, Sale.created_at <= t1)
        .group_by(Product.category)
        .all()
    )
    cat_total = sum(Decimal(r[1]) for r in category_rows) or Decimal("1")
    colors = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"]
    category_mix = [
        {"label": r[0], "value": int(round(float(Decimal(r[1]) / cat_total * 100))), "color": colors[i % 5]}
        for i, r in enumerate(category_rows)
    ]

    return {
        "range": range_name,
        "from": t0.date().isoformat(),
        "to": t1.date().isoformat(),
        "revenue": float(revenue),
        "transactions": count,
        "average_ticket": float(avg),
        "gross_profit": 0.0 if not sales else _gross_profit(db, t0, t1),
        "units_sold": _units_sold(db, t0, t1),
        "payment_methods": {k: float(v) for k, v in pay.items()},
        "top_selling": [
            {"name": r[0], "units": int(r[1] or 0), "revenue": float(r[2] or 0), "change": 0} for r in top
        ],
        "trend": trend,
        "category_mix": category_mix,
    }


def _units_sold(db: Session, t0: datetime, t1: datetime) -> int:
    return int(
        db.query(func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= t0, Sale.created_at <= t1)
        .scalar()
        or 0
    )


def _gross_profit(db: Session, t0: datetime, t1: datetime) -> float:
    row = (
        db.query(
            func.coalesce(func.sum(SaleItem.line_total - (SaleItem.quantity * Product.cost_price)), 0)
        )
        .join(Product, Product.id == SaleItem.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= t0, Sale.created_at <= t1)
        .scalar()
    )
    return float(row or 0)


def inventory_report(db: Session) -> dict:
    products = db.query(Product).filter(Product.deleted_at.is_(None), Product.is_active.is_(True)).all()
    value = sum((p.quantity_on_hand * p.cost_price for p in products), Decimal("0"))
    from app.modules.inventory.service import expiring, low_stock, stock_status

    low = low_stock(db)
    exp = expiring(db, 60)
    return {
        "sku_count": len(products),
        "inventory_value": float(value),
        "low_stock": len(low),
        "critical": len([p for p in low if stock_status(p.quantity_on_hand, p.reorder_threshold) == "critical"]),
        "expiring": len(exp),
        "low_stock_items": [
            {"id": p.id, "name": p.name, "quantity": p.quantity_on_hand, "reorder_threshold": p.reorder_threshold}
            for p in low
        ],
        "expiring_items": [
            {
                "product": b.product.name if b.product else "",
                "batch": b.batch_number,
                "expiry": b.expiry_date.isoformat(),
                "quantity": b.quantity,
            }
            for b in exp
        ],
    }


def purchasing_report(db: Session) -> dict:
    pos = db.query(PurchaseOrder).all()
    by_status: dict[str, int] = {}
    spend = Decimal("0")
    for po in pos:
        by_status[po.status.value] = by_status.get(po.status.value, 0) + 1
        if po.status.value in {"RECEIVED", "PARTIALLY_RECEIVED"}:
            spend += po.total
    supplier_spend = (
        db.query(Supplier.name, func.coalesce(func.sum(PurchaseOrder.total), 0))
        .join(PurchaseOrder, PurchaseOrder.supplier_id == Supplier.id)
        .filter(PurchaseOrder.status.in_(["RECEIVED", "PARTIALLY_RECEIVED"]))
        .group_by(Supplier.name)
        .all()
    )
    return {
        "purchase_orders": len(pos),
        "by_status": by_status,
        "supplier_spend": [{"supplier": r[0], "total": float(r[1])} for r in supplier_spend],
        "received_spend": float(spend),
    }
