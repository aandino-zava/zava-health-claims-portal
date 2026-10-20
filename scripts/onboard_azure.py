"""Administrator-run Azure/GitHub onboarding. Requires signed-in az and gh CLIs.

No administrator token, client secret, or database password is written to source/state.
Run from the repository root. See docs/DEPLOYMENT.md for privileges and recovery.
"""
import argparse
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

GRAPH = "https://graph.microsoft.com/v1.0/"
CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"
RBAC_ADMIN = "f58310d9-a9f6-439a-9e8d-f62e7b41a168"
ACR_PULL = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
STATE = Path("work/onboarding-state.json")
APPSERVICE_CORES = {"B1": 1, "B2": 2, "B3": 4, "S1": 1, "S2": 2, "S3": 4,
                    "P0v3": 1, "P1v3": 2, "P2v3": 4, "P3v3": 8}


def run(*args, body=None, raw=False):
    """Use stdin for GitHub JSON/secrets; never echo command arguments or input."""
    executable = shutil.which(args[0])
    if not executable:
        raise RuntimeError(f"Install {args[0]} and put it on PATH.")
    command = [executable]
    if args[0] == "az" and Path(executable).suffix.lower() == ".cmd":
        # The Windows MSI batch shim reinterprets Graph query strings and ABAC expressions.
        # Invoke that installation's own Python module with an argument vector instead.
        cli_python = Path(executable).parent.parent / "python.exe"
        if not cli_python.exists():
            raise RuntimeError("Azure CLI batch shim has no adjacent Python runtime; use the MSI installer.")
        command = [str(cli_python), "-IBm", "azure.cli"]
    result = subprocess.run([*command, *map(str, args[1:])], input=body,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        # CLI errors can contain submitted bodies: surface the operation, not its input.
        raise RuntimeError(f"{args[0]} {' '.join(args[1:3])} failed (exit {result.returncode}). "
                           "Check account privileges and the corresponding service operation.")
    if raw:
        return result.stdout
    return json.loads(result.stdout) if result.stdout.strip() else None


def gh(path, method="GET", body=None):
    args = ["gh", "api", path, "--method", method]
    if body is not None:
        args += ["--input", "-"]
    return run(*args, body=json.dumps(body) if body is not None else None)


def graph(path, method="GET", body=None):
    args = ["az", "rest", "--method", method, "--url", GRAPH + path, "--output", "json"]
    if body is None:
        return run(*args)
    # az rest has no portable stdin body mode. Temporary bodies contain only app metadata.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "body.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        return run(*args, "--body", "@" + str(path))


def all_graph(path):
    rows = []
    while path:
        data = graph(path)
        rows.extend(data["value"])
        link = data.get("@odata.nextLink")
        if link and not link.startswith(GRAPH):
            raise RuntimeError("Unexpected Microsoft Graph pagination host.")
        path = link.removeprefix(GRAPH) if link else None
    return rows


def application(name, client_id=None):
    if client_id:
        try:
            client_id = str(UUID(client_id))
        except ValueError:
            raise RuntimeError("Configured registration client ID is invalid.") from None
    expression = f"appId eq '{client_id}'" if client_id else f"displayName eq '{name}'"
    matches = all_graph("applications?$filter=" + quote(expression))
    if len(matches) > 1:
        raise RuntimeError(f"Multiple registrations named {name}; resolve the ambiguity first.")
    if client_id and not matches:
        raise RuntimeError("Configured registration was not found in the signed-in tenant.")
    return matches[0] if matches else graph("applications", "POST", {
        "displayName": name, "signInAudience": "AzureADMyOrg",
    })


def service_principal(client_id):
    matches = all_graph("servicePrincipals?$filter=" + quote(f"appId eq '{client_id}'"))
    if matches:
        return matches[0]
    return graph("servicePrincipals", "POST", {"appId": client_id})


def api_manifest(app):
    roles = list(app.get("appRoles", []))
    for label in ("Reader", "Writer", "Reviewer"):
        value = f"Claims.{label}"
        existing = next((role for role in roles if role["value"] == value), None)
        role = {"id": existing["id"] if existing else str(uuid4()), "value": value,
                "displayName": value, "description": f"{label} access to synthetic health claims",
                "allowedMemberTypes": ["User", "Application"], "isEnabled": True}
        if existing:
            roles[roles.index(existing)] = role
        else:
            roles.append(role)
    api = dict(app.get("api") or {})
    scopes = list(api.get("oauth2PermissionScopes", []))
    scope = next((scope for scope in scopes if scope["value"] == "Claims.Access"), None)
    if not scope:
        scope = {"id": str(uuid4()), "value": "Claims.Access", "type": "Admin", "isEnabled": True,
                 "adminConsentDisplayName": "Access the health claims portal",
                 "adminConsentDescription": "Access synthetic claims as the signed-in employee"}
        scopes.append(scope)
    if not scope["isEnabled"]:
        raise RuntimeError("Claims.Access is disabled; resolve its lifecycle before onboarding.")
    api.update(requestedAccessTokenVersion=2, oauth2PermissionScopes=scopes)
    return {"identifierUris": sorted(set(app.get("identifierUris", []) + ["api://" + app["appId"]])),
            "api": api, "appRoles": roles}, scope


def ensure_identities(prefix, employee_id, configured=None):
    configured = configured or {}
    api = application(f"{prefix}-claims-api", configured.get("ENTRA_API_CLIENT_ID"))
    manifest, scope = api_manifest(api)
    graph("applications/" + api["id"], "PATCH", manifest)
    api = graph("applications/" + api["id"])
    api_sp = service_principal(api["appId"])
    spa = application(f"{prefix}-claims-spa", configured.get("ENTRA_SPA_CLIENT_ID"))
    access = list(spa.get("requiredResourceAccess", []))
    resource = next((entry for entry in access if entry["resourceAppId"] == api["appId"]), None)
    if resource is None:
        resource = {"resourceAppId": api["appId"], "resourceAccess": []}
        access.append(resource)
    permission = {"id": scope["id"], "type": "Scope"}
    if permission not in resource["resourceAccess"]:
        resource["resourceAccess"].append(permission)
    graph("applications/" + spa["id"], "PATCH", {"requiredResourceAccess": access})
    spa_sp = service_principal(spa["appId"])
    grants = all_graph("oauth2PermissionGrants?$filter=" + quote(f"clientId eq '{spa_sp['id']}'"))
    grant = next((item for item in grants if item["resourceId"] == api_sp["id"]
                  and item["consentType"] == "AllPrincipals"), None)
    if grant:
        scopes = set(grant["scope"].split()) | {"Claims.Access"}
        graph("oauth2PermissionGrants/" + grant["id"], "PATCH", {"scope": " ".join(sorted(scopes))})
    else:
        graph("oauth2PermissionGrants", "POST", {"clientId": spa_sp["id"], "resourceId": api_sp["id"],
              "consentType": "AllPrincipals", "scope": "Claims.Access"})
    assignments = all_graph(f"users/{employee_id}/appRoleAssignments")
    for role in api["appRoles"]:
        if role["value"] in {"Claims.Reader", "Claims.Writer", "Claims.Reviewer"}:
            if not any(item["resourceId"] == api_sp["id"] and item["appRoleId"] == role["id"]
                       for item in assignments):
                graph(f"users/{employee_id}/appRoleAssignments", "POST", {
                    "principalId": employee_id, "resourceId": api_sp["id"], "appRoleId": role["id"],
                })
    deploy = application(f"{prefix}-github-deploy", configured.get("AZURE_DEPLOY_CLIENT_ID"))
    return api, spa, deploy, service_principal(deploy["appId"])


def ensure_azure_role(principal, role, scope, condition=None):
    matches = run("az", "role", "assignment", "list", "--scope", scope,
                  "--assignee", principal, "--output", "json")
    matches = [item for item in matches if item["scope"].lower() == scope.lower()
               and item["roleDefinitionId"].lower().endswith(role)]
    if matches:
        if condition and any(item.get("condition") != condition for item in matches):
            raise RuntimeError("Existing RBAC delegation has different conditions; review it before continuing.")
        return
    args = ["az", "role", "assignment", "create", "--assignee-object-id", principal,
            "--assignee-principal-type", "ServicePrincipal", "--role", role, "--scope", scope,
            "--name", str(uuid5(NAMESPACE_URL, scope + principal + role)), "--output", "none"]
    if condition:
        args += ["--condition", condition, "--condition-version", "2.0"]
    run(*args)


def delegation_condition(runtime_principal):
    return (
        "((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR "
        f"(@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {{{ACR_PULL}}} "
        f"AND @Request[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {{{runtime_principal}}})) "
        "AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR "
        f"(@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {{{ACR_PULL}}} "
        f"AND @Resource[Microsoft.Authorization/roleAssignments:PrincipalId] ForAnyOfAnyValues:GuidEquals {{{runtime_principal}}}))"
    )


def azure_readiness(location, hosting, database_sku="Standard_B1ms", database_tier="Burstable"):
    """Check service-advertised restrictions before creating billable infrastructure."""
    capabilities = run("az", "postgres", "flexible-server", "list-skus", "--location", location,
                       "--output", "json")
    errors = []
    available = False
    for capability in capabilities:
        versions = capability.get("supportedServerVersions", [])
        editions = capability.get("supportedServerEditions", [])
        version = any(item.get("name") == "16" for item in versions)
        sku = any(item.get("name", "").lower() == database_sku.lower()
                  for edition in editions if edition.get("name") == database_tier
                  for item in edition.get("supportedServerSkus", []))
        available |= version and sku
    if not available:
        reasons = sorted({item["reason"] for item in capabilities if item.get("reason")})
        errors.append(f"PostgreSQL 16 / {database_sku} is not advertised for this subscription in {location}. "
                      + " ".join(reasons))
    if hosting == "containerapps":
        feature = run("az", "feature", "show", "--namespace", "Microsoft.Network",
                      "--name", "AllowBringYourOwnPublicIpAddress", "--output", "json")
        if feature.get("properties", {}).get("state") == "Pending":
            errors.append("Microsoft.Network/AllowBringYourOwnPublicIpAddress is Pending approval; "
                          "this subscription cannot provision the requested Container Apps network. "
                          "Resolve the approval with Azure support or select App Service.")
    if errors:
        raise RuntimeError("Azure subscription readiness failed:\n- " + "\n- ".join(errors))
    print(f"Azure advertises PostgreSQL 16 / {database_sku} in {location}; no checked blocker found.", flush=True)


def appservice_quota_error(usages, sku):
    tier = "Basic" if sku.startswith("B") else "Standard" if sku.startswith("S") else "Premium v3"
    matches = [entry for entry in usages if entry.get("name", {}).get("localizedValue") == tier]
    if matches and any(entry.get("limit", 0) - entry.get("currentValue", 0) < APPSERVICE_CORES[sku]
                       for entry in matches):
        return f"App Service {tier} quota is insufficient for {sku} in this region. Select an available tier or request quota."
    return None


def appservice_readiness(location, sku):
    if sku not in APPSERVICE_CORES:
        raise RuntimeError("Unsupported App Service size; check AZURE_APPSERVICE_SKU.")
    subscription = run("az", "account", "show", "--query", "id", "--output", "json")
    url = (f"https://management.azure.com/subscriptions/{subscription}/providers/Microsoft.Web/"
           f"locations/{location}/usages?api-version=2023-12-01")
    result = run("az", "rest", "--method", "get", "--url", url,
                 "--headers", "Accept-Language=en-US", "--output", "json")
    error = appservice_quota_error(result["value"], sku)
    if error:
        raise RuntimeError(error)
    print(f"No reported App Service quota blocker for {sku} in {location}.", flush=True)


def workflow(repo, filename, title_prefix, inputs, timeout=7200):
    request_id = str(uuid4())
    key = "request_id" if filename == "oidc.yml" else "onboarding_id"
    sha = gh(f"repos/{repo}/git/ref/heads/main")["object"]["sha"]
    gh(f"repos/{repo}/actions/workflows/{filename}/dispatches", "POST", {
        "ref": "main", "inputs": dict(inputs, **{key: request_id}),
    })
    deadline = time.monotonic() + timeout
    run_id = None
    print(f"Waiting for {title_prefix}: {request_id}", flush=True)
    while time.monotonic() < deadline:
        if run_id is None:
            runs = gh(f"repos/{repo}/actions/workflows/{filename}/runs?event=workflow_dispatch&per_page=100")
            match = next((item for item in runs["workflow_runs"]
                          if item["display_title"] == title_prefix + " · " + request_id), None)
            if match:
                if match["head_sha"] != sha:
                    raise RuntimeError("main changed during dispatch; inspect the workflow commit.")
                run_id = match["id"]
                print(match["html_url"], flush=True)
        if run_id:
            current = gh(f"repos/{repo}/actions/runs/{run_id}")
            if current["status"] == "completed":
                if current["conclusion"] != "success":
                    raise RuntimeError("Workflow failed; inspect " + current["html_url"])
                return run_id
        time.sleep(10)
    raise RuntimeError("Workflow is still pending. Inspect Actions before rerunning onboarding.")


def validate_claims(claims, repo_info):
    expected = {"repository": repo_info["full_name"], "repository_id": str(repo_info["id"]),
                "repository_owner_id": str(repo_info["owner"]["id"]), "environment": "azure-demo",
                "ref": "refs/heads/main", "iss": "https://token.actions.githubusercontent.com",
                "aud": "api://AzureADTokenExchange"}
    if any(str(claims.get(key)) != value for key, value in expected.items()):
        raise RuntimeError("OIDC metadata does not match this repository, main, and azure-demo.")
    if not claims.get("sub") or ":environment:azure-demo" not in claims["sub"]:
        raise RuntimeError("OIDC subject does not bind the azure-demo environment.")
    return claims["sub"]


def discover_subject(repo, repo_info):
    run_id = workflow(repo, "oidc.yml", "OIDC discovery", {})
    logs = run("gh", "run", "view", str(run_id), "--repo", repo, "--log", raw=True)
    rows = [line.split("ONBOARDING_OIDC=", 1)[1] for line in logs.splitlines()
            if "ONBOARDING_OIDC={" in line]
    if len(rows) != 1:
        raise RuntimeError("Could not read a unique OIDC discovery result.")
    return validate_claims(json.loads(rows[0]), repo_info)


def set_redirect(spa_id, url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise RuntimeError("Deployment did not return an HTTPS portal origin.")
    redirect = url.rstrip("/") + "/"
    spa = graph("applications/" + spa_id)
    platform = dict(spa.get("spa") or {})
    platform["redirectUris"] = sorted(set(platform.get("redirectUris", []) + [redirect]))
    graph("applications/" + spa_id, "PATCH", {"spa": platform})
    if redirect not in graph("applications/" + spa_id)["spa"]["redirectUris"]:
        raise RuntimeError("Redirect URI did not persist.")
    return redirect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="OWNER/REPOSITORY")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--location", default="eastus")
    parser.add_argument("--hosting", choices=("containerapps", "appservice"), default="containerapps")
    parser.add_argument("--database-sku", help="PostgreSQL SKU; defaults to the environment setting or Standard_B1ms")
    parser.add_argument("--database-tier", choices=("Burstable", "GeneralPurpose", "MemoryOptimized"))
    parser.add_argument("--database-server-name", help="Explicit name for a deliberately new PostgreSQL server")
    parser.add_argument("--appservice-sku", choices=tuple(APPSERVICE_CORES))
    parser.add_argument("--employee", help="Employee object ID; defaults to the signed-in administrator")
    parser.add_argument("--deploy", action="store_true", help="Validate, deploy billable resources, and set redirect")
    parser.add_argument("--finalize", action="store_true", help="Set redirect from the existing claims-app deployment")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9]{2,15}", args.prefix):
        parser.error("prefix must be 3-16 lowercase letters/digits, starting with a letter")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        parser.error("repo must be OWNER/REPOSITORY")
    account = run("az", "account", "show", "--subscription", args.subscription, "--output", "json")
    if account["tenantId"] != args.tenant:
        raise RuntimeError("The subscription does not belong to the requested tenant.")
    run("az", "account", "set", "--subscription", args.subscription)
    group = run("az", "group", "show", "--name", args.resource_group, "--output", "json")
    scope = group["id"]
    info = gh("repos/" + args.repo)
    if not info.get("permissions", {}).get("admin"):
        raise RuntimeError("GitHub repository administrator access is required.")
    variables_path = f"repos/{args.repo}/environments/azure-demo/variables"
    STATE.parent.mkdir(exist_ok=True)
    if STATE.exists():
        old = json.loads(STATE.read_text(encoding="utf-8"))
        if old["repository"] != info["full_name"] or old["resource_group_id"].lower() != scope.lower():
            raise RuntimeError("Local onboarding state belongs to a different destination.")
    if args.finalize:
        if not STATE.exists():
            raise RuntimeError("Run onboarding first to record the SPA registration.")
        url = run("az", "deployment", "group", "show", "-g", args.resource_group, "-n", "claims-app",
                  "--query", "properties.outputs.portalUrl.value", "--output", "tsv", raw=True).strip()
        old["portal_url"] = set_redirect(old["spa_object_id"], url)
        STATE.write_text(json.dumps(old, indent=2) + "\n", encoding="utf-8")
        print("Sign-in redirect configured: " + old["portal_url"])
        return
    environment_path = f"repos/{args.repo}/environments/azure-demo"
    environments = gh(f"repos/{args.repo}/environments?per_page=100")["environments"]
    if not any(item["name"] == "azure-demo" for item in environments):
        gh(environment_path, "PUT", {"deployment_branch_policy": {
            "protected_branches": False, "custom_branch_policies": True,
        }})
        gh(environment_path + "/deployment-branch-policies", "POST", {"name": "main", "type": "branch"})
    current = {item["name"]: item["value"] for item in gh(variables_path + "?per_page=100")["variables"]}
    database_sku = args.database_sku or current.get("AZURE_POSTGRES_SKU", "Standard_B1ms")
    database_tier = args.database_tier or current.get("AZURE_POSTGRES_TIER", "Burstable")
    database_name = args.database_server_name or current.get("AZURE_POSTGRES_SERVER_NAME")
    appservice_sku = args.appservice_sku or current.get("AZURE_APPSERVICE_SKU", "B1")
    if database_name and not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", database_name):
        raise RuntimeError("Invalid PostgreSQL server name.")
    if not re.fullmatch(r"Standard_[A-Za-z0-9_]+", database_sku):
        raise RuntimeError("Invalid PostgreSQL SKU name.")
    if args.deploy:
        azure_readiness(args.location, args.hosting, database_sku, database_tier)
        if args.hosting == "appservice":
            appservice_readiness(args.location, appservice_sku)
    for key, expected in {"AZURE_TENANT_ID": args.tenant, "AZURE_SUBSCRIPTION_ID": args.subscription,
                          "AZURE_PREFIX": args.prefix, "AZURE_HOSTING": args.hosting,
                          "AZURE_RESOURCE_GROUP": args.resource_group}.items():
        if current.get(key) and current[key] != expected:
            raise RuntimeError(f"Existing {key} differs; review destination settings before changing it.")
    print("Discovering the repository's actual OIDC subject (no Azure credentials in the job).", flush=True)
    subject = discover_subject(args.repo, info)
    employee = args.employee or graph("me?$select=id")["id"]
    print("Configuring Entra registrations, consent, and demo employee roles.", flush=True)
    api, spa, deploy, deploy_sp = ensure_identities(args.prefix, employee, current)
    runtime = run("az", "identity", "create", "-g", args.resource_group, "-n", args.prefix + "-runtime",
                  "--location", args.location, "--output", "json")
    ensure_azure_role(deploy_sp["id"], CONTRIBUTOR, scope)
    ensure_azure_role(deploy_sp["id"], RBAC_ADMIN, scope, delegation_condition(runtime["principalId"]))
    federations = all_graph(f"applications/{deploy['id']}/federatedIdentityCredentials")
    credential = {"name": "github-azure-demo", "issuer": "https://token.actions.githubusercontent.com",
                  "subject": subject, "audiences": ["api://AzureADTokenExchange"]}
    existing = next((item for item in federations if item["name"] == credential["name"]), None)
    endpoint = f"applications/{deploy['id']}/federatedIdentityCredentials"
    graph(endpoint + ("/" + existing["id"] if existing else ""), "PATCH" if existing else "POST", credential)
    variables = {"AZURE_TENANT_ID": args.tenant, "AZURE_SUBSCRIPTION_ID": args.subscription,
                 "AZURE_DEPLOY_CLIENT_ID": deploy["appId"], "AZURE_RESOURCE_GROUP": args.resource_group,
                 "AZURE_LOCATION": args.location, "AZURE_HOSTING": args.hosting, "AZURE_PREFIX": args.prefix,
                 "AZURE_POSTGRES_SKU": database_sku, "AZURE_POSTGRES_TIER": database_tier,
                 "AZURE_APPSERVICE_SKU": appservice_sku,
                 "ENTRA_API_CLIENT_ID": api["appId"], "ENTRA_SPA_CLIENT_ID": spa["appId"],
                 "ENTRA_ALLOWED_CLIENT_IDS": spa["appId"], "SEED_DEMO": "true"}
    if database_name:
        variables["AZURE_POSTGRES_SERVER_NAME"] = database_name
    current = gh(environment_path + "/variables?per_page=100")["variables"]
    current = {item["name"]: item["value"] for item in current}
    # Preserve explicitly approved agent clients and the operator's seed preference on reruns.
    allowed = set(filter(None, (value.strip() for value in current.get("ENTRA_ALLOWED_CLIENT_IDS", "").split(","))))
    variables["ENTRA_ALLOWED_CLIENT_IDS"] = ",".join(sorted(allowed | {spa["appId"]}))
    variables["SEED_DEMO"] = current.get("SEED_DEMO", "true")
    for key in ("AZURE_PREFIX", "AZURE_HOSTING", "ENTRA_API_CLIENT_ID", "ENTRA_SPA_CLIENT_ID"):
        if current.get(key) and current[key] != variables[key]:
            raise RuntimeError(f"Existing {key} differs; review destination settings before changing it.")
    for key, value in variables.items():
        gh(environment_path + ("/variables/" + key if key in current else "/variables"),
           "PATCH" if key in current else "POST", {"name": key, "value": value})
    configured_secrets = {item["name"] for item in gh(environment_path + "/secrets?per_page=100")["secrets"]}
    for key in ("DATABASE_ADMIN_PASSWORD", "DATABASE_APP_PASSWORD"):
        if key not in configured_secrets:
            password = "Aa1!" + secrets.token_urlsafe(36)
            run("gh", "secret", "set", key, "--repo", args.repo, "--env", "azure-demo", body=password)
    state = {"repository": info["full_name"], "repository_id": info["id"], "resource_group_id": scope,
             "oidc_subject": subject, "spa_object_id": spa["id"], "employee_object_id": employee,
             "variables": variables}
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print("Azure and GitHub onboarding configured. Existing database secrets were preserved.", flush=True)
    state["validation_run"] = workflow(args.repo, "deploy.yml", "Deploy Azure demo", {"dry_run": "true"})
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    if args.deploy:
        state["deployment_run"] = workflow(args.repo, "deploy.yml", "Deploy Azure demo", {"dry_run": "false"})
        STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        url = run("az", "deployment", "group", "show", "-g", args.resource_group, "-n", "claims-app",
                  "--query", "properties.outputs.portalUrl.value", "--output", "tsv", raw=True).strip()
        state["portal_url"] = set_redirect(spa["id"], url)
        STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        print("Portal deployed; sign-in redirect configured: " + state["portal_url"], flush=True)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
