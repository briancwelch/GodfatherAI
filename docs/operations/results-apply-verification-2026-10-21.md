# Result previews and project application — 2026-10-21

Owner-authorized Phase 11 usability update, candidate **0.3.2-rc.1**. The owner
initially requested Command Center-only changes, then explicitly authorized a
worker update after inspection showed that existing workers had no apply action.
See the [user guide](results-and-apply.md) and
[architecture/extension boundary](../decisions/0018-result-preview-and-actions.md).

The Command Center leads with accomplishments, actual test-command outcomes and
per-file patches. Application uses a separately approved, exact-node job and
explicit local project opt-in. Existing edits in affected files block application;
unrelated edits and the index remain intact. Integrity, paths, types, source commit,
permissions, lease/fencing and duplicate invocation are rechecked. Uncertain side
effects never retry automatically. No schema migration or provider/model download
is introduced. Presentation changes for text, images, reports, tables and charts
remain independent of worker builds; unknown native operations require separately
implemented/advertised worker capabilities.

## Executed local checks

- Full disposable PostgreSQL/API/Python suite: **475 passed, 2 optional pinned
  container checks skipped**. Includes actual Linux Git application, conflicts,
  hidden edits, source/target scope, owner/workspace boundaries, duplicate approval,
  one-time invocation, stale fencing, permission withdrawal and cancellation.
- Native Windows non-integration suite: **262 passed, 3 skipped** (two optional
  pinned-container checks and symlink creation unavailable to this user). Later
  focused real-Git checks passed after local receipt persistence refinements.
- Ruff formatting/lint and strict mypy passed, 138 source files checked.
- Dashboard formatting, lint, strict TypeScript, **19 component tests** and
  production build passed. Existing image/document/table/chart rendering remains
  covered alongside coding, failed/absent tests and confirmed/uncertain application.
- Fresh Edge fixture checks passed at 1440px and 390px: accomplishment summary,
  per-file diff, collapsed diagnostics, disabled action until review, explicit
  confirmation, immutable reference-only request, confirmed result polling and no
  browser errors. Screenshots/evidence: `.cache/result-actions/`.
- Native Windows tray/window smoke passed with synthetic identity/controller:
  project creation, local apply opt-in/out, persistence, pause/resume and removal.

These checks use disposable repositories, local fixture accounts/model responses
and the isolated `godfather_test` database. They do not use a real provider key,
billable inference, production human session or another owner's host permissions.
Git was added only to the development test image for real patch validation;
production coordinator images do not gain Git or execute generated code.

## Build and deployment status

All three native installers were built from clean source
`c3b7450191ff812c163c83698018b80e4e7b2597`. Windows temporary install/reinstall,
packaged Tk/tray and isolated Credential Manager checks passed. Both native Mac
builds, real Git protection checks, tray/window lifecycle and DMG checks
[passed on GitHub runners](https://github.com/briancwelch/GodfatherAI/actions/runs/39677909286).
The existing unsigned/ad-hoc signing status remains; no Developer ID/notarization
or physical recipient acceptance is claimed.

| Package                                                 | SHA-256                                                            |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `godfather-worker-0.3.2-rc.1-windows-x64-setup.exe`     | `4b8acc218b4f85aadae2df7a3a4cbfcfac99b6c1b9478c51e6a088697644722b` |
| `godfather-worker-0.3.2-rc.1-macos-arm64-installer.dmg` | `1ad1db19fb262593edfefd708225307f776fdfea7e9f1fb8ef60be36325a58d1` |
| `godfather-worker-0.3.2-rc.1-macos-x64-installer.dmg`   | `4563b2a2ed506c4b1270f8ba81969e1e6c55e20ec36c98e59d3fe037bb60f029` |

The coordinator archive is `godfather-0.3.2-rc.1-linux-amd64.tar.gz`, SHA-256
`b16324b15b1516b3fc206222a1343545e985eab75986093b566cc78e2d5346a9`.
It contains those checksum-verified downloads and the same clean source revision.
Saved-package image/config, migration, health, anonymous-denial, paired
database/artifact restore and restart checks passed; evidence is
`.cache/release-tests/189ae42ccd2d/result.json`.

[All source CI jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/39677909626),
including native Python/dashboard matrices and Linux PostgreSQL, worker-process,
100-job scheduler, inference and interrupted-workflow recovery gates.

Preflight confirmed the existing rc.4 target healthy at migration
`0011_worker_reconnection`, with no active jobs. Automatic approval review rejected
transfer because exact destination/payload approval was required. No upload or
activation occurred from that rejected call. The concrete approval request names
the existing `root@137.184.227.74` deployment at `/opt/the-godfather`, the verified
coordinator/worker packages and a read-only preservation-check script. Production
activation remains pending that approval; all build and source CI gates passed.

Normal owner project acceptance still requires installing the new worker and
opting in locally. Keep affected files idle during application: editor writes
are not coordinated by the worker lock. Interrupted filesystem writes require
inspection of the project and local Git-directory apply receipt; cancellation
does not undo completed effects. No later workload phase was started.
