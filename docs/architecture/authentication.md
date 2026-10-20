# Phase 09: Google OIDC and independent resource authorization

Human authentication uses Google OAuth Authorization Code Flow with OIDC. Password
authentication was never implemented and is not added. Authlib 1.9.1 (locked with
its maintained JOSE/cryptography dependencies) owns authorization URL construction,
PKCE S256, code exchange and ID-token verification. Its existing HTTPX2 adapter
reuses the project's HTTP client. No OAuth/JWT cryptography is implemented here.
References: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)
and [Authlib web clients](https://docs.authlib.org/en/latest/oauth2/client/web/).

Only `openid email profile` are requested. Google access/ID tokens exist transiently
in the callback process; no refresh token, offline scope, Google API access, token
database, browser token storage, Gmail or Drive integration is introduced.

## Login and sessions

1. A same-origin form POST starts login, optionally supplying an invitation token.
2. PostgreSQL stores a ten-minute login transaction: hashed state, hashed random
   browser binding, nonce, PKCE verifier and optional invitation UUID. The binding
   cookie is HttpOnly, SameSite=Lax for Google's top-level callback, host-only and
   Secure when the configured origin uses HTTPS. The verifier stays server-side.
3. The callback matches state and browser binding under a row lock, checks expiry,
   commits single-use consumption and clears nonce/verifier before provider I/O.
   Authlib additionally validates returned state during code exchange and validates
   the signed ID token against Google JWKS, issuer, audience, lifetime and nonce.
   Only Google's fixed discovery endpoint is configured. Provider HTTP requests
   disable environment proxies and redirects, use TLS verification and timeouts.
4. The account is looked up by the unique Google `sub` in `google_identities`.
   Email is verified contact/display data, never the identity lookup key. Name,
   email and an optional HTTPS profile-picture reference update on successful login.
   Pictures are not fetched by the coordinator or automatically rendered remotely.
5. A fresh random 256-bit opaque application session is issued. PostgreSQL stores
   its SHA-256 digest, user UUID, expiry and revocation status. The host-only
   `godfather_session` cookie is HttpOnly, SameSite=Strict, Secure for HTTPS, and
   lasts at most the configured absolute session duration (default eight hours).

No user-controlled return URL is accepted: callback and final application redirect
are derived exclusively from an exact configured web origin. All application
mutations require the exact Origin. Next.js also validates Host, allowlists backend
operations and forwards the opaque application session server-side. It never
forwards Google tokens. Both application and login cookies use Path=/ and no Domain.
Logout revokes the current server session; revoke-all invalidates every session.
Every request checks account enabled state, session expiry and revocation. Role or
account-state changes revoke the user's sessions. Logout does not sign out Google.

Authentication start and callback are limited using atomic PostgreSQL counters per
direct peer/action/minute, consistently across API processes. A server-side bridge
shares that conservative aggregate limit (default 20/minute). Forwarded client-IP
headers are not trusted. Authentication denial messages are generic. No passwords,
Google tokens, OAuth codes, invitation secrets or session values enter audit data.
Protected API responses and the dashboard bridge use `Cache-Control: no-store`.

## Invitations and existing identities

A valid Google account alone grants nothing. Administrators create an email-bound,
time-limited invitation containing initial roles. A random token is returned once;
only its digest is stored. Administrators deliver it through an approved private
channel; this phase sends no messages automatically. Activation requires a verified
Google email matching the invitation, consumes it under a database lock and binds
the new UUID to `sub`. Expired/revoked/used invitations cannot activate another user.
An invitation never changes the roles of an existing linked account.

First-administrator bootstrap requires one explicitly allowlisted Google email.
The ordinary server-side OIDC callback must first verify the signed ID token and
require the boolean claim `email_verified=true`; its email must match the allowlist
case-insensitively, without alias or Gmail dot normalization. Google `sub` becomes
the durable identity. A preconfigured subject is optional as a legacy additional
pin; no manual token extraction is needed. Bootstrap requires no Google identities
or administrators (including disabled and multi-role accounts). A transaction
advisory lock and singleton row lock serialize admission. The same transaction
creates the account, identity, session and audit events and permanently closes
bootstrap. Rollback leaves it unused. Later users require invitations, even if the
email setting changes. There are no default accounts or first-visitor admission.

The additive `0007_founder_bootstrap` migration seeds the durable singleton closed
for installations with existing Google identities or administrators. Missing state
fails closed; changing configuration cannot reopen it. This mechanism is not an
account-recovery tool. See the [founder setup guide](../operations/founder-bootstrap.md)
and [ADR 0010](../decisions/0010-one-time-founder-bootstrap.md).

The additive `0006_google_identity` migration preserves all existing user UUIDs,
workspace membership, node ownership, jobs and events. Legacy accounts are never
automatically linked by matching email. The offline identity CLI requires local
database authority and an explicit verified subject/UUID mapping. It revokes legacy
human bearer credentials and application sessions while preserving machine tokens.
Legacy human bearer login and admin provisioning work only in explicitly enabled,
isolated `environment=test` regressions; they are refused in normal operation.
See the [operations guide](../operations/phase-09.md) for migration and recovery.

## Role and ownership model

| Platform roles         | Application permission set                                                                                      |
| ---------------------- | --------------------------------------------------------------------------------------------------------------- |
| Platform administrator | Platform user/invitation/audit administration, cluster health, own contributions, permitted jobs and workspaces |
| Contributor            | Own node onboarding/contributions, permitted jobs/workspaces                                                    |
| Member                 | Permitted jobs/workspaces and own account/session settings                                                      |

Users can hold multiple roles; permissions are the union of the role sets. Existing
single-role records remain compatible. New permission kinds can extend the central
mapping without changing account-count assumptions. Only platform administrators
change platform roles. Serialized checks prevent removing/disabling the last enabled
administrator. A second founding administrator is an ordinary invitation with the
same `platform_admin` role; there is no founder-specific code path.

Workspace authorization is independent: owner or explicit membership is required
for lists, jobs, agents, model directory/metrics, attempts, streams, history,
checkpoints and artifact reads. Job mutations require the job owner or workspace
administrator. Agent management and membership/policy changes require workspace
administration. Inaccessible UUIDs return 404, including direct artifact endpoints.
Membership removal and account disabling also invalidate execution eligibility.

New workspaces default to empty model/tool allowlists. Workspace administrators
explicitly grant exact model identifiers and `name@version` read-only tools. The
scheduler and fenced report paths check these policies; capability-only model
selection cannot bypass an exact allowlist. Existing workspaces retain their prior
local read-only grants (NULL policy) until their owners configure explicit lists.
Workspace lists do not globally reveal private assets to platform administrators.

Node credentials remain independent random machine secrets, hashed centrally and
bound server-side to one owner/reserved identity. Registration payloads cannot set
ownership. Contributor and administrator onboarding always creates an owned
credential, never an arbitrary other-user credential. Only the node owner may
drain, disable, enable or revoke it. Worker-local contribution limits, sharing
allowlists, model availability and tool grants remain mandatory. Platform authority
cannot expand them. Revocation/owner disabling prevents reconnect, polling and
fenced writes. Existing lease/attempt/session/fencing checks are preserved.

Platform administrators see cluster health; other users see only owned node health.
Operational views exclude simulated nodes and synthetic job submission in normal
operation. Test fixtures remain in disposable `godfather_test`; no test identity is
seeded in the application database. User administration lists linked identities,
with historical unlinked accounts handled through explicit offline migration.
Worker owners also require an explicitly linked Google identity before their
existing machine credentials can reconnect in normal operation. Test-mode
authentication refuses any database name other than `godfather_test`. Global node
health and audit projections redact inaccessible private workspace grant UUIDs.
Owned machine credentials can be revoked before the worker's first registration.

## Audit and BYOK boundary

Existing immutable-through-HTTP event history records node, agent, job and workflow
actions. New security events record login failure/success, logout, rate limiting,
session revocation, invitations/activation, user changes, workspace permissions and
policies, machine credential creation and offline identity/recovery operations.
Events persist actor (NULL for unauthenticated or offline database authority), action,
target UUID, timestamp, outcome and request correlation ID where applicable. Offline
operations are explicitly named; no HTTP audit edit/delete endpoint exists. Security
audit visibility excludes inaccessible workspace-scoped events even for administrators.
Database operators remain trusted and can alter database history; tamper-evident
external retention is not claimed.

Worker execution takes PostgreSQL `FOR NO KEY UPDATE` node locks: mutations remain
serialized, while cancellation audit inserts can acquire their foreign-key
`KEY SHARE` checks without a node/job lock cycle. Node identity keys are immutable
on this path; job/attempt/lease/fencing validation is unchanged. A deterministic
concurrency regression pauses a worker while it holds the node and proves that
cancellation and its durable event can commit before that worker continues.

Google login does not authorize provider billing. The [BYOK plan](byok-plan.md)
remains planning-only. Its authorization contract is owner UUID + opaque provider
connection ID + private/approval-required/budget-limited policy + permitted user,
workspace, model, payer and usage attribution. A paid invocation will require an
owner-authorized grant covering billable use and data egress; budgets are safeguards,
not guaranteed billing caps. Keys remain worker-local. No key upload/sharing,
provider billing, cost ledger, paid fallback or sensitive-tool approval execution is
implemented. Unsupported operations stay unavailable; local failure never enables
paid inference. Node tool grants continue to protect the existing read-only runtime.

## Remaining public-deployment limits

No Google Cloud project/client, account, VPS, DNS or TLS configuration was changed.
Real Google acceptance remains pending operator setup. Before public exposure,
separately validate TLS/proxy topology, production environment/redirect matching,
secret-store operations and rotation, trusted network policy, distributed rate-limit
capacity, database/artifact backup and restore, dependency/security review, audit
retention and account/worker offboarding. Invitation delivery remains manual. No
new authentication service, Firebase, Auth0, Kubernetes or unrestricted execution
was introduced. Physical macOS/Linux execution still requires those environments.
