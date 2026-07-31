# E2 Interim Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the E2 ledger contract's interim doperpowers slice (spec `docs/doperpowers/specs/2026-07-30-ticket-ledger-observability-design.md` v2.1, § Interim slice): the `env-issue` category with its inverted birth rule, the recomposition return replacing epic auto-close (with all four board-mechanics amendments), the parent-pin dispatch stamp, the sweep's parent-impact reconcile pass, the scale-review dispatch branch, and the worker-protocol/doctrine prose.

**Architecture:** All board logic lives in `skills/issue-tracker/scripts/_board.py` (tables + helpers) consumed by thin shell scripts via heredoc Python. The recomposition lifecycle replaces `close_epics` with `recompose_epics` at every call site; epic-guarded legality lives in `board-transition.sh`'s gate section; dispatch carve-outs live in `_board.py:eligible()`. Protocol prose is behavior — it gets content-pinned tests like code.

**Tech Stack:** bash + python3 heredocs, `gh` CLI (mocked in tests), shell test harnesses under `tests/`.

## Global Constraints

- Branch: work on `e2-ledger-contract`; integration target is `feature/en-cycles`. Never touch `main`.
- Never use `git stash` (shared stash stack across worktrees).
- Spec v2.1 is the contract. Binding values, verbatim:
  - New category label: `env-issue`. `CATEGORIES` becomes `("bug", "enhancement", "spike", "env-issue")`.
  - env-issue birth rule: registrar names a concrete agent-executable repair path ⇒ explicit `--state ready-for-implementer` (or `ready-for-architect` when design-heavy); otherwise **default birth is `needs-human`** (NOT the generic `ready-for-implementer` default).
  - Recomposition trigger: **all children terminal** ("required" = every child; no optionality machinery). The old at-least-one-done guard is retired: an all-wontfix epic also returns for recomposition.
  - The return target is `ready-for-architect` with note `recomposition-due: all children terminal`, audit comment marker **`[board-epic]`** (never the convergence-counted `[board] <from> → <to>:` format).
  - Epic dispatch carve-out: an epic is eligible ONLY in `ready-for-architect` AND only when all its children are terminal (plus the usual blocked-by check).
  - Scoped terminal authority: `in-design → done` becomes legal **for epics only**. (`in-design → wontfix` is already legal for all tickets.)
  - Code-bearing route: `in-design → in-review` becomes legal **for epics only**; the in-review PR gate accepts the closure package recorded in the `pr` meta slot for epics.
  - Parent-pin: dispatch stamps `parent-pin: #<parent> @ <repo HEAD sha>` into the child's board meta at dispatch time. `META_KEYS` gains `parent-pin`.
  - Parent-impact proposals: a structured comment on the child's own ticket beginning `[parent-impact]`. The sweep's reconcile pass performs the parent's `ready-for-architect` return; dedup via a `[board-epic] reconcile:` comment on the parent naming `#<child>@<comment-id>`.
  - Worker write doctrine unchanged: subagents never write; env-issue filing is opt-in authority, not a duty; source ticket untouched by a filing.
- Plugin version: bump `7.30.0 → 7.31.0` via `scripts/bump-version.sh 7.31.0` (never hand-edit manifests) — final task only.
- Commit messages: conventional prefixes, no attribution trailers.
- Tests run from the repo root: `tests/issue-tracker/test-board-scripts.sh`, `tests/issue-tracker/test-board-sweep.sh`, `tests/implementing/test-implement-dispatch.sh`, `tests/implementing/test-protocol-content.sh`, `tests/reviewing-prs/*.sh` (run via each file directly). They use a mock `gh`; no network.
- In test helpers, never pipe `printf` into `grep -Fq` under pipefail (SIGPIPE flake) — use herestrings, matching existing harness style.

## File Structure

| File | Responsibility in this slice |
|---|---|
| `skills/issue-tracker/scripts/_board.py` | Tables (`CATEGORIES`, `META_KEYS`, label colors), `ensure_labels`, `eligible` epic carve-out, `recomposition_ready`, `recompose_epics` (replaces `close_epics`) |
| `skills/issue-tracker/scripts/board-register.sh` | env-issue birth rule + usage docs |
| `skills/issue-tracker/scripts/board-transition.sh` | Epic-guarded edges, closure-package PR gate, recompose call sites, finalize path |
| `skills/issue-tracker/scripts/board-edge.sh` | recompose call sites (3) |
| `skills/issue-tracker/scripts/board-sweep.sh` | `pass_impact` — parent-impact reconcile |
| `skills/implementing/scripts/implement-dispatch.sh` | parent-pin stamp at dispatch |
| `skills/reviewing-prs/scripts/review-dispatch.sh` | sweep branch: in-review epics (no PR) dispatch the scale-review variant |
| `skills/architecting/SKILL.md` | Recomposition claim protocol + env-issue authority |
| `skills/implementing/SKILL.md`, `skills/implementing/references/spike-worker-protocol.md` | env-issue authority |
| `skills/reviewing-prs/SKILL.md` | Scale-review variant + env-issue authority |
| `skills/issue-tracker/SKILL.md` | Category list, birth rule, writers, markers, recomposition doctrine |
| `skills/decomposing/SKILL.md` | Recomposition lifecycle + upward-revision protocol |
| `tests/issue-tracker/test-board-scripts.sh` | Board behavior coverage |
| `tests/issue-tracker/test-board-sweep.sh` | Sweep pass coverage |
| `tests/implementing/test-implement-dispatch.sh` | Dispatch coverage |
| `tests/implementing/test-protocol-content.sh` | Protocol prose pins |
| `tests/reviewing-prs/test-review-dispatch.sh` | Scale-review dispatch coverage |

---

### Task 1: `env-issue` category + inverted birth rule

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:146-150` (categories block), `:380-395` (`ensure_labels`)
- Modify: `skills/issue-tracker/scripts/board-register.sh:9-15` (usage), `:62-90` (validation)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: existing `CATEGORIES`, `ensure_labels()`, `BIRTH`, `NOTE_REQUIRED`.
- Produces: `CATEGORIES == ("bug", "enhancement", "spike", "env-issue")`; `ENV_ISSUE_COLOR = "e4a0f7"`; registration behavior: env-issue with no explicit `--state` births `needs-human` (note required); explicit agent-lane birth allowed.

- [ ] **Step 1: Write the failing tests** — append a section to `tests/issue-tracker/test-board-scripts.sh` (before the summary footer, following the spike-section style around line 1012):

```bash
# ---- env-issue category (E2 interim slice) --------------------------------------
echo "env-issue category:"
# default birth inverts to needs-human (spec v2.1 birth rule)
out="$(run board-register.sh "Registry flakes on pull" env-issue P2 \
  --note "need registry mirror credentials rotated" --body-file "$SPEC_BODY")"
