# Droplet server preparation — 2026-10-20

Server preparation is complete. The Godfather was not deployed. This work does not
complete Phase 10 deployment acceptance and does not authorize the next step.

## Scope and access

The user explicitly authorized Docker Engine/Compose installation, necessary Docker
service configuration, and an initial directory structure on root@137.184.227.74.
SSH used D:\Applications\PuTTY\plink.exe with -batch, preserving PuTTY host-key
verification. No password, key, or private application credential was requested,
printed, transferred, or configured. This validates connectivity with the existing
PuTTY trust/authentication configuration; no independent host fingerprint check was
performed in this task.

The local default process launcher failed before execution with helper_unknown_error.
The approved elevated process launcher worked. This was a local tooling issue.

## Observed server and initial state

- Ubuntu 24.04.5 LTS (noble), x86_64/amd64, kernel 6.8.0-147-generic.
- 2 CPUs; 3915 MiB memory; no swap. Root filesystem 116 GiB, approximately
  114 GiB available before installation (the advertised disk is 120 GB).
- SSH authenticated as uid=0(root). Server uptime was about two minutes at first check.
- Docker Engine, Compose, Docker/containerd service units, conflicting distribution
  packages, Docker apt source files, /var/lib/docker, /var/lib/containerd, and
  /opt/the-godfather were absent at preflight.
- ca-certificates, curl and iptables were already installed; no prerequisite packages
  needed to be added or upgraded.

## Installation performed

Followed Docker's official Ubuntu apt repository method:
https://docs.docker.com/engine/install/ubuntu/

