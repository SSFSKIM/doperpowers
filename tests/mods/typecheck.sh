#!/usr/bin/env bash
# Typechecks every plugin's function-hook mods and their tests: `tsc` through
# each plugin's hooks/mods/tsconfig.json, against the declarations the engine
# lays in the plugin's .claude-plugin/types/ when it loads the plugin from a
# folder it watches (the API, this build's built-in tools, the MCP tools, and
# each plugin the manifest lists under dependencies). Nothing of them is
# committed: they are the engine's, and they are what the mods run against.
#
# --lay first loads every plugin once, headless, so the installed engine lays
# them, which is what CI does. The load's one request carries a key that
# cannot authenticate, so it fails and spends nothing. Without --lay the
# declarations a session already laid are read: a `claude --plugin-dir <plugin>`
# session lays them as it loads the plugin.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
plugins=(. sminos to-human devcloud)
declarations() { echo "$root/$1/.claude-plugin/types/claude-code/index.d.ts"; }

if [ "${1:-}" = --lay ]; then
  args=()
  for p in "${plugins[@]}"; do args+=(--plugin-dir "$root/$p"); done
  log="$(mktemp)"
  trap 'rm -f "$log"' EXIT
  # The engine lays the roots just after the load, while the session runs, and
  # nothing holds the process for them: on a fast failure it can exit first.
  for attempt in 1 2 3; do
    (cd "$(mktemp -d)" && CLAUDE_CODE_PLUGIN_DIR_WATCH=1 ANTHROPIC_API_KEY=unauthenticated \
      timeout 120 claude -p --no-session-persistence --debug-file "$log" "${args[@]}" "lay the type roots") \
      >/dev/null 2>&1 || true
    missing=0
    for p in "${plugins[@]}"; do [ -f "$(declarations "$p")" ] || missing=1; done
    [ "$missing" = 0 ] && break
    echo "type roots not all laid (attempt $attempt):"
    grep "type root" "$log" || true
  done
fi

fail=0
for p in "${plugins[@]}"; do
  name="${p/#./doperpowers}"
  d="$(declarations "$p")"
  if [ ! -f "$d" ]; then
    echo "FAIL $name: no declarations at ${d#"$root"/} (rerun with --lay, or load the plugin in a session)"
    fail=1
    continue
  fi
  echo "== $name, against $(head -1 "$d" | sed 's#^// ##')"
  npx -y -p typescript@5 tsc -p "$root/$p/hooks/mods/tsconfig.json" || fail=1
done
exit "$fail"
