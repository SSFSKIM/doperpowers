#!/usr/bin/env bash
# SessionStart hook, source `compact`: a compaction ends a long stretch of
# work, so the session's in-charge line (and its name, where sminos may name
# it) is derived again now rather than at the daemon's six-hour spacing
# (docs/doperpowers/specs/2026-11-08-sminos-derive-on-compact-design.md).
# `sminos derive <session> --compacted` does the work, detached: the session
# never waits on it, and nothing is printed (a SessionStart hook's stdout
# would reach the model as context). Every path exits 0.
set -uo pipefail
# derive's headless fork of a session: never a member, never recorded.
[[ -n ${SMNS_INTERNAL:-} ]] && exit 0

# `read` rather than `$(cat)`: one line of JSON holds no NUL, so this reads to the end.
IFS= read -r -d '' input
sid=${input#*\"session_id\":}
[[ $sid != "$input" ]] || exit 0
sid=${sid#"${sid%%[![:space:]]*}"}
sid=${sid#\"}
sid=${sid%%\"*}
[[ $sid =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || exit 0

# What derive says goes where the daemon's derive --all puts it, daemon.log: a
# failed fork's reason is said only on stderr.
home=${SMINOS_HOME:-${DAEMON_HOME:-$HOME/.claude/sminos}}
log=/dev/null
[[ -d $home ]] && log=$home/daemon.log
root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
nohup "$root/skills/sminos/scripts/sminos" derive "$sid" --compacted </dev/null >>"$log" 2>&1 &
exit 0
