"""Portable sequential workflow and artifact/checkpoint contracts v1."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from godfather_contracts import Contract, Label, ModelDeployment, ToolReference
from godfather_contracts.coding import CODING_RUNTIME, CodingOutput
from godfather_contracts.execution import AttemptIdentity, Requirements, RetryPolicy
from godfather_contracts.inference import InferenceParameters, InferenceUsage
from godfather_contracts.workloads import (
    IMAGE_RUNTIME,
    MAX_ARTIFACT_BYTES,
    WORKLOAD_RUNTIME,
    AnalysisSettings,
    Dataset,
    ImageSettings,
    WorkloadOutput,
)


class Plan(Contract):
    title: str = Field(min_length=1, max_length=128)
    items: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(
        min_length=1, max_length=16
    )


class TextOutput(Contract):
    text: str = Field(min_length=1, max_length=8192)


class PlanSummary(Contract):
    title: str = Field(min_length=1, max_length=128)
    item_count: int = Field(ge=1, le=16)
    outline: str = Field(min_length=1, max_length=8192)


StepOutput = Plan | TextOutput | PlanSummary | CodingOutput | WorkloadOutput


class WorkflowStep(Contract):
    id: Label
    kind: Literal["model", "tool", "coding", "analytics", "report", "image"]
    instruction: str = Field(default="", max_length=4096)
    output_schema: Literal["plan", "text", "plan_summary", "coding", "workload"]
    input_step: Label | None = None
    tool: ToolReference | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    parameters: InferenceParameters = Field(default_factory=InferenceParameters)

    @model_validator(mode="after")
    def supported_operation(self) -> "WorkflowStep":
        if self.kind in ("analytics", "report", "image"):
            if self.tool or self.output_schema != "workload":
                raise ValueError("Data stages require the workload output contract")
            if (self.kind == "report") != (self.input_step is not None):
                raise ValueError("Only report stages require a prior analytics stage")
            return self
        if self.kind == "coding":
            if (
                self.tool
                or self.output_schema != "coding"
                or not self.instruction
                or self.input_step
            ):
                raise ValueError("Coding requires its bounded isolated-workspace output contract")
            return self
        if self.kind == "model":
            if not self.instruction or self.tool or self.output_schema not in ("plan", "text"):
                raise ValueError("Model steps require an instruction and a supported output schema")
        elif self.tool is None or self.input_step is None or self.output_schema != "plan_summary":
            raise ValueError(
                "Tool steps require a tool, prior input step and matching output schema"
            )
        return self


class WorkflowDefinition(Contract):
    id: UUID
    version: int = Field(default=1, ge=1, le=100000)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def sequential_graph(self) -> "WorkflowDefinition":
        seen: dict[str, WorkflowStep] = {}
        for step in self.steps:
            if step.id in seen or (step.input_step is not None and step.input_step not in seen):
                raise ValueError(
                    "Steps must have unique IDs and reference only completed predecessors"
                )
            if step.kind == "tool" and seen[str(step.input_step)].output_schema != "plan":
                raise ValueError("The demonstration tool requires a structured plan predecessor")
            if step.kind == "report" and seen[str(step.input_step)].kind != "analytics":
                raise ValueError("Reports require a validated analytics predecessor")
            seen[step.id] = step
        return self


class AgentDefinition(Contract):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    requirements: Requirements
    allowed_tools: list[ToolReference] = Field(default_factory=list, max_length=16)
    permissions: list[Label] = Field(default_factory=list, max_length=16)
    workflow: WorkflowDefinition
    timeout_seconds: int = Field(default=600, ge=1, le=86400)
    retry: RetryPolicy = Field(default_factory=lambda: RetryPolicy(limit=1))
    checkpoint_policy: Literal["after_each_step"] = "after_each_step"
    enabled: bool = True

    @model_validator(mode="after")
    def portable_requirements(self) -> "AgentDefinition":
        if self.requirements.shared_inference:
            raise ValueError("Submit shared inference through Distributed Jobs")
        data_steps = [s for s in self.workflow.steps if s.kind in ("analytics", "report", "image")]
        if data_steps:
            if len(data_steps) != len(self.workflow.steps) or self.requirements.model_selection:
                raise ValueError("Data workloads cannot mix with text inference steps")
            kinds = [s.kind for s in data_steps]
            if kinds not in (["analytics"], ["analytics", "report"], ["image"]):
                raise ValueError("Supported data workflows: analytics, analytics-report or image")
            required_runtime = IMAGE_RUNTIME if kinds == ["image"] else WORKLOAD_RUNTIME
            required_permission = "images.generate" if kinds == ["image"] else "data.analyze"
            if (
                required_runtime not in self.requirements.runtimes
                or required_permission not in self.permissions
            ):
                raise ValueError("Data workloads require explicit runtime and permission")
            if kinds == ["image"] and self.retry.limit:
                raise ValueError("Image generation does not replay automatically")
        if any(s.kind == "coding" for s in self.workflow.steps) and (
            len(self.workflow.steps) != 1
            or self.retry.limit != 0
            or CODING_RUNTIME not in self.requirements.runtimes
            or "coding.workspace" not in self.permissions
        ):
            raise ValueError("Coding requires one isolated step, explicit permission and no replay")
        if (
            self.requirements.model_selection
            and self.requirements.model_selection.connection_id
            and self.retry.limit
        ):
            raise ValueError("Paid workflows cannot retry automatically")
        if self.requirements.model_selection is None and not data_steps:
            raise ValueError("A model selection is required")
        if (
            self.requirements.model_selection
            and self.requirements.model_selection.connection_id
            and any(s.output_schema in ("plan", "coding") for s in self.workflow.steps)
            and "structured_output" not in self.requirements.model_selection.required_operations
        ):
            self.requirements.model_selection.required_operations.append("structured_output")
        if self.requirements.tools or self.requirements.tool_permissions:
            raise ValueError("Use the agent allowed_tools and permissions fields for tool policy")
        if any(
            step.tool not in self.allowed_tools
            for step in self.workflow.steps
            if step.kind == "tool"
        ):
            raise ValueError("Every workflow tool must be explicitly allowed")
        keys = [(tool.name, tool.version) for tool in self.allowed_tools]
        if len(keys) != len(set(keys)):
            raise ValueError("Allowed tools must be unique")
        if len(self.model_dump_json().encode("utf-8")) > 131072:
            raise ValueError("Agent definitions must fit the 128 KiB portable contract limit")
        return self


class AgentCreate(Contract):
    workspace_id: UUID
    definition: AgentDefinition


class AgentVersionCreate(Contract):
    expected_version: int = Field(ge=1)
    definition: AgentDefinition


class AgentView(Contract):
    id: UUID
    version_id: UUID
    version: int
    owner_id: UUID
    workspace_id: UUID
    enabled: bool
    definition: AgentDefinition


class ArtifactReference(Contract):
    id: UUID
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=1, le=MAX_ARTIFACT_BYTES)
    format_version: Literal[1] = 1


class WorkflowInput(Contract):
    dependency_outputs: list[ArtifactReference] = Field(default_factory=list, max_length=16)
    template_values: dict[
        Annotated[str, Field(max_length=100)],
        Annotated[str, Field(max_length=4096)] | ArtifactReference,
    ] = Field(default_factory=dict, max_length=64)
    instruction: str = Field(min_length=1, max_length=4096)
    repository_id: UUID | None = None
    dataset: Dataset | None = None
    analysis: AnalysisSettings | None = None
    image: ImageSettings | None = None
    report_format: Literal["html", "markdown", "csv", "xlsx"] | None = None
    search_terms: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list, max_length=8
    )

    @model_serializer(mode="wrap")
    def compatible(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.dependency_outputs:
            data.pop("dependency_outputs", None)
        if not self.template_values:
            data.pop("template_values", None)
        if self.repository_id is None:
            data.pop("repository_id", None)
        if not self.search_terms:
            data.pop("search_terms", None)
        for key in ("dataset", "analysis", "image", "report_format"):
            if getattr(self, key) is None:
                data.pop(key, None)
        return data


class WorkflowSubmission(Contract):
    agent_id: UUID
    agent_version: int = Field(ge=1)
    workspace_id: UUID
    input: WorkflowInput
    priority: int = Field(default=0, ge=-100, le=100)
    paid_consent: bool = False


class ModelReference(Contract):
    provider_id: Label
    provider: Literal["ollama", "openai_compatible", "openai", "anthropic"]
    identifier: Label
    digest: str | None = Field(default=None, max_length=200)

    @classmethod
    def from_deployment(cls, model: ModelDeployment) -> "ModelReference":
        return cls(
            provider_id=model.provider_id,
            provider=model.provider,
            identifier=model.identifier,
            digest=model.digest,
        )


class CompletedStep(Contract):
    step_id: Label
    output: ArtifactReference
    attempt_id: UUID
    fencing_token: int = Field(ge=1)
    model: ModelReference | None = None
    tool: ToolReference | None = None

    @field_validator("model", mode="before")
    @classmethod
    def compact_historical_model(cls, value: object) -> object:
        # Read earlier development checkpoints carrying a full validated snapshot.
        if isinstance(value, ModelDeployment):
            return ModelReference.from_deployment(value)
        if isinstance(value, dict) and "operations" in value:
            return ModelReference.from_deployment(ModelDeployment.model_validate(value))
        return value


class WorkflowState(Contract):
    format_version: Literal[1] = 1
    job_id: UUID
    agent_id: UUID
    agent_version: int = Field(ge=1)
    workflow_id: UUID
    workflow_version: int = Field(ge=1)
    attempt_id: UUID
    fencing_token: int = Field(ge=1)
    checkpoint_version: int = Field(default=0, ge=0, le=32)
    current_step: int = Field(default=0, ge=0, le=32)
    completed: list[CompletedStep] = Field(default_factory=list, max_length=32)
    context: dict[Label, ArtifactReference] = Field(default_factory=dict, max_length=32)
    recovery_count: int = Field(default=0, ge=0, le=10)
    resumed_from_attempt_id: UUID | None = None
    last_error_code: Label | None = None

    @model_validator(mode="after")
    def committed_prefix(self) -> "WorkflowState":
        ids = [s.step_id for s in self.completed]
        if (
            len(ids) != len(set(ids))
            or self.current_step != len(ids)
            or self.checkpoint_version != len(ids)
            or set(self.context) != set(ids)
        ):
            raise ValueError("Checkpoint state must describe a contiguous committed prefix")
        if any(self.context[s.step_id] != s.output for s in self.completed):
            raise ValueError("Context must reference the committed step artifacts")
        return self


class WorkflowAssignment(Contract):
    agent: AgentView
    state: WorkflowState


class WorkflowResult(Contract):
    workflow_id: UUID
    workflow_version: int = Field(ge=1)
    agent_id: UUID
    agent_version: int = Field(ge=1)
    checkpoint_version: int = Field(ge=1, le=32)
    completed_steps: list[Label] = Field(min_length=1, max_length=32)
    final_output: ArtifactReference


class WorkflowReport(AttemptIdentity):
    action: Literal["step_start", "checkpoint"]
    step_id: Label
    expected_checkpoint_version: int = Field(ge=0, le=32)
    output: StepOutput | None = None
    usage: InferenceUsage | None = None


class CheckpointView(Contract):
    id: UUID
    version: int
    job_id: UUID
    attempt_id: UUID
    artifact: ArtifactReference
    agent_id: UUID
    agent_version: int
    workflow_id: UUID
    workflow_version: int
    created_at: datetime
