#!/usr/bin/env bash
# The devcloud image (Design §2): everything every host has, and never a
# credential, a boot descriptor, a ~/.claude checkout or a sminos enrollment.
# Run as root on Ubuntu 24.04 (x86_64 or arm64), from a devcloud checkout:
#
#   DEVCLOUD_USER=<user> DEVCLOUD_UID=<uid> DEVCLOUD_HOME=<home> devcloud/image/setup.sh
#
# The three inputs are the person's Mac account (the profile's build.env):
# the same home path lets a session started on a Mac resume on a host. A VM
# builder runs this and snapshots; image/Dockerfile runs it as its one step.
set -euo pipefail

: "${DEVCLOUD_USER:?set DEVCLOUD_USER, from the profile build.env}"
: "${DEVCLOUD_UID:?set DEVCLOUD_UID}"
: "${DEVCLOUD_HOME:?set DEVCLOUD_HOME}"
[[ "$DEVCLOUD_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "DEVCLOUD_USER is not a user name" >&2; exit 1; }
[[ "$DEVCLOUD_UID" =~ ^[0-9]+$ && "$DEVCLOUD_UID" -gt 0 ]] || { echo "DEVCLOUD_UID is not a uid above 0" >&2; exit 1; }
[[ "$DEVCLOUD_HOME" == /* ]] || { echo "DEVCLOUD_HOME is not an absolute path" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || { echo "run as root" >&2; exit 1; }

plugin="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
arch="$(dpkg --print-architecture)"
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg git git-lfs build-essential python3 python3-venv jq tmux mosh zsh \
  unzip xz-utils tzdata locales procps iproute2 iputils-ping openssh-client less file
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen

# Package repositories: GitHub CLI, Google Cloud CLI, Tailscale, Docker, Node LTS.
install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli.gpg
echo "deb [arch=$arch signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
  > /etc/apt/sources.list.d/github-cli.list
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor --yes -o /etc/apt/keyrings/cloud.google.gpg
echo "deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
  > /etc/apt/sources.list.d/google-cloud-sdk.list
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$arch signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" \
  > /etc/apt/sources.list.d/docker.list
curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
apt-get install -y --no-install-recommends gh google-cloud-cli tailscale docker-ce-cli nodejs

curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL=/usr/local/bin sh
curl -fsSL "https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-$arch.tar.gz" \
  | tar -xz -C /usr/local/bin hcloud

# The user: the Mac's name, uid and home, zsh as the login shell. Ubuntu's
# image ships an `ubuntu` user at uid 1000, which gives way when it is in the way.
if getent passwd "$DEVCLOUD_UID" >/dev/null && [[ "$(getent passwd "$DEVCLOUD_UID" | cut -d: -f1)" != "$DEVCLOUD_USER" ]]; then
  taken="$(getent passwd "$DEVCLOUD_UID" | cut -d: -f1)"
  [[ "$taken" == ubuntu ]] || { echo "uid $DEVCLOUD_UID is taken by $taken" >&2; exit 1; }
  userdel -r ubuntu 2>/dev/null || userdel ubuntu
fi
if ! getent passwd "$DEVCLOUD_USER" >/dev/null; then
  getent group "$DEVCLOUD_USER" >/dev/null || \
    if getent group "$DEVCLOUD_UID" >/dev/null; then groupadd "$DEVCLOUD_USER"; else groupadd -g "$DEVCLOUD_UID" "$DEVCLOUD_USER"; fi
  install -d -m 0755 "$(dirname "$DEVCLOUD_HOME")"
  useradd --uid "$DEVCLOUD_UID" --gid "$DEVCLOUD_USER" --home-dir "$DEVCLOUD_HOME" --create-home \
    --shell /usr/bin/zsh "$DEVCLOUD_USER"
fi
chsh -s /usr/bin/zsh "$DEVCLOUD_USER"

# Claude Code, the native installer, as the user; on every PATH through a link.
# Its own temporary directory, removed after: the installer leaves a socket behind.
scratch="$(runuser -u "$DEVCLOUD_USER" -- mktemp -d)"
runuser -u "$DEVCLOUD_USER" -- env HOME="$DEVCLOUD_HOME" TMPDIR="$scratch" \
  bash -c 'curl -fsSL https://claude.ai/install.sh | bash'
rm -rf "$scratch"
ln -sfn "$DEVCLOUD_HOME/.local/bin/claude" /usr/local/bin/claude

# devcloud itself: the boot program, the service runner, the CLI.
install -d -m 0755 /usr/local/lib/devcloud /etc/devcloud
cp -R "$plugin/boot/." /usr/local/lib/devcloud/
find /usr/local/lib/devcloud -name __pycache__ -prune -exec rm -rf {} +
chmod -R go-w /usr/local/lib/devcloud
for program in devcloud devcloud-boot devcloud-services; do
  ln -sfn "/usr/local/lib/devcloud/$program" "/usr/local/bin/$program"
done
printf 'DEVCLOUD_USER=%s\nDEVCLOUD_UID=%s\nDEVCLOUD_HOME=%s\n' "$DEVCLOUD_USER" "$DEVCLOUD_UID" "$DEVCLOUD_HOME" \
  > /etc/devcloud/image.env

# /etc/devcloud/env reaches every shell of the user's: every zsh reads
# /etc/zsh/zshenv (login, interactive, and the `zsh -c` of Claude Code's Bash
# tool); bash login shells read /etc/profile.d. Root's shells skip it: the
# file may put the user's directories on PATH.
marker='# devcloud: the host environment'
if ! grep -qF "$marker" /etc/zsh/zshenv 2>/dev/null; then
  cat >> /etc/zsh/zshenv <<'ZSH'

# devcloud: the host environment (/etc/devcloud/env), for every zsh but root's.
if [[ $EUID -ne 0 ]]; then
  [[ ":$PATH:" == *":$HOME/.local/bin:"* ]] || export PATH="$HOME/.local/bin:$PATH"
  if [[ -r /etc/devcloud/env ]]; then set -a; . /etc/devcloud/env; set +a; fi
fi
ZSH
fi
cat > /etc/profile.d/devcloud.sh <<'SH'
# devcloud: the host environment (/etc/devcloud/env), for every login shell but root's.
if [ "$(id -u)" -ne 0 ]; then
  case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH"; export PATH ;; esac
  if [ -r /etc/devcloud/env ]; then set -a; . /etc/devcloud/env; set +a; fi
fi
SH

# Where systemd is PID 1 (a VM or microVM), the boot program runs at every boot.
cat > /etc/systemd/system/devcloud-boot.service <<'UNIT'
[Unit]
Description=devcloud: make this machine a devcloud host (boot steps 1-12)
Wants=network-online.target
After=network-online.target cloud-init.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/devcloud-boot
TimeoutStartSec=45min

[Install]
WantedBy=multi-user.target
UNIT
if command -v systemctl >/dev/null; then systemctl enable devcloud-boot.service; fi

apt-get clean
rm -rf /var/lib/apt/lists/* /root/.cache "$DEVCLOUD_HOME/.cache"

# What the image never carries (acceptance 6): no descriptor, no credential, no checkout, no enrollment.
for path in /etc/devcloud/boot.env /var/lib/devcloud "$DEVCLOUD_HOME/.claude/.git" \
            "$DEVCLOUD_HOME/.config/claude-secrets" "$DEVCLOUD_HOME/.config/gcloud" "$DEVCLOUD_HOME/.config/gh" \
            "$DEVCLOUD_HOME/.claude/sminos/daemon"; do
  if [[ -e "$path" ]]; then echo "the image must not hold $path" >&2; exit 1; fi
done
