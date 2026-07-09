# Worker Dispatch Gate — Definition-of-Ready for implementing daemons

## Purpose

Today an implementing daemon dispatched onto a `ready-for-agent` ticket
starts building on the strength of one paragraph: the Worker Protocol's
ORIENT block tells it to size the work and pick a method, and a single
"ambiguous? brainstorm it" sentence guards everything else. Nothing forces
the daemon to establish, before opening a source file, that the ticket is
actually **well-defined** (no non-trivial architecture/product/taste decision
left open) and **well-scoped** (fits 1–2 ExecPlans). The cost of skipping
that check is the most expensive failure mode the pipeline has: a daemon
autonomously implementing an ambiguously scoped task.

After this change, every implementing worker runs a **dispatch gate** as its
phase 0 — the worker-side Definition-of-Ready, the symmetric counterpart of
the review loop's self-merge rubric. Where the review worker asks "may this
PR merge?", the implementing worker asks "may this ticket be built?". A
ticket that fails the gate never gets code; it gets parked into a precise
escalation state, decomposed into child tickets, or flagged for a
human-driven session — each outcome a board write with a recorded verdict.

How to see it working: dispatch a daemon onto a ticket with an open taste
decision; the daemon writes a `[board]` gate comment, moves the ticket to
`needs-human` with the question as the note, and ends its turn without
touching a source file. Dispatch one onto a well-defined ticket that is too
big; the ticket becomes an epic with freshly registered child tickets and a
roadmap in its body.

**Terms of art.** *Dispatch gate*: the mandatory phase-0 check (definition →
scope → method) in the Worker Protocol. *Well-defined*: no non-trivial
architecture/product/taste decision left for a human. *Well-scoped*: fits
1–2 ExecPlans. *Decision coupling*: taste/architecture decisions that span
would-be slices, so decomposing would make each child re-ask the same
question. *Decompose signature*: a child registered with `--parent X
--spawned-by X` pointing at the same ticket — the marker that it was born of
self-decomposition. *Human inbox*: the set of tickets in `needs-human` or
`interactive-preferred`.

## The gate

Rendered into every spawn prompt as the first section of the extracted
Worker Protocol. Runs before the worker opens any source file:

```
1. DEFINITION GATE — enumerate the undecided non-trivial
   architecture/product/taste decisions.
   For each: if the codebase or research can answer it, answer it yourself
   and append the decision to the ticket's Decision log, then continue.
   (Self-answer first — over-parking kills the loop's value.)
   For the remaining human-only questions:
   ├─ discrete, answerable asynchronously            → needs-human
   │    (the questions ARE the note)
   ├─ missing knowledge an agent could gather         → needs-info
   │    (research it yourself, or park for a research pass)
   └─ entangled/generative (answering one spawns the
      next — a live session is the right bandwidth)   → interactive-preferred

2. SCOPE GATE — does the work fit 1–2 ExecPlans?
   ├─ no, and no decision coupling across slices      → DECOMPOSE
   ├─ no, with decision coupling                      → interactive-preferred
   └─ yes → 3

3. METHOD — trivial/mechanical (one obvious change, no design fork)
   → do it inline; anything else → doperpowers:execplan.
   (The autonomous-execspec branch is deleted: execspec is the controlled,
   human-in-loop mode — an unattended daemon running it alone was a
   contradiction in the old ORIENT text.)

Record the verdict as a [board] trail comment either way:
  "gate: defined ✓ scoped ✓ method: execplan"
  "gate: parked needs-human — <the questions>"
  "gate: decomposed into #A #B #C — roadmap in body"
```

The three moves are exhaustive and ordered: definition failures park before
scope is judged; scope failures resolve before a method is picked; a ticket
that reaches step 3 is by construction well-defined and well-scoped.

## State vocabulary

The discriminant changes from *what is missing* to **who can resolve it** —
a state is a queue, and a queue is defined by its consumer and its exit
transition.

| state | meaning | resolver / exit | note |
|---|---|---|---|
| `needs-human` **(new)** | only a human can unblock: architecture/product/taste decision, credentials, real production inputs | human answers asynchronously → decision recorded in the ticket's Decision log → back to `ready-for-agent` | **required** |
| `needs-info` **(redefined, rare)** | knowledge is missing that an agent could gather: a research spike, or a spec that is clear but too shallow to build from | an agent (the worker itself, or a future research pass) gathers it and returns | **required** |
| `blocked` **(narrowed)** | waiting on an external event that is neither a human decision nor gatherable knowledge: a third-party release, a deploy window | the event happens | **required** |
| `interactive-preferred` **(new)** | not daemon-dispatchable: needs a human-driven session (brainstorming → execspec) — decision density too high for async Q&A | a human session picks it up; **both exits are legal**: drive it to PR in-session (`in-progress → in-review → done`), or settle the decisions / re-scope and return it to `ready-for-agent` | **required** |

