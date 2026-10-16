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
on a stub. From there a **runner** drives the units through a fixed cycle —
oracle author, implementer, reviewer, mechanical verifier, landing — in
parallel worktrees for days or weeks, with a **root** session that re-plans,
fixes the process rather than the output, and reports at wave ends, and a
**delegator** that answers from the manifest whatever the manifest answers,
so that what reaches the human is only what the manifest could not decide.

How to see it working, smallest first: the toy forge under `tests/forging/toy/`
is a bundled TypeScript CLI with a short replication-grade spec; the skill
turns it into a manifest, the gate passes it, the runner reforges it module by
module with the reference bundle as the oracle, and `forge-run.py oracle full`
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
- [ ] M4 — The runner: role agents, access tiers, the unit FSM, state, resume
- [ ] M5 — Landing, oracle integration, ledger updates, gaming tests
- [ ] M6 — The root protocol and the delegator
- [ ] M7 — The toy forge end to end, docs, version

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
- **Cycle** / **unit FSM** — oracle author → implementer → reviewer and
  verifier → landing, with bounded returns to the implementer (§2.6).
- **Access tier** — what a role may read: tier A (reference, spec, candidate),
  tier B (spec, candidate, and the diffs of its own failures), tier C (the
  diff, the spec, the rubric, the verifier's report). Enforced by settings and
  mounts, never by the prompt.
- **Runner** — `skills/forging/scripts/forge-run.py`, the process that drives
  units through the FSM, dispatching each role as a headless `claude -p`
  session under that role's agent definition and settings.
- **Root** — the session that runs the preparation and, in the run phase,
  owns the manifest, re-plans, fixes the process, and reports; a human-opened
  interactive session or a sminos seat.
- **Delegator** — `doperpowers:forge-delegator`, the agent the root puts in
  front of the human: it answers escalations the manifest answers and drafts
  the question for the rest.
- **Fast sample** — a 1–10% sample of the full oracle drawn for each
  verification **without replacement per unit** from the inputs that unit
  has not yet seen (the runner keeps the exposure set), so a memorizer fails
  the first draw after its memorized set; when a unit's pool is exhausted,
  its remaining checks are `full`. **Full** is the whole oracle; **held-out**
  is a slice the swarm never sees. The recorded **expectations**, the
  held-out and the reference all live outside every worker's repository, at
  paths the verifier's environment holds (`FORGE_EXPECTED`, `FORGE_HELDOUT`,
  the manifest's reference paths).
- **Verify request** — the implementer's inner loop: a command its settings
  allow that asks the runner to verify its worktree's head in the verifier's
  environment on a fresh sample and return the diffs; not a round.
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
  roles/<role>.json  the --settings file each role runs under (access tiers)
  oracle/            the harness: run, normalize, compare, slices, fast-sample spec
  gate/              the audit's artifacts: decisions.tsv, matrix.tsv, readers/, verdict.md
  runs/<run-id>/     the run phase's state (state.json, events.jsonl, costs)
```

Held-out slices live outside the repository, at a path the root holds in
`FORGE_HELDOUT` and the manifest never names.

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
- **Fast and full.** `fast --seed <n>` is a 1–10% sample drawn fresh for
  each verification — Carlini's compiler fixed a sample per agent because
  the agents ran the oracle themselves; here the runner draws, so a worker
  never sees an input twice and memorizing a sample buys nothing; `full` is
  everything; output is a few lines with the detail in files. Every oracle
  run gets a fresh `HOME` and config directory.
- **Held-out.** A slice the swarm never sees, run by the root at wave ends
  and at closure. Reboot's translators passed 100% of the visible tests and
  62–92% of the hidden ones; this is the only measurement of that gap.
- **A real-input corpus** where one exists — recorded sessions, a file
  corpus, production inputs replayed with recorded responses — because a
  scripted oracle proves only what it exercises (Prime Intellect, giflib's
  30M-file corpus).
- **Isolation.** The implementer's environment cannot reach the reference
  or the expectations: not in its worktree, denied to its tools, absent from
  its container — and **never in its repository's history**, since a
  worktree shares the object store and `git show <commit>:<path>` reads
  what a path denial does not cover; protected artifacts live outside the
  worker's repository, and the toy's own reference and expectations sit in a
  sibling directory, not in the toy repository. The agents on record that
  called the original binary instead of porting it did so despite
  instructions; the isolation is a property of the sandbox. The same holds
  during a verification: the candidate runs on its own side, confined to
  what it links, while the reference side holds the binary and the
  expectations and does the comparing (§2.6).

#### 2.3 The parity ledger

`forge/ledger.tsv`, one row per component of the reference, columns:

```
id  component  source  reference_locus  unit  axes  slices  status  divergence  note
```

`source` is where the spec describes it; `reference_locus` where the
reference implements it; `status` is `missing` | `partial` | `matching`;
`divergence` is empty, `accepted:<reason>` or `triaged:<issue>` (the
TypeScript-to-Go port's `submoduleAccepted` / `submoduleTriaged` pattern).
The ledger is the contract, and no role writes it: the runner moves
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
and what the verifier checks mechanically where it can:

- the unit's oracle slices pass in a fresh checkout (verifier);
- the implementer's diff, measured from the unit's **oracle revision** (the
  commit the runner publishes when the author's work passes its checks),
  touches nothing under `forge/oracle/`, `forge/ledger.tsv` or the reference
  (verifier, by path) and carries no run of reference text (verifier, by
  fingerprint against the reference);
- no test skipped, deleted or weakened; a coverage drop is a deletion alarm
  (verifier where tooling exists, reviewer always);
- no hard-coded expected values, no stubs or `unimplemented` paths standing
  in for behavior, no call to the reference (reviewer; the held-out slice is
  the backstop);
- a workaround that needs a paragraph to justify is wrong (reviewer);
- the **look-alike list** for this language pair — constructs that read the
  same and behave differently — is checked line by line in the diff
  (reviewer; the skill's reference seeds lists for JS→Rust and bundle→TS);
- data the spec reproduces verbatim — prompts, constants, schemas, exact
  strings — matches byte for byte (verifier where the spec's own fidelity
  tools exist, reviewer otherwise);
- structure corresponds to the unit's plan and the first-pass rule.

#### 2.6 The cycle

Each unit runs this FSM, driven by the runner (§3), one role per headless
session; a further round resumes the role's session rather than opening a
fresh one (print mode resumes by session id, and three rounds at opus should
not pay orientation three times) — fresh only on a re-brief:

1. **Oracle author** (tier A; `doperpowers:forge-oracle-author`, opus/high)
   — from the unit's ledger items, the spec and the reference, writes the
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
   passes is **published**: the runner commits it onto the integration branch
   as the unit's oracle revision, and the implementer branches from there, so
   its diff is measured from a baseline that already holds the author's
   changes and any `forge/oracle/` change in that diff is the implementer's.
2. **Implementer** (tier B; `doperpowers:forge-implementer`, opus/high,
   downgradable per unit) — in its own worktree, from the staged spec, the
   brief and the oracle's code (readable; the recorded expectations are not),
   implements to the oracle. Its inner loop is the **verify request**: the
   runner performs the verification in the verifier's environment — the
   reference, the hybrid build and the expectations live there, not in the
   implementer's sandbox, which in a strangler could not even build the
   program — on a fresh draw from the unit's unseen pool, and returns the
   sample's diffs. The candidate itself runs on the **candidate side**, a
   confinement of its own that holds only what it links (in a strangler, the
   hybrid's reference chunks are necessarily among them), never the binary,
   the expectations or the spec inventories; the reference side holds those
   and does the comparing; the response is observation diffs on the parity
   axes only, size-capped, with any run of reference text redacted by
   fingerprint. A candidate that tries to print the protected files gets a
   denial on its side and a redaction on the other. No request counts as a
   round, and the manifest bounds requests per round. Returns `DONE` with a report, or
   `MORE_WORK`, `BLOCKED`, `INFEASIBLE`.
3. **Reviewer** (tier C; `doperpowers:forge-reviewer`, sol/xhigh, read-only:
   the diff, the staged spec, the rubric, the implementer's report) and
   **verifier** (mechanical, a runner step: a fresh checkout at the unit's
   head with the reference reachable, the unit's slices and a fresh sample of
   the full oracle run, the path checks applied, a machine-written report)
   run in parallel. The verifier is not a model: nothing can persuade it, and
   it costs nothing to run again.
4. **Landing** (§3) when both pass; otherwise the findings go back to the
   implementer, up to `max_rounds`; past that the unit returns to the root
   with `MORE_WORK` and the history, and the root re-plans it (split,
   re-brief) or records `INFEASIBLE` in the ledger as a triaged divergence.

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
the gate-miss bound breached) and the **checkpoints** (every wave end, with the report); the **budget** per unit and per run in
tokens (with an optional price table for a dollar estimate), the `full`
interval, and each role's turn limit — all fields of the manifest that the
runner reads, enforces and reports against from each session's usage; the **compute topology** — worktrees per unit on the runner's host, how
many units at once (the default rule: one per four cores and eight
gigabytes of the host), and the **sandbox provider** the verifier's and the
oracle's runs go to: `local` (a fresh worktree or container on the host),
`vm` (a pool on a host the manifest names), or `ephemeral` (a sandbox per
run from a provider with a prebaked image — microVMs with snapshot restore
where cold start matters, a container job service otherwise — with `full`
sharded across many); the oracle runner contract does not change with the
provider, so a provider is a thin wrapper, and this spec implements `local`
and defines the interface (the scenario's choice is in §6); **state** on disk with one writer — the runner's main process owns
`forge/runs/<id>/state.json`, a view rebuilt from per-unit append-only
journals that each unit's worker alone appends to, so a restarted runner
resumes from the journals rather than restarts (the transition table and the
linearization points are in Interfaces); `events.jsonl` for escalations,
budget thresholds and oracle failures at the tip; the **restart procedure** (a smoke test of the
integration branch before any dispatch, as every long-run harness on record
learned to do); and the rule that the root **fixes the process, not the
output**: a failure class that recurs becomes a change to the rubric, a
role's brief, or the oracle, followed by a re-sweep — the root never edits
product code (Bun, Airbnb, Carlini, Google).

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

The **root** holds the manifest and runs the runner; the runner holds the
loop. Why that split: a loop that lives in a model's context is lost at
compaction and drifts over days (every multi-day harness on record moved its
state to files and its loop to a process), while re-planning a stuck unit and
deciding how the process should change are judgment and belong to a model.
`run` executes one wave and returns: the root dispatches it in the
background, is notified at the wave's end, folds the events, reports, and
dispatches the next — the root's turn loop drives waves, the runner drives
units. What the split costs, and is accepted: the session's own windows on
its subagents (the agents pane, the bridge) do not show headless sessions,
so the runner's `status` and the persisted reports are the root's view; and a
role's context is a session the runner resumes between rounds, not a
subagent the root can message.

The runner (`forge-run.py`, Python standard library only) reads
`units.json`, computes waves by topological order over `consumes`, and runs
each wave's units concurrently up to the manifest's limit: a worktree per
unit off the integration branch, the FSM of §2.6 with each role a headless
session —

```
claude -p --agent <role> --settings forge/roles/<role>.json \
       --permission-mode dontAsk --max-turns <n> \
       --output-format stream-json --verbose
```

— the prompt rendered from the manifest and the unit (the brief, the
paths), the role's **report** being its final message, which the runner
persists from the stream's `result` event as `report-<role>.md` and whose
first line is the status (so a read-only role returns the same way as a
writing one), the usage from the stream (`--verbose` is mandatory for
stream-json in print mode; `dontAsk` denies anything the role's allow rules
do not cover, so no prompt blocks a headless role). The runner loads its own
checkout as a plugin with `--plugin-dir`, so the role definitions are those
of the code that dispatches them, and preflights each role once per run:
the harness answers an unknown `--agent` with a warning and default
behavior, never a failure, so the preflight fails the run on that warning.
Tiers are the role's settings, and a tier-B file must carry all of
`sandbox.enabled: true`, `sandbox.failIfUnavailable: true`,
`sandbox.allowUnsandboxedCommands: false`, `sandbox.filesystem.denyRead`
and `permissions.deny` `Read(...)` rules for the reference and the recorded
expectations (`forge/oracle/expected/`; the oracle's code stays readable) —
the sandbox is off by default and falls back to
unsandboxed execution unless told not to, so denial keys alone deny nothing
to a shell; the runner refuses to start a role whose file lacks any of them,
and a live check proves a reference read is refused through the file tools
and through the shell. In containers, the same by mounts. The specification
the implementer reads is a **staged copy** (`forge/.spec/`, the chapters the
manifest's `spec_paths` name, hash recorded), so the whole reference tree
can be denied. State is written as §2.7 says; `--resume` rebuilds it from
the journals and continues.

**Landing** is a queue with one lock: rebase the unit's branch onto the
integration branch; if the rebase changed the diff the review is void and the
unit returns to step 3; run the unit's slices and the fast sample at the tip;
fast-forward; on failure the unit goes back to the implementer with the
tip's diff. The fast-forward is recorded as an **intent** line (old and new
tip) before the ref moves and a **done** line after, and a resume reconciles
the integration ref with the last intent — ref at the new tip: mark done; at
the old tip: redo the fast-forward; elsewhere: escalate — since appending a
line and moving a ref are two writes. A `full` or held-out failure
**after** landing reopens the unit whose landing **caused** it, found by a
bisect over the wave's landings from the last green tip (landings are
linear, so this is mechanical); the ledger names the behavior that broke,
not the blame — a newly landed caller can break a slice an earlier unit
owns. No new unit dispatches while the tip is red (Carlini's compiler: new features kept
breaking existing functionality until the gate existed). `full` runs at
every wave end and on a timer the manifest sets; held-out runs at wave ends
by the root. This is the middle path between
Cursor's observation that a full gate on every commit serialized its agents
and Carlini's that his run needed a regression gate it did not start with;
the 2026-09-27 parallel-milestones design's landing rules (approval bound to
the head it covers, one at a time, tested at the tip) are reused.

**The root's loop**, in `references/root-protocol.md`: start with the smoke
test and resume; dispatch waves; fold the runner's events — a unit past
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
exercises; this is the planned measurement of what it did not); then,
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
  auditor's and readers' briefs), `references/root-protocol.md` (§3's
  operator manual).
- `skills/forging/scripts/forge-run.py` — the runner; `forge-env.sh` — builds
  a role's worktree, settings and environment, and stages the spec. The
  gate's readers need no script: they are read-only subagents the root
  dispatches from `rigor-gate.md`'s brief.
- `agents/forge-oracle-author.md`, `forge-implementer.md`, `forge-reviewer.md`,
  `forge-delegator.md` — the role contracts, with the repository's conventions
  (the compaction tools withheld; `AskUserQuestion` disallowed for the
  detached roles; the reviewer read-only and unable to spawn).
- `tests/forging/` — the FSM tests with a stub `claude`, the gaming tests, the
  toy, `run-forging-tests.sh`.
- The scenario under `docs/doperpowers/research/2026-10-15-compile-class-work/scenario-2.1.300/`.

Reused: doperpowers:brainstorming's purpose exploration and grill for Phase 1;
living-spec.md's document doctrine for `manifest.md`; the
`doperpowers:adversarial-reviewer` agent as the gate's auditor; the
2026-09-27 landing design; sminos and the bridge as the root's channel when it
is a seat; the self-compaction mod for a root that runs for days.

Why the runner dispatches headless sessions rather than subagents of the root
(the alternative considered): a role's isolation — its settings, its sandbox,
what its tools may read — is a property of a process, and a subagent inherits
the parent's; and a days-long loop should not be a tool call in a model's
turn. The Workflow tool was considered for the FSM and rejected for the same
reason plus its determinism constraints on shell work; it remains the right
tool for in-session fan-out the root may want for itself.

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

**Target.** TypeScript on Bun, a readable source tree whose module boundaries
follow the chunk graph (first-pass rule); parity on the harness, not the
model.

**Access tiers.** The oracle author reads SPEC, `modules/`, `cli.pretty.js`
and runs the binary; the implementer reads a staged copy of the chapters
(`forge/.spec/`, `SPEC/*.md` only — `_inventory` carries code signatures and
`_notes` carries reprint lines, both excluded) and its worktree, and
`roles/implementer.json` denies `~/claude-code-bundle/**` and
`~/.local/share/claude/**` to reads and the sandbox, fail-closed; the
verifier runs both binaries. This is the spec's own success criterion made
operational.

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
choice is recorded with the spike's answer, not deferred.

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
microtasks the reprint obscured.

**Run conditions.** Compute: the roles on a 128 GB VM, each in a container
(the reference mounted only in tier A); the verifier's runs and `full` on an
**ephemeral** sandbox provider rather than a fixed runner — a verify is a
stateless job of minutes (checkout at the head, build the hybrid, run the
slices against the scripted server, diff), the work is embarrassingly
parallel, and a fixed host serializes it once saturated, which is where a
swarm's wall-clock goes; with a prebaked image (bun, the toolchain, the
Linux 2.1.300 reference, the recorded corpus) a cold start is seconds
against a run of minutes, and `full` shards across as many sandboxes as the
slices warrant. The reference in those sandboxes is the Linux build of
2.1.300 with its expectations re-recorded on Linux, since the macOS binary
does not run there; parallelism of the roles is set by the VM's cores at M2. Budget: rough calibration from the survey only —
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
exit codes, file formats). The oracle: scripted invocations compared on
stdout, exit code and files written; a held-out set of invocations; a seeded
divergence (a second build with one constant changed). The strangler: `tools/hybrid.mjs`, a
short build that imports each module from the reference chunk or the reforged
source per `forge/strangler.json`, part of the fixture the way the bundle's
`tools/` are part of the scenario's reference. The whole system runs on it
end to end — Phase 0 and 1 by the skill, the gate, Phase 2 by the runner with
two units in parallel, closure — at a cost of tens of agent sessions, most at
sonnet. It is the proof that the machinery works and the fixture for the
gaming tests (§M5).

## Acceptance

Observable at the end, each with the milestone that proves it:

1. **The skill produces a manifest.** A general-purpose subagent with no
   context beyond `skills/forging/SKILL.md`, its references, and the toy
   target writes `tests/forging/toy/forge/` with `manifest.md` (sections
   2.1–2.8 present), `ledger.tsv`, `units.json`, `rubric.md`, `roles/`,
   `oracle/`; `forge-run.py plan` prints its waves. (M1 for the shape, M4 for
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
5. **The FSM runs and resumes.** With a stub `claude` that returns scripted
   statuses, `forge-run.py run` on the toy journals every unit's transitions
   through the FSM with two units concurrent, respects `max_rounds`, resumes
   a role's session on a further round (the stub records the resumed id),
   answers a verify request from the implementer's worktree with a fresh
   sample's diffs without counting a round, returns a unit to the root with
   its history, and `--resume` after a kill at each of the three boundaries
   (after the report is persisted, after the journal line, after
   `state.json`) continues without re-dispatching a role whose journal line
   exists and re-runs one whose line is missing under the next attempt
   number; a session ending in each of the harness's error result variants,
   or with no result, is journaled `ERROR`, retried once per policy and then
   escalated. A unit crossing its token cap raises a `budget` event and no
   new role dispatches past the run cap. (M4)
6. **Gaming is caught, and the tier holds.** A stub implementer that
   hard-codes outputs fails its sample; a memorizer that answers every input
   it has seen fails the first draw after its memorized set, and a unit
   whose pool is exhausted is checked by `full`; an implementer whose diff
   from the oracle revision touches `forge/oracle/` or `ledger.tsv` is
   refused at landing with the path named, while the author's own
   extension of a slice landed in that revision passes; a candidate that
   prints a protected file gets a denial on the candidate side and a
   redacted response; a diff carrying a run of reference text is flagged;
   an oracle author whose slices pass under the stub is returned `MORE_WORK`
   (M5). A live check with a real implementer session under its settings
   shows a `Read` of the reference and a shell `cat` of it both refused, a
   `git show` of any commit finding no reference or expectation content in
   the worker repository's history, and a run with the sandbox unavailable
   refused to start (M4).
7. **Landing holds the tip green.** Two toy units landed in one wave; a
   rebase that changed a diff voided its review and the unit re-entered step
   3; `oracle full` at the wave end prints zero divergences; a `full` fired
   by the interval during an unfinished wave is recorded in `events.jsonl`
   with its result; a seeded divergence landed by unit B that breaks a slice
   unit A owns reopens B at the wave-end `full`, with A's ledger items
   named, and holds the next wave until it is fixed; and a kill on either
   side of a landing's ref move is reconciled on `--resume`. (M5)
8. **The root protocol and delegator work on seeded events.** Events for
   each escalation class are fed; the delegator resolves the class-1–3 ones
   with the manifest line it used and drafts a question for the class-4 one;
   the wave report has the ledger counts, the gate-miss rate, cost, and
   oracle results. (M6)
9. **The toy forge ends green.** `forge-run.py run` on the toy with real
   roles lands every unit, `oracle full` prints zero divergences, held-out
   prints zero, `ledger.tsv` has every row `matching`, and `runs/<id>/`
   holds the cost. (M7)
10. **Tests, docs, version.** `tests/forging/run-forging-tests.sh` passes;
    the repo map row in `CLAUDE.md` describes the skill, agents and runner;
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
ownership and outcomes, and keeps the project's voice; nothing in the
scenario's manifest names the held-out path; every milestone commits as it
goes and keeps `Progress` current.

### M1 — The skill: doctrine, manifest shape, oracle patterns, rubric, rigor gate

What exists at its end: `skills/forging/` with `SKILL.md` and the five
references of §5; `agents/forge-reviewer.md`, since the gate's calibration
dispatches the reviewer that will judge units and the toy's gate runs here;
the toy fixture under `tests/forging/toy/` — a repository of its own,
initialized by `tests/forging/toy/setup.sh` into a working directory, holding
`src/`, `SPEC.md` and the oracle's code, beside a **sibling directory** that
holds what no worker may reach: `ref/` built with `bun build --splitting`,
`mut/` the same build with one constant changed as the seeded divergence,
`tools/hybrid.mjs` the hybrid builder, and the recorded expectations; and,
produced by a subagent reading nothing but the skill and the fixture, the
toy's `forge/` with its oracle (`forge/oracle/run.py` per the contract in
Interfaces), its self-parity and mutation evidence, and its gate record.
Touches: `skills/forging/`, `agents/forge-reviewer.md`, `tests/forging/toy/`. Produces: the manifest shape (`manifest.md`,
`ledger.tsv` columns, `units.json` schema, `roles/*.json` keys, the status
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
touch: the runner, the other three role agents. Proves: acceptance 1's shape (the dry
read), 2 and 3 for the toy (the readers and the calibration dispatched from
`rigor-gate.md`'s briefs, the `doperpowers:adversarial-reviewer` audit,
`forge/gate/verdict.md`); doperpowers:writing-skills' structure test on the
skill.

### M2 — The 2.1.300 scenario manifest

What exists at its end: `scenario-2.1.300/forge/manifest.md`, `ledger.tsv`,
`units.json`, `rubric.md`, `roles/*.json`, written per M1's shape against
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
section names `SPEC/*.md` as the implementer's staged input and excludes
`_inventory` and `_notes`; the unit graph is chapter-aligned chunk groups over the ESM
import graph (`modules/` imports), leaves first, with the many-chapter chunks
handled by a rule the milestone picks from the data and records (split by
section, or first-needing unit); the product share of the bundle is measured
from `CHUNK-INDEX.md` (vendored chunks identified by their fingerprints) and
the budget section gives a range from the survey's calibration against that
share; the manifest's caution paragraph (§6) is present. Does not touch: the
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
the Messages API's streaming shape, started by the runner per slice run on a
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
is a set of scripted sessions and a transcript-replay sample at the path in
`FORGE_HELDOUT`, written by this milestone, never committed. Does not touch:
axes (4)–(6), which the matrix marks unbuilt. Proves: acceptance 2 (the
scenario's verdict), 3 (self-parity and mutation for 2.1.300), 4 (the spike).

### M4 — The runner: role agents, access tiers, the unit FSM, state, resume

What exists at its end: `forge-run.py` with `preflight`, `plan`, `run`,
`unit`, `status`, `--resume`, `--parallel`; `forge-env.sh` (a role's
worktree, settings and environment, and `stage-spec`); the other three
agent definitions (the reviewer is M1's); the FSM tests with a stub
`claude`; the live isolation check.
Touches: `skills/forging/scripts/`, `agents/forge-*.md`, `tests/forging/`.
Consumes: the manifest shape. Produces: the runner's command surface, the
journal and state schemas and the transition table (Interfaces). Decisions:
one headless session per role invocation, as §3 says, with the prompt
rendered from `manifest.md`, `units.json` and the unit's brief, the role's
final message persisted from the stream's `result` event as its report and
the first line parsed as the status, and a further round of the same role
resuming its session by the id the stream's first event carries (recorded in
the journal), fresh only on a re-brief; the implementer's verify request is
`forge-run.py verify` run from its worktree — it writes
`runs/<id>/units/<unit>/verify/<n>.request` and waits for the `.response`,
which the main process writes after performing the verification in the
verifier's environment on a fresh draw (M5 supplies the oracle call and the
exposure set; M4 supplies the request loop, the per-round request bound
from the manifest, and tests it with a stub oracle); a session that ends
without a result text — the harness's `error_max_turns`,
`error_max_budget_usd` and `error_during_execution` result variants, or a
process exit with no `result` — is journaled as `ERROR` with the variant and
whatever usage arrived, retried once (`error_max_turns` by resuming the
session with the instruction to report now; the others fresh), and
escalated on the second, and the stub emits each variant in the tests; `--plugin-dir` pointing at the checkout
the runner lives in, and `preflight` dispatching each role on a one-line
prompt and failing the run on the harness's unknown-agent warning — if a
live check at this milestone shows `--plugin-dir` does not register agents
for `--agent` in print mode, the runner renders `--agents` JSON from the
agent files instead, with a Decision Log line; every role runs with
`--permission-mode dontAsk` and the allow rules its settings file carries;
the stub `claude` for tests is a shell script on `PATH` that emits a
stream-json `result` whose text is a scripted report per role, unit and
attempt from a fixture, so transitions are tested without a model;
concurrency is one worker process per unit, each appending only to its
unit's journal, and the main process the one writer of `state.json`, rebuilt
from the journals (a scratchpad rewritten, not appended — Cursor's finding);
a role is finished at its journal line, so a kill between the persisted
report and the line re-runs the role under the next attempt number; usage is
accumulated per unit and per run from the streams, `budget` events fire at
the manifest's thresholds, and no new role dispatches past the run cap;
before dispatch the implementer's settings file is checked for the
fail-closed sandbox keys and the denials of §3, and `forge-env.sh stage-spec`
copies the manifest's `spec_paths` into `forge/.spec/` with a hash;
`tests/forging/live-isolation-check.sh` runs a real implementer session
against the toy's settings and expects the refusals of acceptance 6, run by
hand as the repository's other live checks are. Does not touch: landing and
oracle integration (M5), the root protocol (M6). Proves: acceptance 5 and
the tier half of 6.

### M5 — Landing, oracle integration, ledger updates, gaming tests

What exists at its end: `forge-run.py land`, `oracle fast|full|heldout|
self-parity|mutation` as thin drivers over `forge/oracle/`'s runner
interface, ledger `status` updates on landing, and the gaming tests. Touches:
`skills/forging/scripts/forge-run.py`, `tests/forging/`. Consumes: the
runner's surface. Decisions: the landing lock is a file under `forge/runs/`;
review validity is bound to the reviewed head's tree hash, so a rebase that
changes the diff voids it; every sample is a `fast --seed <n>` draw without
replacement from the unit's unseen pool, the exposure set kept under the
unit's run directory and exhaustion answered with `full` (verify requests,
the verifier step, the tip check); the **stub check** runs
when the oracle author returns (`oracle stub <unit>` then `compare`; slices
that pass under the stub return the author `MORE_WORK` with their names),
self-parity and mutation re-run when the author's diff touched
`forge/oracle/`, and work that passes is committed onto the integration
branch as the unit's oracle revision, recorded in the journal, from which the
implementer's worktree branches and against which its diff is measured; the
verification's two sides are two directories — the candidate side a
confinement holding the worktree's head and what it links, the reference
side the reference, the expectations and the comparer — and the response is
the comparer's diffs, size-capped, with reference runs redacted by the
fingerprint check that also flags them in the diff; a `full` or held-out failure after landing is attributed by a
bisect over the wave's landings from the last green tip, writes a `reopened`
event naming the landing that caused it and the ledger items that broke,
moves that unit to `reopened`, and holds dispatch while the tip is red (a
test has unit B's landing break a slice unit A owns, and B reopens); the
fast-forward writes an `intent` line with the old and new tips before the
ref moves and a `done` line after, and `--resume` reconciles the ref with
the last intent as §3 says, with kills on both sides of the ref move in the
tests; the runner moves ledger `status`
from slice results at landing and at `full`, and any role diff touching
`ledger.tsv` is refused; the verifier's path check compares the implementer's diff from the
unit's oracle revision against `forge/oracle/**`, `ledger.tsv` and the
manifest's reference paths, and its fingerprint check against runs of
reference text (the toy's `ref/` chunks; the scenario's `CHUNK-INDEX.md`
fingerprints and `modules/`); `oracle` subcommands call
`forge/oracle/run.py` with a fixed argument contract (`<axis> <binary>
<slice>` → a directory of observations, `normalize`, `compare` → a summary
line and a detail file) so the harness is per target and the driver is not;
the held-out path comes only from `FORGE_HELDOUT`; `run` executes `full` at
every wave end and, from a timer in the main process, every
`full_interval_minutes` during a wave, serialized with landing under the same
lock, writing a `full` event with the result and a `tip-failure` event per
divergence, while held-out stays the root's to run. Does not touch: the root
protocol. Proves: acceptance 6's gaming half and 7, on the toy with the stub
`claude` and the toy's oracle.

### M6 — The root protocol and the delegator

What exists at its end: `references/root-protocol.md`, `agents/forge-delegator.md`,
`forge-run.py report` (the wave report rendered from `state.json`, the ledger
and the last oracle results), and a seeded-events test of the delegator's
resolutions and the report's format. Touches: `skills/forging/references/`,
`agents/`, `skills/forging/scripts/forge-run.py` (the `report` subcommand
only), `tests/forging/`.
Consumes: the runner's surface and `events.jsonl`. Decisions: the protocol is
an operator manual in the style of `issue-tracker/references/review-loop.md`
— start, waves, folding events, re-planning, process fixes, reports,
closure — not a skill; the delegator reads `manifest.md` and the event and
returns either a resolution with the manifest line it rests on or a drafted
question with alternatives and a recommendation; the wave report is a fixed
set of lines (units landed and remaining, ledger counts by status, `full`
and held-out results, cost to date, escalations open) so the human reads the
same shape every wave. Does not touch: the runner's loop. Proves: acceptance
8.

### M7 — The toy forge end to end, docs, version

What exists at its end: the toy forged by the real roles, the acceptance
walk, the repo map row, the version bump. Touches: `tests/forging/toy/`,
`CLAUDE.md`, the manifests `bump-version.sh` lists. Consumes: everything.
Decisions: the toy run uses sonnet for the implementer and the readers and
the pinned models elsewhere, with `max_rounds` 3 and `--parallel 2`; the run's
cost is recorded in the spec's retrospective; this milestone spends model
usage (tens of sessions) and the human partner is told the estimate before it
starts. Proves: acceptance 1 (with the runner), 2 (the toy's verdict), 3 (the
toy's self-parity), 9, 10, and executes the whole Acceptance section as
written.

## Concrete Steps

Working directory is the repository root unless stated.

- M1: `tests/claude-code/run-skill-tests.sh` (the structure test picks up
  the new skill); a dry read: dispatch a general-purpose subagent with "Read
  `skills/forging/SKILL.md` and its references; the target is
  `tests/forging/toy/` (its `src/`, `dist/ref/`, `SPEC.md`); produce
  `tests/forging/toy/forge/` per the manifest reference" and inspect
  `ls tests/forging/toy/forge/` → `manifest.md ledger.tsv units.json rubric.md roles oracle gate`.
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
  `ok`; `python3 -I skills/forging/scripts/forge-run.py plan tests/forging/toy/forge` →
  `wave 1: U1 U2` / `wave 2: U3`.
- M4 live check (spends two cheap sessions, by hand):
  `tests/forging/live-isolation-check.sh tests/forging/toy/forge` →
  `read: refused`, `bash: refused`, `no-sandbox: refused to start`;
  `python3 -I skills/forging/scripts/forge-run.py preflight tests/forging/toy/forge` →
  one `ok` line per role.
- M7 (in `tests/forging/toy/`): `python3 -I ../../../skills/forging/scripts/forge-run.py run forge --parallel 2` →
  per-unit transitions and `landed U1 U2 U3`; `… oracle full forge` →
  `full: 0 divergences (N slices, skipped: 0)`; `FORGE_HELDOUT=… oracle heldout forge` →
  `heldout: 0 divergences`; `scripts/bump-version.sh <next>`.

## Interfaces and Dependencies

Defined once here; milestones point at them.

- **Manifest shape** (M1, `references/manifest.md`): the directory of §2;
  `ledger.tsv` columns as §2.3; `units.json` as an object `{ "units": [ {
  "id", "title", "ledger": [], "touches": [], "reference_locus": [],
  "consumes": [], "produces": [], "slices": [], "max_rounds", "models": {}
  } ], "run": { "parallel", "budget": { "unit_tokens", "run_tokens",
  "prices": {} }, "full_interval_minutes", "roles": { "<role>": {
  "max_turns" } }, "sandbox_provider": "local" } }`; the manifest's Target
  section carries `spec_paths` (what `stage-spec` copies) and the reference
  paths the tiers deny; `roles/<role>.json` is a harness `--settings`
  document, and a tier-B file carries the fail-closed sandbox keys of §3; a
  role's report is its final message, its first line one of `DONE`,
  `MORE_WORK`, `BLOCKED`, `INFEASIBLE`, `ERROR`.
- **Oracle runner contract** (M1 for the toy, M3 for the scenario; M5's
  driver; the oracle's code and slice inputs in the repository, the recorded
  expectations outside it at `FORGE_EXPECTED`): `forge/oracle/run.py <axis> run <binary> <slice> <outdir>`,
  `… normalize <outdir>`, `… compare <expected> <actual>` → one summary line
  on stdout (`<axis> <slice>: <n> divergences, skipped: <k>`) and a detail
  file, and `… stub <unit> <outdir>` builds the candidate with the unit's
  module stubbed; `self-parity`, `mutation --against <ref>`, `fast --seed
  <n>`, `full`, `heldout` compose these.
- **Runner surface** (M4, M5, `report` in M6): `forge-run.py
  preflight|plan|run|unit <id>|land <id>|oracle <sub>|status|report
  [--resume] [--parallel n] <forge-dir>`. **Journals and state**: each
  unit's worker appends to `runs/<id>/units/<unit>/journal.jsonl` lines
  `{ "ts", "attempt", "role", "status", "head", "usage" }` and keeps that
  attempt's persisted report beside it; the main process alone writes
  `state.json` `{ "run", "units": { "<id>": { "state", "attempt", "head",
  "review_head", "usage" } }, "usage", "waves": [] }` as a view over the
  journals; landing appends to `runs/<id>/landing.jsonl` lines `rebase-start
  | review-void | tip-check | intent {old, new} | done {new}` per unit, and
  `runs/<id>/units/<unit>/exposure.json` holds the inputs the unit has
  seen. **Transition table**
  (unit states): `planned → authored` (oracle author `DONE`); `authored →
  implemented` (implementer `DONE`); `implemented → judged` (reviewer and
  verifier both `DONE`); `implemented → implemented` (either `MORE_WORK`,
  `attempt + 1`, while `attempt ≤ max_rounds`); `judged → landed`
  (`fast-forward` line); `judged → implemented` (`review-void` or a failed
  `tip-check`); `authored → authored` (stub check failed, author
  `MORE_WORK`); `planned → authored` also publishes the oracle revision
  (journaled with its commit); a role journaled `ERROR` is retried once per
  M4's policy and then `escalated`; `landed → reopened` (a `full` or held-out failure attributed
  to the unit) and `reopened → implemented` (the root resumes it with the
  tip's diff); any role `BLOCKED` or `INFEASIBLE`, or `max_rounds` exceeded,
  → `escalated` with an event, the unit idle until the root resumes or
  closes it. **Linearization points**: a role is finished at its journal
  line; a unit is landed when the integration ref moves (`git update-ref`,
  atomic), bracketed by the `intent` and `done` lines a resume reconciles. **Verify requests**:
  `runs/<id>/units/<unit>/verify/<n>.request` (the worktree head) answered by
  `<n>.response` (the sample's seed and diffs); journal lines carry the
  role's `session` id for resumption. `events.jsonl` lines `{ "ts", "unit",
  "kind", "detail" }` with `kind` in `escalation | infeasible | tip-failure
  | heldout-failure | reopened | budget | full | gate-miss`.
- **Role agents** (M4): `doperpowers:forge-oracle-author`, `forge-implementer`,
  `forge-reviewer`, `forge-delegator`, addressed by `--agent <name>`.
- **Dependencies**: `claude` ≥ 2.1.300 for `--agent`, `--plugin-dir`,
  `--settings`, the `sandbox` settings (`enabled`, `failIfUnavailable`,
  `allowUnsandboxedCommands`, `filesystem.denyRead`) and stream-json both
  ways; `bun` for the toy and the scenario; Python 3.12+ for this
  repository's scripts (the bundle's own tools declare theirs; `extract.py`
  needs 3.14 and is never invoked by this work).

## Surprises & Discoveries

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

## Outcomes & Retrospective

Pending — written at finish.
