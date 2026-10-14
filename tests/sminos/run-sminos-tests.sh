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
EXTRA_PIDS=()
cleanup() {
  [ -n "$SOCK_PID" ] && kill "$SOCK_PID" 2>/dev/null || true
  for pid in ${EXTRA_PIDS[@]+"${EXTRA_PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

pass() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "  FAIL $1"; }
assert_equals() {
  if [[ "$1" == "$2" ]]; then pass "$3"; else
    fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
# A here-string, not `printf | grep -q`: under pipefail an early grep exit
# SIGPIPEs printf, failing a match (or passing a negative check) on long text.
assert_contains() {
  if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:600}"; fi
}
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
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
has_key() { # seat-id key → True | False: whether the record on disk carries the key at all
  python3 -c 'import json, sys; print(sys.argv[2] in json.load(open(sys.argv[1])))' "$SMINOS_HOME/$1.json" "$2"
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
# The daemon's hourly derivation starts a child; only the case that pins it turns it on.
export SMINOS_DERIVE_EVERY=0
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
has_bg=0; fork=0; session_id=""; name=""; resume_uuid=""; worktree=""; i=0
while [ $i -lt ${#args[@]} ]; do
  case "${args[$i]}" in
    --bg) has_bg=1 ;;
    --fork-session) fork=1 ;;
    --session-id) i=$((i + 1)); session_id="${args[$i]}" ;;
    -n) i=$((i + 1)); name="${args[$i]}" ;;
    --resume) i=$((i + 1)); resume_uuid="${args[$i]}" ;;
    --worktree) i=$((i + 1)); worktree="${args[$i]}" ;;
  esac
  i=$((i + 1))
done

