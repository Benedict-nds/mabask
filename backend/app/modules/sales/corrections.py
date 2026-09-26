from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.responses import ConflictError, NotFoundError, ValidationAppError
from app.core.schemas import (
    CorrectionApproveIn,
    CorrectionOut,
    CorrectionRejectIn,
    CorrectionRequestIn,
    ReturnCreate,
    ReturnItemIn,
    SaleCreate,
    SaleItemIn,
)
from app.models import CorrectionStatus, Sale, SaleCorrectionRequest, SaleStatus, User
from app.modules.audit.service import record_audit
from app.modules.sales import returns as returns_svc
from app.modules.sales import service as sales_svc


def _load_request(db: Session, request_id: str, *, for_update: bool = False) -> SaleCorrectionRequest:
    query = db.query(SaleCorrectionRequest).options(
        joinedload(SaleCorrectionRequest.sale).joinedload(Sale.items),
        joinedload(SaleCorrectionRequest.sale).joinedload(Sale.cashier),
        joinedload(SaleCorrectionRequest.requester),
        joinedload(SaleCorrectionRequest.reviewer),
        joinedload(SaleCorrectionRequest.return_record),
        joinedload(SaleCorrectionRequest.corrected_sale),
    )
    if for_update:
        locked = db.query(SaleCorrectionRequest).filter(SaleCorrectionRequest.id == request_id).with_for_update().first()
        if locked is None:
            raise NotFoundError("Correction request not found")
    row = query.filter(SaleCorrectionRequest.id == request_id).first()
    if row is None:
        raise NotFoundError("Correction request not found")
    return row


def correction_reference(request_id: str) -> str:
    """Stable human-readable reference derived from the request id (no separate sequence column)."""
    return f"CR-{request_id.replace('-', '')[:8].upper()}"


def to_correction_out(db: Session, row: SaleCorrectionRequest, *, include_sales: bool = False) -> CorrectionOut:
    sale = row.sale
    corrected = row.corrected_sale
    ret = row.return_record
    refund = Decimal(ret.refund_amount) if ret else None
    corrected_total = Decimal(corrected.total) if corrected else None
    financial_difference = None
    if refund is not None and corrected_total is not None:
        financial_difference = sales_svc.money(corrected_total - refund)

    return CorrectionOut(
        id=row.id,
        reference=correction_reference(row.id),
        sale_id=row.sale_id,
        sale_number=sale.sale_number if sale else None,
        sale_total=sale.total if sale else None,
        sale_created_at=sale.created_at if sale else None,
        sale_cashier_name=sale.cashier.full_name if sale and sale.cashier else None,
        requested_by=row.requested_by,
        requested_by_name=row.requester.full_name if row.requester else None,
        reason=row.reason,
        status=row.status.value,
        reviewed_by=row.reviewed_by,
        reviewed_by_name=row.reviewer.full_name if row.reviewer else None,
        reviewed_at=row.reviewed_at,
        review_note=row.review_note or "",
        return_id=row.return_id,
        return_number=ret.return_number if ret else None,
        refund_amount=refund,
        corrected_sale_id=row.corrected_sale_id,
        corrected_sale_number=corrected.sale_number if corrected else None,
        corrected_sale_total=corrected_total,
        financial_difference=financial_difference,
        created_at=row.created_at,
        sale=sales_svc.to_sale_out(sales_svc._load(db, sale.id), db) if include_sales and sale else None,
        corrected_sale=(
            sales_svc.to_sale_out(sales_svc._load(db, corrected.id), db) if include_sales and corrected else None
        ),
    )


