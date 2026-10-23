"""Authenticated node lifecycle, persisted atomically with audit events."""

import hashlib
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Literal, NoReturn, overload
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer
from godfather_contracts import (
    PROTOCOL_VERSION,
    Connection,
    Heartbeat,
    NodeControl,
    NodeView,
    Registration,
    WorkerAck,
)
from godfather_contracts.coding import CodingSetupOptions, CodingWorkspace
from sqlalchemy import delete, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.logging import correlation_id
from godfather_api.models import (
    AccessCredential,
    Capability,
    Event,
    GoogleIdentity,
    HumanSession,
    Node,
    NodeCapability,
    User,
    Workspace,
    WorkspaceMember,
)

logger = logging.getLogger("godfather.nodes")
router = APIRouter(prefix="/api/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def session_dependency(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    with database.sessions.begin() as session:
        yield session


# Commit before sending success; request-scoped yield teardown runs after the response.
SessionDep = Annotated[Session, Depends(session_dependency, scope="function")]


def node_visibility(session: Session, actor_id: UUID) -> ColumnElement[bool]:
    from godfather_api.authentication import permissions

    owner = session.get(User, actor_id)
    scope = (
        true() if owner and "platform.manage" in permissions(owner) else Node.owner_id == actor_id
    )
    live = (
        true()
        if session.info.get("test")
        else (
            (Node.resources["source"].astext == "physical")
            & Node.owner_id.in_(select(GoogleIdentity.user_id))
        )
    )
    return scope & live


@overload
def authenticate(
    request: Request, session: Session, kind: Literal["worker", "admin"]
) -> AccessCredential: ...


@overload
def authenticate(
    request: Request, session: Session, kind: Literal["human"]
) -> AccessCredential | HumanSession: ...


def authenticate(request: Request, session: Session, kind: str) -> AccessCredential | HumanSession:
    def refused() -> NoReturn:
        if kind == "worker":
            from godfather_api.authentication import throttle

            throttle(request, "worker-invalid-credential")
        raise HTTPException(401, "A valid bearer credential is required")

    if kind == "human":
        from godfather_api.authentication import human

        settings: Settings = request.app.state.settings
        if not (
            settings.environment == "test"
            and settings.test_legacy_credentials
            and request.headers.get("authorization")
        ):
            return human(request, session)
        kind = "admin"
    headers = request.headers.getlist("authorization")
    if len(headers) != 1:
        refused()
    scheme, _, token = headers[0].partition(" ")
    if (
        scheme.lower() != "bearer"
        or len(token) != 43
        or not all(c.isascii() and (c.isalnum() or c in "-_") for c in token)
    ):
        refused()
    # Serialize registration, heartbeat, and revocation for each identity.
    credential = session.scalar(
        select(AccessCredential)
        .where(AccessCredential.token_hash == token_digest(token), AccessCredential.kind == kind)
        .with_for_update()
    )
    if credential is None or credential.revoked:
        refused()
    owner = session.get(User, credential.owner_id)
    if owner is None or not owner.enabled or (kind == "admin" and owner.role != "platform_admin"):
        raise HTTPException(403, "Credential owner is not permitted")
    if kind == "worker":
        from godfather_api.authentication import require_permission

        require_permission(session, owner.id, "nodes.contribute")
        if (
            not session.info.get("test")
            and session.scalar(select(GoogleIdentity.id).where(GoogleIdentity.user_id == owner.id))
            is None
        ):
            raise HTTPException(403, "Worker owner requires an explicitly linked Google identity")
    return credential


@router.post("/workers/coding/options", response_model=CodingSetupOptions)
def coding_setup_options(request: Request, session: SessionDep) -> CodingSetupOptions:
    """Read-only owner workspace names for local consent; no host permissions granted."""
    credential = authenticate(request, session, "worker")
    member_ids = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == credential.owner_id
    )
    workspaces = session.scalars(
        select(Workspace)
        .where(
            Workspace.deleted_at.is_(None),
            (Workspace.owner_id == credential.owner_id) | Workspace.id.in_(member_ids),
        )
        .order_by(Workspace.name, Workspace.id)
        .limit(128)
    )
    return CodingSetupOptions(
        owner_id=credential.owner_id,
        workspaces=[CodingWorkspace(id=w.id, name=w.name) for w in workspaces],
    )


