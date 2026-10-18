#!/usr/bin/env bash
# Stop and SessionStart hook: what this session sends its human reaches its
# project's log (docs/doperpowers/specs/2026-10-13-smns-project-log-design.md
# §4). At SessionStart a member is joined and its export position set; at
# Stop the <message> marks and async asks written since the position are
# appended as `message`, `question` and `answered` events. `sminos record`
# does the work; this only hands it the payload.
#
# A logging failure never blocks a turn: every path exits 0, and nothing is
# printed (a SessionStart hook's stdout would reach the model as context).
set -uo pipefail
# derive's headless fork of a session: never a member, never recorded (§5).
[[ -n ${SMNS_INTERNAL:-} ]] && exit 0

# `read` rather than `$(cat)`: one line of JSON holds no NUL, so this reads to the end.
IFS= read -r -d '' input
[[ -n $input ]] || exit 0

# Where there is no project, nothing is recorded: no .smns and no git
# repository above the session's directory. A cheap look before Python starts;
# a cwd carrying JSON escapes is left to `record` to decide. On a machine
# enrolled at a desk hub every directory is a project (a directory nothing
# claims is in the machine's own), so the enrollment's file admits them all;
# it is only looked for, never read.
enrolled=${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}/daemon/hub.json
cwd=${input#*\"cwd\":}
if [[ ! -e $enrolled && $cwd != "$input" ]]; then
  cwd=${cwd#"${cwd%%[![:space:]]*}"}
  cwd=${cwd#\"}
  cwd=${cwd%%\"*}
  if [[ $cwd == /* && $cwd != *\\* ]]; then
    d=$cwd
    until [[ -e $d/.smns || -e $d/.git ]]; do
      [[ -z $d ]] && exit 0
      d=${d%/*}
    done
  fi
fi

root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
printf '%s' "$input" | "$root/skills/sminos/scripts/sminos" record >/dev/null 2>&1
exit 0
