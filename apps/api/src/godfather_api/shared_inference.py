"""One inference request on an owner-configured private multi-device engine.

The external engine implements tensor/pipeline parallelism. The control plane
reserves consenting member computers and fences one ordinary inference attempt.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer
from godfather_contracts import Contract, ModelSelection, SharedInferenceGroup
from godfather_contracts.execution import Requirements
from godfather_contracts.inference import InferenceInput
from godfather_contracts.jobs import InferenceSubmission, JobView
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from godfather_api.models import AccessCredential, Attempt, Job, Node, Workspace, WorkspaceMember
from godfather_api.nodes import SessionDep, authenticate, node_view

router = APIRouter(
    prefix="/api/v1/shared-inference", dependencies=[Depends(HTTPBearer(auto_error=False))]
)


class SharedSubmission(Contract):
    workspace_id: UUID
    group_id: UUID
    prompt: str = Field(min_length=1, max_length=32768)
    wide_area_consent: bool = False


class WorkspaceAccess(Contract):
    workspace_id: UUID
    group_id: UUID


def declared(node: Node) -> list[SharedInferenceGroup]:
    raw = node.runtimes.get("shared_inference_groups", [])
    return [SharedInferenceGroup.model_validate(g) for g in raw] if isinstance(raw, list) else []


def group_permitted(session: Session, job: Job, node: Node) -> bool:
    from godfather_api.scheduler import base_permitted

    if not (job.requirements or {}).get("shared_inference"):
        return True
    group = Requirements.model_validate(job.requirements).shared_inference
    if group is None:
        return True
    from godfather_api.shared_engine_setup import managed_permitted

    if not managed_permitted(session, group):
        return False
    if (
        group.mode == "wide_area"
        and not Requirements.model_validate(job.requirements).wide_area_consent
    ):
        return False
    if job.type != "inference.text" or node.id != group.leader_node_id:
        return False
    selection = Requirements.model_validate(job.requirements).model_selection
    if (
        selection is None
        or selection.identifier != group.model
        or selection.provider != "openai_compatible"
        or selection.connection_id
        or selection.fallback_models
    ):
        return False
    attempt = (
        session.scalar(
            select(Attempt).where(Attempt.job_id == job.id, Attempt.number == job.attempt_count)
        )
        if job.attempt_count and job.status in ("ASSIGNED", "RUNNING")
        else None
    )
    pinned = attempt.result.get("shared_sessions", {}) if attempt else {}
    if not isinstance(pinned, dict):
        return False
    if attempt and set(pinned) != {str(n) for n in group.node_ids}:
        return False
    leader_models = node_view(session, node).model_deployments
    if not any(
        model.shared_inference_group_id == group.id
        and model.identifier == group.model
        and model.provider == "openai_compatible"
        and model.available
        and {"chat", "stream"} <= set(model.operations)
        and (attempt is None or model.model_dump(mode="json") == attempt.result.get("deployment"))
        for model in leader_models
    ):
        return False
    for member in group.node_ids:
        peer = session.get(Node, member)
        if peer is None or group not in declared(peer) or not base_permitted(session, job, peer):
            return False
        if (
            peer.state != "online"
            or peer.connection_status != "online"
            or peer.last_heartbeat_at is None
            or (datetime.now(UTC) - peer.last_heartbeat_at).total_seconds()
            >= session.info.get("suspect_after_seconds", 20)
        ):
            return False
        if peer.session_id is None or (attempt and pinned.get(str(member)) != str(peer.session_id)):
            return False
        credential = session.scalar(
            select(AccessCredential.id).where(
                AccessCredential.node_id == member,
                AccessCredential.kind == "worker",
                AccessCredential.revoked.is_(False),
            )
        )
        if credential is None:
            return False
        if (
            group.mode == "single_host"
            and len(node_view(session, peer).resources.gpus) < group.device_count
        ):
            return False
    return True


def probe_job(owner: UUID, workspace: UUID, group: SharedInferenceGroup) -> Job:
    return Job(
        id=uuid4(),
        owner_id=owner,
        workspace_id=workspace,
        type="inference.text",
        attempt_count=0,
        requirements=Requirements(
            shared_inference=group,
            wide_area_consent=True,
            model_selection=ModelSelection(identifier=group.model, provider="openai_compatible"),
        ).model_dump(mode="json"),
    )


@router.get("/options")
def options(workspace_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    from godfather_api.scheduler import base_permitted, workspace_access

    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found")
    workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    membership = session.get(WorkspaceMember, (workspace_id, actor.owner_id))
    can_manage = workspace.owner_id == actor.owner_id or bool(
        membership and membership.role == "admin"
    )
    groups = []
    for node in session.scalars(select(Node).order_by(Node.name, Node.id)):
        for group in declared(node):
            if group.leader_node_id != node.id:
                continue
            probe = probe_job(actor.owner_id, workspace_id, group)
            # Discovery preserves every member/owner restriction, but a missing
            # model grant must be visible so a workspace admin can authorize it.
            visibility_probe = probe_job(actor.owner_id, workspace_id, group)
            visibility_probe.requirements = {
                **visibility_probe.requirements,
                "model_selection": None,
            }
            members = [session.get(Node, member) for member in group.node_ids]
            if not all(
                peer and base_permitted(session, visibility_probe, peer) for peer in members
            ):
                continue
            deployment = next(
                (
                    m
                    for m in node_view(session, node).model_deployments
                    if m.shared_inference_group_id == group.id
                    and m.identifier == group.model
                    and m.provider == "openai_compatible"
                    and m.available
                    and "chat" in m.operations
                    and "stream" in m.operations
                ),
                None,
            )
            workspace_allowed = (
                workspace.allowed_models is None or group.model in workspace.allowed_models
            )
            ready = (
                workspace_allowed
                and group_permitted(session, probe, node)
                and deployment is not None
            )
            groups.append(
                {
                    **group.model_dump(mode="json"),
                    "available": ready,
                    "workspace_allowed": workspace_allowed,
                    "can_enable": can_manage,
                    "model_discovered": deployment is not None,
                    "reason": "Ready (owner-configured topology; performance unverified)"
                    if ready
                    else "Workspace permission required for this shared model"
                    if not workspace_allowed
                    else "Waiting for owner consent, online members, devices and engine discovery",
                    "computers": [
                        {"id": str(peer.id), "name": peer.name} for peer in members if peer
                    ],
                }
            )
    return {"groups": groups}


@router.post("/workspace-access")
def enable_workspace_group(
    payload: WorkspaceAccess, request: Request, session: SessionDep
) -> dict[str, bool]:
    from godfather_api.agents import manage_workspace
    from godfather_api.authentication import audit
    from godfather_api.scheduler import lock_workspace

    actor = authenticate(request, session, "human")
    lock_workspace(session, payload.workspace_id)
    manage_workspace(session, payload.workspace_id, actor.owner_id)
    entries = cast(list[dict[str, Any]], options(payload.workspace_id, request, session)["groups"])
    entry = next((group for group in entries if group["id"] == str(payload.group_id)), None)
    if entry is None:
        raise HTTPException(404, "Inference group not found in this authorized workspace")
    if not entry["model_discovered"]:
        raise HTTPException(409, "Wait for the leader to discover this shared engine model")
    workspace = session.get(Workspace, payload.workspace_id)
    assert workspace is not None
    identifier = str(entry["model"])
    if workspace.allowed_models is not None and identifier not in workspace.allowed_models:
        if len(workspace.allowed_models) >= 64:
            raise HTTPException(409, "Workspace model limit reached; review workspace permissions")
        workspace.allowed_models = [*workspace.allowed_models, identifier]
        audit(
            session,
            "workspace_model_enabled",
            actor.owner_id,
            workspace.id,
            workspace_id=workspace.id,
            metadata={"identifier": identifier, "shared_inference_group_id": str(payload.group_id)},
        )
    return {"enabled": True}


@router.post("/jobs", response_model=JobView, status_code=201)
def submit(payload: SharedSubmission, request: Request, session: SessionDep) -> JobView:
    from godfather_api.jobs import submit as submit_job
    from godfather_api.scheduler import lock_workspace

    lock_workspace(session, payload.workspace_id)
    available = options(payload.workspace_id, request, session)
    entries = cast(list[dict[str, Any]], available["groups"])
    entry = next((g for g in entries if g["id"] == str(payload.group_id)), None)
    if entry is None:
        raise HTTPException(404, "Inference group not found in this authorized workspace")
    if not entry["available"]:
        raise HTTPException(
            409, "This group is not ready; check owner consent, devices and engine discovery"
        )
    group = SharedInferenceGroup.model_validate(
        {k: entry[k] for k in SharedInferenceGroup.model_fields}
    )
    if group.mode == "wide_area" and not payload.wide_area_consent:
        raise HTTPException(
            422, "Confirm cross-location prompt sharing and experimental network performance"
        )
    return submit_job(
        InferenceSubmission(
            workspace_id=payload.workspace_id,
            requirements=Requirements(
                shared_inference=group,
                wide_area_consent=payload.wide_area_consent,
                model_selection=ModelSelection(
                    identifier=group.model, provider="openai_compatible", stream=True
                ),
            ),
            input=InferenceInput(prompt=payload.prompt, stream=True),
        ),
        request,
        session,
    )


@router.get("/jobs")
def history(
    request: Request,
    session: SessionDep,
    workspace_id: UUID,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, object]:
    from godfather_api.jobs import view
    from godfather_api.scheduler import workspace_access

    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found")
    query = select(Job).where(
        Job.workspace_id == workspace_id,
        Job.deleted_at.is_(None),
        Job.requirements["shared_inference"].is_not(None),
        Job.requirements.has_key("shared_inference"),
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    return {
        "items": [
            view(session, job).model_dump(mode="json")
            for job in session.scalars(
                query.order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit)
            )
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
