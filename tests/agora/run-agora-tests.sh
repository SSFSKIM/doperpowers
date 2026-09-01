#!/usr/bin/env bash
#
# Hermetic tests for the agora CLI (skills/agora/scripts/agora → agora.py).
#
# agora shells out to the real `claude` CLI (--bg [--resume] / agents --json /
# stop / rm) and reads the harness's peer registry (~/.claude/sessions/*.json)
# and inbox sockets. To stay deterministic, offline, and free of real sessions,
# this suite puts a STUB `claude` first on PATH (coloured bg banner, agents
# --json rows from a state dir, transcript files, same-id --resume, stop/rm),
# redirects HOME and AGORA_HOME to temp dirs, and runs a tiny unix-socket
# server standing in for a live session's inbox. Every test drives the real
# CLI and asserts on the registry, replies, frames, and rendered views.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGORA="$REPO_ROOT/skills/agora/scripts/agora"

FAILURES=0
PASSES=0
TEST_ROOT="$(mktemp -d)"
SOCK_PID=""
cleanup() {
  [ -n "$SOCK_PID" ] && kill "$SOCK_PID" 2>/dev/null || true
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

pass() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "  FAIL $1"; }
assert_equals() {
  if [[ "$1" == "$2" ]]; then pass "$3"; else
    fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
  if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:600}"; fi
}
assert_not_contains() {
  if printf '%s' "$1" | grep -Fq -- "$2"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:600}"
  else pass "$3"; fi
}
assert_file_exists() { if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi; }
assert_file_absent() { if [[ ! -e "$1" ]]; then pass "$2"; else fail "$2"; echo "    still present: $1"; fi; }
assert_rc() { # expected-rc actual-rc label
  if [[ "$1" == "$2" ]]; then pass "$3"; else fail "$3"; echo "    expected rc $1, got $2"; fi
}
mode_of() { python3 -c 'import os, sys; print("%04o" % (os.stat(sys.argv[1]).st_mode & 0o777))' "$1"; }
field() { # seat-id field  → value (via python, never jq)
  python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); v = d.get(sys.argv[2], ""); print(v if isinstance(v, str) else json.dumps(v))' "$AGORA_HOME/$1.json" "$2"
}
seat_id_of() { # alias → seat id of the first record carrying it
  python3 -c 'import glob, json, os, sys
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
    if p.endswith(".reply.json"):
        continue
    try:
        d = json.load(open(p))
    except Exception:
        continue
    if (d.get("alias") or d.get("name")) == sys.argv[2]:
        print(os.path.basename(p)[:-5])
        break' "$AGORA_HOME" "$1"
}
banner_uuid() { printf '%s' "$1" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1; }
banner_short() { printf '%s' "$1" | sed -n 's/.*\[\([0-9a-f]*\) \/ [0-9a-f-]*\].*/\1/p' | head -1; }

# ---- environment: isolated HOME, registry, PATH-shadowed claude stub ---------
# The transport env starts EMPTY: the stub snapshots exactly these names into
# calls.log and assertion failures print that log, so a real credential in the
# runner's shell must never reach it.
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_SUBAGENT_MODEL UNRELATED_TRANSPORT_VAR
unset DAEMON_CLAUDE_SETTINGS DAEMON_CLAUDE_EFFORT AGORA_ALIAS RUNNER_TRACKING_ID DAEMON_HOME
export HOME="$TEST_ROOT/home"
export AGORA_HOME="$TEST_ROOT/registry"
export STUB_STATE="$TEST_ROOT/stub"
export AGORA_POLL_INTERVAL=0.05
export DAEMON_TIMEOUT=10
export AGORA_UUID_POLL=5
export DAEMON_BOOT_ID="boot-current"
export DAEMON_HOST="testhost"
export AGORA_NO_EXEC=1
WORK="$TEST_ROOT/work"
mkdir -p "$HOME/.claude/sessions" "$WORK" "$STUB_STATE/agents" "$STUB_STATE/log"

STUB_BIN="$TEST_ROOT/bin"
mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
# Minimal deterministic stand-in for the `claude` CLI (test use only).
set -euo pipefail
mkdir -p "$STUB_STATE/agents" "$STUB_STATE/log"
echo "$*" >> "$STUB_STATE/log/calls.log"

case "${1:-}" in
  agents)
    python3 - "$STUB_STATE/agents" <<'PY'
import glob, json, os, sys
out = []
for f in glob.glob(os.path.join(sys.argv[1], '*')):
    m = dict(l.rstrip('\n').split('=', 1) for l in open(f) if '=' in l)
    row = {"id": m.get("short"), "sessionId": m.get("uuid"), "kind": m.get("kind", "background"),
           "name": m.get("name"), "state": m.get("state", "done"),
           "status": m.get("status", ""), "cwd": m.get("cwd", "")}
    if m.get("pid"):
        row["pid"] = int(m["pid"])
    out.append(row)
print(json.dumps(out))
PY
    exit 0 ;;
  stop)
    f="$STUB_STATE/agents/${2:-}"
    if [ -f "$f" ]; then sed -i.bak 's/^state=.*/state=stopped/' "$f" && rm -f "$f.bak"; fi
    echo "stopped ${2:-}"; exit 0 ;;
  rm) rm -f "$STUB_STATE/agents/${2:-}"; echo "removed ${2:-}"; exit 0 ;;
  attach) echo "attached ${2:-}"; exit 0 ;;
esac

args=("$@")
prompt="${args[$((${#args[@]} - 1))]}"
has_bg=0; name=""; resume_uuid=""; worktree=""; i=0
while [ $i -lt ${#args[@]} ]; do
  case "${args[$i]}" in
    --bg) has_bg=1 ;;
    -n) i=$((i + 1)); name="${args[$i]}" ;;
    --resume) i=$((i + 1)); resume_uuid="${args[$i]}" ;;
    --worktree) i=$((i + 1)); worktree="${args[$i]}" ;;
  esac
  i=$((i + 1))
done

