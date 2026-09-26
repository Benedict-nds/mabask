"""End-to-end pharmacist journeys across receiving, purchasing, corrections, journal and audit.

Each test drives the public API the same way the UI does, then checks stock, traceability and audit.
"""

from datetime import date, timedelta

from sqlalchemy import event

from app.modules.audit.service import record_audit
from tests.conftest import auth_headers, engine

ADMIN = "amara@brightcare.pharmacy"
CASHIER = "lena@brightcare.pharmacy"
PHARMACIST = "grace@brightcare.pharmacy"


def _amox(client, headers):
    return client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]


def _new_medicine(client, headers, name="Cetirizine 10mg", sku="MD-7001", price="0.40"):
    res = client.post("/products", headers=headers, json={"name": name, "sku": sku, "selling_price": price, "reorder_threshold": 0, "cost_price": "0.10"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["quantity_on_hand"] == 0
    return body


def _get_product(client, headers, product_id):
    return client.get(f"/products/{product_id}", headers=headers).json()


def _audit(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    res = client.get(f"/audit?limit=200&{query}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _sell(client, headers, product, qty, key, payment="CASH"):
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": qty}],
            "payment_method": payment,
            "amount_tendered": "100",
            "idempotency_key": key,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _po_body(supplier_id, product, qty=10, cost="0.20", batch="", expiry=None):
    return {
        "supplier_id": supplier_id,
        "notes": "Journey PO",
        "items": [
            {
                "product_id": product["id"],
                "product_name": product["name"],
                "quantity_ordered": qty,
                "unit_cost": cost,
                "batch_number": batch,
                "expiry_date": expiry,
            }
        ],
    }


# --- Receiving: manual entry -------------------------------------------------------------


def test_adhoc_receipt_without_supplier_records_stock_without_inventing_provenance(client):
    admin = auth_headers(client)
    amox = _amox(client, admin)
    new_med = _new_medicine(client, admin)
    pos_before = len(client.get("/purchase-orders", headers=admin).json())

    res = client.post(
        "/receiving/adhoc",
        headers=admin,
        json={
            "notes": "Walk-in delivery, invoice to follow",
            "items": [
                {"product_id": amox["id"], "quantity": 30, "unit_cost": "0.19", "batch_number": "ADH-AMX-1", "expiry_date": "2028-03-01", "notes": "1 box dented"},
                {"product_id": new_med["id"], "quantity": 50, "unit_cost": "0.12", "batch_number": "ADH-CET-1", "expiry_date": "2028-06-30"},
            ],
        },
    )
    assert res.status_code == 201, res.text
    receipt = res.json()
    assert receipt["reference"].startswith("RCPT-")
    assert receipt["po_number"] is None and receipt["supplier_name"] is None
    assert receipt["units_received"] == 80
    assert len(receipt["lines"]) == 2

    assert len(client.get("/purchase-orders", headers=admin).json()) == pos_before
    assert _get_product(client, admin, amox["id"])["quantity_on_hand"] == amox["quantity_on_hand"] + 30
    med = _get_product(client, admin, new_med["id"])
    assert med["quantity_on_hand"] == 50
    batch = next(b for b in med["batches"] if b["batch_number"] == "ADH-CET-1")
    assert batch["supplier"] is None and batch["purchase_order"] is None

    moves = client.get(f"/stock-movements?product_id={amox['id']}", headers=admin).json()["items"]
    receipt_moves = [m for m in moves if m["reference_type"] == "manual_receipt"]
    assert len(receipt_moves) == 1
    assert receipt_moves[0]["movement_type"] == "PURCHASE"
    assert receipt_moves[0]["quantity"] == 30
    assert "1 box dented" in receipt_moves[0]["reason"]
    assert receipt_moves[0]["po_number"] is None

    logs = _audit(client, admin, action="STOCK_RECEIVED")
    assert logs and logs[0]["entity_label"] == receipt["reference"]
    assert logs[0]["details"]["supplier"] == "Not recorded"
    assert logs[0]["actor"] == "Amara Kane"


def test_adhoc_receipt_is_atomic_when_any_line_is_invalid(client):
    admin = auth_headers(client)
    amox = _amox(client, admin)
    before = amox["quantity_on_hand"]
    res = client.post(
        "/receiving/adhoc",
        headers=admin,
        json={
            "items": [
                {"product_id": amox["id"], "quantity": 10, "unit_cost": "0.2", "batch_number": "ATOM-1", "expiry_date": "2028-01-01"},
                {"product_id": amox["id"], "quantity": 5, "unit_cost": "0.2", "batch_number": "ATOM-2"},
            ]
        },
    )
    assert res.status_code == 422
    assert "Line 2" in res.text
    product = _get_product(client, admin, amox["id"])
    assert product["quantity_on_hand"] == before
    assert all(b["batch_number"] != "ATOM-1" for b in product["batches"])


def test_adhoc_receipt_rejects_conflicting_batch_expiry_and_archived_products(client):
    admin = auth_headers(client)
    amox = _amox(client, admin)
    conflict = client.post(
        "/receiving/adhoc",
        headers=admin,
        json={"items": [{"product_id": amox["id"], "quantity": 1, "unit_cost": "0.2", "batch_number": "AMX-2231", "expiry_date": "2029-01-01"}]},
    )
    assert conflict.status_code == 422
    assert "already exists with expiry" in conflict.text

    med = _new_medicine(client, admin, name="Archived Syrup", sku="MD-ARCH-1")
    assert client.post(f"/products/{med['id']}/archive", headers=admin).status_code == 200
    archived = client.post(
        "/receiving/adhoc",
        headers=admin,
        json={"items": [{"product_id": med["id"], "quantity": 1, "unit_cost": "0.2", "batch_number": "X-1", "expiry_date": "2028-01-01"}]},
    )
    assert archived.status_code == 422
    assert "archived" in archived.text


def test_adhoc_receipt_with_supplier_is_traceable(client):
    admin = auth_headers(client)
    amox = _amox(client, admin)
    res = client.post(
        "/receiving/adhoc",
        headers=admin,
        json={
            "supplier_id": amox["supplier_id"],
            "items": [{"product_id": amox["id"], "quantity": 12, "unit_cost": "0.21", "batch_number": "SUP-1", "expiry_date": "2028-02-01", "notes": "cold chain ok"}],
        },
    )
    assert res.status_code == 201, res.text
    receipt = res.json()
    assert receipt["po_number"] and receipt["reference"] == receipt["po_number"]
    assert receipt["supplier_name"] == "MediSource Global"
    batch = next(b for b in _get_product(client, admin, amox["id"])["batches"] if b["batch_number"] == "SUP-1")
    assert batch["supplier"]["name"] == "MediSource Global"
    assert batch["purchase_order"]["po_number"] == receipt["po_number"]
    po = client.get(f"/purchase-orders/{receipt['purchase_order_id']}", headers=admin).json()
    assert po["status"] == "RECEIVED"
    assert "cold chain ok" in po["notes"]


def test_cashier_cannot_receive_stock(client):
    cashier = auth_headers(client, CASHIER)
    admin = auth_headers(client)
    amox = _amox(client, admin)
    res = client.post(
        "/receiving/adhoc",
        headers=cashier,
        json={"items": [{"product_id": amox["id"], "quantity": 1, "unit_cost": "0.2", "batch_number": "C-1", "expiry_date": "2028-01-01"}]},
    )
    assert res.status_code == 403


def test_manual_receive_against_po_with_line_notes(client):
    admin = auth_headers(client)
    amox = _amox(client, admin)
    po = client.post("/purchase-orders", headers=admin, json=_po_body(amox["supplier_id"], amox, qty=40)).json()
    client.post(f"/purchase-orders/{po['id']}/submit", headers=admin)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=admin)
    item_id = po["items"][0]["id"]
    res = client.post(
        f"/purchase-orders/{po['id']}/receive",
        headers=admin,
        json={"lines": [{"item_id": item_id, "quantity": 25, "batch_number": "PO-LOT-1", "expiry_date": "2028-05-01", "unit_cost": "0.22", "notes": "short shipped 15"}]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "PARTIALLY_RECEIVED"
    moves = client.get(f"/stock-movements?product_id={amox['id']}", headers=admin).json()["items"]
    move = next(m for m in moves if m["reference_id"] == po["id"])
    assert "short shipped 15" in move["reason"]
    assert move["po_number"] == po["po_number"]
    logs = _audit(client, admin, action="PURCHASE_ORDER_RECEIVED", entity_id=po["id"])
    assert logs[0]["details"]["po_number"] == po["po_number"]
    assert logs[0]["details"]["units"] == 25


# --- Purchasing: new medicine and review workflow ---------------------------------------


def test_new_medicine_created_from_po_flow_reaches_stock_on_receipt(client):
    admin = auth_headers(client)
    supplier_id = _amox(client, admin)["supplier_id"]
    med = _new_medicine(client, admin, name="Loratadine 10mg", sku="MD-LOR-1", price="0.50")
    found = client.get("/products?q=Lorat", headers=admin).json()["items"]
    assert any(p["id"] == med["id"] for p in found)

    po = client.post("/purchase-orders", headers=admin, json=_po_body(supplier_id, med, qty=60, batch="", expiry=None))
    assert po.status_code == 201, po.text
    po = po.json()
    assert _get_product(client, admin, med["id"])["quantity_on_hand"] == 0
    client.post(f"/purchase-orders/{po['id']}/submit", headers=admin)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=admin)
    received = client.post(
        f"/purchase-orders/{po['id']}/receive",
        headers=admin,
        json={"lines": [{"item_id": po["items"][0]["id"], "quantity": 60, "batch_number": "LOR-001", "expiry_date": "2028-09-30"}]},
    )
    assert received.status_code == 200, received.text
    product = _get_product(client, admin, med["id"])
    assert product["quantity_on_hand"] == 60
    assert product["batches"][0]["purchase_order"]["po_number"] == po["po_number"]


def test_po_changes_requested_cycle_is_fully_audited(client):
    pharmacist = auth_headers(client, PHARMACIST)
    admin = auth_headers(client)
    amox = _amox(client, admin)
    po = client.post("/purchase-orders", headers=pharmacist, json=_po_body(amox["supplier_id"], amox, qty=500)).json()
    assert client.post(f"/purchase-orders/{po['id']}/submit", headers=pharmacist).json()["status"] == "SUBMITTED"

    no_reason = client.post(f"/purchase-orders/{po['id']}/request-changes", headers=admin, json={"reason": "  "})
    assert no_reason.status_code == 422
    changes = client.post(f"/purchase-orders/{po['id']}/request-changes", headers=admin, json={"reason": "500 is too many; order 200"})
    assert changes.json()["status"] == "CHANGES_REQUESTED"

    seen = client.get(f"/purchase-orders/{po['id']}", headers=pharmacist).json()
    assert seen["review_comment"] == "500 is too many; order 200"
    assert seen["review_requested_by_name"] == "Amara Kane"

    edited = client.put(f"/purchase-orders/{po['id']}", headers=pharmacist, json=_po_body(amox["supplier_id"], amox, qty=200))
    assert edited.json()["status"] == "DRAFT"
    assert client.post(f"/purchase-orders/{po['id']}/approve", headers=admin).status_code == 422
    assert client.post(f"/purchase-orders/{po['id']}/submit", headers=pharmacist).json()["status"] == "SUBMITTED"
    assert client.post(f"/purchase-orders/{po['id']}/approve", headers=admin).json()["status"] == "APPROVED"

    history = list(reversed(_audit(client, admin, entity_type="purchase_order", entity_id=po["id"])))
    actions = [h["action"] for h in history]
    assert actions == [
        "PURCHASE_ORDER_CREATED",
        "PURCHASE_ORDER_SUBMITTED",
        "PURCHASE_ORDER_CHANGES_REQUESTED",
        "PURCHASE_ORDER_UPDATED",
        "PURCHASE_ORDER_SUBMITTED",
        "PURCHASE_ORDER_APPROVED",
    ]
    assert history[2]["details"]["reason"] == "500 is too many; order 200"
    assert history[2]["actor"] == "Amara Kane"
    assert "qty 500 -> 200" in " ".join(history[3]["details"]["changes"])
    assert all(po["po_number"] in (h["entity_label"] or "") for h in history)


def test_reviewer_can_edit_submitted_po_but_creator_cannot_silently(client):
    pharmacist = auth_headers(client, PHARMACIST)
    admin = auth_headers(client)
    cashier = auth_headers(client, CASHIER)
    amox = _amox(client, admin)
    po = client.post("/purchase-orders", headers=pharmacist, json=_po_body(amox["supplier_id"], amox, qty=300)).json()
    client.post(f"/purchase-orders/{po['id']}/submit", headers=pharmacist)

    silent = client.put(f"/purchase-orders/{po['id']}", headers=pharmacist, json=_po_body(amox["supplier_id"], amox, qty=999))
    assert silent.status_code == 422
    own_review = client.put(
        f"/purchase-orders/{po['id']}/review-edit",
        headers=pharmacist,
        json={**_po_body(amox["supplier_id"], amox, qty=999), "reason": "self approve"},
    )
    assert own_review.status_code == 403
    assert client.put(
        f"/purchase-orders/{po['id']}/review-edit",
        headers=cashier,
        json={**_po_body(amox["supplier_id"], amox, qty=1), "reason": "x"},
    ).status_code == 403
    missing_reason = client.put(f"/purchase-orders/{po['id']}/review-edit", headers=admin, json=_po_body(amox["supplier_id"], amox, qty=250))
    assert missing_reason.status_code == 422

    res = client.put(
        f"/purchase-orders/{po['id']}/review-edit",
        headers=admin,
        json={**_po_body(amox["supplier_id"], amox, qty=250, cost="0.19"), "reason": "Supplier minimum is 250 units"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "SUBMITTED"
    assert body["items"][0]["quantity_ordered"] == 250
    log = _audit(client, admin, action="PURCHASE_ORDER_UPDATED", entity_id=po["id"])[0]
    assert log["details"]["reviewer_edit"] is True
    assert log["details"]["reason"] == "Supplier minimum is 250 units"
    assert any("qty 300 -> 250" in c for c in log["details"]["changes"])
    assert any("cost" in c for c in log["details"]["changes"])
    assert client.post(f"/purchase-orders/{po['id']}/approve", headers=admin).json()["status"] == "APPROVED"
    after = client.put(
        f"/purchase-orders/{po['id']}/review-edit",
        headers=admin,
        json={**_po_body(amox["supplier_id"], amox, qty=1), "reason": "too late"},
    )
    assert after.status_code == 422


def test_pharmacist_reviewer_can_edit_someone_elses_submitted_po(client):
    admin = auth_headers(client)
    pharmacist = auth_headers(client, PHARMACIST)
    amox = _amox(client, admin)
    po = client.post("/purchase-orders", headers=admin, json=_po_body(amox["supplier_id"], amox, qty=80)).json()
    client.post(f"/purchase-orders/{po['id']}/submit", headers=admin)
    res = client.put(
        f"/purchase-orders/{po['id']}/review-edit",
        headers=pharmacist,
        json={**_po_body(amox["supplier_id"], amox, qty=90), "reason": "Round up to case size"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "SUBMITTED"


# --- Sale corrections --------------------------------------------------------------------


def test_correction_approve_journey_links_sales_in_journal(client):
    admin = auth_headers(client)
    cashier = auth_headers(client, CASHIER)
    amox = _amox(client, admin)
    start_qty = amox["quantity_on_hand"]
    sale = _sell(client, cashier, amox, qty=3, key="journey-corr-approve")
    req = client.post(f"/sales/{sale['id']}/correction-requests", headers=cashier, json={"reason": "Customer only took 1"})
    assert req.status_code == 201, req.text
    request = req.json()
    assert request["reference"].startswith("CR-")

    assert client.get("/sale-corrections", headers=cashier).status_code == 403
    queue = client.get(f"/sale-corrections?status=PENDING&q={sale['sale_number']}", headers=admin).json()
    assert queue["total"] == 1
    assert client.get(f"/sale-corrections?q={request['reference']}", headers=admin).json()["total"] == 1
    detail = client.get(f"/sale-corrections/{request['id']}", headers=admin).json()
    assert detail["sale"]["items"][0]["batch_number"]
    assert detail["sale"]["cashier_name"] == "Lena Ross"

    pending = client.get("/sales?correction=pending", headers=admin).json()["items"]
    assert any(s["id"] == sale["id"] for s in pending)

    approved = client.post(
        f"/sale-corrections/{request['id']}/approve",
        headers=admin,
        json={"items": [{"product_id": amox["id"], "quantity": 1}], "payment_method": "CASH", "idempotency_key": "journey-approve-1", "review_note": "Verified with customer"},
    )
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result["status"] == "APPROVED"
    assert result["financial_difference"] is not None
    assert _get_product(client, admin, amox["id"])["quantity_on_hand"] == start_qty - 1

    original = client.get(f"/sales/{sale['id']}", headers=admin).json()
    link = original["correction"]
    assert link["status"] == "APPROVED"
    assert link["requested_by_name"] == "Lena Ross"
    assert link["reviewed_by_name"] == "Amara Kane"
    assert link["reason"] == "Customer only took 1"
    assert link["review_note"] == "Verified with customer"
    assert link["corrected_sale_id"] == result["corrected_sale_id"]
    assert link["reference"] == request["reference"]
    assert original["returns"][0]["items"][0]["quantity"] == 3
    assert original["returns"][0]["processed_by_name"] == "Amara Kane"
    assert original["returns"][0]["restock"] is True

    corrected = client.get(f"/sales/{result['corrected_sale_id']}", headers=admin).json()
    assert corrected["is_correction_of"]["original_sale_id"] == sale["id"]
    assert corrected["is_correction_of"]["original_sale_number"] == sale["sale_number"]

    corrected_list = client.get("/sales?correction=corrected", headers=admin).json()["items"]
    assert any(s["id"] == sale["id"] and s["correction"]["reviewed_by_name"] == "Amara Kane" for s in corrected_list)

    log = _audit(client, admin, action="SALE_CORRECTION_APPROVED", entity_id=request["id"])[0]
    assert request["reference"] in log["entity_label"] and sale["sale_number"] in log["entity_label"]
    assert log["details"]["corrected_sale_id"] == result["corrected_sale_id"]


def test_correction_reject_journey_leaves_sale_untouched(client):
    admin = auth_headers(client)
    cashier = auth_headers(client, CASHIER)
    amox = _amox(client, admin)
    sale = _sell(client, cashier, amox, qty=2, key="journey-corr-reject")
    qty_after_sale = _get_product(client, admin, amox["id"])["quantity_on_hand"]
    request = client.post(f"/sales/{sale['id']}/correction-requests", headers=cashier, json={"reason": "Typo"}).json()

    assert client.post(f"/sale-corrections/{request['id']}/reject", headers=admin, json={"reason": " "}).status_code == 422
    rejected = client.post(f"/sale-corrections/{request['id']}/reject", headers=admin, json={"reason": "Sale was correct per receipt"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"

    original = client.get(f"/sales/{sale['id']}", headers=admin).json()
    assert original["status"] == "COMPLETED"
    assert original["returns"] == []
    assert original["correction"]["status"] == "REJECTED"
    assert original["correction"]["review_note"] == "Sale was correct per receipt"
    assert _get_product(client, admin, amox["id"])["quantity_on_hand"] == qty_after_sale
    assert any(s["id"] == sale["id"] for s in client.get("/sales?correction=rejected", headers=admin).json()["items"])
    log = _audit(client, admin, action="SALE_CORRECTION_REJECTED", entity_id=request["id"])[0]
    assert log["actor"] == "Amara Kane"


# --- Sales journal -----------------------------------------------------------------------


def test_journal_product_filter_and_export(client):
    admin = auth_headers(client)
    amox = _amox(client, admin)
    med = _new_medicine(client, admin, name="Ibuprofen 200mg", sku="MD-IBU-1", price="0.30")
    client.post(
        "/receiving/adhoc",
        headers=admin,
        json={"items": [{"product_id": med["id"], "quantity": 20, "unit_cost": "0.1", "batch_number": "IBU-1", "expiry_date": "2028-01-01"}]},
    )
    _sell(client, admin, amox, qty=1, key="journal-amox")
    ibu_sale = _sell(client, admin, med, qty=2, key="journal-ibu")

    filtered = client.get(f"/sales?product_id={med['id']}", headers=admin).json()
    assert [s["id"] for s in filtered["items"]] == [ibu_sale["id"]]
    assert filtered["items"][0]["customer_name"] is not None or filtered["items"][0]["customer_id"] is None

    export = client.get(f"/sales/export.csv?product_id={med['id']}", headers=admin)
    assert export.status_code == 200
    lines = [l for l in export.text.strip().splitlines() if l]
    assert len(lines) == 2 and "Ibuprofen 200mg" in lines[1] and "Amoxicillin" not in export.text
    assert client.get("/sales/export.csv", headers=auth_headers(client, CASHIER)).status_code == 403


def test_journal_list_query_count_does_not_grow_with_rows(client):
    admin = auth_headers(client)
    amox = _amox(client, admin)
    for i in range(2):
        _sell(client, admin, amox, qty=1, key=f"nplus1-a-{i}")

    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        client.get("/sales?limit=50", headers=admin)
        small = len(statements)
        for i in range(6):
            _sell(client, admin, amox, qty=1, key=f"nplus1-b-{i}")
        statements.clear()
        client.get("/sales?limit=50", headers=admin)
        large = len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert large == small


# --- Audit -------------------------------------------------------------------------------


def test_audit_filters_facets_labels_and_redaction(client, db):
    admin = auth_headers(client)
    pharmacist = auth_headers(client, PHARMACIST)
    amox = _amox(client, admin)
    po = client.post("/purchase-orders", headers=pharmacist, json=_po_body(amox["supplier_id"], amox, qty=5)).json()

    record_audit(db, user=None, action="TEST_SECRET_EVENT", entity_type="settings", entity_id="pharmacy",
                 details={"password": "hunter2", "api_key": "sk-live", "nested": {"token": "abc"}, "note": "visible"})
    db.commit()

    today = date.today()
    assert _audit(client, admin, date_from=(today + timedelta(days=1)).isoformat()) == []
    assert _audit(client, admin, date_to=today.isoformat())

    by_entity = _audit(client, admin, entity_id=po["id"])
    assert [r["action"] for r in by_entity] == ["PURCHASE_ORDER_CREATED"]
    assert by_entity[0]["entity_label"].startswith(po["po_number"])
    assert by_entity[0]["actor"] == "Grace Mensah"

    facets = client.get("/audit/facets", headers=admin).json()
    assert "PURCHASE_ORDER_CREATED" in facets["actions"]
    assert "purchase_order" in facets["entity_types"]
    grace = next(u for u in facets["users"] if u["name"] == "Grace Mensah")
    assert all(r["actor"] == "Grace Mensah" for r in _audit(client, admin, user_id=grace["id"]))

    assert any(r["entity_id"] == po["id"] for r in _audit(client, admin, q=po["po_number"]))

    secret = _audit(client, admin, action="TEST_SECRET_EVENT")[0]
    assert secret["details"]["password"] == "[redacted]"
    assert secret["details"]["api_key"] == "[redacted]"
    assert secret["details"]["nested"]["token"] == "[redacted]"
    assert secret["details"]["note"] == "visible"
    assert "hunter2" not in client.get("/audit?limit=200", headers=admin).text

    cashier = auth_headers(client, CASHIER)
    assert client.get("/audit", headers=cashier).status_code == 403
    assert client.get("/audit/facets", headers=cashier).status_code == 403


# --- Archive compatibility ---------------------------------------------------------------


def test_archived_product_history_stays_visible_across_journal_and_corrections(client):
    admin = auth_headers(client)
    med = _new_medicine(client, admin, name="Old Formula Tabs", sku="MD-OLD-1", price="1.00")
    client.post(
        "/receiving/adhoc",
        headers=admin,
        json={"items": [{"product_id": med["id"], "quantity": 5, "unit_cost": "0.5", "batch_number": "OLD-1", "expiry_date": "2028-01-01"}]},
    )
    sale = _sell(client, admin, med, qty=1, key="archived-history")
    request = client.post(f"/sales/{sale['id']}/correction-requests", headers=admin, json={"reason": "Check history"}).json()
    assert client.post(f"/products/{med['id']}/archive", headers=admin).status_code == 200

    assert all(p["id"] != med["id"] for p in client.get("/products?q=Old Formula", headers=admin).json()["items"])
    detail = client.get(f"/sales/{sale['id']}", headers=admin).json()
    assert detail["items"][0]["product_name"] == "Old Formula Tabs"
    assert detail["items"][0]["batch_number"] == "OLD-1"
    correction = client.get(f"/sale-corrections/{request['id']}", headers=admin).json()
    assert correction["sale"]["items"][0]["product_name"] == "Old Formula Tabs"
    assert any(s["id"] == sale["id"] for s in client.get(f"/sales?product_id={med['id']}", headers=admin).json()["items"])
