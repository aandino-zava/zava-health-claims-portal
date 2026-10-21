# Connect the Medical Claims Concierge

The optional connection applies a Medical Director decision to an explicitly bound **fictional** portal claim. The agent keeps its read tools and Gatekeeper submission tool. Azure AI Search supplies document context; it cannot identify a portal claim or authorize an update.

## How a decision reaches the portal

1. The Gatekeeper independently checks protected evidence and versioned policy in Dataverse and saves an evaluation.
2. The existing review flow obtains a native Approval, verifies the assigned reviewer and rechecks the protected facts.
3. For an explicitly portal-bound case, the flow saves `PortalUpdatePending`. Other cases continue through the existing simulator.
4. The portal's existing App Service reads this durable queue every 20 seconds using its managed identity. It independently reads the actual native Approval and response, verifies the reviewer, evaluation link and eligibility, and checks the current evidence, policy and portal claim.
5. One version-checked database update changes the fictional claim and stores its operation receipt in the same transaction. A separate read confirms persistence before the portal records `PortalConfirmed` in Dataverse.

An appeal saying that attachments exist is not evidence that they exist. Claim bindings use exact claim ID, member ID, procedure, service date, version and synthetic-data flag. Names and search snippets are never matching keys.

## Configure a destination

Use App Service with Always On and the existing portal runtime managed identity. This polling connection is not configured for scale-to-zero Container Apps. No callback secret or public write endpoint is added.

In the intended Dataverse environment, create an application user for that managed identity and assign the dedicated **Zava Claims Portal Worker** role from the concierge solution. It reads policy, evidence, evaluations, native Approvals and Approval responses, and updates evaluation completion. It cannot change policy, evidence or Approval records. Keep the agent audience and Medical Director configuration restricted.

Set the portal deployment environment's `CONCIERGE_CONFIG_JSON` variable with destination-specific values:

```json
{
  "enabled": true,
  "dataverseUrl": "https://YOUR_ORG.crm.dynamics.com/",
  "identityClientId": "MANAGED_IDENTITY_CLIENT_ID",
  "reviewerObjectId": "MEDICAL_DIRECTOR_ENTRA_OBJECT_ID",
  "reviewerUserId": "MEDICAL_DIRECTOR_DATAVERSE_USER_ID",
  "allowedClaimIds": "EXACT_FICTIONAL_PORTAL_CLAIM_ID"
}
```

These are identifiers, not credentials. Keep completed destination configuration out of public source. The App Service template maps them to the `CONCIERGE_*` application settings; omitted configuration disables the connection.

An authorized evidence maintainer must put a `portalBinding` object in the protected claim snapshot. It contains exactly `claimId`, `memberId`, `cptCode`, `serviceDate`, `version`, `status` and `synthetic`. Capture those values from the intended fictional portal claim before evaluation; never let the agent choose or edit the binding. The portal ID must also appear in `allowedClaimIds`.

The review request must explicitly explain that approval or denial can update that fictional portal record. Approval requires verified eligibility. Denial still requires an authenticated human decision. An information request or escalation does not change portal status through this connection.

After a portal status change, have the authorized evidence maintainer refresh the protected binding before another evaluation. The original snapshot becomes stale, so a repeated approval cannot silently apply to the newer claim version.

## Verify and operate

Complete a genuine Medical Director Approval, then verify the portal status and timeline, persisted version, operation receipt and Dataverse `PortalConfirmed` result. Do not treat a successful flow or `PortalUpdatePending` as proof of a portal update.

The focused tests cover genuine-proof requirements, wrong reviewer/claim binding, missing Approval response, changed evidence/policy, stale portal state, ineligible approval, expiry, duplicate processing and lost acknowledgements. They use simulated identity records; genuine native approval and managed-identity access require destination acceptance.

Unavailable downstream reads leave the durable decision pending. A failed business check produces `PortalUpdateBlocked` with a reason. A stored receipt reconciles a lost acknowledgement without another claim update. Check the redacted `concierge_*` application events for operational failures.

To pause the connection, set `CONCIERGE_ENABLED=false` in the App Service configuration and set `enabled` to false in the deployment variable. Existing decisions and receipts remain available. There is no automatic reversal of a completed decision.

This is a single-reviewer fictional-data demonstration. Dataverse and PostgreSQL are separate transactions; snapshot checks do not create a cross-service lock. Production needs stronger source attestation, narrower record/field access, clinical governance, monitoring and concurrency controls.
