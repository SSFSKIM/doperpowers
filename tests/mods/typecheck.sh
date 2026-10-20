#!/usr/bin/env bash
# EXPERIMENT: does a headless load lay the type roots on CI?
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
log="$(mktemp)"
args=()
for p in "" sminos to-human devcloud; do args+=(--plugin-dir "$root/$p"); done
cd "$(mktemp -d)"
CLAUDE_CODE_PLUGIN_DIR_WATCH=1 ANTHROPIC_API_KEY=unused timeout 120 \
  claude -p --no-session-persistence --debug-file "$log" "${args[@]}" "hello" ; echo "exit=$?"
sleep 5
grep -E "type root|plugin-dir watch|hooks module" "$log" | head -40
echo "== log tail"; tail -20 "$log"
for p in "" sminos to-human devcloud; do echo "== $p"; ls -la "$root/$p/.claude-plugin/types" 2>&1; done
