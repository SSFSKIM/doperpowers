---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

## Overview

Write execution plans for an executor who is a skilled engineer, has never seen this codebase, and cannot see the design conversation that produced the spec. The plan carries what that engineer cannot derive from the code alone: which files each task touches, the interfaces between tasks, the behavior each task must exhibit and the tests that prove it, and every decision the design already settled. The executor writes the code and runs its own test-first cycle. DRY. YAGNI. TDD. Frequent commits.

**Announce at start:** "I'm using the writing-plans skill to create the execution plan."

**Context:** If working in an isolated worktree, it should have been created via the `doperpowers:using-git-worktrees` skill at execution time.

**Save plans to:** `docs/doperpowers/plans/YYYY-MM-DD-<feature-name>.md`
- (User preferences for plan location override this default)

## Scope Check

If the spec covers multiple independent subsystems, it should have been divided in doperpowers:decomposing. If it wasn't, suggest one plan per subsystem, each producing working, testable software on its own.

## Conditional Sub-Slicing

Consider sub-slicing when parts of the work have **different state owners,
invariants, failure modes, or verification strategies**. A good sub-slice
has an explicit input/output contract, its own focused behavior test, and
a review boundary a reviewer can approve without reading its neighbors.

Keep parts together when splitting would create an invalid intermediate
state, when they must land in the same transaction or cutover, or when
neither part is meaningful or verifiable alone.

When the slice is genuinely multi-unit — each part needing its own
file-structure and interface design — write it as multiple plans for the
one spec, rather than one plan straining to hold them all.

For concurrency-shaped work, the plan fixes the event list, states,
transition table, and linearization points before implementation — a
functional brief alone is how implicit distributed state machines get
built one ref at a time.

Sub-slicing is a judgment tool, not ceremony: the fewest boundaries that
make each important invariant independently understandable and testable.

The split/keep-together signals above are the universal division gate's
calibration list — doperpowers:decomposing owns the doctrine; this
section is that gate applied inside one plan. A goal too big for one
owner altogether belongs to that skill, not to sub-slicing.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Task Right-Sizing

A task is the unit one executor can reliably own from a single
self-contained brief, but it isn't the smallest unit a reviewer could
gate. Every task boundary costs a fresh worker's orientation (executor,
reviewer, and any fixer each read in from zero) plus your own
dispatch-and-adjudicate turn; draw the fewest boundaries that keep these
true:

- **Interface frontiers.** Anything a later task consumes must be
  produced — and reviewed — before that task dispatches: keep producer
  and consumer in one task, or put the contract at a task edge.
  Interfaces internal to a task are free.
- **Reviewable diff.** One reviewer reads one task's diff in a single
  pass.
- **Ownability.** One task holds one coherent verification strategy and
  closely related state owners; its brief needs nothing from neighbors
  beyond the declared Interfaces.

Fold setup, configuration, scaffolding, and documentation into the task
whose deliverable needs them. Inside a task, organize the work as
sequential deliverables, each with its own tests and its own commit.

## Contract Resolution

A task is a contract: the decisions the executor must not make
differently, the interfaces it must honor, and the behavior that proves it
done. The executor writes the code. Code belongs in a task only where the
code is itself a decision — a data shape or schema, a public signature, a
state or transition table, an algorithm whose subtlety is the point, an
exact string or constant, a test case that pins a contract. Code that only
shows how to do what the Decisions already say is transcription: written
blind here, copied there, and stale by the time a later task runs. The
executor writes it once, with the real codebase in view.

The same contract serves an executor you dispatch and tend and a session
that will never share your context — a board Executor, a daemon, a resume
after compaction. The second reads it with nothing left implicit; write
every task for the second.

## Spike Tasks

If the spec declares a prototyping milestone (doperpowers:execspec), plan it as a spike task: the deliverable is knowledge, not shipped code. State the question the spike answers, what to build and how to run it, what to observe, and the spec's promote-or-discard criteria verbatim. A spike task has no Tests slot: its Deliverable is the recorded verdict — build, run, record — routed into the spec's `## Surprises & Discoveries` or `## Decision Log` with the criteria applied: promote (follow-up tasks harden it with tests) or discard (delete the prototype code; the knowledge stays in the spec).

## Final Verification Task

End every plan with a verification task that executes the spec's acceptance section as written — the behavior-phrased checks with their exact commands and expected output — in addition to the full test suite. Tests prove the parts; the spec's acceptance proves the feature. Quote the spec's commands verbatim in the task so the executor needs no other context.

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-execution to implement this plan task-by-task. Deliverables use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

