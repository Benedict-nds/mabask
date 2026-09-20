from tests.conftest import auth_headers


def test_login_success(client):
    res = client.post("/auth/login", json={"email": "amara@brightcare.pharmacy", "password": "pharmacy123"})
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["role"] == "admin"
    assert "users.create" in body["user"]["permissions"]
    assert body["tokens"]["access_token"]


def test_login_invalid(client):
    res = client.post("/auth/login", json={"email": "amara@brightcare.pharmacy", "password": "wrong"})
    assert res.status_code == 401


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401


def test_me_ok(client):
    res = client.get("/auth/me", headers=auth_headers(client))
    assert res.status_code == 200
    assert res.json()["email"] == "amara@brightcare.pharmacy"


def test_cashier_cannot_create_user(client):
    headers = auth_headers(client, "lena@brightcare.pharmacy")
    res = client.post(
        "/users",
        headers=headers,
        json={"email": "x@y.com", "password": "password1", "full_name": "X", "role": "cashier"},
    )
    assert res.status_code == 403


def test_cashier_cannot_manage_settings_or_purchase(client):
    headers = auth_headers(client, "lena@brightcare.pharmacy")
    assert client.get("/settings", headers=headers).status_code == 200
    assert client.get("/users", headers=headers).status_code == 403
    assert client.get("/purchase-orders", headers=headers).status_code == 403
    assert client.patch("/settings", headers=headers, json={"tax_rate": "9"}).status_code == 403


def test_pharmacist_can_operate_inventory_but_not_users(client):
    headers = auth_headers(client, "grace@brightcare.pharmacy")
    assert client.get("/products", headers=headers).status_code == 200
    assert client.get("/purchase-orders", headers=headers).status_code == 200
    assert client.get("/users", headers=headers).status_code == 403
    assert client.get("/settings", headers=headers).status_code == 200
    assert client.patch("/settings", headers=headers, json={"tax_rate": "9"}).status_code == 403
