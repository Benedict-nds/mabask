from tests.conftest import auth_headers


def test_successful_sale_deducts_stock(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    before = product["quantity_on_hand"]
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": 3}],
            "payment_method": "CASH",
            "amount_tendered": "20",
            "discount_percent": 0,
            "idempotency_key": "sale-1",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert float(body["total"]) > 0
    assert float(body["change_due"]) >= 0
    after = client.get(f"/products/{product['id']}", headers=headers).json()
    assert after["quantity_on_hand"] == before - 3


def test_sale_idempotent(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    payload = {
        "items": [{"product_id": product["id"], "quantity": 1}],
        "payment_method": "CARD",
        "idempotency_key": "same-key",
    }
    a = client.post("/sales", headers=headers, json=payload)
    b = client.post("/sales", headers=headers, json=payload)
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["id"] == b.json()["id"]


def test_insufficient_stock(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": 5000}],
            "payment_method": "CASH",
            "amount_tendered": "1",
            "idempotency_key": "too-much",
        },
    )
    assert res.status_code == 422
    after = client.get(f"/products/{product['id']}", headers=headers).json()
    assert after["quantity_on_hand"] == product["quantity_on_hand"]


def test_fefo_deducts_earliest_expiry_first(client):
    headers = auth_headers(client)
    created = client.post(
        "/products",
        headers=headers,
        json={
            "sku": "MD-FEFO",
            "barcode": "8901234599999",
            "name": "FEFO Test Capsule",
            "brand": "Test",
            "category": "Antibiotics",
            "selling_price": "1.00",
            "cost_price": "0.40",
            "reorder_threshold": 5,
            "initial_quantity": 10,
            "batch_number": "FEFO-A",
            "expiry_date": "2027-01-01",
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    add = client.post(
        f"/products/{product_id}/batches",
        headers=headers,
        json={"batch_number": "FEFO-B", "expiry_date": "2029-01-01", "quantity": 20},
    )
    assert add.status_code == 201, add.text
    sale = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "quantity": 15}],
            "payment_method": "CARD",
            "idempotency_key": "fefo-15",
        },
    )
    assert sale.status_code == 201, sale.text
    after = client.get(f"/products/{product_id}", headers=headers).json()
    by_batch = {b["batch_number"]: b["quantity"] for b in after["batches"]}
    assert by_batch["FEFO-A"] == 0
    assert by_batch["FEFO-B"] == 15
    assert after["quantity_on_hand"] == 15


def test_expired_batch_cannot_be_sold(client):
    headers = auth_headers(client)
    created = client.post(
        "/products",
        headers=headers,
        json={
            "sku": "MD-EXPIRED",
            "barcode": "8901234500888",
            "name": "Expired Capsule",
            "brand": "Test",
            "category": "Antibiotics",
            "selling_price": "1.00",
            "cost_price": "0.40",
            "reorder_threshold": 1,
            "initial_quantity": 10,
            "batch_number": "EXP-OLD",
            "expiry_date": "2020-01-01",
        },
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "quantity": 1}],
            "payment_method": "CASH",
            "amount_tendered": "5",
            "idempotency_key": "expired-sale",
        },
    )
    assert res.status_code == 422
    after = client.get(f"/products/{product_id}", headers=headers).json()
    assert after["quantity_on_hand"] == 10


def test_backend_calculates_totals(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment_method": "MOBILE_MONEY",
            "discount_percent": 10,
            "idempotency_key": "totals",
        },
    )
    body = res.json()
    # 2 * 0.35 = 0.70, 10% off = 0.07, taxable 0.63, 5% tax = 0.03, total 0.66
    assert float(body["subtotal"]) == 0.70
    assert float(body["discount_amount"]) == 0.07
    assert float(body["total"]) == 0.66
