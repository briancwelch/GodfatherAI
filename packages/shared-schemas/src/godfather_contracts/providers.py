"""Metadata-only provider policy. API secrets are deliberately not part of this contract."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from godfather_contracts import Contract, Label


class ConnectionCheck(Contract):
    connection_id: UUID
    test_id: UUID


class ConnectionCheckResult(ConnectionCheck):
    session_id: UUID
    code: Literal[
        "ready",
        "provider_auth",
        "provider_unavailable",
        "model_unavailable",
        "rate_limited",
        "provider_timeout",
        "invalid_response",
        "invalid_request",
        "output_limit",
    ]
    models: list[Label] = Field(default_factory=list, max_length=128)


class ModelRate(Contract):
    identifier: Label
    input_microusd_per_million: int = Field(ge=0, le=10**12)
    output_microusd_per_million: int = Field(ge=0, le=10**12)
    source: str = Field(
        pattern=r"^https://(developers\.openai\.com|platform\.openai\.com|openai\.com|platform\.claude\.com|docs\.anthropic\.com|anthropic\.com)/",
        max_length=2048,
    )
    verified_at: datetime


class ConnectionCreate(Contract):
    node_id: UUID
    provider: Literal["openai", "anthropic"]
    name: Label


class ConnectionPolicy(Contract):
    enabled: bool = False
    sharing: Literal["private", "approval_required", "limited"] = "private"
    allowed_user_ids: list[UUID] = Field(default_factory=list, max_length=128)
    allowed_workspace_ids: list[UUID] = Field(default_factory=list, max_length=128)
    default_model: Label | None = None
    rates: list[ModelRate] = Field(default_factory=list, max_length=128)
    lifetime_limit_microusd: int = Field(default=0, ge=0, le=10**15)
    call_limit_microusd: int = Field(default=0, ge=0, le=10**12)

    @model_validator(mode="after")
    def distinct_models(self) -> "ConnectionPolicy":
        if len({r.identifier for r in self.rates}) != len(self.rates):
            raise ValueError("Model prices must be unique")
        if any(r.verified_at.tzinfo is None for r in self.rates):
            raise ValueError("Price verification requires an explicit timezone")
        if self.enabled and (
            not self.rates or not self.call_limit_microusd or not self.lifetime_limit_microusd
        ):
            raise ValueError(
                "Paid connections require verified prices and positive spending safeguards"
            )
        if self.default_model is not None and self.default_model not in {
            r.identifier for r in self.rates
        }:
            raise ValueError("Default model must have an explicitly configured price")
        return self


class ProviderGrant(Contract):
    user_id: UUID
    workspace_id: UUID
    model: Label
    job_id: UUID | None = None
    expires_at: datetime
    limit_microusd: int = Field(gt=0, le=10**12)


class InvocationRequest(Contract):
    session_id: UUID
    attempt_id: UUID
    fencing_token: int = Field(ge=1)
    # One call per text attempt initially. No automatic paid retries.
    call_key: Label = "text"
    input_bytes: int = Field(default=0, ge=0, le=131072)
    max_output_tokens: int = Field(default=512, ge=1, le=8192)


class InvocationSettlement(InvocationRequest):
    invocation_id: UUID
    input_tokens: int | None = Field(default=None, ge=0, le=2**40)
    output_tokens: int | None = Field(default=None, ge=0, le=2**40)
    pricing_supported: bool = True


def estimated_cost(rate: ModelRate, input_tokens: int, output_tokens: int) -> int:
    """Integer micro-USD, rounded upward; this is not provider-confirmed billing."""
    units = input_tokens * rate.input_microusd_per_million
    units += output_tokens * rate.output_microusd_per_million
    return (units + 999_999) // 1_000_000
