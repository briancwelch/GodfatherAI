"""Offline database-authorized Google identity binding and account recovery.

No passwords or Google tokens are accepted. Binding preauthorizes a subject; actual
login still requires Authlib verification of Google's signed ID token.
"""

import argparse
import re
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError

from godfather_api.authentication import audit
from godfather_api.config import Settings
from godfather_api.database import Database
from godfather_api.models import AccessCredential, GoogleIdentity, HumanSession, User


def bind(database: Database, subject: str, user_id: UUID, *, replace: bool = False) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", subject):
        raise ValueError("Invalid Google subject")
    with database.sessions.begin() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(909001)"))
        user = session.get(User, user_id, with_for_update=True)
        if user is None:
            raise ValueError("User not found")
        other = session.scalar(select(GoogleIdentity).where(GoogleIdentity.subject == subject))
        if other is not None and other.user_id != user_id:
            raise ValueError("Identity already bound")
        identity = session.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user_id))
        if identity is not None and identity.subject != subject and not replace:
            raise ValueError("Explicit replacement required")
        if identity is None:
            session.add(GoogleIdentity(user_id=user_id, subject=subject))
        else:
            identity.subject = subject
        session.execute(
            update(HumanSession).where(HumanSession.owner_id == user_id).values(revoked=True)
        )
        session.execute(
            update(AccessCredential)
            .where(AccessCredential.owner_id == user_id, AccessCredential.kind == "admin")
            .values(revoked=True)
        )
        audit(session, "identity_bound_offline", target=user_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("link", "recover"))
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--subject")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    database = Database(Settings())
    try:
        if args.action == "link":
            if args.subject is None:
                raise ValueError("Explicit verified subject required")
            bind(database, args.subject, args.user_id, replace=args.replace)
        else:
            with database.sessions.begin() as session:
                user = session.get(User, args.user_id, with_for_update=True)
                if user is None:
                    raise ValueError("User not found")
                user.enabled = True
                session.execute(
                    update(HumanSession)
                    .where(HumanSession.owner_id == user.id)
                    .values(revoked=True)
                )
                audit(session, "account_recovered_offline", target=user.id)
        print("Identity operation completed; Google authentication is still required.")
    except (ValueError, SQLAlchemyError):
        parser.exit(
            1,
            "Identity operation refused. Check UUID, subject binding and database readiness.\n",
        )
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
