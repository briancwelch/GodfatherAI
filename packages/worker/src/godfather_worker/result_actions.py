"""Local, owner-opted-in actions. No downloaded code, host shell, or automatic replay."""

import asyncio
import hashlib
import json
import os
import re
import tempfile
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from uuid import UUID

from godfather_contracts import Registration
from godfather_contracts.coding import CodingOutput, CodingRepository
from godfather_contracts.execution import AttemptIdentity
from godfather_contracts.jobs import Assignment, JobReport, ReportResponse
from godfather_contracts.result_actions import ResultActionInput, ResultActionOutput

from godfather_worker.client import WorkerClient
from godfather_worker.coding import allowed, command
from godfather_worker.inference import maintain_execution


async def git_command(args: list[str], root: Path) -> tuple[int, str]:
    # The shared command runner excludes system/user Git config. Retain native
    # Windows CRLF handling explicitly, without loading credential helpers/hooks.
    # Repository .gitattributes continues to control per-file line endings.
    return await command(
        ["git", "-c", f"core.autocrlf={'true' if os.name == 'nt' else 'false'}", *args], root
    )


class ApplyBlocked(ValueError):
    """A safe refusal, before any project writes."""


def save_receipt(path: Path, text: str) -> None:
    if path.is_symlink():
        raise ApplyBlocked("The local apply receipt is a link. Review the project manually.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8", newline="") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


async def checked_paths(config: CodingRepository, output: CodingOutput, patch: Path) -> list[str]:
    if not config.allow_apply or config.id != output.repository_id:
        raise ApplyBlocked("Enable applying reviewed changes in this worker's Coding projects.")
    paths = output.files_changed
    if not paths or len(set(p.casefold() for p in paths)) != len(paths):
        raise ApplyBlocked("The patch has no changes or contains ambiguous file names.")
    if any(not allowed(p, config) for p in paths):
        raise ApplyBlocked("The patch includes files outside the project's approved scope.")
    if re.search(
        r"^(?:old mode|new mode|rename |copy |GIT binary patch|Binary files)", output.diff, re.M
    ):
        raise ApplyBlocked("Mode changes, renames and binary patches require manual review.")
    if any(
        mode not in ("100644", "100755")
        for mode in re.findall(r"^(?:new file mode|deleted file mode) (\S+)", output.diff, re.M)
    ):
        raise ApplyBlocked("Special file types cannot be applied.")
    if any(
        mode not in ("100644", "100755")
        for mode in re.findall(r"^index \S+ (\d+)$", output.diff, re.M)
    ):
        raise ApplyBlocked("Special index file types cannot be applied.")
    # Git supplies the actual target paths; never trust just the result's file list.
    code, stat = await command(["git", "apply", "--numstat", "-z", str(patch)], config.path)
    actual = []
    for record in stat.split("\0"):
        if record:
            fields = record.split("\t", 2)
            if len(fields) != 3 or fields[0] == "-" or not allowed(fields[2], config):
                raise ApplyBlocked("The patch has unsupported or unsafe file paths.")
            actual.append(fields[2])
    if code or sorted(actual) != sorted(paths):
        raise ApplyBlocked("The patch does not match the reviewed file list.")
    return paths


async def preflight(config: CodingRepository, output: CodingOutput, patch: Path) -> list[str]:
    paths = await checked_paths(config, output, patch)
    root = config.path.resolve(strict=True)
    code, top = await command(["git", "rev-parse", "--show-toplevel"], root)
    if code or Path(top.strip()).resolve() != root:
        raise ApplyBlocked("The configured project is no longer the same Git repository.")
    code, head = await command(["git", "rev-parse", "--verify", "HEAD^{commit}"], root)
    if code or head.strip() != output.base_commit:
        raise ApplyBlocked(
            "The project commit changed. Run the agent again on the current project."
        )
    for path in paths:
        target = root / path
        # Refuse symlinks, junctions, and parent redirects; Git also checks unsafe paths.
        for entry in (target, *target.parents):
            if entry == root:
                break
            if entry.is_symlink() or entry.is_junction():
                raise ApplyBlocked(
                    "A changed file or parent is a link. Review this patch manually."
                )
        if not target.resolve().is_relative_to(root):
            raise ApplyBlocked("A changed file is outside the project.")
        # status can hide edits behind assume-unchanged/skip-worktree flags.
        # Compare every affected working file to the immutable source blob too.
        code, original = await command(
            ["git", "cat-file", "blob", f"{output.base_commit}:{path}"], root, limit=65536
        )
        if code:
            if target.exists():
                raise ApplyBlocked(
                    "A new file would overwrite an existing file. Your file was kept."
                )
        elif (
            not target.is_file()
            or target.stat().st_size > 65536
            or target.read_bytes().replace(b"\r\n", b"\n")
            != original.encode("utf-8").replace(b"\r\n", b"\n")
        ):
            raise ApplyBlocked(
                "An affected file differs from the reviewed source. Your edits were kept."
            )
    code, dirty = await git_command(
        [
            "--literal-pathspecs",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignored",
            "--",
            *paths,
        ],
        root,
    )
    if code or dirty:
        raise ApplyBlocked(
            "A changed file has existing staged, unstaged, untracked or ignored edits. "
            "Your edits were kept. Commit or move them, then try again."
        )
    code, _ = await git_command(["apply", "--check", "--whitespace=nowarn", str(patch)], root)
    if code:
        raise ApplyBlocked("The patch conflicts with the current project. Your edits were kept.")
    return paths


