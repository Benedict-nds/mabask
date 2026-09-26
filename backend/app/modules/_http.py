from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User
from app.core.permissions import require_permission
from app.core.schemas import (
    CopilotAnswer,
    CopilotAsk,
    CorrectionApproveIn,
    CorrectionOut,
    CorrectionRejectIn,
    CorrectionRequestIn,
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    ExtractOut,
    AdhocReceiveIn,
    ImportReceiveIn,
    InvoiceImportIn,
    InvoiceImportOut,
    POCreate,
    POOut,
    POReviewEditIn,
    Page,
    ReceiptOut,
    ReceiveIn,
    RequestChangesIn,
    ReturnCreate,
    ReturnOut,
    SaleCreate,
    SaleOut,
    SettingsOut,
    SettingsUpdate,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
)
from app.modules.dashboard import service as dashboard_svc
from app.modules.purchases import invoice_import as invoice_import_svc
from app.modules.purchases import receiving as receiving_svc
from app.modules.purchases import service as purchasing_svc
from app.modules.reports import service as reports_svc
from app.modules.sales import corrections as corrections_svc
from app.modules.sales import customers as customers_svc
from app.modules.sales import returns as returns_svc
from app.modules.sales import service as sales_svc
from app.modules.suppliers import service as suppliers_svc
from app.ai.copilot import answer_question
from app.modules.settings.service import get_settings, update_settings
from app.modules.audit.service import record_audit
import json
from datetime import date as date_cls

from app.models import AuditLog

suppliers_router = APIRouter(prefix="/suppliers", tags=["suppliers"])
purchases_router = APIRouter(prefix="/purchase-orders", tags=["purchasing"])
receiving_router = APIRouter(prefix="/receiving", tags=["receiving"])
sales_router = APIRouter(prefix="/sales", tags=["sales"])
returns_router = APIRouter(prefix="/returns", tags=["returns"])
corrections_router = APIRouter(prefix="/sale-corrections", tags=["sale-corrections"])
customers_router = APIRouter(prefix="/customers", tags=["customers"])
reports_router = APIRouter(prefix="/reports", tags=["reports"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
settings_router = APIRouter(prefix="/settings", tags=["settings"])
copilot_router = APIRouter(prefix="/copilot", tags=["ai"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


@suppliers_router.get("", response_model=list[SupplierOut])
def list_suppliers(q: str | None = None, status: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("suppliers.read"))):
    return suppliers_svc.list_suppliers(db, q, status)


@suppliers_router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("suppliers.create"))):
    return suppliers_svc.create_supplier(db, body, actor)


@suppliers_router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("suppliers.read"))):
    return suppliers_svc.to_supplier_out(db, suppliers_svc.get_supplier(db, supplier_id))


@suppliers_router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: str, body: SupplierUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("suppliers.update"))):
    return suppliers_svc.update_supplier(db, supplier_id, body, actor)


@suppliers_router.delete("/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("suppliers.delete"))):
    suppliers_svc.delete_supplier(db, supplier_id, actor)


@purchases_router.get("", response_model=list[POOut])
def list_pos(status: str | None = None, supplier_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("purchases.read"))):
    return purchasing_svc.list_pos(db, status, supplier_id)


@purchases_router.post("", response_model=POOut, status_code=201)
def create_po(body: POCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.create"))):
    return purchasing_svc.create_po(db, body, actor)


@purchases_router.get("/{po_id}", response_model=POOut)
def get_po(po_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("purchases.read"))):
    return purchasing_svc.to_po_out(purchasing_svc._load(db, po_id))


@purchases_router.put("/{po_id}", response_model=POOut)
def update_po(po_id: str, body: POCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.create"))):
    return purchasing_svc.update_draft(db, po_id, body, actor)


@purchases_router.put("/{po_id}/review-edit", response_model=POOut)
def review_edit_po(
    po_id: str,
    body: POReviewEditIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("purchases.approve")),
):
    """Reviewer edit of a SUBMITTED PO (stays SUBMITTED; reason and line changes are audited)."""
    data = POCreate(supplier_id=body.supplier_id, notes=body.notes, items=body.items)
    return purchasing_svc.review_edit(db, po_id, data, body.reason, actor)