tx_path() { printf '%s/.claude/projects/%s/%s.jsonl' "$HOME" "$(printf '%s' "$PWD" | sed 's#/#-#g')" "$1"; }
write_asst() {
  local f; f="$(tx_path "$1")"; mkdir -p "$(dirname "$f")"
  python3 - "$f" "$2" <<'PY'
import json, sys
open(sys.argv[1], 'a').write(json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": sys.argv[2]}]}}) + "\n")
PY
}

if [ $has_bg -eq 1 ]; then
  # Transport-env snapshot: what the launched agent would actually inherit,
  # keyed by the prompt's first line so tests can grep the exact launch.
  # `path=` records only whether PATH survived.
  first="${prompt%%$'\n'*}"
  echo "bg-env:$first base=${ANTHROPIC_BASE_URL:-};token=${ANTHROPIC_AUTH_TOKEN:-};sub=${CLAUDE_CODE_SUBAGENT_MODEL:-};keep=${UNRELATED_TRANSPORT_VAR:-};runner=${RUNNER_TRACKING_ID:-};path=${PATH:+set}" >> "$STUB_STATE/log/calls.log"
  if [ "${STUB_FAIL_BG:-0}" = "1" ]; then
    echo "stub: simulated --bg launch failure" >&2
    exit 1
  fi
  n=$(cat "$STUB_STATE/counter" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_STATE/counter"
  short=$(printf '%08x' "$n")
  uuid="${short}-e808-4cad-a7e0-c1e6447bad28"
  # `--bg --resume <id>` continues the SAME session id (a new background job,
  # hence a new short). STUB_RESUME_COPY=1 emulates the harness starting a
  # copy because the session was already running.
  if [ -n "$resume_uuid" ] && [ "${STUB_RESUME_COPY:-0}" != "1" ]; then uuid="$resume_uuid"; fi
  [ "${STUB_NO_UUID:-0}" = "1" ] && uuid=""
  cwd="$PWD"; [ -n "$worktree" ] && cwd="$PWD/.claude/worktrees/$worktree"
  { echo "short=$short"; echo "uuid=$uuid"; echo "name=$name"; echo "state=${STUB_BG_STATE:-done}"
    echo "status=${STUB_BG_STATUS:-}"; echo "cwd=$cwd"; } > "$STUB_STATE/agents/$short"
  if [ -z "$uuid" ]; then
    :
  elif [ -n "$resume_uuid" ]; then
    write_asst "$uuid" "RESUMED:$resume_uuid:ANSWER:$prompt"
  else
    write_asst "$uuid" "ANSWER:$prompt"
  fi
  printf 'backgrounded · \033[36m%s\033[39m · %s\n' "$short" "$name"
  exit 0
fi

echo "stub: unhandled invocation: $*" >&2; exit 1
STUB
chmod +x "$STUB_BIN/claude"
export PATH="$STUB_BIN:$PATH"

# A stand-in for a live session's inbox socket: appends every frame it
# receives to inbox.received, one connection at a time, forever.
cat > "$TEST_ROOT/sockserver.py" <<'PY'
import os, socket, sys
path, out = sys.argv[1], sys.argv[2]
try:
    os.unlink(path)
except FileNotFoundError:
    pass
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(path)
srv.listen(8)
while True:
    c, _ = srv.accept()
    buf = b""
    while True:
        chunk = c.recv(65536)
        if not chunk:
            break
        buf += chunk
    with open(out, "ab") as f:
        f.write(buf)
    try:
        c.sendall(b"ok\n")
    except OSError:
        pass
    c.close()
PY
SOCK="$TEST_ROOT/inbox.sock"
RECEIVED="$TEST_ROOT/inbox.received"
python3 "$TEST_ROOT/sockserver.py" "$SOCK" "$RECEIVED" &
SOCK_PID=$!
disown "$SOCK_PID"
for _ in $(seq 1 50); do [ -S "$SOCK" ] && break; sleep 0.05; done

run() { # capture stdout+stderr and rc without aborting the suite
  set +e; OUT="$("$@" 2>&1)"; RC=$?; set -e
}

# ---- 1) usage ----------------------------------------------------------------
echo "usage:"
run "$AGORA"; assert_rc 2 "$RC" "no arguments is a usage error (exit 2)"
run "$AGORA" help; assert_rc 0 "$RC" "help exits 0"; assert_contains "$OUT" "agora spawn" "help lists the verbs"
run "$AGORA" listen grp x; assert_rc 2 "$RC" "listen is refused"; assert_contains "$OUT" "SendMessage" "listen refusal points at SendMessage"
run "$AGORA" bogus; assert_rc 2 "$RC" "unknown command is a usage error"
run "$AGORA" seat; assert_rc 2 "$RC" "bare 'seat' is a usage error"

# ---- 2) migration ------------------------------------------------------------
# Runs only when the DEFAULT root is in use: a separate HOME with the old
# daemon registry, an agora v2 group, and a record lacking `group`.
echo "migration:"
MH="$TEST_ROOT/mighome"
OLD="$MH/.claude/orchestrating-daemons"
NEW="$MH/.claude/agora"
mkdir -p "$OLD/board-claims" "$NEW/groups/demo/nodes"
OLD_UUID="11111111-aaaa-4000-8000-000000000001"
printf '{"uuid":"%s","name":"old-worker","status":"idle","current":"%s","cwd":"%s","ticket":"42","task":"legacy"}\n' \
  "$OLD_UUID" "$OLD_UUID" "$WORK" > "$OLD/$OLD_UUID.json"
printf 'legacy reply\n' > "$OLD/$OLD_UUID.reply.txt"
printf '{}' > "$OLD/board-claims/7.json"
printf '{"alias":"scout","parent":"orchestrator","addr":"scout","session":"22222222-bbbb-4000-8000-000000000002","cwd":"/x","branch":"","desc":"scouts ahead","joined":"2026-01-01T00:00:00Z","updated":"2026-01-01T00:00:00Z"}\n' \
  > "$NEW/groups/demo/nodes/scout.json"
CODEX_UUID="12121212-abab-4000-8000-000000000012"
printf '{"uuid":"%s","name":"codexy","status":"idle","current":"%s","cwd":"%s","engine":"codex","pid":"99999","event_log":"/x.events.jsonl"}\n' \
  "$CODEX_UUID" "$CODEX_UUID" "$WORK" > "$OLD/$CODEX_UUID.json"
run env -u AGORA_HOME HOME="$MH" "$AGORA" list
assert_rc 0 "$RC" "first command against the default root migrates and lists"
if [ -L "$OLD" ]; then pass "old daemon root became a symlink"; else fail "old daemon root became a symlink"; fi
assert_file_exists "$NEW/$OLD_UUID.json" "daemon meta moved into the new root"
assert_file_exists "$NEW/$OLD_UUID.reply.txt" "reply file moved"
assert_file_exists "$NEW/board-claims/7.json" "pipeline sibling dir moved intact"
assert_contains "$(cat "$NEW/$OLD_UUID.json")" '"group": "work"' "record lacking group is stamped from its cwd (dir basename)"
assert_contains "$(cat "$NEW/$OLD_UUID.json")" '"ticket": "42"' "pipeline fields survive the stamp"
assert_file_absent "$NEW/groups/demo/nodes" "v2 nodes dir converted away"
assert_file_exists "$NEW/22222222-bbbb-4000-8000-000000000002.json" "v2 node became a seat keyed by its session"
assert_contains "$(cat "$NEW/22222222-bbbb-4000-8000-000000000002.json")" '"brief": "scouts ahead"' "v2 desc became brief"
assert_contains "$(cat "$NEW/22222222-bbbb-4000-8000-000000000002.json")" '"status": "retired"' "converted seat is retired"
assert_contains "$OUT" "old-worker" "migrated daemon listed as a seat"
assert_contains "$OUT" "scout" "converted node listed as a seat"
assert_not_contains "$OUT" "null" "list never prints null for pre-seat records"
assert_contains "$(cat "$NEW/$CODEX_UUID.json")" '"status": "retired"' "legacy codex records are retired by migration"
run env -u AGORA_HOME HOME="$MH" "$AGORA" wake codexy "x"
assert_rc 4 "$RC" "wake refuses a legacy codex record"
run env -u AGORA_HOME HOME="$MH" "$AGORA" resume codexy "x"
assert_rc 4 "$RC" "resume refuses a legacy codex record"
run env -u AGORA_HOME HOME="$MH" "$AGORA" fill codexy "x"
assert_rc 4 "$RC" "fill refuses a legacy codex record"
if ls -d "$MH/.claude/agora.v2-"* >/dev/null 2>&1; then fail "the set-aside v2 root is removed once merged"; else pass "the set-aside v2 root is removed once merged"; fi
run env -u AGORA_HOME HOME="$MH" "$AGORA" migrate
assert_rc 0 "$RC" "explicit migrate exits 0 when nothing is left to do"
assert_equals "$OUT" "" "explicit migrate is silent when it did nothing"
run env -u AGORA_HOME HOME="$MH" "$AGORA" migrate --quiet
assert_rc 0 "$RC" "migrate --quiet is accepted"
run env -u AGORA_HOME HOME="$MH" "$AGORA" list
assert_rc 0 "$RC" "migration is idempotent (second run exits 0)"
run env -u AGORA_HOME HOME="$MH" "$AGORA" view demo
assert_not_contains "$OUT" "null" "view never prints null for a converted node"
assert_contains "$OUT" "dangling — parent 'orchestrator' unknown" "converted node with unknown parent renders in the dangling section"
run env -u AGORA_HOME HOME="$MH" "$AGORA" topology work
assert_not_contains "$OUT" "null" "topology never prints null for a v1-shaped record"
assert_contains "$OUT" '"addr": "old-worker"' "topology falls back addr → alias → name"

# ---- 3) seats: validation and vacant/registered seats ------------------------
echo "seat add:"
run "$AGORA" seat add grp "bad/alias"; assert_rc 2 "$RC" "alias with a slash is rejected"
run "$AGORA" seat add grp ".."; assert_rc 2 "$RC" "'..' is rejected as an alias"
run "$AGORA" seat add grp human; assert_rc 2 "$RC" "'human' is reserved"
run "$AGORA" seat add "../grp" x; assert_rc 2 "$RC" "group name with traversal is rejected"
ORCH_UUID="33333333-cccc-4000-8000-000000000003"
run "$AGORA" seat add grp orchestrator --role lead --session "$ORCH_UUID" --addr "my session"
assert_rc 0 "$RC" "registering an existing session as a seat"
assert_file_exists "$AGORA_HOME/$ORCH_UUID.json" "a registered session's seat is keyed by its session id"
assert_equals "$(field "$ORCH_UUID" addr)" "my session" "--addr is stored (not name-validated)"
assert_equals "$(field "$ORCH_UUID" role)" "lead" "--role is stored"
assert_equals "$(field "$ORCH_UUID" status)" "idle" "a registered session starts idle"
assert_equals "$(mode_of "$AGORA_HOME/$ORCH_UUID.json")" "0600" "seat records are private (umask 077)"
assert_equals "$(mode_of "$AGORA_HOME")" "0700" "the registry root is private"
run "$AGORA" seat add grp scribe --role writer --parent orchestrator --brief "keeps notes"
assert_rc 0 "$RC" "adding a vacant seat"
assert_contains "$OUT" "vacant" "vacant seat reported"
run "$AGORA" list grp
assert_contains "$OUT" "vacant" "list shows the vacant seat's live state"
assert_contains "$OUT" "writer" "list shows the role"
run "$AGORA" join grp joiner --parent orchestrator --desc "v2 style"
assert_rc 0 "$RC" "v2 'join' still works as an alias of seat add"
run "$AGORA" list --json grp
assert_contains "$OUT" '"brief": "v2 style"' "join's --desc lands in brief"
run "$AGORA" leave grp joiner
assert_rc 0 "$RC" "v2 'leave' removes the seat"

# ---- 4) spawn ----------------------------------------------------------------
echo "spawn:"
cd "$WORK"
run "$AGORA" spawn researcher "PING-scope-42" --group grp --parent orchestrator --role researcher
assert_rc 0 "$RC" "spawn exits 0"
assert_contains "$OUT" "seat spawned: researcher" "spawn banner names the seat"
R_UUID="$(banner_uuid "$OUT")"; R_SHORT="$(banner_short "$OUT")"
assert_file_exists "$AGORA_HOME/$R_UUID.json" "record is named after the first session's uuid (banner bracket form)"
assert_equals "$(field "$R_UUID" alias)" "researcher" "alias recorded"
assert_equals "$(field "$R_UUID" name)" "researcher" "harness display name = alias"
assert_equals "$(field "$R_UUID" group)" "grp" "explicit group recorded"
assert_equals "$(field "$R_UUID" parent)" "orchestrator" "parent recorded"
assert_equals "$(field "$R_UUID" role)" "researcher" "role recorded"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "current = first session"
assert_equals "$(field "$R_UUID" short)" "$R_SHORT" "short recorded"
assert_equals "$(field "$R_UUID" status)" "idle" "a first turn that already ended records idle"
assert_equals "$(field "$R_UUID" turns)" "1" "turn 1 recorded"
assert_equals "$(field "$R_UUID" cwd)" "$WORK" "cwd recorded from the harness row"
assert_contains "$(field "$R_UUID" task)" 'You are seat "researcher" in agora group "grp"' "explicit --group prepends the preamble"
assert_contains "$(field "$R_UUID" task)" "--group grp --parent researcher" "preamble tells the seat how to spawn its own children"
assert_contains "$(field "$R_UUID" task)" "PING-scope-42" "task text follows the preamble"
assert_file_exists "$AGORA_HOME/$R_UUID.reply.txt" "reply of an already-finished first turn is recorded"
assert_contains "$(cat "$AGORA_HOME/$R_UUID.reply.txt")" "ANSWER:" "recorded reply comes from the transcript"
assert_contains "$(grep 'bg-env:You are seat' "$STUB_STATE/log/calls.log" | tail -1)" "path=set" "PATH survives the plain-route launch"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--permission-mode auto -n researcher" "launch uses auto permission mode and the alias as display name"

run "$AGORA" spawn plainworker "NOGROUP-1"
assert_rc 0 "$RC" "spawn without --group"
P_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$P_UUID" group)" "work" "group derived from the cwd when --group is absent"
assert_not_contains "$(field "$P_UUID" task)" "You are seat" "no preamble without an explicit --group"
assert_equals "$(field "$P_UUID" preamble)" "" "implicit-group seat records no preamble flag"

run "$AGORA" spawn researcher "again" --group grp
assert_rc 4 "$RC" "spawning an existing seat is refused"
assert_contains "$OUT" "agora fill" "refusal points at fill for a stopped seat"

STUB_BG_STATE=running run "$AGORA" spawn nowaiter "LONG-TASK-7" --no-wait --group grp
assert_rc 0 "$RC" "--no-wait is accepted"
NW_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$NW_UUID" status)" "working" "a running first turn records working"
assert_file_absent "$AGORA_HOME/$NW_UUID.reply.txt" "no reply file while the turn runs"
run "$AGORA" reply nowaiter
assert_contains "$OUT" "ANSWER:" "reply reads the running turn's transcript"
assert_contains "$OUT" "--- latest reply ---" "reply prints its header"

run "$AGORA" spawn waiter "WAIT-1" --group grp --wait
assert_rc 0 "$RC" "--wait exits 0 on a finished turn"
assert_contains "$OUT" "--- reply ---" "--wait prints the reply block"
assert_contains "$OUT" "ANSWER:" "--wait prints the reply text"
W_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$W_UUID" status)" "idle" "--wait records idle"

STUB_BG_STATE=running run "$AGORA" spawn slow "SLOW-1" --group grp --wait
assert_rc 1 "$RC" "--wait watcher timeout exits 1"
assert_contains "$OUT" "watcher expired" "watcher timeout is reported"
S_UUID="$(seat_id_of slow)"
assert_equals "$(field "$S_UUID" status)" "working" "watcher timeout leaves status working (the turn is live)"

record_count() { local n=0 f; for f in "$AGORA_HOME"/*.json; do case "$f" in *.reply.json) ;; *) n=$((n + 1)) ;; esac; done; echo "$n"; }
before=$(record_count)
STUB_FAIL_BG=1 run "$AGORA" spawn failer "F" --group grp
assert_rc 1 "$RC" "a launch that prints no id exits 1"
after=$(record_count)
assert_equals "$after" "$before" "a failed launch leaves no phantom seat"

STUB_NO_UUID=1 run "$AGORA" spawn nouuid "N" --group grp
assert_rc 1 "$RC" "a session with no uuid exits 1"
NU_ID="$(seat_id_of nouuid)"
assert_equals "$(field "$NU_ID" status)" "error" "no-uuid launch records status error"
if [ -n "$(field "$NU_ID" pending_short)" ]; then pass "no-uuid launch records pending_short for recovery"; else fail "no-uuid launch records pending_short for recovery"; fi
"$AGORA" remove "grp/nouuid" >/dev/null

# gateway dimension: env-injected settings/effort ride the launch and are
# persisted; the plain route scrubs the gateway's transport env (PATH survives).
GW="$TEST_ROOT/gw.json"
printf '{"env":{"ANTHROPIC_BASE_URL":"http://gw","ANTHROPIC_AUTH_TOKEN":"tok","CLAUDE_CODE_SUBAGENT_MODEL":"m","PATH":"/nope"}}' > "$GW"
mkdir -p "$HOME/.claude"; cp "$GW" "$HOME/.claude/clodex-settings.json"
export ANTHROPIC_BASE_URL="http://gw" ANTHROPIC_AUTH_TOKEN="fixture-token" CLAUDE_CODE_SUBAGENT_MODEL="sub" UNRELATED_TRANSPORT_VAR="keep" RUNNER_TRACKING_ID="run-1"
DAEMON_CLAUDE_SETTINGS="$GW" DAEMON_CLAUDE_EFFORT=high run "$AGORA" spawn gwworker "GW-1" --group grp
assert_rc 0 "$RC" "gateway spawn exits 0"
G_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$G_UUID" settings)" "$GW" "DAEMON_CLAUDE_SETTINGS persisted as settings"
assert_equals "$(field "$G_UUID" effort)" "high" "DAEMON_CLAUDE_EFFORT persisted as effort"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--settings $GW --effort high" "gateway flags reach the launch"
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "base=http://gw;token=fixture-token" "gateway route keeps the transport env"
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "runner=;" "RUNNER_TRACKING_ID is always stripped"
run "$AGORA" spawn plain2 "PLAIN-2" --group grp
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "base=;token=;sub=;keep=keep;runner=;path=set" "plain route scrubs the gateway env keys, keeps PATH and unrelated vars"
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_SUBAGENT_MODEL UNRELATED_TRANSPORT_VAR RUNNER_TRACKING_ID

run "$AGORA" spawn wtworker "WT-1" --group grp --worktree "feat x"
assert_rc 0 "$RC" "worktree spawn exits 0"
WT_UUID="$(banner_uuid "$OUT")"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--worktree feat-x" "worktree name is sanitized"
assert_equals "$(field "$WT_UUID" cwd)" "$WORK/.claude/worktrees/feat-x" "cwd is the worktree path the harness reports"
assert_contains "$OUT" "worktree=" "banner notes the worktree"

# Live-name refusal: a live harness session already answering to the alias
# would make every SendMessage to it ambiguous — refuse before any side effect.
printf '{"pid":%s,"sessionId":"77777777-aaaa-4000-8000-000000000007","name":"taken","kind":"interactive","status":"idle","messagingSocketPath":"/nonexistent.sock"}\n' "$$" > "$HOME/.claude/sessions/$$.json"
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$AGORA" spawn taken "T" --group grp
assert_rc 4 "$RC" "spawn refuses an alias a live session already answers to"
assert_contains "$OUT" "live session already answers to 'taken'" "live-name refusal is explained"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no session is launched when the name is taken"
run "$AGORA" seat add grp taken
assert_rc 4 "$RC" "seat add refuses a live-held alias without --session"
run "$AGORA" seat add grp taken --session 77777777-aaaa-4000-8000-000000000007
assert_rc 0 "$RC" "seat add registers the very session that holds the name"
rm -f "$HOME/.claude/sessions/$$.json"
run "$AGORA" spawn researcher "OTHER" --group other
assert_rc 0 "$RC" "the same alias in another group is allowed when no live session holds it"
"$AGORA" remove other/researcher >/dev/null

# Lifecycle lock: a spawn of a seat whose lock another agora process holds is
# refused, never duplicated.
python3 - "$AGORA_HOME/locks/grp__locked.lock" <<'PY' &
import fcntl, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
HOLDER=$!
sleep 0.4
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$AGORA" spawn locked "L" --group grp
assert_rc 4 "$RC" "a spawn while the seat's lifecycle lock is held is refused"
assert_contains "$OUT" "being changed by another agora process" "lock refusal is explained"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no session is launched while the lock is held"
kill "$HOLDER" 2>/dev/null || true; wait "$HOLDER" 2>/dev/null || true

# ---- 5) sync (finalize) and blocked shapes -----------------------------------
echo "sync:"
run "$AGORA" sync waiter; assert_equals "$OUT" "noop" "sync on an idle seat is noop"
# The seat 'slow' is working with a live row (state running) → live.
run "$AGORA" sync slow; assert_equals "$OUT" "live" "sync on a running turn is live"
# Lingering finished shape: state=working + status=idle → done → idle.
SLOW_SHORT="$(field "$S_UUID" short)"
sed -i.bak 's/^state=.*/state=working/; s/^status=.*/status=idle/' "$STUB_STATE/agents/$SLOW_SHORT" && rm -f "$STUB_STATE/agents/$SLOW_SHORT.bak"
run "$AGORA" sync slow; assert_equals "$OUT" "idle" "lingering working+idle shape finalizes as idle"
assert_equals "$(field "$S_UUID" status)" "idle" "sync wrote status idle"
assert_file_exists "$AGORA_HOME/$S_UUID.reply.txt" "sync recorded the reply"
# absent: a working seat whose row is gone.
"$AGORA" mark slow working >/dev/null
rm -f "$STUB_STATE/agents/$SLOW_SHORT"
run "$AGORA" sync slow; assert_equals "$OUT" "absent" "sync with no harness row is absent"
assert_equals "$(field "$S_UUID" status)" "working" "absent leaves the record untouched"
# error: state failed.
{ echo "short=$SLOW_SHORT"; echo "uuid=$S_UUID"; echo "name=slow"; echo "state=failed"; echo "status="; echo "cwd=$WORK"; } > "$STUB_STATE/agents/$SLOW_SHORT"
run "$AGORA" sync slow; assert_equals "$OUT" "error" "a failed row finalizes as error"
assert_equals "$(field "$S_UUID" status)" "error" "sync wrote status error"

# Blocked on AskUserQuestion: the question lives in the tool_use input; the
# reply must render it and point at the answer path.
ASKQ_UUID="44444444-dddd-4000-8000-000000000004"
ASKQ_TX="$HOME/.claude/projects/fake-proj/$ASKQ_UUID.jsonl"
mkdir -p "$(dirname "$ASKQ_TX")"
python3 - "$ASKQ_TX" <<'PY'
import json, sys
row = {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Before I pick, one question."},
    {"type": "tool_use", "name": "AskUserQuestion",
     "input": {"questions": [{"question": "Which color should the widget be?",
                              "options": [{"label": "Red"}, {"label": "Blue"}]}]}}]}}
open(sys.argv[1], "w").write(json.dumps(row) + "\n")
PY
"$AGORA" seat add grp asker --session "$ASKQ_UUID" >/dev/null
"$AGORA" mark asker blocked >/dev/null
{ echo "short=aaaa0001"; echo "uuid=$ASKQ_UUID"; echo "name=asker"; echo "state=blocked"; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/aaaa0001"
run "$AGORA" sync asker; assert_equals "$OUT" "idle" "an ended blocked-shape turn finalizes as idle"
ASK_REPLY="$(cat "$AGORA_HOME/$ASKQ_UUID.reply.txt")"
assert_contains "$ASK_REPLY" "Which color should the widget be?" "pending AskUserQuestion surfaced in the reply"
assert_contains "$ASK_REPLY" "Red / Blue" "pending question options rendered"
assert_contains "$ASK_REPLY" "Before I pick, one question." "turn text still printed alongside the question"
assert_contains "$ASK_REPLY" "agora wake asker" "reply points at the answer path"
assert_not_contains "$ASK_REPLY" "blocked on a harness prompt" "a rendered question gets no harness-prompt marker"
PERM_UUID="55555555-eeee-4000-8000-000000000005"
python3 - "$HOME/.claude/projects/fake-proj/$PERM_UUID.jsonl" <<'PY'
import json, sys
open(sys.argv[1], "w").write(json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "About to ask something."}]}}) + "\n")
PY
"$AGORA" seat add grp permer --session "$PERM_UUID" >/dev/null
"$AGORA" mark permer blocked >/dev/null
{ echo "short=aaaa0002"; echo "uuid=$PERM_UUID"; echo "name=permer"; echo "state=blocked"; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/aaaa0002"
run "$AGORA" sync permer; assert_equals "$OUT" "idle" "blocked-without-question also finalizes idle"
assert_contains "$(cat "$AGORA_HOME/$PERM_UUID.reply.txt")" "blocked on a harness prompt" "blocked-without-question reply carries the harness-prompt marker"
run "$AGORA" sync --all
assert_contains "$OUT" "" "sync --all runs"
run "$AGORA" sync
assert_rc 0 "$RC" "bare sync = --all"

# ---- 6) wake / send over the inbox socket -----------------------------------
echo "wake / send:"
# A live peer record for the orchestrator seat: the socket server's pid is
# alive, its socket accepts connections.
printf '{"pid":%s,"sessionId":"%s","name":"my session","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$ORCH_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/$SOCK_PID.json"
run "$AGORA" send orchestrator "hello there"
assert_rc 0 "$RC" "send to a live seat exits 0"
assert_contains "$OUT" "sent to grp/orchestrator" "send reports the target"
sleep 0.2
assert_contains "$(cat "$RECEIVED")" '"type": "user"' "frame is the documented user-message shape"
assert_contains "$(cat "$RECEIVED")" '[agora message from human]\nhello there' "sender identity travels in the text's first line"
run "$AGORA" send scribe "x"
assert_rc 4 "$RC" "send to a vacant seat is refused (exit 4)"
assert_contains "$OUT" "agora wake" "send refusal points at wake"
run "$AGORA" send "my session" "by name" --from ops
assert_rc 0 "$RC" "send resolves a live harness session name when no seat matches"
sleep 0.2
assert_contains "$(cat "$RECEIVED")" '[agora message from ops]\nby name' "--from is honored"
run "$AGORA" send nobody-here "x"
assert_rc 4 "$RC" "send to an unknown target exits 4"
run "$AGORA" list grp
assert_contains "$OUT" "idle" "a seat with a live peer record shows idle"

run "$AGORA" wake orchestrator "wake up" --from boss
assert_rc 0 "$RC" "wake of a live seat exits 0"
assert_contains "$OUT" "via inbox socket" "live wake goes through the socket"
sleep 0.2
assert_contains "$(cat "$RECEIVED")" '[agora wake from boss id=' "wake frame carries the wake prefix, sender, and a message id"
assert_contains "$(cat "$RECEIVED")" ']\nwake up' "wake frame carries the message after the first line"
assert_equals "$(field "$ORCH_UUID" status)" "working" "wake stamps status working"
"$AGORA" mark orchestrator idle >/dev/null

# wake --wait needs EVIDENCE the message landed (the frame's id in the
# target's transcript, or a busy row) before it waits for a reply.
{ echo "short=orch0001"; echo "uuid=$ORCH_UUID"; echo "name=my session"; echo "kind=interactive"; echo "state="; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/orch0001"
AGORA_ACK_TIMEOUT=0.4 run "$AGORA" wake orchestrator "ACK-0" --wait
assert_rc 1 "$RC" "wake --wait without evidence of receipt exits 1"
assert_not_contains "$OUT" "--- reply ---" "no reply block is printed without evidence"
"$AGORA" mark orchestrator idle >/dev/null
( AGORA_ACK_TIMEOUT=5 "$AGORA" wake orchestrator "ACK-1" --wait > "$TEST_ROOT/ack.out" 2>&1; echo $? > "$TEST_ROOT/ack.rc" ) &
ACKW=$!
sleep 0.5
ACK_ID="$(grep -o 'id=[0-9a-f]\{8\}' "$RECEIVED" | tail -1 | cut -d= -f2)"
mkdir -p "$HOME/.claude/projects/fake-proj"
python3 - "$HOME/.claude/projects/fake-proj/$ORCH_UUID.jsonl" "$ACK_ID" <<'PY'
import json, sys
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "[agora wake from human id=%s]\nACK-1" % sys.argv[2]}}) + "\n")
    f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ACKED " + sys.argv[2]}]}}) + "\n")
