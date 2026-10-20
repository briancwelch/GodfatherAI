"""Persistent user/invitation/workspace administration; owner consent is independent."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select, text, update

from godfather_api.agents import manage_workspace
from godfather_api.authentication import (
    ROLE_PERMISSIONS,
    audit,
    require_permission,
    roles,
    user_data,
)
from godfather_api.models import (
    AccessCredential,
    Event,
    GoogleIdentity,
    HumanSession,
    Invitation,
    Node,
    User,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import SessionDep, authenticate, human_event_details, record, token_digest
from godfather_api.scheduler import workspace_access

router = APIRouter(prefix="/api/v1/administration")


class RoleSelection(BaseModel):
    roles: list[str] = Field(min_length=1, max_length=10)

    @field_validator("roles")
    @classmethod
    def valid_roles(cls, value: list[str]) -> list[str]:
        if any(role not in ROLE_PERMISSIONS for role in value):
            raise ValueError("Unsupported role")
        return sorted(set(value))


class UserChange(RoleSelection):
    enabled: bool


class InviteCreate(RoleSelection):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+$")
    hours: int = Field(default=24, ge=1, le=168)


@router.get("/users")
def users(
    request: Request, session: SessionDep, offset: Annotated[int, Query(ge=0)] = 0
) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    return [
        user_data(u)
        for u in session.scalars(
            select(User)
            .join(GoogleIdentity)
            .order_by(User.created_at, User.id)
            .limit(100)
            .offset(offset)
        )
    ]


@router.post("/users/{user_id}")
def change_user(
    user_id: UUID, payload: UserChange, request: Request, session: SessionDep
) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    # All role/enabled mutations serialize, preventing two admins removing the last.
    session.execute(text("SELECT pg_advisory_xact_lock(909002)"))
    require_permission(session, actor.owner_id, "platform.manage")
    user = session.get(User, user_id, with_for_update=True)
    if user is None:
        raise HTTPException(404, "User not found")
    if "platform_admin" in roles(user) and (
        not payload.enabled or "platform_admin" not in payload.roles
    ):
        other = [
            u
            for u in session.scalars(select(User).where(User.enabled.is_(True), User.id != user_id))
            if "platform_admin" in roles(u)
        ]
        if not other:
            raise HTTPException(409, "An enabled platform administrator is required")
    previous_roles, previous_enabled = roles(user), user.enabled
    user.role, user.roles, user.enabled = payload.roles[0], payload.roles, payload.enabled
    session.execute(
        update(HumanSession).where(HumanSession.owner_id == user_id).values(revoked=True)
    )
    audit(
        session,
        "user_changed",
        actor.owner_id,
        user_id,
        metadata={
            "from_roles": previous_roles,
            "to_roles": roles(user),
            "from_enabled": previous_enabled,
            "to_enabled": user.enabled,
        },
    )
    audit(session, "sessions_revoked", actor.owner_id, user_id)
    return user_data(user)


@router.post("/users/{user_id}/revoke-sessions")
def revoke_user_sessions(user_id: UUID, request: Request, session: SessionDep) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    if session.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    session.execute(
        update(HumanSession).where(HumanSession.owner_id == user_id).values(revoked=True)
    )
    audit(session, "sessions_revoked", actor.owner_id, user_id)
    return {"revoked": True}


def invitation_data(row: Invitation) -> dict[str, object]:
    return {
        "id": str(row.id),
        "email": row.email,
        "roles": row.roles,
        "expires_at": row.expires_at.isoformat(),
        "revoked": row.revoked,
        "used_by": str(row.used_by) if row.used_by else None,
    }


@router.get("/invitations")
def invitations(
    request: Request, session: SessionDep, offset: Annotated[int, Query(ge=0)] = 0
) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    return [
        invitation_data(i)
        for i in session.scalars(
            select(Invitation)
            .order_by(Invitation.created_at.desc(), Invitation.id)
            .limit(100)
            .offset(offset)
        )
    ]


@router.post("/invitations", status_code=201)
def invite(payload: InviteCreate, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    secret = secrets.token_urlsafe(32)
    row = Invitation(
        actor_id=actor.owner_id,
        email=payload.email.lower(),
        roles=payload.roles,
        token_hash=token_digest(secret),
        expires_at=datetime.now(UTC) + timedelta(hours=payload.hours),
    )
    session.add(row)
    session.flush()
    audit(session, "invitation_created", actor.owner_id, row.id)
    # One-time delivery only. Never included in list responses or audit details.
    return {**invitation_data(row), "invitation_token": secret}


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(
    invitation_id: UUID, request: Request, session: SessionDep
) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    row = session.get(Invitation, invitation_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Invitation not found")
    row.revoked = True
    audit(session, "invitation_revoked", actor.owner_id, row.id)
    return invitation_data(row)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    allowed_models: list[str] = Field(default_factory=list, max_length=64)
    allowed_tools: list[str] = Field(default_factory=list, max_length=16)


class WorkspacePolicy(BaseModel):
    allowed_models: list[str] = Field(max_length=64)
    allowed_tools: list[str] = Field(max_length=16)


@router.post("/workspaces/{workspace_id}/policy")
def workspace_policy(
    workspace_id: UUID, payload: WorkspacePolicy, request: Request, session: SessionDep
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    workspace = session.get(Workspace, workspace_id, with_for_update=True)
    manage_workspace(session, workspace_id, actor.owner_id)
    assert workspace is not None
    workspace.allowed_models, workspace.allowed_tools = (
        payload.allowed_models,
        payload.allowed_tools,
    )
    audit(
        session, "workspace_policy_changed", actor.owner_id, workspace_id, workspace_id=workspace_id
    )
    return {"updated": True}


@router.post("/workspaces", status_code=201)
def create_workspace(
    payload: WorkspaceCreate, request: Request, session: SessionDep
) -> dict[str, str]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "workspaces.create")
    workspace = Workspace(
        name=payload.name,
        owner_id=actor.owner_id,
        allowed_models=payload.allowed_models,
        allowed_tools=payload.allowed_tools,
    )
    session.add(workspace)
    session.flush()
    audit(session, "workspace_created", actor.owner_id, workspace.id, workspace_id=workspace.id)
    return {"id": str(workspace.id), "name": workspace.name}


@router.get("/workspaces/{workspace_id}/members")
def members(workspace_id: UUID, request: Request, session: SessionDep) -> dict[str, object]:
    actor = authenticate(request, session, "human")
    if not workspace_access(session, actor.owner_id, workspace_id):
        raise HTTPException(404, "Workspace not found")
    workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    return {
        "owner_id": str(workspace.owner_id),
        "allowed_models": workspace.allowed_models,
        "allowed_tools": workspace.allowed_tools,
        "shared": workspace.is_shared,
        "members": [
            {"user_id": str(m.user_id), "role": m.role}
            for m in session.scalars(
                select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
            )
        ],
    }


class MembershipChange(BaseModel):
    user_id: UUID
    role: Literal["admin", "member", "remove"]


@router.post("/workspaces/{workspace_id}/members")
def change_membership(
    workspace_id: UUID, payload: MembershipChange, request: Request, session: SessionDep
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    # Workspace lock serializes revocation/grants; global admin does not bypass it.
    workspace = session.get(Workspace, workspace_id, with_for_update=True)
    manage_workspace(session, workspace_id, actor.owner_id)
    assert workspace is not None
    if payload.user_id == workspace.owner_id:
        raise HTTPException(409, "Workspace owner membership is inherent")
    if session.get(User, payload.user_id) is None:
        raise HTTPException(404, "User not found")
    row = session.get(WorkspaceMember, (workspace_id, payload.user_id))
    if payload.role == "remove":
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(
            WorkspaceMember(workspace_id=workspace_id, user_id=payload.user_id, role=payload.role)
        )
    else:
        row.role = payload.role
    session.flush()
    workspace.is_shared = (
        session.scalar(
            select(WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .limit(1)
        )
        is not None
    )
    audit(
        session,
        "workspace_permission_changed",
        actor.owner_id,
        payload.user_id,
        workspace_id=workspace_id,
    )
    return {"updated": True}


class NodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.get("/node-credentials")
def owned_credentials(
    request: Request, session: SessionDep, offset: Annotated[int, Query(ge=0)] = 0
) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "revoked": c.revoked,
            "node_id": str(c.node_id) if c.node_id else None,
        }
        for c in session.scalars(
            select(AccessCredential)
            .where(AccessCredential.owner_id == actor.owner_id, AccessCredential.kind == "worker")
            .order_by(AccessCredential.created_at.desc())
            .limit(100)
            .offset(offset)
        )
    ]


@router.post("/node-credentials/{credential_id}/revoke")
def revoke_owned_credential(
    credential_id: UUID, request: Request, session: SessionDep
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    credential = session.scalar(
        select(AccessCredential)
        .where(
            AccessCredential.id == credential_id,
            AccessCredential.kind == "worker",
            AccessCredential.owner_id == actor.owner_id,
        )
        .with_for_update()
    )
    if credential is None:
        raise HTTPException(404, "Owned machine credential not found")
    credential.revoked = True
    if credential.node_id is not None:
        node = session.get(Node, credential.node_id, with_for_update=True)
        if node is not None:
            node.state = "disabled"
            record(session, node, "node.credential_revoked", {}, actor.owner_id)
    audit(session, "node_credential_revoked", actor.owner_id, credential.id)
    return {"revoked": True}


@router.post("/node-credentials", status_code=201)
def node_credential(payload: NodeCreate, request: Request, session: SessionDep) -> dict[str, str]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "nodes.contribute")
    if session.scalar(
        select(AccessCredential.id).where(
            AccessCredential.owner_id == actor.owner_id, AccessCredential.name == payload.name
        )
    ):
        raise HTTPException(409, "Node name already exists")
    secret = secrets.token_urlsafe(32)
    row = AccessCredential(
        owner_id=actor.owner_id, kind="worker", name=payload.name, token_hash=token_digest(secret)
    )
    session.add(row)
    session.flush()
    audit(session, "node_credential_created", actor.owner_id, row.id)
    return {"node_id": str(row.id), "owner_id": str(actor.owner_id), "token": secret}


@router.get("/audit")
def security_audit(
    request: Request, session: SessionDep, offset: Annotated[int, Query(ge=0)] = 0
) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    visible = select(Workspace.id).where(
        or_(
            Workspace.owner_id == actor.owner_id,
            Workspace.id.in_(
                select(WorkspaceMember.workspace_id).where(
                    WorkspaceMember.user_id == actor.owner_id
                )
            ),
        )
    )
    query = select(Event).where(
        or_(
            Event.type.like("security.%"),
            Event.type.like("node.%"),
            Event.type.like("agent.%"),
            Event.type.like("provider.%"),
            Event.type.in_(("job.cancellation_requested", "job.manual_retry_requested")),
        ),
        or_(Event.workspace_id.is_(None), Event.workspace_id.in_(visible)),
    )
    return [
        {
            "id": str(e.id),
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "action": e.type,
            "timestamp": e.created_at.isoformat(),
            "details": human_event_details(e, actor.owner_id),
            "correlation_id": e.correlation_id,
        }
        for e in session.scalars(
            query.order_by(Event.created_at.desc(), Event.id).limit(100).offset(offset)
        )
    ]
