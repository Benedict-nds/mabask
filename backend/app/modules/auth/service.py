from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.modules.audit.service import record_audit
from app.core.responses import UnauthorizedError
from app.models import RefreshToken, Role, RolePermission, User
from app.core.permissions import permission_overrides, user_permissions
from app.core.schemas import TokenPair, UserOut
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
    refresh_expiry,
    verify_password,
)


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.name,
        permissions=sorted(user_permissions(user)),
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        permission_overrides=permission_overrides(user),
    )


def _load_user(db: Session, user_id: str) -> User | None:
    return (
        db.query(User)
        .options(
            joinedload(User.role)
            .joinedload(Role.permissions)
            .joinedload(RolePermission.permission)
        )
        .filter(User.id == user_id, User.deleted_at.is_(None))
        .first()
    )


def login(db: Session, email: str, password: str, *, ip: str | None = None) -> tuple[TokenPair, UserOut]:
    user = (
        db.query(User)
        .options(
            joinedload(User.role)
            .joinedload(Role.permissions)
            .joinedload(RolePermission.permission)
        )
        .filter(User.email == email.lower(), User.deleted_at.is_(None))
        .first()
    )
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled")

    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=refresh_expiry(),
        )
    )
    user.last_login_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user=user,
        action="LOGIN",
        entity_type="user",
        entity_id=user.id,
        details={"ip": ip} if ip else {},
    )
    db.commit()
    return TokenPair(access_token=access, refresh_token=refresh), to_user_out(user)


def logout(db: Session, refresh_token: str, user: User) -> None:
    db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(refresh_token)).update({"revoked": True})
    record_audit(db, user=user, action="LOGOUT", entity_type="user", entity_id=user.id)
    db.commit()


def refresh_tokens(db: Session, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token, "refresh")
    stored = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_token(refresh_token), RefreshToken.revoked.is_(False))
        .first()
    )
    if stored is None:
        raise UnauthorizedError("Refresh token is not recognized")
    user = _load_user(db, payload["sub"])
    if user is None or not user.is_active:
        raise UnauthorizedError("Account not found")
    stored.revoked = True
    access = create_access_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(new_refresh), expires_at=refresh_expiry()))
    db.commit()
    return TokenPair(access_token=access, refresh_token=new_refresh)
