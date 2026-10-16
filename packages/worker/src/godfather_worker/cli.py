"""Run one outbound worker; synthetic execution requires explicit simulator opt-in."""

import argparse
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from uuid import uuid4

from godfather_contracts import Heartbeat, Registration
from godfather_contracts.jobs import JobPoll, PollResponse
from pydantic import ValidationError

from godfather_worker.client import WorkerClient, retryable
from godfather_worker.discovery import discover, discover_resources
from godfather_worker.jobs import execute
from godfather_worker.simulated import profile

logger = logging.getLogger("godfather.worker")


def emit(event: str, **fields: object) -> None:
    print(
        json.dumps({"timestamp": datetime.now(UTC).isoformat(), "event": event, **fields}),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--credential-file", required=True, type=Path)
    parser.add_argument("--simulate", choices=("LV-01", "LV-02", "LA-01", "LA-02"))
    parser.add_argument("--primary", action="append", default=[])
    parser.add_argument("--secondary", action="append", default=[])
    parser.add_argument("--policy", choices=("dedicated", "preferred", "shared"))
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--execute-synthetic", action="store_true")
    parser.add_argument("--step-seconds", type=float, default=0)
    parser.add_argument("--allow-owner", type=str, action="append", default=[])
    parser.add_argument("--allow-workspace", type=str, action="append", default=[])
    args = parser.parse_args()
    try:
        if args.execute_synthetic and not args.simulate:
            raise ValueError("Synthetic execution requires a simulated profile")
        if not 0 <= args.step_seconds <= 30:
            raise ValueError("Synthetic step duration must be between 0 and 30 seconds")
        credentials = json.loads(args.credential_file.read_text(encoding="utf-8"))
        if (
            not isinstance(credentials, dict)
            or credentials.get("kind") != "worker"
            or not isinstance(credentials.get("token"), str)
        ):
            raise ValueError("A node-specific worker credential is required")
        client = WorkerClient(args.url, credentials["token"])
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
        values["allowed_job_owner_ids"] = args.allow_owner
        values["allowed_workspace_ids"] = args.allow_workspace
        registration = Registration.model_validate({**values, "session_id": uuid4()})
    except (OSError, KeyError, ValueError, TypeError):
        emit("worker.configuration_invalid")
        return 1
    stop = threading.Event()
    registered = False
    node_id = None
    delay = 1
    try:
        while not stop.is_set():
            try:
                if not registered:
                    result = client.post("/api/v1/workers/register", registration)
                    node_id = result.node_id
                    registered = True
                    emit(
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
                    emit("worker.heartbeat", node_id=str(node_id), state=result.state)
                delay = 1
                if args.execute_synthetic:
                    assert node_id is not None
                    polled = PollResponse.model_validate(
                        client.post_document(
                            f"/api/v1/workers/{node_id}/jobs/poll",
                            JobPoll(session_id=registration.session_id),
                        )
                    )
                    if polled.assignment is not None:
                        execute(
                            client,
                            node_id,
                            registration,
                            polled.assignment,
                            stop,
                            args.step_seconds,
                            result.heartbeat_interval_seconds,
                        )
                        emit(
                            "worker.synthetic_attempt_finished",
                            job_id=str(polled.assignment.job.id),
                        )
                    else:
                        stop.wait(min(1, result.heartbeat_interval_seconds))
                else:
                    stop.wait(result.heartbeat_interval_seconds)
            except HTTPError as error:
                if args.execute_synthetic and error.code == 409 and "/jobs/" in error.url:
                    emit("worker.stale_attempt_discarded")
                    stop.wait(1)
                    continue
                if not retryable(error):
                    emit("worker.request_refused", status_code=error.code)
                    return 1
                emit("worker.coordinator_unavailable", status_code=error.code)
                registered = False
                stop.wait(delay)
                delay = min(delay * 2, 30)
            except (URLError, OSError, TimeoutError):
                emit("worker.coordinator_unavailable")
                registered = False
                stop.wait(delay)
                delay = min(delay * 2, 30)
            except (ValidationError, ValueError):
                emit("worker.invalid_coordinator_response")
                return 1
    except KeyboardInterrupt:
        emit("worker.stopped", node_id=str(node_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
