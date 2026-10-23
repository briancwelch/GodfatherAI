# Workspace contribution implementation and release

The owner requested install-and-contribute onboarding without manually entering
user, node or workspace IDs. The implementation adds one visible local choice,
**Contribute this computer to my workspaces**. Fresh installs offer it before
Connect/approval; existing installations preserve their exact previous permissions
until the owner enables it. Normal and distributed jobs share the same
membership-based scheduling permission.

Main changes:

- `godfather_contracts/__init__.py`: additive false/omitted-by-default sharing field.
- API `nodes.py` and `scheduler.py`: persist only worker-authenticated opt-in,
  resolve both parties' current workspace access, preserve legacy lists, withdraw
  consent when an old/disabled registration replaces it. Existing model-inventory
  authorization now compares identifiers instead of unhashable inventory objects.
- API `distributed.py`: distinguish blocked workspace models and unauthorized API
  connections from missing sharing permission, with task/computer names.
- Worker `desktop.py`, `desktop_app.py`, `desktop_settings.py`, `cli.py`: one-choice
  first-run contribution, no ID fields, installed-model discovery, detected fresh
  capacity, truthful missing-model status and automatic idle-safe re-registration.
  Account credentials, downloads, coding/files and other workload opt-ins remain
  separate. Pause/Quit cancels pending automatic restart.
- Command Center node/detail, pairing and distributed empty-state copy; active
  onboarding guides; [ADR 0024](../decisions/0024-workspace-contribution.md).
- Unit/contract tests, real-PostgreSQL ordinary/distributed membership tests, native
  desktop acceptance and existing isolated browser regression.

Validation uses only a separately labeled, disposable PostgreSQL container bound
to an ephemeral loopback port and `godfather_test`. Existing local application
containers, identities and credentials are preserved. No real inference, paid
provider calls, model downloads or contributor-host permission changes are used.

The final complete Python run passed **591 tests, 4 skipped** in 193 seconds with
real PostgreSQL. Skips require optional pinned coding/data sandbox images or a
host permission to create symlinks. The final source/native checks and focused
database results below include all subsequent test corrections.

Before packaging, strict mypy (174 files), Ruff lint/format, strict TypeScript,
ESLint, production dashboard build and all 32 dashboard tests passed. The 34-case
focused database rerun passed, including new ordinary-job workspace joining,
membership withdrawal blocking an active report, dedicated/private opt-out,
workspace model restriction, paid-key denial, future workspace membership,
registration withdrawal and cross-user distributed model execution with empty
sharing lists. Legacy explicit sharing still passes.

Native Windows source UI acceptance passed fresh and saved-identity pairing,
tray restore, resizing, Projects, Settings without ID fields, model-download
consent, pending model/share settings applying after current work, pause/quit and
truthful no-model status. Isolated Edge acceptance passed submission/error cases,
graphs, results, cancellation, stale controls, dark theme and 390px layout.

Ignored evidence is under `.cache/simple-contribution/` and
`.cache/distributed-ui/`. Native recipient setup, physical inference/backends and
billable calls remain separate from these synthetic tests. The release candidate
uses coordinator **0.7.0-rc.2** and workers **0.7.0-rc.1**, published through
the existing authorized native-build, backup and release gates.

## Published installers and coordinator

All three native installers were built from clean source
`ec46b5ff092b0faeba96d624c0bc1c87a90dc031`. Windows temporary install/reinstall,
frozen GUI/tray and isolated OS credential-store checks passed. Both jobs in the
[native Mac workflow](https://github.com/briancwelch/GodfatherAI/actions/runs/39880933287)
passed architecture, source GUI lifecycle, DMG/checksum, bundled framework startup
and unapproved pairing checks. Candidates retain their existing unsigned/ad-hoc
signing status; physical recipient installation and model execution remain separate.

| Installer         | SHA-256                                                            |
| ----------------- | ------------------------------------------------------------------ |
| Windows x64       | `52e8f31bea440a696a3a027b148f81c9416fcf9977577d1c089a7be7570dbd9e` |
| Mac Apple silicon | `f91e6332cd96418bb012958e2443f47297234254f61f064b18ca8adf88f14b76` |
| Mac Intel         | `4214cec3e16d20206192334f96aab56fde1f5f7521d66179f0982fd4103f1659` |

The coordinator was built from clean source
`b85477e863ed3a6bda85618c50d6081a522f5b45`. It differs from the worker source only
in an optional-Tk test guard: headless Python/container runners must skip the GUI
method test when Tk or its native library is absent. Native packaging jobs execute
the real Tk checks. Git confirms runtime source is identical across these revisions.
The earlier local coordinator candidate was retained and never activated; the final
immutable package uses the corrected test-source revision.

Coordinator archive SHA-256:
`35b335d7f33791414ef073f547c4f3bb6cce0b04860ed221b0795a0e8afded9c`.
All ten disposable release gates passed, including actual PostgreSQL/artifact restore,
repeat migrations, restart persistence, private services, anonymous denial and six
proxied installer downloads. Receipt: `.cache/release-tests/5d4141c49842/result.json`.
The task's separately labeled PostgreSQL test container and the release-test project
were removed; all four original local application containers were preserved.

The VPS activated `/opt/the-godfather/releases/godfather-0.7.0-rc.2-linux-amd64`.
All five services are healthy on exact release images; only Caddy publishes ports.
Migration remains `0016_distributed_jobs`, and the production environment is
byte-identical with mode 600. Stable fingerprints matched 2 users, 2 Google
identities, 3 workspaces, 1 membership, 6 credentials, 4 node ownership/policy records,
12 jobs, 7 agents, 6 artifacts, 3 checkpoints, 4 provider connections and 1 encrypted
account key. No permission was enabled on an existing contributor computer.

Paired backup `/opt/the-godfather/state/backups/20261023T011118-1408936` passed
checksums, PostgreSQL dump listing and artifact gzip integrity. No production restore
was performed. Server evidence:
`/opt/the-godfather/state/deployments/workspace-contribution-20261023-rc2`.
Ignored local release/public evidence: `.cache/simple-contribution/release/`.

All **68 public HTTPS checks passed** through normal DNS and verified TLS after
activation. All three 0.7.0-rc.1 installers were downloaded and hash-verified through
both public hostnames (six complete checks); both runtime catalogs matched. The
new manifest is published only with the updated coordinator, preserving the
required coordinator-before-worker upgrade order. Authentication, foreign-origin
denial and private API boundaries passed. Verification created no live accounts,
enrollments or distributed jobs and made no billable calls. No known serious
unresolved implementation or release errors remain.

All eight jobs in the final [source CI run](https://github.com/briancwelch/GodfatherAI/actions/runs/39882076014)
passed on source `b85477e863ed3a6bda85618c50d6081a522f5b45`: Python 3.12/3.14 and
Windows/macOS/Linux checks, all dashboard jobs, and the real Linux container suite.
The process probes also passed four workers, 100 jobs, API restarts, lease expiry,
loopback model inference, durable agent checkpoints and process interruption/recovery.
