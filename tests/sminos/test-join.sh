#!/usr/bin/env bash
#
# A session's project and its moves (M4 of the sminos org directory,
# docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md §1a, §1c,
# §7): a session's project comes from its launch directory — the transcript's
# latest `relocated` row, else its first row's cwd, as the engine reads a
# session's directory — never from where its shell is now, so the record
# hook, the bridge's export and the members a reconciliation sees stay put
# through a `cd`; a .smns appearing or disappearing under the launch
# directory moves a live session within one tick (`retired` with reason
# `moved` in the old log, `joined` by `move` in the new); `sminos join`
# declares a project (an override file), refuses a seat and a target the
# session cannot sync in, and `join --cwd` takes it back; hand-off carries an
# override; the daemon sweeps an override whose transcript is gone, a month
# quiet, or whose target turned ineligible. Two machines simulated on one Mac
# (two enrolled SMINOS_HOMEs against hub_standin.py) for what crosses them.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$REPO_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"
HOOK="${SMINOS_HOOK:-$REPO_ROOT/hooks/smns-record.sh}"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smj.XXXXXX)"
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
  for _ in $(seq 1 60); do pgrep -f "$T/" >/dev/null 2>&1 || break; sleep 0.05; done
  rm -rf "$T"
}
trap cleanup EXIT

pass() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
fail() { FAILURES=$((FAILURES + 1)); echo "  FAIL $1"; }
assert_equals() {
  if [[ "$1" == "$2" ]]; then pass "$3"; else
    fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
  if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:900}"; fi
}
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:900}"
  else pass "$3"; fi
}
assert_rc() { if [[ "$1" == "$2" ]]; then pass "$3"; else fail "$3"; echo "    expected rc $1, got $2"; fi; }
run_in() { # dir command... — OUT and RC of the command run there
  local d=$1; shift
  set +e; OUT="$(cd "$d" && "$@" 2>&1)"; RC=$?; set -e
}
# Polls every 50 ms until the command holds; one liveness bound, 30 s (ci-kit §6).
until_true() {
  local end=$((SECONDS + 30))
  until "$@"; do
    [ "$SECONDS" -ge "$end" ] && return 1
    sleep 0.05
  done
}
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin"
as() { # a|b|c host — one machine: its HOME, its SMINOS_HOME, its host name
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-0 secret-0 1000 & PIDS+=("$!")
until_true test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"

cat > "$T/ctl.py" <<'PY'
import base64, http.client, json, sys
port = int(open(sys.argv[1]).read())

def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    c.request(method, path, body=None if body is None else json.dumps(body), headers={"Content-Type": "application/json"})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")

cmd, args = sys.argv[2], sys.argv[3:]
if cmd == "token":
    print(call("POST", "/control/enrollment", {})[1]["token"])
elif cmd == "code":  # hub token machine key
    body = json.dumps(dict(zip(("hub", "org", "token", "machine", "key"), [args[0], "org-1", *args[1:4]])),
                      separators=(",", ":")).encode()
    print("smns-enroll-v1." + base64.urlsafe_b64encode(body).rstrip(b"=").decode())
elif cmd == "state":  # a python expression over the state, d
    print(json.dumps(eval(args[0], {"d": call("GET", "/control/state")[1], "json": json})))
elif cmd == "register":  # project name [kind]
    call("POST", "/control/register", {"project": args[0], "name": args[1], "kind": (args[2:] or ["hub"])[0]})
elif cmd == "retire":  # project true|false
    call("POST", "/control/retire", {"project": args[0], "retired": args[1] == "true"})
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }
mp_of() { python3 -c 'import sys, uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:org-1:" + sys.argv[1].lower()))' "$1"; }
smns_id() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$1/.smns"; }
write_smns() { # dir name — a .smns naming only the org
  python3 -c 'import json, sys, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": sys.argv[1], "remote": "", "hub": {"org": "org-1"}}, indent=2))' \
    "$2" > "$1/.smns"
}
live_pid() { sleep 600 & LIVE_PID=$!; PIDS+=("$LIVE_PID"); }
session_record() { # name session pid cwd [kind] [nameSource] — an engine record for a running session
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"%s","kind":"%s","status":"idle","cwd":"%s"}\n' \
    "$3" "$2" "$1" "${6:-user}" "${5:-interactive}" "$4" > "$HOME/.claude/sessions/$1.json"
}
transcript() { # session cwd... — a transcript whose rows ran in each cwd in turn (the first: where it launched)
  local sid=$1; shift
  local tx="$HOME/.claude/projects/p-$sid/$sid.jsonl"
  mkdir -p "$(dirname "$tx")"
  : > "$tx"
  local n=0
  for d in "$@"; do
    n=$((n + 1))
    printf '{"type":"user","uuid":"%s-u%d","isSidechain":false,"sessionId":"%s","cwd":"%s","origin":{"kind":"human"},"message":{"role":"user","content":"step %d"}}\n' \
      "${sid:0:8}" "$n" "$sid" "$d" "$n" >> "$tx"
  done
  TX="$tx"
}
# A project's log as `kind alias-or-session reason project by cwd` lines, for one session.
events_of() { # project-id session
  python3 - "$SMINOS_HOME/projects/$1/log" "$2" <<'PY'
import glob, json, os, sys
d, sid = sys.argv[1], sys.argv[2]
rows = []
for p in glob.glob(os.path.join(d, "*.jsonl")):
    for line in open(p):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("session") == sid and e.get("kind") in ("joined", "retired"):
            rows.append((e["writer"], e["seq"], e))
for _, _, e in sorted(rows, key=lambda r: (r[0], r[1])):
    print(" ".join(str(e.get(k, "")) or "-" for k in ("kind", "reason", "project", "by", "cwd")))
PY
}
members_of() { # project (name or id) → the sessions it lists, from a bare directory
  (cd "$T/x" && "$SMINOS" list "$1" --json --all) | python3 -c 'import json, sys
print(" ".join(sorted(r["alias"] for r in json.load(sys.stdin) if r["state"] not in ("retired", "gone"))))'
}
override_of() { # session → the project its override names, or "none"
  python3 -c 'import json, sys
try:
    print(json.load(open(sys.argv[1]))["project"])
except OSError:
    print("none")' "$SMINOS_HOME/sessions/$1.json"
}
in_session() { # session command... — the command as that session runs it
  local sid=$1; shift
  env CLAUDE_CODE_SESSION_ID="$sid" "$@"
}

