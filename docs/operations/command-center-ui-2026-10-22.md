# Command Center UI update - 2026-10-22

Implementation is local source only. Do not deploy or publish installers until
explicitly authorized by the owner. Existing running local application services,
production services and normal application databases were not upgraded.

## Changes and locations

- Nodes: readable owner name, hover/focus tooltip with full user ID, worker version,
  and a small Out of Date badge when a newer installer exists for that platform.
- Overview ribbon: Jobs and Nodes use the shared Font Awesome icons.
- Administration > Appearance: persisted site-wide visual configuration with preview
  and explicit save. Direct URL: `/administration/appearance`.
- Administration > Computers: delete one credential or select visible-page credentials
  and Delete selected. Both active and revoked credentials can be removed. Confirmed
  deletion immediately revokes access and keeps durable node/execution/audit history.
- Administration > Audit and Activity timelines: readable actor names with ID tooltips.

Appearance controls cover 26 light/dark palette values and 15 typography/layout
settings. Platform administrators manage shared defaults. Other authenticated users
receive those defaults and can choose their browser's light/dark theme. Colors use
hex inputs; fonts are installed system choices. Inaccessible text/action color pairs
are rejected. A failed save/deletion never claims successful completion.

## Source map

- `apps/api/src/godfather_api/appearance.py`: schema, contrast checks, persistence,
  authenticated reads and administrator-only saves.
- `models.py`, migration `0014_command_center_appearance.py`: settings table and
  nullable credential deletion timestamp.
- `administration.py`, `enrollment.py`: owner-only credential deletion and reconnect
  protection; audit names. `nodes.py`, `command_center.py`: authorized identity projections.
- Dashboard `appearance-settings.tsx`, `appearance-provider.tsx`, `lib/appearance.ts`,
  `app/administration/appearance/page.tsx`, shell and CSS: shared configuration/editor.
- Dashboard `node-identity.tsx`, command center, administration, operational components:
  shared names/tooltips, semantic build comparison, icons and AJAX credential controls.
- Shared schemas, worker `build_info.py`/CLI and native build scripts: optional native
  worker version advertisement. No installers were built or published for this task.

## Acceptance and verification

The local unit/component checks, real disposable PostgreSQL integration tests and
isolated browser acceptance are recorded below. Browser API/worker data are synthetic;
they are not evidence of production behavior or physical Windows/macOS installation.
The PostgreSQL tests use the existing API test image with current source mounted
read-only and only reset the explicitly disposable `godfather_test` database.

Browser acceptance covers owner hover/focus tooltips, semantic update badge,
Overview icons, saved appearance/reload, responsive layout, audit actor tooltip,
individual and bulk credential deletion without page navigation, plus the existing
job/agent/workspace management regression scenarios. Evidence is ignored under
`.cache/command-center-management/`, including browser-result.json and screenshots.

Validation actually executed:

- Python Ruff lint/format and strict mypy: passed (162 checked source files).
- Python non-integration suite: 304 passed, 4 skipped. Skips require explicitly
  selected sandbox images or host symlink permission; no failure was hidden.
- Full real PostgreSQL integration suite: 230 passed. After the additional Audit
  request, the final affected Command Center/appearance suite passed all 11 tests.
- Dashboard component tests: 26 passed.
- ESLint, Prettier, TypeScript and optimized Next.js production build: passed.
- Isolated Edge/Playwright browser acceptance: passed all 16 scenarios with no
  browser runtime errors. Screenshots inspected for Nodes, Audit and desktop/mobile
  Appearance; tooltip clipping was corrected and a geometry assertion added.
- Git whitespace/diff checks: passed.

An initial authorization test incorrectly retained the legacy administrator role.
It was corrected to exercise a real human member session, and the final tests
verify forbidden saves and missing-origin rejection. No authorization bypass was
introduced. PowerShell's npm script restriction was handled with `npm.cmd` without
changing the execution policy.

## Later activation requirements

Apply additive migration 0014 together with the updated coordinator/dashboard after
separate deployment authorization. The test harness applied it only to its disposable
database. Existing workers remain supported and display Not reported until updated.
Publish newly built Windows/macOS installers to enable build-version reporting on
those computers; source workers intentionally report no release build. An unavailable
platform installer is labeled unavailable, not out of date. Native installation,
actual recipient upgrades and production acceptance remain deferred.

No new phase is started. Deployment remains on hold.
