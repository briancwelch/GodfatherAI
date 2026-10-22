# Command Center bulk management

This owner-authorized maintenance update changes the dashboard and coordinator
API only. Consigliere 0.4.0-rc.3 and its Windows/Mac installers remain unchanged;
no worker upgrade is needed. Phase 13 has not begun.

## Delete selected records

- **Jobs:** select eligible completed, failed or cancelled rows, then **Delete
  selected** and confirm. Cancel unfinished jobs and wait for confirmation first.
- **Agents:** select rows and choose **Delete selected**. Selection addresses an
  agent and all its versions. Unfinished jobs referencing any version block deletion.
- **Administration > Workspaces:** owners select workspaces and choose **Delete
  selected**. Workspace administrators can manage access but cannot delete another
  owner's workspace. Unfinished jobs block deletion.

Selection applies to the current page and scope. Requests are asynchronous and
atomic. One missing, forbidden or unfinished item rejects the entire batch with
an error. The UI does not claim deletion before backend confirmation. Items are
removed from active use; execution history, artifacts and usage are retained.
This does not erase worker-local files or purge historical records.

## Archive before workspace deletion

The workspace dialog lists the selected workspaces and offers **Archive &
download**. Preparation verifies durable artifacts; an animated indicator shows
this stage without inventing a percentage. The download bar reports actual bytes
and a percentage when its length is available. You may cancel export and keep
the workspaces. No jobs or agents show this extra archive prompt.

The ZIP has a folder per workspace UUID, JSON metadata, verified artifact JSON
payloads and `manifest.json` with counts and SHA-256 checksums. It includes
workspace settings, memberships, agent versions, jobs, attempts, workflow steps,
checkpoints and scoped events, including logically deleted child records. It
excludes account/API credentials, private billing/provider records, installed
models, worker-local repositories and unsaved files. Artifact payloads retain
their portable envelopes; this is an export, not an automatic restore package.

The browser receives the archive before **Delete workspaces** becomes available.
Verify it is saved in your Downloads folder. You may explicitly select **I choose
to delete without downloading an archive**. An export failure never triggers
workspace deletion. Exports are limited to 128 MiB uncompressed content and
10,000 records per entity per workspace; batches support up to 100 workspaces.
Nothing is deleted on a size, authorization, availability or integrity error.

## Edit existing access

Open **Administration > Permissions**, select a workspace, then select an account.
Search/page through accounts as needed. Current workspace access is loaded for
that exact user, including membership outside the visible member page. Save the
workspace role or add access for an account with none. Owner access is inherent.

Platform administrators also see the user's current platform roles, account
status and effective permissions. Checked roles are retained when adding another
role. **Save platform access and revoke sessions** uses existing session
revocation and protects the final enabled administrator. Workspace policy and
node-owner grants remain independent from platform roles.

Existing paginated lists have controls at the top and bottom, including jobs,
nodes, agents, models, activity, checkpoints, administration tables, members and
account selection. Controls inside forms never submit the form.

## Validation

Run `npm test`, `npm run lint`, `npm run typecheck` and `npm run build`; run Ruff,
mypy and the guarded disposable PostgreSQL suite. New backend coverage is in
`tests/integration/test_command_center_management.py`. After building the
dashboard, `node tests/e2e/command-center-management.cjs` runs isolated Edge
acceptance using `.tools/browser/node_modules/playwright`; it uses synthetic
fixtures on loopback and never signs into Google or touches production data.
See the deployment verification report for checks actually executed.
