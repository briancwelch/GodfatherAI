# ADR 0008: Google-only human identity with independent owner authorization

Status: accepted for authorized Phase 09 implementation; real Google login
acceptance pending operator OAuth configuration. No deployment authorization.

Use maintained Authlib Google OIDC Authorization Code Flow with PKCE S256 and
server-side, one-time, browser-bound state/nonce transactions. Google authenticates
humans by stable sub; PostgreSQL owns application identities, invitations, revocable
opaque sessions, multi-role permissions and security events. Keep the existing
Next.js same-origin backend bridge, now forwarding application sessions rather
than legacy human bearer credentials. Secure cookies and strict Origin checks
protect browser operations. There is no password subsystem or identity platform.

Preserve user UUIDs through explicit offline Google identity linking; never link
legacy accounts by email. Invitations and explicit first-identity bootstrap control
admission. Platform roles, workspace membership and node-owner consent are separate
authorization boundaries. Worker machine credentials, outbound connectivity,
attempt leases, fencing and portable checkpoints remain unchanged in purpose.
Workspace model/tool restrictions are checked by the existing scheduler/report
paths; no parallel orchestration or policy service is introduced.

Consequences: Google availability and operator client configuration are required
for new human login. Existing valid application sessions remain independently
revocable. Invitation delivery and offline break-glass procedures need trusted
operators. Test-only signed OIDC fixtures remain isolated in godfather_test.
Legacy bearer/simulator smoke scripts cannot populate normal operational views.
Production TLS/networking, audited backups, real Google acceptance, cloud billing
and deployment retain their separate gates.
