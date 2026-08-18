#!/usr/bin/env bash
#
# Hermetic tests for review-dispatch.sh (the qa-loops trigger half).
#
# Side channels stubbed: `gh` (canned per-PR JSON + a call log), `claude`
# (agents view from a file), and the orchestrating-daemons scripts (a stub
# dir that logs spawn/retire and writes registry meta like the real ones).
# git is real: a bare origin + clone, so worktree/fetch behavior is genuine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DISPATCH="$REPO_ROOT/skills/qa-loops/scripts/review-dispatch.sh"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_equals() {
    if [[ "$1" == "$2" ]]; then pass "$3"; else
        fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}
assert_contains() {
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}
assert_file_exists() {
    if [[ -f "$1" ]]; then pass "$2"; else fail "$2"; echo "    missing: $1"; fi
}
# A binding is only bound when it arrives with a VALUE. Anchored on the rendered
# roster line shape (- `NAME`: value), so a binding that rendered as a blank —
# the shape an unsupplied placeholder used to take — reads as unbound here.
assert_bound() {  # assert_bound <prompt> <NAME> <lane>
    local v; v="$(printf '%s\n' "$1" | sed -n "s/^- \`$2\`: \(.*\)$/\1/p" | head -1)"
    if [[ -n "$v" ]]; then pass "\`$2\` renders with a value ($3)"; else
        fail "\`$2\` renders with a value ($3)"; echo "    binding line absent or empty"; fi
}

# ---- environment --------------------------------------------------------------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export MOCK_DIR="$TEST_ROOT/mock"; mkdir -p "$MOCK_DIR"
export MOCK_LOG="$TEST_ROOT/gh-calls.log"; : > "$MOCK_LOG"
export SPAWN_LOG="$TEST_ROOT/spawn.log"; : > "$SPAWN_LOG"
export PROMPT_DIR="$TEST_ROOT/prompts"; mkdir -p "$PROMPT_DIR"
export STUB_COUNT="$TEST_ROOT/count"
export DAEMON_BOOT_ID="boot-current"

# real git: bare origin + working clone with main and a PR head branch
ORIGIN="$TEST_ROOT/origin.git"
git init -q --bare "$ORIGIN"
CLONE="$TEST_ROOT/clone"
git clone -q "$ORIGIN" "$CLONE" 2>/dev/null
git -C "$CLONE" checkout -q -b main
git -C "$CLONE" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
git -C "$CLONE" push -q -u origin main
git -C "$CLONE" checkout -q -b feat/x
echo hi > "$CLONE/f.txt"
git -C "$CLONE" add f.txt
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -m feat -q
git -C "$CLONE" push -q -u origin feat/x
HEAD_SHA="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
export LOCAL_REPO="$CLONE" BOARD_REPO="test/repo"

# stub daemon scripts: log + register meta like the real --no-wait spawn
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "spawn:$*" >> "$SPAWN_LOG"
echo "spawn-env:settings=${DAEMON_CLAUDE_SETTINGS:-};effort=${DAEMON_CLAUDE_EFFORT:-}" >> "$SPAWN_LOG"
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"
if [ -n "${FAIL_SPAWN_FOR:-}" ] && [ "$name" = "$FAIL_SPAWN_FOR" ]; then
  echo "stub daemon-spawn: simulated failure for $name" >&2
  exit 1
fi
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'aaaa%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" C="$cwd" SPAWN_N="$n" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "cwd": os.environ["C"],
           "status": "working",
           # monotonic per spawn: a worker spawned after a retire must sort
           # NEWER than it, as it does in production (both stamp wall clock)
           "updated": "2026-07-08T00:%02d:00Z" % int(os.environ.get("SPAWN_N") or 0)},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
# Simulate the worker's first protocol action: wait for the dispatcher-owned
# ready file, validate it, then acknowledge before ORIENT. Tests can suppress
# this to prove dispatch does not report success for a worker that never starts.
bind_ready="$(printf '%s\n' "$task" | grep '^- `BIND_READY_FILE`:' | cut -d' ' -f3- || true)"
# The real barrier also verifies the worker's OWN registry identity against
# the name the protocol gives it. A stub that acked without checking hid a
# barrier no scale worker could ever satisfy (it named review-pr-<n> while a
# scale worker is review-epic-<n>), so check it here: a mismatch leaves the
# barrier unacked and dispatch fails exactly as it would in production.
wname="$(printf '%s\n' "$task" | sed -n 's/^- `WORKER_NAME`: \([^ ][^ ]*\).*/\1/p' | head -1)"
if [ "$wname" != "$name" ]; then
  echo "stub worker: barrier identity mismatch (prompt names '$wname', registry name is '$name')" >&2
  bind_ready=""
fi
if [ -n "$bind_ready" ] && [ "${STUB_NO_BIND_ACK:-0}" != "1" ]; then
  READY="$bind_ready" UUID="$uuid" python3 - <<'PY' >/dev/null 2>&1 &
import json, os, time
ready=os.environ["READY"]
for _ in range(500):
    if os.path.isfile(ready):
        ack=ready+".ack"; tmp=ack+".tmp"
        with open(tmp,"w") as f: json.dump({"uuid":os.environ["UUID"]},f)
        os.replace(tmp,ack)
        break
    time.sleep(0.01)
PY
fi
if [ "${STUB_BAD_SPAWN_BANNER:-0}" = "1" ]; then
  echo "daemon spawned without parseable identity"
else
  echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working"
fi
STUB
cat > "$STUB_DAEMONS/codex-spawn.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "codex-spawn:$*" >> "$SPAWN_LOG"
[ "${1:-}" = "--no-wait" ] && shift
name="$1"; task="$2"; cwd="${3:-}"
if [ -n "${FAIL_SPAWN_FOR:-}" ] && [ "$name" = "$FAIL_SPAWN_FOR" ]; then
  echo "stub codex-spawn: simulated failure for $name" >&2
  exit 1
fi
printf '%s' "$task" > "$PROMPT_DIR/$name.prompt"
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$STUB_COUNT"
uuid="$(printf 'cdec%04d' "$n")-0000-4000-8000-000000000000"
U="$uuid" N="$name" C="$cwd" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": os.environ["N"], "cwd": os.environ["C"],
           "engine": "codex", "pid": "99999",
           "status": "working", "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "daemon spawned (no-wait): $name  [${uuid%%-*} / $uuid]  status=working"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
# Faithful to the real daemon-retire.sh: mark the meta retired and bump
# `updated`. A log-only stub let a "retired" failure keep its status=error,
# which is precisely the evidence the real one destroys.
echo "retire:$1" >> "$SPAWN_LOG"
python3 - "$1" <<'PY'
import glob, json, os, sys
q = sys.argv[1]
for path in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if path.endswith(".reply.json"):
        continue
    base = os.path.basename(path)[:-5]
    if base != q and not base.startswith(q):
        continue
    try:
        m = json.load(open(path))
    except Exception:
        continue
    m["status"] = "retired"
    # +1s on its own clock: newer than the worker's last activity, older than
    # any worker spawned after it (production stamps wall clock for both)
    u = str(m.get("updated") or "2026-07-08T00:00:00Z")
    m["updated"] = u[:-2] + "%02dZ" % min(59, int(u[-3:-1]) + 1)
    json.dump(m, open(path, "w"), indent=2)
PY
STUB
# Faithful stand-in for daemon-finalize.sh: same contract (noop/live/absent/
# idle/error on stdout), driven by the registry meta + the mock agents view;
# reply content comes from an optional $MOCK_DIR/reply-<uuid>.txt fixture.
cat > "$STUB_DAEMONS/daemon-finalize.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
meta=""
for f in "$DAEMON_HOME"/*.json; do
  case "$f" in *.reply.json) continue ;; esac
  case "$(basename "$f" .json)" in "$1"*) meta="$f"; break ;; esac
done
[ -n "$meta" ] || { echo "noop"; exit 0; }
uuid="$(basename "$meta" .json)"
out="$(M="$meta" A="$MOCK_DIR/agents.json" python3 <<'PY'
import json, os
m = json.load(open(os.environ["M"]))
if m.get("engine") == "codex" or m.get("status") not in ("working", "blocked"):
    print("noop"); raise SystemExit
cur = m.get("current") or m.get("uuid")
try:
    rows = json.load(open(os.environ["A"]))
except Exception:
    rows = []
row = next((r for r in rows if r.get("sessionId") == cur), None)
state = (row or {}).get("state") or ""
# mirror the real script: a lingering finished session stays state=working;
# status (busy -> idle) is the turn signal
if row is not None and state == "working" and row.get("status") == "idle":
    state = "done"
if state == "":
    print("absent")
elif state in ("working", "blocked"):
    print("live")
elif state == "done":
    print("idle")
else:
    print("error")
PY
)"
case "$out" in
  idle|error)
    if [ -f "$MOCK_DIR/reply-$uuid.txt" ]; then
      cp "$MOCK_DIR/reply-$uuid.txt" "$DAEMON_HOME/$uuid.reply.txt"
    else
      echo "review finished." > "$DAEMON_HOME/$uuid.reply.txt"
    fi
    M="$meta" S="$out" python3 -c '
import json, os
m = json.load(open(os.environ["M"]))
m["status"] = os.environ["S"]
json.dump(m, open(os.environ["M"], "w"))
' ;;
esac
echo "$out"
STUB
chmod +x "$STUB_DAEMONS/daemon-spawn.sh" "$STUB_DAEMONS/codex-spawn.sh" "$STUB_DAEMONS/daemon-retire.sh" "$STUB_DAEMONS/daemon-finalize.sh"
export DAEMON_SCRIPTS="$STUB_DAEMONS"

# Minimal board-bind stand-in: this suite tests dispatch ownership mechanics,
# while the issue-tracker suite tests board-bind's GitHub validation itself.
STUB_BOARD="$TEST_ROOT/stub-board"; mkdir -p "$STUB_BOARD"
cat > "$STUB_BOARD/board-bind.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
# Contract guard, not stub detail: the real board scripts source _lib.sh, whose
# _board_root() resolves BOARD_ROOT from the CURRENT directory and dies "not
# inside a git repo" when cwd is not a checkout. The dispatcher must therefore
# hand us a cwd inside LOCAL_REPO. Reproduce that requirement here — without
# it, the Actions entrypoint (which runs from an EMPTY workspace, since
# pr-review-dispatch.yml omits actions/checkout on purpose) regressed silently.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "error: not inside a git repo" >&2; exit 1; }
q="$1"; ticket="$2"; hit=""
for p in "$DAEMON_HOME"/*.json; do
  [ "$(basename "$p" .json)" = "$q" ] || [[ "$(basename "$p" .json)" == "$q"* ]] || continue
  [ -z "$hit" ] || exit 1
  hit="$p"
done
[ -n "$hit" ] || exit 1
M="$hit" T="$ticket" D="$DAEMON_HOME" python3 - <<'PY'
import glob, json, os
p=os.environ["M"]; ticket=os.environ["T"]
for q in glob.glob(os.path.join(os.environ["D"], "*.json")):
    if q == p or q.endswith(".reply.json"): continue
    m=json.load(open(q))
    if str(m.get("ticket", "")).lstrip("#") == ticket.lstrip("#"):
        del m["ticket"]; json.dump(m, open(q,"w"), indent=2)
m=json.load(open(p)); m["ticket"]=ticket
json.dump(m, open(p,"w"), indent=2)
PY
STUB
chmod +x "$STUB_BOARD/board-bind.sh"
# Board WRITES from this dispatcher (the scale-review outage escalation) go
# through board-transition.sh, the same $BOARD_SCRIPTS convention board-bind
# uses; the issue-tracker suite owns that script's own semantics.
cat > "$STUB_BOARD/board-transition.sh" <<'STUB'
#!/usr/bin/env bash
echo "board-transition:$*" >> "$SPAWN_LOG"
STUB
chmod +x "$STUB_BOARD/board-transition.sh"
# ...but the E2 scale-review branch reads the BOARD itself (`PYTHONPATH=
# $BOARD_SCRIPTS python3 -c 'import _board'`), so the real module is copied
# in beside the stub: board-bind stays stubbed, the snapshot is genuine and
# runs against the mock `gh` below.
cp "$REPO_ROOT/skills/issue-tracker/scripts/_board.py" "$STUB_BOARD/_board.py"
# The dispatcher resolves its board BINDING before anything gh-mode-specific
# (that is what makes the API path reachable without gh), and it sources that
# resolver out of $BOARD_SCRIPTS — so the stub dir needs the real one. It is
# side-effect-free and, with no .doperpowers/board.json in these fixtures,
# resolves gh mode: every case below is the gh path, unchanged.
cp "$REPO_ROOT/skills/issue-tracker/scripts/_binding.sh" "$STUB_BOARD/_binding.sh"
# Same reason, same shape: the claim journal and its reconciliation were
# verbatim copies in both dispatchers until _claim_journal.sh took ownership of
# them, and this dispatcher sources it at TOP LEVEL — before any binding fork,
# so the gh path needs it just as much as the API path does. Absent from the
# stub dir, every case in this suite dies at the source line. Function
# definitions only, no side effects at source time, exactly like _binding.sh.
cp "$REPO_ROOT/skills/issue-tracker/scripts/_claim_journal.sh" "$STUB_BOARD/_claim_journal.sh"
export BOARD_SCRIPTS="$STUB_BOARD"
# Every PRE-EXISTING case in this file exercises the claude path unchanged —
# the label→env→codex resolution only kicks in per-test below via an
# explicit WORKER_ENGINE=codex prefix.
export WORKER_ENGINE=claude

# stub gh + claude
STUB_BIN="$TEST_ROOT/bin"; mkdir -p "$STUB_BIN"
cat > "$STUB_BIN/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$MOCK_LOG"
case "${1:-} ${2:-}" in
  "repo view")
    # two callers: the default-branch read, and BOARD_REPO self-resolution
    # when the caller did not supply one
    case "$*" in
      *nameWithOwner*) echo "test/repo" ;;
      *) echo "${MOCK_DEFAULT_BRANCH:-main}" ;;          # -q .defaultBranchRef.name
    esac ;;
  "pr view")
    # `--json state -q .state` is the cleanup pass's per-candidate check; a PR
    # with no fixture answers like a gone/unreachable one (non-zero).
    if [ ! -f "$MOCK_DIR/pr-$3.json" ]; then echo "gh: no such PR $3" >&2; exit 1; fi
    case "$*" in
      *"--json state"*) python3 -c 'import json,os,sys; print(json.load(open(os.environ["MOCK_DIR"]+"/pr-"+sys.argv[1]+".json")).get("state","OPEN"))' "$3" ;;
      *) cat "$MOCK_DIR/pr-$3.json" ;;
    esac ;;
  "pr list")
    [ "${MOCK_PR_LIST_FAILS:-0}" = "1" ] && { echo "gh: pr list exploded" >&2; exit 1; }
    cat "$MOCK_DIR/pr-list.json" ;;
  "issue view")
    case "$*" in
      *"--json url"*)  N="$3" python3 -c 'import json,os;print(json.load(open(os.environ["MOCK_DIR"]+"/issue-"+os.environ["N"]+".json"))["url"])' ;;
      *"--json body"*) N="$3" python3 -c 'import json,os;print(json.load(open(os.environ["MOCK_DIR"]+"/issue-"+os.environ["N"]+".json"))["body"])' ;;
      *"--json labels"*) N="$3" python3 -c 'import json,os;d=json.load(open(os.environ["MOCK_DIR"]+"/issue-"+os.environ["N"]+".json"));print(json.dumps({"labels": d.get("labels") or [], "state": d.get("state","OPEN")}))' ;;
      *) echo "mock gh: unhandled issue view: $*" >&2; exit 1 ;;
    esac ;;
  "issue list") cat "$MOCK_DIR/techdebt-number.txt" ;;
  "api graphql")
    # _board.py's snapshot query, served from an optional
    # $MOCK_DIR/board-issues.json fixture in the same node shape
    # tests/issue-tracker/mock-gh/gh produces. No fixture = an empty board.
    python3 - <<'PY'
