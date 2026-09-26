"""Product archive / restore lifecycle (soft archive via deleted_at)."""

from decimal import Decimal

from tests.conftest import auth_headers


def _create_product(client, headers, *, sku: str = "ARCH-1", name: str = "Archive Med") -> dict:
    res = client.post(
        "/products",
        headers=headers,
        json={"sku": sku, "name": name, "selling_price": "2.00", "cost_price": "0.80", "category": "General", "reorder_threshold": 0},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _seed_history(client, headers, product: dict) -> dict:
    """Give the product a batch, purchase movement, and a sale for historical checks."""
    supplier_id = product["supplier_id"] or client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]["supplier_id"]
    if not product["supplier_id"]:
        client.patch(f"/products/{product['id']}", headers=headers, json={"supplier_id": supplier_id})

    po = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": 20,
                    "unit_cost": "0.80",
                    "batch_number": "ARCH-BATCH",
                    "expiry_date": "2028-08-01",
                }
            ],
        },
    ).json()
    item_id = po["items"][0]["id"]
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=headers)
    client.post(
        f"/purchase-orders/{po['id']}/receive",
        headers=headers,
        json={"lines": [{"item_id": item_id, "quantity": 20, "batch_number": "ARCH-BATCH", "expiry_date": "2028-08-01"}]},
    )
    sale = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "CASH",
            "amount_tendered": "10.00",
            "idempotency_key": f"arch-sale-{product['sku']}",
        },
    )
    assert sale.status_code == 201, sale.text
    return {"po": po, "sale": sale.json()}


