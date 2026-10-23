# Bootstrap coordinator deployment verification

The owner requested deployment of the completed website changes on October 22,
2026 (America/Los_Angeles). Coordinator **0.8.1-rc.1** is active at
[the Command Center](https://app.the-godfather.ai). Consigliere installers remain
**0.8.0-rc.1**, byte-identical to the previous release. No worker build was performed.

## Release provenance and checks

- Clean source: `69071d5cd87ddbfd49cd7fe95a5d94b83fcab12e`.
- Archive: `godfather-0.8.1-rc.1-linux-amd64.tar.gz`, 402,447,373 bytes.
- SHA-256: `364ad8f3c84e826744089d142ebca97fb6436f950133ee64a308233f36aff92a`.
- Build-start metadata: `2026-10-23T06:04:59.631160+00:00`.
- All eight jobs in [source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39909184801) passed, including Windows/macOS/Linux,
  Python 3.12/3.14 and real PostgreSQL/container recovery checks.
- All ten standard packaged-release gates passed, including saved image IDs,
  production configuration, repeat migrations, private healthy services,
  authentication boundaries, installer downloads, real backup/restore and restart
  persistence. Receipt: `.cache/release-tests/089769e88a9c/result.json`.
- Additional offline image checks verified the new API appearance defaults,
  compiled Bootstrap controls/toasts/progress and worker capability rows. The
  worker download manifest is exactly the preceding release's manifest.

The source [Bootstrap guide](bootstrap-ui.md) records the implementation tests,
including 41 component tests, 345 native Python tests, four focused PostgreSQL
checks and the local browser tests of all main screens with mocked login.

## Activation and preservation

The existing paired-backup upgrade activated
`/opt/the-godfather/releases/godfather-0.8.1-rc.1-linux-amd64` from 0.8.0-rc.1.
The received archive was checked against the local SHA-256 before extraction,
and all internal release checksums passed. No jobs were active at activation.
All five production services are healthy on the exact release images. Only Caddy
publishes host ports; API/dashboard/PostgreSQL/Redis remain private.

The production environment is byte-identical and mode 600. Before/after hashes
matched every existing record in these groups:

| Records                                       | Preserved count |
| --------------------------------------------- | --------------: |
| Users / Google identities                     |           3 / 3 |
| Workspaces / memberships                      |           4 / 2 |
| Node ownership / credentials                  |           4 / 6 |
| Jobs                                          |              22 |
| Distributed groups / tasks                    |           2 / 7 |
| Agents                                        |              10 |
| Artifacts / checkpoints                       |         24 / 12 |
| Provider connections / encrypted account keys |           4 / 1 |
| Stored application settings                   |               0 |

All four existing workers reconnected and were online after activation. No new
owner grants, keys or contribution settings were enabled. No stored appearance
rows existed before this release; the validated defaults apply until an admin
saves settings. Database head remains `0016_distributed_jobs`; no new migration.

Backup `/opt/the-godfather/state/backups/20261023T061720-1542700` passed checksums,
PostgreSQL dump listing and gzip integrity. No production restore was performed.
The preceding release remains available under the documented recovery procedure.
Server evidence is under `/opt/the-godfather/state/deployments/bootstrap-20261022-rc1`.

## Live acceptance and limits

All **83 public HTTPS checks passed** using ordinary DNS and verified TLS,
including anonymous denial, origin enforcement, private API boundaries, matching
runtime catalogs and all six unchanged installer downloads across both hostnames.
No test accounts, enrollments or jobs were created in production.

Fresh headless Edge checks verified that the live sign-in page loads Bootstrap
styles at desktop/light and mobile/dark sizes, without garbled display characters,
page errors or document horizontal overflow. No Google sign-in was attempted.
Authenticated screen/admin acceptance was tested locally with mocked Google and
real disposable PostgreSQL, not by accessing a private production account.

Refresh the website to load the new UI. Shared Bootstrap options are under
**Admin settings > Site appearance**, including controls, panels, semantic colors,
tables, toasts and React-driven progress. No paid inference, model downloads,
worker-host changes, DNS/firewall edits or new host services were performed.

Private local receipts, logs and screenshots are in
`.cache/bootstrap-release-0.8.1-rc.1/`; they are excluded from Git.