# Session uuids come from a counter, shared across homes through STUB_COUNTER
# (two homes on one machine must never mint the same uuid).
counter="${STUB_COUNTER:-$STUB_STATE/counter}"
tx_path() { printf '%s/.claude/projects/%s/%s.jsonl' "$HOME" "$(printf '%s' "$PWD" | sed 's#/#-#g')" "$1"; }
write_asst() {
  local f; f="$(tx_path "$1")"; mkdir -p "$(dirname "$f")"
  python3 - "$f" "$2" <<'PY'
import json, sys
open(sys.argv[1], 'a').write(json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": sys.argv[2]}]}}) + "\n")
PY
}

# `-p --resume <id> --fork-session …` (derive's internal fork): a copy of the
# parent's transcript as a new session, registered while it runs, the hook run
# at its start and stop as the harness would, and the JSON result on stdout.
# `--session-id` pins the fork's id, as the real harness honours it.
# STUB_FORK_RESULT is its answer, STUB_FORK_FAIL=1 a failed run,
# STUB_FORK_CRASH=1 a crash that prints nothing, and STUB_FORK_LIST=1 has it
# list the project's members while it runs.
if [ $fork -eq 1 ]; then
  echo "fork-env:internal=${SMNS_INTERNAL:-} marker=$([ -f "$SMINOS_HOME/internal/$$" ] && echo yes || echo no)" >> "$STUB_STATE/log/calls.log"
  n=$(cat "$counter" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$counter"
  fork_uuid="${session_id:-$(printf '%08x' "$n")-f0f0-4000-8000-00000000f0f0}"
  parent="$(ls "$HOME"/.claude/projects/*/"$resume_uuid.jsonl" 2>/dev/null | head -1 || true)"
  f="$(tx_path "$fork_uuid")"; mkdir -p "$(dirname "$f")"
  if [ -n "$parent" ]; then cp "$parent" "$f"; else : > "$f"; fi
  printf '{"pid":%s,"sessionId":"%s","name":"stubfork","kind":"interactive","status":"busy","cwd":"%s"}\n' \
    "$$" "$fork_uuid" "$PWD" > "$HOME/.claude/sessions/stubfork-$$.json"
  trap 'rm -f "$HOME/.claude/sessions/stubfork-$$.json"' EXIT
  answer="${STUB_FORK_RESULT:-<message>owns the stub tool</message>}"
  hook() { printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","hook_event_name":"%s","source":"%s"}' \
    "$fork_uuid" "$f" "$PWD" "$1" "$2" | CLAUDE_PLUGIN_ROOT="$STUB_PLUGIN_ROOT" "$STUB_PLUGIN_ROOT/hooks/smns-record.sh"; }
  hook SessionStart fork
  [ "${STUB_FORK_CRASH:-0}" = "1" ] && exit 3
  # STUB_FORK_SLEEP: a model call that takes this many seconds.
  [ -n "${STUB_FORK_SLEEP:-}" ] && sleep "$STUB_FORK_SLEEP"
  python3 - "$f" "$answer" <<'PY'
import json, sys
open(sys.argv[1], 'a').write(json.dumps({"type": "assistant", "uuid": "f0f0f0f0-answer", "isSidechain": False,
    "message": {"role": "assistant", "content": [{"type": "text", "text": sys.argv[2]}]}}) + "\n")
PY
  hook Stop ""
  if [ "${STUB_FORK_LIST:-0}" = "1" ]; then "$STUB_SMINOS" list --json > "$STUB_STATE/fork-list.json" 2>&1 || true; fi
  is_error=false; [ "${STUB_FORK_FAIL:-0}" = "1" ] && is_error=true
  python3 -c 'import json, sys; print(json.dumps({"type": "result", "is_error": sys.argv[3] == "true", "result": sys.argv[1], "session_id": sys.argv[2]}))' \
    "$answer" "$fork_uuid" "$is_error"
  if [ "$is_error" = "true" ]; then printf 'stub: warming up\nstub: the fork exploded\n' >&2; exit 1; fi
  exit 0
fi

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
  n=$(cat "$counter" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$counter"
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
# What the stub's derive fork runs: the hook, and the CLI itself.
export STUB_PLUGIN_ROOT="$REPO_ROOT" STUB_SMINOS="$SMINOS"

# A stand-in for a live session's inbox socket: appends every frame it
# receives to inbox.received, one connection at a time, forever. While
# <received>.hold exists, a frame is written and marked (<received>.held), but
# its ack waits for the hold to lift: a deliverer killed in that window has
# pushed without settling.
cat > "$TEST_ROOT/sockserver.py" <<'PY'
import os, socket, sys, time
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
    if os.path.exists(out + ".hold"):
        open(out + ".held", "w").close()
        while os.path.exists(out + ".hold"):
            time.sleep(0.02)
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
for verb in post board topology view groups mark join leave listen log; do
  run "$SMINOS" "$verb"
  assert_rc 2 "$RC" "removed $verb is a usage error"
  assert_contains "$OUT" 'usage: sminos' "removed $verb shows usage"
done
run "$SMINOS" --help
for verb in post board topology view groups mark join leave listen log; do
  assert_not_contains "$OUT" "sminos $verb" "--help omits removed $verb"
done
run "$SMINOS" bogus; assert_rc 2 "$RC" "unknown command is a usage error"
run "$SMINOS" seat; assert_rc 2 "$RC" "bare 'seat' is a usage error"

# ---- 2) migration ------------------------------------------------------------
# Runs only when the DEFAULT root is in use: a separate HOME with the old
# daemon registry, an sminos v2 group, and a record lacking `group`.
echo "migration:"
cd "$WORK"   # a directory in no project: lists and bare names span every project
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
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list --all
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
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list y --all
assert_contains "$OUT" "scout2" "a second group's node sharing a session id still converts"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list x --json
assert_contains "$OUT" '"alias": "scout"' "the first group's node keeps its seat"
assert_equals "$(mode_of "$NEW")" "0700" "migration tightens a 0755 root to 0700"
assert_equals "$(mode_of "$NEW/$OLD_UUID.json")" "0600" "migration tightens a 0644 record to 0600"
rm "$MH/.claude/orchestrating-daemons"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list
if [ -L "$MH/.claude/orchestrating-daemons" ]; then pass "a missing legacy symlink is recreated on the next run"; else fail "a missing legacy symlink is recreated on the next run"; fi
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list
assert_contains "$(cat "$NEW/$DUP_OLD.json")" '"alias": "review-pr-470@aaaa1111"' "dedupe is idempotent (no alias@short@short)"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" send codexy "x"
assert_rc 4 "$RC" "send refuses a legacy codex record"
assert_contains "$OUT" "legacy codex" "and says it is a legacy codex record"
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
run env -u SMINOS_HOME HOME="$AH" "$SMINOS" list --all
assert_rc 0 "$RC" "a root under the former name migrates on the first command"
assert_contains "$OUT" "keeper" "the former root's seats are listed"
assert_file_exists "$AH/.claude/sminos/$V3_UUID.json" "the former root was renamed into place"
if [ -L "$AH/.claude/agora" ] && [ "$(readlink "$AH/.claude/agora")" = "$AH/.claude/sminos" ]; then pass "the former path is a symlink to the root"; else fail "the former path is a symlink to the root"; fi
if [ -L "$AH/.claude/orchestrating-daemons" ]; then pass "the daemon-era symlink is left alone"; else fail "the daemon-era symlink is left alone"; fi
# A real directory recreated at the former path (an older consumer's mkdir -p
# landing in the cutover gap) must never displace a root that holds records.
rm "$AH/.claude/agora"; mkdir "$AH/.claude/agora"
run env -u SMINOS_HOME HOME="$AH" "$SMINOS" list --all
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
run env -u SMINOS_HOME HOME="$AH" "$SMINOS" list --all
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
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list x --json
assert_not_contains "$OUT" '"null"' "list never prints null for a converted node"
assert_contains "$OUT" '"parent": "orchestrator"' "converted node retains its parent"
run env -u SMINOS_HOME HOME="$MH" "$SMINOS" list work --json
assert_contains "$OUT" '"alias": "old-worker"' "list falls back alias → name"

# ---- 3) seats: validation and vacant/registered seats ------------------------
echo "seat add:"
run "$SMINOS" seat add grp "bad/alias"; assert_rc 2 "$RC" "alias with a slash is rejected"
run "$SMINOS" seat add grp ".."; assert_rc 2 "$RC" "'..' is rejected as an alias"
run "$SMINOS" seat add grp human; assert_rc 2 "$RC" "'human' is reserved"
run "$SMINOS" seat add "../grp" x; assert_rc 2 "$RC" "group name with traversal is rejected"
ORCH_UUID="33333333-cccc-4000-8000-000000000003"
run "$SMINOS" seat add grp orchestrator --role lead --session "$ORCH_UUID"
assert_rc 0 "$RC" "registering an existing session as a seat"
assert_equals "$OUT" "seat grp/orchestrator added (session: $ORCH_UUID)" "the confirmation line names the seat and session, no addr"
assert_file_exists "$SMINOS_HOME/$ORCH_UUID.json" "a registered session's seat is keyed by its session id"
assert_equals "$(has_key "$ORCH_UUID" addr)" "False" "a seat record carries no addr"
assert_equals "$(field "$ORCH_UUID" name)" "orchestrator" "a seat record's name is its alias"
run "$SMINOS" seat add grp q --addr q
assert_rc 2 "$RC" "seat add --addr is an unknown argument"
assert_equals "$(seat_id_of q)" "" "the refused seat add wrote no record"
assert_equals "$(field "$ORCH_UUID" role)" "lead" "--role is stored"
assert_equals "$(field "$ORCH_UUID" status)" "idle" "a registered session starts idle"
assert_equals "$(mode_of "$SMINOS_HOME/$ORCH_UUID.json")" "0600" "seat records are private (umask 077)"
assert_equals "$(mode_of "$SMINOS_HOME")" "0700" "the registry root is private"
run "$SMINOS" seat add grp scribe --role writer --brief "keeps notes"
assert_rc 0 "$RC" "adding a vacant seat"
assert_contains "$OUT" "vacant" "vacant seat reported"
run "$SMINOS" list work
assert_contains "$OUT" "vacant" "list shows the vacant seat's state word"
run "$SMINOS" list work --json
assert_contains "$OUT" '"role": "writer"' "list --json carries the seat's role"
# ---- 4) spawn ----------------------------------------------------------------
echo "spawn:"
cd "$WORK"
run "$SMINOS" spawn researcher "PING-scope-42" --role researcher
assert_rc 0 "$RC" "spawn exits 0"
assert_contains "$OUT" "seat spawned: work/researcher" "spawn banner names the seat"
R_UUID="$(banner_uuid "$OUT")"; R_SHORT="$(banner_short "$OUT")"
assert_file_exists "$SMINOS_HOME/$R_UUID.json" "record is named after the first session's uuid (banner bracket form)"
assert_equals "$(field "$R_UUID" alias)" "researcher" "alias recorded"
assert_equals "$(field "$R_UUID" name)" "researcher" "harness display name = alias"
assert_equals "$(has_key "$R_UUID" addr)" "False" "a spawned seat's record carries no addr"
assert_equals "$(field "$R_UUID" group)" "work" "the group derives from the cwd"
assert_equals "$(field "$R_UUID" parent)" "" "no parent is recorded"
assert_equals "$(field "$R_UUID" role)" "researcher" "role recorded"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "current = first session"
assert_equals "$(field "$R_UUID" short)" "$R_SHORT" "short recorded"
assert_equals "$(field "$R_UUID" status)" "idle" "a first turn that already ended records idle"
assert_equals "$(field "$R_UUID" turns)" "1" "turn 1 recorded"
assert_equals "$(field "$R_UUID" cwd)" "$WORK" "cwd recorded from the harness row"
assert_contains "$(field "$R_UUID" task)" 'You are seat "researcher" in sminos group "work", the root of your' "every spawn renders the preamble, naming its project"
assert_contains "$(field "$R_UUID" task)" "$SMINOS chat -n 30" "spawned seat reads family chat before acting"
assert_equals "$(field "$R_UUID" task | grep -m1 '^    .*/sminos \(chat\|say\|status\|spawn\) ')" "    $SMINOS chat -n 30" "reading chat is the first sminos instruction"
assert_contains "$(field "$R_UUID" task)" "$SMINOS say \"done with X; PR #12\"" "preamble teaches a report to the host"
assert_contains "$(field "$R_UUID" task)" "$SMINOS say \"@sibling your change renames a column I read\"" "preamble teaches targeted family messages"
assert_contains "$(field "$R_UUID" task)" 'Tags address only at the start of a message; an @ later' "member preamble teaches that only leading tags address"
assert_contains "$(field "$R_UUID" task)" "$SMINOS spawn <alias> \"<task>\" [--role <role>] [--worktree <name>]" "preamble teaches inherited family spawning"
assert_contains "$(field "$R_UUID" task)" 'ListAgents and SendMessage' "preamble points outside-family contact to native tools"
assert_not_contains "$(field "$R_UUID" task)" 'sminos topology' "spawned seat does not read removed topology view"
assert_not_contains "$(field "$R_UUID" task)" 'sminos post' "spawned seat does not use removed board post"
assert_contains "$(field "$R_UUID" task)" "Your task follows." "preamble separates protocol from task"
assert_contains "$(field "$R_UUID" task)" "PING-scope-42" "task text follows the preamble"
assert_file_exists "$SMINOS_HOME/$R_UUID.reply.txt" "reply of an already-finished first turn is recorded"
assert_contains "$(cat "$SMINOS_HOME/$R_UUID.reply.txt")" "ANSWER:" "recorded reply comes from the transcript"
assert_contains "$(grep 'bg-env:You are seat' "$STUB_STATE/log/calls.log" | tail -1)" "path=set" "PATH survives the plain-route launch"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--permission-mode auto -n researcher" "launch uses auto permission mode and the alias as display name"

run "$SMINOS" spawn plainworker "NOGROUP-1"
assert_rc 0 "$RC" "a second spawn"
P_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$P_UUID" group)" "work" "group derived from the cwd"
assert_contains "$(field "$P_UUID" task)" 'You are seat "plainworker"' "every spawn renders the preamble"
assert_equals "$(field "$P_UUID" preamble)" "1" "and records that it did"

# One name: the alias is the harness name, so there is no second address to give.
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$SMINOS" spawn z "t" --addr q
assert_rc 2 "$RC" "spawn --addr is an unknown argument"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no session is launched for the refused --addr"

STUB_BG_STATE=working run "$SMINOS" spawn nowaiter "LONG-TASK-7" --no-wait
assert_rc 0 "$RC" "--no-wait is accepted"
NW_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$NW_UUID" status)" "working" "a running first turn records working"
assert_file_absent "$SMINOS_HOME/$NW_UUID.reply.txt" "no reply file while the turn runs"
run "$SMINOS" reply nowaiter
assert_contains "$OUT" "ANSWER:" "reply reads the running turn's transcript"
assert_contains "$OUT" "--- latest reply ---" "reply prints its header"

# spawn refuses a FILLED seat (nowaiter's session answers, busy) but RE-FILLS a
# stopped one.
printf '{"pid":%s,"sessionId":"%s","name":"nowaiter","kind":"background","status":"busy","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$NW_UUID" "$SOCK" > "$HOME/.claude/sessions/nowaiter.json"
run "$SMINOS" spawn nowaiter "x"
assert_rc 4 "$RC" "spawning a filled seat is refused"
assert_contains "$OUT" "is filled (busy) — message it with sminos send" "filled refusal names the state word and points at send"
rm -f "$HOME/.claude/sessions/nowaiter.json"
run "$SMINOS" spawn refillme "FIRST" --role r1 --brief b1
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
run "$SMINOS" spawn stamped "STAMPED-1" --stamp board_dispatch=n-7 --stamp lane=implementer
assert_rc 0 "$RC" "spawn with --stamp exits 0"
ST="$(seat_id_of stamped)"
assert_equals "$(field "$ST" board_dispatch)" "n-7" "--stamp lands on the record"
assert_equals "$(field "$ST" lane)" "implementer" "--stamp is repeatable"
run "$SMINOS" spawn badstamp "X" --stamp nosign
assert_rc 2 "$RC" "--stamp without field=value is a usage error"
run "$SMINOS" spawn badstamp "X" --stamp run_bearer=leak
assert_rc 2 "$RC" "--stamp refuses a credential field"
# The drop and the stamp meet on a re-fill, and the stamp wins: meta_set removes
# AFTER it merges, so a dispatched re-fill has to be exempt from its own drop.
"$SMINOS" meta set stamped board_dispatch n-old >/dev/null
run "$SMINOS" spawn stamped "STAMPED-2" --stamp board_dispatch=n-new
assert_rc 0 "$RC" "a dispatched re-fill exits 0"
assert_equals "$(field "$ST" board_dispatch)" "n-new" "its --stamp survives the re-fill's own drop"

run "$SMINOS" spawn refillme "SECOND"
assert_rc 0 "$RC" "re-spawning a stopped seat re-fills it (exit 0)"
assert_contains "$OUT" "seat re-filled: work/refillme" "re-fill is reported"
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
run "$SMINOS" spawn refillme "THIRD" --role r2 --brief b2
assert_equals "$(field "$RF" role)" "r2" "re-fill with --role updates the role"
assert_equals "$(field "$RF" brief)" "b2" "re-fill with --brief updates the brief"
assert_equals "$(field "$RF" attempts)" "3" "attempts keeps counting"
"$SMINOS" remove work/refillme >/dev/null

run "$SMINOS" spawn waiter "WAIT-1" --wait
assert_rc 0 "$RC" "--wait exits 0 on a finished turn"
assert_contains "$OUT" "--- reply ---" "--wait prints the reply block"
assert_contains "$OUT" "ANSWER:" "--wait prints the reply text"
W_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$W_UUID" status)" "idle" "--wait records idle"

STUB_BG_STATE=working run "$SMINOS" spawn slow "SLOW-1" --wait
assert_rc 1 "$RC" "--wait watcher timeout exits 1"
assert_contains "$OUT" "watcher expired" "watcher timeout is reported"
S_UUID="$(seat_id_of slow)"
assert_equals "$(field "$S_UUID" status)" "working" "watcher timeout leaves status working (the turn is live)"

record_count() { local n=0 f; for f in "$SMINOS_HOME"/*.json; do case "$f" in *.reply.json) ;; *) n=$((n + 1)) ;; esac; done; echo "$n"; }
before=$(record_count)
STUB_FAIL_BG=1 run "$SMINOS" spawn failer "F"
assert_rc 1 "$RC" "a launch that prints no id exits 1"
after=$(record_count)
assert_equals "$after" "$before" "a failed launch leaves no phantom seat"

STUB_NO_UUID=1 run "$SMINOS" spawn nouuid "N"
assert_rc 1 "$RC" "a session with no uuid exits 1"
NU_ID="$(seat_id_of nouuid)"
assert_equals "$(field "$NU_ID" status)" "error" "no-uuid launch records status error"
if [ -n "$(field "$NU_ID" pending_short)" ]; then pass "no-uuid launch records pending_short for recovery"; else fail "no-uuid launch records pending_short for recovery"; fi
"$SMINOS" remove "work/nouuid" >/dev/null

# gateway dimension: env-injected settings/effort ride the launch and are
# persisted; the plain route scrubs the gateway's transport env (PATH survives).
GW="$TEST_ROOT/gw.json"
printf '{"env":{"ANTHROPIC_BASE_URL":"http://gw","ANTHROPIC_AUTH_TOKEN":"tok","CLAUDE_CODE_SUBAGENT_MODEL":"m","PATH":"/nope"}}' > "$GW"
mkdir -p "$HOME/.claude"; cp "$GW" "$HOME/.claude/clodex-settings.json"
export ANTHROPIC_BASE_URL="http://gw" ANTHROPIC_AUTH_TOKEN="fixture-token" CLAUDE_CODE_SUBAGENT_MODEL="sub" UNRELATED_TRANSPORT_VAR="keep" RUNNER_TRACKING_ID="run-1"
DAEMON_CLAUDE_SETTINGS="$GW" DAEMON_CLAUDE_EFFORT=high run "$SMINOS" spawn gwworker "GW-1"
assert_rc 0 "$RC" "gateway spawn exits 0"
G_UUID="$(banner_uuid "$OUT")"
assert_equals "$(field "$G_UUID" settings)" "$GW" "DAEMON_CLAUDE_SETTINGS persisted as settings"
assert_equals "$(field "$G_UUID" effort)" "high" "DAEMON_CLAUDE_EFFORT persisted as effort"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--settings $GW --effort high" "gateway flags reach the launch"
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "base=http://gw;token=fixture-token" "gateway route keeps the transport env"
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "runner=;" "RUNNER_TRACKING_ID is always stripped"
run "$SMINOS" spawn plain2 "PLAIN-2"
assert_contains "$(grep 'bg-env:' "$STUB_STATE/log/calls.log" | tail -1)" "base=;token=;sub=;keep=keep;runner=;path=set" "plain route scrubs the gateway env keys, keeps PATH and unrelated vars"
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_SUBAGENT_MODEL UNRELATED_TRANSPORT_VAR RUNNER_TRACKING_ID

run "$SMINOS" spawn wtworker "WT-1" --worktree "feat x"
assert_rc 0 "$RC" "worktree spawn exits 0"
WT_UUID="$(banner_uuid "$OUT")"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "--worktree feat-x" "worktree name is sanitized"
assert_equals "$(field "$WT_UUID" cwd)" "$WORK/.claude/worktrees/feat-x" "cwd is the worktree path the harness reports"
assert_contains "$OUT" "worktree=" "banner notes the worktree"

# Uniqueness is per seat: a live harness session outside the fleet that
# already answers to the alias does not block the alias (the harness tells two
# sessions of one name apart itself).
printf '{"pid":%s,"sessionId":"77777777-aaaa-4000-8000-000000000007","name":"taken","kind":"interactive","status":"idle","messagingSocketPath":"%s"}\n' "$$" "$SOCK" > "$HOME/.claude/sessions/$$.json"
run "$SMINOS" seat add grp taken
assert_rc 0 "$RC" "seat add takes an alias a live session outside the fleet answers to"
run "$SMINOS" seat add grp taken --session 77777777-aaaa-4000-8000-000000000007
assert_rc 0 "$RC" "seat add registers the very session that holds the name"
"$SMINOS" remove grp/taken >/dev/null
run "$SMINOS" spawn taken "T"
assert_rc 0 "$RC" "spawn takes an alias a live session outside the fleet answers to"
rm -f "$HOME/.claude/sessions/$$.json"
"$SMINOS" remove work/taken >/dev/null

# Two projects may both hold an alias; from a directory that is no project a
# bare alias is then ambiguous, and `group/alias` (or `project/alias`) names each.
mkdir -p "$TEST_ROOT/one" "$TEST_ROOT/two"
run "$SMINOS" spawn a "wait" --cwd "$TEST_ROOT/one"
assert_rc 0 "$RC" "spawn one/a exits 0"
ONE_A="$(banner_uuid "$OUT")"
printf '{"pid":%s,"sessionId":"%s","name":"a","kind":"background","status":"busy","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$ONE_A" "$SOCK" > "$HOME/.claude/sessions/one-a.json"
run "$SMINOS" spawn a "wait" --cwd "$TEST_ROOT/two"
assert_rc 0 "$RC" "spawn two/a exits 0 while one/a is live"
TWO_A="$(banner_uuid "$OUT")"
printf '{"pid":%s,"sessionId":"%s","name":"a","kind":"background","status":"idle","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$TWO_A" "$SOCK" > "$HOME/.claude/sessions/two-a.json"
run "$SMINOS" list --json
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys
print(sorted((d["project"], d["state"]) for d in json.load(sys.stdin) if d["alias"] == "a"))')" \
  "[('one', 'busy'), ('two', 'idle')]" "both projects hold a live seat named a"
assert_equals "$(field "$TWO_A" name)" "a" "the second seat's name is its alias too"
assert_contains "$(grep -- '--bg' "$STUB_STATE/log/calls.log" | tail -1)" "-n a " "the second seat launches under its alias"
run "$SMINOS" send a "x"
assert_rc 4 "$RC" "send to an alias two projects hold exits 4"
assert_equals "$OUT" "sminos: ambiguous seat 'a' matches: one/a, two/a" "the ambiguity lists group/alias, no ids"
run "$SMINOS" status a "x"
assert_equals "$OUT" "sminos: ambiguous seat 'a' matches: one/a, two/a" "every seat verb lists the ambiguity the same way"
: > "$RECEIVED"
run "$SMINOS" send two/a "x"
assert_rc 0 "$RC" "send to group/alias delivers"
assert_equals "$OUT" "sent to two/a" "the delivery names the seat by its one name, no harness name beside it"
rm -f "$HOME/.claude/sessions/one-a.json" "$HOME/.claude/sessions/two-a.json"
"$SMINOS" remove one/a >/dev/null; "$SMINOS" remove two/a >/dev/null

# Lifecycle lock: a spawn of a seat whose lock another sminos process holds is
# refused, never duplicated.
python3 - "$(lock_file work/locked)" <<'PY' &
import fcntl, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
HOLDER=$!
sleep 0.4
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$SMINOS" spawn locked "L"
assert_rc 4 "$RC" "a spawn while the seat's lifecycle lock is held is refused"
assert_contains "$OUT" "being changed by another sminos process" "lock refusal is explained"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no session is launched while the lock is held"
mkdir -p "$TEST_ROOT/other"
run "$SMINOS" spawn locked "L" --cwd "$TEST_ROOT/other"
assert_rc 0 "$RC" "the lock is the seat's (group/alias): the same alias in another group spawns meanwhile"
kill "$HOLDER" 2>/dev/null || true; wait "$HOLDER" 2>/dev/null || true
"$SMINOS" remove other/locked >/dev/null

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
"$SMINOS" meta set slow status working >/dev/null
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
"$SMINOS" meta set asker status blocked >/dev/null
{ echo "short=aaaa0001"; echo "uuid=$ASKQ_UUID"; echo "name=asker"; echo "state=blocked"; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/aaaa0001"
run "$SMINOS" sync asker; assert_equals "$OUT" "idle" "an ended blocked-shape turn finalizes as idle"
ASK_REPLY="$(cat "$SMINOS_HOME/$ASKQ_UUID.reply.txt")"
assert_contains "$ASK_REPLY" "Which color should the widget be?" "pending AskUserQuestion surfaced in the reply"
assert_contains "$ASK_REPLY" "Red / Blue" "pending question options rendered"
assert_contains "$ASK_REPLY" "Before I pick, one question." "turn text still printed alongside the question"
assert_contains "$ASK_REPLY" 'sminos send asker "<answer>"' "reply points at the answer path"
assert_not_contains "$ASK_REPLY" "blocked on a harness prompt" "a rendered question gets no harness-prompt marker"
PERM_UUID="55555555-eeee-4000-8000-000000000005"
python3 - "$HOME/.claude/projects/fake-proj/$PERM_UUID.jsonl" <<'PY'
import json, sys
open(sys.argv[1], "w").write(json.dumps(
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "About to ask something."}]}}) + "\n")
PY
"$SMINOS" seat add grp permer --session "$PERM_UUID" >/dev/null
"$SMINOS" meta set permer status blocked >/dev/null
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

# ---- 6) send: the one delivery verb ------------------------------------------
echo "send:"
# A live peer record for the orchestrator seat: the socket server's pid is
# alive, its socket accepts connections.
printf '{"pid":%s,"sessionId":"%s","name":"my session","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$ORCH_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/$SOCK_PID.json"
run "$SMINOS" send orchestrator "hello there"
assert_rc 0 "$RC" "send to a live seat exits 0"
assert_equals "$OUT" "sent to grp/orchestrator" "send reports the target by its one name"
sleep 0.2
assert_contains "$(cat "$RECEIVED")" '"type": "user"' "frame is the documented user-message shape"
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from human id=' "the frame's first line names the sender and carries a message id"
assert_contains "$(tail -c 400 "$RECEIVED")" ']\nhello there' "the message follows the frame's first line"
if grep -q 'sminos message from human id=[0-9a-f]\{8\}\]' "$RECEIVED"; then pass "the frame id is eight hex digits"; else fail "the frame id is eight hex digits"; fi
assert_equals "$(field "$ORCH_UUID" status)" "working" "a send to a live seat records its turn as working"
"$SMINOS" meta set orchestrator status idle >/dev/null
run "$SMINOS" send scribe "x"
assert_rc 4 "$RC" "send to a vacant seat is refused (exit 4)"
assert_contains "$OUT" 'sminos fill grp/scribe "<task>"' "the vacant refusal points at fill"
run "$SMINOS" send "my session" "by name" --from ops
assert_rc 0 "$RC" "send resolves a live harness session name when no seat matches"
sleep 0.2
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from ops id=' "--from is honored"
assert_contains "$(tail -c 400 "$RECEIVED")" ']\nby name' "the raw-name frame carries the message"
# --wait needs a seat record to watch: a session name or a codex thread is
# refused before anything is delivered.
RECV_BEFORE="$(wc -c < "$RECEIVED")"
run "$SMINOS" send "my session" "not delivered" --wait
assert_rc 2 "$RC" "send --wait to a raw session name is refused"
assert_contains "$OUT" "--wait needs a seat" "the refusal says why"
assert_equals "$(printf '%s' "$OUT" | wc -l | tr -d ' ')" "0" "the refusal is one line"
sleep 0.2
assert_equals "$(wc -c < "$RECEIVED")" "$RECV_BEFORE" "nothing reached the session before the refusal"
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
run "$SMINOS" send codex:01a07a8a-569e-7923-b476-8a7d7d6271c3 "held back" --wait
assert_rc 2 "$RC" "send --wait to a codex thread is refused"
assert_contains "$OUT" "--wait needs a seat" "the codex refusal says why"
assert_not_contains "$(cat "$STUB_STATE/log/calls.log")" "queue --thread 01a07a8a" "nothing was queued before the refusal"
run "$SMINOS" send 01a07a8a-569e-7923-b476-8a7d7d6271c3 "ping codex"
assert_rc 0 "$RC" "a codex thread id is accepted"
assert_contains "$OUT" "queued for codex thread 01a07a8a-569e-7923-b476-8a7d7d6271c3 (01a0aaaa-0000-7000-8000-000000000001)" "send reports the thread and the queued submission"
assert_contains "$OUT" "read between turns" "the report says when codex reads it"
assert_not_contains "$OUT" "sent to" "a queued message is not reported as sent"
assert_contains "$(cat "$STUB_STATE/log/codex-queue.log")" "[sminos message from human id=" "the queued text opens with the same frame header"
assert_contains "$(cat "$STUB_STATE/log/codex-queue.log")" "ping codex" "the message body is queued"
run "$SMINOS" send "spike thread" "by name"
assert_rc 4 "$RC" "a bare codex thread NAME is not resolved"
run "$SMINOS" send "codex:spike thread" "by name" --from ops
assert_rc 0 "$RC" "codex:<name> resolves an exact codex thread name"
assert_contains "$OUT" "queued for codex thread 01a07a8a" "the name is reported as its thread id"
assert_contains "$(cat "$STUB_STATE/log/codex-queue.log")" "[sminos message from ops id=" "--from is honored for codex targets"
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
run "$SMINOS" list work
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
run "$SMINOS" list work
assert_contains "$OUT" "idle" "and the seat still reads idle rather than stopped"
peer_with_procstart "Mon Jan  1 00:00:00 2001"
run "$SMINOS" send orchestrator "procstart bogus"
assert_rc 4 "$RC" "an unrelated procStart reads as a recycled pid and send refuses"
assert_contains "$OUT" "is gone — no transcript for its session on this machine" "a seat with no live peer and no transcript is refused as gone"
assert_contains "$OUT" 'sminos fill grp/orchestrator "<task>"' "the gone refusal points at a fresh fill"
assert_contains "$OUT" "sminos retire grp/orchestrator" "and at retire"
assert_equals "$(printf '%s' "$OUT" | wc -l | tr -d ' ')" "0" "the gone refusal is one line"
assert_not_contains "$(grep -- '^--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)" "procstart bogus" "no resume of a gone seat is attempted"
printf '{"pid":%s,"sessionId":"%s","name":"my session","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$ORCH_UUID" "$WORK" "$SOCK" > "$HOME/.claude/sessions/$SOCK_PID.json"

run "$SMINOS" wake orchestrator "wake up" --from boss
assert_rc 2 "$RC" "wake exits 2"
assert_equals "$OUT" 'sminos: wake was folded into send — sminos send <seat> "<msg>" [--wait] [--from F]' "wake answers with the pointer to send, one line"
run "$SMINOS" wake --wait nobody-at-all "x" --from boss
assert_rc 2 "$RC" "wake with its old flags first still exits 2"
assert_contains "$OUT" "wake was folded into send" "and prints the pointer, never looking the seat up"
run "$SMINOS" wake
assert_contains "$OUT" "wake was folded into send" "a bare wake prints the pointer too"

# send --wait needs EVIDENCE the message landed (the frame's id in the
# target's transcript, or a busy row) before it waits for a reply.
{ echo "short=orch0001"; echo "uuid=$ORCH_UUID"; echo "name=my session"; echo "kind=interactive"; echo "state="; echo "status=idle"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/orch0001"
SMINOS_ACK_TIMEOUT=0.4 run "$SMINOS" send orchestrator "ACK-0" --wait
assert_rc 1 "$RC" "send --wait without evidence of receipt exits 1"
assert_not_contains "$OUT" "--- reply ---" "no reply block is printed without evidence"
"$SMINOS" meta set orchestrator status idle >/dev/null
( SMINOS_ACK_TIMEOUT=5 "$SMINOS" send orchestrator "ACK-1" --wait > "$TEST_ROOT/ack.out" 2>&1; echo $? > "$TEST_ROOT/ack.rc" ) &
ACKW=$!
sleep 0.5
ACK_ID="$(grep -o 'id=[0-9a-f]\{8\}' "$RECEIVED" | tail -1 | cut -d= -f2)"
mkdir -p "$HOME/.claude/projects/fake-proj"
python3 - "$HOME/.claude/projects/fake-proj/$ORCH_UUID.jsonl" "$ACK_ID" <<'PY'
import json, sys
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "[sminos message from human id=%s]\nACK-1" % sys.argv[2]}}) + "\n")
    f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ACKED " + sys.argv[2]}]}}) + "\n")
PY
wait "$ACKW" || true
assert_equals "$(cat "$TEST_ROOT/ack.rc")" "0" "send --wait exits 0 once the marker appears in the transcript"
assert_contains "$(cat "$TEST_ROOT/ack.out")" "sent to grp/orchestrator" "acknowledged send --wait names the seat"
assert_contains "$(cat "$TEST_ROOT/ack.out")" "--- reply ---" "acknowledged send --wait prints the reply block"
assert_contains "$(cat "$TEST_ROOT/ack.out")" "ACKED $ACK_ID" "acknowledged send --wait prints the turn's reply"

# Resume branch: 'researcher' has a session but no live peer → --bg --resume.
run "$SMINOS" send researcher "again please"
assert_rc 0 "$RC" "send to a stopped seat exits 0"
assert_contains "$OUT" "via --bg --resume" "a send to a stopped seat resumes the session"
assert_contains "$OUT" "sent to work/researcher" "the resume banner opens with the delivery"
RESUME_LINE="$(grep -- '^--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)"
assert_contains "$RESUME_LINE" "--bg --resume $R_UUID [sminos message from human id=" "resume argv is exactly --bg --resume <id> <frame>"
assert_not_contains "$RESUME_LINE" "--permission-mode" "no permission-mode flag rides a resume (it would start a copy)"
assert_not_contains "$RESUME_LINE" "-n " "no name flag rides a resume"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "same-id resume keeps current"
assert_equals "$(field "$R_UUID" turns)" "2" "resume increments turns"
assert_equals "$(field "$R_UUID" short)" "$R_SHORT" "a same-id resume keeps the session's short"
assert_equals "$(field "$R_UUID" status)" "idle" "a resume whose turn already ended records idle"
run "$SMINOS" send researcher "with reply" --wait
assert_contains "$OUT" "--- reply ---" "send --wait prints the reply block"
assert_contains "$OUT" "RESUMED:$R_UUID" "send --wait prints the resumed turn's reply"
STUB_RESUME_COPY=1 run "$SMINOS" send researcher "copy?"
assert_rc 1 "$RC" "a resume whose banner says a copy started fails loudly"
assert_contains "$OUT" "started a COPY" "copy detection is explained"
assert_equals "$(field "$R_UUID" current)" "$R_UUID" "the record is left untouched after a copy"
assert_equals "$(field "$R_UUID" status)" "idle" "status is restored after a copy"
COPY_SHORT="$(printf '%08x' "$(cat "$STUB_STATE/counter")")"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop $COPY_SHORT" "the announced copy is stopped"
STUB_RESUME_COPY=2 run "$SMINOS" send researcher "silent copy?"
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
# Resume lock: a resume already in flight refuses a twin.
python3 - "$SMINOS_HOME/$R_UUID.resume.lock" <<'PY' &
import fcntl, sys, time
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
LOCKER=$!
sleep 0.4
run "$SMINOS" send researcher "twin"
assert_rc 1 "$RC" "a second resume while one is in flight is refused"
assert_contains "$OUT" "already in flight" "twin refusal is explained"
kill "$LOCKER" 2>/dev/null || true; wait "$LOCKER" 2>/dev/null || true

# ---- 7) retire / fill --------------------------------------------------------
echo "retire / fill:"
run "$SMINOS" retire researcher
assert_rc 0 "$RC" "retire exits 0"
assert_equals "$(field "$R_UUID" status)" "retired" "retire marks the seat retired"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop $(field "$R_UUID" short)" "retire stops the current turn"
assert_contains "$OUT" "sminos fill work/researcher --resume" "retire hints at re-filling"
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$SMINOS" send researcher "are you there"
assert_rc 4 "$RC" "send to a retired seat is refused (exit 4)"
assert_contains "$OUT" "work/researcher is retired" "the refusal names the state"
assert_contains "$OUT" 'sminos fill work/researcher' "and points at fill"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no session is resumed for a retired seat"
run "$SMINOS" fill researcher "FRESH-START"
assert_rc 0 "$RC" "fresh fill exits 0"
assert_contains "$OUT" "seat filled: work/researcher" "fill reports the seat"
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

# ---- 8) status / meta / attach ----------------------------------------
echo "status / meta / attach:"
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
run "$SMINOS" meta set bearer-one status blocked
assert_contains "$OUT" "sminos: migrated: tightened the root to 0700; tightened 1 file(s) to 0600" "the next run says what it tightened"
"$SMINOS" meta set plainworker status blocked >/dev/null
assert_equals "$(mode_of "$SMINOS_HOME/66666666-ffff-4000-8000-000000000006.json")" "0600" "a bearer-carrying record stays 0600 across writes"
assert_equals "$(mode_of "$SMINOS_HOME/$P_UUID.json")" "0600" "a record left wider than 0600 is tightened on the next run"
assert_equals "$(mode_of "$SMINOS_HOME")" "0700" "a root left wider than 0700 is tightened on the next run"
"$SMINOS" remove bearer-one >/dev/null
run "$SMINOS" attach plainworker
assert_contains "$OUT" "claude attach $(field "$P_UUID" short)" "attach prints the harness command when not a TTY"
run "$SMINOS" status nope idle
assert_rc 4 "$RC" "an unknown seat exits 4"
run "$SMINOS" status "$(printf '%s' "$P_UUID" | cut -c1-8)" idle
assert_rc 4 "$RC" "a seat id prefix no longer names a seat"
assert_contains "$OUT" "no seat or member matching" "the prefix is reported as no seat"
run "$SMINOS" status "$(field "$P_UUID" short)" idle
assert_rc 4 "$RC" "a harness short id no longer names a seat"
run "$SMINOS" status "$P_UUID" idle
assert_rc 0 "$RC" "a full seat id resolves"
# A seat re-filled into a new session: its session id differs from its seat id.
RS_SEAT="0a0a1111-abab-4000-8000-0000000a1111"; RS_SESS="0a0a2222-abab-4000-8000-0000000a2222"
printf '{"uuid":"%s","alias":"refilled","group":"grp","status":"idle","current":"%s","short":"rs000001"}' \
  "$RS_SEAT" "$RS_SESS" > "$SMINOS_HOME/$RS_SEAT.json"
run "$SMINOS" status "$RS_SESS" idle
assert_contains "$OUT" "grp/refilled" "a full session id resolves to its seat"
run "$SMINOS" status "$(printf '%s' "$RS_SESS" | cut -c1-13)" idle
assert_rc 4 "$RC" "a session id prefix no longer names a seat"
run "$SMINOS" status rs000001 idle
assert_rc 4 "$RC" "nor does the short id the record carries"
"$SMINOS" remove grp/refilled >/dev/null

run "$SMINOS" list
assert_not_contains "$OUT" "null" "fleet list never prints null"
run "$SMINOS" list --state retired
assert_contains "$OUT" "wtworker" "--state filters"
assert_not_contains "$OUT" "orchestrator" "--state excludes other words"

# ---- 11) exit-gate wave ------------------------------------------------------
echo "exit-gate wave:"

# Redaction: a secret-shaped field never reaches a model-facing surface.
SEC_UUID="88888888-abab-4000-8000-000000000088"
printf '{"uuid":"%s","name":"secretary","alias":"secretary","group":"grp","status":"idle","current":"%s","run_bearer":"SEKRIT","api_token":"NOPE"}' \
  "$SEC_UUID" "$SEC_UUID" > "$SMINOS_HOME/$SEC_UUID.json"
run "$SMINOS" list --json grp
assert_not_contains "$OUT" "SEKRIT" "list --json never emits run_bearer"
assert_not_contains "$OUT" "NOPE" "list --json never emits a *_token field"
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
assert_equals "$OUT" "sminos: ambiguous seat 'dup' matches: ga/dup, gb/dup" "the ambiguity is named, not hidden by a name fallback"
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

# send's socket-send failure falls through to the resume path (never raises).
FAIL_UUID="bbbb2222-abab-4000-8000-0000000b2222"
"$SMINOS" seat add grp flaky --session "$FAIL_UUID" >/dev/null
printf '{"pid":%s,"sessionId":"%s","name":"flaky","kind":"bg","status":"idle","messagingSocketPath":"%s"}\n' \
  "$$" "$FAIL_UUID" "$SOCK" > "$HOME/.claude/sessions/flaky.json"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/fake-proj/$FAIL_UUID.jsonl"   # resumable: its transcript is here
kill "$SOCK_PID" 2>/dev/null || true; wait "$SOCK_PID" 2>/dev/null || true; rm -f "$SOCK"   # socket_ok now fails
run "$SMINOS" send grp/flaky "PLEASE"
assert_rc 0 "$RC" "send whose live socket vanished still exits 0 via the resume fallback"
assert_contains "$OUT" "via --bg --resume" "the vanished-socket send fell through to resume"
rm -f "$HOME/.claude/sessions/flaky.json"; "$SMINOS" remove grp/flaky >/dev/null
# restart the socket server for any later use / clean teardown
python3 "$TEST_ROOT/sockserver.py" "$SOCK" "$RECEIVED" & SOCK_PID=$!; disown "$SOCK_PID"
for _ in $(seq 1 50); do [ -S "$SOCK" ] && break; sleep 0.05; done

# Legacy records remain read-only history: remove drops the record, not its
# unrelated historical scratch file.
CX_UUID="cccc3333-abab-4000-8000-0000000c3333"
EL="$TEST_ROOT/legacy.events.jsonl"
: > "$EL"
printf '{"uuid":"%s","name":"cx","alias":"cx","group":"grp","status":"retired","engine":"codex","event_log":"%s"}' \
  "$CX_UUID" "$EL" > "$SMINOS_HOME/$CX_UUID.json"
run "$SMINOS" remove grp/cx
assert_rc 0 "$RC" "removing a legacy record succeeds"
assert_file_absent "$SMINOS_HOME/$CX_UUID.json" "remove deletes legacy record"
assert_file_exists "$EL" "remove leaves legacy history alone"

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
run "$SMINOS" spawn nodir "X" --cwd "$TEST_ROOT/does-not-exist"
assert_rc 2 "$RC" "spawn with a nonexistent cwd exits 2"
assert_contains "$OUT" "cwd does not exist" "the missing cwd is named"

# ---- 11b) exit-gate round 2 --------------------------------------------------
echo "exit-gate round 2:"

# Integration shape: spawn → retire → spawn (same alias). The second banner's
# bracket uuid is the record filename; attempts and history track the occupants.
run "$SMINOS" spawn resp "R-1" --role reviewer
RESP="$(seat_id_of resp)"
assert_equals "$(banner_uuid "$OUT")" "$RESP" "a new seat's banner bracket is its record filename"
RESP_FIRST="$(field "$RESP" current)"
# The pipeline stamps a failed occupant (retired_from + a note) before retiring
# it, and retire then writes status=retired over the failure — so the stamp and
# its note are the only surviving evidence that this occupant failed. History
# must carry both, or the outage streak forgets every retired failure.
"$SMINOS" meta set resp status error note "worker died mid-run" >/dev/null
"$SMINOS" meta set resp retired_from failure >/dev/null
run "$SMINOS" retire resp
assert_rc 0 "$RC" "retire exits 0"
run "$SMINOS" spawn resp "R-2"
assert_rc 0 "$RC" "re-spawning a retired seat exits 0"
assert_equals "$(banner_uuid "$OUT")" "$RESP" "the re-spawn banner's bracket uuid equals the record filename"
assert_equals "$(field "$RESP" attempts)" "2" "attempts == 2 after one re-spawn"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0]["current"])' "$SMINOS_HOME/$RESP.json")" "$RESP_FIRST" "history[0].current is the first session"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0].get("retired_from",""))' "$SMINOS_HOME/$RESP.json")" "failure" "history[0] carries the predecessor's retired_from stamp"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["history"][0].get("note",""))' "$SMINOS_HOME/$RESP.json")" "worker died mid-run" "history[0] carries the note explaining the failure"
assert_equals "$(field "$RESP" retired_from)" "" "the re-filled record itself drops the predecessor's stamp"
assert_equals "$(field "$RESP" role)" "reviewer" "re-spawn without --role keeps the role"
"$SMINOS" remove work/resp >/dev/null

# Re-fill of a retired legacy record clears its engine fields for the new
# Claude occupant; old scratch is historical and not deleted.
CXR_UUID="dddd4444-abab-4000-8000-0000000d4444"
mkdir -p "$TEST_ROOT/codexruns"
: > "$TEST_ROOT/codexruns/cxr.events.jsonl"; : > "$TEST_ROOT/codexruns/cxr.rc"
printf '{"uuid":"%s","name":"cxr","alias":"cxr","group":"work","status":"idle","current":"","engine":"codex","pid":"99999","event_log":"%s/codexruns/cxr.events.jsonl","cwd":"%s"}' \
  "$CXR_UUID" "$TEST_ROOT" "$WORK" > "$SMINOS_HOME/$CXR_UUID.json"
run "$SMINOS" spawn cxr "CLAUDE-NOW"
assert_rc 0 "$RC" "re-spawning a retired codex seat exits 0"
assert_equals "$(field "$CXR_UUID" engine)" "" "re-fill clears engine"
assert_equals "$(field "$CXR_UUID" pid)" "" "re-fill clears pid"
assert_equals "$(field "$CXR_UUID" event_log)" "" "re-fill clears event_log"
assert_file_exists "$TEST_ROOT/codexruns/cxr.rc" "re-fill leaves legacy scratch alone"
"$SMINOS" remove work/cxr >/dev/null

# A vanished cwd refuses a resume (exit 2) without launching anything.
run "$SMINOS" spawn nocwd "N"
"$SMINOS" meta set nocwd cwd "$TEST_ROOT/vanished" >/dev/null
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
run "$SMINOS" resume nocwd "x"
assert_rc 2 "$RC" "resume with a vanished cwd exits 2"
assert_contains "$OUT" "cwd does not exist" "the vanished cwd is named"
run "$SMINOS" send nocwd "x"
assert_rc 2 "$RC" "a send that resumes, with a vanished cwd, exits 2"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "nothing is launched for a vanished cwd"
"$SMINOS" meta set nocwd cwd "$WORK" >/dev/null; "$SMINOS" remove work/nocwd >/dev/null

# Generation guard: a retire during a --wait watcher wins; the watcher writes
# neither status nor a reply over it.
( STUB_BG_STATE=working SMINOS_POLL_INTERVAL=0.1 DAEMON_TIMEOUT=20 "$SMINOS" spawn genseat "GEN" --wait > "$TEST_ROOT/gen.out" 2>&1; echo $? > "$TEST_ROOT/gen.rc" ) &
GENW=$!
sleep 0.8
GEN="$(seat_id_of genseat)"
run "$SMINOS" retire genseat
assert_rc 0 "$RC" "retire while a watcher waits exits 0"
wait "$GENW" || true
assert_equals "$(field "$GEN" status)" "retired" "the watcher's finalize does not overwrite a retire"
assert_file_absent "$SMINOS_HOME/$GEN.reply.txt" "no reply file is written over a retired seat"
"$SMINOS" remove work/genseat >/dev/null

# resume: a refused or ineffective `claude stop` aborts before any launch.
STUB_BG_STATE=working run "$SMINOS" spawn stopper "S"
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")
STUB_STOP_FAIL=1 run "$SMINOS" resume stopper "x"
assert_rc 1 "$RC" "a refused claude stop aborts the resume"
assert_contains "$OUT" "claude stop" "the stop failure is surfaced"
STUB_STOP_NOOP=1 SMINOS_STOP_TIMEOUT=0.3 run "$SMINOS" resume stopper "x"
assert_rc 1 "$RC" "a turn still running after the stop deadline aborts the resume"
assert_contains "$OUT" "still running" "the still-running turn is reported"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log")" "$nb" "no resume is launched over a running turn"
"$SMINOS" remove work/stopper >/dev/null

# send respects the lifecycle lock.
python3 - "$(lock_file work/plainworker)" <<'PY' &
import fcntl, os, sys, time
os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
f = open(sys.argv[1], "a+")
fcntl.flock(f, fcntl.LOCK_EX)
time.sleep(3)
PY
HOLDER=$!
sleep 0.4
run "$SMINOS" send plainworker "x"
assert_rc 4 "$RC" "send while the seat's lifecycle lock is held is refused"
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

# One liveness probe both classifies a send and routes it. A second probe could
# disagree with the first (the session came up, or went away, in between) and
# route a live seat to a resume, which stops and relaunches its turn.
PROBE_UUID="0f0f1212-abab-4000-8000-0000000f1212"
"$SMINOS" seat add grp probed --session "$PROBE_UUID" >/dev/null
printf '{"type":"user"}\n' > "$HOME/.claude/projects/fake-proj/$PROBE_UUID.jsonl"
PROBE_OUT="$(python3 - "$REPO_ROOT/skills/sminos/scripts" "$PROBE_UUID" "$SOCK" <<'PY'
import contextlib, io, sys
sys.path.insert(0, sys.argv[1])
import sminos
sid, sock = sys.argv[2], sys.argv[3]
live = {"pid": 1, "sessionId": sid, "status": "idle", "messagingSocketPath": sock}
out = []
for first_live in (True, False):
    probes, actions = [], []
    def probe(cur, first_live=first_live):
        probes.append(cur)
        return live if (len(probes) == 1) == first_live else None
    sminos.peer_for_session = probe
    sminos.send_frame = lambda path, text: actions.append("socket")
    sminos.resume_session = lambda *a, **k: actions.append("resume")
    sminos.harness_row = lambda s: None
    with contextlib.redirect_stdout(io.StringIO()):
        sminos.send_to_seat(sminos.resolve_seat("grp/probed"), "frame", "abcd1234", False)
    out.append("%s:%d:%s" % ("live-first" if first_live else "dead-first", len(probes), ",".join(actions)))
print(" ".join(out))
PY
)"
assert_equals "$PROBE_OUT" "live-first:1:socket dead-first:1:resume" "a send probes its seat once and routes on that probe"
rm -f "$HOME/.claude/projects/fake-proj/$PROBE_UUID.jsonl"; "$SMINOS" remove grp/probed >/dev/null

# A session's transcript sits directly in a project dir; the newest copy wins
# when a moved repository left one under two dirs, and a file nested deeper
# (where subagent transcripts live) is not a session transcript.
TP_UUID="0f0f3434-abab-4000-8000-0000000f3434"
mkdir -p "$HOME/.claude/projects/old-dir" "$HOME/.claude/projects/new-dir" "$HOME/.claude/projects/deep/x/subagents"
: > "$HOME/.claude/projects/old-dir/$TP_UUID.jsonl"; : > "$HOME/.claude/projects/new-dir/$TP_UUID.jsonl"
python3 -c 'import os, sys, time; t = time.time(); os.utime(sys.argv[1], (t - 60, t - 60))' "$HOME/.claude/projects/old-dir/$TP_UUID.jsonl"
: > "$HOME/.claude/projects/deep/x/subagents/0f0f5656-abab-4000-8000-0000000f5656.jsonl"
TP_OUT="$(python3 - "$REPO_ROOT/skills/sminos/scripts" "$TP_UUID" <<'PY'
import os, sys
sys.path.insert(0, sys.argv[1])
import sminos
print(os.path.basename(os.path.dirname(sminos.transcript_path(sys.argv[2]))),
      repr(sminos.transcript_path("0f0f5656-abab-4000-8000-0000000f5656")))
PY
)"
assert_equals "$TP_OUT" "new-dir ''" "transcript_path finds the newest one-level copy and nothing nested"
rm -rf "$HOME/.claude/projects/old-dir" "$HOME/.claude/projects/new-dir" "$HOME/.claude/projects/deep"

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
run "$SMINOS" send grp/oneshot "HELLO"
assert_rc 0 "$RC" "a socket that vanishes before the frame is written falls through to resume (exit 0)"
assert_contains "$OUT" "failed before the frame was written" "the pre-write failure is explained"
assert_contains "$OUT" "via --bg --resume" "the send completed via resume"
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
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from human id=' "no session id in the environment → human"
ID_UUID="0b0b8888-abab-4000-8000-0000000b8888"
"$SMINOS" seat add grp me-agent --session "$ID_UUID" >/dev/null
CLAUDE_CODE_SESSION_ID="$ID_UUID" run "$SMINOS" send orchestrator "from an agent"
assert_rc 0 "$RC" "send from a registered agent session exits 0"
sleep 0.2
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from me-agent id=' "an agent's default --from is its seat alias"
CLAUDE_CODE_SESSION_ID="$ID_UUID" run "$SMINOS" send orchestrator "impostor" --from human
assert_rc 4 "$RC" "--from human inside a Claude session is refused"
"$SMINOS" remove grp/me-agent >/dev/null
run "$SMINOS" spawn me-agent "NON-FAMILY-IDENTITY"  # no explicit group, no preamble
PLAIN_ME="$(banner_uuid "$OUT")"
CLAUDE_CODE_SESSION_ID="$PLAIN_ME" run "$SMINOS" send orchestrator "from a pipeline root"
assert_rc 0 "$RC" "a non-family seat still sends to an unrelated seat"
sleep 0.2
assert_contains "$(tail -c 400 "$RECEIVED")" '[sminos message from me-agent id=' "a non-family seat still derives sender alias"
"$SMINOS" remove work/me-agent >/dev/null

# A harness failure is never read as an empty fleet.
STUB_BG_STATE=working run "$SMINOS" spawn unk "U"
STUB_AGENTS_FAIL=1 run "$SMINOS" sync unk
assert_equals "$OUT" "live" "sync claims nothing (live) when the harness fails"
assert_equals "$(field "$(seat_id_of unk)" status)" "working" "a harness failure never finalizes a seat"
"$SMINOS" remove work/unk >/dev/null

# A previous occupant that still answers blocks a fresh re-fill.
PO_UUID="0c0c9999-abab-4000-8000-0000000c9999"
"$SMINOS" seat add work prevocc --session "$PO_UUID" >/dev/null
"$SMINOS" meta set prevocc status retired >/dev/null
printf '{"pid":%s,"sessionId":"%s","name":"prevocc","kind":"bg","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$PO_UUID" "$SOCK" > "$HOME/.claude/sessions/prevocc.json"
run "$SMINOS" spawn prevocc "again"
assert_rc 4 "$RC" "re-spawn is refused while the previous occupant still answers"
assert_contains "$OUT" "previous occupant" "the live previous occupant is named"
assert_contains "$OUT" "use sminos resume, or stop it first" "the hint names resume"
assert_not_contains "$OUT" "sminos send" "and not send, which refuses a retired seat"
run "$SMINOS" fill work/prevocc "again"
assert_rc 4 "$RC" "fresh fill is refused while the previous occupant still answers"
assert_contains "$OUT" "use sminos resume, or stop it" "fill's hint names resume"
assert_not_contains "$OUT" "sminos send" "and not send"
rm -f "$HOME/.claude/sessions/prevocc.json"; "$SMINOS" remove work/prevocc >/dev/null

# Repointing a seat whose occupant is STILL LIVE would leave that process
# running with nothing in the fleet naming it: refused, and the record is left
# exactly as it was.
RPT_UUID="0e0ebbbb-abab-4000-8000-0000000ebbbb"
"$SMINOS" seat add grp pinned --session "$RPT_UUID" >/dev/null
# The live session answers to the harness name it already had (a `seat add
# --session` seat was never named by sminos) — only the record ties the
# process to the fleet.
printf '{"pid":%s,"sessionId":"%s","name":"a name sminos never chose","kind":"interactive","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$RPT_UUID" "$SOCK" > "$HOME/.claude/sessions/pinned.json"
run "$SMINOS" seat add grp pinned --session "0e0ecccc-abab-4000-8000-0000000ecccc"
assert_rc 4 "$RC" "re-pointing a seat whose session is still live is refused"
assert_contains "$OUT" "still holds a live session" "the refusal names the live session"
assert_not_contains "$OUT" "addr" "the refusal names no addr"
assert_equals "$(printf '%s' "$OUT" | grep -c .)" "1" "the refusal is one stderr line"
assert_equals "$(field "$RPT_UUID" current)" "$RPT_UUID" "the refused re-point left the session untouched"
run "$SMINOS" seat add grp pinned --role keeper
assert_rc 0 "$RC" "a seat add that re-points nothing succeeds while the occupant is live"
run "$SMINOS" list work --json
assert_contains "$OUT" '"alias": "pinned"' "a joined session lists under its alias"
assert_not_contains "$OUT" "a name sminos never chose" "never under the harness name it kept"
run "$SMINOS" list work
assert_contains "$OUT" "pinned" "the joined seat's row reads its alias"
assert_contains "$(printf '%s\n' "$OUT" | grep pinned)" "idle" "with its session's live word"
rm -f "$HOME/.claude/sessions/pinned.json"
run "$SMINOS" seat add grp pinned --session "0e0ecccc-abab-4000-8000-0000000ecccc"
assert_rc 0 "$RC" "once the occupant is gone the same re-point succeeds"
assert_equals "$(field "$RPT_UUID" current)" "0e0ecccc-abab-4000-8000-0000000ecccc" "and the new session is recorded"
"$SMINOS" remove grp/pinned >/dev/null

# harness_row prefers a RUNNING row for the session over the recorded short
# (attach reads it for the short id to attach to).
HR_UUID="0d0daaaa-abab-4000-8000-0000000daaaa"
"$SMINOS" seat add grp revived --session "$HR_UUID" >/dev/null
"$SMINOS" meta set revived short hr000001 >/dev/null
{ echo "short=hr000001"; echo "uuid=$HR_UUID"; echo "name=revived"; echo "state=stopped"; echo "status="; echo "cwd=$WORK"; } > "$STUB_STATE/agents/hr000001"
{ echo "short=hr000002"; echo "uuid=$HR_UUID"; echo "name=revived"; echo "state=working"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/hr000002"
run "$SMINOS" attach grp/revived
assert_equals "$OUT" "claude attach hr000002" "an out-of-band revival's running row wins over the stale recorded short"
rm -f "$STUB_STATE/agents/hr000001" "$STUB_STATE/agents/hr000002"; "$SMINOS" remove grp/revived >/dev/null

# peer liveness: a recycled pid (procStart differs from the live process) is dead.
RP_UUID="0e0ebbbb-abab-4000-8000-0000000ebbbb"
printf '{"pid":%s,"sessionId":"%s","name":"recycled","kind":"bg","status":"idle","procStart":"Mon Jan  1 00:00:00 1990","messagingSocketPath":"%s"}\n' \
  "$$" "$RP_UUID" "$SOCK" > "$HOME/.claude/sessions/recycled.json"
run "$SMINOS" send recycled "R"
assert_rc 4 "$RC" "a peer record whose procStart does not match the live pid is not a live session to send to"
LSTART="$(LC_ALL=C ps -o lstart= -p $$ | sed 's/  */ /g;s/^ //;s/ $//')"
printf '{"pid":%s,"sessionId":"%s","name":"recycled","kind":"bg","status":"idle","procStart":"%s","messagingSocketPath":"%s"}\n' \
  "$$" "$RP_UUID" "$LSTART" "$SOCK" > "$HOME/.claude/sessions/recycled.json"
run "$SMINOS" send recycled "R"
assert_rc 0 "$RC" "a peer record whose procStart matches the live pid is live"
assert_contains "$OUT" "sent to session recycled" "and the raw-name send reaches it"
rm -f "$HOME/.claude/sessions/recycled.json"

# status / meta set never resurrect a removed seat (unit level).
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
RAW_CODES="$(python3 - "$REPO_ROOT/skills/sminos/scripts" 2>"$TEST_ROOT/raw-codes.err" <<'PY'
import argparse, sys
sys.path.insert(0, sys.argv[1])
import sminos
codes = []
for phase in ("before", "after"):
    def boom(path, text, phase=phase):
        raise sminos.SendFailed(phase, OSError("injected"))
    sminos.send_frame = boom
    try:
        sminos.cmd_send(argparse.Namespace(target="rawname", msg="x", frm="", wait=False))
        codes.append("0")
    except SystemExit as e:
        codes.append(str(e.code))
print(" ".join(codes))
PY
)"
assert_equals "$RAW_CODES" "4 1" "raw-name send: failure before the write exits 4, after the write exits 1"
assert_contains "$(cat "$TEST_ROOT/raw-codes.err")" "session 'rawname' went away mid-send (injected) — not live" "the failure before the write says the session is not live"
assert_contains "$(cat "$TEST_ROOT/raw-codes.err")" "delivery to session 'rawname' is UNCERTAIN" "the failure after the write says delivery is uncertain"
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
run env -u SMINOS_HOME HOME="$AM" "$SMINOS" list
MERGED_BOARD="$AM/.claude/sminos/groups/g1/board.jsonl"
assert_equals "$(python3 -c 'import json,sys; print(len([json.loads(line) for line in open(sys.argv[1])]))' "$MERGED_BOARD")" "3" "aside board posts are appended to the root board"
assert_contains "$(cat "$MERGED_BOARD")" '"id": 3' "appended posts are renumbered after the root's last id"
assert_contains "$(cat "$MERGED_BOARD")" "aside two" "the aside's posts survive the merge"
assert_contains "$OUT" "unmerged aside entry left in place" "a non-board collision is warned about"
run env -u SMINOS_HOME HOME="$AM" "$SMINOS" list
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
run "$SMINOS" list work --all
assert_not_contains "$OUT" "scribe" "removed seat is gone"

# ---- 12b) the state word: one word per seat, from the session record ---------
# A live seat's word comes from ~/.claude/sessions/<pid>.json plus one socket
# connect; only a seat with no live peer asks `claude agents` (stopped when it
# lists the session or cannot be asked, else gone). Each case constructs a seat
# record, (where live) a peer record on the suite's socket server, whose pid is
# alive, and (where listed) a harness row.
echo "state word:"
ST_BUSY=5a5a0001-0000-4000-8000-00000000a001
ST_SHELL=5a5a0002-0000-4000-8000-00000000a002
ST_BARE=5a5a0003-0000-4000-8000-00000000a003
ST_IDLE=5a5a0004-0000-4000-8000-00000000a004
ST_WAIT=5a5a0005-0000-4000-8000-00000000a005
ST_STOP=5a5a0006-0000-4000-8000-00000000a006
ST_RET=5a5a0007-0000-4000-8000-00000000a007
ST_LONG=5a5a0008-0000-4000-8000-00000000a008
ST_GONE=5a5a000a-0000-4000-8000-00000000a00a
st_peer() { # session-id alias extra-json [pid]
  printf '{"pid":%s,"sessionId":"%s","name":"%s","kind":"background"%s,"messagingSocketPath":"%s"}\n' \
    "${4:-$SOCK_PID}" "$1" "$2" "$3" "$SOCK" > "$HOME/.claude/sessions/st-$2.json"
}
( exit 0 ) & DEAD_PID=$!
wait "$DEAD_PID" || true
st_peer "$ST_BUSY" s-busy ',"status":"busy"'
st_peer "$ST_SHELL" s-shell ',"status":"shell"'
st_peer "$ST_BARE" s-bare ''
st_peer "$ST_IDLE" s-idle ',"status":"idle"'
st_peer "$ST_WAIT" s-wait ',"status":"waiting","waitingFor":"permission to run rm"'
st_peer "$ST_STOP" s-stop ',"status":"busy"' "$DEAD_PID"   # a dead pid whose socket FILE still answers
st_peer "$ST_RET" s-ret ',"status":"idle"'                  # retired wins over a session that answers
st_peer "$ST_LONG" lone-seat-with-a-long-name-past-24 ',"status":"busy"'
# Each fixture lives in a directory of its own, so it is a project of its own
# (a directory in no repository names its seats' project): st, st2, st4.
mkdir -p "$TEST_ROOT/st" "$TEST_ROOT/st2" "$TEST_ROOT/st4"
cd "$TEST_ROOT/st"
"$SMINOS" seat add st s-busy --session "$ST_BUSY" >/dev/null
"$SMINOS" seat add st s-shell --session "$ST_SHELL" >/dev/null
"$SMINOS" seat add st s-bare --session "$ST_BARE" >/dev/null
"$SMINOS" seat add st s-idle --role scout --session "$ST_IDLE" >/dev/null
"$SMINOS" seat add st s-wait --session "$ST_WAIT" >/dev/null
"$SMINOS" seat add st s-stop --session "$ST_STOP" >/dev/null
# s-stop's transcript is on this machine and the harness does not list it;
# s-gone's session is listed by the harness but has no transcript here. The
# transcript decides: it is what a `claude --bg --resume` needs.
mkdir -p "$HOME/.claude/projects/fake-proj"
printf '{"type":"user","message":{"role":"user","content":"start"}}\n' > "$HOME/.claude/projects/fake-proj/$ST_STOP.jsonl"
{ echo "short=5a5a000a"; echo "uuid=$ST_GONE"; echo "name=s-gone"; echo "state=stopped"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/5a5a000a"
"$SMINOS" seat add st s-gone --session "$ST_GONE" >/dev/null
"$SMINOS" seat add st s-ret --session "$ST_RET" >/dev/null
"$SMINOS" meta set st/s-ret status retired >/dev/null
"$SMINOS" seat add st s-vac >/dev/null
# The recorded status never speaks for the word: a `working` record whose
# session is idle reads idle.
"$SMINOS" meta set st/s-idle status working >/dev/null
st_state() { # alias → the state key of its list --json row
  "$SMINOS" list st --json | python3 -c 'import json, sys
print(next(d["state"] for d in json.load(sys.stdin) if d["alias"] == sys.argv[1]))' "$1"
}
assert_equals "$(st_state s-busy)" "busy" "a live peer whose status is busy reads busy"
assert_equals "$(st_state s-shell)" "busy" "a live peer whose status is shell reads busy"
assert_equals "$(st_state s-bare)" "busy" "a live peer with no status reads busy"
assert_equals "$(st_state s-idle)" "idle" "a live peer whose status is idle reads idle (the recorded working says nothing)"
assert_equals "$(st_state s-wait)" "waiting" "a live peer whose status is waiting reads waiting"
assert_equals "$(st_state s-stop)" "stopped" "a dead pid with a socket file, its transcript here and no harness row, reads stopped"
assert_equals "$(st_state s-gone)" "gone" "a session id with no live peer and no transcript here reads gone, though the harness lists it"
assert_equals "$(STUB_AGENTS_FAIL=1 st_state s-gone)" "gone" "the harness is not asked: a failing listing changes no word"
assert_equals "$(st_state s-ret)" "retired" "a retired record reads retired even while its session answers"
assert_equals "$(st_state s-vac)" "vacant" "a seat with no current session reads vacant"
run "$SMINOS" list st --json
assert_rc 0 "$RC" "list --json exits 0"
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys
rows = json.load(sys.stdin)
print(len(rows) == 9 and all("state" in d and "live" not in d and "addr" not in d and "addr" not in d["seat"] and
                             all(k in d for k in ("session", "short", "status", "seat", "project")) for d in rows))')" \
  "True" "list --json rows carry state and the ids, never live or addr"
# A record written before the one name keeps its stale addr (and a name that
# held it) on disk; nothing reads either, so neither surfaces.
ST_OLD=5a5a0009-0000-4000-8000-00000000a009
printf '{"uuid":"%s","alias":"s-old","name":"old harness name","addr":"old harness name","group":"st3","status":"retired","current":""}' \
  "$ST_OLD" > "$SMINOS_HOME/$ST_OLD.json"
run "$SMINOS" list st3 --json
assert_not_contains "$OUT" "old harness name" "a stale addr or name on disk never reaches list --json"
assert_contains "$OUT" '"name": "s-old"' "the record's name reads as its alias"
"$SMINOS" remove st3/s-old >/dev/null
"$SMINOS" meta set st/s-busy now "parsing the schema" >/dev/null
(cd "$TEST_ROOT/st2" && "$SMINOS" seat add st2 lone-seat-with-a-long-name-past-24 --session "$ST_LONG" >/dev/null)
(cd "$TEST_ROOT/st2" && "$SMINOS" seat add st2 z --role reviewer >/dev/null)
run "$SMINOS" list st
assert_rc 0 "$RC" "list of a project exits 0"
st_rows() { # alias word rest ... → rows as list prints them (alias padded to 7, word to 7)
  while [ $# -gt 0 ]; do printf '  %-7s   %-7s  %s\n' "$1" "$2" "$3"; shift 3; done | sed 's/ *$//'
}
# Members newest join first (the seats joined in the order they were added),
# then the seats no member stands for; the line is the in-charge line, then
# `· now:` the status. Retired and gone fold into a tail line, as chart and
# tui do; --all shows them in place; --json keeps them.
EXPECTED_ST_ALL="$(printf 'st\n'; st_rows s-ret retired '' s-gone gone '' s-stop stopped '' s-wait waiting '' \
  s-idle idle '' s-bare busy '' s-shell busy '' s-busy busy '· now: parsing the schema' s-vac vacant '')"
EXPECTED_ST="$(printf 'st\n'; st_rows s-stop stopped '' s-wait waiting '' s-idle idle '' s-bare busy '' \
  s-shell busy '' s-busy busy '· now: parsing the schema' s-vac vacant ''
  printf '+2 hidden (retired, gone) — sminos list --all')"
assert_equals "$OUT" "$EXPECTED_ST" "list is the project heading, then alias, state word, and the member's lines — no header, ids, or recorded status; retired and gone fold into the tail"
run "$SMINOS" list st --all
assert_equals "$OUT" "$EXPECTED_ST_ALL" "--all shows the retired and gone rows in place and prints no tail"
run "$SMINOS" list --json st
assert_contains "$OUT" '"state": "retired"' "--json keeps a retired row"
assert_contains "$OUT" '"state": "gone"' "--json keeps a gone row"
(cd "$TEST_ROOT/st4" && "$SMINOS" seat add st4 ghost --session 0e0e0e0e-0e0e-4000-8000-0e0e0e0e0e0e >/dev/null)
run "$SMINOS" list st4
assert_equals "$OUT" "$(printf '(no members)\n+1 hidden (retired, gone) — sminos list --all')" "a project of only folded members says so, then the count on its own line"
"$SMINOS" remove st4/ghost >/dev/null
run "$SMINOS" list --all
EXPECTED_ST2="$(printf 'st2\n  %s   busy\n  %-24s   vacant\n' lone-seat-with-a-long-name-past-24 z)"
assert_contains "$OUT" "$EXPECTED_ST2" "--all lists every project; an alias pads to at most 24 cells and is never cut"
assert_not_contains "$OUT" "ALIAS" "list prints no header line"
run "$SMINOS" list st --state busy
assert_equals "$(printf '%s\n' "$OUT" | sed 1d | awk '{print $1}' | tr '\n' ' ')" "s-bare s-shell s-busy " "--state keeps only the rows with that word"
run "$SMINOS" list st --state gone
assert_equals "$OUT" "$(printf 'st\n  s-gone   gone')" "--state gone keeps only the gone rows"
run "$SMINOS" list st --state blocked
assert_rc 2 "$RC" "--state accepts only the seven words"
run "$SMINOS" list st --status retired
assert_rc 2 "$RC" "--status is gone, not aliased"
run "$SMINOS" list nosuchproject
assert_rc 4 "$RC" "list of a project not known here exits 4"
assert_equals "$OUT" "sminos: no project 'nosuchproject' is known on this machine" "and says so"
# The word never asks the harness listing: list runs no `claude agents`, even
# for a group whose seats have no live peer.
: > "$STUB_STATE/log/calls.log"
"$SMINOS" list st --json >/dev/null
"$SMINOS" list st >/dev/null
assert_equals "$(grep -c '^agents' "$STUB_STATE/log/calls.log" || true)" "0" "list runs no claude agents, even for seats with no live peer"
STUB_AGENTS_FAIL=1 run "$SMINOS" list st --all
assert_rc 0 "$RC" "list is unaffected by a failing harness"
assert_contains "$OUT" "s-idle    idle" "and still reads the live word"
assert_contains "$OUT" "s-gone    gone" "and a gone member stays gone"
# The chart's hide rule is the word: retired or gone.
run "$SMINOS" chart st --width 200
assert_contains "$OUT" "■ stopped" "a stopped seat is charted with its glyph"
assert_contains "$OUT" "◐ waiting" "a waiting seat is charted with the half glyph"
assert_not_contains "$OUT" "s-ret" "a retired seat is hidden by default"
assert_not_contains "$OUT" "s-gone" "a gone seat is hidden by default"
assert_contains "$OUT" "9 members · 5 live · 2 hidden" "live counts busy, idle and waiting; hidden counts retired and gone"
STUB_AGENTS_FAIL=1 run "$SMINOS" chart st --width 200
assert_not_contains "$OUT" "s-gone" "a failing harness listing does not bring a gone seat back onto the chart"
run "$SMINOS" chart st --all --width 200
assert_contains "$OUT" "⊘ retired" "--all shows the retired seat with its glyph"
assert_contains "$OUT" "✕ gone" "--all shows the gone seat with its glyph"
VIEWS="$(cat <<<"$OUT")
$("$SMINOS" list st)
$("$SMINOS" tui st --headless --all --width 140 --height 40)"
for w in blocked unknown working "done" error failed; do
  assert_not_contains "$VIEWS" " $w" "no view draws the retired word '$w'"
done
run "$SMINOS" tui st --headless --width 140 --height 40 --keys "!focus:st/s-stop,s"
assert_contains "$OUT" "send → st/s-stop ▏" "s on a stopped seat opens the send line (the send resumes it)"
run "$SMINOS" send st/s-gone "hi"
assert_rc 4 "$RC" "send to a gone seat is refused (exit 4)"
assert_equals "$OUT" 'sminos: seat st/s-gone is gone — no transcript for its session on this machine; sminos fill st/s-gone "<task>" or sminos retire st/s-gone' "the gone refusal is one line pointing at fill and retire"
run "$SMINOS" send st/s-ret "hi"
assert_rc 4 "$RC" "send to a retired seat is refused even while its session answers"
assert_contains "$OUT" "sminos fill st/s-ret" "pointing at fill"
nb=$(grep -c -- '^--bg --resume' "$STUB_STATE/log/calls.log" || true)
run "$SMINOS" tui st --headless --width 140 --height 40 --keys "!focus:st/s-stop,s,text:back to work,enter"
assert_contains "$OUT" "send s-stop back to work → rc=0 sent to st/s-stop" "the TUI's send to a stopped seat resumes it"
assert_equals "$(grep -c -- '^--bg --resume' "$STUB_STATE/log/calls.log" || true)" "$((nb + 1))" "through one --bg --resume"
assert_contains "$(grep -- '^--bg --resume' "$STUB_STATE/log/calls.log" | tail -1)" "--bg --resume $ST_STOP [sminos message from human id=" "carrying the frame"
run "$SMINOS" tui st --headless --all --width 140 --height 40 --keys "!focus:st/s-ret,s"
assert_not_contains "$OUT" "send → st/s-ret" "s on a retired seat opens no send line"
assert_contains "$OUT" "s-ret is retired" "and says why"
run "$SMINOS" tui st --headless --all --width 140 --height 40 --keys "!focus:st/s-gone,s"
assert_not_contains "$OUT" "send → st/s-gone" "s on a gone seat opens no send line"
assert_contains "$OUT" "s-gone is gone — no transcript for its session on this machine" "and says why"
assert_contains "$OUT" "sminos fill st/s-gone" "pointing at fill"
run "$SMINOS" reply st/s-idle
assert_contains "$OUT" "st/s-idle  [$ST_IDLE]  state=idle  turns=" "reply's summary line carries the state word, not the recorded status"
rm -f "$STUB_STATE/agents/5a5a000a" "$HOME/.claude/sessions/"st-*.json
for a in s-busy s-shell s-bare s-idle s-wait s-stop s-gone s-ret s-vac; do "$SMINOS" remove "st/$a" >/dev/null; done
"$SMINOS" remove st2/lone-seat-with-a-long-name-past-24 >/dev/null
"$SMINOS" remove st2/z >/dev/null
cd "$WORK"

# ---- 13) chart: the members as boxes ---------------------------------------------
# The `org` fixture below is shared with the tui tests that follow it: a project
# of its own (the directory org) whose members are lead (busy), scout (idle),
# scribe (busy), qa (waiting), a vacant intern, and a retired old-worker folded
# away. There is no tree: the members stand in one column, newest join first.
# Every state word comes from a peer record on the suite's socket server.
echo "chart:"
mkdir -p "$TEST_ROOT/org"
cd "$TEST_ROOT/org"
LEAD_UUID=cccc0001-0000-4000-8000-00000000c001
SCOUT_UUID=cccc0002-0000-4000-8000-00000000c002
SCRIBE_UUID=cccc0003-0000-4000-8000-00000000c003
QA_UUID=cccc0004-0000-4000-8000-00000000c004
{ echo "short=cc000001"; echo "uuid=$LEAD_UUID"; echo "name=lead"; echo "state=working"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000001"
{ echo "short=cc000002"; echo "uuid=$SCOUT_UUID"; echo "name=scout"; echo "state=done"; echo "status="; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000002"
{ echo "short=cc000003"; echo "uuid=$SCRIBE_UUID"; echo "name=scribe"; echo "state=working"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000003"
{ echo "short=cc000004"; echo "uuid=$QA_UUID"; echo "name=qa"; echo "state=blocked"; echo "status=busy"; echo "cwd=$WORK"; } > "$STUB_STATE/agents/cc000004"
org_peer() { # alias session-id status
  printf '{"pid":%s,"sessionId":"%s","name":"%s","kind":"background","status":"%s","cwd":"%s","messagingSocketPath":"%s"}\n' \
    "$SOCK_PID" "$2" "$1" "$3" "$WORK" "$SOCK" > "$HOME/.claude/sessions/org-$1.json"
}
org_peer lead "$LEAD_UUID" busy
org_peer scout "$SCOUT_UUID" idle
org_peer scribe "$SCRIBE_UUID" busy
org_peer qa "$QA_UUID" waiting
"$SMINOS" seat add org lead --role LEAD --session "$LEAD_UUID" >/dev/null
"$SMINOS" seat add org scout --role RES --session "$SCOUT_UUID" >/dev/null
"$SMINOS" seat add org scribe --role DOC --session "$SCRIBE_UUID" >/dev/null
"$SMINOS" seat add org intern >/dev/null
"$SMINOS" seat add org qa --role QA --session "$QA_UUID" >/dev/null
"$SMINOS" seat add org old-worker >/dev/null
"$SMINOS" meta set org/old-worker status retired >/dev/null
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
ok = all(at_col(rows[r + k], L) == "│" and at_col(rows[r + k], R) == "│" for k in (1, 2, 3))
ok = ok and at_col(rows[r - 1], L) in "┌┏╭" and at_col(rows[r - 1], R) in "┐┓╮"
ok = ok and at_col(rows[r + 4], L) in "└┗╰" and at_col(rows[r + 4], R) in "┘┛╯"
print("aligned" if ok else "misaligned:\n" + "\n".join(rows[r - 1:r + 5]))
PY

run "$SMINOS" chart org --width 120
assert_rc 0 "$RC" "chart of a project exits 0"
CHART="$OUT"
assert_contains "$(printf '%s\n' "$CHART" | grep -c 'lead .*LEAD')" "1" "alias left and ROLE right share the first box line"
assert_contains "$CHART" "● busy" "busy member shows the filled glyph"
assert_contains "$CHART" "○ idle" "idle member (live peer) shows the hollow glyph"
assert_contains "$CHART" "◐ waiting" "waiting member shows the half glyph"
assert_contains "$CHART" "◌ vacant" "vacant seat shows the dotted glyph"
assert_not_contains "$CHART" "old-worker" "a retired seat is folded away by default"
assert_contains "$CHART" "notes → board" "a member's status is drawn on its third line"
assert_equals "$(printf '%s' "$CHART" | python3 -c 'import sys; print(any(c in sys.stdin.read() for c in "┬┼├┤┴"))')" "False" "no connector: the chart draws no tree"
assert_contains "$CHART" "6 members · 4 live · 1 hidden (sminos chart org --all)" "summary counts members, live, hidden and points at --all"
assert_equals "$(printf '%s\n' "$CHART" | python3 "$TEST_ROOT/boxcheck.py" scout)" "aligned" "a Korean status line keeps the box borders aligned"
assert_equals "$(printf '%s\n' "$CHART" | python3 "$TEST_ROOT/boxcheck.py" lead)" "aligned" "an ASCII box is aligned too"
assert_contains "$CHART" "…" "an over-long status line is truncated with an ellipsis"
# One column, newest join first: qa, scribe, scout, lead, then the vacant intern.
assert_equals "$(printf '%s\n' "$CHART" | python3 -c '
import sys
rows = sys.stdin.read().split("\n")
def at(m): return next((i, r.index(m)) for i, r in enumerate(rows) if m in r)
names = ("qa ", "scribe ", "scout ", "lead ", "intern ")
ys, xs = [at(n)[0] for n in names], {at(n)[1] for n in names}
print(ys == sorted(ys) and len(xs) == 1)')" "True" "members stand in one column, newest join first, the seats no member stands for last"
run "$SMINOS" chart org --all --width 120
assert_contains "$OUT" "old-worker" "--all shows the retired seat"
assert_not_contains "$OUT" "hidden" "--all summary has nothing hidden"
run "$SMINOS" chart --width 200
assert_rc 0 "$RC" "fleet chart exits 0"
assert_contains "$OUT" "╭" "fleet chart draws projects as rounded boxes"
assert_contains "$(printf '%s\n' "$OUT" | grep -c '│ org ')" "1" "the org project is a root box"
assert_contains "$OUT" "6 members · 4 live" "the project box counts its members and live members"
assert_contains "$OUT" "projects ·" "fleet summary counts projects"
run "$SMINOS" chart nope
assert_rc 4 "$RC" "chart of an unknown project exits 4"

# ---- 14) tui: the interactive chart, driven headlessly -----------------------
# `sminos tui --headless --keys …` runs the same state machine the curses screen
# runs, then prints the final grid, `--- focus: <id>`, and the actions it would
# have taken (attach) or did take (send, over the real launcher). Reuses the
# org fixture from section 13: one column of qa, scribe, scout, lead, intern;
# old-worker is folded away.
echo "tui:"
TUI="$SMINOS tui org --headless --width 110 --height 40"
run $TUI
assert_rc 0 "$RC" "headless tui exits 0"
assert_contains "$OUT" "--- focus: org/qa" "the first member is focused by default"
assert_contains "$OUT" "┏━━" "the focused box has heavy borders"
assert_contains "$OUT" "sminos · org · 6 members · 4 live · 1 hidden · a" "the header carries the counts and the hidden hint"
assert_contains "$OUT" "── detail ──" "the detail panel is shown by default"
assert_contains "$OUT" "org/qa · QA · seat cccc0004 · session cccc0004" "the detail panel names the focused member, role, seat and session"
assert_contains "$OUT" "◐ waiting · short cc000004 · updated" "the detail panel shows the state word and the short id, not the recorded status"
assert_contains "$OUT" "enter attach · s send · b chat" "the footer lists the keys"
run $TUI --keys down
assert_contains "$OUT" "--- focus: org/scribe" "down moves to the next box in the column"
run $TUI --keys "down,down,down,down,down,down"
assert_contains "$OUT" "--- focus: org/intern" "down past the last box stays put"
run $TUI --keys "down,down,up"
assert_contains "$OUT" "--- focus: org/scribe" "up moves back"
run $TUI --keys "down,right"
assert_contains "$OUT" "--- focus: org/scribe" "right on a member goes nowhere: there is no tree"
run $TUI --keys "down,down,home"
assert_contains "$OUT" "--- focus: org/qa" "home returns to the first box"
run $TUI --keys end
assert_contains "$OUT" "--- focus: org/intern" "end goes to the last"
run $TUI --keys "down,down,enter"
assert_contains "$OUT" "attach org/scout cc000002 → claude attach cc000002" "enter on a live seat records the attach against the qualified member and the harness short id"
assert_contains "$OUT" "would run: claude attach cc000002" "the footer flashes the attach command"
run $TUI --keys "end,enter"
assert_not_contains "$OUT" "attach org/intern" "enter on a vacant seat attaches nothing"
assert_contains "$OUT" "intern is vacant — no session to attach; sminos fill org/intern" "the footer explains the vacant seat and names the fill command"
run $TUI --keys "down,down,enter" --no-tmux
assert_contains "$OUT" "→ claude attach cc000002" "--no-tmux still records the plain attach command"
# Tall enough for all six boxes: the two vacant seats order by their
# whole-second `updated`, so which comes last is not fixed.
run "$SMINOS" tui org --headless --width 110 --height 60 --keys a
assert_contains "$OUT" "old-worker" "a shows the folded retired seat"
assert_contains "$OUT" "all shown · a" "the header notes that hidden members are shown"
run $TUI --keys "a,a"
assert_not_contains "$OUT" "old-worker" "a again hides it"
run $TUI --keys s
assert_contains "$OUT" "send → org/qa ▏" "s on a live member opens the send line naming the target"
run $TUI --keys "s,text:abc,backspace,text:d"
assert_contains "$OUT" "send → org/qa ▏abd" "typing and backspace edit the send line"
run $TUI --keys "s,text:abc,esc"
assert_not_contains "$OUT" "send → org/qa" "esc cancels the send line"
assert_contains "$OUT" "enter attach · s send" "and the footer shows the keys again"
run $TUI --keys "end,s"
assert_contains "$OUT" 'intern is vacant — nothing to send to; sminos fill org/intern "<task>" fills it' "s on a vacant seat refuses with the reason"
assert_not_contains "$OUT" "send →" "and opens no send line"
run $TUI --keys "down,down,s,text:ping-from-tui here,enter"
assert_contains "$OUT" "send scout ping-from-tui here → rc=0 sent to org/scout" "enter on the send line delivers through the real launcher and records the result"
assert_contains "$(tail -c 400 "$RECEIVED")" "[sminos message from human id=" "the frame reached the seat's inbox socket with the human sender line"
assert_contains "$(tail -c 400 "$RECEIVED")" "]\nping-from-tui here" "carrying the typed message"
run $TUI --keys b
assert_contains "$OUT" "── chat · org · " "b shows the focused member's project chat"
assert_contains "$OUT" "ping-from-tui here" "the project chat carries the send recorded a moment ago"
"$SMINOS" say --in org 'hello chat from the tui test' >/dev/null
run $TUI --keys b
assert_contains "$OUT" "testhost/human:" "chat panel lists the event id"
assert_contains "$OUT" "hello chat from the tui test" "chat panel shows the first line"
run $TUI --keys "b,tab"
assert_contains "$OUT" "↑↓ enter opens · tab back" "tab moves the keys into the chat list"
run $TUI --keys "b,tab,enter"
assert_contains "$OUT" " · human → * · " "enter opens the message overlay with sender, target and time"
assert_contains "$OUT" "hello chat from the tui test" "message overlay shows the text"
assert_contains "$OUT" "esc closes" "the overlay says how to close"
run $TUI --keys "b,tab,enter,esc"
assert_not_contains "$OUT" "esc closes" "esc closes the overlay"
# Every member of the project shows the one project chat.
run $TUI --keys "down,b"
assert_contains "$OUT" "chat · org · " "another member's panel shows the same project chat"
run $TUI --keys "end,b"
assert_contains "$OUT" "hello chat from the tui test" "so does a vacant seat's"
run $TUI --keys "b,tab,tab,down"
assert_contains "$OUT" "--- focus: org/scribe" "tab again hands the keys back to the chart"
run $TUI --keys "?"
assert_contains "$OUT" "┃ keys" "? opens the help overlay"
assert_contains "$OUT" "a — show / hide retired and gone members" "the help lists the keys"
assert_contains "$OUT" "■ stopped · ✕ gone · ◌ vacant · ⊘ retired" "the help's glyph line names all seven words"
run $TUI --keys "?,q,down"
assert_contains "$OUT" "--- focus: org/scribe" "q inside the overlay only closes it"
run $TUI --keys q
assert_contains "$OUT" "--- quit" "q quits"
run $TUI --keys r
assert_rc 0 "$RC" "r refreshes without error"
assert_contains "$OUT" "--- focus: org/qa" "and keeps the focus"
run "$SMINOS" tui org --headless --width 60 --height 14 --keys "end"
assert_rc 0 "$RC" "a 60x14 terminal renders"
assert_contains "$OUT" "┃ intern" "the viewport scrolls so the focused box is on screen"
assert_not_contains "$OUT" "── detail ──" "the panel collapses below 16 rows"
run "$SMINOS" tui --headless --width 120 --height 40
assert_rc 0 "$RC" "fleet tui exits 0"
assert_contains "$OUT" "sminos · fleet · " "the fleet header names the fleet"
assert_contains "$OUT" "members · " "the focused project box is on screen even when its members fill the top of the viewport"
run "$SMINOS" tui --headless --width 120 --height 160
assert_contains "$OUT" "╭" "unfocused projects are rounded boxes"
assert_equals "$(printf '%s\n' "$OUT" | sed -n 's/^--- focus: //p' | grep -c '/')" "0" "the default fleet focus is a project box"
run "$SMINOS" tui --headless --width 120 --height 40 --keys enter
assert_contains "$OUT" "▸ " "enter on a project collapses it"
# A `!` token in --keys is a DRIVER instruction, not a keystroke: it does what
# only the refresh thread does in a live screen. !focus moves the focus (a
# rebuild does that when the focused member disappears); !drop removes a box
# from the layout (a snapshot does that when a seat is retired mid-turn).
run $TUI --keys "down,down,s,text:bound,!focus:org/qa,enter"
assert_contains "$OUT" "send scout bound → rc=0 sent to org/scout" "a composed message goes to the member that was focused when the editor opened, not to wherever the focus moved"
assert_contains "$OUT" "--- focus: org/qa" "even though the focus did move"
run $TUI --keys "down,down,s,text:gone,!drop:org/scout,enter"
assert_contains "$OUT" "org/scout is no longer on the chart — nothing was sent" "a message is dropped, with a reason, when its target leaves the chart while it is being typed"
assert_equals "$(printf '%s\n' "$OUT" | sed -n '/^--- actions:/,$p' | tail -n +2 | wc -l | tr -d ' ')" "0" "and nothing is sent"
run $TUI --keys "s,text:x"
assert_contains "$OUT" "send → org/qa ▏x" "the send line names the captured target"

run "$SMINOS" tui nope --headless
assert_rc 4 "$RC" "tui of an unknown project exits 4"
run "$SMINOS" tui org
assert_rc 2 "$RC" "tui without a terminal exits 2"
assert_contains "$OUT" "sminos tui needs a terminal — for text use: sminos chart org" "and points at chart"
cd "$WORK"

fi # existing fleet tests; family-only runs skip to the focused section

# ---- the project chat ------------------------------------------------------------
# say and chat speak in the project the seats' cwd resolves to (fam-work, a
# .smns in $WORK); every seat there is a member, whoever spawned it, and a
# name resolves among them.
echo "project chat:"
export SMINOS_HOME="$TEST_ROOT/family-registry"
mkdir -p "$SMINOS_HOME" "$HOME/.claude/projects/fake-proj"
chmod 700 "$SMINOS_HOME"
touch "$RECEIVED"   # a family-only run starts before any frame has arrived
rm -f "$HOME/.claude/sessions/"*.json
cd "$WORK"
git -c init.defaultBranch=main init -q "$WORK"
"$SMINOS" project init --name fam-work >/dev/null
FAMP="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["project"])' "$WORK/.smns")"
FAMLOG="$SMINOS_HOME/projects/$FAMP/log"
recv_size() { wc -c < "$RECEIVED" | tr -d ' '; }
run "$SMINOS" spawn root-alone 'ROOT-TASK'
assert_rc 0 "$RC" "a seat spawns into the project"
ROOT_ID="$(banner_uuid "$OUT")"
assert_contains "$(field "$ROOT_ID" task)" 'You are seat "root-alone" in sminos group "fam-work", the root of your' "every spawn renders the preamble, naming the project"
assert_not_contains "$(field "$ROOT_ID" task)" '"none"' "the preamble never invents a none host"
assert_not_contains "$(field "$ROOT_ID" task)" '{{' "and leaves no placeholder"
assert_contains "$(field "$ROOT_ID" task)" 'Tags address only at the start of a message; an @ later' "the preamble teaches that only leading tags address"
export CLAUDE_CODE_SESSION_ID="$ROOT_ID"
run "$SMINOS" chat -n 30
assert_rc 0 "$RC" "a seat alone in its project reads the chat as the preamble says"
assert_contains "$OUT" 'chat fam-work' "the chat is the project's"
run "$SMINOS" chat
assert_contains "$OUT" '(no new messages)' "with nothing unread"
run "$SMINOS" chat --team
assert_rc 2 "$RC" "chat --team is gone with the per-host chats"
run "$SMINOS" say 'not yet'
assert_rc 0 "$RC" "a seat alone in its project still records"
assert_contains "$(cat "$FAMLOG/testhost.$ROOT_ID.jsonl")" '"text": "not yet"' "into its own writer file"
unset CLAUDE_CODE_SESSION_ID
"$SMINOS" remove work/root-alone >/dev/null
run "$SMINOS" seat add fam lead --session 11111111-aaaa-4000-8000-000000000001
LEAD=11111111-aaaa-4000-8000-000000000001
run "$SMINOS" seat add fam a --session 22222222-aaaa-4000-8000-000000000002
A=22222222-aaaa-4000-8000-000000000002
run "$SMINOS" seat add fam b --session 33333333-aaaa-4000-8000-000000000003
B=33333333-aaaa-4000-8000-000000000003
run "$SMINOS" seat add other x --session 44444444-aaaa-4000-8000-000000000004
# A bare alias outranks id prefixes: `a` is also a hex prefix of another seat's id.
run "$SMINOS" seat add other hexa --session aaaaaaab-aaaa-4000-8000-0000000000ab
assert_rc 0 "$RC" "a seat whose id starts with the alias a is added"
run "$SMINOS" meta get a group
assert_rc 0 "$RC" "a bare alias resolves beside a seat-id prefix match"
assert_equals "$OUT" fam "meta get a reads the aliased seat, not the id-prefix match"
run "$SMINOS" status a 'alias check'
assert_contains "$OUT" 'fam/a now: alias check' "status a resolves the alias before a seat-id prefix"
"$SMINOS" status a >/dev/null
run "$SMINOS" meta get aaaaaaab group
assert_rc 4 "$RC" "a seat-id prefix does not resolve even when no alias matches"
run "$SMINOS" meta get aaaaaaab-aaaa-4000-8000-0000000000ab group
assert_equals "$OUT" other "the full seat id resolves"
"$SMINOS" remove other/hexa >/dev/null
printf '{"pid":%s,"sessionId":"%s","name":"lead","status":"idle","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$LEAD" "$SOCK" > "$HOME/.claude/sessions/lead.json"
printf 'short=bbbb0003\nuuid=%s\nname=b\nstate=stopped\nstatus=\ncwd=%s\n' "$B" "$WORK" > "$STUB_STATE/agents/bbbb0003"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/fake-proj/$B.jsonl"   # stopped, not gone: its transcript is here
export CLAUDE_CODE_SESSION_ID="$A"
BEFORE_RECV="$(recv_size)"
run "$SMINOS" say 'schema done'
assert_rc 0 "$RC" "an untagged report records"
assert_not_contains "$OUT" 'lead:' "an untagged message pushes to no one, the host included"
assert_equals "$(recv_size)" "$BEFORE_RECV" "nothing reaches an inbox"
A_LOG="$FAMLOG/testhost.$A.jsonl"
assert_equals "$(mode_of "$A_LOG")" 0600 "a writer file is private"
assert_contains "$(cat "$A_LOG")" '"from": "a", "to": "*", "text": "schema done"' "an untagged report is a say to *"
run env -u CLAUDE_CODE_SESSION_ID "$SMINOS" tui fam-work --headless --keys "b,tab,enter"
assert_contains "$OUT" " · a → * · " "chat overlay names the target of an untagged message"
run env -u CLAUDE_CODE_SESSION_ID "$SMINOS" tui --all --headless --keys "!focus:fam-work,b"
assert_contains "$OUT" "chat · fam-work · " "a project box selects its own chat"
run env -u CLAUDE_CODE_SESSION_ID "$SMINOS" tui --headless --keys "!focus:nothing,b"
assert_contains "$OUT" "chat · - · 0 messages" "no focused box selects no chat"
run "$SMINOS" say '@b your migration renames my column'
assert_rc 0 "$RC" "tag to a stopped member is recorded"
assert_contains "$OUT" 'b: woken' "tag resumes a stopped member"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "--bg --resume $B" "resume uses saved session"
run "$SMINOS" say '@all standup'
assert_rc 0 "$RC" "broadcast is recorded"
assert_contains "$OUT" 'lead: sent' "@all reaches a live member"
assert_not_contains "$OUT" 'b:' "a stopped member is not in the @all audience"
assert_equals "$(python3 -c 'import json,sys; s = [json.loads(x)["seq"] for x in open(sys.argv[1])]; print(s == list(range(1, len(s) + 1)))' "$A_LOG")" 'True' "a writer's seq increases, its lifecycle and its messages in one sequence"
last_seq() { tail -1 "$1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["seq"])'; }
# A live socket for b makes a later tag push.
printf '{"pid":%s,"sessionId":"%s","name":"b","status":"idle","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$B" "$SOCK" > "$HOME/.claude/sessions/b.json"
export CLAUDE_CODE_SESSION_ID="$LEAD"
run "$SMINOS" say '@b merge b first'
assert_rc 0 "$RC" "a member tags another"
assert_contains "$OUT" 'b: sent' "a tag reaches a live member"
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" say '@b check again'
assert_rc 0 "$RC" "a tagged message delivers"
assert_contains "$(cat "$RECEIVED")" "[sminos chat fam-work ${A:0:8}:$(last_seq "$A_LOG") from a \u2192 @you | unread 5]" "unread counts what the reader has not read, the pushed message aside"
export CLAUDE_CODE_SESSION_ID="$B"
run "$SMINOS" chat
assert_contains "$OUT" 'chat fam-work · 6 new' "chat reads what is above the cursor"
assert_contains "$OUT" '→ @b' "tagged chat entry marks its recipient"
assert_contains "$(cat "$SMINOS_HOME/projects/$FAMP/cursors/$B.json")" "\"testhost/$A\": $(last_seq "$A_LOG")" "chat read advances the cursor"
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" say '@b final'
assert_contains "$(cat "$RECEIVED")" "[sminos chat fam-work ${A:0:8}:$(last_seq "$A_LOG") from a \u2192 @you]" "the message after a read is pushed with no unread count"
# Tags address only at the start of a message; an @ later in the text is text.
run "$SMINOS" say 'report: the @x attempt failed'
assert_rc 0 "$RC" "an @ inside the text is not refused"
assert_not_contains "$OUT" 'x:' "an @ inside the text addresses no one"
assert_contains "$(tail -1 "$A_LOG")" '"to": "*"' "a report quoting an alias is recorded to *"
run "$SMINOS" say 'tell @all'
assert_rc 0 "$RC" "an @all inside the text is not refused"
assert_contains "$(tail -1 "$A_LOG")" '"to": "*"' "an @all inside the text is not a broadcast"
assert_not_contains "$(tail -1 "$A_LOG")" '"wake"' "and wakes no one"
run "$SMINOS" say '@b hi'
assert_contains "$(tail -1 "$A_LOG")" "\"session\": \"$B\", \"alias\": \"b\"" "a leading tag addresses its recipient by session"
printf '{"pid":%s,"sessionId":"%s","name":"a","status":"idle","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$A" "$SOCK" > "$HOME/.claude/sessions/a.json"
export CLAUDE_CODE_SESSION_ID="$LEAD"
run "$SMINOS" say '@a, @b: go'
assert_rc 0 "$RC" "a leading tag run with punctuation delivers"
assert_contains "$(tail -1 "$FAMLOG/testhost.$LEAD.jsonl")" '"alias": "a"' "tags separated by , and : both address"
assert_contains "$(tail -1 "$FAMLOG/testhost.$LEAD.jsonl")" '"alias": "b"' "the second of them too"
rm -f "$HOME/.claude/sessions/a.json"
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "lead"' "a member lists the project"
assert_contains "$OUT" '"alias": "x"' "every member of it, whichever group its seat is in"
run "$SMINOS" send other/x hi
assert_rc 4 "$RC" "a send to a gone seat of the project is refused as gone, not as outside a family"
assert_contains "$OUT" 'is gone' "naming why"
run "$SMINOS" say '@x hi'
assert_rc 0 "$RC" "the project is a tag's reach: a seat of another group in the project is addressed"
assert_contains "$OUT" 'x: recorded' "and recorded for it (no session of its runs here)"
run "$SMINOS" say '@all @b hi'
assert_rc 2 "$RC" "all cannot mix with tags"
run "$SMINOS" say '@a hi'
assert_rc 2 "$RC" "self-tag refused"
run "$SMINOS" say --team '@lead hi'
assert_rc 2 "$RC" "say --team is gone with the per-host chats"
run "$SMINOS" say --in lead hi
assert_rc 2 "$RC" "--in is the operator's, not a session's"
unset CLAUDE_CODE_SESSION_ID
CLAUDE_CODE_SESSION_ID=55555555-aaaa-4000-8000-000000000005 run "$SMINOS" seat add fam interactive --session 55555555-aaaa-4000-8000-000000000005
assert_rc 0 "$RC" "a session registers itself as a seat through seat add"
"$SMINOS" remove fam/interactive >/dev/null
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" spawn c t --worktree c
assert_rc 0 "$RC" "a member spawns a sibling"
C="$(seat_id_of c)"
assert_equals "$(field "$C" parent)" "" "a sibling records no parent"
assert_equals "$(field "$C" group)" work "its group derives from its cwd, not from its spawner"
assert_contains "$(field "$C" task)" "$SMINOS chat -n 30" "its preamble begins with the chat instruction"
# A member's own messages are never its unread: a's note is not counted in the
# frame a receives for the report of the seat it spawned.
printf '{"pid":%s,"sessionId":"%s","name":"a","status":"idle","messagingSocketPath":"%s"}\n' "$SOCK_PID" "$A" "$SOCK" > "$HOME/.claude/sessions/a.json"
"$SMINOS" chat >/dev/null
run "$SMINOS" say 'a note of my own'
assert_rc 0 "$RC" "the spawner speaks in the project"
CHILD_SESSION="$(field "$C" current)"
export CLAUDE_CODE_SESSION_ID="$CHILD_SESSION"
run "$SMINOS" say '@a c reporting'
assert_rc 0 "$RC" "the spawned seat reports to its spawner by tag"
assert_contains "$OUT" 'a: sent' "the report reaches the live spawner"
assert_contains "$(cat "$RECEIVED")" "[sminos chat fam-work ${CHILD_SESSION:0:8}:$(last_seq "$FAMLOG/testhost.$CHILD_SESSION.jsonl") from c \u2192 @you]" "the spawner receives it, its own note not counted unread"
rm -f "$HOME/.claude/sessions/a.json"
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" say '@c @lead cross'
assert_rc 0 "$RC" "two tags in one project are one message"
assert_contains "$OUT" 'c:' "reaching the one"
assert_contains "$OUT" 'lead:' "and the other"
run "$SMINOS" chat
assert_rc 0 "$RC" "a member reads the project chat"
run "$SMINOS" chat --team
assert_rc 2 "$RC" "chat --team is gone"
assert_file_exists "$SMINOS_HOME/projects/$FAMP/cursors/$A.json" "a member's cursor is its own file"
unset CLAUDE_CODE_SESSION_ID
run "$SMINOS" say hi
assert_rc 0 "$RC" "the operator says in the working directory's project"
assert_contains "$(tail -1 "$FAMLOG/testhost.human.jsonl")" '"kind": "human", "from": "human", "to": "*", "text": "hi"' "as human to *"
run "$SMINOS" chat
assert_rc 0 "$RC" "the operator reads the working directory's project chat"
run "$SMINOS" say --in fam-work 'hello team'
assert_rc 0 "$RC" "operator speaks as human into a named project"
assert_contains "$(tail -1 "$FAMLOG/testhost.human.jsonl")" '"from": "human"' "operator identity recorded"
HELLO_TS="$(tail -1 "$FAMLOG/testhost.human.jsonl" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ts"])')"
run "$SMINOS" say '@all operator broadcast'
assert_rc 0 "$RC" "operator can broadcast to the project"
assert_contains "$(tail -1 "$FAMLOG/testhost.human.jsonl")" '"wake": true' "an operator @all is recorded with wake"
run "$SMINOS" chat --since "$HELLO_TS" --json
assert_rc 0 "$RC" "operator can read selected messages as JSONL"
assert_contains "$OUT" '"text": "@all operator broadcast"' "JSONL since prints messages from that time"
assert_not_contains "$OUT" 'schema done' "since skips earlier messages"
run "$SMINOS" retire fam/lead --cascade
assert_rc 2 "$RC" "retire --cascade left with the tree"
assert_not_contains "$(field "$LEAD" status)" retired "and the refused retire touches nothing"
# A spawner is provenance, not a host: retiring it leaves what it spawned.
run "$SMINOS" retire fam/a
assert_rc 0 "$RC" "the spawner retires"
assert_not_contains "$(field "$C" status)" retired "the seat it spawned is not retired with it"
SPAWNED="$(python3 - "$REPO_ROOT/skills/sminos/scripts/sminos.py" "$FAMP" "$C" <<'PY_SPAWNED'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
ms = {m.session: m for m in mod.members(mod.find_project(sys.argv[2]))}
cur = mod.reload_seat(sys.argv[3])["current"]
print(ms[cur].by if cur in ms else "-", cur in ms)
PY_SPAWNED
)"
assert_equals "$SPAWNED" "a True" "and stays a member, its spawner kept as provenance"
"$SMINOS" fill fam/a "back" --resume >/dev/null
rm -f "$HOME/.claude/sessions/b.json"
printf 'short=bbbb0003\nuuid=%s\nname=b\nstate=stopped\nstatus=\ncwd=%s\n' "$B" "$WORK" > "$STUB_STATE/agents/bbbb0003"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/fake-proj/$B.jsonl"   # stopped, not gone: its transcript is here
export CLAUDE_CODE_SESSION_ID="$A"
run "$SMINOS" spawn c 'restore the seat'
assert_rc 0 "$RC" "a member re-fills a stopped seat of the project"
assert_equals "$(field "$C" parent)" "" "the re-filled seat records no parent"
unset CLAUDE_CODE_SESSION_ID
run "$SMINOS" seat add fam all
assert_rc 2 "$RC" "all alias is reserved"
# Board pipeline workers are seats like any other: they list, spawn, and resume.
run "$SMINOS" spawn pipeline-root t
PIPE="$(seat_id_of pipeline-root)"
CLAUDE_CODE_SESSION_ID="$(field "$PIPE" current)"
export CLAUDE_CODE_SESSION_ID
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "x"' "a pipeline worker lists the project"
run "$SMINOS" spawn pipeline-child t
assert_rc 0 "$RC" "a pipeline worker spawns"
assert_equals "$(field "$(seat_id_of pipeline-child)" parent)" '' "what it spawns records no parent"
run "$SMINOS" resume other/x 'pipeline resume'
assert_rc 0 "$RC" "a pipeline worker can resume another seat"
unset CLAUDE_CODE_SESSION_ID
# A blocked row with no process must reconcile even if the record was already idle.
run "$SMINOS" seat add fam blocked-one --session 55555555-aaaa-4000-8000-000000000005
BLOCK=55555555-aaaa-4000-8000-000000000005
printf 'short=abcde012\nuuid=%s\nname=blocked-one\nstate=blocked\nstatus=\n' "$BLOCK" > "$STUB_STATE/agents/abcde012"
run "$SMINOS" list --state gone
assert_contains "$OUT" 'blocked-one' "a blocked row with no peer and no transcript here reads gone"
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
run "$SMINOS" seat add fam d1 --session 77777777-aaaa-4000-8000-000000000007
D1=77777777-aaaa-4000-8000-000000000007
run "$SMINOS" seat add fam d2 --session 88888888-aaaa-4000-8000-000000000008
D2=88888888-aaaa-4000-8000-000000000008
printf 'short=dddd0001\nuuid=%s\nname=d1\nstate=stopped\n' "$D1" > "$STUB_STATE/agents/dddd0001"
printf 'short=dddd0002\nuuid=%s\nname=d2\nstate=stopped\n' "$D2" > "$STUB_STATE/agents/dddd0002"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/fake-proj/$D1.jsonl"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/fake-proj/$D2.jsonl"
python3 - "$SMINOS_HOME/$D1.json" "$SMINOS_HOME/$D2.json" "$WORK" <<'PY_FIX_CWD'
import json, sys
for path, cwd in ((sys.argv[1], sys.argv[3] + '/no-such-sminos-cwd'), (sys.argv[2], sys.argv[3])):
    d = json.load(open(path)); d['cwd'] = cwd
    with open(path, 'w') as f: json.dump(d, f)
PY_FIX_CWD
export CLAUDE_CODE_SESSION_ID="$DUO"
python3 - "$(lock_file d1)" "$TEST_ROOT/d1-lock-ready" <<'PY_D1_LOCK' & d1_holder=$!
import fcntl,pathlib,sys,time
with open(sys.argv[1], 'a') as f:
    fcntl.flock(f,fcntl.LOCK_EX)
    pathlib.Path(sys.argv[2]).touch()
    time.sleep(.7)
PY_D1_LOCK
for _ in $(seq 1 50); do [ -f "$TEST_ROOT/d1-lock-ready" ] && break; sleep .02; done
run "$SMINOS" say '@d1 @d2 lock contention'
wait "$d1_holder"
assert_rc 0 "$RC" "one busy lifecycle lock does not abort sibling fan-out"
assert_contains "$OUT" 'd1: failed:' "busy lifecycle lock is recorded per member"
assert_contains "$OUT" 'd2: woken' "later member still resumes after lock contention"
run "$SMINOS" say '@d1 @d2 please respond'
assert_rc 0 "$RC" "one refused resume does not abort the fan-out"
assert_contains "$OUT" 'd1: pending behind an earlier undelivered message (failed:' "a failed earlier message holds the later one back"
assert_contains "$OUT" 'd2: woken' "the later tagged member resumes"
assert_contains "$(cat "$SMINOS_HOME/projects/$FAMP/delivered/$D2.json")" "\"testhost/$DUO\": {\"settled\": $(last_seq "$FAMLOG/testhost.$DUO.jsonl")" "fan-out settles the successful member"
assert_contains "$(cat "$SMINOS_HOME/projects/$FAMP/delivered/$D1.json")" "\"pending\": $(( $(last_seq "$FAMLOG/testhost.$DUO.jsonl") - 1 )), \"attempts\": 2" "and keeps the failed one pending with its attempts"
unset CLAUDE_CODE_SESSION_ID
# A tagged member with no transcript on this machine (and no process) is gone: a
# resume cannot work, so none is attempted — the message is recorded, the
# sender is told to fill it, and the live member still gets the message.
D4=4d4d4d4d-aaaa-4000-8000-0000000000d4
"$SMINOS" seat add fam d4 --session "$D4" >/dev/null
"$SMINOS" meta set fam/d4 cwd "$WORK" >/dev/null
printf '{"pid":%s,"sessionId":"%s","name":"d2","kind":"background","status":"idle","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$D2" "$SOCK" > "$HOME/.claude/sessions/fam-d2.json"
: > "$STUB_STATE/log/calls.log"
CLAUDE_CODE_SESSION_ID="$DUO" run "$SMINOS" say '@d4 @d2 anyone there'
assert_rc 0 "$RC" "a tagged gone member does not abort the chat"
assert_contains "$OUT" 'd4: recorded' "a tagged gone member's message is recorded"
assert_contains "$OUT" 'd4 is gone — no transcript for its session on this machine; fill it to reach it' "and the sender is told to fill it"
assert_not_contains "$(cat "$STUB_STATE/log/calls.log")" "--resume $D4" "no resume of a gone member is attempted"
assert_contains "$OUT" 'd2: sent' "and the fan-out still reaches the live member"
rm -f "$HOME/.claude/sessions/fam-d2.json"
"$SMINOS" remove fam/d4 >/dev/null
run "$SMINOS" seat add fam d3 --session 99999999-aaaa-4000-8000-000000000009
export CLAUDE_CODE_SESSION_ID="$D1"
D3=99999999-aaaa-4000-8000-000000000009
printf 'short=dddd0003\nuuid=%s\nname=d3\nstate=stopped\n' "$D3" > "$STUB_STATE/agents/dddd0003"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/fake-proj/$D3.jsonl"
python3 - "$SMINOS_HOME/$D3.json" "$WORK" <<'PY_FIX_CWD2'
import json, sys
p=sys.argv[1]; d=json.load(open(p)); d['cwd']=sys.argv[2]
with open(p, 'w') as f: json.dump(d, f)
PY_FIX_CWD2
STUB_NO_UUID=1 run "$SMINOS" say '@d3 check'
assert_rc 0 "$RC" "unconfirmed resume does not erase message"
assert_contains "$OUT" 'd3: woken?' "unconfirmed uuid is reported as uncertain wake"
assert_contains "$(cat "$SMINOS_HOME/projects/$FAMP/delivered/$D3.json")" "\"testhost/$D1\": {\"settled\": $(last_seq "$FAMLOG/testhost.$D1.jsonl")" "an uncertain wake is settled, never re-sent"
assert_contains "$(field "$D3" pending_short)" 'dddd0003' "unconfirmed resume keeps recovery short"
unset CLAUDE_CODE_SESSION_ID
run "$SMINOS" seat add fam solo --session aaaaaaaa-aaaa-4000-8000-00000000000a
export CLAUDE_CODE_SESSION_ID=aaaaaaaa-aaaa-4000-8000-00000000000a
run "$SMINOS" say 'on my own'
assert_rc 0 "$RC" "a seat that spawned nothing and was spawned by no one speaks in its project"
run "$SMINOS" chart fam-work
assert_rc 0 "$RC" "a member reads the chart: it is the project, not an operator view"
run "$SMINOS" tui fam-work --headless
assert_rc 0 "$RC" "and the tui"
unset CLAUDE_CODE_SESSION_ID
# Malformed and torn lines, and concurrent appends, are pinned in "projects
# and the log" below, on the writer files that replaced the per-host chats.
# The startup window: no current, harness row matches provisional short.
run "$SMINOS" seat add fam starter --session aaaaaaaa-bbbb-4000-8000-00000000000a
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
assert_rc 0 "$RC" "provisional caller reads its project chat"
assert_contains "$OUT" 'chat fam-work' "provisional caller finds its project by its record"
run "$SMINOS" say 'starting'
assert_rc 0 "$RC" "provisional caller records a report"
assert_contains "$(tail -1 "$FAMLOG/testhost.$START.jsonl")" '"from": "starter"' "startup report has seat identity"
assert_file_absent "$SMINOS_HOME/$START.json" "startup chat read does not create promoted record"
# A provisional caller spawns without waiting for its promotion: there is no
# tree to key, and its spawn is recorded under the seat's alias.
run "$SMINOS" spawn starter-child t
assert_rc 0 "$RC" "a provisional caller spawns"
assert_contains "$(head -1 "$FAMLOG/testhost.$(field "$(seat_id_of starter-child)" current).jsonl")" '"by": "starter"' "recording the seat it is as the spawner"
python3 - "$SMINOS_HOME/$PROVISIONAL.json" "$SMINOS_HOME/$START.json" "$WORK" <<'PY_PROMOTE'
import json,os,sys
d=json.load(open(sys.argv[1])); d['current']='aaaaaaaa-bbbb-4000-8000-00000000000a'
d['short']='aaaa000a'; d['cwd']=sys.argv[3]
with open(sys.argv[2], 'w') as f: json.dump(d,f)
os.unlink(sys.argv[1])
PY_PROMOTE
BEFORE_GEN="$(field "$START" gen)"
run "$SMINOS" chat
assert_equals "$(field "$START" gen)" "$BEFORE_GEN" "chat read does not invalidate lifecycle watcher"
assert_file_exists "$SMINOS_HOME/projects/$FAMP/cursors/$START.json" "a cursor is keyed by session, so a promotion cannot strand it"
unset CLAUDE_CODE_SESSION_ID

# A delivery record is replaced atomically: a kill just before replace leaves all old bytes.
BEFORE_REC="$(cat "$SMINOS_HOME/projects/$FAMP/delivered/$D2.json")"
RESULT="$(python3 - "$REPO_ROOT/skills/sminos/scripts/sminos.py" "$FAMP" "$D2" <<'PY_ATOMIC'
import subprocess, sys
script = '''import importlib.util, os, signal, sys
spec=importlib.util.spec_from_file_location("sminos",sys.argv[1]); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
def interrupt(*args): os.kill(os.getpid(), signal.SIGKILL)
p = mod.find_project(sys.argv[2])
mod.os.replace=interrupt
mod.delivered_fail(p, sys.argv[3], "testhost/someone", 1)'''
p=subprocess.run([sys.executable, '-c', script, *sys.argv[1:]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(p.returncode)
PY_ATOMIC
)"
assert_equals "$RESULT" '-9' "the record writer was killed before replacement"
assert_equals "$(cat "$SMINOS_HOME/projects/$FAMP/delivered/$D2.json")" "$BEFORE_REC" "a killed write preserves the whole delivery record"
# A member retired while an earlier member's push ran is not resumed from a stale snapshot.
run "$SMINOS" seat add fam stale --session eeeeeeee-aaaa-4000-8000-00000000000e
STALE=eeeeeeee-aaaa-4000-8000-00000000000e
printf 'short=eeee000e\nuuid=%s\nname=stale\nstate=stopped\ncwd=%s\n' "$STALE" "$WORK" > "$STUB_STATE/agents/eeee000e"
"$SMINOS" meta set fam/stale cwd "$WORK" >/dev/null
run "$SMINOS" retire fam/stale
PUSHED="$(python3 - "$REPO_ROOT/skills/sminos/scripts/sminos.py" "$STALE" 2>&1 <<'PY_STALE'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
seat = {**mod.reload_seat(sys.argv[2]), "status": "idle"}   # the fan-out snapshot, stale
member = mod.Member(session=seat["current"], short=seat["current"][:8], alias=seat["alias"], name_source="seat",
                    machine="testhost", local=True, state="stopped", state_age=None, charge="", charge_source="",
                    status="", by="", worktree="", seat=seat)
print(mod.push_member(member, "[sminos chat fam-work testhost/human:99 from human \u2192 @you]\nhi", True))
PY_STALE
)"
assert_contains "$PUSHED" 'recorded' "a push decides retirement on the reloaded record"
assert_contains "$PUSHED" 'is retired; re-fill it to reach it' "a tagged retired member still warns"
assert_not_contains "$(cat "$STUB_STATE/log/calls.log")" "--resume $STALE" "a retired member is never resumed"
assert_equals "$(field "$STALE" status)" retired "a stale push leaves the member retired"
"$SMINOS" remove fam/stale >/dev/null
rm -f "$STUB_STATE/agents/eeee000e"
# A long-held flock is not a timed lease: no second writer overtakes it at 30 s.
if [[ "${SMINOS_FAMILY_ONLY:-0}" != 1 ]]; then
  python3 - "$FAMLOG/testhost.human.jsonl.lock" "$TEST_ROOT/lock-ready" <<'PY_LOCK_HOLDER' & holder=$!
import fcntl, pathlib, sys, time
with open(sys.argv[1], 'a') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    pathlib.Path(sys.argv[2]).touch()
    time.sleep(31)
PY_LOCK_HOLDER
  for _ in $(seq 1 100); do [ -f "$TEST_ROOT/lock-ready" ] && break; sleep .05; done
  "$SMINOS" say --in fam-work 'wait behind lock' > "$TEST_ROOT/waited-say.log" & waiter=$!
  sleep 30.25
  assert_not_contains "$(cat "$FAMLOG/testhost.human.jsonl")" 'wait behind lock' "writer held beyond thirty seconds is not overtaken"
  wait "$holder"; wait "$waiter"
  assert_contains "$(cat "$FAMLOG/testhost.human.jsonl")" 'wait behind lock' "waiting writer records after flock releases"
fi


run "$SMINOS" retire fam/duo --purge
assert_rc 0 "$RC" "retire --purge succeeds"
assert_file_absent "$SMINOS_HOME/$DUO.json" "and purges the one seat named"
assert_file_exists "$SMINOS_HOME/$D1.json" "nothing else: there is no tree to cascade through"
assert_contains "$(tail -1 "$FAMLOG/testhost.$DUO.jsonl")" '"kind": "retired"' "a purge records the session retired"


run "$SMINOS" seat add fam legacy --session dddddddd-aaaa-4000-8000-00000000000d
"$SMINOS" meta set fam/legacy engine codex >/dev/null
"$SMINOS" list >/dev/null 2>&1  # migrate retires the legacy record once
run "$SMINOS" resume fam/legacy 'try legacy'
assert_rc 4 "$RC" "resume refuses legacy codex seat"
assert_contains "$OUT" 'its resume path was retired — retire or remove the seat' "resume keeps actionable legacy codex refusal"
python3 - "$FAMLOG/h0.human.jsonl" <<'PY_HISTORY'
import json, sys
with open(sys.argv[1], 'w') as f:
    for n in range(1, 36):
        f.write(json.dumps({'ts': '2099-01-01T00:00:%02d.000Z' % n, 'writer': 'h0/human', 'seq': n, 'kind': 'human',
                            'from': 'human', 'to': '*', 'text': 'entry %d' % n}) + '\n')
PY_HISTORY
run "$SMINOS" chat
assert_equals "$(printf '%s\n' "$OUT" | grep -c 'entry ')" 30 "an unread chat prints at most thirty messages"
assert_contains "$OUT" "entry 35" "the newest of them"
assert_contains "$OUT" "earlier — sminos chat fam-work -n" "and says how to read the earlier ones"
run "$SMINOS" chat -n 35 --json
assert_equals "$(printf '%s\n' "$OUT" | grep -c '"text": "entry ')" 35 "chat -n reaches back past the unread window"
assert_contains "$OUT" '"text": "entry 1"' "to the earliest message"

# ---- projects and the log -----------------------------------------------------
# A project is named by a committed .smns, or by its owning repository; what
# crosses sessions is an event in the project's append-only log, one file per
# writer, and delivery is the deliverer's own record (spec 2026-10-13, M1).
echo "projects and the log:"
export SMINOS_HOME="$TEST_ROOT/project-registry"
mkdir -m 700 "$SMINOS_HOME"
rm -f "$HOME/.claude/sessions/"*.json
unset CLAUDE_CODE_SESSION_ID
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }
# Each member gets an inbox of its own, so a test can tell who received what.
start_inbox() { # name
  python3 "$TEST_ROOT/sockserver.py" "$TEST_ROOT/in-$1.sock" "$TEST_ROOT/in-$1.received" &
  EXTRA_PIDS+=("$!"); disown "$!"
  for _ in $(seq 1 50); do [ -S "$TEST_ROOT/in-$1.sock" ] && break; sleep 0.05; done
  : > "$TEST_ROOT/in-$1.received"
}
live_peer() { # name session status
  printf '{"pid":%s,"sessionId":"%s","name":"%s","status":"%s","messagingSocketPath":"%s"}\n' \
    "$SOCK_PID" "$2" "$1" "$3" "$TEST_ROOT/in-$1.sock" > "$HOME/.claude/sessions/pl-$1.json"
}
inbox() { cat "$TEST_ROOT/in-$1.received"; }
frames() { # name → each frame the inbox received, decoded, newlines shown as " / "
  python3 -c 'import json, sys
for l in open(sys.argv[1]):
    if l.strip():
        print(json.loads(l)["message"]["content"].replace("\n", " / "))' "$TEST_ROOT/in-$1.received" 2>/dev/null || true
}
bodies() { # name → each received frame's text below its header line, one frame a line
  python3 -c 'import json, sys
for l in open(sys.argv[1]):
    if l.strip():
        print(json.loads(l)["message"]["content"].split("\n", 1)[-1])' "$TEST_ROOT/in-$1.received" 2>/dev/null || true
}
run_in() { # dir cmd... — run, from another directory
  local dir="$1"; shift
  set +e; OUT="$(cd "$dir" && "$@" 2>&1)"; RC=$?; set -e
}
smns_id() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["project"])' "$1/.smns"; }
log_of() { cat "$SMINOS_HOME/projects/$1/log/"*.jsonl 2>/dev/null || true; }
SMINOS_PY="$REPO_ROOT/skills/sminos/scripts/sminos.py"

# Resolution: a .smns names the project; a git repository without one is a
# local project named after its owning repository; anything else is none.
PR="$TEST_ROOT/demo-repo"
mkdir -p "$PR"
gitq init -q "$PR"
cd "$PR"
run "$SMINOS" project show
assert_rc 0 "$RC" "project show resolves a plain git repository"
assert_contains "$OUT" "local-demo-repo" "a repository without .smns is the local project named after it"
mkdir -p "$TEST_ROOT/nowhere"
run "$SMINOS" project show "$TEST_ROOT/nowhere"
assert_rc 4 "$RC" "a directory in no repository and under no .smns is no project"
assert_contains "$OUT" "no project" "and says so"
run "$SMINOS" project init --name demo
assert_rc 0 "$RC" "project init writes .smns"
assert_file_exists "$PR/.smns" "the .smns lands at the repository root"
DEMO="$(smns_id "$PR")"
assert_equals "$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["name"], repr(d["remote"]))' "$PR/.smns")" "demo ''" ".smns carries the name and an empty remote"
run "$SMINOS" project init --name again
assert_rc 2 "$RC" "a second init refuses to replace the project id"
mkdir -p "$PR/deep/er"
run "$SMINOS" project show "$PR/deep/er"
assert_contains "$OUT" "$DEMO" "a subdirectory resolves to the .smns above it"
assert_contains "$OUT" "demo" "with its name"
gitq -C "$PR" add .smns
gitq -C "$PR" commit -qm smns
LR="$TEST_ROOT/plain-repo"
mkdir -p "$LR"
gitq init -q "$LR"
gitq -C "$LR" commit -q --allow-empty -m root
gitq -C "$LR" worktree add -q "$LR/.claude/worktrees/w1" -b w1
run "$SMINOS" project show "$LR/.claude/worktrees/w1"
assert_contains "$OUT" "local-plain-repo" "a linked worktree without .smns resolves to its owning repository"
gitq -C "$PR" worktree add -q "$PR/.claude/worktrees/w2" -b w2
run "$SMINOS" project show "$PR/.claude/worktrees/w2"
assert_contains "$OUT" "$DEMO" "a linked worktree carries the project by checkout"
BROKEN="$TEST_ROOT/broken-repo"
mkdir -p "$BROKEN"
gitq init -q "$BROKEN"
printf 'not json' > "$BROKEN/.smns"
run "$SMINOS" project show "$BROKEN"
assert_rc 0 "$RC" "a broken .smns is not fatal"
assert_contains "$OUT" "ignoring unreadable $BROKEN/.smns" "it is named"
assert_contains "$OUT" "local-broken-repo" "and skipped for the repository's local project"

# Members in M1 are seat records whose cwd resolves to the project.
SA=a0000001-0000-4000-8000-0000000000a1
SB=b0000002-0000-4000-8000-0000000000b2
SC=c0000003-0000-4000-8000-0000000000c3
SD=d0000004-0000-4000-8000-0000000000d4
"$SMINOS" seat add demo a --session "$SA" >/dev/null
"$SMINOS" seat add demo b --session "$SB" >/dev/null
"$SMINOS" seat add demo c --session "$SC" >/dev/null
"$SMINOS" seat add demo d --session "$SD" >/dev/null
for m in a b c; do start_inbox "$m"; done
live_peer a "$SA" idle
live_peer b "$SB" idle
live_peer c "$SC" busy
mkdir -p "$HOME/.claude/projects/pl-proj"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/pl-proj/$SD.jsonl"   # d is stopped: no process, a transcript here
printf 'short=dddd0d04\nuuid=%s\nname=d\nstate=stopped\nstatus=\ncwd=%s\n' "$SD" "$PR" > "$STUB_STATE/agents/dddd0d04"
: > "$STUB_STATE/log/calls.log"

# Acceptance 2: untagged is a record, a tag delivers, @all wakes the live.
export CLAUDE_CODE_SESSION_ID="$SA"
run "$SMINOS" say "merged #12"
assert_rc 0 "$RC" "an untagged say records"
assert_contains "$OUT" "in demo" "into the project's log"
assert_contains "$(log_of "$DEMO")" '"kind": "say", "from": "a", "to": "*", "text": "merged #12"' "an untagged say is a say to *"
assert_file_exists "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl" "the writer file is <machine>.<session>.jsonl"
assert_equals "$(inbox a)$(inbox b)$(inbox c)" "" "a say to * pushes nothing"
CLAUDE_CODE_SESSION_ID="$SB" run "$SMINOS" chat
assert_rc 0 "$RC" "a member reads the project chat"
assert_contains "$OUT" "a → *" "the chat attributes the line to its sender"
assert_contains "$OUT" "merged #12" "and carries the text"
assert_file_exists "$SMINOS_HOME/projects/$DEMO/cursors/$SB.json" "chat saves the reader's cursor"
CURSOR_BEFORE="$(cat "$SMINOS_HOME/projects/$DEMO/cursors/$SB.json")"
CLAUDE_CODE_SESSION_ID="$SB" run "$SMINOS" chat
assert_contains "$OUT" "no new messages" "a second chat has nothing above the cursor"
CLAUDE_CODE_SESSION_ID="$SB" run "$SMINOS" chat -n 5
assert_contains "$OUT" "merged #12" "chat -n tails the log"
assert_equals "$(cat "$SMINOS_HOME/projects/$DEMO/cursors/$SB.json")" "$CURSOR_BEFORE" "chat -n does not move the cursor"
run "$SMINOS" say "@b look at X"
assert_rc 0 "$RC" "a tagged say records"
assert_contains "$OUT" "b: sent" "and delivers to the live member"
assert_contains "$(inbox b)" "[sminos chat demo ${SA:0:8}:$(last_seq "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl") from a \u2192 @you]" "the frame names project, event id, sender, and @you"
assert_contains "$(inbox b)" "look at X" "the frame carries the text"
assert_equals "$(inbox c)" "" "a tag reaches only its recipient"
assert_contains "$(cat "$SMINOS_HOME/projects/$DEMO/delivered/$SB.json")" "\"testhost/$SA\": {\"settled\": $(last_seq "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl")" "delivery is the deliverer's record, settled per writer"
assert_not_contains "$(log_of "$DEMO")" '"delivered"' "the log is never rewritten with outcomes"
run "$SMINOS" say "@all rebase in progress"
assert_rc 0 "$RC" "an @all records"
assert_contains "$(inbox b)" "\u2192 @all" "@all wakes an idle member"
assert_contains "$(inbox b)" "rebase in progress" "with the text"
assert_contains "$(inbox c)" "rebase in progress" "@all reaches a busy member"
assert_not_contains "$(cat "$STUB_STATE/log/calls.log")" "--resume $SD" "@all resumes no stopped member"
assert_equals "$(inbox a)" "" "@all is never delivered to its sender"
assert_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl")" '"wake": true' "@all is recorded with wake"
assert_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl")" "\"alias\": \"b\"" "its audience is the live members at submission"
assert_not_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl")" "\"alias\": \"d\"" "a stopped member is not in its audience"
assert_not_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl")" "\"alias\": \"a\"" "nor is its sender"
# A member that joins after the broadcast never receives it.
SE=e0000005-0000-4000-8000-0000000000e5
unset CLAUDE_CODE_SESSION_ID
"$SMINOS" seat add demo e --session "$SE" >/dev/null
start_inbox e
live_peer e "$SE" idle
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@e welcome"
assert_contains "$(inbox e)" "welcome" "a later member is reached by a tag"
assert_not_contains "$(inbox e)" "rebase in progress" "an @all written before a member joined is never delivered to it"
# A tag to a stopped member resumes it.
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@d wake up"
assert_contains "$OUT" "d: woken" "a tag resumes a stopped member"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "--bg --resume $SD" "through its saved session"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@a hi"
assert_rc 2 "$RC" "a member cannot tag itself"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@all @b hi"
assert_rc 2 "$RC" "@all stands alone"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@nobody hi"
assert_rc 4 "$RC" "a tag matching no member is refused as unknown"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "report: the @b attempt failed"
assert_not_contains "$OUT" "b:" "an @ later in the text addresses no one"
# Ambiguity: two members share an alias; #short and @short tell them apart.
SC2=c0000006-0000-4000-8000-0000000000c6
"$SMINOS" seat add other c --session "$SC2" >/dev/null
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@c hi"
assert_rc 4 "$RC" "a tag matching two members is refused"
assert_contains "$OUT" "c#c0000003" "naming the first as alias#short"
assert_contains "$OUT" "c#c0000006" "and the second"
: > "$TEST_ROOT/in-c.received"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@c#c0000003 the busy one"
assert_rc 0 "$RC" "@name#short resolves"
assert_contains "$(inbox c)" "the busy one" "to the member it names"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@c0000006 by short"
assert_rc 0 "$RC" "@short resolves"
assert_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl")" "\"session\": \"$SC2\"" "an address is stored as the session id"
"$SMINOS" remove other/c >/dev/null
# A quoted tag reaches a display name with spaces.
SW=f0000007-0000-4000-8000-0000000000f7
python3 - "$SMINOS_HOME/$SW.json" "$SW" "$PR" <<'PY_TWO'
import json, sys
json.dump({"uuid": sys.argv[2], "current": sys.argv[2], "alias": "two words", "name": "two words",
           "group": "demo", "status": "idle", "cwd": sys.argv[3]}, open(sys.argv[1], "w"))
PY_TWO
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say '@"two words" hello there'
assert_rc 0 "$RC" '@"two words" resolves'
assert_contains "$OUT" "two words:" "and is reported per recipient"
assert_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.$SA.jsonl")" '"alias": "two words"' "recorded with its alias"
rm -f "$SMINOS_HOME/$SW.json"

# Another project: a tag names it; a message has one destination.
P2="$TEST_ROOT/other-repo"
mkdir -p "$P2"
gitq init -q "$P2"
(cd "$P2" && "$SMINOS" project init --name other >/dev/null)
OTHER="$(smns_id "$P2")"
SX=0a000008-0000-4000-8000-0000000000a8
(cd "$P2" && "$SMINOS" seat add other x --session "$SX" >/dev/null)
start_inbox x
live_peer x "$SX" idle
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@other/x the shared plugin changed"
assert_rc 0 "$RC" "a tag into another project records"
assert_contains "$OUT" "in other" "in the destination project"
assert_contains "$(log_of "$OTHER")" "the shared plugin changed" "the message lands in the tagged project's log"
assert_not_contains "$(log_of "$DEMO")" "the shared plugin changed" "and nowhere else"
assert_contains "$(inbox x)" "[sminos chat other " "the recipient's frame names its project"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" say "@other/x @b both"
assert_rc 2 "$RC" "tags naming two projects are refused"
assert_contains "$OUT" "one message, one project" "with the reason"
assert_not_contains "$(log_of "$DEMO")$(log_of "$OTHER")" '"text": "@other/x @b both"' "and nothing is recorded"
CLAUDE_CODE_SESSION_ID="$SA" run "$SMINOS" chat other -n 5
assert_contains "$OUT" "the shared plugin changed" "the sender reads the record with chat <project>"
unset CLAUDE_CODE_SESSION_ID

# The operator: human events, --in a project by name or id.
run "$SMINOS" say "operator note"
assert_rc 0 "$RC" "the operator says in the cwd's project"
assert_contains "$(log_of "$DEMO")" '"kind": "human", "from": "human", "to": "*", "text": "operator note"' "an operator's untagged say is human to *"
run_in "$TEST_ROOT/nowhere" "$SMINOS" say "lost"
assert_rc 2 "$RC" "outside a project the operator must name one"
run_in "$TEST_ROOT/nowhere" "$SMINOS" say --in other "by name"
assert_rc 0 "$RC" "--in accepts a project name"
run_in "$TEST_ROOT/nowhere" "$SMINOS" say --in "$OTHER" "by id"
assert_rc 0 "$RC" "--in accepts a project id"
assert_contains "$(log_of "$OTHER")" '"text": "by id"' "and records there"
: > "$TEST_ROOT/in-b.received"
run "$SMINOS" say "@b from the operator"
assert_contains "$(inbox b)" "from human \u2192 @you" "an operator's tag delivers as human"
run "$SMINOS" chat
assert_rc 0 "$RC" "the operator reads the chat"
assert_file_exists "$SMINOS_HOME/projects/$DEMO/cursors/human.json" "with a cursor of its own"

# send is recorded to the one session it reaches, and never owed again.
: > "$TEST_ROOT/in-b.received"
run "$SMINOS" send demo/b "direct line"
assert_rc 0 "$RC" "send still delivers"
assert_contains "$(inbox b)" "[sminos message from human id=" "with its own frame"
assert_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.human.jsonl")" '"text": "direct line"' "send is recorded in the target's project"
assert_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.human.jsonl")" "\"session\": \"$SB\"" "addressed to its session"
OWED="$(python3 - "$SMINOS_PY" "$DEMO" "$SB" <<'PY_OWED'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
print(len(mod.owed(p, next(m for m in mod.members(p) if m.session == sys.argv[3]))))
PY_OWED
)"
assert_equals "$OWED" 0 "a sent message is settled in its recipient's delivery record"
owed_count() { # session → events owed to the seat holding it
  python3 - "$SMINOS_PY" "$DEMO" "$1" <<'PY_OWEDN'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
print(len(mod.owed(p, next(m for m in mod.members(p) if m.session == sys.argv[3]))))
PY_OWEDN
}
last_frame() { python3 -c 'import json,sys; print(json.loads(open(sys.argv[1]).read().splitlines()[-1])["message"]["content"])' "$TEST_ROOT/in-$1.received"; }
DEMO_HUMAN="$SMINOS_HOME/projects/$DEMO/log/testhost.human.jsonl"
# --from signs the frame; the log keeps who sent it.
: > "$TEST_ROOT/in-b.received"
run "$SMINOS" send demo/b "signed" --from sweep
assert_contains "$(inbox b)" "[sminos message from sweep id=" "--from signs the frame"
assert_contains "$(tail -1 "$DEMO_HUMAN")" '"kind": "human", "from": "human"' "the log keeps the operator as the sender"
assert_contains "$(tail -1 "$DEMO_HUMAN")" '"via": "sweep"' "and carries the override beside it"
# A send that dies between its append and its push stays owed, and a later
# deliver_next pushes it with its own frame.
: > "$TEST_ROOT/in-b.received"
python3 - "$SMINOS_PY" "$SB" <<'PY_WINDOW'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
mod.record_send(mod.reload_seat(sys.argv[2]), "human", "", "lost in the window", "deadbeef").release()
PY_WINDOW
assert_equals "$(owed_count "$SB")" 1 "a send that died between append and push is still owed"
assert_equals "$(inbox b)" "" "and was not pushed"
python3 - "$SMINOS_PY" "$DEMO" "$SB" <<'PY_LATER' >/dev/null
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
print(mod.deliver_next(p, next(m for m in mod.members(p) if m.session == sys.argv[3])))
PY_LATER
assert_contains "$(inbox b)" "[sminos message from human id=deadbeef]" "a later deliver_next delivers it with its own frame"
assert_equals "$(owed_count "$SB")" 0 "and settles it"
# A send that follows an earlier pending event of its writer carries it first, in one push.
python3 - "$SMINOS_PY" "$DEMO" "$SB" <<'PY_PENDING'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p, w = mod.find_project(sys.argv[2]), mod.writer_id()
e = mod.log_append(p, w, "human", **{"from": "human", "to": [{"session": sys.argv[3], "alias": "b"}], "text": "earlier pending"})
mod.delivered_fail(p, sys.argv[3], w, e["seq"])
PY_PENDING
: > "$TEST_ROOT/in-b.received"
run "$SMINOS" send demo/b "after pending"
assert_rc 0 "$RC" "a send behind a pending event delivers"
assert_equals "$(last_frame b | python3 -c 'import sys; c = sys.stdin.read(); print(-1 < c.find("earlier pending") < c.find("after pending"))')" True "the earlier pending event goes first, in the same push"
assert_equals "$(owed_count "$SB")" 0 "and both are settled"
# A message the log cannot hold is not sent.
chmod 400 "$DEMO_HUMAN"
: > "$TEST_ROOT/in-b.received"
run "$SMINOS" send demo/b "unrecordable"
chmod 600 "$DEMO_HUMAN"
assert_rc 1 "$RC" "a send that cannot be recorded fails"
assert_contains "$OUT" "could not be recorded" "and says why"
assert_equals "$(inbox b)" "" "and delivers nothing"
# Overlapping chat reads: an older snapshot saved last never moves a cursor back.
CURSOR_RACE="$(python3 - "$SMINOS_PY" "$DEMO" <<'PY_RACE'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p, reader = mod.find_project(sys.argv[2]), "0e00000e-0000-4000-8000-00000000000e"
mod.cursor_save(p, reader, {"w/one": 5, "w/two": 2})   # the newer read saves first
mod.cursor_save(p, reader, {"w/one": 3, "w/two": 4})   # the older snapshot saves last
print(json.dumps(mod.cursor_load(p, reader), sort_keys=True))
PY_RACE
)"
assert_equals "$CURSOR_RACE" '{"w/one": 5, "w/two": 4}' "overlapping reads merge per writer, never moving a cursor back"
# A session cannot send to its own seat.
CLAUDE_CODE_SESSION_ID="$SB" run "$SMINOS" send demo/b "to myself"
assert_rc 2 "$RC" "a send to your own seat is refused"
assert_contains "$OUT" "you cannot send to yourself" "with the reason"
# A send another deliverer settled first still waits for the turn under --wait.
printf 'short=bbbb0b02\nuuid=%s\nname=b\nkind=interactive\nstate=\nstatus=idle\ncwd=%s\n' "$SB" "$PR" > "$STUB_STATE/agents/bbbb0b02"
: > "$TEST_ROOT/in-b.received"
python3 - "$SMINOS_PY" "$DEMO" "$SB" > "$TEST_ROOT/race-wait.out" 2>&1 <<'PY_RACE_WAIT' &
import argparse, importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
append = mod.log_append
def append_then_deliver(project, writer, kind, **fields):
    e = append(project, writer, kind, **fields)
    if fields.get("msg_id"):  # a concurrent deliverer gets there first
        mod.deliver_next(project, next(m for m in mod.members(project) if m.session == sys.argv[3]))
    return e
mod.log_append = append_then_deliver
mod.cmd_send(argparse.Namespace(target="demo/b", msg="raced", frm="", wait=True))
PY_RACE_WAIT
RACEW=$!
for _ in $(seq 1 100); do grep -q 'id=' "$TEST_ROOT/in-b.received" && break; sleep 0.05; done
RACE_ID="$(grep -o 'id=[0-9a-f]\{8\}' "$TEST_ROOT/in-b.received" | tail -1 | cut -d= -f2)"
sleep 0.3
if kill -0 "$RACEW" 2>/dev/null; then pass "send --wait is still waiting for the turn the other deliverer started"
else fail "send --wait is still waiting for the turn the other deliverer started"; fi
python3 - "$HOME/.claude/projects/pl-proj/$SB.jsonl" "$RACE_ID" <<'PY_TURN'
import json, sys
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "[sminos message from human id=%s]\nraced" % sys.argv[2]}}) + "\n")
    f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "RACED " + sys.argv[2]}]}}) + "\n")
