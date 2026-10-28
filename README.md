# The Godfather

The Godfather lets you run AI jobs from a browser using your own computers and
models. The **Command Center** is where you manage workspaces, agents and jobs.
**Consigliere** is the worker app you install on each computer that will do the work.

The Command Center is published as **0.11.0-rc.2**; Windows/Apple Silicon/Intel Mac
worker installers are **0.11.0-rc.1**. See the
[release verification](docs/operations/assessment-capacity-release-2026-10-25.md)
for capacity/admission safeguards, native checks, backups and preserved data.

Consigliere now includes **Scan for Local Models** and a **Shared Inference** tab
with guided llama.cpp setup and each computer owner's device approval. Platform
administrators can choose which roles may add new computers. Update workers using
**File > Check for updates**; existing connections, settings and history remain.
Shared Inference now supports right-click **Delete setup** and shows explicit
progress and results for approval, withdrawal and other setup actions.

The next **0.12.0-rc.2** worker adds **Jobs** history, actionable **Notifications**,
saved network-address visibility and clearer Shared Inference approval/start
feedback. See [worker activity and LAN setup](docs/operations/worker-activity-and-lan-2026-10-28.md).

## Sign in

Open [Command Center](https://app.the-godfather.ai) and choose **Continue with Google**.
Use the exact Google email your administrator invited. No invitation code is needed
for normal sign-in. If you cannot sign in, ask your administrator to check your
invitation and its expiry. See [account invitations](docs/operations/user-onboarding.md).

If your group already has a Command Center, you only need its address and a worker
installer. Docker belongs on the coordinator or on a worker that needs an isolated
coding/data environment; it is not required just to open the website or pair Consigliere.

## Install a worker

Invited members, contributors and administrators can connect their own computers.
Member access is sufficient; each owner controls their computer's permissions.

1. In Command Center, open **Nodes > Downloads** (or **Connect a computer**).
2. Download the installer for **Windows x64**, **Mac Apple silicon**, or **Mac Intel**.
3. Install Consigliere. On Windows, run the setup EXE. On Mac, open the DMG and
   copy the app into Applications. These candidate installers are currently unsigned
   on Windows and ad-hoc signed on Mac; obtain them from your trusted Command Center.
4. Open Consigliere, enter your Command Center address if needed, and choose **Connect**.
5. Sign in in the browser and approve the matching pairing code. Return to
   Consigliere and check its connection status.
6. Choose whether to enable **Contribute this computer to my workspaces**. This
   allows workspace members' permitted jobs to use your enabled capabilities.
   Existing computers keep their previous settings until their owners change them.

Workers connect outward over HTTPS. Tailscale is optional. Connecting a computer
preserves its owner's control over files, projects, models and paid API access.
Use **Pause** to stop accepting work. Closing the worker window normally leaves
it running in the tray; use **Quit** to stop the app.

For updates, use **File > Check for updates**. If your old worker has no updater,
quit it from the tray and run the new installer. Keep your existing computer
identity when reconnecting. See [worker installation and settings](docs/operations/consigliere-ui.md)
and [workspace contribution](docs/operations/simple-contribution.md).
For a missing project dependency or the older **Worker could not continue**
message, see [project recovery](docs/operations/worker-project-recovery.md).
Linux workers currently use the [portable/source instructions](docs/operations/worker-distribution.md);
the current desktop installer catalog covers Windows and both Mac architectures.

## Set up a model

A connected computer needs a permitted model before it can answer AI jobs.

- **Local AI:** in Consigliere, open **Models & API connections** or **Settings >
  Resources**. Allow existing local models. If you need a model, separately allow
  downloads and, if needed, Ollama runtime setup. Then in Command Center choose
  **Models > Add / use model > Download local model**, select your computer and
  confirm the download. Use **Use installed model in this workspace** when ready.
- **API models:** open your personal **AI connections**, add your provider key, and
  select the owned computers allowed to use it. Enable account API access locally
  on those computers. Google sign-in does not supply an AI provider key. Provider
  billing applies when you explicitly select a paid model and confirm data sharing.

Use **Allow in workspace / create agent** or **Use model / create agent** to make
an available model usable by an agent. Installing a model and granting workspace
access are separate steps. See [model and worker setup](docs/operations/worker-readiness-and-workspaces-2026-10-22.md)
and [API connections and coding setup](docs/operations/coding-and-account-setup.md).

## Run your first job

1. Open **Workspaces**, create or select a workspace, and add the people who should
   have access. Each person controls which of their computers contributes.
2. Under **Models**, choose a permitted model and create an agent. Under **Agents**,
   review its instructions and enabled tools.
3. Open **Jobs**, choose that workspace and agent, enter your request, and submit.
4. Open the job to follow its status and read its result. Job details contain
   output, available downloads and any reported test results. Logs, attempts and
   checkpoints are available in the technical details.

A queued job usually needs a compatible, online computer with the selected model
and permissions. Check **Nodes** and the worker's model status before retrying.
A job marked for review needs inspection before it is run again.

For coding, approve the local Git project and its file/test scope in Consigliere's
**Projects** tab first. Review the generated changes and actual test results, then
choose **Apply to my project** only when you want them applied. Applying also
requires the project's separate local permission. See [coding setup](docs/operations/coding-and-account-setup.md)
and [preview and apply](docs/operations/results-and-apply.md).

Use **Images** or **Analytics and Reports** for those workloads after enabling the
matching image connection or isolated data environment. Images supports local
AUTOMATIC1111 and explicitly selected OpenAI/Gemini account connections; see
[cloud image setup](docs/operations/cloud-images.md) for the required worker opt-ins.
Use **Distributed Tasks** for dependent tasks across computers. **Distributed Jobs**
runs one model request across GPUs or computers. Start in Consigliere's
**Shared Inference > Set up Shared Inference** to choose an installed compatible
model and participants, obtain owner approvals, and configure the engine. See
[the setup guide](docs/operations/shared-inference-wizard-2026-10-23.md) and
[task variables](docs/operations/shared-inference-and-tasks-2026-10-22.md).

## Host your own Command Center with Docker

The packaged coordinator runs on a **Linux AMD64** Docker host. Install Docker
Engine and the Compose plugin on that host first. Arrange a hostname, HTTPS access
and Google web sign-in configuration, then obtain the trusted coordinator archive
and checksum from your administrator.

Extract the verified release and run its guided setup:

```bash
sha256sum -c godfather-0.9.0-rc.1-linux-amd64.tar.gz.sha256
tar -xzf godfather-0.9.0-rc.1-linux-amd64.tar.gz
cd godfather-0.9.0-rc.1-linux-amd64
bash scripts/setup.sh
```

Setup asks for your hostname, founder Google email, Google OAuth client details
and installation data folder. It loads the packaged images and starts the
Command Center. See [coordinator installation, updates and backups](docs/operations/coordinator-installation.md)
for prerequisites and exact maintenance commands. Windows users can run a local
checkout using Docker Desktop with WSL2; follow [local setup](docs/operations/setup.md).

## Help

- **Not authorized to sign in:** verify the invited Google email and invitation.
- **Computer is offline:** open Consigliere, check the saved address and connection
  message, and reconnect the existing computer rather than registering a duplicate.
- **Connected, waiting for an AI model:** enable an existing local model or set up a
  model/API connection, then grant its workspace access.
- **No compatible worker:** check the selected agent/model, worker permissions,
  workload environment and whether the computer is paused.
- **Upgrade:** quit the old tray app before replacing it; normal upgrades retain
  identity, settings and project permissions.

The [documentation index](docs/README.md) groups user guides, administrator guides,
release verification and development history. Developers should start with the
[development guide](docs/development.md).
