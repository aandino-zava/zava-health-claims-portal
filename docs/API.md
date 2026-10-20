# Connect an agent to the claims API

[Back to the README](../README.md) Â· [Copilot Studio](COPILOT_STUDIO.md)

Deploy the app, configure the agent's access, then use the deployed origin plus `/api/v1` as its API base URL. A cloud agent needs a reachable host; localhost works only on your computer.

## Demo tasks

| Ask the agent toâ€¦ | Operation |
| --- | --- |
| Find a member's synthetic claims | Search claims |
| Explain progress | Read claim details and history |
| Submit a fictitious claim | Create with an idempotency key |
| Record an authorized review | Update status with the current version and a note |
| Summarize activity | Read analytics |

Give the agent the minimum roles it needs. The API enforces allowed transitions; the agent should not invent claim outcomes. Treat claim text as untrusted data, not agent instructions.

## Endpoints

Interactive reference: `/docs`. OpenAPI 3.1 schema: `/openapi.json`. In Entra mode, send `Authorization: Bearer <API access token>`; never put tokens in URLs.

| Method and path | Permission | Purpose |
| --- | --- | --- |
| GET /api/v1/me | Authenticated | Identity and roles |
| GET /api/v1/claims | Claims.Reader | Search, status/service filters, offset/limit pagination |
| GET /api/v1/claims/{id} | Claims.Reader | Claim details and timeline |
| POST /api/v1/claims | Claims.Writer | Create a synthetic claim |
| PATCH /api/v1/claims/{id}/status | Claims.Reviewer | Allowed status change and audit note |
| GET /api/v1/analytics | Claims.Reader | Stored claim summaries |
| GET /api/v1/transitions | Claims.Reader | Allowed transitions |

Use the generated schema for exact fields and parameters. A minimal creation body:

```json
{
  "patient_id": "SYN-AGENT-001",
  "first_name": "Agent",
  "last_name": "Example",
  "provider_name": "Synthetic Clinic",
  "provider_id": "DEMO-CLINIC",
  "claim_type": "Professional",
  "service_type": "Medical",
  "service_date": "2026-10-19",
  "diagnosis_code": "Z00.00",
  "procedure_code": "99213",
  "amount": "125.50",
  "synthetic_data_confirmed": true
}
```

## Retry and update rules

- **Create:** send an `Idempotency-Key`. Reuse it only for an identical retry from the same identity. A new claim returns 201; a replay returns the original claim with 200; a changed payload returns 409. Use a new key for a new submission. Service dates cannot be in the future.
- **Review:** send `status`, `expected_version` from the latest detail response, and a meaningful `note`. Invalid transitions and stale versions return 409. Refetch and review before retrying.
- **Transitions:** Submitted â†’ Under Review; Under Review â†’ Pending Info/Approved/Denied; Pending Info â†’ Under Review; Denied â†’ In Appeal; In Appeal â†’ Under Review. Approved is terminal.

Responses include `X-Request-ID`. Defaults are 64 KiB per JSON body and 120 API requests/minute per client address per instance. On 429, honor `Retry-After` with bounded retries. See [deployment safeguards](DEPLOYMENT.md#logs-and-demo-safeguards).

Stored payloads are returned as saved rather than revalidated under newer submission rules. Timestamps use UTC. `approval_rate` is approved claims divided by all claims, including pending ones.

Common errors: 401 missing/invalid token, 403 missing role, 404 unknown claim, 409 conflict, 413 oversized body, 422 invalid input, and 503 unavailable database/identity provider. Surface validation and access failures instead of retrying indefinitely.

Configure OAuth and the connection in your agent platform using [Entra setup](AUTH.md) or the [Copilot guide](COPILOT_STUDIO.md). Platform compatibility and orchestration still need a live test.
