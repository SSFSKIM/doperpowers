# Ticket Ledger & Observability Doctrine (2026-07-30)

> **Status:** v2 — matured 2026-08-01 through a pre-implementation
> brainstorming review (grill + three independent code/spec/store
> investigations). E2 is the ledger **domain contract**: it fixes
> semantics, write authority, binding identity, and lifecycle rules.
> Implementation is split across four separately-owned deliveries
> (§ Implementation ownership); E2 closes when the interim doperpowers
> slice ships and the contract herein is complete — it does NOT wait for
> the E3 platform to render the ledger.
> **Substrate target:** the AI-native Postgres board (2026-07-30
> cloud-native pipeline pivot: Postgres is the SSOT; GitHub Issues and
> Linear are one-way mirrors). On the interim GitHub board, worker
> behavior stays byte-identical to v8 modulo the E1 lane-split
> vocabulary (which lands there independently) and the additions named
> in § Interim slice — the derived stream requires the Postgres
> convergence and simply doesn't exist there yet.

## Purpose

At swarm scale the human cannot attach to thousands of sessions, and the
stretches between a worker's scope-end writes are silent. The ideadump
proposed making the ticket a continuously-written report ledger; the
pipeline's recorded doctrine says the opposite ("there is no live
progress mirror — scope-end writes are the only status writes"). This
spec resolves the tension without reversing either intent: **what
workers author stays exactly as today (decisions only), and the silence
between decisions is filled by a derived, read-only stream** — possible
because the board and the session transcripts land in the same Postgres
(sessionStore adapter shipped 2026-07-30), with trusted harness hooks
carrying live activity and OTel carrying operational telemetry.

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
- **Derived stream = read-only view** over the ticket's bound sessions,
  sourced per the hierarchy below. Read-only means **workers and UI
  clients cannot mutate it**; trusted platform automation (the hook
  emitter, the mirror machinery) appends immutable derived records by
  construction. Rendering (timeline UI, activity summaries) is E3's
  concern.
- **The human-visible ledger = the merged timeline of both streams.**

### Source hierarchy (v2)

The derived stream's sources, in trust order — each with an honest
completeness contract:

1. **Board events** — authoritative. Decisions, transitions, claims,
   parks, answers, verdicts. The only source that is allowed to imply
   workflow truth.
2. **SessionStore transcripts** — durable history at TURN grain. The
   shipped adapter persists opaque entries keyed
   `(project_key, session_id, subpath)` with per-transcript `id`
   ordering and a coarse `mtime` liveness hint. It is an archival
   mirror, not a live feed: mirror batches can drop after retries,
   in-flight turns are lost on eviction, and rewind-in-place is
   destructive. Native subagents live as `subpath` transcripts under
   the parent session, not as independent sessions.
3. **Trusted hook activity events** — the live intra-turn carrier
   (cc-harness T11): a trusted harness hook appends structured activity
   records (tool starts/ends, prompt boundaries) to the board-owned
   activity stream. Automation-authored, immutable, worker-read-only.
4. **OTel telemetry** — operations plane ONLY: metrics, alerting, and
   correlation (`session.id`, `prompt.id`, resource attributes). OTLP
   permits loss, duplication, and reordering by design; OTel is never a
   canonical human-timeline source. (v1 named it a primary carrier;
   v2 demotes it — Decision Log.)

**Ordering semantics:** there is no causal total order across sources.
Every derived record carries its source, a source-local cursor
(e.g. transcript entry id), observed-at time, and optional source time;
consumers may interleave heuristically but the contract promises
per-source order only. Source time and observation time are distinct
fields, never conflated.

**Access contract:** consumers read the ledger through a logical
`TimelineReader` interface, not raw cross-schema SQL. The initial
implementation may union board events and sessionStore entries in one
Postgres; a later sessionStore promotion (separate DB, archive tier)
must preserve the interface, not the join.

## Write semantics

