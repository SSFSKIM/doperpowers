# Implement Lane Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the E1 lane-split cutover — `ready-for-agent` splits into
`ready-for-architect` / `in-design` / `ready-for-implementer`, with the
Architect (Fable) / Implementer (Opus) relay encoded in board states —
across the board toolkit, dispatch, skills, registrars, and tests, per
`docs/doperpowers/specs/2026-07-30-implement-lane-split-design.md` (v1.3).

**Architecture:** One atomic vocabulary cutover (an intermediate state
where dispatch reads states the board no longer emits is invalid), built
as: (1) a behavior-preserving mechanical rename + final `LEGAL` table,
suite green; (2) new behaviors added test-first on top (birth
classification, `plan:`/`pre-park:` meta, convergence enforcement, lane
dispatch, sweep recovery); (3) the skill split (`implementing-tickets` →
`architecting` + `implementing`); (4) registrar/doc alignment; (5) live
board migration. The QAgent Opus pin + `fix-wave` agent declaration are
**deliberately out of scope** — they only bind on the plain-Claude review
route C5 (doperpowers#32) establishes, so they ride with C5 as a
follow-up ticket this plan registers at the end (the spec delegates this
call to the plan).

**Tech Stack:** bash (macOS bash 3.2 compatible), Python 3 stdlib
(`_board.py`), TypeScript + vitest (triaging-feedback), shell test
harness with a PATH-shimmed `gh` mock.

## Global Constraints

- Substrate: the interim GitHub board — every rule lands in the v8
  toolkit; the spec's rules are substrate-neutral, nothing here blocks
  the future Postgres board.
- New state names, exactly: `ready-for-architect`, `in-design`,
  `ready-for-implementer`. `ready-for-agent` is DELETED (not aliased).
- Historical documents keep the old vocabulary: never edit
  `docs/doperpowers/specs/*`, `docs/doperpowers/plans/*` (other than this
  plan's spec on drift), `teaching/*` (deferred to the follow-up ticket),
  or `skills/issue-tracker/scripts/board-migrate-gh.sh` (a v6→v7
  one-shot; its internal vocabulary is historical).
- `grep` scope for "no residual vocabulary" checks:
  `grep -rn "ready-for-agent" --exclude-dir=docs --exclude-dir=evals --exclude-dir=node_modules --exclude-dir=teaching --exclude-dir=review-bench .`
  must end with matches ONLY in `board-migrate-gh.sh` (+ this plan file
  if grepped before commit). `tests/review-bench/results/` holds FROZEN
  benchmark artifacts (old vocabulary preserved deliberately — never
  rewrite them; always `--exclude-dir=review-bench` on vocabulary greps
  and rename sweeps).
- Shell: `scripts/lint-shell.sh` must stay green (shellcheck baseline).
- Commits: no `Co-Authored-By` lines (repo convention).
- Version bump ONLY via `scripts/bump-version.sh` (Task 16), never by
  hand.
- Tests run from the repo root:
  `tests/issue-tracker/test-board-scripts.sh`,
  `tests/issue-tracker/test-board-sweep.sh`,
  `tests/implementing-tickets/test-implement-dispatch.sh`,
  `node tests/issue-tracker/test-board-template.cjs`,
  `tests/reviewing-prs/test-review-dispatch.sh`,
  `tests/claude-code/run-skill-tests.sh`,
  `(cd skills/triaging-feedback && npm test)`.

## The rename decision rule (used throughout)

Every existing `ready-for-agent` occurrence maps by its role:

| role of the occurrence | becomes |
|---|---|
| the default birth state / unsure queue / dispatch-eligibility predicate / test seed data for implement flows | `ready-for-implementer` |
| "the dispatchable states" as a set (eligibility, slot accounting, kanban core, sweep pre-verdict recovery, board-edge/list tags) | the tuple `B.DISPATCHABLE` = `("ready-for-architect", "ready-for-implementer")` |
| return-to-queue targets (unblock, deferred revival, wake fallback, recovery-cap note) | `ready-for-implementer` by default; prose adds "or `ready-for-architect` per the returner's judgment" |
| doc prose describing the happy path | `ready-for-architect → in-design → ready-for-implementer → in-progress → …` for the architect lane; `ready-for-implementer → in-progress → …` direct |

## File structure

New files:

- `skills/architecting/SKILL.md` — the Architect worker protocol (thin;
  Task 12).
- Appended test sections in the existing suites (no new test files).

Renamed: `skills/implementing-tickets/` → `skills/implementing/`
(directory + frontmatter `name:`; Task 10). Until Task 10, tasks touch
files under the OLD path `skills/implementing-tickets/`.

Modified (owner → responsibility):

- `skills/issue-tracker/scripts/_board.py` — the single vocabulary +
  legality + meta authority (Tasks 1, 3, 4).
- `skills/issue-tracker/scripts/board-{transition,register,answer,sweep,list,map,edge,lint}.sh`, `board-map.template.html` — mechanics (Tasks 1–7).
- `skills/implementing-tickets/scripts/implement-dispatch.sh`,
  `references/worker-bootstrap.md`, `references/issue-dispatch.yml` —
  lane dispatch (Tasks 8–9).
- `skills/implementing[-tickets]/SKILL.md` + references, and skill-wide
  prose — protocols (Tasks 10–13).
- `skills/issue-tracker/SKILL.md`, `references/ticket-gate.md` — board
  schema docs (Task 13).
- `skills/triaging-feedback/src/{gate,verdict,prompt}.ts` + prose,
  `skills/reviewing-prs/SKILL.md` — registrars/review contract (Tasks
  14–15).
- `tests/issue-tracker/*`, `tests/implementing-tickets/*` — suites
  (each task).

---

### Task 1: `_board.py` vocabulary cutover + mechanical suite rename

The behavior-preserving core: final state vocabulary and `LEGAL` table
land; every board script and the whole board suite speak the new names;
the suite is green at the end. New machinery (meta fields, convergence,
pre-park) comes in later tasks — this task only renames and re-tables.

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:19-106`
- Modify: `skills/issue-tracker/scripts/board-register.sh` (rename sites only: 13, 20-23, 97-109 comment text + `state="ready-for-agent"` default)
- Modify: `skills/issue-tracker/scripts/board-transition.sh:83` (skeleton guard)
- Modify: `skills/issue-tracker/scripts/board-answer.sh:17,74,87` (fallback text)
- Modify: `skills/issue-tracker/scripts/board-sweep.sh:9-16,162,201-211` (rename + case arm)
- Modify: `skills/issue-tracker/scripts/board-list.sh:6,38`
- Modify: `skills/issue-tracker/scripts/board-map.sh:91,96,136` region
- Modify: `skills/issue-tracker/scripts/board-map.template.html:200,219,377,415,423`
- Modify: `skills/issue-tracker/scripts/board-edge.sh:81`
- Modify: `skills/issue-tracker/scripts/board-lint.sh:89` (comment text)
- Test: `tests/issue-tracker/test-board-scripts.sh` (mechanical rename of ~28 sites), `tests/issue-tracker/test-board-template.cjs`

**Interfaces:**
- Produces (later tasks consume these exact names from `_board as B`):
  `B.DISPATCHABLE == ("ready-for-architect", "ready-for-implementer")`,
  `B.PRE_PARK` (dict, Task 4 consumes), `B.EDGE_NOTE_REQUIRED` /
  `B.CONVERGENCE_EDGES` (sets of `(from, to)` tuples, Task 5 consumes),
  the final `B.LEGAL`, `B.BIRTH`, `B.OPEN_STATES`, `B.ACTIVE`,
  `B.PULLABLE`, `B.STATUS_COLORS`.

- [ ] **Step 1: Rewrite the `_board.py` vocabulary block**

Replace lines 19–36 (`OPEN_STATES` through `PULLABLE`) with:

```python
# ── state vocabulary (v9: the E1 lane split — the single pre-v9 agent queue
#    split into ready-for-architect / in-design / ready-for-implementer) ──
OPEN_STATES = ("ready-for-architect", "in-design", "ready-for-implementer",
               "in-progress", "needs-human", "needs-info",
               "interactive-preferred", "in-review", "confident-ready",
               "deferred")
TERMINAL = ("done", "wontfix")
STATES = OPEN_STATES + TERMINAL
# Actively-worked states: a close_candidate in one of these is normal
# mid-flight shape (part-1 PR merged, part 2 coming) — surfaces that nag or
# relocate (lint WARN, kanban column) skip them; passive displays still mark.
ACTIVE = ("in-design", "in-progress", "in-review")
# The two dispatchable lane queues — the eligibility predicate, slot
# accounting, and every ELIGIBLE display key off this tuple.
DISPATCHABLE = ("ready-for-architect", "ready-for-implementer")
BIRTH = ("ready-for-architect", "ready-for-implementer", "needs-info",
         "needs-human", "interactive-preferred", "deferred")
# Park discriminant — WHO UNPARKS IT (three addresses): the human as
# themselves (a decision or a real-world input) → needs-human; knowledge
# work anyone could do → needs-info; missing/broken design an AGENT can
# author → ready-for-architect. Ongoing steering → interactive-preferred.
NOTE_REQUIRED = ("needs-human", "needs-info", "interactive-preferred", "wontfix")
# Edge-keyed note requirement (E1 transitions 2/4/5 + the QAgent edge):
# these lane-crossing edges enter states that are note-free at birth, so
# the state-keyed NOTE_REQUIRED cannot express them.
EDGE_NOTE_REQUIRED = {
    ("in-design", "ready-for-implementer"),
    ("ready-for-implementer", "ready-for-architect"),
    ("in-progress", "ready-for-architect"),
    ("in-review", "ready-for-architect"),
}
# Convergence-counted escalation edges: a SECOND traversal of the same
# edge on one ticket converts to a needs-human park (board-transition
# enforces; count resets at the last [answers] comment).
CONVERGENCE_EDGES = EDGE_NOTE_REQUIRED - {("in-design", "ready-for-implementer")}
# Park-return targets (E1 transition 7): written into pre-park: meta at
# needs-human park time; board-answer returns the ticket there. Always an
# IN-FLIGHT state — returning to a dispatchable queue would race the sweep
# onto a second worker.
PRE_PARK = {
    "ready-for-architect": "in-design",
    "in-design": "in-design",
    "ready-for-implementer": "in-progress",
    "in-progress": "in-progress",
    "in-review": "in-review",
}
PULLABLE = ("ready-for-architect", "ready-for-implementer", "needs-info",
            "needs-human", "interactive-preferred", "deferred")
```

- [ ] **Step 2: Rewrite the `LEGAL` table** (current lines 37–67) to exactly:

```python
LEGAL = {
    "ready-for-architect":   {"in-design", "needs-info", "needs-human",
                              "interactive-preferred", "wontfix", "deferred"},
    # in-design: the Architect's in-flight state. Exit = transition 2/3
    # (plan handoff / down-shortcircuit / decompose-epic) or a park.
    "in-design":             {"ready-for-implementer", "needs-info",
                              "needs-human", "interactive-preferred",
                              "wontfix", "deferred"},
    "ready-for-implementer": {"in-progress", "ready-for-architect",
                              "needs-info", "needs-human",
                              "interactive-preferred", "wontfix", "deferred"},
    "in-progress":           {"ready-for-architect", "needs-info",
                              "needs-human", "interactive-preferred",
                              "in-review", "done", "wontfix", "deferred"},
    "needs-info":            {"ready-for-architect", "ready-for-implementer",
                              "in-progress", "needs-human",
                              "interactive-preferred", "wontfix", "deferred"},
    # done from needs-human: the spike handoff — a finished spike parks
    # needs-human "findings ready" and the human closes it after reading
    # (done is the manual flip for non-PR work). Human-only in practice:
    # worker doctrine forbids terminal states.
    # in-design / in-review from needs-human: the pre-park returns
    # (board-answer reads pre-park: meta — E1 transition 7).
    "needs-human":           {"ready-for-architect", "ready-for-implementer",
                              "in-progress", "in-design", "in-review",
                              "needs-info", "interactive-preferred",
                              "done", "wontfix", "deferred"},
    "interactive-preferred": {"ready-for-architect", "ready-for-implementer",
                              "in-progress", "needs-info", "needs-human",
                              "wontfix", "deferred"},
    # ready-for-architect from in-review: the QAgent's design-gap
    # escalation (E1 third address; convergence-counted).
    "in-review":             {"in-progress", "ready-for-architect",
                              "confident-ready", "done", "wontfix",
                              "deferred", "needs-info", "needs-human"},
    # confident-ready: PR rigorously reviewed by the reviewing-prs loop.
    # Reachable ONLY from in-review (a review verdict presupposes an open PR);
    # deliberately NOT in ACTIVE — a confident-ready ticket whose PRs all
    # merged SHOULD surface as a close candidate (the finalize cue).
    "confident-ready": {"in-progress", "in-review", "done", "wontfix", "deferred"},
    "deferred":        {"ready-for-architect", "ready-for-implementer",
                        "needs-info", "needs-human", "interactive-preferred",
                        "wontfix"},
    "done":            set(),   # terminal
    "wontfix":         set(),   # terminal
}
```

- [ ] **Step 3: Update `STATUS_COLORS`** (lines 74–83): remove the
`"ready-for-agent"` entry, add (a state with no color entry never gets its
GitHub label created by `ensure_labels`):

```python
    "ready-for-architect": "006b75",
    "in-design":           "bfd4f2",
    "ready-for-implementer": "0e8a16",
```

- [ ] **Step 4: Update `eligible()` and `newly_eligible()`**

`eligible()` (line 441): change the predicate line to

```python
    if tid in epics(tickets) or n["state"] not in DISPATCHABLE:
```

`newly_eligible()` (line 506): change to

```python
        if n["state"] in DISPATCHABLE and done_tid in n["blocked_by"] \
```

- [ ] **Step 5: Mechanical renames in the board scripts** — apply the
rename decision rule at each site; every change below is exhaustive for
this task (later tasks add behavior):

  - `board-register.sh:35`: `state="ready-for-agent"` →
    `state="ready-for-implementer"`; line 102 guard becomes
    `if state in ("ready-for-architect", "ready-for-implementer") and "(pre-spec: fill in)" in body:`
    and its `--state ready-for-agent` refusal message text becomes
    "a pre-spec skeleton cannot be born into a dispatchable lane state";
    the demotion note text's "board-transition.sh to ready-for-agent" →
    "board-transition.sh to its lane state". Update the header usage
    text (lines 13–23) to name the new default and both lane states.
  - `board-transition.sh:83`: `if to == "ready-for-agent"` →
    `if to in B.DISPATCHABLE` (message text: "before a dispatchable
    lane state").
  - `board-answer.sh` (lines 17, 74, 87): fallback prose
    `board-transition.sh <n> ready-for-agent` →
    `board-transition.sh <n> ready-for-implementer (or ready-for-architect
    per the park discriminant)`.
  - `board-sweep.sh:211`: grep becomes
    `'^(in-progress|in-design|ready-for-architect|ready-for-implementer)\|'`;
    line 201 case arm `ready-for-agent)` →
    `ready-for-architect|ready-for-implementer)` (log text: "pre-verdict
    worker" instead of "pre-gate worker"); line 185 case arm
    `in-progress)` → `in-progress|in-design)` (the resume ladder covers
    mid-design work — the pipeline's most expensive in-flight asset).
    `_recover`'s cap-exhausted note text (line 162): "re-cut to
    ready-for-agent" → "re-cut to its ready-for-* lane". Header comment
    (lines 9–16): describe the in-flight set (in-progress, in-design)
    vs the pre-verdict set (ready-for-*).
  - `board-list.sh:6` comment → "Eligible = a dispatchable lane state
    (ready-for-architect / ready-for-implementer) + every blocked_by
    ticket done + not an epic."; line 38:
    `elif n["state"] == "ready-for-agent":` →
    `elif n["state"] in B.DISPATCHABLE:`.
  - `board-map.sh`: delete the local `eligible()` (the inline duplicate)
    and call `B.eligible(tickets, tid)` everywhere it was used;
    `state_label()` becomes:

    ```python
    def state_label(tid, n):
        if n["state"] in B.DISPATCHABLE:
            unmet = [b for b in n.get("blocked_by", []) if tickets.get(b, {}).get("state") != "done"]
            if unmet:
                return n["state"] + " · waiting: " + ",".join("#%s" % b for b in unmet)
            return n["state"] + " · ELIGIBLE"
        return n["state"]
    ```

    `cls()` becomes:

    ```python
    def cls(tid, n):
        if n["state"] == "in-design":
            return "s_design"
        if n["state"] in B.DISPATCHABLE:
            return "s_elig" if B.eligible(tickets, tid) else "s_wait"
        return CLASS.get(n["state"], "s_wait")
    ```

  - `board-map.template.html`: in `KB_STATES` replace
    `"ready-for-agent"` with
    `"ready-for-architect", "in-design", "ready-for-implementer"`;
    in `STATE_CLS` replace the `"ready-for-agent": "s_elig"` entry with
    `"ready-for-architect": "s_elig", "in-design": "s_design",
    "ready-for-implementer": "s_elig"`; in `BADGE` add
    `s_design: "designing"`; `KB_CORE` becomes
    `{ "ready-for-architect": 1, "ready-for-implementer": 1, "in-progress": 1, "in-review": 1, "done": 1 }`;
    the two sort/count special-cases
    (`s === "ready-for-agent"`) become
    `(s === "ready-for-architect" || s === "ready-for-implementer")`.
    Add one CSS rule next to the existing `.s_prog` rule (same property
    shape as its neighbors, color `#bfd4f2` border / tinted fill):

    ```css
    .s_design { --c: #bfd4f2; }
    ```

    (Match the exact custom-property/selector idiom of the adjacent
    state classes in the file — every state class there sets its palette
    the same way; mirror `.s_prog`'s structure with the new color.)
  - `board-edge.sh:81`: `if n["state"] == "ready-for-agent"` →
    `if n["state"] in B.DISPATCHABLE`.
  - `board-lint.sh:89` comment text: "ready-for-agent → done is
    deliberately not a legal transition" → "a dispatchable lane state →
    done is deliberately not a legal transition".

- [ ] **Step 6: Mechanically rename the board suite** — in
`tests/issue-tracker/test-board-scripts.sh` replace every
`ready-for-agent` occurrence (seed labels, expected label lists, expected
transition strings, refusal comments) with `ready-for-implementer`, EXCEPT
none map to `ready-for-architect` in this task (existing flows are all
implement-lane flows). In `tests/issue-tracker/test-board-template.cjs`
replace kanban column assertions the same way (`ready-for-agent` →
`ready-for-implementer`) and, where the test asserts the full column
list, insert `ready-for-architect` and `in-design` in the positions the
template's `KB_STATES` now defines.

- [ ] **Step 7: Run all three board suites to green**

Run: `tests/issue-tracker/test-board-scripts.sh && tests/issue-tracker/test-board-sweep.sh && node tests/issue-tracker/test-board-template.cjs`
Expected: `all tests passed` from both shell suites; the cjs suite
exits 0. `test-board-sweep.sh` needs no rename (it seeds only
`in-progress`/`needs-human` states) — it runs here as the regression
proof that the sweep's rewritten case arms (Step 5) preserve the
existing recovery/cancel/relay behavior. Fix any missed rename site the
failures name (the suites are the enumerator; the grep in Step 8 is the
proof).

- [ ] **Step 8: Residual-vocabulary check (board scripts + suites)**

Run: `grep -rn "ready-for-agent" skills/issue-tracker/scripts/ tests/issue-tracker/ | grep -v board-migrate-gh.sh`
Expected: no output. (`skills/issue-tracker/SKILL.md` and
`references/ticket-gate.md` still carry the old vocabulary at this
point — their content rewrite is Task 13's; Task 16's repo-wide grep is
the final proof.)

- [ ] **Step 9: Commit**

```bash
git add skills/issue-tracker tests/issue-tracker
git commit -m "feat(board): v9 vocabulary — ready-for-agent splits into ready-for-architect / in-design / ready-for-implementer (E1); final LEGAL table, DISPATCHABLE/PRE_PARK/EDGE_NOTE tables, mechanical suite rename"
```

---

### Task 2: Birth classification — register defaults + skeleton guards

**Files:**
- Modify: `skills/issue-tracker/scripts/board-register.sh`
- Test: `tests/issue-tracker/test-board-scripts.sh` (append a section)

**Interfaces:**
- Consumes: Task 1's `B.BIRTH`, `B.DISPATCHABLE`.
- Produces: `board-register.sh --state ready-for-architect` as a legal
  explicit birth; unchanged default `ready-for-implementer`.

- [ ] **Step 1: Append the failing test section** (before the final
`echo` / failure summary in `test-board-scripts.sh`):

```bash
# ---- lane births (E1 birth classification) ------------------------------------
echo "lane births:"
out="$(run board-register.sh "Design-heavy epic work" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY")"
arch_t="${out%% *}"
assert_contains "$(state "s['issues']['$arch_t']['labels']")" "status:ready-for-architect" "explicit architect-lane birth honored"
out="$(run board-register.sh "Default lane probe" enhancement P2 --body-file "$SPEC_BODY")"
impl_t="${out%% *}"
assert_contains "$(state "s['issues']['$impl_t']['labels']")" "status:ready-for-implementer" "default birth is the implementer lane (unsure → implementer)"
assert_fails run board-register.sh "Arch skeleton" bug P2 --state ready-for-architect   # skeleton refused in BOTH lanes
```

- [ ] **Step 2: Run the new section**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -20`
Expected: these cases may already PASS — Task 1's mechanical pass
carried the guard edit. That is fine: this task's value is regression
coverage of the birth rule; verify each new assertion passes and the
guard text matches Step 3 exactly (fix either side if not).

- [ ] **Step 3: Implement** — in `board-register.sh` the Task 1 edits
already cover the guard; verify the guard block reads exactly:

```python
if state in ("ready-for-architect", "ready-for-implementer") and "(pre-spec: fill in)" in body:
    if env["T_STATE_EXPLICIT"] == "1":
        B.die("a pre-spec skeleton cannot be born into a dispatchable lane "
              "state — pass --body-file with the spec, or birth it "
              "needs-info/needs-human")
    state = "needs-info"
    if not note:
        note = ("pre-spec skeleton — fill the body, then "
                "board-transition.sh to its lane state")
```

- [ ] **Step 4: Run the suite to green**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `all tests passed`

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-register.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(board): birth classification — explicit architect-lane births, skeleton guard covers both lanes"
```

---

### Task 3: `plan:` meta — the `--plan` flag and the `pre-spec` sentinel

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:106` (`META_KEYS`)
- Modify: `skills/issue-tracker/scripts/board-transition.sh`
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Produces: `board-transition.sh <n> <state> [note] [--branch B] [--pr URL] [--plan P]`;
  `META_KEYS = ("spawned-by", "relates-to", "branch", "pr", "plan", "pre-park", "note")`
  (`pre-park` lands here so Task 4 needs no second `META_KEYS` edit).
  A `plan:` value is either `<repo-path>@<40-hex-sha>` or the literal
  `pre-spec`.

- [ ] **Step 1: Append the failing test section**

```bash
# ---- plan meta (E1 transitions 2 and 3) ---------------------------------------
echo "plan meta:"
run board-register.sh "Architect handoff probe" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
plan_t="$(state "s['next']-1")"
run board-transition.sh "$plan_t" in-design >/dev/null
out="$(run board-transition.sh "$plan_t" ready-for-implementer "plan ready: do X then Y" --branch tick/plan-probe --plan "docs/plans/x.md@0123456789abcdef0123456789abcdef01234567")"
assert_contains "$(state "s['issues']['$plan_t']['body']")" "plan: docs/plans/x.md@0123456789abcdef0123456789abcdef01234567" "plan pin recorded in board:meta"
assert_contains "$(state "s['issues']['$plan_t']['body']")" "branch: tick/plan-probe" "branch recorded on the handoff"
run board-register.sh "Shortcircuit probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
sc_t="$(state "s['next']-1")"
run board-transition.sh "$sc_t" in-design >/dev/null
out="$(run board-transition.sh "$sc_t" ready-for-implementer "pre-spec suffices as the plan" --plan pre-spec)"
assert_contains "$(state "s['issues']['$sc_t']['body']")" "plan: pre-spec" "down-shortcircuit sentinel recorded"
assert_fails run board-transition.sh "$plan_t" in-progress --plan "also/here.md@0123456789abcdef0123456789abcdef01234567"   # --plan only on the handoff edge
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -25`
Expected: `unknown option: --plan` failures.

- [ ] **Step 3: Implement**

In `_board.py:106`:

```python
META_KEYS = ("spawned-by", "relates-to", "branch", "pr", "plan", "pre-park", "note")
```

In `board-transition.sh`: extend the option loop (lines 31–37) with
`--plan) _need_arg "$1" "${2:-}"; plan="$2"; shift 2 ;;` (initialize
`plan=""` on line 29 and export `T_PLAN="$plan"` on line 39). In the
python block, after the PR-gate check (line 82), add:

```python
if env["T_PLAN"]:
    import re as _re
    if to != "ready-for-implementer":
        B.die("--plan rides the Architect handoff edge (→ ready-for-implementer) only")
    if env["T_PLAN"] != "pre-spec" and not _re.match(r"^\S+@[0-9a-f]{40}$", env["T_PLAN"]):
        B.die("--plan must be <repo-path>@<full-40-hex-sha> (an immutable pin) or the literal pre-spec")
