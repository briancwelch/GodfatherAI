"""Worker registration/health v1. The additive execution contract lives in jobs."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

PROTOCOL_VERSION = 1
Label = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/ -]*$")
]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
Nonnegative = Annotated[int, Field(ge=0)]
Connection = Literal["online", "suspect", "offline"]
NodeState = Literal["online", "suspect", "offline", "draining", "disabled"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class GPU(Contract):
    name: str = Field(min_length=1, max_length=100)
    backend: Literal["cuda", "metal", "rocm", "unknown"] = "unknown"
    # Detected hardware/driver support is not proof of working inference.
    evidence: Literal["driver", "reported", "simulated"] = "reported"
    memory_bytes: Nonnegative | None = None
    memory_used_bytes: Nonnegative | None = None
    utilization_percent: Percent | None = None
    unified_memory: bool = False


class Resources(Contract):
    source: Literal["physical", "simulated"]
    cpu_name: str = Field(max_length=200)
    cpu_count: int = Field(ge=1, le=65536)
    ram_bytes: Nonnegative | None = None
    available_ram_bytes: Nonnegative | None = None
    cpu_percent: Percent | None = None
    gpus: list[GPU] = Field(default_factory=list, max_length=32)


class ModelInventory(Contract):
    runtime: Label
    identifier: Label


class ToolReference(Contract):
    name: Label
    version: int = Field(default=1, ge=1, le=100000)


class ModelDeployment(Contract):
    """Worker-local provider alias, never an endpoint URL or credential."""

    provider_id: Label
    provider: Literal["ollama", "openai_compatible", "openai", "anthropic"]
    connection_id: UUID | None = None
    identifier: Label
    available: bool = True
    verified_capabilities: list[Label] = Field(default_factory=list, max_length=32)
    declared_capabilities: list[Label] = Field(default_factory=list, max_length=32)
    operations: list[Literal["chat", "stream", "tools", "structured_output"]] = Field(
        default_factory=list, max_length=4
    )
    context_window: int | None = Field(default=None, ge=1, le=2**40)
    digest: str | None = Field(default=None, max_length=200)
    disk_bytes: int | None = Field(default=None, ge=0, le=2**60)
    estimated_ram_bytes: int | None = Field(default=None, ge=0, le=2**60)
    estimated_vram_bytes: int | None = Field(default=None, ge=0, le=2**60)
    metadata_source: Literal["provider_reported", "configured"] = "provider_reported"

    @model_serializer(mode="wrap")
    def compatible(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.connection_id is None:
            data.pop("connection_id", None)
        return data


class ModelSelection(Contract):
    # A missing identifier explicitly selects by capability; no implicit fallback.
    identifier: Label | None = None
    provider: Literal["ollama", "openai_compatible", "openai", "anthropic"] | None = None
    connection_id: UUID | None = None
    paid_consent: bool = False
    grant_id: UUID | None = None
    fallback_models: list[Label] = Field(default_factory=list, max_length=8)
    required_operations: list[Literal["tools", "structured_output"]] = Field(
        default_factory=list, max_length=2
    )
    capabilities: list[Label] = Field(default_factory=list, max_length=32)
    allow_declared_capabilities: bool = False
    context_window: int | None = Field(default=None, ge=1, le=2**40)
    stream: bool = True

    @model_validator(mode="after")
    def explicit_selection(self) -> "ModelSelection":
        if self.identifier is None and not self.capabilities:
            raise ValueError("Select an exact model or required capabilities")
        if self.provider in ("openai", "anthropic") and (
            not self.connection_id or not self.identifier or not self.paid_consent
        ):
            raise ValueError(
                "Native API inference requires an exact connection, model and paid consent"
            )
        if self.connection_id and self.provider not in ("openai", "anthropic"):
            raise ValueError("Provider connections belong to explicit native API routes")
        if self.fallback_models and (
            self.provider != "ollama" or self.connection_id is not None or self.identifier is None
        ):
            raise ValueError("Only explicit local Ollama fallback models are enabled")
        return self

    @model_serializer(mode="wrap")
    def compatible(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for name in (
            "connection_id",
            "paid_consent",
            "grant_id",
            "fallback_models",
            "required_operations",
        ):
            if not getattr(self, name):
                data.pop(name, None)
        return data


class RepositoryReference(Contract):
    id: UUID
    name: Label
    allowed_user_ids: list[UUID] = Field(max_length=128)
    allowed_workspace_ids: list[UUID] = Field(max_length=128)


class Advertisement(Contract):
    worker_version: str | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$",
    )
    os: Literal["windows", "macos", "linux"]
    os_version: str = Field(min_length=1, max_length=100)
    architecture: Literal["x86_64", "arm64", "x86", "unknown"]
    resources: Resources
    primary_capabilities: list[Label] = Field(default_factory=list, max_length=32)
    secondary_capabilities: list[Label] = Field(default_factory=list, max_length=32)
    scheduling_policy: Literal["dedicated", "preferred", "shared"] = "shared"
    concurrency_limit: int = Field(default=1, ge=1, le=128)
    job_protocol_version: Literal[1] | None = None
    inference_protocol_version: Literal[1] | None = None
    workflow_protocol_version: Literal[1] | None = None
    worker_tools: list[ToolReference] = Field(default_factory=list, max_length=16)
    tool_permissions: list[Label] = Field(default_factory=list, max_length=16)
    model_deployments: list[ModelDeployment] = Field(default_factory=list, max_length=128)
    allowed_job_owner_ids: list[UUID] = Field(default_factory=list, max_length=128)
    allowed_workspace_ids: list[UUID] = Field(default_factory=list, max_length=128)
    share_with_workspaces: bool = False
    runtimes: list[Label] = Field(default_factory=list, max_length=32)
    installed_models: list[ModelInventory] = Field(default_factory=list, max_length=128)
    dependencies: list[Label] = Field(default_factory=list, max_length=32)
    toolchains: list[Label] = Field(default_factory=list, max_length=32)
    sandbox_modes: list[Label] = Field(default_factory=list, max_length=16)
    discovery_warnings: list[Label] = Field(default_factory=list, max_length=32)
    coding_repositories: list[RepositoryReference] = Field(default_factory=list, max_length=8)

    @model_serializer(mode="wrap")
    def compatible(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.worker_version is None:
            data.pop("worker_version", None)
        if not self.coding_repositories:
            data.pop("coding_repositories", None)
        if not self.share_with_workspaces:
            data.pop("share_with_workspaces", None)
        return data

    @model_validator(mode="after")
    def distinct_capabilities(self) -> "Advertisement":
        combined = self.primary_capabilities + self.secondary_capabilities
        if len(combined) != len(set(combined)):
            raise ValueError("capabilities must be unique across specialties")
        deployments = [(m.provider_id, m.identifier) for m in self.model_deployments]
        if len(deployments) != len(set(deployments)):
            raise ValueError("model deployments must be unique within a provider alias")
        return self


class Registration(Advertisement):
    protocol_version: int = Field(default=PROTOCOL_VERSION, ge=1)
    session_id: UUID


class Heartbeat(Contract):
    protocol_version: int = Field(default=PROTOCOL_VERSION, ge=1)
    session_id: UUID
    resources: Resources


class WorkerAck(Contract):
    node_id: UUID
    state: NodeState
    connection_status: Connection
    heartbeat_interval_seconds: int = Field(ge=1, le=300)


class NodeView(Advertisement):
    owner_name: str | None = None
    owner_picture: str | None = None
    owner_location: str | None = None
    node_id: UUID
    owner_id: UUID
    name: str
    protocol_version: int
    state: NodeState
    connection_status: Connection
    last_heartbeat_at: datetime | None


class NodeControl(Contract):
    action: Literal["drain", "disable", "enable", "revoke"]