PY
wait "$ACKW" || true
assert_equals "$(cat "$TEST_ROOT/ack.rc")" "0" "wake --wait exits 0 once the marker appears in the transcript"
assert_contains "$(cat "$TEST_ROOT/ack.out")" "--- reply ---" "acknowledged wake --wait prints the reply block"
assert_contains "$(cat "$TEST_ROOT/ack.out")" "ACKED $ACK_ID" "acknowledged wake --wait prints the turn's reply"

# Resume branch: 'researcher' has a session but no live peer → --bg --resume.
run "$AGORA" wake researcher "again please"
assert_rc 0 "$RC" "wake of a stopped seat exits 0"
assert_contains "$OUT" "via --bg --resume" "stopped wake resumes the session"
assert_contains "$(grep -- '--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)" "--resume $R_UUID --permission-mode auto -n researcher" "resume argv continues the recorded session under the alias"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "same-id resume keeps current"
assert_equals "$(field "$R_UUID" turns)" "2" "resume increments turns"
if [ "$(field "$R_UUID" short)" != "$R_SHORT" ]; then pass "resume records the new background short"; else fail "resume records the new background short"; fi
assert_equals "$(field "$R_UUID" status)" "idle" "a resume whose turn already ended records idle"
run "$AGORA" wake researcher "with reply" --wait
assert_contains "$OUT" "--- reply ---" "wake --wait prints the reply block"
assert_contains "$OUT" "RESUMED:$R_UUID" "wake --wait prints the resumed turn's reply"
STUB_RESUME_COPY=1 run "$AGORA" wake researcher "copy?"
assert_rc 1 "$RC" "a resume that started a copy fails loudly"
assert_contains "$OUT" "started a COPY" "copy detection is explained"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "the record is left untouched after a copy"
assert_equals "$(field "$R_UUID" status)" "idle" "status is restored after a copy"
COPY_SHORT="$(printf '%08x' "$(cat "$STUB_STATE/counter")")"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop $COPY_SHORT" "the copy is stopped"

