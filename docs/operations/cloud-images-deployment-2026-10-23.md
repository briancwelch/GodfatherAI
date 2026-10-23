# Cloud image provider release verification

The owner authorized updating and publishing the worker and website on October 23,
2026 (America/Los_Angeles). Coordinator and Consigliere **0.9.0-rc.1** are published
at [Command Center](https://app.the-godfather.ai). This release adds explicitly
selected OpenAI and Google Gemini image generation through owner account keys.
See [cloud image setup](cloud-images.md) for the required local permissions.

## Packages and provenance

All coordinator images and three native installers use clean source revision
`8d4189ff2d5def765d6cc91bd6cbaef4805c0c0c`. The coordinator archive is
`godfather-0.9.0-rc.1-linux-amd64.tar.gz`, 402,500,491 bytes, with SHA-256
`c7c4bf704d53a9cb7447f318a4242287c1a231c4466b7055eb8b097a24ad5b38`. Build-start metadata is `2026-10-23T14:23:44.308029+00:00`.
Database head remains `0016_distributed_jobs`; no new migration is needed.

| Installer           | SHA-256                                                            |
| ------------------- | ------------------------------------------------------------------ |
| Windows x64         | `2d97226ce18fc2e6be93fa48d9f24808abb1fc42e036d20b8a5bc5b9a05f9123` |
| Mac (Apple silicon) | `b2bded91cafd9cbe8cc61c1aa65f62c25ed2fd5f54c3a2e2e2eaed678b135494` |
| Mac (Intel)         | `1bc44954e75bfc61cbfc7cabbe4ca2aee668da0fd716437a12020460533bd791` |

All 8 jobs in [source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39914013964) passed, including Windows/macOS/Linux,
Python 3.12/3.14, frontend checks and real PostgreSQL/container recovery tests.
The [native Mac run](https://github.com/briancwelch/GodfatherAI/actions/runs/39967927883) passed both Apple silicon and Intel builds,
source desktop lifecycle checks, DMG architecture/framework checks and bundled
startup tests. Windows passed temporary install/reinstall, frozen Tk/tray startup
and an isolated synthetic OS credential-store check. The frozen Windows bundle
contains the new cloud image worker and model gateway modules.

All **ten packaged release gates passed**, including saved image provenance,
private healthy services, repeat migrations, authentication boundaries, all
installer downloads, actual disposable database/artifact restore and restart
persistence. Additional offline checks verified both cloud image route contracts,
default-off permissions, compiled provider/consent UI and identical staged/published
worker catalogs. No provider call was made by these checks.

## Production activation and preservation

The received archive and every internal checksum were verified before activation.
The existing paired-backup procedure upgraded coordinator 0.8.1-rc.1 to
`/opt/the-godfather/releases/godfather-0.9.0-rc.1-linux-amd64`. No jobs were active
at the upgrade gate. All five services are healthy on the exact release images;
only Caddy publishes host ports. The environment is byte-identical and mode 600.

Before/after stable fingerprints matched all existing records:

| Record group            | Before | After |
| ----------------------- | -----: | ----: |
| `account_provider_keys` |      1 |     1 |
| `agents`                |     10 |    10 |
| `application_settings`  |      1 |     1 |
| `artifacts`             |     24 |    24 |
| `checkpoints`           |     12 |    12 |
| `credentials`           |      6 |     6 |
| `distributed_parents`   |      2 |     2 |
| `distributed_tasks`     |      7 |     7 |
| `google_identities`     |      3 |     3 |
| `jobs`                  |     22 |    22 |
| `node_ownership`        |      4 |     4 |
| `provider_connections`  |      4 |     4 |
| `users`                 |      3 |     3 |
| `workspace_members`     |      2 |     2 |
| `workspaces`            |      4 |     4 |

All four existing workers reconnected and were online after activation. Node
identities, ownership, contribution policies and API-key grants were preserved.
The release does not turn on cloud image permission or update contributor hosts
without their existing local consent.

Paired backup `/opt/the-godfather/state/backups/20261023T143031-1753137` passed its checksums, PostgreSQL dump listing and artifact
gzip integrity. No production restore was performed. Coordinator 0.8.1-rc.1 remains
available for the documented recovery procedure. Server evidence is under
`/opt/the-godfather/state/deployments/cloud-images-20261023-rc1`.

## Public acceptance and use

All **91 public HTTPS checks passed** through ordinary DNS and verified TLS.
The manifest matches the staged release. All three updated installers were fully
downloaded and SHA-256 checked through both hostnames (six checks). Both pinned
runtime catalogs matched. Anonymous access, foreign-origin denial, worker
authentication and private API boundaries passed, including new Gemini account-key
and cloud image submission paths. These probes created no accounts, enrollments
or jobs and made no inference calls.

Fresh headless Edge checks passed on the live sign-in page at desktop/light and
mobile/dark sizes: Bootstrap loaded, no garbled display text, no page errors and
no horizontal overflow. No Google sign-in was attempted. Authenticated cloud image
execution was tested with mocked provider HTTP and disposable PostgreSQL during
the source milestone, rather than using a private production account.

Update Consigliere using **File > Check for updates**, or obtain the new installer
under **Nodes > Downloads**. Keep the existing computer identity and settings.
Then enable account API access under **Settings > Resources** and cloud image
generation under **Settings > Workloads**. Add/reconnect your provider key in
**AI connections**, select the permitted owned computer, and use **Images** with
explicit provider billing and prompt-egress consent.

Provider billing/access and a real image generation remain owner acceptance.
Physical recipient installation, real Google login, actual image latency/quality
and provider quotas were not exercised. Windows remains unsigned and Mac builds
are ad-hoc signed development candidates; publisher signing/notarization is not
claimed. No paid inference, model downloads, DNS/firewall changes, new host services
or contributor-host reconfiguration occurred.

Local deliverables are retained under `dist/`. Private evidence, native receipts,
package test logs and public downloads are under
`.cache/cloud-image-release-0.9.0-rc.1/`. The packaged receipt is
`source/.cache/release-tests/edea8648c445/result.json` within that evidence folder.
