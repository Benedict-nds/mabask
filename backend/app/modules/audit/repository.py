from datetime import date, datetime, time, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def list_filtered(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: str | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[AuditLog], int]:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id.strip())
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.filter(AuditLog.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                AuditLog.action.ilike(like),
                AuditLog.entity_type.ilike(like),
                AuditLog.entity_id.ilike(like),
                AuditLog.details.ilike(like),
            )
        )
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return rows, total


def facets(db: Session) -> dict:
    actions = [r[0] for r in db.query(AuditLog.action).distinct().order_by(AuditLog.action.asc()).all()]
    entity_types = [r[0] for r in db.query(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type.asc()).all()]
    users = (
        db.query(User.id, User.full_name)
        .filter(User.id.in_(db.query(AuditLog.user_id).filter(AuditLog.user_id.isnot(None)).distinct()))
        .order_by(User.full_name.asc())
        .all()
    )
    return {"actions": actions, "entity_types": entity_types, "users": [{"id": u[0], "name": u[1]} for u in users]}
