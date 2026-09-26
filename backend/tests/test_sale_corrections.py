from tests.conftest import auth_headers


def _product(client, headers, q="Amoxicillin"):
    return client.get(f"/products?q={q}", headers=headers).json()["items"][0]


def _sell(client, headers, product, qty=1, key=None, payment="CARD"):
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": qty}],
            "payment_method": payment,
            "idempotency_key": key or f"corr-sale-{product['sku']}-{qty}-{id(product)}",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _request(client, headers, sale_id, reason="Wrong medicine entered during checkout."):
    return client.post(
        f"/sales/{sale_id}/correction-requests",
        headers=headers,
        json={"reason": reason},
    )


def test_staff_can_request_correction(client):
    admin = auth_headers(client)
    product = _product(client, admin)
    sale = _sell(client, admin, product, qty=1, key="req-1")
    res = _request(client, admin, sale["id"])
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "PENDING"
    assert body["sale_id"] == sale["id"]
    assert body["sale_number"] == sale["sale_number"]
    assert "Wrong medicine" in body["reason"]


def test_cashier_can_request_correction(client):
    admin = auth_headers(client)
    product = _product(client, admin)
    sale = _sell(client, admin, product, qty=1, key="req-cashier")
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    res = _request(client, cashier, sale["id"], reason="Entered wrong SKU at till")
    assert res.status_code == 201, res.text
    assert res.json()["requested_by_name"] == "Lena Ross"


def test_unauthorized_cannot_request_correction(client):
    admin = auth_headers(client)
    product = _product(client, admin)
    sale = _sell(client, admin, product, qty=1, key="req-unauth")
    res = client.post(f"/sales/{sale['id']}/correction-requests", json={"reason": "No token"})
    assert res.status_code in {401, 403}


def test_blank_reason_rejected(client):
    admin = auth_headers(client)
    sale = _sell(client, admin, _product(client, admin), qty=1, key="req-blank")
    res = _request(client, admin, sale["id"], reason="")
    assert res.status_code == 422


def test_whitespace_reason_rejected(client):
    admin = auth_headers(client)
    sale = _sell(client, admin, _product(client, admin), qty=1, key="req-ws")
    res = _request(client, admin, sale["id"], reason="   \n\t  ")
    assert res.status_code == 422


def test_duplicate_pending_request_rejected(client):
    admin = auth_headers(client)
    sale = _sell(client, admin, _product(client, admin), qty=1, key="req-dup")
    assert _request(client, admin, sale["id"]).status_code == 201
    again = _request(client, admin, sale["id"], reason="Second attempt")
    assert again.status_code == 409


def test_admin_can_view_pending_corrections(client):
    admin = auth_headers(client)
    sale = _sell(client, admin, _product(client, admin), qty=1, key="queue-1")
    req = _request(client, admin, sale["id"]).json()
    listed = client.get("/sale-corrections?status=PENDING", headers=admin)
    assert listed.status_code == 200
    ids = [i["id"] for i in listed.json()["items"]]
    assert req["id"] in ids


def test_cashier_cannot_approve(client):
    admin = auth_headers(client)
    product = _product(client, admin)
    sale = _sell(client, admin, product, qty=1, key="no-approve")
    req = _request(client, admin, sale["id"]).json()
    other = client.post(
        "/products",
        headers=admin,
        json={"sku": "CORR-ALT-1", "name": "Correct Alt 1", "selling_price": "0.50", "cost_price": "0.20", "initial_quantity": 5, "batch_number": "CA1", "expiry_date": "2028-01-01", "reorder_threshold": 0},
    ).json()
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    res = client.post(
        f"/sale-corrections/{req['id']}/approve",
        headers=cashier,
        json={
            "items": [{"product_id": other["id"], "quantity": 1}],
            "payment_method": "CARD",
            "idempotency_key": "approve-by-cashier",
        },
    )
    assert res.status_code == 403


