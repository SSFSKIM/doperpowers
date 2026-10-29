#!/usr/bin/env bash
# smns-guide.sh (SessionStart) hands its payload to `sminos guide` and prints
# what that prints, which the engine adds to the session's context: on a
# machine enrolled at a desk hub (hub.json, or identity.json once cut over
# to its endpoint), who the session is in the org and how it
# reaches the others (docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md
# §9). The gate is the verb's (tests/test-guide.sh pins its text); the
# hook only passes the payload on, never prints an error, never blocks a start,
# and exits 0 on every path. HOME and SMINOS_HOME are temporary here.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
HOOK="$PLUGIN_ROOT/hooks/smns-guide.sh"
SMINOS="$PLUGIN_ROOT/skills/sminos/scripts/sminos"
FAILURES=0
T="$(mktemp -d)"; T="$(cd "$T" && pwd -P)"
trap 'rm -rf "$T"' EXIT
unset SMNS_INTERNAL CLAUDE_CODE_SESSION_ID DAEMON_HOME CLAUDE_PLUGIN_ROOT
export HOME="$T/home" SMINOS_HOME="$T/s" DAEMON_HOST=alpha
mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME/daemon" "$T/dir"

fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  [PASS] $1"; }
SID=1a000001-0000-4000-8000-000000000001
PAYLOAD="{\"session_id\":\"$SID\",\"cwd\":\"$T/dir\",\"transcript_path\":\"$T/none.jsonl\",\"hook_event_name\":\"SessionStart\",\"source\":\"startup\"}"
run() { # [env...] — the hook's stdout for PAYLOAD, its stderr in $T/err, its exit in RC
  OUT="$(printf '%s' "$PAYLOAD" | env "$@" "$HOOK" 2>"$T/err")"; RC=$?
}

echo "a machine not enrolled:"
run
if [ -z "$OUT" ] && [ "$RC" = 0 ]; then pass "prints nothing, exits 0"; else fail "rc=$RC printed: $OUT"; fi

printf '{"hub":"http://127.0.0.1:9","org":"org-1","machine":"alpha"}\n' > "$SMINOS_HOME/daemon/hub.json"
# The engine's record of the session: guidance goes only to a member on sight.
printf '{"pid":%s,"sessionId":"%s","name":"s1","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","entrypoint":"cli"}\n' \
  "$$" "$SID" "$T/dir" > "$HOME/.claude/sessions/s1.json"
echo "an enrolled machine:"
run
want="$(printf '%s' "$PAYLOAD" | "$SMINOS" guide)"
if [ -n "$want" ] && [ "$OUT" = "$want" ]; then pass "prints exactly what sminos guide prints"; else fail "printed: $OUT"; fi
if [ "$RC" = 0 ] && [ ! -s "$T/err" ]; then pass "exit 0, nothing on stderr"; else fail "rc=$RC stderr: $(cat "$T/err")"; fi
run SMNS_INTERNAL=1
if [ -z "$OUT" ] && [ "$RC" = 0 ]; then pass "an internal fork gets nothing"; else fail "SMNS_INTERNAL: rc=$RC printed: $OUT"; fi
OUT="$("$HOOK" </dev/null 2>&1)"; RC=$?
if [ -z "$OUT" ] && [ "$RC" = 0 ]; then pass "no payload: nothing, exit 0"; else fail "no payload: rc=$RC printed: $OUT"; fi

echo "the enrollment's file (hub.json, or identity.json on a machine cut over to its endpoint):"
GATE="$T/gate-plugin"
mkdir -p "$GATE/skills/sminos/scripts"
printf '#!/bin/sh\necho guided\n' > "$GATE/skills/sminos/scripts/sminos"
chmod +x "$GATE/skills/sminos/scripts/sminos"
for f in hub.json identity.json none; do
  rm -rf "$SMINOS_HOME/daemon"; mkdir -p "$SMINOS_HOME/daemon"
  [ "$f" = none ] || printf '{}' > "$SMINOS_HOME/daemon/$f"
  run CLAUDE_PLUGIN_ROOT="$GATE"
  if [ "$f" = none ]; then
    if [ -z "$OUT" ] && [ "$RC" = 0 ]; then pass "with neither file, the hook exits before the verb"; else fail "neither file: rc=$RC printed: $OUT"; fi
  elif [ "$OUT" = guided ] && [ "$RC" = 0 ]; then pass "with $f alone, the hook reaches sminos guide"
  else fail "$f alone: rc=$RC printed: $OUT"; fi
done
printf '{}' > "$SMINOS_HOME/daemon/hub.json"

echo "a CLI that fails:"
FAKE="$T/plugin"
mkdir -p "$FAKE/skills/sminos/scripts"
printf '#!/bin/sh\necho "partial"\necho "Traceback: boom" >&2\nexit 1\n' > "$FAKE/skills/sminos/scripts/sminos"
chmod +x "$FAKE/skills/sminos/scripts/sminos"
run CLAUDE_PLUGIN_ROOT="$FAKE"
if [ -z "$OUT" ] && [ "$RC" = 0 ] && [ ! -s "$T/err" ]; then pass "a failing verb's output and error never reach the session; exit 0"
else fail "failing CLI: rc=$RC printed: $OUT stderr: $(cat "$T/err")"; fi

echo "wiring:"
if python3 - "$PLUGIN_ROOT/hooks/hooks.json" <<'PY'
import json, sys
ss = json.load(open(sys.argv[1]))["hooks"]["SessionStart"]
entries = [e for e in ss if any("smns-guide.sh" in x["command"] for x in e["hooks"])]
assert len(entries) == 1, "hooks.json wires smns-guide.sh on SessionStart once"
assert entries[0]["matcher"] == "startup|resume|clear|compact|fork", \
    "a compaction loses the context and a fork has a new session id: the guide fires on every source"
PY
then pass "hooks.json wires smns-guide.sh on SessionStart for startup, resume, clear, compact and fork"
else fail "hooks.json wiring"; fi

if [ "$FAILURES" -eq 0 ]; then echo "PASS"; exit 0; else echo "FAIL ($FAILURES)"; exit 1; fi
