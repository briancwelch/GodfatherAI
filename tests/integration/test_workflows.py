"""PostgreSQL workflow transitions, checkpoint durability, recovery, isolation and fencing."""

import asyncio
import threading
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from godfather_api import workflow_service
from godfather_api.app import create_app
from godfather_api.artifacts import ArtifactError, LocalArtifactStore
from godfather_api.config import Settings
from godfather_api.models import (
    Agent,
    Artifact,
    Attempt,
    Checkpoint,
    Node,
    WorkflowStepRecord,
)
from godfather_api.provision import provision
from godfather_contracts.agents import AgentDefinition
from godfather_contracts.jobs import Assignment
from godfather_model_gateway import Chunk, ProviderConfig
from godfather_worker.agents import execute_agent
from sqlalchemy import func, select

from tests.integration.test_inference import APIWorkerClient
from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.test_agent_runtime import MockModel, model
from tests.workflow_helpers import sample_definition

pytestmark = pytest.mark.integration
USAGE = {
    "duration_seconds": 0.1,
    "input_tokens": 3,
    "output_tokens": 2,
    "token_source": "provider_reported",
}
PLAN = {"title": "Portable plan", "items": ["Inspect", "Report"]}


def enable(h: Harness, index: int = 0, permission: bool = True) -> None:
    registration = h.registrations[index].model_copy(
        update={
            "workflow_protocol_version": 1,
            "inference_protocol_version": 1,
            "model_deployments": [model()],
            "worker_tools": sample_definition().allowed_tools,
            "tool_permissions": ["plan.read"] if permission else [],
        }
    )
    response = h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[index]),
    )
    assert response.status_code == 200, response.text
    h.registrations[index] = registration


def create(h: Harness, definition: AgentDefinition | None = None) -> dict[str, Any]:
    response = h.client.post(
        "/api/v1/agents",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "definition": (definition or sample_definition()).model_dump(mode="json"),
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def submit(h: Harness, agent: dict[str, Any]) -> dict[str, Any]:
    response = h.client.post(
        "/api/v1/workflow/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "agent_id": agent["id"],
            "agent_version": agent["version"],
            "input": {"instruction": "PRIVATE workflow instruction"},
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def get(h: Harness, job_id: str, suffix: str = "") -> Any:
    response = h.client.get(f"/api/v1/workflow/jobs/{job_id}{suffix}", headers=headers(h.admin))
    assert response.status_code == 200, response.text
    return response.json()


def step(
    h: Harness,
    a: dict[str, Any],
    step_id: str,
    version: int,
    action: str = "step_start",
    expected: int = 200,
    index: int = 0,
    **values: object,
) -> dict[str, Any]:
    worker = h.workers[index]
    response = h.client.post(
        f"/api/v1/workers/{worker['credential_id']}/jobs/{a['job']['id']}/workflow/report",
        headers=headers(worker),
        json={
            "session_id": str(h.registrations[index].session_id),
            "attempt_id": a["attempt_id"],
            "fencing_token": a["fencing_token"],
            "action": action,
            "step_id": step_id,
            "expected_checkpoint_version": version,
            **values,
        },
    )
    assert response.status_code == expected, response.text
    return dict(response.json())


def first_checkpoint(h: Harness, a: dict[str, Any]) -> dict[str, Any]:
    h.start(a)
    step(h, a, "plan", 0)
    return step(h, a, "plan", 0, "checkpoint", output=PLAN, usage=USAGE)


def run_worker(
    h: Harness, assignment: dict[str, Any], provider: MockModel | None = None, index: int = 0
) -> MockModel:
    instance = provider or MockModel()
    asyncio.run(
        execute_agent(
            APIWorkerClient(h, index),
            UUID(h.workers[index]["credential_id"]),
            h.registrations[index],
            Assignment.model_validate(assignment),
            threading.Event(),
            10,
            [ProviderConfig(id="local", provider="ollama")],
            provider_override=instance,
        )
    )
    return instance


def restart_identity(h: Harness) -> None:
    registration = h.registrations[0].model_copy(update={"session_id": uuid4()})
    response = h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[0]),
    )
    assert response.status_code == 200, response.text
    h.registrations[0] = registration


