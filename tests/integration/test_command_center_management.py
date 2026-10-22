"""Bulk management preserves durable history, ownership and live execution safety."""

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from godfather_api.models import (
    Agent,
    Artifact,
    Attempt,
    Event,
    GoogleIdentity,
    Job,
    User,
    Workspace,
    WorkspaceMember,
)
from godfather_api.provision import provision
from sqlalchemy import func, select

from tests.integration.test_jobs import Harness, headers
from tests.integration.test_jobs import h as h
from tests.integration.test_workflows import create, enable, run_worker, submit

pytestmark = pytest.mark.integration
PATH = "/api/v1/administration/bulk-delete"


def delete(h: Harness, kind: str, ids: list[str], expected: int = 200) -> None:
    response = h.client.post(PATH, json={"kind": kind, "ids": ids}, headers=headers(h.admin))
    assert response.status_code == expected, response.text


def test_bulk_jobs_are_atomic_private_idempotent_and_not_worker_actions(h: Harness) -> None:
    jobs = [h.submit() for _ in range(2)]
    for job in jobs:
        assert (
            h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)).status_code
            == 200
        )
    pending = h.submit()
    delete(h, "jobs", [jobs[0]["id"], pending["id"]], 409)
    assert h.get(jobs[0]["id"])["status"] == "CANCELLED"
    outsider = provision(h.database, "admin", email="delete-outsider@example.invalid")
    assert (
        h.client.post(
            PATH, json={"kind": "jobs", "ids": [jobs[0]["id"]]}, headers=headers(outsider)
        ).status_code
        == 404
    )
    for auth in ({}, headers(h.workers[0])):
        assert (
            h.client.post(
                PATH, json={"kind": "jobs", "ids": [jobs[0]["id"]]}, headers=auth
            ).status_code
            == 401
        )
    delete(h, "jobs", [jobs[0]["id"], str(uuid4())], 404)
    delete(h, "jobs", [j["id"] for j in jobs])
    delete(h, "jobs", [j["id"] for j in jobs])
    listed = h.client.get("/api/v1/jobs", headers=headers(h.admin)).json()
    assert [j["id"] for j in listed] == [pending["id"]]
    snapshot = h.client.get("/api/v1/command-center?section=jobs", headers=headers(h.admin)).json()
    assert snapshot["totals"]["jobs"] == 1 and snapshot["job_counts"] == {"PENDING": 1}
    for job in jobs:
        for endpoint in (f"/api/v1/jobs/{job['id']}", f"/api/v1/command-center/jobs/{job['id']}"):
            assert h.client.get(endpoint, headers=headers(h.admin)).status_code == 404
        assert (
            h.client.post(f"/api/v1/jobs/{job['id']}/retry", headers=headers(h.admin)).status_code
            == 404
        )
    with h.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 3
        assert (
            session.scalar(
                select(func.count()).select_from(Event).where(Event.type == "security.jobs_deleted")
            )
            == 2
        )
    for ids in ([], [str(uuid4())] * 101):
        delete(h, "jobs", ids, 422)


def test_agent_deletion_retains_completed_work_and_all_versions(h: Harness) -> None:
    enable(h)
    agent = create(h)
    job = submit(h, agent)
    version = h.client.post(
        f"/api/v1/agents/{agent['id']}/versions",
        json={
            "expected_version": 1,
            "definition": agent["definition"],
        },
        headers=headers(h.admin),
    )
    assert version.status_code == 201, version.text
    delete(h, "agents", [agent["id"]], 409)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    run_worker(h, assignment)
    with h.database.sessions() as session:
        artifact_count = session.scalar(select(func.count()).select_from(Artifact))
        attempt_count = session.scalar(select(func.count()).select_from(Attempt))
    delete(h, "agents", [agent["id"]])
    delete(h, "agents", [agent["id"]])
    assert (
        h.client.get(f"/api/v1/agents/{agent['id']}", headers=headers(h.admin)).status_code == 404
    )
    assert (
        h.client.get(
            f"/api/v1/agents?workspace_id={h.workspace_id}", headers=headers(h.admin)
        ).json()
        == []
    )
    snapshot = h.client.get(
        "/api/v1/command-center?section=agents", headers=headers(h.admin)
    ).json()
    assert snapshot["totals"]["agents"] == 0 and snapshot["agent_counts"]["enabled_versions"] == 0
    assert h.client.get(f"/api/v1/jobs/{job['id']}", headers=headers(h.admin)).status_code == 200
    delete(h, "jobs", [job["id"]])
    with h.database.sessions() as session:
        row = session.get(Agent, UUID(agent["version_id"]))
        assert row is not None and row.deleted_at is not None
        assert session.scalar(select(func.count()).select_from(Artifact)) == artifact_count
        assert session.scalar(select(func.count()).select_from(Attempt)) == attempt_count
    recreated = create(h)
    assert recreated["id"] != agent["id"] and recreated["version"] == 3