env_t="$(state "s['next']-1")"
assert_contains "$(state "s['issues']['$env_t']['labels']")" "env-issue" "env-issue category label applied"
assert_contains "$(state "s['issues']['$env_t']['labels']")" "status:needs-human" "env-issue defaults to needs-human, not ready-for-implementer"
# the label is board-managed: ensure_labels created it in the mock label store
assert_contains "$(state "sorted(s['labels'])")" "env-issue" "ensure_labels creates the env-issue label"
# default birth without a note is refused (needs-human requires one)
assert_fails run board-register.sh "Mystery env pain" env-issue P2 --body-file "$SPEC_BODY"
# a named repair path births an agent lane explicitly
run board-register.sh "Pin the broken fixture image" env-issue P2 \
  --state ready-for-implementer --body-file "$SPEC_BODY" >/dev/null
env_a="$(state "s['next']-1")"
assert_contains "$(state "s['issues']['$env_a']['labels']")" "status:ready-for-implementer" "explicit agent-lane env-issue birth allowed"
# filing never touches another ticket: register with --spawned-by and assert source unchanged
run board-register.sh "Source ticket" enhancement P2 --body-file "$SPEC_BODY" >/dev/null
src_t="$(state "s['next']-1")"
run board-transition.sh "$src_t" in-progress >/dev/null
before="$(state "sorted(s['issues']['$src_t']['labels'])")"
run board-register.sh "Flaky DNS in CI" env-issue P3 \
  --note "needs infra DNS fix" --spawned-by "$src_t" --body-file "$SPEC_BODY" >/dev/null
assert_equals "$(state "sorted(s['issues']['$src_t']['labels'])")" "$before" "env-issue filing leaves the source ticket untouched"
```

- [ ] **Step 2: Run to verify failure**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -20`
Expected: FAIL — "env-issue defaults to needs-human" (register dies on unknown category first).

- [ ] **Step 3: Implement** — in `_board.py`, replace the categories block:

```python
# Categories: bug/enhancement are GitHub defaults; spike (the exploration
# lane — deliverable is findings, never a merge) and env-issue (E2:
# environmental friction, fire-and-continue registration) are
# board-managed, so ensure_labels creates them.
CATEGORIES = ("bug", "enhancement", "spike", "env-issue")
SPIKE_COLOR = "f9d0c4"
ENV_ISSUE_COLOR = "e4a0f7"
```

In `ensure_labels()`, after the spike entry:

```python
    want += [("env-issue", ENV_ISSUE_COLOR,
              "issue-tracker board category: environmental friction — "
              "fire-and-continue report; default birth needs-human")]
```

In `board-register.sh`, update the usage header category line:

```
#   category  bug | enhancement | spike (exploration lane: deliverable is a
#             findings comment, never a merge — see doperpowers:implementing)
#             | env-issue (environmental friction report — E2: defaults to
#             needs-human unless the registrar names an agent-executable
#             repair path via an explicit --state)
```

In the Python validation body, directly after the spike/ready-for-architect ban:

```python
# E2 birth rule (inverted for this category only): environmental friction
# that an authorized agent could reach would typically already be solved —
# unsure defaults to the human, not the implement queue. An explicit
# --state is the registrar's positive claim of a named repair path.
if category == "env-issue" and env["T_STATE_EXPLICIT"] != "1":
    state = "needs-human"
    if not note:
        B.die("an env-issue defaults to needs-human and requires --note "
              "naming the requested intervention (or pass an explicit "
              "--state with a named agent repair path)")
```

Note: this block must run BEFORE the `state in B.NOTE_REQUIRED and not note` check so the die message is the specific one; place it immediately after the spike ban and move nothing else. The generic NOTE_REQUIRED check then passes because `note` is set.

- [ ] **Step 4: Run to verify pass**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -5`
Expected: PASS (all assertions, including all pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/_board.py skills/issue-tracker/scripts/board-register.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): env-issue category with inverted needs-human birth default"
```

---

### Task 2: Recomposition core — `recompose_epics` replaces `close_epics`

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:484-576` (`eligible`, `close_epics`)
- Modify: `skills/issue-tracker/scripts/board-transition.sh:74,170` and `skills/issue-tracker/scripts/board-edge.sh:99,101,110` (call sites)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: `apply_state`, `comment`, `epics`, `children`, `TERMINAL`, `DISPATCHABLE`.
- Produces:
  - `recomposition_ready(tickets, tid) -> bool` — tid is an epic, not terminal, has children, all terminal.
  - `recompose_epics(tickets, p, lines)` — walks the parent chain; each recomposition-ready epic returns to `ready-for-architect` via `apply_state(..., bookkeeping=True)` with note `recomposition-due: all children terminal`.
  - `apply_state(..., bookkeeping=False)` — when True, the audit comment is `[board-epic] <to>: <why>` regardless of edge (never the convergence-counted format).
  - `eligible()` epic carve-out: epics are eligible only via `recomposition_ready` + state `ready-for-architect` + blocked-by clear.
  - `close_epics` is DELETED (grep must show no references).

- [ ] **Step 1: Write the failing tests** — in `tests/issue-tracker/test-board-scripts.sh`, REPLACE the two old auto-close assertions (lines ~146-147: "epic closes when all children terminal, one done" / "epic closed as completed") and the finalize-closes-epic assertions (~543-544) with the recomposition behavior, and add a new section:

```bash
# (in place of the old auto-close assertion block)
out="$(run board-transition.sh 4 done)"
assert_contains "$out" "#1: in-progress → ready-for-architect" "last terminal child returns the epic for recomposition"
assert_contains "$(state "s['issues']['1']['labels']")" "status:ready-for-architect" "epic waits in ready-for-architect"
assert_not_contains "$out" "#1: in-progress → done" "epic never auto-closes"
```

```bash
# ---- recomposition lifecycle (E2) -----------------------------------------------
echo "recomposition:"
run board-register.sh "Recomp epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
rc_e="$(state "s['next']-1")"
run board-register.sh "Recomp child A" enhancement P2 --parent "$rc_e" --body-file "$SPEC_BODY" >/dev/null
rc_a="$(state "s['next']-1")"
run board-register.sh "Recomp child B" enhancement P2 --parent "$rc_e" --body-file "$SPEC_BODY" >/dev/null
rc_b="$(state "s['next']-1")"
run board-transition.sh "$rc_a" in-progress >/dev/null
# all-wontfix epic also returns (the one-done guard is retired)
run board-transition.sh "$rc_a" wontfix "not needed" >/dev/null
out="$(run board-transition.sh "$rc_b" wontfix "not needed either")"
assert_contains "$out" "#$rc_e: in-progress → ready-for-architect" "all-wontfix epic returns for recomposition (guard retired)"
# the return's audit comment is the bookkeeping marker, not the convergence format
assert_contains "$(state "s['issues']['$rc_e']['comments'][-1]")" "[board-epic]" "recomposition return posts the board-epic marker"
assert_not_contains "$(state "s['issues']['$rc_e']['comments'][-1]")" "[board] in-progress → ready-for-architect:" "return never writes the convergence-counted format"
# second cycle: corrective child, land it, return fires again w/o needs-human conversion
run board-register.sh "Recomp gap child" enhancement P2 --parent "$rc_e" --body-file "$SPEC_BODY" >/dev/null
rc_c="$(state "s['next']-1")"
run board-transition.sh "$rc_c" in-progress >/dev/null
out="$(run board-transition.sh "$rc_c" done)"
assert_contains "$out" "#$rc_e: in-progress → ready-for-architect" "second recomposition cycle returns again"
assert_not_contains "$(state "s['issues']['$rc_e']['labels']")" "status:needs-human" "bookkeeping returns never trip the convergence counter"
```

- [ ] **Step 2: Run to verify failure**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -20`
Expected: FAIL — old behavior closes the epic (`#1: in-progress → done`).