def expire(h: Harness, a: dict[str, Any]) -> None:
    with h.database.sessions.begin() as session:
        attempt = session.get(Attempt, UUID(a["attempt_id"]))
        assert attempt is not None
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        node = session.get(Node, attempt.node_id)
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
        node.state, node.connection_status = "offline", "offline"
    h.tick()
    h.tick()


def test_three_step_worker_gateway_checkpoint_and_final_result(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    enable(h)
    agent = create(h)
    job = submit(h, agent)
    assert h.tick() == 1
    a = h.poll()
    assert a is not None
    provider = run_worker(h, a)
    assert provider.closed and len(provider.calls) == 2
    state = get(h, job["id"])
    assert state["status"] == "COMPLETED" and state["checkpoint_version"] == 3
    assert [s["step_id"] for s in get(h, job["id"], "/steps")] == ["plan", "describe", "summary"]
    assert all(s["status"] == "COMPLETED" for s in get(h, job["id"], "/steps"))
    assert [c["version"] for c in get(h, job["id"], "/checkpoints")] == [1, 2, 3]
    assert get(h, job["id"], "/result")["output"]["text"]
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Artifact)) == 6
    events = h.client.get(f"/api/v1/jobs/{job['id']}/events", headers=headers(h.admin)).json()
    kinds = {e["type"] for e in events}
    assert {
        "job.workflow.started",
        "job.workflow.checkpoint.committed",
        "job.workflow.model.requested",
        "job.workflow.tool.completed",
        "job.workflow.completed",
    } <= kinds
    assert "PRIVATE workflow instruction" not in caplog.text
    assert "Portable plan" not in caplog.text


def test_restart_restores_checkpoint_without_repeating_committed_steps(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    saved = first_checkpoint(h, a)
    expire(h, a)
    assert h.get(job["id"])["status"] == "PENDING"
    assert h.tick() == 0 and h.poll(1) is None  # Backup has not opted into workflows.
    original_client = h.client
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        h.client = restarted
        try:
            restart_identity(h)
            assert h.tick() == 1
            b = h.poll()
            assert b is not None and b["fencing_token"] == 2
            assert b["workflow"]["state"]["checkpoint_version"] == 1
            assert b["workflow"]["state"]["context"] == saved["context"]
            assert b["workflow"]["state"]["last_error_code"] == "lease_expired"
            step(h, a, "describe", 1, expected=409)
            run = run_worker(h, b)
            assert len(run.calls) == 1  # The plan model call is already committed.
            records = get(h, job["id"], "/steps")
            assert [r["step_id"] for r in records].count("plan") == 1
            assert records[0]["attempt_id"] == a["attempt_id"]
            final = get(h, job["id"], "/result")
            assert final["status"] == "COMPLETED"
            step(h, a, "plan", 0, "checkpoint", expected=409, output=PLAN, usage=USAGE)
            assert get(h, job["id"], "/result") == final
            events = h.client.get(
                f"/api/v1/jobs/{job['id']}/events", headers=headers(h.admin)
            ).json()
            assert {"job.workflow.interrupted", "job.workflow.resumed"} <= {
                e["type"] for e in events
            }
        finally:
            h.client = original_client


def test_checkpoint_concurrency_idempotence_and_sequence_validation(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    step(h, a, "describe", 0, expected=409)
    step(h, a, "plan", 0)
    step(
        h, a, "plan", 0, "checkpoint", expected=422, output={"text": "invalid schema"}, usage=USAGE
    )

    def commit() -> dict[str, Any]:
        return step(h, a, "plan", 0, "checkpoint", output=PLAN, usage=USAGE)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: commit(), range(2)))
    assert results[0] == results[1]
    assert len(get(h, job["id"], "/checkpoints")) == 1
    step(
        h,
        a,
        "plan",
        0,
        "checkpoint",
        expected=409,
        output={"title": "Different", "items": ["changed"]},
        usage=USAGE,
    )
    step(h, a, "summary", 1, expected=409)


