"""Small PostgreSQL scheduler; no queue or process memory is authoritative."""

from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from godfather_contracts import ModelDeployment, NodeView
from godfather_contracts.jobs import Requirements
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.logging import correlation_id
from godfather_api.models import (
    AccessCredential,
    Attempt,
    Event,
    Job,
    Node,
    User,
    WorkflowRun,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import connection_at, node_view

ACTIVE = ("ASSIGNED", "RUNNING")
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")
SCHEDULER_LOCK = 7040401


def workspace_access(session: Session, owner_id: UUID, workspace_id: UUID) -> bool:
    workspace = session.get(Workspace, workspace_id)
    return workspace is not None and (
        workspace.owner_id == owner_id
        or session.get(WorkspaceMember, (workspace_id, owner_id)) is not None
    )


def permitted(session: Session, job: Job, node: Node) -> bool:
    owner = session.get(User, job.owner_id)
    if (
        owner is None
        or not owner.enabled
        or not workspace_access(session, job.owner_id, job.workspace_id)
    ):
        return False
    if not workspace_access(session, node.owner_id, job.workspace_id):
        return False
    if node.owner_id == job.owner_id:
        return True
    policy = node.contribution_policy
    allowed_owners = policy.get("allowed_job_owner_ids", [])
    allowed_workspaces = policy.get("allowed_workspace_ids", [])
    return (
        isinstance(allowed_owners, list)
        and isinstance(allowed_workspaces, list)
        and node.scheduling_policy != "dedicated"
        and str(job.owner_id) in allowed_owners
        and str(job.workspace_id) in allowed_workspaces
    )


def matches(requirements: Requirements, node: NodeView, reserved: list[Requirements]) -> bool:
    """Fail closed on unknown required resources, with conservative reservations."""
    if requirements.model_selection is not None:
        if node.inference_protocol_version != 1:
            return False
    elif node.job_protocol_version != 1 or node.resources.source != "simulated":
        return False
    if requirements.os not in ("any", node.os) or requirements.architecture not in (
        "any",
        node.architecture,
    ):
        return False
    if not set(requirements.capabilities) <= set(
        node.primary_capabilities + node.secondary_capabilities
    ):
        return False
    for required, available in (
        (requirements.runtimes, node.runtimes),
        (requirements.toolchains, node.toolchains),
        (requirements.dependencies, node.dependencies),
        (requirements.sandbox_modes, node.sandbox_modes),
    ):
        if not set(required) <= set(available):
            return False
    if not all(tool in node.worker_tools for tool in requirements.tools) or not set(
        requirements.tool_permissions
    ) <= set(node.tool_permissions):
        return False
    if not all(model in node.installed_models for model in requirements.models):
        return False
    if requirements.model_selection is not None:
        return deployment_for(requirements, node, reserved) is not None
    return resources_match(requirements, node, reserved)


def resources_match(
    requirements: Requirements, node: NodeView, reserved: list[Requirements]
) -> bool:
    if requirements.cpu_count + sum(r.cpu_count for r in reserved) > node.resources.cpu_count:
        return False
    ram = requirements.ram_bytes
    if ram:
        total, available_ram = node.resources.ram_bytes, node.resources.available_ram_bytes
        if total is None or available_ram is None:
            return False
        if ram > min(available_ram, total - sum(r.ram_bytes for r in reserved)):
            return False
    if requirements.backend not in ("any", "cpu") or requirements.gpu_memory_bytes:
        gpus = [g for g in node.resources.gpus if requirements.backend in ("any", g.backend)]
        if not gpus:
            return False
        if requirements.gpu_memory_bytes:
            free = max(
                (
                    g.memory_bytes - g.memory_used_bytes
                    for g in gpus
                    if g.memory_bytes is not None and g.memory_used_bytes is not None
                ),
                default=0,
            )
            if requirements.gpu_memory_bytes + sum(r.gpu_memory_bytes for r in reserved) > free:
                return False
    return True


def reservation(requirements: Requirements, deployment: ModelDeployment | None) -> Requirements:
    if deployment is None:
        return requirements
    return requirements.model_copy(
        update={
            "ram_bytes": max(requirements.ram_bytes, deployment.estimated_ram_bytes or 0),
            "gpu_memory_bytes": max(
                requirements.gpu_memory_bytes, deployment.estimated_vram_bytes or 0
            ),
        }
    )


def deployment_for(
    requirements: Requirements, node: NodeView, reserved: list[Requirements]
) -> ModelDeployment | None:
    selection = requirements.model_selection
    if selection is None:
        return None
    for model in sorted(node.model_deployments, key=lambda m: (m.provider_id, m.identifier)):
        capabilities = set(model.verified_capabilities)
        if selection.allow_declared_capabilities:
            capabilities.update(model.declared_capabilities)
        if (
            model.available
            and (selection.identifier is None or selection.identifier == model.identifier)
            and (selection.provider is None or selection.provider == model.provider)
            and set(selection.capabilities) <= capabilities
            and "chat" in model.operations
            and (not selection.stream or "stream" in model.operations)
            and (
                selection.context_window is None
                or (
                    model.context_window is not None
                    and model.context_window >= selection.context_window
                )
            )
            and resources_match(reservation(requirements, model), node, reserved)
        ):
            return model
    return None


def job_event(
    session: Session,
    job: Job,
    kind: str,
    now: datetime,
    attempt: Attempt | None = None,
    details: dict[str, object] | None = None,
    actor_id: UUID | None = None,
) -> None:
    session.add(
        Event(
            job_id=job.id,
            workspace_id=job.workspace_id,
            node_id=attempt.node_id if attempt else None,
            attempt_id=attempt.id if attempt else None,
            actor_id=actor_id,
            type="job." + kind,
            created_at=now,
            correlation_id=correlation_id.get() or uuid4().hex,
            details=details or {},
        )
    )


def finish_failure(
    session: Session, job: Job, attempt: Attempt, now: datetime, code: str, retryable: bool
) -> None:
    from godfather_api.workflow_service import end_attempt

    end_attempt(session, job, attempt, code, retryable and job.attempt_count <= job.retry_limit)
    attempt.status, attempt.finished_at = "FAILED", now
    attempt.error = {"code": code, "retryable": retryable}
    job.assigned_node_id = None
    job.result_refs = {}
    job_event(session, job, "attempt_failed", now, attempt, attempt.error)
    if retryable and job.attempt_count <= job.retry_limit:
        job.status = "RETRY_WAIT"
        delay = min(3600, job.retry_backoff_seconds * 2 ** (job.attempt_count - 1))
        job.next_run_at = now + timedelta(seconds=delay)
    else:
        job.status, job.next_run_at = "FAILED", None


def maintain(session: Session, settings: Settings, now: datetime) -> None:
    # Lock jobs before attempts everywhere. SKIP LOCKED avoids waiting behind reports/cancels.
    jobs = session.scalars(
        select(Job)
        .where(Job.status.in_(ACTIVE + ("RETRY_WAIT",)))
        .order_by(Job.id)
        .with_for_update(skip_locked=True)
    ).all()
    for job in jobs:
        if job.status == "RETRY_WAIT":
            if job.next_run_at is not None and job.next_run_at <= now:
                job.status, job.next_run_at = "PENDING", None
                previous = session.scalar(
                    select(Attempt).where(
                        Attempt.job_id == job.id, Attempt.number == job.attempt_count
                    )
                )
                job_event(session, job, "retried", now, previous)
            continue
        attempt = session.scalar(
            select(Attempt).where(Attempt.job_id == job.id, Attempt.number == job.attempt_count)
        )
        if attempt is None:
            continue
        expired = attempt.lease_expires_at <= now
        timed_out = attempt.deadline_at is not None and attempt.deadline_at <= now
        if expired or timed_out:
            if job.cancel_requested_at is not None:
                attempt.status, attempt.finished_at = "CANCELLED", now
                job.status, job.assigned_node_id = "CANCELLED", None
                job_event(session, job, "cancelled", now, attempt)
                from godfather_api.workflow_service import end_attempt

                end_attempt(session, job, attempt, "cancelled")
            else:
                code = "timeout" if timed_out else "lease_expired"
                job_event(session, job, code, now, attempt)
                finish_failure(session, job, attempt, now, code, True)
    session.flush()


def schedule(session: Session, settings: Settings, now: datetime) -> int:
    """Serialize short decisions across API processes; skip locked nodes/jobs.

    Lock order is credential (HTTP only), node, job. The scheduler never locks
    credentials. Its advisory try-lock avoids contention and protects fair turns.
    """
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SCHEDULER_LOCK}):
        return 0
    from godfather_api.workflow_service import eligible

    maintain(session, settings, now)
    # Credential revocation/disabled owner is checked again on delivery and reports.
    nodes = session.scalars(
        select(Node)
        .join(AccessCredential, AccessCredential.node_id == Node.id)
        .join(User, User.id == Node.owner_id)
        .where(
            Node.state == "online",
            Node.connection_status == "online",
            User.enabled.is_(True),
            AccessCredential.revoked.is_(False),
            AccessCredential.kind == "worker",
        )
        .order_by(Node.id)
        .with_for_update(of=Node, skip_locked=True)
    ).all()
    nodes = [n for n in nodes if connection_at(n.last_heartbeat_at, now, settings) == "online"]
    views = {n.id: node_view(session, n) for n in nodes}
    active_jobs = session.scalars(select(Job).where(Job.status.in_(ACTIVE))).all()
    reservations: dict[UUID, list[Requirements]] = {n.id: [] for n in nodes}
    active_by_owner = Counter(j.owner_id for j in active_jobs)
    for job in active_jobs:
        if job.assigned_node_id in reservations:
            attempt = session.scalar(
                select(Attempt).where(Attempt.job_id == job.id, Attempt.number == job.attempt_count)
            )
            deployment = None
            if attempt and attempt.result.get("deployment"):
                deployment = ModelDeployment.model_validate(attempt.result["deployment"])
            reservations[job.assigned_node_id].append(
                reservation(Requirements.model_validate(job.requirements), deployment)
            )
    # No fixed queue window: an incompatible head cannot hide compatible queued jobs.
    pending = list(
        session.scalars(
            select(Job)
            .where(
                Job.status == "PENDING",
                Job.type.in_(
                    ("synthetic.echo", "synthetic.fail", "inference.text", "agent.workflow")
                ),
            )
            .order_by(Job.priority.desc(), Job.created_at, Job.id)
            .with_for_update(skip_locked=True)
        ).all()
    )
    users = {u.id: u for u in session.scalars(select(User)).all()}
    turn = session.scalar(select(func.max(User.scheduling_turn))) or 0
    count = 0
    while pending:
        pending.sort(
            key=lambda j: (
                active_by_owner[j.owner_id],
                users[j.owner_id].scheduling_turn,
                -j.priority,
                j.created_at,
                str(j.id),
            )
        )
        selected = False
        for job in list(pending):
            try:
                requirements = Requirements.model_validate(job.requirements)
            except ValidationError:
                continue  # Legacy schema-only rows cannot bypass typed execution validation.
            candidates = [
                n
                for n in nodes
                if len(reservations[n.id]) < n.concurrency_limit
                and permitted(session, job, n)
                and eligible(session, job, n, views[n.id])
                and matches(requirements, views[n.id], reservations[n.id])
            ]
            # A preferred owner gets first refusal while it has compatible queued work.
            candidates = [
                n
                for n in candidates
                if n.scheduling_policy != "preferred"
                or n.owner_id == job.owner_id
                or not any(
                    queued.owner_id == n.owner_id
                    and permitted(session, queued, n)
                    and eligible(session, queued, n, views[n.id])
                    and matches(
                        Requirements.model_validate(queued.requirements),
                        views[n.id],
                        reservations[n.id],
                    )
                    for queued in pending
                )
            ]
            if not candidates:
                continue
            candidates.sort(
                key=lambda n: (
                    0 if n.scheduling_policy == "preferred" and n.owner_id == job.owner_id else 1,
                    -len(set(requirements.capabilities) & set(views[n.id].primary_capabilities)),
                    len(reservations[n.id]),
                    views[n.id].resources.cpu_percent or 0,
                    str(n.id),
                )
            )
            node = candidates[0]
            deployment = deployment_for(requirements, views[node.id], reservations[node.id])
            if job.type == "agent.workflow":
                run = session.get(WorkflowRun, job.id)
                assert run is not None
                if run.recovery_node_id is None:
                    run.recovery_node_id = node.id
            job.attempt_count += 1
            job.fencing_token += 1
            job.status, job.assigned_node_id = "ASSIGNED", node.id
            deadline = now + timedelta(seconds=job.timeout_seconds)
            attempt = Attempt(
                id=uuid4(),
                job_id=job.id,
                node_id=node.id,
                session_id=node.session_id,
                number=job.attempt_count,
                fencing_token=job.fencing_token,
                status="ASSIGNED",
                created_at=now,
                deadline_at=deadline,
                lease_expires_at=min(
                    deadline, now + timedelta(seconds=settings.execution_lease_seconds)
                ),
                result={"deployment": deployment.model_dump(mode="json")} if deployment else {},
            )
            session.add(attempt)
            session.flush()
            job_event(session, job, "assigned", now, attempt, {"fencing_token": job.fencing_token})
            turn += 1
            users[job.owner_id].scheduling_turn = turn
            active_by_owner[job.owner_id] += 1
            reservations[node.id].append(reservation(requirements, deployment))
            pending.remove(job)
            count += 1
            selected = True
            break
        if not selected:
            break
    return count


def scheduler_tick(database: Database, settings: Settings, now: datetime | None = None) -> int:
    with database.sessions.begin() as session:
        return schedule(session, settings, now or datetime.now(UTC))
