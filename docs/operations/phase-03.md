# Phase 03: Worker registration and health

Current authentication is documented in [Phase 09](../operations/phase-09.md).
Google OIDC/application sessions replace human bearer login in normal operation;
worker machine credentials remain independent. Earlier bearer/simulator procedures
below are historical and restricted to isolated automated tests. Phase 09 does not
authorize public deployment or Phase 10.

## Scope and prerequisite

Phase 03 was explicitly authorized. Before changes, the Phase 02 migration succeeded, the existing real-PostgreSQL suite passed **44 tests**, and the actual API/PostgreSQL restart, persistence, outage (live 200 / ready 503) and recovery probe passed. The full repository check also passed. An initial overlapping restart/test run caused two connection errors; after the probe finished, the serial test run passed. No Phase 02 source defect was found.

This phase adds authenticated enrollment, discovery, health, administration endpoints, simulated worker processes and durable lifecycle events. The dashboard remains disconnected. There is no scheduler, task execution, agent runtime, failover, inference or remote deployment.

## Start the local coordinator

Run from the repository root after the existing [setup guide](setup.md), using the ignored `.env`:

```text
uv sync --locked --all-packages
docker compose --profile tools build api migrate api-test
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait api dashboard
```

Migration `0002_worker_health` is additive and preserves Phase 02 records. The API never migrates automatically. Health remains at **http://localhost:8000/health/live** and **http://localhost:8000/health/ready**; the existing nonfunctional shell remains at **http://localhost:3000**. Databases have no host ports.

Defaults are 10-second heartbeats, suspect after 20 seconds, offline after 30 seconds, and a 1-second database sweep. Configure `GODFATHER_HEARTBEAT_INTERVAL_SECONDS`, `GODFATHER_SUSPECT_AFTER_SECONDS`, `GODFATHER_OFFLINE_AFTER_SECONDS`, and `GODFATHER_HEALTH_SCAN_SECONDS` in `.env`, then recreate the API. Heartbeat must be less than suspect, which must be less than offline. Workers obey the interval returned by the API.

## Provision local synthetic identities

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

## Run four simulated workers on one computer

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

## Physical discovery

Omit `--simulate` to discover the current host, then explicitly advertise allowed specialties and limits:

```text
uv run --locked --all-packages godfather-worker --credential-file .cache/credentials/physical-node.json --primary research --secondary coding --policy shared --concurrency 1
```

Provision `physical-node` first. This performs read-only host inventory, not inference or task execution. Discovery reads CPU/RAM through [psutil](https://psutil.readthedocs.io/stable/index.html); NVIDIA telemetry uses its documented [query interface](https://docs.nvidia.com/deploy/nvidia-smi/index.html). macOS uses system_profiler, Windows uses CIM, and Linux uses DRM sysfs plus optional rocminfo. Installed model inventory reads `ollama list` only when installed, forcing a loopback Ollama endpoint; unavailable probes are unknown/warnings. No drivers, models or services are installed. No repository or private file inventory is performed. Sandbox modes remain empty because finding Docker does not establish an authorized sandbox.

Workers open no listening ports. Local HTTP accepts only loopback origins. Future Tailscale communication requires an explicitly authorized HTTPS origin with valid certificates and the same node credentials. No remote service is configured or exposed by this phase.

## Verification commands

```text
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
docker compose --profile tools run --rm api-test python -m pytest -p no:cacheprovider --tb=short
uv run --locked --all-packages python -m scripts.check_worker_health
```

Create `godfather_test` once as documented in Phase 02 if absent. Integration tests reset only that explicitly disposable database. Run the worker smoke and database tests **serially**: the smoke intentionally restarts local PostgreSQL and the API. It creates a new synthetic owner, launches four native child processes, verifies fresh heartbeats, independently stops LV-01 and LA-01 while peers stay online, and checks ownership/identity/telemetry after actual service restarts. It stops only its own processes, preserves rows and writes logs/results to `.cache/phase03-runs/RUN_UUID/`. Successful completion revokes all its credentials. If interrupted or failed, use its private credential documents' `credential_id` values with the offline revoke command. Do not print their token fields.

The existing CI matrix runs worker/core/discovery tests on Windows, macOS and Linux, plus Python 3.12 on Linux. Configured CI is not proof that this unpushed change has run remotely. GPU inference and physical macOS/AMD validation are outside this local test evidence.

## Validation and remaining limits

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

## Files changed

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