@purchases_router.post("/{po_id}/submit", response_model=POOut)
def submit_po(po_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.create"))):
    return purchasing_svc.submit_po(db, po_id, actor)


@purchases_router.post("/{po_id}/approve", response_model=POOut)
def approve_po(po_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.approve"))):
    return purchasing_svc.approve_po(db, po_id, actor)


@purchases_router.post("/{po_id}/request-changes", response_model=POOut)
def request_po_changes(
    po_id: str,
    body: RequestChangesIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("purchases.approve")),
):
    return purchasing_svc.request_changes(db, po_id, body, actor)


@purchases_router.post("/{po_id}/cancel", response_model=POOut)
def cancel_po(po_id: str, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.approve"))):
    return purchasing_svc.cancel_po(db, po_id, actor)


@purchases_router.post("/{po_id}/receive", response_model=POOut)
def receive_po(po_id: str, body: ReceiveIn, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.receive"))):
    return purchasing_svc.receive_po(db, po_id, body, actor)


@receiving_router.post("/extract", response_model=ExtractOut)
async def extract(file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(require_permission("purchases.receive"))):
    raw = await file.read()
    return receiving_svc.extract_invoice(db, file.filename or "invoice.csv", raw, file.content_type or "")


@receiving_router.post("/import", response_model=POOut)
def import_invoice(body: ImportReceiveIn, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.receive"))):
    return purchasing_svc.import_invoice(db, body, actor)


@receiving_router.post("/manual", response_model=POOut)
def manual_receive(body: ImportReceiveIn, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.receive"))):
    """Ad-hoc multi-line receive without a prior PO. Creates an approved PO then receives (same stock path)."""
    if not body.notes or body.notes == "Invoice import":
        body = body.model_copy(update={"notes": "Manual receiving"})
    return purchasing_svc.import_invoice(db, body, actor)


@receiving_router.post("/adhoc", response_model=ReceiptOut, status_code=201)
def adhoc_receive(body: AdhocReceiveIn, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.receive"))):
    """Multi-line receipt without a prior PO; supplier optional (unrecorded provenance is never invented)."""
    return purchasing_svc.receive_adhoc(db, body, actor)


@receiving_router.post("/invoice", response_model=InvoiceImportOut, status_code=201)
def import_supplier_invoice(body: InvoiceImportIn, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchases.receive"))):
    """Confirm a reviewed invoice: optional new medicines, markup pricing, and receipt in one transaction."""
    return invoice_import_svc.import_supplier_invoice(db, body, actor)


@sales_router.get("", response_model=Page[SaleOut])
def list_sales(
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    cashier_id: str | None = None,
    payment_method: str | None = None,
    status: str | None = None,
    product_id: str | None = None,
    correction: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("sales.read")),
):
    rows, total = sales_svc.list_sales(
        db,
        limit,
        offset,
        q,
        date_from=date_from,
        date_to=date_to,
        cashier_id=cashier_id,
        payment_method=payment_method,
        status=status,
        product_id=product_id,
        correction=correction,
    )
    return Page(items=sales_svc.sales_to_out(db, rows), total=total, limit=limit, offset=offset)


@sales_router.get("/cashiers")
def list_sale_cashiers(db: Session = Depends(get_db), _: User = Depends(require_permission("sales.read"))):
    return sales_svc.list_sale_cashiers(db)


@sales_router.get("/export.csv")
def export_sales_csv(
    q: str | None = None,
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    cashier_id: str | None = None,
    payment_method: str | None = None,
    status: str | None = None,
    product_id: str | None = None,
    correction: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports.read")),
):
    content = sales_svc.export_sales_csv(
        db,
        q=q,
        date_from=date_from,
        date_to=date_to,
        cashier_id=cashier_id,
        payment_method=payment_method,
        status=status,
        product_id=product_id,
        correction=correction,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sales-journal.csv"'},
    )


@sales_router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("sales.read"))):
    return sales_svc.get_sale(db, sale_id)


@sales_router.post("", response_model=SaleOut, status_code=201)
def create_sale(body: SaleCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("sales.create"))):
    return sales_svc.complete_sale(db, body, actor)


@sales_router.post("/{sale_id}/correction-requests", response_model=CorrectionOut, status_code=201)
def request_sale_correction(
    sale_id: str,
    body: CorrectionRequestIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("sales.correction_request")),
):
    return corrections_svc.request_correction(db, sale_id, body, actor)


@returns_router.post("", response_model=ReturnOut, status_code=201)
def create_return(body: ReturnCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("sales.refund"))):
    return returns_svc.process_return(db, body, actor)


@corrections_router.get("", response_model=Page[CorrectionOut])
def list_corrections(
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("sales.correction_approve")),
):
    rows, total = corrections_svc.list_corrections(db, status, limit, offset, q)
    return Page(items=[corrections_svc.to_correction_out(db, r) for r in rows], total=total, limit=limit, offset=offset)


@corrections_router.get("/{request_id}", response_model=CorrectionOut)
def get_correction(request_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("sales.correction_approve"))):
    return corrections_svc.get_correction(db, request_id)


@corrections_router.post("/{request_id}/approve", response_model=CorrectionOut)
def approve_correction(
    request_id: str,
    body: CorrectionApproveIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("sales.correction_approve")),
):
    return corrections_svc.approve_correction(db, request_id, body, actor)


