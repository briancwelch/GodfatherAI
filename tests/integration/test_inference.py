"""Real PostgreSQL inference scheduling and worker/provider flow with deterministic mocks."""

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from uuid import UUID

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from godfather_api import inference as inference_api
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.models import Attempt, Job, Node
from godfather_api.provision import provision
from godfather_contracts import Contract, ModelDeployment, Registration
from godfather_contracts.inference import InferenceResult, InferenceUsage
from godfather_contracts.jobs import Assignment
from godfather_model_gateway import ProviderConfig
from godfather_model_gateway.providers import OllamaProvider
from godfather_worker.client import WorkerClient
from godfather_worker.inference import execute_inference

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.test_model_gateway import BlockingStream

pytestmark = pytest.mark.integration


def test_legacy_synthetic_assignment_remains_compatible(h: Harness) -> None:
    h.submit()
    assert h.tick() == 1
    a = h.poll()
    assert a is not None
    assert "deployment" not in a
    assert "workflow" not in a
    assert "model_selection" not in a["job"]["requirements"]
    assert "tools" not in a["job"]["requirements"]
    assert "tool_permissions" not in a["job"]["requirements"]


def test_nonstreaming_job_refuses_partial_updates(h: Harness) -> None:
    enable(h)
    submit(h, stream=False)
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    h.report(a, "output", expected=422, output={"sequence": 1, "text": "not requested"})


def test_total_persisted_output_limit(h: Harness) -> None:
    model = enable(h)
    job = submit(h)
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    for sequence in range(1, 9):
        h.report(a, "output", output={"sequence": sequence, "text": "x" * 4096})
    h.report(a, "output", expected=422, output={"sequence": 9, "text": "x"})
    assert len(output(h, job["id"])["text"]) == 32768
    h.report(a, "complete", result=inference_result(model, "x" * 32768))


def test_worker_cancellation_during_output_does_not_exit_worker(h: Harness) -> None:
    enable(h)
    job = submit(h)
    h.tick()
    a = h.poll()
    assert a is not None

    class CancelOnOutput(APIWorkerClient):
        def post_document(self, path: str, payload: Contract) -> object:
            if getattr(payload, "action", None) == "output":
                h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin))
            return super().post_document(path, payload)

    async def run() -> None:
        config = ProviderConfig(id="local", provider="ollama")
        provider = OllamaProvider(
            config,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200, content='{"message":{"content":"hello"},"done":true}\n'
                )
            ),
        )
        await execute_inference(
            CancelOnOutput(h),
            UUID(h.workers[0]["credential_id"]),
            h.registrations[0],
            Assignment.model_validate(a),
            threading.Event(),
            10,
            [config],
            provider,
        )

    asyncio.run(run())
    assert h.get(job["id"])["status"] == "CANCELLED"


def test_stream_emits_live_partial_then_final_snapshot(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = enable(h)
    job = submit(h)
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    h.report(a, "output", output={"sequence": 1, "text": "hello"})
    observed, proceed = threading.Event(), threading.Event()
    original = inference_api.snapshot

    def capture(session: Any, current_job: Job) -> dict[str, object]:
        data = original(session, current_job)
        if data["status"] == "RUNNING":
            observed.set()
            assert proceed.wait(5)
        return data

    monkeypatch.setattr(inference_api, "snapshot", capture)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            h.client.get, f"/api/v1/inference/jobs/{job['id']}/stream", headers=headers(h.admin)
        )
        try:
            assert observed.wait(5)
            h.report(a, "complete", result=inference_result(model, "hello world"))
        finally:
            proceed.set()
        response = future.result(timeout=10)
    frames = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert any(f.get("text") == "hello" and f.get("status") == "RUNNING" for f in frames)
    assert frames[-1]["text"] == "hello world" and frames[-1]["status"] == "COMPLETED"
    assert all(f["attempt_id"] == a["attempt_id"] for f in frames)


