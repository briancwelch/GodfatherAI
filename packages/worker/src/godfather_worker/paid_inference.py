"""Require a fresh durable reservation before each billable provider call."""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import suppress
from uuid import UUID

from godfather_contracts import ModelDeployment, Registration
from godfather_contracts.inference import InferenceInput
from godfather_contracts.jobs import Assignment
from godfather_contracts.providers import InvocationRequest, InvocationSettlement
from godfather_model_gateway import Chunk, GatewayError, Provider

from godfather_worker.client import WorkerClient
from godfather_worker.provider_credentials import load


class MeteredProvider:
    def __init__(
        self,
        provider: Provider,
        client: WorkerClient,
        node_id: UUID,
        registration: Registration,
        assignment: Assignment,
    ) -> None:
        self.provider, self.client = provider, client
        self.registration, self.assignment = registration, assignment
        self.root = f"/api/v1/workers/{node_id}/jobs/{assignment.job.id}/provider"
        self.counter = 0

    async def discover(self) -> list[ModelDeployment]:
        return await self.provider.discover()

    async def close(self) -> None:
        await self.provider.close()

    async def infer(self, model: str, request: InferenceInput) -> AsyncGenerator[Chunk]:
        config = getattr(self.provider, "config", None)
        if config is not None:
            try:
                load(config)
            except OSError:
                raise GatewayError("provider_auth") from None
        deployment = self.assignment.deployment
        selection = self.assignment.job.requirements.model_selection
        if (
            deployment is None
            or selection is None
            or not selection.paid_consent
            or selection.connection_id is None
            or deployment.connection_id != selection.connection_id
            or deployment.identifier != model
        ):
            raise GatewayError("invalid_request")
        payload = InvocationRequest(
            session_id=self.registration.session_id,
            attempt_id=self.assignment.attempt_id,
            fencing_token=self.assignment.fencing_token,
            call_key=f"call-{self.counter}",
            input_bytes=len(
                (
                    request.prompt
                    + (request.system or "")
                    + json.dumps([request.output_schema, [t.model_dump() for t in request.tools]])
                ).encode("utf-8")
            ),
            max_output_tokens=request.parameters.max_tokens,
        )
        self.counter += 1
        result = await asyncio.to_thread(
            self.client.post_document, self.root + "/authorize", payload
        )
        if not isinstance(result, dict) or "invocation_id" not in result:
            raise GatewayError("invalid_response")
        input_tokens = output_tokens = None
        completed = False
        pricing_supported = True
        try:
            async for chunk in self.provider.infer(model, request):
                if chunk.input_tokens is not None:
                    input_tokens = chunk.input_tokens
                if chunk.output_tokens is not None:
                    output_tokens = chunk.output_tokens
                completed = completed or chunk.done
                pricing_supported = pricing_supported and not chunk.cost_reconciliation_required
                yield chunk
        finally:
            # Missing final usage retains the reservation for review, including on disconnect.
            settlement = InvocationSettlement(
                **payload.model_dump(),
                invocation_id=UUID(str(result["invocation_id"])),
                input_tokens=input_tokens if completed else None,
                output_tokens=output_tokens if completed else None,
                pricing_supported=pricing_supported,
            )
            with suppress(Exception):
                await asyncio.shield(
                    asyncio.to_thread(self.client.post_document, self.root + "/settle", settlement)
                )
