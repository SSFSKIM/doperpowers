# Implement-Worker Autonomy — the Ticket Gate and the no-orchestrator implement loop

## Purpose

Today the implement side of the pipeline has two structural weaknesses. First,
a dispatched worker may start building from an ambiguously scoped ticket — the
current Worker Protocol tells it to park "the moment ANY part of the task is
ambiguous," but that discovery happens informally, mid-orient or mid-build,
after context and sometimes code have already been spent. The cost of
implementing a badly defined task is the single biggest waste in the pipeline.
Second, the loop assumes a central orchestrator-as-judge (the main session)
that reads every worker turn and answers, queues, or wakes — a role that does
not scale and that the auto-attach future (workers attaching to opened issues
the way review workers attach to opened PRs) eliminates outright.

After this change, every implement worker runs the **Ticket Gate** before
opening a single source file: the ticket must be *well-defined* (no
non-trivial architecture decision, no product-design decision, and no taste
decision — major or minor — left unanswered by the ticket body + codebase) and
*well-scoped* (fits ~1–2 ExecPlans). A gate failure never means guessing; it
means parking into a re-triaged vocabulary (`needs-human`, a narrowed
`needs-info`, the new `interactive-preferred`) or decomposing into child
tickets with rigorous edges. The orchestrator-as-judge dies now: the protocol
is written for the no-orchestrator world, and until the auto-attach trigger
lands (next phase, scoped out), dispatch is a mechanical ritual with no
judgment in it.

This is the implement-side mirror of doperpowers:reviewing-prs — where the
review loop put its rigor gate at the *end* of the pipeline (confident-ready
before merge), this loop puts its rigor gate at the *start* (gate before
code). Both replace live orchestrator judgment with a protocol embedded in
the spawn prompt.

How to see it working: dispatch a worker onto a well-specified small ticket —
it sets `in-progress` itself, leaves a `[gate]` comment, builds, and opens a
PR that the review loop picks up; zero orchestrator turns anywhere. Dispatch
one onto a ticket with a buried taste fork — it writes no code and the ticket
comes back `needs-human` with the question and a recommended answer in the
note.

**Terms of art.** *Ticket Gate*: the pre-code pass/park verdict (well-defined
+ well-scoped). *needs-human*: parked for the human acting as themselves — a
decision only they can make, or a real-world input only they possess.
*needs-info*: rare — spec lacks depth for a sophisticated result, or core
decisions need substantial research first. *interactive-preferred*: the
ticket's shape wants continuous human steering; never auto-dispatched.
*Decompose*: register child tickets under the parent with edges; a blocked-by
chain IS serialization. *Direct / ExecPlan*: the two execution modes on gate
pass. *Mechanical dispatcher*: whoever/whatever spawns workers — writes
nothing to the board, judges nothing.

## Architecture

```
ready-for-agent ticket
  → dispatch                                  [mechanical — interim: human-run
                                               ritual; auto-attach trigger is
                                               next phase, scoped out]
    → implement worker (claude --bg, fresh context, own worktree)
        THE GATE — before any source file:
          fail (open decision)      → needs-human   [questions + recommendations]
          fail (missing knowledge)  → needs-info    [what's missing, why it gates]
          fail (shape needs human)  → interactive-preferred [steering areas]
          fail (size, sliceable)    → DECOMPOSE: children via --parent
                                      (+ --blocked-by), parent becomes epic
          pass                      → in-progress + one-line [gate] comment
        BUILD: direct | doperpowers:execplan → PR ("Closes #N")
    → doperpowers:reviewing-prs loop → self-merge | confident-ready → done
```

Load-bearing properties:

- **The gate precedes code, every dispatch.** Fresh context re-runs it from
  scratch; there is no inherited trust between parent and child tickets.
- **The worker's first board write IS the verdict.** Dispatch writes nothing;
  `in-progress` means gate-passed, a park state means gate-failed.
- **No orchestrator anywhere.** Escalation targets are the board itself
  (states, notes, comments) and the human on their next wake. Turn-end
  messages are audit trail, not requests.
- **Fractal decomposition is emergent.** Each child's worker re-runs the same
  gate; a still-too-big child decomposes again. No depth counters, no
  recursion machinery — the per-ticket gate is the whole mechanism.
