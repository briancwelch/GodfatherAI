"""Real PostgreSQL provider ownership, billing grants and durable safeguards."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from godfather_api.models import ProviderInvocation, WorkspaceMember
from godfather_api.provision import provision

from tests.integration.test_inference import enable, submit
from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h

pytestmark = pytest.mark.integration


def test_provider_billing_needs_no_prices_or_godfather_budget(h: Harness) -> None:
    identifier, _ = connection(h)
    response = h.client.post(
        f"/api/v1/provider-connections/{identifier}/policy",
        headers=headers(h.admin),
        json={"enabled": True, "billing": "provider"},
    )
    assert response.status_code == 200, response.text
    job = paid_job(h, identifier)
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    authorization = reserve(h, assignment)
    assert authorization.status_code == 200 and authorization.json()["reserved_microusd"] == 0
    assert reserve(h, assignment).status_code == 409
    path = f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/{job['id']}/provider/settle"
    body = {
        "session_id": str(h.registrations[0].session_id),
        "attempt_id": assignment["attempt_id"],
        "fencing_token": assignment["fencing_token"],
        "invocation_id": authorization.json()["invocation_id"],
        "input_tokens": 10,
        "output_tokens": 20,
    }
    assert h.client.post(path, headers=headers(h.workers[0]), json=body).status_code == 200
    with h.database.sessions() as session:
        call = session.get(ProviderInvocation, UUID(body["invocation_id"]))
        assert call is not None and call.settled_microusd is None
        assert call.status == "settled" and call.usage["input_tokens"] == 10


def connection(h: Harness) -> tuple[str, dict[str, Any]]:
    model = enable(h)
    response = h.client.post(
        "/api/v1/provider-connections",
        headers=headers(h.admin),
        json={
            "name": "Fixture API",
            "node_id": h.workers[0]["credential_id"],
            "provider": "openai",
        },
    )
    assert response.status_code == 201, response.text
    identifier = response.json()["id"]
    policy = {
        "enabled": True,
        "sharing": "private",
        "call_limit_microusd": 1000000,
        "lifetime_limit_microusd": 10000000,
        "rates": [
            {
                "identifier": "fixture",
                "input_microusd_per_million": 1000000,
                "output_microusd_per_million": 1000000,
                "source": "https://openai.com/api/pricing/",
                "verified_at": datetime.now(UTC).isoformat(),
            }
        ],
    }
    assert (
        h.client.post(
            f"/api/v1/provider-connections/{identifier}/policy",
            headers=headers(h.admin),
            json=policy,
        ).status_code
        == 200
    )
    model = model.model_copy(update={"provider": "openai", "connection_id": UUID(identifier)})
    registration = h.registrations[0].model_copy(update={"model_deployments": [model]})
    h.registrations[0] = registration
    assert (
        h.client.post(
            "/api/v1/workers/register",
            headers=headers(h.workers[0]),
            json=registration.model_dump(mode="json"),
        ).status_code
        == 200
    )
    return identifier, policy


def paid_job(h: Harness, identifier: str) -> dict[str, Any]:
    return submit(
        h,
        requirements={
            "model_selection": {
                "provider": "openai",
                "identifier": "fixture",
                "connection_id": identifier,
                "paid_consent": True,
            }
        },
    )


def reserve(h: Harness, assignment: dict[str, Any], **extra: object) -> Any:
    return h.client.post(
        f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/{assignment['job']['id']}/provider/authorize",
        headers=headers(h.workers[0]),
        json={
            "session_id": str(h.registrations[0].session_id),
            "attempt_id": assignment["attempt_id"],
            "fencing_token": assignment["fencing_token"],
            "input_bytes": 20,
            **extra,
        },
    )


def test_google_account_authority_does_not_grant_provider_authority(h: Harness) -> None:
    identifier, _ = connection(h)
    other = provision(h.database, "admin", email="other-admin@example.invalid")
    assert h.client.get("/api/v1/provider-connections", headers=headers(other)).json() == []
    for suffix, payload in (("control", {"action": "revoke"}), ("test", {}), ("policy", {})):
        response = h.client.post(
            f"/api/v1/provider-connections/{identifier}/{suffix}",
            headers=headers(other),
            json=payload,
        )
        assert response.status_code == 404
    assert (
        h.client.post(
            "/api/v1/provider-connections",
            headers=headers(h.admin),
            json={
                "node_id": h.workers[0]["credential_id"],
                "provider": "openai",
                "name": "safe",
                "api_key": "fixture-secret",
            },
        ).status_code
        == 422
    )
    assert (
        h.client.get("/api/v1/provider-connections", headers=headers(h.workers[0])).status_code
        == 401
    )


def test_no_silent_local_to_paid_selection_or_missing_consent(h: Harness) -> None:
    identifier, _ = connection(h)
    submit(h)  # Exact model but no paid route: must never select the billable inventory.
    assert h.tick() == 0
    response = h.client.post(
        "/api/v1/inference/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "input": {"prompt": "hello"},
            "requirements": {
                "model_selection": {
                    "provider": "openai",
                    "identifier": "fixture",
                    "connection_id": identifier,
                }
            },
        },
    )
    assert response.status_code == 422


def test_reservation_duplicate_settlement_and_late_accounting(h: Harness) -> None:
    identifier, _ = connection(h)
    job = paid_job(h, identifier)
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    authorization = reserve(h, assignment)
    assert authorization.status_code == 200, authorization.text
    assert reserve(h, assignment).status_code == 409
    # Revocation blocks fresh calls but must not discard usage from the accepted one.
    assert (
        h.client.post(
            f"/api/v1/provider-connections/{identifier}/control",
            headers=headers(h.admin),
            json={"action": "revoke"},
        ).status_code
        == 200
    )
    assert reserve(h, assignment, call_key="next").status_code in (403, 409)
    identity = {
        "session_id": str(h.registrations[0].session_id),
        "attempt_id": assignment["attempt_id"],
        "fencing_token": assignment["fencing_token"],
        "invocation_id": authorization.json()["invocation_id"],
        "input_tokens": 10,
        "output_tokens": 20,
    }
    path = f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/{job['id']}/provider/settle"
    assert h.client.post(path, headers=headers(h.workers[0]), json=identity).status_code == 200
    assert h.client.post(path, headers=headers(h.workers[0]), json=identity).status_code == 200
    assert (
        h.client.post(
            path, headers=headers(h.workers[0]), json={**identity, "output_tokens": 21}
        ).status_code
        == 409
    )
    usage = h.client.get(
        f"/api/v1/provider-connections/{identifier}/usage", headers=headers(h.admin)
    ).json()
    assert usage[0]["estimated_microusd"] == 30 and usage[0]["payer_id"] == h.admin["owner_id"]


def test_unknown_usage_retains_reservation_and_paid_attempt_does_not_retry(h: Harness) -> None:
    identifier, _ = connection(h)
    job = paid_job(h, identifier)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    assert reserve(h, assignment).status_code == 200
    h.report(assignment, "fail", error_code="provider_timeout")
    assert h.get(job["id"])["status"] == "FAILED"
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin)).status_code
        == 409
    )
    with h.database.sessions() as session:
        row = session.query(ProviderInvocation).one()
        assert row.settled_microusd is None and row.reserved_microusd > 0


def test_budget_counts_outstanding_calls_transactionally(h: Harness) -> None:
    identifier, policy = connection(h)
    paid_job(h, identifier)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    first = reserve(h, assignment)
    assert first.status_code == 200
    policy["lifetime_limit_microusd"] = first.json()["reserved_microusd"]
    assert (
        h.client.post(
            f"/api/v1/provider-connections/{identifier}/policy",
            headers=headers(h.admin),
            json=policy,
        ).status_code
        == 200
    )
    assert reserve(h, assignment, call_key="second").status_code == 409


def test_workspace_membership_does_not_authorize_cross_user_spending(h: Harness) -> None:
    identifier, policy = connection(h)
    borrower = provision(h.database, "admin", email="borrower@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=h.workspace_id, user_id=UUID(borrower["owner_id"]), role="member"
            )
        )
    # Node-owner contribution grants remain independently necessary.
    response = h.client.post(
        "/api/v1/inference/jobs",
        headers=headers(borrower),
        json={
            "workspace_id": str(h.workspace_id),
            "input": {"prompt": "hello"},
            "requirements": {
                "model_selection": {
                    "provider": "openai",
                    "identifier": "fixture",
                    "connection_id": identifier,
                    "paid_consent": True,
                }
            },
        },
    )
    assert response.status_code == 201
    assert h.tick() == 0
    assert (
        h.client.get(
            f"/api/v1/provider-connections/{identifier}/usage", headers=headers(borrower)
        ).status_code
        == 404
    )
    # An owner can issue a scoped grant without transferring a key.
    grant = h.client.post(
        f"/api/v1/provider-connections/{identifier}/grants",
        headers=headers(h.admin),
        json={
            "user_id": borrower["owner_id"],
            "workspace_id": str(h.workspace_id),
            "model": "fixture",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "limit_microusd": 100000,
        },
    )
    assert grant.status_code == 201


def test_per_job_owner_approval_binds_grant_and_preserves_payer(h: Harness) -> None:
    identifier, policy = connection(h)
    borrower = provision(h.database, "admin", email="approved-borrower@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=h.workspace_id, user_id=UUID(borrower["owner_id"]), role="member"
            )
        )
    registration = h.registrations[0].model_copy(
        update={
            "allowed_job_owner_ids": [UUID(borrower["owner_id"])],
            "allowed_workspace_ids": [h.workspace_id],
        }
    )
    h.registrations[0] = registration
    assert (
        h.client.post(
            "/api/v1/workers/register",
            headers=headers(h.workers[0]),
            json=registration.model_dump(mode="json"),
        ).status_code
        == 200
    )
    job = h.client.post(
        "/api/v1/inference/jobs",
        headers=headers(borrower),
        json={
            "workspace_id": str(h.workspace_id),
            "input": {"prompt": "approved fixture"},
            "requirements": {
                "model_selection": {
                    "provider": "openai",
                    "identifier": "fixture",
                    "connection_id": identifier,
                    "paid_consent": True,
                }
            },
        },
    ).json()
    policy.update(
        sharing="approval_required",
        allowed_user_ids=[borrower["owner_id"]],
        allowed_workspace_ids=[str(h.workspace_id)],
    )
    assert (
        h.client.post(
            f"/api/v1/provider-connections/{identifier}/policy",
            headers=headers(h.admin),
            json=policy,
        ).status_code
        == 200
    )
    assert h.tick() == 0
    grant = h.client.post(
        f"/api/v1/provider-connections/{identifier}/grants",
        headers=headers(h.admin),
        json={
            "user_id": borrower["owner_id"],
            "workspace_id": str(h.workspace_id),
            "job_id": job["id"],
            "model": "fixture",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "limit_microusd": 100000,
        },
    )
    assert grant.status_code == 201, grant.text
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    assert reserve(h, assignment).status_code == 200
    usage = h.client.get(
        f"/api/v1/provider-connections/{identifier}/usage", headers=headers(h.admin)
    ).json()[0]
    assert (
        usage["payer_id"] == h.admin["owner_id"] and usage["submitter_id"] == borrower["owner_id"]
    )
    assert (
        h.client.post(
            f"/api/v1/provider-connections/{identifier}/grants/{grant.json()['id']}/revoke",
            headers=headers(h.admin),
            json={},
        ).status_code
        == 200
    )
    assert reserve(h, assignment, call_key="after-revocation").status_code in (403, 409)


def test_concurrent_reservations_cannot_reuse_the_same_remaining_allowance(h: Harness) -> None:
    identifier, policy = connection(h)
    policy["lifetime_limit_microusd"] = 4628
    assert (
        h.client.post(
            f"/api/v1/provider-connections/{identifier}/policy",
            headers=headers(h.admin),
            json=policy,
        ).status_code
        == 200
    )
    paid_job(h, identifier)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda key: reserve(h, assignment, call_key=key).status_code, ["a", "b"])
        )
    assert sorted(responses) == [200, 409]


def test_release_indicator_uses_runtime_metadata(h: Harness) -> None:
    settings = cast(FastAPI, h.client.app).state.settings
    settings.release_version = "1.2.3-fixture"
    settings.release_revision = "a" * 40
    settings.release_built_at = "2026-10-20T20:00:00Z"
    snapshot = h.client.get("/api/v1/command-center", headers=headers(h.admin)).json()
    assert snapshot["release"] == {
        "version": "1.2.3-fixture",
        "revision": "a" * 40,
        "built_at": "2026-10-20T20:00:00Z",
    }


def test_lost_coding_attempt_requires_review_and_fences_late_writes(h: Harness) -> None:
    from godfather_contracts import Registration, RepositoryReference
    from godfather_contracts.agents import AgentDefinition
    from godfather_contracts.coding import CODING_RUNTIME, REPOSITORY_PREFIX

    from tests.integration.test_workflows import create, enable
    from tests.workflow_helpers import sample_definition

    enable(h)
    repo = uuid4()
    registration = h.registrations[0].model_copy(
        update={
            "runtimes": [CODING_RUNTIME, REPOSITORY_PREFIX + str(repo)],
            "tool_permissions": ["coding.workspace"],
            "worker_tools": [],
            "coding_repositories": [
                RepositoryReference(
                    id=repo,
                    name="Fixture repository",
                    allowed_user_ids=[UUID(h.admin["owner_id"])],
                    allowed_workspace_ids=[h.workspace_id],
                )
            ],
        }
    )
    # Validate the advertisement, including nested repository scopes, before registration.
    registration = Registration.model_validate(registration.model_dump(mode="json"))
    h.registrations[0] = registration
    assert (
        h.client.post(
            "/api/v1/workers/register",
            headers=headers(h.workers[0]),
            json=registration.model_dump(mode="json"),
        ).status_code
        == 200
    )
    definition = sample_definition().model_dump(mode="json")
    definition.update(
        allowed_tools=[],
        permissions=["coding.workspace"],
        retry={"limit": 0},
        workflow={
            "id": str(uuid4()),
            "version": 1,
            "steps": [
                {
                    "id": "code",
                    "kind": "coding",
                    "instruction": "Inspect approved source",
                    "output_schema": "coding",
                }
            ],
        },
    )
    definition["requirements"]["runtimes"] = [CODING_RUNTIME]
    agent = create(h, AgentDefinition.model_validate(definition))
    job = h.client.post(
        "/api/v1/workflow/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "agent_id": agent["id"],
            "agent_version": 1,
            "input": {"instruction": "Inspect fixture", "repository_id": str(repo)},
        },
    ).json()
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    h.tick(datetime.fromisoformat(assignment["lease_expires_at"]) + timedelta(seconds=1))
    detail = h.client.get(
        f"/api/v1/command-center/jobs/{job['id']}", headers=headers(h.admin)
    ).json()
    assert detail["job"]["status"] == "FAILED" and detail["workflow"]["status"] == "REVIEW_REQUIRED"
    assert detail["job"]["attempt_count"] == 1
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin)).status_code
        == 409
    )
    h.report(assignment, "progress", expected=409, progress=100)
