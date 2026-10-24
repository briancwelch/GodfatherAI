"""Worker-only setup requests; each physical computer approves its own execution."""

import ipaddress
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from fastapi import APIRouter, HTTPException, Request
from godfather_contracts import Contract, SharedInferenceGroup
from godfather_contracts.shared_engine import (
    SETUP_RUNTIME,
    EngineAction,
    EngineApproval,
    EngineCreate,
    EngineGroup,
    EngineMember,
    EngineProposal,
    EngineReport,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from godfather_api.authentication import audit, require_permission
from godfather_api.models import (
    AccessCredential,
    Job,
    Node,
    SharedEngineConsent,
    SharedEngineSetup,
    User,
    Workspace,
)
from godfather_api.nodes import SessionDep, authenticate, node_view, transition
from godfather_api.scheduler import base_permitted, workspace_access
from godfather_api.shared_inference import probe_job

router = APIRouter(prefix="/api/v1/workers/shared-engine")


def owned(request: Request, session: Session) -> tuple[AccessCredential, Node]:
    credential = authenticate(request, session, "worker")
    node = session.get(Node, credential.node_id) if credential.node_id else None
    if node is None or node.owner_id != credential.owner_id or node.state == "disabled":
        raise HTTPException(409, "Resume and connect this computer before shared inference setup")
    return credential, node


def proposal(row: SharedEngineSetup) -> EngineProposal:
    return EngineProposal.model_validate(row.proposal)


def consents(session: Session, group_id: UUID) -> list[SharedEngineConsent]:
    return list(
        session.scalars(
            select(SharedEngineConsent)
            .where(SharedEngineConsent.group_id == group_id)
            .order_by(SharedEngineConsent.node_id)
        )
    )


def approved(session: Session, consent: SharedEngineConsent) -> bool:
    credential = (
        session.get(AccessCredential, consent.credential_id) if consent.credential_id else None
    )
    return bool(
        consent.approved
        and credential
        and not credential.revoked
        and credential.node_id == consent.node_id
    )


def topology(session: Session, row: SharedEngineSetup) -> SharedInferenceGroup | None:
    plan = proposal(row)
    members = consents(session, row.id)
    if {m.node_id for m in members} != set(plan.node_ids) or not all(
        approved(session, m) for m in members
    ):
        return None
    count = sum(len(EngineApproval.model_validate(m.configuration).devices) for m in members)
    if not 2 <= count <= 1024:
        return None
    return SharedInferenceGroup(
        id=plan.id,
        name=plan.name,
        mode=plan.mode,
        leader_node_id=plan.leader_node_id,
        node_ids=plan.node_ids,
        model=plan.model_alias,
        engine="llama_cpp",
        parallelism="pipeline",
        device_count=count,
        private_transport=True,
    )


def member_row(
    session: Session, group_id: UUID, node_id: UUID
) -> tuple[SharedEngineSetup, SharedEngineConsent]:
    row = session.get(SharedEngineSetup, group_id, with_for_update=True)
    member = session.get(SharedEngineConsent, (group_id, node_id), with_for_update=True)
    if row is None or member is None:
        raise HTTPException(404, "Shared inference invitation not found for this computer")
    return row, member


def permitted_members(session: Session, row: SharedEngineSetup) -> bool:
    plan = proposal(row)
    probe = SharedInferenceGroup(
        id=plan.id,
        name=plan.name,
        mode=plan.mode,
        leader_node_id=plan.leader_node_id,
        node_ids=plan.node_ids,
        model=plan.model_alias,
        engine="llama_cpp",
        parallelism="pipeline",
        device_count=max(2, len(plan.node_ids)),
        private_transport=True,
    )
    job = probe_job(row.owner_id, row.workspace_id, probe)
    job.requirements = {}
    return all(
        (node := session.get(Node, n)) is not None
        and node.state not in ("draining", "disabled")
        and base_permitted(session, job, node)
        for n in plan.node_ids
    )


def view(session: Session, row: SharedEngineSetup, own_id: UUID) -> EngineGroup:
    own = session.get(SharedEngineConsent, (row.id, own_id))
    reveal = own is not None and approved(session, own)
    members = []
    by_id = {m.node_id: m for m in consents(session, row.id)}
    for identity in proposal(row).node_ids:
        member = by_id[identity]
        node = session.get(Node, identity)
        user = session.get(User, node.owner_id) if node else None
        configuration = (
            EngineApproval.model_validate(member.configuration) if member.configuration else None
        )
        members.append(
            EngineMember(
                node_id=identity,
                name=node.name if node else "Unavailable computer",
                owner=user.display_name if user else "Unavailable owner",
                approved=approved(session, member),
                devices=configuration.devices if configuration else [],
                host=configuration.host if configuration and reveal else None,
                port=configuration.port if configuration and reveal else None,
                certificate=configuration.certificate if configuration and reveal else None,
                phase=member.phase,
                error_code=member.error_code,
            )
        )
    return EngineGroup(
        proposal=proposal(row),
        members=members,
        desired_running=row.desired_running,
        generation=row.generation,
        group=topology(session, row),
    )


class OptionsRequest(Contract):
    workspace_id: UUID | None = None


@router.post("/options")
def options(payload: OptionsRequest, request: Request, session: SessionDep) -> dict[str, object]:
    credential, own = owned(request, session)
    workspaces = list(
        session.scalars(
            select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.name)
        )
    )
    workspaces = [w for w in workspaces if workspace_access(session, credential.owner_id, w.id)]
    if payload.workspace_id and payload.workspace_id not in {w.id for w in workspaces}:
        raise HTTPException(404, "Workspace not found")
    candidates = []
    if payload.workspace_id:
        plan = EngineProposal(
            id=uuid4(),
            workspace_id=payload.workspace_id,
            name="Setup",
            model_name="Installed model",
            mode="single_host",
            leader_node_id=own.id,
            node_ids=[own.id],
        )
        for node in session.scalars(select(Node).order_by(Node.name, Node.id)):
            probe = probe_job(
                credential.owner_id,
                payload.workspace_id,
                SharedInferenceGroup(
                    id=plan.id,
                    name=plan.name,
                    mode="single_host",
                    leader_node_id=own.id,
                    node_ids=[own.id],
                    model=plan.model_alias,
                    engine="llama_cpp",
                    parallelism="pipeline",
                    device_count=2,
                    private_transport=True,
                ),
            )
            # Candidate discovery must not depend on a new alias already being workspace-allowed.
            probe.requirements = {}
            if not base_permitted(session, probe, node):
                continue
            user = session.get(User, node.owner_id)
            candidates.append(
                {
                    "node_id": str(node.id),
                    "name": node.name,
                    "owner": user.display_name if user else "Owner",
                    "os": node.os,
                    "architecture": node.architecture,
                    "online": node.state == "online",
                    "setup_supported": SETUP_RUNTIME in node_view(session, node).runtimes,
                }
            )
    return {
        "node_id": str(own.id),
        "credential_id": str(credential.id),
        "workspaces": [{"id": str(w.id), "name": w.name} for w in workspaces[:128]],
        "computers": candidates[:128],
    }


