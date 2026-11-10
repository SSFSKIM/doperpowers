#!/usr/bin/env bash
#
# A repository is a project by its remote (docs/doperpowers/specs/
# 2026-10-19-smns-remote-identity-design.md §1–§4, §9): on an enrolled
# machine (one cut over to its endpoint, daemon/identity.json) a repository
# no .smns claims resolves to the hub project its
# remote derives — the same id from the MacBook's scp-like spelling and the
# mini's https one, in a linked worktree and a second clone too — while a
# .smns still wins, and no remote, a local path, or several remotes none named
# origin leave it a stray with `project show` saying why; a machine not
# enrolled still reads local-<repo>. Two clones on one machine keep the
# registered root and are both offered as checkouts; a `set-url` under a live
# session moves it within a tick and is said once; `init --hub` pins the id
# the repository has, moving nothing; a stray in such a repository moves once
# when the repository gains its remote, and once when its machine cuts over;
# the record hook keeps a <message> for the derived project, alpha's hello
# names it by the remote's basename, the other machine follows it, and
# `@<repo>/<alias>` arrives. Machines simulated on one Mac, each its own
# SMINOS_HOME: alpha cut over, gamma not enrolled; then the cases that span
# machines, on RL10: delta cutting over with a session in such a repository,
# and alpha and beta each cut over to its own endpoint_standin.py, what one
# endpoint took reaching the other as arrivals (rl10-machines.sh's hand-off).
# Hermetic: HOME and SMINOS_HOME are temporary, one pair per machine; `claude`
# is a stub; nothing reaches a network beyond 127.0.0.1 (no remote is ever
# fetched: ssh is a stand-in that records being called).
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"
HOOK="${SMINOS_HOOK:-$PLUGIN_ROOT/hooks/smns-record.sh}"

FAILURES=0
PASSES=0
# Physical: a verb reads its directory as the process's cwd, symlinks resolved (/tmp on macOS).
T="$(cd "$(mktemp -d /tmp/smr.XXXXXX)" && pwd -P)"
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
repo() { # dir [remote-name url]... — a repository with one commit and the remotes named
  local d=$1; shift
  gitq init -q "$d"
  gitq -C "$d" commit -q --allow-empty -m base
  while [ $# -ge 2 ]; do gitq -C "$d" remote add "$1" "$2"; shift 2; done
}

unset CLAUDE_CODE_SESSION_ID SMNS_INTERNAL SMNS_MEMBER DAEMON_HOME AGORA_HOME DAEMON_HOST CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR
export SMINOS_DERIVE_EVERY=0 DAEMON_BOOT_ID=boot-current SCRIPTS
mkdir -p "$T/bin" "$T/x"
as() { # a|b|c|d host — one machine: its HOME, its SMINOS_HOME, its host name
  export HOME="$T/$1/home" SMINOS_HOME="$T/$1/s" STUB_STATE="$T/$1/stub" DAEMON_HOST="$2"
  mkdir -p "$HOME/.claude/sessions" "$STUB_STATE"
}
# shellcheck source=rl10-machines.sh
. "$SCRIPT_DIR/rl10-machines.sh"

cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
case "${1:-}" in
  agents) cat "$STUB_STATE/agents.json" 2>/dev/null || echo "[]"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
# ssh, as git would call it for a remote: nothing here may reach one.
cat > "$T/bin/fake-ssh" <<SSH
#!/bin/sh
: > "$T/ssh-entered"
exit 1
SSH
chmod +x "$T/bin/fake-ssh"
export PATH="$T/bin:$PATH" GIT_SSH_COMMAND="$T/bin/fake-ssh" GIT_SSH_VARIANT=simple

