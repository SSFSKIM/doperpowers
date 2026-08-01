#!/usr/bin/env bash
#
# Hermetic tests for board-sweep.sh — the unattended tick.
#
# The board is the shared mock gh (real _board.py + board-transition run
# against it); PR listing and issue comments come from a gh overlay shim;
# every lane dispatcher and daemon verb is a logging stub, so these tests
# pin the SWEEP's own logic: pass scoping, bounded recovery, cancel guards,
# land signal detection, relay ordering, and pass isolation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SWEEP="$REPO_ROOT/skills/issue-tracker/scripts/board-sweep.sh"

FAILURES=0
TEST_ROOT="$(mktemp -d)"
cleanup() { rm -rf "$TEST_ROOT"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_contains() {
    if grep -Fq -- "$2" <<<"$1"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if grep -Fq -- "$2" <<<"$1"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
}
assert_equals() {
    if [ "$1" = "$2" ]; then pass "$3"; else
        fail "$3"; echo "    expected: $2"; echo "    actual:   $1"; fi
}

# ---- environment --------------------------------------------------------------
export HOME="$TEST_ROOT/home"; mkdir -p "$HOME/.claude/projects/proj"
export DAEMON_HOME="$TEST_ROOT/registry"; mkdir -p "$DAEMON_HOME"
export MOCK_GH_STATE="$TEST_ROOT/gh-state.json"
export MOCK_GH_LOG="$TEST_ROOT/gh-log.jsonl"
export BOARD_REPO="test/repo"
export BOARD_SCRIPTS="$REPO_ROOT/skills/issue-tracker/scripts"
export ACTION_LOG="$TEST_ROOT/actions.log"; : > "$ACTION_LOG"
export SWEEP_LOG="$TEST_ROOT/sweep.log"
export MOCK_PR_LIST="$TEST_ROOT/pr-list.json"; echo "[]" > "$MOCK_PR_LIST"
export COMMENTS_DIR="$TEST_ROOT/comments"; mkdir -p "$COMMENTS_DIR"
export FINALIZE_MAP="$TEST_ROOT/finalize.json"; echo "{}" > "$FINALIZE_MAP"
# A consumer repo distinct from the invocation cwd: launchd/cron start the
# tick outside any repo, and the bare board scripts (reconcile, answer,
# transition) anchor _lib.sh on the current directory — the sweep must cd.
# A real git repo, as in production: board-transition runs against it live.
export LOCAL_REPO="$TEST_ROOT/consumer"
git init -q "$LOCAL_REPO"

# The harness keeps comments in TWO stores: seeded fixtures (per-ticket JSON
# under $COMMENTS_DIR, with the createdAt/author shape the relay pass reads)
# and whatever the tick itself wrote through B.comment, which lands in the
# shared mock-gh state as a bare body string. A `--json comments` read must
# see both, or a marker the sweep just posted would be invisible to the next
# tick's dedupe read. Fixtures come first (they are the older, seeded trail),
# run-written comments after; every comment carries a stable id — fixtures
# keep their own, mock-state comments get their append index — because the
# reconcile marker names the proposal by comment id.
export MERGE_COMMENTS="$TEST_ROOT/merge-comments.py"
cat > "$MERGE_COMMENTS" <<'PY'
import json, os, sys
num = sys.argv[1]
out = []
fixture = os.path.join(os.environ["COMMENTS_DIR"], num + ".json")
if os.path.exists(fixture):
    with open(fixture) as f:
        for i, c in enumerate(json.load(f).get("comments") or []):
            c.setdefault("id", "FX_%s_%d" % (num, i))
            out.append(c)
with open(os.environ["MOCK_GH_STATE"]) as f:
    issues = json.load(f)["issues"]
for i, body in enumerate((issues.get(num) or {}).get("comments") or []):
    # Seed-era createdAt: comments the tick wrote are the board's own trail,
    # never a human answer the relay pass should chase.
    out.append({"id": "IC_%s_%d" % (num, i), "author": {"login": "board"},
                "body": body, "createdAt": "2026-07-18T00:00:00Z"})
print(json.dumps({"comments": out}))
PY

# gh overlay: pr list is a test fixture and issue-view comments are the merge
# above; everything else delegates to the shared issue-tracker mock.
GH_EXTRA="$TEST_ROOT/gh-extra"; mkdir -p "$GH_EXTRA"
cat > "$GH_EXTRA/gh" <<SHIM
#!/usr/bin/env bash
if [ "\${1:-}" = "pr" ] && [ "\${2:-}" = "list" ]; then
  cat "\$MOCK_PR_LIST"; exit 0
fi
if [ "\${1:-}" = "issue" ] && [ "\${2:-}" = "view" ] && grep -q -- "json comments" <<<"\$*"; then
  exec python3 "\$MERGE_COMMENTS" "\$3"
fi
exec "$REPO_ROOT/tests/issue-tracker/mock-gh/gh" "\$@"
SHIM
chmod +x "$GH_EXTRA/gh"
export PATH="$GH_EXTRA:$PATH"

# ---- board readers/writers over the shared mock state -------------------------
mock_comment() {  # <ticket> <body> — post as a worker/human would
    T_N="$1" T_BODY="$2" python3 - <<'PY'
import json, os
p = os.environ["MOCK_GH_STATE"]
with open(p) as f:
    s = json.load(f)
s["issues"][os.environ["T_N"]]["comments"].append(os.environ["T_BODY"])
with open(p, "w") as f:
    json.dump(s, f)
PY
}
issue_labels() {  # <ticket> → comma-joined labels
    T_N="$1" python3 - <<'PY'
import json, os
with open(os.environ["MOCK_GH_STATE"]) as f:
    s = json.load(f)
print(",".join(s["issues"][os.environ["T_N"]]["labels"]))
PY
}
last_comment() {  # <ticket> → newest comment body ("" when there are none)
    T_N="$1" python3 - <<'PY'
import json, os
with open(os.environ["MOCK_GH_STATE"]) as f:
    s = json.load(f)
c = s["issues"][os.environ["T_N"]]["comments"]
print(c[-1] if c else "")
PY
}
comment_count() {  # <ticket> <substring> → how many comments contain it
    T_N="$1" T_SUB="$2" python3 - <<'PY'
import json, os
with open(os.environ["MOCK_GH_STATE"]) as f:
    s = json.load(f)
sub = os.environ["T_SUB"]
print(sum(1 for c in s["issues"][os.environ["T_N"]]["comments"] if sub in c))
PY
}
set_status() {  # <ticket> <state> — fixture surgery, bypassing the legality table
    T_N="$1" T_TO="$2" python3 - <<'PY'
import json, os
p = os.environ["MOCK_GH_STATE"]
with open(p) as f:
    s = json.load(f)
it = s["issues"][os.environ["T_N"]]
it["labels"] = [l for l in it["labels"] if not l.startswith("status:")]
it["labels"].append("status:" + os.environ["T_TO"])
with open(p, "w") as f:
    json.dump(s, f)
PY
}
board_eligible() {  # <ticket> → eligible | not-eligible (the dispatch predicate)
    PYTHONPATH="$BOARD_SCRIPTS" python3 - "$1" <<'PY'
import sys
import _board as B
print("eligible" if B.eligible(B.snapshot(), sys.argv[1]) else "not-eligible")
PY
}

# daemon-verb stubs
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
export DAEMON_SCRIPTS="$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-finalize.sh" <<'STUB'
#!/usr/bin/env bash
# Mimics REAL daemon-finalize semantics: a meta not in working/blocked is
# already terminal → noop, regardless of what the test map says. The map
# only supplies verdicts finalize could actually produce.
echo "finalize:$1" >> "$ACTION_LOG"
python3 -c "
import json, os, sys
uuid = sys.argv[1]
meta = json.load(open(os.path.join(os.environ['DAEMON_HOME'], uuid + '.json')))
if meta.get('status') not in ('working', 'blocked'):
    print('noop'); raise SystemExit
m = json.load(open(os.environ['FINALIZE_MAP']))
print(m.get(uuid, 'live'))" "$1"
STUB
cat > "$STUB_DAEMONS/daemon-resume.sh" <<'STUB'
#!/usr/bin/env bash
echo "resume:$1:${2:0:60}" >> "$ACTION_LOG"
STUB
cat > "$STUB_DAEMONS/daemon-retire.sh" <<'STUB'
#!/usr/bin/env bash
echo "retire:$1" >> "$ACTION_LOG"
python3 - "$1" <<'PY'
import json, os, sys
p = os.path.join(os.environ["DAEMON_HOME"], sys.argv[1] + ".json")
try:
    m = json.load(open(p)); m["status"] = "retired"; json.dump(m, open(p, "w"))
except Exception:
    pass
PY
STUB
chmod +x "$STUB_DAEMONS"/*.sh

# lane stubs
cat > "$TEST_ROOT/impl-dispatch" <<'STUB'
#!/usr/bin/env bash
echo "impl-dispatch:$*" >> "$ACTION_LOG"
STUB
cat > "$TEST_ROOT/review-dispatch" <<'STUB'
#!/usr/bin/env bash
echo "review-dispatch:$*" >> "$ACTION_LOG"
if [ "${FAIL_REVIEW:-0}" = "1" ]; then echo "review lane exploded" >&2; exit 1; fi
STUB
cat > "$TEST_ROOT/land-dispatch" <<'STUB'
#!/usr/bin/env bash
echo "land-dispatch:$*" >> "$ACTION_LOG"
STUB
cat > "$TEST_ROOT/board-answer" <<'STUB'
#!/usr/bin/env bash
echo "answer:$*" >> "$ACTION_LOG"
STUB
cat > "$TEST_ROOT/reconcile" <<'STUB'
#!/usr/bin/env bash
echo "reconcile-ran" >> "$ACTION_LOG"
echo "reconcile-pwd:$PWD" >> "$ACTION_LOG"
echo "reconcile report line"
STUB
chmod +x "$TEST_ROOT/impl-dispatch" "$TEST_ROOT/review-dispatch" \
         "$TEST_ROOT/land-dispatch" "$TEST_ROOT/board-answer" "$TEST_ROOT/reconcile"
export IMPLEMENT_DISPATCH_CMD="$TEST_ROOT/impl-dispatch"
export REVIEW_DISPATCH_CMD="$TEST_ROOT/review-dispatch"
export LAND_DISPATCH_CMD="$TEST_ROOT/land-dispatch"
export BOARD_ANSWER_CMD="$TEST_ROOT/board-answer"
export RECONCILE_CMD="$TEST_ROOT/reconcile"

# ---- board + registry seed ----------------------------------------------------
python3 - <<'PY'
import json, os
def issue(num, title, labels, state="OPEN", reason=None, body=""):
    return {"number": num, "id": "ID_%d" % num, "title": title, "body": body,
            "state": state, "stateReason": reason, "labels": labels,
            "assignees": [], "parent": None, "blockedBy": [],
            "closesPRs": [], "xrefPRs": [], "comments": [],
            "createdAt": "2026-07-18T00:00:00Z", "updatedAt": "2026-07-18T00:00:00Z",
            "url": "https://github.com/test/repo/issues/%d" % num}
s = {"next": 40, "labels": ["status:needs-human", "status:in-progress",
                            "status:in-design", "status:ready-for-architect"], "issues": {
    "10": issue(10, "dead worker mid-build", ["status:in-progress"]),
    "11": issue(11, "worker beyond recovery", ["status:in-progress"]),
    "12": issue(12, "stalled worker", ["status:in-progress"]),
    "13": issue(13, "cancelled underneath its worker", [], state="CLOSED", reason="COMPLETED"),
    "14": issue(14, "landed ticket with live lander", [], state="CLOSED", reason="COMPLETED"),
    "15": issue(15, "parked with fresh answer", ["status:needs-human"],
                body="board:meta\nnote: which flavor?\n"),
    "16": issue(16, "parked, answers already relayed", ["status:needs-human"],
                body="board:meta\nnote: q\n"),
    "17": issue(17, "parked, no new comment", ["status:needs-human"],
                body="board:meta\nnote: q\n"),
    "18": issue(18, "healthy live worker", ["status:in-progress"]),
    "19": issue(19, "resume-fork failed once", ["status:in-progress"]),
    "20": issue(20, "dead architect mid-design", ["status:in-design"]),
    "21": issue(21, "dead pre-verdict architect", ["status:ready-for-architect"]),
    # IMPACT pass: two epic/child pairs, no bound workers. 25 is claimable
    # (pulled in-progress by its active child); 27 has already returned to
    # ready-for-architect, so its child's proposal must be left unmarked.
    "25": issue(25, "epic pulled by an active child", ["status:in-progress"]),
    "26": issue(26, "child that finds a parent-level gap", ["status:in-progress"]),
    "27": issue(27, "epic already awaiting an architect", ["status:ready-for-architect"]),
    "28": issue(28, "child of the already-returned epic", ["status:in-progress"]),
    "29": issue(29, "epic closed while a child still runs", [],
                state="CLOSED", reason="COMPLETED"),
    "30": issue(30, "child of a closed epic", ["status:in-progress"]),
}}
s["issues"]["26"]["parent"] = 25
s["issues"]["28"]["parent"] = 27
s["issues"]["30"]["parent"] = 29
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))

def meta(uuid, name, ticket, status, recov=None, updated="2026-07-18T00:00:00Z", current=None):
    m = {"uuid": uuid, "current": current or uuid, "name": name, "ticket": ticket,
         "status": status, "updated": updated}
    if recov is not None:
        m["sweep_recoveries"] = recov
    json.dump(m, open(os.path.join(os.environ["DAEMON_HOME"], uuid + ".json"), "w"))
U = lambda n: "%s-0000-4000-8000-000000000000" % n
meta(U("aaaa0010"), "10-dead", "10", "working")
# ALREADY-finalized error meta (real finalize says noop for it) at the cap:
meta(U("aaaa0011"), "11-hopeless", "11", "error", recov="3")
meta(U("aaaa0012"), "12-stalled", "12", "working")
meta(U("aaaa0013"), "13-cancelled", "13", "working")
meta(U("aaaa0014"), "land-pr-7", "14", "working")
# Parked workers in the PRODUCTION shape: nothing finalizes a --no-wait
# worker's meta when it parks, so status lingers `working`.
meta(U("aaaa0015"), "15-parked", "15", "working", updated="2026-07-18T01:00:00Z")
meta(U("aaaa0016"), "16-parked", "16", "working", updated="2026-07-18T01:00:00Z",
     recov=None)
meta(U("aaaa0017"), "17-parked", "17", "working", updated="2026-07-18T01:00:00Z")
meta(U("aaaa0018"), "18-healthy", "18", "working")
# ALREADY-finalized error meta below the cap (a failed resume fork's shape):
meta(U("aaaa0019"), "19-refork", "19", "error", recov="1")
meta(U("aaaa0020"), "20-design", "20", "working")
meta(U("aaaa0021"), "21-preverdict", "21", "working")
PY

# finalize verdicts per uuid (only consulted for working/blocked metas —
# the parked trio's turns ended, so real finalize would say idle)
python3 - <<'PY'
import json, os
U = lambda n: "%s-0000-4000-8000-000000000000" % n
json.dump({U("aaaa0010"): "absent", U("aaaa0012"): "live",
           U("aaaa0013"): "live", U("aaaa0014"): "live", U("aaaa0018"): "live",
           U("aaaa0015"): "idle", U("aaaa0016"): "idle", U("aaaa0017"): "idle",
           U("aaaa0020"): "absent", U("aaaa0021"): "absent"},
          open(os.environ["FINALIZE_MAP"], "w"))
PY

# transcripts: mtime is the turn-end ordering signal. 12 old (stall), 18
# fresh (healthy); 15/16 old (comments postdate the turn → relay-eligible),
# 17 fresh (its comment predates the turn end → not an answer).
for u in aaaa0012 aaaa0015 aaaa0016; do
  f="$HOME/.claude/projects/proj/$u-0000-4000-8000-000000000000.jsonl"
  touch "$f"; touch -t 202607170000 "$f"
done
touch "$HOME/.claude/projects/proj/aaaa0018-0000-4000-8000-000000000000.jsonl"
touch "$HOME/.claude/projects/proj/aaaa0017-0000-4000-8000-000000000000.jsonl"

# comments: 15 fresh human answer · 16 newest is [answers] · 17 stale comment
cat > "$COMMENTS_DIR/15.json" <<'J'
{"comments":[{"id":"IC_15a","author":{"login":"me"},"body":"Answer: flavor B, and ship it.","createdAt":"2026-07-18T02:00:00Z"}]}
J
cat > "$COMMENTS_DIR/16.json" <<'J'
{"comments":[{"id":"IC_16a","author":{"login":"me"},"body":"[answers] relayed already","createdAt":"2026-07-18T02:00:00Z"}]}
J
cat > "$COMMENTS_DIR/17.json" <<'J'
{"comments":[{"id":"IC_17a","author":{"login":"me"},"body":"old musing","createdAt":"2026-07-18T00:30:00Z"}]}
J

# PRs for the land pass
cat > "$MOCK_PR_LIST" <<'J'
[{"number":21,"reviewDecision":"APPROVED","labels":[{"name":"confident-ready"}]},
 {"number":22,"reviewDecision":"REVIEW_REQUIRED","labels":[{"name":"confident-ready"}]},
 {"number":23,"reviewDecision":"","labels":[{"name":"confident-ready"},{"name":"land"}]},
 {"number":24,"reviewDecision":"APPROVED","labels":[{"name":"confident-ready"}]}]
J
python3 - <<'PY'
import json, os
u = "bbbb0024-0000-4000-8000-000000000000"
json.dump({"uuid": u, "current": u, "name": "land-pr-24", "status": "idle",
           "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"], u + ".json"), "w"))
PY

run_sweep() { SWEEP_STALL_MINUTES=60 "$SWEEP" 2>&1; }

echo "board-sweep: full tick"
out="$(run_sweep)"
log="$(cat "$ACTION_LOG")"

# RECOVER
assert_contains "$log" "resume:aaaa0010-0000-4000-8000-000000000000" "dead (absent) worker is resumed"
assert_contains "$log" "resume:aaaa0012-0000-4000-8000-000000000000" "stalled live worker is resumed"
assert_contains "$log" "resume:aaaa0019-0000-4000-8000-000000000000" "an already-finalized error meta (finalize noop) still recovers"
assert_not_contains "$log" "resume:aaaa0018" "healthy live worker is left alone"
assert_not_contains "$log" "resume:aaaa0011" "recovery cap exhausts — no fourth resume"
st15="$(python3 -c "
import json, os
s = json.load(open(os.environ['MOCK_GH_STATE']))
print(','.join(s['issues']['11']['labels']))")"
assert_contains "$st15" "status:needs-human" "cap-exhausted ticket parks needs-human"
recov10="$(python3 -c "
import json, os
print(json.load(open(os.path.join(os.environ['DAEMON_HOME'],
  'aaaa0010-0000-4000-8000-000000000000.json'))).get('sweep_recoveries'))")"
assert_contains "$recov10" "1" "recovery attempt is counted durably in the meta"

# RECOVER — lane-state split (E1): in-flight design work resumes; a dead
# pre-verdict worker is retired so the dispatch pass re-runs it fresh
assert_contains "$log" "resume:aaaa0020-0000-4000-8000-000000000000" "dead in-design worker gets the resume ladder (mid-design WIP is preserved)"
assert_contains "$out" "RECOVER: #20 worker aaaa0020-0000-4000-8000-000000000000 died mid-turn (session gone) — resume attempt 1/3" "in-design recovery goes through _recover's counted ladder"
assert_contains "$log" "retire:aaaa0021-0000-4000-8000-000000000000" "dead ready-for-architect worker is retired, not resumed"
assert_contains "$out" "pre-verdict worker" "retire log names the pre-verdict rule"
assert_not_contains "$log" "resume:aaaa0021" "pre-verdict recovery never resumes"

# CANCEL
assert_contains "$log" "retire:aaaa0013-0000-4000-8000-000000000000" "live worker on a terminal ticket is retired"
c13="$(python3 -c "
import json, os
s = json.load(open(os.environ['MOCK_GH_STATE']))
print(' / '.join(s['issues']['13']['comments']))")"
assert_contains "$c13" "[board] sweep" "cancel posts a termination comment"
assert_not_contains "$log" "retire:aaaa0014" "land workers are never board-cancelled"

# DISPATCH + REVIEW lanes
assert_contains "$log" "impl-dispatch:--sweep" "implement lane sweeps"
assert_contains "$log" "review-dispatch:--sweep" "review lane sweeps"

# LAND
assert_contains "$log" "land-dispatch:21" "approved confident-ready PR gets a land worker"
assert_contains "$log" "land-dispatch:23" "land label overrides a missing approval"
assert_not_contains "$log" "land-dispatch:22" "unapproved PR is not landed"
assert_not_contains "$log" "land-dispatch:24" "an existing land meta means no second sweep attempt"

# RELAY
assert_contains "$log" "answer:15 --posted" "fresh human comment on a parked ticket relays"
assert_not_contains "$log" "answer:16" "[answers] comment does not re-relay"
assert_not_contains "$log" "answer:17" "a comment older than the park is not an answer"
relayed="$(python3 -c "
import json, os
print(json.load(open(os.path.join(os.environ['DAEMON_HOME'],
  'aaaa0015-0000-4000-8000-000000000000.json'))).get('relayed_comment'))")"
assert_contains "$relayed" "IC_15a" "relayed comment id is recorded in the meta"

# REPORT
assert_contains "$log" "reconcile-ran" "report pass runs reconcile"
assert_contains "$log" "reconcile-pwd:$LOCAL_REPO" "tick runs from LOCAL_REPO (launchd cwd is not a repo)"
assert_contains "$(cat "$SWEEP_LOG")" "reconcile report line" "sweep log captures the report"

echo "board-sweep: idempotence + isolation + lock"

: > "$ACTION_LOG"
out="$(run_sweep)"
log="$(cat "$ACTION_LOG")"
assert_not_contains "$log" "answer:15" "second tick does not re-relay the same comment"
assert_not_contains "$log" "retire:aaaa0013" "second tick does not re-cancel a retired worker"

: > "$ACTION_LOG"
out="$(FAIL_REVIEW=1 run_sweep)"
log="$(cat "$ACTION_LOG")"
assert_contains "$log" "land-dispatch:21" "a failing review lane never stops later passes"
assert_contains "$out" "review lane exploded" "the failing lane's error is surfaced"

mkdir -p "$DAEMON_HOME/board-sweep.lock"
out="$(run_sweep)"
assert_contains "$out" "another sweep holds the lock" "a held lock exits quietly"
rmdir "$DAEMON_HOME/board-sweep.lock"

out="$(DAEMON_HOME="$TEST_ROOT/fresh-registry" SWEEP_LOG="$TEST_ROOT/fresh-sweep.log" run_sweep)"
assert_contains "$out" "tick complete" "a fresh machine (no registry dir yet) still ticks"
assert_not_contains "$out" "another sweep holds the lock" "missing registry dir is not misread as a held lock"

# ---- IMPACT pass (E2 upward revision) -----------------------------------------
# A child worker may not write its parent: it posts a [parent-impact] comment
# on its OWN ticket and the sweep performs the parent's reconciliation return.
echo "board-sweep: IMPACT pass"
EPIC=25; CHILD=26; PENDING_EPIC=27; PENDING_CHILD=28
assert_equals "$(comment_count "$EPIC" "[board-epic] reconcile:")" "0" "no proposal, no reconcile marker"

mock_comment "$CHILD" "[parent-impact] #$EPIC acceptance-A3: discovered the queue contract cannot hold ordering"
out="$(run_sweep)"
assert_contains "$(issue_labels "$EPIC")" "status:ready-for-architect" "parent-impact proposal returns the parent for reconciliation"
assert_contains "$(last_comment "$EPIC")" "[board-epic] reconcile: #$CHILD@" "reconcile marker names the consumed proposal"
assert_contains "$out" "IMPACT: #$EPIC: in-progress → ready-for-architect" "the return is logged as an IMPACT action"
assert_equals "$(board_eligible "$EPIC")" "eligible" "reconciliation-due epic is dispatch-eligible even with active children"

out="$(run_sweep)"
assert_equals "$(comment_count "$EPIC" "[board-epic] reconcile:")" "1" "a consumed proposal is not re-consumed"

# The marker, not the parent's state, is what makes consumption durable: put
# the epic back in a claimable state and the same proposal must not re-fire.
set_status "$EPIC" in-progress
out="$(run_sweep)"
assert_equals "$(comment_count "$EPIC" "[board-epic] reconcile:")" "1" "the marker dedupes even once the parent is claimable again"
assert_contains "$(issue_labels "$EPIC")" "status:in-progress" "a consumed proposal never returns the parent a second time"

# Dedupe-hole rule: a parent already awaiting/holding an Architect gets NO
# marker — marking it there would consume the proposal with nobody reading it.
mock_comment "$PENDING_CHILD" "[parent-impact] #$PENDING_EPIC the acceptance cannot be met as written"
out="$(run_sweep)"
assert_equals "$(comment_count "$PENDING_EPIC" "[board-epic] reconcile:")" "0" "a proposal on an already-returned parent is left unmarked"
assert_equals "$(board_eligible "$PENDING_EPIC")" "not-eligible" "an epic with no reconciliation-due note stays out of the pool while children are active"

# A closed parent has no reconciliation to perform — a late proposal must not
# stamp a status label back onto it (epics do get closed under live children).
mock_comment 30 "[parent-impact] #29 the parent shipped without this"
out="$(run_sweep)"
assert_equals "$(issue_labels 29)" "" "a closed parent is never re-labelled by a late proposal"
assert_equals "$(comment_count 29 "[board-epic]")" "0" "a closed parent gets no bookkeeping comment"

echo
if [ "$FAILURES" -gt 0 ]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
