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
from godfather_contracts import Contract
from godfather_contracts.execution import Requirements
from godfather_contracts.jobs import InferenceSubmission, JobView
from godfather_contracts.model_management import (
    INSTALL_RUNTIME,
    MODEL_CATALOG,
    PROVIDER_RUNTIME_PREFIX,
    SETUP_RUNTIME,
    ModelInstallInput,
    ModelInstallRequest,
)
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from godfather_api.jobs import authorized_job, current_attempt, submit
from godfather_api.models import (
    AccessCredential,
    Attempt,
    Job,
    Node,
    User,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import SessionDep, authenticate, connection_at, node_view
from godfather_api.scheduler import job_event, permitted, workspace_access

router = APIRouter(prefix="/api/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])


@router.get("/models/install-options")
def install_options(workspace_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    workspace_permission(session, workspace_id, actor.owner_id)
    result = []
    for node in session.scalars(
        select(Node).where(Node.owner_id == actor.owner_id, Node.session_id.is_not(None))
    ):
        view = node_view(session, node)
        providers = [
            r.removeprefix(PROVIDER_RUNTIME_PREFIX)
            for r in view.runtimes
            if r.startswith(PROVIDER_RUNTIME_PREFIX)
        ]
        healthy = (
            node.state == "online"
            and connection_at(node.last_heartbeat_at, datetime.now(UTC), request.app.state.settings)
            == "online"
        )
        result.append(
            {
                "node_id": str(node.id),
                "name": node.name,
                "os": node.os,
                "available": healthy and INSTALL_RUNTIME in view.runtimes and bool(providers),
                "providers": providers,
                "runtime_setup": SETUP_RUNTIME in view.runtimes,
                "runtime_ready": "ollama" in view.runtimes
                or any(m.provider == "ollama" for m in view.model_deployments),
                "installed_models": [
                    {"identifier": m.identifier, "provider_id": m.provider_id}
                    for m in view.model_deployments
                    if m.provider == "ollama"
                ],
                "reason": "Ready"
                if healthy and INSTALL_RUNTIME in view.runtimes and providers
                else "Owner must enable model downloads on an online worker",
            }
        )
    return {
        "nodes": result,
        "catalog": MODEL_CATALOG,
        "models": models(workspace_id, request, session, 200, 0, include_restricted=True),
    }


@router.post("/models/install", response_model=JobView, status_code=201)
def install_model(payload: ModelInstallRequest, request: Request, session: SessionDep) -> JobView:
    from godfather_api.jobs import view

    actor = authenticate(request, session, "human")
    from godfather_api.scheduler import lock_workspace

    lock_workspace(session, payload.workspace_id)
    workspace_permission(session, payload.workspace_id, actor.owner_id)
    node = session.scalar(
        select(Node)
        .where(Node.id == payload.node_id, Node.owner_id == actor.owner_id)
        .with_for_update()
    )
    if node is None:
        raise HTTPException(404, "Owned worker not found")
    if payload.identifier not in {m["identifier"] for m in MODEL_CATALOG}:
        raise HTTPException(422, "Choose a supported model from the download catalog")
    runtime = PROVIDER_RUNTIME_PREFIX + payload.provider_id
    node_spec = node_view(session, node)
    if INSTALL_RUNTIME not in node_spec.runtimes or runtime not in node_spec.runtimes:
        raise HTTPException(409, "The node owner must opt in to model installation on this worker")
    if payload.install_runtime and (
        SETUP_RUNTIME not in node_spec.runtimes or payload.provider_id != "local-ollama"
    ):
        raise HTTPException(409, "Approve Ollama runtime setup locally in Consigliere first")
    if any(
        m.identifier == payload.identifier and m.provider_id == payload.provider_id
        for m in node_spec.model_deployments
    ):
        raise HTTPException(
            409, "This model is already installed; select it from the model directory"
        )
    if session.scalar(
        select(Job.id).where(
            Job.type == "model.install",
            Job.status.in_(("PENDING", "ASSIGNED", "RUNNING", "RETRY_WAIT")),
            Job.input_refs["node_id"].astext == str(node.id),
            Job.input_refs["provider_id"].astext == payload.provider_id,
            Job.input_refs["identifier"].astext == payload.identifier,
        )
    ):
        raise HTTPException(409, "This model already has an active installation request")
    job = Job(
        owner_id=actor.owner_id,
        workspace_id=payload.workspace_id,
        type="model.install",
        requirements=Requirements(
            runtimes=[INSTALL_RUNTIME, runtime]
            + ([SETUP_RUNTIME] if payload.install_runtime else [])
        ).model_dump(mode="json"),
        input_refs=ModelInstallInput(
            node_id=node.id,
            provider_id=payload.provider_id,
            identifier=payload.identifier,
            install_runtime=payload.install_runtime,
        ).model_dump(mode="json"),
        timeout_seconds=3600,
        retry_limit=0,
    )
    if not permitted(session, job, node):
        raise HTTPException(403, "Worker contribution or workspace access is unavailable")
    session.add(job)
    session.flush()
    job_event(session, job, "submitted", datetime.now(UTC), actor_id=actor.owner_id)
    return view(session, job)


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
    include_restricted: bool = False,
) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    workspace_permission(session, workspace_id, actor.owner_id)
    workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    membership = session.get(WorkspaceMember, (workspace_id, actor.owner_id))
    can_enable = workspace.owner_id == actor.owner_id or bool(
        membership and membership.role == "admin"
    )
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
            billing_selection = None
            if deployment.connection_id is not None:
                from godfather_contracts import ModelSelection

                from godfather_api.provider_connections import selection_visible

                billing_selection = selection_visible(
                    session,
                    ModelSelection(
                        identifier=deployment.identifier,
                        provider=deployment.provider,
                        connection_id=deployment.connection_id,
                        paid_consent=True,
                    ),
                    actor.owner_id,
                    workspace_id,
                    node,
                )
                if billing_selection is None:
                    continue
            workspace_allowed = (
                workspace.allowed_models is None
                or deployment.identifier in workspace.allowed_models
            )
            if not workspace_allowed and not include_restricted:
                continue
            if not session.info.get("test") and node.resources.get("source") != "physical":
                continue
            result.append(
                {
                    "node_id": str(node.id),
                    "owner_id": str(node.owner_id),
                    "node_name": node.name,
                    "state": node.state,
                    "workspace_allowed": workspace_allowed,
                    "can_enable": can_enable,
                    "worker_available": healthy,
                    "available": healthy
                    and workspace_allowed
                    and deployment.available
                    and view.inference_protocol_version == 1,
                    "deployment": deployment.model_dump(mode="json"),
                    "grant_id": str(billing_selection.grant_id)
                    if billing_selection and billing_selection.grant_id
                    else None,
                }
            )
    return result[offset : offset + limit]


class ModelWorkspaceAccess(Contract):
    workspace_id: UUID
    node_id: UUID
    provider_id: str = Field(min_length=1, max_length=100)
    identifier: str = Field(min_length=1, max_length=255)


@router.post("/models/workspace-access")
def enable_workspace_model(
    payload: ModelWorkspaceAccess, request: Request, session: SessionDep
) -> dict[str, bool]:
    from godfather_api.agents import manage_workspace
    from godfather_api.authentication import audit
    from godfather_api.scheduler import lock_workspace

    actor = authenticate(request, session, "human")
    lock_workspace(session, payload.workspace_id)
    manage_workspace(session, payload.workspace_id, actor.owner_id)
    workspace = session.get(Workspace, payload.workspace_id)
    assert workspace is not None
    visible = models(
        payload.workspace_id, request, session, 200, 0, payload.node_id, include_restricted=True
    )
    if not any(
        isinstance(row["deployment"], dict)
        and row["deployment"]["identifier"] == payload.identifier
        and row["deployment"]["provider_id"] == payload.provider_id
        for row in visible
    ):
        raise HTTPException(
            404, "Model is not advertised by an authorized worker or API connection"
        )
    if workspace.allowed_models is not None and payload.identifier not in workspace.allowed_models:
        if len(workspace.allowed_models) >= 64:
            raise HTTPException(409, "Workspace model limit reached; review workspace permissions")
        workspace.allowed_models = [*workspace.allowed_models, payload.identifier]
        audit(
            session,
            "workspace_model_enabled",
            actor.owner_id,
            payload.workspace_id,
            workspace_id=payload.workspace_id,
            metadata={"identifier": payload.identifier},
        )
    return {"enabled": True}


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


def snapshot(session: Session, job: Job, *, include_partial: bool = False) -> dict[str, object]:
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
        "partial_text": attempt.result.get("text", "")
        if (
            include_partial
            and attempt
            and job.status == "FAILED"
            and job.cancel_requested_at is None
        )
        else "",
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
    actor = authenticate(request, session, "human")
    return snapshot(session, inference_job(session, job_id, actor.owner_id))


@router.get("/inference/jobs/{job_id}/stream")
def stream(job_id: UUID, request: Request, session: SessionDep) -> StreamingResponse:
    actor = authenticate(request, session, "human")
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
                    current_actor = authenticate(request, fresh, "human")
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
    actor = authenticate(request, session, "human")
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
