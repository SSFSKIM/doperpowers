#!/usr/bin/env bash
#
# The org's directory on the machine side (M3 of the sminos org directory,
# docs/doperpowers/specs/2026-10-18-smns-org-directory-design.md), on
# machines cut over to their endpoints (daemon/identity.json, which is what
# enrolls a machine) and on a home that is not enrolled. Pins: a session in a
# directory no .smns claims is a member of its machine's project on an
# enrolled machine, and the record hook exports its <message> there (the
# hook's cheap look admits every directory on an enrolled machine, and still
# exits before Python elsewhere); a machine project offers no checkout and
# refuses @all; a .smns naming only its org resolves with the enrollment's
# URL, a differing `url` is said once across verbs, and a machine not
# enrolled reads it as a local project with a hub marker, says so once a day,
# and runs no git; a linked worktree at a head before the .smns resolves to
# the main checkout's; a name resolves to the hub project before a same-named
# local-* one. Then the uplink's side, one machine and two: epsilon, cut over
# to its endpoint_standin.py, follows every project of the org's directory
# (`follow`), holds one it has a local member or checkout of, lands a message
# tagged into a followed project in an events frame, and leaves a project the
# directory retires, following it again when it is active; alpha and beta,
# each cut over to its own stand-in, what one endpoint took reaching the other
# as arrivals (rl10-machines.sh's hand-off), and `projects` and `machines`
# read across them.
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

# shellcheck source=rl10-machines.sh
. "$SCRIPT_DIR/rl10-machines.sh"
HUB="http://127.0.0.1:9"   # the hub URL of the identity rl10_cut_over writes
FOLLOWX=0f0f0f0f-1111-4222-8333-444455556666

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
proj_row() { printf '%s\n' "$OUT" | awk -v n="$1" '$1 == n { $1 = $1; print }'; }
mach_row() { printf '%s\n' "$OUT" | awk -v n="$1" '$1 == n { $1 = $1; print }'; }

# ---- before alpha enrolls: a local project named after its repository
echo "alpha, not enrolled yet:"
as a alpha
RO="$T/a/orgproj"
gitq init -q "$RO"
run_in "$RO" "$SMINOS" say "local words"
assert_rc 0 "$RC" "a repository without .smns is the local project local-orgproj"

# ---- alpha enrolled: the machine project. Cut over (identity.json, which is
# what enrolls a machine), a new enrolment as its endpoint's welcome marks one
# (#147): no endpoint runs here until the uplink's cases below.
echo "alpha, enrolled:"
rl10_cut_over
python3 -c 'import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos
sminos.mark_enrolled(sys.argv[1], sys.argv[2])' "$DAEMON_HOST" "$RL10_ENROLLED"
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
# A machine just enrolled: the operator's words wait for the hub's head of its
# writer (#147), here released as the uplink's handshake releases them.
assert_contains "$OUT" "it waits in orgproj for the upstream's head" "on a new enrolment the operator's say waits for the hub's head"
OPID="$OPID" python3 -c 'import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_hublog as hublog
hublog.HubLog(sminos.find_project(os.environ["OPID"]), {"key": None, "machine": sminos.host_name()}).on_have({"have": {}})'
run_in "$BARE" "$SMINOS" chat orgproj -n 5
assert_contains "$OUT" "hub words" "chat <name> reads the hub project, though local-orgproj has the same name"
assert_not_contains "$OUT" "local words" "and not the local one"
run_in "$BARE" "$SMINOS" chat local-orgproj -n 5
assert_contains "$OUT" "local words" "chat local-<name> reads the local one, by its id"
run_in "$BARE" "$SMINOS" projects
assert_equals "$(proj_row local-orgproj)" "local-orgproj local 0 0 -" \
  "the local project whose name the hub project answers to is listed by its id, the name it answers to"

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
# identity.json admits (a machine cut over to its endpoint); without it, not,
# a stray hub.json alone included: it enrolls nothing.
for f in identity.json hub.json none; do
  as d delta
  rm -rf "$SMINOS_HOME" "$T/python-started"
  mkdir -p "$SMINOS_HOME/daemon" "$T/d/bare"
  [ "$f" = none ] || printf '{}' > "$SMINOS_HOME/daemon/$f"
  hook_payload SessionStart "$STRAY" "$T/d/bare" /nowhere | CLAUDE_PLUGIN_ROOT="$FAKE" "$HOOK"
  case "$f" in
    identity.json)
      [ -e "$T/python-started" ] && pass "with identity.json alone, the hook admits a directory outside any project" \
        || fail "with identity.json alone, the hook admits a directory outside any project" ;;
    hub.json)
      [ ! -e "$T/python-started" ] && pass "with a stray hub.json alone, the hook exits before Python outside a project" \
        || fail "with a stray hub.json alone, the hook exits before Python outside a project" ;;
    none)
      [ ! -e "$T/python-started" ] && pass "without identity.json, the hook exits before Python outside a project" \
        || fail "without identity.json, the hook exits before Python outside a project" ;;
  esac
