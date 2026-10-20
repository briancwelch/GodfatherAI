"""Transactional workflow transitions, immutable artifacts and fenced checkpoints."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from godfather_agent_runtime import WorkflowError, state_for
from godfather_agent_runtime.tools import ToolError, authorize, describe, validate_agent
from godfather_agent_runtime.tools import definition as tool_definition
from godfather_contracts import ModelDeployment, NodeView
from godfather_contracts.agents import (
    AgentDefinition,
    AgentView,
    ArtifactReference,
    CheckpointView,
    CompletedStep,
    ModelReference,
    Plan,
    PlanSummary,
    StepOutput,
    TextOutput,
    WorkflowAssignment,
    WorkflowReport,
    WorkflowResult,
    WorkflowState,
)
from godfather_contracts.coding import CODING_RUNTIME, CodingOutput
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from godfather_api.artifacts import ArtifactError, ArtifactStore, encode
from godfather_api.models import (
    Agent,
    Artifact,
    Attempt,
    Checkpoint,
    Job,
    Node,
    WorkflowRun,
    WorkflowStepRecord,
)
from godfather_api.scheduler import job_event


def agent_view(agent: Agent) -> AgentView:
    try:
        definition = AgentDefinition.model_validate(agent.definition)
        validate_agent(definition)
    except (ValidationError, ToolError):
        raise HTTPException(409, "Agent definition is not a supported executable version") from None
    return AgentView(
        id=agent.agent_key,
        version_id=agent.id,
        version=agent.version,
        owner_id=agent.owner_id,
        workspace_id=agent.workspace_id,
        enabled=agent.enabled,
        definition=definition.model_copy(update={"enabled": agent.enabled}),
    )


def eligible(session: Session, job: Job, node: Node, view: NodeView) -> bool:
    if job.type != "agent.workflow":
        return True
    run = session.get(WorkflowRun, job.id)
    agent = session.get(Agent, job.agent_id)
    previous = (
        session.scalar(
            select(Attempt).where(Attempt.job_id == job.id, Attempt.number == job.attempt_count)
        )
        if job.attempt_count
        else None
    )
    if (
        previous is not None
        and previous.error.get("code") in ("lease_expired", "timeout")
        and previous.session_id == node.session_id
    ):
        return False  # A partitioned process cannot reacquire its own expired attempt.
    return (
        run is not None
        and agent is not None
        and agent.enabled
        and view.workflow_protocol_version == 1
        and run.status != "REVIEW_REQUIRED"
    )


def reference(artifact: Artifact) -> ArtifactReference:
    return ArtifactReference(
        id=artifact.id, checksum=artifact.checksum, size_bytes=artifact.size_bytes
    )


def load_artifact(
    session: Session, store: ArtifactStore, job: Job, ref: ArtifactReference
) -> object:
    artifact = session.get(Artifact, ref.id)
    if (
        artifact is None
        or artifact.job_id != job.id
        or artifact.workspace_id != job.workspace_id
        or reference(artifact) != ref
    ):
        raise HTTPException(404, "Artifact not found in this workflow")
    try:
        return json.loads(store.read(ref.id, ref.checksum, ref.size_bytes))
    except (ArtifactError, ValueError):
        raise HTTPException(
            503, "Workflow artifact is unavailable or failed integrity validation"
        ) from None


def save_artifact(
    session: Session, store: ArtifactStore, job: Job, attempt: Attempt, kind: str, value: object
) -> Artifact:
    raw = encode(value)
    artifact = Artifact(
        id=uuid4(),
        owner_id=job.owner_id,
        workspace_id=job.workspace_id,
        job_id=job.id,
        attempt_id=attempt.id,
        kind=kind,
        checksum=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
    )
    try:
        store.write(artifact.id, raw)  # Flush/fsync before a durable database reference exists.
    except ArtifactError:
        raise HTTPException(503, "Workflow artifact could not be durably stored") from None
    session.add(artifact)
    session.flush()
    return artifact


def workflow_assignment(
    session: Session, store: ArtifactStore, job: Job, attempt: Attempt
) -> WorkflowAssignment:
    agent = session.get(Agent, job.agent_id)
    run = session.get(WorkflowRun, job.id)
    if agent is None or run is None or run.agent_id != agent.id:
        raise HTTPException(409, "Workflow metadata is inconsistent")
    view = agent_view(agent)
    if (
        run.workflow_id != view.definition.workflow.id
        or run.workflow_version != view.definition.workflow.version
    ):
        raise HTTPException(409, "Pinned workflow version does not match execution metadata")
    state = WorkflowState(
        job_id=job.id,
        agent_id=agent.agent_key,
        agent_version=agent.version,
        workflow_id=run.workflow_id,
        workflow_version=run.workflow_version,
        attempt_id=attempt.id,
        fencing_token=attempt.fencing_token,
    )
    if run.checkpoint_version:
        checkpoint = session.scalar(
            select(Checkpoint).where(
                Checkpoint.job_id == job.id, Checkpoint.version == run.checkpoint_version
            )
        )
        if (
            checkpoint is None
            or checkpoint.artifact_id is None
            or job.checkpoint_ref != "checkpoint:" + str(checkpoint.id)
        ):
            raise HTTPException(409, "Workflow checkpoint metadata is inconsistent")
        artifact = session.get(Artifact, checkpoint.artifact_id)
        if artifact is None or artifact.checksum != checkpoint.checksum:
            raise HTTPException(409, "Workflow checkpoint artifact metadata is inconsistent")
        try:
            state = WorkflowState.model_validate(
                load_artifact(session, store, job, reference(artifact))
            )
            if (
                state.job_id != job.id
                or state.current_step != run.cursor
                or state.checkpoint_version != run.checkpoint_version
            ):
                raise ValueError("Invalid checkpoint identity")
            previous = state.attempt_id
            failed_attempt = session.scalar(
                select(Attempt).where(
                    Attempt.job_id == job.id, Attempt.number == job.attempt_count - 1
                )
            )
            state = state.model_copy(
                update={
                    "attempt_id": attempt.id,
                    "fencing_token": attempt.fencing_token,
                    "recovery_count": job.attempt_count - 1,
                    "last_error_code": failed_attempt.error.get("code") if failed_attempt else None,
                    "resumed_from_attempt_id": previous
                    if previous != attempt.id
                    else state.resumed_from_attempt_id,
                }
            )
        except (ValidationError, ValueError):
            raise HTTPException(409, "Workflow checkpoint state failed validation") from None
    result = WorkflowAssignment(agent=view, state=state)
    try:
        state_for(result, state)
    except WorkflowError:
        raise HTTPException(
            409, "Checkpoint does not match this immutable workflow version"
        ) from None
    # Verify the entire committed prefix, including artifacts not used by the next step.
    # A corrupt prefix must never become an apparently successful restored workflow.
    for committed_step in state.completed:
        load_artifact(session, store, job, committed_step.output)
    return result


def restoration_ready(session: Session, store: ArtifactStore, job: Job, previous: Attempt) -> bool:
    run = session.get(WorkflowRun, job.id)
    if run is None or run.status == "REVIEW_REQUIRED":
        return False
    try:
        workflow_assignment(session, store, job, previous)
    except HTTPException:
        run.status, run.recovery_error = "REVIEW_REQUIRED", "checkpoint_unavailable_or_invalid"
        event(session, job, previous, "review_required", {"code": run.recovery_error})
        return False
    return True


def event(
    session: Session,
    job: Job,
    attempt: Attempt | None,
    kind: str,
    details: dict[str, object] | None = None,
) -> None:
    run = session.get(WorkflowRun, job.id)
    agent = session.get(Agent, job.agent_id)
    if run is None or agent is None:
        return
    job_event(
        session,
        job,
        "workflow." + kind,
        datetime.now(UTC),
        attempt,
        {
            "workflow_id": str(run.workflow_id),
            "workflow_version": run.workflow_version,
            "agent_id": str(agent.agent_key),
            "agent_version": agent.version,
            "fencing_token": attempt.fencing_token if attempt else job.fencing_token,
            **(details or {}),
        },
        actor_id=job.owner_id,
    )


def started(session: Session, store: ArtifactStore, job: Job, attempt: Attempt) -> None:
    assignment = workflow_assignment(session, store, job, attempt)
    if not assignment.agent.enabled:
        raise HTTPException(403, "Agent version is disabled")
    run = session.get(WorkflowRun, job.id)
    assert run is not None
    run.status = "RUNNING"
    event(
        session,
        job,
        attempt,
        "resumed" if job.attempt_count > 1 else "started",
        {
            "checkpoint_version": assignment.state.checkpoint_version,
            "resumed_from_attempt_id": str(assignment.state.resumed_from_attempt_id)
            if assignment.state.resumed_from_attempt_id
            else None,
        },
    )


def end_attempt(
    session: Session, job: Job, attempt: Attempt | None, code: str, retrying: bool = False
) -> None:
    if job.type != "agent.workflow":
        return
    run = session.get(WorkflowRun, job.id)
    if run is None:
        return
    interrupted = retrying or code in (
        "lease_expired",
        "timeout",
        "provider_unavailable",
        "provider_timeout",
        "transient_error",
    )
    status = "CANCELLED" if code == "cancelled" else "INTERRUPTED" if retrying else "FAILED"
    run.status = status
    agent = session.get(Agent, job.agent_id)
    if (
        code not in ("cancelled",)
        and agent is not None
        and any(s.kind == "coding" for s in agent_view(agent).definition.workflow.steps)
    ):
        run.status = "REVIEW_REQUIRED"
        run.recovery_error = "coding_interruption_requires_review"
    if attempt is not None:
        for record in session.scalars(
            select(WorkflowStepRecord).where(
                WorkflowStepRecord.job_id == job.id,
                WorkflowStepRecord.attempt_id == attempt.id,
                WorkflowStepRecord.status == "RUNNING",
            )
        ):
            record.status = (
                "CANCELLED" if code == "cancelled" else "INTERRUPTED" if interrupted else "FAILED"
            )
            record.error_code, record.finished_at = code, datetime.now(UTC)
            event(
                session,
                job,
                attempt,
                "step." + record.status.lower(),
                {"step_id": record.step_id, "code": code},
            )
    event(
        session,
        job,
        attempt,
        "interrupted" if interrupted else "cancelled" if code == "cancelled" else "failed",
        {"code": code, "retrying": retrying},
    )
    if interrupted and not retrying and code != "cancelled":
        event(session, job, attempt, "failed", {"code": code, "retrying": False})


def validate_tool_policy(agent: AgentDefinition, node: NodeView, tool: object) -> None:
    try:
        if tool is None:
            raise ToolError("Missing tool")
        from godfather_contracts import ToolReference

        authorize(
            ToolReference.model_validate(tool),
            agent,
            node.worker_tools,
            list(node.tool_permissions),
            node.os,
        )
    except ToolError:
        raise HTTPException(403, "Agent or node-owner tool permission is missing") from None


def transition(
    session: Session,
    store: ArtifactStore,
    job: Job,
    attempt: Attempt,
    node: NodeView,
    payload: WorkflowReport,
) -> WorkflowState:
    if job.status != "RUNNING" or job.cancel_requested_at is not None:
        raise HTTPException(409, "Workflow is not accepting step transitions")
    assignment = workflow_assignment(session, store, job, attempt)
    spec, state = assignment.agent.definition, assignment.state
    run = session.get(WorkflowRun, job.id)
    assert run is not None
    if payload.expected_checkpoint_version != state.checkpoint_version:
        # Repeating the last committed write is safe only for the same valid attempt/output.
        if (
            payload.action == "checkpoint"
            and state.completed
            and payload.expected_checkpoint_version == state.checkpoint_version - 1
            and state.completed[-1].step_id == payload.step_id
            and state.completed[-1].attempt_id == attempt.id
            and payload.output is not None
            and encode(load_artifact(session, store, job, state.completed[-1].output))
            == encode(payload.output.model_dump(mode="json"))
        ):
            return state
        raise HTTPException(409, "Checkpoint version is stale")
    if state.current_step >= len(spec.workflow.steps):
        raise HTTPException(409, "All workflow steps are already committed")
    step = spec.workflow.steps[state.current_step]
    if step.id != payload.step_id:
        raise HTTPException(409, "Only the next uncommitted step may transition")
    if step.kind == "tool":
        validate_tool_policy(spec, node, step.tool)
    if step.kind == "coding":
        repository_id = job.input_refs.get("repository_id")
        if (
            CODING_RUNTIME not in node.runtimes
            or "coding.workspace" not in node.tool_permissions
            or not any(
                str(r.id) == repository_id
                and job.owner_id in r.allowed_user_ids
                and job.workspace_id in r.allowed_workspace_ids
                for r in node.coding_repositories
            )
        ):
            raise HTTPException(403, "Coding repository or worker permission was withdrawn")
    record = session.scalar(
        select(WorkflowStepRecord).where(
            WorkflowStepRecord.job_id == job.id,
            WorkflowStepRecord.step_id == step.id,
            WorkflowStepRecord.attempt_id == attempt.id,
        )
    )
    if payload.action == "step_start":
        if not assignment.agent.enabled:
            raise HTTPException(403, "Agent version is disabled")
        if payload.output is not None or payload.usage is not None:
            raise HTTPException(422, "Step start cannot publish output")
        if record is None:
            inputs = {"instruction": "job.input"}
            if step.input_step:
                inputs["prior_output"] = str(state.context[step.input_step].id)
            record = WorkflowStepRecord(
                job_id=job.id,
                attempt_id=attempt.id,
                step_id=step.id,
                input_refs=inputs,
                metadata_refs={
                    "kind": step.kind,
                    "model": attempt.result.get("deployment")
                    if step.kind in ("model", "coding")
                    else None,
                    "tool": step.tool.model_dump(mode="json") if step.tool else None,
                },
            )
            session.add(record)
            event(session, job, attempt, "step.started", {"step_id": step.id})
            event(
                session,
                job,
                attempt,
                "model.requested" if step.kind == "model" else "tool.started",
                {"step_id": step.id},
            )
        return state
    if record is None or record.status != "RUNNING" or payload.output is None:
        raise HTTPException(409, "Start this step before committing its validated output")
    limit = (
        min(step.timeout_seconds, tool_definition(step.tool).timeout_seconds)
        if step.tool
        else step.timeout_seconds
    )
    if record.created_at + timedelta(seconds=limit) <= datetime.now(UTC):
        raise HTTPException(408, "Step execution timeout expired")
    try:
        output: StepOutput
        if step.output_schema == "plan":
            output = Plan.model_validate(payload.output.model_dump())
        elif step.output_schema == "text":
            output = TextOutput.model_validate(payload.output.model_dump())
        elif step.output_schema == "coding":
            output = CodingOutput.model_validate(payload.output.model_dump())
            if str(output.repository_id) != job.input_refs.get("repository_id"):
                raise ValueError("Coding output must match the approved repository")
        else:
            output = PlanSummary.model_validate(payload.output.model_dump())
            source = load_artifact(session, store, job, state.context[str(step.input_step)])
            if output != describe(Plan.model_validate(source)):
                raise ValueError("Tool output differs from its declared deterministic contract")
        if (step.kind in ("model", "coding")) != (payload.usage is not None):
            raise ValueError("Only model steps require usage metadata")
    except (ValidationError, ValueError):
        raise HTTPException(422, "Step output does not satisfy the declared schema") from None
    artifact = save_artifact(
        session, store, job, attempt, "step_output", output.model_dump(mode="json")
    )
    completed = CompletedStep(
        step_id=step.id,
        output=reference(artifact),
        attempt_id=attempt.id,
        fencing_token=attempt.fencing_token,
        model=ModelReference.from_deployment(
            ModelDeployment.model_validate(attempt.result["deployment"])
        )
        if step.kind == "model"
        else None,
        tool=step.tool,
    )
    state = state.model_copy(
        update={
            "completed": state.completed + [completed],
            "context": {**state.context, step.id: completed.output},
            "current_step": state.current_step + 1,
            "checkpoint_version": state.checkpoint_version + 1,
        }
    )
    state = WorkflowState.model_validate(state.model_dump())
    state_artifact = save_artifact(
        session, store, job, attempt, "workflow_state", state.model_dump(mode="json")
    )
    now = datetime.now(UTC)
    if attempt.lease_expires_at <= now or attempt.deadline_at is None or attempt.deadline_at <= now:
        raise HTTPException(409, "Attempt expired before the checkpoint could commit")
    checkpoint = Checkpoint(
        job_id=job.id,
        attempt_id=attempt.id,
        version=state.checkpoint_version,
        format_version=1,
        artifact_ref="artifact:" + str(state_artifact.id),
        artifact_id=state_artifact.id,
        checksum=state_artifact.checksum,
    )
    session.add(checkpoint)
    session.flush()
    record.status, record.output_artifact_id, record.finished_at = (
        "COMPLETED",
        artifact.id,
        datetime.now(UTC),
    )
    record.metadata_refs = {
        **record.metadata_refs,
        "usage": payload.usage.model_dump(mode="json") if payload.usage else None,
    }
    run.cursor, run.checkpoint_version = state.current_step, state.checkpoint_version
    job.checkpoint_ref = "checkpoint:" + str(checkpoint.id)
    event(
        session,
        job,
        attempt,
        "model.completed" if step.kind == "model" else "tool.completed",
        {"step_id": step.id},
    )
    event(
        session,
        job,
        attempt,
        "step.completed",
        {"step_id": step.id, "artifact_id": str(artifact.id)},
    )
    event(
        session,
        job,
        attempt,
        "checkpoint.committed",
        {"step_id": step.id, "version": checkpoint.version, "checkpoint_id": str(checkpoint.id)},
    )
    session.flush()
    return state


def completed(
    session: Session, store: ArtifactStore, job: Job, attempt: Attempt, result: WorkflowResult
) -> None:
    assignment = workflow_assignment(session, store, job, attempt)
    state = assignment.state
    expected = (
        WorkflowResult(
            workflow_id=state.workflow_id,
            workflow_version=state.workflow_version,
            agent_id=state.agent_id,
            agent_version=state.agent_version,
            checkpoint_version=state.checkpoint_version,
            completed_steps=[s.step_id for s in state.completed],
            final_output=state.completed[-1].output,
        )
        if state.completed
        else None
    )
    if state.current_step != len(assignment.agent.definition.workflow.steps) or result != expected:
        raise HTTPException(409, "Commit all declared workflow steps before completing")
    run = session.get(WorkflowRun, job.id)
    assert run is not None
    run.status = "COMPLETED"
    event(session, job, attempt, "completed", {"checkpoint_version": state.checkpoint_version})


def checkpoint_view(session: Session, job: Job, checkpoint: Checkpoint) -> CheckpointView:
    agent = session.get(Agent, job.agent_id)
    run = session.get(WorkflowRun, job.id)
    artifact = session.get(Artifact, checkpoint.artifact_id)
    assert agent is not None and run is not None and artifact is not None
    return CheckpointView(
        id=checkpoint.id,
        version=checkpoint.version,
        job_id=job.id,
        attempt_id=checkpoint.attempt_id,
        artifact=reference(artifact),
        agent_id=agent.agent_key,
        agent_version=agent.version,
        workflow_id=run.workflow_id,
        workflow_version=run.workflow_version,
        created_at=checkpoint.created_at,
    )
