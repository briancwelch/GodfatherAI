#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
verify_release
if [[ ${GODFATHER_DEPLOY_BACKUP:-0} != 1 ]]; then
  exec 9>"$GODFATHER_STATE_DIR/deploy.lock"
  flock -n 9 || { echo 'Installation or another backup is running' >&2; exit 1; }
fi
exec 8>"$GODFATHER_STATE_DIR/backup.lock"
flock -n 8 || { echo 'Another backup is running' >&2; exit 1; }
backup="$GODFATHER_STATE_DIR/backups/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p -- "$backup"
# A single writer and no external side effects: freeze API/scheduler before snapshot.
running=$(compose ps --services --status running | grep -E '^(api|dashboard|caddy)$' || true)
resume() {
  if [[ -n "$running" && ${GODFATHER_KEEP_STOPPED:-0} != 1 ]]; then
    # Intentional word splitting: service names above are a fixed allowlist.
    compose up -d --wait --wait-timeout 180 $running
  fi
}
trap resume EXIT
compose stop caddy dashboard api
compose exec -T postgres pg_dump -U godfather -d godfather --format=custom > "$backup/database.dump.partial"
compose exec -T postgres pg_restore --list < "$backup/database.dump.partial" > /dev/null
mv -- "$backup/database.dump.partial" "$backup/database.dump"
compose run --rm --no-deps -T --entrypoint python api -c \
  'import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); t.add("/var/lib/godfather/artifacts",arcname="artifacts"); t.close()' \
  | gzip > "$backup/artifacts.tar.gz.partial"
gzip -t "$backup/artifacts.tar.gz.partial"
mv -- "$backup/artifacts.tar.gz.partial" "$backup/artifacts.tar.gz"
cp -- "$RELEASE_DIR/release.env" "$RELEASE_DIR/manifest.json" "$backup/"
# Record the exact private configuration fingerprint while writers remain stopped.
# Secrets themselves stay OUTSIDE this data backup. Export them separately using
# the encrypted configuration procedure in RECOVERY.md, with an independent key.
compose run --rm --no-deps -T --user 0 --entrypoint python \
  --volume "$backup:/recovery:ro" \
  --volume "$GODFATHER_ENV_FILE:/run/godfather-production.env:ro" \
  api -m godfather_api.recovery inventory --backup /recovery \
  --environment-file /run/godfather-production.env > "$backup/recovery.json.partial"
mv -- "$backup/recovery.json.partial" "$backup/recovery.json"
(cd -- "$backup" && sha256sum database.dump artifacts.tar.gz release.env manifest.json recovery.json > SHA256SUMS)
echo "$backup"
echo 'Data backup complete. Matching encrypted configuration export is required separately; see RECOVERY.md.' >&2
