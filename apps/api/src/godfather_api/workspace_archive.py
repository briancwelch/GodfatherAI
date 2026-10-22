"""Owner-only, bounded workspace export; no host files or account secrets."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import Text, cast, func, select

from godfather_api.artifacts import ArtifactError
from godfather_api.authentication import audit
from godfather_api.models import (
    Agent,
    Artifact,
    Attempt,
    Checkpoint,
    Event,
    Job,
    WorkflowRun,
    WorkflowStepRecord,
    Workspace,
    WorkspaceMember,
)
from godfather_api.nodes import SessionDep, authenticate, human_event_details
from godfather_api.scheduler import TERMINAL, lock_workspace

router = APIRouter(prefix="/api/v1/administration")
MAX_BYTES = 128 * 1024 * 1024
MAX_ROWS = 10000


class ArchiveSelection(BaseModel):
    model_config = {"extra": "forbid"}
    ids: list[UUID] = Field(min_length=1, max_length=100)


@router.post("/workspace-archive")
def workspace_archive(payload: ArchiveSelection, request: Request, session: SessionDep) -> Response:
    actor = authenticate(request, session, "human")
    ids = sorted(set(payload.ids))
    for workspace_id in ids:
        lock_workspace(session, workspace_id)
    workspaces = list(
        session.scalars(select(Workspace).where(Workspace.id.in_(ids)).order_by(Workspace.id))
    )
    if len(workspaces) != len(ids) or any(
        w.owner_id != actor.owner_id or w.deleted_at is not None for w in workspaces
    ):
        raise HTTPException(404, "Owned workspace not found")
    output = io.BytesIO()
    total_bytes = 0
    checksums: dict[str, str] = {}
    counts: dict[str, dict[str, int]] = {}

    def rows(model: Any, condition: Any, lock: bool = False) -> list[Any]:
        # Bound uncompressed database payload before materializing potentially large JSON records.
        count, size = session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(
                        func.octet_length(
                            cast(func.row_to_json(model.__table__.table_valued()), Text)
                        )
                    ),
                    0,
                ),
            )
            .select_from(model)
            .where(condition)
        ).one()
        if count > MAX_ROWS or size > MAX_BYTES - total_bytes:
            raise HTTPException(
                413, "Workspace exceeds the interactive archive limit; nothing deleted"
            )
        query = select(model).where(condition).limit(MAX_ROWS + 1)
        if lock:
            query = query.order_by(model.id).with_for_update()
        return list(session.scalars(query))

    def records(values: list[Any], omit: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        return [
            {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in omit}
            for row in values
        ]

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:

        def write(name: str, value: Any, raw: bool = False) -> None:
            nonlocal total_bytes
            data = (
                value
                if raw
                else json.dumps(jsonable_encoder(value), ensure_ascii=False, indent=2).encode(
                    "utf-8"
                )
            )
            total_bytes += len(data)
            if total_bytes > MAX_BYTES:
                raise HTTPException(
                    413,
                    "Workspace exceeds the 128 MiB interactive archive limit; nothing deleted",
                )
            archive.writestr(name, data)
            checksums[name] = hashlib.sha256(data).hexdigest()

        for workspace in workspaces:
            prefix = str(workspace.id) + "/"
            jobs = rows(Job, Job.workspace_id == workspace.id, lock=True)
            if any(j.status not in TERMINAL for j in jobs):
                raise HTTPException(
                    409, "Finish or cancel this workspace's jobs before archiving for deletion"
                )
            job_ids = [j.id for j in jobs]
            artifacts = rows(Artifact, Artifact.workspace_id == workspace.id)
            counts[str(workspace.id)] = {}

            def write_records(
                name: str,
                values: list[Any],
                omit: tuple[str, ...] = (),
                *,
                workspace_key: str = str(workspace.id),
                folder: str = prefix,
            ) -> None:
                counts[workspace_key][name] = len(values)
                write(folder + name + ".json", records(values, omit))

            write_records("workspace", [workspace])
            write_records(
                "memberships", rows(WorkspaceMember, WorkspaceMember.workspace_id == workspace.id)
            )
            write_records("agents", rows(Agent, Agent.workspace_id == workspace.id))
            write_records("jobs", jobs)
            write_records("attempts", rows(Attempt, Attempt.job_id.in_(job_ids)), ("session_id",))
            write_records("workflow_runs", rows(WorkflowRun, WorkflowRun.job_id.in_(job_ids)))
            write_records(
                "workflow_steps", rows(WorkflowStepRecord, WorkflowStepRecord.job_id.in_(job_ids))
            )
            write_records("checkpoints", rows(Checkpoint, Checkpoint.job_id.in_(job_ids)))
            write_records("artifacts", artifacts)
            events = rows(Event, Event.workspace_id == workspace.id)
            counts[str(workspace.id)]["events"] = len(events)
            write(
                prefix + "events.json",
                [
                    {
                        **{
                            k: getattr(e, k)
                            for k in (
                                "id",
                                "type",
                                "actor_id",
                                "workspace_id",
                                "job_id",
                                "attempt_id",
                                "node_id",
                                "created_at",
                                "correlation_id",
                            )
                        },
                        "details": human_event_details(e, actor.owner_id),
                    }
                    for e in events
                ],
            )
            if sum(a.size_bytes for a in artifacts) > MAX_BYTES - total_bytes:
                raise HTTPException(
                    413, "Workspace exceeds the interactive archive limit; nothing deleted"
                )
            for artifact in artifacts:
                try:
                    raw = request.app.state.artifacts.read(
                        artifact.id, artifact.checksum, artifact.size_bytes
                    )
                except ArtifactError:
                    raise HTTPException(
                        503,
                        "An artifact failed integrity validation or is unavailable; "
                        "archive not completed and nothing deleted",
                    ) from None
                write(prefix + "artifacts/" + str(artifact.id) + ".json", raw, True)
        manifest = {
            "format": "godfather.workspace-archive.v1",
            "exported_at": datetime.now(UTC).isoformat(),
            "workspace_ids": [str(i) for i in ids],
            "record_counts": counts,
            "sha256": dict(checksums),
            "contents": (
                "Workspace configuration, memberships, all agent versions, jobs, attempts, "
                "workflows, checkpoints, verified artifacts and scoped events, "
                "including logically deleted records."
            ),
            "excludes": [
                "Account credentials, API keys, Google identities and sessions",
                "Private provider connections, grants and billing records",
                "Worker-local repositories, uncommitted files, models and host configuration",
            ],
            "restore": "Portable export for review; automatic import is not implemented.",
        }
        write("manifest.json", manifest)
    for workspace in workspaces:
        audit(
            session,
            "workspace_archive_prepared",
            actor.owner_id,
            workspace.id,
            workspace_id=workspace.id,
            metadata={"format": "godfather.workspace-archive.v1"},
        )
    filename = "godfather-workspaces-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".zip"
    return Response(
        output.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