- **Edges carry structure.** `--parent` = decomposition (composition),
  `--spawned-by` = discovery (scope-outs/follow-ups from work),
  `--blocked-by` = ordering. Serial vs parallel is a dependency shape, not a
  policy branch.

## The Ticket Gate

Runs during ORIENT, before any source file opens. It is brainstorming's grill
run *in absentia*: interrogate the ticket the way the grill interrogates a
human, but every answer must come from the ticket body, the codebase, or repo
docs. Trivial lookups (docs, grep, an external API's actual shape) are orient
work the worker just does — never a park.

**Check 1 — well-defined.** Classify every fork the implementation will hit:

| fork class | examples | who answers |
|---|---|---|
| Mechanical/technical, one obvious best answer | internal naming, idiomatic choice, which test file — repo precedent or engineering judgment decides | the worker. Parking these is a protocol violation, not caution |
| Non-trivial architecture | subsystem boundary, data model, API/protocol shape — lasting consequences | ticket + codebase; unanswered → gate-fail |
| Product design or taste, **major or minor** | user-facing behavior, wording, interaction/visual choices — anywhere a reasonable human could prefer differently on non-technical grounds | the ticket; unanswered → gate-fail. Even minor taste is never the worker's call |

Note the deliberate asymmetry: trivial architecture calls belong to the
worker, but even minor taste calls do not.

Park discriminant on gate-fail — **who unparks it?**

- The human acting as themselves (a decision, or a real-world input like
  credentials/auth/production data) → `needs-human`. Note = the crisp question
  list, each with the worker's recommended answer (grill posture preserved:
  recommend, then let the human confirm).
- Knowledge work that anyone could in principle do (substantial research,
  spec-deepening) → `needs-info`. Note = what is missing and why gating cannot
  proceed without it. The research threshold keeps this rare: only research
  that is its own work-unit, or whose outcome must pass through the human
  before decisions harden.
- Not one answer but ongoing steering → `interactive-preferred` (Check 2's
  territory).

**Check 2 — well-scoped.** The work must fit the ticket as one purpose-unit:
roughly 1–2 ExecPlans. Too big forks on one question — *can the remainder be
written down as self-contained child pre-specs right now?*

- **Yes → decompose** (next section).
- **No** — coherence across slices needs one continuously steered human
  context → `interactive-preferred`, note = which decision areas need
  steering, so the human enters the eventual /brainstorming session
  pre-oriented.

**Verdict is the worker's first board write.** Pass →
`board-transition.sh <n> in-progress` plus a one-line `[gate]` comment naming
the verdict and the execution mode chosen — a cheap audit trail while the
gate's judgment earns trust; tunable to silence later. Fail → the park state
itself, with its required note.

## Decompose — the one scoping behavior

- **Registration.** Each child via `board-register.sh --parent <original>`;
  ordering via `--blocked-by` between siblings. A linear chain is
  serialization; no edges is parallel fan-out; mixed shapes are fine.
