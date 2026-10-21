# The Godfather

Private, cross-platform AI orchestration platform for two founding administrators in Las Vegas and Chino Hills.

One developer builds the platform for both administrators. The second administrator does not need a development environment.

**Current assignment: Phase 11 coding agents, independent frontier-provider connections, readable results and release status.** See the [Phase 11 runbook](docs/operations/phase-11.md). Google Sign-In authenticates users; separate worker-local OpenAI/Anthropic API keys authorize paid inference. Release `0.2.0-rc.5` includes the invitation onboarding repair; see [repair verification](docs/operations/onboarding-repair-2026-10-20.md) and [Phase 11 deployment verification](docs/operations/phase-11-deployment-2026-10-20.md). No paid API calls are authorized. The existing Windows worker reconnected after the upgrade; live coding acceptance still requires an updated worker with owner-approved repository configuration. Mac signing and physical recipient acceptance remain pending; see the [Mac user guide](packages/worker/macos/README.md).

## Start here

**Current usability milestone:** [install and connect](docs/operations/simple-onboarding.md).
The normal worker is a tray app with automatic browser pairing, saved OS credentials
and outbound HTTPS. Tailscale is optional. Native installers and the guided
coordinator setup are candidates until their recorded build and deployment checks
pass; this source change does not activate new public routes on the existing server.

For inviting another user, follow the [onboarding guide](docs/operations/user-onboarding.md).
Invited users select Continue with Google using the exact invited email; no code
is required. Email delivery is manual, and Tailscale access is separate.

1. Read [AGENTS.md](AGENTS.md) and the [UI/UX specification](docs/design/UI-UX.md).
2. Follow the [Windows, macOS, and Linux setup guide](docs/operations/setup.md).
3. Review [Phase 01 validation](docs/operations/phase-01.md) and [Phase 02 setup and results](docs/operations/phase-02.md).
4. Follow [Phase 03 startup, credential provisioning and simulated workers](docs/operations/phase-03.md).
5. Use [Phase 04 jobs, scheduler simulation and validation](docs/operations/phase-04.md) and the [job protocol](docs/protocols/jobs-v1.md).
6. Follow [Phase 05 provider setup and inference validation](docs/operations/phase-05.md), [architecture](docs/architecture/model-gateway.md), and the [inference API contract](docs/protocols/inference-v1.md).
7. Use [Phase 06 agent definitions, local commands and recovery evidence](docs/operations/phase-06.md), [runtime architecture](docs/architecture/agent-runtime.md), and the [workflow API contract](docs/protocols/agents-v1.md).
8. Review [Phase 07-08 recovery evidence](docs/operations/phase-07-08.md).
9. Follow [Phase 09 Google setup and migration](docs/operations/phase-09.md), [authentication architecture](docs/architecture/authentication.md), and [real integration verification](docs/operations/phase-09-integration.md).

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

Open **http://127.0.0.1:3000** for the Command Center and **http://127.0.0.1:8000/api/v1** for the API. Configure Google OIDC and the [one-time founder email allowlist](docs/operations/founder-bootstrap.md), then use normal Google sign-in; no manual ID token is required. Existing accounts still require explicit ownership-preserving linking. Subsequent users require invitations; backend permissions remain enforced. Both ports bind to `127.0.0.1`. PostgreSQL and Redis have no host ports. Health probes are at **http://localhost:8000/health/live** and **http://localhost:8000/health/ready**. Readiness requires the current migration head; API startup never applies migrations automatically.

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

| Path                      | Purpose                                                                   |
| ------------------------- | ------------------------------------------------------------------------- |
| `apps/dashboard`          | Next.js, strict TypeScript, Tailwind and local operational Command Center |
| `apps/api`                | FastAPI foundation, configuration, logging and SQLAlchemy models          |
| `packages/worker`         | Outbound registration, heartbeats, synthetic jobs and opt-in inference    |
| `packages/model-gateway`  | Portable Ollama/OpenAI-compatible discovery and text inference adapters   |
| `packages/agent-runtime`  | Portable sequential workflows and validated read-only tool contracts      |
| `packages/shared-schemas` | Versioned worker registration/health contracts                            |
| `infrastructure/docker`   | Dashboard build/runtime container                                         |
| `scripts`                 | Portable development checks                                               |
| `tests`                   | Tooling/API unit tests and guarded real-PostgreSQL integration tests      |
| `docs/design`             | Authoritative frontend design guidance                                    |
| `docs/architecture`       | Architecture and cross-platform compatibility                             |
| `docs/decisions`          | Architecture decision records                                             |
| `docs/operations`         | Setup, phase gates, troubleshooting                                       |
| `.github/workflows`       | Cross-platform checks and Linux container smoke checks                    |

Future packages and infrastructure are created only when their milestones require them.

## Safety and milestone boundaries

The dashboard uses Google OIDC and HttpOnly/SameSite application sessions through a same-origin server bridge. Google tokens never enter browser storage. Workspace membership and node-owner consent remain separate from platform roles. No Google client or public deployment is configured automatically; see the [authentication architecture](docs/architecture/authentication.md).

PostgreSQL is authoritative for node identities, heartbeats, jobs, attempts, leases, retries and events. Redis is transient. Workers connect outbound, and owners control their host permissions. A platform administrator cannot bypass those restrictions.

`app.the-godfather.ai` and `api.the-godfather.ai` are proposed names only. Nothing here registers domains, configures DNS, provisions a VPS, or authorizes deployment. Production targets an independent Ubuntu DigitalOcean coordinator using the same containerized application architecture with separately reviewed environment configuration.

Historical phase reports retain their original acceptance boundaries. The current Phase 11 assignment supersedes earlier BYOK planning-only limits; live spending, new infrastructure, DNS/Google Cloud changes and unrelated account access remain outside its authorization.
