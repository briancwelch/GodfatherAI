"""Run one outbound worker; synthetic execution requires explicit simulator opt-in."""

import argparse
import asyncio
import json
import logging
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from uuid import uuid4

from godfather_agent_runtime import WorkflowError
from godfather_agent_runtime.tools import ToolError
from godfather_agent_runtime.tools import definition as tool_definition
from godfather_contracts import Heartbeat, Registration, ToolReference
from godfather_contracts.coding import CODING_RUNTIME, REPOSITORY_PREFIX, CodingRepository
from godfather_contracts.jobs import JobPoll, PollResponse
from godfather_contracts.model_management import INSTALL_RUNTIME, PROVIDER_RUNTIME_PREFIX
from godfather_model_gateway import ProviderConfig
from pydantic import ValidationError

from godfather_worker.agents import execute_agent
from godfather_worker.client import WorkerClient, retryable
from godfather_worker.discovery import discover, discover_resources
from godfather_worker.inference import discover_models, execute_inference
from godfather_worker.jobs import execute
from godfather_worker.model_management import execute_installation
from godfather_worker.simulated import profile

logger = logging.getLogger("godfather.worker")


def emit(event: str, **fields: object) -> None:
    print(
        json.dumps({"timestamp": datetime.now(UTC).isoformat(), "event": event, **fields}),
        flush=True,
    )


