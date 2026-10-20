# Check your demo

[Back to the README](../README.md) · [Deployment](DEPLOYMENT.md)

Use these checks after setting up your own environment. A successful deployment or health check alone does not verify sign-in or agent access.

## Before deployment

Run **Deploy Azure demo** with **dry_run checked**. Resolve the configuration and repository errors it reports before requesting a real deployment. This is an offline check; it does not establish access to your Azure environment.

For Copilot integration, CI also checks the generated v2 definition against the API routes, parameters, and response models. Follow [Connect Copilot Studio](COPILOT_STUDIO.md) for the separate import, OAuth, and browser checks in your target environment.

## Try the browser workflow

1. Open the portal. In Azure, sign in with an assigned work account; local mode supplies a demo identity.
2. Confirm the Dashboard and Claims Tracker load.
3. Submit a claim using fictitious member and provider details.
4. Open its details and record a permitted status change with a test note.
5. Reload the page and confirm the claim, status, and history remain.
6. Check that Analytics reflects the stored claims.
7. Confirm a request ID appears in response headers and corresponding JSON events reach your Log Analytics workspace.

## Check API access

- Confirm /health/ready returns a ready response.
- In Entra mode, call /api/v1/claims without a token and expect HTTP 401.
- Confirm an assigned reader can read but cannot submit or review without the corresponding roles.
- Confirm an unauthorized identity cannot read claims.
- Connect your agent using [the API guide](API.md). Verify its permitted operations and rejected operations with synthetic data.

Local development bypasses real sign-in, so it cannot validate your Entra configuration. Test agent authentication through the actual platform you intend to demonstrate.

## Automated checks

Repository checks catch missing guides, unexpected document headings, obvious misplaced Python content, broken local link paths, and startup syntax problems. These are structural checks, not a review of documentation accuracy or link anchors.

The [CI workflow](../.github/workflows/ci.yml) runs application and signed-token tests, PostgreSQL integration, JavaScript syntax checks, Bicep compilation, a Docker build, and a container readiness check using separate bootstrap/runtime database users, plus a scan for fixable high/critical image vulnerabilities. Deployment-tool tests cover invalid configuration, client-list consistency, secret-value redaction, parameter contracts for both hosting choices, and validation-only workflow guards.

Tests cover claim creation, duplicate-request handling, filtering, aggregates, input validation, authorization, and status updates. PostgreSQL integration applies migrations and checks basic persistence and aggregation.

These checks do not replace browser regression tests, load tests, backup recovery exercises, or verification of your own subscription policies and identity configuration. Copilot/Foundry integration must be configured and tested separately.

PostgreSQL tests prove the restricted role can create/read/review claims and is denied deletion, schema changes, migration metadata access, and role creation. Failure-path tests cover database readiness, throttling, oversized streamed bodies, diagnostic redaction, and removal of bootstrap credentials before server execution. Frontend tests exercise escaping of agent-provided text and API error handling. These focused tests do not substitute for a complete automated browser sign-in suite.

CI prints a combined Python branch-coverage report after PostgreSQL integration. It reports exercised code; it does not certify correctness or replace the scenario checks above.
