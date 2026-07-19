# Conditional sub-slicing — invariant-based decomposition inside one slice (2026-07-19)

## Purpose

doperpowers' unit of work is the Slice: one spec drives one plan (controlled)
or one ExecPlan (autonomous). `writing-plans` handles the case where a spec
spans multiple independent subsystems (Scope Check → separate plans), but has
no doctrine for the opposite failure: a slice that is *one* legitimate spec
yet internally multi-unit — several state owners, invariants, and failure
modes hiding under one brief.

The evidence is Task 8 of ida-solution's M5 Phase 4 Slice 1 (vault:
`Big Slice Dev/`): a slice that grew to ~54 files / 20k+ lines, where review
kept surfacing new Important findings at the same seam, each fix adding
another ref/flag/condition. It was rescued only when the runaway area was
restructured into seven independently designed and verified sub-units
(contracts → cache observation → service wiring → refresh coordinator →
reconciliation → React driver → acceptance), after which stability recovered
immediately. This spec encodes the generalized lesson into the two skills
where its halves fire.

## What the case showed

- **The split criterion is invariants, never size.** The slice contained at
  least three different concurrency models (PostgreSQL transaction writer,
  multi-read cache/recovery consistency, async UI ordering) under one brief.
  Each needed different design tools and a different test harness. File
  count, technical layers, and line count were never the signal.
- **The cohesion counter-case is equally load-bearing.** The follow-up PR2
  (auto-adjust proposalization) spans lifecycle RPC + rule producer +
  parameter consumer — three technical areas — but shares one approval
  invariant and one rollout gate; splitting it would create invalid
  intermediate products (proposals that approve to nothing). The doctrine
  must block over-splitting as firmly as under-splitting.
- **Three altitudes were being conflated:** product slice/PR (one end-to-end
  invariant, one rollout gate) vs implementation sub-slice / task group (one
  state owner, own behavior test, own scoped review, *inside* one plan) vs
  TDD step. Task 8 needed the middle altitude — not more PRs.
- **The rescue signal fires at run time, not plan time.** Repeated Important
  findings at one seam — each fix breeding the next — is a structure signal.
  It arrives during subagent-driven development, where `writing-plans` is not
  in context; a note only there would miss the moment that actually turned
  Task 8 around.
- **The root cause under it all:** a functional brief without a state
  model. Concurrency-shaped work implemented from feature requirements alone
  becomes an implicit distributed state machine, built one ref at a time.

## Design

Two texts. Wording below is near-final (approved in design review; final
polish at implementation).

**1. New section in `skills/writing-plans/SKILL.md`, after Scope Check:**

> ## Conditional Sub-Slicing
>
> Default to the smallest cohesive plan that delivers the spec's end-to-end
> invariant. Never split merely because the work touches many files or
> crosses technical layers — file count is not a boundary.
>
> Consider sub-slicing when parts of the work have **different state owners,
> invariants, failure modes, or verification strategies** — e.g. a database
> transaction contract, a pure domain state machine, and async UI
> coordination are three units, not one. A good sub-slice has an explicit
> input/output contract, its own focused behavior test, and a review
> boundary a reviewer can approve without reading its neighbors.
>
> Keep parts together when splitting would create an invalid intermediate
> state, when they must land in the same transaction or cutover, or when
> neither part is meaningful or verifiable alone.
>
> Expression ladder — use the lightest rung that fits:
> 1. **Task groups within this plan** (default) — one group per state
>    owner; each group gets its own implement→review cycle before the next
>    begins.
> 2. **Multiple plans for one spec** — when the slice is genuinely
>    multi-unit and each group would need its own file-structure and
>    interface design.
> 3. **Mid-flight promotion** — when implementation reveals a runaway area
>    (see the escalation signal in doperpowers:subagent-driven-development),
>    promote it to its own sub-spec/plan referenced from the parent, rather
>    than patching on.
>
> For concurrency-shaped work, the plan fixes the event list, states,
> transition table, and linearization points before implementation — a
> functional brief alone is how implicit distributed state machines get
> built one ref at a time.
>
> Sub-slicing is a judgment tool, not ceremony: the fewest boundaries that
> make each important invariant independently understandable and testable.

**2. New section in `skills/subagent-driven-development/SKILL.md`:**

> ## Escalation Signal: Repeated Findings at One Seam
>
> If review keeps surfacing new Important findings in the same area — and
> each fix adds another flag, ref, or condition — stop the patch loop. That
> is a structure signal, not an implementation-quality signal: reassess
> state ownership and decomposition per Conditional Sub-Slicing in
> doperpowers:writing-plans, and consider promoting the area to its own
> sub-spec/plan before dispatching the next task.

## Acceptance

Behavior-phrased, run as fresh-context pressure sessions
(doperpowers:writing-skills style):

- A planning session given a Task-8-shaped brief (three concurrency models
  under one feature brief) produces a plan whose tasks group along state
  ownership boundaries — not one flat task list, not a split by technical
  layer.
- A planning session given a PR2-shaped brief (multiple technical layers,
  one shared approval invariant and rollout gate) keeps the plan cohesive
  and does not propose separate plans/PRs.
- A scenario Q&A presenting an SDD transcript summary with two rounds of
  Important findings at the same seam (each fix adding a flag) yields
  "reassess decomposition/ownership" — not a third patch dispatch. (Weakest
  test: signal-recognition by Q&A, not a live loop; stated honestly.)

## Decision Log

1. **Placement: full note in writing-plans + 2–3 line escalation echo in
   subagent-driven-development.** Rejected: writing-plans only (the human's
   initial phrasing) — the run-time half of the doctrine, the one that
   actually rescued Task 8, would live in a skill not loaded during
   execution. Rejected: spreading to execplan and implementing-tickets —
   execplan's PLANS.md milestone structure already is its sub-unit
   mechanism, and implementing-tickets already carries oversized-ticket
   decomposition; more copies is doctrine sprawl.
2. **Task-groups-in-one-plan is the default rung; multiple-plans-per-spec is
   the escalation.** Rejected: multiple plans as the primary expression (the
   initiating prompt's framing) — the case retrospective is explicit that
   the ideal Slice 1 shape was ONE plan with three task groups, with
   promotion only when a group outgrew it mid-flight.
3. **The concurrency clause (events/states/transitions before
   implementation) is included, one sentence.** Rejected: keeping the note
   strictly about sub-slicing — the case analysis ranks the missing state
   model as the root cause above the missing decomposition; one line buys
   the highest-value lesson.
4. **Soft doctrine, no numeric thresholds.** Rejected: rules like "≥3
   review units → split" — the source retrospective itself rejects the
   numeric form; the repo's golden rule requires hard constraints to map to
   validated failure states, and the validated failures here are structural
   (invariant mixing, invalid intermediates), not numeric.

## Surprises & Discoveries

- The vault 회고 already contained a generalized English doctrine draft
  (its §6), close to drop-in quality — this spec's work was compression and
  placement, not invention.
- The source case's own retrospective spends as much text warning against
  over-splitting (PR2, ceremony-exceeds-implementation) as against
  under-splitting — the doctrine's anti-criteria are original evidence, not
  balance-for-balance's-sake.

## Outcomes & Retrospective

Pending — written after the pressure sessions pass and the next real
multi-unit slice exercises the ladder.

## Revision Notes

(none yet)
