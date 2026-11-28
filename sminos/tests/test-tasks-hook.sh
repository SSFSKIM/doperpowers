#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
# smns-tasks.sh (SessionStart) runs `sminos task remind`, prints the start line
# without the keys' line, and only then marks those keys with `sminos task
# shown` (docs/doperpowers/plans/2026-11-27-task-board-b1.md, M1): no store, no
# Python; nothing marked when remind fails, when the hook is killed between its
# two calls, or when the mark fails, so the next start names the same acts; an
# internal fork gets nothing; every path exits 0. HOME and SMINOS_HOME are
# temporary here, and no machine is enrolled.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
HOOK="$PLUGIN_ROOT/hooks/smns-tasks.sh"
SMINOS="$PLUGIN_ROOT/skills/sminos/scripts/sminos"
FAILURES=0
T="$(mktemp -d)"; T="$(cd "$T" && pwd -P)"
trap 'rm -rf "$T"' EXIT
unset SMNS_INTERNAL CLAUDE_CODE_SESSION_ID DAEMON_HOME CLAUDE_PLUGIN_ROOT CLAUDE_PID
export HOME="$T/home" SMINOS_HOME="$T/s" DAEMON_HOST=alpha
mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME"
chmod 700 "$SMINOS_HOME"

fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }
SID=5eed0000-0000-4000-8000-0000000000a1
PAYLOAD="{\"session_id\": \"$SID\",\"cwd\":\"$T\",\"hook_event_name\":\"SessionStart\",\"source\":\"startup\"}"
run() { # [env...] — the hook's stdout for PAYLOAD, its stderr in $T/err, its exit in RC
  OUT="$(printf '%s' "$PAYLOAD" | env "$@" "$HOOK" 2>"$T/err")"; RC=$?
}
waiting() { "$SMINOS" task waiting | wc -l | tr -d ' '; }
# A plugin root whose CLI is the real one but for what $1 does to verb $2.
fake() { # <name> <verb> <shell for that verb>
  mkdir -p "$T/$1/skills/sminos/scripts"
  cat >"$T/$1/skills/sminos/scripts/sminos" <<EOF
#!/usr/bin/env bash
if [ "\${2:-}" = "$2" ]; then $3; fi
exec "$SMINOS" "\$@"
EOF
  chmod +x "$T/$1/skills/sminos/scripts/sminos"
}

echo "no store:"
fake noprobe remind 'touch "'"$T"'/ran"'
run CLAUDE_PLUGIN_ROOT="$T/noprobe"
if [ -z "$OUT" ] && [ "$RC" = 0 ] && [ ! -e "$T/ran" ]; then pass "prints nothing, runs no CLI, exits 0"
else fail "no store: rc=$RC printed: $OUT ran: $([ -e "$T/ran" ] && echo yes)"; fi

CLAUDE_CODE_SESSION_ID=$SID "$SMINOS" task assign --class blocking --title "Log in to the console" \
  --body-file - >/dev/null <<'EOF'
The secret body of the task.
EOF
"$SMINOS" task "done" t1 --note "logged in" >/dev/null 2>&1

echo "a failing remind:"
fake badremind remind 'echo "t1.1"; echo partial; exit 1'
run CLAUDE_PLUGIN_ROOT="$T/badremind"
if [ -z "$OUT" ] && [ "$RC" = 0 ] && [ "$(waiting)" = 1 ]; then pass "prints nothing, marks nothing"
else fail "failing remind: rc=$RC printed: $OUT waiting: $(waiting)"; fi

echo "killed between its two calls:"
fake killed shown 'kill -9 "$PPID"; exit 0'
(printf '%s' "$PAYLOAD" | CLAUDE_PLUGIN_ROOT="$T/killed" "$HOOK" >"$T/out" 2>"$T/err") 2>/dev/null
if grep -q '^The human acted on tasks you assigned: marked t1 done' "$T/out" && [ "$(waiting)" = 1 ]; then
  pass "the line was printed and nothing was marked: the next start names it again"
else fail "killed: printed $(cat "$T/out") waiting: $(waiting)"; fi

echo "a mark that fails:"
fake badmark shown 'exit 1'
run CLAUDE_PLUGIN_ROOT="$T/badmark"
if [ -n "$OUT" ] && [ "$RC" = 0 ] && [ "$(waiting)" = 1 ]; then pass "the line printed, nothing marked, exit 0"
else fail "failing mark: rc=$RC printed: $OUT waiting: $(waiting)"; fi

echo "an internal fork:"
run SMNS_INTERNAL=1
if [ -z "$OUT" ] && [ "$RC" = 0 ] && [ "$(waiting)" = 1 ]; then pass "gets nothing, marks nothing"
else fail "SMNS_INTERNAL: rc=$RC printed: $OUT"; fi
OUT="$("$HOOK" </dev/null 2>&1)"; RC=$?
if [ -z "$OUT" ] && [ "$RC" = 0 ]; then pass "no payload: nothing, exit 0"; else fail "no payload: rc=$RC printed: $OUT"; fi

echo "the real hook:"
run
want="The human acted on tasks you assigned: marked t1 done. Read one: sminos task show t1"
if [ "$OUT" = "$want" ] && [ "$RC" = 0 ] && [ ! -s "$T/err" ]; then pass "prints the start line without the keys' line"
else fail "printed: [$OUT] rc=$RC stderr: $(cat "$T/err")"; fi
case "$OUT" in *"Log in"*|*secret*|*"logged in"*) fail "the line holds text an agent or the human wrote" ;;
  *) pass "no title, body or note in what it prints" ;; esac
if [ "$(waiting)" = 0 ]; then pass "the outcome is marked after the print"; else fail "still waiting: $(waiting)"; fi
shown_to="$("$SMINOS" task show t1 --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["outcomes"][0]["shown"]["session"])')"
if [ "$shown_to" = "$SID" ]; then pass "shown to the session the payload names"; else fail "shown to: $shown_to"; fi
run
if [ -z "$OUT" ] && [ "$RC" = 0 ]; then pass "the next start names nothing again"; else fail "again: $OUT"; fi

echo "a fork's start:"
CLAUDE_CODE_SESSION_ID=$SID "$SMINOS" task assign --class needed --title "Rotate the key" >/dev/null
PAYLOAD="{\"session_id\":\"5eed0000-0000-4000-8000-0000000000f1\",\"source\":\"fork\"}"
run
case "$OUT" in "This conversation is a fork:"*) pass "the fork is told whose tasks stay where" ;;
  *) fail "fork: [$OUT]" ;; esac

if python3 - "$PLUGIN_ROOT/hooks/hooks.json" <<'PY'
import json, sys
ss = json.load(open(sys.argv[1]))["hooks"]["SessionStart"]
entries = [e for e in ss if any("smns-tasks.sh" in x["command"] for x in e["hooks"])]
assert len(entries) == 1 and entries[0]["matcher"] == "startup|resume|clear|compact|fork"
PY
then pass "hooks.json wires smns-tasks.sh on SessionStart for every source"
else fail "hooks.json wiring"; fi

echo
if [ "$FAILURES" -eq 0 ]; then echo "test-tasks-hook: all passed"; exit 0; fi
echo "test-tasks-hook: $FAILURES failed"; exit 1
