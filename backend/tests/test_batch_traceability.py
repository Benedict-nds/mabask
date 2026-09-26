"""Supplier / batch traceability via purchase stock movements (no Batch.supplier_id)."""

from decimal import Decimal

from tests.conftest import auth_headers


def _supplier(client, headers, name: str) -> dict:
    res = client.post(
        "/suppliers",
        headers=headers,
        json={"name": name, "contact_name": "Buyer", "email": f"{name.lower().replace(' ', '')}@example.com"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _product(client, headers, *, sku: str, name: str, supplier_id: str | None = None) -> dict:
    body = {
        "sku": sku,
        "name": name,
        "selling_price": "1.00",
        "cost_price": "0.40",
        "reorder_threshold": 0,
        "category": "Antibiotics",
    }
    if supplier_id:
        body["supplier_id"] = supplier_id
    res = client.post("/products", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _receive_po(client, headers, *, supplier_id: str, product: dict, batch_number: str, qty: int = 50) -> dict:
    po = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": qty,
                    "unit_cost": "0.40",
                    "batch_number": batch_number,
                    "expiry_date": "2028-06-01",
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
        json={
            "lines": [
                {
                    "item_id": item_id,
                    "quantity": qty,
                    "batch_number": batch_number,
                    "expiry_date": "2028-06-01",
                    "unit_cost": "0.40",
                }
            ]
        },
    )
    assert received.status_code == 200, received.text
    return po


def test_po_receipt_batch_exposes_supplier_and_po(client):
    headers = auth_headers(client)
    supplier = _supplier(client, headers, "TraceSupply A")
    product = _product(client, headers, sku="TR-1", name="Trace Med A", supplier_id=supplier["id"])
    po = _receive_po(client, headers, supplier_id=supplier["id"], product=product, batch_number="BATCH-A1")

    body = client.get(f"/products/{product['id']}", headers=headers).json()
    batch = next(b for b in body["batches"] if b["batch_number"] == "BATCH-A1")
    assert batch["supplier"]["id"] == supplier["id"]
    assert batch["supplier"]["name"] == "TraceSupply A"
    assert batch["purchase_order"]["id"] == po["id"]
    assert batch["purchase_order"]["po_number"] == po["po_number"]
    assert batch["received_at"] is not None


def test_multiple_batches_different_suppliers(client):
    headers = auth_headers(client)
    preferred = _supplier(client, headers, "Preferred Only")
    supply_x = _supplier(client, headers, "Supplier X Trace")
    supply_y = _supplier(client, headers, "Supplier Y Trace")
    product = _product(client, headers, sku="TR-PARA", name="Paracetamol Trace", supplier_id=preferred["id"])

    po_x = _receive_po(client, headers, supplier_id=supply_x["id"], product=product, batch_number="BATCH-X", qty=30)
    po_y = _receive_po(client, headers, supplier_id=supply_y["id"], product=product, batch_number="BATCH-Y", qty=40)

    body = client.get(f"/products/{product['id']}", headers=headers).json()
    assert body["supplier_id"] == preferred["id"]
    assert body["supplier_name"] == "Preferred Only"

    by_number = {b["batch_number"]: b for b in body["batches"]}
    assert by_number["BATCH-X"]["supplier"]["name"] == "Supplier X Trace"
    assert by_number["BATCH-X"]["purchase_order"]["po_number"] == po_x["po_number"]
    assert by_number["BATCH-Y"]["supplier"]["name"] == "Supplier Y Trace"
    assert by_number["BATCH-Y"]["purchase_order"]["po_number"] == po_y["po_number"]
    # Preferred product supplier must not override historical batch suppliers
    assert by_number["BATCH-X"]["supplier"]["id"] != preferred["id"]
    assert by_number["BATCH-Y"]["supplier"]["id"] != preferred["id"]


def test_manual_add_batch_has_no_fabricated_supplier(client):
    headers = auth_headers(client)
    preferred = _supplier(client, headers, "Preferred Manual")
    product = _product(client, headers, sku="TR-MAN", name="Manual Batch Med", supplier_id=preferred["id"])

    added = client.post(
        f"/products/{product['id']}/batches",
        headers=headers,
        json={"batch_number": "MANUAL-1", "expiry_date": "2029-01-01", "quantity": 10, "cost_price": "0.40"},
    )
    assert added.status_code == 201, added.text
    batch = next(b for b in added.json()["batches"] if b["batch_number"] == "MANUAL-1")
    assert batch["supplier"] is None
    assert batch["purchase_order"] is None
    assert batch["received_at"] is None


def test_sale_detail_exposes_batch_supplier(client):
    headers = auth_headers(client)
    supplier = _supplier(client, headers, "Sale Trace Supply")
    product = _product(client, headers, sku="TR-SALE", name="Sale Trace Med", supplier_id=supplier["id"])
    _receive_po(client, headers, supplier_id=supplier["id"], product=product, batch_number="SALE-BATCH", qty=20)

    sale = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment_method": "CASH",
            "amount_tendered": "10.00",
            "idempotency_key": "trace-sale-1",
        },
    )
    assert sale.status_code == 201, sale.text
    detail = client.get(f"/sales/{sale.json()['id']}", headers=headers).json()
    item = detail["items"][0]
    assert item["batch_number"] == "SALE-BATCH"
    assert item["batch_supplier_name"] == "Sale Trace Supply"
    assert item["batch_supplier_id"] == supplier["id"]
    assert item["batch_po_number"]


