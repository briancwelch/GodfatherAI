# Cloud image generation through owner account connections

Accepted for implementation by the owner, 2026-10-22. Deployment and live billable
acceptance remain separate actions.

Coordinator and worker **0.9.0-rc.1** were published with owner authorization on
2026-10-23; see [release verification](../operations/cloud-images-deployment-2026-10-23.md).
Live billable image acceptance remains separate.

Extend the existing model gateway, encrypted account connections and fenced
workflow execution with OpenAI Images and Google Gemini native image APIs.
This supersedes Phase 12's local-only image boundary for explicitly selected
cloud image jobs. Local AUTOMATIC1111 remains available without cloud fallback.
No new dependencies, services or database migration are required.

Account model discovery uses authenticated model-list GET requests and a reviewed
image-model allowlist. Catalog entries declare image modality; deployments expose
only `image_generation`. They cannot execute text requests. Gemini account keys
use the existing AES-GCM vault and owner-selected computer grants. Credentials
are delivered only to an owned worker with account API opt-in; image catalog
delivery additionally requires `cloud-images-v1`. Older workers retain their
text-only payload shape. Existing account keys must be saved again to refresh
their provider catalog; existing credentials are never inferred or replaced.

Consigliere has a separate, default-off cloud image permission. CLI workers require
`--account-providers --cloud-images --execute-workflows --allow-tool-permission
images.generate`. Cloud generation does not require a local GPU, image runtime or
Docker. Scheduling still checks worker health, workspace model permissions,
resource capacity, ownership, protocol and exact model/connection compatibility.
The chosen connection identifies an individually permitted computer. There is no
automatic cross-computer, cross-account or local-to-paid fallback.

Owner-authorized usability correction, 2026-10-23: the image picker also shows
discovered models blocked by the selected workspace's model allowlist, following
[the model directory's inventory/permission distinction](0021-discovered-models-and-workspace-use.md).
The response labels this inventory as restricted; it still checks private account
access and node-owner consent. A workspace owner or administrator may explicitly
allow the selected model through the existing model-access endpoint. A member
receives administrator guidance. Listing or allowing a model never submits a job
or grants paid-call consent. Existing workspace grants are preserved during
deployment. Missing local models are not reported as a cloud-generation blocker.

The Images form selects a provider and exact owned connection/model, with explicit
provider billing and prompt-egress consent. The backend verifies the same route.
Immediately before egress the worker obtains a durable invocation marker under
the existing active lease/fence and current owner permissions. The image call key
is fixed and a second invocation for that job is refused. Retry limit is zero;
manual paid retry is refused. Disconnect, cancellation, malformed output or an
uncertain provider response leave the marker for review. Cancellation cannot
retract provider acceptance or charges. Successful provider token counts are
informational; Godfather does not estimate image prices or impose billing caps.

Initial scope is text-to-image, one 1024 x 1024 PNG per job. Sampling steps and
seeds remain local-only controls. Native transports use fixed official HTTPS
origins, no environment proxy, redirects, URL-result downloads or HTTP retries.
Responses are bounded to 8 MiB, encoded images to 4 MiB, and decoded dimensions
are checked before PNG re-encoding. Provider metadata is discarded; the existing
checksummed, workspace-scoped artifact/download path remains authoritative.
No image editing, reference uploads, streaming previews or provider tool use is
introduced.

API contracts checked against the official [OpenAI image reference](https://developers.openai.com/api/reference/resources/images/methods/generate),
[Gemini GenerateContent image guide](https://ai.google.dev/gemini-api/docs/generate-content/image-generation)
and [Gemini model-list reference](https://ai.google.dev/api/models) on 2026-10-22.
Provider account availability, billing, verification and quotas require live
acceptance; mocked HTTP is not evidence that a real account can generate.
