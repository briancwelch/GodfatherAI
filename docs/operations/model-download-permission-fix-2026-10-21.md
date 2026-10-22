# Consigliere model-download permission fix and deployment

**Coordinator and Consigliere 0.4.1-rc.3 are deployed**, 2026-10-21 (Pacific).
The owner authorized rebuilding the apps/workers and deploying to the existing
VPS. Windows, Apple Silicon and Intel Mac installers are published under
**Nodes → Downloads**. Existing installed workers were not replaced or granted
download consent automatically; owners must install the update and opt in.

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
- Controller-to-real-CLI registration tests: Windows and both Mac architecture
  fixture advertisements, empty model discovery, downloads enabled/disabled. Registration
  contains installation/provider runtimes only with explicit permission. Discovery
  and coordinator transport are mocked; these are not physical Mac/Linux tests.
- Python Ruff formatting/lint and strict mypy: passed.
- Dashboard ESLint, TypeScript, **21 component tests**, and changed-file Prettier:
  passed. The PowerShell npm wrapper was blocked by execution policy; the normal
  `npm.cmd`/`npx.cmd` entry points completed without changing that policy.
- Patch whitespace check: passed.

The ordinary sandbox launcher failed before file access; checks used the approved
process fallback. These initial checks used no real account credentials,
downloaded no models and made no paid provider calls.

## Rebuilt artifacts and release validation

All artifacts use committed source
`2c8e5b3d563f2b4351877498c8545ad344336adc`, pushed to `main` before building.
The immutable coordinator archive is
`dist/godfather-0.4.1-rc.3-linux-amd64.tar.gz`, SHA-256
`6859d54d58e2d8461531b714ecd6ec70dc10718f571194b9ed7240998f35a799`.
API metadata records build start `2026-10-22T05:53:31.674790+00:00` (UTC).
Schema remains `0013_command_center_deletion`; no new migration was needed.

| Installer                                          | SHA-256                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `consigliere-0.4.1-rc.3-windows-x64-setup.exe`     | `7e6dd9c0d8cc1935f15d830717e4140d2dab9901e77b0c60cb0f77f3113223c9` |
| `consigliere-0.4.1-rc.3-macos-arm64-installer.dmg` | `a733033f8776c57b70158add907553643c8de68a0ed1e5a3736ec5429bc1ec63` |
| `consigliere-0.4.1-rc.3-macos-x64-installer.dmg`   | `cca83b618562c5a534496bdb6738b393329da8435d4e76b8c73c0e45cf91fbec` |

- Full disposable PostgreSQL suite: **527 passed, 3 skipped**. The skips require
  explicitly selected existing coding/data sandbox images.
- Local dashboard production build passed.
- Windows installer: temporary install/reinstall, packaged Tk/tray startup and an
  isolated synthetic Credential Manager check passed. No normal app replacement.
  Evidence: `.cache/model-download-fix/windows-check.json`.
- [Native Mac build run](https://github.com/briancwelch/GodfatherAI/actions/runs/39730133020):
  **both jobs passed**, including source unit tests, desktop lifecycle, standalone
  app/DMG creation, native architecture/framework checks and packaged startup.
  Downloaded installer manifests match the exact source revision and version;
  all checksum sidecars were checked before release staging.
- [Source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39730133909):
  **all eight jobs passed before activation**. Windows/macOS/Linux Python and
  dashboard checks, Python 3.12/3.14, real PostgreSQL tests, API/database restart,
  four-worker health, the 100-job durable scheduler, inference and interrupted
  checkpoint recovery all completed successfully.
- Saved coordinator images passed isolated release validation: exact image IDs,
  source metadata, architecture/content, Caddy/config/shell checks, fresh/repeated
  migrations, private services, anonymous denial, all installer downloads on both
  proxy hostnames, actual database/artifact restore, and restart persistence.
  Evidence: `.cache/release-tests/95890a80c15c/result.json`.

## Production verification

The existing VPS now points `/opt/the-godfather/state/current` to
`releases/godfather-0.4.1-rc.3-linux-amd64`. API, dashboard, Caddy, PostgreSQL and
Redis are healthy. API metadata matches the exact version/source/build above.
The PostgreSQL image identity is unchanged; PostgreSQL and Redis have no public
host-port mappings.

Pre/post fingerprints match for **2 users, 2 Google identities, 3 workspaces,
4 credentials, 2 node ownership/policy records, 8 jobs, 3 agents, 4 artifacts,
2 checkpoints, 2 provider connections and 1 encrypted account-provider key**.
Workspace memberships remain empty. Both existing nodes reconnected and report
online; no real job was submitted. Production environment bytes, including proxy
and vault keys, are identical and mode 600.

Paired pre-upgrade backup:
`/opt/the-godfather/state/backups/20261022T060206-909504`.
Checksums, PostgreSQL dump listing and artifact gzip integrity passed. Production
restore was not performed; actual restore passed in the isolated release test.
Evidence: `.cache/model-download-fix/upgrade.log` and `postflight.log`.

Normal DNS and verified public TLS checks passed: **41 HTTP checks**, including
HTTP 200 and matching installer SHA-256 values for all three downloads on both
`app.the-godfather.ai` and `api.the-godfather.ai` (**six verified binaries**).
The served download manifest matches the staged release. Anonymous private APIs,
worker credentials, account-provider access and foreign-origin mutations remain
denied. No account login, real job submission or model pull was used as a live
fixture. Evidence: `.cache/model-download-fix/public-result.json` and
`public-check.log`.

The existing unsigned Windows/ad-hoc signed Mac distribution status remains.
Physical recipient installation, signed-in owner acceptance and real model pulls
remain unclaimed. No model, paid inference, DNS, firewall or Google/account
configuration was changed. Phase 13 has not begun.