- [ ] **Step 3: Implement** — in `_board.py`:

Extend `apply_state`'s signature and comment branch:

```python
def apply_state(tickets, tid, to, why, extra_meta=None, bookkeeping=False):
```

and replace the comment block inside it:

```python
    if why:
        if bookkeeping:
            # Board bookkeeping on an epic (recompose/pull): the marker is
            # deliberately NOT the "[board] from → to:" format — the
            # convergence counter greps that format, and a mechanical
            # return must never count as a worker escalation traversal.
            comment(tid, "[board-epic] %s: %s" % (to, why))
        elif (old, to) in CONVERGENCE_EDGES:
            comment(tid, "[board] %s → %s: %s" % (old, to, why))
        else:
            comment(tid, "[board] %s: %s" % (to, why))
```

Replace `close_epics` wholesale with:

```python
def recomposition_ready(tickets, tid):
    """An epic whose every child is terminal awaits recomposition — E2:
    'required' = every child (no optionality machinery), and the old
    at-least-one-done guard is retired: an all-wontfix epic also wakes an
    Architect, whose verdict (done / wontfix / needs-human) replaces the
    guard's silent stall."""
    n = tickets.get(tid)
    if n is None or n["state"] in TERMINAL:
        return False
    kids = children(tickets, tid)
    return bool(kids) and all(tickets[k]["state"] in TERMINAL for k in kids)


def recompose_epics(tickets, p, lines):
    """E2 replaces the mechanical epic auto-close: a parent is closed by an
    Architect's VERIFICATION against its own acceptance (recomposition),
    never by child bookkeeping. When the last child lands, the epic
    returns to ready-for-architect — the one state where epics are
    dispatchable — with the recomposition-due note. Bookkeeping latitude:
    exempt from LEGAL and from convergence counting ([board-epic] marker)."""
    while p and p in tickets:
        if recomposition_ready(tickets, p) \
           and tickets[p]["state"] != "ready-for-architect":
            lines.append(apply_state(
                tickets, p, "ready-for-architect",
                "recomposition-due: all children terminal",
                bookkeeping=True))
        # the chain walk ends here: an ancestor can only become ready when
        # THIS epic reaches terminal via its own recomposition verdict
        break
```

Replace `eligible()`:

```python
def eligible(tickets, tid):
    n = tickets[tid]
    if tid in epics(tickets):
        # E2 carve-out: the ONE dispatchable epic state is
        # ready-for-architect, and only with every child terminal — a
        # queued corrective child must pull the epic back out of the
        # dispatch pool before an Architect claims a moving target.
        if n["state"] != "ready-for-architect" \
           or not recomposition_ready(tickets, tid):
            return False
    elif n["state"] not in DISPATCHABLE:
        return False
    return all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"])
```

Update call sites — `board-transition.sh` lines 74 and 168-170 and the header comment at lines 9-11, and `board-edge.sh` lines 99, 101, 110: every `B.close_epics(...)` becomes `B.recompose_epics(...)` (same arguments). Update `board-transition.sh`'s header line to:

```
#   → done/wontfix: an epic whose children are all terminal RETURNS to
#                   ready-for-architect for recomposition (E2) — epics are
#                   closed by an Architect's verdict, never by bookkeeping
```

- [ ] **Step 4: Run to verify pass**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -5`
Expected: PASS. Also run `grep -rn "close_epics" skills/` — expected: no output.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/_board.py skills/issue-tracker/scripts/board-transition.sh skills/issue-tracker/scripts/board-edge.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): recomposition return replaces epic auto-close"
```

---