def record(
    session: Session,
    node: Node,
    event: str,
    details: dict[str, object],
    actor_id: UUID | None = None,
) -> None:
    session.add(
        Event(
            node_id=node.id,
            actor_id=actor_id,
            type=event,
            correlation_id=correlation_id.get(),
            details=details,
        )
    )
    logger.info(event, extra={"node_id": str(node.id), "node_state": node.state})


def connection_at(last: datetime | None, now: datetime, settings: Settings) -> Connection:
    if last is None or (now - last).total_seconds() >= settings.offline_after_seconds:
        return "offline"
    if (now - last).total_seconds() >= settings.suspect_after_seconds:
        return "suspect"
    return "online"


def transition(session: Session, node: Node, connection: Connection) -> None:
    previous = node.connection_status
    node.connection_status = connection
    if node.state not in ("draining", "disabled"):
        node.state = connection
    if previous != connection:
        record(session, node, "node.health_changed", {"from": previous, "to": connection})


def sweep_health(database: Database, settings: Settings, now: datetime | None = None) -> None:
    """No in-memory authority; locks prevent racing a fresh heartbeat or another API."""
    timestamp = now or datetime.now(UTC)
    with database.sessions.begin() as session:
        nodes = session.scalars(
            select(Node)
            .where(Node.connection_status != "offline")
            .order_by(Node.id)
            .with_for_update(skip_locked=True)
        )
        for node in nodes:
            transition(session, node, connection_at(node.last_heartbeat_at, timestamp, settings))


def node_view(session: Session, node: Node) -> NodeView:
    specialties: dict[str, list[str]] = {"primary": [], "secondary": []}
    for name, specialty in session.execute(
        select(Capability.name, NodeCapability.specialty)
        .join(NodeCapability)
        .where(NodeCapability.node_id == node.id)
        .order_by(Capability.name)
    ):
        specialties[specialty].append(name)
    return NodeView.model_validate(
        {
            **node.runtimes,
            "allowed_job_owner_ids": node.contribution_policy.get("allowed_job_owner_ids", []),
            "allowed_workspace_ids": node.contribution_policy.get("allowed_workspace_ids", []),
            "share_with_workspaces": node.contribution_policy.get("share_with_workspaces", False),
            "node_id": node.id,
            "owner_id": node.owner_id,
            "owner_name": (
                owner.display_name if (owner := session.get(User, node.owner_id)) else None
            ),
            "name": node.name,
            "owner_picture": owner.picture if owner else None,
            "owner_location": (owner.profile or {}).get("location") if owner else None,
            "os": node.os,
            "os_version": node.os_version,
            "architecture": node.architecture,
            "protocol_version": node.protocol_version,
            "state": node.state,
            "connection_status": node.connection_status,
            "last_heartbeat_at": node.last_heartbeat_at,
            "scheduling_policy": node.scheduling_policy,
            "concurrency_limit": node.concurrency_limit,
            "resources": node.resources,
            "primary_capabilities": specialties["primary"],
            "secondary_capabilities": specialties["secondary"],
        }
    )


def human_node_view(session: Session, node: Node, actor_id: UUID) -> NodeView:
    view = node_view(session, node)
    if node.owner_id == actor_id:
        return view
    from godfather_api.scheduler import workspace_access

    return view.model_copy(
        update={
            "allowed_workspace_ids": [
                w for w in view.allowed_workspace_ids if workspace_access(session, actor_id, w)
            ],
            "allowed_job_owner_ids": [u for u in view.allowed_job_owner_ids if u == actor_id],
            "coding_repositories": [
                r.model_copy(
                    update={
                        "allowed_user_ids": [actor_id],
                        "allowed_workspace_ids": [
                            w
                            for w in r.allowed_workspace_ids
                            if workspace_access(session, actor_id, w)
                        ],
                    }
                )
                for r in view.coding_repositories
                if actor_id in r.allowed_user_ids
            ],
            "model_deployments": [m for m in view.model_deployments if m.connection_id is None],
        }
    )


