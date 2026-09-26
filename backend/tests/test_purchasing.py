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

    submitted = client.post(f"/purchase-orders/{po_id}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
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
    assert client.post(f"/purchase-orders/{po_id}/submit", headers=headers).status_code == 200
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


def _draft(client, headers, qty=4, notes="Restock"):
    product, supplier_id = _product_and_supplier(client, headers)
    created = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "notes": notes,
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "quantity_ordered": qty,
                    "unit_cost": "0.18",
                    "batch_number": "REV",
                    "expiry_date": "2028-01-01",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json(), product, supplier_id


def _put_body(po, product, qty=None, supplier_id=None):
    item = po["items"][0]
    return {
        "supplier_id": supplier_id or po["supplier_id"],
        "notes": po.get("notes") or "Updated",
        "items": [
            {
                "product_id": product["id"],
                "product_name": product["name"],
                "quantity_ordered": qty if qty is not None else item["quantity_ordered"] + 1,
                "unit_cost": "0.18",
                "batch_number": item["batch_number"],
                "expiry_date": item["expiry_date"],
            }
        ],
    }


def test_draft_to_submitted(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    res = client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "SUBMITTED"


def test_submitted_to_changes_requested(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    res = client.post(
        f"/purchase-orders/{po['id']}/request-changes",
        headers=headers,
        json={"reason": "Please correct the quantities for Amoxicillin before approval."},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "CHANGES_REQUESTED"
    assert "correct the quantities" in body["review_comment"]
    assert body["review_requested_by_name"]


def test_changes_requested_edit_returns_to_draft(client):
    headers = auth_headers(client)
    po, product, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": "Fix qty"})
    res = client.put(f"/purchase-orders/{po['id']}", headers=headers, json=_put_body(po, product, qty=9))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "DRAFT"
    assert res.json()["items"][0]["quantity_ordered"] == 9
    assert res.json()["review_comment"] == "Fix qty"


def test_resubmit_then_approve_after_changes(client):
    headers = auth_headers(client)
    po, product, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": "Fix qty"})
    edited = client.put(f"/purchase-orders/{po['id']}", headers=headers, json=_put_body(po, product, qty=9))
    assert edited.json()["status"] == "DRAFT"
    submitted = client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    assert submitted.json()["status"] == "SUBMITTED"
    approved = client.post(f"/purchase-orders/{po['id']}/approve", headers=headers)
    assert approved.json()["status"] == "APPROVED"


def test_request_changes_empty_reason_fails(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    res = client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": ""})
    assert res.status_code == 422


def test_request_changes_whitespace_reason_fails(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    res = client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": "   \n\t  "})
    assert res.status_code == 422


def test_request_changes_from_draft_fails(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    res = client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": "Too soon"})
    assert res.status_code == 422


def test_request_changes_from_approved_fails(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=headers)
    res = client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": "Too late"})
    assert res.status_code == 422


def test_edit_submitted_po_fails(client):
    headers = auth_headers(client)
    po, product, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    res = client.put(f"/purchase-orders/{po['id']}", headers=headers, json=_put_body(po, product))
    assert res.status_code == 422


def test_edit_approved_po_fails(client):
    headers = auth_headers(client)
    po, product, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=headers)
    res = client.put(f"/purchase-orders/{po['id']}", headers=headers, json=_put_body(po, product))
    assert res.status_code == 422


def test_cashier_cannot_approve(client):
    admin = auth_headers(client)
    po, _, _ = _draft(client, admin)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=admin)
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    res = client.post(f"/purchase-orders/{po['id']}/approve", headers=cashier)
    assert res.status_code == 403


def test_cashier_cannot_request_changes(client):
    admin = auth_headers(client)
    po, _, _ = _draft(client, admin)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=admin)
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    res = client.post(
        f"/purchase-orders/{po['id']}/request-changes",
        headers=cashier,
        json={"reason": "Cashiers should not review POs"},
    )
    assert res.status_code == 403


def test_cashier_cannot_edit_po(client):
    admin = auth_headers(client)
    po, product, _ = _draft(client, admin)
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    res = client.put(f"/purchase-orders/{po['id']}", headers=cashier, json=_put_body(po, product))
    assert res.status_code == 403


def test_submit_and_approve_write_audit(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/approve", headers=headers)
    logs = client.get("/audit", headers=headers).json()["items"]
    actions = [i["action"] for i in logs]
    assert "PURCHASE_ORDER_SUBMITTED" in actions
    assert "PURCHASE_ORDER_APPROVED" in actions
    submitted = next(i for i in logs if i["action"] == "PURCHASE_ORDER_SUBMITTED")
    assert submitted["details"]["po_number"] == po["po_number"]
    assert submitted["details"]["previous_status"] == "DRAFT"
    assert submitted["details"]["new_status"] == "SUBMITTED"


def test_request_changes_writes_audit_with_reason(client):
    headers = auth_headers(client)
    po, _, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    reason = "Please correct the quantities for Amoxicillin before approval."
    client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": reason})
    logs = client.get("/audit?action=PURCHASE_ORDER_CHANGES_REQUESTED", headers=headers).json()["items"]
    assert logs
    assert logs[0]["details"]["reason"] == reason
    assert logs[0]["details"]["previous_status"] == "SUBMITTED"
    assert logs[0]["details"]["new_status"] == "CHANGES_REQUESTED"


def test_edit_after_changes_requested_is_audited(client):
    headers = auth_headers(client)
    po, product, _ = _draft(client, headers)
    client.post(f"/purchase-orders/{po['id']}/submit", headers=headers)
    client.post(f"/purchase-orders/{po['id']}/request-changes", headers=headers, json={"reason": "Fix qty"})
    client.put(f"/purchase-orders/{po['id']}", headers=headers, json=_put_body(po, product, qty=9))
    logs = client.get("/audit?action=PURCHASE_ORDER_UPDATED", headers=headers).json()["items"]
    assert logs
    assert logs[0]["details"]["previous_status"] == "CHANGES_REQUESTED"
    assert logs[0]["details"]["new_status"] == "DRAFT"

