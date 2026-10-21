# Same-computer reconnection — 2026-10-21

The owner requested retaining **Carbon** instead of making duplicate nodes or
choosing new names when moving from CLI to tray or recovering a lost connection.
Coordinator candidate **0.3.1-rc.4** keeps the tested **0.3.1-rc.3** worker installers;
the repair is in browser approval and the API, with migration
`0011_worker_reconnection`.

Browser approval has an explicit **Reconnect this computer** checkbox. The
approval binds to the existing credential ID under the signed-in owner, not just
its reusable name. Exchange locks that credential and its node, rechecks ownership,
account permission, live status and unfinished attempts, then permanently revokes
and archives the old credential, issuing a fresh credential attached to the same
node. The old session/inventory is cleared until registration. Node history,
provider references and owner permissions remain attached to the existing ID.
No host files or OS credential store are read by the coordinator.

New pairing without explicit reconnect cannot replace anything. Another admin
cannot target another owner's node. Administrative disable/drain states stay
effective; a credential revoked by its owner can be replaced by fresh owner
approval. Active attempts/liveness block replacement, checked both at approval
and exchange. Concurrent approvals cannot successively revoke the replacement:
only the approval bound to the still-current old credential succeeds. The retired
credential remains revoked, loses its node binding and has an internal archived
name in the credential audit list. Nodes still shows one computer under its
original display name. Existing lease/fencing checks remain unchanged.

## Verification and activation

- Full isolated PostgreSQL/API/Python suite: **454 passed, 4 optional native
  Git/container checks skipped**. Fresh/repeat migration included. Reconnection
  tests cover one retained node, fresh/revoked credentials, old-token rejection,
  cross-owner denial, active-worker recheck, concurrent approvals, unfinished
  attempts and disabled/draining controls.
- Ruff formatting/lint and strict mypy: passed (133 source files).
- Dashboard lint, strict TypeScript, production build and 15 component tests:
  passed. Fresh Edge against a local fixture tested the duplicate-name message,
  explicit reconnect selection and successful **Carbon** approval without browser
  errors. The fixture made no production account or credential changes.
- Native Windows desktop/controller checks: 14 passed. No worker source changed;
  the previously verified Windows/Apple silicon/Intel Mac rc.3 installers remain
  the downloads for this coordinator-only repair.

Final package and deployment evidence will be recorded after completion. No
physical recipient reconnection or provider inference is implied by these tests.
