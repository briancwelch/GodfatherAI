"""Authenticated workspace-scoped synthetic jobs and fenced worker reports."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer
from godfather_contracts import ModelDeployment
from godfather_contracts.agents import WorkflowResult
from godfather_contracts.execution import AttemptIdentity
from godfather_contracts.inference import MAX_TEXT, InferenceInput, InferenceResult
from godfather_contracts.jobs import (
    Assignment,
    AttemptView,
    EventView,
    JobPoll,
    JobReport,
    JobSubmission,
    JobView,
    PollResponse,
    ReportResponse,
    SyntheticResult,
)
from godfather_contracts.model_management import (
    INSTALL_RUNTIME,
    ModelInstallInput,
    ModelInstallResult,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from godfather_api import workflow_service
from godfather_api.models import Attempt, Event, Job, Node, WorkflowRun, Workspace, WorkspaceMember
from godfather_api.nodes import SessionDep, authenticate, node_view
from godfather_api.scheduler import (
    ACTIVE,
    TERMINAL,
    finish_failure,
    job_event,
    permitted,
    workspace_access,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])


def current_attempt(session: Session, job: Job) -> Attempt | None:
    return session.scalar(
        select(Attempt).where(Attempt.job_id == job.id, Attempt.number == job.attempt_count)
    )


def view(session: Session, job: Job) -> JobView:
    attempt = current_attempt(session, job)
    return JobView.model_validate(
        {
            **{
                key: getattr(job, key)
                for key in (
                    "id",
                    "owner_id",
                    "workspace_id",
                    "type",
                    "status",
                    "priority",
                    "requirements",
                    "timeout_seconds",
                    "assigned_node_id",
                    "attempt_count",
                    "fencing_token",
                    "checkpoint_ref",
                    "cancel_requested_at",
                    "next_run_at",
                    "created_at",
                )
            },
            "input": job.input_refs,
            "retry": {"limit": job.retry_limit, "backoff_seconds": job.retry_backoff_seconds},
            "result": job.result_refs or None,
            "current_attempt_id": attempt.id if attempt else None,
        }
    )


def authorized_job(session: Session, job_id: UUID, actor_id: UUID, lock: bool = False) -> Job:
    query = select(Job).where(Job.id == job_id)
    job = session.scalar(query.with_for_update() if lock else query)
    if job is None or not workspace_access(session, actor_id, job.workspace_id):
        raise HTTPException(404, "Job not found in an authorized workspace")
    if not session.info.get("test") and job.type.startswith("synthetic."):
        raise HTTPException(404, "Test job unavailable in live mode")
    return job


@router.post("/jobs", response_model=JobView, status_code=201)
def submit(payload: JobSubmission, request: Request, session: SessionDep) -> JobView:
    actor = authenticate(request, session, "human")
    if not session.info.get("test") and payload.type.startswith("synthetic."):
        raise HTTPException(403, "Synthetic jobs are restricted to isolated tests")
    if not workspace_access(session, actor.owner_id, payload.workspace_id):
        raise HTTPException(404, "Workspace not found or permission denied")
    selection = payload.requirements.model_selection
    if (
        selection
        and selection.provider in ("openai", "anthropic")
        and (not selection.connection_id or not selection.paid_consent)
    ):
        raise HTTPException(
            422, "Explicit provider connection and paid data-egress consent are required"
        )
    if selection and selection.connection_id and payload.retry.limit:
        raise HTTPException(
            422, "Automatic paid retries are disabled pending billing reconciliation"
        )
    job = Job(
        owner_id=actor.owner_id,
        workspace_id=payload.workspace_id,
        type=payload.type,
        requirements=payload.requirements.model_dump(mode="json"),
        input_refs=payload.input.model_dump(mode="json"),
        priority=payload.priority,
        timeout_seconds=payload.timeout_seconds,
        retry_limit=payload.retry.limit,
        retry_backoff_seconds=payload.retry.backoff_seconds,
    )
    session.add(job)
    session.flush()
    job_event(session, job, "submitted", datetime.now(UTC), actor_id=actor.owner_id)
    return view(session, job)


@router.get("/jobs", response_model=list[JobView])
def list_jobs(
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobView]:
    actor = authenticate(request, session, "human")
    memberships = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == actor.owner_id
    )
    query = (
        select(Job)
        .join(Workspace, Job.workspace_id == Workspace.id)
        .where(or_(Workspace.owner_id == actor.owner_id, Job.workspace_id.in_(memberships)))
    )
    if not session.info.get("test"):
        query = query.where(~Job.type.like("synthetic.%"))
    return [
        view(session, job)
        for job in session.scalars(
            query.order_by(Job.created_at, Job.id).limit(limit).offset(offset)
        )
    ]


@router.get("/jobs/{job_id}", response_model=JobView)
def inspect_job(job_id: UUID, request: Request, session: SessionDep) -> JobView:
    actor = authenticate(request, session, "human")
    return view(session, authorized_job(session, job_id, actor.owner_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobView)
def cancel_job(job_id: UUID, request: Request, session: SessionDep) -> JobView:
    actor = authenticate(request, session, "human")
    job = authorized_job(session, job_id, actor.owner_id, True)
    workspace = session.get(Workspace, job.workspace_id)
    membership = session.get(WorkspaceMember, (job.workspace_id, actor.owner_id))
    if (
        job.owner_id != actor.owner_id
        and (workspace is None or workspace.owner_id != actor.owner_id)
        and (membership is None or membership.role != "admin")
    ):
        raise HTTPException(403, "Only the job owner or workspace administrator may cancel")
    if job.status in TERMINAL or job.cancel_requested_at is not None:
        return view(session, job)
    now = datetime.now(UTC)
    job.cancel_requested_at = now
    attempt = current_attempt(session, job)
    job_event(session, job, "cancellation_requested", now, attempt, actor_id=actor.owner_id)
    if job.status != "RUNNING":
        job.status, job.assigned_node_id, job.next_run_at = "CANCELLED", None, None
        if attempt is not None and attempt.status in ACTIVE:
            attempt.status, attempt.finished_at = "CANCELLED", now
        job_event(session, job, "cancelled", now, attempt, actor_id=actor.owner_id)
        workflow_service.end_attempt(session, job, attempt, "cancelled")
    session.flush()
    return view(session, job)


@router.post("/jobs/{job_id}/retry", response_model=JobView)
def retry_job(job_id: UUID, request: Request, session: SessionDep) -> JobView:
    actor = authenticate(request, session, "human")
    job = authorized_job(session, job_id, actor.owner_id, True)
    workspace = session.get(Workspace, job.workspace_id)
    membership = session.get(WorkspaceMember, (job.workspace_id, actor.owner_id))
    if (
        job.owner_id != actor.owner_id
        and (workspace is None or workspace.owner_id != actor.owner_id)
        and (membership is None or membership.role != "admin")
    ):
        raise HTTPException(403, "Only the job owner or workspace administrator may retry")
    previous = current_attempt(session, job)
    if job.type == "result.action":
        raise HTTPException(
            409, "Result actions cannot be replayed; inspect the project and its apply receipt"
        )
    selection = view(session, job).requirements.model_selection
    if selection and selection.connection_id:
        raise HTTPException(
            409,
            "Paid attempts require billing reconciliation; submit a separately authorized new job",
        )
    if (
        job.status != "FAILED"
        or previous is None
        or job.cancel_requested_at is not None
        or job.attempt_count >= 11
        or previous.error.get("code")
        not in (
            "lease_expired",
            "timeout",
            "transient_error",
            "provider_unavailable",
            "provider_timeout",
            "rate_limited",
            "step_timeout",
        )
    ):
        raise HTTPException(409, "This job is not eligible for safe bounded retry")
    run = session.get(WorkflowRun, job.id)
    if run is not None:
        if run.status == "REVIEW_REQUIRED":
            raise HTTPException(409, "Workflow recovery requires review")
        run.status = "INTERRUPTED"
    job.status, job.next_run_at = "PENDING", None
    job_event(
        session, job, "manual_retry_requested", datetime.now(UTC), previous, actor_id=actor.owner_id
    )
    session.flush()
    return view(session, job)


@router.get("/jobs/{job_id}/attempts", response_model=list[AttemptView])
def attempts(job_id: UUID, request: Request, session: SessionDep) -> list[AttemptView]:
    actor = authenticate(request, session, "human")
    authorized_job(session, job_id, actor.owner_id)
    return [
        AttemptView.model_validate(a, from_attributes=True)
        for a in session.scalars(
            select(Attempt).where(Attempt.job_id == job_id).order_by(Attempt.number)
        )
    ]


@router.get("/jobs/{job_id}/events", response_model=list[EventView])
def events(
    job_id: UUID,
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EventView]:
    actor = authenticate(request, session, "human")
    authorized_job(session, job_id, actor.owner_id)
    return [
        EventView.model_validate(e, from_attributes=True)
        for e in session.scalars(
            select(Event)
            .where(Event.job_id == job_id)
            .order_by(Event.created_at, Event.id)
            .limit(limit)
            .offset(offset)
        )
    ]


def worker_node(node_id: UUID, payload: JobPoll, request: Request, session: Session) -> Node:
    credential = authenticate(request, session, "worker")
    if payload.job_protocol_version != 1:
        raise HTTPException(426, "Execution protocol v1 is required")
    if credential.node_id != node_id:
        raise HTTPException(403, "Credential is scoped to another node")
    # Serialize worker mutations without blocking FK KEY SHARE checks from job
    # cancellation audit inserts. Node identity keys are immutable on this path.
    node = session.scalar(select(Node).where(Node.id == node_id).with_for_update(key_share=True))
    if node is None or node.session_id != payload.session_id:
        raise HTTPException(409, "Register this worker session first")
    if node.state == "disabled":
        raise HTTPException(403, "Node is disabled")
    synthetic = (
        node.runtimes.get("job_protocol_version") == 1
        and node.resources.get("source") == "simulated"
    )
    if (
        not synthetic
        and node.runtimes.get("inference_protocol_version") != 1
        and node.runtimes.get("workflow_protocol_version") != 1
    ):
        raise HTTPException(403, "Execution requires explicit worker opt-in")
    return node


@router.post("/workers/{node_id}/jobs/poll", response_model=PollResponse)
def poll(node_id: UUID, payload: JobPoll, request: Request, session: SessionDep) -> PollResponse:
    node = worker_node(node_id, payload, request, session)
    # The scheduler alone assigns. Polling never steals a preferred node's work.
    job = session.scalar(
        select(Job)
        .where(Job.assigned_node_id == node.id, Job.status == "ASSIGNED")
        .order_by(Job.created_at, Job.id)
        .with_for_update()
    )
    if job is None:
        from godfather_contracts.providers import ConnectionCheck

        from godfather_api.models import ProviderConnection

        checks = []
        if "provider-connections-v1" in node_view(session, node).runtimes:
            checks = [
                ConnectionCheck(connection_id=c.id, test_id=c.test_id)
                for c in session.scalars(
                    select(ProviderConnection)
                    .where(
                        ProviderConnection.node_id == node.id,
                        ProviderConnection.revoked.is_(False),
                        ProviderConnection.test_id.is_not(None),
                    )
                    .limit(8)
                )
            ]
        return PollResponse(provider_checks=checks)
    attempt = current_attempt(session, job)
    now = datetime.now(UTC)
    if (
        attempt is None
        or attempt.session_id != node.session_id
        or attempt.lease_expires_at <= now
        or not permitted(session, job, node)
    ):
        return PollResponse()
    assert attempt.deadline_at is not None
    return PollResponse(
        assignment=Assignment(
            job=view(session, job),
            attempt_id=attempt.id,
            fencing_token=attempt.fencing_token,
            lease_expires_at=attempt.lease_expires_at,
            deadline_at=attempt.deadline_at,
            deployment=ModelDeployment.model_validate(attempt.result["deployment"])
            if job.type in ("inference.text", "agent.workflow")
            else None,
            workflow=workflow_service.workflow_assignment(
                session, request.app.state.artifacts, job, attempt
            )
            if job.type == "agent.workflow"
            else None,
        )
    )


def lock_execution(
    node_id: UUID, job_id: UUID, payload: AttemptIdentity, request: Request, session: Session
) -> tuple[Node, Job, Attempt]:
    node = worker_node(node_id, payload, request, session)
    job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    attempt = current_attempt(session, job) if job is not None else None
    now = datetime.now(UTC)
    if (
        job is None
        or attempt is None
        or job.status not in ACTIVE
        or attempt.status not in ACTIVE
        or job.assigned_node_id != node.id
        or attempt.node_id != node.id
        or attempt.session_id != payload.session_id
        or attempt.id != payload.attempt_id
        or attempt.fencing_token != payload.fencing_token
        or job.fencing_token != payload.fencing_token
        or attempt.lease_expires_at <= now
        or attempt.deadline_at is None
        or attempt.deadline_at <= now
    ):
        raise HTTPException(409, "Attempt is stale, expired or no longer owns this job")
    if not permitted(session, job, node):
        raise HTTPException(409, "Workspace or node-owner execution permission was withdrawn")
    return node, job, attempt


@router.post("/workers/{node_id}/jobs/{job_id}/report", response_model=ReportResponse)
def report(
    node_id: UUID, job_id: UUID, payload: JobReport, request: Request, session: SessionDep
) -> ReportResponse:
    node, job, attempt = lock_execution(node_id, job_id, payload, request, session)
    assert attempt.deadline_at is not None
    now = datetime.now(UTC)
    inference = job.type == "inference.text"
    if inference:
        if node.runtimes.get("inference_protocol_version") != 1:
            raise HTTPException(403, "Inference requires explicit worker opt-in")
    elif job.type == "agent.workflow":
        if node.runtimes.get("workflow_protocol_version") != 1:
            raise HTTPException(403, "Workflow execution requires explicit worker opt-in")
    elif job.type == "model.install":
        if INSTALL_RUNTIME not in node_view(session, node).runtimes:
            raise HTTPException(403, "Node owner has not enabled model installation")
    elif job.type == "result.action":
        pass  # lock_execution rechecks exact node, project, runtime and local owner consent.
    elif (
        node.runtimes.get("job_protocol_version") != 1
        or node.resources.get("source") != "simulated"
    ):
        raise HTTPException(403, "Synthetic execution requires simulated worker opt-in")
    cancelled = job.cancel_requested_at is not None
    if cancelled and payload.action in ("complete", "fail", "cancelled", "start"):
        job.status, job.assigned_node_id = "CANCELLED", None
        attempt.status, attempt.finished_at = "CANCELLED", now
        job_event(session, job, "cancelled", now, attempt)
        workflow_service.end_attempt(session, job, attempt, "cancelled")
    elif payload.action == "ack":
        if job.status != "ASSIGNED":
            raise HTTPException(409, "Assignment was already started")
        if attempt.acknowledged_at is None:
            attempt.acknowledged_at = now
            job_event(session, job, "acknowledged", now, attempt)
    elif payload.action == "start":
        if job.status != "ASSIGNED" or attempt.acknowledged_at is None:
            raise HTTPException(409, "Acknowledge assignment before starting")
        job.status, attempt.status, attempt.started_at = "RUNNING", "RUNNING", now
        job_event(session, job, "started", now, attempt)
        if job.type == "agent.workflow":
            workflow_service.started(session, request.app.state.artifacts, job, attempt)
    elif payload.action == "output":
        if not inference or job.status != "RUNNING" or payload.output is None:
            raise HTTPException(422, "Running inference and a bounded output update are required")
        if not InferenceInput.model_validate(job.input_refs).stream:
            raise HTTPException(422, "This job did not request streaming output")
        # Cancellation cannot publish more private partial output.
        if not cancelled:
            previous = attempt.result
            stored_sequence = previous.get("sequence", 0)
            sequence = stored_sequence if isinstance(stored_sequence, int) else 0
            chunk = payload.output
            if chunk.sequence == sequence:
                if previous.get("last_text") != chunk.text:
                    raise HTTPException(409, "Output sequence was already used")
            elif chunk.sequence == sequence + 1:
                text = str(previous.get("text", "")) + chunk.text
                if len(text) > MAX_TEXT:
                    raise HTTPException(422, "Inference output limit exceeded")
                attempt.result = {
                    **previous,
                    "text": text,
                    "sequence": chunk.sequence,
                    "last_text": chunk.text,
                }
            else:
                raise HTTPException(409, "Output must append the next sequence")
    elif payload.action in ("renew", "progress"):
        if job.status != "RUNNING":
            raise HTTPException(409, "Start execution before reporting progress or renewing")
        if payload.action == "progress" and payload.progress is None:
            raise HTTPException(422, "Progress percentage is required")
        attempt.lease_expires_at = min(
            attempt.deadline_at,
            now + timedelta(seconds=request.app.state.settings.execution_lease_seconds),
        )
        job_event(session, job, "lease_renewed", now, attempt)
        if payload.action == "progress":
            job_event(session, job, "progress", now, attempt, {"percent": payload.progress})
    elif payload.action == "complete":
        if job.status != "RUNNING" or payload.result is None:
            raise HTTPException(422, "Running execution and a synthetic result are required")
        if inference:
            if not isinstance(payload.result, InferenceResult):
                raise HTTPException(422, "An inference result is required")
            if payload.result.deployment.model_dump(mode="json") != attempt.result.get(
                "deployment"
            ):
                raise HTTPException(409, "Result must use the assigned model deployment")
            if not payload.result.text.startswith(str(attempt.result.get("text", ""))):
                raise HTTPException(409, "Final text must extend the streamed prefix")
        elif job.type == "agent.workflow":
            if not isinstance(payload.result, WorkflowResult):
                raise HTTPException(422, "A structured workflow result is required")
            workflow_service.completed(
                session, request.app.state.artifacts, job, attempt, payload.result
            )
        elif job.type == "model.install":
            expected = ModelInstallInput.model_validate(job.input_refs)
            if (
                not isinstance(payload.result, ModelInstallResult)
                or payload.result.identifier != expected.identifier
                or payload.result.provider_id != expected.provider_id
            ):
                raise HTTPException(
                    422, "Installation result must match the approved model/provider"
                )
        elif job.type == "result.action":
            from godfather_contracts.result_actions import ResultActionInput, ResultActionOutput

            expected_action = ResultActionInput.model_validate(job.input_refs)
            if (
                not isinstance(payload.result, ResultActionOutput)
                or payload.result.source_job_id != expected_action.source_job_id
            ):
                raise HTTPException(422, "Result must match the approved action")
            if (
                payload.result.state == "applied"
                and session.scalar(
                    select(Event.id).where(
                        Event.job_id == job.id, Event.type == "job.result_action_started"
                    )
                )
                is None
            ):
                raise HTTPException(409, "Apply must be authorized before publishing success")
        elif not isinstance(payload.result, SyntheticResult):
            raise HTTPException(422, "A synthetic result is required")
        if attempt.lease_expires_at <= datetime.now(UTC) or attempt.deadline_at <= datetime.now(
            UTC
        ):
            raise HTTPException(409, "Attempt expired before the result could commit")
        attempt.result = payload.result.model_dump(mode="json")
        job.result_refs = attempt.result
        job.status, job.assigned_node_id = "COMPLETED", None
        attempt.status, attempt.finished_at = "COMPLETED", now
        job_event(session, job, "completed", now, attempt)
    elif payload.action == "fail":
        if job.status != "RUNNING" or payload.error_code is None:
            raise HTTPException(422, "Running execution and a classified error are required")
        if (
            not inference
            and job.type not in ("agent.workflow", "model.install", "result.action")
            and payload.error_code not in ("transient_error", "permanent_error")
        ):
            raise HTTPException(422, "Synthetic failures require synthetic error codes")
        finish_failure(
            session,
            job,
            attempt,
            now,
            payload.error_code,
            payload.error_code
            in (
                "transient_error",
                "provider_unavailable",
                "provider_timeout",
                "rate_limited",
                "step_timeout",
            ),
        )
    else:
        raise HTTPException(409, "There is no cancellation request to acknowledge")
    return ReportResponse(
        status=job.status, cancel_requested=cancelled, lease_expires_at=attempt.lease_expires_at
    )
