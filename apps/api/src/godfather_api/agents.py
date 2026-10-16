"""Workspace-scoped immutable agent versions and authenticated workflow endpoints."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer
from godfather_agent_runtime.tools import REGISTRY, ToolError, validate_agent
from godfather_contracts import Contract
from godfather_contracts.agents import (
    AgentCreate,
    AgentVersionCreate,
    AgentView,
    ArtifactReference,
    CheckpointView,
    WorkflowReport,
    WorkflowState,
    WorkflowSubmission,
)
from godfather_contracts.execution import AttemptIdentity
from godfather_contracts.jobs import JobView
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from godfather_api import workflow_service as service
from godfather_api.jobs import authorized_job, current_attempt, lock_execution, view
from godfather_api.models import (
    Agent,
    Artifact,
    Checkpoint,
    Event,
    Job,
    WorkflowRun,
    WorkflowStepRecord,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import SessionDep, authenticate, node_view
from godfather_api.scheduler import job_event, workspace_access

router = APIRouter(prefix="/api/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])


def audit_agent(session: Session, agent: Agent, actor_id: UUID, action: str) -> None:
    from godfather_api.logging import correlation_id

    session.add(
        Event(
            actor_id=actor_id,
            workspace_id=agent.workspace_id,
            type="agent." + action,
            correlation_id=correlation_id.get() or uuid4().hex,
            details={"agent_id": str(agent.agent_key), "version": agent.version},
        )
    )


class AgentControl(Contract):
    action: Literal["enable", "disable"]


class ArtifactRead(AttemptIdentity):
    artifact: ArtifactReference


def manage_workspace(session: Session, workspace_id: UUID, actor_id: UUID) -> None:
    workspace = session.get(Workspace, workspace_id)
    membership = session.get(WorkspaceMember, (workspace_id, actor_id))
    if workspace is None or not workspace_access(session, actor_id, workspace_id):
        raise HTTPException(404, "Workspace not found or permission denied")
    if workspace.owner_id != actor_id and (membership is None or membership.role != "admin"):
        raise HTTPException(403, "Workspace administration is required to manage agents")


def find_agent(
    session: Session, key: UUID, actor_id: UUID, version: int | None = None, lock: bool = False
) -> Agent:
    query = select(Agent).where(Agent.agent_key == key)
    if version is not None:
        query = query.where(Agent.version == version)
    query = query.order_by(Agent.version.desc()).limit(1)
    agent = session.scalar(query.with_for_update() if lock else query)
    if agent is None or not workspace_access(session, actor_id, agent.workspace_id):
        raise HTTPException(404, "Agent not found in an authorized workspace")
    return agent


def flush_agent(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError:
        raise HTTPException(
            409, "Agent name/version conflicts with an existing definition"
        ) from None


@router.post("/agents", response_model=AgentView, status_code=201)
def create_agent(payload: AgentCreate, request: Request, session: SessionDep) -> AgentView:
    actor = authenticate(request, session, "admin")
    manage_workspace(session, payload.workspace_id, actor.owner_id)
    try:
        validate_agent(payload.definition)
    except ToolError:
        raise HTTPException(422, "Unsupported tools or missing agent permissions") from None
    agent = Agent(
        owner_id=actor.owner_id,
        workspace_id=payload.workspace_id,
        agent_key=uuid4(),
        version=1,
        name=payload.definition.name,
        definition=payload.definition.model_dump(mode="json"),
        enabled=payload.definition.enabled,
    )
    session.add(agent)
    flush_agent(session)
    audit_agent(session, agent, actor.owner_id, "created")
    return service.agent_view(agent)


@router.get("/agents", response_model=list[AgentView])
def list_agents(
    workspace_id: UUID,
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentView]:
    actor = authenticate(request, session, "admin")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found or permission denied")
    rows = session.scalars(
        select(Agent)
        .where(Agent.workspace_id == workspace_id)
        .order_by(Agent.agent_key, Agent.version)
        .limit(limit)
        .offset(offset)
    ).all()
    # Legacy schema-only definitions remain disabled and cannot execute.
    result = []
    for agent in rows:
        try:
            result.append(service.agent_view(agent))
        except HTTPException:
            continue
    return result


@router.get("/agents/{agent_id}", response_model=AgentView)
def inspect_agent(
    agent_id: UUID,
    request: Request,
    session: SessionDep,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> AgentView:
    actor = authenticate(request, session, "admin")
    return service.agent_view(find_agent(session, agent_id, actor.owner_id, version))


@router.get("/agents/{agent_id}/versions", response_model=list[AgentView])
def versions(
    agent_id: UUID,
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentView]:
    actor = authenticate(request, session, "admin")
    agent = find_agent(session, agent_id, actor.owner_id)
    return [
        service.agent_view(row)
        for row in session.scalars(
            select(Agent)
            .where(Agent.agent_key == agent_id, Agent.workspace_id == agent.workspace_id)
            .order_by(Agent.version)
            .limit(limit)
            .offset(offset)
        )
    ]


@router.post("/agents/{agent_id}/versions", response_model=AgentView, status_code=201)
def create_version(
    agent_id: UUID, payload: AgentVersionCreate, request: Request, session: SessionDep
) -> AgentView:
    actor = authenticate(request, session, "admin")
    previous = find_agent(session, agent_id, actor.owner_id, lock=True)
    manage_workspace(session, previous.workspace_id, actor.owner_id)
    if previous.version != payload.expected_version:
        raise HTTPException(409, "Agent version changed; inspect the current version")
    try:
        validate_agent(payload.definition)
    except ToolError:
        raise HTTPException(422, "Unsupported tools or missing agent permissions") from None
    agent = Agent(
        owner_id=previous.owner_id,
        workspace_id=previous.workspace_id,
        agent_key=previous.agent_key,
        version=previous.version + 1,
        name=payload.definition.name,
        definition=payload.definition.model_dump(mode="json"),
        enabled=payload.definition.enabled,
    )
    session.add(agent)
    flush_agent(session)
    audit_agent(session, agent, actor.owner_id, "created")
    return service.agent_view(agent)


@router.post("/agents/{agent_id}/versions/{version}/control", response_model=AgentView)
def control_agent(
    agent_id: UUID, version: int, payload: AgentControl, request: Request, session: SessionDep
) -> AgentView:
    actor = authenticate(request, session, "admin")
    agent = find_agent(session, agent_id, actor.owner_id, version, True)
    manage_workspace(session, agent.workspace_id, actor.owner_id)
    service.agent_view(agent)  # Refuse enabling unsupported legacy definitions.
    agent.enabled = payload.action == "enable"
    audit_agent(session, agent, actor.owner_id, payload.action + "d")
    return service.agent_view(agent)


@router.get("/tools")
def tools(request: Request, session: SessionDep) -> list[dict[str, object]]:
    authenticate(request, session, "admin")
    return [tool.model_dump(mode="json") for tool in REGISTRY.values()]


@router.post("/workflow/jobs", response_model=JobView, status_code=201)
def submit_workflow(payload: WorkflowSubmission, request: Request, session: SessionDep) -> JobView:
    actor = authenticate(request, session, "admin")
    agent = find_agent(session, payload.agent_id, actor.owner_id, payload.agent_version)
    if agent.workspace_id != payload.workspace_id:
        raise HTTPException(404, "Agent does not belong to this workspace")
    spec = service.agent_view(agent).definition
    if not agent.enabled:
        raise HTTPException(409, "Agent version is disabled")
    requirements = spec.requirements.model_copy(
        update={"tools": spec.allowed_tools, "tool_permissions": spec.permissions}
    )
    job = Job(
        owner_id=actor.owner_id,
        workspace_id=payload.workspace_id,
        agent_id=agent.id,
        type="agent.workflow",
        requirements=requirements.model_dump(mode="json"),
        input_refs=payload.input.model_dump(mode="json"),
        priority=payload.priority,
        timeout_seconds=spec.timeout_seconds,
        retry_limit=spec.retry.limit,
        retry_backoff_seconds=spec.retry.backoff_seconds,
    )
    session.add(job)
    session.flush()
    session.add(
        WorkflowRun(
            job_id=job.id,
            agent_id=agent.id,
            workflow_id=spec.workflow.id,
            workflow_version=spec.workflow.version,
        )
    )
    session.flush()
    job_event(session, job, "submitted", datetime.now(UTC), actor_id=actor.owner_id)
    service.event(session, job, None, "submitted")
    return view(session, job)


def workflow_job(session: Session, job_id: UUID, actor_id: UUID) -> Job:
    job = authorized_job(session, job_id, actor_id)
    if job.type != "agent.workflow":
        raise HTTPException(404, "Workflow job not found")
    return job


@router.get("/workflow/jobs/{job_id}")
def inspect_workflow(job_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "admin")
    job = workflow_job(session, job_id, actor.owner_id)
    run = session.get(WorkflowRun, job.id)
    assert run is not None
    attempt = current_attempt(session, job)
    return {
        "job": view(session, job).model_dump(mode="json"),
        "workflow_id": str(run.workflow_id),
        "workflow_version": run.workflow_version,
        "status": run.status,
        "current_step": run.cursor,
        "checkpoint_version": run.checkpoint_version,
        "state": service.workflow_assignment(
            session, request.app.state.artifacts, job, attempt
        ).state.model_dump(mode="json")
        if attempt
        else None,
    }


@router.get("/workflow/jobs/{job_id}/steps")
def steps(job_id: UUID, request: Request, session: SessionDep) -> list[dict[str, object]]:
    actor = authenticate(request, session, "admin")
    job = workflow_job(session, job_id, actor.owner_id)
    records = session.scalars(
        select(WorkflowStepRecord)
        .where(WorkflowStepRecord.job_id == job.id)
        .order_by(WorkflowStepRecord.created_at, WorkflowStepRecord.id)
    ).all()
    return [
        {
            "id": str(r.id),
            "step_id": r.step_id,
            "attempt_id": str(r.attempt_id),
            "status": r.status,
            "input_refs": r.input_refs,
            "output_artifact_id": str(r.output_artifact_id) if r.output_artifact_id else None,
            "metadata": r.metadata_refs,
            "error_code": r.error_code,
            "started_at": r.created_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in records
    ]


@router.get("/workflow/jobs/{job_id}/checkpoints", response_model=list[CheckpointView])
def checkpoints(job_id: UUID, request: Request, session: SessionDep) -> list[CheckpointView]:
    actor = authenticate(request, session, "admin")
    job = workflow_job(session, job_id, actor.owner_id)
    return [
        service.checkpoint_view(session, job, cp)
        for cp in session.scalars(
            select(Checkpoint).where(Checkpoint.job_id == job.id).order_by(Checkpoint.version)
        )
    ]


@router.get("/workflow/jobs/{job_id}/result")
def result(job_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "admin")
    job = workflow_job(session, job_id, actor.owner_id)
    attempt = current_attempt(session, job)
    final: object = None
    if job.status == "COMPLETED":
        ref = ArtifactReference.model_validate(job.result_refs["final_output"])
        final = service.load_artifact(session, request.app.state.artifacts, job, ref)
    return {
        "job_id": str(job.id),
        "status": job.status,
        "result": job.result_refs or None,
        "output": final,
        "error": attempt.error if attempt else None,
    }


@router.get("/workflow/jobs/{job_id}/artifacts/{artifact_id}")
def artifact(job_id: UUID, artifact_id: UUID, request: Request, session: SessionDep) -> object:
    actor = authenticate(request, session, "admin")
    job = workflow_job(session, job_id, actor.owner_id)
    row = session.get(Artifact, artifact_id)
    if row is None or row.job_id != job.id:
        raise HTTPException(404, "Artifact not found in this workflow")
    return service.load_artifact(session, request.app.state.artifacts, job, service.reference(row))


@router.post("/workers/{node_id}/jobs/{job_id}/workflow/report", response_model=WorkflowState)
def report_step(
    node_id: UUID, job_id: UUID, payload: WorkflowReport, request: Request, session: SessionDep
) -> WorkflowState:
    node, job, attempt = lock_execution(node_id, job_id, payload, request, session)
    if job.type != "agent.workflow" or node.runtimes.get("workflow_protocol_version") != 1:
        raise HTTPException(403, "Workflow execution requires explicit worker opt-in")
    return service.transition(
        session, request.app.state.artifacts, job, attempt, node_view(session, node), payload
    )


@router.post("/workers/{node_id}/jobs/{job_id}/workflow/artifact")
def read_worker_artifact(
    node_id: UUID, job_id: UUID, payload: ArtifactRead, request: Request, session: SessionDep
) -> dict[str, object]:
    node, job, _ = lock_execution(node_id, job_id, payload, request, session)
    if job.type != "agent.workflow" or node.runtimes.get("workflow_protocol_version") != 1:
        raise HTTPException(403, "Workflow execution requires explicit worker opt-in")
    return {
        "data": service.load_artifact(session, request.app.state.artifacts, job, payload.artifact)
    }