# ---- alpha: a local project before it enrolls, then enrolled
as a alpha
mkdir -p "$T/x"
LR="$T/a/legacy"
gitq init -q "$LR"
run_in "$LR" "$SMINOS" say "a local project"
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" alpha "$KEY")" >/dev/null
AMP="$(mp_of alpha)"

echo "a .smns appearing under a live session moves it:"
R="$T/a/scratch"
gitq init -q "$R"
S1=1a000001-0000-4000-8000-000000000001
live_pid
S1_PID=$LIVE_PID
session_record s1 "$S1" "$S1_PID" "$R"
transcript "$S1" "$R"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(members_of alpha)" "s1" "a session in a repository with no .smns is a member of the machine project"
write_smns "$R" scratch
SPID="$(smns_id "$R")"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(events_of "$AMP" "$S1")" "joined - - - $R
retired moved $SPID - -" "the next tick retires it in the machine project, reason moved, naming the new project"
assert_equals "$(events_of "$SPID" "$S1")" "joined - - move $R" "and joins it in the new one, by move, with its launch directory"
assert_equals "$(members_of alpha)" "" "list --project alpha no longer lists it"
run_in "$R" "$SMINOS" list --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print([(r["alias"], r["project"]) for r in json.load(sys.stdin)])')" "[('s1', 'scratch')]" "list in the repository lists it under the new project"
run_in "$T/x" "$SMINOS" chat alpha -n 10
assert_contains "$OUT" "s1 retired (moved to scratch)" "chat in the machine project shows it moved, naming the project"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(events_of "$SPID" "$S1" | wc -l | tr -d ' ')" 1 "a later tick writes nothing more"

