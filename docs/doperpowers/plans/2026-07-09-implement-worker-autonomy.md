# Implement-Worker Autonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Board schema v8 (retire `blocked`; add `needs-human` and `interactive-preferred`), a new sibling skill `implementing-tickets` carrying the Ticket Gate + Implement Worker Protocol v2, the issue-tracker SKILL.md rewritten as the no-orchestrator board manual, reviewing-prs park-vocabulary ripples, tests, and the ida-solution migration.

**Architecture:** The whole state machine lives in `skills/issue-tracker/scripts/_board.py` (constants + `LEGAL` matrix) — the schema change is one file plus the scripts/template that render states. Doctrine moves out of issue-tracker into a new `skills/implementing-tickets/` (mirror of `reviewing-prs`): SKILL.md doctrine + `references/implement-worker-protocol.md` with `{{PLACEHOLDERS}}`. No dispatch script this phase (that is the next-phase trigger).

**Tech Stack:** bash + stdlib-only Python (inline via `_py` heredocs), mock-`gh` hermetic test harness (`tests/issue-tracker/`), GitHub Issues as the only store.

**Spec:** `docs/doperpowers/specs/2026-07-09-implement-worker-autonomy-design.md` — read its Purpose and The Ticket Gate sections before starting.

## Global Constraints

