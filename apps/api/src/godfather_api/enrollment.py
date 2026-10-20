"""Owner-approved proof-of-possession pairing; no public machine credential delivery."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from godfather_contracts import Contract
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from godfather_api.authentication import audit, human, require_permission, throttle
from godfather_api.models import AccessCredential, GoogleIdentity, WorkerEnrollment
from godfather_api.nodes import SessionDep, token_digest

router = APIRouter(prefix="/api/v1")


class EnrollmentApproval(Contract):
    challenge: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(min_length=1, max_length=100)


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
    row = WorkerEnrollment(
        owner_id=owner.id,
        challenge=payload.challenge,
        name=payload.name,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
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
    credential = AccessCredential(
        owner_id=owner.id,
        kind="worker",
        name=row.name,
        token_hash=token_digest(payload.machine_secret),
    )
    try:
        with session.begin_nested():
            session.add(credential)
            session.flush()
    except IntegrityError:
        raise HTTPException(409, "Node name already exists; approve a new name") from None
    row.consumed = True
    audit(session, "worker_enrollment_consumed", owner.id, credential.id)
    return {
        "credential_id": str(credential.id),
        "owner_id": str(owner.id),
        "owner": owner.email,
        "name": row.name,
    }
