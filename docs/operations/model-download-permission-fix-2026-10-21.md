# Consigliere model-download permission correction

Source-only correction, 2026-10-21. No release version, distributed installer,
installed worker or coordinator deployment was changed.

## Cause and behavior

Command Center already requires the owner-controlled `model.install.v1` runtime
and Ollama provider alias. The CLI advertises them only with
`--allow-model-installation`. Consigliere had no download-consent control and never
passed that flag, so enabling existing local models left every desktop worker
ineligible. Its empty-inventory startup check also blocked first-model setup.

Consigliere now exposes **Allow model downloads from Command Center** on the
Models & API connections tab and in Settings → Resources. It defaults to false,
persists separately from inference permission and forwards the existing CLI flag.
Local AI models must also be enabled. Empty installed inventories can connect.
Contribution changes require Pause and Resume. Command Center now gives those
steps and explains that an app without the checkbox needs an update.

The existing owner-only authorization, per-download confirmation, catalog,
leases/fencing, cancellation and verified post-download discovery remain in place.
No new dependency, schema migration, runtime installation or automatic download
was added. See [the setup steps](consigliere-ui.md#add-a-local-model).

## Verification executed

- Focused desktop/model-install/onboarding/coding-setup tests: **46 passed**.
- Python suite excluding integration: **301 passed, 4 skipped, 225 deselected**.
  Skips require a selected installed sandbox image or host symlink permission.
- Existing model-install integration tests: **3 passed** against the explicitly
  disposable local PostgreSQL `godfather_test` database using the cached test
  image and current mounted tests/packages. No live application database changes.
- Windows native Tk/tray smoke: passed for fresh and saved synthetic identities.
  Verified both settings locations stay synchronized, consent persists, invalid
  download-only settings are rejected, active contribution changes require Pause,
  empty inventory can Resume and download consent can be withdrawn after Pause.
  Visually inspected the Resources screenshot; all controls fit the default
  settings window. Screenshots are under `.cache/model-download-fix/`.
- Controller-to-real-CLI registration tests: Windows, macOS and Linux fixture
  advertisements, empty model discovery, downloads enabled/disabled. Registration
  contains installation/provider runtimes only with explicit permission. Discovery
  and coordinator transport are mocked; these are not physical Mac/Linux tests.
- Python Ruff formatting/lint and strict mypy: passed.
- Dashboard ESLint, TypeScript, **21 component tests**, and changed-file Prettier:
  passed. The PowerShell npm wrapper was blocked by execution policy; the normal
  `npm.cmd`/`npx.cmd` entry points completed without changing that policy.
- Patch whitespace check: passed.

The ordinary sandbox launcher failed before file access; checks used the approved
process fallback. No tests used real account credentials, downloaded models or
made paid provider calls. Packaging, physical Mac/Linux acceptance, live worker
downloads and deployment remain pending. A new worker build is required to expose
the checkbox in already installed apps; the dashboard copy also needs deployment.
