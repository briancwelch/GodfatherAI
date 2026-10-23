# Development

The [README](../README.md) is the platform user guide. This page is for developers
working on the private repository. Read [AGENTS.md](../AGENTS.md), the current
assigned milestone and relevant architecture before editing. Frontend changes
also require the [UI/UX rules](design/UI-UX.md). Work only on the authorized milestone.

## Local setup

Use the [Windows, macOS and Linux setup guide](operations/setup.md) for tools,
private environment configuration and full startup instructions. GitHub access to
`briancwelch/GodfatherAI` is required; never put credentials in clone URLs.

After preparing `.env` locally:

```text
uv sync --locked --all-packages
npm ci
docker compose --profile tools build dashboard api migrate
docker compose up --wait postgres redis
docker compose --profile tools run --rm migrate
docker compose up --wait
```

Open **http://127.0.0.1:3000**. The API is at **http://127.0.0.1:8000/api/v1**;
liveness/readiness are `/health/live` and `/health/ready`. Configure Google sign-in
and the [one-time founder allowlist](operations/founder-bootstrap.md) for normal
browser use. Application startup does not apply migrations. PostgreSQL and Redis
have no host ports; dashboard/API development ports bind only to loopback.

For frontend hot reload, stop the container dashboard before `npm run dev` so
both servers do not compete for port 3000. Keep the required local API and
dependencies running.

## Checks

```text
uv run --locked --all-packages python scripts/dev.py doctor
uv run --locked --all-packages python scripts/dev.py check
docker compose config --quiet
```

Doctor reads tool availability without installing anything. The check command
runs formatting, lint, typing, Python tests and frontend checks/build, stopping
at the first failure. `npm test` runs dashboard component regressions. Integration
tests need an explicitly named disposable PostgreSQL database; never use live or
ordinary development data. See the setup guide and CI workflow for exact commands.

## Repository map

| Path                      | Purpose                                               |
| ------------------------- | ----------------------------------------------------- |
| `apps/dashboard`          | Browser Command Center                                |
| `apps/api`                | Control plane and persistent authorization/scheduling |
| `packages/worker`         | Cross-platform worker and Consigliere                 |
| `packages/model-gateway`  | Interchangeable model providers                       |
| `packages/agent-runtime`  | Portable workflow contracts                           |
| `packages/shared-schemas` | Versioned shared contracts                            |
| `infrastructure`          | Containers, migrations and release templates          |
| `scripts`                 | Build, validation and operator tools                  |
| `tests`                   | Current unit, integration and browser regressions     |
| `docs/history/phases.md`  | Consolidated historical phase gates and evidence      |

Maintain current regression tests even when first introduced in an early phase.
Use [cleanup retention](operations/project-cleanup-2026-10-22.md) for generated
builds/caches. Packaging and release validation details remain in the
[release engineering guide](operations/production-release.md); its early candidate
examples are historical. Deployment and new milestone work require explicit scope.
