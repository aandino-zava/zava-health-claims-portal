"""Apply a protected human decision to an explicitly bound fictional claim.

The portal pulls from a durable Dataverse outbox using its managed identity.
No agent-facing write tool, callback secret, or name-based claim matching.
"""
import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update

from app import services
from app.database import Claim
from app.telemetry import event


class RejectedDecision(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise RejectedDecision(reason)


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def same(value, expected):
    return isinstance(value, str) and value.casefold() == expected.casefold()


def business_fields(row):
    # Dataverse connectors can omit null properties while the SDK returns them.
    # Preserve every non-null business value, including false and zero.
    return {k: v for k, v in row.items() if k.startswith("cr_") and "@" not in k and v is not None}


def portal_snapshot(row):
    return {"claimId": row.id, "memberId": row.patient_id,
            "cptCode": row.payload["procedure_code"], "serviceDate": row.payload["service_date"],
            "version": row.version, "status": row.status,
            "synthetic": row.payload.get("synthetic_data_confirmed") is True}


class DataverseGateway:
    def __init__(self, settings):
        from azure.identity import ManagedIdentityCredential
        from PowerPlatform.Dataverse.client import DataverseClient
        from PowerPlatform.Dataverse.core.config import OperationContext
        self.client = DataverseClient(
            base_url=settings.concierge_dataverse_url,
            credential=ManagedIdentityCredential(client_id=settings.concierge_identity_client_id),
            context=OperationContext(user_agent_context="app=zava-claims-portal/1.0"))

    def pending(self):
        return [dict(r) for r in self.client.records.list("cr_claim_evaluation",
                filter="cr_state eq 'PortalUpdatePending' and cr_mode eq 'Simulated'", top=10)]

    def evidence(self, alias, version):
        # Values have already passed identifier validation.
        return [dict(r) for r in self.client.records.list("cr_claim_evidence",
                filter=f"cr_claim_id eq '{alias}' and cr_policy_version eq '{version}'", top=2)]

    def policies(self, number, version):
        return [dict(r) for r in self.client.records.list("cr_medical_policy_rules",
                filter=f"cr_policy_number eq '{number}' and cr_policy_version eq '{version}' and cr_is_active eq true",
                orderby=["cr_rule_id asc"], top=10)]

    def approval(self, identifier):
        row = self.client.records.retrieve("msdyn_flow_approval", str(UUID(identifier)))
        return dict(row) if row else {}

    def responses(self, identifier):
        identifier = str(UUID(identifier))
        return [dict(r) for r in self.client.records.list("msdyn_flow_approvalresponse",
                filter=f"_msdyn_flow_approvalresponse_approval_value eq {identifier}", top=2)]

    def acknowledge(self, row, state, receipt):
        result = decode(row["cr_result_json"])
        result.update(status=state, executionMode="PortalSynthetic", portalReceipt=receipt,
                      authorizationGranted=False)
        self.client.records.update("cr_claim_evaluation", row["cr_claim_evaluationid"], {
            "cr_state": state, "cr_receipt_json": json.dumps(receipt),
            "cr_result_json": json.dumps(result),
            "cr_review_summary": f"FICTIONAL PORTAL CLAIM. {state}. "
                                 f"Portal claim: {receipt.get('portalClaimId', 'unchanged')}. "
                                 f"Reason: {receipt.get('reason', 'Verified human decision and portal readback')}.",
        })


class ConciergeWorker:
    def __init__(self, settings, sessions, gateway):
        self.settings, self.sessions, self.gateway = settings, sessions, gateway
        self.allowed = {v.strip() for v in settings.concierge_allowed_claim_ids.split(",")}

    def validate(self, evaluation, *, fresh=True):
        import re
        alias = evaluation["cr_claim_id"]
        number, version = evaluation["cr_policy_number"], evaluation["cr_policy_version"]
        require(bool(re.fullmatch(r"SYN-CLM-[0-9]+", alias)), "InvalidSyntheticAlias")
        require(bool(re.fullmatch(r"[A-Z0-9-]{3,80}", number)), "InvalidPolicyIdentifier")
        require(bool(re.fullmatch(r"[0-9]+\.[0-9]+", version)), "InvalidPolicyVersion")
        require(evaluation["cr_state"] == "PortalUpdatePending" and evaluation["cr_mode"] == "Simulated",
                "NotAnApprovedOutboxEntry")
        decision = decode(evaluation["cr_decision_json"])
        require(decision["decision"] in {"ApproveAuthorization", "DenyClaim"}, "DecisionDoesNotChangeClaim")
        reviewer = self.settings.concierge_reviewer_object_id
        require(all(same(v, reviewer) for v in [decision.get("reviewerObjectId"),
                    evaluation.get("cr_reviewer_object_id"), evaluation.get("cr_assigned_reviewer_id")]),
                "WrongMedicalDirector")
        require(same(decision.get("reviewerTenantId"), self.settings.entra_tenant_id), "WrongReviewerTenant")
        approval_id = str(UUID(evaluation["cr_approval_id"]))
        require(same(decision.get("approvalId"), approval_id), "WrongApprovalBinding")
        approval, responses = self.gateway.approval(approval_id), self.gateway.responses(approval_id)
        require(approval.get("statecode") == 1 and approval.get("msdyn_flow_approval_result") == decision["decision"],
                "ApprovalNotCompleted")
        require(approval.get("msdyn_flow_approval_itemlink", "").endswith("id=" + evaluation["cr_claim_evaluationid"]),
                "ApprovalForAnotherEvaluation")
        require(len(responses) == 1, "MissingOrAmbiguousApprovalResponse")
        response = responses[0]
        require(same(response.get("_ownerid_value"), self.settings.concierge_reviewer_user_id)
                and response.get("msdyn_flow_approvalresponse_response") == decision["decision"]
                and same(response.get("_msdyn_flow_approvalresponse_approval_value"), approval_id)
                and response.get("statecode") == 1, "UnverifiedApprovalResponse")
        require(instant(response["createdon"]) < instant(evaluation["cr_expires_at"]), "LateApprovalResponse")
        if decision["decision"] == "ApproveAuthorization":
            require(decode(evaluation["cr_result_json"]).get("eligibleForHumanApproval") is True,
                    "ApprovalWithoutVerifiedEligibility")
        stored = decode(evaluation["cr_evidence_snapshot_json"])
        evidence = {"cr_"+key: value for key, value in stored.items()}
        if fresh:
            current = self.gateway.evidence(alias, version)
            require(len(current) == 1, "MissingOrAmbiguousProtectedEvidence")
            require(all(current[0].get("cr_"+key) == value for key, value in stored.items()), "EvidenceChanged")
        require(evidence.get("cr_is_synthetic") is True, "NonSyntheticEvidence")
        claim = decode(evidence["cr_claim_snapshot_json"])
        require(claim.get("claimId") == alias and claim.get("synthetic") is True
                and claim.get("version") == evaluation["cr_claim_version"], "ClaimSnapshotMismatch")
        require(evidence.get("cr_member_id") == claim.get("memberId")
                and evidence.get("cr_cpt_code") == claim.get("cptCode"), "MemberOrProcedureMismatch")
        binding = claim.get("portalBinding", {})
        require(binding.get("claimId") in self.allowed and binding.get("synthetic") is True,
                "PortalClaimNotExplicitlyAllowed")
        require(binding.get("memberId") == claim["memberId"] and binding.get("cptCode") == claim["cptCode"]
                and binding.get("serviceDate") == claim["serviceDate"], "WrongPortalClaimBinding")
        saved = decode(evaluation["cr_policy_snapshot_json"])
        if fresh:
            policies = self.gateway.policies(number, version)
            require(len(policies) == len(saved) == 3
                    and [business_fields(r) for r in policies] == [business_fields(r) for r in saved], "PolicyChanged")
            require(all(instant(r["cr_effective_from"]).date() <= instant(claim["serviceDate"]+"T00:00:00Z").date()
                        and (r.get("cr_effective_to") is None
                             or instant(claim["serviceDate"]+"T00:00:00Z").date()
                             < instant(r["cr_effective_to"]).date()) for r in policies), "PolicyOutsideServiceDate")
        return decision, binding

    def apply(self, evaluation):
        decision, binding = self.validate(evaluation, fresh=False)
        operation = str(UUID(evaluation["cr_evaluation_id"]))
        with self.sessions() as db:
            row = services.get_claim(db, binding["claimId"])
            prior = [entry.get("conciergeReceipt") for entry in row.history
                     if entry.get("conciergeReceipt", {}).get("operationId") == operation]
            # A lost Dataverse acknowledgement can be repaired even after expiry.
            if prior:
                require(len(prior) == 1 and prior[0]["approvalId"] == evaluation["cr_approval_id"],
                        "ReceiptConflict")
                return prior[0]
            self.validate(evaluation)
            require(datetime.now(UTC) < instant(evaluation["cr_expires_at"]), "EvaluationExpired")
            require(portal_snapshot(row) == binding, "PortalClaimChanged")
            status = "Approved" if decision["decision"] == "ApproveAuthorization" else "Denied"
            require(status in services.TRANSITIONS[row.status], "InvalidPortalTransition")
            receipt = {"operationId": operation, "approvalId": evaluation["cr_approval_id"],
                       "portalClaimId": row.id, "claimAlias": evaluation["cr_claim_id"],
                       "status": status, "previousVersion": row.version, "version": row.version+1,
                       "reviewerObjectId": decision["reviewerObjectId"], "mode": "PortalSynthetic",
                       "policyVersion": evaluation["cr_policy_version"],
                       "correlationId": evaluation["cr_correlation_id"],
                       "at": datetime.now(UTC).isoformat()}
            history = row.history + [{"status": status, "at": receipt["at"],
                "actor": "Medical Director " + decision["reviewerObjectId"],
                "note": f"Fictional claim: verified Medical Director decision through Claims Concierge. "
                        f"Evaluation {operation}; approval {evaluation['cr_approval_id']}. No real care authorization.",
                "conciergeReceipt": receipt}]
            changed = db.execute(update(Claim).where(Claim.id == row.id, Claim.version == binding["version"])
                                 .values(status=status, version=receipt["version"], history=history,
                                         updated_at=datetime.now(UTC)))
            require(changed.rowcount == 1, "ConcurrentPortalChange")
            db.commit()
        # Verify through a separate database session before acknowledging completion.
        with self.sessions() as db:
            persisted = services.get_claim(db, binding["claimId"])
            if not (persisted.status == status and persisted.version == receipt["version"]
                    and persisted.history[-1].get("conciergeReceipt") == receipt):
                raise RuntimeError("PortalReadbackUnconfirmed")
        return receipt

    def run_once(self):
        for evaluation in self.gateway.pending():
            try:
                receipt = self.apply(evaluation)
            except RejectedDecision as exc:
                self.gateway.acknowledge(evaluation, "PortalUpdateBlocked", {"reason": str(exc),
                                         "mode": "PortalSynthetic", "claimWrites": 0})
                event("concierge_decision_blocked", reason=str(exc))
            else:
                self.gateway.acknowledge(evaluation, "PortalConfirmed", receipt)
                event("concierge_portal_update_confirmed")


async def run_worker(settings, sessions, stop):
    worker = None
    while not stop.is_set():
        try:
            if worker is None:
                gateway = await asyncio.to_thread(DataverseGateway, settings)
                worker = ConciergeWorker(settings, sessions, gateway)
            await asyncio.to_thread(worker.run_once)
        except Exception as exc:
            # Keep the durable outbox entry for reconciliation; never log payloads.
            event("concierge_sync_unavailable", reason=type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.concierge_poll_seconds)
        except TimeoutError:
            pass
