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

standin() { # JSON of devcloud-standin.json's members besides sminos and ssh_hosts.vm1
  python3 - "$HOME/devcloud-standin.json" "$SMINOS" "$T" "$PATH" "${1:-{\}}" <<'PY'
import json, sys
path, sminos, t, p, more = sys.argv[1:]
cfg = {"sminos": sminos, "ssh_hosts": {"vm1": {"env": {
    "HOME": t + "/vm1/home", "SMINOS_HOME": t + "/vm1/s", "DAEMON_HOST": "vm1", "PATH": t + "/vm1/bin:" + p,
    "FAKE_CLAUDE_STATE": t + "/vm1/claude", "SMINOS_UUID_POLL": "5", "SMINOS_DERIVE_EVERY": "0"}}}}
for k, v in json.loads(more).items():
    if k == "ssh_hosts":
        cfg["ssh_hosts"].update(v)
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

echo "== --on vm1 from a session"
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

echo
if [ "$FAILURES" -eq 0 ]; then echo "all $PASSES assertions passed"; else
  echo "$FAILURES of $((PASSES + FAILURES)) assertions FAILED"; exit 1; fi
