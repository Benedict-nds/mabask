from tests.conftest import auth_headers


def test_admin_lists_users(client):
    headers = auth_headers(client)
    res = client.get("/users", headers=headers)
    assert res.status_code == 200
    emails = {u["email"] for u in res.json()}
    assert "amara@brightcare.pharmacy" in emails


def test_pharmacist_cannot_list_users(client):
    headers = auth_headers(client, "grace@brightcare.pharmacy")
    assert client.get("/users", headers=headers).status_code == 403


def test_admin_creates_and_gets_user(client):
    headers = auth_headers(client)
    created = client.post(
        "/users",
        headers=headers,
        json={"email": "new.cashier@brightcare.pharmacy", "password": "pharmacy123", "full_name": "New Cashier", "role": "cashier"},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    got = client.get(f"/users/{user_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["email"] == "new.cashier@brightcare.pharmacy"
    roles = client.get("/users/roles", headers=headers)
    assert roles.status_code == 200
    assert {r["name"] for r in roles.json()} == {"admin", "pharmacist", "cashier"}


def test_cannot_change_own_role(client):
    headers = auth_headers(client)
    me = client.get("/auth/me", headers=headers).json()
    res = client.patch(f"/users/{me['id']}", headers=headers, json={"role": "cashier"})
    assert res.status_code == 422


def test_cannot_demote_last_admin(client):
    headers = auth_headers(client)
    users = client.get("/users", headers=headers).json()
    admin = next(u for u in users if u["role"] == "admin")
    other = next(u for u in users if u["role"] != "admin")
    res = client.patch(f"/users/{admin['id']}", headers=headers, json={"role": "pharmacist"})
    assert res.status_code == 422
    assert client.patch(f"/users/{other['id']}", headers=headers, json={"role": "pharmacist"}).status_code == 200
