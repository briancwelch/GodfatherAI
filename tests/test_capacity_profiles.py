"""Measured totals never become owner grants; runtime profiles never derive from disk size."""

import asyncio
import json

import httpx2 as httpx
import pytest
from godfather_api.scheduler import matches, reservation
from godfather_contracts import GPU, ModelDeployment, ModelSelection, Resources
from godfather_contracts.inference import InferenceInput
from godfather_contracts.jobs import Requirements
from godfather_model_gateway import ModelMemoryProfile, ProviderConfig
from godfather_model_gateway.providers import OllamaProvider, OpenAICompatibleProvider
from godfather_worker.desktop import Contribution
from pydantic import ValidationError

from tests.test_inference_matching import model_node

GIB = 1024**3


def hardware() -> Resources:
    return Resources(
        source="physical",
        cpu_name="Measured fixture",
        cpu_count=32,
        ram_bytes=64 * GIB,
        available_ram_bytes=48 * GIB,
        gpus=[GPU(name="Unshared GPU", backend="cuda", memory_bytes=24 * GIB, memory_used_bytes=0)],
    )


def profile() -> ModelMemoryProfile:
    return ModelMemoryProfile(
        estimated_ram_bytes=4 * GIB,
        estimated_vram_bytes=0,
        context_window=2048,
        digest="matching-digest",
        evidence="Synthetic acceptance measurement for CPU-only inference at context 2048",
    )


def test_hardware_is_separate_and_repeated_capping_never_expands_a_budget() -> None:
    actual = hardware()
    capped = Contribution(cpu_cores=2, ram_gib=6).resources(actual)
    assert capped.cpu_count == 2 and capped.ram_bytes == 6 * GIB
    assert capped.available_ram_bytes == 6 * GIB and capped.gpus == []
    assert capped.hardware is not None
    assert capped.hardware.cpu_count == 32 and capped.hardware.ram_bytes == 64 * GIB
    assert capped.hardware.gpus == actual.gpus
    recapped = Contribution(cpu_cores=16, ram_gib=32).resources(capped)
    assert recapped.cpu_count == 2 and recapped.ram_bytes == 6 * GIB
    assert recapped.gpus == [] and recapped.hardware == capped.hardware
    assert actual.cpu_count == 32 and len(actual.gpus) == 1
    assert "hardware" not in actual.model_dump()  # Legacy/unlimited wire shape is unchanged.


@pytest.mark.parametrize("missing", ["ram_bytes", "available_ram_bytes"])
def test_unknown_required_memory_fails_closed_even_with_known_hardware(missing: str) -> None:
    capped = Contribution(cpu_cores=2, ram_gib=6).resources(hardware())
    setattr(capped, missing, None)
    node = model_node("windows")
    node.resources = capped
    assert not matches(
        Requirements(ram_bytes=1, model_selection=ModelSelection(identifier="fixture")), node, []
    )
    assert capped.hardware is not None and capped.hardware.ram_bytes == 64 * GIB


def test_ordinary_gpu_restrictions_and_memory_reservations_remain_authoritative() -> None:
    node = model_node("windows")
    node.resources = Contribution(cpu_cores=4, ram_gib=6).resources(hardware())
    request = Requirements(model_selection=ModelSelection(identifier="fixture"))
    deployment = node.model_deployments[0]
    deployment.estimated_ram_bytes = 4 * GIB
    assert matches(request, node, [])
    assert not matches(request, node, [reservation(request, deployment)])
    deployment.estimated_vram_bytes = 1
    assert not matches(request, node, [])  # Physical GPU presence is never permission.


@pytest.mark.parametrize("kind", ["ollama", "openai_compatible"])
def test_discovery_uses_explicit_runtime_profiles_without_using_download_size(kind: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": name, "digest": "matching-digest", "size": 4096}
                        for name in ("profiled", "unprofiled")
                    ]
                },
            )
        if request.url.path == "/api/show":
            return httpx.Response(
                200, json={"capabilities": ["completion"], "model_info": {"x.context_length": 8192}}
            )
        return httpx.Response(200, json={"data": [{"id": "profiled"}, {"id": "unprofiled"}]})

    async def run() -> None:
        configured = profile().model_copy(update={"digest": None})
        config = ProviderConfig.model_validate(
            {
                "id": "local",
                "provider": kind,
                "url": "http://127.0.0.1" + ("/v1" if kind == "openai_compatible" else ""),
                "memory_profiles": {"profiled": configured.model_dump()},
            }
        )
        adapter = (OllamaProvider if kind == "ollama" else OpenAICompatibleProvider)(
            config, httpx.MockTransport(handle)
        )
        try:
            found = {model.identifier: model for model in await adapter.discover()}
        finally:
            await adapter.close()
        assert found["profiled"].estimated_ram_bytes == 4 * GIB
        assert found["profiled"].estimated_vram_bytes == 0
        assert found["profiled"].context_window == 2048
        assert found["profiled"].metadata_source == "configured"
        assert found["unprofiled"].estimated_ram_bytes is None
        assert found["unprofiled"].estimated_vram_bytes is None
        if kind == "ollama":
            assert found["profiled"].disk_bytes == found["unprofiled"].disk_bytes == 4096

    asyncio.run(run())


def test_digest_change_withdraws_profiled_model_instead_of_reusing_an_old_estimate() -> None:
    config = ProviderConfig(id="local", provider="ollama", memory_profiles={"profiled": profile()})
    model = ModelDeployment(
        provider_id="local", provider="ollama", identifier="profiled", digest="replacement"
    )
    found = config.memory_profile(model)
    assert not found.available and found.estimated_ram_bytes is None


def test_cpu_profile_bounds_actual_ollama_context_and_disables_gpu_offload() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["options"]["num_ctx"] == 2048
        assert payload["options"]["num_gpu"] == 0
        return httpx.Response(200, json={"message": {"content": "fixture"}, "done": True})

    async def run() -> None:
        config = ProviderConfig(
            id="local", provider="ollama", memory_profiles={"profiled": profile()}
        )
        adapter = OllamaProvider(config, httpx.MockTransport(handle))
        request = InferenceInput(prompt="Synthetic prompt", stream=False)
        try:
            chunks = [chunk async for chunk in adapter.infer("profiled", request)]
            assert chunks[-1].done
        finally:
            await adapter.close()

    asyncio.run(run())


def test_profiles_require_explicit_memory_and_evidence() -> None:
    for values in (
        {},
        {"estimated_ram_bytes": 4096},
        {**profile().model_dump(), "evidence": ""},
        {**profile().model_dump(), "estimated_ram_bytes": 0},
    ):
        with pytest.raises(ValidationError):
            ModelMemoryProfile.model_validate(values)
