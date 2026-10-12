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
ORANGE="${ESC}[1;38;2;215;119;87m"
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

# Unlike flush's command substitution, preserve all newlines and distinguish
# no hook response (the engine draws delta) from an empty replacement.
shown() {
  local payload response
  payload=$(jq -nc --arg id "$1" --argjson index "$2" --argjson final "$3" --arg delta "$4" \
    '{ session_id: "s", hook_event_name: "MessageDisplay", turn_id: "t", message_id: $id, index: $index, final: $final, delta: $delta }')
  response=$(printf '%s' "$payload" | "$HOOK")
  if [[ -z $response ]]; then printf '%s' "$4"
  else printf '%s' "$response" | jq -j '.hookSpecificOutput.displayContent'; fi
}

echo "MAWS draws the channel itself:"
out=$(MAWS_NATIVE_TO_HUMAN=1 flush maws 0 false '<message>The report.</message>')
if [ -z "$out" ]; then pass "native MAWS returns no drawing"; else fail "native drawing: $(printf '%q' "$out")"; fi
if [ ! -e "$state_dir/maws" ]; then pass "native MAWS creates no streaming state"; else fail "native MAWS left streaming state"; fi
out=$(MAWS_NATIVE_TO_HUMAN='' flush empty-env 0 true '<message>The report.</message>')
case $out in
  *"${ORANGE}message${OFF}"*) pass "an empty advertisement keeps today's drawing" ;;
  *) fail "empty advertisement skipped the drawing: $(printf '%q' "$out")" ;;
esac

unset MAWS_NATIVE_TO_HUMAN
echo "a message with no mark:"
out=$(flush m0 0 false "Just a reply.
")
if [ -z "$out" ]; then pass "the hook returns nothing, so the engine draws its own"; else fail "returned: $(printf '%q' "$out")"; fi
if [ "$(head -n 3 "$state_dir/m0")" = "$(printf '0\n0\n')" ]; then pass "and records that the flush is done"; else fail "state after an unmarked flush: $(cat "$state_dir/m0" 2>&1)"; fi
flush m0 1 true "" > /dev/null
if [ ! -e "$state_dir/m0" ]; then pass "the last flush removes the record"; else fail "record left behind after the last flush"; fi

echo "old marks:"
for tag in to-human essential; do
  out=$(flush "legacy-$tag" 0 true "<$tag>Old report.</$tag>"$'\n'"notes")
  expected=$'\n'"${ORANGE}message${OFF}"$'\n\n''Old report.'$'\n'"${DIM}notes${OFF}"
  if [ "$out" = "$expected" ]; then pass "$tag draws as message and closes before the record"
  else fail "$tag alias: $(printf '%q' "$out")"; fi
done

echo "one flush:"
out=$(flush m1 0 false "a note
<message>
The report.
")
case $out in
  *"${ORANGE}message${OFF}"*) pass "the mark opens as a header in its color" ;;
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
</message>
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
out=$(flush m2 0 false "<message>
Outer.
<insight>
Inner.
</insight>
Outer again.
")
case $out in
  *"${YELLOW}insight${OFF}"*) pass "the inner mark opens as its own header" ;;
  *) fail "no inner header: $(printf '%q' "$out")" ;;
esac
inner_then_outer="${YELLOW}insight${OFF}"$'\n\n\n''Inner.'
case $out in
  *"$inner_then_outer"*"${ORANGE}message${OFF}"*) pass "the enclosing mark's header resumes when the inner one closes" ;;
  *) fail "no resumed header: $(printf '%q' "$out")" ;;
esac
case $out in
  *"${DIM}Outer again."*) fail "the enclosing mark's rest was dimmed as record" ;;
  *) pass "the enclosing mark's rest is not record" ;;
esac

echo "a question with choices:"
MAGENTA="${ESC}[1;35m"
out=$(flush m4 0 false "<need-input>
Which backend?
<choice>SQLite</choice>
<choice recommended>Postgres</choice>
</need-input>
")
case $out in
  *"${MAGENTA}need input${OFF}"*) pass "the question opens as a header" ;;
  *) fail "no header: $(printf '%q' "$out")" ;;
esac
case $out in
  *"◇ SQLite"*) pass "a choice draws as a line under its marker" ;;
  *) fail "no choice marker: $(printf '%q' "$out")" ;;
