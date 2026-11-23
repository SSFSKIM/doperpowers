#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh disable=SC2088  # a --cwd of ~/… is the other machine's
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# `sminos spawn --on` between two machines (EN.G1's plan, M3:
# docs/doperpowers/plans/2026-11-21-sminos-environments-en-g1.md, acceptance
# 1 to 5): `mac` runs the Mac side from a session, and `vm1` the VM side,
# which devcloud's stand-in runs for real under vm1's home when mac calls
# `devcloud vm ssh vm1 -- sminos spawn … --asked-from …` (its words joined
# as devcloud joins them, the task on standard input).
#
# - The seat on vm1's home and none on mac's; its `joined` names the
#   spawner; the launch names the spawner's alias, short id, project and
#   machine and carries a task of three lines with quotes, backticks and `$`
#   as written; from a terminal, "the operator"; the carried flags.
# - The VM's refusals: another org, another repository's checkout or none,
#   a directory missing there, not enrolled; `--cwd ~/…` under vm1's home.
# - `--on new`: devcloud's lines first, then the spawn on the host it named;
#   the wait for enrollment, and its end; a cap; an up that names no host.
# - What is not known: a copy that predates the call, a name devcloud has no
#   host for (with the note for a machine of the org), and after `new` made
#   a VM, the kept-VM directions; a stopped seat re-filled, a filled one
#   refused; today's call by hand, unchanged.
# - `--channel` (EN.G2's M1, docs/doperpowers/plans/2026-11-23-sminos-
#   environments-en-g2.md, Interfaces §1): vm1 places the thread by its own
#   statement, registering a channel it did not know; the preamble's
#   qualified tag, run as the child, reaches the spawner beside a
#   channel-mate named for its short (the bare short does not); every
#   command printed run as printed where another log answers to the name;
#   placements that fail after the launch (a registration made uncarried, a
#   channel retired, the identity gone) and the Mac's `channel add` as
#   printed beside a local member named for the remote short; a --worktree
#   landing in a project vm1 does not carry; the merge base's sminos as the
#   VM side; a delay and a held lock under the placement's deadline, and a
#   Mac's bound that ends first, with the inspection it prints run from
#   vm1's login directory; the wait for a welcome not kept yet; the VM's
#   refusals; a terminal's spawn.
#
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine, each
# cut over as an endpoint's welcome leaves it (identity.json) with no daemon
# started; vm1's `claude` is fake_claude.py; origins resolve through git's
# insteadOf to a local bare repository. run-sminos-tests.sh runs this file
# beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smn.XXXXXX)"
T="$(cd "$T" && pwd -P)"
PIDS=()
cleanup() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do wait "$pid" 2>/dev/null || true; done
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
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:1500}"; fi
}
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:900}"
  else pass "$3"; fi
}
assert_rc() { if [[ "$1" == "$2" ]]; then pass "$3"; else fail "$3"; echo "    expected rc $1, got $2"; echo "    ${OUT:0:1500}"; fi; }
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

# SMINOS_RL10 first: no daemon is started here, but an inherited one would name an endpoint outside the test.
unset SMINOS_RL10 CLAUDE_CODE_SESSION_ID CLAUDE_PID SMNS_INTERNAL SMNS_MEMBER DAEMON_HOME AGORA_HOME DAEMON_HOST \
  CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR CLAUDE_CONFIG_DIR MAWS_USER_DATA FAKE_CLAUDE_STATE
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SMINOS_UUID_POLL=5 SMINOS_POLL_INTERVAL=0.05

BARE="$T/origin.git"
OTHER="$T/other.git"
gitq init -q --bare "$BARE"
gitq init -q --bare "$OTHER"
gitconfig() { # home — origins as GitHub names them, resolving to the local bare repositories
  printf '[url "%s"]\n\tinsteadOf = https://github.com/example/repo\n[url "%s"]\n\tinsteadOf = https://github.com/someone/else\n' \
    "$BARE" "$OTHER" > "$1/.gitconfig"
}
identity() { # sminos-home host org — cut over as an endpoint's welcome leaves the machine
  mkdir -p "$1/daemon"
  chmod 700 "$1" "$1/daemon"
  printf '{"org": "%s", "hub": "http://127.0.0.1:9", "name": "%s", "former": {}, "ref": "ref-%s", "enrolled": "2026-11-05T00:00:00.000Z", "cutover": "2026-11-05T00:00:01.000Z", "build": "b"}' \
    "$3" "$2" "$2" > "$1/daemon/identity.json"
  chmod 600 "$1/daemon/identity.json"
}

# ---- vm1: a host whose boot checked the repository out, its claude fake_claude.py
VH="$T/vm1/home"
VS="$T/vm1/s"
mkdir -p "$VH/.claude/sessions" "$VS" "$T/vm1/bin" "$T/vm1/claude"
gitconfig "$VH"
ln -s "$SCRIPT_DIR/fake_claude.py" "$T/vm1/bin/claude"
identity "$VS" vm1 org-1
vm() { HOME="$VH" SMINOS_HOME="$VS" DAEMON_HOST=vm1 FAKE_CLAUDE_STATE="$T/vm1/claude" PATH="$T/vm1/bin:$PATH" "$@"; }

# ---- mac: the repository at a pushed branch, and a session in it
MH="$T/mac/home"
export HOME="$MH" SMINOS_HOME="$T/mac/s" DAEMON_HOST=mac
mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME"
gitconfig "$HOME"
identity "$SMINOS_HOME" mac org-1
WORK="$T/mac/repo"
gitq init -q "$WORK"
gitq -C "$WORK" remote add origin https://github.com/example/repo
gitq -C "$WORK" checkout -q -b topic
gitq -C "$WORK" commit -q --allow-empty -m one
gitq -C "$WORK" push -q origin topic
vm gitq clone -q https://github.com/example/repo "$VH/Developer/GitHub/repo" 2>/dev/null
mkdir -p "$VH/work/x"

