from decimal import Decimal

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


def get_settings(db: Session) -> SettingsOut:
    return SettingsOut(
        pharmacy_name=get_setting(db, "pharmacy_name"),
        license_number=get_setting(db, "license_number"),
        phone=get_setting(db, "phone"),
        email=get_setting(db, "email"),
        address=get_setting(db, "address"),
        tax_rate=get_tax_rate(db),
        currency=get_setting(db, "currency", "GHS"),
    )


def update_settings(db: Session, data: SettingsUpdate) -> SettingsOut:
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.flush()
    return get_settings(db)
