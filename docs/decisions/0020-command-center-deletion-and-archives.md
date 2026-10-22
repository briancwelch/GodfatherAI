# Command Center deletion and workspace archives

Status: accepted for the owner-authorized Command Center maintenance update, 2026-10-21.

## Decision

Use nullable UTC `deleted_at` markers on workspaces, jobs and immutable agent
versions. Deleting an agent addresses its portable agent ID and removes every
version from future selection. Deleted records disappear from normal lists and
cannot be inspected, executed or retried through human job/agent routes. Durable
attempts, checkpoints, artifacts, scoped audit events and provider usage records
remain stored with their original foreign keys. This is logical deletion, not a
purge of retained data. No worker files are removed.

Only workspace owners delete workspaces. Job owners and workspace administrators
may delete authorized terminal jobs. Workspace administrators may delete agents.
Platform administration never bypasses workspace ownership or membership.
Batches contain 1-100 IDs and commit atomically; a missing, forbidden or unfinished
item rejects the batch without deleting any item. Retries with already deleted
IDs are idempotent while the actor retains the relevant access.

Unfinished jobs block workspace/agent deletion; individual jobs must be completed,
failed or cancelled. Workspace locks serialize creation, versioning and job
submission with deletion; job locks serialize scheduler claims, manual retries
and result actions. Existing scheduler fencing and portable worker protocols are
unchanged. Application migration `0013_command_center_deletion` is additive.
Downgrading this migration drops deletion markers and can make retained rows
visible again; normal recovery uses the documented paired backup procedure.

## Workspace archives

A dedicated asynchronous dialog recommends an owner-only ZIP export before
workspace deletion. Prepare and download never delete data; deletion has a
separate explicit confirmation. Users may explicitly choose to skip the archive.
Preparation uses indeterminate animation, downloading reports measured bytes and
percentage when Content-Length is available, and reduced-motion preferences are
respected. A browser download receipt is not proof the user saved the file.

The archive includes workspace policy and membership, all agent versions, jobs,
attempts, workflows, checkpoints, integrity-verified artifact JSON envelopes and
scoped events. A versioned manifest contains record counts and file SHA-256 values.
Logically deleted child records are included. API keys, Google identities/session
credentials, private provider connections/grants/billing and worker-local files
are excluded. Automatic import/restore is not part of this update.

Exports are restricted to owned, active workspaces with no unfinished jobs. They
are bounded to 100 selected workspaces, 10,000 records per entity per workspace,
and 128 MiB uncompressed content in one request. Metadata size is checked before
materializing database records. Missing/corrupt artifacts or exceeded bounds fail
without deleting anything. The authenticated same-origin bridge streams the ZIP;
no public archive URL, service or new dependency is introduced.

## Permissions and navigation

Exact selected-user membership lookup avoids deriving permissions from one
paginated member list. Workspace roles and platform roles remain distinct;
only platform administrators can read/edit other users' platform roles. Failed
or stale lookups never enable an editor for a different account. Saving platform
access retains explicit existing roles and uses normal session revocation and
last-administrator protection.

All existing paginated views have controls at both ends, sharing the same state.
Table selection is limited to eligible visible rows and is cleared by scope
changes. AJAX mutations await the backend and show explicit failure states.
