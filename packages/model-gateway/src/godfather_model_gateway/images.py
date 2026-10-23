"""Bounded native image APIs. No automatic retries, fallback or URL downloads."""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx2 as httpx
from godfather_contracts import Contract, Label, ModelDeployment
from godfather_contracts.inference import InferenceInput
from godfather_contracts.workloads import CLOUD_IMAGE_MODELS, ImageSettings
from pydantic import Field, model_validator

from godfather_model_gateway import Chunk, GatewayError, ProviderConfig
from godfather_model_gateway.providers import HTTPProvider, check_status


class ImageProviderConfig(Contract):
    backend: str = "automatic1111"
    url: str = "http://127.0.0.1:7860"
    models: list[Label] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def local_only(self) -> "ImageProviderConfig":
        url = urlsplit(self.url)
        if (
            self.backend != "automatic1111"
            or url.scheme != "http"
            or url.hostname not in ("127.0.0.1", "::1")
            or url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError("Only an explicitly opted-in loopback AUTOMATIC1111 API is supported")
        if any(len(m) > 80 for m in self.models):
            raise ValueError("Use model names of at most 80 characters")
        return self


class ImageProvider(Protocol):
    async def models(self) -> list[str]: ...
    async def generate(self, prompt: str, settings: ImageSettings) -> list[bytes]: ...


class Automatic1111:
    def __init__(
        self, config: ImageProviderConfig, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self.transport = transport

    async def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> object:
        try:
            async with (
                httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=5 if method == "GET" else 600,
                    transport=self.transport,
                ) as client,
                client.stream(method, self.config.url.rstrip("/") + path, json=payload) as response,
            ):
                if response.status_code != 200:
                    raise GatewayError("provider_unavailable")
                raw = bytearray()
                async for part in response.aiter_bytes():
                    raw.extend(part)
                    if len(raw) > 8 * 1024 * 1024:
                        raise GatewayError("output_limit")
            import json

            return json.loads(raw)
        except (httpx.HTTPError, ValueError):
            raise GatewayError("provider_unavailable") from None

    async def models(self) -> list[str]:
        data = await self.request("GET", "/sdapi/v1/sd-models")
        if not isinstance(data, list):
            raise GatewayError("invalid_response")
        actual = {m.get("model_name") for m in data if isinstance(m, dict)}
        return [m for m in self.config.models if m in actual]

    async def generate(self, prompt: str, settings: ImageSettings) -> list[bytes]:
        if settings.model not in await self.models():
            raise GatewayError("model_unavailable")
        data = await self.request(
            "POST",
            "/sdapi/v1/txt2img",
            {
                "prompt": prompt,
                "width": settings.width,
                "height": settings.height,
                "batch_size": settings.count,
                "n_iter": 1,
                "steps": settings.steps,
                "seed": settings.seed,
                "send_images": True,
                "save_images": False,
                "override_settings": {"sd_model_checkpoint": settings.model},
                "override_settings_restore_afterwards": True,
            },
        )
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("images"), list)
            or len(data["images"]) != settings.count
        ):
            raise GatewayError("invalid_response")
        try:
            images = [base64.b64decode(item, validate=True) for item in data["images"]]
        except (ValueError, TypeError):
            raise GatewayError("invalid_response") from None
        if any(
            not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > 4 * 1024 * 1024
            for image in images
        ):
            raise GatewayError("invalid_response")
        return images


async def gemini_models(client: HTTPProvider) -> set[str]:
    identifiers: set[str] = set()
    token = ""
    seen: set[str] = set()
    try:
        for _ in range(8):
            query = {"pageSize": "1000", **({"pageToken": token} if token else {})}
            data = await client.request("GET", "models?" + urlencode(query))
            identifiers.update(
                m["name"].removeprefix("models/")
                for m in data["models"]
                if "generateContent" in m.get("supportedGenerationMethods", [])
            )
            token = data.get("nextPageToken", "")
            if not token:
                return identifiers
            if not isinstance(token, str) or len(token) > 4096 or token in seen:
                raise GatewayError("invalid_response")
            seen.add(token)
    except (KeyError, TypeError, AttributeError, ValueError):
        raise GatewayError("invalid_response") from None
    raise GatewayError("output_limit")


