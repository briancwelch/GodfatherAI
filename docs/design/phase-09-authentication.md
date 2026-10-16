# Phase 09 authentication and administration

The login panel starts Google OIDC and optionally accepts a one-time invitation.
It explains invitation-only access and shows a generic denied state or an honest
unconfigured/unavailable error. There is no password or bearer-credential field.
The header displays `/auth/me` identity and roles, with logout and session revocation.
Operational routes render their existing authorized API state after authentication.

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
