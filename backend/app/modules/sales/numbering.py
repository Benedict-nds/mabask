from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import PurchaseOrder, Return, Sale


def _next(db: Session, model, field, prefix: str) -> str:
    year = datetime.now(timezone.utc).year
    stem = f"{prefix}-{year}-"
    last = db.query(func.max(field)).filter(field.like(f"{stem}%")).scalar()
    n = 1
    if last:
        tail = str(last).rsplit("-", 1)[-1]
        try:
            n = int(tail) + 1
        except ValueError:
            n = 1
    return f"{stem}{n:04d}"


def next_sale_number(db: Session) -> str:
    return _next(db, Sale, Sale.sale_number, "SALE")


def next_po_number(db: Session) -> str:
    return _next(db, PurchaseOrder, PurchaseOrder.po_number, "PO")


def next_return_number(db: Session) -> str:
    return _next(db, Return, Return.return_number, "RET")
