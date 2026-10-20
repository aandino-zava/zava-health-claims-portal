"""Deployment tooling regressions; no Azure calls or real credentials."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_repo import HEADINGS, check
from scripts.deployment_parameters import check_contract, fixture_outputs, parameters
from scripts.preflight_tenant import validate

ROOT = Path(__file__).resolve().parents[1]


def config():
    ids = [f"{i:08d}-1111-4111-8111-111111111111" for i in range(1, 6)]
    return dict(zip(
        ("AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_DEPLOY_CLIENT_ID",
         "ENTRA_API_CLIENT_ID", "ENTRA_SPA_CLIENT_ID"), ids, strict=True
    ), AZURE_RESOURCE_GROUP="claims-demo-rg", AZURE_PREFIX="claimsdemo",
        ENTRA_ALLOWED_CLIENT_IDS=ids[-1], DATABASE_ADMIN_PASSWORD="test-only-not-a-secret", DATABASE_APP_PASSWORD="test-app-only")


def runtime_config(hosting):
    c = config()
    return {
        "AZURE_HOSTING": hosting, "AZURE_PREFIX": c["AZURE_PREFIX"], "AZURE_LOCATION": "eastus",
        "DATABASE_ADMIN_PASSWORD": "SENSITIVE_TEST_SENTINEL", "DATABASE_APP_PASSWORD": "APP_SECRET_SENTINEL", "GITHUB_SHA": "test-commit",
        "AZURE_TENANT_ID": c["AZURE_TENANT_ID"], "ENTRA_API_CLIENT_ID": c["ENTRA_API_CLIENT_ID"],
        "ENTRA_SPA_CLIENT_ID": c["ENTRA_SPA_CLIENT_ID"], "ENTRA_ALLOWED_CLIENT_IDS": c["ENTRA_ALLOWED_CLIENT_IDS"],
    }


def test_valid_config_and_defaults():
    assert validate(config()) == []
    assert validate(dict(config(), AZURE_HOSTING="appservice", AZURE_LOCATION="centralus")) == []


@pytest.mark.parametrize("key,value", [
    ("AZURE_TENANT_ID", "not-a-guid"), ("AZURE_SUBSCRIPTION_ID", ""),
    ("AZURE_DEPLOY_CLIENT_ID", "00000000-0000-0000-0000-000000000000"),
    ("ENTRA_API_CLIENT_ID", "{00000004-1111-4111-8111-111111111111}"),
    ("ENTRA_SPA_CLIENT_ID", "invalid"), ("AZURE_PREFIX", "Bad-prefix"),
    ("AZURE_PREFIX", "ab"), ("AZURE_HOSTING", "invalid"),
    ("AZURE_LOCATION", "East US"), ("AZURE_RESOURCE_GROUP", "has spaces"),
    ("ENTRA_ALLOWED_CLIENT_IDS", ","), ("DATABASE_ADMIN_PASSWORD", " "),
    ("DATABASE_APP_PASSWORD", ""), ("SEED_DEMO", "maybe"),
])
def test_bad_configuration(key, value):
    assert any(key in error for error in validate(dict(config(), **{key: value})))


def test_allowlist_relationship_and_empty_entry():
    c = config()
    c["ENTRA_ALLOWED_CLIENT_IDS"] = c["ENTRA_API_CLIENT_ID"]
    assert any("include ENTRA_SPA_CLIENT_ID" in error for error in validate(c))
    c["ENTRA_ALLOWED_CLIENT_IDS"] = config()["ENTRA_SPA_CLIENT_ID"] + ","
    assert any("empty entries" in error for error in validate(c))
    c = config()
    c["ENTRA_API_CLIENT_ID"] = c["ENTRA_SPA_CLIENT_ID"]
    assert any("separate app registrations" in error for error in validate(c))


def test_preflight_cli_redacts_values():
    env = dict(os.environ, **config(), AZURE_HOSTING="PRIVATE_BAD_VALUE")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/preflight_tenant.py")],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "AZURE_HOSTING" in result.stderr
    assert "PRIVATE_BAD_VALUE" not in result.stdout + result.stderr
    assert env["DATABASE_ADMIN_PASSWORD"] not in result.stdout + result.stderr


@pytest.fixture
def repo(tmp_path):
    for name, heading in HEADINGS.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(heading + "\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app/start.py").write_text("def main():\n    pass\n", encoding="utf-8")
    return tmp_path


def test_repo_sanity_and_mutations(repo):
    assert not check(repo)
    guide = repo / "docs/BEGINNERS_GUIDE.md"
    guide.write_text('"""startup"""\nimport os\ndef main(): pass\n')
    assert any("BEGINNERS_GUIDE" in error for error in check(repo))
    guide.unlink()
    assert any("Missing required document" in error for error in check(repo))
    (repo / "README.md").write_text("# Health Claims Portal\n[missing](missing.md)\n")
    assert any("broken repository link" in error for error in check(repo))
    (repo / "app/start.py").write_text("def main(:\n")
    assert any("cannot compile" in error for error in check(repo))


def test_contract_rejects_drift():
    template = {"parameters": {"name": {"type": "string"}}}
    with pytest.raises(ValueError, match="Missing"):
        check_contract({"parameters": {}}, template)
    with pytest.raises(ValueError, match="Unknown"):
        check_contract({"parameters": {"extra": {"value": "x"}}}, template)
    with pytest.raises(ValueError, match="Expected string"):
        check_contract({"parameters": {"name": {"value": 1}}}, template)


@pytest.mark.parametrize("hosting", ["containerapps", "appservice"])
def test_live_parameters_keep_contract(hosting):
    env = runtime_config(hosting)
    foundation = parameters(env)["parameters"]
    assert foundation == {k: {"value": v} for k, v in {
        "prefix": env["AZURE_PREFIX"], "location": "eastus", "databasePassword": env["DATABASE_ADMIN_PASSWORD"],
        "hosting": hosting,
        "databaseSku": "Standard_B1ms", "databaseTier": "Burstable",
    }.items()}
    outputs = fixture_outputs()
    actual = parameters(env, outputs)["parameters"]
    expected = {"prefix", "location", "databasePassword", "identityId", "databaseHost", "image",
                "tenantId", "apiClientId", "spaClientId", "allowedClientIds", "appDatabasePassword", "seedDemo"}
    expected |= {"webSubnetId", "logsWorkspaceId"} if hosting == "appservice" else {"environmentId", "registryServer"}
    assert set(actual) == expected
    assert actual["databasePassword"]["value"] == env["DATABASE_ADMIN_PASSWORD"]
    assert actual["image"]["value"] == "validationonly.azurecr.io/health-claims-portal:test-commit"


@pytest.mark.parametrize("hosting", ["containerapps", "appservice"])
def test_dry_run_cli_with_compiled_templates(tmp_path, hosting):
    templates = ROOT / "work/templates"
    if not templates.exists():
        if os.environ.get("REQUIRE_COMPILED_TEMPLATES") == "1":
            pytest.fail("CI must compile templates before testing parameter generation")
        pytest.skip("Compile Bicep templates into work/templates for contract integration tests")
    shutil.copytree(templates, tmp_path / "work/templates")
    # Deliberately invalid real outputs: dry run must not depend on or overwrite these.
    real = tmp_path / "work/foundation.outputs.json"
    real.write_text("do not consume")
    env = dict(os.environ, **runtime_config(hosting))
    result = subprocess.run([sys.executable, str(ROOT / "scripts/deployment_parameters.py"), "--dry-run"],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert real.read_text() == "do not consume"
    assert not (tmp_path / "work/app.parameters.json").exists()
    for name in ("foundation", "app"):
        body = (tmp_path / f"work/validation/{name}.parameters.json").read_text()
        assert env["DATABASE_ADMIN_PASSWORD"] not in body + result.stdout + result.stderr
        assert env["DATABASE_APP_PASSWORD"] not in body + result.stdout + result.stderr
        assert json.loads(body)["parameters"]["databasePassword"]["value"] == "ValidationOnly_123!"


def test_workflow_cloud_steps_are_gated():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
    assert "default: true" in workflow
    steps = workflow.split("      - ")[1:]
    cloud_steps = [s for s in steps if any(x in s for x in
                   ("azure/login@", "az deployment ", "az acr build", "Build parameter files without logging"))]
    assert len(cloud_steps) == 5
    assert all("if: ${{ !inputs.dry_run }}" in step for step in cloud_steps)
    validation, deployment = workflow.split("\n  deploy:", 1)
    assert "id-token: write" not in validation
    assert "id-token: write" in deployment
    assert "needs: validate" in deployment
    assert workflow.index("python scripts/preflight_tenant.py") < workflow.index("azure/login@")


def test_database_passwords_must_be_separate():
    c = config()
    c["DATABASE_APP_PASSWORD"] = c["DATABASE_ADMIN_PASSWORD"]
    assert any("different password" in error for error in validate(c))


def test_database_capacity_override_is_passed_to_foundation():
    env = dict(runtime_config("appservice"), AZURE_POSTGRES_SKU="Standard_B2s", AZURE_POSTGRES_TIER="Burstable")
    assert validate(dict(config(), **{k: env[k] for k in ("AZURE_POSTGRES_SKU", "AZURE_POSTGRES_TIER")})) == []
    result = parameters(env)["parameters"]
    assert result["databaseSku"]["value"] == "Standard_B2s"
    assert result["databaseTier"]["value"] == "Burstable"
    assert validate(dict(config(), AZURE_POSTGRES_SKU="invalid"))
    assert validate(dict(config(), AZURE_POSTGRES_TIER="invalid"))