# ---- 6b) resume: process-level continuation ---------------------------------
echo "resume:"
run "$AGORA" resume plainworker "RES-1"
assert_rc 0 "$RC" "resume exits 0"
assert_contains "$OUT" "resumed work/plainworker" "resume reports the seat"
assert_contains "$(grep -- '--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)" "--resume $P_UUID --permission-mode auto -n plainworker" "resume continues the recorded session"
assert_equals "$(field "$P_UUID" turns)" "2" "resume increments turns"
assert_equals "$(field "$P_UUID" current)" "$P_UUID" "same-id resume keeps current"
P_SHORT="$(field "$P_UUID" short)"
sed -i.bak 's/^state=.*/state=working/; s/^status=.*/status=busy/' "$STUB_STATE/agents/$P_SHORT" && rm -f "$STUB_STATE/agents/$P_SHORT.bak"
run "$AGORA" resume plainworker "RES-2"
assert_rc 0 "$RC" "resume of a live turn exits 0"
assert_contains "$(grep -E '^(stop|--bg)' "$STUB_STATE/log/calls.log" | tail -2 | head -1)" "stop $P_SHORT" "a live turn is stopped before the resume"
run "$AGORA" resume plainworker "RES-4" --wait
assert_rc 0 "$RC" "resume --wait exits 0"
assert_contains "$OUT" "--- reply ---" "resume --wait prints the reply block"
assert_contains "$OUT" "RESUMED:$P_UUID:ANSWER:RES-4" "resume --wait prints the resumed turn's reply"
run "$AGORA" wake scribe "x"
assert_rc 4 "$RC" "waking a vacant seat exits 4"
assert_contains "$OUT" "agora fill" "vacant wake points at fill"
# Resume lock: a resume already in flight refuses a twin.
python3 - "$AGORA_HOME/$R_UUID.resume.lock" <<'PY' &
import fcntl, sys, time
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
LOCKER=$!
sleep 0.4
run "$AGORA" wake researcher "twin"
assert_rc 1 "$RC" "a second resume while one is in flight is refused"
assert_contains "$OUT" "already in flight" "twin refusal is explained"
kill "$LOCKER" 2>/dev/null || true; wait "$LOCKER" 2>/dev/null || true