echo "a session's project is its launch directory's:"
B2="$T/a/bare2"
mkdir -p "$B2"
OR="$T/a/other"
gitq init -q "$OR"
write_smns "$OR" other
OPID="$(smns_id "$OR")"
run_in "$OR" "$SMINOS" say "other is here"   # registered, so what members_of says of it below is read
S2=1a000002-0000-4000-8000-000000000002
live_pid
session_record s2 "$S2" "$LIVE_PID" "$OR"   # the engine's record follows the shell: it is in other now
transcript "$S2" "$B2" "$OR" "$B2" "$OR"     # launched in bare2, its rows in both since
hook_payload() { # event session cwd transcript
  printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","hook_event_name":"%s","source":"startup"}' "$2" "$4" "$3" "$1"
}
hook_payload SessionStart "$S2" "$OR" "$TX" | CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$HOOK"
printf '{"type":"assistant","uuid":"s2-a1","isSidechain":false,"cwd":"%s","message":{"role":"assistant","content":[{"type":"text","text":"<message>said while in other</message>"}]}}\n' "$OR" >> "$TX"
hook_payload Stop "$S2" "$OR" "$TX" | CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$HOOK"
assert_contains "$(cat "$SMINOS_HOME/projects/$AMP/log/"*.jsonl)" "said while in other" \
  "the record hook exports to the launch directory's project, though the payload's cwd is another project's"
assert_not_contains "$(cat "$SMINOS_HOME/projects/$OPID/log/"*.jsonl 2>/dev/null)" "said while in other" "and not to the other"
python3 - "$OR" "$S2" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
rec = {"type": "assistant", "uuid": "s2-a2", "isSidechain": False, "cwd": sys.argv[1],
       "message": {"role": "assistant", "content": [{"type": "text", "text": "<message>live from other</message>"}]}}
sminos.export_live(sys.argv[1], sys.argv[2], [rec])
PY
assert_contains "$(cat "$SMINOS_HOME/projects/$AMP/log/"*.jsonl)" "live from other" \
  "the bridge's export too, though the bridge names the other directory"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(members_of other)" "" "the other project's reconciliation does not join it"
assert_contains " $(members_of alpha) " " s2 " "it stays a member of its launch directory's project"
assert_equals "$(events_of "$AMP" "$S2")" "joined - - - $B2" "joined once, carrying the launch directory, never moved"
assert_equals "$(events_of "$OPID" "$S2")" "" "nothing of it in the other project's log"
write_smns "$B2" bare2
B2PID="$(smns_id "$B2")"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(events_of "$AMP" "$S2" | tail -1)" "retired moved $B2PID - -" "a .smns added under the launch directory still moves it"
assert_equals "$(events_of "$B2PID" "$S2")" "joined - - move $B2" "into the launch directory's new project"

echo "a session the engine relocated:"
S3=1a000003-0000-4000-8000-000000000003
B3="$T/a/bare3"
mkdir -p "$B3"
live_pid
session_record s3 "$S3" "$LIVE_PID" "$B3"
transcript "$S3" "$B3"
printf '{"type":"relocated","sessionId":"%s","relocatedCwd":"%s"}\n' "$S3" "$OR" >> "$TX"
printf '{"type":"user","uuid":"s3-u9","isSidechain":false,"cwd":"%s","message":{"role":"user","content":"back"}}\n' "$B3" >> "$TX"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(members_of other)" "s3" "a transcript's latest relocated row names the session's directory (/cd, EnterWorktree)"
assert_equals "$(events_of "$OPID" "$S3")" "joined - - - $OR" "and its joined carries that directory"
S14=1a000014-0000-4000-8000-000000000014
assert_equals "$(python3 - "$S14" "$B3" "$HOME/.claude/projects/p-$S14/$S14.jsonl" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
sid, launch, tx = sys.argv[1:4]
os.makedirs(os.path.dirname(tx), exist_ok=True)
with open(tx, "w") as f:   # a first row past 64 KiB, its cwd near its start: a long pasted prompt
    f.write(json.dumps({"type": "user", "cwd": launch, "sessionId": sid,
                        "message": {"role": "user", "content": "x" * 70000}}) + "\n")
print(sminos.launch_cwd(sid, fallback="/current"))
PY
)" "$B3" "a first row longer than 64 KiB is read to its end for its cwd, never the current directory"
assert_equals "$(python3 - "$S14" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
tx = sminos.transcript_path(sys.argv[1])
with open(tx, "w") as f:   # a row still being written: no row yet
    f.write('{"type": "user", "cwd": "/launch", "mess')
if os.path.exists(sminos.launch_cache_path(sys.argv[1])):
    os.unlink(sminos.launch_cache_path(sys.argv[1]))
print(sminos.launch_cwd(sys.argv[1], fallback="/current"))
PY
)" "/current" "only before a whole row exists does the current directory stand in"

