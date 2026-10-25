# ADR 0032: Complete coordinator recovery

- Status: Accepted for finding #3, order #4
- Date: 2026-10-25

Quiesced PostgreSQL and artifacts remain the durable recovery pair. A backup now
also records the exact release, migration head, file hashes and fingerprint of the
private environment and effective API settings used at capture. A data backup alone is incomplete for disaster
recovery: account provider ciphertext requires the original provider vault key.

Use the existing API package and cryptography dependency for an offline AES-GCM
configuration export. It contains the complete private environment and binds it to
one data inventory. Keep the export outside the data backup and escrow its independent
random recovery key separately. Do not reuse the provider vault key, put secrets in
release archives, or create an application endpoint for exporting secrets. Input
files and output directories require private POSIX permissions; Windows operators
must provide equivalent ACLs. Recovery refuses overwrites.

Before traffic resumes, a read-only command verifies the exact migration head,
all database-referenced artifact bytes, checkpoint metadata, pinned workflow state,
provider-key decryption and expiration of restored active leases. It prints counts
and fixed error messages, never decrypted material. It runs with API writers stopped;
it neither migrates nor renews/fences jobs. Normal scheduler and worker lease/fencing
checks remain authoritative after startup.

Restore into fresh reviewed storage with the matching trusted release. Reconcile
security/consent changes and uncertain external effects since the snapshot. This
does not promise recovery of host files, GPU state, uncommitted work or effects
after the backup point. Older backups without an inventory need deliberate manual
configuration matching; do not manufacture a retrospective verification record.

The disposable drill uses a real dump, fresh PostgreSQL storage, restored artifact
bytes, recovered configuration and a synthetic encrypted provider key. Controlled
lease time proves stale writes fail before and after reassignment. No new service,
runtime dependency, worker protocol or production action is introduced.