done
as a alpha
TX="$HOME/.claude/projects/bare/$STRAY.jsonl"
mkdir -p "$(dirname "$TX")"
printf '%s\n' '{"type":"user","uuid":"st000001","isSidechain":false,"origin":{"kind":"human"},"message":{"role":"user","content":"go"}}' > "$TX"
hook_payload SessionStart "$STRAY" "$BARE" "$TX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
printf '%s\n' '{"type":"assistant","uuid":"st000002","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"<message>done in the bare directory</message>"}]}}' >> "$TX"
hook_payload Stop "$STRAY" "$BARE" "$TX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
assert_contains "$(cat "$SMINOS_HOME/projects/$AMP/host/"*.jsonl 2>/dev/null)" "done in the bare directory" \
  "a stray's <message> is exported to its machine project's host store (the machine is cut over)"
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
assert_contains "$OUT" "project orgproj syncs through the desk hub of org org-1; this machine is not enrolled (mawsd endpoint enroll)" \
  "a reading verb on a machine not enrolled says how the project syncs, and where the enrollment is made"
run_in "$RC_" "$SMINOS" machines
assert_contains "$OUT" "this machine is not enrolled at a desk hub (mawsd endpoint enroll): it knows only itself" \
  "machines on a machine not enrolled: where the enrollment is made"
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

# ---- RL10: the org's directory on the uplink side, one machine
# epsilon is cut over to its endpoint stand-in by its identity.json alone;
# the directory is the stand-in's `org`, sent after each welcome, or an `org`
# frame sent down the live connection; what the endpoint brings of a followed
# project is an RL10 arrival; what epsilon says and uploads is read from the
# frames the stand-in received. The cases that need a second machine (beta,
# the tables built from two) are the next block's.
echo "RL10, epsilon's uplink:"
as e epsilon
export MAWS_USER_DATA="$T/e/maws"
EPE="$MAWS_USER_DATA/mawsd/endpoint"
EID='{"org": "org-1", "hub": "http://127.0.0.1:9", "name": "epsilon", "former": [], "ref": "ref-epsilon", "enrolled": "2026-11-05T00:00:00.000Z"}'
# Cut over as a welcome leaves a machine: daemon/identity.json, the stand-in's
# identity (the same enrolment, so nothing waits for a head, #147).
mkdir -p "$SMINOS_HOME/daemon"
chmod 700 "$SMINOS_HOME" "$SMINOS_HOME/daemon"
python3 - "$SMINOS_HOME/daemon/identity.json" "$EID" <<'PY'
import json, os, sys
with open(sys.argv[1], "w") as f:
    json.dump({**json.loads(sys.argv[2]), "former": {}, "cutover": "2026-11-05T00:00:01.000Z", "build": "b"}, f)
