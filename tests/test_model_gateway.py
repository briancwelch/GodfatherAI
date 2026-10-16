"""Deterministic provider contracts; no model installation, downloads, or credentials."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx2 as httpx
import pytest
from godfather_contracts import ModelDeployment, ModelSelection
from godfather_contracts.inference import InferenceInput
from godfather_model_gateway import GatewayError, ProviderConfig, generate
from godfather_model_gateway.providers import OllamaProvider, OpenAICompatibleProvider
from pydantic import ValidationError


def deployment() -> ModelDeployment:
    return ModelDeployment(
        provider_id="local",
        provider="ollama",
        identifier="fixture-model",
        operations=["chat", "stream"],
    )


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("kind", ["ollama", "openai_compatible"])
def test_discovery_and_inference_contract(kind: str, stream: bool) -> None:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "fixture-model", "digest": "abc", "size": 4096}]}
            )
        if path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "capabilities": ["completion"],
                    "model_info": {"fixture.context_length": 4096},
                },
            )
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "fixture-model"}]})
        body = json.loads(request.content)
        assert body["model"] == "fixture-model" and body["stream"] is stream
        assert body["messages"][-1]["content"] == "private prompt"
        assert (body["options"]["num_predict"] if kind == "ollama" else body["max_tokens"]) == 512
        if kind == "ollama":
            final = {
                "message": {"content": "hello" if not stream else ""},
                "done": True,
                "eval_count": 2,
                "prompt_eval_count": 3,
                "eval_duration": 1000000000,
            }
            if not stream:
                return httpx.Response(200, json=final)
            return httpx.Response(
                200,
                content=json.dumps({"message": {"content": "hello"}, "done": False})
                + "\n"
                + json.dumps(final)
                + "\n",
            )
        if not stream:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                },
            )
        chunks = [
            {"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
        ]
        return httpx.Response(
            200,
            content="".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n",
        )

    async def run() -> None:
        config = ProviderConfig.model_validate(
            {
                "id": "local",
                "provider": kind,
                "url": "http://127.0.0.1" + ("/v1" if kind == "openai_compatible" else ""),
                "chat_enabled": True,
                "stream_enabled": True,
                "declared_capabilities": ["text"],
            }
        )
        adapter = (OllamaProvider if kind == "ollama" else OpenAICompatibleProvider)(
            config, httpx.MockTransport(handle)
        )
        try:
            models = await adapter.discover()
            assert len(models) == 1 and models[0].identifier == "fixture-model"
            assert models[0].declared_capabilities == ["text"]
            assert models[0].verified_capabilities == (["completion"] if kind == "ollama" else [])
            assert models[0].context_window == (4096 if kind == "ollama" else None)
            output: list[str] = []

            async def on_text(text: str) -> None:
                output.append(text)

            result = await generate(
                adapter,
                models[0],
                InferenceInput(prompt="private prompt", stream=stream),
                5,
                on_text,
            )
            assert result.text == "hello" and "".join(output) == "hello"
            assert result.usage.input_tokens == 3 and result.usage.output_tokens == 2
            assert result.usage.token_source == "provider_reported"
            assert (
                result.usage.first_token_seconds is not None
                if stream
                else result.usage.first_token_seconds is None
            )
            assert result.usage.rate_source == (
                "provider_reported" if kind == "ollama" else "worker_estimate"
            )
        finally:
            await adapter.close()

    asyncio.run(run())
    assert calls


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "provider_auth"),
        (403, "provider_auth"),
        (404, "model_unavailable"),
        (429, "rate_limited"),
        (500, "provider_unavailable"),
        (504, "provider_timeout"),
        (400, "invalid_request"),
        (302, "invalid_request"),
    ],
)
def test_error_classification_and_no_redirect(status: int, code: str) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status, text="PRIVATE BODY", headers={"Location": "https://other.invalid"}
        )

    async def run() -> None:
        adapter = OllamaProvider(
            ProviderConfig(id="local", provider="ollama"), httpx.MockTransport(handle)
        )
        try:
            with pytest.raises(GatewayError) as error:
                await adapter.discover()
            assert error.value.code == code and "PRIVATE" not in str(error.value)
        finally:
            await adapter.close()

    asyncio.run(run())
    assert calls == 1


@pytest.mark.parametrize("failure", ["connection", "timeout", "malformed", "truncated", "limit"])
def test_transport_and_protocol_failures(failure: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if failure == "connection":
            raise httpx.ConnectError("secret endpoint", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret prompt", request=request)
        if failure == "malformed":
            return httpx.Response(200, text="PRIVATE invalid json\n")
        if failure == "limit":
            return httpx.Response(200, content=b"x" * (262145) + b"\n")
        return httpx.Response(
            200, content=json.dumps({"message": {"content": "partial"}, "done": False}) + "\n"
        )

    async def run() -> None:
        adapter = OllamaProvider(
            ProviderConfig(id="local", provider="ollama"), httpx.MockTransport(handle)
        )

        async def ignore(text: str) -> None:
            pass

        try:
            with pytest.raises(GatewayError) as error:
                await generate(adapter, deployment(), InferenceInput(prompt="private"), 2, ignore)
            expected = {
                "connection": "provider_unavailable",
                "timeout": "provider_timeout",
                "malformed": "invalid_response",
                "truncated": "invalid_response",
                "limit": "output_limit",
            }
            assert error.value.code == expected[failure]
            assert "secret" not in str(error.value)
        finally:
            await adapter.close()

    asyncio.run(run())


class BlockingStream(httpx.AsyncByteStream):
    def __init__(self, received: asyncio.Event) -> None:
        self.received = received
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'{"message":{"content":"first"},"done":false}\n'
        self.received.set()
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("cancel", [False, True])
def test_total_timeout_and_cancellation_close_stream(cancel: bool) -> None:
    async def run() -> None:
        received = asyncio.Event()
        body = BlockingStream(received)
        adapter = OllamaProvider(
            ProviderConfig(id="local", provider="ollama"),
            httpx.MockTransport(lambda r: httpx.Response(200, stream=body)),
        )

        async def ignore(text: str) -> None:
            pass

        task = asyncio.create_task(
            generate(
                adapter, deployment(), InferenceInput(prompt="test"), 60 if cancel else 0.02, ignore
            )
        )
        try:
            if cancel:
                await asyncio.wait_for(received.wait(), 1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(GatewayError, match="provider_timeout"):
                    await task
            assert body.closed
        finally:
            await adapter.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "settings",
    [
        {"url": "http://192.168.1.2:11434"},
        {"url": "https://public.invalid"},
        {"url": "http://user:pass@localhost"},
        {"url": "http://localhost?key=secret"},
    ],
)
def test_ollama_endpoint_boundaries(settings: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ProviderConfig.model_validate({"id": "local", "provider": "ollama", **settings})


def test_remote_provider_security_and_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(id="remote", provider="openai_compatible", url="http://remote.invalid/v1")
    monkeypatch.delenv("GODFATHER_TEST_KEY", raising=False)
    config = ProviderConfig(
        id="remote",
        provider="openai_compatible",
        url="https://remote.invalid/v1",
        api_key_env="GODFATHER_TEST_KEY",
    )
    with pytest.raises(GatewayError, match="provider_auth"):
        config.headers()
    monkeypatch.setenv("GODFATHER_TEST_KEY", "private-key")
    assert config.headers() == {"Authorization": "Bearer private-key"}
    assert "private-key" not in repr(config)
    with pytest.raises(ValidationError):
        ModelSelection()


@pytest.mark.parametrize("kind", ["ollama", "openai_compatible"])
def test_provider_cannot_silently_substitute_model(kind: str) -> None:
    async def run() -> None:
        config = ProviderConfig.model_validate({"id": "local", "provider": kind})
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"model": "different"}))
        provider = (OllamaProvider if kind == "ollama" else OpenAICompatibleProvider)(
            config, transport
        )

        async def ignore(text: str) -> None:
            pass

        try:
            with pytest.raises(GatewayError, match="invalid_response"):
                await generate(
                    provider,
                    deployment(),
                    InferenceInput(prompt="private", stream=False),
                    5,
                    ignore,
                )
        finally:
            await provider.close()

    asyncio.run(run())
