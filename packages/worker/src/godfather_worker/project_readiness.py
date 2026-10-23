"""Read-only checks for optional coding projects; never install or change anything."""

import asyncio

from godfather_agent_runtime import WorkflowError
from godfather_contracts.coding import CodingRepository

from godfather_worker.coding import command, local_engine

# Only these codes leave the probe. Raw process output, paths and exceptions do not.
PROJECT_ISSUES = {
    "folder_missing": (
        "Project folder is unavailable.",
        "Restore access to the saved folder, or remove and re-add the project in Projects.",
    ),
    "git_unavailable": (
        "Git is unavailable.",
        "Install or restore Git on this computer, then reopen Consigliere.",
    ),
    "docker_unavailable": (
        "Local Docker is unavailable.",
        "Open Docker Desktop or your local Docker engine and select a local context.",
    ),
    "docker_not_linux": (
        "Docker is using Windows containers.",
        "Switch Docker Desktop to Linux containers.",
    ),
    "image_missing": (
        "The saved Docker test image is missing.",
        "Restore the original image in local Docker, or remove and re-add the project "
        "in Projects using an installed Linux test environment.",
    ),
    "image_not_linux": (
        "The saved Docker test image is not a Linux image.",
        "Remove and re-add the project in Projects using an installed Linux test environment.",
    ),
    "check_timeout": (
        "The project dependency check timed out.",
        "Check that the project folder, Git and local Docker respond normally.",
    ),
}


def project_issue_message(repository: CodingRepository, code: str) -> str:
    problem, remedy = PROJECT_ISSUES[code]
    image = f" Saved image: {repository.image}." if code == "image_missing" else ""
    return f"{repository.name}: {problem}{image} {remedy} Then Pause and Resume to check again."


async def project_issue(repository: CodingRepository) -> str | None:
    """Withhold an unready project while unrelated worker capabilities remain usable."""
    try:
        async with asyncio.timeout(15):
            if not repository.path.is_dir():
                return "folder_missing"
            try:
                code, _ = await command(["git", "--version"], repository.path)
                if code:
                    return "git_unavailable"
            except TimeoutError:
                raise
            except (OSError, WorkflowError):
                return "git_unavailable"
            try:
                endpoint = await local_engine(repository.path)
                code, output = await command(
                    ["docker", "--host", endpoint, "info", "--format", "{{.OSType}}"],
                    repository.path,
                )
                if code:
                    return "docker_unavailable"
                if output.strip() != "linux":
                    return "docker_not_linux"
                code, output = await command(
                    [
                        "docker",
                        "--host",
                        endpoint,
                        "image",
                        "inspect",
                        "--format",
                        "{{.Os}}",
                        repository.image,
                    ],
                    repository.path,
                )
                if code:
                    # Distinguish a missing image from an engine that stopped during the probe.
                    engine_code, _ = await command(
                        ["docker", "--host", endpoint, "info", "--format", "{{.OSType}}"],
                        repository.path,
                    )
                    return "docker_unavailable" if engine_code else "image_missing"
                return None if output.strip() == "linux" else "image_not_linux"
            except TimeoutError:
                raise
            except (OSError, WorkflowError):
                return "docker_unavailable"
    except TimeoutError:
        return "check_timeout"
    except OSError:
        return "folder_missing"


async def available_projects(
    repositories: list[CodingRepository],
) -> tuple[list[CodingRepository], list[dict[str, str]]]:
    # At most eight owner-approved repositories; check concurrently within one deadline.
    codes = await asyncio.gather(*(project_issue(repository) for repository in repositories))
    ready, issues = [], []
    for repository, code in zip(repositories, codes, strict=True):
        if code:
            issues.append({"repository_id": str(repository.id), "code": code})
        else:
            ready.append(repository)
    return ready, issues
