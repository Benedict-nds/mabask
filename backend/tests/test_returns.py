from tests.conftest import auth_headers


def _sale(client, headers, qty=2):
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": qty}],
            "payment_method": "CARD",
            "idempotency_key": f"ret-{qty}",
        },
    )
    assert res.status_code == 201, res.text
    return res.json(), product


def test_valid_return_restocks(client):
    headers = auth_headers(client)
    sale, product = _sale(client, headers)
    after_sale = client.get(f"/products/{product['id']}", headers=headers).json()["quantity_on_hand"]
    item = sale["items"][0]
    res = client.post(
        "/returns",
        headers=headers,
        json={"sale_id": sale["id"], "reason": "Customer changed mind", "restock": True, "items": [{"sale_item_id": item["id"], "quantity": 1}]},
    )
    assert res.status_code == 201, res.text
    restored = client.get(f"/products/{product['id']}", headers=headers).json()["quantity_on_hand"]
    assert restored == after_sale + 1


def test_excessive_return_rejected(client):
    headers = auth_headers(client)
    sale, _ = _sale(client, headers, qty=1)
    item = sale["items"][0]
    res = client.post(
        "/returns",
        headers=headers,
        json={"sale_id": sale["id"], "reason": "Trying too many", "items": [{"sale_item_id": item["id"], "quantity": 4}]},
    )
    assert res.status_code == 422
