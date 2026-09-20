from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.audit.service import record_audit
from app.core.responses import ConflictError, NotFoundError, ValidationAppError
from app.models import POStatus, Product, PurchaseOrder, Supplier, SupplierStatus, User
from app.core.schemas import SupplierCreate, SupplierOut, SupplierUpdate


def _status(value: str) -> SupplierStatus:
    try:
        return SupplierStatus(value)
    except ValueError as exc:
        raise ValidationAppError("Invalid supplier status") from exc


def to_supplier_out(db: Session, supplier: Supplier) -> SupplierOut:
    active_skus = (
        db.query(func.count(Product.id))
        .filter(Product.supplier_id == supplier.id, Product.deleted_at.is_(None), Product.is_active.is_(True))
        .scalar()
        or 0
    )
    outstanding = (
        db.query(func.coalesce(func.sum(PurchaseOrder.total), 0))
        .filter(
            PurchaseOrder.supplier_id == supplier.id,
            PurchaseOrder.status.in_([POStatus.SUBMITTED, POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED]),
        )
        .scalar()
        or 0
    )
    last = (
        db.query(func.max(PurchaseOrder.received_at))
        .filter(PurchaseOrder.supplier_id == supplier.id, PurchaseOrder.received_at.is_not(None))
        .scalar()
    )
    return SupplierOut(
        id=supplier.id,
        name=supplier.name,
        contact_name=supplier.contact_name,
        email=supplier.email,
        phone=supplier.phone,
        address=supplier.address,
        status=supplier.status.value,
        rating=supplier.rating,
        on_time_rate=supplier.on_time_rate,
        notes=supplier.notes,
        active_skus=active_skus,
        outstanding=Decimal(outstanding),
        last_delivery=last.date() if last else None,
    )


def list_suppliers(db: Session, q: str | None = None, status: str | None = None) -> list[SupplierOut]:
    query = db.query(Supplier).filter(Supplier.deleted_at.is_(None))
    if q:
        query = query.filter(Supplier.name.ilike(f"%{q}%"))
    if status:
        query = query.filter(Supplier.status == _status(status))
    return [to_supplier_out(db, s) for s in query.order_by(Supplier.name).all()]


def get_supplier(db: Session, supplier_id: str) -> Supplier:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.deleted_at.is_(None)).first()
    if supplier is None:
        raise NotFoundError("Supplier not found")
    return supplier


def create_supplier(db: Session, data: SupplierCreate, actor: User) -> SupplierOut:
    if db.query(Supplier).filter(Supplier.name == data.name, Supplier.deleted_at.is_(None)).first():
        raise ConflictError("A supplier with that name already exists")
    supplier = Supplier(
        name=data.name,
        contact_name=data.contact_name,
        email=data.email,
        phone=data.phone,
        address=data.address,
        status=_status(data.status),
        rating=data.rating,
        on_time_rate=data.on_time_rate,
        notes=data.notes,
    )
    db.add(supplier)
    db.flush()
    record_audit(db, user=actor, action="SUPPLIER_CREATED", entity_type="supplier", entity_id=supplier.id)
    db.commit()
    return to_supplier_out(db, supplier)


def update_supplier(db: Session, supplier_id: str, data: SupplierUpdate, actor: User) -> SupplierOut:
    supplier = get_supplier(db, supplier_id)
    payload = data.model_dump(exclude_unset=True)
    if "status" in payload:
        payload["status"] = _status(payload["status"])
    for key, value in payload.items():
        setattr(supplier, key, value)
    record_audit(db, user=actor, action="SUPPLIER_UPDATED", entity_type="supplier", entity_id=supplier.id)
    db.commit()
    return to_supplier_out(db, supplier)


def delete_supplier(db: Session, supplier_id: str, actor: User) -> None:
    supplier = get_supplier(db, supplier_id)
    supplier.deleted_at = datetime.now(timezone.utc)
    record_audit(db, user=actor, action="SUPPLIER_DELETED", entity_type="supplier", entity_id=supplier.id)
    db.commit()