`needs-human` and `interactive-preferred` rows are the human's inbox — the
queue a future Slack connector drains (explicitly out of scope here).

Existing `needs-info` tickets that are really human decisions get re-triaged
by hand at the next reconcile; lint does not force a migration.

## Decompose

The old idea of "serialize" is not a separate action: serialization is
decomposition whose children carry a `blocked_by` chain. One action, one
mechanism, edge structure expressing seriality where it exists.

Procedure (worker-side):

1. Write the roadmap into the parent ticket's body (around the `board:meta`
   block).
2. Register each child via `board-register.sh … --parent <own> --spawned-by
   <own>` — the decompose signature — plus `--blocked-by` chains only where
   phases are genuinely serial. Every phase is a child, **including phase
   1**: the parent becomes a pure epic (epics are never dispatched; the
   existing sweeps move them).
3. Post the gate trail comment naming the children.
4. End the turn. The worktree is untouched (no code was written) and is
   auto-cleaned; the daemon retires; children enter the normal dispatch
   loop.

**Authority extension.** Workers today write only their own ticket's open
states. This change grants exactly one more power: a worker may register
**children of its own ticket** (`--parent`/`--spawned-by` both equal to its
own number). FOLLOW-UPS registration stays with the orchestrator at finalize
— decompose is a pre-build structural decision; follow-ups are post-PR
residue. Different moment, different authority.

**Recursion is free; churn is guarded.** A child is just a ticket, so its
own dispatch runs the same gate — the fractal property needs no machinery.
The only failure mode is decomposition without work landing, guarded by a
hard rule: a ticket born of decompose (its own `parent == spawned-by`) may
NOT decompose again — if it still does not fit, that is a `needs-human`
escalation (a human may grant an exception). Lint backs the rule up (below).

## Protocol extraction

The Worker Protocol moves out of the issue-tracker SKILL.md into
`skills/issue-tracker/references/worker-protocol.md`, mirroring
`reviewing-prs/references/review-worker-protocol.md`. The gate is its first
section; the surviving rules (own-ticket-only writes, no terminal states,
JSON proposal block, FOLLOW-UPS contract, turn-end discipline) carry over
with the escalation discriminant updated to the new three-way vocabulary.

Dispatch-loop step 2 in SKILL.md becomes: *spawn prompt = full issue body +
the contents of `references/worker-protocol.md` with `<N>` filled in.* No
render script — plain substitution, same as today.

The two-roles table gains the child-registration power; the state table is
replaced by the vocabulary above; `issue-register`'s register-time state
hints get a one-line update to the new vocabulary. `orchestrating-daemons`
and `reviewing-prs` are untouched. Ships as **7.10.0** via
`scripts/bump-version.sh` (behavior addition = minor).

## Lint

`board-lint.sh` gains three checks:

1. Notes required on `needs-human` and `interactive-preferred` (same
   mechanism as `blocked`/`needs-info`).
2. **WARN** on an epic chain of depth ≥ 3 (epic whose parent's parent is
   also an epic) — decomposition churn smell.
