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
# a cwd carrying JSON escapes is left to `record` to decide. The payload's cwd
# is where the shell is now, and a session's project is its launch
# directory's, so the engine's project directory ($CLAUDE_PROJECT_DIR) is
# looked at too: either admits. On a machine enrolled at a desk hub every
# directory is a project (a repository no .smns claims is its remote's
# project, and a directory neither claims is in the machine's own), so the
# enrollment's file admits them all; it is only looked for, never read,
# and which project is `record`'s to decide. So does the session's join
# override (`sminos join`), which
# puts a session launched in no repository into a project.
home=${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}
enrolled=$home/daemon/hub.json
in_project() { # dir — whether a .smns or .git lies above it (a dir it cannot judge: yes)
  local d=$1
  [[ $d == /* && $d != *\\* ]] || return 0
  until [[ -e $d/.smns || -e $d/.git ]]; do
    [[ -z $d ]] && return 1
    d=${d%/*}
  done
}
cwd=${input#*\"cwd\":}
if [[ ! -e $enrolled && $cwd != "$input" ]]; then
  cwd=${cwd#"${cwd%%[![:space:]]*}"}
  cwd=${cwd#\"}
  cwd=${cwd%%\"*}
  sid=${input#*\"session_id\":}
  sid=${sid#"${sid%%[![:space:]]*}"}
  sid=${sid#\"}
  sid=${sid%%\"*}
  in_project "$cwd" || { [[ -n ${CLAUDE_PROJECT_DIR:-} ]] && in_project "$CLAUDE_PROJECT_DIR"; } \
    || { [[ $sid =~ ^[0-9a-fA-F-]+$ ]] && [[ -e $home/sessions/$sid.json ]]; } || exit 0
fi

root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
printf '%s' "$input" | "$root/skills/sminos/scripts/sminos" record >/dev/null 2>&1
exit 0
