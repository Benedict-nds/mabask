from tests.conftest import auth_headers


def test_create_product_zero_stock_no_movement(client):
    headers = auth_headers(client)
    res = client.post(
        "/products",
        headers=headers,
        json={
            "sku": "CET-10",
            "name": "Cetirizine 10mg",
            "selling_price": "0.40",
            "cost_price": "0.12",
            "reorder_threshold": 0,
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["quantity_on_hand"] == 0
    assert body["batches"] == []
    assert body["barcode"] == ""

    moves = client.get(f"/stock-movements?product_id={body['id']}", headers=headers)
    assert moves.status_code == 200
    assert moves.json()["items"] == []


def test_new_product_on_po_stays_zero_until_receive(client):
    headers = auth_headers(client)
    supplier_id = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]["supplier_id"]
    created = client.post(
        "/products",
        headers=headers,
        json={
            "sku": "AMOX-NEW-PO",
            "name": "Amoxicillin Susp 125mg",
            "selling_price": "1.20",
            "cost_price": "0.55",
            "category": "Antibiotics",
            "reorder_threshold": 0,
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()
    assert product["quantity_on_hand"] == 0

    po = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "notes": "New medicine PO",
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": 100,
                    "unit_cost": "0.55",
                    "batch_number": "",
                    "expiry_date": None,
                }
            ],
        },
    )
    assert po.status_code == 201, po.text
    assert po.json()["items"][0]["product_id"] == product["id"]
    assert client.get(f"/products/{product['id']}", headers=headers).json()["quantity_on_hand"] == 0

    moves = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["items"]
    assert moves == []


def test_receive_new_product_creates_batch_and_purchase_movement(client):
    headers = auth_headers(client)
    supplier_id = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]["supplier_id"]
    product = client.post(
        "/products",
        headers=headers,
        json={"sku": "CET-RCV", "name": "Cetirizine 10mg Tabs", "selling_price": "0.40", "cost_price": "0.12", "reorder_threshold": 0},
    ).json()

    po = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": 100,
                    "unit_cost": "0.12",
                    "batch_number": "ABC123",
                    "expiry_date": "2028-05-01",
                }
            ],
        },
    ).json()
    item_id = po["items"][0]["id"]
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=headers)

    received = client.post(
        f"/purchase-orders/{po['id']}/receive",
        headers=headers,
        json={"lines": [{"item_id": item_id, "quantity": 100, "batch_number": "ABC123", "expiry_date": "2028-05-01"}]},
    )
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "RECEIVED"

    after = client.get(f"/products/{product['id']}", headers=headers).json()
    assert after["quantity_on_hand"] == 100
    assert any(b["batch_number"] == "ABC123" and b["quantity"] == 100 for b in after["batches"])

    moves = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["items"]
    purchase = [m for m in moves if m["movement_type"] == "PURCHASE"]
    assert len(purchase) == 1
    assert purchase[0]["quantity"] == 100
    assert purchase[0]["reference_type"] == "purchase_order"
    assert purchase[0]["reference_id"] == po["id"]


