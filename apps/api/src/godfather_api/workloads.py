"""Workspace-scoped workload submission, real availability and durable downloads."""

import base64
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Request, Response
from godfather_contracts import Contract, ModelSelection
from godfather_contracts.agents import (
    AgentCreate,
    AgentDefinition,
    WorkflowInput,
    WorkflowSubmission,
)
from godfather_contracts.jobs import JobView
from godfather_contracts.workloads import CLOUD_IMAGE_RUNTIME, WorkloadOutput
from pydantic import Field
from sqlalchemy import select

from godfather_api.agents import create_agent, submit_workflow
from godfather_api.jobs import authorized_job
from godfather_api.models import Agent, Artifact, Job, Node, Workspace, WorkspaceMember
from godfather_api.nodes import SessionDep, authenticate, node_view
from godfather_api.scheduler import permitted, workspace_access
from godfather_api.workflow_service import agent_view, load_artifact, reference

router = APIRouter(prefix="/api/v1/workloads")


class Submission(Contract):
    workspace_id: UUID
    kind: Literal["analytics", "report", "image"]
    input: WorkflowInput
    connection_id: UUID | None = None
    paid_consent: bool = False
    ram_bytes: int = Field(default=512 * 1024**2, ge=512 * 1024**2, le=2**40)
    gpu_memory_bytes: int = Field(default=0, ge=0, le=2**40)


def template(
    kind: str,
    ram_bytes: int = 512 * 1024**2,
    gpu_memory_bytes: int = 0,
    selection: ModelSelection | None = None,
) -> AgentDefinition:
    image = kind == "image"
    stages = ["image"] if image else ["analytics", "report"] if kind == "report" else ["analytics"]
    return AgentDefinition.model_validate(
        {
            "name": (
                f"Cloud images {selection.provider} {selection.identifier} "
                f"{selection.connection_id}"
                if selection
                else "Local images"
            )
            if image
            else "Analytics and reporting"
            if kind == "report"
            else "Dataset analytics",
            "description": "Built-in Phase 12 workload v1; fixed, bounded worker execution.",
            "requirements": {
                "capabilities": ["images"]
                if image
                else ["analytics", "reporting"]
                if kind == "report"
                else ["analytics"],
                "runtimes": [
                    CLOUD_IMAGE_RUNTIME
                    if selection
                    else "local-images-v1"
                    if image
                    else "data-workloads-v1"
                ],
                "model_selection": selection.model_dump(mode="json") if selection else None,
                "ram_bytes": ram_bytes,
                "gpu_memory_bytes": gpu_memory_bytes,
            },
            "permissions": ["images.generate" if image else "data.analyze"],
            "workflow": {
                "id": str(uuid5(NAMESPACE_URL, "godfather:workloads:v1:" + kind)),
                "steps": [
                    {
                        "id": stage,
                        "kind": stage,
                        "output_schema": "workload",
                        "input_step": "analytics" if stage == "report" else None,
                        "timeout_seconds": 600 if image else 120,
                    }
                    for stage in stages
                ],
            },
            "retry": {"limit": 0 if image else 2, "backoff_seconds": 2},
            "timeout_seconds": 900 if image else 300,
        }
    )