# ---- 7) retire / fill --------------------------------------------------------
echo "retire / fill:"
run "$AGORA" retire researcher
assert_rc 0 "$RC" "retire exits 0"
assert_equals "$(field "$R_UUID" status)" "retired" "retire marks the seat retired"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop $(field "$R_UUID" short)" "retire stops the current turn"
assert_contains "$OUT" "agora fill grp/researcher --resume" "retire hints at re-filling"
run "$AGORA" fill researcher "FRESH-START"
assert_rc 0 "$RC" "fresh fill exits 0"
assert_contains "$OUT" "seat filled: grp/researcher" "fill reports the seat"
NEWCUR="$(field "$R_UUID" current)"
if [ "$NEWCUR" != "$R_UUID" ]; then pass "fresh fill gives the seat a new session while keeping the seat id"; else fail "fresh fill gives the seat a new session while keeping the seat id"; fi
assert_not_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--resume" "fresh fill does not resume"
assert_contains "$(field "$R_UUID" task)" 'You are seat "researcher"' "fresh fill re-renders the preamble for a wired seat"
assert_contains "$(field "$R_UUID" task)" "FRESH-START" "fresh fill carries the new task"
assert_equals "$(field "$R_UUID" turns)" "1" "fresh fill resets turns"
run "$AGORA" fill researcher "CONTINUE" --resume
assert_rc 0 "$RC" "fill --resume exits 0"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--resume $NEWCUR" "fill --resume continues the current session"
printf '{"pid":%s,"sessionId":"%s","name":"researcher","kind":"bg","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$(field "$R_UUID" current)" "$SOCK" > "$HOME/.claude/sessions/live-researcher.json"
run "$AGORA" fill researcher "x"
assert_rc 4 "$RC" "filling a live seat is refused"
rm -f "$HOME/.claude/sessions/live-researcher.json"
run "$AGORA" retire waiter --purge
assert_rc 0 "$RC" "retire --purge exits 0"
assert_file_absent "$AGORA_HOME/$W_UUID.json" "purge removes the record"
assert_file_absent "$AGORA_HOME/$W_UUID.reply.txt" "purge removes the reply"
run "$AGORA" retire wtworker
assert_contains "$OUT" "branch worktree-feat-x" "retiring a worktree'd seat notes the branch"

