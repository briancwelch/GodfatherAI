# Consigliere and Command Center usability

Owner-authorized update, 2026-10-21. The worker desktop app is now **Consigliere**,
carrying **The Godfather AI** branding. Worker protocol, authentication, node
ownership, local project consent and provider permissions are unchanged.

Unreleased source update, 2026-10-23: see [local model scanning, node registration
permissions and status feedback](worker-scan-and-node-permissions-2026-10-23.md).
Publishing and deployment are on hold; existing installers do not include it yet.
The same pending update now includes the [Shared Inference wizard](shared-inference-wizard-2026-10-23.md)
with owner-approved managed llama.cpp setup in its own tab.

## Native layout revision during Phase 12

The owner requested closer alignment with the Element desktop reference. The new
candidate uses the shared navy/cyan header, compact menu and grouped icon ribbon.
The command icons are rendered from the existing bundled Font Awesome vectors.
The main window expands normally; it no longer caps its size to 900 pixels or
recalculates a maximum height from its contents. There is no window-wide scrolling
canvas. Overflowing project rows and the Shared Inference approval form scroll
within their own panes; approval/start/withdraw controls remain visible.

**Projects** is a main tab, with a resizable approved-project list and an embedded
editor. Project details and Files & testing are compact subtabs. Existing owner,
workspace, file-scope, test-environment and reviewed-application permissions remain.
Project Save controls retain space when the window shrinks.

**Settings** is a single resizable window containing six tabs:

- General: sign-in startup, start minimized and close-to-tray behavior.
- Resources: CPU/RAM scheduling allowance, primary specialty, local models,
  explicit model-download permission and authorized account API connections.
- Workloads: explicit analytics/report permission, an already installed pinned
  Python environment, and optional local image-backend/model permission.
- Sharing: **Contribute this computer to my workspaces** uses current workspace
  membership automatically, without entering IDs. Fresh installations offer this
  before Connect; upgrades retain their previous permissions until the owner opts
  in. Changes apply automatically after current work. See
  [simple contribution](simple-contribution.md).
- Appearance: light/dark theme, text size, remembered dimensions and reset layout.
- Connection: account/coordinator/network status, refresh, Command Center and the
  existing confirmed local-disconnect action.

Appearance changes can be saved while working; contribution changes apply
automatically after current work finishes, without manual Pause/Resume.
Appearance preferences live in owner-local `appearance.json`, separately from
contribution settings and OS credentials. Startup changes occur only when the
owner explicitly saves them. This UI revision grants no new access by default.
Native checks cover resized windows, embedded project operations, six settings
tabs, theme persistence and tray restore with an isolated fixture identity.

## Add a local model

In Consigliere, choose **Pause**, then **Models & API connections**. Enable both
**Allow my existing local AI models** and **Allow model downloads from Command
Center**, then **Resume**. The same controls are available under **Settings →
Resources**; choose **Save settings** there before resuming. Ollama must already
be installed and running. An empty model inventory does not prevent connection.

After the worker connects, open **Models → Add / use model** in Command Center.
**Local & API models** lists installed local and connected OpenAI/Anthropic models.
Workspace access and worker availability are separate: use **Allow in workspace /
create agent** to authorize the selected model and open its agent editor, or
**Use model / create agent** when already allowed. API definitions and runs retain
their explicit provider consent. Selecting a model does not run inference.

Use **Download local model** only for a new Ollama model. Select your worker and
runtime; installed choices are labeled **Already installed** and offer **Use
installed model**. Confirm a new download and choose **Install selected model**.
Downloads use that computer's network and storage. Local-model use and model-download consent are separate; existing-model
permission alone does not enable downloads. Each download still needs the owner's
confirmation in Command Center. Neither setting installs Ollama.

For basic model-only agents, update Consigliere to **0.4.1-rc.4** from
**Nodes → Downloads**. The coordinator and all three updated installers are
deployed; see [verification](model-directory-verification-2026-10-21.md).
The model-selection dashboard is coordinator **0.4.1-rc.5**. Refresh the page
after deployment. Existing project/workload-enabled workers remain compatible.
Older settings keep downloads disabled until the owner explicitly enables them.

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
