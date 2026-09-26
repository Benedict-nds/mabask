"""Pharmacy invoice format (Quantity, Description, Rate, Discount, Amount/Extended, Expiry),
selling-price markup, and flexible medicine fields."""

from decimal import Decimal

import pytest

from app.modules.purchases.invoice_csv import markup_price, parse_invoice_csv
from tests.conftest import auth_headers

PHARMACY_CSV = (
    "Quantity,Description,Rate,Discount,Amount,Expiry\n"
    "10,Amoxicillin 500mg,5.00,,50.00,2027-04\n"
    "20,Zinc Sulphate 20mg Tabs,8.00,,160.00,\n"
)


def _extract(client, headers, csv_text: str, filename: str = "invoice.csv"):
    res = client.post("/receiving/extract", headers=headers, files={"file": (filename, csv_text, "text/csv")})
    return res


def _line(**overrides):
    line = {
        "description": "Zinc Sulphate 20mg Tabs",
        "new_product": {"name": "Zinc Sulphate 20mg Tabs"},
        "quantity": 20,
        "rate": "8.00",
        "discount": "0",
        "amount": "160.00",
        "batch_number": "ZN-001",
        "expiry_date": "2027-06-30",
    }
    line.update(overrides)
    return line


def _import(client, headers, items, **body):
    payload = {"items": items, "markup_percent": "35", "discount_mode": "percent"}
    payload.update(body)
    return client.post("/receiving/invoice", headers=headers, json=payload)


def _product(client, headers, product_id):
    return client.get(f"/products/{product_id}", headers=headers).json()


# ---------- CSV format ----------


def test_pharmacy_columns_import_with_description_rate_quantity(client):
    headers = auth_headers(client)
    res = _extract(client, headers, PHARMACY_CSV)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["columns"] == {
        "name": "Description",
        "quantity": "Quantity",
        "rate": "Rate",
        "discount": "Discount",
        "amount": "Amount",
        "expiry": "Expiry",
    }
    first, second = body["items"]
    assert first["description"] == "Amoxicillin 500mg" and first["matched"] is True
    assert first["quantity"] == 10
    assert Decimal(first["unit_cost"]) == Decimal("5.00")
    assert Decimal(first["amount"]) == Decimal("50.00")
    assert Decimal(first["discount"]) == 0
    assert first["expiry"] == "2027-04-30"
    assert first["issues"] == []
    assert second["matched"] is False
    assert second["description"] == "Zinc Sulphate 20mg Tabs"
    assert second["expiry"] is None
    assert body["discount_mode"] == "percent"
    assert body["default_markup_percent"] is None


@pytest.mark.parametrize(
    "header",
    [
        "Qty,Item Description,Unit Price,Disc,Extended,Expiry Date",
        "QTY,Product Description,Unit Cost,DISCOUNT,Extended Amount,EXPIRY",
        "quantity,description,rate,discount,amount,expiry",
        " Quantity , Description , Rate (GH₵) , Discount , Amount , Exp Date ",
    ],
)
def test_header_variations_resolve(header):
    parsed = parse_invoice_csv(f"{header}\n10,Amoxicillin 500mg,5.00,,50.00,2027-04-30\n")
    assert set(parsed.columns) == {"name", "quantity", "rate", "discount", "amount", "expiry"}
    row = parsed.rows[0]
    assert (row.quantity, row.rate, row.amount) == (10, Decimal("5.00"), Decimal("50.00"))


def test_unrelated_columns_are_not_misread():
    parsed = parse_invoice_csv(
        "Qty,Description,Rate,Amount,Pack Size,Quantity Remarks,Supplier Code\n5,Paracetamol,2.00,10.00,100s,urgent,SUP-9\n"
    )
    assert parsed.columns["quantity"] == "Qty"
    assert set(parsed.ignored_columns) == {"Pack Size", "Quantity Remarks", "Supplier Code"}


