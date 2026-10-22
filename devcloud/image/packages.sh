#!/usr/bin/env bash
# The packages every devcloud host has: the apt packages, the package
# repositories (GitHub CLI, Google Cloud CLI, Tailscale, Docker, Node LTS) and
# the tools installed from their releases (uv, hcloud). Run as root on Ubuntu
# 24.04 (x86_64 or arm64). It takes no input, so image/Dockerfile runs it as a
# layer of its own, whose cache key is this file alone; setup.sh runs it
# everywhere else, first.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo "run as root" >&2; exit 1; }

arch="$(dpkg --print-architecture)"
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg git git-lfs build-essential python3 python3-venv jq ripgrep tmux mosh zsh \
  unzip xz-utils tzdata locales procps iproute2 iputils-ping openssh-client less file sudo perl xxd nftables
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen

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

apt-get clean
rm -rf /var/lib/apt/lists/* /root/.cache
