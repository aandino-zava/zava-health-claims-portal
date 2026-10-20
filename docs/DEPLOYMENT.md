# Deploy your demo to Azure

[Back to the README](../README.md)

For the fastest local trial, use [Docker Compose](RUN-LOCALLY.md). Follow this guide when you need a hosted API for your agentic demo.

## Deployment path

1. Fork or copy this repository into your GitHub account.
2. Choose a resource group, region, and hosting option in your Azure subscription.
3. Configure Entra sign-in and the GitHub deployment identity using the prerequisites below.
4. Set the GitHub environment variables and database secret.
5. Run **Deploy Azure demo** with **dry_run checked** to validate configuration first.
6. When validation passes, run it again with **dry_run unchecked** to create resources. Configure the returned sign-in redirect URL and [check your demo](VALIDATION.md).

This is a parameterized deployment, not a one-click setup: identity permissions and subscription policies require preparation.

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
| AZURE_PREFIX | Unique deployment prefix, e.g. `claimsdev` |
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
3. The workflow provisions a VNet, private PostgreSQL Flexible Server/database, private DNS, Container Registry, managed identity and Log Analytics. It creates either a Container Apps environment or a Linux App Service B1 plan and web app, then builds the image and deploys the application.
4. Read the reported URL in the workflow summary and configure the SPA redirect URI as described in AUTH.md.
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
