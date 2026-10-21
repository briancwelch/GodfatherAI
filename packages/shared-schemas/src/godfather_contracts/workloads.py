"""Versioned, bounded data contracts for deterministic worker workloads."""

import base64
import binascii
import hashlib
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from godfather_contracts import Contract

WORKLOAD_RUNTIME = "data-workloads-v1"
IMAGE_RUNTIME = "local-images-v1"
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


class Dataset(Contract):
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,119}\.(csv|json|xlsx)$")
    content_base64: str = Field(min_length=4, max_length=1400000)

    @field_validator("content_base64")
    @classmethod
    def bounded_file(cls, value: str) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Dataset must be base64 encoded") from None
        if not 0 < len(raw) <= 1024 * 1024:
            raise ValueError("Dataset limit is 1 MiB")
        return value


class AnalysisSettings(Contract):
    group_by: str | None = Field(default=None, max_length=120)
    date_column: str | None = Field(default=None, max_length=120)
    value_column: str | None = Field(default=None, max_length=120)


class ImageSettings(Contract):
    backend: Literal["automatic1111"] = "automatic1111"
    model: str = Field(min_length=1, max_length=200)
    width: int = Field(default=512, ge=256, le=1024, multiple_of=64)
    height: int = Field(default=512, ge=256, le=1024, multiple_of=64)
    count: int = Field(default=1, ge=1, le=4)
    steps: int = Field(default=20, ge=1, le=50)
    seed: int = Field(default=-1, ge=-1, le=2**32 - 1)


class Download(Contract):
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")
    media_type: Literal[
        "text/html",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/png",
    ]
    content_base64: str = Field(min_length=4, max_length=7000000)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def integrity(self) -> "Download":
        try:
            raw = base64.b64decode(self.content_base64, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid file encoding") from None
        if hashlib.sha256(raw).hexdigest() != self.checksum:
            raise ValueError("Download checksum mismatch")
        if self.media_type == "image/png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Only PNG image artifacts are supported")
        return self


class Metric(Contract):
    count: int = Field(ge=1, le=10000)
    missing: int = Field(ge=0, le=10000)
    sum: float = Field(allow_inf_nan=False)
    mean: float = Field(allow_inf_nan=False)
    median: float = Field(allow_inf_nan=False)
    min: float = Field(allow_inf_nan=False)
    max: float = Field(allow_inf_nan=False)
    sample_stddev: float = Field(ge=0, allow_inf_nan=False)
    anomaly_count: int = Field(ge=0, le=10000)
    anomaly_rows: list[Annotated[int, Field(ge=1, le=10000)]] = Field(max_length=100)


class Aggregate(Contract):
    label: str = Field(max_length=4096)
    count: int = Field(ge=0, le=10000)
    value: float = Field(allow_inf_nan=False)
    change: float | None = Field(default=None, allow_inf_nan=False)
    change_percent: float | None = Field(default=None, allow_inf_nan=False)


class AnalysisResult(Contract):
    schema_version: Literal[1] = 1
    source: str = Field(min_length=1, max_length=200)
    source_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    row_count: int = Field(ge=1, le=10000)
    columns: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        min_length=1, max_length=64
    )
    metrics: dict[str, Metric] = Field(max_length=64)
    groups: list[Aggregate] = Field(max_length=100)
    periods: list[Aggregate] = Field(max_length=100)
    group_by: str | None = Field(default=None, max_length=120)
    value_column: str | None = Field(default=None, max_length=120)
    date_column: str | None = Field(default=None, max_length=120)


class WorkloadOutput(Contract):
    format_version: Literal[1] = 1
    kind: Literal["analytics", "report", "image"]
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=24000)
    # Pure JSON from a fixed worker program, never executable code.
    analysis: dict[str, object] = Field(default_factory=dict, max_length=24)
    files: list[Download] = Field(default_factory=list, max_length=8)
    limitations: list[Annotated[str, Field(max_length=1000)]] = Field(
        default_factory=list, max_length=16
    )

    @model_validator(mode="after")
    def bounded_output(self) -> "WorkloadOutput":
        if self.kind in ("analytics", "report"):
            AnalysisResult.model_validate(self.analysis)
        if len(self.model_dump_json().encode()) > MAX_ARTIFACT_BYTES - 1024:
            raise ValueError("Output artifact exceeds 8 MiB")
        return self
