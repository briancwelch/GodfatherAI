# Phase 09: Google authentication setup, migration and verification

Scope: human Google OIDC, revocable application sessions, multi-role administration,
invitation-only onboarding, workspace isolation, independent node ownership and
durable auditing. Phase 10, external deployment, paid frontier integration and
production system changes are not authorized. See [authentication architecture](../architecture/authentication.md)
and [ADR 0008](../decisions/0008-google-oidc-and-owner-authorization.md).

## Google Cloud setup — operator action, not performed by Codex

Use a Google Cloud project controlled by the platform operators. In Google Auth
Platform configure Branding, Audience and Clients. Create an OAuth client of type
**Web application**. Request only `openid`, `email`, `profile`; Gmail/Drive APIs and
Google access/refresh-token storage are unnecessary. During Google's testing mode,
add the invited accounts as Google test users if required by the project's audience.
Google test-user approval does not bypass Godfather invitations.

Prefer separate OAuth clients for development and production. Register exact redirect
URIs, with no trailing slash:

| Environment               | Application origin             | Authorized redirect URI                          |
| ------------------------- | ------------------------------ | ------------------------------------------------ |
| Windows/macOS/Linux local | `http://127.0.0.1:3000`        | `http://127.0.0.1:3000/api/auth/callback`        |
| Optional localhost local  | `http://localhost:3000`        | `http://localhost:3000/api/auth/callback`        |
| Planned production        | `https://app.the-godfather.ai` | `https://app.the-godfather.ai/api/auth/callback` |