PY_TURN
wait "$RACEW" || true
assert_equals "$(grep -c 'raced' "$TEST_ROOT/in-b.received")" 1 "the settled send is not pushed twice"
assert_contains "$(cat "$TEST_ROOT/race-wait.out")" "delivered by a concurrent delivery" "send says who delivered it"
assert_contains "$(cat "$TEST_ROOT/race-wait.out")" "--- reply ---" "and still prints the reply block"
assert_contains "$(cat "$TEST_ROOT/race-wait.out")" "RACED $RACE_ID" "with the turn's reply"
# A pending @all is settled, not replayed, when a send resumes a stopped member.
python3 - "$SMINOS_PY" "$DEMO" "$SB" <<'PY_WAKE'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p, w = mod.find_project(sys.argv[2]), mod.writer_id()
e = mod.log_append(p, w, "human", **{"from": "human", "to": [{"session": sys.argv[3], "alias": "b"}],
                                    "text": "@all stale broadcast", "wake": True})
mod.delivered_fail(p, sys.argv[3], w, e["seq"])  # it failed while b was live
PY_WAKE
mv "$HOME/.claude/sessions/pl-b.json" "$TEST_ROOT/pl-b.json.aside"   # b stops
: > "$STUB_STATE/log/calls.log"
run "$SMINOS" send demo/b "after a broadcast"
assert_rc 0 "$RC" "a send to a stopped member behind a pending @all delivers"
assert_contains "$OUT" "via --bg --resume" "by resuming it"
assert_contains "$(cat "$STUB_STATE/log/calls.log")" "after a broadcast" "the resume carries the send"
assert_not_contains "$(cat "$STUB_STATE/log/calls.log")" "stale broadcast" "but not the broadcast a stopped member is never resumed for"
assert_equals "$(owed_count "$SB")" 0 "the broadcast is settled by passing"
mv "$TEST_ROOT/pl-b.json.aside" "$HOME/.claude/sessions/pl-b.json"
rm -f "$STUB_STATE/agents/bbbb0b02"

