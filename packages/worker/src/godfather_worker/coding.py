"""Bounded single-agent coding in an owner-approved, networkless container."""

import asyncio
import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from godfather_agent_runtime import WorkflowError
from godfather_contracts import ModelDeployment
from godfather_contracts.agents import WorkflowInput, WorkflowStep
from godfather_contracts.coding import (
    CodingOutput,
    CodingPlan,
    CodingRepository,
    FileEdit,
    TestOutcome,
)
from godfather_contracts.inference import InferenceUsage
from godfather_model_gateway import Provider, StructuredRequest, generate


async def command(
    args: list[str], cwd: Path, limit: int = 131072, timeout: int = 60
) -> tuple[int, str]:
    """No shell, inherited credentials, Git helpers, network fetches or unbounded output."""
    executable = shutil.which(args[0])
    if executable is None:
        raise WorkflowError("tool_permission")
    if args[0] == "git":
        args = [
            args[0],
            "--no-optional-locks",
            "-c",
            f"safe.directory={cwd.resolve().as_posix()}",
            "-c",
            "protocol.allow=never",
            "-c",
            "core.fsmonitor=false",
            *args[1:],
        ]
    environment = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in (
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "USERPROFILE",
            "HOME",
        )
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }
    )
    if args[0] == "docker" and "--host" in args:
        environment.pop("DOCKER_HOST", None)
        environment.pop("DOCKER_CONTEXT", None)
    process = await asyncio.create_subprocess_exec(
        executable,
        *args[1:],
        cwd=cwd,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    data = bytearray()
    try:
        async with asyncio.timeout(timeout):
            assert process.stdout is not None
            while block := await process.stdout.read(4096):
                data.extend(block)
                if len(data) > limit:
                    process.kill()
                    await process.wait()
                    return 137, bytes(data[:limit]).decode(
                        "utf-8", errors="replace"
                    ) + "\n[output limit exceeded]"
            code = await process.wait()
            return code, data.decode("utf-8", errors="replace")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def allowed(path: str, config: CodingRepository) -> bool:
    try:
        FileEdit(path=path, content="")
    except ValueError:
        return False
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in config.files)


async def snapshot(config: CodingRepository, target: Path) -> tuple[str, dict[str, str]]:
    source = config.path.resolve(strict=True)
    code, revision = await command(
        ["git", "-C", str(source), "rev-parse", "--verify", "HEAD^{commit}"], source
    )
    revision = revision.strip()
    if code or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise WorkflowError("workflow_validation")
    code, tree = await command(
        ["git", "-C", str(source), "ls-tree", "-rz", "--full-tree", revision], source
    )
    if code:
        raise WorkflowError("workflow_validation")
    files: dict[str, str] = {}
    for record in tree.split("\0"):
        if not record:
            continue
        metadata, path = record.split("\t", 1)
        mode, kind, blob = metadata.split()
        if not allowed(path, config):
            continue
        if mode not in ("100644", "100755") or kind != "blob":
            raise WorkflowError("tool_permission")
        code, content = await command(
            ["git", "-C", str(source), "cat-file", "blob", blob], source, 32768
        )
        if code or "\x00" in content or "\ufffd" in content or len(files) >= 128:
            raise WorkflowError("workflow_validation")
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="")
        destination.chmod(0o755 if mode == "100755" else 0o644)
        files[path] = content
    if not files:
        raise WorkflowError("tool_permission")
    return revision, files


async def local_engine(workspace: Path) -> str:
    endpoint = os.getenv("DOCKER_HOST")
    if endpoint is None:
        code, endpoint = await command(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], workspace
        )
        if code:
            raise WorkflowError("tool_permission")
        endpoint = endpoint.strip()
    if not endpoint.startswith(("unix://", "npipe://")):
        raise WorkflowError("tool_permission")
    return endpoint


def search_files(files: dict[str, str], terms: list[str]) -> list[dict[str, str | int]]:
    """Literal, bounded code search within the already authorized snapshot only."""
    matches: list[dict[str, str | int]] = []
    if not terms:
        return matches
    for path, content in sorted(files.items()):
        for number, line in enumerate(content.splitlines(), 1):
            if any(term in line for term in terms):
                matches.append({"path": path, "line": number, "text": line[:500]})
                if len(matches) == 32:
                    return matches
    return matches


