from app.core.backup import restore_sqlite, rotating_backup, verify_sqlite
from app.core.paths import sqlite_url
from tests.conftest import auth_headers


def test_health_reports_local_ai_mode(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["ai"]["enabled"] is False
    assert body["ai"]["mode"] == "local-data"


def test_sqlite_backup_restore_roundtrip(tmp_path):
    live = tmp_path / "live.db"
    import sqlite3

    conn = sqlite3.connect(live)
    conn.execute("create table medicines (name text)")
    conn.execute("insert into medicines values ('Paracetamol')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    dest = rotating_backup(live, backup_dir, keep=2)
    assert dest.is_file()
    assert verify_sqlite(dest) == "ok"

    conn = sqlite3.connect(live)
    conn.execute("insert into medicines values ('Ibuprofen')")
    conn.commit()
    conn.close()

    restored = tmp_path / "restored.db"
    restore_sqlite(dest, restored)
    conn = sqlite3.connect(restored)
    rows = [r[0] for r in conn.execute("select name from medicines").fetchall()]
    conn.close()
    assert rows == ["Paracetamol"]


def test_sqlite_url_uses_absolute_path(tmp_path):
    url = sqlite_url(tmp_path / "data" / "aetherqore.db")
    assert url.startswith("sqlite:///")
    assert "aetherqore.db" in url


def test_copilot_answers_from_local_data_without_ai_key(client):
    headers = auth_headers(client)
    status = client.get("/copilot/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["ai_enabled"] is False

    asked = client.post("/copilot/ask", headers=headers, json={"question": "How much revenue did we make today?"})
    assert asked.status_code == 200, asked.text
    body = asked.json()
    assert body["llm_used"] is False
    assert "GH₵" in body["text"] or "revenue" in body["text"].lower()
    assert body["source"] in {"sales", "general", "inventory", "suppliers"}


def test_production_rejects_weak_secret(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me")
    get_settings.cache_clear()
    try:
        try:
            get_settings()
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass
    finally:
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-jwt-tokens")
        get_settings.cache_clear()
