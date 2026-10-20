# Entra configuration

[Back to the README](../README.md) Â· [Deployment](DEPLOYMENT.md)

Start with [automated onboarding](DEPLOYMENT.md#automated-onboarding). It creates separate single-tenant API, browser SPA, and deployment registrations; grants consent and demo roles; configures GitHub OIDC; and sets the deployed redirect URL. The browser needs no client secret.

Use the steps below for manual setup or troubleshooting.

## API registration

1. Set the application ID URI to `api://<API_CLIENT_ID>`.
2. Expose delegated scope `Claims.Access`. Set `api.requestedAccessTokenVersion` to `2`.
3. Define enabled `Claims.Reader`, `Claims.Writer`, and `Claims.Reviewer` app roles with unique GUIDs and Users/Groups plus Applications allowed.
4. Assign demo users their roles through the API enterprise application. Roles are independent: readers read, writers submit, and reviewers change status. A full browser workflow needs all three.

## Browser registration

1. Add the Single-page application platform with the exact HTTPS portal origin followed by `/` as its redirect URI.
2. Grant delegated access to `Claims.Access` and the required tenant consent.
3. Include the SPA client ID in `ENTRA_ALLOWED_CLIENT_IDS` and set the [deployment variables](DEPLOYMENT.md#manual-setup-reference).

Onboarding sets the returned redirect automatically. For a new host deployed manually, use onboarding with `--finalize` or add the exact URI yourself.

The UI uses MSAL authorization code with PKCE and tab-scoped `sessionStorage`. The API validates signature, expiry, issuer, audience, tenant, client allowlist, and role. Delegated tokens also need `Claims.Access`. Claim data is authorized; the root page, assets, health endpoints, authentication configuration, and API schema are public.

## Agent clients

Register each agent client separately and add its client ID to the allowlist. Delegated calls need `Claims.Access` and the user's app roles. Application-only calls need assigned API application roles, administrator consent, and a token for `api://<API_CLIENT_ID>/.default`.

Prefer managed or federated identity where the agent platform supports it. Keep client secrets out of source, browser code, and agent instructions. [Copilot Studio](COPILOT_STUDIO.md) has its own connector/client setup; Azure onboarding does not create that connection.

Test consent, token issuance, role isolation, sign-in, and sign-out in the receiving tenant. Locally signed test tokens cannot establish that configuration.
