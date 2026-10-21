# Run agent → Preview changes → Apply to my project

Open a coding job from Jobs. Its result shows what the agent accomplished, actual
test-command outcomes and each changed file. Expand a file to inspect its diff.
The full patch remains downloadable. Test output, source hashes, execution logs,
attempts and checkpoints are available in the collapsed evidence/details panels.
No test count is inferred from a successful command or a model's narrative.

Running the agent still leaves the original project untouched. To apply from the
browser, install the worker version containing `result-actions-v1`, keep its saved
connection/settings, and enable application once for the local project:

1. Pause the tray worker and open **Coding projects**.
2. Select the existing project and use **Toggle applying reviewed changes for
   selected project**. Its label changes to **Apply enabled**. New projects have
   an explicit application checkbox, off by default.
3. Resume the worker. Refresh the coding result in Command Center.
4. Preview the changed files, acknowledge review and choose **Apply to my
   project → Confirm and apply**. Failed or absent tests remain clearly visible.

The request queues a separate application job on the original owned computer.
It may wait while that computer is offline. Approval is not success: the result
shows **Changes applied** only after the worker confirms application. Changes
remain unstaged; review and commit them through your normal project tools.

The worker refuses a moved base commit, edits in affected files, staged changes
in those files, unsafe links/paths and untracked or ignored filename collisions.
Unrelated edits remain intact. If blocked, inspect the reason, commit or move your
existing affected-file edits, rerun the agent when the base commit changed, and
review the new result. Repeated requests for an active/completed application
reuse the same durable job; only a confirmed safe pre-write refusal permits a
new request. Both job and computer ownership are required; platform administration
does not bypass these restrictions.

Pause editing affected files during application. The local lock coordinates
Godfather workers, not your editor. A crash, cancellation or lost reply after
authorization needs inspection. Automatic retry/failover is disabled for these
side effects. The worker stores the approved patch and receipt in the repository's
Git directory under `godfather-actions/JOB_ID.patch` and `JOB_ID.json`; a crashed
worker can also leave `godfather-apply.lock`. Inspect the project and receipt
before manually removing a stale lock. Nothing is force-applied or auto-committed.

Older workers continue existing jobs and previews. The Command Center explains
that application needs an updated worker and local project permission. Preview,
summary and report/image/table rendering improvements can subsequently ship as
Command Center-only changes. New local operations still need matching advertised
worker support; see [the action design](../decisions/0018-result-preview-and-actions.md).

For operators: the database schema stays at `0011_worker_reconnection`, but
`result.action` adds a new durable job payload. An older coordinator cannot read
that payload. Image rollback to rc.4 is only suitable before any result-action
jobs have been created; afterward use a compatible forward fix or a separately
reviewed, data-preserving recovery. Matching migration heads alone do not prove
behavioral rollback compatibility. Never delete action history to make a rollback
pass.
