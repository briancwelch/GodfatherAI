# Capacity and assessment fixes release, 2026-10-25

The owner authorized order #6, new workers, GitHub push and production deployment.
Command Center is **0.11.0-rc.2**; Windows x64, Apple Silicon and Intel Mac
installers are **0.11.0-rc.1** at [Command Center](https://app.the-godfather.ai).

## Delivered and deferred

Scheduling CPU/RAM remains within owner limits. Hardware measurements and unshared
GPUs are separate presentation data. Explicit evidenced runtime profiles populate
existing RAM/VRAM fields, with context/digest bounds and CPU-only offload controls.
Unprofiled requirements remain unknown; download/storage size is not inference RAM.
Existing reservations, consent, platform matching and recovery fencing remain.

The earlier approved reconnection, authentication polling, workflow usage/history
and complete recovery changes are included. Orders #5, #7, #8, Conditional and
Evidence gate remain [pending](pending-assessment-work-2026-10-25.md).

## Executed validation

| Check                                               | Result                                                                                                     |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Native Python unit suite                            | 479 passed; 5 platform/opt-in skips                                                                        |
| Complete disposable PostgreSQL integration suite    | 329 passed                                                                                                 |
| Dashboard component/fake-timer suite                | 67 passed                                                                                                  |
| Lint, formatting, strict typing and dashboard build | Passed; 204 typed Python sources                                                                           |
| npm audit                                           | Zero vulnerabilities                                                                                       |
| Browser fixtures                                    | Capacity, usage/history, polling/reauthentication; desktop/mobile passed                                   |
| Windows installer                                   | Temporary install/reinstall, packaged Tk/tray, isolated credential-store and frozen capacity checks passed |
| Both native Mac builds                              | Passed                                                                                                     |
| Saved coordinator package                           | Passed, including private artifact permissions and capability-free UID-10001 restoration                   |
| Public HTTPS/security/download checks               | 118 passed; all installer hashes verified on both hostnames                                                |
| Live anonymous browser                              | Sign-in rendered, no page errors, protected polling stopped after 401                                      |
| Production integrity                                | 36 artifacts, 18 checkpoints, 23 workflows and 1 encrypted provider key verified read-only                 |
| Production state                                    | Five healthy services; all 17 stable-record fingerprint groups preserved                                   |

[Feature CI](https://github.com/briancwelch/GodfatherAI/actions/runs/40219166608),
[coordinator CI](https://github.com/briancwelch/GodfatherAI/actions/runs/40222517253),
[native Mac builds](https://github.com/briancwelch/GodfatherAI/actions/runs/40219217168).
Worker source: ae3ba09030c77c5e18dab2b3b98ebee1484ccd60.
Coordinator source: a3a89f88ee173bfffa460f7644cf612392d8d2ac.
The coordinator-only follow-up corrects operator instructions and package tests;
application and worker behavior is unchanged from the feature commit.

## Packages and preservation

Coordinator archive: godfather-0.11.0-rc.2-linux-amd64.tar.gz,
**422,043,713 bytes**, SHA-256 **e49d5d1ee3b92bc4100b491bb9432890f0ef4dbbd94791e2721855171f9a166c**.

| Installer                                                                                                       | SHA-256                                                          |
| --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| [Windows x64](https://app.the-godfather.ai/downloads/consigliere-0.11.0-rc.1-windows-x64-setup.exe)             | 8e7b749c4d352c457b5a20ed64f1eeecdb341b781a6ca8c2fc35684fa6f2aca1 |
| [Mac (Apple silicon)](https://app.the-godfather.ai/downloads/consigliere-0.11.0-rc.1-macos-arm64-installer.dmg) | ae908bdc6d48fa10b4ba12c29c4b9211cc971a7e75cd3726284881c80cf93b3e |
| [Mac (Intel)](https://app.the-godfather.ai/downloads/consigliere-0.11.0-rc.1-macos-x64-installer.dmg)           | 2e1b393a1a5c8f2efc087535247c9478dc4105410fd75b9707b5a6d08f7bc2d6 |

Paired pre-upgrade backup: /opt/the-godfather/state/backups/20261025T185901-3090816. Checksums, dump listing and artifact archive
integrity passed. Migration head remains **0018_shared_engine_removal**. Environment
bytes/mode 600 stayed unchanged. Preserved records include all 5 node ownerships,
3 users, 4 workspaces, 32 jobs, 36 artifacts, 18 checkpoints, encrypted account
keys, contribution policies and shared-engine consents. Only Caddy publishes host
ports. Contributor installations were not forcibly replaced.

The first strict integrity probe used container root without DAC permissions and
could not read UID-10001 private files. Both backups contained all valid bytes.
The corrected one-shot verifier uses only DAC_READ_SEARCH; the normal API remains
UID 10001 with all capabilities dropped. Artifact restore runs as UID 10001 and
preserves private permissions. The package gate tests denied root reads, scoped
verification and non-root restoration. No artifact permission relaxation or data
repair was needed.

The additional data backup at /opt/the-godfather/state/backups/20261025T182258-3072495
has a separately encrypted configuration export under
/opt/the-godfather/recovery-configurations/ and an independent mode-600 key under
/opt/the-godfather/recovery-keys/, each in a private directory. Byte-identical
unsealing passed without displaying secrets; temporary plaintext was removed.
This recovery set matches release 0.11.0-rc.1; retain that trusted release before
forward upgrade. Off-host copying/key escrow has not been configured.

Local evidence: .cache/capacity-release-0.11.0-rc.1/ and
.cache/capacity-release-0.11.0-rc.2/. Server evidence:
/opt/the-godfather/state/deployments/assessment-20261025-capacity-rc2/.

## Remaining acceptance

Update Consigliere using **File > Check for updates** or **Nodes > Downloads**.
Older workers remain compatible; separate physical totals appear after their owner
updates. Owner budgets remain unchanged. Populate real profiles from defensible
measurements/documentation using the [capacity guide](capacity-and-admission.md).

Real Google sign-in, physical inference/GPU benchmarks and off-host disaster
rehearsal remain unverified. Windows is unsigned; Mac packages retain existing
ad-hoc signing. Release trust/notices are explicitly deferred in order #5.
This computer maps the API hostname to a private Tailscale address. API public
probes used the approved VPS address with normal hostname/certificate verification;
public DNS resolves to that VPS. No DNS or local hosts changes occurred.