class GeminiImageInventory(HTTPProvider):
    async def discover(self) -> list[ModelDeployment]:
        try:
            identifiers = await gemini_models(self)
            return [
                ModelDeployment(
                    provider_id=self.config.id,
                    provider="gemini",
                    connection_id=self.config.connection_id,
                    identifier=m.identifier,
                    operations=["image_generation"],
                    metadata_source="configured",
                )
                for m in self.config.model_catalog
                if m.modality == "image"
                and m.identifier in identifiers
                and m.identifier in CLOUD_IMAGE_MODELS["gemini"]
            ]
        except (KeyError, TypeError, AttributeError, ValueError):
            raise GatewayError("invalid_response") from None

    async def infer(self, model: str, request: InferenceInput) -> AsyncGenerator[Chunk]:
        raise GatewayError("invalid_request")
        yield Chunk()  # This inventory cannot execute text requests.


@dataclass
class CloudImageResult:
    images: list[bytes]
    input_tokens: int | None = None
    output_tokens: int | None = None


class CloudImages:
    def __init__(
        self, config: ProviderConfig, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config, self.transport = config, transport

    def validate(self, settings: ImageSettings) -> None:
        if (
            self.config.provider != settings.backend
            or settings.backend not in CLOUD_IMAGE_MODELS
            or settings.model not in CLOUD_IMAGE_MODELS[settings.backend]
            or not self.config.has_account_api_key
            or not any(
                m.identifier == settings.model and m.modality == "image"
                for m in self.config.model_catalog
            )
        ):
            raise GatewayError("model_unavailable")

    async def generate(self, prompt: str, settings: ImageSettings) -> CloudImageResult:
        self.validate(settings)
        if settings.backend == "openai":
            endpoint = "/images/generations"
            payload: dict[str, object] = {
                "model": settings.model,
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "output_format": "png",
                "quality": "medium",
            }
        else:
            endpoint = f"/models/{settings.model}:generateContent"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "imageConfig": {"aspectRatio": "1:1"},
                },
            }
        try:
            async with (
                asyncio.timeout(600),
                httpx.AsyncClient(
                    trust_env=False, follow_redirects=False, timeout=600, transport=self.transport
                ) as client,
                client.stream(
                    "POST", self.config.url + endpoint, json=payload, headers=self.config.headers()
                ) as response,
            ):
                check_status(response.status_code)
                raw = bytearray()
                async for part in response.aiter_bytes():
                    raw.extend(part)
                    if len(raw) > 8 * 1024**2:
                        raise GatewayError("output_limit")
            data = json.loads(raw)
            if settings.backend == "openai":
                encoded = [item["b64_json"] for item in data["data"]]
                usage = data.get("usage") or {}
                input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
            else:
                encoded = [
                    part["inlineData"]["data"]
                    for candidate in data["candidates"]
                    for part in candidate["content"]["parts"]
                    if not part.get("thought")
                    and "inlineData" in part
                    and part["inlineData"].get("mimeType") == "image/png"
                ]
                usage = data.get("usageMetadata") or {}
                input_tokens = usage.get("promptTokenCount")
                output_tokens = usage.get("candidatesTokenCount")
            if len(encoded) != 1:
                raise GatewayError("invalid_response")
            images = [base64.b64decode(item, validate=True) for item in encoded]
            if any(
                not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 4 * 1024**2 for raw in images
            ):
                raise GatewayError("invalid_response")
            if any(
                value is not None and (type(value) is not int or not 0 <= value <= 2**40)
                for value in (input_tokens, output_tokens)
            ):
                raise GatewayError("invalid_response")
            return CloudImageResult(images, input_tokens, output_tokens)
        except (httpx.TimeoutException, TimeoutError):
            raise GatewayError("provider_timeout") from None
        except httpx.RequestError:
            raise GatewayError("provider_unavailable") from None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GatewayError("invalid_response") from None