os.chmod(sys.argv[1], 0o600)
PY
EMP="$(mp_of epsilon)"
EBARE="$T/e/bare"
mkdir -p "$EBARE"
# orgproj-e, held by a session there; chkproj-e, by its checkout alone.
REO="$T/e/orgproj"
gitq init -q "$REO"
write_smns "$REO" orgproj-e '{"org": "org-1"}'
EOPID="$(smns_id "$REO")"
EMA=5e000002-0000-4000-8000-0000000000e2
live_pid
session_record ma "$EMA" "$LIVE_PID" "$REO" idle
run_in "$REO" "$SMINOS" list
REK="$T/e/chkproj"
gitq init -q "$REK"
write_smns "$REK" chkproj-e '{"org": "org-1"}'
EKPID="$(smns_id "$REK")"
run_in "$REK" "$SMINOS" say "chkproj-e exists"
# A stray in the bare directory, its <message> exported to the machine project.
ESTRAY=5e000001-0000-4000-8000-0000000000e1
live_pid
session_record stray "$ESTRAY" "$LIVE_PID" "$EBARE" idle
ETX="$HOME/.claude/projects/bare/$ESTRAY.jsonl"
mkdir -p "$(dirname "$ETX")"
printf '%s\n' '{"type":"user","uuid":"se000001","isSidechain":false,"origin":{"kind":"human"},"message":{"role":"user","content":"go"}}' > "$ETX"
hook_payload SessionStart "$ESTRAY" "$EBARE" "$ETX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
printf '%s\n' '{"type":"assistant","uuid":"se000002","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"<message>done in the bare directory of epsilon</message>"}]}}' >> "$ETX"
hook_payload Stop "$ESTRAY" "$EBARE" "$ETX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
# The org's directory as the endpoint sends it: followed-x retired or not.
org_dir() { # retired(true|false) → an `org` frame's body
  python3 - "$1" "$EOPID" "$EKPID" "$EMP" "$FOLLOWX" <<'PY'
import json, sys
retired, held, chk, own, followx = sys.argv[1] == "true", *sys.argv[2:]
print(json.dumps({"projects": [{"id": held, "name": "orgproj-e", "kind": "hub", "retired": False},
                               {"id": chk, "name": "chkproj-e", "kind": "hub", "retired": False},
                               {"id": own, "name": "epsilon", "kind": "machine", "retired": False},
                               {"id": followx, "name": "followed-x", "kind": "hub", "retired": retired}],
                  "machines": [{"name": "epsilon", "online": True}]}))
PY
}
org_sent() { # retired(true|false) → `ctl send`'s argument: the directory as an `org` frame down the live connection
  python3 -c 'import json, sys; print(json.dumps({"frames": [{"t": "org", **json.loads(sys.argv[1])}]}))' "$(org_dir "$1")"
}
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPE" "{\"identity\": $EID, \"org\": $(org_dir false), \"ask_legacy\": false}" &
PIDS+=("$!")
until_true test -S "$EPE/ctl.sock"
ep_e() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPE" "$@" >/dev/null; }
epq_e() { python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$EPE" state \
  | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps(eval(sys.argv[1], {"d": d})))' "$1"; }
# The follow of epsilon's last hello of a project on the live connection:
# true | false | none (not opened on it).
ep_follow() {
  epq_e "next((str(f['frame'].get('follow') is True).lower() for f in reversed(d['received']) if f['conn'] == d['current']
               and f['frame'].get('t') == 'hello' and f['frame'].get('project') == '$1'), 'none')" | tr -d '"'
}
ep_follows() { [ "$(ep_follow "$1")" = "$2" ]; }
ep_says() { # project text — whether an `events` frame epsilon sent up for the project carries the text
  [ "$(epq_e "any('$2' in repr(f['frame']['events']) for f in d['received'] if f['frame'].get('t') == 'events'
                  and f['frame'].get('project') == '$1')" 2>/dev/null)" = true ]
}
start_daemon
E_DAEMON=$DAEMON_PID
until_true ep_follows "$EOPID" false || true
assert_equals "$(ep_follow "$EOPID")" false "epsilon holds orgproj-e, its checkout here: hello without follow"
until_true ep_follows "$EMP" false || true
assert_equals "$(ep_follow "$EMP")" false "and its own machine project"
# On RL10 a session's <message> is kept in its project's host store, not
# its log, and goes up the session lane as a sub-less `host` message.
ep_host_says() { # project text — whether a `host` session message epsilon sent for the project carries the text
  [ "$(epq_e "any('$2' in repr(f['frame']['message'].get('body')) for f in d['received'] if f['frame'].get('t') == 'session'
                  and f['frame']['message'].get('kind') == 'host' and f['frame']['message'].get('project') == '$1')" 2>/dev/null)" = true ]
}
until_true ep_host_says "$EMP" "done in the bare directory of epsilon" || true
ep_host_says "$EMP" "done in the bare directory of epsilon" \
  && pass "the stray's <message> reaches the endpoint, a host message of epsilon's machine project" \
  || fail "the stray's <message> reaches the endpoint, a host message of epsilon's machine project"
until_true ep_follows "$EKPID" false || true
assert_equals "$(ep_follow "$EKPID")" false "a project registered here by its checkout alone is held"
until_true ep_follows "$FOLLOWX" true || true
assert_equals "$(ep_follow "$FOLLOWX")" true "a project of the org's directory epsilon does not hold is opened follow: true"
assert_equals "$(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d["root"], d["name"], d["hub"]["org"])' \
  "$SMINOS_HOME/projects/$FOLLOWX/project.json" 2>&1)" " followed-x org-1" "registered here with no root"