def test_purchase_movement_exposes_supplier_and_po(client):
    headers = auth_headers(client)
    supplier = _supplier(client, headers, "Move Trace Supply")
    product = _product(client, headers, sku="TR-MV", name="Move Trace Med", supplier_id=supplier["id"])
    po = _receive_po(client, headers, supplier_id=supplier["id"], product=product, batch_number="MOVE-BATCH")

    moves = client.get(f"/stock-movements?product_id={product['id']}", headers=headers).json()["items"]
    purchase = next(m for m in moves if m["movement_type"] == "PURCHASE")
    assert purchase["reference_type"] == "purchase_order"
    assert purchase["reference_id"] == po["id"]
    assert purchase["po_number"] == po["po_number"]
    assert purchase["supplier_id"] == supplier["id"]
    assert purchase["supplier_name"] == "Move Trace Supply"


def test_untraceable_batch_still_loads(client, db):
    headers = auth_headers(client)
    product = _product(client, headers, sku="TR-OLD", name="Old Unlinked Med")

    from datetime import date

    from app.models import Batch, Product

    db.add(
        Batch(
            product_id=product["id"],
            batch_number="ORPHAN-1",
            expiry_date=date(2027, 1, 1),
            quantity=5,
            cost_price=Decimal("0.40"),
        )
    )
    row = db.get(Product, product["id"])
    row.quantity_on_hand = 5
    db.commit()

    body = client.get(f"/products/{product['id']}", headers=headers).json()
    batch = next(b for b in body["batches"] if b["batch_number"] == "ORPHAN-1")
    assert batch["supplier"] is None
    assert batch["purchase_order"] is None
    assert body["quantity_on_hand"] == 5


def test_products_list_batch_provenance_no_n_plus_one_shape(client):
    """List endpoint returns provenance for multiple products in one response."""
    headers = auth_headers(client)
    s1 = _supplier(client, headers, "List Supply 1")
    s2 = _supplier(client, headers, "List Supply 2")
    p1 = _product(client, headers, sku="TR-L1", name="List Med 1", supplier_id=s1["id"])
    p2 = _product(client, headers, sku="TR-L2", name="List Med 2", supplier_id=s2["id"])
    _receive_po(client, headers, supplier_id=s1["id"], product=p1, batch_number="L1-B")
    _receive_po(client, headers, supplier_id=s2["id"], product=p2, batch_number="L2-B")

    page = client.get("/products?q=List Med&limit=20", headers=headers).json()
    items = {p["sku"]: p for p in page["items"]}
    assert items["TR-L1"]["batches"][0]["supplier"]["name"] == "List Supply 1"
    assert items["TR-L2"]["batches"][0]["supplier"]["name"] == "List Supply 2"
