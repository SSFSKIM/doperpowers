#!/usr/bin/env bash
#
# Hermetic tests for the sminos CLI (skills/sminos/scripts/sminos → sminos.py).
#
# sminos shells out to the real `claude` CLI (--bg [--resume] / agents --json /
# stop / rm) and reads the harness's peer registry (~/.claude/sessions/*.json)
# and inbox sockets. To stay deterministic, offline, and free of real sessions,
# this suite puts a STUB `claude` first on PATH (coloured bg banner, agents
# --json rows from a state dir, transcript files, same-id --resume, stop/rm),
# redirects HOME and SMINOS_HOME to temp dirs, and runs a tiny unix-socket
# server standing in for a live session's inbox. Every test drives the real
# CLI and asserts on the registry, replies, frames, and rendered views.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SMINOS="$REPO_ROOT/skills/sminos/scripts/sminos"

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
  python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); v = d.get(sys.argv[2], ""); print(v if isinstance(v, str) else json.dumps(v))' "$SMINOS_HOME/$1.json" "$2"
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
        break' "$SMINOS_HOME" "$1"
}
banner_uuid() { printf '%s' "$1" | sed -n 's/.*\[[0-9a-f]* \/ \([0-9a-f-]*\)\].*/\1/p' | head -1; }
banner_short() { printf '%s' "$1" | sed -n 's/.*\[\([0-9a-f]*\) \/ [0-9a-f-]*\].*/\1/p' | head -1; }

# ---- environment: isolated HOME, registry, PATH-shadowed claude stub ---------
# The transport env starts EMPTY: the stub snapshots exactly these names into
# calls.log and assertion failures print that log, so a real credential in the
# runner's shell must never reach it.
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_SUBAGENT_MODEL UNRELATED_TRANSPORT_VAR
unset DAEMON_CLAUDE_SETTINGS DAEMON_CLAUDE_EFFORT SMINOS_ALIAS RUNNER_TRACKING_ID DAEMON_HOME
# The harness exports CLAUDE_CODE_SESSION_ID to Bash tools; sminos derives the
# sender identity from it. The suite is "a real terminal" unless a case sets it.
unset CLAUDE_CODE_SESSION_ID
lock_file() { printf '%s/locks/name__%s.lock' "$SMINOS_HOME" "$(printf '%s' "$1" | python3 -c 'import hashlib,sys; print(hashlib.sha1(sys.stdin.read().encode()).hexdigest())')"; }
export HOME="$TEST_ROOT/home"
export SMINOS_HOME="$TEST_ROOT/registry"
export STUB_STATE="$TEST_ROOT/stub"
export SMINOS_POLL_INTERVAL=0.05
export DAEMON_TIMEOUT=10
export SMINOS_UUID_POLL=5
export DAEMON_BOOT_ID="boot-current"
export DAEMON_HOST="testhost"
export SMINOS_NO_EXEC=1
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
    # STUB_AGENTS_FAIL=1: the harness itself fails (distinct from an empty fleet).
    [ "${STUB_AGENTS_FAIL:-0}" = "1" ] && { echo "stub: agents unavailable" >&2; exit 1; }
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
    # STUB_STOP_FAIL=1: the supervisor refuses. STUB_STOP_NOOP=1: it accepts
    # but the turn keeps running (the row never leaves state=working).
    [ "${STUB_STOP_FAIL:-0}" = "1" ] && { echo "stub: stop refused" >&2; exit 1; }
    f="$STUB_STATE/agents/${2:-}"
    if [ -f "$f" ] && [ "${STUB_STOP_NOOP:-0}" != "1" ]; then sed -i.bak 's/^state=.*/state=stopped/' "$f" && rm -f "$f.bak"; fi
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
  # `--bg --resume <id>` with NO other flag wakes the session itself (same
  # id, same short, its saved options). Any additional flag makes the real
  # harness start a COPY under a new id and say so (observed live, v2.1.257);
  # STUB_RESUME_COPY=1 forces that copy-with-note path, =2 a silent copy.
  if [ -n "$resume_uuid" ]; then
    extra=0; k=0
    while [ $k -lt $((${#args[@]} - 1)) ]; do
      case "${args[$k]}" in --bg|--resume) ;; "$resume_uuid") ;; *) extra=1 ;; esac
      k=$((k + 1))
    done
    oldfile="$(grep -l "^uuid=$resume_uuid$" "$STUB_STATE/agents"/* 2>/dev/null | head -1 || true)"
    oldshort="${oldfile##*/}"
    if [ $extra -eq 1 ] || [ "${STUB_RESUME_COPY:-0}" = "1" ]; then
      echo "note: background session ${oldshort:-????????} keeps its own saved options, so the flags you passed started a copy as $short. Without flags, the same command continues ${oldshort:-????????} itself."
    elif [ "${STUB_RESUME_COPY:-0}" = "2" ]; then
      :
    else
      uuid="$resume_uuid"
      if [ -n "$oldfile" ]; then short="$oldshort"; name="$(sed -n 's/^name=//p' "$oldfile")"; fi
      echo "note: woke session $short with its saved options (--permission-mode, -n, --model)."
    fi
  fi
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
# Stand-in for the `codex` CLI's `queue` verb, in its own PATH dir so one case
# can run without it. It knows the threads listed in $STUB_STATE/codex-threads
# (one "<uuid> <name>" per line), appends every accepted message to
# codex-queue.log, and answers like the real CLI. It shadows any real codex:
# the real one would spin up an app-server under the test HOME.
CODEX_BIN="$TEST_ROOT/bin-codex"
mkdir -p "$CODEX_BIN"
cat > "$CODEX_BIN/codex" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$STUB_STATE/log/calls.log"
[ "${1:-}" = "queue" ] || { echo "stub: unhandled codex invocation: $*" >&2; exit 1; }
thread=""; message=""
while [ $# -gt 0 ]; do
  case "$1" in
    --thread) thread="$2"; shift ;;
    --message) message="$2"; shift ;;
  esac
  shift
done
[ "${STUB_CODEX_FAIL:-0}" = "1" ] && { echo "Error: failed to queue session message: app server exploded" >&2; exit 1; }
tid="$(awk -v q="$thread" '$1 == q || substr($0, length($1) + 2) == q { print $1; exit }' "$STUB_STATE/codex-threads" 2>/dev/null || true)"
if [ -z "$tid" ]; then
  echo "Error: No active session found matching '$thread'." >&2; exit 1
fi
printf '%s\t%s\n' "$tid" "$message" >> "$STUB_STATE/log/codex-queue.log"
echo "Queued message 01a0aaaa-0000-7000-8000-000000000001 for thread $tid."
STUB
chmod +x "$CODEX_BIN/codex"
export PATH="$STUB_BIN:$CODEX_BIN:$PATH"

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

if [[ "${SMINOS_FAMILY_ONLY:-0}" != 1 ]]; then
# ---- 1) usage ----------------------------------------------------------------
echo "usage:"
run "$SMINOS"; assert_rc 2 "$RC" "no arguments is a usage error (exit 2)"
run "$SMINOS" help; assert_rc 0 "$RC" "help exits 0"; assert_contains "$OUT" "sminos spawn" "help lists the verbs"
run "$SMINOS" listen grp x; assert_rc 2 "$RC" "listen is refused"; assert_contains "$OUT" "sminos send" "listen refusal points at sminos send"
run "$SMINOS" bogus; assert_rc 2 "$RC" "unknown command is a usage error"
run "$SMINOS" seat; assert_rc 2 "$RC" "bare 'seat' is a usage error"

# ---- 2) migration ------------------------------------------------------------
# Runs only when the DEFAULT root is in use: a separate HOME with the old
# daemon registry, an sminos v2 group, and a record lacking `group`.
echo "migration:"
MH="$TEST_ROOT/mighome"
OLD="$MH/.claude/orchestrating-daemons"
NEW="$MH/.claude/sminos"
mkdir -p "$OLD/board-claims" "$NEW/groups/demo/nodes"
OLD_UUID="11111111-aaaa-4000-8000-000000000001"
printf '{"uuid":"%s","name":"old-worker","status":"idle","current":"%s","cwd":"%s","ticket":"42","task":"legacy"}\n' \
  "$OLD_UUID" "$OLD_UUID" "$WORK" > "$OLD/$OLD_UUID.json"
printf 'legacy reply\n' > "$OLD/$OLD_UUID.reply.txt"
printf '{}' > "$OLD/board-claims/7.json"
printf '{"alias":"scout","parent":"orchestrator","addr":"scout","session":"22222222-bbbb-4000-8000-000000000002","cwd":"/x","branch":"","desc":"scouts ahead","joined":"2026-01-01T00:00:00Z","updated":"2026-01-01T00:00:00Z"}\n' \
  > "$NEW/groups/demo/nodes/scout.json"
# A sessionless v2 node: its seat id is derived, and the derivation is pinned below.
printf '{"alias":"nosess","parent":"","addr":"nosess","session":"","cwd":"/n","branch":"","desc":"no session","joined":"2026-01-01T00:00:00Z","updated":"2026-01-01T00:00:00Z"}\n' \
  > "$NEW/groups/demo/nodes/nosess.json"
CODEX_UUID="12121212-abab-4000-8000-000000000012"
printf '{"uuid":"%s","name":"codexy","status":"idle","current":"%s","cwd":"%s","engine":"codex","pid":"99999","event_log":"/x.events.jsonl","updated":"2026-07-09T09:09:09Z"}\n' \
  "$CODEX_UUID" "$CODEX_UUID" "$WORK" > "$OLD/$CODEX_UUID.json"
# Duplicate (group, alias): the old substrate respawned workers under one name.
DUP_OLD="e1e1e1e1-abab-4000-8000-0000000e1e11"; DUP_NEW="e2e2e2e2-abab-4000-8000-0000000e2e22"
printf '{"uuid":"%s","name":"review-pr-470","group":"fleet","status":"idle","current":"%s","short":"aaaa1111","updated":"2026-07-11T10:00:00Z"}\n' "$DUP_OLD" "$DUP_OLD" > "$OLD/$DUP_OLD.json"
printf '{"uuid":"%s","name":"review-pr-470","group":"fleet","status":"idle","current":"%s","short":"bbbb2222","updated":"2026-07-11T12:00:00Z"}\n' "$DUP_NEW" "$DUP_NEW" > "$OLD/$DUP_NEW.json"
# A codex record with a NEWER updated must not win the alias over a claude record.
DUP_CX="e3e3e3e3-abab-4000-8000-0000000e3e33"
printf '{"uuid":"%s","name":"review-pr-470","group":"fleet","status":"idle","current":"%s","short":"cccc3333","engine":"codex","pid":"99999","updated":"2026-07-12T00:00:00Z"}\n' "$DUP_CX" "$DUP_CX" > "$OLD/$DUP_CX.json"
# A working codex record whose pid is alive is left alone by migration.
CX_LIVE="e4e4e4e4-abab-4000-8000-0000000e4e44"
printf '{"uuid":"%s","name":"cx-live","group":"fleet","status":"working","current":"%s","engine":"codex","pid":"%s","updated":"2026-07-10T00:00:00Z"}\n' "$CX_LIVE" "$CX_LIVE" "$$" > "$OLD/$CX_LIVE.json"
# The same session id joined two v2 groups: the second node must not overwrite the first's seat.
mkdir -p "$NEW/groups/other/nodes"
printf '{"alias":"scout2","parent":"","addr":"scout2","session":"22222222-bbbb-4000-8000-000000000002","cwd":"/y","branch":"","desc":"other side","joined":"2026-01-01T00:00:00Z","updated":"2026-01-01T00:00:00Z"}\n' \
  > "$NEW/groups/other/nodes/scout2.json"
chmod 755 "$OLD"; chmod 644 "$OLD/$OLD_UUID.json"   # the old substrate's wide modes
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list
assert_rc 0 "$RC" "first command against the default root migrates and lists"
if [ -L "$OLD" ]; then pass "old daemon root became a symlink"; else fail "old daemon root became a symlink"; fi
assert_file_exists "$NEW/$OLD_UUID.json" "daemon meta moved into the new root"
assert_file_exists "$NEW/$OLD_UUID.reply.txt" "reply file moved"
assert_file_exists "$NEW/board-claims/7.json" "pipeline sibling dir moved intact"
assert_contains "$(cat "$NEW/$OLD_UUID.json")" '"group": "work"' "record lacking group is stamped from its cwd (dir basename)"
assert_contains "$(cat "$NEW/$OLD_UUID.json")" '"ticket": "42"' "pipeline fields survive the stamp"
assert_file_absent "$NEW/groups/demo/nodes" "v2 nodes dir converted away"
assert_file_exists "$NEW/22222222-bbbb-4000-8000-000000000002.json" "v2 node became a seat keyed by its session"
# The derived id keeps the tool's former name in its namespace: a conversion
# interrupted before the rename already wrote a seat under this very id.
NOSESS_ID="$(python3 -c 'import uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "agora:demo/nosess"))')"
assert_file_exists "$NEW/$NOSESS_ID.json" "a sessionless v2 node keeps its pre-rename deterministic seat id"
assert_contains "$(cat "$NEW/22222222-bbbb-4000-8000-000000000002.json")" '"brief": "scouts ahead"' "v2 desc became brief"
assert_contains "$(cat "$NEW/22222222-bbbb-4000-8000-000000000002.json")" '"status": "retired"' "converted seat is retired"
assert_contains "$OUT" "old-worker" "migrated daemon listed as a seat"
assert_contains "$OUT" "scout" "converted node listed as a seat"
assert_not_contains "$OUT" "null" "list never prints null for pre-seat records"
assert_contains "$(cat "$NEW/$CODEX_UUID.json")" '"status": "retired"' "legacy codex records are retired by migration"
assert_not_contains "$OUT" "killed" "migration does not signal legacy codex pids"
assert_contains "$(cat "$NEW/$DUP_OLD.json")" '"alias": "review-pr-470@aaaa1111"' "the older duplicate is renamed alias@short"
assert_contains "$(cat "$NEW/$DUP_OLD.json")" '"status": "retired"' "the older duplicate is retired"
assert_contains "$(cat "$NEW/$DUP_OLD.json")" '"name": "review-pr-470"' "dedupe leaves the pipeline's name field untouched"
assert_not_contains "$(cat "$NEW/$DUP_NEW.json")" '"alias": "review-pr-470@' "the newest duplicate keeps the alias"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["updated"])' "$NEW/$DUP_OLD.json")" "2026-07-11T10:00:00Z" "a demoted duplicate keeps its original updated"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("updated",""))' "$NEW/$CODEX_UUID.json")" "2026-07-09T09:09:09Z" "a retired codex record keeps its original updated"
assert_contains "$(cat "$NEW/$DUP_CX.json")" '"alias": "review-pr-470@cccc3333"' "a codex record never wins an alias over a claude record"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$NEW/$CX_LIVE.json")" "working" "a working codex record with a live pid is left as is"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$NEW/$DUP_NEW.json")" "idle" "the newest duplicate keeps its status"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" view other
assert_contains "$OUT" "scout2" "a second group's node sharing a session id still converts"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" view demo
assert_contains "$OUT" "scout" "the first group's node keeps its seat"
assert_equals "$(mode_of "$NEW")" "0700" "migration tightens a 0755 root to 0700"
assert_equals "$(mode_of "$NEW/$OLD_UUID.json")" "0600" "migration tightens a 0644 record to 0600"
rm "$MH/.claude/orchestrating-daemons"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list
if [ -L "$MH/.claude/orchestrating-daemons" ]; then pass "a missing legacy symlink is recreated on the next run"; else fail "a missing legacy symlink is recreated on the next run"; fi
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list
assert_contains "$(cat "$NEW/$DUP_OLD.json")" '"alias": "review-pr-470@aaaa1111"' "dedupe is idempotent (no alias@short@short)"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" wake codexy "x"
assert_rc 4 "$RC" "wake refuses a legacy codex record"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" resume codexy "x"
assert_rc 4 "$RC" "resume refuses a legacy codex record"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" fill codexy "x"
assert_rc 4 "$RC" "fill refuses a legacy codex record"
if ls -d "$MH/.claude/sminos.v2-"* >/dev/null 2>&1; then fail "the set-aside v2 root is removed once merged"; else pass "the set-aside v2 root is removed once merged"; fi
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" migrate
assert_rc 0 "$RC" "explicit migrate exits 0 when nothing is left to do"
assert_equals "$OUT" "" "explicit migrate is silent when it did nothing"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" migrate --quiet
assert_rc 0 "$RC" "migrate --quiet is accepted"
# The root's former name: a machine that ran sminos as `agora` has a real
# ~/.claude/agora holding v3 records, with the daemon-era path already a symlink
# into it. That root is renamed into place and the old path becomes a symlink,
# so a still-cached older plugin keeps resolving it.
AH="$TEST_ROOT/agorahome"
mkdir -p "$AH/.claude/agora/groups/g1"
ln -s "$AH/.claude/agora" "$AH/.claude/orchestrating-daemons"
V3_UUID="33333333-cccc-4000-8000-000000000003"
printf '{"uuid":"%s","alias":"keeper","name":"keeper","group":"g1","status":"idle","current":"%s","cwd":"/k","updated":"2026-09-01T00:00:00Z"}\n' "$V3_UUID" "$V3_UUID" > "$AH/.claude/agora/$V3_UUID.json"
run env -u SMINOS_HOME HOME="$AH" "$SMINOS" list
assert_rc 0 "$RC" "a root under the former name migrates on the first command"
assert_contains "$OUT" "keeper" "the former root's seats are listed"
assert_file_exists "$AH/.claude/sminos/$V3_UUID.json" "the former root was renamed into place"
if [ -L "$AH/.claude/agora" ] && [ "$(readlink "$AH/.claude/agora")" = "$AH/.claude/sminos" ]; then pass "the former path is a symlink to the root"; else fail "the former path is a symlink to the root"; fi
if [ -L "$AH/.claude/orchestrating-daemons" ]; then pass "the daemon-era symlink is left alone"; else fail "the daemon-era symlink is left alone"; fi
# A real directory recreated at the former path (an older consumer's mkdir -p
# landing in the cutover gap) must never displace a root that holds records.
rm "$AH/.claude/agora"; mkdir "$AH/.claude/agora"
run env -u SMINOS_HOME HOME="$AH" "$SMINOS" list
assert_contains "$OUT" "keeper" "a directory recreated at the former path does not displace the root"
assert_file_exists "$AH/.claude/sminos/$V3_UUID.json" "the record-holding root stays where it is"
if [ -L "$AH/.claude/agora" ]; then pass "the recreated directory is folded away and the symlink restored"; else fail "the recreated directory is folded away and the symlink restored"; fi
if ls -d "$AH/.claude/sminos.v2-"* >/dev/null 2>&1; then fail "an empty recreated directory leaves no aside behind"; else pass "an empty recreated directory leaves no aside behind"; fi
# The migration lock keeps the former name so a cached older binary and this one
# serialise on the same file during the upgrade.
assert_file_exists "$AH/.claude/.agora-migrate.lock" "the migration lock is the one older agora binaries take"
# A recreated former root that an older plugin already WROTE INTO — a seat and
# its flock file — is merged, not stranded: the seat surfaces in the fleet.
rm "$AH/.claude/agora"; mkdir "$AH/.claude/agora"
LATE_UUID="44444444-dddd-4000-8000-000000000004"
printf '{"uuid":"%s","alias":"latecomer","name":"latecomer","group":"g1","status":"idle","current":"%s","cwd":"/l","updated":"2026-09-04T00:00:00Z"}\n' "$LATE_UUID" "$LATE_UUID" > "$AH/.claude/agora/$LATE_UUID.json"
printf 'late reply\n' > "$AH/.claude/agora/$LATE_UUID.reply.txt"
: > "$AH/.claude/agora/.metalock"
run env -u SMINOS_HOME HOME="$AH" "$SMINOS" list
assert_rc 0 "$RC" "a recreated former root holding a seat migrates cleanly"
assert_file_exists "$AH/.claude/sminos/$LATE_UUID.json" "a seat written into the recreated former root moves into the root"
assert_file_exists "$AH/.claude/sminos/$LATE_UUID.reply.txt" "its reply file moves with it"
assert_contains "$OUT" "latecomer" "the merged seat is listed"
assert_contains "$OUT" "keeper" "the root's own seats are untouched by the merge"
assert_not_contains "$OUT" "unmerged aside entry" "a colliding flock file is dropped, not reported"
if ls -d "$AH/.claude/sminos.v2-"* >/dev/null 2>&1; then fail "the merged aside is removed"; else pass "the merged aside is removed"; fi
if [ -L "$AH/.claude/agora" ]; then pass "the former path is a symlink again after the merge"; else fail "the former path is a symlink again after the merge"; fi
# A leftover $AGORA_HOME would aim every consumer at a fresh, empty registry:
# refuse it outright rather than let dispatchers launch over live seats.
run env -u SMINOS_HOME AGORA_HOME="$AH/.claude/sminos" HOME="$AH" "$SMINOS" list
assert_rc 2 "$RC" "a stale AGORA_HOME is refused (exit 2)"
assert_contains "$OUT" "SMINOS_HOME" "the refusal names the knob that replaced it"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list
assert_rc 0 "$RC" "migration is idempotent (second run exits 0)"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" view demo
assert_not_contains "$OUT" "null" "view never prints null for a converted node"
assert_contains "$OUT" "dangling — parent 'orchestrator' unknown" "converted node with unknown parent renders in the dangling section"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" topology work
assert_not_contains "$OUT" "null" "topology never prints null for a v1-shaped record"
assert_contains "$OUT" '"addr": "old-worker"' "topology falls back addr → alias → name"

