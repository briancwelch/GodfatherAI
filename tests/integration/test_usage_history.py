"""Durable, workspace-scoped inference measurements and execution provenance."""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from godfather_agent_runtime.tools import describe
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.models import (
    Attempt,
    HumanSession,
    Job,
    User,
    WorkflowStepRecord,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import token_digest
from godfather_api.provision import provision
from godfather_contracts.agents import AgentDefinition, Plan
from godfather_contracts.coding import CODING_RUNTIME
from godfather_contracts.inference import InferenceUsage
from godfather_model_gateway import Chunk
from sqlalchemy import select

from tests.integration.test_inference import enable as enable_inference
from tests.integration.test_inference import inference_result
from tests.integration.test_inference import submit as submit_inference
from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import (
    PLAN,
    USAGE,
    create,
    enable,
    expire,
    first_checkpoint,
    run_worker,
    step,
    submit,
)
from tests.integration.test_workloads import enable_data, submit_data
from tests.test_agent_runtime import MockModel, model
from tests.workflow_helpers import sample_definition

pytestmark = pytest.mark.integration


def metrics(h: Harness) -> dict[str, Any]:
    response = h.client.get(
        "/api/v1/inference/metrics",
        params={"workspace_id": str(h.workspace_id)},
        headers=headers(h.admin),
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


class CounterModel(MockModel):
    async def infer(self, identifier: str, request: object) -> AsyncGenerator[Chunk]:
        async for chunk in super().infer(identifier, request):
            yield chunk.model_copy(
                update={"input_tokens": 11, "output_tokens": 5, "generation_seconds": 2.0}
                if len(self.calls) == 1
                else {"input_tokens": None, "output_tokens": None}
            )


def test_workflow_measurements_preserve_each_call_and_unknown_counters(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    run_worker(h, assignment, CounterModel())
    with h.database.sessions.begin() as session:
        records = list(session.scalars(select(WorkflowStepRecord)))
        recorded = {row.step_id: row.metadata_refs.get("usage") for row in records}
        for record in records:
            record.metadata_refs = {**record.metadata_refs, "private_debug": "excluded metadata"}
    data = metrics(h)
    samples = {row["step_id"]: row for row in data["recent_measurements"]}
    assert data["job_counts"] == {"COMPLETED": 1}
    assert set(samples) == {"plan", "summary"}  # The deterministic tool is not inference.
    assert samples["plan"]["usage"] == recorded["plan"]
    assert samples["plan"]["usage"]["input_tokens"] == 11
    assert samples["plan"]["usage"]["output_tokens"] == 5
    assert samples["plan"]["usage"]["tokens_per_second"] == 2.5
    assert samples["plan"]["usage"]["rate_source"] == "provider_reported"
    assert samples["summary"]["usage"] == recorded["summary"]
    assert samples["summary"]["usage"]["input_tokens"] is None
    assert samples["summary"]["usage"]["output_tokens"] is None
    assert samples["summary"]["usage"]["tokens_per_second"] is None
    assert all(row["job_id"] == job["id"] for row in samples.values())
    assert all(row["deployment"] == assignment["deployment"] for row in samples.values())
    assert all(row["source"] == "workflow_step" for row in samples.values())
    assert "PRIVATE workflow instruction" not in json.dumps(data)
    assert "Portable plan" not in json.dumps(data) and "excluded metadata" not in json.dumps(data)


def test_checkpoint_replay_failover_and_restart_do_not_duplicate_measurements(h: Harness) -> None:
    enable(h)
    enable(h, 1)
    job = submit(h, create(h))
    h.tick()
    original = h.poll()
    assert original is not None
    first_checkpoint(h, original)
    step(h, original, "plan", 0, "checkpoint", output=PLAN, usage=USAGE)
    before = metrics(h)
    assert len(before["recent_measurements"]) == 1
    assert before["recent_measurements"][0]["usage"]["input_tokens"] == 3
    step(h, original, "describe", 1)
    step(
        h,
        original,
        "describe",
        1,
        "checkpoint",
        output=describe(Plan.model_validate(PLAN)).model_dump(mode="json"),
    )
    step(h, original, "summary", 2)  # Uncommitted model work must not become a measurement.
    expire(h, original)
    recovered = h.poll(1)
    assert recovered is not None
    provider = run_worker(h, recovered, index=1)
    assert len(provider.calls) == 1
    samples = metrics(h)["recent_measurements"]
    assert len(samples) == 2 and len({s["measurement_id"] for s in samples}) == 2
    assert {(s["step_id"], s["node_id"]) for s in samples} == {
        ("plan", h.workers[0]["credential_id"]),
        ("summary", h.workers[1]["credential_id"]),
    }
    assert (
        next(s for s in samples if s["step_id"] == "plan")["attempt_id"] == original["attempt_id"]
    )
    step(h, original, "plan", 0, "checkpoint", expected=409, output=PLAN, usage=USAGE)
    original_client = h.client
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        h.client = restarted
        try:
            assert metrics(h)["recent_measurements"] == samples
            detail = h.client.get(
                f"/api/v1/command-center/jobs/{job['id']}", headers=headers(h.admin)
            ).json()["job"]
            assert detail["assigned_node_id"] is None
            assert detail["execution"]["node_id"] == h.workers[1]["credential_id"]
            assert detail["execution"]["attempt_number"] == 2
        finally:
            h.client = original_client


def test_direct_inference_measurements_remain_exact_and_separate_from_workflow_calls(
    h: Harness,
) -> None:
    deployment = enable_inference(h)
    job = submit_inference(h, stream=False)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    result = inference_result(deployment)
    h.report(assignment, "complete", result=result)
    direct = metrics(h)["recent_measurements"][0]
    assert direct["source"] == "inference_attempt" and direct["step_id"] is None
    assert direct["job_id"] == job["id"] and direct["usage"] == result["usage"]
    enable(h)
    workflow = submit(h, create(h))
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    run_worker(h, assignment)
    data = metrics(h)
    assert data["job_counts"] == {"COMPLETED": 2}
    assert len(data["recent_measurements"]) == 3
    assert {s["job_id"] for s in data["recent_measurements"]} == {job["id"], workflow["id"]}


def test_measurements_are_workspace_scoped_and_logically_deleted_jobs_stay_hidden(
    h: Harness,
) -> None:
    enable(h)
    jobs = []
    first_workspace = h.workspace_id
    with h.database.sessions.begin() as session:
        other = Workspace(owner_id=UUID(h.admin["owner_id"]), name="Separate usage")
        session.add(other)
        session.flush()
        other_workspace = other.id
    for workspace in (first_workspace, other_workspace):
        h.workspace_id = workspace
        job = submit(h, create(h))
        h.tick()
        assignment = h.poll()
        assert assignment is not None
        run_worker(h, assignment)
        jobs.append(job)
    h.workspace_id = first_workspace
    assert {s["job_id"] for s in metrics(h)["recent_measurements"]} == {jobs[0]["id"]}
    outsider = provision(h.database, "admin", email="usage-outsider@example.invalid")
    for auth, status in (({}, 401), (headers(h.workers[0]), 401), (headers(outsider), 404)):
        assert (
            h.client.get(
                f"/api/v1/inference/metrics?workspace_id={first_workspace}", headers=auth
            ).status_code
            == status
        )
    response = h.client.post(
        "/api/v1/administration/bulk-delete",
        json={"kind": "jobs", "ids": [jobs[0]["id"]]},
        headers=headers(h.admin),
    )
    assert response.status_code == 200
    data = metrics(h)
    assert data["job_counts"] == {} and data["recent_measurements"] == []
    assert data["recent_attempts"] == []
    with h.database.sessions() as session:
        assert (
            len(
                session.scalars(
                    select(WorkflowStepRecord).where(
                        WorkflowStepRecord.job_id == UUID(jobs[0]["id"])
                    )
                ).all()
            )
            == 3
        )


def test_combined_measurements_are_bounded_and_sorted_by_completion(h: Harness) -> None:
    enable(h)
    submit(h, create(h))
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    run_worker(h, assignment)
    now = datetime.now(UTC)
    with h.database.sessions.begin() as session:
        for index in range(199):
            direct = Job(
                owner_id=UUID(h.admin["owner_id"]),
                workspace_id=h.workspace_id,
                type="inference.text",
                status="COMPLETED",
                attempt_count=1,
                fencing_token=1,
            )
            session.add(direct)
            session.flush()
            session.add(
                Attempt(
                    job_id=direct.id,
                    node_id=UUID(h.workers[0]["credential_id"]),
                    number=1,
                    fencing_token=1,
                    status="COMPLETED",
                    lease_expires_at=now,
                    finished_at=now - timedelta(minutes=index + 1),
                    result={
                        "deployment": assignment["deployment"],
                        "usage": InferenceUsage(duration_seconds=1).model_dump(mode="json"),
                    },
                )
            )
    data = metrics(h)
    samples = data["recent_measurements"]
    assert data["recent_measurement_limit"] == 200 and len(samples) == 200
    assert len({s["measurement_id"] for s in samples}) == 200
    assert [s["source"] for s in samples[:2]] == ["workflow_step", "workflow_step"]
    assert [s["measured_at"] for s in samples] == sorted(
        (s["measured_at"] for s in samples), reverse=True
    )


def test_pending_model_jobs_count_without_counting_data_workflows(h: Harness) -> None:
    enable(h)
    submit(h, create(h))
    enable_data(h, 1)
    submit_data(h)
    data = metrics(h)
    assert data["job_counts"] == {"PENDING": 1}
    assert data["recent_measurements"] == []


def test_historical_coding_step_usage_is_included(h: Harness) -> None:
    definition = sample_definition().model_dump(mode="json")
    definition["requirements"]["runtimes"] = [CODING_RUNTIME]
    definition["allowed_tools"] = []
    definition["permissions"] = ["coding.workspace"]
    definition["retry"]["limit"] = 0
    definition["workflow"]["steps"] = [
        {
            "id": "code",
            "kind": "coding",
            "instruction": "Inspect fixture",
            "output_schema": "coding",
        }
    ]
    agent = create(h, AgentDefinition.model_validate(definition))
    usage = InferenceUsage(
        duration_seconds=1, input_tokens=7, output_tokens=4, token_source="provider_reported"
    ).model_dump(mode="json")
    now = datetime.now(UTC)
    with h.database.sessions.begin() as session:
        job = Job(
            owner_id=UUID(h.admin["owner_id"]),
            workspace_id=h.workspace_id,
            agent_id=UUID(agent["version_id"]),
            type="agent.workflow",
            status="COMPLETED",
            attempt_count=1,
            fencing_token=1,
        )
        session.add(job)
        session.flush()
        attempt = Attempt(
            job_id=job.id,
            node_id=UUID(h.workers[0]["credential_id"]),
            number=1,
            fencing_token=1,
            status="COMPLETED",
            lease_expires_at=now,
            finished_at=now,
        )
        session.add(attempt)
        session.flush()
        session.add(
            WorkflowStepRecord(
                job_id=job.id,
                attempt_id=attempt.id,
                step_id="code",
                status="COMPLETED",
                finished_at=now,
                metadata_refs={
                    "kind": "coding",
                    "model": model().model_dump(mode="json"),
                    "usage": usage,
                },
            )
        )
    data = metrics(h)
    assert data["job_counts"] == {"COMPLETED": 1}
    assert len(data["recent_measurements"]) == 1
    assert data["recent_measurements"][0]["step_id"] == "code"
    assert data["recent_measurements"][0]["usage"] == usage


@pytest.mark.parametrize("terminal", ["COMPLETED", "FAILED", "CANCELLED"])
def test_execution_identity_survives_cleared_assignments(h: Harness, terminal: str) -> None:
    job = h.submit()
    path = f"/api/v1/command-center/jobs/{job['id']}"
    assert h.client.get(path, headers=headers(h.admin)).json()["job"]["execution"] is None
    h.tick()
    assignment = h.poll()
    assert assignment is not None and "execution" not in assignment["job"]
    h.start(assignment)
    active = h.client.get(path, headers=headers(h.admin)).json()["job"]
    assert active["execution"]["node_id"] == active["assigned_node_id"]
    if terminal == "COMPLETED":
        h.report(assignment, "complete", result={"value": "done", "steps": 1})
    elif terminal == "FAILED":
        h.report(assignment, "fail", error_code="permanent_error")
    else:
        assert (
            h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)).status_code
            == 200
        )
        h.report(assignment, "cancelled")
    result = h.client.get(path, headers=headers(h.admin)).json()["job"]
    assert result["status"] == terminal and result["assigned_node_id"] is None
    assert result["execution"] == active["execution"]
    assert result["execution"]["node_name"] == "LV-01"
    assert result["execution"]["owner_id"] == h.admin["owner_id"]
    listing = h.client.get("/api/v1/command-center?section=jobs", headers=headers(h.admin)).json()
    assert listing["jobs"][0]["execution"] == result["execution"]


def test_job_provenance_does_not_grant_members_full_node_inspection(h: Harness) -> None:
    job = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.complete(assignment)
    viewer = provision(h.database, "admin", email="history-member@example.invalid")
    with h.database.sessions.begin() as session:
        user = session.get(User, UUID(viewer["owner_id"]))
        assert user is not None
        user.role, user.roles = "member", ["member"]
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=user.id, role="member"))
        session.add(
            HumanSession(
                owner_id=user.id,
                token_hash=token_digest("s" * 43),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    member_headers = {"X-Godfather-Session": "s" * 43}
    response = h.client.get(f"/api/v1/command-center/jobs/{job['id']}", headers=member_headers)
    assert response.status_code == 200, response.text
    provenance = response.json()["job"]["execution"]
    assert provenance["node_name"] == "LV-01" and provenance["can_inspect_node"] is False
    assert set(provenance) == {
        "attempt_id",
        "attempt_number",
        "node_id",
        "node_name",
        "owner_id",
        "owner_name",
        "can_inspect_node",
    }
    listing = h.client.get(
        f"/api/v1/command-center?section=jobs&workspace_id={h.workspace_id}", headers=member_headers
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["jobs"][0]["execution"] == provenance
    assert (
        h.client.get(
            f"/api/v1/command-center/nodes/{provenance['node_id']}", headers=member_headers
        ).status_code
        == 404
    )
    outsider = provision(h.database, "admin", email="history-outsider@example.invalid")
    assert (
        h.client.get(
            f"/api/v1/command-center/jobs/{job['id']}", headers=headers(outsider)
        ).status_code
        == 404
    )
