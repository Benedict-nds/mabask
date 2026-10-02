import json
from datetime import date, timedelta
from decimal import Decimal

from app.models import AuditLog, Batch, SaleItem, User
from tests.conftest import auth_headers

ADMIN = "amara@brightcare.pharmacy"
CASHIER = "lena@brightcare.pharmacy"
PHARMACIST = "grace@brightcare.pharmacy"


def _product(client, headers):
    return client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]


def _batch(product, number="AMX-2231"):
    return next(b for b in product["batches"] if b["batch_number"] == number)


def _edit_expiry(client, headers, product_id, batch_id, expiry, reason="Typo at receiving"):
    return client.patch(
        f"/products/{product_id}/batches/{batch_id}",
        headers=headers,
        json={"expiry_date": expiry, "reason": reason},
    )


def _sell(client, headers, product_id, qty, key):
    res = client.post(
        "/sales",
        headers=headers,
        json={"items": [{"product_id": product_id, "quantity": qty}], "payment_method": "CASH", "idempotency_key": key},
    )
    return res


def _audit(db, action):
    return [(row, json.loads(row.details)) for row in db.query(AuditLog).filter(AuditLog.action == action).all()]


def _user_id(db, email):
    return db.query(User).filter(User.email == email).one().id


# --- Product-level settings -------------------------------------------------------------------


def test_admin_updates_reorder_point_and_it_persists(client):
    headers = auth_headers(client)
    product = _product(client, headers)
    assert product["reorder_threshold"] == 400
    assert product["status"] != "healthy"

    res = client.patch(f"/products/{product['id']}", headers=headers, json={"reorder_threshold": 10})
    assert res.status_code == 200, res.text
    assert res.json()["reorder_threshold"] == 10
    assert res.json()["status"] == "healthy"

    fresh = client.get(f"/products/{product['id']}", headers=headers).json()
    assert fresh["reorder_threshold"] == 10
    low = client.get("/reports/inventory", headers=headers).json()["low_stock_items"]
    assert product["id"] not in {p["id"] for p in low}


def test_negative_reorder_point_rejected(client):
    headers = auth_headers(client)
    product = _product(client, headers)
    res = client.patch(f"/products/{product['id']}", headers=headers, json={"reorder_threshold": -1})
    assert res.status_code == 422
    assert "error" in res.json()
    assert client.get(f"/products/{product['id']}", headers=headers).json()["reorder_threshold"] == 400


def test_pharmacist_updates_all_product_fields(client):
    headers = auth_headers(client, PHARMACIST)
    product = _product(client, headers)
    payload = {
        "name": "Amoxicillin 500mg Caps",
        "cost_price": "0.20",
        "selling_price": "0.40",
        "reorder_threshold": 150,
        "brand": "Amoxil Plus",
        "sku": "MD-1001-B",
        "barcode": "8901234500099",
        "category": "Antibiotics",
        "generic_name": "Amoxicillin",
        "description": "Broad-spectrum antibiotic",
        "dosage_form": "Capsule",
        "strength": "500mg",
        "unit": "capsule",
    }
    res = client.patch(f"/products/{product['id']}", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    for key, value in payload.items():
        if key in ("cost_price", "selling_price"):
            assert Decimal(str(body[key])) == Decimal(value)
        else:
            assert body[key] == value, key


def test_cashier_cannot_update_product(client):
    headers = auth_headers(client, CASHIER)
    product = _product(client, headers)
    assert client.patch(f"/products/{product['id']}", headers=headers, json={"reorder_threshold": 5}).status_code == 403


def test_product_update_audit_lists_changes(client, db):
    headers = auth_headers(client)
    product = _product(client, headers)
    client.patch(f"/products/{product['id']}", headers=headers, json={"reorder_threshold": 10, "brand": "Amoxil"})
    rows = _audit(db, "PRODUCT_UPDATED")
    assert len(rows) == 1
    assert rows[0][1]["changes"] == ["reorder_threshold: 400 → 10"]


def test_price_and_name_changes_do_not_rewrite_history(client, db):
    headers = auth_headers(client)
    product = _product(client, headers)
    sale = _sell(client, headers, product["id"], 2, "hist-1")
    assert sale.status_code == 201, sale.text
    sale_id = sale.json()["id"]
    before_items = client.get(f"/sales/{sale_id}", headers=headers).json()["items"]
    batch_cost_before = Decimal(str(_batch(product)["cost_price"]))

    res = client.patch(
        f"/products/{product['id']}",
        headers=headers,
        json={"selling_price": "9.99", "cost_price": "5.00", "sku": "NEW-SKU", "barcode": "NEWBAR"},
    )
    assert res.status_code == 200

    after_items = client.get(f"/sales/{sale_id}", headers=headers).json()["items"]
    assert [i["unit_price"] for i in after_items] == [i["unit_price"] for i in before_items]
    assert [i["line_total"] for i in after_items] == [i["line_total"] for i in before_items]
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale_id).one()
    assert item.unit_price == Decimal("0.35")
    assert item.product_id == product["id"]
    fresh = client.get(f"/products/{product['id']}", headers=headers).json()
    assert Decimal(str(_batch(fresh)["cost_price"])) == batch_cost_before
    assert client.get(f"/products/barcode/NEWBAR", headers=headers).json()["id"] == product["id"]