def test_private_workspace_and_node_consent_apply_to_inference_endpoints(h: Harness) -> None:
    enable(h)
    job = submit(h)
    outsider = provision(h.database, "admin", email="unrelated@example.invalid")
    for path in (
        f"inference/jobs/{job['id']}/result",
        f"inference/jobs/{job['id']}/stream",
        f"models?workspace_id={h.workspace_id}",
        f"inference/metrics?workspace_id={h.workspace_id}",
    ):
        assert h.client.get("/api/v1/" + path, headers=headers(outsider)).status_code == 404
    with h.database.sessions.begin() as session:
        owned_node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert owned_node is not None
        owned_node.owner_id = UUID(outsider["owner_id"])
        owned_node.scheduling_policy = "dedicated"
    assert (
        h.client.get(
            f"/api/v1/models?workspace_id={h.workspace_id}", headers=headers(h.admin)
        ).json()
        == []
    )
    assert h.tick() == 0 and h.get(job["id"])["status"] == "PENDING"


def enable(h: Harness, index: int = 0) -> ModelDeployment:
    model = ModelDeployment(
        provider_id="local",
        provider="ollama",
        identifier="fixture",
        verified_capabilities=["completion"],
        operations=["chat", "stream"],
        digest="fixture-v1",
    )
    registration = h.registrations[index].model_copy(
        update={
            "inference_protocol_version": 1,
            "model_deployments": [model],
            "resources": h.registrations[index].resources.model_copy(update={"source": "physical"}),
        }
    )
    response = h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[index]),
    )
    assert response.status_code == 200, response.text
    h.registrations[index] = registration
    return model


