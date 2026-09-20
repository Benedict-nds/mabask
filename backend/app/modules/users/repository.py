from sqlalchemy.orm import Session

from app.models import User


def get_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def list_active(db: Session) -> list[User]:
    return db.query(User).filter(User.deleted_at.is_(None)).all()
