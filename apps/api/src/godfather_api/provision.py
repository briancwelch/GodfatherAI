"""Offline, database-authorized local credential provisioning; no HTTP bootstrap secret.

Stdout is a one-time credential document, intended for capture by provision_local.
Never redirect it to a shared log. Tokens are never stored plaintext in PostgreSQL.
"""

import argparse
import json
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.models import AccessCredential, Event, Node, User, Workspace
from godfather_api.nodes import record, token_digest


def provision(
    database: Database,
    kind: str,
    *,
    email: str | None = None,
    owner_id: UUID | None = None,
    name: str | None = None,
) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    with database.sessions.begin() as session:
        if kind == "admin":
            if email is None or not (3 <= len(email) <= 320) or "@" not in email:
                raise ValueError("A valid local administrator email is required")
            owner = session.scalar(select(User).where(User.email == email).with_for_update())
            if owner is None:
                owner = User(
                    email=email, display_name="Local platform administrator", role="platform_admin"
                )
                session.add(owner)
                session.flush()
            if not owner.enabled or owner.role != "platform_admin":
                raise ValueError("Existing user is not an enabled administrator")
        else:
            owner = session.get(User, owner_id) if owner_id else None
            if owner is None or not owner.enabled:
                raise ValueError("An existing enabled owner is required")
            if name is None or not (1 <= len(name) <= 100):
                raise ValueError("A node name of 1 to 100 characters is required")
        credential = AccessCredential(
            owner_id=owner.id, kind=kind, name=name, token_hash=token_digest(token)
        )
        session.add(credential)
        session.flush()
        session.add(
            Event(
                actor_id=owner.id,
                type="credential.provisioned",
                details={"credential_id": str(credential.id), "kind": kind},
            )
        )
        return {
            "token": token,
            "credential_id": str(credential.id),
            "owner_id": str(owner.id),
            "kind": kind,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("admin", "worker", "revoke", "workspace"))
    parser.add_argument("--email")
    parser.add_argument("--owner-id", type=UUID)
    parser.add_argument("--name")
    parser.add_argument("--credential-id", type=UUID)
    args = parser.parse_args()
    database = Database(Settings())
    try:
        if args.kind == "workspace":
            if args.owner_id is None or args.name is None or not 1 <= len(args.name) <= 200:
                raise ValueError("Workspace owner and name are required")
            with database.sessions.begin() as session:
                owner = session.get(User, args.owner_id)
                if owner is None or not owner.enabled:
                    raise ValueError("Enabled owner is required")
                workspace = Workspace(owner_id=owner.id, name=args.name)
                session.add(workspace)
                session.flush()
                session.add(
                    Event(
                        actor_id=owner.id, workspace_id=workspace.id, type="workspace.provisioned"
                    )
                )
                document = {"workspace_id": str(workspace.id), "owner_id": str(owner.id)}
            print(json.dumps(document))
        elif args.kind == "revoke":
            with database.sessions.begin() as session:
                credential = session.get(AccessCredential, args.credential_id, with_for_update=True)
                if credential is None:
                    raise ValueError("Credential not found")
                credential.revoked = True
                if credential.node_id is not None:
                    node = session.get(Node, credential.node_id, with_for_update=True)
                    if node is not None:
                        node.state = "disabled"
                        record(session, node, "node.credential_revoked", {}, credential.owner_id)
                session.add(
                    Event(
                        actor_id=credential.owner_id,
                        type="credential.revoked",
                        details={"credential_id": str(credential.id)},
                    )
                )
            print(json.dumps({"status": "revoked"}))
        else:
            print(
                json.dumps(
                    provision(
                        database,
                        args.kind,
                        email=args.email,
                        owner_id=args.owner_id,
                        name=args.name,
                    )
                )
            )
    except (SQLAlchemyError, ValueError):
        # No DB arguments or credential values in diagnostics, even on constraint errors.
        parser.exit(
            1, "Provisioning refused: check owner, unique node name, and database readiness.\n"
        )
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