### Task 3: Epic-guarded edges and the closure-package gate

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:67-112` (`LEGAL` comments only), `skills/issue-tracker/scripts/board-transition.sh:51-132` (gate section)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Consumes: `epics()`, `LEGAL`, the `T_PR` env plumbing.
- Produces: `in-design → done` and `in-design → in-review` legal for epics only (enforced in board-transition, `LEGAL["in-design"]` gains both with an epic-guard comment); the in-review PR gate accepts an epic whose `--pr`/meta carries the closure package; non-epics on these edges die with a clear message.

- [ ] **Step 1: Write the failing tests** — continue the recomposition section:

```bash
# Architect recomposition verdict paths (epic-guarded edges)
run board-transition.sh "$rc_e" in-design >/dev/null           # Architect claims
out="$(run board-transition.sh "$rc_e" done)"
assert_contains "$out" "#$rc_e: in-design → done" "recomposition Architect closes a non-code epic from in-design"
assert_equals "$(state "s['issues']['$rc_e']['stateReason']")" "COMPLETED" "epic closed as completed"
# a LEAF may never use the epic edges
run board-register.sh "Leaf in design" enhancement P2 --state ready-for-architect --body-file "$SPEC_BODY" >/dev/null
leaf_t="$(state "s['next']-1")"
run board-transition.sh "$leaf_t" in-design >/dev/null
assert_fails run board-transition.sh "$leaf_t" done
assert_fails run board-transition.sh "$leaf_t" in-review --pr "https://example.com/pkg"
# code-bearing epic routes in-review with the closure package as the pr slot
run board-register.sh "Code epic" enhancement P1 --body-file "$SPEC_BODY" >/dev/null
ce_e="$(state "s['next']-1")"
run board-register.sh "Code child" enhancement P2 --parent "$ce_e" --body-file "$SPEC_BODY" >/dev/null
ce_c="$(state "s['next']-1")"
run board-transition.sh "$ce_c" in-progress >/dev/null
run board-transition.sh "$ce_c" done >/dev/null                 # epic → ready-for-architect
run board-transition.sh "$ce_e" in-design >/dev/null
assert_fails run board-transition.sh "$ce_e" in-review          # package required
out="$(run board-transition.sh "$ce_e" in-review --pr "https://github.com/o/r/issues/$ce_e#closure-package")"
assert_contains "$out" "#$ce_e: in-design → in-review" "code-bearing epic enters scale review with the closure package"
out="$(run board-transition.sh "$ce_e" done)"
assert_contains "$out" "#$ce_e: in-review → done" "clean scale review closes the epic"
```

- [ ] **Step 2: Run to verify failure**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -15`
Expected: FAIL — `illegal transition: in-design → done`.

- [ ] **Step 3: Implement** — in `_board.py`, `LEGAL["in-design"]` becomes:

```python
    # in-design: the Architect's in-flight state. Exit = transition 2/3
    # (plan handoff / down-shortcircuit / decompose-epic) or a park.
    # done / in-review: EPIC-ONLY (E2 recomposition verdicts — the scoped
    # terminal-authority exception; board-transition enforces the guard).
    "in-design":             {"ready-for-implementer", "needs-info",
                              "needs-human", "interactive-preferred",
                              "wontfix", "deferred", "done", "in-review"},
```

In `board-transition.sh`, after the spike ban (line ~60), add:

```python
# E2 epic guard: the in-design → done / in-review edges exist ONLY for a
# recomposition claim on an epic (the scoped terminal-authority
# exception). A leaf Architect never closes or reviews its own ticket.
if cur == "in-design" and to in ("done", "in-review") \
        and tid not in B.epics(tickets):
    B.die("in-design → %s is the epic recomposition edge — #%s has no "
          "children; a leaf exits in-design via ready-for-implementer "
          "or a park" % (to, tid))
```

Update the in-review PR-gate comment (line ~118-123) to name the epic case — the existing check already passes when `--pr` is supplied, so only the comment changes:

```python
if to == "in-review" and not env["T_PR"] and not n.get("pr"):
    # A RETURN to in-review (the needs-human pre-park: E1 transition 7) never
    # re-supplies --pr — the ticket's board:meta already carries it from the
    # original entry. The invariant is "a ticket in in-review always has a
    # PR recorded", not "every entry carries the flag". For an EPIC the pr
    # slot carries the recomposition closure package (E2) — same invariant,
    # different artifact.
    B.die("a PR link is required when moving to in-review (--pr URL; for an "
          "epic: the closure-package URL)")
```

- [ ] **Step 4: Run to verify pass**

Run: `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/_board.py skills/issue-tracker/scripts/board-transition.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): epic-guarded recomposition verdict edges + closure-package gate"
```

---

### Task 4: Dispatch — parent-pin stamp and recomposition dispatch

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py:152-153` (`META_KEYS`)
- Modify: `skills/implementing/scripts/implement-dispatch.sh` (~line 278 area, beside the role-meta write)
- Test: `tests/implementing/test-implement-dispatch.sh`

**Interfaces:**
- Consumes: `_ticket_exports` (already evals `T_PARENT` if present — verify; if absent, add `q("T_PARENT", n.get("parent") or "")` beside the existing exports at line ~99), the role-meta write block at line ~278.
- Produces: `META_KEYS` gains `"parent-pin"`; after a successful spawn of a ticket WITH a parent, dispatch writes `parent-pin: #<parent> @ <git -C "$LOCAL_REPO" rev-parse HEAD>` into the child's board meta via a `gh issue edit --body` round-trip using `_board.py`'s `parse_meta`/`render_body` (mirror the platform's claim-record stamp). Failure is non-fatal (like the role-meta write). Epics in `ready-for-architect` already route `ARCHITECT` (state-based) — covered by a test, no dispatch code change.

- [ ] **Step 1: Write the failing tests** — in `tests/implementing/test-implement-dispatch.sh`, following its existing mock-board style:

```bash
# parent-pin: a child with a parent gets the dispatch-time contract stamp
# (fixture: ticket with parent set, dispatched once)
assert_contains "$(mock_issue_body "$CHILD_TICKET")" "parent-pin: #$PARENT_TICKET @ " \
  "dispatch stamps parent-pin (parent + repo HEAD sha) into the child meta"
# a parentless ticket gets no stamp
assert_not_contains "$(mock_issue_body "$LONE_TICKET")" "parent-pin:" \
  "no parent-pin on a parentless dispatch"
# a recomposition-ready epic dispatches on the ARCHITECT role
assert_contains "$SPAWN_LOG_CONTENT" "role=ARCHITECT" \
  "recomposition-ready epic in ready-for-architect dispatches an Architect"
```

Adapt fixture names to the harness's existing helpers (it has a mock gh and spawn log; reuse its current fixture-creation pattern — the file's existing tests show the exact helper names).

- [ ] **Step 2: Run to verify failure**

Run: `tests/implementing/test-implement-dispatch.sh 2>&1 | tail -10`
Expected: FAIL — no parent-pin in the body.

- [ ] **Step 3: Implement** — `_board.py` META_KEYS:

```python
META_KEYS = ("spawned-by", "relates-to", "branch", "pr", "plan", "pre-park",
             "parent-pin", "note")
```

In `implement-dispatch.sh`, in `dispatch_one` after the role-meta write block (`echo "dispatched #$n → ..."` vicinity), add:

```bash
  # E2 parent-pin: stamp the inherited-contract pin at DISPATCH time (the
  # parent's spec moves between cut and dispatch; the repo HEAD sha pins
  # what the child actually read). Non-fatal like the role-meta write.
  if [ -n "${T_PARENT:-}" ]; then
    pin_sha="$(git -C "$LOCAL_REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
    T_N="$n" T_PIN="#$T_PARENT @ $pin_sha" _py - <<'PY' \
      || echo "#$n: parent-pin meta write failed (non-fatal)" >&2
import os
import _board as B
env = os.environ
tid = env["T_N"]
body = B.gh(["issue", "view", tid, "-R", B.repo(), "--json", "body",
             "--jq", ".body"])
meta = B.parse_meta(body)
meta["parent-pin"] = env["T_PIN"]
B.gh(["issue", "edit", tid, "-R", B.repo(), "--body-file", "-"],
     input_text=B.render_body(body, meta))
PY
  fi
```

(If `_ticket_exports` doesn't already export `T_PARENT`, add `q("T_PARENT", n.get("parent") or "")` in its Python block. `_py` here must resolve the issue-tracker scripts dir on `PYTHONPATH` the same way the script's existing `_board`-importing blocks do — reuse the existing helper/pattern in this file; if it has none for `_board`, use `PYTHONPATH="$BOARD_SCRIPTS_DIR" python3` matching how `board-*.sh` callers do it.)

- [ ] **Step 4: Run to verify pass**

Run: `tests/implementing/test-implement-dispatch.sh 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/_board.py skills/implementing/scripts/implement-dispatch.sh tests/implementing/test-implement-dispatch.sh
git commit -m "feat(implement): dispatch stamps the parent-pin contract into child meta"
```

---

### Task 5: Scale-review dispatch — in-review epics without PRs

**Files:**
- Modify: `skills/reviewing-prs/scripts/review-dispatch.sh` (sweep section, line ~616-656)
- Test: `tests/reviewing-prs/test-review-dispatch.sh`

**Interfaces:**
- Consumes: the sweep's existing PR iteration, `dispatch_one`/`run_for`, board snapshot via `BOARD_SCRIPTS`.
- Produces: after the open-PR loop, the sweep also lists board tickets that are (a) epics, (b) `in-review`, (c) have a `pr:` meta (the closure package), (d) have no live bound reviewer — and dispatches a reviewer with `P_REVIEW_MODE=scale` in the prompt environment (the bootstrap template gains a `{{REVIEW_MODE}}` slot rendered as `pr` today and `scale` for epics; the scale prompt names the closure-package URL instead of a PR number). Dedupe/retire logic reuses the existing `_reviewer_meta`/`_retire` helpers keyed `review-epic-<n>`.

- [ ] **Step 1: Write the failing test** — in `tests/reviewing-prs/test-review-dispatch.sh`, following its mock pattern:

```bash
# E2 scale review: an in-review EPIC with a closure package and no PR gets
# a reviewer; a leaf in-review without a PR does not (PRs drive leaves).
# fixture: epic ticket in-review, pr: meta = closure package URL, children terminal
out="$(run_sweep)"
assert_contains "$out" "review-epic-$EPIC_TICKET" "sweep dispatches a scale reviewer onto the in-review epic"
assert_contains "$SPAWNED_PROMPT" "scale" "reviewer prompt carries the scale-review mode"
out2="$(run_sweep)"
assert_not_contains "$out2" "spawn" "second sweep dedupes the live epic reviewer"
```

Adapt helper names to the harness's existing mocks (spawn log + mock gh are already there; follow the file's existing dispatch test shape).

- [ ] **Step 2: Run to verify failure**

Run: `tests/reviewing-prs/test-review-dispatch.sh 2>&1 | tail -10`
Expected: FAIL — no epic dispatch line.

- [ ] **Step 3: Implement** — in the `--sweep` branch after the PR loop:

```bash
  # E2 scale review: recomposition epics enter in-review with a closure
  # package in the pr: meta and no GitHub PR — the PR loop above cannot
  # see them. List them off the board and dispatch the scale variant.
  epic_rows="$(PYTHONPATH="$BOARD_SCRIPTS" python3 - <<'PY'
import _board as B
tickets = B.snapshot()
eps = B.epics(tickets)
for tid in sorted(tickets, key=int):
    n = tickets[tid]
    if tid in eps and n["state"] == "in-review" and n.get("pr"):
        print("%s|%s" % (tid, n["pr"]))
PY
)" || epic_rows=""
  while IFS='|' read -r etid epkg; do
    [ -n "$etid" ] || continue
    dispatch_epic "$etid" "$epkg" || echo "epic #$etid: scale dispatch failed" >&2
  done <<EOF
$epic_rows
EOF
```

`dispatch_epic` mirrors `dispatch_one`'s spawn tail with: worker name `review-epic-<n>`, no PR checkout (worktree at the current base ref of the integration branch recorded on the epic's `branch:` meta, else the repo default branch), prompt rendered with `{{REVIEW_MODE}}=scale`, `{{CLOSURE_PACKAGE}}=<pkg url>`, `{{ISSUE_NUMBER}}=<etid>`; dedupe: skip when `_reviewer_meta review-epic-<n>` reports a live ACTIVE worker (reuse `_is_live`/`_retire` exactly as `dispatch_one` does). Add both template slots to the bootstrap heredoc with `pr`-mode defaults so leaf rendering is unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `tests/reviewing-prs/test-review-dispatch.sh 2>&1 | tail -5`; then the other `tests/reviewing-prs/*.sh` files.
Expected: PASS, existing tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add skills/reviewing-prs/scripts/review-dispatch.sh tests/reviewing-prs/test-review-dispatch.sh
git commit -m "feat(reviewing-prs): sweep dispatches scale review onto in-review recomposition epics"
```

---

### Task 6: Sweep `pass_impact` — parent-impact reconcile

**Files:**
- Modify: `skills/issue-tracker/scripts/board-sweep.sh` (new pass before `pass_land`, wired into the tail at line ~326-334)
- Test: `tests/issue-tracker/test-board-sweep.sh`

**Interfaces:**
- Consumes: `_bound_rows`-style board reads, `B.snapshot`, `B.apply_state(..., bookkeeping=True)`, mock gh comments.
- Produces: `pass_impact` — for every ACTIVE ticket with a parent, read its comments; a comment starting `[parent-impact]` that is NOT yet named by any `[board-epic] reconcile:` comment on the parent triggers: (1) parent returns to `ready-for-architect` (bookkeeping, note `reconciliation-due: [parent-impact] from #<child>`) unless the parent is already in `ready-for-architect` or `in-design`; (2) a `[board-epic] reconcile: #<child>@<comment-id>` comment on the parent (the dedupe marker — written even when the state write was skipped, so one proposal wakes one reconciliation).

