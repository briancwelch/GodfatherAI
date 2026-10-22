# Worker readiness and workspace experience

Accepted for the owner-authorized milestone, 2026-10-22. The owner separately
authorized publishing downloads and deploying Command Center after validation.

Workers check their configured coordinator's HTTPS download catalog, compare native
platform semantic versions, prompt by default, and verify SHA-256 before handing
off to the existing native installer. An owner-local setting enables unattended
updates. A maintenance event ends polling only between attempts, allowing assigned
work to finish before installation. Connection credentials and contribution/project
data retain their existing locations. Linux portable builds use an equivalent
per-user replacement adapter. No remote shell, service installer or new control
plane is introduced. Source checkouts have no released version to compare.

Ollama runtime installation is distinct from a model pull. Owners may explicitly
enable portable runtime setup on their own worker. The coordinator publishes a
pinned official artifact catalog containing upstream URLs and SHA-256 digests;
the worker checks HTTPS/redirect hosts, platform, archive paths and checksums.
Runtime files remain in the owner's worker data folder; inference binds to loopback.
The app's Get started flow prepares Ollama, then opens the existing model catalog.
Command Center may include runtime setup in an existing fenced `model.install`
job only after the worker advertises the independent `ollama.setup.v1` consent.
No API key, billable inference, shared filesystem or public Ollama port is added.
Model bytes come from Ollama's registry through its local pull API. Runtime bytes
come from the pinned official release, using metadata published by Command Center.
They are not served by another contributor's node.

The new input flag is omitted when false so existing workers can still consume
ordinary model-install jobs. Only opted-in new workers can match runtime-setup
requirements. Spending, workspace model allowlists and tool permissions remain
independent. An unavailable provider is never treated as permission to install.

Overview aggregates jobs and agents across the account's authorized workspaces.
Workspace detail retains scoped counts, model capacity and history. Workspaces is
a dedicated first-class directory. Account settings is self-service; Admin
settings remains role-gated. A JSONB profile migration records owner customization
so subsequent Google sign-ins update contact email without overwriting the chosen
display name/avatar. Avatar URLs load in the viewer's browser and have branded
initials fallbacks; the coordinator never fetches remote avatar bytes.

Images and Analytics and Reports keep existing execution contracts, with distinct
routes and collapsible, responsive worker-readiness panels. Worker-side job
submission was explicitly deferred by the owner.
