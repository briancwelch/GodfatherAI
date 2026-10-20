"""Opt-in portable inference; provider addresses/keys stay in worker-owned config."""

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from godfather_contracts import Heartbeat, ModelDeployment, Registration
from godfather_contracts.inference import InferenceInput, StreamUpdate
from godfather_contracts.jobs import Assignment, JobReport, ReportResponse
from godfather_model_gateway import GatewayError, Provider, ProviderConfig, generate
from godfather_model_gateway.providers import create_provider

from godfather_worker.client import WorkerClient
from godfather_worker.discovery import discover_resources
from godfather_worker.paid_inference import MeteredProvider
from godfather_worker.provider_credentials import load as load_provider_credential


async def discover_models(configs: list[ProviderConfig]) -> list[ModelDeployment]:
    async def discover_one(config: ProviderConfig) -> list[ModelDeployment]:
        try:
            load_provider_credential(config)
        except OSError:
            return []
        provider = create_provider(config)
        try:
            # Startup/refresh must not block heartbeats for a provider's inference timeout.
            async with asyncio.timeout(5):
                return await provider.discover()
        except (GatewayError, TimeoutError) as error:
            # Omit unavailable providers; replacement registration withdraws old models.
            code = error.code if isinstance(error, GatewayError) else "provider_timeout"
            logging.getLogger("godfather.worker").warning("provider.discovery_failed code=%s", code)
            return []
        finally:
            await provider.close()

    batches = await asyncio.gather(*(discover_one(config) for config in configs))
    deployments = [model for batch in batches for model in batch]
    if len(deployments) > 128:
        raise ValueError("Combined inventory exceeds the protocol limit of 128 deployments")
    return deployments


async def maintain_execution(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
    stop: threading.Event,
    heartbeat_seconds: int,
    report: Callable[[str], Awaitable[ReportResponse]],
) -> None:
    interval = max(0.1, (assignment.lease_expires_at - datetime.now(UTC)).total_seconds() / 3)
    renew_at, heartbeat_at = 0.0, 0.0
    while not stop.is_set():
        now = monotonic()
        if now >= renew_at:
            if (await report("renew")).cancel_requested:
                await report("cancelled")
                return
            renew_at = now + interval
        if now >= heartbeat_at:
            resources = registration.resources
            if resources.source == "physical":
                resources = (await asyncio.to_thread(discover_resources))[0]
            await asyncio.to_thread(
                client.post,
                f"/api/v1/workers/{node_id}/heartbeat",
                Heartbeat(session_id=registration.session_id, resources=resources),
            )
            heartbeat_at = now + heartbeat_seconds
        await asyncio.sleep(0.1)


async def execute_inference(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
    stop: threading.Event,
    heartbeat_seconds: int,
    configs: list[ProviderConfig],
    provider_override: Provider | None = None,
) -> None:
    deployment = assignment.deployment
    payload = assignment.job.input
    if deployment is None or not isinstance(payload, InferenceInput):
        raise ValueError("Invalid inference assignment")
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

    if (await report("ack")).status == "CANCELLED":
        return
    if (await report("start")).status == "CANCELLED":
        return
    config = next(
        (
            c
            for c in configs
            if c.id == deployment.provider_id and c.provider == deployment.provider
        ),
        None,
    )
    if config is None:
        await report("fail", error_code="model_unavailable")
        return
    provider = provider_override or create_provider(config)
    if config.provider in ("openai", "anthropic"):
        provider = MeteredProvider(provider, client, node_id, registration, assignment)
    pending = ""
    sequence = 0
    last_flush = 0.0

    async def flush() -> None:
        nonlocal pending, sequence, last_flush
        while pending:
            part, pending = pending[:4096], pending[4096:]
            sequence += 1
            response = await report("output", output=StreamUpdate(sequence=sequence, text=part))
            if response.cancel_requested:
                await report("cancelled")
                raise asyncio.CancelledError
        last_flush = monotonic()

    async def on_text(text: str) -> None:
        nonlocal pending
        if payload.stream:
            pending += text
            if len(pending) >= 1024 or (sequence < 480 and monotonic() - last_flush >= 0.25):
                await flush()

    async def run() -> None:
        timeout = min(
            config.timeout_seconds,
            max(0.001, (assignment.deadline_at - datetime.now(UTC)).total_seconds()),
        )
        result = await generate(provider, deployment, payload, timeout, on_text)
        await flush()
        await report("complete", result=result)

    work = asyncio.create_task(run())
    watch = asyncio.create_task(
        maintain_execution(
            client, node_id, registration, assignment, stop, heartbeat_seconds, report
        )
    )
    try:
        done, _ = await asyncio.wait((work, watch), return_when=asyncio.FIRST_COMPLETED)
        if watch in done:
            await watch  # Transport/permission errors abort local provider execution.
        elif work in done and not work.cancelled():
            await work
    except GatewayError as error:
        await report("fail", error_code=error.code)
    finally:
        for task in (work, watch):
            task.cancel()
        for task in (work, watch):
            with suppress(asyncio.CancelledError, Exception):
                await task
        await provider.close()
