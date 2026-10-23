# Bootstrap website appearance

The Command Center uses Bootstrap 5.3.8 styles with the Godfather navy/cyan palette.
Python/FastAPI and React/TSX remain in place. The package is bundled locally;
normal browser use does not request framework CSS or JavaScript from a CDN.

Open **Admin settings > Site appearance** (or `/administration/appearance`). Only
platform administrators may save shared defaults. Authenticated members may read
them. Saved changes reach other open sessions within 30 seconds. Each browser may
still choose light or dark. Reset preview loads defaults; Save applies them.

The configuration includes:

- Light/dark colors, header/highlight colors, font, font size, line height and corners.
- Content, navigation and inspector widths; default panels; sticky header and ribbon size.
- Solid/outline buttons; small/medium/large controls; panel padding and shadow.
- Table density, stripes, cell borders and row hover highlighting.
- Success, warning, danger and information colors. Semantic badge text automatically
  chooses black or white for contrast. Existing palette contrast checks still apply.
- Toast corner and width. Errors and active work remain visible until dismissed or
  resolved; successful completion keeps the existing expiry behavior.
- Progress-bar height, stripes and animation. Reduce motion overrides animation,
  including the operating system preference.

The live preview shows buttons, a table, measured progress and an example warning.
It contains labeled sample content, not live worker telemetry. It does not send
notifications or jobs. Invalid values cannot be saved. Older settings receive
new component defaults without overwriting their saved palette/layout values.

React drives the progress bars. Reported work and downloads show actual measured
percentages. Unknown progress uses an indeterminate bar and announces that progress
was not reported. A completed progress indicator alone is not proof of job success.

Worker setup lists each permitted computer separately with an explicit Online or
Unavailable badge and independent image-model / analytics badges. Installed models
on an unavailable computer do not make it available for submission. Long names
wrap, and the worker connection action has its own padded row.

The website source is checked as strict UTF-8 in `npm test`; known mojibake
sequences and replacement characters fail the regression. This checks application
source, not arbitrary uploaded documents or model output.

Developer checks:

```text
npm test
npm run lint
npm run typecheck
npm run format:check
npm run build
.venv/Scripts/python.exe -m pytest tests/test_appearance.py
.venv/Scripts/mypy.exe
```

Real PostgreSQL coverage is in
`tests/integration/test_command_center_appearance.py`, using only the explicitly
disposable `godfather_test` database. Browser acceptance uses mocked Google login
with the existing test-only `tests.e2e.auth_server`, never a real private account.
This source change does not deploy or rebuild workers.

## Verification on 2026-10-22

- Dashboard component suite: 41 passed, including source UTF-8, worker capability
  badges, honest measured/unknown progress and shared Bootstrap settings.
- Native Python suite: 345 passed, 4 optional host/container checks skipped and
  272 integration tests deselected. The skips require an explicitly selected
  preinstalled coding/data container or host symlink support.
- Focused real PostgreSQL suite: 4 passed, including appearance persistence after
  API restart, administrator/member permissions, origin enforcement and retained
  audit/identity behavior. Only the disposable godfather_test database was reset.
- ESLint, TypeScript, Prettier, Python formatting/Ruff and configured mypy passed.
  npm audit reported zero vulnerabilities. The Next.js production build passed
  without warnings.
- Headless Edge 155: all 15 main routes in light and dark, loaded mobile/tablet
  screens at 390/760 pixels, saved settings, warning-toast dismissal, worker
  panel collapse and reduced motion passed with no page errors or document
  horizontal overflow. Google login was mocked. Worker readiness used explicitly
  synthetic options; no inference or paid provider calls were made.

Browser screenshots remain locally in .cache/bootstrap-ui. The committed browser
probe is tests/e2e/bootstrap-ui.cjs. It expects the existing isolated OIDC test API
on loopback port 8009 and the built dashboard on 3010. The API fixture verifies test
mode and godfather_test before resetting data. On Docker Desktop, its test
container must join the local frontend network for the loopback publish to work.
Run the browser probe with node tests/e2e/bootstrap-ui.cjs after starting that
fixture. Those source checks did not deploy or package workers. The subsequent
[authorized coordinator deployment](bootstrap-deployment-2026-10-22.md) records
production activation and the preserved worker installers.
