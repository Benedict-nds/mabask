"""Per-user permission overrides on top of the role baseline (INHERIT / ALLOW / DENY)."""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.core.permissions import (
    ADMIN_ONLY_PERMISSIONS,
    ADMIN_ROLE,
    ALL_PERMISSIONS,
    INHERIT,
    PERMISSION_CODES,
    PERMISSION_GROUPS,
    permission_group,
    permission_overrides,
    role_permissions,
    user_permissions,
)
from app.core.responses import ForbiddenError, NotFoundError, ValidationAppError
from app.core.schemas import PermissionInfo, UserPermissionEntry, UserPermissionsOut
from app.models import User, UserPermissionOverride
from app.modules.audit.service import record_audit

_GROUP_LABELS = dict(PERMISSION_GROUPS)
_GROUP_ORDER = {key: i for i, (key, _) in enumerate(PERMISSION_GROUPS)}
ADMIN_ONLY_REASON = "Admin-only. Follows the role and cannot be overridden; change the role instead."


def permission_catalog() -> list[PermissionInfo]:
    entries = [
        PermissionInfo(
            code=code,
            description=description,
            group=permission_group(code),
            group_label=_GROUP_LABELS.get(permission_group(code), permission_group(code).title()),
            admin_only=code in ADMIN_ONLY_PERMISSIONS,
        )
        for code, description in ALL_PERMISSIONS
    ]
    return sorted(entries, key=lambda e: _GROUP_ORDER.get(e.group, len(_GROUP_ORDER)))


def _load_target(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if user is None:
        raise NotFoundError("User not found")
    return user


def _edit_blocker(actor: User, target: User) -> str | None:
    if actor.role.name != ADMIN_ROLE:
        return "Only admins can manage permissions."
    if actor.id == target.id:
        return "You cannot change your own permissions. Ask another admin."
    return None


def _assert_can_manage(actor: User, target: User) -> None:
    if actor.role.name != ADMIN_ROLE:
        raise ForbiddenError("Only admins can manage permissions")
    if actor.id == target.id:
        raise ValidationAppError("You cannot change your own permissions")


def validate_overrides(changes: Mapping[str, str]) -> None:
    for code, state in changes.items():
        if code not in PERMISSION_CODES:
            raise ValidationAppError("Unknown permission", {"permission": code})
        if code in ADMIN_ONLY_PERMISSIONS and state != INHERIT:
            raise ValidationAppError(
                f"{code} is admin-only and follows the role. Change the user's role instead.",
                {"permission": code},
            )


def _audit_change(db: Session, actor: User, target: User, code: str, previous: str, new: str, *, reason: str) -> None:
    record_audit(
        db,
        user=actor,
        action="PERMISSION_OVERRIDE_CHANGED",
        entity_type="user",
        entity_id=target.id,
        details={
            "target_user": target.email,
            "target_name": target.full_name,
            "role": target.role.name,
            "permission": code,
            "previous": previous,
            "new": new,
            "reason": reason,
        },
    )


def apply_overrides(
    db: Session, target: User, changes: Mapping[str, str], actor: User, *, reason: str = "override"
) -> int:
    """Validate the whole batch, then apply and audit each real change. Caller commits."""
    validate_overrides(changes)
    existing = {o.permission_code: o for o in target.permission_overrides}
    changed = 0
    for code, state in changes.items():
        row = existing.get(code)
        previous = row.effect if row else INHERIT
        if previous == state:
            continue
        if state == INHERIT:
            target.permission_overrides.remove(row)
        elif row is None:
            target.permission_overrides.append(
                UserPermissionOverride(permission_code=code, effect=state, updated_by=actor.id)
            )
        else:
            row.effect = state
            row.updated_by = actor.id
        _audit_change(db, actor, target, code, previous, state, reason=reason)
        changed += 1
    return changed


def _detail(target: User, actor: User) -> UserPermissionsOut:
    baseline = role_permissions(target)
    overrides = permission_overrides(target)
    effective = user_permissions(target)
    blocker = _edit_blocker(actor, target)
    entries = [
        UserPermissionEntry(
            **info.model_dump(),
            role_default=info.code in baseline,
            override=overrides.get(info.code, INHERIT),
            effective=info.code in effective,
            locked=info.admin_only,
            locked_reason=ADMIN_ONLY_REASON if info.admin_only else None,
        )
        for info in permission_catalog()
    ]
    return UserPermissionsOut(
        user_id=target.id,
        full_name=target.full_name,
        role=target.role.name,
        editable=blocker is None,
        not_editable_reason=blocker,
        override_count=len(overrides),
        permissions=entries,
    )


def get_user_permissions(db: Session, user_id: str, actor: User) -> UserPermissionsOut:
    return _detail(_load_target(db, user_id), actor)


def set_user_permissions(db: Session, user_id: str, changes: Mapping[str, str], actor: User) -> UserPermissionsOut:
    target = _load_target(db, user_id)
    _assert_can_manage(actor, target)
    apply_overrides(db, target, changes, actor)
    db.commit()
    db.refresh(target)
    return _detail(target, actor)


def reset_user_permissions(db: Session, user_id: str, actor: User) -> UserPermissionsOut:
    target = _load_target(db, user_id)
    _assert_can_manage(actor, target)
    changes = {o.permission_code: INHERIT for o in target.permission_overrides}
    for code in [c for c in changes if c not in PERMISSION_CODES or c in ADMIN_ONLY_PERMISSIONS]:
        # Stale or ineffective rows (e.g. a code removed from the registry) are cleared silently.
        target.permission_overrides.remove(next(o for o in target.permission_overrides if o.permission_code == code))
        changes.pop(code)
    apply_overrides(db, target, changes, actor, reason="reset_to_role_defaults")
    db.commit()
    db.refresh(target)
    return _detail(target, actor)