S=a1b2c3d4-0000-4000-8000-00000000c0de
sleep 600 & PIDS+=("$!")
printf '{"pid":%s,"sessionId":"%s","name":"boss","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$!" "$S" "$WORK" > "$HOME/.claude/sessions/boss.json"
python3 -B -c 'import sys; sys.path.insert(0, sys.argv[1]); import sminos_records as r
r.establish(sys.argv[2], r.default_provenance("hook"))' "$SCRIPTS" "$S"
(cd "$WORK" && "$SMINOS" list >/dev/null 2>&1) || true
PROJECT_NAME="$(cd "$WORK" && "$SMINOS" project show 2>/dev/null | sed -n 's/^project *\([^ ]*\).*/\1/p' | head -1)"
# vm1 has read the spawner from the project's log, as its download brings it once the spawner's writer comes
# (test-fresh-machine.sh shows the VM side before then): its writer copied into vm1's log, the project's id the same
# on both machines (a hub project derived from the remote).
python3 -B - "$SCRIPTS" "$WORK" "$S" "$SMINOS_HOME" "$VS" <<'PY'
import os, shutil, sys
sys.path.insert(0, sys.argv[1])
import sminos
work, session, mac, vm = sys.argv[2:]
src = sminos.writer_path(sminos.resolve_project(work), "mac/" + session)
dst = os.path.join(vm, os.path.relpath(src, mac))
os.makedirs(os.path.dirname(dst), exist_ok=True)
shutil.copyfile(src, dst)
PY

standin() { # JSON of devcloud-standin.json's members besides sminos and ssh_hosts.vm1 (vm1_env: more of vm1's env;
  # vm1: more of its entry)
  python3 - "$HOME/devcloud-standin.json" "$SMINOS" "$T" "$PATH" "${1:-{\}}" <<'PY'
import json, sys
path, sminos, t, p, more = sys.argv[1:]
cfg = {"sminos": sminos, "ssh_hosts": {"vm1": {"env": {
    "HOME": t + "/vm1/home", "SMINOS_HOME": t + "/vm1/s", "DAEMON_HOST": "vm1", "PATH": t + "/vm1/bin:" + p,
    "FAKE_CLAUDE_STATE": t + "/vm1/claude", "SMINOS_UUID_POLL": "5", "SMINOS_DERIVE_EVERY": "0"}}}}
for k, v in json.loads(more).items():
    if k == "ssh_hosts":
        cfg["ssh_hosts"].update(v)
    elif k == "vm1_env":
        cfg["ssh_hosts"]["vm1"]["env"].update(v)
    elif k == "vm1":
        cfg["ssh_hosts"]["vm1"].update(v)
    else:
        cfg[k] = v
json.dump(cfg, open(path, "w"))
PY
  : > "$HOME/devcloud-standin.calls"
}
calls() { python3 -c 'import json, sys; print(" ".join(json.loads(l)["argv"][1] for l in open(sys.argv[1])))' "$HOME/devcloud-standin.calls"; }
# Mac side from the session: OUT its stdout and stderr together, OUTS its stdout alone, RC its exit.
on() { # alias args... (the task on stdin from TASK)
  set +e
  OUTS="$(cd "$WORK" && printf '%s' "$TASK" | CLAUDE_CODE_SESSION_ID="$S" "$SMINOS" spawn "$1" - "${@:2}" 2>"$T/err")"
  RC=$?
  set -e
  OUT="$OUTS
$(cat "$T/err")"
}
seat_on_vm1() { # alias → "alias by" of its seat and its joined in vm1's log, empty for none
  python3 - "$VS" "$1" <<'PY'
import glob, json, os, sys
home, alias = sys.argv[1:]
seat = [d for d in (json.load(open(p)) for p in glob.glob(os.path.join(home, "*.json"))) if d.get("alias") == alias]
by = ""
for p in glob.glob(os.path.join(home, "projects", "*", "log", "*.jsonl")):
    for line in open(p):
        e = json.loads(line)
        if e.get("kind") == "joined" and e.get("alias") == alias:
            by = e.get("by", "")
print("%s %s" % (alias, by) if seat else "")
PY
}
last_launch() { python3 -c 'import json, sys; print(json.dumps([a for a in map(json.loads, open(sys.argv[1])) if "--bg" in a][-1]))' "$T/vm1/claude/calls.log"; }
ssh_calls() { python3 -c 'import json, sys; print(sum(json.loads(l)["argv"][1] == "ssh" for l in open(sys.argv[1])))' "$HOME/devcloud-standin.calls" 2>/dev/null || echo 0; }
seats_here() { python3 -c 'import glob, json, os, sys; print(" ".join(sorted(json.load(open(p)).get("alias", "") for p in glob.glob(os.path.join(sys.argv[1], "*.json")))))' "$SMINOS_HOME"; }

# shellcheck disable=SC2016  # the task's backticks and $ are its text, sent as written
TASK='Three lines: "quoted", `ticks`
and $HOME as written,
and done.'

echo "== --on vm1 from a session (the VM side runs in none: devcloud vm ssh carries no session)"
standin
on w1 --on vm1
assert_rc 0 "$RC" "spawned on vm1"
assert_contains "$OUTS" "seat spawned on vm1: " "the Mac's line names the VM"
assert_contains "$OUTS" "/w1  [" "and the seat"
assert_contains "$OUTS" 'message it: sminos say "@' "with the address that reaches it"
assert_equals "$(seat_on_vm1 w1)" "w1 boss" "the seat is vm1's, its joined naming the spawner as by"
assert_equals "$(seats_here)" "" "no seat on mac"
LAUNCH="$(last_launch)"
assert_contains "$LAUNCH" "boss (@${S:0:8}, in $PROJECT_NAME on mac; sminos say \\\"@${S:0:8}" "the launch names the spawner's alias, short, project and machine"
# shellcheck disable=SC2016
assert_contains "$LAUNCH" 'Three lines: \"quoted\", `ticks`\nand $HOME as written,\nand done.' "the task arrives as written"
assert_contains "$LAUNCH" "\"--permission-mode\", \"auto\"" "under the mode asked"
assert_equals "$(calls)" "ssh" "one call of devcloud, vm ssh"

echo "== the VM side's flag inside a session (over devcloud vm ssh there is none, as above)"
set +e
OUT="$(cd "$VH/Developer/GitHub/repo" && printf 'a task' | CLAUDE_CODE_SESSION_ID="$S" vm "$SMINOS" spawn w9 - \
  --asked-from='{"v": 1, "nonce": "0123456789abcdef", "org": "org-1", "origin": null, "by": null}' 2>&1)"
