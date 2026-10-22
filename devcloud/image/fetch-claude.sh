#!/usr/bin/env bash
# Cache the native Linux release, not an npm installation. This is its own
# Docker layer, keyed only on this script; setup.sh consumes it without network.
# Release paths and checksum schema: https://claude.ai/install.sh and
# https://code.claude.com/docs/en/setup#binary-integrity-and-code-signing
# With no Docker cache (VM bake/adopt), setup.sh runs this after packages.sh.
set -euo pipefail

case "$(uname -m)" in
  x86_64|amd64) platform=linux-x64 ;;
  aarch64|arm64) platform=linux-arm64 ;;
  *) echo "unsupported Claude Code architecture: $(uname -m)" >&2; exit 1 ;;
esac
base="${DEVCLOUD_CLAUDE_RELEASE_URL:-https://downloads.claude.ai/claude-code-releases}"
destination="${1:-/usr/local/lib/claude-code}"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
fetch() { curl -fsSL --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 180 "$@"; }

version="$(fetch "$base/latest")"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.-]+)?$ ]] || {
  echo "Claude Code release returned an invalid version" >&2; exit 1;
}
fetch "$base/$version/manifest.json" -o "$scratch/manifest.json"
checksum="$(jq -r --arg platform "$platform" '.platforms[$platform].checksum // empty' "$scratch/manifest.json")"
[[ "$checksum" =~ ^[a-f0-9]{64}$ ]] || {
  echo "Claude Code manifest has no valid checksum for $platform" >&2; exit 1;
}
fetch "$base/$version/$platform/claude" -o "$scratch/claude"
printf '%s  %s\n' "$checksum" "$scratch/claude" | sha256sum -c - || {
  echo "Claude Code checksum verification failed" >&2; exit 1;
}
# Publish only after validation; no failed download becomes an executable.
install -d -m 0755 "$destination"
install -m 0755 "$scratch/claude" "$destination/claude"
printf '%s\n' "$version" > "$destination/version"
chmod 0644 "$destination/version"
echo "cached Claude Code $version ($platform)"