# The merged display: per-writer streams in seq order, heads by (ts, writer).
MERGE="$SMINOS_HOME/projects/merge-test"
mkdir -p "$MERGE/log"
printf '{"project": "merge-test", "name": "merge", "remote": "", "root": "/nowhere"}\n' > "$MERGE/project.json"
python3 - "$MERGE/log" <<'PY_MERGE'
import json, os, sys
d = sys.argv[1]
def w(name, events):
    with open(os.path.join(d, name), "w") as f:
        for e in events:
            f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")
w("h1.w1.jsonl", [
    {"ts": "2026-10-13T08:00:01.000Z", "writer": "h1/w1", "seq": 1, "kind": "human", "from": "w1", "to": "*", "text": "w1-1"},
    {"ts": "2026-10-13T08:00:04.000Z", "writer": "h1/w1", "seq": 2, "kind": "human", "from": "w1", "to": "*", "text": "w1-2"},
    "not json at all",
    {"ts": "2026-10-13T08:00:02.000Z", "writer": "h1/w1", "seq": 3, "kind": "human", "from": "w1", "to": "*", "text": "w1-3 clock stepped back"}])
w("h2.w2.jsonl", [
    {"ts": "2026-10-13T08:00:03.000Z", "writer": "h2/w2", "seq": 1, "kind": "human", "from": "w2", "to": "*", "text": "w2-1"}])
