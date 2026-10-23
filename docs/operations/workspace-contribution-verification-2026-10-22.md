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
is **0.7.0-rc.1** for coordinator and workers; deployment results follow after
the existing authorized native-build, backup and release gates.
