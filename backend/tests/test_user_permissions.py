import json

from app.core.permissions import ADMIN_ONLY_PERMISSIONS, ALL_PERMISSIONS, ROLE_PERMISSIONS
from app.models import AuditLog, User, UserPermissionOverride
from tests.conftest import auth_headers

ADMIN = "amara@brightcare.pharmacy"
CASHIER = "lena@brightcare.pharmacy"
PHARMACIST = "grace@brightcare.pharmacy"


def _user_id(db, email):
    return db.query(User).filter(User.email == email).one().id


def _me(client, email):
    return client.get("/auth/me", headers=auth_headers(client, email)).json()


def _set(client, user_id, overrides, email=ADMIN):
    return client.put(f"/users/{user_id}/permissions", headers=auth_headers(client, email), json={"overrides": overrides})


def _submitted_po(client):
    headers = auth_headers(client)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    created = client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": product["supplier_id"],
            "items": [{"product_id": product["id"], "product_name": product["name"], "quantity_ordered": 5, "unit_cost": "0.18"}],
        },
    )
    assert created.status_code == 201, created.text
    po_id = created.json()["id"]
    assert client.post(f"/purchase-orders/{po_id}/submit", headers=headers).status_code == 200
    return po_id


def _audit(db, action):
    return [(row, json.loads(row.details)) for row in db.query(AuditLog).filter(AuditLog.action == action).all()]


def _second_admin(client):
    res = client.post(
        "/users",
        headers=auth_headers(client),
        json={"email": "owner2@brightcare.pharmacy", "password": "pharmacy123", "full_name": "Second Admin", "role": "admin"},
    )
    assert res.status_code == 201, res.text
    return res.json()


# --- Role baselines --------------------------------------------------------------------------


def test_role_baselines_unchanged_without_overrides(client):
    assert set(_me(client, ADMIN)["permissions"]) == {code for code, _ in ALL_PERMISSIONS}
    assert set(_me(client, PHARMACIST)["permissions"]) == set(ROLE_PERMISSIONS["pharmacist"])
    assert set(_me(client, CASHIER)["permissions"]) == set(ROLE_PERMISSIONS["cashier"])
    assert _me(client, PHARMACIST)["permission_overrides"] == {}


def test_pharmacist_is_not_admin_equivalent(client):
    pharmacist = set(_me(client, PHARMACIST)["permissions"])
    assert not pharmacist & ADMIN_ONLY_PERMISSIONS


def test_permission_catalog_groups_existing_codes(client):
    res = client.get("/users/permission-catalog", headers=auth_headers(client))
    assert res.status_code == 200
    catalog = res.json()
    assert {e["code"] for e in catalog} == {code for code, _ in ALL_PERMISSIONS}
    by_code = {e["code"]: e for e in catalog}
    assert by_code["purchases.receive"]["group"] == "receiving"
    assert by_code["sales.correction_approve"]["group"] == "corrections"
    assert by_code["users.update"]["admin_only"] is True
    assert by_code["purchases.approve"]["admin_only"] is False


def test_detail_reports_baseline_override_and_effective(client, db):
    grace = _user_id(db, PHARMACIST)
    detail = client.get(f"/users/{grace}/permissions", headers=auth_headers(client)).json()
    assert detail["editable"] is True and detail["override_count"] == 0
    approve = next(p for p in detail["permissions"] if p["code"] == "purchases.approve")
    assert approve == {**approve, "role_default": True, "override": "INHERIT", "effective": True, "locked": False}
    users_update = next(p for p in detail["permissions"] if p["code"] == "users.update")
    assert users_update["locked"] is True and users_update["effective"] is False


# --- Deny overrides are enforced by the backend ------------------------------------------------


def test_deny_purchase_approval_blocks_api(client, db):
    grace = _user_id(db, PHARMACIST)
    po_id = _submitted_po(client)
    res = _set(client, grace, {"purchases.approve": "DENY"})
    assert res.status_code == 200, res.text
    assert res.json()["override_count"] == 1

    assert "purchases.approve" not in _me(client, PHARMACIST)["permissions"]
    blocked = client.post(f"/purchase-orders/{po_id}/approve", headers=auth_headers(client, PHARMACIST))
    assert blocked.status_code == 403
    assert client.get(f"/purchase-orders/{po_id}", headers=auth_headers(client, PHARMACIST)).json()["status"] == "SUBMITTED"


