#!/usr/bin/env bash
# The experimental-context hooks. experimental-context.sh (SessionStart) is
# silent unless the session is in the mode — EXPERIMENTAL_CONTEXT=1 in its
# environment, or a flag file named by its session id — and then prints the
# skill BODY (never the frontmatter) followed by the transcript's live
# <revisit> entries: latest value per key, retired keys dropped, sidechain rows
# and fenced code ignored, each stamped with its date and compactions-ago.
# experimental-context-toggle.sh (UserPromptExpansion) writes and removes the
# flag. Both take the flag directory from CONTEXT_DIR so this suite never
# touches ~/.claude/experimental-context.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/experimental-context.sh"
TOGGLE="$REPO_ROOT/hooks/experimental-context-toggle.sh"
FAILURES=0
CONTEXT_DIR="$(mktemp -d)"; export CONTEXT_DIR
TRANSCRIPT="$(mktemp)"
trap 'rm -rf "$CONTEXT_DIR" "$TRANSCRIPT"' EXIT
unset EXPERIMENTAL_CONTEXT  # the operator's own environment must not put every case in the mode

fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }
start() { # <session-id> [source] [transcript] → the hook's stdout for a SessionStart payload
  printf '{"session_id":"%s","hook_event_name":"SessionStart","source":"%s","cwd":"/tmp","transcript_path":"%s"}' "$1" "${2:-compact}" "${3:-}" | "$HOOK"
}
expand() { # <session-id> <args> → run the toggle for a UserPromptExpansion payload
  printf '{"session_id":"%s","hook_event_name":"UserPromptExpansion","command_name":"experimental-context","command_args":"%s","prompt":"/experimental-context %s"}' "$1" "$2" "$2" | "$TOGGLE"
}
row() { printf '%s\n' "$1" >> "$TRANSCRIPT"; }
body="$(awk 'seen > 1 { print } /^---$/ { seen++ }' "$REPO_ROOT/skills/experimental-context/SKILL.md")"

echo "environment:"
out="$("$HOOK" </dev/null)"
if [ -z "$out" ]; then pass "no EXPERIMENTAL_CONTEXT, no payload: the hook prints nothing"; else fail "no env: printed: $out"; fi
out="$(EXPERIMENTAL_CONTEXT=0 start s0)"
if [ -z "$out" ]; then pass "EXPERIMENTAL_CONTEXT=0: the hook prints nothing"; else fail "=0: printed: $out"; fi
out="$(EXPERIMENTAL_CONTEXT=1 "$HOOK" </dev/null)"
if grep -q "EXPERIMENTAL-CONTEXT mode" <<<"$out"; then pass "EXPERIMENTAL_CONTEXT=1: the skill body is injected"
else fail "=1: body missing, got: $out"; fi
if grep -qE '^(---|name:|description:|disable-model-invocation:)' <<<"$out"; then
  fail "EXPERIMENTAL_CONTEXT=1: frontmatter leaked into the session"
else pass "EXPERIMENTAL_CONTEXT=1: frontmatter stripped"; fi
if [ "$out" = "$body" ]; then pass "with no transcript the hook's text IS the skill's body"; else fail "hook text differs from the skill body"; fi

echo "mid-session switch:"
SID="11111111-2222-4333-8444-555555555555"
out="$(start "$SID")"
if [ -z "$out" ]; then pass "an unflagged session gets nothing on compact"; else fail "unflagged session printed: $out"; fi
expand "$SID" ""
if [ -f "$CONTEXT_DIR/$SID" ]; then pass "/experimental-context writes the session's flag"; else fail "no flag written"; fi
out="$(start "$SID")"
if [ "$out" = "$body" ]; then pass "a flagged session gets the body on compact, without the env var"
else fail "flagged session on compact got: $out"; fi
out="$(start "$SID" resume)"
if [ "$out" = "$body" ]; then pass "and on resume"; else fail "flagged session on resume got: $out"; fi
out="$(start "other-session")"
if [ -z "$out" ]; then pass "another session is untouched by this session's flag"; else fail "another session printed: $out"; fi
expand "$SID" "off"
if [ ! -e "$CONTEXT_DIR/$SID" ]; then pass "/experimental-context off removes the flag"; else fail "off left the flag"; fi
out="$(start "$SID")"
if [ -z "$out" ]; then pass "after off, compact injects nothing"; else fail "after off, printed: $out"; fi

