# Living Specs

The design spec doperpowers:execspec writes
(`docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md`), from the design
doperpowers:brainstorming closed and your human partner approved, is not a
snapshot of an approval — it is the one document an initiative has, for the
whole life of its feature: the design with its reasoning, the acceptance,
the execution, and where the work stands. At every moment it states the
design as it stands now: what is learned while building is written into
the section it bears on, and the feature closes with a retrospective. Its
history is git. Whoever drives the session maintains it: execspec writes
it, execution keeps it true, finishing writes the retrospective.

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
decisions, their whys, and what was learned that bears on them included — and an
executor with nothing but this document and the code can build any one of
its milestones. Define terms of art; reference repo common knowledge instead
of duplicating it.

**What the document carries, and what it leaves out.** Intent, constraints,
the decisions whose wrong answer is costly — each with its reason, so a gap
can be resolved in its spirit — the interfaces between parts, and the
definition of done — everything the executor cannot derive from the code.
Not procedure: a paragraph that explains code the executor can read, a
step-by-step it can derive, a location it can find, is cut; a sentence that
says why is kept. The executor is a frontier model with the codebase in
view; it compiles design into implementation better and later than the
author can transcribe it, and design time cannot foresee every gap — a spec
that tries to pre-decide everything grows long, goes stale against the
code, and boxes in a worker who will see more than its author did. Say each
thing once, in the section that owns it; every other section points to it.

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

**The retrospective.** Of PLANS.md's five bullets on living plans this one
binds as written; `Progress` binds through the execution section below, and
the rest are replaced by "Keeping the spec current":

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
ref at a time. Headings run `### M1 — <title>`, `### M2 — …`; the execution
loop and plan-executor find milestones by them.

**What a milestone carries.** Every executor reads the whole spec, so a
milestone entry restates nothing the spec already says — it points. The
section opens with the verification — which independent reviews the spec
gets and the rung of the branch review, named at authoring so the executor,
the reviewer, and a recovering session read the same council — and then the
constraints that bind every milestone — version floors, dependency limits,
naming and copy rules, platform requirements, and for a child of a
composite spec the binding inheritance and cross-child contracts, each
citing its id — open the section once. Then each milestone:

- **What exists at its end** that did not before, as behavior someone can
  observe.
- **What it touches**: the areas or files where the work lives, by
  repository path. No line ranges: they are stale by the time the
  milestone runs, and the executor finds the function itself.
- **Interfaces** it exposes to later milestones and consumes from earlier
  ones, by name — defined once, in Interfaces and Dependencies. The
  controller schedules reviews from these.
- **Decisions** that belong to this milestone alone and nowhere else in
  the design: approach, error semantics, naming, ordering, what to reuse
  from the codebase (by path), the pitfalls seen in the code while
  designing, and the facts the code does not show — a deploy that follows
  `main` on its own, a service's real behavior. A decision the design
  already carries is pointed at, not repeated. This slot and the design
  are what carry intent past the planner–coder gap; a constraint implicit
  in the requirements never reaches the executor unless it is written
  somewhere in the spec.
- **What it does not touch.** State the scope's edge explicitly; a frontier
  executor widens scope where the edge is not drawn.
- **What it proves**: the acceptance items it satisfies, by number, and any
  behavior its tests must pin that acceptance does not already state, one
  line each; the commands that show it working, with what to expect, are
  Concrete Steps.

Code appears in the spec only where the code is itself a decision — a data
shape or schema, a public signature, a state or transition table, an
algorithm whose subtlety is the point, an exact string, constant, or piece
of copy, a test case that pins a contract — and lives in the design or in
Interfaces and Dependencies, once. Code that only shows how to do what the
decisions already say is transcription: written blind here and stale by the
time the milestone runs.

Not carried: commit messages, which test file or line to sit beside, exact
strings that are not decisions, steps. The executor writes those once, with
the real codebase in view, and runs its own test-first cycle.

