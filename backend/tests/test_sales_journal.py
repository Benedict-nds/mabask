from datetime import date, timedelta

from tests.conftest import auth_headers


def _sell(client, headers, product, qty=1, key="journal-sale", payment="CARD"):
    res = client.post(
        "/sales",
        headers=headers,
        json={
            "items": [{"product_id": product["id"], "quantity": qty}],
            "payment_method": payment,
            "idempotency_key": key,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_sales_list_paginated(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    _sell(client, headers, product, key="page-a")
    _sell(client, headers, product, key="page-b")
    page = client.get("/sales?limit=1&offset=0", headers=headers)
    assert page.status_code == 200
    body = page.json()
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert body["total"] >= 2
    assert len(body["items"]) == 1
    page2 = client.get("/sales?limit=1&offset=1", headers=headers)
    assert len(page2.json()["items"]) == 1
    assert page2.json()["items"][0]["id"] != body["items"][0]["id"]


def test_filter_by_date_cashier_payment_status(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    sale = _sell(client, headers, product, key="filt-1", payment="CASH")
    today = date.today().isoformat()
    listed = client.get(
        f"/sales?date_from={today}&date_to={today}&cashier_id={sale['cashier_id']}&payment_method=CASH&status=COMPLETED",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    ids = [i["id"] for i in listed.json()["items"]]
    assert sale["id"] in ids

    empty = client.get(
        f"/sales?date_from={(date.today() - timedelta(days=30)).isoformat()}&date_to={(date.today() - timedelta(days=29)).isoformat()}",
        headers=headers,
    )
    assert sale["id"] not in [i["id"] for i in empty.json()["items"]]


def test_search_sale_number_product_sku(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    sale = _sell(client, headers, product, key="search-1")
    by_number = client.get(f"/sales?q={sale['sale_number']}", headers=headers)
    assert by_number.json()["total"] >= 1
    assert by_number.json()["items"][0]["sale_number"] == sale["sale_number"]

    by_name = client.get("/sales?q=Amoxicillin", headers=headers)
    assert any(i["id"] == sale["id"] for i in by_name.json()["items"])

    by_sku = client.get(f"/sales?q={product['sku']}", headers=headers)
    assert any(i["id"] == sale["id"] for i in by_sku.json()["items"])


def test_cashier_cannot_access_sales_export(client):
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    # cashiers have sales.read for POS lookup, but export requires reports.read
    res = client.get("/sales/export.csv", headers=cashier)
    assert res.status_code == 403


def test_unauthorized_cannot_access_reports(client):
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    assert client.get("/reports/sales", headers=cashier).status_code == 403


def test_correction_links_in_journal(client):
    headers = auth_headers(client)
    wrong = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    right = client.post(
        "/products",
        headers=headers,
        json={
            "sku": "JRN-RIGHT",
            "name": "Journal Right Med",
            "selling_price": "0.90",
            "cost_price": "0.30",
            "initial_quantity": 5,
            "batch_number": "JRN-1",
            "expiry_date": "2028-01-01",
            "reorder_threshold": 0,
        },
    ).json()
    sale = _sell(client, headers, wrong, key="jrn-corr")
    req = client.post(
        f"/sales/{sale['id']}/correction-requests",
        headers=headers,
        json={"reason": "Wrong item at till"},
    ).json()
    approved = client.post(
        f"/sale-corrections/{req['id']}/approve",
        headers=headers,
        json={
            "items": [{"product_id": right["id"], "quantity": 1}],
            "payment_method": "CARD",
            "idempotency_key": "jrn-approve",
        },
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()

    original = client.get(f"/sales/{sale['id']}", headers=headers).json()
    assert original["status"] == "REFUNDED"
    assert original["correction"]["corrected_sale_number"] == body["corrected_sale_number"]
    assert original["correction"]["financial_difference"] is not None
    assert original["returns"]
    assert any(m["movement_type"] == "SALE" for m in original["stock_movements"])
    assert any(m["movement_type"] == "RETURN" for m in original["stock_movements"])

    corrected = client.get(f"/sales/{body['corrected_sale_id']}", headers=headers).json()
    assert corrected["is_correction_of"]["original_sale_id"] == sale["id"]

    corrected_list = client.get("/sales?correction=corrected", headers=headers).json()["items"]
    assert any(i["id"] == sale["id"] for i in corrected_list)
    corr_sales = client.get("/sales?correction=correction_sale", headers=headers).json()["items"]
    assert any(i["id"] == body["corrected_sale_id"] for i in corr_sales)


def test_export_respects_filters(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    sale = _sell(client, headers, product, key="export-keep", payment="MOBILE_MONEY")
    other = client.post(
        "/products",
        headers=headers,
        json={
            "sku": "JRN-OTHER",
            "name": "Other Journal Med",
            "selling_price": "0.20",
            "cost_price": "0.05",
            "initial_quantity": 3,
            "batch_number": "OTH-1",
            "expiry_date": "2028-01-01",
            "reorder_threshold": 0,
        },
    ).json()
    _sell(client, headers, other, key="export-skip", payment="CARD")

    res = client.get(
        f"/sales/export.csv?payment_method=MOBILE_MONEY&q={sale['sale_number']}",
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert "text/csv" in res.headers.get("content-type", "")
    text = res.text
    assert "sale_number" in text.splitlines()[0]
    assert sale["sale_number"] in text
    assert "export-skip" not in text
    assert product["sku"] in text
    assert "batch" in text.splitlines()[0]


def test_pos_lookup_still_works(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    sale = _sell(client, headers, product, key="pos-lookup")
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    listed = client.get(f"/sales?q={sale['sale_number']}", headers=cashier)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["sale_number"] == sale["sale_number"]
    detail = client.get(f"/sales/{sale['id']}", headers=cashier)
    assert detail.status_code == 200
    assert detail.json()["items"][0]["batch_number"]


def test_sale_item_exposes_batch_cost_not_as_kpi_redefinition(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    sale = _sell(client, headers, product, key="cost-detail")
    detail = client.get(f"/sales/{sale['id']}", headers=headers).json()
    item = detail["items"][0]
    assert item["batch_cost_price"] is not None
    assert item["product_sku"] == product["sku"]
    # Summary KPI path unchanged
    report = client.get("/reports/sales?range=daily", headers=headers)
    assert report.status_code == 200
    assert "gross_profit" in report.json()