mp_of() { python3 -c 'import sys, uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:org-1:" + sys.argv[1].lower()))' "$1"; }
rp_of() { python3 -c 'import sys, uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, "smns-repo:org-1:" + sys.argv[1]))' "$1"; }
smns_field() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1/.smns" "$2"; }
write_smns() { # dir name — a .smns naming only the org
  python3 -c 'import json, sys, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": sys.argv[1], "remote": "", "hub": {"org": "org-1"}}, indent=2))' \
    "$2" > "$1/.smns"
}
show_field() { printf '%s\n' "$OUT" | sed -n "s/^$1 *//p"; }   # a line of `project show`'s output, its label dropped
registered_root() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["root"])' "$SMINOS_HOME/projects/$1/project.json"; }
# A running session: its engine record (a `sleep`, or with an inbox — inbox_standin.py,
# whose frames land in $T/<name>.received — the session's process) and a transcript
# launched in its directory.
live_session() { # name session dir [inbox]
  local pid
  if [ -n "${4:-}" ]; then
    : > "$T/$1.received"
    python3 "$SCRIPT_DIR/inbox_standin.py" "$T/$1.sock" "$T/$1.received" & pid=$!
    until_true test -S "$T/$1.sock"
  else
    sleep 600 & pid=$!
  fi
  PIDS+=("$pid")
  printf '{"pid":%s,"sessionId":"%s","name":"%s","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"%s}\n' \
    "$pid" "$2" "$1" "$3" "${4:+,\"messagingSocketPath\":\"$T/$1.sock\"}" > "$HOME/.claude/sessions/$1.json"
  TX="$HOME/.claude/projects/p-$2/$2.jsonl"
  mkdir -p "$(dirname "$TX")"
  printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","origin":{"kind":"human"},"message":{"role":"user","content":"go"}}\n' \
    "${2:0:8}" "$2" "$3" > "$TX"
}
# A project's log as `kind reason project by cwd` lines, for one session.
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
tick() { "$SMINOS" daemon tick >/dev/null 2>&1 || true; }
start_daemon() { "$SMINOS" daemon run --interval 1 >> "$SMINOS_HOME/run.out" 2>&1 & PIDS+=("$!"); }
hook_payload() { # event session cwd transcript
  printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","hook_event_name":"%s","source":"startup"}' "$2" "$4" "$3" "$1"
}

WKEY=github.com/acme/widget
WPID="$(rp_of "$WKEY")"

# ---- alpha: a repository by its remote
echo "alpha: a repository by its remote:"
as a alpha
rl10_cut_over
AMP="$(mp_of alpha)"
W="$T/a/widget"
repo "$W" origin git@github.com:Acme/Widget.git
run_in "$W" "$SMINOS" project show
assert_equals "$(show_field id)" "$WPID" "a clone with no .smns is the project its remote derives: uuid5 of the org and the remote key"
assert_equals "$(show_field project)" "Widget" "named by the remote's last path segment, as written"
assert_equals "$(show_field kind)" "hub" "a hub project"
assert_equals "$(show_field source)" "remote origin → $WKEY" "project show names its source: the remote and its key"
assert_equals "$(show_field hub)" "http://127.0.0.1:9 (org org-1)" "synced through the enrollment's hub"
assert_equals "$(show_field root)" "$W" "rooted at the clone"
mkdir -p "$W/src/deep"
run_in "$W/src/deep" "$SMINOS" project show
assert_equals "$(show_field id)" "$WPID" "a directory inside it too"
gitq -C "$W" worktree add -q -b feat "$T/a/widget-feat"
run_in "$T/a/widget-feat" "$SMINOS" project show
assert_equals "$(show_field id)" "$WPID" "a linked worktree reads its main checkout's remote"
assert_equals "$(show_field root)" "$W" "and its root is the main checkout"
# The one change design §8 (the project registry) makes with no stored
# statement: a worktree outside its repository takes a .smns above the main
# checkout, as the checkout does.
TOP="$T/a/top"
mkdir -p "$TOP"
write_smns "$TOP" topped
repo "$TOP/inner" origin https://github.com/acme/inner.git
gitq -C "$TOP/inner" worktree add -q -b feat "$T/a/inner-feat"
run_in "$TOP/inner" "$SMINOS" project show
assert_equals "$(show_field id)" "$(smns_field "$TOP" project)" "a .smns above a clone with a remote is its project"
run_in "$T/a/inner-feat" "$SMINOS" project show
assert_equals "$(show_field id)" "$(smns_field "$TOP" project)" \
  "a worktree outside its repository takes the .smns above its main checkout"