def human_event_details(event: Event, actor_id: UUID) -> dict[str, object]:
    # Global health history must not reveal private workspace grant UUIDs.
    if event.type == "node.contribution_changed" and event.actor_id != actor_id:
        return {"policy_changed": True}
    return event.details


def ack(node: Node, settings: Settings) -> WorkerAck:
    return WorkerAck.model_validate(
        {
            "node_id": node.id,
            "state": node.state,
            "connection_status": node.connection_status,
            "heartbeat_interval_seconds": settings.heartbeat_interval_seconds,
        }
    )


def check_protocol(version: int) -> None:
    if version != PROTOCOL_VERSION:
        raise HTTPException(426, "Worker protocol v1 is required; upgrade the worker")


@router.post("/workers/register", response_model=WorkerAck)
def register(payload: Registration, request: Request, session: SessionDep) -> WorkerAck:
    credential = authenticate(request, session, "worker")
    check_protocol(payload.protocol_version)
    settings: Settings = request.app.state.settings
    if settings.environment != "test" and payload.resources.source != "physical":
        raise HTTPException(403, "Simulated workers are restricted to isolated tests")
    now = datetime.now(UTC)
    node = session.scalar(select(Node).where(Node.id == credential.node_id).with_for_update())
    created = node is None
    if node is None:
        node = Node(
            id=credential.id,
            owner_id=credential.owner_id,
            name=credential.name,
            os=payload.os,
            os_version=payload.os_version,
            architecture=payload.architecture,
            state="offline",
            connection_status="offline",
        )
        session.add(node)
        session.flush()
        credential.node_id = node.id
    elif node.state == "disabled":
        raise HTTPException(403, "Node is disabled")
    elif (
        node.session_id != payload.session_id
        and connection_at(node.last_heartbeat_at, now, settings) != "offline"
    ):
        raise HTTPException(409, "Node identity has an active worker process")
    if any(node.id not in group.node_ids for group in payload.shared_inference_groups):
        raise HTTPException(422, "Workers may consent only to groups containing their own node ID")
    if len({g.id for g in payload.shared_inference_groups}) != len(payload.shared_inference_groups):
        raise HTTPException(422, "Shared inference groups must have distinct IDs")
    node.os, node.os_version, node.architecture = (
        payload.os,
        payload.os_version,
        payload.architecture,
    )
    node.protocol_version = payload.protocol_version
    node.session_id = payload.session_id
    node.resources = payload.resources.model_dump(mode="json")
    node.runtimes = payload.model_dump(
        mode="json",
        include={
            "worker_version",
            "job_protocol_version",
            "inference_protocol_version",
            "workflow_protocol_version",
            "worker_tools",
            "tool_permissions",
            "model_deployments",
            "runtimes",
            "installed_models",
            "dependencies",
            "toolchains",
            "sandbox_modes",
            "discovery_warnings",
            "coding_repositories",
            "shared_inference_groups",
        },
    )
    node.scheduling_policy, node.concurrency_limit = (
        payload.scheduling_policy,
        payload.concurrency_limit,
    )
    session.execute(delete(NodeCapability).where(NodeCapability.node_id == node.id))
    # A shared order avoids deadlocks when new nodes declare overlapping specialties.
    for name in sorted(payload.primary_capabilities + payload.secondary_capabilities):
        session.execute(
            insert(Capability)
            .values(name=name)
            .on_conflict_do_nothing(index_elements=[Capability.name])
        )
    for specialty, names in (
        ("primary", payload.primary_capabilities),
        ("secondary", payload.secondary_capabilities),
    ):
        for name in sorted(names):
            capability_id = session.scalar(select(Capability.id).where(Capability.name == name))
            session.add(
                NodeCapability(node_id=node.id, capability_id=capability_id, specialty=specialty)
            )
    policy = {
        k: v
        for k, v in node.contribution_policy.items()
        if k not in ("allowed_job_owner_ids", "allowed_workspace_ids", "share_with_workspaces")
    }
    if payload.allowed_job_owner_ids:
        policy["allowed_job_owner_ids"] = [str(v) for v in payload.allowed_job_owner_ids]
    if payload.allowed_workspace_ids:
        policy["allowed_workspace_ids"] = [str(v) for v in payload.allowed_workspace_ids]
    if payload.share_with_workspaces:
        policy["share_with_workspaces"] = True
    if node.contribution_policy != policy:
        record(
            session,
            node,
            "node.contribution_changed",
            {
                "allowed_job_owner_ids": policy.get("allowed_job_owner_ids", []),
                "allowed_workspace_ids": policy.get("allowed_workspace_ids", []),
                "share_with_workspaces": policy.get("share_with_workspaces", False),
            },
            credential.owner_id,
        )
    node.contribution_policy = policy
    node.last_heartbeat_at = now
    transition(session, node, "online")
    record(
        session, node, "node.registered" if created else "node.reconnected", {}, credential.owner_id
    )
    return ack(node, settings)


