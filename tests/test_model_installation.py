"""Local Ollama pull adapter tests: all download traffic is mocked only in tests."""

import asyncio
import json
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx2 as httpx
import pytest
from godfather_contracts import Contract, Registration
from godfather_contracts.jobs import Assignment, JobReport
from godfather_contracts.model_management import INSTALL_RUNTIME, PROVIDER_RUNTIME_PREFIX
from godfather_model_gateway import ProviderConfig
from godfather_model_gateway.providers import OllamaProvider
from godfather_worker.client import WorkerClient
from godfather_worker.model_management import execute_installation
from godfather_worker.simulated import profile


class Reports(WorkerClient):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1", "test-only")
        self.reports: list[JobReport] = []

    def post_document(self, path: str, payload: Contract) -> object:
        if isinstance(payload, JobReport):
            self.reports.append(payload)
            return {
                "status": "RUNNING",
                "cancel_requested": False,
                "lease_expires_at": datetime.now(UTC) + timedelta(seconds=30),
            }
        return {
            "node_id": uuid4(),
            "state": "online",
            "connection_status": "online",
            "heartbeat_interval_seconds": 10,
        }


def fixture() -> tuple[Assignment, Registration]:
    node_id = uuid4()
    registration = Registration(**profile("LV-01").model_dump(), session_id=uuid4())
    registration.runtimes = [INSTALL_RUNTIME, PROVIDER_RUNTIME_PREFIX + "local"]
    assignment = Assignment.model_validate(
        {
            "job": {
                "id": uuid4(),
                "owner_id": uuid4(),
                "workspace_id": uuid4(),
                "type": "model.install",
                "status": "ASSIGNED",
                "priority": 0,
                "requirements": {"runtimes": registration.runtimes},
                "input": {"node_id": node_id, "provider_id": "local", "identifier": "qwen3:0.6b"},
                "timeout_seconds": 120,
                "retry": {"limit": 0},
                "assigned_node_id": node_id,
                "current_attempt_id": uuid4(),
                "attempt_count": 1,
                "fencing_token": 1,
                "checkpoint_ref": None,
                "cancel_requested_at": None,
                "next_run_at": None,
                "created_at": datetime.now(UTC),
                "result": None,
            },
            "attempt_id": uuid4(),
            "fencing_token": 1,
            "lease_expires_at": datetime.now(UTC) + timedelta(seconds=30),
            "deadline_at": datetime.now(UTC) + timedelta(seconds=120),
        }
    )
    return assignment, registration


@pytest.mark.parametrize("case", ["success", "provider_failure", "size_limit", "not_discovered"])
def test_pull_requires_success_and_real_inventory_before_completion(case: str) -> None:
    assignment, registration = fixture()
    client = Reports()
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/pull":
            assert json.loads(request.content) == {"model": "qwen3:0.6b", "stream": True}
            if case == "provider_failure":
                return httpx.Response(200, content='{"error":"test-only provider failure"}\n')
            return httpx.Response(
                200, content='{"total":1000,"completed":900,"digest":"a"}\n{"status":"success"}\n'
            )
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": []
                    if case == "not_discovered"
                    else [{"name": "qwen3:0.6b", "size": 1000, "digest": "test"}]
                },
            )
        return httpx.Response(200, json={"capabilities": ["completion"], "model_info": {}})

    async def run() -> None:
        config = ProviderConfig(id="local", provider="ollama")
        provider = OllamaProvider(config, httpx.MockTransport(handle))
        assert assignment.job.assigned_node_id is not None
        await execute_installation(
            client,
            assignment.job.assigned_node_id,
            registration,
            assignment,
            threading.Event(),
            10,
            [config],
            max_bytes=1 if case == "size_limit" else 2000,
            provider_override=provider,
        )

    asyncio.run(run())
    assert "/api/pull" in calls
    assert any(r.action == "complete" for r in client.reports) is (case == "success")
    if case != "success":
        assert any(r.action == "fail" for r in client.reports)


def test_worker_refuses_installation_without_local_opt_in() -> None:
    assignment, registration = fixture()
    registration.runtimes = []
    assert assignment.job.assigned_node_id is not None
    with pytest.raises(ValueError, match="opt-in"):
        asyncio.run(
            execute_installation(
                Reports(),
                assignment.job.assigned_node_id,
                registration,
                assignment,
                threading.Event(),
                10,
                [],
            )
        )
