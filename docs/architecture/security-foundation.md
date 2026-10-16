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

Authentication implementation remains deferred for these local metadata-only phases; this document establishes the boundary and prerequisites, not a claim that login exists.