PY_MERGE
run "$SMINOS" chat merge -n 10 --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json,sys; print(" ".join(json.loads(l)["text"].split()[0] for l in sys.stdin if l.strip()))')" \
  "w1-1 w2-1 w1-2 w1-3" "two writers interleave by ts while one writer keeps seq order under a backwards ts"
run "$SMINOS" chat merge --since 2026-10-13T08:00:03Z --json
assert_equals "$(printf '%s\n' "$OUT" | grep -c '"text"')" 2 "chat --since reads from a time"

# Appends: seq under the file lock, a torn or malformed line skipped and never rewritten.
HUMAN_LOG="$SMINOS_HOME/projects/$DEMO/log/testhost.human.jsonl"
LAST_SEQ="$(tail -1 "$HUMAN_LOG" | python3 -c 'import json,sys; print(json.load(sys.stdin)["seq"])')"
printf '%s\n%s' 'garbage line' '{"ts":"x","seq":' >> "$HUMAN_LOG"
run "$SMINOS" say "after a torn append"
assert_rc 0 "$RC" "a say after a torn append records"
assert_contains "$(tail -1 "$HUMAN_LOG")" "\"seq\": $((LAST_SEQ + 1))" "seq follows the last well-formed line"
assert_contains "$(cat "$HUMAN_LOG")" "garbage line" "a malformed line is never rewritten"
"$SMINOS" say "parallel one" >/dev/null & p1=$!
"$SMINOS" say "parallel two" >/dev/null & p2=$!
wait "$p1"; wait "$p2"
assert_equals "$(tail -2 "$HUMAN_LOG" | python3 -c 'import json,sys; print(sorted(json.loads(l)["seq"] for l in sys.stdin))')" \
  "[$((LAST_SEQ + 2)), $((LAST_SEQ + 3))]" "two concurrent appends take distinct consecutive seqs"
assert_equals "$(tail -1 "$HUMAN_LOG" | python3 -c 'import json,re,sys; print(bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", json.load(sys.stdin)["ts"])))')" True "ts is ISO-8601 UTC with milliseconds"
BATCH="$(python3 - "$SMINOS_PY" "$DEMO" <<'PY_BATCH'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p, w = mod.find_project(sys.argv[2]), "testhost/0d00000d-0000-4000-8000-00000000000d"
spans = [{"kind": "message", "src": "r1#0", "text": "one"}, {"kind": "message", "src": "r1#1", "text": "two"}]
first = mod.log_append_batch(p, w, spans)
again = mod.log_append_batch(p, w, spans + [{"kind": "message", "src": "r2#0", "text": "three"}])
plain = mod.log_append_batch(p, w, [{"kind": "status", "text": "no src"}, {"kind": "status", "text": "nor here"}])
print([e["seq"] for e in first], [e["seq"] for e in again], [e["seq"] for e in plain])
PY_BATCH
)"
assert_equals "$BATCH" "[1, 2] [3] [4, 5]" "a batch drops the events whose src the file holds, and never one without a src"
QA="$(python3 - "$SMINOS_PY" "$DEMO" <<'PY_QA'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p, w = mod.find_project(sys.argv[2]), "testhost/0f00000f-0000-4000-8000-00000000000f"
question = {"kind": "question", "src": "toolu_1", "text": ["Pick?"], "choices": ["a", "b"]}
answered = {"kind": "answered", "src": "toolu_1", "text": "a"}
print(len(mod.log_append_batch(p, w, [question])), len(mod.log_append_batch(p, w, [answered])),
      len(mod.log_append_batch(p, w, [question, answered])))
PY_QA
)"
assert_equals "$QA" "1 1 0" "an answer shares its question's src and is still appended, once"

# Delivery settles in order per writer: event 10 failing holds back event 11.
DELIVERY_TEST="$TEST_ROOT/deliver_test.py"
cat > "$DELIVERY_TEST" <<'PY_DELIVER'
import importlib.util, json, os, sys, time
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
project, seat_id, mode, record = mod.find_project(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
member = next(m for m in mod.members(project) if m.session == seat_id)
down = os.path.join(os.path.dirname(record), "push-down")
def fake_push(member, text, tagged, session=None):
    body = text.split("\n", 1)[1]
    time.sleep(0.05)
    if body == "ten" and os.path.exists(down):
        if mode == "once":
            os.unlink(down)  # the next attempt succeeds
        with open(record, "a") as f:
            f.write("fail:%s\n" % body)
        return "failed:simulated"
    with open(record, "a") as f:
        f.write("sent:%s\n" % body)
    return "sent"
mod.push_member = fake_push
print(json.dumps({k: v for k, v in mod.deliver_next(project, member).items() if k != "outcomes"}))
PY_DELIVER
SG=09000009-0000-4000-8000-000000000009
"$SMINOS" seat add demo g --session "$SG" >/dev/null
W10=0c00000c-0000-4000-8000-00000000000c
python3 - "$SMINOS_PY" "$DEMO" "$W10" <<'PY_FILL'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
for _ in range(9):
    mod.log_append(p, mod.writer_id(sys.argv[3]), "say", **{"from": "k", "to": "*", "text": "filler"})
PY_FILL
REC="$TEST_ROOT/deliver.log"
: > "$REC"; touch "$TEST_ROOT/push-down"
append_g() { python3 - "$SMINOS_PY" "$DEMO" "$W10" "$SG" "$1" <<'PY_APPEND'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
e = mod.log_append(p, mod.writer_id(sys.argv[3]), "say", **{"from": "k", "to": [{"session": sys.argv[4], "alias": "g"}], "text": sys.argv[5]})
print(e["seq"])
PY_APPEND
}
assert_equals "$(append_g ten)" 10 "the failing event is the writer's event 10"
assert_equals "$(python3 "$DELIVERY_TEST" "$SMINOS_PY" "$DEMO" "$SG" sticky "$REC")" '{"delivered": 0, "pending": 1}' "a failed push leaves the event pending"
assert_equals "$(append_g eleven)" 11 "the next event is 11"
assert_equals "$(python3 "$DELIVERY_TEST" "$SMINOS_PY" "$DEMO" "$SG" sticky "$REC")" '{"delivered": 0, "pending": 2}' "11 waits while 10 still fails"
assert_equals "$(tr '\n' ' ' < "$REC")" "fail:ten fail:ten " "11 is never pushed before 10"
assert_contains "$(cat "$SMINOS_HOME/projects/$DEMO/delivered/$SG.json")" '"pending": 10, "attempts": 2' "the record keeps the pending event and its attempts"
rm -f "$TEST_ROOT/push-down"
assert_equals "$(python3 "$DELIVERY_TEST" "$SMINOS_PY" "$DEMO" "$SG" sticky "$REC")" '{"delivered": 2, "pending": 0}' "a later attempt delivers both"
assert_equals "$(tr '\n' ' ' < "$REC")" "fail:ten fail:ten sent:ten sent:eleven " "in order"
assert_equals "$(python3 "$DELIVERY_TEST" "$SMINOS_PY" "$DEMO" "$SG" sticky "$REC")" '{"delivered": 0, "pending": 0}' "nothing is delivered twice"
# The same, with the sender's fast path and a daemon tick (two deliver_next) at once.
"$SMINOS" seat add demo h --session 0a00000a-0000-4000-8000-00000000000a >/dev/null
SH=0a00000a-0000-4000-8000-00000000000a
python3 - "$SMINOS_PY" "$DEMO" "$SH" <<'PY_FILL2'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
w = "testhost/0b00000b-0000-4000-8000-00000000000b"
for text in ["ten", "eleven", "twelve"]:
    mod.log_append(p, w, "say", **{"from": "k", "to": [{"session": sys.argv[3], "alias": "h"}], "text": text})
PY_FILL2
: > "$REC"; touch "$TEST_ROOT/push-down"
python3 "$DELIVERY_TEST" "$SMINOS_PY" "$DEMO" "$SH" once "$REC" >/dev/null & d1=$!
python3 "$DELIVERY_TEST" "$SMINOS_PY" "$DEMO" "$SH" once "$REC" >/dev/null & d2=$!
wait "$d1"; wait "$d2"
python3 "$DELIVERY_TEST" "$SMINOS_PY" "$DEMO" "$SH" once "$REC" >/dev/null
assert_equals "$(grep '^sent:' "$REC" | tr '\n' ' ')" "sent:ten sent:eleven sent:twelve " "concurrent deliverers push each event once, in writer order"
assert_equals "$(head -1 "$REC")" "fail:ten" "the first attempt at 10 failed and held 11 back"
# The same through the real mechanisms: a writer's event 10 fails in its own
# fast path (a resume that does not launch); then its event 11 goes out on
# the sender's fast path while a real `daemon tick` delivers at once. (The
# in-process race above stays: it stages a failure inside the race itself.)
SQ=0d00000d-0000-4000-8000-00000000000d
WQ=0e00000e-0000-4000-8000-00000000000e
"$SMINOS" seat add demo q --session "$SQ" >/dev/null
mkdir -p "$HOME/.claude/projects/q-proj"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/q-proj/$SQ.jsonl"   # q is stopped: a tag resumes it
python3 - "$SMINOS_PY" "$DEMO" "$WQ" <<'PY_FILLQ'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
for _ in range(9):
    mod.log_append(p, mod.writer_id(sys.argv[3]), "say", **{"from": "w", "to": "*", "text": "filler"})
PY_FILLQ
STUB_FAIL_BG=1 CLAUDE_CODE_SESSION_ID="$WQ" run "$SMINOS" say "@q ten"
assert_contains "$OUT" "q: failed:resume failed" "event 10's push fails in the fast path: the resume does not launch"
assert_contains "$(tail -1 "$SMINOS_HOME/projects/$DEMO/log/testhost.$WQ.jsonl")" '"seq": 10, "kind": "say"' "it is the writer's event 10"
start_inbox q
live_peer q "$SQ" idle
CLAUDE_CODE_SESSION_ID="$WQ" "$SMINOS" say "@q eleven" > "$TEST_ROOT/q-say.out" 2>&1 & qs=$!
"$SMINOS" daemon tick > "$TEST_ROOT/q-tick.out" 2>&1 & qt=$!
wait "$qs" || true; wait "$qt" || true
assert_equals "$(bodies q | grep -e '^@q ten$' -e '^@q eleven$' | tr '\n' ' ')" "@q ten @q eleven " \
  "with the fast path and a daemon tick at once, 10 and 11 each arrive once, 11 never before 10"
assert_equals "$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))[sys.argv[2]]; print(d["settled"], d["pending"])' \
  "$SMINOS_HOME/projects/$DEMO/delivered/$SQ.json" "testhost/$WQ")" "11 None" "and both are settled"
rm -f "$HOME/.claude/sessions/pl-q.json"

# attach adopts the existing log/; an unreachable remote is not an error.
P3="$TEST_ROOT/remote-repo"
mkdir -p "$P3"
gitq init -q "$P3"
(cd "$P3" && "$SMINOS" project init --name mirrored --remote "$TEST_ROOT/no-such-remote.git" >/dev/null)
MIRRORED="$(smns_id "$P3")"
(cd "$P3" && "$SMINOS" say "before attach" >/dev/null)
run_in "$P3" "$SMINOS" project attach
assert_rc 0 "$RC" "attach with an unreachable remote succeeds"
assert_contains "$OUT" "the daemon" "and says the first sync is left to the daemon"
assert_contains "$(log_of "$MIRRORED")" "before attach" "attach preserves the local log"
assert_contains "$(git -C "$SMINOS_HOME/projects/$MIRRORED/log" log --oneline 2>&1)" "attach" "the existing log is the first commit"
assert_contains "$(git -C "$SMINOS_HOME/projects/$MIRRORED/log" ls-files)" "testhost.human.jsonl" "the writer files are committed"
assert_not_contains "$(git -C "$SMINOS_HOME/projects/$MIRRORED/log" ls-files)" ".lock" "lock files are never committed"
assert_equals "$(git -C "$SMINOS_HOME/projects/$MIRRORED/log" remote get-url origin)" "$TEST_ROOT/no-such-remote.git" "the remote is added"
# A remote that already carries another machine's history is integrated.
BARE="$TEST_ROOT/smns-remote.git"
gitq init -q --bare "$BARE"
SEED="$TEST_ROOT/seed"
gitq clone -q "$BARE" "$SEED" 2>/dev/null
printf '{"ts": "2026-10-13T08:00:00.000Z", "writer": "h9/human", "seq": 1, "kind": "human", "from": "human", "to": "*", "text": "from h9"}\n' > "$SEED/h9.human.jsonl"
gitq -C "$SEED" add h9.human.jsonl
gitq -C "$SEED" commit -qm "h9"
gitq -C "$SEED" push -q origin HEAD:main 2>/dev/null
python3 - "$P3/.smns" "$BARE" <<'PY_REMOTE'
import json, sys
d = json.load(open(sys.argv[1])); d["remote"] = sys.argv[2]; json.dump(d, open(sys.argv[1], "w"))
PY_REMOTE
run_in "$P3" "$SMINOS" project attach
assert_rc 0 "$RC" "attach to a populated remote succeeds"
assert_file_exists "$SMINOS_HOME/projects/$MIRRORED/log/h9.human.jsonl" "the remote's writer files arrive"
assert_contains "$(log_of "$MIRRORED")" "before attach" "beside the local ones (unrelated histories integrated)"
run_in "$P3" "$SMINOS" chat -n 10
assert_contains "$OUT" "from h9" "the merged log reads both machines"
run_in "$PR" "$SMINOS" project attach
assert_rc 2 "$RC" "attach of a project without a remote is refused"
chmod 500 "$SMINOS_HOME/projects/$MIRRORED/log/.git"
run_in "$P3" "$SMINOS" project attach
chmod 700 "$SMINOS_HOME/projects/$MIRRORED/log/.git"
assert_rc 1 "$RC" "a git step that fails ends the attach"
assert_contains "$OUT" "git config user.name in" "naming the step that failed"

# migrate imports the former per-host family chats as legacy writers.
HOST_ID="$SA"
mkdir -p "$SMINOS_HOME/chats"
python3 - "$SMINOS_HOME/chats/$HOST_ID.jsonl" <<'PY_CHATS'
import json, sys
rows = [{"id": 1, "ts": "2026-09-26T05:00:00Z", "from": "b", "to": ["a"], "mode": "host", "text": "old report", "delivered": {"a": "sent"}},
        {"id": 2, "ts": "2026-09-26T05:00:01Z", "from": "a", "to": ["b"], "mode": "tagged", "text": "@b old tag", "delivered": {"b": "sent"}},
        {"id": 3, "ts": "2026-09-26T05:00:02Z", "from": "human", "to": ["a", "b"], "mode": "operator", "text": "old operator", "delivered": {}},
        {"id": 4, "ts": "2026-09-26T05:00:03Z", "from": "a", "to": ["gone"], "mode": "tagged", "text": "@gone hello", "delivered": {}}]
with open(sys.argv[1], "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
PY_CHATS
run "$SMINOS" migrate
assert_rc 0 "$RC" "migrate runs"
assert_contains "$OUT" "imported 1 family chat" "and reports the import"
LEGACY="$SMINOS_HOME/projects/$DEMO/log/legacy.$HOST_ID.jsonl"
assert_file_exists "$LEGACY" "a family chat becomes the legacy writer's file in the host's project"
assert_file_absent "$SMINOS_HOME/chats/$HOST_ID.jsonl" "the chat file is set aside once imported"
assert_contains "$(cat "$LEGACY")" '"ts": "2026-09-26T05:00:01.000Z", "writer": "legacy/'"$HOST_ID"'", "seq": 2, "kind": "say", "from": "a", "to": [{"session": "'"$SB"'", "alias": "b"}]' "a tag is resolved against the seats to a session"
assert_contains "$(cat "$LEGACY")" '"kind": "human", "from": "human", "to": "*", "text": "old operator"' "an operator line imports as human to *"
assert_contains "$(cat "$LEGACY")" '"to": "*", "text": "@gone hello"' "an unresolvable tag stays as text"
assert_not_contains "$(cat "$LEGACY")" '"delivered"' "the old delivery maps are not imported"
run "$SMINOS" migrate
assert_not_contains "$OUT" "imported" "the import runs once"
OWED_LEGACY="$(python3 - "$SMINOS_PY" "$DEMO" "$SB" <<'PY_OWED2'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p = mod.find_project(sys.argv[2])
print(sum(1 for e in mod.owed(p, next(m for m in mod.members(p) if m.session == sys.argv[3])) if e["writer"].startswith("legacy/")))
PY_OWED2
)"
assert_equals "$OWED_LEGACY" 0 "imported history is never delivered again"
run "$SMINOS" chat -n 50
assert_contains "$OUT" "old tag" "imported lines read in the project chat"
cd "$WORK"
rm -f "$HOME/.claude/sessions/pl-"*.json

# ---- the project family ---------------------------------------------------------
# Members are derived: a session whose latest joined/retired is joined, plus, on
# this machine, every live harness session and every seat in the project, joined
# into the log on sight. There is no host and no tree: a spawn records its
# spawner as provenance and nothing more (spec 2026-10-13, M2).
echo "the project family:"
export SMINOS_HOME="$TEST_ROOT/pf-registry"
mkdir -m 700 "$SMINOS_HOME"
rm -f "$HOME/.claude/sessions/"*.json
unset CLAUDE_CODE_SESSION_ID
R="$TEST_ROOT/pf-repo"
mkdir -p "$R/deep"
gitq init -q "$R"
(cd "$R" && "$SMINOS" project init --name pfdemo >/dev/null)
gitq -C "$R" add .smns
gitq -C "$R" commit -qm smns
PF="$(smns_id "$R")"
PFLOG="$SMINOS_HOME/projects/$PF/log"
pf_peer() { # name session status [nameSource] [cwd] [pid] — a live harness session with an inbox of its own
  [ -S "$TEST_ROOT/in-$1.sock" ] || start_inbox "$1"
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"%s","kind":"interactive","status":"%s","cwd":"%s","messagingSocketPath":"%s"}\n' \
    "${6:-$SOCK_PID}" "$2" "$1" "${4:-derived}" "$3" "${5:-$R}" "$TEST_ROOT/in-$1.sock" > "$HOME/.claude/sessions/pf-$1.json"
}
events_of() { # session → its own writer file's events as "kind[:reason]" words
  python3 -c 'import json, sys
for l in open(sys.argv[1]):
    e = json.loads(l)
    print(e["kind"] + (":" + e["reason"] if e.get("reason") else ""), end=" ")' "$PFLOG/testhost.$1.jsonl" 2>/dev/null || true
}
json_row() { # alias field [project] → that field of the alias's row in list --json
  "$SMINOS" list ${3:-} --json | python3 -c 'import json, sys
rows = [d for d in json.load(sys.stdin) if d["alias"] == sys.argv[1]]
v = rows[0].get(sys.argv[2]) if rows else "<no row>"
print(v if isinstance(v, str) else json.dumps(v))' "$1" "$2"
}
# The Stop / SessionStart hook, run as the harness runs it: one JSON payload on stdin.
HOOK="$REPO_ROOT/hooks/smns-record.sh"
# HOOK_OUT is everything it printed (the harness would inject a SessionStart
# hook's stdout as context), HOOK_RC its exit code.
hook_run() { # event session cwd transcript [source]
  set +e
  HOOK_OUT="$(printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","hook_event_name":"%s","source":"%s"}' \
    "$2" "$4" "$3" "$1" "${5:-}" | CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$HOOK" 2>&1)"
  HOOK_RC=$?
  set -e
}
cd "$R"