# ---- 3) seats: validation and vacant/registered seats ------------------------
echo "seat add:"
run "$SMINOS" seat add grp "bad/alias"; assert_rc 2 "$RC" "alias with a slash is rejected"
run "$SMINOS" seat add grp ".."; assert_rc 2 "$RC" "'..' is rejected as an alias"
run "$SMINOS" seat add grp human; assert_rc 2 "$RC" "'human' is reserved"
run "$SMINOS" seat add "../grp" x; assert_rc 2 "$RC" "group name with traversal is rejected"
ORCH_UUID="33333333-cccc-4000-8000-000000000003"
run "$SMINOS" seat add grp orchestrator --role lead --session "$ORCH_UUID" --addr "my session"
assert_rc 0 "$RC" "registering an existing session as a seat"
assert_file_exists "$SMINOS_HOME/$ORCH_UUID.json" "a registered session's seat is keyed by its session id"
assert_equals "$(field "$ORCH_UUID" addr)" "my session" "--addr is stored (not name-validated)"
assert_equals "$(field "$ORCH_UUID" role)" "lead" "--role is stored"
assert_equals "$(field "$ORCH_UUID" status)" "idle" "a registered session starts idle"
assert_equals "$(mode_of "$SMINOS_HOME/$ORCH_UUID.json")" "0600" "seat records are private (umask 077)"
assert_equals "$(mode_of "$SMINOS_HOME")" "0700" "the registry root is private"
run "$SMINOS" seat add grp scribe --role writer --parent orchestrator --brief "keeps notes"
assert_rc 0 "$RC" "adding a vacant seat"
assert_contains "$OUT" "vacant" "vacant seat reported"
run "$SMINOS" list grp
assert_contains "$OUT" "vacant" "list shows the vacant seat's live state"
assert_contains "$OUT" "writer" "list shows the role"
run "$SMINOS" join grp joiner --parent orchestrator --desc "v2 style"
assert_rc 0 "$RC" "v2 'join' still works as an alias of seat add"
run "$SMINOS" list --json grp
assert_contains "$OUT" '"brief": "v2 style"' "join's --desc lands in brief"
run "$SMINOS" leave grp joiner
assert_rc 0 "$RC" "v2 'leave' removes the seat"

# ---- 4) spawn ----------------------------------------------------------------
echo "spawn:"
cd "$WORK"
run "$SMINOS" spawn researcher "PING-scope-42" --group grp --parent orchestrator --role researcher
assert_rc 0 "$RC" "spawn exits 0"
assert_contains "$OUT" "seat spawned: grp/researcher" "spawn banner names the seat"
R_UUID="$(banner_uuid "$OUT")"; R_SHORT="$(banner_short "$OUT")"
assert_file_exists "$SMINOS_HOME/$R_UUID.json" "record is named after the first session's uuid (banner bracket form)"
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
assert_contains "$(field "$R_UUID" task)" 'You are seat "researcher" in sminos group "grp"' "explicit --group prepends the preamble"
assert_contains "$(field "$R_UUID" task)" "--group grp --parent researcher" "preamble tells the seat how to spawn its own children"
assert_contains "$(field "$R_UUID" task)" "send grp/<alias>" "preamble teaches sminos send as the transport"
assert_not_contains "$(field "$R_UUID" task)" "ToolSearch" "preamble no longer routes through the native tool"
assert_contains "$(field "$R_UUID" task)" "PING-scope-42" "task text follows the preamble"
assert_file_exists "$SMINOS_HOME/$R_UUID.reply.txt" "reply of an already-finished first turn is recorded"
assert_contains "$(cat "$SMINOS_HOME/$R_UUID.reply.txt")" "ANSWER:" "recorded reply comes from the transcript"
assert_contains "$(grep 'bg-env:You are seat' "$STUB_STATE/log/calls.log" | tail -1)" "path=set" "PATH survives the plain-route launch"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--permission-mode auto -n researcher" "launch uses auto permission mode and the alias as display name"

run "$SMINOS" spawn plainworker "NOGROUP-1"
assert_rc 0 "$RC" "spawn without --group"
P_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$P_UUID" group)" "work" "group derived from the cwd when --group is absent"
assert_not_contains "$(field "$P_UUID" task)" "You are seat" "no preamble without an explicit --group"
assert_equals "$(field "$P_UUID" preamble)" "" "implicit-group seat records no preamble flag"

# Launch under the advertised address (--addr): the harness -n name and the
# record's name are the addr, so a custom addr is the live SendMessage name.
run "$SMINOS" spawn worker-a "ADDR-1" --group grp --addr "custom addr"
assert_rc 0 "$RC" "spawn with --addr exits 0"
WA_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$WA_UUID" addr)" "custom addr" "custom addr recorded"
assert_equals "$(field "$WA_UUID" name)" "custom addr" "harness display name is the addr"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" '-n custom addr' "launch runs under -n <addr>"
"$SMINOS" remove grp/worker-a >/dev/null

STUB_BG_STATE=working run "$SMINOS" spawn nowaiter "LONG-TASK-7" --no-wait --group grp
assert_rc 0 "$RC" "--no-wait is accepted"
NW_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$NW_UUID" status)" "working" "a running first turn records working"
assert_file_absent "$SMINOS_HOME/$NW_UUID.reply.txt" "no reply file while the turn runs"
run "$SMINOS" reply nowaiter
assert_contains "$OUT" "ANSWER:" "reply reads the running turn's transcript"
assert_contains "$OUT" "--- latest reply ---" "reply prints its header"

# spawn refuses a FILLED seat (nowaiter is busy) but RE-FILLS a stopped one.
run "$SMINOS" spawn nowaiter "x" --group grp
assert_rc 4 "$RC" "spawning a filled seat is refused"
assert_contains "$OUT" "message it with sminos send/wake" "filled refusal points at send/wake"
run "$SMINOS" spawn refillme "FIRST" --group grp --role r1 --brief b1
assert_rc 0 "$RC" "first spawn of refillme exits 0"
RF="$(seat_id_of refillme)"
"$SMINOS" meta set refillme ticket 42 lane implement board_dispatch n-8 >/dev/null   # pipeline-owned: ticket and the dispatch marker are per-run, lane describes the seat
"$SMINOS" status refillme "did the first pass" >/dev/null
RF_FIRST="$(field "$RF" current)"
# PROVENANCE RIDES THE LAUNCH DICT. `--stamp field=value` merges into the very
# first write of the record, which is what the board pipeline needs: a separate
# `meta set` after the spawn never runs when the uuid poll times out or the
# caller dies inside it, and the client reads `board_dispatch` precisely to tell
# a dispatched seat from an operator's own.
run "$SMINOS" spawn stamped "STAMPED-1" --group grp --stamp board_dispatch=n-7 --stamp lane=implementer
assert_rc 0 "$RC" "spawn with --stamp exits 0"
ST="$(seat_id_of stamped)"
assert_equals "$(field "$ST" board_dispatch)" "n-7" "--stamp lands on the record"
assert_equals "$(field "$ST" lane)" "implementer" "--stamp is repeatable"
run "$SMINOS" spawn badstamp "X" --group grp --stamp nosign
assert_rc 2 "$RC" "--stamp without field=value is a usage error"
run "$SMINOS" spawn badstamp "X" --group grp --stamp run_bearer=leak
assert_rc 2 "$RC" "--stamp refuses a credential field"
# The drop and the stamp meet on a re-fill, and the stamp wins: meta_set removes
# AFTER it merges, so a dispatched re-fill has to be exempt from its own drop.
"$SMINOS" meta set stamped board_dispatch n-old >/dev/null
run "$SMINOS" spawn stamped "STAMPED-2" --group grp --stamp board_dispatch=n-new
assert_rc 0 "$RC" "a dispatched re-fill exits 0"
assert_equals "$(field "$ST" board_dispatch)" "n-new" "its --stamp survives the re-fill's own drop"

run "$SMINOS" spawn refillme "SECOND" --group grp
assert_rc 0 "$RC" "re-spawning a stopped seat re-fills it (exit 0)"
assert_contains "$OUT" "seat re-filled: grp/refillme" "re-fill is reported"
assert_equals "$(banner_uuid "$OUT")" "$RF" "re-fill banner's bracket uuid is the RECORD filename, not the new session"
assert_equals "$(seat_id_of refillme)" "$RF" "re-fill keeps the same seat id"
assert_equals "$(field "$RF" role)" "r1" "re-fill without --role keeps the seat's role"
assert_equals "$(field "$RF" brief)" "b1" "re-fill without --brief keeps the seat's brief"
assert_contains "$(field "$RF" task)" "SECOND" "re-fill updates the task"
assert_equals "$(field "$RF" turns)" "1" "re-fill resets turns"
assert_equals "$(field "$RF" lane)" "implement" "re-fill keeps the seat-describing pipeline field (lane)"
assert_equals "$(field "$RF" ticket)" "" "re-fill clears the predecessor's run binding (ticket)"
# A RE-FILL IS A NEW OCCUPANT, so it does not inherit the predecessor's
# provenance: a seat a dispatcher once launched, re-filled by hand, would
# otherwise still read as dispatched — and the board client refuses a
# dispatched seat whose bind never lands. A dispatched re-fill re-stamps it.
assert_equals "$(field "$RF" board_dispatch)" "" "re-fill drops the predecessor's dispatch marker"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0]["ticket"])' "$SMINOS_HOME/$RF.json")" "42" "history[0].ticket records the predecessor's ticket"
if [ "$(field "$RF" current)" != "$RF" ]; then pass "re-fill gives the seat a new session"; else fail "re-fill gives the seat a new session"; fi
assert_not_contains "$(field "$RF" now)" "did the first pass" "a fresh re-fill clears the stale now line"
assert_equals "$(field "$RF" attempts)" "2" "re-fill bumps attempts"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0]["current"])' "$SMINOS_HOME/$RF.json")" "$RF_FIRST" "history[0] records the previous occupant's session"
run "$SMINOS" spawn refillme "THIRD" --group grp --role r2 --brief b2
assert_equals "$(field "$RF" role)" "r2" "re-fill with --role updates the role"
assert_equals "$(field "$RF" brief)" "b2" "re-fill with --brief updates the brief"
assert_equals "$(field "$RF" attempts)" "3" "attempts keeps counting"
"$SMINOS" remove grp/refillme >/dev/null

run "$SMINOS" spawn waiter "WAIT-1" --group grp --wait
assert_rc 0 "$RC" "--wait exits 0 on a finished turn"
assert_contains "$OUT" "--- reply ---" "--wait prints the reply block"
assert_contains "$OUT" "ANSWER:" "--wait prints the reply text"
W_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$W_UUID" status)" "idle" "--wait records idle"

STUB_BG_STATE=working run "$SMINOS" spawn slow "SLOW-1" --group grp --wait
assert_rc 1 "$RC" "--wait watcher timeout exits 1"
assert_contains "$OUT" "watcher expired" "watcher timeout is reported"
S_UUID="$(seat_id_of slow)"
assert_equals "$(field "$S_UUID" status)" "working" "watcher timeout leaves status working (the turn is live)"

