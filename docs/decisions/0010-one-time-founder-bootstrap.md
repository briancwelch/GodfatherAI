# ADR 0010: Verified Google email allowlist for one-time founder bootstrap

Status: accepted for local implementation; rollout and production configuration
remain separately authorized.

The first administrator should use ordinary Google sign-in without extracting an
ID token or running a verification script. Configure one exact founder email in
private environment configuration. Authlib continues to verify the Google OIDC
response, including signature, issuer, audience, expiration and nonce, after the
existing browser-bound state and PKCE exchange. Admission additionally requires
the boolean `email_verified=true` and a case-insensitive exact email match. Do not
normalize aliases or Gmail dots. Persist Google's stable `sub` as the identity;
future login never uses email to locate or link an account.

An optional legacy subject pin remains supported as an additional restriction.
Blank email disables bootstrap. No configured identity is seeded at startup.
Existing accounts with the same email require explicit linking rather than
automatic takeover. Administrators, including disabled or multi-role accounts,
and any linked Google identity prohibit initial bootstrap.

Migration `0007_founder_bootstrap` creates one durable bootstrap row, already
closed for existing installations with administrators or Google identities.
On a fresh installation, the existing transaction advisory lock and a row lock
serialize verified callbacks. Account, subject, session, audit events and permanent
closure commit atomically. Failure rolls back all of them. Closure survives process
restarts, email-setting changes and account disabling. Missing state fails closed.
There is no HTTP reset or rearm operation; bootstrap is not account recovery.

Additional users require normal invitations; a second administrator is invited
with the existing `platform_admin` role. Sessions, rate limiting, RBAC, workspace
isolation, worker credentials and node-owner restrictions retain their existing
behavior. Operators may remove the bootstrap email after success, but security
does not depend on removing it. Existing UUIDs and application data are preserved.

This supersedes the manual founder-subject acquisition requirement in earlier
configuration packs. It does not change the explicit linking/recovery procedures
for historical accounts. Real Google acceptance and deployment remain pending.
