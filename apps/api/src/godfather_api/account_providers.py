"""Account key vault and explicit owner-only worker delivery, separate from scheduling."""

import asyncio
import base64
import os
import re
from typing import Literal
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Request
from godfather_contracts import Contract
from godfather_contracts.execution import JobPoll
from godfather_contracts.providers import ConnectionPolicy
from godfather_contracts.workloads import CLOUD_IMAGE_MODELS, CLOUD_IMAGE_RUNTIME
from godfather_model_gateway import GatewayError, NativeModel, ProviderConfig
from godfather_model_gateway.images import gemini_models
from godfather_model_gateway.providers import HTTPProvider
from pydantic import Field, SecretStr
from sqlalchemy import select

from godfather_api.authentication import audit, throttle
from godfather_api.config import Settings
from godfather_api.jobs import worker_node
from godfather_api.models import AccountProviderKey, Node, ProviderConnection, User
from godfather_api.nodes import SessionDep, authenticate

router = APIRouter(prefix="/api/v1")


def crypt(key: SecretStr) -> AESGCM:
    raw = key.get_secret_value()
    if not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise HTTPException(503, "Account API key storage is not configured by the administrator")
    return AESGCM(bytes.fromhex(raw))


def encrypt_key(key: str, owner: UUID, provider: str, settings: Settings) -> str:
    nonce = os.urandom(12)
    data = crypt(settings.provider_vault_key).encrypt(
        nonce, key.encode(), f"godfather:{owner}:{provider}".encode()
    )
    return base64.urlsafe_b64encode(nonce + data).decode()


def decrypt_key(row: AccountProviderKey, settings: Settings) -> str:
    try:
        data = base64.urlsafe_b64decode(row.encrypted_key)
        return (
            crypt(settings.provider_vault_key)
            .decrypt(data[:12], data[12:], f"godfather:{row.owner_id}:{row.provider}".encode())
            .decode()
        )
    except (ValueError, InvalidTag):
        raise HTTPException(
            503, "Account API key could not be unlocked; contact your administrator"
        ) from None


class SaveKey(Contract):
    api_key: SecretStr = Field(min_length=8, max_length=4096, repr=False)
    allowed_node_ids: list[UUID] = Field(min_length=1, max_length=128)


class ComputerGrant(Contract):
    allowed_node_ids: list[UUID] = Field(min_length=1, max_length=128)


