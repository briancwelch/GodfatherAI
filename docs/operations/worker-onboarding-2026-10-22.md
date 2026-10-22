# Worker onboarding repair - 2026-10-22

**Released:** coordinator and Windows/Apple silicon/Intel workers **0.4.2-rc.2**.
Download from **Nodes > Connect a computer** in
[Command Center](https://app.the-godfather.ai). Quit the existing tray worker before
installing the replacement. Existing local identities, settings and permissions
retain their locations. Fresh computers use Connect and matching-code approval;
Reconnect is only for replacing a connection under an existing owned name.

The owner authorized repairing fresh Windows/macOS onboarding, incorporating the
existing version-reporting changes, rebuilding native workers, publishing them in
Command Center, and pushing the final changes to GitHub main.

## Behavior

The worker now paints its comparison code before opening the browser and selects
the Connection tab. A failed exchange keeps the previous code visibly marked
inactive, with instructions to close the approval page and start Connect again.
Certificate, DNS and timeout failures have specific, secret-free messages.
The previous flow cleared the code immediately after a polling failure.

Worker HTTPS retains system trust and adds a bundled Mozilla public-root store
from certifi. This dependency supplies public roots on fresh Windows installations
and standalone Mac Python builds; certificate and hostname verification remain
mandatory. Both packaging paths explicitly include the bundle. No trust bypass,
credential fallback, model download or host permission change is introduced.

The exact transport error on the recipient's fresh Windows computer was not
available. Source and an isolated frozen diagnostic on the developer's Windows
host both reached the expected unapproved HTTP 404. Missing system trust is covered
by a regression starting with an empty CA store, rather than asserted as a proven
recipient root cause.

The window title and footer show the embedded build version, or explicitly identify
an unreleased source checkout. Registration advertises that same build identity
through the previously implemented Command Center contract. A header badge shows
Disconnected, Awaiting approval, Connecting, Connected, Paused and recovery/refusal
states. Connected requires an actual registration/heartbeat acknowledgement.

## Verification and release

Local validation: 310 non-integration tests passed, four optional environment tests
skipped; Ruff and strict mypy passed. Windows native Tk/tray checks verified the code
before approval, automatic connection, acknowledgement-driven state, saved-session
restart, pause/resume, settings, projects and tray restoration. No private Google
account or actual recipient enrollment was used.

Frozen `--self-test` loads bundled trust and records the embedded version. With
`GODFATHER_SELF_TEST_ORIGIN` set, it sends a fresh, unapproved pairing exchange to
that origin and requires HTTP 404; it cannot save credentials or register a node.
The Mac release workflow enables this real-coordinator check for both native
architectures. Lost responses or secure-store failures remain non-replayable.

Native build and release evidence is recorded below. Physical recipient installation/pairing and publisher signing
remain separate acceptance; Mac candidates use ad-hoc signing.


## Native candidates and source

All three **0.4.2-rc.2** installers were built from clean source
`c84c4745503a1455107f62bc457bd608bab27d4b`. Later commits correct only the
headless GUI regression's skip/formatting and documentation, not shipped runtime
code. Candidate rc.1 was not published. The first Intel smoke exceeded its old
15-second overall deadline; the final run uses a 60-second failure deadline and
passed, without sleeps as success criteria.

- [Apple silicon and Intel native build checks](https://github.com/briancwelch/GodfatherAI/actions/runs/39808595580): passed both architectures, source UI lifecycle, frozen app, real HTTPS unapproved pairing, DMG, signature, architecture and native-library checks.
- Windows temporary install/reinstall and frozen Tk/tray/HTTPS self-test passed;
  the frozen report states `passed` and `worker_version: 0.4.2-rc.2`.
- An additional real-coordinator test started with zero trusted CAs, loaded the
  packaged 120 public roots, and reached HTTP 404 while retaining certificate and
  hostname verification. No real enrollment approval or saved credential was used.
- The setup self-test initially required an automatic-review retry after proving
  its TemporaryDirectory targets in source. The exact isolated test then passed;
  the normal installed worker and its identity were not replaced.
- Disposable release checks passed all ten gates: image identity/architecture,
  production/Caddy config, shell syntax, migrations, empty identity bootstrap,
  private health, proxy authentication, all installer downloads on both hostnames,
  actual database/artifact restore, and persistence/restart. Evidence:
  `.cache/release-tests/145a92d76dfe/result.json`.

| Installer | SHA-256 |
| --- | --- |
| Windows x64 | `0b28e9e4b773aad91997407c219132b907d07c7fde90cead9429cfe940bb2efb` |
| Mac Apple silicon | `7f3060b7502c6004e040bc006cde49d743be3f3fbd267d6210476d8efc2a8a93` |
| Mac Intel | `1b4334c593b0558b09a88d9db886e63ced374a82e0d507f9b8112151527759e2` |

Coordinator package: `dist/godfather-0.4.2-rc.2-linux-amd64.tar.gz`, SHA-256
`f180c150e1964cffc0d7466ba9e5eaac87fcfd9894ff25d4346892dbf6996714`.
The existing schema remains `0014_command_center_appearance`.


## Final source CI

[Repository checks](https://github.com/briancwelch/GodfatherAI/actions/runs/39809690373)
passed all eight jobs on `abea8767d348ac5747ce3128b5fa4076bcc47aa6`.
The disposable PostgreSQL/API container run completed **541 passed, 4 skipped**;
the headless image skips only the GUI adapter check and explicitly optional
sandbox-image checks. Native Windows/Mac GUI checks ran separately. Python
3.12/3.14, Windows/macOS/Linux, dashboard format/lint/types/component tests/build/
audit, real API/database restart and outage, four independent workers, the
100-job scheduler with lease expiry, inference and checkpoint interruption/recovery
all passed. Source runners skip integration tests when no disposable database is
configured; the container job executes those tests against real PostgreSQL.

The staged archive at
`/opt/the-godfather/incoming/godfather-0.4.2-rc.2-linux-amd64.tar.gz.upload-f180c150`
matched the trusted local hash. The extracted new release passed its own checksums
and configuration checks. Initial automatic approval review blocked activation
before any service change, requesting explicit consent for the live upgrade and
brief interruption. The original `0.4.1-rc.6` service remained current at that point.

## Authorized production activation

The owner then explicitly approved activation, backup and brief service interruption.
The existing verified installer upgraded the coordinator to
`/opt/the-godfather/releases/godfather-0.4.2-rc.2-linux-amd64`. All five services
passed health checks; API metadata reports version `0.4.2-rc.2` and the exact
native-build source `c84c4745503a1455107f62bc457bd608bab27d4b`. Schema remains
`0014_command_center_appearance`. API, dashboard, PostgreSQL and Redis have no
published host ports; the existing proxy remains the public entry point.

The production environment remained byte-identical with mode 600. Before/after
record fingerprints matched for 2 users, 2 Google identities, 3 workspaces,
1 membership, 4 credentials, 2 node ownership/policy records, 9 jobs, 5 agents,
6 artifacts, 3 checkpoints, 2 provider connections and 1 encrypted account key.
No account key was decrypted. There were no active jobs at upgrade or postflight.
Node health after activation was one online and one offline; no contributor
computer was remotely installed, reconfigured or granted new permissions.

Paired backup: `/opt/the-godfather/state/backups/20261022T195238-1266002`.
Its checksums, PostgreSQL dump listing and artifact gzip integrity passed.
Actual restore testing used the disposable release environment; production
restore was not performed. Previous release and download artifacts are retained.

Deployment evidence is ignored under `.cache/worker-onboarding-2026-10-22/`;
server-side preservation evidence is under
`/opt/the-godfather/state/deployments/worker-onboarding-20261022-rc2`.

All **50 public HTTP checks passed** using normal DNS and verified TLS. The
download manifest matches the staged release, and all three new installers
returned HTTP 200 with exact SHA-256 matches on both existing public hostnames
(six complete download/hash checks). Fresh unapproved enrollment returns the
expected 404; unauthenticated worker registration, private APIs, account/workload
operations, appearance and credential deletion remain denied. Foreign-origin
mutations remain blocked. No production job, account login or real enrollment
approval was performed to manufacture acceptance.

Actual recipient Google sign-in and fresh Windows/Mac installation still require
physical acceptance. Native runner, packaged HTTPS and synthetic lifecycle checks
do not substitute for that acceptance. No next implementation phase is started.
