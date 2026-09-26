"""Confirm a reviewed supplier invoice (CSV or AI-extracted) in one transaction.

Rate is the unit cost price. Selling price precedence per line: explicit selling price, else
cost x (1 + markup/100) for new medicines (and for existing ones only when the user asks).
Stock moves through receive_adhoc, so batches, StockMovement(PURCHASE) and supplier/PO
traceability are identical to manual receiving.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import has_permission
from app.core.responses import ForbiddenError, ValidationAppError
from app.core.schemas import (
    AdhocReceiveIn,
    AdhocReceiveLineIn,
    InvoiceImportIn,
    InvoiceImportOut,
    InvoiceLineIn,
    InvoicePriceOut,
)
from app.models import Product, Supplier, User
from app.modules.audit.service import record_audit
from app.modules.purchases.invoice_csv import amount_tolerance, line_amounts, markup_price, money
from app.modules.purchases.service import receive_adhoc


def _label(index: int, line: InvoiceLineIn) -> str:
    name = line.new_product.name if line.new_product else line.description
    base = f"Line {index}" + (f" (row {line.row})" if line.row else "")
    return f"{base}: {name}" if name else base


def _discount_note(line: InvoiceLineIn, mode: str, discount_amount: Decimal, net: Decimal) -> str:
    if not line.discount:
        return ""
    shown = f"{line.discount.normalize():f}%" if mode == "percent" else f"GHS {money(line.discount)}"
    return f"Invoice discount {shown} (-{discount_amount}); line amount {net}"


def import_supplier_invoice(db: Session, data: InvoiceImportIn, actor: User) -> InvoiceImportOut:
    try:
        return _import(db, data, actor)
    except Exception:
        db.rollback()
        raise


def _import(db: Session, data: InvoiceImportIn, actor: User) -> InvoiceImportOut:
    if not data.items:
        raise ValidationAppError("The invoice has no lines to receive")

    markup = data.markup_percent
    mode = data.discount_mode
    supplier = None
    if data.supplier_id:
        supplier = db.get(Supplier, data.supplier_id)
        if supplier is None:
            raise ValidationAppError("Supplier not found")

    # Validate every line (money, pricing, product choice) before anything is written.
    priced: list[tuple[int, InvoiceLineIn, Decimal, Decimal, Decimal | None, str | None]] = []
    invoice_total = Decimal("0")
    for index, line in enumerate(data.items, start=1):
        label = _label(index, line)
        if bool(line.product_id) == bool(line.new_product):
            raise ValidationAppError(f"{label}: choose an existing medicine or create a new one", {"line": index})
        if mode == "percent" and line.discount > 100:
            raise ValidationAppError(f"{label}: discount cannot exceed 100%", {"line": index})
        gross, discount_amount, net = line_amounts(line.quantity, line.rate, line.discount, mode)
        if mode == "amount" and discount_amount > gross:
            raise ValidationAppError(f"{label}: discount {discount_amount} is larger than the line ({gross})", {"line": index})
        if line.amount is not None and abs(money(line.amount) - net) > amount_tolerance(line.quantity):
            raise ValidationAppError(
                f"{label}: invoice amount {money(line.amount)} does not match {line.quantity} x {line.rate}"
                + (f" less discount {discount_amount}" if discount_amount else "")
                + f" = {net}",
                {"line": index},
            )
        invoice_total += net

        price: Decimal | None = None
        source: str | None = None
        if line.selling_price is not None:
            price, source = money(line.selling_price), "explicit"
        elif line.new_product or data.update_existing_prices:
            if markup is None:
                raise ValidationAppError(
                    f"{label}: enter a selling-price markup % or a selling price for this line", {"line": index}
                )
            price, source = markup_price(line.rate, markup), "markup"
        priced.append((index, line, gross, net, price, source))

    new_lines = [p for p in priced if p[1].new_product]
    if new_lines and not has_permission(actor, "inventory.create"):
        raise ForbiddenError("Creating new medicines needs the inventory.create permission")
    if any(p[4] is not None for p in priced if p[1].product_id) and not has_permission(actor, "inventory.update"):
        raise ForbiddenError("Changing selling prices needs the inventory.update permission")

    existing_ids = {line.product_id for _, line, *_ in priced if line.product_id}
    existing = {p.id: p for p in db.query(Product).filter(Product.id.in_(existing_ids)).all()} if existing_ids else {}
    for index, line, *_ in priced:
        if not line.product_id:
            continue
        product = existing.get(line.product_id)
        if product is None:
            raise ValidationAppError(f"{_label(index, line)}: medicine not found", {"line": index})
        if product.deleted_at is not None:
            raise ValidationAppError(
                f"{_label(index, line)}: {product.name} is archived. Restore it from Inventory before receiving.",
                {"line": index},
            )

    # One product per distinct new name; reject names that already exist (active or archived).
    new_by_name: dict[str, list[tuple[int, InvoiceLineIn, Decimal | None, str | None]]] = {}
    for index, line, _gross, _net, price, source in new_lines:
        key = " ".join(line.new_product.name.lower().split())  # type: ignore[union-attr]
        new_by_name.setdefault(key, []).append((index, line, price, source))
    if new_by_name:
        clashes = (
            db.query(Product)
            .filter(func.lower(Product.name).in_(list(new_by_name)))
            .all()
        )
        for product in clashes:
            index, line, *_ = new_by_name[" ".join(product.name.lower().split())][0]
            if product.deleted_at is not None:
                raise ValidationAppError(
                    f"{_label(index, line)}: matches the archived medicine {product.name}. "
                    "Restore it from Inventory, or use a different name.",
                    {"line": index},
                )
            raise ValidationAppError(
                f"{_label(index, line)}: {product.name} already exists. Select it instead of creating a duplicate.",
                {"line": index},
            )

    price_by_existing: dict[str, tuple[Decimal, str]] = {}
    for index, line, _gross, _net, price, source in priced:
        if not line.product_id or price is None:
            continue
        previous = price_by_existing.setdefault(line.product_id, (price, source or "markup"))
        if previous[0] != price:
            raise ValidationAppError(f"{_label(index, line)}: lines for the same medicine give different selling prices", {"line": index})

    created: list[InvoicePriceOut] = []
    product_for_line: dict[int, str] = {}
    for key, entries in new_by_name.items():
        index, line, price, source = entries[0]
        if any(e[2] != price for e in entries[1:]):
            raise ValidationAppError(f"{_label(index, line)}: lines for the same new medicine give different selling prices", {"line": index})
        assert line.new_product is not None and price is not None
        product = Product(
            sku=None,
            barcode=None,
            name=line.new_product.name.strip(),
            category="General",
            cost_price=line.rate,
            selling_price=price,
            reorder_threshold=line.new_product.reorder_threshold,
            supplier_id=supplier.id if supplier else None,
            is_active=True,
            quantity_on_hand=0,
        )
        db.add(product)
        db.flush()
        record_audit(
            db,
            user=actor,
            action="PRODUCT_CREATED",
            entity_type="product",
            entity_id=product.id,
            details={
                "name": product.name,
                "sku": None,
                "source": f"{data.source} import",
                "cost_price": str(line.rate),
                "selling_price": str(price),
                "price_source": source,
                "markup_percent": str(markup) if source == "markup" else None,
            },
        )
        created.append(
            InvoicePriceOut(
                product_id=product.id,
                product_name=product.name,
                cost_price=line.rate,
                new_selling_price=price,
                price_source=source,  # type: ignore[arg-type]
            )
        )
        for entry in entries:
            product_for_line[entry[0]] = product.id

    header_notes = data.notes.strip() or f"{data.source} import"
    receipt = receive_adhoc(
        db,
        AdhocReceiveIn(
            supplier_id=supplier.id if supplier else None,
            notes=header_notes,
            items=[
                AdhocReceiveLineIn(
                    product_id=line.product_id or product_for_line[index],
                    quantity=line.quantity,
                    unit_cost=line.rate,
                    batch_number=line.batch_number,
                    expiry_date=line.expiry_date,
                    notes=_discount_note(line, mode, *line_amounts(line.quantity, line.rate, line.discount, mode)[1:])[:200],
                )
                for index, line, *_ in priced
            ],
        ),
        actor,
        commit=False,
    )

    updates: list[InvoicePriceOut] = []
    for product_id, (price, source) in price_by_existing.items():
        product = existing[product_id]
        old = product.selling_price
        if money(Decimal(old)) == price:
            continue
        product.selling_price = price
        record_audit(
            db,
            user=actor,
            action="PRODUCT_UPDATED",
            entity_type="product",
            entity_id=product.id,
            details={
                "changes": [f"selling price {money(Decimal(old))} -> {price}"],
                "source": f"{data.source} import",
                "price_source": source,
                "markup_percent": str(markup) if source == "markup" else None,
            },
        )
        updates.append(
            InvoicePriceOut(
                product_id=product.id,
                product_name=product.name,
                cost_price=product.cost_price,
                old_selling_price=old,
                new_selling_price=price,
                price_source=source,  # type: ignore[arg-type]
            )
        )

    record_audit(
        db,
        user=actor,
        action="INVOICE_IMPORTED",
        entity_type="purchase_order" if receipt.purchase_order_id else "manual_receipt",
        entity_id=receipt.purchase_order_id or receipt.receipt_id or receipt.reference,
        details={
            "reference": receipt.reference,
            "source": data.source,
            "supplier": receipt.supplier_name or "Not recorded",
            "markup_percent": str(markup) if markup is not None else None,
            "discount_mode": mode,
            "lines": len(priced),
            "units": receipt.units_received,
            "invoice_total": str(money(invoice_total)),
            "new_medicines": [c.product_name for c in created][:25],
            "price_updates": [f"{u.product_name}: {money(Decimal(u.old_selling_price or 0))} -> {u.new_selling_price}" for u in updates][:25],
        },
    )
    db.commit()
    return InvoiceImportOut(
        receipt=receipt,
        markup_percent=markup,
        discount_mode=mode,
        invoice_total=money(invoice_total),
        created_products=created,
        price_updates=updates,
    )
