"""Real PostgreSQL scheduling, concurrency and recovery with controlled time."""

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi import Request
from fastapi.testclient import TestClient
from godfather_api import jobs
from godfather_api.app import create_app
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.migrations import migration_config
from godfather_api.models import Attempt, Job, Node, User, Workspace, WorkspaceMember
from godfather_api.provision import provision
from godfather_api.scheduler import ACTIVE, scheduler_tick
from godfather_contracts import Registration
from godfather_contracts.execution import JobPoll
from godfather_contracts.jobs import SyntheticInput, SyntheticResult
from godfather_worker.jobs import synthetic_result
from godfather_worker.simulated import profile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def headers(credential: dict[str, str]) -> dict[str, str]:
    return {"Authorization": "Bearer " + credential["token"]}


class Harness:
    def __init__(self, database: Database, client: TestClient) -> None:
        self.database, self.client = database, client
        self.admin = provision(database, "admin", email="scheduler@example.invalid")
        with database.sessions.begin() as session:
            workspace = Workspace(owner_id=UUID(self.admin["owner_id"]), name="Synthetic only")
            session.add(workspace)
            session.flush()
            self.workspace_id = workspace.id
        self.workers: list[dict[str, str]] = []
        self.registrations: list[Registration] = []
        for name in ("LV-01", "LA-01"):
            worker = provision(database, "worker", owner_id=UUID(self.admin["owner_id"]), name=name)
            registration = Registration(
                **profile(name).model_dump(exclude={"job_protocol_version"}),
                job_protocol_version=1,
                session_id=uuid4(),
            )
            response = client.post(
                "/api/v1/workers/register",
                json=registration.model_dump(mode="json"),
                headers=headers(worker),
            )
            assert response.status_code == 200, response.text
            self.workers.append(worker)
            self.registrations.append(registration)

    def submit(self, **values: object) -> dict[str, Any]:
        response = self.client.post(
            "/api/v1/jobs",
            json={
                "workspace_id": str(self.workspace_id),
                "requirements": {"capabilities": ["coding"]},
                **values,
            },
            headers=headers(self.admin),
        )
        assert response.status_code == 201, response.text
        return dict(response.json())

    def get(self, job_id: str) -> dict[str, Any]:
        response = self.client.get(f"/api/v1/jobs/{job_id}", headers=headers(self.admin))
        assert response.status_code == 200, response.text
        return dict(response.json())

    def tick(self, now: datetime | None = None) -> int:
        return scheduler_tick(self.database, Settings(health_monitor_enabled=False), now)

    def poll(self, index: int = 0) -> dict[str, Any] | None:
        worker = self.workers[index]
        response = self.client.post(
            f"/api/v1/workers/{worker['credential_id']}/jobs/poll",
            json={"session_id": str(self.registrations[index].session_id)},
            headers=headers(worker),
        )
        assert response.status_code == 200, response.text
        return response.json()["assignment"]  # type: ignore[no-any-return]

    def report(
        self,
        assignment: dict[str, Any],
        action: str,
        index: int = 0,
        expected: int = 200,
        **values: object,
    ) -> dict[str, Any]:
        worker = self.workers[index]
        response = self.client.post(
            f"/api/v1/workers/{worker['credential_id']}/jobs/{assignment['job']['id']}/report",
            json={
                "session_id": str(self.registrations[index].session_id),
                "attempt_id": assignment["attempt_id"],
                "fencing_token": assignment["fencing_token"],
                "action": action,
                **values,
            },
            headers=headers(worker),
        )
        assert response.status_code == expected, response.text
        return dict(response.json())

    def start(self, assignment: dict[str, Any], index: int = 0) -> None:
        self.report(assignment, "ack", index)
        self.report(assignment, "start", index)

    def complete(self, assignment: dict[str, Any], index: int = 0) -> None:
        self.start(assignment, index)
        self.report(assignment, "progress", index, progress=100)
        self.report(assignment, "complete", index, result={"value": "done", "steps": 1})


