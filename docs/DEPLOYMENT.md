# Deploy your demo to Azure

[Back to the README](../README.md)

Use automated onboarding for a new tenant. Use the GitHub deployment workflow for later releases.

## Working Zava setup

| Component | Configuration |
| --- | --- |
| Resource group | `rg-healthclaimsportal-demo` |
| Web app | Linux App Service, `B1`, **Central US** (`centralus`) |
| Database | Private PostgreSQL 16, `Standard_D2ads_v5`, `GeneralPurpose`, **East US 2** (`eastus2`) |
| Registry, runtime identity, logs | East US 2 |
| Network | One VNet per region, bidirectional peering, private DNS links |

This profile is verified in Zava. Hosting quota varies by subscription, which is why the web app uses a separate region. Check availability in your destination subscription.

## Automated onboarding

### 1. Prepare access

- Install Python 3.12+, Azure CLI, and GitHub CLI (`gh`).
- Use a destination repo or fork with these workflows on `main`, Actions enabled, and repository administrator access.
- Have an existing dedicated resource group in the target subscription.
- Use an Entra administrator who can create apps, grant consent, and assign app roles, plus Azure Owner on the resource group or equivalent permissions. Global Administrator satisfies the Entra requirements.

For another tenant, use a separate repo or fork and a fresh checkout. Each repository's `azure-demo` environment targets one tenant; onboarding stops if existing destination settings conflict.

### 2. Sign in and run setup

From the repository folder, replace the uppercase placeholders. The example uses the working Zava region and size choices; `claimsnewdemo` is an example prefix.

```powershell
az login --tenant "TENANT_ID"
gh auth login --scopes workflow

python scripts/onboard_azure.py `
  --repo "OWNER/REPOSITORY" `
  --tenant "TENANT_ID" `
  --subscription "SUBSCRIPTION_ID" `
  --resource-group "YOUR_RESOURCE_GROUP" `
  --prefix "claimsnewdemo" `
  --location eastus2 `
  --hosting appservice `
  --appservice-location centralus `
  --appservice-sku B1 `
  --database-sku Standard_D2ads_v5 `
  --database-tier GeneralPurpose `
  --deploy
```

Use a unique prefix: 3â€“16 lowercase letters and digits, starting with a letter. Here, `--location` selects the foundation/database region; `--appservice-location` selects web hosting. Matching regions use one VNet. Different regions add the peered web VNet and DNS link.

The command:

1. Creates or reuses the API, SPA, and deployment registrations. It configures v2 tokens, `Claims.Access`, SPA consent, and Reader/Writer/Reviewer roles for the signed-in administrator. Use `--employee` for another demo user's object ID.
2. Creates the runtime managed identity and resource-group deployment access. Contributor provisions resources; the extra RBAC delegation permits only AcrPull assignments for that runtime identity.
3. Creates `azure-demo`, discovers the repo's actual OIDC subject, and configures federation, variables, and two separate random database secrets. GitHub uses OIDC without an Azure client secret or directory administration rights.
4. Runs offline validation, deploys the infrastructure and container, waits for readiness, then adds the returned HTTPS URLâ€”with its trailing `/`â€”to the SPA redirect URIs.

Initial administrator sign-ins and required tenant approvals remain interactive. Omit `--deploy` to configure identities and GitHub and run offline validation without provisioning hosting or PostgreSQL. Existing database secrets, approved clients, redirect URIs, and environment protections are preserved. New environments allow deployments from `main`.

### 3. Check the result

Open the reported URL, sign in, submit a fictitious claim, and reload. Follow [Check your demo](VALIDATION.md) for role and API checks. `/health/ready` checks the database and schema; browser sign-in needs its own test.

## Later releases and recovery

- **Redeploy:** wait for CI to pass, then run **Actions â†’ Deploy Azure demo â†’ Run workflow** on `main`. Leave `dry_run` checked for offline validation; uncheck it to deploy. Offline validation does not log in to Azure or prove capacity, policy, or sign-in.
- **Retry setup:** rerun the same onboarding command. Ignored `work/onboarding-state.json` holds identifiers and workflow IDs, never passwords or tokens. Configured registrations are reused even if their display names have an older prefix.
- **Finish the redirect:** if deployment succeeded but administrator sign-in expired, rerun the same command with `--finalize` instead of `--deploy`. It reads the existing deployment URL without redeploying. Use this after a manual deployment creates a new host too.

Keep the prefix, foundation region, and database name stable once data is stored. In Zava, `AZURE_POSTGRES_SERVER_NAME` is `zavaclaims2-pg-0b2ca611`; routine releases preserve it. Changing a region or server name does not migrate data. The workflow does not delete resources from an earlier hosting choice.