def main(
    argv: list[str] | None = None,
    *,
    credential: dict[str, str] | None = None,
    stop_event: threading.Event | None = None,
    observer: Callable[..., None] | None = None,
    worker_client: WorkerClient | None = None,
) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if arguments and arguments[0] == "provider":
        from godfather_worker.provider_credentials import main as provider_main

        return provider_main(arguments[1:])
    notify = observer or emit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--credential-file", required=credential is None, type=Path)
    parser.add_argument("--simulate", choices=("LV-01", "LV-02", "LA-01", "LA-02"))
    parser.add_argument("--primary", action="append", default=[])
    parser.add_argument("--secondary", action="append", default=[])
    parser.add_argument("--policy", choices=("dedicated", "preferred", "shared"))
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--execute-synthetic", action="store_true")
    parser.add_argument("--execute-workflows", action="store_true")
    parser.add_argument(
        "--account-providers",
        action="store_true",
        help="Owner opt-in to explicitly authorized account API connections",
    )
    parser.add_argument(
        "--allow-model-installation",
        action="store_true",
        help="Owner opt-in: accept approved local Ollama catalog downloads",
    )
    parser.add_argument(
        "--allow-tool", action="append", default=[], help="Owner grant: TOOL_NAME@VERSION"
    )
    parser.add_argument("--allow-tool-permission", action="append", default=[])
    parser.add_argument(
        "--pause-after-checkpoint", type=int, help="Simulator-only fault-injection barrier"
    )
    parser.add_argument(
        "--inference-config",
        type=Path,
        help="Opt in to text inference with worker-owned provider JSON settings",
    )
    parser.add_argument("--step-seconds", type=float, default=0)
    parser.add_argument(
        "--coding-config",
        type=Path,
        help="Owner-approved repository, container image and test command configuration",
    )
    parser.add_argument("--allow-owner", type=str, action="append", default=[])
    parser.add_argument("--allow-workspace", type=str, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.execute_synthetic and not args.simulate:
            raise ValueError("Synthetic execution requires a simulated profile")
        if args.inference_config and args.execute_synthetic:
            raise ValueError("Choose synthetic execution or inference per worker process")
        if args.execute_workflows and not args.inference_config and not args.account_providers:
            raise ValueError("Workflow execution requires an inference configuration")
        if args.pause_after_checkpoint is not None and (
            not args.simulate
            or not args.execute_workflows
            or not 1 <= args.pause_after_checkpoint <= 32
        ):
            raise ValueError("Checkpoint pauses require an explicitly simulated workflow worker")
        configs: list[ProviderConfig] = []
        repositories: list[CodingRepository] = []
        if args.coding_config:
            if not args.execute_workflows or args.simulate:
                raise ValueError("Coding requires a physical opted-in workflow worker")
            repositories = [
                CodingRepository.model_validate(c)
                for c in json.loads(args.coding_config.read_text(encoding="utf-8"))
            ]
            if not 1 <= len(repositories) <= 8 or len({c.id for c in repositories}) != len(
                repositories
            ):
                raise ValueError("Configure one to eight distinct coding repositories")
            from godfather_worker.coding import command, local_engine

            git_code, _ = asyncio.run(command(["git", "--version"], repositories[0].path))
            if git_code:
                raise ValueError("Coding requires an existing Git installation")

            for repository in repositories:
                endpoint = asyncio.run(local_engine(repository.path))
                code, output = asyncio.run(
                    command(
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
                )
                if code or output.strip() != "linux":
                    raise ValueError(
                        "Coding requires an existing pinned Linux image; no automatic downloads"
                    )
        if args.allow_model_installation and (not args.inference_config or args.simulate):
            raise ValueError(
                "Model installation requires a physical worker and local inference configuration"
            )
        if args.inference_config:
            raw_configs = json.loads(args.inference_config.read_text(encoding="utf-8"))
            if not isinstance(raw_configs, list) or not 1 <= len(raw_configs) <= 8:
                raise ValueError("Configure one to eight providers")
            configs = [ProviderConfig.model_validate(c) for c in raw_configs]
            if len({c.id for c in configs}) != len(configs):
                raise ValueError("Provider aliases must be unique")
            if args.execute_workflows and any(
                c.provider == "openai_compatible"
                and urlsplit(c.url).hostname not in ("localhost", "127.0.0.1", "::1")
                for c in configs
            ):
                raise ValueError("Phase 06 workflow providers must remain local")
        if not 0 <= args.step_seconds <= 30:
            raise ValueError("Synthetic step duration must be between 0 and 30 seconds")
        credentials = credential or json.loads(args.credential_file.read_text(encoding="utf-8"))
        if (
            not isinstance(credentials, dict)
            or credentials.get("kind") != "worker"
            or not isinstance(credentials.get("token"), str)
        ):
            raise ValueError("A node-specific worker credential is required")
        client = worker_client or WorkerClient(args.url, credentials["token"])
        advertisement = profile(args.simulate) if args.simulate else discover()
        values = advertisement.model_dump()
        if args.primary:
            values["primary_capabilities"] = args.primary
        if args.secondary:
            values["secondary_capabilities"] = args.secondary
        if args.policy:
            values["scheduling_policy"] = args.policy
        if args.concurrency is not None:
            values["concurrency_limit"] = args.concurrency
        values["job_protocol_version"] = 1 if args.execute_synthetic else None
        if configs or args.account_providers:
            if args.concurrency not in (None, 1):
                raise ValueError("Phase 05 inference workers execute one attempt at a time")
            values["concurrency_limit"] = 1
            values["inference_protocol_version"] = 1
            values["model_deployments"] = asyncio.run(discover_models(configs))
            if any(c.provider in ("openai", "anthropic") for c in configs):
                values["runtimes"] = [*values["runtimes"], "provider-connections-v1"]
        if args.account_providers:
            values["runtimes"] = [
                *values["runtimes"],
                "account-provider-keys-v1",
                "provider-connections-v1",
            ]
        if args.execute_workflows:
            tools = []
            for grant in args.allow_tool:
                name, version = grant.rsplit("@", 1)
                reference = ToolReference(name=name, version=int(version))
                tool_definition(reference)
                tools.append(reference)
            values["workflow_protocol_version"] = 1
            values["worker_tools"] = tools
            values["tool_permissions"] = args.allow_tool_permission
        if repositories:
            if "coding.workspace" not in args.allow_tool_permission:
                raise ValueError("The owner must explicitly grant coding.workspace")
            values["runtimes"] = [
                *values["runtimes"],
                CODING_RUNTIME,
                *(REPOSITORY_PREFIX + str(r.id) for r in repositories),
            ]
            values["coding_repositories"] = [
                {
                    "id": r.id,
                    "name": r.name,
                    "allowed_user_ids": r.allowed_user_ids,
                    "allowed_workspace_ids": r.allowed_workspace_ids,
                }
                for r in repositories
            ]
        if args.allow_model_installation:
            aliases = [c.id for c in configs if c.provider == "ollama"]
            if not aliases or any(len(alias) > 64 for alias in aliases):
                raise ValueError(
                    "Model installation requires an Ollama provider alias of up to 64 characters"
                )
            values["runtimes"] = list(
                dict.fromkeys(
                    [
                        *values["runtimes"],
                        INSTALL_RUNTIME,
                        *(PROVIDER_RUNTIME_PREFIX + alias for alias in aliases),
                    ]
                )
            )
        values["allowed_job_owner_ids"] = args.allow_owner
        values["allowed_workspace_ids"] = args.allow_workspace
        registration = Registration.model_validate({**values, "session_id": uuid4()})
    except (OSError, KeyError, ValueError, TypeError, ToolError, WorkflowError):
        notify("worker.configuration_invalid")
        return 1
    stop = stop_event or threading.Event()
    registered = False
    node_id = None
    delay = 1
    refresh_at = monotonic() + 30
    local_configs = list(configs)
    account_refresh = args.account_providers
    try:
        while not stop.is_set():
            try:
                if (
                    args.account_providers
                    and node_id is not None
                    and (account_refresh or monotonic() >= refresh_at)
                ):
                    from godfather_worker.account_providers import fetch

                    try:
                        configs = [*local_configs, *fetch(client, node_id, registration.session_id)]
                    except HTTPError as error:
                        if error.code not in (404, 503):
                            raise
                        configs = list(local_configs)
                        notify("worker.account_connections_unavailable")
                    account_refresh = False
                    refresh_at = 0
                if (configs or args.account_providers) and monotonic() >= refresh_at:
                    deployments = asyncio.run(discover_models(configs))
                    registration = registration.model_copy(
                        update={"model_deployments": deployments}
                    )
                    refresh_at = monotonic() + 30
                    registered = False  # Same session: atomically replaces durable inventory.
                if not registered:
                    result = client.post("/api/v1/workers/register", registration)
                    node_id = result.node_id
                    if account_refresh:
                        continue
                    registered = True
                    notify(
                        "worker.registered",
                        node_id=str(node_id),
                        source=registration.resources.source,
                        profile=args.simulate,
                    )
                else:
                    resources = registration.resources if args.simulate else discover_resources()[0]
                    result = client.post(
                        f"/api/v1/workers/{node_id}/heartbeat",
                        Heartbeat(session_id=registration.session_id, resources=resources),
                    )
                    notify("worker.heartbeat", node_id=str(node_id), state=result.state)
                delay = 1
                if args.execute_synthetic or configs:
                    assert node_id is not None
                    polled = PollResponse.model_validate(
                        client.post_document(
                            f"/api/v1/workers/{node_id}/jobs/poll",
                            JobPoll(session_id=registration.session_id),
                        )
                    )
                    if polled.provider_checks:
                        from godfather_worker.provider_checks import check_connections

                        asyncio.run(
                            check_connections(
                                client, node_id, registration, polled.provider_checks, configs
                            )
                        )
                        refresh_at = 0
                    if polled.assignment is not None:
                        notify("worker.attempt_started", job_id=str(polled.assignment.job.id))
                        if (
                            polled.assignment.job.type == "agent.workflow"
                            and args.execute_workflows
                        ):
                            asyncio.run(
                                execute_agent(
                                    client,
                                    node_id,
                                    registration,
                                    polled.assignment,
                                    stop,
                                    result.heartbeat_interval_seconds,
                                    configs,
                                    args.pause_after_checkpoint,
                                    repositories=repositories,
                                )
                            )
                        elif (
                            polled.assignment.job.type == "model.install"
                            and args.allow_model_installation
                        ):
                            asyncio.run(
                                execute_installation(
                                    client,
                                    node_id,
                                    registration,
                                    polled.assignment,
                                    stop,
                                    result.heartbeat_interval_seconds,
                                    configs,
                                )
                            )
                            refresh_at = (
                                0  # Advertise verified installation before taking another job.
                            )
                        elif polled.assignment.job.type == "inference.text" and configs:
                            asyncio.run(
                                execute_inference(
                                    client,
                                    node_id,
                                    registration,
                                    polled.assignment,
                                    stop,
                                    result.heartbeat_interval_seconds,
                                    configs,
                                )
                            )
                        else:
                            execute(
                                client,
                                node_id,
                                registration,
                                polled.assignment,
                                stop,
                                args.step_seconds,
                                result.heartbeat_interval_seconds,
                            )
                        notify(
                            "worker.attempt_finished",
                            job_id=str(polled.assignment.job.id),
                        )
                    else:
                        stop.wait(min(1, result.heartbeat_interval_seconds))
                else:
                    stop.wait(result.heartbeat_interval_seconds)
            except HTTPError as error:
                if worker_client is not None and error.code == 409 and not registered:
                    notify("worker.session_busy")
                    stop.wait(delay)
                    delay = min(delay * 2, 30)
                    continue
                if (
                    (args.execute_synthetic or configs)
                    and error.code == 409
                    and "/jobs/" in error.url
                ):
                    notify("worker.stale_attempt_discarded")
                    stop.wait(1)
                    continue
                if not retryable(error):
                    notify("worker.request_refused", status_code=error.code)
                    return 1
                notify("worker.coordinator_unavailable", status_code=error.code)
                registered = False
                stop.wait(delay)
                delay = min(delay * 2, 30)
            except (URLError, OSError, TimeoutError):
                notify("worker.coordinator_unavailable")
                registered = False
                stop.wait(delay)
                delay = min(delay * 2, 30)
            except (ValidationError, ValueError):
                notify("worker.invalid_coordinator_response")
                return 1
    except KeyboardInterrupt:
        notify("worker.stopped", node_id=str(node_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
