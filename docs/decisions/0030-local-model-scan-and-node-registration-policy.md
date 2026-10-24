# Owner-initiated model scanning and configurable node registration

Status: owner authorized local implementation, 2026-10-23. Publishing,
packaging and deployment remain on hold.

The desktop worker needs to find models outside Ollama, without silently
searching an owner's files or granting new execution permissions. Platform
administrators also need to restrict who can add computers independently of
an existing node owner's ability to connect and contribute.

## Local model scan

**Scan for Local Models** starts a background, cancellable metadata search.
Search common model libraries and owner-selected folders, plus loopback model
servers. Return at most 128 distinct results and report omitted results,
unreadable entries and incomplete/cancelled scans. Bound filesystem work to
100,000 entries and approximately 60 seconds; bound each server probe separately.
Do not follow directory symlinks/junctions below the search roots, execute model code, deserialize
weights, download models, start runtimes, or use provider credentials. Readable
Hugging Face snapshot file links remain supported.

Detected files are local inventory with unverified runtime support, not
schedulable deployments. Local paths remain in the desktop results, outside
jobs, scheduler state and artifacts. The owner's separate **Use detected local
text servers** action saves loopback OpenAI-compatible connections and enables
their declared chat/stream operations through the existing model gateway.
Preserve owner opt-ins, existing connections, workspace authorization, download
permissions and the eight-provider limit. The combined advertised deployment
inventory remains capped at 128; excess inventory must not crash the worker.
An explicit scan's OpenAI-compatible model selection bounds later refreshes.
Ollama retains its existing refresh behavior so owner-approved downloads appear.

This is broad discovery for supported libraries/formats, not a guarantee of
finding arbitrary, inaccessible, encrypted or proprietary model installations.
Custom directories and server ports are explicit additions to the search.

The scanner uses documented [Hugging Face cache structure](https://huggingface.co/docs/huggingface_hub/guides/manage-cache),
[LM Studio model layout](https://lmstudio.ai/docs/app/advanced/import-model)
and [GPT4All locations/server settings](https://docs.gpt4all.io/gpt4all_desktop/settings.html).

## Node registration permissions

Store `members_can_add_nodes` and `contributors_can_add_nodes` in the existing
PostgreSQL `application_settings` table. Both default to true to preserve ADR
0029's deployed behavior. Platform administrators can add their own computers;
turning off both switches restricts new nodes to administrators. For accounts
with multiple roles, any allowed assigned role suffices.

Expose the effective `nodes.add` capability in authenticated account responses.
Keep `nodes.contribute` for existing connections, worker authentication and
scheduling. Enforce the new policy at pairing approval, credential exchange,
manual credential issuance and first worker registration. A pairing or unused
credential created before a restriction cannot bypass the latest policy.
Reconnecting a registered, owned node remains allowed under the existing offline,
ownership, credential replacement and unfinished-attempt checks. A credential
that never registered a node cannot use Reconnect to bypass the restriction.

Only platform administrators can read or update the role switches. Changes are
audited with before/after values. No schema migration, role promotion, restart
or change to node-owner host restrictions is needed. This extends ADR 0029 for
new node creation; existing contribution authorization remains unchanged.

## Connection and update feedback

Keep the reconnect warning directly under its browser pairing checkbox, linked
with `aria-describedby`, using the owner's requested wording and emphasis.
Display animated indeterminate progress beside the desktop connection status
while checking/downloading updates, stopping on completion or failure. Retain
verified catalogs, checksums, owner installation choices and idle handoff.

Show a small lock only after a successful authenticated worker registration or
heartbeat over the controller's certificate-verified HTTPS transport. Saved
identity, a configured HTTPS address and optional Tailscale connectivity alone
do not establish that state. Hide the lock on HTTP, disconnection, pause,
disabled/refused access, session conflict or worker failure. The indicator
describes the last confirmed transport; it is not a persistent socket monitor.
