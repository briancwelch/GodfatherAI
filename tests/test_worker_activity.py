"""Notifications survive restart, stay scoped, and require explicit owner actions."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from godfather_contracts.worker_activity import ActivityCursor, JobNotice
from godfather_worker.activity import Inbox, inbox_path, load_inbox, save_inbox

from tests.test_shared_engine_setup import group_fixture


def test_lifecycle_events_are_deduplicated_and_persisted_per_identity(tmp_path: Path) -> None:
    box = Inbox()
    event = JobNotice(
        id=uuid4(),
        job_id=uuid4(),
        attempt_id=uuid4(),
        type="job.started",
        created_at=datetime.now(UTC),
    )
    box.job_event(event)
    box.job_event(event)
    assert len(box.notices) == 1 and not box.notices[0].read
    box.notices[0].read = True
    box.cursor = ActivityCursor(at=event.created_at, id=event.id)
    account = {"origin": "https://example.invalid", "credential_id": str(uuid4())}
    location = inbox_path(tmp_path, account)
    save_inbox(location, box)
    loaded = load_inbox(location)
    loaded.job_event(event)
    assert loaded == box
    assert inbox_path(tmp_path, {**account, "credential_id": str(uuid4())}) != location
    assert inbox_path(tmp_path, {**account, "origin": "https://other.invalid"}) != location


def test_notifications_are_bounded_and_corrupt_history_does_not_break_worker(
    tmp_path: Path,
) -> None:
    box = Inbox()
    for _ in range(220):
        box.job_event(
            JobNotice(
                id=uuid4(),
                job_id=uuid4(),
                attempt_id=uuid4(),
                type="job.completed",
                created_at=datetime.now(UTC),
            )
        )
    assert len(box.notices) == 200
    location = tmp_path / "invalid.json"
    location.write_text('{"bad": true}')
    assert load_inbox(location) == Inbox()


def test_shared_invitation_join_and_start_notices_do_not_auto_approve(tmp_path: Path) -> None:
    consent, group = group_fixture(tmp_path)
    group.desired_running = False
    for member in group.members:
        member.phase = "waiting"
    pending = group.model_copy(deep=True)
    pending.group = None
    pending.members[1].approved = False
    peer = pending.members[1].node_id
    box = Inbox()
    assert box.shared_groups(peer, [pending]) == 1
    assert "approve and join" in box.notices[0].title
    assert not pending.members[1].approved
    box.shared_groups(peer, [pending])
    assert len(box.notices) == 1
    assert box.shared_groups(peer, [group]) == 0
    assert "waiting for start" in box.notices[0].title
    leader_box = Inbox()
    assert leader_box.shared_groups(consent.node_id, [group]) == 1
    assert "ready to start" in leader_box.notices[0].title
    assert not group.desired_running
    group.desired_running = True
    leader_box.shared_groups(consent.node_id, [group])
    assert "starting" in leader_box.notices[0].title
    for member in group.members:
        member.phase = "ready"
    leader_box.shared_groups(consent.node_id, [group])
    assert "ready" in leader_box.notices[0].title


def test_unchanged_shared_state_is_not_announced_again_after_restart(tmp_path: Path) -> None:
    consent, group = group_fixture(tmp_path)
    box = Inbox()
    box.shared_groups(consent.node_id, [group])
    location = tmp_path / "inbox.json"
    save_inbox(location, box)
    loaded = load_inbox(location)
    loaded.shared_groups(consent.node_id, [group])
    assert len(loaded.notices) == 1
