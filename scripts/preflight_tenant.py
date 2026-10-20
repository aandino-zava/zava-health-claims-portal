"""Offline deployment configuration checks. Never log configuration values."""
import os
import re
import sys
from uuid import UUID

GUID_KEYS = (
    "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "AZURE_DEPLOY_CLIENT_ID",
    "ENTRA_API_CLIENT_ID", "ENTRA_SPA_CLIENT_ID",
)


def valid_guid(value):
    try:
        return bool(UUID(value).int) and str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def validate(env):
    errors = []
    for key in (*GUID_KEYS, "AZURE_RESOURCE_GROUP", "AZURE_PREFIX",
                "ENTRA_ALLOWED_CLIENT_IDS", "DATABASE_ADMIN_PASSWORD", "DATABASE_APP_PASSWORD"):
        if not env.get(key, "").strip():
            errors.append(f"{key}: set a nonempty value in the selected GitHub environment.")
    for key in GUID_KEYS:
        if env.get(key) and not valid_guid(env[key]):
            errors.append(f"{key}: use a nonzero lowercase GUID in canonical hyphenated format.")
    if env.get("AZURE_PREFIX") and not re.fullmatch(r"[a-z][a-z0-9]{2,15}", env["AZURE_PREFIX"]):
        errors.append("AZURE_PREFIX: use 3-16 lowercase letters/digits, starting with a letter.")
    if env.get("AZURE_HOSTING", "appservice") not in {"containerapps", "appservice"}:
        errors.append("AZURE_HOSTING: choose containerapps or appservice.")
    if env.get("AZURE_APPSERVICE_SKU", "B1") not in {"B1", "B2", "B3", "S1", "S2", "S3", "P0v3", "P1v3", "P2v3", "P3v3"}:
        errors.append("AZURE_APPSERVICE_SKU: choose a supported Basic, Standard, or Premium v3 size.")
    if not re.fullmatch(r"Standard_[A-Za-z0-9_]+", env.get("AZURE_POSTGRES_SKU", "Standard_D2ads_v5")):
        errors.append("AZURE_POSTGRES_SKU: use an Azure PostgreSQL SKU name such as Standard_B2s.")
    if env.get("AZURE_POSTGRES_TIER", "GeneralPurpose") not in {"Burstable", "GeneralPurpose", "MemoryOptimized"}:
        errors.append("AZURE_POSTGRES_TIER: choose Burstable, GeneralPurpose, or MemoryOptimized.")
    if env.get("AZURE_POSTGRES_SERVER_NAME") and not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", env["AZURE_POSTGRES_SERVER_NAME"]
    ):
        errors.append("AZURE_POSTGRES_SERVER_NAME: use 3-63 lowercase letters/digits/hyphens, with alphanumeric ends.")
    if not re.fullmatch(r"[a-z][a-z0-9]+", env.get("AZURE_LOCATION", "centralus")):
        errors.append("AZURE_LOCATION: use a region code such as centralus, not a display name.")
    if env.get("AZURE_APPSERVICE_LOCATION") and not re.fullmatch(r"[a-z][a-z0-9]+", env["AZURE_APPSERVICE_LOCATION"]):
        errors.append("AZURE_APPSERVICE_LOCATION: use a region code such as centralus.")
    if env.get("AZURE_REGISTRY_NAME") and not re.fullmatch(r"[a-z0-9]{5,50}", env["AZURE_REGISTRY_NAME"]):
        errors.append("AZURE_REGISTRY_NAME: use 5-50 lowercase letters or digits.")
    if env.get("AZURE_WEBAPP_NAME") and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,58}[a-z0-9]", env["AZURE_WEBAPP_NAME"]):
        errors.append("AZURE_WEBAPP_NAME: use 2-60 lowercase letters/digits/hyphens, with alphanumeric ends.")
    group = env.get("AZURE_RESOURCE_GROUP", "")
    if group and (group != group.strip() or len(group) > 90 or group.endswith(".")
                  or not all(c.isalnum() or c in "_-.()" for c in group)):
        errors.append("AZURE_RESOURCE_GROUP: use an existing resource group name without surrounding spaces.")
    raw = env.get("ENTRA_ALLOWED_CLIENT_IDS", "")
    if raw.strip():
        clients = [v.strip() for v in raw.split(",")]
        if not all(valid_guid(v) for v in clients):
            errors.append("ENTRA_ALLOWED_CLIENT_IDS: use comma-separated GUIDs with no empty entries.")
        # Runtime checks are case-sensitive.
        if env.get("ENTRA_SPA_CLIENT_ID") not in clients:
            errors.append("ENTRA_ALLOWED_CLIENT_IDS: include ENTRA_SPA_CLIENT_ID with identical casing.")
    api, spa = env.get("ENTRA_API_CLIENT_ID"), env.get("ENTRA_SPA_CLIENT_ID")
    if api and spa and api.lower() == spa.lower():
        errors.append("ENTRA_API_CLIENT_ID / ENTRA_SPA_CLIENT_ID: use separate app registrations.")
    if env.get("DATABASE_APP_PASSWORD") and env.get("DATABASE_APP_PASSWORD") == env.get("DATABASE_ADMIN_PASSWORD"):
        errors.append("DATABASE_APP_PASSWORD: use a different password from DATABASE_ADMIN_PASSWORD.")
    if env.get("SEED_DEMO", "true").lower() not in {"true", "false"}:
        errors.append("SEED_DEMO: choose true or false.")
    return errors


def main():
    errors = validate(os.environ)
    if errors:
        print("Deployment configuration needs attention:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Preflight passed (offline configuration only; Azure access and capacity are not verified).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