def test_owner_tool_permissions_are_required_and_rechecked(h: Harness) -> None:
    enable(h, permission=False)
    job = submit(h, create(h))
    assert h.tick() == 0
    enable(h)
    assert h.tick() == 1
    a = h.poll()
    assert a is not None
    first_checkpoint(h, a)
    step(h, a, "describe", 1)
    enable(h, permission=False)
    step(
        h,
        a,
        "describe",
        1,
        "checkpoint",
        expected=403,
        output={"title": "Portable plan", "item_count": 2, "outline": "Inspect\nReport"},
    )
    assert len(get(h, job["id"], "/checkpoints")) == 1


@pytest.mark.parametrize("phase", ["pending", "running"])
def test_cancellation_preserves_committed_prefix_and_prevents_new_writes(
    h: Harness, phase: str
) -> None:
    enable(h)
    job = submit(h, create(h))
    a = None
    if phase == "running":
        h.tick()
        a = h.poll()
        assert a is not None
        first_checkpoint(h, a)
        step(h, a, "describe", 1)
    response = h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin))
    assert response.status_code == 200
    if a:
        step(
            h,
            a,
            "describe",
            1,
            "checkpoint",
            expected=409,
            output={"title": "Portable plan", "item_count": 2, "outline": "Inspect\nReport"},
        )
        h.report(a, "cancelled")
    assert get(h, job["id"])["status"] == "CANCELLED"
    assert get(h, job["id"], "/result")["output"] is None
    assert len(get(h, job["id"], "/checkpoints")) == (1 if a else 0)


