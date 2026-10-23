"""Real PostgreSQL parallelism, dependency transport, permissions and fencing."""

import asyncio
import threading
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.models import DistributedJob, Job, Node, WorkspaceMember
from godfather_api.provision import provision
from godfather_contracts.agents import AgentDefinition
from godfather_contracts.distributed import DISTRIBUTED_RUNTIME
from godfather_model_gateway import Chunk
from sqlalchemy import func, select

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import (
    create,
    enable,
    expire,
    first_checkpoint,
    run_worker,
    step,
)
from tests.test_agent_runtime import MockModel
from tests.workflow_helpers import sample_definition

pytestmark = pytest.mark.integration


class RecordingModel(MockModel):
    def __init__(self, answer: str, barrier: threading.Barrier | None = None) -> None:
        super().__init__()
        self.answer, self.barrier = answer, barrier
        self.prompts: list[str] = []

    async def infer(self, identifier: str, request: object) -> AsyncGenerator[Chunk]:
        self.calls.append(identifier)
        self.prompts.append(str(getattr(request, "prompt", "")))
        if self.barrier:
            await asyncio.to_thread(self.barrier.wait, 10)
        yield Chunk(text=self.answer, done=True, input_tokens=5, output_tokens=3)


def setup(h: Harness) -> dict[str, Any]:
    for index in range(2):
        enable(h, index)
        registration = h.registrations[index].model_copy(
            update={"runtimes": [*h.registrations[index].runtimes, DISTRIBUTED_RUNTIME]}
        )
        response = h.client.post(
            "/api/v1/workers/register",
            headers=headers(h.workers[index]),
            json=registration.model_dump(mode="json"),
        )
        assert response.status_code == 200, response.text
        h.registrations[index] = registration
    definition = sample_definition().model_dump(mode="json")
    definition.update(name="Distributed text agent", allowed_tools=[], permissions=[])
    definition["workflow"]["steps"] = [
        {
            "id": "answer",
            "kind": "model",
            "instruction": "Solve the assigned task using the supplied evidence.",
            "output_schema": "text",
        }
    ]
    return create(h, AgentDefinition.model_validate(definition))


def payload(h: Harness, agent: dict[str, Any]) -> dict[str, Any]:
    nodes = [w["credential_id"] for w in h.workers[:2]]
    tasks = [
        {
            "key": f"task{i}",
            "name": f"Parallel task {i}",
            "agent_id": agent["id"],
            "agent_version": agent["version"],
            "input": {"instruction": f"Independent investigation {i}"},
            "node_ids": [nodes[i]],
        }
        for i in range(2)
    ]
    tasks.append(
        {
            "key": "final",
            "name": "Final synthesis",
            "agent_id": agent["id"],
            "agent_version": agent["version"],
            "input": {"instruction": "Combine predecessor evidence."},
            "node_ids": nodes,
            "depends_on": ["task0", "task1"],
        }
    )
    return {
        "workspace_id": str(h.workspace_id),
        "name": "Distributed investigation",
        "instruction": "Explain the evidence.",
        "node_ids": nodes,
        "tasks": tasks,
        "final_task": "final",
    }


def submit(h: Harness, value: dict[str, Any], expected: int = 201) -> dict[str, Any]:
    response = h.client.post("/api/v1/distributed/jobs", headers=headers(h.admin), json=value)
    assert response.status_code == expected, response.text
    return dict(response.json())


