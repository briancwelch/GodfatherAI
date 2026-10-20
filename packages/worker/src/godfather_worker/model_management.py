"""Explicit owner opt-in: download catalog models into the worker's local Ollama."""

import asyncio
import threading
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from godfather_contracts import Registration
from godfather_contracts.jobs import Assignment, JobReport, ReportResponse
from godfather_contracts.model_management import (
    INSTALL_RUNTIME,
    MODEL_CATALOG,
    PROVIDER_RUNTIME_PREFIX,
    ModelInstallInput,
    ModelInstallResult,
)
from godfather_model_gateway import GatewayError, ProviderConfig
from godfather_model_gateway.providers import OllamaProvider

from godfather_worker.client import WorkerClient
from godfather_worker.inference import maintain_execution


async def execute_installation(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
    stop: threading.Event,
    heartbeat_seconds: int,
    configs: list[ProviderConfig],
    max_bytes: int = 16 * 1024**3,
    provider_override: OllamaProvider | None = None,
) -> None:
    payload = assignment.job.input
    if (
        not isinstance(payload, ModelInstallInput)
        or payload.node_id != node_id
        or INSTALL_RUNTIME not in registration.runtimes
        or PROVIDER_RUNTIME_PREFIX + payload.provider_id not in registration.runtimes
        or payload.identifier not in {m["identifier"] for m in MODEL_CATALOG}
    ):
        raise ValueError("Model installation requires the node owner's explicit local opt-in")
    config = next(
        (c for c in configs if c.id == payload.provider_id and c.provider == "ollama"), None
    )
    if config is None:
        raise ValueError("Installation provider is not owner-configured Ollama")
    # ProviderConfig enforces a local loopback origin and rejects credentials in URLs.
    timeout = max(0.1, (assignment.deadline_at - datetime.now(UTC)).total_seconds())
    provider = provider_override or OllamaProvider(
        config.model_copy(update={"timeout_seconds": min(timeout, 3600)})
    )
    route = f"/api/v1/workers/{node_id}/jobs/{assignment.job.id}/report"

    async def report(action: str, **values: object) -> ReportResponse:
        body = JobReport.model_validate(
            {
                "session_id": registration.session_id,
                "attempt_id": assignment.attempt_id,
                "fencing_token": assignment.fencing_token,
                "action": action,
                **values,
            }
        )
        return ReportResponse.model_validate(
            await asyncio.to_thread(client.post_document, route, body)
        )

    async def download() -> None:
        success = False
        layers: dict[str, int] = {}
        last_progress = 0.0
        async with asyncio.timeout(timeout):
            async for item in provider.documents(
                "POST", "api/pull", {"model": payload.identifier, "stream": True}, "ndjson"
            ):
                if "error" in item:
                    raise GatewayError("invalid_response")
                total, completed = item.get("total"), item.get("completed", 0)
                if isinstance(total, int) and not isinstance(total, bool) and total > 0:
                    if not isinstance(completed, int) or not 0 <= completed <= total:
                        raise GatewayError("invalid_response")
                    layers[str(item.get("digest", "layer"))] = total
                    if sum(layers.values()) > max_bytes:
                        raise GatewayError("output_limit")
                    if monotonic() - last_progress >= 1:
                        await report("progress", progress=min(99, completed * 100 // total))
                        last_progress = monotonic()
                if item.get("status") == "success":
                    success = True
            if not success or not any(
                m.identifier == payload.identifier for m in await provider.discover()
            ):
                raise GatewayError("invalid_response")
            await report(
                "complete",
                result=ModelInstallResult(
                    identifier=payload.identifier, provider_id=payload.provider_id
                ),
            )

    work = watch = None
    try:
        if (await report("ack")).status == "CANCELLED" or (
            await report("start")
        ).status == "CANCELLED":
            return
        work = asyncio.create_task(download())
        watch = asyncio.create_task(
            maintain_execution(
                client, node_id, registration, assignment, stop, heartbeat_seconds, report
            )
        )
        done, _ = await asyncio.wait((work, watch), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    except GatewayError as error:
        await report("fail", error_code=error.code)
    except TimeoutError:
        await report("fail", error_code="provider_timeout")
    finally:
        for pending_task in (work, watch):
            if pending_task is not None:
                pending_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await pending_task
        await provider.close()
