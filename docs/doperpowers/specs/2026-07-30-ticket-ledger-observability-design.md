# Ticket Ledger & Observability Doctrine (2026-07-30)

> **Status:** design approved in-session (ideadump roadmapping, epic E2).
> **Substrate target:** the AI-native Postgres board (2026-07-30
> cloud-native pipeline pivot: Postgres is the SSOT; GitHub Issues and
> Linear are one-way mirrors). On the interim GitHub board, worker
> behavior stays byte-identical to v8 — the derived stream below requires
> the Postgres convergence and simply doesn't exist there yet.

## Purpose

At swarm scale the human cannot attach to thousands of sessions, and the
stretches between a worker's scope-end writes are silent. The ideadump
proposed making the ticket a continuously-written report ledger; the
pipeline's recorded doctrine says the opposite ("there is no live
progress mirror — scope-end writes are the only status writes"). This
spec resolves the tension without reversing either intent: **what
workers author stays exactly as today (decisions only), and the silence
between decisions is filled by a derived, read-only stream** — possible
now because the board and the session transcripts land in the same
Postgres (sessionStore adapter shipped 2026-07-30), with OTel carrying
session-tagged telemetry.

After this: a human opens a ticket and sees one merged timeline — every
decision event AND what the bound session is actually doing — with zero
additional worker writes; non-blocking environmental friction has a
first-class address instead of dying in chat logs.

## The ledger (hybrid)

- **Worker-authored stream = decisions only** (unchanged doctrine):
  state transitions, parks (batch questions with recommended answers),
  gate verdicts, answers, closing artifacts (the Architect's plan note,
  the Implementer's PR). Workers author no progress prose; worker
  turn-end messages remain audit trail, not communication — the board is
  the communication surface (v8 doctrine, restated for the swarm).
- **Derived stream = read-only view** over the sessionStore transcripts
  and OTel telemetry of the ticket's bound session(s), joined on the
  ticket↔session binding. No worker cooperation required; rendering
  (timeline UI, activity summaries) is E3's concern.
- **The human-visible ledger = the merged timeline of both streams.**

## Write semantics

- **Event log: append-only.** Every transition, park, answer, and
  verdict is an immutable event (the audit trail — v8's `[board]`
  comments, made structural).
- **Current-state fields: mutable.** Status, priority, current note,
  `plan:`, branch, PR, binding (v8's `board:meta` block, made columns).
- **Writers:** the bound accountable worker (its own ticket only), the
  human, and pipeline automation (sweep, dispatch). **Subagents never
  write** — their output flows through the accountable worker (the
  accountability model: one accountable agent per ticket). The derived
  stream is read-only by construction.

## The env-issue lane

- A new ticket category **`env-issue`**: non-blocking environmental
  friction (missing tool in the pod image, flaky registry, broken test
  fixture that the worker routed around) filed by ANY worker through its
  existing registration authority (`--spawned-by <its ticket>`), after
  the standard search-before-register dedup. Filing is fire-and-continue
  — the worker's own ticket is never parked for it.
- Blocking environmental failure remains what it is today: a park on the
  worker's own ticket. The PR `## Confusions` section remains the
  PR-time record; register an env-issue when the friction is actionable
  or likely to recur for other workers.
- **Consumers:** the ops-agent sweep (the cloud program's R3 lane) and
  the human wake queue. This is the "silent issue" killer from the
  ideadump: friction becomes a board object with a resolution loop, not
  a log line.

## Naming

**"ticket" stays.** The doctrine term for the concept remains
purpose-unit; renaming the everyday word would churn every skill and
script for cosmetic gain. What the E3 UI displays on a node is a surface
decision deferred to E3.

## Acceptance (observable)

1. A ticket's rendered timeline (E3) interleaves decision events with
   derived session activity — and diffing the worker protocols against
   v8 shows zero new write duties.
2. A worker files an `env-issue` ticket mid-build and its own ticket
   proceeds uninterrupted — no park, no state change on its ticket.
3. Any past board state is reconstructible from the event log alone
   (append-only); reading current state never requires folding the log.
4. On the interim GitHub board, a v8 worker transcript and a post-E2
   worker transcript are indistinguishable (no new duties there).

## Deferred

- Timeline/queue rendering, activity summarization, and node display
  naming — E3 (control-plane product).
- Mirror field-mapping (which columns flow to the GitHub/Linear
  mirrors) — board-platform work in the cloud program's round.
- Retention/compaction policy for the derived stream.

## Decision Log

- Decision: Hybrid ledger — worker-authored decisions + derived
  read-only progress stream, merged at render time.
  Rationale: fills the between-scope silence at zero token cost and
  zero doctrine reversal; the Postgres convergence (board + sessionStore
  in one database) makes the derived stream a join, not a duty.
  Rejected: worker-authored continuous ledger (reverses the recorded
  scope-end doctrine, pays tokens for prose nobody may read); status quo
  (leaves the swarm's silent stretches unsolved).
  Date/Author: 2026-07-30, human.
- Decision: Append-only event log + mutable current-state fields.
  Rationale: mirrors v8's proven split (audit comments vs meta block),
  made structural on Postgres.
  Date/Author: 2026-07-30, session decision, human-informed.
- Decision: Write authority = bound worker + human + automation;
  subagents excluded; derived stream read-only.
  Rationale: the accountability model — one accountable agent per
  ticket; subagent output flows through it.
  Date/Author: 2026-07-30, human (ideadump) + session.
- Decision: env-issue = board-native ticket category via existing
  registration authority.
  Rationale: zero new substrate (the NO-NEW-SUBSTRATE precedent),
  aggregation is a board query, the resolution loop comes free, and the
  R3 ops agent is a natural consumer. Rejected: dedicated report
  table/tool (a second state system needing its own ack loop);
  OTel-events-only (no resolution loop — the silent-issue problem
  restated).
  Date/Author: 2026-07-30, human.
- Decision: Keep "ticket".
  Rationale: rename = whole-vocabulary churn for cosmetic gain;
  purpose-unit already carries the doctrine; UI display naming is E3's.
  Rejected: new platform-wide name; UI-only alias decided now.
  Date/Author: 2026-07-30, human.

## Surprises & Discoveries

- Observation: The ideadump's core demand — "report at the ledger
  instead of the final message" — was ALREADY v8 doctrine at scope ends
  (turn-ends are audit trail; the board is the communication surface).
  The real gap was between scope ends, and the Postgres convergence
  turned filling it from a doctrine reversal into a join.
  Evidence: implementing-tickets "no live progress mirror" paragraph;
  Postgres sessionStore adapter shipped 2026-07-30 (cc-harness).

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-30: v1, authored from the E2 grill of the ideadump roadmapping
  session (ledger essence → write semantics → env channel → naming).