def list_corrections(
    db: Session, status: str | None = None, limit: int = 50, offset: int = 0, q: str | None = None
) -> tuple[list[SaleCorrectionRequest], int]:
    query = db.query(SaleCorrectionRequest).options(
        joinedload(SaleCorrectionRequest.sale).joinedload(Sale.cashier),
        joinedload(SaleCorrectionRequest.requester),
        joinedload(SaleCorrectionRequest.reviewer),
        joinedload(SaleCorrectionRequest.return_record),
        joinedload(SaleCorrectionRequest.corrected_sale),
    )
    if status:
        try:
            query = query.filter(SaleCorrectionRequest.status == CorrectionStatus(status))
        except ValueError as exc:
            raise ValidationAppError("Invalid correction status") from exc
    if q and q.strip():
        term = q.strip()
        like = f"%{term}%"
        ref = term.upper().removeprefix("CR-").replace("-", "").lower()
        conditions = [
            SaleCorrectionRequest.sale.has(Sale.sale_number.ilike(like)),
            SaleCorrectionRequest.reason.ilike(like),
        ]
        if ref:
            conditions.append(func.replace(SaleCorrectionRequest.id, "-", "").ilike(f"{ref}%"))
        query = query.filter(or_(*conditions))
    total = query.count()
    rows = query.order_by(SaleCorrectionRequest.created_at.desc()).offset(offset).limit(limit).all()
    return rows, total


def get_correction(db: Session, request_id: str) -> CorrectionOut:
    return to_correction_out(db, _load_request(db, request_id), include_sales=True)


def request_correction(db: Session, sale_id: str, data: CorrectionRequestIn, actor: User) -> CorrectionOut:
    reason = data.reason.strip()
    if not reason:
        raise ValidationAppError("A correction reason is required")

    sale = db.query(Sale).filter(Sale.id == sale_id).with_for_update().first()
    if sale is None:
        raise NotFoundError("Sale not found")
    if sale.status == SaleStatus.REFUNDED:
        raise ValidationAppError("Fully refunded sales cannot be corrected")

    pending = (
        db.query(SaleCorrectionRequest)
        .filter(
            SaleCorrectionRequest.sale_id == sale_id,
            SaleCorrectionRequest.status == CorrectionStatus.PENDING,
        )
        .first()
    )
    if pending is not None:
        raise ConflictError("A pending correction request already exists for this sale")

    approved = (
        db.query(SaleCorrectionRequest)
        .filter(
            SaleCorrectionRequest.sale_id == sale_id,
            SaleCorrectionRequest.status == CorrectionStatus.APPROVED,
        )
        .first()
    )
    if approved is not None:
        raise ConflictError("This sale already has an approved correction")

    returnable = sum(i.quantity - i.quantity_returned for i in sale.items)
    if returnable <= 0:
        raise ValidationAppError("This sale has no returnable items left to correct")

    row = SaleCorrectionRequest(
        sale_id=sale.id,
        requested_by=actor.id,
        reason=reason,
        status=CorrectionStatus.PENDING,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        user=actor,
        action="SALE_CORRECTION_REQUESTED",
        entity_type="sale_correction",
        entity_id=row.id,
        details={
            "sale_id": sale.id,
            "sale_number": sale.sale_number,
            "reason": reason,
            "status": CorrectionStatus.PENDING.value,
        },
    )
    db.commit()
    return to_correction_out(db, _load_request(db, row.id), include_sales=True)


def reject_correction(db: Session, request_id: str, data: CorrectionRejectIn, actor: User) -> CorrectionOut:
    reason = data.reason.strip()
    if not reason:
        raise ValidationAppError("A rejection reason is required")

    row = _load_request(db, request_id, for_update=True)
    if row.status != CorrectionStatus.PENDING:
        raise ValidationAppError("Only pending correction requests can be rejected")

    previous = row.status.value
    row.status = CorrectionStatus.REJECTED
    row.reviewed_by = actor.id
    row.reviewed_at = datetime.now(timezone.utc)
    row.review_note = reason
    record_audit(
        db,
        user=actor,
        action="SALE_CORRECTION_REJECTED",
        entity_type="sale_correction",
        entity_id=row.id,
        details={
            "sale_id": row.sale_id,
            "sale_number": row.sale.sale_number if row.sale else None,
            "requested_by": row.requested_by,
            "requester_name": row.requester.full_name if row.requester else None,
            "reviewer_id": actor.id,
            "rejection_reason": reason,
            "previous_status": previous,
            "new_status": CorrectionStatus.REJECTED.value,
        },
    )
    db.commit()
    return to_correction_out(db, _load_request(db, row.id), include_sales=True)


