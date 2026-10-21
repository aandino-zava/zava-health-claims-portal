import copy
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.concierge import ConciergeWorker, DataverseGateway, RejectedDecision, portal_snapshot
from app.database import Claim
from tests.test_api import payload, setup, submit  # noqa: F401


@pytest.fixture
def connected(setup):  # noqa: F811
    client, app, _ = setup
    result = submit(client, {**payload(), "patient_id": "SYN-MEMBER-1001", "procedure_code": "72148"})
    row = result.json()
    client.patch(
        f"/api/v1/claims/{row['id']}/status",
        json={"status": "Under Review", "expected_version": 1, "note": "Fictional concierge acceptance"},
    )
    with app.state.sessions() as db:
        binding = portal_snapshot(db.get(Claim, row["id"]))
    reviewer, user, tenant, approval, evaluation, record = [str(uuid4()) for _ in range(6)]
    settings = SimpleNamespace(
        concierge_allowed_claim_ids=row["id"],
        concierge_reviewer_object_id=reviewer,
        concierge_reviewer_user_id=user,
        entra_tenant_id=tenant,
    )
    snapshot = {
        "claimId": "SYN-CLM-1001",
        "memberId": "SYN-MEMBER-1001",
        "cptCode": "72148",
        "version": 1,
        "synthetic": True,
        "serviceDate": binding["serviceDate"],
        "portalBinding": binding,
    }
    evidence = {
        "claim_id": "SYN-CLM-1001",
        "member_id": "SYN-MEMBER-1001",
        "cpt_code": "72148",
        "is_synthetic": True,
        "claim_snapshot_json": json.dumps(snapshot),
        "facts_json": "protected",
    }
    policies = [
        {
            "cr_rule_id": str(i),
            "cr_effective_from": "2026-01-01T00:00:00Z",
            "cr_effective_to": "2027-01-01T00:00:00Z",
        }
        for i in range(3)
    ]
    response = {
        "_ownerid_value": user,
        "msdyn_flow_approvalresponse_response": "ApproveAuthorization",
        "_msdyn_flow_approvalresponse_approval_value": approval,
        "statecode": 1,
        "createdon": datetime.now(UTC).isoformat(),
    }
    item = {
        "cr_claim_evaluationid": record,
        "cr_evaluation_id": evaluation,
        "cr_claim_id": "SYN-CLM-1001",
        "cr_policy_number": "AMH-RAD-2026",
        "cr_policy_version": "1.0",
        "cr_state": "PortalUpdatePending",
        "cr_mode": "Simulated",
        "cr_reviewer_object_id": reviewer,
        "cr_assigned_reviewer_id": reviewer,
        "cr_approval_id": approval,
        "cr_claim_version": 1,
        "cr_correlation_id": str(uuid4()),
        "cr_expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "cr_result_json": json.dumps({"eligibleForHumanApproval": True}),
        "cr_evidence_snapshot_json": json.dumps(evidence),
        "cr_policy_snapshot_json": json.dumps(policies),
        "cr_decision_json": json.dumps(
            {
                "decision": "ApproveAuthorization",
                "reviewerObjectId": reviewer,
                "reviewerTenantId": tenant,
                "approvalId": approval,
            }
        ),
    }

    class Gateway:
        def __init__(self):
            self.current_evidence = {"cr_" + k: v for k, v in evidence.items()}
            self.current_policies = policies
            self.current_responses = [response]
            self.acknowledgements = []

        def evidence(self, *_):
            return [self.current_evidence]

        def policies(self, *_):
            return self.current_policies

        def responses(self, *_):
            return self.current_responses

        def approval(self, *_):
            return {
                "statecode": 1,
                "msdyn_flow_approval_result": "ApproveAuthorization",
                "msdyn_flow_approval_itemlink": "https://review.example/?id=" + record,
            }

        def pending(self):
            return [item]

        def acknowledge(self, *args):
            self.acknowledgements.append(args)

    gateway = Gateway()
    worker = ConciergeWorker(settings, app.state.sessions, gateway)
    return worker, item, gateway, client, row["id"]


def test_verified_approval_persists_once_and_recovers_lost_acknowledgement(connected):
    worker, item, gateway, client, claim = connected
    first = worker.apply(item)
    assert first["status"] == "Approved" and first["version"] == 3
    # An uncertain acknowledgement must not produce a second portal write.
    item["cr_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    gateway.current_responses[0]["createdon"] = (datetime.now(UTC) - timedelta(seconds=2)).isoformat()
    gateway.current_evidence = {"cr_facts_json": "changed after commit"}
    assert worker.apply(item) == first
    actual = client.get(f"/api/v1/claims/{claim}").json()
    assert actual["status"] == "Approved" and actual["version"] == 3 and len(actual["history"]) == 3


@pytest.mark.parametrize(
    "failure",
    [
        "wrong_reviewer",
        "missing_response",
        "wrong_claim",
        "stale_portal",
        "changed_evidence",
        "changed_policy",
        "ineligible",
        "expired",
    ],
)
def test_rejects_unsafe_decisions_without_a_claim_write(connected, failure):
    worker, item, gateway, client, claim = connected
    if failure == "wrong_reviewer":
        gateway.current_responses[0]["_ownerid_value"] = str(uuid4())
    if failure == "missing_response":
        gateway.current_responses = []
    if failure == "wrong_claim":
        worker.allowed = {"CLM-2026-0000000000000000"}
    if failure == "stale_portal":
        client.patch(
            f"/api/v1/claims/{claim}/status",
            json={"status": "Pending Info", "expected_version": 2, "note": "Concurrent reviewer change"},
        )
    if failure == "changed_evidence":
        gateway.current_evidence = {"cr_facts_json": "appeal-only assertion"}
    if failure == "changed_policy":
        gateway.current_policies = copy.deepcopy(gateway.current_policies)
        gateway.current_policies[0]["cr_effective_to"] = "2026-01-02T00:00:00Z"
    if failure == "ineligible":
        item["cr_result_json"] = '{"eligibleForHumanApproval":false}'
    if failure == "expired":
        item["cr_expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with pytest.raises(RejectedDecision):
        worker.apply(item)
    actual = client.get(f"/api/v1/claims/{claim}").json()
    assert actual["status"] != "Approved"


def test_downstream_failure_preserves_pending_decision(connected):
    worker, item, gateway, *_ = connected

    def unavailable(*_):
        raise TimeoutError()

    gateway.responses = unavailable
    with pytest.raises(TimeoutError):
        worker.run_once()
    assert gateway.acknowledgements == [] and item["cr_state"] == "PortalUpdatePending"


def test_managed_identity_gateway_initializes_without_network_or_credentials():
    gateway = DataverseGateway(SimpleNamespace(
        concierge_dataverse_url="https://example.crm.dynamics.com",
        concierge_identity_client_id="11111111-1111-4111-8111-111111111111"))
    gateway.client.close()


def test_active_policy_can_have_no_end_date(connected):
    worker, item, gateway, *_ = connected
    gateway.current_policies = copy.deepcopy(gateway.current_policies)
    for rule in gateway.current_policies:
        rule["cr_effective_to"] = None
    item["cr_policy_snapshot_json"] = json.dumps(gateway.current_policies)
    assert worker.apply(item)["status"] == "Approved"
