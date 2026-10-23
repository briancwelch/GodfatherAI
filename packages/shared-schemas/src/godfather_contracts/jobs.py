"""Additive synthetic execution protocol v1; registration/heartbeat v1 stays valid."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from godfather_contracts import Contract, ModelDeployment
from godfather_contracts.agents import WorkflowAssignment, WorkflowInput, WorkflowResult
from godfather_contracts.execution import AttemptIdentity
from godfather_contracts.execution import JobPoll as JobPoll
from godfather_contracts.execution import Requirements as Requirements
from godfather_contracts.execution import RetryPolicy as RetryPolicy
from godfather_contracts.inference import (
    InferenceInput,
    InferenceResult,
    ProviderErrorCode,
    StreamUpdate,
)
from godfather_contracts.model_management import ModelInstallInput, ModelInstallResult
from godfather_contracts.providers import ConnectionCheck
from godfather_contracts.result_actions import ResultActionInput, ResultActionOutput

JobState = Literal[
    "PENDING", "ASSIGNED", "RUNNING", "RETRY_WAIT", "COMPLETED", "FAILED", "CANCELLED"
]
ErrorCode = Literal[
    "transient_error", "permanent_error", "lease_expired", "timeout", "permission_lost"
]


class SyntheticInput(Contract):
    value: str = Field(default="synthetic", max_length=1000)
    steps: int = Field(default=3, ge=1, le=100)
    fail_until_attempt: int = Field(default=0, ge=0, le=11)
    permanent: bool = False


class JobSubmission(Contract):
    workspace_id: UUID
    type: Literal["synthetic.echo", "synthetic.fail", "inference.text"] = "synthetic.echo"
    requirements: Requirements = Field(default_factory=Requirements)
    input: SyntheticInput | InferenceInput = Field(default_factory=SyntheticInput)
    priority: int = Field(default=0, ge=-100, le=100)
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)

    @model_validator(mode="after")
    def execution_contract(self) -> "JobSubmission":
        if self.requirements.shared_inference and (
            self.type != "inference.text" or self.retry.limit
        ):
            raise ValueError("Shared inference uses one non-replaying inference attempt")
        if self.type == "inference.text":
            if (
                not isinstance(self.input, InferenceInput)
                or self.requirements.model_selection is None
            ):
                raise ValueError("Inference input and model selection are required")
            if self.input.stream != self.requirements.model_selection.stream:
                raise ValueError("Input and model selection stream modes must agree")
            operations = self.requirements.model_selection.required_operations
            if self.input.tools and "tools" not in operations:
                operations.append("tools")
            if self.input.output_schema and "structured_output" not in operations:
                operations.append("structured_output")
        elif not isinstance(self.input, SyntheticInput) or self.requirements.model_selection:
            raise ValueError("Synthetic jobs require synthetic input without model selection")
        return self


class InferenceSubmission(JobSubmission):
    type: Literal["inference.text"] = "inference.text"
    input: InferenceInput


class SyntheticResult(Contract):
    value: str = Field(max_length=1000)
    steps: int = Field(ge=1, le=100)


class JobView(Contract):
    id: UUID
    owner_id: UUID
    workspace_id: UUID
    type: str
    status: JobState
    priority: int
    requirements: Requirements
    input: SyntheticInput | InferenceInput | WorkflowInput | ModelInstallInput | ResultActionInput
    timeout_seconds: int
    retry: RetryPolicy
    assigned_node_id: UUID | None
    current_attempt_id: UUID | None
    attempt_count: int
    fencing_token: int
    checkpoint_ref: str | None
    cancel_requested_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    result: (
        SyntheticResult
        | InferenceResult
        | WorkflowResult
        | ModelInstallResult
        | ResultActionOutput
        | None
    )


class Assignment(Contract):
    job: JobView
    attempt_id: UUID
    fencing_token: int
    lease_expires_at: datetime
    deadline_at: datetime
    deployment: ModelDeployment | None = None
    workflow: WorkflowAssignment | None = None

    @model_serializer(mode="wrap")
    def compatible_assignment(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.deployment is None:
            data.pop("deployment", None)
        if self.workflow is None:
            data.pop("workflow", None)
        return data


class PollResponse(Contract):
    assignment: Assignment | None = None
    provider_checks: list[ConnectionCheck] = Field(default_factory=list, max_length=8)

    @model_serializer(mode="wrap")
    def compatible(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.provider_checks:
            data.pop("provider_checks", None)
        return data


class JobReport(AttemptIdentity):
    action: Literal["ack", "start", "progress", "renew", "complete", "fail", "cancelled", "output"]
    progress: int | None = Field(default=None, ge=0, le=100)
    result: (
        SyntheticResult
        | InferenceResult
        | WorkflowResult
        | ModelInstallResult
        | ResultActionOutput
        | None
    ) = None
    output: StreamUpdate | None = None
    error_code: (
        Literal[
            "transient_error",
            "permanent_error",
            "workflow_validation",
            "tool_permission",
            "artifact_unavailable",
            "step_timeout",
        ]
        | ProviderErrorCode
        | None
    ) = None


class ReportResponse(Contract):
    status: JobState
    cancel_requested: bool
    lease_expires_at: datetime


class AttemptView(Contract):
    id: UUID
    created_at: datetime
    node_id: UUID
    number: int
    fencing_token: int
    status: str
    lease_expires_at: datetime
    acknowledged_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    error: dict[str, object]
    recovered_from_attempt_id: UUID | None = None
    resumed_checkpoint_version: int = 0


class EventView(Contract):
    id: UUID
    type: str
    created_at: datetime
    correlation_id: str | None
    node_id: UUID | None
    attempt_id: UUID | None
    details: dict[str, object]
