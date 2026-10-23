"""Authorize a single paid image call durably before any provider data egress."""

import asyncio
from contextlib import suppress
from uuid import UUID

from godfather_contracts import Registration
from godfather_contracts.agents import WorkflowInput
from godfather_contracts.jobs import Assignment
from godfather_contracts.providers import InvocationRequest, InvocationSettlement
from godfather_contracts.workloads import CLOUD_IMAGE_RUNTIME, WorkloadOutput
from godfather_model_gateway import GatewayError, ProviderConfig
from godfather_model_gateway.images import CloudImages

from godfather_worker.client import WorkerClient
from godfather_worker.workloads import image_output


async def execute(
    config: ProviderConfig,
    payload: WorkflowInput,
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
) -> WorkloadOutput:
    selection, deployment = assignment.job.requirements.model_selection, assignment.deployment
    image = payload.image
    if (
        image is None
        or selection is None
        or deployment is None
        or not selection.paid_consent
        or not selection.connection_id
        or selection.required_operations != ["image_generation"]
        or deployment.connection_id != selection.connection_id
        or config.connection_id != selection.connection_id
        or deployment.identifier != image.model
        or selection.identifier != image.model
        or deployment.provider != image.backend
        or selection.provider != image.backend
        or CLOUD_IMAGE_RUNTIME not in registration.runtimes
        or "images.generate" not in registration.tool_permissions
    ):
        raise GatewayError("invalid_request")
    provider = CloudImages(config)
    provider.validate(image)
    request = InvocationRequest(
        session_id=registration.session_id,
        attempt_id=assignment.attempt_id,
        fencing_token=assignment.fencing_token,
        call_key="image",
        input_bytes=len(payload.instruction.encode()),
        max_output_tokens=1,
    )
    root = f"/api/v1/workers/{node_id}/jobs/{assignment.job.id}/provider"
    authorization = await asyncio.to_thread(client.post_document, root + "/authorize", request)
    if not isinstance(authorization, dict) or "invocation_id" not in authorization:
        raise GatewayError("invalid_response")
    # An interrupted or rejected response leaves the durable marker for review.
    result = await provider.generate(payload.instruction, image)
    output = image_output(result.images, payload)
    with suppress(Exception):
        await asyncio.to_thread(
            client.post_document,
            root + "/settle",
            InvocationSettlement(
                **request.model_dump(),
                invocation_id=UUID(str(authorization["invocation_id"])),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                pricing_supported=False,
            ),
        )
    return output
