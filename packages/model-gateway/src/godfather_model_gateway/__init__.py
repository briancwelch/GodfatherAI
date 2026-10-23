"""Provider contracts and bounded inference; cancellation closes the HTTP stream."""

import asyncio
import json
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from time import perf_counter
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from godfather_contracts import Contract, Label, ModelDeployment
from godfather_contracts.inference import (
    MAX_TEXT,
    InferenceInput,
    InferenceResult,
    InferenceUsage,
    ProviderErrorCode,
    ToolCall,
)
from pydantic import Field, PrivateAttr, SecretStr, model_validator


class NativeModel(Contract):
    identifier: Label
    context_window: int = Field(ge=1, le=2**40)
    max_output_tokens: int = Field(ge=1, le=2**30)
    tools: bool = False
    structured_output: bool = False


class ProviderConfig(Contract):
    id: Label
    provider: Literal["ollama", "openai_compatible", "openai", "anthropic"]
    connection_id: UUID | None = None
    shared_inference_group_id: UUID | None = None
    model_catalog: list[NativeModel] = Field(default_factory=list, max_length=128)
    _api_key: SecretStr | None = PrivateAttr(default=None)
    _account_key: bool = PrivateAttr(default=False)
    url: str = Field(default="http://127.0.0.1:11434", max_length=2048, repr=False)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    timeout_seconds: float = Field(default=120, ge=0.1, le=3600, allow_inf_nan=False)
    # OpenAI-compatible discovery doesn't certify chat/stream support.
    chat_enabled: bool = False
    stream_enabled: bool = False
    declared_capabilities: list[Label] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def secure_endpoint(self) -> "ProviderConfig":
        if self.provider in ("openai", "anthropic"):
            if self.connection_id is None or self.api_key_env:
                raise ValueError(
                    "Native providers require a separate node-local credential connection"
                )
            endpoint = (
                "https://api.openai.com/v1"
                if self.provider == "openai"
                else "https://api.anthropic.com/v1"
            )
            if self.url not in ("http://127.0.0.1:11434", endpoint):
                raise ValueError("Native providers require the official HTTPS API endpoint")
            self.url = endpoint
        if self.shared_inference_group_id and (
            self.provider != "openai_compatible" or self.connection_id
        ):
            raise ValueError(
                "Shared inference requires an owner-configured local OpenAI-compatible engine"
            )
        parsed = urlsplit(self.url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)
        ):
            raise ValueError("Invalid provider endpoint")
        loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
        if self.provider == "openai_compatible" and parsed.hostname in (
            "api.openai.com",
            "api.anthropic.com",
        ):
            raise ValueError("Use the native provider with its independent credential connection")
        if self.shared_inference_group_id and not loopback:
            raise ValueError("Shared engine endpoints must remain on the leader worker loopback")
        if self.provider == "ollama" and not loopback:
            raise ValueError("Ollama endpoints must remain worker-local loopback")
        if parsed.scheme == "http" and not loopback:
            raise ValueError("Remote providers require certificate-validated HTTPS")
        if self.provider == "ollama" and parsed.path not in ("", "/"):
            raise ValueError("Ollama endpoint must be an origin")
        return self

    def headers(self) -> dict[str, str]:
        if self.provider in ("openai", "anthropic"):
            if self._api_key is None:
                raise GatewayError("provider_auth")
            value = self._api_key.get_secret_value()
            if not value.strip() or "\r" in value or "\n" in value:
                raise GatewayError("provider_auth")
            if self.provider == "anthropic":
                return {"x-api-key": value, "anthropic-version": "2023-06-01"}
            return {"Authorization": "Bearer " + value}
        if self.api_key_env is None:
            return {}
        key = os.getenv(self.api_key_env)
        if not key or not key.strip() or "\n" in key or "\r" in key:
            raise GatewayError("provider_auth")
        return {"Authorization": "Bearer " + key}

    def set_api_key(self, key: str, *, account: bool = False) -> None:
        self._api_key = SecretStr(key)
        self._account_key = account

    @property
    def has_account_api_key(self) -> bool:
        return self._api_key is not None and self._account_key


