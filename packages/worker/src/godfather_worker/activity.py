"""Bounded owner-local notification history; coordinator job records stay authoritative."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from godfather_contracts import Contract
from godfather_contracts.shared_engine import EngineGroup
from godfather_contracts.worker_activity import ActivityCursor, JobNotice
from pydantic import Field

JOB_LABELS = {
    "job.assigned": "Job assigned",
    "job.started": "Job started",
    "job.completed": "Job completed",
    "job.cancelled": "Job cancelled",
    "job.cancellation_requested": "Job cancellation requested",
    "job.attempt_failed": "Job attempt failed",
    "job.lease_expired": "Job interrupted: connection lease expired",
    "job.timeout": "Job timed out",
    "job.permission_lost": "Job stopped: permission changed",
}


class Notice(Contract):
    id: UUID = Field(default_factory=uuid4)
    key: str = Field(max_length=200)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    title: str = Field(max_length=200)
    message: str = Field(max_length=1000)
    target: Literal["jobs", "shared"]
    reference: UUID
    read: bool = False


class Inbox(Contract):
    notices: list[Notice] = Field(default_factory=list, max_length=200)
    seen: list[str] = Field(default_factory=list, max_length=1000)
    shared_states: dict[str, str] = Field(default_factory=dict)
    cursor: ActivityCursor | None = None

    def add(self, notice: Notice) -> None:
        if notice.key in self.seen:
            return
        self.notices = [notice, *self.notices][:200]
        self.seen = [*self.seen, notice.key][-1000:]

    def job_event(self, event: JobNotice) -> None:
        title = JOB_LABELS.get(event.type)
        if title:
            self.add(
                Notice(
                    key=str(event.id),
                    at=event.created_at,
                    title=title,
                    message=f"Job {str(event.job_id)[:8]} on this computer. "
                    "Open Jobs for its status.",
                    target="jobs",
                    reference=event.job_id,
                )
            )

    def shared_groups(self, node_id: UUID, groups: list[EngineGroup]) -> int:
        attention = 0
        current = {}
        for group in groups:
            own = next((m for m in group.members if m.node_id == node_id), None)
            if own is None:
                continue
            title, message = "", ""
            state = "waiting"
            if not own.approved and own.phase != "stopped":
                state = "approval"
                attention += 1
                title = "Shared Inference: approve and join"
                message = (
                    "Choose your backend, detect and select devices, select this computer's "
                    "private address, then click Approve this computer."
                )
            elif any(m.phase == "error" for m in group.members):
                state = "error"
                title, message = (
                    "Shared Inference failed",
                    "Review the setup and local engine error.",
                )
            elif group.desired_running:
                state = "ready" if all(m.phase == "ready" for m in group.members) else "starting"
                title = (
                    "Shared Inference ready" if state == "ready" else "Shared Inference starting"
                )
                message = (
                    "The engine is ready. Open Distributed Jobs in Command Center to submit work."
                    if state == "ready"
                    else "Approved computers are starting their engines."
                )
            elif group.group and all(m.phase == "waiting" for m in group.members):
                if node_id == group.proposal.leader_node_id:
                    state = "start"
                    attention += 1
                    title = "Shared Inference: ready to start"
                    message = "All owners approved. Click Configure and Start on this computer."
                else:
                    state = "joined"
                    title = "Shared Inference: joined, waiting for start"
                    message = (
                        "All owners approved. The initiating computer must click "
                        "Configure and Start."
                    )
            elif own.phase == "stopped":
                state = "stopped"
                title, message = "Shared Inference stopped", "This setup's engine is stopped."
            key = str(group.proposal.id)
            current[key] = f"{group.generation}:{state}"
            previous = self.shared_states.get(key)
            # Existing stopped setups do not need an announcement on first launch.
            if title and current[key] != previous and (state != "stopped" or previous):
                self.add(
                    Notice(
                        key=f"{key}:{current[key]}:{uuid4().hex}",
                        title=title,
                        message=f'"{group.proposal.name}": {message}',
                        target="shared",
                        reference=group.proposal.id,
                    )
                )
        self.shared_states = current
        return attention


def inbox_path(folder: Path, identity: dict[str, str]) -> Path:
    scope = identity.get("origin", "") + "\n" + identity["credential_id"]
    return folder / "activity" / (hashlib.sha256(scope.encode()).hexdigest() + ".json")


def load_inbox(path: Path) -> Inbox:
    try:
        if path.stat().st_size > 1024**2:
            return Inbox()
        return Inbox.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Inbox()


def save_inbox(path: Path, inbox: Inbox) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(inbox.model_dump_json(), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