def detail(h: Harness, parent_id: str) -> dict[str, Any]:
    response = h.client.get(f"/api/v1/distributed/jobs/{parent_id}", headers=headers(h.admin))
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_parallel_workers_then_dependency_synthesis_and_restart(h: Harness) -> None:
    parent = submit(h, payload(h, setup(h)))
    assert h.tick() == 2
    polled = [h.poll(i) for i in range(2)]
    assert all(polled)
    assignments = [a for a in polled if a is not None]
    assert len(assignments) == 2 and assignments[0]["job"]["id"] != assignments[1]["job"]["id"]
    assert (
        next(t for t in detail(h, parent["id"])["tasks"] if t["key"] == "final")["ready"] is False
    )
    barrier = threading.Barrier(2)
    models = [RecordingModel(f"EVIDENCE-FROM-WORKER-{i}", barrier) for i in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_worker, h, assignments[i], models[i], i) for i in range(2)]
        for future in futures:
            future.result(timeout=20)
    # Durable graph and committed outputs survive a fresh API app/session factory.
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as client:
        response = client.get(f"/api/v1/distributed/jobs/{parent['id']}", headers=headers(h.admin))
        assert response.status_code == 200 and len(response.json()["tasks"]) == 3
    assert h.tick() == 1
    final_index, final_assignment = next((i, a) for i in range(2) if (a := h.poll(i)) is not None)
    assert len(final_assignment["job"]["input"]["dependency_outputs"]) == 2
    synthesis = RecordingModel("Combined verified answer")
    run_worker(h, final_assignment, synthesis, final_index)
    assert all(f"EVIDENCE-FROM-WORKER-{i}" in synthesis.prompts[0] for i in range(2))
    assert h.tick() == 0
    result = detail(h, parent["id"])
    assert result["status"] == "COMPLETED"
    assert sum(n["contribution_percent"] or 0 for n in result["nodes"]) == pytest.approx(
        100, abs=0.02
    )
    final = next(t for t in result["tasks"] if t["key"] == "final")
    output = h.client.get(
        f"/api/v1/workflow/jobs/{final['job_id']}/artifacts/{final['result']['final_output']['id']}",
        headers=headers(h.admin),
    )
    assert output.status_code == 200 and output.json()["text"] == "Combined verified answer"


def test_cancellation_fences_running_children_and_is_idempotent(h: Harness) -> None:
    parent = submit(h, payload(h, setup(h)))
    h.tick()
    assignments = [h.poll(i) for i in range(2)]
    for i, assignment in enumerate(assignments):
        assert assignment
        h.start(assignment, i)
    for _ in range(2):
        response = h.client.post(
            f"/api/v1/distributed/jobs/{parent['id']}/cancel", headers=headers(h.admin)
        )
        assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
    for i, assignment in enumerate(assignments):
        assert assignment
        h.report(assignment, "complete", i, expected=409, result={"value": "stale", "steps": 1})
    assert h.tick() == 0
    assert {t["status"] for t in detail(h, parent["id"])["tasks"]} == {"CANCELLED"}


def test_private_workspace_and_withdrawn_owner_consent(h: Harness) -> None:
    parent = submit(h, payload(h, setup(h)))
    other = provision(h.database, "admin", email="other-distributed@example.invalid")
    assert (
        h.client.get(f"/api/v1/distributed/jobs/{parent['id']}", headers=headers(other)).status_code
        == 404
    )
    assert h.client.get("/api/v1/distributed/jobs", headers=headers(other)).json()["total"] == 0
    assert (
        h.client.post(
            f"/api/v1/distributed/jobs/{parent['id']}/cancel", headers=headers(other)
        ).status_code
        == 404
    )
    value = payload(
        h, h.client.get(f"/api/v1/agents/{detail_agent(h)}", headers=headers(h.admin)).json()
    )
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node
        node.owner_id = UUID(other["owner_id"])
        session.add(
            WorkspaceMember(workspace_id=h.workspace_id, user_id=node.owner_id, role="member")
        )
        node.scheduling_policy = "shared"
        node.contribution_policy = {"allowed_job_owner_ids": [], "allowed_workspace_ids": []}
    submit(h, value, 404)
    assert h.tick() == 1  # Only the still-authorized participant may receive work.


def detail_agent(h: Harness) -> str:
    from godfather_api.models import Agent

    with h.database.sessions() as session:
        key = session.scalar(select(Agent.agent_key))
        assert key
        return str(key)


