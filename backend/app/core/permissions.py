from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import ForbiddenError
from app.models import Permission, RolePermission, User

ALL_PERMISSIONS = [
    ("users.read", "View staff accounts"),
    ("users.create", "Create staff accounts"),
    ("users.update", "Update staff accounts"),
    ("users.delete", "Deactivate staff accounts"),
    ("inventory.read", "View inventory"),
    ("inventory.create", "Create products"),
    ("inventory.update", "Update products"),
    ("inventory.delete", "Deactivate products"),
    ("inventory.adjust", "Adjust stock quantities"),
    ("sales.read", "View sales"),
    ("sales.create", "Complete sales"),
    ("sales.refund", "Process returns"),
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
        "customers.read",
        "customers.create",
        "customers.update",
        "ai.use",
    ],
}


def user_permissions(user: User) -> set[str]:
    return {rp.permission.code for rp in user.role.permissions}


def has_permission(user: User, code: str) -> bool:
    return code in user_permissions(user)


def require_permission(code: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, code):
            raise ForbiddenError()
        return user

    return dependency


def load_permission_codes(db: Session, user: User) -> list[str]:
    rows = (
        db.query(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == user.role_id)
        .all()
    )
    return [r[0] for r in rows]
