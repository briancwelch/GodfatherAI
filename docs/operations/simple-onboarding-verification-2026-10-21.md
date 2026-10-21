# Simple onboarding candidate verification — 2026-10-21

Candidate **0.3.0-rc.4** is built and locally verified. Deployment was not performed
in this milestone. The new public HTTPS worker routes and installer downloads are
not activated by committing this source.

Coordinator source: `4e87eb5d4a043ef5d712001a1c049a36db996e39`.
Windows and both Mac workers: `3226193310e2e68b264b006b8c94b752597b34f0`.
The later coordinator commit only improves installer download labels. All source
changes are committed and pushed to `main`; generated binaries remain outside Git.

## Resulting experience

Contributors download the worker from **Nodes → Connect a computer**, install it,
enter their Command Center address and click **Connect**. They approve the matching
code using their invited Google account. The app exchanges and saves its credential
automatically, starts the worker and reconnects on later launches. Closing the
window leaves it in the tray/menu bar; Pause, Resume, Open Command Center and Quit
are available there. Pairing can be cancelled and expires after five minutes.

The normal flow requires no command line, credential file, manual finish button,
hosts-file edit or Tailscale grant. Windows setup adds a per-user Start menu
shortcut. The Mac DMG includes an Applications link. Advanced settings retain
explicit resource contributions and sharing scopes. Existing models require local
consent; no models or runtimes are installed automatically.

The coordinator remains the existing Docker Compose system. On a prepared Linux
AMD64 Docker host, run `bash scripts/setup.sh` from the verified extracted release.
Its wizard collects the hostname and Google OAuth configuration, generates local
secrets and invokes the existing installer. This is not an advertised public curl
installer or a Docker Engine provisioning tool.

## Main files changed

| Area                | Files                                                                                                                                                                                                           | Behavior                                                                                                                        |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Desktop             | `packages/worker/src/godfather_worker/{desktop_app,desktop,pairing,launcher,native_desktop}.py`                                                                                                                 | Shared tray/window, automatic approval, saved origin-bound identity, reconnect, pause and clean shutdown                        |
| Native packaging    | `windows_setup.py`, `scripts/build_windows_worker.py`, `scripts/build_macos_worker.py`, `scripts/build_worker.py`, `.github/workflows/macos-worker.yml`                                                         | Per-user Windows setup; native Apple silicon/Intel DMGs; existing CLI arguments retained                                        |
| Command Center      | `connect-computer.tsx`, `worker-enrollment.tsx`, `administration.tsx`, `command-center.tsx`, `google-login.tsx`                                                                                                 | Installer discovery and three-step onboarding; manual credentials under Advanced; computer-neutral approval                     |
| HTTPS/configuration | API `config.py`, `authentication.py`, `nodes.py`; dashboard `control-server.ts`; release Caddy/Compose/env templates                                                                                            | Operator-configured HTTPS origin; narrow public worker routes; invalid-credential throttling; authenticated proxy peer metadata |
| Operator setup      | `infrastructure/release/scripts/setup.sh`, `scripts/release.py`, `scripts/stage_worker_downloads.py`                                                                                                            | Guided first installation; checksum-verified installer staging and release inclusion                                            |
| Validation          | `tests/test_simple_onboarding.py`, `tests/test_desktop_install.py`, `tests/integration/test_public_worker_https.py`, desktop/release tests; `scripts/check_{desktop_ui,windows_worker,worker_proxy,release}.py` | Origin, permission, storage, install recovery, native lifecycle, routing and durable release checks                             |
| Decisions/docs      | `AGENTS.md`, ADR 0016, README, onboarding/distribution and Mac guides                                                                                                                                           | Records optional Tailscale, simple setup and signing/acceptance boundaries                                                      |

## Checks actually executed

Counts overlap; these are separate runs, not additive totals.

| Check                                                                                        | Result                                                                                                                                                                                                            |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full PostgreSQL/API and Python suite in the isolated `godfather_test` database               | **436 passed, 3 skipped**; optional native Git/container coding acceptance skips                                                                                                                                  |
| Final native Windows non-integration suite                                                   | **245 passed, 2 skipped**; optional pinned coding-image tests skipped                                                                                                                                             |
| Targeted desktop, pairing, native packaging and release tests after startup-state correction | **49 passed**                                                                                                                                                                                                     |
| Ruff formatting/lint and strict mypy                                                         | Passed; mypy checked 124 source files                                                                                                                                                                             |
| Dashboard lint, strict TypeScript, component tests, formatting and production build          | Passed; **14 component tests**                                                                                                                                                                                    |
| Real Windows Tk/tray lifecycle with synthetic identity/controller                            | Passed fresh pairing, saved-identity startup without browser approval, tray hide/show, pause/resume and clean quit                                                                                                |
| Final frozen Windows setup `--self-test`                                                     | Passed temporary install, isolated shortcut, repeat install and bundled Tk/tray startup                                                                                                                           |
| Windows Credential Manager                                                                   | Passed write/read/delete using a separate synthetic service; no existing identity replaced                                                                                                                        |
| Native Mac ARM64 and Intel workflow                                                          | Both passed source checks, tray lifecycle, app/DMG build, ad-hoc signature, architecture/linkage, extracted-app startup and checksum checks                                                                       |
| Real Caddy routing with synthetic backend                                                    | Passed public worker forwarding, private-route blocking, download allowlist and forged metadata replacement                                                                                                       |
| Both legacy two-host and new one-host production Caddy configurations                        | Offline validation passed                                                                                                                                                                                         |
| Final saved coordinator images and Compose project                                           | Passed image provenance/content, shell syntax, fresh/repeat migration, private services, real HTTP proxy, anonymous-worker rejection on both hostnames, database/artifact restore, volume persistence and restart |