RC=$?
set -e
assert_rc 2 "$RC" "refused, as a usage error"
assert_contains "$OUT" "sminos: spawn: --asked-from is the form another machine's sminos calls over devcloud vm ssh, and a session is not one: drop it" "in the words say --notice's refusal has"
assert_not_contains "$OUT" "sminos-spawn " "and no outcome line"
assert_equals "$(seat_on_vm1 w9)" "" "no seat made"

echo "== a client that sends the session variable and a host that accepts it: the call clears it there"
standin "{\"vm1_env\": {\"CLAUDE_CODE_SESSION_ID\": \"$S\"}}"
on w11 --on vm1
assert_rc 0 "$RC" "spawned on vm1, the transport's call no session's"
assert_not_contains "$OUT" "a session is not one" "not refused as a session"
assert_equals "$(seat_on_vm1 w11)" "w11 boss" "the seat is vm1's"

echo "== from a terminal, with the carried flags"
standin
set +e
OUTS="$(cd "$WORK" && printf '%s' "$TASK" | "$SMINOS" spawn w2 - --on vm1 --cwd '~/work/x' --role tester --brief 'its brief' \
  --worktree wt1 --stamp en_test=1 --model opus --effort high --permission-mode plan 2>"$T/err")"
RC=$?
set -e
assert_rc 0 "$RC" "spawned from a terminal"
LAUNCH="$(last_launch)"
assert_contains "$LAUNCH" 'spawned by\nthe operator.' "the preamble says the operator"
for want in '"--permission-mode", "plan"' '"--model", "opus"' '"--effort", "high"' '"--worktree", "wt1"' '"-n", "w2"'; do
  assert_contains "$LAUNCH" "$want" "the VM's launch carries $want"
done
REC="$(python3 -c 'import glob, json, os, sys
for p in glob.glob(os.path.join(sys.argv[1], "*.json")):
    d = json.load(open(p))
    if d.get("alias") == "w2":
        print(d.get("role"), d.get("brief"), d.get("en_test"), d.get("cwd"))' "$VS")"
assert_equals "$REC" "tester its brief 1 $VH/work/x" "role, brief and stamp on the seat, in ~/work/x under vm1's home"

echo "== a stopped seat is re-filled, a filled one refused"
standin
W1_SESSION="$(python3 -c 'import glob, json, os, sys
print(next(json.load(open(p))["current"] for p in glob.glob(os.path.join(sys.argv[1], "*.json")) if json.load(open(p)).get("alias") == "w1"))' "$VS")"
sleep 600 & W1_PID=$!; PIDS+=("$W1_PID")
printf '{"pid":%s,"sessionId":"%s","name":"w1","nameSource":"user","kind":"bg","status":"busy","cwd":"%s"}\n' \
  "$W1_PID" "$W1_SESSION" "$VH/Developer/GitHub/repo" > "$VH/.claude/sessions/w1.json"
on w1 --on vm1
assert_rc 4 "$RC" "a filled seat: the VM's exit"
assert_contains "$OUT" "seat repo/w1 is filled" "its own sentence"
assert_contains "$OUT" "vm1's sminos answered exit 4" "and the Mac's"
kill "$W1_PID" 2>/dev/null || true
wait "$W1_PID" 2>/dev/null || true
rm -f "$VH/.claude/sessions/w1.json"
on w1 --on vm1
assert_rc 0 "$RC" "a stopped seat"
assert_contains "$OUTS" "seat re-filled on vm1: " "is re-filled"

echo "== the VM's refusals"
standin
on w3 --on vm1 --cwd '~/missing'
assert_rc 2 "$RC" "a directory missing there: spawn's own exit"
assert_contains "$OUT" "spawn: cwd does not exist or is not a directory: $VH/missing" "its sentence, under vm1's home"
assert_contains "$OUT" "vm1's sminos answered exit 2" "then the Mac's line"
mv "$VH/Developer/GitHub/repo" "$VH/Developer/GitHub/repo.kept"
vm gitq clone -q https://github.com/someone/else "$VH/Developer/GitHub/repo" 2>/dev/null
on w3 --on vm1
assert_rc 1 "$RC" "another repository's checkout"
assert_contains "$OUT" "is a checkout of github.com/someone/else, and the machine that asked took it for its checkout of github.com/example/repo" "said as such"
assert_equals "$(seat_on_vm1 w3)" "" "no seat"
rm -rf "$VH/Developer/GitHub/repo"
mkdir -p "$VH/Developer/GitHub/repo"
on w3 --on vm1
assert_contains "$OUT" "/Developer/GitHub/repo is no checkout" "no checkout at all"
on w3 --on vm1 --cwd '~/Developer/GitHub/repo'
assert_rc 0 "$RC" "the same directory named with --cwd is spawned in"
rm -rf "$VH/Developer/GitHub/repo"
mv "$VH/Developer/GitHub/repo.kept" "$VH/Developer/GitHub/repo"
identity "$VS" vm1 org-2
on w4 --on vm1
assert_rc 1 "$RC" "vm1 of another org"
assert_contains "$OUT" "spawn: this machine is enrolled in another org than the machine that asked" "the VM's sentence"
standin '{"up": {"name": "vm1"}}'
on w4 --on new
assert_rc 1 "$RC" "another org under --on new"
assert_equals "$(calls)" "up ssh" "is never waited on"
rm "$VS/daemon/identity.json"
standin
on w4 --on vm1
assert_rc 1 "$RC" "vm1 not enrolled"
assert_contains "$OUT" "spawn --on: vm1 is not enrolled in the org" "refused in the Mac's words"
assert_equals "$(seat_on_vm1 w4)" "" "no seat made"

echo "== --on new: the wait for enrollment"
standin '{"up": {"name": "vm1"}}'
( n=0; until [ "$(ssh_calls)" -ge 2 ] || [ $n -ge 600 ]; do sleep 0.05; n=$((n + 1)); done
  identity "$VS" vm1 org-1 ) & PIDS+=("$!")
