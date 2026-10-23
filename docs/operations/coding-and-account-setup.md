# Coding projects and account API connections

Worker **0.3.1-rc.3** requires the account/project coordinator update. Build and activation status are
recorded separately in the [candidate verification report](coding-account-verification-2026-10-21.md).

## Reconnect the same computer

Routine updates keep the saved connection; open the worker and resume. If the
local credential was lost or you are switching from the old CLI to the tray app:

1. Quit the old worker and wait 30 seconds. Let unfinished work settle.
2. Click **Connect** in the worker. In its browser approval, enter the existing
   computer name, such as **Carbon**.
3. Check **Reconnect this computer** and approve the matching code.

Coordinator **0.3.1-rc.4** adds this option. The node ID, display name, history and
computer permissions remain in place; no second node is added. A fresh credential
replaces the previous one, which stays permanently revoked. The owned-credential
audit list retains that retired credential. This requires the owning Google
account; a platform administrator cannot replace someone else's computer. Active
workers, unfinished attempts and administrative disable/drain states block
replacement. Revoked credentials can be replaced through this fresh approval;
their old secret never becomes valid again. Local files/settings are untouched.

## Connect an API account

1. Open **Account settings** in Command Center.
2. Create a key at OpenAI or Anthropic using the link there, then paste it into
   that provider's key field.
3. Check the owned computers allowed to use it and click **Connect**.
4. On those workers, pause, enable **Use API connections from my account** and
   resume. Models appear after the next inventory refresh.

Open **Models → Add / use model → Local & API models** to select an account model
or an installed local model. If workspace access is required, its owner/admin can
choose **Allow in workspace / create agent**. This authorizes only that model and
opens the editor with it selected. API models are used through their connection;
they are not local downloads. Keep the selected worker online to execute jobs.
Consigliere **0.4.1-rc.4** enables model-only agents without coding-project setup.

The encrypted key is never shown again. Change computers and **Save connection**
without re-entering it; paste a new key only to replace it. **Disconnect** removes
the active encrypted copy and blocks new authorizations. Revoke at the provider
to invalidate it there too. Historical confidential backups follow retention policy;
already sent requests may still complete.

The provider manages billing and limits. No Godfather price/budget setup is
required. Google login stays separate. Select paid models explicitly and confirm
that the run sends your task to that provider; no local-to-paid fallback occurs.
Testing lists models without a billable prompt and does not prove every model's
inference permissions. The initial catalog supports compatible GPT/o-series and
Claude text models with conservative application context/output limits, omitting
unsupported audio/image/realtime IDs.
References: [OpenAI models](https://developers.openai.com/api/reference/resources/models/methods/list),
[Anthropic models](https://platform.claude.com/docs/en/api/models/list).

## Enable a coding project

1. **Pause** the worker and open **Coding projects**.
2. Choose the Git folder, workspace, existing Linux Docker test image, committed
   file patterns and test command. Click **Check and save project**.
3. Enable existing local models or an account API connection, then **Resume**.
4. Create an agent with **Isolated coding task** and an available model. Run it,
   select your advertised project and describe the task.

A small Python project might allow `src/*.py, tests/*.py` with
`python -m unittest discover -s tests` in a suitable image. Choose your actual
tools and paths. Coding requires existing Git, a committed repository and local
Docker. Its selected Linux image must contain `/bin/sh`, `cp`, test tools and
offline dependencies. Merely connecting a worker requires none of those tools.
Setup does not install them or execute commands on the host.

If an existing project's folder, Git, Docker engine or pinned image becomes
unavailable, see [project recovery](worker-project-recovery.md). The updated
worker retains that grant, shows the specific problem and withholds the project
from jobs while other enabled work can connect. Pause/Resume rechecks after repair.

Git trust is limited to the approved project directory for each worker Git
command. No global Git setting is changed. Network fetches, optional locks and
filesystem-monitor commands remain disabled.

Test commands become literal arguments in the existing isolated environment.
Choose a focused scope; snapshot limits and secret/path exclusions remain.
Uncommitted files are excluded. Originals stay unchanged; review patches/test
reports before applying anything. Remove/re-add a project to change scope, then
resume and refresh the run dialog. Only the connected owner gets project use.
For an empty project list, check worker version, saved project, matching workspace
and resumed registration. Model availability is required for execution.

## Operator activation

Use migration `0010_account_provider_keys` through the backup-based installer.
Add a separate random 32-byte `GODFATHER_PROVIDER_VAULT_KEY` as 64 lowercase hex
characters to the private environment, preserving existing values. First-install
setup generates it; an existing upgrade adds it explicitly. Empty/malformed
configuration fails closed. Never log, commit or replace a configured vault key.
Keep a confidential copy separately from the database and preserve it on restore.
Image-only rollback to schema `0009` is invalid after migration; use paired-backup
recovery if necessary.

Account routes require a human session and origin/CSRF checks. Worker key delivery
requires its individual credential/session, ownership, explicit computer grant and
local opt-in. Platform administration grants no other owner's key access. The
trusted API can decrypt account keys; this does not protect against compromise
of both operator configuration and database.

Windows installers remain unsigned; Macs remain ad-hoc signed without Developer
ID/notarization. Signing and physical recipient acceptance remain separate. Quit
an old worker before installing/starting its replacement.