@pytest.fixture
def h() -> Iterator[Harness]:
    if os.getenv("GODFATHER_RUN_INTEGRATION") != "1":
        pytest.skip("requires explicitly disposable PostgreSQL godfather_test")
    settings = Settings(health_monitor_enabled=False)
    if settings.environment != "test" or settings.database_name != "godfather_test":
        pytest.fail("Refusing to reset anything except godfather_test in test mode")
    command.upgrade(migration_config(), "head")
    command.downgrade(migration_config(), "base")
    command.upgrade(migration_config(), "head")
    database = Database(settings)
    try:
        with TestClient(create_app(settings)) as client:
            yield Harness(database, client)
    finally:
        database.close()


def test_submission_scope_validation_history_and_secret_safe_errors(h: Harness) -> None:
    assert (
        h.client.post("/api/v1/jobs", json={"workspace_id": str(h.workspace_id)}).status_code == 401
    )
    assert h.client.get("/api/v1/jobs", headers=headers(h.workers[0])).status_code == 401
    job = h.submit()
    assert job["status"] == "PENDING" and job["owner_id"] == h.admin["owner_id"]
    assert len(h.client.get("/api/v1/jobs", headers=headers(h.admin)).json()) == 1
    other = provision(h.database, "admin", email="private@example.invalid")
    for suffix in ("", "/events", "/attempts"):
        assert (
            h.client.get(f"/api/v1/jobs/{job['id']}{suffix}", headers=headers(other)).status_code
            == 404
        )
    assert h.client.get("/api/v1/jobs", headers=headers(other)).json() == []
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(other)).status_code == 404
    )
    invalid = h.client.post(
        "/api/v1/jobs",
        json={"workspace_id": str(h.workspace_id), "type": "coding", "token": h.admin["token"]},
        headers=headers(h.admin),
    )
    assert invalid.status_code == 422 and h.admin["token"] not in invalid.text
    assert (
        h.client.post(
            "/api/v1/jobs", json={"workspace_id": str(h.workspace_id)}, headers=headers(other)
        ).status_code
        == 404
    )
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.report(assignment, "start", expected=409)
    h.complete(assignment)
    events = h.client.get(f"/api/v1/jobs/{job['id']}/events", headers=headers(h.admin)).json()
    assert {e["type"] for e in events} >= {
        "job.submitted",
        "job.assigned",
        "job.started",
        "job.progress",
        "job.lease_renewed",
        "job.completed",
    }
    assert all(e["correlation_id"] and e["created_at"] for e in events)
    assert all(e["attempt_id"] and e["node_id"] for e in events if e["type"] != "job.submitted")


def test_primary_backup_matching_and_queued_incompatible_work(h: Harness) -> None:
    blocked = h.submit(requirements={"os": "linux"}, priority=100)
    first, second = h.submit(), h.submit()
    assert h.tick() == 2
    assert h.get(first["id"])["assigned_node_id"] == h.workers[0]["credential_id"]
    assert h.get(second["id"])["assigned_node_id"] == h.workers[1]["credential_id"]
    assert h.get(blocked["id"])["status"] == "PENDING"
    third = h.submit()
    assert h.tick() == 0 and h.get(third["id"])["status"] == "PENDING"


def test_concurrent_schedulers_and_duplicate_claims_do_not_conflict(h: Harness) -> None:
    jobs = [h.submit() for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(lambda _: h.tick(), range(8))) == 2
    with ThreadPoolExecutor(max_workers=4) as executor:
        deliveries = list(executor.map(lambda _: h.poll(), range(4)))
    assert len({d["attempt_id"] for d in deliveries if d}) == 1
    with h.database.sessions() as session:
        counts = session.execute(
            select(Attempt.job_id, func.count())
            .where(Attempt.status.in_(ACTIVE))
            .group_by(Attempt.job_id)
        ).all()
        assert len(counts) == 2 and all(count == 1 for _, count in counts)
    assert sum(h.get(j["id"])["status"] == "ASSIGNED" for j in jobs) == 2


