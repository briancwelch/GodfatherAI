# Documentation

Start with the [user guide](../README.md) for sign-in, worker installation, models
and your first job. The Command Center and all three desktop installers are
published as **0.10.0-rc.3**. The [release verification](operations/shared-inference-release-2026-10-24.md)
records packaging, preservation and public checks. See [cloud image setup](operations/cloud-images.md)
for OpenAI/Gemini account connections and the required worker opt-ins.

The [local model scan and node permissions update](operations/worker-scan-and-node-permissions-2026-10-23.md)
is included, alongside the [worker Shared Inference wizard](operations/shared-inference-wizard-2026-10-23.md)
and owner-approved llama.cpp lifecycle management.

## Using the platform

| Task                                            | Guide                                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Invite people and sign in                       | [User onboarding](operations/user-onboarding.md)                                            |
| Install, update and configure Consigliere       | [Worker guide](operations/consigliere-ui.md)                                                |
| Contribute computers to a workspace             | [Simple contribution](operations/simple-contribution.md)                                    |
| Set up local AI and worker updates              | [Worker readiness and workspaces](operations/worker-readiness-and-workspaces-2026-10-22.md) |
| API keys and local coding projects              | [Account and project setup](operations/coding-and-account-setup.md)                         |
| Review and apply coding results                 | [Results and application](operations/results-and-apply.md)                                  |
| Shared inference, dependent tasks and variables | [Distributed Jobs and Tasks](operations/shared-inference-and-tasks-2026-10-22.md)           |
| Images, analytics and reports                   | [Workload instructions](history/phases.md#phase-12)                                         |
| Cloud image provider setup                      | [OpenAI and Gemini images](operations/cloud-images.md)                                      |
| Manage users, workspaces and jobs               | [Command Center management](operations/command-center-management.md)                        |

The worker readiness guide supersedes the older manual Ollama-only setup in the
Consigliere guide. Distributed Tasks is the current name for the task graphs called
Distributed Jobs in older guides; Distributed Jobs now means shared inference.

For shared colors, Bootstrap components, toasts and progress bars, see
[website appearance settings](operations/bootstrap-ui.md).

## Running a Command Center

- [Docker installation, updates and backups](operations/coordinator-installation.md)
- [Complete recovery inventory and protected configuration restore](operations/coordinator-recovery.md)
- [First administrator sign-in](operations/founder-bootstrap.md)
- [Portable worker packages and Linux/source setup](operations/worker-distribution.md)
- [Latest production/package verification](operations/member-node-registration-verification-2026-10-23.md)
- [Cleanup and six-release retention](operations/project-cleanup-2026-10-22.md)

## Development and history

- [Pending assessment orders and acceptance gates](operations/pending-assessment-work-2026-10-25.md)
- [Capacity truthfulness and model admission profiles](operations/capacity-and-admission.md)

- [Development setup and checks](development.md)
- [Consolidated phase history and acceptance evidence](history/phases.md)
- [Repository instructions](../AGENTS.md) and [UI/UX rules](design/UI-UX.md)
- [Architecture](architecture/) and [decision records](decisions/)
- [Versioned protocols](protocols/)

Dated deployment and verification reports remain under `operations/` as historical
evidence. Their release numbers, authorization and test counts apply to those
specific runs. Use the current user/operator guides for new installations.
