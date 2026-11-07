#!/usr/bin/env bash
#
# Hub projects, and the `hub` verbs on a machine whose enrollment is its
# endpoint's. `project init --hub` writes the org of the identity the
# endpoint gave (daemon/identity.json); a hub project, a malformed hub
# included, runs no git phase and `project attach` refuses it, and a
# conversion racing a tick's git sync leaves no git event in the hub log.
# `hub enroll`, `check` and `leave` say where the enrollment is made
# (`mawsd endpoint enroll|status`) and exit 1, reading no word given after
# them; `hub show` prints the endpoint's identity, or says the same and exits
# 1 on a machine no endpoint welcomed. A stray hub.json enrolls nothing.
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per installation;
# `claude` is a stub; nothing reaches a network beyond 127.0.0.1.
# run-sminos-tests.sh runs this file beside its own cases.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="$PLUGIN_ROOT/skills/sminos/scripts"
SMINOS="$SCRIPTS/sminos"

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smh.XXXXXX)"
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
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:900}"; fi
}
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:900}"
  else pass "$3"; fi
}
assert_rc() { if [[ "$1" == "$2" ]]; then pass "$3"; else fail "$3"; echo "    expected rc $1, got $2"; fi; }
# Every output of the CLI is kept, to be searched for secrets at the end.
run() { set +e; OUT="$("$@" 2>&1)"; RC=$?; set -e; printf '%s\n' "$OUT" >> "$T/all.out"; }
# Polls every 50 ms until the command holds. The leading count is kept for the
# call sites, but the ceiling is one liveness bound, 30 s, not a claim about the
# machine's speed (ci-kit §6): a loaded host is slow, not wrong.
until_true() { # tries command...
  local end=$((SECONDS + 30)); shift
  until "$@"; do
    [ "$SECONDS" -ge "$end" ] && return 1
    sleep 0.05
  done
}
gitq() { git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }
json_get() { python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(json.dumps(eval(sys.argv[2], {"d": d})))' "$@"; }

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL DAEMON_HOME AGORA_HOME DAEMON_HOST MAWS_USER_DATA SMINOS_RL10
export SMINOS_DERIVE_EVERY=0
export DAEMON_BOOT_ID=boot-current
mkdir -p "$T/bin"
# One installation: its HOME, its SMINOS_HOME, its host name.
as() { # name host — the installation `name` is the one the verbs after it run as
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}

# A stub `claude`: `agents` lists $STUB_STATE/agents.json; `stop` is recorded.
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
  stop) echo "$2" >> "$STUB_STATE/stops"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

# Machines cut over as an endpoint's welcome leaves one (identity.json,
# rl10_cut_over), of org-1 at the identity's hub.
# shellcheck source=rl10-machines.sh
source "$SCRIPT_DIR/rl10-machines.sh"
HUB="http://127.0.0.1:9"
mode_of() { python3 -c 'import os, stat, sys; print(oct(stat.S_IMODE(os.stat(sys.argv[1]).st_mode)))' "$1"; }
# A hub.json as `hub enroll` wrote it, left behind: no enrollment now.
stray_hub_json() { # machine
  python3 - "$SMINOS_HOME/daemon/hub.json" "$1" <<'PY'
import json, os, sys
os.makedirs(os.path.dirname(sys.argv[1]), mode=0o700, exist_ok=True)
with open(sys.argv[1], "w") as f:
    json.dump({"hub": "http://127.0.0.1:9", "org": "org-1", "machine": sys.argv[2], "client_id": "c",
               "client_secret": "s", "key": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8", "former": {},
               "enrolled": "2026-10-01T00:00:00Z"}, f)
os.chmod(sys.argv[1], 0o600)
PY
}
POINTER="this machine's enrollment is its endpoint's: \`mawsd endpoint enroll|status\`"

# ---- the hub verbs on a machine no endpoint welcomed
echo "the hub verbs, before any welcome:"
as n nu
for verb in enroll check leave; do
  run "$SMINOS" hub "$verb"
  assert_rc 1 "$RC" "hub $verb exits 1"
  assert_contains "$OUT" "$POINTER" "hub $verb says the enrollment is the endpoint's"
  assert_contains "$OUT" "sminos takes it at the endpoint's first welcome" "and that sminos takes it at the first welcome"
