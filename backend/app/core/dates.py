from __future__ import annotations

import re
from datetime import date, datetime

# ISO-like: 2027-09-16 and the zero-padded bug 0027-09-16
_ISO = re.compile(r"^(\d{3,4})-(\d{1,2})-(\d{1,2})")
_ISO_SLASH = re.compile(r"^(\d{3,4})/(\d{1,2})/(\d{1,2})$")
# Ghana / invoice: 15/09/27, 15/09/2027, 15.09.2027
_DMY = re.compile(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{2}|\d{4})$")
# 15-09-2027
_DMY_DASH = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
# 27-09-16 meaning 2027-09-16
_YMD_SHORT = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{2})$")


def _fix_century(value: date) -> date:
    if value.year < 1000:
        return value.replace(year=value.year + 2000)
    return value


def _make(year: int, month: int, day: int) -> date:
    if year < 1000:
        year += 2000
    return date(year, month, day)


def parse_expiry(value: object, *, required: bool = False) -> date | None:
    """Parse an expiry date and fold 2-digit / zero-padded years (0027) into 20xx."""
    if value is None or value == "":
        if required:
            raise ValueError("Expiry date is required")
        return None
    if isinstance(value, datetime):
        return _fix_century(value.date())
    if isinstance(value, date):
        return _fix_century(value)

    text = str(value).strip().replace("T", " ").split()[0]
    if not text:
        if required:
            raise ValueError("Expiry date is required")
        return None

    try:
        match = _ISO.match(text)
        if match:
            return _make(int(match[1]), int(match[2]), int(match[3]))
        match = _ISO_SLASH.match(text)
        if match:
            return _make(int(match[1]), int(match[2]), int(match[3]))
        match = _DMY.match(text)
        if match:
            return _make(int(match[3]), int(match[2]), int(match[1]))
        match = _DMY_DASH.match(text)
        if match:
            return _make(int(match[3]), int(match[2]), int(match[1]))
        match = _YMD_SHORT.match(text)
        if match:
            return _make(int(match[1]), int(match[2]), int(match[3]))
        return _fix_century(date.fromisoformat(text[:10]))
    except ValueError:
        if required:
            raise ValueError("Invalid expiry date. Use a full year, e.g. 2027-09-16.") from None
        return None


def repair_short_year_expiries(db) -> int:
    """Rewrite stored years like 0027 (year 27 AD) to 2027 on batches and PO lines."""
    from app.models.entities import Batch, PurchaseOrderItem

    cutoff = date(1000, 1, 1)
    fixed = 0
    for model, column in ((Batch, Batch.expiry_date), (PurchaseOrderItem, PurchaseOrderItem.expiry_date)):
        rows = db.query(model).filter(column.isnot(None), column < cutoff).all()
        for row in rows:
            row.expiry_date = _fix_century(row.expiry_date)
            fixed += 1
    if fixed:
        db.commit()
    return fixed
