#!/usr/bin/env bash
#
# The org's directory on the machine side (M3 of the sminos org directory,
# docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md): two
# machines simulated on one Mac — two SMINOS_HOMEs enrolled as alpha and beta
# — and a third home that is not enrolled, against hub_standin.py's `org`
# frame and follow-only hellos. Pins: a session in a directory no .smns claims
# is a member of its machine's project on an enrolled machine, and the record
# hook exports its <message> there (the hook's cheap look admits every
# directory on an enrolled machine, and still exits before Python elsewhere);
# a machine project offers no checkout and refuses @all; a .smns naming only
# its org resolves with the enrollment's URL, a differing `url` is said once
# across verbs, and a machine not enrolled reads it as a local project with a
# hub marker, says so once a day, and runs no git; a linked worktree at a head
# before the .smns resolves to the main checkout's; a name resolves to the hub
# project before a same-named local-* one; each machine follows every project
# of the org's directory (`follow`), holds it again (`follow` false) once a
# local member comes, and a message tagged into a followed project lands in
# its log at the hub; `projects` and `machines` read the directory, and one
# the directory retires is left, then followed again when it is active.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"
HOOK="${SMINOS_HOOK:-$PLUGIN_ROOT/hooks/smns-record.sh}"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smo.XXXXXX)"
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

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST CLAUDE_PLUGIN_ROOT
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin"
# One machine: its HOME, its SMINOS_HOME, its host name; the verbs after it run there.
as() { # a|b|c host
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
esac
case " $* " in
  *" --fork-session "*)
    printf '{"type": "result", "is_error": false, "result": "keeps the bare directory tidy", "session_id": "x"}\n'
    exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
# ssh, as git calls it for a project's remote: a hub project must never reach it.
cat > "$T/bin/fake-ssh" <<SSH
#!/bin/sh
: > "$T/ssh-entered"
exit 1
SSH
chmod +x "$T/bin/fake-ssh"
export PATH="$T/bin:$PATH" GIT_SSH_COMMAND="$T/bin/fake-ssh" GIT_SSH_VARIANT=simple

python3 "$SCRIPT_DIR/hub_standin.py" "$T/hub.port" cid-0 secret-0 1000 & PIDS+=("$!")
until_true test -s "$T/hub.port"
HUB="http://127.0.0.1:$(cat "$T/hub.port")"
KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode())')"
FOLLOWX=0f0f0f0f-1111-4222-8333-444455556666

cat > "$T/ctl.py" <<'PY'
import base64, http.client, json, os, sys, time
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
elif cmd == "gen":
    print(call("GET", "/control/state")[1]["generations"].get(args[0], 0))
elif cmd == "register":  # project name
    call("POST", "/control/register", {"project": args[0], "name": args[1]})
elif cmd == "retire":  # project true|false
    call("POST", "/control/retire", {"project": args[0], "retired": args[1] == "true"})
elif cmd == "inject":  # project events-json
    call("POST", "/control/inject", {"project": args[0], "events": json.loads(args[1])})
PY
ctl() { python3 "$T/ctl.py" "$T/hub.port" "$@"; }
# A session's `joined` as another machine (gamma) would have uploaded it, sealed with the org key.
joined_of() { # project writer-session alias
  python3 - "$@" <<'PY'
import json, os, sys, time
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos_codes as codes
project, session, alias = sys.argv[1:4]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
draft = {"ts": ts, "writer": "gamma/" + session, "seq": 1, "kind": "joined", "session": session, "alias": alias,
         "name_source": "user", "machine": "gamma", "cwd": "/home/g/x", "worktree": "", "role": "", "seat": "",
         "by": "", "session_kind": "interactive", "repo": "x", "branch": "main"}
print(json.dumps([codes.seal(bytes(range(32)), "log", project, draft, codes.b64url(os.urandom(16)))]))
PY
}
mp_of() { python3 -c 'import sys, uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:org-1:" + sys.argv[1].lower()))' "$1"; }
smns_id() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$1/.smns"; }
write_smns() { # dir name hub-json [remote]
  python3 -c 'import json, sys, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": sys.argv[1], "remote": sys.argv[3], "hub": json.loads(sys.argv[2])}, indent=2))' \
    "$2" "$3" "${4:-}" > "$1/.smns"
}
session_record() { # name session pid cwd status — an engine record for a running session
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"%s","cwd":"%s"}\n' \
    "$3" "$2" "$1" "$5" "$4" > "$HOME/.claude/sessions/$1.json"
}
live_pid() { sleep 600 & LIVE_PID=$!; PIDS+=("$LIVE_PID"); }
start_daemon() { # → DAEMON_PID (of the machine `as` named last)
  "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & DAEMON_PID=$!
  PIDS+=("$DAEMON_PID")
}
hub_follow() { # project machine → true | false | none: the follow of the machine's last hello of it
  ctl state "d['projects'].get('$1', {}).get('follow', {}).get('$2', 'none')"
}
follows() { [ "$(hub_follow "$1" "$2")" = "$3" ]; }
hub_says() { # project text — whether the hub holds an event of the project carrying the text
  ctl state "any('$2' in json.dumps(e) for evs in d['projects'].get('$1', {}).get('writers', {}).values() for e in evs)" \
    2>/dev/null | grep -q true
}

