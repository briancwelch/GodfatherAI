#!/usr/bin/env bash
# Guided first install. Run from the verified, extracted coordinator release.
set -Eeuo pipefail
umask 077
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ $(uname -s) = Linux && $(uname -m) = x86_64 ]] || { echo 'Use a Linux AMD64 Docker host.' >&2; exit 1; }
command -v docker >/dev/null || { echo 'Install Docker Engine with Docker Compose on this host first.' >&2; exit 1; }
docker compose version >/dev/null
docker info >/dev/null
(cd -- "$release_dir" && sha256sum --check --quiet SHA256SUMS)
[[ -t 0 ]] || { echo 'Run setup in an interactive terminal.' >&2; exit 1; }
echo 'The Godfather coordinator setup'
echo 'Your hostname must already point to this server. HTTPS ports 80/443 must be reachable.'
read -r -p 'Command Center hostname (for example ai.example.com): ' hostname
[[ "$hostname" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$hostname" = *.* && "$hostname" != *..* ]] || { echo 'Enter a hostname only, without a URL, spaces or port.' >&2; exit 1; }
read -r -p 'Your founder Google email: ' founder
[[ "$founder" =~ ^[a-zA-Z0-9._+%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]] || { echo 'Enter one valid Google email.' >&2; exit 1; }
echo "In your Google web OAuth client, add this authorized redirect URI:"
echo "https://$hostname/api/auth/callback"
read -r -p 'Google OAuth client ID: ' client_id
[[ "$client_id" =~ ^[a-zA-Z0-9._-]+\.apps\.googleusercontent\.com$ ]] || { echo 'Enter the Google web OAuth client ID.' >&2; exit 1; }
read -r -s -p 'Google OAuth client secret (hidden): ' client_secret
echo
[[ "$client_secret" =~ ^[a-zA-Z0-9_-]{10,}$ ]] || { echo 'Enter the Google OAuth client secret.' >&2; exit 1; }
read -r -p 'Installation data folder [/opt/the-godfather]: ' install_root
install_root=${install_root:-/opt/the-godfather}
[[ "$install_root" = /* && "$install_root" != / && "$install_root" != *$'\n'* ]] || { echo 'Choose an absolute data folder.' >&2; exit 1; }
mkdir -p -- "$install_root"
install_root=$(cd -- "$install_root" && pwd -P)
env_file="$install_root/production.env"
[[ ! -e "$env_file" && ! -e "$install_root/state/current" ]] || { echo 'An installation already exists. Use the documented upgrade command.' >&2; exit 1; }
db_secret=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
proxy_secret=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
vault_secret=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
# noclobber prevents a concurrent setup from replacing credentials.
(set -o noclobber; cat > "$env_file" <<EOF
POSTGRES_PASSWORD=$db_secret
ACME_EMAIL=$founder
GODFATHER_WEB_ORIGIN=https://$hostname
GODFATHER_APP_HOST=$hostname
GODFATHER_PUBLIC_HOSTS=$hostname
GODFATHER_PROXY_TOKEN=$proxy_secret
GODFATHER_PROVIDER_VAULT_KEY=$vault_secret
GODFATHER_GOOGLE_BOOTSTRAP_EMAIL=$founder
GODFATHER_GOOGLE_CLIENT_ID=$client_id
GODFATHER_GOOGLE_CLIENT_SECRET=$client_secret
EOF
)
unset client_secret db_secret proxy_secret vault_secret
chmod 600 "$env_file"
echo "Installing at https://$hostname. Persistent settings: $env_file"
GODFATHER_ENV_FILE="$env_file" GODFATHER_STATE_DIR="$install_root/state" \
  bash "$release_dir/scripts/install.sh" install
echo "Open https://$hostname and sign in with your founder Google account."
echo 'Then invite contributors. Each worker only needs this Command Center address.'
