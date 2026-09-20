import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: str = "",
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Attach an audit row to the current session. It commits with the caller."""
    entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details or {}, default=str),
    )
    db.add(entry)
    return entry
