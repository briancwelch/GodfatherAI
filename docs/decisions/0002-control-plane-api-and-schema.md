# ADR 0002: Control-plane API and initial schema

- Status: Accepted within authorized Phase 02
- Date: 2026-10-15

## Decision

Use one FastAPI application factory and synchronous SQLAlchemy 2 with psycopg 3 binary wheels. Synchronous endpoints run database probes in FastAPI's thread pool. A small bounded pool, connection timeout, statement timeout and UTC session timezone keep behavior explicit. No async database abstraction is needed yet.

Pydantic Settings validates `GODFATHER_` environment variables at application creation. Database passwords are required secret values, never defaults or client configuration. Database URLs are built with SQLAlchemy URL objects so passwords containing punctuation are escaped safely. Only `local` and `test` environments are currently accepted; this is not production exposure authorization.

Alembic owns schema changes. Migrations are an explicit command, not an API startup side effect. The first revision contains fixed DDL independent of future ORM edits. Readiness checks database connectivity and exact revision-head agreement; liveness does not access PostgreSQL. Redis is not an API dependency in this phase and remains transient.

The initial schema comprises users, workspaces/memberships, owned nodes, capabilities/node specialties, portable model definitions/node deployments, versioned portable agents, jobs, attempts, checkpoint references and events. UUID primary keys and timezone-aware timestamps are used. PostgreSQL constraints reject invalid states, nonpositive limits/tokens, duplicate attempt numbers/fencing tokens, duplicate checkpoint versions and cross-workspace job/agent or event/job references. Checkpoints must reference an attempt for the same job.

Schema fields reserve durable information needed by later phases; they do not implement state transitions, authentication, worker registration, claims, leases, fencing enforcement, scheduling, checkpoints or execution. No default users, administrator accounts, runtime credentials, or real data are seeded. JSON fields hold portable definitions/requirements/references; they must not contain secrets. Detailed execution contract validation belongs to the phase introducing those operations.

Use standard-library JSON logging with allowlisted request fields, bounded validated correlation IDs, and generic error responses. Do not log query strings, arbitrary paths, headers, SQL, parameters or exception messages. Uvicorn access logging and proxy-header trust are disabled. Full authentication/authorization and public deployment controls are still mandatory before remote access or real data.

## Tests and packaging

Use a non-root Python container with separate runtime and development targets. Runtime and migration services use the same source/dependency baseline. The API publishes only loopback port 8000; PostgreSQL/Redis remain internal. Compose profiles expose explicit migration and test tools without a background scheduler or worker.

The API joins both the application network and the internal backend network. The application network is needed for Docker to publish its loopback HTTP port; an internal-only service did not publish a usable Windows host port during verification. PostgreSQL and Redis join only the internal network, with no host port mappings.

Database-free tests run on all supported OS CI runners. Real PostgreSQL integration runs in a separate `godfather_test` database only when environment=test and the explicit integration flag is set. The test suite applies/reverses migrations only there, uses synthetic records, and never deletes the local application volume. A portable host-side smoke probe verifies actual API and PostgreSQL process restarts, database outage health responses and recovery using a temporary test-created table.

New dependencies are limited to the mandated FastAPI/SQLAlchemy/Alembic/Pydantic stack, pydantic-settings, the PostgreSQL driver, Uvicorn, and the current Starlette-supported `httpx2` test client. Full API sessions, RBAC, registration, workers and domain write routes are deferred.
