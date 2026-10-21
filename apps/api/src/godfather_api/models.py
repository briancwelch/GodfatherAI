"""Durable control-plane schema for identities and fenced synthetic execution."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        }
    )


class Entity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Owned:
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)


class User(Entity, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('platform_admin','contributor','member')", name="role"),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32), server_default="member")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    scheduling_turn: Mapped[int] = mapped_column(BigInteger, server_default="0")
    roles: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    picture: Mapped[str | None] = mapped_column(String(2048))


class GoogleIdentity(Entity, Base):
    __tablename__ = "google_identities"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    subject: Mapped[str] = mapped_column(String(255), unique=True)


class ProviderConnection(Entity, Owned, Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        UniqueConstraint("account_key_id", "node_id", name="uq_provider_account_node"),
    )
    node_id: Mapped[UUID] = mapped_column(ForeignKey("nodes.id", ondelete="RESTRICT"))
    provider: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    policy: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    revoked: Mapped[bool] = mapped_column(Boolean, server_default="false")
    test_id: Mapped[UUID | None]
    test_result: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    account_key_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("account_provider_keys.id", ondelete="RESTRICT")
    )


class AccountProviderKey(Entity, Owned, Base):
    __tablename__ = "account_provider_keys"
    __table_args__ = (UniqueConstraint("owner_id", "provider", name="uq_account_provider_owner"),)
    provider: Mapped[str] = mapped_column(String(32))
    encrypted_key: Mapped[str] = mapped_column(Text)
    model_catalog: Mapped[list[dict[str, object]]] = mapped_column(JSONB, server_default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    allowed_node_ids: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")


class ProviderConnectionGrant(Entity, Base):
    __tablename__ = "provider_connection_grants"
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="RESTRICT"), index=True
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    scope: Mapped[dict[str, object]] = mapped_column(JSONB)
    revoked: Mapped[bool] = mapped_column(Boolean, server_default="false")


class ProviderInvocation(Entity, Base):
    __tablename__ = "provider_invocations"
    __table_args__ = (
        UniqueConstraint("attempt_id", "call_key", name="uq_provider_invocation_call"),
    )
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="RESTRICT"), index=True
    )
    grant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("provider_connection_grants.id", ondelete="RESTRICT")
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="RESTRICT"))
    payer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    submitter_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    call_key: Mapped[str] = mapped_column(String(100))
    reserved_microusd: Mapped[int] = mapped_column(BigInteger)
    settled_microusd: Mapped[int | None] = mapped_column(BigInteger)
    price: Mapped[dict[str, object]] = mapped_column(JSONB)
    usage: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    status: Mapped[str] = mapped_column(String(32), server_default="reserved")


class AdministratorBootstrap(Base):
    """Durable singleton: once closed, environment changes cannot rearm bootstrap."""

    __tablename__ = "administrator_bootstrap"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    founder_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class HumanSession(Entity, Owned, Base):
    __tablename__ = "human_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Invitation(Entity, Base):
    __tablename__ = "invitations"
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String(320))
    roles: Mapped[list[str]] = mapped_column(JSONB)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, server_default="false")
    used_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class LoginTransaction(Entity, Base):
    __tablename__ = "login_transactions"
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(128))
    verifier: Mapped[str] = mapped_column(String(128))
    invitation_id: Mapped[UUID | None] = mapped_column(ForeignKey("invitations.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed: Mapped[bool] = mapped_column(Boolean, server_default="false")


class AuthenticationLimit(Base):
    __tablename__ = "authentication_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger)
    count: Mapped[int] = mapped_column(Integer)


class WorkerEnrollment(Entity, Owned, Base):
    __tablename__ = "worker_enrollments"
    challenge: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    replaces_credential_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("access_credentials.id", ondelete="RESTRICT")
    )


class Workspace(Entity, Owned, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(200))
    is_shared: Mapped[bool] = mapped_column(Boolean, server_default="false")
    allowed_models: Mapped[list[str] | None] = mapped_column(JSONB)
    allowed_tools: Mapped[list[str] | None] = mapped_column(JSONB)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (CheckConstraint("role IN ('admin','member')", name="role"),)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), server_default="member")


class Node(Entity, Owned, Base):
    __tablename__ = "nodes"
    __table_args__ = (
        CheckConstraint("os IN ('windows','macos','linux')", name="os"),
        CheckConstraint(
            "state IN ('online','suspect','offline','draining','disabled')", name="state"
        ),
        CheckConstraint("scheduling_policy IN ('dedicated','preferred','shared')", name="policy"),
        CheckConstraint("concurrency_limit > 0", name="concurrency"),
        CheckConstraint("protocol_version > 0", name="protocol"),
        CheckConstraint("connection_status IN ('online','suspect','offline')", name="connection"),
    )
    name: Mapped[str] = mapped_column(String(200))
    os: Mapped[str] = mapped_column(String(16))
    os_version: Mapped[str] = mapped_column(String(100))
    architecture: Mapped[str] = mapped_column(String(32))
    protocol_version: Mapped[int] = mapped_column(Integer, server_default="1")
    state: Mapped[str] = mapped_column(String(16), server_default="offline")
    scheduling_policy: Mapped[str] = mapped_column(String(16), server_default="shared")
    concurrency_limit: Mapped[int] = mapped_column(Integer, server_default="1")
    resources: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    runtimes: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    contribution_policy: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connection_status: Mapped[str] = mapped_column(String(16), server_default="offline")
    session_id: Mapped[UUID | None]


class AccessCredential(Entity, Owned, Base):
    __tablename__ = "access_credentials"
    __table_args__ = (
        CheckConstraint("kind IN ('admin','worker')", name="kind"),
        CheckConstraint(
            "(kind='admin' AND name IS NULL AND node_id IS NULL) OR "
            "(kind='worker' AND name IS NOT NULL)",
            name="scope",
        ),
        UniqueConstraint("owner_id", "name", name="uq_credentials_owner_name"),
    )
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str | None] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="RESTRICT"), unique=True
    )
    revoked: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Capability(Entity, Base):
    __tablename__ = "capabilities"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, server_default="")


class NodeCapability(Base):
    __tablename__ = "node_capabilities"
    __table_args__ = (CheckConstraint("specialty IN ('primary','secondary')", name="specialty"),)
    node_id: Mapped[UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    capability_id: Mapped[UUID] = mapped_column(
        ForeignKey("capabilities.id", ondelete="RESTRICT"), primary_key=True
    )
    specialty: Mapped[str] = mapped_column(String(16), server_default="secondary")


class Model(Entity, Owned, Base):
    __tablename__ = "models"
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(100))
    identifier: Mapped[str] = mapped_column(String(300))
    requirements: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")


class NodeModel(Base):
    __tablename__ = "node_models"
    node_id: Mapped[UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("models.id", ondelete="RESTRICT"), primary_key=True
    )
    runtime: Mapped[str] = mapped_column(String(100))
    backend: Mapped[str] = mapped_column(String(32))


class Agent(Entity, Owned, Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_agents_id_workspace"),
        UniqueConstraint(
            "workspace_id", "name", "version", name="uq_agents_workspace_name_version"
        ),
        CheckConstraint("version > 0", name="version"),
        UniqueConstraint("workspace_id", "agent_key", "version", name="uq_agents_key_version"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    agent_key: Mapped[UUID] = mapped_column(
        default=uuid4, server_default=sa_text("gen_random_uuid()")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Job(Entity, Owned, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_jobs_id_workspace"),
        ForeignKeyConstraint(
            ["agent_id", "workspace_id"],
            ["agents.id", "agents.workspace_id"],
            name="fk_jobs_agent_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('PENDING','ASSIGNED','RUNNING','RETRY_WAIT',"
            "'COMPLETED','FAILED','CANCELLED')",
            name="status",
        ),
        CheckConstraint("timeout_seconds > 0", name="timeout"),
        CheckConstraint("retry_limit >= 0", name="retry_limit"),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        Index("ix_jobs_workspace_status", "workspace_id", "status"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"))
    agent_id: Mapped[UUID | None]
    type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")
    priority: Mapped[int] = mapped_column(Integer, server_default="0")
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default="300")
    retry_limit: Mapped[int] = mapped_column(Integer, server_default="0")
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0")
    requirements: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    input_refs: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    result_refs: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    assigned_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="RESTRICT")
    )
    fencing_token: Mapped[int] = mapped_column(BigInteger, server_default="0")
    retry_backoff_seconds: Mapped[int] = mapped_column(Integer, server_default="1")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkpoint_ref: Mapped[str | None] = mapped_column(Text)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attempt(Entity, Base):
    __tablename__ = "attempts"
    __table_args__ = (
        Index(
            "uq_attempts_active_job",
            "job_id",
            unique=True,
            postgresql_where=sa_text("status IN ('ASSIGNED','RUNNING')"),
        ),
        UniqueConstraint("job_id", "number", name="uq_attempts_job_number"),
        UniqueConstraint("job_id", "fencing_token", name="uq_attempts_job_fencing"),
        UniqueConstraint("id", "job_id", name="uq_attempts_id_job"),
        CheckConstraint("number > 0 AND fencing_token > 0", name="positive_tokens"),
        CheckConstraint(
            "status IN ('ASSIGNED','RUNNING','COMPLETED','FAILED','CANCELLED','INTERRUPTED')",
            name="status",
        ),
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    node_id: Mapped[UUID] = mapped_column(ForeignKey("nodes.id", ondelete="RESTRICT"))
    number: Mapped[int] = mapped_column(Integer)
    fencing_token: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default="ASSIGNED")
    session_id: Mapped[UUID | None]
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    recovered_from_attempt_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("attempts.id", ondelete="RESTRICT")
    )
    resumed_checkpoint_version: Mapped[int] = mapped_column(Integer, server_default="0")
    result: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Checkpoint(Entity, Base):
    __tablename__ = "checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "job_id"],
            ["attempts.id", "attempts.job_id"],
            name="fk_checkpoints_attempt_job",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("job_id", "version", name="uq_checkpoints_job_version"),
        CheckConstraint("version > 0 AND format_version > 0", name="versions"),
        ForeignKeyConstraint(
            ["artifact_id", "job_id"],
            ["artifacts.id", "artifacts.job_id"],
            name="fk_checkpoints_artifact_job",
            ondelete="RESTRICT",
        ),
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    attempt_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    format_version: Mapped[int] = mapped_column(Integer, server_default="1")
    artifact_ref: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    artifact_id: Mapped[UUID | None]


class Artifact(Entity, Owned, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("id", "job_id", name="uq_artifacts_id_job"),
        ForeignKeyConstraint(
            ["attempt_id", "job_id"],
            ["attempts.id", "attempts.job_id"],
            name="fk_artifacts_attempt_job",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["jobs.id", "jobs.workspace_id"],
            name="fk_artifacts_job_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 8388608", name="size"),
        CheckConstraint("kind IN ('step_output','workflow_state')", name="kind"),
    )
    job_id: Mapped[UUID] = mapped_column(index=True)
    workspace_id: Mapped[UUID]
    attempt_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(32))
    checksum: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "cursor >= 0 AND cursor <= 32 AND checkpoint_version = cursor", name="cursor"
        ),
        CheckConstraint(
            "status IN ('READY','RUNNING','INTERRUPTED','COMPLETED','FAILED',"
            "'CANCELLED','REVIEW_REQUIRED')",
            name="status",
        ),
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), primary_key=True
    )
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"))
    workflow_id: Mapped[UUID]
    workflow_version: Mapped[int] = mapped_column(Integer)
    cursor: Mapped[int] = mapped_column(Integer, server_default="0")
    checkpoint_version: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(16), server_default="READY")
    recovery_error: Mapped[str | None] = mapped_column(String(64))
    # Retained as the first execution node for history; no longer restricts failover.
    recovery_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="RESTRICT")
    )


class WorkflowStepRecord(Entity, Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attempt_id", "job_id"],
            ["attempts.id", "attempts.job_id"],
            name="fk_workflow_steps_attempt_job",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["output_artifact_id", "job_id"],
            ["artifacts.id", "artifacts.job_id"],
            name="fk_workflow_steps_output_job",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("job_id", "step_id", "attempt_id", name="uq_workflow_steps_attempt"),
        Index(
            "uq_workflow_steps_completed",
            "job_id",
            "step_id",
            unique=True,
            postgresql_where=sa_text("status = 'COMPLETED'"),
        ),
        CheckConstraint(
            "status IN ('RUNNING','COMPLETED','INTERRUPTED','FAILED','CANCELLED')", name="status"
        ),
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    attempt_id: Mapped[UUID]
    step_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), server_default="RUNNING")
    input_refs: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    output_artifact_id: Mapped[UUID | None]
    metadata_refs: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    error_code: Mapped[str | None] = mapped_column(String(64))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Entity, Base):
    __tablename__ = "events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["jobs.id", "jobs.workspace_id"],
            name="fk_events_job_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint("job_id IS NULL OR workspace_id IS NOT NULL", name="job_scope"),
    )
    attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("attempts.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    workspace_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    job_id: Mapped[UUID | None] = mapped_column(index=True)
    node_id: Mapped[UUID | None] = mapped_column(ForeignKey("nodes.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