```

and in the `extra` block (lines 88–92) add:

```python
if env["T_PLAN"]:
    extra["plan"] = env["T_PLAN"]
```

Update the usage header (line 5) to
`board-transition.sh <number> <to-state> [note] [--branch NAME] [--pr URL] [--plan PATH@SHA|pre-spec]`.

- [ ] **Step 4: Run the suite to green**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `all tests passed`

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker
git commit -m "feat(board): plan: meta — --plan pin (path@sha | pre-spec sentinel) on the Architect handoff edge"
```

---

### Task 4: Park returns — automatic `pre-park:` + lane-aware `board-answer.sh`

**Files:**
- Modify: `skills/issue-tracker/scripts/board-transition.sh` (auto pre-park write/clear)
- Modify: `skills/issue-tracker/scripts/board-answer.sh` (return target + refusal text)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: `B.PRE_PARK` (Task 1), `META_KEYS` incl. `pre-park` (Task 3).
- Produces: every `needs-human` park written from a `PRE_PARK` source
  carries `pre-park: <in-flight state>` in board:meta; any transition
  OUT of `needs-human` clears it; `board-answer.sh` returns the ticket
  to the `pre-park:` value, falling back to `in-progress`.

- [ ] **Step 1: Append the failing test section**

```bash
# ---- pre-park + lane-aware answer return (E1 transition 7) --------------------
echo "pre-park returns:"
run board-register.sh "Architect park probe" enhancement P1 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
pp_t="$(state "s['next']-1")"
run board-transition.sh "$pp_t" in-design >/dev/null
run board-transition.sh "$pp_t" needs-human "Q1: layout A or B? (rec: A)" >/dev/null
assert_contains "$(state "s['issues']['$pp_t']['body']")" "pre-park: in-design" "architect park records its in-flight return target"
out="$(run board-transition.sh "$pp_t" in-design "answers relayed")"
assert_contains "$out" "#$pp_t: needs-human → in-design" "needs-human → in-design is a legal return"
assert_not_contains "$(state "s['issues']['$pp_t']['body']")" "pre-park:" "return clears the pre-park meta"
# gate-fail park from the architect QUEUE also returns to in-design
run board-register.sh "Gate-fail park probe" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
gf_t="$(state "s['next']-1")"
run board-transition.sh "$gf_t" needs-human "gate fail: purpose unstated" >/dev/null
assert_contains "$(state "s['issues']['$gf_t']['body']")" "pre-park: in-design" "architect-queue gate-fail park targets in-design"
```