echo "a seat the engine relocated:"
SEAT2=1a000015-0000-4000-8000-000000000015
run_in "$B3" "$SMINOS" seat add crew mover --session "$SEAT2"
live_pid
session_record mover "$SEAT2" "$LIVE_PID" "$B3"
transcript "$SEAT2" "$B3"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_contains " $(members_of alpha) " " mover " "a seat launched in a bare directory is in the machine project"
printf '{"type":"relocated","sessionId":"%s","relocatedCwd":"%s"}\n' "$SEAT2" "$B2" >> "$TX"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_not_contains " $(members_of alpha) " " mover " "relocated into another project, the seat leaves its spawn directory's project"
assert_contains " $(members_of bare2) " " mover " "and is a member of the project its session now runs in, as its engine record is"
assert_equals "$(events_of "$B2PID" "$SEAT2" | tail -1)" "joined - - move $B2" "joined there with the relocated directory"

echo "a session relocated within its project (a worktree):"
WR="$T/a/wtp"
gitq init -q "$WR"
write_smns "$WR" wtp
WPID="$(smns_id "$WR")"
gitq -C "$WR" add .smns
gitq -C "$WR" commit -q -m smns
gitq -C "$WR" worktree add -q -b one "$WR/.claude/worktrees/one"
gitq -C "$WR" worktree add -q -b two "$WR/.claude/worktrees/two"
S13=1a000013-0000-4000-8000-000000000013
live_pid
session_record s13 "$S13" "$LIVE_PID" "$WR/.claude/worktrees/one"
transcript "$S13" "$WR/.claude/worktrees/one"
S13_TX=$TX
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(events_of "$WPID" "$S13")" "joined - - - $WR/.claude/worktrees/one" "a session launched in a worktree joins with the worktree"
printf '{"type":"relocated","sessionId":"%s","relocatedCwd":"%s"}\n' "$S13" "$WR" >> "$S13_TX"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(events_of "$WPID" "$S13" | tail -1)" "joined - - - $WR" \
  "leaving the worktree (the engine relocates it) refreshes its joined directory, in the same project"
gitq -C "$WR" worktree remove --force "$WR/.claude/worktrees/one"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
run_in "$WR" "$SMINOS" list --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print([r["cwd"] for r in json.load(sys.stdin) if r["alias"] == "s13"])')" "['$WR']" \
  "with its former directory removed, its row names the directory Resume can use"
printf '{"type":"relocated","sessionId":"%s","relocatedCwd":"%s"}\n' "$S13" "$WR/.claude/worktrees/two" >> "$S13_TX"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(events_of "$WPID" "$S13")" "joined - - - $WR/.claude/worktrees/one
joined - - - $WR
joined - - - $WR/.claude/worktrees/two" "entering another worktree refreshes it again: one event per relocation, never per tick, never a move"

echo "sminos join:"
run_in "$R" "$SMINOS" join other
assert_rc 2 "$RC" "join outside a session is a usage error"
run_in "$T/x" in_session "$S1" "$SMINOS" join
assert_contains "$OUT" "scratch" "join alone names the session's project"
assert_contains "$OUT" "no override" "and that no override holds"
run_in "$T/x" in_session "$S1" "$SMINOS" join other
assert_rc 0 "$RC" "join other"
assert_equals "$(override_of "$S1")" "$OPID" "writes the override"
assert_equals "$(events_of "$SPID" "$S1" | tail -1)" "retired moved $OPID - -" "retires it in its project, moved to the target"
assert_equals "$(events_of "$OPID" "$S1")" "joined - - join $R" "and joins it there before returning, by join, with its launch directory"
run_in "$T/x" "$SMINOS" list other --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print([r["cwd"] for r in json.load(sys.stdin) if r["alias"] == "s1"])')" "['$R']" "list other shows it with its real cwd"
run_in "$T/x" in_session "$S1" "$SMINOS" join
assert_contains "$OUT" "other" "join alone names the project joined"
assert_contains "$OUT" "scratch" "and the directory's"
run_in "$T/x" in_session "$S1" "$SMINOS" join other
assert_rc 0 "$RC" "joining the project it is in"
assert_contains "$OUT" "already" "is a no-op that says so"
assert_equals "$(events_of "$OPID" "$S1" | wc -l | tr -d ' ')" 1 "and writes nothing"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(members_of other)" "s1 s3" "a tick keeps it where it joined"
run_in "$T/x" in_session "$S1" "$SMINOS" join --cwd
assert_rc 0 "$RC" "join --cwd"
assert_equals "$(override_of "$S1")" "none" "removes the override"
assert_equals "$(events_of "$OPID" "$S1" | tail -1)" "retired moved $SPID - -" "and moves it back to its directory's project"
assert_equals "$(events_of "$SPID" "$S1" | tail -1)" "joined - - join $R" "joined there again"