done
run "$SMINOS" hub enroll --name other smns-enroll-v1.eyJzZWNyZXQiOiJ3b3JkIn0
assert_rc 1 "$RC" "hub enroll with words after it exits 1 too"
assert_contains "$OUT" "$POINTER" "with the same line"
assert_not_contains "$OUT" "smns-enroll-v1" "never echoing a word it was given"
assert_not_contains "$OUT" "other" "not even the name"
run "$SMINOS" hub show
assert_rc 1 "$RC" "hub show exits 1 with no identity"
assert_contains "$OUT" "$POINTER" "saying the enrollment is the endpoint's"
assert_contains "$OUT" "sminos takes it at the endpoint's first welcome" "and that sminos takes it at the first welcome"
assert_contains "$OUT" "writes as nu" "and the name this machine writes as meanwhile"
run "$SMINOS" hub show extra
assert_rc 2 "$RC" "hub show takes no word"
assert_contains "$OUT" "usage: sminos hub show" "its usage names show"
run "$SMINOS" hub smns-enroll-v1.eyJzZWNyZXQiOiJ3b3JkIn0
assert_rc 2 "$RC" "a word that is no verb is a usage error"
assert_not_contains "$OUT" "smns-enroll-v1" "that never echoes it"
run "$SMINOS" hub
assert_rc 2 "$RC" "so is no verb"

# ---- a stray hub.json
# The file `hub enroll` once wrote enrolls nothing: the machine keeps the name
# it writes as, is in no hub, and its verbs answer as before any welcome.
echo "a stray hub.json:"
stray_hub_json stray-name
run "$SMINOS" hub show
assert_rc 1 "$RC" "hub show still exits 1"
assert_contains "$OUT" "writes as nu" "the machine writes as its own name, not hub.json's"
for verb in enroll check leave; do
  run "$SMINOS" hub "$verb"
  assert_rc 1 "$RC" "hub $verb still exits 1"
done
assert_equals "$(test -e "$SMINOS_HOME/daemon/hub.json" && echo there || echo none)" there "hub.json is left as it is"
run "$SMINOS" machines
assert_contains "$OUT" "this machine is not enrolled" "machines says the machine is not enrolled"
assert_contains "$OUT" "nu " "and lists it under its own name"
assert_not_contains "$OUT" "stray-name" "never under hub.json's"
PS="$T/n/p"
mkdir -p "$PS"
gitq init -q "$PS"
cd "$PS"
run "$SMINOS" project init --hub
assert_rc 1 "$RC" "project init --hub is refused: there is no hub to name"
assert_contains "$OUT" "mawsd endpoint enroll" "saying where the enrollment is made"
assert_equals "$(test -e "$PS/.smns" && echo there || echo none)" none "and writes no .smns"
"$SMINOS" project init --name strayproj >/dev/null
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["hub"] = {"org": "org-1"}; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$PS/.smns"
run "$SMINOS" project show
assert_not_contains "$OUT" "hub      $HUB" "a hub project of org-1 is not synced through any hub here"
"$SMINOS" say "said beside a stray hub.json" >/dev/null 2>&1
assert_contains "$(cat "$SMINOS_HOME/projects/$(json_get "$PS/.smns" 'd["project"]' | tr -d '"')/log/nu.human.jsonl" 2>/dev/null)" \
  "said beside a stray hub.json" "what is said is written under the machine's own name"
assert_equals "$(test -e "$SMINOS_HOME/daemon/heads.json" && echo marked || echo none)" none \
  "and no enrolment is marked for it (#147)"
cd "$T"

