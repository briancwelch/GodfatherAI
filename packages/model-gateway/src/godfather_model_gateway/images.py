"""Local image adapter boundary. No credentials, paid fallback, retries or downloads."""

import base64
from typing import Protocol
from urllib.parse import urlsplit

import httpx2 as httpx
from godfather_contracts import Contract, Label
from godfather_contracts.workloads import ImageSettings
from pydantic import Field, model_validator

from godfather_model_gateway import GatewayError


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
