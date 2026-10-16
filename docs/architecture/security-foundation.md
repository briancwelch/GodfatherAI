# Early security boundaries

## Phase 01

The dashboard serves static development content without accounts, sessions, credentials, private workspaces, or operational APIs. It explicitly says no backend or user session is connected. Its navigation does not authorize actions. Authentication is not simulated with a browser flag or a cosmetic login form.

Native Next.js commands bind to `127.0.0.1`. The container listens inside its namespace and Compose publishes only `127.0.0.1:3000`. PostgreSQL and Redis have no published ports and use an internal backend network. The dashboard is on a separate network and receives no database credentials. Redis has no durable responsibility and does not persist data.

`.env` is ignored by Git and excluded from container build context; only `.env.example` is committed. Set a unique local PostgreSQL password before starting. These development files are not a production secret-management system. Docker images use pinned version tags; digests and security scanning remain future hardening work. The dashboard runs as a non-root user with a read-only root filesystem.

## Phase 02 API boundary

The local API publishes only `127.0.0.1:8000` and exposes version/health/OpenAPI metadata. It has no private-domain read/write endpoints or user sessions. PostgreSQL remains internal, with explicit reviewed Alembic migrations. Readiness requires a current database schema. Configuration errors hide input values; request logs omit headers, raw paths, query values, SQL and raw exception strings. The service runs as uid 10001 with a read-only root filesystem, disabled proxy-header trust and no Uvicorn access log.

Ownership and role columns are schema foundations, not implemented permissions. No default founder accounts or worker credentials are seeded. The test database is separately named and guarded; migration downgrade/reset tests never target the application database or its volume.

## Before real data, remote access, or worker onboarding

Implement actual server-validated sessions and backend authorization, minimum API authentication, individually authenticated workers, invitation-based onboarding, and revocation before those capabilities are used. Keep secrets out of client bundles and logs. Tailscale connectivity never substitutes for authentication.

Both founders are equal platform administrators. Platform authority cannot grant host/filesystem/shell access on another owner's node. Node-owner consent, private workspaces, and scoped tool permissions remain independent boundaries.

Public deployment additionally requires TLS, rate limits, secret storage, audit logging, backup/restore verification and explicit authorization. Proposed public hostnames are not domain ownership or deployment readiness. Full RBAC is Phase 09; its later position does not permit unauthenticated earlier remote or real-data operations.

## Phase 03 minimum API and worker authentication

New node APIs require independently provisioned bearer credentials. Offline local provisioning uses existing database authority; there is no unauthenticated enrollment endpoint. PostgreSQL stores only digests of random 256-bit secrets. Worker identities are bound to owners and reserved UUIDs. Revocation, owner-enabled checks and server-validated administrator roles are enforced on every operation. Both founders can administer shared health, while no endpoint grants host paths, shell access, tool exposure or changes to owner contribution policies.

Administrator credentials are separate from worker credentials. Workers can register and heartbeat only their provisioned identity; they cannot inspect the node directory or call administration endpoints. Process session UUIDs reject duplicate live processes and stale heartbeat sessions. These are not execution attempt leases or scheduler fencing tokens.

Local wrappers capture one-time provisioning stdout into ignored files without printing tokens. Newly created POSIX files/directories use 0600/0700. Windows inherits directory ACLs, so owner-private directories are required. Request logs and validation errors omit payload values and credentials. Lifecycle events persist safe audit details in PostgreSQL. Workers initiate outbound requests only, disable proxy/redirect forwarding and require certificate-validated HTTPS beyond loopback. No home-network inbound ports, remote integrations or public services are configured.

This local minimum does not implement browser login, full workspace RBAC, remote invitations, rate limits, production secret storage or identity-preserving credential rotation. These remain prerequisites before real-data/remote/public exposure as applicable. See [ADR 0003](../decisions/0003-worker-identity-and-health.md) and [Phase 03 operations](../operations/phase-03.md).

## Phase 04 job boundary

Job submission/history require authenticated administrator credentials plus workspace ownership or explicit membership. Platform administration does not reveal private workspaces. Cancellation requires the job owner or workspace administrator. The node owner must have workspace access; cross-owner execution additionally requires explicit owner and workspace allowlists supplied by that node's individual credential, with a compatible non-dedicated policy. Health controls cannot grant execution consent. Contribution changes are audited and delivery/reports revalidate permissions.

Only opt-in simulated workers can execute the bounded synthetic handlers. Fenced reports verify identity, session, attempt, generation, active ownership, lease and deadline under PostgreSQL locks. Terminal/stale attempts cannot write results. No shell, filesystem path, arbitrary code, SQL, model, MCP or production side-effect payload is accepted. API and databases retain existing local network restrictions. Full browser sessions, contributor/member RBAC, rate limiting and production hardening remain later gates. See [ADR 0004](../decisions/0004-durable-synthetic-scheduler.md).