def test_deny_reports_blocks_reports_and_dashboard(client, db):
    grace = _user_id(db, PHARMACIST)
    headers = auth_headers(client, PHARMACIST)
    assert client.get("/reports/sales", headers=headers).status_code == 200
    assert _set(client, grace, {"reports.read": "DENY"}).status_code == 200
    assert client.get("/reports/sales", headers=headers).status_code == 403
    assert client.get("/dashboard", headers=headers).status_code == 403


def test_deny_inventory_update_blocks_product_edit(client, db):
    grace = _user_id(db, PHARMACIST)
    headers = auth_headers(client, PHARMACIST)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    assert _set(client, grace, {"inventory.update": "DENY"}).status_code == 200
    assert client.patch(f"/products/{product['id']}", headers=headers, json={"name": "Renamed"}).status_code == 403
    assert client.get("/products", headers=headers).status_code == 200


def test_deny_refund_blocks_cashier_returns(client, db):
    lena = _user_id(db, CASHIER)
    headers = auth_headers(client, CASHIER)
    assert client.post("/returns", headers=headers, json={}).status_code == 422
    assert _set(client, lena, {"sales.refund": "DENY"}).status_code == 200
    assert client.post("/returns", headers=headers, json={}).status_code == 403


# --- Allow overrides ----------------------------------------------------------------------------


def test_allow_grants_capability_outside_role(client, db):
    grace = _user_id(db, PHARMACIST)
    headers = auth_headers(client, PHARMACIST)
    product = client.get("/products?q=Amoxicillin", headers=headers).json()["items"][0]
    assert client.post(f"/products/{product['id']}/archive", headers=headers, json={"reason": "test"}).status_code == 403
    assert _set(client, grace, {"inventory.archive": "ALLOW"}).status_code == 200
    assert "inventory.archive" in _me(client, PHARMACIST)["permissions"]
    assert client.post(f"/products/{product['id']}/archive", headers=headers, json={"reason": "test"}).status_code == 200


def test_allow_applies_only_to_that_user(client, db):
    created = client.post(
        "/users",
        headers=auth_headers(client),
        json={"email": "p2@brightcare.pharmacy", "password": "pharmacy123", "full_name": "Second Pharmacist", "role": "pharmacist"},
    )
    assert created.status_code == 201
    assert _set(client, _user_id(db, PHARMACIST), {"inventory.archive": "ALLOW"}).status_code == 200
    assert "inventory.archive" in _me(client, PHARMACIST)["permissions"]
    assert "inventory.archive" not in _me(client, "p2@brightcare.pharmacy")["permissions"]


def test_cashier_allowed_receiving(client, db):
    lena = _user_id(db, CASHIER)
    headers = auth_headers(client, CASHIER)
    assert client.post("/receiving/adhoc", headers=headers, json={}).status_code == 403
    assert _set(client, lena, {"purchases.receive": "ALLOW"}).status_code == 200
    assert client.post("/receiving/adhoc", headers=headers, json={}).status_code == 422


# --- Inherit and reset --------------------------------------------------------------------------


def test_inherit_restores_role_behaviour(client, db):
    grace = _user_id(db, PHARMACIST)
    _set(client, grace, {"reports.read": "DENY"})
    assert client.get("/reports/sales", headers=auth_headers(client, PHARMACIST)).status_code == 403
    res = _set(client, grace, {"reports.read": "INHERIT"})
    assert res.status_code == 200 and res.json()["override_count"] == 0
    assert client.get("/reports/sales", headers=auth_headers(client, PHARMACIST)).status_code == 200
    assert db.query(UserPermissionOverride).count() == 0


def test_reset_to_role_defaults_clears_all_overrides(client, db):
    grace = _user_id(db, PHARMACIST)
    _set(client, grace, {"reports.read": "DENY", "purchases.approve": "DENY", "inventory.archive": "ALLOW"})
    assert _me(client, PHARMACIST)["permission_overrides"] == {
        "reports.read": "DENY",
        "purchases.approve": "DENY",
        "inventory.archive": "ALLOW",
    }
    res = client.post(f"/users/{grace}/permissions/reset", headers=auth_headers(client))
    assert res.status_code == 200
    assert res.json()["override_count"] == 0
    assert set(_me(client, PHARMACIST)["permissions"]) == set(ROLE_PERMISSIONS["pharmacist"])
    reset_rows = [d for _, d in _audit(db, "PERMISSION_OVERRIDE_CHANGED") if d["reason"] == "reset_to_role_defaults"]
    assert {(d["permission"], d["previous"], d["new"]) for d in reset_rows} == {
        ("reports.read", "DENY", "INHERIT"),
        ("purchases.approve", "DENY", "INHERIT"),
        ("inventory.archive", "ALLOW", "INHERIT"),
    }


