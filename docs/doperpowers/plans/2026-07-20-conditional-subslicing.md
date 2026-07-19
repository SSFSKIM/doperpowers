# Conditional Sub-Slicing Doctrine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the two halves of the conditional sub-slicing doctrine — the planning-time note in writing-plans and the run-time escalation signal in subagent-driven-development — and validate both with the spec's pressure scenarios.

**Architecture:** Two markdown section insertions into existing skill files (no structural changes to either skill), then behavior validation via fresh-context subagent scenarios per the spec's acceptance section.

**Tech Stack:** Markdown skill content; Agent-tool subagent dispatches for validation; repo test suite `tests/claude-code/run-skill-tests.sh`.

**Spec:** `docs/doperpowers/specs/2026-07-19-conditional-subslicing-design.md`

## Global Constraints

- The two doctrine texts land as written in the spec's Design section (final polish of phrasing allowed; no change in substance).
- Soft doctrine only — no numeric thresholds ("≥3 units → split" is a plan failure), per spec Decision 4.
- Task-groups-in-one-plan stays the default rung of the expression ladder, per spec Decision 2.
- Do NOT add any cross-reference to `doperpowers:roadmapping` yet — that sentence lands with the roadmapping slice (human's sequencing order).
- No other content in either skill file is modified.

---

### Task 1: Conditional Sub-Slicing section in writing-plans

**Files:**
- Modify: `skills/writing-plans/SKILL.md` (insert new section between "## Scope Check" and "## File Structure")

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the section title `## Conditional Sub-Slicing` and the phrase "escalation signal in doperpowers:subagent-driven-development", which Task 2's section must match (title `## Escalation Signal: Repeated Findings at One Seam`, back-reference `Conditional Sub-Slicing in doperpowers:writing-plans`).

- [ ] **Step 1: Insert the section**

In `skills/writing-plans/SKILL.md`, the Scope Check section currently ends with the line `If the spec covers multiple independent subsystems, ... Each plan should produce working, testable software on its own.` followed by `## File Structure`. Insert between them:

```markdown
## Conditional Sub-Slicing

Default to the smallest cohesive plan that delivers the spec's end-to-end
invariant. Never split merely because the work touches many files or
crosses technical layers — file count is not a boundary.

Consider sub-slicing when parts of the work have **different state owners,
invariants, failure modes, or verification strategies** — e.g. a database
transaction contract, a pure domain state machine, and async UI
coordination are three units, not one. A good sub-slice has an explicit
input/output contract, its own focused behavior test, and a review
boundary a reviewer can approve without reading its neighbors.

Keep parts together when splitting would create an invalid intermediate
state, when they must land in the same transaction or cutover, or when
neither part is meaningful or verifiable alone.

Expression ladder — use the lightest rung that fits:

1. **Task groups within this plan** (default) — one group per state
   owner; each group gets its own implement→review cycle before the next
   begins.
2. **Multiple plans for one spec** — when the slice is genuinely
   multi-unit and each group would need its own file-structure and
   interface design.
3. **Mid-flight promotion** — when implementation reveals a runaway area
   (see the escalation signal in doperpowers:subagent-driven-development),
   promote it to its own sub-spec/plan referenced from the parent, rather
   than patching on.

For concurrency-shaped work, the plan fixes the event list, states,
transition table, and linearization points before implementation — a
functional brief alone is how implicit distributed state machines get
built one ref at a time.

Sub-slicing is a judgment tool, not ceremony: the fewest boundaries that
make each important invariant independently understandable and testable.
```

- [ ] **Step 2: Verify the insertion**

Run: `grep -n "## Conditional Sub-Slicing" skills/writing-plans/SKILL.md && grep -n "## Scope Check\|## File Structure" skills/writing-plans/SKILL.md`
Expected: `Conditional Sub-Slicing` appears at a line number between `Scope Check` and `File Structure`.

- [ ] **Step 3: Commit**

```bash
git add skills/writing-plans/SKILL.md
git commit -m "feat(writing-plans): conditional sub-slicing — split on invariants, never on file count"
```

### Task 2: Escalation Signal section in subagent-driven-development

**Files:**
- Modify: `skills/subagent-driven-development/SKILL.md` (insert new section between "## Handling Reviewer ⚠️ Items" and "## Constructing Reviewer Prompts")

**Interfaces:**
- Consumes: Task 1's section title (`Conditional Sub-Slicing` in doperpowers:writing-plans) — the back-reference below must match it exactly.
- Produces: section title `## Escalation Signal: Repeated Findings at One Seam` (referenced by Task 1's rung 3 as "the escalation signal in doperpowers:subagent-driven-development").

- [ ] **Step 1: Insert the section**

In `skills/subagent-driven-development/SKILL.md`, the "Handling Reviewer ⚠️ Items" section ends with `...treat it as a failed spec review — send it back to the implementer and re-review.` followed by `## Constructing Reviewer Prompts`. Insert between them:

```markdown
## Escalation Signal: Repeated Findings at One Seam

If review keeps surfacing new Important findings in the same area — and
each fix adds another flag, ref, or condition — stop the patch loop. That
is a structure signal, not an implementation-quality signal: reassess
state ownership and decomposition per Conditional Sub-Slicing in
doperpowers:writing-plans, and consider promoting the area to its own
sub-spec/plan before dispatching the next task.
```

- [ ] **Step 2: Verify the insertion and the cross-reference pair**

Run: `grep -n "Escalation Signal" skills/subagent-driven-development/SKILL.md skills/writing-plans/SKILL.md && grep -n "Conditional Sub-Slicing" skills/writing-plans/SKILL.md skills/subagent-driven-development/SKILL.md`
Expected: both files hit on both greps — each section names the other.

- [ ] **Step 3: Commit**

```bash
git add skills/subagent-driven-development/SKILL.md
git commit -m "feat(subagent-driven-development): repeated findings at one seam is a structure signal"
```

### Task 3: Final verification — spec acceptance pressure scenarios + repo tests

**Files:**
- Modify: `docs/doperpowers/specs/2026-07-19-conditional-subslicing-design.md` (record results in `## Outcomes & Retrospective`)

**Interfaces:**
- Consumes: both inserted sections (Tasks 1-2) at their repo paths.

All three scenarios dispatch a FRESH subagent (Agent tool, model `sonnet`, no session history) whose prompt includes the repo-absolute skill path — the subagent must read the MODIFIED repo file, not any plugin-cache copy. Mid-tier is deliberate: if sonnet-with-the-text behaves correctly, the text is doing the work.

- [ ] **Step 1: Scenario A — Task-8-shaped brief must produce state-owner task groups**

Dispatch a subagent with exactly this prompt:

> Read /Users/new/Developer/GitHub/doperpowers/skills/writing-plans/SKILL.md and follow it. You are planning implementation for this approved mini-spec; produce ONLY the plan's task outline (task/group titles + one-line deliverable each), not full steps.
>
> Mini-spec: "Timetable replacement and /today integrity." (i) Replace a student's academy timetable atomically in PostgreSQL via a single RPC — transaction boundary, lock ordering, service-role ACL. (ii) Server-side daily-plan cache consistency: detect when cached task rows were read against a stale base plan (reads span multiple queries), and recover safely. (iii) React /today client refresh coordination: post-hydration GET, invalidation of in-flight responses when a mutation lands, out-of-order response handling, reconciliation of tasks whose end time passed mid-request.
>
> Return the outline and one paragraph explaining your decomposition choice.

PASS: the outline groups work along the three state-ownership boundaries (atomic DB writer / cache-recovery consistency / client refresh coordination) — as task groups or clearly bounded task clusters — rather than one flat list or a split by technical layer (SQL vs TypeScript vs React). The explanation references invariants/state ownership, not file count.

- [ ] **Step 2: Scenario B — PR2-shaped brief must stay cohesive**

Dispatch a subagent with exactly this prompt:

> Read /Users/new/Developer/GitHub/doperpowers/skills/writing-plans/SKILL.md and follow it. You are planning implementation for this approved mini-spec. First decide: ONE implementation plan or SEVERAL? Answer with your decision, its justification, and a task outline.
>
> Mini-spec: "Auto-adjust proposalization." (i) Add a proposal lifecycle kind plus an RPC resolver so auto-adjustments become proposals. (ii) Change the rule producer to emit proposals instead of writing schedules directly. (iii) Change the generation consumer to apply approved proposal parameters. All three share one product invariant: only approved proposals may mutate the authoritative schedule, enforced at a single rollout gate — a partial landing would create proposals that approve to nothing, or producers that bypass the approval boundary.

PASS: decides ONE plan (internal tasks fine); justification cites the shared invariant / invalid intermediate states. FAIL: proposes separate plans/PRs per technical area.

- [ ] **Step 3: Scenario C — repeated-findings transcript must trigger reassessment, not a third patch**

Dispatch a subagent with exactly this prompt:

> Read /Users/new/Developer/GitHub/doperpowers/skills/subagent-driven-development/SKILL.md. You are the controller mid-execution. History on the current task ("client refresh wiring"): Review round 1 found an Important — a stale response overwrites state after a mutation; fixed by adding a mutation-epoch ref. Round 2, on the fixed code, found an Important — overlapping mutations break the epoch; fixed by adding an active-mutation counter ref. Round 3 has just found an Important — a reconciliation refresh consumes the pending recovery during an active mutation. The fix subagent proposes adding a pending-recovery boolean ref. As controller, what do you do next? Answer concretely.

PASS: declines to dispatch the third patch as-is; names the repeated-findings-at-one-seam signal; proposes reassessing state ownership/decomposition (e.g. extracting a coordinator state machine, promotion to a sub-spec/plan). FAIL: approves the pending-recovery ref patch and moves on.

- [ ] **Step 4: Run the repo test suite**

Run: `tests/claude-code/run-skill-tests.sh`
Expected: exit 0, no failures (no test pins the modified skill content; if one does, fix the pin, not the doctrine).

- [ ] **Step 5: Record results in the spec and commit**

In `docs/doperpowers/specs/2026-07-19-conditional-subslicing-design.md`, replace the `## Outcomes & Retrospective` body with a dated record: each scenario's verdict (PASS/FAIL) with one line of verbatim evidence from the subagent's answer, plus the test-suite result. If any scenario FAILED: fix the doctrine wording, re-run that scenario, and record both rounds. Then:

```bash
git add docs/doperpowers/specs/2026-07-19-conditional-subslicing-design.md
git commit -m "docs(specs): conditional sub-slicing acceptance results"
```
