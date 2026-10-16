"""Deterministic portable scheduler matching and synthetic handler contract tests."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from godfather_api.scheduler import matches
from godfather_contracts import NodeView
from godfather_contracts.jobs import JobSubmission, Requirements, SyntheticInput, SyntheticResult
from godfather_worker.jobs import synthetic_result
from godfather_worker.simulated import profile
from pydantic import ValidationError


def node_view() -> NodeView:
    return NodeView.model_validate(
        {
            **profile("LV-01").model_dump(),
            "node_id": uuid4(),
            "owner_id": uuid4(),
            "name": "test",
            "protocol_version": 1,
            "state": "online",
            "connection_status": "online",
            "last_heartbeat_at": datetime.now(UTC),
            "job_protocol_version": 1,
        }
    )


@pytest.mark.parametrize(
    "requirements,expected",
    [
        ({"capabilities": ["coding"]}, True),
        ({"capabilities": ["research"]}, True),
        ({"capabilities": ["images"]}, False),
        ({"os": "macos"}, False),
        ({"architecture": "arm64"}, False),
        ({"cpu_count": 9}, False),
        ({"ram_bytes": 25 * 1024**3}, False),
        ({"backend": "cuda", "gpu_memory_bytes": 1024**3}, True),
        ({"backend": "metal"}, False),
        ({"gpu_memory_bytes": 13 * 1024**3}, False),
        ({"runtimes": ["python"]}, True),
        ({"toolchains": ["unapproved"]}, False),
        ({"dependencies": ["missing-package:1"]}, False),
        ({"sandbox_modes": ["docker"]}, False),
        ({"models": [{"runtime": "simulated", "identifier": "demo-only"}]}, True),
        ({"models": [{"runtime": "ollama", "identifier": "absent"}]}, False),
    ],
)
def test_matching(requirements: dict[str, object], expected: bool) -> None:
    assert matches(Requirements.model_validate(requirements), node_view(), []) is expected


def test_reservations_unknown_capacity_and_opt_in() -> None:
    node = node_view()
    assert not matches(Requirements(cpu_count=2), node, [Requirements(cpu_count=7)])
    assert not matches(
        Requirements(gpu_memory_bytes=8 * 1024**3),
        node,
        [Requirements(gpu_memory_bytes=8 * 1024**3)],
    )
    node.resources.gpus[0].memory_used_bytes = None
    assert not matches(Requirements(gpu_memory_bytes=1), node, [])
    node.resources.available_ram_bytes = None
    assert not matches(Requirements(ram_bytes=1), node, [])
    node.job_protocol_version = None
    assert not matches(Requirements(), node, [])
    node.job_protocol_version = 1
    node.resources.source = "physical"
    assert not matches(Requirements(), node, [])


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "coding"},
        {"priority": 101},
        {"timeout_seconds": 0},
        {"retry": {"limit": 11}},
        {"requirements": {"ram_bytes": -1}},
        {"owner_id": str(uuid4())},
        {"checkpoint_ref": "/local/file"},
        {"input": {"steps": 101}},
        {"input": {"shell": "unapproved"}},
    ],
)
def test_submission_rejects_invalid_or_out_of_scope_inputs(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        JobSubmission.model_validate({"workspace_id": uuid4(), **overrides})


def test_synthetic_handlers_are_bounded_and_idempotent() -> None:
    payload = SyntheticInput(value="portable", fail_until_attempt=1)
    assert synthetic_result(payload, 1, "synthetic.echo") == "transient_error"
    result = synthetic_result(payload, 2, "synthetic.echo")
    assert isinstance(result, SyntheticResult) and result.value == "portable"
    assert result == synthetic_result(payload, 2, "synthetic.echo")
    assert (
        synthetic_result(SyntheticInput(permanent=True), 1, "synthetic.fail") == "permanent_error"
    )
    assert synthetic_result(payload, 2, "coding") == "permanent_error"


@pytest.mark.parametrize("cancel_on_renew", [False, True])
def test_worker_synthetic_execution_protocol_and_cooperative_cancellation(
    cancel_on_renew: bool,
) -> None:
    import threading
    from datetime import timedelta
    from unittest.mock import Mock

    from godfather_contracts import Registration
    from godfather_contracts.jobs import Assignment
    from godfather_worker.client import WorkerClient
    from godfather_worker.jobs import execute

    registration = Registration(**profile("LV-01").model_dump(), session_id=uuid4())
    now = datetime.now(UTC)
    assignment = Assignment.model_validate(
        {
            "attempt_id": uuid4(),
            "fencing_token": 1,
            "lease_expires_at": now + timedelta(seconds=30),
            "deadline_at": now + timedelta(seconds=60),
            "job": {
                "id": uuid4(),
                "owner_id": uuid4(),
                "workspace_id": uuid4(),
                "type": "synthetic.echo",
                "status": "ASSIGNED",
                "priority": 0,
                "requirements": {},
                "input": {"steps": 2},
                "timeout_seconds": 60,
                "retry": {},
                "assigned_node_id": uuid4(),
                "current_attempt_id": None,
                "attempt_count": 1,
                "fencing_token": 1,
                "checkpoint_ref": None,
                "cancel_requested_at": None,
                "next_run_at": None,
                "created_at": now,
                "result": None,
            },
        }
    )
    client = Mock(spec=WorkerClient)
    actions: list[str] = []

    def send(path: str, payload: object) -> dict[str, object]:
        from godfather_contracts.jobs import JobReport

        assert isinstance(payload, JobReport)
        actions.append(payload.action)
        return {
            "status": "CANCELLED" if payload.action == "cancelled" else "RUNNING",
            "cancel_requested": cancel_on_renew and payload.action == "renew",
            "lease_expires_at": assignment.lease_expires_at,
        }

    client.post_document.side_effect = send
    execute(client, uuid4(), registration, assignment, threading.Event(), 0, 10)
    assert actions[:2] == ["ack", "start"]
    if cancel_on_renew:
        assert (
            actions[-1] == "cancelled" and "complete" not in actions and "progress" not in actions
        )
    else:
        assert actions[-1] == "complete" and actions.count("progress") == 2
    client.post.assert_called_once()


def test_dependency_versions_match_exactly() -> None:
    node = node_view()
    node.dependencies = ["package:1.0"]
    assert matches(Requirements(dependencies=["package:1.0"]), node, [])
    assert not matches(Requirements(dependencies=["package:2.0"]), node, [])
