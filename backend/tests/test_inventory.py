from tests.conftest import auth_headers


def test_create_and_list_product(client):
    headers = auth_headers(client)
    res = client.post(
        "/products",
        headers=headers,
        json={
            "sku": "MD-2001",
            "barcode": "9990001112223",
            "name": "Loratadine 10mg",
            "brand": "Claritin",
            "category": "Respiratory",
            "selling_price": "0.20",
            "cost_price": "0.06",
            "reorder_threshold": 80,
            "initial_quantity": 40,
            "batch_number": "LOR-1",
            "expiry_date": "2027-09-01",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["quantity_on_hand"] == 40
    assert body["status"] == "low"

    listed = client.get("/products?q=Loratadine", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_barcode_lookup(client):
    headers = auth_headers(client)
    res = client.get("/products/barcode/8901234500011", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Amoxicillin 500mg"


def test_stock_adjustment_and_movement(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    batch_id = product["batches"][0]["id"]
    res = client.post(
        f"/products/{product['id']}/adjust",
        headers=headers,
        json={"quantity_delta": -10, "reason": "Damaged blister packs", "movement_type": "DAMAGE", "batch_id": batch_id},
    )
    assert res.status_code == 200, res.text
    assert res.json()["quantity_on_hand"] == 90

    moves = client.get(f"/stock-movements?product_id={product['id']}", headers=headers)
    assert moves.status_code == 200
    types = [m["movement_type"] for m in moves.json()["items"]]
    assert "DAMAGE" in types


def test_low_stock_status(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    assert product["status"] == "critical"  # 100 on hand, reorder 400


def test_add_batch(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    before = product["quantity_on_hand"]
    res = client.post(
        f"/products/{product['id']}/batches",
        headers=headers,
        json={"batch_number": "AMX-FEFO-B", "expiry_date": "2029-01-01", "quantity": 20},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["quantity_on_hand"] == before + 20
    numbers = [b["batch_number"] for b in body["batches"]]
    assert "AMX-FEFO-B" in numbers


def test_short_year_expiry_is_stored_as_20xx(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    res = client.post(
        f"/products/{product['id']}/batches",
        headers=headers,
        json={"batch_number": "AMX-YY", "expiry_date": "0027-09-16", "quantity": 4},
    )
    assert res.status_code == 201, res.text
    batch = next(b for b in res.json()["batches"] if b["batch_number"] == "AMX-YY")
    assert batch["expiry_date"] == "2027-09-16"

    ghana = client.post(
        f"/products/{product['id']}/batches",
        headers=headers,
        json={"batch_number": "AMX-GH", "expiry_date": "15/09/27", "quantity": 3},
    )
    assert ghana.status_code == 201, ghana.text
    batch = next(b for b in ghana.json()["batches"] if b["batch_number"] == "AMX-GH")
    assert batch["expiry_date"] == "2027-09-15"