assert_equals "$(show_field source)" ".smns at $TOP" "and project show names that file's folder"
U="$T/a/solo"
repo "$U" upstream https://github.com/acme/solo.git
run_in "$U" "$SMINOS" project show
assert_equals "$(show_field source)" "remote upstream → github.com/acme/solo" "a sole remote not named origin is the one"
BM="$T/a/bommed"
repo "$BM" origin https://github.com/acme/bommed.git
printf '\xef\xbb\xbf' | cat - "$BM/.git/config" > "$T/bommed.config" && mv "$T/bommed.config" "$BM/.git/config"
run_in "$BM" "$SMINOS" project show
assert_equals "$(show_field id)" "$(rp_of github.com/acme/bommed)" "a git config that opens with a UTF-8 BOM derives its remote, as git reads it"

echo "alpha: what derives nothing, and what wins:"
N="$T/a/noremote"
repo "$N"
run_in "$N" "$SMINOS" project show
assert_equals "$(show_field id)" "$AMP" "a repository with no remote is a stray in the machine project"
assert_contains "$(show_field source)" "machine project: the repository has no remote" "show says why"
P="$T/a/pathremote"
repo "$P" origin /srv/x.git
run_in "$P" "$SMINOS" project show
assert_equals "$(show_field id)" "$AMP" "a remote that is a local path derives nothing"
assert_contains "$(show_field source)" 'remote `origin` is a local path' "show says why"
M="$T/a/tworemotes"
repo "$M" a git@github.com:acme/a.git b git@github.com:acme/b.git
run_in "$M" "$SMINOS" project show
assert_equals "$(show_field id)" "$AMP" "two remotes, none named origin, derive nothing"
assert_equals "$(show_field source)" 'machine project: remotes `a`, `b`, none named origin — name one origin, or `sminos project init --hub`' \
  "show says why, and how to name one"
S="$T/a/declared"
repo "$S" origin git@github.com:acme/declared.git
write_smns "$S" declared
run_in "$S" "$SMINOS" project show
assert_equals "$(show_field id)" "$(smns_field "$S" project)" "a .smns wins over the remote"
assert_equals "$(show_field source)" ".smns at $S" "show names the file"
run_in "$T/x" "$SMINOS" project show
assert_equals "$(show_field source)" "machine project: no git repository" "a directory in no repository is a stray, as before"

# ---- two clones on one machine
echo "alpha: two clones of one repository:"
W2="$T/a/widget-2"
repo "$W2" origin https://github.com/acme/widget
WA=5a000001-0000-4000-8000-0000000000a1
WA2=5a000002-0000-4000-8000-0000000000a2
live_session wa "$WA" "$W" inbox
WA_TX=$TX
live_session wa2 "$WA2" "$W2"
run_in "$W" "$SMINOS" list
run_in "$W2" "$SMINOS" list --json
assert_equals "$(printf '%s\n' "$OUT" | python3 -c 'import json, sys
print(sorted((r["alias"], r["project"], r["project_kind"]) for r in json.load(sys.stdin)))')" \
  "[('wa', 'Widget', 'hub'), ('wa2', 'Widget', 'hub')]" "a second clone, its remote spelled another way, is the same project"
assert_equals "$(registered_root "$WPID")" "$W" "the registered root stands: the second clone does not take it over"
tick
assert_equals "$(registered_root "$WPID")" "$W" "nor does a tick"
assert_equals "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["key"])' "$SMINOS_HOME/projects/$WPID/remote.json")" \
  "$WKEY" "the project's home records the key its id derives from"
assert_equals "$(cd "$W" && python3 -c 'import os, sys
sys.path.insert(0, os.environ["SCRIPTS"])
import sminos, sminos_policy as policy
print(sorted(c["path"] for c in policy.known_checkouts(sminos.resolve_project("."))))')" "['$W', '$W2']" \
  "both clones are offered as checkouts"
GUIDE="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","source":"startup"}' "$WA" "$W" "$WA_TX" \
  | "$SMINOS" guide)"
assert_contains "$GUIDE" "in project Widget on machine alpha: the project of your repository's remote, $WKEY" \
  "the session-start guidance says where the project comes from"