@router.post("/groups")
def groups(_: OptionsRequest, request: Request, session: SessionDep) -> dict[str, object]:
    credential, node = owned(request, session)
    rows = session.scalars(
        select(SharedEngineSetup)
        .join(SharedEngineConsent, SharedEngineConsent.group_id == SharedEngineSetup.id)
        .where(SharedEngineConsent.node_id == node.id)
        .order_by(SharedEngineSetup.desired_running.desc(), SharedEngineSetup.created_at.desc())
        .limit(8)
    )
    visible = [
        view(session, row, node.id)
        for row in rows
        if workspace_access(session, credential.owner_id, row.workspace_id)
    ]
    return {"node_id": str(node.id), "groups": [v.model_dump(mode="json") for v in visible]}


@router.post("/create", response_model=EngineGroup, status_code=201)
def create(payload: EngineCreate, request: Request, session: SessionDep) -> EngineGroup:
    credential, own = owned(request, session)
    require_permission(session, credential.owner_id, "jobs.use")
    if not workspace_access(session, credential.owner_id, payload.workspace_id):
        raise HTTPException(404, "Workspace not found")
    if own.id not in payload.node_ids or (payload.mode == "single_host") != (
        len(payload.node_ids) == 1
    ):
        raise HTTPException(422, "Include this computer and choose a matching group type")
    plan = EngineProposal(**payload.model_dump(), id=uuid4(), leader_node_id=own.id)
    # Lock members in stable order to serialize competing invitations/start requests.
    nodes = list(
        session.scalars(
            select(Node).where(Node.id.in_(plan.node_ids)).order_by(Node.id).with_for_update()
        )
    )
    if len(nodes) != len(plan.node_ids) or any(
        SETUP_RUNTIME not in node_view(session, n).runtimes for n in nodes
    ):
        raise HTTPException(
            409, "Every selected computer needs the worker with Shared Inference setup"
        )
    for node in nodes:
        probe = probe_job(
            credential.owner_id,
            plan.workspace_id,
            SharedInferenceGroup(
                id=plan.id,
                name=plan.name,
                mode=plan.mode,
                leader_node_id=plan.leader_node_id,
                node_ids=plan.node_ids,
                model=plan.model_alias,
                engine="llama_cpp",
                parallelism="pipeline",
                device_count=max(2, len(plan.node_ids)),
                private_transport=True,
            ),
        )
        probe.requirements = {}
        if not base_permitted(session, probe, node):
            raise HTTPException(404, "A selected computer is not permitted in this workspace")
        pending = session.scalars(
            select(SharedEngineConsent).where(
                SharedEngineConsent.node_id == node.id, SharedEngineConsent.phase != "stopped"
            )
        ).all()
        if len(pending) >= 8:
            raise HTTPException(
                409, "A selected computer already has eight pending or enabled groups"
            )
    row = SharedEngineSetup(
        id=plan.id,
        owner_id=credential.owner_id,
        workspace_id=plan.workspace_id,
        leader_node_id=own.id,
        proposal=plan.model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    session.add_all(SharedEngineConsent(group_id=row.id, node_id=n.id) for n in nodes)
    session.flush()
    audit(
        session,
        "shared_engine_proposed",
        credential.owner_id,
        row.id,
        workspace_id=row.workspace_id,
        metadata={"participant_count": len(nodes)},
    )
    return view(session, row, own.id)


@router.post("/approve", response_model=EngineGroup)
def approve(payload: EngineApproval, request: Request, session: SessionDep) -> EngineGroup:
    credential, node = owned(request, session)
    row, member = member_row(session, payload.group_id, node.id)
    if row.desired_running:
        raise HTTPException(409, "Stop this group before changing local approval")
    if not workspace_access(session, node.owner_id, row.workspace_id):
        raise HTTPException(404, "Workspace not found")
    plan = proposal(row)
    if plan.mode == "single_host" and (
        len(payload.devices) < 2 or any(d.backend == "cpu" for d in payload.devices)
    ):
        raise HTTPException(422, "Select at least two available GPUs, or include another computer")
    if node.id != plan.leader_node_id and ipaddress.ip_address(payload.host).is_loopback:
        raise HTTPException(
            422, "Choose this computer's private network address for peer connections"
        )
    try:
        certificate = x509.load_pem_x509_certificate(payload.certificate.encode("ascii"))
        certificate.verify_directly_issued_by(certificate)
        expected = f"{node.id.hex}.{row.id.hex}.shared.godfather.invalid"
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if expected not in names.get_values_for_type(x509.DNSName) or not (
            certificate.not_valid_before_utc <= datetime.now(UTC) < certificate.not_valid_after_utc
        ):
            raise ValueError("Certificate scope or validity mismatch")
    except (
        ValueError,
        x509.ExtensionNotFound,
        UnicodeError,
        InvalidSignature,
        UnsupportedAlgorithm,
    ):
        raise HTTPException(
            422, "Use the certificate generated locally for this computer and group"
        ) from None
    member.approved, member.credential_id = True, credential.id
    member.configuration = payload.model_dump(mode="json")
    member.phase, member.error_code = "waiting", None
    session.flush()
    audit(
        session,
        "shared_engine_approved",
        credential.owner_id,
        row.id,
        workspace_id=row.workspace_id,
        metadata={"node_id": str(node.id), "device_count": len(payload.devices)},
    )
    return view(session, row, node.id)


@router.post("/control", response_model=EngineGroup)
def control(payload: EngineAction, request: Request, session: SessionDep) -> EngineGroup:
    credential, node = owned(request, session)
    row, member = member_row(session, payload.group_id, node.id)
    if payload.action == "withdraw":
        member.approved, member.phase = False, "stopped"
        member.configuration = {}
        row.desired_running = False
    else:
        if row.leader_node_id != node.id:
            raise HTTPException(
                403, "Only this group's initiating computer may start or stop the group"
            )
        if payload.action == "start":
            if row.desired_running:
                return view(session, row, node.id)
            if topology(session, row) is None or not permitted_members(session, row):
                raise HTTPException(
                    409, "Wait for all local owner approvals and workspace contribution permission"
                )
            nodes = list(
                session.scalars(
                    select(Node)
                    .where(Node.id.in_(proposal(row).node_ids))
                    .order_by(Node.id)
                    .with_for_update()
                )
            )
            if len(nodes) != len(proposal(row).node_ids):
                raise HTTPException(409, "A participating computer is unavailable")
            other = session.scalar(
                select(SharedEngineSetup.id)
                .join(SharedEngineConsent, SharedEngineConsent.group_id == SharedEngineSetup.id)
                .where(
                    SharedEngineConsent.node_id.in_(proposal(row).node_ids),
                    SharedEngineSetup.id != row.id,
                    SharedEngineSetup.desired_running.is_(True),
                )
                .limit(1)
            )
            if other:
                raise HTTPException(
                    409, "A selected computer already belongs to a running shared engine"
                )
            row.generation += 1
            for participant in consents(session, row.id):
                participant.phase, participant.error_code = "waiting", None
        row.desired_running = payload.action == "start"
    session.flush()
    audit(
        session,
        "shared_engine_" + payload.action,
        credential.owner_id,
        row.id,
        workspace_id=row.workspace_id,
    )
    return view(session, row, node.id)


@router.post("/report")
def report(payload: EngineReport, request: Request, session: SessionDep) -> dict[str, bool]:
    _, node = owned(request, session)
    row, member = member_row(session, payload.group_id, node.id)
    if payload.generation != row.generation:
        raise HTTPException(409, "This engine run has been superseded")
    if payload.phase in ("starting", "ready") and (
        not row.desired_running or not approved(session, member)
    ):
        raise HTTPException(409, "Shared engine approval was withdrawn or the group stopped")
    member.phase, member.error_code = payload.phase, payload.error_code
    if payload.phase in ("starting", "stopped"):
        # The local controller has stopped its previous runner. Retire only an idle
        # session; never reset a live attempt or bypass a manually drained node.
        session.refresh(node, with_for_update=True)
        active = session.scalar(
            select(Job.id)
            .where(Job.assigned_node_id == node.id, Job.status.in_(("ASSIGNED", "RUNNING")))
            .limit(1)
        )
        if active and payload.phase == "starting":
            raise HTTPException(409, "Wait for this computer's current job or lease to finish")
        if not active:
            node.session_id, node.last_heartbeat_at = None, None
            transition(session, node, "offline")
    if payload.phase in ("error", "stopped"):
        row.desired_running = False
    return {"recorded": True}


def managed_permitted(session: Session, group: SharedInferenceGroup) -> bool:
    row = session.get(SharedEngineSetup, group.id)
    return row is None or (
        row.desired_running
        and topology(session, row) == group
        and all(m.phase == "ready" for m in consents(session, row.id))
    )