def test_batch_is_atomic_when_one_entry_is_invalid(client, db):
    grace = _user_id(db, PHARMACIST)
    res = _set(client, grace, {"reports.read": "DENY", "users.update": "ALLOW"})
    assert res.status_code == 422
    assert db.query(UserPermissionOverride).count() == 0
    assert "reports.read" in _me(client, PHARMACIST)["permissions"]


def test_unknown_permission_and_state_rejected(client, db):
    grace = _user_id(db, PHARMACIST)
    assert _set(client, grace, {"made.up": "DENY"}).status_code == 422
    assert _set(client, grace, {"reports.read": "MAYBE"}).status_code == 422
    assert client.put(f"/users/{grace}/permissions", headers=auth_headers(client), json={"overrides": {}}).status_code == 422


# --- Security --------------------------------------------------------------------------------------


def test_pharmacist_and_cashier_cannot_manage_overrides(client, db):
    lena = _user_id(db, CASHIER)
    grace = _user_id(db, PHARMACIST)
    assert _set(client, lena, {"reports.read": "ALLOW"}, email=PHARMACIST).status_code == 403
    assert _set(client, grace, {"purchases.approve": "ALLOW"}, email=PHARMACIST).status_code == 403
    assert _set(client, grace, {"reports.read": "ALLOW"}, email=CASHIER).status_code == 403
    assert client.post(f"/users/{lena}/permissions/reset", headers=auth_headers(client, PHARMACIST)).status_code == 403
    assert client.get(f"/users/{lena}/permissions", headers=auth_headers(client, CASHIER)).status_code == 403


def test_admin_only_permissions_cannot_be_granted_to_non_admins(client, db):
    grace = _user_id(db, PHARMACIST)
    for code in sorted(ADMIN_ONLY_PERMISSIONS):
        res = _set(client, grace, {code: "ALLOW"})
        assert res.status_code == 422, code
        assert "admin-only" in res.json()["error"]["message"]
    assert client.get("/users", headers=auth_headers(client, PHARMACIST)).status_code == 403


def test_stale_admin_only_rows_are_ignored_by_resolver(client, db):
    grace = _user_id(db, PHARMACIST)
    db.add(UserPermissionOverride(user_id=grace, permission_code="users.update", effect="ALLOW"))
    db.add(UserPermissionOverride(user_id=grace, permission_code="settings.manage", effect="ALLOW"))
    amara = _user_id(db, ADMIN)
    db.add(UserPermissionOverride(user_id=amara, permission_code="users.update", effect="DENY"))
    db.commit()
    assert not set(_me(client, PHARMACIST)["permissions"]) & ADMIN_ONLY_PERMISSIONS
    assert client.patch("/settings", headers=auth_headers(client, PHARMACIST), json={"tax_rate": "9"}).status_code == 403
    assert "users.update" in _me(client, ADMIN)["permissions"]


def test_admin_cannot_change_own_permissions(client, db):
    amara = _user_id(db, ADMIN)
    for code in ("users.update", "settings.manage", "reports.read"):
        res = _set(client, amara, {code: "DENY"})
        assert res.status_code == 422
    assert client.post(f"/users/{amara}/permissions/reset", headers=auth_headers(client)).status_code == 422
    detail = client.get(f"/users/{amara}/permissions", headers=auth_headers(client)).json()
    assert detail["editable"] is False and "own permissions" in detail["not_editable_reason"]
    assert set(_me(client, ADMIN)["permissions"]) == {code for code, _ in ALL_PERMISSIONS}


def test_multiple_admins(client, db):
    second = _second_admin(client)
    assert _set(client, second["id"], {"users.update": "DENY"}).status_code == 422
    assert _set(client, second["id"], {"settings.manage": "DENY"}).status_code == 422
    assert _set(client, second["id"], {"sales.refund": "DENY"}).status_code == 200
    me = _me(client, "owner2@brightcare.pharmacy")
    assert "sales.refund" not in me["permissions"]
    assert ADMIN_ONLY_PERMISSIONS <= set(me["permissions"])
    # The second admin cannot undo their own restriction but still manages everyone else.
    assert _set(client, second["id"], {"sales.refund": "INHERIT"}, email="owner2@brightcare.pharmacy").status_code == 422
    assert _set(client, _user_id(db, PHARMACIST), {"reports.read": "DENY"}, email="owner2@brightcare.pharmacy").status_code == 200


