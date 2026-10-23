"""Explicitly opted-in, individually authorized account keys stay in worker memory."""

from uuid import UUID

from godfather_contracts import Contract
from godfather_contracts.execution import JobPoll
from godfather_model_gateway import ProviderConfig
from pydantic import Field, SecretStr

from godfather_worker.client import WorkerClient


class AccountProvider(Contract):
    id: str
    provider: str
    connection_id: UUID
    model_catalog: list[dict[str, object]]
    api_key: SecretStr = Field(repr=False, exclude=True)


class AccountProviders(Contract):
    providers: list[AccountProvider] = Field(max_length=3)


def fetch(client: WorkerClient, node_id: UUID, session_id: UUID) -> list[ProviderConfig]:
    response = AccountProviders.model_validate(
        client.post_document(
            f"/api/v1/workers/{node_id}/account-providers", JobPoll(session_id=session_id)
        )
    )
    configs = []
    for provider in response.providers:
        config = ProviderConfig.model_validate(provider.model_dump(exclude={"api_key"}))
        config.set_api_key(provider.api_key.get_secret_value(), account=True)
        configs.append(config)
    return configs