Native Mac evidence:
[successful final workflow](https://github.com/briancwelch/GodfatherAI/actions/runs/39635418190).
Its artifacts were downloaded and independently checked while staging. The earlier
worker-only import failure was fixed by deferring the coordinator migration import
until coordinator assembly and adding a regression check. No coordinator packages
were added to the worker build dependency set.

Local evidence is under `.cache/simple-onboarding/`; the isolated release report is
`.cache/release-tests/a531166c201b/result.json`. The latter records no Google call,
public TLS/DNS verification, Droplet load test or SSH installation.

## Reviewable artifacts

All paths are under `dist/`. The coordinator contains all three worker downloads
and their manifest. Each native build also has an external manifest/checksum.

| Artifact                                                                            | SHA-256                                                            |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `godfather-0.3.0-rc.4-linux-amd64.tar.gz`                                           | `95052bbbfb4745cd2ab149c046248584092462ac1558790e6636942cc215fd08` |
| `worker-downloads-0.3.0-rc.4/godfather-worker-0.3.0-rc.4-windows-x64-setup.exe`     | `9b1e7bbe525e6fb1f465712742f649a8d6c279aed6879a4bf8cd7ee36d93f0cf` |
| `worker-downloads-0.3.0-rc.4/godfather-worker-0.3.0-rc.4-macos-arm64-installer.dmg` | `1408698993baac280c7490b6c37d975cff25f55b55e333fd10f7c033b43b6efc` |
| `worker-downloads-0.3.0-rc.4/godfather-worker-0.3.0-rc.4-macos-x64-installer.dmg`   | `da8e8a37e165c72efb8844b10c1e93680f9f9340410702a2cb1632ac7a6cab61` |

## Security and remaining acceptance

Machine secrets stay in Windows Credential Manager or macOS Keychain and are bound
to the selected coordinator origin. Existing private Mac identities retain their
original API endpoint. Google Sign-In remains separate from paid provider API keys;
this milestone made no billable inference calls. Contribution restrictions, owner
permissions, durable jobs, leases and fencing retain their existing implementation.
Private databases, model servers and node administration are not exposed by Caddy.

Windows candidates are unsigned. Mac candidates are ad-hoc signed, with no
Developer ID or notarization credentials supplied. Ordinary distribution under
default Gatekeeper settings requires the publisher's Developer ID signature and
Apple notarization; contributors do not need Apple Developer accounts.
See [Apple's distribution guidance](https://developer.apple.com/developer-id/).
The existing builder accepts `--sign-identity` and `--notary-profile` when the
publisher supplies those credentials securely. Signing credentials belong in the
publisher's secure build environment, never in worker installers or source control.

Physical recipient installation, real Google pairing and remote inference still
need acceptance after coordinator activation. Linux retains the portable CLI/core;
a native Linux desktop installer is not part of this candidate. The first-install
wizard was syntax checked and packaged, not executed against a fresh real server
with DNS, TLS and Google credentials. It requires an existing Docker/Compose host,
hostname and Google web OAuth client. Existing installations retain the reviewed
upgrade/backup path instead of overwriting configuration.

The original local CLI worker was not stopped or reconfigured by these tests.
Owners switching to the desktop app should quit their old CLI worker first.

## Next authorized action

Approval is needed before activating this candidate on the existing coordinator.
AGENTS.md rule 3 requires explicit authorization for external changes; this upgrade
enables authenticated worker routes on the public HTTPS address and publishes the
candidate installers. Use the existing backup-based upgrade, preserve operator
configuration and data, add a fresh private proxy token, then verify anonymous
worker rejection, private-route isolation, download hashes, signed-in job history
and a real owner-approved worker connection. No DNS, Google Cloud or Tailscale
administration change is required by this candidate's design.

After activation and recipient acceptance, complete publisher signing before
claiming frictionless worldwide production installation. Do not advance into a
new workload phase as part of this usability milestone.
