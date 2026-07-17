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
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; echo "    in: $1"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; echo "    in: $1"; else pass "$3"; fi
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

# gh overlay: pr list + issue-view comments are test fixtures; everything
# else delegates to the shared issue-tracker mock.
GH_EXTRA="$TEST_ROOT/gh-extra"; mkdir -p "$GH_EXTRA"
cat > "$GH_EXTRA/gh" <<SHIM
#!/usr/bin/env bash
if [ "\${1:-}" = "pr" ] && [ "\${2:-}" = "list" ]; then
  cat "\$MOCK_PR_LIST"; exit 0
fi
if [ "\${1:-}" = "issue" ] && [ "\${2:-}" = "view" ] && printf '%s' "\$*" | grep -q "json comments"; then
  cat "\$COMMENTS_DIR/\$3.json" 2>/dev/null || echo '{"comments":[]}'; exit 0
fi
exec "$REPO_ROOT/tests/issue-tracker/mock-gh/gh" "\$@"
SHIM
chmod +x "$GH_EXTRA/gh"
export PATH="$GH_EXTRA:$PATH"

# daemon-verb stubs
STUB_DAEMONS="$TEST_ROOT/stub-daemons"; mkdir -p "$STUB_DAEMONS"
export DAEMON_SCRIPTS="$STUB_DAEMONS"
cat > "$STUB_DAEMONS/daemon-finalize.sh" <<'STUB'
#!/usr/bin/env bash
echo "finalize:$1" >> "$ACTION_LOG"
python3 -c "
import json, os, sys
m = json.load(open(os.environ['FINALIZE_MAP']))
print(m.get(sys.argv[1], 'noop'))" "$1"
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
s = {"next": 30, "labels": ["status:needs-human", "status:in-progress"], "issues": {
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
}}
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))

def meta(uuid, name, ticket, status, recov=None, updated="2026-07-18T00:00:00Z", current=None):
    m = {"uuid": uuid, "current": current or uuid, "name": name, "ticket": ticket,
         "status": status, "updated": updated}
    if recov is not None:
        m["sweep_recoveries"] = recov
    json.dump(m, open(os.path.join(os.environ["DAEMON_HOME"], uuid + ".json"), "w"))
U = lambda n: "%s-0000-4000-8000-000000000000" % n
meta(U("aaaa0010"), "10-dead", "10", "working")
meta(U("aaaa0011"), "11-hopeless", "11", "error", recov="3")
meta(U("aaaa0012"), "12-stalled", "12", "working")
meta(U("aaaa0013"), "13-cancelled", "13", "working")
meta(U("aaaa0014"), "land-pr-7", "14", "working")
meta(U("aaaa0015"), "15-parked", "15", "idle", updated="2026-07-18T01:00:00Z")
meta(U("aaaa0016"), "16-parked", "16", "idle", updated="2026-07-18T01:00:00Z",
     recov=None)
meta(U("aaaa0017"), "17-parked", "17", "idle", updated="2026-07-18T01:00:00Z")
meta(U("aaaa0018"), "18-healthy", "18", "working")
PY

# finalize verdicts per uuid
python3 - <<'PY'
import json, os
U = lambda n: "%s-0000-4000-8000-000000000000" % n
json.dump({U("aaaa0010"): "absent", U("aaaa0011"): "error", U("aaaa0012"): "live",
           U("aaaa0013"): "live", U("aaaa0014"): "live", U("aaaa0018"): "live"},
          open(os.environ["FINALIZE_MAP"], "w"))
PY

# transcripts: 12's is old (stall), 18's is fresh (healthy)
touch -t 202607170000 "$HOME/.claude/projects/proj/aaaa0012-0000-4000-8000-000000000000.jsonl" 2>/dev/null \
  || { touch "$HOME/.claude/projects/proj/aaaa0012-0000-4000-8000-000000000000.jsonl"; \
       touch -t 202607170000 "$HOME/.claude/projects/proj/aaaa0012-0000-4000-8000-000000000000.jsonl"; }
touch "$HOME/.claude/projects/proj/aaaa0018-0000-4000-8000-000000000000.jsonl"

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

echo
if [ "$FAILURES" -gt 0 ]; then
    echo "$FAILURES test(s) FAILED"
    exit 1
fi
echo "all tests passed"