SMINOS_ON_ENROLL_POLL=0.3 on w5 --on new
assert_rc 0 "$RC" "spawned once the VM enrolled"
assert_contains "$OUT" "vm1 is up and not enrolled in the org yet: waiting up to 11 minutes" "the note"
assert_equals "$(grep -c 'is up and not enrolled' <<<"$OUT")" "1" "said once"
# The host enrolls as the second try is under way: that try, or a third, spawns.
if [[ "$(calls)" == "up ssh ssh" || "$(calls)" == "up ssh ssh ssh" ]]; then pass "tried again on the VM's own word"
else fail "tried again on the VM's own word: $(calls)"; fi
FIRST_READY="$(grep -n 'vm1  ready in' <<<"$OUTS" | cut -d: -f1)"
SPAWN_LINE="$(grep -n 'seat spawned on vm1' <<<"$OUTS" | cut -d: -f1)"
if [ -n "$FIRST_READY" ] && [ -n "$SPAWN_LINE" ] && [ "$FIRST_READY" -lt "$SPAWN_LINE" ]; then
  pass "devcloud's lines before the spawn's"; else fail "devcloud's lines before the spawn's"; fi
assert_contains "$OUT" "vm1 is kept and this session's thread owns it: devcloud vm down vm1 ends it" "and who owns it"
rm "$VS/daemon/identity.json"
standin '{"up": {"name": "vm1"}}'
SMINOS_ON_ENROLL_POLL=0.2 SMINOS_ON_ENROLL_WAIT=0.6 on w6 --on new
assert_rc 1 "$RC" "never enrolled"
assert_contains "$OUT" "spawn --on new: vm1 did not enroll within 0 minutes: nothing was spawned. Once sminos machines lists it, sminos spawn --on vm1 spawns there. The VM vm1 is kept" "past the bound, kept"
identity "$VS" vm1 org-1

echo "== --on new: devcloud's refusals and an up that names nothing"
standin '{"up": {"exit": 4, "lines": ["caps      over the count cap"]}}'
on w7 --on new
assert_rc 4 "$RC" "a cap: devcloud's exit"
assert_contains "$OUT" "pass --vm-confirmed" "the way on"
assert_equals "$(calls)" "up" "no vm ssh"
standin '{"up": {"lines": ["created   vm9 (id 1)"]}}'
on w7 --on new
assert_rc 1 "$RC" "an up that names no host"
assert_contains "$OUT" "did not name one host where sminos reads it" "said so"

echo "== what is not known"
standin '{"ssh_hosts": {"vmold": {"exit": 2}}}'
on w8 --on vmold
assert_rc 2 "$RC" "a copy that predates the call: its exit"
assert_contains "$OUT" "the outcome on vmold is not known (no outcome line came back)" "not known"
assert_contains "$OUT" "so its sminos may predate this call" "and why it may be"
assert_not_contains "$OUT" "nothing was spawned" "never nothing spawned"
standin
on w8 --on mini
assert_rc 1 "$RC" "a name devcloud has no VM for"
assert_contains "$OUT" "devcloud vm: no VM named mini in any usable account" "devcloud's line"
assert_contains "$OUT" "the outcome on mini is not known" "then not known"
printf '{"projects": [], "machines": [{"name": "mini"}], "at": ""}' > "$SMINOS_HOME/daemon/org.json"
on w8 --on mini
assert_contains "$OUT" "mini is a machine of this org that devcloud has no host for. If it is a Mac" "the note for a machine of the org"
rm "$SMINOS_HOME/daemon/org.json"
standin '{"up": {"name": "dc-gone-0001"}}'
on w8 --on new
assert_contains "$OUT" "the outcome on dc-gone-0001 is not known" "under new, a host ssh does not know"
assert_contains "$OUT" "The VM dc-gone-0001 is kept and this session's thread owns it" "the kept-VM directions"

echo "== today's call by hand"
standin
set +e
OUT="$(cd "$WORK" && "$SMINOS_DEVCLOUD" vm ssh vm1 -- sminos spawn w9 "by hand" 2>&1)"; RC=$?
set -e
assert_rc 0 "$RC" "spawns on an enrolled home"
assert_contains "$OUT" "seat spawned: " "and prints its line as before"
rm "$VS/daemon/identity.json"
set +e
OUT="$(cd "$WORK" && "$SMINOS_DEVCLOUD" vm ssh vm1 -- sminos spawn w10 "by hand" 2>&1)"; RC=$?
set -e
assert_rc 0 "$RC" "and on one that is not"
assert_contains "$OUT" "seat spawned: " "as before"

# ------------------------------------------------------------ spawn --on --channel (EN.G2's M1, Interfaces §1)

DESK=5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c
LOBBY=0123abcd-4567-8abc-a123-456789abcdef
OTHERDESK=00000001-0000-8000-8000-000000000000
py() { python3 -B - "$SCRIPTS" "$@"; }
register() { # sminos-home id name [org] — a channel registered as the org's directory registers one
  SMINOS_HOME="$1" py "$2" "$3" "${4:-org-1}" <<'PY2'
import sys
sys.path.insert(0, sys.argv[1])
import sminos
cid, name, org = sys.argv[2:]
sminos.register_if_absent(sminos.make_project(cid, name, "", "", {"url": "http://127.0.0.1:9", "org": org}))
PY2
}
welcome() { # sminos-home [capabilities as JSON] — the welcome its uplink kept
  printf '{"v": 1, "sessions": {}, "capabilities": %s}\n' "${2:-[\"channels\"]}" > "$1/daemon/audiences.json"
}
seat_session() { # alias → the vm1 seat's current session
  python3 -c 'import glob, json, os, sys
print(next((d["current"] for d in map(lambda p: json.load(open(p)), glob.glob(os.path.join(sys.argv[1], "*.json"))) if d.get("alias") == sys.argv[2]), ""))' "$VS" "$1"
}
stated() { # session → "<writer> <channels…>" of its statements in vm1's logs, after its joined, one a line
  python3 - "$VS" "$1" <<'PY2'
import glob, json, os, sys
home, sid = sys.argv[1:]
for p in glob.glob(os.path.join(home, "projects", "*", "log", "*.jsonl")):
    joined = False
    for line in open(p):
        e = json.loads(line)
        if e.get("session") != sid:
            continue
        joined = joined or e["kind"] == "joined"
        if e["kind"] == "channels":
            print("%s %s%s" % (e["writer"], " ".join(e["channels"]), "" if joined else " (before its joined)"))
PY2
}
log_of() { # sminos-home id — the events of a channel's log there, one a line
  cat "$1/projects/$2/log/"*.jsonl 2>/dev/null || true
}
identity "$VS" vm1 org-1
welcome "$VS"
register "$SMINOS_HOME" "$DESK" desk
register "$SMINOS_HOME" "$LOBBY" lobby