record_count() { local n=0 f; for f in "$SMINOS_HOME"/*.json; do case "$f" in *.reply.json) ;; *) n=$((n + 1)) ;; esac; done; echo "$n"; }
before=$(record_count)
STUB_FAIL_BG=1 run "$SMINOS" spawn failer "F" --group grp
assert_rc 1 "$RC" "a launch that prints no id exits 1"
after=$(record_count)
assert_equals "$after" "$before" "a failed launch leaves no phantom seat"

STUB_NO_UUID=1 run "$SMINOS" spawn nouuid "N" --group grp
assert_rc 1 "$RC" "a session with no uuid exits 1"
NU_ID="$(seat_id_of nouuid)"
assert_equals "$(field "$NU_ID" status)" "error" "no-uuid launch records status error"
if [ -n "$(field "$NU_ID" pending_short)" ]; then pass "no-uuid launch records pending_short for recovery"; else fail "no-uuid launch records pending_short for recovery"; fi
"$SMINOS" remove "grp/nouuid" >/dev/null

# gateway dimension: env-injected settings/effort ride the launch and are
# persisted; the plain route scrubs the gateway's transport env (PATH survives).
GW="$TEST_ROOT/gw.json"
printf '{"env":{"ANTHROPIC_BASE_URL":"http://gw","ANTHROPIC_AUTH_TOKEN":"tok","CLAUDE_CODE_SUBAGENT_MODEL":"m","PATH":"/nope"}}' > "$GW"
mkdir -p "$HOME/.claude"; cp "$GW" "$HOME/.claude/clodex-settings.json"
export ANTHROPIC_BASE_URL="http://gw" ANTHROPIC_AUTH_TOKEN="fixture-token" CLAUDE_CODE_SUBAGENT_MODEL="sub" UNRELATED_TRANSPORT_VAR="keep" RUNNER_TRACKING_ID="run-1"
DAEMON_CLAUDE_SETTINGS="$GW" DAEMON_CLAUDE_EFFORT=high run "$SMINOS" spawn gwworker "GW-1" --group grp
assert_rc 0 "$RC" "gateway spawn exits 0"
G_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$G_UUID" settings)" "$GW" "DAEMON_CLAUDE_SETTINGS persisted as settings"
assert_equals "$(field "$G_UUID" effort)" "high" "DAEMON_CLAUDE_EFFORT persisted as effort"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--settings $GW --effort high" "gateway flags reach the launch"
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "base=http://gw;token=fixture-token" "gateway route keeps the transport env"
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "runner=;" "RUNNER_TRACKING_ID is always stripped"
run "$SMINOS" spawn plain2 "PLAIN-2" --group grp
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "base=;token=;sub=;keep=keep;runner=;path=set" "plain route scrubs the gateway env keys, keeps PATH and unrelated vars"
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_SUBAGENT_MODEL UNRELATED_TRANSPORT_VAR RUNNER_TRACKING_ID

run "$SMINOS" spawn wtworker "WT-1" --group grp --worktree "feat x"
assert_rc 0 "$RC" "worktree spawn exits 0"
WT_UUID="$(banner_uuid "$OUT")"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--worktree feat-x" "worktree name is sanitized"
assert_equals "$(field "$WT_UUID" cwd)" "$WORK/.claude/worktrees/feat-x" "cwd is the worktree path the harness reports"
assert_contains "$OUT" "worktree=" "banner notes the worktree"

# Live-name refusal: a live harness session already answering to the alias
# would make every SendMessage to it ambiguous — refuse before any side effect.
printf '{"pid":%s,"sessionId":"77777777-aaaa-4000-8000-000000000007","name":"taken","kind":"interactive","status":"idle","messagingSocketPath":"%s"}\n' "$$" "$SOCK" > "$HOME/.claude/sessions/$$.json"
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$SMINOS" spawn taken "T" --group grp
assert_rc 4 "$RC" "spawn refuses an alias a live session already answers to"
assert_contains "$OUT" "live session already answers to 'taken'" "live-name refusal is explained"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no session is launched when the name is taken"
run "$SMINOS" seat add grp taken
assert_rc 4 "$RC" "seat add refuses a live-held alias without --session"
run "$SMINOS" seat add grp taken --session 77777777-aaaa-4000-8000-000000000007
assert_rc 0 "$RC" "seat add registers the very session that holds the name"
rm -f "$HOME/.claude/sessions/$$.json"
run "$SMINOS" spawn researcher "OTHER" --group other
assert_rc 0 "$RC" "the same alias in another group is allowed when no live session holds it"
"$SMINOS" remove other/researcher >/dev/null

# Lifecycle lock: a spawn of a seat whose lock another sminos process holds is
# refused, never duplicated.
python3 - "$(lock_file locked)" <<'PY' &
import fcntl, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
HOLDER=$!
sleep 0.4
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$SMINOS" spawn locked "L" --group grp
assert_rc 4 "$RC" "a spawn while the seat's lifecycle lock is held is refused"
assert_contains "$OUT" "being changed by another sminos process" "lock refusal is explained"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no session is launched while the lock is held"
kill "$HOLDER" 2>/dev/null || true; wait "$HOLDER" 2>/dev/null || true

# ---- 5) sync (finalize) and blocked shapes -----------------------------------
echo "sync:"
run "$SMINOS" sync waiter; assert_equals "$OUT" "noop" "sync on an idle seat is noop"
# The seat 'slow' is working with a live row (state running) → live.
run "$SMINOS" sync slow; assert_equals "$OUT" "live" "sync on a running turn is live"
# Lingering finished shape: state=working + status=idle → done → idle.
SLOW_SHORT="$(field "$S_UUID" short)"
sed -i.bak 's/^state=.*/state=working/; s/^status=.*/status=idle/' "$STUB_STATE/agents/$SLOW_SHORT" && rm -f "$STUB_STATE/agents/$SLOW_SHORT.bak"
run "$SMINOS" sync slow; assert_equals "$OUT" "idle" "lingering working+idle shape finalizes as idle"
assert_equals "$(field "$S_UUID" status)" "idle" "sync wrote status idle"
assert_file_exists "$SMINOS_HOME/$S_UUID.reply.txt" "sync recorded the reply"
# absent: a working seat whose row is gone.
"$SMINOS" mark slow working >/dev/null
rm -f "$STUB_STATE/agents/$SLOW_SHORT"
run "$SMINOS" sync slow; assert_equals "$OUT" "absent" "sync with no harness row is absent"
assert_equals "$(field "$S_UUID" status)" "working" "absent leaves the record untouched"
# error: state failed.
{ echo "short=$SLOW_SHORT"; echo "uuid=$S_UUID"; echo "name=slow"; echo "state=failed"; echo "status="; echo "cwd=$WORK"; } > "$STUB_STATE/agents/$SLOW_SHORT"
run "$SMINOS" sync slow; assert_equals "$OUT" "error" "a failed row finalizes as error"
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
"$SMINOS" seat add grp asker --session "$ASKQ_UUID" >/dev/null
"$SMINOS" mark asker blocked >/dev/null
{ echo "short=aaaa0001"; echo "uuid=$ASKQ_UUID"; echo "name=asker"; echo "state=blocked"; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/aaaa0001"
run "$SMINOS" sync asker; assert_equals "$OUT" "idle" "an ended blocked-shape turn finalizes as idle"
ASK_REPLY="$(cat "$SMINOS_HOME/$ASKQ_UUID.reply.txt")"
assert_contains "$ASK_REPLY" "Which color should the widget be?" "pending AskUserQuestion surfaced in the reply"
assert_contains "$ASK_REPLY" "Red / Blue" "pending question options rendered"
assert_contains "$ASK_REPLY" "Before I pick, one question." "turn text still printed alongside the question"
assert_contains "$ASK_REPLY" "sminos wake asker" "reply points at the answer path"
assert_not_contains "$ASK_REPLY" "blocked on a harness prompt" "a rendered question gets no harness-prompt marker"
PERM_UUID="55555555-eeee-4000-8000-000000000005"
python3 - "$HOME/.claude/projects/fake-proj/$PERM_UUID.jsonl" <<'PY'
import json, sys
open(sys.argv[1], "w").write(json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "About to ask something."}]}}) + "\n")
PY
"$SMINOS" seat add grp permer --session "$PERM_UUID" >/dev/null
"$SMINOS" mark permer blocked >/dev/null
{ echo "short=aaaa0002"; echo "uuid=$PERM_UUID"; echo "name=permer"; echo "state=blocked"; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/aaaa0002"
run "$SMINOS" sync permer; assert_equals "$OUT" "idle" "blocked-without-question also finalizes idle"
assert_contains "$(cat "$SMINOS_HOME/$PERM_UUID.reply.txt")" "blocked on a harness prompt" "blocked-without-question reply carries the harness-prompt marker"

# A natively-woken turn: the harness's own SendMessage started it and it ended
# between two syncs, so the record never left `idle` and the reply file still
# describes the PREVIOUS turn. The transcript's mtime is the only witness.
NAT_UUID="3d3d2222-abab-4000-8000-00000003d3d2"
"$SMINOS" seat add grp nativewoke --session "$NAT_UUID" >/dev/null
printf 'PREVIOUS TURN TEXT\n' > "$SMINOS_HOME/$NAT_UUID.reply.txt"
python3 - "$HOME/.claude/projects/fake-proj/$NAT_UUID.jsonl" <<'PY'
import json, sys
open(sys.argv[1], "w").write(json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "NATIVELY WOKEN ANSWER"}]}}) + "\n")
PY
python3 -c 'import os, sys, time; t = time.time()
os.utime(sys.argv[1], (t - 10, t - 10)); os.utime(sys.argv[2], (t, t))' \
  "$SMINOS_HOME/$NAT_UUID.reply.txt" "$HOME/.claude/projects/fake-proj/$NAT_UUID.jsonl"
run "$SMINOS" reply nativewoke
assert_contains "$OUT" "NATIVELY WOKEN ANSWER" "reply prefers a transcript newer than the recorded reply"
assert_not_contains "$OUT" "PREVIOUS TURN TEXT" "the previous turn's recorded reply is not what reply shows"
{ echo "short=nat00099"; echo "uuid=$NAT_UUID"; echo "name=nativewoke"; echo "state=working"; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/nat00099"
run "$SMINOS" sync nativewoke
assert_equals "$OUT" "idle" "sync reconciles an idle seat whose transcript moved on"
assert_contains "$(cat "$SMINOS_HOME/$NAT_UUID.reply.txt")" "NATIVELY WOKEN ANSWER" "sync re-recorded the natively-woken turn's reply"
run "$SMINOS" sync nativewoke
assert_equals "$OUT" "noop" "a second sync, with the reply now current, is noop"
"$SMINOS" remove grp/nativewoke >/dev/null; rm -f "$STUB_STATE/agents/nat00099"

run "$SMINOS" sync --all
assert_rc 0 "$RC" "sync --all runs"
run "$SMINOS" sync
assert_rc 0 "$RC" "bare sync = --all"

# ---- 6) wake / send over the inbox socket -----------------------------------
echo "wake / send:"
# A live peer record for the orchestrator seat: the socket server's pid is
# alive, its socket accepts connections.
printf '{"pid":%s,"sessionId":"%s","name":"my session","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$ORCH_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/$SOCK_PID.json"
run "$SMINOS" send orchestrator "hello there"
assert_rc 0 "$RC" "send to a live seat exits 0"
assert_contains "$OUT" "sent to grp/orchestrator" "send reports the target"
sleep 0.2
assert_contains "$(cat "$RECEIVED")" '"type": "user"' "frame is the documented user-message shape"
assert_contains "$(cat "$RECEIVED")" '[sminos message from human]\nhello there' "sender identity travels in the text's first line"
run "$SMINOS" send scribe "x"
assert_rc 4 "$RC" "send to a vacant seat is refused (exit 4)"
assert_contains "$OUT" "sminos wake" "send refusal points at wake"
run "$SMINOS" send "my session" "by name" --from ops
assert_rc 0 "$RC" "send resolves a live harness session name when no seat matches"
sleep 0.2
assert_contains "$(cat "$RECEIVED")" '[sminos message from ops]\nby name' "--from is honored"
run "$SMINOS" send nobody-here "x"
assert_rc 4 "$RC" "send to an unknown target exits 4"

# ---- 6b) codex threads, through codex's durable message queue ----------------
# When no seat and no live harness session matches, the target is tried as a
# Codex thread (id or exact name) via `codex queue`; `codex:` skips the lookups.
echo "send to codex:"
NOCODEX_PATH="$STUB_BIN:$(dirname "$(command -v python3)"):/usr/bin:/bin"
run env PATH="$NOCODEX_PATH" "$SMINOS" send nobody-here "x"
assert_rc 4 "$RC" "without codex on PATH an unknown target still exits 4"
assert_contains "$OUT" "no seat or live session matching" "without codex the refusal names only seats and sessions"
assert_not_contains "$OUT" "codex" "without codex the refusal does not mention codex"
printf '%s\n' "01a07a8a-569e-7923-b476-8a7d7d6271c3 spike thread" "01a0730b-88ff-7591-a446-c278aa14093f orchestrator" > "$STUB_STATE/codex-threads"
run "$SMINOS" send nobody-here "x"
assert_rc 4 "$RC" "with codex on PATH an unknown target exits 4"
assert_contains "$OUT" "or codex thread matching" "with codex the refusal names codex threads too"
assert_not_contains "$(cat "$STUB_STATE/log/calls.log")" "queue --thread nobody-here" "a bare name is never tried as a codex thread (a name miss costs codex a full history scan)"
run "$SMINOS" send 01a0aaaa-0000-7000-8000-00000000dead "x"
assert_rc 4 "$RC" "an unknown thread id exits 4"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "queue --thread 01a0aaaa-0000-7000-8000-00000000dead" "a bare thread id IS tried with codex before giving up"
run "$SMINOS" send 01a07a8a-569e-7923-b476-8a7d7d6271c3 "ping codex"
assert_rc 0 "$RC" "a codex thread id is accepted"
assert_contains "$OUT" "queued for codex thread 01a07a8a-569e-7923-b476-8a7d7d6271c3 (01a0aaaa-0000-7000-8000-000000000001)" "send reports the thread and the queued submission"
assert_contains "$OUT" "read between turns" "the report says when codex reads it"
assert_not_contains "$OUT" "sent to" "a queued message is not reported as sent"
assert_contains "$(cat "$STUB_STATE/log/codex-queue.log")" "[sminos message from human]" "sender identity travels in the queued text"
assert_contains "$(cat "$STUB_STATE/log/codex-queue.log")" "ping codex" "the message body is queued"
run "$SMINOS" send "spike thread" "by name"
assert_rc 4 "$RC" "a bare codex thread NAME is not resolved"
run "$SMINOS" send "codex:spike thread" "by name" --from ops
assert_rc 0 "$RC" "codex:<name> resolves an exact codex thread name"
assert_contains "$OUT" "queued for codex thread 01a07a8a" "the name is reported as its thread id"
assert_contains "$(cat "$STUB_STATE/log/codex-queue.log")" "[sminos message from ops]" "--from is honored for codex targets"
run "$SMINOS" send orchestrator "to the seat"
assert_rc 0 "$RC" "a seat alias that a codex thread also carries reaches the seat"
assert_contains "$OUT" "sent to grp/orchestrator" "the seat wins over the codex thread of the same name"
run "$SMINOS" send codex:orchestrator "to codex"
assert_rc 0 "$RC" "codex: routes straight to codex"
assert_contains "$OUT" "queued for codex thread 01a0730b" "codex: skips the seat lookup"
run "$SMINOS" send codex:no-such-thread "x"
assert_rc 4 "$RC" "codex: with an unknown thread exits 4"
assert_contains "$OUT" "no codex thread matching 'no-such-thread'" "codex: refusal names the thread"
run env STUB_CODEX_FAIL=1 "$SMINOS" send codex:orchestrator "x"
assert_rc 1 "$RC" "a codex failure other than an unknown thread exits 1"
assert_contains "$OUT" "codex queue failed for 'orchestrator': Error: failed to queue session message: app server exploded" "the codex error text is surfaced"
run "$SMINOS" list grp
assert_contains "$OUT" "idle" "a seat with a live peer record shows idle"

# procStart is a wall-clock string with no zone in it: the harness writes it in
# UTC while `ps -o lstart=` prints local time, so comparing the two as text
# read every live seat as `stopped` and made send refuse everything on any
# machine that is not on UTC. The pid below is really running, so its start
# time is real; these cases pin that the same instant written either way still
# reads as the same process, and that an unrelated time still reads as a
# recycled pid.
lstart_as() { # utc|local → the socket server's real start time in that zone
  # LC_ALL=C, exactly as sminos reads it: a localized ps prints "수  9/ 2 23:08:14 2026".
  LSTART="$(LC_ALL=C LANG=C ps -o lstart= -p "$SOCK_PID")" python3 -c '
import os, sys, time
t = time.strptime(" ".join(os.environ["LSTART"].split()), "%a %b %d %H:%M:%S %Y")
epoch = time.mktime(t)
print(time.strftime("%a %b %e %H:%M:%S %Y", time.gmtime(epoch) if sys.argv[1] == "utc" else time.localtime(epoch)))' "$1"
}
peer_with_procstart() { # procStart-string → rewrite the orchestrator's peer record
  printf '{"pid":%s,"sessionId":"%s","name":"my session","kind":"interactive","status":"idle","cwd":"%s","procStart":"%s","messagingSocketPath":"%s"}\n' \
    "$SOCK_PID" "$ORCH_UUID" "$WORK" "$1" "$SOCK" > "$HOME/.claude/sessions/$SOCK_PID.json"
}
peer_with_procstart "$(lstart_as local)"
run "$SMINOS" send orchestrator "procstart local"
assert_rc 0 "$RC" "a procStart written in local time identifies the process"
peer_with_procstart "$(lstart_as utc)"
run "$SMINOS" send orchestrator "procstart utc"
assert_rc 0 "$RC" "a procStart written in UTC identifies the same process (the harness writes UTC; ps prints local)"
run "$SMINOS" list grp
assert_contains "$OUT" "idle" "and the seat still reads idle rather than stopped"
peer_with_procstart "Mon Jan  1 00:00:00 2001"
run "$SMINOS" send orchestrator "procstart bogus"
assert_rc 4 "$RC" "an unrelated procStart reads as a recycled pid and send refuses"
printf '{"pid":%s,"sessionId":"%s","name":"my session","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$ORCH_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/$SOCK_PID.json"

run "$SMINOS" wake orchestrator "wake up" --from boss
assert_rc 0 "$RC" "wake of a live seat exits 0"
assert_contains "$OUT" "via inbox socket" "live wake goes through the socket"
sleep 0.2
assert_contains "$(cat "$RECEIVED")" '[sminos wake from boss id=' "wake frame carries the wake prefix, sender, and a message id"
assert_contains "$(cat "$RECEIVED")" ']\nwake up' "wake frame carries the message after the first line"
assert_equals "$(field "$ORCH_UUID" status)" "working" "wake stamps status working"
"$SMINOS" mark orchestrator idle >/dev/null

# wake --wait needs EVIDENCE the message landed (the frame's id in the
# target's transcript, or a busy row) before it waits for a reply.
{ echo "short=orch0001"; echo "uuid=$ORCH_UUID"; echo "name=my session"; echo "kind=interactive"; echo "state="; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/orch0001"
SMINOS_ACK_TIMEOUT=0.4 run "$SMINOS" wake orchestrator "ACK-0" --wait
assert_rc 1 "$RC" "wake --wait without evidence of receipt exits 1"
assert_not_contains "$OUT" "--- reply ---" "no reply block is printed without evidence"
"$SMINOS" mark orchestrator idle >/dev/null
( SMINOS_ACK_TIMEOUT=5 "$SMINOS" wake orchestrator "ACK-1" --wait > "$TEST_ROOT/ack.out" 2>&1; echo $? > "$TEST_ROOT/ack.rc" ) &
ACKW=$!
sleep 0.5
ACK_ID="$(grep -o 'id=[0-9a-f]\{8\}' "$RECEIVED" | tail -1 | cut -d= -f2)"
mkdir -p "$HOME/.claude/projects/fake-proj"
python3 - "$HOME/.claude/projects/fake-proj/$ORCH_UUID.jsonl" "$ACK_ID" <<'PY'
import json, sys
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "[sminos wake from human id=%s]\nACK-1" % sys.argv[2]}}) + "\n")
    f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ACKED " + sys.argv[2]}]}}) + "\n")