- [ ] **Step 1: Write the failing test** — in `tests/issue-tracker/test-board-sweep.sh`, following its existing pass-test style:

```bash
# ---- IMPACT pass (E2 upward revision) -------------------------------------------
# fixture: epic in in-progress (pulled by active child); child posts [parent-impact]
mock_comment "$CHILD" "[parent-impact] #$EPIC acceptance-A3: discovered the queue contract cannot hold ordering"
run_sweep
assert_contains "$(issue_labels "$EPIC")" "status:ready-for-architect" "parent-impact proposal returns the parent for reconciliation"
assert_contains "$(last_comment "$EPIC")" "[board-epic] reconcile: #$CHILD@" "reconcile marker names the consumed proposal"
run_sweep
assert_equals "$(comment_count "$EPIC" '\[board-epic\] reconcile:')" "1" "a consumed proposal is not re-consumed"
```

Adapt helper names to the harness's existing mock helpers.

- [ ] **Step 2: Run to verify failure**

Run: `tests/issue-tracker/test-board-sweep.sh 2>&1 | tail -10`
Expected: FAIL — parent stays `in-progress`.

- [ ] **Step 3: Implement** — add before `pass_land`:

```bash
pass_impact() {
  # E2 upward revision: a child worker may not write its parent — it posts
  # a [parent-impact] comment on its OWN ticket, and this pass performs
  # the parent's reconciliation return (board bookkeeping). Dedupe is a
  # [board-epic] reconcile: marker on the parent naming child@comment-id.
  local acted=0
  PYTHONPATH="$BOARD_SCRIPTS_DIR" python3 - <<'PY' | tee -a "$SWEEP_LOG"
import json
import _board as B
tickets = B.snapshot()
for tid in sorted(tickets, key=int):
    n = tickets[tid]
    p = n.get("parent")
    if not p or p not in tickets or n["state"] not in B.ACTIVE:
        continue
    child_comments = json.loads(B.gh(
        ["issue", "view", tid, "-R", B.repo(), "--json", "comments"]
    )).get("comments") or []
    proposals = [(str(c.get("id") or ""), c.get("body") or "")
                 for c in child_comments
                 if (c.get("body") or "").lstrip().startswith("[parent-impact]")]
    if not proposals:
        continue
    parent_comments = json.loads(B.gh(
        ["issue", "view", p, "-R", B.repo(), "--json", "comments"]
    )).get("comments") or []
    seen = " ".join((c.get("body") or "") for c in parent_comments)
    for cid, _body in proposals:
        marker = "#%s@%s" % (tid, cid)
        if marker in seen:
            continue
        lines = []
        if tickets[p]["state"] not in ("ready-for-architect", "in-design"):
            lines.append(B.apply_state(
                tickets, p, "ready-for-architect",
                "reconciliation-due: [parent-impact] from #%s" % tid,
                bookkeeping=True))
        B.comment(p, "[board-epic] reconcile: %s" % marker)
        for ln in lines:
            print("[sweep] IMPACT: %s" % ln)
PY
  log "[sweep] IMPACT pass done"
}
```

Wire it into the tail between `pass_cancel` and the dispatch pass:

```bash
pass_impact   || log "[sweep] IMPACT pass errored (continuing)"
```

The spec's step 3 requires the reconciliation Architect to be DISPATCHED ("the dispatched Architect reconciles"), but Task 2's `recomposition_ready` gate blocks epic dispatch while children are active. So this task ALSO extends `eligible()`'s epic branch: a `reconciliation-due:` note is the second dispatchable epic condition. Replace `eligible()` in `_board.py` (final form, superseding Task 2's version):

```python
def eligible(tickets, tid):
    n = tickets[tid]
    if tid in epics(tickets):
        # E2 carve-out: dispatchable epic states are exactly
        # ready-for-architect awaiting recomposition (children all
        # terminal) or awaiting reconciliation (the sweep's
        # reconciliation-due return — children may still be active).
        if n["state"] != "ready-for-architect":
            return False
        if not recomposition_ready(tickets, tid) \
           and not (n.get("note") or "").startswith("reconciliation-due:"):
            return False
    elif n["state"] not in DISPATCHABLE:
        return False
    return all(tickets.get(b, {}).get("state") == "done" for b in n["blocked_by"])
```

Add a dispatch-eligibility assertion to the sweep test:

```bash
assert_contains "$(run_list_eligible)" "$EPIC" "reconciliation-due epic is dispatch-eligible even with active children"
```

(`run_list_eligible` = whatever the harness uses to probe `B.eligible`; if none exists, assert via `board-list.sh` ELIGIBLE tag output.)

- [ ] **Step 4: Run to verify pass**