def test_lease_expiration_reassignment_and_all_stale_reports_are_fenced(h: Harness) -> None:
    job = h.submit(retry={"limit": 1, "backoff_seconds": 0})
    h.tick()
    old = h.poll()
    assert old is not None
    h.start(old)
    now = datetime.now(UTC) + timedelta(seconds=31)
    h.tick(now)
    assert h.get(job["id"])["status"] == "RETRY_WAIT"
    with h.database.sessions.begin() as session:
        for node in session.scalars(select(Node)):
            node.last_heartbeat_at = now
    h.tick(now)
    new = h.poll()
    assert new is not None and new["fencing_token"] == old["fencing_token"] + 1
    for action in ("start", "progress", "renew", "complete", "fail", "cancelled"):
        h.report(old, action, expected=409)
    h.complete(new)
    h.report(old, "complete", expected=409, result={"value": "stale", "steps": 1})
    assert h.get(job["id"])["result"]["value"] == "done"
    attempts = h.client.get(f"/api/v1/jobs/{job['id']}/attempts", headers=headers(h.admin)).json()
    assert [a["status"] for a in attempts] == ["FAILED", "COMPLETED"]
    assert attempts[0]["error"]["code"] == "lease_expired"


@pytest.mark.parametrize("running", [False, True])
def test_cancellation_during_assignment_and_execution(h: Harness, running: bool) -> None:
    job = h.submit(retry={"limit": 3})
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    if running:
        h.start(assignment)
    route = f"/api/v1/jobs/{job['id']}/cancel"
    response = h.client.post(route, headers=headers(h.admin))
    assert response.status_code == 200
    if running:
        assert response.json()["status"] == "RUNNING"
        assert h.report(assignment, "renew")["cancel_requested"]
        h.report(assignment, "complete", result={"value": "discard", "steps": 1})
    else:
        h.report(assignment, "start", expected=409)
    assert h.get(job["id"])["status"] == "CANCELLED"
    assert h.get(job["id"])["result"] is None
    h.tick(datetime.now(UTC) + timedelta(seconds=3600))
    assert h.client.post(route, headers=headers(h.admin)).json()["status"] == "CANCELLED"


@pytest.mark.parametrize("retryable", [False, True])
def test_backoff_retry_limit_and_terminal_failures(h: Harness, retryable: bool) -> None:
    job = h.submit(retry={"limit": 1, "backoff_seconds": 10})
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    h.report(assignment, "fail", error_code="transient_error" if retryable else "permanent_error")
    if retryable:
        current = h.get(job["id"])
        assert current["status"] == "RETRY_WAIT"
        due = datetime.fromisoformat(current["next_run_at"].replace("Z", "+00:00"))
        assert h.tick(due - timedelta(microseconds=1)) == 0
        assert h.tick(due) == 1
        assignment = h.poll()
        assert assignment is not None
        h.start(assignment)
        h.report(assignment, "fail", error_code="transient_error")
    assert h.get(job["id"])["status"] == "FAILED"
    h.tick(datetime.now(UTC) + timedelta(hours=1))
    assert h.get(job["id"])["attempt_count"] == (2 if retryable else 1)


def test_deadline_caps_renewal_and_cancellation_survives_disappearance(h: Harness) -> None:
    job = h.submit(timeout_seconds=2)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    response = h.report(assignment, "renew")
    assert response["lease_expires_at"] == assignment["deadline_at"]
    h.tick(datetime.now(UTC) + timedelta(seconds=3))
    assert h.get(job["id"])["status"] == "FAILED"
    cancelled = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    h.client.post(f"/api/v1/jobs/{cancelled['id']}/cancel", headers=headers(h.admin))
    h.tick(datetime.now(UTC) + timedelta(seconds=31))
    assert h.get(cancelled["id"])["status"] == "CANCELLED"


def test_node_disconnection_revocation_and_session_fencing(h: Harness) -> None:
    job = h.submit(retry={"limit": 1, "backoff_seconds": 0})
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node is not None
        node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=31)
        node.state, node.connection_status = "offline", "offline"
    h.tick(datetime.now(UTC) + timedelta(seconds=31))
    assert h.get(job["id"])["status"] == "RETRY_WAIT"
    # Restore the compatible peer only; the disconnected preferred worker stays excluded.
    now = datetime.now(UTC) + timedelta(seconds=32)
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[1]["credential_id"]))
        assert node is not None
        node.last_heartbeat_at = now
    h.tick(now)
    replacement = h.poll(1)
    assert replacement is not None
    h.complete(replacement, 1)
    h.report(assignment, "complete", expected=409)
    assert h.get(job["id"])["status"] == "COMPLETED"