echo "a session moving back into a project exports only what is new:"
S16=1a000016-0000-4000-8000-000000000016
B16="$T/a/bare16"
mkdir -p "$B16"
live_pid
session_record s16 "$S16" "$LIVE_PID" "$B16"
transcript "$S16" "$B16"
S16_TX=$TX
mark16() { # n text — an assistant row carrying a <message> mark
  printf '{"type":"assistant","uuid":"s16-a%s","isSidechain":false,"cwd":"%s","message":{"role":"assistant","content":[{"type":"text","text":"<message>%s</message>"}]}}\n' \
    "$1" "$B16" "$2" >> "$S16_TX"
}
stop16() { hook_payload Stop "$S16" "$B16" "$S16_TX" | CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$HOOK"; }
count_in() { cat "$SMINOS_HOME/projects/$1/log/"*.jsonl 2>/dev/null | grep -c -- "$2" || true; }
hook_payload SessionStart "$S16" "$B16" "$S16_TX" | CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$HOOK"
mark16 1 "sixteen in alpha"
stop16
run_in "$T/x" in_session "$S16" "$SMINOS" join other
mark16 2 "sixteen in other"
stop16
run_in "$T/x" in_session "$S16" "$SMINOS" join --cwd
mark16 3 "sixteen back in alpha"
stop16
assert_equals "$(count_in "$AMP" "sixteen in alpha") $(count_in "$AMP" "sixteen back in alpha")" "1 1" \
  "its machine project holds what it said there, before and after its stint in other"
assert_equals "$(count_in "$AMP" "sixteen in other")" 0 \
  "and nothing it said in other: back from a move, its export resumes where its last export stopped, wherever that ran"
assert_equals "$(count_in "$OPID" "sixteen in other") $(count_in "$OPID" "sixteen in alpha")" "1 0" \
  "the project it moved into holds what it said there, and nothing exported before the move"

echo "an override survives a .smns appearing:"
S4=1a000004-0000-4000-8000-000000000004
B4="$T/a/bare4"
mkdir -p "$B4"
live_pid
session_record s4 "$S4" "$LIVE_PID" "$B4"
transcript "$S4" "$B4"
run_in "$T/x" in_session "$S4" "$SMINOS" join other
write_smns "$B4" bare4
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(override_of "$S4")" "$OPID" "the override stands"
assert_contains " $(members_of other) " " s4 " "and the session stays in the project it joined"
assert_equals "$(events_of "$(smns_id "$B4")" "$S4")" "" "never joined in the directory's new project"

echo "refusals:"
run_in "$T/x" in_session "$S4" "$SMINOS" join local-legacy
assert_rc 1 "$RC" "join local-<name> on an enrolled machine is refused"
assert_contains "$OUT" "history" "saying a local project is kept only as history"
SEAT=1a000005-0000-4000-8000-000000000005
run_in "$R" "$SMINOS" seat add crew seatling --session "$SEAT"
run_in "$T/x" in_session "$SEAT" "$SMINOS" join other
assert_rc 1 "$RC" "join from a seat is refused"
assert_contains "$OUT" "a seat's project is where it was spawned" "saying why"
run_in "$T/x" in_session "$S4" "$SMINOS" join nowhere-known
assert_rc 4 "$RC" "a project not known here is unknown"

echo "hand-off carries the override:"
S6=1a000006-0000-4000-8000-000000000006
S7=1a000007-0000-4000-8000-000000000007
B6="$T/a/bare6"
mkdir -p "$B6"
live_pid
S6_PID=$LIVE_PID
session_record s6 "$S6" "$S6_PID" "$B6"
transcript "$S6" "$B6"
S6_TX=$TX
run_in "$T/x" in_session "$S6" "$SMINOS" join other
printf '{"type":"continued-in","continuedInSessionId":"%s"}\n' "$S7" >> "$S6_TX"
live_pid
session_record s7 "$S7" "$LIVE_PID" "$B6" bg derived   # a background job's name is one the harness made up
transcript "$S7" "$B6"
"$SMINOS" daemon tick >/dev/null 2>&1 || true   # its predecessor still exiting, in the project it joined
kill "$S6_PID"; wait "$S6_PID" 2>/dev/null || true
rm -f "$HOME/.claude/sessions/s6.json"
for _ in 1 2 3; do "$SMINOS" daemon tick >/dev/null 2>&1 || true; done
assert_equals "$(override_of "$S7")" "$OPID" "the successor holds the override its predecessor held"
assert_contains " $(members_of other) " " s6 " "and stands in the joined project under the alias its predecessor held there"
assert_not_contains " $(members_of other) " " s7 " "never under the name the harness made up for it"
assert_equals "$(python3 - "$OPID" "$S7" <<'PY'
import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
p, sid = sminos.find_project(sys.argv[1]), sys.argv[2]
print(" ".join(e["alias"] for e in sminos._own_events(p, sid) if e["kind"] in ("joined", "renamed")))
PY
)" "s6" "its joined there carries that alias from the start, no rename after it: the hand-off another tick finished is read at the join"

