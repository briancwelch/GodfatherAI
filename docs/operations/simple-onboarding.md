# Install and connect

This usability milestone replaces manual worker credential files and mandatory
Tailscale setup. Release **0.3.0-rc.4** was activated on the existing coordinator
on 2026-10-21. Open [Command Center](https://app.the-godfather.ai), then
**Nodes → Connect a computer** for the Windows/Mac candidate installers.
See [live deployment verification](simple-onboarding-deployment-2026-10-21.md)
and the [build checks and artifact hashes](simple-onboarding-verification-2026-10-21.md).
Publisher signing and physical recipient pairing remain pending.

## Contributor

1. Your administrator invites your exact Google email. Open Command Center and
   choose **Continue with Google** with that account. No invitation code is needed.
2. Open **Nodes → Connect a computer**. Download the worker for your computer.
   Windows setup installs for your own account and adds a Start menu shortcut.
   On Mac, copy the app from its DMG into Applications and open it.
3. Enter the Command Center address in the worker and click **Connect**. Compare
   the code in the browser, give the computer a name and approve. The worker
   connects automatically; there is no credential file or finish button.

Enable **Allow my existing local AI models** to contribute installed Ollama models.
The app does not install Ollama or download models. With local AI off, the node
connects for availability only. Paid AI, repository access and other tools retain
their separate owner-controlled configuration and permissions.

Candidate `0.3.1-rc.3` adds graphical project setup and encrypted account API
connections; see [coding and account setup](coding-and-account-setup.md). Its new
features require both the updated coordinator and worker before use.

Later launches use the saved connection and reconnect. Close the window to leave
the app in the tray/menu bar. Use **Pause**, **Resume**, **Open Command Center** or
**Quit** there. Advanced settings contain scheduling capacity and explicit sharing
scopes. Capacity is advertised scheduling capacity, not an OS resource limiter.

The OS credential store holds the machine credential, bound to the coordinator
address. A saved connection cannot silently move its credential to another server.
To change servers, pause, disconnect locally and revoke the old credential in
Command Center, then connect again. Existing private Mac credentials retain their
original API address until explicitly replaced. Quit the old CLI worker before
switching to the desktop app; it is not terminated or revoked by the installer.

**Candidate signing:** Windows candidates are unsigned and may trigger SmartScreen.
Mac candidates are ad-hoc signed, without Developer ID or notarization. macOS can
block ordinary installation. Production distribution needs an Apple Developer
membership, a Developer ID Application certificate and notarization credentials.
No signing secret is required from contributors. Do not disable Gatekeeper to turn
an unsigned candidate into a claimed production release.

## Coordinator operator

The existing coordinator still runs as Docker Compose on Linux AMD64, with at
least two CPUs, 4 GB RAM and 15 GiB free. Docker Engine and Compose must already be
available. Prepare a hostname pointing to the host and a Google web OAuth client.
The setup wizard gives the exact redirect URI. These external accounts and DNS
changes cannot be created by the application without the operator's authorization.

After verifying the supplied release archive checksum and extracting it, run one
installation command from that release folder:

```bash
bash scripts/setup.sh
```

The wizard asks for the hostname, founder Google email, OAuth client ID and hidden
client secret, generates database and proxy secrets, creates a private environment
file and invokes the existing checked installer. It never overwrites an existing
configuration or database. Keep the extracted release directory in place; Compose
mounts its Caddy configuration and worker downloads. Upgrade and backup procedures
remain in [production-release.md](production-release.md).

This is a one-command **verified local release install**, not a published curl URL
or container-registry service. The existing coordinator now hosts the Windows/Mac
candidate downloads. A public coordinator bootstrap URL and signed release
publishing remain separate work.

One hostname serves the dashboard, downloads and authenticated worker routes.
PostgreSQL, Redis, model servers and node administration remain private. Tailscale
is optional. For an existing installation, set the proxy token before activation
so pairing limits distinguish real client IPs. Caddy overwrites client-IP metadata;
the API accepts it only with the configured proxy secret. A blank token uses the
more restrictive shared-proxy rate limit. Existing API hostname workers remain
compatible. Google login configuration is independent of OpenAI/Anthropic keys.

## Build and verify candidates

Use the existing project-local uv toolchain. Native builds never install services,
download models, enroll a node or modify production.

```text
uv run --locked --all-packages python -m scripts.build_windows_worker --version 0.3.0-rc.4
uv run --locked --all-packages python -m scripts.build_macos_worker --version 0.3.0-rc.4
uv run --locked --all-packages python -m scripts.check_desktop_ui
```

The Mac command runs on native ARM64/Intel runners through the existing manual
GitHub workflow. Windows setup `--self-test` installs into a temporary test folder,
creates an isolated shortcut, opens the bundled GUI startup smoke and verifies an
idempotent repeat; it does not install into the user's normal application folders.
The UI lifecycle smoke uses a synthetic identity/controller, not real Google or
inference. PostgreSQL enrollment tests exercise real persistence with Google HTTP
mocked. Physical Mac acceptance and real recipient pairing remain separate checks.

Stage verified installers for the coordinator's download panel:

```text
uv run --no-sync python -m scripts.stage_worker_downloads --output dist/worker-downloads INSTALLER...
uv run --no-sync python -m scripts.release --version 0.3.0-rc.4 --worker-downloads dist/worker-downloads
```

Staging checks installer hashes and version manifests; release assembly checks
the hashes again. Empty downloads show an unavailable message rather than a broken
download button. Linux retains the portable CLI/core; the shared tray source needs
a native Python/Tk build and desktop tray support. A Linux desktop installer is
not claimed by this candidate.
