from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import AuditLog


def list_filtered(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    entity_type: str | None = None,
    user_id: str | None = None,
    q: str | None = None,
) -> tuple[list[AuditLog], int]:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(AuditLog.action.ilike(like), AuditLog.entity_type.ilike(like), AuditLog.entity_id.ilike(like)))
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return rows, total