assert_contains "$(cat "$SMINOS_HOME/daemon/org.json")" "\"id\": \"$FOLLOWX\"" "the org's directory is kept at daemon/org.json"
EGM=5c000013-0000-4000-8000-0000000000c3
ep_e send "$(python3 - "$FOLLOWX" "$EGM" <<'PY'
import json, sys, time
project, session = sys.argv[1:3]
ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
joined = {"ts": ts, "writer": "gamma/" + session, "seq": 1, "kind": "joined", "session": session, "alias": "gm",
          "name_source": "user", "machine": "gamma", "cwd": "/home/g/x", "worktree": "", "role": "", "seat": "",
          "by": "", "session_kind": "interactive", "repo": "x", "branch": "main"}
signer = {"kind": "machine", "ref": "ref-gamma", "name": "gamma", "keyId": "k-gamma"}
print(json.dumps({"frames": [{"t": "events", "project": project, "events": [{"event": joined, "signer": signer}]}]}))
PY
)"
egm_here() { [ -s "$SMINOS_HOME/projects/$FOLLOWX/log/gamma.$EGM.jsonl" ]; }
until_true egm_here || true
egm_here && pass "what the endpoint brings of a followed project reaches epsilon" \
  || fail "what the endpoint brings of a followed project reaches epsilon"
run_in "$EBARE" "$SMINOS" say "@followed-x/gm hello from epsilon"
assert_rc 0 "$RC" "a message tagged into the followed project is accepted"
until_true ep_says "$FOLLOWX" "hello from epsilon" || true
ep_says "$FOLLOWX" "hello from epsilon" && pass "and goes up in an events frame of that project" \
  || fail "and goes up in an events frame of that project"
assert_equals "$(epq_e "sorted({str(f['frame'].get('follow') is True) for f in d['received'] if f['frame'].get('t') == 'hello'
                                and f['frame'].get('project') == '$FOLLOWX'})")" '["True"]' \
  "epsilon still follows it: writing a message holds nothing"

echo "RL10, a project retired, then active again:"
CONNS_E="$(epq_e 'd["conns"]')"
# Retired in the stand-in's directory too, so the reconnect's welcome carries it.
ep_e set "{\"org\": $(org_dir true)}"
ep_e send "$(org_sent true)"
e_reopened_without() { [ "$(epq_e 'd["conns"]')" -gt "$CONNS_E" ] && [ "$(epq_e 'd["connected"]')" = true ] \
  && ep_follows "$EMP" false && ep_follows "$FOLLOWX" none; }
until_true e_reopened_without || true
e_reopened_without && pass "a project the directory retires leaves the connection: epsilon reconnects without it" \
  || fail "a project the directory retires leaves the connection: epsilon reconnects without it"
e_row() { printf '%s\n' "$OUT" | awk -v n="$1" '$1 == n { $1 = $1; print }'; }
run_in "$EBARE" "$SMINOS" projects
assert_not_contains "$OUT" "followed-x" "projects hides it"
run_in "$EBARE" "$SMINOS" projects --all
assert_contains "$OUT" "followed-x" "projects --all shows it"
assert_equals "$(e_row followed-x)" "followed-x hub (retired) 0 0 -" "marked retired"
CONN_RETIRED="$(epq_e 'd["current"]')"
ep_e set "{\"org\": $(org_dir false)}"
ep_e send "$(org_sent false)"
e_refollowed() { [ "$(epq_e 'd["current"]')" = "$CONN_RETIRED" ] && ep_follows "$FOLLOWX" true; }
until_true e_refollowed || true
e_refollowed && pass "active again, epsilon follows it again, on the same connection" \
  || fail "active again, epsilon follows it again, on the same connection"
run_in "$EBARE" "$SMINOS" projects
assert_equals "$(e_row followed-x)" "followed-x hub 0 0 -" "and projects lists it"
kill "$E_DAEMON"
set +e; wait "$E_DAEMON"; set -e
assert_not_contains "$(cat "$SMINOS_HOME/daemon.log")" "Traceback" "nothing in epsilon's daemon.log is a traceback"
unset MAWS_USER_DATA

