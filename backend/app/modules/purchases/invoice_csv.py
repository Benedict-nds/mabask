"""Supplier invoice CSV parsing: Quantity, Description, Rate, Discount, Amount/Extended, Expiry.

Header matching is exact after normalisation (case, spacing, punctuation, parenthesised
units), never substring-based, so unrelated columns are ignored rather than misread.
"""

from __future__ import annotations

import calendar
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.dates import parse_expiry

CENT = Decimal("0.01")

# Ordered by priority: when a file has two headers for the same field, the earlier alias wins.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": (
        "description",
        "product description",
        "item description",
        "description of goods",
        "product",
        "product name",
        "item",
        "item name",
        "medicine",
        "medicine name",
        "drug",
        "drug name",
        "name",
    ),
    "quantity": ("quantity", "qty", "quantity supplied", "qty supplied", "quantity received", "qty received"),
    "rate": ("rate", "unit rate", "unit price", "unit cost", "cost price", "cost", "price"),
    "discount": (
        "discount",
        "disc",
        "discount %",
        "disc %",
        "discount percent",
        "discount pct",
        "discount amount",
        "discount amt",
        "disc amount",
        "disc amt",
        "discount value",
    ),
    "amount": (
        "amount",
        "extended",
        "extended amount",
        "ext amount",
        "extended price",
        "ext price",
        "extension",
        "line total",
        "line amount",
        "net amount",
        "total",
    ),
    "expiry": ("expiry", "expiry date", "exp", "exp date", "expiration", "expiration date", "expires"),
    "batch": ("batch", "batch number", "batch no", "batch num", "lot", "lot number", "lot no", "batch lot", "batch lot no"),
    "selling_price": ("selling price", "selling", "sell price", "retail price", "retail", "sale price"),
}

REQUIRED_FIELDS = ("name", "quantity", "rate")
FIELD_LABELS = {
    "name": "Description",
    "quantity": "Quantity",
    "rate": "Rate",
    "discount": "Discount",
    "amount": "Amount/Extended",
    "expiry": "Expiry",
    "batch": "Batch",
    "selling_price": "Selling price",
}

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name}
_MONTH_YEAR_NUM = re.compile(r"^(\d{1,2})\s*[/\-.]\s*(\d{2}|\d{4})$")
_YEAR_MONTH_NUM = re.compile(r"^(\d{4})\s*[/\-.]\s*(\d{1,2})$")
_MONTH_YEAR_TEXT = re.compile(r"^([a-z]{3,9})\.?\s*[/\-.\s]\s*(\d{2}|\d{4})$")


def normalize_header(header: str) -> str:
    text = header.replace("\ufeff", "").strip().lower()
    text = re.sub(r"\((?!%\)).*?\)", " ", text)  # drop units like "(GHS)" but keep "(%)"
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    return " ".join(text.split())


def map_headers(headers: list[str]) -> tuple[dict[str, int], list[str]]:
    """Map canonical fields to column indexes. Returns (mapping, ignored original headers)."""
    normalized = [normalize_header(h) for h in headers]
    mapping: dict[str, int] = {}
    for field_name, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                index = normalized.index(alias)
                if index not in mapping.values():
                    mapping[field_name] = index
                    break
    used = set(mapping.values())
    ignored = [h.strip() for i, h in enumerate(headers) if i not in used and h.strip()]
    return mapping, ignored


def discount_mode_from_header(header: str) -> str | None:
    lowered = header.lower()
    if "%" in lowered or "percent" in lowered or "pct" in lowered:
        return "percent"
    if any(word in lowered for word in ("amount", "amt", "value", "ghs", "gh₵", "₵", "cedi")):
        return "amount"
    return None


def parse_number(raw: str) -> Decimal | None:
    """Parse invoice numbers: '1,200.50', 'GH₵ 5.00', '5 %'. Blank or unreadable -> None."""
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"(?i)gh[s₵¢c]?|₵|¢|\$|%", "", text)
    text = text.replace(",", "").replace(" ", "")
    if not text or text in {"-", "."}:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_invoice_expiry(raw: str) -> date | None:
    """Full dates via the shared parser; month/year (04/2027, Apr-27, 2027-04) -> last day of month."""
    text = (raw or "").strip()
    if not text:
        return None
    parsed = parse_expiry(text, required=False)
    if parsed is not None:
        return parsed
    lowered = text.lower()
    month = year = None
    if match := _MONTH_YEAR_NUM.match(lowered):
        month, year = int(match[1]), int(match[2])
    elif match := _YEAR_MONTH_NUM.match(lowered):
        year, month = int(match[1]), int(match[2])
    elif match := _MONTH_YEAR_TEXT.match(lowered):
        month = _MONTHS.get(match[1][:3])
        year = int(match[2])
    if not month or not year or not 1 <= month <= 12:
        return None
    if year < 100:
        year += 2000
    return date(year, month, calendar.monthrange(year, month)[1])


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def markup_price(cost: Decimal, markup_percent: Decimal) -> Decimal:
    """selling = cost x (1 + markup/100), rounded to the cent."""
    return money(Decimal(cost) * (Decimal(1) + Decimal(markup_percent) / Decimal(100)))


def line_amounts(quantity: int, rate: Decimal, discount: Decimal, mode: str) -> tuple[Decimal, Decimal, Decimal]:
    """Return (gross, discount_amount, net). Percent discounts apply to the gross line."""
    gross = Decimal(quantity) * Decimal(rate)
    if mode == "percent":
        discount_amount = gross * Decimal(discount) / Decimal(100)
    else:
        discount_amount = Decimal(discount)
    return money(gross), money(discount_amount), money(gross - discount_amount)


