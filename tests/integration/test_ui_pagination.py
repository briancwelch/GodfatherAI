"""Counted pages remain bounded, ordered and authorized over real PostgreSQL."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from godfather_api.models import (
    Checkpoint,
    Event,
    GoogleIdentity,
    Invitation,
    User,
    WorkspaceMember,
)
from godfather_api.provision import provision
from sqlalchemy import select

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import create, enable, run_worker, submit

pytestmark = pytest.mark.integration


def test_checkpoint_pages_are_disjoint_bounded_and_private(h: Harness) -> None:
    enable(h)
    job = submit(h, create(h))
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    run_worker(h, assignment)
    with h.database.sessions.begin() as session:
        cp = session.scalar(
            select(Checkpoint)
            .where(Checkpoint.job_id == UUID(job["id"]))
            .order_by(Checkpoint.version.desc())
        )
        assert cp is not None
        for version in range(cp.version + 1, 54):
            session.add(
                Checkpoint(
                    job_id=cp.job_id,
                    attempt_id=cp.attempt_id,
                    version=version,
                    artifact_id=cp.artifact_id,
                    artifact_ref=cp.artifact_ref,
                    checksum=cp.checksum,
                )
            )
    path = f"/api/v1/command-center/jobs/{job['id']}/checkpoints"
    pages = [
        h.client.get(path, params={"offset": n}, headers=headers(h.admin)).json()
        for n in (0, 25, 50)
    ]
    assert all(p["limit"] == 25 and p["total"] == 53 for p in pages)
    assert [len(p["items"]) for p in pages] == [25, 25, 3]
    assert [c["version"] for p in pages for c in p["items"]] == list(range(1, 54))
    detail = h.client.get(
        f"/api/v1/command-center/jobs/{job['id']}", headers=headers(h.admin)
    ).json()
    assert len(detail["checkpoints"]) == 25
    outsider = provision(h.database, "admin", email="checkpoint-outsider@example.invalid")
    for offset in (0, 25):
        assert (
            h.client.get(path, params={"offset": offset}, headers=headers(outsider)).status_code
            == 404
        )
    assert h.client.get(path).status_code == 401
    assert h.client.get(path, headers=headers(h.workers[0])).status_code == 401
    assert h.client.get(path, params={"offset": -1}, headers=headers(h.admin)).status_code == 422


def test_administration_pages_count_the_authorized_records(h: Harness) -> None:
    owner = UUID(h.admin["owner_id"])
    now = datetime.now(UTC)
    with h.database.sessions.begin() as session:
        for n in range(27):
            user = User(email=f"page-{n}@example.invalid", display_name=f"Page {n}")
            session.add(user)
            session.flush()
            session.add(GoogleIdentity(user_id=user.id, subject=f"page-{n}"))
            session.add(WorkspaceMember(workspace_id=h.workspace_id, user_id=user.id))
            session.add(
                Invitation(
                    actor_id=owner,
                    email=user.email,
                    roles=["member"],
                    token_hash=hashlib.sha256(str(n).encode()).hexdigest(),
                    expires_at=now + timedelta(hours=1),
                )
            )
            session.add(
                Event(
                    type="security.pagination_fixture",
                    actor_id=owner,
                    workspace_id=h.workspace_id,
                    details={"n": n},
                )
            )
    for endpoint in ("users", "invitations", "audit", "node-credentials"):
        path = "/api/v1/administration/" + endpoint
        first = h.client.get(path, params={"paged": True}, headers=headers(h.admin))
        assert first.status_code == 200, first.text
        page = first.json()
        assert page["limit"] == 25 and page["offset"] == 0
        assert len(page["items"]) == min(25, page["total"])
        second = h.client.get(
            path, params={"paged": True, "offset": 25}, headers=headers(h.admin)
        ).json()
        assert not {x["id"] for x in page["items"]} & {x["id"] for x in second["items"]}
        assert second["total"] == page["total"]
        assert isinstance(h.client.get(path, headers=headers(h.admin)).json(), list)
        assert h.client.get(path, params={"paged": True}).status_code == 401
        assert (
            h.client.get(path, params={"offset": -1}, headers=headers(h.admin)).status_code == 422
        )
    match = h.client.get(
        "/api/v1/administration/users",
        params={"paged": True, "search": "page-26@"},
        headers=headers(h.admin),
    ).json()
    assert match["total"] == 1 and match["items"][0]["email"] == "page-26@example.invalid"
    members = f"/api/v1/administration/workspaces/{h.workspace_id}/members"
    first = h.client.get(members, headers=headers(h.admin)).json()
    second = h.client.get(members, params={"offset": 25}, headers=headers(h.admin)).json()
    assert first["total"] == second["total"] == 27
    assert len(first["members"]) == 25 and len(second["members"]) == 2
    outsider = provision(h.database, "admin", email="page-outsider@example.invalid")
    assert (
        h.client.get(members, params={"offset": 25}, headers=headers(outsider)).status_code == 404
    )
    assert (
        h.client.get(
            "/api/v1/administration/node-credentials?paged=true", headers=headers(outsider)
        ).json()["total"]
        == 0
    )


def test_job_node_and_activity_defaults_are_25(h: Harness) -> None:
    with h.database.sessions.begin() as session:
        for n in range(27):
            session.add(Event(type="page.fixture", workspace_id=h.workspace_id, details={"n": n}))
    for section in ("jobs", "nodes"):
        assert (
            h.client.get(
                f"/api/v1/command-center?section={section}", headers=headers(h.admin)
            ).json()["limit"]
            == 25
        )
    job = h.submit()
    checkpoints = h.client.get(
        f"/api/v1/command-center/jobs/{job['id']}/checkpoints", headers=headers(h.admin)
    ).json()
    assert checkpoints["items"] == [] and checkpoints["total"] == 0
    path = "/api/v1/command-center/events"
    first = h.client.get(path, headers=headers(h.admin)).json()
    second = h.client.get(path, params={"offset": 25}, headers=headers(h.admin)).json()
    assert first["limit"] == 25 and len(first["items"]) == 25
    assert not {e["id"] for e in first["items"]} & {e["id"] for e in second["items"]}