# Acceptance 1: two interactive sessions in the project list under its name,
# with their state words, no seat add run.
IA=1a000001-0000-4000-8000-00000000001a
IB=1b000002-0000-4000-8000-00000000001b
pf_peer ia "$IA" idle user
pf_peer ib "$IB" busy derived "$R/deep"
run "$SMINOS" list
assert_rc 0 "$RC" "list in a project with two interactive sessions exits 0"
assert_equals "$(printf '%s\n' "$OUT" | head -1)" "pfdemo" "list prints the project's heading"
assert_contains "$OUT" "  ia   idle" "a seat-less interactive session lists with its state word"
assert_contains "$OUT" "  ib   busy" "so does one working in a subdirectory of the project"
assert_equals "$(events_of "$IA")" "joined " "the first list joins a live session into the log"
assert_contains "$(cat "$PFLOG/testhost.$IA.jsonl")" '"name_source": "user"' "with the harness's name source"
assert_contains "$(cat "$PFLOG/testhost.$IA.jsonl")" '"seat": "", "by": ""' "seat-less and spawned by no one"
run "$SMINOS" list
assert_equals "$(events_of "$IA")" "joined " "reconciliation is idempotent: a second list joins nothing"
run_in "$TEST_ROOT/nowhere" "$SMINOS" list
assert_contains "$OUT" "pfdemo" "from a directory that is no project, list shows every project"
pf_peer outsider 1c000003-0000-4000-8000-00000000001c idle derived "$TEST_ROOT/nowhere"
run "$SMINOS" list --all
assert_not_contains "$OUT" "outsider" "a session in no project is in no family"
rm -f "$HOME/.claude/sessions/pf-outsider.json"
# An internal fork (derive's headless run) is never a member.
pf_peer forked 1d000004-0000-4000-8000-00000000001d idle derived "$R" "$$"
mkdir -p "$SMINOS_HOME/internal"; : > "$SMINOS_HOME/internal/$$"
run "$SMINOS" list
assert_not_contains "$OUT" "forked" "a session whose pid is marked internal is not listed"
assert_file_absent "$PFLOG/testhost.1d000004-0000-4000-8000-00000000001d.jsonl" "and never joined"
rm -f "$SMINOS_HOME/internal/$$" "$HOME/.claude/sessions/pf-forked.json"
# A session running before the log existed: a seat record with no membership event.
OLDS=1e000005-0000-4000-8000-00000000001e
printf '{"uuid":"%s","current":"%s","alias":"oldtimer","group":"pf-repo","status":"idle","cwd":"%s","role":"keeper"}' \
  "$OLDS" "$OLDS" "$R" > "$SMINOS_HOME/$OLDS.json"
chmod 600 "$SMINOS_HOME/$OLDS.json"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/pl-proj/$OLDS.jsonl"   # stopped: its transcript is here
run "$SMINOS" list
assert_contains "$OUT" "oldtimer" "a seat that predates the log lists"
assert_equals "$(events_of "$OLDS")" "joined " "and is joined on the first list"
assert_contains "$(cat "$PFLOG/testhost.$OLDS.jsonl")" "\"role\": \"keeper\", \"seat\": \"$OLDS\", \"by\": \"\"" "with its seat and role"

# Acceptance 4: a spawn records its spawner; retiring the spawner leaves the
# spawned seat live; aliases collide and #short tells them apart.
nb=$(grep -c -- '--bg' "$STUB_STATE/log/calls.log" || true)
run "$SMINOS" spawn pc t --parent ia
assert_rc 2 "$RC" "spawn --parent is refused as an unknown argument"
run "$SMINOS" spawn pc t --group pfdemo
assert_rc 2 "$RC" "so is spawn --group"
assert_equals "$(grep -c -- '--bg' "$STUB_STATE/log/calls.log" || true)" "$nb" "nothing is launched for either"
CLAUDE_CODE_SESSION_ID="$IA" run "$SMINOS" spawn pc "wait for instructions" --brief "owns the parser"
assert_rc 0 "$RC" "a member spawns a sibling"
PC="$(banner_uuid "$OUT")"
assert_equals "$(events_of "$PC")" "joined in-charge " "the spawn records joined, then the brief as its in-charge line"
assert_contains "$(cat "$PFLOG/testhost.$PC.jsonl")" "\"seat\": \"$PC\", \"by\": \"ia\"" "joined carries the seat and the spawner"
assert_contains "$(cat "$PFLOG/testhost.$PC.jsonl")" '"text": "owns the parser", "source": "set"' "the brief is a set in-charge line"
assert_equals "$(field "$PC" parent)" "" "the seat records no parent"
pf_peer pc "$PC" idle seat
run "$SMINOS" list
assert_contains "$OUT" "owns the parser" "list shows the in-charge line"
assert_contains "$OUT" "· by ia" "and the provenance"
assert_equals "$(json_row pc charge_source)" "set" "list --json carries the charge's source"
assert_equals "$(json_row pc by)" "ia" "and the spawner"
assert_equals "$(json_row pc seat | python3 -c 'import json,sys; print(json.load(sys.stdin)["seat_id"])')" "$PC" "and the seat"
assert_equals "$(json_row ia seat)" "null" "a seat-less member carries no seat"
assert_equals "$(json_row ia machine)" "testhost" "every row names its machine"
printf 'short=1a00001a\nuuid=%s\nname=ia\nkind=interactive\nstate=\nstatus=idle\ncwd=%s\n' "$IA" "$R" > "$STUB_STATE/agents/1a00001a"
run "$SMINOS" retire ia
assert_rc 0 "$RC" "retire takes a seat-less member"
assert_contains "$(tail -3 "$STUB_STATE/log/calls.log")" "stop 1a00001a" "and stops its session"
assert_equals "$(events_of "$IA")" "joined retired:retire " "recording retired in its own file"
rm -f "$HOME/.claude/sessions/pf-ia.json" "$STUB_STATE/agents/1a00001a"   # the stopped session exits
run "$SMINOS" list
assert_not_contains "$OUT" "  ia " "a retired seat-less session leaves the family"
assert_equals "$(json_row pc state)" "idle" "retiring the spawner leaves the spawned seat live"
IC=1f000006-0000-4000-8000-00000000001f
mkdir -p "$TEST_ROOT/pf-other-cwd"
start_inbox pc2
printf '{"pid":%s,"sessionId":"%s","name":"pc","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$IC" "$R" "$TEST_ROOT/in-pc2.sock" > "$HOME/.claude/sessions/pf-pc2.json"
run "$SMINOS" list
assert_contains "$OUT" "pc#${PC:0:8}" "two members sharing an alias list as alias#short"
assert_contains "$OUT" "pc#${IC:0:8}" "both of them"
run "$SMINOS" say "@pc hi"
assert_rc 4 "$RC" "a tag both answer to is refused"
assert_contains "$OUT" "pc#${PC:0:8}" "naming the seat"
assert_contains "$OUT" "pc#${IC:0:8}" "and the session"
run "$SMINOS" say "@pc#${IC:0:4} only you"
assert_rc 0 "$RC" "#short picks one"
assert_contains "$(inbox pc2)" "only you" "and delivers to a seat-less member over its socket"
rm -f "$HOME/.claude/sessions/pf-pc2.json"

# Occupancy: a fresh fill displaces; a resume of a retired seat re-joins.
run "$SMINOS" retire pc
assert_rc 0 "$RC" "retire a seat"
assert_equals "$(events_of "$PC")" "joined in-charge retired:retire " "retire records retired"
run "$SMINOS" list
run "$SMINOS" daemon tick
assert_rc 0 "$RC" "a daemon tick runs over the project"
run "$SMINOS" list
run "$SMINOS" daemon tick
assert_equals "$(events_of "$PC")" "joined in-charge retired:retire " "a retired seat stays retired across repeated lists and ticks, though its session still answers"
run "$SMINOS" list
assert_not_contains "$OUT" "  pc " "and is folded away"
rm -f "$HOME/.claude/sessions/pf-pc.json"
run "$SMINOS" fill pc "again"
assert_rc 0 "$RC" "a fresh fill of the retired seat"
PC2="$(field "$PC" current)"
assert_equals "$(events_of "$PC")" "joined in-charge retired:retire retired:replaced " "the displaced session is retired as replaced"
assert_equals "$(events_of "$PC2")" "joined in-charge " "the new one joins (the seat's brief stays its line)"
assert_equals "$(python3 -c 'import json,sys
a = json.loads(open(sys.argv[1]).read().splitlines()[-1])["ts"]; b = json.loads(open(sys.argv[2]).readline())["ts"]
print(a <= b)' "$PFLOG/testhost.$PC.jsonl" "$PFLOG/testhost.$PC2.jsonl")" "True" "retired (replaced) is written before joined"
run "$SMINOS" retire pc
run "$SMINOS" fill pc "continue" --resume
assert_rc 0 "$RC" "fill --resume of the retired seat"
assert_equals "$(field "$PC" current)" "$PC2" "keeps its session"
assert_equals "$(events_of "$PC2")" "joined in-charge retired:retire joined " "and re-joins it under the same uuid"
run "$SMINOS" list
assert_contains "$OUT" "pc" "the revived seat lists again"
# seat add records joined; remove records retired.
SAS=2a000007-0000-4000-8000-00000000002a
run "$SMINOS" seat add pf-repo added --session "$SAS"
assert_rc 0 "$RC" "seat add registers a session"
assert_equals "$OUT" "seat pf-repo/added added (session: $SAS)" "naming no parent"
assert_equals "$(events_of "$SAS")" "joined " "seat add records joined"
run "$SMINOS" seat add pf-repo added --parent pc
assert_rc 2 "$RC" "seat add --parent is gone"
run "$SMINOS" remove pf-repo/added
assert_equals "$(events_of "$SAS")" "joined retired:retire " "remove records retired"

# Lifecycle order is by seq within the session's own file, never by ts: the
# hook's joined at session start, then an operator retire and a resume under
# a clock stepped back.
HK=2b000008-0000-4000-8000-00000000002b
printf '{"uuid":"%s","current":"%s","alias":"hk","group":"pf-repo","status":"idle","cwd":"%s"}' \
  "$HK" "$HK" "$R" > "$SMINOS_HOME/$HK.json"
chmod 600 "$SMINOS_HOME/$HK.json"
printf '{"type":"user"}\n' > "$HOME/.claude/projects/pl-proj/$HK.jsonl"
hook_run SessionStart "$HK" "$R" "$HOME/.claude/projects/pl-proj/$HK.jsonl" startup
assert_equals "$(events_of "$HK")" "joined " "the hook joins a seat's session at its start, at the real time"
CLOCK="$(python3 - "$SMINOS_PY" "$PF" "$HK" 2>&1 <<'PY_CLOCK'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p, hk = mod.find_project(sys.argv[2]), sys.argv[3]
joined = hk in {m.session for m in mod.members(p)}        # the joined of the hook stands; nothing is reconciled
real_now = mod.now
mod.now = lambda ms=False: "2001-01-01T00:00:00.000Z" if ms else real_now(ms)   # the clock steps back
mod.main(["retire", hk])
retired = hk not in {m.session for m in mod.members(p)}
mod.main(["fill", hk, "back", "--resume"])
rejoined = hk in {m.session for m in mod.members(p)}
mod.now = real_now
mod.main(["status", hk, "first"])
mod.lifecycle(p, hk, "in-charge", text="first line", source="set")
mod.now = lambda ms=False: "2001-01-01T00:00:00.000Z" if ms else real_now(ms)
mod.main(["status", hk, "second"])
mod.lifecycle(p, hk, "in-charge", text="second line", source="set")
m = next(x for x in mod.members(p) if x.session == hk)
print(m.status, m.charge)
print(joined, retired, rejoined)
PY_CLOCK
)"
assert_equals "$(printf '%s\n' "$CLOCK" | tail -1)" "True True True" "joined, retired, re-joined in seq order though the later two carry earlier ts"
assert_equals "$(printf '%s\n' "$CLOCK" | tail -2 | head -1)" "second second line" "a writer's later status and in-charge line win by seq, though they carry an earlier ts"
assert_equals "$(events_of "$HK" | cut -d' ' -f1-3)" "joined retired:retire joined" "the hook's joined is the first of the session's own sequence"

# Reach is the project: a name resolves in the working directory's project;
# from no project, across every project known here.
run_in "$TEST_ROOT/nowhere" "$SMINOS" say "@ib from nowhere"
assert_rc 0 "$RC" "from no project, a name resolves across the projects known here"
assert_contains "$OUT" "in pfdemo" "into the project that holds it"
assert_contains "$(inbox ib)" "from nowhere" "and delivers"
P4="$TEST_ROOT/pf-second"
mkdir -p "$P4"
gitq init -q "$P4"
(cd "$P4" && "$SMINOS" seat add pf-second ib --session 2c000009-0000-4000-8000-00000000002c >/dev/null)
run_in "$TEST_ROOT/nowhere" "$SMINOS" say "@ib which one"
assert_rc 4 "$RC" "a name two projects hold is refused from no project"
assert_contains "$OUT" "pfdemo/ib#${IB:0:8}" "naming each with its project"
assert_contains "$OUT" "pf-second/ib#2c000009" "both"
run "$SMINOS" say "@ib in my project"
assert_rc 0 "$RC" "inside a project the same name resolves in it"
run "$SMINOS" send ib "direct to a session"
assert_rc 0 "$RC" "send reaches a seat-less member"
assert_contains "$OUT" "sent to ib" "and says so"
assert_contains "$(inbox ib)" "[sminos message from human id=" "with send's own frame, over its socket"
assert_contains "$(tail -1 "$PFLOG/testhost.human.jsonl")" "\"session\": \"$IB\"" "recorded to its session"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["testhost/human"]["settled"])' "$SMINOS_HOME/projects/$PF/delivered/$IB.json")" \
  "$(tail -1 "$PFLOG/testhost.human.jsonl" | python3 -c 'import json,sys; print(json.load(sys.stdin)["seq"])')" "and settled in its delivery record"
run "$SMINOS" send ib "x" --wait
assert_rc 2 "$RC" "send --wait to a seat-less member is refused: there is no record to watch"
CLAUDE_CODE_SESSION_ID="$IB" run "$SMINOS" status ib "reading the schema"
assert_rc 0 "$RC" "a seat-less member sets its status"
assert_contains "$(tail -1 "$PFLOG/testhost.$IB.jsonl")" '"kind": "status"' "as a status event in its own file"
run "$SMINOS" status pc "parsing"
assert_contains "$(tail -1 "$PFLOG/testhost.$PC2.jsonl")" '"kind": "status", "session": "'"$PC2"'", "text": "parsing"' "a seat's status is an event too"
assert_equals "$(field "$PC" now)" "parsing" "beside the local now line"
run "$SMINOS" list
assert_contains "$OUT" "· now: reading the schema" "list shows a member's status"

# A status set in one home reaching the other's list is pinned through the
# real mirror, in "the mirror and the daemon".

# A seat-less member's membership ends with its process, as it began with it:
# the next reading verb retires it (reason ended) and it re-joins when it runs
# again. Only interactive and bg sessions are members on sight.
IE=2d00000d-0000-4000-8000-00000000002d
pf_peer closer "$IE" idle user
run "$SMINOS" list
assert_contains "$OUT" "closer" "a live interactive session lists"
rm -f "$HOME/.claude/sessions/pf-closer.json"   # its session exits
run "$SMINOS" list
assert_not_contains "$OUT" "closer" "once its session exits, the next reading verb ends its membership"
assert_equals "$(events_of "$IE")" "joined retired:ended " "recording retired, reason ended, in its own file"
assert_contains "$(tail -1 "$PFLOG/testhost.$IE.jsonl")" '"by": "", "reason": "ended"' "by no one"
run "$SMINOS" say "@closer are you there"
assert_rc 4 "$RC" "a tag to it while it is closed is refused"
assert_contains "$OUT" "@closer: closer's session ended; say it untagged to leave a note" "saying its session ended and how to leave it a note"
pf_peer closer "$IE" idle user                  # resumed outside sminos
run "$SMINOS" list
assert_contains "$OUT" "closer" "when it runs again it lists again"
assert_equals "$(events_of "$IE")" "joined retired:ended joined " "re-joined under the same uuid"
rm -f "$HOME/.claude/sessions/pf-closer.json"
HL=2e00000e-0000-4000-8000-00000000002e
start_inbox headless
printf '{"pid":%s,"sessionId":"%s","name":"headless","kind":"sdk","status":"busy","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$HL" "$R" "$TEST_ROOT/in-headless.sock" > "$HOME/.claude/sessions/pf-headless.json"
run "$SMINOS" list
assert_not_contains "$OUT" "headless" "a session of another kind (a tool's headless run) is not a member on sight"
assert_file_absent "$PFLOG/testhost.$HL.jsonl" "and is never joined"
rm -f "$HOME/.claude/sessions/pf-headless.json"

# A seat and a seat-less session that share an alias: every member verb
# refuses the name as ambiguous, as a tag is refused, and #short picks one.
DS=2f00000f-0000-4000-8000-00000000002f
DL=3a000010-0000-4000-8000-00000000003a
run "$SMINOS" seat add pf-repo dupe --session "$DS"
pf_peer dupe "$DL" idle user
# A project qualifier, by name or by id, resolves the same way: only a full id
# or a group qualifier that is no project names a seat directly.
for name in dupe pfdemo/dupe "$PF/dupe"; do
  for verb in "send $name hi" "status $name busy" "retire $name"; do
    run "$SMINOS" $verb
    assert_rc 4 "$RC" "$verb: a name a seat and a seat-less session share is refused"
    assert_contains "$OUT" "pf-repo/dupe" "$verb: naming the seat"
    assert_contains "$OUT" "dupe#${DL:0:8}" "$verb: and the session"
  done
done
assert_not_contains "$(field "$DS" status)" "retired" "the refused retires touched nothing"
run "$SMINOS" status pf-repo/dupe "the seat's"
assert_rc 0 "$RC" "a group qualifier that is no project names the seat directly"
run "$SMINOS" status "$DS" "the seat's, by id"
assert_rc 0 "$RC" "and so does its full id"
run "$SMINOS" send "dupe#${DL:0:4}" "the session one"
assert_rc 0 "$RC" "alias#short picks the seat-less one"
assert_contains "$(inbox dupe)" "the session one" "and reaches it"
rm -f "$HOME/.claude/sessions/pf-dupe.json"
"$SMINOS" remove pf-repo/dupe >/dev/null
# A fan-out resume that launched stands, though its re-join cannot be recorded:
# the frame settles, a warning says what failed, and the next recipient is
# still delivered.
STP=4c000018-0000-4000-8000-00000000004c
"$SMINOS" seat add pf-repo stp --session "$STP" >/dev/null
printf '{"type":"user"}\n' > "$HOME/.claude/projects/pl-proj/$STP.jsonl"   # stopped: its transcript is here
: > "$TEST_ROOT/in-ib.received"
chmod 400 "$PFLOG/testhost.$STP.jsonl"
run "$SMINOS" say "@stp @ib wake both"
chmod 600 "$PFLOG/testhost.$STP.jsonl"
assert_rc 0 "$RC" "a say whose resumed recipient cannot be re-joined in the log still completes"
assert_contains "$OUT" "stp: woken" "the resume launched with the frame"
assert_contains "$OUT" "pf-repo/stp was resumed with the message, but recording joined of ${STP:0:8}" "a warning names the failed re-join"
assert_contains "$OUT" "ib: sent" "the fan-out goes on to the next recipient"
assert_contains "$(inbox ib)" "wake both" "which is delivered"
assert_equals "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["testhost/human"]["settled"])' "$SMINOS_HOME/projects/$PF/delivered/$STP.json")" \
  "$(tail -1 "$PFLOG/testhost.human.jsonl" | python3 -c 'import json,sys; print(json.load(sys.stdin)["seq"])')" "the launched frame is settled, never pushed again"
"$SMINOS" remove pf-repo/stp >/dev/null
# send and status reconcile the project before they resolve: a session no
# reading verb has seen yet is joined, then reached.
FR=3b000011-0000-4000-8000-00000000003b
pf_peer fresh "$FR" idle user
run "$SMINOS" send fresh "first contact"
assert_rc 0 "$RC" "a send before any list reaches a session that just opened"
assert_equals "$(events_of "$FR")" "joined " "joining it first"
FR2=3c000012-0000-4000-8000-00000000003c
pf_peer fresh2 "$FR2" idle user
CLAUDE_CODE_SESSION_ID="$FR2" run "$SMINOS" status fresh2 "starting"
assert_rc 0 "$RC" "so does a status"
assert_equals "$(events_of "$FR2")" "joined status " "joined before its status is recorded"
rm -f "$HOME/.claude/sessions/pf-fresh.json" "$HOME/.claude/sessions/pf-fresh2.json"
# From inside a project a bare name never reaches past it, recorded or not.
FA=3d000013-0000-4000-8000-00000000003d
pf_peer faraway "$FA" idle user "$P4"
run "$SMINOS" send faraway "across"
assert_rc 4 "$RC" "a bare name of another project's live session is refused"
assert_contains "$OUT" "<project>/faraway" "pointing at the qualified name"
assert_equals "$(inbox faraway)" "" "and nothing is sent"
run "$SMINOS" send pf-second/faraway "across, qualified"
assert_rc 0 "$RC" "the qualified name reaches it"
assert_contains "$(log_of local-pf-second)" "across, qualified" "recorded in its project's log"
rm -f "$HOME/.claude/sessions/pf-faraway.json"
# Membership follows the process, not the inbox: a running session whose
# socket does not answer stays a member.
MU=3e000014-0000-4000-8000-00000000003e
printf '{"pid":%s,"sessionId":"%s","name":"mute","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s/no-such.sock"}\n' \
  "$SOCK_PID" "$MU" "$R" "$TEST_ROOT" > "$HOME/.claude/sessions/pf-mute.json"
run "$SMINOS" list
assert_contains "$OUT" "mute" "a running session whose inbox does not answer joins"
run "$SMINOS" list
assert_contains "$OUT" "mute" "and stays a member"
assert_equals "$(events_of "$MU")" "joined " "with no retired (ended) for an unanswering inbox"
rm -f "$HOME/.claude/sessions/pf-mute.json"
run "$SMINOS" list   # its process is gone now: its membership ends

# The chart and the tui draw what list prints (§7): the in-charge line,
# `now:` the status, `by` the spawner, and a remote member's @machine age.
CLAUDE_CODE_SESSION_ID="$IB" run "$SMINOS" spawn helper "t" --brief "helps the parser"
HELPER="$(banner_uuid "$OUT")"
"$SMINOS" status helper "drafting" >/dev/null
pf_peer helper "$HELPER" idle seat
FAR=3f000015-0000-4000-8000-00000000003f
python3 - "$PFLOG/h2.$FAR.jsonl" "$FAR" <<'PY_FAR'
import datetime, json, sys
t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=3)
ts = t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000)
w, s = "h2/" + sys.argv[2], sys.argv[2]
with open(sys.argv[1], "w") as f:
    f.write(json.dumps({"ts": "2026-01-01T00:00:00.000Z", "writer": w, "seq": 1, "kind": "joined", "session": s,
                        "alias": "far", "name_source": "user", "machine": "h2", "cwd": "/elsewhere", "worktree": "",
                        "role": "", "seat": "", "by": ""}) + "\n")
    f.write(json.dumps({"ts": ts, "writer": w, "seq": 2, "kind": "state", "session": s, "state": "idle",
                        "machine": "h2"}) + "\n")
PY_FAR
run "$SMINOS" chart pfdemo --width 200
assert_contains "$OUT" "helps the parser" "a chart box carries the in-charge line"
assert_contains "$OUT" "now: drafting · by ib" "then now: the status and by the spawner"
assert_contains "$OUT" "○ idle @h2 3m" "a remote member's word carries its machine and age"
run "$SMINOS" tui pfdemo --headless --width 200 --height 90 --keys "!focus:pfdemo/helper"
assert_contains "$OUT" "now: drafting · by ib" "the tui draws the same boxes"
run "$SMINOS" tui pfdemo --headless --width 200 --height 90 --keys "!focus:pfdemo/far"
assert_contains "$OUT" "○ idle @h2 3m" "with the remote member's machine and age"
run "$SMINOS" tui pfdemo --headless --width 200 --height 90 --keys "!focus:pfdemo/far,enter"
assert_contains "$OUT" "far is on h2 — attach to it there" "enter on a remote member says where it runs"
# Enter attaches to a seat-less local member when the harness offers an
# attachable session, and says why not otherwise.
BG=4a000016-0000-4000-8000-00000000004a
start_inbox bgone
printf '{"pid":%s,"sessionId":"%s","name":"bgone","kind":"bg","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$BG" "$R" "$TEST_ROOT/in-bgone.sock" > "$HOME/.claude/sessions/pf-bgone.json"
{ echo "short=bb00b001"; echo "uuid=$BG"; echo "name=bgone"; echo "kind=background"; echo "state=working"; echo "status=idle"; echo "cwd=$R"; } > "$STUB_STATE/agents/bb00b001"
run "$SMINOS" tui pfdemo --headless --width 200 --height 90 --keys "!focus:pfdemo/bgone,enter"
assert_contains "$OUT" "attach pfdemo/bgone bb00b001 → claude attach bb00b001" "enter attaches to a seat-less member the harness can attach to"
run "$SMINOS" tui pfdemo --headless --width 200 --height 90 --keys "!focus:pfdemo/ib,enter"
assert_contains "$OUT" "ib holds no seat, and the harness offers no session to attach to" "and says why it cannot, for an interactive terminal's"
rm -f "$HOME/.claude/sessions/pf-bgone.json" "$STUB_STATE/agents/bb00b001" "$PFLOG/h2.$FAR.jsonl"

# A lifecycle event is part of its verb: a failed append exits 1, saying the
# local operation completed and the log write failed.
RFS=4b000017-0000-4000-8000-00000000004b
"$SMINOS" seat add pf-repo rfail --session "$RFS" >/dev/null
chmod 400 "$PFLOG/testhost.$RFS.jsonl"
run "$SMINOS" retire pf-repo/rfail
chmod 600 "$PFLOG/testhost.$RFS.jsonl"
assert_rc 1 "$RC" "a retire whose event cannot be recorded exits 1"
assert_contains "$OUT" "retire completed, but recording retired of ${RFS:0:8} in pfdemo's log failed" "saying the retire happened and the log write did not"
assert_equals "$(field "$RFS" status)" "retired" "the local retire stands"
chmod 500 "$PFLOG"
run "$SMINOS" spawn sfail "t"
chmod 700 "$PFLOG"
assert_rc 0 "$RC" "a spawn whose joined cannot be recorded still exits 0: its worker runs, and a dispatcher must not release it"
assert_contains "$OUT" "seat spawned: pf-repo/sfail" "its banner names the seat it launched"
assert_contains "$OUT" "sminos: warning: spawn completed, but recording joined of" "a loud warning says the log write failed"
assert_contains "$OUT" "but its spawner (by the operator) is not recorded" "naming what the failed event loses"
assert_not_contains "$OUT" "in-charge" "and nothing it does not: the spawn had no brief to record"
run "$SMINOS" list --json
assert_contains "$OUT" '"alias": "sfail"' "reconciliation repairs the membership on the next reading verb"
assert_contains "$(head -1 "$PFLOG/testhost.$(field "$(seat_id_of sfail)" current).jsonl")" '"kind": "joined"' "joining it into the log"
cd "$WORK"
rm -f "$HOME/.claude/sessions/pf-"*.json

# ---- messages to the host and the in-charge line --------------------------------
# A session's <message> marks and async asks reach the project's log through
# the Stop / SessionStart hook (§4); every member has one in-charge line, set,
# named, derived by a headless internal fork, or the transcript's title (§5).
echo "messages to the host and the in-charge line:"
export SMINOS_HOME="$TEST_ROOT/hp-registry"
mkdir -m 700 "$SMINOS_HOME"
rm -f "$HOME/.claude/sessions/"*.json
unset CLAUDE_CODE_SESSION_ID
R3="$TEST_ROOT/hp-repo"
mkdir -p "$R3"
gitq init -q "$R3"
(cd "$R3" && "$SMINOS" project init --name hostdemo >/dev/null)
HP="$(smns_id "$R3")"
HPLOG="$SMINOS_HOME/projects/$HP/log"
TXD="$HOME/.claude/projects/hp-proj"
mkdir -p "$TXD"
cd "$R3"

# The mark grammar is the to-human mod's, ported: its own parse fixtures pin it.
while IFS= read -r line; do
  case "$line" in
    "ok "*) pass "mark parity: ${line#ok }" ;;
    *) fail "mark parity: ${line#FAIL }" ;;
  esac
done < <(python3 "$SCRIPT_DIR/marks_parity.py" "$REPO_ROOT/skills/sminos/scripts" 2>&1)

# Transcript records as the harness stores them (the shapes the ask design and
# a live 2.1.296 transcript record).
cat > "$TEST_ROOT/tx.py" <<'PY_TX'
import json, sys
ASK = "mcp__doperpowers__AskUserQuestion"
ASYNC_RESULT = ("Your questions are waiting for the human; this call does not wait for them. Their answer will "
                "reach you in a later message that quotes each question. Go on with work that does not depend on it.")
HEAD = "The human responded to your async AskUserQuestion (call %s): %s"
path, kind, args = sys.argv[1], sys.argv[2], sys.argv[3:]
base = {"isSidechain": False, "uuid": args[0] if args else ""}
if kind == "prompt":
    rec = {"type": "user", "origin": {"kind": "human"}, "message": {"role": "user", "content": args[1]}}
elif kind == "asst":
    rec = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": args[1]}]}}
elif kind == "peer":
    rec = {"type": "user", "origin": {"kind": "peer", "name": "other"}, "message": {"role": "user", "content":
           '<cross-session-message from="uds:/tmp/x.sock" from-name="other">\n%s\n</cross-session-message>' % args[1]}}
elif kind == "ask":   # uuid call async|blocking|native questions-json
    inp = {"questions": json.loads(args[3])}
    if args[2] != "native":
        inp["async"] = args[2] == "async"
    rec = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": args[1], "name": "AskUserQuestion" if args[2] == "native" else ASK, "input": inp}]}}
elif kind == "result":   # uuid call text|ASYNC
    rec = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": args[1], "content": ASYNC_RESULT if args[2] == "ASYNC" else args[2]}]}}
elif kind == "deliver-att":
    rec = {"type": "attachment", "attachment": {"type": "hook_additional_context", "content": [HEAD % (args[1], args[2])],
                                                "hookName": "tool.call", "hookEvent": "PostToolUse"}}
elif kind == "deliver-prompt":
    rec = {"type": "user", "origin": {"kind": "plugin", "name": "doperpowers"}, "message": {"role": "user", "content":
           "The doperpowers plugin sent a message:\n" + HEAD % (args[1], args[2]) + "\n\nThis is how Claude Code "
           "surfaces a prompt a plugin submits between turns — it starts this turn in the user's place. "
           "Address the message above."}}
elif kind == "title":
    rec, base = {"type": "ai-title", "aiTitle": args[0]}, {}