- Python in `scripts/` is stdlib-only; every GitHub call shells out to `gh` (fail-loud).
- All board writes go through the scripts (Board Write Hard Gate) — never raw `gh issue edit` for `status:*` labels or edges.
- The three park states (`needs-human`, `needs-info`, `interactive-preferred`) ALWAYS require a note; `wontfix` keeps requiring one.
- Exactly one `status:*` label per open issue; terminal states are close reasons, never labels.
- Thresholds and rubric wording live in ONE place: the protocol text (`references/implement-worker-protocol.md`).
- Commit messages: no `Co-Authored-By` / attribution lines (user's global CLAUDE.md).
- `tests/issue-tracker/test-board-scripts.sh` is order-dependent (issue numbers accrue sequentially). NEVER insert a `board-register.sh` call mid-file — append new sections immediately BEFORE the `# template view logic` block (currently the `echo "board template (kanban view logic):"` stanza), and only edit existing sections in place without adding registrations.

---

### Task 1: Schema v8 core — `_board.py`, transition/register/lint, migrate mapping

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:19-63` (vocabulary block)
- Modify: `skills/issue-tracker/scripts/board-register.sh:12-13,63-64`
- Modify: `skills/issue-tracker/scripts/board-lint.sh:14,49-59` (+ header)
- Modify: `skills/issue-tracker/scripts/board-transition.sh:7` (header comment only)
- Modify: `skills/issue-tracker/scripts/board-migrate-gh.sh:100` (legacy mapping)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Produces: `_board.py` constants consumed by every later task —
  `OPEN_STATES = ("ready-for-agent", "in-progress", "needs-human", "needs-info", "interactive-preferred", "in-review", "confident-ready", "deferred")`,
  `NOTE_REQUIRED = ("needs-human", "needs-info", "interactive-preferred", "wontfix")`,
  `BIRTH = ("ready-for-agent", "needs-info", "needs-human", "interactive-preferred", "deferred")`,
  `PULLABLE = ("ready-for-agent", "needs-info", "needs-human", "interactive-preferred", "deferred")`, and the `LEGAL` matrix below. Task 2 keys CSS classes `s_needh`/`s_ipref` off these state names.

- [ ] **Step 1: Migrate the existing tests off `blocked` (the failing tests)**

In `tests/issue-tracker/test-board-scripts.sh` make exactly these in-place edits:

(1a) The register birth-state block (issue #2) — replace:

```bash
out="$(run board-register.sh $'Multi\nline title' bug P1 --state blocked --note "waiting on A")"
assert_equals "$(state "s['issues']['2']['title']")" "Multi line title" "title newlines collapsed"
assert_contains "$(state "s['issues']['2']['labels']")" "status:blocked" "birth state honored"
assert_contains "$(state "s['issues']['2']['comments'][0]")" "[board] blocked: waiting on A" "birth note posted as [board] comment"
assert_contains "$(state "s['issues']['2']['body']")" "note: waiting on A" "birth note in board:meta"
```

with:

```bash
out="$(run board-register.sh $'Multi\nline title' bug P1 --state needs-human --note "waiting on A")"
assert_equals "$(state "s['issues']['2']['title']")" "Multi line title" "title newlines collapsed"
assert_contains "$(state "s['issues']['2']['labels']")" "status:needs-human" "birth state honored"
assert_contains "$(state "s['issues']['2']['comments'][0]")" "[board] needs-human: waiting on A" "birth note posted as [board] comment"
assert_contains "$(state "s['issues']['2']['body']")" "note: waiting on A" "birth note in board:meta"
```

(1b) In the register refusals, replace the line

```bash
assert_fails run board-register.sh "X" bug P2 --state needs-info       # note required
```

with:

```bash
assert_fails run board-register.sh "X" bug P2 --state needs-info       # note required
assert_fails run board-register.sh "X" bug P2 --state interactive-preferred  # note required
assert_fails run board-register.sh "X" bug P2 --state blocked          # retired state (v8)
```

(1c) In the transition section, replace:

```bash
assert_fails run board-transition.sh 3 blocked                         # note required
```

with:

```bash
assert_fails run board-transition.sh 3 needs-human                     # note required
```

(1d) The in-review escalation half for `blocked` (issue #18) — replace:

```bash
assert_fails run board-transition.sh 18 blocked                                # note required
out="$(run board-transition.sh 18 blocked "push conflict — needs a human")"
assert_contains "$out" "#18: in-review → blocked" "in-review → blocked is now legal (protocol escalation)"
assert_contains "$(state "s['issues']['18']['labels']")" "status:blocked" "blocked label applied"
```

with:

```bash
assert_fails run board-transition.sh 18 needs-human                            # note required
out="$(run board-transition.sh 18 needs-human "push conflict — needs a human")"
assert_contains "$out" "#18: in-review → needs-human" "in-review → needs-human is legal (protocol escalation)"
assert_contains "$(state "s['issues']['18']['labels']")" "status:needs-human" "needs-human label applied"
```

Also update that section's leading comment: `in-review → needs-info (round cap reached, impasse) and in-review → needs-human (push conflict, precondition failure)`.

(1e) Append the three new sections immediately BEFORE the `echo "board template (kanban view logic):"` stanza (registrations here continue the issue sequence at 19, 20 — nothing after this point registers issues):

```bash
# ---- interactive-preferred (park: ticket shape wants live human steering) -----
echo "interactive-preferred:"
assert_fails run board-register.sh "IP birth" enhancement P2 --state interactive-preferred  # note required
run board-register.sh "IP birth" enhancement P2 --state interactive-preferred --note "product-core: onboarding voice" >/dev/null   # 19
assert_contains "$(state "s['issues']['19']['labels']")" "status:interactive-preferred" "birth state honored"
out="$(run board-list.sh)"
line19="$(printf '%s\n' "$out" | grep '^#19 ')"
assert_not_contains "$line19" "ELIGIBLE" "interactive-preferred is never ELIGIBLE"
out="$(run board-transition.sh 19 in-progress)"
assert_contains "$out" "#19: interactive-preferred → in-progress" "human takes it up: in-progress legal"
assert_fails run board-transition.sh 19 interactive-preferred                  # note required
out="$(run board-transition.sh 19 interactive-preferred "back to parked")"
assert_contains "$out" "#19: in-progress → interactive-preferred" "in-progress → interactive-preferred legal (gate-fail mid-build)"
set +e
lint_out="$(run board-lint.sh 2>&1)"; lint_rc=$?
set -e
assert_equals "$lint_rc" "0" "board with a noted interactive-preferred ticket lints green"

# ---- needs-human (park: the human as themselves unparks) ---------------------
echo "needs-human:"
run board-register.sh "NH probe" enhancement P2 >/dev/null                     # 20
assert_fails run board-transition.sh 20 needs-human                            # note required
out="$(run board-transition.sh 20 needs-human "pick auth provider: A or B (rec: A)")"
assert_contains "$out" "#20: ready-for-agent → needs-human" "gate-fail park applied"
out="$(run board-transition.sh 20 needs-info "research first: provider capability matrix")"
assert_contains "$out" "#20: needs-human → needs-info" "park-to-park re-triage legal"
out="$(run board-transition.sh 20 ready-for-agent)"
assert_contains "$out" "#20: needs-info → ready-for-agent" "answered park returns to ready"

# ---- blocked is retired (v8) --------------------------------------------------
echo "blocked retired:"
assert_fails run board-transition.sh 20 blocked "any"                          # unknown state
python3 - <<'LEGACY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["20"]["labels"] = ["enhancement", "status:blocked", "priority:P2"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
LEGACY
set +e
lint_out="$(run board-lint.sh 2>&1)"; rc=$?
set -e
assert_equals "$rc" "1" "legacy status:blocked FAILs lint"
assert_contains "$lint_out" "retired state: status:blocked" "retired label named"
assert_contains "$lint_out" "board-transition.sh 20 needs-human" "FIX points at the needs-human migration"
out="$(run board-transition.sh 20 needs-human "migrated: carried note")"
assert_contains "$(state "s['issues']['20']['labels']")" "status:needs-human" "migration swaps the label"
assert_not_contains "$(state "s['issues']['20']['labels']")" "status:blocked" "retired label removed"
```

- [ ] **Step 2: Run the suite to verify the new/edited asserts fail**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -20`
Expected: FAILs — `board-register.sh` dies with `birth state must be one of: ready-for-agent, needs-info, blocked, deferred` on `--state needs-human`, and downstream asserts fail.

- [ ] **Step 3: Rewrite the vocabulary block in `_board.py`**

Replace lines 19–48 (from `# ── state vocabulary` through the `LEGAL = {...}` closing brace) with:

```python
# ── state vocabulary (v8: blocked retired into needs-human; the park trio) ──
OPEN_STATES = ("ready-for-agent", "in-progress", "needs-human", "needs-info",
               "interactive-preferred", "in-review", "confident-ready",
               "deferred")
TERMINAL = ("done", "wontfix")
STATES = OPEN_STATES + TERMINAL
# Actively-worked states: a close_candidate in one of these is normal
# mid-flight shape (part-1 PR merged, part 2 coming) — surfaces that nag or
# relocate (lint WARN, kanban column) skip them; passive displays still mark.
ACTIVE = ("in-progress", "in-review")
BIRTH = ("ready-for-agent", "needs-info", "needs-human",
         "interactive-preferred", "deferred")
# Park discriminant — WHO UNPARKS IT: the human as themselves (a decision or
# a real-world input) → needs-human; knowledge work anyone could do →
# needs-info; ongoing steering, not one answer → interactive-preferred.
NOTE_REQUIRED = ("needs-human", "needs-info", "interactive-preferred", "wontfix")
PULLABLE = ("ready-for-agent", "needs-info", "needs-human",
            "interactive-preferred", "deferred")
LEGAL = {
    "ready-for-agent": {"in-progress", "needs-info", "needs-human",
                        "interactive-preferred", "wontfix", "deferred"},
    "in-progress":     {"needs-info", "needs-human", "interactive-preferred",
                        "in-review", "done", "wontfix", "deferred"},
    "needs-info":      {"ready-for-agent", "in-progress", "needs-human",
                        "interactive-preferred", "wontfix", "deferred"},
    "needs-human":     {"ready-for-agent", "in-progress", "needs-info",
                        "interactive-preferred", "wontfix", "deferred"},
    "interactive-preferred": {"ready-for-agent", "in-progress", "needs-info",
                        "needs-human", "wontfix", "deferred"},
    # needs-info/needs-human reachable from in-review: the reviewing-prs
    # worker's impasse/precondition escalations (protocol safety valves)
    "in-review":       {"in-progress", "confident-ready", "done", "wontfix",
                        "deferred", "needs-info", "needs-human"},
    # confident-ready: PR rigorously reviewed by the reviewing-prs loop.
    # Reachable ONLY from in-review (a review verdict presupposes an open PR);
    # deliberately NOT in ACTIVE — a confident-ready ticket whose PRs all
    # merged SHOULD surface as a close candidate (the finalize cue).
    "confident-ready": {"in-progress", "in-review", "done", "wontfix", "deferred"},
    "deferred":        {"ready-for-agent", "needs-info", "needs-human",
                        "interactive-preferred", "wontfix"},
    "done":            set(),   # terminal
    "wontfix":         set(),   # terminal
}
```

Then in `STATUS_COLORS`, replace the `"blocked": "d93f0b",` entry with:

```python
    "needs-human":     "d93f0b",
    "interactive-preferred": "d4c5f9",
```

(keep `"needs-info": "fbca04",` and the rest as they are).

- [ ] **Step 4: `board-register.sh` — note rule from the constant + header**

Replace (in the inline python):

```python
if state in ("needs-info", "blocked") and not note:
    B.die("--note is required for state %s" % state)
```

with:

```python
if state in B.NOTE_REQUIRED and not note:
    B.die("--note is required for state %s" % state)
```

And the two header comment lines:

```
#   --state   birth state: ready-for-agent (default) | needs-human | needs-info
#             | interactive-preferred | deferred (the three park states require --note)
```

- [ ] **Step 5: `board-lint.sh` — park-trio notes + retired-label FIX + header**

Replace the note check:

```python
    if n["state"] in ("blocked", "needs-info") and not n.get("note"):
```

with:

```python
    if n["state"] in ("needs-human", "needs-info", "interactive-preferred") \
       and not n.get("note"):
```

Replace the CONFLICT branch:

```python
    elif n["state"] == B.CONFLICT:
        fail(tid, "open with %d status:* labels: %s" %
             (len(n["status_labels"]), ", ".join(n["status_labels"])),
             "board-transition.sh %s <state> — the write normalizes the label set" % tid)
```

with:

```python
    elif n["state"] == B.CONFLICT:
        if n["status_labels"] == ["blocked"]:
            fail(tid, "retired state: status:blocked (v8 folded it into needs-human)",
                 "board-transition.sh %s needs-human \"<carried note>\" — the write swaps the label" % tid)
        else:
            fail(tid, "open with %d status:* labels: %s" %
                 (len(n["status_labels"]), ", ".join(n["status_labels"])),
                 "board-transition.sh %s <state> — the write normalizes the label set" % tid)
```

Header comment: change `#   FAIL blocked/needs-info without a note (board:meta)` to `#   FAIL needs-human/needs-info/interactive-preferred without a note (board:meta)` and add below it `#   FAIL open issue carrying the retired status:blocked label (v8 → needs-human)`.

- [ ] **Step 6: `board-transition.sh` header + `board-migrate-gh.sh` legacy mapping**

`board-transition.sh` line 7: `# Enforces transition legality and mandatory notes (blocked/needs-info/wontfix),` → `# Enforces transition legality and mandatory notes (the park trio + wontfix),`.

`board-migrate-gh.sh` — directly after `    want = n["state"]` (line 100) insert:

```python
    # v8: the legacy v6 vocabulary carried `blocked`; it lands as needs-human.
    if want == "blocked":
        want = "needs-human"
```

(No fixture test for this — adding a legacy ticket would renumber every issue the sequential suite creates afterward; the mapping is three lines guarded by the suite's migrate section still passing.)

- [ ] **Step 7: Run the suite to verify it passes**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -5`
Expected: `all tests passed` (the map/reconcile sections still pass untouched: `board-map.sh` renders unknown park states as `s_wait` until Task 2, and reconcile's proposal scan is rewritten in Task 3).

- [ ] **Step 8: Commit**

```bash
git add skills/issue-tracker/scripts/_board.py skills/issue-tracker/scripts/board-register.sh skills/issue-tracker/scripts/board-lint.sh skills/issue-tracker/scripts/board-transition.sh skills/issue-tracker/scripts/board-migrate-gh.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): 보드 스키마 v8 — blocked 폐기, needs-human/interactive-preferred 추가"
```

---

### Task 2: Board views — map classes, kanban columns, header counts

**Files:**
- Modify: `skills/issue-tracker/scripts/board-map.sh:130-133` (CLASS dict)
- Modify: `skills/issue-tracker/scripts/board-map.template.html:69` (CSS), `:199-201` (KB_STATES), `:209-213` (BADGE), `:215-219` (STATE_CLS), `:538-553` (updateHeader)
- Test: `tests/issue-tracker/test-board-scripts.sh` (append map asserts)

**Interfaces:**
- Consumes: Task 1's state names. Produces: CSS classes `s_needh`, `s_ipref` in the HTML payload (`"cls": "s_needh"`), kanban columns `needs-human` / `interactive-preferred`.

- [ ] **Step 1: Append the failing map asserts**

Immediately before the `echo "board template (kanban view logic):"` stanza (after Task 1's appended sections — issue #19 is parked `interactive-preferred`, #20 `needs-human` at this point):

```bash
# ---- map: v8 park classes ------------------------------------------------------
echo "board-map (v8 park classes):"
run board-map.sh --write >/dev/null 2>&1
BOARD_HTML="$(cat "$WORK/doperpowers/issue-tracker/BOARD.html")"
assert_contains "$BOARD_HTML" '"cls": "s_needh"' "html payload carries the needs-human class"
assert_contains "$BOARD_HTML" '"cls": "s_ipref"' "html payload carries the interactive-preferred class"
assert_contains "$BOARD_HTML" '"interactive-preferred"' "kanban vocabulary carries the interactive-preferred column"
assert_not_contains "$BOARD_HTML" 's_blk' "retired blocked class gone from the render"
```

- [ ] **Step 2: Run to verify failure**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | grep -A2 "v8 park classes"`
Expected: FAIL on `s_needh` / `s_ipref` (park states currently fall through to `s_wait`).

- [ ] **Step 3: Implement — board-map.sh CLASS dict**

Replace:

```python
CLASS = {"done": "s_done", "in-progress": "s_prog", "in-review": "s_rev",
         "confident-ready": "s_cready", "blocked": "s_blk",
         "needs-info": "s_info", "deferred": "s_def", "wontfix": "s_wf",
         "conflict": "s_conflict", "untracked": "s_untracked"}
```

with:

```python
CLASS = {"done": "s_done", "in-progress": "s_prog", "in-review": "s_rev",
         "confident-ready": "s_cready", "needs-human": "s_needh",
         "needs-info": "s_info", "interactive-preferred": "s_ipref",
         "deferred": "s_def", "wontfix": "s_wf",
         "conflict": "s_conflict", "untracked": "s_untracked"}
```

- [ ] **Step 4: Implement — template edits (5 spots)**

(4a) CSS line 69 — replace the `.s_blk` rule with:

```css
  .s_needh { --bd: #ef4444; --bgc: rgba(239,68,68,.09);  --tx: #fca5a5; --glow: rgba(239,68,68,.22); }
  .s_ipref { --bd: #ec4899; --bgc: rgba(236,72,153,.09); --tx: #f9a8d4; --glow: rgba(236,72,153,.22); }
```

(4b) KB_STATES — replace:

```javascript
    KB_STATES = ["ready-for-agent", "in-progress", "in-review", "confident-ready",
                 "close-candidate", "blocked", "needs-info", "deferred",
                 "conflict", "untracked", "done", "wontfix"];
```

with:

```javascript
    KB_STATES = ["ready-for-agent", "in-progress", "in-review", "confident-ready",
                 "close-candidate", "needs-human", "needs-info",
                 "interactive-preferred", "deferred",
                 "conflict", "untracked", "done", "wontfix"];
```

(4c) BADGE — replace the `s_wait: "waiting", s_blk: "blocked", s_info: "needs-info",` and `s_def: "deferred", s_wf: "wontfix",` lines with:

```javascript
                s_wait: "waiting", s_needh: "needs-human", s_info: "needs-info",
                s_ipref: "interactive", s_def: "deferred", s_wf: "wontfix",
```

(4d) STATE_CLS — replace:

```javascript
                    "ready-for-agent": "s_elig", "blocked": "s_blk", "needs-info": "s_info",
                    "deferred": "s_def", "wontfix": "s_wf",
```

with:

```javascript
                    "ready-for-agent": "s_elig", "needs-human": "s_needh",
                    "needs-info": "s_info", "interactive-preferred": "s_ipref",
                    "deferred": "s_def", "wontfix": "s_wf",
```

(4e) updateHeader — replace the counter init, the `blocked` count branch, and the hcounts line:

```javascript
    var total = BOARD.nodes.length, c = { done: 0, prog: 0, rev: 0, elig: 0, needh: 0, info: 0, cand: 0 };
      else if (n.state === "needs-human") c.needh++;
      + c.needh + " needs-human · " + c.info + " needs-info"
```

(each replaces its counterpart: `blk: 0` → `needh: 0` in the init; `n.state === "blocked"` branch; `c.blk + " blocked · "` in the string).

- [ ] **Step 5: Run the suite to verify it passes**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -5`
Expected: `all tests passed` (includes the pre-existing template `.cjs` tests — they use synthetic states and are unaffected).

- [ ] **Step 6: Commit**

```bash
git add skills/issue-tracker/scripts/board-map.sh skills/issue-tracker/scripts/board-map.template.html tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): 보드 뷰 v8 — s_needh/s_ipref 클래스, 칸반 컬럼, 헤더 카운트"
```

---

### Task 3: `board-reconcile.sh` — the proposal scanner dies; the wake queue is born

**Files:**
- Modify: `skills/issue-tracker/scripts/board-reconcile.sh`
- Test: `tests/issue-tracker/test-board-scripts.sh` (edit the reconcile section in place)

**Interfaces:**
- Consumes: park states from Task 1. Produces: reconcile output lines shaped `parked    #<n>: <state> — <note>` (the human wake queue; the future Slack connector pushes exactly this).

