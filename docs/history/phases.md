# Phase history and acceptance evidence

This is the consolidated historical record for Phases 01-12. The original scope,
commands, test results and limitations are retained below as evidence of what was
accepted at that time. Old version numbers and statements such as "not deployed"
are historical; use the [user guide](../../README.md) and [documentation index](../README.md)
for current installation and use. Historical authorization does not authorize new
operations. Phases 13 and 14 remain future milestones unless separately assigned.

Phase 10 was recorded in the [production release](../operations/production-release.md),
[first deployment](../operations/first-deployment.md), and dated deployment reports
rather than a separate phase-10 file. Later worker transport and account setup
revisions are recorded in [ADR 0016](../decisions/0016-simple-install-and-connect.md)
and [ADR 0017](../decisions/0017-account-connections-and-coding-project-setup.md).

## Records

- [Phase 01: Repository and environment](#phase-01)
- [Phase 02: Control-plane API](#phase-02)
- [Phase 03: Worker registration and health](#phase-03)
- [Phase 04: Durable job scheduler](#phase-04)
- [Phase 05: Local inference and provider gateway](#phase-05)
- [Phase 06: Agent runtime, stateful workflows and durable checkpoints](#phase-06)
- [Phase 07–08: Automatic failover and local Command Center](#phase-07-08)
- [Phase 09 real integration verification - 2026-10-16](#phase-09-integration)
- [Phase 09: Google authentication setup, migration and verification](#phase-09)
- [Phase 11 deployment verification - 2026-10-20](#phase-11-deployment-2026-10-20)
- [Phase 11 local validation - 2026-10-20](#phase-11-validation-2026-10-20)
- [Phase 11: coding, results and independent provider connections](#phase-11)
- [Phase 12 and Consigliere verification — 2026-10-21](#phase-12-verification-2026-10-21)
- [Phase 12: images, analytics and reports](#phase-12)

<a id="phase-01"></a>

<a id="phase-01--phase-01-repository-and-environment"></a>

## Phase 01: Repository and environment

<a id="phase-01--authorized-scope"></a>

### Authorized scope

Git monorepo, locked uv/Python and npm/Next.js dependencies, formatting/lint/typing/tests, local environment template, Compose dependencies and shell image, CI configuration, cross-platform setup and compatibility documentation. The dashboard is nonfunctional and local only.

No Phase 02 routes, health endpoints, configuration system, logging pipeline, SQLAlchemy models, migrations, or application persistence are implemented. No worker, scheduler, inference, agent workflow, failover, functional management UI, private-data use or public hosting is implemented.

<a id="phase-01--gate"></a>

### Gate

The sole developer can clone, restore dependencies, start the local Linux-container stack, open `http://localhost:3000`, and pass checks using repeatable setup instructions. The platform has two administrators, not two developers; the second administrator does not need a development environment. PostgreSQL data persists across container recreation. Workers and other later features will be testable with multiple simulated processes on one machine when their phases are implemented.

<a id="phase-01--initial-scaffold-validation"></a>

### Initial scaffold validation

These records describe the initial, pre-reboot checks. Current Docker/WSL2 results follow in the next section.

Validated locally on Windows x64 on 2026-10-15, with project-managed Python 3.14.8, uv 0.13.1, Node.js 24.22.0, npm 11.19.1, and Edge 155.0.4283.45.

| Check                                 | Actual result                                                                                                            |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Private GitHub repository             | GitHub metadata confirms `briancwelch/GodfatherAI` is private and empty; local `origin` configured                       |
| `uv sync --all-packages`              | Passed; `uv.lock` generated and local package installed                                                                  |
| `npm install`                         | Passed; root workspace lockfile generated                                                                                |
| Portable `scripts/dev.py check`       | Passed end to end after initial test typing corrections                                                                  |
| Ruff format/check                     | Passed                                                                                                                   |
| Strict mypy                           | Passed, four source files                                                                                                |
| pytest                                | Seven tests passed                                                                                                       |
| Prettier                              | Passed                                                                                                                   |
| ESLint 10                             | Passed, zero warnings                                                                                                    |
| TypeScript/Next route type generation | Passed                                                                                                                   |
| Next.js native production build       | Passed; static shell and icon generated                                                                                  |
| Native production server              | Running on `127.0.0.1:3000`; HTTP 200                                                                                    |
| Edge desktop, 1440×1000               | Light/dark passed; screenshots inspected                                                                                 |
| Edge narrow layout, 390×844           | Light/dark passed; screenshots inspected                                                                                 |
| Browser smoke behavior                | Skip link, keyboard phase anchor, collapsible narrow navigation, no horizontal overflow or console errors                |
| HTTP response headers                 | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` observed                                                      |
| `npm audit --audit-level=high`        | Zero reported vulnerabilities after replacing the Next lint preset                                                       |
| Compose client `config --quiet`       | Passed using checksum-verified Compose 5.6.0, with a disposable validation password supplied through process environment |
| Missing PostgreSQL password           | Configuration correctly rejected, exit 1                                                                                 |
| Official image manifests              | Selected Node, PostgreSQL and Redis tags advertise Linux amd64 and arm64                                                 |
| Git ignore rules                      | Local environment, tooling, dependencies, caches and build output excluded                                               |
| Development doctor                    | Expected failure: Docker CLI/engine prerequisites missing                                                                |

Browser automation used isolated headless Edge contexts after the browser tool's sandbox helper failed. The one-off smoke probe and screenshots are under ignored `.tools` and `.cache`; no browser test dependency was added to the project. This is a focused layout/keyboard check, not a full accessibility audit or actual mobile-device test.

The initial Windows inspection found no Docker Desktop/CLI installation and WSL reported not installed. The owner subsequently installed Docker Desktop for all users with its WSL2 backend and rebooted. The authorized post-reboot checks below supersede the initial Docker prerequisite failure.

CI definitions cover Python and frontend checks on Windows/macOS/Linux and container health/persistence on Linux. They are not completed runs until the repository is pushed and GitHub Actions executes with authorization.

`AGENTS.md` now explicitly records the owner's clarification: one developer builds the platform for two equal founding administrators. The shell copy, README, ADR and phase gate use the same distinction. `docs/design/UI-UX.md` remains unchanged, including its pre-existing trailing space.

<a id="phase-01--post-reboot-dockerwsl2-validation--2026-10-15"></a>

### Post-reboot Docker/WSL2 validation — 2026-10-15

| Check                       | Actual result                                                                                                                                                                |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| WSL                         | Default version 2; `docker-desktop` running on WSL2                                                                                                                          |
| Docker Desktop              | 4.95.0; client/server engine 29.8.2, `desktop-linux`, Linux amd64                                                                                                            |
| Docker Compose              | 5.6.0 from the installed Docker Desktop                                                                                                                                      |
| Local configuration         | Created ignored `.env` with a unique generated local password; no credential was printed or committed                                                                        |
| Fresh dashboard image build | Passed using the Linux standalone build/runtime stages                                                                                                                       |
| Full stack startup          | `docker compose up --build --wait --wait-timeout 180` passed; dashboard, PostgreSQL and Redis healthy                                                                        |
| Local URL                   | `http://localhost:3000` returns HTTP 200 from the dashboard container                                                                                                        |
| Port isolation              | Only `127.0.0.1:3000` published; PostgreSQL/Redis host bindings absent                                                                                                       |
| Backend network             | `internal=true`; dashboard and database/cache use separate networks                                                                                                          |
| Runtime restrictions        | Dashboard uid 1000 and Redis uid 999; both read-only root filesystems                                                                                                        |
| Redis                       | `PING` returned `PONG`                                                                                                                                                       |
| PostgreSQL persistence      | Committed a scratch value, recreated only the PostgreSQL container, confirmed a changed container ID and the surviving value; removed only the test-created table afterwards |
| Dependency lock cleanup     | Deduplicated old ESLint peer installations; the rebuilt container uses ESLint 10 without the old deprecation warning                                                         |
| Environment doctor          | Passed with Linux engine and all required tools available                                                                                                                    |
| Full local check runner     | Passed after the team-copy and lockfile changes: Ruff format/lint, strict mypy, seven pytest tests, Prettier, ESLint, strict TypeScript and native Next.js build             |
| npm audit                   | Zero reported vulnerabilities                                                                                                                                                |
| Container browser smoke     | Isolated Edge at 1440×1000 and 390×844, light and dark; all four cases passed HTTP, keyboard anchors, narrow navigation, overflow and console-error checks                   |

Local containers are intentionally left running for review. Stop them with `docker compose down`; preserve the named PostgreSQL volume. No host service installation, public deployment or external integration was performed by this verification.

<a id="phase-01--gate-completion-before-phase-02"></a>

### Gate completion before Phase 02

- Published as `9176cb00184e91b3e3df737c62285a862ef3feb7` to the authorized private repository.
- [All eight GitHub CI jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/38831542451), including Windows/macOS/Linux checks and Linux container health/persistence.
- A clean private-repository clone restored locked Python/npm dependencies and passed its complete check runner.
- Repeated local Docker startup and PostgreSQL container-recreation persistence passed. Redis temporary state was correctly discarded on recreation, followed by a successful PING.
- One developer/two administrators remains the team model. GPU and physical worker validation belong to later phases; CI does not prove every physical hardware/backend combination.

The Phase 01 gate passed before beginning the explicitly authorized Phase 02. See `phase-02.md` for current API configuration and commands.

<a id="phase-01--stop-condition"></a>

### Stop condition

Report completed work and remaining acceptance gaps, then stop. Phase 02 requires explicit approval. Cloud deployment, DNS changes, remote service installation and production credentials remain separately gated.

---

<a id="phase-02"></a>

<a id="phase-02--phase-02-control-plane-api"></a>

## Phase 02: Control-plane API

<a id="phase-02--scope-and-prerequisite-gate"></a>

### Scope and prerequisite gate

Phase 01 was committed/pushed as `9176cb00184e91b3e3df737c62285a862ef3feb7`. All eight jobs in [the Phase 01 CI run](https://github.com/briancwelch/GodfatherAI/actions/runs/38831542451) passed: Python across Windows/macOS/Linux plus Linux Python 3.12, frontend on all three OS runners, and Linux container startup/persistence. A fresh private-repository clone restored both lockfiles and passed all checks locally before Phase 02 code changes.

The local startup/health checks passed. A committed PostgreSQL probe survived container recreation. Redis's temporary probe was lost on recreation and Redis returned `PONG`, matching its deliberately non-durable policy. There is no Redis persistence requirement: PostgreSQL is the sole durable state authority under AGENTS.md.

Phase 02 adds the API foundation and schema only. No job submission, claims, scheduling, worker registration, heartbeat processing, inference, domain CRUD, or dashboard management is implemented. One developer builds the platform for two administrators.

<a id="phase-02--start-locally-all-supported-development-oses"></a>

### Start locally (all supported development OSes)

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

<a id="phase-02--configuration"></a>

### Configuration

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

<a id="phase-02--migrations-and-tests"></a>

### Migrations and tests

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

<a id="phase-02--validation-results"></a>

### Validation results

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

The implementation was committed as `cbcfb38ecec7e5046a6e4a746f81d8cb92673d4f` on `phase-02-control-plane`. [All eight Phase 02 CI jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/38833558905): Python checks on Windows/macOS/Linux and Linux Python 3.12, frontend checks on all three OS runners, and the Linux container job. That container job independently reported **44 passed** and a passing actual API/PostgreSQL restart, outage and recovery probe.

The Phase 02 gate is satisfied. Local services remain running for review. No Phase 03 work has begun. Physical worker/GPU behavior, remote/public deployment and full authentication remain untested and outside Phase 02.

<a id="phase-02--stop-boundary"></a>

### Stop boundary

Phase 03 remains unauthorized. This phase does not implement registration, worker credentials, node discovery/health transitions, scheduling, inference or functional dashboard screens. Production VPS provisioning, domains/DNS, TLS/public exposure and private-data use remain separately gated.

---

<a id="phase-03"></a>

<a id="phase-03--phase-03-worker-registration-and-health"></a>

## Phase 03: Worker registration and health

Current authentication is documented in [Phase 09](phases.md#phase-09).
Google OIDC/application sessions replace human bearer login in normal operation;
worker machine credentials remain independent. Earlier bearer/simulator procedures
below are historical and restricted to isolated automated tests. Phase 09 does not
authorize public deployment or Phase 10.

<a id="phase-03--scope-and-prerequisite"></a>

### Scope and prerequisite

Phase 03 was explicitly authorized. Before changes, the Phase 02 migration succeeded, the existing real-PostgreSQL suite passed **44 tests**, and the actual API/PostgreSQL restart, persistence, outage (live 200 / ready 503) and recovery probe passed. The full repository check also passed. An initial overlapping restart/test run caused two connection errors; after the probe finished, the serial test run passed. No Phase 02 source defect was found.

This phase adds authenticated enrollment, discovery, health, administration endpoints, simulated worker processes and durable lifecycle events. The dashboard remains disconnected. There is no scheduler, task execution, agent runtime, failover, inference or remote deployment.

<a id="phase-03--start-the-local-coordinator"></a>

### Start the local coordinator

Run from the repository root after the existing [setup guide](../operations/setup.md), using the ignored `.env`:

```text
uv sync --locked --all-packages
docker compose --profile tools build api migrate api-test
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Migration `0002_worker_health` is additive and preserves Phase 02 records. The API never migrates automatically. Health remains at **http://localhost:8000/health/live** and **http://localhost:8000/health/ready**; the existing nonfunctional shell remains at **http://localhost:3000**. Databases have no host ports.

Defaults are 10-second heartbeats, suspect after 20 seconds, offline after 30 seconds, and a 1-second database sweep. Configure `GODFATHER_HEARTBEAT_INTERVAL_SECONDS`, `GODFATHER_SUSPECT_AFTER_SECONDS`, `GODFATHER_OFFLINE_AFTER_SECONDS`, and `GODFATHER_HEALTH_SCAN_SECONDS` in `.env`, then recreate the API. Heartbeat must be less than suspect, which must be less than offline. Workers obey the interval returned by the API.

<a id="phase-03--provision-local-synthetic-identities"></a>

### Provision local synthetic identities

The local provisioning wrapper works on Windows, macOS and Linux. It invokes an offline command inside the running local API container using existing database authority. It captures one-time credentials into ignored `.cache/credentials` files, refuses overwrites, and prints only the owner UUID and destination. Never invoke the underlying provisioning module in a logged terminal: its stdout intentionally carries the one-time secret document.

```text
uv run --locked --all-packages python -m scripts.provision_local admin --email vegas-admin@example.invalid
uv run --locked --all-packages python -m scripts.provision_local admin --email la-admin@example.invalid --output .cache/credentials/la-admin.json
```

Both accounts have the same platform administrator role. These example identities are synthetic, not production accounts or browser sessions. Copy the printed Vegas owner UUID into `OWNER_UUID` below; use the LA owner's UUID for LA nodes if testing independent ownership:

```text
uv run --locked --all-packages python -m scripts.provision_local worker --owner-id OWNER_UUID --name LV-01
uv run --locked --all-packages python -m scripts.provision_local worker --owner-id OWNER_UUID --name LV-02
uv run --locked --all-packages python -m scripts.provision_local worker --owner-id OWNER_UUID --name LA-01
uv run --locked --all-packages python -m scripts.provision_local worker --owner-id OWNER_UUID --name LA-02
```

Names are unique within an owner; the reserved credential UUID becomes the persistent node UUID on registration. Do not copy one worker credential to multiple simultaneously running processes. Files use exclusive creation and POSIX mode 0600 inside a mode 0700 directory when newly created. On Windows, permissions inherit the parent directory's ACL: use an owner-private workspace and review its ACL. Git and Docker ignore `.cache` and `.env`; this is local development storage, not production secret management.

<a id="phase-03--run-four-simulated-workers-on-one-computer"></a>

### Run four simulated workers on one computer

Open four terminals in the repository root, then run one command in each:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LV-01.json --simulate LV-01
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LV-02.json --simulate LV-02
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LA-01.json --simulate LA-01
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LA-02.json --simulate LA-02
```

Each is an independent process with an individual credential, stable node UUID and process session UUID. LV profiles advertise Windows x64 and coding/images with different resources and policies; LA profiles advertise macOS arm64/x64 and analytics/reports. All fictional hardware, models and telemetry carry explicit simulated labels. They do not establish actual macOS/GPU support on a Windows computer. Each profile may be run on any development OS.

Inspect with an administrator credential:

```text
uv run --locked --all-packages python -m scripts.inspect_nodes --credential-file .cache/credentials/admin.json
uv run --locked --all-packages python -m scripts.inspect_nodes --credential-file .cache/credentials/admin.json --node-id NODE_UUID
uv run --locked --all-packages python -m scripts.inspect_nodes --credential-file .cache/credentials/admin.json --node-id NODE_UUID --action drain
```

Replace `NODE_UUID` with an actual node UUID. Actions also include `disable`, `enable`, and irreversible credential `revoke`. Draining remains visible while connection status changes independently; it does not execute or schedule anything. Administrative controls cannot grant host permissions. Stop a worker with Ctrl+C: it should become suspect at 20 seconds and offline at 30 seconds after its last heartbeat, within the next sweep, without affecting other workers. A replacement process must wait for that deadline before taking over the same identity; early duplicates exit with HTTP 409. Restarting a disabled/revoked worker is refused until enabled or separately reprovisioned, respectively.

Offline revocation also works for unregistered worker credentials and administrators:

```text
uv run --locked --all-packages python -m scripts.provision_local revoke --credential-id CREDENTIAL_UUID
```

<a id="phase-03--physical-discovery"></a>

### Physical discovery

Omit `--simulate` to discover the current host, then explicitly advertise allowed specialties and limits:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/physical-node.json --primary research --secondary coding --policy shared --concurrency 1
```

Provision `physical-node` first. This performs read-only host inventory, not inference or task execution. Discovery reads CPU/RAM through [psutil](https://psutil.readthedocs.io/stable/index.html); NVIDIA telemetry uses its documented [query interface](https://docs.nvidia.com/deploy/nvidia-smi/index.html). macOS uses system_profiler, Windows uses CIM, and Linux uses DRM sysfs plus optional rocminfo. Installed model inventory reads `ollama list` only when installed, forcing a loopback Ollama endpoint; unavailable probes are unknown/warnings. No drivers, models or services are installed. No repository or private file inventory is performed. Sandbox modes remain empty because finding Docker does not establish an authorized sandbox.

Workers open no listening ports. Local HTTP accepts only loopback origins. Future Tailscale communication requires an explicitly authorized HTTPS origin with valid certificates and the same node credentials. No remote service is configured or exposed by this phase.

<a id="phase-03--verification-commands"></a>

### Verification commands

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_worker_health
```

Create `godfather_test` once as documented in Phase 02 if absent. Integration tests reset only that explicitly disposable database. Run the worker smoke and database tests **serially**: the smoke intentionally restarts local PostgreSQL and the API. It creates a new synthetic owner, launches four native child processes, verifies fresh heartbeats, independently stops LV-01 and LA-01 while peers stay online, and checks ownership/identity/telemetry after actual service restarts. It stops only its own processes, preserves rows and writes logs/results to `.cache/phase03-runs/RUN_UUID/`. Successful completion revokes all its credentials. If interrupted or failed, use its private credential documents' `credential_id` values with the offline revoke command. Do not print their token fields.

The existing CI matrix runs worker/core/discovery tests on Windows, macOS and Linux, plus Python 3.12 on Linux. Configured CI is not proof that this unpushed change has run remotely. GPU inference and physical macOS/AMD validation are outside this local test evidence.

<a id="phase-03--validation-and-remaining-limits"></a>

### Validation and remaining limits

Validated on Windows x64 with Python 3.14.8, Docker Desktop/WSL2 Linux amd64, and PostgreSQL 17.11 on 2026-10-15:

| Check                                 | Actual result                                                                                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Phase 02 prerequisite                 | Migration, 44-test PostgreSQL suite, full repository checks, real service restarts, durable probe and outage/recovery passed before changes                        |
| Python formatting/lint/strict typing  | Passed; 29 source files type checked                                                                                                                               |
| Windows database-free suite           | 54 passed; 33 database cases deliberately skipped and separately executed in PostgreSQL                                                                            |
| Final real-PostgreSQL container suite | **87 passed**, including 33 integration cases, with no skips                                                                                                       |
| Migration round trip and metadata     | Passed; head `0002_worker_health`, no pending metadata operations, existing Phase 02 nodes preserved through the incremental upgrade                               |
| Frontend checks                       | Prettier, ESLint, strict TypeScript and production build passed; frontend source unchanged                                                                         |
| Dependency and configuration checks   | `uv pip check`, Compose validation and Git patch whitespace checks passed                                                                                          |
| Four native Windows child processes   | LV-01, LV-02, LA-01 and LA-02 registered and persisted subsequent heartbeats                                                                                       |
| Independent loss                      | LV-01 reached suspect then offline while the other three remained online; LA-01 later reached suspect then offline while LV-02 and LA-02 remained online           |
| Actual API/PostgreSQL restarts        | Node UUIDs, ownership, credentials and telemetry survived; surviving workers continued heartbeats                                                                  |
| Final loss and durable events         | All four stopped workers reached offline; PostgreSQL retained four registration events and twelve connection transitions (online/suspect/offline for each)         |
| Provisioning/inspection CLI           | Documented credential-file provisioning, authenticated node listing and offline revocation commands passed with separate synthetic credentials                     |
| Demo cleanup                          | All child processes stopped; all five demo credentials revoked; four preserved node records are now disabled with offline connection status                        |
| Real Windows discovery                | Reported 20 logical CPUs, 33,693,753,344 RAM bytes, NVIDIA GeForce RTX 5060 Ti driver memory/utilization and Intel Graphics with unknown backend; no inference run |
| Cross-platform discovery              | Windows, macOS arm64/x64, Linux, CPU-only, NVIDIA, reported Metal/ROCm, unsupported values and missing probes covered through mocks on the local suites            |

The successful live run is `8192dcefd05d4f48b85150471e1012ed`. Its non-secret snapshots and stage evidence are in `.cache/phase03-runs/8192dcefd05d4f48b85150471e1012ed/result.json`, with individual worker logs beside it. The result captures all nodes offline before credential revocation; current database state is disabled/offline after revocation. Read-only physical discovery evidence is `.cache/phase03-physical-discovery.json`. These local evidence files and revoked credential documents are intentionally ignored by Git and excluded from Docker builds. Local services remain healthy on loopback for review.

No unresolved local check failures remain. The new CI step is configured to repeat the four-process smoke after the serial database tests, but this change has not been pushed or run on remote CI. Physical macOS, physical AMD/Metal execution, Linux arm64 execution, inference, and remote/Tailscale/TLS connectivity remain unverified. Mock or driver-discovery results do not establish them.

<a id="phase-03--files-changed"></a>

### Files changed

| Area                             | Files                                                                                                                                                                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API                              | `apps/api/pyproject.toml`; `apps/api/src/godfather_api/{app,config,logging,models,nodes,provision}.py`                                                                                                |
| Portable protocol                | `packages/shared-schemas/pyproject.toml`; `packages/shared-schemas/src/godfather_contracts/__init__.py`                                                                                               |
| Worker                           | `packages/worker/pyproject.toml`; `packages/worker/src/godfather_worker/{__init__,cli,client,discovery,simulated}.py`                                                                                 |
| Database                         | `infrastructure/migrations/versions/0002_worker_health.py`                                                                                                                                            |
| Local infrastructure and tooling | `.env.example`; `compose.yaml`; `infrastructure/docker/api.Dockerfile`; `pyproject.toml`; `uv.lock`; `.github/workflows/checks.yml`; `scripts/{check_worker_health,inspect_nodes,provision_local}.py` |
| Tests                            | `tests/test_api.py`; `tests/test_worker.py`; `tests/integration/test_database.py`; `tests/integration/test_nodes.py`                                                                                  |
| Documentation                    | `README.md`; `docs/architecture/{compatibility,security-foundation}.md`; `docs/operations/{setup,phase-03}.md`; `docs/protocols/worker-v1.md`; `docs/decisions/0003-worker-identity-and-health.md`    |

Full browser authentication, contributor/member RBAC, token rotation preserving identity, remote invitation/distribution, rate limiting, real hardware inference, and public deployment are later gates. Discovery is self-reported telemetry, not host attestation or a guarantee that an inference backend works. Some adapters cannot report dedicated GPU memory or GPU utilization; these remain null. No scheduling permissions or model execution are inferred from hardware reports.

See [ADR 0003](../decisions/0003-worker-identity-and-health.md) and the [protocol contract](../protocols/worker-v1.md). Stop after Phase 03. Phase 04 requires explicit authorization.

---

<a id="phase-04"></a>

<a id="phase-04--phase-04-durable-job-scheduler"></a>

## Phase 04: Durable job scheduler

<a id="phase-04--scope-and-prerequisite"></a>

### Scope and prerequisite

Phase 04 was explicitly authorized. Before editing, the existing real-PostgreSQL suite passed **87 tests** without skips. The full repository check passed: Python format/lint/strict typing, **54 Windows unit tests** (33 PostgreSQL tests separately executed), and frontend format/lint/type/build. The live four-process Phase 03 smoke also passed registration, fresh heartbeats, independent suspect/offline transitions, actual API/PostgreSQL restarts, ownership/identity persistence and credential cleanup. Prerequisite evidence: `.cache/phase03-runs/012ca5e68efc495eb419eaa7ab1217e9/result.json`. No prerequisite defect was found. The existing Phase 03 working-tree changes were preserved.

This phase adds PostgreSQL jobs/attempts/events, matching, fairness, leases/fences, cancellation, retries and opt-in synthetic workers. No real coding, inference, MCP, agents, dashboard management, checkpoint restoration or remote deployment is implemented. No service or dependency was added.

<a id="phase-04--local-startup"></a>

### Local startup

After the [existing setup](../operations/setup.md), from the repository root with the ignored local `.env`:

```text
uv sync --locked --all-packages
docker compose --profile tools build api migrate api-test
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Apply the additive `0003_durable_scheduler` migration explicitly. Existing data is retained. Readiness rejects a mismatched schema; startup never applies migrations. The active-attempt index refuses any inconsistent legacy duplicate active attempts instead of deleting records. Databases have no public/host ports.

Local API: **http://localhost:8000/api/v1**. Health: **http://localhost:8000/health/ready**. The unchanged disconnected shell remains **http://localhost:3000**; it does not display jobs or live metrics. Public names remain proposed and unused.

Defaults: 30-second execution leases, 10-second heartbeats, suspect/offline thresholds 20/30 seconds, and one-second maintenance. Configure `.env` `GODFATHER_EXECUTION_LEASE_SECONDS` and recreate the API. `GODFATHER_SCHEDULER_ENABLED=false` pauses assignment and execution recovery, retaining health monitoring. `health_monitor_enabled=False` is the internal deterministic-test switch disabling the combined maintenance task.

<a id="phase-04--submit-and-inspect-synthetic-jobs"></a>

### Submit and inspect synthetic jobs

Provision a new synthetic administrator and two workers using [Phase 03](phases.md#phase-03), or reuse your existing private development credential files. Do not print bearer tokens. Replace `OWNER_UUID`, `WORKSPACE_UUID` and `JOB_UUID` below with actual IDs:

```text
uv run --locked --all-packages python -m scripts.provision_local workspace --owner-id OWNER_UUID --name Scheduler-demo
uv run --locked --all-packages python -m scripts.jobs submit --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID --capability coding --count 100
uv run --locked --all-packages python -m scripts.jobs list --credential-file .cache/credentials/admin.json
uv run --locked --all-packages python -m scripts.jobs inspect --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.jobs events --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.jobs attempts --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.jobs cancel --credential-file .cache/credentials/admin.json --job-id JOB_UUID
```

Workspace provisioning is offline local database administration, not a public API. It creates a private workspace owned by the specified enabled user. No user/membership management UI is introduced. Use reviewed synthetic database fixtures for cross-owner membership testing until broader administration is authorized.

Open two terminals, each with its own provisioned worker credential:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LV-01.json --simulate LV-01 --execute-synthetic --concurrency 1
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/LA-01.json --simulate LA-01 --execute-synthetic --concurrency 1
```

`--step-seconds 1` adds a bounded synthetic delay per step for observation. Workers renew leases and send heartbeats during delays. Without `--execute-synthetic`, Phase 03 registration/heartbeat-only behavior continues and no jobs are assigned. Physical discovery workers cannot opt into execution in this phase.

Dedicated nodes serve only their owner. Preferred nodes give their owner first refusal on compatible queued work and rank ahead of other eligible nodes for the owner's jobs. Shared nodes are normal eligible candidates. Primary specialties rank ahead of secondary specialties within the preference tier; compatible backups run when preferred capacity is unavailable. All nodes must be online, authenticated, enabled, fresh and compatible. Active reservations prevent oversubscribing declared CPU, memory and concurrency. GPU matching is conservative and never performs inference.

Across owners, the node owner must already have explicit workspace access. Its worker must then opt in with **both** `--allow-owner OWNER_UUID` and `--allow-workspace WORKSPACE_UUID`, and a non-dedicated policy. These can be repeated. Omit the flags to withdraw sharing on registration. Administrative health controls cannot supply them. Workspace public/shared flags do not grant membership. A job owner who loses workspace access cannot continue execution.

Fairness chooses the eligible user with fewest active assignments, then oldest persisted scheduling turn; priority and FIFO apply within that user's work. This is nonpreemptive admission fairness, not a resource-time quota. Incompatible head jobs do not block compatible jobs. See the [state machine, exact retry formula, endpoint contracts and fencing protocol](../protocols/jobs-v1.md) and [ADR 0004](../decisions/0004-durable-synthetic-scheduler.md).

<a id="phase-04--repeatable-acceptance"></a>

### Repeatable acceptance

Run serially; the live smoke intentionally restarts the local PostgreSQL/API services. Never run database-reset integration tests concurrently with live acceptance.

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_job_scheduler
```

The PostgreSQL suite resets only the explicitly guarded `godfather_test` database in `environment=test` with `GODFATHER_RUN_INTEGRATION=1`; create it as documented in Phase 02. It verifies schema/migration metadata and round trips, validation, permission isolation, compatibility/reservations, primary/backup nodes, parallel scheduling/polling, expiry before sweeping, stale reports after reassignment/completion, cancellation races, retry bounds/backoff, API/pool recreation, node loss and persistent round-robin fairness. Its deterministic workload completes 100 jobs across two concurrent simulated worker sessions, with one active attempt per job.

The host smoke creates only new synthetic records and a private ignored `.cache/phase04-runs/RUN_UUID/` evidence directory. It submits 100 jobs before starting workers, actually restarts PostgreSQL/API, verifies all 100 remain pending, then launches two native worker processes. Ten inputs intentionally fail once, producing 110 attempts. It verifies terminal states and nonoverlapping attempt intervals and leaves an OS-incompatible job queued. It then stops the actual worker running another synthetic job, waits for lease expiry, and verifies retry on the surviving worker with a new fencing token. The handler runs from the beginning. Finally it cancels the incompatible probe, stops only its own child processes and revokes its three credentials, retaining rows/evidence. Failures also stop/revoke owned processes/credentials; synthetic jobs already created may remain queued or recoverable for inspection.

The CI OS matrix covers portable tests on Windows/macOS/Linux and Python 3.12/3.14. The serial Linux container job runs this live acceptance after Phase 03. Configured CI is not proof of an executed remote run.

<a id="phase-04--validation-and-limits"></a>

### Validation and limits

Validated on 2026-10-15 using Windows x64/Python 3.14.8, Docker Desktop/WSL2 Linux amd64 and PostgreSQL 17.11:

| Check                               | Actual result                                                                                                                                             |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 03 prerequisite               | 87 PostgreSQL tests, full repository checks and four-process health/restart smoke passed before changes                                                   |
| Python format/lint/strict types     | Passed; 38 source files type checked                                                                                                                      |
| Windows database-free suite         | **84 passed**; 59 database cases deliberately skipped and separately executed against PostgreSQL                                                          |
| Complete PostgreSQL container suite | **143 passed**, no skips; includes 59 integration cases and the deterministic 100-job workload                                                            |
| Migrations                          | Additive upgrade, metadata comparison, idempotence and guarded disposable-database round trips passed; local application head is `0003_durable_scheduler` |
| Frontend                            | Prettier, ESLint, strict TypeScript and production build passed; dashboard source unchanged                                                               |
| Configuration/dependencies          | Compose validation, `uv pip check` and Git patch whitespace checks passed                                                                                 |
| Native two-process workload         | **100 completed jobs, 110 attempts, 48/52 completions across the two nodes, zero overlapping assignments**                                                |
| Actual API/PostgreSQL restarts      | All 100 pending jobs survived and later completed                                                                                                         |
| Real worker-process loss            | Stopped running LV Windows simulator; expired attempt failed; surviving LA macOS simulator completed fresh attempt with fencing token 2                   |
| Incompatible job                    | Linux-only job remained pending, then was explicitly cancelled during cleanup                                                                             |
| Cleanup and credential logging      | Both native processes stopped, all three run credentials revoked, all 102 synthetic jobs terminal, no run credentials in worker logs                      |

Final native acceptance evidence is `.cache/phase04-runs/425d327da6504a3385e226169a112a3a/result.json`, with individual worker logs beside it. An earlier complete live acceptance also passed in `4425d850f0e8418bb994c65c2c66d3ef`. Evidence/credentials stay ignored and excluded from Docker builds. Both runs recorded no overlapping execution attempts; the database unique index and concurrency tests additionally enforce active ownership. Checkpoint references stayed null. Local API and shell remain available on loopback. No unresolved local test failures remain. Remote CI is configured; its results must be checked separately on the pushed branch.

One initial regression test failed because new registration stored empty consent lists instead of the existing empty policy. Storage was corrected to preserve the old empty-policy representation, and the subsequent complete PostgreSQL suite passed. Later validation adds explicit exact-label dependencies, rollback and synthetic-worker cancellation tests.

No physical macOS/Linux worker, Metal/AMD/CUDA inference, actual coding, checkpoints, remote/Tailscale/TLS connectivity, public hosting, external integrations or browser authentication are established by simulation. The coordinator runs Linux containers locally on Windows. This scheduler is sized for the initial small cluster and scans queued jobs; no large-cluster throughput or time-based fairness claim is made. Full contributor/member RBAC and production security remain separately gated. Current endpoints are authenticated local development functionality only.

<a id="phase-04--phase-04-files-changed"></a>

### Phase 04 files changed

| Area                       | Files                                                                                                                                                                                                         |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Control plane              | `apps/api/src/godfather_api/{app,config,models,nodes,provision,jobs,scheduler}.py`                                                                                                                            |
| Database                   | `infrastructure/migrations/versions/0003_durable_scheduler.py`                                                                                                                                                |
| Contracts                  | `packages/shared-schemas/src/godfather_contracts/{__init__,jobs}.py`                                                                                                                                          |
| Portable synthetic worker  | `packages/worker/src/godfather_worker/{__init__,cli,client,jobs,simulated}.py`                                                                                                                                |
| Simulation and local tools | `scripts/{provision_local,jobs,check_job_scheduler}.py`                                                                                                                                                       |
| Tests                      | `tests/test_scheduler.py`, `tests/integration/test_jobs.py`                                                                                                                                                   |
| Configuration/CI           | `.env.example`, `compose.yaml`, `.github/workflows/checks.yml`                                                                                                                                                |
| Documentation              | `README.md`, `docs/operations/{setup,phase-04}.md`, `docs/architecture/{compatibility,security-foundation}.md`, `docs/protocols/{worker-v1,jobs-v1}.md`, `docs/decisions/0004-durable-synthetic-scheduler.md` |

Repository rules added during this phase require dynamic users/nodes and a commit/push at phase completion. Scheduling uses persistent identities without geographic bindings. The phase is saved on `phase-04-durable-scheduler`, including the existing uncommitted Phase 03 foundation. The added rules in `AGENTS.md` are preserved; only trailing whitespace was removed.

Stop after Phase 04. The next recommended milestone is **Phase 05: local model inference**; do not begin without explicit approval.

---

<a id="phase-05"></a>

<a id="phase-05--phase-05-local-inference-and-provider-gateway"></a>

## Phase 05: Local inference and provider gateway

<a id="phase-05--real-model-gate-confirmed-before-phase-06"></a>

### Real-model gate confirmed before Phase 06

After the user made Ollama available, Phase 05 was reverified before Phase 06 changes: all **200 PostgreSQL-backed tests** passed, Windows checks passed (122 tests; 78 database cases separately executed), and formatting/lint/strict typing plus frontend formatting/lint/types/build passed. Cancellation, stale-attempt rejection and durable inference were covered by the executed suite.

The existing native-worker acceptance then ran against the already installed `qwen3:8b`, with an explicit 512-token output budget to allow its reasoning before the visible answer. Both streaming and non-streaming jobs completed through the authenticated API, scheduler, native worker and model gateway. The streaming result included `Hello!`. Completed results were unchanged after an actual API restart. Evidence: `.cache/phase05-runs/567de24eb58348a5943bec7cf20e3758/result.json`, with SSE captures and worker log beside it. The run's worker was stopped and both credentials revoked. No model installation/download or system configuration change occurred. This establishes the real-local-model gate; it does not establish physical macOS/Linux or GPU-backend parity.

Repeat with an already installed model:

```text
uv run --locked --all-packages python -m scripts.check_model_inference --ollama --model YOUR_EXACT_INSTALLED_MODEL --max-tokens 512 --verify-restart
```

The earlier unavailable-Ollama notes below record the initial Phase 05 delivery, superseded by this successful real-model acceptance. Phase 06 was subsequently explicitly authorized by the user.

<a id="phase-05--scope-and-prerequisite"></a>

### Scope and prerequisite

Phase 05 was explicitly authorized. Before edits, Phase 04 passed Python formatting/lint/strict typing, 84 Windows unit tests, all 143 PostgreSQL-backed tests without skips, frontend formatting/lint/type/build, and the native scheduler acceptance. That acceptance completed 100 jobs across two workers with 110 nonoverlapping attempts, preserved queued jobs through actual API/PostgreSQL restarts, left an incompatible job queued, and recovered a stopped worker's job on a surviving worker with a new fence. Evidence: `.cache/phase04-runs/bd98ed06f5d44e89a4ccfd4826bbfa92/result.json`.

This phase adds the provider-neutral gateway, Ollama/OpenAI-compatible adapters, model advertisements and matching, opt-in text execution, authenticated result/model/metrics APIs, and attempt-aware SSE. Read [architecture](../architecture/model-gateway.md), [ADR 0005](../decisions/0005-worker-local-model-gateway.md), and [typed inference protocol](../protocols/inference-v1.md).

No agent orchestration, model download, image workflow, MCP, coding agent, full dashboard, remote integration or cloud deployment is included. The dashboard remains the existing disconnected shell. Phase 06 requires separate explicit authorization.

<a id="phase-05--start-local-services"></a>

### Start local services

Use the [existing cross-platform setup](../operations/setup.md), ignored `.env`, and Docker Desktop/WSL2 on Windows. All commands run from the repository root:

```text
uv sync --locked --all-packages
docker compose --profile tools build api api-test migrate
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

There is no new database revision: typed deployment/partial/result metadata uses existing JSONB columns. The schema head stays `0003_durable_scheduler`. The migration command remains an explicit readiness check; startup never changes schema.

API: **http://localhost:8000/api/v1**, readiness: **http://localhost:8000/health/ready**, disconnected shell: **http://localhost:3000**. Publishing remains loopback-only, databases internal. Nothing uses the proposed public domains or DigitalOcean.

<a id="phase-05--existing-ollama-installation"></a>

### Existing Ollama installation

Do not install Ollama, start an installed service, change its binding/firewall, or download a model without owner authorization. If it is already running, inspect `http://127.0.0.1:11434/api/tags` or run `ollama list`. Choose the exact returned identifier, including tag. The worker never calls model pull/create/delete endpoints.

Create `.cache/credentials/providers.json` in your owner-private credential directory. This file contains worker-local configuration, never coordinator settings:

```json
[
  {
    "id": "local-inference",
    "provider": "ollama",
    "url": "http://127.0.0.1:11434",
    "timeout_seconds": 120
  }
]
```

Provision an administrator, private workspace, and individually authenticated worker using the existing [Phase 03](phases.md#phase-03) and [Phase 04](phases.md#phase-04) instructions. Use actual IDs, with no production credentials. Start the worker on the machine hosting Ollama:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/worker.json --inference-config .cache/credentials/providers.json
```

Physical discovery is portable and requires no CUDA. macOS providers may use Metal internally; the coordinator makes no OS-specific inference calls. No OS service is installed. Keep the terminal running. Inference advertises one concurrency slot; `--concurrency` other than 1 is refused in this phase. Existing contribution policies and repeated `--allow-owner UUID`/`--allow-workspace UUID` options still control cross-owner execution. Platform administration cannot supply that consent.

List available deployments with the administrator credential and actual workspace UUID:

```text
uv run --locked --all-packages python -m scripts.inference models --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID
```

Create a private `.cache/credentials/inference-request.json` using the [request example](../protocols/inference-v1.md), replacing the workspace and model identifiers. Keep prompts out of shell arguments/history. Submit and inspect using the returned job UUID:

```text
uv run --locked --all-packages python -m scripts.inference submit --credential-file .cache/credentials/admin.json --request-file .cache/credentials/inference-request.json
uv run --locked --all-packages python -m scripts.inference stream --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.inference result --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.inference metrics --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID
uv run --locked --all-packages python -m scripts.inference cancel --credential-file .cache/credentials/admin.json --job-id JOB_UUID
```

Result/stream commands intentionally display authorized response text. Streams close after at most 30 seconds; rerun/reconnect for the current snapshot. Clients replace text on each snapshot and clear it on reset/invalidation. If no compatible model exists the job remains `PENDING`; no alternate model is selected. Set both streaming flags false for a non-streaming job. Changing available models requires no application source change or coordinator restart; workers refresh discovery between attempts.

<a id="phase-05--openai-compatible-providers"></a>

### OpenAI-compatible providers

A compatible endpoint can be local or an explicitly authorized remote service. Merely supporting remote configuration does not authorize contacting an account, incurring costs or sending private data. Configure only approved endpoints; none is preconfigured or contacted by tests.

```json
[
  {
    "id": "approved-provider",
    "provider": "openai_compatible",
    "url": "https://YOUR_APPROVED_HOST/v1",
    "api_key_env": "GODFATHER_APPROVED_PROVIDER_KEY",
    "chat_enabled": true,
    "stream_enabled": true,
    "declared_capabilities": ["completion"],
    "timeout_seconds": 120
  }
]
```

Set the named environment variable securely in the worker's environment; never put its value in job/config payloads, committed files or logs. For an already-approved local compatible provider, HTTP is permitted only on loopback. Certificate validation is mandatory remotely; redirects and environment proxies are disabled. Discovery does not certify capabilities, context sizes or operation support. Capability-based selection must explicitly accept declarations; exact model identifiers still require enabled operations.

<a id="phase-05--repeatable-tests-and-native-demonstration"></a>

### Repeatable tests and native demonstration

The integration reset guard is unchanged: only `environment=test`, `godfather_test`, and `GODFATHER_RUN_INTEGRATION=1` permit migration-reset tests. Never run reset tests concurrently with live acceptance.

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
uv pip check
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_model_inference
```

The default native acceptance starts its own loopback mock Ollama server and native worker, provisions fresh synthetic identities/workspace, advertises a model, submits streaming and non-streaming jobs, reads attempt-tagged SSE, verifies final results and metadata, checks worker logs for prompt/credential leaks, then stops its own processes/server and revokes its credentials. Jobs/evidence remain for inspection. It never replaces a real provider or binds port 11434. Evidence is under ignored `.cache/phase05-runs/RUN_UUID/`. Mock results are labeled `mock_ollama`; their token figures are fixtures, not hardware measurements.

With an **already running** Ollama and an **already installed** suitable model, use:

```text
uv run --locked --all-packages python -m scripts.check_model_inference --ollama --model YOUR_EXACT_INSTALLED_MODEL
```

This runs the same full API/scheduler/native-worker/client path against loopback Ollama and labels evidence `real_ollama`. It does not download anything. The simulated advertisement used by the smoke is clearly labeled; a real provider invocation establishes inference on this host, not simulated CPU/GPU performance. Use the normal worker command for actual host discovery.

The CI OS matrix covers portable Python/provider/matching tests on Windows/macOS/Linux and Python 3.12/3.14. Its Linux container job now also includes native-worker/mock-provider acceptance. Configuration does not establish an executed remote CI run.

<a id="phase-05--validation-and-unresolved-gate"></a>

### Validation and unresolved gate

Executed on 2026-10-15 with Windows x64/Python 3.14.8 and Docker Desktop/WSL2 Linux amd64:

| Check                                 | Actual result                                                                                                                                                                                                                                                                           |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 04 prerequisite                 | Full repository checks, 143 PostgreSQL tests, and native 100-job/restart/worker-loss acceptance passed before edits                                                                                                                                                                     |
| Python formatting/lint                | Passed; 71 Python files formatted consistently                                                                                                                                                                                                                                          |
| Strict typing                         | Passed; 50 source files checked                                                                                                                                                                                                                                                         |
| Windows database-free tests           | **122 passed**; 78 PostgreSQL cases deliberately skipped here and executed separately below                                                                                                                                                                                             |
| Complete built-image PostgreSQL suite | **200 passed**, no skips, including 78 integration cases and the preserved 100-job scheduler workload                                                                                                                                                                                   |
| Provider/model coverage               | Streaming/non-streaming Ollama/OpenAI-compatible mocks, discovery/provenance, exact model matching, unknown resources, OS mocks, transport/protocol failures, total timeouts and HTTP cancellation                                                                                      |
| Persistence/security coverage         | Registration updates, same model on multiple nodes, workspace/owner restrictions, queueing, bounded contiguous output, live SSE partial/final snapshots, reconnection, API/pool recreation, lease/deadline expiry, stale reports after replacement, cancellation races and retry policy |
| Old synthetic protocol                | New optional fields omitted from synthetic assignments; explicit compatibility regression passed                                                                                                                                                                                        |
| Frontend                              | Prettier, ESLint, strict TypeScript and production build passed; dashboard source unchanged                                                                                                                                                                                             |
| Containers/dependencies               | Final API/test/migration images built; migration readiness, Compose validation, `uv pip check` and Git whitespace checks passed                                                                                                                                                         |
| Native worker demonstration           | Actual outbound worker process discovered the loopback mock model and completed streaming and non-streaming jobs through the local API/scheduler/gateway/SSE/result path                                                                                                                |
| Privacy/cleanup                       | Acceptance verified no prompt/run credentials in its worker log; owned worker/server stopped and two run credentials revoked; synthetic records/evidence retained                                                                                                                       |
| Real Ollama                           | **Not executed: loopback API unavailable**, both before implementation and on final recheck                                                                                                                                                                                             |

Final native evidence: `.cache/phase05-runs/ceb56288d92448e1aeb414eb135d0c8f/result.json`, with its SSE captures and worker log beside it. An earlier complete acceptance also passed in `394566e6c6bf4078a238be4f4963d033`. Both are explicitly labeled `mock_ollama`; their token counts/rates are deterministic fixtures, not actual model throughput. Local API/shell remain healthy and loopback-only.

Initial implementation checks exposed test-module namespace typing ambiguity, fixed by explicit test package markers. Review also caught older strict worker compatibility and cancellation during an output upload; both now have passing regressions. No unresolved local formatting/lint/type/test failure remains. Remote CI is configured but has not been claimed as executed.

Real Ollama was not reachable at `127.0.0.1:11434`, and its executable was not found on the execution shell's PATH. This does not prove it is absent from every local installation directory. No installation, model download or system change was attempted. The roadmap's real-local-model gate cannot be claimed from mocks; it remains open until an already installed model can be exercised with the command above. Implementation is saved on `phase-05-model-gateway`; this does not declare the real-inference gate passed.

Physical macOS/Linux inference and CUDA/Metal/AMD acceleration remain unverified. Local Windows native execution, Linux container tests and mocked platform compatibility are separate evidence. Compatible-provider behavior beyond the standard chat/SSE contract, production security/retention controls, large artifact storage and actual remote failover remain later work.

<a id="phase-05--files-changed"></a>

### Files changed

| Area          | Files                                                                                                                                                                                                                                   |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gateway       | `packages/model-gateway/pyproject.toml`, `src/godfather_model_gateway/{__init__,providers}.py`                                                                                                                                          |
| Contracts     | `packages/shared-schemas/src/godfather_contracts/{__init__,jobs,inference}.py`                                                                                                                                                          |
| API/scheduler | `apps/api/src/godfather_api/{app,jobs,nodes,scheduler,inference}.py`                                                                                                                                                                    |
| Worker        | `packages/worker/pyproject.toml`, `src/godfather_worker/{cli,client,jobs,inference}.py`                                                                                                                                                 |
| Tools         | `scripts/{inference,check_model_inference}.py`                                                                                                                                                                                          |
| Tests         | `tests/{__init__,test_model_gateway,test_inference_matching}.py`, `tests/integration/{__init__,test_inference}.py`                                                                                                                      |
| Workspace/CI  | `pyproject.toml`, `uv.lock`, `.github/workflows/checks.yml`                                                                                                                                                                             |
| Docs          | `README.md`, `docs/architecture/{model-gateway,compatibility,security-foundation}.md`, `docs/decisions/0005-worker-local-model-gateway.md`, `docs/protocols/{inference-v1,worker-v1,jobs-v1}.md`, `docs/operations/{phase-05,setup}.md` |

Stop after Phase 05. Do not begin Phase 06 without explicit approval, and do not treat the unverified real-inference gate as passed.

---

<a id="phase-06"></a>

<a id="phase-06--phase-06-agent-runtime-stateful-workflows-and-durable-checkpoints"></a>

## Phase 06: Agent runtime, stateful workflows and durable checkpoints

<a id="phase-06--scope-and-prerequisite"></a>

### Scope and prerequisite

Phase 06 was explicitly authorized after confirming Phase 05. Before Phase 06 implementation, the full repository check passed (format/lint/strict typing, 122 Windows tests, frontend format/lint/types/build); all 200 PostgreSQL-backed tests passed without skips, including cancellation, durable results and fencing. A real `qwen3:8b` job passed through the API, native worker and gateway in both streaming/non-streaming modes, and results survived an actual API restart. Phase 05 evidence: `.cache/phase05-runs/567de24eb58348a5943bec7cf20e3758/result.json`. This closure was committed/pushed as `143e14e` before Phase 06 changes.

This phase implements portable immutable agent versions, predefined sequential model/tool workflows, read-only tool grants, central immutable JSON artifacts, transactional checkpoints, fenced same-node process-restart recovery and authenticated workflow APIs. Read [architecture](../architecture/agent-runtime.md), [ADR 0006](../decisions/0006-sequential-workflows-and-artifacts.md), and [API/protocol](../protocols/agents-v1.md).

The user also requested hybrid local/frontier BYOK planning only. [That plan](../architecture/byok-plan.md) is saved; it is **not implemented or authorized for implementation**. Phase 06 workflow configuration accepts loopback providers only, validated before provider discovery. No cloud calls, paid fallback, keys/secret stores, cost ledger, grant/approval system or new frontier adapter is introduced.

<a id="phase-06--local-startup-and-storage"></a>

### Local startup and storage

Use the [Windows/macOS/Linux setup](../operations/setup.md) and existing ignored `.env`. From the repository root:

```text
uv sync --locked --all-packages
docker compose --profile tools build api api-test migrate
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Apply the additive migration explicitly; the head is now `0004_agent_runtime`. Existing identities, jobs, inference results and legacy agent/checkpoint rows remain. Old schema-only agents are disabled and unsupported rather than treated as executable definitions. Startup/readiness never silently apply migrations. Downgrades/reset tests are restricted to the guarded disposable `godfather_test` database.

API: **http://localhost:8000/api/v1**, readiness: **http://localhost:8000/health/ready**, unchanged disconnected shell: **http://localhost:3000**. Public domains remain proposed and unused.

Compose mounts the new local `artifacts-data` named volume only on the API, at `/var/lib/godfather/artifacts`; the non-root API otherwise keeps its read-only filesystem. Database rows own artifact visibility and metadata; clients never receive host paths. Native API development uses ignored `.cache/artifacts` or an explicitly configured `GODFATHER_ARTIFACT_DIRECTORY`. Use an owner-private Windows directory/ACL, or POSIX 0700 directory/0600 files. Never put the artifact store in a public web directory.

Database and artifacts must be retained/backed up together. An API restart/recreation retains the named volume; `docker compose down` without volume deletion retains both database and artifact volumes. Do not delete volumes or orphan files automatically. Transaction failures may leave unreferenced files; production retention/GC and a complete backup/restore runbook remain later work. Missing/corrupt referenced files block restoration visibly with a 503.

<a id="phase-06--define-and-run-a-local-workflow"></a>

### Define and run a local workflow

Reuse [Phase 03 private credential provisioning](phases.md#phase-03) and [Phase 04 private workspace provisioning](phases.md#phase-04). Each worker has its own node credential and owner. No identities or keys are preseeded. Use only synthetic instructions during this local development phase.

If Ollama is already installed/running, use its existing discovered model identifier. No command below installs it, changes its binding or pulls a model. Create the worker-owned provider configuration as described in [Phase 05](phases.md#phase-05), using loopback Ollama or an already approved local compatible provider.

Create a portable data-only demonstration definition and store it in your private ignored directory. Replace the model placeholder with the exact installed identifier:

```text
uv run --locked --all-packages python -m scripts.workflows demo-definition --model YOUR_INSTALLED_MODEL --definition-file .cache/credentials/demo-agent.json
uv run --locked --all-packages python -m scripts.workflows create --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID --definition-file .cache/credentials/demo-agent.json
uv run --locked --all-packages python -m scripts.workflows list --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID
```

The definition file is exclusively created; existing files are not overwritten. The backend creates a stable agent ID and immutable version-1 row. The demo has three steps: structured model plan, authorized deterministic `plan.describe@1`, and model summary. It is configuration, not a special hardcoded agent type. Edit your private copy or create other names/configurations as needed; append versions rather than mutating one already submitted.

Start the worker, granting both the tool reference and required permission:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/worker.json --inference-config .cache/credentials/providers.json --execute-workflows --allow-tool plan.describe@1 --allow-tool-permission plan.read
```

This uses physical discovery by default and no host services. It does not grant filesystem, shell, Git, SQL or account access. Platform administrators cannot supply the node owner's grants. Cross-owner execution still additionally requires that node owner's workspace access, existing owner/workspace allowlists and a compatible contribution policy. Missing grants leave jobs queued or refuse subsequent tool transitions. One slot is advertised/executed per worker; multiple nodes remain dynamically managed.

Create a private plain UTF-8 `.cache/credentials/instruction.txt` containing a synthetic instruction, then submit using the actual returned agent ID:

```text
uv run --locked --all-packages python -m scripts.workflows submit --credential-file .cache/credentials/admin.json --workspace-id WORKSPACE_UUID --agent-id AGENT_UUID --agent-version 1 --instruction-file .cache/credentials/instruction.txt
uv run --locked --all-packages python -m scripts.workflows inspect --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows steps --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows checkpoints --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows result --credential-file .cache/credentials/admin.json --job-id JOB_UUID
uv run --locked --all-packages python -m scripts.workflows cancel --credential-file .cache/credentials/admin.json --job-id JOB_UUID
```

Submit/create commands print identifiers/status, not sensitive instructions. Explicit inspect/result/artifact commands intentionally display authorized private data. Prompt contents, tool outputs and credentials are omitted from application/worker logs and audit events. Create a new version with `version --agent-id ... --agent-version CURRENT_VERSION --definition-file ...`; enable/disable one version with those actions. Disabling blocks new starts/steps but lets an already started valid step checkpoint; use cancellation to stop execution.

<a id="phase-06--repeatable-validation-and-process-interruption"></a>

### Repeatable validation and process interruption

Run tests and live acceptance serially. Do not reset `godfather_test` while running live smoke tests, even though the application database is separately named.

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
uv pip check
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_agent_runtime
```

The default acceptance starts its own ephemeral loopback model fixture and actual native worker processes. It provisions synthetic credentials/workspace/agent and completes all three steps normally. It then runs with a simulator-only barrier after checkpoint 1, stops that actual process, waits for coordinator-owned health/lease expiry, verifies retry, restarts the actual API and retains its artifact volume, and starts a new worker process with the same node credential. The new attempt restores checkpoint 1, skips the committed plan step and completes the two remaining steps. It verifies three unique completed step records, checkpoint versions 1/2/3, two attempts/higher fence, interruption/resume/completion history, stale old-session rejection and unchanged final results.

For the real already-installed local model:

```text
uv run --locked --all-packages python -m scripts.check_agent_runtime --ollama --model YOUR_EXACT_INSTALLED_MODEL
```

This performs the same normal and interrupted/recovered workflows through Ollama. It performs no model download, paid provider request, account access or system configuration change. The acceptance's node hardware advertisement remains explicitly simulated; a real model invocation establishes the local inference path, not simulated GPU performance. Use the normal worker command for physical capability discovery.

Evidence and synthetic output remain in ignored `.cache/phase06-runs/RUN_UUID/`. Every exit stops its own processes/server and attempts to cancel its own jobs and revoke its two credentials. Completed rows/artifacts remain for inspection. The `--pause-after-checkpoint N` worker flag is a documented, simulator-only fault-injection barrier, not a production workflow pause/approval feature. A new session must wait for the old one to become offline; no process inherits another live session or lease.

The CI OS matrix executes portable tests on Windows/macOS/Linux and Python 3.12/3.14 when run. The serial Linux container job now includes the native mock workflow/recovery acceptance. Configuring CI is not proof of executed remote results.

<a id="phase-06--validation-and-evidence"></a>

### Validation and evidence

The native mock demonstration passed in `.cache/phase06-runs/09c0c49e9ff9488484d02ae3f3307f0a/result.json`. Real Ollama `qwen3:8b` then passed both normal and interrupted/recovered demonstrations in `.cache/phase06-runs/075e70cacb1f4be7810f92f6d55a1beb/result.json`. Both had three committed steps, versions 1/2/3, no repeated committed plan step, actual process interruption/API restart, successful same-node recovery and rejected stale writes. The real plan belonged to the original attempt; the tool and summary belonged to the new attempt. No installation or download occurred. After the final compact-reference and definition-size changes, the native mock acceptance was repeated successfully against the rebuilt API: `.cache/phase06-runs/e394725e1774429dbc17cc6b541efa2c/result.json`. Cleanup succeeded, including stopping owned worker processes and revoking both synthetic credentials.

Final checks actually executed locally:

| Check                                       | Result                                                                                                                                                                                         |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python scripts/dev.py check`               | Passed: Ruff format (91 files), Ruff lint, strict mypy (65 source files), Windows pytest (141 passed, 92 database cases intentionally skipped), Prettier, ESLint, TypeScript and Next.js build |
| Rebuilt `api`, `api-test`, `migrate` images | Passed                                                                                                                                                                                         |
| Full PostgreSQL container pytest            | **233 passed, zero skipped** in 39.37 seconds; includes all 92 database cases, migration upgrade/downgrade/schema checks and 14 workflow integration cases                                     |
| `docker compose config --quiet`             | Passed                                                                                                                                                                                         |
| `uv pip check`                              | Passed: 45 installed packages compatible                                                                                                                                                       |
| `git diff --check`                          | Passed                                                                                                                                                                                         |

The workflow tests include artifact rollback/corruption, node grants, immutable versions, workspace isolation, malformed model output, cancellation during blocked inference, step deadlines, concurrent duplicate checkpoints, restart restoration, stale fencing and lease expiry during storage I/O. Unit tests also cover bounded definitions, compact/historical model references and refusing remote workflow configuration before discovery. Native acceptance evidence is additional to these deterministic tests. Physical OS/backend validation remains limited as described below.

<a id="phase-06--limitations-and-security-boundary"></a>

### Limitations and security boundary

- Sequential bounded JSON workflows only; no autonomous tools, parallel branches, multi-agent supervisors, visual engine, coding/WordPress/image agents or full dashboard.
- Only one node process executes a workflow attempt. Process recovery is same-node and requires an authenticated replacement session after lease/deadline expiry; compatible cross-node automatic failover remains Phase 07.
- Model output must satisfy the declared schema. Unsupported JSON-mode providers or malformed plans fail explicitly; there is no silent fallback or unvalidated tool execution.
- Only known, read-only, deterministic tools are allowed. Non-idempotent/external operations are rejected, so no uncertain external operation is automatically retried. Future support needs explicit approval/reconciliation design.
- Artifacts are immutable bounded JSON, not an unrestricted file ingestion API or cloud object store. Complete production retention, quota and backup/restore verification remain later phases.
- Physical macOS/Linux inference, CUDA/Metal/AMD execution, public/remote deployment and remote CI are not established by Windows native processes, Linux containers or OS mocks.
- The user-added BYOK requirement is preserved in `AGENTS.md` with its explicit planning-only boundary. No billing controls, native frontier providers, credential sharing or cloud failover have been implemented.

<a id="phase-06--files-changed"></a>

### Files changed

| Area              | Files                                                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Runtime           | `packages/agent-runtime/pyproject.toml`, `src/godfather_agent_runtime/{__init__,tools}.py`                                                                                              |
| Contracts         | `packages/shared-schemas/src/godfather_contracts/{__init__,execution,agents,jobs}.py`                                                                                                   |
| API/persistence   | `apps/api/pyproject.toml`, `src/godfather_api/{agents,artifacts,workflow_service,app,config,models,jobs,nodes,scheduler}.py`                                                            |
| Schema/storage    | `infrastructure/migrations/versions/0004_agent_runtime.py`, `infrastructure/docker/api.Dockerfile`, `compose.yaml`                                                                      |
| Worker/gateway    | `packages/worker/pyproject.toml`, `src/godfather_worker/{agents,cli,inference}.py`, `packages/model-gateway/src/godfather_model_gateway/{__init__,providers}.py`                        |
| Tools/tests       | `scripts/{workflow_demo,workflows,check_agent_runtime}.py`, `tests/{workflow_helpers,test_agent_runtime,test_model_gateway}.py`, `tests/integration/{test_workflows,test_inference}.py` |
| Workspace/CI/docs | `pyproject.toml`, `uv.lock`, `.github/workflows/checks.yml`, `AGENTS.md`, `README.md`, setup/security/compatibility/protocol docs, new architecture/ADR/runbook                         |

Stop after Phase 06. Phase 07 and BYOK implementation both require separate explicit authorization.

---

<a id="phase-07-08"></a>

<a id="phase-07-08--phase-0708-automatic-failover-and-local-command-center"></a>

## Phase 07–08: Automatic failover and local Command Center

Current authentication is documented in [Phase 09](phases.md#phase-09).
Google OIDC/application sessions replace human bearer login in normal operation;
worker machine credentials remain independent. Earlier bearer/simulator procedures
below are historical and restricted to isolated automated tests. Phase 09 does not
authorize public deployment or Phase 10.

The user explicitly authorized these phases as one combined milestone. Stop after
Phase 08. Phase 09 and BYOK implementation remain unapproved.

<a id="phase-07-08--prerequisites"></a>

### Prerequisites

Before implementation, repository checks passed and all 233 PostgreSQL-backed tests
passed. Phase 06's native mock acceptance verified process interruption, actual API
restart, durable checkpoint restoration, no repeated committed step and stale-write
rejection: `.cache/phase06-runs/1dfdfb17d06a4b9c916d9ea59dc3c3ec/result.json`.

Real Phase 05 `qwen3:8b` initially exhausted the acceptance command's default 32-token
budget before returning visible text. Revalidation with an explicit 2048-token
budget passed streaming, non-streaming and result durability across an actual API
restart: `.cache/phase05-runs/3431d11e4a744a80b46d749decfe295f/result.json`.
No model was downloaded, provider account accessed or billable inference enabled.

<a id="phase-07-08--recovery-and-portability"></a>

### Recovery and portability

See [ADR 0007](../decisions/0007-cross-node-recovery-and-local-command-center.md).
The scheduler expires/fences interrupted attempts and queues bounded retries. Any
compatible authorized available node can restore the pinned workflow and committed
JSON artifacts through existing fenced APIs. The original and recovery attempts are
linked permanently. If none qualifies, the job stays pending with its checkpoint.
OS/architecture/model/runtime/dependency/tool/resource requirements and both owners'
consent remain mandatory. Workflow `retry.limit` (0–10) and `backoff_seconds`
(0–3600) configure automatic recovery budgets; there is no unlimited retry policy.

Each committed checkpoint and every output in its prefix is verified against its
database identity, SHA-256, byte length and immutable workflow version. Invalid
storage/metadata pauses recovery as `REVIEW_REQUIRED`, preserving evidence and
preventing automatic replay. Cancel the job or perform a reviewed repair using
existing local storage/database authority; there is no force-resume UI.

The coordinator's existing private `artifacts-data` volume makes artifacts independent
of the failed worker. Keep it and PostgreSQL together. This phase neither copies
private host paths nor implements arbitrary repository workspaces. The test workflow
is coding-compatible read-only planning; real Git patches/worktrees remain Phase 11.
Unsupported side-effecting tools are rejected. Uncommitted model/read-only work can
repeat; committed steps cannot. Unsaved files, GPU state and interrupted external
side effects are not recoverable state.

<a id="phase-07-08--local-startup"></a>

### Local startup

Use the existing approved toolchain and ignored `.env`; preserve current passwords
and volumes. Windows uses Docker Desktop/WSL2 with a Linux engine. macOS/Linux use
the same Compose architecture. From the repository root:

```text
uv sync --locked --all-packages
npm ci
docker compose --profile tools build api api-test migrate dashboard
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

The additive migration head is `0005_cross_node_recovery`. It preserves identities,
jobs, historical attempts and artifacts. It adds recovery references, interrupted
attempt status and review metadata. Migrations remain explicit; readiness requires
the current head. Never reset the application database or delete volumes.

Open **http://127.0.0.1:3000**. API/readiness remain
**http://127.0.0.1:8000/api/v1** and **http://127.0.0.1:8000/health/ready**.
Both host ports remain bound to loopback; databases/inference are not public.
For native frontend hot reload, stop only the dashboard container, then `npm run dev`.
Its server defaults to the loopback API. Compose sets the internal API address.

Use an already provisioned administrator credential from the private credential
file created by [Phase 03 provisioning](phases.md#phase-03). Enter only its `token` value
in the local connection form. No account or credential is preseeded. The server
validates it against the API before setting an eight-hour HttpOnly, SameSite=Strict
cookie. Disconnect removes that cookie; provisioning revocation invalidates backend
access immediately. Native/container dashboards share no global admin credential.

<a id="phase-07-08--routes-and-integrations"></a>

### Routes and integrations

| Dashboard               | Behavior and API dependencies                                                                                                                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/`                     | Workspace selector; node/job/agent counts, reported resources, recent work/events/recovery; `/command-center` projection                                                        |
| `/nodes`, `/nodes/UUID` | Search/status filters, ownership/platform/hardware/model/tool inspection, visible workload/history; confirmed existing `/nodes/UUID/control` operations                         |
| `/jobs`, `/jobs/UUID`   | Submit pinned workflow or bounded synthetic job; progress, attempts/recovery origin, checkpoints/artifacts/result/errors; existing workflow/job APIs and confirmed cancel/retry |
| `/agents`               | Immutable versions, requirements, model selection, allowed tools, execution history and existing enable/disable API                                                             |
| `/models`               | Workspace-permitted provider-neutral deployments, context/estimates when known, recent per-node inference measurements                                                          |
| `/activity`             | Paged durable events filtered by node, user, job, agent, exact type, derived severity and time range                                                                            |

The same FastAPI monolith adds authenticated `GET /command-center`,
`/command-center/jobs/UUID`, `/command-center/nodes/UUID`, `/command-center/agents/UUID`, `/command-center/events`
and `POST /jobs/UUID/retry`. There is no second backend or scheduler. These API paths
are under `/api/v1`; the browser's `/api/control` bridge permits only reviewed
operations and never returns the bearer credential in a JSON response.

Tables/events are bounded at 100 rows with paging. Summary counts cover their full
scope. Node history shows the latest 100 visible jobs; job detail shows the latest
100 events, with the full paged history in Activity. Simulated telemetry is labeled
and excluded from physical utilization. Unknown values are distinct from zero.
Model performance is sampled per node from up to 200 recent inference attempts,
not an invented benchmark. Agent availability means a compatible online report,
not guaranteed immediate execution. Times display in the browser's local timezone.
Polling runs sequentially every three seconds while visible; failed refreshes show
a stale/error state. Destructive controls use keyboard-accessible confirmation dialogs.

Manual retry is limited to eligible failed jobs with classified transient/lease/time
errors. It preserves attempts/checkpoints and enforces a maximum of eleven total
attempts. It cannot revive cancelled/successful jobs, override review, clear tool
restrictions or retry unsupported external effects.

<a id="phase-07-08--combined-browser-demonstration"></a>

### Combined browser demonstration

Run database-reset integration tests and live acceptance **serially**:

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_command_center
```

The browser acceptance needs an already approved Playwright installation and browser.
It first resolves `playwright`, then the existing ignored
`.tools/browser/node_modules/playwright`. `GODFATHER_PLAYWRIGHT_MODULE` may identify
an existing module path. On Windows it uses installed Edge; elsewhere it uses an
existing Playwright Chromium. It does not install a browser or service automatically.

The harness creates only synthetic identities/workspace and independent worker
credentials. It explicitly grants the Vegas owner membership in that new synthetic
workspace using local database authority; the primary worker independently advertises
both owner/workspace allowlists. It starts a loopback model fixture and two native
simulated workers. The browser signs in, verifies registrations, submits the workflow,
waits for checkpoint 1, then signals the harness to terminate only its primary child.
It observes offline health, reassignment, checkpoint restoration and completion,
inspects linked attempts/history, tests confirmed drain/enable, and opens agent/model/
audit views. The original node reconnects and its old attempt is explicitly rejected.
Light/dark/narrow screenshots and JSON evidence stay under ignored
`.cache/phase07-08-runs/RUN_UUID/`. All exits stop owned processes and revoke owned
credentials; synthetic rows/artifacts remain for review. No private accounts are used.

<a id="phase-07-08--security-limits-and-future-work"></a>

### Security limits and future work

This is trusted local development with minimum existing credential/workspace
authorization, not a production browser identity system. Do not publish it or proxy
it remotely. Phase 09 must add production sessions, contributor/member RBAC and the
remaining authentication/authorization UX. Before remote/public use also require
TLS, rate limits, production secret management, audit/backup verification and
separate deployment approval. Owner host/tool/filesystem restrictions cannot be
overridden by platform administration.

No BYOK credentials/billing, unrestricted code/shell, WordPress/WooCommerce writes,
VPS deployment, DNS changes, cloud object storage or Kubernetes is implemented.
Physical macOS/Linux and GPU inference remain unverified by simulations. Production
retention, storage repair tooling, backup/restore and capacity optimization remain
later milestones. Layout/theme controls are local presentation preferences; advanced
saved per-user layouts remain future work.

<a id="phase-07-08--validation-results"></a>

### Validation results

| Check                                     | Executed result                                                                                                                                                                                                   |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python formatting / lint / strict typing  | Ruff: 99 formatted files and clean lint; mypy: 70 source files clean                                                                                                                                              |
| Native Windows pytest                     | 141 passed; 113 PostgreSQL cases intentionally skipped in this environment                                                                                                                                        |
| Full PostgreSQL container pytest          | **254 passed, zero skipped**, 47.89 seconds; all earlier phase regressions plus 21 new dashboard/failover cases                                                                                                   |
| Frontend checks                           | Prettier, ESLint, strict TypeScript, five component/security tests and production Next.js build passed                                                                                                            |
| Local container builds/startup            | API, API-test, migrate and dashboard images built; migration applied; loopback API/dashboard healthy                                                                                                              |
| Configuration / dependency / patch checks | `docker compose config --quiet`, `uv pip check` (45 compatible packages) and `git diff --check` passed                                                                                                            |
| Browser failover                          | Passed: real browser submission, native primary process termination, offline status, cross-owner Windows-to-macOS simulation, checkpoint restore/completion, stale reconnect rejection and confirmed drain/enable |
| Visual verification                       | Desktop light and mobile dark screenshots inspected; no horizontal page overflow; browser page-error list empty                                                                                                   |

The first combined browser acceptance passed with evidence at
`.cache/phase07-08-runs/1cfaf8e9e11342c591db70a952182644/result.json` and
`browser-result.json`, plus checkpoint/offline/recovered-job/layout screenshots.
The final images also passed the complete acceptance at
`.cache/phase07-08-runs/32a1434c049d4a649d4564b3a5c80ad6/result.json` and
`browser-result.json`. Both runs completed cleanup: owned processes stopped and all
four synthetic credentials revoked. The final repository check log is
`.cache/phase07-08-final-check.log`.
Mock local inference in this demonstration is explicitly separate from the real
Ollama prerequisite evidence above. Remote CI and physical macOS/Linux/GPU tests
were not executed in this session.

<a id="phase-07-08--files-changed"></a>

### Files changed

| Area                             | Files                                                                                                                                                                                                                                                                              |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API / recovery                   | `apps/api/src/godfather_api/{agents,app,command_center,jobs,models,scheduler,workflow_service}.py`                                                                                                                                                                                 |
| Schema / contracts               | `infrastructure/migrations/versions/0005_cross_node_recovery.py`, `packages/shared-schemas/src/godfather_contracts/jobs.py`                                                                                                                                                        |
| Dashboard routes                 | `apps/dashboard/src/app/{page,layout}.tsx`, `globals.css`, `[section]/page.tsx`, `jobs/[id]/page.tsx`, `nodes/[id]/page.tsx`, `api/control/[...path]/route.ts`, `api/session/route.ts`                                                                                             |
| Dashboard components / contracts | `apps/dashboard/src/components/{command-center,operational}.tsx`, `apps/dashboard/src/lib/{contracts,control-server}.ts`                                                                                                                                                           |
| Validation / tooling             | `scripts/{check_command_center,dev}.py`, `tests/dashboard-components.cjs`, `tests/e2e/command-center.cjs`, `tests/integration/{test_command_center,test_failover,test_workflows}.py`                                                                                               |
| Local configuration / CI         | `compose.yaml`, `package.json`, `.github/workflows/checks.yml`                                                                                                                                                                                                                     |
| Documentation                    | `README.md`, `docs/operations/{setup,phase-07-08}.md`, `docs/architecture/{agent-runtime,compatibility,security-foundation}.md`, `docs/protocols/agents-v1.md`, `docs/design/phase-07-08-command-center.md`, `docs/decisions/0007-cross-node-recovery-and-local-command-center.md` |

No third-party runtime dependency was added. The browser acceptance uses the already
available Playwright installation; component tests use the existing TypeScript
compiler, React renderer and Node test runner.

---

<a id="phase-09-integration"></a>

<a id="phase-09-integration--phase-09-real-integration-verification---2026-10-16"></a>

## Phase 09 real integration verification - 2026-10-16

Implementation is limited to Phase 09. Real Google authentication acceptance is
**incomplete** because the operator confirmed no OAuth client is configured.
No Google Cloud project/client, external account, DNS, Droplet or public service
was configured or deployed. No model was downloaded or inference runtime installed.

<a id="phase-09-integration--evidence-boundaries"></a>

### Evidence boundaries

Before changes, the existing repository checks and **254 PostgreSQL-backed tests**
passed, including registration/health, job lifecycle, models/agents, migrations,
durable workflow checkpoints and cross-node failover/fencing. There was no Phase 09
password subsystem to migrate. Existing provisioned human bearer login was replaced
with Google OIDC/application sessions; existing UUIDs and ownership remain intact.

Automated OIDC tests use signed fixture ID tokens and mock only Google's HTTP
responses. Authlib's actual code exchange/PKCE/token validation runs. This is
automated-test evidence, not evidence of a successful Google account login.
Test-mode authentication is refused against any database except `godfather_test`.

The browser test uses actual Next.js, FastAPI and PostgreSQL with independently
authenticated application sessions for two administrators and a contributor.
Google alone is mocked inside the isolated automated-test server/browser. An
actual native Windows worker discovers its hardware and the already-installed
`qwen3:8b` Ollama model, registers through its machine protocol, executes a
read-only workflow, commits a checkpoint/artifact/result and reports real health.
No operational API response is mocked. Test accounts/agents/jobs exist only in
the explicitly disposable test database, never in the normal application database.

Successful complete browser evidence:
`.cache/phase09-runs/65f5f8877ccb423691eb87b565bd00fc/browser-result.json`.
The earlier successful run with real cross-user execution denial and cancellation
is `.cache/phase09-runs/10ed180bf7924b59be3a03fb469d7558/browser-result.json`.
Each directory contains API/dashboard/worker/browser logs plus inspected node,
completed-job and loaded administration desktop/mobile screenshots. The final
browser run also visited the real agent, installed-model and activity screens.
Owned test processes/container were stopped and the tested worker credential
was revoked; reconnection returned 401. These paths are ignored, private evidence.

<a id="phase-09-integration--feature-to-api-and-persisted-state-map"></a>

### Feature to API and persisted-state map

All API paths below have prefix `/api/v1`. Browser calls go through the allowlisted
same-origin `/api/control` or `/api/auth` bridge. The table distinguishes actual
backend integration from the pending external Google acceptance.

| Dashboard feature                                           | Actual backend API                                                                                     | Authoritative persisted source                                                                       | Verification                                                                                                                            |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Google sign-in / invitation admission                       | `POST /auth/start`, `GET /auth/callback`                                                               | `login_transactions`, `invitations`, `google_identities`, `users`, `authentication_limits`, `events` | Signed mocked-provider integration and browser passed; real Google pending                                                              |
| Current account / platform roles                            | `GET /auth/me`                                                                                         | `users`, `google_identities`, `human_sessions`                                                       | Real backend account display and independent sessions verified                                                                          |
| Logout / all-session revocation                             | `POST /auth/logout`, `/auth/sessions/revoke`                                                           | `human_sessions`, `events`                                                                           | API and browser verified; prior session requests return 401                                                                             |
| Users, role/account status, admin recovery                  | `GET/POST /administration/users...`                                                                    | `users`, `human_sessions`, `events`                                                                  | PostgreSQL tests cover role denial, account disabling, equal admins and last-admin protection; loaded UI verified                       |
| Invitations / revocation                                    | `GET/POST /administration/invitations...`                                                              | `invitations`, `events`                                                                              | Actual creation/activation/listing and expiry/reuse/revocation tests; UI shows persisted states                                         |
| Workspace selector / private/shared membership              | `GET /command-center`, `/administration/workspaces/{id}/members`; workspace create/member/policy POSTs | `workspaces`, `workspace_members`, model/tool allowlists, `events`                                   | Browser and PostgreSQL isolation/grant/policy tests; other administrator receives 404 for private workspace                             |
| Owned worker credentials                                    | `GET/POST /administration/node-credentials`, `POST /administration/node-credentials/{id}/revoke`       | `access_credentials` digest/owner/revocation, `events`                                               | New owner-only APIs tested, including pre-registration revocation and other-owner denial; secrets appear only on creation               |
| Node inventory / health / hardware                          | `GET /command-center`, `/nodes`, `/command-center/nodes/{id}`; machine registration/heartbeat          | `nodes`, `node_capabilities`, `capabilities`, `access_credentials`                                   | Actual Windows worker online/status and physical-source CPU/RAM reports rendered; no fabricated GPU data                                |
| Node drain / disable / enable / revoke                      | `POST /nodes/{id}/control`                                                                             | `nodes`, `access_credentials`, `events`                                                              | PostgreSQL lifecycle tests; real browser-path credential revocation and reconnect denial; other admin cannot override owner             |
| Jobs / submit / status / attempts                           | `POST /workflow/jobs`, `GET /command-center/jobs/{id}`, `/jobs/{id}/attempts`                          | `jobs`, `attempts`, `events`                                                                         | Real browser submission and actual local model execution; shared access requires explicit membership                                    |
| Job cancellation / safe manual retry                        | `POST /jobs/{id}/cancel`, `/jobs/{id}/retry`                                                           | `jobs`, `attempts`, `events`, workflow state                                                         | Real queued cancellation verified; retry eligibility/denial persisted-path regressions passed; running cancellation concurrency covered |
| Checkpoints / artifacts / results                           | `/workflow/jobs/{id}...`, `/command-center/jobs/{id}`                                                  | `workflow_runs`, `workflow_steps`, `checkpoints`, `artifacts` plus private immutable artifact store  | Real committed checkpoint/output read through authorized API; cross-workspace artifact protections covered by PostgreSQL regressions    |
| Agents / immutable configuration / enable-disable / history | `/agents...`, `/command-center/agents/{id}`, `/command-center?section=agents`                          | `agents`, jobs/attempts/workflow-step records and events                                             | Real agent created through authorized API, selected/executed in UI; screen and existing mutation/version/isolation tests verified       |
| Installed models / availability / observed metrics          | `/models`, `/inference/metrics`, `/command-center?section=models`                                      | Worker-reported `nodes.runtimes`; `attempts.result` and workflow-step usage                          | Actual installed Ollama discovery and scoped screen verified; absent observations remain unavailable                                    |
| Operational and security audit                              | `/command-center/events`, `/administration/audit`                                                      | Append-only-through-API `events` with actor, scope, time, target/outcome and correlation             | Real login/invitation/permission/node/job events verified and rendered; inaccessible private grant IDs redacted                         |

The physical worker test verifies existing Windows discovery, not accelerator parity
or physical macOS/Linux execution. Unknown GPU/VRAM/utilization observations remain
explicitly unavailable; no synthetic numeric values were used to fill those gaps.

<a id="phase-09-integration--executed-checks"></a>

### Executed checks

| Check                                             | Executed result                                                                                                                                                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Python formatting / lint / strict typing          | Ruff: 113 files formatted, clean lint; mypy: 80 source files clean                                                                                                                                           |
| Native Windows pytest                             | **148 passed**, 138 PostgreSQL cases skipped only in the native environment                                                                                                                                  |
| Complete PostgreSQL container pytest              | **286 passed, zero skipped**, 71.00 seconds                                                                                                                                                                  |
| Frontend                                          | Prettier, ESLint, strict TypeScript, seven component/security tests and production Next.js build passed                                                                                                      |
| Targeted deterministic cancellation tests         | Both node-lock/audit concurrency and blocked-provider cancellation passed together                                                                                                                           |
| Browser with actual Windows worker / local Ollama | Passed; two admins, contributor, denied outsider, real model/workflow/checkpoint/artifact, shared/private scope, owner execution denial, cancellation, credential reconnect denial, audit, logout/revoke-all |
| Visual checks                                     | Loaded desktop light and mobile dark administration screenshots inspected; no horizontal page overflow                                                                                                       |
| Final local images / startup                      | API, migrate and dashboard images built; additive `0006_google_identity` applied; API/dashboard healthy after restart                                                                                        |
| Normal application database preservation          | Before/after counts and identity/node/workspace/membership fingerprints matched exactly; jobs retained                                                                                                       |
| Normal local login                                | Browser verified truthful Google-not-configured state at `http://127.0.0.1:3000`; unauthenticated operational bridge returns 401                                                                             |
| Configuration / dependencies / patch              | Compose validation, 50-package dependency compatibility and Git whitespace checks passed                                                                                                                     |
| Real Google / remote / physical other platforms   | **Not executed**; Google client not configured, no external deployment, no physical macOS/Linux/GPU acceptance claimed                                                                                       |

The complete repository check log is `.cache/phase09-final-check.log`; image build log is
`.cache/phase09-final-build.log`. PostgreSQL tests exercise migration upgrade,
downgrade, metadata consistency and API restart persistence only in `godfather_test`.

During the final regression run a cancellation/audit lock cycle was exposed.
Worker node locks now use `FOR NO KEY UPDATE`, preserving mutation serialization
while allowing cancellation-event foreign-key checks. A deterministic event-barrier
test and the original blocked-provider cancellation test passed together. This
change preserves job leases, fencing, stale-worker rejection and owner authorization.
Normal local migration evidence is `.cache/phase09-before-migration.json` and
`.cache/phase09-after-migration.json`; these contain counts and fingerprints, not
raw identities or credentials. The normal login screenshot is
`.cache/phase09-unconfigured-local.png`. No first-admin or test account was created
in the normal application database during this implementation.

<a id="phase-09-integration--remaining-mocks-unavailable-features-and-security-limitations"></a>

### Remaining mocks, unavailable features and security limitations

There are **no production-facing fixture responses, hardcoded accounts, fake
sessions or seeded operational records** in the new code. Google HTTP/token fixtures
exist only under `tests/` and the guarded automated test server. Legacy synthetic
workspaces/history are retained, not deleted; unlinked identities and simulated
nodes are excluded from normal operational use. Synthetic job creation and simulated
registration are restricted to isolated test mode. Historical bearer/simulator live
smoke scripts are marked superseded and cannot provision human login normally.

Every enabled dashboard action uses a real backend operation. Theme changes are
presentation state only. Unsupported telemetry is unavailable. Scheduler timing
remains environment configuration; there is no pretend scheduler-settings save
operation. Agent creation/versioning uses the existing real API; no visual workflow
builder is added. BYOK key enrollment/sharing/billing, paid routing, production MCP
writes, sensitive-tool approval execution, arbitrary shell/coding and Phase 10
deployment remain unavailable and are not represented as implemented controls.

Real Google login/setup, founding-account migration, external TLS/proxy/network
validation, production secret rotation, audit retention and backup/restore review
remain prerequisites before public exposure. Legacy workspace NULL model/tool
policies intentionally preserve earlier local grants; owners should review and
configure explicit allowlists. Email conflicts fail closed and require reviewed
operator resolution. Database operators remain trusted; cryptographic audit
immutability is not claimed. No full repository security scan or physical
macOS/Linux/GPU acceptance is claimed by this implementation.

<a id="phase-09-integration--changed-files"></a>

### Changed files

- Identity and configuration: `apps/api/pyproject.toml`, `uv.lock`, `.env.example`,
  `compose.yaml`, `apps/api/src/godfather_api/{authentication,administration,identity,models,config,database,app}.py`,
  `infrastructure/migrations/versions/0006_google_identity.py`.
- Existing protected operations: `apps/api/src/godfather_api/{nodes,jobs,agents,inference,command_center,scheduler,provision}.py`.
- Dashboard: authentication route under `apps/dashboard/src/app/api/auth/[action]/`,
  administration route, protected section/job/node routes, home, global styles,
  `components/{administration,google-login,command-center,operational}.tsx`,
  `lib/{control-server,contracts}.ts`; legacy `api/session/route.ts` removed.
- Validation: `tests/{oidc_provider,test_authentication}.py`,
  `tests/integration/{test_authentication,test_jobs}.py`, `tests/dashboard-components.cjs`,
  `tests/e2e/{__init__,auth_server}.py`, `tests/e2e/google-auth.cjs`,
  `scripts/check_google_oidc.py`.
- Documentation: README, setup, authentication architecture, ADR 0008, Phase 09
  design/operations/integration reports, and historical-authentication notices in
  security foundation, Phase 03/07-08 and job/agent/inference protocols.

Stop after Phase 09. Completion of this implementation does not authorize Phase 10.

---

<a id="phase-09"></a>

<a id="phase-09--phase-09-google-authentication-setup-migration-and-verification"></a>

## Phase 09: Google authentication setup, migration and verification

Scope: human Google OIDC, revocable application sessions, multi-role administration,
invitation-only onboarding, workspace isolation, independent node ownership and
durable auditing. Phase 10, external deployment, paid frontier integration and
production system changes are not authorized. See [authentication architecture](../architecture/authentication.md)
and [ADR 0008](../decisions/0008-google-oidc-and-owner-authorization.md).

<a id="phase-09--google-cloud-setup--operator-action-not-performed-by-codex"></a>

### Google Cloud setup — operator action, not performed by Codex

Use a Google Cloud project controlled by the platform operators. In Google Auth
Platform configure Branding, Audience and Clients. Create an OAuth client of type
**Web application**. Request only `openid`, `email`, `profile`; Gmail/Drive APIs and
Google access/refresh-token storage are unnecessary. During Google's testing mode,
add the invited accounts as Google test users if required by the project's audience.
Google test-user approval does not bypass Godfather invitations.

Prefer separate OAuth clients for development and production. Register exact redirect
URIs, with no trailing slash:

| Environment               | Application origin             | Authorized redirect URI                          |
| ------------------------- | ------------------------------ | ------------------------------------------------ |
| Windows/macOS/Linux local | `http://127.0.0.1:3000`        | `http://127.0.0.1:3000/api/auth/callback`        |
| Optional localhost local  | `http://localhost:3000`        | `http://localhost:3000/api/auth/callback`        |
| Planned production        | `https://app.the-godfather.ai` | `https://app.the-godfather.ai/api/auth/callback` |

Use one exact origin consistently in browser, API and dashboard configuration;
localhost and 127.0.0.1 have different cookies. The callback is on the dashboard,
not `api.the-godfather.ai`. Do not use wildcard redirects. This server flow does
not require a Google JavaScript SDK or additional Google API permissions. Consult
[Google's current setup and OIDC reference](https://developers.google.com/identity/openid-connect/openid-connect).
Production names remain proposed; this document does not verify registration,
DNS, domain ownership, TLS or hosting readiness.

<a id="phase-09--configuration"></a>

### Configuration

Set the following only in ignored local environment configuration or a secure
deployment secret store. Never paste the client secret into chat, logs or Git.

| Variable                             | Meaning                                                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `GODFATHER_GOOGLE_CLIENT_ID`         | Google Web client ID; API only                                                                          |
| `GODFATHER_GOOGLE_CLIENT_SECRET`     | Google Web client secret; API only                                                                      |
| `GODFATHER_WEB_ORIGIN`               | Exact application origin; API and dashboard                                                             |
| `GODFATHER_API_URL`                  | Dashboard server's backend address; defaults to `http://127.0.0.1:8000`, Compose uses `http://api:8000` |
| `GODFATHER_GOOGLE_BOOTSTRAP_SUBJECT` | Optional legacy additional subject pin; leave blank for normal founder setup                            |
| `GODFATHER_GOOGLE_BOOTSTRAP_EMAIL`   | One exact founder Google email; verified by normal server-side Google sign-in                           |
| `GODFATHER_SESSION_SECONDS`          | API session lifetime, 300–86400 seconds; default 28800                                                  |
| `GODFATHER_AUTHENTICATION_LIMIT`     | API auth start/callback requests per direct peer/action/minute; default 20                              |
| `GODFATHER_ENVIRONMENT`              | `local`, `test`, or `production` for API configuration                                                  |

Compose forwards the Google and web-origin configuration from the ignored root
`.env`. Optional session/rate settings can be supplied explicitly in the API
environment. Native Next.js reads its process environment or ignored
`apps/dashboard/.env.local`; it does not automatically read the repository root
`.env`. Never prefix OAuth secrets with `NEXT_PUBLIC_`. The dashboard receives no
Google client secret. Missing client configuration produces an honest unavailable
login state and grants no access.

For production configuration, use the separate production client, planned HTTPS
origin, `GODFATHER_ENVIRONMENT=production` and a private backend URL or the reviewed
HTTPS API address. Startup rejects missing Google configuration, nonproduction
web origins and legacy-test credential mode. Secure cookies are derived from the
exact HTTPS origin. Production TLS, private networking, secret rotation, proxy
trust and deployment remain separately authorized Phase 10 work. Existing Compose
continues publishing only loopback API/UI ports and no database/inference ports.

<a id="phase-09--bootstrap-and-ownership-preserving-migration"></a>

### Bootstrap and ownership-preserving migration

On a fresh database, configure only `GODFATHER_GOOGLE_BOOTSTRAP_EMAIL` with the
founder's exact Google email and leave the optional subject setting blank. Apply
`0007_founder_bootstrap` explicitly when rollout is authorized, then choose
**Continue with Google**, without an invitation. No ID-token extraction or
identity-verification script is required. The normal callback verifies Google's
signature, issuer, audience, expiry, nonce and PKCE exchange, requires the boolean
`email_verified=true`, and compares the verified email with the allowlist.

Successful bootstrap persists Google's stable `sub`, creates the platform
administrator, session and audit records, and permanently closes bootstrap in one
transaction. A concurrent or later different identity cannot become another
founder. Remove the allowlist afterward as configuration hygiene; closure remains
enforced even if it is retained or changed. No account is created at startup.
See the [founder operator checklist](../operations/founder-bootstrap.md). Existing subject
configuration remains an optional additional restriction for compatibility.

Existing Phase 03–08 users keep their UUIDs and owned resources. If any legacy
administrator exists, bootstrap intentionally refuses to create an unrelated
replacement administrator. With local database authority, identify the existing
real user's UUID from your private records and bind its verified Google subject:

```text
docker compose exec -T api python -m godfather_api.identity link --user-id EXISTING_USER_UUID --subject VERIFIED_GOOGLE_SUB
```

Run only after backing up the database/artifact volume with the existing authorized
backup procedure. The command never matches/merges accounts by email and never
copies node data. It preserves UUIDs, roles, nodes, workspaces, jobs and audit
history, revokes legacy human credentials/sessions, and leaves machine credentials
independent. Existing subject replacement requires `--replace` and fresh operator
identity verification. Successful Google login updates profile/contact data.
Email uniqueness conflicts fail closed; resolve them with reviewed database
administration rather than silently merging identities. Synthetic historical
accounts should remain unlinked and are not usable human login accounts.

After migration, run:

```text
uv sync --locked --all-packages
npm ci
docker compose --profile tools build api migrate dashboard
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Migrations are explicit; never reset application volumes. The head is
`0007_founder_bootstrap`. This additive migration closes bootstrap for existing
administrators or Google identities and preserves their records. For native frontend development, use the same documented
origin and API URL and avoid running two dashboards on port 3000.

<a id="phase-09--invitations-administration-and-recovery"></a>

### Invitations, administration and recovery

In **Account / Administration**, create an invitation for the second founder's
Google email with role **platform administrator**. No email is sent automatically.
Use **Copy sign-in instructions** on the invitation row and share them privately.
The recipient opens the Command Center and selects **Continue with Google** using
the exact invited Google email; no code is required. Exactly one active, unused,
unexpired invitation must match the verified email. Tailscale membership and Google
OAuth test-user settings are separate. Both receive identical platform privileges. Future invitations
can grant multiple contributor/member/administrator roles without account-count
or location limits. Invitations expire in 1–168 hours and can be revoked. Only
token digests appear in the database; lists/audit never return the original token.

Workspace owners create private workspaces and explicitly add member/admin UUIDs.
They grant exact installed model identifiers and supported `name@version` tools in
the execution policy; empty lists deny use. Legacy NULL policies preserve the prior
local read-only authorization, and owners should review/configure explicit lists.
Agent selection still requires an existing registered agent and compatible worker.
Shared platform administration never grants private workspace access.

Node owners create an independent worker credential in the same screen. Save its
one-time response in an owner-private file, adding `"kind": "worker"` for the
existing worker CLI. Configure allowed tools, model configuration, owner/workspace
allowlists, scheduling policy and resource capacity on that owner's worker using
the [existing worker contract](phases.md#phase-03). Revocation and drain/disable controls
are on node detail. Another administrator cannot enable, revoke or change that
node's contribution. Roles cannot grant another owner's host/filesystem access.
The owned credential inventory also supports revocation before a worker has ever
registered. Existing workers retain their machine tokens, but normal reconnect
requires their owner to complete explicit Google identity linking first.

For normal account recovery, the user recovers their Google account through Google;
there is no application password/reset token. A second platform administrator can
reenable an account, restore appropriate roles and revoke its sessions. If all
administrators are locked out, local database authority can run:

```text
docker compose exec -T api python -m godfather_api.identity recover --user-id EXISTING_USER_UUID
```

This reenables that existing account, revokes sessions and audits the offline
operation. It does not silently promote a member. At least one enabled platform
administrator must remain; ordinary HTTP operations cannot remove the last one.
If a Google identity changes, use the explicitly reviewed `identity link --replace`
procedure, preserving the same application UUID and ownership records.

<a id="phase-09--automated-validation-and-real-google-acceptance"></a>

### Automated validation and real Google acceptance

Run tests serially because disposable PostgreSQL suites exercise migrations/resets:

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose --profile tools build api-test
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_google_oidc --model EXACT_INSTALLED_MODEL
```

The OIDC integration tests mock only Google HTTP responses and sign fixture ID
tokens with the maintained JOSE library, so Authlib verification actually runs.
Negative cases cover signature/issuer/audience/expiry/nonce, state/browser binding,
PKCE verifier, invitation denial/expiry/revocation/reuse, independent roles,
workspace isolation, worker impersonation/revocation, session revocation and CSRF.

The browser harness resets **only** guarded `godfather_test`, starts an owned test
API container on loopback 8009 and Next.js on loopback 3010, intercepts Google
authorization only inside Playwright, and runs a real physical Windows worker
against an already-installed loopback Ollama model. It does not download models,
install browsers or alter the application database. Logs/screenshots/evidence are
under ignored `.cache/phase09-runs/UUID/`. It stops only its own processes/container.
These are automated-test identities, never seeded into the normal Command Center.
Historical Phase 03–08 live-database bearer/simulator smoke scripts are superseded;
normal admin credential provisioning and simulated-worker registration are refused.

**Real Google login acceptance is pending**: no Google OAuth client is configured.
After operator setup, perform the user's full acceptance in the normal local stack:
bootstrap/link the first verified Google administrator; invite and independently
log in the second administrator; onboard an actual owned worker; submit a real
workflow and inspect PostgreSQL-backed result/checkpoints/artifacts; explicitly
share its workspace with the second administrator; prove a separate private
workspace remains inaccessible; prove node-owner grants prevent unauthorized
execution; invite a contributor and verify platform operations are forbidden;
revoke the worker credential and confirm registration returns 401; inspect real
audit history; verify logout/revoke-all/account-disable and an uninvited Google
account denial. Inspect cookies for HttpOnly/SameSite/Secure as applicable and
confirm no Google tokens exist in browser storage. Capture sanitized evidence.
If a worker/model is unavailable, record the affected steps incomplete.

See [real integration verification](phases.md#phase-09-integration) for executed results,
remaining limitations and the operational feature/API/persistence map. No Phase 10
work or external Google Cloud configuration is part of this implementation.

---

<a id="phase-11-deployment-2026-10-20"></a>

<a id="phase-11-deployment-2026-10-20--phase-11-deployment-verification---2026-10-20"></a>

## Phase 11 deployment verification - 2026-10-20

The user explicitly approved SSH access to the existing production host and
deployment of the reviewed candidate. The established source-free installer
upgraded `0.1.0-rc.7` to **`0.2.0-rc.4`**, source revision
`538df376740632faf806d8bb6a832c2cd7cdb5ef`. The separate documentation commit
recording this result is not the deployed application revision.

<a id="phase-11-deployment-2026-10-20--executed-production-checks"></a>

### Executed production checks

- The transferred archive matched trusted local SHA-256
  `a03ab4fc92f51562d79507de4ad22e3daccdfe136175cb974ea54304a328a85d`;
  packaged-file checksums and production configuration validation passed.
- Proxy routing and Compose configuration matched the previous release. No DNS,
  Google Cloud configuration, production credential or host policy was changed.
- The installer took a quiesced, paired database/artifact backup before migration.
  Backup checksums, `pg_restore --list` and compressed artifact integrity passed.
  The existing PostgreSQL image and persistent volumes were retained.
- Migration advanced from `0007_founder_bootstrap` to
  `0009_provider_connections`. API, dashboard, proxy, PostgreSQL and Redis became
  healthy; current/previous links identify the new and old release respectively.
- Before/after user, node-owner and worker-credential fingerprints matched.
  Existing user/node/workspace/job/credential counts matched. The production
  environment file checksum and private permissions were preserved.
- The existing Windows worker reconnected and returned online. Existing
  authenticated browser requests continued succeeding after the upgrade.
- Real HTTPS returned 200 with normal certificate validation. The direct public
  API health path returned 404 and public worker registration returned 403.
- Headless browser acceptance verified the live login shell, anonymous dashboard
  and provider-connection API denial, real Google authorization redirect, exact
  callback, `openid email profile` scopes and PKCE S256, with no page errors.
- Runtime metadata reports `0.2.0-rc.4`, the exact revision above, build time
  `2026-10-20T23:39:12.681703+00:00` and environment `production`. The user
  refreshed their signed-in Command Center and confirmed the footer version and
  existing job results. This was user-assisted authenticated UI acceptance.

Private deployment logs, backup location and machine-specific fingerprints remain
in ignored operator evidence under `.cache/phase11-deployment`; production data
and secrets are not included in this document or Git.

<a id="phase-11-deployment-2026-10-20--remaining-acceptance"></a>

### Remaining acceptance

The packaged Windows worker completed real local Ollama/Git/container coding
acceptance before deployment. A coding task through the live coordinator has not
been executed: it needs the updated worker and owner-approved repository/model/
command configuration. The existing worker was left operational without replacing
its installation or changing owner contribution permissions.

No provider connection or key was added in production, and no paid API call was
performed. Real OpenAI/Anthropic acceptance needs owner-local credentials and
explicit spending authorization. Physical macOS/Linux inference and a fresh
automated Google account sign-in were not tested. The computer-use launcher failed;
the public browser checks used the existing Playwright fallback, while signed-in
version/results were confirmed directly by the user.

GitHub checks passed for the deployed application revision, including Python and
dashboard matrices on Windows/macOS/Linux, PostgreSQL tests and historical
process/recovery probes. See [local validation](phases.md#phase-11-validation-2026-10-20).
No later milestone was started.

---

<a id="phase-11-validation-2026-10-20"></a>

<a id="phase-11-validation-2026-10-20--phase-11-local-validation---2026-10-20"></a>

## Phase 11 local validation - 2026-10-20

Scope: the explicitly authorized coding/frontier/results assignment. Google login,
node identity and provider API credentials remain independent. No real frontier
key was supplied, no paid inference was performed and no production data was used.

<a id="phase-11-validation-2026-10-20--implemented"></a>

### Implemented

- Independent owner/node-bound provider connections, private/approval/limited
  policies, revocation, scoped grants, integer micro-USD reservations and usage.
  Secrets remain in worker-local OS stores; the coordinator has no key-upload API.
- Native OpenAI Responses and Anthropic Messages adapters with bounded streaming,
  structured-output/tool-call contracts, safe errors and provider token usage.
  Unsupported cache-pricing categories retain accounting liabilities for review.
- A single coding step in the existing runtime: approved committed Git snapshots,
  literal code search, validated file edits, actual Git diffs and owner-approved
  tests/build commands in a restricted local Linux container. Original repositories
  are preserved; interrupted commands require review and late writes are fenced.
- Answer-first results, safe Markdown, highlighted code/diffs, readable JSON,
  tables/charts and supported document/media envelopes, copy/download controls,
  partial/error states and expandable technical history. No new image/report
  generation subsystem or arbitrary remote media loading is implied.
- Provider Connections, agent connection/model selection, explicit paid-run
  consent, local-only ordered fallback, provider activity/audit integration and
  runtime release metadata in the status bar.
- Additive migration `0009_provider_connections`. Existing identity, job, worker
  ownership and production volumes are not replaced by this migration.

<a id="phase-11-validation-2026-10-20--executed-checks"></a>

### Executed checks

| Validation                                                         | Actual result                                                                                                    |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Full PostgreSQL-enabled suite, disposable `godfather_test`         | 403 passed, 3 skipped                                                                                            |
| Full native Windows suite with actual Git/container checks enabled | 224 passed, 182 database-only skips                                                                              |
| Frontend component tests                                           | 12 passed                                                                                                        |
| Ruff formatting/lint and strict mypy                               | Passed                                                                                                           |
| Dashboard formatting, ESLint, TypeScript and production build      | Passed                                                                                                           |
| Native container coding fixture                                    | Real Git diff and actual passing test; original preserved                                                        |
| Sandbox boundary probe                                             | Host secret environment absent, host snapshot read-only, no external route, test writes disposable               |
| Credential store contract mocks                                    | Windows/macOS/Linux namespaces and fail-closed unavailable store verified                                        |
| Authenticated browser/worker acceptance                            | Real PostgreSQL, native Windows worker, installed `qwen3:8b`, actual Git/container tests and persisted artifacts |

The three skips in the coordinator test image are deliberate: it contains no Git
or Docker daemon access. Those worker-side tests were separately executed on the
native Windows host. Counts describe separate runs, not disjoint tests to add up.

GitHub CI additionally exposed two pre-existing references to the optional Windows
`CREATE_NO_WINDOW` constant in worker discovery/health tooling. They now detect the
actual subprocess feature with a zero fallback. Strict mypy was rerun successfully
for `linux`, `darwin` and `win32` targets before rebuilding the final candidate.

The historical four-process/scheduler/inference/workflow CI probes use test-only
bearer credentials. CI now runs those probes with an explicit Compose override
against `godfather_test`, after the normal Google-authenticated API restart gate.
The normal local and production configuration does not enable legacy login.
Inference/workflow probes explicitly authorize their exact fixture model and the
predefined `plan.describe@1` tool through the owner workspace-policy API.

The browser harness mocks **Google HTTP responses only**, using actual Authlib
verification, sessions, invitations and RBAC. It verifies private connection
visibility, workspace artifact denial, real job/result persistence, agent management,
worker revocation, logout and existing node-owner restrictions. It does not establish
real Google account acceptance after a production upgrade. Screenshots and detailed
test logs remain in ignored `.cache/phase11` and `.cache/phase09-runs` directories.

<a id="phase-11-validation-2026-10-20--release-and-remaining-acceptance"></a>

### Release and remaining acceptance

The clean source is packaged using the established source-free Linux AMD64 release
process and standalone Windows-worker builder. Generated manifests record the exact
release, source revision, image IDs, build time and migration head. The release smoke
checker compares image metadata and verifies fresh/repeat migrations, private proxy
behavior, backups/restores and durable volumes in a separately owned local project.
Packaging and its generated evidence occur after this source commit; consult those
manifests/results for the exact artifact identity rather than hardcoding it here.

Automatic approval review initially rejected production SSH inspection. The user
then explicitly approved SSH access and deployment of this candidate. Release
`0.2.0-rc.4` at `538df376740632faf806d8bb6a832c2cd7cdb5ef` was deployed;
the migration, service health, backup integrity and preservation checks passed.
The user confirmed the signed-in version and existing results after refresh.
See [deployment verification](phases.md#phase-11-deployment-2026-10-20) for the exact
live checks and remaining coding/provider acceptance.

Real OpenAI/Anthropic acceptance requires owner-local API credentials plus explicit
authorization for billable calls. OS credential-store behavior was mocked, not tested
against actual provider keys. Physical macOS/Linux workers, new native macOS builds,
and real provider rate/cancellation/billing behavior remain unverified. Paid retries,
paid fallback, server-side API-key storage and unrestricted coding tools stay disabled.

The current task remains Phase 11 until its pending live gates are resolved; no
later phase, DNS/Google Cloud change or new infrastructure is authorized here.

---

<a id="phase-11"></a>

<a id="phase-11--phase-11-coding-results-and-independent-provider-connections"></a>

## Phase 11: coding, results and independent provider connections

The user explicitly authorized this assignment, including routine deployment to the
existing environment. This supersedes earlier planning-only BYOK notes. No frontier
credentials or billable calls have been authorized or supplied. The user separately
approved SSH access and deployment of `0.2.0-rc.4`; the upgrade and preservation
checks passed. See [deployment verification](phases.md#phase-11-deployment-2026-10-20)
for executed checks and remaining live coding/provider acceptance.

<a id="phase-11--identity-and-billing"></a>

### Identity and billing

**Current usability revision:** the owner subsequently authorized encrypted
account key entry and provider-managed billing on 2026-10-21. For candidate
`0.3.1-rc.3`, follow [account connections and project setup](../operations/coding-and-account-setup.md).
The local-key commands and spending-policy instructions below document the legacy
compatible path; they are not required by the new account flow.

Google OIDC remains the account/session system, with the existing invitation and
workspace RBAC checks. Its tokens, scopes and client secret are not provider API
credentials. OpenAI Responses and Anthropic Messages use separate, owner-local API
keys. Consumer ChatGPT/Claude subscriptions and browser tokens are not supported.
Node machine authentication remains independent of both systems.

Open **Provider Connections**, choose a provider and an owned worker, and create a
private connection. Creation stores metadata only and leaves spending disabled.
On that worker, under the owner's OS account, run:

```text
godfather-worker provider set openai CONNECTION_UUID
godfather-worker provider set anthropic CONNECTION_UUID
```

The command prompts without echo and stores the key in Windows Credential Manager,
macOS Keychain or Linux Secret Service. There is no plaintext fallback or central
key-upload endpoint. A missing/locked/unsupported store fails closed; headless Linux
requires an already configured supported Secret Service. This feature installs no
OS services. The pip installation also exposes `godfather-worker-provider`.

Add the public connection reference to the worker's existing provider JSON:

```json
[
  { "id": "local", "provider": "ollama", "url": "http://127.0.0.1:11434" },
  {
    "id": "my-api",
    "provider": "openai",
    "connection_id": "CONNECTION_UUID",
    "model_catalog": [
      {
        "identifier": "EXACT_PROVIDER_MODEL_ID",
        "context_window": 32768,
        "max_output_tokens": 4096,
        "tools": false,
        "structured_output": false
      }
    ]
  }
]
```

Replace all placeholders and verify each model's actual limits/operations using
the provider's current documentation. The numbers above illustrate configuration,
not a model capability claim. Use `anthropic` for Messages. Native endpoints are
fixed to official HTTPS APIs. The
official OpenAI/Anthropic hosts cannot be configured through the legacy compatible
adapter to bypass connection policy. Existing local Ollama/compatible runtimes stay
available. Listing an ID does not certify feature support; the
owner must enable supported operations individually. Catalogs are intersected with
actual provider discovery; unavailable IDs are not advertised. Discovery and Test
Connection list models without running inference. They still require a valid key.

In Provider Connections, enter owner-verified documented input/output prices in USD
per million tokens, official source URLs and verification dates. Verification expires
after 30 days. Unknown/stale pricing blocks paid reservations. Enable a connection
only after setting per-call and lifetime safeguards. Set a default model and select
the exact permitted provider connection/model when creating an agent. Each paid run
requires a separate submitter confirmation covering spending and task data egress.

Private connections can serve only their owner. Sharing additionally needs explicit
borrower/workspace allowlists and an owner-issued expiring model grant. Per-job
approval requires the exact pending job ID; issuing it binds the grant to that job.
Node-owner contribution permissions and workspace model policies still apply.
Neither Google sign-in nor platform administration bypasses these checks.

PostgreSQL records the payer, submitter, job, attempt, connection, reservation,
price version and provider-reported token counts. Costs are integer micro-USD
estimates, not invoices. Concurrent reservations consume the same connection/grant
allowance. Missing usage retains its reservation for reconciliation. Usage with
cache-pricing categories unsupported by this initial base-token estimator also
requires reconciliation rather than inventing a settled cost. Paid retries
and paid fallback are disabled; a possibly accepted external call is not replayed.
Application limits cannot guarantee provider billing caps.

Disable/revoke blocks future authorizations without changing Google login, sessions
or node ownership. Already authorized external requests may still incur charges.
Revoke the actual key at its provider separately. Remove the local stored copy with:

```text
godfather-worker provider delete openai CONNECTION_UUID
```

<a id="phase-11--coding-worker-opt-in"></a>

### Coding worker opt-in

Coding reuses Phase 06's sequential workflow, immutable artifacts and fenced
checkpoints. Start with one `coding` step, `output_schema=coding`, explicit
`coding.workspace` permission, `coding-sandbox-v1` runtime and zero automatic
retries. The UI creates this definition through the Coding workflow option.

The node owner supplies a local repository JSON configuration with these fields:

```json
[
  {
    "id": "REPOSITORY_UUID",
    "name": "Approved project",
    "path": "ABSOLUTE_LOCAL_REPOSITORY_PATH",
    "image": "sha256:EXISTING_LOCAL_IMAGE_ID",
    "allowed_user_ids": ["USER_UUID"],
    "allowed_workspace_ids": ["WORKSPACE_UUID"],
    "files": ["src/*.py", "tests/*.py"],
    "commands": [["python", "-m", "unittest", "discover", "-s", "tests"]]
  }
]
```

Use an already installed Linux toolchain image, pinned by image ID or repository
digest. It must contain `/bin/sh`, `cp` and the approved test/build tools and offline
dependencies. No image/model downloads or dependency installation are automatic.
Start the existing worker with its existing machine credential and inference
configuration, adding:

```text
--execute-workflows --coding-config coding.json --allow-tool-permission coding.workspace
```

Select that advertised repository when submitting a coding task. Optional literal
code-search terms return up to 32 matching file/line references and feed those
actual matches to the agent. Only committed
UTF-8 text files matching the owner's bounded patterns enter the snapshot. Git
metadata, credential directories, environment files, symlinks and unsafe paths are
excluded or refused. This first implementation bounds the repository prompt to
32,768 characters and outputs to the existing artifact limits; select a focused
set of files for larger repositories. It does not inspect uncommitted source work.

The worker inspects the approved snapshot, requests a bounded edit plan, validates
every edit and executes only owner-configured commands. Tests run as an unprivileged
UID in a networkless, read-only-root Linux container, with no host credentials or
Docker socket. The host snapshot is read-only; the writable test workspace is a
256 MiB tmpfs and `/tmp` is 64 MiB. Test writes are disposable and do not amend the
proposed patch. CPU, memory, process count, output and time are bounded. Remote
Docker endpoints are refused. Docker itself remains an owner-trusted local service.

The deliverable contains the source commit, actual Git diff, changed files and
actual command exit codes/output. Failing tests are explicitly reported; completed
job status means the deliverable was produced, not that every test passed. The
original repository is preserved. Git pushes, deployment, host shell tools and
destructive operations are absent. A lost coding attempt requires review rather
than replaying commands. Committed artifacts remain portable and authorized by
workspace. The worker protocol retains its existing local-inference wire shape;
new coding assignments require separately advertised capabilities.

<a id="phase-11--results-and-release-status"></a>

### Results and release status

The owner-authorized **0.3.2-rc.1** update is deployed with accomplishment-first
coding previews and a separate, locally opted-in application action. Follow the
[Run → Preview → Apply guide](../operations/results-and-apply.md) and
[deployment verification](../operations/results-apply-verification-2026-10-21.md). This needs
one updated worker; future presentation changes remain Command Center-only.

Job detail prioritizes sanitized Markdown, highlighted code/diffs, readable JSON,
tables, chart data and supported authorized document/media envelopes. Copy and
download controls use persisted output; artifact downloads recheck workspace access
and integrity. Remote Markdown images and raw HTML are not rendered. Partial output
is labeled; cancellation continues to clear private stream output. Raw results,
attempts, checkpoints and lifecycle/failover events remain in Technical Details.
No image/report generation subsystem is added by the result renderers themselves.

The status bar reads version, Git revision and build timestamp embedded by
`scripts.release`; environment comes from the running API configuration. Local
development with no release metadata says unavailable. Nothing hardcodes the
currently deployed release into the dashboard.

<a id="phase-11--validation"></a>

### Validation

Run normal Ruff, mypy, pytest, frontend lint/typecheck/tests/build and the disposable
PostgreSQL suite as documented in setup. Real worker/container/browser acceptance:

```powershell
$codingImage = docker image inspect --format '{{.Id}}' godfather-local-api
.venv/Scripts/python.exe -m scripts.check_google_oidc --model EXISTING_OLLAMA_MODEL --coding-image $codingImage
```

This uses real PostgreSQL, native Windows worker, installed local model, Git and
Docker, with Google network responses mocked only inside the isolated OIDC test
server. It resets only `godfather_test`. Run serially after database tests.
Physical macOS/Linux workers, real Google login after upgrade, real paid-provider
calls, production data preservation and deployed version checks need their actual
environments. Do not treat mocks or local evidence as live acceptance.

Provider references: [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses),
[OpenAI structured output](https://developers.openai.com/api/docs/guides/structured-outputs),
[Claude Messages](https://platform.claude.com/docs/en/claude_api_primer),
[Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming).

---

<a id="phase-12-verification-2026-10-21"></a>

<a id="phase-12-verification-2026-10-21--phase-12-and-consigliere-verification--2026-10-21"></a>

## Phase 12 and Consigliere verification — 2026-10-21

**Command Center and Consigliere 0.4.0-rc.3 are deployed** to the existing
DigitalOcean environment. The owner authorized implementation, builds and this
deployment in the Phase 12 assignment. The later native UI request is included.
Source was committed and pushed before building. Phase 13 has not begun.

<a id="phase-12-verification-2026-10-21--delivered-behavior-and-files"></a>

### Delivered behavior and files

- `workloads.py` in shared schemas, API and worker; worker `data_program.py`:
  workspace-authorized CSV/JSON and bounded values-only XLSX uploads, deterministic
  statistics, grouping, monthly trends, comparisons and documented anomaly flags.
  Structured SQL results can be uploaded as exports. Calculations run as fixed
  trusted code in an owner-approved, restricted Linux container on a worker.
- Model gateway `images.py`: extensible image interface and an explicitly opted-in,
  existing local AUTOMATIC1111 backend. Dimensions, sampling steps, seed, multiple
  PNG outputs, metadata, cancellation/failure reporting and durable downloads use
  the existing workflow, artifact and scheduler contracts. No configured backend
  produces an honest unavailable state; no cloud fallback or model download occurs.
- Workflow/runtime, scheduler, worker CLI/desktop, artifact store, bridge and
  Caddy integration: capability/runtime/permission matching, model-free data jobs,
  durable source/checkpoint references, fenced publication and authorized files.
  Additive migration `0012_workload_artifacts` raises the bounded envelope limit
  to 8 MiB; rollback refuses oversized records instead of deleting them.
- Dashboard `workloads.tsx`, its route and job-result presentation: upload and
  submit, choose analysis/report/image settings, inspect metrics/charts, and
  download HTML, Markdown, CSV, XLSX and reproducibility JSON as applicable.
- Worker `desktop_app.py`, `desktop_layout.py`, `desktop_theme.py`,
  `desktop_settings.py`, `coding_projects.py`, bundled Font Awesome command icons
  and native checks: normal resizing, no window-wide scrolling canvas, conditional
  table scrolling, navy/cyan header/ribbon and embedded Projects tab. Settings has
  General, Resources, Workloads, Sharing, Appearance and Connection tabs. Local
  appearance persists; changes to contributed capabilities require Pause and
  explicit owner choices. No host permission is enabled by default.
- Tests, packaging scripts, the [Phase 12 runbook](phases.md#phase-12),
  [native UI guide](../operations/consigliere-ui.md), and
  [ADR 0019](../decisions/0019-bounded-worker-data-workloads.md) document the
  execution boundaries and setup.

<a id="phase-12-verification-2026-10-21--executed-checks"></a>

### Executed checks

- Local disposable PostgreSQL suite: **512 passed, 3 skipped**. The skips were two
  opt-in coding-container checks and one opt-in workload-container check. Separate
  explicitly selected, existing-image runs exercised real coding and data sandbox
  execution. The data workload/packaging run passed 59 tests; the coding run passed
  30 tests with the unrelated opt-in workload check skipped.
- Integration tests exercised preferred data execution, compatible backup resume
  after a committed analysis checkpoint, stale fencing, restart/download recovery,
  workspace denial, malformed input and withdrawn owner permission. These used
  isolated fixtures, not production datasets or real image hardware.
- Latest native unit suite: **294 passed, 4 skipped, 217 deselected**. The skips
  cover optional container checks and an unavailable Windows symlink permission.
  Ruff formatting/lint and strict mypy over 153 files passed. Dashboard ESLint,
  TypeScript, production build and **20 component tests** passed.
- [Final source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39694954027)
  passed all eight jobs: Python 3.12/3.14, Windows/macOS/Linux Python and dashboard
  checks, plus the Linux container gates. The container gates include migrations,
  health/restart, scheduler/failover and existing inference/workflow acceptance.
- Isolated Edge checks passed upload-to-job navigation, unavailable image controls,
  and desktop/mobile layout at 1440 and 390 pixels. No production job was submitted.
  Real Windows UI checks exercised resizing, embedded Projects, saving scoped
  projects, all six Settings tabs, appearance persistence and tray restoration.
- Windows packaged temporary install/reinstall, bundled Tk/tray startup and an
  isolated Credential Manager namespace passed. Both final
  [native Mac builds](https://github.com/briancwelch/GodfatherAI/actions/runs/39694953831)
  passed source UI checks, frozen-app startup, architecture/library/signature and
  DMG checks. Earlier candidates exposed a Mac frozen-startup failure and a later
  test assumption about exact client heights. Those candidates were not deployed;
  final checks passed after packaging/import changes and a native-size-aware test.
  A single root cause for the initial startup failure was not established.
- Final saved-image release checks passed production configuration/Caddy validation,
  fresh/repeated migrations, empty identity bootstrap, private healthy services,
  anonymous denial, all three installer downloads through both proxy hostnames,
  persistence/restart and actual paired database/artifact restore in a disposable
  environment. Evidence: `.cache/release-tests/4b02c369717b/result.json`.

<a id="phase-12-verification-2026-10-21--immutable-artifacts"></a>

### Immutable artifacts

All four artifacts were built from clean source
`564c1d027136e108904d128efa119f10f0ae1fa5`. Later documentation commits do not alter
the deployed source revision. Installer manifests record the same source.

| Artifact                                           | SHA-256                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `consigliere-0.4.0-rc.3-windows-x64-setup.exe`     | `c561d6bb91489bb93916e9ecb05b927160d1d14044666e7a269dd27fa67a4df9` |
| `consigliere-0.4.0-rc.3-macos-arm64-installer.dmg` | `b97b9e9a421eaa93f69712eb4d95c0f15fc973532ab253778d88d75656f7287f` |
| `consigliere-0.4.0-rc.3-macos-x64-installer.dmg`   | `93bb3805e3e786bf1b4dc6ae1fe1da68448932da16b1425514a5bd8c7b431b9a` |
| `godfather-0.4.0-rc.3-linux-amd64.tar.gz`          | `2c66e68b6ff04d367690d3a50e02fc43272abb104ec3464c246f441c9fd9ac87` |

Download Consigliere from **Nodes → Downloads** in
[Command Center](https://app.the-godfather.ai). Quit the existing tray worker before
installing the replacement. Existing settings, credentials and project permissions
retain their locations. The owner must opt into the new data/image capabilities;
upgrading does not grant them automatically.

<a id="phase-12-verification-2026-10-21--production-verification"></a>

### Production verification

The existing deployment under `/opt/the-godfather` now resolves to
`releases/godfather-0.4.0-rc.3-linux-amd64`; API metadata reports the exact source
above and schema `0012_workload_artifacts`. All five services are healthy.
PostgreSQL and Redis have no published host ports. The existing environment,
including vault/proxy keys, remained byte-identical and mode 600. No DNS, firewall,
Google Cloud configuration or account credentials were changed.

Before/after fingerprints matched for **2 users, 2 Google identities, 2 workspaces,
3 credentials, 1 node ownership/policy, 8 jobs, 3 agents, 4 artifacts, 2 checkpoints,
2 provider connections and 1 encrypted account-provider key**. Workspace membership
was empty before and after. The existing node remained offline with no active jobs;
no real user worker was installed, reconfigured or started automatically.

Paired backup: `/opt/the-godfather/state/backups/20261021T235539-750894`.
Its checksums, PostgreSQL dump listing and artifact gzip passed. Production restore
was not performed; actual restore testing used the disposable release environment.
Preservation evidence: `.cache/phase12/upgrade.log` and `postflight.log`.

Public verified-TLS checks retrieved all three installers and matched their SHA-256
values and served manifest. Anonymous workload options/submission/download and
worker publication were denied; foreign-origin writes were blocked. Existing
account, administrator, checkpoint and result-action boundaries also passed.
A fresh browser verified the live login, pairing sign-in gate and real Google
redirect with PKCE/S256 and exactly `openid email profile`, without signing into a
private account. Ordinary DNS/TLS returned HTTP 200 at the expected existing server.
Evidence: `.cache/phase12/public-result.json`, `phase12-public-extra.json`,
`live-browser-result.json` and related logs/screenshots.

<a id="phase-12-verification-2026-10-21--remaining-acceptance-and-unsupported-options"></a>

### Remaining acceptance and unsupported options

The owner stated that no real dataset is currently authorized. Users can upload
their own permitted CSV/JSON/XLSX data; live analytics/report acceptance awaits such
a submission and an owner-opted-in compatible worker with an existing pinned Python
image. No production fixture job was created to manufacture acceptance.

Google Sign-In remains identity-only. **Google Drive/Sheets data connections are
not implemented**; export and upload are available. Live database connections and
generated SQL/Python execution are not supported. PDF export and cloud image
providers are not implemented. No local image backend was configured during this
run, so actual generation/GPU performance and image failover on physical workers
remain unverified. Cancellation does not promise to stop work already accepted by
an external local backend.

Native builds do not prove recipient Docker/GPU parity or physical installation.
Windows publisher signing and Mac Developer ID/notarization remain pending; these
are unsigned/ad-hoc signed candidates. Real private-account login, recipient
pairing and live workload acceptance remain owner actions. See the runbooks for
exact setup. Stop at Phase 12; Phase 13 requires a separate assignment.

---

<a id="phase-12"></a>

<a id="phase-12--phase-12-images-analytics-and-reports"></a>

## Phase 12: images, analytics and reports

The owner authorized implementation/build/deployment and required a GitHub main
checkpoint first. That checkpoint is `5f375637e0a8c80bafdf27c5c84de9e6ab7567ce`.
The owner subsequently confirmed that **no real dataset is authorized yet**.
Acceptance uses deterministic fixtures only in isolated tests; production must not
receive fictional datasets or test jobs. Owners may submit their own datasets to
any compatible, permitted worker. No paid image request is authorized.

<a id="phase-12--use-the-command-center"></a>

### Use the Command Center

Open **Images / Analytics / Reports**, choose an authorized workspace and workload.
Upload a CSV, JSON or values-only Excel workbook, enter the request/context and
optionally select grouping, ISO date and numeric value columns by their exact names.
The calculations are deterministic: the request is context, not generated code.
Submit Analytics only or Analytics → report. The latter checkpoints completed
analysis before reporting; recovery skips the committed stage.

Job detail shows calculated statistics, group/month charts, period comparisons,
source checksum and downloads before technical details. History, cancellation,
retry, checkpoints and failover use existing Jobs. Reports are HTML (including a
chart), Markdown, CSV or Excel; each report also provides structured analysis JSON.
PDF is not implemented. CSV/Excel reports include source, checksum, summary and
methodology. Spreadsheet exports use strings and neutralize formula prefixes.

Uploads are bounded to 1 MiB, 10,000 records and 64 columns. UTF-8 CSV needs a header
and consistent row widths. JSON accepts flat record arrays or an authorized SQL
export shaped as `{"columns":["name"],"rows":[["value"]]}`. No database SQL is
executed. Excel reads `xl/worksheets/sheet1.xml` only, rejects formulas, macros and
external links, and bounds ZIP expansion to 8 MiB/200 entries. Date columns must
contain ISO values (Excel date serials must be exported as ISO strings). Nested
records, complex workbooks and larger datasets need a bounded export first.

Numeric columns require finite numeric nonmissing values. Missing values are
excluded and counted. Statistics include count, missing count, sum, mean, median,
min/max and sample standard deviation. Anomaly candidates use absolute z-score
greater than 3; this is a transparent heuristic, not a significance/causality claim.
Groups/months are limited to 100. Monthly changes compare observed periods; absent
months are not silently synthesized, and percentage changes from zero are unknown.

Google Sign-In authorizes identity only. Google Sheets/Drive account ingestion and
live SQL source connections are **not configured/implemented** in this candidate.
Export an authorized spreadsheet and upload it. A future Google data connection
needs separate read-only consent, encrypted refresh credentials, revocation and
workspace/worker restrictions; do not reuse Google login tokens or change Google
Cloud settings under this assignment. No real data-connection credentials exist.

<a id="phase-12--owner-controlled-worker-setup"></a>

### Owner-controlled worker setup

Updated Consigliere Settings contains optional data sandbox and local image backend
configuration. Blank values disable these capabilities. The owner must already
have a local Docker engine and a pinned image containing Python 3.12+ standard
library. No image/model/dependency download, service installation or Docker endpoint
change occurs. Enter the existing image digest to allow analytics/report execution.
Saving opts this computer into these workloads; Pause, change Settings, then Resume.
Existing credentials, node identity, contributions and private project grants remain.

CLI users may create owner-local `workloads.json`:

```json
{
  "image": "sha256:REPLACE_WITH_EXISTING_LOCAL_IMAGE_ID",
  "images": null
}
```

The placeholder is intentionally invalid. Inspect an already installed suitable
image with `docker image inspect --format '{{.Id}}' YOUR_EXISTING_IMAGE`. Its identity
must be a SHA-256 ID or digest; `--pull=never` prevents automatic retrieval. Start
the existing authenticated worker with:

```text
godfather-worker-cli --url YOUR_CONFIGURED_COORDINATOR --credential-file YOUR_EXISTING_WORKER_CREDENTIAL --execute-workflows --workload-config workloads.json --allow-tool-permission data.analyze
```

Do not create another node identity just to enable a workload. Native Windows,
macOS and Linux use the same Python workflow core and a local Linux-container
adapter; absent Docker/image support is an honest unavailable state. A reporting
worker can also analyze; schedules require both capabilities for the combined job.

<a id="phase-12--optional-local-images"></a>

### Optional local images

The model gateway now has a separate extensible image adapter protocol. The first
adapter is an already installed AUTOMATIC1111 API on literal loopback HTTP, with
an owner-configured allowlist of installed `model_name` values. It discovers actual
models before advertising; it never treats Ollama text models as image providers.

```json
{
  "image": null,
  "images": {
    "backend": "automatic1111",
    "url": "http://127.0.0.1:7860",
    "models": ["EXACT_INSTALLED_MODEL_NAME"]
  }
}
```

Grant `images.generate` in the CLI or save these explicit local settings in the
desktop. Configure an existing dedicated backend; this release does not install or
launch one. Supported controls: 256–1024 pixels in 64-pixel increments, 1–4 images,
1–50 sampling steps and seed (-1 requests random). Output is validated/re-encoded
PNG. Metadata describes the prompt and requested settings, not an invented actual
random seed. No credentials are sent and there is no cloud fallback. Cloud image
providers must later implement the existing account/provider authorization before
use; they cannot be configured through this local adapter.

Image jobs have no automatic replay. Cancellation closes the request and fences
publication; an already accepted local generation may finish on its backend.
The adapter avoids a global interrupt that could cancel unrelated backend work.
The [official API guide](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API)
documents discovery and generation; inspect the installed backend's `/docs` for its
actual version. No configured image provider means live image acceptance is pending.

<a id="phase-12--isolation-artifacts-and-recovery"></a>

### Isolation, artifacts and recovery

The existing sequential agent runtime, PostgreSQL job/attempt state machine,
resource matching, fair scheduling, node-owner/workspace policy, leases/fencing and
immutable versioned artifacts remain authoritative. There is no second scheduler.
Data workflows explicitly omit text-model selection; legacy assignments retain
their wire shape, and new stages require separately advertised runtimes/permissions.

Fixed repository code parses data in an unprivileged, networkless, read-only-root
container, with one CPU, 512 MiB memory/swap ceiling, 32 PIDs, 16 MiB temporary
storage and bounded stdout/time. Its only host mount is a private temporary copy of
the fixed program and submitted JSON, read-only. No generated Python, generated SQL,
host shell, source repository, Docker socket or provider credentials enter it.
Cancellation/timeout removes only that generated disposable container. The local
Docker engine itself remains owner-trusted, as with coding execution.

Source uploads persist in the PostgreSQL job input before assignment; disconnection
cannot lose the submitted dataset. Completed analysis/report/image envelopes use
the existing centrally durable artifact store, fsync-before-reference, immutable
UUID names and SHA-256 verification. The additive `0012_workload_artifacts` migration
raises the bounded envelope limit to 8 MiB; rollback refuses larger records rather
than truncating them. No tables/data are removed. Only workflow checkpoint writes
gain a 9 MiB public request bound; ordinary routes retain 2 MiB. Worker poll/artifact
reads support the larger bounded envelopes. Workspace authorization and integrity
are rechecked on every file download, including after restart. HTML downloads are
attachments with restrictive CSP; generated HTML is never injected into the app.

<a id="phase-12--validation-and-remaining-acceptance"></a>

### Validation and remaining acceptance

Run native formatting/lint/mypy/pytest and dashboard checks, then the real PostgreSQL
suite against `godfather_test` only. `tests/test_workloads.py` includes an opt-in
real sandbox test using `GODFATHER_CODING_TEST_IMAGE` set to an **existing** local
image digest. Integration tests cover prefix recovery, stale fencing, restart,
download authorization, input contracts and withdrawn node-owner permission.

The deployed 0.4.0-rc.3 release and actual executed results are recorded in the
[verification report](phases.md#phase-12-verification-2026-10-21).
Real customer analytics/reporting acceptance awaits an owner-submitted authorized
dataset. No fictional production records or paid/live image calls may be created
to manufacture acceptance. Cross-platform packaging is evidence of native builds,
not proof of physical Docker/inference performance on every recipient computer.

<a id="phase-12--ui-acceptance-checklist"></a>

### UI acceptance checklist

The new navigation section lets users select a workspace, upload and submit data,
choose output formats, see honest worker/provider availability and open job history.
It reuses compact application chrome, panel/form controls and responsive field grids.
Loading, no workspace, no compatible worker/provider, rejected input and submission
failure states are explicit; labels, keyboard focus and status live regions remain.
Data comes from authenticated workspace options/submission and persisted job outputs.
Browser tests must cover upload-to-job navigation, unavailable images, readable
tables/charts, download links and narrow viewport layout. Technical diagnostics
remain in existing Job detail disclosure.