| Azure reports | Next step |
| --- | --- |
| App Service VM quota is zero | Choose an available hosting region with `--appservice-location`, or obtain quota. Basic/Standard/Premium v3 sizes still need native validation. |
| PostgreSQL `SkuNotAvailable` | Select an available `--database-sku` and matching `--database-tier`. |
| A failed, empty server's name remains reserved | Use `--database-server-name` for a deliberately new server. Keep populated databases on their existing name. |
| Container Apps network approval is pending | Resolve the approval or select App Service before deployment. |

Live preflight checks advertised PostgreSQL availability, known Container Apps restrictions, and native App Service plan validation. It does not automatically choose regions/SKUs or override policy. Advertised capacity can still fail during provisioning. Container Apps remains an alternative through `--hosting containerapps`; the CLI default is Container Apps/East US unless overridden.

## Manual setup reference

Use [Entra configuration](AUTH.md) for manual API/SPA setup. Create a deployment principal with resource-group Contributor and permission to assign AcrPull to the runtime identity. Its federated credential uses issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, and the **actual** subject from the repo's OIDC discovery workflow. Subjects can include immutable repository/owner IDs; do not guess them.

Set these variables in GitHub's `azure-demo` environment. Onboarding fills them for you:

| Variable | Meaning / Zava setting |
| --- | --- |
| `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | Destination IDs |
| `AZURE_DEPLOY_CLIENT_ID` | Deployment registration client ID |
| `AZURE_RESOURCE_GROUP`, `AZURE_PREFIX` | Dedicated group and unique prefix; Zava uses `rg-healthclaimsportal-demo` / `zavaclaims2` |
| `AZURE_LOCATION` | Foundation/database region; `eastus2` |
| `AZURE_HOSTING` | `appservice` |
| `AZURE_APPSERVICE_LOCATION`, `AZURE_APPSERVICE_SKU` | `centralus` / `B1` |
| `AZURE_POSTGRES_SKU`, `AZURE_POSTGRES_TIER` | `Standard_D2ads_v5` / `GeneralPurpose` |
| `AZURE_POSTGRES_SERVER_NAME` | Stable server name; optional override for new deployments |
| `ENTRA_API_CLIENT_ID`, `ENTRA_SPA_CLIENT_ID` | Separate API and browser client IDs |
| `ENTRA_ALLOWED_CLIENT_IDS` | Browser and approved agent client IDs, comma-separated |
| `SEED_DEMO` | `true` adds eight fictitious claims |

Add separate strong environment secrets: `DATABASE_ADMIN_PASSWORD` and `DATABASE_APP_PASSWORD`. Keep both stable across releases. Rotate them coherently in GitHub and hosting settings. Deployment uses temporary parameter files without logging their contents and removes them afterward.

## Operational boundaries

Use fictitious data only. This demo has one app instance, a single-zone database, seven-day backups, and 30-day log retention. Hosting, PostgreSQL, registry, logging, and cross-region traffic incur charges. Idle resources can still cost money.

The container runs as a non-root user. Managed identity pulls images from the authenticated Basic registry; its public endpoint remains enabled and admin login is disabled. PostgreSQL is private and requires TLS. App Service enforces HTTPS/TLS 1.2 and disables FTP/SCM basic publishing credentials.

At startup, a separate administrator connection runs migrations under an advisory lock, optionally seeds data, and configures `claims_app` with SELECT/INSERT/UPDATE access. The API user cannot delete claims, change schema, or manage roles. Bootstrap credentials are removed from the server process but remain in encrypted hosting settings for later startups. Restrict access to those settings. Larger deployments need controlled release migrations, scaling, recovery, and policy review.

## Logs and demo safeguards

JSON console events include a server-generated request ID; responses expose `X-Request-ID`. Logs omit bodies, queries, tokens, notes, and personal fields. Claim history stays in PostgreSQL and is not an immutable audit store.

App Service forwards `AppServiceConsoleLogs` to Log Analytics; Container Apps uses `ContainerAppConsoleLogs_CL`. Verify ingestion in your environment. Alerts are not preconfigured.

Defaults are 64 KiB per request body and 120 API requests/minute per client address per instance. Configure `MAX_REQUEST_BYTES` and `REQUESTS_PER_MINUTE` in hosting settings as needed. Health probes are exempt; proxies can share limits. This is a demo safeguard, not distributed abuse protection.

For rollback, redeploy a known-good image/commit after checking schema compatibility; database downgrade is not automatic. To retire the demo, preserve any required test data before removing its dedicated resources. Deployment workflows do not perform cleanup.