def test_missing_required_columns_explained(client):
    headers = auth_headers(client)
    res = _extract(client, headers, "Item,Pack Size\nParacetamol,100s\n")
    assert res.status_code == 422
    assert "Quantity" in res.json()["error"]["message"] and "Rate" in res.json()["error"]["message"]


def test_extended_column_and_total_rows(client):
    headers = auth_headers(client)
    csv = (
        "ABC Pharma Ltd - Invoice 4471,,,,\n"
        "Qty,Description,Rate,Disc,Extended\n"
        "4,Amoxicillin 500mg,2.50,,10.00\n"
        ",TOTAL,,,10.00\n"
    )
    body = _extract(client, headers, csv).json()
    assert body["columns"]["amount"] == "Extended"
    assert len(body["items"]) == 1
    assert Decimal(body["items"][0]["amount"]) == Decimal("10.00")
    assert body["skipped_rows"][0]["row"] == 4


def test_blank_discount_is_zero_and_populated_discount_is_percent(client):
    headers = auth_headers(client)
    body = _extract(client, headers, "Quantity,Description,Rate,Discount,Amount\n10,Amoxicillin 500mg,5.00,,50.00\n10,Amoxicillin 500mg,5.00,10,45.00\n").json()
    blank, populated = body["items"]
    assert Decimal(blank["discount"]) == 0
    assert Decimal(populated["discount"]) == Decimal("10")
    assert body["discount_mode"] == "percent"

    amount_header = _extract(client, headers, "Quantity,Description,Rate,Discount Amount,Amount\n10,Amoxicillin 500mg,5.00,2.50,47.50\n").json()
    assert amount_header["discount_mode"] == "amount"


def test_quantity_must_be_positive_whole_number(client):
    headers = auth_headers(client)
    body = _extract(client, headers, "Quantity,Description,Rate\n-2,Amoxicillin 500mg,5.00\n2.5,Amoxicillin 500mg,5.00\nabc,Amoxicillin 500mg,5.00\n").json()
    issues = [i["issues"] for i in body["items"]]
    assert "Quantity must be above 0" in issues[0]
    assert any("whole number" in x for x in issues[1])
    assert any("not a number" in x for x in issues[2])


def test_legacy_csv_still_extracts(client):
    headers = auth_headers(client)
    body = _extract(client, headers, "name,quantity,unit_cost,batch,expiry\nAmoxicillin 500mg,500,0.18,AMX-2240,2027-04-01\n").json()
    item = body["items"][0]
    assert item["matched"] and item["batch"] == "AMX-2240" and item["expiry"] == "2027-04-01"
    assert Decimal(item["unit_cost"]) == Decimal("0.18")


# ---------- Markup ----------


def test_markup_formula_is_parameterised():
    assert markup_price(Decimal("5.00"), Decimal("35")) == Decimal("6.75")
    assert markup_price(Decimal("5.00"), Decimal("30")) == Decimal("6.50")
    assert markup_price(Decimal("8.00"), Decimal("30")) == Decimal("10.40")
    assert markup_price(Decimal("5.00"), Decimal("32")) != markup_price(Decimal("5.00"), Decimal("40"))


@pytest.mark.parametrize("markup,expected", [("35", "6.75"), ("30", "6.50"), ("32", "6.60"), ("40", "7.00")])
def test_new_medicine_selling_price_uses_chosen_markup(client, markup, expected):
    headers = auth_headers(client)
    res = _import(
        client,
        headers,
        [_line(new_product={"name": "Zinc 20mg"}, description="Zinc 20mg", quantity=10, rate="5.00", amount="50.00")],
        markup_percent=markup,
    )
    assert res.status_code == 201, res.text
    created = res.json()["created_products"][0]
    assert Decimal(created["new_selling_price"]) == Decimal(expected)
    assert created["price_source"] == "markup"
    product = _product(client, headers, created["product_id"])
    assert Decimal(str(product["selling_price"])) == Decimal(expected)
    assert Decimal(str(product["cost_price"])) == Decimal("5.00")


