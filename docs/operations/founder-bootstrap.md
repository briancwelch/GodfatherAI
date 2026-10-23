# One-time founder setup using normal Google sign-in

This flow applies to source containing migration `0007_founder_bootstrap`.
Previously built rc.4 archives do not contain this change. No production settings,
Google Cloud client, database migration or deployment were applied by this task.

## Operator checklist

1. Use the normal Google **Web application** OAuth client with only `openid email
profile`. The exact planned production redirect URI is
   `https://app.the-godfather.ai/api/auth/callback`. The local redirect is
   `http://127.0.0.1:3000/api/auth/callback`. Use separate development and production
   clients. No JavaScript SDK or authorized JavaScript origins are needed by this
   server-side flow. The temporary OAuth Playground client and manual token helper
   are unnecessary for this bootstrap.
2. In private configuration, set `GODFATHER_GOOGLE_CLIENT_ID`,
   `GODFATHER_GOOGLE_CLIENT_SECRET`, and the matching `GODFATHER_WEB_ORIGIN`.
   Set `GODFATHER_GOOGLE_BOOTSTRAP_EMAIL` to the explicitly approved founder's
   exact Google email. Leave `GODFATHER_GOOGLE_BOOTSTRAP_SUBJECT` blank (or unset).
   Templates intentionally contain no personal email or credentials. Never commit
   private configuration or prefix secrets with `NEXT_PUBLIC_`.
3. At an authorized rollout, back up the existing database/artifacts and run the
   documented explicit migration command, `docker compose --profile tools run --rm
migrate` for development. For production, follow the separately authorized
   install/upgrade procedure in the [release guide](production-release.md), whose
   installer explicitly runs the migration before starting the application. Confirm
   head `0007_founder_bootstrap`. Do not reset volumes. The migration preserves
   users/resources and closes bootstrap if any administrator or Google identity
   already exists. Historical accounts require the explicit linking process in
   [Phase 09](../history/phases.md#phase-09), rather than a replacement founder.
4. Open the configured Command Center and choose **Continue with Google** without
   an invitation. Select the allowlisted account. Complete Google's ordinary
   browser authentication and consent. Do not copy tokens, secrets or browser
   authentication responses into chat or terminal commands.
5. Confirm **Account / Administration** identifies your linked account with the
   platform administrator role. Inspect the durable `security.administrator_bootstrapped`
   and `security.login` events through normal administration. The account
   is bound to Google's stable `sub` and bootstrap is permanently closed in the
   same transaction. A later login with that `sub` is ordinary login, even if its
   contact email changes. No token or subject extraction is needed.
6. Remove the email setting as optional configuration hygiene during an authorized
   configuration update. Keeping or changing it cannot rearm bootstrap. Normal
   logout revokes the current application session, without logging out of Google;
   existing absolute expiry, revoke-all and disable protections still apply.
7. Invite the second founder using their verified Google email and explicitly
   select **platform administrator** (the UI defaults to member). Privately deliver
   the one-time invitation token. They enter it in the login form and complete
   normal Google sign-in. Invitation expiry, revocation, single-use enforcement
   and email matching remain mandatory. Google test-user membership alone does
   not grant application access.

Google Audience must permit the intended personal accounts. If the project is in
Testing and Google requires test users, include both accounts. Follow the current
[Google OIDC setup reference](https://developers.google.com/identity/openid-connect/openid-connect)
for consent/publishing requirements; this task changes no Google settings.

## Admission and failure behavior

- Only the configured email with a valid, server-verified ID token and the boolean
  `email_verified=true` can create the initial administrator. A plain email form,
  unverified JWT payload, different account, alias or suffix domain grants nothing.
- Signature, issuer, audience, expiry, nonce, state, browser binding, PKCE, generic
  denial messages and rate limits remain in the existing OIDC path. Google tokens
  are never stored in browser storage, application sessions, audit records or Git.
- Denied attempts cannot consume the founder slot. A failed database transaction
  cannot consume it either. Concurrent verified sign-ins serialize: the same
  identity gets one account; a different identity cannot create a second founder.
- Closure is durable, not inferred solely from the current account count. Missing
  bootstrap state denies new onboarding. It is not a recovery or account-merge
  mechanism. Do not delete the singleton or downgrade the migration to rearm it.

The [architecture](../architecture/authentication.md) and
[ADR 0010](../decisions/0010-one-time-founder-bootstrap.md) describe the locking,
identity and migration boundaries. Real Google browser acceptance is a separate
operator check after OAuth configuration and authorized application startup.

## Local validation - 2026-10-20

- Disposable Linux PostgreSQL full regression: **322 passed**, including signed
  OIDC verification, unauthorized/unverified accounts, permanent closure, migration
  backfill, transaction rollback, and concurrent callbacks across API instances.
- Native Windows checks: **165 passed, 157 integration skips**; those database
  cases passed in the isolated PostgreSQL run. Ruff formatting/lint, strict mypy
  (85 source files), Prettier, ESLint, TypeScript, seven frontend tests and Next.js
  production build passed.
- Existing development `.env`, Compose configuration, dependency records, virtual
  environment configuration, healthy container IDs and application-data fingerprint
  were preserved. Migration tests used only disposable `godfather_test` databases;
  no migration was applied to the existing development database.
- Google responses were signed test fixtures exercised through real Authlib
  verification, not evidence of live Google authentication. No real account was
  bootstrapped, Google setting changed, production configuration applied, commit
  created, release rebuilt, push performed or deployment started.

The user has subsequently authorized a local review/commit and new rc.5 release.
See [first-deployment.md](first-deployment.md) for the current preparation boundary
and operator commands. The existing clean rc.4 release remains unchanged.