Then, in the EXISTING board-answer test block (the section that
currently asserts the answered park lands `in-progress` — search for
`answers relayed`), append after its final assert:

```bash
# lane-aware return: an architect park's answer resumes into in-design
```
plus a case mirroring that block's daemon-stub setup with a ticket parked
from `in-design` (reuse the block's stub-meta helper exactly as the
existing case does, changing only the ticket's park path; name the new
ticket variable `ans_arch_t` where the existing case uses `ans_t`),
asserting:

```bash
assert_contains "$(state "s['issues']['$ans_arch_t']['labels']")" "status:in-design" "answered architect park resumes into in-design"
```

- [ ] **Step 2: Run to verify the new asserts fail**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -30`
Expected: FAILs on "records its in-flight return target" (no pre-park
written yet) and on the legality line only if Task 1's LEGAL missed the
edge (it should already pass legality).

- [ ] **Step 3: Implement in `board-transition.sh`'s python block** — in
the `extra` assembly (after Task 3's plan block):

```python
if to == "needs-human" and cur in B.PRE_PARK:
    extra["pre-park"] = B.PRE_PARK[cur]
if cur == "needs-human" and to != "needs-human":
    extra["pre-park"] = None
```

(`update_meta` deletes a key on `None` — no other change needed.)

- [ ] **Step 4: Implement in `board-answer.sh`** — in the python info
block (lines 61–101), read the return target and emit it as a 5th field:

```python
ret = B.parse_meta(tickets[tid]["body"]).get("pre-park") or "in-progress"
print("%s\t%s\t%s\t%s\t%s" % (meta.get("uuid", ""), meta.get("engine", "claude"),
                              meta.get("status", "?"), meta.get("updated", "?"), ret))
```

Shell side (lines 103–108):

```bash
IFS=$'\t' read -r uuid engine status updated ret <<<"$info"
[ -n "$uuid" ] || die "binding lookup failed"
echo "relay: #$tid → $engine session ${uuid:0:8} (status=$status, last-updated=$updated, return=$ret)"

"$SCRIPT_DIR/board-transition.sh" "$tid" "$ret" \
  "answers relayed — resuming bound session ${uuid:0:8}"