echo "== --on vm1 --channel: the VM places the thread by its own statement, registering what it did not know"
standin
on c1 --on vm1 --channel desk --channel "$LOBBY"
assert_rc 0 "$RC" "spawned and placed"
[ "$RC" = 0 ] || echo "$OUT"
C1="$(seat_session c1)"
assert_contains "$OUTS" "seat spawned on vm1: " "the seat's line"
assert_contains "$OUTS" "c1#${C1:0:8}: in desk" "then desk's, by the session's first eight"
assert_contains "$OUTS" "c1#${C1:0:8}: in lobby" "and lobby's"
assert_equals "$(stated "$C1" | tail -1)" "vm1/$C1 $DESK $LOBBY" "its statements under the new session's writer, the last its whole set"
assert_not_contains "$(stated "$C1")" "before its joined" "each after its joined"
assert_equals "$(log_of "$VS" "$DESK")" "" "no request in desk's log on vm1"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["name"])' "$VS/projects/$DESK/project.json")" \
  "desk" "vm1 registered desk under the name sent"
LAUNCH="$(last_launch)"
assert_contains "$LAUNCH" "You are being placed in the channel \\\"desk\\\", as your spawner asked: once that is recorded on your machine, \`sminos list $DESK\`" "the preamble says it by the id"
PID_MAC="$(py "$WORK" <<'PY2'
import sys
sys.path.insert(0, sys.argv[1])
import sminos
print(sminos.resolve_project(sys.argv[2]).id)
PY2
)"
assert_contains "$LAUNCH" "boss (@$PID_MAC/${S:0:8}, in $PROJECT_NAME on mac; sminos say \\\"@$PID_MAC/${S:0:8}" "and gives the spawner's qualified address"

echo "== the preamble's tag, run as the child on vm1, reaches the spawner beside a channel-mate named for its short"
# Another machine's thread in another project, in desk, its alias the spawner's short (as vm1's download keeps it).
FAR=f0000000-0000-4000-8000-0000000000f1
FARP=7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d
SMINOS_HOME="$VS" HOME="$VH" DAEMON_HOST=vm1 py "$FARP" "$FAR" "${S:0:8}" "$DESK" <<'PY2'
import sys
sys.path.insert(0, sys.argv[1])
import sminos
pid, sid, alias, desk = sys.argv[2:]
p = sminos.make_project(pid, "far", "", "", {"url": "http://127.0.0.1:9", "org": "org-1"})
sminos.register_if_absent(p)
p = sminos.known_project(pid)
w = "beta/" + sid
sminos.log_append(p, w, "joined", session=sid, alias=alias, name_source="user", machine="beta", cwd="/w", worktree="",
                  role="", seat="", by="", session_kind="interactive", thread=sid)
sminos.log_append(p, w, "state", session=sid, state="idle", machine="beta")
sminos.log_append(p, w, "channels", session=sid, thread=sid, op="0" * 16, channels=[desk])
PY2
as_child() { # session command... — run on vm1 as that session, from its seat's directory
  local sid=$1; shift
  (cd "$VH/Developer/GitHub/repo" && CLAUDE_CODE_SESSION_ID="$sid" vm "$@")
}
said_to() { # writer [sminos-home] — the sessions the last say under it names, on vm1 unless another home is named
  python3 - "${2:-$VS}" "$1" <<'PY2'
import glob, json, os, sys
home, writer = sys.argv[1:]
last = None
for p in glob.glob(os.path.join(home, "projects", "*", "log", "*.jsonl")):
    for line in open(p):
        e = json.loads(line)
        if e.get("writer") == writer and e.get("kind") == "say":
            last = e
print(" ".join(t.get("session", "") for t in (last or {}).get("to") or []))
PY2
}
set +e
OUT="$(as_child "$C1" "$SMINOS" say "@$PID_MAC/${S:0:8} hello from the VM" 2>&1)"; RC=$?
set -e
assert_rc 0 "$RC" "the qualified tag is said"
assert_equals "$(said_to "vm1/$C1")" "$S" "and it reaches the spawner's session"
set +e
OUT="$(as_child "$C1" "$SMINOS" say "@${S:0:8} hello" 2>&1)"; RC=$?
set -e
assert_equals "$(said_to "vm1/$C1")" "$FAR" "the bare short reaches the channel-mate: the limit the qualified address is for"

echo "== every command printed, run as printed where another log answers to its name"
# vm1 knows desk as `ops`, and another channel as `desk`; this Mac has two channels named desk.
python3 - "$VS/projects/$DESK/project.json" <<'PY2'
import json, sys
d = json.load(open(sys.argv[1])); d["name"] = "ops"; json.dump(d, open(sys.argv[1], "w"))
PY2
register "$VS" "$OTHERDESK" desk
register "$SMINOS_HOME" "$OTHERDESK" desk
standin
on c2 --on vm1 --channel "$DESK"
assert_rc 0 "$RC" "spawned, desk named by its id"
C2="$(seat_session c2)"
assert_contains "$OUTS" "c2#${C2:0:8}: in desk" "the Mac's line says the name it knows"
LAUNCH="$(last_launch)"
assert_contains "$LAUNCH" "placed in the channel \\\"ops\\\"" "the preamble the name vm1 knows"
CMDS="$(python3 -c 'import json, re, sys
task = json.loads(sys.argv[1])[-1]
sentence = task[task.index("You are being placed"):].split("\n")[0]
print("\n".join(re.findall(r"`(sminos [^`]*)`", sentence)))' "$LAUNCH")"
assert_equals "$(wc -l <<<"$CMDS" | tr -d ' ')" "3" "three commands in it"
while IFS= read -r cmd; do
  run="${cmd//…/said as printed}"
  set +e
  GOT="$(as_child "$C2" bash -c "${run/sminos/\"\$0\"}" "$SMINOS" 2>&1)"; RC=$?
  set -e
  assert_rc 0 "$RC" "ran as printed: $cmd"
  case "$cmd" in
    *list*) assert_contains "$GOT" "c2" "it lists the thread in desk" ;;
  esac
done <<<"$CMDS"
assert_contains "$(log_of "$VS" "$DESK")" "said as printed" "what it said is in desk's log"
assert_not_contains "$(log_of "$VS" "$OTHERDESK")" "said as printed" "and not in the other desk's"