Run: `tests/issue-tracker/test-board-sweep.sh 2>&1 | tail -5` and `tests/issue-tracker/test-board-scripts.sh 2>&1 | tail -3`
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/scripts/board-sweep.sh skills/issue-tracker/scripts/_board.py tests/issue-tracker/test-board-sweep.sh tests/issue-tracker/test-board-scripts.sh
git commit -m "feat(issue-tracker): sweep IMPACT pass — parent-impact proposals wake reconciliation"
```

---

### Task 7: Worker-protocol prose — Architect, Implementer, spike, QAgent

**Files:**
- Modify: `skills/architecting/SKILL.md` (Authority section ~line 121 + new Recomposition section)
- Modify: `skills/implementing/SKILL.md` (registration-authority vicinity)
- Modify: `skills/implementing/references/spike-worker-protocol.md`
- Modify: `skills/reviewing-prs/SKILL.md` (after the verdict section)
- Test: `tests/implementing/test-protocol-content.sh`, `tests/reviewing-prs/test-skill-entrypoint.sh` (if it pins prose; else protocol-content only)

**Interfaces:**
- Consumes: each protocol's existing Authority/registration language.
- Produces: four protocol additions, content-pinned by tests. Exact language blocks below — implementers adjust surrounding flow, not the normative sentences.

- [ ] **Step 1: Write the failing tests** — in `tests/implementing/test-protocol-content.sh`, following its assert style:

```bash
# E2 env-issue authority (all four worker protocols)
assert_file_contains skills/architecting/SKILL.md "env-issue" "architect protocol carries env-issue authority"
assert_file_contains skills/implementing/SKILL.md "env-issue" "implementer protocol carries env-issue authority"
assert_file_contains skills/implementing/references/spike-worker-protocol.md "env-issue" "spike protocol carries env-issue authority"
assert_file_contains skills/reviewing-prs/SKILL.md "env-issue" "review protocol carries env-issue authority"
assert_file_contains skills/implementing/SKILL.md "never park, transition, or otherwise interrupt" "env-issue filing is fire-and-continue"
# E2 recomposition protocol (Architect)
assert_file_contains skills/architecting/SKILL.md "recomposition" "architect protocol carries the recomposition claim"
assert_file_contains skills/architecting/SKILL.md "lineage" "recomposition includes the contract-lineage check"
# E2 scale-review variant (QAgent)
assert_file_contains skills/reviewing-prs/SKILL.md "scale review" "review protocol names the scale-review variant"
assert_file_contains skills/reviewing-prs/SKILL.md "corrective child" "scale review verdict set: close or corrective child"
```

(Use the harness's actual file-assert helper name; add one if absent, herestring-based.)

- [ ] **Step 2: Run to verify failure**

Run: `tests/implementing/test-protocol-content.sh 2>&1 | tail -10`
Expected: FAIL on every new assertion.

- [ ] **Step 3: Implement.** The shared env-issue block — add to each of the four protocols, adapted to each file's voice and placeholder conventions (Implementer/Architect use `{{ISSUE_NUMBER}}`):

```markdown
**Environmental friction (env-issue).** Non-blocking environmental
friction you routed around (missing tool in the image, flaky registry,
broken fixture) MAY be filed as its own ticket — search the board first,
then `board-register.sh "<title>" env-issue <P0..P3> --spawned-by
{{ISSUE_NUMBER}} --body-file <full report>`. State the friction, what
you attempted, why your permissions cannot resolve it, the intervention
requested, and a check that proves resolution. Default birth is
needs-human; pass an explicit --state only when you can name a concrete
repair path some authorized agent can execute. Filing is
fire-and-continue: never park, transition, or otherwise interrupt your
own ticket to report non-blocking friction — a genuinely blocking
failure stays what it is today, a park on your own ticket. This is
opt-in authority, not a duty; subagents never write the board.
```

Architect recomposition section (new, after the Authority section in `skills/architecting/SKILL.md`):

```markdown
## Recomposition claims

A dispatched ticket that is an EPIC is a recomposition (or
reconciliation) claim, not a design claim. Your deliverable is a
VERDICT against the epic's own acceptance — the whole-unit behavior,
not the sum of child acceptances.

1. **Lineage check first:** for every child, compare its `parent-pin:`
   meta (the parent revision it executed) against the parent's current
   revision; every material change is incorporated, explicitly
   irrelevant (say why), or becomes a corrective child. Consume any
   unconsumed `[parent-impact]` proposals the same way.
2. **Reconciliation-due claims** (children still active): reconcile the
   parent's living spec, flag affected in-flight children on their
   tickets, then exit in-design via a park return — the epic waits with
   its children; you do NOT close it.
3. **Recomposition-due claims** (all children terminal): verify the
   parent's acceptance. Non-code parent: record why no aggregate code
   review applies, then close with your verdict —
   `board-transition.sh <n> done "<evidence>"` (or wontfix). This is
   the scoped terminal-authority exception: epics only, recomposition
   claims only; you never close a leaf.
4. **Code-bearing integration parent** (two-plus children touched one
   executable surface, cross-child invariants, multi-repo composition,
   or the roadmap marks review required): assemble the closure package
   as a comment on the epic — parent acceptance, child closing
   artifacts, exact base/head ranges, cross-child contracts, your
   recomposition evidence — then
   `board-transition.sh <n> in-review "<summary>" --pr <package URL>`.
   The scale reviewer's clean verdict closes the epic; any defect
   becomes a corrective child and the epic waits again.
5. A change to the parent's PURPOSE, a material reduction of
   acceptance, or a product/taste call is the human's — park
   needs-human with the proposal and your recommendation.
```

QAgent scale-review variant (new subsection in `skills/reviewing-prs/SKILL.md`, after the verdict section):

```markdown
## Scale review (recomposition epics)

A `review-epic-<n>` dispatch is the E2 scale review: the ticket is an
EPIC in in-review whose `pr:` meta is a closure package, not a PR.
Same engine machinery — whole-range codex runs over the package's named
base/head ranges, lenses derived from the cross-child contracts — but a
different entry artifact and verdict set: there are no fix waves and no
merge step (the children are already merged; there is no branch to
fix). Verdicts: clean ⇒ `board-transition.sh <n> done "<summary>"`;
any defect ⇒ register a corrective child ticket
(`--parent <n> --spawned-by <n>`, full finding as the body) and
`board-transition.sh <n> ready-for-architect "scale review: corrective
child #<c>"` — the epic waits for the child and recomposes again. Audit
the closure package against the epic's acceptance the same way you
audit a PR against its ticket.
```

(Note the `in-review → ready-for-architect` edge is legal and convergence-counted — the QAgent's existing escalation edge. A corrective-child return is a REAL escalation, exactly what the counter should see; a second one converts to needs-human, which is correct: two failed recompositions deserve the human.)

- [ ] **Step 4: Run to verify pass**

Run: `tests/implementing/test-protocol-content.sh 2>&1 | tail -5`; also `tests/reviewing-prs/test-skill-entrypoint.sh 2>&1 | tail -3`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/architecting/SKILL.md skills/implementing/SKILL.md skills/implementing/references/spike-worker-protocol.md skills/reviewing-prs/SKILL.md tests/implementing/test-protocol-content.sh
git commit -m "docs(protocols): env-issue authority, recomposition claims, scale-review variant"
```

---

### Task 8: Doctrine prose — issue-tracker and decomposing skills

**Files:**
- Modify: `skills/issue-tracker/SKILL.md` (category list, writers, birth rules, markers, recomposition doctrine)
- Modify: `skills/decomposing/SKILL.md` (Recomposition section + new Upward Revision section)
- Test: `tests/implementing/test-protocol-content.sh` (or the cross-doc test if it pins these files)

**Interfaces:**
- Consumes: Task 1-7 vocabulary (exact marker strings, edge names).
- Produces: doctrine text matching the mechanics; content-pinned.

