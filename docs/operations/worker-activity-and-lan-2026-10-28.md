# Worker Jobs, notifications and shared inference addresses

Owner-authorized scope, 2026-10-28: correct Shared Inference address/approval
feedback, add node job history and notifications, then build new workers,
push and deploy after validation. Candidate: **0.12.0-rc.1**. Release evidence
will be recorded separately after packaging and production checks.

## Jobs and notifications

Consigliere's **Jobs** tab lists this computer's current and previous execution
attempts, 25 at a time. Active attempts appear first. Each row identifies the job,
type, workspace, attempt status/number, and start/finish times in local time.
The details distinguish this attempt's status from the overall job status when
work retries or moves to another computer. Shared inference participants see
jobs they contributed to, using the attempt's durable participant snapshot.

The **Notifications** tab keeps the latest 200 notices locally, with unread
counts and a notice bar visible from every tab. Select a notice and **Open
selected** to review the relevant job or Shared Inference setup. Opening a
notice never grants consent or starts execution. **Mark selected read** and
**Mark all read** preserve the history. Closing to the tray keeps polling active;
quitting stops polling. These are in-app notices, with no operating-system
notification permission or external notification service.

New shared invitations prompt the owner to choose a backend, detect/select
devices, choose an address and approve joining. Once all owners approve, the
initiator receives **Ready to start** and must select **Configure and Start**.
Other participants see that the initiator must start. Starting, ready, failed
and stopped states produce notices when they change; unchanged states do not
repeat. The Shared Inference tab also counts setups requiring local action.

Job assignment, start, completion, cancellation requests, confirmed cancellation
and attempt failures come from persisted coordinator events. A first connection
establishes a baseline without announcing old jobs as new. Later refreshes read
events in bounded pages, so a job may start and finish between polls without
losing either recorded transition. Notification read state and the event cursor
survive restart and are isolated by coordinator and worker credential. The
normal refresh interval is five seconds. Failed refreshes retain the last
confirmed job rows and display the connection error.

The read-only worker endpoint is `POST /api/v1/workers/activity/jobs`. The server
derives the node from its authenticated worker credential. History requires
current owner workspace access and excludes deleted workspaces/jobs. It returns
status metadata without prompts, results, artifacts, raw errors, credentials,
fencing tokens or host paths. Administrator sessions cannot use this endpoint
to impersonate a worker. There is no schema migration or new dependency.

## LAN address and approval feedback

The approval request already saves the address selected by the owner. The peer
binds its TLS listener to that saved address. The initiator connects to each
peer's saved endpoint; no startup path substitutes Tailscale for a saved LAN IP.
For Carbon as initiator and Radium as peer, the relevant connection is
**Carbon -> Radium's approved address/port**. Carbon does not expose a peer RPC
listener merely because its own address field contains port 50053.

The initial address list now puts LAN/private addresses ahead of Tailscale's
100.64.0.0/10 range. Saved addresses and ports appear beside participant status,
and selecting an existing setup restores this computer's saved endpoint.
Background refresh preserves unsaved edits. Approval confirmation includes the
selected endpoint. Changing the address/port requires clicking **Approve this
computer** again; Start explains and rejects an unsaved endpoint change.
Endpoint changes while running require stopping the setup first.

Approval feedback updates when the last owner approves, without replacing an
unrelated error. The old worker could show **Ready to start** and both owners
approved while retaining an earlier **Waiting for other owners** message.
Approval itself does not test the private route or prove an engine is running.

No firewall, routing, Tailscale configuration, computer identity, credentials,
existing consent files, model weights or installed runtime are changed by this
source update. New installers require explicit user installation as usual.
Physical Carbon/Radium inference and native hardware performance require live
acceptance after updating both workers.

## Local validation

- Python container suite against disposable `godfather_test`: **789 passed,
  32 skipped**. GUI adapters and optional external sandbox/recovery checks are
  the skips. The coordinator container intentionally has no usable Tk library.
- Windows non-integration suite: **490 passed, 5 skipped**; final shared-engine
  targeted suite after selection/account-isolation cases: **49 passed**.
- Native Windows smoke passed for fresh and saved identities, Jobs history,
  opening/read-marking notifications, invitation routing without automatic
  approval, compact/desktop geometry, tray lifecycle and clean shutdown.
- Ruff formatting/lint, strict mypy, documentation formatting, dashboard ESLint,
  strict TypeScript and **68 dashboard tests** passed.
- Existing group `aa1d2c19` was read in an explicitly read-only production
  transaction: both Carbon and Radium were stopped with approvals withdrawn and
  empty saved endpoints. This cannot prove what address was saved when the
  screenshot was taken. No approvals or network settings were changed.

No real model job, new model download or billable request was used for validation.
