# Same-computer reconnection — 2026-10-21

The owner requested retaining **Carbon** instead of making duplicate nodes or
choosing new names when moving from CLI to tray or recovering a lost connection.
Deployed coordinator **0.3.1-rc.4** keeps the tested **0.3.1-rc.3** worker installers;
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
- [All source CI jobs passed](https://github.com/briancwelch/GodfatherAI/actions/runs/39669041505),
  including native Windows/macOS/Linux Python/dashboard checks and the Linux
  PostgreSQL, worker-process, scheduler and recovery gates.

The coordinator package is `godfather-0.3.1-rc.4-linux-amd64.tar.gz`, SHA-256
`04c30619d4c3191f239d069c1e901729b0ce6dc8ad799e93de493218b211bc4a`,
built from clean source `f7930a3eb1755a98a84d789019f1544b4f28c904`.
The saved-package release check passed image/config validation, fresh/repeat
migration, private service health, anonymous denial, paired database/artifact
restore and restart persistence. Evidence is
`.cache/release-tests/e178745a4c5f/result.json`.

## Authorized production deployment

After explicit owner approval for rc.4, the uploaded package checksum and all
internal release checksums matched. The installer deployed it with migration
`0011_worker_reconnection`; all five services were healthy. The PostgreSQL image
was unchanged, and PostgreSQL/Redis still had no host ports. The private
environment, including vault/proxy keys, was byte-identical and remained root-owned
mode 600. The previous release pointer is rc.3.

Before/after fingerprints confirmed preservation of 2 users, 2 Google identities,
2 workspaces, 2 credentials, 1 node ownership/policy, 3 jobs, 2 artifacts,
1 checkpoint and 1 provider connection. There were no active jobs or seeded account
keys. No credential was replaced on the user's behalf: the existing node remained
offline, ready for its owner to approve reconnection.

The paired backup at
`/opt/the-godfather/state/backups/20261021T203539-657071` passed checksums,
`pg_restore --list` and artifact gzip validation. Private deployment evidence is
`.cache/coding-setup/reconnect-postflight.log`.

Fresh public TLS checks against rc.4 verified all three worker installer hashes,
anonymous worker/account endpoint denial, human-session gates, hidden internal
API/health endpoints and foreign-origin mutation rejection. A fresh Edge browser
verified the login page, optional legacy invitation-code UI, pairing sign-in gate,
and real Google redirect with PKCE and identity-only scopes. Evidence is
`.cache/coding-setup/public-result.json` and `live-browser-result.json`.

Actual owner reconnection, signed-in results/settings acceptance and real provider
key/inference acceptance remain separate checks. No private session was forged or
copied and no billable inference was performed. No later workload phase was started.

## Owner's next steps

1. In the rc.3 tray worker, click **Connect** to open a fresh approval page.
2. Sign in as the existing computer's owner, enter **Carbon**, check **Reconnect
   this computer**, compare the code and approve.
3. Return to the worker. The same **Carbon** node should become online; keep using
   the current worker build. Routine updates retain its saved OS-store connection.

Do not revoke the node first. The old worker must be stopped for at least the
offline interval and its unfinished work must settle. The signed-in Command Center
footer should show `0.3.1-rc.4 · f7930a3e`.
