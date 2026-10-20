"""Nonbillable worker-side model-list checks requested by the connection owner."""

import asyncio
from uuid import UUID

from godfather_contracts import Registration
from godfather_contracts.providers import ConnectionCheck, ConnectionCheckResult
from godfather_model_gateway import GatewayError, ProviderConfig
from godfather_model_gateway.providers import create_provider

from godfather_worker.client import WorkerClient
from godfather_worker.provider_credentials import load


async def check_connections(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    checks: list[ConnectionCheck],
    configs: list[ProviderConfig],
) -> None:
    async def check(item: ConnectionCheck) -> None:
        config = next((c for c in configs if c.connection_id == item.connection_id), None)
        result = ConnectionCheckResult(
            **item.model_dump(), session_id=registration.session_id, code="provider_auth"
        )
        if config is not None:
            try:
                load(config)
                provider = create_provider(config)
                try:
                    async with asyncio.timeout(5):
                        models = await provider.discover()
                    result = result.model_copy(
                        update={"code": "ready", "models": [m.identifier for m in models]}
                    )
                finally:
                    await provider.close()
            except GatewayError as error:
                result = result.model_copy(update={"code": error.code})
            except TimeoutError:
                result = result.model_copy(update={"code": "provider_timeout"})
            except OSError:
                pass
        await asyncio.to_thread(
            client.post_document, f"/api/v1/workers/{node_id}/provider-checks", result
        )

    await asyncio.gather(*(check(item) for item in checks))