def test_manual_receive_multiple_lines(client):
    headers = auth_headers(client)
    amox = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    supplier_id = amox["supplier_id"]
    other = client.post(
        "/products",
        headers=headers,
        json={"sku": "IBU-200", "name": "Ibuprofen 200mg", "selling_price": "0.25", "cost_price": "0.08", "reorder_threshold": 0},
    ).json()
    before_amox = amox["quantity_on_hand"]

    res = client.post(
        "/receiving/manual",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "notes": "Manual receiving",
            "items": [
                {
                    "product_id": amox["id"],
                    "product_name": amox["name"],
                    "quantity_ordered": 5,
                    "unit_cost": "0.18",
                    "batch_number": "MAN-AMX",
                    "expiry_date": "2028-06-01",
                },
                {
                    "product_id": other["id"],
                    "product_name": other["name"],
                    "quantity_ordered": 12,
                    "unit_cost": "0.08",
                    "batch_number": "MAN-IBU",
                    "expiry_date": "2028-07-01",
                },
            ],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "RECEIVED"
    assert res.json()["notes"] == "Manual receiving"

    assert client.get(f"/products/{amox['id']}", headers=headers).json()["quantity_on_hand"] == before_amox + 5
    assert client.get(f"/products/{other['id']}", headers=headers).json()["quantity_on_hand"] == 12


def test_manual_receive_invalid_line_prevents_partial(client):
    headers = auth_headers(client)
    amox = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    before = amox["quantity_on_hand"]
    other = client.post(
        "/products",
        headers=headers,
        json={"sku": "PARA-FAIL", "name": "Paracetamol Fail Path", "selling_price": "0.10", "cost_price": "0.03", "reorder_threshold": 0},
    ).json()

    res = client.post(
        "/receiving/manual",
        headers=headers,
        json={
            "supplier_id": amox["supplier_id"],
            "notes": "Manual receiving",
            "items": [
                {
                    "product_id": amox["id"],
                    "product_name": amox["name"],
                    "quantity_ordered": 3,
                    "unit_cost": "0.18",
                    "batch_number": "OK-1",
                    "expiry_date": "2028-06-01",
                },
                {
                    "product_id": other["id"],
                    "product_name": other["name"],
                    "quantity_ordered": 4,
                    "unit_cost": "0.03",
                    "batch_number": "",
                    "expiry_date": "2028-06-01",
                },
            ],
        },
    )
    assert res.status_code == 422
    assert client.get(f"/products/{amox['id']}", headers=headers).json()["quantity_on_hand"] == before
    assert client.get(f"/products/{other['id']}", headers=headers).json()["quantity_on_hand"] == 0


def test_multi_line_po_receive_rejects_overreceive_atomically(client):
    headers = auth_headers(client)
    amox = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    other = client.post(
        "/products",
        headers=headers,
        json={"sku": "VIT-C", "name": "Vitamin C 500mg", "selling_price": "0.30", "cost_price": "0.10", "reorder_threshold": 0},
    ).json()
    before = amox["quantity_on_hand"]

    po = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": amox["supplier_id"],
            "items": [
                {
                    "product_id": amox["id"],
                    "product_name": amox["name"],
                    "quantity_ordered": 5,
                    "unit_cost": "0.18",
                    "batch_number": "A1",
                    "expiry_date": "2028-01-01",
                },
                {
                    "product_id": other["id"],
                    "product_name": other["name"],
                    "quantity_ordered": 5,
                    "unit_cost": "0.10",
                    "batch_number": "V1",
                    "expiry_date": "2028-01-01",
                },
            ],
        },
    ).json()
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=headers)
    a_id, b_id = po["items"][0]["id"], po["items"][1]["id"]

    res = client.post(
        f"/purchase-orders/{po['id']}/receive",
        headers=headers,
        json={
            "lines": [
                {"item_id": a_id, "quantity": 5, "batch_number": "A1", "expiry_date": "2028-01-01"},
                {"item_id": b_id, "quantity": 9, "batch_number": "V1", "expiry_date": "2028-01-01"},
            ]
        },
    )
    assert res.status_code == 422
    assert client.get(f"/products/{amox['id']}", headers=headers).json()["quantity_on_hand"] == before
    assert client.get(f"/products/{other['id']}", headers=headers).json()["quantity_on_hand"] == 0
    assert client.get(f"/purchase-orders/{po['id']}", headers=headers).json()["status"] == "APPROVED"


def test_cashier_cannot_manual_receive(client):
    admin = auth_headers(client)
    amox = client.get("/products?q=Amoxicillin", headers=admin).json()["items"][0]
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    res = client.post(
        "/receiving/manual",
        headers=cashier,
        json={
            "supplier_id": amox["supplier_id"],
            "items": [
                {
                    "product_id": amox["id"],
                    "product_name": amox["name"],
                    "quantity_ordered": 1,
                    "unit_cost": "0.18",
                    "batch_number": "X",
                    "expiry_date": "2028-01-01",
                }
            ],
        },
    )
    assert res.status_code == 403


def test_cashier_cannot_create_product(client):
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    res = client.post(
        "/products",
        headers=cashier,
        json={"sku": "NOPE", "name": "Should Fail", "selling_price": "1.00", "reorder_threshold": 0, "cost_price": "0.10"},
    )
    assert res.status_code == 403


def test_optional_barcode_still_unique(client):
    headers = auth_headers(client)
    first = client.post(
        "/products",
        headers=headers,
        json={"sku": "BAR-1", "barcode": "1112223334445", "name": "Unique Bar One", "selling_price": "1", "reorder_threshold": 0, "cost_price": "0.10"},
    )
    assert first.status_code == 201
    dup = client.post(
        "/products",
        headers=headers,
        json={"sku": "BAR-2", "barcode": "1112223334445", "name": "Unique Bar Two", "selling_price": "1", "reorder_threshold": 0, "cost_price": "0.10"},
    )
    assert dup.status_code == 409
