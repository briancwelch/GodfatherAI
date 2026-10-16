"""Real PostgreSQL tests. Only run against the explicitly disposable test database."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from fastapi.testclient import TestClient
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.migrations import migration_config, migration_head
from godfather_api.models import (
    Agent,
    Attempt,
    Base,
    Capability,
    Checkpoint,
    Event,
    Job,
    Model,
    Node,
    NodeCapability,
    NodeModel,
    User,
    Workspace,
    WorkspaceMember,
)
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


@pytest.fixture
def db() -> Iterator[Database]:
    if os.getenv("GODFATHER_RUN_INTEGRATION") != "1":
        pytest.skip("set GODFATHER_RUN_INTEGRATION=1 with a disposable godfather_test database")
    settings = Settings()
    if settings.environment != "test" or settings.database_name != "godfather_test":
        pytest.fail("integration tests require environment=test and database_name=godfather_test")
    database = Database(settings)
    # Reversibility is exercised only on this explicitly disposable test database.
    command.upgrade(migration_config(), "head")
    command.downgrade(migration_config(), "base")
    command.upgrade(migration_config(), "head")
    seed_graph(database)
    yield database
    database.close()


def test_migration_matches_metadata_and_is_idempotent(db: Database) -> None:
    command.upgrade(migration_config(), "head")
    command.check(migration_config())
    assert set(inspect(db.engine).get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    with db.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version")) == migration_head()
        )
        assert connection.scalar(text("SHOW timezone")) == "UTC"
    assert db.ready()


def test_readiness_rejects_schema_drift_and_recovers(db: Database) -> None:
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='unexpected_revision'"))
    try:
        with TestClient(create_app(Settings())) as client:
            assert client.get("/health/ready").status_code == 503
            assert client.get("/health/live").status_code == 200
    finally:
        with db.engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num=:head"), {"head": migration_head()}
            )
    assert db.ready()


def test_phase03_upgrade_preserves_phase02_nodes(db: Database) -> None:
    with db.sessions() as session:
        node_id = session.scalar(select(Node.id))
    command.downgrade(migration_config(), "0001_initial")
    with db.engine.connect() as connection:
        assert connection.scalar(text("SELECT id FROM nodes LIMIT 1")) == node_id
    command.upgrade(migration_config(), "head")
    with db.sessions() as session:
        node = session.get(Node, node_id)
        assert node is not None and node.connection_status == "offline"
        assert node.session_id is None


def seed_graph(db: Database) -> UUID:
    """Synthetic fixtures only; no provider keys, host paths, or real personal data."""
    with db.sessions.begin() as session:
        owner = User(email="synthetic@example.invalid", display_name="Synthetic owner")
        session.add(owner)
        session.flush()
        workspace = Workspace(owner_id=owner.id, name="Synthetic workspace")
        node = Node(
            owner_id=owner.id,
            name="Synthetic node",
            os="linux",
            os_version="test",
            architecture="x86_64",
        )
        capability = Capability(name="synthetic")
        model = Model(owner_id=owner.id, name="Synthetic model", provider="test", identifier="test")
        session.add_all([workspace, node, capability, model])
        session.flush()
        agent = Agent(owner_id=owner.id, workspace_id=workspace.id, name="Synthetic agent")
        session.add_all(
            [
                agent,
                WorkspaceMember(workspace_id=workspace.id, user_id=owner.id),
                NodeCapability(node_id=node.id, capability_id=capability.id),
                NodeModel(node_id=node.id, model_id=model.id, runtime="test", backend="cpu"),
            ]
        )
        session.flush()
        job = Job(owner_id=owner.id, workspace_id=workspace.id, agent_id=agent.id, type="synthetic")
        session.add(job)
        session.flush()
        attempt = Attempt(
            job_id=job.id,
            node_id=node.id,
            number=1,
            fencing_token=1,
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        session.add(attempt)
        session.flush()
        session.add_all(
            [
                Checkpoint(
                    job_id=job.id,
                    attempt_id=attempt.id,
                    version=1,
                    artifact_ref="artifact://synthetic/v1",
                    checksum="a" * 64,
                ),
                Event(
                    actor_id=owner.id,
                    workspace_id=workspace.id,
                    job_id=job.id,
                    node_id=node.id,
                    type="synthetic.test",
                ),
            ]
        )
        return job.id


def test_persistence_across_application_and_pool_restart(db: Database) -> None:
    with db.sessions() as session:
        job_id = session.scalar(select(Job.id))
        assert job_id is not None
    with TestClient(create_app(Settings())) as client:
        assert client.get("/health/ready").status_code == 200
    db.close()
    reopened = Database(Settings())
    try:
        with TestClient(create_app(Settings())) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200
        with reopened.sessions() as session:
            job = session.get(Job, job_id)
            assert job is not None and job.status == "PENDING"
            checkpoint = session.scalar(select(Checkpoint).where(Checkpoint.job_id == job_id))
            assert checkpoint is not None and checkpoint.artifact_ref == "artifact://synthetic/v1"
            assert checkpoint.created_at.tzinfo is not None
            assert session.scalar(select(User.role)) == "member"
            assert session.scalar(select(Workspace.is_shared)) is False
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE jobs SET status='INVALID'",
        "UPDATE jobs SET timeout_seconds=0",
        "UPDATE nodes SET os='unknown'",
        "UPDATE nodes SET concurrency_limit=0",
        "UPDATE attempts SET fencing_token=0",
        "INSERT INTO attempts SELECT * FROM attempts LIMIT 1",
        "INSERT INTO attempts (id,job_id,node_id,number,fencing_token,lease_expires_at) "
        "SELECT gen_random_uuid(),job_id,node_id,number+1,fencing_token,lease_expires_at "
        "FROM attempts LIMIT 1",
        "INSERT INTO attempts (id,job_id,node_id,number,fencing_token,lease_expires_at) "
        "SELECT gen_random_uuid(),job_id,node_id,number,fencing_token+1,lease_expires_at "
        "FROM attempts LIMIT 1",
        "UPDATE checkpoints SET version=0",
        "UPDATE users SET role='machine_admin'",
        "UPDATE jobs SET owner_id='00000000-0000-0000-0000-000000000000'",
    ],
)
def test_database_rejects_invalid_records(db: Database, statement: str) -> None:
    with db.engine.connect() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(text(statement))
        connection.rollback()


def test_cross_workspace_agent_reference_is_rejected(db: Database) -> None:
    with db.sessions.begin() as session:
        owner = session.scalar(select(User))
        agent = session.scalar(select(Agent))
        assert owner is not None and agent is not None
        other = Workspace(owner_id=owner.id, name="Other workspace")
        session.add(other)
        session.flush()
        other_id = other.id
        owner_id, agent_id = owner.id, agent.id
    with db.sessions() as session:
        session.add(
            Job(owner_id=owner_id, workspace_id=other_id, agent_id=agent_id, type="invalid")
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_checkpoint_must_belong_to_its_attempt_job(db: Database) -> None:
    with db.sessions.begin() as session:
        job = session.scalar(select(Job))
        attempt = session.scalar(select(Attempt))
        assert job is not None and attempt is not None
        other = Job(owner_id=job.owner_id, workspace_id=job.workspace_id, type="synthetic")
        session.add(other)
        session.flush()
        other_id, attempt_id = other.id, attempt.id
    with db.sessions() as session:
        session.add(
            Checkpoint(
                job_id=other_id,
                attempt_id=attempt_id,
                version=1,
                artifact_ref="artifact://invalid",
                checksum="b" * 64,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_event_must_use_its_jobs_workspace(db: Database) -> None:
    with db.sessions.begin() as session:
        job = session.scalar(select(Job))
        assert job is not None
        other = Workspace(owner_id=job.owner_id, name="Other event workspace")
        session.add(other)
        session.flush()
        other_id, job_id = other.id, job.id
    with db.sessions() as session:
        session.add(Event(workspace_id=other_id, job_id=job_id, type="invalid"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
