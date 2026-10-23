"""Shared execution requirements and fenced identities; no handler dependencies."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from godfather_contracts import (
    Contract,
    Label,
    ModelInventory,
    ModelSelection,
    SharedInferenceGroup,
    ToolReference,
)


class Requirements(Contract):
    capabilities: list[Label] = Field(default_factory=list, max_length=32)
    os: Literal["any", "windows", "macos", "linux"] = "any"
    architecture: Literal["any", "x86_64", "arm64", "x86"] = "any"
    cpu_count: int = Field(default=1, ge=1, le=65536)
    ram_bytes: int = Field(default=0, ge=0, le=2**60)
    gpu_memory_bytes: int = Field(default=0, ge=0, le=2**60)
    backend: Literal["any", "cpu", "cuda", "metal", "rocm"] = "any"
    runtimes: list[Label] = Field(default_factory=list, max_length=32)
    dependencies: list[Label] = Field(default_factory=list, max_length=32)
    toolchains: list[Label] = Field(default_factory=list, max_length=32)
    sandbox_modes: list[Label] = Field(default_factory=list, max_length=16)
    models: list[ModelInventory] = Field(default_factory=list, max_length=32)
    model_selection: ModelSelection | None = None
    shared_inference: SharedInferenceGroup | None = None
    wide_area_consent: bool = False
    tools: list[ToolReference] = Field(default_factory=list, max_length=16)
    tool_permissions: list[Label] = Field(default_factory=list, max_length=16)

    @model_serializer(mode="wrap")
    def compatible_requirements(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for field in (
            "model_selection",
            "tools",
            "tool_permissions",
            "shared_inference",
            "wide_area_consent",
        ):
            if not getattr(self, field):
                data.pop(field, None)
        return data


class RetryPolicy(Contract):
    limit: int = Field(default=0, ge=0, le=10)
    backoff_seconds: int = Field(default=1, ge=0, le=3600)


class JobPoll(Contract):
    job_protocol_version: int = Field(default=1, ge=1)
    session_id: UUID


class AttemptIdentity(JobPoll):
    attempt_id: UUID
    fencing_token: int = Field(ge=1)