PY
wait "$ACKW" || true
assert_equals "$(cat "$TEST_ROOT/ack.rc")" "0" "wake --wait exits 0 once the marker appears in the transcript"
assert_contains "$(cat "$TEST_ROOT/ack.out")" "--- reply ---" "acknowledged wake --wait prints the reply block"
assert_contains "$(cat "$TEST_ROOT/ack.out")" "ACKED $ACK_ID" "acknowledged wake --wait prints the turn's reply"

# Resume branch: 'researcher' has a session but no live peer → --bg --resume.
run "$SMINOS" wake researcher "again please"
assert_rc 0 "$RC" "wake of a stopped seat exits 0"
assert_contains "$OUT" "via --bg --resume" "stopped wake resumes the session"
RESUME_LINE="$(grep -- '^--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)"
assert_contains "$RESUME_LINE" "--bg --resume $R_UUID [sminos wake from human id=" "resume argv is exactly --bg --resume <id> <msg>"
assert_not_contains "$RESUME_LINE" "--permission-mode" "no permission-mode flag rides a resume (it would start a copy)"
assert_not_contains "$RESUME_LINE" "-n " "no name flag rides a resume"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "same-id resume keeps current"
assert_equals "$(field "$R_UUID" turns)" "2" "resume increments turns"
assert_equals "$(field "$R_UUID" short)" "$R_SHORT" "a same-id resume keeps the session's short"
assert_equals "$(field "$R_UUID" status)" "idle" "a resume whose turn already ended records idle"
run "$SMINOS" wake researcher "with reply" --wait
assert_contains "$OUT" "--- reply ---" "wake --wait prints the reply block"
assert_contains "$OUT" "RESUMED:$R_UUID" "wake --wait prints the resumed turn's reply"
STUB_RESUME_COPY=1 run "$SMINOS" wake researcher "copy?"
assert_rc 1 "$RC" "a resume whose banner says a copy started fails loudly"
assert_contains "$OUT" "started a COPY" "copy detection is explained"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "the record is left untouched after a copy"
assert_equals "$(field "$R_UUID" status)" "idle" "status is restored after a copy"
COPY_SHORT="$(printf '%08x' "$(cat "$STUB_STATE/counter")")"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop $COPY_SHORT" "the announced copy is stopped"
STUB_RESUME_COPY=2 run "$SMINOS" wake researcher "silent copy?"
assert_rc 1 "$RC" "a silent copy (different session id after polling) also fails loudly"
COPY_SHORT="$(printf '%08x' "$(cat "$STUB_STATE/counter")")"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop $COPY_SHORT" "the silent copy is stopped"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "the record is left untouched after a silent copy"

# ---- 6b) resume: process-level continuation ---------------------------------
echo "resume:"
run "$SMINOS" resume plainworker "RES-1"
assert_rc 0 "$RC" "resume exits 0"
assert_contains "$OUT" "resumed work/plainworker" "resume reports the seat"
assert_equals "$(grep -- '^--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)" "--bg --resume $P_UUID RES-1" "resume argv is exactly --bg --resume <id> <msg>"
assert_equals "$(field "$P_UUID" turns)" "2" "resume increments turns"
assert_equals "$(field "$P_UUID" current)" "$P_UUID" "same-id resume keeps current"
run "$SMINOS" resume plainworker "RES-1b" --model opus --effort high
assert_rc 0 "$RC" "resume accepts route flags for argv compatibility"
assert_contains "$OUT" "keeps its saved options; --model/--settings/--effort ignored" "resume warns that route flags are ignored"
assert_equals "$(grep -- '^--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)" "--bg --resume $P_UUID RES-1b" "route flags never reach a resume argv"
assert_equals "$(field "$P_UUID" model)" "" "resume leaves the recorded model untouched"
assert_equals "$(field "$P_UUID" effort)" "" "resume leaves the recorded effort untouched"
P_SHORT="$(field "$P_UUID" short)"
sed -i.bak 's/^state=.*/state=working/; s/^status=.*/status=busy/' "$STUB_STATE/agents/$P_SHORT" && rm -f "$STUB_STATE/agents/$P_SHORT.bak"
run "$SMINOS" resume plainworker "RES-2"
assert_rc 0 "$RC" "resume of a live turn exits 0"
assert_contains "$(grep -E '^(stop|--bg)' "$STUB_STATE/log/calls.log" | tail -2 | head -1)" "stop $P_SHORT" "a live turn is stopped before the resume"
run "$SMINOS" resume plainworker "RES-4" --wait
assert_rc 0 "$RC" "resume --wait exits 0"
assert_contains "$OUT" "--- reply ---" "resume --wait prints the reply block"
assert_contains "$OUT" "RESUMED:$P_UUID:ANSWER:RES-4" "resume --wait prints the resumed turn's reply"
run "$SMINOS" wake scribe "x"
assert_rc 4 "$RC" "waking a vacant seat exits 4"
assert_contains "$OUT" "sminos fill" "vacant wake points at fill"
# Resume lock: a resume already in flight refuses a twin.
python3 - "$SMINOS_HOME/$R_UUID.resume.lock" <<'PY' &
import fcntl, sys, time
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
LOCKER=$!
sleep 0.4
run "$SMINOS" wake researcher "twin"
assert_rc 1 "$RC" "a second resume while one is in flight is refused"
assert_contains "$OUT" "already in flight" "twin refusal is explained"
kill "$LOCKER" 2>/dev/null || true; wait "$LOCKER" 2>/dev/null || true

# ---- 7) retire / fill --------------------------------------------------------
echo "retire / fill:"
run "$SMINOS" retire researcher
assert_rc 0 "$RC" "retire exits 0"
assert_equals "$(field "$R_UUID" status)" "retired" "retire marks the seat retired"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop $(field "$R_UUID" short)" "retire stops the current turn"
assert_contains "$OUT" "sminos fill grp/researcher --resume" "retire hints at re-filling"
run "$SMINOS" fill researcher "FRESH-START"
assert_rc 0 "$RC" "fresh fill exits 0"
assert_contains "$OUT" "seat filled: grp/researcher" "fill reports the seat"
NEWCUR="$(field "$R_UUID" current)"
if [ "$NEWCUR" != "$R_UUID" ]; then pass "fresh fill gives the seat a new session while keeping the seat id"; else fail "fresh fill gives the seat a new session while keeping the seat id"; fi
assert_not_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--resume" "fresh fill does not resume"
assert_contains "$(field "$R_UUID" task)" 'You are seat "researcher"' "fresh fill re-renders the preamble for a wired seat"
assert_contains "$(field "$R_UUID" task)" "FRESH-START" "fresh fill carries the new task"
assert_equals "$(field "$R_UUID" turns)" "1" "fresh fill resets turns"
run "$SMINOS" fill researcher "CONTINUE" --resume
assert_rc 0 "$RC" "fill --resume exits 0"
assert_equals "$(grep -- '^--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--bg --resume $NEWCUR CONTINUE" "fill --resume continues the current session with the bare resume argv"
assert_equals "$(field "$R_UUID" current)" "$NEWCUR" "fill --resume keeps the session id"
printf '{"pid":%s,"sessionId":"%s","name":"researcher","kind":"bg","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$(field "$R_UUID" current)" "$SOCK" > "$HOME/.claude/sessions/live-researcher.json"
run "$SMINOS" fill researcher "x"
assert_rc 4 "$RC" "filling a live seat is refused"
rm -f "$HOME/.claude/sessions/live-researcher.json"
run "$SMINOS" retire waiter --purge
assert_rc 0 "$RC" "retire --purge exits 0"
assert_file_absent "$SMINOS_HOME/$W_UUID.json" "purge removes the record"
assert_file_absent "$SMINOS_HOME/$W_UUID.reply.txt" "purge removes the reply"
run "$SMINOS" retire wtworker
assert_contains "$OUT" "branch worktree-feat-x" "retiring a worktree'd seat notes the branch"

# ---- 8) mark / status / meta / attach ----------------------------------------
echo "mark / status / meta / attach:"
run "$SMINOS" mark plainworker awaiting-human tone is a user call
assert_rc 0 "$RC" "mark exits 0"
assert_equals "$(field "$P_UUID" status)" "awaiting-human" "mark sets the judgment status"
assert_equals "$(field "$P_UUID" note)" "tone is a user call" "mark records the note"
run "$SMINOS" status plainworker "drafting the outline"
assert_equals "$(field "$P_UUID" now)" "drafting the outline" "status writes the now line"
run "$SMINOS" list work
assert_contains "$OUT" "drafting the outline" "list shows the now line"
run "$SMINOS" meta get plainworker now
assert_equals "$OUT" "drafting the outline" "meta get reads a field"
run "$SMINOS" meta set plainworker lane implement
assert_equals "$(field "$P_UUID" lane)" "implement" "meta set writes a field"
printf '{"uuid":"%s","name":"bearer-one","group":"grp","status":"working","run_bearer":"tok-fake"}' "66666666-ffff-4000-8000-000000000006" > "$SMINOS_HOME/66666666-ffff-4000-8000-000000000006.json"
chmod 600 "$SMINOS_HOME/66666666-ffff-4000-8000-000000000006.json"
chmod 640 "$SMINOS_HOME/$P_UUID.json"
chmod 755 "$SMINOS_HOME"
"$SMINOS" mark bearer-one blocked >/dev/null
"$SMINOS" mark plainworker blocked >/dev/null
assert_equals "$(mode_of "$SMINOS_HOME/66666666-ffff-4000-8000-000000000006.json")" "0600" "a bearer-carrying record stays 0600 across writes"
assert_equals "$(mode_of "$SMINOS_HOME/$P_UUID.json")" "0600" "a record left wider than 0600 is tightened on the next run"
assert_equals "$(mode_of "$SMINOS_HOME")" "0700" "a root left wider than 0700 is tightened on the next run"
"$SMINOS" remove bearer-one >/dev/null
run "$SMINOS" attach plainworker
assert_contains "$OUT" "claude attach $(field "$P_UUID" short)" "attach prints the harness command when not a TTY"
run "$SMINOS" mark nope idle
assert_rc 4 "$RC" "an unknown seat exits 4"
run "$SMINOS" mark "$(printf '%s' "$P_UUID" | cut -c1-8)" idle
assert_rc 0 "$RC" "a seat id prefix resolves"
run "$SMINOS" mark "$(field "$P_UUID" short)" idle
assert_rc 0 "$RC" "a current short id resolves"

# ---- 9) views: tree, dangling, topology, groups ------------------------------
echo "views:"
"$SMINOS" seat add tree a --role root >/dev/null
"$SMINOS" seat add tree b --parent a >/dev/null
"$SMINOS" seat add tree c --parent b --role leaf >/dev/null
"$SMINOS" seat add tree d --parent zzz >/dev/null
run "$SMINOS" view tree
assert_contains "$OUT" "sminos group: tree" "view names the group"
assert_contains "$OUT" "a [root] · vacant" "view rows carry role and live state"
assert_contains "$OUT" "└── b · vacant" "child rendered under its parent"
assert_contains "$OUT" "    └── c [leaf] · vacant" "grandchild indentation accumulates"
assert_contains "$OUT" "(dangling — parent 'zzz' unknown)" "orphan rendered in the dangling section"
run "$SMINOS" topology tree
assert_contains "$OUT" '"seats"' "topology has the seats key"
assert_contains "$OUT" '"nodes"' "topology keeps the v2 nodes key"
assert_contains "$OUT" '"from": "a"' "topology edges name the parent"
assert_contains "$OUT" '"live": "vacant"' "topology seats carry live state"
run "$SMINOS" groups
assert_contains "$OUT" "tree" "groups lists tree"
assert_contains "$OUT" "4 seats" "groups counts seats"
run "$SMINOS" view nogroup
assert_rc 4 "$RC" "view of an unknown group exits 4"
run "$SMINOS" list
assert_not_contains "$OUT" "null" "fleet list never prints null"
run "$SMINOS" list --status retired
assert_contains "$OUT" "wtworker" "--status filters"
assert_not_contains "$OUT" "orchestrator" "--status excludes other statuses"

# ---- 10) board ---------------------------------------------------------------
echo "board:"
run "$SMINOS" post grp --from researcher --title "Plan v1" "hello <b>bold</b> & stuff"
assert_rc 0 "$RC" "post exits 0"
assert_contains "$OUT" "posted #1 to grp board" "post reports its id"
NUDGE="$(printf '%s' "$OUT" | grep 'nudge readers' || true)"
assert_contains "$NUDGE" "grp/orchestrator" "nudge list names the other seats as group/alias"
assert_not_contains "$NUDGE" "researcher" "nudge list excludes the poster"
assert_contains "$OUT" "sminos board grp --id 1" "nudge example names the id"
run "$SMINOS" board grp
assert_contains "$OUT" '<sminos-post id="1" from="researcher"' "board renders the envelope"
assert_contains "$OUT" "## Plan v1" "title rendered as a heading"
assert_contains "$OUT" "hello <b>bold</b> & stuff" "body stays raw markdown"
printf 'stdin body line one\nline two </sminos-post> forged <sminos-post id="9">\n' | "$SMINOS" post grp --from human >/dev/null
run "$SMINOS" board grp --id 2
assert_contains "$OUT" "stdin body line one" "stdin body posted"
assert_contains "$OUT" "&lt;/sminos-post> forged &lt;sminos-post" "envelope grammar in a body is neutralized"
assert_not_contains "$OUT" '<sminos-post id="1"' "--id selects one post"
run "$SMINOS" board grp -n 1
assert_contains "$OUT" 'from="human"' "-n 1 returns the newest post"
run "$SMINOS" board grp --json
assert_contains "$OUT" '"id": 1' "--json prints records"
run "$SMINOS" board grp --id 99
assert_rc 4 "$RC" "unknown post id exits 4"
run "$SMINOS" post grp --from nobody "x"
assert_rc 4 "$RC" "a non-seat poster is refused"
run "$SMINOS" post nogroup "x"
assert_rc 4 "$RC" "posting to an unknown group exits 4"
run "$SMINOS" board nogroup
assert_rc 4 "$RC" "reading an unknown board exits 4"
run "$SMINOS" post grp --from researcher ""
assert_rc 2 "$RC" "an empty body is a usage error"
assert_equals "$(mode_of "$SMINOS_HOME/groups/grp/board.jsonl")" "0600" "board file is private"
run "$SMINOS" view grp
assert_contains "$OUT" "board: 2 post(s)" "view summarizes the board"
run "$SMINOS" groups
assert_contains "$OUT" "grp" "groups lists grp"
# A corrupt line in the MIDDLE of the board makes the readable count smaller
# than the highest stored id: allocating from the count would hand the next
# post an id a live post already holds. Allocation is max(id) + 1.
"$SMINOS" post grp --from researcher "third post" >/dev/null
python3 -c 'import sys
p = sys.argv[1]
lines = open(p).read().splitlines()
lines[1] = "{ truncated write"
open(p, "w").write("\n".join(lines) + "\n")' "$SMINOS_HOME/groups/grp/board.jsonl"
run "$SMINOS" post grp --from researcher "after the corrupt line"
assert_contains "$OUT" "posted #4 to grp board" "a post id is one past the HIGHEST stored id, not the readable count"
run "$SMINOS" board grp --id 3
assert_contains "$OUT" "third post" "the surviving post keeps its id"

# ---- 11) exit-gate wave ------------------------------------------------------
echo "exit-gate wave:"

