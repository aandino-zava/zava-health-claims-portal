# Check your demo

[Back to the README](../README.md) Â· [Deployment](DEPLOYMENT.md)

Check the whole workflow. A successful deployment or health response does not establish browser sign-in or agent access.

## Automated checks

| Check | What it establishes |
| --- | --- |
| Repository checks | Required guides, local link paths, balanced code fences, startup syntax. Link anchors and prose accuracy need review. |
| Application and signed-token tests | Claim rules, validation, retries, filtering, totals, authorization, readiness, limits, and diagnostic redaction. |
| PostgreSQL integration | Migrations, persistence, aggregates, restricted-role read/write/review, and denied deletion/schema/role/migration-metadata access. |
| Frontend and API contracts | JavaScript syntax, escaping, error handling, seven-operation Copilot export, and template freshness. |
| Infrastructure and container checks | Bicep compilation, parameter contracts, deployment guards, image build, fixable high/critical vulnerability scan, and container readiness. |

The [CI workflow](../.github/workflows/ci.yml) also verifies that bootstrap credentials are removed before server execution and reports combined Python branch coverage. Coverage describes exercised code; scenario testing is still required.

**Deploy Azure demo** with `dry_run` checked runs offline validation. It does not log in to Azure, build an image, provision resources, or prove quota and policy acceptance. Real deployment adds live preflight and a database readiness check.

## Verified in Zava

On October 20, 2026, the [Azure deployment](https://github.com/aandino-zava/zava-health-claims-portal/actions/runs/39369414180) succeeded with App Service B1 in Central US and private PostgreSQL 16 in East US 2. The following checks passed:

- Database readiness and Entra tenant/SPA configuration.
- HTTP 401 for an unauthenticated `/api/v1/claims` request.
- Work-account browser sign-in and loading the eight seeded claims.
- Submission of a fictitious claim and retrieval of that same claim after a full page reload.
- Stored claim details and the reviewer controls were visible.

The unused East US VNet and three security groups were removed afterward. Live readiness, the three Entra registrations, and the current/rollback images were verified intact.

## Still to verify

Reader-only and unassigned-user isolation, a live reviewer status update, sign-out, and Log Analytics event delivery need scenario checks in the target environment. Copilot Studio/Foundry import, authentication, orchestration, and computer use remain unverified. A clean onboarding run against a second tenant has not been performed.

Load, failover, backup recovery, and a complete automated browser sign-in suite are outside the current evidence.

## Repeat and record acceptance

1. Sign in with an assigned work account. Confirm Dashboard and Claims Tracker load.
2. Submit fictitious member/provider details. Record the returned claim ID.
3. Open the claim, record a permitted status change with a test note, and reload. Confirm the record and history persist, and Analytics updates.
4. Call `/health/ready`; expect `ready`. Call `/api/v1/claims` without a token; expect 401.
5. Check that Reader alone cannot submit/review and that an unassigned identity cannot read claims. Confirm each permitted role works independently.
6. Match a response's `X-Request-ID` to its JSON event in Log Analytics. Test your agent's allowed and rejected operations through its actual platform.

Record the date, environment, deployed commit, workflow URL, claim ID, observed results, and any open items. Local mode supplies all roles and bypasses Entra, so it cannot establish tenant authentication or role isolation.
