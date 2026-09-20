import csv
import io
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dates import parse_expiry
from app.core.responses import ValidationAppError
from app.models import Product
from app.core.schemas import ExtractedLine, ExtractOut
from app.ai.invoice_ocr import extract_invoice_with_model


def _parse_date(value: str):
    return parse_expiry(value, required=False)


def _match_product(db: Session, name: str) -> Product | None:
    needle = name.strip().lower()
    products = db.query(Product).filter(Product.deleted_at.is_(None), Product.is_active.is_(True)).all()
    exact = [p for p in products if p.name.lower() == needle]
    if exact:
        return exact[0]
    partial = [p for p in products if needle in p.name.lower() or p.name.lower() in needle]
    if len(partial) == 1:
        return partial[0]
    return None


def _lines_from_rows(db: Session, rows: list[dict]) -> list[ExtractedLine]:
    items: list[ExtractedLine] = []
    for row in rows:
        name = str(row.get("name") or row.get("medicine") or row.get("product") or "").strip()
        if not name:
            continue
        try:
            qty = int(float(row.get("quantity") or row.get("qty") or 0))
        except (TypeError, ValueError):
            qty = 0
        try:
            cost = Decimal(str(row.get("unit_cost") or row.get("cost") or row.get("price") or "0"))
        except Exception:
            cost = Decimal("0")
        batch = str(row.get("batch") or row.get("batch_number") or "").strip()
        expiry = _parse_date(str(row.get("expiry") or row.get("expiry_date") or ""))
        product = _match_product(db, name)
        confidence = 0.98 if product and product.name.lower() == name.lower() else 0.82 if product else 0.45
        items.append(
            ExtractedLine(
                name=product.name if product else name,
                quantity=qty,
                unit_cost=cost,
                batch=batch,
                expiry=expiry,
                confidence=confidence,
                matched=product is not None,
                product_id=product.id if product else None,
            )
        )
    return items


def extract_invoice(db: Session, filename: str, raw: bytes, content_type: str) -> ExtractOut:
    text = ""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="ignore")

    items: list[ExtractedLine] = []
    if filename.lower().endswith(".csv") or content_type.endswith("csv") or "," in text.splitlines()[0] if text else False:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames:
            items = _lines_from_rows(db, [dict(r) for r in reader])

    if not items and get_settings().ai_enabled:
        try:
            parsed = extract_invoice_with_model(text[:12000])
            items = _lines_from_rows(db, parsed)
        except Exception:
            items = []

    if not items:
        raise ValidationAppError(
            "Could not read line items. Upload a CSV with columns name,quantity,unit_cost,batch,expiry. "
            "Free-form invoice reading needs an AI provider and an internet connection."
        )

    supplier_id = None
    supplier_name = None
    matched = next((i for i in items if i.product_id), None)
    if matched:
        product = db.get(Product, matched.product_id)
        if product and product.supplier:
            supplier_id = product.supplier_id
            supplier_name = product.supplier.name

    return ExtractOut(supplier_id=supplier_id, supplier_name=supplier_name, items=items)
