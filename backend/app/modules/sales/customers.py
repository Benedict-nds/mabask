from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.responses import NotFoundError
from app.models import Customer
from app.core.schemas import CustomerCreate, CustomerOut, CustomerUpdate


def to_customer_out(c: Customer) -> CustomerOut:
    return CustomerOut(id=c.id, name=c.name, phone=c.phone, email=c.email, notes=c.notes)


def list_customers(db: Session, q: str | None = None) -> list[CustomerOut]:
    query = db.query(Customer).filter(Customer.deleted_at.is_(None))
    if q:
        query = query.filter(Customer.name.ilike(f"%{q}%"))
    return [to_customer_out(c) for c in query.order_by(Customer.name).all()]


def get_customer(db: Session, customer_id: str) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.deleted_at.is_(None)).first()
    if customer is None:
        raise NotFoundError("Customer not found")
    return customer


def create_customer(db: Session, data: CustomerCreate) -> CustomerOut:
    customer = Customer(name=data.name.strip(), phone=data.phone, email=data.email, notes=data.notes)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return to_customer_out(customer)


def update_customer(db: Session, customer_id: str, data: CustomerUpdate) -> CustomerOut:
    customer = get_customer(db, customer_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, key, value)
    db.commit()
    return to_customer_out(customer)


def get_or_create_walkin(db: Session, name: str) -> Customer:
    existing = db.query(Customer).filter(Customer.name == name.strip(), Customer.deleted_at.is_(None)).first()
    if existing:
        return existing
    customer = Customer(name=name.strip())
    db.add(customer)
    db.flush()
    return customer


def delete_customer(db: Session, customer_id: str) -> None:
    customer = get_customer(db, customer_id)
    customer.deleted_at = datetime.now(timezone.utc)
    db.commit()
