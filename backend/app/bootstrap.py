from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Customer, Setting, User

logger = logging.getLogger("aetherqore.bootstrap")


def bootstrap_pharmacy(db: Session) -> dict[str, str]:
    """Create RBAC, default settings, walk-in customer, and the first admin if needed."""
    from seed import seed_rbac

    roles = seed_rbac(db)
    created: dict[str, str] = {}

    defaults = {
        "pharmacy_name": os.environ.get("AETHERQORE_PHARMACY_NAME", "Pharmacy"),
        "license_number": os.environ.get("AETHERQORE_LICENSE_NUMBER", ""),
        "phone": os.environ.get("AETHERQORE_PHONE", ""),
        "email": os.environ.get("AETHERQORE_ADMIN_EMAIL", ""),
        "address": os.environ.get("AETHERQORE_ADDRESS", ""),
        "tax_rate": os.environ.get("AETHERQORE_TAX_RATE", "0"),
        "currency": "GHS",
    }
    for key, value in defaults.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=value))
            created[f"setting.{key}"] = value

    if db.query(Customer).filter(Customer.name == "Walk-in").first() is None:
        db.add(Customer(name="Walk-in", notes="Default counter customer"))
        created["customer"] = "Walk-in"

    if db.query(User).filter(User.deleted_at.is_(None)).count() == 0:
        email = os.environ.get("AETHERQORE_ADMIN_EMAIL", "admin@pharmacy.local").strip().lower()
        name = os.environ.get("AETHERQORE_ADMIN_NAME", "Pharmacy Admin").strip()
        password = os.environ.get("AETHERQORE_ADMIN_PASSWORD", "").strip()
        if not password:
            raise RuntimeError("AETHERQORE_ADMIN_PASSWORD is required to create the first admin account")
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=name,
                role_id=roles["admin"].id,
            )
        )
        created["admin"] = email

    db.commit()
    return created
