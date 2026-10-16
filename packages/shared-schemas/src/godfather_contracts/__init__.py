"""Worker registration/health v1. The additive execution contract lives in jobs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class Advertisement(Contract):
    os: Literal["windows", "macos", "linux"]
    os_version: str = Field(min_length=1, max_length=100)
    architecture: Literal["x86_64", "arm64", "x86", "unknown"]
    resources: Resources
    primary_capabilities: list[Label] = Field(default_factory=list, max_length=32)
    secondary_capabilities: list[Label] = Field(default_factory=list, max_length=32)
    scheduling_policy: Literal["dedicated", "preferred", "shared"] = "shared"
    concurrency_limit: int = Field(default=1, ge=1, le=128)
    job_protocol_version: Literal[1] | None = None
    allowed_job_owner_ids: list[UUID] = Field(default_factory=list, max_length=128)
    allowed_workspace_ids: list[UUID] = Field(default_factory=list, max_length=128)
    runtimes: list[Label] = Field(default_factory=list, max_length=32)
    installed_models: list[ModelInventory] = Field(default_factory=list, max_length=128)
    dependencies: list[Label] = Field(default_factory=list, max_length=32)
    toolchains: list[Label] = Field(default_factory=list, max_length=32)
    sandbox_modes: list[Label] = Field(default_factory=list, max_length=16)
    discovery_warnings: list[Label] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def distinct_capabilities(self) -> "Advertisement":
        combined = self.primary_capabilities + self.secondary_capabilities
        if len(combined) != len(set(combined)):
            raise ValueError("capabilities must be unique across specialties")
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
    node_id: UUID
    owner_id: UUID
    name: str
    protocol_version: int
    state: NodeState
    connection_status: Connection
    last_heartbeat_at: datetime | None


class NodeControl(Contract):
    action: Literal["drain", "disable", "enable", "revoke"]