# Redaction: a secret-shaped field never reaches a model-facing surface.
SEC_UUID="88888888-abab-4000-8000-000000000088"
printf '{"uuid":"%s","name":"secretary","alias":"secretary","group":"grp","status":"idle","current":"%s","run_bearer":"SEKRIT","api_token":"NOPE"}' \
  "$SEC_UUID" "$SEC_UUID" > "$SMINOS_HOME/$SEC_UUID.json"
run "$SMINOS" list --json grp
assert_not_contains "$OUT" "SEKRIT" "list --json never emits run_bearer"
assert_not_contains "$OUT" "NOPE" "list --json never emits a *_token field"
run "$SMINOS" topology grp
assert_not_contains "$OUT" "SEKRIT" "topology never emits run_bearer"
assert_not_contains "$OUT" "NOPE" "topology never emits a token field"
run "$SMINOS" list grp
assert_not_contains "$OUT" "SEKRIT" "list never emits run_bearer"
run "$SMINOS" meta get secretary run_bearer
assert_rc 4 "$RC" "meta get refuses a credential field (the CLI is model-callable)"
assert_not_contains "$OUT" "SEKRIT" "the refused credential value is not echoed"
run "$SMINOS" meta get secretary status
assert_equals "$OUT" "idle" "meta get still reads ordinary fields"
"$SMINOS" remove grp/secretary >/dev/null

# send: an ambiguous seat name propagates (exit 4), never silently falling
# through to a raw harness-name lookup.
"$SMINOS" seat add ga dup >/dev/null
"$SMINOS" seat add gb dup >/dev/null
run "$SMINOS" send dup "hi"
assert_rc 4 "$RC" "send to an ambiguous seat name exits 4"
assert_contains "$OUT" "ambiguous seat 'dup'" "the ambiguity is named, not hidden by a name fallback"
"$SMINOS" remove ga/dup >/dev/null; "$SMINOS" remove gb/dup >/dev/null

# Recycled-pid peer: a peer record whose pid is alive but whose socket file is
# gone must NOT count as live (so it can't block a fill or a name reuse).
STALE_UUID="99999999-abab-4000-8000-000000000099"
"$SMINOS" seat add grp stale --session "$STALE_UUID" >/dev/null
printf '{"pid":%s,"sessionId":"%s","name":"stale","kind":"bg","status":"idle","messagingSocketPath":"%s/gone.sock"}\n' \
  "$$" "$STALE_UUID" "$TEST_ROOT" > "$HOME/.claude/sessions/stale.json"
run "$SMINOS" fill grp/stale "REFILL" --resume
assert_rc 0 "$RC" "a peer with a live pid but a missing socket is not live — resume proceeds"
rm -f "$HOME/.claude/sessions/stale.json"; "$SMINOS" remove grp/stale >/dev/null

# sync promotes a natively-woken idle seat (harness shows it running) to working.
NAT_UUID="aaaa1111-abab-4000-8000-0000000a1111"
"$SMINOS" seat add grp native --session "$NAT_UUID" >/dev/null   # status idle
{ echo "short=nat00001"; echo "uuid=$NAT_UUID"; echo "name=native"; echo "state=working"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/nat00001"
"$SMINOS" meta set native short nat00001 >/dev/null
run "$SMINOS" sync grp/native
assert_equals "$OUT" "live" "sync reports a natively-woken idle seat as live"
assert_equals "$(field "$NAT_UUID" status)" "working" "sync promotes the idle-but-running seat to working"
rm -f "$STUB_STATE/agents/nat00001"; "$SMINOS" remove grp/native >/dev/null

# wake socket-send failure falls through to the resume path (never raises).
FAIL_UUID="bbbb2222-abab-4000-8000-0000000b2222"
"$SMINOS" seat add grp flaky --session "$FAIL_UUID" >/dev/null
printf '{"pid":%s,"sessionId":"%s","name":"flaky","kind":"bg","status":"idle","messagingSocketPath":"%s"}\n' \
  "$$" "$FAIL_UUID" "$SOCK" > "$HOME/.claude/sessions/flaky.json"
kill "$SOCK_PID" 2>/dev/null || true; wait "$SOCK_PID" 2>/dev/null || true; rm -f "$SOCK"   # socket_ok now fails
run "$SMINOS" wake grp/flaky "PLEASE"
assert_rc 0 "$RC" "wake whose live socket vanished still exits 0 via the resume fallback"
assert_contains "$OUT" "via --bg --resume" "the vanished-socket wake fell through to resume"
rm -f "$HOME/.claude/sessions/flaky.json"; "$SMINOS" remove grp/flaky >/dev/null
# restart the socket server for any later use / clean teardown
python3 "$TEST_ROOT/sockserver.py" "$SOCK" "$RECEIVED" & SOCK_PID=$!; disown "$SOCK_PID"
for _ in $(seq 1 50); do [ -S "$SOCK" ] && break; sleep 0.05; done

# codex purge deletes the run-scratch set alongside the record.
CX_UUID="cccc3333-abab-4000-8000-0000000c3333"
mkdir -p "$TEST_ROOT/codexruns"
EL="$TEST_ROOT/codexruns/run-xyz.events.jsonl"
: > "$EL"; : > "$TEST_ROOT/codexruns/run-xyz.rc"; : > "$TEST_ROOT/codexruns/run-xyz.meta"
printf '{"uuid":"%s","name":"cx","alias":"cx","group":"grp","status":"retired","engine":"codex","event_log":"%s"}' \
  "$CX_UUID" "$EL" > "$SMINOS_HOME/$CX_UUID.json"
run "$SMINOS" retire grp/cx --purge
assert_rc 0 "$RC" "purging a codex seat exits 0"
assert_file_absent "$EL" "codex purge deletes the event log"
assert_file_absent "$TEST_ROOT/codexruns/run-xyz.rc" "codex purge deletes the run-scratch siblings"
assert_file_absent "$SMINOS_HOME/$CX_UUID.json" "codex purge removes the record"

# Stopping a LIVE legacy codex worker blocks on the wrapper's `.rc` barrier:
# until that file lands the finalizer can still rewrite the run scratch a
# retire or remove is about to purge. Here the barrier lands after ~1s.
CXB_UUID="2c2c1111-abab-4000-8000-00000002c2c1"
CXB_EL="$TEST_ROOT/codexruns/barrier.events.jsonl"
: > "$CXB_EL"; rm -f "$TEST_ROOT/codexruns/barrier.rc"
sleep 30 & CXB_PID=$!; disown "$CXB_PID"
( sleep 1; : > "$TEST_ROOT/codexruns/barrier.rc" ) & disown $!
printf '{"uuid":"%s","name":"cxb","alias":"cxb","group":"grp","status":"working","current":"%s","engine":"codex","pid":"%s","event_log":"%s","host":"testhost","boot_id":"boot-current"}' \
  "$CXB_UUID" "$CXB_UUID" "$CXB_PID" "$CXB_EL" > "$SMINOS_HOME/$CXB_UUID.json"
CXB_T0="$(python3 -c 'import time; print(time.time())')"
run "$SMINOS" retire grp/cxb
CXB_T1="$(python3 -c 'import time; print(time.time())')"
assert_rc 0 "$RC" "retiring a live legacy codex seat exits 0"
assert_file_exists "$TEST_ROOT/codexruns/barrier.rc" "the wrapper's .rc barrier is what released the retire"
assert_equals "$(python3 -c 'import sys; print("waited" if float(sys.argv[2]) - float(sys.argv[1]) >= 0.8 else "returned early")' "$CXB_T0" "$CXB_T1")" "waited" "the retire blocked until the .rc barrier appeared"
kill "$CXB_PID" 2>/dev/null || true
"$SMINOS" remove grp/cxb >/dev/null

# derive_group uses the OWNING repository, not a linked worktree's dir name.
REPO="$TEST_ROOT/myrepo"
mkdir -p "$REPO"; git init -q "$REPO"; git -C "$REPO" config user.email t@t; git -C "$REPO" config user.name t
git -C "$REPO" commit -q --allow-empty -m init
WTDIR="$REPO/.claude/worktrees/feat-x"
git -C "$REPO" worktree add -q "$WTDIR" -b wt-feat-x >/dev/null 2>&1
run "$SMINOS" spawn wtchild "WT-GROUP" --cwd "$WTDIR"
assert_rc 0 "$RC" "spawn in a linked worktree exits 0"
WC_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$WC_UUID" group)" "myrepo" "group derives from the owning repo, not the worktree dir"
"$SMINOS" remove "myrepo/wtchild" >/dev/null

# cwd that does not exist is refused (exit 2) — never HOME-substituted.
run "$SMINOS" spawn nodir "X" --group grp --cwd "$TEST_ROOT/does-not-exist"
assert_rc 2 "$RC" "spawn with a nonexistent cwd exits 2"
assert_contains "$OUT" "cwd does not exist" "the missing cwd is named"

# ---- 11b) exit-gate round 2 --------------------------------------------------
echo "exit-gate round 2:"

# Integration shape: spawn → retire → spawn (same alias). The second banner's
# bracket uuid is the record filename; attempts and history track the occupants.
run "$SMINOS" spawn resp "R-1" --group grp --role reviewer
RESP="$(seat_id_of resp)"
assert_equals "$(banner_uuid "$OUT")" "$RESP" "a new seat's banner bracket is its record filename"
RESP_FIRST="$(field "$RESP" current)"
# The pipeline stamps a failed occupant (retired_from + a note) before retiring
# it, and retire then writes status=retired over the failure — so the stamp and
# its note are the only surviving evidence that this occupant failed. History
# must carry both, or the outage streak forgets every retired failure.
"$SMINOS" mark resp error "worker died mid-run" >/dev/null
"$SMINOS" meta set resp retired_from failure >/dev/null
run "$SMINOS" retire resp
assert_rc 0 "$RC" "retire exits 0"
run "$SMINOS" spawn resp "R-2" --group grp
assert_rc 0 "$RC" "re-spawning a retired seat exits 0"
assert_equals "$(banner_uuid "$OUT")" "$RESP" "the re-spawn banner's bracket uuid equals the record filename"
assert_equals "$(field "$RESP" attempts)" "2" "attempts == 2 after one re-spawn"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0]["current"])' "$SMINOS_HOME/$RESP.json")" "$RESP_FIRST" "history[0].current is the first session"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0].get("retired_from",""))' "$SMINOS_HOME/$RESP.json")" "failure" "history[0] carries the predecessor's retired_from stamp"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0].get("note",""))' "$SMINOS_HOME/$RESP.json")" "worker died mid-run" "history[0] carries the note explaining the failure"
assert_equals "$(field "$RESP" retired_from)" "" "the re-filled record itself drops the predecessor's stamp"
assert_equals "$(field "$RESP" role)" "reviewer" "re-spawn without --role keeps the role"
"$SMINOS" remove grp/resp >/dev/null

# Re-fill of a legacy codex record clears its engine fields (the new occupant
# is a claude session) and drops the run scratch.
CXR_UUID="dddd4444-abab-4000-8000-0000000d4444"
: > "$TEST_ROOT/codexruns/cxr.events.jsonl"; : > "$TEST_ROOT/codexruns/cxr.rc"
printf '{"uuid":"%s","name":"cxr","alias":"cxr","group":"grp","status":"idle","current":"","engine":"codex","pid":"99999","event_log":"%s/codexruns/cxr.events.jsonl","cwd":"%s"}' \
  "$CXR_UUID" "$TEST_ROOT" "$WORK" > "$SMINOS_HOME/$CXR_UUID.json"
run "$SMINOS" spawn cxr "CLAUDE-NOW" --group grp
assert_rc 0 "$RC" "re-spawning a retired codex seat exits 0"
assert_equals "$(field "$CXR_UUID" engine)" "" "re-fill clears engine"
assert_equals "$(field "$CXR_UUID" pid)" "" "re-fill clears pid"
assert_equals "$(field "$CXR_UUID" event_log)" "" "re-fill clears event_log"
assert_file_absent "$TEST_ROOT/codexruns/cxr.rc" "re-fill drops the codex run scratch"
"$SMINOS" remove grp/cxr >/dev/null

# A vanished cwd refuses a resume (exit 2) without launching anything.
run "$SMINOS" spawn nocwd "N" --group grp
"$SMINOS" meta set nocwd cwd "$TEST_ROOT/vanished" >/dev/null
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$SMINOS" resume nocwd "x"
assert_rc 2 "$RC" "resume with a vanished cwd exits 2"
assert_contains "$OUT" "cwd does not exist" "the vanished cwd is named"
run "$SMINOS" wake nocwd "x"
assert_rc 2 "$RC" "wake-resume with a vanished cwd exits 2"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "nothing is launched for a vanished cwd"
"$SMINOS" meta set nocwd cwd "$WORK" >/dev/null; "$SMINOS" remove grp/nocwd >/dev/null

# Generation guard: a retire during a --wait watcher wins; the watcher writes
# neither status nor a reply over it.
( STUB_BG_STATE=working SMINOS_POLL_INTERVAL=0.1 DAEMON_TIMEOUT=20 "$SMINOS" spawn genseat "GEN" --group grp --wait > "$TEST_ROOT/gen.out" 2>&1; echo $? > "$TEST_ROOT/gen.rc" ) &
GENW=$!
sleep 0.8
GEN="$(seat_id_of genseat)"
run "$SMINOS" retire genseat
assert_rc 0 "$RC" "retire while a watcher waits exits 0"
wait "$GENW" || true
assert_equals "$(field "$GEN" status)" "retired" "the watcher's finalize does not overwrite a retire"
assert_file_absent "$SMINOS_HOME/$GEN.reply.txt" "no reply file is written over a retired seat"
"$SMINOS" remove grp/genseat >/dev/null

# resume: a refused or ineffective `claude stop` aborts before any launch.
STUB_BG_STATE=working run "$SMINOS" spawn stopper "S" --group grp
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
STUB_STOP_FAIL=1 run "$SMINOS" resume stopper "x"
assert_rc 1 "$RC" "a refused claude stop aborts the resume"
assert_contains "$OUT" "claude stop" "the stop failure is surfaced"
STUB_STOP_NOOP=1 SMINOS_STOP_TIMEOUT=0.3 run "$SMINOS" resume stopper "x"
assert_rc 1 "$RC" "a turn still running after the stop deadline aborts the resume"
assert_contains "$OUT" "still running" "the still-running turn is reported"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no resume is launched over a running turn"
"$SMINOS" remove grp/stopper >/dev/null

# wake respects the lifecycle lock.
python3 - "$(lock_file plainworker)" <<'PY' &
import fcntl, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
HOLDER=$!
sleep 0.4
run "$SMINOS" wake plainworker "x"
assert_rc 4 "$RC" "wake while the seat's lifecycle lock is held is refused"
kill "$HOLDER" 2>/dev/null || true; wait "$HOLDER" 2>/dev/null || true

# Peer liveness needs a listener: a socket FILE with nobody behind it is dead.
DEAD_UUID="ffff5555-abab-4000-8000-0000000f5555"
"$SMINOS" seat add grp deadsock --session "$DEAD_UUID" >/dev/null
: > "$TEST_ROOT/dead.sock"
printf '{"pid":%s,"sessionId":"%s","name":"deadsock","kind":"bg","status":"idle","messagingSocketPath":"%s/dead.sock"}\n' \
  "$$" "$DEAD_UUID" "$TEST_ROOT" > "$HOME/.claude/sessions/deadsock.json"
run "$SMINOS" fill grp/deadsock "REFILL" --resume
assert_rc 0 "$RC" "a peer whose socket file has no listener is not live — resume proceeds"
rm -f "$HOME/.claude/sessions/deadsock.json"; "$SMINOS" remove grp/deadsock >/dev/null

