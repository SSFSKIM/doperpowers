#!/usr/bin/env bash
# to-human-stream.sh (MessageDisplay) draws the output style's marks while an
# assistant message streams: a mark becomes a header in its own color, the
# working record between marks dims, and a message with no mark at all is left
# for the engine to draw as it was. The engine flushes whole lines at a time
# and runs up to three flushes of a message at once, so the marks left open
# carry from one flush to the next in a state file that each flush waits on
# in turn; the hook keeps that under TMPDIR, which this suite points at a
# directory of its own.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/to-human-stream.sh"
FAILURES=0
TMPDIR="$(mktemp -d)"; export TMPDIR
trap 'rm -rf "$TMPDIR"' EXIT
state_dir="$TMPDIR/doperpowers-to-human"

ESC=$(printf '\033')
CYAN="${ESC}[1;36m"
YELLOW="${ESC}[1;33m"
DIM="${ESC}[2m"
OFF="${ESC}[0m"

fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }

flush() { # <message-id> <index> <final> <delta> → the text the hook asks to display
  local payload
  payload=$(jq -nc --arg id "$1" --argjson index "$2" --argjson final "$3" --arg delta "$4" \
    '{ session_id: "s", hook_event_name: "MessageDisplay", turn_id: "t", message_id: $id, index: $index, final: $final, delta: $delta }')
  printf '%s' "$payload" | "$HOOK" | jq -r 'if . == null then "" else .hookSpecificOutput.displayContent end'
}

echo "a message with no mark:"
out=$(flush m0 0 false "Just a reply.
")
if [ -z "$out" ]; then pass "the hook returns nothing, so the engine draws its own"; else fail "returned: $(printf '%q' "$out")"; fi
if [ "$(cat "$state_dir/m0")" = "$(printf '0\n0\n')" ]; then pass "and records that the flush is done"; else fail "state after an unmarked flush: $(cat "$state_dir/m0" 2>&1)"; fi
flush m0 1 true "" > /dev/null
if [ ! -e "$state_dir/m0" ]; then pass "the last flush removes the record"; else fail "record left behind after the last flush"; fi

echo "one flush:"
out=$(flush m1 0 false "a note
<to-human>
The report.
")
case $out in
  *"${CYAN}to human${OFF}"*) pass "the mark opens as a header in its color" ;;
  *) fail "no header: $(printf '%q' "$out")" ;;
esac
case $out in
  *"${DIM}a note${OFF}"*) fail "the record before the first mark was dimmed" ;;
  *"a note"*) pass "text before the message's first mark is left alone" ;;
  *) fail "the leading text was dropped: $(printf '%q' "$out")" ;;
esac
case $out in
  *"${DIM}The report."*) fail "the mark's own body was dimmed" ;;
  *"The report."*) pass "the mark's body stays undimmed" ;;
  *) fail "the body was dropped: $(printf '%q' "$out")" ;;
esac

echo "the next flush of the same message:"
out=$(flush m1 1 false "Still the report.
</to-human>
back to notes
")
case $out in
  *"${DIM}back to notes${OFF}"*) pass "the record after the mark closes is dimmed" ;;
  *) fail "record not dimmed: $(printf '%q' "$out")" ;;
esac
case $out in
  *"${DIM}Still the report."*) fail "the open mark did not carry across the flush" ;;
  *"Still the report."*) pass "the mark left open carries to the next flush" ;;
  *) fail "the body was dropped: $(printf '%q' "$out")" ;;
esac
out=$(flush m1 2 true "the tail, no newline")
case $out in
  *"${DIM}the tail, no newline${OFF}"*) pass "the message's last line dims as record once a mark has closed" ;;
  *) fail "tail not dimmed: $(printf '%q' "$out")" ;;
esac

echo "a mark inside another:"
out=$(flush m2 0 false "<to-human>
Outer.
<essential>
Inner.
</essential>
Outer again.
")
case $out in
  *"${YELLOW}essential${OFF}"*) pass "the inner mark opens as its own header" ;;
  *) fail "no inner header: $(printf '%q' "$out")" ;;
esac
inner_then_outer="${YELLOW}essential${OFF}"$'\n\n\n''Inner.'
case $out in
  *"$inner_then_outer"*"${CYAN}to human${OFF}"*) pass "the enclosing mark's header resumes when the inner one closes" ;;
  *) fail "no resumed header: $(printf '%q' "$out")" ;;
esac
case $out in
  *"${DIM}Outer again."*) fail "the enclosing mark's rest was dimmed as record" ;;
  *) pass "the enclosing mark's rest is not record" ;;
esac

echo "state:"
if [ "$(cat "$state_dir/m2")" = "$(printf '0\n1\nto-human\n')" ]; then pass "a message still streaming records its index, that it has marked, and the marks open"
else fail "state after a marked flush: $(cat "$state_dir/m2" 2>&1)"; fi
flush m2 1 true "</to-human>
" > /dev/null
if [ ! -e "$state_dir/m2" ]; then pass "the last flush of a message clears its state"; else fail "state left behind after the final flush"; fi

echo "two flushes at once:"
# The engine dispatches a message's last flush the moment the message ends,
# while the flush before it may still be running. The later one must wait for
# the earlier one's record rather than read stale state: here the earlier one
# is simulated by a record that appears only after the later one has started.
mkdir -p "$state_dir"
printf '0\n1\nto-human\n' > "$state_dir/m3"   # flush 0 done; flush 1 (which closes the mark) still running
out_file="$TMPDIR/m3.out"
( flush m3 2 true "a tail after the close" > "$out_file" ) &
later=$!
sleep 0.2
printf '1\n1\n\n' > "$state_dir/m3"            # flush 1 done: the mark is closed
wait "$later"
out=$(cat "$out_file")
case $out in
  *"${DIM}a tail after the close${OFF}"*) pass "a flush waits for the one before it and reads the marks it left" ;;
  *) fail "the later flush read stale state: $(printf '%q' "$out")" ;;
esac

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "to-human-stream hook: all checks passed"
else
  echo "to-human-stream hook: $FAILURES check(s) failed"
fi
exit "$FAILURES"