launches() { grep -c '"--bg"' "$T/vm1/claude/calls.log" 2>/dev/null || echo 0; }
during_launch() { # the shell words run while vm1's next launch is held (fake_claude's bg-sleep)
  local before
  before="$(launches)"
  echo 1 > "$T/vm1/claude/bg-sleep"
  ( n=0; until [ "$(launches)" -gt "$before" ] || [ $n -ge 600 ]; do sleep 0.05; n=$((n + 1)); done; eval "$1" ) &
  PIDS+=("$!")
}
settled() { rm -f "$T/vm1/claude/bg-sleep"; wait "${PIDS[${#PIDS[@]}-1]}" 2>/dev/null || true; }

echo "== after the launch nothing is a refusal: a registration made uncarried, a channel retired, the identity gone"
# lobby made hubless (an older copy's registration) and desk retired in vm1's directory while the engine launches.
LOBBY_REG="$(cat "$VS/projects/$LOBBY/project.json")"
during_launch "printf '{\"project\": \"$LOBBY\", \"name\": \"lobby\", \"remote\": \"\", \"root\": \"\"}' > '$VS/projects/$LOBBY/project.json'; printf '{\"projects\": [{\"id\": \"$DESK\", \"name\": \"ops\", \"kind\": \"channel\", \"retired\": true}], \"machines\": [], \"at\": \"\"}' > '$VS/daemon/org.json'"
standin
BEFORE="$(launches)"
on c3 --on vm1 --channel "$LOBBY" --channel "$DESK"
settled
C3="$(seat_session c3)"
assert_rc 0 "$RC" "the spawn stands"
assert_equals "$(( $(launches) - BEFORE ))" "1" "one launch"
assert_contains "$OUT" "spawn completed, but c3#${C3:0:8} was not placed in lobby on vm1 (its machine's enrollment does not carry it now): sminos channel add $LOBBY $C3 asks its machine, once sminos list --machine vm1 shows it here" "lobby: not carried now, and the command that asks for it"
assert_contains "$OUT" "was not placed in desk on vm1 (its machine's enrollment does not carry it now)" "desk retired: likewise"
assert_equals "$(stated "$C3")" "" "no statement"
printf '%s' "$LOBBY_REG" > "$VS/projects/$LOBBY/project.json"
rm -f "$VS/daemon/org.json"

echo "== the Mac's channel add, as printed, asks for the remote thread where a local member's alias is its short"
# What vm1 wrote of c3 reaches this Mac's copy of the project's log, as the download brings it; a local member here
# is named for c3's short.
py "$WORK" "$VS" "$SMINOS_HOME" "$C3" <<'PY2'
import glob, os, shutil, sys
sys.path.insert(0, sys.argv[1])
work, vm, mac, sid = sys.argv[2:]
for src in glob.glob(os.path.join(vm, "projects", "*", "log", "vm1." + sid + "*.jsonl")):
    dst = os.path.join(mac, os.path.relpath(src, vm))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
