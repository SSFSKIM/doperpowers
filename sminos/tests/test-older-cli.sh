#!/usr/bin/env bash
# shellcheck source=sminos/tests/devcloud-isolation.sh
. "$(dirname "${BASH_SOURCE[0]}")/devcloud-isolation.sh"   # first: no test reaches a real devcloud (T1's M5)
#
# An older sminos beside this one, on one machine (T1's M6; the composite's
# D7): this code makes a session its human opened a thread, stops it and
# holds a message for it; an older CLI then runs every verb that reads the
# store, against the same store and the same stub engine. It resumes no
# session its human opened, and the `ended` it writes for the stopped thread
# changes nothing for this code.
#
#   test-older-cli.sh [<path to an older sminos launcher>]
#
# With a path, that launcher is the older CLI (a copy in a plugin cache).
# Without one, the older CLI is sminos 1.27.10, the oldest still in a plugin
# cache on the owner's machines: revision aefb80aa of this repository,
# extracted by `git archive`, and fetched from `origin` by its id when the
# clone lacks it (the gates check out one commit). When it cannot be had the
# script fails: it never passes on a line saying it was skipped.
#
# What 1.27.10 does is asserted as it is, so that a change is seen: its first
# reading verb reconciles the session, which has no process and no seat, to
# an unstamped `ended`; a tag and `send` naming it are refused as ended, and
# `resume` and `fill` find no seat; nothing starts the engine; its tick
# reports what is owed from another machine as `recorded` and settles
# nothing, since a closed session is no member to its delivery. The
# settlement by a stale deliverer that D7 accepts needs a member snapshot
# taken before the session exits, which this fixture does not make.
# Hermetic: HOME and SMINOS_HOME are temporary; `claude` is a stub that logs
# every call; the machine is not enrolled.
# run-sminos-tests.sh runs this file beside its own cases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
SCRIPTS="${SMINOS_SCRIPTS:-$PLUGIN_ROOT/skills/sminos/scripts}"
SMINOS="$SCRIPTS/sminos"
OLDER_REV=aefb80aa55bb8d95c47341ca21051ba244e103dd   # sminos 1.27.10

FAILURES=0
PASSES=0
T="$(mktemp -d /tmp/smo.XXXXXX)"
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
    fail "$3"; echo "    expected to find: $2"; echo "    in: ${1:0:900}"; fi
}
assert_not_contains() {
  if grep -Fq -- "$2" <<<"$1"; then
    fail "$3"; echo "    expected NOT to find: $2"; echo "    in: ${1:0:900}"
  else pass "$3"; fi
}
run() { # command... — OUT (stdout and stderr) and RC of the command, run in the repository
  set +e; OUT="$(cd "$REPO" && "$@" 2>&1)"; RC=$?; set -e
}

# ---- the older CLI ----------------------------------------------------------
if [ $# -ge 1 ]; then
  OLDER="$1"
  [ -x "$OLDER" ] || { echo "FAIL the older sminos launcher $OLDER is not an executable file"; exit 1; }
else
  TOP="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
  if ! git -C "$TOP" cat-file -e "$OLDER_REV^{commit}" 2>/dev/null \
      && ! git -C "$TOP" fetch -q --depth=1 origin "$OLDER_REV"; then
    echo "FAIL sminos 1.27.10 (revision ${OLDER_REV:0:8}) cannot be had from this clone or from origin"
    exit 1
  fi
  mkdir -p "$T/older"
  git -C "$TOP" archive "$OLDER_REV" sminos | tar -x -C "$T/older"
  OLDER="$T/older/sminos/skills/sminos/scripts/sminos"
  version="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' \
    "$T/older/sminos/.claude-plugin/plugin.json")"
  [ "$version" = 1.27.10 ] || { echo "FAIL revision ${OLDER_REV:0:8} is sminos $version, not 1.27.10"; exit 1; }
fi
echo "older sminos: $OLDER"

# ---- one machine, one store, one stub engine --------------------------------
unset CLAUDE_CODE_SESSION_ID CLAUDE_PID SMNS_INTERNAL SMNS_MEMBER DAEMON_HOME AGORA_HOME CLAUDE_PLUGIN_ROOT CLAUDE_PROJECT_DIR
export HOME="$T/home" SMINOS_HOME="$T/s" STUB_STATE="$T/stub" DAEMON_HOST=alpha DAEMON_BOOT_ID=boot-current \
  SMINOS_DERIVE_EVERY=0
mkdir -p "$HOME/.claude/sessions" "$SMINOS_HOME" "$STUB_STATE" "$T/bin"
cat > "$T/bin/claude" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$STUB_STATE/calls"
case "${1:-}" in
  agents) echo "[]"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$T/bin/claude"
