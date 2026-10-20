# Proposed gateway extension: hybrid inference and owner-controlled BYOK

Status: **historical design, now being implemented under the explicitly authorized Phase 11 assignment**. See the [Phase 11 runbook](../operations/phase-11.md) and [boundary decision](../decisions/0012-phase-11-execution-and-provider-boundaries.md). The original proposal below retains its historical Phase 06/07 scope statements. Live paid calls still require separately supplied credentials and spending authorization.

## Boundary and defaults

Extend the existing model gateway and PostgreSQL-backed scheduler. Keep local inference, provider adapters, workflow execution, leases and fencing in their existing components; do not build a second orchestrator. Default jobs and agents to local-only routing. A local provider becoming unavailable must leave work queued or explicitly unavailable, never enable cloud spending. Exact models remain exact. Any fallback needs an explicit ordered allowlist and separate authorization covering provider, model, payer, data egress and spending. A configured key alone is not authorization to use it for somebody else's job.

Keep Phase 06 scoped to the currently authorized local workflow/checkpoint milestone. It must not add cloud adapters, a cost ledger, sharing policies, keychain access, approval endpoints or paid routing merely to anticipate this proposal. Those changes require a later explicit implementation assignment and its own tests/gate.

## Credentials and advertisements

Node owners provision their own provider-specific credentials on their own workers. Use an OS credential-store adapter where available: Windows Credential Manager, macOS Keychain, or a supported Linux secret store. Design an explicit owner-approved protected-file/environment alternative where a native store is unavailable, especially headless Linux. Verify actual store/backend availability; do not assume desktop keychains exist everywhere. Installation/service/account changes require separate approval. Key rotation/revocation must remain owner-controlled.

Worker configuration maps a private local credential reference to an opaque public provider/deployment alias. Central advertisements contain only provider kind, model identity/capabilities, billing class, owner-derived identity, permitted sharing-policy metadata and credential availability. Never send key material, local secret-store paths, secret contents or environment-variable names to the scheduler, another user, prompts, artifacts, telemetry or exception bodies. No central key-upload endpoint or automatic credential replication is planned. Both platform administrators remain subject to owner policy. Protect provider transports from redirects/proxies, require HTTPS remotely, redact errors and forbid model-generated endpoint/credential selection.

A compromised participating worker can access credentials its owner grants that process; the design cannot make an owner-controlled host untrusted while giving it usable keys. Prefer restricted provider keys/projects and provider-side limits when available, without claiming universal support.

## Adapter and routing contract

Retain the common discovery/inference/stream/cancel/error/usage interface. Add native provider adapters for OpenAI, Anthropic, Google Gemini and other reviewed providers where their protocols or usage semantics do not fit the existing OpenAI-compatible adapter. Reuse the compatible adapter only where its contract is actually satisfied. Verify official APIs, supported models, authentication, usage fields and cancellation/idempotency behavior at implementation time. Do not invent parity or silently translate unsupported features.

Version advertisements and invocation policy additively. Proposed billing metadata includes `local_unmetered` versus `api_billable`, credential-owner identity, permitted models/operations and a pricing reference. Local electricity/hardware costs are not implied to be zero. Paid invocation policy must specify allowed owners/providers/models, maximum output, allowed egress, optional approved fallback route, job/call limits and approval/grant references. Old workers lacking this protocol cannot execute billable jobs. Agents carry portable requirements/policies, never host keys or a permanent machine/provider binding.

## Sharing and authorization

Model sharing as owner grants with two independent dimensions:

| Sharing mode      | Required behavior                                                                                                                |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Private           | Only credential-owner jobs can use the deployment. Other users and platform admins cannot override this.                         |
| Approval-required | Each use needs an owner-issued, expiring, revocable grant bound to borrower, workspace, job, provider/model, purpose and limits. |
| Budget-limited    | Only explicitly permitted borrowers/workspaces can use a bounded owner grant. No implicit sharing just because budget remains.   |

Approval and budget limits can be combined. Owner jobs also respect configured budgets. Cross-user paid inference requires the credential owner's explicit spending consent, the submitting user's explicit paid-route/data-egress consent, workspace authorization, and the existing node-owner execution policy. Workspace membership or platform-admin status alone grants neither spending nor key access. Enforce these checks both transactionally in the backend and immediately before the worker's provider call. Health controls must never edit billing consent. Revocation blocks new calls; an already accepted external call may still incur charges.

## Durable accounting and safeguards

