from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models import Setting
from app.core.schemas import SettingsOut, SettingsUpdate

DEFAULTS = {
    "pharmacy_name": "BrightCare Pharmacy",
    "license_number": "RX-2026-88214",
    "phone": "+1 (555) 019-4477",
    "email": "hello@brightcare.pharmacy",
    "address": "240 Meridian Ave, Suite 12",
    "tax_rate": "5",
    "currency": "GHS",
}


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    if row:
        return row.value
    return DEFAULTS.get(key, default)


def get_tax_rate(db: Session) -> Decimal:
    return Decimal(get_setting(db, "tax_rate", "5"))


def get_default_markup(db: Session) -> Decimal | None:
    """Pharmacy's default selling-price markup %. Unset until the pharmacy chooses one."""
    raw = get_setting(db, "default_markup_percent", "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def get_settings(db: Session) -> SettingsOut:
    return SettingsOut(
        pharmacy_name=get_setting(db, "pharmacy_name"),
        license_number=get_setting(db, "license_number"),
        phone=get_setting(db, "phone"),
        email=get_setting(db, "email"),
        address=get_setting(db, "address"),
        tax_rate=get_tax_rate(db),
        currency=get_setting(db, "currency", "GHS"),
        default_markup_percent=get_default_markup(db),
    )


def update_settings(db: Session, data: SettingsUpdate) -> SettingsOut:
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        if value is None and key != "default_markup_percent":
            continue
        stored = "" if value is None else str(value)
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=stored))
        else:
            row.value = stored
    db.flush()
    return get_settings(db)
