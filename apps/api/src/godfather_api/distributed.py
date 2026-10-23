"""Durable parallel workflows using the existing scheduler, permissions and fences."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer
from godfather_contracts.agents import (
    ArtifactReference,
    WorkflowInput,
    WorkflowResult,
    WorkflowSubmission,
)
from godfather_contracts.distributed import DISTRIBUTED_RUNTIME, DistributedSubmission
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from godfather_api import workflow_service
from godfather_api.jobs import current_attempt
from godfather_api.logging import correlation_id
from godfather_api.models import (
    Agent,
    Attempt,
    DistributedJob,
    DistributedTask,
    Event,
    Job,
    Node,
    WorkflowRun,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import SessionDep, authenticate, connection_at, node_view
from godfather_api.scheduler import (
    ACTIVE,
    TERMINAL,
    job_event,
    lock_workspace,
    permitted,
    workspace_access,
)

router = APIRouter(
    prefix="/api/v1/distributed/jobs", dependencies=[Depends(HTTPBearer(auto_error=False))]
)


def participant_permitted(session: Session, job: Job, node: Node) -> bool:
    if job.id is None:
        return True  # Unsaved capability-directory probes are not distributed children.
    task = session.get(DistributedTask, job.id)
    if task is None:
        return True
    parent = session.get(DistributedJob, task.distributed_job_id)
    return bool(
        parent
        and parent.status in ("PENDING", "RUNNING")
        and task.ready
        and str(node.id) in task.allowed_node_ids
    )


def dependency_source(session: Session, job: Job, ref: ArtifactReference) -> Job:
    task = session.get(DistributedTask, job.id)
    if task is None or ref not in WorkflowInput.model_validate(job.input_refs).dependency_outputs:
        return job
    for predecessor in session.scalars(
        select(DistributedTask).where(DistributedTask.distributed_job_id == task.distributed_job_id)
    ):
        if predecessor.key not in task.depends_on:
            continue
        source = session.get(Job, predecessor.job_id)
        if (
            source
            and source.deleted_at is None
            and source.status == "COMPLETED"
            and source.workspace_id == job.workspace_id
        ):
            result = WorkflowResult.model_validate(source.result_refs)
            if result.final_output == ref:
                return source
    raise HTTPException(404, "Dependency artifact is not an authorized committed predecessor")


def stop_child(session: Session, job: Job, now: datetime) -> None:
    if job.status in TERMINAL:
        return
    attempt = current_attempt(session, job)
    job.cancel_requested_at = now
    job.status, job.assigned_node_id, job.next_run_at = "CANCELLED", None, None
    if attempt and attempt.status in ACTIVE:
        attempt.status, attempt.finished_at = "CANCELLED", now
    workflow_service.end_attempt(session, job, attempt, "cancelled")
    job_event(session, job, "cancelled", now, attempt)


def parent_event(
    session: Session, parent: DistributedJob, kind: str, now: datetime, actor_id: UUID | None = None
) -> None:
    session.add(
        Event(
            workspace_id=parent.workspace_id,
            actor_id=actor_id,
            type="distributed." + kind,
            correlation_id=correlation_id.get() or uuid4().hex,
            created_at=now,
            details={"distributed_job_id": str(parent.id)},
        )
    )


def advance(session: Session, now: datetime) -> None:
    """Scheduler-only reconciliation. Skip locked groups rather than invert lock order."""
    parents = session.scalars(
        select(DistributedJob)
        .where(DistributedJob.status.in_(("PENDING", "RUNNING")))
        .order_by(DistributedJob.id)
        .with_for_update(skip_locked=True)
    ).all()
    for parent in parents:
        tasks = session.scalars(
            select(DistributedTask).where(DistributedTask.distributed_job_id == parent.id)
        ).all()
        jobs = session.scalars(
            select(Job)
            .where(Job.id.in_([t.job_id for t in tasks]))
            .order_by(Job.id)
            .with_for_update(skip_locked=True)
        ).all()
        if len(jobs) != len(tasks):
            continue
        by_id = {j.id: j for j in jobs}
        by_key = {t.key: by_id[t.job_id] for t in tasks}
        failed = next(
            (j for j in jobs if j.status in ("FAILED", "CANCELLED") or j.deleted_at is not None),
            None,
        )
        if failed:
            parent.status, parent.error, parent.finished_at = (
                "FAILED",
                "A subtask failed or was cancelled; inspect its attempts before resubmitting.",
                now,
            )
            for job in jobs:
                stop_child(session, job, now)
            parent_event(session, parent, "failed", now)
            continue
        if jobs and all(j.status == "COMPLETED" for j in jobs):
            parent.status, parent.finished_at = "COMPLETED", now
            parent_event(session, parent, "completed", now)
            continue
        for task in tasks:
            if task.ready or not all(by_key[key].status == "COMPLETED" for key in task.depends_on):
                continue
            job = by_id[task.job_id]
            payload = WorkflowInput.model_validate(job.input_refs)
            payload.dependency_outputs = [
                WorkflowResult.model_validate(by_key[key].result_refs).final_output
                for key in task.depends_on
            ]
            job.input_refs = payload.model_dump(mode="json")
            task.ready = True
            job_event(session, job, "dependencies_ready", now)
        if any(j.attempt_count for j in jobs) and parent.status == "PENDING":
            parent.status = "RUNNING"
            parent_event(session, parent, "started", now)
    session.flush()


def authorized(
    session: Session, parent_id: UUID, actor_id: UUID, lock: bool = False
) -> DistributedJob:
    query = select(DistributedJob).where(DistributedJob.id == parent_id)
    parent = session.scalar(query.with_for_update() if lock else query)
    if parent is None or not workspace_access(session, actor_id, parent.workspace_id):
        raise HTTPException(404, "Distributed job not found in an authorized workspace")
    return parent


def summary(parent: DistributedJob) -> dict[str, object]:
    return {
        "id": str(parent.id),
        "name": parent.name,
        "workspace_id": str(parent.workspace_id),
        "owner_id": str(parent.owner_id),
        "status": parent.status,
        "created_at": parent.created_at,
        "finished_at": parent.finished_at,
        "error": parent.error,
    }


@router.post("", status_code=201)
def submit(
    payload: DistributedSubmission, request: Request, session: SessionDep
) -> dict[str, object]:
    from godfather_api.agents import submit_workflow

    actor = authenticate(request, session, "human")
    lock_workspace(session, payload.workspace_id)
    if not workspace_access(session, actor.owner_id, payload.workspace_id):
        raise HTTPException(404, "Workspace not found")
    probe = Job(
        id=uuid4(),
        owner_id=actor.owner_id,
        workspace_id=payload.workspace_id,
        requirements={},
        input_refs={},
        type="agent.workflow",
    )
    visible = {
        n.id: n
        for n in session.scalars(select(Node).where(Node.id.in_(payload.node_ids)))
        if permitted(session, probe, n)
    }
    if len(visible) != len(payload.node_ids):
        raise HTTPException(404, "Selected participant is unavailable or not permitted")
    parent = DistributedJob(
        owner_id=actor.owner_id,
        workspace_id=payload.workspace_id,
        name=payload.name,
        instruction=payload.instruction,
        selected_node_ids=[str(n) for n in payload.node_ids],
        final_task=payload.final_task,
    )
    session.add(parent)
    session.flush()
    for task in payload.tasks:
        child_input = task.input.model_copy(
            update={"instruction": payload.instruction + "\nTask:\n" + task.input.instruction}
        )
        child = submit_workflow(
            WorkflowSubmission(
                workspace_id=payload.workspace_id,
                agent_id=task.agent_id,
                agent_version=task.agent_version,
                input=child_input,
                priority=payload.priority,
                paid_consent=task.paid_consent,
            ),
            request,
            session,
        )
        job = session.get(Job, child.id)
        assert job is not None
        agent = session.get(Agent, job.agent_id)
        assert agent is not None
        spec = workflow_service.agent_view(agent).definition
        if task.depends_on and any(step.kind != "model" for step in spec.workflow.steps):
            raise HTTPException(
                422,
                "Dependent tasks must use model-only agents to combine predecessor outputs safely",
            )
        if task.depends_on:
            job.requirements = {
                **job.requirements,
                "runtimes": list(
                    dict.fromkeys([*child.requirements.runtimes, DISTRIBUTED_RUNTIME])
                ),
            }
        for node_id in task.node_ids:
            node = visible[node_id]
            if permitted(session, job, node):
                continue
            workspace = session.get(Workspace, job.workspace_id)
            selection = child.requirements.model_selection
            if (
                workspace
                and workspace.allowed_models is not None
                and (
                    (
                        selection
                        and any(
                            m not in workspace.allowed_models
                            for m in [selection.identifier, *selection.fallback_models]
                        )
                    )
                    or any(
                        m.identifier not in workspace.allowed_models
                        for m in child.requirements.models
                    )
                )
            ):
                raise HTTPException(
                    403,
                    f"{task.name}: the agent's model is not enabled in this "
                    "workspace. Open Models in this workspace and choose an "
                    "allowed model or ask a workspace administrator to enable it.",
                )
            from godfather_api.provider_connections import allowed

            if not allowed(session, job, node):
                raise HTTPException(
                    403,
                    f"{task.name}: the selected API connection is not "
                    f"authorized on {node.name}. Choose a permitted local model "
                    "or authorize the API connection for this computer.",
                )
            raise HTTPException(
                403,
                f"{task.name}: {node.name} cannot accept this task under "
                "its workspace or owner permissions. Check the agent's tool "
                "permissions and the owner's contribution setting.",
            )
        session.add(
            DistributedTask(
                job_id=job.id,
                distributed_job_id=parent.id,
                key=task.key,
                name=task.name,
                depends_on=list(task.depends_on),
                allowed_node_ids=[str(n) for n in task.node_ids],
                ready=not task.depends_on,
            )
        )
        session.flush()
    parent_event(session, parent, "submitted", datetime.now(UTC), actor.owner_id)
    return summary(parent)


@router.get("")
def list_jobs(
    request: Request,
    session: SessionDep,
    workspace_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    if workspace_id and not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found")
    memberships = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == actor.owner_id
    )
    query = (
        select(DistributedJob)
        .join(Workspace, Workspace.id == DistributedJob.workspace_id)
        .where(
            Workspace.deleted_at.is_(None),
            or_(Workspace.owner_id == actor.owner_id, DistributedJob.workspace_id.in_(memberships)),
        )
    )
    if workspace_id:
        query = query.where(DistributedJob.workspace_id == workspace_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(DistributedJob.created_at.desc(), DistributedJob.id)
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [summary(row) for row in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/options")
def options(
    workspace_id: UUID,
    request: Request,
    session: SessionDep,
    node_offset: Annotated[int, Query(ge=0)] = 0,
    agent_offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    from godfather_api.inference import models

    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found")
    probe = Job(
        id=uuid4(),
        owner_id=actor.owner_id,
        workspace_id=workspace_id,
        requirements={},
        input_refs={},
        type="agent.workflow",
    )
    available_nodes = [
        n
        for n in session.scalars(
            select(Node).where(Node.session_id.is_not(None)).order_by(Node.name, Node.id)
        )
        if permitted(session, probe, n)
    ]
    agents = session.scalars(
        select(Agent)
        .where(
            Agent.workspace_id == workspace_id, Agent.enabled.is_(True), Agent.deleted_at.is_(None)
        )
        .order_by(Agent.name, Agent.version.desc())
    ).all()
    agent_data = []
    for agent in agents[agent_offset : agent_offset + 25]:
        try:
            agent_spec = workflow_service.agent_view(agent)
        except HTTPException:
            continue
        agent_data.append(agent_spec.model_dump(mode="json"))
    nodes = []
    for node in available_nodes[node_offset : node_offset + 25]:
        spec = node_view(session, node)
        nodes.append(
            {
                "node_id": str(node.id),
                "name": node.name,
                "state": node.state,
                "connection_status": connection_at(
                    node.last_heartbeat_at, datetime.now(UTC), request.app.state.settings
                ),
                "context_supported": DISTRIBUTED_RUNTIME in spec.runtimes,
                "model_deployments": [
                    row["deployment"]
                    for row in models(workspace_id, request, session, 200, 0, node.id)
                ],
            }
        )
    return {
        "nodes": nodes,
        "agents": agent_data,
        "node_total": len(available_nodes),
        "agent_total": len(agents),
        "node_offset": node_offset,
        "agent_offset": agent_offset,
        "limit": 25,
    }


@router.get("/{parent_id}")
def detail(parent_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    parent = authorized(session, parent_id, actor.owner_id)
    tasks = session.scalars(
        select(DistributedTask)
        .where(DistributedTask.distributed_job_id == parent.id)
        .order_by(DistributedTask.key)
    ).all()
    now = datetime.now(UTC)
    seconds: dict[UUID, float] = {}
    task_data: list[dict[str, object]] = []
    for task in tasks:
        job = session.get(Job, task.job_id)
        assert job is not None
        attempts = session.scalars(
            select(Attempt).where(Attempt.job_id == job.id).order_by(Attempt.number)
        ).all()
        for attempt in attempts:
            if attempt.started_at:
                end = min(
                    now, attempt.finished_at or attempt.lease_expires_at, attempt.deadline_at or now
                )
                seconds[attempt.node_id] = seconds.get(attempt.node_id, 0) + max(
                    0, (end - attempt.started_at).total_seconds()
                )
        run = session.get(WorkflowRun, job.id)
        selection = job.requirements.get("model_selection")
        if attempts and attempts[-1].result.get("deployment"):
            selection = attempts[-1].result["deployment"]
        task_data.append(
            {
                "key": task.key,
                "name": task.name,
                "job_id": str(job.id),
                "depends_on": task.depends_on,
                "allowed_node_ids": task.allowed_node_ids,
                "ready": task.ready,
                "status": job.status,
                "assigned_node_id": str(job.assigned_node_id) if job.assigned_node_id else None,
                "attempt_count": job.attempt_count,
                "checkpoint_version": run.checkpoint_version if run else 0,
                "model": selection,
                "result": job.result_refs or None,
            }
        )
    total = sum(seconds.values())
    nodes: list[dict[str, object]] = []
    participant_ids = {UUID(n) for n in parent.selected_node_ids} | seconds.keys()
    for node_id in sorted(participant_ids, key=str):
        node = session.get(Node, node_id)
        if node is None:
            continue
        spec = node_view(session, node)
        online = (
            connection_at(node.last_heartbeat_at, now, request.app.state.settings) == "online"
            and node.state == "online"
        )
        nodes.append(
            {
                "id": str(node.id),
                "name": node.name,
                "state": node.state,
                "connection_status": connection_at(
                    node.last_heartbeat_at, now, request.app.state.settings
                ),
                "last_heartbeat_at": node.last_heartbeat_at,
                "execution_seconds": round(seconds.get(node.id, 0), 3),
                "contribution_percent": round(seconds.get(node.id, 0) / total * 100, 2)
                if total
                else None,
                "resources": spec.resources.model_dump(mode="json") if online else None,
            }
        )
    workspace = session.get(Workspace, parent.workspace_id)
    membership = session.get(WorkspaceMember, (parent.workspace_id, actor.owner_id))
    can_control = (
        parent.owner_id == actor.owner_id
        or bool(workspace and workspace.owner_id == actor.owner_id)
        or bool(membership and membership.role == "admin")
    )
    return {
        **summary(parent),
        "instruction": parent.instruction,
        "final_task": parent.final_task,
        "tasks": task_data,
        "nodes": nodes,
        "can_control": can_control,
        "generated_at": now,
        "contribution_basis": (
            "Share of recorded attempt execution time, including retries; "
            "not GPU usage or problem completion."
        ),
    }


@router.post("/{parent_id}/cancel")
def cancel(parent_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    parent = authorized(session, parent_id, actor.owner_id, True)
    workspace = session.get(Workspace, parent.workspace_id)
    membership = session.get(WorkspaceMember, (parent.workspace_id, actor.owner_id))
    if (
        parent.owner_id != actor.owner_id
        and (workspace is None or workspace.owner_id != actor.owner_id)
        and (membership is None or membership.role != "admin")
    ):
        raise HTTPException(403, "Only the job owner or workspace administrator may cancel")
    if parent.status in TERMINAL:
        return summary(parent)
    now = datetime.now(UTC)
    children = select(DistributedTask.job_id).where(DistributedTask.distributed_job_id == parent.id)
    for job in session.scalars(
        select(Job).where(Job.id.in_(children)).order_by(Job.id).with_for_update()
    ):
        stop_child(session, job, now)
    parent.status, parent.finished_at = "CANCELLED", now
    parent_event(session, parent, "cancelled", now, actor.owner_id)
    session.flush()
    return summary(parent)