# ---- 8) mark / status / meta / attach ----------------------------------------
echo "mark / status / meta / attach:"
run "$AGORA" mark plainworker awaiting-human tone is a user call
assert_rc 0 "$RC" "mark exits 0"
assert_equals "$(field "$P_UUID" status)" "awaiting-human" "mark sets the judgment status"
assert_equals "$(field "$P_UUID" note)" "tone is a user call" "mark records the note"
run "$AGORA" status plainworker "drafting the outline"
assert_equals "$(field "$P_UUID" now)" "drafting the outline" "status writes the now line"
run "$AGORA" list work
assert_contains "$OUT" "drafting the outline" "list shows the now line"
run "$AGORA" meta get plainworker now
assert_equals "$OUT" "drafting the outline" "meta get reads a field"
run "$AGORA" meta set plainworker lane implement
assert_equals "$(field "$P_UUID" lane)" "implement" "meta set writes a field"
printf '{"uuid":"%s","name":"bearer-one","status":"working","run_bearer":"tok-fake"}' "66666666-ffff-4000-8000-000000000006" > "$AGORA_HOME/66666666-ffff-4000-8000-000000000006.json"
chmod 600 "$AGORA_HOME/66666666-ffff-4000-8000-000000000006.json"
chmod 640 "$AGORA_HOME/$P_UUID.json"
"$AGORA" mark bearer-one blocked >/dev/null
"$AGORA" mark plainworker blocked >/dev/null
assert_equals "$(mode_of "$AGORA_HOME/66666666-ffff-4000-8000-000000000006.json")" "0600" "a bearer-carrying record stays 0600 across writes"
assert_equals "$(mode_of "$AGORA_HOME/$P_UUID.json")" "0640" "a plain record keeps its existing mode"
"$AGORA" remove bearer-one >/dev/null
run "$AGORA" attach plainworker
assert_contains "$OUT" "claude attach $(field "$P_UUID" short)" "attach prints the harness command when not a TTY"
run "$AGORA" mark nope idle
assert_rc 4 "$RC" "an unknown seat exits 4"
run "$AGORA" mark "$(printf '%s' "$P_UUID" | cut -c1-8)" idle
assert_rc 0 "$RC" "a seat id prefix resolves"
run "$AGORA" mark "$(field "$P_UUID" short)" idle
assert_rc 0 "$RC" "a current short id resolves"