- **Event log: append-only.** Every transition, park, answer, verdict,
  claim, bind, release, and reclaim is an immutable event (the audit
  trail — v8's `[board]` comments, made structural) — plus a
  `field-change` event for every mutable-field write (priority,
  `plan:`, branch, PR, note), so acceptance 7's reconstruction claim
  holds for the whole board state, not just workflow state.
- **Current-state fields: mutable.** Status, priority, current note,
  `plan:`, branch, PR, `owner_run` (v8's `board:meta` block, made
  columns).
- **Writers:** the bound accountable worker — its own ticket's open
  states, plus registering NEW child/follow-up/env-issue tickets (the
  full v8 registration authority, restated whole) — the human, the
  sweep, and **control-plane automation for claim-lifecycle records
  only** (next section). **Subagents never write** — their output flows
  through the accountable worker (the accountability model: one
  accountable agent per ticket). The derived stream is
  worker-read-only by construction.

### Dispatch writes claims, never workflow state (v2)

v1's "dispatch writes nothing" conflated two invariants; v2 narrows it:

- **Dispatch makes no workflow-state transition.** It cannot move a
  ticket between lanes, and the worker's first workflow decision on the
  board remains its own (E1: the gate verdict or the plan-execution
  `in-progress` note).
- **Dispatch automation MUST write claim-lifecycle records:** one
  fenced transaction creates the `run`, sets the ticket's `owner_run`,
  and appends a `claim` event (actor: automation). Without this there
  is no ticket↔session attribution and no reconstructible claim
  history.
- **Phase end is one transaction:** close the run, clear `owner_run`,
  append a `release` event — executed by the transition endpoint
  itself, atomically with the state write that ends the phase (not by
  a separate observer that could lag or die between the two). (The
  stale R2 draft leaves `owner_run` uncleared on lane crossings, which
  would strand every Architect→Implementer handoff unclaimable —
  named rebase defect, § R2 rebase.)

**Run state at parks and exits** — the "at most one active run"
invariant needs every exit class mapped:

- `needs-human` / `interactive-preferred`: a PAUSE — the run stays
  open and bound; the answered resume is the same run.
- `needs-info`, `deferred`, `wontfix`, `done`, and every lane
  crossing: a SCOPE END — the run closes in the same transaction as
  the transition. `needs-info` in particular is fold-and-recut (E1):
  the later re-dispatch is a fresh claim, never a resume; leaving its
  run open would let a later dispatch create a second active run.

## Binding identity: ticket → run → session (v2)

The doctrine phrase stays **"ticket ↔ accountable claim."** One ticket,
one accountable execution — carried by a relay team (Architect →
Implementer → QAgent on a planned leaf), each phase holding its own
exclusive claim. The storage contract beneath the phrase:

- A **ticket** has at most one active **run** and an immutable history
  of runs. The runs collectively form the ticket's accountable
  execution.
- A **run** is one fenced claim for one lane/phase. It records the
  accountable lane, fence, lifecycle timestamps, and the exact
  session-store locator: **(store namespace, project_key,
  session_id)** — the composite key the shipped adapter actually uses,
  not a bare session id.
- The binding is recorded by trusted automation, **verified against
  the real session identity at initialization** — never a worker-prompt
  duty. (Whether the runtime observes the id at `system/init` or
  preassigns and verifies it is the cc-harness owner's choice; the
  contract fixes the end, not the mechanism.)
- `owner_run` is the ticket's mutable pointer to its current claimant;
  history lives in claim/bind/release/reclaim/supersede events, never
  by overwrite.
- **Same run:** process or appserver-thread restart that keeps the
  claim and resumes the same SDK session.
- **New run:** reclaim after ownership loss (even when it resumes the
  prior session — with an explicit predecessor link), and every fork
  (a forked session id is a successor binding with provenance).
- **Native subagents** ride the parent session's `subpath` transcripts
  under the parent's run — never modeled as independently resumable
  sessions. A detached child session requires its own explicit binding
  and parent-run edge.

This gives E3 both historical attribution (timeline reads all runs) and
live-terminal authorization (only the current run's thread/pod may
attach).

## Node lifecycle: leaves and recomposition (v2)

A ticket = a purpose unit = one reliably-ownable goal (the decomposing
gate). The tree decides ownability; the lane protocol decides which
relay roles the unit needs:

- **Implementation leaf:** Architect (size-gated) → Implementer →
  QAgent. Small leaves skip the Architect (E1 DIRECT); spikes end in
  findings.
- **Non-leaf (epic):** the Architect brackets it — decompose at the
  start, recompose at the end. No Implementer phase, and no QAgent
  phase from its own lane protocol (the shape-gated scale review below
  is the exception); while children execute, the parent holds no
  **standing** worker claim (transient reconciliation claims
  excepted).

### Recomposition replaces epic auto-close

The interim board's mechanical close (`close_epics`: all children
terminal + one done ⇒ parent done) is a doctrine violation — the
decomposing skill requires closing a parent by VERIFICATION against its
own whole-unit acceptance, not by bookkeeping. v2 fixes the return
path:

