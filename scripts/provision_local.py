"""Capture one-time local credentials directly into a private, ignored file.

This is local database administration through Docker, never a remote onboarding API.
"""

import argparse
import json
import os
from pathlib import Path

from scripts.check_api_restart import compose
from scripts.dev import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("admin", "worker", "revoke", "workspace"))
    parser.add_argument("--email")
    parser.add_argument("--owner-id")
    parser.add_argument("--name")
    parser.add_argument("--credential-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    names = compose("ps", "--format", "{{.Name}}").splitlines()
    if not names or any(not name.startswith("godfather-local-") for name in names):
        parser.error("Only the local godfather-local Compose project is permitted")
    command = ["exec", "-T", "api", "python", "-m", "godfather_api.provision", args.kind]
    for option in ("email", "owner_id", "name", "credential_id"):
        value = getattr(args, option)
        if value:
            command.extend(["--" + option.replace("_", "-"), value])
    if args.kind == "workspace":
        document = json.loads(compose(*command))
        print(f"Created workspace {document['workspace_id']}; owner_id={document['owner_id']}")
        return 0
    if args.kind == "revoke":
        compose(*command)
        print("Credential revoked.")
        return 0
    output = args.output or ROOT / ".cache" / "credentials" / f"{args.name or 'admin'}.json"
    # Requiring an explicit safe file name avoids traversal in a node's display name.
    if (
        args.output is None
        and args.name
        and (Path(args.name).name != args.name or args.name in (".", ".."))
    ):
        parser.error("Use --output with a safe private file path")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            document = json.loads(compose(*command))
            json.dump(document, stream)
        print(f"Saved {args.kind} credential to {output}; owner_id={document['owner_id']}")
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
