import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import date, timedelta

import pytest
from jsonschema import Draft4Validator
from openapi_spec_validator import validate
from pydantic import ValidationError

from app.schemas import ClaimCreate, StoredClaimData
from scripts.export_copilot import ROOT, TEMPLATE, api_schema, convert_schema, export
from tests.test_api import payload, setup  # noqa: F401

HOST = "claims-api.example.com"
TENANT = "11111111-1111-4111-8111-111111111111"
API = "22222222-2222-4222-8222-222222222222"


def swagger():
    return export(HOST, TENANT, API)


def test_swagger_valid_and_checked_in_template_matches():
    document = swagger()
    validate(document)
    assert json.loads(TEMPLATE.read_text()) == document
    assert document["swagger"] == "2.0"
    assert document["security"][0]["entraOAuth"] == [f"api://{API}/Claims.Access", "offline_access"]
    assert document["securityDefinitions"]["entraOAuth"]["flow"] == "accessCode"


def test_exported_operations_and_parameters_match_live_contract():
    native, document = api_schema(), swagger()
    exported_ids = set()
    for path, methods in native["paths"].items():
        for method, operation in methods.items():
            exported = document["paths"][path.removeprefix("/api/v1")][method]
            assert exported["operationId"] == operation["operationId"]
            exported_ids.add(exported["operationId"])
            native_parameters = {(p["in"], p["name"], p.get("required", False))
                                 for p in operation.get("parameters", [])}
            parameters = {(p["in"], p["name"], p["required"]) for p in exported["parameters"]
                          if p["in"] != "body"}
            assert native_parameters == parameters
            assert all(p.get("description") for p in exported["parameters"])
            for parameter in operation.get("parameters", []):
                actual = next(p for p in exported["parameters"] if p["name"] == parameter["name"])
                for key in ("type", "enum", "minimum", "maximum", "minLength", "maxLength", "default"):
                    expected = convert_schema(parameter["schema"])
                    if key in expected:
                        assert actual[key] == expected[key]
            if "requestBody" in operation:
                body = next(p for p in exported["parameters"] if p["in"] == "body")
                expected = operation["requestBody"]["content"]["application/json"]["schema"]
                assert body["schema"] == convert_schema(expected)
    assert len(exported_ids) == 7
    detail = document["definitions"]["ClaimDetail"]["properties"]["data"]
    assert detail["$ref"] == "#/definitions/StoredClaimData"
    assert set(document["definitions"]["StoredClaimData"]["properties"]) == set(ClaimCreate.model_fields)


def test_read_model_is_explicit_but_independent_of_submission_rules():
    original = ClaimCreate(**payload()).model_dump(mode="json")
    assert StoredClaimData(**original).model_dump() == original
    historical = dict(original, diagnosis_code="older-code-format", email="legacy-value",
                      service_date=(date.today() + timedelta(days=30)).isoformat(),
                      future_field={"preserved": True})
    assert StoredClaimData(**historical).model_dump() == historical
    with pytest.raises(ValidationError):
        ClaimCreate(**historical)


def nullable_json_schema(value):
    """Honor Swagger's nullable extension when validating instances with JSON Schema."""
    if isinstance(value, list):
        return [nullable_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: nullable_json_schema(item) for key, item in value.items() if key != "x-nullable"}
    return {"anyOf": [result, {"type": "null"}]} if value.get("x-nullable") else result


def test_real_api_responses_match_swagger_models(setup):  # noqa: F811
    client, _, _ = setup
    document = swagger()

    def conforms(path, method, response):
        assert response.is_success
        schema = document["paths"][path][method]["responses"][str(response.status_code)]["schema"]
        contract = nullable_json_schema({**deepcopy(schema), "definitions": document["definitions"]})
        Draft4Validator(contract).validate(response.json())

    created = client.post("/api/v1/claims", json=payload(), headers={"Idempotency-Key": "connector-replay"})
    conforms("/claims", "post", created)
    claim = created.json()
    replay = client.post("/api/v1/claims", json=payload(), headers={"Idempotency-Key": "connector-replay"})
    assert replay.status_code == 200
    conforms("/claims", "post", replay)
    conforms("/claims", "get", client.get("/api/v1/claims"))
    conforms("/claims/{claim_id}", "get", client.get(f"/api/v1/claims/{claim['id']}"))
    updated = client.patch(f"/api/v1/claims/{claim['id']}/status", json={
        "status": "Under Review", "expected_version": claim["version"], "note": "Synthetic connector test"})
    conforms("/claims/{claim_id}/status", "patch", updated)
    conforms("/analytics", "get", client.get("/api/v1/analytics"))
    conforms("/transitions", "get", client.get("/api/v1/transitions"))
    conforms("/me", "get", client.get("/api/v1/me"))


@pytest.mark.parametrize("host", ["https://api.example.com", "api.example.com/path", "user:pass@api.example.com"])
def test_reject_host_with_scheme_path_or_credentials(host):
    with pytest.raises(ValueError):
        export(host, TENANT, API)


def test_fail_on_unsupported_schema_instead_of_silently_losing_fields():
    with pytest.raises(ValueError):
        convert_schema({"oneOf": [{"type": "string"}, {"type": "integer"}]})


def test_custom_export_does_not_overwrite_public_template(tmp_path):
    before = TEMPLATE.read_bytes()
    destination = tmp_path / "connector.json"
    result = subprocess.run([
        sys.executable, "-m", "scripts.export_copilot", "--host", "custom-api.example.com",
        "--tenant-id", TENANT, "--api-client-id", API, "--output", str(destination),
    ], cwd=ROOT, env=dict(os.environ), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert TEMPLATE.read_bytes() == before
    assert json.loads(destination.read_text())["host"] == "custom-api.example.com"
    destination.write_text("{}")
    stale = subprocess.run([
        sys.executable, "-m", "scripts.export_copilot", "--host", "custom-api.example.com",
        "--tenant-id", TENANT, "--api-client-id", API, "--output", str(destination), "--check",
    ], cwd=ROOT, capture_output=True, text=True)
    assert stale.returncode != 0
    assert "stale" in stale.stderr
