# Shared inference and worker discovery release, 2026-10-24

The owner authorized building and deploying the pending worker and Command Center
changes on 2026-10-24, lifting the prior publishing/deployment hold. The selected
release is **0.10.0-rc.3** for the coordinator and all three native installers.
The coordinator is active and all three installers are published at
[Command Center](https://app.the-godfather.ai). All five services are healthy.

This release includes the [Shared Inference wizard](shared-inference-wizard-2026-10-23.md),
managed pinned llama.cpp setup with local owner device approval and mutual TLS,
explicit local-model scanning, configurable new-node registration permissions,
the reconnect notice and native update progress/secure-connection feedback.
Worker identities, local settings and existing history are preserved. Runtime
downloads and model execution continue to require the applicable owner opt-ins.

Migration **0017_shared_engine_setup** adds durable setup and per-node consent
tables. It does not replace existing nodes, credentials or job records. Legacy
shared inference declarations remain supported.

## Validation before packaging

The source milestone passed 448 non-integration Python tests with four optional
checks skipped, the full 295-test PostgreSQL suite and a final nine-test setup
rerun including two newly added owner drain/disable cases. Dashboard components
passed 44 tests. Python/frontend lint, formatting, types and the prior dashboard
build/browser smoke passed. Native Windows fixture geometry and a wizard flow
passed. Real pinned CPU RPC discovery through mutual TLS passed; physical
multi-GPU and separate-machine inference remain hardware acceptance items.

The release preparation refreshed the native lifecycle fixture to mock the new
explicit scan and setup-refresh boundaries. Fresh and saved-identity Tk/tray
flows passed. Packaged startup now also imports the shared-engine transport and
checks its bundled pinned runtime catalog without downloading or starting an
engine.

The initial unpublished candidates found a concurrent SSL read/write timeout
on Linux and an Intel Mac dependency-build gap. The TLS bridge now uses one
nonblocking I/O owner per connection with bounded buffers and partial-write
handling. Round-trip tests include fragmented bulk transfers. Intel packaging
builds the same current cryptography release with hash-pinned Maturin/CFFI/
setuptools/Pycparser and static OpenSSL; it does not downgrade cryptography.
Rc.1 and rc.2 were not deployed.

## Release acceptance

All deliverables use clean source revision
`583b7798cf836e09aff611793954697731610060`. All eight
[source CI jobs](https://github.com/briancwelch/GodfatherAI/actions/runs/40106657021)
passed across Windows, macOS, Linux, Python 3.12/3.14, frontend checks/build,
PostgreSQL, worker health, scheduling, inference and durable recovery. Both
[native Mac jobs](https://github.com/briancwelch/GodfatherAI/actions/runs/40106687586)
passed packaging, architecture/library inspection and startup tests. The frozen
Windows installer passed temporary install/reinstall, native Tk/tray startup,
isolated OS credential-store checks, and bundled wizard/runtime module inspection.

All ten packaged release gates passed, including image provenance, configuration,
repeat migrations, authenticated HTTP boundaries, all installer downloads,
disposable database/artifact restoration and restart persistence. An additional
network-disabled check verified the actual API image's release metadata,
migration head, owner-approval routes and default registration policy. The final
TLS relay also passed actual pinned native CPU RPC discovery without model weights.

Coordinator archive: `godfather-0.10.0-rc.3-linux-amd64.tar.gz`, **420,121,550 bytes**,
SHA-256 `dcf6f45d40d4ab6eefc4c579579a843480a561be9eba5d1c7bb261136bd694d3`.
The archive checksum was verified on the VPS before extraction and activation.

| Installer                                                                                                     | SHA-256                                                            |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| [Windows x64](https://app.the-godfather.ai/downloads/consigliere-0.10.0-rc.3-windows-x64-setup.exe)           | `852f781694515e8be9bc7b9e89b5d0e772df08f2f7a45a90e2a0368a8dd3e0fc` |
| [Mac Apple Silicon](https://app.the-godfather.ai/downloads/consigliere-0.10.0-rc.3-macos-arm64-installer.dmg) | `732ce270c0794dab1f3e5f30d7b0d4032ab36da11d8ba4943c47a13559e09ae5` |
| [Mac Intel](https://app.the-godfather.ai/downloads/consigliere-0.10.0-rc.3-macos-x64-installer.dmg)           | `31163da6a0f5a9ace9c575417526ee2c793084a2af51e7b21050fa4311e94409` |

Installers retain the existing unsigned distribution policy; Mac notarization and
Windows SmartScreen acceptance are not claimed. CI receipts, native reports,
checksummed artifacts and deployment/public-check evidence are under
`.cache/shared-engine-release-0.10.0-rc.3/`.

## Production preservation and public checks

The backup-first upgrade replaced coordinator 0.9.0-rc.4 with
`/opt/the-godfather/releases/godfather-0.10.0-rc.3-linux-amd64` and applied migration
`0017_shared_engine_setup`. All five services became healthy. Only Caddy publishes
host ports; API, dashboard, PostgreSQL and Redis remain private. There were no
active jobs at activation or postflight. Three existing computers were online and
two already-offline computers remained offline, matching preflight.

All **15 stable-record fingerprint groups** were preserved, including user/Google
identities, credentials, encrypted account keys, node ownership and contribution
policies, workspaces/memberships, agents, jobs, artifacts, checkpoints, provider
connections, application settings and distributed records. All 31 existing job
records and five node identities remained. The private production environment
file is byte-identical and retains mode 600. No credentials, roles or owner scopes
were changed by deployment.

Backup: `/opt/the-godfather/state/backups/20261024T153810-2392525`. Checksums,
PostgreSQL archive listing and artifact gzip integrity passed. Actual restoration
was tested only in the disposable package gate. Server preservation evidence is
under `/opt/the-godfather/state/deployments/shared-engine-20261024-rc3/`.

All **116 normal-TLS public checks** passed. The three installers downloaded from
both hostnames matched their published hashes. Anonymous shared-engine
create/approve/control/report requests are rejected on both public worker origins;
node-registration settings retain authentication/CSRF protection, and direct
public administrator APIs remain private. No real Google login, new account/node,
provider-key update, job or owner participation approval was created for acceptance.

Existing installed workers were not forcibly replaced. Owners can select
**File > Check for updates**, then use the new **Shared Inference** tab. Existing
saved settings/identities are preserved. Runtime downloads and participation still
require local consent. No contributor-host inference setup, model-weight download
or paid inference was performed. Physical multi-GPU/multi-host inference acceptance
remains separate from these verified release and native RPC checks.
