"""Native provider contracts with mocked HTTP only; no API spending."""

import asyncio
import getpass
import importlib
import json
import platform
from types import SimpleNamespace
from uuid import uuid4

import httpx2 as httpx
import pytest
from godfather_contracts.inference import FunctionTool, InferenceInput
from godfather_contracts.providers import ConnectionPolicy
from godfather_model_gateway import GatewayError, ProviderConfig
from godfather_model_gateway.frontier import AnthropicProvider, OpenAIProvider
from godfather_worker import provider_credentials
from pydantic import ValidationError


def config(provider: str) -> ProviderConfig:
    value = ProviderConfig.model_validate(
        {
            "id": "owner-api",
            "provider": provider,
            "connection_id": str(uuid4()),
            "model_catalog": [
                {
                    "identifier": "test-model",
                    "context_window": 65536,
                    "max_output_tokens": 8192,
                    "tools": True,
                    "structured_output": True,
                }
            ],
        }
    )
    value.set_api_key("fixture-api-secret")
    return value


def collect(provider: OpenAIProvider | AnthropicProvider, request: InferenceInput) -> list[object]:
    async def run() -> list[object]:
        try:
            return [c.model_dump() async for c in provider.infer("test-model", request)]
        finally:
            await provider.close()

    return asyncio.run(run())


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_native_credentials_are_independent_and_never_serialized(provider: str) -> None:
    value = config(provider)
    assert "fixture-api-secret" not in value.model_dump_json() + repr(value)
    assert "google" not in value.model_dump_json()
    assert value.url.startswith("https://api.")
    with pytest.raises(ValidationError):
        ProviderConfig.model_validate(
            {"id": "bad", "provider": provider, "api_key_env": "GOOGLE_CLIENT_SECRET"}
        )
    with pytest.raises(ValidationError):
        ProviderConfig.model_validate({**value.model_dump(), "url": "https://attacker.invalid/v1"})
    with pytest.raises(ValidationError):
        ConnectionPolicy.model_validate({"api_key": "never-accepted"})


def test_openai_responses_stream_and_tool_arguments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer fixture-api-secret"
        body = json.loads(request.content)
        assert body["store"] is False and body["tools"][0]["name"] == "lookup"
        events = [
            {"type": "response.output_text.delta", "delta": "Answer"},
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "usage": {"input_tokens": 12, "output_tokens": 4},
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "lookup",
                            "arguments": '{"id":1}',
                        }
                    ],
                },
            },
        ]
        return httpx.Response(200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events))

    chunks = collect(
        OpenAIProvider(config("openai"), httpx.MockTransport(handler)),
        InferenceInput(
            prompt="hello",
            tools=[
                FunctionTool(name="lookup", description="fixture", parameters={"type": "object"})
            ],
        ),
    )
    assert chunks[0]["text"] == "Answer"  # type: ignore[index]
    assert chunks[-1]["tool_calls"][0]["name"] == "lookup"  # type: ignore[index]
    assert chunks[-1]["input_tokens"] == 12  # type: ignore[index]


def test_anthropic_stream_preserves_usage_and_tool_json() -> None:
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 20}}},
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tool-1", "name": "lookup"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"id":1}'},
        },
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 9},
        },
        {"type": "message_stop"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert (
            request.url.path == "/v1/messages"
            and request.headers["x-api-key"] == "fixture-api-secret"
        )
        assert "authorization" not in request.headers
        return httpx.Response(200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events))

    chunks = collect(
        AnthropicProvider(config("anthropic"), httpx.MockTransport(handler)),
        InferenceInput(prompt="hello"),
    )
    assert chunks[-1]["input_tokens"] == 20  # type: ignore[index]
    assert chunks[-1]["output_tokens"] == 9  # type: ignore[index]
    assert chunks[-1]["tool_calls"][0]["arguments"] == '{"id":1}'  # type: ignore[index]


@pytest.mark.parametrize("provider", [OpenAIProvider, AnthropicProvider])
@pytest.mark.parametrize(
    "status,code", [(401, "provider_auth"), (429, "rate_limited"), (503, "provider_unavailable")]
)
def test_safe_provider_errors(
    provider: type[OpenAIProvider] | type[AnthropicProvider], status: int, code: str
) -> None:
    kind = "openai" if provider is OpenAIProvider else "anthropic"
    with pytest.raises(GatewayError, match=code) as error:
        collect(
            provider(
                config(kind),
                httpx.MockTransport(
                    lambda r: httpx.Response(status, text="private error fixture-api-secret")
                ),
            ),
            InferenceInput(prompt="hello"),
        )
    assert "secret" not in str(error.value)


def test_truncated_stream_is_not_success() -> None:
    with pytest.raises(GatewayError, match="invalid_response"):
        collect(
            OpenAIProvider(
                config("openai"),
                httpx.MockTransport(
                    lambda r: httpx.Response(
                        200,
                        text='data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
                    )
                ),
            ),
            InferenceInput(prompt="hello"),
        )


def test_missing_os_store_never_falls_back_to_google_or_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_credentials, "store", lambda: (_ for _ in ()).throw(OSError("unavailable"))
    )
    monkeypatch.setenv("GODFATHER_GOOGLE_CLIENT_SECRET", "not-an-api-key")
    with pytest.raises(OSError, match="credential unavailable"):
        provider_credentials.load(config("openai"))


@pytest.mark.parametrize(
    "system,module,backend_name",
    [
        ("Windows", "keyring.backends.Windows", "WinVaultKeyring"),
        ("Darwin", "keyring.backends.macOS", "Keyring"),
        ("Linux", "keyring.backends.SecretService", "Keyring"),
    ],
)
def test_owner_credentials_use_separate_os_store_namespaces(
    system: str,
    module: str,
    backend_name: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values: dict[tuple[str, str], str] = {}

    class Store:
        priority = 1

        def get_password(self, service: str, account: str) -> str | None:
            return values.get((service, account))

        def set_password(self, service: str, account: str, password: str) -> None:
            values[service, account] = password

        def delete_password(self, service: str, account: str) -> None:
            del values[service, account]

    def imported(name: str) -> object:
        assert name == module
        return SimpleNamespace(**{backend_name: Store})

    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(importlib, "import_module", imported)
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "fixture-secret")
    identifier = str(uuid4())
    assert provider_credentials.main(["set", "openai", identifier]) == 0
    assert values == {("ai.the-godfather.provider.openai", identifier): "fixture-secret"}
    assert "fixture-secret" not in capsys.readouterr().out
    assert provider_credentials.main(["delete", "openai", identifier]) == 0
    assert not values
