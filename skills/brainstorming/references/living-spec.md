# Living Specs

The design spec written at the end of doperpowers:brainstorming
(`docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md`) is not a snapshot of
an approval — it is the one document an initiative has, for the whole life
of its feature: the design with its reasoning, the acceptance, the
execution, and the record of what happened. Discoveries made while building
flow back into it, and the feature closes with a retrospective. Whoever
drives the session maintains it: brainstorming writes it, execution routes
discoveries into its record, finishing writes the retrospective.

The norms come from Codex's ExecPlan doctrine, PLANS.md. The sections that
bind are quoted below char-for-char — follow the quoted text, not a
paraphrase; details die in paraphrase. Where the source says "ExecPlan" or
"plan", read "spec". What is not quoted does not bind (see "What does NOT
bind" below); the full source stays at `archive/execplan/references/PLANS.md`,
and the reasons behind each rejection are in
`docs/doperpowers/specs/2026-07-03-living-specs-design.md` and the Decision
Log of `docs/doperpowers/specs/2026-09-12-one-spec-sized-by-the-gate-design.md`.

**The bar (recalibrated from PLANS.md's novice standard):** a fresh session
with no conversation history can pick up the spec and continue the work —
decisions, their whys, and everything learned so far included — and an
executor with nothing but this document and the code can build any one of
its milestones. Define terms of art; reference repo common knowledge instead
of duplicating it.

**What the document carries, and what it leaves out.** Intent, constraints,
decisions with their reasons, the interfaces between parts, and the
definition of done — everything the executor cannot derive from the code.
Not procedure: a paragraph that explains code the executor can read, a
step-by-step it can derive, a location it can find, is cut; a sentence that
says why is kept. The executor is a frontier model with the codebase in
view; it compiles design into implementation better and later than the
author can transcribe it.

## What binds

**Purpose and intent come first.**

> Purpose and intent come first. Begin by explaining, in a few sentences, why the work matters from a user's perspective: what someone can do after this change that they could not do before, and how to see it working. Then guide the reader through the exact steps to achieve that outcome, including what to edit, what to run, and what they should observe.

**Non-negotiables** (the two about a complete novice are recalibrated to the bar above; these three bind as written):

> * Every ExecPlan is a living document. Contributors are required to revise it as progress is made, as discoveries occur, and as design decisions are finalized. Each revision must remain fully self-contained.
> * Every ExecPlan must produce a demonstrably working behavior, not merely code changes to "meet a definition".
> * Every ExecPlan must define every term of art in plain language or do not use it.

**Self-containment and plain language.** An excerpt: the paragraph goes on to ask for repetition ("even if you repeat yourself"), which the bar above recalibrates; the rule itself binds:

> Self-containment and plain language are paramount. If you introduce a phrase that is not ordinary English ("daemon", "middleware", "RPC gateway", "filter graph"), define it immediately and remind the reader how it manifests in this repository (for example, by naming the files or commands where it appears).

**Avoid common failure modes.**

> Avoid common failure modes. Do not rely on undefined jargon. Do not describe "the letter of a feature" so narrowly that the resulting code compiles but does nothing meaningful. Do not outsource key decisions to the reader. When ambiguity exists, resolve it in the plan itself and explain why you chose that path. Err on the side of over-explaining user-visible effects and under-specifying incidental implementation details.

**Anchor the plan with observable outcomes.** This is the acceptance section's standard — a legitimate end-to-end check of the feature, not a summary of it:

> Anchor the plan with observable outcomes. State what the user can do after implementation, the commands to run, and the outputs they should see. Acceptance should be phrased as behavior a human can verify ("after starting the server, navigating to [http://localhost:8080/health](http://localhost:8080/health) returns HTTP 200 with body OK") rather than internal attributes ("added a HealthCheck struct"). If a change is internal, explain how its impact can still be demonstrated (for example, by running tests that fail before and pass after, and by showing a scenario that uses the new behavior).

**Specify repository context explicitly.**

> Specify repository context explicitly. Name files with full repository-relative paths, name functions and modules precisely, and describe where new files should be created. If touching multiple areas, include a short orientation paragraph that explains how those parts fit together so a novice can navigate confidently. When running commands, show the working directory and exact command line. When outcomes depend on environment, state the assumptions and provide alternatives when reasonable.

**Validation is not optional.**

> Validation is not optional. Include instructions to run tests, to start the system if applicable, and to observe it doing something useful. Describe comprehensive testing for any new features or capabilities. Include expected outputs and error messages so a novice can tell success from failure. Where possible, show how to prove that the change is effective beyond compilation (for example, through a small end-to-end scenario, a CLI invocation, or an HTTP request/response transcript). State the exact test commands appropriate to the project’s toolchain and how to interpret their results.

**Living plans and design decisions** — four of the five bullets, with the spec as the target document. The first bullet ("Record all decisions in the `Decision Log` section") is superseded by "Where reasoning lives" below: at authoring a decision is recorded in the section it shapes; the log is the dated record of what changed after.

> * ExecPlans must contain and maintain a `Progress` section, a `Surprises & Discoveries` section, a `Decision Log`, and an `Outcomes & Retrospective` section. These are not optional.
> * When you discover optimizer behavior, performance tradeoffs, unexpected bugs, or inverse/unapply semantics that shaped your approach, capture those observations in the `Surprises & Discoveries` section with short evidence snippets (test output is ideal).
> * If you change course mid-implementation, document why in the `Decision Log` and reflect the implications in `Progress`. Plans are guides for the next contributor as much as checklists for you.
> * At completion of a major task or the full plan, write an `Outcomes & Retrospective` entry summarizing what was achieved, what remains, and lessons learned.

**Prototyping milestones and parallel implementations.** When unknowns are large, the spec declares spike milestones (see "Spike milestones" below).

> It is acceptable—-and often encouraged—-to include explicit prototyping milestones when they de-risk a larger change. Examples: adding a low-level operator to a dependency to validate feasibility, or exploring two composition orders while measuring optimizer effects. Keep prototypes additive and testable. Clearly label the scope as “prototyping”; describe how to run and observe results; and state the criteria for promoting or discarding the prototype.
>
> Prefer additive code changes followed by subtractions that keep tests passing. Parallel implementations (e.g., keeping an adapter alongside an older path during migration) are fine when they reduce risk or enable tests to continue passing during a large migration. Describe how to validate both paths and how to retire one safely with tests. When working with multiple new libraries or feature areas, consider creating spikes that evaluate the feasibility of these features _independently_ of one another, proving that the external library performs as expected and implements the features we need in isolation.

## The execution section

Every spec carries its execution: `Progress`, placed right after the
purpose (it is the spec's ledger, kept current at every stopping point),
`Plan of Work` told as milestones, `Concrete Steps`, and
`Interfaces and Dependencies` when the work defines new interfaces — in
PLANS.md's skeleton wording:

    ## Progress

    Use a list with checkboxes to summarize granular steps. Every stopping point must be documented here, even if it requires splitting a partially completed task into two (“done” vs. “remaining”). This section must always reflect the actual current state of the work.

    - [x] (2025-10-01 13:00Z) Example completed step.
    - [ ] Example incomplete step.
    - [ ] Example partially completed step (completed: X; remaining: Y).

    Use timestamps to measure rates of progress.

    ## Plan of Work

    Describe, in prose, the sequence of edits and additions. For each edit, name the file and location (function, module) and what to insert or change. Keep it concrete and minimal.

    ## Concrete Steps

    State the exact commands to run and where to run them (working directory). When a command generates output, show a short expected transcript so the reader can compare. This section must be updated as work proceeds.

    ## Interfaces and Dependencies

    Be prescriptive. Name the libraries, modules, and services to use and why. Specify the types, traits/interfaces, and function signatures that must exist at the end of the milestone. Prefer stable names and paths such as `crate::module::function` or `package.submodule.Interface`. E.g.:

    In crates/foo/planner.rs, define:

        pub trait Planner {
            fn plan(&self, observed: &Observed) -> Vec<Action>;
        }

**Milestones** shape the Plan of Work:

> Milestones are narrative, not bureaucracy. If you break the work into milestones, introduce each with a brief paragraph that describes the scope, what will exist at the end of the milestone that did not exist before, the commands to run, and the acceptance you expect to observe. Keep it readable as a story: goal, work, result, proof. Progress and milestones are distinct: milestones tell the story, progress tracks granular work. Both must exist. Never abbreviate a milestone merely for the sake of brevity, do not leave out details that could be crucial to a future implementation.
>
> Each milestone must be independently verifiable and incrementally implement the overall goal of the execution plan.

**Sizing a milestone.** A milestone is the unit one executor owns from
this document and the code, and the unit reviewed at its boundary before
anything downstream consumes it. Every boundary costs a fresh worker's
orientation and a review; draw the fewest that keep these true: anything a
later milestone consumes is produced — and reviewed — before that milestone
starts, so keep producer and consumer together or put the interface at the
edge; one reviewer reads one milestone's diff in a single pass; one
milestone holds one verification strategy and closely related state. Setup,
scaffolding, configuration, and documentation fold into the milestone whose
deliverable needs them. Keep parts together when splitting would create an
invalid intermediate state, when they must land in the same cutover, or
when neither is meaningful or verifiable alone; split where state owners,
invariants, failure modes, or verification strategies differ
(doperpowers:decomposing's signals, applied inside one spec). For
concurrency-shaped work, fix the event list, the states, the transition
table, and the linearization points before implementation — a functional
description alone is how implicit distributed state machines get built one
ref at a time. Headings run `### M1 — <title>`, `### M2 — …`; the SDE brief
extractor reads them.

**What a milestone carries.** The constraints that bind every milestone —
version floors, dependency limits, naming and copy rules, platform
requirements, and for a child of a composite spec the binding inheritance
and cross-child contracts, each citing its id — open the section once, so a
reviewer's dispatch can copy them verbatim. Then each milestone:

- **What exists at its end** that did not before, as behavior someone can
  observe.
- **Files**, by repository path. No line ranges: they are stale by the time
  the milestone runs, and the executor finds the function itself.
- **Interfaces** it exposes to later milestones and consumes from earlier
  ones, by name and signature — a milestone's executor sees only its own
  text, and this is how it learns the names its neighbors use. The
  controller schedules reviews from these.
- **Decisions** the executor must not make differently: approach, error
  semantics, naming, ordering, what to reuse from the codebase (by path),
  the pitfalls seen in the code while designing, and the facts the code
  does not show — a deploy that follows `main` on its own, a service's real
  behavior. This slot is what carries the design's intent past the
  planner–coder gap; a constraint implicit in the requirements never
  reaches the executor unless it is written here.
- **What it does not touch.** State the scope's edge explicitly; a frontier
  executor widens scope where the edge is not drawn.
- **Proof**: the behaviors its tests assert, one line each, and the commands
  that show the milestone working with what to expect (Concrete Steps).
- **Code** only where the code is itself a decision — a data shape or
  schema, a public signature, a state or transition table, an algorithm
  whose subtlety is the point, an exact string, constant, or piece of copy,
  a test case that pins a contract. Code that only shows how to do what the
  Decisions already say is transcription: written blind here and stale by
  the time the milestone runs.

Not carried: commit messages, which test file or line to sit beside, exact
strings that are not decisions, steps. The executor writes those once, with
the real codebase in view, and runs its own test-first cycle.

**Spike milestones.** A prototyping milestone's deliverable is knowledge,
not shipped code: state the question it answers, what to build and how to
run it, what to observe, and the promote-or-discard criteria. It has no
tests; its proof is the recorded verdict, routed into `Surprises &
Discoveries` with the criteria applied — promote (a following milestone
hardens it with tests) or discard (delete the prototype; the knowledge
stays).

**The last milestone** executes the acceptance section as written — the
behavior-phrased checks with their exact commands and expected output —
in addition to the full test suite. Tests prove the parts; acceptance
proves the feature. Quote the commands so the executor needs nothing else.

**No placeholders.** A placeholder is a deferred decision: "TBD", "add
appropriate error handling" (name the errors and what happens on each),
"write tests for the above" (name the behaviors they assert), "as in M2"
(repeat the decision; the executor reads only its own milestone), a name no
milestone's Interfaces or Code defines. Complete means the decisions are
stated; a test named by the behavior it asserts is complete, and so is an
implementation described by its contract.

**When it is written.** After the design is approved, never before: in an
interactive session with the rest of the spec, once the presentation is
approved; on the board, after the approval park when the ticket carries
one. Writing it is the first hostile read of the design — a design
statement the milestones prove wrong is fixed in the design, with a dated
line in the Decision Log.

**While the spec is being executed**, PLANS.md's implementing rule binds,
with brainstorming's gate as the one stop: a fork under it that the spec
does not cover goes to your human partner; everything else is decided and
logged.

> When implementing an executable specification (ExecPlan), do not prompt the user for "next steps"; simply proceed to the next milestone. Keep all sections up to date, add or split entries in the list at every stopping point to affirmatively state the progress made and next steps. Resolve ambiguities autonomously, and commit frequently.

A spec with one milestone is worked directly by its executor; several run
through doperpowers:subagent-driven-execution — a fresh executor per
milestone, a review at each dependency frontier — under a
`doperpowers:plan-executor` subagent (doperpowers:brainstorming step 9).

**A child of a composite spec** cannot extend the composite — siblings on
parallel branches share it — so its execution section is a standalone file
under `docs/doperpowers/plans/`, headed by the composite's path, the child
id, and the parent pin. It carries the constraints and the milestones and
nothing of the design, which lives in the child's section; the SDE loop
reads it like any spec.

## Where reasoning lives

The design sections carry their own reasoning. Where a decision is made,
the section says why, and names the strongest alternative and why it lost —
a clause, not a ceremony; the alternatives were generated in the grill, so
capturing them there is free and stops re-proposals. That is the decision
record at authoring; no section restates it.

The record, after the body, in this order:

**`## Surprises & Discoveries`** — in PLANS.md's skeleton format:

    - Observation: …
      Evidence: …

For anything that changed design understanding: an assumption that proved
false, a measured behavior, a constraint discovered while building. One
observation and one evidence snippet — test output is ideal; a stop that
repaired the document is one line and its commit. Incidental implementation
noise belongs in commit messages, not here.

**`## Decision Log`** — dated, the record of what moved after the design
was written. It carries the verification call brainstorming makes when it
routes the work (which independent reviews the work gets and the branch
review rung — the one entry written at authoring, so the executor, the
reviewer, and a recovering session read the same council), every change of
course after approval, and a dated line for any revision that changed the
document without changing a decision. A course change, in PLANS.md's
skeleton format:

    - Decision: …
      Rationale: …
      Date/Author: …

with the alternative rejected then. When you change course, revise the
design sections to match — the document stays consistent as a whole — and
the log says what moved and why.

**`## Outcomes & Retrospective`** — until finish, exactly the line "Pending —
written at finish." At finish (after the whole-branch review), summarize
what was achieved against the spec's original purpose, what remains, and
lessons learned.

## What does NOT bind

Not quoted above, and superseded by doperpowers machinery: the single fenced
code block, prose-first, no-tables formatting (specs are files, not chat
payloads — use tables, JSON, or diagrams wherever they beat prose for
precision); novice-grade self-containment (the bar above); the Idempotence
and Recovery section (worktree isolation + git); Artifacts and Notes and
"capture evidence" inside the fence (the record's evidence snippets); "do
not prompt the user for next steps" at authoring time (the human gates —
design approval and spec review in doperpowers:brainstorming — come first;
the rule binds only during execution, as above); "Record all decisions in
the `Decision Log` section" and the separate bottom-note rule for
revisions (reasoning lives in the design; the log is the dated record of
change — measured on the reviewer-fold spec, a 340-line log restating a
630-line design, 2026-09-26). These rejections carry rationale — read the
Decision Logs in `docs/doperpowers/specs/2026-07-03-living-specs-design.md`
and `docs/doperpowers/specs/2026-09-12-one-spec-sized-by-the-gate-design.md`
before re-proposing one.

## Front of the spec

Untemplated on purpose: across this repo's existing specs no heading
structure repeats, and that variance is a feature — form fits problem
(state tables for state machines, JSON for schemas, prose for concepts).
Required: the purpose-first opening, Progress right after it, an acceptance
section phrased as observable behavior, the execution section, and the
record.
