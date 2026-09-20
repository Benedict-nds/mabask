from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AuditLog, Product, PurchaseOrder, Sale, User
from app.modules.inventory.service import expiring, low_stock
from app.modules.reports.service import _gross_profit, sales_report


def dashboard(db: Session) -> dict:
    today0 = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    today1 = datetime.combine(date.today(), datetime.max.time()).replace(tzinfo=timezone.utc)
    yesterday0 = today0 - timedelta(days=1)
    yesterday1 = today0 - timedelta(microseconds=1)

    today_rev = db.query(func.coalesce(func.sum(Sale.total), 0)).filter(Sale.created_at >= today0, Sale.created_at <= today1).scalar()
    today_count = db.query(func.count(Sale.id)).filter(Sale.created_at >= today0, Sale.created_at <= today1).scalar()
    yday_rev = db.query(func.coalesce(func.sum(Sale.total), 0)).filter(Sale.created_at >= yesterday0, Sale.created_at <= yesterday1).scalar()

    inventory_value = db.query(func.coalesce(func.sum(Product.quantity_on_hand * Product.cost_price), 0)).filter(
        Product.deleted_at.is_(None), Product.is_active.is_(True)
    ).scalar()

    low = low_stock(db)
    exp = expiring(db, 30)
    pending_pos = (
        db.query(func.count(PurchaseOrder.id))
        .filter(PurchaseOrder.status.in_(["SUBMITTED", "APPROVED", "PARTIALLY_RECEIVED"]))
        .scalar()
    )

    weekly = sales_report(db, "weekly")
    recent_sales = (
        db.query(Sale)
        .order_by(Sale.created_at.desc())
        .limit(6)
        .all()
    )
    audits = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(8).all()
    actors = {u.id: u.full_name for u in db.query(User).all()}

    yday = float(yday_rev or 0)
    today = float(today_rev or 0)
    change = ((today - yday) / yday * 100) if yday else 0

    insights = []
    for p in low[:3]:
        insights.append(
            {
                "text": f"{p.name} is at {p.quantity_on_hand} units (reorder at {p.reorder_threshold}). Create a purchase order to avoid a stockout.",
                "action": "Create purchase order",
                "href": "/suppliers",
            }
        )
    for b in exp[:2]:
        name = b.product.name if b.product else "A medicine"
        insights.append(
            {
                "text": f"{name} batch {b.batch_number} expires {b.expiry_date.isoformat()} ({b.quantity} units). Consider a clearance before write-off.",
                "action": "Review inventory",
                "href": "/inventory",
            }
        )
    if not insights:
        insights.append(
            {
                "text": "Inventory and expiry look healthy. Keep selling — the copilot will flag the next risk.",
                "action": "See report",
                "href": "/reports",
            }
        )

    activity = []
    for a in audits:
        activity.append(
            {
                "id": a.id,
                "who": actors.get(a.user_id, "System"),
                "action": a.action.replace("_", " ").lower(),
                "time": a.created_at.isoformat() if a.created_at else "",
                "type": "ai" if a.action.startswith("AI") else "inventory" if "PRODUCT" in a.action or "STOCK" in a.action else "sale" if "SALE" in a.action else "shipment" if "PURCHASE" in a.action else "cash",
            }
        )

    return {
        "greeting_name": None,
        "today_revenue": today,
        "today_sales_count": int(today_count or 0),
        "yesterday_revenue": yday,
        "yesterday_change_pct": round(change, 1),
        "inventory_value": float(inventory_value or 0),
        "low_stock_count": len(low),
        "expiring_count": len(exp),
        "pending_invoices": int(pending_pos or 0),
        "weekly_revenue": weekly["revenue"],
        "weekly_trend": weekly["trend"],
        "gross_profit": weekly["gross_profit"],
        "insights": insights[:3],
        "recent_sales": [
            {"id": s.id, "sale_number": s.sale_number, "total": float(s.total), "created_at": s.created_at.isoformat()}
            for s in recent_sales
        ],
        "activity": activity,
    }
