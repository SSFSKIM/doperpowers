# Plan Resolution and the Document Tree — Design

The controlled track (doperpowers:brainstorming → spec → doperpowers:writing-plans
→ doperpowers:subagent-driven-execution) writes plans at a resolution calibrated
to a worker that no longer exists. writing-plans' overview still assumes an
engineer with "zero context … and questionable taste" and mandates complete
code in every step; the model text in subagent-driven-execution names opus at
high effort. The record shows what that mismatch costs (§6): a 5,715-line plan
that was 79% code, 63% of it surviving verbatim into the shipped tree — the
controller implemented the library in the plan and the executors transcribed
it — and a session where the fable controller's output (~630k tokens) was
roughly 2.7× all opus workers combined. Meanwhile the decomposing doctrine
tells every child to open "its own spec" citing the composite, which in
practice either never happens (Vitrea: nine children, no child specs, a
41-entry Decision Log in the parent) or produces 660–830-line child documents
under a 3,200-line parent before any plan exists (afleet).

After this lands one can observe: writing-plans sizes a task's text by the
decisions it carries, not by the code it could pre-write — a task is Files,
Interfaces, Deliverable, Tests, Decisions, and Code only where the code is a
decision; decomposing states that the document tree is the composite tree —
one spec per composite, none per leaf — and every child's artifact, not a
child spec, cites the parent; brainstorming knows how a child of a composite
enters and exits; the executor prompt says which code in a brief is a
decision and makes test-first the default for testable logic; and this spec
carries the baseline, the two wording micro-tests, and the monitoring
protocol that decides whether the change stands.

Human-confirmed frame (2026-09-04): scope = plan resolution + document tree
+ the child's path; elaboration = the whole plan at once (rolling
elaboration deferred); plan species = the controlled plan and the ExecPlan
stay two documents (merge deferred); a leaf's design lives in its section of
the composite, and a leaf whose design will not fit a section is a composite
in disguise; child documents = composite children (their own composite spec)
and spikes (findings) only; track = direct, with this spec as the durable
record, edits applied in-session, wording micro-tested before adoption, then
adopt-and-monitor. Task grain, review cadence, and reviewer depth (the 08-21
design) are untouched.

On the direct track this spec is the only record of the wording: §1–§4 quote
the skill-bound text verbatim; commentary sits outside the quotes.

## §1 Contract resolution (doperpowers:writing-plans)

**Overview** — the two premise paragraphs are replaced by:

> Write execution plans for an executor who is a skilled engineer, has never
> seen this codebase, and cannot see the design conversation that produced
> the spec. The plan carries what that engineer cannot derive from the code
> alone: which files each task touches, the interfaces between tasks, the
> behavior each task must exhibit and the tests that prove it, and every
> decision the design already settled. The executor writes the code and runs
> its own test-first cycle. DRY. YAGNI. TDD. Frequent commits.

**Task Right-Sizing** — the last sentence becomes:

> Inside a task, organize the work as sequential deliverables, each with its
> own tests and its own commit.

**"Bite-Sized Steps" is removed** and this section takes its place:

> ## Contract Resolution
>
> A task is a contract: the decisions the executor must not make
> differently, the interfaces it must honor, and the behavior that proves it
> done. The executor writes the code. Code belongs in a task only where the
> code is itself a decision — a data shape or schema, a public signature, a
> state or transition table, an algorithm whose subtlety is the point, an
> exact string, constant, or piece of copy, a test case that pins a
> contract. Code that only
> shows how to do what the Decisions already say is transcription: written
> blind here, copied there, and stale by the time a later task runs. The
> executor writes it once, with the real codebase in view.
>
> Every executor is a fresh context — a subagent, a daemon, a board
> Executor, a session resumed after compaction — and reads the contract with
> nothing left implicit. Only its escalation route differs.

**Spike Tasks** — the body becomes:

> If the spec declares a prototyping milestone (doperpowers:execspec), plan
> it as a spike task: the deliverable is knowledge, not shipped code. State
> the question the spike answers, what to build and how to run it, what to
> observe, and the spec's promote-or-discard criteria verbatim. A spike task
> has no Tests slot: its Deliverable is the recorded verdict — build, run,
> record — routed into the spec's `## Surprises & Discoveries` or
> `## Decision Log` with the criteria applied: promote (follow-up tasks
> harden it with tests) or discard (delete the prototype code; the knowledge
> stays in the spec).

**Final Verification Task** — "Quote the spec's commands verbatim in the
task's steps" becomes "Quote the spec's commands verbatim in the task".

**Plan Document Header** — the worker line, the Spec line, and Global
Constraints become:

> > **For agentic workers:** REQUIRED SUB-SKILL: Use
> > doperpowers:subagent-driven-execution to implement this plan
> > task-by-task. Deliverables use checkbox (`- [ ]`) syntax for tracking.
>
> **Spec:** [path to the spec this plan implements — the plan argues from
> the spec, so the spec travels with it; conflicts found during execution
> resolve against it. For a child of a composite spec: the composite's path,
> the child id, and the parent pin (the composite's commit — or the board's
> `parent-pin:` hash — as this child received it) — the child's section is
> its spec.]
>
> ## Global Constraints
>
> [The spec's project-wide requirements — version floors, dependency limits,
> naming and copy rules, platform requirements — one line each, with exact
> values copied verbatim from the spec. For a child of a composite spec, also
> the clauses of its binding design inheritance and cross-child contracts
> that bind these tasks, verbatim, each citing its id. Every task's
> requirements implicitly include this section.]

**Task Structure** — the template body is replaced by:

`````markdown
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
state table, a subtle algorithm, an exact string or piece of copy, a
test that pins a contract. Omit the slot otherwise.]

```python
class KernelRecord(TypedDict):
    key: str
    pid: int
    started_at: float
```

`````

**No Placeholders** — the section becomes:

> ## No Placeholders
>
> A placeholder is a deferred decision. These are **plan failures** — never
> write them:
> - "TBD", "TODO", "implement later", "fill in details"
> - "Add appropriate error handling" / "add validation" / "handle edge
>   cases" — name the errors and what happens on each
> - "Write tests for the above" — name the behaviors the tests assert
> - "Similar to Task N" — repeat the decision; the executor reads only their
>   own task
> - References to types, functions, or methods that no task's Interfaces or
>   Code defines
>
> Complete means the decisions are stated. A test named by the behavior it
> asserts is complete; an implementation described by its contract is
> complete; neither needs its code in the plan.

**Remember** — becomes:

> - Exact file paths always
> - Every decision stated; code only where the code is a decision
> - Exact commands with expected output
> - DRY, YAGNI, TDD, frequent commits

**Scope Check** — becomes:

> If the spec covers multiple independent subsystems, it should have been
> divided in doperpowers:decomposing. If it wasn't, suggest one plan per
> subsystem, each producing working, testable software on its own.

**Self-Review** item 3 becomes:

> **3. Interface consistency:** Do the names and signatures later tasks
> Consume match what earlier tasks Produce? A function produced as
> `clearLayers()` in Task 3 and consumed as `clearFullLayers()` in Task 7 is
> a bug.

and item 4 (Spec drift) gains a closing conditional:

> For a child of a composite spec that fix is yours only for advisory
> content; a wrong binding clause flows back as `[parent-impact]`
> (doperpowers:decomposing), and the plan carries the clause as it stands.

Unchanged, deliberately: the description, Conditional Sub-Slicing, File
Structure ("this is where decomposition decisions get locked in" — a
decision, so it stays), Task Right-Sizing's three criteria, the save path,
Self-Review items 1 and 2, and Execution Handoff including the codex plan
review.

## §2 The document tree (doperpowers:decomposing and its template)

**Overview** — after the sentence ending "recomposition closes it.", insert:

> The document tree is the composite tree: one spec per composite, none per
> leaf. A child's contract is its section here; what it adds are execution
> artifacts — its brief or plan, and the ledger that records its run — a
> spike's findings, or its own composite spec when it is a composite in
> turn.

**The Tree** — the NO NEW SUBSTRATE bullet becomes:

> - NO NEW SUBSTRATE: the tree is not a registry file. It IS the citation
>   chain (each child's artifact — brief, plan, ledger, PR body, ticket,
>   or a composite child's own spec — opens by citing its parent), the
>   board's typed edges, and the composite specs' tracking maps.

**The Pipeline**, step 7 — becomes:

> 7. **Dispatch and tend** — children go to their tracks per their track
>    hint, each carrying its section as pre-landed design and writing no
>    spec of its own: a brief child implements against its section and a
>    dispatch brief, a plan child grills only its residue
>    (doperpowers:brainstorming) and goes to doperpowers:writing-plans, a
>    spike writes findings, and a composite child runs this skill at its
>    own dispatch. Every child keeps a LEDGER: a plan child's record is its
>    committed plan and the doperpowers:subagent-driven-execution ledger; a
>    brief child opens `docs/doperpowers/ledgers/YYYY-MM-DD-<child-id>.md`
>    on its branch at dispatch — it cites this document (path + child id +
>    parent pin), carries the brief verbatim, and then Progress as
>    deliverables land, in-flight Decisions with their rationale, Surprises,
>    and the flow-back raised; its outcome section, written at close, is
>    the child's retrospective and the Tracking Map points at it. On a board
>    the ticket timeline and the PR body are that ledger. Residue rulings a
>    leaf makes land in this Decision Log under the child's id. As children
>    land, the tracking map, Decision Log, and Surprises stay current; when
>    the children are all in, close the parent by RECOMPOSITION — verify the
>    parent's own acceptance, then write the retrospective; the Deferred
>    section seeds the next cut.

**The Derivation Contract** — the last paragraph becomes:

> At dispatch, the child treats its section and its design inheritance as
> pre-landed grill input: it grills only the residue and never re-litigates
> landed decisions. Its section IS its spec. Design the child produces for
> itself expands that section in place; a leaf whose residue design trips
> the gate's split signals is a composite in disguise and gets its own
> composite spec instead. The child's artifacts — its brief or plan, its
> ledger, its PR or ticket — open by citing this composite spec (path +
> child id + parent pin); that citation is what keeps the flow-back channel
> alive when there is no board. Children read the parent document's *current* state at dispatch,
> never a frozen snapshot; when a Revision Note lands that touches an
> in-flight child's contract, flag that child. When a child's work
> contradicts the parent, the discovery flows back into the parent's
> Revision Notes — never silent divergence. This is the doperpowers:execspec
> discipline one level up.

**Common Mistakes** — a row is added after "Child quietly diverging from
the parent":

> | Writing a spec for a leaf child | Its section is its spec; its documents are its brief or plan and its ledger. A leaf whose residue trips the split signals is a composite in disguise — cut it. |
> | Authoring an ExecPlan for a child | An ExecPlan carries a design because it has no spec; a child has one — its section. The brief dispatches, the ledger records. |

**The Derivation Contract**, the Track hint line — the child vocabulary
is named by artifact, and `autonomous` leaves it:

> - **Track hint** — brief (the section plus a dispatch brief is the
>   whole contract; the board's DIRECT mode), plan (a
>   doperpowers:writing-plans plan at task grain; the board's
>   PLAN-EXECUTION), spike (deliverable is findings, never a merge), or
>   another decomposing run at dispatch. Every child's executor is a fresh
>   context — a subagent, a daemon, a board worker — so the hint names the
>   grain of the brief, never who runs it.

The template's child heading reads `[track hint: brief | plan | spike
(findings, never a merge) | decomposing]`.

**references/composite-spec-template.md** — in the header note, "Children
dispatch per their track hint; each child spec opens by citing this
document (path + child id) — except a child that landed before this cut: it
cannot cite forward, so the citation runs backward (its child section and
the Tracking Map point at its spec)." becomes:

> Children dispatch per their track hint, each carrying its section as its
> spec; each child's artifact (brief or plan, ledger, findings, PR, ticket
> — or a composite child's own composite spec) opens by citing this
> document (path + child id + parent pin) — except a child that landed before this
> cut: it cannot cite forward, so the citation runs backward (its child
> section and the Tracking Map point at its artifact).

and the Tracking Map body becomes:

> [child id → ledger (or ticket #), plus its plan / findings / composite
> spec where one exists, and status. This map plus the children's Status
> fields IS this unit's progress record — there is no separate Progress
> section. Keep it current as children land; a landed child's row carries
> its closing evidence and points at the ledger whose outcome section is
> the child's retrospective.]

## §3 The child's path (doperpowers:brainstorming)

**Understanding the idea** — a bullet is added after the scope-and-coupling
bullet:

> - A goal that arrives as a child of a composite spec
>   (doperpowers:decomposing) carries its section — purpose, acceptance,
>   edges, contracts, graded design inheritance — as pre-landed design.
>   Grill only the residue, against the code; record the residue's decisions
>   in the parent's Decision Log under the child's id; design you produce
>   expands the child's section in place, and a residue design that trips
>   doperpowers:decomposing's split signals means the child is a composite —
>   route it there. The composite's approval covers the section, so present
>   only the residue; the track hint is your recommendation, confirmed like
>   any track. The child writes no spec of its own: its section is its spec,
>   the hint names its exit (a plan child to doperpowers:writing-plans; a
>   brief child implements against its section and brief, keeping the
>   ledger doperpowers:decomposing describes), and the track's own review
>   covers the residue.

**The path**, steps 5 and 7 — each gains a trailing clause:

> 5. **Write design doc** — … save to
>    `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md` and commit (a
>    child of a composite spec expands its section in the composite instead)
> 7. **Independent spec review** — dispatch a spec reviewer subagent;
>    evaluate its findings, fix what survives (see below; a child of a
>    composite spec skips this — its track's own review covers the residue)

**After the Design › Documentation** — a line is added after the save-path
bullet:

> - A child of a composite spec writes no document of its own: expand its
>   section in the composite and commit that.

## §4 Cross-references

**doperpowers:execspec**, the superseded-directives table — the
writing-plans row becomes:

> | Milestones narrative, Concrete Steps, Interfaces and Dependencies | doperpowers:writing-plans, at contract resolution — decisions, interfaces, acceptance, exact commands; code only where it is a decision |

**doperpowers:subagent-driven-execution › executor-prompt.md** — "Your Job"
items 1–2 become:

> 1. Write the tests first (doperpowers:test-driven-development) for
>    testable logic — the brief names the behaviors they assert.
> 2. Implement what the task's Deliverables and Decisions specify.
>    Code blocks in the brief are decisions — honor them as written;
>    everything else is yours to write.

the report format's "**TDD Evidence** (if TDD was required for this
task)" becomes "**TDD Evidence** (for testable logic)", and the
self-review line "Did I follow TDD if required?" becomes "Did I write the
tests first for testable logic?".

**doperpowers:subagent-driven-execution › SKILL.md**, loop step 6 — the
living-tail routing gains the same conditional as writing-plans'
Self-Review 4:

> (doperpowers:execspec; for a child of a composite spec, advisory
> content in place and a binding contradiction as `[parent-impact]` per
> doperpowers:decomposing)

**doperpowers:finishing-a-development-branch**, Step 1's retrospective
sentence — a child must not overwrite the composite's Outcomes:

> For a child of a composite spec the entry is the outcome section of the
> child's ledger (a plan child's: its Tracking Map row) — closing evidence
> and artifact — and the composite's Outcomes waits for recomposition.

**scripts/sde-telemetry** — the role classifier learns the
initiative-prefixed description forms this session used ("Implement i2 Task
2: …", "Review i3 Task 5", "Run i3 Task 6 acceptance"), which it filed as
`other` (Surprises); the executor and reviewer patterns accept an optional
`i<n> ` before `task`. Monitoring depends on the classifier reading real
runs.

## §5 Unchanged, deliberately

- **doperpowers:architecting** — both artifact shapes stand; the plan an
  Architect writes for a stranger Executor is the "session that will never
  share your context" case §1 already names, and writing-plans defines its
  resolution.
- **doperpowers:executing** — PLAN-EXECUTION's "execute it to the letter"
  plus "absorb divergence" reads unchanged: the letter is the contract.
- **doperpowers:organizing-sprints** — already says a big epic derives its
  ExecPlan at dispatch from the umbrella spec; the same rule.
- **task-reviewer-prompt.md, scripts/task-brief, the ledger** — they key
  on task headings and the brief's requirements, which a contract still
  states.
- **doperpowers:execplan / PLANS.md** — the novice bar stays; it is the
  stranger case, and the merge of the two plan species is deferred.

## §6 Evidence

**Baseline (the record).** ptc-tool, session `96abe6e2`, 2026-08-20..22:
spec 2,402 lines; plan 5,715 lines, 28 tasks, 4,489 lines (79%) inside
fenced code; 1,440 of 2,289 plan code lines ≥25 chars (63%) present verbatim
in the shipped tree — core-library tasks 75–93%, integration and spike tasks
(T12, T17, T19, T22, T27) 17–31% (survival shows the code was used, not
that pre-writing it paid; the monitoring's fix-rate row is what settles
that); writing-plans invoked 11:37, SDE started
15:35; execution 2026-08-20 15:38 → 08-22 07:09, 20 of 28 tasks with
review-fix commits, three final-review rounds. ptc-tool, session `56c9ce21`,
2026-09-01 (the new grain, old resolution): three plans of 1,402 / 1,000 /
1,054 lines, each written and codex-reviewed in 15–25 minutes; executors
5–10 minutes per task; task-level fixes 1 of 16; fable controller output
629,666 tokens vs. opus workers ≈ 235k across all roles; each initiative
≈ 1.5 h end to end. designer (Vitrea), 2026-08-24..26: composite 623 lines,
no child specs or plans; C1 landed 27 minutes after dispatch, C4 (43-state
machine, 241 tests) in ≈ 1 h; v1 with 1,196 unit + 393 browser tests in
three days; the parent's Decision Log reached 41 entries with no child
editing it. afleet, 2026-09-03..04: composite 3,202 lines; "residue-only"
child specs of 663 and 834 lines before any plan.

**Micro-test A (writing-plans wording).** Spec:
`docs/doperpowers/specs/2026-08-20-client-agent-grade-reads-design.md`;
control: the shipped plan
`docs/doperpowers/plans/2026-08-20-client-agent-grade-reads.md` (806 lines,
67% in code blocks, 5 tasks). Five fresh opus reps write a plan for that
spec with the new `skills/writing-plans/SKILL.md` as their instructions,
and two opus reps write one under the old text as the same-model control.
Measured per rep: total lines, fenced-code share, task count, presence of
the Deliverables / Tests / Decisions slots, and a reviewer's placeholder
scan (deferred decisions found). Binding = reps converge on the slot shape;
the expectation recorded here (not in the skill): under 400 lines, code
share under a third, no deferred decisions.

**Micro-test B (child entry).** Five single-shot opus reps are dispatched
as the owner of a controlled leaf child of an existing composite spec (the
Vitrea composite, child C5, at its recorded pin) with the new brainstorming
and decomposing text as instructions and asked what they will produce
before code; five more with the current text as control. Pass = no rep
under the new text opens a child design document; the control's behavior
is recorded either way (the afleet session is the observed baseline
failure).

**Monitoring.** After each of the next three controlled-track features:
`scripts/sde-telemetry` over the session, plus plan lines, fenced-code
share (`awk '/^```/{f=!f;next} f{n++} END{print n"/"NR}' PLAN`), task
count, plan-authoring span (writing-plans invocation → `sde-workspace`),
and controller output tokens; appended as a row under Surprises. Reopen
when: two consecutive monitored features show final-review
Critical+Important above four; two consecutive features need a task-level
fix on more than one task in three; a task needs more than two fix rounds;
an executor reports BLOCKED or NEEDS_CONTEXT citing a decision the plan
should have carried. Prediction on record: plan lines down ≥5× against the 09-01
runs' 1,000–1,400 at comparable task counts, code share under a third,
executor span up modestly, fix rate and final-review defects within the
08-21 baseline.

## §7 Out of scope (recorded so they are not re-derived)

- **Rolling elaboration** (frontier tasks at brief resolution, later tasks
  as one-paragraph contracts elaborated at dispatch): the codex plan review
  should see the whole decomposition first, and the controller's dispatch
  message already carries the frontier delta. Reopen if staleness shows in
  the monitoring rows.
- **One plan species** (the controlled plan and the ExecPlan merged, with a
  fanned mode and a solo mode): a second step, so this change stays
  attributable and the diff bounded.
- **Parallel executors**: a separate design (08-21 §4); contract-resolution
  plans with an interface DAG are its prerequisite, not its substitute.
- **Reviewer depth**: the reviewer's call (08-21).

## Acceptance

- `grep -n "questionable taste\|Bite-Sized\|Complete code in every step\|task's steps" skills/writing-plans/SKILL.md` prints nothing; `grep -c "## Contract Resolution\|\*\*Deliverables:\*\*\|\*\*Decisions:\*\*\|A placeholder is a deferred decision" skills/writing-plans/SKILL.md` prints 4.
- `grep -c "brief | plan | spike" skills/decomposing/references/composite-spec-template.md` prints 1; `grep -c "ledgers/" skills/decomposing/SKILL.md` prints 1; `grep -c "ExecPlan" skills/decomposing/SKILL.md` prints 4 (The Gate's execution-mechanics examples and the Common Mistakes row that forbids one for a child).
- `grep -rn "child spec" skills/` prints nothing; `grep -n "composite tree" skills/decomposing/SKILL.md` and `grep -n "own composite spec" skills/decomposing/references/composite-spec-template.md` each print one line.
- `grep -c "child of a composite spec" skills/brainstorming/SKILL.md` prints 4 (the bullet, steps 5 and 7, the Documentation line).
- `grep -n "at contract resolution" skills/execspec/SKILL.md` prints the table row; `grep -n "Code blocks in the brief are decisions" skills/subagent-driven-execution/executor-prompt.md` prints one line; `grep -c "child of a composite spec" skills/finishing-a-development-branch/SKILL.md skills/subagent-driven-execution/SKILL.md skills/writing-plans/SKILL.md` prints 1, 1, and 3.
- `python3 scripts/sde-telemetry ~/.claude/projects/-Users-new-Developer-GitHub-ptc-tool/56c9ce21-0c8e-457a-b31f-a03de48651d3.jsonl | grep '^dispatches:'` shows executor=15 and task-reviewer=12 (the 09-01 forms classified; the two spike runs and the pre-09-01 dispatches stay `other`).
- Micro-test A: five reps, each with the Deliverables / Tests / Decisions slots present and a placeholder scan finding no deferred decision; lines and code share recorded under Surprises beside the two old-text controls.
- Micro-test B: zero of five new-text reps open a child design document; the five controls' behavior recorded under Surprises.
- `tests/executing/test-protocol-content.sh` and `tests/claude-code/test-sde-workspace.sh` pass (they read this tree; `run-skill-tests.sh` queries the installed plugin and does not exercise the edit).
- Version bumped via `scripts/bump-version.sh`; this spec committed with the edits.

## Decision Log

- Decision: plans at contract resolution — Files, Interfaces, Deliverables,
  Tests, Decisions, Code only where the code is a decision — over complete
  code in every step.
  Rationale: the 08-21 design deferred this with "frontier intelligence
  spent once, up front"; the 63% verbatim figure shows it is spent once by
  fable and again by opus transcribing and a reviewer reading; where the
  plan could not know the shapes (integration, spikes) 70–83% of its code
  was rewritten anyway. Vitrea's opus children built C4 from an 8-line
  section plus the design; the 09-01 executors ran at 5–10 minutes per
  task, transcription speed. Outside this repo, spec-kit's tasks are
  descriptions with file paths and parallel markers, Kiro's tasks are
  trackable outcomes on a dependency graph, and PLANS.md elaborates
  Concrete Steps as work proceeds; the full-code plan was the outlier.
  Rejected: brief-only with no plan document — the plan is the handoff to a
  stranger (board Executor, daemon, resume) and the anchor of the codex plan
  review, which produced blocking fixes on all three 09-01 plans, none
  about code lines.
  Date/Author: 2026-09-04 / fable session + human

- Decision: the whole plan is elaborated at once at contract resolution;
  rolling elaboration deferred.
  Rationale: the plan review sees the full decomposition; the controller's
  dispatch already carries the frontier delta; rolling would change
  task-brief extraction and the ledger in the same initiative.
  Date/Author: 2026-09-04 / human

- Decision: the controlled plan and the ExecPlan stay two documents; the
  merge into one plan species is a second step.
  Rationale: attribution and a bounded diff. The ExecPlan already has the
  contract shape (Plan of Work, Interfaces, Validation), so the merge is
  mechanical once resolution has landed.
  Date/Author: 2026-09-04 / human

- Decision: the document tree is the composite tree — one spec per
  composite, none per leaf; a leaf's design lives in its section; a leaf
  whose design will not fit a section is a composite in disguise.
  Rationale: Vitrea ran nine children and five correctives with no child
  specs and a 41-entry parent log; afleet's "thin" child specs were 663 and
  834 lines under a 3,202-line parent before any plan. The exception
  ("allow a design-bearing leaf spec") was rejected: it re-opens the afleet
  pattern, and a leaf that genuinely needs a spec fails the gate.
  Date/Author: 2026-09-04 / human

- Decision: a child writes a document of its own in two cases only — a
  composite child (its composite spec at its dispatch) and a spike
  (findings). Every other child's document is its execution artifact.
  Rationale: findings are the spike track's mandated deliverable; a
  composite child's cut needs a living tail of its own. A big-atomic
  controlled leaf writes its plan through writing-plans — that plan is its
  artifact, and its Spec line cites the section and the parent pin.
  Date/Author: 2026-09-04 / human

- Decision: residue decisions a leaf makes go to the parent's Decision Log
  under the child id; a leaf's retrospective is its tracking-map row plus
  its closing artifact.
  Rationale: no new substrate; Vitrea's flow-back rulings are the
  precedent. Rejected: a living tail on the plan document — a second
  living document per leaf.
  Date/Author: 2026-09-04 / fable session

- Decision: the executor prompt makes test-first the default for testable
  logic and names brief code blocks as decisions.
  Rationale: the plan no longer scripts the RED/GREEN steps, so the cycle
  must be the executor's; the direct track already binds
  test-driven-development for testable logic. Rejected: keep "if the task
  says to" — nothing would say so any more.
  Date/Author: 2026-09-04 / fable session

- Decision: "Bite-Sized Steps" removed; Contract Resolution takes its slot.
  Rationale: the section was about the executor's cycle, which the
  test-driven-development skill owns; leaving it would put step-scripting
  back in the plan.
  Date/Author: 2026-09-04 / fable session

- Decision: the skill text carries criteria, no line or code-share numbers;
  expected magnitudes live in §6.
  Rationale: carried from the 08-21 decision — numbers become gates.
  Date/Author: 2026-09-04 / fable session

- Decision: direct track with this spec as the durable record, edits
  applied in-session, wording micro-tested per doperpowers:writing-skills
  before adoption, then adopt-and-monitor with the collector.
  Rationale: the 08-21 precedent; roughly 300 lines of doctrine prose, a
  plan would be the diff itself. Rejected: controlled — the first
  contract-resolution plan would be written before the skill it
  exemplifies; paired double-run — the costliest evidence (08-21).
  Date/Author: 2026-09-04 / human

- Decision: independent spec review by a fable general-purpose subagent
  per brainstorming's routing (design-heavy spec); no critique debate
  unless that review disagrees with the design.
  Rationale: the design's prior art was checked outward (spec-kit, Kiro,
  PLANS.md); one independent pass is proportionate to a doctrine change.
  Date/Author: 2026-09-04 / fable session

- Decision: the 2026-07-21 goal-gated-decomposition spec's citation-chain
  wording ("child spec cites parent") is overturned here by entry, not
  edited there.
  Rationale: living specs record history; the current doctrine lives in the
  skills and this spec.
  Date/Author: 2026-09-04 / fable session

- Decision: architecting, executing, organizing-sprints, the task reviewer
  prompt, task-brief, and the ledger are unchanged (§5).
  Rationale: each was read against the new rule; none contradicts it.
  Date/Author: 2026-09-04 / fable session

- Decision: the telemetry classifier is fixed in this initiative.
  Rationale: the monitoring protocol reads real runs, and the 09-01 forms
  ("Implement i2 Task 2") were filed as `other`; a one-pattern fix.
  Date/Author: 2026-09-04 / fable session

- Decision: the independent spec review's surviving findings (review of
  2026-09-04, 18 findings, 17 adopted in some form): finishing writes a
  child's Tracking Map row instead of the composite's Outcomes;
  writing-plans' Self-Review 4 and SDE step 6 distinguish advisory (fix in
  place) from binding (`[parent-impact]`) for a child; `direct` joins the
  track-hint vocabulary; "will not fit a section" becomes "trips the
  gate's split signals" — the gate is the only law, and section size is
  taste; Global Constraints copies the binding clauses verbatim rather than
  by id; test-first is the executor's first step; the Tests slot carries
  expected output; commit messages ride the Deliverable checkboxes; the
  parent pin is defined once (commit, or the board's hash); Scope Check
  routes to decomposing; the micro-tests run five reps per variant with a
  same-model control; the monitoring gains a task-level fix-rate reopen;
  the live skill suite is dropped from acceptance because it reads the
  installed plugin.
  Rejected (design-bounded): grouping the parent's Decision Log under
  per-child headings to avoid merge conflicts between parallel children —
  the log stays chronological per PLANS.md; entries carry the child id, and
  the parent's owner lands flow-back from child reports as Vitrea did.
  Date/Author: 2026-09-04 / fable session (review findings adopted)

- Decision: "piece of copy" joins the code-as-decision list (Contract
  Resolution and the Code slot).
  Rationale: micro-test A — three of five new-text reps specified a
  SKILL.md rewrite by constraints ("replace the sentence with one route …
  one clause") and left the executor to author behavior-shaping prose; the
  same-model controls pinned it verbatim. Copy is an exact string.
  Date/Author: 2026-09-04 / fable session (micro-test refinement)

- Decision: a child's artifacts are one triple at two grains — contract
  (its section), dispatch (a brief, or a writing-plans plan for a
  big-atomic child), record (a ledger: the SDE ledger for a plan child, a
  committed `docs/doperpowers/ledgers/` document for a brief child that
  cites the composite, carries the brief verbatim, and whose outcome
  section is the child's retrospective). `autonomous` leaves the child
  hint vocabulary, which is named by artifact: brief | plan | spike |
  decomposing. Contract Resolution's "tended executor vs. stranger"
  framing is replaced by one bar: every executor is a fresh context.
  Rationale: the human's correction — a subagent spawned by the parent's
  owner and a daemon spawned elsewhere both read one initializing payload
  and report back; only the escalation route differs, which is not a
  reason for a different artifact. An ExecPlan earns its place only where
  there is no spec (it carries the design); a child's section is its spec,
  so an ExecPlan for a child restates it — Vitrea's "autonomous" children
  never wrote one. The ledger is what the ExecPlan's living tail provided
  and the brief lacked, and it closes Vitrea's one recorded cost
  (child-local reasoning surviving only in transcripts); the board's ticket
  timeline plus PR body already are that ledger, so the off-board document
  mirrors the on-board record. The standalone autonomous track keeps its
  ExecPlan for now — there it IS the spec — and this argument is why the
  deferred plan-species merge will work.
  Date/Author: 2026-09-04 / human + fable session

## Surprises & Discoveries

- Observation: plan writing is fast; the plan's cost is tokens and
  transcription, not calendar time. The three 09-01 plans took 6–14 minutes
  to write and 10–12 to review; the 5,715-line plan took under four hours
  including review; but the fable controller's output for the 09-01 session
  was 629,666 tokens against ≈ 235k for all opus workers.
  Evidence: `scripts/sde-telemetry` over session `56c9ce21`; the session's
  Skill / Write timestamps.
- Observation: the plan's code survived verbatim at 63% overall, 75–93% in
  core-library tasks and 17–31% in integration and spike tasks — the
  executors transcribed where the plan could know the shapes and rewrote
  where it could not.
  Evidence: line-set comparison of the 2026-08-20 ptc-kernel plan's fenced
  code (≥25-char lines) against the shipped tree, 2026-09-04.
- Observation: the telemetry classifier filed the 09-01 session's
  initiative-prefixed dispatches ("Implement i2 Task 2: peek runtime",
  "Review i3 Task 5") as `other` — 33 of 47.
  Evidence: the dispatch list in the same readout.
- Observation: at the new grain, task reviewers took 1.5–4 minutes per
  task (09-01) against 20–40 minutes in the August baseline's mutation
  batteries; whether that is the grain, the tasks, or the reviewer's
  judgment is not attributable from one session.
  Evidence: the same readout; 08-21 §3.
- Observation: "residue-only" child specs were not thin — 663 and 834
  lines — and the composite that spawned them already carried ≈ 350 lines
  of the corresponding design.
  Evidence: `afleet-c1` and `afleet-c2` spec line counts; the parent's §6.
- Observation (micro-test A, 2026-09-04): seven opus reps planned the
  same spec from a detached tree at its commit (`0f77ba69`, no shipped plan
  present). Every new-text rep carried the Deliverables / Tests /
  Decisions slots on every task and no step blocks; every old-text rep
  carried step blocks and none of the slots. Same-model reviewers found
  the same decision completeness on both sides.

  | Variant | Rep | Lines | Code | Tasks | Deferred | Placeholders | Gaps | Code blocks | Transcription |
  |---|---|---|---|---|---|---|---|---|---|
  | new | 1 | 686 | 5% | 4 | 3 | 0 | 2 | 6 | 0 |
  | new | 2 | 335 | 21% | 4 | 3 | 0 | 2 | 3 | 1 |
  | new | 3 | 783 | 9% | 5 | 3 | 0 | 2 | 11 | 0 |
  | new | 4 | 277 | 19% | 4 | 3 | 0 | 2 | 3 | 0 |
  | new | 5 | 310 | 13% | 4 | 3 | 0 | 2 | 8 | 2 |
  | old | 1 | 1380 | 65% | 4 | 2 | 0 | 1 | 37 | 17 |
  | old | 2 | 1242 | 62% | 5 | 3 | 0 | 2 | 36 | 16 |
  | shipped (fable) | — | 806 | 67% | 5 | — | — | — | — | — |

  Median lines 335 vs 1,311 (3.9× fewer against the same-model control,
  2.4× against the fable-authored shipped plan); code share 5–21% vs
  62–65%; the "under 400 lines" expectation held for three of five — the
  two long reps spent their lines in Tests (188–191) and Decisions
  (178–180) enumerations, not code. The deferred decisions the new-text
  reps left were the exact wording of user-facing prose (three reps), an
  either/or in test mechanics (one), and an unpinned edge case (two); the
  first class is now in the code-as-decision list. Old rep 1's two
  deferrals were the same prose class. One reviewer caught a vacuous
  anti-regression assertion in new rep 1 (a grep for a line-wrapped
  sentence) — a defect class the task reviewer's rubric already names.
  Evidence: `/tmp/micro-a/{new,old}/rep-*.md` (session-local), seven
  reviewer reports, this session.
- Observation (micro-test B, 2026-09-04): dispatched as the owner of the
  Vitrea composite's child C5 at its pin (`9d1ea36`) and asked what they
  would produce before code, five of five opus reps under the new
  brainstorming and decomposing text expanded the C5 section in place,
  wrote only an execution plan citing the composite path, child id, and
  pin, routed residue decisions to the parent's Decision Log under C5,
  advisory overturns to Revision Notes, and binding contradictions to
  `[parent-impact]`; five of five reps under the current text opened a
  standalone child design spec at `docs/doperpowers/specs/…c5…-design.md`
  with its own living tail before the plan. Two new-text reps volunteered
  the composite-in-disguise route unprompted.
  Run against the second revision's text (hints controlled | autonomous |
  direct); the fourth revision renamed the hints and added the ledger
  without touching the tested predicate.
  Evidence: ten single-shot reports, this session.

## Outcomes & Retrospective

Written 2026-09-04 at finish, before the monitoring window.

**Against the purpose.** writing-plans now sizes a task's text by the
decisions it carries: Files, Interfaces, Deliverables, Tests, Decisions,
and Code only where the code is a decision (a schema, a signature, a
state table, a subtle algorithm, an exact string or piece of copy, a
contract-pinning test). decomposing states that the document tree is the
composite tree; a child's artifact, not a child spec, cites the parent;
brainstorming knows how a child of a composite enters and exits;
finishing writes a child's tracking-map row rather than the composite's
Outcomes; the executor prompt puts test-first first and names brief code
as decisions; the telemetry classifier reads the initiative-prefixed
dispatch forms. The wording was checked before adoption: on the same spec
and the same worker model, five new-text plans and two old-text plans had
the same decision completeness (three deferred decisions, no placeholders,
two coverage gaps, against two to three, none, and one to two) at a median
of 335 lines against 1,311 and 5–21% code against 62–65%; on a real
composite child, five of five reps under the new text wrote no child spec
and five of five under the old text did.

**What remains.** The §6 monitoring rows for the next three controlled
features — the fix-rate and final-review columns are what decide whether
the change stands. The two deferred directions in §7: rolling
elaboration, and the merge of the controlled plan and the ExecPlan into
one plan species. The live skill suite (`run-skill-tests.sh`) reads the
installed plugin and cannot exercise a branch; a `--plugin-dir` shim is a
small separate fix.

**Lessons.** Verbatim survival measured that the plan's code was used,
not that pre-writing it paid; a same-model control plus reviewer scans of
deferred decisions was the measure that settled it, in under an hour.
The independent review's high findings were all integration seams —
finishing, Self-Review 4, the track-hint vocabulary — that reading the
edited skills alone did not surface: a doctrine change leaks at the
cross-skill conditionals, so review the skills that consume the changed
artifact, not only the ones that produce it. And a wording change whose
predicate is observable (a child of a composite spec) is testable with
single-shot reps in minutes; one whose product is a full artifact needs
the artifact written, about ten minutes a rep, and a reviewer to read it.

## Revision Notes

- 2026-09-04: initial spec from the design pass (this session's grill:
  four forks, all resolved to the recommendation), written after the
  baseline measurements above.
- 2026-09-04 (second revision): independent spec review folded — the
  finishing conditional, the advisory/binding conditional in Self-Review 4
  and SDE step 6, `direct` in the track-hint vocabulary, the split-signals
  wording, verbatim binding clauses in Global Constraints, executor order,
  Tests slot expected output, commit messages on Deliverables, five-rep
  micro-tests, fix-rate reopen, acceptance corrections.
- 2026-09-04 (third revision): micro-tests A and B run and recorded;
  "piece of copy" added to the code-as-decision list from A's deferred
  class; Outcomes & Retrospective written at finish.
- 2026-09-04 (fourth revision): the human's correction folded — no
  tended/unattended division (every executor is a fresh context), no
  ExecPlan for a child, hints named by artifact (brief | plan | spike |
  decomposing), and the per-child ledger as the third member of the
  contract / dispatch / record triple.