elif kind == "sidechain":
    rec = {"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "content": [{"type": "text", "text": args[1]}]}}
    base.pop("isSidechain")
else:
    sys.exit("tx.py: unknown kind " + kind)
with open(path, "a") as f:
    f.write(json.dumps({**base, **rec}, ensure_ascii=False) + "\n")
PY_TX
tx() { python3 "$TEST_ROOT/tx.py" "$@"; }
hp_peer() { # name session nameSource kind — a running harness session in the project
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"%s","kind":"%s","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
    "$SOCK_PID" "$2" "$1" "$3" "$4" "$R3" "$TEST_ROOT/in-$1.sock" > "$HOME/.claude/sessions/hp-$1.json"
}
hp_events() { # session → "kind[:src]" words from its own writer file
  python3 -c 'import json, sys
for l in open(sys.argv[1]):
    e = json.loads(l)
    print(e["kind"] + (":" + e["src"] if e.get("src") else ""), end=" ")' "$HPLOG/testhost.$1.jsonl" 2>/dev/null || true
}
host_count() { "$SMINOS" chat hostdemo --host --json 2>/dev/null | grep -c '"kind"' || true; }

if python3 - "$REPO_ROOT/hooks/hooks.json" <<'PY_WIRED'
import json, sys
hooks = json.load(open(sys.argv[1]))["hooks"]
def wired(event, matcher=None):
    return any("smns-record.sh" in h["command"] and (matcher is None or e.get("matcher") == matcher)
               for e in hooks.get(event, []) for h in e["hooks"])
assert wired("SessionStart", "startup|resume|clear|fork") and wired("Stop")
PY_WIRED
then pass "hooks.json runs the hook on Stop and on SessionStart (startup|resume|clear|fork)"
else fail "hooks.json runs the hook on Stop and on SessionStart (startup|resume|clear|fork)"; fi

# A session starts: the hook joins it and sets its export position at the
# transcript's start (the file does not exist yet).
HA=5a000001-0000-4000-8000-00000000005a
TA="$TXD/$HA.jsonl"
hp_peer ha "$HA" user interactive
hook_run SessionStart "$HA" "$R3" "$TA" startup
assert_equals "$(hp_events "$HA")" "joined " "the hook joins a session at its start"
assert_contains "$(cat "$HPLOG/testhost.$HA.jsonl")" '"alias": "ha", "name_source": "user"' "under its harness name"
assert_file_exists "$SMINOS_HOME/projects/$HP/cursors/export/$HA.json" "and initialises its export position"
assert_rc 0 "$HOOK_RC" "the hook exits 0"
assert_equals "$HOOK_OUT" "" "and prints nothing: a SessionStart hook's output would be read as context"

# One turn: marks in every form the grammar knows, a peer frame mid-turn.
tx "$TA" prompt a1000001 "parse it"
tx "$TA" asst a1000002 'Reading.
<message>done with the parser</message>
And `<message>not this</message>` is an example.'
tx "$TA" asst a1000003 'An example:
```
<message>fenced, not sent</message>
```
<to-human>an old mark</to-human>'
tx "$TA" peer a1000004 "your change renames a column I read"
tx "$TA" asst a1000005 '<message>outer <insight>inner</insight> tail</message>
<message>left open to the end'
tx "$TA" sidechain a1000006 '<message>a subagent writes this</message>'
hook_run Stop "$HA" "$R3" "$TA"
assert_equals "$(hp_events "$HA")" "joined message:a1000002#0 message:a1000003#0 message:a1000005#0 message:a1000005#1 message:a1000005#2 message:a1000005#3 " \
  "Stop records each span as a message, src record uuid and span index; marks after a peer frame too"
run "$SMINOS" chat hostdemo --host
assert_rc 0 "$RC" "chat --host exits 0"
assert_contains "$OUT" "ha: done with the parser" "chat --host prints the message attributed to its session"
assert_not_contains "$OUT" "not this" "a backticked tag is not a message to the host"
assert_not_contains "$OUT" "fenced, not sent" "nor a fenced one"
assert_contains "$OUT" "ha: an old mark" "an old <to-human> mark records as a message"
assert_contains "$OUT" "ha: inner" "a nested alias mark is a run of its own"
assert_contains "$OUT" "ha: tail" "and the outer mark resumes after it"
assert_contains "$OUT" "ha: left open to the end" "an unclosed mark runs to the end of the text"
assert_not_contains "$OUT" "a subagent writes this" "a sidechain record is not the session's"
assert_contains "$(cat "$HPLOG/testhost.$HA.jsonl")" '"kind": "message", "from": "ha", "to": "host", "text": "done with the parser", "src": "a1000002#0"' \
  "a message event carries from, to host, text, and src"
BEFORE="$(hp_events "$HA")"
hook_run Stop "$HA" "$R3" "$TA"
assert_equals "$(hp_events "$HA")" "$BEFORE" "a Stop replayed over the same transcript appends nothing"
run "$SMINOS" chat hostdemo
assert_not_contains "$OUT" "done with the parser" "the chat itself carries no host message"

# Asks: an async ask records a question with its labels; its delivery records
# the answer under the same src; a blocking ask, plugin or native, records nothing.
Q1='[{"question":"Which backend?","header":"Backend","multiSelect":false,"options":[{"label":"Postgres","description":"running"},{"label":"SQLite","description":"a file"}]}]'
tx "$TA" prompt a2000001 "ask me"
tx "$TA" ask a2000002 toolu_async1 async "$Q1"
tx "$TA" result a2000003 toolu_async1 ASYNC
tx "$TA" ask a2000004 toolu_block1 blocking "$Q1"
tx "$TA" result a2000005 toolu_block1 'Your questions have been answered: "Which backend?"="SQLite". You can now continue with these answers in mind.'
tx "$TA" ask a2000006 toolu_native native "$Q1"
tx "$TA" result a2000007 toolu_native 'User has answered your questions: "Which backend?"="Postgres".'
tx "$TA" ask a2000008 toolu_refused async '[{"question":"Pick?","header":"P","multiSelect":false,"options":[{"label":"Only","description":""}]}]'
tx "$TA" result a2000009 toolu_refused '<tool_use_error>a question with fewer than 2 options</tool_use_error>'
tx "$TA" asst a200000a "Asked; going on."
hook_run Stop "$HA" "$R3" "$TA"
assert_contains "$(hp_events "$HA")" "question:toolu_async1 " "an async ask the tool accepted records a question, src its call id"
assert_not_contains "$(hp_events "$HA")" "toolu_block1" "a blocking ask records nothing"
assert_not_contains "$(hp_events "$HA")" "toolu_native" "nor the native AskUserQuestion"
assert_not_contains "$(hp_events "$HA")" "toolu_refused" "nor an async call the tool refused"
assert_contains "$(grep toolu_async1 "$HPLOG/testhost.$HA.jsonl")" '"text": ["Which backend?"], "choices": ["Postgres", "SQLite"]' \
  "the question carries its text and its option labels"
run "$SMINOS" chat hostdemo --host
assert_contains "$OUT" "ha asks (open): Which backend?" "chat --host shows the question, open"
assert_contains "$OUT" "Postgres · SQLite" "with both labels"
tx "$TA" prompt a3000001 "later"
tx "$TA" deliver-att a3000002 toolu_async1 'Your questions have been answered: "Which backend?"="SQLite". You can now continue with these answers in mind.'
tx "$TA" asst a3000003 "Taking SQLite."
hook_run Stop "$HA" "$R3" "$TA"
assert_contains "$(hp_events "$HA")" "question:toolu_async1 " "the question stays"
assert_contains "$(hp_events "$HA")" "answered:toolu_async1 " "its delivery records answered with the same src"
assert_contains "$(grep '"kind": "answered"' "$HPLOG/testhost.$HA.jsonl")" '"from": "ha", "src": "toolu_async1", "text": "Your questions have been answered: \"Which backend?\"=\"SQLite\". You can now continue with these answers in mind."' \
  "carrying the engine's result text"
run "$SMINOS" chat hostdemo --host
assert_contains "$OUT" "ha asks: Which backend?" "an answered question is no longer open"
assert_contains "$OUT" '    answered: Your questions have been answered: "Which backend?"="SQLite".' "and its answer stands under it"
# A delivery the plugin submitted as a prompt, framed by the engine.
tx "$TA" ask a3000004 toolu_async2 async "$Q1"
tx "$TA" result a3000005 toolu_async2 ASYNC
tx "$TA" asst a3000006 "Asked again."
tx "$TA" deliver-prompt a3000007 toolu_async2 'Your questions have been answered: "Which backend?"="Postgres". You can now continue with these answers in mind.'
tx "$TA" asst a3000008 "Taking Postgres."
hook_run Stop "$HA" "$R3" "$TA"
assert_contains "$(grep '"src": "toolu_async2"' "$HPLOG/testhost.$HA.jsonl" | grep answered)" '=\"Postgres\". You can now continue with these answers in mind."' \
  "a plugin-submitted delivery records its answer without the engine's framing"
assert_equals "$(grep -c 'This is how Claude Code' "$HPLOG/testhost.$HA.jsonl" || true)" "0" "the framing is not part of it"

# An export that died after the first of two spans in one record: the retry
# appends only the second.
tx "$TA" asst a4000001 '<message>first of two</message> <message>second of two</message>'
python3 - "$SMINOS_PY" "$HP" "$HA" <<'PY_HALF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
p, s = mod.find_project(sys.argv[2]), sys.argv[3]
mod.log_append_batch(p, mod.writer_id(s), [{"kind": "message", "from": "ha", "to": "host", "text": "first of two", "src": "a4000001#0"}])
PY_HALF
hook_run Stop "$HA" "$R3" "$TA"
assert_equals "$(grep -c '"src": "a4000001#0"' "$HPLOG/testhost.$HA.jsonl")" "1" "the span already recorded is not recorded again"
assert_equals "$(grep -c '"src": "a4000001#1"' "$HPLOG/testhost.$HA.jsonl")" "1" "and the one after it is recorded once"

# A mark written before the process died, never exported: a resume keeps the
# position, and the next Stop exports it once.
tx "$TA" asst a5000001 '<message>written before the crash</message>'
hook_run SessionStart "$HA" "$R3" "$TA" resume
assert_not_contains "$(cat "$HPLOG/testhost.$HA.jsonl")" "written before the crash" "a SessionStart exports nothing"
tx "$TA" prompt a5000002 "back"
tx "$TA" asst a5000003 "Resumed."
hook_run Stop "$HA" "$R3" "$TA"
assert_equals "$(grep -c 'written before the crash' "$HPLOG/testhost.$HA.jsonl")" "1" "the resumed session's next Stop exports it once"
hook_run Stop "$HA" "$R3" "$TA"
assert_equals "$(grep -c 'written before the crash' "$HPLOG/testhost.$HA.jsonl")" "1" "and never again"

# The hook never blocks a turn: with the export lock, or the log's lock for
# the session's file, held by a stalled process, it gives up in time, appends
# nothing, and keeps the position; the next Stop exports.
tx "$TA" asst a6000001 '<message>while a lock is held</message>'
POS="$SMINOS_HOME/projects/$HP/cursors/export/$HA.json"
POS_BEFORE="$(cat "$POS")"
for held in "export lock:$SMINOS_HOME/projects/$HP/cursors/export/$HA.lock" "log lock:$HPLOG/testhost.$HA.jsonl.lock"; do
  rm -f "$TEST_ROOT/held" "$TEST_ROOT/release"
  python3 - "${held#*:}" "$TEST_ROOT/held" "$TEST_ROOT/release" <<'PY_HOLD' & holder=$!
import fcntl, os, sys, time
with open(sys.argv[1], 'a') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    open(sys.argv[2], 'w').close()
    while not os.path.exists(sys.argv[3]):
        time.sleep(0.05)
PY_HOLD
  for _ in $(seq 1 100); do [ -f "$TEST_ROOT/held" ] && break; sleep .05; done
  t0=$(date +%s)
  SMNS_RECORD_TIMEOUT=1 hook_run Stop "$HA" "$R3" "$TA"
  elapsed=$(( $(date +%s) - t0 ))
  touch "$TEST_ROOT/release"; wait "$holder"
  assert_rc 0 "$HOOK_RC" "with the ${held%%:*} held, the hook exits 0"
  assert_equals "$(( elapsed < 4 ))" "1" "promptly (${elapsed}s for a 1s bound)"
  assert_not_contains "$(cat "$HPLOG/testhost.$HA.jsonl")" "while a lock is held" "appending nothing"
  assert_equals "$(cat "$POS")" "$POS_BEFORE" "and keeping the export position"
done
assert_contains "$(tail -1 "$SMINOS_HOME/daemon.log")" "record: gave up after 1s" "the give-up is a line in daemon.log"
# With migrate's lock held elsewhere, the hook neither migrates nor exports.
rm -f "$TEST_ROOT/held" "$TEST_ROOT/release"
python3 - "$HOME/.claude/.agora-migrate.lock" "$TEST_ROOT/held" "$TEST_ROOT/release" <<'PY_HOLD' & holder=$!
import fcntl, os, sys, time
with open(sys.argv[1], 'a') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    open(sys.argv[2], 'w').close()
    while not os.path.exists(sys.argv[3]):
        time.sleep(0.05)
PY_HOLD
for _ in $(seq 1 100); do [ -f "$TEST_ROOT/held" ] && break; sleep .05; done
t0=$(date +%s)
SMNS_RECORD_TIMEOUT=1 hook_run Stop "$HA" "$R3" "$TA"
elapsed=$(( $(date +%s) - t0 ))
touch "$TEST_ROOT/release"; wait "$holder"
assert_rc 0 "$HOOK_RC" "with migrate's lock held, the hook exits 0"
assert_equals "$(( elapsed < 4 ))" "1" "promptly (${elapsed}s for a 1s bound)"
assert_not_contains "$(cat "$HPLOG/testhost.$HA.jsonl")" "while a lock is held" "exporting nothing"
assert_equals "$(cat "$POS")" "$POS_BEFORE" "and keeping the export position"
assert_contains "$(tail -1 "$SMINOS_HOME/daemon.log")" "migrate's lock held elsewhere" "saying so in daemon.log"
# A migration step is never cut short: a colliding aside board merged by the
# hook, its merge outlasting the hook's bound, completes once and only once.
MG="$TEST_ROOT/mergehome"
mkdir -p "$MG/.claude/sessions" "$MG/sminos/groups/g1" "$MG/sminos.v2-20260101T000000Z/groups/g1"
chmod 700 "$MG/sminos"
printf '{"id":1,"ts":"t","from":"human","title":"","cwd":"/","branch":"","text":"root one"}\n' > "$MG/sminos/groups/g1/board.jsonl"
printf '{"id":1,"ts":"t","from":"human","title":"","cwd":"/","branch":"","text":"aside one"}\n{"id":2,"ts":"t","from":"human","title":"","cwd":"/","branch":"","text":"aside two"}\n' \
  > "$MG/sminos.v2-20260101T000000Z/groups/g1/board.jsonl"
HOME="$MG" SMINOS_HOME="$MG/sminos" SMNS_RECORD_TIMEOUT=0.2 SMINOS_TEST_MERGE_PAUSE=0.6 hook_run Stop "$HA" "$R3" "$TA"
assert_rc 0 "$HOOK_RC" "a hook whose migration outlasts its bound exits 0"
HOME="$MG" SMINOS_HOME="$MG/sminos" SMNS_RECORD_TIMEOUT=0.2 hook_run Stop "$HA" "$R3" "$TA"
board_check() { python3 -c 'import json, sys
posts = [json.loads(l) for l in open(sys.argv[1])]
print(len(posts), sorted(p["id"] for p in posts) == list(range(1, len(posts) + 1)), sorted(p["text"] for p in posts))' "$1"; }
assert_equals "$(board_check "$MG/sminos/groups/g1/board.jsonl")" "3 True ['aside one', 'aside two', 'root one']" \
  "the board holds each post once, every line whole, ids in sequence, after a second run"
if ls -d "$MG/sminos.v2-"* >/dev/null 2>&1; then fail "the merged aside is gone"; else pass "the merged aside is gone"; fi
# A migration step's own lock is waited for only until the hook's deadline: a
# step that cannot have it is skipped untouched, and a later call does it.
MW="$TEST_ROOT/migwait"
mkdir -p "$MW/.claude/sessions" "$MW/sminos/chats" "$MW/sminos/projects/$HP/log"
chmod 700 "$MW/sminos"
NEEDY=7b00000c-0000-4000-8000-00000000007b
printf '{"uuid":"%s","current":"%s","alias":"needy","status":"idle","cwd":"%s"}' "$NEEDY" "$NEEDY" "$R3" > "$MW/sminos/$NEEDY.json"
chmod 600 "$MW/sminos/$NEEDY.json"
hold_lock() { # path — hold an exclusive flock on it until $TEST_ROOT/release appears
  rm -f "$TEST_ROOT/held" "$TEST_ROOT/release"
  python3 - "$1" "$TEST_ROOT/held" "$TEST_ROOT/release" <<'PY_HOLD' & holder=$!
import fcntl, os, sys, time
with open(sys.argv[1], 'a') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    open(sys.argv[2], 'w').close()
    while not os.path.exists(sys.argv[3]):
        time.sleep(0.05)
PY_HOLD
  for _ in $(seq 1 100); do [ -f "$TEST_ROOT/held" ] && break; sleep .05; done
}
mw_hook() { # timed: sets elapsed
  local t0
  t0=$(date +%s)
  HOME="$MW" SMINOS_HOME="$MW/sminos" SMNS_RECORD_TIMEOUT=1 hook_run Stop "$HA" "$R3" "$TA"
  elapsed=$(( $(date +%s) - t0 ))
}
needy_group() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("group", "<none>"))' "$MW/sminos/$NEEDY.json"; }
hold_lock "$MW/sminos/.metalock"
mw_hook
touch "$TEST_ROOT/release"; wait "$holder"
assert_rc 0 "$HOOK_RC" "with .metalock held, a hook whose migration must stamp a seat record exits 0"
assert_equals "$(( elapsed < 4 ))" "1" "promptly (${elapsed}s for a 1s bound)"
assert_equals "$(needy_group)" "<none>" "leaving the record untouched"
assert_contains "$(cat "$MW/sminos/daemon.log")" "migrate: skipped migrating record ${NEEDY:0:8} — .metalock held past the deadline" "and saying what it skipped"
mw_hook
assert_equals "$(needy_group)" "hp-repo" "once the lock is free, a later call stamps it"
# A pending legacy chat import, its project's log lock held.
printf '{"id":1,"ts":"2026-01-01T00:00:00Z","from":"human","to":[],"mode":"broadcast","text":"legacy hello"}\n' > "$MW/sminos/chats/$NEEDY.jsonl"
hold_lock "$MW/sminos/projects/$HP/log/.sync.lock"
mw_hook
touch "$TEST_ROOT/release"; wait "$holder"
assert_rc 0 "$HOOK_RC" "with the log's .sync.lock held, a hook whose migration must import a chat exits 0"
assert_equals "$(( elapsed < 4 ))" "1" "promptly (${elapsed}s for a 1s bound)"
assert_file_exists "$MW/sminos/chats/$NEEDY.jsonl" "leaving the chat to import"
assert_file_absent "$MW/sminos/projects/$HP/log/legacy.$NEEDY.jsonl" "writing nothing into the log"
assert_equals "$(find "$MW/sminos/projects/$HP/log" -name '.tmp-*' | wc -l | tr -d ' ')" "0" "and leaving no temporary file"
assert_contains "$(cat "$MW/sminos/daemon.log")" "migrate: skipped importing chat ${NEEDY:0:8} — the log's .sync.lock held past the deadline" "saying what it skipped"
mw_hook
assert_contains "$(cat "$MW/sminos/projects/$HP/log/legacy.$NEEDY.jsonl" 2>/dev/null)" "legacy hello" "once the lock is free, a later call imports it"
assert_file_exists "$MW/sminos/chats/$NEEDY.jsonl.imported" "and sets the chat aside as imported"
hook_run Stop "$HA" "$R3" "$TA"
assert_equals "$(grep -c 'while a lock is held' "$HPLOG/testhost.$HA.jsonl")" "1" "once the locks are free, the next Stop exports"

# No position at all (the plugin arrived mid-session): the first Stop exports
# the trailing run of assistant records and nothing before the peer frame.
HB=5b000002-0000-4000-8000-00000000005b
TB="$TXD/$HB.jsonl"
hp_peer hb "$HB" derived interactive
tx "$TB" prompt b1000001 "go"
tx "$TB" asst b1000002 '<message>before the frame</message>'
tx "$TB" peer b1000003 "a peer interrupts"
tx "$TB" asst b1000004 '<message>after the frame</message>'
hook_run Stop "$HB" "$R3" "$TB"
assert_contains "$(cat "$HPLOG/testhost.$HB.jsonl")" "after the frame" "a first Stop with no position exports the trailing run"
assert_not_contains "$(cat "$HPLOG/testhost.$HB.jsonl")" "before the frame" "and nothing before the peer frame"
assert_equals "$(hp_events "$HB" | cut -d' ' -f1)" "joined" "joining the session first"
tx "$TB" asst b1000005 '<message>next turn</message>'
hook_run Stop "$HB" "$R3" "$TB"
assert_contains "$(cat "$HPLOG/testhost.$HB.jsonl")" "next turn" "from there the position carries on"
assert_not_contains "$(cat "$HPLOG/testhost.$HB.jsonl")" "before the frame" "and the earlier mark stays out"
# An answer to a question the log never held (asked before the plugin came) stands alone.
tx "$TB" deliver-att b1000006 toolu_orphan 'Your questions have been answered: "Old?"="Yes".'
tx "$TB" asst b1000007 "Noted."
hook_run Stop "$HB" "$R3" "$TB"
run "$SMINOS" chat hostdemo --host
assert_contains "$OUT" 'hb answered (call toolu_orphan): Your questions have been answered: "Old?"="Yes".' "an answer with no question in the log is shown on its own"
run "$SMINOS" chat hostdemo --host --kind message
assert_rc 2 "$RC" "chat --host takes no --kind"
# The window is chosen before grouping: an answer given now to a question
# asked long ago shows, its question beneath it, by default and since today.
HQ=6f00000a-0000-4000-8000-00000000006f
python3 - "$HPLOG/testhost.$HQ.jsonl" "$HQ" <<'PY_OLDQ'
import datetime, json, sys
w = "testhost/" + sys.argv[2]
t = datetime.datetime.now(datetime.timezone.utc)
now = t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000)
rows = [{"ts": "2000-01-01T00:00:00.000Z", "kind": "question", "from": "hq", "to": "host", "text": ["Old question?"],
         "choices": ["Yes", "No"], "src": "toolu_old"}]
rows += [{"ts": "2000-01-02T00:00:%02d.000Z" % i, "kind": "message", "from": "hq", "to": "host", "text": "filler %d" % i,
          "src": "q%d#0" % i} for i in range(35)]
rows += [{"ts": now, "kind": "answered", "from": "hq", "src": "toolu_old", "text": "Your questions have been answered: \"Old question?\"=\"Yes\"."}]
with open(sys.argv[1], "w") as f:
    for seq, r in enumerate(rows, 1):
        f.write(json.dumps({"ts": r.pop("ts"), "writer": w, "seq": seq, **r}) + "\n")
PY_OLDQ
TODAY="$(date -u +%Y-%m-%d)"
for window in "" "--since $TODAY"; do
  # shellcheck disable=SC2086
  run "$SMINOS" chat hostdemo --host $window
  assert_contains "$OUT" 'hq answered (call toolu_old): Your questions have been answered: "Old question?"="Yes".' "an answer whose question is outside the window shows (${window:-default})"
  assert_contains "$OUT" "    to: Old question? (asked 2000-01-01 00:00)" "with its question beneath it (${window:-default})"
  assert_not_contains "$OUT" "hq asks" "and the question itself stays outside the window (${window:-default})"
done
run "$SMINOS" chat hostdemo --host --since "$TODAY" --json
assert_contains "$(printf '%s\n' "$OUT" | grep toolu_old | head -1)" '"kind": "question"' "--json gives the question first, as context"
assert_contains "$(printf '%s\n' "$OUT" | grep toolu_old | tail -1)" '"kind": "answered"' "then the answer"
assert_not_contains "$OUT" "filler" "and nothing else outside the window"
rm -f "$HPLOG/testhost.$HQ.jsonl"
# Every reading chat reconciles first, the host view too.
HR=7a00000b-0000-4000-8000-00000000007a
hp_peer hr "$HR" derived interactive
run "$SMINOS" chat hostdemo --host
assert_equals "$(hp_events "$HR")" "joined " "a first host read joins a live session"

# Who is not a member records nothing: another tool's headless run, a session
# in no project, an internal fork.
HS=5c000003-0000-4000-8000-00000000005c
hp_peer tool "$HS" derived sdk
tx "$TXD/$HS.jsonl" asst c1000001 '<message>from a tool run</message>'
hook_run SessionStart "$HS" "$R3" "$TXD/$HS.jsonl" startup
hook_run Stop "$HS" "$R3" "$TXD/$HS.jsonl"
assert_file_absent "$HPLOG/testhost.$HS.jsonl" "a session of another kind records nothing"
assert_rc 0 "$HOOK_RC" "and the hook exits 0"
mkdir -p "$TEST_ROOT/hp-nowhere"
NOW_HOMES="$(ls "$SMINOS_HOME/projects" | wc -l | tr -d ' ')"
hook_run SessionStart "$HA" "$TEST_ROOT/hp-nowhere" "$TA" startup
hook_run Stop "$HA" "$TEST_ROOT/hp-nowhere" "$TA"
assert_equals "$(ls "$SMINOS_HOME/projects" | wc -l | tr -d ' ')" "$NOW_HOMES" "a session in no project records nothing anywhere"
HI=5d000004-0000-4000-8000-00000000005d
hp_peer fork "$HI" derived interactive
tx "$TXD/$HI.jsonl" asst d1000001 '<message>a fork answers</message>'
SMNS_INTERNAL=1 hook_run SessionStart "$HI" "$R3" "$TXD/$HI.jsonl" fork
SMNS_INTERNAL=1 hook_run Stop "$HI" "$R3" "$TXD/$HI.jsonl"
assert_file_absent "$HPLOG/testhost.$HI.jsonl" "an internal fork records nothing"
rm -f "$HOME/.claude/sessions/hp-fork.json" "$HOME/.claude/sessions/hp-tool.json"

# The harness record not yet written at SessionStart: no join on no evidence,
# but the position is set, so the first turn's marks all count at its Stop.
HC=5e000005-0000-4000-8000-00000000005e
TC="$TXD/$HC.jsonl"
hook_run SessionStart "$HC" "$R3" "$TC" startup
assert_file_absent "$HPLOG/testhost.$HC.jsonl" "a session the harness has not registered yet is not joined at its start"
assert_file_exists "$SMINOS_HOME/projects/$HP/cursors/export/$HC.json" "but its export position is set"
hp_peer hc "$HC" derived interactive
tx "$TC" prompt e1000001 "first"
tx "$TC" asst e1000002 '<message>first mark</message>'
tx "$TC" peer e1000003 "a frame"
tx "$TC" asst e1000004 '<message>second mark</message>'
hook_run Stop "$HC" "$R3" "$TC"
assert_equals "$(hp_events "$HC")" "joined message:e1000002#0 message:e1000004#0 " "its Stop joins it and exports the whole first turn"

# The in-charge line: charge beats a name the human set; the name beats a
# derived line; a derived line beats the transcript's title.
run "$SMINOS" list --json
assert_equals "$(json_row ha charge)" "ha" "a user-named member's line is its name"
assert_equals "$(json_row ha charge_source)" "name" "sourced from the name"
run "$SMINOS" list
assert_equals "$(printf '%s\n' "$OUT" | grep '^  ha ')" "  ha   idle" "list does not print the name twice"
python3 - "$SMINOS_PY" "$HP" "$HA" <<'PY_DERIVED'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sminos", sys.argv[1]); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
mod.lifecycle(mod.find_project(sys.argv[2]), sys.argv[3], "in-charge", text="a derived guess", source="derived")
PY_DERIVED
assert_equals "$(json_row ha charge)" "ha" "the name beats a derived line"
run "$SMINOS" charge hb "owns the GUI tool"
assert_rc 0 "$RC" "the operator sets a member's line"
assert_contains "$(tail -1 "$HPLOG/testhost.$HB.jsonl")" '"kind": "in-charge", "session": "'"$HB"'", "text": "owns the GUI tool", "source": "set"' \
  "as a set in-charge event in the member's own file"
run "$SMINOS" list
assert_contains "$OUT" "owns the GUI tool" "list shows the line"
assert_equals "$(json_row hb charge_source)" "set" "list --json says it was set"
CLAUDE_CODE_SESSION_ID="$HA" run "$SMINOS" charge "parser"
assert_rc 0 "$RC" "a session sets its own line"
run "$SMINOS" list
assert_contains "$OUT" "  ha " "the member keeps its alias"
assert_contains "$OUT" "parser" "and shows the line it set"
assert_equals "$(json_row ha charge_source)" "set" "charge beats a name the human set"
run "$SMINOS" charge "orphan line"
assert_rc 2 "$RC" "the operator names the member"
run "$SMINOS" charge hb "two" "three"
assert_rc 2 "$RC" "a line given as several words is refused: quote it"
tx "$TC" title "구글 테이크아웃 Gemini 대화 기록"
assert_equals "$(json_row hc charge)" "구글 테이크아웃 Gemini 대화 기록" "with no line set, named, or derived, the transcript's latest title"
assert_equals "$(json_row hc charge_source)" "title" "sourced from the title"

# derive: a headless internal fork answers; nothing of it stays.
HD=5f000006-0000-4000-8000-00000000005f
TD="$TXD/$HD.jsonl"
hp_peer hd "$HD" derived interactive
for i in 1 2 3 4 5 6 7 8 9; do tx "$TD" prompt "f00000$i" "prompt $i"; tx "$TD" asst "f10000$i" "answer $i"; done
run "$SMINOS" derive hd
assert_contains "$OUT" "not derived" "a session with fewer than ten prompts is not derived"
tx "$TD" prompt f0000010 "prompt 10"
tx "$TD" peer f0000011 "a frame is not a prompt"
run "$SMINOS" list --json
MEMBERS_BEFORE="$(printf '%s' "$OUT" | grep -c '"session"')"
HOST_BEFORE="$(host_count)"
TX_BEFORE="$(find "$HOME/.claude/projects" -name '*.jsonl' | wc -l | tr -d ' ')"
: > "$STUB_STATE/fork-list.json"
STUB_FORK_LIST=1 STUB_FORK_RESULT='<message>Keeps the stub tool working.
A second line.</message>' run "$SMINOS" derive hd
assert_rc 0 "$RC" "derive exits 0"
assert_contains "$OUT" "hd: Keeps the stub tool working." "derive prints the one-line answer, marks stripped, first line"
assert_contains "$(tail -1 "$HPLOG/testhost.$HD.jsonl")" '"text": "Keeps the stub tool working.", "source": "derived"' "and records it as a derived line"
assert_equals "$(json_row hd charge_source)" "derived" "list --json says the line was derived"
run "$SMINOS" list --json
assert_equals "$(printf '%s' "$OUT" | grep -c '"session"')" "$MEMBERS_BEFORE" "list --json has the same number of members after"
assert_not_contains "$(cat "$STUB_STATE/fork-list.json")" "stubfork" "nor during the fork: its session is marked internal"
assert_contains "$(cat "$STUB_STATE/fork-list.json")" '"alias": "hd"' "while the members stay listed"
assert_equals "$(host_count)" "$HOST_BEFORE" "the host stream has no new line"
assert_equals "$(find "$HOME/.claude/projects" -name '*.jsonl' | wc -l | tr -d ' ')" "$TX_BEFORE" "the fork's transcript is deleted"
assert_contains "$(grep 'fork-env:' "$STUB_STATE/log/calls.log" | tail -1)" "internal=1 marker=yes" "the fork runs with SMNS_INTERNAL set and its pid marked before it starts"
FORK_ARGV="$(grep -- '--fork-session' "$STUB_STATE/log/calls.log" | tail -1)"
if grep -Eq -- "^-p --resume $HD --fork-session --session-id [0-9a-f-]{36} --tools  --output-format json In one line: what is this session in charge of" <<<"$FORK_ARGV"; then
  pass "the fork is the headless resume the design names, its id pinned, the prompt last"
else fail "the fork is the headless resume the design names, its id pinned, the prompt last"; echo "    in: $FORK_ARGV"; fi
assert_equals "$(ls "$SMINOS_HOME/internal" 2>/dev/null | wc -l | tr -d ' ')" "0" "and its marker is removed"
FORK_ID="$(sed -n 's/.*--session-id \([0-9a-f-]*\).*/\1/p' <<<"$FORK_ARGV")"
assert_file_absent "$HPLOG/testhost.$FORK_ID.jsonl" "and the hook recorded nothing for the fork"
run "$SMINOS" derive hd
assert_contains "$OUT" "not derived" "a session derived within six hours is not derived again"
# A user-named session with prompts enough and no line set: its name is its line.
HU=6e000009-0000-4000-8000-00000000006e
hp_peer hu "$HU" user interactive
for i in 1 2 3 4 5 6 7 8 9 10; do tx "$TXD/$HU.jsonl" prompt "u90000$i" "prompt $i"; done
run "$SMINOS" derive hu
assert_contains "$OUT" "hu: not derived — its human named it" "a user-named session is never derived"
run "$SMINOS" derive --all
assert_contains "$OUT" "hu: not derived — its human named it" "nor by --all"
assert_not_contains "$(cat "$HPLOG/testhost.$HU.jsonl")" "in-charge" "and holds no line"
# A fork that fails prints its stderr's tail and writes nothing.
HE=6a000007-0000-4000-8000-00000000006a
TE="$TXD/$HE.jsonl"
hp_peer he "$HE" derived interactive
for i in 1 2 3 4 5 6 7 8 9 10; do tx "$TE" prompt "g0000$i" "prompt $i"; done
TX_BEFORE="$(find "$HOME/.claude/projects" -name '*.jsonl' | wc -l | tr -d ' ')"
STUB_FORK_FAIL=1 run "$SMINOS" derive he
assert_rc 1 "$RC" "a failed fork exits 1"
assert_contains "$OUT" "stub: the fork exploded" "printing the tail of its stderr"
assert_not_contains "$(cat "$HPLOG/testhost.$HE.jsonl")" "in-charge" "and writing nothing"
assert_equals "$(find "$HOME/.claude/projects" -name '*.jsonl' | wc -l | tr -d ' ')" "$TX_BEFORE" "its transcript is deleted all the same"
assert_equals "$(ls "$SMINOS_HOME/internal" 2>/dev/null | wc -l | tr -d ' ')" "0" "and its marker"
STUB_FORK_CRASH=1 run "$SMINOS" derive he
assert_rc 1 "$RC" "a fork that crashes without printing anything exits 1"
assert_not_contains "$(cat "$HPLOG/testhost.$HE.jsonl")" "in-charge" "writing nothing"
assert_equals "$(find "$HOME/.claude/projects" -name '*.jsonl' | wc -l | tr -d ' ')" "$TX_BEFORE" "and leaves no transcript: its id was pinned before it started"
# A headless or SDK run registers as interactive with an sdk-* entrypoint: no
# member, whatever its kind — neither reconciliation nor the hook joins it.
HH=6b000008-0000-4000-8000-00000000006b
printf '{"pid":%s,"sessionId":"%s","name":"headless","kind":"interactive","entrypoint":"sdk-cli","status":"busy","cwd":"%s"}\n' \
  "$SOCK_PID" "$HH" "$R3" > "$HOME/.claude/sessions/hp-headless.json"
run "$SMINOS" list --all
assert_not_contains "$OUT" "headless" "an sdk-cli run is not listed, though its kind reads interactive"
assert_file_absent "$HPLOG/testhost.$HH.jsonl" "nor joined by reconciliation"
tx "$TXD/$HH.jsonl" asst h1000001 '<message>from a headless run</message>'
hook_run SessionStart "$HH" "$R3" "$TXD/$HH.jsonl" startup
hook_run Stop "$HH" "$R3" "$TXD/$HH.jsonl"
assert_file_absent "$HPLOG/testhost.$HH.jsonl" "nor joined by the hook, and it exports nothing"
assert_rc 0 "$HOOK_RC" "the hook exits 0 for it"
for ep in cli:6c000009 claude-vscode:6d00000a; do
  printf '{"pid":%s,"sessionId":"%s-0000-4000-8000-00000000006c","name":"ide","kind":"interactive","entrypoint":"%s","status":"idle","cwd":"%s"}\n' \
    "$SOCK_PID" "${ep#*:}" "${ep%%:*}" "$R3" > "$HOME/.claude/sessions/hp-ide-${ep#*:}.json"
  run "$SMINOS" list --json
  assert_contains "$OUT" "${ep#*:}-0000" "an interactive session from entrypoint ${ep%%:*} still joins"
done
cd "$WORK"
rm -f "$HOME/.claude/sessions/hp-"*.json

# ---- the mirror and the daemon ----------------------------------------------------
# A project whose .smns names a remote mirrors its log through it; one daemon
# per machine syncs, delivers what is owed to its members, and publishes their
# state (spec 2026-10-13, §8, M4). Two homes on one machine stand for two
# machines: each its own HOME (harness sessions, transcripts), SMINOS_HOME,
# stub harness state and machine name; the stub mints session uuids from one
# shared counter. With SMINOS_TRANSCRIPT=1 the acceptance steps print as a
# transcript.
echo "the mirror and the daemon:"
unset CLAUDE_CODE_SESSION_ID
MD="$TEST_ROOT/md"
mkdir -p "$MD"
export STUB_COUNTER="$MD/uuid-counter"
for h in h1 h2 h3 solo inst; do
  mkdir -p "$MD/$h/.claude/sessions" "$MD/$h/stub/agents" "$MD/$h/stub/log" "$MD/$h/sminos"
  chmod 700 "$MD/$h/sminos"
