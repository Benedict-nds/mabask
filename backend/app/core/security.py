from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, email: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": _now() + timedelta(minutes=settings.access_token_expire_minutes),
        "iat": _now(),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": _now() + timedelta(days=settings.refresh_token_expire_days),
        "iat": _now(),
        # Stored hashes are unique; without this, two logins in the same second collide.
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str, expected_type: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        from app.core.responses import UnauthorizedError

        raise UnauthorizedError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        from app.core.responses import UnauthorizedError

        raise UnauthorizedError("Invalid token") from exc
    if payload.get("type") != expected_type:
        from app.core.responses import UnauthorizedError

        raise UnauthorizedError("Invalid token type")
    return payload


def refresh_expiry() -> datetime:
    settings = get_settings()
    return _now() + timedelta(days=settings.refresh_token_expire_days)
