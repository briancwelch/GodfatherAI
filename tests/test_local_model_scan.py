"""Read-only multi-library discovery, bounded inventories, and owner consent."""

import asyncio
import json
import os
import threading
from pathlib import Path
from unittest.mock import Mock

import httpx2 as httpx
import pytest
from godfather_contracts import Advertisement, ModelDeployment
from godfather_model_gateway import ProviderConfig
from godfather_model_gateway.providers import HTTPProvider, OllamaProvider, OpenAICompatibleProvider
from godfather_worker import local_model_scan as scan
from godfather_worker.desktop import Contribution
from godfather_worker.simulated import profile
from pydantic import ValidationError


def weight(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"untrusted model bytes; never execute or deserialize")
    return path


def test_files_hf_mlx_shards_and_custom_folders_are_detected_without_loading(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "huggingface/hub/models--org--text/snapshots/abcdef123456"
    weight(snapshot / "model-00001-of-00002.safetensors")
    weight(snapshot / "model-00002-of-00002.safetensors")
    weight(tmp_path / "LM Studio/org/model/model-Q4.gguf")
    weight(tmp_path / "GPT4All/another.gguf")
    weight(tmp_path / "ComfyUI/models/checkpoints/image.safetensors")
    mlx = tmp_path / "mlx/org/model"
    weight(mlx / "model-00001-of-00002.safetensors")
    weight(mlx / "model-00002-of-00002.safetensors")
    (mlx / "config.json").write_text("{}")
    weight(tmp_path / "custom/audio.onnx")
    weight(tmp_path / "node_modules/ignored.gguf")
    weight(tmp_path / "unrelated.bin")
    result = scan.scan([tmp_path, snapshot], configs=[])
    assert len(result.models) == 6
    assert len({m.location for m in result.models}) == 6
    assert any(m.name == "org/text (abcdef12)" for m in result.models)
    assert not any(m.served for m in result.models)
    assert not result.providers and not result.incomplete


def test_gguf_shards_group_but_quantizations_stay_distinct(tmp_path: Path) -> None:
    for name in ("model-Q4-00001-of-00002.gguf", "model-Q4-00002-of-00002.gguf", "model-Q8.gguf"):
        weight(tmp_path / name)
    result = scan.scan([tmp_path], configs=[])
    assert all(Path(m.location).exists() for m in result.models)
    assert {m.name for m in result.models} == {
        "model-Q4.gguf",
        "model-Q8.gguf",
    }


def test_coreml_bundles_count_once_and_are_never_loaded(tmp_path: Path) -> None:
    weight(tmp_path / "vision.mlpackage/Data/model.mlmodel")
    weight(tmp_path / "compiled.mlmodelc/weights.bin")
    result = scan.scan([tmp_path], configs=[])
    assert {m.name for m in result.models} == {"vision.mlpackage", "compiled.mlmodelc"}
    assert all(m.source == "Core ML bundle" and not m.served for m in result.models)


def test_scan_refuses_nonlocal_and_authenticated_provider_configs() -> None:
    with pytest.raises(ValueError, match="loopback"):
        scan.scan(
            [],
            configs=[
                ProviderConfig(
                    id="remote", provider="openai_compatible", url="https://remote.invalid/v1"
                )
            ],
        )


def test_ollama_offline_manifests_require_installed_blobs_and_deduplicate_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "ollama"
    digest = "sha256:" + "a" * 64
    weight(store / "blobs" / digest.replace(":", "-"))
    manifest = store / "manifests/registry.ollama.ai/library/fixture/latest"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {"layers": [{"digest": digest, "mediaType": "application/vnd.ollama.image.model"}]}
        )
    )
    missing = store / "manifests/registry.ollama.ai/library/missing/latest"
    missing.parent.mkdir(parents=True)
    missing.write_text(json.dumps({"layers": [{"digest": "sha256:" + "b" * 64}]}))
    offline = scan.scan([store], configs=[])
    assert [m.name for m in offline.models] == ["fixture:latest"]

    async def probe(_: object) -> list[list[str]]:
        return [["fixture:latest"]]

    monkeypatch.setattr(scan, "probe_servers", probe)
    online = scan.scan([store], configs=[ProviderConfig(id="local-ollama", provider="ollama")])
    assert len(online.models) == 1 and online.models[0].served
    assert online.models[0].gguf_path == str(store / "blobs" / digest.replace(":", "-"))