echo "entries:"
expand "$SID" ""
row '{"type":"user","message":{"role":"user","content":"start"},"timestamp":"2026-08-01T00:00:00Z"}'
row '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"ok <revisit key=\"goal\">Clone with highest fidelity.\nSecond line.</revisit>"}]},"timestamp":"2026-08-01T00:01:00Z"}'
row '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"<revisit key=\"handles\">PR #1</revisit> <revisit key=\"push-policy\">Nothing pushed without request.</revisit>"}]},"timestamp":"2026-08-02T00:00:00Z"}'
row '{"type":"assistant","isSidechain":true,"message":{"role":"assistant","content":[{"type":"text","text":"<revisit key=\"leak\">from a subagent</revisit>"}]},"timestamp":"2026-08-02T00:00:00Z"}'
row '{"type":"system","subtype":"compact_boundary","timestamp":"2026-08-03T00:00:00Z"}'
# shellcheck disable=SC2016
row '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Example:\n```\n<revisit key=\"fenced\">ignored</revisit>\n```\n<revisit key=\"handles\">PR #2</revisit>"}]},"timestamp":"2026-08-04T00:00:00Z"}'
row '{"type":"system","subtype":"compact_boundary","timestamp":"2026-08-05T00:00:00Z"}'
row '{"type":"assistant","message":{"role":"assistant","content":"string content <revisit key=\"push-policy\" retired=\"true\"/>"},"timestamp":"2026-08-06T00:00:00Z"}'
row 'not json at all'
out="$(start "$SID" compact "$TRANSCRIPT")"
entries="${out#"$body"}"
if [ "${out:0:${#body}}" = "$body" ]; then pass "the body comes first, verbatim"; else fail "body not first"; fi
if grep -q '^- goal (set 2026-08-01, 2 compactions ago): Clone with highest fidelity\.$' <<<"$entries"; then pass "goal: first line, date, compactions-ago"
else fail "goal line wrong: $entries"; fi
if grep -q '^  Second line\.$' <<<"$entries"; then pass "a multi-line value keeps its continuation lines, indented"; else fail "continuation missing"; fi
if grep -q '^- handles (set 2026-08-04, 1 compaction ago): PR #2$' <<<"$entries" && ! grep -q 'PR #1' <<<"$entries"; then pass "re-emitting a key supersedes its earlier value"
else fail "supersession wrong: $entries"; fi
if ! grep -q 'push-policy' <<<"$entries"; then pass "a retired key is dropped, from plain-string content too"; else fail "retired key survived"; fi
if ! grep -q 'leak' <<<"$entries"; then pass "sidechain (subagent) rows are ignored"; else fail "sidechain entry leaked"; fi
if ! grep -q 'fenced' <<<"$entries"; then pass "fenced code is ignored"; else fail "fenced example became an entry"; fi
if [ "$(grep -c '^- ' <<<"$entries")" = 2 ]; then pass "exactly the two live keys are listed"; else fail "entry count: $entries"; fi
if grep -q '^- goal' <<<"$entries" && [ "$(grep -n '^- ' <<<"$entries" | head -1)" = "$(grep -n '^- goal' <<<"$entries")" ]; then pass "keys keep first-seen order"; else fail "order wrong"; fi
out="$(start "$SID" compact "/nonexistent/transcript.jsonl")"
if [ "$out" = "$body" ]; then pass "a missing transcript yields the body alone"; else fail "missing transcript: $out"; fi
big="$(python3 -c 'print("x" * 7000)')"
row "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":\"<revisit key=\\\"big\\\">first line\\n$big</revisit>\"},\"timestamp\":\"2026-08-07T00:00:00Z\"}"
out="$(start "$SID" compact "$TRANSCRIPT")"
if grep -q '^- big (set 2026-08-07, 0 compactions ago): first line$' <<<"$out" && ! grep -q 'xxxx' <<<"$out" && grep -q "grep -o" <<<"$out"; then
  pass "over budget, only first lines are shown and the grep recipe names the transcript"
else fail "budget fallback wrong: $(tail -3 <<<"$out")"; fi

echo "sweep:"
touch -t 202601010000 "$CONTEXT_DIR/stale-session"
touch "$CONTEXT_DIR/fresh-session"
start "$SID" >/dev/null
if [ ! -e "$CONTEXT_DIR/stale-session" ]; then pass "an injection sweeps flags older than a week"; else fail "stale flag survived the sweep"; fi
if [ -e "$CONTEXT_DIR/fresh-session" ] && [ -e "$CONTEXT_DIR/$SID" ]; then pass "recent flags survive the sweep"; else fail "a recent flag was swept"; fi

echo "wiring:"
if python3 - "$REPO_ROOT/hooks/hooks.json" <<'PY'
import json, sys
h = json.load(open(sys.argv[1]))["hooks"]
ss = [e for e in h["SessionStart"] if any("experimental-context.sh" in x["command"] for x in e["hooks"])]
assert ss, "hooks.json does not wire experimental-context.sh"
assert all(m in ss[0]["matcher"] for m in ("startup", "compact", "resume")), "SessionStart must fire on startup, resume and compact"
ex = [e for e in h["UserPromptExpansion"] if any("experimental-context-toggle.sh" in x["command"] for x in e["hooks"])]
assert ex, "hooks.json does not wire experimental-context-toggle.sh"
assert ex[0]["matcher"] == "doperpowers:experimental-context|experimental-context", "the matcher is a whole-string match on the qualified and bare command names"
PY
then pass "hooks.json wires SessionStart and the experimental-context expansion"; else fail "hooks.json wiring"; fi

echo
if [ "$FAILURES" -eq 0 ]; then echo "All experimental-context hook tests passed"; exit 0
else echo "$FAILURES experimental-context hook test(s) failed"; exit 1; fi
