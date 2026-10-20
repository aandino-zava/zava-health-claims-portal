# Deploy your demo to Azure

[Back to the README](../README.md)

For the fastest local trial, use [Docker Compose](RUN-LOCALLY.md). Follow this guide when you need a hosted API for your agentic demo.

## Deployment path

1. Fork or copy this repository into your GitHub account.
2. Choose a resource group, region, and hosting option in your Azure subscription.
3. Run the administrator onboarding command below to create the identities and configure GitHub.
4. The command runs **Deploy Azure demo** with **dry_run checked** to validate configuration first.
5. Include `--deploy` to continue after validation, create Azure resources, and configure the returned sign-in redirect URI automatically.
6. Sign in and [check your demo](VALIDATION.md).

## Automated onboarding

Install Python 3.12+, Azure CLI, and GitHub CLI (`gh`), then sign in with `az login --tenant <TENANT_ID>` and `gh auth login --scopes workflow`. Run from the repository root after these scripts and workflows are on `main` in your destination repository. The account running setup needs permission to create app registrations and service principals, grant tenant consent to this custom API, assign employee app roles, and create resource-group role assignments. Global Administrator plus Azure Owner on the target resource group satisfies these prerequisites; use narrower administrator roles where your tenant permits. GitHub repository administrator access is required. The command cannot grant its operator these privileges.

```powershell
python scripts/onboard_azure.py --repo OWNER/REPOSITORY --tenant TENANT_ID --subscription SUBSCRIPTION_ID --resource-group RESOURCE_GROUP --prefix UNIQUE_PREFIX --location eastus --hosting containerapps --deploy
```

Omit `--deploy` to configure onboarding and run validation only. This still creates identity metadata, an Azure managed identity, and access assignments; it does not provision hosting or PostgreSQL. With `--deploy`, the command creates billable resources after validation passes. Choose `appservice` if that is your preferred hosting option before the first deployment.

If Azure rejects the default database size with `SkuNotAvailable`, select an available size explicitly, for example `--database-sku Standard_B2s --database-tier Burstable`. The command saves these values as GitHub environment variables and reuses them on subsequent runs. Changing database size changes Azure costs. Capability discovery reports what Azure advertises; actual provisioning can still reject a listed size because of capacity or subscription restrictions.

Failed server creation can leave a name reserved after its ARM resource disappears. For an empty environment only, use `--database-server-name <fresh-unique-name>` to deliberately create a new server. The name is saved for later releases. Changing this setting in a populated environment creates a different database; it does not migrate existing claims. Keep the selected name stable once data is stored.

App Service defaults to B1. If your subscription has zero quota for Basic, select a permitted size with `--appservice-sku P0v3`, for example, and require successful ARM validation. The deployment identity retains its resource-group scope. A higher hosting tier changes ongoing costs. Supported sizes are B1-B3, S1-S3, and P0v3-P3v3.

Both onboarding and real GitHub deployments also submit a small, secret-free App Service plan template to ARM **validation only** before provisioning. This catches per-size VM quotas that the regional usage summary can misrepresent. It creates no hosting resources and uses the deployment identity's existing resource-group permissions. If validation reports a VM quota of zero, request at least one instance of the selected size through Azure support before rerunning deployment. Selecting a larger size is not a substitute for a successful native validation.

The command:

- Creates or reuses three single-tenant registrations named `<prefix>-claims-api`, `<prefix>-claims-spa`, and `<prefix>-github-deploy`. It configures v2 API tokens, `Claims.Access`, and the three claim roles; grants SPA consent; and assigns Reader, Writer, and Reviewer to the signed-in administrator (or the object ID supplied with `--employee`).
- Creates `azure-demo` if missing, restricting a new environment to deployments from `main`. Existing protection and approval rules are preserved, so a protected environment may wait for your review in Actions.
- Runs **Discover Azure OIDC subject** to obtain the exact environment subject, including immutable IDs where applicable. Only selected non-secret claims are logged. It validates the repository IDs, issuer, audience, environment, and branch before creating federation. It does not guess the subject from repository age or change the repository's OIDC settings.
- Creates the runtime managed identity and gives the deployment principal resource-group Contributor access. Its additional RBAC Administrator delegation is conditioned on **AcrPull for that runtime principal only**, for both assignment creation and deletion. The deployment identity receives no Microsoft Graph application permission or client secret.
- Writes deployment variables and creates separate random database passwords directly through `gh secret set` stdin. Existing secrets are preserved, and passwords are never stored in onboarding state. Existing approved agent clients and the seed preference are preserved.
- Runs offline validation, optionally waits for deployment, then uses the local administrator session to add the actual HTTPS portal origin with a trailing `/` to the SPA. Existing redirect URIs are preserved.

State and workflow run IDs are saved in ignored `work/onboarding-state.json`; it contains identifiers, not passwords or tokens. Rerun with the same arguments to recover from partial setup. Registrations already referenced by the GitHub environment's client IDs are reused, even when their display names have an earlier infrastructure prefix. A configured client ID missing from the signed-in tenant stops setup instead of silently creating a replacement. Duplicate registration names and conflicting prefix/hosting/client settings stop setup for review. The command does not remove old-tenant identities or resources, alter existing environment protections, rotate existing database passwords, or grant directory administration to GitHub.

If deployment succeeded but the local session expired before redirect configuration, sign in again and run the same command with `--finalize` instead of `--deploy`. This reads the existing `claims-app` deployment output and completes the redirect without redeploying infrastructure. Normal later releases use **Deploy Azure demo**; the host name and redirect stay stable when the prefix and hosting option are unchanged. Changing the host requires rerunning `--finalize`.

The initial local administrator sign-ins and any tenant-required approval remain interactive. This is the bootstrap trust boundary: an unconfigured GitHub repository cannot authorize itself to administer your tenant.

Real deployment also checks the subscription's advertised PostgreSQL 16 availability for the selected database size before provisioning. For Container Apps, it detects a pending `AllowBringYourOwnPublicIpAddress` feature approval that can block the environment network. The same check runs locally before `--deploy` changes setup and in GitHub after OIDC login. These checks catch known service restrictions; they do not guarantee regional capacity or replace ARM policy evaluation. Offline `dry_run` remains unchanged. If PostgreSQL reports regional restrictions, request access through Azure support or explicitly choose an available region. A feature requiring Microsoft approval cannot be approved by this script.

## Manual alternative

The following settings and steps provide the equivalent manual route and help troubleshoot a partial onboarding run.

## Prerequisites