esac
case $out in
  *"◆ Postgres"*) pass "the recommended choice draws under the filled marker" ;;
  *) fail "no recommended marker: $(printf '%q' "$out")" ;;
esac
case $out in
  *"</choice>"* | *"<choice"*) fail "a choice tag was left in the drawing: $(printf '%q' "$out")" ;;
  *) pass "the choice tags are gone" ;;
esac
case $out in
  *"${DIM}Which backend?"* | *"${DIM}◇"*) fail "the question or a choice was dimmed as record" ;;
  *) pass "the question and its choices are not record" ;;
esac
out=$(flush m6 0 true "<need-input>Which? <choice>A</choice> <choice recommended>B</choice></need-input>
")
case $out in
  *"Which? "$'\n'"◇ A"*$'\n'"◆ B"*) pass "choices written on one line each get a line of their own" ;;
  *) fail "inline choices not broken into lines: $(printf '%q' "$out")" ;;
esac
out=$(flush m5 0 true "<message>
<choice>A</choice>
</message>
")
case $out in
  *"<choice>A</choice>"*) pass "a choice outside a need-input mark is text" ;;
  *) fail "a choice outside need-input was drawn as one: $(printf '%q' "$out")" ;;
esac

echo "an insight:"
out=$(flush m7 0 true "Editing the parser.
<insight>
The cache key is the path.
</insight>
")
case $out in
  *"${YELLOW}insight${OFF}"*) pass "the insight opens as a header in its color" ;;
  *) fail "no insight header: $(printf '%q' "$out")" ;;
esac
case $out in
  *"${DIM}The cache key"*) fail "the insight's body was dimmed as record" ;;
  *"The cache key is the path."*) pass "the insight's body stays undimmed" ;;
  *) fail "the insight's body was dropped: $(printf '%q' "$out")" ;;
esac

echo "tags in code:"
sentence=$'The style now asks for three marks: `<message>`, `<need-input>`, `<insight>`.'
out=$(flush vocabulary 0 true "$sentence")
# No replacement also preserves literal text: the engine draws the delta.
if [ -z "$out" ] || [ "$out" = "$sentence" ]; then pass "backticked vocabulary stays literal"
else fail "quoted vocabulary became marks: $(printf '%q' "$out")"; fi
out=$(flush vocabulary-mark 0 true "<message>$sentence</message>")
expected=$'\n'"${ORANGE}message${OFF}"$'\n\n'"$sentence"
if [ "$out" = "$expected" ]; then pass "one real message keeps quoted tags in its body"
else fail "real message with quoted tags: $(printf '%q' "$out")"; fi

for fence in '```' '~~~~'; do
  example="$fence"$'md\n<need-input>Which?\n<choice recommended>A</choice>\n<choice>B</choice>\n</need-input>\n'"$fence"
  out=$(flush "fenced-${#fence}" 0 true "$example")
  if [ -z "$out" ] || [ "$out" = "$example" ]; then pass "$fence keeps the full question example literal"
  else fail "fenced example: $(printf '%q' "$out")"; fi
  out=$(flush "fenced-mark-${#fence}" 0 true "<message>Example:"$'\n'"$example"$'\n''Done.</message>')
  expected=$'\n'"${ORANGE}message${OFF}"$'\n\n''Example:'$'\n'"$example"$'\n''Done.'
  if [ "$out" = "$expected" ]; then pass "a real mark keeps its fenced example"
  else fail "fence inside message: $(printf '%q' "$out")"; fi
done

# A partial backticked tag and its code delimiter are carried, not drawn as a
# header before the closer tells us it is an inline span.
first=$(flush split-code 0 false 'Use `<need-')
second=$(flush split-code 1 false 'input>Example</need-input>` here.'$'\n\n')
third=$(flush split-code 2 true '<message>Real.</message>')
joined="$first$second$third"
case $joined in
  *"${MAGENTA}need input"*) fail "a split quoted tag became a question: $(printf '%q' "$joined")" ;;
  *$'Use `<need-input>Example</need-input>` here.'*"${ORANGE}message${OFF}"*'Real.'*) pass "a backticked tag split across flushes stays literal, and the later mark draws" ;;
  *) fail "split quoted text lost: $(printf '%q' "$joined")" ;;
esac

