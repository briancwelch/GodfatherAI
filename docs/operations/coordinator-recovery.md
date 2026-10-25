# Complete coordinator recovery

This is an operator procedure, not authorization to restore production. Keep API,
scheduler and public traffic stopped until checks pass. The original coordinator
must remain stopped and isolated; never run writers against two database copies.
Restore to new empty volumes and retain the failed installation for diagnosis.
Never use `down -v`, an Alembic downgrade, or an old image against a newer schema.

## Recovery inventory

| Item                          | Capture and protection                                                                                                                                                                 | Restore requirement                                                                                                                                                                                                                                    |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| PostgreSQL                    | Confidential `database.dump`, custom-format dump with API writers stopped                                                                                                              | All identities, session/worker credential hashes, consent/grants, jobs, attempts, fences, events, encrypted account keys, checkpoint/artifact metadata and bootstrap closure. Restore the whole database with matching PostgreSQL major version.       |
| Artifacts                     | Confidential paired `artifacts.tar.gz`, same stopped-writer window                                                                                                                     | Entire `artifacts/v1` tree, including committed outputs, coding patches/workspace envelopes and checkpoints. Preserve UID/GID 10001. Never substitute an unrelated snapshot.                                                                           |
| Private configuration         | Separately encrypted export below                                                                                                                                                      | Exact `production.env`: database password, Google client ID/secret and bootstrap settings, origin/hosts, ACME contact, proxy token, **original provider vault key**, and locally added values. Never generate a new vault key for existing ciphertext. |
| Recovery key                  | Independent 32 random bytes, escrowed separately from both data backup and encrypted export                                                                                            | Required to decrypt the export. This is neither a provider API key nor the provider vault key. Losing it makes the export unusable.                                                                                                                    |
| Matching software             | Trusted coordinator archive and expected hash, saved images/IDs, Compose/Caddy files, release metadata and migrations                                                                  | Match release and exact database migration head. Keep current and five previous releases, checking schema compatibility. Preserve worker downloads and manifests from that release.                                                                    |
| Backup metadata               | `recovery.json` and `SHA256SUMS` with the data pair                                                                                                                                    | File hashes, migration head and whole-environment fingerprint; no environment values. The encrypted export authenticates and binds the inventory. Checksums alone do not establish authenticity.                                                       |
| Operator state/overrides      | Private record of `state/current`, `state/previous`, environment/state paths, Compose overrides and external volume mappings                                                           | Reconstruct reviewed paths/mappings. Overrides are not copied by `backup.sh`; escrow their contents under the same confidential policy or keep those settings in the private environment.                                                              |
| TLS and external access       | Protect Caddy `/data` and `/config` separately when certificate/ACME account continuity is required; preserve access to DNS, OAuth, firewall/SSH and optional Tailscale administration | Not part of the data pair. Restore approved Caddy state or separately authorize certificate reissuance. Verify hostnames, callbacks and operator access independently; keep internal ports private.                                                    |
| Owner-controlled worker state | Each owner backs up Consigliere identity/settings, local credentials, approved projects/repositories, models and shared-engine setup                                                   | Coordinator backup does not copy host files, private keys, installed models or uncommitted work. Reconnect existing identities; host changes still require owner consent. Lost credentials may require deliberate re-pairing.                          |
| Redis                         | No durable backup required                                                                                                                                                             | Recreate transient state; PostgreSQL remains authoritative.                                                                                                                                                                                            |

The recovery point is the quiesced data snapshot with matching configuration export.
Later work is outside that point. Keep confidential off-host copies under an approved
retention policy. This procedure does not upload anything or establish a recovery SLA.

## Capture configuration separately

Use a release containing `godfather_api.recovery`. `scripts/backup.sh` writes
`recovery.json` before restarting writers. It does **not** copy `production.env` or
its vault key into the data backup. Each complete recovery set additionally needs
the export below. Configuration changed since capture? Export refuses; take a new
paired backup rather than editing its inventory.

