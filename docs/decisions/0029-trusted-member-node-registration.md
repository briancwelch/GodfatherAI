# Trusted members can register owned computers

Status: accepted by the owner, 2026-10-23. Deployed in coordinator 0.9.0-rc.4;
see the [deployment verification](../operations/member-node-registration-verification-2026-10-23.md).

The Godfather is an invitation-only platform for vetted members. Registering an
owned computer is a normal member capability. Previously only contributors and
platform administrators received `nodes.contribute`, so a member could sign in
but the pairing page and API refused to connect their computer.

Grant `nodes.contribute` to the member role in the existing central permission
mapping. Keep all checks in browser enrollment, approval, credential exchange,
worker authentication and scheduling. Existing member accounts gain the
permission when the updated coordinator calculates it on the next request;
there is no account migration or role promotion. The existing contributor role
remains compatible and currently has the same permissions as member.

Invitation-only Google sign-in, enabled-account checks, proof-of-possession
pairing, owner-bound credentials and revocation remain mandatory. A member
cannot choose another owner or revoke another owner's pairing or machine
credential. Platform administration, workspace access, local file/tool grants
and paid-provider consent retain their independent authorization checks.

This is a coordinator permission change. No worker protocol, installer,
dependency or database migration changes. Deployment requires its own explicit
authorization. Tests cover legacy and current role storage, invited member and
contributor registration, ownership isolation and disabled/revoked access.

Local validation on 2026-10-23: 385 Python unit tests passed, with four existing
skips for unavailable sandbox images or host symlink permission. All 89
PostgreSQL authentication, worker enrollment and node integration tests passed
against disposable `godfather_test`, using the existing test image with current
source mounted read-only. Google's upstream exchange was mocked; no real Google
account was accessed. All 43 dashboard component tests, Ruff formatting/lint,
strict mypy and updated-document Prettier checks passed. No frontend source or
worker package changed. Production activation was subsequently authorized and
is recorded in the linked deployment verification.
