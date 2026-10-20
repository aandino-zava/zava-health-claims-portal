import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import start
from app.config import Settings
from app.main import create_app
from app.services import utc_iso
from app.telemetry import logger
from tests.test_api import setup  # noqa: F401


def test_configuration_names_missing_field(monkeypatch):
    for key in ("ENTRA_TENANT_ID", "ENTRA_API_CLIENT_ID", "ENTRA_SPA_CLIENT_ID"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError, match="requires a valid ENTRA_TENANT_ID"):
        Settings(environment="test", auth_mode="entra", _env_file=None)


def test_missing_schema_readiness_is_safe_503():
    app = create_app(Settings(environment="test", auth_mode="development", database_url="sqlite://"))
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database temporarily unavailable"}
        assert len(response.headers["X-Request-ID"]) == 32


def test_request_limit_and_security_headers():
    app = create_app(Settings(environment="test", auth_mode="development",
                              database_url="sqlite://", requests_per_minute=2))
    with TestClient(app) as client:
        assert client.get("/api/v1/me").status_code == 200
        assert client.get("/api/v1/me").status_code == 200
        response = client.get("/api/v1/me")
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        # Health probes remain available after API throttling.
        assert client.get("/health/live").status_code == 200


def test_streamed_body_limit():
    app = create_app(Settings(environment="test", auth_mode="development", database_url="sqlite://",
                              max_request_bytes=1024))
    with TestClient(app) as client:
        response = client.post("/api/v1/claims", content=iter([b"x" * 600, b"y" * 600]))
        assert response.status_code == 413
        assert "x" * 30 not in response.text


def test_logs_redact_queries_and_caller_values(caplog):
    app = create_app(Settings(environment="test", auth_mode="development", database_url="sqlite://"))
    logger.addHandler(caplog.handler)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/me?email=PRIVATE_SENTINEL", headers={
                "Authorization": "Bearer TOKEN_SENTINEL", "X-Request-ID": "UNTRUSTED_SENTINEL"})
        records = [json.loads(record.message) for record in caplog.records if record.name == logger.name]
        request = next(record for record in records if record["event"] == "request_completed")
        assert request["request_id"] == response.headers["X-Request-ID"]
        assert request["route"] == "/api/v1/me"
        serialized = json.dumps(records)
        assert all(value not in serialized for value in
                   ("PRIVATE_SENTINEL", "TOKEN_SENTINEL", "UNTRUSTED_SENTINEL"))
    finally:
        logger.removeHandler(caplog.handler)


def test_stored_payload_is_not_resubmitted_to_new_validation(setup):  # noqa: F811
    from app.database import Claim
    from tests.test_api import payload

    client, app, _ = setup
    response = client.post("/api/v1/claims", json=payload(), headers={"Idempotency-Key": "historical-claim"})
    claim_id = response.json()["id"]
    with app.state.sessions() as db:
        row = db.get(Claim, claim_id)
        row.payload = dict(row.payload, diagnosis_code="historical-format")
        db.commit()
    detail = client.get(f"/api/v1/claims/{claim_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["diagnosis_code"] == "historical-format"
    assert detail.json()["created_at"].endswith("+00:00")
    assert client.get("/static/app.js").headers["Cache-Control"] == "public, max-age=0, must-revalidate"
    assert detail.headers["Cache-Control"] == "no-store"


def test_timestamp_normalization():
    assert utc_iso(datetime(2026, 1, 1)) == "2026-01-01T00:00:00+00:00"
    assert utc_iso(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00+00:00"
    assert utc_iso(datetime.fromisoformat("2026-01-01T01:00:00+01:00")) == "2026-01-01T00:00:00+00:00"


def test_admin_credential_removed_before_server_exec(monkeypatch):
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "PRIVATE_BOOTSTRAP_SENTINEL")
    monkeypatch.setattr(start, "Settings", lambda: object())
    monkeypatch.setattr(start, "prepare_database", lambda settings: None)
    invoked = []
    monkeypatch.setattr(start.os, "execvp", lambda command, arguments: invoked.append(
        (command, "MIGRATION_DATABASE_URL" in start.os.environ)))
    start.main()
    assert invoked == [("uvicorn", False)]


def test_bootstrap_failure_does_not_print_driver_secrets(monkeypatch):
    monkeypatch.setattr(start, "Settings", lambda: object())

    def fail(settings):
        raise RuntimeError("PRIVATE_DRIVER_SENTINEL")

    monkeypatch.setattr(start, "prepare_database", fail)
    with pytest.raises(SystemExit) as error:
        start.main()
    assert "PRIVATE_DRIVER_SENTINEL" not in str(error.value)



@pytest.mark.parametrize("migration_url", [
    "postgresql+psycopg://claims_app:other@db/claims",
    "postgresql+psycopg://admin:other@other-host/claims",
])
def test_production_bootstrap_requires_separate_matching_connection(monkeypatch, migration_url):
    from types import SimpleNamespace

    monkeypatch.setenv("MIGRATION_DATABASE_URL", migration_url)
    settings = SimpleNamespace(environment="production", database_url="postgresql+psycopg://claims_app:test@db/claims")
    with pytest.raises(ValueError, match="separate runtime and migration"):
        start.prepare_database(settings)
