# ADR 0010: macOS worker desktop and proof-of-possession pairing

Status: accepted for local implementation; native acceptance and deployment pending.

The authorized task adds a standalone Mac onboarding candidate using the existing
worker and Google authentication. A Tk/ttk interface uses standard-library code
and a bundled interpreter, avoiding another orchestration system or Electron.
The desktop calls the same CLI lifecycle through injected in-memory credentials,
stop event and status observer; existing command-line usage stays compatible.
The browser approval screen is a narrow addition, not a new dashboard section.

The device generates pairing and machine secrets independently. The browser sees
only a public SHA-256 challenge in its fragment and a matching comparison code.
Existing invited Google sessions create five-minute, single-use owner-bound grants.
Only the private worker route can exchange proof for registration authority.
PostgreSQL row locking consumes the grant and creates a digested machine credential
atomically. No bearer credential is returned through the browser, redirect URL,
installer, or polling response. Failed/ambiguous exchange is reconciled by owner
revocation rather than replay. Keychain is mandatory; there is no file fallback.

The browser page's purpose is owner consent. It displays signed-in owner, comparison
code, node name and explicit approval. States are checking, signed-out Google login,
permission denied, invalid link, approving, approved, cancelled and error. Existing
semantic labels/buttons, live status and trusted same-origin bridge are reused.
The native app provides hardware, connection, current job, conservative contribution
settings, explicit start/stop, diagnostics and local identity removal. All status
comes from discovery or real runtime events. Desktop scaling and accessibility
remain native acceptance checks. Tests cover authorization/expiry/replay/races,
protocol integration, secret-store failure, lifecycle and packaging boundaries.

Tradeoffs: an explicit Finish connecting button avoids background polling and
browser-to-app callback listeners; Tk requires a working build-host Tcl/Tk runtime;
macOS builds and signing cannot be validated on Windows. Existing transport still
requires private Tailscale connectivity and private API DNS. CPU/RAM controls are
scheduling budgets, not OS enforcement. Concurrency remains one. No unrestricted
tools, BYOK, model downloads, cloud fallback or network-policy
changes are introduced. Native DMG builds and Apple notarization are explicit
operator actions. The separately authorized manual GitHub Actions workflow uploads
unsigned development candidates as private run artifacts; it does not notarize,
publish releases, or deploy the enrollment extension.