# ---- RL10: two machines through their endpoints (#153 M3d)
# The cases that need a second machine (beta following alpha's projects,
# alpha reading both): alpha and beta are real sminos homes, each with its
# daemon and its endpoint_standin.py, never enrolled at a hub. What one
# endpoint accepted reaches the other's connection as arrivals through the
# stand-in's own echo (rl10_relay); the org's directory is the stand-ins'.
# On RL10 a stray's <message> stays in its machine's host store and goes up
# to the endpoint alone (the epsilon case above), so beta reads alpha's
# stray as a member of alpha's machine project, not its <message>; and the
# endpoint carries no presence, so `machines` names another machine by its
# newest event.
echo "RL10: two machines through their endpoints:"
rl10_as ya alpha
rl10_cut_over
YEPA=$EP
YAMP="$(rl10_mp alpha)"
YBARE="$T/ya/bare"
mkdir -p "$YBARE"
YSTRAY=6a000001-0000-4000-8000-0000000000a1
live_pid
session_record stray "$YSTRAY" "$LIVE_PID" "$YBARE" idle
run_in "$YBARE" "$SMINOS" list
YRO="$T/ya/orgproj"
gitq init -q "$YRO"
write_smns "$YRO" orgproj '{"org": "org-1"}'
YOPID="$(smns_id "$YRO")"
YMA=6a000002-0000-4000-8000-0000000000a2
live_pid
session_record ma "$YMA" "$LIVE_PID" "$YRO" idle
run_in "$YRO" "$SMINOS" list
YRK="$T/ya/chkproj"
gitq init -q "$YRK"
write_smns "$YRK" chkproj '{"org": "org-1"}'
YKPID="$(smns_id "$YRK")"
run_in "$YRK" "$SMINOS" say "chkproj exists"
YFOLLOWX=0f0f0f0f-4444-4222-8333-444455556666
YDIR="$(python3 - "$YOPID" "$YKPID" "$YAMP" "$(rl10_mp beta)" "$YFOLLOWX" <<'PY'
import json, sys
org, chk, amp, bmp, fx = sys.argv[1:6]
print(json.dumps({"projects": [{"id": org, "name": "orgproj", "kind": "hub", "retired": False},
                               {"id": chk, "name": "chkproj", "kind": "hub", "retired": False},
                               {"id": amp, "name": "alpha", "kind": "machine", "machine": "alpha", "retired": False},
                               {"id": bmp, "name": "beta", "kind": "machine", "machine": "beta", "retired": False},
                               {"id": fx, "name": "followed-x", "kind": "hub", "retired": False}],
                  "machines": [{"name": n, "online": False} for n in ("alpha", "beta", "testhost")]}))
PY
)"
rl10_serve "\"org\": $YDIR"
start_daemon
rl10_as yb beta
rl10_cut_over
YEPB=$EP
mkdir -p "$T/yb/bare"
rl10_serve "\"org\": $YDIR"
start_daemon
y_relayed() { rl10_relay "$YEPA" "$YEPB"; "$@"; }
y_follow() { # ep-dir pid → the follow of the live connection's last hello of the project: True | False | none
  python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$1" opened \
    | python3 -c 'import json, sys; o = json.load(sys.stdin)["projects"].get(sys.argv[1]); print(o["follow"] if o else "none")' "$2"
}
y_follows() { [ "$(y_follow "$1" "$2")" = "$3" ]; }
until_true y_follows "$YEPB" "$YOPID" True || true
assert_equals "$(y_follow "$YEPB" "$YOPID")" True "RL10: beta opens orgproj at its endpoint to follow, a project it has no checkout of"
until_true y_follows "$YEPB" "$YAMP" True || true
assert_equals "$(y_follow "$YEPB" "$YAMP")" True "RL10: and alpha's machine project"
y_stray_up() { [ "$(rl10_q "$YEPA" "any(e['kind'] == 'joined' and e.get('session') == '$YSTRAY' for c, e in up('$YAMP'))")" = true ]; }
until_true y_stray_up || true
y_stray_up && pass "RL10: alpha's endpoint takes its stray's joined in alpha's machine project" \
  || fail "RL10: alpha's endpoint takes its stray's joined in alpha's machine project"
y_stray_read() { (cd "$T/yb/bare" && "$SMINOS" list alpha --json 2>/dev/null) | grep -q "\"session\": \"$YSTRAY\""; }
until_true y_relayed y_stray_read || true
y_stray_read && pass "RL10: beta reads alpha's stray in alpha's machine project" \
  || fail "RL10: beta reads alpha's stray in alpha's machine project"