1. **Trigger:** all children terminal ("required" = every child; the
   board has no optionality machinery and this spec adds none) ⇒ the
   parent returns to `ready-for-architect` with a `recomposition-due`
   note, never directly to done. The old at-least-one-done guard is
   retired deliberately: an all-wontfix epic also wakes recomposition,
   and its Architect closes it `wontfix`, closes it `done`, or parks
   `needs-human` — a verdict, not a stall.
2. An Architect claims it and verifies the parent's own acceptance —
   integration seams, end-to-end behavior, the contract-lineage check
   below.
3. **Code-bearing integration parent** (two-plus children touched one
   executable surface; parent owns cross-child state/ordering/authz/
   migration/concurrency invariants; multi-repo composition; or the
   roadmap marks review required) ⇒ the Architect hands a pinned
   closure package to QAgent scale review (`in-review`): parent
   acceptance, child closing artifacts, exact base/head ranges,
   cross-child contracts, recomposition evidence. QAgent clean ⇒ the
   epic closes done; any defect ⇒ a corrective child ticket (there is
   no branch to fix-wave — the children are merged) and the parent
   waits again.
4. **Non-code parent** (docs, research, independent roll-ups) ⇒ the
   Architect closes it directly, recording why no aggregate code
   review applies.

QAgent review is shape-gated, not per-level — reviewing every ancestor
of every merge would re-review the same code once per tree level. And
it never substitutes for recomposition: purpose-verdicts are the
Architect's; correctness of the reconciled aggregate is QAgent's.

### Board mechanics of the recomposition lifecycle

Every path above is walked through the state machine it rides — an
escalation is only as real as its return path (E1 retrospective,
lesson 3). The lifecycle requires these named amendments, each part of
the interim slice's migration inventory:

- **Epic dispatch carve-out.** Eligibility currently excludes every
  epic. The ONE exception: an epic sitting in `ready-for-architect` is
  dispatchable — to the architect lane only — for recomposition and
  reconciliation claims. Every other epic state remains undispatchable.
- **The return is board bookkeeping.** The recomposition-due return
  fires from the epic's pulled in-flight state (`in-progress` or
  `in-design`) with the same latitude `pull_epics`/`close_epics` have
  today: exempt from `LEGAL`, and **excluded from convergence
  counting** — its audit comment carries a distinguishable
  `[board-epic]` marker so the convergence counter never reads a
  bookkeeping return as a worker escalation traversal. (Without this,
  the second recomposition cycle of any epic that needed a gap child
  would mechanically convert to `needs-human`.)
- **Where the parent waits.** After a reconciliation release, or after
  a gap/corrective child is registered, children are active again — the
  first active child's pull returns the epic to its in-flight state,
  exactly today's `pull_epics`. "The parent waits again" = the pulled
  in-flight state.
- **Scoped terminal authority.** The recomposition Architect may write
  the epic's terminal verdict (`done` or `wontfix`) — a deliberate,
  narrow exception to the worker-never-writes-terminal doctrine,
  legal only from a recomposition claim on an epic (new legal edges
  from `in-design`, epic-guarded). The QAgent's clean scale-review
  verdict closes the epic the same way. Leaf tickets are untouched:
  their terminal writes keep today's rules.
- **The in-review PR gate.** The board requires a PR to enter
  `in-review`. For a recomposition parent the pinned closure package
  is the artifact that satisfies that invariant (recorded in the same
  meta slot); the gate accepts it only for epics. QAgent scale review
  is a named protocol variant of reviewing-prs — same engine
  machinery, different entry artifact and verdict set (close /
  corrective child; no fix waves, no merge step).

### Upward revision: children change, parents must not go stale silently

Child specs WILL legitimately diverge from the contract they inherited.
The defect is silence, not staleness. Protocol:

1. **Pin at dispatch:** dispatch automation stamps the parent spec
   path, revision SHA, and inherited section id into the child's claim
   record (an extension of the claim-lifecycle write authority — not a
   worker duty, and not a cut-time snapshot, because the parent moves
   between cut and dispatch). "What contract did this child actually
   execute" is always answerable.
2. **Local vs parent-impacting:** a child revises its own MEANS freely.
   Discovery that touches a parent-owned END — purpose, acceptance,
   cross-child contract, dependency edge, sibling assumption, or the
   division itself — becomes a **parent-impact proposal**: a
   structured comment on the child's own ticket
   (`[parent-impact] <parent> <affected clauses>: <evidence>`),
   within the child worker's existing own-ticket write authority. The
   child never edits the parent's success criteria. Materiality is
   the proposing worker's judgment; the reconciling Architect reviews
   it (a proposal judged immaterial is answered on the child ticket,
   not folded into the parent).
3. **Reconciliation claim:** the sweep's reconcile pass reads
   unconsumed `[parent-impact]` markers and performs the parent's
   `ready-for-architect` return (board bookkeeping, same authority as
   the recomposition-due return — no new worker write on the parent),
   BEFORE final recomposition when siblings are building against the
   stale contract. The dispatched Architect reconciles the parent's
   living spec, flags affected in-flight children, then releases via
   the interim board's named release exit: a `needs-info` park
   ("reconciled — waiting on children"), which is legal from
   `in-design`, PULLABLE (the next active child pulls the epic back
   in-flight), frees the architect slot, and is never force-parked by
   the sweep's recovery pass. An Architect never ends its turn with
   the epic still in `in-design` — an escalation is only as real as
   its return path, and so is a release.
4. **Asymmetric authority:** the Architect may reconcile
   evidence-compelled technical consequences (clarify acceptance
   without changing intent, revise cross-child contracts, recut
   children, add gap children). Changing the parent's PURPOSE,
   materially reducing acceptance, or product/taste calls remain the
   human's — "we built something else, so we rewrote acceptance" is
   the failure this guards.
5. **Lineage check at recomposition:** the Architect reconciles every
   child against the final parent revision (child, dispatch SHA, later
   changes, reconciled?, evidence). No advance to QAgent until every
   material change is incorporated, explicitly irrelevant, or carried
   by a corrective child. The QAgent package pins the parent SHA; a
   parent change mid-review restarts the review.

The ledger carries this protocol as events: the proposal, the parent
revision that resolved it, and the children it flagged.

## The env-issue lane

- A new ticket category **`env-issue`**: environmental friction filed
  by ANY accountable worker through its existing registration authority
  (`--spawned-by <its ticket>`), after the standard
  search-before-register dedup. Filing is fire-and-continue — the
  worker's own ticket is never parked for it.
- **Birth rule (v2 — differs from the generic E1 default):**

  > Can the registrar name a concrete repair path that some authorized
  > agent of ours can execute in a repository or environment that
  > agent controls? Yes ⇒ `ready-for-implementer` (or
  > `ready-for-architect` when design-heavy). No / uncertain ⇒
  > **`needs-human`**.

  The inverted default is deliberate: environmental friction that an
  authorized agent could reach would typically already be solved —
  workers carry kube/gcloud/repo credentials. Dispatching an agent
  with no capability beyond the reporter's is wasted work. (Generic
  tickets keep E1's unsure ⇒ `ready-for-implementer`.)
- A `needs-human` env-issue body carries: the observed friction, what
  the worker attempted / routed around, why agent permissions cannot
  resolve it, the exact human intervention requested, and a check that
  proves resolution. If an ops agent later gains the capability, the
  ticket reclassifies to an agent lane with a note naming the repair
  path — category stable, resolver state changes.
- Blocking environmental failure remains what it is today: a park on
  the worker's own ticket. The PR `## Confusions` section remains the
  PR-time record; register an env-issue when the friction is
  actionable or likely to recur for other workers.
