"""Owner-opted-in workflow execution using the existing gateway and fenced job loop."""

import asyncio
import json
import threading
from contextlib import suppress
from datetime import UTC, datetime
from urllib.error import HTTPError
from uuid import UUID

from godfather_agent_runtime import WorkflowError, execute_workflow
from godfather_contracts import Contract, Registration
from godfather_contracts.agents import (
    ArtifactReference,
    StepOutput,
    WorkflowInput,
    WorkflowReport,
    WorkflowState,
)
from godfather_contracts.coding import CodingRepository
from godfather_contracts.inference import InferenceUsage
from godfather_contracts.jobs import Assignment, JobReport, ReportResponse
from godfather_model_gateway import GatewayError, Provider, ProviderConfig
from godfather_model_gateway.providers import create_provider

from godfather_worker.client import WorkerClient
from godfather_worker.inference import maintain_execution
from godfather_worker.paid_inference import MeteredProvider


class ArtifactRead(Contract):
    job_protocol_version: int = 1
    session_id: UUID
    attempt_id: UUID
    fencing_token: int
    artifact: ArtifactReference


async def execute_agent(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
    stop: threading.Event,
    heartbeat_seconds: int,
    configs: list[ProviderConfig],
    pause_after_checkpoint: int | None = None,
    provider_override: Provider | None = None,
    repositories: list[CodingRepository] | None = None,
) -> None:
    bundle, deployment, payload = assignment.workflow, assignment.deployment, assignment.job.input
    if bundle is None or deployment is None or not isinstance(payload, WorkflowInput):
        raise ValueError("Workflow assignment is incomplete")
    identity = {
        "session_id": registration.session_id,
        "attempt_id": assignment.attempt_id,
        "fencing_token": assignment.fencing_token,
    }
    root = f"/api/v1/workers/{node_id}/jobs/{assignment.job.id}"

    async def report(action: str, **values: object) -> ReportResponse:
        body = JobReport.model_validate({**identity, "action": action, **values})
        return ReportResponse.model_validate(
            await asyncio.to_thread(client.post_document, root + "/report", body)
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
    # Compatible workflows remain local; native paid providers use the metered wrapper below.
    if config.provider == "openai_compatible" and not config.url.startswith(
        ("http://127.0.0.1", "http://localhost", "http://[::1]")
    ):
        await report("fail", error_code="workflow_validation")
        return
    provider = provider_override or create_provider(config)
    if config.provider in ("openai", "anthropic"):
        provider = MeteredProvider(provider, client, node_id, registration, assignment)

    async def read_artifact(ref: ArtifactReference) -> object:
        body = ArtifactRead.model_validate({**identity, "artifact": ref})
        result = await asyncio.to_thread(client.post_document, root + "/workflow/artifact", body)
        if not isinstance(result, dict) or "data" not in result:
            raise WorkflowError("artifact_unavailable")
        return result["data"]

    async def transition(
        action: str, step_id: str, version: int, output: StepOutput | None, usage: object | None
    ) -> WorkflowState:
        body = WorkflowReport.model_validate(
            {
                **identity,
                "action": action,
                "step_id": step_id,
                "expected_checkpoint_version": version,
                "output": output,
                "usage": usage if isinstance(usage, InferenceUsage) else None,
            }
        )
        state = WorkflowState.model_validate(
            await asyncio.to_thread(client.post_document, root + "/workflow/report", body)
        )
        if action == "checkpoint":
            print(
                json.dumps(
                    {
                        "event": "worker.checkpoint_committed",
                        "job_id": str(assignment.job.id),
                        "attempt_id": str(assignment.attempt_id),
                        "checkpoint_version": state.checkpoint_version,
                    }
                ),
                flush=True,
            )
            if pause_after_checkpoint == state.checkpoint_version:
                await (
                    asyncio.Event().wait()
                )  # Simulator-only deterministic fault-injection barrier.
        return state

    async def run() -> None:
        from godfather_contracts.agents import WorkflowStep

        from godfather_worker.coding import execute as execute_coding

        async def coding(step: WorkflowStep) -> tuple[StepOutput, object]:
            config = next((r for r in repositories or [] if r.id == payload.repository_id), None)
            if (
                config is None
                or assignment.job.owner_id not in config.allowed_user_ids
                or assignment.job.workspace_id not in config.allowed_workspace_ids
            ):
                raise WorkflowError("tool_permission")
            return await execute_coding(config, payload, step, provider, deployment)

        async with asyncio.timeout(
            max(0.001, (assignment.deadline_at - datetime.now(UTC)).total_seconds())
        ):
            result = await execute_workflow(
                bundle,
                payload,
                deployment,
                provider,
                registration.worker_tools,
                list(registration.tool_permissions),
                registration.os,
                read_artifact,
                transition,
                coding=coding,
            )
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
            await watch
        elif not work.cancelled():
            await work
    except (GatewayError, WorkflowError) as error:
        await report("fail", error_code=error.code)
    except TimeoutError:
        await report("fail", error_code="step_timeout")
    except HTTPError as error:
        if error.code == 408:
            await report("fail", error_code="step_timeout")
            return
        if error.code != 409:
            raise
        if (await report("renew")).cancel_requested:
            await report("cancelled")
        else:
            raise
    finally:
        for task in (work, watch):
            task.cancel()
        for task in (work, watch):
            with suppress(asyncio.CancelledError, Exception):
                await task
        await provider.close()
