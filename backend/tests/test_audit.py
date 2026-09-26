from tests.conftest import auth_headers


def test_successful_sale_writes_audit(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    client.post(
        "/sales",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}], "payment_method": "CARD", "idempotency_key": "aud-1"},
    )
    logs = client.get("/audit", headers=headers)
    assert logs.status_code == 200
    actions = [i["action"] for i in logs.json()["items"]]
    assert "SALE_COMPLETED" in actions
    assert "LOGIN" in actions
    filtered = client.get("/audit?action=SALE_COMPLETED", headers=headers)
    assert filtered.status_code == 200
    assert all(i["action"] == "SALE_COMPLETED" for i in filtered.json()["items"])
    login = next(i for i in logs.json()["items"] if i["action"] == "LOGIN")
    assert "ip" in login["details"]


def test_failed_sale_does_not_write_success_audit(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    before = [i["action"] for i in client.get("/audit", headers=headers).json()["items"]].count("SALE_COMPLETED")
    client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": 9999}],
            "payment_method": "CASH",
            "amount_tendered": "1",
            "idempotency_key": "aud-fail",
        },
    )
    after = [i["action"] for i in client.get("/audit", headers=headers).json()["items"]].count("SALE_COMPLETED")
    assert after == before


def test_failed_receive_does_not_write_success_audit(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    created = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": product["supplier_id"],
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": 5,
                    "unit_cost": "0.18",
                    "batch_number": "FAIL-RCV",
                    "expiry_date": "2028-01-01",
                }
            ],
        },
    )
    po_id = created.json()["id"]
    item_id = created.json()["items"][0]["id"]
    client.post(f"/purchase-orders/{po_id}/submit", headers=headers)
    client.post(f"/purchase-orders/{po_id}/approve", headers=headers)
    before = [i["action"] for i in client.get("/audit", headers=headers).json()["items"]].count("PURCHASE_ORDER_RECEIVED")
    res = client.post(
        f"/purchase-orders/{po_id}/receive",
        headers=headers,
        json={"lines": [{"item_id": item_id, "quantity": 9}]},
    )
    assert res.status_code == 422
    after = [i["action"] for i in client.get("/audit", headers=headers).json()["items"]].count("PURCHASE_ORDER_RECEIVED")
    assert after == before