These Linux commands put only paths in arguments. Disable tracing and never print
the populated environment or expanded Compose configuration. Substitute reviewed
absolute paths and the trusted API image from the matching release's
`release.env`/`image-ids.txt`. Images must already be loaded and verified.
Inventory capture also checks that the configured vault key decrypts stored account
keys; a bad or missing key cannot silently produce a completed recovery inventory.

```bash
set -euo pipefail
set +x
umask 077
backup=/opt/the-godfather/state/backups/REVIEWED-SNAPSHOT
environment_file=/opt/the-godfather/production.env
api_image=REVIEWED-MATCHING-API-IMAGE
key_dir=/media/private-key-escrow/godfather
export_dir=/media/private-config-exports/godfather
install -d -m 700 "$key_dir" "$export_dir"
snapshot=$(basename "$backup")

# Once per recovery key; refuses to overwrite an existing key.
docker run --rm --pull=never --network=none --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL \
  --mount "type=bind,src=$key_dir,dst=/keys" \
  "$api_image" python -m godfather_api.recovery new-key --key-file /keys/recovery.key

# Each snapshot: encrypted export is mode 600 and cannot be overwritten.
docker run --rm --pull=never --network=none --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL \
  --mount "type=bind,src=$backup,dst=/backup,readonly" \
  --mount "type=bind,src=$environment_file,dst=/private/production.env,readonly" \
  --mount "type=bind,src=$key_dir,dst=/keys,readonly" \
  --mount "type=bind,src=$export_dir,dst=/exports" \
  "$api_image" python -m godfather_api.recovery seal-config \
  --backup /backup --input /private/production.env --key-file /keys/recovery.key \
  --output "/exports/$snapshot.enc"
```

Escrow the recovery key through a separately protected channel. Data/export access
must not imply recovery-key access. Test unsealing before declaring the set
recoverable. Retain old keys until their retained exports expire. POSIX checks
reject shared file permissions and output directories; on Windows provide equivalent
private ACLs. Never place plaintext secrets in evidence, logs, releases or Git.

## Restore configuration before services

Verify the trusted release and backup `SHA256SUMS`; check the dump with
`pg_restore --list` and archive with `gzip -t`. Privately retrieve the matching
encrypted export and independent key. Choose a new private configuration directory:

```bash
private_restore=/opt/the-godfather-recovered
install -d -m 700 "$private_restore"
docker run --rm --pull=never --network=none --read-only \
  --user "$(id -u):$(id -g)" --cap-drop ALL \
  --mount "type=bind,src=$backup,dst=/backup,readonly" \
  --mount "type=bind,src=$key_dir,dst=/keys,readonly" \
  --mount "type=bind,src=$export_dir,dst=/exports,readonly" \
  --mount "type=bind,src=$private_restore,dst=/private" \
  "$api_image" python -m godfather_api.recovery unseal-config \
  --backup /backup --input "/exports/$snapshot.enc" --key-file /keys/recovery.key \
  --output /private/production.env
```

Missing/malformed key files fail with a fixed input error. Wrong recovery keys or
damaged ciphertext fail authentication without writing the destination. Another
snapshot's export fails the binding check. Existing files are never overwritten.
Use recovered values, not newly generated database, OAuth, proxy or vault secrets.

## Restore the data pair and verify offline

Prepare a reviewed new Compose project/volume mapping using the matching release
and recovered environment. Use a distinct project name with **new empty** database
and artifact volumes. Inspect external/explicit volume names in overrides. No public
proxy or API should run yet. Substitute approved paths and a unique project name:

