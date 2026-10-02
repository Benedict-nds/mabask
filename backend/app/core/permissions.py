from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import ForbiddenError
from app.models import User

ALL_PERMISSIONS = [
    ("users.read", "View staff accounts"),
    ("users.create", "Create staff accounts"),
    ("users.update", "Update staff accounts"),
    ("users.delete", "Deactivate staff accounts"),
    ("inventory.read", "View inventory"),
    ("inventory.create", "Create products"),
    ("inventory.update", "Update products"),
    ("inventory.delete", "Deactivate products"),
    ("inventory.archive", "Archive products from the active catalog"),
    ("inventory.restore", "Restore archived products"),
    ("inventory.adjust", "Adjust stock quantities"),
    ("inventory.batch_edit", "Correct batch expiry dates"),
    ("sales.read", "View sales"),
    ("sales.create", "Complete sales"),
    ("sales.refund", "Process returns"),
    ("sales.correction_request", "Request sale corrections"),
    ("sales.correction_approve", "Approve or reject sale corrections"),
    ("purchases.read", "View purchase orders"),
    ("purchases.create", "Create purchase orders"),
    ("purchases.approve", "Approve purchase orders"),
    ("purchases.receive", "Receive stock"),
    ("suppliers.read", "View suppliers"),
    ("suppliers.create", "Create suppliers"),
    ("suppliers.update", "Update suppliers"),
    ("suppliers.delete", "Deactivate suppliers"),
    ("customers.read", "View customers"),
    ("customers.create", "Create customers"),
    ("customers.update", "Update customers"),
    ("reports.read", "View reports and dashboard"),
    ("audit.read", "View audit logs"),
    ("settings.manage", "Manage pharmacy settings"),
    ("ai.use", "Use AI copilot"),
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [code for code, _ in ALL_PERMISSIONS],
    "pharmacist": [
        "inventory.read",
        "inventory.create",
        "inventory.update",
        "inventory.delete",
        "inventory.adjust",
        "sales.read",
        "sales.create",
        "sales.refund",
        "sales.correction_request",
        "purchases.read",
        "purchases.create",
        "purchases.approve",
        "purchases.receive",
        "suppliers.read",
        "suppliers.create",
        "suppliers.update",
        "customers.read",
        "customers.create",
        "customers.update",
        "reports.read",
        "audit.read",
        "ai.use",
    ],
    "cashier": [
        "inventory.read",
        "sales.read",
        "sales.create",
        "sales.refund",
        "sales.correction_request",
        "customers.read",
        "customers.create",
        "customers.update",
        "ai.use",
    ],
}


ADMIN_ROLE = "admin"

# System administration: team, permission management and settings/security. These always
# follow the role, so no override can grant them to a non-admin or remove them from an admin.
ADMIN_ONLY_PERMISSIONS = frozenset({"users.read", "users.create", "users.update", "users.delete", "settings.manage"})

PERMISSION_CODES = frozenset(code for code, _ in ALL_PERMISSIONS)

PERMISSION_GROUPS: list[tuple[str, str]] = [
    ("inventory", "Inventory"),
    ("sales", "Point of sale & returns"),
    ("corrections", "Sale corrections"),
    ("purchases", "Purchasing"),
    ("receiving", "Receiving"),
    ("suppliers", "Suppliers"),
    ("customers", "Customers"),
    ("reports", "Reports & dashboard"),
    ("audit", "Audit log"),
    ("ai", "AI Copilot"),
    ("users", "Team management"),
    ("settings", "Settings & security"),
]

_GROUP_OVERRIDES = {
    "sales.correction_request": "corrections",
    "sales.correction_approve": "corrections",
    "purchases.receive": "receiving",
}

ALLOW = "ALLOW"
DENY = "DENY"
INHERIT = "INHERIT"


def permission_group(code: str) -> str:
    return _GROUP_OVERRIDES.get(code, code.split(".", 1)[0])


def is_overridable(code: str) -> bool:
    return code in PERMISSION_CODES and code not in ADMIN_ONLY_PERMISSIONS


def role_permissions(user: User) -> set[str]:
    return {rp.permission.code for rp in user.role.permissions}


def permission_overrides(user: User) -> dict[str, str]:
    """Stored overrides that can take effect; anything else is ignored by the resolver."""
    return {
        o.permission_code: o.effect
        for o in user.permission_overrides
        if is_overridable(o.permission_code) and o.effect in (ALLOW, DENY)
    }


def resolve_permissions(baseline: set[str], overrides: dict[str, str]) -> set[str]:
    """Role baseline + user ALLOWs - user DENYs. Admin-only codes always follow the baseline."""
    effective = set(baseline)
    for code, effect in overrides.items():
        if not is_overridable(code):
            continue
        if effect == ALLOW:
            effective.add(code)
        elif effect == DENY:
            effective.discard(code)
    return effective


def user_permissions(user: User) -> set[str]:
    """Effective permissions: the single source of truth for every authorization check."""
    return resolve_permissions(role_permissions(user), permission_overrides(user))


def has_permission(user: User, code: str) -> bool:
    return code in user_permissions(user)


def require_permission(code: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, code):
            raise ForbiddenError()
        return user

    return dependency


def load_permission_codes(db: Session, user: User) -> list[str]:
    return sorted(user_permissions(user))