@router.post("/workers/{node_id}/heartbeat", response_model=WorkerAck)
def heartbeat(
    node_id: UUID, payload: Heartbeat, request: Request, session: SessionDep
) -> WorkerAck:
    credential = authenticate(request, session, "worker")
    check_protocol(payload.protocol_version)
    if credential.node_id != node_id:
        raise HTTPException(403, "Credential is scoped to another node")
    node = session.scalar(select(Node).where(Node.id == node_id).with_for_update())
    if node is None:
        raise HTTPException(409, "Register this node first")
    if node.state == "disabled":
        raise HTTPException(403, "Node is disabled")
    if node.session_id != payload.session_id:
        raise HTTPException(409, "Worker process session is stale; register again")
    if node.resources.get("source") != payload.resources.source:
        raise HTTPException(422, "Telemetry source must match registration")
    node.resources = payload.resources.model_dump(mode="json")
    node.last_heartbeat_at = datetime.now(UTC)
    transition(session, node, "online")
    return ack(node, request.app.state.settings)


@router.get("/nodes", response_model=list[NodeView])
def list_nodes(
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NodeView]:
    actor = authenticate(request, session, "human")
    nodes = session.scalars(
        select(Node)
        .where(Node.session_id.is_not(None), node_visibility(session, actor.owner_id))
        .order_by(Node.created_at, Node.id)
        .limit(limit)
        .offset(offset)
    )
    return [human_node_view(session, node, actor.owner_id) for node in nodes]


@router.get("/nodes/{node_id}", response_model=NodeView)
def inspect_node(node_id: UUID, request: Request, session: SessionDep) -> NodeView:
    actor = authenticate(request, session, "human")
    node = session.scalar(
        select(Node).where(Node.id == node_id, node_visibility(session, actor.owner_id))
    )
    if node is None or node.session_id is None:
        raise HTTPException(404, "Node not found")
    return human_node_view(session, node, actor.owner_id)


@router.post("/nodes/{node_id}/control", response_model=NodeView)
def control_node(
    node_id: UUID, payload: NodeControl, request: Request, session: SessionDep
) -> NodeView:
    admin = authenticate(request, session, "human")
    credential = session.scalar(
        select(AccessCredential).where(AccessCredential.node_id == node_id).with_for_update()
    )
    node = session.scalar(select(Node).where(Node.id == node_id).with_for_update())
    if node is None or credential is None:
        raise HTTPException(404, "Node not found")
    if node.owner_id != admin.owner_id:
        raise HTTPException(403, "Only the node owner may change its contribution")
    if credential.revoked:
        raise HTTPException(409, "Node credential has been permanently revoked")
    previous = node.state
    if payload.action == "revoke":
        credential.revoked = True
        node.state = "disabled"
    elif payload.action == "enable":
        transition(
            session,
            node,
            connection_at(node.last_heartbeat_at, datetime.now(UTC), request.app.state.settings),
        )
        node.state = node.connection_status
    else:
        node.state = "draining" if payload.action == "drain" else "disabled"
    record(
        session,
        node,
        "node." + payload.action,
        {"from": previous, "to": node.state},
        admin.owner_id,
    )
    return node_view(session, node)