- [ ] **Step 1: Edit the reconcile test section in place (failing)**

In the `# ---- bind / show / reconcile` section: DELETE the proposal fixture and its two asserts —

```bash
cat > "$DAEMON_HOME/aaaa-bbbb.reply.txt" <<'J'
work done, proposing:
{"ticket":"9","from":"in-progress","to":"in-review","reason":"PR open","evidence":"https://github.com/test/repo/pull/12"}
J
```

and

```bash
assert_contains "$out" "proposal  #9: in-progress → in-review" "reconcile surfaces proposal"
assert_contains "$out" "board-transition.sh 9 in-review --pr https://github.com/test/repo/pull/12" "apply hint carries PR"
```

Keep `run board-transition.sh 9 in-progress >/dev/null` and the orphan/lint asserts. Where the two deleted asserts were, add:

```bash
assert_contains "$out" "parked    #2: needs-human — waiting on A" "reconcile lists the wake queue"
assert_not_contains "$out" "proposal" "the proposal scanner is gone (v8: no orchestrator)"
```

(#2 was registered `--state needs-human --note "waiting on A"` in Task 1 and never transitions.)

- [ ] **Step 2: Run to verify failure**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | grep -B1 -A3 "wake queue"`
Expected: FAIL — reconcile does not yet print `parked` lines.

- [ ] **Step 3: Rewrite reconcile's section 1**

In `board-reconcile.sh`: delete the whole `# 1. Unapplied proposals in daemon replies` block (through its final `print("          apply: ...")` line) and the now-unused `import shlex`. In its place:

```python
# 1. The wake queue: parked tickets — every one waits on the human.
#    needs-human = a decision/real-world input only they have; needs-info =
#    research must precede gating; interactive-preferred = take it into a
#    live doperpowers:brainstorming session.
for t, n in by_id(tickets.items()):
    if n["state"] in ("needs-human", "needs-info", "interactive-preferred"):
        note = " ".join((n.get("note") or "(no note — lint FAILs this)").split())
        print("parked    #%s: %s — %s" % (t, n["state"], note))
```

Update the header comment (lines 5–10) to:

```
# Lists the human wake queue (parked tickets: needs-human / needs-info /
# interactive-preferred), flags in-progress tickets with no live bound
# daemon, lists dispatchable tickets, and finishes with a board-lint pass.
# There is no proposal scanner: v8 workers write their own ticket states and
# register child/follow-up tickets directly (doperpowers:implementing-tickets).
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -5`
Expected: `all tests passed`

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-reconcile.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): reconcile — 제안 스캐너 제거, 웨이크 큐(파킹 티켓) 보고로 대체"
```

---

### Task 4: reviewing-prs — all parks become `needs-human`

**Files:**
- Modify: `skills/reviewing-prs/references/review-worker-protocol.md:33-34,57-59,96-104,106-108`
- Test: `tests/reviewing-prs/test-review-dispatch.sh` (rendered-prompt asserts, near the existing `assert_not_contains "$PROMPT" "{{"` line)

**Interfaces:**
- Consumes: `in-review → needs-human` legality (Task 1). No `needs-info` writes remain in the review protocol.

- [ ] **Step 1: Add the failing prompt asserts**

After `assert_not_contains "$PROMPT" "{{" "no unsubstituted placeholder survives"` add:

```bash
assert_contains "$PROMPT" "needs-human" "protocol parks route to needs-human (v8)"
assert_not_contains "$PROMPT" "needs-info" "review-loop parks are all human-unparked (v8)"
assert_not_contains "$PROMPT" "→ blocked" "retired blocked vocabulary gone from the protocol"
```

Run: `bash tests/reviewing-prs/test-review-dispatch.sh 2>&1 | tail -8`
Expected: the two new negative/positive asserts FAIL (protocol still says needs-info/blocked).

- [ ] **Step 2: Edit the protocol (4 spots)**

(2a) EVALUATE bullet: `- A finding you cannot verify is an escalation (needs-info), never a` → `- A finding you cannot verify is an escalation (needs-human), never a`

(2b) RE-REVIEW cap: `set ticket #{{ISSUE_NUMBER}} to needs-info with an impasse summary and end your turn.` → `set ticket #{{ISSUE_NUMBER}} to needs-human with an impasse summary and end your turn.`