# The initial fence flush has no mark, so it still has to record code state.
first=$(flush split-fence 0 false $'```md\n')
[[ -n $first ]] || first=$'```md\n'  # no replacement: the engine draws the original
second=$(flush split-fence 1 false $'<need-input>Which?\n<choice>A</choice>\n</need-input>\n')
[[ -n $second ]] || second=$'<need-input>Which?\n<choice>A</choice>\n</need-input>\n'
third=$(flush split-fence 2 true $'```\n<message>Real.</message>')
joined="$first$second$third"
case $joined in
  *"${MAGENTA}need input"* | *'◇ A'*) fail "fence state lost across flushes: $(printf '%q' "$joined")" ;;
  *'<need-input>Which?'*'<choice>A</choice>'*"${ORANGE}message${OFF}"*'Real.'*) pass "a fence opened without marks carries across flushes" ;;
  *) fail "split fenced example lost: $(printf '%q' "$joined")" ;;
esac

out=$(flush code-choice 0 true $'<need-input>Example:\nWrite `<choice>A</choice>` lines.\n```\n<choice>B</choice>\n</need-input>\n```\n<choice recommended>Yes</choice>\n</need-input>')
expected=$'\n'"${MAGENTA}need input${OFF}"$'\n\n''Example:'$'\nWrite `<choice>A</choice>` lines.'$'\n```\n<choice>B</choice>\n</need-input>\n```\n◆ Yes'
if [ "$out" = "$expected" ]; then pass "quoted choice tags and a fenced closer stay inside the real question"
else fail "code inside question: $(printf '%q' "$out")"; fi

for fence in '```' '~~~'; do
  out=$(flush glued-final 0 true '<message>Run:'$'\n'"${fence}sh"$'\nx\n'"$fence"'</message>'$'\n''<need-input>Go?</need-input>')
  expected=$'\n'"${ORANGE}message${OFF}"$'\n\n''Run:'$'\n'"${fence}sh"$'\nx\n'"$fence"$'\n\n'"${MAGENTA}need input${OFF}"$'\n\n''Go?'
  if [ "$out" = "$expected" ]; then pass "$fence closing fence glued to a tag recovers the report"
  else fail "glued fence: $(printf '%q' "$out")"; fi
done
first=$(flush glued-example 0 false $'<message>Example:\n```text\n```</message>\n<need-input>Example only?</need-input>\n')
case $first in
  *"${MAGENTA}need input"*) fail "a speculative glued recovery drew an example as a question: $(printf '%q' "$first")" ;;
  *) pass "a glued fence does not speculate before the strict reading is settled" ;;
esac
second=$(flush glued-example 1 true $'```\nEnd.</message>')
joined="$first$second"
case $joined in
  *"${MAGENTA}need input"*) fail "balanced strict example became a question: $(printf '%q' "$joined")" ;;
  *'<need-input>Example only?</need-input>'*'End.'*) pass "the balanced strict reading keeps the glued example literal" ;;
  *) fail "balanced glued example lost: $(printf '%q' "$joined")" ;;
esac

echo "partial lines do not settle code boundaries:"
first=$(shown partial-opener 0 false $'A ` <need-input>Example</need-input>\n'; printf X); first=${first%X}
first_offset=$(sed -n '4p' "$state_dir/partial-opener")
second=$(shown partial-opener 1 false '```foo'; printf X); second=${second%X}
second_offset=$(sed -n '4p' "$state_dir/partial-opener")
third=$(shown partial-opener 2 true $' ` rest\n'; printf X); third=${third%X}
joined="$first$second$third"
expected=$'A ` <need-input>Example</need-input>\n```foo ` rest\n'
if [[ $joined == "$expected" ]]; then pass "a partial opener never invents a header and preserves the full inline source"
else fail "partial opener drawing: $(printf '%q' "$joined")"; fi
if (( second_offset >= first_offset )); then pass "the emitted source offset never moves backward"
else fail "partial opener moved emitted offset from $first_offset to $second_offset"; fi

