from tests.conftest import auth_headers


def test_dashboard_requires_reports_permission(client):
    cashier = auth_headers(client, "lena@brightcare.pharmacy")
    assert client.get("/dashboard", headers=cashier).status_code == 403


def test_dashboard_from_database(client):
    headers = auth_headers(client)
    res = client.get("/dashboard", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert "today_revenue" in body
    assert "low_stock_count" in body
    assert body["low_stock_count"] >= 1