def test_invalid_model_structure_never_calls_tool(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    provider = run_worker(h, a, MockModel(invalid=True))
    assert len(provider.calls) == 1
    assert get(h, job["id"], "/result")["error"]["code"] == "workflow_validation"
    assert get(h, job["id"], "/checkpoints") == []
    assert [r["step_id"] for r in get(h, job["id"], "/steps")] == ["plan"]


def test_step_timeout_is_enforced_before_checkpoint(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    first_checkpoint(h, a)
    step(h, a, "describe", 1)
    with h.database.sessions.begin() as session:
        record = session.scalar(
            select(WorkflowStepRecord).where(WorkflowStepRecord.step_id == "describe")
        )
        assert record is not None
        record.created_at = datetime.now(UTC) - timedelta(seconds=6)
    step(
        h,
        a,
        "describe",
        1,
        "checkpoint",
        expected=408,
        output={"title": "Portable plan", "item_count": 2, "outline": "Inspect\nReport"},
    )
    h.report(a, "fail", error_code="step_timeout")
    assert h.get(job["id"])["status"] == "RETRY_WAIT"
    assert len(get(h, job["id"], "/checkpoints")) == 1


def test_artifact_failure_rolls_back_all_checkpoint_metadata(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    step(h, a, "plan", 0)
    store = cast(FastAPI, h.client.app).state.artifacts
    original = store.write
    writes = 0

    def fail_second(key: UUID, raw: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise ArtifactError("Injected durable write failure")
        original(key, raw)

    monkeypatch.setattr(store, "write", fail_second)
    step(h, a, "plan", 0, "checkpoint", expected=503, output=PLAN, usage=USAGE)
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Artifact)) == 0
        assert session.scalar(select(func.count()).select_from(Checkpoint)) == 0
    assert get(h, job["id"])["checkpoint_version"] == 0
    assert h.get(job["id"])["checkpoint_ref"] is None
    monkeypatch.setattr(store, "write", original)
    step(h, a, "plan", 0, "checkpoint", output=PLAN, usage=USAGE)
    assert get(h, job["id"])["checkpoint_version"] == 1


def test_corrupt_artifact_is_not_restored(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    first_checkpoint(h, a)
    cp = get(h, job["id"], "/checkpoints")[0]
    store: LocalArtifactStore = cast(FastAPI, h.client.app).state.artifacts
    store.path(UUID(cp["artifact"]["id"])).write_bytes(b"corrupt")
    response = h.client.get(f"/api/v1/workflow/jobs/{job['id']}", headers=headers(h.admin))
    assert response.status_code == 503 and "corrupt" not in response.text


def test_versions_are_immutable_disabled_agents_stay_queued(h: Harness) -> None:
    enable(h)
    agent = create(h)
    job = submit(h, agent)
    response = h.client.post(
        f"/api/v1/agents/{agent['id']}/versions/1/control",
        headers=headers(h.admin),
        json={"action": "disable"},
    )
    assert response.status_code == 200
    assert h.tick() == 0 and h.get(job["id"])["status"] == "PENDING"
    definition = sample_definition(name=agent["definition"]["name"]).model_dump(mode="json")
    response = h.client.post(
        f"/api/v1/agents/{agent['id']}/versions",
        headers=headers(h.admin),
        json={"expected_version": 1, "definition": definition},
    )
    assert response.status_code == 201
    assert response.json()["version"] == 2 and response.json()["id"] == agent["id"]
    versions = h.client.get(
        f"/api/v1/agents/{agent['id']}/versions", headers=headers(h.admin)
    ).json()
    assert versions[0]["definition"]["workflow"]["id"] == agent["definition"]["workflow"]["id"]
    assert (
        versions[1]["definition"]["workflow"]["id"] != versions[0]["definition"]["workflow"]["id"]
    )
    assert h.tick() == 0
    with h.database.sessions() as session:
        assert session.get(Agent, UUID(agent["version_id"])) is not None


def test_workspace_isolation_and_unsupported_tools(h: Harness) -> None:
    enable(h)
    agent = create(h)
    job = submit(h, agent)
    outsider = provision(h.database, "admin", email="unrelated-workflow@example.invalid")
    for path in (
        f"agents?workspace_id={h.workspace_id}",
        f"agents/{agent['id']}",
        f"workflow/jobs/{job['id']}",
        f"workflow/jobs/{job['id']}/checkpoints",
        f"workflow/jobs/{job['id']}/steps",
        f"workflow/jobs/{job['id']}/result",
    ):
        assert h.client.get("/api/v1/" + path, headers=headers(outsider)).status_code == 404
        assert h.client.get("/api/v1/" + path, headers=headers(h.workers[0])).status_code == 401
    unsafe = sample_definition().model_dump(mode="json")
    unsafe["allowed_tools"].append({"name": "shell", "version": 1})
    response = h.client.post(
        "/api/v1/agents",
        headers=headers(h.admin),
        json={"workspace_id": str(h.workspace_id), "definition": unsafe},
    )
    assert response.status_code == 422
    assert (
        h.client.get("/api/v1/tools", headers=headers(h.admin)).json()[0]["side_effect"]
        == "read_only"
    )


def test_workflow_cancellation_closes_blocked_model(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None

    async def run() -> None:
        entered = asyncio.Event()

        class BlockingModel(MockModel):
            async def infer(self, identifier: str, request: object) -> AsyncGenerator[Chunk]:
                entered.set()
                await asyncio.Event().wait()
                yield Chunk(done=True)

        provider = BlockingModel()
        assignment = Assignment.model_validate(a).model_copy(
            update={"lease_expires_at": datetime.now(UTC) + timedelta(seconds=0.3)}
        )
        task = asyncio.create_task(
            execute_agent(
                APIWorkerClient(h),
                UUID(h.workers[0]["credential_id"]),
                h.registrations[0],
                assignment,
                threading.Event(),
                10,
                [ProviderConfig(id="local", provider="ollama")],
                provider_override=provider,
            )
        )
        await asyncio.wait_for(entered.wait(), 3)
        response = await asyncio.to_thread(
            h.client.post, f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)
        )
        assert response.status_code == 200
        await asyncio.wait_for(task, 5)
        assert provider.closed

    asyncio.run(run())
    assert get(h, job["id"])["status"] == "CANCELLED"


def test_lease_expiry_during_artifact_write_rejects_checkpoint(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    step(h, a, "plan", 0)
    current = datetime.now(UTC)

    class Clock:
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return current

    store = cast(FastAPI, h.client.app).state.artifacts
    original = store.write
    writes = 0

    def advance_after_state_write(key: UUID, data: bytes) -> None:
        nonlocal current, writes
        original(key, data)
        writes += 1
        if writes == 2:
            current += timedelta(seconds=60)

    monkeypatch.setattr(workflow_service, "datetime", Clock)
    monkeypatch.setattr(store, "write", advance_after_state_write)
    step(h, a, "plan", 0, "checkpoint", expected=409, output=PLAN, usage=USAGE)
    assert h.get(job["id"])["checkpoint_ref"] is None
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Checkpoint)) == 0
