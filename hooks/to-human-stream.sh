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
# A message with no mark in it returns nothing and displays as it was, which
# is every session that does not use the output style.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dir="${TMPDIR:-/tmp}/doperpowers-to-human"

input=$(cat) || exit 0

meta=$(printf '%s' "$input" | jq -r '[.message_id, (.final | tostring)] | @tsv') || exit 0
message_id=${meta%%$'\t'*}
final=${meta##*$'\t'}
[[ -n $message_id ]] || exit 0

state="$dir/$message_id"

# The cheap path: no mark opened in an earlier flush of this message, and none
# in this one. The tags carry no character JSON escapes, so the raw payload
# answers it without a parse.
if [[ ! -f $state ]]; then
  case $input in
    *'<to-human>'* | *'<essential>'* | *'<need-input>'*) ;;
    *) exit 0 ;;
  esac
  mkdir -p "$dir" || exit 0
fi

# The sentinel keeps the trailing newlines a command substitution would strip.
delta=$(
  printf '%s' "$input" | jq -j '.delta'
  printf 'X'
) || exit 0
delta=${delta%X}

out=$(
  printf '%s' "$delta" | awk -v statefile="$state" -f "$here/to-human-stream.awk"
  printf 'X'
) || exit 0
out=${out%X}

if [[ $final == true ]]; then
  rm -f "$state"
  # Flushes of a message the engine abandoned leave their state behind.
  find "$dir" -type f -mmin +720 -delete 2>/dev/null
fi

printf '%s' "$out" | jq -Rs '{ hookSpecificOutput: { hookEventName: "MessageDisplay", displayContent: . } }'
