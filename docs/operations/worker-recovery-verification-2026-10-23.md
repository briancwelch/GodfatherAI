# Worker project recovery and heartbeat verification

The owner requested preventing Carbon's missing-project-image startup failure,
showing exact recovery instructions for other owners, and retaining the Nodes
EKG's previous heartbeats. This follow-up uses the existing worker/website update
authorization. Release publication is recorded below after package validation.

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
