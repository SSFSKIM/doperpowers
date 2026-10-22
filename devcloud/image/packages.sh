#!/usr/bin/env bash
# The packages every devcloud host has, in three parts of similar size:
#   apt     the apt packages from Ubuntu's archive
#   gcloud  the Google Cloud CLI, from its package repository
#   tools   the GitHub CLI, Tailscale, the Docker CLI and Node LTS from their
#           package repositories, and the tools installed from their releases
#           (uv, hcloud)
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
    unzip xz-utils tzdata locales procps iproute2 iputils-ping openssh-client less file sudo perl xxd nftables
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

parts=("$@")
[[ ${#parts[@]} -gt 0 ]] || parts=(apt gcloud tools)
for part in "${parts[@]}"; do
  case "$part" in apt | gcloud | tools) ;; *) echo "no part $part (apt, gcloud, tools)" >&2; exit 2 ;; esac
done

arch="$(dpkg --print-architecture)"
export DEBIAN_FRONTEND=noninteractive
for part in "${parts[@]}"; do "part_$part"; done

apt-get clean
rm -rf /var/lib/apt/lists/* /root/.cache
