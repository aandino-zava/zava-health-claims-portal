# Connect Copilot Studio

[API reference](API.md) · [Deploy your demo](DEPLOYMENT.md)

Configure the API connection and browser automation separately. Azure deployment provides the app; it does not create a Copilot Studio agent or connection.

## 1. Prepare access

1. Deploy the app and complete [Check your demo](VALIDATION.md).
2. Keep the API registration configured for v2 access tokens as described in [Entra setup](AUTH.md).
3. Create a separate confidential client registration for the connector. Give it delegated permission to the API's `Claims.Access` scope and obtain the required consent.
4. Add that connector client ID to `ENTRA_ALLOWED_CLIENT_IDS`, retaining the browser client ID, and redeploy the app configuration.
5. Assign the demo user the API roles needed for the scenario. Reader reads; Writer submits; Reviewer changes status. A full workflow normally needs all three independent roles.

The connector client ID differs from the API ID and browser SPA ID. Register the Web callback URI supplied by Power Platform on the connector registration. Enter its client secret only in the connector's secure authentication settings, never in a definition file or agent instructions.

## 2. Generate your definition

From the repository folder, after `uv sync --frozen`, run:

```powershell
uv run python -m scripts.export_copilot --host "<your-portal-hostname>" --tenant-id "<your-tenant-guid>" --api-client-id "<your-api-registration-client-guid>"
```

Use just the hostname, such as `your-app.azurewebsites.net`, without `https://` or a path. Output goes to `work/copilot-studio.swagger.json`, which Git ignores. It contains endpoint and public identity identifiers, but no credentials.

The checked-in [template](../integrations/copilot-studio.swagger.json) uses reserved examples. Generate your own file before importing it. The exporter derives all seven operations and their models from the live application schema. CI checks Swagger 2.0 structure, operation/parameter consistency, real API response shapes, and template freshness. Unsupported schema changes fail rather than silently losing fields.

The standard `/openapi.json` remains OpenAPI 3.1. The export uses v2 representations: decimal input is text for precision; nullable fields use `x-nullable`. Runtime validation remains authoritative for dates, amounts, transitions, and permissions.

## 3. Import and authenticate

Use **Add tool > REST API** in Copilot Studio where available, or import the v2 definition into a Power Platform custom connector and add its actions to the agent. Select the operations your scenario needs.

Configure OAuth 2.0 using the connector registration from step 1:

| Setting | Value |
| --- | --- |
| Client ID | Connector registration client ID |
| Client secret | Enter securely in platform connection settings |
| Authorization URL | `https://login.microsoftonline.com/<tenant-guid>/oauth2/v2.0/authorize` |
| Token / refresh URL | `https://login.microsoftonline.com/<tenant-guid>/oauth2/v2.0/token` |
| Scope | `api://<API-client-guid>/Claims.Access offline_access` |

The definition includes endpoints and scopes. Follow the connection UI for credential entry and callback configuration. The connection needs a token for this API, rather than a token issued for Microsoft Graph or another resource.

See Microsoft's [REST API tool guide](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-rest-api) and [Entra custom connector/OBO guide](https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-custom-connector-on-behalf-of). Availability and UI vary. The supplied file describes delegated authorization-code OAuth; it does not preconfigure OBO or an application-only connection.

## 4. Prove one API workflow

1. Call `/me` through the connection and confirm the expected API roles.
2. List claims and get one claim's details. Confirm nested fields such as `data.patient_id`, `data.diagnosis_code`, and `data.provider_id` are available for mapping.
3. Create one fictitious claim. Bind a GUID to `Idempotency-Key` and retain it for retries of that submission; do not generate a new key for each retry.
4. Read the returned claim and allowed transitions. Submit a reviewer update using its current `version` as `expected_version`.
5. Confirm the status and history. A replayed create returns 200; a new create returns 201. On 409, inspect/refetch before retrying. On 429, honor `Retry-After` with bounded retries.

Defaults are 120 API requests/minute per client address per instance and 64 KiB per request body. Shared proxies/concurrent agents can share a limit. Tune hosting settings after measuring your demo workload; see [deployment safeguards](DEPLOYMENT.md#logs-and-demo-safeguards).

## 5. Add browser interaction

For an API-plus-UI demo, create or update a claim through the API, then use [computer use](https://learn.microsoft.com/en-us/microsoft-copilot-studio/computer-use) to open Claims Tracker, search for the returned claim ID, and verify the result. Configure the machine/browser connection and normal Entra website sign-in separately; the API connection does not automatically sign in the browser.

The portal's screens and controls remain available. Treat claim notes and app content as untrusted data, separate from agent instructions.

CI validates schemas and API contracts. Import, consent, token issuance, orchestration, website sign-in, and computer use still require verification in your chosen Copilot Studio environment.
