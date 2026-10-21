# Phase 12 and Consigliere verification — 2026-10-21

**Command Center and Consigliere 0.4.0-rc.3 are deployed** to the existing
DigitalOcean environment. The owner authorized implementation, builds and this
deployment in the Phase 12 assignment. The later native UI request is included.
Source was committed and pushed before building. Phase 13 has not begun.

## Delivered behavior and files

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
- Tests, packaging scripts, the [Phase 12 runbook](phase-12.md),
  [native UI guide](consigliere-ui.md), and
  [ADR 0019](../decisions/0019-bounded-worker-data-workloads.md) document the
  execution boundaries and setup.

## Executed checks

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

## Immutable artifacts

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

## Production verification

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

## Remaining acceptance and unsupported options

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