def amount_tolerance(quantity: int) -> Decimal:
    """One cent, plus half a cent per unit for rates printed rounded to the cent."""
    return CENT + Decimal(quantity) * Decimal("0.005")


@dataclass
class ParsedRow:
    row: int
    description: str
    quantity: int
    rate: Decimal
    discount: Decimal | None
    amount: Decimal | None
    selling_price: Decimal | None
    batch: str
    expiry: date | None
    expiry_raw: str
    issues: list[str] = field(default_factory=list)


@dataclass
class ParsedInvoice:
    columns: dict[str, str]
    ignored_columns: list[str]
    discount_mode: str
    discount_mode_source: str
    rows: list[ParsedRow]
    skipped: list[tuple[int, str, str]]


class InvoiceColumnsError(ValueError):
    pass


def _read_rows(text: str) -> list[list[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int], list[str]]:
    best: tuple[int, dict[str, int], list[str]] | None = None
    for index, row in enumerate(rows[:20]):
        mapping, ignored = map_headers(row)
        if all(f in mapping for f in REQUIRED_FIELDS):
            return index, mapping, ignored
        if best is None or len(mapping) > len(best[1]):
            best = (index, mapping, ignored)
    if best is None:
        raise InvoiceColumnsError("The file is empty.")
    _, mapping, _ = best
    missing = [FIELD_LABELS[f] for f in REQUIRED_FIELDS if f not in mapping]
    found = [c.strip() for c in rows[best[0]] if c.strip()]
    raise InvoiceColumnsError(
        f"Missing required column(s): {', '.join(missing)}. Found: {', '.join(found) or 'none'}. "
        "Expected columns like Quantity, Description, Rate, Discount, Amount, Expiry."
    )


def parse_invoice_csv(text: str) -> ParsedInvoice:
    rows = _read_rows(text)
    header_index, mapping, ignored = _find_header(rows)
    headers = rows[header_index]
    columns = {f: headers[i].strip() for f, i in mapping.items()}

    def cell(cells: list[str], field_name: str) -> str:
        index = mapping.get(field_name)
        if index is None or index >= len(cells):
            return ""
        return cells[index].strip()

    data_rows = rows[header_index + 1 :]
    discount_mode, discount_source = "percent", "default: percentage, matching the app's discount convention"
    if "discount" in mapping:
        from_header = discount_mode_from_header(columns["discount"])
        if from_header:
            discount_mode, discount_source = from_header, f"column name “{columns['discount']}”"
        elif any("%" in cell(r, "discount") for r in data_rows):
            discount_mode, discount_source = "percent", "values contain %"

    parsed: list[ParsedRow] = []
    skipped: list[tuple[int, str, str]] = []
    for offset, cells in enumerate(data_rows):
        row_no = header_index + 2 + offset
        description = cell(cells, "name")
        qty_raw = cell(cells, "quantity")
        if not any(c.strip() for c in cells):
            continue
        if not qty_raw:
            skipped.append((row_no, "No quantity (treated as a note or total row)", " ".join(c.strip() for c in cells if c.strip())[:120]))
            continue
        issues: list[str] = []
        if not description:
            issues.append("Description is blank")

        quantity = 0
        qty_value = parse_number(qty_raw)
        if qty_value is None:
            issues.append(f"Quantity “{qty_raw}” is not a number")
        elif qty_value <= 0:
            issues.append("Quantity must be above 0")
        elif qty_value != qty_value.to_integral_value():
            issues.append(f"Quantity {qty_raw} must be a whole number of units")
        else:
            quantity = int(qty_value)

        rate_raw = cell(cells, "rate")
        rate = parse_number(rate_raw)
        if rate is None:
            issues.append("Rate is missing" if not rate_raw else f"Rate “{rate_raw}” is not a number")
            rate = Decimal("0")
        elif rate < 0:
            issues.append("Rate cannot be negative")

        discount_raw = cell(cells, "discount")
        discount = parse_number(discount_raw) if discount_raw else Decimal("0")
        if discount is None:
            issues.append(f"Discount “{discount_raw}” is not a number")
        elif discount < 0:
            issues.append("Discount cannot be negative")

        amount_raw = cell(cells, "amount")
        amount = parse_number(amount_raw) if amount_raw else None
        if amount_raw and amount is None:
            issues.append(f"Amount “{amount_raw}” is not a number")

        selling_raw = cell(cells, "selling_price")
        selling = parse_number(selling_raw) if selling_raw else None
        if selling_raw and selling is None:
            issues.append(f"Selling price “{selling_raw}” is not a number")

        expiry_raw = cell(cells, "expiry")
        expiry = parse_invoice_expiry(expiry_raw)
        if expiry_raw and expiry is None:
            issues.append(f"Could not read expiry “{expiry_raw}”")

        parsed.append(
            ParsedRow(
                row=row_no,
                description=description,
                quantity=quantity,
                rate=rate,
                discount=discount,
                amount=amount,
                selling_price=selling,
                batch=cell(cells, "batch"),
                expiry=expiry,
                expiry_raw=expiry_raw,
                issues=issues,
            )
        )
    return ParsedInvoice(
        columns=columns,
        ignored_columns=ignored,
        discount_mode=discount_mode,
        discount_mode_source=discount_source if "discount" in mapping else "no discount column",
        rows=parsed,
        skipped=skipped,
    )