- A target Azure public-cloud tenant, subscription, existing resource group and a 3-16 character lowercase alphanumeric prefix starting with a letter.
- East US (`eastus`) is the default; verify service availability, PostgreSQL SKU capacity and quotas in the selected subscription.
- The API and SPA registrations from [AUTH.md](AUTH.md).
- A deployment app/service principal with a GitHub federated identity credential: issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, and the repository's exact subject ending in `:environment:azure-demo`. New GitHub repositories use the immutable format `repo:OWNER@OWNER_ID/REPOSITORY@REPOSITORY_ID:environment:azure-demo`; older repositories may use `repo:OWNER/REPOSITORY:environment:azure-demo`. Check the actual subject reported by `azure/login` or the repository's OIDC settings. Replace all names/IDs for each fork. See [GitHub's OIDC reference](https://docs.github.com/en/actions/reference/security/oidc).
- Deployment identity permissions scoped to the resource group: Contributor plus permission to create the runtime AcrPull role assignment (for example Role Based Access Control Administrator). Apply your organization's narrower role-assignment conditions if required. Creating these identities and permissions is an administrator setup step.

Create a GitHub environment named `azure-demo`. If you restrict deployment branches, allow the branch you intend to run; environment approval rules also apply to validation-only runs. Configure required reviewers if desired, and add these variables:

| Variable | Meaning |
| --- | --- |
| AZURE_TENANT_ID | Destination tenant GUID |
| AZURE_SUBSCRIPTION_ID | Destination subscription GUID |
| AZURE_DEPLOY_CLIENT_ID | GitHub deployment identity client GUID |
| AZURE_RESOURCE_GROUP | Existing target resource group |
| AZURE_LOCATION | `eastus` unless overridden |
| AZURE_HOSTING | `containerapps` (default) or `appservice`; choose before initial deployment |
| AZURE_APPSERVICE_SKU | Optional App Service size; default `B1`, or a supported Standard/Premium v3 size with available quota |
| AZURE_PREFIX | Unique deployment prefix, e.g. `claimsdev` |
| AZURE_POSTGRES_SKU | Optional database size; default `Standard_B1ms`, e.g. `Standard_B2s` where B1ms is unavailable |
| AZURE_POSTGRES_TIER | Optional `Burstable` (default), `GeneralPurpose`, or `MemoryOptimized`; must match the size |
| AZURE_POSTGRES_SERVER_NAME | Optional explicit PostgreSQL server name; keep stable after data is stored |
| ENTRA_API_CLIENT_ID | API registration client GUID |
| ENTRA_SPA_CLIENT_ID | Browser registration client GUID |
| ENTRA_ALLOWED_CLIENT_IDS | SPA and approved agent client GUIDs, comma-separated |
| SEED_DEMO | Optional `true` (default) or `false`; include eight fictitious example claims |

Add two environment secrets: `DATABASE_ADMIN_PASSWORD` for migrations/setup and a different `DATABASE_APP_PASSWORD` for the restricted application user. Use strong passwords satisfying Azure requirements; never commit them. Existing deployments adopting this version must add the new application secret before running the workflow. The workflow writes temporary ARM parameter files without printing them and removes them at the end. Keep both passwords stable between deployments unless intentionally rotating them. The startup setup reapplies the runtime password and grants on restart; rotate both values coherently in GitHub and the deployed settings.

## Validate first (no Azure resources created)

1. Set the environment variables and secret listed above. Use separate API and browser client IDs; include the browser client ID in the allowed-client list. Use canonical GUIDs and a region code such as `eastus`.
2. Open Actions > **Deploy Azure demo** > Run workflow. Select your intended branch and leave **dry_run checked** (the default).
3. Read the run summary. Fix any named settings and repeat until the checks pass.

This mode checks configuration, repository structure, application tests, lint, JavaScript syntax, Bicep compilation, and generated parameter contracts. It does not sign in to Azure, deploy resources, or build/push a registry image. GitHub Actions runner usage still applies.

Parameter generation uses explicitly fictitious infrastructure outputs in `work/validation`, not outputs from an existing deployment. It substitutes dummy passwords and removes generated parameter files afterward. The configured database secrets are checked for presence and separation only; validation-only mode does not prove Azure will accept its password policy.

A passing result **does not verify** registration existence, tenant/subscription membership, federation, permissions, regional capacity, quotas, policies, or sign-in. It is an offline preparation check, not an ARM what-if or a guarantee of deployment success. Application tests here use SQLite; the separate CI workflow also runs PostgreSQL integration and a container readiness check.

## Deploy after validation

1. Confirm application CI is green for the commit being deployed.
2. Run Actions > **Deploy Azure demo** > Run workflow on the intended branch and **uncheck dry_run**. This authorizes the workflow to create/update billable Azure resources. The same validation checks run before Azure login.
3. The workflow provisions a VNet, private PostgreSQL Flexible Server/database, private DNS, Container Registry, managed identity and Log Analytics. It creates either a Container Apps environment or a Linux App Service plan (B1 by default, configurable) and web app, then builds the image and deploys the application.
4. The onboarding command configures the reported SPA redirect URI automatically. For a manual workflow run against a new host, run onboarding with `--finalize`, or configure it as described in AUTH.md.
5. Sign in with an assigned demo employee; submit a synthetic claim and confirm it survives reload. Verify a reader cannot submit/review, an unassigned user cannot read data, and an approved agent can call the API.

`/health/ready` succeeding verifies database connectivity/schema, not Entra sign-in. The root page, static assets, health endpoints, authentication configuration and API schema are public; claim data endpoints require authorization.

## Operational boundaries

**Registry security/cost tradeoff:** The templates use a Basic registry with a public endpoint and authenticated access; admin login is disabled. This reduces registry cost compared with a Premium registry using private networking, but increases network exposure. If your organization prohibits public registry endpoints, use an approved exception or adapt the infrastructure and build path for private access. The workflow does not create policy exemptions. PostgreSQL uses private networking.

Azure charges apply to hosting, PostgreSQL, the registry, and configured logging/network services. App Service Basic, PostgreSQL, and the registry have ongoing costs even when the demo is idle. Container Apps can scale application replicas to zero, but that does not remove the other service costs. Check current prices, regional capacity, quotas, and policies in your target subscription before deployment.

The container runs as a non-root user. Runtime registry pulls use managed identity. The database has private network access, and the connection requires TLS. Database credentials are Container Apps secrets or encrypted App Service settings. At startup, the administrator connection runs migrations and optional seeding, then provisions `claims_app` with SELECT, INSERT, and UPDATE on the claims table. That role cannot delete claims, change the schema, or manage roles. The server process receives the restricted connection; the bootstrap connection variable is removed before the server is executed. The administrator credential remains configured at the hosting control plane for future startups, so restrict access to hosting settings. This is not a passwordless design. Schema migration runs under a PostgreSQL advisory lock on startup; this demo uses one instance. For larger deployments, move migrations into a controlled release job and review connection pooling, scaling, audit retention and backup recovery. App Service uses a dedicated VNet integration subnet, HTTPS only, TLS 1.2 minimum, and disabled FTP/SCM basic publishing credentials.

The template uses a small single-zone PostgreSQL server, 7-day backups and 30-day log retention. It is a demonstration configuration, not a production healthcare baseline. Tenant-specific policies may require further controls. There is no automated clinical or insurance decision making.

To deploy another environment, reuse the repository with a separate resource group, prefix, identities and GitHub environment configuration. The application requires no changes to business logic. Both Container Apps and App Service templates are included. Select the hosting mode before initial deployment; changing the mode does not automatically delete resources from the previous mode. Provisioning depends on subscription quota and regional availability.

## Logs and demo safeguards

Application events are JSON on stdout with a server-generated request ID. They record request outcome/duration and claim-operation events, omitting bodies, query strings, tokens, review notes, and personal fields. Responses include `X-Request-ID`. Claim history remains in PostgreSQL and is not an immutable external audit store.

Container Apps sends console output to the provisioned Log Analytics workspace. App Service enables container logging and forwards `AppServiceConsoleLogs` to that workspace. Ingestion charges apply. Verify delivery after deployment before relying on it; alerts are not preconfigured. For App Service, use Logs to inspect `AppServiceConsoleLogs`; for Container Apps, inspect `ContainerAppConsoleLogs_CL`.

The API limits bodies to 64 KiB and requests to 120/minute per client address per instance by default. Limits are configurable with `MAX_REQUEST_BYTES` and `REQUESTS_PER_MINUTE` in hosting settings. Health probes are exempt. Proxy/NAT users can share a limit; verify trusted-proxy settings for your host. This is a demo safeguard, not a distributed gateway or DDoS protection.

For rollback, redeploy a previous known-good image/commit after checking schema compatibility. No automatic database downgrade is attempted. Remove only this demo's dedicated resource group when retiring it, after preserving any required test data; resource deletion is not performed by these workflows.