Use PostgreSQL for metadata-only grant, pricing, budget, reservation and invocation/settlement records. Separate the job submitter from the credential owner/payer. Track per-owner and per-job totals, including all attempts and resumed workflow calls; optionally group by workspace/provider. Use decimal amounts or integer currency subunits with explicit currency and price-version identifiers, never binary floating-point money or implicit currency conversion.

Before a billable call, atomically verify all permissions and reserve a conservative amount against call, job and owner-period budgets under locks. Account for concurrent reservations across every node that uses that owner's allowance. Price the exact model, maximum output, estimated input, cache/reasoning/other billable units where supported, and a disclosed margin. Unknown pricing/usage must not be treated as zero or free: fail closed or require a distinct explicit reviewed override. Bound provider parameters before dispatch.

Persist an invocation ID and authorization tied to job, workflow step, attempt, node, fence, payer and selected route before contacting the provider. Workers require a fresh authorized reservation and valid lease; no new paid calls when the coordinator cannot approve them. Authenticate worker usage reports and store provider-reported units separately from estimates. Settle idempotently, release unused reservations only when justified, and retain unreconciled liabilities after disconnects/timeouts. Usage/cost summaries contain identities/counts/amounts, not prompt or response text. Restrict payer-ledger visibility to that owner and explicitly authorized views.

Use a versioned owner-approved pricing catalog, verified against official provider pricing during implementation/updates. Present estimated cost, reported usage, estimated settled cost, and provider-confirmed billing distinctly. Provider invoice reconciliation can be manual/imported initially; do not access billing accounts without authorization. Late usage or charges from a fenced attempt must have an audited accounting-only reconciliation path that cannot change workflow results or checkpoint ownership.

Application spending limits are **safeguards, not guaranteed billing caps**. Provider-side lag, unknown usage, interrupted requests, pricing changes, retries, requests outside The Godfather, and already accepted calls can exceed estimates. Never display an estimate as an invoice or promise that cancelling a stream prevents billing. Provider-side account limits, when configured separately by the owner, are additional safeguards whose semantics must be verified.

## Recovery and failure handling

Preserve existing transactional claims, attempt identities, fencing, deadlines and checkpoint commits. Check both execution ownership and spending authorization immediately before each new paid invocation. A stale attempt cannot mutate workflow results; fencing cannot retract an external API call already accepted by a provider.

Keep completed checkpoint steps committed; do not pay to repeat them during resume. For uncertain calls, record `reconciliation_required` and retain reservations rather than silently repeating billable work. Use provider idempotency/retrieval only where documented and tested. An approval for one call is not unlimited approval for retries. Any automatic paid retry needs explicit bounded retry-spend authorization and a fresh reservation; otherwise pause for approval/reconciliation.

Failover may use only a compatible node whose owner has independently provisioned the required credential and approved the same paid route/payer/grant. Never copy a key through a checkpoint or silently use another owner's account. Credential unavailability, grant expiration/revocation, exhausted budget or uncertain prior charges leave work queued or explicitly blocked for review. Local-to-cloud and cross-payer fallback require new approval unless already specifically authorized.

## Implementation sequence, only after authorization

1. Finalize versioned policy/usage contracts and an ADR; add guarded additive metadata migrations and worker-local credential-store adapters with mocked secrets.
2. Implement native provider adapters with deterministic contract tests. No live account calls during development without explicit authorization.
3. Add transactional grants, reservations, settlement/reconciliation and per-owner/per-job views; test concurrent reservations and revoked/expired grants.
4. Connect authorization-aware routing to the existing scheduler/gateway/workflow steps. Preserve local-only defaults and exact model requirements.
5. Add authenticated policy/approval/metrics APIs and operational documentation; full dashboard changes remain separately scoped.
6. Perform explicitly authorized low-budget live tests for selected accounts/providers. Verify redaction and owner isolation before enabling cross-user use.

Required acceptance includes Windows/macOS/Linux credential-backend mocks, unavailable key stores, no-secret advertisements/logs/artifacts, private/approved/budget-limited sharing, admin non-bypass, local-to-paid fallback refusal, concurrent budget reservations, unknown pricing/usage, approval expiry/revocation, cancellation, retries, stale workers, duplicate/late settlement, checkpoint resume without repeating committed calls, and failover without key transfer or payer substitution.

Open implementation decisions: which provider accounts/models are approved first, which currency/catalog maintenance policy to use, initial call/job/owner-period limits, acceptable data-egress/retention policies, available native secret stores, who may approve spending on each owner's behalf (default owner only), and whether any paid retries/fallbacks should be enabled (default disabled). None blocks the present design or authorizes implementation.
