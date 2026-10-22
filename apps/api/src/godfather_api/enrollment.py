"""Owner-approved proof-of-possession pairing; no public machine credential delivery."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from godfather_contracts import Contract
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from godfather_api.authentication import audit, human, require_permission, throttle
from godfather_api.models import AccessCredential, Attempt, GoogleIdentity, Node, WorkerEnrollment
from godfather_api.nodes import SessionDep, connection_at, token_digest

router = APIRouter(prefix="/api/v1")


class EnrollmentApproval(Contract):
    challenge: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(min_length=1, max_length=100)
    reconnect: bool = False


def reconnect_node(
    session: SessionDep, credential: AccessCredential, request: Request
) -> Node | None:
    """The credential lock serializes replacement against all old worker requests."""
    if credential.deleted_at is not None:
        raise HTTPException(409, "This connection was deleted. Start a new pairing.")
    if credential.node_id is None:
        return None
    node = session.scalar(select(Node).where(Node.id == credential.node_id).with_for_update())
    if node is None or node.owner_id != credential.owner_id:
        raise HTTPException(409, "Existing computer identity is unavailable")
    if node.state == "draining" or (node.state == "disabled" and not credential.revoked):
        raise HTTPException(409, "Enable the existing computer before reconnecting it")
    if (
        connection_at(node.last_heartbeat_at, datetime.now(UTC), request.app.state.settings)
        != "offline"
    ):
        raise HTTPException(409, "Quit the old worker, wait 30 seconds, then reconnect")
    if session.scalar(
        select(Attempt.id)
        .where(Attempt.node_id == node.id, Attempt.status.in_(("ASSIGNED", "RUNNING")))
        .limit(1)
    ):
        raise HTTPException(409, "Wait for the existing computer's unfinished work to settle")
    return node


class EnrollmentExchange(Contract):
    secret: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)
    machine_secret: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)


@router.post("/administration/worker-enrollments/revoke")
def revoke(payload: EnrollmentApproval, request: Request, session: SessionDep) -> dict[str, bool]:
    actor = human(request, session)
    row = session.scalar(
        select(WorkerEnrollment)
        .where(
            WorkerEnrollment.challenge == payload.challenge,
            WorkerEnrollment.owner_id == actor.owner_id,
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Owned pairing not found")
    row.consumed = True
    audit(session, "worker_enrollment_revoked", actor.owner_id, row.id)
    return {"revoked": True}


@router.post("/administration/worker-enrollments", status_code=201)
def approve(payload: EnrollmentApproval, request: Request, session: SessionDep) -> dict[str, str]:
    actor = human(request, session)
    owner = require_permission(session, actor.owner_id, "nodes.contribute")
    throttle(request, "worker-enrollment-approve")
    if session.scalar(select(GoogleIdentity.id).where(GoogleIdentity.user_id == owner.id)) is None:
        raise HTTPException(403, "Google-linked owner required")
    existing = session.scalar(
        select(AccessCredential)
        .where(
            AccessCredential.owner_id == owner.id,
            AccessCredential.kind == "worker",
            AccessCredential.name == payload.name,
        )
        .with_for_update()
    )
    if existing is not None and not payload.reconnect:
        raise HTTPException(409, "This computer already exists. Select Reconnect this computer.")
    if payload.reconnect:
        if existing is None:
            raise HTTPException(
                404, "No owned computer has that name. Uncheck Reconnect to add it."
            )
        reconnect_node(session, existing, request)
    row = WorkerEnrollment(
        owner_id=owner.id,
        challenge=payload.challenge,
        name=payload.name,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        replaces_credential_id=existing.id if payload.reconnect and existing else None,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        raise HTTPException(409, "Pairing already approved; reconnect from the app") from None
    audit(session, "worker_enrollment_approved", owner.id, row.id)
    return {"expires_at": row.expires_at.isoformat()}


@router.post("/workers/enrollment/exchange")
def exchange(payload: EnrollmentExchange, request: Request, session: SessionDep) -> dict[str, str]:
    throttle(request, "worker-enrollment-exchange")
    row = session.scalar(
        select(WorkerEnrollment)
        .where(WorkerEnrollment.challenge == token_digest(payload.secret))
        .with_for_update()
    )
    if row is None or row.consumed or row.expires_at <= datetime.now(UTC):
        raise HTTPException(404, "Pairing unavailable; approve a new connection from the app")
    owner = require_permission(session, row.owner_id, "nodes.contribute")
    if session.scalar(select(GoogleIdentity.id).where(GoogleIdentity.user_id == owner.id)) is None:
        raise HTTPException(403, "Google-linked owner required")
    previous = None
    node = None
    if row.replaces_credential_id is not None:
        previous = session.scalar(
            select(AccessCredential)
            .where(
                AccessCredential.id == row.replaces_credential_id,
                AccessCredential.owner_id == owner.id,
                AccessCredential.kind == "worker",
                AccessCredential.name == row.name,
            )
            .with_for_update()
        )
        if previous is None:
            raise HTTPException(409, "Connection already replaced. Start Connect again.")
        node = reconnect_node(session, previous, request)
    credential = AccessCredential(
        owner_id=owner.id,
        kind="worker",
        name=row.name,
        token_hash=token_digest(payload.machine_secret),
        node_id=node.id if node else None,
    )
    try:
        with session.begin_nested():
            if previous is not None:
                # Keep the old token permanently revoked, freeing only its name/node binding.
                previous.revoked = True
                previous.name = "Retired connection " + str(previous.id)
                previous.node_id = None
                session.flush()
                if node is not None:
                    node.session_id = None
                    node.last_heartbeat_at = None
                    node.state = node.connection_status = "offline"
                    node.runtimes = {}
            session.add(credential)
            session.flush()
    except IntegrityError:
        raise HTTPException(409, "Node name already exists; approve a new name") from None
    row.consumed = True
    if previous is not None:
        audit(
            session,
            "worker_connection_replaced",
            owner.id,
            credential.id,
            metadata={
                "previous_credential_id": str(previous.id),
                "node_id": str(node.id) if node else None,
            },
        )
    audit(session, "worker_enrollment_consumed", owner.id, credential.id)
    return {
        "credential_id": str(credential.id),
        "owner_id": str(owner.id),
        "owner": owner.email,
        "name": row.name,
    }