def test_workspace_delete_is_owner_only_and_prevents_new_submissions(h: Harness) -> None:
    owner = UUID(h.admin["owner_id"])
    with h.database.sessions.begin() as session:
        other = Workspace(owner_id=owner, name="Another private workspace")
        session.add(other)
        session.flush()
        other_id = other.id
    pending = h.submit()
    delete(h, "workspaces", [str(h.workspace_id), str(other_id)], 409)
    with h.database.sessions() as session:
        row = session.get(Workspace, other_id)
        assert row is not None and row.deleted_at is None
    assert (
        h.client.post(f"/api/v1/jobs/{pending['id']}/cancel", headers=headers(h.admin)).status_code
        == 200
    )
    outsider = provision(h.database, "admin", email="workspace-delete-outsider@example.invalid")
    with h.database.sessions.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=h.workspace_id, user_id=UUID(outsider["owner_id"]), role="admin"
            )
        )
    assert (
        h.client.post(
            PATH,
            json={"kind": "workspaces", "ids": [str(h.workspace_id)]},
            headers=headers(outsider),
        ).status_code
        == 404
    )
    delete(h, "workspaces", [str(h.workspace_id), str(other_id)])
    delete(h, "workspaces", [str(h.workspace_id)])
    assert (
        h.client.get("/api/v1/command-center", headers=headers(h.admin)).json()["workspaces"] == []
    )
    assert h.client.get("/api/v1/jobs", headers=headers(h.admin)).json() == []
    assert (
        h.client.post(
            "/api/v1/jobs", json={"workspace_id": str(h.workspace_id)}, headers=headers(h.admin)
        ).status_code
        == 404
    )
    assert (
        h.client.get(
            f"/api/v1/administration/workspaces/{h.workspace_id}/members", headers=headers(h.admin)
        ).status_code
        == 404
    )
    with h.database.sessions() as session:
        assert session.get(Job, UUID(pending["id"])) is not None


def test_permission_lookup_uses_exact_user_beyond_member_page_and_limits_role_visibility(
    h: Harness,
) -> None:
    with h.database.sessions.begin() as session:
        members = []
        for n in range(28):
            user = User(
                email=f"permission-{n}@example.invalid",
                display_name=f"User {n}",
                role="contributor",
                roles=["contributor"],
            )
            session.add(user)
            session.flush()
            session.add(GoogleIdentity(user_id=user.id, subject=f"permission-{n}"))
            session.add(
                WorkspaceMember(
                    workspace_id=h.workspace_id,
                    user_id=user.id,
                    role="admin" if n == 27 else "member",
                )
            )
            members.append(user.id)
    path = f"/api/v1/administration/workspaces/{h.workspace_id}/members/"
    response = h.client.get(path + str(members[-1]), headers=headers(h.admin))
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"
    assert response.json()["account"]["roles"] == ["contributor"]
    assert response.json()["account"]["permissions"]
    newcomer = provision(h.database, "admin", email="permission-new@example.invalid")
    assert (
        h.client.get(path + newcomer["owner_id"], headers=headers(h.admin)).json()["role"] == "none"
    )
    assert (
        h.client.get(path + h.admin["owner_id"], headers=headers(h.admin)).json()["role"] == "owner"
    )
    assert h.client.get(path + str(members[-1]), headers=headers(newcomer)).status_code == 404
    assert h.client.get(path + str(members[-1]), headers=headers(h.workers[0])).status_code == 401
    changed = h.client.post(
        path.rstrip("/"),
        json={"user_id": str(members[-1]), "role": "member"},
        headers=headers(h.admin),
    )
    assert changed.status_code == 200
    assert (
        h.client.get(path + str(members[-1]), headers=headers(h.admin)).json()["role"] == "member"
    )