PY2
L=b1b2c3d4-0000-4000-8000-00000000beef
sleep 600 & PIDS+=("$!")
printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$!" "$L" "${C3:0:8}" "$WORK" > "$HOME/.claude/sessions/local.json"
(cd "$WORK" && "$SMINOS" list >/dev/null 2>&1) || true
welcome "$SMINOS_HOME"
ADD="$(grep -o "sminos channel add $LOBBY $C3" <<<"$OUT" | head -1)"
set +e
GOT="$(cd "$WORK" && CLAUDE_CODE_SESSION_ID="$S" bash -c "${ADD/sminos/\"\$0\"}" "$SMINOS" 2>&1)"; RC=$?
set -e
assert_contains "$GOT" "c3#${C3:0:8}: asked; pending on vm1" "asked of vm1 for the remote thread"
REQ="$(log_of "$SMINOS_HOME" "$LOBBY" | grep channel-request | tail -1 || true)"
assert_contains "$REQ" "\"session\": \"$C3\"" "the request names its session"
assert_not_contains "$REQ" "$L" "and never the local member"
SAY="$(grep -o 'sminos say "@[^"]*"' <<<"$OUT" | head -1)"
assert_equals "$SAY" "sminos say \"@$C3 …\"" "the banner names the placed thread by its whole session id"
set +e
GOT="$(cd "$WORK" && CLAUDE_CODE_SESSION_ID="$S" bash -c "${SAY/sminos/\"\$0\"}" "$SMINOS" 2>&1)"; RC=$?
set -e
assert_rc 0 "$RC" "its say, run as printed beside a local member named for its short"
assert_equals "$(said_to "mac/$S" "$SMINOS_HOME")" "$C3" "reaches the remote thread, not the local member"
rm "$HOME/.claude/sessions/local.json"

echo "== the identity gone to another org by the placement: no statement, one warning, no command"
during_launch "identity '$VS' vm1 org-2"
standin
on c4 --on vm1 --channel "$DESK"
settled
C4="$(seat_session c4)"
assert_rc 0 "$RC" "the spawn stands"
assert_contains "$OUT" "spawn completed, but none of the placements asked for was made: vm1 is no longer enrolled in this org" "said once"
assert_not_contains "$OUT" "channel add" "with no command"
assert_equals "$(stated "$C4")" "" "no statement"
assert_contains "$OUT" "which its enrollment does not carry (this machine is not enrolled in the org)" \
  "G1's no-reach note, from the placement's own read"
assert_not_contains "$OUT" "it is listed here once" "and no promise"
identity "$VS" vm1 org-1

echo "== the seat's project made uncarried by the placement: G1's note from the placement's own read, one warning"
# The project the seat is filed in, carried at the launch, retired in vm1's directory while the engine launches.
during_launch "printf '{\"projects\": [{\"id\": \"$PID_MAC\", \"name\": \"repo\", \"retired\": true}], \"machines\": [], \"at\": \"\"}' > '$VS/daemon/org.json'"
standin
on c4b --on vm1 --channel "$DESK"
settled
C4B="$(seat_session c4b)"
assert_rc 0 "$RC" "the spawn stands"
assert_contains "$OUT" "which its enrollment does not carry (the org's directory has retired it)" "G1's no-reach note"
assert_contains "$OUT" "none of the placements asked for (desk) was made: its project on vm1 is not carried" "one warning"
assert_not_contains "$OUT" "it is listed here once" "and no promise"
assert_equals "$(stated "$C4B")" "" "no statement"
rm -f "$VS/daemon/org.json"

echo "== the seat's directory mapped to another project, one vm1 does not carry, by the placement: that one is named"
# At the launch the seat's checkout is in the project its remote derives (repo); a .smns written there meanwhile
# files it in another, of another org. The outcome names the project the placement read, with its reason.
during_launch "printf '{\"project\": \"5e000000-0000-4000-8000-0000000000b2\", \"name\": \"elsewhere\", \"remote\": \"\", \"hub\": {\"org\": \"org-2\"}}' > '$VH/Developer/GitHub/repo/.smns'"
standin
on c4c --on vm1 --channel "$DESK"
settled
rm -f "$VH/Developer/GitHub/repo/.smns"
assert_rc 0 "$RC" "the spawn stands"
assert_contains "$OUT" "vm1 filed this seat in its project elsewhere, which its enrollment does not carry (its .smns names another org)" \
  "the project the placement read, named with its reason"
assert_not_contains "$OUT" "its project repo" "never the launch's project beside it"
assert_not_contains "$OUT" "it is listed here once" "and no promise"

echo "== the seat's carriage not read within the placement's deadline: no promise"
standin '{"vm1_env": {"SMINOS_PLACE_BUDGET": "0.000001"}}'
on c4d --on vm1 --channel "$DESK"
assert_rc 0 "$RC" "the spawn stands"
assert_contains "$OUT" "whether its enrollment carries that project could not be read once it was placed" "said so"
assert_not_contains "$OUT" "it is listed here once" "and no promise"
assert_contains "$OUT" "the time for placing ran out" "its placement: time"

echo "== --worktree onto a seat already in desk, landing in a project vm1 does not carry: no placement at all"
mkdir -p "$VH/work/stale"   # the engine's checkout: a stale .smns naming another org, a project vm1 does not carry
printf '{"project": "5e000000-0000-4000-8000-00000000057a", "name": "stale", "remote": "", "hub": {"org": "org-2"}}' \
  > "$VH/work/stale/.smns"
echo "$VH/work/stale" > "$T/vm1/claude/bg-cwd"
standin
on c1 --on vm1 --channel "$DESK" --channel "$OTHERDESK" --worktree wt9
rm "$T/vm1/claude/bg-cwd"
assert_rc 0 "$RC" "the spawn stands"
assert_contains "$OUT" "which its enrollment does not carry" "G1's note"
assert_contains "$OUT" "none of the placements asked for (desk, desk) was made: its project on vm1 is not carried, and this project's memberships will not be seen from here" "then one warning"
for absent in "channel add" "once it is listed here" ": in desk" "not placed in"; do
  assert_not_contains "$OUT" "$absent" "nothing said of which channels it is in ($absent)"
done
C1B="$(seat_session c1)"
assert_equals "$(stated "$C1B")" "" "no statement under the refill's writer"
assert_contains "$(python3 -c 'import glob, json, os, sys
print(next(json.load(open(p)).get("channels") for p in glob.glob(os.path.join(sys.argv[1], "*.json")) if json.load(open(p)).get("alias") == "c1"))' "$VS")" "$DESK" "the seat's record still holds desk"

echo "== the merge base's sminos as the VM side, onto a seat already in one of two channels asked and in a third"
OLD="$T/old"
mkdir -p "$OLD"
TOP="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
MERGE_BASE=1b5b56f977cde0d79c9b42ba9ef5d5c2d6e9ba58   # `git merge-base origin/main HEAD` when M1 was built (1.55.1)
git -C "$TOP" cat-file -e "$MERGE_BASE^{commit}" 2>/dev/null || git -C "$TOP" fetch -q --depth=1 origin "$MERGE_BASE"
git -C "$TOP" archive "$MERGE_BASE" sminos | tar -x -C "$OLD"
held_by() { python3 -c 'import glob, json, os, sys
print(" ".join(next(json.load(open(p)).get("channels") for p in glob.glob(os.path.join(sys.argv[1], "*.json")) if json.load(open(p)).get("alias") == sys.argv[2])))' "$VS" "$1"; }
standin
on c2 --on vm1 --channel "$OTHERDESK"   # by this version: c2 is in desk and the other desk
assert_equals "$(held_by c2)" "$DESK $OTHERDESK" "(c2 in desk and a third channel)"
standin "{\"sminos\": \"$OLD/sminos/skills/sminos/scripts/sminos\"}"
on c2 --on vm1 --channel "$DESK" --channel "$LOBBY"
assert_rc 0 "$RC" "the thread opens"
assert_equals "$(held_by c2)" "$DESK $OTHERDESK" "the seat still in the two it was in: an older VM changes no membership"
C2B="$(seat_session c2)"
assert_contains "$OUT" "spawn completed, but vm1's sminos did not carry out the placements asked for (it predates spawn --channel). Which channels c2#${C2B:0:8} is in is not known here" "the Mac says the VM did not carry them out"
assert_contains "$OUT" "It was told to reach you as @${S:0:8}" "and which address the child was given"
assert_not_contains "$OUTS" ": in desk" "naming no channel it is in"

echo "== time: a delay before the VM side starts, and a lock another process holds on the second channel"
FRESH=00000002-0000-8000-8000-000000000000
register "$SMINOS_HOME" "$FRESH" fresh
mkdir -p "$VS/projects/$FRESH"
python3 -c 'import fcntl, sys, time
f = open(sys.argv[1], "a"); fcntl.flock(f, fcntl.LOCK_EX); open(sys.argv[2], "w").close(); time.sleep(600)' \
  "$VS/projects/$FRESH/project.json.lock" "$T/locked" & LOCKER=$!; PIDS+=("$LOCKER")
until [ -e "$T/locked" ]; do sleep 0.05; done
standin "{\"vm1_env\": {\"SMINOS_PLACE_BUDGET\": \"2\"}, \"vm1\": {\"said\": \"$T/said\", \"hold\": \"$T/go\"}}"
( until [ -e "$T/said" ]; do sleep 0.05; done; sleep 1; touch "$T/go" ) & PIDS+=("$!")
BEFORE="$(launches)"
on c5 --on vm1 --channel "$DESK" --channel "$FRESH"
C5="$(seat_session c5)"
assert_rc 0 "$RC" "the spawn stands"
assert_contains "$OUTS" "c5#${C5:0:8}: in desk" "the first channel placed"
assert_contains "$OUT" "was not placed in fresh on vm1 (the time for placing ran out): sminos channel add $FRESH $C5" "the second's time ran out"
assert_equals "$(( $(launches) - BEFORE ))" "1" "one launch"
rm -f "$T/said" "$T/go"
echo "-- and a Mac whose own bound ends while vm1 still waits on that lock"
standin "{\"vm1_env\": {\"SMINOS_PLACE_BUDGET\": \"60\"}}"
BEFORE="$(launches)"
SMINOS_ON_TIMEOUT=6 on c6 --on vm1 --channel "$DESK" --channel "$FRESH"
C6="$(seat_session c6)"
if [ "$RC" -ne 0 ]; then pass "the Mac exits non-zero"; else fail "the Mac exits non-zero"; fi
assert_contains "$OUT" "vm1 gave no outcome within 1 minutes, and the call was stopped: a session may or may not have started there. Do not spawn it again before looking" "not known, and where to look"
assert_contains "$OUT" "a channel that does not list it shows nothing about whether it was launched" "and what a channel's list does not show"
assert_not_contains "$OUTS" "seat spawned on" "no spawn said"
assert_equals "$(stated "$C6" | tail -1)" "vm1/$C6 $DESK" "vm1's own store holds the seat and the first statement"
assert_equals "$(( $(launches) - BEFORE ))" "1" "one launch"
LOOK="$(grep -o 'devcloud vm ssh vm1 -- sminos list --here --all' <<<"$OUT" | head -1)"
set +e
LISTED="$(cd "$VH" && bash -c "${LOOK/devcloud/\"\$0\"}" "$SMINOS_DEVCLOUD" 2>&1)"
set -e
assert_contains "$LISTED" "c6" "the inspection, run as printed from vm1's login directory, lists the seat"
assert_contains "$OUT" "devcloud vm ssh vm1 -- claude agents the engine's jobs there" "and the engine's jobs"
kill "$LOCKER" 2>/dev/null || true

echo "== a VM that has kept no welcome is waited on, then spawned; at the wait's end, exit 75 and no launch"
rm "$VS/daemon/audiences.json"
standin
: > "$T/err"   # the welcome kept again once the Mac has said it waits for one, on `on`'s standard error
( n=0; until grep -q "has kept no welcome of its endpoint yet" "$T/err" 2>/dev/null || [ $n -ge 600 ]; do
    sleep 0.05; n=$((n + 1)); done
  welcome "$VS" ) & PIDS+=("$!")
SMINOS_ON_ENROLL_POLL=0.5 on c7 --on vm1 --channel "$DESK"
assert_rc 0 "$RC" "spawned once the welcome is kept"
assert_contains "$OUT" "vm1's sminos has kept no welcome of its endpoint yet" "the note"
assert_contains "$OUTS" ": in desk" "and placed"
rm "$VS/daemon/audiences.json"
standin
BEFORE="$(launches)"
CALLS="$(ssh_calls)"
# Coarse here (test_on.py proves the exact end on a fake clock): one whole try, its refusal, a poll as long as the
# wait, and the end, so no try is begun with a fraction of a second left (one too short for ssh times out, exit 1).
SMINOS_ON_ENROLL_POLL=1 SMINOS_ON_ENROLL_WAIT=1 on c8 --on vm1 --channel "$DESK"
assert_rc 75 "$RC" "the wait's end"
assert_equals "$(( $(ssh_calls) - CALLS ))" "1" "after one whole try"
assert_contains "$OUT" "vm1's sminos had kept no welcome of its endpoint within 0 minutes" "its words"
assert_contains "$OUT" "spawn the seat again with --on vm1 (keep the alias, the task and each --channel; leave out --vm-project and --vm-confirmed" "and the way on"
assert_equals "$(launches)" "$BEFORE" "no launch"

echo "== the VM's refusals: an endpoint that serves no channels, a channel it does not carry, the spawner shadowed"
welcome "$VS" '["access"]'
standin '{"up": {"name": "vm1"}}'
on c9 --on new --channel "$DESK"
assert_rc 1 "$RC" "refused"
assert_contains "$OUT" "this machine's endpoint serves no channels" "the VM's line"
assert_contains "$OUT" "The VM vm1 is kept and this session's thread owns it" "a VM --on new made is said kept, and whose"
welcome "$VS"
ROOM_ID=00000003-0000-8000-8000-000000000000
register "$VS" "$ROOM_ID" room org-2
register "$SMINOS_HOME" "$ROOM_ID" room
standin
on c9 --on vm1 --channel room
assert_rc 1 "$RC" "a channel vm1 does not carry"
assert_contains "$OUT" "does not carry the log of channel room ($ROOM_ID)" "named"
python3 - "$VS" "$PID_MAC" "${S:0:8}" "$SCRIPTS" <<'PY2'
import os, sys
home, pid, short, scripts = sys.argv[1:]
os.environ["SMINOS_HOME"] = home
sys.path.insert(0, scripts)
import sminos
p = sminos.known_project(pid)
sid = "eeee2222-0000-4000-8000-0000000000aa"
sminos.log_append(p, "beta/" + sid, "joined", session=sid, alias=short, name_source="user", machine="beta", cwd="/w",
                  worktree="", role="", seat="", by="", session_kind="interactive")
PY2
standin
on c9 --on vm1 --channel "$DESK"
assert_rc 1 "$RC" "the spawner shadowed in its own project"
assert_contains "$OUT" "spawn: the spawner's address, @$PID_MAC/${S:0:8}, names" "in the qualified form"

echo "== from a terminal, --on vm1 --channel places the thread"
standin
set +e
OUTS="$(cd "$WORK" && printf 'a task' | "$SMINOS" spawn c10 - --on vm1 --channel "$DESK" 2>"$T/err")"; RC=$?
set -e
C10="$(seat_session c10)"
assert_rc 0 "$RC" "spawned"
assert_contains "$OUTS" "c10#${C10:0:8}: in desk" "and placed"

echo
if [ "$FAILURES" -eq 0 ]; then echo "all $PASSES assertions passed"; else
  echo "$FAILURES of $((PASSES + FAILURES)) assertions FAILED"; exit 1; fi