YRB="$T/yb/orgproj"
cp -R "$YRO" "$YRB"
YWB=6b000004-0000-4000-8000-0000000000b4
live_pid
session_record wb "$YWB" "$LIVE_PID" "$YRB" waiting
run_in "$YRB" "$SMINOS" list
until_true y_follows "$YEPB" "$YOPID" False || true
assert_equals "$(y_follow "$YEPB" "$YOPID")" False "RL10: once a session joins it there, beta holds orgproj: hello again with follow false"
until_true y_follows "$YEPB" "$YKPID" True || true
assert_equals "$(y_follow "$YEPB" "$YKPID")" True "RL10: beta follows chkproj, of which it has no checkout"
YRKB="$T/yb/chkproj"
cp -R "$YRK" "$YRKB"
run_in "$YRKB" "$SMINOS" chat
until_true y_follows "$YEPB" "$YKPID" False || true
assert_equals "$(y_follow "$YEPB" "$YKPID")" False "RL10: a registered checkout, no session, makes beta hold it: hello again without follow"
y_offered() {
  [ "$(rl10_q "$YEPB" "any(f.get('t') == 'session' and f['message'].get('kind') == 'machine' and f['message'].get('project') == '$YKPID'
                       and any(c['path'].endswith('/yb/chkproj') for c in f['message']['body'].get('checkouts', [])) for c, f in F)")" = true ]
}
until_true y_offered || true
y_offered && pass "RL10: with the checkout in the machine presence it sends its endpoint" \
  || fail "RL10: with the checkout in the machine presence it sends its endpoint"
y_wb_up() { [ "$(rl10_q "$YEPB" "any(e['kind'] == 'state' and e.get('session') == '$YWB' and e.get('state') == 'waiting' for c, e in up('$YOPID'))")" = true ]; }
until_true y_wb_up || true
y_wb_up && pass "RL10: beta's endpoint takes wb's word in orgproj, waiting" || fail "RL10: beta's endpoint takes wb's word in orgproj, waiting"

echo "RL10: alpha reads both:"
rl10_as ya alpha
y_wb_here() { (cd "$YRO" && "$SMINOS" list --json) | grep -q '"state": "waiting"'; }
until_true y_relayed y_wb_here || true
run_in "$YRO" "$SMINOS" list
assert_equals "$(printf '%s\n' "$OUT" | head -1)" "orgproj" "RL10: list in orgproj prints one heading"
assert_contains "$OUT" "ma [${YMA:0:8}]" "RL10: with alpha's member"
assert_contains "$OUT" "wb [${YWB:0:8}]" "RL10: and beta's"
run_in "$YBARE" "$SMINOS" list --machine beta --state waiting
assert_contains "$OUT" "wb [${YWB:0:8}]" "RL10: --machine beta --state waiting from alpha prints beta's waiting session"
assert_not_contains "$OUT" "ma [" "RL10: and nothing else"
assert_not_contains "$OUT" "stray [" "RL10: nothing else at all"
run_in "$YBARE" "$SMINOS" projects
assert_equals "$(proj_row orgproj)" "orgproj hub 2 1 alpha, beta" "RL10: projects: orgproj a hub project, two live, one waiting, on alpha and beta"
assert_equals "$(proj_row alpha)" "alpha machine 1 0 alpha" "RL10: alpha's machine project"
assert_equals "$(proj_row beta)" "beta machine 0 0 -" "RL10: beta's"
assert_equals "$(proj_row followed-x)" "followed-x hub 0 0 -" "RL10: and the project alpha only follows"
run_in "$YBARE" "$SMINOS" machines
assert_equals "$(mach_row alpha)" "alpha this machine 2 alpha, orgproj" "RL10: machines: alpha is this machine, with its sessions and their projects"
assert_equals "$(mach_row beta | sed -E 's/last event [0-9]+[a-z]+ ago/last event … ago/')" "beta last event … ago 1 orgproj" \
  "RL10: beta by its newest event alpha holds, with its live session and its project"
assert_equals "$(mach_row testhost)" "testhost no event yet 0 -" "RL10: a machine nothing has come from"
for m in ya yb; do
  assert_not_contains "$(cat "$T/$m/s/daemon.log" 2>/dev/null)" "Traceback" "RL10: nothing in $m's daemon.log is a traceback"
done
unset MAWS_USER_DATA

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-org: all $PASSES assertions passed"
else
  echo "test-org: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  for f in "$T"/{e,ya,yb}/s/daemon.log "$T"/{e,ya,yb}/s/run.out; do
    [ -f "$f" ] && { echo "--- $f"; tail -30 "$f"; }
  done
  exit 1
fi
