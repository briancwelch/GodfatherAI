# Shared Inference removal and action feedback

Published as **0.10.0-rc.5**, 2026-10-24, after separate owner authorization.
See the [release verification](shared-inference-feedback-release-2026-10-24.md).
The implementation checks below record source validation before packaging.

## Changes

- Worker list: right-click **Delete setup**, matching visible button, Delete key
  and keyboard context menu. The clicked row is selected before the menu opens;
  blank space cannot accidentally target a previously selected setup.
- Explicit confirmation distinguishes whole-setup deletion on the initiating
  computer from invitation removal on another participant. Both stop the group;
  model files, node identity, owner settings and job history are preserved.
- Approval, withdrawal, deletion, device detection, refresh and wizard requests
  show pending and result/error feedback beside the controls. Duplicate actions
  are disabled. Validation and cancellations also explain their outcome.
- Confirmed responses update the list immediately. A stale refresh cannot restore
  an older approval or deleted row. Network failure leaves the row and explains
  that central confirmation is missing even though local participation stopped.
- API: authenticated node-only removal, idempotent logical deletion, durable
  per-computer dismissal, capacity recovery and stale-advertisement rejection.
  Migration **0018_shared_engine_removal** is additive. Existing worker response
  payloads are unchanged; update the coordinator before distributing workers.
- Shared UI specification now requires immediate, nearby, truthful feedback for
  every user action, including validation, cancellation and failure.

## Validation

- Python non-integration suite: **458 passed, 4 skipped** (existing optional
  container/symlink cases).
- Focused PostgreSQL integration: **48 passed** across managed setup, existing
  shared inference and database suites. This includes active-job result fencing
  after either participant or initiator deletion, permission denial, idempotent
  removal, retained history/identity, capacity recovery and migration
  upgrade/downgrade/metadata agreement. Only disposable `godfather_test` was used.
- Native Windows Tk fixture: approval validation, pending/disabled controls,
  successful approval, withdrawal, context-menu deletion and confirmed row removal
  passed. Buttons, progress and nearby feedback stayed within the window at
  **1120 x 760** and **760 x 600**. No network calls or models were loaded.
- Existing native desktop smoke passed for both fresh and saved identities,
  including pairing, tray restore, resizing, Projects and Settings.
- Ruff lint/format and strict mypy checks passed.

Core tests use isolated fixtures and actual PostgreSQL; they do not prove a new
installed build, live accounts, multi-computer inference or physical GPU behavior.
Native macOS/Linux interaction still needs platform acceptance. Existing installed
workers receive these changes through **File > Check for updates**.
