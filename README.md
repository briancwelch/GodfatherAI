# The Godfather

The Godfather is a private AI workspace that lets a group run tasks using its own
computers and AI models. You manage your work in a browser, and a companion app
called **Consigliere** connects the computers that do the work.

**Project status: inactive as of November 10, 2026.** This repository preserves
the source for reference and anyone who wants to run their own installation.
Updates, support, hosted access and installer downloads are not guaranteed.
The last recorded release was **0.12.0-rc.2**, a preview release.

## What it can do

- Run AI requests with models on your own computers or an API provider you choose.
- Organize people, agents and jobs into private or shared workspaces.
- Produce coding changes for review, images, data analysis and reports.
- Follow job progress, read results and download available files.
- Let computer owners choose which resources and projects they contribute.
- Coordinate tasks across compatible computers, including shared model inference
  when the required setup and owner approvals are in place.

Features depend on the connected computers, installed models and permissions.
Connecting a computer does not give other members unrestricted access to its files.

## What you need

To use an existing installation, ask its administrator for:

- The **Command Center address**: the website where you sign in and manage jobs.
- An invitation for your Google account.
- A trusted Consigliere installer if you want to contribute a computer.

This source repository does not include a working account, API keys or private
configuration. Historical website addresses in the documentation are examples or
records of previous installations; they do not guarantee an available service.

You only need a browser to use a Command Center that someone else hosts.
Consigliere is needed on computers that will perform jobs. Desktop installers
were produced for Windows x64, Apple Silicon Mac and Intel Mac; Linux uses the
[source installation guide](docs/operations/worker-distribution.md).

## Get started

1. Open the Command Center address supplied by your administrator and choose
   **Continue with Google**. Use the account that received the invitation.
2. Open **Workspaces** and choose or create a workspace for your work.
3. If you are contributing a computer, open **Nodes > Downloads** or **Connect a
   computer**. Obtain the matching installer, install Consigliere and open it.
4. Enter your Command Center address in Consigliere, choose **Connect**, and
   approve the matching pairing code in your browser.
5. Choose which capabilities and projects that computer may contribute. Use
   **Pause** when you want it to stop accepting new work.

Workers connect outward to the Command Center. You do not need to open an inbound
port on your home network. Closing the Consigliere window normally leaves it in
the system tray; choose **Quit** to stop it.

See the [worker guide](docs/operations/consigliere-ui.md) for installation,
connection settings and updates. Preview installers were unsigned on Windows and
ad-hoc signed on Mac; obtain them from an administrator you trust.

## Choose an AI model

An agent needs a model that an available computer is allowed to use.

- **Use local AI:** in Consigliere, open **Models & API connections** and allow an
  installed model. If you need to download one, enable downloads on that computer
  first. In the Command Center, open **Models** and allow the model in your workspace.
- **Use an API provider:** open your personal **AI connections**, add your own
  provider key and select the computers allowed to use it. Each computer also needs
  local API access enabled. Google sign-in does not provide an AI API key.

API providers may charge for usage. Select a paid model and confirm sharing data
with that provider before using it. Local model jobs do not silently switch to a
paid provider.

From **Models**, choose **Use model / create agent** or **Allow in workspace /
create agent**. An agent is a saved set of instructions, model choices and allowed
tools for a type of work.

See [model setup](docs/operations/worker-readiness-and-workspaces-2026-10-22.md)
and [API connections](docs/operations/coding-and-account-setup.md).

## Run a job

1. Open **Jobs** and select your workspace and agent.
2. Enter your request and submit it.
3. Open the job to follow progress, read the result and download any available files.

For coding work, first approve the local Git project and its file and test
permissions in Consigliere's **Projects** tab. Review the proposed changes and
reported test results before choosing **Apply to my project**.

Images, analytics and reports need their matching models or execution environments.
See [reviewing results](docs/operations/results-and-apply.md) and the
[documentation index](docs/README.md) for individual guides.

## If something is not working

| Problem                 | What to check                                                                               |
| ----------------------- | ------------------------------------------------------------------------------------------- |
| Cannot sign in          | Ask the administrator to check your invited email and invitation expiry.                    |
| Computer is offline     | Open Consigliere, check its saved address and reconnect the existing computer.              |
| Job stays queued        | Check that a compatible computer is online, unpaused and allowed to use the selected model. |
| No model is available   | Allow an installed model or configure an API connection, then grant workspace access.       |
| Coding job cannot start | Check the project's local permissions and required tools in Consigliere.                    |
| Job needs review        | Inspect its result and any previous effects before running it again.                        |

## Run your own installation

Self-hosting requires someone to maintain the Command Center, its database,
backups, HTTPS and Google sign-in configuration. You must supply your own settings
and credentials. The source does not automatically connect to a previous deployment.

Start with the [installation and backup guide](docs/operations/coordinator-installation.md).
For running from source on Windows, macOS or Linux, use the
[setup guide](docs/operations/setup.md). Local development opens at
**http://127.0.0.1:3000** once configured and started.

For source changes and checks, see the [development guide](docs/development.md).
Dated release reports describe past verification, rather than current service
availability or a promise of ongoing maintenance.
