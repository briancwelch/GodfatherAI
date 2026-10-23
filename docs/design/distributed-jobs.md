# Distributed Jobs

Authorized 2026-10-22. The owner subsequently approved updated installers, VPS
deployment and GitHub synchronization after local validation.

Purpose: submit one goal to selected computers, run independent tasks concurrently,
then combine their durable outputs with a dependent model task. Navigation adds
Distributed Jobs beside Jobs and preserves workspace scope.

Hierarchy: expanded submission, job history (25 rows), selected job result, task
dependency graph, participant contribution bars and exact task table. Reuse the
application shell, appearance, Font Awesome commands and compact panel/table styles.
Submission selects a workspace, participants, per-task immutable agent versions and
eligible nodes, then a final synthesis agent. Existing agent definitions select models.
Dependent tasks require model-only agents; independent tasks reuse existing workflow
permissions and inputs. The normal UI starts with model-only tasks. No automatic
project apply or production tool write is introduced.

States: loading, empty workspace/agent/node catalog, waiting for dependencies,
waiting for a compatible selected worker, assigned, running, retrying, completed,
failed, cancelled, stale API snapshot, offline/unknown hardware telemetry and denied
control. A disconnected node does not imply lost durable checkpoints.

Accessibility: semantic labels, fieldsets, visible statuses, keyboard buttons and
native progress meters; graph has an equivalent task table. Narrow screens stack
panels and scroll wide tables. No color-only meaning or animated network decoration.

API: existing session bridge and workspace-scoped Command Center catalogs;
/api/v1/distributed/jobs list/create/detail/cancel; child workflow result/artifact
reads. Backend enforces selected participants, workspace access, owner policy,
per-attempt fencing and paid provider consent. Node selection grants no host access.

Acceptance: two selected workers receive different child assignments concurrently;
unselected nodes never claim them; final synthesis waits for durable predecessor
results; failure recovery retains checkpoints; cancellation fences every unfinished
child; private workspaces remain invisible; measured time shares sum approximately
to 100 percent while unavailable host telemetry stays unknown; mobile and keyboard
access remain usable. Host CPU/GPU utilization is explicitly system-wide, not a
per-job measurement. Time shares include failed/retried work and are not progress.

Submission feedback revision (2026-10-22): show readiness blockers and unavailable
computer/model warnings beside Run. Run remains actionable for incomplete setups
and validates all required fields into a focused, persistent error summary; native
validation must not silently intercept submission. API validation preserves field
locations without copying rejected input values. Pending, confirmed/queued, denied,
network failure and confirmation timeout are distinct states. Refreshing catalogs
must not erase a submission failure. A confirmation timeout never retries a POST;
the user checks history first. The first authorized workspace is usable even when
the overview does not supply a default workspace ID. No sharing/model permissions
change as part of these UI checks.
