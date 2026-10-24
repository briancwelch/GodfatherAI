"""Persistent role policy for adding computers; existing owner consent is independent."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from godfather_contracts import Contract
from pydantic import StrictBool
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from godfather_api.authentication import audit, require_permission, roles
from godfather_api.models import ApplicationSetting, User
from godfather_api.nodes import SessionDep, authenticate

router = APIRouter(prefix="/api/v1/administration/node-registration")


class NodeRegistrationPolicy(Contract):
    members_can_add_nodes: StrictBool = True
    contributors_can_add_nodes: StrictBool = True


def policy(session: Session) -> NodeRegistrationPolicy:
    row = session.get(ApplicationSetting, "node_registration")
    return NodeRegistrationPolicy.model_validate(row.value) if row else NodeRegistrationPolicy()


def can_add_nodes(session: Session, user: User) -> bool:
    assigned = roles(user)
    if "platform_admin" in assigned:
        return True
    current = policy(session)
    return ("member" in assigned and current.members_can_add_nodes) or (
        "contributor" in assigned and current.contributors_can_add_nodes
    )


def require_add_nodes(session: Session, owner_id: UUID) -> None:
    user = session.get(User, owner_id)
    if user is None or not user.enabled or not can_add_nodes(session, user):
        raise HTTPException(
            403, "Your role cannot add new nodes. Contact a platform administrator."
        )


@router.get("")
def get_policy(request: Request, session: SessionDep) -> NodeRegistrationPolicy:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    return policy(session)


@router.post("")
def save_policy(
    payload: NodeRegistrationPolicy, request: Request, session: SessionDep
) -> NodeRegistrationPolicy:
    actor = authenticate(request, session, "human")
    require_permission(session, actor.owner_id, "platform.manage")
    session.execute(text("SELECT pg_advisory_xact_lock(909003)"))
    row = session.scalar(
        select(ApplicationSetting)
        .where(ApplicationSetting.key == "node_registration")
        .with_for_update()
    )
    before = policy(session).model_dump()
    if row is None:
        session.add(ApplicationSetting(key="node_registration", value=payload.model_dump()))
    else:
        row.value = payload.model_dump()
    audit(
        session,
        "node_registration_policy_updated",
        actor.owner_id,
        metadata={"before": before, "after": payload.model_dump()},
    )
    return payload
