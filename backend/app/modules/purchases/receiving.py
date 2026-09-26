from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dates import parse_expiry
from app.core.responses import ValidationAppError
from app.models import Product
from app.core.schemas import ExtractedLine, ExtractOut, SkippedRowOut
from app.ai.invoice_ocr import extract_invoice_with_model
from app.modules.purchases.invoice_csv import InvoiceColumnsError, ParsedRow, parse_invoice_csv, parse_number
from app.modules.settings.service import get_default_markup


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


class _Catalog:
    """Active and archived products loaded once per extract, for name matching."""

    def __init__(self, db: Session):
        products = db.query(Product).all()
        self.active = [p for p in products if p.deleted_at is None and p.is_active]
        self.by_name = {}
        for p in self.active:
            self.by_name.setdefault(_norm(p.name), p)
        self.archived = {}
        for p in products:
            if p.deleted_at is not None:
                self.archived.setdefault(_norm(p.name), p)

    def match(self, name: str) -> tuple[Product | None, float]:
        needle = _norm(name)
        if not needle:
            return None, 0.0
        exact = self.by_name.get(needle)
        if exact is not None:
            return exact, 0.98
        partial = [p for p in self.active if needle in _norm(p.name) or _norm(p.name) in needle]
        if len(partial) == 1:
            return partial[0], 0.82
        return None, 0.45

    def archived_match(self, name: str) -> Product | None:
        return self.archived.get(_norm(name))


def _line(catalog: _Catalog, row: ParsedRow) -> ExtractedLine:
    product, confidence = catalog.match(row.description)
    archived = None if product else catalog.archived_match(row.description)
    return ExtractedLine(
        name=product.name if product else row.description,
        quantity=row.quantity,
        unit_cost=row.rate,
        batch=row.batch,
        expiry=row.expiry,
        confidence=confidence,
        matched=product is not None,
        product_id=product.id if product else None,
        row=row.row,
        description=row.description,
        discount=row.discount,
        amount=row.amount,
        selling_price=row.selling_price,
        expiry_raw=row.expiry_raw,
        issues=row.issues,
        product_sku=(product.sku or "") if product else "",
        current_cost_price=product.cost_price if product else None,
        current_selling_price=product.selling_price if product else None,
        archived_product_id=archived.id if archived else None,
        archived_product_name=archived.name if archived else None,
    )


def _rows_from_ai(parsed: list[dict]) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    for index, item in enumerate(parsed, start=1):
        name = str(item.get("name") or item.get("description") or "").strip()
        if not name:
            continue
        qty = parse_number(str(item.get("quantity") or ""))
        cost = parse_number(str(item.get("unit_cost") or item.get("rate") or ""))
        expiry_raw = str(item.get("expiry") or "")
        issues = []
        if qty is None or qty <= 0 or qty != qty.to_integral_value():
            issues.append("Check the quantity")
        if cost is None:
            issues.append("Rate is missing")
        rows.append(
            ParsedRow(
                row=index,
                description=name,
                quantity=int(qty) if qty is not None and qty > 0 and qty == qty.to_integral_value() else 0,
                rate=cost if cost is not None else Decimal("0"),
                discount=None,
                amount=None,
                selling_price=None,
                batch=str(item.get("batch") or "").strip(),
                expiry=parse_expiry(expiry_raw, required=False),
                expiry_raw=expiry_raw,
                issues=issues,
            )
        )
    return rows


def _looks_like_csv(filename: str, content_type: str, text: str) -> bool:
    if filename.lower().endswith(".csv") or content_type.endswith("csv"):
        return True
    first = text.splitlines()[0] if text else ""
    return "," in first or ";" in first or "\t" in first


def extract_invoice(db: Session, filename: str, raw: bytes, content_type: str) -> ExtractOut:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="ignore")

    catalog = _Catalog(db)
    out = ExtractOut(items=[], default_markup_percent=get_default_markup(db))
    column_error: str | None = None
    explicit_csv = filename.lower().endswith(".csv") or content_type.endswith("csv")

    if text.strip() and _looks_like_csv(filename, content_type, text):
        try:
            parsed = parse_invoice_csv(text)
        except InvoiceColumnsError as exc:
            column_error = str(exc)
        else:
            out.columns = parsed.columns
            out.ignored_columns = parsed.ignored_columns
            out.discount_mode = parsed.discount_mode  # type: ignore[assignment]
            out.discount_mode_source = parsed.discount_mode_source
            out.skipped_rows = [SkippedRowOut(row=r, reason=why, text=t) for r, why, t in parsed.skipped]
            out.items = [_line(catalog, row) for row in parsed.rows]

    if not out.items and get_settings().ai_enabled and not (explicit_csv and column_error is None and out.columns):
        try:
            ai_rows = _rows_from_ai(extract_invoice_with_model(text[:12000]))
        except Exception:
            ai_rows = []
        if ai_rows:
            out.source = "ai"
            out.columns = {}
            out.items = [_line(catalog, row) for row in ai_rows]

    if not out.items:
        if column_error:
            raise ValidationAppError(column_error)
        if out.columns:
            raise ValidationAppError("The CSV has the right columns but no item rows with a quantity.")
        raise ValidationAppError(
            "Could not read line items. Upload a CSV with columns Quantity, Description, Rate "
            "(optional: Discount, Amount/Extended, Expiry). Free-form invoice reading needs an AI provider "
            "and an internet connection."
        )

    matched = next((i for i in out.items if i.product_id), None)
    if matched:
        product = next((p for p in catalog.active if p.id == matched.product_id), None)
        if product and product.supplier:
            out.supplier_id = product.supplier_id
            out.supplier_name = product.supplier.name
    return out
