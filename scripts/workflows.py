"""Local agent/workflow client using private credential and instruction files."""

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request
from uuid import UUID

from godfather_contracts import Contract
from godfather_contracts.agents import (
    AgentCreate,
    AgentDefinition,
    AgentVersionCreate,
    WorkflowInput,
    WorkflowSubmission,
)
from godfather_worker.client import WorkerClient

from scripts.workflow_demo import demonstration_definition


class Control(Contract):
    action: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "demo-definition",
            "create",
            "list",
            "version",
            "enable",
            "disable",
            "submit",
            "inspect",
            "steps",
            "checkpoints",
            "result",
            "cancel",
        ),
    )
    parser.add_argument("--credential-file", type=Path)
    parser.add_argument("--definition-file", type=Path)
    parser.add_argument("--instruction-file", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--workspace-id", type=UUID)
    parser.add_argument("--agent-id", type=UUID)
    parser.add_argument("--agent-version", type=int, default=1)
    parser.add_argument("--job-id", type=UUID)
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.action == "demo-definition":
        if not args.model or args.definition_file is None:
            parser.error("demo-definition requires --model and --definition-file")
        args.definition_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(
            os.open(args.definition_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(demonstration_definition(args.model).model_dump_json(indent=2) + "\n")
        print("Created portable demonstration definition")
        return 0
    if args.credential_file is None:
        parser.error("--credential-file is required")
    credential = json.loads(args.credential_file.read_text(encoding="utf-8"))
    if credential.get("kind") != "admin":
        parser.error("An administrator credential is required")
    client = WorkerClient(args.url, credential["token"])
    result: object = None
    if args.action in ("create", "version"):
        if args.definition_file is None:
            parser.error("--definition-file is required")
        definition = AgentDefinition.model_validate_json(
            args.definition_file.read_text(encoding="utf-8")
        )
        if args.action == "create":
            if args.workspace_id is None:
                parser.error("--workspace-id is required")
            result = client.post_document(
                "/api/v1/agents", AgentCreate(workspace_id=args.workspace_id, definition=definition)
            )
        else:
            if args.agent_id is None:
                parser.error("--agent-id is required")
            result = client.post_document(
                f"/api/v1/agents/{args.agent_id}/versions",
                AgentVersionCreate(expected_version=args.agent_version, definition=definition),
            )
    elif args.action in ("enable", "disable"):
        if args.agent_id is None:
            parser.error("--agent-id is required")
        result = client.post_document(
            f"/api/v1/agents/{args.agent_id}/versions/{args.agent_version}/control",
            Control(action=args.action),
        )
    elif args.action == "submit":
        if args.workspace_id is None or args.agent_id is None or args.instruction_file is None:
            parser.error("submit requires workspace, agent and instruction file")
        result = client.post_document(
            "/api/v1/workflow/jobs",
            WorkflowSubmission(
                workspace_id=args.workspace_id,
                agent_id=args.agent_id,
                agent_version=args.agent_version,
                input=WorkflowInput(instruction=args.instruction_file.read_text(encoding="utf-8")),
            ),
        )
    else:
        if args.action == "list":
            if args.workspace_id is None:
                parser.error("--workspace-id is required")
            route = f"agents?workspace_id={args.workspace_id}"
        else:
            if args.job_id is None:
                parser.error("--job-id is required")
            route = (
                f"jobs/{args.job_id}/cancel"
                if args.action == "cancel"
                else f"workflow/jobs/{args.job_id}"
            )
            if args.action not in ("inspect", "cancel"):
                route += "/" + args.action
        with client.opener.open(
            Request(
                client.url + "/api/v1/" + route,
                headers={"Authorization": "Bearer " + client.token},
                method="POST" if args.action == "cancel" else "GET",
            ),
            timeout=15,
        ) as response:
            result = json.loads(response.read(1024**2))
    if args.action in ("create", "version", "enable", "disable", "submit") and isinstance(
        result, dict
    ):
        result = {
            key: result[key]
            for key in ("id", "version", "workspace_id", "enabled", "status")
            if key in result
        }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
