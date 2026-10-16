"""Opt-in synthetic execution only: bounded data transformations, no host tools."""

import threading
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from godfather_contracts import Heartbeat, Registration
from godfather_contracts.jobs import (
    Assignment,
    JobReport,
    ReportResponse,
    SyntheticInput,
    SyntheticResult,
)

from godfather_worker.client import WorkerClient


def synthetic_result(payload: SyntheticInput, attempt: int, job_type: str) -> SyntheticResult | str:
    if job_type == "synthetic.fail" or attempt <= payload.fail_until_attempt:
        return "permanent_error" if payload.permanent else "transient_error"
    if job_type != "synthetic.echo":
        return "permanent_error"
    return SyntheticResult(value=payload.value, steps=payload.steps)


def execute(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
    stop: threading.Event,
    step_seconds: float,
    heartbeat_seconds: int,
) -> None:
    """Discard the assignment on transport failure; the lease decides safe retry.

    Periodic renewals and heartbeats continue during deliberate synthetic delays.
    No local progress is advertised as a recoverable checkpoint.
    """
    route = f"/api/v1/workers/{node_id}/jobs/{assignment.job.id}/report"

    def report(action: str, **values: object) -> ReportResponse:
        payload = JobReport.model_validate(
            {
                "session_id": registration.session_id,
                "attempt_id": assignment.attempt_id,
                "fencing_token": assignment.fencing_token,
                "action": action,
                **values,
            }
        )
        return ReportResponse.model_validate(client.post_document(route, payload))

    acknowledged = report("ack")
    if acknowledged.status == "CANCELLED":
        return
    started = report("start")
    if started.status == "CANCELLED":
        return
    lease_seconds = max(0.1, (assignment.lease_expires_at - datetime.now(UTC)).total_seconds() / 3)
    next_renew, next_heartbeat = monotonic(), monotonic()
    for step in range(assignment.job.input.steps):
        deadline = monotonic() + step_seconds
        while True:
            now = monotonic()
            if now >= next_heartbeat:
                client.post(
                    f"/api/v1/workers/{node_id}/heartbeat",
                    Heartbeat(session_id=registration.session_id, resources=registration.resources),
                )
                next_heartbeat = now + heartbeat_seconds
            if now >= next_renew:
                if report("renew").cancel_requested:
                    report("cancelled")
                    return
                next_renew = now + lease_seconds
            if stop.is_set():
                return
            if now >= deadline:
                break
            stop.wait(min(0.1, deadline - now))
        if report(
            "progress", progress=(step + 1) * 100 // assignment.job.input.steps
        ).cancel_requested:
            report("cancelled")
            return
    result = synthetic_result(
        assignment.job.input, assignment.job.attempt_count, assignment.job.type
    )
    if isinstance(result, str):
        report("fail", error_code=result)
    else:
        report("complete", result=result.model_dump(mode="json"))