# ---- before alpha enrolls: a local project named after its repository
echo "alpha, not enrolled yet:"
as a alpha
RO="$T/a/orgproj"
gitq init -q "$RO"
run_in "$RO" "$SMINOS" say "local words"
assert_rc 0 "$RC" "a repository without .smns is the local project local-orgproj"

# ---- alpha enrolled: the machine project
echo "alpha, enrolled:"
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" alpha "$KEY")" >/dev/null
AMP="$(mp_of alpha)"
BARE="$T/a/bare"
mkdir -p "$BARE"
STRAY=5a000001-0000-4000-8000-0000000000a1
live_pid
STRAY_PID=$LIVE_PID
session_record stray "$STRAY" "$STRAY_PID" "$BARE" idle
run_in "$BARE" "$SMINOS" project show
assert_contains "$OUT" "id       $AMP" "a directory no .smns claims is in the machine's own project, its id the hub's"
assert_contains "$OUT" "kind     machine" "of kind machine"
assert_contains "$OUT" "project  alpha" "named after the machine"
run_in "$BARE" "$SMINOS" list --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print([(r["alias"], r["project"], r["project_kind"]) for r in json.load(sys.stdin)])')" \
  "[('stray', 'alpha', 'machine')]" "a session there is a member of the machine project"
run_in "$BARE" "$SMINOS" say "@all anyone"
assert_rc 2 "$RC" "@all is refused in a machine project"
assert_contains "$OUT" "a machine project is not a team: tag who you mean" "saying why"
assert_equals "$(python3 -c 'import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_policy as policy
print(policy.known_checkouts(sminos.own_machine_project()))')" "[]" \
  "the machine project offers no checkout, though a session joined it from a directory here"

# ---- a .smns naming only its org
echo "a .smns naming its org:"
write_smns "$RO" orgproj '{"org": "org-1"}'
gitq -C "$RO" add .smns
gitq -C "$RO" commit -q -m "smns"
OPID="$(smns_id "$RO")"
run_in "$RO" "$SMINOS" project show
assert_contains "$OUT" "hub      $HUB (org org-1)" "a .smns with hub {org} resolves with the enrollment's URL"
assert_contains "$OUT" "kind     hub" "a hub project"
run_in "$RO" "$SMINOS" say "hub words"
run_in "$BARE" "$SMINOS" chat orgproj -n 5
assert_contains "$OUT" "hub words" "chat <name> reads the hub project, though local-orgproj has the same name"
assert_not_contains "$OUT" "local words" "and not the local one"
run_in "$BARE" "$SMINOS" chat local-orgproj -n 5
assert_contains "$OUT" "local words" "chat local-<name> reads the local one, by its id"

RU="$T/a/urlproj"
gitq init -q "$RU"
write_smns "$RU" urlproj '{"url": "https://elsewhere.example", "org": "org-1"}'
SAID=""
for verb in "list" "project show" "chat"; do
  # shellcheck disable=SC2086
  run_in "$RU" "$SMINOS" $verb
  SAID+="$OUT"$'\n'
done
assert_equals "$(grep -c 'drop `url` from .smns' <<<"$SAID")" 1 "a .smns url that differs from the enrollment's is said exactly once across three verbs"
assert_equals "$(grep -c 'drop `url` from .smns' "$SMINOS_HOME/daemon.log")" 1 "and in daemon.log once"
run_in "$RU" "$SMINOS" project show
assert_contains "$OUT" "hub      $HUB (org org-1)" "the enrollment's URL is the one used"