@pytest.mark.parametrize("case", ["cycle", "unselected", "duplicate", "orphan", "forged_context"])
def test_invalid_graphs_are_atomic(h: Harness, case: str) -> None:
    value = payload(h, setup(h))
    if case == "cycle":
        value["tasks"][0]["depends_on"] = ["final"]
    elif case == "unselected":
        value["tasks"][0]["node_ids"] = [str(uuid4())]
    elif case == "duplicate":
        value["tasks"][1]["key"] = "task0"
    elif case == "orphan":
        value["tasks"][-1]["depends_on"] = ["task0"]
    else:
        value["tasks"][0]["input"]["dependency_outputs"] = [
            {"id": str(uuid4()), "checksum": "a" * 64, "size_bytes": 1}
        ]
    submit(h, value, 422)
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(DistributedJob)) == 0
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_failure_stops_siblings_and_cannot_retry_child_independently(h: Harness) -> None:
    parent = submit(h, payload(h, setup(h)))
    h.tick()
    assignment = h.poll()
    assert assignment
    h.start(assignment)
    h.report(assignment, "fail", error_code="permanent_error")
    assert h.tick() == 0
    result = detail(h, parent["id"])
    assert result["status"] == "FAILED"
    assert {task["status"] for task in result["tasks"]} <= {"FAILED", "CANCELLED"}
    response = h.client.post(
        f"/api/v1/jobs/{assignment['job']['id']}/retry", headers=headers(h.admin)
    )
    assert response.status_code == 409


def test_checkpoint_failover_stays_in_selected_pool(h: Harness) -> None:
    text = setup(h)
    plan = create(h)
    value = payload(h, text)
    value["tasks"][0].update(
        agent_id=plan["id"], agent_version=plan["version"], node_ids=value["node_ids"]
    )
    parent = submit(h, value)
    assert h.tick() == 2
    first, second = h.poll(), h.poll(1)
    assert first and second
    first_checkpoint(h, first)
    run_worker(h, second, RecordingModel("Other task completed"), 1)
    expire(h, first)
    with h.database.sessions.begin() as session:
        job = session.get(Job, UUID(first["job"]["id"]))
        assert job
        job.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
    h.tick()
    recovered = h.poll(1)
    assert recovered and recovered["job"]["id"] == first["job"]["id"]
    assert recovered["workflow"]["state"]["checkpoint_version"] == 1
    assert recovered["fencing_token"] > first["fencing_token"]
    step(h, first, "describe", 1, expected=409)
    model = run_worker(h, recovered, index=1)
    assert len(model.calls) == 1  # The already committed plan is not regenerated.
    assert detail(h, parent["id"])["status"] != "FAILED"


def test_unselected_worker_and_old_context_worker_do_not_claim(h: Harness) -> None:
    agent = setup(h)
    outsider = provision(
        h.database, "worker", owner_id=UUID(h.admin["owner_id"]), name="Unselected"
    )
    registration = h.registrations[0].model_copy(
        update={"name": "Unselected", "session_id": uuid4()}
    )
    response = h.client.post(
        "/api/v1/workers/register",
        headers=headers(outsider),
        json=registration.model_dump(mode="json"),
    )
    assert response.status_code == 200
    parent = submit(h, payload(h, agent))
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node
        node.state = "offline"
    assert h.tick() == 1
    poll = h.client.post(
        f"/api/v1/workers/{outsider['credential_id']}/jobs/poll",
        headers=headers(outsider),
        json={"session_id": str(registration.session_id)},
    )
    assert poll.status_code == 200 and poll.json()["assignment"] is None
    rows = detail(h, parent["id"])
    assert next(t for t in rows["tasks"] if t["key"] == "task0")["status"] == "PENDING"
    assert (
        next(n for n in rows["nodes"] if n["id"] == h.workers[0]["credential_id"])["resources"]
        is None
    )


def test_artifacts_not_shared_outside_exact_dependencies(h: Harness) -> None:
    parent = submit(h, payload(h, setup(h)))
    h.tick()
    first, second = h.poll(), h.poll(1)
    assert first and second
    run_worker(h, first, RecordingModel("Private child output"))
    h.start(second, 1)
    ref = h.get(first["job"]["id"])["result"]["final_output"]
    response = h.client.post(
        f"/api/v1/workers/{h.workers[1]['credential_id']}/jobs/{second['job']['id']}/workflow/artifact",
        headers=headers(h.workers[1]),
        json={
            "session_id": str(h.registrations[1].session_id),
            "attempt_id": second["attempt_id"],
            "fencing_token": second["fencing_token"],
            "artifact": ref,
        },
    )
    assert response.status_code == 404 and "Private child output" not in response.text
    assert detail(h, parent["id"])["status"] != "FAILED"