# ---- a remote that changes under a live session
echo "alpha: a remote that changes:"
G="$T/a/gadget"
repo "$G" origin git@github.com:acme/gadget.git
GPID="$(rp_of github.com/acme/gadget)"
ZPID="$(rp_of github.com/acme/gizmo)"
GA=5a000003-0000-4000-8000-0000000000a3
live_session ga "$GA" "$G"
run_in "$G" "$SMINOS" list
assert_equals "$(events_of "$GPID" "$GA")" "joined - - - $G" "a session in the repository joins its derived project"
gitq -C "$G" remote set-url origin git@github.com:acme/gizmo.git
SAID=""
for verb in "list" "project show" "chat"; do
  # shellcheck disable=SC2086
  run_in "$G" "$SMINOS" $verb
  SAID+="$OUT"$'\n'
done
assert_equals "$(grep -c "the remote of $G is now github.com/acme/gizmo, not github.com/acme/gadget" <<<"$SAID")" 1 \
  "the remote changing under a registered root is said exactly once across three verbs"
assert_contains "$SAID" "project gadget ($GPID): the remote of $G is now github.com/acme/gizmo, not github.com/acme/gadget, so its sessions there move to project gizmo ($ZPID); a .smns pins a project against its remote: \`sminos project init --hub\`" \
  "naming the old project, the new one and the pin"
assert_equals "$(grep -c "the remote of $G is now" "$SMINOS_HOME/daemon.log")" 1 "and in daemon.log once"
tick
assert_equals "$(events_of "$GPID" "$GA")" "joined - - - $G
retired moved $ZPID - -" "the session is retired in the old project, reason moved, naming the new one"
assert_equals "$(events_of "$ZPID" "$GA")" "joined - - move $G" "and joined in the new one, by move"
tick
assert_equals "$(events_of "$ZPID" "$GA" | wc -l | tr -d ' ')" 1 "a later tick writes nothing more"
run_in "$G" "$SMINOS" list
assert_not_contains "$OUT" "the remote of" "and the line is not said again"

# ---- init --hub pins the id the repository has
echo "alpha: init --hub pins what the remote gave:"
PN="$T/a/pinme"
repo "$PN" origin git@github.com:acme/PinMe.git
PPID_="$(rp_of github.com/acme/pinme)"
PA=5a000004-0000-4000-8000-0000000000a4
live_session pa "$PA" "$PN"
run_in "$PN" "$SMINOS" list
run_in "$PN" "$SMINOS" project init --hub
assert_contains "$OUT" "pinning the id its remote github.com/acme/pinme gave it" "init --hub says it pins the derived id"
assert_equals "$(smns_field "$PN" project) $(smns_field "$PN" name)" "$PPID_ PinMe" "the .smns holds the derived id and name"
run_in "$PN" "$SMINOS" project show
assert_equals "$(show_field source) $(show_field id)" ".smns at $PN $PPID_" "the file now declares the same project"
tick
assert_equals "$(events_of "$PPID_" "$PA")" "joined - - - $PN" "and no session moved"
run_in "$N" "$SMINOS" project init --hub
assert_equals "$(smns_field "$N" project | grep -cE '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-')" 1 \
  "in a repository that derives nothing, init --hub still writes a fresh id"

# ---- the roll's shape: a stray whose repository now derives a project
echo "alpha: a stray in a repository that gains its remote:"
L="$T/a/later"
repo "$L"
LPID="$(rp_of github.com/acme/later)"
LA=5a000005-0000-4000-8000-0000000000a5
live_session la "$LA" "$L"
tick
assert_equals "$(events_of "$AMP" "$LA")" "joined - - - $L" "a session in a repository with no remote is a stray"
gitq -C "$L" remote add origin git@github.com:acme/later.git
tick
assert_equals "$(events_of "$AMP" "$LA")" "joined - - - $L
retired moved $LPID - -" "the first tick after the repository derives a project moves it once"
assert_equals "$(events_of "$LPID" "$LA")" "joined - - move $L" "into the derived project"
tick
assert_equals "$(events_of "$AMP" "$LA" | grep -c moved)" 1 "and only once"

# ---- machines not enrolled
echo "a machine not enrolled:"
as c gamma
WC="$T/c/widget"
repo "$WC" origin git@github.com:acme/widget.git
run_in "$WC" "$SMINOS" project show
assert_equals "$(show_field id)" "local-widget" "a machine not enrolled still reads local-<repo>"
assert_equals "$(show_field source)" "the repository at $WC, a local project: this machine is not enrolled" "and says so"