# A linked worktree at a head from before the .smns.
RW="$T/a/wtrepo"
gitq init -q "$RW"
gitq -C "$RW" commit -q --allow-empty -m base
BASE="$(git -C "$RW" rev-parse HEAD)"
write_smns "$RW" wtrepo '{"org": "org-1"}'
gitq -C "$RW" add .smns
gitq -C "$RW" commit -q -m smns
gitq -C "$RW" worktree add -q --detach "$T/a/wt-old" "$BASE"
[ ! -e "$T/a/wt-old/.smns" ] && pass "the worktree's head has no .smns" || fail "the worktree's head has no .smns"
run_in "$T/a/wt-old" "$SMINOS" project show
assert_contains "$OUT" "id       $(smns_id "$RW")" "a linked worktree without the file resolves to its main checkout's project"

# ---- the record hook's cheap look
echo "the record hook:"
FAKE="$T/fakeplugin"
mkdir -p "$FAKE/skills/sminos/scripts"
printf '#!/bin/sh\n: > "%s/python-started"\n' "$T" > "$FAKE/skills/sminos/scripts/sminos"
chmod +x "$FAKE/skills/sminos/scripts/sminos"
hook_payload() { # event session cwd transcript
  printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","hook_event_name":"%s","source":"startup"}' "$2" "$4" "$3" "$1"
}
as c gamma
mkdir -p "$T/c/bare"
hook_payload SessionStart "$STRAY" "$T/c/bare" /nowhere | CLAUDE_PLUGIN_ROOT="$FAKE" "$HOOK"
[ ! -e "$T/python-started" ] && pass "on a machine not enrolled, the hook exits before Python where no .smns or .git lies above" \
  || fail "on a machine not enrolled, the hook exits before Python where no .smns or .git lies above"
as a alpha
hook_payload SessionStart "$STRAY" "$BARE" /nowhere | CLAUDE_PLUGIN_ROOT="$FAKE" "$HOOK"
[ -e "$T/python-started" ] && pass "on an enrolled machine, it admits every directory" \
  || fail "on an enrolled machine, it admits every directory"
TX="$HOME/.claude/projects/bare/$STRAY.jsonl"
mkdir -p "$(dirname "$TX")"
printf '%s\n' '{"type":"user","uuid":"st000001","isSidechain":false,"origin":{"kind":"human"},"message":{"role":"user","content":"go"}}' > "$TX"
hook_payload SessionStart "$STRAY" "$BARE" "$TX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
printf '%s\n' '{"type":"assistant","uuid":"st000002","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"<message>done in the bare directory</message>"}]}}' >> "$TX"
hook_payload Stop "$STRAY" "$BARE" "$TX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
assert_contains "$(cat "$SMINOS_HOME/projects/$AMP/log/"*.jsonl 2>/dev/null)" "done in the bare directory" \
  "a stray's <message> is exported to its machine project's log"
# derive --all covers the machine project's strays: one whose model made no
# tool call yet is asked nothing (§5 of the log design), one that made ten is
# derived.
DRIFT=5a000005-0000-4000-8000-0000000000a5
live_pid
printf '{"pid":%s,"sessionId":"%s","name":"drift","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$LIVE_PID" "$DRIFT" "$BARE" > "$HOME/.claude/sessions/drift.json"
for i in 1 2 3 4 5 6 7 8 9 10; do
  printf '{"type":"assistant","uuid":"dr%06d","isSidechain":false,"message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_dr%06d","name":"Bash","input":{}}]}}\n' "$i" "$i"
done > "$(dirname "$TX")/$DRIFT.jsonl"
run_in "$BARE" "$SMINOS" derive --all
assert_contains "$OUT" "stray: not derived — 0 tool calls, needs 10" "derive --all covers the stray in its machine project"
assert_contains "$OUT" "drift: keeps the bare directory tidy" "and derives one whose model made ten tool calls"
assert_contains "$(cat "$SMINOS_HOME/projects/$AMP/log/alpha.$DRIFT.jsonl")" '"source": "derived"' \
  "recording its derived line in the machine project's log"
rm -f "$HOME/.claude/sessions/drift.json"

