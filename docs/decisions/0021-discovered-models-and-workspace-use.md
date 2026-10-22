# Discovered models and explicit workspace use

Accepted 2026-10-21 for the owner-authorized model usability correction.

An installed/deployed model and permission to execute it in a workspace are
different states. An empty workspace model allowlist still denies all execution,
but must not hide the owner's discovered inventory and make setup impossible.
The Models page and unified picker show authorized node/provider inventory with
separate workspace access and worker availability. Agent options continue to
return only workspace-allowed models. No migration or policy reset is required.

An owner/workspace administrator can explicitly select **Allow in workspace /
create agent**. A transactional, audited action adds that one discovered model
identifier to the existing allowlist, preserving other model/tool restrictions.
It validates node contribution, account-key computer grants, provider connection
visibility, membership and model identity. Platform administration cannot override
workspace administration, node-owner consent or another owner's API credentials.
No paid inference or model download occurs during selection. Paid definitions and
runs retain explicit connection/model selection and per-run provider consent.

The download catalog labels installed node/provider/model tuples and disables
duplicate choices. **Use installed model** returns to the unified picker. A stale
catalog/duplicate-install response refreshes inventory and returns to selection.
The server's duplicate-request and already-installed guards remain in place.

Workers opting in to local or account models also advertise the existing workflow
protocol so model-only agents can execute. No host tools are granted by this;
coding, local paths, data environments and other tools retain separate opt-ins.
Existing worker protocols remain compatible, but this execution correction needs
the updated desktop worker.