def test_context_protocol_gate_and_unknown_contribution(h: Harness) -> None:
    parent = submit(h, payload(h, setup(h)))
    assert all(n["contribution_percent"] is None for n in detail(h, parent["id"])["nodes"])
    h.tick()
    for index in range(2):
        assignment = h.poll(index)
        assert assignment
        run_worker(h, assignment, RecordingModel(f"Evidence {index}"), index)
        registration = h.registrations[index].model_copy(
            update={
                "runtimes": [r for r in h.registrations[index].runtimes if r != DISTRIBUTED_RUNTIME]
            }
        )
        response = h.client.post(
            "/api/v1/workers/register",
            headers=headers(h.workers[index]),
            json=registration.model_dump(mode="json"),
        )
        assert response.status_code == 200
        h.registrations[index] = registration
    assert h.tick() == 0
    final = next(t for t in detail(h, parent["id"])["tasks"] if t["key"] == "final")
    assert final["ready"] and final["status"] == "PENDING"
    assert all(h.poll(index) is None for index in range(2))


def test_workspace_member_reads_without_parent_control(h: Harness) -> None:
    agent = setup(h)
    parent = submit(h, payload(h, agent))
    member = provision(h.database, "admin", email="read-only-member@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=h.workspace_id, user_id=UUID(member["owner_id"]), role="member"
            )
        )
    response = h.client.get(f"/api/v1/distributed/jobs/{parent['id']}", headers=headers(member))
    assert response.status_code == 200 and not response.json()["can_control"]
    assert (
        h.client.post(
            f"/api/v1/distributed/jobs/{parent['id']}/cancel", headers=headers(member)
        ).status_code
        == 403
    )
    options = h.client.get(
        f"/api/v1/distributed/jobs/options?workspace_id={h.workspace_id}", headers=headers(member)
    )
    assert options.status_code == 200 and options.json()["nodes"] == []


