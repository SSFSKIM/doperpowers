# Living Specs

The design spec doperpowers:execspec writes
(`docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md`), from a design
your human partner approved, is not a snapshot of an approval — it is the
one document an initiative has, for the whole life of its feature: the design with its reasoning, the acceptance,
the execution, and where the work stands. At every moment it states the
design as it stands now: what is learned while building is written into
the section it bears on, and the feature closes with a retrospective. Its
history is git. Whoever drives the session maintains it: execspec writes
it, execution keeps it true, finishing writes the retrospective.

**The bar:** a fresh session with no conversation history can pick up the
spec and continue the work — decisions, their whys, and what was learned
that bears on them included — and an executor with nothing but this
document and the code can build any one of its milestones. Reference repo
common knowledge instead of duplicating it.

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

## What every spec has

Untemplated on purpose: across this repo's existing specs no heading
structure repeats, and that variance is a feature — form fits problem
(state tables for state machines, JSON for schemas, prose for concepts).
Five parts are in every spec, because something reads each: the purpose-first
opening; Progress right after it, where the plan-executor, the execution
loop and a recovering session find where the work stands (a composite
spec's Tracking Map is its Progress); an acceptance section phrased as
observable behavior, which the last milestone executes as written; the
execution section; and Outcomes & Retrospective, which the finish writes.

**Purpose comes first.** The spec opens by saying, in a few sentences, why
the work matters from a user's perspective: what someone can do after this
change that they could not do before, and how to see it working. What it
delivers is behavior that can be demonstrated, not code changes that meet
a definition: a feature described so narrowly by its letter that the code
compiles and does nothing meaningful has missed. Spend the words on
user-visible effects, not on incidental implementation.

**Terms of art are defined.** A phrase that is not ordinary English
("daemon", "middleware", "RPC gateway") is defined in plain language where
it first appears, with how it shows up in this repository — the files or
commands where it lives — or it is not used. Files are named by
repository-relative path and functions and modules by their exact names,
so a reader finds each by searching for it.

**Acceptance is observable behavior.** The acceptance section is a
legitimate end-to-end check of the feature, not a summary of it: what
someone can do once the work has landed, the commands to run, and the
output to expect. Each item is phrased as behavior a person can verify
("after starting the server, `GET /health` returns HTTP 200 with body
`OK`"), not as an internal attribute ("added a HealthCheck struct"). For
an internal change, say how its effect is demonstrated: a test that fails
before and passes after, a scenario that uses the new behavior.

## The execution section

Every spec carries its execution, in four sections:

- **`Progress`**, right after the purpose: the spec's ledger, kept current
  at every stopping point. A checkbox list, one line per unit of work with
  its state and date; a unit stopped partway is split into what is done
  and what remains, so the list always shows the actual state of the work.
  It also records the events that leave no diff — your human partner's
  approval and any condition on it, a review completed.

      - [x] (2026-10-01 13:00Z) M1 — the parser accepts both forms.
      - [ ] M2 — the migration (done: schema; remaining: backfill).

- **`Plan of Work`**, told as milestones (below).
- **`Concrete Steps`**: the exact commands to run and the working
  directory to run them in, with a short expected transcript where a
  command prints something to compare against. This is where validation
  lives, and it goes beyond compiling: how to run the tests, how to start
  the system where that applies, and how to watch it do something useful —
  a small end-to-end scenario, a CLI invocation, an HTTP exchange — with
  the expected output and the error messages that tell success from
  failure. Where an outcome depends on the environment, the assumption is
  stated. Updated as the work proceeds.
- **`Interfaces and Dependencies`**, when the work defines new interfaces:
  the libraries, modules, and services to use and why, and the types,
  interfaces, and function signatures that must exist at the end of a
  milestone, by stable name and path (`crate::module::function`,
  `package.submodule.Interface`).

**Milestones** tell the story of the work — goal, work, result, proof —
where Progress tracks its state; a spec has both. Each milestone is
independently verifiable and takes the work one increment toward the
spec's goal.

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

**Spike milestones.** When an unknown is large, a prototyping milestone
de-risks the work that depends on it: a library's feasibility proven in
isolation, two orders of composition measured against each other. Its
deliverable is knowledge, not shipped code: state the question it answers,
what to build and how to run it, what to observe, and the
promote-or-discard criteria. Keep the prototype additive and labelled as
one, and give independent unknowns a spike each. It has no tests; its
proof is the verdict, written where the spec posed the question, with the
criteria applied — promote (a following milestone hardens it with tests)
or discard (delete the prototype; the knowledge stays).

**Migrations** go additive first, then subtract with the tests passing. A
parallel implementation (an adapter kept beside the older path) is fine
where it lowers risk or keeps the tests passing through a large change;
the spec says how both paths are validated and how one is retired.

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

**While the spec is being executed**, the work goes from one milestone to
the next without asking your human partner for next steps: the executor
keeps every section current, records at each stopping point what is done
and what is next, resolves ambiguities itself, and commits often.

A gap or a contradiction the spec did not foresee is expected, not a
failure of the spec: the executor resolves it in the spirit of the stated
intent and the reasons behind the nearby decisions, and continues; what it
chose reaches the spec through its one writer. Two things stop the work
and go back to the spec's author, and from there to your human partner
when only they can answer: a product, taste, or substantive design
decision the spec does not cover, and a spec whose letter would defeat
its own purpose.

A spec has one writer while it runs. With one milestone that is its
executor. With several (doperpowers:subagent-driven-execution under a
`doperpowers:plan-executor` subagent) it is the controller: executors
report what they decided and found, and the controller writes what a
later reader needs into the section it belongs to ("Keeping the spec
current"), ticks Progress when a milestone's review is clean, and commits.
The SDE ledger is gitignored, so the committed spec is what each later
executor and a recovering session read.

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
proposed. An advisory sentence the child overturns is replaced by the
child's own text from then on; a binding one stands until the composite's
writer rules, and the entry is the proposal. An entry leaves the list when
the parent pin moves past the rewrite. The SDE loop reads the document like
any spec.

## Where reasoning lives

The design sections carry their own reasoning. Where a decision is made,
the section says why, and the reason is written against the choice a
reader with the code in view would otherwise make. An alternative that was
seriously weighed is named there with why it lost — a clause, not a
ceremony — and no other. A decision that rests on a preference or a
product call has no derivation to give: the section states it as a
requirement of the product and says what the requirement is for.

## Keeping the spec current

The spec states the design as it stands. When course changes — a ruling, a
review finding, a discovery, a gap resolved while building — rewrite every
section the change touches so the document reads as if it had always said
this: the rule and its reason, with nothing in it that a reader who never
saw the earlier text could tell had changed. Who ruled, when, in whose
words, and what the text said before go in the commit message. Every
executor and reviewer reads the whole document, and a superseded statement
left standing, or a sentence that tells its own history, is one more thing
each of them must reconcile. A statement about the system's stages — what
holds between two releases, what a later milestone builds, what the code on
the branch still does — is design, not history, and stays.

A spec that appends its changes instead — a decision log, a surprises
section, revision notes at the bottom — grows a second account of itself
that every reader must reconcile with the first. Measured over the 65
specs here that kept those sections: they were 36% of the text, one
changed ruling stood in four places, and the ruling it replaced was still
asserted twice above the entry that overturned it.

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

**History is git.** Commit a change of course apart from other work; its
message is the only account of the change. The baseline is the commit your
human partner approved: the spec's first commit, made as the approved
design before any review or execution alters it, or the commit a Progress
line names when approval came later. Read history at the grain these
documents have: `git log -- <spec>` for the changes,
`git log -L '/^### <heading>/,/^##/:<spec>'` for one section,
`git diff --word-diff <commit> -- <spec>` for everything since an approval
or a pin.

A change of course shows in `Progress` as the work it adds or reopens; how
a unit went is the commit log's.

**`## Outcomes & Retrospective`** — until finish, one line saying it is
pending. At finish (after the whole-branch review), summarize what was
achieved against the spec's original purpose, what remains, and lessons
learned.

A spec written in the earlier form — it keeps a `Decision Log` and
`Surprises & Discoveries` — continues in that form until it closes: revise
its sections and add its dated entry as its own entries do. Code may cite
its log by number, and a log that stops without saying so reads as
complete.