def test_no_hidden_default_markup(client):
    headers = auth_headers(client)
    res = _import(client, headers, [_line()], markup_percent=None)
    assert res.status_code == 422
    assert "markup" in res.json()["error"]["message"].lower()


def test_default_markup_comes_from_settings_and_can_be_overridden(client):
    headers = auth_headers(client)
    assert client.patch("/settings", headers=headers, json={"default_markup_percent": "33"}).status_code == 200
    assert Decimal(_extract(client, headers, PHARMACY_CSV).json()["default_markup_percent"]) == Decimal("33")
    res = _import(client, headers, [_line(quantity=10, rate="5.00", amount="50.00")], markup_percent="30")
    assert Decimal(res.json()["created_products"][0]["new_selling_price"]) == Decimal("6.50")
    cleared = client.patch("/settings", headers=headers, json={"default_markup_percent": None})
    assert cleared.json()["default_markup_percent"] is None


def test_explicit_selling_price_overrides_markup(client):
    headers = auth_headers(client)
    res = _import(client, headers, [_line(selling_price="12.00")], markup_percent="35")
    created = res.json()["created_products"][0]
    assert Decimal(created["new_selling_price"]) == Decimal("12.00")
    assert created["price_source"] == "explicit"


def test_existing_medicine_price_kept_unless_requested(client):
    headers = auth_headers(client)
    amox = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    line = _line(product_id=amox["id"], new_product=None, description="Amoxicillin 500mg", quantity=10, rate="0.20", amount="2.00", batch_number="AMX-NEW")
    kept = _import(client, headers, [line])
    assert kept.status_code == 201, kept.text
    assert kept.json()["price_updates"] == []
    after = _product(client, headers, amox["id"])
    assert Decimal(str(after["selling_price"])) == Decimal("0.35")
    assert Decimal(str(after["cost_price"])) == Decimal("0.20")

    updated = _import(client, headers, [dict(line, batch_number="AMX-NEW2")], update_existing_prices=True, markup_percent="30")
    assert updated.status_code == 201, updated.text
    change = updated.json()["price_updates"][0]
    assert Decimal(change["old_selling_price"]) == Decimal("0.35")
    assert Decimal(change["new_selling_price"]) == Decimal("0.26")


# ---------- Amount / discount validation at confirm ----------


def test_amount_mismatch_rejected_but_rounding_tolerated(client):
    headers = auth_headers(client)
    bad = _import(client, headers, [_line(amount="150.00")])
    assert bad.status_code == 422
    assert "does not match" in bad.json()["error"]["message"]

    rounded = _import(client, headers, [_line(new_product={"name": "Round Med"}, description="Round Med", quantity=3, rate="0.33", amount="1.00")])
    assert rounded.status_code == 201, rounded.text


def test_percent_and_amount_discount_conventions(client):
    headers = auth_headers(client)
    pct = _import(client, headers, [_line(new_product={"name": "Disc Pct"}, quantity=10, rate="5.00", discount="10", amount="45.00")])
    assert pct.status_code == 201, pct.text
    assert Decimal(pct.json()["invoice_total"]) == Decimal("45.00")
    assert Decimal(pct.json()["created_products"][0]["cost_price"]) == Decimal("5.00")

    amt = _import(
        client,
        headers,
        [_line(new_product={"name": "Disc Amt"}, quantity=10, rate="5.00", discount="2.50", amount="47.50")],
        discount_mode="amount",
    )
    assert amt.status_code == 201, amt.text
    assert Decimal(amt.json()["invoice_total"]) == Decimal("47.50")

    wrong_mode = _import(client, headers, [_line(new_product={"name": "Disc Wrong"}, quantity=10, rate="5.00", discount="2.50", amount="47.50")])
    assert wrong_mode.status_code == 422


# ---------- New medicines ----------


