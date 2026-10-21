"""Portable contracts, deterministic tools, validated execution and artifact integrity."""

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest
from godfather_agent_runtime import WorkflowError, execute_workflow
from godfather_agent_runtime.tools import ToolError, authorize, execute_tool, validate_agent
from godfather_api.artifacts import ArtifactError, LocalArtifactStore, encode
from godfather_contracts import ModelDeployment, ToolReference
from godfather_contracts.agents import (
    AgentDefinition,
    AgentView,
    ArtifactReference,
    CompletedStep,
    StepOutput,
    WorkflowAssignment,
    WorkflowInput,
    WorkflowState,
)
from godfather_model_gateway import Chunk
from pydantic import ValidationError

from tests.workflow_helpers import sample_definition


def test_agent_definition_has_an_aggregate_portable_size_limit() -> None:
    value = sample_definition().model_dump(mode="json")
    template = value["workflow"]["steps"][0]
    value["workflow"]["steps"] = [
        {**template, "id": f"step{i}", "instruction": "x" * 4096} for i in range(32)
    ]
    with pytest.raises(ValidationError, match="128 KiB"):
        AgentDefinition.model_validate(value)


def test_old_checkpoint_model_snapshots_normalize_to_compact_references() -> None:
    state = bundle().state
    ref = ArtifactReference(id=uuid4(), checksum="a" * 64, size_bytes=1)
    data = {
        "step_id": "plan",
        "output": ref.model_dump(),
        "attempt_id": state.attempt_id,
        "fencing_token": 1,
        "model": model().model_dump(mode="json"),
    }
    completed = CompletedStep.model_validate(data)
    assert completed.model is not None and completed.model.identifier == "fixture"
    assert "operations" not in completed.model_dump_json()
    assert "verified_capabilities" not in completed.model_dump_json()


def test_workflow_cli_refuses_remote_provider_before_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    from godfather_worker import cli

    config = tmp_path / "providers.json"
    config.write_text(
        json.dumps(
            [{"id": "remote", "provider": "openai_compatible", "url": "https://remote.invalid/v1"}]
        ),
        encoding="utf-8",
    )
    credential = tmp_path / "worker.json"
    credential.write_text(json.dumps({"kind": "worker", "token": "x" * 43}), encoding="utf-8")

    async def forbidden(configs: object) -> object:
        raise AssertionError("Provider discovery must not occur")

    monkeypatch.setattr(cli, "discover_models", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "godfather-worker",
            "--credential-file",
            str(credential),
            "--inference-config",
            str(config),
            "--execute-workflows",
            "--simulate",
            "LV-01",
        ],
    )
    assert cli.main() == 1
    output = capsys.readouterr().out
    assert "worker.configuration_invalid" in output and "remote.invalid" not in output


class MockModel:
    def __init__(self, invalid: bool = False) -> None:
        self.calls: list[str] = []
        self.invalid = invalid
        self.closed = False

    async def discover(self) -> list[ModelDeployment]:
        return [model()]

    async def infer(self, identifier: str, request: object) -> AsyncGenerator[Chunk]:
        self.calls.append(identifier)
        text = (
            "not JSON"
            if self.invalid
            else json.dumps({"title": "Portable plan", "items": ["Inspect", "Report"]})
            if "Return only JSON matching" in str(getattr(request, "prompt", ""))
            else "Inspected the plan and prepared a report."
        )
        yield Chunk(text=text, done=True, input_tokens=3, output_tokens=2)

    async def close(self) -> None:
        self.closed = True


def model() -> ModelDeployment:
    return ModelDeployment(
        provider_id="local", provider="ollama", identifier="fixture", operations=["chat", "stream"]
    )


def bundle() -> WorkflowAssignment:
    spec = sample_definition()
    agent_id = uuid4()
    return WorkflowAssignment(
        agent=AgentView(
            id=agent_id,
            version_id=uuid4(),
            version=1,
            owner_id=uuid4(),
            workspace_id=uuid4(),
            enabled=True,
            definition=spec,
        ),
        state=WorkflowState(
            job_id=uuid4(),
            agent_id=agent_id,
            agent_version=1,
            workflow_id=spec.workflow.id,
            workflow_version=1,
            attempt_id=uuid4(),
            fencing_token=1,
        ),
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "duplicate",
        "forward",
        "tool_schema",
        "permission",
        "unknown_tool",
        "bound_node",
        "empty_model",
    ],
)
def test_definition_validation(invalid: str) -> None:
    value = sample_definition().model_dump(mode="json")
    if invalid == "duplicate":
        value["workflow"]["steps"][1]["id"] = "plan"
    elif invalid == "forward":
        value["workflow"]["steps"][0]["input_step"] = "summary"
    elif invalid == "tool_schema":
        value["workflow"]["steps"][0]["output_schema"] = "text"
    elif invalid == "permission":
        value["permissions"] = []
    elif invalid == "unknown_tool":
        value["allowed_tools"].append({"name": "shell", "version": 1})
    elif invalid == "bound_node":
        value["node_id"] = str(uuid4())
    else:
        value["requirements"]["model_selection"] = None
    with pytest.raises((ValidationError, ToolError)):
        validate_agent(AgentDefinition.model_validate(value))