**Spike milestones.** A prototyping milestone's deliverable is knowledge,
not shipped code: state the question it answers, what to build and how to
run it, what to observe, and the promote-or-discard criteria. It has no
tests; its proof is the verdict, written where the spec posed the question,
with the criteria applied — promote (a following milestone
hardens it with tests) or discard (delete the prototype; the knowledge
stays).

**The last milestone** executes the acceptance section as written — the
behavior-phrased checks with their exact commands and expected output —
in addition to the full test suite. Tests prove the parts; acceptance
proves the feature. Quote the commands so the executor needs nothing else.

**No placeholders.** A placeholder is a deferred decision: "TBD", "add
appropriate error handling" (name the errors and what happens on each),
"write tests for the above" (name the behaviors they assert), a name no
section of the spec defines. Complete means the decisions are stated; a
test named by the behavior it asserts is complete, and so is an
implementation described by its contract. Pointing at a decision the spec
makes elsewhere is not a placeholder — it is the rule.

**When it is written.** After the design is approved, never before: with
the rest of the spec, once the presentation is approved. Writing it is the first hostile read of the design — a design
statement the milestones prove wrong is fixed in the design.

**While the spec is being executed**, PLANS.md's implementing rule binds,
with brainstorming's gate as the one stop: a fork under it that the spec
does not cover goes to your human partner; everything else is decided, and
written into the spec where a later reader needs it.

> When implementing an executable specification (ExecPlan), do not prompt the user for "next steps"; simply proceed to the next milestone. Keep all sections up to date, add or split entries in the list at every stopping point to affirmatively state the progress made and next steps. Resolve ambiguities autonomously, and commit frequently.

A gap or a contradiction the spec did not foresee is expected, not a
failure of the spec: the executor resolves it in the spirit of the stated
intent and the reasons behind the nearby decisions, and continues; what it
chose reaches the spec through its one writer. It goes back to the spec's author only for a fork
under the gate — a product, taste, or substantive design decision the spec
does not cover — or when following the spec would defeat its own purpose.

A spec with one milestone is worked directly by its executor, who is its
writer as it goes. Several run through
doperpowers:subagent-driven-execution — a fresh executor per milestone, a
review at each dependency frontier — under a `doperpowers:plan-executor`
subagent (doperpowers:execspec step 4). On that path the controller is the
spec's one writer: executors report what they decided and found, and the
controller writes what a later reader needs into the section it belongs
to ("Keeping the spec current"), ticks Progress when a milestone's review
is clean, and commits, so each later executor reads it in the spec; the SDE
ledger is gitignored, so the committed spec is what a recovery reader
sees.

**A child of a composite spec** cannot extend the composite — siblings on
parallel branches share it — so its execution section is a standalone file
under `docs/doperpowers/plans/`, headed by the composite's path, the child
id, and the parent pin. It carries the constraints and the milestones and
restates nothing of the composite's design, which lives in the child's
section. Decisions local to the child that the composite does not carry
are stated here once: in the milestone they belong to, or among the
constraints when they span milestones. Its last section, `## For the
composite's writer`, is state, like Progress: each sentence of the
composite this child's work makes false or incomplete, with the replacement
proposed. Until the writer rewrites the composite that list is what says
which text governs, and an entry leaves it when the parent pin moves past
the rewrite. The SDE loop reads the document like any spec.

## Where reasoning lives

The design sections carry their own reasoning. Where a decision is made,
the section says why, and the reason is written against the choice a
reader with the code in view would otherwise make. An alternative that was
seriously weighed is named there with why it lost — a clause, not a
ceremony — and no other. What your human partner settled as a preference
or a product call is a requirement of the product: state it as one, where
a derived decision states its reason.

## Keeping the spec current

The spec states the design as it stands. When course changes — a ruling, a
review finding, a discovery, a gap resolved while building — rewrite every
section the change touches so the document reads as if it had always said
this: the rule and its reason. Every executor and reviewer reads the whole
document, and a superseded statement left standing, or a sentence that
tells its own history, is one more thing each of them must reconcile. A
statement about the system's stages — what holds between two releases, what
a later milestone builds — is design, not history, and stays.