**Spec:** [path to the spec this plan implements — the plan argues from
the spec, so the spec travels with it; conflicts found during execution
resolve against it. For a child of a composite spec: the composite's path,
the child id, and the parent pin (the composite's commit — or the board's
`parent-pin:` hash — as this child received it) — the child's section is
its spec.]

## Global Constraints

[The spec's project-wide requirements — version floors, dependency limits,
naming and copy rules, platform requirements — one line each, with exact
values copied verbatim from the spec. For a child of a composite spec, also
the clauses of its binding design inheritance and cross-child contracts
that bind these tasks, verbatim, each citing its id. Every task's
requirements implicitly include this section.]

---
```

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Interfaces:**
- Consumes: [what this task uses from earlier tasks, naming the task —
  "from Task 2: `walk(cursor) -> list[dict]`" — exact signatures. The
  controller schedules reviews from these: a producer is reviewed before
  its consumer dispatches.]
- Produces: [what later tasks rely on — exact function names, parameter
  and return types. A task's executor sees only their own task; this
  block is how they learn the names and types neighboring tasks use.]

**Deliverables:**
- [ ] [what exists when this deliverable lands, as behavior someone can
  observe — "`ptc kernels` lists a spawned kernel with its pid and prints
  nothing for a session that has none" — one checkbox per deliverable,
  each ending with its commit message: `feat: list kernels`]

**Tests:** [the behaviors the tests assert, one line each, with the test
file and the command that runs them — "`test_spawn_refuses_second_owner`
in `tests/test_kernel.py`: a second spawn under the same key exits 2
without touching the run-file; run `pytest tests/test_kernel.py -v`,
expect `1 passed`".]

**Decisions:** [every call the executor must not make differently —
approach, error semantics, naming, ordering, what to reuse from the
codebase (by path), the pitfalls you saw in the code — one line each.]

**Code:** [only where the code is a decision: a schema, a signature, a
state table, a subtle algorithm, an exact string, a test that pins a
contract. Omit the slot otherwise.]

```python
class KernelRecord(TypedDict):
    key: str
    pid: int
    started_at: float
```

````

## No Placeholders

A placeholder is a deferred decision. These are **plan failures** — never
write them:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge
  cases" — name the errors and what happens on each
- "Write tests for the above" — name the behaviors the tests assert
- "Similar to Task N" — repeat the decision; the executor reads only their
  own task
- References to types, functions, or methods that no task's Interfaces or
  Code defines

Complete means the decisions are stated. A test named by the behavior it
asserts is complete; an implementation described by its contract is
complete; neither needs its code in the plan.

## Remember
- Exact file paths always
- Every decision stated; code only where the code is a decision
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits

## Self-Review

After writing the complete plan, look at the spec with fresh eyes and check the plan against it. This is a checklist you run yourself — not a subagent dispatch.

**1. Spec coverage:** Skim each section/requirement in the spec. Can you point to a task that implements it? List any gaps.

**2. Placeholder scan:** Search your plan for red flags — any of the patterns from the "No Placeholders" section above. Fix them.

**3. Interface consistency:** Do the names and signatures later tasks Consume match what earlier tasks Produce? A function produced as `clearLayers()` in Task 3 and consumed as `clearFullLayers()` in Task 7 is a bug.

**4. Spec drift:** Planning is the first hostile read of the spec. If planning revealed a spec statement that is wrong — an argument that is actually an output, an infeasible constraint, a misnamed path — fix the spec now and add a line to its `## Revision Notes` (see doperpowers:execspec). Never let the plan silently diverge from the spec. For a child of a composite spec that fix is yours only for advisory content; a wrong binding clause flows back as `[parent-impact]` (doperpowers:decomposing), and the plan carries the clause as it stands.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.

## Execution Handoff

After saving the plan, report the path ("Plan complete and saved to `docs/doperpowers/plans/<filename>.md`"), then run the plan review on the Codex side — doperpowers:codex-companion's `adversarial-review` verb (model `gpt-5.6-sol`, effort `xhigh` via its with-effort wrapper), in a background Bash, with the focus text:

> Review the execution plan at [PLAN_FILE_PATH] against its spec at [SPEC_FILE_PATH]. Verify the implementation architecture is sound and the plan is complete, spec-aligned, well-decomposed, and buildable by an engineer with zero context.

Evaluate its findings rather than accepting them wholesale; fix what survives.

Then execute:
- **REQUIRED SUB-SKILL:** Use doperpowers:subagent-driven-execution
- Fresh executor per task; reviews at dependency frontiers; fixes resume the executor
