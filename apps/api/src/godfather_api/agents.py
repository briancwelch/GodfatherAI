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
from godfather_contracts.coding import CODING_RUNTIME, REPOSITORY_PREFIX
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
    Node,
    WorkflowRun,
    WorkflowStepRecord,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import SessionDep, authenticate, node_view, node_visibility
from godfather_api.scheduler import job_event, lock_workspace, workspace_access

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
    query = select(Agent).where(Agent.agent_key == key, Agent.deleted_at.is_(None))
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
    actor = authenticate(request, session, "human")
    lock_workspace(session, payload.workspace_id)
    manage_workspace(session, payload.workspace_id, actor.owner_id)
    try:
        validate_agent(payload.definition)
    except ToolError:
        raise HTTPException(422, "Unsupported tools or missing agent permissions") from None
    previous = session.scalar(
        select(Agent)
        .where(Agent.workspace_id == payload.workspace_id, Agent.name == payload.definition.name)
        .order_by(Agent.version.desc())
        .limit(1)
    )
    if previous is not None and previous.deleted_at is None:
        raise HTTPException(409, "Agent name already exists; create a new version")
    agent = Agent(
        owner_id=actor.owner_id,
        workspace_id=payload.workspace_id,
        agent_key=uuid4(),
        version=previous.version + 1 if previous else 1,
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
    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found or permission denied")
    rows = session.scalars(
        select(Agent)
        .where(Agent.workspace_id == workspace_id, Agent.deleted_at.is_(None))
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
    actor = authenticate(request, session, "human")
    return service.agent_view(find_agent(session, agent_id, actor.owner_id, version))


@router.get("/agents/{agent_id}/versions", response_model=list[AgentView])
def versions(
    agent_id: UUID,
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentView]:
    actor = authenticate(request, session, "human")
    agent = find_agent(session, agent_id, actor.owner_id)
    return [
        service.agent_view(row)
        for row in session.scalars(
            select(Agent)
            .where(
                Agent.agent_key == agent_id,
                Agent.workspace_id == agent.workspace_id,
                Agent.deleted_at.is_(None),
            )
            .order_by(Agent.version)
            .limit(limit)
            .offset(offset)
        )
    ]


@router.post("/agents/{agent_id}/versions", response_model=AgentView, status_code=201)
def create_version(
    agent_id: UUID, payload: AgentVersionCreate, request: Request, session: SessionDep
) -> AgentView:
    actor = authenticate(request, session, "human")
    previous = find_agent(session, agent_id, actor.owner_id)
    lock_workspace(session, previous.workspace_id)
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
    actor = authenticate(request, session, "human")
    agent = find_agent(session, agent_id, actor.owner_id, version)
    lock_workspace(session, agent.workspace_id)
    agent = find_agent(session, agent_id, actor.owner_id, version, True)
    manage_workspace(session, agent.workspace_id, actor.owner_id)
    service.agent_view(agent)  # Refuse enabling unsupported legacy definitions.
    agent.enabled = payload.action == "enable"
    audit_agent(session, agent, actor.owner_id, payload.action + "d")
    return service.agent_view(agent)


@router.get("/tools")
def tools(request: Request, session: SessionDep) -> list[dict[str, object]]:
    authenticate(request, session, "human")
    return [tool.model_dump(mode="json") for tool in REGISTRY.values()]


@router.get("/agent-options")
def agent_options(workspace_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    """Actual runtime catalog and owner-visible capability advertisements, no credentials."""
    from godfather_api import inference

    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found or permission denied")
    workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    capabilities: set[str] = set()
    for node in session.scalars(select(Node).where(node_visibility(session, actor.owner_id))):
        view = node_view(session, node)
        capabilities.update(view.primary_capabilities)
        capabilities.update(view.secondary_capabilities)
    return {
        "capabilities": sorted(capabilities),
        "models": inference.models(workspace_id, request, session, 200, 0),
        "model_limit": 200,
        "repositories": coding_repositories(workspace_id, request, session),
        "tools": [
            tool.model_dump(mode="json")
            for tool in REGISTRY.values()
            if workspace.allowed_tools is None
            or f"{tool.reference.name}@{tool.reference.version}" in workspace.allowed_tools
        ],
        "workflows": [
            {"id": "text", "name": "Read-only model response", "output_schema": "text"},
            {"id": "plan", "name": "Structured plan", "output_schema": "plan"},
            {"id": "coding", "name": "Isolated coding task", "output_schema": "coding"},
        ],
    }


@router.get("/coding/repositories")
def coding_repositories(
    workspace_id: UUID, request: Request, session: SessionDep
) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found")
    result = []
    for node in session.scalars(select(Node).where(node_visibility(session, actor.owner_id))):
        for repo in node_view(session, node).coding_repositories:
            if (
                actor.owner_id in repo.allowed_user_ids
                and workspace_id in repo.allowed_workspace_ids
            ):
                result.append(
                    {
                        "id": str(repo.id),
                        "name": repo.name,
                        "node_name": node.name,
                        "available": node.state == "online",
                    }
                )
    return result


@router.post("/workflow/jobs", response_model=JobView, status_code=201)
def submit_workflow(payload: WorkflowSubmission, request: Request, session: SessionDep) -> JobView:
    actor = authenticate(request, session, "human")
    lock_workspace(session, payload.workspace_id)
    agent = find_agent(session, payload.agent_id, actor.owner_id, payload.agent_version)
    if agent.workspace_id != payload.workspace_id:
        raise HTTPException(404, "Agent does not belong to this workspace")
    spec = service.agent_view(agent).definition
    if (
        spec.requirements.model_selection
        and spec.requirements.model_selection.connection_id
        and not payload.paid_consent
    ):
        raise HTTPException(
            422, "Confirm paid inference and sending this task to the selected provider"
        )
    if not agent.enabled:
        raise HTTPException(409, "Agent version is disabled")
    requirements = spec.requirements.model_copy(
        update={"tools": spec.allowed_tools, "tool_permissions": spec.permissions}
    )
    coding = any(s.kind == "coding" for s in spec.workflow.steps)
    kinds = [s.kind for s in spec.workflow.steps]
    if "analytics" in kinds and (payload.input.dataset is None or payload.input.image is not None):
        raise HTTPException(422, "Analytics requires an uploaded dataset")
    if "image" in kinds:
        if payload.input.image is None or payload.input.dataset is not None:
            raise HTTPException(422, "Image generation requires explicit local model settings")
        requirements = requirements.model_copy(
            update={
                "runtimes": [*requirements.runtimes, "image-model:" + payload.input.image.model]
            }
        )
    if not any(k in ("analytics", "report", "image") for k in kinds) and any(
        (
            payload.input.dataset,
            payload.input.analysis,
            payload.input.image,
            payload.input.report_format,
        )
    ):
        raise HTTPException(422, "Data inputs require a data workload agent")
    if not coding and (payload.input.repository_id or payload.input.search_terms):
        raise HTTPException(422, "Repository access and code search require a coding workflow")
    if coding:
        if payload.input.repository_id is None:
            raise HTTPException(422, "An owner-approved repository is required")
        requirements = requirements.model_copy(
            update={
                "runtimes": list(
                    dict.fromkeys(
                        [
                            *requirements.runtimes,
                            CODING_RUNTIME,
                            REPOSITORY_PREFIX + str(payload.input.repository_id),
                        ]
                    )
                )
            }
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
    actor = authenticate(request, session, "human")
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
        "recovery_error": run.recovery_error,
        "state": service.workflow_assignment(
            session, request.app.state.artifacts, job, attempt
        ).state.model_dump(mode="json")
        if attempt
        else None,
    }


@router.get("/workflow/jobs/{job_id}/steps")
def steps(job_id: UUID, request: Request, session: SessionDep) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
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
    actor = authenticate(request, session, "human")
    job = workflow_job(session, job_id, actor.owner_id)
    return [
        service.checkpoint_view(session, job, cp)
        for cp in session.scalars(
            select(Checkpoint).where(Checkpoint.job_id == job.id).order_by(Checkpoint.version)
        )
    ]


@router.get("/workflow/jobs/{job_id}/result")
def result(job_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    job = workflow_job(session, job_id, actor.owner_id)
    attempt = current_attempt(session, job)
    final: object = None
    output_error: str | None = None
    if job.status == "COMPLETED":
        ref = ArtifactReference.model_validate(job.result_refs["final_output"])
        final = service.load_artifact(session, request.app.state.artifacts, job, ref)
    elif job.cancel_requested_at is None:
        committed = session.scalar(
            select(WorkflowStepRecord)
            .where(WorkflowStepRecord.job_id == job.id, WorkflowStepRecord.status == "COMPLETED")
            .order_by(WorkflowStepRecord.finished_at.desc())
            .limit(1)
        )
        if committed is not None and committed.output_artifact_id is not None:
            row = session.get(Artifact, committed.output_artifact_id)
            if row is not None:
                try:
                    final = service.load_artifact(
                        session, request.app.state.artifacts, job, service.reference(row)
                    )
                except HTTPException as error:
                    if error.status_code != 503:
                        raise
                    output_error = "Committed output is unavailable or failed integrity validation"
    return {
        "job_id": str(job.id),
        "status": job.status,
        "result": job.result_refs or None,
        "output": final,
        "output_error": output_error,
        "partial": final is not None and job.status != "COMPLETED",
        "error": attempt.error if attempt else None,
    }


@router.get("/workflow/jobs/{job_id}/artifacts/{artifact_id}")
def artifact(job_id: UUID, artifact_id: UUID, request: Request, session: SessionDep) -> object:
    actor = authenticate(request, session, "human")
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
