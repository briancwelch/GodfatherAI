# The Godfather

Private, cross-platform AI orchestration platform for two founding administrators in Las Vegas and Chino Hills.

One developer builds the platform for both administrators. The second administrator does not need a development environment.

**Coordinator 0.7.0-rc.2; Consigliere 0.7.0-rc.1 are published.**
[Workspace contribution verification](docs/operations/workspace-contribution-verification-2026-10-22.md).
Workspace contribution replaces sharing ID entry with
**Contribute this computer to my workspaces**. Install, connect, approve and use
workspace membership for ordinary/distributed work. Existing computers keep their
permissions until their owners opt in. See [simple contribution](docs/operations/simple-contribution.md).
Models → Add / use model lists installed local and connected API models. The
worker update enables basic model-only agents while preserving existing settings.

**Workload release: 0.4.0-rc.3 — Phase 12 images, analytics and reporting.** See the
[Phase 12 runbook](docs/operations/phase-12.md) for owner-controlled worker setup,
bounded dataset uploads, deterministic calculations and downloadable reports.
No real dataset or paid image call is authorized; live customer acceptance remains
pending. Google Sign-In remains separate from data-source and provider consent.
Existing [Phase 11 coding/BYOK](docs/operations/phase-11.md) functionality is preserved.

## Start here

The [model setup guide](docs/operations/consigliere-ui.md#add-a-local-model)
explains local/API model selection, workspace authorization and optional downloads.
Installed models are labeled and cannot be selected for another download.
All three updated installers are under **Nodes → Downloads**. Existing-model use,
downloads and account API access retain their separate owner permissions; API
runs require explicit provider consent.

The authorized [Command Center management update](docs/operations/command-center-management.md)
adds AJAX bulk deletion, optional workspace ZIP archives with animated progress,
top/bottom pagination and saved-user permission editing. It requires only the
coordinator/dashboard update; that update did not change Consigliere installers.
The [deployment verification](docs/operations/command-center-management-verification-2026-10-21.md) records activation and preservation checks.

**Consigliere** is the new name of The Godfather AI desktop worker. The current
UI update adds normal window resizing, an embedded Projects tab, a compact
navy/cyan command ribbon and expanded owner-local Settings. See the
[Consigliere UI and upgrade guide](docs/operations/consigliere-ui.md).
Worker downloads are under **Nodes → Downloads**. Tailscale is detected when
installed and remains optional; existing private routing is preferred where
configured. Consigliere **0.7.0-rc.1** is the current worker. The earlier coordinator
release introduced Phase 12;
see the [verification report](docs/operations/phase-12-verification-2026-10-21.md).

Earlier release **0.3.2-rc.1** added accomplishment-first coding results and
**Run agent → Preview changes → Apply to my project**. See the
[result/application guide](docs/operations/results-and-apply.md). Application
requires the updated worker and explicit local project permission. The versioned
[result action design](docs/decisions/0018-result-preview-and-actions.md) keeps
future presentation changes independent of worker builds.
The [deployment report](docs/operations/results-apply-verification-2026-10-21.md)
records native installer checks, source CI, data preservation and public checks.

Usability release **0.3.1-rc.3** adds account API key entry with
provider-managed billing, local coding-project setup and tray/window improvements.
See its [verification](docs/operations/coding-account-verification-2026-10-21.md)
and [setup guide](docs/operations/coding-and-account-setup.md). It requires a new
coordinator migration and worker build; it is deployed. Coordinator
**0.3.1-rc.4** adds explicit reconnection under the same computer name
and node history, using those unchanged worker installers. See the
[reconnection report](docs/operations/worker-reconnection-2026-10-21.md).

**Current usability milestone:** [install and connect](docs/operations/simple-onboarding.md).
The normal worker is a tray app with automatic browser pairing, saved OS credentials
and outbound HTTPS. Tailscale is optional. Open
[Command Center](https://app.the-godfather.ai) → **Nodes → Connect a computer**
for Windows, Apple silicon and Intel Mac downloads. The updated installers passed
the [recorded local and native checks](docs/operations/phase-12-verification-2026-10-21.md).
That report also records coordinator activation and public checks.
Publisher signing and physical recipient
acceptance remain pending; the Windows/Mac installers are unsigned/ad-hoc signed
candidates.

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

Command Center maintenance: [UI changes and verification](docs/operations/command-center-ui-2026-10-22.md) adds shared appearance settings, readable owner/audit identities, worker build status and AJAX credential deletion. The previous **0.4.2-rc.2** [onboarding repair](docs/operations/worker-onboarding-2026-10-22.md) introduced pairing, build-version reporting and connection indicators. Quit the existing tray worker before installing the replacement; saved identities and settings are preserved.

**Distributed Jobs (0.6.0-rc.1):** [Distributed Jobs](docs/operations/distributed-jobs-2026-10-22.md) adds selected-node parallel tasks, durable dependency handling, final synthesis and workload graphs. The coordinator and updated Windows, Apple silicon and Intel Mac installers are deployed. Update participating workers through File > Check for updates before using synthesis.

## Local development

The previous **0.5.0** release introduced in-app worker updates and local Ollama
setup, a system Overview and Workspaces directory, personal profiles, and separate
Images / Analytics and Reports workflows. See the
[milestone guide](docs/operations/worker-readiness-and-workspaces-2026-10-22.md).
Existing workers need one normal installer upgrade to acquire the updater.

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
