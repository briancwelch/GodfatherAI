# Command Center appearance and human identities

Status: accepted for the owner-authorized UI maintenance update, 2026-10-22.
Coordinator deployment was subsequently authorized on 2026-10-22; see the
[deployment report](../operations/command-center-ui-deployment-2026-10-22.md).
Native worker builds and installer publication remain explicitly deferred.

## Shared appearance

Store one validated appearance document in PostgreSQL `application_settings`.
Authenticated humans can read the shared defaults; `platform.manage` is required
for updates. The existing same-origin authenticated bridge allows only GET/POST
`appearance`; API authorization, origin checks and auditing remain mandatory.
There are no custom CSS, HTML, font URLs or new dependencies.

Administration > Appearance (also `/administration/appearance`) provides light and
dark palettes, system font choices, font size, line height, table density,
navigation/inspector widths, corner radius, content width, default open panels,
striped rows, sticky application bar, reduced motion and ribbon size. The editor
has a bounded preview, explicit save, reset-to-default preview, loading, failure
and permission states. Text/action pairs require 4.5:1 contrast. The light action
color is slightly darkened from the historical baseline to meet that requirement
on muted surfaces. Browser theme selection is session-local; shared defaults and
other appearance settings refresh in open sessions within 30 seconds. Operating
system reduced-motion preferences always take precedence over animation.

## Display identity and builds

Node owners and audit actors expose the existing user display name alongside
an ID tooltip available on hover and keyboard focus. Activity timelines use the
same component. Names are projected only for already authorized nodes/events;
this adds no account-directory or workspace access. Missing identities remain
explicitly unknown. Stored event/ownership UUIDs are unchanged; displayed names
are current profile names, not historical name snapshots.

Native worker builds embed their build version in `godfather_worker/build-info.json`.
Registration persists the optional version in the existing node runtime JSON.
Old workers still register without the optional field; their version is unknown.
Source execution never claims a released installer version. Worker protocol stays
v1; update the coordinator before connecting newly built workers.

The browser compares semantic versions (including numbered prereleases) against
published installers in its same-origin download manifest for that OS/architecture.
It never substitutes the coordinator release number or compares different targets.
Missing/invalid manifests or unknown worker versions do not produce a speculative
update badge. There is no automatic installation, download or worker restart.

## Credential deletion

Extend existing atomic bulk deletion with `node-credentials` (1-100 IDs). Every
selected credential must belong to the authenticated human, even for platform
administrators. Lock credential rows before nodes, matching registration/revocation.
Revoke, timestamp logical deletion and disable the node in one transaction; hide
deleted credentials from normal lists. Preserve credential, node, attempts,
checkpoints and audit history. Free the old display name for a fresh pairing.
Deleted connections cannot be resurrected by a pending reconnect approval.

Active attempts expire and recover under existing lease/fencing rules. No local
files or OS credentials are deleted. Both per-row and bulk actions use explicit
confirmation and AJAX, and only update after server confirmation. Migration
`0014_command_center_appearance` is additive; downgrade removes appearance and
deletion markers but does not un-revoke tokens or enable nodes.