# --- Batch expiry ----------------------------------------------------------------------------------


def test_admin_updates_batch_expiry_and_it_persists(client, db):
    headers = auth_headers(client)
    product = _product(client, headers)
    batch = _batch(product)
    res = _edit_expiry(client, headers, product["id"], batch["id"], "2027-06-30")
    assert res.status_code == 200, res.text
    assert _batch(res.json())["expiry_date"].startswith("2027-06-30")

    fresh = client.get(f"/products/{product['id']}", headers=headers).json()
    assert _batch(fresh)["expiry_date"].startswith("2027-06-30")
    assert fresh["nearest_expiry"].startswith("2027-06-30")
    listed = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    assert listed["nearest_expiry"].startswith("2027-06-30")
    assert db.get(Batch, batch["id"]).expiry_date == date(2027, 6, 30)


def test_expiry_edit_feeds_expiry_reports(client):
    headers = auth_headers(client)
    product = _product(client, headers)
    batch = _batch(product)
    report = client.get("/reports/inventory", headers=headers).json()
    assert "AMX-2231" not in {i["batch"] for i in report["expiring_items"]}

    soon = (date.today() + timedelta(days=20)).isoformat()
    assert _edit_expiry(client, headers, product["id"], batch["id"], soon).status_code == 200
    report = client.get("/reports/inventory", headers=headers).json()
    assert {"batch": "AMX-2231", "expiry": soon} in [{"batch": i["batch"], "expiry": i["expiry"]} for i in report["expiring_items"]]
    assert client.get("/dashboard", headers=headers).json()["expiring_count"] >= 1


def test_expiry_edit_changes_fefo_order(client):
    headers = auth_headers(client)
    product = _product(client, headers)
    later = client.post(
        f"/products/{product['id']}/batches",
        headers=headers,
        json={"batch_number": "AMX-LATE", "expiry_date": "2028-12-31", "quantity": 10},
    )
    assert later.status_code == 201, later.text
    late_batch = _batch(later.json(), "AMX-LATE")

    earliest = (date.today() + timedelta(days=90)).isoformat()
    assert _edit_expiry(client, headers, product["id"], late_batch["id"], earliest).status_code == 200
    assert _sell(client, headers, product["id"], 4, "fefo-1").status_code == 201
    fresh = client.get(f"/products/{product['id']}", headers=headers).json()
    assert _batch(fresh, "AMX-LATE")["quantity"] == 6
    assert _batch(fresh, "AMX-2231")["quantity"] == 100


def test_expiry_moved_into_past_blocks_sale_from_that_batch(client):
    headers = auth_headers(client)
    product = _product(client, headers)
    batch = _batch(product)
    past = (date.today() - timedelta(days=1)).isoformat()
    assert _edit_expiry(client, headers, product["id"], batch["id"], past).status_code == 200
    res = _sell(client, headers, product["id"], 1, "expired-1")
    assert res.status_code == 422
    assert "Insufficient stock" in res.json()["error"]["message"]


def test_expiry_validation(client):
    headers = auth_headers(client)
    product = _product(client, headers)
    batch = _batch(product)
    assert _edit_expiry(client, headers, product["id"], batch["id"], "not-a-date").status_code == 422
    assert _edit_expiry(client, headers, product["id"], batch["id"], "2150-01-01").status_code == 422
    assert _edit_expiry(client, headers, product["id"], batch["id"], "2027-06-30", reason="   ").status_code == 422
    assert client.patch(
        f"/products/{product['id']}/batches/{batch['id']}", headers=headers, json={"expiry_date": "2027-06-30"}
    ).status_code == 422
    assert _edit_expiry(client, headers, product["id"], "missing", "2027-06-30").status_code == 404
    assert client.get(f"/products/{product['id']}", headers=headers).json()["nearest_expiry"].startswith("2027-04-01")