# --- Role changes, creation and audit -----------------------------------------------------------


def test_role_change_audited_and_overrides_preserved(client, db):
    lena = _user_id(db, CASHIER)
    _set(client, lena, {"sales.refund": "DENY"})
    res = client.patch(f"/users/{lena}", headers=auth_headers(client), json={"role": "pharmacist"})
    assert res.status_code == 200
    assert res.json()["permission_overrides"] == {"sales.refund": "DENY"}
    assert "sales.refund" not in res.json()["permissions"]
    assert "purchases.approve" in res.json()["permissions"]
    rows = _audit(db, "ROLE_CHANGED")
    assert len(rows) == 1
    row, details = rows[0]
    assert row.user_id == _user_id(db, ADMIN) and row.entity_id == lena
    assert (details["previous"], details["new"]) == ("cashier", "pharmacist")


def test_role_change_response_is_fresh_with_production_session_settings(client, db):
    db.expire_on_commit = False
    lena = _user_id(db, CASHIER)
    auth_headers(client, CASHIER)
    res = client.patch(f"/users/{lena}", headers=auth_headers(client), json={"role": "pharmacist"})
    assert res.status_code == 200
    assert res.json()["role"] == "pharmacist"
    assert "purchases.approve" in res.json()["permissions"]


def test_same_role_patch_is_not_a_role_change(client, db):
    lena = _user_id(db, CASHIER)
    assert client.patch(f"/users/{lena}", headers=auth_headers(client), json={"role": "cashier", "full_name": "Lena R"}).status_code == 200
    assert _audit(db, "ROLE_CHANGED") == []


def test_override_change_audit_contents(client, db):
    grace = _user_id(db, PHARMACIST)
    _set(client, grace, {"purchases.approve": "DENY"})
    _set(client, grace, {"purchases.approve": "ALLOW"})
    _set(client, grace, {"purchases.approve": "ALLOW"})
    rows = _audit(db, "PERMISSION_OVERRIDE_CHANGED")
    assert [(d["previous"], d["new"]) for _, d in rows] == [("INHERIT", "DENY"), ("DENY", "ALLOW")]
    row, details = rows[0]
    assert row.user_id == _user_id(db, ADMIN)
    assert row.entity_type == "user" and row.entity_id == grace
    assert row.created_at is not None
    assert details["permission"] == "purchases.approve"
    assert details["target_user"] == PHARMACIST
    assert not any(k in json.dumps(details).lower() for k in ("password", "token", "hash", "secret"))


def test_create_user_defaults_to_inherit_and_accepts_overrides(client, db):
    headers = auth_headers(client)
    plain = client.post(
        "/users",
        headers=headers,
        json={"email": "c1@brightcare.pharmacy", "password": "pharmacy123", "full_name": "Plain Cashier", "role": "cashier"},
    )
    assert plain.status_code == 201
    assert plain.json()["permission_overrides"] == {}
    assert set(plain.json()["permissions"]) == set(ROLE_PERMISSIONS["cashier"])

    custom = client.post(
        "/users",
        headers=headers,
        json={
            "email": "c2@brightcare.pharmacy",
            "password": "pharmacy123",
            "full_name": "Custom Cashier",
            "role": "cashier",
            "permission_overrides": {"sales.refund": "DENY", "purchases.receive": "ALLOW", "reports.read": "INHERIT"},
        },
    )
    assert custom.status_code == 201, custom.text
    body = custom.json()
    assert body["permission_overrides"] == {"sales.refund": "DENY", "purchases.receive": "ALLOW"}
    assert "sales.refund" not in body["permissions"] and "purchases.receive" in body["permissions"]
    assert {d["reason"] for _, d in _audit(db, "PERMISSION_OVERRIDE_CHANGED")} == {"set_at_creation"}

    escalate = client.post(
        "/users",
        headers=headers,
        json={
            "email": "c3@brightcare.pharmacy",
            "password": "pharmacy123",
            "full_name": "Sneaky",
            "role": "cashier",
            "permission_overrides": {"users.create": "ALLOW"},
        },
    )
    assert escalate.status_code == 422
    assert db.query(User).filter(User.email == "c3@brightcare.pharmacy").first() is None


def test_deleted_user_overrides_cascade(client, db):
    lena = _user_id(db, CASHIER)
    _set(client, lena, {"sales.refund": "DENY"})
    user = db.get(User, lena)
    db.delete(user)
    db.commit()
    assert db.query(UserPermissionOverride).count() == 0