def test_cancel_audit_does_not_deadlock_with_a_worker_holding_its_node(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    acquired, release = threading.Event(), threading.Event()
    original = jobs.worker_node

    def hold_node(node_id: UUID, payload: JobPoll, request: Request, session: Session) -> Node:
        node = original(node_id, payload, request, session)
        acquired.set()
        assert release.wait(5), "Test must release the worker without relying on sleeps"
        return node

    monkeypatch.setattr(jobs, "worker_node", hold_node)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(h.report, assignment, "renew")
        try:
            assert acquired.wait(3)
            response = h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin))
            assert response.status_code == 200, response.text
        finally:
            release.set()
        assert future.result(timeout=5)["cancel_requested"]
    h.report(assignment, "cancelled")
    assert h.get(job["id"])["status"] == "CANCELLED"


def test_owner_consent_and_workspace_access_are_both_required(h: Harness) -> None:
    other = provision(h.database, "admin", email="other-owner@example.invalid")
    with h.database.sessions.begin() as session:
        workspace = Workspace(owner_id=UUID(other["owner_id"]), name="Foreign workspace")
        session.add(workspace)
        session.flush()
        workspace_id = workspace.id
    response = h.client.post(
        "/api/v1/jobs", json={"workspace_id": str(workspace_id)}, headers=headers(other)
    )
    assert response.status_code == 201
    job_id = response.json()["id"]
    assert h.tick() == 0
    # Only the authenticated node identity can advertise its owner's sharing consent.
    registration = h.registrations[0].model_copy(
        update={
            "allowed_job_owner_ids": [UUID(other["owner_id"])],
            "allowed_workspace_ids": [workspace_id],
        }
    )
    assert (
        h.client.post(
            "/api/v1/workers/register",
            json=registration.model_dump(mode="json"),
            headers=headers(h.workers[0]),
        ).status_code
        == 200
    )
    assert h.tick() == 0  # Node owner still cannot see the private workspace.
    with h.database.sessions.begin() as session:
        session.add(WorkspaceMember(workspace_id=workspace_id, user_id=UUID(h.admin["owner_id"])))
    registration.scheduling_policy = "dedicated"
    h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[0]),
    )
    assert h.tick() == 0
    registration.scheduling_policy = "shared"
    h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[0]),
    )
    assert h.tick() == 1
    assignment = h.poll()
    assert assignment is not None and assignment["job"]["id"] == job_id
    registration.allowed_job_owner_ids = []
    h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[0]),
    )
    h.report(assignment, "ack", expected=409)