def test_expiry_edit_is_audited_with_old_and_new_values(client, db):
    headers = auth_headers(client)
    product = _product(client, headers)
    batch = _batch(product)
    _edit_expiry(client, headers, product["id"], batch["id"], "2027-06-30", reason="Supplier label misread")
    _edit_expiry(client, headers, product["id"], batch["id"], "2027-06-30")
    rows = _audit(db, "BATCH_EXPIRY_CHANGED")
    assert len(rows) == 1
    row, details = rows[0]
    assert row.user_id == _user_id(db, ADMIN)
    assert row.entity_type == "batch" and row.entity_id == batch["id"]
    assert row.created_at is not None
    assert details["previous_expiry"] == "2027-04-01"
    assert details["new_expiry"] == "2027-06-30"
    assert details["batch_number"] == "AMX-2231"
    assert details["product"] == "Amoxicillin 500mg"
    assert details["reason"] == "Supplier label misread"
    listed = client.get("/audit?action=BATCH_EXPIRY_CHANGED", headers=headers).json()["items"]
    assert listed[0]["details"]["new_expiry"] == "2027-06-30"


def test_expiry_edit_leaves_movements_and_po_lines_untouched(client, db):
    headers = auth_headers(client)
    product = _product(client, headers)
    before = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["total"]
    _edit_expiry(client, headers, product["id"], _batch(product)["id"], "2027-06-30")
    after = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["total"]
    assert after == before
    assert client.get(f"/products/{product['id']}", headers=headers).json()["quantity_on_hand"] == 100


# --- Permissions ------------------------------------------------------------------------------------


def test_expiry_edit_requires_batch_edit_permission(client):
    for email in (PHARMACIST, CASHIER):
        headers = auth_headers(client, email)
        product = _product(client, headers)
        res = _edit_expiry(client, headers, product["id"], _batch(product)["id"], "2027-06-30")
        assert res.status_code == 403, email
    assert "inventory.batch_edit" not in client.get("/auth/me", headers=auth_headers(client, PHARMACIST)).json()["permissions"]
    assert "inventory.batch_edit" in client.get("/auth/me", headers=auth_headers(client)).json()["permissions"]


def test_permission_overrides_apply_to_editing(client, db):
    admin = auth_headers(client)
    grace = _user_id(db, PHARMACIST)
    put = lambda overrides: client.put(f"/users/{grace}/permissions", headers=admin, json={"overrides": overrides})

    assert put({"inventory.batch_edit": "ALLOW", "inventory.update": "DENY"}).status_code == 200
    headers = auth_headers(client, PHARMACIST)
    product = _product(client, headers)
    assert _edit_expiry(client, headers, product["id"], _batch(product)["id"], "2027-06-30").status_code == 200
    assert client.patch(f"/products/{product['id']}", headers=headers, json={"reorder_threshold": 5}).status_code == 403

    assert put({"inventory.batch_edit": "INHERIT", "inventory.update": "INHERIT"}).status_code == 200
    assert _edit_expiry(client, headers, product["id"], _batch(product)["id"], "2027-07-31").status_code == 403
    assert client.patch(f"/products/{product['id']}", headers=headers, json={"reorder_threshold": 5}).status_code == 200


# --- Archived products ------------------------------------------------------------------------------


def test_archived_product_cannot_be_edited_and_stays_archived(client):
    headers = auth_headers(client)
    product = _product(client, headers)
    batch = _batch(product)
    assert client.post(f"/products/{product['id']}/archive", headers=headers).status_code == 200

    assert client.patch(f"/products/{product['id']}", headers=headers, json={"reorder_threshold": 5}).status_code == 404
    res = _edit_expiry(client, headers, product["id"], batch["id"], "2027-06-30")
    assert res.status_code == 409
    assert "Restore" in res.json()["error"]["message"]

    fresh = client.get(f"/products/{product['id']}", headers=headers).json()
    assert fresh["deleted_at"] is not None
    assert fresh["reorder_threshold"] == 400
    assert _batch(fresh)["expiry_date"].startswith("2027-04-01")
    assert client.post(f"/products/{product['id']}/restore", headers=headers).status_code == 200
    assert _edit_expiry(client, headers, product["id"], batch["id"], "2027-06-30").status_code == 200
