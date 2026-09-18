#!/usr/bin/env bash
# MessageDisplay hook for the `to-human` output style.
#
# The engine flushes an assistant message in batches of whole lines while it
# streams and displays what this hook returns in place of each batch; the
# stored message and what the model reads are untouched. Marks are drawn as
# headers and the working record between them dims, so the report takes shape
# as it arrives instead of only when the message ends and the `to-human` mod
# folds it.
#
# The engine runs this once per flush, at most ten times a second per message,
# and stops scheduling flushes while three are in flight — so a slow answer
# costs coarser batches, never a backlog. It still runs in every session,
# including the ones that never mark anything, so the path that has nothing to
# do returns without spawning a process: the marks carry no character JSON
# escaping, so the raw payload answers it, and the state directory exists only
# while some message has a mark open.
set -uo pipefail

dir="${TMPDIR:-/tmp}/doperpowers-to-human"

# `read` rather than `$(cat)`: a builtin and no subshell, so the path that has
# nothing to do runs in this process alone. The payload is one line of JSON,
# which holds no NUL, so the delimiter never matches and this reads to the end.
IFS= read -r -d '' input
[[ -n $input ]] || exit 0

case $input in
  *'<to-human>'* | *'<essential>'* | *'<need-input>'*) ;;
  *)
    shopt -s nullglob
    pending=("$dir"/*)
    ((${#pending[@]})) || exit 0
    ;;
esac

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The sentinel keeps the trailing newlines a command substitution would strip.
payload=$(
  printf '%s' "$input" | jq -j '.message_id, "\n", (.final | tostring), "\n", .delta'
  printf 'X'
) || exit 0
payload=${payload%X}
message_id=${payload%%$'\n'*}
payload=${payload#*$'\n'}
final=${payload%%$'\n'*}
delta=${payload#*$'\n'}
[[ -n $message_id ]] || exit 0

# Past the pre-filter, this may still be a message of another session that has
# nothing marked: it opens no mark here and none is open from an earlier flush.
state="$dir/$message_id"
if [[ ! -f $state ]]; then
  case $delta in
    *'<to-human>'* | *'<essential>'* | *'<need-input>'*) mkdir -p "$dir" || exit 0 ;;
    *) exit 0 ;;
  esac
fi

out=$(
  printf '%s' "$delta" | awk -v statefile="$state" -f "$here/to-human-stream.awk"
  printf 'X'
) || exit 0
out=${out%X}

if [[ $final == true ]]; then
  rm -f "$state"
  # Empty once the last message streaming is done, which is what the next
  # session's pre-filter reads. Flushes of a message the engine abandoned are
  # what keeps it from emptying, so prune those when it does not.
  rmdir "$dir" 2>/dev/null || find "$dir" -type f -mmin +720 -delete 2>/dev/null
fi

printf '%s' "$out" | jq -Rs '{ hookSpecificOutput: { hookEventName: "MessageDisplay", displayContent: . } }'