Use one exact origin consistently in browser, API and dashboard configuration;
localhost and 127.0.0.1 have different cookies. The callback is on the dashboard,
not `api.the-godfather.ai`. Do not use wildcard redirects. This server flow does
not require a Google JavaScript SDK or additional Google API permissions. Consult
[Google's current setup and OIDC reference](https://developers.google.com/identity/openid-connect/openid-connect).
Production names remain proposed; this document does not verify registration,
DNS, domain ownership, TLS or hosting readiness.

## Configuration

Set the following only in ignored local environment configuration or a secure
deployment secret store. Never paste the client secret into chat, logs or Git.

| Variable                             | Meaning                                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `GODFATHER_GOOGLE_CLIENT_ID`         | Google Web client ID; API only                                                                          |
| `GODFATHER_GOOGLE_CLIENT_SECRET`     | Google Web client secret; API only                                                                      |
| `GODFATHER_WEB_ORIGIN`               | Exact application origin; API and dashboard                                                             |
| `GODFATHER_API_URL`                  | Dashboard server's backend address; defaults to `http://127.0.0.1:8000`, Compose uses `http://api:8000` |
| `GODFATHER_GOOGLE_BOOTSTRAP_SUBJECT` | Explicitly verified stable Google sub for first administrator                                           |
| `GODFATHER_GOOGLE_BOOTSTRAP_EMAIL`   | Matching verified Google email for first administrator                                                  |
| `GODFATHER_SESSION_SECONDS`          | API session lifetime, 300–86400 seconds; default 28800                                                  |
| `GODFATHER_AUTHENTICATION_LIMIT`     | API auth start/callback requests per direct peer/action/minute; default 20                              |
| `GODFATHER_ENVIRONMENT`              | `local`, `test`, or `production` for API configuration                                                  |

Compose forwards the Google and web-origin configuration from the ignored root
`.env`. Optional session/rate settings can be supplied explicitly in the API
environment. Native Next.js reads its process environment or ignored
`apps/dashboard/.env.local`; it does not automatically read the repository root
`.env`. Never prefix OAuth secrets with `NEXT_PUBLIC_`. The dashboard receives no
Google client secret. Missing client configuration produces an honest unavailable
login state and grants no access.

For production configuration, use the separate production client, planned HTTPS
origin, `GODFATHER_ENVIRONMENT=production` and a private backend URL or the reviewed
HTTPS API address. Startup rejects missing Google configuration, nonproduction
web origins and legacy-test credential mode. Secure cookies are derived from the
exact HTTPS origin. Production TLS, private networking, secret rotation, proxy
trust and deployment remain separately authorized Phase 10 work. Existing Compose
continues publishing only loopback API/UI ports and no database/inference ports.

## Bootstrap and ownership-preserving migration

Obtain the founding administrator's `sub` from a Google-issued ID token verified
with a maintained Google/OIDC library for the intended OAuth client. Do not copy
an unverified JWT payload, trust an email address alone, or publish that token.
The configured subject is an allowlisted identity, not a password. First login
still independently verifies Google's signature, issuer, audience, expiry, nonce,
PKCE exchange and verified email.

On a fresh database, set both bootstrap identity variables, apply the migration,
start locally and choose **Continue with Google**. The matching identity creates
the first administrator once. Remove bootstrap settings after successful setup.
No account is automatically created at startup, and no hardcoded founder exists.

Existing Phase 03–08 users keep their UUIDs and owned resources. If any legacy
administrator exists, bootstrap intentionally refuses to create an unrelated
replacement administrator. With local database authority, identify the existing
real user's UUID from your private records and bind its verified Google subject:

```text
docker compose exec -T api python -m godfather_api.identity link --user-id EXISTING_USER_UUID --subject VERIFIED_GOOGLE_SUB
```

Run only after backing up the database/artifact volume with the existing authorized
backup procedure. The command never matches/merges accounts by email and never
copies node data. It preserves UUIDs, roles, nodes, workspaces, jobs and audit
history, revokes legacy human credentials/sessions, and leaves machine credentials
independent. Existing subject replacement requires `--replace` and fresh operator
identity verification. Successful Google login updates profile/contact data.
Email uniqueness conflicts fail closed; resolve them with reviewed database
administration rather than silently merging identities. Synthetic historical
accounts should remain unlinked and are not usable human login accounts.

After migration, run:

```text
uv sync --locked --all-packages
npm ci
docker compose --profile tools build api migrate dashboard
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Migrations are explicit; never reset application volumes. The head is
`0006_google_identity`. For native frontend development, use the same documented
origin and API URL and avoid running two dashboards on port 3000.

## Invitations, administration and recovery

In **Account / Administration**, create an invitation for the second founder's
Google email with role **platform administrator**. Deliver the one-time invitation
token privately. They enter it in the first-login form and authenticate with their
own Google account. Both receive identical platform privileges. Future invitations
can grant multiple contributor/member/administrator roles without account-count
or location limits. Invitations expire in 1–168 hours and can be revoked. Only
token digests appear in the database; lists/audit never return the original token.

Workspace owners create private workspaces and explicitly add member/admin UUIDs.
They grant exact installed model identifiers and supported `name@version` tools in
the execution policy; empty lists deny use. Legacy NULL policies preserve the prior
local read-only authorization, and owners should review/configure explicit lists.
Agent selection still requires an existing registered agent and compatible worker.
Shared platform administration never grants private workspace access.

Node owners create an independent worker credential in the same screen. Save its
one-time response in an owner-private file, adding `"kind": "worker"` for the
existing worker CLI. Configure allowed tools, model configuration, owner/workspace
allowlists, scheduling policy and resource capacity on that owner's worker using
the [existing worker contract](phase-03.md). Revocation and drain/disable controls
are on node detail. Another administrator cannot enable, revoke or change that
node's contribution. Roles cannot grant another owner's host/filesystem access.
The owned credential inventory also supports revocation before a worker has ever
registered. Existing workers retain their machine tokens, but normal reconnect
requires their owner to complete explicit Google identity linking first.

For normal account recovery, the user recovers their Google account through Google;
there is no application password/reset token. A second platform administrator can
reenable an account, restore appropriate roles and revoke its sessions. If all
administrators are locked out, local database authority can run:

```text
docker compose exec -T api python -m godfather_api.identity recover --user-id EXISTING_USER_UUID
```

This reenables that existing account, revokes sessions and audits the offline
operation. It does not silently promote a member. At least one enabled platform
administrator must remain; ordinary HTTP operations cannot remove the last one.
If a Google identity changes, use the explicitly reviewed `identity link --replace`
procedure, preserving the same application UUID and ownership records.

## Automated validation and real Google acceptance

Run tests serially because disposable PostgreSQL suites exercise migrations/resets:

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose --profile tools build api-test
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_google_oidc --model EXACT_INSTALLED_MODEL
```

The OIDC integration tests mock only Google HTTP responses and sign fixture ID
tokens with the maintained JOSE library, so Authlib verification actually runs.
Negative cases cover signature/issuer/audience/expiry/nonce, state/browser binding,
PKCE verifier, invitation denial/expiry/revocation/reuse, independent roles,
workspace isolation, worker impersonation/revocation, session revocation and CSRF.

The browser harness resets **only** guarded `godfather_test`, starts an owned test
API container on loopback 8009 and Next.js on loopback 3010, intercepts Google
authorization only inside Playwright, and runs a real physical Windows worker
against an already-installed loopback Ollama model. It does not download models,
install browsers or alter the application database. Logs/screenshots/evidence are
under ignored `.cache/phase09-runs/UUID/`. It stops only its own processes/container.
These are automated-test identities, never seeded into the normal Command Center.
Historical Phase 03–08 live-database bearer/simulator smoke scripts are superseded;
normal admin credential provisioning and simulated-worker registration are refused.

**Real Google login acceptance is pending**: no Google OAuth client is configured.
After operator setup, perform the user's full acceptance in the normal local stack:
bootstrap/link the first verified Google administrator; invite and independently
log in the second administrator; onboard an actual owned worker; submit a real
workflow and inspect PostgreSQL-backed result/checkpoints/artifacts; explicitly
share its workspace with the second administrator; prove a separate private
workspace remains inaccessible; prove node-owner grants prevent unauthorized
execution; invite a contributor and verify platform operations are forbidden;
revoke the worker credential and confirm registration returns 401; inspect real
audit history; verify logout/revoke-all/account-disable and an uninvited Google
account denial. Inspect cookies for HttpOnly/SameSite/Secure as applicable and
confirm no Google tokens exist in browser storage. Capture sanitized evidence.
If a worker/model is unavailable, record the affected steps incomplete.

See [real integration verification](phase-09-integration.md) for executed results,
remaining limitations and the operational feature/API/persistence map. No Phase 10
work or external Google Cloud configuration is part of this implementation.