# The org directory's registration of a project it does not know keeps a
# registration that lands meanwhile: a CLI or hook registering the project
# with its real root between the uplink's lookup and its write (the lock both
# take held here, the rooted registration written while the uplink waits).
RACE=0e0e0e0e-1111-4222-8333-444455556666
mkdir -p "$T/race/root"
assert_equals "$(SMINOS_HOME="$T/race/s" python3 - "$RACE" "$T/race/root" <<'PY'
import contextlib, fcntl, json, os, sys, threading
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_uplink as uplink
pid, root = sys.argv[1], sys.argv[2]
home = os.path.join(sminos.projects_root(), pid)
os.makedirs(home, exist_ok=True)
lock = os.path.join(home, "project.json.lock")
waiting = threading.Event()
real = sminos.flocked

@contextlib.contextmanager
def flocked(path, *args, **kw):
    if path == lock:
        waiting.set()
    with real(path, *args, **kw):
        yield

sminos.flocked = flocked
fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
cred = {"hub": "http://127.0.0.1:9", "org": "org-1", "machine": "alpha"}
frame = {"t": "org", "projects": [{"id": pid, "name": "raced", "kind": "hub", "retired": False}], "machines": []}
t = threading.Thread(target=uplink.keep_org, args=(frame, cred))
t.start()
if not waiting.wait(10):
    sys.exit("keep_org never asked for the registration lock")
rooted = {"project": pid, "name": "raced", "remote": "", "root": root, "hub": {"url": "http://127.0.0.1:9", "org": "org-1"}}
sminos.write_json(os.path.join(home, "project.json"), rooted)
fcntl.flock(fd, fcntl.LOCK_UN)
t.join(10)
print(json.load(open(os.path.join(home, "project.json")))["root"] == root)
PY
)" True "a rooted registration landing while the org's directory registers the project is kept"

# ---- a machine not enrolled
echo "a machine not enrolled:"
as c gamma
RC_="$T/c/orgproj"
cp -R "$RO" "$RC_"
python3 -c 'import json, sys
d = json.load(open(sys.argv[1])); d["remote"] = sys.argv[2]; json.dump(d, open(sys.argv[1], "w"))' "$RC_/.smns" "ssh://archive$T/archive.git"
run_in "$RC_" "$SMINOS" list
assert_contains "$OUT" "project orgproj syncs through the desk hub of org org-1; this machine is not enrolled (sminos hub enroll)" \
  "a reading verb on a machine not enrolled says how the project syncs"
run_in "$RC_" "$SMINOS" list
assert_not_contains "$OUT" "this machine is not enrolled" "once a day"
run_in "$RC_" "$SMINOS" project show
assert_contains "$OUT" "kind     hub (not enrolled)" "project show says hub (not enrolled)"
touch -t 202001010000 "$SMINOS_HOME/projects/$OPID/hinted" 2>/dev/null || true
run_in "$RC_" "$SMINOS" list
assert_contains "$OUT" "this machine is not enrolled" "and again a day later"
run_in "$RC_" "$SMINOS" daemon tick
[ ! -e "$T/ssh-entered" ] && pass "a hub project here runs no git, though its .smns names a remote" \
  || fail "a hub project here runs no git, though its .smns names a remote"
[ ! -e "$SMINOS_HOME/projects/$OPID/log/.git" ] && pass "and has no mirror" || fail "and has no mirror"
run_in "$T/c/bare" "$SMINOS" list --here --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys; print(len(json.load(sys.stdin)))')" 0 \
  "a directory in no repository is still no project on a machine not enrolled"

# ---- the uplink: every project of the org followed or held
echo "alpha's uplink:"
as a alpha
MA=5a000002-0000-4000-8000-0000000000a2
live_pid
session_record ma "$MA" "$LIVE_PID" "$RO" idle
run_in "$RO" "$SMINOS" list
start_daemon
until_true follows "$OPID" alpha false || true
assert_equals "$(hub_follow "$OPID" alpha)" false "alpha holds orgproj, its checkout here: hello without follow"
until_true follows "$AMP" alpha false || true
assert_equals "$(hub_follow "$AMP" alpha)" false "and its own machine project"
assert_equals "$(ctl state "d['registry'].get('$AMP')")" '{"name": "alpha", "kind": "machine", "machine": "alpha", "retired": false}' \
  "which the hub lists as alpha's machine project"
