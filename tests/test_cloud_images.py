"""Native image contracts with mocked HTTP; no provider credentials or paid calls."""

import asyncio
import base64
import io
import json
from typing import Literal
from uuid import uuid4

import httpx2 as httpx
import pytest
from godfather_agent_runtime import WorkflowError
from godfather_api.account_providers import discover_catalog
from godfather_contracts import ModelSelection
from godfather_contracts.agents import WorkflowInput
from godfather_contracts.workloads import ImageSettings
from godfather_model_gateway import GatewayError, NativeModel, ProviderConfig
from godfather_model_gateway.frontier import OpenAIProvider
from godfather_model_gateway.images import CloudImages, GeminiImageInventory
from godfather_model_gateway.providers import HTTPProvider
from godfather_worker.desktop import Contribution
from godfather_worker.workloads import image_output
from PIL import Image
from pydantic import ValidationError


def png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1024, 1024)).save(output, format="PNG")
    return output.getvalue()


def config(provider: str) -> ProviderConfig:
    model = "gpt-image-1.5" if provider == "openai" else "gemini-3.1-flash-image"
    value = ProviderConfig.model_validate(
        {
            "id": "account-images",
            "provider": provider,
            "connection_id": uuid4(),
            "model_catalog": [
                NativeModel(
                    identifier=model, modality="image", context_window=1, max_output_tokens=1
                )
            ],
        }
    )
    value.set_api_key("fixture-image-secret", account=True)
    return value


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_native_image_request_response_and_secret_boundary(provider: str) -> None:
    value = config(provider)
    model = value.model_catalog[0].identifier
    calls = []
    raw = png()

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        encoded = base64.b64encode(raw).decode()
        assert "fixture-image-secret" not in request.content.decode()
        if provider == "openai":
            assert str(request.url) == "https://api.openai.com/v1/images/generations"
            assert request.headers["Authorization"] == "Bearer fixture-image-secret"
            assert body == {
                "model": model,
                "prompt": "Test square",
                "n": 1,
                "size": "1024x1024",
                "output_format": "png",
                "quality": "medium",
            }
            return httpx.Response(
                200,
                json={
                    "data": [{"b64_json": encoded}],
                    "usage": {"input_tokens": 12, "output_tokens": 6},
                },
            )
        assert (
            str(request.url)
            == f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        assert request.headers["x-goog-api-key"] == "fixture-image-secret"
        assert body["generationConfig"] == {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "1:1"},
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"inlineData": {"mimeType": "image/png", "data": encoded}}]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 6},
            },
        )

    adapter = CloudImages(value, httpx.MockTransport(respond))
    result = asyncio.run(
        adapter.generate(
            "Test square",
            ImageSettings(
                backend=provider,
                model=model,
                width=1024,
                height=1024,
            ),
        )
    )
    assert result.images == [raw] and result.input_tokens == 12 and result.output_tokens == 6
    assert len(calls) == 1
    assert "fixture-image-secret" not in repr(value) + value.model_dump_json()


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "provider_auth"),
        (429, "rate_limited"),
        (503, "provider_unavailable"),
        (302, "invalid_request"),
    ],
)
def test_cloud_errors_are_redacted_and_never_retried(status: int, code: str) -> None:
    value = config("openai")
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            text="fixture-image-secret private prompt",
            headers={"location": "https://foreign.invalid/steal"},
        )

    with pytest.raises(GatewayError) as error:
        asyncio.run(
            CloudImages(value, httpx.MockTransport(respond)).generate(
                "private prompt",
                ImageSettings(backend="openai", model="gpt-image-1.5", width=1024, height=1024),
            )
        )
    assert str(error.value) == code and len(calls) == 1


@pytest.mark.parametrize(
    "data",
    [
        {"data": [{"url": "https://foreign.invalid/image.png"}]},
        {"data": [{"b64_json": "not base64"}]},
        {"data": [{"b64_json": "bm90IGFuIGltYWdl"}]},
        {"data": []},
        {"data": [{"b64_json": "eA=="}, {"b64_json": "eA=="}]},
    ],
)
def test_cloud_rejects_urls_malformed_images_and_wrong_count(data: object) -> None:
    with pytest.raises(GatewayError, match="invalid_response"):
        asyncio.run(
            CloudImages(
                config("openai"), httpx.MockTransport(lambda _: httpx.Response(200, json=data))
            ).generate(
                "prompt",
                ImageSettings(backend="openai", model="gpt-image-1.5", width=1024, height=1024),
            )
        )