# seat add --session records the harness row's short, and clears it when the row is gone.
SA_UUID="abcd6666-abab-4000-8000-000000ab6666"
{ echo "short=sa000001"; echo "uuid=$SA_UUID"; echo "name=sadd"; echo "kind=interactive"; echo "state="; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/sa000001"
"$SMINOS" seat add grp sadd --session "$SA_UUID" >/dev/null
assert_equals "$(field "$SA_UUID" short)" "sa000001" "seat add --session records the current short from the harness"
rm -f "$STUB_STATE/agents/sa000001"
"$SMINOS" seat add grp sadd --session "$SA_UUID" >/dev/null
assert_equals "$(field "$SA_UUID" short)" "" "seat add --session clears a short the harness no longer shows"
"$SMINOS" remove grp/sadd >/dev/null

# Socket delivery that fails BEFORE the frame is written falls through to a
# resume; a failure AFTER the frame is written is 'uncertain' and never resumes.
cat > "$TEST_ROOT/oneshot.py" <<'PY'
import os, socket, sys
path = sys.argv[1]
try:
    os.unlink(path)
except FileNotFoundError:
    pass
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(path); srv.listen(1)
c, _ = srv.accept()          # the liveness probe
os.unlink(path)              # nobody can connect after this
c.close(); srv.close()
PY
OS_UUID="0a0a7777-abab-4000-8000-0000000a7777"
"$SMINOS" seat add grp oneshot --session "$OS_UUID" >/dev/null
python3 "$TEST_ROOT/oneshot.py" "$TEST_ROOT/oneshot.sock" & OS_PID=$!; disown "$OS_PID"
for _ in $(seq 1 50); do [ -S "$TEST_ROOT/oneshot.sock" ] && break; sleep 0.05; done
printf '{"pid":%s,"sessionId":"%s","name":"oneshot","kind":"bg","status":"idle","messagingSocketPath":"%s/oneshot.sock"}\n' \
  "$OS_PID" "$OS_UUID" "$TEST_ROOT" > "$HOME/.claude/sessions/oneshot.json"
run "$SMINOS" wake grp/oneshot "HELLO"
assert_rc 0 "$RC" "a socket that vanishes before the frame is written falls through to resume (exit 0)"
assert_contains "$OUT" "failed before the frame was written" "the pre-write failure is explained"
assert_contains "$OUT" "via --bg --resume" "the wake completed via resume"
rm -f "$HOME/.claude/sessions/oneshot.json"; "$SMINOS" remove grp/oneshot >/dev/null
AFTER_PHASE="$(python3 - "$REPO_ROOT/skills/sminos/scripts" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import sminos
class Fake:
    def settimeout(self, t): pass
    def connect(self, p): pass
    def sendall(self, b): pass
    def shutdown(self, how): raise OSError("reset after write")
    def recv(self, n): return b""
    def close(self): pass
sminos.socket.socket = lambda *a, **k: Fake()
try:
    sminos.send_frame("/nowhere", "t")
    print("none")
except sminos.SendFailed as e:
    print(e.phase)
PY
)"
assert_equals "$AFTER_PHASE" "after" "a close-out failure after the frame was written is the 'after' phase"

# Round 3: sender identity derives from CLAUDE_CODE_SESSION_ID when present.
# (The socket server was restarted above; re-point the orchestrator's peer
# record at its current pid so the seat is live again.)
rm -f "$HOME/.claude/sessions/"*.json
printf '{"pid":%s,"sessionId":"%s","name":"my session","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$ORCH_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/$SOCK_PID.json"
run "$SMINOS" send orchestrator "from a terminal"
assert_rc 0 "$RC" "send without a session id in the environment exits 0"
sleep 0.2
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from human]' "no session id in the environment → human"
ID_UUID="0b0b8888-abab-4000-8000-0000000b8888"
"$SMINOS" seat add grp me-agent --parent orchestrator --session "$ID_UUID" >/dev/null
CLAUDE_CODE_SESSION_ID="$ID_UUID" run "$SMINOS" send orchestrator "from an agent"
assert_rc 0 "$RC" "send from a registered agent session exits 0"
sleep 0.2
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from me-agent]' "an agent's default --from is its seat alias"
CLAUDE_CODE_SESSION_ID="$ID_UUID" run "$SMINOS" send orchestrator "impostor" --from human
assert_rc 4 "$RC" "--from human inside a Claude session is refused"
CLAUDE_CODE_SESSION_ID="$ID_UUID" run "$SMINOS" post grp "agent note"
assert_rc 0 "$RC" "post from an agent session defaults --from to its alias"
run "$SMINOS" board grp -n 1
assert_contains "$OUT" 'from="me-agent"' "the post is stamped with the agent's alias"
CLAUDE_CODE_SESSION_ID="$ID_UUID" run "$SMINOS" post grp "impostor" --from human
assert_rc 4 "$RC" "post --from human inside a Claude session is refused"
"$SMINOS" remove grp/me-agent >/dev/null
run "$SMINOS" spawn me-agent "NON-FAMILY-IDENTITY"  # no explicit group, no preamble
PLAIN_ME="$(banner_uuid "$OUT")"
CLAUDE_CODE_SESSION_ID="$PLAIN_ME" run "$SMINOS" send orchestrator "from a pipeline root"
assert_rc 0 "$RC" "a non-family seat still sends to an unrelated seat"
sleep 0.2
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from me-agent]' "a non-family seat still derives sender alias"
"$SMINOS" remove work/me-agent >/dev/null

# A harness failure is 'unknown', never an empty fleet.
STUB_AGENTS_FAIL=1 run "$SMINOS" list grp
assert_rc 0 "$RC" "list still runs when the harness fails"
assert_contains "$OUT" "unknown" "list shows unknown liveness when claude agents fails"
STUB_BG_STATE=working run "$SMINOS" spawn unk "U" --group grp
STUB_AGENTS_FAIL=1 run "$SMINOS" sync unk
assert_equals "$OUT" "live" "sync claims nothing (live) when the harness fails"
assert_equals "$(field "$(seat_id_of unk)" status)" "working" "a harness failure never finalizes a seat"
"$SMINOS" remove grp/unk >/dev/null

# A previous occupant that still answers blocks a fresh re-fill.
PO_UUID="0c0c9999-abab-4000-8000-0000000c9999"
"$SMINOS" seat add grp prevocc --session "$PO_UUID" >/dev/null
"$SMINOS" mark prevocc retired >/dev/null
printf '{"pid":%s,"sessionId":"%s","name":"prevocc","kind":"bg","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$PO_UUID" "$SOCK" > "$HOME/.claude/sessions/prevocc.json"
run "$SMINOS" spawn prevocc "again" --group grp
assert_rc 4 "$RC" "re-spawn is refused while the previous occupant still answers"
assert_contains "$OUT" "previous occupant" "the live previous occupant is named"
run "$SMINOS" fill grp/prevocc "again"
assert_rc 4 "$RC" "fresh fill is refused while the previous occupant still answers"
rm -f "$HOME/.claude/sessions/prevocc.json"; "$SMINOS" remove grp/prevocc >/dev/null

# Repointing a seat whose occupant is STILL LIVE would leave that process
# running with nothing in the fleet naming it: refused for a new --addr and for
# a new --session alike, and the record is left exactly as it was.
RPT_UUID="0e0ebbbb-abab-4000-8000-0000000ebbbb"
"$SMINOS" seat add grp pinned --session "$RPT_UUID" >/dev/null
# The live session answers to the harness name it already had (a `seat add
# --session` seat was never named by sminos), so the machine-wide name check
# cannot see it — only the record ties the process to the fleet.
printf '{"pid":%s,"sessionId":"%s","name":"a name sminos never chose","kind":"interactive","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$RPT_UUID" "$SOCK" > "$HOME/.claude/sessions/pinned.json"
run "$SMINOS" seat add grp pinned --addr "pinned elsewhere"
assert_rc 4 "$RC" "re-addressing a seat whose session is still live is refused"
assert_contains "$OUT" "still holds a live session" "the refusal names the live session"
assert_equals "$(printf '%s' "$OUT" | grep -c .)" "1" "the refusal is one stderr line"
assert_equals "$(field "$RPT_UUID" addr)" "pinned" "the refused re-address left the addr untouched"
run "$SMINOS" seat add grp pinned --session "0e0ecccc-abab-4000-8000-0000000ecccc"
assert_rc 4 "$RC" "re-pointing a live seat at another session is refused too"
assert_equals "$(field "$RPT_UUID" current)" "$RPT_UUID" "the refused re-point left the session untouched"
rm -f "$HOME/.claude/sessions/pinned.json"
run "$SMINOS" seat add grp pinned --addr "pinned elsewhere"
assert_rc 0 "$RC" "once the occupant is gone the same re-address succeeds"
assert_equals "$(field "$RPT_UUID" addr)" "pinned elsewhere" "and the new addr is recorded"
"$SMINOS" remove grp/pinned >/dev/null

# harness_row prefers a RUNNING row for the session over the recorded short.
HR_UUID="0d0daaaa-abab-4000-8000-0000000daaaa"
"$SMINOS" seat add grp revived --session "$HR_UUID" >/dev/null
"$SMINOS" meta set revived short hr000001 >/dev/null
{ echo "short=hr000001"; echo "uuid=$HR_UUID"; echo "name=revived"; echo "state=stopped"; echo "status="; echo "cwd=$WORK"; } > "$STUB_STATE/agents/hr000001"
{ echo "short=hr000002"; echo "uuid=$HR_UUID"; echo "name=revived"; echo "state=working"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/hr000002"
run "$SMINOS" list grp
assert_contains "$(printf '%s' "$OUT" | grep '^revived')" "busy" "an out-of-band revival's running row wins over the stale recorded short"
rm -f "$STUB_STATE/agents/hr000001" "$STUB_STATE/agents/hr000002"; "$SMINOS" remove grp/revived >/dev/null

# peer liveness: a recycled pid (procStart differs from the live process) is dead.
RP_UUID="0e0ebbbb-abab-4000-8000-0000000ebbbb"
printf '{"pid":%s,"sessionId":"%s","name":"recycled","kind":"bg","status":"idle","procStart":"Mon Jan  1 00:00:00 1990","messagingSocketPath":"%s"}\n' \
  "$$" "$RP_UUID" "$SOCK" > "$HOME/.claude/sessions/recycled.json"
run "$SMINOS" spawn recycled "R" --group grp
assert_rc 0 "$RC" "a peer record whose procStart does not match the live pid does not block the name"
"$SMINOS" remove grp/recycled >/dev/null
LSTART="$(LC_ALL=C ps -o lstart= -p $$ | sed 's/  */ /g;s/^ //;s/ $//')"
printf '{"pid":%s,"sessionId":"%s","name":"recycled","kind":"bg","status":"idle","procStart":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$RP_UUID" "$LSTART" "$SOCK" > "$HOME/.claude/sessions/recycled.json"
run "$SMINOS" spawn recycled "R" --group grp
assert_rc 4 "$RC" "a peer record whose procStart matches the live pid is live and blocks the name"
rm -f "$HOME/.claude/sessions/recycled.json"

# status / mark / meta set never resurrect a removed seat (unit level).
RES_OUT="$(python3 - "$REPO_ROOT/skills/sminos/scripts" <<'PY'
import os, sys
sys.path.insert(0, sys.argv[1])
import sminos
sid = "0f0fcccc-abab-4000-8000-0000000fcccc"
w = sminos.meta_set(sid, {"now": "x"}, bump=False, create=False)
print("wrote" if w else "refused", "exists" if os.path.exists(sminos.meta_path(sid)) else "absent")
PY
)"
assert_equals "$RES_OUT" "refused absent" "a create=False write on a missing record writes nothing and creates nothing"

# send to a raw harness name: a SendFailed before the write is 'not live' (exit
# 4); after the write it is 'uncertain' (exit 1). Driven at unit level — the
# failure is injected into send_frame, so no timing race decides the outcome.
printf '{"pid":%s,"sessionId":"1a1adddd-abab-4000-8000-0000001adddd","name":"rawname","kind":"interactive","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$SOCK" > "$HOME/.claude/sessions/rawname.json"
RAW_CODES="$(python3 - "$REPO_ROOT/skills/sminos/scripts" <<'PY'
import argparse, sys
sys.path.insert(0, sys.argv[1])
import sminos
codes = []
for phase in ("before", "after"):
    def boom(path, text, phase=phase):
        raise sminos.SendFailed(phase, OSError("injected"))
    sminos.send_frame = boom
    try:
        sminos.cmd_send(argparse.Namespace(target="rawname", msg="x", frm=""))
        codes.append("0")
    except SystemExit as e:
        codes.append(str(e.code))
print(" ".join(codes))
PY
)"
assert_equals "$RAW_CODES" "4 1" "raw-name send: failure before the write exits 4, after the write exits 1"
rm -f "$HOME/.claude/sessions/rawname.json"

# retire hint for a legacy codex record.
CXH_UUID="1b1beeee-abab-4000-8000-0000001beeee"
printf '{"uuid":"%s","name":"cxh","alias":"cxh","group":"grp","status":"idle","current":"%s","engine":"codex","pid":"99999"}' "$CXH_UUID" "$CXH_UUID" > "$SMINOS_HOME/$CXH_UUID.json"
run "$SMINOS" retire grp/cxh
assert_contains "$OUT" "no resume path; remove with: sminos remove grp/cxh" "retire of a codex record hints at remove, not fill --resume"
"$SMINOS" remove grp/cxh >/dev/null

# Aside merge: a colliding board is appended with renumbered ids; any other
# collision is left in place and warned about on every run.
AM="$TEST_ROOT/asidehome"
mkdir -p "$AM/.claude/sminos/groups/g1" "$AM/.claude/sminos.v2-20260101T000000Z/groups/g1" "$AM/.claude/sminos.v2-20260101T000000Z/groups/g1/nodes"
printf '{"id":1,"ts":"t","from":"human","title":"","cwd":"/","branch":"","text":"root one"}\n' > "$AM/.claude/sminos/groups/g1/board.jsonl"
printf '{"id":1,"ts":"t","from":"human","title":"","cwd":"/","branch":"","text":"aside one"}\n{"id":2,"ts":"t","from":"human","title":"","cwd":"/","branch":"","text":"aside two"}\n' > "$AM/.claude/sminos.v2-20260101T000000Z/groups/g1/board.jsonl"
printf 'root notes\n' > "$AM/.claude/sminos/groups/g1/notes.txt"   # a colliding non-board entry
printf 'aside notes\n' > "$AM/.claude/sminos.v2-20260101T000000Z/groups/g1/notes.txt"
rmdir "$AM/.claude/sminos.v2-20260101T000000Z/groups/g1/nodes"
run env -u SMINOS_HOME HOME="$AM" "$SMINOS" board g1 --json
assert_equals "$(printf '%s' "$OUT" | grep -c '"id"')" "3" "aside board posts are appended to the root board"
assert_contains "$OUT" '"id": 3' "appended posts are renumbered after the root's last id"
assert_contains "$OUT" "aside two" "the aside's posts survive the merge"
assert_contains "$OUT" "unmerged aside entry left in place" "a non-board collision is warned about"
run env -u SMINOS_HOME HOME="$AM" "$SMINOS" groups
assert_contains "$OUT" "unmerged aside entry left in place" "the warning repeats on every run until resolved"

# lib.sh creates the root 0700 and tightens a wide one.
LIBROOT="$TEST_ROOT/libroot"
( SMINOS_HOME="$LIBROOT" bash -c "source '$REPO_ROOT/skills/sminos/scripts/lib.sh'" )
assert_equals "$(mode_of "$LIBROOT")" "0700" "lib.sh creates the registry root 0700"
chmod 755 "$LIBROOT"
( SMINOS_HOME="$LIBROOT" bash -c "source '$REPO_ROOT/skills/sminos/scripts/lib.sh'" )
assert_equals "$(mode_of "$LIBROOT")" "0700" "lib.sh tightens a wide root to 0700"

# ---- 12) remove --------------------------------------------------------------
echo "remove:"
run "$SMINOS" remove grp/scribe
assert_rc 0 "$RC" "remove exits 0"
run "$SMINOS" list grp
assert_not_contains "$OUT" "scribe" "removed seat is gone"