- [ ] **Step 1: Write the failing tests** — append:

```bash
assert_file_contains skills/issue-tracker/SKILL.md "env-issue" "board doctrine lists the env-issue category"
assert_file_contains skills/issue-tracker/SKILL.md "recomposition" "board doctrine carries the recomposition return"
assert_file_contains skills/issue-tracker/SKILL.md "\[board-epic\]" "board doctrine names the bookkeeping marker"
assert_file_contains skills/decomposing/SKILL.md "\[parent-impact\]" "decomposing doctrine names the proposal marker"
assert_file_contains skills/decomposing/SKILL.md "parent-pin" "decomposing doctrine names the dispatch-time pin"
```

- [ ] **Step 2: Run to verify failure**

Run: `tests/implementing/test-protocol-content.sh 2>&1 | tail -6`
Expected: FAIL on the new assertions.

- [ ] **Step 3: Implement.** `skills/issue-tracker/SKILL.md`: extend the category enumeration with `env-issue` and its birth rule (one paragraph, matching Task 1's register semantics); in the epic/lifecycle text, replace any auto-close description with:

```markdown
An epic whose children are all terminal is never closed by bookkeeping:
it RETURNS to `ready-for-architect` (`recomposition-due`) and an
Architect closes it by verification — directly for non-code parents,
via `in-review` with a closure package for code-bearing ones. Board
bookkeeping writes on epics (recomposition/reconciliation returns) post
`[board-epic]` comments — a marker the convergence counter deliberately
never reads. Epics are dispatchable ONLY in `ready-for-architect`
(awaiting recomposition, or a reconciliation-due return).
```

`skills/decomposing/SKILL.md`: extend the Recomposition section to name the board rendering (`ready-for-architect` return, Architect verdict, shape-gated scale review), and add after it:

```markdown
## Upward Revision

Children read the parent's current state at dispatch — the dispatch
machinery stamps `parent-pin:` (parent + repo revision) into the child
so "what contract did this child execute" is always answerable. A child
revises its own means freely; discovery that touches a parent-owned
end — purpose, acceptance, a cross-child contract, an edge, the
division itself — becomes a `[parent-impact]` comment on the child's
own ticket (evidence + affected clauses; the child never edits the
parent). The sweep returns the parent to `ready-for-architect`
(`reconciliation-due`); the reconciling Architect judges materiality,
updates the parent's living tail, and flags affected in-flight
children. Purpose changes and material acceptance reductions go to the
human. At final recomposition the Architect runs the lineage check:
every child's pin against the final parent revision — incorporated,
explicitly irrelevant, or a corrective child.
```

- [ ] **Step 4: Run to verify pass**

Run: `tests/implementing/test-protocol-content.sh 2>&1 | tail -3`; `tests/skill-links/test-cross-doc-refs.sh` if present.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/issue-tracker/SKILL.md skills/decomposing/SKILL.md tests/implementing/test-protocol-content.sh
git commit -m "docs(doctrine): recomposition lifecycle and upward revision in board + decomposing skills"
```

---

### Task 9: Final verification, version bump, spec living tail

**Files:**
- Modify: version manifests via `scripts/bump-version.sh 7.31.0` (never by hand)
- Modify: `docs/doperpowers/specs/2026-07-30-ticket-ledger-observability-design.md` (Revision Notes)

- [ ] **Step 1: Full suites**

Run, each from repo root, expecting PASS:

```bash
tests/issue-tracker/test-board-scripts.sh
tests/issue-tracker/test-board-sweep.sh
tests/implementing/test-implement-dispatch.sh
tests/implementing/test-protocol-content.sh
for t in tests/reviewing-prs/*.sh; do "$t"; done
tests/claude-code/run-skill-tests.sh
scripts/lint-shell.sh
```

- [ ] **Step 2: Spec acceptance — the E2-close criteria, executed as written**

Verify each against the test output above (the suites exercise them; name the covering assertion in the ledger):

1. Acceptance 1 (env-issue filing leaves the source ticket untouched) — Task 1's final assertion.
2. Acceptance 2 (zero new write duties; additions are opt-in) — Task 7's "opt-in authority" pins + no protocol test regressions.
3. Acceptance 3 (needs-human default vs named-repair-path birth) — Task 1's birth assertions.
4. Acceptance 4 (parent observed in `ready-for-architect`, closes only via recomposition, second cycle no convergence trip) — Task 2 + Task 3 assertions.
5. Acceptance 5 (`[parent-impact]` → reconciliation return + lineage pin) — Task 6 + Task 4 assertions.

Then run the residual greps:

```bash
grep -rn "close_epics" skills/ tests/        # expected: no hits in skills/; test hits only as retired-name lint if any
grep -rn "at least one is done" skills/      # expected: no hits (guard retired)
```

- [ ] **Step 3: Version bump + spec note**

```bash
scripts/bump-version.sh 7.31.0
```

Append to the spec's `## Revision Notes`:

```markdown
- 2026-08-01: interim slice implemented (v7.31.0, branch
  e2-ledger-contract): env-issue category + inverted birth; recompose
  replaces auto-close with the four mechanics amendments; parent-pin
  dispatch stamp; sweep IMPACT pass; scale-review dispatch; protocol
  and doctrine prose. E2-close acceptance 1-5 verified by the suite.
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: v7.31.0 — E2 interim slice complete"
```

---

## Plan Self-Review Notes (author-run)

- Spec coverage: every § Interim slice bullet maps to a task (env-issue → 1; recompose + mechanics → 2, 3; parent-pin → 4; scale review → 5; IMPACT pass → 6; protocols → 7; doctrine → 8; version/acceptance → 9). The feedback-triage exclusion is a non-change (documented in doctrine text only if the implementer finds existing prose claiming otherwise — none known).
- Spec drift found during planning, already reflected here: the spec's eligibility carve-out said "an epic in ready-for-architect is dispatchable" without the reconciliation-due case (children still active) — Task 6 extends eligibility to `reconciliation-due:` notes, which the spec's step-3 dispatch requirement implies. Record in the spec's Revision Notes at Task 9 if not already noted.
- Type consistency: marker strings (`[board-epic]`, `[parent-impact]`, `reconciliation-due:`, `recomposition-due:`), function names (`recompose_epics`, `recomposition_ready`), and meta key (`parent-pin`) are identical across Tasks 2, 4, 6, 7, 8.