def test_admin_approve_preserves_original_and_moves_stock(client):
    admin = auth_headers(client)
    wrong = _product(client, admin)
    correct = client.post(
        "/products",
        headers=admin,
        json={
            "sku": "CORR-RIGHT",
            "name": "Correct Medicine",
            "selling_price": "0.55",
            "cost_price": "0.20",
            "initial_quantity": 10,
            "batch_number": "RIGHT-1",
            "expiry_date": "2028-06-01",
            "reorder_threshold": 0,
        },
    ).json()
    before_wrong = client.get(f"/products/{wrong['id']}", headers=admin).json()["quantity_on_hand"]
    before_right = client.get(f"/products/{correct['id']}", headers=admin).json()["quantity_on_hand"]

    sale = _sell(client, admin, wrong, qty=2, key="approve-happy")
    after_sale_wrong = client.get(f"/products/{wrong['id']}", headers=admin).json()["quantity_on_hand"]
    assert after_sale_wrong == before_wrong - 2

    req = _request(client, admin, sale["id"]).json()
    approved = client.post(
        f"/sale-corrections/{req['id']}/approve",
        headers=admin,
        json={
            "items": [{"product_id": correct["id"], "quantity": 2}],
            "payment_method": "CARD",
            "idempotency_key": "approve-happy-key",
            "review_note": "Swapped to correct SKU",
        },
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "APPROVED"
    assert body["corrected_sale_id"]
    assert body["return_id"]
    assert body["financial_difference"] is not None

    original = client.get(f"/sales/{sale['id']}", headers=admin).json()
    assert original["status"] == "REFUNDED"
    assert original["items"][0]["product_id"] == wrong["id"]
    assert original["items"][0]["quantity"] == 2
    assert original["correction"]["status"] == "APPROVED"
    assert original["correction"]["corrected_sale_id"] == body["corrected_sale_id"]

    corrected = client.get(f"/sales/{body['corrected_sale_id']}", headers=admin).json()
    assert corrected["items"][0]["product_id"] == correct["id"]
    assert corrected["is_correction_of"]["original_sale_id"] == sale["id"]

    after_wrong = client.get(f"/products/{wrong['id']}", headers=admin).json()["quantity_on_hand"]
    after_right = client.get(f"/products/{correct['id']}", headers=admin).json()["quantity_on_hand"]
    assert after_wrong == before_wrong
    assert after_right == before_right - 2

    wrong_moves = client.get(f"/stock-movements?product_id={wrong['id']}", headers=admin).json()["items"]
    types = [m["movement_type"] for m in wrong_moves]
    assert "SALE" in types
    assert "RETURN" in types
    right_moves = client.get(f"/stock-movements?product_id={correct['id']}", headers=admin).json()["items"]
    assert any(m["movement_type"] == "SALE" for m in right_moves)


def test_reject_requires_reason_and_no_stock_change(client):
    admin = auth_headers(client)
    product = _product(client, admin)
    before = client.get(f"/products/{product['id']}", headers=admin).json()["quantity_on_hand"]
    sale = _sell(client, admin, product, qty=1, key="reject-1")
    after_sale = client.get(f"/products/{product['id']}", headers=admin).json()["quantity_on_hand"]
    req = _request(client, admin, sale["id"]).json()

    blank = client.post(f"/sale-corrections/{req['id']}/reject", headers=admin, json={"reason": "  "})
    assert blank.status_code == 422

    rejected = client.post(
        f"/sale-corrections/{req['id']}/reject",
        headers=admin,
        json={"reason": "Not enough evidence"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["review_note"] == "Not enough evidence"

    sale_after = client.get(f"/sales/{sale['id']}", headers=admin).json()
    assert sale_after["status"] == "COMPLETED"
    assert client.get(f"/products/{product['id']}", headers=admin).json()["quantity_on_hand"] == after_sale
    assert after_sale == before - 1


def test_already_refunded_sale_cannot_be_corrected(client):
    admin = auth_headers(client)
    product = _product(client, admin)
    sale = _sell(client, admin, product, qty=1, key="refunded-corr")
    item = sale["items"][0]
    client.post(
        "/returns",
        headers=admin,
        json={"sale_id": sale["id"], "reason": "Full refund", "restock": True, "items": [{"sale_item_id": item["id"], "quantity": 1}]},
    )
    res = _request(client, admin, sale["id"])
    assert res.status_code == 422


def test_invalid_sale_cannot_be_corrected(client):
    admin = auth_headers(client)
    res = _request(client, admin, "00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_double_approval_is_idempotent(client):
    admin = auth_headers(client)
    wrong = _product(client, admin)
    correct = client.post(
        "/products",
        headers=admin,
        json={
            "sku": "CORR-IDEM",
            "name": "Idem Correct",
            "selling_price": "0.40",
            "cost_price": "0.10",
            "initial_quantity": 5,
            "batch_number": "IDEM-1",
            "expiry_date": "2028-01-01",
            "reorder_threshold": 0,
        },
    ).json()
    sale = _sell(client, admin, wrong, qty=1, key="idem-sale")
    req = _request(client, admin, sale["id"]).json()
    payload = {
        "items": [{"product_id": correct["id"], "quantity": 1}],
        "payment_method": "CARD",
        "idempotency_key": "same-approve-key",
    }
    first = client.post(f"/sale-corrections/{req['id']}/approve", headers=admin, json=payload)
    assert first.status_code == 200, first.text
    second = client.post(f"/sale-corrections/{req['id']}/approve", headers=admin, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["corrected_sale_id"] == first.json()["corrected_sale_id"]
    sales = client.get("/sales?limit=50", headers=admin).json()["items"]
    corrected_ids = [s["id"] for s in sales if s.get("is_correction_of") and s["is_correction_of"]["original_sale_id"] == sale["id"]]
    assert len(corrected_ids) == 1


def test_insufficient_stock_for_corrected_sale_fails_safely(client):
    admin = auth_headers(client)
    wrong = _product(client, admin)
    empty = client.post(
        "/products",
        headers=admin,
        json={"sku": "CORR-EMPTY", "name": "Empty Correct Target", "selling_price": "0.40", "cost_price": "0.10", "reorder_threshold": 0},
    ).json()
    before = client.get(f"/products/{wrong['id']}", headers=admin).json()["quantity_on_hand"]
    sale = _sell(client, admin, wrong, qty=1, key="fail-stock")
    req = _request(client, admin, sale["id"]).json()
    res = client.post(
        f"/sale-corrections/{req['id']}/approve",
        headers=admin,
        json={
            "items": [{"product_id": empty["id"], "quantity": 1}],
            "payment_method": "CARD",
            "idempotency_key": "fail-stock-key",
        },
    )
    assert res.status_code == 422
    assert client.get(f"/sales/{sale['id']}", headers=admin).json()["status"] == "COMPLETED"
    assert client.get(f"/products/{wrong['id']}", headers=admin).json()["quantity_on_hand"] == before - 1
    assert client.get(f"/sale-corrections/{req['id']}", headers=admin).json()["status"] == "PENDING"


def test_financial_difference_when_prices_differ(client):
    admin = auth_headers(client)
    cheap = _product(client, admin)  # Amox selling 0.35
    expensive = client.post(
        "/products",
        headers=admin,
        json={
            "sku": "CORR-EXP",
            "name": "Expensive Correct",
            "selling_price": "1.00",
            "cost_price": "0.40",
            "initial_quantity": 5,
            "batch_number": "EXP-1",
            "expiry_date": "2028-01-01",
            "reorder_threshold": 0,
        },
    ).json()
    sale = _sell(client, admin, cheap, qty=1, key="price-diff")
    req = _request(client, admin, sale["id"]).json()
    approved = client.post(
        f"/sale-corrections/{req['id']}/approve",
        headers=admin,
        json={
            "items": [{"product_id": expensive["id"], "quantity": 1}],
            "payment_method": "CARD",
            "idempotency_key": "price-diff-key",
        },
    ).json()
    assert float(approved["refund_amount"]) > 0
    assert float(approved["corrected_sale_total"]) > float(approved["refund_amount"])
    assert float(approved["financial_difference"]) == float(approved["corrected_sale_total"]) - float(approved["refund_amount"])


def test_correction_audits(client):
    admin = auth_headers(client)
    wrong = _product(client, admin)
    right = client.post(
        "/products",
        headers=admin,
        json={
            "sku": "CORR-AUD",
            "name": "Audit Correct",
            "selling_price": "0.40",
            "cost_price": "0.10",
            "initial_quantity": 3,
            "batch_number": "AUD-1",
            "expiry_date": "2028-01-01",
            "reorder_threshold": 0,
        },
    ).json()
    sale = _sell(client, admin, wrong, qty=1, key="audit-corr")
    req = _request(client, admin, sale["id"], reason="Audit trail reason").json()
    logs = client.get("/audit?action=SALE_CORRECTION_REQUESTED", headers=admin).json()["items"]
    assert any(i["entity_id"] == req["id"] for i in logs)

    client.post(
        f"/sale-corrections/{req['id']}/approve",
        headers=admin,
        json={
            "items": [{"product_id": right["id"], "quantity": 1}],
            "payment_method": "CARD",
            "idempotency_key": "audit-approve-key",
        },
    )
    approved_logs = client.get("/audit?action=SALE_CORRECTION_APPROVED", headers=admin).json()["items"]
    assert any(i["entity_id"] == req["id"] for i in approved_logs)

    sale2 = _sell(client, admin, wrong, qty=1, key="audit-reject")
    req2 = _request(client, admin, sale2["id"], reason="Will reject").json()
    client.post(f"/sale-corrections/{req2['id']}/reject", headers=admin, json={"reason": "Not valid"})
    rejected_logs = client.get("/audit?action=SALE_CORRECTION_REJECTED", headers=admin).json()["items"]
    assert any(i["entity_id"] == req2["id"] for i in rejected_logs)