async def apply_patch(
    config: CodingRepository,
    output: CodingOutput,
    job_id: UUID,
    authorize: Callable[[], Awaitable[None]],
) -> list[str]:
    """Recheck under a local lock, authorize once, then let Git validate/apply all hunks.

    A durable journal prevents local replay after uncertain completion. Git applies
    without --reject/--3way, leaves the index untouched, and never runs a model's commands.
    Editors do not honor this lock: users must pause edits to affected files during apply.
    """
    code, location = await command(["git", "rev-parse", "--absolute-git-dir"], config.path)
    if code:
        raise ApplyBlocked("The project is not available.")
    git_dir = Path(location.strip())
    lock = git_dir / "godfather-apply.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise ApplyBlocked(
            "Another apply may be unfinished. Review the local Godfather apply journal "
            "before removing its lock."
        ) from None
    try:
        with handle, tempfile.TemporaryDirectory(prefix="godfather-apply-") as folder:
            patch = Path(folder) / "changes.patch"
            patch.write_text(output.diff, encoding="utf-8", newline="")
            paths = await preflight(config, output, patch)
            journal = git_dir / "godfather-actions"
            if journal.is_symlink() or journal.is_junction():
                raise ApplyBlocked(
                    "The local apply journal is a link. Review the project manually."
                )
            journal.mkdir(exist_ok=True, mode=0o700)
            receipt = journal / f"{job_id}.json"
            if receipt.exists():
                raise ApplyBlocked(
                    "This action already has a local receipt. Inspect the project; "
                    "it will not be replayed."
                )
            # Save the immutable patch for review/recovery before the side effect.
            save_receipt(journal / f"{job_id}.patch", output.diff)
            await authorize()
            save_receipt(
                receipt,
                json.dumps({"state": "started", "base_commit": output.base_commit, "files": paths}),
            )
            # A final preflight catches edits made while waiting for authorization.
            await preflight(config, output, patch)
            code, _ = await git_command(["apply", "--whitespace=nowarn", str(patch)], config.path)
            if code:
                # I/O failure can be uncertain; never claim a safe conflict after starting writes.
                raise RuntimeError(
                    "Apply did not confirm completion; review the local receipt and project."
                )
            save_receipt(
                receipt,
                json.dumps({"state": "applied", "base_commit": output.base_commit, "files": paths}),
            )
            return paths
    finally:
        lock.unlink(missing_ok=True)


async def perform_action(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
    stop: threading.Event,
    repositories: list[CodingRepository],
) -> None:
    payload = assignment.job.input
    if not isinstance(payload, ResultActionInput) or payload.node_id != node_id:
        raise ValueError("Unsupported result action")
    identity = AttemptIdentity(
        session_id=registration.session_id,
        attempt_id=assignment.attempt_id,
        fencing_token=assignment.fencing_token,
    )
    root = f"/api/v1/workers/{node_id}/jobs/{assignment.job.id}"

    async def report(action: str, **values: object) -> ReportResponse:
        return ReportResponse.model_validate(
            await asyncio.to_thread(
                client.post_document,
                root + "/report",
                JobReport.model_validate({**identity.model_dump(), "action": action, **values}),
            )
        )

    try:
        config = next(
            (
                r
                for r in repositories
                if r.id == payload.repository_id
                and r.allow_apply
                and assignment.job.owner_id in r.allowed_user_ids
                and assignment.job.workspace_id in r.allowed_workspace_ids
            ),
            None,
        )
        if config is None or stop.is_set():
            raise ApplyBlocked("Project application is not enabled on this worker.")
        document = await asyncio.to_thread(
            client.post_document, root + "/result-action/input", identity
        )
        encoded = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if (
            len(encoded) != payload.artifact.size_bytes
            or hashlib.sha256(encoded).hexdigest() != payload.artifact.checksum
        ):
            raise ApplyBlocked(
                "The result failed integrity validation. Refresh the job and review its artifact."
            )
        output = CodingOutput.model_validate(document)

        async def authorize() -> None:
            if stop.is_set():
                raise ApplyBlocked("The worker was paused before application.")
            await asyncio.to_thread(client.post_document, root + "/result-action/begin", identity)

        files = await apply_patch(config, output, assignment.job.id, authorize)
        result = ResultActionOutput(
            source_job_id=payload.source_job_id,
            state="applied",
            files=files,
            summary="Applied the reviewed patch to your project. Changes are unstaged; "
            "review and commit them when ready.",
        )
    except ApplyBlocked as error:
        result = ResultActionOutput(
            source_job_id=payload.source_job_id, state="blocked", summary=str(error)
        )
    except Exception:
        # No replay: a missing completion report requires inspection, not another automatic apply.
        await report("fail", error_code="permanent_error")
        return
    await report("complete", result=result)


async def execute_action(
    client: WorkerClient,
    node_id: UUID,
    registration: Registration,
    assignment: Assignment,
    stop: threading.Event,
    repositories: list[CodingRepository],
    heartbeat_seconds: int = 10,
) -> None:
    route = f"/api/v1/workers/{node_id}/jobs/{assignment.job.id}/report"

    async def report(action: str) -> ReportResponse:
        return ReportResponse.model_validate(
            await asyncio.to_thread(
                client.post_document,
                route,
                JobReport(
                    session_id=registration.session_id,
                    attempt_id=assignment.attempt_id,
                    fencing_token=assignment.fencing_token,
                    action=action,
                ),
            )
        )

    if (await report("ack")).status == "CANCELLED" or (await report("start")).status == "CANCELLED":
        return
    work = asyncio.create_task(
        perform_action(client, node_id, registration, assignment, stop, repositories)
    )
    watch = asyncio.create_task(
        maintain_execution(
            client, node_id, registration, assignment, stop, heartbeat_seconds, report
        )
    )
    try:
        done, _ = await asyncio.wait((work, watch), return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            await work
        else:
            await watch
    finally:
        for task in (work, watch):
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