def test_cloud_settings_require_explicit_supported_model_size_and_account_key() -> None:
    for update in ({"count": 2}, {"width": 512}, {"seed": 1}, {"steps": 5}, {"model": "gpt-4.1"}):
        with pytest.raises(ValidationError):
            ImageSettings.model_validate(
                {
                    "backend": "openai",
                    "model": "gpt-image-1.5",
                    "width": 1024,
                    "height": 1024,
                    **update,
                }
            )
    value = config("openai")
    value.set_api_key("fixture-image-secret")
    with pytest.raises(GatewayError, match="model_unavailable"):
        CloudImages(value).validate(
            ImageSettings(backend="openai", model="gpt-image-1.5", width=1024, height=1024)
        )
    assert not Contribution().cloud_images
    with pytest.raises(ValidationError):
        ModelSelection(
            provider="gemini",
            identifier="gemini-3.1-flash-image",
            connection_id=uuid4(),
            paid_consent=True,
            required_operations=["image_generation"],
        )


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_account_catalog_discovers_image_only_models_and_inventory_is_not_chat(
    provider: Literal["openai", "gemini"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = config(provider)
    model = value.model_catalog[0].identifier

    async def request(
        self: HTTPProvider, method: str, path: str, payload: dict[str, object] | None = None
    ) -> dict[str, object]:
        assert method == "GET"
        return (
            {"data": [{"id": model}, {"id": "unreviewed-image-model"}]}
            if provider == "openai"
            else {
                "models": [
                    {"name": "models/" + model, "supportedGenerationMethods": ["generateContent"]}
                ],
            }
        )

    monkeypatch.setattr(HTTPProvider, "request", request)

    async def run() -> None:
        catalog = await discover_catalog(provider, "fixture-image-secret")
        assert len(catalog) == 1 and catalog[0].modality == "image"
        instance = OpenAIProvider(value) if provider == "openai" else GeminiImageInventory(value)
        try:
            deployments = await instance.discover()
            assert len(deployments) == 1
            assert deployments[0].operations == ["image_generation"]
        finally:
            await instance.close()

    asyncio.run(run())


def test_transport_timeout_size_limit_and_cancellation_do_not_replay() -> None:
    settings = ImageSettings(backend="openai", model="gpt-image-1.5", width=1024, height=1024)

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture-image-secret", request=request)

    with pytest.raises(GatewayError, match="provider_timeout"):
        asyncio.run(
            CloudImages(config("openai"), httpx.MockTransport(timeout)).generate("test", settings)
        )
    with pytest.raises(GatewayError, match="output_limit"):
        asyncio.run(
            CloudImages(
                config("openai"),
                httpx.MockTransport(
                    lambda _: httpx.Response(200, content=b"x" * (8 * 1024**2 + 1))
                ),
            ).generate("test", settings)
        )

    async def cancel() -> None:
        entered = asyncio.Event()
        calls = []

        async def blocked(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        task = asyncio.create_task(
            CloudImages(config("openai"), httpx.MockTransport(blocked)).generate("test", settings)
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(calls) == 1

    asyncio.run(cancel())


def test_image_artifact_reencodes_pixels_and_rejects_unexpected_dimensions() -> None:
    from PIL.PngImagePlugin import PngInfo

    raw = io.BytesIO()
    metadata = PngInfo()
    metadata.add_text("backend-private", "fixture-metadata-path")
    Image.new("RGB", (1024, 1024)).save(raw, format="PNG", pnginfo=metadata)
    payload = WorkflowInput(
        instruction="test",
        image=ImageSettings(backend="openai", model="gpt-image-1.5", width=1024, height=1024),
    )
    output = image_output([raw.getvalue()], payload)
    assert b"fixture-metadata-path" not in base64.b64decode(output.files[0].content_base64)
    payload.image = ImageSettings(model="local", width=512, height=512)
    with pytest.raises(WorkflowError, match="workflow_validation"):
        image_output([raw.getvalue()], payload)
