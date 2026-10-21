"""Local project consent helpers. Never install tools, pull images or change a repository."""

import json
import os
import re
import shlex
from pathlib import Path
from uuid import UUID, uuid4

from godfather_contracts import Contract
from godfather_contracts.coding import CodingRepository, CodingSetupOptions

from godfather_worker.client import WorkerClient
from godfather_worker.coding import command, local_engine


def setup_options(identity: dict[str, str], origin: str) -> CodingSetupOptions:
    data = WorkerClient(origin, identity["token"]).post_document(
        "/api/v1/workers/coding/options", Contract()
    )
    options = CodingSetupOptions.model_validate(data)
    if str(options.owner_id) != identity["owner_id"]:
        raise ValueError("The saved connection owner does not match. Reconnect this computer.")
    return options


async def local_images(folder: Path) -> dict[str, str]:
    endpoint = await local_engine(folder)
    code, output = await command(
        ["docker", "--host", endpoint, "image", "ls", "--no-trunc", "--format", "{{json .}}"],
        folder,
    )
    if code:
        raise ValueError("Open Docker Desktop or your local Docker engine, then try again.")
    images: dict[str, str] = {}
    for line in output.splitlines():
        row = json.loads(line)
        image = str(row["ID"])
        if re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            label = f"{row['Repository']}:{row['Tag']} ({image[7:19]})"
            images[label] = image
    return images


def project_config(
    *,
    name: str,
    path: str,
    image: str,
    owner: UUID,
    workspace: UUID,
    patterns: str,
    test_command: str,
) -> CodingRepository:
    folder = Path(path).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Choose your project's Git repository folder.")
    argv = shlex.split(test_command, posix=True)
    if not argv or len(argv) > 32:
        raise ValueError("Enter one test command, with at most 32 arguments.")
    return CodingRepository(
        id=uuid4(),
        name=name.strip(),
        path=folder,
        image=image,
        allowed_user_ids=[owner],
        allowed_workspace_ids=[workspace],
        files=[p.strip() for p in patterns.split(",") if p.strip()],
        commands=[argv],
    )


async def check_project(repository: CodingRepository) -> None:
    code, output = await command(["git", "rev-parse", "--show-toplevel"], repository.path)
    if code or Path(output.strip()).resolve() != repository.path:
        raise ValueError("Choose the top-level folder of a Git repository you can access.")
    code, output = await command(["git", "rev-parse", "--verify", "HEAD^{commit}"], repository.path)
    if code or not re.fullmatch(r"[0-9a-f]{40}", output.strip()):
        raise ValueError("Commit the project in Git before enabling coding access.")
    endpoint = await local_engine(repository.path)
    code, output = await command(
        ["docker", "--host", endpoint, "image", "inspect", "--format", "{{.Os}}", repository.image],
        repository.path,
    )
    if code or output.strip() != "linux":
        raise ValueError(
            "Choose an already installed Linux test environment. No images are downloaded."
        )


def save_repositories(path: Path, repositories: list[CodingRepository]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps([r.model_dump(mode="json") for r in repositories]), encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
