# The Godfather

Private, cross-platform AI orchestration platform for two founding administrators in Las Vegas and Chino Hills.

One developer builds the platform for both administrators. The second administrator does not need a development environment.

**Current milestone: Phase 06 — agent runtime and durable workflow checkpoints.** Portable immutable agent versions run predefined model/tool steps through the existing scheduler and gateway. PostgreSQL owns execution state and metadata; a private local persistent volume holds immutable checkpoint/output artifacts. Native mock and real Ollama demonstrations passed process interruption, API restart, same-node recovery, no repeated committed steps and stale-write rejection. The dashboard remains a disconnected shell. BYOK remains a planning-only extension.

## Start here

1. Read [AGENTS.md](AGENTS.md) and the [UI/UX specification](docs/design/UI-UX.md).
2. Follow the [Windows, macOS, and Linux setup guide](docs/operations/setup.md).
3. Review [Phase 01 validation](docs/operations/phase-01.md) and [Phase 02 setup and results](docs/operations/phase-02.md).
4. Follow [Phase 03 startup, credential provisioning and simulated workers](docs/operations/phase-03.md).
5. Use [Phase 04 jobs, scheduler simulation and validation](docs/operations/phase-04.md) and the [job protocol](docs/protocols/jobs-v1.md).
6. Follow [Phase 05 provider setup and inference validation](docs/operations/phase-05.md), [architecture](docs/architecture/model-gateway.md), and the [inference API contract](docs/protocols/inference-v1.md).
7. Use [Phase 06 agent definitions, local commands and recovery evidence](docs/operations/phase-06.md), [runtime architecture](docs/architecture/agent-runtime.md), and the [workflow API contract](docs/protocols/agents-v1.md).

Use the private remote `https://github.com/briancwelch/GodfatherAI.git`. GitHub account access is required to clone it. Never embed credentials in a clone URL.

## Local development

Prerequisites: Git, Node.js 24.22.0 with npm 11, uv 0.13.1, and Docker with Compose and a Linux engine. On Windows, use Docker Desktop with WSL2. Python 3.14 is selected by `.python-version`; uv can manage it independently of system Python. Python source targets 3.12+ syntax.

After preparing `.env` as described in the setup guide:

```text
uv sync --locked --all-packages
npm ci
docker compose --profile tools build dashboard api migrate
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait
```

Open **http://localhost:3000** for the shell and **http://localhost:8000/api/v1** for the API. Both ports bind to `127.0.0.1`. PostgreSQL and Redis have no host ports. Health probes are at **http://localhost:8000/health/live** and **http://localhost:8000/health/ready**. Readiness requires the current migration head; API startup never applies migrations automatically.

For frontend hot reload, start only the dependencies and run Next.js natively:

```text
docker compose up --wait postgres redis
npm run dev
```

Do not run the container dashboard and native Next.js server on port 3000 simultaneously. Stop the container dashboard first if it is already running.

## Checks

```text
uv run --locked --all-packages python scripts/dev.py doctor
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
```

The doctor inspects tools and Docker availability without installing anything. The check command runs Python formatting, lint, typing and tests, then frontend formatting, lint, typing and a production build. It fails at the first failed check. See the setup guide for individual commands.

## Layout

| Path                      | Purpose                                                                 |
| ------------------------- | ----------------------------------------------------------------------- |
| `apps/dashboard`          | Next.js, strict TypeScript, Tailwind, minimal shadcn/ui shell           |
| `apps/api`                | FastAPI foundation, configuration, logging and SQLAlchemy models        |
| `packages/worker`         | Outbound registration, heartbeats, synthetic jobs and opt-in inference  |
| `packages/model-gateway`  | Portable Ollama/OpenAI-compatible discovery and text inference adapters |
| `packages/agent-runtime`  | Portable sequential workflows and validated read-only tool contracts    |
| `packages/shared-schemas` | Versioned worker registration/health contracts                          |
| `infrastructure/docker`   | Dashboard build/runtime container                                       |
| `scripts`                 | Portable development checks                                             |
| `tests`                   | Tooling/API unit tests and guarded real-PostgreSQL integration tests    |
| `docs/design`             | Authoritative frontend design guidance                                  |
| `docs/architecture`       | Architecture and cross-platform compatibility                           |
| `docs/decisions`          | Architecture decision records                                           |
| `docs/operations`         | Setup, phase gates, troubleshooting                                     |
| `.github/workflows`       | Cross-platform checks and Linux container smoke checks                  |

Future packages and infrastructure are created only when their milestones require them.

## Safety and milestone boundaries

The dashboard is a local shell, without a login or private data. It does not claim operational state. Node APIs require provisioned worker or administrator bearer credentials. Browser sessions, full RBAC and remote exposure remain separately gated; see the [security foundation](docs/architecture/security-foundation.md).

PostgreSQL is authoritative for node identities, heartbeats, jobs, attempts, leases, retries and events. Redis is transient. Workers connect outbound, and owners control their host permissions. A platform administrator cannot bypass those restrictions.

`app.the-godfather.ai` and `api.the-godfather.ai` are proposed names only. Nothing here registers domains, configures DNS, provisions a VPS, or authorizes deployment. Production targets an independent Ubuntu DigitalOcean coordinator using the same containerized application architecture with separately reviewed environment configuration.

Phase 01–05 passed their gates, including real Ollama acceptance before Phase 06. Phase 06 implements only sequential read-only workflows and same-node process recovery; see its report for actual checks and limits. Stop after Phase 06. Phase 07 remains unapproved. [Hybrid inference/BYOK](docs/architecture/byok-plan.md) is planning only and requires separate explicit implementation authorization.
