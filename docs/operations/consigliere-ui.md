# Consigliere and Command Center usability

Owner-authorized update, 2026-10-21. The worker desktop app is now **Consigliere**,
carrying **The Godfather AI** branding. Worker protocol, authentication, node
ownership, local project consent and provider permissions are unchanged.

## Command Center

- **Jobs:** Submit a job opens by default. Job history uses authenticated,
  request-based pagination with 25 rows per page; search/status changes reset it.
- **Job details:** Job information opens by default. Technical details contains
  keyboard-accessible Logs, Attempts and Checkpoints tabs. Checkpoints load in
  separate authorized 25-item pages. The initial detail response is also bounded.
- **Nodes:** Connected nodes is the initial tab, with 25 records per page.
  Previously connected computers retain their offline/draining/disabled history.
  **Downloads** contains the Consigliere installers and connection instructions.
- **Activity / Audit:** 25 events per request; filters reset pagination.
- **Administration:** Settings, Workspaces, Permissions, Computers, Users,
  Invitations and Audit tabs, scoped to the current user's permissions. List tabs
  remember their own positions. Users, invitations, credentials, audit events and
  workspace members use 25-item pages. The permission editor has a searchable,
  paged account selector for platform administrators.
- Explorer and command ribbon use bundled Font Awesome Free icons; users,
  invitations, permissions, settings, workspaces and navigation are distinct.
  Dark mode uses neutral black/grey surfaces with the existing cyan accents.

Pagination changes data through the existing session-authenticated same-origin
bridge without navigating or reloading the document. Loading/error/empty states
remain visible. Backend authorization applies to every page and count. Legacy
administration array responses remain available; `paged=true` requests include
`items`, `total`, `offset` and `limit`. No migration is needed.

## Install and upgrade

Download from **Nodes → Downloads**. Quit the existing worker using **Quit** in
its tray menu before installing; closing its window leaves it running.

**Windows:** Run the Consigliere setup EXE. It replaces the single per-user
application under `%LOCALAPPDATA%\The Godfather\Desktop Worker\app`, creates one
Consigliere Start menu shortcut and removes recognized old version directories
and the former worker shortcut. Existing autostart consent is redirected to the
replacement executable. Settings, project permissions and OS credentials remain
in their existing locations. A running worker blocks replacement. Unrecognized
folders or links fail closed, and a failed directory swap restores the old app.
Reinstalling the identical version is safe; differing bytes under the same version
are refused. New versions replace the existing app rather than accumulating.

**macOS:** Mount the architecture-appropriate DMG, run **Install
Consigliere.command**, then select **Install / replace existing version**. This
opens a native installer window. It replaces Consigliere.app in the existing
Applications folder, including a recognized The Godfather Worker.app migration.
New per-user installs use `~/Applications`. Keep the same installation location
for upgrades. Read-only/system-owned Applications folders may require an owner
to resolve permissions; the installer does not elevate. The stable bundle ID,
Keychain service, settings folder and optional login-startup identity are retained.
Open Consigliere from Applications after installation and eject the DMG.

The existing unsigned Windows/ad-hoc signed Mac distribution status remains.
Publisher signing, notarization and physical recipient acceptance are separate
from native build/startup checks. CLI Python entry points remain compatible.

## Optional Tailscale

Consigliere checks for Tailscale on PATH and standard Windows, Mac and Linux
installation paths. A bounded, read-only `tailscale status --json --peers=false`
query distinguishes absent, installed/disconnected, connected and unavailable
status. The desktop refreshes this periodically and through **Refresh network**.
On macOS, `TAILSCALE_BE_CLI=1` selects the documented CLI mode; see the
[Tailscale CLI reference](https://tailscale.com/docs/reference/tailscale-cli?tab=macos).

Tailscale is optional. Existing private routes and DNS for the configured
Command Center address are preferred by normal system routing; authenticated HTTPS
remains the normal connection when no private route is configured. Connecting to
a tailnet alone does not prove that the coordinator is reachable on that tailnet.
Consigliere never guesses a peer as the coordinator, substitutes another hostname,
changes DNS/routes/ACLs, logs into Tailscale, or weakens TLS verification. No peer
inventory, tailnet name or raw CLI output is advertised to other users or logged.

No provider credentials or paid inference are needed for this update.