@pytest.mark.parametrize("os", ["windows", "macos", "linux"])
def test_tool_permissions_and_portability(os: str) -> None:
    agent = sample_definition()
    ref = ToolReference(name="plan.describe", version=1)
    with pytest.raises(ToolError):
        authorize(ref, agent, [], ["plan.read"], os)
    with pytest.raises(ToolError):
        authorize(ref, agent, [ref], [], os)
    result = asyncio.run(
        execute_tool(ref, {"title": "Safe", "items": ["a", "b"]}, agent, [ref], ["plan.read"], os)
    )
    assert result.item_count == 2 and result.outline == "a\nb"
    with pytest.raises(ValidationError):
        asyncio.run(execute_tool(ref, {"shell": "not allowed"}, agent, [ref], ["plan.read"], os))


def test_checkpoint_prefix_and_serialization_are_platform_independent() -> None:
    state = bundle().state
    data = encode({"title": "Unicode plan", "items": ["Windows", "macOS", "Linux"]})
    ref = ArtifactReference(
        id=uuid4(), checksum=hashlib.sha256(data).hexdigest(), size_bytes=len(data)
    )
    completed = CompletedStep(
        step_id="plan", output=ref, attempt_id=state.attempt_id, fencing_token=1, model=model()
    )
    state = WorkflowState.model_validate(
        {
            **state.model_dump(),
            "completed": [completed],
            "context": {"plan": ref},
            "current_step": 1,
            "checkpoint_version": 1,
        }
    )
    assert WorkflowState.model_validate_json(state.model_dump_json()) == state
    assert "Windows" not in state.model_dump_json()  # Outputs live in referenced artifacts.
    with pytest.raises(ValidationError):
        WorkflowState.model_validate({**state.model_dump(), "checkpoint_version": 2})
    with pytest.raises(ValidationError):
        WorkflowState.model_validate({**state.model_dump(), "context": {}})


def test_local_artifacts_are_immutable_bounded_and_verified(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    key = uuid4()
    raw = encode({"text": "portable ✓"})
    digest = hashlib.sha256(raw).hexdigest()
    store.write(key, raw)
    assert store.read(key, digest, len(raw)) == raw
    with pytest.raises(ArtifactError):
        store.write(key, raw)
    with pytest.raises(ArtifactError):
        store.write(uuid4(), b"x" * (8 * 1024 * 1024 + 1))
    with pytest.raises(ArtifactError):
        store.path("../outside")  # type: ignore[arg-type]
    store.path(key).write_bytes(b"corruption")
    with pytest.raises(ArtifactError):
        store.read(key, digest, len(raw))


@pytest.mark.parametrize("invalid", [False, True])
def test_sequential_model_tool_model_with_validated_checkpoints(invalid: bool) -> None:
    async def run() -> None:
        assignment = bundle()
        provider = MockModel(invalid)
        state = assignment.state
        objects: dict[object, object] = {}
        starts: list[str] = []

        async def read(ref: ArtifactReference) -> object:
            return objects[ref.id]

        async def report(
            action: str, step_id: str, version: int, output: StepOutput | None, usage: object | None
        ) -> WorkflowState:
            nonlocal state
            assert version == state.checkpoint_version
            if action == "step_start":
                starts.append(step_id)
                return state
            assert output is not None
            raw = encode(output.model_dump(mode="json"))
            ref = ArtifactReference(
                id=uuid4(), checksum=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw)
            )
            objects[ref.id] = output.model_dump(mode="json")
            step = CompletedStep(
                step_id=step_id, output=ref, attempt_id=state.attempt_id, fencing_token=1
            )
            state = WorkflowState.model_validate(
                {
                    **state.model_dump(),
                    "completed": state.completed + [step],
                    "context": {**state.context, step_id: ref},
                    "current_step": version + 1,
                    "checkpoint_version": version + 1,
                }
            )
            return state

        if invalid:
            with pytest.raises(WorkflowError, match="workflow_validation"):
                await execute_workflow(
                    assignment,
                    WorkflowInput(instruction="Create a plan"),
                    model(),
                    provider,
                    assignment.agent.definition.allowed_tools,
                    ["plan.read"],
                    "windows",
                    read,
                    report,
                )
            assert starts == ["plan"] and state.checkpoint_version == 0
        else:
            result = await execute_workflow(
                assignment,
                WorkflowInput(instruction="Create a plan"),
                model(),
                provider,
                assignment.agent.definition.allowed_tools,
                ["plan.read"],
                "linux",
                read,
                report,
            )
            assert (
                result.completed_steps == ["plan", "describe", "summary"]
                and len(provider.calls) == 2
            )

    asyncio.run(run())
