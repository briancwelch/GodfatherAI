"""Explicit owner approval of capability-negotiated actions on immutable results."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from godfather_contracts.agents import ArtifactReference
from godfather_contracts.coding import CodingOutput
from godfather_contracts.execution import AttemptIdentity, Requirements
from godfather_contracts.result_actions import (
    ACTION_RUNTIME,
    PATCH_RUNTIME,
    TARGET_PREFIX,
    ResultActionInput,
    ResultActionRequest,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from godfather_api import jobs, workflow_service
from godfather_api.models import Event, Job, Node
from godfather_api.nodes import SessionDep, authenticate, node_view
from godfather_api.scheduler import job_event, workspace_access

router = APIRouter(prefix="/api/v1")


def coding_output(value: object) -> CodingOutput:
    try:
        return CodingOutput.model_validate(value)
    except ValidationError:
        raise HTTPException(409, "This result does not contain a compatible coding patch") from None


def source_output(
    session: Session, request: Request, action: ResultActionInput, owner: UUID
) -> CodingOutput:
    source = jobs.authorized_job(session, action.source_job_id, owner)
    if source.status != "COMPLETED" or source.owner_id != owner:
        raise HTTPException(409, "Only your completed, reviewed coding results can be applied")
    reference = ArtifactReference.model_validate(source.result_refs.get("final_output"))
    if reference != action.artifact:
        raise HTTPException(409, "The approved result reference changed")
    return coding_output(
        workflow_service.load_artifact(session, request.app.state.artifacts, source, reference)
    )


def can_apply(session: Session, node: Node, owner: UUID, workspace: UUID, repository: UUID) -> bool:
    view = node_view(session, node)
    return (
        node.owner_id == owner
        and workspace_access(session, owner, workspace)
        and {ACTION_RUNTIME, PATCH_RUNTIME, TARGET_PREFIX + str(repository)} <= set(view.runtimes)
        and "coding.workspace" in view.tool_permissions
        and any(
            r.id == repository
            and owner in r.allowed_user_ids
            and workspace in r.allowed_workspace_ids
            for r in view.coding_repositories
        )
    )


@router.post("/jobs/{source_id}/result-actions", status_code=201)
def submit(
    source_id: UUID, payload: ResultActionRequest, request: Request, session: SessionDep
) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    source = jobs.authorized_job(session, source_id, actor.owner_id, lock=True)
    if (
        source.type != "agent.workflow"
        or source.status != "COMPLETED"
        or source.owner_id != actor.owner_id
    ):
        raise HTTPException(403, "Apply requires your own completed coding job")
    reference = ArtifactReference.model_validate(source.result_refs.get("final_output"))
    if reference.id != payload.artifact_id or reference.checksum != payload.checksum:
        raise HTTPException(409, "Refresh and review the current verified result before applying")
    attempt = jobs.current_attempt(session, source)
    node = session.get(Node, attempt.node_id) if attempt else None
    if node is None or node.owner_id != actor.owner_id:
        raise HTTPException(403, "Only the computer's owner may apply to its local project")
    output = coding_output(
        workflow_service.load_artifact(session, request.app.state.artifacts, source, reference)
    )
    if not output.diff or not output.files_changed:
        raise HTTPException(409, "There are no project changes to apply")
    if not can_apply(session, node, actor.owner_id, source.workspace_id, output.repository_id):
        raise HTTPException(
            409,
            "Update this worker and enable applying reviewed changes for this project "
            "in Coding projects, then Resume",
        )
    # Source-row lock serializes double clicks. Never replay uncertain side effects.
    previous = session.scalar(
        select(Job)
        .where(
            Job.type == "result.action", Job.input_refs["source_job_id"].astext == str(source_id)
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    if previous is not None and not (
        previous.status == "COMPLETED" and previous.result_refs.get("state") == "blocked"
    ):
        return {"job_id": str(previous.id), "status": previous.status}
    action = ResultActionInput(
        source_job_id=source.id,
        artifact=reference,
        node_id=node.id,
        repository_id=output.repository_id,
    )
    job = Job(
        owner_id=actor.owner_id,
        workspace_id=source.workspace_id,
        type="result.action",
        input_refs=action.model_dump(mode="json"),
        requirements=Requirements(
            runtimes=[ACTION_RUNTIME, PATCH_RUNTIME, TARGET_PREFIX + str(output.repository_id)],
            tool_permissions=["coding.workspace"],
        ).model_dump(mode="json"),
        timeout_seconds=120,
        retry_limit=0,
    )
    session.add(job)
    session.flush()
    job_event(
        session,
        job,
        "result_action_approved",
        datetime.now(UTC),
        details={
            "source_job_id": str(source.id),
            "artifact_id": str(reference.id),
            "action": action.action,
        },
        actor_id=actor.owner_id,
    )
    return {"job_id": str(job.id), "status": job.status}


def action_execution(
    node_id: UUID, job_id: UUID, payload: AttemptIdentity, request: Request, session: Session
) -> tuple[Job, ResultActionInput]:
    node, job, _ = jobs.lock_execution(node_id, job_id, payload, request, session)
    if (
        job.type != "result.action"
        or job.status != "RUNNING"
        or job.cancel_requested_at is not None
    ):
        raise HTTPException(409, "This result action is not accepting execution")
    action = ResultActionInput.model_validate(job.input_refs)
    if not can_apply(session, node, job.owner_id, job.workspace_id, action.repository_id):
        raise HTTPException(403, "Local project application permission was withdrawn")
    return job, action


@router.post("/workers/{node_id}/jobs/{job_id}/result-action/input")
def action_input(
    node_id: UUID, job_id: UUID, payload: AttemptIdentity, request: Request, session: SessionDep
) -> CodingOutput:
    job, action = action_execution(node_id, job_id, payload, request, session)
    return source_output(session, request, action, job.owner_id)


@router.post("/workers/{node_id}/jobs/{job_id}/result-action/begin")
def begin(
    node_id: UUID, job_id: UUID, payload: AttemptIdentity, request: Request, session: SessionDep
) -> dict[str, bool]:
    job, action = action_execution(node_id, job_id, payload, request, session)
    source_output(session, request, action, job.owner_id)
    if session.scalar(
        select(Event.id).where(Event.job_id == job.id, Event.type == "job.result_action_started")
    ):
        raise HTTPException(
            409,
            "Application was already authorized once; inspect the project rather than replaying",
        )
    job_event(
        session,
        job,
        "result_action_started",
        datetime.now(UTC),
        jobs.current_attempt(session, job),
        {"source_job_id": str(action.source_job_id), "action": action.action},
    )
    return {"authorized": True}
