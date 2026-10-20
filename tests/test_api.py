from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.auth import Principal, current_user
from app.config import Settings
from app.main import create_app
from app.seed import seed


@pytest.fixture
def setup(monkeypatch):
    tmp_path = Path("work") / "tests" / str(uuid4())
    tmp_path.mkdir(parents=True)
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings()
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app, settings


def payload():
    return dict(
        patient_id="SYN-TEST",
        first_name="Test",
        last_name="Person",
        provider_name="Demo Clinic",
        provider_id="DEMO-1",
        diagnosis_code="Z00.00",
        procedure_code="99213",
        amount="125.25",
        service_date="2026-09-01",
        synthetic_data_confirmed=True,
    )


def submit(client, data=None, key="request-0001"):
    return client.post("/api/v1/claims", json=data or payload(), headers={"Idempotency-Key": key})


def test_create_read_persistence_and_idempotency(setup):
    client, app, settings = setup
    created = submit(client)
    assert created.status_code == 201, created.text
    claim = created.json()
    assert claim["amount"] == "125.25"
    assert claim["status"] == "Submitted"
    repeated = submit(client)
    assert repeated.status_code == 200
    assert repeated.json()["id"] == claim["id"]
    assert submit(client, {**payload(), "amount": "126.00"}).status_code == 409
    # A new app instance reads the same durable database.
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/api/v1/claims/{claim['id']}").json()["patient_id"] == "SYN-TEST"
        assert second.get("/api/v1/claims").json()["total"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", "0"),
        ("amount", "1.001"),
        ("amount", "-1"),
        ("diagnosis_code", "bad"),
        ("procedure_code", "12"),
        ("npi", "123"),
        ("synthetic_data_confirmed", False),
        ("email", "invalid"),
        ("service_date", (date.today() + timedelta(days=1)).isoformat()),
        ("status", "Approved"),
        ("date_of_birth", "2026-09-02"),
    ],
)
def test_validation(setup, field, value):
    response = submit(setup[0], {**payload(), field: value})
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])


def test_status_transitions_and_stale_writes(setup):
    client, _, _ = setup
    claim = submit(client).json()
    url = f"/api/v1/claims/{claim['id']}/status"
    assert (
        client.patch(url, json={"status": "Approved", "expected_version": 1, "note": "Reviewed"}).status_code
        == 409
    )
    changed = client.patch(
        url, json={"status": "Under Review", "expected_version": 1, "note": "Review started"}
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    assert len(changed.json()["history"]) == 2
    assert (
        client.patch(
            url, json={"status": "Denied", "expected_version": 1, "note": "Stale change"}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            url, json={"status": "Pending Info", "expected_version": 2, "note": "Need details"}
        ).status_code
        == 200
    )


def test_roles_enforced_on_each_operation(setup):
    client, app, _ = setup
    claim = submit(client).json()
    app.dependency_overrides[current_user] = lambda: Principal("reader", {"Claims.Reader"})
    assert client.get("/api/v1/claims").status_code == 200
    assert submit(client, key="another-request").status_code == 403
    assert (
        client.patch(
            f"/api/v1/claims/{claim['id']}/status",
            json={"status": "Under Review", "expected_version": 1, "note": "Review"},
        ).status_code
        == 403
    )
    app.dependency_overrides[current_user] = lambda: Principal("none", set())
    assert client.get("/api/v1/analytics").status_code == 403
    assert client.get(f"/api/v1/claims/{claim['id']}").status_code == 403


def test_seed_search_filters_paging_and_totals(setup):
    client, _, settings = setup
    seed(settings)
    seed(settings)
    assert client.get("/api/v1/claims").json()["total"] == 8
    assert client.get("/api/v1/claims?status=Approved").json()["total"] == 3
    assert client.get("/api/v1/claims?service_type=Dental").json()["total"] == 1
    assert client.get("/api/v1/claims?q=AVERY").json()["total"] == 1
    assert client.get("/api/v1/claims?q=%25").json()["total"] == 0
    assert len(client.get("/api/v1/claims?limit=3&offset=3").json()["items"]) == 3
    stats = client.get("/api/v1/analytics").json()
    assert stats["total_amount"] == 38625
    assert stats["approved_amount"] == 33725
    assert sum(stats["by_service"].values()) == 8


def test_readiness_and_api_contract(setup):
    client, _, _ = setup
    assert client.get("/health/ready").status_code == 200
    assert client.get("/").status_code == 200
    spec = client.get("/openapi.json").json()
    post = spec["paths"]["/api/v1/claims"]["post"]
    assert post["operationId"] == "createClaim"
    assert "HTTPBearer" in spec["components"]["securitySchemes"]
    assert client.get("/api/v1/claims/missing").status_code == 404
    assert client.get("/api/v1/claims?limit=101").status_code == 422


def test_production_rejects_development_identity():
    with pytest.raises(ValueError):
        Settings(environment="production", auth_mode="development")