def submit(h: Harness, stream: bool = True, **values: object) -> dict[str, Any]:
    response = h.client.post(
        "/api/v1/inference/jobs",
        headers=headers(h.admin),
        json={
            "workspace_id": str(h.workspace_id),
            "requirements": {
                "model_selection": {"identifier": "fixture", "stream": stream},
            },
            "input": {"prompt": "private fixture prompt", "stream": stream},
            **values,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def output(h: Harness, job_id: str) -> dict[str, Any]:
    response = h.client.get(f"/api/v1/inference/jobs/{job_id}/result", headers=headers(h.admin))
    assert response.status_code == 200, response.text
    return dict(response.json())


def inference_result(model: ModelDeployment, text: str = "hello") -> dict[str, Any]:
    return InferenceResult(
        text=text,
        deployment=model,
        usage=InferenceUsage(
            duration_seconds=1, input_tokens=2, output_tokens=1, token_source="provider_reported"
        ),
    ).model_dump(mode="json")


class APIWorkerClient(WorkerClient):
    def __init__(self, h: Harness, index: int = 0) -> None:
        super().__init__("http://127.0.0.1:8000", h.workers[index]["token"])
        self.h = h

    def post_document(self, path: str, payload: Contract) -> object:
        response = self.h.client.post(
            path,
            json=payload.model_dump(mode="json"),
            headers={"Authorization": "Bearer " + self.token},
        )
        if response.status_code != 200:
            raise HTTPError(self.url + path, response.status_code, "safe rejection", {}, None)  # type: ignore[arg-type]
        return response.json()


@pytest.mark.parametrize("stream", [False, True])
def test_prompt_through_api_scheduler_worker_provider_result_and_sse(
    h: Harness, stream: bool, caplog: pytest.LogCaptureFixture
) -> None:
    enable(h)
    job = submit(h, stream)
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None
    requests: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "fixture"
        assert body["messages"][-1]["content"] == "private fixture prompt"
        final = {
            "message": {"content": "hello"},
            "done": True,
            "prompt_eval_count": 4,
            "eval_count": 2,
        }
        return httpx.Response(
            200, content=json.dumps(final) + "\n" if stream else json.dumps(final)
        )

    async def run() -> None:
        config = ProviderConfig(id="local", provider="ollama")
        adapter = OllamaProvider(config, httpx.MockTransport(handle))
        await execute_inference(
            APIWorkerClient(h),
            UUID(h.workers[0]["credential_id"]),
            h.registrations[0],
            Assignment.model_validate(assignment),
            threading.Event(),
            10,
            [config],
            adapter,
        )

    asyncio.run(run())
    assert requests and h.get(job["id"])["status"] == "COMPLETED"
    response = output(h, job["id"])
    assert response["text"] == "hello" and response["result"]["usage"]["output_tokens"] == 2
    assert response["attempt_id"] == assignment["attempt_id"]
    assert response["metadata"]["queue_wait_seconds"] >= 0
    # API/pool recreation retains the exact final result and attempt.
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        persisted = restarted.get(
            f"/api/v1/inference/jobs/{job['id']}/result", headers=headers(h.admin)
        )
        assert persisted.json() == response
    events = h.client.get(
        f"/api/v1/inference/jobs/{job['id']}/stream",
        headers={**headers(h.admin), "Last-Event-ID": "old-attempt:99"},
    )
    assert events.status_code == 200 and events.headers["content-type"].startswith(
        "text/event-stream"
    )
    assert "event: reset" in events.text and "event: snapshot" in events.text
    assert assignment["attempt_id"] in events.text and "hello" in events.text
    metrics = h.client.get(
        "/api/v1/inference/metrics",
        params={"workspace_id": str(h.workspace_id)},
        headers=headers(h.admin),
    ).json()
    assert metrics["job_counts"] == {"COMPLETED": 1}
    assert metrics["failure_rate"] == 0 and "private fixture prompt" not in json.dumps(metrics)
    assert "private fixture prompt" not in caplog.text and '"text": "hello"' not in caplog.text


def test_model_directory_updates_multiple_nodes_and_exact_model_queue(h: Harness) -> None:
    enable(h)
    enable(h, 1)
    path = f"/api/v1/models?workspace_id={h.workspace_id}"
    assert h.client.get(path).status_code == 401
    listed = h.client.get(path, headers=headers(h.admin)).json()
    assert len(listed) == 2 and len({m["node_id"] for m in listed}) == 2
    assert all(m["deployment"]["identifier"] == "fixture" for m in listed)
    missing = submit(h, requirements={"model_selection": {"identifier": "not-installed"}})
    jobs = [submit(h) for _ in range(3)]
    assert h.tick() == 2  # Both concurrency slots; the exact missing model stays pending.
    assert h.get(missing["id"])["status"] == "PENDING"
    assert sorted(h.get(j["id"])["status"] for j in jobs) == ["ASSIGNED", "ASSIGNED", "PENDING"]
    reg = h.registrations[0].model_copy(update={"model_deployments": []})
    h.client.post(
        "/api/v1/workers/register", json=reg.model_dump(mode="json"), headers=headers(h.workers[0])
    )
    assert len(h.client.get(path, headers=headers(h.admin)).json()) == 1
    # Older workers still register but cannot run inference or satisfy it with legacy inventory.
    reg = h.registrations[1].model_copy(update={"inference_protocol_version": None})
    h.client.post(
        "/api/v1/workers/register", json=reg.model_dump(mode="json"), headers=headers(h.workers[1])
    )
    assert not h.client.get(path, headers=headers(h.admin)).json()[0]["available"]


def test_bounded_stream_sequence_cancellation_and_result_identity(h: Harness) -> None:
    model = enable(h)
    job = submit(h)
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    h.report(a, "output", output={"sequence": 1, "text": "private partial"})
    h.report(a, "output", output={"sequence": 1, "text": "private partial"})
    h.report(a, "output", expected=409, output={"sequence": 1, "text": "different"})
    h.report(a, "output", expected=409, output={"sequence": 3, "text": "gap"})
    h.report(a, "output", expected=422, output={"sequence": 513, "text": "over cap"})
    h.report(a, "complete", expected=409, result=inference_result(model, "contradiction"))
    wrong_model = model.model_copy(update={"identifier": "substitution"})
    h.report(a, "complete", expected=409, result=inference_result(wrong_model, "private partial"))
    assert output(h, job["id"])["text"] == "private partial"
    h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin))
    assert output(h, job["id"])["text"] == ""
    h.report(a, "output", output={"sequence": 2, "text": "ignored"})
    h.report(a, "complete", result=inference_result(model, "private partial"))
    assert h.get(job["id"])["status"] == "CANCELLED"
    assert output(h, job["id"])["result"] is None
    events = h.client.get(f"/api/v1/inference/jobs/{job['id']}/stream", headers=headers(h.admin))
    assert "private partial" not in events.text and "event: invalidated" in events.text


