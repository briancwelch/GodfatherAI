"""Read-only, node-scoped activity. Prompts, results and tool output are excluded."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, Field

from godfather_contracts import Contract


class ActivityCursor(Contract):
    at: AwareDatetime
    id: UUID


class ActivityRequest(Contract):
    offset: int = Field(default=0, ge=0, le=1000000)
    limit: int = Field(default=25, ge=1, le=100)
    job_id: UUID | None = None
    cursor: ActivityCursor | None = None


class NodeJob(Contract):
    job_id: UUID
    attempt_id: UUID
    type: str
    workspace: str
    status: str
    job_status: str
    number: int
    shared: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobNotice(Contract):
    id: UUID
    job_id: UUID
    attempt_id: UUID
    type: str
    created_at: datetime


class ActivityResponse(Contract):
    node_id: UUID
    jobs: list[NodeJob] = Field(max_length=100)
    has_more: bool
    events: list[JobNotice] = Field(max_length=100)
    cursor: ActivityCursor
    more_events: bool = False