@router.get("/options")
def options(workspace_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found")
    workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    membership = session.get(WorkspaceMember, (workspace_id, actor.owner_id))
    can_enable = workspace.owner_id == actor.owner_id or bool(
        membership and membership.role == "admin"
    )
    nodes = []
    cloud_models = []
    restricted_cloud_models = []
    for node in session.scalars(select(Node)):
        candidate = Job(
            owner_id=actor.owner_id,
            workspace_id=workspace_id,
            type="agent.workflow",
            requirements={},
            input_refs={},
        )
        if not permitted(session, candidate, node):
            continue
        view = node_view(session, node)
        from datetime import UTC, datetime

        from godfather_api.nodes import connection_at

        online = (
            view.state == "online"
            and view.workflow_protocol_version == 1
            and connection_at(node.last_heartbeat_at, datetime.now(UTC), request.app.state.settings)
            == "online"
        )
        if CLOUD_IMAGE_RUNTIME in view.runtimes and "images.generate" in view.tool_permissions:
            from godfather_contracts.execution import Requirements

            from godfather_api.provider_connections import allowed

            for model in view.model_deployments:
                if (
                    model.provider not in ("openai", "gemini")
                    or not model.available
                    or not model.connection_id
                    or "image_generation" not in model.operations
                ):
                    continue
                selection = ModelSelection(
                    provider=model.provider,
                    identifier=model.identifier,
                    connection_id=model.connection_id,
                    paid_consent=True,
                    stream=False,
                    required_operations=["image_generation"],
                )
                candidate.requirements = Requirements(model_selection=selection).model_dump(
                    mode="json"
                )
                if not allowed(session, candidate, node):
                    continue
                workspace_allowed = (
                    workspace.allowed_models is None or model.identifier in workspace.allowed_models
                )
                entry = {
                    "node_id": str(node.id),
                    "node_name": node.name,
                    "available": online,
                    "provider": model.provider,
                    "provider_id": model.provider_id,
                    "model": model.identifier,
                    "connection_id": str(model.connection_id),
                    "workspace_allowed": workspace_allowed,
                    "can_enable": can_enable,
                }
                if workspace_allowed and permitted(session, candidate, node):
                    cloud_models.append(entry)
                elif not workspace_allowed:
                    # The initial permission probe and the provider check above still
                    # enforce node-owner contribution and private account-key access.
                    # Show this inventory without authorizing execution or changing policy.
                    restricted_cloud_models.append(entry)
        nodes.append(
            {
                "id": str(node.id),
                "name": node.name,
                "available": online,
                "analytics": "data-workloads-v1" in view.runtimes
                and "data.analyze" in view.tool_permissions,
                "image_models": [
                    r.removeprefix("image-model:")
                    for r in view.runtimes
                    if r.startswith("image-model:")
                ]
                if "images.generate" in view.tool_permissions and "local-images-v1" in view.runtimes
                else [],
                "cloud_image_models": [
                    f"{m['provider']}: {m['model']}"
                    for m in cloud_models
                    if m["node_id"] == str(node.id)
                ],
                "restricted_image_model_count": sum(
                    m["node_id"] == str(node.id) for m in restricted_cloud_models
                ),
            }
        )
    return {
        "nodes": nodes,
        "dataset_limit_bytes": 1024 * 1024,
        "formats": ["html", "markdown", "csv", "xlsx"],
        "image_backends": ["automatic1111", "openai", "gemini"],
        "cloud_images": True,
        "cloud_image_models": cloud_models,
        "restricted_cloud_image_models": restricted_cloud_models,
        "workspace_name": workspace.name,
        "sql_sources": [],
        "sql_note": (
            "Upload authorized structured SQL results as JSON; live SQL conne"
            "ctions are not configured."
        ),
    }


@router.post("/jobs", response_model=JobView, status_code=201)
def submit(payload: Submission, request: Request, session: SessionDep) -> JobView:
    actor = authenticate(request, session, "human")
    from godfather_api.scheduler import lock_workspace

    lock_workspace(session, payload.workspace_id)
    if not workspace_access(session, actor.owner_id, payload.workspace_id):
        raise HTTPException(404, "Workspace not found")
    # Serialize built-in definition creation without mutating existing user agents.
    session.scalar(select(Workspace).where(Workspace.id == payload.workspace_id).with_for_update())
    selection = None
    image = payload.input.image
    if payload.kind == "image" and image and image.backend != "automatic1111":
        if payload.connection_id is None or not payload.paid_consent:
            raise HTTPException(
                422, "Select your cloud connection and confirm provider billing and data sharing"
            )
        from godfather_contracts.providers import ConnectionPolicy

        from godfather_api.models import ProviderConnection

        connection = session.get(ProviderConnection, payload.connection_id)
        if (
            connection is None
            or connection.owner_id != actor.owner_id
            or connection.revoked
            or connection.provider != image.backend
            or connection.account_key_id is None
            or ConnectionPolicy.model_validate(connection.policy).billing != "provider"
        ):
            raise HTTPException(404, "Owned account image connection not found")
        selection = ModelSelection(
            provider=image.backend,
            identifier=image.model,
            connection_id=connection.id,
            paid_consent=True,
            stream=False,
            required_operations=["image_generation"],
        )
    elif payload.connection_id is not None or payload.paid_consent:
        raise HTTPException(422, "Cloud consent and connections require a cloud image workload")
    spec = template(payload.kind, payload.ram_bytes, payload.gpu_memory_bytes, selection)
    spec.name += f" v1 ({payload.ram_bytes}/{payload.gpu_memory_bytes})"
    row = session.scalar(
        select(Agent)
        .where(
            Agent.workspace_id == payload.workspace_id,
            Agent.name == spec.name,
            Agent.deleted_at.is_(None),
        )
        .order_by(Agent.version.desc())
        .limit(1)
    )
    if row is None:
        agent = create_agent(
            AgentCreate(workspace_id=payload.workspace_id, definition=spec), request, session
        )
    else:
        agent = agent_view(row)
        if agent.definition != spec:
            raise HTTPException(
                409, "Built-in workload definition was changed; review it in Agents"
            )
    return submit_workflow(
        WorkflowSubmission(
            agent_id=agent.id,
            agent_version=agent.version,
            workspace_id=payload.workspace_id,
            input=payload.input,
            paid_consent=payload.paid_consent,
        ),
        request,
        session,
    )


@router.get("/jobs/{job_id}/files/{artifact_id}/{index}")
def file(
    job_id: UUID, artifact_id: UUID, index: int, request: Request, session: SessionDep
) -> Response:
    actor = authenticate(request, session, "human")
    job = authorized_job(session, job_id, actor.owner_id)
    row = session.get(Artifact, artifact_id)
    if row is None or row.job_id != job.id:
        raise HTTPException(404, "Artifact not found")
    try:
        output = WorkloadOutput.model_validate(
            load_artifact(session, request.app.state.artifacts, job, reference(row))
        )
        if not 0 <= index < len(output.files):
            raise ValueError("Unknown file")
        download = output.files[index]
    except ValueError:
        raise HTTPException(404, "Download not found") from None
    disposition = "inline" if download.media_type == "image/png" else "attachment"
    return Response(
        base64.b64decode(download.content_base64, validate=True),
        media_type=download.media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{download.filename}"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
