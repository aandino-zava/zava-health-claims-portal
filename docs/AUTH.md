# Entra configuration

Create two single-tenant app registrations in the destination tenant. Use different client IDs for the API and the browser SPA. No browser client secret is needed.

The [automated onboarding command](DEPLOYMENT.md#automated-onboarding) creates these registrations, grants SPA consent, assigns your demo roles, and configures the deployed redirect URI. The instructions below describe the equivalent manual configuration.

## API registration

1. Set the application ID URI to `api://<API_CLIENT_ID>`.
2. Expose delegated scope `Claims.Access` and set `api.requestedAccessTokenVersion` to `2` in the manifest.
3. Define enabled app roles `Claims.Reader`, `Claims.Writer`, and `Claims.Reviewer`, each allowing Users/Groups and Applications. Use unique GUIDs for their role IDs.
4. Assign the required roles to demo employees through the API enterprise application. Roles are independent: a reviewer normally needs Reader as well; someone filing claims normally needs Reader and Writer.

## Browser registration

1. Add a Single-page application platform, with redirect URI exactly the deployed portal origin followed by `/`.
2. Add delegated permission to the API's `Claims.Access` scope and obtain required tenant consent.
3. Include this SPA client ID in `ENTRA_ALLOWED_CLIENT_IDS`.
4. Set the GitHub environment variables described in DEPLOYMENT.md.

The first deployment reports the portal URL for your chosen hosting service. Add that exact redirect URI before attempting sign-in. The UI uses MSAL authorization code with PKCE; MSAL caches tokens in sessionStorage for the browser tab. The server validates signature, expiry, issuer, audience, tenant, authorized client and required role. Delegated tokens must also carry `Claims.Access`.

## Agent clients

Register each authorized agent client separately. Assign only its necessary API application roles, grant administrator consent, and add its client ID to the comma-separated allowlist. Request a token for `api://<API_CLIENT_ID>/.default` using a supported confidential-client flow. Prefer managed/federated identity where the chosen agent platform supports it. Do not put client secrets in source code or browser code.

Delegated agent calls need `Claims.Access` plus the signed-in user's app roles. An application-only token needs application roles. Configure the agent platform to call the same `/api/v1` endpoints as the browser; the application does not require an AI model.

Live tenant consent, token issuance, role assignment, sign-in and sign-out must be verified in the chosen tenant after deployment. Unit tests with locally signed tokens do not establish that the tenant is configured correctly.