def test_admin_can_archive_and_restore(client):
    headers = auth_headers(client)
    product = _create_product(client, headers)
    archived = client.post(f"/products/{product['id']}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    body = archived.json()
    assert body["deleted_at"] is not None
    assert body["is_active"] is True  # archive does not flip deactivate flag

    active = client.get("/products?q=Archive Med", headers=headers).json()["items"]
    assert all(p["id"] != product["id"] for p in active)

    archived_list = client.get("/products?archived=true&q=Archive Med", headers=headers)
    assert archived_list.status_code == 200
    assert any(p["id"] == product["id"] for p in archived_list.json()["items"])

    restored = client.post(f"/products/{product['id']}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["deleted_at"] is None
    assert any(p["id"] == product["id"] for p in client.get("/products?q=Archive Med", headers=headers).json()["items"])


def test_non_admin_cannot_archive_or_restore(client):
    admin = auth_headers(client)
    product = _create_product(client, admin, sku="ARCH-PERM", name="Perm Archive Med")
    client.post(f"/products/{product['id']}/archive", headers=admin)

    for email in ("lena@brightcare.pharmacy", "grace@brightcare.pharmacy"):
        headers = auth_headers(client, email)
        assert client.post(f"/products/{product['id']}/restore", headers=headers).status_code == 403
        # restore as admin for next archive denial check
        client.post(f"/products/{product['id']}/restore", headers=admin)
        assert client.post(f"/products/{product['id']}/archive", headers=headers).status_code == 403
        assert client.get("/products?archived=true", headers=headers).status_code == 403


def test_archive_preserves_history_and_traceability(client):
    headers = auth_headers(client)
    product = _create_product(client, headers, sku="ARCH-HIST", name="History Archive Med")
    hist = _seed_history(client, headers, product)
    before = client.get(f"/products/{product['id']}", headers=headers).json()
    qty_before = before["quantity_on_hand"]
    batch_before = next(b for b in before["batches"] if b["batch_number"] == "ARCH-BATCH")
    assert batch_before["supplier"] is not None
    moves_before = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["total"]

    archived = client.post(f"/products/{product['id']}/archive", headers=headers).json()
    assert archived["quantity_on_hand"] == qty_before

    # Product still loadable; batches + provenance intact
    detail = client.get(f"/products/{product['id']}", headers=headers).json()
    assert detail["deleted_at"] is not None
    batch = next(b for b in detail["batches"] if b["batch_number"] == "ARCH-BATCH")
    assert batch["quantity"] == batch_before["quantity"]
    assert batch["supplier"]["name"] == batch_before["supplier"]["name"]
    assert batch["purchase_order"]["po_number"] == batch_before["purchase_order"]["po_number"]

    moves = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()
    assert moves["total"] == moves_before
    purchase = next(m for m in moves["items"] if m["movement_type"] == "PURCHASE")
    assert purchase["po_number"]
    assert purchase["supplier_name"]

    sale = client.get(f"/sales/{hist['sale']['id']}", headers=headers).json()
    assert sale["items"][0]["product_name"] == "History Archive Med"
    assert sale["items"][0]["batch_supplier_name"]

    journal = client.get(f"/sales?q={hist['sale']['sale_number']}", headers=headers).json()
    assert any(s["id"] == hist["sale"]["id"] for s in journal["items"])

    po = client.get(f"/purchase-orders/{hist['po']['id']}", headers=headers).json()
    assert po["items"][0]["product_id"] == product["id"]


def test_restore_does_not_create_stock_or_movements(client):
    headers = auth_headers(client)
    product = _create_product(client, headers, sku="ARCH-STOCK", name="Stock Archive Med")
    _seed_history(client, headers, product)
    before = client.get(f"/products/{product['id']}", headers=headers).json()
    moves_before = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["total"]

    client.post(f"/products/{product['id']}/archive", headers=headers)
    restored = client.post(f"/products/{product['id']}/restore", headers=headers).json()
    assert restored["quantity_on_hand"] == before["quantity_on_hand"]
    moves_after = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["total"]
    assert moves_after == moves_before


def test_archive_restore_idempotency(client):
    headers = auth_headers(client)
    product = _create_product(client, headers, sku="ARCH-IDEM", name="Idem Archive Med")
    assert client.post(f"/products/{product['id']}/archive", headers=headers).status_code == 200
    assert client.post(f"/products/{product['id']}/archive", headers=headers).status_code == 409
    assert client.post(f"/products/{product['id']}/restore", headers=headers).status_code == 200
    assert client.post(f"/products/{product['id']}/restore", headers=headers).status_code == 409


def test_archive_audit_events(client):
    headers = auth_headers(client)
    product = _create_product(client, headers, sku="ARCH-AUD", name="Audit Archive Med")
    client.post(f"/products/{product['id']}/archive", headers=headers)
    client.post(f"/products/{product['id']}/restore", headers=headers)
    logs = client.get("/audit", headers=headers).json()["items"]
    archived = [i for i in logs if i["action"] == "PRODUCT_ARCHIVED" and i["entity_id"] == product["id"]]
    restored = [i for i in logs if i["action"] == "PRODUCT_RESTORED" and i["entity_id"] == product["id"]]
    assert len(archived) == 1
    assert len(restored) == 1
    assert archived[0]["details"]["sku"] == "ARCH-AUD"
    assert restored[0]["details"]["name"] == "Audit Archive Med"


def test_archived_sku_remains_reserved(client):
    headers = auth_headers(client)
    product = _create_product(client, headers, sku="ARCH-SKU", name="SKU Archive Med")
    client.post(f"/products/{product['id']}/archive", headers=headers)
    conflict = client.post(
        "/products",
        headers=headers,
        json={"sku": "ARCH-SKU", "name": "Other Med", "selling_price": "1.00", "cost_price": "0.40", "reorder_threshold": 0},
    )
    assert conflict.status_code == 409


def test_archived_excluded_from_barcode_and_sale(client):
    headers = auth_headers(client)
    product = _create_product(client, headers, sku="ARCH-POS", name="POS Archive Med")
    client.patch(f"/products/{product['id']}", headers=headers, json={"barcode": "8909999000111"})
    # seed stock via add batch
    client.post(
        f"/products/{product['id']}/batches",
        headers=headers,
        json={"batch_number": "POS-B", "expiry_date": "2028-01-01", "quantity": 5, "cost_price": "0.80"},
    )
    client.post(f"/products/{product['id']}/archive", headers=headers)

    assert client.get("/products/barcode/8909999000111", headers=headers).status_code == 404
    sale = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "CASH",
            "amount_tendered": "10.00",
            "idempotency_key": "arch-pos-block",
        },
    )
    assert sale.status_code in {400, 404, 422}


def test_is_active_preserved_across_archive_restore(client):
    headers = auth_headers(client)
    product = _create_product(client, headers, sku="ARCH-INA", name="Inactive Archive Med")
    client.delete(f"/products/{product['id']}", headers=headers)  # deactivate is_active=false
    assert client.get(f"/products/{product['id']}", headers=headers).json()["is_active"] is False

    client.post(f"/products/{product['id']}/archive", headers=headers)
    archived = client.get(f"/products/{product['id']}", headers=headers).json()
    assert archived["deleted_at"] is not None
    assert archived["is_active"] is False

    restored = client.post(f"/products/{product['id']}/restore", headers=headers).json()
    assert restored["deleted_at"] is None
    assert restored["is_active"] is False
