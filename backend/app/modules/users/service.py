from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.responses import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models import Role, RolePermission, User
from app.core.permissions import ROLE_PERMISSIONS
from app.core.schemas import RoleOut, UserCreate, UserOut, UserUpdate
from app.core.security import hash_password
from app.modules.auth.service import to_user_out
from app.modules.users.permissions import apply_overrides, validate_overrides

ROLE_RANK = {"cashier": 0, "pharmacist": 1, "admin": 2}


def _rank(role_name: str) -> int:
    return ROLE_RANK.get(role_name, -1)


def _load(db: Session, user_id: str) -> User:
    user = (
        db.query(User)
        .options(
            joinedload(User.role)
            .joinedload(Role.permissions)
            .joinedload(RolePermission.permission)
        )
        .filter(User.id == user_id, User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise NotFoundError("User not found")
    return user


def _assert_can_assign(actor: User, role_name: str) -> None:
    if _rank(role_name) < 0:
        raise ValidationAppError("Unknown role", {"role": role_name})
    if _rank(role_name) > _rank(actor.role.name):
        raise ForbiddenError("You cannot assign a role above your own")


def _assert_not_last_admin(db: Session, user: User) -> None:
    if user.role.name != "admin":
        return
    remaining = (
        db.query(User)
        .join(Role)
        .filter(
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            User.id != user.id,
            Role.name == "admin",
        )
        .count()
    )
    if remaining == 0:
        raise ValidationAppError("Cannot deactivate or demote the last admin")


def list_users(db: Session) -> list[UserOut]:
    users = (
        db.query(User)
        .options(
            joinedload(User.role)
            .joinedload(Role.permissions)
            .joinedload(RolePermission.permission)
        )
        .filter(User.deleted_at.is_(None))
        .order_by(User.full_name)
        .all()
    )
    return [to_user_out(u) for u in users]


def get_user(db: Session, user_id: str) -> UserOut:
    return to_user_out(_load(db, user_id))


def list_roles() -> list[RoleOut]:
    return [
        RoleOut(name=name, description=name.title(), permissions=perms)
        for name, perms in ROLE_PERMISSIONS.items()
    ]


def create_user(db: Session, data: UserCreate, actor: User) -> UserOut:
    _assert_can_assign(actor, data.role)
    if data.permission_overrides:
        if actor.role.name != "admin":
            raise ForbiddenError("Only admins can manage permissions")
        validate_overrides(data.permission_overrides)
    if db.query(User).filter(User.email == data.email.lower(), User.deleted_at.is_(None)).first():
        raise ConflictError("A user with that email already exists")
    role = db.query(Role).filter(Role.name == data.role).first()
    if role is None:
        raise ValidationAppError("Unknown role", {"role": data.role})
    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role_id=role.id,
        is_active=data.is_active,
    )
    db.add(user)
    db.flush()
    record_audit(db, user=actor, action="USER_CREATED", entity_type="user", entity_id=user.id, details={"email": user.email, "role": data.role})
    if data.permission_overrides:
        db.refresh(user)
        apply_overrides(db, user, data.permission_overrides, actor, reason="set_at_creation")
    db.commit()
    return to_user_out(_load(db, user.id))


def update_user(db: Session, user_id: str, data: UserUpdate, actor: User) -> UserOut:
    user = _load(db, user_id)
    previous_role = user.role.name
    changed: list[str] = []
    if data.role is not None and data.role != previous_role:
        if user.id == actor.id:
            raise ValidationAppError("You cannot change your own role")
        _assert_can_assign(actor, data.role)
        if user.role.name == "admin" and data.role != "admin":
            _assert_not_last_admin(db, user)
        role = db.query(Role).filter(Role.name == data.role).first()
        if role is None:
            raise ValidationAppError("Unknown role", {"role": data.role})
        user.role = role
        record_audit(
            db,
            user=actor,
            action="ROLE_CHANGED",
            entity_type="user",
            entity_id=user.id,
            details={"target_user": user.email, "target_name": user.full_name, "previous": previous_role, "new": data.role},
        )
        changed.append("role")
    if data.is_active is not None and data.is_active != user.is_active:
        changed.append("is_active")
    if data.is_active is False:
        if user.id == actor.id:
            raise ValidationAppError("You cannot deactivate your own account")
        _assert_not_last_admin(db, user)
        user.is_active = False
    elif data.is_active is True:
        user.is_active = True
    if data.full_name is not None and data.full_name != user.full_name:
        user.full_name = data.full_name
        changed.append("full_name")
    if data.password:
        user.password_hash = hash_password(data.password)
        changed.append("password_reset")
    record_audit(db, user=actor, action="USER_UPDATED", entity_type="user", entity_id=user.id, details={"changed": changed})
    db.commit()
    return to_user_out(_load(db, user.id))


def delete_user(db: Session, user_id: str, actor: User) -> None:
    user = _load(db, user_id)
    if user.id == actor.id:
        raise ValidationAppError("You cannot deactivate your own account")
    _assert_not_last_admin(db, user)
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    record_audit(db, user=actor, action="USER_DELETED", entity_type="user", entity_id=user.id)
    db.commit()