# ---- hub projects
echo "hub projects:"
as a alpha
rl10_cut_over
gitq init -q --bare "$T/archive.git"
gitq init -q --bare "$T/archive-h.git"
PH="$T/a/hp"
mkdir -p "$PH"
gitq init -q "$PH"
cd "$PH"
run "$SMINOS" project init --hub --name hubproj --remote "$T/archive-h.git"
assert_rc 0 "$RC" "project init --hub makes a hub project"
assert_equals "$(json_get "$PH/.smns" 'd["hub"]')" '{"org": "org-1"}' ".smns names the org alone: the URL is each machine's enrollment's"
assert_contains "$OUT" "a hub project of org org-1 (through $HUB here)" "and says so"
run "$SMINOS" project show
assert_contains "$OUT" "hub      $HUB (org org-1)" "project show names the hub"
PG="$T/a/gp"
mkdir -p "$PG"
gitq init -q "$PG"
cd "$PG"
"$SMINOS" project init --name gitproj --remote "$T/archive.git" >/dev/null
"$SMINOS" say "before the hub" >/dev/null
run "$SMINOS" daemon tick
assert_contains "$OUT" "gitproj: synced" "a hub-less project syncs through its remote"
SMNS_BEFORE="$(json_get "$PG/.smns" '{k: v for k, v in d.items() if k != "hub"}')"
run "$SMINOS" project init --hub
assert_rc 0 "$RC" "--hub on an existing .smns adds the field"
assert_equals "$(json_get "$PG/.smns" '{k: v for k, v in d.items() if k != "hub"}')" "$SMNS_BEFORE" "keeping every other field"
assert_equals "$(json_get "$PG/.smns" 'd["hub"]')" '{"org": "org-1"}' "with the org"
assert_contains "$OUT" "no longer synced" "saying its remote is no longer the live path"
run "$SMINOS" project init --hub
assert_rc 0 "$RC" "--hub again changes nothing"
assert_contains "$OUT" "already a hub project" "and says so"
run "$SMINOS" project init --hub --name renamed
assert_rc 2 "$RC" "--hub on an existing .smns changes nothing else"
REMOTE_HEAD="$(git -C "$T/archive.git" rev-parse main)"
"$SMINOS" say "after the hub" >/dev/null
run "$SMINOS" daemon tick
assert_contains "$OUT" "gitproj: reconciled" "the hub project ticks"
assert_not_contains "$OUT" "gitproj: synced" "with no git phase"
assert_not_contains "$OUT" "hubproj: synced" "nor for the project made a hub project at init"
assert_equals "$(git -C "$T/archive.git" rev-parse main)" "$REMOTE_HEAD" "its remote is not pushed"
assert_equals "$(test -d "$SMINOS_HOME/projects/$(json_get "$PH/.smns" 'd["project"]' | tr -d '"')/log/.git" && echo git || echo none)" none \
  "a hub project's log is never made a git working tree, though its .smns names a remote"
run "$SMINOS" project attach
assert_rc 1 "$RC" "project attach refuses a hub project"
assert_contains "$OUT" "syncs through its hub" "saying why"
cd "$T"
mv "$PG" "$PG.moved"
"$SMINOS" say --in gitproj "while its checkout is gone" >/dev/null
run "$SMINOS" daemon tick
assert_not_contains "$OUT" "gitproj: synced" "a hub project whose checkout is gone still gets no git phase"
assert_equals "$(git -C "$T/archive.git" rev-parse main)" "$REMOTE_HEAD" "its remote still not pushed"
cd "$T"
gitq init -q --bare "$T/archive-n.git"
PN="$T/a/np"
mkdir -p "$PN"
gitq init -q "$PN"
cd "$PN"
"$SMINOS" project init --name nullhub --remote "$T/archive-n.git" >/dev/null
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["hub"] = None; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$PN/.smns"
"$SMINOS" say "under a null hub" >/dev/null 2>&1
run "$SMINOS" daemon tick
assert_not_contains "$OUT" "nullhub: synced" "a .smns whose hub is null gets no git phase"
assert_contains "$OUT" "its hub names no org" "with a warning"
assert_equals "$(git -C "$T/archive-n.git" rev-parse --verify -q main || echo none)" none "its remote is never pushed"
run "$SMINOS" project attach
assert_rc 1 "$RC" "project attach refuses it"
run "$SMINOS" project init --hub
assert_rc 1 "$RC" "--hub does not overwrite a malformed hub"
assert_contains "$OUT" "fix its .smns by hand" "saying to fix it by hand"
PO="$T/a/op"
mkdir -p "$PO"
gitq init -q "$PO"
cd "$PO"
"$SMINOS" project init --name orgonly >/dev/null
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["hub"] = {"org": "org-1"}; json.dump(d, open(sys.argv[1], "w"), indent=2)' "$PO/.smns"
"$SMINOS" say "under an org-only hub" >/dev/null 2>&1
importable() { # project dir — whether the uplink would import an events frame for it, for org-1
  python3 - "$SCRIPTS" "$1" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import sminos_uplink
pid = json.load(open(os.path.join(sys.argv[2], ".smns")))["project"]
print("imports" if sminos_uplink.hub_project(pid, {"org": "org-1"}) else "refuses")
PY
}
assert_equals "$(importable "$PO" 2>/dev/null)" imports "the uplink imports into a project whose hub carries only its org"
assert_equals "$(importable "$PH" 2>/dev/null)" imports "and into one made by init --hub"
assert_equals "$(importable "$PN" 2>/dev/null)" refuses "and nothing into one whose hub names no org"
cd "$T"