```bash
release_dir=/opt/the-godfather/releases/REVIEWED-MATCHING-RELEASE
restore_project=godfather-recovery-reviewed-unique-name
restore_compose=(docker compose --project-name "$restore_project"
  --project-directory "$release_dir"
  --env-file "$release_dir/release.env"
  --env-file "$private_restore/production.env"
  -f "$release_dir/compose.production.yaml")
"${restore_compose[@]}" config --quiet
for suffix in postgres-data artifacts-data; do
  if docker volume inspect "${restore_project}_${suffix}" >/dev/null 2>&1; then
    echo 'Recovery requires new empty volumes; review the project name and mappings' >&2
    exit 1
  fi
done
"${restore_compose[@]}" up -d --wait --pull never postgres redis
"${restore_compose[@]}" exec -T postgres pg_restore -U godfather -d godfather \
  --exit-on-error --no-owner < "$backup/database.dump"
"${restore_compose[@]}" run --rm --no-deps -T --user 0 --entrypoint python api -c '
import os, pathlib, sys, tarfile
root = pathlib.Path("/var/lib/godfather/artifacts")
assert not any(root.iterdir()), "Restore requires an empty artifact volume"
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
    archive.extractall(root.parent, filter="data")
for item in [root, *root.rglob("*")]:
    assert not item.is_symlink(), "Artifact links require review"
    os.chown(item, 10001, 10001)
' < "$backup/artifacts.tar.gz"

# One-shot check: no migration, scheduler, public listener or provider request.
"${restore_compose[@]}" run --rm --no-deps -T --user 0 --entrypoint python \
  --volume "$backup:/backup:ro" \
  --volume "$private_restore/production.env:/private/production.env:ro" \
  api -m godfather_api.recovery verify --backup /backup \
  --environment-file /private/production.env
```

The verifier also compares effective API settings, including secret values through
a fingerprint, with the captured settings. Shell/Compose overrides missing from the
recovered environment fail this check. Keep settings in the private environment and
escrow any explicit overrides; restore the original configuration before making
separately reviewed changes.

The verifier uses a read-only database transaction and reports counts/head only.
It checks referenced artifact hashes/sizes, checkpoint identity/references, latest
pinned workflow state and committed outputs, and decrypts **all** stored account
provider keys, including disabled historical keys, without contacting a provider.
Missing/wrong vault keys fail clearly without key/ciphertext values. Missing artifacts,
damaged checkpoints, unsupported legacy references or head mismatches stop recovery.
Do not drop records, generate a replacement key or silently use an older checkpoint.

Keep workers/traffic blocked until restored active leases expire against a correct
UTC clock. The verifier refuses live leases; it never edits fences or resets leases.
After verification, start only the API with public traffic blocked so normal lease
maintenance can mark expired attempts and schedule safe recovery. Reconnect compatible
workers deliberately. Verify stale attempts cannot renew, checkpoint or complete;
replacements must get higher fences and restore the committed prefix. The disposable
test proves these checks with controlled lease time, without waiting for real expiry.

Before real traffic, reconcile permissions, invitations, credential/key revocations,
node-owner consent and external actions since the snapshot. Restoring older state can
undo a later revocation or lose an action's completion record. Do not automatically
replay uncertain external effects. Preserve non-retryable paid/action jobs and
review-required states. Verify workspace access and actual Google/TLS/worker
connectivity under separate release approval. Recovery does not cover uncommitted
files, GPU state or changes after the backup point.

Older backups without `recovery.json` remain data backups. Retrieve their exact
configuration from existing escrow and perform deliberate legacy review. Do not
label newly invented metadata as evidence of the original configuration.

## Disposable acceptance

With existing dependencies and a local Docker Linux engine:

```powershell
$env:GODFATHER_RUN_RECOVERY = '1'
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/integration/test_recovery.py -q
```

On Linux set `GODFATHER_RUN_RECOVERY=1` for the same pytest command. It uses an existing
`postgres:17.11-bookworm` image (`--pull=never`; optional
`GODFATHER_RECOVERY_POSTGRES_IMAGE` selects another existing compatible image),
generated container IDs, loopback-only ports and temporary database storage. It
preserves normal Compose projects and `.env`, and removes its own containers.

Coverage: real dump/fresh restore, recovered configuration, synthetic encrypted
provider key, missing/wrong vault and recovery keys, migration head, artifact/checkpoint
corruption, read-only verification, downtime rejection, higher-fence reassignment,
committed-prefix recovery and secret-free errors. `tests/test_recovery.py` covers
encryption binding, tampering, permissions and non-overwrite behavior. CI runs the
real disposable drill as a separate step.