# ---- RL10: the repository's project across machines cut over to their endpoints (#153 M3d)
# The cases that span machines: a machine that cuts over (its endpoint's
# welcome, `daemon probe`) with a session in such a repository, and alpha's
# record hook, its endpoint and beta, each a real sminos home with its daemon
# and its endpoint_standin.py, never enrolled at a hub. What one endpoint accepted reaches the other's connection as
# arrivals through the stand-in's own echo (rl10_relay). The org's directory
# names the project as alpha's hello named it, the registration the hub
# makes of a hello.
echo "RL10: a machine that cuts over with a session in such a repository:"
rl10_as rd delta
WRD="$T/rd/widget"
repo "$WRD" origin https://github.com/acme/widget.git
RDA=6d000001-0000-4000-8000-0000000000d1
live_session rda "$RDA" "$WRD"
run_in "$WRD" "$SMINOS" list
assert_equals "$(events_of local-widget "$RDA")" "joined - - - $WRD" "RL10: before it cuts over, the session is in local-widget"
rl10_serve
run_in "$WRD" "$SMINOS" daemon probe
assert_contains "$OUT" "welcomed as delta of org org-1: this machine is cut over" "RL10: the endpoint's welcome cuts delta over"
tick
assert_equals "$(events_of local-widget "$RDA")" "joined - - - $WRD
retired moved $WPID - -" "RL10: the first tick after the cutover writes exactly one moved"
assert_equals "$(events_of "$WPID" "$RDA")" "joined - - move $WRD" "RL10: into the repository's derived project"
tick
assert_equals "$(events_of local-widget "$RDA" | grep -c moved)" 1 "RL10: and only once"

echo "RL10: alpha's record hook, its endpoint, and beta:"
rl10_as ra alpha
rl10_cut_over
EPA=$EP
WRA="$T/ra/widget"
repo "$WRA" origin git@github.com:Acme/Widget.git
run_in "$WRA" "$SMINOS" project show
assert_equals "$(show_field id) $(show_field kind)" "$WPID hub" "RL10: on a machine cut over, the clone is the hub project its remote derives"
RWA=6a000001-0000-4000-8000-0000000000a1
live_session rwa "$RWA" "$WRA" inbox
RWA_TX=$TX
hook_payload SessionStart "$RWA" "$WRA" "$RWA_TX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
printf '%s\n' '{"type":"assistant","uuid":"ra000002","isSidechain":false,"message":{"role":"assistant","content":[{"type":"text","text":"<message>widget is built on RL10</message>"}]}}' >> "$RWA_TX"
hook_payload Stop "$RWA" "$WRA" "$RWA_TX" | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK"
assert_contains "$(cat "$SMINOS_HOME/projects/$WPID/host/"*.jsonl 2>/dev/null)" "widget is built on RL10" \
  "RL10: the record hook keeps a <message> from the clone in the derived project's host store"
assert_not_contains "$(cat "$SMINOS_HOME/projects/$WPID/log/"*.jsonl 2>/dev/null)" "widget is built on RL10" \
  "RL10: not in its log"
rl10_serve
start_daemon
r_hello_of() { # ep-dir pid → the name and follow of the live connection's last hello of the project, or none
  python3 "$SCRIPT_DIR/endpoint_standin.py" ctl "$1" opened \
    | python3 -c 'import json, sys; o = json.load(sys.stdin)["projects"].get(sys.argv[1]); print("%s %s" % (o["name"], o["follow"]) if o else "none")' "$2"
}
r_hello_is() { [ "$(r_hello_of "$1" "$2")" = "$3" ]; }
until_true r_hello_is "$EPA" "$WPID" "Widget False" || true
assert_equals "$(r_hello_of "$EPA" "$WPID")" "Widget False" \
  "RL10: alpha's uplink opens the project at its endpoint under the remote's basename, holding it"
r_host_up() {
  [ "$(rl10_q "$EPA" "any('widget is built on RL10' in repr(f['message'].get('body')) for c, f in F if f.get('t') == 'session'
                      and f['message'].get('kind') == 'host' and f['message'].get('project') == '$WPID')")" = true ]
}
until_true r_host_up || true
r_host_up && pass "RL10: and the <message> goes up as a host message of the project" \
  || fail "RL10: and the <message> goes up as a host message of the project"