3. **FAIL** (with FIX line) on a re-decomposed decompose-child: a ticket
   whose own `parent == spawned-by` and which itself has sub-issues. The
   exception is structural, not an annotation: the signature marks
   *self*-decomposition by a worker, so a human-approved nested
   decomposition — performed by the orchestrator after the `needs-human`
   escalation — registers the grandchildren with `--spawned-by` pointing at
   the origin epic (or the session's ticket), never at their own parent.
   Sanctioned nesting therefore never carries the self-signature and lint
   stays green; the FIX line says exactly that.

## Acceptance

- A worker dispatched onto a ticket with an open taste decision ends its
  turn with the ticket in `needs-human`, the questions in the note, a gate
  trail comment, and zero source files touched.
- A worker dispatched onto a well-defined but oversized ticket without
  decision coupling ends its turn with the parent an epic (roadmap in body),
  children registered with the decompose signature and correct `blocked_by`
  chains, and a trail comment naming them.
- A worker dispatched onto an oversized ticket **with** decision coupling —
  or a decision-dense ticket — ends its turn with the ticket in
  `interactive-preferred` and a note saying why a live session is the right
  bandwidth.
- A worker dispatched onto a well-defined, well-scoped ticket posts a
  passing gate comment and proceeds (inline for trivial work, execplan
  otherwise); no autonomous execspec run exists anywhere in the protocol.
- A decompose-born child that tries to decompose again is caught: the
  protocol routes it to `needs-human`, and if one slips through, lint FAILs
  the board.
- `board-transition.sh` accepts the two new states from any open state,
  refuses them without a note, and `board-list.sh`/`BOARD.html` display
  them; `board-lint.sh` passes on a healthy board exercising all new states.
- `tests/issue-tracker/test-board-scripts.sh` covers: new-state transitions
  and note enforcement, decompose-signature registration, depth-3 WARN, and
  the re-decompose FAIL.

## Out of scope

- Slack (or any) connector draining the human inbox — later phase.
- A dedicated research-daemon loop consuming `needs-info` tickets (the
  redefinition deliberately makes them dispatchable to one later).
- Automated re-triage of legacy `needs-info` tickets.
- Any change to reviewing-prs, orchestrating-daemons, or the consumer label
  automation.
- An observation/staged-rollout mode: unlike self-merge, every gate outcome
  is a reversible board write, so the trail comments themselves are the
  observation channel.

## Decision Log

- **2026-07-09 — Serialize and decompose unified into one action.** A serial
  roadmap is decomposition plus a `blocked_by` chain; the board already
  expresses ordering as edges and eligibility as computation. Rejected: the
  original three-way classification (serialize / interactive / decompose) —
  two of the three were the same mechanism with different edge shapes.
- **2026-07-09 — Discriminant is "who resolves it", not "what is missing".**
  `needs-human` = human-only (decisions, taste, credentials, production
  inputs); `needs-info` = agent-gatherable knowledge (rare); `blocked` =
  external events. Rejected: folding `blocked` into `needs-human` (would
  pollute the human inbox with non-decision waits); rejected: keeping the
  two-state vocabulary with redefinitions only (loses the human-inbox queue).
- **2026-07-09 — `interactive-preferred` is its own state, both exits
  legal.** Its queue semantics differ from `needs-human`: the human occupies
  a session rather than dropping an answer. A session may drive the ticket
  to PR itself or re-scope and hand it back — both legal transitions.
  Rejected: modeling it as a flavor of `needs-human`.
- **2026-07-09 — Worker authority extended to own-children registration
  only.** Bounded by the decompose signature (`--parent`/`--spawned-by` =
  own ticket), lintable, consistent with the reviewing-prs precedent of
  orchestrator-less writes. Rejected: proposal-only decomposition (stalls
  when the orchestrator sleeps); rejected: full registration authority
  (board pollution risk).
- **2026-07-09 — No fractal machinery; a churn guard instead.** Recursion
  falls out of "the gate runs per-ticket at dispatch". Hard rule:
  decompose-children may not re-decompose (needs-human instead), backed by a
  lint FAIL plus a depth-3 WARN. Rejected: building explicit recursive
  decomposition support (YAGNI); rejected: no guard at all (unattended
  ticket-multiplication risk).
- **2026-07-09 — Execution stays two-way; autonomous execspec deleted.**
  Trivial → inline, else → execplan. The old ORIENT's "large → execspec"
  contradicted the two-track methodology (execspec is the controlled,
  human-gated mode). The gate now routes large/tasteful work to
  interactive-preferred or decompose instead.
- **2026-07-09 — Protocol extracted to `references/worker-protocol.md`
  (Approach B).** Mirrors review-worker-protocol.md; the gate would have
  doubled the embedded block inside SKILL.md. Rejected: inline expansion
  (Approach A — unmaintainable at ~100 lines embedded); rejected: a separate
  dispatch-gate skill (Approach C — the gate is meaningless without the
  board vocabulary; cohesion loss).
- **2026-07-09 — Decompose signature instead of new metadata.** `parent ==
  spawned-by` already implies "born of self-decomposition"; no new label or
  meta field. Smaller schema, stronger lint.

## Surprises & Discoveries

- The working tree carried an uncommitted edit to
  `skills/brainstorming/SKILL.md` reverting the 7.9.0 "recommend the track,
  then confirm" language back to the older "human chooses, controlled
  default" style — likely a parallel-session leftover; flagged to the human
  during brainstorming, not part of this change.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-09 — Initial spec from brainstorming session (gate skeleton,
  vocabulary re-carve, decompose mechanics, authority, guards).
