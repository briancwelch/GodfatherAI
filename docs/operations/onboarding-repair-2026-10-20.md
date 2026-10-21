# Invitation onboarding repair - 2026-10-20

Deployed application: **0.2.0-rc.5**, source revision
`b6256accd4980313b8ba9c6ec97d07ba4e6c02f6`. Deployment and SSH access to the
existing host were authorized by the user. Documentation-only follow-up commits
do not change the deployed application revision.

## Cause and repair

Production contained a valid, unused administrator invitation. The recipient
completed Google's redirect but The Godfather rejected admission without the
undistributed invitation token. The old UI returned that token once as JSON;
there was no email sender. Tailscale membership did not grant application access.

Normal first sign-in now consumes exactly one active invitation matching Google's
verified email, without a code. Existing invitations work without recreation.
Identity remains bound to Google `sub`; existing local accounts are never linked
by email. Expiry, revocation, single-use consumption, legacy-token compatibility,
sessions and RBAC remain enforced. Duplicate pending invitations are refused or
fail closed rather than selecting roles. Existing identities do not inherit roles
from pending invitations.

Administration explicitly states that email delivery is manual and provides
**Copy sign-in instructions** on active rows, including after refresh. Login
explains exact-email selection and hides optional legacy codes in a disclosure.
See [user onboarding](user-onboarding.md) and [ADR 0013](../decisions/0013-verified-email-invitation-activation.md).

## Executed validation

- Full PostgreSQL suite: **412 passed, 3 skipped**. The three skips require native
  worker Git/container facilities, exercised separately in the browser harness.
- Subsequently added concurrent invitation-consumption test: **1 passed**. A
  read-only test-image pytest-cache warning did not affect the result.
- Frontend component suite: **13 passed**. Ruff, strict mypy, Prettier, ESLint,
  TypeScript and the production Next.js build passed.
- Isolated browser acceptance passed using actual PostgreSQL, Windows worker,
  existing Ollama and Git/container coding. The second administrator signed in
  without a code; another invitee exercised legacy-token compatibility. Google's
  network alone was mocked inside that isolated harness.
- The actual release package passed image/provenance, migration, private proxy,
  paired backup/restore and restart/persistence checks.
- Production upgrade completed with all five services healthy, migration head
  `0009_provider_connections`, exact release metadata and unchanged production
  configuration, node-owner and worker-credential fingerprints. The worker
  reconnected. Backup checksums, dump listing and artifact integrity passed.
- Live browser checks passed for the no-code login copy, optional legacy field,
  anonymous invitation/control/provider denial and real Google callback/scopes/
  PKCE. HTTPS returned 200; direct API health stayed 404 and public worker
  registration stayed 403.

Private evidence remains in ignored `.cache/onboarding-fix` and the recorded
isolated test directories. No identity details or credentials are included here.
No DNS, Google Cloud, Tailscale policy, provider keys, paid inference or worker
installation changes were made. Pending invitation roles/expiry were preserved.

## Recipient acceptance

The original invitation remained active and unused at the initial post-deployment
check. The recipient retried through the normal Google sign-in flow, without an
invitation code. The user subsequently confirmed that sign-in worked ("All good").
This closes real recipient acceptance through user confirmation, separately from
the automated tests that mock Google's network. No recipient credentials or
private account details were collected.