- **Consumers:** the ops-agent sweep (the cloud program's R3 lane) and
  the human wake queue — but the human DECISION queue includes an
  env-issue only when it actually sits in `needs-human`; agent-lane
  env issues belong to the ops/filter view, or fire-and-continue
  contradicts itself by taxing human attention.
- `env-issue` is a **category, not a lane state** — no dedicated
  dispatch route, no hardcoded worker species. On the interim board an
  agent-lane env issue takes the ordinary implement route; on the
  platform the ops agent may preferentially claim the category.

## Park durability (v2)

Every SDK decision park is mirrored into a durable board projection
(cc-harness T5) with a stable correlation id; the queue reads that
projection, so pod death never silently loses a question. A
board-originated park answers through the board/wake relay; an
SDK-originated park answers through the appserver's respond path; both
outcomes land back in the event log, and a re-raised decision after pod
death correlates to the original id idempotently. **One answer binds
per correlation id: first accepted wins**, enforced by the projection —
a second answer (e.g. board and appserver racing on the same question)
is rejected and recorded as a superseded-answer event, so the worker
never observes two answers and the log never shows an ambiguous
outcome.

## Naming

**"ticket" stays.** The doctrine term for the concept remains
purpose-unit; renaming the everyday word would churn every skill and
script for cosmetic gain. What the E3 UI displays on a node is a surface
decision deferred to E3.

## Implementation ownership (v2)

E2 fixes the contract; four separately-owned deliveries implement it:

1. **Interim doperpowers slice** (this repo, rides
   `feature/en-cycles`): `env-issue` category + birth rule + worker
   protocol amendments; epic auto-close replaced by the
   `ready-for-architect` recomposition return; recomposition/upward-
   revision doctrine into the decomposing skill. See § Interim slice.
2. **cc-harness runtime:** T5 durable decision mirroring +
   answer/re-raise correlation; T11 trusted hook activity emitter;
   pod-level sessionStore injection (the stock `ccx serve` entrypoint
   constructs no store — deployment precondition, not config wire).
3. **E3 board-service core:** the Postgres schema/API — atomic
   claim/bind/release/reclaim, legal transitions per E1 v1.3.3, the
   immutable event log, the activity projection, `TimelineReader`, the
   mirror outbox.
4. **E3 product:** timeline/queue/terminal rendering — consumes the
   contract, never defines it.

### R2 rebase requirements

`r2-board-schema.md` (2026-07-30) predates E1 v1.3.3 and is a DRAFT
input to E3 decomposition, not an implementation target. Named defects
the rebase must fix — not silently:

- missing `in-review → ready-for-architect` QAgent escalation edge;
- claims all three park states resume to pre-park (only `needs-human`
  carries the session-resume contract; `needs-info` is fold-and-recut);
- requires `plan_path` on every `in-design → ready-for-implementer`
  transition (the decompose exit legitimately carries none);
- convergence counting lacks E1's post-adjudication reset;
- lane-crossing release never clears `ticket.owner_run` (strands the
  handoff);
- hardcodes env-issue birth to `ready-for-implementer` (contradicts
  the v2 birth rule above);
- epic auto-close instead of the recomposition return path.

## Interim slice (doperpowers, implementable now)

- `_board.py`: `CATEGORIES` gains `env-issue`; `ensure_labels()`
  creates the label (a consumer repo won't have it — registration
  would fail).
- `close_epics` retired in favor of the recomposition return: all
  children terminal ⇒ parent to `ready-for-architect` with the
  `recomposition-due` note; an Architect closes it through the normal
  lane (code-bearing parents route `in-review` first). Carried by the
  mechanics amendments above: the epic `ready-for-architect` dispatch
  carve-out in eligibility; the bookkeeping return with the
  `[board-epic]` convergence-exempt marker; the epic-guarded terminal
  edges from `in-design`; the closure-package satisfaction of the
  in-review PR gate; the sweep's `[parent-impact]` reconcile pass.
- Worker protocols (Architect, Implementer, spike, QAgent): the
  optional fire-and-continue env-issue authority — search first, full
  body, `--spawned-by`, v2 birth rule, source ticket untouched;
  subagents still never write. The Architect protocol gains the
  recomposition claim (verification, lineage check, scoped terminal
  verdict); the QAgent protocol gains the scale-review variant.
- Decomposing skill: the recomposition lifecycle and upward-revision
  protocol (dispatch-time pinning, parent-impact proposals,
  reconciliation claims, lineage check). On the interim board the
  dispatch-time pin is written by the dispatch machinery into the
  child's board meta (`parent-pin:`), mirroring the platform's
  claim-record stamp.
- The feedback-triage registrar (`bug | enhancement` only, no
  provenance) is explicitly OUTSIDE "any worker" for env-issue filing;
  an origin-less automation registration path is platform work.
- Honest posture: no ops lane exists here; no derived stream exists
  here; nothing may imply otherwise.

## Acceptance (observable)

Each criterion names its verifying owner. **E2 closes when the
E2-close items pass**; deferred items are verified by their owners
when those deliveries land — they bind the contract but not E2's
closure.

*E2-close (interim slice, this repo):*

1. A worker files an `env-issue` ticket mid-build and its own ticket
   proceeds uninterrupted — no park, no state change on its ticket.
2. On the interim GitHub board, a v8 worker transcript and a post-E2
   worker transcript are indistinguishable modulo the E1 lane-split
   vocabulary and the additions named in § Interim slice (env-issue
   filing is opt-in authority, not a duty; zero new write duties).
3. An env-issue whose registrar cannot name an agent-executable repair
   path is born `needs-human` and appears in the human decision queue;
   one with a named repair path is born into an agent lane and does
   NOT appear there.
4. A parent whose last child lands is observed in
   `ready-for-architect` (not done); it reaches done only through an
   Architect's recomposition — via `in-review` when code-bearing —
   and a second recomposition cycle (gap child) does NOT trip the
   convergence counter.
5. A child's `[parent-impact]` proposal produces the parent's
   reconciliation return and the flagging of affected in-flight
   children; the recomposition lineage check names every child's
   pinned parent revision.

*Deferred verification — owner E3 (board core + product):*

6. A ticket's rendered timeline interleaves decision events with
   derived session activity.
7. Any past board state is reconstructible from the event log alone
   (append-only) — including the claim/release history of every run
   and every mutable-field change — and reading current state never
   requires folding the log.

*Deferred verification — owner cc-harness:*

8. Killing a pod mid-park loses no question: the park is present in
   the durable projection, its eventual answer correlates to the
   original decision id, and a racing second answer is rejected as
   superseded.

## Deferred

- Timeline/queue rendering, activity summarization, and node display
  naming — E3 (control-plane product).
- Mirror field-mapping (which columns flow to the GitHub/Linear
  mirrors) — board-platform work in the cloud program's round.
- Retention/compaction policy for the derived stream.
- The ops-agent worker protocol (R3) and any category-preferential
  dispatch.
- Origin-less automation registration (feedback-triage provenance).

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
  subagents excluded; derived stream worker-read-only.
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
- Decision (v2): E2 closes at the domain-contract boundary; four
  implementation owners (interim slice, cc-harness, E3 core, E3
  product).
  Rationale: E2's acceptance crosses four independently-owned systems;
  one build-epic would have no single reliable owner (the decomposing
  gate). Rejected: E2 blocked until E3 renders the ledger (couples the
  doctrine to a product timeline it doesn't need).
  Date/Author: 2026-08-01, human + session.
- Decision (v2): Source hierarchy board events > sessionStore > trusted
  hooks > OTel; OTel demoted to operations plane.
  Rationale: OTLP permits loss/duplication/reordering by design (spec
  §retry/ack); sessionStore is turn-grain archival (mirror drops,
  destructive rewind); hooks are the only trusted intra-turn carrier
  (R1 verdict). "Read-only" sharpened to worker/client-read-only.
  Rejected: v1's "sessionStore + OTel" as co-primary carriers (promises
  a completeness and ordering neither source has).
  Date/Author: 2026-08-01, human + session, per OTLP spec + R1 +
  adapter inspection.
- Decision (v2): Dispatch writes claim-lifecycle records, never
  workflow state.
  Rationale: without an automation-authored fenced claim/bind/release
  event there is no ticket↔session attribution, no reconstructible
  history, and no terminal authorization; E1's real invariant was that
  the worker's first WORKFLOW decision is its own.
  Rejected: v1's literal "dispatch writes nothing" (unimplementable
  with the required binding).
  Date/Author: 2026-08-01, human + session.
