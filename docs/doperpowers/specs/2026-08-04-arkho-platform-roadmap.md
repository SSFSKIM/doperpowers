# Arkho Platform Roadmap (2026-08-04)

> **Parent:** `docs/doperpowers/specs/2026-07-30-control-plane-product-design.md`
> (epic E3 of the ideadump triage roadmap,
> `2026-07-30-ideadump-triage-roadmap.md` § Epic outcomes). **Level
> name:** Epic E3. **Consumes:**
> `research/2026-07-30-clean-slate/r2-board-schema.md` v2 (the
> board-service internals — schema, transaction shapes, roles),
> `r2-platform.md` §6 (service shape), the E1/E2 contract canon
> (`2026-07-30-implement-lane-split-design.md` v1.3.3,
> `2026-07-30-ticket-ledger-observability-design.md` v2.x),
> `plans/2026-07-23-a0-core-board-service.md` (prior art — a complete,
> never-executed implementation plan; its transaction drills carry
> over, its schema is superseded), and
> `skills/issue-tracker/scripts/board-map.template.html` (proven
> topology interactions). Children dispatch per their track hint; each
> child spec opens by citing this document (path + child id). This
> document is born in doperpowers and **moves into the Arkho repo at
> materialization** (Decision 2); after the move, the Arkho path is the
> canonical citation target.

## Purpose

A human cannot oversee a swarm by attaching to sessions one at a time,
and the human's decision throughput on parked work is the swarm's
tightest bottleneck. Arkho (`SSFSKIM/arkho`, private) is the standalone
control-plane product that fixes this: the Postgres SSOT board (the
AI-native platform the 2026-07-30 pivot fixed), a browser surface for
the ticket topology, each ticket's merged decision+activity timeline,
and ONE unified needs-human queue whose answers wake the parked workers
that filed them. GitHub Issues (and later Linear) become one-way
mirrors. The ledger and the queue are THE human↔agent communication
surfaces — the human does not steer live sessions; the session terminal
is an inspection/break-glass surface, deliberately late (parent spec
Decision Log, 2026-08-04). doperpowers stays a skills plugin whose
workers speak the board API; cc-harness stays the session runtime.

## Parent-Level Acceptance

E3 closes at **phase web** (the parent spec's phasing; phase native is
the named continuation, child A7, not part of this closure):

1. From the topology view, clicking a ticket shows its merged timeline
   and bound session. *(The parent spec's live-terminal clause on this
   criterion verifies at A6 — deliberately the last required child.)*