r_wa_up() { [ "$(rl10_q "$EPA" "any(e['kind'] == 'joined' and e.get('session') == '$RWA' for c, e in up('$WPID'))")" = true ]; }
until_true r_wa_up || true
r_wa_up && pass "RL10: alpha's endpoint takes rwa's joined in it" || fail "RL10: alpha's endpoint takes rwa's joined in it"
# The org's directory, as the hub registers what alpha's hello named.
RDIR="$(python3 - "$WPID" "$(r_hello_of "$EPA" "$WPID" | cut -d' ' -f1)" <<'PY'
import json, sys
print(json.dumps({"projects": [{"id": sys.argv[1], "name": sys.argv[2], "kind": "hub", "retired": False}],
                  "machines": [{"name": "alpha", "online": True}, {"name": "beta", "online": True}]}))
PY
)"
rl10_directory "$RDIR" "$EPA"
rl10_as rb beta
rl10_cut_over
EPB=$EP
WRB="$T/rb/widget"
repo "$WRB" origin https://github.com/ACME/widget/
run_in "$WRB" "$SMINOS" project show
assert_equals "$(show_field id)" "$WPID" "RL10: beta's clone, spelled another way, is the same project"
mkdir -p "$T/rb/bare"
rl10_serve "\"org\": $RDIR"
start_daemon
until_true r_hello_is "$EPB" "$WPID" "Widget True" || true
assert_equals "$(r_hello_of "$EPB" "$WPID")" "Widget True" "RL10: beta opens it at its endpoint to follow, holding no session there"
relayed() { rl10_relay "$EPA" "$EPB"; "$@"; }
r_wa_known() { (cd "$T/rb/bare" && "$SMINOS" list Widget --json 2>/dev/null) | grep -q "\"session\": \"$RWA\""; }
until_true relayed r_wa_known || true
r_wa_known && pass "RL10: beta reads rwa there, from alpha's endpoint" || fail "RL10: beta reads rwa there, from alpha's endpoint"
run_in "$T/rb/bare" "$SMINOS" say "@Widget/rwa hello from beta on RL10"
assert_equals "$RC" 0 "RL10: @Widget/rwa from beta is accepted"
r_say_up() { [ -n "$(rl10_up "$EPB" "$WPID" "hello from beta on RL10")" ]; }
until_true r_say_up || true
assert_equals "$(rl10_up "$EPB" "$WPID" "hello from beta on RL10" | python3 -c 'import json, sys; e = json.load(sys.stdin); print(e["writer"], e["to"][0]["session"])' 2>&1)" \
  "beta/human $RWA" "RL10: beta's endpoint takes it in the project, from beta's operator to rwa"
rl10_as ra alpha
r_arrived() { grep -Fq "hello from beta on RL10" "$T/rwa.received" 2>/dev/null; }
until_true relayed r_arrived || true
r_arrived && pass "RL10: and it arrives in alpha's session" || fail "RL10: and it arrives in alpha's session"
assert_equals "$(rl10_q "$EPA" "[f['event']['writer'] for c, f in F if f.get('t') == 'words?' and f.get('event', {}).get('text') == '@Widget/rwa hello from beta on RL10']")" \
  '["beta/human"]' "RL10: on alpha's endpoint's words verdict, a person's words being the endpoint's to admit"
rl10_as rb beta
run_in "$WRB" "$SMINOS" project show
assert_equals "$(show_field project)" "Widget" "RL10: beta's clone goes by the name the directory keeps, not its own spelling's"
[ ! -e "$T/ssh-entered" ] && pass "RL10: no remote was ever reached" || fail "RL10: no remote was ever reached"
for m in ra rb; do
  assert_not_contains "$(cat "$T/$m/s/daemon.log" 2>/dev/null)" "Traceback" "RL10: nothing in $m's daemon.log is a traceback"
done
unset MAWS_USER_DATA

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "test-remote: all $PASSES assertions passed"
else
  echo "test-remote: $FAILURES of $((PASSES + FAILURES)) assertions FAILED"
  for f in "$T"/a/s/daemon.log "$T"/ra/s/daemon.log "$T"/rb/s/daemon.log "$T"/ra/s/run.out "$T"/rb/s/run.out; do
    [ -f "$f" ] && { echo "--- $f"; tail -30 "$f"; }
  done
  exit 1
fi
