# Build macOS worker candidates from Windows

The **Build macOS worker candidates** GitHub Actions workflow is manual only.
It builds the prepared worker on native `macos-15` (Apple Silicon ARM64) and
`macos-15-intel` (Intel x64) runners. No Mac is needed on the developer's desk.
It reuses `scripts/build_macos_worker.py`, which reuses `scripts/build_worker.py`.
The standalone `.app` includes Python, Tk and worker dependencies. Recipients
do not need Python, Docker, Git or VS Code.

## Trigger from GitHub

1. Open <https://github.com/briancwelch/GodfatherAI/actions/workflows/macos-worker.yml>.
2. Click **Run workflow**. Leave **Use workflow from** set to `main`.
3. Leave **source_ref** set to `main`, or select an exact commit/tag containing
   the prepared Mac worker and its packaging/check scripts. Both the workflow
   and current application source are available on `main`.
4. Leave **version** blank for `0.1.0-dev.RUN_ID.RUN_ATTEMPT`, or enter a candidate
   version such as `0.1.0-rc.6`. Click the green **Run workflow** button.
5. Open the new run. Both architecture jobs must finish successfully. Under
   **Artifacts**, download the two archives ending in
   `unsigned-development-candidate`. Artifacts expire after 14 days; save copies
   privately if you need them longer. This does not create a GitHub Release.

Equivalent Windows command with an authenticated GitHub CLI:

```powershell
gh workflow run macos-worker.yml --repo briancwelch/GodfatherAI --ref main -f source_ref=main
gh run list --repo briancwelch/GodfatherAI --workflow macos-worker.yml
```

Each Actions artifact is a ZIP download containing a versioned
`godfather-worker-VERSION-macos-{arm64,x64}-installer.dmg`, `.dmg.sha256` and
`.dmg.manifest.json`. The DMG contains **The Godfather Worker.app**, the simple
[Mac installation README](../../packages/worker/macos/README.md),
[troubleshooting guide](../../packages/worker/macos/TROUBLESHOOTING.md),
administrator guide and manifest. The reused builder also makes a CLI ZIP, but
this workflow uploads only the desktop DMG and its metadata.

On the destination Mac, extract the Actions ZIP, then verify the DMG in Terminal
from its download folder before following the included installation README:

```sh
shasum -a 256 -c godfather-worker-VERSION-macos-arm64-installer.dmg.sha256
```

Replace VERSION with the actual version; Intel uses `macos-x64`.

## Build checks and boundaries

The workflow installs uv 0.13.1 and native Homebrew Python 3.14 with Tk support
on each ephemeral runner. `uv sync --locked --package godfather-worker --group dev` checks the
application lockfile and installs the worker plus development test tools, without
unrelated coordinator/API dependencies. The existing builder exports the worker closure
and installs build-only PyInstaller 6.22.3 in its isolated environment. Build hook
transitive dependencies and Homebrew patch versions are not fully locked; these
remain release-hardening work. No new application dependency is introduced.

Checks cover the actual runner/interpreter architecture, Tk initialization,
desktop lifecycle/security unit tests, CLI `--help`, frozen app `--self-test`, code
signature integrity, Mach-O architectures, DMG integrity and SHA-256. A second
smoke test mounts the finished DMG read-only, checks its guides/manifest, copies
the app into a temporary directory, unmounts the DMG and launches the copy with
Python/build environment variables removed and a system-only PATH. Native
libraries must use bundled or Apple system dependencies, and symlinks must stay
inside the app. Credential file names and private key containers are rejected;
public certifi CA certificates are permitted. Only the allowlisted DMG/checksum/
manifest paths are uploaded, after all checks succeed. The run summary records
the exact source commit.

The workflow uses read-only repository permission and no signing, production,
enrollment or provider secrets. Checkout credentials are not persisted. Native
startup loads Tk and Apple's Keychain framework without reading or writing
Keychain items, enrolling a node, contacting the coordinator, running models or
installing a login service. The existing v1 protocol and pairing behavior are
unchanged. Production deployment, migrations and DigitalOcean are separate.

## Unsigned development candidates and troubleshooting

These builds have PyInstaller/ad-hoc signatures for native execution. They are
**unsigned development candidates for distribution purposes**: no Apple Developer
ID identity, notarization, stapling or production Gatekeeper compatibility is
claimed. No Apple signing credentials are requested or used. Passing signature
integrity checks does not establish Gatekeeper trust. Request a signed, notarized
installer for ordinary distribution; do not disable system security settings.

Runner startup on macOS 15 does not prove clean-recipient installation, the
declared minimum macOS 13 target, UI accessibility, real Keychain prompts,
enrollment against production, inference, login startup or upgrades. The prepared
browser enrollment API/dashboard/migration also require separately authorized
deployment before real pairing can work.

For failures, open the failed job and step in Actions. Missing Tk stops before
the DMG is built; ensure Python and python-tk are the same 3.14 installation.
Architecture/linkage or isolated startup failures prevent artifact upload.
For an existing/partial output error, use a fresh version or rerun on a fresh
runner. If a runner is queued, check GitHub Actions availability and the private
repository's Actions allowance/billing; no extra build service is required.

## Verified initial build: 2026-10-20

[Run 39502464147](https://github.com/briancwelch/GodfatherAI/actions/runs/39502464147)
completed successfully on both requested native runners using worker source commit
`af866acceee7840c47e927b53df8e7af22c6047d`. Candidate version:
`0.1.0-dev.39502464147.1`. Both jobs passed their 22 desktop/package unit tests,
standalone build, CLI help, frozen Tk/Keychain-framework startup, DMG mount/copy/
unmount startup, architecture, bundled-library, signature-integrity and checksum
checks. Both artifacts were uploaded. Their downloaded DMGs were independently
hashed again on Windows and matched the packaged SHA-256 files:

| Target    | DMG SHA-256                                                        |
| --------- | ------------------------------------------------------------------ |
| ARM64     | `ed3d87f1fff386764edd7b2fa7333254653138ef3264ca774062070273c6aa11` |
| Intel x64 | `0fd6ea6f8e839f3ded676bd3e7a3cb07b2eba010a6278b02448e8c08b336c458` |

Local configuration checks passed with actionlint 1.7.12, Prettier, Ruff and strict
mypy. The broader focused Windows worker/desktop/package suite passed 49 tests.
The exact worker-only CI dependency command was also checked in a separate local
environment with 22 passing tests. The initial runs exposed an unnecessary
API-only cryptography build dependency on Intel and an omitted root test-tools
group; the final workflow fixes both without changing `uv.lock`.

These results establish native CI packaging/startup only. The recipient acceptance
and signing limitations above still apply. No production service, deployment,
enrollment migration, private account or release publication was changed.