(2c) AUTHORITY block — replace:

```
YOUR AUTHORITY: ticket #{{ISSUE_NUMBER}}'s open states via
board-transition.sh (confident-ready / needs-info / blocked — note required
for the latter two); registering finding-tickets; merging ONLY in the
self-merge tier AND only when auto-merge is on (auto-merge: {{AUTO_MERGE}} —
if off, the tier being satisfied still means the HUMAN-tier path, not a
merge); done ONLY as post-merge finalize. NEVER: wontfix, other
tickets' states, force-push, opening your own PRs, /codex:cancel.
Escalation discriminant: waiting on an action/precondition → blocked;
waiting on knowledge or a human taste/product decision → needs-info.
```

with:

```
YOUR AUTHORITY: ticket #{{ISSUE_NUMBER}}'s open states via
board-transition.sh (confident-ready / needs-human — note required for
needs-human); registering finding-tickets; merging ONLY in the self-merge
tier AND only when auto-merge is on (auto-merge: {{AUTO_MERGE}} — if off,
the tier being satisfied still means the HUMAN-tier path, not a merge);
done ONLY as post-merge finalize. NEVER: wontfix, other tickets' states,
force-push, opening your own PRs, /codex:cancel. Every park in this loop
waits on the human — write needs-human with the question/impasse/conflict
as the note (who unparks it: the human as themselves).
```

(2d) Push-conflict fallback: `a second rejection → needs-info with the conflict described.` → `a second rejection → needs-human with the conflict described.`

- [ ] **Step 3: Run both suites to verify they pass**

