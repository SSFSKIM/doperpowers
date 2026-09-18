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
# costs coarser batches, never a backlog. Those three run at once, and the
# message's last flush is dispatched the moment the message ends, while the
# one before it may still be running; the engine applies their answers in
# order but does not run them in order. What a flush draws depends on the
# marks the flushes before it left open, so each one records its index in the
# message's state file when it is done and the next waits for that record
# before reading the file.
#
# This runs in every session, including the ones that never mark anything, so
# the path that has nothing to do stays inside this process: the fields it
# needs sit ahead of the delta in the payload and carry no JSON escaping, so
# expansions read them, and jq is spawned only for a delta that is drawn.
set -uo pipefail

dir="${TMPDIR:-/tmp}/doperpowers-to-human"

# `read` rather than `$(cat)`: a builtin and no subshell. The payload is one
# line of JSON, which holds no NUL, so the delimiter never matches and this
# reads to the end.
IFS= read -r -d '' input
[[ -n $input ]] || exit 0

field() { # <key> <var> → sets var to a scalar field that precedes the delta
  local key="\"$1\":" rest
  rest=${input#*"$key"}
  [[ $rest != "$input" ]] || return 1
  rest=${rest#\"}
  rest=${rest%%[\",\}]*}
  [[ -n $rest ]] && printf -v "$2" '%s' "$rest"
}
message_id='' index='' final=''
field message_id message_id || exit 0
field index index || exit 0
field final final || exit 0
case $message_id in *[!A-Za-z0-9_-]*) exit 0 ;; esac
case $index in *[!0-9]*) exit 0 ;; esac

# The state file: the index of the last flush that finished, whether the
# message has marked anything yet, and the marks left open (innermost last,
# comma-separated), one per line.
state="$dir/$message_id"
seen=0
stack=""
if ((index > 0)); then
  # The flush before this one may still be running. Wait for its record,
  # bounded: a flush the engine cancelled leaves none, and the message must
  # not stall on it.
  for ((i = 0; i < 200; i++)); do
    if { IFS= read -r done_index && IFS= read -r seen && IFS= read -r stack; } <"$state" 2>/dev/null \
      && [[ $done_index != *[!0-9]* && -n $done_index ]] && ((done_index >= index - 1)); then
      break
    fi
    sleep 0.01
  done
fi

if ((seen == 0)); then
  case $input in
    *'<to-human>'* | *'<essential>'* | *'<need-input>'*) ;;
    *)
      # Nothing to draw and nothing pending: leave the record and go.
      if [[ $final == true ]]; then
        [[ -f $state ]] && rm -f "$state"
      else
        [[ -d $dir ]] || mkdir -p "$dir" || exit 0
        printf '%s\n0\n\n' "$index" >"$state"
      fi
      exit 0
      ;;
  esac
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The sentinel keeps the trailing newlines a command substitution would strip.
delta=$(
  printf '%s' "$input" | jq -j '.delta'
  printf 'X'
) || exit 0
delta=${delta%X}

[[ -d $dir ]] || mkdir -p "$dir" || exit 0
if [[ $final == true ]]; then
  # The last flush records nothing; what it leaves is removed below.
  record=""
else
  record="$state"
fi

out=$(
  printf '%s' "$delta" | awk -v flush="$index" -v seen="$seen" -v stack="$stack" -v statefile="$record" -f "$here/to-human-stream.awk"
  printf 'X'
) || exit 0
out=${out%X}

if [[ $final == true ]]; then
  [[ -f $state ]] && rm -f "$state"
  # Flushes of a message the engine abandoned leave their state behind; prune
  # those once they pile up.
  shopt -s nullglob
  left=("$dir"/*)
  ((${#left[@]} > 64)) && find "$dir" -type f -mmin +720 -delete 2>/dev/null
fi

printf '%s' "$out" | jq -Rs '{ hookSpecificOutput: { hookEventName: "MessageDisplay", displayContent: . } }'
