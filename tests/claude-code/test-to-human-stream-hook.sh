#!/usr/bin/env bash
# to-human-stream.sh (MessageDisplay) draws the output style's marks while an
# assistant message streams: a mark becomes a header in its own color, the
# working record between marks dims, and a message with no mark at all is left
# for the engine to draw as it was. The engine flushes whole lines at a time,
# so the marks left open carry from one flush to the next in a state file; the
# hook keeps that under TMPDIR, which this suite points at a directory of its
# own.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/to-human-stream.sh"
FAILURES=0
TMPDIR="$(mktemp -d)"; export TMPDIR
trap 'rm -rf "$TMPDIR"' EXIT

ESC=$(printf '\033')
CYAN="$ESC[1;36m"
YELLOW="$ESC[1;33m"
DIM="$ESC[2m"
OFF="$ESC[0m"

fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }

flush() { # <message-id> <final> <delta> → the text the hook asks to display
  local payload
  payload=$(jq -nc --arg id "$1" --argjson final "$2" --arg delta "$3" \
    '{ session_id: "s", hook_event_name: "MessageDisplay", turn_id: "t", message_id: $id, index: 0, final: $final, delta: $delta }')
  printf '%s' "$payload" | "$HOOK" | jq -r 'if . == null then "" else .hookSpecificOutput.displayContent end'
}

echo "a message with no mark:"
out=$(flush m0 true "Just a reply.
")
if [ -z "$out" ]; then pass "the hook returns nothing, so the engine draws its own"; else fail "returned: $(printf '%q' "$out")"; fi

echo "one flush:"
out=$(flush m1 false "a note
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
out=$(flush m1 false "Still the report.
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

echo "a mark inside another:"
out=$(flush m2 false "<to-human>
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
state_dir="$TMPDIR/doperpowers-to-human"
if [ -f "$state_dir/m2" ]; then pass "a message still streaming keeps its state"; else fail "no state file for a message with a mark open"; fi
flush m2 true "</to-human>
" > /dev/null
if [ ! -f "$state_dir/m2" ]; then pass "the last flush of a message clears its state"; else fail "state left behind after the final flush"; fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "to-human-stream hook: all checks passed"
else
  echo "to-human-stream hook: $FAILURES check(s) failed"
fi
exit "$FAILURES"
