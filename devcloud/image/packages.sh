#!/usr/bin/env bash
# The packages every devcloud host has, in four parts of similar size:
#   apt       the apt packages from Ubuntu's archive
#   gcloud    the Google Cloud CLI, from its package repository
#   tools     the GitHub CLI, Tailscale, the Docker CLI and Node LTS from their
#             package repositories, and the tools installed from their releases
#             (uv, hcloud)
#   chromium  the web plugin's headless Chromium, with the libraries it links
# Run as root on Ubuntu 24.04 (x86_64 or arm64). With no argument it runs every
# part, in order: setup.sh does, first. With parts named it runs those:
# image/Dockerfile runs one per layer, so that a build cache's layers are
# pulled side by side; their cache key is this file alone. Each run ends with
# apt's lists and caches removed.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo "run as root" >&2; exit 1; }

part_apt() {
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg git git-lfs build-essential python3 python3-venv jq ripgrep tmux mosh zsh \
    unzip xz-utils tzdata locales procps iproute2 iputils-ping openssh-client less file sudo perl xxd nftables \
    poppler-utils
  sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
  locale-gen
}

part_gcloud() {
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor --yes -o /etc/apt/keyrings/cloud.google.gpg
  echo "deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list
  apt-get update
  apt-get install -y --no-install-recommends google-cloud-cli
}

part_tools() {
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli.gpg
  echo "deb [arch=$arch signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$arch signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" \
    > /etc/apt/sources.list.d/docker.list
  # NodeSource's setup adds its repository and runs apt-get update.
  curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
  apt-get install -y --no-install-recommends gh tailscale docker-ce-cli nodejs

  curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL=/usr/local/bin sh
  curl -fsSL "https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-$arch.tar.gz" \
    | tar -xz -C /usr/local/bin hcloud
}

# The web plugin's renderer (its clipper's findChrome; the boot names it in
# WEB_CHROME): Playwright's Chrome Headless Shell, the build the Macs run,
# pinned by playwright-core's version (1.64.1: chromium_headless_shell-1248),
# with the libraries it links and nothing of a desktop. Node comes from part
# tools. Its sandbox needs user namespaces, which Ubuntu 24.04 grants an
# unprivileged program only through an AppArmor profile naming it, as Ubuntu's
# own does for Google Chrome's: written here, loaded now where AppArmor runs (a
# VM's setup) and at every boot by apparmor.service. A container's runtime
# decides instead (Docker's default seccomp profile refuses them).
part_chromium() {
  apt-get update
  # The libraries the binary links (readelf's NEEDED; the x86_64 build adds atk-bridge).
  apt-get install -y --no-install-recommends libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 \
    libdbus-1-3 libgbm1 libglib2.0-0t64 libnspr4 libnss3 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxkbcommon0 libxrandr2
  PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright npx --yes playwright-core@1.64.1 install --no-progress chromium-headless-shell
  local shell
  shell="$(ls -d /opt/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell | sort -V | tail -n 1)"
  ln -sfn "$shell" /usr/local/bin/chrome-headless-shell
  chrome-headless-shell --version
  install -d -m 0755 /etc/apparmor.d
  cat > /etc/apparmor.d/devcloud-chrome-headless-shell <<PROFILE
abi <abi/4.0>,
include <tunables/global>

profile devcloud-chrome-headless-shell $shell flags=(unconfined) {
  userns,
}
PROFILE
  if command -v apparmor_parser >/dev/null && [[ -d /sys/kernel/security/apparmor ]]; then
    apparmor_parser -r /etc/apparmor.d/devcloud-chrome-headless-shell
  fi
}

parts=("$@")
[[ ${#parts[@]} -gt 0 ]] || parts=(apt gcloud tools chromium)
for part in "${parts[@]}"; do
  case "$part" in apt | gcloud | tools | chromium) ;; *) echo "no part $part (apt, gcloud, tools, chromium)" >&2; exit 2 ;; esac
done

arch="$(dpkg --print-architecture)"
export DEBIAN_FRONTEND=noninteractive
for part in "${parts[@]}"; do "part_$part"; done

apt-get clean
rm -rf /var/lib/apt/lists/* /root/.cache /root/.npm