def test_fairness_is_persistent_across_users_and_priority_is_within_owner(h: Harness) -> None:
    other = provision(h.database, "admin", email="fairness@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=UUID(other["owner_id"])))
    for index, registration in enumerate(h.registrations):
        registration.allowed_job_owner_ids = [UUID(other["owner_id"])]
        registration.allowed_workspace_ids = [h.workspace_id]
        h.client.post(
            "/api/v1/workers/register",
            json=registration.model_dump(mode="json"),
            headers=headers(h.workers[index]),
        )
    for _ in range(5):
        h.submit(priority=100)
    for _ in range(2):
        assert (
            h.client.post(
                "/api/v1/jobs",
                json={"workspace_id": str(h.workspace_id), "priority": -100},
                headers=headers(other),
            ).status_code
            == 201
        )
    h.tick()
    with h.database.sessions() as session:
        assigned = session.scalars(select(Job).where(Job.status == "ASSIGNED")).all()
        assert {str(j.owner_id) for j in assigned} == {h.admin["owner_id"], other["owner_id"]}
    h.database.close()
    h.tick()
    with h.database.sessions() as session:
        assert all(u.scheduling_turn > 0 for u in session.scalars(select(User)))


def test_api_scheduler_restart_preserves_pending_assigned_and_running_jobs(h: Harness) -> None:
    jobs = [h.submit() for _ in range(4)]
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    before = {j["id"]: h.get(j["id"])["status"] for j in jobs}
    h.database.close()
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        after = {
            j["id"]: restarted.get(f"/api/v1/jobs/{j['id']}", headers=headers(h.admin)).json()[
                "status"
            ]
            for j in jobs
        }
        assert before == after
    h.report(assignment, "complete", result={"value": "after restart", "steps": 1})
    assert h.tick() == 1


def test_100_jobs_two_concurrent_simulated_workers(h: Harness) -> None:
    jobs = [h.submit(input={"value": f"job-{n}", "steps": 2}) for n in range(100)]
    # Prove the whole queued workload remains durable across pool/API recreation.
    h.database.close()
    with TestClient(create_app(Settings(health_monitor_enabled=False))) as restarted:
        assert len(restarted.get("/api/v1/jobs?limit=200", headers=headers(h.admin)).json()) == 100
    seen: set[str] = set()
    handled = [0, 0]

    def work(index: int) -> str:
        assignment = h.poll(index)
        assert assignment is not None
        h.start(assignment, index)
        outcome = synthetic_result(
            SyntheticInput.model_validate(assignment["job"]["input"]),
            assignment["job"]["attempt_count"],
            assignment["job"]["type"],
        )
        assert isinstance(outcome, SyntheticResult)
        h.report(assignment, "complete", index, result=outcome.model_dump())
        handled[index] += 1
        return str(assignment["job"]["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        for _ in range(50):
            assert h.tick() == 2
            with h.database.sessions() as session:
                active = session.execute(
                    select(Attempt.job_id, func.count())
                    .where(Attempt.status.in_(ACTIVE))
                    .group_by(Attempt.job_id)
                ).all()
                assert len(active) == 2 and all(count == 1 for _, count in active)
            completed = list(executor.map(work, (0, 1)))
            assert not seen.intersection(completed)
            seen.update(completed)
    assert len(seen) == 100 and handled == [50, 50]
    assert all(h.get(job["id"])["status"] == "COMPLETED" for job in jobs)
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Attempt)) == 100
        assert (
            session.scalar(
                select(func.count()).select_from(Attempt).where(Attempt.status.in_(ACTIVE))
            )
            == 0
        )


@pytest.mark.parametrize(
    "unavailable", ["draining", "disabled", "offline", "suspect", "stale_heartbeat", "revoked"]
)
def test_unavailable_or_unauthenticated_nodes_never_receive_jobs(
    h: Harness, unavailable: str
) -> None:
    from godfather_api.models import AccessCredential

    with h.database.sessions.begin() as session:
        for node in session.scalars(select(Node)):
            if unavailable == "stale_heartbeat":
                node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=21)
            elif unavailable == "revoked":
                credential = session.scalar(
                    select(AccessCredential).where(AccessCredential.node_id == node.id)
                )
                assert credential is not None
                credential.revoked = True
            else:
                node.state = unavailable
    job = h.submit()
    assert h.tick() == 0 and h.get(job["id"])["status"] == "PENDING"


def test_resource_reservations_prevent_oversubscription_even_with_free_slots(h: Harness) -> None:
    with h.database.sessions.begin() as session:
        node = session.get(Node, UUID(h.workers[0]["credential_id"]))
        assert node is not None
        node.concurrency_limit = 3
    first = h.submit(requirements={"os": "windows", "cpu_count": 5})
    second = h.submit(requirements={"os": "windows", "cpu_count": 5})
    assert h.tick() == 1
    assert h.get(first["id"])["status"] == "ASSIGNED"
    assert h.get(second["id"])["status"] == "PENDING"


def test_expired_lease_is_rejected_before_any_sweeper_runs(h: Harness) -> None:
    job = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)
    with h.database.sessions.begin() as session:
        attempt = session.get(Attempt, UUID(assignment["attempt_id"]))
        assert attempt is not None
        attempt.lease_expires_at = datetime.now(UTC) - timedelta(microseconds=1)
    h.report(assignment, "renew", expected=409)
    h.report(assignment, "complete", expected=409, result={"value": "late", "steps": 1})
    assert h.get(job["id"])["status"] == "RUNNING"
    h.tick()
    assert h.get(job["id"])["status"] == "FAILED"