```

Header comment (line 9): "the ticket returns to its parking lane's
in-flight state (pre-park: meta; in-progress when absent)".

- [ ] **Step 5: Run the suite to green**

Run: `tests/issue-tracker/test-board-scripts.sh`
Expected: `all tests passed`

- [ ] **Step 6: Commit**

```bash
git add skills/issue-tracker tests/issue-tracker
git commit -m "feat(board): pre-park meta + lane-aware answered-park returns (in-design/in-progress/in-review)"
```

---

### Task 5: Edge-keyed notes + convergence enforcement

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py` (`apply_state` comment format)
- Modify: `skills/issue-tracker/scripts/board-transition.sh` (edge-note check + convergence conversion)
- Modify: `tests/issue-tracker/mock-gh/gh` (add the `issue view --json comments` handler — the shared mock has NONE today; unmatched commands `die("unhandled: …")`, so without this every convergence-edge transition in the suite hard-fails)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: `B.EDGE_NOTE_REQUIRED`, `B.CONVERGENCE_EDGES` (Task 1),
  `B.PRE_PARK` (Task 4's write path re-used by the conversion).
- Produces: convergence-counted transitions post comments in the format
  `[board] <from> → <to>: <note>` (all other transitions keep
  `[board] <to>: <note>`); a second traversal of the same convergence
  edge since the last `[answers]` comment is CONVERTED into a
  `needs-human` park whose note carries both attempts.

- [ ] **Step 1: Append the failing test section**

```bash
# ---- edge notes + convergence (E1 transitions 4/5/6) --------------------------
echo "convergence:"
run board-register.sh "Escalation probe" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
cv_t="$(state "s['next']-1")"
assert_fails run board-transition.sh "$cv_t" ready-for-architect            # edge note required
out="$(run board-transition.sh "$cv_t" ready-for-architect "gate: plan-need — multi-milestone")"
assert_contains "$out" "#$cv_t: ready-for-implementer → ready-for-architect" "gate escalation applied"
assert_contains "$(state "s['issues']['$cv_t']['comments'][-1]")" "[board] ready-for-implementer → ready-for-architect: gate: plan-need" "escalation comment carries the edge"
# complete a design pass, execute, then hit the SAME escalation edge again
run board-transition.sh "$cv_t" in-design >/dev/null
run board-transition.sh "$cv_t" ready-for-implementer "pre-spec suffices as the plan" --plan pre-spec >/dev/null
out="$(run board-transition.sh "$cv_t" ready-for-architect "still believe plan-need")"
assert_contains "$out" "#$cv_t: ready-for-implementer → needs-human" "second traversal of the same edge converts to needs-human"
assert_contains "$(state "s['issues']['$cv_t']['body']")" "convergence: second traversal" "conversion note names the convergence rule"
assert_contains "$(state "s['issues']['$cv_t']['body']")" "pre-park: in-progress" "converted park still records a return target"
# an [answers] comment resets the count: a sanctioned re-traversal of the
# SAME edge passes. Fresh ticket (the converted one is parked) — the reset
# only proves anything on the edge that was previously counted.
run board-register.sh "Escalation probe 2" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
cv2_t="$(state "s['next']-1")"
run board-transition.sh "$cv2_t" ready-for-architect "gate: plan-need — round 1" >/dev/null
run board-transition.sh "$cv2_t" in-design >/dev/null
run board-transition.sh "$cv2_t" ready-for-implementer "plan cut" --plan pre-spec >/dev/null
python3 - <<'ANS'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
t = str(max(int(k) for k in s["issues"]))
s["issues"][t]["comments"].append("[answers] yes — architect may take it again")
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
ANS
out="$(run board-transition.sh "$cv2_t" ready-for-architect "human-sanctioned re-escalation")"
assert_contains "$out" "#$cv2_t: ready-for-implementer → ready-for-architect" "same-edge re-traversal passes after [answers] reset (no needs-human conversion)"
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -30`
Expected: FAIL on "edge note required" (state-keyed check does not cover
it) and on the edge-format comment.

- [ ] **Step 3: Teach the mock `issue view --json comments`** — the
shared mock (`tests/issue-tracker/mock-gh/gh`) has no `issue view`
handler, and its fall-through is `die("unhandled: …")`. Add this block
after the `["issue", "comment"]` handler (line ~119), serving the real
gh shape (`[{"body": …}]`) mapped from the mock's plain-string comment
store:

```python
    if argv[:2] == ["issue", "view"]:
        it = issue(s, argv[2])
        if opt(argv, "--json") == "comments":
            print(json.dumps({"comments": [{"body": c} for c in it["comments"]]}))
            return
        die("unhandled issue view fields: %s" % " ".join(argv))
```

- [ ] **Step 4: Implement the comment format** — in `_board.py`
`apply_state` (line 458), add a `frm_to_comment` decision: replace

```python
    if why:
        comment(tid, "[board] %s: %s" % (to, why))
```

with

```python
    if why:
        if (old, to) in CONVERGENCE_EDGES:
            comment(tid, "[board] %s → %s: %s" % (old, to, why))
        else:
            comment(tid, "[board] %s: %s" % (to, why))
```

- [ ] **Step 5: Implement the checks in `board-transition.sh`'s python
block** — after the legality check (line 77–78), add:

```python
if (cur, to) in B.EDGE_NOTE_REQUIRED and not note:
    B.die("a note is required on the %s → %s edge" % (cur, to))

if (cur, to) in B.CONVERGENCE_EDGES:
    # Convergence rule (E1 transition 6): count prior traversals of THIS
    # edge since the last [answers] comment; a second traversal converts
    # to a needs-human park. Comments are not in the snapshot — one
    # extra gh call, only on escalation edges.
    import json as _json
    comments = _json.loads(B.gh(["issue", "view", tid, "-R", B.repo(),
                                 "--json", "comments"])).get("comments") or []
    marker = "[board] %s → %s:" % (cur, to)
    count = 0
    for c in comments:
        # real gh (and the Step-3 mock handler) serve [{"body": ...}];
        # tolerate plain strings defensively
        body = ((c.get("body") if isinstance(c, dict) else c) or "").lstrip()
        if body.startswith("[answers]"):
            count = 0
        elif body.startswith(marker):
            count += 1
    if count >= 1:
        note = ("convergence: second traversal of %s → %s — no third "
                "mechanical bounce; both positions: %s" % (cur, to, note))
        to = "needs-human"
```

Place this BEFORE the `NOTE_REQUIRED`/pre-park blocks so the converted
park flows through them (the park gets its note check and its
`pre-park:` write for free).

- [ ] **Step 6: Run both board suites to green**

Run: `tests/issue-tracker/test-board-scripts.sh && tests/issue-tracker/test-board-sweep.sh`
Expected: `all tests passed` from both. The sweep suite is regression
insurance for the `apply_state` format change — the sweep's own parks
traverse no convergence edge, so its comment format must be unchanged.

- [ ] **Step 7: Commit**

```bash
git add skills/issue-tracker tests/issue-tracker
git commit -m "feat(board): edge-keyed notes + mechanical convergence enforcement with [answers] reset"
```

---

### Task 6: Sweep recovery over the new states (behavior test)

Task 1 already made the sweep's code changes; this task proves them. The
sweep tests live in the DEDICATED suite
`tests/issue-tracker/test-board-sweep.sh` (NOT `test-board-scripts.sh`,
which has no sweep section). Its idiom: stub `daemon-finalize.sh`/
`daemon-resume.sh`/`daemon-retire.sh` scripts append to `$ACTION_LOG`;
the board is seeded by one python heredoc (the `issue()` helper +
`meta()` registry writer, around line 136); per-uuid finalize verdicts
come from `$FINALIZE_MAP`; assertions live under the
`echo "board-sweep: full tick"` section (line ~235) and check
`$ACTION_LOG` / the captured sweep output.

**Files:**
- Test: `tests/issue-tracker/test-board-sweep.sh`
- Modify (only if the tests find gaps): `skills/issue-tracker/scripts/board-sweep.sh`

- [ ] **Step 1: Extend the seed with two lane-state tickets.** In the
board-seed heredoc, add the two new status labels to the seed's label
list (labels the sweep may apply must pre-exist in mock state):

```python
s = {"next": 30, "labels": ["status:needs-human", "status:in-progress",
                            "status:in-design", "status:ready-for-architect"], "issues": {
```

and append two issues to the dict (after `"19": …`):

```python
    "20": issue(20, "dead architect mid-design", ["status:in-design"]),
    "21": issue(21, "dead pre-verdict architect", ["status:ready-for-architect"]),
```

After the existing `meta(U("aaaa0019"), …)` line, bind them:

```python
meta(U("aaaa0020"), "20-design", "20", "working")
meta(U("aaaa0021"), "21-preverdict", "21", "working")
```

In the FINALIZE_MAP heredoc, add both verdicts to the dict:

```python
           U("aaaa0020"): "absent", U("aaaa0021"): "absent",
```

- [ ] **Step 2: Append the assertions** to the `board-sweep: full tick`
section, after the existing RECOVER block:

```bash
# RECOVER — lane-state split (E1): in-flight design work resumes; a dead
# pre-verdict worker is retired so the dispatch pass re-runs it fresh
assert_contains "$log" "resume:aaaa0020-0000-4000-8000-000000000000" "dead in-design worker gets the resume ladder (mid-design WIP is preserved)"
assert_contains "$out" "RECOVER: #20 worker aaaa0020-0000-4000-8000-000000000000 died mid-turn (session gone) — resume attempt 1/3" "in-design recovery goes through _recover's counted ladder"
assert_contains "$log" "retire:aaaa0021-0000-4000-8000-000000000000" "dead ready-for-architect worker is retired, not resumed"
assert_contains "$out" "pre-verdict worker" "retire log names the pre-verdict rule"
assert_not_contains "$log" "resume:aaaa0021" "pre-verdict recovery never resumes"
```

- [ ] **Step 3: Run — expected pass** (Task 1 implemented the case
arms); if a case fails, fix `board-sweep.sh`'s case arms / row grep to
match Task 1 Step 5's specification (`in-progress|in-design)` resumes,
`ready-for-architect|ready-for-implementer)` retires with "pre-verdict
worker" log text, row grep
`'^(in-progress|in-design|ready-for-architect|ready-for-implementer)\|'`),
and re-run to green.

Run: `tests/issue-tracker/test-board-sweep.sh`
Expected: `all tests passed`

- [ ] **Step 4: Commit**

```bash
git add tests/issue-tracker/test-board-sweep.sh skills/issue-tracker/scripts/board-sweep.sh
git commit -m "test(board): sweep recovery split over the lane states (in-design resumes, ready-for-* retires)"
```

---

### Task 7: Display + lint sweep-up (list/map/template/edge/lint)

Task 1 made these code changes mechanically; this task adds the behavior
assertions and closes the display loop.

**Files:**
- Test: `tests/issue-tracker/test-board-scripts.sh`, `tests/issue-tracker/test-board-template.cjs`
- Modify (only on failure): the five display scripts named in Task 1

- [ ] **Step 1: Append display assertions** to the board suite (after
the lane-births section):

```bash
echo "lane display:"
assert_contains "$(run board-list.sh)" "ELIGIBLE" "board-list still tags eligibility"
assert_contains "$(run board-list.sh ready-for-architect)" "ready-for-architect" "state filter works for the architect queue"
out="$(run board-map.sh)"
assert_contains "$out" "ready-for-architect · ELIGIBLE" "board-map table shows lane + eligibility"
```

