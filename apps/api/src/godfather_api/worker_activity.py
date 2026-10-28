"""Minimal history for the authenticated computer, including shared participants."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from godfather_contracts.worker_activity import (
    ActivityCursor,
    ActivityRequest,
    ActivityResponse,
    JobNotice,
    NodeJob,
)
from sqlalchemy import and_, or_, select

from godfather_api.models import Attempt, Event, Job, Node, Workspace, WorkspaceMember
from godfather_api.nodes import SessionDep, authenticate

router = APIRouter(prefix="/api/v1/workers/activity")
NOTICE_TYPES = (
    "job.assigned",
    "job.started",
    "job.completed",
    "job.cancelled",
    "job.cancellation_requested",
    "job.attempt_failed",
    "job.lease_expired",
    "job.timeout",
    "job.permission_lost",
)


@router.post("/jobs", response_model=ActivityResponse)
def activity(payload: ActivityRequest, request: Request, session: SessionDep) -> ActivityResponse:
    credential = authenticate(request, session, "worker")
    node = session.get(Node, credential.node_id) if credential.node_id else None
    if node is None or node.owner_id != credential.owner_id or node.state == "disabled":
        raise HTTPException(403, "This computer is unavailable")
    memberships = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == credential.owner_id
    )
    scope = and_(
        Job.deleted_at.is_(None),
        Workspace.deleted_at.is_(None),
        or_(Workspace.owner_id == credential.owner_id, Job.workspace_id.in_(memberships)),
        or_(Attempt.node_id == node.id, Attempt.result["shared_sessions"].has_key(str(node.id))),
    )
    query = (
        select(Attempt, Job, Workspace.name)
        .join(Job, Attempt.job_id == Job.id)
        .join(Workspace, Job.workspace_id == Workspace.id)
        .where(scope)
    )
    if payload.job_id:
        query = query.where(Job.id == payload.job_id)
    rows = session.execute(
        query.order_by(
            Attempt.status.in_(("ASSIGNED", "RUNNING")).desc(),
            Attempt.created_at.desc(),
            Attempt.id.desc(),
        )
        .offset(payload.offset)
        .limit(payload.limit + 1)
    ).all()
    event_query = (
        select(Event)
        .join(Attempt, Event.attempt_id == Attempt.id)
        .join(Job, Attempt.job_id == Job.id)
        .join(Workspace, Job.workspace_id == Workspace.id)
        .where(scope, Event.job_id == Job.id, Event.type.in_(NOTICE_TYPES))
    )
    notices = []
    more_events = False
    if payload.cursor:
        cursor = payload.cursor
        events = list(
            session.scalars(
                event_query.where(
                    or_(
                        Event.created_at > cursor.at,
                        and_(Event.created_at == cursor.at, Event.id > cursor.id),
                    )
                )
                .order_by(Event.created_at, Event.id)
                .limit(101)
            )
        )
        more_events = len(events) > 100
        for event in events[:100]:
            assert event.job_id and event.attempt_id
            notices.append(
                JobNotice(
                    id=event.id,
                    job_id=event.job_id,
                    attempt_id=event.attempt_id,
                    type=event.type,
                    created_at=event.created_at,
                )
            )
        if notices:
            cursor = ActivityCursor(at=notices[-1].created_at, id=notices[-1].id)
    else:
        # Establish a baseline: opening a new worker must not announce old jobs as new.
        latest = session.scalar(
            event_query.order_by(Event.created_at.desc(), Event.id.desc()).limit(1)
        )
        cursor = ActivityCursor(
            at=latest.created_at if latest else datetime.now(UTC),
            id=latest.id if latest else UUID(int=0),
        )
    return ActivityResponse(
        node_id=node.id,
        jobs=[
            NodeJob(
                job_id=job.id,
                attempt_id=attempt.id,
                type=job.type,
                workspace=name,
                status=attempt.status,
                job_status=job.status,
                number=attempt.number,
                shared=attempt.node_id != node.id or bool(attempt.result.get("shared_sessions")),
                created_at=attempt.created_at,
                started_at=attempt.started_at,
                finished_at=attempt.finished_at,
            )
            for attempt, job, name in rows[: payload.limit]
        ],
        has_more=len(rows) > payload.limit,
        events=notices,
        cursor=cursor,
        more_events=more_events,
    )
