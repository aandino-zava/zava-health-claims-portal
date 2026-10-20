"""Onboarding boundaries: no tenant or GitHub connection required."""
from copy import deepcopy

import pytest

from scripts import onboard_azure as onboarding


def test_api_manifest_preserves_ids_and_unrelated_permissions():
    app = {"appId": "api-client", "identifierUris": ["api://custom"], "appRoles": [
        {"id": "reader-role", "value": "Claims.Reader"},
        {"id": "unrelated-role", "value": "Other"},
    ], "api": {"oauth2PermissionScopes": [
        {"id": "existing-scope", "value": "Claims.Access", "isEnabled": True},
    ], "preAuthorizedApplications": [{"appId": "approved-client"}]}}
    before = deepcopy(app)
    manifest, scope = onboarding.api_manifest(app)
    assert app == before
    assert scope["id"] == "existing-scope"
    assert manifest["api"]["requestedAccessTokenVersion"] == 2
    assert manifest["api"]["preAuthorizedApplications"] == [{"appId": "approved-client"}]
    assert {role["value"]: role["id"] for role in manifest["appRoles"]}["Claims.Reader"] == "reader-role"
    assert "api://custom" in manifest["identifierUris"]
    assert len(manifest["appRoles"]) == 4


def claims():
    return {"repository": "owner/claims", "repository_id": "123", "repository_owner_id": "456",
            "iss": "https://token.actions.githubusercontent.com", "aud": "api://AzureADTokenExchange",
            "environment": "azure-demo", "ref": "refs/heads/main",
            "sub": "repo:owner@456/claims@123:environment:azure-demo"}


def repo():
    return {"full_name": "owner/claims", "id": 123, "owner": {"id": 456}}


def test_subject_is_observed_instead_of_inferred_from_repo_age():
    assert onboarding.validate_claims(claims(), repo()) == claims()["sub"]
    legacy = dict(claims(), sub="repo:owner/claims:environment:azure-demo")
    assert onboarding.validate_claims(legacy, repo()) == legacy["sub"]


@pytest.mark.parametrize("key,value", [
    ("repository", "attacker/claims"), ("repository_id", "999"),
    ("repository_owner_id", "999"), ("environment", "other"),
    ("ref", "refs/heads/untrusted"), ("iss", "https://other.example"),
    ("aud", "other"), ("sub", "repo:owner/claims:pull_request"),
])
def test_rejects_mismatched_federation_context(key, value):
    with pytest.raises(RuntimeError):
        onboarding.validate_claims(dict(claims(), **{key: value}), repo())


def test_redirect_merges_existing_uris_and_has_exact_trailing_slash(monkeypatch):
    app = {"spa": {"redirectUris": ["https://other.example/"]}}

    def fake_graph(path, method="GET", body=None):
        if method == "PATCH":
            app.update(body)
        return deepcopy(app)

    monkeypatch.setattr(onboarding, "graph", fake_graph)
    assert onboarding.set_redirect("spa", "https://claims.example") == "https://claims.example/"
    assert app["spa"]["redirectUris"] == ["https://claims.example/", "https://other.example/"]
    onboarding.set_redirect("spa", "https://claims.example/")
    assert len(app["spa"]["redirectUris"]) == 2


@pytest.mark.parametrize("url", ["http://claims.example", "https://claims.example/path", "https://claims.example/?token=x"])
def test_redirect_rejects_invalid_origin(url):
    with pytest.raises(RuntimeError, match="HTTPS portal origin"):
        onboarding.set_redirect("spa", url)


def test_rbac_delegation_constrains_both_write_and_delete():
    condition = onboarding.delegation_condition("runtime-principal")
    assert condition.count(onboarding.ACR_PULL) == 2
    assert condition.count("runtime-principal") == 2
    assert "@Request[Microsoft.Authorization/roleAssignments:PrincipalId]" in condition
    assert "@Resource[Microsoft.Authorization/roleAssignments:PrincipalId]" in condition


def test_run_does_not_log_sensitive_cli_errors(monkeypatch):
    monkeypatch.setattr(onboarding.shutil, "which", lambda name: name)
    monkeypatch.setattr(onboarding.subprocess, "run", lambda *args, **kwargs: type("Result", (), {
        "returncode": 1, "stderr": "secret body", "stdout": "secret body",
    })())
    with pytest.raises(RuntimeError) as error:
        onboarding.run("gh", "secret", "set", "PASSWORD", body="secret body")
    assert "secret body" not in str(error.value)


def test_live_preflight_stops_on_regional_restriction_and_pending_feature(monkeypatch):
    def azure(*args):
        if args[1] == "postgres":
            return [{"supportedServerVersions": [], "reason": "Provisioning is restricted in this region."}]
        return {"properties": {"state": "Pending"}}

    monkeypatch.setattr(onboarding, "run", azure)
    with pytest.raises(RuntimeError) as error:
        onboarding.azure_readiness("eastus", "containerapps")
    assert "Provisioning is restricted" in str(error.value)
    assert "Pending approval" in str(error.value)


def test_app_service_preflight_does_not_require_container_network_feature(monkeypatch):
    def azure(*args):
        assert args[1] == "postgres"
        return [{"supportedServerVersions": [{"name": "16"}], "supportedServerEditions": [
            {"name": "Burstable", "supportedServerSkus": [{"name": "Standard_B1ms"}]},
        ]}]

    monkeypatch.setattr(onboarding, "run", azure)
    onboarding.azure_readiness("eastus2", "appservice")


def test_configured_registration_is_reused_after_infrastructure_prefix_change(monkeypatch):
    client = "11111111-1111-4111-8111-111111111111"
    app = {"id": "original-registration", "appId": client, "displayName": "original-claims-api"}
    expressions = []

    def lookup(path):
        expressions.append(path)
        return [app]

    monkeypatch.setattr(onboarding, "all_graph", lookup)
    assert onboarding.application("newprefix-claims-api", client) == app
    assert "appId%20eq" in expressions[0]
    assert "displayName" not in expressions[0]


def test_missing_configured_registration_never_creates_replacement(monkeypatch):
    monkeypatch.setattr(onboarding, "all_graph", lambda path: [])
    with pytest.raises(RuntimeError, match="not found"):
        onboarding.application("newprefix-claims-api", "11111111-1111-4111-8111-111111111111")


def test_readiness_checks_selected_database_size_instead_of_default(monkeypatch):
    monkeypatch.setattr(onboarding, "run", lambda *args: [{
        "supportedServerVersions": [{"name": "16"}], "supportedServerEditions": [
            {"name": "Burstable", "supportedServerSkus": [{"name": "Standard_B2s"}]},
        ],
    }])
    onboarding.azure_readiness("eastus2", "appservice", "Standard_B2s", "Burstable")
    with pytest.raises(RuntimeError, match="Standard_B1ms"):
        onboarding.azure_readiness("eastus2", "appservice")


def test_arm_plan_preflight_uses_metadata_only_and_requested_size(monkeypatch):
    import json
    from pathlib import Path

    def azure(*args, **kwargs):
        assert args[:4] == ("az", "deployment", "group", "validate")
        template = json.loads(Path(args[args.index("--template-file") + 1]).read_text())
        assert "parameters" not in template
        plan = template["resources"][0]
        assert plan["name"] == "claims-plan"
        assert plan["sku"] == {"name": "P0v3", "tier": "PremiumV3", "capacity": 1}
        assert kwargs["public_errors"] is True

    monkeypatch.setattr(onboarding, "run", azure)
    onboarding.validate_appservice_plan("eastus2", "P0v3", "demo-rg", "claims")