- Decision (v2): Binding = ticket → runs → (store namespace,
  project_key, session_id); wording stays "ticket ↔ accountable
  claim"; relay phases are runs under one accountable execution.
  Rationale: one ticket legitimately spans Architect/Implementer/QAgent
  sessions plus restarts and reclaims; a mutable singular session id
  destroys history and terminal authz. The composite key is what the
  shipped adapter actually uses.
  Rejected: bare ticket↔session_id binding (topological symmetry
  without lifecycle truth).
  Date/Author: 2026-08-01, human + session.
- Decision (v2): Non-leaf nodes are Architect-bracketed (decompose,
  then recompose); epic auto-close replaced by the
  `ready-for-architect` recomposition return; QAgent scale review
  shape-gated to code-bearing integration parents.
  Rationale: the decomposing doctrine already requires closing a
  parent by verification, not bookkeeping — the board's close_epics
  contradicted it; per-level mandatory review would re-review the same
  code once per ancestor.
  Rejected: mechanical auto-close (status quo); Implementer/QAgent
  phases on epics (no implementation of their own); unconditional
  per-parent review (exponential cost, no marginal signal).
  Date/Author: 2026-08-01, human + session.
- Decision (v2): Upward revision — children propose, a re-dispatched
  Architect reconciles, the human approves material purpose/acceptance
  changes; dispatch-time SHA pinning + recomposition lineage check.
  Rationale: child discovery legitimately changes parent contracts;
  the defect is silent staleness. Asymmetric authority prevents
  acceptance being rewritten to match what got built.
  Rejected: frozen parent contracts (fiction); children editing the
  parent directly (no accountable reconciler); deferring all
  reconciliation to final recomposition (siblings build against stale
  contracts meanwhile).
  Date/Author: 2026-08-01, human + session.
