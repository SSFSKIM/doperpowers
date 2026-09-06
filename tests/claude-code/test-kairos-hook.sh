#!/usr/bin/env bash
# The kairos hooks. kairos.sh (SessionStart) is silent unless the session is in
# proactive mode — KAIROS=1 in its environment, or a flag file named by its
# session id — and then prints the skill BODY (never the frontmatter), the same
# text `/kairos` loads. kairos-toggle.sh (UserPromptExpansion on `kairos`)
# writes and removes that flag. Both take the flag directory from KAIROS_DIR so
# this suite never touches ~/.claude/kairos.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/hooks/kairos.sh"
TOGGLE="$REPO_ROOT/hooks/kairos-toggle.sh"
FAILURES=0
KAIROS_DIR="$(mktemp -d)"; export KAIROS_DIR
trap 'rm -rf "$KAIROS_DIR"' EXIT
unset KAIROS  # the operator's own environment must not put every case in the mode

fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }
start() { # <session-id> [source] → the hook's stdout for a SessionStart payload
  printf '{"session_id":"%s","hook_event_name":"SessionStart","source":"%s","cwd":"/tmp"}' "$1" "${2:-compact}" | "$HOOK"
}
expand() { # <session-id> <args> → run the toggle for a UserPromptExpansion payload
  printf '{"session_id":"%s","hook_event_name":"UserPromptExpansion","command_name":"kairos","command_args":"%s","prompt":"/kairos %s"}' "$1" "$2" "$2" | "$TOGGLE"
}
body="$(awk 'seen > 1 { print } /^---$/ { seen++ }' "$REPO_ROOT/skills/kairos/SKILL.md")"

echo "environment:"
out="$("$HOOK" </dev/null)"
if [ -z "$out" ]; then pass "no KAIROS, no payload: the hook prints nothing"; else fail "no KAIROS: printed: $out"; fi
out="$(KAIROS=0 start s0)"
if [ -z "$out" ]; then pass "KAIROS=0: the hook prints nothing"; else fail "KAIROS=0: printed: $out"; fi
out="$(KAIROS=1 "$HOOK" </dev/null)"
if grep -q "PROACTIVE mode" <<<"$out"; then pass "KAIROS=1: the skill body is injected"
else fail "KAIROS=1: body missing, got: $out"; fi
if grep -qE '^(---|name:|description:|disable-model-invocation:)' <<<"$out"; then
  fail "KAIROS=1: frontmatter leaked into the session"
else pass "KAIROS=1: frontmatter stripped"; fi
if [ "$out" = "$body" ]; then pass "the hook's text IS the skill's body"; else fail "hook text differs from the skill body"; fi

echo "mid-session switch:"
SID="11111111-2222-4333-8444-555555555555"
out="$(start "$SID")"
if [ -z "$out" ]; then pass "an unflagged session gets nothing on compact"; else fail "unflagged session printed: $out"; fi
expand "$SID" ""
if [ -f "$KAIROS_DIR/$SID" ]; then pass "/kairos writes the session's flag"; else fail "/kairos wrote no flag"; fi
out="$(start "$SID")"
if [ "$out" = "$body" ]; then pass "a flagged session gets the body on compact, without KAIROS in its environment"
else fail "flagged session on compact got: $out"; fi
out="$(start "$SID" resume)"
if [ "$out" = "$body" ]; then pass "and on resume"; else fail "flagged session on resume got: $out"; fi
out="$(start "other-session")"
if [ -z "$out" ]; then pass "another session is untouched by this session's flag"; else fail "another session printed: $out"; fi
expand "$SID" "off"
if [ ! -e "$KAIROS_DIR/$SID" ]; then pass "/kairos off removes the flag"; else fail "/kairos off left the flag"; fi
out="$(start "$SID")"
if [ -z "$out" ]; then pass "after off, compact injects nothing"; else fail "after off, printed: $out"; fi
expand "$SID" "off"
if [ ! -e "$KAIROS_DIR/$SID" ]; then pass "/kairos off on an unflagged session is a no-op"; else fail "off created a flag"; fi

echo "sweep:"
expand "$SID" ""
touch -t 202601010000 "$KAIROS_DIR/stale-session"
touch "$KAIROS_DIR/fresh-session"
start "$SID" >/dev/null
if [ ! -e "$KAIROS_DIR/stale-session" ]; then pass "an injection sweeps flags older than a week"; else fail "stale flag survived the sweep"; fi
if [ -e "$KAIROS_DIR/fresh-session" ] && [ -e "$KAIROS_DIR/$SID" ]; then pass "recent flags survive the sweep"; else fail "a recent flag was swept"; fi

echo "wiring:"
if python3 - "$REPO_ROOT/hooks/hooks.json" <<'PY'
import json, sys
h = json.load(open(sys.argv[1]))["hooks"]
ss = h["SessionStart"]
assert any("kairos.sh" in x["command"] for e in ss for x in e["hooks"]), "hooks.json does not wire kairos.sh"
assert all(m in ss[0]["matcher"] for m in ("startup", "compact", "resume")), "SessionStart must fire on startup, resume and compact"
ex = h["UserPromptExpansion"]
assert ex[0]["matcher"] == "kairos", "the toggle must match only the kairos command"
assert any("kairos-toggle.sh" in x["command"] for e in ex for x in e["hooks"]), "hooks.json does not wire kairos-toggle.sh"
PY
then pass "hooks.json wires SessionStart and the kairos expansion"; else fail "hooks.json wiring"; fi

echo
if [ "$FAILURES" -eq 0 ]; then echo "All kairos hook tests passed"; exit 0
else echo "$FAILURES kairos hook test(s) failed"; exit 1; fi