echo "the override sweep:"
for n in 8 9 10; do
  sid="1a00000$n-0000-4000-8000-00000000000$n"
  [ "$n" = 10 ] && sid=1a000010-0000-4000-8000-000000000010
  mkdir -p "$SMINOS_HOME/sessions"
  printf '{"project":"%s","at":"2026-01-01T00:00:00.000Z"}\n' "$OPID" > "$SMINOS_HOME/sessions/$sid.json"
done
transcript 1a000008-0000-4000-8000-000000000008 "$B6"
python3 -c 'import os, sys, time; t = time.time() - 31 * 86400; os.utime(sys.argv[1], (t, t))' "$TX"
transcript 1a000010-0000-4000-8000-000000000010 "$B6"
python3 -c 'import os, sys, time; t = time.time() - 29 * 86400; os.utime(sys.argv[1], (t, t))' "$TX"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(override_of 1a000008-0000-4000-8000-000000000008)" "none" "an override whose transcript is 31 days quiet is swept"
assert_equals "$(override_of 1a000009-0000-4000-8000-000000000009)" "none" "one whose transcript is gone too"
assert_equals "$(override_of 1a000010-0000-4000-8000-000000000010)" "$OPID" "one 29 days quiet is kept"
assert_equals "$(override_of "$S4")" "$OPID" "and a live one"
assert_contains "$(cat "$SMINOS_HOME/daemon.log")" "1a000008" "each sweep is a daemon.log line naming the session"

echo "the hook's cheap look, on a machine not enrolled:"
as c gamma
FAKE="$T/fakeplugin"
mkdir -p "$FAKE/skills/sminos/scripts" "$T/c/bare" "$T/c/repo/.git"
printf '#!/bin/sh\n: > "%s/python-started"\n' "$T" > "$FAKE/skills/sminos/scripts/sminos"
chmod +x "$FAKE/skills/sminos/scripts/sminos"
hook_payload Stop "$S1" "$T/c/bare" /nowhere | CLAUDE_PLUGIN_ROOT="$FAKE" "$HOOK"
[ ! -e "$T/python-started" ] && pass "where no .smns or .git lies above the payload's cwd, the hook exits before Python" \
  || fail "where no .smns or .git lies above the payload's cwd, the hook exits before Python"
hook_payload Stop "$S1" "$T/c/bare" /nowhere | CLAUDE_PLUGIN_ROOT="$FAKE" CLAUDE_PROJECT_DIR="$T/c/repo" "$HOOK"
[ -e "$T/python-started" ] && pass "unless the session's project directory has one: a cd elsewhere does not lose the export" \
  || fail "unless the session's project directory has one: a cd elsewhere does not lose the export"
rm -f "$T/python-started"
mkdir -p "$SMINOS_HOME/sessions"
printf '{"project":"%s","at":"2026-10-18T00:00:00.000Z"}\n' "$OPID" > "$SMINOS_HOME/sessions/$S1.json"
hook_payload Stop "$S1" "$T/c/bare" /nowhere | CLAUDE_PLUGIN_ROOT="$FAKE" "$HOOK"
[ -e "$T/python-started" ] && pass "or the session holds a join override: one that joined a project from no repository still exports" \
  || fail "or the session holds a join override: one that joined a project from no repository still exports"