- Decision (v2): env-issue birth defaults to `needs-human`; agent lane
  only when the registrar names a concrete authorized repair path.
  Rationale: environmental friction reachable by agent authority would
  typically already be solved (workers carry kube/gcloud/repo creds);
  dispatching an agent with no capability beyond the reporter's is
  waste. Inverts the generic E1 unsure-default deliberately, for this
  category only.
  Rejected: v1.1's generic birth rule for env-issue (routes
  human-only interventions to agents); unconditional `needs-human`
  (some friction IS agent-repairable — broken fixtures, image pins).
  Date/Author: 2026-08-01, human.
- Decision (v2.1): The recomposition Architect holds scoped terminal
  authority — it may write an epic's `done`/`wontfix` from a
  recomposition claim (epic-guarded edges from `in-design`); the
  QAgent's clean scale-review verdict closes the same way.
  Rationale: recomposition IS the verification event the decomposing
  doctrine requires before closure; routing every verified epic
  through a `needs-human` close would tax the human queue with
  verdicts already evidenced. The exception is narrow: epics only,
  recomposition claims only — leaf terminal writes keep the
  worker-never-closes doctrine.
  Rejected: needs-human handoff for every epic close (queue tax on
  evidenced verdicts); unrestricted worker terminal authority
  (overturns the standing doctrine for no need).
  Date/Author: 2026-08-01, session, from the fable review's finding.
- Decision (v2): Park durability via T5 projection with correlation
  ids; two answer paths (board relay / appserver respond), one durable
  queue.
  Rationale: appserver parks are process memory; pod death otherwise
  loses questions silently — the reference architecture already
  requires T5 correlation.
  Date/Author: 2026-08-01, session, per R1/appserver inspection.
- Decision (v2): Timeline access through a logical `TimelineReader`
  interface, not raw SQL joins.
  Rationale: same-Postgres is the initial deployment, not an
  invariant; sessionStore promotion is an allowed future (archive
  tier, separate DB) that must not break E3's query contract.
  Rejected: hard same-database coupling as a spec premise.
  Date/Author: 2026-08-01, session.

## Surprises & Discoveries

- Observation: The ideadump's core demand — "report at the ledger
  instead of the final message" — was ALREADY v8 doctrine at scope ends
  (turn-ends are audit trail; the board is the communication surface).
  The real gap was between scope ends, and the Postgres convergence
  turned filling it from a doctrine reversal into a join.
  Evidence: implementing-tickets "no live progress mirror" paragraph;
  Postgres sessionStore adapter shipped 2026-07-30 (cc-harness).