import json, os
try:
    issues = json.load(open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json")))
except Exception:
    issues = []
nodes = []
for it in issues:
    n = it["number"]
    nodes.append({
        "id": "ID_%d" % n, "number": n, "title": it.get("title", "ticket %d" % n),
        "body": it.get("body", ""), "state": it.get("state", "OPEN"),
        "stateReason": "COMPLETED" if it.get("state") == "CLOSED" else None,
        "createdAt": "2026-08-01T00:00:00Z", "updatedAt": "2026-08-01T00:00:00Z",
        "url": "https://github.com/test/repo/issues/%d" % n,
        "labels": {"nodes": [{"name": l} for l in it.get("labels", [])]},
        "assignees": {"nodes": []},
        "parent": {"number": it["parent"]} if it.get("parent") else None,
        "blockedBy": {"nodes": []},
        "closedByPullRequestsReferences": {"totalCount": 0, "nodes": []},
        "timelineItems": {"totalCount": 0, "nodes": []},
    })
print(json.dumps({"data": {"repository": {"issues": {
    "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}))
PY
    ;;
  *) echo "mock gh: unhandled: $*" >&2; exit 1 ;;
esac
STUB
cat > "$STUB_BIN/claude" <<'STUB'
#!/usr/bin/env bash
[ "${1:-}" = "agents" ] && { cat "$MOCK_DIR/agents.json"; exit 0; }
exit 0
STUB
# Transparent git recorder: real git, every invocation logged. The scale path
# has to FETCH things (per-child pull heads) whose absence is silent
# otherwise — a missing fetch shows up only as a review that cannot resolve a
# range, hours later and somewhere else.
export GIT_CALL_LOG="$TEST_ROOT/git-calls.log"; : > "$GIT_CALL_LOG"
REAL_GIT="$(command -v git)"
cat > "$STUB_BIN/git" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$GIT_CALL_LOG"
exec "$REAL_GIT" "\$@"
STUB
chmod +x "$STUB_BIN/gh" "$STUB_BIN/claude" "$STUB_BIN/git"
export PATH="$STUB_BIN:$PATH"

# canned GitHub data
echo "[]" > "$MOCK_DIR/agents.json"
echo "99" > "$MOCK_DIR/techdebt-number.txt"
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHA"]
list_entries = []
def pr(n, **kw):
    base = {"number": n, "title": "feat: add f", "body": "Adds f.\n\nCloses #7",
            "baseRefName": "main", "headRefName": "feat/x", "headRefOid": sha,
            "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": False,
            "state": "OPEN", "labels": [], "closingIssuesReferences": []}
    base.update(kw)
    json.dump(base, open(os.path.join(d, "pr-%d.json" % n), "w"))
    # gh pr list carries the same ticket-linking fields gh pr view does — the
    # sweep resolves the primary ticket from the list call now, before any
    # per-PR view.
    list_entries.append({k: base[k] for k in
                          ("number", "isDraft", "labels", "title", "body",
                           "closingIssuesReferences")})
pr(5)
pr(6, isDraft=True)
pr(9, title="chore: tidy", body="No ticket for this one.")
json.dump([e for e in list_entries if e["number"] != 9],
          open(os.path.join(d, "pr-list.json"), "w"))
json.dump({"url": "https://github.com/test/repo/issues/7",
           "body": "Ticket seven brief body"}, open(os.path.join(d, "issue-7.json"), "w"))
PY

reset_state() { rm -f "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; rm -rf "$DAEMON_HOME"/review-pr-*-control.*; : > "$SPAWN_LOG"; echo "[]" > "$MOCK_DIR/agents.json"; }

# ---- triggered dispatch (happy path) ------------------------------------------
echo "triggered dispatch:"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "spawns --no-wait with the registry name"
assert_contains "$(cat "$DAEMON_HOME/aaaa0001-0000-4000-8000-000000000000.json")" '"ticket": "7"' "ticketed Reviewer worker is bound for board-answer resume"
assert_contains "$(cat "$DAEMON_HOME/aaaa0001-0000-4000-8000-000000000000.json")" '"role": "QAGENT"' "reviewer meta records its lane so an answered park returns to in-review, not in-progress"
WT="$LOCAL_REPO/.claude/worktrees/review-pr-5"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "worktree checked out at the PR head SHA"
if git -C "$WT" symbolic-ref -q HEAD >/dev/null; then
    fail "worktree is detached"; else pass "worktree is detached"; fi
PROMPT="$(cat "$PROMPT_DIR/review-pr-5.prompt")"
BIND_READY="$(printf '%s\n' "$PROMPT" | grep '^- `BIND_READY_FILE`:' | cut -d' ' -f3- || true)"
assert_contains "$PROMPT" "REVIEW worker for PR #5" "prompt carries the worker bootstrap header"
assert_contains "$PROMPT" '`BIND_READY_FILE`:' "prompt carries the startup binding barrier"
if [ -n "$BIND_READY" ] && [ -f "$BIND_READY" ]; then pass "bind-ready barrier opens after exclusive binding"; else fail "bind-ready barrier opens after exclusive binding"; fi
assert_contains "$(cat "$BIND_READY" 2>/dev/null || true)" '"ticket": "7"' "barrier proves the primary ticket binding"
assert_contains "$(cat "$BIND_READY" 2>/dev/null || true)" '"ledger"' "barrier carries the undisclosed ledger path to the orchestrator"
if [ -f "$BIND_READY.ack" ]; then pass "dispatch waits for worker barrier acknowledgement"; else fail "dispatch waits for worker barrier acknowledgement"; fi
assert_not_contains "$PROMPT" "Adds f." "prompt carries no inlined PR body (the worker reads the PR live via gh)"
assert_contains "$PROMPT" '`ISSUE_NUMBER`: 7' "prompt binds the primary ticket (Closes #7 parsed from the body)"
assert_not_contains "$PROMPT" "Ticket seven brief body" "prompt carries no inlined ticket body"
assert_contains "$PROMPT" '`BASE_REF`: main' "prompt carries the base ref"
assert_contains "$PROMPT" '`TECH_DEBT_ISSUE`: 99' "prompt carries the standing tech-debt issue binding"
assert_contains "$PROMPT" '`AUTO_MERGE`: off' "prompt binds auto-merge off by default (observation mode)"
assert_contains "$PROMPT" "no repo risk-surface manifest" "prompt renders the manifest-absent fallback when the repo has none"
assert_contains "$PROMPT" "no repo-facts manifest" "prompt renders the repo-facts-absent fallback when the repo has none"
assert_not_contains "$PROMPT" "{{" "no unsubstituted bootstrap placeholder survives"
assert_contains "$PROMPT" '`REVIEW_MODE`: pr' "leaf prompt binds the ordinary pr mode"
assert_not_contains "$PROMPT" "SCALE REVIEWER" "leaf prompt carries none of the scale variant's framing"
assert_not_contains "$PROMPT" "CLOSURE_PACKAGE" "leaf prompt carries no closure-package binding"
assert_not_contains "$PROMPT" "<!-- mode:" "mode blocks are resolved at render, never shipped to the worker"
assert_contains "$PROMPT" "Use doperpowers:qa-loops" "prompt names the Review Worker Protocol skill"
assert_contains "$PROMPT" "dispatcher-pinned copy" "prompt routes the protocol through the dispatcher-pinned file"
assert_contains "$PROMPT" "$REPO_ROOT/skills/qa-loops/SKILL.md" "prompt carries the canonical dispatcher-owned skill path"
assert_contains "$PROMPT" "$REPO_ROOT/skills/executing/SKILL.md" "prompt carries the canonical implement-contract path (the skill IS the protocol)"
assert_contains "$PROMPT" "scripts/review-engine.sh" "prompt binds the engine script path"
assert_contains "$PROMPT" '`CODEX_REVIEW_MODEL`:' "prompt binds the engine model"
assert_contains "$PROMPT" '`CODEX_REVIEW_EFFORT`:' "prompt binds the engine effort"
# The bindings a reviewer cannot function without, pinned on the VALUE side:
# an existing `NAME`: assertion passes just as well against a rendered blank.
assert_bound "$PROMPT" BIND_READY_FILE pr
assert_bound "$PROMPT" IMPLEMENT_PROTOCOL_FILE pr
assert_bound "$PROMPT" BOARD_SCRIPTS pr
SKILL_PIN="$(printf '%s\n' "$PROMPT" | sed -n 's/.*dispatcher-pinned copy at `\([^`]*\)`.*/\1/p' | head -1)"
if [[ -n "$SKILL_PIN" ]]; then pass "SKILL_FILE renders a protocol path"; else
    fail "SKILL_FILE renders a protocol path"; fi

# ---- an unsupplied bootstrap placeholder fails the render ----------------------
# The renderer used to substitute an unknown {{X}} with "", so a binding a mode
# block asks for and no call site supplies shipped as a silent blank — and no
# downstream assertion can tell "empty by design" from "erased". Driven through
# a copy of the skill whose template carries one placeholder nothing fills
# (the template path is derived from the script's own dir, so the copy IS the
# lever); the sibling skills the dispatcher sources are symlinked back.
echo "unrendered placeholder fails closed:"
ALT_SKILLS="$TEST_ROOT/alt-skills"; mkdir -p "$ALT_SKILLS"
ln -s "$REPO_ROOT/skills/orchestrating-daemons" "$ALT_SKILLS/orchestrating-daemons"
cp -R "$REPO_ROOT/skills/qa-loops" "$ALT_SKILLS/qa-loops"
printf '\n- `FORGOTTEN_BINDING`: {{FORGOTTEN_BINDING}}\n' \
    >> "$ALT_SKILLS/qa-loops/references/review-worker-bootstrap.md"
reset_state
rm -f "$PROMPT_DIR/review-pr-5.prompt"
if ALT_OUT="$("$ALT_SKILLS/qa-loops/scripts/review-dispatch.sh" 5 2>&1)"; then
    fail "a placeholder no call site supplies fails the dispatch"
else
    pass "a placeholder no call site supplies fails the dispatch"
fi
assert_contains "$ALT_OUT" "unrendered placeholders: FORGOTTEN_BINDING" "the render failure names the placeholder"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "no reviewer is spawned on a failed render"
if [[ -f "$PROMPT_DIR/review-pr-5.prompt" ]]; then
    fail "no prompt reaches a worker on a failed render"
else
    pass "no prompt reaches a worker on a failed render"
fi

# Ticket ownership is exclusive: the reviewer replaces the finished implement
# worker as board-answer's resume target.
echo "review ticket binding:"
reset_state
OLD="impl0000-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["OLD"]
json.dump({"uuid": u, "current": u, "name": "implement-ticket-7",
           "status": "idle", "ticket": "7", "updated": "2026-07-07T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
"$DISPATCH" 5 >/dev/null
NEW_META="$(python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    m=json.load(open(p))
    if m.get("name") == "review-pr-5": print(p); break
PY
)"
assert_contains "$(cat "$NEW_META")" '"ticket": "7"' "new reviewer owns ticket #7"
assert_not_contains "$(cat "$DAEMON_HOME/impl0000-0000-4000-8000-000000000000.json")" '"ticket"' "old Executor worker binding is stripped"

# Regression (2026-08-02): the GitHub Actions entrypoint runs the dispatcher
# from an EMPTY, non-git workspace — pr-review-dispatch.yml omits
# actions/checkout so the job never executes PR code. The dispatcher's own git
# calls all use `git -C "$LOCAL_REPO"`, so nothing corrected the process cwd,
# and every bare board-script call died at source time in _lib.sh. Live effect:
# four ticketed PRs in a row spawned a reviewer, failed to bind, and retired it.
echo "board scripts are invoked from inside LOCAL_REPO:"
NOT_A_REPO="$TEST_ROOT/not-a-repo"; mkdir -p "$NOT_A_REPO"
reset_state
if (cd "$NOT_A_REPO" && "$DISPATCH" 5 >/dev/null 2>&1); then
    pass "dispatch from a non-repo cwd still reaches board-bind"
else
    fail "dispatch from a non-repo cwd still reaches board-bind"
fi
assert_contains "$(cat "$(python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    m=json.load(open(p))
    if m.get("name") == "review-pr-5": print(p); break
PY
)")" '"ticket": "7"' "ticket binds even when the caller's cwd is not a checkout"

# Binding is mandatory: an unbound reviewer could park needs-human where the
# answer relay cannot reach it. Retire it instead of allowing the dispatch.
FAIL_BOARD="$TEST_ROOT/fail-board"; mkdir -p "$FAIL_BOARD"
printf '#!/usr/bin/env bash\nexit 1\n' > "$FAIL_BOARD/board-bind.sh"
chmod +x "$FAIL_BOARD/board-bind.sh"
# Only the BIND fails here: the two files the dispatcher SOURCES out of this
# same dir — the binding resolver and the claim journal — would otherwise abort
# the run before a reviewer was ever spawned, and the assertions below are
# about what happens to a spawned one. A dir that fails everything would still
# make the dispatch fail, but for the wrong reason, and the retire it is
# checking for would never be reached.
cp "$REPO_ROOT/skills/issue-tracker/scripts/_binding.sh" "$FAIL_BOARD/_binding.sh"
cp "$REPO_ROOT/skills/issue-tracker/scripts/_claim_journal.sh" "$FAIL_BOARD/_claim_journal.sh"
reset_state
if BOARD_SCRIPTS="$FAIL_BOARD" REVIEW_BIND_ATTEMPTS=1 REVIEW_BIND_DELAY=0 "$DISPATCH" 5 >/dev/null 2>&1; then
    fail "bind failure aborts review dispatch"
else
    pass "bind failure aborts review dispatch"
fi
assert_contains "$(cat "$SPAWN_LOG")" "retire:" "bind failure retires the unreachable reviewer"
assert_equals "$(find "$DAEMON_HOME" -name bind-ready.json -type f -print)" "" "bind failure never opens the startup barrier"

# A published barrier is not success until the worker acknowledges it. A model
# that died/timed out before reading the prompt is retired and dispatch fails.
reset_state
if STUB_NO_BIND_ACK=1 REVIEW_ACK_POLLS=2 REVIEW_ACK_DELAY=0.01 "$DISPATCH" 5 >/dev/null 2>&1; then
    fail "missing worker barrier ack fails dispatch"
else
    pass "missing worker barrier ack fails dispatch"
fi
assert_contains "$(cat "$SPAWN_LOG")" "retire:" "missing barrier ack retires the non-started reviewer"

# Exact spawn identity is mandatory. A changed/unparseable banner must fail
# closed, never fall back to a same-name registry heuristic.
reset_state
if STUB_BAD_SPAWN_BANNER=1 "$DISPATCH" 5 >/dev/null 2>&1; then
    fail "unparseable spawn UUID fails dispatch"
else
    pass "unparseable spawn UUID fails dispatch"
fi
assert_equals "$(find "$DAEMON_HOME" -name bind-ready.json -type f -print)" "" "identity parse failure never opens the barrier"

# Every control-state initialization step is explicitly guarded in sweep mode;
# set -e is suspended beneath the per-PR `||` wrapper.
assert_contains "$(cat "$DISPATCH")" "control state initialization failed" "control-state setup has a fail-closed guard"

# ---- worktree bootstrap hook ---------------------------------------------------
# WORKTREE_BOOTSTRAP_CMD runs inside the fresh worktree before the worker
# spawns; its failure is reported but never blocks the dispatch. The command
# executes with the worktree at the TRUSTED base ref — never the PR head —
# and the worktree lands on the PR head afterwards.
echo "worktree bootstrap:"
reset_state
out="$(WORKTREE_BOOTSTRAP_CMD='touch .bootstrapped && echo deps-ready' "$DISPATCH" 5)"
WT="$LOCAL_REPO/.claude/worktrees/review-pr-5"
assert_file_exists "$WT/.bootstrapped" "bootstrap command ran inside the fresh worktree"
assert_contains "$(cat "$DAEMON_HOME/review-pr-5.bootstrap.log" 2>/dev/null || true)" "deps-ready" "bootstrap output lands in the registry log"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "bootstrapped dispatch still spawns"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "bootstrapped worktree still ends at the PR head SHA"

# Trust invariant: f.txt exists only on the PR head (feat/x), not on main —
# a bootstrap that could see it would be executing PR-controlled state.
reset_state
out="$(WORKTREE_BOOTSTRAP_CMD='if [ -f f.txt ]; then touch .saw-pr-head; else touch .ran-on-base; fi' "$DISPATCH" 5)"
assert_file_exists "$WT/.ran-on-base" "bootstrap executed against the trusted base ref"
if [ -f "$WT/.saw-pr-head" ]; then
    fail "bootstrap never sees PR-head files"
else
    pass "bootstrap never sees PR-head files"
fi
assert_file_exists "$WT/f.txt" "worktree carries the PR head after the bootstrap"

reset_state
out="$(WORKTREE_BOOTSTRAP_CMD='echo boom >&2; exit 7' "$DISPATCH" 5 2>&1)"
assert_contains "$out" "bootstrap failed rc=7" "failed bootstrap is reported with its exit code"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "failed bootstrap never blocks dispatch"

# Budget overrun: TERM (then KILL) fires and the dispatch still completes —
# never hangs for the sleep's full 300s.
reset_state
t0=$SECONDS
out="$(WORKTREE_BOOTSTRAP_CMD='sleep 300' WORKTREE_BOOTSTRAP_TIMEOUT=1 "$DISPATCH" 5 2>&1)"
elapsed=$((SECONDS - t0))
assert_contains "$out" "bootstrap failed" "overrunning bootstrap is killed and reported"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "killed bootstrap never blocks dispatch"
if [ "$elapsed" -lt 60 ]; then
    pass "budget enforcement is prompt (${elapsed}s)"
else
    fail "budget enforcement is prompt (${elapsed}s)"
fi

reset_state
out="$("$DISPATCH" 5)"
if [ -f "$LOCAL_REPO/.claude/worktrees/review-pr-5/.bootstrapped" ]; then
    fail "unset WORKTREE_BOOTSTRAP_CMD keeps prior behavior (no bootstrap)"
else
    pass "unset WORKTREE_BOOTSTRAP_CMD keeps prior behavior (no bootstrap)"
fi

# ---- per-worker dispatch lock ---------------------------------------------------
# A concurrent dispatch (PR event + sweep overlapping a long bootstrap) is
# skipped while the lock is fresh; a stale lock is stolen, not obeyed.
echo "dispatch lock:"
reset_state
mkdir "$DAEMON_HOME/review-pr-5.dispatch.lock"
out="$("$DISPATCH" 5)"
assert_contains "$out" "concurrent dispatch holds the lock — skip" "fresh lock skips the second dispatch"
assert_equals "$(cat "$SPAWN_LOG")" "" "locked dispatch spawns nothing"
rmdir "$DAEMON_HOME/review-pr-5.dispatch.lock"

reset_state
mkdir "$DAEMON_HOME/review-pr-5.dispatch.lock"
python3 - "$DAEMON_HOME/review-pr-5.dispatch.lock" <<'PY'
import os, sys, time
t = time.time() - 3600
os.utime(sys.argv[1], (t, t))
PY
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "stale lock is stolen and dispatch proceeds"
if [ -d "$DAEMON_HOME/review-pr-5.dispatch.lock" ]; then
    fail "lock is released after dispatch"
else
    pass "lock is released after dispatch"
fi

# ---- skips --------------------------------------------------------------------
echo "skips:"
reset_state
out="$("$DISPATCH" 6)"
assert_contains "$out" "draft" "draft PR skipped"
assert_equals "$(cat "$SPAWN_LOG")" "" "draft PR spawns nothing"

# ---- dedupe: active / dead / finished -----------------------------------------
echo "dedupe:"
seed_reviewer() {  # $1=status
    S="$1" python3 - <<'PY'
import json, os
json.dump({"uuid": "feed0000-0000-4000-8000-000000000000",
           "current": "feed0000-0000-4000-8000-000000000000",
           "name": "review-pr-5", "status": os.environ["S"],
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "feed0000-0000-4000-8000-000000000000.json"), "w"))
PY
}
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "live ACTIVE reviewer → skip"
assert_equals "$(cat "$SPAWN_LOG")" "" "live ACTIVE reviewer spawns nothing"

reset_state; seed_reviewer working    # agents.json now [] → session gone
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "dead reviewer retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "dead reviewer respawned"

reset_state
H="old-host" B="boot-old" python3 - <<'PY'
import json, os
u = "feed0000-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "claude",
           "host": os.environ["H"], "boot_id": os.environ["B"], "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "foreign-host Claude reviewer is retired despite a visible migrated session"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host Claude reviewer is respawned"

reset_state; seed_reviewer idle
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "triggered mode retires a finished reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "triggered mode re-dispatches after an explicit event"

# ---- finished-but-unfinalized reviewer (the one-harness lifecycle) ---------------
# A --no-wait worker's meta stays status=working after its turn ends; only
# `claude agents` knows the truth, and finished --bg sessions stay LISTED
# indefinitely — presence alone is NOT liveness. Dispatch must finalize
# through daemon-finalize.sh before deciding.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "done"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "finished-but-unfinalized reviewer is finalized + retired, not skipped as active"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "finished-but-unfinalized reviewer re-dispatches on an explicit event"
# The retire that follows overwrites status with `retired` (as the real
# daemon-retire does), so finalize's own durable evidence is its reply file.
assert_file_exists "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt" "dispatch finalized the meta through daemon-finalize (reply recorded)"

# The ENGINE-UNAVAILABLE marker reaches the reply file THROUGH finalization,
# so the sweep's outage retry works on the one-harness lifecycle.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "done"}]' > "$MOCK_DIR/agents.json"
printf 'trail posted; engine down.\nENGINE-UNAVAILABLE\n' > "$MOCK_DIR/reply-feed0000-0000-4000-8000-000000000000.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "sweep finalizes and retries an unfinalized ENGINE-UNAVAILABLE reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep re-dispatches after finalizing the outage turn"
rm -f "$MOCK_DIR/reply-feed0000-0000-4000-8000-000000000000.txt"

# A normally-finished turn finalizes to idle and the sweep SKIPS it — no
# endless respawn of completed reviews.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "done"}]' > "$MOCK_DIR/agents.json"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "sweep finalizes a normally-finished reviewer and skips it"
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:" "a finalized finished reviewer is not retired by the sweep"

# Production shape (observed live 2026-07-15): a finished daemon LINGERS in
# `claude agents` with state=working while its process lives — `status`
# (busy → idle) is the turn signal. An explicit PR event must still finalize
# and re-dispatch such a reviewer instead of skipping it as active forever.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working", "status": "idle"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "lingering finished reviewer (state=working, status=idle) is finalized + retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "lingering finished reviewer re-dispatches on an explicit event"
assert_file_exists "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt" "lingering finished reviewer was finalized (reply recorded)"

# ...and a genuinely mid-turn reviewer (status=busy) still skips as active.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working", "status": "busy"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "busy reviewer still skips as active"
assert_equals "$(cat "$SPAWN_LOG")" "" "busy reviewer spawns nothing"

# ---- dedupe without exported DAEMON_HOME (production repro) -------------------
# In launchd/cron the parent process never exports DAEMON_HOME — the script's
# own `DAEMON_HOME="${DAEMON_HOME:-...}"` default assignment computes it fine
# either way, but _reviewer_meta's python subprocess only sees it if the
# shell var was exported (or passed inline). Seed the registry at the
# DEFAULT location ($HOME/.claude/orchestrating-daemons, not the test's
# $DAEMON_HOME override) and invoke the dispatcher with DAEMON_HOME entirely
# absent from the child environment.
echo "dedupe without exported DAEMON_HOME:"
reset_state
DEFAULT_DAEMON_HOME="$HOME/.claude/orchestrating-daemons"; mkdir -p "$DEFAULT_DAEMON_HOME"
NOEXPORT_UUID="cafe1234-0000-4000-8000-000000000000"
D="$DEFAULT_DAEMON_HOME" U="$NOEXPORT_UUID" python3 - <<'PY'
import json, os
json.dump({"uuid": os.environ["U"], "current": os.environ["U"],
           "name": "review-pr-5", "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["D"], os.environ["U"] + ".json"), "w"))
PY
echo "[{\"id\": \"cafe1234\", \"sessionId\": \"$NOEXPORT_UUID\", \"state\": \"working\"}]" > "$MOCK_DIR/agents.json"
out="$(env -u DAEMON_HOME HOME="$HOME" PATH="$PATH" LOCAL_REPO="$LOCAL_REPO" BOARD_REPO="$BOARD_REPO" \
    DAEMON_SCRIPTS="$DAEMON_SCRIPTS" MOCK_DIR="$MOCK_DIR" MOCK_LOG="$MOCK_LOG" SPAWN_LOG="$SPAWN_LOG" \
    PROMPT_DIR="$PROMPT_DIR" STUB_COUNT="$STUB_COUNT" "$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "ACTIVE+live reviewer skipped even with DAEMON_HOME absent from the child env"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn logged — DAEMON_HOME reached _reviewer_meta via explicit passthrough, not inheritance"
rm -rf "$DEFAULT_DAEMON_HOME"

# ---- sweep ---------------------------------------------------------------------
echo "sweep:"
reset_state; seed_reviewer idle
out="$("$DISPATCH" --sweep)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep skips finished(5)/draft(6)"
reset_state
out="$("$DISPATCH" --sweep)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "sweep dispatches the unbound open PR"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-6" "sweep never dispatches a draft"

# ---- sweep honors REVIEW_MAX_CONCURRENT (gh-mode spawn throttle) ----------------
# gh mode's work list is the open-PR listing itself: with a deep backlog one
# tick would spawn one reviewer daemon per open PR. The cap counts live
# reviewer metas (working/blocked) and queues everything beyond it to a later
# tick. Triggered dispatch is an explicit event and is never gated.
echo "review cap:"
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHA"]
base = {"number": 4, "title": "fix: something", "body": "No ticket for this one.",
        "baseRefName": "main", "headRefName": "feat/x", "headRefOid": sha,
        "url": "https://github.com/test/repo/pull/4", "isDraft": False,
        "state": "OPEN", "labels": [], "closingIssuesReferences": []}
json.dump(base, open(os.path.join(d, "pr-4.json"), "w"))
json.dump([{"number": 4, "isDraft": False, "labels": [], "title": "fix: something",
            "body": "No ticket for this one.", "closingIssuesReferences": []},
           {"number": 5, "isDraft": False, "labels": [], "title": "feat: add f",
            "body": "Adds f.\n\nCloses #7", "closingIssuesReferences": []}],
          open(os.path.join(d, "pr-list.json"), "w"))
PY
reset_state
out="$(REVIEW_MAX_CONCURRENT=1 "$DISPATCH" --sweep 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-4" "cap=1: the first unbound PR is dispatched"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "cap=1: the second PR is not spawned this tick"
assert_contains "$out" "#5: review cap reached (1 live) — queued for a later tick" "the queued PR is reported by name"
# a live reviewer seeded at cap: NOTHING new spawns, and the queue message names both
reset_state
seed_reviewer working
echo '[{"id": "cafe9999", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working"}]' > "$MOCK_DIR/agents.json"
out="$(REVIEW_MAX_CONCURRENT=1 "$DISPATCH" --sweep 2>&1)" || true
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "at cap with a live reviewer, no new spawn"
assert_contains "$out" "#4: review cap reached (1 live) — queued for a later tick" "the other PR queues behind the live reviewer"
# a stale-boot meta is a dead session, not a slot: parked-ticket metas are
# never finalized (board-answer wake targets), so a reboot's leftovers would
# otherwise hold the cap closed forever (observed: 8 dead metas, 0 spawns).
reset_state
python3 - <<'PY'
import json, os
json.dump({"uuid": "dead0000-0000-4000-8000-000000000000",
           "current": "dead0000-0000-4000-8000-000000000000",
           "name": "review-pr-9", "status": "working",
           "host": os.uname().nodename, "boot_id": "boot-stale",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "dead0000-0000-4000-8000-000000000000.json"), "w"))
PY
out="$(REVIEW_MAX_CONCURRENT=1 "$DISPATCH" --sweep 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-4" "a stale-boot working meta does not hold a cap slot"
: > "$SPAWN_LOG"
# premature-idle metas hold a slot; genuinely finished idle metas do not.
# The no-wait spawn can record idle at BIRTH (fast poll) with an empty
# reply while the review is just starting — observed sailing 12 spawns
# past cap 8. A real finish has a substantive finalize-written reply.
reset_state
python3 - <<'PY'
import json, os
home = os.environ["DAEMON_HOME"]
def meta(uuid, name, reply):
    json.dump({"uuid": uuid, "current": uuid, "name": name, "status": "idle",
               "updated": "2026-07-08T00:00:00Z"},
              open(os.path.join(home, uuid + ".json"), "w"))
    if reply is not None:
        open(os.path.join(home, uuid + ".reply.txt"), "w").write(reply)
meta("beb10000-0000-4000-8000-000000000000", "review-pr-8", "")            # premature: empty reply
meta("beb20000-0000-4000-8000-000000000000", "review-pr-9", "x" * 400)     # finished: substantive reply
PY
out="$(REVIEW_MAX_CONCURRENT=1 "$DISPATCH" --sweep 2>&1)" || true
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "a premature-idle (empty-reply) meta holds the cap slot"
assert_contains "$out" "review cap reached (1 live)" "the pass reports the held slot"
reset_state
python3 - <<'PY'
import json, os
home = os.environ["DAEMON_HOME"]
json.dump({"uuid": "beb20000-0000-4000-8000-000000000000", "current": "beb20000-0000-4000-8000-000000000000",
           "name": "review-pr-9", "status": "idle", "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(home, "beb20000-0000-4000-8000-000000000000.json"), "w"))
open(os.path.join(home, "beb20000-0000-4000-8000-000000000000.reply.txt"), "w").write("x" * 400)
PY
out="$(REVIEW_MAX_CONCURRENT=1 "$DISPATCH" --sweep 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-4" "a finished idle meta (substantive reply) frees its slot"
: > "$SPAWN_LOG"
# triggered dispatch bypasses the cap (explicit event)
out="$(REVIEW_MAX_CONCURRENT=0 "$DISPATCH" 4 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-4" "triggered dispatch is never gated by the cap"
# restore the canonical pr list for later sections
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]
json.dump([{"number": 5, "isDraft": False, "labels": [], "title": "feat: add f",
            "body": "Adds f.\n\nCloses #7", "closingIssuesReferences": []},
           {"number": 6, "isDraft": True, "labels": [], "title": "wip",
            "body": "", "closingIssuesReferences": []}],
          open(os.path.join(d, "pr-list.json"), "w"))
PY

# ---- sweep skips a PR whose primary ticket is parked ----------------------------
# A prior reviewer parked the ticket on the human; every tick would otherwise
# spawn a reviewer that board-bind refuses (observed live: PR #574 / #548).
# Triggered dispatch still proceeds — resolving the park is the operator's call.
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d["labels"] = [{"name": "status:needs-human"}]
json.dump(d, open(p, "w"))'
out="$("$DISPATCH" --sweep)"
assert_contains "$out" "primary ticket #7 is parked needs-human" "sweep names the park it skips"
# ...and the park's own reviewer meta is LEFT INTACT: board-answer relays to
# that bound session, so retiring it would break the wake path the park's
# note promises. (Verified: board-answer accepts needs-human parks ONLY — it
# dies by name on needs-info / interactive-preferred — so needs-human is the
# whole set of parks with a session-resume path to protect.)
assert_contains "$out" "the park's wake target" "the sweep says why it leaves the reviewer meta alone"
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:" "a parked ticket's resumable reviewer is not retired"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "sweep spawns no reviewer over a parked ticket"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "triggered dispatch still proceeds over the park"
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d.pop("labels", None)
json.dump(d, open(p, "w"))'

# ---- a CONFLICT ticket never binds a reviewer ----------------------------------
# Two or more status labels is `conflict` by _board.py's own definition, and
# reading only the first position let `in-review` + `needs-human` pass as
# in-review — binding a reviewer to an unrepaired ticket whose park says a
# human is waiting.
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p))
d["labels"] = [{"name": "status:in-review"}, {"name": "status:needs-human"}]
json.dump(d, open(p, "w"))'
OUT_CONFLICT="$("$DISPATCH" --sweep)"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "a ticket carrying two status labels binds no reviewer"
assert_contains "$OUT_CONFLICT" "multiple status labels" "the sweep names the conflict rather than a puzzling not-in-review"
assert_contains "$OUT_CONFLICT" "repair it" "and points at the repair"
# single-label in-review is unchanged: it dispatches
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d["labels"] = [{"name": "status:in-review"}]
json.dump(d, open(p, "w"))'
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "a single status:in-review label still dispatches"
# zero labels keeps the deliberate fail-open
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d.pop("labels", None)
json.dump(d, open(p, "w"))'
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "an untracked ticket still fails open, as before"
# ...but a CLOSED linked ticket is not untracked, it is FINISHED. A done or
# wontfix write closes the issue AND strips its status label, so a
# labels-only lookup said nothing and run_for read that silence as
# "in-review" — a reviewer spawned onto a terminal ticket. State is what
# distinguishes the two zero-label cases.
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d.pop("labels", None); d["state"] = "CLOSED"
json.dump(d, open(p, "w"))'
out="$("$DISPATCH" --sweep)"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "a CLOSED primary ticket binds no reviewer"
assert_contains "$out" "primary ticket #7 is CLOSED" "the sweep names the terminal ticket it skips"
# A lookup that FAILS is still fail-open — an API blip or a malformed
# response must not stall review. Only a lookup that SUCCEEDS and reports a
# terminal ticket is stale.
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d["labels"] = "not-a-list"
json.dump(d, open(p, "w"))'
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "a malformed status lookup still fails open"
# leave the fixture as the blocks below expect it: OPEN, no labels
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d.pop("labels", None); d["state"] = "OPEN"
json.dump(d, open(p, "w"))'

# ---- sweep skips a PR whose primary ticket has left in-review (any route) -------
# Finding 2 (independent review, E1 lane-split dispatch fix): a reviewer only
# makes sense while its ticket is in-review — this generalizes past
# ready-for-architect specifically. Two distinct non-review states are
# exercised: ready-for-architect (the actual RE-REVIEW escalation route) and
# in-progress (an unrelated state, proving the gate is general — not
# hardcoded to one label).
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d["labels"] = [{"name": "status:ready-for-architect"}]
json.dump(d, open(p, "w"))'
out="$("$DISPATCH" --sweep)"
assert_contains "$out" "primary ticket #7 is parked (status:ready-for-architect)" "sweep names the ready-for-architect park it skips"
assert_contains "$out" "resumes when the ticket returns to in-review" "ready-for-architect skip message states its own resume path"
assert_not_contains "$out" "the review resumes via board-answer" "ready-for-architect skip message is not the board-answer wording"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep spawns no reviewer over a ready-for-architect park"

reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d["labels"] = [{"name": "status:in-progress"}]
json.dump(d, open(p, "w"))'
out="$("$DISPATCH" --sweep)"
assert_contains "$out" "primary ticket #7 is parked (status:in-progress)" "sweep also skips a ticket at an UNRELATED non-review state (rule is general, not ready-for-architect-specific)"
assert_contains "$out" "resumes when the ticket returns to in-review" "in-progress skip message resumes on its own too (not a board-answer park)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep spawns no reviewer over an in-progress ticket"

# ---- Finding 1: the DISPATCHER (not the dying worker) retires a stale reviewer --
# The independent review caught a real defect in the original self-retire fix:
# daemon-retire.sh calls `claude stop` BEFORE writing status=retired, so a
# worker asking to stop itself most likely never reaches that write — the
# meta would finalize idle instead, which is EXACTLY the state that strands
# it forever. The corrected mechanism retires from the sweep instead: once
# the ticket has left in-review, a FINISHED (idle) reviewer meta for that PR
# is retired right here, before it can ever reach _decide's permanent
# sweep-mode "skip finished reviewer" wall.
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d["labels"] = [{"name": "status:ready-for-architect"}]
json.dump(d, open(p, "w"))'
seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "done"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" --sweep)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "the dispatcher retires the finished reviewer once its ticket has left in-review"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:" "no new reviewer spawns while the ticket is still parked"

# ...and never touches a reviewer that is still genuinely ACTIVE — it owns
# its own exit (the still-running worker's own turn, free to keep running
# fix waves after an early PROTOCOL BLOCKER park, must never be interrupted
# by the sweep).
reset_state
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d["labels"] = [{"name": "status:ready-for-architect"}]
json.dump(d, open(p, "w"))'
seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "working"}]' > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" --sweep)"
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:" "an ACTIVE reviewer is never retired, even when its ticket has left in-review"
assert_contains "$out" "still-active reviewer owns its own exit" "sweep names why it left the active reviewer alone"

# ---- the ticket's return to in-review dispatches a fresh reviewer, unattended --
# Simulates the state the retire above actually produces (unlike self-retire,
# daemon-retire.sh here runs from the dispatcher against an ALREADY-finished
# session, so `claude stop` is a harmless no-op and the status=retired write
# always lands). The moment the ticket returns to in-review, that SAME
# registry entry must hit the pre-existing "none / retired -> dispatch" row
# with no special-case dispatch logic needed — no human step in between.
reset_state; seed_reviewer retired
N=7 python3 -c 'import json,os
p = os.environ["MOCK_DIR"] + "/issue-" + os.environ["N"] + ".json"
d = json.load(open(p)); d.pop("labels", None)
json.dump(d, open(p, "w"))'
out="$("$DISPATCH" --sweep)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "the ticket's return to in-review dispatches a fresh reviewer, unattended"

# ---- sweep retries an engine-unavailable reviewer -------------------------------
reset_state
U="feed0000-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-09T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
printf 'trail posted; engine down after 3 attempts.\nENGINE-UNAVAILABLE\n' \
  > "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "sweep retires an ENGINE-UNAVAILABLE reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep re-dispatches the PR after the outage"

# ---- sweep still skips a normally-finished reviewer ------------------------------
reset_state
U="feed0000-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-09T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
printf 'review complete; merged.\n' \
  > "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep still skips a finished reviewer without the marker"

# ---- sweep outage cap ------------------------------------------------------------
# A persistent engine outage must not make the cron sweep respawn forever:
# after 3 CONSECUTIVE ENGINE-UNAVAILABLE reviewers for one PR, the sweep
# skips it. An explicit PR event (triggered mode) always re-dispatches.
echo "sweep outage cap:"
seed_outage_metas() {  # $1 = how many consecutive outage reviewers to seed
  local i
  for f in "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; do rm -f "$f"; done
  for i in $(seq 1 "$1"); do
    U="feed000$i-0000-4000-8000-000000000000" I="$i" python3 - <<'PY'
import json, os
u = os.environ["U"]; i = os.environ["I"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-0%sT00:00:00Z" % i},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
    printf 'trail posted; engine down.\nENGINE-UNAVAILABLE\n' \
      > "$DAEMON_HOME/feed000$i-0000-4000-8000-000000000000.reply.txt"
  done
}
reset_state
seed_outage_metas 2
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep still respawns below the outage cap (2 consecutive)"
reset_state
seed_outage_metas 3
OUT_CAP="$("$DISPATCH" --sweep 2>&1 || true)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep skips a PR at the outage cap (3 consecutive)"
assert_contains "$OUT_CAP" "outage" "sweep names the outage cap as the skip reason"
: > "$SPAWN_LOG"
OUT_EVT="$("$DISPATCH" 5 2>&1 || true)"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "an explicit PR event ignores the outage cap"
[ -s "$SPAWN_LOG" ] || echo "    dispatch said: $OUT_EVT"

# ---- sweep retries a dead worker (terminal error, no reply marker) ---------------
# A worker that dies BEFORE it can speak — e.g. the gateway refuses its very
# first turn — finalizes status=error with an EMPTY reply: no assistant
# message exists to carry ENGINE-UNAVAILABLE. The sweep must treat terminal
# worker errors as retryable (same 3-consecutive cap), or a gateway outage
# parks the PR out of the sweep until an explicit event.
echo "sweep dead-worker retry:"
reset_state; seed_reviewer error
printf '\n' > "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "sweep retires an errored worker whose reply is empty"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep re-dispatches after a dead worker"

# one-harness lifecycle: an unfinalized worker whose SESSION errored is
# finalized to status=error by the sweep itself, then retried in the same pass.
reset_state; seed_reviewer working
echo '[{"id": "feedcafe", "sessionId": "feed0000-0000-4000-8000-000000000000", "state": "error"}]' > "$MOCK_DIR/agents.json"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_file_exists "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt" "sweep finalized the errored session through daemon-finalize (reply recorded)"
assert_contains "$(cat "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.json")" '"retired_from": "failure"' "and its retirement is stamped as a FAILURE one, so the streak can still see it"
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep finalizes an errored session and re-dispatches in the same pass"

# dead workers share the outage cap: 3 consecutive errored reviewers (empty
# replies — the marker never existed) stop the sweep respawning.
seed_error_metas() {  # $1 = how many consecutive errored reviewers to seed
  local i
  for f in "$DAEMON_HOME"/*.json "$DAEMON_HOME"/*.reply.txt; do rm -f "$f"; done
  for i in $(seq 1 "$1"); do
    U="feed000$i-0000-4000-8000-000000000000" I="$i" python3 - <<'PY'
import json, os
u = os.environ["U"]; i = os.environ["I"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5",
           "status": "error", "updated": "2026-07-0%sT00:00:00Z" % i},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
    printf '\n' > "$DAEMON_HOME/feed000$i-0000-4000-8000-000000000000.reply.txt"
  done
}
reset_state
seed_error_metas 2
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "review-pr-5" "sweep still respawns below the cap (2 consecutive dead workers)"
reset_state
seed_error_metas 3
OUT_DEAD="$("$DISPATCH" --sweep 2>&1 || true)"
assert_equals "$(cat "$SPAWN_LOG")" "" "sweep skips a PR after 3 consecutive dead workers"
assert_contains "$OUT_DEAD" "3 consecutive" "sweep names the failure cap as the skip reason"

# marker outages and dead workers form ONE streak — interleaving them must
# not reset the count.
reset_state
seed_error_metas 2
U="feed0003-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-03T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
printf 'trail posted; engine down.\nENGINE-UNAVAILABLE\n' \
  > "$DAEMON_HOME/feed0003-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_equals "$(cat "$SPAWN_LOG")" "" "marker outages and dead workers count as one 3-streak"

# ---- no linked issue ------------------------------------------------------------
echo "no linked issue:"
reset_state
out="$("$DISPATCH" 9)"
PROMPT9="$(cat "$PROMPT_DIR/review-pr-9.prompt")"
assert_contains "$PROMPT9" '`ISSUE_NUMBER`: none' "no-issue PR binds ticket=none"
assert_contains "$PROMPT9" '`ISSUE_LIST`: none' "no-issue PR binds an empty issue list"

# ---- stale worktree replaced -----------------------------------------------------
echo "stale worktree:"
reset_state
mkdir -p "$WT"; echo junk > "$WT/junk.txt"
out="$("$DISPATCH" 5)"
assert_equals "$(git -C "$WT" rev-parse HEAD)" "$HEAD_SHA" "stale worktree dir replaced with a fresh checkout"

# ---- live worktree guard (defense-in-depth on top of dedupe) ------------------
# A live daemon can occupy $WT even when the DAEMON_HOME registry has no
# record of it (e.g. a non-review daemon, or a registry that was cleared).
# The registry-only dedupe check would say "dispatch"; the cwd-based guard
# must refuse anyway rather than force-removing a worktree a live process is
# sitting in.
echo "live worktree guard:"
reset_state
out="$("$DISPATCH" 5)"                                     # real dispatch: (re)creates $WT
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "setup: worktree created via a real dispatch"
reset_state                                                  # clears registry → dedupe alone would say "dispatch"
echo "[{\"id\": \"live0001\", \"sessionId\": \"live0001-0000-4000-8000-000000000000\", \"cwd\": \"$WT\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "occupied worktree refuses removal"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn when the worktree is occupied by a live daemon"
if [ -d "$WT" ]; then pass "worktree still exists after the refused dispatch"; else
    fail "worktree still exists after the refused dispatch"; fi
reset_state

# A session restored from a foreign state volume can still be visible in the
# local dashboard, but its foreign registry identity must not occupy the worktree.
U="foreign1-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "other-daemon", "engine": "claude",
           "cwd": os.environ["WT"], "host": "old-host", "boot_id": "boot-old",
           "status": "working", "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"foreign1\", \"sessionId\": \"foreign1-0000-4000-8000-000000000000\", \"cwd\": \"$WT\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host Claude session does not occupy the worktree"
assert_not_contains "$out" "live daemon occupies" "foreign-host Claude session does not block removal"
reset_state

# A MANAGED local session whose turn is over (lingering shape: state=working,
# status=idle — finished daemons stay listed) must NOT occupy the worktree:
# retire + respawn deliberately reuses that path.
U="linger01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "claude",
           "cwd": os.environ["WT"], "status": "retired",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"linger01\", \"sessionId\": \"linger01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"working\", \"status\": \"idle\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "a finished lingering session frees the worktree for re-dispatch"
assert_not_contains "$out" "live daemon occupies" "finished lingering session does not block worktree removal"
reset_state

# The observed post-retire shape (2026-07-19 live board, PR #574): the
# retired reviewer's row lingers state=stopped with NO status field, so the
# idle escape never matches — only the meta's `retired` status can free the
# worktree.
U="retire01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "claude",
           "cwd": os.environ["WT"], "status": "retired",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"retire01\", \"sessionId\": \"retire01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"stopped\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "a retired reviewer's statusless stopped row frees the worktree"
assert_not_contains "$out" "live daemon occupies" "retired meta overrides the statusless stopped row"
reset_state

# ...but a PARKED worker's stopped row (meta NOT retired — its worktree is
# the resume context) must still occupy.
U="parked01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "other-daemon", "engine": "claude",
           "cwd": os.environ["WT"], "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"parked01\", \"sessionId\": \"parked01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"stopped\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "a parked (non-retired) stopped session still occupies the worktree"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn over a parked session's worktree"
reset_state

# ...while a managed local session that is genuinely mid-turn (status=busy)
# still occupies it.
U="linger01-0000-4000-8000-000000000000" WT="$WT" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "other-daemon", "engine": "claude",
           "cwd": os.environ["WT"], "status": "working",
           "updated": "2026-07-08T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo "[{\"id\": \"linger01\", \"sessionId\": \"linger01-0000-4000-8000-000000000000\", \"cwd\": \"$WT\", \"state\": \"working\", \"status\": \"busy\"}]" \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "busy managed session still occupies the worktree"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn over a busy session's worktree"
reset_state

# ---- sweep failure isolation ----------------------------------------------------
echo "sweep failure isolation:"
# PR 4 (earlier in the sweep order) fails mid-dispatch; PR 5 must still be
# dispatched afterward, and the failure must be surfaced rather than
# silently swallowed or left to abort the rest of the pass.
#
# NOTE on how the failure is injected: dispatch_one runs inside
# `run_for ... || echo ...`, and bash suspends `errexit` for the *entire*
# call subtree of a command guarded by `||`. That USED to mean a gh/git
# failure deep inside dispatch_one could go unreported — it no longer does:
# every gh/git step that can fail (git fetch, gh pr view, worktree add, ...)
# is now explicitly guarded inline (`... || { echo "#$pr: <step> failed" >&2;
# return 1; }`), so those failures surface as their own observable per-PR
# error today — see the "dispatch guards" section below, which pins exactly
# that (`#3: gh pr view failed`, reaching the sweep's reporter). This section
# instead simulates a SPAWN-time failure (e.g. a daemon registry write
# conflict) for review-pr-4 specifically, via the stub's FAIL_SPAWN_FOR hook:
# `daemon-spawn.sh` is dispatch_one's actual *last* command, so its failure
# is the one that exercises the sweep's own `|| echo "dispatch error"`
# loop-isolation reporter directly, distinct from the per-step gh/git guards
# already covered elsewhere in this file.
#
# pr-list.json is overwritten so PR 4 sorts BEFORE PR 5 (which must still be
# dispatched). Safe to mutate here: no later test in this file depends on
# the original pr-list.json contents.
SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHA"]
def pr(n, **kw):
    base = {"number": n, "title": "fix: something", "body": "No ticket for this one.",
            "baseRefName": "main", "headRefName": "feat/x", "headRefOid": sha,
            "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": False,
            "state": "OPEN", "labels": [], "closingIssuesReferences": []}
    base.update(kw)
    json.dump(base, open(os.path.join(d, "pr-%d.json" % n), "w"))
pr(4)
json.dump([{"number": 4, "isDraft": False, "labels": [], "title": "fix: something",
            "body": "No ticket for this one.", "closingIssuesReferences": []},
           {"number": 5, "isDraft": False, "labels": [], "title": "feat: add f",
            "body": "Adds f.\n\nCloses #7", "closingIssuesReferences": []}],
          open(os.path.join(d, "pr-list.json"), "w"))
PY
reset_state
out="$(FAIL_SPAWN_FOR="review-pr-4" "$DISPATCH" --sweep 2>&1)" || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "sweep still dispatches PR 5 after PR 4 (earlier) fails mid-dispatch"
assert_contains "$out" "#4: dispatch error (continuing sweep)" "sweep surfaces PR 4's dispatch failure instead of swallowing it"

# ---- dispatch_one step guards (nounset loop kill / stale-state contamination) ----
echo "dispatch guards:"
# With the sweep's `|| echo` reporter suspending errexit through the whole
# dispatch_one call, mid-function failures need explicit per-step guards.
# Two concrete consequences are pinned here (both reproduced pre-fix):
#  (a) FIRST-PR gh failure: eval of the failed parse left PR_STATE unbound
#      and `set -u` (NOT suspended by ||) killed the loop subshell —
#      starvation again, on a narrower trigger.
#  (b) contamination: a gh failure AFTER a successful iteration left the
#      previous PR's eval'd vars (HEAD_SHA/HEAD_REF/PR_STATE...) in place —
#      the bad PR was dispatched anyway, with a worktree at the WRONG PR's
#      SHA and an EMPTY prompt (the render failed silently).
# PR 3 has NO canned pr-3.json, so the mock `gh pr view 3` exits nonzero.

# (a) first-PR failure: [bad(3), good(5)] — loop must survive and report
python3 - <<'PY'
import json, os
json.dump([{"number": 3, "isDraft": False, "labels": [], "title": "",
            "body": "", "closingIssuesReferences": []},
           {"number": 5, "isDraft": False, "labels": [], "title": "feat: add f",
            "body": "Adds f.\n\nCloses #7", "closingIssuesReferences": []}],
          open(os.path.join(os.environ["MOCK_DIR"], "pr-list.json"), "w"))
PY
reset_state
out="$("$DISPATCH" --sweep 2>&1)" || true
assert_contains "$out" "#3: gh pr view failed" "first-PR gh failure surfaced as a per-step error"
assert_contains "$out" "#3: dispatch error (continuing sweep)" "first-PR gh failure reaches the sweep reporter"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "loop survives a first-PR gh failure (no nounset kill)"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-3" "failing first PR is not spawned"

# (b) contamination: [good-A(5), bad(3), good-B(4)] — good-B on its OWN
# branch feat/y with a distinct SHA, so a stale-state dispatch is detectable
git -C "$CLONE" checkout -q -b feat/y main
echo yo > "$CLONE/g.txt"
git -C "$CLONE" add g.txt
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -m feat2 -q
git -C "$CLONE" push -q -u origin feat/y
HEAD_SHA2="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
SHA2="$HEAD_SHA2" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha2 = os.environ["SHA2"]
json.dump({"number": 4, "title": "feat: add g", "body": "No ticket for this one.",
           "baseRefName": "main", "headRefName": "feat/y", "headRefOid": sha2,
           "url": "https://github.com/test/repo/pull/4", "isDraft": False,
           "state": "OPEN", "labels": [], "closingIssuesReferences": []},
          open(os.path.join(d, "pr-4.json"), "w"))
json.dump([{"number": 5, "isDraft": False, "labels": [], "title": "feat: add f",
            "body": "Adds f.\n\nCloses #7", "closingIssuesReferences": []},
           {"number": 3, "isDraft": False, "labels": [], "title": "",
            "body": "", "closingIssuesReferences": []},
           {"number": 4, "isDraft": False, "labels": [], "title": "feat: add g",
            "body": "No ticket for this one.", "closingIssuesReferences": []}],
          open(os.path.join(d, "pr-list.json"), "w"))
PY
reset_state
rm -f "$PROMPT_DIR/review-pr-3.prompt"
out="$("$DISPATCH" --sweep 2>&1)" || true
assert_not_contains "$(cat "$SPAWN_LOG")" "review-pr-3" "bad PR after a good one is never spawned (no stale-state dispatch)"
if [ -f "$PROMPT_DIR/review-pr-3.prompt" ]; then
    fail "no prompt rendered for the bad PR"; else pass "no prompt rendered for the bad PR"; fi
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-4" "good-B after the bad PR still dispatched"
assert_equals "$(git -C "$LOCAL_REPO/.claude/worktrees/review-pr-4" rev-parse HEAD)" "$HEAD_SHA2" "good-B worktree at its OWN head SHA, not the previous PR's"

# ---- risk-surface manifest (read from BASE, not HEAD) + rollout flags ----------
echo "risk manifest + rollout flags:"
# Commit a manifest to main (the base) with a distinctive marker, then a
# DIFFERENT version on the PR head branch. The prompt must carry the BASE
# version and never the HEAD version — a PR cannot weaken its own gate.
git -C "$CLONE" checkout -q main
mkdir -p "$CLONE/.doperpowers"
printf 'RISK-FROM-BASE\nlib/auth.ts\n' > "$CLONE/.doperpowers/risk-surfaces.md"
printf '## Validation\nFACTS-FROM-BASE: npm test\n' > "$CLONE/.doperpowers/repo-facts.md"
git -C "$CLONE" add .doperpowers
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m "add manifests"
git -C "$CLONE" push -q origin main
git -C "$CLONE" checkout -q -b feat/z main
printf 'RISK-FROM-HEAD-SHOULD-NOT-APPEAR\n' > "$CLONE/.doperpowers/risk-surfaces.md"
printf 'FACTS-FROM-HEAD-SHOULD-NOT-APPEAR\n' > "$CLONE/.doperpowers/repo-facts.md"
git -C "$CLONE" add .doperpowers
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m "sneak manifest edit"
git -C "$CLONE" push -q origin feat/z
HEAD_SHA_Z="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
SHAZ="$HEAD_SHA_Z" python3 - <<'PY'
import json, os
d = os.environ["MOCK_DIR"]; sha = os.environ["SHAZ"]
json.dump({"number": 10, "title": "feat: z", "body": "No ticket for this one.",
           "baseRefName": "main", "headRefName": "feat/z", "headRefOid": sha,
           "url": "https://github.com/test/repo/pull/10", "isDraft": False,
           "state": "OPEN", "labels": [], "closingIssuesReferences": []},
          open(os.path.join(d, "pr-10.json"), "w"))
PY
reset_state
out="$(AUTO_MERGE_ENABLED=true DEFAULT_BRANCH=develop "$DISPATCH" 10)"
P10="$(cat "$PROMPT_DIR/review-pr-10.prompt")"
assert_contains "$P10" "RISK-FROM-BASE" "manifest content injected from the BASE ref"
assert_not_contains "$P10" "RISK-FROM-HEAD-SHOULD-NOT-APPEAR" "HEAD-side manifest edit does not leak (read from base, not head)"
assert_contains "$P10" "FACTS-FROM-BASE" "repo-facts content injected from the BASE ref"
assert_not_contains "$P10" "FACTS-FROM-HEAD-SHOULD-NOT-APPEAR" "HEAD-side repo-facts edit does not leak (read from base, not head)"
assert_contains "$P10" '`AUTO_MERGE`: on' "AUTO_MERGE_ENABLED=true binds auto-merge on"

# ---- engine switch (label → WORKER_ENGINE → claude) + codex liveness -----------
# Canned PR on feat/x (labels overridable) + a thin wrapper over $DISPATCH, so
# an env-var prefix (e.g. `WORKER_ENGINE=codex run_dispatch 41`) reaches the
# script for exactly one call.
gh_pr() {  # $1=number $2=state $3=isDraft(0|1) $4=labels (comma-separated, "" for none)
    N="$1" STATE="$2" DRAFT="$3" LABELS="$4" SHA="$HEAD_SHA" python3 - <<'PY'
import json, os
n = int(os.environ["N"])
labels = [{"name": l} for l in os.environ["LABELS"].split(",") if l]
d = {"number": n, "title": "feat: add f", "body": "Adds f.\n\nCloses #7",
     "baseRefName": "main", "headRefName": "feat/x", "headRefOid": os.environ["SHA"],
     "url": "https://github.com/test/repo/pull/%d" % n, "isDraft": os.environ["DRAFT"] == "1",
     "state": os.environ["STATE"], "labels": labels, "closingIssuesReferences": []}
json.dump(d, open(os.path.join(os.environ["MOCK_DIR"], "pr-%d.json" % n), "w"))
PY
}
run_dispatch() { "$DISPATCH" "$@"; }

echo "engine switch (one harness, two model routes):"
reset_state
: > "$SPAWN_LOG"
gh_pr 41 OPEN 0 ""                                  # helper: canned PR, no labels
WORKER_ENGINE=codex run_dispatch 41
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-41" "WORKER_ENGINE=codex spawns the one-harness daemon"
assert_not_contains "$(cat "$SPAWN_LOG")" "codex-spawn:" "codex-CLI worker species is retired from dispatch"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=$HOME/.claude/clodex-settings.json;effort=xhigh" "gateway route rides DAEMON_CLAUDE_SETTINGS/EFFORT"
prompt="$(cat "$PROMPT_DIR/review-pr-41.prompt")"
assert_contains "$prompt" "review-engine.sh" "prompt binds the engine script path"
assert_contains "$prompt" '`BASE_REF`: main' "prompt binds the base ref the engine call uses"
assert_not_contains "$prompt" "--criteria" "criteria concept is gone from the rendered prompt"
assert_not_contains "$prompt" "developer_instructions" "no developer instructions ride the rendered prompt"
assert_not_contains "$prompt" "{{ENGINE_BLOCK}}" "engine block placeholder rendered"
assert_not_contains "$prompt" "CODEX_COMPANION" "companion is gone from the prompt"

: > "$SPAWN_LOG"
gh_pr 42 OPEN 0 "engine:claude"
WORKER_ENGINE=codex run_dispatch 42
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-42" "engine:claude label overrides env"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=;effort=high" "claude route spawns without the gateway settings, at effort high"
if grep -E ' opus$' "$SPAWN_LOG" > /dev/null; then
    pass "claude route pins the QAgent model to opus"
else
    fail "claude route pins the QAgent model to opus"
fi
prompt42="$(cat "$PROMPT_DIR/review-pr-42.prompt")"
assert_contains "$prompt42" "scripts/review-engine.sh" "claude route binds the same single engine (no per-route fork)"

: > "$SPAWN_LOG"
gh_pr 43 OPEN 0 "engine:claude"
# The clearing has to be an ASSIGNMENT, not an omission: this dispatcher can
# itself be running inside a gateway-routed daemon whose environment exports
# these, daemon-spawn would inherit them AND persist them into the registry
# meta, and every later resume of this reviewer would ride the gateway while
# the log said claude.
DAEMON_CLAUDE_SETTINGS="$HOME/.claude/ambient-gateway.json" DAEMON_CLAUDE_EFFORT=xhigh \
    run_dispatch 43
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=;effort=high" "an ambient gateway settings/effort pair is cleared on the claude route"
assert_not_contains "$(cat "$SPAWN_LOG")" "ambient-gateway.json" "the ambient gateway settings file never reaches the spawned reviewer"

# The built-in default (no label, no WORKER_ENGINE in the environment) is the
# plain-Claude route — the clodex gateway is opt-in only.
: > "$SPAWN_LOG"
gh_pr 44 OPEN 0 ""
env -u WORKER_ENGINE "$DISPATCH" 44
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-44" "unlabelled PR with no WORKER_ENGINE still dispatches"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=;effort=high" "built-in default route is plain Claude (no gateway settings) at effort high"
if grep -E ' opus$' "$SPAWN_LOG" > /dev/null; then
    pass "built-in default pins the QAgent model to opus"
else
    fail "built-in default pins the QAgent model to opus"
fi

echo "codex reviewer liveness in dedupe:"
sleep 300 & LIVEPID=$!
python3 - "$DAEMON_HOME" "$LIVEPID" <<'PY'
import json, sys
json.dump({"uuid": "cdec9999-0000-4000-8000-000000000000", "current": "cdec9999-0000-4000-8000-000000000000",
           "name": "review-pr-43", "engine": "codex", "pid": str(sys.argv[2]),
           "status": "working", "updated": "2026-07-10T00:00:00Z"},
          open(sys.argv[1] + "/cdec9999-0000-4000-8000-000000000000.json", "w"))
PY
gh_pr 43 OPEN 0 ""
out="$(WORKER_ENGINE=codex run_dispatch 43)"
assert_contains "$out" "skip active reviewer" "live codex pid dedupes"
kill "$LIVEPID" 2>/dev/null; wait "$LIVEPID" 2>/dev/null || true
: > "$SPAWN_LOG"
out="$(WORKER_ENGINE=codex run_dispatch 43)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-43" "dead codex pid retires + respawns (via the one-harness spawn)"

# ---- _wt_occupied codex-registry scan (worktree-removal guard, not dedupe) -----
# The "live worktree guard" section above pins _wt_occupied's FIRST branch (a
# `claude agents` cwd hit). Codex workers never appear in `claude agents`, so
# the function falls through to a registry scan that must count a worktree as
# occupied ONLY when a meta has ALL of: engine == "codex", cwd == the target
# worktree, status in (working, blocked), and a live pid. This section
# targets that scan directly, observed the same way as the claude-path guard:
# through dispatch_one's "live daemon occupies" refusal and whether a spawn
# happens — not by calling _wt_occupied as an internal. These dispatches use
# the suite's default WORKER_ENGINE=claude (unqualified "$DISPATCH" 5) since
# what's under test is the engine field of the meta SITTING in the worktree,
# not which engine this dispatch itself would spawn as.
echo "live worktree guard (codex registry scan):"
reset_state
out="$("$DISPATCH" 5)"                                     # setup: (re)creates $WT via a real dispatch
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "setup: worktree created via a real dispatch"
reset_state                                                  # clears registry + agents.json ([] by reset_state)

# (a) live codex-engine meta, same cwd, status working → OCCUPIED, blocked
sleep 300 & WTPID=$!
WT="$WT" PID="$WTPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8001-0000-4000-8000-000000000000",
           "current": "cdec8001-0000-4000-8000-000000000000",
           "name": "occupant", "engine": "codex", "cwd": os.environ["WT"],
           "pid": os.environ["PID"], "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8001-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5 2>&1)" || true
assert_contains "$out" "live daemon occupies" "live codex-engine meta (same cwd, live pid) blocks worktree removal"
assert_equals "$(cat "$SPAWN_LOG")" "" "no spawn while a live codex worker occupies the worktree"
if [ -d "$WT" ]; then pass "worktree still exists after the refused dispatch"; else
    fail "worktree still exists after the refused dispatch"; fi
kill "$WTPID" 2>/dev/null; wait "$WTPID" 2>/dev/null || true

# (b) same shape of meta, but the pid is now dead → NOT occupied, dispatch proceeds
WT="$WT" PID="$WTPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8001-0000-4000-8000-000000000000",
           "current": "cdec8001-0000-4000-8000-000000000000",
           "name": "occupant", "engine": "codex", "cwd": os.environ["WT"],
           "pid": os.environ["PID"], "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8001-0000-4000-8000-000000000000.json"), "w"))
PY
: > "$SPAWN_LOG"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "dead codex pid in the registry does not block removal — dispatch proceeds"

# (c) guard: a STALE claude-engine "working" meta in this SAME cwd must NOT
# block removal either. This pins the fail-open behavior the task required
# to preserve: the codex-registry scan filters on engine == "codex", so a
# non-codex (or missing-engine) meta is skipped outright regardless of cwd,
# status, or pid — it never reaches the pid-liveness check at all.
reset_state
WT="$WT" python3 - <<'PY'
import json, os
json.dump({"uuid": "aaaa9001-0000-4000-8000-000000000000",
           "current": "aaaa9001-0000-4000-8000-000000000000",
           "name": "stale-claude-occupant", "engine": "claude", "cwd": os.environ["WT"],
           "status": "working", "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "aaaa9001-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "stale claude-engine meta in the same cwd does not block removal (fail-open preserved)"
reset_state

# (d) host-aware: a codex meta whose pid is live HERE but was recorded on
# another host (registry migrated on a state volume) is NOT an occupant —
# the process did not migrate, only its number did.
sleep 300 & WTPID=$!
WT="$WT" PID="$WTPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8002-0000-4000-8000-000000000000",
           "current": "cdec8002-0000-4000-8000-000000000000",
           "name": "occupant", "engine": "codex", "cwd": os.environ["WT"],
           "pid": os.environ["PID"], "host": "old-host", "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8002-0000-4000-8000-000000000000.json"), "w"))
PY
: > "$SPAWN_LOG"
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host codex pid does not block removal — dispatch proceeds"
kill "$WTPID" 2>/dev/null; wait "$WTPID" 2>/dev/null || true
reset_state

# ---- dedupe is host-aware too ---------------------------------------------------
# A working codex reviewer meta whose live-here pid carries a foreign host must
# read as DEAD in _decide: respawn, not "skip active reviewer".
echo "dedupe (host-aware):"
sleep 300 & DEDUPID=$!
PID="$DEDUPID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8003-0000-4000-8000-000000000000",
           "current": "cdec8003-0000-4000-8000-000000000000",
           "name": "review-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": "old-host", "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8003-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:cdec8003" "foreign-host live pid → reviewer treated as dead and retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "foreign-host live pid → respawned"
reset_state
# A rebuilt host can keep its hostname while getting a fresh pid namespace.
PID="$DEDUPID" H="$(hostname)" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8003-0000-4000-8000-000000000000",
           "current": "cdec8003-0000-4000-8000-000000000000",
           "name": "review-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": os.environ["H"], "boot_id": "boot-old",
           "status": "working", "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8003-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$(cat "$SPAWN_LOG")" "retire:cdec8003" "prior-boot live pid → reviewer treated as dead and retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "prior-boot live pid → respawned"
reset_state
# control: same live pid, HOST MATCHING this machine → still a live occupant
PID="$DEDUPID" H="$(hostname)" B="$DAEMON_BOOT_ID" python3 - <<'PY'
import json, os
json.dump({"uuid": "cdec8003-0000-4000-8000-000000000000",
           "current": "cdec8003-0000-4000-8000-000000000000",
           "name": "review-pr-5", "engine": "codex",
           "pid": os.environ["PID"], "host": os.environ["H"], "boot_id": os.environ["B"], "status": "working",
           "updated": "2026-07-10T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], "cdec8003-0000-4000-8000-000000000000.json"), "w"))
PY
out="$("$DISPATCH" 5)"
assert_contains "$out" "active reviewer" "same-host live pid still skips as active"
assert_equals "$(cat "$SPAWN_LOG")" "" "same-host live pid spawns nothing"
kill "$DEDUPID" 2>/dev/null; wait "$DEDUPID" 2>/dev/null || true
reset_state

# ---- E2 scale review: in-review recomposition epics carry no PR -----------------
# A recomposition epic reaches in-review with a CLOSURE PACKAGE in its `pr:`
# meta (a comment URL) and no GitHub PR at all — its children are already
# merged — so the open-PR loop above can never see it. The sweep lists such
# epics off the board and dispatches the scale variant, `review-epic-<n>`.
#
# This is the first case in this file that reads the board, and the two
# harness pieces it needs are wired at the top: `_board.py` copied beside the
# stub board-bind.sh, and the mock `gh` serving the snapshot GraphQL query
# from $MOCK_DIR/board-issues.json (absent for every earlier case, which
# therefore sweeps an empty board).
echo "scale review (recomposition epics):"
reset_state
echo "[]" > "$MOCK_DIR/pr-list.json"       # the PR half of the sweep is empty here
PKG="https://github.com/test/repo/issues/20#issuecomment-99"
PKG="$PKG" python3 - <<'PY'
import json, os
def meta(k, v):
    return "\n\n<!-- board:meta\n%s: %s\n-->\n" % (k, v)
def it(n, status, body, parent=None, closed=False):
    return {"number": n, "state": "CLOSED" if closed else "OPEN",
            "labels": [] if closed else ["status:" + status],
            "body": body, "parent": parent}
issues = [
    # #20: the epic — in-review, closure package in `pr:`, both children terminal
    it(20, "in-review", "Epic acceptance." + meta("pr", os.environ["PKG"])),
    # #21: a LEAF in-review whose `pr:` is a real PR — never a scale review
    it(21, "in-review", "Leaf." + meta("pr", "https://github.com/test/repo/pull/5")),
    # #22 carries a merged PR in its `pr:` meta. Squash/rebase merges rewrite
    # commits and delete the branch, so its head SHA is an ancestor of nothing
    # on main — the dispatcher has to fetch refs/pull/<n>/head or the
    # reviewer cannot detach at the range the closure package names.
    it(22, "done", "child a" + meta("pr", "https://github.com/test/repo/pull/41"),
       parent=20, closed=True),
    it(23, "done", "child b", parent=20, closed=True),
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
# The epic's outgoing owner: the Architect that assembled the closure package.
# Its claude-species meta lingers status=working after its turn ends, and the
# real board-bind.sh refuses to rebind a ticket owned by an ACTIVE daemon —
# so the dispatch must finalize it first (2026-07-18 shakedown) or every
# scale reviewer would bind-fail and be retired.
python3 - <<'PY'
import json, os
u = "arch0001-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "20-recompose-epic", "role": "ARCHITECT",
           "ticket": "20", "status": "working", "updated": "2026-08-01T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "arch0001", "sessionId": "arch0001-0000-4000-8000-000000000000", "state": "done"}]' \
    > "$MOCK_DIR/agents.json"
out="$("$DISPATCH" --sweep 2>&1)"
assert_contains "$(cat "$DAEMON_HOME/arch0001-0000-4000-8000-000000000000.json")" '"status": "idle"' \
    "the epic's lingering Architect owner is finalized before the scale reviewer binds"
assert_contains "$out" "review-epic-20" "sweep dispatches a scale reviewer onto the in-review epic"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "scale reviewer spawns under the review-epic-<n> registry name"
assert_not_contains "$(cat "$SPAWN_LOG")" "review-epic-21" "an in-review LEAF is never scale-reviewed (PRs drive leaves)"
EPIC_PROMPT="$(cat "$PROMPT_DIR/review-epic-20.prompt")"
assert_contains "$EPIC_PROMPT" '`REVIEW_MODE`: scale' "reviewer prompt carries the scale-review mode"
assert_contains "$EPIC_PROMPT" "\`CLOSURE_PACKAGE\`: $PKG" "prompt binds the closure package as the entry artifact"
assert_contains "$EPIC_PROMPT" '`ISSUE_NUMBER`: 20' "prompt binds the epic ticket under review"
assert_contains "$EPIC_PROMPT" "SCALE REVIEWER of recomposition epic #20" "scale prompt opens as the epic's reviewer, not a PR reviewer"
assert_not_contains "$EPIC_PROMPT" "PR_NUMBER" "scale prompt carries no PR framing at all (there is no PR)"
assert_not_contains "$EPIC_PROMPT" "HEAD_SHA" "scale prompt carries no PR-head bindings"
assert_contains "$EPIC_PROMPT" '`BASE_REF`: main' "scale prompt binds the engine base (the branch the epic integrates into)"
assert_contains "$EPIC_PROMPT" '`WORKER_NAME`: review-epic-20' "scale prompt binds the registry identity the startup barrier verifies"
# The value side, on the scale call site too: the hard-fail sees a missing
# binding, never an empty-valued one, and this lane has its own P_* block.
assert_bound "$EPIC_PROMPT" BIND_READY_FILE scale
assert_bound "$EPIC_PROMPT" IMPLEMENT_PROTOCOL_FILE scale
assert_bound "$EPIC_PROMPT" BOARD_SCRIPTS scale
# This epic has no `branch:` meta, so the worktree sits on the default branch
# itself — there is no aggregate range to hand the engine, and the prompt must
# say so instead of leaving the worker to review nothing.
assert_contains "$EPIC_PROMPT" "NO aggregate branch range" "the missing-integration-branch case names the closure package's PR ranges as the review ranges"
assert_not_contains "$EPIC_PROMPT" "{{" "no unsubstituted placeholder survives the scale render"
assert_not_contains "$EPIC_PROMPT" "<!-- mode:" "mode blocks are resolved at render, never shipped to the worker"
EPIC_META="$(python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    m = json.load(open(p))
    if m.get("name") == "review-epic-20": print(p); break
PY
)"
assert_contains "$(cat "$EPIC_META")" '"ticket": "20"' "scale reviewer owns the epic ticket (board-answer can reach it)"
assert_equals "$(git -C "$LOCAL_REPO/.claude/worktrees/review-epic-20" rev-parse HEAD)" \
    "$(git -C "$LOCAL_REPO" rev-parse origin/main)" "scale worktree is detached at the integration base ref"
# U3: the children's PR heads are fetched by ref, not assumed reachable.
assert_contains "$(cat "$GIT_CALL_LOG")" "fetch -q origin refs/pull/41/head" \
    "the dispatcher fetches each merged child's pull head into the shared object store"
# ...and a pull ref that will not fetch is the REVIEWER's finding, not a
# reason to refuse the review. This mock origin has no refs/pull/* at all, so
# the fetch above genuinely failed — and the reviewer still went out.
assert_contains "$out" "refs/pull/41/head is unfetchable" \
    "an unfetchable pull head is logged"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" \
    "...and the scale review is dispatched anyway"

# A live scale reviewer dedupes the next sweep — same registry machinery the
# PR path uses, keyed review-epic-<n>.
python3 - <<'PY' > "$MOCK_DIR/agents.json"
import glob, json, os
rows = []
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    m = json.load(open(p))
    if m.get("name") == "review-epic-20":
        rows.append({"id": "epic0001", "sessionId": m["current"],
                     "state": "working", "status": "busy"})
print(json.dumps(rows))
PY
: > "$SPAWN_LOG"
out2="$("$DISPATCH" --sweep 2>&1)"
assert_equals "$(cat "$SPAWN_LOG")" "" "second sweep dedupes the live epic reviewer"
assert_contains "$out2" "active reviewer" "second sweep names the live scale reviewer it skipped"

# The reviewer finishes its turn. Its meta stays on file with a terminal
# status — nothing ever retires it (the stale-ticket retirement in run_for is
# PR-only, and an out-of-review epic is not even listed here) — so the
# closure package it was dispatched against is the ONLY thing that can tell
# a superseded reviewer from a current one. Same package ⇒ still skip: a
# completed review must not be respawned every tick.
python3 - <<'PY'
import glob, json, os
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    m = json.load(open(p))
    if m.get("name") == "review-epic-20":
        m["status"] = "idle"
        json.dump(m, open(p, "w"), indent=2)
PY
echo "[]" > "$MOCK_DIR/agents.json"
: > "$SPAWN_LOG"
out4="$("$DISPATCH" --sweep 2>&1)"
assert_equals "$(cat "$SPAWN_LOG")" "" "a finished scale reviewer is not respawned while the closure package is unchanged"
assert_contains "$out4" "skip finished reviewer" "sweep names the finished-reviewer skip"

# ...but a SECOND recomposition cycle must dispatch a second reviewer: the
# corrective child landed, the Architect pinned a NEW closure package, and
# the epic returned to in-review. Without the package comparison every cycle
# after the first would strand on that same "skip finished reviewer" verdict.
PKG2="https://github.com/test/repo/issues/20#issuecomment-200"
PKG2="$PKG2" python3 - <<'PY'
import json, os
p = os.path.join(os.environ["MOCK_DIR"], "board-issues.json")
issues = json.load(open(p))
for it in issues:
    if it["number"] == 20:
        it["body"] = "Epic acceptance.\n\n<!-- board:meta\npr: %s\n-->\n" % os.environ["PKG2"]
json.dump(issues, open(p, "w"))
PY
: > "$SPAWN_LOG"
out5="$("$DISPATCH" --sweep 2>&1)"
assert_contains "$out5" "new closure package, new recomposition cycle" "sweep names the superseded reviewer it retired"
assert_contains "$(cat "$SPAWN_LOG")" "retire:" "the superseded reviewer's terminal meta is retired"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "the second recomposition cycle dispatches a fresh scale reviewer"
assert_contains "$(cat "$PROMPT_DIR/review-epic-20.prompt")" "$PKG2" "the second reviewer is bound to the NEW closure package"

# An epic that has LEFT in-review for good (its verdict closed it) is no
# longer listed at all — no reviewer follows it.
reset_state
python3 - <<'PY'
import json, os
p = os.path.join(os.environ["MOCK_DIR"], "board-issues.json")
issues = json.load(open(p))
for it in issues:
    if it["number"] == 20:
        it["state"], it["labels"] = "CLOSED", []
json.dump(issues, open(p, "w"))
PY
out6="$("$DISPATCH" --sweep 2>&1)"
assert_not_contains "$out6" "review-epic-20" "a closed (recomposed) epic is never scale-reviewed again"
assert_equals "$(cat "$SPAWN_LOG")" "" "a closed epic spawns nothing"

# ---- the engine's review range is the epic's AGGREGATE diff --------------------
# The worktree sits at the epic's integration branch (its `branch:` meta), but
# the engine's base must be what that branch merges INTO — the default branch.
# Binding BASE_REF to the integration branch itself, which the worktree is
# already checked out at, made `--base origin/{{BASE_REF}}` review
# merge-base(X,X)..X: nothing at all.
reset_state
git -C "$CLONE" checkout -q -b epic/integration main
echo aggregate > "$CLONE/agg.txt"
git -C "$CLONE" add agg.txt
git -C "$CLONE" -c user.email=t@t -c user.name=t commit -q -m "epic children, merged"
git -C "$CLONE" push -q -u origin epic/integration
INT_SHA="$(git -C "$CLONE" rev-parse HEAD)"
git -C "$CLONE" checkout -q main
PKG="$PKG" python3 - <<'PY'
import json, os
def it(n, status, body, parent=None, closed=False):
    return {"number": n, "state": "CLOSED" if closed else "OPEN",
            "labels": [] if closed else ["status:" + status],
            "body": body, "parent": parent}
meta = "\n\n<!-- board:meta\nbranch: epic/integration\npr: %s\n-->\n" % os.environ["PKG"]
issues = [
    it(20, "in-review", "Epic acceptance." + meta),
    it(22, "done", "child a", parent=20, closed=True),
    it(23, "done", "child b", parent=20, closed=True),
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
out7="$("$DISPATCH" --sweep 2>&1)"
assert_contains "$out7" "review-epic-20" "the sweep reports the scale dispatch it made"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "an epic with an integration branch dispatches its scale reviewer"
assert_equals "$(git -C "$LOCAL_REPO/.claude/worktrees/review-epic-20" rev-parse HEAD)" "$INT_SHA" \
    "the scale worktree sits at the epic's integration-branch head"
INT_PROMPT="$(cat "$PROMPT_DIR/review-epic-20.prompt")"
assert_contains "$INT_PROMPT" '`BASE_REF`: main' "the engine base is the default branch, not the epic's own branch"
assert_not_contains "$INT_PROMPT" '`BASE_REF`: epic/integration' "the engine never reviews the integration branch against itself"
assert_contains "$INT_PROMPT" '`INTEGRATION_REF`: epic/integration' "the prompt names the integration branch the worktree sits at"
assert_contains "$INT_PROMPT" "aggregate review range" "the prompt states the aggregate range the engine's --base gives it"

# ...and the NEXT cycle must not ride that branch. The recomposition return
# clears `branch:` with `pr:` (both describe a composition that just changed),
# so an epic whose new closure package arrives without --branch has no
# integration ref at all — even though the previous cycle recorded one. The
# fixture below is exactly what recompose_epics + a --branch-less in-review
# entry leave behind.
reset_state
PKG2="$PKG2" python3 - <<'PY'
import json, os
p = os.path.join(os.environ["MOCK_DIR"], "board-issues.json")
issues = json.load(open(p))
for it in issues:
    if it["number"] == 20:
        it["body"] = "Epic acceptance.\n\n<!-- board:meta\npr: %s\n-->\n" % os.environ["PKG2"]
json.dump(issues, open(p, "w"))
PY
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "the next cycle still dispatches its scale reviewer"
assert_equals "$(git -C "$LOCAL_REPO/.claude/worktrees/review-epic-20" rev-parse HEAD)" \
    "$(git -C "$LOCAL_REPO" rev-parse origin/main)" \
    "with no branch: of its own it falls back to the default branch, not the previous cycle's integration ref"
NEXT_PROMPT="$(cat "$PROMPT_DIR/review-epic-20.prompt")"
assert_contains "$NEXT_PROMPT" "NO aggregate branch range" "and the prompt says so instead of implying a range it does not have"
assert_not_contains "$NEXT_PROMPT" '`INTEGRATION_REF`: epic/integration' "no trace of the cleared integration ref reaches the worker"

# ---- scale review honors the epic's engine:* label ----------------------------
# Scale review is a QAgent route, and per-ticket engine overrides apply to
# every QAgent route — the X4 exemption covers ARCHITECT dispatch alone, where
# plan authorship is deliberately never label-routed. The epic's label was
# ignored and the environment always won.
echo "scale review engine label:"
reset_state
echo "[]" > "$MOCK_DIR/pr-list.json"
PKG2="https://github.com/test/repo/issues/30#issuecomment-77"
PKG2="$PKG2" python3 - <<'PY'
import json, os
def meta(k, v):
    return "\n\n<!-- board:meta\n%s: %s\n-->\n" % (k, v)
issues = [
    {"number": 30, "state": "OPEN",
     "labels": ["status:in-review", "engine:claude"],
     "body": "Epic acceptance." + meta("pr", os.environ["PKG2"]), "parent": None},
    {"number": 31, "state": "CLOSED", "labels": [], "body": "child", "parent": 30},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
: > "$SPAWN_LOG"
out="$(WORKER_ENGINE=codex "$DISPATCH" --sweep 2>&1)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-30" "the labelled epic gets its scale reviewer"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=;effort=high" "engine:claude on the EPIC routes its scale review through the claude harness at effort high"
# ...and an unlabelled epic still takes the environment default (the gateway
# route), which is what the block above already exercised on #20.
reset_state
echo "[]" > "$MOCK_DIR/pr-list.json"
PKG2="$PKG2" python3 - <<'PY'
import json, os
def meta(k, v):
    return "\n\n<!-- board:meta\n%s: %s\n-->\n" % (k, v)
issues = [
    {"number": 30, "state": "OPEN", "labels": ["status:in-review"],
     "body": "Epic acceptance." + meta("pr", os.environ["PKG2"]), "parent": None},
    {"number": 31, "state": "CLOSED", "labels": [], "body": "child", "parent": 30},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
: > "$SPAWN_LOG"
out="$(WORKER_ENGINE=codex "$DISPATCH" --sweep 2>&1)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn-env:settings=$HOME/.claude/clodex-settings.json;effort=xhigh" "an unlabelled epic keeps the environment default"

# ---- the scale selector needs a closure package, not any pr: value ------------
# A LEAF that opened a real PR and later gained children reaches
# recomposition-ready while still in-review with a /pull/ URL in `pr:` —
# nothing cleared it (only the recomposition return clears `pr`, and a merge
# auto-close never runs it). Handing that PR to a scale reviewer as its
# closure package is the wrong artifact; the PR loop owns real PRs.
echo "scale selector artifact check:"
reset_state
python3 - <<'PY'
import json, os
issues = [
    {"number": 20, "state": "OPEN", "labels": ["status:in-review"],
     "body": "Grew children after its own PR."
             "\n\n<!-- board:meta\npr: https://github.com/test/repo/pull/7\n-->\n",
     "parent": None},
    {"number": 22, "state": "CLOSED", "labels": [], "body": "child a", "parent": 20},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
OUT_ART="$("$DISPATCH" --sweep 2>&1 || true)"
assert_equals "$(cat "$SPAWN_LOG")" "" "a recomposition-ready parent whose pr: is a real PR gets no scale reviewer"
assert_contains "$OUT_ART" "not a closure package" "the sweep says why it skipped it"
assert_contains "$OUT_ART" "https://github.com/test/repo/pull/7" "and names the artifact it refused to review"

# ---- an in-review epic is a scale target only when recomposition is due -------
# A leaf that gained children AFTER opening a real PR is in-review with a `pr:`
# meta too — dispatching a scale reviewer there puts a second reviewer on the
# wrong artifact.
reset_state
python3 - <<'PY'
import json, os
p = os.path.join(os.environ["MOCK_DIR"], "board-issues.json")
issues = json.load(open(p))
issues.append({"number": 24, "state": "OPEN", "labels": ["status:in-progress"],
               "body": "late corrective child", "parent": 20})
json.dump(issues, open(p, "w"))
PY
out8="$("$DISPATCH" --sweep 2>&1)"
assert_not_contains "$out8" "review-epic-20" "an in-review epic with a live child is not a scale target"
assert_equals "$(cat "$SPAWN_LOG")" "" "no scale reviewer spawns while recomposition is not due"

# ---- the gone-integration-branch fallback still fetches the default branch ----
# When the `branch:` meta names a branch that is already deleted (the normal
# shape once the children merge), the fallback collapses int_ref onto the
# default branch — which makes the int_ref != base_ref fetch below it a no-op.
# Everything downstream then comes from whatever origin/<default> the local
# clone last saw: the worktree, both manifests, and the merged per-child head
# SHAs the closure package names — in exactly the mode whose prompt sends the
# worker at those per-child ranges. Advance origin/main from a SECOND clone so
# this clone's remote-tracking ref is genuinely stale, and the worktree head
# proves whether the fallback fetched.
reset_state
OTHER="$TEST_ROOT/other"
rm -rf "$OTHER"
git clone -q "$ORIGIN" "$OTHER" 2>/dev/null
# the bare origin's HEAD is still the unborn branch git init made, so the
# fresh clone lands with no local main — take it from the remote ref.
git -C "$OTHER" checkout -q -B main origin/main
echo "merged child work" > "$OTHER/merged.txt"
git -C "$OTHER" add merged.txt
git -C "$OTHER" -c user.email=t@t -c user.name=t commit -q -m "children merged into main"
git -C "$OTHER" push -q origin main
FRESH_MAIN="$(git -C "$OTHER" rev-parse HEAD)"
STALE_MAIN="$(git -C "$LOCAL_REPO" rev-parse origin/main)"
if [ "$STALE_MAIN" != "$FRESH_MAIN" ]; then
    pass "the local clone's origin/main starts out stale (the condition under test)"
else
    fail "the local clone's origin/main starts out stale (the condition under test)"
fi
PKG="$PKG" python3 - <<'PY'
import json, os
meta = "\n\n<!-- board:meta\nbranch: epic/already-deleted\npr: %s\n-->\n" % os.environ["PKG"]
issues = [
    {"number": 20, "state": "OPEN", "labels": ["status:in-review"],
     "body": "Epic acceptance." + meta, "parent": None},
    {"number": 22, "state": "CLOSED", "labels": [], "body": "child a", "parent": 20},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
out9="$("$DISPATCH" --sweep 2>&1)"
assert_contains "$out9" "integration branch 'epic/already-deleted' is gone" "the deleted integration branch is reported, not fatal"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "the fallback still dispatches a scale reviewer"
assert_equals "$(git -C "$LOCAL_REPO" rev-parse origin/main)" "$FRESH_MAIN" \
    "the fallback fetches the default branch instead of trusting a stale local ref"
assert_equals "$(git -C "$LOCAL_REPO/.claude/worktrees/review-epic-20" rev-parse HEAD)" "$FRESH_MAIN" \
    "the fallback worktree sits at the FRESH default-branch head (where the merged children are)"
GONE_PROMPT="$(cat "$PROMPT_DIR/review-epic-20.prompt")"
assert_contains "$GONE_PROMPT" "NO aggregate branch range" "the fallback prompt still routes the worker to the package's per-child ranges"

# ---- a capped scale review escalates to the human instead of stranding --------
# The 3-consecutive-failure cap is permanent on the PR path because an
# explicit PR event can always re-dispatch. Scale reviews are sweep-only, so
# a transient engine outage would skip the epic forever: same closure
# package, same cap, every tick. At the cap the sweep retires the failed
# reviewer and parks the epic needs-human; answering returns it to in-review
# and the next sweep dispatches fresh.
echo "scale review outage escalation:"
reset_state
PKG="$PKG" python3 - <<'PY'
import json, os
meta = "\n\n<!-- board:meta\npr: %s\n-->\n" % os.environ["PKG"]
issues = [
    {"number": 20, "state": "OPEN", "labels": ["status:in-review"],
     "body": "Epic acceptance." + meta, "parent": None},
    {"number": 22, "state": "CLOSED", "labels": [], "body": "child a", "parent": 20},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
# three consecutive ENGINE-UNAVAILABLE reviewers, all stamped with the
# CURRENT closure package (so the superseded-reviewer path cannot fire and
# quietly re-dispatch for the wrong reason)
PKG="$PKG" python3 - <<'PY'
import json, os
for i in (1, 2, 3):
    u = "feed000%d-0000-4000-8000-000000000000" % i
    json.dump({"uuid": u, "current": u, "name": "review-epic-20", "engine": "codex",
               "status": "idle", "closure_package": os.environ["PKG"],
               "updated": "2026-07-0%dT00:00:00Z" % i},
              open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
    with open(os.path.join(os.environ["DAEMON_HOME"], u + ".reply.txt"), "w") as f:
        f.write("trail posted; engine down.\nENGINE-UNAVAILABLE\n")
PY
OUT_CAPEPIC="$("$DISPATCH" --sweep 2>&1 || true)"
CAP_LOG="$(cat "$SPAWN_LOG")"
assert_contains "$CAP_LOG" "retire:feed0003" "the capped scale review retires its latest failed reviewer"
assert_contains "$CAP_LOG" "board-transition:20 needs-human" "the capped scale review parks the epic on the human"
# The note must carry the RECIPE: this park has no resumable session (the
# reviewer was just retired) and board-answer refuses a dead bound session by
# design, so "answer it" alone points at a path that dies.
assert_contains "$CAP_LOG" "no session to resume" "the park note says why answering alone will not work"
assert_contains "$CAP_LOG" "board-transition.sh 20 in-review" "the park note names the exact command that returns the epic"
assert_not_contains "$CAP_LOG" "spawn:--no-wait review-epic-20" "the capped epic spawns no fourth reviewer"
assert_contains "$OUT_CAPEPIC" "parked needs-human" "the sweep reports the escalation it performed"

# the human answers: the epic returns to in-review (its pre-park target) and
# the retired metas are gone — the next sweep dispatches fresh, with no
# special-case return logic anywhere.
reset_state
rm -f "$DAEMON_HOME"/*.reply.txt
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "the answered epic gets a fresh scale reviewer on the next sweep"
assert_not_contains "$(cat "$SPAWN_LOG")" "board-transition:20 needs-human" "a fresh dispatch does not re-park the epic"

# ---- dead-worker cycles must reach the scale cap ------------------------------
# A reviewer that dies pre-reply finalizes `error`; the respawn retires it, and
# daemon-retire overwrites that status with `retired` — erasing the only
# evidence _outage_streak had. The streak reset every tick, the cap was
# unreachable, and the sweep respawned a doomed reviewer forever, so F4's
# escalation could never fire for exactly the failure class it exists for.
# Failure retirements are stamped now; supersessions are not.
echo "scale cap via dead-worker cycles:"
reset_state
PKG="$PKG" python3 - <<'PY'
import json, os
meta = "\n\n<!-- board:meta\npr: %s\n-->\n" % os.environ["PKG"]
issues = [
    {"number": 20, "state": "OPEN", "labels": ["status:in-review"],
     "body": "Epic acceptance." + meta, "parent": None},
    {"number": 22, "state": "CLOSED", "labels": [], "body": "child a", "parent": 20},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
# every live review-epic-20 session reports state=error, so each cycle is a
# dead worker: finalize error → respawn → retire (stamped) → fresh spawn
fail_all_epic_reviewers() {
    python3 - <<'PY' > "$MOCK_DIR/agents.json"
import glob, json, os
rows = []
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    if m.get("name") == "review-epic-20" and m.get("status") == "working":
        rows.append({"id": "e", "sessionId": m["current"], "state": "error"})
print(json.dumps(rows))
PY
}
"$DISPATCH" --sweep >/dev/null 2>&1 || true      # cycle 0: first reviewer spawns
CAP_SPAWNS=0
for _cycle in 1 2 3; do
    fail_all_epic_reviewers
    : > "$SPAWN_LOG"
    OUT_CYCLE="$("$DISPATCH" --sweep 2>&1 || true)"
    grep -q 'spawn:--no-wait review-epic-20' "$SPAWN_LOG" && CAP_SPAWNS=$((CAP_SPAWNS + 1))
done
assert_equals "$CAP_SPAWNS" "2" "the third dead-worker cycle stops respawning (2 retries, then the cap)"
assert_contains "$OUT_CYCLE" "parked needs-human" "and the capped epic escalates to the human instead of looping forever"
assert_contains "$(cat "$SPAWN_LOG")" "board-transition:20 needs-human" "the park goes through the board, as F4 defined it"

# A SUPERSEDED retirement is not a failure and must break the streak, or a
# long-lived epic would accumulate its way to a false cap.
reset_state
PKG="$PKG" python3 - <<'PY'
import json, os
home = os.environ["DAEMON_HOME"]
def meta(uuid, status, updated, retired_from=None):
    m = {"uuid": uuid, "current": uuid, "name": "review-epic-20",
         "status": status, "updated": updated}
    if retired_from:
        m["retired_from"] = retired_from
    json.dump(m, open(os.path.join(home, uuid + ".json"), "w"), indent=2)
    open(os.path.join(home, uuid + ".reply.txt"), "w").write("\n")
meta("aaa10001-0000-4000-8000-000000000000", "retired", "2026-07-01T00:00:00Z", "failure")
meta("aaa10002-0000-4000-8000-000000000000", "retired", "2026-07-02T00:00:00Z")   # superseded
meta("aaa10003-0000-4000-8000-000000000000", "retired", "2026-07-03T00:00:00Z", "failure")
meta("aaa10004-0000-4000-8000-000000000000", "error",   "2026-07-04T00:00:00Z")
PY
OUT_SUPER="$("$DISPATCH" --sweep 2>&1 || true)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "an unstamped (superseded) retirement breaks the streak — no false cap"
assert_not_contains "$OUT_SUPER" "parked needs-human" "so the epic is not escalated on a streak it never had"

# ---- a triggered re-review is not a failure ------------------------------------
# Triggered mode respawns a CLEANLY finished reviewer on every explicit PR
# event. Stamping those retirements as failures (L2 stamped the whole respawn
# path) meant two ordinary re-reviews plus one real outage reached the
# 3-consecutive cap and parked a healthy PR.
echo "triggered re-review carries no failure stamp:"
reset_state
U="feed0000-0000-4000-8000-000000000000" python3 - <<'PY'
import json, os
u = os.environ["U"]
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "engine": "codex",
           "status": "idle", "updated": "2026-07-09T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
printf 'review complete; merged.\n' \
  > "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.reply.txt"
"$DISPATCH" 5 >/dev/null 2>&1 || true
assert_contains "$(cat "$SPAWN_LOG")" "retire:feed0000" "the clean reviewer is still replaced on an explicit event"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-pr-5" "and the fresh one dispatches"
assert_not_contains "$(cat "$DAEMON_HOME/feed0000-0000-4000-8000-000000000000.json")" "retired_from" \
    "but its retirement carries NO failure stamp — a re-review must not advance the streak"

# ---- a reviewer whose PR left the open listing ---------------------------------
# The sweep enumerates OPEN PRs, so once a reviewer routes its ticket off
# in-review and the PR closes, nothing finalizes the lingering meta and
# execute-dispatch skips the now-eligible ticket forever. Same deadlock G1
# fixed on the epic side, same registry-driven cleanup.
echo "stale PR-reviewer retirement:"
reset_state
echo "[]" > "$MOCK_DIR/pr-list.json"          # PR #5 is no longer open
# ...and absence from the listing is only a CANDIDATE: the cleanup verifies
# each one directly, so the fixture has to say the PR really closed.
python3 -c 'import json,os; p=os.environ["MOCK_DIR"]+"/pr-5.json"; d=json.load(open(p)); d["state"]="CLOSED"; json.dump(d,open(p,"w"))'
python3 - <<'PY'
import json, os
issues = [{"number": 7, "state": "OPEN", "labels": ["status:ready-for-architect"],
           "body": "the ticket its reviewer bounced", "parent": None}]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
python3 - <<'PY'
import json, os
u = "c10ded01-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "ticket": "7",
           "status": "working", "updated": "2026-08-01T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "c10ded01", "sessionId": "c10ded01-0000-4000-8000-000000000000", "state": "done"}]' \
    > "$MOCK_DIR/agents.json"
OUT_CLOSEDPR="$("$DISPATCH" --sweep 2>&1 || true)"
assert_file_exists "$DAEMON_HOME/c10ded01-0000-4000-8000-000000000000.reply.txt" \
    "the reviewer of a closed PR is finalized"
assert_contains "$(cat "$SPAWN_LOG")" "retire:c10ded01" "and retired, releasing the ticket it still owned"
assert_contains "$OUT_CLOSEDPR" "PR #5 is CLOSED, no longer open" "the sweep names why, with the state it verified"
assert_not_contains "$(cat "$DAEMON_HOME/c10ded01-0000-4000-8000-000000000000.json")" "retired_from" \
    "an orphaned-work retirement is not a failure — it must not feed the streak"

# Absence from the listing is not proof of closure. The listing is capped at
# 100 and has a failure fallback, so a transient gh failure once read as
# "every PR closed" and would retire completed dedupe records wholesale —
# duplicate reviews on the next healthy sweep.
echo "cleanup needs a healthy, complete listing:"
reset_state
python3 - <<'PY'
import json, os
issues = [{"number": 7, "state": "OPEN", "labels": ["status:ready-for-architect"],
           "body": "the ticket its reviewer bounced", "parent": None}]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
u = "c10ded03-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "ticket": "7",
           "status": "working", "updated": "2026-08-01T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "c10ded03", "sessionId": "c10ded03-0000-4000-8000-000000000000", "state": "done"}]' \
    > "$MOCK_DIR/agents.json"
OUT_LISTFAIL="$(MOCK_PR_LIST_FAILS=1 "$DISPATCH" --sweep 2>&1 || true)"
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:c10ded03" "a failed listing retires nothing"
assert_contains "$OUT_LISTFAIL" "absence is not evidence when the listing is unhealthy" "and the sweep says why it cleaned nothing"

# a candidate absent from the (healthy) listing but actually OPEN — the
# 100-cap case — survives, costing only its verification call
: > "$SPAWN_LOG"
echo "[]" > "$MOCK_DIR/pr-list.json"
python3 -c 'import json,os; p=os.environ["MOCK_DIR"]+"/pr-5.json"; d=json.load(open(p)); d["state"]="OPEN"; json.dump(d,open(p,"w"))'
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:c10ded03" "a candidate that is still OPEN is left alone (the 100-cap costs calls, not correctness)"

# a candidate the API will not answer for is left alone too, and says so
: > "$SPAWN_LOG"
python3 - <<'PY'
import json, os
d = os.environ["DAEMON_HOME"]
u = "c10ded04-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-pr-404", "ticket": "7",
           "status": "working", "updated": "2026-08-01T00:00:00Z"},
          open(os.path.join(d, u + ".json"), "w"))
PY
OUT_UNVERIF="$("$DISPATCH" --sweep 2>&1 || true)"
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:c10ded04" "an unverifiable candidate is not retired on a guess"
assert_contains "$OUT_UNVERIF" "cannot confirm PR #404 is closed" "and the sweep names it"
rm -f "$DAEMON_HOME/c10ded04-0000-4000-8000-000000000000.json"

# ...but a PARKED ticket keeps its reviewer, closed PR or not (M2's rule).
reset_state
python3 - <<'PY'
import json, os
issues = [{"number": 7, "state": "OPEN", "labels": ["status:needs-human"],
           "body": "parked on the human", "parent": None}]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
u = "c10ded02-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-pr-5", "ticket": "7",
           "status": "working", "updated": "2026-08-01T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "c10ded02", "sessionId": "c10ded02-0000-4000-8000-000000000000", "state": "done"}]' \
    > "$MOCK_DIR/agents.json"
"$DISPATCH" --sweep >/dev/null 2>&1 || true
assert_not_contains "$(cat "$SPAWN_LOG")" "retire:c10ded02" "a parked ticket's reviewer survives even when its PR is gone"
echo "[]" > "$MOCK_DIR/agents.json"
rm -f "$MOCK_DIR/board-issues.json"
# the PR half stays empty from here on, as the scale-review blocks below expect
# ---- a scale reviewer whose epic left in-review gets finalized + retired ------
# The in-review listing above cannot see this reviewer (its epic moved on when
# a defect became a corrective child), and board-sweep's pass_cancel skips
# review-epic-* metas on purpose — so nothing else would ever finalize it, and
# its lingering `working` meta keeps OWNING the ticket against implement
# dispatch. Mirrors run_for's off-review retirement on the epic side.
echo "stale scale reviewer retirement:"
reset_state
python3 - <<'PY'
import json, os
issues = [
    {"number": 20, "state": "OPEN", "labels": ["status:in-progress"],
     "body": "Epic acceptance — a corrective child is running.", "parent": None},
    {"number": 24, "state": "OPEN", "labels": ["status:in-progress"],
     "body": "corrective child", "parent": 20},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
python3 - <<'PY'
import json, os
u = "dead0001-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-epic-20", "ticket": "20",
           "status": "working", "updated": "2026-08-01T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "dead0001", "sessionId": "dead0001-0000-4000-8000-000000000000", "state": "done"}]' \
    > "$MOCK_DIR/agents.json"
OUT_STALE="$("$DISPATCH" --sweep 2>&1 || true)"
assert_file_exists "$DAEMON_HOME/dead0001-0000-4000-8000-000000000000.reply.txt" \
    "the finished reviewer of an out-of-review epic is finalized (reply recorded)"
assert_not_contains "$(cat "$DAEMON_HOME/dead0001-0000-4000-8000-000000000000.json")" "retired_from" \
    "a stale-ticket retirement is NOT a failure — it must break the streak, not extend it"
assert_contains "$(cat "$SPAWN_LOG")" "retire:dead0001" "and retired, releasing the ticket it still owned"
assert_contains "$OUT_STALE" "the epic has left in-review" "the sweep names why it retired the reviewer"
assert_not_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "an out-of-review epic is never re-dispatched by this pass"

# a LIVE reviewer owns its own exit — the same rule everywhere else
reset_state
python3 - <<'PY'
import json, os
u = "live0001-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "review-epic-20", "ticket": "20",
           "status": "working", "updated": "2026-08-01T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY
echo '[{"id": "live0001", "sessionId": "live0001-0000-4000-8000-000000000000", "state": "working", "status": "busy"}]' \
    > "$MOCK_DIR/agents.json"
OUT_LIVE="$("$DISPATCH" --sweep 2>&1 || true)"
assert_equals "$(cat "$SPAWN_LOG")" "" "a live reviewer on an out-of-review epic is left completely alone"
assert_contains "$OUT_LIVE" "owns its own exit" "the sweep says why it left the live reviewer alone"
assert_contains "$(cat "$DAEMON_HOME/live0001-0000-4000-8000-000000000000.json")" '"status": "working"' \
    "the live reviewer's meta is not finalized out from under it"
echo "[]" > "$MOCK_DIR/agents.json"

# ---- the scale listing survives a SELF-RESOLVED BOARD_REPO --------------------
# _board.repo() reads the ENVIRONMENT. When the caller supplies no BOARD_REPO
# the script resolves one itself — and that assignment used to be a plain
# shell variable, so every scale epic died "BOARD_REPO is unset" inside the
# python subprocess and vanished silently. board-sweep exports it and masks
# the miss; the documented direct invocation does not.
echo "scale listing with a self-resolved BOARD_REPO:"
reset_state
PKG="$PKG" python3 - <<'PY'
import json, os
meta = "\n\n<!-- board:meta\npr: %s\n-->\n" % os.environ["PKG"]
issues = [
    {"number": 20, "state": "OPEN", "labels": ["status:in-review"],
     "body": "Epic acceptance." + meta, "parent": None},
    {"number": 22, "state": "CLOSED", "labels": [], "body": "child a", "parent": 20},
]
json.dump(issues, open(os.path.join(os.environ["MOCK_DIR"], "board-issues.json"), "w"))
PY
OUT_UNEXP="$(env -u BOARD_REPO "$DISPATCH" --sweep 2>&1 || true)"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait review-epic-20" "the scale listing still finds its epic when the script resolved BOARD_REPO itself"
assert_not_contains "$OUT_UNEXP" "BOARD_REPO is unset" "no scale subprocess dies for want of BOARD_REPO in its environment"

rm -f "$MOCK_DIR/board-issues.json"

# ---- _stamp_meta mode discipline ----------------------------------------------
# The shared bookkeeping write (retired_from, closure_package, the gh role
# stamp). It lands on API metas too — a retirement can stamp one — and an API
# meta holds the run bearer at 0600. Recreating it at the umask default
# republishes that secret world-readable, permanently: the api path's own stamp
# preserves whatever mode it finds. Exercised directly, since no path in this
# gh-mode suite puts a bearer at rest.
echo "_stamp_meta mode discipline:"
eval "$(sed -n '/^_stamp_meta() {/,/^}/p' "$DISPATCH")"
mode_of() { python3 -c 'import os, sys
print("%o" % (os.stat(sys.argv[1]).st_mode & 0o777))' "$1"; }
printf '%s' '{"uuid": "u1", "run_bearer": "SECRET-TOKEN"}' > "$DAEMON_HOME/u1.json"
chmod 600 "$DAEMON_HOME/u1.json"
_stamp_meta u1 retired_from failure
assert_equals "$(mode_of "$DAEMON_HOME/u1.json")" "600" "a run-bearer meta survives the stamp at 0600"
assert_contains "$(cat "$DAEMON_HOME/u1.json")" '"retired_from": "failure"' "and the stamp still wrote its field"
printf '%s' '{"uuid": "u2"}' > "$DAEMON_HOME/u2.json"
chmod 600 "$DAEMON_HOME/u2.json"
_stamp_meta u2 retired_from failure
assert_equals "$(mode_of "$DAEMON_HOME/u2.json")" "600" "any narrowed meta keeps the mode it already had"
rm -f "$DAEMON_HOME/u1.json" "$DAEMON_HOME/u2.json"

echo
if [[ "$FAILURES" -gt 0 ]]; then
    echo "$FAILURES test(s) FAILED"; exit 1
fi
echo "all tests passed"