@router.post("/account/providers/{provider}/computers")
def computers(
    provider: Literal["openai", "anthropic", "gemini"],
    payload: ComputerGrant,
    request: Request,
    session: SessionDep,
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    session.get(User, actor.owner_id, with_for_update=True)
    row = session.scalar(
        select(AccountProviderKey)
        .where(
            AccountProviderKey.owner_id == actor.owner_id, AccountProviderKey.provider == provider
        )
        .with_for_update()
    )
    if row is None or not row.enabled:
        raise HTTPException(404, "Connect this provider first")
    for node_id in payload.allowed_node_ids:
        node = session.get(Node, node_id)
        if node is None or node.owner_id != actor.owner_id:
            raise HTTPException(404, "Choose only your own worker computers")
    row.allowed_node_ids = list(dict.fromkeys(map(str, payload.allowed_node_ids)))
    for connection in session.scalars(
        select(ProviderConnection).where(ProviderConnection.account_key_id == row.id)
    ):
        connection.policy = {
            **connection.policy,
            "enabled": str(connection.node_id) in row.allowed_node_ids,
        }
    audit(session, "account_provider_computers_changed", actor.owner_id)
    return {"saved": True}


async def discover_catalog(
    provider: Literal["openai", "anthropic", "gemini"], key: str
) -> list[NativeModel]:
    config = ProviderConfig(
        id="account-check", provider=provider, connection_id=uuid4(), timeout_seconds=10
    )
    config.set_api_key(key)
    client = HTTPProvider(config)
    try:
        async with asyncio.timeout(10):
            identifiers = (
                await gemini_models(client)
                if provider == "gemini"
                else {str(m["id"]) for m in (await client.request("GET", "models"))["data"]}
            )
        # Restrict to native text APIs. These are conservative application limits,
        # not claims about the provider's full context/output capacity.
        text_models = [
            NativeModel(
                identifier=identifier,
                context_window=65536,
                max_output_tokens=4096,
                tools=True,
                structured_output=True,
            )
            for identifier in sorted(identifiers)
            if (provider == "anthropic" and identifier.startswith("claude-"))
            or (
                provider == "openai"
                and re.fullmatch(
                    r"(?:gpt-(?:4\.1|4o|5|6)(?:\.[0-9]+)?(?:-(?:mini|nano))?(?:-\d{4}-\d{2}-\d{2})?|o[34](?:-mini)?(?:-\d{4}-\d{2}-\d{2})?)",
                    identifier,
                )
            )
        ][:64]
        return text_models + [
            NativeModel(
                identifier=identifier, modality="image", context_window=1, max_output_tokens=1
            )
            for identifier in CLOUD_IMAGE_MODELS.get(provider, ())
            if identifier in identifiers
        ]
    except (GatewayError, KeyError, TypeError, ValueError, AttributeError, TimeoutError):
        raise HTTPException(
            400,
            "Could not connect. Check that this provider API key can list models, and try again.",
        ) from None
    finally:
        await client.close()


@router.get("/account/providers")
def account_keys(request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    rows = session.scalars(
        select(AccountProviderKey)
        .where(AccountProviderKey.owner_id == actor.owner_id)
        .order_by(AccountProviderKey.provider)
    )
    return {
        "storage_available": bool(
            re.fullmatch(
                r"[0-9a-f]{64}", request.app.state.settings.provider_vault_key.get_secret_value()
            )
        ),
        "connections": [
            {
                "provider": row.provider,
                "connected": row.enabled,
                "models": row.model_catalog if row.enabled else [],
                "allowed_node_ids": row.allowed_node_ids,
            }
            for row in rows
        ],
    }


@router.post("/account/providers/{provider}")
async def save_key(
    provider: Literal["openai", "anthropic", "gemini"],
    payload: SaveKey,
    request: Request,
    session: SessionDep,
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    throttle(request, "account-provider-save")
    for node_id in payload.allowed_node_ids:
        node = session.get(Node, node_id)
        if node is None or node.owner_id != actor.owner_id:
            raise HTTPException(404, "Choose only your own worker computers")
    key = payload.api_key.get_secret_value().strip()
    if not key or any(c.isspace() for c in key):
        raise HTTPException(422, "Paste one API key without spaces or line breaks")
    encrypted = encrypt_key(key, actor.owner_id, provider, request.app.state.settings)
    catalog = await discover_catalog(provider, key)
    if not catalog:
        raise HTTPException(
            400, "Connected, but no supported text or image models were found for this key"
        )
    session.get(User, actor.owner_id, with_for_update=True)
    row = session.scalar(
        select(AccountProviderKey)
        .where(
            AccountProviderKey.owner_id == actor.owner_id, AccountProviderKey.provider == provider
        )
        .with_for_update()
    )
    if row is None:
        row = AccountProviderKey(owner_id=actor.owner_id, provider=provider)
        session.add(row)
    row.encrypted_key, row.model_catalog, row.enabled = (
        encrypted,
        [
            m.model_dump(mode="json", exclude={"modality"} if m.modality == "text" else set())
            for m in catalog
        ],
        True,
    )
    row.allowed_node_ids = list(dict.fromkeys(map(str, payload.allowed_node_ids)))
    for connection in session.scalars(
        select(ProviderConnection).where(ProviderConnection.account_key_id == row.id)
    ):
        connection.policy = {
            **connection.policy,
            "enabled": str(connection.node_id) in row.allowed_node_ids,
        }
    audit(session, "account_provider_saved", actor.owner_id)
    return {"connected": True}


@router.post("/account/providers/{provider}/disconnect")
def disconnect(
    provider: Literal["openai", "anthropic", "gemini"], request: Request, session: SessionDep
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    session.get(User, actor.owner_id, with_for_update=True)
    row = session.scalar(
        select(AccountProviderKey)
        .where(
            AccountProviderKey.owner_id == actor.owner_id, AccountProviderKey.provider == provider
        )
        .with_for_update()
    )
    if row is not None:
        row.enabled, row.encrypted_key, row.model_catalog = False, "", []
        for connection in session.scalars(
            select(ProviderConnection).where(ProviderConnection.account_key_id == row.id)
        ):
            connection.policy = {**connection.policy, "enabled": False}
        audit(session, "account_provider_disconnected", actor.owner_id)
    return {"disconnected": True}


@router.post("/workers/{node_id}/account-providers")
def worker_keys(
    node_id: UUID, payload: JobPoll, request: Request, session: SessionDep
) -> dict[str, object]:
    node = worker_node(node_id, payload, request, session)
    from godfather_api.nodes import node_view

    if "account-provider-keys-v1" not in node_view(session, node).runtimes:
        raise HTTPException(403, "Enable account API connections on this worker first")
    session.get(User, node.owner_id, with_for_update=True)
    rows = session.scalars(
        select(AccountProviderKey)
        .where(AccountProviderKey.owner_id == node.owner_id, AccountProviderKey.enabled.is_(True))
        .order_by(AccountProviderKey.id)
        .with_for_update()
    )
    result = []
    cloud_images = CLOUD_IMAGE_RUNTIME in node_view(session, node).runtimes
    for row in rows:
        if str(node.id) not in row.allowed_node_ids:
            continue
        catalog = [m for m in row.model_catalog if cloud_images or m.get("modality") != "image"]
        if not catalog or (row.provider == "gemini" and not cloud_images):
            continue
        connection = session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.account_key_id == row.id, ProviderConnection.node_id == node.id
            )
        )
        if connection is None:
            connection = ProviderConnection(
                owner_id=node.owner_id,
                node_id=node.id,
                provider=row.provider,
                name=f"My {row.provider} account",
                account_key_id=row.id,
                policy=ConnectionPolicy(enabled=True, billing="provider").model_dump(mode="json"),
            )
            session.add(connection)
            session.flush()
        if connection.revoked or not connection.policy.get("enabled"):
            continue
        result.append(
            {
                "id": "account-" + str(row.id),
                "provider": row.provider,
                "connection_id": str(connection.id),
                "model_catalog": catalog,
                "api_key": decrypt_key(row, request.app.state.settings),
            }
        )
    if result:
        audit(session, "account_provider_access", node.owner_id, node.id)
    return {"providers": result}