- Observation (2026-08-01): the shipped sessionStore adapter supports
  the derived stream only conditionally — no ticket knowledge, no
  parent/child relations in schema, no turn entity, no status, TEXT
  payloads (deliberately not jsonb: U+0000/lone-surrogate round-trip),
  `mtime` as the only liveness hint, and hard-delete/rewind semantics.
  "Zero new worker writes" survives, but only because the LAUNCHER
  records the binding — zero new system integration it is not.
  Evidence: postgresSessionStore.ts inspection; appserver
  registry/turns are process memory; p2 probe (subagents are subpath
  files, not sessions).
- Observation (2026-08-01): the board's own code contradicted the
  decomposing doctrine — close_epics closed parents by bookkeeping
  while the skill required verification-by-recomposition. Nobody
  noticed until the ledger design forced the parent lifecycle into
  events. A contract made structural surfaces the doctrine violations
  its prose form tolerated.
  Evidence: _board.py close_epics vs decomposing SKILL.md
  Recomposition section.
- Observation (2026-08-01): E2's v1 acceptance was not ownable as one
  epic — it crossed four systems (plugin, cc-harness, board core,
  product UI). The cross-spec review, the store inspection, and the
  repo surface map independently converged on the same contract-vs-
  implementation split.
  Evidence: the three 2026-08-01 investigation reports.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-08-01: v2.1.1, plan-review pass (writing-plans is the first
  hostile read): the reconciliation release exit is now NAMED — the
  interim board's `needs-info` park from `in-design` (legal, PULLABLE,
  recovery-safe) — closing the "release" verb the spec used without a
  state; the sweep's reconcile marker is written only when the return
  actually fires (a proposal arriving mid-claim stays unmarked for the
  next tick), and the lineage check reads all proposals regardless of
  markers; dispatch eligibility extends to `reconciliation-due:` epics
  (children still active) so the reconciling Architect is dispatchable,
  as step 3 requires.
- 2026-08-01: v2.1, independent fable spec review (14 findings, all
  adopted). The critical cluster: the recomposition lifecycle had been
  designed as doctrine without walking it through the board machinery
  it rides — epics were undispatchable (no consumer for
  recomposition-due), no legal path let an Architect write done, the
  return tripped the convergence counter on second cycles, and the
  in-review PR gate rejected epics. New § Board mechanics names each
  amendment. Also: writers/actors fixed for parent-impact proposals
  (child comment + sweep reconcile pass) and dispatch-time pinning
  (claim-record stamp); run-state-at-parks map (needs-human pauses,
  needs-info closes); field-change events restore the event-log
  reconstruction claim; first-accepted-answer arbitration; acceptance items
  tagged with verifying owners (E2-close vs deferred); trigger
  predicate pinned (all children, one-done guard deliberately
  retired); wording fixes (standing claim, birth-rule antecedent,
  MUST, mechanism footnoted to cc-harness).
- 2026-08-01: v2, pre-implementation maturity round (grill + three
  independent investigations: repo surface map, cross-spec consistency,
  sessionStore semantics). Contract boundary fixed (four
  implementation owners); source hierarchy replaces "sessionStore +
  OTel" (OTel demoted to ops plane); "dispatch writes nothing"
  narrowed to workflow state (claim-lifecycle records are dispatch's);
  ticket→run→session binding model with composite store key; non-leaf
  lifecycle (Architect-bracketed recomposition, auto-close retired,
  shape-gated QAgent scale review); upward-revision protocol; env-issue
  birth inverted to needs-human default; park durability (T5
  projection); TimelineReader interface; R2 rebase defects named.
- 2026-07-31: v1.1, consistency fixes from the E1 maturity round's
  cross-spec review (no decision re-opened): the Writers clause restated
  with the full v8 registration authority (child/follow-up/env-issue
  tickets) and dispatch removed from the writer set; env-issue birth
  classification pinned to E1's birth rule + interim `CATEGORIES` note;
  acceptance 4's "indistinguishable" claim carved out for the E1 lane
  vocabulary that lands on the interim board independently.
- 2026-07-30: v1, authored from the E2 grill of the ideadump roadmapping
  session (ledger essence → write semantics → env channel → naming).
