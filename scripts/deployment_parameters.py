"""Generate parameters; validation-only mode uses isolated fictitious outputs."""
import argparse
import json
import os
from pathlib import Path


def parameters(env, outputs=None):
    hosting = env.get("AZURE_HOSTING", "containerapps")
    if hosting not in {"containerapps", "appservice"}:
        raise ValueError("AZURE_HOSTING must be containerapps or appservice")
    params = {
        "prefix": env["AZURE_PREFIX"], "location": env.get("AZURE_LOCATION", "eastus"),
        "databasePassword": env["DATABASE_ADMIN_PASSWORD"],
    }
    if outputs is None:
        params["hosting"] = hosting
        if hosting == "appservice" and env.get("AZURE_APPSERVICE_LOCATION"):
            params["appServiceLocation"] = env["AZURE_APPSERVICE_LOCATION"]
        params["databaseSku"] = env.get("AZURE_POSTGRES_SKU", "Standard_B1ms")
        params["databaseTier"] = env.get("AZURE_POSTGRES_TIER", "Burstable")
        if env.get("AZURE_POSTGRES_SERVER_NAME"):
            params["databaseServerName"] = env["AZURE_POSTGRES_SERVER_NAME"]
    else:
        keys = (("identityId", "databaseHost", "webSubnetId", "logsWorkspaceId") if hosting == "appservice"
                else ("environmentId", "identityId", "registryServer", "databaseHost"))
        for key in keys:
            params[key] = outputs[key]["value"]
        if hosting == "appservice":
            params["appServiceSku"] = env.get("AZURE_APPSERVICE_SKU", "B1")
            params["location"] = env.get("AZURE_APPSERVICE_LOCATION") or params["location"]
        params.update(
            appDatabasePassword=env["DATABASE_APP_PASSWORD"],
            seedDemo=env.get("SEED_DEMO", "true").lower() == "true",
            image=f"{outputs['registryServer']['value']}/health-claims-portal:{env['GITHUB_SHA']}",
            tenantId=env["AZURE_TENANT_ID"], apiClientId=env["ENTRA_API_CLIENT_ID"],
            spaClientId=env["ENTRA_SPA_CLIENT_ID"], allowedClientIds=env["ENTRA_ALLOWED_CLIENT_IDS"],
        )
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
        "contentVersion": "1.0.0.0",
        "parameters": {key: {"value": value} for key, value in params.items()},
    }


def fixture_outputs():
    scope = "/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/validation-only"
    values = {
        "identityId": f"{scope}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/fixture",
        "environmentId": f"{scope}/providers/Microsoft.App/managedEnvironments/fixture",
        "webSubnetId": f"{scope}/providers/Microsoft.Network/virtualNetworks/fixture/subnets/web",
        "registryServer": "validationonly.azurecr.io",
        "databaseHost": "validation-only.postgres.database.azure.com",
        "logsWorkspaceId": f"{scope}/providers/Microsoft.OperationalInsights/workspaces/fixture",
    }
    return {key: {"value": value} for key, value in values.items()}


def check_contract(document, template):
    supplied, declared = document["parameters"], template.get("parameters", {})
    for name in supplied.keys() - declared.keys():
        raise ValueError(f"Unknown template parameter: {name}")
    for name, spec in declared.items():
        if name not in supplied:
            if "defaultValue" not in spec:
                raise ValueError(f"Missing template parameter: {name}")
            continue
        value = supplied[name]["value"]
        if spec["type"].lower() in {"string", "securestring"} and not isinstance(value, str):
            raise ValueError(f"Expected string parameter: {name}")
        if spec["type"].lower() == "bool" and not isinstance(value, bool):
            raise ValueError(f"Expected bool parameter: {name}")
        if "allowedValues" in spec and value not in spec["allowedValues"]:
            raise ValueError(f"Invalid allowed value for parameter: {name}")
        if isinstance(value, str) and not spec.get("minLength", 0) <= len(value) <= spec.get("maxLength", 10**9):
            raise ValueError(f"Invalid length for parameter: {name}")


def dry_run(env, folder, templates):
    # Do not consume real deployment outputs or persist the configured password.
    sample = dict(env, DATABASE_ADMIN_PASSWORD="ValidationOnly_123!", DATABASE_APP_PASSWORD="ValidationApp_123!", GITHUB_SHA=env.get("GITHUB_SHA", "validation-only"))
    documents = {"foundation": parameters(sample), "app": parameters(sample, fixture_outputs())}
    app_template = "app-service" if sample.get("AZURE_HOSTING") == "appservice" else "app"
    for name, document in documents.items():
        template_name = "foundation" if name == "foundation" else app_template
        check_contract(document, json.loads((templates / f"{template_name}.json").read_text()))
    folder.mkdir(parents=True, exist_ok=True)
    for name, document in documents.items():
        (folder / f"{name}.parameters.json").write_text(json.dumps(document), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--app", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    folder = Path("work")
    if args.dry_run:
        dry_run(os.environ, folder / "validation", folder / "templates")
        print("Parameter contracts passed using fictitious infrastructure outputs and a dummy password.")
        return
    folder.mkdir(exist_ok=True)
    outputs = json.loads((folder / "foundation.outputs.json").read_text()) if args.app else None
    document = parameters(os.environ, outputs)
    name = "app" if args.app else "foundation"
    (folder / f"{name}.parameters.json").write_text(json.dumps(document), encoding="utf-8")


if __name__ == "__main__":
    main()
