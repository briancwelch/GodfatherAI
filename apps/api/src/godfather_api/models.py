"""Initial durable schema only. No registration, scheduling, leases or workflow execution."""

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


class Workspace(Entity, Owned, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(200))
    is_shared: Mapped[bool] = mapped_column(Boolean, server_default="false")


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
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    definition: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")


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
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attempt(Entity, Base):
    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "number", name="uq_attempts_job_number"),
        UniqueConstraint("job_id", "fencing_token", name="uq_attempts_job_fencing"),
        UniqueConstraint("id", "job_id", name="uq_attempts_id_job"),
        CheckConstraint("number > 0 AND fencing_token > 0", name="positive_tokens"),
        CheckConstraint(
            "status IN ('ASSIGNED','RUNNING','COMPLETED','FAILED','CANCELLED')", name="status"
        ),
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    node_id: Mapped[UUID] = mapped_column(ForeignKey("nodes.id", ondelete="RESTRICT"))
    number: Mapped[int] = mapped_column(Integer)
    fencing_token: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), server_default="ASSIGNED")
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
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    attempt_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    format_version: Mapped[int] = mapped_column(Integer, server_default="1")
    artifact_ref: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))


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
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    workspace_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    job_id: Mapped[UUID | None] = mapped_column(index=True)
    node_id: Mapped[UUID | None] = mapped_column(ForeignKey("nodes.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
