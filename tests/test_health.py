from app.db.migrate import apply_migrations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_reports_configuration_state(client):
    resp = client.get("/ready")
    body = resp.json()
    assert resp.status_code == 200
    assert body["llm"] == "NOT_CONFIGURED"
    assert body["telegram_publish"] == "NOT_CONFIGURED"
    assert body["brand_status"] == "UNDECIDED"


def test_migrations_idempotent(db):
    assert apply_migrations(db) == []  # already applied in fixture, re-run is a no-op
