from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.responses import UnauthorizedError
from app.models import Role, RolePermission, User
from app.core.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise UnauthorizedError()
    payload = decode_token(creds.credentials, "access")
    user = (
        db.query(User)
        .options(
            joinedload(User.role)
            .joinedload(Role.permissions)
            .joinedload(RolePermission.permission)
        )
        .filter(User.id == payload["sub"], User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise UnauthorizedError("Account not found")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled")
    return user
