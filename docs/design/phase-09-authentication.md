# Phase 09 authentication and administration

The login panel starts Google OIDC and optionally accepts a one-time invitation.
It explains invitation-only access and shows a generic denied state or an honest
unconfigured/unavailable error. There is no password or bearer-credential field.
The header displays `/auth/me` identity and roles, with logout and session revocation.
Operational routes render their existing authorized API state after authentication.

Protected background polling pauses across the page after any HTTP 401. The
application hides cached protected views and shows Google sign-in plus **Check
session**. Returning to a visible tab or focusing the window checks `/auth/me`
once for all waiting pollers; an explicit session check does the same. Polling
resumes only after successful verification. A different account triggers a clean
reload so it cannot inherit the previous account's cached views. A workspace 403
remains a scoped permission failure rather than expiring the whole session.

Healthy identity checks run on mount, focus or explicit refresh, without a
recurring identity timer. Other protected polls retain their normal intervals;
transient failures double the delay up to 60 seconds and success resets it.
Hidden tabs pause requests. Polls do not overlap, and effect cleanup removes
timers/listeners, aborts in-flight requests and ignores late responses. Session
checks and protected polling have bounded request timeouts. These browser controls
do not replace backend session, Origin, workspace or node-owner authorization,
and recovery never replays a mutation, job submission or paid operation.

`npm test` includes Node fake-timer regressions for polling and cancellation.
After a local dashboard build, `node tests/e2e/authentication-polling.cjs` exercises
the real UI with intercepted fixture responses and a browser clock. It requires
the existing Playwright tooling; it does not perform real Google sign-in.

Administration is a separate navigation destination. Its hierarchy is account,
workspaces and membership, owned node onboarding, then platform users/invitations
and security audit. Platform controls depend on backend-provided permissions.
Workspace management depends independently on ownership/membership; platform
administration does not confer private workspace rights or node controls.

Components reuse existing panels, semantic tables, labeled inputs, buttons and
confirmation dialogs. All requests expose loading, empty, forbidden, unavailable
and confirmed-success states. Secrets appear only on the initiating response,
with explicit copy/delivery instructions, and never in inventories. Tables scroll
within their container on narrow screens. Keyboard focus and visible labels remain.

API dependencies: `/auth/me`, `/auth/start`, `/auth/callback`, `/auth/logout`,
`/auth/sessions/revoke` and `/administration/*`, over the same-origin bridge.
Acceptance checks cover login denial, real identity rendering, expired sessions,
permission-aware administration, independent workspace ownership, node owner
controls, one-time invitation output, and persisted audit refresh.