def test_workspace_archive_contains_verified_durable_data_and_no_account_secrets(
    h: Harness,
) -> None:
    import hashlib
    import io
    import json
    import zipfile

    enable(h)
    agent = create(h)
    job = submit(h, agent)
    h.tick()
    assignment = h.poll()
    assert assignment is not None
    run_worker(h, assignment)
    path = "/api/v1/administration/workspace-archive"
    payload = {"ids": [str(h.workspace_id)]}
    for auth in ({}, headers(h.workers[0])):
        assert h.client.post(path, json=payload, headers=auth).status_code == 401
    outsider = provision(h.database, "admin", email="archive-outsider@example.invalid")
    assert h.client.post(path, json=payload, headers=headers(outsider)).status_code == 404
    response = h.client.post(path, json=payload, headers=headers(h.admin))
    assert response.status_code == 200, response.text[:200]
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "godfather.workspace-archive.v1"
        assert manifest["workspace_ids"] == [str(h.workspace_id)]
        assert manifest["record_counts"][str(h.workspace_id)]["artifacts"] > 0
        for name, checksum in manifest["sha256"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
        archived_jobs = json.loads(archive.read(f"{h.workspace_id}/jobs.json"))
        assert archived_jobs[0]["id"] == job["id"]
        assert archived_jobs[0]["status"] == "COMPLETED"
        assert not any(
            "credentials" in name or "provider_keys" in name or "human_sessions" in name
            for name in archive.namelist()
        )
        assert h.admin["token"].encode() not in b"".join(
            archive.read(name) for name in archive.namelist()
        )
    assert h.get(job["id"])["status"] == "COMPLETED"
    # A missing/corrupt artifact never produces an archive labeled complete.
    with h.database.sessions() as session:
        artifact = session.scalar(select(Artifact).where(Artifact.job_id == UUID(job["id"])))
        assert artifact is not None
        assert isinstance(h.client.app, FastAPI)
        h.client.app.state.artifacts.path(artifact.id).unlink()
    assert h.client.post(path, json=payload, headers=headers(h.admin)).status_code == 503
    with h.database.sessions() as session:
        row = session.get(Workspace, h.workspace_id)
        assert row is not None and row.deleted_at is None


def test_workspace_archive_blocks_unfinished_and_bounded_exports(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from godfather_api import workspace_archive

    job = h.submit()
    path = "/api/v1/administration/workspace-archive"
    payload = {"ids": [str(h.workspace_id)]}
    assert h.client.post(path, json=payload, headers=headers(h.admin)).status_code == 409
    assert (
        h.client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=headers(h.admin)).status_code
        == 200
    )
    monkeypatch.setattr(workspace_archive, "MAX_BYTES", 16)
    assert h.client.post(path, json=payload, headers=headers(h.admin)).status_code == 413
    assert (
        h.client.post(
            path, json={"ids": [str(h.workspace_id), str(uuid4())]}, headers=headers(h.admin)
        ).status_code
        == 404
    )


def test_workspace_delete_serializes_concurrent_submissions(h: Harness) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    owner = UUID(h.admin["owner_id"])
    for index in range(4):
        with h.database.sessions.begin() as session:
            workspace = Workspace(owner_id=owner, name=f"Deletion race {index}")
            session.add(workspace)
            session.flush()
            workspace_id = workspace.id
        barrier = Barrier(2)

        def remove(target: UUID = workspace_id, gate: Barrier = barrier) -> int:
            gate.wait(timeout=10)
            return h.client.post(
                PATH,
                json={"kind": "workspaces", "ids": [str(target)]},
                headers=headers(h.admin),
            ).status_code

        def submit_job(target: UUID = workspace_id, gate: Barrier = barrier) -> int:
            gate.wait(timeout=10)
            return h.client.post(
                "/api/v1/jobs", json={"workspace_id": str(target)}, headers=headers(h.admin)
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            deletion = executor.submit(remove)
            submission = executor.submit(submit_job)
            result = (deletion.result(timeout=15), submission.result(timeout=15))
        assert result in ((200, 404), (409, 201)), result
        with h.database.sessions() as session:
            stored = session.get(Workspace, workspace_id)
            assert stored is not None
            if stored.deleted_at is not None:
                assert (
                    session.scalar(
                        select(Job.id).where(
                            Job.workspace_id == workspace_id,
                            Job.status.not_in(("COMPLETED", "FAILED", "CANCELLED")),
                        )
                    )
                    is None
                )