def test_disconnection_stale_stream_and_result_are_fenced(h: Harness) -> None:
    model = enable(h)
    enable(h, 1)
    job = submit(h, retry={"limit": 1, "backoff_seconds": 0})
    h.tick()
    assignments = [h.poll(i) for i in range(2)]
    index = next(i for i, a in enumerate(assignments) if a is not None)
    a = assignments[index]
    assert a is not None
    h.start(a, index)
    h.report(a, "output", index, output={"sequence": 1, "text": "OLD PRIVATE OUTPUT"})
    with h.database.sessions.begin() as session:
        attempt = session.get(Attempt, UUID(a["attempt_id"]))
        assert attempt is not None
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        node = session.get(Node, attempt.node_id)
        assert node is not None
        node.state, node.connection_status = "offline", "offline"
    assert output(h, job["id"])["text"] == ""  # Before the sweeper as well.
    h.report(a, "output", index, expected=409, output={"sequence": 2, "text": "stale"})
    h.tick()
    h.tick()
    b = h.poll(1 - index)
    assert b is not None and b["fencing_token"] > a["fencing_token"]
    h.report(a, "complete", index, expected=409, result=inference_result(model))
    h.start(b, 1 - index)
    h.report(b, "complete", 1 - index, result=inference_result(model, "replacement"))
    response = output(h, job["id"])
    assert response["text"] == "replacement" and response["attempt_id"] == b["attempt_id"]
    events = h.client.get(
        f"/api/v1/inference/jobs/{job['id']}/stream",
        headers={**headers(h.admin), "Last-Event-ID": a["attempt_id"] + ":1"},
    )
    assert a["attempt_id"] not in events.text and "OLD PRIVATE OUTPUT" not in events.text


@pytest.mark.parametrize(
    "code,retry",
    [
        ("provider_unavailable", True),
        ("provider_timeout", True),
        ("rate_limited", True),
        ("model_unavailable", False),
        ("provider_auth", False),
        ("invalid_response", False),
    ],
)
def test_classified_provider_failures_obey_existing_retry_limits(
    h: Harness, code: str, retry: bool
) -> None:
    enable(h)
    job = submit(h, retry={"limit": 1, "backoff_seconds": 0})
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    h.report(a, "fail", error_code=code)
    assert h.get(job["id"])["status"] == ("RETRY_WAIT" if retry else "FAILED")
    assert output(h, job["id"])["error"] == {"code": code, "retryable": retry}


def test_timeout_expiry_and_permission_boundaries(h: Harness) -> None:
    enable(h)
    job = submit(h)
    h.tick()
    a = h.poll()
    assert a is not None
    h.start(a)
    for path in (
        f"inference/jobs/{job['id']}/result",
        f"inference/jobs/{job['id']}/stream",
        "inference/metrics?workspace_id=" + str(h.workspace_id),
        "models?workspace_id=" + str(h.workspace_id),
    ):
        assert h.client.get("/api/v1/" + path, headers=headers(h.workers[0])).status_code == 401
    with h.database.sessions.begin() as session:
        attempt = session.get(Attempt, UUID(a["attempt_id"]))
        assert attempt is not None
        attempt.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    h.report(a, "output", expected=409, output={"sequence": 1, "text": "late"})
    h.tick()
    assert output(h, job["id"])["error"]["code"] == "timeout"


def test_worker_cancellation_closes_blocked_provider(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable(h)
    job = submit(h)
    h.tick()
    a = h.poll()
    assert a is not None
    # Skip physical probes; the shared portable monitor still renews and heartbeats.
    registration: Registration = h.registrations[0].model_copy(
        update={
            "resources": h.registrations[0].resources.model_copy(update={"source": "simulated"})
        }
    )
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node is not None
        node.resources = registration.resources.model_dump(mode="json")

    async def run() -> None:
        received = asyncio.Event()
        body = BlockingStream(received)
        config = ProviderConfig(id="local", provider="ollama")
        provider = OllamaProvider(
            config, httpx.MockTransport(lambda r: httpx.Response(200, stream=body))
        )
        task = asyncio.create_task(
            execute_inference(
                APIWorkerClient(h),
                UUID(h.workers[0]["credential_id"]),
                registration,
                Assignment.model_validate(a),
                threading.Event(),
                10,
                [config],
                provider,
            )
        )
        await asyncio.wait_for(received.wait(), 2)
        response = await asyncio.to_thread(
            h.client.post, f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)
        )
        assert response.status_code == 200
        await asyncio.wait_for(task, 15)
        assert body.closed

    asyncio.run(run())
    assert h.get(job["id"])["status"] == "CANCELLED"