# Every two-way split of this source, and a character-at-a-time stream, must
# agree with the final inline reading and keep every newline exactly once.
for ((split = 0; split <= ${#expected}; split++)); do
  first=$(shown "partial-split-$split" 0 false "${expected:0:split}"; printf X); first=${first%X}
  second=$(shown "partial-split-$split" 1 true "${expected:split}"; printf X); second=${second%X}
  if [[ $first$second != "$expected" ]]; then fail "inline source split $split: $(printf '%q' "$first$second")"; break; fi
done
if (( split > ${#expected} )); then pass "every two-way split preserves the finished inline reading"; fi
joined='' previous_offset=0
for ((split = 0; split < ${#expected}; split++)); do
  final=false; (( split == ${#expected} - 1 )) && final=true
  part=$(shown partial-characters "$split" "$final" "${expected:split:1}"; printf X); part=${part%X}
  joined+=$part
  if [[ $final == false ]]; then
    offset=$(sed -n '4p' "$state_dir/partial-characters")
    if (( offset < previous_offset )); then fail "character flush $split moved emitted offset from $previous_offset to $offset"; fi
    previous_offset=$offset
  fi
done
if [[ $joined == "$expected" ]]; then pass "character flushes preserve exact text without speculative headers or duplicate source"
else fail "character flush drawing: $(printf '%q' "$joined")"; fi

echo "JavaScript trim paragraph boundaries:"
blank_lines=($'\t' $'\v' $'\f' $'\r' ' ' $'\302\240' $'\341\232\200'
  $'\342\200\200' $'\342\200\201' $'\342\200\202' $'\342\200\203' $'\342\200\204' $'\342\200\205'
  $'\342\200\206' $'\342\200\207' $'\342\200\210' $'\342\200\211' $'\342\200\212'
  $'\342\200\250' $'\342\200\251' $'\342\200\257' $'\342\201\237' $'\343\200\200' $'\357\273\277')
for ((blank_index = 0; blank_index < ${#blank_lines[@]}; blank_index++)); do
  source=$'stray `\n'"${blank_lines[blank_index]}"$'\nUse `<need-input>Example</need-input>`\n'
  out=$(shown "trim-blank-$blank_index" 0 true "$source"; printf X); out=${out%X}
  if [[ $out == "$source" ]]; then pass "trim whitespace $blank_index keeps the next paragraph's tag inside inline code"
  else fail "trim whitespace $blank_index drawing: $(printf '%q' "$out")"; fi
  out=$(shown "trim-mark-$blank_index" 0 true "<message>$source</message>"; printf X); out=${out%X}
  expected=$'\n'"${ORANGE}message${OFF}"$'\n\n'"$source"
  if [[ $out == "$expected" ]]; then pass "trim whitespace $blank_index survives replacement drawing exactly"
  else fail "trim whitespace $blank_index in message: $(printf '%q' "$out")"; fi
done

echo "JavaScript dot excludes line terminators in fence info:"
info_terminators=($'\r' $'\342\200\250' $'\342\200\251')
for ((info_index = 0; info_index < ${#info_terminators[@]}; info_index++)); do
  source=$'Use `\n<need-input>Example</need-input>\n~~~'"${info_terminators[info_index]}"$'\n x`\n'
  out=$(shown "fence-info-$info_index" 0 true "$source"; printf X); out=${out%X}
  if [[ $out == "$source" ]]; then pass "line terminator $info_index does not make an opening fence"
  else fail "line terminator $info_index fence drawing: $(printf '%q' "$out")"; fi
  out=$(shown "fence-info-mark-$info_index" 0 true "<message>$source</message>"; printf X); out=${out%X}
  expected=$'\n'"${ORANGE}message${OFF}"$'\n\n'"$source"
  if [[ $out == "$expected" ]]; then pass "line terminator $info_index keeps the example literal inside a real message"
  else fail "line terminator $info_index in message: $(printf '%q' "$out")"; fi
done

echo "golden MessageDisplay record consumed by the mod:"
golden_index=0
for specification in '~~~ closed adjacent' '``` closed blank' '``` open blank'; do
  read -r fence close spacing <<< "$specification"
  source=$'<message>Report.</message>\n'"$fence"$'\n'
  golden=$'\n'"${ORANGE}message${OFF}"$'\n\nReport.\n'"${DIM}${fence}${OFF}"$'\n'
  if [[ $spacing == blank ]]; then source+=$'\n'; golden+=$'\n'; fi
  source+=$'<need-input>Example</need-input>\n'
  golden+="${DIM}<need-input>${OFF}${DIM}Example</need-input>${OFF}"$'\n'
  if [[ $close == closed ]]; then
    source+="$fence"$'\n'; golden+="${DIM}${fence}${OFF}"$'\n'
  fi
  out=$(shown "golden-$golden_index" 0 true "$source"; printf X); out=${out%X}
  golden_index=$((golden_index + 1))
  if [[ $out == "$golden" ]]; then pass "$specification draws the exact report and literal dimmed fence fixture"
  else fail "$specification golden drawing: $(printf '%q' "$out")"; fi
done
out=$(shown golden-choices 0 true $'<need-input>Which?\n<choice>Use `main`</choice>\n<choice recommended>`npm test`</choice>\n</need-input>'; printf X); out=${out%X}
expected=$'\n'"${MAGENTA}need input${OFF}"$'\n\nWhich?\n◇ Use `main`\n◆ `npm test`\n'
if [[ $out == "$expected" ]]; then pass "choices ending in code draw the marker fixture consumed by the mod"
else fail "code choices drawing: $(printf '%q' "$out")"; fi

echo "state:"
if [ "$(head -n 3 "$state_dir/m2")" = "$(printf '0\n1\nmessage\n')" ]; then pass "a message still streaming records its index, that it has marked, and the marks open"
else fail "state after a marked flush: $(cat "$state_dir/m2" 2>&1)"; fi
flush m2 1 true "</message>
" > /dev/null
if [ ! -e "$state_dir/m2" ]; then pass "the last flush of a message clears its state"; else fail "state left behind after the final flush"; fi

echo "two flushes at once:"
# The engine dispatches a message's last flush the moment the message ends,
# while the flush before it may still be running. The later one must wait for
# the earlier one's record rather than read stale state: here the earlier one
# is simulated by a record that appears only after the later one has started.
mkdir -p "$state_dir"
printf '0\n1\nmessage\n' > "$state_dir/m3"   # flush 0 done; flush 1 (which closes the mark) still running
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

echo "a source record is published only when complete:"
shim="$TMPDIR/awk-shim"; mkdir -p "$shim"
cat > "$shim/awk" <<'SHIM'
#!/usr/bin/env bash
set -euo pipefail
record=''
for arg; do case $arg in statefile=*) record=${arg#statefile=} ;; esac; done
"$REAL_AWK" "$@"
# Emulate a write paused between the synchronization header and source body.
cp "$record" "$HOLD_AWK_DIR/complete"
head -n 3 "$record" > "$HOLD_AWK_DIR/partial"
cat "$HOLD_AWK_DIR/partial" > "$record"
: > "$HOLD_AWK_DIR/ready"
for ((i = 0; i < 500; i++)); do
  [[ -e $HOLD_AWK_DIR/release ]] && break
  sleep 0.01
done
[[ -e $HOLD_AWK_DIR/release ]]
cp "$HOLD_AWK_DIR/complete" "$record"
SHIM
chmod +x "$shim/awk"
hold="$TMPDIR/awk-hold"; mkdir -p "$hold"
real_awk=$(command -v awk)
PATH="$shim:$PATH" REAL_AWK="$real_awk" HOLD_AWK_DIR="$hold" \
  shown atomic-state 0 false $'A ` <need-input>Example</need-input>\n' > "$TMPDIR/atomic-first" &
writer=$!
for ((i = 0; i < 500; i++)); do
  [[ -e $hold/ready ]] && break
  sleep 0.01
done
if [[ ! -e $hold/ready ]]; then fail "paused state writer never reached the source write"
elif [[ -e $state_dir/atomic-state ]]; then fail "an incomplete record exposed its done index to the next flush"
else pass "an incomplete source record is invisible to the next flush"; fi
shown atomic-state 1 true $'` rest\n' > "$TMPDIR/atomic-second" &
reader=$!
sleep 0.1
: > "$hold/release"
wait "$writer" || fail "paused state writer failed"
wait "$reader" || fail "concurrent state reader failed"
joined=$(cat "$TMPDIR/atomic-first" "$TMPDIR/atomic-second"; printf X); joined=${joined%X}
expected=$'A ` <need-input>Example</need-input>\n` rest\n'
if [[ $joined == "$expected" ]]; then pass "the next flush reads the complete buffered source without dropping text"
else fail "concurrent source drawing: $(printf '%q' "$joined")"; fi
shopt -s nullglob
leftovers=("$state_dir"/.atomic-state-*)
if [[ ! -e $state_dir/atomic-state && ${#leftovers[@]} -eq 0 ]]; then pass "a final flush leaves no message or temporary record"
else fail "records left after final flush: $state_dir/atomic-state ${leftovers[*]:-}"; fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "to-human-stream hook: all checks passed"
else
  echo "to-human-stream hook: $FAILURES check(s) failed"
fi
exit "$FAILURES"
