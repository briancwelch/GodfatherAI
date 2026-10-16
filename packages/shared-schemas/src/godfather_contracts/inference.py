"""Bounded portable text inference contract v1, independent of provider APIs."""

from typing import Literal

from pydantic import Field

from godfather_contracts import Contract, ModelDeployment

MAX_TEXT = 32768
MAX_UPDATES = 512
ProviderErrorCode = Literal[
    "provider_unavailable",
    "model_unavailable",
    "provider_auth",
    "rate_limited",
    "provider_timeout",
    "invalid_response",
    "invalid_request",
    "output_limit",
]


class InferenceParameters(Contract):
    temperature: float = Field(default=0.7, ge=0, le=2, allow_inf_nan=False)
    top_p: float = Field(default=1, gt=0, le=1, allow_inf_nan=False)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class InferenceInput(Contract):
    prompt: str = Field(min_length=1, max_length=MAX_TEXT)
    system: str | None = Field(default=None, max_length=8192)
    stream: bool = True
    parameters: InferenceParameters = Field(default_factory=InferenceParameters)


class InferenceUsage(Contract):
    input_tokens: int | None = Field(default=None, ge=0, le=2**40)
    output_tokens: int | None = Field(default=None, ge=0, le=2**40)
    token_source: Literal["provider_reported", "unavailable"] = "unavailable"
    duration_seconds: float = Field(ge=0, le=86400, allow_inf_nan=False)
    first_token_seconds: float | None = Field(default=None, ge=0, le=86400, allow_inf_nan=False)
    tokens_per_second: float | None = Field(default=None, ge=0, le=2**40, allow_inf_nan=False)
    rate_source: Literal["provider_reported", "worker_estimate", "unavailable"] = "unavailable"
    timing_source: Literal["worker_measured"] = "worker_measured"


class InferenceResult(Contract):
    text: str = Field(max_length=MAX_TEXT)
    deployment: ModelDeployment
    usage: InferenceUsage
    finish_reason: Literal["stop", "length", "other"] = "stop"


class StreamUpdate(Contract):
    sequence: int = Field(ge=1, le=MAX_UPDATES)
    # Append-only, bounded batches rather than unlimited token/event rows.
    text: str = Field(min_length=1, max_length=4096)
