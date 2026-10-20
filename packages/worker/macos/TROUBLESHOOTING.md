# macOS worker: technical troubleshooting and native builds

## Current readiness

This is an unsigned development candidate, not a production Mac distribution.
The manual [GitHub Actions workflow](../../../docs/operations/macos-worker-actions.md)
builds and smoke tests Apple Silicon/Intel packages on native macOS 15 runners.
Consult the actual run result before claiming either build passed. Keychain prompts,
GUI layout/accessibility, Gatekeeper, login startup, upgrades and physical inference
remain separate acceptance checks. No Apple signing identity is used by CI.
No production configuration or deployment was changed. New enrollment requires
separately approved API/dashboard deployment and migration `0008_worker_enrollment`.
Existing machine credentials and worker protocol v1 remain supported.

## Native builds (developer only)

On each actual target architecture, use macOS 13+ with native Python 3.14 including
working Tcl/Tk, uv 0.13.1, and Apple command-line tools. Use a GUI login session
for the Tk smoke check. The minimum OS marker is a target, not compatibility proof;
test on the oldest OS you intend to distribute to. Tk/ttk uses Python's bundled
desktop toolkit; no Electron, Node, Docker or Python installation is needed on the
recipient's Mac. There is no new application dependency or second worker runtime.

```sh
export GODFATHER_BUILD_PYTHON=/absolute/path/to/native/python3.14
uv sync --locked --all-packages
uv run --locked --all-packages python -m scripts.build_macos_worker --version 0.1.0-rc.6
```

Do not force another architecture or use Rosetta as proof of a native arm64 build.
The script rejects non-Mac/unsupported targets, builds the existing worker-only
dependency closure in an isolated environment, then freezes the app separately.
It fails if Tk is missing. PyInstaller 6.22.3 remains build-only; no full repository,
API, `.env`, tokens, provider keys, or models are copied into the app.
Build-hook dependencies follow the existing worker builder; fully locking those
transitives and reviewing bundled license notices remains release hardening work.

Outputs are `dist/godfather-worker-VERSION-macos-{arm64,x64}-installer.dmg`,
`.dmg.sha256` and `.dmg.manifest.json`; a worker CLI archive is also produced by
the reused build pipeline. The DMG contains the app, README and administrator/
troubleshooting guides. Preserve previous output; use a new version after a partial
failed build. The script never installs, uploads or publishes an artifact.

With an already provisioned Developer ID identity and notarytool Keychain profile:

```sh
uv run --locked --all-packages python -m scripts.build_macos_worker --version 0.1.0-rc.7 --sign-identity "Developer ID Application: YOUR IDENTITY" --notary-profile YOUR_PROFILE
```

**This explicit optional command contacts Apple and uploads the DMG for notarization.**
Run it only with authorization. No Apple password/key is passed on the command line.
Without credentials, output is ad-hoc signed for native execution, with no Developer
ID signing or notarization, and is labeled a development candidate. Verify the
external manifest for final notarization state; the manifest inside the DMG records
the earlier creation state. Notarization must return Accepted, and stapling and
ticket validation must pass. Clean-host Gatekeeper acceptance is still separate.

## Enrollment and recovery

The app keeps a random 256-bit pairing secret and a separate random machine secret
in memory. Only SHA-256 of the pairing secret enters the browser URL fragment.
The matching 12-hex-character code is a comparison aid, not the authentication
secret. Existing Google OIDC and invitation/session checks authorize approval.
A fixed return cookie carries only the public challenge through Google sign-in;
there is no arbitrary return URL and no Google token is sent to the worker.

Approval requires `nodes.contribute`, an enabled Google-linked account and trusted
origin. PostgreSQL stores only the challenge, session-derived owner, name, five-minute
expiry and consumed state. Exchange is on `/api/v1/workers/enrollment/exchange`,
under the existing Caddy private worker matcher, with rate limits using actual peer
identity rather than public forwarded headers. No grant exists before human
approval. Row locking gives one successful exchange; the machine secret is sent
once in its TLS body and only its digest is stored centrally. The response contains
identity metadata, never a credential. Both approval and exchange are audited.
Unused approval cancellation is available on the browser approval page; an already
issued credential must be revoked independently in Administration.