done
H1=(HOME="$MD/h1" SMINOS_HOME="$MD/h1/sminos" DAEMON_HOST=h1 STUB_STATE="$MD/h1/stub")
H2=(HOME="$MD/h2" SMINOS_HOME="$MD/h2/sminos" DAEMON_HOST=h2 STUB_STATE="$MD/h2/stub")
H3=(HOME="$MD/h3" SMINOS_HOME="$MD/h3/sminos" DAEMON_HOST=h2 STUB_STATE="$MD/h3/stub")   # a second machine named h2
SOLO=(HOME="$MD/solo" SMINOS_HOME="$MD/solo/sminos" DAEMON_HOST=solo STUB_STATE="$MD/solo/stub")
md_peer() { # home name session status [kind] [cwd] — a live harness session in that home, its own inbox
  [ -S "$TEST_ROOT/in-md-$2.sock" ] || start_inbox "md-$2"
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"derived","kind":"%s","status":"%s","cwd":"%s","messagingSocketPath":"%s"}\n' \
    "$SOCK_PID" "$3" "$2" "${5:-bg}" "$4" "${6:-$RR}" "$TEST_ROOT/in-md-$2.sock" > "$MD/$1/.claude/sessions/$2.json"
}
md_inbox() { cat "$TEST_ROOT/in-md-$1.received" 2>/dev/null || true; }
tscript() { # the command as the acceptance reads it, then what it printed
  [[ "${SMINOS_TRANSCRIPT:-0}" == 1 ]] || return 0
  printf '    $ %s\n' "$1"
  [ -z "$2" ] || printf '%s\n' "$2" | sed 's/^/      /'
}
clock() { python3 -c 'import time; print(time.time())'; }
since() { python3 -c 'import sys, time; print("%.1f" % (time.time() - float(sys.argv[1])))' "$1"; }
seq_of() { python3 -c 'import json, sys; print(json.loads(open(sys.argv[1]).read().splitlines()[-1])["seq"])' "$1"; }

# Acceptance 6. A scratch repository R, its .smns naming a local bare repository.
REMOTE="$MD/remote.git"
gitq init -q --bare "$REMOTE"
RR="$MD/R"
mkdir -p "$RR"
gitq init -q "$RR"
cd "$RR"
run env "${H1[@]}" "$SMINOS" project init --name demo --remote "$REMOTE"
tscript "env \$H1 sminos project init --name demo --remote $REMOTE" "$OUT"
assert_rc 0 "$RC" "project init names the remote"
gitq -C "$RR" add .smns
gitq -C "$RR" commit -qm smns
MDP="$(smns_id "$RR")"
LOG1="$MD/h1/sminos/projects/$MDP/log"
LOG2="$MD/h2/sminos/projects/$MDP/log"
run env "${H1[@]}" "$SMINOS" spawn a "wait for instructions"
tscript "env \$H1 sminos spawn a \"wait for instructions\"" "$OUT"
A="$(banner_uuid "$OUT")"
run env "${H2[@]}" "$SMINOS" spawn b "wait for instructions"
tscript "env \$H2 sminos spawn b \"wait for instructions\"" "$OUT"
B="$(banner_uuid "$OUT")"
assert_contains "$A" "-e808-" "a spawns under h1"
assert_contains "$B" "-e808-" "b spawns under h2"
if [[ -n "$A" && "$A" != "$B" ]]; then pass "the two homes mint distinct session uuids before anything replicates"; else
  fail "the two homes mint distinct session uuids before anything replicates"; echo "    a=$A b=$B"; fi
md_peer h1 a "$A" idle
md_peer h2 b "$B" busy
run env "${H1[@]}" "$SMINOS" daemon tick
tscript "env \$H1 sminos daemon tick" "$OUT"
assert_rc 0 "$RC" "h1 ticks"
assert_contains "$OUT" "demo: synced · reconciled 0 · published 1 · delivered 0 · pushed" "its first tick attaches the mirror, publishes a's state, and pushes"
assert_contains "$(gitq -C "$REMOTE" ls-tree -r --name-only main)" "h1.$A.jsonl" "a's file is on the remote"
assert_contains "$(gitq -C "$REMOTE" ls-tree -r --name-only main)" "machines/h1.json" "with h1's claim on its name"
run env "${H2[@]}" "$SMINOS" project attach
tscript "env \$H2 sminos project attach" "$OUT"
assert_rc 0 "$RC" "h2 attaches"
assert_contains "$OUT" "attached demo to $REMOTE" "and says so"
assert_file_exists "$LOG2/h1.$A.jsonl" "the attach brings h1's files"
assert_file_exists "$LOG2/h2.$B.jsonl" "beside h2's own"
run env "${H2[@]}" "$SMINOS" daemon tick
tscript "env \$H2 sminos daemon tick" "$OUT"
assert_contains "$OUT" "demo: synced · reconciled 0 · published 1 · delivered 0 · pushed" "h2 ticks: b's state published and pushed"
assert_not_contains "$OUT" "migrated" "the daemon's own files are no seat records"
assert_equals "$(printf '%s\n' "$OUT" | grep -c ': ')" 1 "and make no project of their own"
run env "${H1[@]}" "$SMINOS" daemon tick
tscript "env \$H1 sminos daemon tick" "$OUT"
run env "${H1[@]}" "$SMINOS" list
tscript "env \$H1 sminos list" "$OUT"
assert_contains "$OUT" "demo" "after one h2 tick and one h1 tick, list under h1 shows the project"
B_ROW="$(printf '%s\n' "$OUT" | grep '^  b ' || true)"
assert_contains "$B_ROW" "busy @h2 " "with b on h2, its state, and the state's age"
assert_contains "$(printf '%s\n' "$OUT" | grep '^  a ' || true)" "idle" "and a, local, by its live word"
CLAUDE_CODE_SESSION_ID="$A" run env "${H1[@]}" "$SMINOS" say "@b hello"
tscript "env \$H1 CLAUDE_CODE_SESSION_ID=<a> sminos say \"@b hello\"" "$OUT"
assert_rc 0 "$RC" "a says @b from h1"
assert_contains "$OUT" "b: recorded (on h2)" "recorded for b's machine to deliver"
run env "${H1[@]}" "$SMINOS" daemon tick
tscript "env \$H1 sminos daemon tick" "$OUT"
assert_contains "$OUT" "pushed" "one h1 tick pushes it"
assert_equals "$(md_inbox b)" "" "and it reaches no socket until h2 ticks"
run env "${H2[@]}" "$SMINOS" daemon tick
tscript "env \$H2 sminos daemon tick" "$OUT"
assert_contains "$OUT" "delivered 1 to b" "h2's tick delivers it to b"
assert_contains "$(frames md-b)" "[sminos chat demo ${A:0:8}:" "b's socket receives the frame, the event's id in it"
assert_contains "$(frames md-b)" "from a → @you] / @b hello" "from a, carrying the text"
run env "${H2[@]}" "$SMINOS" daemon tick
tscript "env \$H2 sminos daemon tick" "$OUT"
assert_contains "$OUT" "delivered 0" "a second h2 tick delivers nothing more"
assert_equals "$(bodies md-b | grep -c '^@b hello$')" 1 "b holds the frame once"
md_peer h2 b "$B" idle
run env "${H2[@]}" "$SMINOS" daemon tick
tscript "env \$H2 sminos daemon tick    # b went idle" "$OUT"
assert_contains "$OUT" "published 0" "one tick of a new word publishes nothing"
run env "${H2[@]}" "$SMINOS" daemon tick
tscript "env \$H2 sminos daemon tick" "$OUT"
assert_contains "$OUT" "published 1" "the second publishes it"
run env "${H1[@]}" "$SMINOS" daemon tick
tscript "env \$H1 sminos daemon tick" "$OUT"
run env "${H1[@]}" "$SMINOS" list
tscript "env \$H1 sminos list" "$OUT"
assert_contains "$(printf '%s\n' "$OUT" | grep '^  b ' || true)" "idle @h2 " "after b went idle for two h2 ticks and one h1 tick, list under h1 shows b idle @h2"

# M2's status across homes, through the mirror: a status set under h1 is in
# h2's list --json after a sync.
run env "${H1[@]}" "$SMINOS" status a "reading the schema"
assert_rc 0 "$RC" "the operator sets a's status under h1"
run env "${H1[@]}" "$SMINOS" daemon tick
run env "${H2[@]}" "$SMINOS" daemon tick
A_ROW="$(env "${H2[@]}" "$SMINOS" list --json | python3 -c 'import json, sys
r = next(d for d in json.load(sys.stdin) if d["session"] == sys.argv[1])
print(r["status"], r["machine"], r["local"], r["state"])' "$A")"
assert_equals "$A_ROW" "reading the schema h1 False idle" "h2's list --json shows a remote, on h1, with its status and published state"

# Both daemons running: the same say lands within two seconds.
env "${H1[@]}" "$SMINOS" daemon run --interval 1 > "$MD/run-h1.out" 2>&1 & RUN1=$!
env "${H2[@]}" "$SMINOS" daemon run --interval 1 > "$MD/run-h2.out" 2>&1 & RUN2=$!
sleep 1.5
T0="$(clock)"
CLAUDE_CODE_SESSION_ID="$A" run env "${H1[@]}" "$SMINOS" say "@b while both daemons run"
for _ in $(seq 1 120); do grep -q 'while both daemons run' "$TEST_ROOT/in-md-b.received" 2>/dev/null && break; sleep 0.05; done
LANDED="$(since "$T0")"
tscript "env \$H1 sminos daemon run --interval 1 & env \$H2 sminos daemon run --interval 1 &" ""
tscript "env \$H1 CLAUDE_CODE_SESSION_ID=<a> sminos say \"@b while both daemons run\"" "$OUT
(landed in b's socket after ${LANDED}s)"
if grep -q 'while both daemons run' "$TEST_ROOT/in-md-b.received" && python3 -c 'import sys; sys.exit(float(sys.argv[1]) > 2.0)' "$LANDED"; then
  pass "with daemon run --interval 1 under both homes the say lands within two seconds (${LANDED}s)"
else fail "with daemon run --interval 1 under both homes the say lands within two seconds"; echo "    took ${LANDED}s"; fi
run env "${H1[@]}" "$SMINOS" daemon run --interval 1
assert_rc 1 "$RC" "a second run in the same home is refused"
assert_contains "$OUT" "a daemon already runs" "saying one runs"
run env "${H1[@]}" "$SMINOS" daemon status
assert_contains "$OUT" "daemon: running (pid $RUN1" "daemon status names the running loop"
assert_contains "$OUT" "demo: last tick " "and the last tick per project"
kill "$RUN1"; wait "$RUN1" || true
run env "${H1[@]}" "$SMINOS" daemon status
assert_contains "$OUT" "daemon: not running here" "once stopped, status says so"
# The sender's machine does not wait out its interval: a say to a remote member
# asks the local loop for a tick at once.
env "${H1[@]}" "$SMINOS" daemon run --interval 60 > "$MD/run-h1-slow.out" 2>&1 & RUN1=$!
sleep 1.5
T0="$(clock)"
CLAUDE_CODE_SESSION_ID="$A" run env "${H1[@]}" "$SMINOS" say "@b nudged"
for _ in $(seq 1 120); do grep -q 'nudged' "$TEST_ROOT/in-md-b.received" 2>/dev/null && break; sleep 0.05; done
NUDGED="$(since "$T0")"
if grep -q 'nudged' "$TEST_ROOT/in-md-b.received" && python3 -c 'import sys; sys.exit(float(sys.argv[1]) > 3.0)' "$NUDGED"; then
  pass "a say to a remote member has the sender's daemon push at once, whatever its interval (${NUDGED}s)"
else fail "a say to a remote member has the sender's daemon push at once, whatever its interval"; echo "    took ${NUDGED}s"; fi
kill "$RUN1" "$RUN2"; wait "$RUN1" "$RUN2" || true
assert_contains "$(cat "$MD/run-h2.out")" "delivered 1 to b" "the loop says what it delivered"

# The sync invariant: an append after a successful sync, while the other home
# publishes, syncs on the next tick with both histories intact.
run env "${H1[@]}" "$SMINOS" daemon tick
run env "${H1[@]}" "$SMINOS" say "after the sync"
md_peer h2 b "$B" waiting
run env "${H2[@]}" "$SMINOS" daemon tick
run env "${H2[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "published 1 · delivered 0 · pushed" "meanwhile h2 publishes and pushes"
H2_HEAD="$(gitq -C "$LOG2" rev-parse HEAD)"
run env "${H1[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "demo: synced" "h1's next tick syncs"
assert_contains "$OUT" "pushed" "and pushes"
H1_SAY="$(gitq -C "$LOG1" log -S'after the sync' --format=%H | tail -1)"
run env "${H2[@]}" "$SMINOS" daemon tick
assert_contains "$(cat "$LOG2/h1.human.jsonl")" "after the sync" "h1's append reaches h2"
assert_contains "$(cat "$LOG1/h2.$B.jsonl")" '"state": "waiting"' "h2's publication reaches h1"
if gitq -C "$REMOTE" merge-base --is-ancestor "$H1_SAY" main && gitq -C "$REMOTE" merge-base --is-ancestor "$H2_HEAD" main; then
  pass "the remote holds both histories"; else fail "the remote holds both histories"; fi
assert_equals "$(gitq -C "$LOG1" status --porcelain)" "" "h1's mirror is clean: every event is in a commit"

# A state flip lasting one tick is not published.
STATES_BEFORE="$(grep -c '"kind": "state"' "$LOG1/h1.$A.jsonl")"
md_peer h1 a "$A" busy
run env "${H1[@]}" "$SMINOS" daemon tick
md_peer h1 a "$A" idle
run env "${H1[@]}" "$SMINOS" daemon tick
assert_equals "$(grep -c '"kind": "state"' "$LOG1/h1.$A.jsonl")" "$STATES_BEFORE" "a state flip lasting one tick is not published"
md_peer h1 a "$A" busy
run env "${H1[@]}" "$SMINOS" daemon tick
run env "${H1[@]}" "$SMINOS" daemon tick
assert_contains "$(tail -1 "$LOG1/h1.$A.jsonl")" '"kind": "state", "session": "'"$A"'", "state": "busy", "machine": "h1"' "one that holds for two ticks is"
md_peer h1 a "$A" idle

# A second machine under a claimed name refuses to run, and writes nothing to the remote.
REMOTE_HEAD="$(gitq -C "$REMOTE" rev-parse main)"
run env "${H3[@]}" "$SMINOS" project attach
assert_rc 1 "$RC" "attach under a name another instance claimed is refused"
assert_contains "$OUT" "the machine name h2 is claimed by another instance" "saying the name is claimed"
run env "${H3[@]}" "$SMINOS" daemon tick
assert_rc 1 "$RC" "a claimed machine name refuses to run: tick"
assert_contains "$OUT" "refuses to run" "saying so"
run env "${H3[@]}" "$SMINOS" daemon run --interval 1
assert_rc 1 "$RC" "and run"
assert_equals "$(gitq -C "$REMOTE" rev-parse main)" "$REMOTE_HEAD" "nothing of it reached the remote"
assert_contains "$(cat "$MD/h3/sminos/daemon.log")" "refused: the machine name h2 is claimed" "the refusal is in daemon.log"

# A stalled remote: the fetch and the push wait outside .sync.lock, so a
# fetch that hangs blocks no say and no Stop export; what they append during
# it is committed and integrated in the same exclusive phase. The remote is
# reached over a stand-in ssh that waits while a gate file exists.
cat > "$MD/fake-ssh" <<'SSH'
#!/bin/sh
# ssh, as GIT_SSH_VARIANT=simple calls it (host, command): run the command here.
[ -z "${SSH_ENTERED:-}" ] || : > "$SSH_ENTERED"
while [ -n "${SSH_GATE:-}" ] && [ -f "$SSH_GATE" ]; do sleep 0.05; done
exec sh -c "$2"
SSH
chmod +x "$MD/fake-ssh"
export GIT_SSH_COMMAND="$MD/fake-ssh" GIT_SSH_VARIANT=simple
STALL="$MD/stall.git"
gitq init -q --bare "$STALL"
SR="$MD/SR"
mkdir -p "$SR"
gitq init -q "$SR"
cd "$SR"
run env "${H1[@]}" "$SMINOS" project init --name stall --remote "ssh://stall$STALL"
gitq -C "$SR" add .smns
gitq -C "$SR" commit -qm smns
STP="$(smns_id "$SR")"
SLOG="$MD/h1/sminos/projects/$STP/log"
SS=5a000005-0000-4000-8000-00000000005a
STX="$MD/h1/.claude/projects/st/$SS.jsonl"
mkdir -p "$(dirname "$STX")"
tx "$STX" prompt 5b000001 "start"
md_peer h1 sess "$SS" idle interactive "$SR"
md_hook() { # event session cwd transcript [source] — the hook under h1
  set +e
  HOOK_OUT="$(printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","hook_event_name":"%s","source":"%s"}' \
    "$2" "$4" "$3" "$1" "${5:-}" | env "${H1[@]}" CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$HOOK" 2>&1)"
  HOOK_RC=$?
  set -e
}
md_hook SessionStart "$SS" "$SR" "$STX" startup
run env "${H1[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "stall: synced" "a project mirrored over ssh syncs"
run env "${H2[@]}" "$SMINOS" project attach
run env "${H2[@]}" "$SMINOS" say "from h2 before the stall"
run env "${H2[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "stall: synced" "the other home pushes to it"
GATE="$MD/ssh-gate"
touch "$GATE"
rm -f "$MD/ssh-entered"
env "${H1[@]}" SSH_GATE="$GATE" SSH_ENTERED="$MD/ssh-entered" "$SMINOS" daemon tick > "$MD/stalled-tick.out" 2>&1 & STALLED=$!
for _ in $(seq 1 100); do [ -f "$MD/ssh-entered" ] && break; sleep 0.05; done
assert_file_exists "$MD/ssh-entered" "h1's tick is inside a fetch that hangs"
T0="$(clock)"
run env "${H1[@]}" "$SMINOS" say "said while the fetch hangs"
SAY_TOOK="$(since "$T0")"
assert_rc 0 "$RC" "a say during the hung fetch records"
if python3 -c 'import sys; sys.exit(float(sys.argv[1]) > 2.0)' "$SAY_TOOK"; then pass "unblocked (${SAY_TOOK}s)"; else
  fail "unblocked"; echo "    took ${SAY_TOOK}s"; fi
tx "$STX" asst 5b000002 "<message>exported while the fetch hangs</message>"
T0="$(clock)"
md_hook Stop "$SS" "$SR" "$STX"
STOP_TOOK="$(since "$T0")"
assert_contains "$(cat "$SLOG/h1.$SS.jsonl")" "exported while the fetch hangs" "a Stop export during the hung fetch records the message"
if python3 -c 'import sys; sys.exit(float(sys.argv[1]) > 2.0)' "$STOP_TOOK"; then pass "unblocked (${STOP_TOOK}s)"; else
  fail "unblocked"; echo "    took ${STOP_TOOK}s"; fi
if kill -0 "$STALLED" 2>/dev/null; then pass "while the tick still waits on the fetch"; else fail "while the tick still waits on the fetch"; fi
rm -f "$GATE"
wait "$STALLED" || true
assert_contains "$(cat "$MD/stalled-tick.out")" "stall: synced" "released, the tick integrates"
SAID="$(gitq -C "$SLOG" log -S'said while the fetch hangs' --format=%H | tail -1)"
EXPORTED="$(gitq -C "$SLOG" log -S'exported while the fetch hangs' --format=%H | tail -1)"
# The commit holding both appends is the merge's first parent: committed in the
# phase that merged, not after it.
MERGES="$(gitq -C "$SLOG" rev-list --merges --parents HEAD)"
if [[ -n "$SAID" && "$SAID" == "$EXPORTED" ]] && grep -q "^[0-9a-f]* $SAID " <<<"$MERGES"; then
  pass "what was appended during the fetch is committed before the remote is merged, in the same phase"
else fail "what was appended during the fetch is committed before the remote is merged, in the same phase"
  echo "    said=$SAID exported=$EXPORTED"; gitq -C "$SLOG" log --graph --format='%h %p %s' | sed 's/^/    /'; fi
assert_contains "$(cat "$SLOG/h2.human.jsonl")" "from h2 before the stall" "the other home's history is integrated"
assert_contains "$(gitq -C "$STALL" log -p main)" "said while the fetch hangs" "and h1's append is pushed"
# A fetch past its bound is abandoned, and the tick goes on.
touch "$GATE"
T0="$(clock)"
run env "${H1[@]}" SSH_GATE="$GATE" SMINOS_GIT_TIMEOUT=1 "$SMINOS" daemon tick
TOOK="$(since "$T0")"
rm -f "$GATE"
assert_contains "$OUT" "stall: not synced" "a fetch that hangs past its bound is abandoned"
assert_contains "$OUT" "demo: synced" "and the tick goes on with the other projects"
if python3 -c 'import sys; sys.exit(float(sys.argv[1]) > 5.0)' "$TOOK"; then pass "within its bound (${TOOK}s for 1s)"; else
  fail "within its bound"; echo "    took ${TOOK}s"; fi
assert_contains "$(cat "$MD/h1/sminos/daemon.log")" "timed out after 1s" "daemon.log says why"
run env "${H1[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "stall: synced" "the next tick syncs again"
unset GIT_SSH_COMMAND GIT_SSH_VARIANT
cd "$RR"

# One machine, a project with no remote: the daemon delivers what the fast
# path left owed. x and y are seats; a seat whose session is down is resumed
# by a tag, and a resume that does not launch is a failed push.
LR2="$MD/solo-repo"
mkdir -p "$LR2"
gitq init -q "$LR2"
cd "$LR2"
run env "${SOLO[@]}" "$SMINOS" spawn x "wait"
X="$(banner_uuid "$OUT")"
run env "${SOLO[@]}" "$SMINOS" spawn y "wait"
Y="$(banner_uuid "$OUT")"
SOLOP=local-solo-repo
md_peer solo x "$X" idle bg "$LR2"
STUB_FAIL_BG=1 run env "${SOLO[@]}" "$SMINOS" say "@x @y both of you"
assert_contains "$OUT" "x: sent" "an event to two local members reaches the first"
assert_contains "$OUT" "y: failed" "and the second's push fails"
md_peer solo y "$Y" idle bg "$LR2"
run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "solo-repo: reconciled 0 · delivered 1 to y" "a later tick delivers it to the second"
run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "delivered 0" "and nothing more"
assert_equals "$(bodies md-x | grep -c 'both of you$')" 1 "the first received it once"
assert_equals "$(bodies md-y | grep -c 'both of you$')" 1 "the second once"

# A daemon restarted between the push and the record delivers at most once more.
rm -f "$MD/solo/.claude/sessions/y.json"
STUB_FAIL_BG=1 run env "${SOLO[@]}" "$SMINOS" say "@y restart me"
assert_contains "$OUT" "y: failed" "an event to y is owed"
md_peer solo y "$Y" idle bg "$LR2"
touch "$TEST_ROOT/in-md-y.received.hold"
rm -f "$TEST_ROOT/in-md-y.received.held"
env "${SOLO[@]}" "$SMINOS" daemon tick > /dev/null 2>&1 & DOOMED=$!
disown "$DOOMED"
for _ in $(seq 1 100); do [ -f "$TEST_ROOT/in-md-y.received.held" ] && break; sleep 0.05; done
assert_file_exists "$TEST_ROOT/in-md-y.received.held" "a tick pushes to y"
kill -9 "$DOOMED"
for _ in $(seq 1 100); do kill -0 "$DOOMED" 2>/dev/null || break; sleep 0.05; done
rm -f "$TEST_ROOT/in-md-y.received.hold"
run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "delivered 1 to y" "killed before settling it, the restarted daemon pushes it again"
run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "delivered 0" "and then never again"
assert_equals "$(bodies md-y | grep -c '^@y restart me$')" 2 "at most once more: two frames in all"
# A push that keeps failing is retried each tick and given up on the 60th
# attempt: settled, with a line in daemon.log naming the event and the member.
rm -f "$MD/solo/.claude/sessions/y.json"
STUB_FAIL_BG=1 run env "${SOLO[@]}" "$SMINOS" say "@y never arrives"
GIVEUP_SEQ="$(seq_of "$MD/solo/sminos/projects/$SOLOP/log/solo.human.jsonl")"
python3 - "$MD/solo/sminos/projects/$SOLOP/delivered/$Y.json" <<'PY_ATTEMPTS'
import json, sys
d = json.load(open(sys.argv[1]))
d["solo/human"]["attempts"] = 58
json.dump(d, open(sys.argv[1], "w"))
PY_ATTEMPTS
STUB_FAIL_BG=1 run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "delivered 0" "the 59th attempt fails"
assert_contains "$(cat "$MD/solo/sminos/projects/$SOLOP/delivered/$Y.json")" '"pending": '"$GIVEUP_SEQ"', "attempts": 59' "and stays pending"
STUB_FAIL_BG=1 run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$(cat "$MD/solo/sminos/projects/$SOLOP/delivered/$Y.json")" '"settled": '"$GIVEUP_SEQ"', "pending": null' "the 60th settles it"
assert_contains "$(cat "$MD/solo/sminos/daemon.log")" "gave up delivering solo/human:$GIVEUP_SEQ (solo-repo) to $Y after 60 attempts" "with a line in daemon.log"
CALLS_BEFORE="$(grep -c -- "--resume $Y" "$MD/solo/stub/log/calls.log")"
run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_equals "$(grep -c -- "--resume $Y" "$MD/solo/stub/log/calls.log")" "$CALLS_BEFORE" "and it is never tried again"

# daemon run: an owed event in a remote-less project is delivered while a
# derivation child sleeps (one at a time), and a session that appears after
# the loop started is seen.
rm -f "$MD/solo/.claude/sessions/y.json"
STUB_FAIL_BG=1 run env "${SOLO[@]}" "$SMINOS" say "@y from before the run"
assert_contains "$OUT" "y: failed" "another event to y is owed"
SL=5c000005-0000-4000-8000-00000000005c
SLX="$MD/solo/.claude/projects/sl/$SL.jsonl"
mkdir -p "$(dirname "$SLX")"
for i in 1 2 3 4 5 6 7 8 9 10; do tx "$SLX" prompt "5d0000$i" "prompt $i"; tx "$SLX" asst "5e0000$i" "answer $i"; done
md_peer solo sleeper "$SL" idle interactive "$LR2"
env "${SOLO[@]}" STUB_FAIL_BG=1 SMINOS_DERIVE_EVERY=1 STUB_FORK_SLEEP=10 STUB_FORK_RESULT="watches the sleepy fixture" \
  "$SMINOS" daemon run --interval 1 > "$MD/run-solo.out" 2>&1 & RUNS=$!
for _ in $(seq 1 100); do grep -q '^fork-env:' "$MD/solo/stub/log/calls.log" 2>/dev/null && break; sleep 0.05; done
assert_contains "$(cat "$MD/solo/stub/log/calls.log")" "fork-env:internal=1" "run starts derive --all, whose fork sleeps"
md_peer solo y "$Y" idle bg "$LR2"
for _ in $(seq 1 100); do grep -q 'from before the run' "$TEST_ROOT/in-md-y.received" && break; sleep 0.05; done
assert_contains "$(md_inbox y)" "from before the run" "run delivers an owed event in a project with no remote"
assert_not_contains "$(cat "$MD/solo/sminos/projects/$SOLOP/log/solo.$SL.jsonl")" '"source": "derived"' "while the derivation child still sleeps"
NC=5f00000f-0000-4000-8000-00000000005f
md_peer solo newcomer "$NC" idle interactive "$LR2"
for _ in $(seq 1 100); do grep -q '"kind": "joined"' "$MD/solo/sminos/projects/$SOLOP/log/solo.$NC.jsonl" 2>/dev/null && break; sleep 0.05; done
assert_contains "$(cat "$MD/solo/sminos/projects/$SOLOP/log/solo.$NC.jsonl" 2>/dev/null)" '"kind": "joined"' "run sees a session that appeared after it started"
assert_equals "$(grep -c '^fork-env:' "$MD/solo/stub/log/calls.log")" 1 "one derivation in flight at a time, though one is due every second"
kill "$RUNS"; wait "$RUNS" || true
assert_contains "$(cat "$MD/run-solo.out")" "delivered 1 to y" "the loop reports the delivery"
for _ in $(seq 1 300); do grep -q '"source": "derived"' "$MD/solo/sminos/projects/$SOLOP/log/solo.$SL.jsonl" && break; sleep 0.05; done
assert_contains "$(cat "$MD/solo/sminos/projects/$SOLOP/log/solo.$SL.jsonl")" '"text": "watches the sleepy fixture", "source": "derived"' "the derivation finishes on its own"
# A harness rename is recorded in a project with no remote too: the only
# record of a name change.
printf '{"pid":%s,"sessionId":"%s","name":"night-shift","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s","messagingSocketPath":"%s"}\n' \
  "$SOCK_PID" "$NC" "$LR2" "$TEST_ROOT/in-md-newcomer.sock" > "$MD/solo/.claude/sessions/newcomer.json"
run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "solo-repo: reconciled 0 · published 1" "a tick in a project with no remote publishes a harness rename"
assert_contains "$(tail -1 "$MD/solo/sminos/projects/$SOLOP/log/solo.$NC.jsonl")" '"kind": "renamed", "session": "'"$NC"'", "alias": "night-shift", "name_source": "user"' "as renamed, with the name's source"
assert_not_contains "$(cat "$MD/solo/sminos/projects/$SOLOP/log/solo.$NC.jsonl")" '"kind": "state"' "and no state: only another machine reads that"
run env "${SOLO[@]}" "$SMINOS" daemon tick
assert_contains "$OUT" "solo-repo: reconciled 0 · delivered 0" "once"
cd "$RR"

# daemon install writes the launchd agent under the HOME it is given and loads nothing.
mkdir -p "$MD/inst/.claude" "$MD/lc"
printf '{"env": {"ANTHROPIC_BASE_URL": "x", "ANTHROPIC_AUTH_TOKEN": "y"}}\n' > "$MD/inst/.claude/clodex-settings.json"
printf '#!/bin/sh\necho "$*" >> "%s/launchctl.calls"\n' "$MD" > "$MD/lc/launchctl"
chmod +x "$MD/lc/launchctl"
run env HOME="$MD/inst" SMINOS_HOME="$MD/inst/sminos" PATH="$MD/lc:$PATH" ANTHROPIC_BASE_URL=http://gateway.test "$SMINOS" daemon install
assert_rc 0 "$RC" "daemon install succeeds"
PLIST="$MD/inst/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist"
assert_file_exists "$PLIST" "it writes the agent under the HOME it is given"
assert_contains "$OUT" "launchctl bootstrap gui/" "and says how to load it"
assert_file_absent "$MD/launchctl.calls" "loading nothing itself"
assert_equals "$(python3 - "$PLIST" "$MD/inst/sminos" "$SMINOS" <<'PY_PLIST'
import os, plistlib, sys
d = plistlib.load(open(sys.argv[1], "rb"))
env = d["EnvironmentVariables"]
print(d["Label"], d["ProgramArguments"][1:], os.path.realpath(d["ProgramArguments"][0]) == os.path.realpath(sys.argv[3]),
      env["SMINOS_HOME"] == sys.argv[2], env.get("ANTHROPIC_BASE_URL"), "ANTHROPIC_AUTH_TOKEN" in env,
      bool(env.get("PATH")), d["KeepAlive"], d["RunAtLoad"])
PY_PLIST
)" "com.doperpowers.sminos-daemon ['daemon', 'run'] True True http://gateway.test False True True True" \
  "a well-formed plist: daemon run through this CLI, SMINOS_HOME, PATH, and the gateway route as the environment sets it"
assert_equals "$(mode_of "$PLIST")" "0600" "readable only by its owner: it may carry the gateway's token"
# A CLI running from the versioned plugin cache installs the marketplace
# clone's CLI, which plugin updates keep; with no clone known, itself.
CACHE="$MD/inst/.claude/plugins/cache/doperpowers/doperpowers/9.9.9"
MKT="$MD/inst/.claude/plugins/marketplaces/doperpowers"
mkdir -p "$CACHE/skills" "$MKT/skills/sminos/scripts"
cp -R "$REPO_ROOT/skills/sminos" "$CACHE/skills/"
printf '#!/bin/sh\n' > "$MKT/skills/sminos/scripts/sminos"
chmod +x "$MKT/skills/sminos/scripts/sminos"
printf '{"doperpowers": {"installLocation": "%s", "autoUpdate": true}}\n' "$MKT" > "$MD/inst/.claude/plugins/known_marketplaces.json"
plist_cli() { python3 -c 'import os, plistlib, sys; print(os.path.realpath(plistlib.load(open(sys.argv[1], "rb"))["ProgramArguments"][0]))' "$PLIST"; }
real() { python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
run env HOME="$MD/inst" SMINOS_HOME="$MD/inst/sminos" PATH="$MD/lc:$PATH" "$CACHE/skills/sminos/scripts/sminos" daemon install
assert_rc 0 "$RC" "install from the plugin cache succeeds"
assert_equals "$(plist_cli)" "$(real "$MKT/skills/sminos/scripts/sminos")" "and runs the marketplace clone's CLI, not the versioned cache's"
rm "$MD/inst/.claude/plugins/known_marketplaces.json"
run env HOME="$MD/inst" SMINOS_HOME="$MD/inst/sminos" PATH="$MD/lc:$PATH" "$CACHE/skills/sminos/scripts/sminos" daemon install
assert_equals "$(plist_cli)" "$(real "$CACHE/skills/sminos/scripts/sminos")" "with no marketplace clone known, it runs itself"
assert_file_absent "$MD/launchctl.calls" "still loading nothing"
# run notices new code: a change to its own scripts ends the loop with exit 0,
# for launchd's KeepAlive to restart it on the new code.
env HOME="$MD/inst" SMINOS_HOME="$MD/inst/sminos" "$CACHE/skills/sminos/scripts/sminos" daemon run --interval 1 > "$MD/run-code.out" 2>&1 & RUNC=$!
sleep 1.5
touch "$CACHE/skills/sminos/scripts/sminos_daemon.py"
for _ in $(seq 1 100); do kill -0 "$RUNC" 2>/dev/null || break; sleep 0.05; done
if kill -0 "$RUNC" 2>/dev/null; then fail "run exits once its code changes"; kill "$RUNC"; wait "$RUNC" || true; else
  set +e; wait "$RUNC"; RUNC_RC=$?; set -e
  assert_rc 0 "$RUNC_RC" "run exits 0 once its code changes"
fi
assert_contains "$(cat "$MD/run-code.out")" "its code changed" "saying why"
run env "${H1[@]}" "$SMINOS" daemon
assert_rc 2 "$RC" "daemon with no verb is a usage error"
cd "$WORK"
unset STUB_COUNTER

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  exit 1
fi
