"""Independent API-inference authorization; never accepts or returns API keys."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from godfather_contracts import Contract, ModelSelection
from godfather_contracts.execution import AttemptIdentity, Requirements
from godfather_contracts.providers import (
    ConnectionCheckResult,
    ConnectionCreate,
    ConnectionPolicy,
    InvocationRequest,
    InvocationSettlement,
    ModelRate,
    ProviderGrant,
    estimated_cost,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from godfather_api.models import (
    AccountProviderKey,
    Event,
    Job,
    Node,
    ProviderConnection,
    ProviderConnectionGrant,
    ProviderInvocation,
)
from godfather_api.nodes import SessionDep, authenticate, connection_at, node_view
from godfather_api.scheduler import workspace_access

router = APIRouter(prefix="/api/v1")


def audit(session: Session, owner: UUID, connection: UUID, action: str) -> None:
    row = session.get(ProviderConnection, connection)
    session.add(
        Event(
            actor_id=owner,
            node_id=row.node_id if row else None,
            type="provider." + action,
            details={"connection_id": str(connection)},
        )
    )


def owned(session: Session, identifier: UUID, owner: UUID) -> ProviderConnection:
    row = session.scalar(
        select(ProviderConnection)
        .where(ProviderConnection.id == identifier, ProviderConnection.owner_id == owner)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Provider connection not found")
    return row


def allowed(session: Session, job: Job, node: Node) -> bool:
    selection = Requirements.model_validate(job.requirements or {}).model_selection
    if selection is None or selection.connection_id is None:
        return selection is None or selection.provider not in ("openai", "anthropic", "gemini")
    row = session.get(ProviderConnection, selection.connection_id)
    if row is None or row.revoked or row.node_id != node.id or row.owner_id != node.owner_id:
        return False
    policy = ConnectionPolicy.model_validate(row.policy)
    if not policy.enabled or not selection.paid_consent or selection.provider != row.provider:
        return False
    if row.account_key_id:
        key = session.get(AccountProviderKey, row.account_key_id)
        if (
            key is None
            or not key.enabled
            or key.owner_id != job.owner_id
            or key.owner_id != row.owner_id
            or str(node.id) not in key.allowed_node_ids
        ):
            return False
        if selection.identifier not in {m.get("identifier") for m in key.model_catalog}:
            return False
        if "image_generation" in selection.required_operations and (
            policy.billing != "provider"
            or not any(
                m.get("identifier") == selection.identifier and m.get("modality") == "image"
                for m in key.model_catalog
            )
        ):
            return False
    elif "image_generation" in selection.required_operations:
        return False
    if policy.billing != "provider" and selection.identifier not in {
        r.identifier for r in policy.rates
    }:
        return False
    if job.owner_id == row.owner_id:
        return True
    if policy.sharing == "private":
        return False
    if (
        job.owner_id not in policy.allowed_user_ids
        or job.workspace_id not in policy.allowed_workspace_ids
    ):
        return False
    grant = session.get(ProviderConnectionGrant, selection.grant_id) if selection.grant_id else None
    if (
        grant is None
        or grant.revoked
        or grant.connection_id != row.id
        or grant.owner_id != row.owner_id
    ):
        return False
    scope = ProviderGrant.model_validate(grant.scope)
    return (
        scope.user_id == job.owner_id
        and scope.workspace_id == job.workspace_id
        and scope.model == selection.identifier
        and scope.expires_at > datetime.now(UTC)
        and scope.job_id in (None, job.id)
        and (policy.sharing != "approval_required" or scope.job_id == job.id)
    )


def selection_visible(
    session: Session, selection: ModelSelection, actor: UUID, workspace: UUID, node: Node
) -> ModelSelection | None:
    probe = Job(
        id=uuid4(),
        owner_id=actor,
        workspace_id=workspace,
        requirements=Requirements(model_selection=selection).model_dump(mode="json"),
    )
    # A catalog is informational: borrowers see models only after a scoped grant exists.
    if allowed(session, probe, node):
        return selection
    for record in session.scalars(
        select(ProviderConnectionGrant).where(
            ProviderConnectionGrant.connection_id == selection.connection_id,
            ProviderConnectionGrant.revoked.is_(False),
        )
    ):
        scope = ProviderGrant.model_validate(record.scope)
        if (
            scope.user_id != actor
            or scope.workspace_id != workspace
            or scope.model != selection.identifier
        ):
            continue
        chosen = selection.model_copy(update={"grant_id": record.id})
        probe.id = scope.job_id or uuid4()
        probe.requirements = Requirements(model_selection=chosen).model_dump(mode="json")
        if allowed(session, probe, node):
            return chosen
    return None


def totals(session: Session, identifier: UUID, grant_id: UUID | None = None) -> tuple[int, int]:
    query = select(ProviderInvocation).where(ProviderInvocation.connection_id == identifier)
    if grant_id is not None:
        query = query.where(ProviderInvocation.grant_id == grant_id)
    settled = liability = 0
    for call in session.scalars(query):
        if call.settled_microusd is None:
            liability += call.reserved_microusd
        else:
            settled += call.settled_microusd
    return settled, liability


@router.get("/provider-connections")
def connections(request: Request, session: SessionDep) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    result = []
    for row in session.scalars(
        select(ProviderConnection)
        .where(ProviderConnection.owner_id == actor.owner_id)
        .order_by(ProviderConnection.created_at)
    ):
        node = session.get(Node, row.node_id)
        settled, liability = totals(session, row.id)
        deployments = (
            [
                m.model_dump(mode="json")
                for m in node_view(session, node).model_deployments
                if m.connection_id == row.id and m.provider == row.provider
            ]
            if node
            else []
        )
        healthy = (
            node is not None
            and node.state == "online"
            and connection_at(node.last_heartbeat_at, datetime.now(UTC), request.app.state.settings)
            == "online"
        )
        result.append(
            {
                "id": str(row.id),
                "owner_id": str(row.owner_id),
                "node_id": str(row.node_id),
                "name": row.name,
                "provider": row.provider,
                "revoked": row.revoked,
                "policy": row.policy,
                "models": deployments,
                "available": healthy and bool(deployments) and not row.revoked,
                "estimated_microusd": settled,
                "reserved_microusd": liability,
                "billing_status": "estimates; not provider invoices",
                "check_supported": node is not None
                and "provider-connections-v1" in node_view(session, node).runtimes,
            }
        )
        result[-1]["test"] = row.test_result
    return result


@router.post("/provider-connections", status_code=201)
def create(payload: ConnectionCreate, request: Request, session: SessionDep) -> dict[str, str]:
    actor = authenticate(request, session, "human")
    node = session.scalar(
        select(Node).where(Node.id == payload.node_id, Node.owner_id == actor.owner_id)
    )
    if node is None:
        raise HTTPException(404, "Owned worker not found")
    row = ProviderConnection(
        owner_id=actor.owner_id,
        node_id=node.id,
        provider=payload.provider,
        name=payload.name,
        policy=ConnectionPolicy().model_dump(mode="json"),
    )
    session.add(row)
    session.flush()
    audit(session, actor.owner_id, row.id, "created")
    return {
        "id": str(row.id),
        "credential_setup": (
            "Enter the API key locally using godfather-worker provider; never upload it here"
        ),
    }


@router.post("/provider-connections/{connection_id}/policy")
def policy(
    connection_id: UUID, payload: ConnectionPolicy, request: Request, session: SessionDep
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    row = owned(session, connection_id, actor.owner_id)
    if row.revoked:
        raise HTTPException(409, "Revoked connections cannot be enabled; create a new connection")
    row.policy = payload.model_dump(mode="json")
    audit(session, actor.owner_id, row.id, "policy_changed")
    return {"saved": True}


class Control(Contract):
    action: Literal["revoke", "disable"]


@router.post("/provider-connections/{connection_id}/control")
def control(
    connection_id: UUID, payload: Control, request: Request, session: SessionDep
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    row = owned(session, connection_id, actor.owner_id)
    if payload.action == "revoke":
        row.revoked = True
    row.policy = {**row.policy, "enabled": False}
    audit(session, actor.owner_id, row.id, payload.action)
    return {"saved": True}


@router.post("/provider-connections/{connection_id}/grants", status_code=201)
def grant(
    connection_id: UUID, payload: ProviderGrant, request: Request, session: SessionDep
) -> dict[str, str]:
    actor = authenticate(request, session, "human")
    if payload.expires_at.tzinfo is None or payload.expires_at <= datetime.now(UTC):
        raise HTTPException(422, "Use an active connection and a future timezone-aware expiry")
    if not workspace_access(session, actor.owner_id, payload.workspace_id) or not workspace_access(
        session, payload.user_id, payload.workspace_id
    ):
        raise HTTPException(404, "Both users must have workspace access")
    job = None
    if payload.job_id:
        job = session.scalar(select(Job).where(Job.id == payload.job_id).with_for_update())
        if (
            job is None
            or job.owner_id != payload.user_id
            or job.workspace_id != payload.workspace_id
        ):
            raise HTTPException(404, "Job not found in the grant scope")
        selection = Requirements.model_validate(job.requirements).model_selection
        if (
            job.status != "PENDING"
            or selection is None
            or selection.connection_id != connection_id
            or selection.identifier != payload.model
            or not selection.paid_consent
        ):
            raise HTTPException(
                409, "Per-job approval requires a pending job with this explicit paid route"
            )
    row = owned(session, connection_id, actor.owner_id)
    if row.revoked:
        raise HTTPException(409, "Connection is revoked")
    record = ProviderConnectionGrant(
        connection_id=row.id, owner_id=actor.owner_id, scope=payload.model_dump(mode="json")
    )
    session.add(record)
    session.flush()
    if job is not None:
        requirements = Requirements.model_validate(job.requirements)
        assert requirements.model_selection is not None
        requirements.model_selection.grant_id = record.id
        job.requirements = requirements.model_dump(mode="json")
        from godfather_api.scheduler import job_event

        job_event(session, job, "provider_grant_bound", datetime.now(UTC), actor_id=actor.owner_id)
    audit(session, actor.owner_id, row.id, "grant_created")
    return {"id": str(record.id)}


@router.post("/provider-connections/{connection_id}/grants/{grant_id}/revoke")
def revoke_grant(
    connection_id: UUID, grant_id: UUID, request: Request, session: SessionDep
) -> dict[str, bool]:
    actor = authenticate(request, session, "human")
    owned(session, connection_id, actor.owner_id)
    row = session.get(ProviderConnectionGrant, grant_id)
    if row is None or row.connection_id != connection_id:
        raise HTTPException(404, "Grant not found")
    row.revoked = True
    audit(session, actor.owner_id, connection_id, "grant_revoked")
    return {"saved": True}


@router.get("/provider-connections/{connection_id}/usage")
def usage(connection_id: UUID, request: Request, session: SessionDep) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    owned(session, connection_id, actor.owner_id)
    return [
        {
            "id": str(c.id),
            "job_id": str(c.job_id),
            "attempt_id": str(c.attempt_id),
            "payer_id": str(c.payer_id),
            "submitter_id": str(c.submitter_id),
            "status": c.status,
            "reserved_microusd": c.reserved_microusd,
            "estimated_microusd": c.settled_microusd,
            "usage": c.usage,
            "price": c.price,
        }
        for c in session.scalars(
            select(ProviderInvocation)
            .where(ProviderInvocation.connection_id == connection_id)
            .order_by(ProviderInvocation.created_at.desc())
            .limit(200)
        )
    ]


@router.get("/provider-connections/{connection_id}/grants")
def grants(connection_id: UUID, request: Request, session: SessionDep) -> list[dict[str, object]]:
    actor = authenticate(request, session, "human")
    owned(session, connection_id, actor.owner_id)
    return [
        {"id": str(g.id), "revoked": g.revoked, "scope": g.scope}
        for g in session.scalars(
            select(ProviderConnectionGrant)
            .where(ProviderConnectionGrant.connection_id == connection_id)
            .limit(200)
        )
    ]


@router.post("/provider-connections/{connection_id}/test")
def test(connection_id: UUID, request: Request, session: SessionDep) -> dict[str, str]:
    actor = authenticate(request, session, "human")
    row = owned(session, connection_id, actor.owner_id)
    if row.revoked:
        raise HTTPException(409, "Connection is revoked")
    node = session.get(Node, row.node_id)
    if node is None or "provider-connections-v1" not in node_view(session, node).runtimes:
        raise HTTPException(
            409, "Configure this connection on the worker and restart it before testing"
        )
    row.test_id = uuid4()
    row.test_result = {"status": "pending", "requested_at": datetime.now(UTC).isoformat()}
    audit(session, actor.owner_id, row.id, "test_requested")
    return {"status": "pending", "test_id": str(row.test_id)}


@router.post("/workers/{node_id}/provider-checks")
def checked(
    node_id: UUID, payload: ConnectionCheckResult, request: Request, session: SessionDep
) -> dict[str, bool]:
    from godfather_contracts.execution import JobPoll

    from godfather_api.jobs import worker_node

    node = worker_node(node_id, JobPoll(session_id=payload.session_id), request, session)
    row = session.scalar(
        select(ProviderConnection)
        .where(
            ProviderConnection.id == payload.connection_id,
            ProviderConnection.node_id == node.id,
            ProviderConnection.owner_id == node.owner_id,
        )
        .with_for_update()
    )
    if row is None or row.test_id != payload.test_id or row.revoked:
        raise HTTPException(404, "Connection check no longer active")
    row.test_result = {
        "status": payload.code,
        "models": list(payload.models),
        "checked_at": datetime.now(UTC).isoformat(),
    }
    row.test_id = None
    return {"saved": True}


@router.post("/workers/{node_id}/jobs/{job_id}/provider/authorize")
def reserve(
    node_id: UUID, job_id: UUID, payload: InvocationRequest, request: Request, session: SessionDep
) -> dict[str, object]:
    from godfather_api.jobs import lock_execution

    identity = AttemptIdentity(
        session_id=payload.session_id,
        attempt_id=payload.attempt_id,
        fencing_token=payload.fencing_token,
    )
    node, job, attempt = lock_execution(node_id, job_id, identity, request, session)
    if job.status != "RUNNING" or job.cancel_requested_at is not None:
        raise HTTPException(409, "Paid execution requires an active uncancelled attempt")
    selected = Requirements.model_validate(job.requirements).model_selection
    if selected is None or selected.connection_id is None or not allowed(session, job, node):
        raise HTTPException(403, "No explicit paid-inference authorization")
    row = session.scalar(
        select(ProviderConnection)
        .where(ProviderConnection.id == selected.connection_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    assert row is not None
    if selected.grant_id:
        current_grant = session.get(ProviderConnectionGrant, selected.grant_id)
        if current_grant is not None:
            session.refresh(current_grant)
    if not allowed(session, job, node):
        raise HTTPException(403, "Paid permission was withdrawn before reservation")
    settings = ConnectionPolicy.model_validate(row.policy)
    if "image_generation" in selected.required_operations:
        from godfather_contracts.workloads import CLOUD_IMAGE_RUNTIME, ImageSettings

        from godfather_api.workflow_service import workflow_assignment

        image = ImageSettings.model_validate(job.input_refs.get("image"))
        view = node_view(session, node)
        workflow = workflow_assignment(session, request.app.state.artifacts, job, attempt)
        if (
            settings.billing != "provider"
            or row.account_key_id is None
            or CLOUD_IMAGE_RUNTIME not in view.runtimes
            or "images.generate" not in view.tool_permissions
            or image.backend != selected.provider
            or image.model != selected.identifier
            or payload.call_key != "image"
            or len(workflow.agent.definition.workflow.steps) != 1
            or workflow.agent.definition.workflow.steps[0].kind != "image"
        ):
            raise HTTPException(403, "Cloud image execution requires an opted-in account route")
        if session.scalar(select(ProviderInvocation.id).where(ProviderInvocation.job_id == job.id)):
            raise HTTPException(
                409, "Review the previous image invocation before submitting a new job"
            )
    rate = next((r for r in settings.rates if r.identifier == selected.identifier), None)
    if settings.billing != "provider" and (
        rate is None
        or (datetime.now(UTC) - rate.verified_at).days > 30
        or rate.verified_at > datetime.now(UTC)
    ):
        raise HTTPException(409, "Owner must verify current documented pricing")
    if session.scalar(
        select(ProviderInvocation.id).where(
            ProviderInvocation.attempt_id == attempt.id,
            ProviderInvocation.call_key == payload.call_key,
        )
    ):
        raise HTTPException(
            409,
            "Invocation already reserved; reconcile rather than repeat a possibly billable call",
        )
    amount = (
        estimated_cost(rate, payload.input_bytes + 4096, payload.max_output_tokens)
        if rate is not None and settings.billing != "provider"
        else 0
    )
    spent, liability = totals(session, row.id)
    if settings.billing != "provider" and (
        amount <= 0
        or amount > settings.call_limit_microusd
        or spent + liability + amount > settings.lifetime_limit_microusd
    ):
        raise HTTPException(409, "Connection spending safeguard does not permit this call")
    if job.owner_id != row.owner_id:
        grant_row = session.get(ProviderConnectionGrant, selected.grant_id)
        assert grant_row is not None
        scope = ProviderGrant.model_validate(grant_row.scope)
        spent, liability = totals(session, row.id, grant_row.id)
        if spent + liability + amount > scope.limit_microusd:
            raise HTTPException(409, "Grant spending safeguard exhausted")
    call = ProviderInvocation(
        connection_id=row.id,
        grant_id=selected.grant_id if job.owner_id != row.owner_id else None,
        job_id=job.id,
        attempt_id=attempt.id,
        payer_id=row.owner_id,
        submitter_id=job.owner_id,
        call_key=payload.call_key,
        reserved_microusd=amount,
        price=rate.model_dump(mode="json")
        if rate is not None and settings.billing != "provider"
        else {"billing": "provider"},
    )
    session.add(call)
    session.flush()
    audit(session, job.owner_id, row.id, "invocation_reserved")
    return {"invocation_id": str(call.id), "reserved_microusd": amount}


@router.post("/workers/{node_id}/jobs/{job_id}/provider/settle")
def settle(
    node_id: UUID,
    job_id: UUID,
    payload: InvocationSettlement,
    request: Request,
    session: SessionDep,
) -> dict[str, bool]:
    # Accounting-only late settlement is independent of result fencing and policy revocation.
    actor = authenticate(request, session, "worker")
    call = session.scalar(
        select(ProviderInvocation)
        .where(ProviderInvocation.id == payload.invocation_id)
        .with_for_update()
    )
    from godfather_api.models import Attempt

    attempt = session.get(Attempt, payload.attempt_id)
    if (
        call is None
        or attempt is None
        or call.job_id != job_id
        or call.attempt_id != attempt.id
        or attempt.node_id != node_id
        or actor.node_id != node_id
        or attempt.session_id != payload.session_id
        or attempt.fencing_token != payload.fencing_token
    ):
        raise HTTPException(404, "Invocation not found")
    usage_data: dict[str, object] = {
        "input_tokens": payload.input_tokens,
        "output_tokens": payload.output_tokens,
        "pricing_supported": payload.pricing_supported,
    }
    if call.status == "settled":
        if call.usage != usage_data:
            raise HTTPException(409, "Usage was already settled")
        return {"saved": True}
    call.usage = usage_data
    if call.price.get("billing") == "provider":
        call.status = "settled"
        return {"saved": True}
    if (
        payload.input_tokens is None
        or payload.output_tokens is None
        or not payload.pricing_supported
    ):
        call.status = "reconciliation_required"
    else:
        call.settled_microusd = estimated_cost(
            ModelRate.model_validate(call.price), payload.input_tokens, payload.output_tokens
        )
        call.status = "settled"
    return {"saved": True}
