# Phase 09 real integration verification - 2026-10-16

Implementation is limited to Phase 09. Real Google authentication acceptance is
**incomplete** because the operator confirmed no OAuth client is configured.
No Google Cloud project/client, external account, DNS, Droplet or public service
was configured or deployed. No model was downloaded or inference runtime installed.

## Evidence boundaries

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

## Feature to API and persisted-state map

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

## Executed checks

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

## Remaining mocks, unavailable features and security limitations

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

## Changed files

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
