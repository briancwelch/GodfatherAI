"""Model matching is OS/provider-neutral and never silently replaces exact identifiers."""

import pytest
from godfather_api.scheduler import deployment_for, matches
from godfather_contracts import ModelDeployment, ModelSelection, NodeView
from godfather_contracts.jobs import Requirements

from tests.test_scheduler import node_view


def model_node(os: str) -> NodeView:
    node = node_view()
    node.os = os  # type: ignore[assignment]
    node.resources.source = "physical"
    node.inference_protocol_version = 1
    node.job_protocol_version = None
    node.model_deployments = [
        ModelDeployment(
            provider_id="local",
            provider="ollama",
            identifier="fixture",
            verified_capabilities=["completion"],
            declared_capabilities=["research"],
            operations=["chat", "stream"],
            context_window=4096,
        )
    ]
    return node


@pytest.mark.parametrize("os", ["windows", "macos", "linux"])
def test_portable_model_requirements(os: str) -> None:
    node = model_node(os)
    req = Requirements(model_selection=ModelSelection(identifier="fixture"))
    assert matches(req, node, [])
    assert deployment_for(req, node, []) == node.model_deployments[0]
    req.model_selection = ModelSelection(identifier="different")
    assert not matches(req, node, [])
    req.model_selection = ModelSelection(capabilities=["completion"])
    assert matches(req, node, [])
    req.model_selection = ModelSelection(capabilities=["research"])
    assert not matches(req, node, [])
    req.model_selection.allow_declared_capabilities = True
    assert matches(req, node, [])
    req.os = "linux" if os != "linux" else "windows"
    assert not matches(req, node, [])


@pytest.mark.parametrize(
    "override",
    ["unavailable", "operation", "context", "opt_in", "ram", "vram", "reserved", "provider"],
)
def test_incompatible_deployments_fail_closed(override: str) -> None:
    node = model_node("windows")
    req = Requirements(model_selection=ModelSelection(identifier="fixture", context_window=4096))
    reserved: list[Requirements] = []
    if override == "unavailable":
        node.model_deployments[0].available = False
    elif override == "operation":
        node.model_deployments[0].operations = ["chat"]
    elif override == "context":
        node.model_deployments[0].context_window = None
    elif override == "opt_in":
        node.inference_protocol_version = None
    elif override == "ram":
        node.model_deployments[0].estimated_ram_bytes = 2**50
    elif override == "vram":
        node.model_deployments[0].estimated_vram_bytes = 2**50
    elif override == "reserved":
        reserved = [Requirements(cpu_count=node.resources.cpu_count)]
    else:
        assert req.model_selection is not None
        req.model_selection.provider = "openai_compatible"
    assert not matches(req, node, reserved)


def test_capability_selection_can_choose_a_smaller_compatible_deployment() -> None:
    node = model_node("macos")
    node.model_deployments[0].estimated_ram_bytes = 2**50
    node.model_deployments.append(
        node.model_deployments[0].model_copy(
            update={
                "identifier": "smaller",
                "estimated_ram_bytes": None,
            }
        )
    )
    req = Requirements(model_selection=ModelSelection(capabilities=["completion"]))
    assert matches(req, node, [])
    selected = deployment_for(req, node, [])
    assert selected is not None and selected.identifier == "smaller"
