"""Authenticated model directory, inference results, and attempt-aware SSE snapshots."""

import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from godfather_contracts.jobs import InferenceSubmission, JobView
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from godfather_api.jobs import authorized_job, current_attempt, submit
from godfather_api.models import AccessCredential, Attempt, Job, Node, User
from godfather_api.nodes import SessionDep, authenticate, connection_at, node_view
from godfather_api.scheduler import permitted, workspace_access

router = APIRouter(prefix="/api/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])


def workspace_permission(session: Session, workspace_id: UUID, actor_id: UUID) -> None:
    if not workspace_access(session, actor_id, workspace_id):
        raise HTTPException(404, "Workspace not found or permission denied")


@router.get("/models")
def models(
    workspace_id: UUID,
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    node_id: UUID | None = None,
) -> list[dict[str, object]]:
    actor = authenticate(request, session, "admin")
    workspace_permission(session, workspace_id, actor.owner_id)
    probe = Job(owner_id=actor.owner_id, workspace_id=workspace_id)
    query = (
        select(Node)
        .join(AccessCredential, AccessCredential.node_id == Node.id)
        .join(User, User.id == Node.owner_id)
        .where(
            AccessCredential.revoked.is_(False),
            AccessCredential.kind == "worker",
            User.enabled.is_(True),
        )
        .order_by(Node.id)
    )
    if node_id is not None:
        query = query.where(Node.id == node_id)
    result: list[dict[str, object]] = []
    now = datetime.now(UTC)
    for node in session.scalars(query):
        if not permitted(session, probe, node):
            continue
        view = node_view(session, node)
        healthy = (
            node.state == "online"
            and connection_at(node.last_heartbeat_at, now, request.app.state.settings) == "online"
        )
        for deployment in view.model_deployments:
            result.append(
                {
                    "node_id": str(node.id),
                    "owner_id": str(node.owner_id),
                    "state": node.state,
                    "available": healthy
                    and deployment.available
                    and view.inference_protocol_version == 1,
                    "deployment": deployment.model_dump(mode="json"),
                }
            )
    return result[offset : offset + limit]


@router.get("/models/deployments/{node_id}")
def deployments(
    node_id: UUID,
    workspace_id: UUID,
    request: Request,
    session: SessionDep,
) -> list[dict[str, object]]:
    result = models(workspace_id, request, session, 200, 0, node_id)
    if not result:
        raise HTTPException(404, "No deployments in an authorized workspace")
    return result


@router.post("/inference/jobs", response_model=JobView, status_code=201)
def submit_inference(
    payload: InferenceSubmission, request: Request, session: SessionDep
) -> JobView:
    return submit(payload, request, session)


def inference_job(session: Session, job_id: UUID, actor_id: UUID) -> Job:
    job = authorized_job(session, job_id, actor_id)
    if job.type != "inference.text":
        raise HTTPException(404, "Inference job not found")
    return job


def snapshot(session: Session, job: Job) -> dict[str, object]:
    attempt = current_attempt(session, job)
    now = datetime.now(UTC)
    valid = attempt is not None and (
        job.status == "COMPLETED"
        or (
            job.status == "RUNNING"
            and job.cancel_requested_at is None
            and attempt.lease_expires_at > now
            and attempt.deadline_at is not None
            and attempt.deadline_at > now
        )
    )
    data = attempt.result if valid and attempt else {}
    return {
        "job_id": str(job.id),
        "attempt_id": str(attempt.id) if attempt else None,
        "fencing_token": job.fencing_token,
        "status": job.status,
        "valid": valid,
        "sequence": data.get("sequence", 0),
        "text": data.get("text", ""),
        "result": job.result_refs if job.status == "COMPLETED" else None,
        "error": attempt.error if attempt else None,
        "metadata": {
            "node_id": str(attempt.node_id) if attempt else None,
            "deployment": attempt.result.get("deployment") if attempt else None,
            "usage": attempt.result.get("usage") if attempt else None,
            "queue_wait_seconds": max(0, (attempt.created_at - job.created_at).total_seconds())
            if attempt
            else None,
        },
    }


@router.get("/inference/jobs/{job_id}/result")
def result(job_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "admin")
    return snapshot(session, inference_job(session, job_id, actor.owner_id))


@router.get("/inference/jobs/{job_id}/stream")
def stream(job_id: UUID, request: Request, session: SessionDep) -> StreamingResponse:
    actor = authenticate(request, session, "admin")
    inference_job(session, job_id, actor.owner_id)

    async def events() -> AsyncIterator[str]:
        # Never hold a credential lock, SQL transaction or connection while waiting.
        previous: dict[str, object] | None = None
        generation: object = None
        for _ in range(60):  # A bounded 30-second subscription; reconnect for a fresh snapshot.
            if await request.is_disconnected():
                return

            def read() -> dict[str, object]:
                with request.app.state.database.sessions.begin() as fresh:
                    current_actor = authenticate(request, fresh, "admin")
                    return snapshot(fresh, inference_job(fresh, job_id, current_actor.owner_id))

            try:
                data = await asyncio.to_thread(read)
            except HTTPException:
                yield "event: revoked\ndata: {}\n\n"
                return
            if data["attempt_id"] != generation:
                generation = data["attempt_id"]
                yield (
                    "event: reset\ndata: "
                    + json.dumps(
                        {
                            "job_id": str(job_id),
                            "attempt_id": generation,
                            "fencing_token": data["fencing_token"],
                            "text": "",
                        }
                    )
                    + "\n\n"
                )
            if data != previous:
                event = "snapshot" if data["valid"] else "invalidated"
                event_id = f"{data['attempt_id']}:{data['sequence']}:{data['status']}"
                yield f"id: {event_id}\nevent: {event}\ndata: {json.dumps(data)}\n\n"
                previous = data
            if data["status"] in ("COMPLETED", "FAILED", "CANCELLED", "RETRY_WAIT"):
                return
            if data["status"] == "RUNNING" and not data["valid"]:
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/inference/metrics")
def metrics(workspace_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "admin")
    workspace_permission(session, workspace_id, actor.owner_id)
    states: Counter[str] = Counter(
        {
            state: count
            for state, count in session.execute(
                select(Job.status, func.count())
                .where(Job.workspace_id == workspace_id, Job.type == "inference.text")
                .group_by(Job.status)
            ).all()
        }
    )
    terminal = sum(states[s] for s in ("COMPLETED", "FAILED", "CANCELLED"))
    attempts = session.scalars(
        select(Attempt)
        .join(Job)
        .where(Job.workspace_id == workspace_id, Job.type == "inference.text")
        .order_by(Attempt.created_at.desc())
        .limit(200)
    ).all()
    return {
        "job_counts": dict(states),
        "terminal_jobs": terminal,
        "failure_rate": states["FAILED"] / terminal if terminal else None,
        "cancellation_rate": states["CANCELLED"] / terminal if terminal else None,
        "rates_denominator": "terminal_jobs",
        "recent_attempt_limit": 200,
        "recent_attempts": [
            {
                "attempt_id": str(a.id),
                "job_id": str(a.job_id),
                "node_id": str(a.node_id),
                "status": a.status,
                "error": a.error,
                "deployment": a.result.get("deployment"),
                "usage": a.result.get("usage"),
            }
            for a in attempts
        ],
    }