2. The queue shows board parks as preselected answer forms; answering
   one visibly resumes the bound worker (ticket returns to its
   parking lane's in-flight state, session activity resumes). *(The
   SDK-decision species appears in the same queue when
   `external:cc-harness-T5` lands — conditional, not required for
   closure; the queue's board species is required.)*
3. A board state change appears on the GitHub Issues mirror without any
   worker having written to GitHub; editing the mirror changes nothing
   on the board (repair, never ingest).
4. doperpowers workers drive their full protocol (register → claim →
   gate → transitions → parks/answers → epic lifecycle → terminal)
   against the board API with no dependency on the Arkho repo beyond
   that API.
5. At least one live board has been cut over end-to-end — Arkho's own
   development board: its pre-flip GitHub state imported, its GitHub
   issues demoted to mirror, its workers running via the plugin
   adapter. *(The doperpowers board's own flip is a human-triggered
   conditional gate in A5 — the playbook must be proven, the trigger is
   operational timing, not E3 closure.)*

## Grounding Baseline

Measured 2026-08-04: no Arkho repo, no provisioned Postgres. A0 Plan 1
exists as a complete 9-task implementation plan (Node 22 + `pg`,
~6 endpoints, real-Postgres acceptance drills, Render deploy artifacts)
— never executed. Board-service internals fully drafted
(r2-board-schema v2, rebased against E1 v1.3.3 + E2 v2.x this session).
`board-map.template.html` (37 KB) carries the proven pan/zoom DAG,
kanban toggle, state filters, epic collapse. The plugin's board
toolkit (`_board.py` + 9 scripts) is gh-CLI-coupled but its state
machine is substrate-neutral by design (E1/E2, shipped v7.36.0).
Appserver: M1 surface live-probed (decisions-as-state cross-connection,
bearer auth); M2 control family absent (`-32601`); `thread/attach`
adoption is M3. The v8 GitHub label vocabulary — the mirror's target
vocabulary — is already shipped and live.

## Children

### A1: Board service core — controlled

- **Purpose:** The platform's spine: the Postgres SSOT implementing
  r2-board-schema v2 — the E1 v1.3.3 state machine and E2 ledger
  contract as an authenticated API plus lifecycle automation. Every
  other child consumes what this child stands up.
- **Acceptance:**
  - **G1 (schema + transactions):** the v2 DDL and transaction shapes
    pass the acceptance drills — two racing claims yield one winner; a
    zombie fence is refused; a lane-crossing transition closes the run,
    clears `owner_run`, and appends the release event in ONE
    transaction; any past board state reconstructs from the event log
    alone.
  - **G2 (worker-protocol-complete API):** every state-machine
    operation a worker protocol names is expressible through the API —
    claim, transition (with edge-keyed note/PR checks, convergence rule
    + reset, epic guards), park/answer (lane-mapped returns,
    first-accepted-wins), register (dedup + API-side birth
    classification, env-issue rule), comment, timeline, decision-park
    read. A run's bearer token cannot write another ticket's state;
    human-authored writes (answers, adjudications) authenticate through
    X2's human-principal path — `actor_kind='human'` is
    credential-derived, never caller-asserted.
  - **G3 (lifecycle automation):** reconciler/dispatcher process:
    recomposition-due and reconcile returns, epic pull, and a reclaim
    that is **liveness-source-aware (X6)**: a live worker whose binding
    names no sessionStore feed (a local plugin session) is never
    reclaimed while its lease is renewed or its run keeps writing; a
    dead run is reclaimed with a successor run carrying
    `predecessor_run`.
  - **G4 (deployed + readable):** a deployed instance is reachable;
    `TimelineReader` serves merged reads (the sessionStore/activity
    union renders when such data exists — its absence is a legal,
    honest state).
  - Forward seams owned here: the board-side ingest halves of the two
    external projections — T5 decision-park mirroring and T11 activity
    (schema + roles land with G1; each ingest wire is co-designed when
    its external lands).
- **Edges:** blocked-by: — (dispatchable at materialization);
  blocks: A2, A3, A4, A6.
- **Contracts:** X1 (owner), X2 (owner), X3 (owner), X4 (outbox schema
  owner), X6 (owner — API semantics).
- **Required:** yes (all gates).
- **Status:** not-dispatched (dispatchable now, post-materialization).

### A2: Plugin board adapter — controlled

- **Purpose:** The substrate swap the E-cycle state machine was written
  to be neutral over: the doperpowers issue-tracker toolkit and worker
  dispatch scripts speak the Arkho board API instead of the gh CLI.
  Lives in the doperpowers repo; its ticket materializes on the
  doperpowers board (Decision 1). This child is what makes parent
  acceptance 4 real.
- **Acceptance:** a worker runs the full protocol — register → claim →
  gate verdict → transitions → park/answer relay → epic
  recomposition → terminal — against a live A1 instance, with worker
  transcripts indistinguishable from GH-board runs modulo transport.
  An answered `needs-human` park physically resumes the bound worker —
  A2's ported sweep/relay owns wake delivery end-to-end for plugin
  workers (level-triggered poll, idempotent resume, ack marker), and
  its dispatch automation renews the run lease for sessions with no
  sessionStore feed (X6). The wake path survives a relay crash at
  every boundary: answered-but-unrelayed states are re-polled, never
  lost, never double-resumed — the crash-at-boundary drill is part of
  this acceptance. Board binding is per-repo configuration: gh
  mode remains fully supported (X5 — consumer repos like ida-solution
  never require a Postgres service).
- **Edges:** blocked-by: A1.G2 (start); completion additionally
  exercises A1.G3 (the epic-recomposition drill needs the reconciler);
  blocks: A5 and A3.G3's completion.
- **Contracts:** X1 (consumer), X5 (owner), X6 (local-worker mechanics
  owner).
- **Required:** yes.
- **Status:** not-dispatched (blocked-by A1).

### A3: Web UI — controlled

- **Purpose:** Surfaces 1–3 of the parent spec: the topology view
  (porting BOARD.html's proven interactions onto the board API), the
  ticket detail view (the E2 merged timeline plus `plan:` artifact
  links and bound-session status), and the unified needs-human queue
  (batch parks rendered as preselected forms; the env-issue lane as a
  filter). Behind team auth (the Cloudflare Access pattern is the
  precedent; mechanism is this child's call).
- **Acceptance:**
  - **G1 (topology):** pan/zoom DAG + kanban toggle + state filter +
    epic collapse operate against the live API.
  - **G2 (ticket detail):** decision events interleave with the derived
    activity/session stream when it exists; plan pins and bound-session
    status render.
  - **G3 (queue):** board parks render as preselected forms; submitting
    an answer visibly resumes the bound worker. **Conditional gate
    G3-sdk:** the SDK-decision species joins the same queue —
    evaluable when `external:cc-harness-T5` lands; until then the
    queue serves the board species only.
- **Edges:** blocked-by: A1.G2 (G2/G3 additionally exercise A1.G4);
  G3's completion blocked-by A2 (a visible resume needs a real bound
  worker); conditional-on (G3-sdk only): external:cc-harness-T5;
  blocks: A6.
- **Contracts:** X1 (consumer), X3 (consumer), X2 (front-door owner —
  the mechanism that produces the human credential, per its contract),
  X6 (submitter).
- **Required:** G1–G3 yes; G3-sdk conditional.
- **Status:** not-dispatched (blocked-by A1).

### A4: Mirror writers — autonomous

- **Purpose:** The one-way outbound GitHub mirror (the schema's outbox
  consumer): per-ticket coalescing, board-state → v8 label vocabulary
  mapping, `mirror_ref` drift repair. Doubles as A5's migration
  instrument — the thing that keeps a demoted GH board honest.
- **Acceptance:** a board write appears on the mirrored GitHub issue
  without any worker GitHub write; a mirror-side edit is repaired on
  the reconcile pass, never ingested; a dead mirror stalls only its own
  outbox (backoff; the SSOT never waits); delivery stays within the
  coalescing rate posture (~2–3 human-relevant writes per run).
- **Edges:** blocked-by: A1.G1 + A1.G2; blocks: A5. Linear: deferred
  (not an edge — a reservation, see Deferred).
- **Contracts:** X4 (delivery-semantics owner).
- **Required:** yes.
- **Status:** not-dispatched (blocked-by A1).

### A5: Cutover — controlled

- **Purpose:** The flip that makes the SSOT claim true for a live
  board: import/backfill a GH board's issues into tickets + events,
  freeze registrations for the window, flip the repo's plugin binding
  (A2's per-repo config), demote its GH issues to mirror (A4). The
  playbook is itself a deliverable — every subsequent board flip
  (doperpowers', consumer repos') replays it.
- **Acceptance:**
  - **G1 (Arkho's own board — required):** the flip is a BARRIER, not
    a snapshot: ALL board writes freeze (not just registrations) and
    every active claim is drained to a scope end or explicitly
    migrated before the import; the import replays to a high-water
    mark and passes a parity check against the frozen GH state
    (tickets, states, edges, open parks); a defined rollback exists
    until the binding flips; the flip is atomic per repo (A2's
    binding), runs under an out-of-band control principal — never a
    worker claim on the board being flipped — and is human-triggered.
    Post-flip a worker runs the full protocol via A2 against the Arkho
    SSOT; the GH mirror tracks; a mirror edit is repaired. A straggler
    write after the snapshot is impossible by the freeze — never
    merely "repaired" away, which would silently destroy legitimate
    workflow state.
  - **G2 (doperpowers board — conditional):** the same playbook run on
    the doperpowers board; becomes evaluable when the human triggers
    it. Not required for E3 closure (Parent-Level Acceptance 5).
- **Edges:** blocked-by: A2, A4.
- **Contracts:** X1, X4, X5 (consumer), X6 (its G1 drills run on the
  signal plane).
- **Required:** G1 yes; G2 conditional (human-triggered).
- **Status:** not-dispatched (blocked-by A2, A4).

### A6: Terminal gateway — controlled, deliberately late

- **Purpose:** The inspection/break-glass session surface: a web
  terminal client speaking through Arkho's authenticated proxy to a
  pod's appserver WS (`thread/subscribe` + `thread/read` + `turn/start`
  + `decision/*`). Auth and audit centralize at the gateway; humans
  get no `pods/exec` grant. Deliberately last among required children
  per the steering decision — the queue and ledger, not the terminal,
  are the communication surfaces. Until this lands, break-glass is
  operator `kubectl exec` + `ccx attach`.
- **Acceptance:** from the ticket view, one action opens a live
  terminal to the bound session in the browser; the gateway authorizes
  per identity against the run table (only the current run's
  thread/pod is reachable; X2 tokens verified at the gateway); the
  worker protocol never requires the terminal.
- **Edges:** blocked-by: A1 and A3 (the terminal-launch action lives
  in A3's ticket view — an A3↔A6 integration seam delivered at A6
  time); external:cc-harness-M2 (control-surface wire methods) and
  external:swarm-runtime (appserver-born worker sessions to attach
  to — sessions must run under `ccx serve`; `thread/attach` adoption
  is M3 and NOT assumed). deliberately-late.
- **Contracts:** X1 (run-table authz read), X2 (consumer), X6 (reads
  run liveness).
- **Required:** yes (it completes Parent-Level Acceptance 1's terminal
  clause) — but last, and its external edges are start-time gates.
- **Status:** not-dispatched (waiting-external + deliberately late).

### A7: macOS app phase — decomposing (run at dispatch)

- **Purpose:** Phase native: a macOS app hosting real ghostty against
  the same backends. Kept coarse on purpose — the frontier rule; its
  precise gates emerge from its own cut.
- **Acceptance:** coarse — emerges from its own decomposing run.
- **Edges:** blocked-by: A3, A6; conditional-on: the human's
  phase-native go after phase-web recomposition.
- **Contracts:** X1, X2 (consumer, by construction).
- **Required:** no — E3 closes at phase web; A7 is the named
  continuation this map tracks.
- **Status:** conditional.

## Cross-Child Contracts

- **X1 — The board API contract.** Owner: A1 (content delivered by
  A1.G2, versioned in the Arkho repo). Binds A2, A3, A5, A6, A7 —
  NOT A4, which consumes the outbox directly through its DB role
  (X4), never the API.
  Authority clauses fixed here: the API is worker-protocol-complete
  against E1 v1.3.3 + E2 v2.x (every legal state-machine operation
  expressible — the upstream canon, not re-litigable by any child);
  writes are token-scoped per run (workers never speak SQL; subagents
  cannot write); the event log is append-only by privilege. Written to
  outlive this unit — promotion to root canon is a closing-time
  action.
- **X2 — One identity issuer, three principal classes.** Owner: A1
  (the credential contract: per-run bearers, human principals, and
  gateway verification — how the API derives `actor_kind` from each
  class). Binds A2 (workers hold per-run bearers), A3 (owns the
  front-door MECHANISM that produces the human credential — the
  Cloudflare Access precedent — but never its contract), and A6
  (verifies the same issuer for terminal authz). Human-authored
  events are semantically load-bearing (convergence reset, answer
  authority, epic adjudication), so the human-principal path is part
  of A1.G2, not deferred to A3. Token mechanism (hash-stored bearer
  vs short-lived JWT) is A1's delivery, decided at A1's plan time.
- **X3 — TimelineReader.** Owner: A1; consumer: A3. A logical
  interface, never raw cross-schema SQL: per-source order only;
  source-local cursor + observed-at + optional source time on every
  derived record; a later sessionStore promotion (separate DB/archive
  tier) must preserve the interface. Absence of derived data is a
  legal state consumers must render honestly.
- **X4 — Mirror semantics.** Outbox schema owner: A1; delivery
  semantics owner: A4 (coalescing, v8 label vocabulary mapping,
  repair-never-ingest). Consumer: A5 (the backfill is the mapping's
  inverse). Invariant fixed here (Class A, standing): a mirror edit
  NEVER mutates the SSOT — no webhook intake exists.
- **X5 — Substrate-neutral worker protocol.** Owner: A2. Binds A5 and
  every future consumer-repo flip. The plugin's state-machine
  semantics are identical across the gh and API bindings; binding is
  per-repo configuration; gh mode remains a supported first-class
  substrate (the marketplace/zero-dependency identity — consumer
  repos never require a Postgres service).
- **X6 — The session signal plane: liveness + answer-wake.** Owner:
  A1 for API semantics, A2 for local-worker mechanics. The r2 draft
  derives run liveness solely from the cc-harness sessionStore
  (`ccs_sessions.mtime`) — a feed pre-cluster plugin workers do not
  produce, so as drafted every A2-bound worker would be reclaimed at
  lease expiry mid-work. A1 makes the liveness source pluggable: the
  sessionStore join when the binding names a store; an
  automation-renewed lease otherwise; any authenticated write from
  the run counts as life (all reconcilable with E2's zero-new-duties
  — renewal is dispatch automation, never worker prose). The same
  plane carries the wake, and delivery is **level-triggered off
  durable state, never edge-triggered**: the answer event IS the
  queue entry (NOTIFY is a latency hint only). **A2 owns wake
  delivery end-to-end for plugin workers** — it polls unrelayed
  answers, resumes the bound session idempotently, and acknowledges
  by appending a relay marker keyed to the answer event id; A1 owns
  the durable answer/ack state and enforces one ack per answer. A
  crash at any boundary leaves a re-pollable state — never a ticket
  returned in-flight while its session stays parked, never a doubled
  resume. A3 merely submits. Binds A5 (its G1 drills run entirely on
  this plane) and A6 (terminal authz reads the same run liveness).
  Recorded in the r2 draft as open item 8.

## Ordering & Dependency Map

```
A1 ──┬──► A2 (doperpowers repo; completion exercises A1.G3) ──┬──► A5
     ├──► A3 (web UI; G3 completes against A2's bound worker) ┤ (flip: Arkho
     ├──► A4 (GH mirror) ─────────────────────────────────────┘  board req'd;
     │                                                           dp board
     └──► A6 (terminal gateway) ◄── also blocked-by A3;          human-trig.)
              external: cc-harness M2, swarm runtime (deliberately late)
A3 + A6 ──► A7 (phase native — conditional, own decomposing run)
```

A2/A3/A4 START in parallel once A1.G2 lands (gate-level edges); the
arrows above are start-time — completion gates still reach deeper (A2's
acceptance exercises A1.G3; A3.G3 completes against A2's bound worker).
**A1–A5 are cluster-independent**:
they need one Postgres and a deploy target, not the k8s/gVisor swarm
runtime — every phase-web surface except the terminal, and the cutover
itself, proceed without the R-round spikes. **E3's CLOSURE still
queues behind them**: A6 is required, and its externals (cc-harness M2;
swarm-runtime worker pods) are hard completion dependencies with
outside owners — carried as external rows in the Tracking Map, not
hidden behind "deliberately late".

## Risks & Mitigations

- **A1 is the fan-out bottleneck.** Mitigation: gate-level edges — A2,
  A3, A4 START on A1.G2, before G3/G4 finish (their completion gates
  still reach G3/G4 — see Ordering).
- **External timing (T5, M2, swarm runtime).** Mitigation: conditional
  gates keep parent acceptance evaluable without them (G3-sdk
  conditional; A6's externals are start-time gates on the last
  required child).
- **Dual-substrate maintenance in the plugin (X5).** Mitigation: one
  state-machine source with a transport adapter boundary; A2's
  acceptance forbids semantic drift between bindings.
- **Cutover fidelity (A5).** Mitigation: import drill on a copy first,
  registration freeze window, human-triggered flip, mirror as the
  fallback rendering throughout.
- **Postgres hosting stalls A1.** Mitigation: the schema is
  host-agnostic by construction (mainline features only); vendor
  choice is A1's at dispatch with R4's re-priced numbers as input.

## Deferred / Out of Scope

**Deferred (may return):** the Linear mirror (no live Linear consumer;
X4's delivery semantics extend to it when one exists); derived-stream /
activity retention policy (E2 deferral stands); multi-human auth model
(single-operator assumption holds for now); ops-agent
category-preferential dispatch (the cloud program's R3 lane);
origin-less automation registration (feedback-triage provenance);
the doperpowers board's own flip timing (A5.G2, human-triggered);
phase-native details (A7's own cut).

**Explicitly out of scope (standing exclusions):** webhook intake on
any mirror (X4 invariant — edits never flow inward); real-time session
steering as a design driver (the 2026-08-04 steering decision — the
parent spec's Decision Log holds it); renaming "ticket" (E2 decision;
UI display naming is A3's surface concern at most).

## Tracking Map

| child | spec / ticket | status |
|---|---|---|
| A1 board service core | — (ticket at materialization, Arkho board) | not-dispatched |
| A2 plugin board adapter | — (ticket at materialization, doperpowers board) | not-dispatched |
| A3 web UI | — (Arkho board) | not-dispatched |
| A4 mirror writers | — (Arkho board) | not-dispatched |
| A5 cutover | — (Arkho board) | not-dispatched |
| A6 terminal gateway | — (Arkho board) | not-dispatched |
| A7 macOS app | — (registered at phase-native go) | conditional |
| external: cc-harness M2 control surface | owner: cc-harness program (R1 T9) | not-started — blocks A6 completion |
| external: swarm-runtime worker pods (`ccx serve`-born sessions) | owner: cloud program (R-round spikes, human-gated) | not-started — blocks A6 completion |

## Decision Log

- Decision: A child materializes onto the board of the repo its diff
  touches — Arkho's own board for A1/A3–A7, the doperpowers board for
  A2.
  Rationale: branch/ticket topology binds tickets to the repo the work
  changes (worktree-per-ticket machinery assumes it); Arkho born
  self-tracking on the board pattern it replaces makes A5's dogfood
  cut-over the cleanest possible; the roadmap's tracking map is the
  unifying record. Rejected: everything on the doperpowers board
  (every Arkho branch/PR crosses repos).
  Date/Author: 2026-08-04, human (grill Q1).
- Decision: This roadmap is born in doperpowers for the approval gate
  and MOVES into Arkho at materialization (tombstone pointer left
  behind); children cite the Arkho path.
  Rationale: the platform's founding parent document belongs in the
  platform (self-contained, SaaS-exit framing); the move happens
  inside the already-gated materialization step, before any ticket is
  registered, so no citation breaks. Rejected: permanent doperpowers
  residence (the platform's parent doc in a foreign repo forever).
  Date/Author: 2026-08-04, human (grill Q2).
- Decision: A1 is ONE leaf on the controlled track — no sub-decomposing
  run.
  Rationale: one state owner, one invariant family, one verification
  strategy; no seam yields independently-landable children (API without
  reconciler leaks claims; schema without API ships nothing); A0
  Plan 1 held the smaller version in one plan; writing-plans'
  conditional sub-slicing handles sequencing below the tree's
  resolution. Rejected: its own decomposing run (a cut on size, not on
  seams — the gate asks reliably-ownable, not small).
  Date/Author: 2026-08-04, human (grill Q3).
- Decision: `SSFSKIM/arkho`, private.
  Rationale: personal account (no org in the picture); private because
  it is the control plane for private infrastructure; the GH-Pages
  limitation of private repos is moot — A3 IS the hosted UI, Cloudflare
  Access precedent. Rejected: public; an org.
  Date/Author: 2026-08-04, human (grill Q4).
- Decision: A2 (plugin adapter) and A5 (cutover) added beyond the five
  human-named cut lines; the unified queue folded into A3.
  Rationale: without A2, parent acceptance 4 has no owner; without A5,
  the migration is a hope, not a child with acceptance; the queue
  shares A3's state owner, auth, and rendering surface — a standalone
  queue child would cut across one surface. Rejected: five-child cut
  as named; standalone queue child.
  Date/Author: 2026-08-04, human approved the amended shape (phase-2
  reaction).
- Decision: gh mode remains a supported first-class plugin substrate;
  board binding is per-repo configuration (X5).
  Rationale: ida-solution is a real marketplace consumer with no
  Postgres service; the plugin's zero-dependency identity is preserved
  in the parent spec's product boundary. The pivot demotes GH to
  mirror for boards that FLIP — it does not retire the gh substrate
  for repos that never do. Rejected: hard cutover of the plugin to
  API-only. **Flagged for the human at spec review — decided by the
  session, not grilled.**
  Date/Author: 2026-08-04, session.
- Decision: E3 closes at phase web; A7 (phase native) is a tracked,
  conditional continuation — not required for closure.
  Rationale: the parent spec's own phasing separates web and native;
  parent-level acceptance is phrased on browser surfaces; holding E3
  open for a native app would hostage recomposition on a phase the
  human gates separately. Rejected: A7 required (closure hostage);
  dropping A7 to Deferred (the human named it in the cut — it stays a
  tracked child).
  Date/Author: 2026-08-04, session, from the parent spec's phasing.
- Decision: terminal gateway (A6) deliberately last among required
  children; its externals are start-time gates.
  Rationale: the 2026-08-04 steering decision (parent spec Decision
  Log) — the ledger + queue are the communication surfaces; A6's
  externals (M2 wire, appserver-born sessions) are the two things the
  probes showed missing, and nothing in surfaces 1–3 waits on them.
  Rejected: terminal in the first wave (rebuilds the
  attach-one-at-a-time model the Purpose rejects).
  Date/Author: 2026-08-04, human (steering frame) + session (edge
  placement).
- Decision: Postgres vendor and A1's deploy target are A1's decisions
  at dispatch (means, not ends), with R4's re-priced numbers as input.
  Rationale: the schema is host-agnostic by construction; fixing a
  vendor in the roadmap would bind a means and go stale exactly the
  way the 07-23 Supabase verdict did. Rejected: fixing hosting here.
  Date/Author: 2026-08-04, session.
- Decision: Parent acceptance 2's SDK-decision species is conditional
  on external:cc-harness-T5 — E3 can close on the board species alone.
  Rationale: external timing must not hostage closure; the projection's
  board side (schema, roles, ingest seam) still lands in A1, and the
  queue is species-agnostic by construction, so the unified queue is
  demonstrated the moment T5 lands with zero A3 rework. This
  CONDITIONALIZES a human-settled parent decision (unified queue over
  both park backends, 2026-07-30) — **flagged for the human at spec
  review; authored by the session.** Rejected: requiring both species
  (closure hostage to another repo's backlog); dropping the species
  (reverses the parent decision outright).
  Date/Author: 2026-08-04, session (review F7).
- Decision: Run liveness is pluggable-source (X6) — sessionStore join
  when the binding names a store, automation-renewed lease otherwise,
  authenticated run writes as evidence; A1 owns the semantics, A2 the
  local-worker mechanics.
  Rationale: the r2 draft's mtime-only rule would reclaim live
  pre-cluster workers (the heartbeat `NOT EXISTS` is vacuously true
  for a local session); E2's zero-new-duties doctrine survives because
  renewal is dispatch automation, never worker prose. Rejected:
  mtime-only liveness (fences the very workers A2 and A5.G1 depend
  on); a worker-authored heartbeat duty (reverses E2 doctrine).
  Date/Author: 2026-08-04, session (review F1 — the blocking finding).
- Decision: Linear mirror deferred out of A4's acceptance; the flip
  (A5) is human-triggered.
  Rationale: no live Linear consumer exists; a cutover is an
  outward-facing batch action on a live board — operator timing.
  Rejected: Linear in A4's required gates; automatic flip on
  readiness.
  Date/Author: 2026-08-04, session.

## Surprises & Discoveries

- Observation: A1–A5 are cluster-independent — the board, UI, and
  mirrors need one Postgres and a deploy target, not the k8s/gVisor
  runtime. E3's critical path does not queue behind the R-round
  spikes; only the deliberately-late A6 waits on the swarm runtime.
  Evidence: r2-board-schema v2 §4 (pooler/direct budget), r2-platform
  §6 (one small service), A0 Plan 1's Render deploy artifacts.
- Observation: the platform's hardest-looking parts have shipped prior
  art — 37 KB of proven topology interactions (BOARD.html), a complete
  never-executed board-service plan with carrying-over acceptance
  drills, and a live-probed decisions-as-state appserver. The
  genuinely new construction is the queue rendering, the mirror
  writers, and the adapter seam.
  Evidence: Grounding Baseline.
- Observation: the mirror's target vocabulary already exists in
  production — the v8 label scheme IS what the GH mirror must render,
  so A4's mapping is a port of a shipped rendering, not a design.
  Evidence: `_board.py` STATUS_COLORS / label scheme, live on the
  doperpowers board.

## Outcomes & Retrospective

Pending — written when the unit closes. Closing is a RECOMPOSITION
check: verify Parent-Level Acceptance as written — all children landed
is not the same event — then retrospect. This is a code-bearing parent
(children share the API surface and one executable platform): the
closure package routes through QAgent scale review. Operational note
(review F10): with children split across two boards (Decision 1), no
single board's parent linkage sees all of E3 — recomposition-due
automation cannot fire for the epic itself; closure runs off this
Tracking Map by hand.

## Revision Notes

- 2026-08-04: v1.2, codex adversarial review (gpt-5.6-sol, xhigh; 7
  findings, 6 adopted): **A5.G1 rewritten as a full cutover barrier**
  (freeze ALL writes, drain/migrate active claims, high-water-mark
  delta + parity check, defined rollback, out-of-band control
  principal — was registration-freeze only, which would have repaired
  away legitimate straggler writes); **X6 wake delivery made
  level-triggered and crash-safe** (A2 = end-to-end delivery owner,
  ack markers keyed to the answer event id, crash-at-boundary drill in
  A2's acceptance); the cluster-independence claim narrowed (A1–A5
  proceed, E3's CLOSURE still queues behind A6's externals — now
  owned rows in the Tracking Map). Companion fixes in the r2 draft:
  answer-transaction event-before-projection ordering (FK made the
  drafted order unsatisfiable), worker-authored `in-review → done`
  epic-guarded at the API boundary (leaf reviews exit via
  `confident-ready`), parent-impact consumption as anti-joined
  `parent-impact-consumed` events with a one-consumption unique index.
  The 7th finding (SDK-species conditionalization) restates the
  already-flagged Decision Log entry — the human's gate ruling.
- 2026-08-04: v1.1, independent fable review (10 findings, all adopted;
  none re-opened a human decision): **X6 signal-plane contract**
  (pluggable liveness + answer-wake ownership — the blocking finding:
  the r2 draft's sessionStore-only heartbeat would have reclaimed
  every live pre-cluster worker); X2 extended to three principal
  classes (human credentials are A1-contract, A3-mechanism);
  completion-gate edges added (A2 → A1.G3, A3.G3 → A2, A6 → A3);
  X1/A4 bind corrected (mirror writers ride the DB role, not the
  API); T5/T11 board-side ingest assigned to A1; the SDK-species
  conditionalization surfaced as a flagged Decision Log entry;
  manual-recomposition note in Outcomes. Companion edits: r2 draft
  open item 8; parent-spec board-placement disambiguation.
- 2026-08-04: v1, authored from the E3 decomposing run (grounding →
  tentative cut → human reaction → grill Q1–Q4 → this document).
  Terminal demotion inherited from the parent spec's same-day steering
  decision.
