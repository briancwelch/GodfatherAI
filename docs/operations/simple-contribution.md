# Install, connect and contribute

On a new computer:

1. Install Consigliere and click **Connect**.
2. Sign in and approve the matching browser code.
3. Leave **Contribute this computer to my workspaces** enabled.

The computer automatically contributes to ordinary and distributed jobs in
workspaces its owner belongs to. Workspace membership handles sharing; there are
no user IDs, computer IDs or workspace IDs to enter. Invite contributors to a
workspace by name/email in Command Center. They do not maintain a second sharing
list on their computers.

Existing computers keep their previous settings after updating. Enable the same
switch on the main Connection screen once. Changes apply automatically after
current work; no manual Pause/Resume is needed. Turn it off to stop accepting other
members' work, or use Pause to stop working altogether.

Contribution uses existing installed local AI models and owner-enabled workloads.
If no model exists, the worker says **Connected - waiting for an AI model**. Choose
**Set up local AI** for the existing explicit runtime/model setup, or configure an
API connection under **Models & API connections**. Nothing is downloaded or billed
just by connecting or sharing. Files, coding projects and paid credentials retain
their separate permissions.

In Distributed Jobs, choose a workspace, contributing computers, tasks and agents.
Workspace administrators still choose allowed models/tools. If an agent uses a
model that is not enabled there, the error names that problem instead of asking
for unrelated sharing consent. Paid connections must be authorized for the exact
selected computer; contributing someone else's computer does not share their key.

The new worker requires the matching coordinator update. Older workers continue
their existing private or restricted contribution settings until their owners
upgrade and opt in. See [ADR 0024](../decisions/0024-workspace-contribution.md).