Added /etc/apt/keyrings/docker.asc (readable public signing key) and
/etc/apt/sources.list.d/docker.sources (noble/stable/amd64,
https://download.docker.com/linux/ubuntu, Signed-By the above key).
Both apt metadata updates succeeded, including the signed Docker repository.

Exactly five packages were newly installed; zero upgraded and zero removed:

| Package               | Exact installed apt version   |
| --------------------- | ----------------------------- |
| docker-ce             | 5:29.9.1-1~ubuntu.24.04~noble |
| docker-ce-cli         | 5:29.9.1-1~ubuntu.24.04~noble |
| containerd.io         | 2.4.2-2~ubuntu.24.04~noble    |
| docker-buildx-plugin  | 0.38.0-1~ubuntu.24.04~noble   |
| docker-compose-plugin | 5.6.0-1~ubuntu.24.04~noble    |

Apt reported 91.3 MB downloaded and 362 MB additional installed disk use. Installation
was noninteractive, used --no-remove and --no-install-recommends, and was pinned to
the reviewed candidate versions. NEEDRESTART_MODE=l avoided unrelated service
restarts. Apt reported no services or sessions needing restart and an up-to-date kernel.
The package scripts enabled Docker, Docker's socket, and containerd. Explicitly ran
systemctl enable --now docker.service. Docker uses its standard package configuration;
no daemon override, user/group membership grant, or TCP API listener was added.

## Verification results

Verified at 2026-10-20 17:42:17 UTC (10:42:17 America/Los_Angeles):

- docker version: client and server both 29.9.1, API 1.56, linux/amd64.
- docker compose version: v5.6.0.
- docker buildx version: v0.38.0.
- Runtime bundled versions: containerd v2.4.2, runc 1.5.2, docker-init 0.19.0.
- Docker: enabled, active/running, Result=success, NRestarts=0.
- containerd: enabled, active/running.
- docker info succeeded: overlayfs storage, systemd cgroups v2, AppArmor/seccomp,
  standard iptables firewall backend, local Unix socket /run/docker.sock.
- docker ps -a: zero containers. docker image ls: zero images.
  docker volume ls: zero volumes. No image was pulled and no container was run.
- TCP socket inspection showed only SSH on port 22 and loopback DNS resolver sockets;
  no application ports or Docker TCP API listener.
- /var/run/reboot-required absent; no reboot performed or required by the package check.

## Directories created

All directories are root:root and contain no files:

| Directory                        | Mode | Purpose                             |
| -------------------------------- | ---- | ----------------------------------- |
| /opt/the-godfather               | 0755 | Deployment base                     |
| /opt/the-godfather/incoming      | 0750 | Future authorized archive transfers |
| /opt/the-godfather/releases      | 0750 | Future immutable extracted releases |
| /opt/the-godfather/state         | 0700 | Private deployment state            |
| /opt/the-godfather/state/backups | 0700 | Future private backup storage       |

Used the user's /opt/the-godfather path. The earlier production-release guide uses
/opt/godfather as an example; future separately authorized deployment commands must
use the new base consistently. No symlink, production.env, secret, release pointer,
release content, backup task, or application data was created.

## Issues and boundaries

No authentication or package installation failure occurred. The first detailed
preflight stopped because systemctl list-unit-files returned nonzero when no Docker
units existed. Its read-only command was rerun with the expected absence tolerated;
all remaining checks passed. No installation had begun at that point.

During package installation PowerShell formatted a blank native stderr line as a
NativeCommandError record. Plink/the remote script exited 0, all five packages were
configured, and service/version checks passed; this was not an installation failure.

Docker's startup journal contained informational failed cleanup attempts for absent
IPv4/IPv6 nftables docker-bridges tables. The daemon subsequently initialized
successfully using the iptables backend. No corrective networking change was made.
No firewall administration command was run and no host/cloud firewall policy was
edited. Docker performed its own standard networking initialization when started;
this report does not claim the firewall ruleset remained byte-for-byte unchanged.

PostgreSQL, Redis, Node.js and Python were not installed or upgraded. Ubuntu already
has python3 and python3-minimal 3.12.3-0ubuntu2.1; those were left in place. No existing
Docker data/services were removed. No release artifacts or application containers
were transferred/started. DNS, Google OAuth and Tailscale were untouched. No account,
SSH policy, cloud resource, public application listener, or firewall policy was configured.
No Git commit or push was performed; this is a bounded server-preparation step,
not completion of the deployment phase.

Only this local report and local command/log evidence were written. No application
source or release artifact was modified. Runtime and service checks above are the
validation for this task; no application test suite or deployment acceptance was run.
Stop here. The next step requires separate explicit deployment authorization.

## Exact SSH commands and scripts executed

Initial SSH inspection (executed directly from PowerShell):

```powershell
& 'D:\Applications\PuTTY\plink.exe' -batch -ssh root@137.184.227.74 'set -eu; id; cat /etc/os-release; uname -m; uptime; command -v docker || true; command -v docker-compose || true; dpkg-query -W -f=''${binary:Package} ${Status} ${Version}\n'' docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker.io docker-compose docker-compose-v2 podman-docker containerd runc 2>/dev/null || true; systemctl is-active docker || true; ls -ld /opt/the-godfather /var/lib/docker /var/lib/containerd 2>/dev/null || true'
```

Subsequent scripts below were saved locally with LF line endings and UTF-8 without
BOM. Each was executed using this PowerShell invocation, with SCRIPT replaced by
its filename. Output was saved with Tee-Object to the corresponding local .log:

```powershell
& 'D:\Applications\PuTTY\plink.exe' -batch -ssh root@137.184.227.74 -m 'D:\Projects\Godfather AI\.cache\server-preparation-2026-10-20\SCRIPT'
```

Evidence directory: `.cache/server-preparation-2026-10-20/` in the development
checkout. The initial 01-preflight.log preserves the stopped inspection;
01-preflight-rerun.log preserves the successful rerun. The original script's
systemctl list-unit-files line had no `|| true`; that is the only change before rerun.
The installed packages and full command outputs are preserved in 02/03/04 logs.

### 01-preflight.sh

```sh
set -eu
[ "$(id -u)" -eq 0 ]
. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ]
printf '\n--- Hardware ---\n'
nproc
free -m
df -h / /opt
printf '\n--- Installed relevant packages ---\n'
dpkg-query -W -f='${binary:Package} ${db:Status-Abbrev} ${Version}\n' 2>/dev/null | awk '$1 ~ /^(docker|containerd|runc|podman-docker|ca-certificates|curl|iptables)/ {print}'
printf '\n--- Existing service units ---\n'
systemctl list-unit-files docker.service docker.socket containerd.service --no-pager || true
printf '\n--- Existing Docker repository files ---\n'
find /etc/apt/sources.list.d -maxdepth 1 -iname '*docker*' -print
printf '\n--- Existing directory metadata ---\n'
for path in /opt/the-godfather /var/lib/docker /var/lib/containerd; do
  if [ -e "$path" ] || [ -L "$path" ]; then ls -ld "$path"; fi
done
printf '\n--- Conflicting-package safety gate ---\n'
for pkg in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
  status=$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null || true)
  if [ "$status" = 'install ok installed' ]; then
    printf 'STOP: conflicting package is installed: %s\n' "$pkg" >&2
    exit 1
  fi
done
```

### 02-repository-and-install-plan.sh

```sh
set -eu
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ]
[ ! -e /etc/apt/sources.list.d/docker.sources ]
[ ! -e /etc/apt/keyrings/docker.asc ]
command -v curl
command -v update-ca-certificates
apt-get update -o APT::Update::Error-Mode=any
install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update -o APT::Update::Error-Mode=any
apt-cache policy docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
apt-get --simulate --no-remove --no-install-recommends install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 03-install-docker.sh

```sh
set -eu
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
apt-get install -y --no-remove --no-install-recommends \
  docker-ce=5:29.9.1-1~ubuntu.24.04~noble \
  docker-ce-cli=5:29.9.1-1~ubuntu.24.04~noble \
  containerd.io=2.4.2-2~ubuntu.24.04~noble \
  docker-buildx-plugin=0.38.0-1~ubuntu.24.04~noble \
  docker-compose-plugin=5.6.0-1~ubuntu.24.04~noble
systemctl enable --now docker.service
systemctl is-enabled docker.service
systemctl is-active docker.service
```

### 04-verify-and-create-directories.sh

```sh
set -eu
printf '\n--- UTC verification time ---\n'
date -u +%Y-%m-%dT%H:%M:%SZ
printf '\n--- Docker version ---\n'
docker version
printf '\n--- Compose and Buildx versions ---\n'
docker compose version
docker buildx version
printf '\n--- Service health ---\n'
systemctl is-enabled docker.service
systemctl is-active docker.service
systemctl status docker.service containerd.service --no-pager --full
systemctl show docker.service -p ActiveState -p SubState -p UnitFileState -p Result -p NRestarts
printf '\n--- Docker info ---\n'
docker info
printf '\n--- Containers, images, volumes ---\n'
docker ps -a
docker image ls
docker volume ls
[ -z "$(docker ps -aq)" ]
[ -z "$(docker image ls -q)" ]
printf '\n--- Create deployment directories ---\n'
for path in /opt/the-godfather /opt/the-godfather/incoming /opt/the-godfather/releases /opt/the-godfather/state /opt/the-godfather/state/backups; do
  [ ! -e "$path" ] && [ ! -L "$path" ]
done
install -d -o root -g root -m 0755 /opt/the-godfather
install -d -o root -g root -m 0750 /opt/the-godfather/incoming /opt/the-godfather/releases
install -d -o root -g root -m 0700 /opt/the-godfather/state /opt/the-godfather/state/backups
find /opt/the-godfather -maxdepth 2 -printf '%M %u:%g %p\n'
[ -z "$(find /opt/the-godfather -type f -print -quit)" ]
printf '\n--- Installed package versions ---\n'
dpkg-query -W -f='${binary:Package} ${Status} ${Version}\n' docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
printf '\n--- Native application packages (inspection only) ---\n'
dpkg-query -W -f='${binary:Package} ${db:Status-Abbrev} ${Version}\n' 2>/dev/null | awk '$1 ~ /^(postgresql|redis-server|nodejs|python3$|python3-minimal$)/ {print}'
printf '\n--- Listening TCP sockets ---\n'
ss -lntp
printf '\n--- Reboot requirement ---\n'
if [ -e /var/run/reboot-required ]; then cat /var/run/reboot-required; else printf 'No reboot required.\n'; fi
```