export PATH="$T/bin:$PATH"

REPO="$T/repo"
git -c init.defaultBranch=main init -q "$REPO"
python3 -c 'import json, uuid
print(json.dumps({"project": str(uuid.uuid4()), "name": "olderproj", "remote": "", "hub": {"org": "org-1"}}))' \
  > "$REPO/.smns"
PROJECT="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["project"])' "$REPO/.smns")"
SID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
TX="$HOME/.claude/projects/p-$SID/$SID.jsonl"
mkdir -p "$(dirname "$TX")"
printf '{"type":"user","uuid":"%s-u1","isSidechain":false,"sessionId":"%s","cwd":"%s","origin":{"kind":"human"},"message":{"role":"user","content":"go"}}\n' \
  "${SID:0:8}" "$SID" "$REPO" > "$TX"
opened() { # the session run by a process of its human's terminal (a `sleep`), named keeper by them
  sleep 600 & PIDS+=("$!")
  printf '{"pid":%s,"sessionId":"%s","name":"keeper","nameSource":"user","kind":"interactive","status":"idle","cwd":"%s"}\n' \
    "$!" "$SID" "$REPO" > "$HOME/.claude/sessions/keeper.json"
}
closed() { # its terminal closed
  kill "${PIDS[-1]}"; wait "${PIDS[-1]}" 2>/dev/null || true
  rm -f "$HOME/.claude/sessions/keeper.json"
}
# The session's own events, one line each: writer seq kind reason stamped
own_events() {
  cat "$SMINOS_HOME/projects/$PROJECT/log/"*.jsonl | python3 -c 'import json, sys
for line in sys.stdin:
    e = json.loads(line)
    if e.get("session") == sys.argv[1] and e.get("kind") in ("joined", "retired"):
        print(e["kind"], e.get("reason", "-"), "stamped" if isinstance(e.get("thread"), str) and e["thread"] else "unstamped")' "$SID"
}
row() { # field — the session's row in this code's `list --stopped --json`, one field
  (cd "$REPO" && "$SMINOS" list --stopped --json) | python3 -c 'import json, sys
rows = [m for m in json.load(sys.stdin) if m["session"] == sys.argv[1]]
print(rows[0][sys.argv[2]] if rows else "<no row>")' "$SID" "$1"
}
calls() { cat "$STUB_STATE/calls" 2>/dev/null || true; }

# ---- this code: a thread its human opened, stopped, a message held for it ----
echo "this code makes the thread, stops it, holds a message:"
opened
run "$SMINOS" list
assert_contains "$OUT" "keeper [${SID:0:8}]" "the session its human opened is a member"
THREAD="$(row thread)"
assert_equals "$(row opened)" human "it is a thread its human opened"
closed
run "$SMINOS" daemon tick
run "$SMINOS" daemon tick
assert_equals "$(row state)" stopped "two sweeps after its terminal closed it is stopped"
run "$SMINOS" say "@keeper hello from this code"
assert_contains "$OUT" "recorded and held" "a message to it is recorded and held"
# A person's words from another machine, as that machine's log reaches this one.
printf '{"ts":"%s","writer":"beta/human","seq":1,"kind":"human","from":"human","to":[{"session":"%s","alias":"keeper"}],"text":"@keeper hello from beta"}\n' \
  "$(python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))')" \
  "$SID" > "$SMINOS_HOME/projects/$PROJECT/log/beta.human.jsonl"
