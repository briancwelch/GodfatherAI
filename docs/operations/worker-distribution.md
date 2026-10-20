# Separate worker distribution and enrollment plan

**macOS update:** The [Mac candidate](../../packages/worker/macos/README.md) now has
local desktop, Keychain and owner-approved browser pairing source, an additive
enrollment migration and native `.app`/DMG build automation. Native builds,
Developer ID signing/notarization, physical acceptance and production deployment
remain pending. [ADR 0010](../decisions/0010-macos-worker-browser-pairing.md) supersedes
the manual-secret Mac enrollment proposal below. The rest of this document records
the earlier cross-platform distribution plan; Windows/Linux native installers and
secure-store adapters remain future work.

This document covers standalone packaging and the planned native installers and
one-time enrollment. Native installers and one-time enrollment are not implemented.
The coordinator bundle does not install a
worker, Python, Ollama, Git, a development environment or a source checkout on any
contributor host. Existing machine credentials remain supported unchanged while
the new enrollment protocol is reviewed and implemented in a separately authorized
change. Do not ship the current reusable credential as an enrollment token.

## Product and build boundaries

Run `uv run --locked --all-packages python -m scripts.build_worker --version 0.1.0-rc.2`
on each target build host. The script creates a separate ignored build environment,
exports the locked worker-only dependency set and adds build-only PyInstaller 6.22.3.
It never changes the application lockfile or installs a service. Native `--help`
must succeed before packaging. Output is `dist/godfather-worker-VERSION-OS-ARCH.zip`
and `.zip.sha256`, with the complete standalone directory, manifest, checksums and
this guide. Windows x64 can be built/tested locally; macOS requires native runners.
For Linux AMD64, Docker Desktop's Linux VM can build the standalone artifacts:

```powershell
docker buildx build --platform linux/amd64 --file infrastructure/docker/worker-build.Dockerfile --build-arg RELEASE_VERSION=0.1.0-rc.2 --output type=local,dest=dist .
```

The Linux build uses Debian Bookworm's glibc baseline and build-only `binutils` for
PyInstaller binary inspection; neither is installed on the host. Run this on a clean
output/version to avoid replacing older exported artifacts. These are unsigned
candidates, not finished native installers. Build-time PyInstaller hook dependencies
are resolved in the isolated environment; fully locking these and signing remain
release-hardening prerequisites.

Build **godfather-worker** separately from the coordinator, with only contracts,
model-gateway, agent-runtime and worker dependencies. Freeze a standalone directory
with a private embedded Python runtime using a pinned PyInstaller version. Build
on each target OS/architecture: Windows x64; macOS arm64 and x64 where feasible;
Linux x64 and arm64 as required by actual owners. PyInstaller is not a cross-compiler.
Linux builds must target the oldest supported glibc baseline (initially Ubuntu
24.04); Docker Desktop Linux tests do not certify physical Linux/GPU behavior.
Build tools belong only on build hosts, never contributor machines.

Publish distinct versioned worker archives plus checksums, dependency/license
inventory, supported protocol versions and signed release metadata. Include only
the worker binary/runtime, native launcher/config template, uninstall instructions
and licenses. Never bundle `.env`, enrollment credentials, provider keys, models,
Git metadata, API/database components or repository sources. Sign Windows binaries
and installer with Authenticode, sign/notarize macOS artifacts, and sign Linux
packages/repository metadata. Signing identities and distribution hosting are
operator decisions; no public download service is provisioned here.

Native installation: Windows per-user installer and background launcher (Task
Scheduler or a separately consented service); macOS signed `.pkg`/app with per-user
LaunchAgent; Linux `.deb` or archive with per-user systemd unit. Default to the
contributor's account with no administrator/root privilege. Machine-wide service
installation requires explicit consent and restricted service identity. Install
under product-specific version directories with separate private config/state/logs;
atomic executable update and previous-version rollback. Upgrades preserve owner
policy and credentials. Uninstall stops/revokes the worker and removes only product
files; preserve owner workspaces/models by default. Host-level restrictions remain
authoritative even for platform administrators.

Acceptance per build: clean host with no Python/Node/Git; install/help/start/stop;
outbound HTTPS and actual hardware discovery; enrollment expiry/replay and owner
isolation; revocation; protocol compatibility; portable workflow checkpoint recovery;
upgrade/rollback/uninstall without touching unrelated files; platform signing checks.
No provider is enabled until the owner explicitly configures it. Never auto-install
Ollama, download models, enable paid fallback, discover private files or expose
credentials/host mounts. Core registration/discovery alone should work CPU-only.

## Enrollment protocol to implement

1. A Google-authenticated contributor with `nodes.contribute` requests an owned
   enrollment grant through the same-origin dashboard bridge. Owner ID comes only
   from the session; an administrator cannot name another owner. The owner selects
   node name, contribution limits, exact allowed workspaces/users/tools and expiry.
2. Generate 256 bits of cryptographic randomness. Return the registration secret
   once, with a maximum ten-minute lifetime (default five minutes). Persist only
   its digest, owner, reserved node identity, explicit policy, expiry, created/used/
   revoked timestamps and audit metadata in PostgreSQL. No secret in URLs, logs,
   process arguments, screenshots, download packages or durable events.
3. Installer accepts the secret through a masked interactive prompt or protected
   standard input. Verify the exact approved HTTPS coordinator and certificate;
   never disable TLS verification or accept arbitrary redirects. Store nothing
   until enrollment succeeds. Tailscale connectivity/grants remain a prerequisite.
4. Worker locally generates its long-lived random machine credential; POST the
   registration secret and machine secret in a bounded TLS body to a new enrollment
   endpoint. Under one PostgreSQL transaction, row-lock the grant, validate expiry,
   owner enabled/linked/allowed, revocation and unused state, consume it, bind the
   digest of the machine secret to the reserved owner/node, and audit success.
   Exactly one concurrent exchange succeeds. Scheduler never receives secret values.
5. Return only the existing versioned identity/registration contract and allowed
   policy. Keep the existing outbound heartbeat, session, lease and fencing checks.
   Enrollment is separate from reconnect: reconnect uses the machine credential,
   never the consumed enrollment grant or interactive Google login.
6. Fail closed on ambiguous network loss after consumption: the owner revokes the
   reserved credential and creates a new grant. Do not allow token replay to fetch
   a credential. Atomic local credential-file write must precede normal operation;
   cleanup must not leak temporary secrets.
7. Store worker credential in Windows Credential Manager/DPAPI, macOS Keychain or
   Linux Secret Service when available, with an explicit mode-600 file fallback
   only where the owner accepts that storage policy. Existing credential-file CLI
   needs an adapter for native stores. Provider secrets remain separate and local.
8. Revoke unused grants and enrolled machine credentials independently through
   owner-authorized audited operations. Disabled users/nodes cannot enroll/reconnect.
   Rate-limit grant issuance and exchange without trusting public forwarded headers.

Required tests: expiry boundaries/fake clock; concurrent single use; replay;
disabled/revoked/unlinked owner; cross-owner admin denial; rollback of failed DB
transaction; malformed/oversized inputs; generic errors and secret redaction;
network-loss reconciliation; secure-store failure; reconnect/revocation; unchanged
lease fencing, node policy, workspace isolation and model requirements. Additive
migration and backward-compatible protocol versioning are required. This plan
introduces no automatic billing/BYOK, unrestricted shell or host filesystem grants.

Reference: [PyInstaller platform build requirements](https://pyinstaller.org/en/stable/operating-mode.html).
