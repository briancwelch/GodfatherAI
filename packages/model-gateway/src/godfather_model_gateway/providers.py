"""Replaceable Ollama NDJSON and OpenAI-compatible chat/SSE adapters."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx2 as httpx
from godfather_contracts import ModelDeployment
from godfather_contracts.inference import InferenceInput
from pydantic import ValidationError

from godfather_model_gateway import Chunk, GatewayError, Provider, ProviderConfig


def document(raw: str | bytes) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise GatewayError("invalid_response")
    return value


def check_status(status: int) -> None:
    if 200 <= status < 300:
        return
    if status in (401, 403):
        raise GatewayError("provider_auth")
    if status == 404:
        raise GatewayError("model_unavailable")
    if status == 429:
        raise GatewayError("rate_limited")
    if status in (408, 504):
        raise GatewayError("provider_timeout")
    raise GatewayError("provider_unavailable" if status >= 500 else "invalid_request")


class HTTPProvider:
    def __init__(
        self, config: ProviderConfig, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.url.rstrip("/") + "/",
            trust_env=False,
            follow_redirects=False,
            timeout=config.timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def documents(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        mode: str = "json",
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                async with self.client.stream(
                    method, path, json=payload, headers=self.config.headers()
                ) as response:
                    check_status(response.status_code)
                    buffer = b""
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 4 * 1024**2:
                            raise GatewayError("output_limit")
                        buffer += chunk
                        if mode == "json":
                            continue
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            if len(line) > 262144:
                                raise GatewayError("output_limit")
                            item = self.parse_line(line, mode)
                            if item is not None:
                                yield item
                        if len(buffer) > 262144:
                            raise GatewayError("output_limit")
                    if buffer.strip():
                        if mode == "json":
                            yield document(buffer)
                        else:
                            item = self.parse_line(buffer, mode)
                            if item is not None:
                                yield item
        except (httpx.TimeoutException, TimeoutError):
            raise GatewayError("provider_timeout") from None
        except httpx.RequestError:
            raise GatewayError("provider_unavailable") from None
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            raise GatewayError("invalid_response") from None

    @staticmethod
    def parse_line(line: bytes, mode: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        if mode == "sse":
            if not line.startswith(b"data:"):
                return None
            line = line[5:].strip()
            if line == b"[DONE]":
                return {"_done": True}
        return document(line)

    async def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> dict[str, Any]:
        async for item in self.documents(method, path, payload):
            return item
        raise GatewayError("invalid_response")


class OllamaProvider(HTTPProvider):
    async def discover(self) -> list[ModelDeployment]:
        data = await self.request("GET", "api/tags")
        result: list[ModelDeployment] = []
        try:
            models = data["models"]
            if not isinstance(models, list) or len(models) > 128:
                raise GatewayError("invalid_response")
            for model in models:
                identifier = model["name"]
                info = await self.request("POST", "api/show", {"model": identifier})
                capabilities = info.get("capabilities", [])
                metadata = info.get("model_info", {})
                contexts = [v for k, v in metadata.items() if k.endswith(".context_length")]
                chat = "completion" in capabilities
                result.append(
                    ModelDeployment(
                        provider_id=self.config.id,
                        provider="ollama",
                        identifier=identifier,
                        verified_capabilities=capabilities,
                        declared_capabilities=self.config.declared_capabilities,
                        operations=["chat", "stream"] if chat else [],
                        context_window=max(contexts) if contexts else None,
                        digest=model.get("digest"),
                        disk_bytes=model.get("size"),
                        # Disk bytes do not certify RAM/VRAM needs; leave those unknown.
                    )
                )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise GatewayError("invalid_response") from None
        return result

    async def infer(self, model: str, request: InferenceInput) -> AsyncGenerator[Chunk]:
        messages = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        parameters = request.parameters
        options: dict[str, object] = {
            "temperature": parameters.temperature,
            "top_p": parameters.top_p,
            "num_predict": parameters.max_tokens,
        }
        if parameters.seed is not None:
            options["seed"] = parameters.seed
        payload = {
            "model": model,
            "messages": messages,
            "stream": request.stream,
            "options": options,
        }
        try:
            async for data in self.documents(
                "POST", "api/chat", payload, "ndjson" if request.stream else "json"
            ):
                if "error" in data:
                    raise GatewayError("provider_unavailable")
                if data.get("model") not in (None, model):
                    raise GatewayError("invalid_response")
                duration = data.get("eval_duration")
                yield Chunk(
                    text=data.get("message", {}).get("content", ""),
                    done=data.get("done", False),
                    input_tokens=data.get("prompt_eval_count"),
                    output_tokens=data.get("eval_count"),
                    generation_seconds=duration / 1e9 if duration and duration > 0 else None,
                    finish_reason="length" if data.get("done_reason") == "length" else "stop",
                )
        except (ValidationError, TypeError, AttributeError):
            raise GatewayError("invalid_response") from None


class OpenAICompatibleProvider(HTTPProvider):
    async def discover(self) -> list[ModelDeployment]:
        data = await self.request("GET", "models")
        try:
            models = data["data"]
            if not isinstance(models, list) or len(models) > 128:
                raise GatewayError("invalid_response")
            operations: list[Any] = []
            if self.config.chat_enabled:
                operations.append("chat")
                if self.config.stream_enabled:
                    operations.append("stream")
            return [
                ModelDeployment(
                    provider_id=self.config.id,
                    provider="openai_compatible",
                    identifier=m["id"],
                    declared_capabilities=self.config.declared_capabilities,
                    operations=operations,
                    metadata_source="configured",
                )
                for m in models
            ]
        except (ValueError, KeyError, TypeError):
            raise GatewayError("invalid_response") from None

    async def infer(self, model: str, request: InferenceInput) -> AsyncGenerator[Chunk]:
        messages = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, object] = {
            "model": model,
            "messages": messages,
            "stream": request.stream,
            **request.parameters.model_dump(exclude_none=True),
        }
        if request.stream:
            payload["stream_options"] = {"include_usage": True}
        finished = False
        saw_done = False
        finish_reason = "other"
        try:
            async for data in self.documents(
                "POST", "chat/completions", payload, "sse" if request.stream else "json"
            ):
                if "error" in data:
                    raise GatewayError("provider_unavailable")
                if data.get("model") not in (None, model):
                    raise GatewayError("invalid_response")
                if data.get("_done"):
                    if not finished:
                        raise GatewayError("invalid_response")
                    saw_done = True
                    continue
                if saw_done:
                    raise GatewayError("invalid_response")
                usage = data.get("usage") or {}
                choices = data.get("choices", [])
                choice = choices[0] if choices else {}
                reason = choice.get("finish_reason")
                if reason is not None:
                    finish_reason = reason if reason in ("stop", "length") else "other"
                finished = finished or reason is not None
                message = choice.get("delta" if request.stream else "message", {})
                content = message.get("content") or ""
                if message.get("tool_calls") or message.get("function_call"):
                    raise GatewayError("invalid_response")  # No tool execution in Phase 05.
                yield Chunk(
                    text=content,
                    done=finished,
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    finish_reason=finish_reason,
                )
            if request.stream and not saw_done:
                raise GatewayError("invalid_response")
        except (ValidationError, TypeError, AttributeError, IndexError):
            raise GatewayError("invalid_response") from None


def create_provider(config: ProviderConfig) -> Provider:
    if config.provider == "ollama":
        return OllamaProvider(config)
    return OpenAICompatibleProvider(config)