def test_unknown_description_creates_medicine_with_zero_stock_then_receives(client):
    headers = auth_headers(client)
    res = _import(client, headers, [_line()])
    assert res.status_code == 201, res.text
    body = res.json()
    created = body["created_products"][0]
    product = _product(client, headers, created["product_id"])
    assert product["name"] == "Zinc Sulphate 20mg Tabs"
    assert product["sku"] == "" and product["barcode"] == ""
    assert product["brand"] == "" and product["category"] == "General"
    assert product["quantity_on_hand"] == 20
    assert product["batches"][0]["batch_number"] == "ZN-001"

    moves = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["items"]
    assert len(moves) == 1
    assert moves[0]["movement_type"] == "PURCHASE" and moves[0]["quantity"] == 20
    assert moves[0]["previous_quantity"] == 0

    audit = client.get(f"/audit?entity_type=product&entity_id={product['id']}", headers=headers).json()["items"]
    assert any(a["action"] == "PRODUCT_CREATED" for a in audit)


def test_two_lines_same_new_medicine_create_one_product(client):
    headers = auth_headers(client)
    res = _import(client, headers, [_line(), _line(batch_number="ZN-002", quantity=5, amount="40.00")])
    assert res.status_code == 201, res.text
    assert len(res.json()["created_products"]) == 1
    product = _product(client, headers, res.json()["created_products"][0]["product_id"])
    assert product["quantity_on_hand"] == 25


def test_new_medicine_duplicate_name_rejected(client):
    headers = auth_headers(client)
    res = _import(client, headers, [_line(new_product={"name": "amoxicillin 500MG"})])
    assert res.status_code == 422
    assert "already exists" in res.json()["error"]["message"]


def test_bad_line_rolls_back_everything(client):
    headers = auth_headers(client)
    before = client.get("/products?limit=200", headers=headers).json()["total"]
    res = _import(client, headers, [_line(), _line(new_product={"name": "Other New"}, batch_number="", description="Other New")])
    assert res.status_code == 422
    assert "batch number is required" in res.json()["error"]["message"]
    assert client.get("/products?limit=200", headers=headers).json()["total"] == before


def test_missing_expiry_blocks_receipt_under_existing_rules(client):
    headers = auth_headers(client)
    res = _import(client, headers, [_line(expiry_date=None)])
    assert res.status_code == 422
    assert "Expiry" in res.json()["error"]["message"]


def test_cashier_cannot_import_invoice(client):
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    assert _import(client, cashier, [_line()]).status_code == 403


# ---------- Manual product validation ----------


BASE_PRODUCT = {"name": "Vitamin B Complex", "cost_price": "1.00", "selling_price": "1.50", "reorder_threshold": 10}


def test_only_name_cost_selling_reorder_required(client):
    headers = auth_headers(client)
    res = client.post("/products", headers=headers, json=BASE_PRODUCT)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["sku"] == "" and body["barcode"] == "" and body["brand"] == ""
    assert body["quantity_on_hand"] == 0

    second = client.post("/products", headers=headers, json=dict(BASE_PRODUCT, name="Vitamin D3", sku="", barcode="  ", brand="", category=""))
    assert second.status_code == 201, second.text
    assert second.json()["category"] == "General"


@pytest.mark.parametrize("missing", ["name", "cost_price", "selling_price", "reorder_threshold"])
def test_required_product_fields(client, missing):
    headers = auth_headers(client)
    payload = {k: v for k, v in BASE_PRODUCT.items() if k != missing}
    assert client.post("/products", headers=headers, json=payload).status_code == 422


def test_blank_name_and_negative_values_rejected(client):
    headers = auth_headers(client)
    assert client.post("/products", headers=headers, json=dict(BASE_PRODUCT, name="   ")).status_code == 422
    assert client.post("/products", headers=headers, json=dict(BASE_PRODUCT, cost_price="-1")).status_code == 422
    assert client.post("/products", headers=headers, json=dict(BASE_PRODUCT, reorder_threshold=-1)).status_code == 422


def test_supplied_sku_and_barcode_stay_unique(client):
    headers = auth_headers(client)
    assert client.post("/products", headers=headers, json=dict(BASE_PRODUCT, sku="MD-1001")).status_code == 409
    assert client.post("/products", headers=headers, json=dict(BASE_PRODUCT, barcode="8901234500011")).status_code == 409