until_true hub_says "$AMP" "done in the bare directory" || true
hub_says "$AMP" "done in the bare directory" && pass "the stray's <message> reaches the hub" || fail "the stray's <message> reaches the hub"
RK="$T/a/chkproj"
gitq init -q "$RK"
write_smns "$RK" chkproj '{"org": "org-1"}'
KPID="$(smns_id "$RK")"
run_in "$RK" "$SMINOS" say "chkproj exists"
until_true follows "$KPID" alpha false || true
assert_equals "$(hub_follow "$KPID" alpha)" false "a project registered here by its checkout alone is held"
ctl register "$FOLLOWX" followed-x
until_true follows "$FOLLOWX" alpha true || true
assert_equals "$(hub_follow "$FOLLOWX" alpha)" true "a project of the org's directory alpha does not hold is opened follow: true"
assert_equals "$(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d["root"], d["name"], d["hub"]["org"])' \
  "$SMINOS_HOME/projects/$FOLLOWX/project.json")" " followed-x org-1" "registered here with no root"
assert_contains "$(cat "$SMINOS_HOME/daemon/org.json")" "\"id\": \"$FOLLOWX\"" "the org's directory is kept at daemon/org.json"
GM=5c000003-0000-4000-8000-0000000000c3
ctl inject "$FOLLOWX" "$(joined_of "$FOLLOWX" "$GM" gm)"
gm_here() { [ -s "$SMINOS_HOME/projects/$FOLLOWX/log/gamma.$GM.jsonl" ]; }
until_true gm_here || true
gm_here && pass "what the hub holds of a followed project reaches alpha" || fail "what the hub holds of a followed project reaches alpha"
run_in "$BARE" "$SMINOS" say "@followed-x/gm hello from alpha"
assert_rc 0 "$RC" "a message tagged into the followed project is accepted"
until_true hub_says "$FOLLOWX" "hello from alpha" || true
hub_says "$FOLLOWX" "hello from alpha" && pass "and lands in its log at the hub" || fail "and lands in its log at the hub"
assert_equals "$(hub_follow "$FOLLOWX" alpha)" true "alpha still follows it: writing a message holds nothing"

# ---- beta
echo "beta:"
as b beta
"$SMINOS" hub enroll <<<"$(ctl code "$HUB" "$(ctl token)" beta "$KEY")" >/dev/null
start_daemon
B_DAEMON=$DAEMON_PID
until_true follows "$OPID" beta true || true
assert_equals "$(hub_follow "$OPID" beta)" true "beta follows orgproj, a project it has no checkout of"
until_true follows "$AMP" beta true || true
assert_equals "$(hub_follow "$AMP" beta)" true "and alpha's machine project"
mkdir -p "$T/b/bare"
stray_read() { (cd "$T/b/bare" && "$SMINOS" chat alpha --host -n 5) | grep -q "done in the bare directory"; }
until_true stray_read || true
stray_read && pass "beta reads alpha's stray's <message> in alpha's machine project (chat alpha --host)" \
  || fail "beta reads alpha's stray's <message> in alpha's machine project (chat alpha --host)"
RB="$T/b/orgproj"
cp -R "$RO" "$RB"
WB=5b000004-0000-4000-8000-0000000000b4
live_pid
session_record wb "$WB" "$LIVE_PID" "$RB" waiting
run_in "$RB" "$SMINOS" list
until_true follows "$OPID" beta false || true
assert_equals "$(hub_follow "$OPID" beta)" false "once a session joins it there, beta holds orgproj: hello again with follow false"
# A checkout alone makes a project held: beta, following chkproj with no
# checkout, clones it and registers the clone (a verb in it), no session there.
until_true follows "$KPID" beta true || true
assert_equals "$(hub_follow "$KPID" beta)" true "beta follows chkproj, of which it has no checkout"
RKB="$T/b/chkproj"
cp -R "$RK" "$RKB"
run_in "$RKB" "$SMINOS" chat
until_true follows "$KPID" beta false || true
assert_equals "$(hub_follow "$KPID" beta)" false "a registered checkout, no session, makes beta hold it: hello again without follow"
offered() {
  ctl state "any(x['machine'] == 'beta' and x['message'].get('kind') == 'machine' and x['message'].get('project') == '$KPID'
              and any(c['path'].endswith('/b/chkproj') for c in x['message']['body'].get('checkouts', [])) for x in d['sessions'])" \
    | grep -q true
}
until_true offered || true
offered && pass "with the checkout in its machine presence" || fail "with the checkout in its machine presence"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["root"].endswith("/b/chkproj"))' \
  "$SMINOS_HOME/projects/$KPID/project.json")" True "and the rooted registration kept"