# ---- the conversion against a tick that syncs the project through git
# A tick read each project when it began; `project init --hub` may land while
# it waits on the remote. The conversion takes the mirror's sync lock, and
# each git phase reads .smns again under that lock, so what is left of the
# tick neither integrates nor pushes, and no git event enters the hub log.
echo "a conversion during a tick's sync:"
cat > "$T/race.py" <<'PY'
import json, os, subprocess, sys, threading
scripts, root, mode = sys.argv[1:4]
sys.path.insert(0, scripts)
import sminos, sminos_daemon as daemon
project = sminos.resolve_project(root)  # as the tick read it: no hub yet
convert = [os.path.join(scripts, "sminos"), "project", "init", "--hub"]
report = {}
if mode == "held":
    # The tick's fetch waits until the conversion has started and had a second
    # to finish; the tick's delivery waits for the conversion to end, so its
    # push comes after the switch.
    entered, gate, proc = threading.Event(), threading.Event(), []
    real_fetch, real_deliver = daemon.fetch, daemon.deliver_owed
    def held_fetch(log):
        entered.set()
        gate.wait(60)
        real_fetch(log)
    def deliver_after(project_, view):
        proc[0].wait(60)
        return real_deliver(project_, view)
    daemon.fetch, daemon.deliver_owed = held_fetch, deliver_after
    out = {}
    t = threading.Thread(target=lambda: out.update(daemon.tick(project)))
    t.start()
    entered.wait(60)
    proc.append(subprocess.Popen(convert, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said during the held fetch"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    try:
        proc[0].wait(1.0)
    except subprocess.TimeoutExpired:
        pass
    report["converted during the fetch"] = proc[0].poll() is not None
    gate.set()
    t.join(120)
    report["tick"] = out
elif mode == "elsewhere":
    # The switch landed in another checkout of the project (sys.argv[4]),
    # which shares its log, between the tick's read of this one and its sync;
    # then a session in this checkout, whose .smns names no hub, wrote.
    import sminos_uplink
    subprocess.run(convert, cwd=sys.argv[4], stdout=subprocess.DEVNULL, check=True)
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said where no hub is named"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    sminos.forget_caches()
    report["uplink feeds it"] = project.id in sminos_uplink.hub_projects({"org": "org-1"})
    sminos.forget_caches()
    report["tick"] = daemon.tick(project)
elif mode == "registering":
    # This checkout, whose .smns names no hub, registers itself over the
    # registration the other checkout (sys.argv[4]) left, and is held just
    # before it writes; meanwhile the other checkout converts and registers.
    import time, sminos_uplink
    other = sys.argv[4]
    sminos.project_path(sminos.resolve_project(other), "log")
    sminos.forget_caches()
    held, release, real_write = threading.Event(), threading.Event(), sminos.write_json
    def held_write(path, data, mode=0o600):
        if path.endswith("project.json") and not held.is_set():
            held.set()
            release.wait(60)
        return real_write(path, data, mode)
    sminos.write_json = held_write
    t = threading.Thread(target=sminos.project_path, args=(project, "log"))
    t.start()
    held.wait(60)
    proc = subprocess.Popen(convert, cwd=other, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 60
    while time.time() < deadline and proc.poll() is None and not sminos.names_hub(other, project.id):
        time.sleep(0.05)
    try:
        proc.wait(2.0)  # as far as it gets while this registration is held
    except subprocess.TimeoutExpired:
        pass
    report["converted while held"] = proc.poll() is not None
    release.set()
    t.join(60)
    report["converted"] = proc.wait(60) == 0
    sminos.write_json = real_write
    sminos.forget_caches()
    report["registered from the hub checkout"] = \
        os.path.realpath(str(sminos.registration(project.id).get("root") or "")) == os.path.realpath(other)
    report["uplink feeds it"] = project.id in sminos_uplink.hub_projects({"org": "org-1"})
    try:
        daemon.ensure_mirrored(project)
        report["git barred"] = False
    except daemon.BecameHub:
        report["git barred"] = True
else:  # "stale": the switch landed between the tick's read and its sync of the project
    subprocess.run(convert, cwd=root, stdout=subprocess.DEVNULL, check=True)
    subprocess.run([os.path.join(scripts, "sminos"), "say", "said after the switch"], cwd=root,
                   stdout=subprocess.DEVNULL, check=True)
    report["tick"] = daemon.tick(project)
print(json.dumps(report))
PY
other_pushes() { # bare-remote text — another machine's git event, pushed to the remote
  rm -rf "$T/other-clone"
  gitq clone -q "$1" "$T/other-clone" 2>/dev/null
  printf '{"ts": "2026-10-15T00:00:00.000Z", "writer": "other/human", "seq": 1, "kind": "say", "from": "human", "to": "*", "text": "%s"}\n' \
    "$2" > "$T/other-clone/other.human.jsonl"
  gitq -C "$T/other-clone" add other.human.jsonl
  gitq -C "$T/other-clone" commit -qm other
  gitq -C "$T/other-clone" push -q origin HEAD:main
}
mirrored_project() { # name → a checkout under $T/a/<name> of a git-mirrored project, synced once
  gitq init -q --bare "$T/$1.git"
  mkdir -p "$T/a/$1"
  gitq init -q "$T/a/$1"
  cd "$T/a/$1"
  "$SMINOS" project init --name "$1" --remote "$T/$1.git" >/dev/null
  "$SMINOS" say "before the switch" >/dev/null
  run "$SMINOS" daemon tick
  assert_contains "$OUT" "$1: synced" "$1 syncs through git before the switch"
  cd "$T"
}
log_of() { echo "$SMINOS_HOME/projects/$(json_get "$T/a/$1/.smns" 'd["project"]' | tr -d '"')/log"; }
as a alpha
mirrored_project heldproj
HELD_HEAD="$(git -C "$T/heldproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/heldproj" held
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["converted during the fetch"])')" \
  False "a conversion started while a tick fetches waits for that sync to end"
assert_equals "$(json_get "$T/a/heldproj/.smns" 'd["hub"]')" '{"org": "org-1"}' "then converts the project"
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; print(json.load(sys.stdin)["tick"]["pushed"])')" \
  False "the rest of the tick, after the switch, pushes nothing"
assert_equals "$(git -C "$T/heldproj.git" rev-parse main)" "$HELD_HEAD" "the remote is where it was"
assert_contains "$(cat "$(log_of heldproj)/alpha.human.jsonl")" "said during the held fetch" \
  "though the log holds what was said meanwhile"
mirrored_project staleproj
STALE_HEAD="$(git -C "$T/staleproj.git" rev-parse main)"
other_pushes "$T/staleproj.git" "a git event after the switch"
OTHER_HEAD="$(git -C "$T/staleproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/staleproj" stale
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys; t = json.load(sys.stdin)["tick"]; print([t["integrated"], t["pushed"]])')" \
  "[False, False]" "a tick that read the project before the switch neither integrates nor pushes it after"
assert_equals "$(test -e "$(log_of staleproj)/other.human.jsonl" && echo there || echo none)" none \
  "no git event enters the hub project's log"
assert_equals "$(git -C "$T/staleproj.git" rev-parse main)" "$OTHER_HEAD" "nothing of this machine is pushed"
[[ "$OTHER_HEAD" != "$STALE_HEAD" ]] || fail "the other machine's push moved the remote"
# Two checkouts of one project share its log: the switch made in one bars git
# for a tick that read the other, whose .smns names no hub, and a session
# writing from that other checkout does not take the project back to git.
mirrored_project twoproj
TWO_B="$T/a/twoproj-b"
mkdir -p "$TWO_B"
gitq init -q "$TWO_B"
cp "$T/a/twoproj/.smns" "$TWO_B/.smns"
other_pushes "$T/twoproj.git" "a git event after the switch in the other checkout"
TWO_HEAD="$(git -C "$T/twoproj.git" rev-parse main)"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/twoproj" elsewhere "$TWO_B"
assert_equals "$(printf '%s' "$OUT" | python3 -c 'import json, sys
out = sys.stdin.read()
try:
    r = json.loads(out.strip().splitlines()[-1])
    print([r["uplink feeds it"], r["tick"]["integrated"], r["tick"]["pushed"]])
except (ValueError, IndexError, KeyError):
    print(out)')" \
  "[True, False, False]" "a switch in another checkout: the uplink feeds the project, and a tick that read this one neither integrates nor pushes it"
assert_equals "$(test -e "$(log_of twoproj)/other.human.jsonl" && echo there || echo none)" none \
  "no git event enters the log both checkouts share"
assert_equals "$(git -C "$T/twoproj.git" rev-parse main)" "$TWO_HEAD" "nothing of this machine is pushed"
assert_equals "$(python3 -c 'import json, os, sys; print(os.path.realpath(json.load(open(sys.argv[1]))["root"]) == os.path.realpath(sys.argv[2]))' \
  "$(log_of twoproj)/../project.json" "$TWO_B")" True "the project stays registered from the checkout that names the hub"
# A checkout registering without a hub, held just before it writes, while
# another checkout of the project converts: the conversion registers after it.
# The other checkout is at an older head that named the project otherwise, so
# its registration is not this checkout's project as it is now, and this one
# writes over it (an identical one it would keep: project_path's kept_root).
mirrored_project regproj
REG_B="$T/a/regproj-b"
mkdir -p "$REG_B"
gitq init -q "$REG_B"
python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); d["name"] = "regproj-then"; json.dump(d, open(sys.argv[2], "w"))' \
  "$T/a/regproj/.smns" "$REG_B/.smns"
run python3 "$T/race.py" "$SCRIPTS" "$T/a/regproj" registering "$REG_B"
reg_report() { printf '%s' "$OUT" | python3 -c 'import json, sys
out = sys.stdin.read()
try:
    print(json.loads(out.strip().splitlines()[-1])[sys.argv[1]])
except (ValueError, IndexError, KeyError):
    print(out)' "$1"; }
assert_equals "$(reg_report "converted while held")" False \
  "a conversion in another checkout waits for a registration in flight"
assert_equals "$(reg_report converted)" True "then converts the project"
assert_equals "$(reg_report "registered from the hub checkout")" True \
  "the project ends registered from the checkout that names the hub"
assert_equals "$(reg_report "uplink feeds it")" True "the uplink feeds the project"
assert_equals "$(reg_report "git barred")" True "git no longer syncs it from the checkout that names no hub"
cd "$T"
as b2 beta2
P0="$T/b2/p"
mkdir -p "$P0"
gitq init -q "$P0"
cd "$P0"
run "$SMINOS" project init --hub
assert_rc 1 "$RC" "project init --hub on a machine not enrolled is refused"
assert_contains "$OUT" "mawsd endpoint enroll" "saying where the enrollment is made"
assert_equals "$(test -e "$P0/.smns" && echo there || echo none)" none "and writes no .smns"
cd "$T"
# ---- a machine cut over to its endpoint (O12 M5)
# Writing as omega before any welcome, beside a stray hub.json, the machine is
# cut over by its endpoint's welcome (endpoint_standin.py, as `daemon run`'s
# probe meets it), which names it sigma: identity.json holds the identity,
# omega's sessions stay this machine's, and the enrollment is the endpoint's —
# hub show prints it, enroll, check and leave exit 1 naming the identity's
# file, and hub.json stays, its key the endpoint's to ask for.
echo "a machine cut over to its endpoint:"
as cut omega
stray_hub_json stray-name
PC="$T/cut/proj"
mkdir -p "$PC"
gitq init -q "$PC"
cd "$PC"
"$SMINOS" project init --name cproj >/dev/null
S5=5c000005-0000-4000-8000-0000000000c5
printf '{"pid":%s,"sessionId":"%s","name":"cterm","nameSource":"derived","kind":"interactive","status":"idle","cwd":"%s"}\n' \
  "$$" "$S5" "$PC" > "$HOME/.claude/sessions/cterm.json"
machines() { printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["machine"], r["local"]) for r in json.load(sys.stdin)))'; }
run "$SMINOS" list --json
assert_equals "$(machines)" "[('cterm', 'omega', True)]" "a session joins as omega, the name this machine writes as"
export MAWS_USER_DATA="$T/cut/maws"
EPC="$MAWS_USER_DATA/mawsd/endpoint"
python3 "$SCRIPT_DIR/endpoint_standin.py" serve "$EPC" "{\"identity\": {\"org\": \"org-1\", \"hub\": \"$HUB\", \"name\": \"sigma\", \"former\": [\"omega\"], \"ref\": \"ref-sigma\", \"enrolled\": \"2026-10-27T00:00:00.000Z\"}}" &
PIDS+=("$!")
until_true 100 test -S "$EPC/ctl.sock"
CRED_BEFORE="$(cat "$SMINOS_HOME/daemon/hub.json")"
run "$SMINOS" daemon probe
assert_rc 0 "$RC" "the endpoint's whole welcome cuts the machine over"
IDENT="$SMINOS_HOME/daemon/identity.json"
assert_equals "$(mode_of "$IDENT")" 0o600 "identity.json is mode 600"
assert_equals "$(json_get "$IDENT" '[d["name"], d["org"], d["ref"], d["former"]]')" "[\"sigma\", \"org-1\", \"ref-sigma\", {\"omega\": [\"$S5\"]}]" \
  "it holds the endpoint's name, and omega with the session held under it"
run "$SMINOS" list --json
assert_equals "$(machines)" "[('cterm', 'sigma', True)]" "the session is this machine's, on sigma"
run "$SMINOS" hub show
assert_rc 0 "$RC" "hub show reads the identity"
assert_contains "$OUT" "machine  sigma" "printing the endpoint's name"
assert_contains "$OUT" "hub      $HUB (org org-1)" "its hub and org"
assert_contains "$OUT" "former   omega (1 sessions)" "the former name"
assert_contains "$OUT" "cut over " "marked cut over"
assert_contains "$OUT" "$IDENT holds it, and removing it undoes the cutover" "naming the file that undoes it"
for verb in enroll check leave; do
  run "$SMINOS" hub "$verb"
  assert_rc 1 "$RC" "hub $verb exits 1 on a cut-over machine"
  assert_contains "$OUT" "$POINTER (it cut over to RL10 on " "saying the enrollment is the endpoint's, since the cutover"
  assert_contains "$OUT" "its identity is $IDENT" "naming the identity's file"
done
assert_equals "$(cat "$SMINOS_HOME/daemon/hub.json")" "$CRED_BEFORE" "hub.json stays as it was"
run "$SMINOS" say "said as sigma"
assert_contains "$(cat "$SMINOS_HOME/projects/$(json_get "$PC/.smns" 'd["project"]' | tr -d '"')/log/sigma.human.jsonl")" \
  "said as sigma" "new events are written under sigma"
PC2="$T/cut/proj2"
mkdir -p "$PC2"
gitq init -q "$PC2"
cd "$PC2"
run "$SMINOS" project init --hub --name cproj2
assert_rc 0 "$RC" "project init --hub takes the hub from the identity"
assert_equals "$(json_get "$PC2/.smns" 'd["hub"]')" '{"org": "org-1"}' "the org"
unset MAWS_USER_DATA
cd "$T"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "all $PASSES hub assertions passed"
else
  echo "$FAILURES of $((PASSES + FAILURES)) hub assertions FAILED"
  exit 1
fi