def test_editing_product_can_clear_optional_codes(client):
    headers = auth_headers(client)
    created = client.post("/products", headers=headers, json=dict(BASE_PRODUCT, sku="VIT-B", barcode="123")).json()
    res = client.patch(f"/products/{created['id']}", headers=headers, json={"sku": "", "barcode": "", "category": ""})
    assert res.status_code == 200, res.text
    assert res.json()["sku"] == "" and res.json()["barcode"] == "" and res.json()["category"] == "General"
    other = client.post("/products", headers=headers, json=dict(BASE_PRODUCT, name="Other"))
    assert other.status_code == 201


# ---------- Regression ----------


def test_invoice_with_supplier_is_traceable_to_po(client):
    headers = auth_headers(client)
    supplier_id = client.get("/suppliers", headers=headers).json()[0]["id"]
    res = _import(client, headers, [_line()], supplier_id=supplier_id)
    assert res.status_code == 201, res.text
    receipt = res.json()["receipt"]
    assert receipt["po_number"] and receipt["supplier_name"] == "MediSource Global"
    product = _product(client, headers, res.json()["created_products"][0]["product_id"])
    batch = product["batches"][0]
    assert batch["supplier"]["name"] == "MediSource Global"
    assert batch["purchase_order"]["po_number"] == receipt["po_number"]


def test_invoice_without_supplier_records_not_recorded(client):
    headers = auth_headers(client)
    res = _import(client, headers, [_line()])
    receipt = res.json()["receipt"]
    assert receipt["po_number"] is None and receipt["supplier_name"] is None
    assert receipt["reference"].startswith("RCPT-")
    product = _product(client, headers, res.json()["created_products"][0]["product_id"])
    assert product["batches"][0]["supplier"] is None
    audit = client.get("/audit?action=INVOICE_IMPORTED", headers=headers).json()["items"][0]
    assert audit["details"]["supplier"] == "Not recorded"
    assert audit["details"]["markup_percent"] == "35"


def test_archived_product_cannot_be_received_or_recreated_via_invoice(client):
    headers = auth_headers(client)
    created = client.post("/products", headers=headers, json=dict(BASE_PRODUCT, name="Old Syrup")).json()
    assert client.post(f"/products/{created['id']}/archive", headers=headers).status_code == 200

    extract = _extract(client, headers, "Quantity,Description,Rate\n5,Old Syrup,2.00\n").json()
    line = extract["items"][0]
    assert line["matched"] is False and line["archived_product_id"] == created["id"]

    by_id = _import(client, headers, [_line(product_id=created["id"], new_product=None, description="Old Syrup", quantity=5, rate="2.00", amount="10.00")])
    assert by_id.status_code == 422 and "archived" in by_id.json()["error"]["message"]
    by_name = _import(client, headers, [_line(new_product={"name": "Old Syrup"}, quantity=5, rate="2.00", amount="10.00")])
    assert by_name.status_code == 422 and "archived" in by_name.json()["error"]["message"]

    after = client.get(f"/products/{created['id']}", headers=headers).json()
    assert after["deleted_at"] is not None and after["quantity_on_hand"] == 0


def test_existing_csv_import_endpoint_still_works(client):
    headers = auth_headers(client)
    item = _extract(client, headers, "name,quantity,unit_cost,batch,expiry\nAmoxicillin 500mg,5,0.18,AMX-LEG,2027-04-01\n").json()["items"][0]
    supplier_id = client.get("/suppliers", headers=headers).json()[0]["id"]
    res = client.post(
        "/receiving/import",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "items": [
                {
                    "product_id": item["product_id"],
                    "product_name": item["name"],
                    "quantity_ordered": item["quantity"],
                    "unit_cost": item["unit_cost"],
                    "batch_number": item["batch"],
                    "expiry_date": item["expiry"],
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "RECEIVED"
