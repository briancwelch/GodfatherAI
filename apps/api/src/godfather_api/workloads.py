"""Workspace-scoped workload submission, real availability and durable downloads."""

import base64
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Request, Response
from godfather_contracts import Contract
from godfather_contracts.agents import (
    AgentCreate,
    AgentDefinition,
    WorkflowInput,
    WorkflowSubmission,
)
from godfather_contracts.jobs import JobView
from godfather_contracts.workloads import WorkloadOutput
from pydantic import Field
from sqlalchemy import select

from godfather_api.agents import create_agent, submit_workflow
from godfather_api.jobs import authorized_job
from godfather_api.models import Agent, Artifact, Job, Node, Workspace
from godfather_api.nodes import SessionDep, authenticate, node_view
from godfather_api.scheduler import permitted, workspace_access
from godfather_api.workflow_service import agent_view, load_artifact, reference

router = APIRouter(prefix="/api/v1/workloads")


class Submission(Contract):
    workspace_id: UUID
    kind: Literal["analytics", "report", "image"]
    input: WorkflowInput
    ram_bytes: int = Field(default=512 * 1024**2, ge=512 * 1024**2, le=2**40)
    gpu_memory_bytes: int = Field(default=0, ge=0, le=2**40)


def template(
    kind: str, ram_bytes: int = 512 * 1024**2, gpu_memory_bytes: int = 0
) -> AgentDefinition:
    image = kind == "image"
    stages = ["image"] if image else ["analytics", "report"] if kind == "report" else ["analytics"]
    return AgentDefinition.model_validate(
        {
            "name": "Local images"
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
                "runtimes": ["local-images-v1" if image else "data-workloads-v1"],
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
    nodes = []
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
        online = view.state == "online" and view.workflow_protocol_version == 1
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
            }
        )
    return {
        "nodes": nodes,
        "dataset_limit_bytes": 1024 * 1024,
        "formats": ["html", "markdown", "csv", "xlsx"],
        "image_backends": ["automatic1111"],
        "cloud_images": False,
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
    spec = template(payload.kind, payload.ram_bytes, payload.gpu_memory_bytes)
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
