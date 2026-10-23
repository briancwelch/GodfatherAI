# Worker project recovery and heartbeat verification

The owner requested preventing Carbon's missing-project-image startup failure,
showing exact recovery instructions for other owners, retaining the Nodes EKG's
previous heartbeats, and aligning the Distributed Jobs execution choices.
The owner explicitly approved pushing and deploying the follow-up. Coordinator
and Consigliere **0.9.0-rc.2 are published** at
[Command Center](https://app.the-godfather.ai), replacing 0.9.0-rc.1.

## Behavior

- Missing coding-project dependencies withhold only affected repositories from
  coding and Apply advertisements. Other enabled capabilities can connect.
- Saved project IDs, scope, image pins and permissions remain unchanged. A
  successful Pause/Resume after repair restores the same grant.
- A persistent Connection panel names the affected project and problem; Projects
  shows availability, the exact saved image when missing, and repair steps.
- Read-only startup probes distinguish unavailable folders, Git, local Docker,
  Windows containers, missing/non-Linux images and timeouts. Events contain only
  fixed codes and UUIDs. Nothing is installed, pulled or reconfigured.
- The EKG scrolls the timestamps actually observed during the mounted view for
  up to 60 seconds/64 receipts. New heartbeats retain earlier pulses. Duplicate
  snapshots add none. Offline/stale traces dim and expire; reduced-motion mode
  uses slower updates. Reloading starts a new observation window.
- Distributed Jobs places its execution-setup legend above a separate choice
  grid. All three choices align in one desktop row and stack within the mobile
  viewport, retaining their radio-group semantics.

The Carbon diagnostic established the missing image and startup failure. The
owner subsequently confirmed that an earlier requested cleanup removed the image;
the update's restart exposed it. The updater and release scripts inspected here
do not prune Docker images. Installer regression coverage verifies exact saved
project and cloud-image options survive automatic updates. Future cleanup must
retain image pins referenced by saved projects and data workload settings.

See [recovery steps](worker-project-recovery.md) and
[ADR 0028](../decisions/0028-optional-project-readiness.md).

## Local evidence

| Check                                        | Result                                                                                                                                                          |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Offline Python suite                         | 379 passed; four explicitly optional physical sandbox/symlink checks skipped; 279 PostgreSQL checks deselected                                                  |
| Dashboard components                         | 42 passed, including retention, deduplication, expiry, future/invalid data and bounded memory                                                                   |
| Python formatting/lint/types                 | Passed; 183 source files type-checked                                                                                                                           |
| Dashboard formatting/lint/strict types/build | Passed                                                                                                                                                          |
| Native Windows Tk/tray lifecycle             | Passed fresh and saved-identity fixture flows, warning panel and selected-project instructions, repair clearing, resizing, settings and idle-safe update checks |
| Fixture browser acceptance                   | Passed, including two retained pulses, movement between receipts, duplicate refresh, offline history, reduced motion and expiry with no page errors             |

The final browser run also passed equal-width execution choices in one desktop
row and stacked choices within a 390-pixel viewport, with no page errors.

Python regression tests exercise the actual desktop-to-CLI registration path with
mocked dependencies on Windows/macOS/Linux profiles, including mixed ready/unready
projects, all-projects-unavailable, retained IDs/scopes, restored Apply grants and
no private process output in events. These are deterministic profiles rather
than physical macOS/Linux inference acceptance.

Native fixture screenshots are under `.cache/worker-recovery/`. Browser evidence
is under `.cache/distributed-ui/`. The browser suite's existing processing-toast
selector was updated to the Bootstrap progressbar role before the successful run.
No private account sign-in, real job execution, provider call or billable inference
was needed for these checks. Production activation and native packages remain
separate from local source validation.

## Published release

The coordinator uses clean source `565daf2c946c69180e1957aa49cc95a0e063ee70`.
The three installers use clean source `8da04d45b32ceff37158e04d9a8329f9aa58aacf`.
The later commit contains only the requested website alignment and documentation;
Git comparison confirms identical worker, API and build-script source. The
[worker-source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39976027194)
passed all eight jobs, including PostgreSQL, four real worker processes,
scheduler, inference and durable workflow recovery. Both native builds in the
[Mac packaging run](https://github.com/briancwelch/GodfatherAI/actions/runs/39976109230)
passed. The [final coordinator CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39977874516)
also passed all eight jobs against the website alignment commit.

All ten packaged release gates passed, including real disposable database and
artifact backup/restore, all installer downloads and restart persistence. Saved
image checks confirm the heartbeat-history and aligned-choice code in the actual
dashboard bundle. The frozen Windows executable contains the readiness module
and passed temporary install/reinstall, Tk/tray startup and isolated OS-store
checks. No contributor's installed worker was modified.

The coordinator archive is `godfather-0.9.0-rc.2-linux-amd64.tar.gz`, 402,522,762
bytes, SHA-256 `abf3c30d70ff078b616a9b888c749618dcf864f21d727c23086a7fb1ac213a8d`.
Migration head stays `0016_distributed_jobs`.

| Installer         | SHA-256                                                            |
| ----------------- | ------------------------------------------------------------------ |
| Windows x64       | `8e395adab6f2ba5575f6626086f7fd1524c3cfc17fdf0d62f464d97efe962649` |
| Mac Apple silicon | `0dce3cb36aa0546491a351488ccf599e411ffc4ebca31e94caf923951a72c129` |
| Mac Intel         | `fdbaf68397fb0594f4c293ad84977e10045df473ae171cc0dd679fecb0cad298` |

Verified deliverables are retained in `dist/`. Immutable build checkouts,
receipts, checksums and deployment helpers are under
`.cache/worker-recovery-release-0.9.0-rc.2/`. Packaged test evidence is
`.cache/release-tests/3e6f7f4806a9/result.json`. The received archive and internal
checksums passed on the VPS; the prepared release directory is
`/opt/the-godfather/releases/godfather-0.9.0-rc.2-linux-amd64`.

Production preflight found all five services healthy, four workers online and no
active jobs. Automatic approval review initially blocked activation pending
explicit deployment authorization; the owner then supplied it before the upgrade
ran. The existing no-active-job/paired-backup procedure activated the release.
All five services are healthy, only Caddy publishes host ports, and all four
workers reconnected online. The production environment remained byte-identical
with mode 600. Stable fingerprints matched all 15 existing record groups,
including credentials, ownership/policies, users, workspaces, jobs, artifacts,
account/provider keys and appearance settings.

Paired backup `/opt/the-godfather/state/backups/20261023T153340-1782292` passed its
checksums, PostgreSQL dump listing and artifact gzip integrity. No production
restore was performed. The previous release remains available for recovery.
VPS evidence is under
`/opt/the-godfather/state/deployments/worker-recovery-20261023-rc2`.

Public desktop/light and mobile/dark browser checks passed with Bootstrap loaded,
no page errors and no horizontal overflow. No Google sign-in was attempted.
Authenticated EKG history and execution-choice alignment were verified against
the fixture API and actual compiled bundle, rather than through a private
production account.

All **91 public HTTPS checks passed** using ordinary DNS and verified TLS. All
three installers were fully downloaded and SHA-256 checked through both public
hostnames (six hashes), and both runtime catalogs matched. The public manifest
matches the exact staged installer set. Authentication, foreign-origin and
private-route boundaries passed without creating users, nodes or jobs. No paid
provider call was made.

Refresh the website for the EKG and alignment fixes. Update Consigliere through
**File > Check for updates** or **Nodes > Downloads** for project recovery.
No contributor-host update, image download, paid inference or permission change
was forced. Windows remains unsigned and Mac builds are ad-hoc signed; physical
recipient installation and real inference remain owner acceptance.