A rule that changes after its code has landed leaves the code behind the
spec. Say which work brings it in line — a milestone added or amended, a
Progress item, in a composite the child that owns it — because without
that the mismatch reads the same as a spec that is wrong about the code,
and the next writer corrects the spec back.

What is learned while building is written where it bears:

| What it is | Where it goes |
|---|---|
| The reason for a decision — an assumption that proved false, a measured behavior | Beside the decision, with one evidence snippet (test output is ideal) |
| A fact as built that a later milestone consumes | Interfaces and Dependencies, or that milestone's entry |
| A fact about the environment that later milestones need | The constraints that open the execution section |
| A limit accepted | The repository's tech-debt tracker |
| A lesson | Outcomes & Retrospective, at finish |
| Anything else | The commit message, or the executor's report |

A review finding that was dismissed and that a later reviewer would raise
again is answered in the reason of the decision it questioned.

A decision that code, tests, or another document cites carries an id
(`C5`, `X8`); a rewrite keeps the id, and a withdrawn id is not reused.

**History is git.** Commit a change of course apart from other work, with a
message that says what moved and why — your human partner's words quoted
when they ruled; that message is the only account of the change. The
baseline is the commit your human partner approved: the spec's first
commit, made as the approved design before any review or execution alters
it, or the commit a Progress line names when approval came later. Read
history at the grain these documents have: `git log -- <spec>` for the
changes, `git log -L '/^### <heading>/,/^##/:<spec>'` for one section,
`git diff --word-diff <commit> -- <spec>` for everything since an approval
or a pin.

Two sections say where the work stands:

**`## Progress`** — right after the purpose, in the skeleton above: one line
per unit of work with its state and date, and the events that leave no
diff — your human partner's approval and any condition on it, a review
completed. How a unit went is the commit log's.

**`## Outcomes & Retrospective`** — until finish, exactly the line "Pending —
written at finish." At finish (after the whole-branch review), summarize
what was achieved against the spec's original purpose, what remains, and
lessons learned.

A spec written in the earlier form — it keeps a `Decision Log` and
`Surprises & Discoveries` — continues in that form until it closes: revise
its sections and add its dated entry as its own entries do. Code may cite
its log by number, and a log that stops without saying so reads as
complete.

## What does NOT bind

Not quoted above, and superseded by doperpowers machinery: the single fenced
code block, prose-first, no-tables formatting (specs are files, not chat
payloads — use tables, JSON, or diagrams wherever they beat prose for
precision); novice-grade self-containment (the bar above); the Idempotence
and Recovery section (worktree isolation + git); Artifacts and Notes and
"capture evidence" inside the fence (an evidence snippet beside the
decision it supports); "do
not prompt the user for next steps" at authoring time (the human gates —
design approval in doperpowers:brainstorming and spec review in
doperpowers:execspec — come first; the rule binds only during execution, as
above); the `Surprises & Discoveries` and `Decision Log` sections, "Record
all decisions in the `Decision Log` section", "document why in the
`Decision Log`", and the separate bottom-note rule for revisions (the spec
states the design as it stands and git is its history — measured
2026-11-22: in the 65 specs here that kept those sections they were 36% of
the text, one changed ruling stood in four places, and the ruling it
replaced was still asserted twice above the entry that overturned it).
These rejections
carry rationale — read the Decision Logs in
`docs/doperpowers/specs/2026-07-03-living-specs-design.md` and
`docs/doperpowers/specs/2026-09-12-one-spec-sized-by-the-gate-design.md`
before re-proposing one.

## Front of the spec

Untemplated on purpose: across this repo's existing specs no heading
structure repeats, and that variance is a feature — form fits problem
(state tables for state machines, JSON for schemas, prose for concepts).
Required: the purpose-first opening, Progress right after it, an acceptance
section phrased as observable behavior, the execution section, and
Outcomes & Retrospective.