# ---- 9) views: tree, dangling, topology, groups ------------------------------
echo "views:"
"$AGORA" seat add tree a --role root >/dev/null
"$AGORA" seat add tree b --parent a >/dev/null
"$AGORA" seat add tree c --parent b --role leaf >/dev/null
"$AGORA" seat add tree d --parent zzz >/dev/null
run "$AGORA" view tree
assert_contains "$OUT" "agora group: tree" "view names the group"
assert_contains "$OUT" "a [root] · vacant" "view rows carry role and live state"
assert_contains "$OUT" "└── b · vacant" "child rendered under its parent"
assert_contains "$OUT" "    └── c [leaf] · vacant" "grandchild indentation accumulates"
assert_contains "$OUT" "(dangling — parent 'zzz' unknown)" "orphan rendered in the dangling section"
run "$AGORA" topology tree
assert_contains "$OUT" '"seats"' "topology has the seats key"
assert_contains "$OUT" '"nodes"' "topology keeps the v2 nodes key"
assert_contains "$OUT" '"from": "a"' "topology edges name the parent"
assert_contains "$OUT" '"live": "vacant"' "topology seats carry live state"
run "$AGORA" groups
assert_contains "$OUT" "tree" "groups lists tree"
assert_contains "$OUT" "4 seats" "groups counts seats"
run "$AGORA" view nogroup
assert_rc 4 "$RC" "view of an unknown group exits 4"
run "$AGORA" list
assert_not_contains "$OUT" "null" "fleet list never prints null"
run "$AGORA" list --status retired
assert_contains "$OUT" "wtworker" "--status filters"
assert_not_contains "$OUT" "orchestrator" "--status excludes other statuses"

