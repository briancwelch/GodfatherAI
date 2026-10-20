#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
RELEASE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
: "${GODFATHER_ENV_FILE:?Set an absolute path to the private production environment file}"
: "${GODFATHER_STATE_DIR:?Set an absolute path to persistent operator state, e.g. /opt/the-godfather/state}"
[[ "$GODFATHER_ENV_FILE" = /* && "$GODFATHER_STATE_DIR" = /* ]] || { echo 'Use absolute operator paths' >&2; exit 1; }
[[ -f "$GODFATHER_ENV_FILE" ]] || { echo 'Private environment file missing' >&2; exit 1; }
[[ $(stat -c %a "$GODFATHER_ENV_FILE") = 600 ]] || { echo 'Environment file must have mode 600' >&2; exit 1; }
mkdir -p -- "$GODFATHER_STATE_DIR"
compose() {
  docker compose --project-name godfather-production --project-directory "$RELEASE_DIR" \
    --env-file "$RELEASE_DIR/release.env" --env-file "$GODFATHER_ENV_FILE" \
    -f "$RELEASE_DIR/compose.production.yaml" "$@"
}
verify_release() {
  (cd -- "$RELEASE_DIR" && sha256sum --check --quiet SHA256SUMS)
  compose config --quiet
}
