# Phase 02: Control-plane API

## Scope and prerequisite gate

Phase 01 was committed/pushed as `9176cb00184e91b3e3df737c62285a862ef3feb7`. All eight jobs in [the Phase 01 CI run](https://github.com/briancwelch/GodfatherAI/actions/runs/38831542451) passed: Python across Windows/macOS/Linux plus Linux Python 3.12, frontend on all three OS runners, and Linux container startup/persistence. A fresh private-repository clone restored both lockfiles and passed all checks locally before Phase 02 code changes.

The local startup/health checks passed. A committed PostgreSQL probe survived container recreation. Redis's temporary probe was lost on recreation and Redis returned `PONG`, matching its deliberately non-durable policy. There is no Redis persistence requirement: PostgreSQL is the sole durable state authority under AGENTS.md.

Phase 02 adds the API foundation and schema only. No job submission, claims, scheduling, worker registration, heartbeat processing, inference, domain CRUD, or dashboard management is implemented. One developer builds the platform for two administrators.

## Start locally (all supported development OSes)

Prepare the ignored `.env` as in the setup guide. Then:

```text
uv sync --locked --all-packages
npm ci
docker compose --profile tools build dashboard api migrate
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait
```

Run the explicit migration step before starting the full stack for the first time or after adding a migration. Startup does not create tables or change the schema. Without a current schema, readiness returns 503 and Compose does not mark the API healthy. Health checks use real state.

| Local URL                                   | Contract                                                                                               |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `http://localhost:3000`                     | Existing disconnected dashboard shell                                                                  |
| `http://localhost:8000/api/v1`              | Service identifier and API contract version                                                            |
| `http://localhost:8000/health/live`         | 200 with `status=alive`, independent of the database                                                   |
| `http://localhost:8000/health/ready`        | 200 with `status=ready` only with reachable, current PostgreSQL; otherwise 503 with `status=not_ready` |
| `http://localhost:8000/api/v1/openapi.json` | Versioned machine-readable schema; interactive docs disabled                                           |

Every HTTP response carries `X-Correlation-ID`. A single valid ASCII ID of at most 64 characters is preserved; invalid, duplicate or absent values receive a new UUID-derived ID. Logs use UTC JSON records and route templates. Unknown paths are logged as `unmatched`. Request headers, query values, SQL and raw exception strings are omitted. Health error responses do not reveal database details.

No user authentication is implemented because these routes expose only local foundation/health metadata, not private domain records or operations. Do not expose the API or shell remotely or use real private data. Owner columns and role fields are schema foundations, not implemented RBAC.

## Configuration

Compose maps `POSTGRES_PASSWORD` from ignored `.env` to `GODFATHER_DATABASE_PASSWORD`. The dashboard never receives it. API/migration settings:

| Variable                             | Default / validation                               |
| ------------------------------------ | -------------------------------------------------- |
| `GODFATHER_ENVIRONMENT`              | `local`; accepts `local` or `test`                 |
| `GODFATHER_DATABASE_HOST`            | `postgres`; nonempty                               |
| `GODFATHER_DATABASE_PORT`            | 5432; 1–65535                                      |
| `GODFATHER_DATABASE_NAME`            | `godfather`; a safe identifier up to 63 characters |
| `GODFATHER_DATABASE_USER`            | `godfather`; nonempty                              |
| `GODFATHER_DATABASE_PASSWORD`        | Required, nonblank SecretStr                       |
| `GODFATHER_DATABASE_TIMEOUT_SECONDS` | 3; 1–30, used for connection/pool/statement bounds |
| `GODFATHER_LOG_LEVEL`                | INFO; DEBUG/INFO/WARNING/ERROR                     |

Native Python unit tests need no environment secrets or database. Native API development requires explicitly exported settings and an authorized reachable PostgreSQL endpoint; no database port is published by default. Prefer the container workflow. Do not set a global connection URL or print resolved Compose configuration containing passwords.

## Migrations and tests

The initial revision is `0001_initial`. Never edit a revision after publication/application; subsequent changes need a new migration. Use `python -m alembic -c infrastructure/migrations/alembic.ini ...` from the root or the `migrate` Compose service. Schema downgrade deletes tables and requires explicit review outside the guarded disposable test environment. No automatic production rollback is provided.

Run ordinary checks on Windows/macOS/Linux:

```text
uv run --locked --all-packages python scripts/dev.py check
```

Without the integration flag, database tests report skips; that is not evidence of database validation. Run the real database suite explicitly:

```text
docker compose --profile tools build api-test
docker compose exec -T postgres createdb -U godfather godfather_test
docker compose --profile tools run --rm api-test
uv run --locked --all-packages python -m scripts.check_api_restart
```

Create `godfather_test` only once; if it already exists, omit the `createdb` command. This database is explicitly disposable: the suite applies downgrade/base/upgrade cycles and resets its synthetic records between tests. Its guard requires `GODFATHER_ENVIRONMENT=test`, database name exactly `godfather_test`, and `GODFATHER_RUN_INTEGRATION=1`. Never point it at application or production data. Tests must run serially against this database.

The restart probe is restricted to the `godfather-local` development project. It creates a unique scratch table, restarts the API and PostgreSQL, confirms its committed value, stops PostgreSQL to check liveness=200/readiness=503, restores PostgreSQL and readiness, and drops only its own scratch table. It intentionally interrupts this local database while it runs; do not run it with real work in progress. It contains no sleep-based polling; Compose health checks provide bounded readiness waiting.

## Validation results

Validated on Windows x64 with Docker Desktop's WSL2 Linux amd64 engine, Python 3.14.8 and PostgreSQL 17.11 on 2026-10-15.

| Check                                 | Actual result                                                                                                                                                        |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 01 prerequisite gate            | Passed locally, in a fresh clone, and in all eight GitHub CI jobs before API implementation                                                                          |
| Ruff formatting/lint and strict mypy  | Passed; 15 Python source files type checked                                                                                                                          |
| Windows database-free tests           | 27 passed                                                                                                                                                            |
| Real PostgreSQL Linux-container suite | 44 passed; includes 17 integration cases with no database skips                                                                                                      |
| Migration round trip                  | Upgrade/base downgrade/upgrade passed on the guarded disposable database                                                                                             |
| Migration metadata check              | `alembic check` found no pending upgrade operations; head matched                                                                                                    |
| Referential/default/constraint checks | Passed for ownership, private/member defaults, workspace references, checkpoint/attempt job references, states, limits, duplicate attempt numbers and fencing tokens |
| API container build/start             | Passed with non-root uid 10001 and read-only root filesystem                                                                                                         |
| Real API and PostgreSQL restarts      | Passed; committed temporary probe survived both process restarts                                                                                                     |
| Database outage and recovery          | Live=200 and ready=503 with PostgreSQL stopped; ready=200 after restoration without API restart                                                                      |
| HTTP/correlation smoke                | `/api/v1` returns 200 and preserves `phase02-live-smoke` in the response correlation header                                                                          |
| Runtime request/startup logs          | Observed JSON records with UTC timestamps; tests confirm omission of secrets, SQL, query values and raw exception strings                                            |
| Network isolation                     | API bound to `127.0.0.1:8000`, shell to `127.0.0.1:3000`; no PostgreSQL/Redis host bindings                                                                          |

The first host-side restart probe found that an API attached only to the internal backend network did not publish a usable host port. Joining the application network corrected that; the full probe then passed. The scratch table from each run was removed, and the database volume was preserved. Integration tests remain isolated in `godfather_test`.

The complete repository check runner passed on Windows: Python formatting/lint/typing, 27 database-free tests (17 database cases deliberately skipped there and separately passed in the container), frontend formatting/lint/typing and production build. `uv pip check`, `npm audit --audit-level=high`, Compose validation and patch whitespace checks passed. The application database contains 13 domain tables plus the Alembic version table at `0001_initial`, with no leftover restart probe tables. The API runtime image contains no local `.env` file.

Phase 02 GitHub CI is pending the implementation-branch push. Physical worker/GPU behavior, remote/public deployment and full authentication remain untested and outside Phase 02.

## Stop boundary

Phase 03 remains unauthorized. This phase does not implement registration, worker credentials, node discovery/health transitions, scheduling, inference or functional dashboard screens. Production VPS provisioning, domains/DNS, TLS/public exposure and private-data use remain separately gated.