def test_concurrent_scheduler_ticks_do_not_duplicate_children(h: Harness) -> None:
    parent = submit(h, payload(h, setup(h)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(h.tick) for _ in range(2)]
        assert sum(future.result() for future in futures) == 2
    rows = detail(h, parent["id"])
    assert sorted(t["attempt_count"] for t in rows["tasks"]) == [0, 1, 1]
    assert sorted(t["status"] for t in rows["tasks"]) == ["ASSIGNED", "ASSIGNED", "PENDING"]


@pytest.mark.parametrize("membership_sharing", [False, True])
def test_explicit_shared_nodes_are_selectable_by_nonadmin_members(
    h: Harness, membership_sharing: bool
) -> None:
    from godfather_api.models import HumanSession, User
    from godfather_api.nodes import token_digest

    agent = setup(h)
    member = provision(h.database, "admin", email="shared-consumer@example.invalid")
    member_id = UUID(member["owner_id"])
    token = "s" * 43
    if membership_sharing:
        for index, registration in enumerate(h.registrations):
            registration = registration.model_copy(
                update={"share_with_workspaces": True, "scheduling_policy": "shared"}
            )
            response = h.client.post(
                "/api/v1/workers/register",
                headers=headers(h.workers[index]),
                json=registration.model_dump(mode="json"),
            )
            assert response.status_code == 200
            h.registrations[index] = registration
    with h.database.sessions.begin() as session:
        user = session.get(User, member_id)
        assert user
        user.role, user.roles = "member", ["member"]
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=member_id, role="member"))
        session.add(
            HumanSession(
                owner_id=member_id,
                token_hash=token_digest(token),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        for worker in h.workers:
            node = session.get(Node, UUID(worker["credential_id"]))
            assert node
            node.scheduling_policy = "shared"
            node.contribution_policy = (
                {"share_with_workspaces": True}
                if membership_sharing
                else {
                    "allowed_job_owner_ids": [str(member_id)],
                    "allowed_workspace_ids": [str(h.workspace_id)],
                }
            )
    auth = {"X-Godfather-Session": token, "Origin": "http://127.0.0.1:3000"}
    response = h.client.get(
        f"/api/v1/distributed/jobs/options?workspace_id={h.workspace_id}", headers=auth
    )
    assert response.status_code == 200 and len(response.json()["nodes"]) == 2
    response = h.client.post("/api/v1/distributed/jobs", headers=auth, json=payload(h, agent))
    assert response.status_code == 201, response.text
    assert h.tick() == 2
    if membership_sharing:
        assignment = h.poll(1)
        assert assignment
        run_worker(h, assignment, RecordingModel("Shared workspace contribution"), 1)
        assert h.get(assignment["job"]["id"])["status"] == "COMPLETED"
    # Node-owner withdrawal is rechecked even after assignments were committed.
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node
        node.contribution_policy = {}
    assert h.poll() is None


def test_disabled_workspace_model_is_not_misreported_as_node_consent(h: Harness) -> None:
    from godfather_api.models import Workspace

    agent = setup(h)
    with h.database.sessions.begin() as session:
        workspace = session.get(Workspace, h.workspace_id)
        assert workspace
        workspace.allowed_models = []
    response = h.client.post(
        "/api/v1/distributed/jobs", headers=headers(h.admin), json=payload(h, agent)
    )
    assert response.status_code == 403
    assert "model is not enabled" in response.json()["detail"]
    assert "node-owner contribution consent" not in response.json()["detail"]
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(DistributedJob)) == 0
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_parallel_tasks_use_different_installed_models(h: Harness) -> None:
    first_agent = setup(h)
    definition = AgentDefinition.model_validate(first_agent["definition"])
    data = definition.model_dump(mode="json")
    data["name"] = "Specialist model agent"
    data["requirements"]["model_selection"]["identifier"] = "specialist-model"
    specialist_agent = create(h, AgentDefinition.model_validate(data))
    registration = h.registrations[1].model_copy(
        update={
            "model_deployments": [
                h.registrations[1]
                .model_deployments[0]
                .model_copy(update={"identifier": "specialist-model"})
            ]
        }
    )
    response = h.client.post(
        "/api/v1/workers/register",
        headers=headers(h.workers[1]),
        json=registration.model_dump(mode="json"),
    )
    assert response.status_code == 200
    h.registrations[1] = registration
    value = payload(h, first_agent)
    value["tasks"][1].update(
        agent_id=specialist_agent["id"], agent_version=specialist_agent["version"]
    )
    parent = submit(h, value)
    assert h.tick() == 2
    one, two = h.poll(), h.poll(1)
    assert one and two
    assert one["deployment"]["identifier"] == "fixture"
    assert two["deployment"]["identifier"] == "specialist-model"
    assert {t["model"]["identifier"] for t in detail(h, parent["id"])["tasks"]} == {
        "fixture",
        "specialist-model",
    }


def test_named_output_variables_wait_and_resolve_committed_predecessor(h: Harness) -> None:
    from godfather_contracts.variables import VARIABLE_RUNTIME

    value = payload(h, setup(h))
    for index in range(2):
        registration = h.registrations[index].model_copy(
            update={"runtimes": [*h.registrations[index].runtimes, VARIABLE_RUNTIME]}
        )
        assert (
            h.client.post(
                "/api/v1/workers/register",
                headers=headers(h.workers[index]),
                json=registration.model_dump(mode="json"),
            ).status_code
            == 200
        )
        h.registrations[index] = registration
    value["variables"] = {"project": "Arithmetic"}
    value["tasks"][0]["input"]["instruction"] = "Add 1+1"
    value["tasks"][1]["input"]["instruction"] = (
        "For {{workspace.name}} / {{vars.project}}, add 2+2 then add {{tasks.task0.output}}"
    )
    parent = submit(h, value)
    assert h.tick() == 1 and h.poll(1) is None
    first = h.poll(0)
    assert first
    run_worker(h, first, RecordingModel("2"), 0)
    assert h.tick() == 1
    second = h.poll(1)
    assert second
    model = RecordingModel("6")
    run_worker(h, second, model, 1)
    assert '"text": "2"' in model.prompts[0]
    assert "Synthetic only / Arithmetic" in model.prompts[0]
    assert "{{tasks.task0.output}}" not in model.prompts[0]
    current = detail(h, parent["id"])
    task = next(t for t in current["tasks"] if t["key"] == "task1")
    assert task["depends_on"] == ["task0"] and task["status"] == "COMPLETED"