# ---- 13) chart: the box organisation chart ----------------------------------
# The `org` fixture below is shared with the tui tests that follow it: a lead
# (busy) with three children — scout (idle, live peer), scribe (busy) with a
# vacant intern under it, qa (blocked) — and a retired old-worker folded away.
echo "chart:"
LEAD_UUID=cccc0001-0000-4000-8000-00000000c001
SCOUT_UUID=cccc0002-0000-4000-8000-00000000c002
SCRIBE_UUID=cccc0003-0000-4000-8000-00000000c003
QA_UUID=cccc0004-0000-4000-8000-00000000c004
{ echo "short=cc000001"; echo "uuid=$LEAD_UUID"; echo "name=lead"; echo "state=working"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000001"
{ echo "short=cc000002"; echo "uuid=$SCOUT_UUID"; echo "name=scout"; echo "state=done"; echo "status="; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000002"
{ echo "short=cc000003"; echo "uuid=$SCRIBE_UUID"; echo "name=scribe"; echo "state=working"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000003"
{ echo "short=cc000004"; echo "uuid=$QA_UUID"; echo "name=qa"; echo "state=blocked"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000004"
# scout is idle: a finished row plus a live peer record whose socket answers.
printf '{"pid":%s,"sessionId":"%s","name":"scout","kind":"background","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$SCOUT_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/org-scout.json"
# Blocked counts as live only while a peer process answers its socket.
printf '{"pid":%s,"sessionId":"%s","name":"qa","kind":"background","status":"busy","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$QA_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/org-qa.json"
"$SMINOS" seat add org lead --role LEAD --session "$LEAD_UUID" >/dev/null
"$SMINOS" seat add org scout --role RES --parent lead --session "$SCOUT_UUID" >/dev/null
"$SMINOS" seat add org scribe --role DOC --parent lead --session "$SCRIBE_UUID" >/dev/null
"$SMINOS" seat add org intern --parent scribe >/dev/null
"$SMINOS" seat add org qa --role QA --parent lead --session "$QA_UUID" >/dev/null
"$SMINOS" seat add org old-worker --parent lead >/dev/null
"$SMINOS" mark org/old-worker retired >/dev/null
"$SMINOS" status org/scribe "notes → board" >/dev/null
"$SMINOS" status org/scout "스펙 읽는 중 어쩌구저쩌구 매우 긴 문장입니다" >/dev/null

# boxcheck: every row of the box holding <marker> has its left and right
# borders in the same display columns (Korean counts two cells).
cat > "$TEST_ROOT/boxcheck.py" <<'PY'
import sys, unicodedata
marker = sys.argv[1]
rows = sys.stdin.read().split("\n")
def cw(ch): return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
def col(row, idx): return sum(cw(c) for c in row[:idx])
def at_col(row, c):
    x = 0
    for ch in row:
        if x == c: return ch
        x += cw(ch)
    return ""
r = next(i for i, row in enumerate(rows) if marker in row)
i = rows[r].index(marker)
li = rows[r].rindex("│", 0, i); ri = rows[r].index("│", i)
L, R = col(rows[r], li), col(rows[r], ri)
ok = all(at_col(rows[r + k], L) == "│" and at_col(rows[r + k], R) == "│" for k in (1, 2))
ok = ok and at_col(rows[r - 1], L) in "┌┏╭" and at_col(rows[r - 1], R) in "┐┓╮"
ok = ok and at_col(rows[r + 3], L) in "└┗╰" and at_col(rows[r + 3], R) in "┘┛╯"
print("aligned" if ok else "misaligned:\n" + "\n".join(rows[r - 1:r + 4]))
PY

run "$SMINOS" chart org --width 120
assert_rc 0 "$RC" "chart of a group exits 0"
CHART="$OUT"
assert_contains "$(printf '%s\n' "$CHART" | grep -c 'lead .*LEAD')" "1" "alias left and ROLE right share the first box line"
assert_contains "$CHART" "● busy" "busy seat shows the filled glyph"
assert_contains "$CHART" "○ idle" "idle seat (live peer) shows the hollow glyph"
assert_contains "$CHART" "◐ blocked" "blocked seat shows the half glyph"
assert_contains "$CHART" "◌ vacant" "vacant seat shows the dotted glyph"
assert_not_contains "$CHART" "old-worker" "a retired seat is folded away by default"
assert_contains "$CHART" "+1 retired" "the parent notes its folded children"
assert_equals "$(( $(printf '%s\n' "$CHART" | grep -n '+1 retired' | cut -d: -f1) - $(printf '%s\n' "$CHART" | grep -n 'lead .*LEAD' | cut -d: -f1) ))" "2" "the retired note sits on the lead box's third line"
assert_contains "$CHART" "notes → board" "a seat's now line is drawn on its third line"
assert_contains "$CHART" "│─┼──│" "a parent centred on three children meets the bus at the middle child"
assert_contains "$CHART" "┌──│" "the first child opens the bus"
assert_contains "$CHART" "└──│" "the last child closes the bus"
assert_contains "$CHART" "6 seats · 4 live · 1 hidden (sminos chart org --all)" "summary counts seats, live, hidden and points at --all"
assert_equals "$(printf '%s\n' "$CHART" | python3 "$TEST_ROOT/boxcheck.py" scout)" "aligned" "a Korean now line keeps the box borders aligned"
assert_equals "$(printf '%s\n' "$CHART" | python3 "$TEST_ROOT/boxcheck.py" lead)" "aligned" "an ASCII box is aligned too"
assert_contains "$CHART" "…" "an over-long now line is truncated with an ellipsis"
# intern sits one column to the right of scribe; scribe one to the right of lead.
assert_equals "$(printf '%s\n' "$CHART" | python3 -c '
import sys
rows = sys.stdin.read().split("\n")
def x(m): return next(r.index(m) for r in rows if m in r)
print(x("lead ") < x("scribe ") < x("intern "))')" "True" "children are laid out to the right of their parent"
run "$SMINOS" chart org --all --width 120
assert_contains "$OUT" "old-worker" "--all shows the retired seat"
assert_not_contains "$OUT" "hidden" "--all summary has nothing hidden"
run "$SMINOS" chart --width 200
assert_rc 0 "$RC" "fleet chart exits 0"
assert_contains "$OUT" "╭" "fleet chart draws groups as rounded boxes"
assert_contains "$(printf '%s\n' "$OUT" | grep -c '│ org ')" "1" "the org group is a root box"
assert_contains "$OUT" "6 seats · 4 live" "the group box counts its seats and live seats"
assert_contains "$OUT" "groups ·" "fleet summary counts groups"
run "$SMINOS" chart nope
assert_rc 4 "$RC" "chart of an unknown group exits 4"
run "$SMINOS" chart bad/name
assert_rc 2 "$RC" "chart of a bad group name exits 2"

# ---- 14) tui: the interactive chart, driven headlessly -----------------------
# `sminos tui --headless --keys …` runs the same state machine the curses screen
# runs, then prints the final grid, `--- focus: <id>`, and the actions it would
# have taken (attach) or did take (send, over the real launcher). Reuses the
# org fixture from section 13: lead's visible children in alias order are qa,
# scout, scribe; intern hangs under scribe; old-worker is folded away.
echo "tui:"
TUI="$SMINOS tui org --headless --width 110 --height 34"
run $TUI
assert_rc 0 "$RC" "headless tui exits 0"
assert_contains "$OUT" "--- focus: org/lead" "the first root is focused by default"
assert_contains "$OUT" "┏━━" "the focused box has heavy borders"
assert_contains "$OUT" "sminos · org · 6 seats · 4 live · 1 hidden · a" "the header carries the counts and the hidden hint"
assert_contains "$OUT" "── detail ──" "the detail panel is shown by default"
assert_contains "$OUT" "org/lead · LEAD · seat cccc0001 · session cccc0001" "the detail panel names the focused seat, role, seat and session"
assert_contains "$OUT" "● busy · status idle · short cc000001" "the detail panel shows live state, recorded status and the short id"
assert_contains "$OUT" "enter attach · s send · b board" "the footer lists the keys"
run $TUI --keys right
assert_contains "$OUT" "--- focus: org/qa" "right enters the first (topmost) child"
run $TUI --keys "right,down"
assert_contains "$OUT" "--- focus: org/scout" "down moves to the next box in the same column"
run $TUI --keys "right,down,down,down"
assert_contains "$OUT" "--- focus: org/scribe" "down past the last box stays put"
run $TUI --keys "right,down,down,right"
assert_contains "$OUT" "--- focus: org/intern" "right from scribe reaches intern"
run $TUI --keys "right,down,down,right,left"
assert_contains "$OUT" "--- focus: org/scribe" "left returns to the parent"
run $TUI --keys "right,down,down,right,home"
assert_contains "$OUT" "--- focus: org/lead" "home returns to the first root"
run $TUI --keys "right,down,enter"
assert_contains "$OUT" "attach org/scout cc000002 → claude attach cc000002" "enter on a live seat records the attach against the qualified seat and the harness short id"
assert_contains "$OUT" "would run: claude attach cc000002" "the footer flashes the attach command"
run $TUI --keys "right,down,down,right,enter"
assert_not_contains "$OUT" "attach intern" "enter on a vacant seat attaches nothing"
assert_contains "$OUT" "intern is vacant — no session to attach; sminos fill org/intern" "the footer explains the vacant seat and names the fill command"
run $TUI --keys "right,down,enter" --no-tmux
assert_contains "$OUT" "→ claude attach cc000002" "--no-tmux still records the plain attach command"
run $TUI --keys a
assert_contains "$OUT" "old-worker" "a shows the folded retired seat"
assert_contains "$OUT" "all shown · a" "the header notes that hidden seats are shown"
run $TUI --keys "a,a"
assert_not_contains "$OUT" "old-worker" "a again hides it"
run $TUI --keys s
assert_contains "$OUT" "send → org/lead ▏" "s on a live seat opens the send line naming the target"
run $TUI --keys "s,text:abc,backspace,text:d"
assert_contains "$OUT" "send → org/lead ▏abd" "typing and backspace edit the send line"
run $TUI --keys "s,text:abc,esc"
assert_not_contains "$OUT" "send → org/lead" "esc cancels the send line"
assert_contains "$OUT" "enter attach · s send" "and the footer shows the keys again"
run $TUI --keys "right,down,down,right,s"
assert_contains "$OUT" "intern is vacant — enter attaches (and wakes) a stopped seat; a vacant or gone seat needs sminos fill" "s on a vacant seat refuses with the reason"
assert_not_contains "$OUT" "send →" "and opens no send line"
run $TUI --keys "right,down,s,text:ping-from-tui here,enter"
assert_contains "$OUT" "send scout ping-from-tui here → rc=0 sent to org/scout (scout)" "enter on the send line delivers through the real launcher and records the result"
assert_contains "$(cat "$RECEIVED")" "[sminos message from human]\nping-from-tui here" "the frame reached the seat's inbox socket with the human sender line"
run $TUI --keys b
assert_contains "$OUT" "── board · org · 0 posts · tab to browse ──" "b switches the panel to the group board"
assert_contains "$OUT" "(no posts)" "an empty board says so"
"$SMINOS" post org --title "Kickoff" "hello board from the tui test" >/dev/null
run $TUI --keys b
assert_contains "$OUT" "board · org · 1 post ·" "the board panel counts posts"
assert_contains "$OUT" "#1    " "the board panel lists the post id"
assert_contains "$OUT" "Kickoff" "and its title"
run $TUI --keys "b,tab"
assert_contains "$OUT" "↑↓ enter opens · tab back" "tab moves the keys into the board list"
run $TUI --keys "b,tab,enter"
assert_contains "$OUT" "#1 · human · " "enter on a board row opens the post overlay with its header"
assert_contains "$OUT" "hello board from the tui test" "the overlay shows the post body"
assert_contains "$OUT" "esc closes" "the overlay says how to close"
run $TUI --keys "b,tab,enter,esc"
assert_not_contains "$OUT" "esc closes" "esc closes the overlay"
run $TUI --keys "b,tab,tab,right"
assert_contains "$OUT" "--- focus: org/qa" "tab again hands the keys back to the chart"
run $TUI --keys "?"
assert_contains "$OUT" "┃ keys" "? opens the help overlay"
assert_contains "$OUT" "a — show / hide retired, failed and gone seats" "the help lists the keys"
run $TUI --keys "?,q,right"
assert_contains "$OUT" "--- focus: org/qa" "q inside the overlay only closes it"
run $TUI --keys q
assert_contains "$OUT" "--- quit" "q quits"
run $TUI --keys r
assert_rc 0 "$RC" "r refreshes without error"
assert_contains "$OUT" "--- focus: org/lead" "and keeps the focus"
run "$SMINOS" tui org --headless --width 60 --height 14 --keys "right,down,down,right"
assert_rc 0 "$RC" "a 60x14 terminal renders"
assert_contains "$OUT" "┃ intern       ┃" "the viewport scrolls so the focused box is on screen"
assert_not_contains "$OUT" "── detail ──" "the panel collapses below 16 rows"
run "$SMINOS" tui --headless --width 120 --height 40
assert_rc 0 "$RC" "fleet tui exits 0"
assert_contains "$OUT" "sminos · fleet · " "the fleet header names the fleet"
assert_contains "$OUT" "seats · " "the focused group box is on screen even when its children fill the top of the viewport"
run "$SMINOS" tui --headless --width 120 --height 160
assert_contains "$OUT" "╭" "unfocused groups are rounded boxes"
assert_equals "$(printf '%s\n' "$OUT" | sed -n 's/^--- focus: //p' | grep -c '/')" "0" "the default fleet focus is a group box"
run "$SMINOS" tui --headless --width 120 --height 40 --keys enter
assert_contains "$OUT" "▸ " "enter on a group collapses it"
# A `!` token in --keys is a DRIVER instruction, not a keystroke: it does what
# only the refresh thread does in a live screen. !focus moves the focus (a
# rebuild does that when the focused seat disappears); !drop removes a box from
# the layout (a snapshot does that when a seat is retired mid-turn).
run $TUI --keys "right,down,s,text:bound,!focus:org/qa,enter"
assert_contains "$OUT" "send scout bound → rc=0 sent to org/scout" "a composed message goes to the seat that was focused when the editor opened, not to wherever the focus moved"
assert_contains "$OUT" "--- focus: org/qa" "even though the focus did move"
run $TUI --keys "right,down,s,text:gone,!drop:org/scout,enter"
assert_contains "$OUT" "org/scout is no longer on the chart — nothing was sent" "a message is dropped, with a reason, when its target leaves the chart while it is being typed"
assert_equals "$(printf '%s\n' "$OUT" | sed -n '/^--- actions:/,$p' | tail -n +2 | wc -l | tr -d ' ')" "0" "and nothing is sent"
run $TUI --keys "s,text:x"
assert_contains "$OUT" "send → org/lead ▏x" "the send line names the captured target"

# A dead seat under a dead seat: the parent's note must count the whole folded
# subtree, not just its direct child, or the box and the summary disagree.
"$SMINOS" seat add org old-helper --parent old-worker >/dev/null
"$SMINOS" mark org/old-helper retired >/dev/null
run "$SMINOS" chart org --width 120
assert_contains "$OUT" "+2 retired" "a folded subtree counts every seat in it"
assert_contains "$OUT" "7 seats · 4 live · 2 hidden" "and the summary agrees with the box"
"$SMINOS" remove org/old-helper >/dev/null

run "$SMINOS" tui nope --headless
assert_rc 4 "$RC" "tui of an unknown group exits 4"
run "$SMINOS" tui bad/name --headless
assert_rc 2 "$RC" "tui of a bad group name exits 2"
run "$SMINOS" tui org
assert_rc 2 "$RC" "tui without a terminal exits 2"
assert_contains "$OUT" "sminos tui needs a terminal — for text use: sminos chart org" "and points at chart"

fi # existing fleet tests; family-only runs skip to the focused section

# ---- family chat --------------------------------------------------------------
echo "family chat:"
export SMINOS_HOME="$TEST_ROOT/family-registry"
mkdir -p "$SMINOS_HOME"
rm -f "$HOME/.claude/sessions/"*.json
cd "$WORK"
run "$SMINOS" seat add fam lead --session 11111111-aaaa-4000-8000-000000000001
LEAD=11111111-aaaa-4000-8000-000000000001
run "$SMINOS" seat add fam a --parent lead --session 22222222-aaaa-4000-8000-000000000002
A=22222222-aaaa-4000-8000-000000000002
run "$SMINOS" seat add fam b --parent lead --session 33333333-aaaa-4000-8000-000000000003
B=33333333-aaaa-4000-8000-000000000003
run "$SMINOS" seat add other x --session 44444444-aaaa-4000-8000-000000000004
X=44444444-aaaa-4000-8000-000000000004
printf '{"pid":%s,"sessionId":"%s","name":"lead","status":"idle","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$LEAD" "$SOCK" > "$HOME/.claude/sessions/lead.json"
printf 'short=bbbb0003\nuuid=%s\nname=b\nstate=stopped\nstatus=\ncwd=%s\n' "$B" "$WORK" > "$STUB_STATE/agents/bbbb0003"
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" say 'schema done'
assert_rc 0 "$RC" "untagged family report records"
assert_contains "$OUT" 'lead: sent' "report pushes to host"
CHAT="$SMINOS_HOME/chats/$LEAD.jsonl"
assert_equals "$(mode_of "$CHAT")" 0600 "chat record is private"
assert_contains "$(cat "$CHAT")" '"mode": "host"' "report mode is host"
assert_contains "$(cat "$CHAT")" '"lead": "sent"' "report delivery is stored"
assert_contains "$(cat "$RECEIVED")" '[sminos chat lead #1 from a \u2192 lead]' "host receives framed report"
run "$SMINOS" say '@b your migration renames my column'
assert_rc 0 "$RC" "tag to stopped sibling is recorded"
assert_contains "$OUT" 'b: woken' "tag resumes stopped sibling"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "--bg --resume $B" "resume uses saved session"
run "$SMINOS" say '@all standup'
assert_rc 0 "$RC" "broadcast is recorded"
assert_contains "$OUT" 'b: recorded' "stopped sibling stays stopped on broadcast"
assert_equals "$(python3 -c 'import json,sys; print([json.loads(x)["id"] for x in open(sys.argv[1])])' "$CHAT")" '[1, 2, 3]' "chat ids increase"
# A live socket for b makes the host's untagged team message and a later tag push.
printf '{"pid":%s,"sessionId":"%s","name":"b","status":"idle","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$B" "$SOCK" > "$HOME/.claude/sessions/b.json"
export CLAUDE_CODE_SESSION_ID="$LEAD"
run "$SMINOS" say 'merge b first'
assert_rc 0 "$RC" "root host speaks to team"
assert_contains "$OUT" 'b: sent' "team reaches live child"
assert_contains "$(tail -1 "$CHAT")" '"mode": "team"' "team mode recorded"
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" say '@b check again'
assert_rc 0 "$RC" "tagged sibling message delivers"
assert_contains "$(cat "$RECEIVED")" '[sminos chat lead #5 from a \u2192 @b | unread 2]' "unread excludes previously pushed messages"
assert_equals "$(field "$B" chat_seen)" '' "a pushed message does not mark history read"
export CLAUDE_CODE_SESSION_ID="$B"
run "$SMINOS" chat -n 30
assert_contains "$OUT" 'chat lead (fam) · members: lead, a, b · 5 messages' "chat reads complete history"
assert_contains "$OUT" '→ @b' "tagged chat entry marks its recipient"
assert_contains "$(field "$B" chat_seen)" "$LEAD\": 5" "chat read advances watermark"
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" say '@b final'
assert_not_contains "$(cat "$RECEIVED")" '[sminos chat lead #6 from a → @b | unread' "read clears unread count"
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "lead"' "family list includes parent"
assert_not_contains "$OUT" '"alias": "x"' "family list excludes other group"
for target in other/x "$X" rawname codex:thread; do
  run "$SMINOS" send "$target" hi
  assert_rc 4 "$RC" "family send refuses $target"
  assert_contains "$OUT" 'ListAgents and SendMessage' "family refusal suggests native tools"
done
run "$SMINOS" wake other/x hi
assert_rc 4 "$RC" "family wake refuses outside seat"
run "$SMINOS" say '@x hi'
assert_rc 4 "$RC" "outside-family tag refused"
run "$SMINOS" say '@all @b hi'
assert_rc 2 "$RC" "all cannot mix with tags"
run "$SMINOS" say '@a hi'
assert_rc 2 "$RC" "self-tag refused"
run "$SMINOS" say --team '@lead hi'
assert_rc 2 "$RC" "team cannot name parent"
run "$SMINOS" say --in lead hi
assert_rc 2 "$RC" "family seat cannot select arbitrary chat"
run "$SMINOS" spawn c t --parent x
assert_rc 2 "$RC" "seat cannot override parent when spawning"
assert_contains "$OUT" 'a seat spawns its own children' "spawn refusal explains constraint"
run "$SMINOS" spawn c t --worktree c
assert_rc 0 "$RC" "family seat spawns child"
C="$(seat_id_of c)"
assert_equals "$(field "$C" parent)" a "child parent is caller"
assert_equals "$(field "$C" group)" fam "child inherits caller group"
run "$SMINOS" say --team 'my team'
assert_rc 0 "$RC" "middle seat speaks in its own chat"
assert_file_exists "$SMINOS_HOME/chats/$A.jsonl" "child-host chat has distinct history"
run "$SMINOS" say '@c @lead cross'
assert_rc 2 "$RC" "one message cannot span two families"
run "$SMINOS" chat
assert_rc 0 "$RC" "member can read parent chat"
run "$SMINOS" chat --team
assert_contains "$OUT" 'chat a (fam)' "team chat selects child's family"
assert_contains "$(field "$A" chat_seen)" "$LEAD\"" "parent chat cursor remains when own chat read"
assert_contains "$(field "$A" chat_seen)" "$A\"" "own chat cursor saved independently"
unset CLAUDE_CODE_SESSION_ID
run "$SMINOS" say hi
assert_rc 2 "$RC" "operator must select a chat"
run "$SMINOS" chat
assert_rc 2 "$RC" "operator must name the chat host"
run "$SMINOS" say --in lead 'hello team'
assert_rc 0 "$RC" "operator speaks as human"
assert_contains "$(tail -1 "$CHAT")" '"from": "human"' "operator identity recorded"
run "$SMINOS" say --in lead '@all operator broadcast'
assert_rc 0 "$RC" "operator can broadcast to a named family"
assert_contains "$(tail -1 "$CHAT")" '"mode": "all"' "explicit operator @all records broadcast mode"
run "$SMINOS" chat lead --since 6 --json
assert_rc 0 "$RC" "operator can read selected messages as JSONL"
assert_contains "$OUT" '"text": "@all operator broadcast"' "JSONL since prints messages after watermark"
assert_not_contains "$OUT" 'schema done' "since skips earlier messages"
run "$SMINOS" retire fam/lead
assert_rc 4 "$RC" "host cannot retire over live children"
assert_contains "$OUT" 'b' "retirement names live child"
run "$SMINOS" retire fam/lead --cascade
assert_rc 0 "$RC" "cascade retires descendants"
assert_contains "$OUT" 'retired fam/lead' "cascade ends with host"
assert_equals "$(printf '%s\n' "$OUT" | sed -n 's/^retired fam\/\([^ ]*\).*/\1/p' | tr '\n' ' ')" 'c a b lead ' "cascade retires depth-first then siblings in alias order"
run "$SMINOS" seat add fam all
assert_rc 2 "$RC" "all alias is reserved"
# Pipeline roots carry no preamble flag and retain the unrestricted operator surface.
run "$SMINOS" spawn pipeline-root t
PIPE="$(seat_id_of pipeline-root)"
CLAUDE_CODE_SESSION_ID="$(field "$PIPE" current)"
export CLAUDE_CODE_SESSION_ID
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "x"' "pipeline root still lists the fleet"
run "$SMINOS" spawn pipeline-child t
assert_rc 0 "$RC" "pipeline root spawns unrestricted"
assert_equals "$(field "$(seat_id_of pipeline-child)" parent)" '' "pipeline child does not inherit parent"
run "$SMINOS" resume other/x 'pipeline resume'
assert_rc 0 "$RC" "pipeline root can resume an unrelated seat"
unset CLAUDE_CODE_SESSION_ID
# A blocked row with no process must reconcile even if the record was already idle.
run "$SMINOS" seat add fam blocked-one --session 55555555-aaaa-4000-8000-000000000005
BLOCK=55555555-aaaa-4000-8000-000000000005
printf 'short=abcde012\nuuid=%s\nname=blocked-one\nstate=blocked\nstatus=\n' "$BLOCK" > "$STUB_STATE/agents/abcde012"
run "$SMINOS" list fam
assert_contains "$OUT" 'stopped' "blocked row without peer is stopped"
run "$SMINOS" sync fam/blocked-one
assert_rc 0 "$RC" "blocked row sync succeeds"
assert_contains "$OUT" 'idle' "idle blocked row is reconciled"
assert_contains "$(cat "$SMINOS_HOME/$BLOCK.reply.txt")" 'blocked on a harness prompt' "blocked reply carries prompt marker"
BLOCK_GEN="$(field "$BLOCK" gen)"
run "$SMINOS" sync fam/blocked-one
assert_contains "$OUT" 'noop' "repeated blocked sync has nothing new to reconcile"
assert_equals "$(field "$BLOCK" gen)" "$BLOCK_GEN" "repeated sync does not bump lifecycle generation"
run "$SMINOS" seat add fam blocked-working --session bbbbbbbb-aaaa-4000-8000-00000000000b
BW=bbbbbbbb-aaaa-4000-8000-00000000000b
printf 'short=abcde013\nuuid=%s\nname=blocked-working\nstate=blocked\nstatus=\n' "$BW" > "$STUB_STATE/agents/abcde013"
"$SMINOS" meta set blocked-working status working >/dev/null
run "$SMINOS" sync fam/blocked-working
assert_contains "$OUT" idle "working record with dead blocked row reconciles to idle"
assert_contains "$(cat "$SMINOS_HOME/$BW.reply.txt")" 'blocked on a harness prompt' "working blocked row records pending question"

# Fan-out continues after a stopped member's resume is refused.
run "$SMINOS" seat add fam duo --session 66666666-aaaa-4000-8000-000000000006
DUO=66666666-aaaa-4000-8000-000000000006
run "$SMINOS" seat add fam d1 --parent duo --session 77777777-aaaa-4000-8000-000000000007
D1=77777777-aaaa-4000-8000-000000000007
run "$SMINOS" seat add fam d2 --parent duo --session 88888888-aaaa-4000-8000-000000000008
D2=88888888-aaaa-4000-8000-000000000008
printf 'short=dddd0001\nuuid=%s\nname=d1\nstate=stopped\n' "$D1" > "$STUB_STATE/agents/dddd0001"
printf 'short=dddd0002\nuuid=%s\nname=d2\nstate=stopped\n' "$D2" > "$STUB_STATE/agents/dddd0002"
python3 - "$SMINOS_HOME/$D1.json" "$SMINOS_HOME/$D2.json" "$WORK" <<'PY_FIX_CWD'
import json, sys
for path, cwd in ((sys.argv[1], '/no-such-sminos-cwd'), (sys.argv[2], sys.argv[3])):
    d = json.load(open(path)); d['cwd'] = cwd
    with open(path, 'w') as f: json.dump(d, f)
PY_FIX_CWD
export CLAUDE_CODE_SESSION_ID="$DUO"
run "$SMINOS" say '@d1 @d2 please respond'
assert_rc 0 "$RC" "one refused resume does not abort the chat"
assert_contains "$OUT" 'd1: failed:' "bad cwd is recorded as a failed push"
assert_contains "$OUT" 'd2: woken' "the later tagged member resumes"
assert_contains "$(tail -1 "$SMINOS_HOME/chats/$DUO.jsonl")" '"d2": "woken"' "fan-out retains successful outcome"
run "$SMINOS" seat add fam d3 --parent duo --session 99999999-aaaa-4000-8000-000000000009
D3=99999999-aaaa-4000-8000-000000000009
printf 'short=dddd0003\nuuid=%s\nname=d3\nstate=stopped\n' "$D3" > "$STUB_STATE/agents/dddd0003"
python3 - "$SMINOS_HOME/$D3.json" "$WORK" <<'PY_FIX_CWD2'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d['cwd']=sys.argv[2]
with open(p, 'w') as f: json.dump(d, f)
PY_FIX_CWD2
STUB_NO_UUID=1 run "$SMINOS" say '@d3 check'
assert_rc 0 "$RC" "unconfirmed resume does not erase message"
assert_contains "$OUT" 'd3: woken?' "unconfirmed uuid is reported as uncertain wake"
assert_contains "$(tail -1 "$SMINOS_HOME/chats/$DUO.jsonl")" '"d3": "woken?"' "uncertain wake is recorded"
assert_contains "$(field "$D3" pending_short)" 'dddd0003' "unconfirmed resume keeps recovery short"
unset CLAUDE_CODE_SESSION_ID
run "$SMINOS" seat add fam solo --session aaaaaaaa-aaaa-4000-8000-00000000000a
export CLAUDE_CODE_SESSION_ID=aaaaaaaa-aaaa-4000-8000-00000000000a
run "$SMINOS" say 'no family'
assert_rc 4 "$RC" "isolated family seat has no chat"
assert_contains "$OUT" 'no family yet' "isolated seat explains how to gain a family"
run "$SMINOS" chart fam
assert_rc 4 "$RC" "family cannot use operator chart"
run "$SMINOS" tui fam --headless
assert_rc 4 "$RC" "family cannot use operator tui"
unset CLAUDE_CODE_SESSION_ID
# Corrupt history is ignored on reads, while the highest valid id wins.
printf '%s\n' 'not JSON at all' '{"id": 40, "from": "old", "delivered": {}}' >> "$SMINOS_HOME/chats/$DUO.jsonl"
run "$SMINOS" say --in duo 'after corrupt line'
assert_rc 0 "$RC" "a corrupt line does not block recording"
assert_contains "$(tail -1 "$SMINOS_HOME/chats/$DUO.jsonl")" '"id": 41' "next id follows highest valid record"
"$SMINOS" say --in duo 'parallel one' > "$TEST_ROOT/parallel-one.log" & p1=$!
"$SMINOS" say --in duo 'parallel two' > "$TEST_ROOT/parallel-two.log" & p2=$!
wait "$p1"; wait "$p2"
IDS="$(python3 - "$SMINOS_HOME/chats/$DUO.jsonl" <<'PY_IDS'
import json,sys
ids=[]
for line in open(sys.argv[1]):
    try: ids.append(json.loads(line)['id'])
    except (ValueError,KeyError): pass
print(ids[-2:])
PY_IDS
)"
assert_equals "$IDS" '[42, 43]' "two writers obtain unique sequential ids"
# The startup window: no current, harness row matches provisional short.
run "$SMINOS" seat add fam starter --parent duo --session aaaaaaaa-bbbb-4000-8000-00000000000a
START=aaaaaaaa-bbbb-4000-8000-00000000000a
PROVISIONAL=bbbbbbbb-bbbb-4000-8000-00000000000b
python3 - "$SMINOS_HOME/$START.json" "$SMINOS_HOME/$PROVISIONAL.json" <<'PY_PROVISIONAL'
import json,os,sys
d=json.load(open(sys.argv[1])); d['current']=''; d['short']='aaaa000a'
with open(sys.argv[2], 'w') as f: json.dump(d,f)
os.unlink(sys.argv[1])
PY_PROVISIONAL
printf 'short=aaaa000a\nuuid=%s\nname=starter\nstate=working\nstatus=busy\n' "$START" > "$STUB_STATE/agents/aaaa000a"
export CLAUDE_CODE_SESSION_ID="$START"
run "$SMINOS" chat -n 30
assert_rc 0 "$RC" "provisional caller reads its parent chat"
assert_contains "$OUT" 'chat duo (fam)' "provisional caller finds family by short"
run "$SMINOS" say 'starting'
assert_rc 0 "$RC" "provisional caller records a report"
assert_contains "$(tail -1 "$SMINOS_HOME/chats/$DUO.jsonl")" '"from": "starter"' "startup report has seat identity"
assert_file_absent "$SMINOS_HOME/$START.json" "startup chat read does not create promoted record"
# Promotion occurs while spawn waits; its child inherits the final tree.
python3 - "$SMINOS_HOME/$PROVISIONAL.json" "$SMINOS_HOME/$START.json" "$WORK" <<'PY_PROMOTE' & promoter=$!
import json,os,sys,time
time.sleep(.2)
d=json.load(open(sys.argv[1])); d['current']='aaaaaaaa-bbbb-4000-8000-00000000000a'
d['short']='aaaa000a'; d['cwd']=sys.argv[3]
with open(sys.argv[2], 'w') as f: json.dump(d,f)
os.unlink(sys.argv[1])
PY_PROMOTE
run "$SMINOS" spawn starter-child t
wait "$promoter"
assert_rc 0 "$RC" "spawn waits for parent's promotion"
assert_equals "$(field "$(seat_id_of starter-child)" parent)" starter "startup child belongs to promoted parent"
assert_file_absent "$SMINOS_HOME/$PROVISIONAL.json" "provisional record is gone after promotion"
assert_contains "$(field "$START" chat_seen)" "$DUO" "promotion preserves startup read watermark"
BEFORE_GEN="$(field "$START" gen)"
run "$SMINOS" chat
assert_equals "$(field "$START" gen)" "$BEFORE_GEN" "chat read does not invalidate lifecycle watcher"
unset CLAUDE_CODE_SESSION_ID

# The update is transactional: a kill just before replace leaves all old bytes.
BEFORE_CHAT="$(cat "$SMINOS_HOME/chats/$DUO.jsonl")"
RESULT="$(python3 - "$REPO_ROOT/skills/sminos/scripts/sminos.py" "$DUO" <<'PY_ATOMIC'
import subprocess, sys
script = '''import importlib.util, os, signal, sys
spec=importlib.util.spec_from_file_location("sminos",sys.argv[1]); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def interrupt(*args): os.kill(os.getpid(), signal.SIGKILL)
mod.os.replace=interrupt
mod.chat_update(sys.argv[2],1,{"lead":"sent"})'''
p=subprocess.run([sys.executable, '-c', script, *sys.argv[1:]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(p.returncode)
PY_ATOMIC
)"
assert_equals "$RESULT" '-9' "chat updater was killed before replacement"
assert_equals "$(cat "$SMINOS_HOME/chats/$DUO.jsonl")" "$BEFORE_CHAT" "killed update preserves complete chat"
# A long-held flock is not a timed lease: no second writer overtakes it at 30 s.
if [[ "${SMINOS_FAMILY_ONLY:-0}" != 1 ]]; then
  python3 - "$SMINOS_HOME/chats/$DUO.lock" "$TEST_ROOT/lock-ready" <<'PY_LOCK_HOLDER' & holder=$!
import fcntl, pathlib, sys, time
with open(sys.argv[1], 'a') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    pathlib.Path(sys.argv[2]).touch()
    time.sleep(31)
PY_LOCK_HOLDER
  for _ in $(seq 1 100); do [ -f "$TEST_ROOT/lock-ready" ] && break; sleep .05; done
  "$SMINOS" say --in duo 'wait behind lock' > "$TEST_ROOT/waited-say.log" & waiter=$!
  sleep 30.25
  assert_not_contains "$(cat "$SMINOS_HOME/chats/$DUO.jsonl")" 'wait behind lock' "writer held beyond thirty seconds is not overtaken"
  wait "$holder"; wait "$waiter"
  assert_contains "$(cat "$SMINOS_HOME/chats/$DUO.jsonl")" 'wait behind lock' "waiting writer records after flock releases"
fi


START_CHILD="$(seat_id_of starter-child)"
run "$SMINOS" retire fam/duo --cascade --purge
assert_rc 0 "$RC" "cascade purge succeeds"
assert_file_absent "$SMINOS_HOME/$DUO.json" "cascade purges host"
assert_file_absent "$SMINOS_HOME/$D1.json" "cascade purges first child"
assert_file_absent "$SMINOS_HOME/$D2.json" "cascade purges second child"
assert_file_absent "$SMINOS_HOME/$START.json" "cascade purges nested host"
assert_file_absent "$SMINOS_HOME/$START_CHILD.json" "cascade purges grandchild"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  exit 1
fi