def test_cancel_pending_and_retry_wait_and_wrong_worker_scope(h: Harness) -> None:
    job = h.submit(retry={"limit": 1, "backoff_seconds": 10})
    queued = h.submit()
    assert (
        h.client.post(f"/api/v1/jobs/{queued['id']}/cancel", headers=headers(h.admin)).json()[
            "status"
        ]
        == "CANCELLED"
    )
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.report(assignment, "ack", 1, expected=409)
    response = h.client.post(
        f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/poll",
        json={"session_id": str(h.registrations[0].session_id)},
        headers=headers(h.workers[1]),
    )
    assert response.status_code == 403
    response = h.client.post(
        f"/api/v1/workers/{h.workers[0]['credential_id']}/jobs/poll",
        json={"session_id": str(h.registrations[0].session_id), "job_protocol_version": 2},
        headers=headers(h.workers[0]),
    )
    assert response.status_code == 426
    h.start(assignment)
    h.report(assignment, "fail", error_code="transient_error")
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)).json()["status"]
        == "CANCELLED"
    )
    h.tick(datetime.now(UTC) + timedelta(seconds=11))
    assert h.get(job["id"])["attempt_count"] == 1


def test_completion_cancellation_race_has_one_terminal_outcome(h: Harness) -> None:
    job = h.submit()
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    h.start(assignment)

    def complete() -> int:
        worker = h.workers[0]
        return h.client.post(
            f"/api/v1/workers/{worker['credential_id']}/jobs/{job['id']}/report",
            json={
                "session_id": str(h.registrations[0].session_id),
                "attempt_id": assignment["attempt_id"],
                "fencing_token": assignment["fencing_token"],
                "action": "complete",
                "result": {"value": "done", "steps": 1},
            },
            headers=headers(worker),
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        completed = executor.submit(complete)
        cancelled = executor.submit(
            h.client.post, f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)
        )
        assert completed.result() == 200 and cancelled.result().status_code == 200
    current = h.get(job["id"])
    assert current["status"] in ("COMPLETED", "CANCELLED")
    assert (current["result"] is None) == (current["status"] == "CANCELLED")
    h.report(assignment, "complete", expected=409, result={"value": "overwrite", "steps": 1})


def test_single_slot_round_robin_survives_scheduler_pool_restarts(h: Harness) -> None:
    other = provision(h.database, "admin", email="roundrobin@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=UUID(other["owner_id"])))
        backup = session.get(Node, UUID(h.workers[1]["credential_id"]))
        assert backup is not None
        backup.state = "disabled"
    registration = h.registrations[0]
    registration.scheduling_policy = "shared"
    registration.allowed_job_owner_ids = [UUID(other["owner_id"])]
    registration.allowed_workspace_ids = [h.workspace_id]
    h.client.post(
        "/api/v1/workers/register",
        json=registration.model_dump(mode="json"),
        headers=headers(h.workers[0]),
    )
    for _ in range(3):
        h.submit(priority=100)
        assert (
            h.client.post(
                "/api/v1/jobs",
                json={"workspace_id": str(h.workspace_id), "priority": -100},
                headers=headers(other),
            ).status_code
            == 201
        )
    dispatched: list[str] = []
    for _ in range(6):
        h.database.close()
        assert h.tick() == 1
        assignment = h.poll()
        assert assignment is not None
        dispatched.append(assignment["job"]["owner_id"])
        h.complete(assignment)
    assert all(a != b for a, b in zip(dispatched, dispatched[1:], strict=False))
    assert dispatched.count(h.admin["owner_id"]) == 3


def test_failed_submission_commit_rolls_back_job_and_audit(h: Harness) -> None:
    from godfather_api.models import Event
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    def fail_commit(session: Session) -> None:
        raise OperationalError("private SQL", {}, Exception("private detail"))

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = h.client.post(
            "/api/v1/jobs", json={"workspace_id": str(h.workspace_id)}, headers=headers(h.admin)
        )
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 500 and "private" not in response.text
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert (
            session.scalar(
                select(func.count()).select_from(Event).where(Event.type == "job.submitted")
            )
            == 0
        )
