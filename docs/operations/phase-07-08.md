# Phase 07–08: Automatic failover and local Command Center

Current authentication is documented in [Phase 09](../operations/phase-09.md).
Google OIDC/application sessions replace human bearer login in normal operation;
worker machine credentials remain independent. Earlier bearer/simulator procedures
below are historical and restricted to isolated automated tests. Phase 09 does not
authorize public deployment or Phase 10.

The user explicitly authorized these phases as one combined milestone. Stop after
Phase 08. Phase 09 and BYOK implementation remain unapproved.

## Prerequisites

Before implementation, repository checks passed and all 233 PostgreSQL-backed tests
passed. Phase 06's native mock acceptance verified process interruption, actual API
restart, durable checkpoint restoration, no repeated committed step and stale-write
rejection: `.cache/phase06-runs/1dfdfb17d06a4b9c916d9ea59dc3c3ec/result.json`.

Real Phase 05 `qwen3:8b` initially exhausted the acceptance command's default 32-token
budget before returning visible text. Revalidation with an explicit 2048-token
budget passed streaming, non-streaming and result durability across an actual API
restart: `.cache/phase05-runs/3431d11e4a744a80b46d749decfe295f/result.json`.
No model was downloaded, provider account accessed or billable inference enabled.

## Recovery and portability

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

## Local startup

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
file created by [Phase 03 provisioning](phase-03.md). Enter only its `token` value
in the local connection form. No account or credential is preseeded. The server
validates it against the API before setting an eight-hour HttpOnly, SameSite=Strict
cookie. Disconnect removes that cookie; provisioning revocation invalidates backend
access immediately. Native/container dashboards share no global admin credential.

## Routes and integrations

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

## Combined browser demonstration

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

## Security limits and future work

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

## Validation results

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

## Files changed

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