BEFORE="$(own_events)"
assert_equals "$BEFORE" "joined - stamped" "its one membership event is a stamped joined"

# ---- the older CLI: every verb that reads the store ---------------------------
echo "the older CLI over the same store:"
assert_equals "$(calls)" "" "this code asked the stub engine nothing"
run "$OLDER" list
assert_contains "$OUT" "(no members in olderproj)" "its list shows no member: a closed session it does not know as a thread"
assert_equals "$(own_events)" "$(printf 'joined - stamped\nretired ended unstamped')" \
  "its first reading verb reconciled the session to an unstamped ended"
run "$OLDER" say "@keeper hello from the older code"
assert_equals "$RC" 4 "its tagged say is refused (exit 4)"
assert_contains "$OUT" "session ended" "it says the session ended"
run "$OLDER" send keeper "a send from the older code"
assert_equals "$RC" 4 "its send is refused (exit 4)"
assert_contains "$OUT" "keeper: keeper's session ended" "it says the session ended"
run "$OLDER" resume keeper "a resume from the older code"
assert_equals "$RC" 4 "its resume finds no seat (exit 4)"
assert_contains "$OUT" "no seat matching 'keeper'" "it says there is no seat"
run "$OLDER" fill keeper "a fill from the older code"
assert_equals "$RC" 4 "its fill finds no seat (exit 4)"
assert_contains "$OUT" "no seat matching 'keeper'" "it says there is no seat"
run "$OLDER" fill --resume keeper "a fill --resume from the older code"
assert_equals "$RC" 4 "its fill --resume finds no seat (exit 4)"
assert_contains "$OUT" "no seat matching 'keeper'" "it says there is no seat"
run "$OLDER" daemon tick
assert_equals "$RC" 0 "its daemon tick runs"
assert_contains "$OUT" "delivered 0" "its tick delivers nothing"
OUTBOX="$(cat "$SMINOS_HOME/projects/$PROJECT/outcomes.jsonl" 2>/dev/null || true)"
assert_contains "$OUTBOX" '"writer": "beta/human", "seq": 1}, "session": "'"$SID"'", "outcome": "recorded"' \
  "its tick reports the message from another machine as recorded"
assert_equals "$(calls)" "" "no verb of the older CLI called the stub engine: nothing resumed or started"
# The boundary: the older CLI's last verb has run, this code has made no call yet.
BOUNDARY="$(own_events)"
assert_equals "$BOUNDARY" "$(printf 'joined - stamped\nretired ended unstamped')" \
  "at the boundary: this code's stamped joined, then the older copy's unstamped ended, and nothing else"

# ---- this code again ------------------------------------------------------------
echo "this code after the older CLI:"
assert_equals "$(row state)" stopped "list --stopped still shows it stopped"
assert_equals "$(row thread)" "$THREAD" "under the same thread"
run "$SMINOS" daemon owed
assert_equals "$RC" 0 "daemon owed exits 0: what is held is no debt"
assert_contains "$OUT" "closed sessions 2" "both messages are still held for it: the older tick settled nothing"
run "$SMINOS" list
assert_equals "$(own_events)" "$BOUNDARY" "this code's reads wrote nothing over the older copy's ended: no repair joined"
run "$SMINOS" daemon tick
assert_equals "$(own_events)" "$BOUNDARY" "nor did its tick: the older ended is passed by"
opened
run "$SMINOS" list
assert_contains "$OUT" "keeper [${SID:0:8}]" "reopened by its human, it is live as keeper"
assert_equals "$(row thread)" "$THREAD" "the same thread"
assert_equals "$(calls)" "" "and nothing called the stub engine: nothing resumed it but its human"

echo
echo "older CLI: $PASSES passed, $FAILURES failed"
[ "$FAILURES" -eq 0 ]
