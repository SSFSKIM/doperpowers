# Forging: compile-class work, from a rigorous manifest to an unattended run

**Date.** 2026-10-15. **Status.** Spec written from the approved design; under
self-review, then independent review; not yet executing. **Research.**
`docs/doperpowers/research/2026-10-15-compile-class-work/prime-agent-rust.md`
and `prior-art-survey.md` beside it (28 sources). **Design history.** The
brainstorm ran in one interactive session on 2026-10-15: the human partner
opened with the observation that a task whose specification and verification
are rigorous enough behaves like source code — the agent swarm compiles it —
and asked for the layer that evaluates and strengthens that rigor before the
work starts; the grill resolved it into a whole work system for compile-class
work (below), with the rigor layer as the preparation phase's exit gate. Four
forks were put to the human partner and decided: technical class-4 branches
gate, taste branches are scheduled; the audit is rubric-driven by default with
independent readers for long runs; landing gates on a fast sample with the full
oracle at wave ends; the first run's target is a scenario, not a run — Claude
Code 2.1.300 reforged on Bun through a module strangler.

## Purpose

Some engineering work is large, technical, and has a fixed target: port this
program to that language with no behavioral difference; rebuild this binary
from its specification; migrate these three thousand files. The goal is clear,
the forks are technical, and correctness can be decided by executing a
reference. Today doperpowers runs such work the way it runs product work — a
design, a spec, a sequential executor loop, the human present for forks — and
that shape spends the human on decisions a reference could have made and
leaves the swarm's parallelism unused. After this work, a human partner who
has such a target prepares it once, with the agent, into a **manifest**: the
reference pinned, the oracle built and proven to catch divergence, every
component of the reference in a ledger with the oracle slice that proves it,
the work cut into units along what the oracle can check, the grading rubric,
the per-unit cycle, the stop condition, and the classes of question that may
reach a human. A **rigor gate** audits that manifest and passes it only when
no technical decision is left undetermined and every unit's proof would fail
on a stub. From there the **root** session runs the units as a tree of
subagents — a **controller** per wave dispatching each unit's oracle author,
implementer and reviewer, every level fanning out as its work demands — for
days or weeks in parallel worktrees, with the mechanical steps (verification,
the stub check, landing, the ledger's status) as scripts the agents call and
every agent's state on disk, so the whole tree resumes after a crash. The
root re-plans, fixes the process rather than the output, and reports at wave
ends, and a **delegator** answers from the manifest whatever the manifest
answers, so that what reaches the human is only what the manifest could not
decide.

How to see it working, smallest first: the toy forge under `tests/forging/toy/`
is a bundled TypeScript CLI with a short replication-grade spec; the skill
turns it into a manifest, the gate passes it, the root's agent tree reforges it
module by module with the reference bundle as the oracle, and `forge.py oracle full`
ends with zero divergences and a ledger with every component `matching`. At
scale, without a run: the Claude Code 2.1.300 scenario under
`docs/doperpowers/research/2026-10-15-compile-class-work/scenario-2.1.300/`
carries a manifest built from the 404,213-line harness specification and the
extracted bundle, an oracle harness for the provider-request, headless and
on-disk axes that scores 2.1.300 against itself at 100% and catches the 2.1.299 → 2.1.300
changelog as divergences, and a gate record that says, honestly, which ledger
items the built axes cover and which wait on the TUI axis.

## Progress

- [ ] M1 — The skill: doctrine, manifest shape, oracle patterns, rubric, rigor gate
- [ ] M2 — The 2.1.300 scenario manifest: target, ledger, unit graph, rubric, cycle, run conditions
- [ ] M3 — The scenario's oracle harness, the strangler spike, and the gate record
- [ ] M4 — The forge tools: plan, worktrees, oracle drivers, stub check, publication, verification, status
- [ ] M5 — Landing, `full` at the tip, ledger updates, gaming tests
- [ ] M6 — The agents and their protocols: controller, roles, root, delegator
- [ ] M7 — The toy forge end to end with a crash and resume, docs, version

## Terms

- **Compile-class work** — work with a fixed **reference** whose behavior is
  the target, an **oracle** that can be built by executing that reference, and
  forks that are technical rather than taste. Ports, parity rewrites,
  reimplementation from a spec plus a reference, mechanical migrations.
- **Reference** — the artifact whose behavior the result must match: a binary,
  a test or conformance suite, a reference implementation. Pinned to one
  revision for the whole run.
- **Oracle** — a procedure that runs the reference and the candidate on the
  same scripted inputs and compares observations after **normalization**
  (the rewriting that makes two runs of the reference itself identical).
- **Parity axis** — one observable surface the oracle compares: outputs,
  requests sent to a provider, files written, protocol messages, rendered
  frames.
- **Oracle slice** — the named subset of the oracle's scripted inputs that
  proves one ledger item or one unit.
- **Manifest** — the preparation phase's product: a directory `forge/` in the
  target repository (shape in §2 and `skills/forging/references/manifest.md`).
- **Parity ledger** — `forge/ledger.tsv`: every component of the reference,
  its oracle slices, its status (`missing`, `partial`, `matching`), and any
  divergence, accepted with a reason or triaged with an issue.
- **Unit** — the piece of work one pass of the cycle owns: its ledger items,
  what it touches, what it consumes and produces, its oracle slices.
- **Cycle** — oracle author → implementer → reviewer and verifier →
  landing, with bounded returns to the implementer (§2.6): the default a
  controller runs and adapts, not a state machine in a script.
- **Access tier** — what a role may change: tier A (the oracle author)
  writes `forge/oracle/` and the unit's shim, tier B (the implementer) its
  worktree outside `forge/oracle/` and the ledger, tier C (the reviewer, the
  delegator) nothing. Every tier reads everything — the reference, the spec,
  the oracle and its expectations — and may run the reference; the held-out
  is the one thing no role is given. Write scope is held by the role's
  agent definition (the reviewer's tools cannot write) and the landing's
  path check.
- **Forge tools** — `skills/forging/scripts/forge.py`, the mechanical
  steps the agents call and nothing can persuade: the plan, worktrees, the
  oracle's drivers, the stub check, publication, verification, landing,
  `full`, status, usage and the report.
- **Controller** — `doperpowers:forge-controller`, the subagent the root
  dispatches per wave: it runs the cycle for its units, dispatching their
  roles as its own subagents.
- **Root** — the session that runs the preparation and, in the run phase,
  owns the manifest, dispatches the controllers, re-plans, fixes the
  process, and reports; a human-opened interactive session or a sminos
  seat.
- **Delegator** — `doperpowers:forge-delegator`, the agent the root puts in
  front of the human: it answers escalations the manifest answers and drafts
  the question for the rest.
- **Fast sample** — a 1–10% sample of the full oracle on a seed; the
  tools draw a fresh seed for every check they make, so a pass on one
  sample says nothing about the next. **Full** is the whole oracle;
  **held-out** is a slice no role is given: the root keeps it outside every
  worktree and passes its path to `forge.py oracle heldout --path <p>`
  itself, and neither the manifest nor an environment variable names it,
  since every subagent's shell inherits the session's environment; the
  roles are told it exists and is not theirs. The recorded
  **expectations** live outside the repository for their size
  (`FORGE_EXPECTED`), and every role may read them.
- **Stub check** — the mechanical check that a unit's slices fail when the
  unit's module is stubbed (its exports throw, or its paths are emptied);
  the proof that a slice proves something.
- **Gate-miss rate** — in the run, the count of `BLOCKED` returns and
  class-4 questions the delegator has to draft, per wave: each is a decision
  the gate did not find.
- **Strangler build** — a hybrid of the reference's own modules and reforged
  modules, runnable as a whole, so one replaced module is proven by the whole
  program's oracle. Available only when the candidate shares the reference's
  runtime.
- **Decision classes** — every decision an implementer will face is (1)
  decided by the manifest or spec, (2) derivable from their intent plus the
  code so that two competent implementers derive the same answer, (3) free,
  with the manifest saying why the oracle is invariant to it, or (4)
  behavior-affecting and neither decided, derivable, nor declared free. A
  class-4 decision is a **branch**; the gate admits none that is technical and
  schedules those that are taste.
- **Status vocabulary** — what a role returns: `DONE`, `MORE_WORK` (another
  round with the findings attached), `BLOCKED` (needs an input it names),
  `INFEASIBLE` (the sanctioned honest exit, with the reason), `ERROR`
  (environment). The first line of a role's report file is its status.

## Design

### 1. Phase 0 — what qualifies

Three tests, all required: a reference exists and can be pinned; an oracle can
be built that executes the reference to produce expected observations (the
expected values come from the reference, never from the agent being judged);
the remaining forks are technical — the candidate's structure may follow the
reference's, and the human partner has no taste decision inside the work
beyond what the manifest can schedule. A target that fails any test takes the
attended path (doperpowers:brainstorming → doperpowers:execspec) as today.
The skill states the verdict and the failing test in one paragraph; it does
not grill a target that fails.

Why three tests and not a size threshold: size is what makes the swarm
worthwhile, but the reference and the oracle are what make it *possible*; a
small target with an oracle is still compile-class (the toy), and a large
target without one is product work however technical it looks.

### 2. Phase 1 — the manifest

The preparation phase is attended: the human partner and the root build the
manifest together. Every strong result in the survey had its human working on
the oracle and the process before and during the run (Prime Intellect built
the verification setup first; Bun's human edited prompts and checked that
tests actually ran; the one fully unattended swarm produced the most disputed
output), so this phase is where the human's time goes, and the run phase is
built to need little of it.

The manifest is a directory in the target repository:

```
forge/
  manifest.md        the document (sections 2.1–2.8 below), living-spec-shaped
  ledger.tsv         the parity ledger
  units.json         the unit graph
  rubric.md          the reviewer's grading sheet
  oracle/            the harness: run, normalize, compare, slices, fast-sample spec
  gate/              the audit's artifacts: decisions.tsv, matrix.tsv, readers/, verdict.md
  runs/<run-id>/     the run phase's records and progress files (§2.7)
```

Held-out slices live outside the repository and every worktree, at a path
the root passes on the command line of `forge.py oracle heldout --path <p>`
and the manifest never names. No environment variable carries it: the tree
runs in one process, and every subagent's shell inherits the session's
environment (SPEC chapter 16, "Child environment").

#### 2.1 Target and reference

The reference's revision, hash, and how to obtain and run it. The target
(language, runtime, repository). The parity axes that must match and, as
explicitly, what need not: performance, platform coverage, telemetry
destinations, anything the human partner excludes. The **first-pass rule**:
the candidate's structure follows the reference's until parity is reached;
idiomatic restructuring and optimization are a later phase with their own
oracle (survey principle 6: structural correspondence is what makes parity and
side-by-side review possible, and most of Bun's post-green regressions were
constructs that look alike in both languages and behave differently).

#### 2.2 The oracle harness

One differential runner per parity axis under `forge/oracle/`, each with
`run <binary> <slice>`, `normalize`, and `compare`. The expected side is
always a recorded run of the reference. Six properties the manifest must show
evidence for, because each has a failure on record:

- **Self-parity.** The reference against itself, same slices, twice, scores
  100% after normalization. Whatever differs between two runs of the
  reference is nondeterminism, and the normalization is defined by making it
  disappear — ids, timestamps, ordering of independent events, process ids.
- **A verified verifier.** A seeded divergence is caught: an adjacent version
  of the reference when one exists (the scenario has 2.1.299 and 2.1.296
  installed; the changelog names what changed), else a mutated copy. The
  harness counts what it skipped and the count is zero or explained; a
  differential fuzzer on record reported "0 divergences" because 28 of 37
  cases threw at construction and were silently skipped.
- **Fast and full.** `fast --seed <n>` is a 1–10% sample — Carlini's
  agents each ran their own; here the implementer runs it on seeds of its
  own as it works, and the tools draw a fresh seed for every check they
  make; `full` is everything; output is a few lines with the detail in
  files. Every oracle run gets a fresh `HOME` and config directory.
- **Held-out.** A slice no role is given, run by the root at wave ends and
  at closure. Reboot's translators passed 100% of the visible tests and
  62–92% of the hidden ones; this is the only measurement of that gap.
- **A real-input corpus** where one exists — recorded sessions, a file
  corpus, production inputs replayed with recorded responses — because a
  scripted oracle proves only what it exercises (Prime Intellect, giflib's
  30M-file corpus).
- **No delegation, and a held-out no role is given.** The candidate is proven
  by its own behavior, never by calling the reference: Reboot's translator
  called the original C binary despite instructions, and Carlini's compiler
  handed its 16-bit boot code to GCC, so where the shape allows it this is
  structural — a strangler's hybrid for a unit leaves that unit's reference
  chunk out of the build, and a candidate that imports it does not build —
  and elsewhere a rubric item. Reading the reference is not delegation: every role reads
  the reference, the spec, the oracle and its expectations, and runs the
  reference beside its candidate, as every port on record did. The held-out
  is the one thing kept from the roles, and it is kept by instruction: no
  role is given its path, and each is told a held-out exists and is not
  theirs — a stated prohibition, which beside the honest exit is what the
  human partner holds sufficient (§2.5).

#### 2.3 The parity ledger

`forge/ledger.tsv`, one row per component of the reference, columns:

```
id  component  source  reference_locus  unit  axes  slices  status  divergence  note
```

`source` is where the spec describes it; `reference_locus` where the
reference implements it; `status` is `missing` | `partial` | `matching`;
`divergence` is empty, `accepted:<reason>` or `triaged:<issue>` (the
TypeScript-to-Go port's `submoduleAccepted` / `submoduleTriaged` pattern).
The ledger is the contract, and no role writes it: the tools move
`status` from slice results at landing and at `full`; a divergence entry is
written by the root after review, and a `triaged` entry is a ledger change
request — an escalation class, so it reaches the human through the
delegator rather than closing on a re-plan alone; nothing else changes
without a dated line in the manifest's Decision Log. Done means no `missing`,
every `partial` triaged, every divergence recorded.

#### 2.4 Decomposition along what the oracle can check

The macro architecture is done once, here, not per unit (Bun did all design
up front; Prime Intellect's per-task planner existed to write ground truth and
the verifier). The manifest picks one of four shapes by what the oracle can
prove at unit granularity, and records why the others lost:

- **(a) Module strangler** — the candidate shares the reference's runtime, so
  one module at a time is replaced in a hybrid build and the whole program's
  oracle proves it. Strongest per-unit oracle; order is the import graph,
  leaves first. The scenario's shape (§6).
- **(b) Feature-reduction ladder** — a minimal runnable core first, then
  features restored one level at a time, every level a runnable program with
  its oracle slice (Reboot; 6–20 points better on hidden tests than porting
  without reduction). For interpreters, CLIs, harnesses ported across
  runtimes.
- **(c) Dependency-order units with per-unit I/O oracles** — leaf functions
  up, each with recorded inputs and outputs of the reference (Syzygy,
  Oxidizer). For libraries where instrumentation is feasible.
- **(d) Whole port, then convergence on a count that goes down** — everything
  translated, then compile errors by crate, then smoke, then test shards
  (Bun). For mechanical ports whose units cannot run alone. Out of this
  version: the cycle and the gate need per-unit slices that fail under a
  stub, which this shape has only at the end; it is listed so a target that
  needs it is recognized and routed to a later design, not forced into
  (a)–(c).

`forge/units.json` carries the unit graph — for each unit: `id`, `title`,
`ledger` (ids it proves), `touches` (paths), `reference_locus`, `consumes`
and `produces` (interfaces, by name), `slices`, `max_rounds`, and per-role
model overrides. Interfaces at unit edges are fixed in the manifest before the
run; a unit that needs an interface the manifest does not fix is a gate
finding.

#### 2.5 The rubric

`forge/rubric.md`, fixed once per target, is what the reviewer grades against
and what the verifier checks mechanically where it can. The implementer's
brief carries it too, its prohibited items named as what deceives the
verification, beside the honest exit (`INFEASIBLE`) that makes a stated
prohibition hold (§2.6):

- the unit's oracle slices pass in a fresh checkout (verifier);
- the implementer's own delta — its commits as replayed by the latest
  rebase, `onto..head`, never the aggregate from the unit's oracle revision,
  which other units' publications and landings legitimately enter — touches
  nothing under `forge/oracle/` or `forge/ledger.tsv` (verifier, by path);
- no test skipped, deleted or weakened; a coverage drop is a deletion alarm
  (verifier where tooling exists, reviewer always);
- no hard-coded expected values or special cases for the oracle's inputs,
  no stubs or `unimplemented` paths standing in for behavior, no call to the
  reference — its binary, or the chunk a strangler unit replaces, which the
  hybrid leaves out (reviewer; the build; the held-out slice is the
  backstop);
- a workaround that needs a paragraph to justify is wrong (reviewer);
- the **look-alike list** for this language pair — constructs that read the
  same and behave differently — is checked line by line in the diff
  (reviewer; the skill's reference seeds lists for JS→Rust and bundle→TS);
- data the spec reproduces verbatim — prompts, constants, schemas, exact
  strings — matches byte for byte (verifier where the spec's own fidelity
  tools exist, reviewer otherwise);
- structure corresponds to the unit's plan and the first-pass rule.

#### 2.6 The cycle

Each unit runs this cycle under its wave's controller (§3), each role a
subagent the controller dispatches; a further round resumes the role by
SendMessage rather than dispatching a fresh one, since three rounds at opus
should not pay orientation three times — fresh only on a re-brief. The
cycle is the default, and the controller adapts it to what it finds —
splitting a unit, adding a reader, giving two implementers the halves of a
large chunk — recording what it did in its progress file:

1. **Oracle author** (tier A; `doperpowers:forge-oracle-author`, opus/high)
   — in the unit's **author worktree**, branched from the integration tip,
   and from the unit's ledger items, the spec and the reference, writes the
   unit's brief (what exists at the end, what it touches, the interfaces, the
   decisions that belong to this unit alone), extracts ground truth, and
   writes or extends the unit's oracle slices. In a strangler the author also
   generates the unit's export shim (§6). Returns `DONE` with the brief, or
   `INFEASIBLE` when the ledger items cannot be proven by any slice it can
   build (that is a gate finding returned to the root). The author is the one
   role that writes under `forge/oracle/`, so its work is checked
   mechanically when it returns: the **stub check** — the unit's slices must
   fail with the unit's module stubbed — and, when anything under
   `forge/oracle/` changed, self-parity and the mutation run again. "Fails on
   the current tree" means nothing in a strangler, where the current tree is
   the reference; the stub is the failure the slices must show. Work that
   passes is **published**: `forge.py publish`, under the integration lock
   that serializes every write to the integration branch (§3), replays it
   onto the tip as the unit's oracle revision, and the implementer works
   in the unit's **implementation worktree**, branched from that revision,
   so its diff is measured from a baseline that already holds the author's
   changes and any `forge/oracle/` change in that diff is the implementer's.
2. **Implementer** (tier B; `doperpowers:forge-implementer`, opus/high,
   downgradable per unit) — in the implementation worktree, from the spec, the
   reference, the brief and the oracle, implements the unit; in a reforge
   the reference module is its first source, and the spec supplies the
   names and the intent a minified expression hides. It runs the oracle
   itself as it works — the unit's slices, `fast` on seeds of its own, the
   reference beside its candidate — through the manifest's sandbox
   provider. Returns `DONE` with a report, or `MORE_WORK`, `BLOCKED`,
   `INFEASIBLE`.
3. **Reviewer** (tier C; `doperpowers:forge-reviewer`, sol/xhigh, read-only:
   the diff, the spec, the rubric, the implementer's report) and
   **verifier** (mechanical — `forge.py verify`, which the controller runs
   on the sandbox provider: a fresh checkout at the unit's
   head with the reference reachable, the unit's slices and a fresh sample of
   the full oracle run, the path checks applied, a machine-written report)
   run in parallel. The verifier is not a model: nothing can persuade it, and
   it costs nothing to run again.
4. **Landing** (§3) when both pass; otherwise the findings go back to the
   implementer, up to `max_rounds`; past that the controller re-plans it
   within its wave (split, re-brief) or returns it to the root with the
   history, and the root re-plans it or records `INFEASIBLE` in the ledger
   as a triaged divergence. A role that ends without a report — an API
   error, a turn limit — is resumed once to report, dispatched again once,
   then escalated.

Separation is the anti-gaming structure the survey reports working: the
author of the proof is not the implementer, and the proof is checked by a
script when the author returns; the judge runs in another context, on
another model, and sees the diff; the verifier is a script in a clean
environment; the ledger is written by no role; the honest exit exists
(ImpossibleBench: offering an explicit abort cut cheating from 54% to 9%).

#### 2.7 Run conditions

Written in the manifest before the run: the **stop condition** (every unit
landed; `full` green on k consecutive runs; held-out green; the ledger done
per §2.3); the **escalation classes** that may reach the human (an oracle
defect, a ledger change request, a unit `INFEASIBLE` twice after re-planning,
a budget threshold crossed, a held-out failure the root cannot attribute,
the gate-miss bound breached, an infrastructure loss past its retries) and the **checkpoints** (every wave end, with the report); the **budget** per unit and per run in
tokens (with an optional price table for a dollar estimate) and how many
landings pass between two `full` runs — fields the controllers and the root
enforce and report against from the agents' usage, which `forge.py usage`
sums from their transcripts, charging a role's helpers and its retired
attempts to its unit and the root's and the controllers' own to the run as
overhead; the **compute topology** — two worktrees per unit on the root's
host (the author's and the implementer's, §2.6), how
many units at once (the default rule: one per four cores and eight
gigabytes of the host), and the **sandbox provider** the verifier's and the
oracle's runs go to: `local` (a fresh worktree or container on the host)
or `ci-kit` (SSFSKIM/ci-kit's `ci-gate`, which runs the target's declared
gates on the tested commit off this host — for a private repository on its
GCE Spot backend, one Spot VM per job — and prints one line per gate and a
verdict); the oracle runner contract does not change with the provider, so
a provider is a thin wrapper, and this spec implements `local` and defines
the interface, with the retry rule below (the scenario's choice is in §6); **state** on disk in three layers: the harness's transcript of every agent
(the root's, and each subagent's under the session's directory, from which a
stopped agent resumes by SendMessage); git (each unit's branches and
worktrees, committed as the work goes); and the forge's records — the tools'
(`integration.jsonl`, the log of every publication and landing;
verification results; `events.jsonl` for escalations, budget thresholds
and oracle failures at the tip; the ledger's status) and the agents'
progress files (the root's and one per controller: each unit's state,
attempt and head, and every agent id the unit has had, retired ones
included), rewritten rather than appended (Cursor's scratchpad finding),
so a restarted root rebuilds its view from them and resumes the tree
rather than restarting it (§3; schemas in Interfaces); the **restart procedure** (a smoke test of the
integration branch before any dispatch, as every long-run harness on record
learned to do); and the rule that the root **fixes the process, not the
output**: a failure class that recurs becomes a change to the rubric, a
role's brief, or the oracle, followed by a re-sweep — the root never edits
product code (Bun, Airbnb, Carlini, Google).

A gate that fails is not always a verdict. ci-kit records a preempted Spot
VM but does not re-run its job, which GitHub fails like any other and
ci-kit's CLI reports as a failed gate (the ci-kit design, §3a), so the
provider contract tells a loss from a result: the forge's gates write a
result marker when the oracle completes; a failed gate job with no marker
is an infrastructure loss; and the `ci-kit` provider re-runs the same head
up to the manifest's `infra_retries`, then records an `ERROR` environment
escalation — never `MORE_WORK`, and never a round against the unit's
`max_rounds`.

#### 2.8 The rigor gate

The exit of Phase 1; `skills/forging/references/rigor-gate.md` is its rubric
and `forge/gate/` its artifacts. Five parts:

- **Decision ledger** (`decisions.tsv`): every decision point an implementer
  will face, found by reading the manifest and the sample units' briefs as an
  implementer would, each classified 1–4 with its source.
- **Verification matrix** (`matrix.tsv`): every ledger item against its
  slices — does a slice exist, is the axis built, does it fail under the
  stub check (§2.6), is it gameable without the behavior (the held-out and
  corpus coverage), which unit proves it.
- **Independent readers** (`readers/`), for a run longer than a day: on a
  sample of units, two or three readers each given the manifest, the spec and
  one unit's brief, asked for the decisions they would have to make, their
  choice, and the tests they would write — one of them at the implementer's
  rung (opus), since agreement among cheaper models is not invariance among
  the models that will run; the root dispatches them as subagents from the
  brief in `rigor-gate.md`, and the auditor diffs the lists. A divergence on
  a behavior-affecting choice is a class-4 decision the ledger missed; a
  divergence on tests is an under-determined slice.
- **Judge calibration** (`calibration/`): the reviewer agent, with the
  rubric, on seeded diffs — a stub, a memorizer, one look-alike trap from the
  rubric's list — must flag each; a judge that passes a seeded diff is
  re-briefed before the run. This is the survey's one principle the design
  would otherwise only claim: judges need calibration, and self-critique does
  not supply it.
- **The audit** — the `doperpowers:adversarial-reviewer` agent with the gate
  rubric in its brief, reading the manifest, the evidence from §2.2, the two
  ledgers, the readers' lists and the calibration; its verdict is
  `forge/gate/verdict.md`.

What the gate can claim, and no more: executor-invariance is **sampled** at
the gate — `n` units, `k` readers, zero behavior-affecting divergences — and
**measured in the run**: every `BLOCKED` a role returns and every class-4
question the delegator has to draft is a decision the gate missed, counted
in the wave report as the gate-miss rate, with a bound the manifest sets
whose breach is an escalation class (re-audit the manifest before the next
wave). The gate passes when: in the sample no technical class-4 decision
remains (each was decided in the manifest or given a derivation rule), every
taste class-4 decision is scheduled as a checkpoint at a named unit with its
question drafted, every sampled unit's slices fail under the stub check,
self-parity is 100% and the verifier has caught a seeded divergence on every
built axis, the judge flagged every seeded diff, and the matrix names
honestly which ledger items no built axis covers. The human partner approves
the manifest on the verdict. A gate that fails returns to the preparation
with the findings; there is no partial pass.

### 3. Phase 2 — the run

The **root** holds the manifest and runs the run as a tree of subagents.
The default shape, which every level adapts to what it finds:

```
root (the session)        manifest, waves, escalations, held-out, reports
└─ controller per wave    doperpowers:forge-controller: the cycle for its units
   ├─ oracle author  ┐
   ├─ implementer    ├ per unit, each fanning out as its reading demands
   └─ reviewer       ┘
   forge.py           verify, stub, publish, land, full: run by the controller
```

Why agents at every level and scripts only for the mechanics: the
situations a multi-week run meets — a unit that should be split, an oracle
slice that is wrong, a failure class that recurs, a chunk too large to read
in one context — are judgment, and a script handles only the transitions it
encodes, turning every other case into an escalation; and work against a
404,213-line spec and a 4.93 MB chunk needs fan-out shaped to the reading,
which only the agent doing the reading can choose. The mechanics stay
scripts because nothing should be able to persuade them. The shape is
doperpowers's own — a controller dispatching an executor and a reviewer per
milestone (doperpowers:subagent-driven-execution) — with the forge's oracle
in place of the plan's tests, and the human partner can watch it in the
session's agents pane and through the bridge.

The root dispatches each wave's controller as a background subagent,
briefed with the manifest, its units and its progress file; folds the
controller's report when it returns; runs held-out; reports; and dispatches
the next. It may split a large wave across several controllers, or start
the next wave's controller for units whose dependencies have landed. A
controller creates each unit's author worktree at the integration tip
(`forge.py worktree <unit> --author`) and, once the author's work is
published, its implementation worktree at the unit's oracle revision
(`forge.py worktree <unit>`, created there or reset to it), dispatches
its units' roles in parallel up to the manifest's limit, resumes a role by
SendMessage for a further round, runs the mechanical steps, re-plans a
stuck unit within its wave, runs `full` after the manifest's count of
landings and at its wave's end, and returns to the root what it cannot
decide — an escalation class, or a unit past re-planning.

**Limits the tree runs under.** The harness caps subagent nesting at depth
3 and concurrency at 20 subagents per session by default, each raised by an
environment variable (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`,
`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`; SPEC chapter 18). The default shape
reaches depth 3 — root 0, controller 1, role 2, a role's fan-out 3 — and
the root's environment sets the concurrency from the manifest's `parallel`
with room for fan-out; a deeper shape raises the depth.

**Resume.** Every agent's transcript is on disk
(`~/.claude/projects/<slug>/<session>/subagents/agent-<id>.jsonl`, beside a
metadata sidecar), and a stopped agent resumes from it by SendMessage with
its context intact (SPEC 18.25). The tree lives in one process, so a crash
stops every agent in it at once: the root resumes with `claude --resume`,
reads its progress file and `forge.py status`, and continues each controller
that was in flight by SendMessage, which continues its roles the same way.
Where the harness refuses a resume — a transcript too large to load, a
working directory it rejects — the agent is dispatched fresh with the
unit's branch and the progress file, which is why both are kept current. A
crash can lose the uncommitted part of each agent's work and its turn in
flight; roles commit as they go to keep that small. A lost host is the
larger failure and loses what was not pushed: `publish` and `land` push the
integration branch, a `ci-kit` verification pushes the head it tests, and
a devcloud host mirrors the transcripts to the session store. Should one process
prove too small for the tree, the root partitions the graph across sminos
seats running the same protocol — deferred until a run measures it.

**Landing** is a queue under the integration lock (below): rebase the unit's branch onto the
integration branch, recording the `onto` commit, so the implementer's own
delta is `onto..head` whatever else has landed; if the rebase changed that
delta the review is void and the unit returns to step 3; run the unit's
slices and the fast sample at the tip;
fast-forward; on failure the unit goes back to the implementer with the
tip's diff. Every write to the integration branch — a publication, a
landing's fast-forward, `full`'s ledger update — holds the one
**integration lock** and is recorded in the run's integration log
(`integration.jsonl`) as an **intent** line (the operation, its unit, the
old and new tip) before the ref moves and a **done** line after, since
appending a line and moving a ref are two writes. Every writer, and
`status`, first reconciles a pending intent with the ref — at the intent's
new tip: mark done; at its old tip: redo the move; elsewhere: escalate —
and the rule is unambiguous because nothing moves the ref outside the
lock. A `full` or held-out failure
**after** landing reopens the unit whose landing **caused** it, found by a
bisect over the wave's landings from the last green tip (landings are
linear, so this is mechanical); the ledger names the behavior that broke,
not the blame — a newly landed caller can break a slice an earlier unit
owns. A slice belongs to the tip's regression suite only once its unit has
landed: a published slice for a unit still being implemented runs in that
unit's verifications and nowhere else, so a publication cannot redden the
tip (in a ladder or dependency-order shape the slice rightly fails until
its unit lands; in a strangler the tip still holds the reference module).
No new unit dispatches while the tip is red (Carlini's compiler: new features kept
breaking existing functionality until the gate existed). `full` runs at
every wave end and after the manifest's count of landings; held-out runs at
wave ends by the root. This is the middle path between
Cursor's observation that a full gate on every commit serialized its agents
and Carlini's that his run needed a regression gate it did not start with;
the 2026-09-27 parallel-milestones design's landing rules (approval bound to
the head it covers, one at a time, tested at the tip) are reused.

**The root's loop**, in `references/root-protocol.md` (the controller's in
`references/controller-protocol.md`): start with the smoke test and resume;
dispatch waves; fold the controllers' reports and the tools' events — a unit past
`max_rounds` is re-planned (split by ledger items, re-briefed) or recorded
`INFEASIBLE` as a triaged divergence; a failure class seen twice becomes a
rubric, brief or oracle change and a re-sweep of the affected units; ledger
changes get a dated Decision Log line; at each wave end, `full` and held-out,
the ledger's counts, the gate-miss rate, the cost, and a report to the human
through the session's `<message>` (the `to-human` output style, or sminos
when the root is a seat). Escalations go through the **delegator** first — a
fresh reader per escalation, so the manifest does not have to sit in a
days-long root's context: given the event and the manifest, it resolves what the manifest decides (classes 1–3), records the
resolution, and for class 4 or a taste call writes the question with the
alternatives and the recommendation before it reaches the human. Reboot's
delegator resolved 77% of its escalations; the manifest is what gives ours
that reach.

### 4. Phase 3 — closure

`full` and held-out green per the stop condition; the ledger audited (every
`partial` and divergence has its entry); a **scheduled dogfooding window**
in which the human partner uses the candidate for real and every difference
found becomes a ledger divergence or a unit (the oracle proves what it
exercises; this is the planned measurement of what it did not); the
structure phase, mandatory before closure when the unit shape deferred
structure to it (§6); then the manifest's maintainability checks assigned
to final acceptance and, for a reforge, the customization suite (§6); then,
optionally, a second phase on the candidate — idiomatic restructuring,
performance — with its own oracle (the candidate's full suite) and no numeric
target (Prime Intellect's hillclimb: a fixed threshold becomes a stopping
point). The manifest's Outcomes & Retrospective records what parity was
reached, what the oracle missed, and the cost.

### 5. Where it lives in doperpowers

New:

- `skills/forging/SKILL.md` — Phases 0, 1 and the gate, as the agent runs
  them with the human partner; `references/manifest.md` (the directory and
  document shapes, the ledger and units schemas, the status vocabulary),
  `references/oracle-patterns.md` (axes and oracle designs by reference kind
  — a CLI or harness, a library, a compiler, a web service — the six
  properties of §2.2 and how to show each), `references/rubric.md` (the
  template and the look-alike lists), `references/rigor-gate.md` (§2.8 as the
  auditor's and readers' briefs), `references/root-protocol.md` and
  `references/controller-protocol.md` (§3's operator manuals).
- `skills/forging/scripts/forge.py` — the forge tools. The gate's readers
  need no script: they are read-only subagents the root dispatches from
  `rigor-gate.md`'s brief.
- `agents/forge-controller.md`, `forge-oracle-author.md`,
  `forge-implementer.md`, `forge-reviewer.md`, `forge-delegator.md` — the
  contracts, with the repository's conventions
  (the compaction tools withheld; `AskUserQuestion` disallowed for the
  detached roles; the reviewer read-only and unable to spawn).
- `tests/forging/` — the tools' tests, the gaming tests, the toy,
  `run-forging-tests.sh`.
- The scenario under `docs/doperpowers/research/2026-10-15-compile-class-work/scenario-2.1.300/`.

Reused: doperpowers:brainstorming's purpose exploration and grill for Phase 1;
living-spec.md's document doctrine for `manifest.md`; the
`doperpowers:adversarial-reviewer` agent as the gate's auditor; the
2026-09-27 landing design; doperpowers:subagent-driven-execution's controller
shape for the controller; sminos and the bridge as the root's channel when it
is a seat; the self-compaction mod for a root that runs for days.

Why the run is a tree of subagents rather than a script driving headless
sessions — the shape this spec first chose — is §3's argument; the Decision
Log records the change. The Workflow tool was considered and rejected for
the same reason: a script's fixed control flow cannot reshape the tree to
what the agents find.

Why the verifier is a script and not the "verifier agent" named in the
presentation: the role's work is to run commands in a clean environment and
report; a model there adds cost and a surface that can be argued with.
Recorded as the second Decision Log entry; the human partner's
approval covered the role, and this refinement serves its intent.

### 6. The scenario: Claude Code 2.1.300, reforged on Bun through a strangler

The acceptance instance for Phases 0 and 1, built for real and stopped at the
gate; no Phase 2 run. One caution the root records in the scenario's
manifest: reverse engineering and reimplementing the Claude Code binary is a
matter of Anthropic's terms, and whether this scenario ever becomes a run is
the human partner's call.

**Reference.** `~/claude-code-bundle/2.1.300/`: the binary (`MAP.md` records
its hash and carve), the extracted module graph (`modules/`, 2,413 chunks and
the entry stub), the reprint (`cli.pretty.js`, 1,184,755 lines), and the
specification (`SPEC/`, 57 chapters, 404,213 lines, replication-grade by its
own criterion — "a competent systems engineer with no access to Anthropic's
source, given only this library and a Claude-compatible inference API, can
rebuild the harness and get behaviourally equivalent results" — with
`_inventory/citation-anchors.tsv` tying spec sections to chunk lines and
`_inventory/section-index.tsv` enumerating sections). Adjacent versions
2.1.299, 2.1.296 and 2.1.289 are installed; `notes/changelog-2.1.293-2.1.300.md`
names what changed. Real sessions: 5,424 transcripts under
`~/.claude/projects/`.

**Target.** A TypeScript-on-Bun codebase a developer can maintain, edit and
customize, at parity on the harness (not the model). Three properties make
it so, each decided by the reference rather than by taste: the vendored
libraries become package dependencies at the versions the bundle carries,
not reforged source; Anthropic's own code is split into its original
modules, named from the spec and typed under `tsc --strict` with the spec's
schemas as the types' source; and no file exceeds a size the manifest sets
(Prime Intellect's port ended with its largest file near 2,500 lines);
whether each is checked at a unit's landing or at final acceptance follows
from the unit shape (Unit graph, below). The
bundle marks no module boundaries — no source path survives in the reprint,
and only a few hundred lazy-init wrappers delimit anything — so they are
recovered from two facts: a bundler of this kind lays each module's code out
contiguously, and the rebuilt anchors tie spec sections to line ranges; M2
checks the first against the second before the unit graph relies on it. A
new architecture is out of the forge: it is design with taste forks, done
afterwards on the reforged codebase as product work. The bar is checked at
closure by a **customization suite** the manifest writes at M2 — tasks a
maintainer does (add a slash command, change a tool's permission rule, add
a setting, change what the status line shows), each decided by a test —
performed by an agent on the candidate.

**Access.** Every role reads SPEC (its `_inventory` and `_notes`
included), `modules/`, `cli.pretty.js` and `MAP.md`, and runs the binary.
Reading a chunk and rewriting it as readable TypeScript is the expected
method; SPEC gives the names, the intent a minified expression hides, and
the ledger. The scenario therefore does not test SPEC's own replication
criterion — rebuilding without the source — which would need the reference
denied and is a different experiment.

**Parity axes**, in the order they are built: (1) provider-request parity —
a scripted model server at `ANTHROPIC_BASE_URL` records every request body
and answers from a recorded corpus; the request (system prompt, messages,
tools, betas, cache-control placement) is the harness's output and the first
thing compared; (2) headless protocol parity — `-p --output-format
stream-json` and `--input-format stream-json` event streams; (3) on-disk
artefact parity — the `~/.claude/` tree after a scripted session, per the A3
chapter; (4) protocol parity — hook events through a recording hook, MCP
through a recording server, the SDK protocol; (5) static parity — `--help`
trees, settings acceptance and rejection, tool schemas, the command catalog;
(6) TUI frame parity — a pty and a terminal emulator, frames at quiescence.
M3 builds (1), (2) and (3); the others are designed in the manifest and the
matrix marks the ledger items only they cover.

**Verified verifier.** Self-parity: 2.1.300 against 2.1.300 on the built
axes, twice, 100% after normalization. Seeded divergence: 2.1.299 against
2.1.300 must surface the changelog's items that the built axes can see, each
attributed; skipped cases counted. **Corpus**: transcripts replayed — their
user turns fed to both binaries, each executing its own tools in an
identical fixture workspace (the harness runs its own tools; stream-json
input carries user messages, not tool results), the scripted server
answering by position from the recorded assistant turns — so the corpus
measures harness parity under recorded conversations, not a bit-replay of
the original sessions; under held-out, the root's alone. The scripted server
answers **by position** within a session (the nth request gets the nth
recorded response) and records each request's hash for the diff, so one
early divergence does not turn every later request into a miss.

**Ledger.** One row per section of the chapters, from a heading walk over
`SPEC/*.md` (every section, not only the cited ones), with `reference_locus`
from `citation-anchors.tsv` **rebuilt against the pinned reprint first** —
the inventories on disk were built for an earlier bundle and name chunks
that do not exist in this one (1,449 of 1,450) — and every locus validated
against `modules/`; a section with no citation keeps an empty locus and
`uncited` in its note. The spec's own `tools/verbatim.py` and
`checkcites.py` become the rubric's byte-match check.

**Unit graph.** The import graph over `modules/` is acyclic — 2,413 chunks,
198,914 edges, 197 leaves, computed during this spec's review — so
leaves-first is well-founded; but the leaves are tiny vendored modules
(together 1.6% of the bundle), and the core is the opposite:
`chunk-dzn4bwzn.js` at 4.93 MB holds about 9,671 function declarations and
3,155 exports, imports 348 chunks and is imported by 594. An export shim maps
a chunk's exports, and calls inside a chunk never cross it, so a chunk
cannot be split by sections through the shim. The unit of a strangler is
therefore the chunk unless the spike's second question answers yes: can the
hybrid builder strangle **at symbol level** inside a chunk, patching the
chunk's internal bindings to import from the reforged module? If yes, the
core is many units, aligned to chapters through the rebuilt anchors; if no,
the core is one Bun-scale unit, and the shape for it is the feature-reduction
ladder inside that unit while the rest of the graph stays a strangler. The
choice is recorded with the spike's answer, not deferred. It also decides
when structure arrives: with symbol-level strangling the recovered modules
are the units, and the reforge produces them; without it the units are
chunks, the reforge names and types them in place, and a structure phase
after parity splits them into their recovered modules under the same oracle,
the program then being all candidate. The maintainability checks follow the
same answer, and M2 records their phases for both: with recovered-module
units, `tsc --strict`, the spec's names and the file-size cap apply at each
unit's landing; with chunk units, names and `tsc --strict` apply at
landing, while the size cap and the module split apply at final
acceptance, after the structure phase, which is then mandatory before
closure.

**The strangler mechanics**, and its spike. Cross-chunk imports use minified
names, so a reforged module needs a generated **export shim** mapping its
readable exports to the names the unreplaced chunks import
(`_inventory/exports-real-names.txt` is the mapping's seed); the oracle
author generates it, nobody hand-writes it. Before any unit can be proven,
the **zero-replacement hybrid** — the extracted module graph under
`modules/` run by plain `bun`, each `/$bunfs/root/<name>` import rewritten to
the on-disk `modules/<name>` (the extracted names keep the virtual-path
suffixes, so the tree is the mapping; `extract.py` is not run again) and the
embedded assets and native addons reachable — must itself pass self-parity
against the binary. That is a spike with two answers. The first is the hybrid's self-parity:
promote (the strangler holds; units proceed) or discard (the shape falls
back to the feature-reduction ladder,
L0 argument parsing → L1 headless with the scripted server → L2 file and
Bash tools → L3 permissions and hooks → L4 persistence and resume → L5 MCP,
plugins, skills → L6 TUI → L7 the rest, recorded in the manifest with the
reason). The second is symbol-level strangling, above, which decides the
core's unit.

**Rubric additions.** The bundle→TS look-alike list: minifier idioms (`!0`,
comma expressions, folded conditionals), getter and `valueOf` side effects,
property-order dependence, `==` coercions preserved or not, async ordering of
microtasks the reprint obscured. With un-minifying the method, the
mechanical part of this list — the minifier idioms — is a candidate for one
deterministic pass over `modules/` before any unit, proven by the hybrid's
self-parity with every chunk passed through it, which leaves names, types
and structure to the units (the survey: deterministic tools where they
exist); M2 records whether the manifest runs one. The maintainability
bar enters the rubric in the phases the unit shape sets (Unit graph): at
each unit's landing, `tsc --strict` clean for the unit's files with
explicit `any` counted and the spec's names wherever it gives one, and,
for recovered-module units, no file over the manifest's size; for chunk
units the size cap and the module split are checked at final acceptance
instead, since a chunk meets neither before the structure phase splits it.

**Run conditions.** Compute, on the two environments being built beside
this one rather than on machinery of its own: the root and its agent tree
on the 128 GB VM as a **devcloud** host (the 2026-10-15 devcloud design:
Claude Code configured as on the Macs, inference through the gateway,
transcripts mirrored to the central session store), with the target
repository's `devenv/` installing bun, the toolchain and the reference, and
the held-out on that host outside every worktree; verification and `full`
through **ci-kit** on its GCE Spot backend (the 2026-10-15 ci-kit design,
§3a), which records a preemption but does not re-run the job, so the
forge's provider re-runs a gate that failed without its result marker
(§2.7). A verification is a stateless job of minutes (checkout at the head,
build the hybrid, run the slices against the scripted server, diff) and the
work is embarrassingly parallel, which is the load Spot capacity is priced
for; `full` is declared as shard gates and runs one Spot VM per shard. The
forge's gates take the unit from the `ci/` ref's label and the sample's
seed from the nonce commit `ci-gate` creates, so every call draws a fresh
seed without a change to the kit. A gate's round trip through GitHub
Actions and a VM boot is minutes, which fits the verifier step and `full`
but not the implementer's inner loop, which runs the oracle on the root's
host. The reference on the Spot VMs is the Linux build of 2.1.300 with its
expectations re-recorded on Linux, since the macOS binary does not run
there; how the gate obtains it and the corpus — a setup step from a bucket,
or an image built on the kit's runner image — is settled when a run is
planned. The tree's concurrency is set at M2 from the host's cores and the
subagent cap the root raises (§3). Budget: rough calibration from the survey only —
Bun's 535k lines of Zig cost about $165k at frontier prices, Carlini's
100k-line compiler $20k; the product share of this bundle is unmeasured
(vendored React, Ink, mermaid, highlight.js and the SDK are a large fraction),
so M2 measures it from the chunk index before estimating. Stop, escalation
classes and checkpoints per §2.7.

### 7. The toy forge

`tests/forging/toy/`: a TypeScript CLI of three or four modules (argument
parsing, a config reader, a transform, output), bundled with `bun build
--splitting` into a chunked reference, with a short replication-grade spec
written the way the 2.1.300 SPEC is written (verbatim strings, schemas,
exit codes, file formats). Its layout mirrors the scenario's: `setup.sh`
generates a working directory with two siblings — the **worker repository**
(the spec, the oracle's code and slice inputs, and a candidate `src/` of
empty modules in the reference's layout) and the **reference directory**
(`ref/`, `mut/`, `tools/hybrid.mjs`, the expectations), which every role
reads, as the scenario's roles read the bundle; the original TypeScript
stays with the generator, in neither, because the scenario has no original
source to read. The oracle: scripted invocations compared on
stdout, exit code and files written; a held-out set of invocations, which
`setup.sh` writes to a third sibling no role is given; a seeded
divergence (a second build with one constant changed). The strangler: `tools/hybrid.mjs`, a
short build that imports each module from the reference chunk or the reforged
source per `forge/strangler.json`, part of the fixture the way the bundle's
`tools/` are part of the scenario's reference. The whole system runs on it
end to end — Phase 0 and 1 by the skill, the gate, Phase 2 by the root's
agent tree with two units in parallel, closure — at a cost of tens of agent sessions, most at
sonnet. It is the proof that the machinery works and the fixture for the
gaming tests (§M5).

## Acceptance

Observable at the end, each with the milestone that proves it:

1. **The skill produces a manifest.** A general-purpose subagent with no
   context beyond `skills/forging/SKILL.md`, its references, and the toy
   target writes `tests/forging/toy/forge/` with `manifest.md` (sections
   2.1–2.8 present), `ledger.tsv`, `units.json`, `rubric.md`, `oracle/`;
   `forge.py plan` prints its waves. (M1 for the shape, M4 for
   `plan`)
2. **The gate decides.** `forge/gate/verdict.md` for the toy names the
   verdict and the five parts' artifacts exist, the calibration showing the
   reviewer flagged every seeded diff; for the toy the verdict is pass. For
   2.1.300 the verdict names which ledger items the built axes cover and
   which wait on unbuilt axes, with a count of each. (M1 for the toy, M3 for
   the scenario)
3. **The oracle is verified.** For the toy and for 2.1.300: `oracle
   self-parity` prints `100%` on every built axis; `oracle mutation` against
   the seeded or adjacent reference prints the divergences it caught,
   attributed, and `skipped: 0` or an explained count; `oracle stub <unit>`
   on a sampled unit prints the slices that fail under the stub, and none
   pass. (M1 for the toy, M3 for the scenario)
4. **The strangler spike has its two answers.** The scenario manifest's
   Decision Log carries the zero-replacement hybrid's self-parity result with
   `promote` or `discard`, and the symbol-level answer with the core's unit
   shape that follows. (M3)
5. **The tools keep the run's state.** On the toy, without a model:
   `forge.py plan` prints the waves; `worktree <unit> --author` branches a
   unit's author worktree from the integration tip, and `worktree <unit>`
   its implementation worktree from the unit's oracle revision, refusing a
   unit with none — shown on a new unit with no prior publication;
   `publish` commits an author's work as that revision
   only after `stub` shows every slice failing under the stub, and returns
   the names of any that pass, and a kill between its ref move and its
   `done` line is reconciled by the next writer; `verify` runs the unit's slices and a
   fresh-seed sample in a fresh checkout and writes its result record;
   `status` rebuilds each unit's published, verified and landed state from
   git and the records alone, and agrees with a controller's progress file
   or names where it does not; `usage` sums the agents' tokens from their
   transcripts, charging a role's helpers and its retired attempts to its
   unit, and a unit past its cap raises a `budget` event. (M4)
6. **Gaming is caught.** A stub implementer that hard-codes the outputs of
   the slices it ran fails the verifier's fresh sample or the held-out; an
   implementer whose own delta touches `forge/oracle/` or `ledger.tsv` is
   refused at landing with the path named, while the author's own
   extension of a slice landed in that revision passes, and so does a unit
   whose rebase brought in another unit's oracle publication; a candidate
   that imports the chunk its unit replaces fails to build in the hybrid;
   an oracle author whose slices pass under the stub is refused
   publication and returned `MORE_WORK`. (M4 for the stub check, M5 for the
   rest)
7. **Landing holds the tip green.** Two toy units landed in one wave; a
   rebase that changed a diff voided its review and the unit re-entered step
   3; `oracle full` at the wave end prints zero divergences; a `full` fired
   by the interval during an unfinished wave is recorded in `events.jsonl`
   with its result; a seeded divergence landed by unit B that breaks a slice
   unit A owns reopens B at the wave-end `full`, with A's ledger items
   named, and holds the next wave until it is fixed; a published slice of a
   unit still in flight is skipped by the tip's `full` and reported as
   pending; a kill on either side of a landing's ref move is reconciled
   by the next writer or `status`; and a publication concurrent with a
   landing waits on the integration lock, both recorded in order. (M5)
8. **The root protocol and delegator work on seeded events.** Events for
   each escalation class are fed; the delegator resolves the class-1–3 ones
   with the manifest line it used and drafts a question for the class-4 one;
   the wave report has the ledger counts, the gate-miss rate, cost, and
   oracle results. (M6)
9. **The toy forge ends green, through a crash.** The root, run on the toy
   with the real agents, lands every unit; `oracle full` prints zero
   divergences, held-out prints zero, `ledger.tsv` has every row
   `matching`, and `runs/<id>/` holds the cost. Mid-wave the session's
   process is killed and `claude --resume` continues it: the controller and
   its roles resume by SendMessage or are dispatched fresh from their
   progress and branches, no landed work is lost, and no unit lands twice.
   (M7)
10. **Tests, docs, version.** `tests/forging/run-forging-tests.sh` passes;
    the repo map row in `CLAUDE.md` describes the skill, agents and tools;
    the version is bumped with `scripts/bump-version.sh`. (M7)

## Execution

Constraints that bind every milestone: Python scripts are standard-library
only and run under the Python the repo already uses for sminos (3.12+);
shell passes `scripts/lint-shell.sh`; agent definitions follow the
repository's conventions in `CLAUDE.md`'s repo map (model and effort pinned in
frontmatter, `mcp__doperpowers__compact` and `context_usage` withheld,
`AskUserQuestion` disallowed for the detached roles, the reviewer read-only
with `Agent` and `Skill` blocked); the skill carries only what the reading
model cannot derive (the Golden Rule in `CLAUDE.md`), states roles as
ownership and outcomes, and keeps the project's voice; nothing in a
manifest names the held-out path and no environment variable carries it,
since every subagent's shell inherits the session's environment; every
milestone commits as it goes and keeps `Progress` current.

### M1 — The skill: doctrine, manifest shape, oracle patterns, rubric, rigor gate

What exists at its end: `skills/forging/` with `SKILL.md` and the five
references of §5; `agents/forge-reviewer.md`, since the gate's calibration
dispatches the reviewer that will judge units and the toy's gate runs here;
the toy fixture under `tests/forging/toy/`, whose `setup.sh` generates a
working directory of two siblings as §7 says — the worker repository
(`SPEC.md`, the oracle's code, a candidate `src/` of empty modules) and the
reference directory (`ref/` built with `bun build --splitting` from the
original TypeScript the generator keeps, `mut/` the same build with one
constant changed as the seeded divergence, `tools/hybrid.mjs` the hybrid
builder, which leaves a replaced module's chunk out, the recorded
expectations) — and the toy's held-out invocations in a third sibling no
role is given; and,
produced by a subagent reading nothing but the skill and the fixture, the
toy's `forge/` with its oracle (`forge/oracle/run.py` per the contract in
Interfaces), its self-parity and mutation evidence, and its gate record.
Touches: `skills/forging/`, `agents/forge-reviewer.md`, `tests/forging/toy/`. Produces: the manifest shape (`manifest.md`,
`ledger.tsv` columns, `units.json` schema, the status
vocabulary, the report-file convention) in `references/manifest.md` —
consumed by every later milestone under those names. Decisions for this
milestone: the skill's body is Phases 0, 1 and the gate as a path the agent
walks with the human partner (qualify → explore the purpose and the exclusions
with brainstorming's moves → build the oracle and prove its six properties →
ledger → shape and units → rubric → cycle and run conditions → gate), each
step naming its artifact; the doctrine of what a role sees, returns and may
touch lives in the references, so the agent definitions (M4) point to it
rather than restate it; the look-alike lists in `rubric.md` are seeded for
JS→Rust and bundle→TS from the survey and §6, with the instruction to extend
per target; `rigor-gate.md` carries the auditor's brief, the readers'
prompt and the calibration's seeded-diff recipes verbatim, since a dispatch
copies them, and the root dispatches readers and the calibration's reviewer
as subagents; the toy's oracle, strangler shim and hybrid use are the subagent's work from
the skill, and where its output falls short of the contract the executor
fixes the skill's text, not the output, and re-runs the read. Does not
touch: the forge tools, the other agents. Proves: acceptance 1's shape (the dry
read), 2 and 3 for the toy (the readers and the calibration dispatched from
`rigor-gate.md`'s briefs, the `doperpowers:adversarial-reviewer` audit,
`forge/gate/verdict.md`); doperpowers:writing-skills' structure test on the
skill.

### M2 — The 2.1.300 scenario manifest

What exists at its end: `scenario-2.1.300/forge/manifest.md`, `ledger.tsv`,
`units.json`, `rubric.md`, written per M1's shape against
the bundle, with the spike question and the compute and budget sections
stated. Touches: `docs/doperpowers/research/2026-10-15-compile-class-work/scenario-2.1.300/`.
Consumes: the manifest shape. Produces: the scenario's ledger and unit graph,
consumed by M3. Decisions: first, the inventories are rebuilt against the pinned
reprint — `tools/sections.py build` and `tools/anchors.py build` in the
bundle, run under the Python those tools declare — and every locus is
validated against `modules/`, with the count that fail recorded in the
manifest's Surprises; the ledger's rows come from a heading walk over
`SPEC/*.md`, with `reference_locus` from the rebuilt anchors and uncited
sections kept and marked — a script under `scenario-2.1.300/tools/` derives
them so the ledger is regenerable; `spec_paths` in the manifest's Target
section names `SPEC/`; whether a deterministic de-minification pass runs
before the units is decided from a trial on a sample of chunks and recorded
(§6); the unit graph is chapter-aligned chunk groups over the ESM
import graph (`modules/` imports), leaves first, with the many-chapter chunks
handled by a rule the milestone picks from the data and records (split by
section, or first-needing unit); the product share of the bundle is measured
from `CHUNK-INDEX.md` (vendored chunks identified by their fingerprints) and
the budget section gives a range from the survey's calibration against that
share; each vendored chunk is matched to the published package and
version it carries and becomes a dependency of the target, not a unit; the
contiguity of original modules is checked against the rebuilt anchors and
each chunk's candidate module boundaries recorded in `units.json` for the
spike's symbol-level answer to use; the maintainability bar (§6) is
written into the Target section and the rubric with the phase of each
check — at unit landing or at final acceptance — recorded for both unit
shapes, since the spike that picks between them is M3's (recovered-module
units: `tsc --strict`, names and the file-size cap at landing; chunk
units: names and `tsc --strict` at landing, the size cap and the module
split at final acceptance after the then-mandatory structure phase), and
the customization suite — its tasks and the test that decides each —
into the closure section; the manifest's caution paragraph (§6) is present. Does not touch: the
oracle harness, which is M3. Proves: the manifest's sections per acceptance 1
(for the scenario), reviewed by a self-review against M1's shape.

### M3 — The scenario's oracle harness, the strangler spike, and the gate record

What exists at its end: `scenario-2.1.300/forge/oracle/` with the scripted
model server, the runners for axes (1), (2) and (3), normalization, slices,
the fast-sample spec; self-parity and mutation evidence under `forge/gate/`;
the spike's verdict in the manifest's Decision Log; the gate run (decision
ledger, matrix, three readers on two units with one at opus, the judge
calibration, the adversarial-reviewer audit) and `forge/gate/verdict.md`. Touches: `scenario-2.1.300/forge/oracle/`,
`forge/gate/`, `manifest.md`. Consumes: the scenario's ledger and unit
graph. Decisions: the scripted server is a small Python HTTP server speaking
the Messages API's streaming shape, started by the oracle per slice run on a
fresh port so that position is the count of requests that server has seen,
answering the nth request with the nth recorded response and recording each
request's normalized hash for the comparison (a changed request still gets
its positional answer and its difference is still reported), the corpus
captured once from the real provider with the user's own account (the
recording run is the one model-spending step; it is sized to the slices, not
the corpus); normalization is defined by the
self-parity runs as §2.2 says; the spike runs before any slice is written for
a unit and answers both of §6's questions — the zero-replacement hybrid
under plain `bun`, `forge/oracle/hybrid.py`
rewriting each `/$bunfs/root/<name>` import to the on-disk `modules/<name>`
(the extracted tree is the mapping; `extract.py` needs Python 3.14 and is
not run), then a symbol-level strangle of one function of the core chunk —
and its two answers decide whether `units.json` keeps the strangler shape or
the ladder, and whether the core is many units or one (M2's graph is revised
in place, with the Decision Log line); the mutation run is 2.1.299
against 2.1.300 with the changelog's items as the expected catches; held-out
is a set of scripted sessions and a transcript-replay sample at a path
outside the repository that the root passes to `oracle heldout --path`,
written by this milestone, never committed and named in no file or
environment variable. Does not touch:
axes (4)–(6), which the matrix marks unbuilt. Proves: acceptance 2 (the
scenario's verdict), 3 (self-parity and mutation for 2.1.300), 4 (the spike).

### M4 — The forge tools: plan, worktrees, oracle drivers, stub check, publication, verification, status

What exists at its end: `forge.py` with `plan`, `worktree <unit> [--author]`,
`oracle fast|full|heldout|self-parity|mutation|stub` as thin drivers over
`forge/oracle/`'s runner interface, `publish <unit>`, `verify <unit>`,
`status`, `usage`, and their tests on the toy. Touches:
`skills/forging/scripts/forge.py`, `tests/forging/`. Consumes: the
manifest shape. Produces: the tools' command surface and the records'
schemas (Interfaces). Decisions: no tool calls a model, so every one is
tested without one; `plan` computes waves by topological order over
`consumes`; `worktree <unit> --author` creates the author's worktree on a
branch from the integration tip, and `worktree <unit>` creates the
implementation worktree at the unit's published oracle revision or resets
it there, refusing a unit with no publication (a test takes a new unit
with no prior publication from `--author` through `publish` to its
implementation worktree and sees it start at the oracle revision); the
**stub check** is `oracle stub <unit>` then `compare`, and `publish`
refuses work whose slices pass under the stub, naming them, re-runs
self-parity and mutation when the author's diff touched `forge/oracle/`,
and, under the integration lock — a file under `forge/runs/` that `land`
and `full` take in M5 — reconciles any pending intent, replays what
passes onto the integration tip (a conflict returns it to the author), and
moves the ref between a `publish` operation's `intent` and `done` lines in
`integration.jsonl`, the `done` naming the unit's oracle revision (a test
kills it between the ref move and the `done` line, and the next writer
reconciles); `verify` takes a fresh
checkout at the unit's head, runs the unit's slices and a `fast` sample on a
seed it draws, applies the path check (§M5), and writes a result record
under the unit's run directory, through the manifest's sandbox provider
(`local` here; `ci-kit` is the scenario's, designed with §2.7's retry
rule and not built);
`oracle` subcommands call `forge/oracle/run.py` with a fixed argument
contract (`<axis> <binary> <slice>` → a directory of observations,
`normalize`, `compare` → a summary line and a detail file) so the harness
is per target and the driver is not; `oracle heldout` takes the held-out
path only as `--path <p>` on its command line, never from the manifest or
the environment, and refuses a path inside the repository; `status`
derives each unit's published, verified and landed state from git and the
records, and reports where a progress file disagrees; `usage` sums
`message.usage` from the session's transcripts per agent and charges each
transcript to its nearest ancestor a progress file names, walking the
sidecars' `parentAgentId` (SPEC 18 §18.25.2), so a role's helpers count
against its unit and the root's and the controllers' own usage counts in
the run total as overhead, raising a `budget` event at the manifest's
thresholds (tests: a helper whose usage crosses its unit's cap raises the
`budget` event; a re-brief followed by a restart keeps the retired role's
usage on its unit). Does not touch:
landing (M5), the agents (M6). Proves: acceptance 5.

### M5 — Landing, `full` at the tip, ledger updates, gaming tests

What exists at its end: `forge.py land` and `full`, ledger `status`
updates on landing and at `full`, and the gaming tests. Touches:
`skills/forging/scripts/forge.py`, `tests/forging/`. Consumes: the tools'
surface. Decisions: `land` and `full` take M4's integration lock, so
controllers publishing and landing at once are serialized (a test runs a
publication concurrent with a landing and sees one wait for the other,
both recorded in order);
review validity is bound to the reviewed head's tree hash, so a rebase that
changes the diff voids it; the tip check samples on a fresh seed; a
unit's hybrid leaves the unit's reference chunk out of the build, and a test
has a candidate import it and fail to build; the tip's suite is the slices of landed units (a published slice for a
unit still in flight runs in that unit's verifications only, and `full` at
the tip reports `pending: k slices`; a test marks a unit pending with a
slice that fails at the tip and sees it skipped); a `full` or held-out
failure after landing is attributed by a bisect over the wave's landings
from the last green tip, writes a `reopened`
event naming the landing that caused it and the ledger items that broke,
moves that unit to `reopened`, and `status` reports the tip red so no
controller dispatches while it is (a
test has unit B's landing break a slice unit A owns, and B reopens; another
interleaves two units' publications and landings and sees both land); the
fast-forward writes a `land` operation's `intent` line with the old and
new tips before the ref moves and its `done` line after, and every writer
and `status` reconcile a pending intent as §3 says, with kills on both
sides of the ref move in the tests; the tools move ledger `status`
from slice results at landing and at `full`, and any role diff touching
`ledger.tsv` is refused; the verifier's path check compares the implementer's own delta
(`onto..head` of the latest rebase, the `onto` recorded at `rebase-start`;
the oracle revision kept for provenance only) against `forge/oracle/**` and
`ledger.tsv`; `full` runs under the integration lock, commits its ledger
update as a `full` operation of `integration.jsonl`, writes a `full` event
with the result and a `tip-failure` event per divergence, and is what a
controller runs after the manifest's count of landings and at its wave's
end, while held-out stays the root's to run. Does not touch: the agents.
Proves: acceptance 6 and 7, on the toy with scripted candidates and the
toy's oracle.

### M6 — The agents and their protocols: controller, roles, root, delegator

What exists at its end: `agents/forge-controller.md`,
`forge-oracle-author.md`, `forge-implementer.md`, `forge-delegator.md` (the
reviewer is M1's); `references/controller-protocol.md` and
`references/root-protocol.md`; `forge.py report`; a seeded-events test of
the delegator's resolutions and the report's format. Touches: `agents/`,
`skills/forging/references/`, `skills/forging/scripts/forge.py` (`report`
only), `tests/forging/`. Consumes: the tools' surface, `events.jsonl`, the
progress-file schema. Decisions: the protocols are operator manuals in the
style of `issue-tracker/references/review-loop.md`, not skills — the
controller's: worktrees, dispatching and resuming roles, the mechanical
steps in their order, re-planning within a wave, the progress file, what
returns to the root; the root's: start and resume, waves and controllers,
folding reports and events, re-planning, process fixes, held-out, reports,
closure; each agent definition pins its model (controller opus/high, oracle
author opus/high, implementer opus/high and downgradable per unit,
delegator opus/high), withholds the compaction tools and
`AskUserQuestion`, and points to the protocol or the references for its
contract rather than restating it; the controller and the roles keep
`Agent` for fan-out; the delegator reads `manifest.md` and the event and
returns either a resolution with the manifest line it rests on or a drafted
question with alternatives and a recommendation; the wave report is a fixed
set of lines (units landed and remaining, ledger counts by status, `full`
and held-out results, cost to date, escalations open) so the human reads
the same shape every wave. Does not touch: the tools beyond `report`.
Proves: acceptance 8.

### M7 — The toy forge end to end, docs, version

What exists at its end: the toy forged by the real roles, the acceptance
walk, the repo map row, the version bump. Touches: `tests/forging/toy/`,
`CLAUDE.md`, the manifests `bump-version.sh` lists. Consumes: everything.
Decisions: the toy run uses sonnet for the implementer and the readers and
the pinned models elsewhere, with `max_rounds` 3 and `parallel` 2, and one
kill of the session's process mid-wave followed by `claude --resume`; the run's
cost is recorded in the spec's retrospective; this milestone spends model
usage (tens of sessions) and the human partner is told the estimate before it
starts. Proves: acceptance 1 (with `plan`), 2 (the toy's verdict), 3 (the
toy's self-parity), 9, 10, and executes the whole Acceptance section as
written.

## Concrete Steps

Working directory is the repository root unless stated.

- M1: `tests/claude-code/run-skill-tests.sh` (the structure test picks up
  the new skill); `tests/forging/toy/setup.sh /tmp/toy` → `/tmp/toy/work`
  (the worker repository), `/tmp/toy/reference` and `/tmp/toy/heldout`; a
  dry read: dispatch a
  general-purpose subagent with "Read `skills/forging/SKILL.md` and its
  references; the target's spec is `/tmp/toy/work/SPEC.md`, its reference
  `/tmp/toy/reference/ref/`; produce
  `/tmp/toy/work/forge/` per the manifest reference" and inspect
  `ls /tmp/toy/work/forge/` → `manifest.md ledger.tsv units.json rubric.md oracle gate`.
- M2, M3 (in `docs/doperpowers/research/2026-10-15-compile-class-work/scenario-2.1.300/`):
  `python3 -I tools/ledger.py` → `ledger.tsv` with its row count printed;
  `python3 -I forge/oracle/run.py self-parity --axis provider-request` →
  `self-parity provider-request: 100% (N slices, skipped: 0)`;
  `python3 -I forge/oracle/run.py mutation --against ~/.local/share/claude/versions/2.1.299` →
  `mutation: caught K/K changelog items on built axes; skipped: 0`;
  `python3 -I forge/oracle/hybrid.py --zero-replacement && python3 -I forge/oracle/run.py self-parity --candidate forge/.hybrid/cli` →
  the spike's number; the gate: the readers dispatched as subagents from `rigor-gate.md`'s brief
  on U1 and U2 (lists under `forge/gate/readers/`), the calibration's
  reviewer on the seeded diffs (`forge/gate/calibration/`), then the
  adversarial-reviewer dispatch with the auditor's brief; `cat forge/gate/verdict.md`.
- M4, M5, M6: `tests/forging/run-forging-tests.sh` → every test's name and
  `ok`; `python3 -I skills/forging/scripts/forge.py plan tests/forging/toy/forge` →
  `wave 1: U1 U2` / `wave 2: U3`.
- M7 (an interactive session opened in `tests/forging/toy/` with this
  checkout as its plugin): the root protocol run on `forge/` with `parallel`
  2 → the wave reports and `landed U1 U2 U3`; mid-wave, the session's
  process killed, then `claude --resume <session>` → the tree continues, and
  `python3 -I ../../../skills/forging/scripts/forge.py status forge` → every
  unit `landed` once; `… forge.py oracle full forge` →
  `full: 0 divergences (N slices, skipped: 0)`; `… forge.py oracle heldout --path <held-out> forge` →
  `heldout: 0 divergences`; `scripts/bump-version.sh <next>`.

## Interfaces and Dependencies

Defined once here; milestones point at them.

- **Manifest shape** (M1, `references/manifest.md`): the directory of §2;
  `ledger.tsv` columns as §2.3; `units.json` as an object `{ "units": [ {
  "id", "title", "ledger": [], "touches": [], "reference_locus": [],
  "consumes": [], "produces": [], "slices": [], "max_rounds", "models": {}
  } ], "run": { "parallel", "budget": { "unit_tokens", "run_tokens",
  "prices": {} }, "full_every_landings", "sandbox_provider": "local", "infra_retries" } }`;
  the manifest's Target section carries `spec_paths` and the reference
  paths; a
  role's report is its final message, its first line one of `DONE`,
  `MORE_WORK`, `BLOCKED`, `INFEASIBLE`, `ERROR`.
- **Oracle runner contract** (M1 for the toy, M3 for the scenario; M5's
  driver; the oracle's code and slice inputs in the repository, the recorded
  expectations outside it at `FORGE_EXPECTED`): `forge/oracle/run.py <axis> run <binary> <slice> <outdir>`,
  `… normalize <outdir>`, `… compare <expected> <actual>` → one summary line
  on stdout (`<axis> <slice>: <n> divergences, skipped: <k>`) and a detail
  file, and `… stub <unit> <outdir>` builds the candidate with the unit's
  module stubbed; `self-parity`, `mutation --against <ref>`, `fast --seed
  <n>`, `full`, `heldout <path>` compose these.
- **Forge tools** (M4, M5, `report` in M6): `forge.py
  plan|worktree <unit> [--author]|oracle <sub>|publish <unit>|verify <unit>|land <unit>|full|status|usage|report
  <forge-dir>`, `oracle heldout` taking `--path <p>`. **Records**:
  `runs/<id>/units/<unit>/verify/<n>.json`
  `{ "head", "seed", "slices", "result", "detail" }`;
  `runs/<id>/integration.jsonl`, the integration log, appended under the
  integration lock by every write to the integration branch, lines
  `{ "op", "unit", "kind", … }` with `op` in `publish | land | full` and
  `kind` in `rebase-start {onto} | review-void | tip-check | intent {old,
  new} | done {new}` — a publication's `done` names the unit's oracle
  revision, and `full`'s ledger update has no unit; `events.jsonl` lines
  `{ "ts", "unit", "kind", "detail" }` with `kind` in `escalation |
  infeasible | tip-failure | heldout-failure | reopened | budget | full |
  gate-miss`. **Progress files**, written by the agents and rewritten, not
  appended: `runs/<id>/progress.md` (the root's: waves, controllers and
  their agent ids, escalations open) and `runs/<id>/waves/<w>.md` (each
  controller's: per unit its state, attempt, head, review head, and every
  agent id the unit has had, by role and attempt, retired ones kept, which
  is what `usage` charges to the unit). **Unit states**, as the controller records them
  and `status` checks them against git and the tools' records: `planned →
  authored` (author `DONE` in its author worktree, the publication's `done`
  line written, the implementation worktree created at the oracle
  revision); `authored → authored` (the
  stub check failed, author `MORE_WORK`); `authored → implemented`
  (implementer `DONE`); `implemented → judged` (reviewer `DONE` and a
  passing `verify` at the same head); `implemented → implemented` (either
  `MORE_WORK`, `attempt + 1`, while `attempt ≤ max_rounds`); `judged →
  landed` (the `done` line); `judged → implemented` (`review-void` or a
  failed `tip-check`); `landed → reopened` (a `full` or held-out failure
  attributed to the unit) and `reopened → implemented`; any role `BLOCKED`
  or `INFEASIBLE`, or `max_rounds` exceeded, → `escalated` with an event.
  **Linearization points**: a unit is published, or landed, when the
  integration ref moves (`git update-ref`, atomic, under the integration
  lock), bracketed by its operation's `intent` and `done` lines, which the
  next writer or `status` reconciles; a role's outcome counts once the
  controller has written it to its progress file, and a role whose outcome
  is not written is resumed by SendMessage or dispatched again.
- **Sandbox provider contract** (M4 builds `local`; `ci-kit` is designed
  here and not built): `verify` and `full` hand the provider a head and the
  oracle's command and get back the result record; a provider changes where
  the run happens, never the runner contract. A gate writes a result marker
  when the oracle completes; a failed gate job with no marker is an
  infrastructure loss, which the `ci-kit` provider re-runs on the same head
  up to `run.infra_retries` and then records as an `escalation` event with
  status `ERROR` — never `MORE_WORK`, never a round (§2.7).
- **Agents** (M6, the reviewer M1): `doperpowers:forge-controller`,
  `forge-oracle-author`, `forge-implementer`, `forge-reviewer`,
  `forge-delegator`, dispatched through the Agent tool.
- **Dependencies**: `claude` ≥ 2.1.300 for a stopped subagent's resume
  from its transcript by SendMessage and the nesting and concurrency caps
  (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3;
  `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, default 20; SPEC chapter 18); `bun` for the toy and the scenario; Python 3.12+ for this
  repository's scripts (the bundle's own tools declare theirs; `extract.py`
  needs 3.14 and is never invoked by this work).

## Surprises & Discoveries

- Observation: the 2.1.300 bundle marks no original module boundaries: the
  reprint holds no source path string, and the lazy-init wrapper pattern
  (`<name> = <helper>(() => {`) occurs on 388 lines against 54,245
  top-level functions; the core chunk carries a handful. Module recovery
  therefore rests on code contiguity and the spec's anchors (§6).
  Evidence: `grep -c` over `cli.pretty.js` and `modules/chunk-dzn4bwzn.js`,
  2026-10-16.
- Observation: the harness persists every subagent's transcript under the
  session's `subagents/` directory with a metadata sidecar and resumes a
  stopped or evicted agent from it by SendMessage, refusing only named
  cases (a transcript too large to load, a rejected working directory, an
  agent the user stopped); subagent nesting defaults to depth 3 and
  concurrency to 20, each raised by an environment variable. Evidence:
  SPEC chapter 18 §18.25 and the depth and concurrency subsection;
  chapter 4's rows for `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` and
  `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`.

- Observation: the scenario's spec is 404,213 lines over 57 chapters, not
  the ~14,000 the brainstorm assumed, and was itself produced by an
  orchestrated pool of about fourteen chapter authors with review rounds.
  Evidence: `wc -l SPEC/*.md` → 404213; `SPEC/_notes/00-orchestration.md`.
- Observation: the bundle's `SPEC/_inventory/section-index.tsv` and
  `citation-anchors.tsv` were built for an earlier bundle: of the 1,450
  chunk names they cite, one exists under `modules/`. Evidence: the
  adversarial review of this spec, 2026-10-15, confirmed by
  `comm -12 <(cut -f4 section-index.tsv | cut -d: -f1 | sort -u) <(ls modules | sort) | wc -l` → 1.
- Observation: the chunk import graph is acyclic with 197 leaves that are
  tiny vendored modules, and one core chunk that a shim cannot split.
  Evidence: the design review of this spec, 2026-10-15, computed from the
  imports under `modules/`: 2,413 chunks, 198,914 edges, leaves 756 KB of 46
  MB; `chunk-dzn4bwzn.js` 4.93 MB, about 9,671 function declarations, 3,155
  exports, imports 348, imported by 594.
- Observation: the strangler shape depends on the extracted module graph
  running under plain `bun` with parity, which nothing has tested.
  Evidence: `cli` imports `/$bunfs/root/chunk-*.js` virtual paths (the
  anchors' first rows); recorded as M3's spike.

## Decision Log

- Decision: Verification for this work — one independent spec review by a
  general-purpose subagent (model fable) on the design (§1–§7 against the
  survey's principles and contradictions), and the
  `doperpowers:adversarial-reviewer` agent's buildability review of the
  execution section in the same round; the whole-branch review at
  `doperpowers:reviewer-high` (the runner and the role contracts are what a
  weeks-long run stands on). A critique debate was not held: the design was
  argued with the human partner directly over four rounds against the
  survey.
  Date/Author: 2026-10-15 (the root session, per the human partner's approval)
- Decision: The verifier is a runner step, not a model (the presentation
  named a "verifier agent").
  Rationale: §5. Serves the approved role's intent — a fresh environment that
  cannot be argued with — at lower cost.
  Rejected: a haiku-pinned agent that runs the scripts and reports — a model
  in the loop that gains nothing over the script and can be persuaded.
  Date/Author: 2026-10-15
- Decision: The runner dispatches headless `claude -p --agent` sessions, not
  subagents of the root, and is a standalone Python process.
  Rationale: §5 — isolation is a process property; a days-long loop belongs
  outside a model's context.
  Rejected: the Workflow tool (determinism constraints on shell work;
  in-session); plan-executor over subagent-driven-execution (one shared
  worktree, sequential, the loop in a model's context).
  Date/Author: 2026-10-15
- Decision: After the first adversarial review (2026-10-15), eight changes:
  the scenario rebuilds the bundle's inventories before deriving the ledger,
  and the ledger comes from a heading walk, not the citation index; the
  runner has one state writer and per-unit journals, with the transition
  table and linearization points in Interfaces and kills at every boundary
  in the tests; a tier-B role's settings must enable a fail-closed sandbox
  (the sandbox is off by default and falls back to unsandboxed execution),
  proven by a live check; the runner loads its own checkout with
  `--plugin-dir` and preflights every role, since the harness only warns on
  an unknown agent; a role's report is its final message, persisted by the
  runner, so the read-only reviewer needs no write; the implementer reads a
  staged copy of the spec so the whole reference tree can be denied; the
  strangler spike reads the extracted tree, not a record table `MAP.md` does
  not hold; the run controls (budget, `full` interval, turn limits) are
  manifest fields the runner enforces, with tests.
  Rationale: each was a gap an executor would have had to guess across, and
  two (the stale inventories, the sandbox defaults) would have made a
  milestone's proof false.
  Date/Author: 2026-10-15
- Decision: After the independent design review (2026-10-15), twelve
  changes: the implementer's inner loop is a verify request the runner
  serves in the verifier's environment on a fresh sample, and it may read
  the oracle's code but not the expectations; the strangler's unit is the
  chunk unless the spike's second question (symbol-level strangling) answers
  yes, and §6 says what follows either way instead of deferring to M2; the
  corpus replays user turns with both binaries executing tools in identical
  fixtures, since the harness runs its own tools; the oracle author's slices
  are checked by a stub check when it returns and any oracle change re-runs
  self-parity and mutation; the gate's claim is a sampled rate with one
  reader at the implementer's rung, and invariance is measured in the run as
  the gate-miss rate with a bound that is an escalation class; samples are
  drawn fresh so memorizing one buys nothing; a post-landing failure reopens
  its unit, attributed through the ledger or by bisect, and holds dispatch
  while the tip is red; the ledger is written by no role; a further round
  resumes the role's session; the readers' script is cut (the root dispatches
  them as subagents) and the delegator's reason is written; shape (d) is out
  of this version; `run` executes one wave and the root loops, with the
  split's costs named; judge calibration on seeded diffs joins the gate;
  the scripted server answers by position; a `triaged` entry is an
  escalation class; every oracle run gets a fresh HOME.
  Rationale: the review's findings 1, 2, 5, 7 and 8 were defects an
  executor could not have repaired — a tier that could not build or test,
  a unit the shim could not cut, a gate condition empty in a strangler, a
  landing a memorizer passes, a failure with no state; the rest were
  simplifications or measurements the design claimed without supplying.
  Date/Author: 2026-10-15
- Decision: After the third review round (2026-10-15, consistency after
  the folds), nine changes: a verification has a candidate side and a
  reference side, the response is capped and redacted by fingerprint, and
  the fingerprint check flags reference text in a diff; protected artifacts
  never enter a worker repository's history (the toy's reference and
  expectations move to a sibling directory, expectations to
  `FORGE_EXPECTED`), and the live check probes `git show`; the author's
  passing work is published as the unit's oracle revision and the
  implementer's diff is measured from it; samples are drawn without
  replacement from a per-unit pool with an exposure set, exhaustion
  answered by `full`, and the anti-memorization claim narrowed to what
  that guarantees; the reviewer agent moves to M1 so the gate calibrates
  the judge that will run; the scripted server answers by position, one
  server per slice run; post-landing attribution is a bisect from the last
  green tip, the ledger naming what broke, not who; landing writes intent
  and done around the ref move and a resume reconciles them; a session
  ending without a result is `ERROR` with the harness's variant, retried
  once per policy.
  Rationale: each was a hole the previous fold opened or left — the
  verify request as an exfiltration route, the shared object store, the
  author's changes failing the implementer's guard, a seed that does not
  mean unseen, a judge calibrated before it existed.
  Date/Author: 2026-10-15
- Decision: After the fourth review round (2026-10-15, scoped to the
  third fold), four changes, and the review is closed: the implementer's
  guarded delta is `onto..head` of its latest rebase, never the aggregate
  from its oracle revision (another unit's publication or landing enters
  that aggregate legitimately); a published slice joins the tip's suite
  only when its unit lands; the toy's original source lives in the
  protected directory and the worker repository gets empty candidate
  modules; and the isolation claim is narrowed in §2.2 — in a shared-realm
  shape a candidate built to leak what it links cannot be walled off
  without ending the strangler, so the design deters the recorded threat
  (drift toward the reference) with bounds, the reviewer's rubric and the
  fingerprint check, and the human partner accepts that residual at the
  gate or chooses another shape. The next review round would be adjudicating
  that residual, which is the human partner's call, not a reviewer's.
  Rejected: process- or realm-separating the candidate from the reference
  chunks — it ends the strangler's whole-program oracle, the reason for the
  shape.
  Date/Author: 2026-10-15
- Decision: The verifier's and the oracle's runs go to a sandbox provider
  the manifest names (`local` | `vm` | `ephemeral`), with the oracle runner
  contract unchanged across providers; this spec implements `local` and
  defines the interface, and the scenario names `ephemeral` for verify and
  `full`.
  Rationale: the human partner's question (2026-10-15) whether a per-run
  serverless sandbox beats one self-hosted runner for verification. It does
  for this workload: a verify is stateless and minutes long, the work is
  embarrassingly parallel, and a fixed host serializes it once saturated;
  Prime Intellect ran over 10,000 microVM sandboxes for exactly this. Cold
  start is the cost, and a prebaked image with the toolchain, the reference
  and the corpus makes it seconds; for a compiled target a snapshot-restoring
  microVM provider keeps the warmed build directory, which a container job
  service cannot. The roles stay on the VM: they are long-lived sessions
  with worktrees, not jobs.
  Rejected: implementing a provider now — no run is planned, and the toy
  needs only `local`.
  Date/Author: 2026-10-15 (the human partner's question; the root's design)
- Decision: Milestone order puts the scenario (M2, M3) before the runner
  (M4–M7).
  Rationale: the human partner's priority is the simulation; M2 and M3
  depend only on M1's shape; execution can stop after M3 without leaving
  half a runner.
  Date/Author: 2026-10-15
- Decision: The leak deterrents read every tree a verify request ran: a
  submission must descend from every head the unit's verify requests ran
  since its last brief, and the reviewer reads the delta commit by commit.
  Rationale: found while explaining the shared-realm residual to the human
  partner (2026-10-16): the reviewer saw only the aggregate diff, so leak
  code could run in an intermediate verified head and be rewritten out of
  history, or deleted in a later commit, before the reviewer looked. The
  request files already record each verified head, so the check is one
  ancestry test per submission.
  Rejected: scanning every verified tree with a separate reviewer pass —
  the same coverage at a reviewer's cost per request, where ancestry plus
  the commit-by-commit read costs nothing extra.
  Date/Author: 2026-10-16
- Decision: The decomposition above the unit is data in the manifest, not
  a layer of sessions. The ledger (what must be proven, from the spec's
  sections) and the unit graph (what changes, from the reference's
  structure) are built once in Phase 1; the per-unit authoring that a
  composite process gives to child documents and their reviews is the
  oracle author's, run in parallel by the runner and checked by the stub
  check; the root is the planner that recurses on demand — a unit too large
  for one implementer (the scenario's core chunk) or stuck past
  `max_rounds` is split inside the same graph. An orchestrator session over
  architect seats belongs to a program of several designs, where a forge is
  one seat's execution engine, not inside a forge.
  Rationale: the human partner asked (2026-10-16) whether the MAWS process —
  one architect's composite spec, adversarially reviewed children with
  their own execution documents, plan-executor waves — holds at 2.1.300's
  scale, or needs an orchestration layer over parallel architects. In
  compile-class work the specification is an input (SPEC/, 404,213 lines),
  so child documents would restate it; document reviews do not compose (the
  2026-10-09 ruling: 79 defects after every child reviewed clean) while the
  tip check and `full` do; and the cases at this scale ran flat under one
  up-front design — Bun's Zig→Rust port (one PORTING.md and LIFETIMES.tsv,
  then 1,448 files through one cycle) and Prime Intellect's (a root and a
  per-task planner, 1,981 agents). Recursive planners appear in the case
  without a reference (Cursor's browser), whose output is disputed.
  Rejected: architect seats per chapter under an orchestrator session —
  57 sessions re-specifying a replication-grade spec in prose, checked by
  document review instead of by the oracle. Deferred: a root of roots,
  should one root's escalation load prove too much — Reboot's manager grew
  unreliable as its objective grew; no run measures it yet, and the core
  chunk (imported by 594 chunks) means the graph does not partition into
  independent regions.
  Date/Author: 2026-10-16 (the human partner's question; the design session's answer)
- Decision: Every role reads the reference — the binary, the extracted
  bundle, the reprint — and the recorded expectations, and may run the
  reference; un-minifying the reference module under the spec's names is a
  legitimate method; what deceives the verification is named to the roles
  as prohibited, beside the honest exit; the only things kept out of reach
  are the held-out (no role is given its path) and, in a strangler, the
  chunk a unit replaces (absent from that unit's hybrid build). Removed with
  it: the tier-B read denials and the fail-closed sandbox they needed, the
  staged spec copy, the verify request protocol and its exposure sets (the
  implementer runs the oracle itself; the runner draws a fresh seed for
  each of its checks), the two-sided verification with redaction, the
  fingerprint check against reference text, the live isolation check, and
  the ancestry check of the entry two above. §2.2's shared-realm residual no
  longer exists: nothing is hidden that a candidate could leak.
  Rationale: the human partner's correction (2026-10-16). They never asked
  that the implementer see only SPEC; the denial was this spec's reading of
  SPEC's own replication criterion, turned into an access rule. Reading the
  reference is how every port on record worked (Bun, Prime Intellect, the
  TypeScript-to-Go port), and the recorded failures were calling the
  reference (Reboot, Carlini's compiler), not reading it. Current models do
  not build covert channels around a stated prohibition when an honest exit
  exists (ImpossibleBench: the abort path alone cut cheating from 54% to
  9%), and the most recent run, Prime Intellect's, relied on role
  separation and a fresh-sandbox verifier, not read walls. What stays is
  what catches honest error, which recent runs still show: the scripted
  verifier, the cross-model reviewer, the held-out, the path guard on the
  oracle and the ledger — Bun's agents stubbed failing functions behind
  long justifying comments, and its green CI on six platforms shipped 19
  regressions from look-alike code.
  Rejected: keeping the denials so the scenario also tests whether SPEC
  alone suffices — a different experiment from the reforge the human
  partner wants; a later run can deny the reference again.
  Date/Author: 2026-10-16 (the human partner's correction)
- Decision: The run is a tree of subagents, not a script driving headless
  sessions: the root dispatches a controller per wave, the controller
  dispatches each unit's roles and resumes them by SendMessage, every level
  fans out as its reading demands, and the tree's shape is the agents' to
  adapt. The mechanical steps stay scripts the agents call (`forge.py`:
  worktrees, stub check, publication, verification, landing, `full`,
  status, usage). State lives in the agents' transcripts, git, and the
  forge's records and progress files; a crash is resumed by `claude
  --resume` and SendMessage down the tree, or by fresh dispatch from the
  progress files and branches where the harness refuses a resume.
  Rationale: the human partner's direction (2026-10-16): scripted
  orchestration is inefficient and weak at situational handling; work on a
  spec and binary this large needs flexible fan-out for context
  efficiency, so the subagent tree must be dynamic; and it must be
  doperpowers's own pattern — an agent dispatching subagents from a skill
  or instructions — with every agent's state on disk and resumable. The
  harness supports it: transcripts persist and a stopped agent resumes from
  its own (SPEC 18.25); the default depth of 3 fits root, controller, role
  and fan-out. The headless runner's main reason was gone already: it made
  each role's read denial a process boundary, and the read denials were
  removed in the entry above.
  Rejected: the headless runner (`forge-run.py` with `claude -p` per role) —
  a fixed state machine handles only the transitions it encodes and turns
  every unforeseen case into an escalation; the Workflow tool, for the same
  reason. Accepted cost: the tree lives in one process, so a crash stops
  every agent at once and each resumes from its transcript; partitioning
  across sminos seats waits until a run shows one process too small.
  Supersedes: the 2026-10-15 entries on the headless runner, the
  verifier as a runner step, and per-role settings files.
  Date/Author: 2026-10-16 (the human partner's direction)
- Decision: Verification and `full` run through ci-kit (`ci-gate` on its
  GCE Spot backend), and the root's host is a devcloud host; the sandbox
  providers are `local` and `ci-kit`.
  Rationale: the human partner's direction (2026-10-16): verification
  runs on GCE Spot instances, not a serverless service, and two initiatives
  already in progress own the pieces — ci-kit the remote sandbox for
  verification and CI, with a measured GCE Spot backend (one VM per job,
  preemption handled), and devcloud the cloud host that runs Claude Code as
  the Macs do. The forge consumes both instead of building a pool of its
  own.
  Rejected: a forge-owned Spot pool behind a `gce-spot` provider — a second
  copy of what ci-kit builds; and the 2026-10-15 `ephemeral` provider,
  superseded by the human partner's choice.
  Date/Author: 2026-10-16 (the human partner's direction)
- Decision: The reforge's target is a codebase a developer can maintain,
  edit and customize, and that requires structure as well as names and
  types — recovered, not redesigned: vendored libraries become dependencies
  at the versions the bundle carries, Anthropic's code is split into its
  original modules (recovered from code contiguity and the spec's anchors),
  typed under `tsc --strict`, with a file-size cap; the bar is checked at
  closure by a customization suite written at M2. With symbol-level
  strangling the recovered modules are the units; without it a structure
  phase follows parity under the same oracle.
  Rationale: the human partner's answer (2026-10-16) — "a maintainable,
  editable, customizable codebase" — and their question whether that needs
  structure beyond types. Names and types alone leave the core chunk one
  file of about 9,700 functions, where no maintainer finds a feature;
  vendored copies are code nobody should maintain; and recovered structure
  is decided by the reference, so it stays compile-class work.
  Rejected: a new architecture inside the forge — design with taste forks,
  which takes the work out of compile-class; it belongs to product work on
  the reforged codebase afterwards. Also rejected: names and types only
  (the cheapest bar) — it fails the human partner's stated purpose.
  Date/Author: 2026-10-16 (the human partner's answer; the design session's route)
- Decision: After the adversarial review of the 2026-10-16 revisions, six
  changes. Publication takes the integration lock with `land` and `full`
  and is bracketed by intent and done lines in one integration log
  (`integration.jsonl`, replacing `landing.jsonl` and `publications.jsonl`),
  and every writer reconciles a pending intent before it mutates, so the
  reconciliation rule holds because nothing moves the integration ref
  outside the lock. A unit has two worktrees: the author's, branched from
  the integration tip, and the implementer's, branched from the unit's
  published oracle revision. The maintainability checks have a phase M2
  records: with recovered-module units, names, `tsc --strict` and the size
  cap at landing; with chunk units, names and `tsc --strict` at landing and
  the size cap and the module split at final acceptance, after a structure
  phase that is then mandatory (refining the maintainability entry above).
  The held-out path is never in the session's environment, since every
  subagent's shell inherits it (SPEC chapter 16): the root passes it on
  `oracle heldout --path`, no file names it, and the roles are told it
  exists and is not theirs. Progress files keep every agent id a unit has
  had, and `usage` charges each transcript to its nearest ancestor a
  progress file names through the sidecars' `parentAgentId`, the root and
  the controllers counting as overhead. ci-kit records a preemption without
  re-running the job, so the forge's gates write a result marker and the
  `ci-kit` provider re-runs a failure with no marker up to
  `run.infra_retries` before an `ERROR` escalation.
  Rationale: the review found a publication racing a landing outside the
  lock, no defined baseline for a new unit's implementer, a size cap a
  chunk unit cannot meet before structure exists, an environment variable
  that handed the held-out to every role, a helper's or a replaced role's
  usage escaping its unit's cap, and a preempted gate that would have read
  as a failed round. It confirmed what the revisions rest on: a stopped
  subagent resumes from its transcript; the depth arithmetic (root 0 to a
  role's fan-out 3) fits the default cap; the runner-era machinery is gone
  outside the Decision Log; and ci-kit's CLI supports the unit as the `ci/`
  ref's label, the seed from the nonce commit, and shard gates.
  Supersedes: "preemption handled" in the ci-kit entry above.
  Date/Author: 2026-10-16

## Outcomes & Retrospective

Pending — written at finish.
