#!/usr/bin/env bash
# devenv-inputs: application-agents/triaging-feedback/package-lock.json
#
# doperpowers' development environment, on macOS and Ubuntu: the tools its test
# suites run (.github/ci-kit.yml) and the one npm package's dependencies. Safe to
# re-run; installs only what is missing. Claude Code itself is assumed present.
set -euo pipefail

missing=()
for tool in git python3 node npm jq tmux zsh shellcheck; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done

if [ "${#missing[@]}" -gt 0 ]; then
  echo "installing: ${missing[*]}"
  case "$(uname -s)" in
    Darwin)
      packages=("${missing[@]/npm/node}")
      brew install "${packages[@]}"
      ;;
    Linux)
      packages=()
      for tool in "${missing[@]}"; do
        case "$tool" in
          node | npm) packages+=(nodejs npm) ;;
          *) packages+=("$tool") ;;
        esac
      done
      sudo apt-get update -qq
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${packages[@]}"
      ;;
    *)
      echo "unsupported platform: $(uname -s)" >&2
      exit 1
      ;;
  esac
fi

# bun runs the mods' tests; the npm package lands in ~/.local, with no root needed.
if ! command -v bun >/dev/null 2>&1; then
  npm install --global --prefix "$HOME/.local" bun
fi

(cd application-agents/triaging-feedback && npm ci --no-audit --no-fund)
