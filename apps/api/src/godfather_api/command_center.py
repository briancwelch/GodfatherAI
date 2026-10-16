"""Local Command Center projections over existing authorized durable state."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer
from godfather_contracts.execution import Requirements
from sqlalchemy import Select, String, case, false, func, or_, select, true
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from godfather_api import agents, inference, jobs, workflow_service
from godfather_api.models import (
    AccessCredential,
    Agent,
    Attempt,
    Checkpoint,
    Event,
    Job,
    Node,
    User,
    WorkflowRun,
    WorkflowStepRecord,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import (
    SessionDep,
    authenticate,
    connection_at,
    human_event_details,
    human_node_view,
    node_view,
    node_visibility,
)
from godfather_api.scheduler import matches, permitted, workspace_access

router = APIRouter(
    prefix="/api/v1/command-center", dependencies=[Depends(HTTPBearer(auto_error=False))]
)
PAGE_SIZE = 100


def manages(session: Session, workspace: Workspace, actor_id: UUID) -> bool:
    membership = session.get(WorkspaceMember, (workspace.id, actor_id))
    return workspace.owner_id == actor_id or (membership is not None and membership.role == "admin")


def severity_expression() -> ColumnElement[str]:
    return case(
        (or_(Event.type.like("%failed%"), Event.type.like("%review_required%")), "error"),
        (
            or_(
                Event.type.like("%interrupted%"),
                Event.type.like("%expired%"),
                Event.type.like("%recovery%"),
                Event.details["to"].astext.in_(("offline", "suspect")),
            ),
            "warning",
        ),
        else_="info",
    )


def event_data(row: Event, severity: str, actor_id: UUID) -> dict[str, object]:
    return {
        "id": str(row.id),
        "type": row.type,
        "created_at": row.created_at.isoformat(),
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "job_id": str(row.job_id) if row.job_id else None,
        "node_id": str(row.node_id) if row.node_id else None,
        "attempt_id": str(row.attempt_id) if row.attempt_id else None,
        "severity": severity,
        "details": human_event_details(row, actor_id),
        "correlation_id": row.correlation_id,
    }


@router.get("/events")
def events(
    request: Request,
    session: SessionDep,
    workspace_id: UUID | None = None,
    node_id: UUID | None = None,
    user_id: UUID | None = None,
    job_id: UUID | None = None,
    agent_id: UUID | None = None,
    event_type: Annotated[str | None, Query(max_length=100)] = None,
    severity: Literal["info", "warning", "error"] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    if workspace_id is not None and not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found or permission denied")
    if any(value is not None and value.tzinfo is None for value in (since, until)):
        raise HTTPException(422, "Event time filters require timezone offsets")
    if since is not None and until is not None and since > until:
        raise HTTPException(422, "Event time range is reversed")
    visible = select(Workspace.id).where(
        or_(
            Workspace.owner_id == actor.owner_id,
            Workspace.id.in_(
                select(WorkspaceMember.workspace_id).where(
                    WorkspaceMember.user_id == actor.owner_id
                )
            ),
        )
    )
    query = select(Event, severity_expression()).where(
        or_(
            Event.workspace_id.in_(visible),
            (
                Event.workspace_id.is_(None)
                & Event.node_id.in_(select(Node.id).where(node_visibility(session, actor.owner_id)))
            ),
        )
    )
    if workspace_id is not None:
        query = query.where(or_(Event.workspace_id == workspace_id, Event.workspace_id.is_(None)))
    for column, value in (
        (Event.node_id, node_id),
        (Event.actor_id, user_id),
        (Event.job_id, job_id),
        (Event.type, event_type),
    ):
        if value is not None:
            query = query.where(column == value)
    if agent_id is not None:
        agent_jobs = (
            select(Job.id).join(Agent, Job.agent_id == Agent.id).where(Agent.agent_key == agent_id)
        )
        query = query.where(
            or_(Event.details["agent_id"].astext == str(agent_id), Event.job_id.in_(agent_jobs))
        )
    if severity is not None:
        query = query.where(severity_expression() == severity)
    if since is not None:
        query = query.where(Event.created_at >= since)
    if until is not None:
        query = query.where(Event.created_at <= until)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Event.created_at.desc(), Event.id.desc()).limit(PAGE_SIZE).offset(offset)
    )
    return {
        "items": [event_data(e, s, actor.owner_id) for e, s in rows],
        "total": total,
        "offset": offset,
        "limit": PAGE_SIZE,
    }


@router.get("")
def overview(
    request: Request,
    session: SessionDep,
    workspace_id: UUID | None = None,
    section: Literal["overview", "jobs", "nodes", "agents", "models", "activity"] = "overview",
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[str, Query(max_length=32)] = "",
) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    member_ids = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == actor.owner_id
    )
    workspaces = session.scalars(
        select(Workspace)
        .where(or_(Workspace.owner_id == actor.owner_id, Workspace.id.in_(member_ids)))
        .order_by(Workspace.name, Workspace.id)
    ).all()
    selected = (
        next((w for w in workspaces if w.id == workspace_id), None)
        if workspace_id
        else next(iter(workspaces), None)
    )
    if workspace_id is not None and selected is None:
        raise HTTPException(404, "Workspace not found or permission denied")
    node_query = select(Node).where(
        Node.session_id.is_not(None), node_visibility(session, actor.owner_id)
    )
    node_counts = dict(
        session.execute(
            select(Node.state, func.count())
            .where(Node.session_id.is_not(None), node_visibility(session, actor.owner_id))
            .group_by(Node.state)
        )
        .tuples()
        .all()
    )
    live_jobs = true() if session.info.get("test") else ~Job.type.like("synthetic.%")
    job_query = (
        select(Job).where(Job.workspace_id == selected.id)
        if selected
        else select(Job).where(false())
    )
    job_query = job_query.where(live_jobs)
    job_counts = (
        dict(
            session.execute(
                select(Job.status, func.count())
                .where(Job.workspace_id == selected.id, live_jobs)
                .group_by(Job.status)
            )
            .tuples()
            .all()
        )
        if selected
        else {}
    )
    agent_query = (
        select(Agent).where(Agent.workspace_id == selected.id)
        if selected
        else select(Agent).where(false())
    )
    agent_counts = (
        dict(
            session.execute(
                select(Agent.enabled, func.count())
                .where(Agent.workspace_id == selected.id)
                .group_by(Agent.enabled)
            )
            .tuples()
            .all()
        )
        if selected
        else {}
    )
    if section == "nodes":
        if status:
            node_query = node_query.where(Node.state == status)
        if search:
            node_query = node_query.where(
                or_(
                    Node.name.icontains(search, autoescape=True),
                    Node.os.icontains(search, autoescape=True),
                    Node.id.cast(String).icontains(search, autoescape=True),
                    Node.owner_id.cast(String).icontains(search, autoescape=True),
                )
            )
    if section == "jobs":
        if status:
            job_query = job_query.where(Job.status == status)
        if search:
            job_query = job_query.where(
                or_(
                    Job.type.icontains(search, autoescape=True),
                    Job.id.cast(String).icontains(search, autoescape=True),
                    Job.owner_id.cast(String).icontains(search, autoescape=True),
                )
            )
    if section == "agents" and search:
        agent_query = agent_query.where(Agent.name.icontains(search, autoescape=True))

    def total(query: Select[Any]) -> int:
        return int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)

    node_total, job_total, agent_total = total(node_query), total(job_query), total(agent_query)
    node_rows = session.scalars(
        node_query.order_by(Node.created_at.desc(), Node.id)
        .limit(PAGE_SIZE)
        .offset(offset if section == "nodes" else 0)
    ).all()
    job_rows = session.scalars(
        job_query.order_by(Job.created_at.desc(), Job.id)
        .limit(PAGE_SIZE)
        .offset(offset if section == "jobs" else 0)
    ).all()
    agent_rows = session.scalars(
        agent_query.order_by(Agent.name, Agent.version.desc())
        .limit(PAGE_SIZE)
        .offset(offset if section == "agents" else 0)
    ).all()
    agent_views = []
    for agent in agent_rows:
        try:
            agent_views.append(workflow_service.agent_view(agent).model_dump(mode="json"))
        except HTTPException:
            continue
    active = dict(
        session.execute(
            select(Job.assigned_node_id, func.count())
            .where(
                Job.status.in_(("ASSIGNED", "RUNNING")),
                Job.workspace_id.in_(
                    select(Workspace.id).where(
                        or_(Workspace.owner_id == actor.owner_id, Workspace.id.in_(member_ids))
                    )
                ),
            )
            .group_by(Job.assigned_node_id)
        )
        .tuples()
        .all()
    )
    # Availability means compatible healthy advertisement, not an execution guarantee.
    available_versions = 0
    if selected:
        healthy = [
            (n, node_view(session, n))
            for n in session.scalars(
                select(Node)
                .join(AccessCredential, AccessCredential.node_id == Node.id)
                .join(User, User.id == Node.owner_id)
                .where(
                    Node.state == "online",
                    Node.session_id.is_not(None),
                    AccessCredential.kind == "worker",
                    AccessCredential.revoked.is_(False),
                    User.enabled.is_(True),
                )
            )
            if connection_at(n.last_heartbeat_at, datetime.now(UTC), request.app.state.settings)
            == "online"
        ]
        for agent in session.scalars(
            select(Agent).where(Agent.workspace_id == selected.id, Agent.enabled.is_(True))
        ):
            try:
                definition = workflow_service.agent_view(agent).definition
            except HTTPException:
                continue
            requirements = Requirements.model_validate(
                {
                    **definition.requirements.model_dump(),
                    "tools": definition.allowed_tools,
                    "tool_permissions": definition.permissions,
                }
            )
            probe = Job(
                owner_id=actor.owner_id,
                workspace_id=selected.id,
                requirements=requirements.model_dump(mode="json"),
            )
            if any(
                v.workflow_protocol_version == 1
                and permitted(session, probe, n)
                and matches(requirements, v, [])
                for n, v in healthy
            ):
                available_versions += 1
    active_agent_versions = (
        session.scalar(
            select(func.count(func.distinct(Job.agent_id))).where(
                Job.workspace_id == selected.id, Job.status.in_(("ASSIGNED", "RUNNING"))
            )
        )
        if selected
        else 0
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "actor_id": str(actor.owner_id),
        "workspace_id": str(selected.id) if selected else None,
        "workspaces": [
            {
                "id": str(w.id),
                "name": w.name,
                "owner_id": str(w.owner_id),
                "can_manage": manages(session, w, actor.owner_id),
            }
            for w in workspaces
        ],
        "node_counts": node_counts,
        "job_counts": job_counts,
        "agent_counts": {
            "enabled_versions": agent_counts.get(True, 0),
            "disabled_versions": agent_counts.get(False, 0),
            "compatible_online_versions": available_versions,
            "active_versions": active_agent_versions or 0,
        },
        "nodes": [
            {
                **human_node_view(session, n, actor.owner_id).model_dump(mode="json"),
                "visible_active_jobs": active.get(n.id, 0),
            }
            for n in node_rows
        ],
        "jobs": [jobs.view(session, j).model_dump(mode="json") for j in job_rows],
        "agents": agent_views,
        "models": inference.models(
            selected.id, request, session, PAGE_SIZE, offset if section == "models" else 0
        )
        if selected
        else [],
        "metrics": inference.metrics(selected.id, request, session) if selected else None,
        "events": events(request, session, workspace_id=selected.id if selected else None),
        "totals": {"nodes": node_total, "jobs": job_total, "agents": agent_total},
        "limit": PAGE_SIZE,
        "offset": offset,
    }


@router.get("/jobs/{job_id}")
def job_detail(job_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    job = jobs.authorized_job(session, job_id, actor.owner_id)
    run = session.get(WorkflowRun, job.id)
    agent = session.get(Agent, job.agent_id) if job.agent_id else None
    workspace = session.get(Workspace, job.workspace_id)
    assert workspace is not None
    return {
        "can_control": job.owner_id == actor.owner_id
        or manages(session, workspace, actor.owner_id),
        "job": jobs.view(session, job).model_dump(mode="json"),
        "attempts": [a.model_dump(mode="json") for a in jobs.attempts(job_id, request, session)],
        "workflow": {
            "status": run.status,
            "current_step": run.cursor,
            "checkpoint_version": run.checkpoint_version,
            "recovery_error": run.recovery_error,
            "agent_id": str(agent.agent_key) if agent else None,
            "agent_version": agent.version if agent else None,
        }
        if run
        else None,
        "checkpoints": [
            workflow_service.checkpoint_view(session, job, cp).model_dump(mode="json")
            for cp in session.scalars(
                select(Checkpoint).where(Checkpoint.job_id == job.id).order_by(Checkpoint.version)
            )
        ]
        if run
        else [],
        "steps": agents.steps(job_id, request, session) if run else [],
        "events": events(request, session, job_id=job_id),
        "output": agents.result(job_id, request, session)
        if run and job.status == "COMPLETED"
        else None,
    }


@router.get("/nodes/{node_id}")
def node_detail(node_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    node = session.scalar(
        select(Node).where(Node.id == node_id, node_visibility(session, actor.owner_id))
    )
    if node is None or node.session_id is None:
        raise HTTPException(404, "Node not found")
    member_ids = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == actor.owner_id
    )
    visible = select(Workspace.id).where(
        or_(Workspace.owner_id == actor.owner_id, Workspace.id.in_(member_ids))
    )
    assigned = session.scalars(
        select(Job)
        .where(
            Job.workspace_id.in_(visible),
            or_(
                Job.assigned_node_id == node_id,
                Job.id.in_(select(Attempt.job_id).where(Attempt.node_id == node_id)),
            ),
        )
        .order_by(Job.created_at.desc())
        .limit(PAGE_SIZE)
    ).all()
    return {
        "can_control": node.owner_id == actor.owner_id,
        "node": human_node_view(session, node, actor.owner_id).model_dump(mode="json"),
        "jobs": [jobs.view(session, j).model_dump(mode="json") for j in assigned],
        "events": events(request, session, node_id=node_id),
    }


@router.get("/agents/{agent_id}")
def agent_history(agent_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    agent = agents.find_agent(session, agent_id, actor.owner_id)
    rows = session.execute(
        select(Job.id, Attempt.node_id, Agent.version, WorkflowStepRecord)
        .select_from(Job)
        .join(Agent, Job.agent_id == Agent.id)
        .join(WorkflowStepRecord, WorkflowStepRecord.job_id == Job.id)
        .join(Attempt, WorkflowStepRecord.attempt_id == Attempt.id)
        .where(
            Agent.agent_key == agent.agent_key,
            Agent.workspace_id == agent.workspace_id,
            WorkflowStepRecord.metadata_refs["kind"].astext == "model",
        )
        .order_by(WorkflowStepRecord.created_at.desc(), WorkflowStepRecord.id)
        .limit(PAGE_SIZE)
    )
    return {
        "assignments": [
            {
                "job_id": str(job_id),
                "node_id": str(node_id),
                "agent_version": version,
                "step_id": record.step_id,
                "status": record.status,
                "deployment": record.metadata_refs.get("model"),
                "usage": record.metadata_refs.get("usage"),
            }
            for job_id, node_id, version, record in rows
        ],
        "events": events(request, session, agent_id=agent_id),
        "limit": PAGE_SIZE,
    }