async def sandbox(
    workspace: Path, config: CodingRepository, argv: list[str], timeout: int
) -> TestOutcome:
    if not argv or any("\x00" in a for a in argv):
        raise WorkflowError("tool_permission")
    name = "godfather-coding-" + uuid4().hex
    if "," in str(workspace):
        raise WorkflowError("tool_permission")
    endpoint = await local_engine(workspace)
    options = [
        "docker",
        "--host",
        endpoint,
        "run",
        "--name",
        name,
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=128",
        "--memory=512m",
        "--cpus=1",
        "--user=65534:65534",
        "--mount",
        f"type=bind,source={workspace},target=/input,readonly",
        "--workdir=/workspace",
        "--tmpfs=/tmp:rw,size=64m,mode=1777",
        "--tmpfs=/workspace:rw,size=256m,mode=1777",
        "--env=HOME=/tmp",
        "--entrypoint=/bin/sh",
        config.image,
        "-c",
        'cp -R /input/. /workspace/ && exec "$@"',
        "godfather-tests",
        *argv,
    ]
    try:
        code, output = await command(options, workspace, limit=16000, timeout=timeout)
        return TestOutcome(command=argv, exit_code=code, output=output)
    finally:
        # Only this generated disposable container is removed; no host/repository cleanup commands.
        await asyncio.shield(
            command(
                ["docker", "--host", endpoint, "rm", "--force", name],
                workspace,
                limit=4096,
                timeout=15,
            )
        )


async def execute(
    config: CodingRepository,
    instruction: WorkflowInput,
    step: WorkflowStep,
    provider: Provider,
    deployment: ModelDeployment,
) -> tuple[CodingOutput, InferenceUsage]:
    with tempfile.TemporaryDirectory(prefix="godfather-coding-") as temporary:
        root = Path(temporary)
        original, workspace = root / "original", root / "workspace"
        original.mkdir()
        workspace.mkdir()
        revision, files = await snapshot(config, original)
        matches = search_files(files, instruction.search_terms)
        shutil.copytree(original, workspace, dirs_exist_ok=True)
        # A Linux container runs as an unprivileged UID, with access to only this disposable copy.
        for path in [workspace, *workspace.rglob("*")]:
            path.chmod(0o777 if path.is_dir() else path.stat().st_mode | 0o666)
        prompt = (
            "Inspect the approved snapshot. Return only JSON with summary and edits. "
            "Each edit has path and complete replacement content. Do not request shell commands. "
            "Do not change unrelated files. Tests are selected by the owner, not by the model.\n"
            + step.instruction
            + "\nTask:\n"
            + instruction.instruction
            + "\nFiles:\n"
            + json.dumps(files)
            + "\nLiteral code search matches:\n"
            + json.dumps(matches)
        )
        if len(prompt) > 32768:
            raise WorkflowError("workflow_validation")

        async def ignore(text: str) -> None:
            pass

        result = await generate(
            provider,
            deployment,
            StructuredRequest(
                prompt=prompt,
                stream=False,
                parameters=step.parameters,
                output_schema=CodingPlan.model_json_schema(),
            ),
            step.timeout_seconds,
            ignore,
        )
        plan = CodingPlan.model_validate_json(result.text)
        if len({e.path.casefold() for e in plan.edits}) != len(plan.edits):
            raise WorkflowError("workflow_validation")
        for edit in plan.edits:
            if not allowed(edit.path, config):
                raise WorkflowError("tool_permission")
            destination = workspace / edit.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(edit.content, encoding="utf-8", newline="")
            destination.chmod(destination.stat().st_mode | 0o666)
        tests = [
            await sandbox(workspace, config, argv, step.timeout_seconds) for argv in config.commands
        ]
        changes = []
        for path in workspace.rglob("*"):
            if path.is_symlink():
                raise WorkflowError("tool_permission")
            if path.is_file() and allowed(path.relative_to(workspace).as_posix(), config):
                relative = path.relative_to(workspace).as_posix()
                if path.stat().st_size > 32768:
                    raise WorkflowError("workflow_validation")
                if path.read_text(encoding="utf-8") != files.get(relative):
                    changes.append(relative)
        # Diff only approved source files; exclude build output produced by the tests.
        review = root / "review"
        review.mkdir()
        for relative in set(files) | set(changes):
            source = workspace / relative
            if source.is_file():
                destination = review / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            elif relative in files:
                changes.append(relative)
        code, diff = await command(
            [
                "git",
                "--no-pager",
                "diff",
                "--no-index",
                "--no-ext-diff",
                "--no-textconv",
                "--",
                "original",
                "review",
            ],
            root,
            limit=131000,
        )
        if code not in (0, 1):
            raise WorkflowError("workflow_validation")
        diff = diff.replace("a/original/", "a/").replace("b/review/", "b/")
        summary = plan.summary
        if any(t.exit_code != 0 for t in tests):
            summary = "Tests failed; review the patch and test output.\n\n" + summary
        elif not tests:
            summary = "No test commands were approved; this patch is untested.\n\n" + summary
        return CodingOutput(
            summary=summary[:8192],
            repository_id=config.id,
            base_commit=revision,
            files_changed=sorted(set(changes)),
            diff=diff,
            tests=tests,
            search_matches=matches,
        ), result.usage
