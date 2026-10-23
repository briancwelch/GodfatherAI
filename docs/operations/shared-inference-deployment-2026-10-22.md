# Shared inference and Distributed Tasks release verification

The owner explicitly requested packaging and deployment after the local implementation
milestone. Coordinator and Consigliere **0.8.0-rc.1** are now published at the existing
Command Center. The deployment occurred on October 22, 2026 in America/Los_Angeles
(October 23 UTC). No engines, weights or contributor-host settings were installed
or changed. See the [feature and owner setup guide](shared-inference-and-tasks-2026-10-22.md).

## Immutable packages

Coordinator and all three installers use the same clean source revision:
`bc0f9843a1bb8d75026d29000967489b8811ac1b`. The release contains the three shared
inference topology declarations, the renamed Distributed Tasks screen and compatible
legacy API, task variables, corner feedback and the factual Nodes heartbeat trace.
The external owner-configured engine performs device/model parallelism.

All eight jobs in [source CI](https://github.com/briancwelch/GodfatherAI/actions/runs/39899913368)
passed on that revision, including Windows/macOS/Linux, Python 3.12/3.14,
frontend checks and the real Linux container integration suite. The local source
report records the executed regression, focused PostgreSQL and browser checks.

Windows packaging passed temporary install/reinstall, frozen GUI/tray and isolated
OS credential-store checks. Both architecture jobs in the
[native Mac build](https://github.com/briancwelch/GodfatherAI/actions/runs/39901562202)
passed source GUI lifecycle, DMG architecture/checksum, bundled framework startup
and unapproved pairing checks. Existing unsigned Windows/ad-hoc Mac candidate
signing status remains; this is not Developer ID notarization or physical recipient
acceptance.

| Installer         | SHA-256                                                            |
| ----------------- | ------------------------------------------------------------------ |
| Windows x64       | `5665a5d68f2b963f766b661449b5b68116d2abac71984a5f387bc7d70b0b4ff7` |
| Mac Apple silicon | `8ebd95e7698363ba1f0c358a4d067586b51a8562f53694cad8d155c04c858117` |
| Mac Intel         | `d4712cddf3442b18c7af5be116df13a586b3dca5e572e1af1b051093ecc76f10` |

Coordinator archive: `godfather-0.8.0-rc.1-linux-amd64.tar.gz` (402,399,748 bytes).
SHA-256: `ecf7bb8cf3bf9359c3afe82c8366001b28a9ad5424ae2dad252a9888a4f6e8cf`.
Its manifest and running API report the exact source revision above. Runtime
build-start metadata is `2026-10-23T04:47:44.455298+00:00`. The database remains at
`0016_distributed_jobs`; this feature needs no new schema migration.

All **ten standard release gates passed**, including image verification, production
configuration, shell syntax, fresh/repeat migration, founder singleton, private
healthy services, authenticated proxy boundaries, all installer downloads, actual
PostgreSQL/artifact restore and restart persistence. The disposable test project
was removed; existing local application services were preserved. Additional packaged
API/dashboard audits confirmed canonical routes, topology contracts, literal output
substitution and compiled task/variable/toast/heartbeat components.

## Production activation and preservation

The existing backup/upgrade procedure activated
`/opt/the-godfather/releases/godfather-0.8.0-rc.1-linux-amd64` from coordinator
0.7.0-rc.2. The incoming archive was verified against the locally recorded SHA-256
before extraction. No jobs were active when the upgrade began. All five services
are healthy on the exact release images; only Caddy publishes host ports. The
production environment is byte-identical and retains mode 600.

Before/after stable fingerprints matched all of these records:

| Records                                       | Preserved count |
| --------------------------------------------- | --------------: |
| Users / Google identities                     |           3 / 3 |
| Workspaces / memberships                      |           4 / 2 |
| Node ownership and contribution policies      |               4 |
| Worker credentials                            |               6 |
| Jobs                                          |              22 |
| Distributed task groups / tasks               |           2 / 7 |
| Agents                                        |              10 |
| Artifacts / checkpoints                       |         24 / 12 |
| Provider connections / encrypted account keys |           4 / 1 |

All four existing workers were online after activation. No owner permission or
account-key setting was enabled by the release. Protected fingerprints contain
stable hashes, not decrypted credentials.

Paired backup `/opt/the-godfather/state/backups/20261023T045408-1504343` passed
checksums, PostgreSQL dump listing and artifact gzip integrity. No production
restore was performed. The preceding release remains available for the documented
rollback procedure. Server evidence is under
`/opt/the-godfather/state/deployments/shared-inference-20261022-rc1`.

## Public verification and remaining acceptance

All **83 public HTTPS checks passed** through normal DNS and verified TLS. The
published manifest exactly matches the release. All three 0.8.0-rc.1 installers were
downloaded and SHA-256 verified through both public hostnames (six full checks),
and both runtime catalogs matched the existing pinned catalog. Anonymous access,
foreign-origin denial, worker authentication and private API boundaries passed,
including the new shared-inference and Distributed Tasks routes. These checks
created no accounts, enrollments or jobs and made no inference calls.

Updated installers are available under **Nodes > Downloads** and through existing
workers' **File > Check for updates**. The coordinator and matching manifest were
activated together before publishing those installers. Existing node identity,
settings and owner consent survive normal updates. Participating workers need the
new version for task variables and shared-inference declarations.

Physical multi-GPU/multi-host inference, cross-location throughput, real Google
login and recipient-device installation were not exercised in this deployment.
Shared inference requires owners to configure their private engine/group and
verify actual device activity, cancellation and failure behavior. Wide-area mode
remains experimental. No billable inference, model downloads, DNS/firewall changes,
new services or contributor-host reconfiguration occurred.

Ignored local evidence: `.cache/shared-inference-release-0.8.0-rc.1/` (native
receipts, packaging logs, Windows report, deployment/postflight logs, public receipts
and hash-verified downloads). Standard release receipt:
`.cache/release-tests/cf80d8fe8efc/result.json`.
