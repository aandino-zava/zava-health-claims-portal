"""Runs only against an explicitly supplied disposable PostgreSQL database."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.bootstrap import configure_runtime_role
from app.config import Settings
from app.database import database
from app.main import create_app
from tests.test_api import payload


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable PostgreSQL not supplied")
def test_postgres_migration_persistence_and_aggregation(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_POSTGRES_URL"])
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AUTH_MODE", "development")
    command.upgrade(Config("alembic.ini"), "head")
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/claims", json=payload(), headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 201, response.text
        claim_id = response.json()["id"]
        assert client.get(f"/api/v1/claims/{claim_id}").status_code == 200
        assert client.get("/api/v1/analytics").json()["total"] >= 1
        assert client.get("/api/v1/claims?q=SYN-TEST").json()["total"] >= 1


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable PostgreSQL not supplied")
def test_restricted_runtime_role(monkeypatch):
    admin_url = os.environ["TEST_POSTGRES_URL"]
    monkeypatch.setenv("DATABASE_URL", admin_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AUTH_MODE", "development")
    command.upgrade(Config("alembic.ini"), "head")
    runtime_url = make_url(admin_url).set(username="claims_runtime_test", password="ci-runtime-'@:$")
    engine, _ = database(admin_url)
    with engine.connect() as connection:
        configure_runtime_role(connection, runtime_url)
        # Re-running is idempotent, including password/grant configuration.
        configure_runtime_role(connection, runtime_url)
    restricted, _ = database(runtime_url.render_as_string(hide_password=False))
    try:
        with TestClient(create_app(Settings(database_url=runtime_url.render_as_string(hide_password=False)))) as client:
            created = client.post("/api/v1/claims", json=payload(), headers={"Idempotency-Key": str(uuid4())})
            assert created.status_code == 201
            claim = created.json()
            updated = client.patch(f"/api/v1/claims/{claim['id']}/status", json={
                "status": "Under Review", "expected_version": claim["version"], "note": "Synthetic review"})
            assert updated.status_code == 200
            assert client.get("/health/ready").status_code == 200
        for statement in ("DELETE FROM claims WHERE false", "CREATE TABLE forbidden_table (id int)",
                          "DROP TABLE claims", "SELECT * FROM alembic_version", "CREATE ROLE forbidden_role"):
            with restricted.connect() as connection:
                with pytest.raises(DBAPIError):
                    connection.execute(text(statement))
                connection.rollback()
    finally:
        restricted.dispose()
        engine.dispose()