def approve_correction(db: Session, request_id: str, data: CorrectionApproveIn, actor: User) -> CorrectionOut:
    if not data.idempotency_key.strip():
        raise ValidationAppError("idempotency_key is required")
    if not data.items:
        raise ValidationAppError("Corrected sale must include at least one item")

    existing_key = (
        db.query(SaleCorrectionRequest)
        .filter(SaleCorrectionRequest.approval_idempotency_key == data.idempotency_key)
        .first()
    )
    if existing_key is not None and existing_key.id != request_id:
        raise ConflictError("That approval idempotency key was already used")

    row = _load_request(db, request_id, for_update=True)

    if row.status == CorrectionStatus.APPROVED:
        if row.approval_idempotency_key == data.idempotency_key:
            return to_correction_out(db, row, include_sales=True)
        raise ConflictError("This correction was already approved")
    if row.status != CorrectionStatus.PENDING:
        raise ValidationAppError("Only pending correction requests can be approved")

    sale = sales_svc._load(db, row.sale_id)
    if sale.status == SaleStatus.REFUNDED:
        raise ValidationAppError("Fully refunded sales cannot be corrected")

    return_items = [
        ReturnItemIn(sale_item_id=item.id, quantity=item.quantity - item.quantity_returned)
        for item in sale.items
        if item.quantity - item.quantity_returned > 0
    ]
    if not return_items:
        raise ValidationAppError("This sale has no returnable items left to correct")

    try:
        ret = returns_svc.process_return(
            db,
            ReturnCreate(
                sale_id=sale.id,
                reason=f"Sale correction: {row.reason}",
                restock=True,
                items=return_items,
            ),
            actor,
            commit=False,
        )
        corrected = sales_svc.complete_sale(
            db,
            SaleCreate(
                items=[SaleItemIn(product_id=i.product_id, quantity=i.quantity) for i in data.items],
                payment_method=data.payment_method,
                amount_tendered=data.amount_tendered,
                discount_percent=data.discount_percent,
                tax_rate=data.tax_rate,
                customer_id=data.customer_id or sale.customer_id,
                customer_name=data.customer_name,
                idempotency_key=data.idempotency_key,
                notes=data.notes or f"Correction of {sale.sale_number}",
            ),
            actor,
            commit=False,
        )

        previous = row.status.value
        row.status = CorrectionStatus.APPROVED
        row.reviewed_by = actor.id
        row.reviewed_at = datetime.now(timezone.utc)
        row.review_note = data.review_note.strip()
        row.return_id = ret.id
        row.corrected_sale_id = corrected.id
        row.approval_idempotency_key = data.idempotency_key

        financial_difference = sales_svc.money(Decimal(corrected.total) - Decimal(ret.refund_amount))
        record_audit(
            db,
            user=actor,
            action="SALE_CORRECTION_APPROVED",
            entity_type="sale_correction",
            entity_id=row.id,
            details={
                "sale_id": sale.id,
                "sale_number": sale.sale_number,
                "corrected_sale_id": corrected.id,
                "corrected_sale_number": corrected.sale_number,
                "return_id": ret.id,
                "return_number": ret.return_number,
                "refund_amount": str(ret.refund_amount),
                "corrected_total": str(corrected.total),
                "financial_difference": str(financial_difference),
                "reason": row.reason,
                "previous_status": previous,
                "new_status": CorrectionStatus.APPROVED.value,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return to_correction_out(db, _load_request(db, row.id), include_sales=True)