def test_inventory_cap_is_explicit_and_compatible_with_existing_protocol(tmp_path: Path) -> None:
    for i in range(131):
        weight(tmp_path / f"model-{i}.gguf")
    result = scan.scan([tmp_path], configs=[])
    assert len(result.models) == 128 and result.omitted == 3
    original = profile("LA-01")
    data = original.model_dump()
    data["installed_models"] = [{"runtime": "files", "identifier": m.name} for m in result.models]
    assert len(Advertisement.model_validate(data).installed_models) == 128


def test_cancel_and_work_limits_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weight(tmp_path / "model.gguf")
    cancel = threading.Event()
    cancel.set()
    result = scan.scan([tmp_path], configs=[], cancel=cancel)
    assert result.cancelled and result.incomplete and not result.models
    monkeypatch.setattr(scan, "FILE_LIMIT", 1)
    result = scan.scan([tmp_path], configs=[])
    assert result.incomplete and not result.cancelled


def test_unreadable_root_does_not_abort_other_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    denied, readable = tmp_path / "denied", tmp_path / "readable"
    denied.mkdir()
    weight(readable / "model.gguf")
    original = os.scandir

    def scandir(path: Path) -> object:
        if path == denied:
            raise PermissionError("denied")
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    result = scan.scan([denied, readable], configs=[])
    assert len(result.models) == 1 and result.unreadable == 1


def test_scan_probes_only_model_metadata_and_keeps_capabilities_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "fixture:latest"}]})
        return httpx.Response(
            200, json={"data": [{"id": "local-model"}, {"id": "<invalid>"}, None]}
        )

    monkeypatch.setattr(
        scan, "HTTPProvider", lambda config: HTTPProvider(config, httpx.MockTransport(handle))
    )
    configs = scan.local_servers()[:2]
    result = scan.scan([], configs=configs)
    assert len(result.models) == 2
    assert all(m.served for m in result.models)
    assert all(not c.chat_enabled and not c.stream_enabled for c in result.providers)
    assert all(r.method == "GET" and r.url.host == "127.0.0.1" for r in requests)
    assert result.providers[1].discovery_models == ["local-model"]


@pytest.mark.parametrize("provider_type", [OllamaProvider, OpenAICompatibleProvider])
def test_selected_server_inventory_never_exceeds_scan_selection(
    provider_type: type[HTTPProvider],
) -> None:
    kind = "ollama" if provider_type is OllamaProvider else "openai_compatible"
    rows = [{"name": f"model-{i}", "id": f"model-{i}"} for i in range(140)]

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        return httpx.Response(200, json={"models": rows, "data": rows})

    async def run() -> None:
        config = ProviderConfig.model_validate(
            {"id": "local", "provider": kind, "discovery_models": ["model-4", "model-130"]}
        )
        provider = provider_type(config, httpx.MockTransport(handle))
        try:
            assert {m.identifier for m in await provider.discover()} == {"model-4", "model-130"}  # type: ignore[attr-defined]
        finally:
            await provider.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "extra",
    [{"url": "https://remote.invalid/v1"}, {"api_key_env": "PRIVATE_KEY"}, {"id": "local-ollama"}],
)
def test_scanned_servers_cannot_enable_remote_or_credentialed_access(extra: dict[str, str]) -> None:
    config = {
        "id": "local",
        "provider": "openai_compatible",
        "url": "http://127.0.0.1:1234/v1",
        **extra,
    }
    with pytest.raises(ValidationError):
        Contribution.model_validate({"local_providers": [config]})


def test_default_libraries_include_configured_cache_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "custom-ollama"))
    monkeypatch.setattr("psutil.disk_partitions", Mock(return_value=[]))
    roots = scan.default_roots(tmp_path)
    assert tmp_path / "hf/hub" in roots and tmp_path / "custom-ollama" in roots
    assert tmp_path / ".lmstudio/models" in roots


def test_combined_live_provider_inventory_caps_without_crashing_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from godfather_worker.inference import discover_models

    class Provider:
        def __init__(self, config: ProviderConfig) -> None:
            self.config = config

        async def discover(self) -> list[ModelDeployment]:
            return [
                ModelDeployment(
                    provider_id=self.config.id, provider="ollama", identifier=f"model-{i}"
                )
                for i in range(80)
            ]

        async def close(self) -> None:
            pass

    monkeypatch.setattr("godfather_worker.inference.create_provider", Provider)
    models = asyncio.run(
        discover_models(
            [
                ProviderConfig(id="first", provider="ollama"),
                ProviderConfig(id="second", provider="ollama"),
            ]
        )
    )
    assert len(models) == 128
    assert sum(m.provider_id == "first" for m in models) == 80
    assert sum(m.provider_id == "second" for m in models) == 48
