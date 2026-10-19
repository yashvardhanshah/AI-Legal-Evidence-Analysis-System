import os
if os.environ.get("RUN_DB_TESTS") != "1":
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1:1/unused")

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.main import app

client = TestClient(app)


def test_liveness():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_fails_closed(monkeypatch):
    def failed_engine():
        raise OperationalError("", {}, Exception("private-password"))
    monkeypatch.setattr("app.main.get_engine", failed_engine)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "private-password" not in response.text
    assert response.json()["database"] == "unavailable"


def test_cors():
    response = client.options("/api/v1/health/live", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    response = client.options("/api/v1/health/live", headers={
        "Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in response.headers


def test_private_case_endpoints_require_authentication():
    assert client.get("/api/v1/cases").status_code == 401


def test_real_database_when_enabled():
    import pytest
    if os.environ.get("RUN_DB_TESTS") != "1":
        pytest.skip("Set RUN_DB_TESTS=1 with a migrated PostgreSQL database")
    assert client.get("/api/v1/health/ready").status_code == 200
    from app.database import get_engine
    from sqlalchemy import text
    with get_engine().begin() as connection:
        connection.execute(text("INSERT INTO system_metadata (key, value) VALUES ('integration_probe', 'persisted')"))
    try:
        with get_engine().connect() as connection:
            assert connection.execute(text("SELECT value FROM system_metadata WHERE key='integration_probe'")).scalar_one() == "persisted"
    finally:
        with get_engine().begin() as connection:
            connection.execute(text("DELETE FROM system_metadata WHERE key='integration_probe'"))
