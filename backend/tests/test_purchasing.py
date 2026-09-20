from tests.conftest import auth_headers


def _product_and_supplier(client, headers):
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    supplier_id = product["supplier_id"]
    return product, supplier_id


def test_po_lifecycle_and_receive(client):
    headers = auth_headers(client)
    product, supplier_id = _product_and_supplier(client, headers)
    before = product["quantity_on_hand"]

    created = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "notes": "Restock",
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": 20,
                    "unit_cost": "0.18",
                    "batch_number": "AMX-NEW",
                    "expiry_date": "2028-01-01",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    po_id = created.json()["id"]
    item_id = created.json()["items"][0]["id"]

    assert client.post(f"/purchase-orders/{po_id}/approve", headers=headers).status_code == 200

    received = client.post(
        f"/purchase-orders/{po_id}/receive",
        headers=headers,
        json={"lines": [{"item_id": item_id, "quantity": 12, "batch_number": "AMX-NEW", "expiry_date": "2028-01-01"}]},
    )
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "PARTIALLY_RECEIVED"

    after = client.get(f"/products/{product['id']}", headers=headers).json()
    assert after["quantity_on_hand"] == before + 12

    full = client.post(
        f"/purchase-orders/{po_id}/receive",
        headers=headers,
        json={"lines": [{"item_id": item_id, "quantity": 8, "batch_number": "AMX-NEW", "expiry_date": "2028-01-01"}]},
    )
    assert full.json()["status"] == "RECEIVED"
    after2 = client.get(f"/products/{product['id']}", headers=headers).json()
    assert after2["quantity_on_hand"] == before + 20


def test_submit_then_approve(client):
    headers = auth_headers(client)
    product, supplier_id = _product_and_supplier(client, headers)
    created = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": 4,
                    "unit_cost": "0.18",
                    "batch_number": "SUB",
                    "expiry_date": "2028-01-01",
                }
            ],
        },
    )
    po_id = created.json()["id"]
    submitted = client.post(f"/purchase-orders/{po_id}/submit", headers=headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "SUBMITTED"
    approved = client.post(f"/purchase-orders/{po_id}/approve", headers=headers)
    assert approved.json()["status"] == "APPROVED"


def test_cannot_over_receive(client):
    headers = auth_headers(client)
    product, supplier_id = _product_and_supplier(client, headers)
    created = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": 5,
                    "unit_cost": "0.18",
                    "batch_number": "X",
                    "expiry_date": "2028-01-01",
                }
            ],
        },
    )
    po_id = created.json()["id"]
    item_id = created.json()["items"][0]["id"]
    client.post(f"/purchase-orders/{po_id}/approve", headers=headers)
    res = client.post(
        f"/purchase-orders/{po_id}/receive",
        headers=headers,
        json={"lines": [{"item_id": item_id, "quantity": 9}]},
    )
    assert res.status_code == 422


def test_csv_extract_normalizes_short_year(client):
    headers = auth_headers(client)
    csv = "name,quantity,unit_cost,batch,expiry\nAmoxicillin 500mg,10,0.18,NEW-1,15/09/27\n"
    res = client.post(
        "/receiving/extract",
        headers=headers,
        files={"file": ("invoice.csv", csv, "text/csv")},
    )
    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["expiry"] == "2027-09-15"

    padded = client.post(
        "/receiving/extract",
        headers=headers,
        files={"file": ("invoice.csv", "name,quantity,unit_cost,batch,expiry\nAmoxicillin 500mg,10,0.18,NEW-2,0027-09-16\n", "text/csv")},
    )
    assert padded.status_code == 200, padded.text
    assert padded.json()["items"][0]["expiry"] == "2027-09-16"
