# macOS worker preparation results â€” 2026-10-20

## Distribution status

Historical preparation snapshot: the native ARM64/Intel builds subsequently passed
as recorded in the [Actions build report](macos-worker-actions.md). The GitHub main
synchronization commits the prepared source; signing, physical recipient acceptance
and deployment of browser enrollment remain separate. The original results below
describe the earlier preparation task.

**No macOS installer is ready to distribute.** Local implementation, native build
automation and documentation are prepared. This Windows environment has no native
Mac build runner or Apple signing credentials. No `.app`, `.dmg`, notarization ticket
or binary release checksum was produced. Mocked packaging tests create disposable
test files only; those are not release artifacts.

The existing production worker protocol is unchanged. The new browser enrollment
extension is local source only: production API/dashboard deployment and migration
`0008_worker_enrollment` require separate approval. No private accounts were accessed,
users invited, messages sent, infrastructure changed, or releases uploaded/published.
No Git commit or push was made; this is a bounded preparation task, with no advance
to another roadmap milestone.

## Implemented behavior and files

- `packages/worker/src/godfather_worker/macos_app.py`: Tk/ttk app with actual
  hardware/model discovery, owner/name, comparison code, connection and job status,
  contribution selection, start/stop/pause, diagnostics, optional per-user login
  launcher, single-instance lock and local identity/settings removal.
- `packages/worker/src/godfather_worker/{desktop,keychain}.py`: existing v1 worker
  controller, in-memory enrollment, native Keychain adapter, scheduling budgets,
  fixed production origins, explicit shared-owner/workspace allowlists. No plaintext
  credential fallback, callback listener, paid inference or host tools.
- `packages/worker/src/godfather_worker/cli.py`: additive injectable credential,
  stop-event, transport and event-observer support; original CLI arguments remain
  compatible. Desktop reconnect waits behind active-session fencing rather than
  replacing a live process. Status comes from actual worker events.
- `apps/api/src/godfather_api/{enrollment,models,app}.py` and
  `infrastructure/migrations/versions/0008_worker_enrollment.py`: authenticated
  Google-owner approval, five-minute grants, owner cancellation, rate-limited
  private proof exchange, atomic single-use credential creation and audit.
- `apps/dashboard/src/app/worker-enrollment/page.tsx`,
  `components/{worker-enrollment,google-login}.tsx`, `lib/control-server.ts` and
  `app/api/auth/[action]/route.ts`: matching-code consent page, same-origin bridge
  allowlist and fixed enrollment return through existing Google login. No new
  authentication system or Google tokens on the worker.
- `scripts/{build_macos_worker,build_worker}.py`: native arm64/x86_64 detection,
  worker-only standalone app/DMG build, Tk smoke check, architecture/signature
  verification, immutable versioned output names and SHA-256 generation. Optional
  Developer ID signing/notarization requires explicit build flags and authorization
  to contact Apple. Without credentials the candidate is clearly labeled ad-hoc.
- `tests/test_desktop_worker.py`, `tests/integration/test_worker_enrollment.py`:
  isolated controller/store/package tests and real PostgreSQL enrollment tests.
- `packages/worker/macos/{README,TROUBLESHOOTING,ADMINISTRATOR}.md`, root README,
  worker distribution guide and ADR 0010: end-user instructions, native build/
  acceptance procedure, administrator handoff and security decision.

The pre-existing untracked `docs/operations/first-production-worker-2026-10-20.md`
was read for deployment evidence. During GitHub synchronization its source-control
version was sanitized to omit personal/private network details and production data;
the original remains in ignored private local evidence.

## Tests actually executed

| Check                                  | Result and boundary                                                                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Ruff formatting/lint                   | Passed, repository-wide                                                                                                              |
| Strict mypy                            | Passed, 93 Python files                                                                                                              |
| Windows unit suite                     | 179 passed; 168 integration cases deselected for their separate database run                                                         |
| Full real PostgreSQL integration suite | 166 passed in 107.26 seconds before the final two test additions                                                                     |
| Final enrollment integration suite     | 11 passed in 7.23 seconds, including the two added cross-admin/rollback tests                                                        |
| PostgreSQL migrations                  | Upgrade/downgrade, metadata consistency and restart checks passed in disposable `godfather_test`; normal/production schema unchanged |
| Dashboard lint and TypeScript          | Passed                                                                                                                               |
| Existing dashboard component tests     | 7 passed                                                                                                                             |
| Next.js production compilation         | Passed, including `/worker-enrollment`                                                                                               |
| Prettier / Git whitespace              | Passed                                                                                                                               |

The integration run used the real FastAPI/SQLAlchemy/PostgreSQL implementation,
read-only mounted current source and the existing disposable local test database.
Only Google's upstream OIDC service was mocked by the existing signed-token test
harness. Simulated advertisements occur only in isolated protocol tests. Cases
cover no-session approval denial, missing/expired/consumed/cancelled grants,
disabled/unlinked/unauthorized owner, owner injection and origin rejection,
concurrent exchange, digest-only secret persistence, audit redaction, another
administrator's cancellation denial, rollback on name conflict, unchanged
registration/heartbeat, active-session fence, reconnect after expiry and revocation.

Native API/store calls, controller shutdown/restart, scheduling budgets and packaging
commands are isolated unit tests with mocks. They are not actual Mac, Keychain,
Gatekeeper, Google-in-production or inference acceptance evidence. Earlier test
failures were corrected before the passing checks: an incorrect reconnect test
attempted to replace a still-active session, and formatting/typing/test-double
issues were resolved. No known executed check remains failing.

## Remaining limitations and next action

1. Build separate arm64 and x86_64 DMGs on native Mac hosts using the troubleshooting
   guide. Complete clean-host install, GUI/accessibility, Keychain, native inference,
   restart/revocation, signed upgrade, login startup and uninstall acceptance.
   Intel dependency compatibility and minimum OS remain unverified until then.
2. Provision Developer ID/notarization only through an approved operator workflow.
   An ad-hoc development candidate cannot provide a frictionless ordinary install.
   Release license notices/build-hook locking also need operator review.
3. Review and obtain approval for the additive server deployment. The current live
   coordinator does not gain browser enrollment merely from these local changes.
4. Arrange private Tailscale TCP 443 permissions and API hostname resolution for
   each Mac. The installer does not edit DNS, hosts files, routers or tailnet policy.
5. Runtime contribution is intentionally narrow: CPU-only mode registers/heartbeats
   without executing jobs or tools; opt-in existing Ollama supports local text
   inference. Concurrency is fixed at one. CPU/RAM controls are scheduling budgets,
   not hard OS/inference limits. GPU capability is reported locally without a GPU
   scheduling budget. Login startup starts the app/worker with saved settings only
   after explicit local opt-in.
6. Lost exchange responses or failed Keychain writes require owner revocation of
   any pending credential and a fresh pairing. Existing revoked names remain
   reserved; choose a new display name. App removal alone does not revoke access.

Stop here. Recommended next work is native macOS acceptance and release review,
followed only by separately authorized deployment/distribution.
