# The Godfather

Private, cross-platform AI orchestration platform for two founding administrators in Las Vegas and Los Angeles.

One developer builds the platform for both administrators. The second administrator does not need a development environment.

**Current milestone: Phase 01 — repository and local environment.** This repository contains development tooling, a nonfunctional Command Center shell, and local dependency configuration. It has no API routes, users, jobs, workers, scheduling, inference, or external integrations.

## Start here

1. Read [AGENTS.md](AGENTS.md) and the [UI/UX specification](docs/design/UI-UX.md).
2. Follow the [Windows, macOS, and Linux setup guide](docs/operations/setup.md).
3. Review [Phase 01 scope and validation](docs/operations/phase-01.md).

Use the private remote `https://github.com/briancwelch/GodfatherAI.git`. GitHub account access is required to clone it. Never embed credentials in a clone URL.

## Local development

Prerequisites: Git, Node.js 24.22.0 with npm 11, uv 0.13.1, and Docker with Compose and a Linux engine. On Windows, use Docker Desktop with WSL2. Python 3.14 is selected by `.python-version`; uv can manage it independently of system Python. Python source targets 3.12+ syntax.

After preparing `.env` as described in the setup guide:

```text
uv sync --locked --all-packages
npm ci
docker compose up --build --wait
```

Open **http://localhost:3000**. Only the dashboard is published, bound to `127.0.0.1`. PostgreSQL and Redis have no host ports. No API URL exists in Phase 01.

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

| Path                    | Purpose                                                                |
| ----------------------- | ---------------------------------------------------------------------- |
| `apps/dashboard`        | Next.js, strict TypeScript, Tailwind, minimal shadcn/ui shell          |
| `apps/api`              | Installable Python package scaffold; implementation begins in Phase 02 |
| `infrastructure/docker` | Dashboard build/runtime container                                      |
| `scripts`               | Portable development checks                                            |
| `tests`                 | Development tooling tests                                              |
| `docs/design`           | Authoritative frontend design guidance                                 |
| `docs/architecture`     | Architecture and cross-platform compatibility                          |
| `docs/decisions`        | Architecture decision records                                          |
| `docs/operations`       | Setup, phase gates, troubleshooting                                    |
| `.github/workflows`     | Cross-platform checks and Linux container smoke checks                 |

Future packages and infrastructure are created only when their milestones require them.

## Safety and milestone boundaries

The dashboard is a local shell, without a login or private data. It does not claim operational state. Authentication and server-side authorization are required before real data or remote exposure; see the [security foundation](docs/architecture/security-foundation.md).

PostgreSQL will be authoritative for durable execution state. Redis is transient. Future workers connect outbound, and owners control their host permissions. A platform administrator cannot bypass those restrictions.

`app.the-godfather.ai` and `api.the-godfather.ai` are proposed names only. Nothing here registers domains, configures DNS, provisions a VPS, or authorizes deployment. Production targets an independent Ubuntu DigitalOcean coordinator using the same containerized application architecture with separately reviewed environment configuration.

Phase 01 ends with documented results and a reproducible development setup. There is no second-developer acceptance requirement. Phase 02 requires explicit authorization.
