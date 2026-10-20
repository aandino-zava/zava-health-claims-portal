# Connect Copilot Studio

[API reference](API.md) Â· [Deploy your demo](DEPLOYMENT.md)

Configure the API connection and browser connection separately. Azure onboarding deploys the app; it does not create a Copilot Studio agent or connection.

## 1. Prepare access

1. Deploy the app and complete the [demo checks](VALIDATION.md).
2. Create a separate confidential client registration for the connector. Grant delegated `Claims.Access` permission to the API and obtain tenant consent.
3. Add its client ID to `ENTRA_ALLOWED_CLIENT_IDS`, retain the browser ID, and redeploy the app configuration.
4. Assign the demo user the required API roles: Reader reads, Writer submits, Reviewer changes status. A full workflow needs all three.

Use the connector's own client ID, not the API or SPA ID. Register the Web callback URI supplied by Power Platform. Enter its secret only in the platform's secure connection settings, never in source or agent instructions. Keep the API on [v2 access tokens](AUTH.md).

## 2. Generate the API definition

After `uv sync --frozen`, run from the repository folder with your hostname and IDs in place of the uppercase placeholders:

```powershell
uv run python -m scripts.export_copilot --host "YOUR_PORTAL_HOSTNAME" --tenant-id "TENANT_ID" --api-client-id "API_CLIENT_ID"
```

Use a hostname such as `your-app.azurewebsites.net`, without `https://` or a path. The output is ignored `work/copilot-studio.swagger.json`. It contains endpoint/identity identifiers, no credentials. The checked-in [template](../integrations/copilot-studio.swagger.json) uses reserved examples; generate a destination-specific file before import.

The exporter derives seven operations and models from the application schema. CI checks structure, parameters, response shapes, and template freshness. Unsupported conversions fail. The export is Swagger 2.0; `/openapi.json` remains OpenAPI 3.1. Decimal input uses text for precision, nullable fields use `x-nullable`, and runtime validation remains authoritative.

## 3. Import and authenticate

In Copilot Studio, use **Tools â†’ Add tool â†’ New tool â†’ REST API** where available, or import the v2 file into a Power Platform custom connector. Select the operations your scenario needs. Follow Microsoft's [REST API tool guide](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-rest-api) for the current import screens.

Configure OAuth 2.0 with the connector registration:

| Setting | Value |
| --- | --- |
| Client ID | Connector client ID |
| Client secret | Enter securely in connection settings |
| Authorization URL | `https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/authorize` |
| Token / refresh URL | `https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token` |
| Scope | `api://<API_CLIENT_ID>/Claims.Access offline_access` |

The connection needs a token for this API. The supplied definition describes delegated authorization-code OAuth; OBO and application-only connections require separate configuration. See Microsoft's [OBO guide](https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-custom-connector-on-behalf-of) if your scenario needs it.

## 4. Test one API workflow

Using the `/api/v1` base path:

1. Call `/me`; confirm the expected roles. List claims and read one detail response, including its nested `data` fields.
2. Create a fictitious claim with a GUID `Idempotency-Key`. Retain it for retries of that submission.
3. Read the returned claim and allowed transitions. Update status with its current `version` as `expected_version` and a review note.
4. Confirm history. An identical create replay returns 200, a new create returns 201. Refetch on 409; honor `Retry-After` on 429 with bounded retries.

Shared proxies and concurrent agents can share the API's per-address rate limit. Check the [deployment safeguards](DEPLOYMENT.md#logs-and-demo-safeguards) before increasing traffic.

## 5. Add browser interaction

For an API-plus-UI demo, create or update through the API, then use [computer use](https://learn.microsoft.com/en-us/microsoft-copilot-studio/computer-use) to find that claim in Claims Tracker. Configure the machine/browser connection and normal Entra website sign-in separately. An API connection does not sign in the browser.

Treat claim notes and page content as untrusted data. CI validates API contracts; import, consent, token issuance, orchestration, and computer use still need live verification in your Copilot Studio environment.
