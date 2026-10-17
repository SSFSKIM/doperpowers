#!/usr/bin/env bash
# The quickest real check of a doperpowers environment: the tools are there, and
# the repository's fast whole-repo checks pass (part of ci-kit's repo-checks gate).
set -euo pipefail

for tool in git python3 node npm jq tmux zsh shellcheck bun; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done
bash tests/version-bump/test-bump-version.sh
bash tests/codex/test-marketplace-manifest.sh
bash tests/skill-links/test-cross-doc-refs.sh