- **Provenance discipline.** `--parent` for decomposition children (they ARE
  the parent's content, sliced). `--spawned-by` keeps its existing meaning —
  scope-outs and follow-ups discovered during work.
- **Honest child triage (the fractal rule).** The decomposing worker
  gate-triages each child at registration: `ready-for-agent` only if it
  believes the child passes the full gate; a child with an open human
  decision is born `needs-human`; a product-core child is born
  `interactive-preferred` — each with the required note.
- **Just-in-time registration.** Register now every child that can be written
  as a self-contained pre-spec (the issue-register bar: a fresh-context worker
  can start from the body alone). Contingent later phases are NOT registered
  speculatively — they live as a `## Roadmap` section in the parent's body,
  and the worker finishing phase K registers phase K+1 at PR time with
  `--parent <epic>` and `--blocked-by` as needed. A roadmap line in the parent
  is the one sanctioned form of "ticket that doesn't exist yet."
- **The parent becomes an epic.** Existing machinery unchanged: epics are
  never dispatched; the sweep moves them. The decomposing worker's exit:
  children registered, parent body updated (roadmap + a Decision log entry
  recording why this cut), end turn. It writes no code.

## Execution — two modes on gate pass

- **Direct** — the pre-spec is the plan: TDD, commit, open the PR.
- **ExecPlan** — invoke doperpowers:execplan when the work has 2+ milestones,
  or spans enough files/design sequencing that a fresh session would need the
  document to survive context death. The gate already served as the grill's
  in-absentia form; the ExecPlan is authored from ticket + gate findings and
  executed to the letter.

The previous protocol's third row (in-daemon execspec + writing-plans) is
deleted: a daemon driving the controlled track with nobody at the controls was
always a contradiction — that shape is precisely `interactive-preferred` now.
Thresholds are tunable starting values living in one place: the protocol text.

## Components

### 1. `skills/issue-tracker` — schema v8

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `needs-human` | open + `status:needs-human` | parked for the human as themselves: a decision only they can make, or a real-world input only they possess (credentials, auth, production data) | **required** |
| `needs-info` | open + `status:needs-info` | rare: spec unambiguous but lacks depth for a sophisticated result, or core decisions need substantial research first | **required** |
| `interactive-preferred` | open + `status:interactive-preferred` | ticket shape wants continuous human steering; never auto-dispatched; summons the human into /brainstorming | **required** |

`blocked` is REMOVED from the schema. All other states unchanged
(`ready-for-agent`, `in-progress`, `in-review`, `confident-ready`, `done`,
`wontfix`, `deferred`).

Script changes: `board-transition.sh` (state set, legality incl.
`in-review → needs-human` replacing `in-review → blocked`, note enforcement
for all three park states, repair reachability); `board-lint.sh` (known-label
set; an open `status:blocked` FAILs with FIX line "migrate:
board-transition.sh <n> needs-human" — lint IS the migration tooling);
`board-list.sh` (`interactive-preferred` never tags `ELIGIBLE`);
`board-map.sh` (kanban columns/DAG classes for the new states);
`board-register.sh` (`--state` accepts them). Setting `interactive-preferred`
is legal for: a gate-failing worker, issue-register at registration, the
human.

### 2. New skill `skills/implementing-tickets/` — the product

Sibling and mirror of `reviewing-prs`:

- **`SKILL.md`** — loop doctrine: the Ticket Gate, the park discriminant,
  decompose mechanics, the 2-way execution choice, direct-registration
  authority, edge cases. Triggers on dispatching implementation workers /
  gating tickets / decomposing oversized tickets.
- **`references/implement-worker-protocol.md`** — Protocol v2 (draft below),
  `{{PLACEHOLDERS}}` (issue number, repo, ticket body; exact set finalized at
  plan time — see Assumptions) rendered into every spawn prompt. The interim mechanical dispatcher renders
  it by hand per SKILL.md; the trigger phase's dispatch script renders it
  mechanically.
- **`scripts/`** — empty this phase; `implement-dispatch.sh` + workflow
  template land here next phase, exactly where `review-dispatch.sh` lives in
  its skill.

### 3. `skills/issue-tracker` — SKILL.md rewrite (the board manual)

The "two roles" table and all orchestrator-as-judge doctrine (judge rubric,
JSON proposal handling, answer/queue/wake) are deleted. What remains: the
state schema, the Board Write Hard Gate, the scripts reference, the pre-spec
body shape, the deferral rule (updated: workers register follow-ups directly
at PR time), edge cases. The dispatch loop becomes a mechanical ritual: list
ELIGIBLE → render protocol + ticket body → `daemon-spawn.sh` (worktree) →
`board-bind.sh` — no `in-progress` write, no judging step, and a pointer to
implementing-tickets for doctrine. Reconcile-on-wake becomes the human's
ritual: the wake queue is `board-list.sh needs-human` / `needs-info` /
`interactive-preferred` (exactly the queue the future Slack connector will
push). Finalize semantics unchanged: `done` arrives by merge; the human (or
the review worker in its self-merge tier) runs the finalize transition.

`orchestrating-daemons` is untouched — its judge rubric remains correct for
ad-hoc conversational fleets. The judge dies in the ticket pipeline, not
everywhere; one paragraph in issue-tracker notes the boundary.

### 4. `skills/reviewing-prs` — rename-level ripples

Protocol escalation discriminant and error-table rows swap `blocked` →
`needs-human` (permission-gated ops, push conflicts at retry cap). No
behavior change.

### 5. Consumer migration (ida-solution, one-time)

- Create labels `status:needs-human`, `status:interactive-preferred`
  (scripts auto-create on first write; pre-creating keeps the hosted board's
  legend complete from day one).
- Sweep open `status:blocked` tickets → `needs-human` with carried notes;
  lint FAILs stragglers.
- `issue-status-labels.yml`: MANAGED set adds the two new labels, drops
  `status:blocked`.
- Hosted board re-renders pick up new columns on the next issue event.

Also: one-line addition to `issue-register`'s register step — a cluster whose
grill already shows it is product-core may be registered
`--state interactive-preferred` at birth.

## Implement Worker Protocol v2 (draft — final wording lands in the reference file)

```
You are an IMPLEMENT worker for ticket #<N> in <repo>, running unattended in
your own worktree. There is NO orchestrator: your escalation targets are the
board itself (states, notes, comments) and the human on their next wake.
Turn-end messages are audit trail, not requests — nobody answers them. Your
ticket brief is below; treat it as the source of truth.

THE GATE comes before everything. Do not open a source file until the ticket
passes. Interrogate the brief the way a brainstorming grill interrogates a
human — but every answer must come from the ticket body, the codebase, or
repo docs. Trivial lookups (docs, grep, an API's actual shape) are orient
work: do them, never park for them.

Check 1 — WELL-DEFINED. Classify every fork the implementation will hit:
- Mechanical/technical with one obvious best answer (internal naming,
  idiomatic choice, repo precedent) → YOUR call. Parking these is a protocol
  violation, not caution.
- Non-trivial architecture (subsystem boundary, data model, API shape) →
  must be answered by ticket + codebase; unanswered → gate-fail.
- Product design or taste, major OR minor (user-facing behavior, wording,
  interaction/visual choices — anywhere a reasonable human could prefer
  differently on non-technical grounds) → must be answered by the ticket;
  unanswered → gate-fail. Even minor taste is never your call.

Check 2 — WELL-SCOPED. The work must fit ~1–2 ExecPlans. Too big? One
question decides: can the remainder be written down as self-contained child
pre-specs right now?
- Yes → DECOMPOSE. Register children via board-register.sh --parent <N>
  (+ --blocked-by between siblings where order matters; a chain IS
  serialization). Gate-triage each child honestly: ready-for-agent only if
  YOU believe it passes this gate; an open human decision → born needs-human;
  product-core → born interactive-preferred — required notes always. Register
  only children you can spec self-contained NOW; contingent later phases live
  as a ## Roadmap section in the parent body — the worker finishing phase K
  registers phase K+1 at PR time. Update the parent (roadmap + Decision log
  entry: why this cut), end your turn. Write no code.
- No — the slices need one continuously steered human context →
  board-transition.sh <N> interactive-preferred "<which decision areas need
  steering>"; end your turn.

VERDICT IS YOUR FIRST WRITE. Pass → board-transition.sh <N> in-progress plus
a one-line [gate] comment naming the verdict and execution mode. Fail → the
park state itself. Park discriminant — WHO UNPARKS IT:
- The human as themselves — a decision only they can make, or a real-world
  input only they possess (credentials, auth, production data) →
  needs-human. Note = the crisp question list, each with your recommended
  answer.
- Knowledge work anyone could do, but substantial enough to be its own
  work-unit (or its outcome needs human review before decisions harden) →
  needs-info. Note = what is missing and why gating cannot proceed.
- Ongoing steering, not one answer → interactive-preferred.

EXECUTION (gate passed) — choose in the [gate] comment:
- DIRECT: the pre-spec is the plan — TDD, commit, open the PR.
- EXECPLAN: 2+ milestones, or enough files/design sequencing that a fresh
  session would need the document to survive context death →
  doperpowers:execplan (the gate already served as its grill; author the
  ExecPlan from ticket + gate findings, execute to the letter).

YOUR AUTHORITY: your OWN ticket's open states via board-transition.sh (never
raw gh); registering decomposition children (--parent) and follow-up tickets
(--spawned-by) directly. NEVER: terminal states (done arrives by merge — your
PR body MUST say "Closes #<N>"; wontfix is the human's call — to recommend
it, set needs-human with the recommendation as the note); other tickets'
states (a cross-ticket observation is a comment on that ticket, nothing
more); scope beyond the ticket.

Opening your PR closes out your scope: register every residual as a ticket
(--spawned-by <N>) BEFORE your turn-end message, then list what you
registered (numbers) in a FOLLOW-UPS section — or the literal line
"FOLLOW-UPS: none". A follow-up not registered does not exist. From the PR
on, the review loop (doperpowers:reviewing-prs) owns the path to merge.
```

## Acceptance (observable behavior)

Protocol scenarios — each plants one temptation; a fresh-context daemon
spawned with nothing but Protocol v2 + the ticket body must land in exactly
one row:

| planted ticket | must happen | must NOT happen |
|---|---|---|
| clean, small, fully specified | direct build → PR, `[gate]` comment | park; ExecPlan ceremony |
| one *minor* taste fork buried in it | `needs-human`, question + recommended answer | any code; the worker "just picking one" |
| oversized but cleanly sliceable | children with `--parent`/`--blocked-by`, honest child triage, parent roadmap | code; speculative registration of contingent phases |
| product-core, taste throughout | `interactive-preferred` with orienting note | decomposition that shreds coherence |
| considerable but well-defined | ExecPlan authored, then executed | building straight off the ticket body |

Schema/scripts (extends `tests/issue-tracker/test-board-scripts.sh` on
`mock-gh`):

1. Three park states: legal from every open state; note enforcement on all
   three; repair reachability.
2. `blocked` gone: transition to it rejected; open `status:blocked` → lint
   FAIL with the needs-human FIX line.
3. `interactive-preferred`: never `ELIGIBLE` in board-list; own kanban
   column/DAG class; accepted by `board-register.sh --state`.
4. `in-review → needs-human` legal; `in-review → blocked` rejected.
5. `tests/reviewing-prs/test-review-dispatch.sh`: rendered protocol carries
   no `blocked` vocabulary.

End-to-end: a gate-passed ticket flows ticket → PR → review worker → merge →
`done` with zero orchestrator turns; the human's wake ritual is three
`board-list.sh` queries; `board-lint.sh` exits 0 on a migrated board.

## Assumptions to verify at plan time

- The exact current legality table in `board-transition.sh` (this spec names
  only the deltas; the full matrix is read at plan time).
- ida-solution's `issue-status-labels.yml` MANAGED-set mechanics and the
  count of open `status:blocked` tickets at migration time.
- The placeholder set Protocol v2 actually needs for interim hand-rendering
  (tech-debt issue number is referenced by reviewing-prs; confirm whether the
  implement protocol needs it too or drops it).

## Decision Log

- Decision: Approach A — new sibling skill `implementing-tickets` + schema
  surgery in issue-tracker; rejected B (rewrite issue-tracker in place — one
  file serving two actors, breaks the reviewing-prs symmetry, forces a later
  split anyway) and C (three-way re-layer with a fresh board skill — renames
  script paths consumers depend on for zero behavioral gain).
  Rationale: same reasoning as the reviewing-prs Decision Log — the loop has
  no orchestrator, so the actor's manual is not the board's manual.
  Date/Author: 2026-07-09 / human confirmed Claude's recommendation.

- Decision: The orchestrator-as-judge dies NOW; one protocol written for the
  no-orchestrator world; interim dispatch is a mechanical human-run ritual.
  Rejected: dual doctrine until the trigger lands; freezing dispatch.
  Rationale: under the gate, workers no longer produce orchestrator-grade
  questions — parks are by definition human-grade (needs-human) or work-units
  (needs-info), so the judge role has nothing left to judge.
  Date/Author: 2026-07-09 / human.

- Decision: Retire `blocked`; park vocabulary = needs-human / needs-info /
  interactive-preferred with the "who unparks it" discriminant. Rejected:
  keeping blocked alongside (empty intersection left for it), demoting
  interactive-preferred to a non-status marker label (splits eligibility
  across two namespaces).
  Rationale: the new needs-human definition absorbs blocked's entire meaning
  (credentials/auth/human-hand) plus the human-decision half of old
  needs-info; a state no worker can correctly choose is schema debt.
  Date/Author: 2026-07-09 / human.

- Decision: Serialize and decompose unify into ONE behavior — children under
  a parent; a blocked-by chain IS serialization. Rejected: the original
  three-way classification (serialize / interactive-preferred / decompose) as
  separate policies.
  Rationale: the board has exactly two edge types and both behaviors reduce
  to registering children; the real fork is only "can the remainder be
  written as self-contained child pre-specs now?" — no → interactive-preferred.
  Date/Author: 2026-07-09 / Claude proposed, human adopted.

- Decision: Fractal decomposition is emergent — no depth counters, no
  recursion machinery; the only rule is honest gate-triage of each registered
  child. Rejected: explicit recursion policy (depth limits, lineage checks,
  mandatory human review of grandchildren).
  Rationale: every dispatched worker re-runs the same gate from fresh
  context, which is already the recursion invariant. YAGNI on the rest.
  Date/Author: 2026-07-09 / delegated to Claude, human adopted.

- Decision: Execution is 2-way (direct vs execplan); the in-daemon
  execspec+writing-plans row is deleted. Rejected: always-execplan;
  keeping the 3-way.
  Rationale: a daemon driving the controlled track with nobody at the
  controls was a contradiction — that case is interactive-preferred by
  definition. The 2-way is a deletion from the existing protocol, not new
  structure.
  Date/Author: 2026-07-09 / delegated to Claude, human adopted.

- Decision: Even MINOR taste decisions gate-fail (asymmetric with
  architecture, where trivial calls are the worker's).
  Rationale: human's explicit directive — taste is where agent guessing costs
  the most trust per unit of saved time; mechanical/technical judgment is
  where worker autonomy is earned.
  Date/Author: 2026-07-09 / human (original directive).

- Decision: Just-in-time child registration — register only children
  specifiable as self-contained pre-specs now; contingent phases live as a
  parent-body Roadmap; the worker finishing phase K registers K+1 at PR time.
  Rejected: registering the whole chain speculatively.
  Rationale: preserves the issue-register bar (every ticket body
  self-contained for a fresh-context worker); a speculative ticket that can't
  meet the bar would just gate-fail later. The roadmap line is the one
  sanctioned "ticket that doesn't exist yet."
  Date/Author: 2026-07-09 / Claude judgment call, approved in section review.

- Decision: The JSON proposal block dies. Wontfix recommendation =
  needs-human on the worker's own ticket with the recommendation as note;
  cross-ticket observations = plain comment on the other ticket, never a
  state write. Follow-ups and decomposition children are registered DIRECTLY
  by the worker (extending the reviewing-prs precedent to the implement
  loop).
  Rationale: propose-only requires a judge to receive the proposal; this
  loop has none. Registration is additive and reversible — low blast radius.
  Date/Author: 2026-07-09 / approved in section review.

- Decision: The worker writes its own `in-progress` — the first board write
  IS the gate verdict; dispatch writes nothing.
  Rationale: makes the gate observable on the board itself and keeps the
  dispatcher fully mechanical.
  Date/Author: 2026-07-09 / approved in section review.

- Decision: `orchestrating-daemons` keeps its judge doctrine — the judge dies
  in the ticket pipeline only, not for ad-hoc conversational fleets.
  Date/Author: 2026-07-09 / approved in section review.

- Decision: Scoped OUT of this phase: the auto-attach trigger mechanism
  (issue-event workflow/runner/sweep — implementing-tickets/scripts/ is its
  future home) and the Slack connector for the needs-human queue.
  Date/Author: 2026-07-09 / human (original directive).

## Surprises & Discoveries

- Observation: the new `needs-human` definition empties `blocked` exactly —
  today's blocked ("credentials / auth / human hand") is verbatim the
  real-world-input half of needs-human, and ticket-on-ticket waiting was
  already edges, never a state. Retirement is absorption, not amputation.
  Evidence: state table + discriminant in skills/issue-tracker/SKILL.md
  (pre-change).

- Observation: the current Worker Protocol already contained the 2-way
  execution split in embryo — its 3-way ORIENT block's third row (in-daemon
  execspec + writing-plans) is the only part this design deletes, and that
  row described a daemon driving the human-gated controlled track with no
  human present.
  Evidence: Worker Protocol block in skills/issue-tracker/SKILL.md
  (pre-change).

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-09: Initial spec from brainstorm (controlled track). Decision Log
  seeded with the approach fork (A over B/C), the judge-dies-now scope call,
  the blocked retirement, the serialize/decompose unification, emergent
  fractal, 2-way execution, the minor-taste rule, JIT registration, the death
  of the proposal block, and the scope-outs (trigger mechanism, Slack
  connector).