Run: `bash tests/reviewing-prs/test-review-dispatch.sh 2>&1 | tail -3 && bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -3`
Expected: both `all tests passed` (or the dispatch suite's own pass summary).

- [ ] **Step 4: Commit**

```bash
git add skills/reviewing-prs/references/review-worker-protocol.md tests/reviewing-prs/test-review-dispatch.sh
git commit -m "feat(reviewing-prs): 리뷰 루프 파킹 전면 needs-human 전환 (v8 who-unparks 판별식)"
```

---

### Task 5: New skill `implementing-tickets` — doctrine + Protocol v2

**Files:**
- Create: `skills/implementing-tickets/SKILL.md`
- Create: `skills/implementing-tickets/references/implement-worker-protocol.md`
- Create: `tests/implementing-tickets/test-protocol-content.sh` (mode 755)

**Interfaces:**
- Produces: the protocol path `skills/implementing-tickets/references/implement-worker-protocol.md` with placeholder set `{{ISSUE_NUMBER}} {{ISSUE_URL}} {{ISSUE_TITLE}} {{ISSUE_BODY}} {{REPO}} {{BOARD_SCRIPTS}}` — Task 6's dispatch ritual and the next-phase dispatch script both render it.

- [ ] **Step 1: Write the failing content test**

`tests/implementing-tickets/test-protocol-content.sh`:

```bash
#!/usr/bin/env bash
#
# Structural invariants over the implement-worker protocol + skill doctrine.
# Prose is behavior here: these asserts pin the load-bearing clauses so a
# future edit cannot silently drop the gate, resurrect the proposal block,
# or reintroduce retired vocabulary.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROTO="$REPO_ROOT/skills/implementing-tickets/references/implement-worker-protocol.md"
SKILL="$REPO_ROOT/skills/implementing-tickets/SKILL.md"

FAILURES=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
assert_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then pass "$3"; else
        fail "$3"; echo "    expected to find: $2"; fi
}
assert_not_contains() {
    if printf '%s' "$1" | grep -Fq -- "$2"; then
        fail "$3"; echo "    expected NOT to find: $2"; else pass "$3"; fi
}

echo "protocol content:"
[ -f "$PROTO" ] || { echo "missing $PROTO"; exit 1; }
proto="$(cat "$PROTO")"
assert_contains "$proto" "THE GATE comes before everything" "gate precedes everything"
assert_contains "$proto" "WELL-DEFINED" "check 1 present"
assert_contains "$proto" "WELL-SCOPED" "check 2 present"
assert_contains "$proto" "Even minor taste is never your call" "minor-taste rule present"
assert_contains "$proto" "VERDICT IS YOUR FIRST BOARD WRITE" "verdict-first-write present"
assert_contains "$proto" "WHO UNPARKS IT" "park discriminant present"
assert_contains "$proto" "a chain IS" "serialization-as-edges present"
assert_contains "$proto" "## Roadmap" "JIT roadmap escape hatch present"
assert_contains "$proto" "FOLLOW-UPS: none" "follow-ups contract present"
assert_contains "$proto" "A follow-up not registered does not exist" "direct registration doctrine"
assert_contains "$proto" "Closes #{{ISSUE_NUMBER}}" "merge-closes contract present"
assert_contains "$proto" "NO orchestrator" "no-orchestrator doctrine"
assert_contains "$proto" "doperpowers:execplan" "execplan mode wired"
assert_contains "$proto" "doperpowers:reviewing-prs" "handoff to the review loop named"
assert_not_contains "$proto" '"ticket":' "the JSON proposal block is dead"
assert_not_contains "$proto" "→ blocked" "no retired blocked vocabulary"
assert_not_contains "$proto" "status:blocked" "no retired blocked label"

echo "placeholders:"
want="{{BOARD_SCRIPTS}} {{ISSUE_BODY}} {{ISSUE_NUMBER}} {{ISSUE_TITLE}} {{ISSUE_URL}} {{REPO}}"
got="$(grep -o '{{[A-Z_]*}}' "$PROTO" | sort -u | tr '\n' ' ' | sed 's/ $//')"
if [ "$got" = "$want" ]; then pass "placeholder set is exactly: $want"; else
    fail "placeholder set drifted"; echo "    expected: $want"; echo "    actual:   $got"; fi

echo "skill doctrine:"
[ -f "$SKILL" ] || { echo "missing $SKILL"; exit 1; }
skill="$(cat "$SKILL")"
assert_contains "$skill" "name: implementing-tickets" "frontmatter name"
assert_contains "$skill" "references/implement-worker-protocol.md" "skill points at the protocol"
assert_contains "$skill" "doperpowers:issue-tracker" "skill points at the board schema"
assert_not_contains "$skill" "status:blocked" "no retired vocabulary in doctrine"

echo
if [ "$FAILURES" -gt 0 ]; then echo "$FAILURES test(s) FAILED"; exit 1; fi
echo "all tests passed"
```

Run: `bash tests/implementing-tickets/test-protocol-content.sh`
Expected: `missing .../implement-worker-protocol.md` → exit 1.

- [ ] **Step 2: Write the protocol reference**

`skills/implementing-tickets/references/implement-worker-protocol.md` — exact content:

```
You are an IMPLEMENT worker for ticket #{{ISSUE_NUMBER}} ({{ISSUE_URL}}) in
{{REPO}}, running unattended in your own worktree. There is NO orchestrator
in this loop: your escalation targets are the board itself (states, notes,
comments) and the human on their next wake. Turn-end messages are audit
trail, not requests — nobody answers them. Your ticket brief is at the
bottom of this prompt; treat it as the source of truth.

Toolkit:
- board scripts: {{BOARD_SCRIPTS}}

THE GATE comes before everything. Do not open a source file until the
ticket passes. Interrogate the brief the way a brainstorming grill
interrogates a human — but every answer must come from the ticket body, the
codebase, or repo docs. Trivial lookups (docs, grep, an API's actual shape)
are orient work: do them, never park for them.

Check 1 — WELL-DEFINED. Classify every fork the implementation will hit:
- Mechanical/technical with one obvious best answer (internal naming,
  idiomatic choice, repo precedent) → YOUR call. Parking these is a
  protocol violation, not caution.
- Non-trivial architecture (subsystem boundary, data model, API shape) →
  must be answered by ticket + codebase; unanswered → gate-fail.
- Product design or taste, major OR minor (user-facing behavior, wording,
  interaction/visual choices — anywhere a reasonable human could prefer
  differently on non-technical grounds) → must be answered by the ticket;
  unanswered → gate-fail. Even minor taste is never your call.

Check 2 — WELL-SCOPED. The work must fit this ticket as one purpose-unit
(roughly 1–2 ExecPlans). Too big? One question decides: can the remainder
be written down as self-contained child pre-specs right now?
- Yes → DECOMPOSE. Register children:
  {{BOARD_SCRIPTS}}/board-register.sh "<title>" <bug|enhancement> <P0..P3> --parent {{ISSUE_NUMBER}}
  (+ --blocked-by between siblings where order matters; a chain IS
  serialization; + --state S --note "<why>" for a child born parked). Then
  flesh out each child body (gh issue edit <n> --body-file -) to the
  pre-spec bar: a fresh-context worker can start from the body alone.
  Gate-triage each child honestly: ready-for-agent only if YOU believe it
  passes this gate; an open human decision → born needs-human;
  product-core → born interactive-preferred — required notes always.
  Register only children you can spec self-contained NOW; contingent later
  phases live as a "## Roadmap" section in the parent body — the worker
  finishing phase K registers phase K+1 at PR time. Update the parent
  (roadmap + a Decision log entry: why this cut), end your turn. Write no
  code.
- No — the slices need one continuously steered human context →
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} interactive-preferred "<which decision areas need steering>"
  and end your turn.

VERDICT IS YOUR FIRST BOARD WRITE. Dispatch wrote nothing.
- Pass → {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-progress
  then a one-line gate comment:
  gh issue comment {{ISSUE_NUMBER}} --body "[gate] pass — <direct|execplan>: <one line>"
- Fail → the park state itself, with the required note. Park discriminant —
  WHO UNPARKS IT:
  - The human as themselves — a decision only they can make, or a
    real-world input only they possess (credentials, auth, production
    data) → needs-human. Note = the crisp question list, each with your
    recommended answer.
  - Knowledge work anyone could do, but substantial enough to be its own
    work-unit (or its outcome needs human review before decisions harden)
    → needs-info. Note = what is missing and why gating cannot proceed.
  - Ongoing steering, not one answer → interactive-preferred.
  End your turn stating the park crisply.

EXECUTION (gate passed) — name the mode in the gate comment:
- DIRECT: the pre-spec is the plan — TDD
  (doperpowers:test-driven-development), commit frequently, open the PR.
- EXECPLAN: 2+ milestones, or enough files/design sequencing that a fresh
  session would need the document to survive context death →
  doperpowers:execplan (the gate already served as its grill; author the
  ExecPlan from ticket + gate findings, execute to the letter).

YOUR AUTHORITY: your OWN ticket's open states via board-transition.sh
(never raw gh for status labels); registering decomposition children
(--parent {{ISSUE_NUMBER}}) and follow-up tickets (--spawned-by
{{ISSUE_NUMBER}}) directly. NEVER: terminal states (done arrives by merge —
your PR body MUST say "Closes #{{ISSUE_NUMBER}}"; wontfix is the human's
call — to recommend it, park needs-human with the recommendation as the
note); other tickets' states (a cross-ticket observation is a comment on
that ticket, nothing more); scope beyond the ticket.

Opening your PR closes out your scope:
{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-review "<one-line>" --pr <URL> --branch <branch>
Register every residual as a ticket (--spawned-by {{ISSUE_NUMBER}}) BEFORE
your turn-end message, then list what you registered (numbers) in a
FOLLOW-UPS section — or the literal line "FOLLOW-UPS: none". A follow-up
not registered does not exist. From the PR on, the review loop
(doperpowers:reviewing-prs) owns the path to merge.

---- Ticket #{{ISSUE_NUMBER}} brief: {{ISSUE_TITLE}} ----
{{ISSUE_BODY}}
```

- [ ] **Step 3: Write the SKILL.md**

`skills/implementing-tickets/SKILL.md` — exact content:

```markdown
---
name: implementing-tickets
description: Use when dispatching implementation workers onto board tickets, gating a ticket before building (well-defined + well-scoped), parking tickets (needs-human / needs-info / interactive-preferred), decomposing an oversized ticket into child tickets, or choosing direct-vs-execplan execution — the implement-side autonomous loop; the inverse of doperpowers:reviewing-prs.
---

# Implementing Tickets — the autonomous implement loop

## Overview

The implement-side mirror of doperpowers:reviewing-prs: where the review
loop puts its rigor gate at the END of the pipeline (confident-ready before
merge), this loop puts its rigor gate at the START — **a worker may not
write code until the ticket passes the Ticket Gate**. There is NO
orchestrator: a worker's escalation targets are the board itself (states,
notes, comments) and the human on their next wake; turn-end messages are
audit trail, not requests. Full design + rationale:
`docs/doperpowers/specs/2026-07-09-implement-worker-autonomy-design.md`.

## The pieces

| piece | what |
|---|---|
| `references/implement-worker-protocol.md` | the Implement Worker Protocol — rendered (`{{PLACEHOLDERS}}`) into every spawn prompt |
| The Ticket Gate | the pre-code pass/park verdict (below) |
| board schema + dispatch ritual | owned by doperpowers:issue-tracker (states, scripts, the mechanical ritual, the wake ritual) |
| `scripts/` | empty this phase — the auto-attach trigger (`implement-dispatch.sh` + workflow template) lands here next phase |

## The Ticket Gate

Runs during ORIENT, before any source file opens — brainstorming's grill in
absentia: every answer must come from the ticket body, the codebase, or
repo docs. Trivial lookups are orient work, never a park.

**Check 1 — well-defined.** Every fork the implementation will hit:

| fork class | who answers |
|---|---|
| mechanical/technical, one obvious best answer | the worker — parking these is a protocol violation, not caution |
| non-trivial architecture (subsystem boundary, data model, API shape) | ticket + codebase; unanswered → gate-fail |
| product design or taste, **major or minor** | the ticket; unanswered → gate-fail — even minor taste is never the worker's call |

**Check 2 — well-scoped.** Fits ~1–2 ExecPlans. Too big forks on ONE
question: *can the remainder be written as self-contained child pre-specs
right now?* Yes → decompose. No → `interactive-preferred`.

**The verdict is the worker's first board write.** Dispatch writes nothing;
`in-progress` + a `[gate]` comment = pass, a park state = fail.

## Park discriminant — who unparks it?

- **The human as themselves** (a decision only they can make, or a
  real-world input only they possess: credentials, auth, production data)
  → `needs-human`. Note = the question list, each with a recommended answer.
- **Knowledge work anyone could do** but substantial enough to be its own
  work-unit → `needs-info` (rare by design — the research threshold above
  keeps orient-work lookups out of it).
- **Ongoing steering, not one answer** → `interactive-preferred` — summons
  the human into a live doperpowers:brainstorming session; the note says
  which decision areas need steering.

## Decompose — the one scoping behavior

Children via `board-register.sh --parent <original>`; sibling ordering via
`--blocked-by` (a chain IS serialization — serial vs parallel is a
dependency shape, not a policy branch). `--spawned-by` stays reserved for
scope-outs/follow-ups discovered during work. Each child is gate-triaged
honestly at registration (`ready-for-agent` only if the worker believes it
passes the gate). Register only children specifiable as self-contained
pre-specs NOW; contingent phases live as a `## Roadmap` section in the
parent body — the worker finishing phase K registers phase K+1 at PR time.
The parent becomes an epic (never dispatched; the sweeps move it). The
decomposing worker writes no code. Recursion is emergent: each child's
worker re-runs the same gate; no depth machinery exists.

## Execution — two modes on gate pass

- **Direct** — the pre-spec is the plan: TDD, commit, PR.
- **ExecPlan** — doperpowers:execplan when the work has 2+ milestones or
  enough design sequencing that a fresh session would need the document to
  survive context death. The gate already served as execplan's grill.

There is no in-daemon execspec mode: work that wants a living spec with a
human at the gates is precisely `interactive-preferred`.

## Worker authority

Own ticket's open states via `board-transition.sh`; direct registration of
decomposition children (`--parent`) and follow-up tickets (`--spawned-by`).
NEVER: terminal states (`done` arrives by the PR's `Closes #N` merge;
`wontfix` is recommended via a `needs-human` park, decided by the human),
other tickets' states (cross-ticket observations are comments), scope
beyond the ticket. There is no proposal block — with no judge to receive
proposals, registration and comments are the only channels.

## Edge cases

- **Dispatched onto an epic** — refuse: epics are never dispatched; end the
  turn naming the mistake (the sweep owns epic states).
- **needs-human answered in comments** — the human flips the ticket back to
  `ready-for-agent`; the next dispatch re-runs the gate with the comments
  as ticket content. Answers belong in the body/comments, not in chat.
- **Worker dies mid-build** — `board-reconcile.sh` flags the orphaned
  `in-progress` ticket; respawn re-runs the gate from fresh context (prior
  `[gate]` comments are context, not inherited trust).
- **Gate-fail discovered mid-build** (a taste fork surfaces only once code
  exists) — same protocol, late: park (`in-progress → needs-human` /
  `interactive-preferred` are legal), commit WIP to the branch, state the
  park crisply, end the turn.

## Interim dispatch

Until the auto-attach trigger lands, dispatch is the mechanical ritual in
doperpowers:issue-tracker (render this skill's protocol → spawn → bind —
no board write, no judgment). The trigger phase replaces only who invokes
it.
```

- [ ] **Step 4: Run the content test**

Run: `chmod +x tests/implementing-tickets/test-protocol-content.sh && bash tests/implementing-tickets/test-protocol-content.sh`
Expected: `all tests passed`

- [ ] **Step 5: Commit**

```bash
git add skills/implementing-tickets tests/implementing-tickets
git commit -m "feat(implementing-tickets): 신규 스킬 — 티켓 게이트 + 구현 워커 프로토콜 v2 (reviewing-prs 대칭)"
```

---

### Task 6: issue-tracker SKILL.md rewrite + issue-register ripple

**Files:**
- Modify: `skills/issue-tracker/SKILL.md` (full rewrite — complete replacement content below)
- Modify: `skills/issue-register/SKILL.md` (two surgical edits)

**Interfaces:**
- Consumes: Task 5's protocol path (the dispatch ritual renders it). Produces: the board manual every worker protocol references as "the schema".

- [ ] **Step 1: Replace `skills/issue-tracker/SKILL.md` in full**

Exact new content:

````markdown
---
name: issue-tracker
description: Use when managing the issue board — registering tickets, running the mechanical dispatch ritual, working the wake queue (needs-human / needs-info / interactive-preferred), reconciling the board after time away, or asking what is in progress / parked / dispatchable. The board IS the repo's GitHub issues; the toolkit lives in this skill's scripts/.
---

# Issue Tracker

A repo's issue board, stored where it cannot fork: **GitHub Issues is the
single source of truth.** Tickets are **purpose-units**: born as pre-specs
from `issue-register`, gated and driven to a PR by autonomous implement
workers (doperpowers:implementing-tickets), reviewed to a confident merge by
review workers (doperpowers:reviewing-prs), tracked as GitHub issues with
typed edges (sub-issue = parent, dependency = blocked-by, provenance =
spawned-by).

There is no local board file, nothing to sync, and no worktree restriction —
every script talks to GitHub directly (`gh` required, fail-loud) and may run
from any checkout. `doperpowers/issue-tracker/` in the consumer repo survives
only as a gitignored render cache for `board-map.sh`.

**There is no orchestrator-judge.** Dispatch is mechanical (the ritual
below): it renders a protocol, spawns a worker, and writes nothing. Workers
write their own ticket's open states and register child/follow-up tickets
directly, under their protocol's authority rules. Everything that needs a
human lands on the board as a parked state and waits for the wake ritual.
All writes go through the scripts (the Hard Gate below).

## The Board Write Hard Gate (put this in the consumer CLAUDE.md)

> Board Write Hard Gate: issue creation and every state/edge change MUST go
> through the issue-tracker scripts — never raw `gh issue edit` for
> `status:*` labels or sub-issue/dependency edges. At registration, category +
> status + parent + blocked-by are each either set or consciously N/A —
> silence is not N/A.

The scripts are the schema: they enforce the state machine, mandatory notes,
PR gates, and cycle/deadlock checks that GitHub's API will not.
`board-lint.sh` catches what slips past (run it on wake; wire it to cron for
unattended repos).

## Who writes the board

| writer | writes | doctrine |
|---|---|---|
| **Implement worker** (daemon, one ticket) | its OWN ticket's open states; NEW child/follow-up tickets | doperpowers:implementing-tickets |
| **Review worker** (daemon, one PR) | its PR's ticket (`confident-ready` / `needs-human`); finding-tickets; post-merge finalize | doperpowers:reviewing-prs |
| **The human** (wake ritual) | everything else — unpark answers, `wontfix`, finalize, priorities, edge re-cuts | this file |
| **Dispatcher** (interim: a human-run ritual; next phase: an issue-event trigger) | NOTHING | the ritual below |

## State vocabulary

`ready-for-agent → in-progress → in-review → done` is the happy path; under
the review loop (doperpowers:reviewing-prs) a PR passes through
`confident-ready` between `in-review` and `done`.

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `ready-for-agent` | open + `status:ready-for-agent` | pre-spec complete; dispatchable once blockers are done | — |
| `in-progress` | open + `status:in-progress` | a worker passed the gate and is driving it (an epic stays here while children run) | optional |
| `needs-human` | open + `status:needs-human` | parked for the human **as themselves**: a decision only they can make, or a real-world input only they possess (credentials, auth, production data) | **required** |
| `needs-info` | open + `status:needs-info` | rare: the spec is unambiguous but lacks depth for a sophisticated result, or core decisions need substantial research first | **required** |
| `interactive-preferred` | open + `status:interactive-preferred` | the ticket's shape wants continuous human steering — never auto-dispatched; take it into a live doperpowers:brainstorming session | **required** |
| `in-review` | open + `status:in-review` | PR open (review rounds, conflicts, merge queue — all of it) | PR link |
| `confident-ready` | open + `status:confident-ready` | PR rigorously reviewed (reviewing-prs loop); merge/close with confidence | optional |
| `done` | **closed — completed** | landed — normally arrives by the merge itself (PR body `Closes #N` auto-closes); manual flip for non-PR work only, verify it landed first | optional |
| `wontfix` | **closed — not planned** | rejected | **required** |
| `deferred` | open + `status:deferred` | tracked, not now | optional |

**Park discriminant — who unparks it?** The human acting as themselves (a
decision, or a real-world input) → `needs-human`. Knowledge work that anyone
could in principle do (substantial research, spec-deepening) → `needs-info`.
Not one answer but ongoing steering → `interactive-preferred`. (`blocked`
was retired in v8: its meaning was absorbed by `needs-human`; lint names any
legacy label with the migration FIX.)

Exactly one `status:*` label on every open issue; terminal states are the
close reason (no label). An issue outside this scheme is `untracked` (no
label) or `conflict` (2+ labels) — lint FAILs it; `board-transition.sh`
repairs it (any open state is reachable from either).

Ticket dependencies are **edges** (native GitHub dependencies), never states —
eligibility is computed. Edges are born at register time and re-cut later with
`board-edge.sh` (understanding changes; the graph follows). Epics (issues with
sub-issues) are never dispatched; the sweep moves them automatically. Notes
land twice: the current note in the issue's `board:meta` body block, the audit
trail as `[board]` comments.

## Toolkit

Paths relative to this skill's `scripts/` directory. Ticket ids are issue
numbers (`42` or `#42`). Target repo = `$BOARD_REPO` (owner/name) or the
checkout's repo.

| script | does |
|---|---|
| `board-register.sh <title> <category> <priority> [--state S] [--note N] [--parent N] [--blocked-by N,N] [--spawned-by N] [--body-file F]` | open the issue with labels + typed edges; priority (`P0`…`P3`, P0 = drop everything) is REQUIRED and becomes the managed `priority:*` label; prints `<number> <url>` — then the registrar fleshes out the pre-spec body (`gh issue edit <n> --body-file …`) |
| `board-transition.sh <n> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes + the in-review PR gate; runs the epic/unblock sweeps; repairs untracked/conflict issues. Re-run `<n> done` on a merge-auto-closed ticket to **finalize** (strip the stale label + run the sweeps; idempotent) |
| `board-edge.sh <n> --block N \| --unblock N \| --parent N \| --orphan` | re-cut edges after birth (one op per call): add/cut a dependency, move under another epic, or leave one. Rejects self-edges, cycles, ancestor-epic blockers; runs the same epic sweeps as transition |
| `board-relate.sh <a> <b> [--cut]` | symmetric relates annotation (board:meta) — rendered by board-map, no effect on eligibility |
| `board-priority.sh <n> <P0..P3>` | re-prioritize: swap the `priority:*` label (repairs a double label); prints `#n: P2 → P0` |
| `board-list.sh [state]` | board view in dispatch order (P0 rows first, unprioritized last); `ELIGIBLE` tag = dispatchable, `CLOSE?` tag = close candidate (see the ritual) |
| `board-map.sh [--write\|--serve\|--stop]` | human telemetry. `--write` renders **`BOARD.html`** (interactive layered-DAG: pan/zoom, node detail, state filter, epic collapse — plus a kanban view toggle) and **`BOARD.md`** (table) into the gitignored render dir. `--serve` additionally serves the render dir on 127.0.0.1 (per-repo port; `$BOARD_PORT` overrides) and opens the board over http — served tabs **hot-reload**: every later render (explicit `--write`, or the automatic one each mutating script fires while the server is up) appears without a manual refresh. `--stop` kills the server. No argument prints the table. Prefer `--serve` when a human will keep the board open |
| `board-show.sh <n>` | node + issue URL + bound daemon |
| `board-bind.sh <uuid> <n>` | record which daemon owns the ticket (in the daemon registry) |
| `board-reconcile.sh` | read-only catch-up: the wake queue (parked tickets), orphaned tickets, dispatchables, then a lint pass |
| `board-lint.sh` | schema invariants over the live board: one status label per open issue, none on closed, notes where required (the park trio + wontfix), no dependency cycles, at most one priority label (missing priority is a WARN — backfill legacy tickets with `board-priority.sh`), the retired `status:blocked` label named with its migration FIX. Also WARNs close candidates. `FAIL … FIX: …` lines, exit 1 |
| `board-migrate-gh.sh [--board FILE] [--apply]` | one-shot v6→v7 migration: push a legacy `board.json` into GitHub (dry-run by default; legacy `blocked` lands as `needs-human`) |

## Remote board (hosted)

`board-map.sh --serve` renders locally on demand. For an always-current hosted
view, a workflow re-renders BOARD.html on every issue event (plus a cron safety
net — sub-issue/dependency edits fire no webhook) and deploys it. Hosted pages
hot-reload the same way served local tabs do (the page polls its own caching
headers), so a browser left open tracks each redeploy. Two templates,
pick by repo visibility:

- **Public repo → GitHub Pages.** Copy `references/board-pages.yml` into
  `.github/workflows/` and set Pages → Source to "GitHub Actions". Zero external
  accounts. Note: a Pages site is *public* even for a private repo on
  non-Enterprise plans — and on Free/most org plans, private-repo Pages is
  unavailable entirely.
- **Private repo → Cloudflare Pages + Access.** Copy
  `references/board-cloudflare-pages.yml`. It deploys to Cloudflare Pages behind
  Cloudflare Access, giving a **private, team-authenticated URL** (the only way
  to host a private board below GitHub Enterprise). Read the template header:
  set up Access *before* the first deploy, or there is a window where issue
  titles are public.

## The dispatch ritual (mechanical — no judgment)

1. `board-list.sh` → pick the TOP `ELIGIBLE` ticket — rows already print in
   dispatch order (P0 before P1 before …; unprioritized last). A row tagged
   `CLOSE?` is a **close candidate**: every linked PR merged/closed (≥1
   merged) yet the issue is open — usually a PR that skipped `Closes #N`.
   Triage it before spawning anything: if the work landed, walk it to `done`
   (or `wontfix "superseded by PR"`); if work genuinely remains, dispatch as
   normal. Derived from GitHub PR state on every snapshot — never a label,
   never auto-closed.
2. Render the Implement Worker Protocol
   (`doperpowers:implementing-tickets` →
   `references/implement-worker-protocol.md`): substitute every
   `{{PLACEHOLDER}}` (`ISSUE_NUMBER`, `ISSUE_URL`, `ISSUE_TITLE`, `REPO`,
   `BOARD_SCRIPTS` = this skill's scripts dir, `ISSUE_BODY` = the full
   issue body from `gh issue view <n> --json body`).
3. `daemon-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>` (from
   `orchestrating-daemons` — always a worktree; workers write code).
4. `board-bind.sh <uuid> <n>`. Write NOTHING else: the worker's first board
   write is its gate verdict — `in-progress` (+ a `[gate]` comment) means
   the gate passed; a park state means it failed.

Nobody judges turn-ends. Parked tickets wait for the wake ritual; opened PRs
are picked up by the review loop (doperpowers:reviewing-prs). The next phase
replaces step 3's invoker with an issue-event trigger
(doperpowers:implementing-tickets `scripts/`, when it lands) — the ritual
itself does not change.

**Ad-hoc daemons are a different animal:** fleets you spawn conversationally
for your own work follow doperpowers:orchestrating-daemons and its judge
rubric. Board pipeline workers do not — their doctrine is
implementing-tickets / reviewing-prs, and nobody sits between them and the
board.

## The wake ritual (the human's catch-up)

1. `board-reconcile.sh` — the wake queue (parked tickets with notes),
   orphaned in-progress tickets, dispatchables, then a lint pass.
2. Answer the parks, on the ticket (answers belong in the body/comments —
   the next worker reads the ticket, not your chat):
   - `needs-human` → answer the note's questions in a comment (or edit the
     body), then `board-transition.sh <n> ready-for-agent` — the next
     dispatch re-runs the gate against the enriched ticket.
   - `needs-info` → do (or delegate) the research; fold the findings into
     the body; back to `ready-for-agent`.
   - `interactive-preferred` → take it into a live doperpowers:brainstorming
     session (the note says which decision areas need steering); the session
     ends in a controlled-track build, a decomposition into gate-passing
     children, or a re-spec back to `ready-for-agent`.
