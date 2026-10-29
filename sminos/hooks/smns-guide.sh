#!/usr/bin/env bash
# SessionStart hook: on a machine enrolled at a desk hub (daemon/hub.json, or
# daemon/identity.json once cut over to its endpoint), tell the session who it
# is in the org and how it reaches the org's other sessions
# (docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md §9). What it
# prints joins the session's context; `sminos guide` writes the text and holds
# the gate (not enrolled, an internal fork, no session: nothing). A failure
# prints nothing and never blocks a start: every path exits 0.
set -uo pipefail
[[ -n ${SMNS_INTERNAL:-} ]] && exit 0
# Only an enrolled machine gets guidance: its enrollment file (hub.json, or
# identity.json on a machine cut over to its endpoint, whose hub.json is gone)
# is looked for, never read, so an unenrolled machine starts no Python here.
home=${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}
[[ -e $home/daemon/hub.json || -e $home/daemon/identity.json ]] || exit 0

IFS= read -r -d '' input
[[ -n $input ]] || exit 0

root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
if out=$(printf '%s' "$input" | "$root/skills/sminos/scripts/sminos" guide 2>/dev/null) && [[ -n $out ]]; then
  printf '%s\n' "$out"
fi
exit 0