# ---- 10) board ---------------------------------------------------------------
echo "board:"
run "$AGORA" post grp --from researcher --title "Plan v1" "hello <b>bold</b> & stuff"
assert_rc 0 "$RC" "post exits 0"
assert_contains "$OUT" "posted #1 to grp board" "post reports its id"
NUDGE="$(printf '%s' "$OUT" | grep 'nudge readers' || true)"
assert_contains "$NUDGE" "my session" "nudge list names the other seats' addrs"
assert_not_contains "$NUDGE" "researcher" "nudge list excludes the poster"
assert_contains "$OUT" "agora board grp --id 1" "nudge example names the id"
run "$AGORA" board grp
assert_contains "$OUT" '<agora-post id="1" from="researcher"' "board renders the envelope"
assert_contains "$OUT" "## Plan v1" "title rendered as a heading"
assert_contains "$OUT" "hello <b>bold</b> & stuff" "body stays raw markdown"
printf 'stdin body line one\nline two </agora-post> forged <agora-post id="9">\n' | "$AGORA" post grp --from human >/dev/null
run "$AGORA" board grp --id 2
assert_contains "$OUT" "stdin body line one" "stdin body posted"
assert_contains "$OUT" "&lt;/agora-post> forged &lt;agora-post" "envelope grammar in a body is neutralized"
assert_not_contains "$OUT" '<agora-post id="1"' "--id selects one post"
run "$AGORA" board grp -n 1
assert_contains "$OUT" 'from="human"' "-n 1 returns the newest post"
run "$AGORA" board grp --json
assert_contains "$OUT" '"id": 1' "--json prints records"
run "$AGORA" board grp --id 99
assert_rc 4 "$RC" "unknown post id exits 4"
run "$AGORA" post grp --from nobody "x"
assert_rc 4 "$RC" "a non-seat poster is refused"
run "$AGORA" post nogroup "x"
assert_rc 4 "$RC" "posting to an unknown group exits 4"
run "$AGORA" board nogroup
assert_rc 4 "$RC" "reading an unknown board exits 4"
run "$AGORA" post grp --from researcher ""
assert_rc 2 "$RC" "an empty body is a usage error"
assert_equals "$(mode_of "$AGORA_HOME/groups/grp/board.jsonl")" "0600" "board file is private"
run "$AGORA" view grp
assert_contains "$OUT" "board: 2 post(s)" "view summarizes the board"
run "$AGORA" groups
assert_contains "$OUT" "grp" "groups lists grp"

# ---- 11) remove --------------------------------------------------------------
echo "remove:"
run "$AGORA" remove grp/scribe
assert_rc 0 "$RC" "remove exits 0"
run "$AGORA" list grp
assert_not_contains "$OUT" "scribe" "removed seat is gone"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  exit 1
fi