And to `test-board-template.cjs`: assert the rendered `KB_STATES`
includes all three new states in order and `KB_CORE` includes both lane
queues (mirror the file's existing column assertions).

- [ ] **Step 2: Run both, fix to green**

Run: `tests/issue-tracker/test-board-scripts.sh && node tests/issue-tracker/test-board-template.cjs`
Expected: green; any failure names the residual display site — fix per
Task 1 Step 5's specification.

- [ ] **Step 3: Run board-lint on the mock state end-of-suite** — the
suite already runs lint cases; confirm no new FAIL class appeared.

- [ ] **Step 4: Commit**

```bash
git add tests/issue-tracker skills/issue-tracker
git commit -m "test(board): lane-state display assertions (list/map/kanban)"
```

---

### Task 8: Lane dispatch — `implement-dispatch.sh` routes the Architect

**Files:**
- Modify: `skills/implementing-tickets/scripts/implement-dispatch.sh`
- Modify: `skills/implementing-tickets/references/worker-bootstrap.md`
- Test: `tests/implementing-tickets/test-implement-dispatch.sh`

**Interfaces:**
- Consumes: `B.DISPATCHABLE`, `B.eligible` (Task 1); the architecting
  protocol path `skills/architecting/SKILL.md` (authored in Task 12 —
  until then the dispatch test stubs it; see Step 1 note).
- Produces: role selection = `SPIKE` (category, state-free) →
  `ARCHITECT` (state `ready-for-architect`, always plain-Claude route,
  model `${ARCHITECT_MODEL:-fable}`, `engine:*` labels IGNORED) →
  `IMPLEMENT`; per-lane slot accounting
  (`_slots_used architect` over `("ready-for-architect","in-design")`,
  `_slots_used implement` over `("ready-for-implementer","in-progress")`);
  caps `ARCHITECT_MAX_CONCURRENT` (default 1) and
  `IMPLEMENT_MAX_CONCURRENT` (default 5, unchanged).

- [ ] **Step 1: Write the failing tests** — in
`test-implement-dispatch.sh`, first update the board seed (the `issue()`
block): change every `status:ready-for-agent` seed label to
`status:ready-for-implementer`, and ADD two issues:

```python
    "8": issue(8, "Design the ledger split", ["status:ready-for-architect", "priority:P0"]),
    "9": issue(9, "Design with codex label", ["status:ready-for-architect", "priority:P1", "engine:codex"]),
```

(bump `"next"` to 10). Create the protocol stub the dispatcher will pin
(until Task 12 authors the real one) as part of the test env setup:

```bash
mkdir -p "$REPO_ROOT/skills/architecting"
[ -f "$REPO_ROOT/skills/architecting/SKILL.md" ] || printf '# Architect Worker Protocol (stub)\n' > "$REPO_ROOT/skills/architecting/SKILL.md"
```

(Write the stub creation into the test file's environment section; Task
12 replaces the stub with the real protocol and the guard keeps the test
stable either way.) Then append the cases:

```bash
echo "implement-dispatch: architect lane"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(run 8)"
assert_contains "$out" "dispatched #8" "architect ticket dispatches"
assert_contains "$out" "role=ARCHITECT" "architect role selected off the state"
PROMPT8="$PROMPT_DIR/8-design-the-ledger-split.prompt"
assert_file_contains "$PROMPT8" "ARCHITECT worker for ticket #8" "prompt carries the ARCHITECT role"
assert_file_contains "$PROMPT8" "architecting/SKILL.md" "architect lane opens the architecting protocol"
assert_contains "$(grep '^spawn:' "$SPAWN_LOG" | tail -1)" "model=fable" "architect route pins the frontier model"
assert_contains "$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)" "settings=;effort=" "architect route never rides the gateway"

out="$(run 9)"
assert_contains "$(grep '^spawn-env:' "$SPAWN_LOG" | tail -1)" "settings=;effort=" "engine:codex label is IGNORED on the architect lane (X4 exemption)"
assert_contains "$(grep '^spawn:' "$SPAWN_LOG" | tail -1)" "model=fable" "labelled architect ticket still pins fable"

echo "implement-dispatch: per-lane caps"

rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
out="$(ARCHITECT_MAX_CONCURRENT=1 run --sweep)"
n_arch="$(grep -c 'role=ARCHITECT' <<<"$out" || true)"
assert_contains "$n_arch" "1" "architect cap 1 admits exactly one design dispatch"
assert_contains "$out" "architect cap reached" "sweep names the architect cap"
assert_contains "$(cat "$SPAWN_LOG")" "spawn:--no-wait 3-" "implementer lane still dispatches under its own cap (the P0 spike rides it)"

# an in-design bound meta occupies an ARCHITECT slot (binding release = slot accounting)
rm -f "$DAEMON_HOME"/*.json; : > "$SPAWN_LOG"; echo 0 > "$STUB_COUNT"
python3 - <<'PY'
import json, os
json.dump({"uuid": "cccc0008-0000-4000-8000-000000000000", "current": "w",
           "name": "8-design-the-ledger-split", "ticket": "8", "status": "working",
           "updated": "2026-07-18T00:00:00Z"},
          open(os.path.join(os.environ["DAEMON_HOME"],
                            "cccc0008-0000-4000-8000-000000000000.json"), "w"))
PY
python3 - <<'PY'
import json, os
s = json.load(open(os.environ["MOCK_GH_STATE"]))
s["issues"]["8"]["labels"] = ["status:in-design", "priority:P0"]
json.dump(s, open(os.environ["MOCK_GH_STATE"], "w"))
PY
out="$(ARCHITECT_MAX_CONCURRENT=1 run 9)"
assert_contains "$out" "architect cap reached" "an in-design bound worker occupies the architect slot"
```

- [ ] **Step 2: Run to verify the new cases fail**

Run: `tests/implementing-tickets/test-implement-dispatch.sh 2>&1 | tail -30`
Expected: FAILs — no ARCHITECT role exists yet; ticket 8 is reported
`skip` or dispatched as IMPLEMENT.

- [ ] **Step 3: Implement in `implement-dispatch.sh`**

Header env docs add:

```
#   ARCHITECT_MAX_CONCURRENT  architect-lane slot cap (default 1) — the
#                   Fable-spend lever; counted over ready-for-architect/
#                   in-design bound metas, separate from the implement cap
#   ARCHITECT_MODEL model pin for the architect route (default fable);
#                   the architect dispatch IGNORES engine:* labels and
#                   WORKER_ENGINE — plan authorship is never label-routed
```

After line 49 add `ARCHITECT_PROTOCOL="$SKILL_DIR/../architecting/SKILL.md"`
and `ARCH_CAP="${ARCHITECT_MAX_CONCURRENT:-1}"`.

`_ticket_exports` (line 73): no change (state is already exported).

`_slots_used` becomes lane-parameterized — replace the function with:

```bash
# Occupied slots for one lane: bound metas in an active status whose
# ticket is still in that lane's active states. The architect lane's
# states are (ready-for-architect, in-design); the implement lane's are
# (ready-for-implementer, in-progress). A stale `working` meta on any
# other state never eats a slot — that worker's scope ended when the
# ticket moved on (binding release IS this accounting).
_slots_used() {  # <architect|implement>
  LANE="$1" BOARD_SCRIPTS="$BOARD_SCRIPTS" python3 - <<'PY'
import glob, json, os, sys
sys.path.insert(0, os.environ["BOARD_SCRIPTS"])
import _board as B
tickets = B.snapshot()
lane = {"architect": ("ready-for-architect", "in-design"),
        "implement": ("ready-for-implementer", "in-progress")}[os.environ["LANE"]]
used = 0
for p in glob.glob(os.path.join(os.environ["DAEMON_HOME"], "*.json")):
    if p.endswith(".reply.json"):
        continue
    try:
        m = json.load(open(p))
    except Exception:
        continue
    name = str(m.get("name") or "")
    if name.startswith("review-pr-") or name.startswith("land-pr-"):
        continue
    tk = str(m.get("ticket") or "").lstrip("#")
    if not tk or m.get("status") not in ("working", "blocked", "error"):
        continue
    if tickets.get(tk, {}).get("state") in lane:
        used += 1
print(used)
PY
}
```

In `dispatch_one`, replace the cap check (lines 173–176) and the
role/engine selection (lines 178–187) with:

```bash
  if [ "$T_CATEGORY" = "spike" ]; then
    # category precedence is state-free: a spike dispatches on the spike
    # protocol from EITHER lane queue
    lane="implement"; role="SPIKE"; protocol_file="$SPIKE_PROTOCOL"
    decompose="(none — spike lane)"
  elif [ "$T_STATE" = "ready-for-architect" ]; then
    lane="architect"; role="ARCHITECT"; protocol_file="$ARCHITECT_PROTOCOL"
    decompose="$DECOMPOSE_DOC"
  else
    lane="implement"; role="IMPLEMENT"; protocol_file="$IMPLEMENT_PROTOCOL"
    decompose="$DECOMPOSE_DOC"
  fi
  [ -f "$protocol_file" ] || { echo "#$n: protocol file missing: $protocol_file" >&2; return 1; }

  if [ "$lane" = "architect" ]; then
    if [ "$(_slots_used architect)" -ge "$ARCH_CAP" ]; then
      echo "architect cap reached ($ARCH_CAP): #$n stays queued for the next sweep"
      return 0
    fi
    # X4 exemption: plan authorship is never label-routed
    engine="claude"
  else
    if [ "$(_slots_used implement)" -ge "$CAP" ]; then
      echo "cap reached ($CAP): #$n stays queued for the next sweep"
      return 0
    fi
    engine="${T_ENGINE_LABEL:-}"
    [ -n "$engine" ] || engine="${WORKER_ENGINE:-claude}"
  fi
```

In the spawn block, route the architect lane through the plain-Claude
arm with its model pin — change the claude-route spawn (line 226–229) to:

```bash
    local model="${IMPLEMENT_MODEL:-}"
    [ "$lane" != "architect" ] || model="${ARCHITECT_MODEL:-fable}"
    spawn_out="$(DAEMON_CLAUDE_SETTINGS='' DAEMON_CLAUDE_EFFORT='' \
      "$DAEMON_SCRIPTS/daemon-spawn.sh" --no-wait "$name" "$prompt" "$LOCAL_REPO" "$name" \
      "$model")" \
      || { echo "#$n: worker spawn failed" >&2; return 1; }
```

and make the codex arm unreachable for the architect lane (it already
is: `engine=claude` was forced above). Declare `local lane model` in
`dispatch_one`'s local list. In `--sweep` mode's inner loop, replace the
single cap short-circuit (lines 265–268) with a both-caps check:

```bash
    if [ "$(_slots_used implement)" -ge "$CAP" ] && [ "$(_slots_used architect)" -ge "$ARCH_CAP" ]; then
      echo "cap reached: both lanes full — remaining eligible tickets stay queued"
      break
    fi
```

(`dispatch_one` itself enforces the per-lane cap per ticket.)

- [ ] **Step 4: Update `worker-bootstrap.md`** — replace line 4's
skill-naming sentence so the one template serves all three roles:

```markdown
You are an {{ROLE}} worker for ticket #{{ISSUE_NUMBER}} ({{ISSUE_URL}}) in
{{REPO}}, running unattended in your own worktree.

Your protocol for this run is the dispatcher-pinned copy at
`{{PROTOCOL_FILE}}` — open it first and follow it; it is authoritative
for this turn.
```

(bindings list unchanged).

- [ ] **Step 5: Run the dispatch suite to green**

Run: `tests/implementing-tickets/test-implement-dispatch.sh`
Expected: `all tests passed` (the pre-existing cases prove the
implementer/spike/X4 paths are unbroken; the new cases prove the lane).

- [ ] **Step 6: Commit**

```bash
git add skills/implementing-tickets tests/implementing-tickets skills/architecting
git commit -m "feat(dispatch): architect lane — state-routed ARCHITECT role, fable pin, X4 exemption, per-lane slot caps"
```

---

### Task 9: `issue-dispatch.yml` template trigger

**Files:**
- Modify: `skills/implementing-tickets/references/issue-dispatch.yml:37`

- [ ] **Step 1: Edit the trigger condition** — line 37:

```yaml
    if: (github.event.label.name == 'status:ready-for-implementer' || github.event.label.name == 'status:ready-for-architect') && github.actor == 'SSFSKIM'
```

- [ ] **Step 2: Validate the workflow file parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('skills/implementing-tickets/references/issue-dispatch.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add skills/implementing-tickets/references/issue-dispatch.yml
git commit -m "feat(dispatch): issue-event template triggers on both lane labels"
```

### Task 10: Skill rename — `implementing-tickets` → `implementing`

Directory + skill-name rename with a grep-driven reference sweep. Prose
CONTENT changes come in Tasks 11–13; this task changes names and paths
only, ending green.

**Files:**
- Rename: `skills/implementing-tickets/` → `skills/implementing/`;
  `tests/implementing-tickets/` → `tests/implementing/`
- Modify (path/name references): `skills/issue-tracker/scripts/board-sweep.sh:61`,
  `skills/reviewing-prs/scripts/review-dispatch.sh:50,377`,
  `skills/issue-tracker/scripts/board-register.sh:10`,
  `skills/issue-tracker/scripts/board-reconcile.sh:10`,
  `skills/issue-tracker/SKILL.md` (name refs only),
  `tests/implementing/test-implement-dispatch.sh` (its `DISPATCH=` and
  mock paths), `tests/implementing/test-protocol-content.sh` (path
  constants), every other live reference the grep in Step 3 names.

- [ ] **Step 1: Rename**

```bash
git mv skills/implementing-tickets skills/implementing
git mv tests/implementing-tickets tests/implementing
```

Edit `skills/implementing/SKILL.md` frontmatter: `name: implementing`
(description content updated in Task 11).

- [ ] **Step 2: Update the two cross-skill hardcoded paths** (the sites
prior verification found outside grep-obvious prose):

`skills/issue-tracker/scripts/board-sweep.sh:61`:

```bash
IMPLEMENT_DISPATCH_CMD="${IMPLEMENT_DISPATCH_CMD:-$SKILL_DIR/../implementing/scripts/implement-dispatch.sh}"
```

`skills/reviewing-prs/scripts/review-dispatch.sh:377`:

```bash
    P_IMPLEMENT_PROTOCOL_FILE="${SKILL_DIR%/*}/implementing/SKILL.md" \
```

- [ ] **Step 3: Grep-driven sweep of every remaining live reference**

Run: `grep -rln "implementing-tickets" --exclude-dir=docs --exclude-dir=evals --exclude-dir=node_modules --exclude-dir=review-bench --exclude-dir=.git .`
For every file listed: replace `implementing-tickets` →
`implementing` (both the `doperpowers:implementing-tickets` skill name
and path fragments). Historical `docs/` and the frozen benchmark
artifacts under `tests/review-bench/results/` stay untouched (the
`--exclude-dir` keeps them out of the listing — never rewrite them).
One file the grep names deserves a caution:
`tests/reviewing-prs/test-review-dispatch.sh:311` asserts the literal
protocol path `skills/implementing-tickets/SKILL.md` — the plain
replacement is exactly right there (the assertion tracks
`review-dispatch.sh:377`'s Step-2 edit). Re-run the grep.
Expected final output: empty.

- [ ] **Step 4: Run everything renamed**

Run: `tests/issue-tracker/test-board-scripts.sh && tests/implementing/test-implement-dispatch.sh && tests/implementing/test-protocol-content.sh && tests/reviewing-prs/test-review-dispatch.sh`
Expected: board + dispatch + review-dispatch suites green
(`test-review-dispatch.sh` proves the renamed protocol path
`review-dispatch.sh` emits still points at a real file).
`test-protocol-content.sh` may FAIL on assertions naming old
paths/skill names — update those assertion strings (rename only, e.g.
`implementing-tickets/SKILL.md` → `implementing/SKILL.md`); content
assertions that fail for missing prose belong to Task 11, and if any
fails here, defer it by noting it in the Task 11 step rather than
weakening it now.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(skills): rename implementing-tickets → implementing (E1 skill split, part 1)"
```

---

### Task 11: `implementing` protocol rework — plan-execution mode, no plan authorship

**Files:**
- Modify: `skills/implementing/SKILL.md`
- Test: `tests/implementing/test-protocol-content.sh`

**Interfaces:**
- Consumes: `plan:` meta semantics (Task 3), transitions 4/5 legality
  (Tasks 1, 5).
- Produces: the Implementer protocol every plan-carrying dispatch runs.

- [ ] **Step 1: Add failing protocol-content assertions** to
`tests/implementing/test-protocol-content.sh`, in its existing
assertion idiom (grep the protocol file for required phrases):
the protocol must contain `MODE SELECTION`, `plan-execution`,
`ready-for-architect`, and must NOT contain `EXECPLAN:` (the retired
self-authoring mode) — four assertions.

- [ ] **Step 2: Run to verify they fail**

Run: `tests/implementing/test-protocol-content.sh 2>&1 | tail -10`
Expected: the four new assertions FAIL.

- [ ] **Step 3: Edit `skills/implementing/SKILL.md`**

Frontmatter description becomes:

```yaml
description: Use when dispatched as an IMPLEMENT worker onto a board ticket (including the spike lane) — plan-execution or DIRECT mode; plan authorship belongs to doperpowers:architecting. Also when operating or setting up the autonomous implement loop — the inverse of doperpowers:reviewing-prs.
```

Insert a new section between `## Role` and `## The Gate`:

```markdown
## Mode Selection

MODE SELECTION — read your ticket's `board:meta` block first. The
`plan:` field decides your mode — machine-read, never note prose:

- `plan: <path>@<sha>` → **PLAN-EXECUTION**: an Architect authored your
  plan at that immutable revision on the recorded branch. NO intake
  gate — the Architect's phase carried the quality machinery (council,
  spec/plan review); you do not re-run the gate or re-judge the design.
- `plan: pre-spec` → **DIRECT**, with the plan-need ruling inherited:
  the Architect explicitly ruled the pre-spec suffices. Run the gate,
  but its plan-need check is bound by that ruling — you may still park
  for unrelated reasons.
- no `plan:` → **DIRECT** with the full gate below.
```

In `## The Gate`, after the two-check paragraph (before the Check-2
outcomes list), insert the escalation outcome:

```markdown
- Plan-need (DIRECT only; a `pre-spec` ruling binds this check) — the
  work needs a plan another session could execute: multiple sequenced
  milestones, work that must survive context death, or missing design
  decisions that are AGENT-answerable →
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-architect "<what needs designing and why>"
  and end your turn. Design gaps route to the architect lane — never to
  needs-human (the human address is for decisions only a human can make).
```

In `## Verdict`, the Fail bullet's dependency sentence (line 66) gets
the rename rule's return-target mapping:
"dependencies are edges, and the ticket goes back to ready-for-agent."
→ "dependencies are edges, and the ticket goes back to
`ready-for-implementer`."

In `## Verdict`, after the Pass line's gate-comment instruction, add:

```markdown
In PLAN-EXECUTION mode the verdict differs: your first board write is
{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-progress "plan-execution: <plan path>@<sha>"
and you post NO `[gate]` comment — the design was authorized at the
Architect's handoff, and re-litigating it is the exact thing this mode
removes.
```

In `## Execution`, replace the entire `EXECPLAN:` mode bullet (lines
99–106, from `- EXECPLAN: the work needs the document…` through
`…execute your own plan in this session.`) with:

```markdown
- PLAN-EXECUTION: open the plan at its pinned revision and execute it to
  the letter, evidence discipline unchanged. The plan on the branch is a
  LIVING document: when the codebase reveals divergence, absorb it —
  record what changed and why in the plan's Surprises/Revision Notes on
  your branch, adapt, and drive to the end. Only a GENUINELY blocked
  plan (not merely divergent) returns to its author — see Mid-build
  below. You author no plan document, ever: writing-plans,
  subagent-driven-development, and execplan authoring are other scopes'
  skills — plan AUTHORSHIP belongs to the architect lane
  (doperpowers:architecting); when work needs a plan, escalate, never
  self-author.
```

In `## Mid-build Forks and Parks`, append:

```markdown
A plan that proves GENUINELY blocked mid-execution (wrong about the
codebase in a way you cannot absorb, not merely divergent) is a return,
not a needs-human park:
{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-architect "<why the plan is blocked>" --branch <branch>
with WIP committed AND pushed on the branch first, plus the standard
orientation summary comment. This ends your scope (no bound pause — a
fresh Architect picks it up). The board enforces convergence: a second
traversal of the same edge parks needs-human mechanically — if your
return comes back unchanged and you still disagree, the machinery sends
the disagreement to the human; never bounce a third time yourself.
```

In `## Authority`, extend the "Yours:" sentence:

```markdown
YOUR AUTHORITY: your OWN ticket's open states via board-transition.sh
(never raw gh for status labels), including the architect-lane
escalations (`ready-for-architect` at gate time or as a mid-build
return); registering decomposition children (--parent {{ISSUE_NUMBER}})
and follow-up tickets (--spawned-by {{ISSUE_NUMBER}}) directly.
```

(rest of the NEVER sentence unchanged).

- [ ] **Step 4: Run the protocol-content suite to green**

Run: `tests/implementing/test-protocol-content.sh`
Expected: all pass, including the four new assertions.

- [ ] **Step 5: Commit**

```bash
git add skills/implementing tests/implementing
git commit -m "feat(implementing): plan-execution + DIRECT modes; plan authorship removed, architect escalation edges added (E1)"
```

---

### Task 12: Author `skills/architecting/SKILL.md`

**Files:**
- Create: `skills/architecting/SKILL.md` (replaces Task 8's stub)
- Test: `tests/implementing/test-protocol-content.sh` (assertions on the new protocol)

**Interfaces:**
- Consumes: transitions 1–3 (Tasks 1, 3), the batch-park format
  (issue-tracker's existing needs-human note law), `--plan` (Task 3).
- Produces: the protocol `implement-dispatch.sh` pins for
  `ready-for-architect` dispatches.

- [ ] **Step 1: Add failing assertions** to
`tests/implementing/test-protocol-content.sh`: the architecting protocol
file must exist, contain `ARCHITECT worker`, `Ends at the plan` (case
per Step 3), `--plan`, `pre-spec`, and NOT contain `{{ENGINE_NAME}}`
(the architect route is engine-exempt).

- [ ] **Step 2: Run to verify failure** (the Task 8 stub fails all
content assertions).

- [ ] **Step 3: Write the full protocol** — `skills/architecting/SKILL.md`:

```markdown
---
name: architecting
description: Use when dispatched as an ARCHITECT worker onto a ready-for-architect board ticket — the design phase of the implement lane relay; grills the ticket, decides the shape, and authors the plan an Implementer executes. Ends at the plan. The design-side counterpart of doperpowers:implementing.
---
# Architect Worker Protocol

Operator or setup invocation: read doperpowers:implementing
`references/operation-manual.md` instead. The protocol below is for a
dispatched Architect worker.

## Role

You are an ARCHITECT worker for ticket #{{ISSUE_NUMBER}} ({{ISSUE_URL}})
in {{REPO}}, running unattended in your own worktree. Your scope **Ends
at the plan**: you write no implementation code, and you never review
the Implementer's output — the review loop (doperpowers:reviewing-prs)
owns that, and no orchestrator-judge exists in this pipeline. Your
escalation targets are the board itself and the human on their next
wake. Read your ticket first (gh issue view {{ISSUE_NUMBER}} — body and
comments); that brief is the source of truth.

Toolkit:

- board scripts: {{BOARD_SCRIPTS}}

## The Gate (architect-lane bar)

Run both checks from the board schema's single copy —
{{BOARD_SCRIPTS}}/../references/ticket-gate.md — under its
ARCHITECT-LANE VARIANT: WELL-DEFINED means the PURPOSE and success
criteria are stated and human-taste forks are answered or
enumerable-for-parking; open DESIGN forks are your work, not gate
failures. Check-2 (WELL-SCOPED) applies unchanged.

VERDICT IS YOUR FIRST BOARD WRITE. Dispatch wrote nothing.

- Pass → {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-design
  then a one-line gate comment:
  gh issue comment {{ISSUE_NUMBER}} --body "[gate] pass — architect: <one line>"
- Fail → the park state with its required note, classified against the
  park discriminant (doperpowers:issue-tracker owns the single copy),
  plus the 3–6 line orientation summary every park carries.
- Too big (Check-2) → take the Pass write first — `in-design` plus the
  gate comment "[gate] pass — architect: too big, decomposing" — then
  decompose (below). Decomposing is design work and its exit is an
  in-design exit; the board has no `ready-for-architect →
  ready-for-implementer` edge, so skipping this write leaves you with no
  legal move. Slices needing one continuously steered human context →
  interactive-preferred.

## Design

Your behavior protocol is doperpowers:brainstorming plus
doperpowers:decomposing, applied per-ticket in worker clothes — grill,
decide, author, end. There is no synchronous human gate; the council and
parks carry the quality machinery.

- **Grill against the codebase first** — a question the code can answer
  is answered by reading it, never parked. Unclear nontrivial decisions
  only the human can settle become ONE needs-human park in the existing
  batch format: numbered questions, each with your recommended answer
  (board-answer.sh relays the answers into this session; park = pause,
  your binding survives).
- **Bank WIP at every park from in-design**: draft plan committed and
  PUSHED on the ticket branch, branch recorded via --branch. A parked
  session that dies unresumably must not take the pipeline's most
  expensive in-flight asset with it.
- **Track judgment (council scaling)** — pick the artifact shape:
  - ExecPlan shape (medium; big-but-atomic): solo. Grill, author one
    self-contained ExecPlan to the doperpowers:execplan bar (a
    zero-context session executes it), end.
  - Spec → Impl Plan shape (large/novel/high-stakes): the council —
    dispatch doperpowers:critique on the matured design and debate to
    convergence; run the spec-review pass; dispatch
    doperpowers:plan-reviewer on the implementation plan. All existing
    machinery, reused.
- **Down-shortcircuit** — the ticket turned out small; the pre-spec
  suffices as the plan:
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-implementer "pre-spec suffices as the plan" --plan pre-spec
  Your ruling binds the Implementer's plan-need check (it attaches to
  the ticket, not to one worker). End your turn.
- **Decompose** — at the gate or discovered mid-design: register
  children per {{DECOMPOSE_DOC}}, applying the birth rule to each child
  (obvious multi-milestone / novel-design / cross-cutting children are
  born ready-for-architect; everything else — including every unsure
  case and every spike — ready-for-implementer). Update the parent (it
  becomes an epic, never dispatched), then exit from in-design:
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-implementer "decomposed — parent is an epic"
  No --plan (epics never dispatch; the epic pull returns the finished
  parent to in-progress). You write no code; end when the children
  stand.

## Closing Artifact

The plan is the ENTIRE interface to the Implementer — self-contained for
a zero-context executor; nothing you learned survives except what the
plan and the ticket carry. Commit the plan on the ticket branch and PUSH
it (cattle reclaim depends on origin-visible artifacts), then close your
scope in one transition:

{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-implementer "<brief context and intent>" --branch <branch> --plan <repo-path>@<full-commit-sha>

The `plan:` pin is machine-read — "plan attached" downstream means the
meta field, never note prose — and names the immutable revision the
review loop audits against (your Implementer's living-plan updates on
the branch are divergence evidence, not the contract). This transition
ends your scope and releases your binding: do not wait, poll, or touch
downstream work.

## If Resumed With Answers

The answers live on the ticket — treat them as ticket content. Re-state
your gate verdict against them in ONE paragraph as a ticket comment
("[gate] re-pass — <one line>", or a fresh park if they reshape the
scope), then continue the design from where it stands. If a returned
ticket arrives with an Implementer's blockage note (the return edge),
treat the note as new ticket content: re-enter through the gate, repair
or re-cut the plan, and hand off again — the board's convergence rule
sends a second disagreement on the same edge to the human by itself.

## Authority

Yours: your OWN ticket's open states via board-transition.sh (never raw
gh for status labels); registering decomposition children (--parent
{{ISSUE_NUMBER}}) and follow-up tickets (--spawned-by {{ISSUE_NUMBER}})
directly. NEVER: implementation code, plan execution, terminal states,
other tickets' states, reviewing the Implementer's output. Your dispatch
ignores engine:* labels by design (plan authorship is never
label-routed) — a route question is not yours to answer.
```

- [ ] **Step 4: Run the protocol-content suite to green**

Run: `tests/implementing/test-protocol-content.sh`
Expected: all pass.

- [ ] **Step 5: Run the dispatch suite once more** (it pins this file):

Run: `tests/implementing/test-implement-dispatch.sh`
Expected: `all tests passed` — the `architecting/SKILL.md` stub guard in
the test env now finds the real file and leaves it untouched.

- [ ] **Step 6: Commit**

```bash
git add skills/architecting tests/implementing
git commit -m "feat(architecting): the Architect worker protocol (E1 skill split, part 2)"
```

---

### Task 13: Board-schema documents — gate variant, state table, discriminant, rituals

**Files:**
- Modify: `skills/issue-tracker/references/ticket-gate.md`
- Modify: `skills/issue-tracker/SKILL.md`
- Modify: `skills/implementing/references/implement-decompose.md:21-24`
- Modify: `skills/implementing/references/spike-worker-protocol.md:76`
- Modify: `skills/implementing/references/operation-manual.md:56,188`

- [ ] **Step 1: `ticket-gate.md`** — three edits:

Title/intro (lines 1–12): retitle `# The Ticket Gate — what the
dispatchable lane states mean`; in the intro replace the single
`ready-for-agent` mention: registrars triage honestly against it —
"a dispatchable lane state only if the ticket would pass (the birth
rule: design-heavy work → `ready-for-architect`; everything else,
including every unsure case and every spike → `ready-for-implementer`)".

Check-2 sizing (line 35) — replace the first sentence with:

```markdown
The work must fit the ticket as one purpose-unit: roughly ONE plan — an
ExecPlan, or a Spec → Impl Plan for the largest work (the architect
lane's output; on a plan-less DIRECT ticket the pre-spec itself is the
plan) — big-but-ATOMIC work that cannot land halfway still counts as
ONE unit (plan-execution is what lands it whole).
```

Append a new section:

```markdown
## The architect-lane variant (Check 1)

On a `ready-for-architect` ticket, Check-1 cannot apply verbatim — open
architecture forks are exactly this lane's population. The variant:
WELL-DEFINED means the PURPOSE and success criteria are stated, and
human-taste forks are answered or enumerable-for-parking. Open DESIGN
forks are the lane's work, never gate failures. Check-2 applies
unchanged in both lanes.
```

- [ ] **Step 2: `skills/issue-tracker/SKILL.md`** — the edits, each
anchored:

1. Happy path (line 53): replace the sentence with "The architect lane's
   happy path is `ready-for-architect → in-design →
   ready-for-implementer → in-progress → in-review → done`; a direct
   ticket starts at `ready-for-implementer`. Under the review loop a PR
   passes through `confident-ready` between `in-review` and `done`."
2. State table (line 59, the `ready-for-agent` row): replace with three
   rows:

```markdown
| `ready-for-architect` | open + `status:ready-for-architect` | dispatchable to DESIGN: purpose + success criteria stated to the architect-lane bar (`references/ticket-gate.md` variant); the work needs design/plan authorship by an Architect (Fable route) | — |
| `in-design` | open + `status:in-design` | the Architect's in-flight state — gate passed, grill/authoring underway; its parks return here (`pre-park:`) | optional |
| `ready-for-implementer` | open + `status:ready-for-implementer` | dispatchable to EXECUTION: an Architect's plan attached (`plan:` pin), ruled pre-spec-sufficient (`plan: pre-spec`), or plan-less DIRECT (the gate — `references/ticket-gate.md` — runs at dispatch); the DEFAULT birth state (unsure → implementer) | — |
```

3. Park discriminant paragraph (lines 70–83): after the
   `interactive-preferred` sentence, insert the third address + writers:

```markdown
The discriminant has a THIRD address: missing or broken design that an
AGENT can author → `ready-for-architect` — written by the Implementer's
gate (plan-need), the Implementer mid-build (a genuinely blocked plan),
and the review worker at a design-gap impasse; never by-passed into
`needs-human` (the human address is for what only a human can give).
The board counts these escalation edges: a second traversal of the same
edge on one ticket converts to `needs-human` mechanically.
```

   and update the unblock sentence: "cut `blocked-by` and return the
   ticket to its lane queue (`ready-for-implementer`, or
   `ready-for-architect` by your judgment of the birth rule)".
4. "Who writes the board" table (lines 44–49): the Implement worker row's
   writes gain "; architect-lane escalations"; add a row above it:

```markdown
| **Architect worker** (daemon, one ticket, Fable route) | its OWN ticket's open states through the design phase (`in-design`, handoff to `ready-for-implementer` with the `plan:` pin); NEW child/follow-up tickets | doperpowers:architecting |
```

   and the Review worker row's writes become "its PR's ticket
   (`confident-ready` / `needs-human` / `ready-for-architect`)".
5. Dispatch ritual step 2 (lines 151–172): replace the ROLE/protocol
   sentence with: "`ROLE` = `SPIKE` when the ticket's category is
   `spike` (state-free — category outranks lane), `ARCHITECT` when the
   state is `ready-for-architect`, else `IMPLEMENT`; `PROTOCOL_FILE` =
   the lane's protocol (spike → doperpowers:implementing
   `references/spike-worker-protocol.md`; architect →
   doperpowers:architecting `SKILL.md`; else doperpowers:implementing
   `SKILL.md`). The ARCHITECT dispatch ignores `engine:*` labels and
   `$WORKER_ENGINE` — plan authorship is never label-routed — and pins
   `${ARCHITECT_MODEL:-fable}` on the plain-Claude route; the
   engine resolution earlier in this step applies to the other roles."
6. Wake ritual needs-human bullet (lines 209–218): the fallback sentence
   becomes "Fallback — no/dead bound session, or answers that reshape
   the ticket's scope: answer in a comment (or edit the body), then
   `board-transition.sh <n> ready-for-implementer` (or
   `ready-for-architect` per the birth rule; strip a stale `plan:` pin
   with a fresh Architect pass when the scope answer invalidates the
   plan) — the next dispatch runs the lane's protocol against the
   enriched ticket from fresh context. An answered park with a live
   bound session returns to its `pre-park:` state automatically."
7. Worker protocols section (lines 239–248): name three protocols
   (architecting SKILL.md added; implementing paths renamed).
8. Consumer-automation edge case (line 315–319): "must track the v9
   vocabulary (the two lane-queue labels replace the single pre-v9
   agent-queue label)" — phrased WITHOUT the retired literal, so the
   repo-wide grep in Task 16 needs no carve-out for live skill prose.

- [ ] **Step 3: The three implementing references** — apply the rename
decision rule: `implement-decompose.md` step 3's `ready-for-agent` →
"a dispatchable lane state (the birth rule: design-heavy children →
`ready-for-architect`, else `ready-for-implementer`)";
`spike-worker-protocol.md:76` graduation text → same phrasing;
`operation-manual.md:56` → same; `operation-manual.md:188` → "flip back
to `ready-for-implementer`".

- [ ] **Step 4: Verify no stale vocabulary in skills**

Run: `grep -rn "ready-for-agent" skills/issue-tracker/ skills/implementing/ skills/architecting/ | grep -v board-migrate-gh.sh`
Expected: no output. (Scoped to THIS task's skills — `skills/triaging-feedback/`
is Task 14's, and Task 16's repo-wide grep is the final proof.)

- [ ] **Step 5: Run the full local suites** (docs changes can break
protocol-content assertions):

Run: `tests/issue-tracker/test-board-scripts.sh && tests/implementing/test-implement-dispatch.sh && tests/implementing/test-protocol-content.sh`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add skills/issue-tracker skills/implementing
git commit -m "docs(board): v9 schema — lane state table, third park address, architect-lane gate variant, lane-aware rituals"
```

---

### Task 14: triaging-feedback registrar learns the lane vocabulary

**Files:**
- Modify: `skills/triaging-feedback/src/gate.ts:6,97-115`,
  `src/verdict.ts:24`, `src/prompt.ts:15,23`
- Modify: `skills/triaging-feedback/references/triage-worker-protocol.md`,
  `references/setup.md`, `SKILL.md` (prose mentions)
- Test: `skills/triaging-feedback/test/` (vitest; existing specs updated)

The swap is 1:1 — `'ready-for-agent'` → `'ready-for-implementer'`
everywhere in this skill. The feedback registrar keeps its conservative
gate (no architect-lane births: feedback tickets are bug-shaped; a
design-heavy item lands `needs-human` for the human to route — this
preserves the existing demotion posture and adds no new capability).

- [ ] **Step 1: Update the vitest specs first** — in
`skills/triaging-feedback/test/`, replace every `ready-for-agent` string
with `ready-for-implementer`.

- [ ] **Step 2: Run to verify failure**

Run: `(cd skills/triaging-feedback && npm test)`
Expected: failures — src still emits the old state.

- [ ] **Step 3: Implement** — `gate.ts:6`:

```typescript
export type BirthState = 'ready-for-implementer' | 'needs-human' | 'needs-info';
```

then replace every `'ready-for-agent'` literal in `gate.ts` (the
`routeTicket` demotion returns and final return) and `verdict.ts:24`'s
`STATES` array with `'ready-for-implementer'`; update the two Korean
prompt lines (`prompt.ts:15,23`) the same way; sweep the three prose
files with the same 1:1 replacement.

- [ ] **Step 4: Run to green**

Run: `(cd skills/triaging-feedback && npm test)`
Expected: all vitest suites pass.

- [ ] **Step 5: Commit**

```bash
git add skills/triaging-feedback
git commit -m "feat(triaging-feedback): registrar births ready-for-implementer (v9 vocabulary, 1:1 swap)"
```

---

### Task 15: reviewing-prs contract — plan admissibility, anchor, third address

Text-only protocol edits; the QAgent model pin and the `fix-wave` agent
declaration are OUT of scope (they ride C5 — the Task 17 follow-up
ticket).

**Files:**
- Modify: `skills/reviewing-prs/SKILL.md` (five anchored edits)

- [ ] **Step 1: Spec hierarchy** — after the sentence ending "never the
PR head." (line ~153) insert:

```markdown
One more admissible source on an architect-lane ticket: the ticket's
`plan:` meta pin (`<path>@<sha>`) names the Architect-authored plan at
an immutable revision — resolve that path at exactly that SHA, never
the branch tip (the Implementer's living-plan updates on the branch are
evidence of absorbed divergence, not the contract; a `plan: pre-spec`
sentinel adds nothing — the issue body is the plan). Audit the PR
against the pinned plan plus the issue body together.
```

- [ ] **Step 2: Authorization anchor** — in the "Timestamp drift"
paragraph (line ~159), after "the `[gate] pass` timestamp", insert:

```markdown
On a ticket whose `plan:` pin names a revision (`<path>@<sha>`, not the
`pre-spec` sentinel) there is no implementer `[gate] pass` — that ticket
ran in PLAN-EXECUTION mode, which posts none. The authorization time is
the Architect's handoff: the `[board] ready-for-implementer:` comment's
timestamp, and every rule in this audit keyed to the gate timestamp
reads that comment instead. A `plan: pre-spec` ticket ran DIRECT and
carries a real `[gate] pass` — anchor on it as usual.
```

- [ ] **Step 3: Missing-section rule** (line ~205): change "only when
the ticket carries a `[gate] pass` comment" to "only when the ticket
carries a `[gate] pass` comment or an Architect handoff comment (the
`plan:` pin's authorization — see the audit's anchor rule)".

- [ ] **Step 4: The impasse route + AUTHORITY** — in RE-REVIEW (line
~276-281), replace from "At the cap with unresolved blockers" to the end
of that paragraph with:

```markdown
The exit condition is no NEW blocker, not a clean report. At the cap
with unresolved blockers there is no confidence to grant. When those
blockers cluster at one seam — each wave's fix spawning the next finding
there — that is a decomposition defect an AGENT can re-cut: set ticket
#{{ISSUE_NUMBER}} to ready-for-architect with the impasse summary as the
note (the design-gap address; the board converts a second traversal of
this edge to needs-human mechanically — never write it twice yourself).
Otherwise — an impasse that needs human judgment or input — set the
ticket to needs-human with the impasse summary and end your turn.
```

The `ready-for-architect` branch ends the turn too — say so on that
branch, so neither exit reads as fall-through.

In AUTHORITY (line ~326), change the parenthetical to
"(confident-ready / needs-human / ready-for-architect — notes required
for the parks and the escalation)".

- [ ] **Step 4b: The two rules the new lane makes incomplete** — both
outside the five sites above, both load-bearing:

ORIENT (line ~65) tells the worker to locate the `[gate] pass` comment
as the authorization time. A real-pin ticket has none — add the
handoff-comment alternative here, matching the Step 2 anchor rule, so
the read-only pass doesn't come up empty.

ESCALATE's PARKED tier (line ~332) enumerates the states over which
confident-ready may never be granted, and names only `needs-human`.
Extend it to cover a ticket just set to `ready-for-architect` by the
Step 4 impasse route — without this the new escalation has no
confidence-tier protection behind it.

- [ ] **Step 5: TOO-BIG registration** (line ~236): after the
`board-register.sh` command line, add: "Birth classification applies:
the default is `ready-for-implementer`; a finding that is missing DESIGN
(not just missing work) passes `--state ready-for-architect`."

- [ ] **Step 6: Verify + commit**

Run: `grep -n "ready-for-architect" skills/reviewing-prs/SKILL.md | head`
Expected: the five edit sites appear.

```bash
git add skills/reviewing-prs
git commit -m "feat(reviewing-prs): plan-pin admissibility, handoff anchor, ready-for-architect impasse route (E1; pins/fix-wave ride C5)"
```

---

### Task 16: Full validation sweep + version bump

- [ ] **Step 1: Run every suite**

```bash
tests/issue-tracker/test-board-scripts.sh
tests/issue-tracker/test-board-sweep.sh
node tests/issue-tracker/test-board-template.cjs
tests/implementing/test-implement-dispatch.sh
tests/implementing/test-protocol-content.sh
tests/reviewing-prs/test-review-dispatch.sh
(cd skills/triaging-feedback && npm test)
tests/claude-code/run-skill-tests.sh
scripts/lint-shell.sh
```

Expected: every command green. `run-skill-tests.sh` failures will name
skill files whose references went stale in the rename — fix per the
rename rule and re-run.

- [ ] **Step 2: Repo-wide residual check**

Run: `grep -rn "ready-for-agent" --exclude-dir=docs --exclude-dir=evals --exclude-dir=node_modules --exclude-dir=teaching --exclude-dir=review-bench --exclude-dir=.git . | grep -v board-migrate-gh.sh | grep -v 2026-07-31-implement-lane-split.md`
Expected: no output. Same for
`grep -rln "implementing-tickets" --exclude-dir=docs --exclude-dir=evals --exclude-dir=node_modules --exclude-dir=review-bench --exclude-dir=.git .`
(`tests/review-bench/results/` is frozen benchmark output holding both
old vocabularies — excluded, never rewritten.)

- [ ] **Step 3: Version bump (minor — new states + skill split are a
feature release)**

Run: `scripts/bump-version.sh minor`
Expected: manifests updated to 7.30.0 per `.version-bump.json`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(release): v7.30.0 — E1 implement lane split"
```

---

### Task 17: Final verification — spec acceptance, live-board migration, follow-ups

- [ ] **Step 1: Execute the spec's acceptance section as written** —
from `docs/doperpowers/specs/2026-07-30-implement-lane-split-design.md`
"## Acceptance (observable)", each item verbatim, with its proof:

1. "A ticket registered `ready-for-architect` is picked up by a
   Fable-routed worker whose first board write is the gate verdict …" —
   static proof: Task 8's dispatch tests (role/model/protocol) + Task 12's
   protocol content; live proof deferred to the first architect dispatch.
2. "A dispatch on `ready-for-implementer` with a `plan:` meta field
   spawns an Opus worker that authors no plan document …" — Task 11's
   mode-selection protocol + Task 8 dispatch tests; live proof deferred.
3. "An Implementer dispatched on a plan-less ticket that needs a plan
   writes `ready-for-architect` (with note) as its verdict — not
   `needs-human`." — Task 5's escalation-edge test + Task 11's gate text.
4. "A mid-execution genuine blockage lands as `in-progress →
   ready-for-architect` with note + orientation summary + WIP …" — Task
   5's edge tests + Task 11's mid-build text.
5. "A label-less review dispatch spawns ONE Opus-high QAgent …" —
   **deferred to the C5-riding follow-up** (Step 3); the review loop is
   untouched by this plan beyond protocol text.
6. "An Architect on an oversized goal routes to decomposing and
   registers children carrying lane states …; a `spike` child is born
   `ready-for-implementer`." — Task 12's decompose section + Task 2's
   birth tests + ticket-gate/decompose docs (Task 13).
7. "A ticket that traverses the same escalation/return edge twice parks
   `needs-human` …" — Task 5's convergence tests.
8. "An answered Architect park resumes the ticket into `in-design`, and
   the resumed session completes via transition 2 legally." — Task 4's
   pre-park tests + Task 3's handoff test.

Record this mapping in the turn-end/PR body as Validation Evidence.

- [ ] **Step 2: Migrate THIS repo's live board** (run after the merge to
main, from the repo root; the old label reads as `conflict` until each
ticket is repaired):

```bash
# open tickets currently in status:ready-for-agent (from the pre-plan survey:
# #40 #39 #38 #37 #32 — re-derive the live list first):
gh issue list --state open --label "status:ready-for-agent" --json number -q '.[].number'
# each one (repair path: conflict → any open state):
for n in $(gh issue list --state open --label "status:ready-for-agent" --json number -q '.[].number'); do
  skills/issue-tracker/scripts/board-transition.sh "$n" ready-for-implementer
done
gh label delete "status:ready-for-agent" --yes
skills/issue-tracker/scripts/board-lint.sh
```

Expected: lint exits 0 (or names only pre-existing WARNs).

- [ ] **Step 3: Register the two follow-up tickets** (bodies written to
temp files first, per the ticket contract):

1. `"QAgent Opus-high pin + fix-wave agent declaration (rides C5)"
   enhancement P2 --blocked-by 32 --state ready-for-implementer` — body:
   the spec's reviewing-prs pin decisions (QAgent = ONE Opus high on the
   plain-Claude route; `agents/fix-wave.md` declared on Opus medium
   replacing `wave-board.md`'s general-purpose Task dispatch, its
   quiescence/ledger contract preserved; X4 precedence: an
   `engine:codex` label overrides the pins), citing spec section "Model
   pins ride dispatch, not protocols".
2. `"v9 board-vocabulary consumer migration (ida-solution) + teaching
   SQL examples" enhancement P3` — body: the consumer checklist — plugin
   update to 7.30.0; run Step 2's label migration on the ida-solution
   board; update the live `issue-dispatch.yml` `if:` condition to the
   two lane labels (Task 9's template is the source); the
   `teaching/cloud-scale-architecture` lessons' SQL predicates.

- [ ] **Step 4: Leave the spec's living tail alone** — its
`## Outcomes & Retrospective` stays "Pending — written at finish" (the
finishing session writes it after the follow-ups resolve); the plan
pointer already rides the spec's v1.3.1 revision note. Nothing to
commit here.

