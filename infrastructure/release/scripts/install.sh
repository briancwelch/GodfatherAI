#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
action=${1:-}
[[ "$action" = install || "$action" = upgrade ]] || { echo 'Usage: install.sh install|upgrade' >&2; exit 1; }
exec 9>"$GODFATHER_STATE_DIR/deploy.lock"
flock -n 9 || { echo 'Another installation is running' >&2; exit 1; }
verify_release
[[ $(uname -m) = x86_64 ]] || { echo 'This release requires Linux AMD64' >&2; exit 1; }
[[ $(nproc) -ge 2 ]] || { echo 'At least 2 vCPUs required' >&2; exit 1; }
awk '/MemTotal/ {exit ($2 < 3500000)}' /proc/meminfo || { echo 'At least 4GB host RAM required' >&2; exit 1; }
available=$(df -Pk "$GODFATHER_STATE_DIR" | awk 'NR==2 {print $4}')
[[ "$available" -ge 15728640 ]] || { echo 'Need at least 15GiB free for images/backups' >&2; exit 1; }
current="$GODFATHER_STATE_DIR/current"
if [[ "$action" = install ]]; then
  [[ ! -e "$current" ]] || { echo 'Existing installation: use upgrade' >&2; exit 1; }
  [[ -z $(compose ps -aq) ]] || { echo 'Existing project containers: inspect before install' >&2; exit 1; }
  if docker volume inspect godfather-production_postgres-data >/dev/null 2>&1; then
    echo 'Existing database volume: use the reviewed recovery procedure' >&2; exit 1
  fi
else
  [[ -L "$current" ]] || { echo 'No current release found' >&2; exit 1; }
  previous=$(readlink -f -- "$current")
  [[ "$previous" != "$RELEASE_DIR" ]] || { echo 'Release already current' >&2; exit 1; }
  old_postgres=$(awk '/^godfather\/postgres:/ {print $2}' "$previous/image-ids.txt")
  new_postgres=$(awk '/^godfather\/postgres:/ {print $2}' "$RELEASE_DIR/image-ids.txt")
  [[ -n "$old_postgres" && "$old_postgres" = "$new_postgres" ]] || { echo 'Database image changes require a separately reviewed upgrade' >&2; exit 1; }
fi
# Import every image, including dependencies; never build/pull on the server.
docker load --input "$RELEASE_DIR/images.tar"
while read -r image expected; do
  [[ $(docker image inspect --format '{{.Id}}' "$image") = "$expected" ]]
  [[ $(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image") = linux/amd64 ]]
done < "$RELEASE_DIR/image-ids.txt"
while read -r image; do
  expected=$(awk -v tag="$image" '$1 == tag {print $2}' "$RELEASE_DIR/image-ids.txt")
  [[ -n "$expected" ]] || { echo 'Compose image override is outside this release' >&2; exit 1; }
done < <(compose --profile tools config --images)
# Validate Caddy offline: this command never obtains certificates or starts a listener.
compose run --rm --no-deps -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
if [[ "$action" = upgrade ]]; then
  # Back up with the OLD images/schema. Services stay stopped if any later step fails.
  GODFATHER_DEPLOY_BACKUP=1 GODFATHER_KEEP_STOPPED=1 bash "$previous/scripts/backup.sh"
  compose stop caddy dashboard api
fi
compose up -d --wait --wait-timeout 120 --pull never postgres redis
compose --profile tools run --rm --no-deps -T migrate
# Never continue startup after failed migration. No automatic schema downgrade.
compose up -d --wait --wait-timeout 180 --pull never api dashboard caddy
if [[ "$action" = upgrade ]]; then
  ln -sfn -- "$previous" "$GODFATHER_STATE_DIR/previous"
fi
ln -sfn -- "$RELEASE_DIR" "$current"
echo 'Release healthy. Complete real Google login and worker acceptance before declaring production ready.'