# ---- two machines: a move reaches the other; an override whose target retires
echo "two machines:"
as a alpha
"$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & PIDS+=("$!")
as b beta
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" beta "$KEY")" >/dev/null
"$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & PIDS+=("$!")
as a alpha
MR="$T/a/moving"
gitq init -q "$MR"
write_smns "$MR" moving
MPID="$(smns_id "$MR")"
S11=1a000011-0000-4000-8000-000000000011
live_pid
session_record s11 "$S11" "$LIVE_PID" "$MR"
transcript "$S11" "$MR"
run_in "$MR" "$SMINOS" list
beta_has() { grep -qs "$2" "$T/b/s/projects/$MPID/log/alpha.$S11.jsonl"; }
until_true beta_has "$MPID" '"joined"' || true
beta_has "$MPID" '"joined"' && pass "beta reads s11's joined in moving" || fail "beta reads s11's joined in moving"
rm "$MR/.smns"
until_true beta_has "$MPID" '"moved"' || true
beta_has "$MPID" '"moved"' && pass "removing the .smns moves it back, and the old project's moved retirement reaches beta" \
  || fail "removing the .smns moves it back, and the old project's moved retirement reaches beta"
assert_equals "$(events_of "$AMP" "$S11")" "joined - - move $MR" "into the machine project, by move"
alpha_follows() { [ "$(ctl state "d['projects'].get('$MPID', {}).get('follow', {}).get('alpha', 'none')")" = true ]; }
until_true alpha_follows || true
alpha_follows && pass "while alpha keeps following the old project" || fail "while alpha keeps following the old project"

FY=0f0f0f0f-2222-4222-8333-444455556666
ctl register "$FY" followed-y
# A machine project whose machine is not enrolled (a revoked one's): the
# stand-in reactivates a retired machine project while its machine is active.
GHP="$(mp_of ghost)"
ctl register "$GHP" ghost machine
known_here() { [ -s "$SMINOS_HOME/projects/$1/project.json" ]; }
until_true known_here "$FY" || true
until_true known_here "$GHP" || true
S12=1a000012-0000-4000-8000-000000000012
B12="$T/a/bare12"
mkdir -p "$B12"
live_pid
session_record s12 "$S12" "$LIVE_PID" "$B12"
transcript "$S12" "$B12"
run_in "$T/x" in_session "$S12" "$SMINOS" join followed-y
assert_rc 0 "$RC" "join a project alpha only follows"
assert_equals "$(events_of "$FY" "$S12")" "joined - - join $B12" "joined there"
# Both retired at once: each retirement ends alpha's stream and reopens it
# without the project, so one reconnect, not two, stands between them and org.json.
ctl retire "$FY" true
ctl retire "$GHP" true
retired_here() { python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if all(any(p["id"] == i and p.get("retired") for p in d["projects"]) for i in sys.argv[2:]) else 1)' \
  "$SMINOS_HOME/daemon/org.json" "$@" 2>/dev/null; }
until_true retired_here "$FY" "$GHP" || true
retired_here "$FY" "$GHP" && pass "the org frame marking both retired reaches alpha's org.json" \
  || fail "the org frame marking both retired reaches alpha's org.json"
"$SMINOS" daemon tick >/dev/null 2>&1 || true
assert_equals "$(events_of "$FY" "$S12" | tail -1)" "retired moved $AMP - -" \
  "once the org frame retires its target, the next tick moves the session back to its directory's project"
assert_contains "$(events_of "$AMP" "$S12")" "joined - - move $B12" "joined there by move"
assert_equals "$(override_of "$S12")" "none" "and the override is swept"
assert_contains "$(cat "$SMINOS_HOME/daemon.log")" "${S12:0:8}" "with a daemon.log line naming the session"
run_in "$T/x" in_session "$S12" "$SMINOS" join followed-y
assert_rc 1 "$RC" "join of a retired project is refused"
assert_contains "$OUT" "retired" "saying it is retired"
run_in "$T/x" in_session "$S12" "$SMINOS" join ghost
assert_rc 1 "$RC" "join of a retired machine project is refused"
assert_contains "$OUT" "retired" "saying why"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-join: all $PASSES assertions passed"
else
  echo "test-join: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  for f in "$T"/a/s/daemon.log "$T"/b/s/daemon.log "$T"/a/s/run.out "$T"/b/s/run.out; do
    [ -f "$f" ] && { echo "--- $f"; tail -30 "$f"; }
  done
  exit 1
fi