The app stores the machine identity in login Keychain service
`ai.the-godfather.worker`, account `machine-credential-v1`, through Security.framework.
It uses the macOS generic-password API directly through ctypes, without plaintext
fallback, subprocess arguments or credential logs. Those legacy Keychain APIs and
same-identity signed upgrades require physical validation on both Mac architectures.
On network loss after exchange or failed Keychain save, revoke the pending machine
credential before creating another approval. Never replay a grant to recover a
secret. Reconnect uses the persisted machine credential, never Google credentials.

## Connectivity

The app uses `https://app.the-godfather.ai` and the certificate-validated
`https://api.the-godfather.ai`. It disables proxies and redirects through the existing
worker transport. No inbound local listener, URL callback scheme, router port,
hosts-file edit, tailnet policy change or service installation is performed.
The **Set up Tailscale** button opens the official download page only.

The recorded first Windows deployment used a per-host mapping of the API name to
the coordinator's private Tailscale address. Public DNS alone therefore does not
establish Mac reachability. Before onboarding, an authorized administrator must
arrange private resolution and the minimum tailnet TCP 443 grant for each Mac,
without relaxing Caddy or exposing other ports. This work is deliberately not
automated by the installer. A future approved private DNS rollout could remove
this per-host prerequisite. TLS certificates must still match the API hostname.

## Runtime, limits and local state

`~/Library/Application Support/The Godfather Worker/` contains nonsecret contribution
settings, optional local Ollama configuration, and an instance lock. The folder is
private. `~/Library/LaunchAgents/ai.the-godfather.worker.plist` optionally opens the
app and starts processing with saved contribution settings at login, only after
the owner explicitly enables this option. The app runs as the logged-in user,
not root, and must remain open while contributing. Closing waits for current
outbound requests/cancellation to finish. A second app instance exits to protect
the shared machine identity. Stop does not revoke the credential; the existing
health/lease timeout makes the node offline. Restart waits behind active-session
fencing. Active jobs may be interrupted and use the existing retry/lease policy.

Only CPU presence and optional local Ollama text inference are exposed. Primary
capability defaults to CPU; owners can prefer inference and make CPU secondary
when inference is enabled. Custom capability labels,
arbitrary shell/tools/files, workflow execution and BYOK are intentionally absent.
Concurrency is fixed to one, as required by the existing inference executor.
Shared work is off by default and requires explicit owner AND workspace UUID lists;
backend access checks still apply. CPU/RAM settings cap registration/heartbeat
scheduling capacity; these are not OS limits or reliable inference memory caps.
GPU hardware is visible locally as reported/unverified but not advertised as a
scheduling budget. Existing Ollama may use its configured GPU and more CPU/RAM.
Do not enable inference if the owner needs a hard host-resource ceiling.

## Acceptance checklist (pending native execution)

On separate clean arm64 and x86_64 Macs with no developer tools: verify checksum,
install, Gatekeeper/Developer ID/ticket, UI scaling and keyboard use, Google invitation
and matching code, cancelled/expired/replayed approval, Keychain refusal, ambiguous
network loss, private DNS/Tailscale denial, CPU-only online heartbeat, optional existing
Ollama inference with a real job/result, loss/reconnect, immediate Stop/Start,
remote credential revocation, shared-owner/workspace denials, concurrent app launch,
login startup, signed upgrade retaining identity, and full per-user uninstall.
Record actual evidence separately from unit mocks or PostgreSQL contract tests.

References: [Apple Keychain items](https://developer.apple.com/documentation/security/keychain-items)
and [PyInstaller native packaging](https://www.pyinstaller.org/en/stable/usage.html).