class GatewayError(Exception):
    def __init__(self, code: ProviderErrorCode) -> None:
        self.code = code
        super().__init__(code)  # Never include provider bodies, URLs, prompts or keys.


class StructuredRequest(InferenceInput):
    """Internal JSON-mode hint; workflow validation still checks the exact schema.

    This never changes the Phase 05 job/worker wire payload.
    """

    json_output: Literal[True] = True


class Chunk(Contract):
    text: str = Field(default="", max_length=MAX_TEXT)
    done: bool = False
    input_tokens: int | None = Field(default=None, ge=0, le=2**40)
    output_tokens: int | None = Field(default=None, ge=0, le=2**40)
    generation_seconds: float | None = Field(default=None, gt=0, le=86400, allow_inf_nan=False)
    finish_reason: Literal["stop", "length", "other"] = "stop"
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=16)
    cost_reconciliation_required: bool = False


class Provider(Protocol):
    async def discover(self) -> list[ModelDeployment]: ...

    def infer(self, model: str, request: InferenceInput) -> AsyncGenerator[Chunk]: ...

    async def close(self) -> None: ...


async def generate(
    provider: Provider,
    deployment: ModelDeployment,
    request: InferenceInput,
    timeout_seconds: float,
    on_text: Callable[[str], Awaitable[None]],
) -> InferenceResult:
    """All adapters share total deadlines, output limits, and task cancellation."""
    start = perf_counter()
    first: float | None = None
    text = ""
    usage_in = usage_out = None
    generation = None
    final: Chunk | None = None
    try:
        async with (
            asyncio.timeout(timeout_seconds),
            aclosing(provider.infer(deployment.identifier, request)) as stream,
        ):
            async for chunk in stream:
                if final is not None and chunk.text:
                    raise GatewayError("invalid_response")
                if chunk.text:
                    if first is None:
                        first = perf_counter() - start
                    if len(text) + len(chunk.text) > MAX_TEXT:
                        raise GatewayError("output_limit")
                    text += chunk.text
                    await on_text(chunk.text)
                if chunk.input_tokens is not None:
                    usage_in = chunk.input_tokens
                if chunk.output_tokens is not None:
                    usage_out = chunk.output_tokens
                if chunk.generation_seconds is not None:
                    generation = chunk.generation_seconds
                if chunk.done:
                    final = chunk
            if final is None:
                raise GatewayError("invalid_response")
    except TimeoutError:
        raise GatewayError("provider_timeout") from None
    elapsed = perf_counter() - start
    if len(text) + sum(len(c.arguments) for c in final.tool_calls) > MAX_TEXT:
        raise GatewayError("output_limit")
    for call in final.tool_calls:
        if call.name not in {tool.name for tool in request.tools}:
            raise GatewayError("invalid_response")
        try:
            if not isinstance(json.loads(call.arguments), dict):
                raise ValueError
        except ValueError:
            raise GatewayError("invalid_response") from None
    rate = None
    rate_source: Literal["provider_reported", "worker_estimate", "unavailable"] = "unavailable"
    if usage_out is not None:
        # Without provider generation timing this is end-to-end throughput,
        # including prompt evaluation/loading, not a fabricated decode speed.
        denominator = generation or max(0.000001, elapsed)
        rate = usage_out / denominator
        rate_source = "provider_reported" if generation else "worker_estimate"
    return InferenceResult(
        text=text,
        deployment=deployment,
        usage=InferenceUsage(
            input_tokens=usage_in,
            output_tokens=usage_out,
            token_source="provider_reported"
            if usage_in is not None or usage_out is not None
            else "unavailable",
            duration_seconds=elapsed,
            first_token_seconds=first if request.stream else None,
            tokens_per_second=rate,
            rate_source=rate_source,
        ),
        finish_reason=final.finish_reason,
        tool_calls=final.tool_calls,
    )