@corrections_router.post("/{request_id}/reject", response_model=CorrectionOut)
def reject_correction(
    request_id: str,
    body: CorrectionRejectIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("sales.correction_approve")),
):
    return corrections_svc.reject_correction(db, request_id, body, actor)


@customers_router.get("", response_model=list[CustomerOut])
def list_customers(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("customers.read"))):
    return customers_svc.list_customers(db, q)


@customers_router.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerCreate, db: Session = Depends(get_db), _: User = Depends(require_permission("customers.create"))):
    return customers_svc.create_customer(db, body)


@customers_router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: str, body: CustomerUpdate, db: Session = Depends(get_db), _: User = Depends(require_permission("customers.update"))):
    return customers_svc.update_customer(db, customer_id, body)


@customers_router.get("/{customer_id}/sales", response_model=list[SaleOut])
def customer_sales(customer_id: str, db: Session = Depends(get_db), _: User = Depends(require_permission("sales.read"))):
    return sales_svc.customer_sales(db, customer_id)


@reports_router.get("/sales")
def report_sales(range: str = "weekly", start: str | None = None, end: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("reports.read"))):
    s = date_cls.fromisoformat(start) if start else None
    e = date_cls.fromisoformat(end) if end else None
    return reports_svc.sales_report(db, range, s, e)


@reports_router.get("/inventory")
def report_inventory(db: Session = Depends(get_db), _: User = Depends(require_permission("reports.read"))):
    return reports_svc.inventory_report(db)


@reports_router.get("/purchasing")
def report_purchasing(db: Session = Depends(get_db), _: User = Depends(require_permission("reports.read"))):
    return reports_svc.purchasing_report(db)


@dashboard_router.get("")
def get_dashboard(db: Session = Depends(get_db), _: User = Depends(require_permission("reports.read"))):
    return dashboard_svc.dashboard(db)


@settings_router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return get_settings(db)


@settings_router.patch("", response_model=SettingsOut)
def patch_settings(body: SettingsUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("settings.manage"))):
    result = update_settings(db, body)
    record_audit(db, user=actor, action="SETTINGS_UPDATED", entity_type="settings", entity_id="pharmacy")
    db.commit()
    return result


@copilot_router.post("/ask", response_model=CopilotAnswer)
def copilot(body: CopilotAsk, db: Session = Depends(get_db), _: User = Depends(require_permission("ai.use"))):
    return answer_question(db, body.question)


@audit_router.get("/facets")
def audit_facets(db: Session = Depends(get_db), _: User = Depends(require_permission("audit.read"))):
    """Distinct actions, entity types and actors actually present, for filter dropdowns."""
    from app.modules.audit.repository import facets

    return facets(db)


@audit_router.get("")
def list_audit(
    limit: int = Query(50, le=200),
    offset: int = 0,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: str | None = None,
    q: str | None = None,
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("audit.read")),
):
    from app.models import User as UserModel
    from app.modules.audit.labels import redact, resolve_entity_labels
    from app.modules.audit.repository import list_filtered

    rows, total = list_filtered(
        db,
        limit=limit,
        offset=offset,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )
    user_ids = {r.user_id for r in rows if r.user_id}
    names = (
        {u.id: u.full_name for u in db.query(UserModel.id, UserModel.full_name).filter(UserModel.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    details_by_id: dict[str, dict] = {}
    for r in rows:
        try:
            parsed = json.loads(r.details or "{}")
        except ValueError:
            parsed = {"raw": r.details}
        details_by_id[r.id] = redact(parsed if isinstance(parsed, dict) else {"value": parsed})
    labels = resolve_entity_labels(db, rows, details_by_id)
    return {
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "actor": names.get(r.user_id),
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "entity_label": labels.get(r.id),
                "details": details_by_id[r.id],
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@notifications_router.get("")
def list_notifications(db: Session = Depends(get_db), _: User = Depends(require_permission("inventory.read"))):
    from app.modules.inventory.service import expiring, low_stock

    notes = []
    for p in low_stock(db)[:10]:
        notes.append(
            {
                "id": f"low-{p.id}",
                "title": "Low stock",
                "message": f"{p.name} is down to {p.quantity_on_hand} units",
                "kind": "warning",
                "is_read": False,
                "created_at": None,
            }
        )
    for b in expiring(db, 30)[:10]:
        notes.append(
            {
                "id": f"exp-{b.id}",
                "title": "Expiring soon",
                "message": f"{b.product.name if b.product else 'Medicine'} batch {b.batch_number} expires {b.expiry_date}",
                "kind": "danger",
                "is_read": False,
                "created_at": None,
            }
        )
    return notes