3. Finalize merges: `board-transition.sh <n> done` on merge-auto-closed
   tickets (lint's FIX line says the same). Workers registered their own
   follow-ups at PR time — verify against the PR's FOLLOW-UPS section; a
   follow-up not registered does not exist.
4. Triage `CLOSE?` rows: verify & close (`done` / `wontfix`), or re-scope.
5. `wontfix` recommendations arrive as `needs-human` parks with the
   recommendation in the note — the close is yours, never a worker's.

## Worker protocols

The implement-side protocol lives in doperpowers:implementing-tickets
(`references/implement-worker-protocol.md`); the review-side protocol in
doperpowers:reviewing-prs (`references/review-worker-protocol.md`). Both are
embedded VERBATIM in spawn prompts. This file owns only the schema they
write against.

## The ticket body (pre-spec)

The issue body — seeded by register, fleshed out by the registrar (register
time, plus a terminal outcome comment). Sections: Problem & intent /
Constraints / Success criteria / Open questions / Decision log — plus, on a
decomposed parent, Roadmap (the one sanctioned form of "ticket that doesn't
exist yet"). The trailing `<!-- board:meta … -->` block is script-owned
(spawned-by / relates-to / branch / pr / note) — edit around it, never
inside it.

## Scope-outs become tickets (deferral rule)

Work deliberately deferred out of scope — during a grill, a brainstorm, an
issue-register session, a worker's gate/decomposition, or a worker's PR-time
follow-ups — is registered on the board THE MOMENT the deferral is decided,
by whoever decided it (v8: workers register directly; there is no proposal
queue), with its lineage as edges:

- `--parent <epic>` — decomposition children (they ARE the parent's content,
  sliced) and work that belongs to an existing epic
- `--spawned-by <origin>` — scope-outs and follow-ups discovered during work
- `--blocked-by <numbers>` — what must land first

Deferral without a ticket is silent scope loss: the decision exists only in
the design conversation and dies with the session. The ticket's Decision log
records *why* it was cut, so nobody re-litigates it later.

PR landing is a deferral point like any other. A PR that addresses its
ticket but leaves work behind still closes the ticket (`Closes #N` stays in
the body: done means the PR landed, not that every idea it surfaced died).
The worker registers the residue as tickets (`--spawned-by <n>`) BEFORE its
turn-end message and lists the numbers in its FOLLOW-UPS section — a
follow-up not registered does not exist.

## Edge cases

- A merged PR auto-closed its ticket (`Closes #N`) → the board already reads
  it `done`; the stale status label and unswept epics are what's left. Run
  `board-transition.sh <n> done` to finalize — reconcile's lint pass names
  these tickets.
- A merged PR did NOT close its ticket (no `Closes #N`) → the ticket becomes
  a **close candidate**: lint WARNs it, `board-list.sh` tags it `CLOSE?`, and
  the kanban view pulls it into a close-candidate column (in-progress /
  in-review tickets stay put — a merged part-1 PR mid-flight is normal, they
  only carry the mark). Human verifies and closes; never auto-closed.
- `orphaned` in reconcile → the worker died: respawn (the fresh worker
  re-runs the gate from scratch — prior `[gate]` comments are context, not
  inherited trust), re-bind, resume the ticket.
- A wontfix blocker makes a dependent `STUCK` — re-cut the edge
  (`board-edge.sh <n> --unblock <blocker>`) or wontfix the dependent; that is
  a human call.
- An issue labeled by hand (or by external automation) lands `untracked` /
  `conflict` → lint names it; `board-transition.sh` repairs it. A legacy
  `status:blocked` label is a special case of conflict — lint's FIX line
  carries the `needs-human` migration.
- Consumer label automation that already speaks `status:*` (e.g. assign →
  `status:in-progress`) is a legitimate board writer — same store, same
  vocabulary, no sync. Its managed-label set must track the v8 vocabulary
  (add `status:needs-human` / `status:interactive-preferred`, drop the
  retired `status:blocked`).
````

- [ ] **Step 2: issue-register ripples (two edits)**

Edit 1 — in the checklist step 6, replace:

```
state `ready-for-agent` when complete & unblocked, `--state needs-info` when open questions remain, `--state deferred` when parked, `--state blocked` for non-ticket blockage — `needs-info` and `blocked` need `--note`).
```

with:

```
state `ready-for-agent` when complete & unblocked, `--state needs-human` when a human decision or real-world input is the blocker, `--state needs-info` when substantial research must precede core decisions, `--state interactive-preferred` when the grill already shows the work is product-core and should be driven live with a human, `--state deferred` when parked — the three park states need `--note`).
```

Edit 2 — in The Ticket Artifact section, replace:

```
Cluster hierarchy → `--parent`; ordering → `--blocked-by`; parked → `--state
deferred`; open-questions-remain → `--state needs-info`.
```

with:

```
Cluster hierarchy → `--parent`; ordering → `--blocked-by`; parked → `--state
deferred`; open human decisions → `--state needs-human`; research-first →
`--state needs-info`; product-core, wants live steering → `--state
interactive-preferred`.
```

- [ ] **Step 3: Verify no stale vocabulary or dangling references**

Run: `grep -rn "status:blocked\|→ blocked\|blocked/needs-info\|judging daemon state proposals\|proposal block" skills/issue-tracker/SKILL.md skills/issue-register/SKILL.md | grep -v "retired\|legacy"`
Expected: no output (every surviving `status:blocked` mention is a retirement/migration note, filtered by the second grep). Also run `grep -n "Worker Protocol" skills/issue-tracker/SKILL.md` — expected: only the "Worker protocols" pointer section (no embedded protocol block remains).

Run: `bash tests/implementing-tickets/test-protocol-content.sh && bash tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -3`
Expected: both pass.

- [ ] **Step 4: Commit**

```bash
git add skills/issue-tracker/SKILL.md skills/issue-register/SKILL.md
git commit -m "docs(issue-tracker,issue-register): v8 보드 매뉴얼 — 판관 폐지, 기계적 디스패치 리추얼 + 웨이크 리추얼"
```

---

### Task 7: Release — version bump + codex-plugin sync

**Files:**
- Modify: `package.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json` (via script)
- Modify: `.codex-plugin/` skill tree (via sync script)

- [ ] **Step 1: Bump the minor version**

Run: `scripts/bump-version.sh 7.10.0 && scripts/bump-version.sh --check`
Expected: all declared files report `7.10.0`, no drift.

- [ ] **Step 2: Sync the codex plugin**

Run: `scripts/sync-to-codex-plugin.sh`
Expected: rsync preview + apply showing `skills/implementing-tickets/` added and the modified issue-tracker/reviewing-prs files updated. (If the script requires network/gh and fails in this environment, record that in the commit message and leave the sync for the maintainer — do NOT hand-edit `.codex-plugin`.)

- [ ] **Step 3: Shell lint**

Run: `scripts/lint-shell.sh`
Expected: no new shellcheck violations (baseline unchanged or improved).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "release: 7.10.0 — 구현 워커 자율성: 티켓 게이트, 보드 스키마 v8, implementing-tickets 스킬"
```

---

### Task 8: Consumer migration (ida-solution) + final verification

**Files:**
- Modify (consumer repo): ida-solution `.github/workflows/issue-status-labels.yml`
- Live board writes via the v8 scripts (`BOARD_REPO` env)

This task touches the LIVE ida-solution board and repo — outward-facing, but it is the deliverable's deployment. Work from this repo's checkout; the scripts take `BOARD_REPO`.

- [ ] **Step 1: Pre-create the v8 labels and find legacy `blocked` tickets**

```bash
export BOARD_REPO="$(gh repo list --json nameWithOwner --jq '.[].nameWithOwner' | grep -i 'ida-solution' | head -1)"
gh label create status:needs-human -R "$BOARD_REPO" --color d93f0b --description "issue-tracker board state" --force
gh label create status:interactive-preferred -R "$BOARD_REPO" --color d4c5f9 --description "issue-tracker board state" --force
skills/issue-tracker/scripts/board-lint.sh
```

Expected: lint FAILs any open `status:blocked` ticket with `FIX: board-transition.sh <n> needs-human "<carried note>"` (possibly zero — then skip step 2).

- [ ] **Step 2: Migrate each named ticket**

For each ticket lint named, carry its existing note (`board-show.sh <n>` shows it):

```bash
skills/issue-tracker/scripts/board-transition.sh <n> needs-human "<carried note>"
```

Then: `skills/issue-tracker/scripts/board-lint.sh` — expected exit 0 (WARNs allowed). Only after zero holders: `gh label delete status:blocked -R "$BOARD_REPO" --yes`.

- [ ] **Step 3: Update the consumer label automation**

In the ida-solution clone (`gh repo clone` if absent), edit `.github/workflows/issue-status-labels.yml`: in its MANAGED label set, remove `status:blocked` and add `status:needs-human`, `status:interactive-preferred` (keep `status:confident-ready` and the `synchronize` demotion rule intact). Commit and push to the consumer's default flow:

```bash
git -C <ida-solution-clone> add .github/workflows/issue-status-labels.yml
git -C <ida-solution-clone> commit -m "chore(board): v8 상태 어휘 — needs-human/interactive-preferred 추가, blocked 제거"
git -C <ida-solution-clone> push
```

- [ ] **Step 4: Final verification — the spec's acceptance, as written**

Full suites:

```bash
bash tests/issue-tracker/test-board-scripts.sh
bash tests/reviewing-prs/test-review-dispatch.sh
bash tests/implementing-tickets/test-protocol-content.sh
scripts/lint-shell.sh
```

Expected: every suite ends `all tests passed` (dispatch suite: its own pass summary), shellcheck baseline clean.

Spec acceptance items (schema/scripts section), each already pinned by a suite assert — verify the run output names them: (1) park-trio legality + note enforcement + repair; (2) `blocked` rejected + retired-label lint FIX; (3) `interactive-preferred` never ELIGIBLE, own kanban column, `--state` accepted; (4) `in-review → needs-human` legal / `→ blocked` rejected; (5) rendered review protocol carries no `blocked`/`needs-info` vocabulary.

Consumer: `BOARD_REPO=<ida-solution> skills/issue-tracker/scripts/board-lint.sh` → exit 0 on the migrated board.

The spec's five protocol scenarios (clean ticket → direct build; buried minor-taste fork → needs-human; oversized-sliceable → decompose; product-core → interactive-preferred; considerable → execplan) are LIVE-shakedown acceptance: they require spawning real workers and are run on ida-solution scratch tickets after this lands, per the spec's Acceptance table — record outcomes in the spec's `## Outcomes & Retrospective`. Do not fake them with mocks.

- [ ] **Step 5: Update the spec's living tail and commit**

Add to the spec's `## Revision Notes`: one line stating implementation landed, tests green, consumer migrated (with date). Then:

```bash
git add docs/doperpowers/specs/2026-07-09-implement-worker-autonomy-design.md
git commit -m "docs(spec): 구현 워커 자율성 — 구현 완료 리비전 노트"
```
