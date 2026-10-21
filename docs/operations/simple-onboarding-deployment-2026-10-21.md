# Install-and-connect deployment — 2026-10-21

The user explicitly approved deploying **0.3.0-rc.4** and hosting its native
candidate downloads on the existing coordinator. The upgrade completed at
[Command Center](https://app.the-godfather.ai). The administrator then confirmed
the footer `0.3.0-rc.4 · 4e87eb5d`, existing job results and the Windows/Mac download
panel under **Nodes → Connect a computer**.

Contributors install the worker, enter `https://app.the-godfather.ai`, click
**Connect**, and approve the matching code using their invited Google account.
The app saves the machine credential in the OS credential store and starts and
reconnects automatically. No credential file or Tailscale configuration is needed
for the normal flow. See the [user guide](simple-onboarding.md).

## Release and deployment

| Item                          | Verified value                                                     |
| ----------------------------- | ------------------------------------------------------------------ |
| Previous coordinator          | `0.2.0-rc.5`, source `b6256accd4980313b8ba9c6ec97d07ba4e6c02f6`    |
| Active coordinator            | `0.3.0-rc.4`, source `4e87eb5d4a043ef5d712001a1c049a36db996e39`    |
| Native worker source          | `3226193310e2e68b264b006b8c94b752597b34f0`                         |
| Coordinator archive SHA-256   | `95052bbbfb4745cd2ab149c046248584092462ac1558790e6636942cc215fd08` |
| Active release directory      | `/opt/the-godfather/releases/godfather-0.3.0-rc.4-linux-amd64`     |
| Pre-upgrade paired backup     | `/opt/the-godfather/state/backups/20261021T185559-610524`          |
| Alembic head before and after | `0009_provider_connections`                                        |

The archive was checked locally and after transfer. All packaged checksums,
Compose configuration, image loading and Caddy configuration checks passed.
The existing installer quiesced application writers, backed up PostgreSQL and
artifacts together, applied the existing migration head and started all services.
API, dashboard, Caddy, PostgreSQL and Redis were healthy afterward. The PostgreSQL
image content was unchanged. The previous release remains available through
`state/previous`; recovery follows the existing
[backup/rollback runbook](production-release.md#backup-restore-and-rollback).

Every previous environment value was preserved. The only added setting was a new
private proxy token shared by Caddy and the API; the environment file remains
root-owned with mode `600`. The token authenticates proxy peer metadata used for
pairing rate limits. Google Sign-In remains independent of paid inference keys.

## Live checks actually executed

| Check                                    | Result                                                                                                                                                                                                                                      |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Five production services                 | Healthy after upgrade                                                                                                                                                                                                                       |
| Existing Windows CLI worker              | Reconnected; online with a fresh heartbeat                                                                                                                                                                                                  |
| Existing persistent records              | Fingerprints unchanged for 2 users, 2 Google identities, 2 workspaces, 2 worker credentials, 1 node ownership/policy, 3 jobs and their input/result/checkpoint references, 2 artifacts and 1 checkpoint; provider connections remained at 0 |
| Production backup                        | All SHA-256 checks passed; `pg_restore --list` and artifact gzip validation passed                                                                                                                                                          |
| Public HTTPS                             | Dashboard and downloads returned 200 using normal certificate verification, connecting directly to the coordinator's public IP through hostname resolution overrides                                                                        |
| Windows and both Mac downloads           | All three complete HTTPS downloads matched the trusted staged manifest and SHA-256 values below                                                                                                                                             |
| Anonymous valid worker registration      | 401 on both app and API hostnames, including with forged client proxy headers                                                                                                                                                               |
| Unapproved pairing exchange              | 404 on both hostnames; no machine credential or node created                                                                                                                                                                                |
| API hostname private routes              | Health, user administration and node listing returned 404                                                                                                                                                                                   |
| Dashboard private APIs without a session | Command Center, user administration and provider connections returned 401                                                                                                                                                                   |
| Foreign-origin pairing approval request  | 403                                                                                                                                                                                                                                         |
| Unlisted download path                   | `/downloads/production.env` returned 404                                                                                                                                                                                                    |
| Fresh-browser login UI                   | No code required; optional legacy-code disclosure works; Tailscale described as optional                                                                                                                                                    |
| Fresh-browser worker approval page       | Requires the invited account to sign in before approving a computer                                                                                                                                                                         |
| Real Google authorization redirect       | Correct production callback, PKCE S256 and only `openid email profile` scopes; no browser JavaScript errors                                                                                                                                 |
| Signed-in administrator acceptance       | User confirmed release footer, existing results and Windows/Mac downloads                                                                                                                                                                   |

Browser checks used a fresh headless Edge profile; they did not copy existing
browser sessions or complete Google sign-in on the user's behalf. Public HTTPS
checks used resolution overrides without changing hosts files or disabling TLS.
The database comparison used fingerprints rather than printing identity, secret
or result contents. Private command logs and reports are under
`.cache/simple-onboarding-deployment/`; the pre/post record snapshots and original
private environment backup remain in the server's protected deployment directory.
These files are outside version control.

## Published candidate downloads

| Download                                                                                                           | SHA-256                                                            |
| ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ |
| [Windows x64](https://app.the-godfather.ai/downloads/godfather-worker-0.3.0-rc.4-windows-x64-setup.exe)            | `9b1e7bbe525e6fb1f465712742f649a8d6c279aed6879a4bf8cd7ee36d93f0cf` |
| [Mac: Apple silicon](https://app.the-godfather.ai/downloads/godfather-worker-0.3.0-rc.4-macos-arm64-installer.dmg) | `1408698993baac280c7490b6c37d975cff25f55b55e333fd10f7c033b43b6efc` |
| [Mac: Intel](https://app.the-godfather.ai/downloads/godfather-worker-0.3.0-rc.4-macos-x64-installer.dmg)           | `da8e8a37e165c72efb8844b10c1e93680f9f9340410702a2cb1632ac7a6cab61` |

Before activation, [Repository checks](https://github.com/briancwelch/GodfatherAI/actions/runs/39637586690)
passed on documentation commit `22f49643140315b8f5261d67c3b57311764ddef5`,
including the OS matrices and Linux integration checks. The
[native Mac workflow](https://github.com/briancwelch/GodfatherAI/actions/runs/39635418190)
passed on both architectures. Earlier executed unit, integration, native installer
and isolated release checks are recorded in the
[candidate verification report](simple-onboarding-verification-2026-10-21.md).

## Remaining acceptance and limits

Physical installation and owner-approved pairing with the new desktop app,
especially on the recipient's Mac, still require acceptance. The existing CLI
worker's reconnection demonstrates backward compatibility, not that new-device
acceptance. Quit an old CLI worker before switching to the desktop app; this
deployment did not stop, replace or revoke it.

Windows installers are unsigned and can trigger SmartScreen. Mac apps are ad-hoc
signed, without Developer ID or notarization, so macOS can block ordinary
installation. The publisher still needs Apple Developer ID signing and notarization
credentials for normal distribution; contributors do not need developer accounts.
See [Apple's distribution guidance](https://developer.apple.com/developer-id/).
No default Gatekeeper or SmartScreen acceptance is claimed. Linux retains the
portable worker CLI; this release has no native Linux tray installer.

The guided coordinator install requires Docker/Compose, a hostname and a Google
OAuth client; no public one-line bootstrap download service was published. Its
fresh-server flow was not exercised against another real server in this deployment.

No DNS, Google Cloud, Tailscale policy, host firewall, provider credential, local
model installation or contributor-machine configuration changes were made. No
billable inference was invoked. Work stopped at this authorized usability release;
no later workload phase was started.