echo "alpha reads both:"
as a alpha
wb_here() { (cd "$RO" && "$SMINOS" list --json) | grep -q '"state": "waiting"'; }
until_true wb_here || true
run_in "$RO" "$SMINOS" list
assert_equals "$(printf '%s\n' "$OUT" | head -1)" "orgproj" "list in orgproj prints one heading"
assert_contains "$OUT" "ma [${MA:0:8}]" "with alpha's member"
assert_contains "$OUT" "wb [${WB:0:8}]" "and beta's"
run_in "$BARE" "$SMINOS" list --machine beta --state waiting
assert_contains "$OUT" "wb [${WB:0:8}]" "--machine beta --state waiting from alpha prints beta's waiting session"
assert_not_contains "$OUT" "ma [" "and nothing else"
assert_not_contains "$OUT" "stray [" "nothing else at all"
run_in "$BARE" "$SMINOS" projects
assert_contains "$OUT" "PROJECT" "projects prints its table"
proj_row() { printf '%s\n' "$OUT" | awk -v n="$1" '$1 == n { $1 = $1; print }'; }
assert_equals "$(proj_row orgproj)" "orgproj hub 2 1 alpha, beta" "orgproj: a hub project, two live, one waiting, on alpha and beta"
assert_equals "$(proj_row local-orgproj)" "local-orgproj local 0 0 -" \
  "the local project whose name the hub project answers to is listed by its id, the name it answers to"
assert_equals "$(proj_row alpha)" "alpha machine 1 0 alpha" "alpha's machine project"
assert_equals "$(proj_row beta)" "beta machine 0 0 -" "beta's"
assert_equals "$(proj_row followed-x)" "followed-x hub 0 0 -" "and the project alpha only follows"
run_in "$BARE" "$SMINOS" machines
mach_row() { printf '%s\n' "$OUT" | awk -v n="$1" '$1 == n { $1 = $1; print }'; }
assert_equals "$(mach_row alpha)" "alpha online 2 alpha, orgproj" "machines: alpha online, with its sessions and their projects"
assert_equals "$(mach_row beta)" "beta online 1 orgproj" "beta online"
assert_equals "$(mach_row testhost)" "testhost never seen 0 -" "a machine that never connected"
kill "$B_DAEMON"
beta_seen() { (cd "$BARE" && "$SMINOS" machines) | grep -Eq '^beta +last seen'; }
until_true beta_seen || true
beta_seen && pass "a machine whose daemon stopped is last seen" || fail "a machine whose daemon stopped is last seen"

echo "a project retired, then active again:"
GEN="$(ctl gen alpha)"
ctl retire "$FOLLOWX" true
reopened_without() { [ "$(ctl gen alpha)" -gt "$GEN" ] && [ "$(ctl state "d['projects']['$FOLLOWX']['open'].get('alpha') == d['generations']['alpha']")" = false ] \
  && [ "$(ctl state "d['projects']['$AMP']['open'].get('alpha') == d['generations']['alpha']")" = true ]; }
until_true reopened_without || true
reopened_without && pass "a project the directory retires leaves the stream: alpha reconnects without it" \
  || fail "a project the directory retires leaves the stream: alpha reconnects without it"
run_in "$BARE" "$SMINOS" projects
assert_not_contains "$OUT" "followed-x" "projects hides it"
run_in "$BARE" "$SMINOS" projects --all
assert_contains "$OUT" "followed-x" "projects --all shows it"
assert_equals "$(proj_row followed-x)" "followed-x hub (retired) 0 0 -" "marked retired"
GEN="$(ctl gen alpha)"
ctl retire "$FOLLOWX" false
refollowed() { [ "$(ctl state "d['projects']['$FOLLOWX']['open'].get('alpha') == d['generations']['alpha']")" = true ] && follows "$FOLLOWX" alpha true; }
until_true refollowed || true
refollowed && pass "active again, alpha follows it again" || fail "active again, alpha follows it again"
run_in "$BARE" "$SMINOS" projects
assert_equals "$(proj_row followed-x)" "followed-x hub 0 0 -" "and projects lists it"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-org: all $PASSES assertions passed"
else
  echo "test-org: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  for f in "$T"/a/s/daemon.log "$T"/b/s/daemon.log "$T"/a/s/run.out "$T"/b/s/run.out; do
    [ -f "$f" ] && { echo "--- $f"; tail -30 "$f"; }
  done
  exit 1
fi
