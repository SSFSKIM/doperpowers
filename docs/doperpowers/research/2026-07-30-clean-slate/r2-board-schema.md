# R2 — Board-service schema draft, v2 (rebased 2026-08-04)

> Sibling deliverable to `r2-platform.md` §6; **the input to the E3
> (Arkho platform) decomposing run**
> (`specs/2026-07-30-control-plane-product-design.md` gates its division
> on this). This is a DRAFT for design consumption — a schema to
> decompose against, not a migration to run. Lineage: A0 Plan 1
> (`plans/2026-07-23-a0-core-board-service.md`) extended with the E1
> lane states (`specs/2026-07-30-implement-lane-split-design.md`), the
> E2 ledger doctrine (`specs/2026-07-30-ticket-ledger-observability-design.md`),
> the live v8 vocabulary (`skills/issue-tracker/scripts/_board.py`), the
> managed-postgres-core connection facts, and the shipped cc-harness
> Postgres sessionStore adapter (verified 2026-07-30 at
> `CC-to-SDK/harness/src/store/postgresSessionStore.ts`).
>
> **v2 (2026-08-04):** rebased onto **E1 v1.3.3 as shipped** (v7.30.0,
> hardened through the E2 campaign) and the **E2 v2.x domain contract**
> (complete 2026-08-02). The 2026-07-30 draft predated both; E2's
> § "R2 rebase requirements" names seven defects this revision must fix
> visibly — see § Rebase record immediately below.

## Rebase record (2026-08-04)

The seven named defects (E2 § R2 rebase requirements), each with its
fix:

| # | Named defect (v1) | Fix in v2 |
|---|---|---|
| 1 | Missing `in-review → ready-for-architect` QAgent escalation edge | Edge added to the legality table (note required, convergence-counted) — the third-address edge per E1 v1.3 (§1) |
| 2 | Claimed all three park states resume to pre-park | Only `needs-human` carries the session-resume contract, returning to the **parking lane's in-flight state** (mapped, not verbatim `from_state`); `needs-info` is fold-and-recut (run closed at park, later dispatch = fresh claim); `interactive-preferred` is a human-attended pause (§1 park semantics, §3.3) |
| 3 | Required `plan_path` on every `in-design → ready-for-implementer` transition | The edge requires a note always, plus exactly one of: a `path@SHA` pin, the `pre-spec` sentinel, or the **decompose exit** (children exist, no plan — the parent becomes an epic) (§1, §3.2) |
| 4 | Convergence counting lacked E1's post-adjudication reset | The COUNT runs over **worker-authored** traversal events **since the last human-authored event** on the ticket; automation bookkeeping returns never count (`actor_kind` does structurally what the interim board's `[board-epic]`/`[answers]` markers do) (§1) |
| 5 | Lane-crossing release never cleared `ticket.owner_run` | Phase end is ONE transaction executed by the transition endpoint: close the run, **clear `owner_run`**, append a `release` event (E2: never a separate observer) (§3.2) |
| 6 | Hardcoded env-issue birth to `ready-for-implementer` | E2 v2 birth rule: a named agent-executable repair path ⇒ agent lane; no / uncertain ⇒ **`needs-human`** — the inverted default, this category only (§3.5) |
| 7 | Epic auto-close instead of the recomposition return | Full Architect-bracketed epic lifecycle: recomposition-due return, epic dispatch carve-out, scoped terminal authority, closure-package `in-review` gate, per-cycle scale review, reconciliation claims + `[parent-impact]` upward revision (§1a, §3.6) |

**Absorbed beyond the named defects** (E2 v2.x contract items the v1
draft predated): dispatch writes claim-lifecycle records, never workflow
state (§0.7); the composite session-store locator `(store namespace,
project_key, session_id)` plus predecessor-run lineage for reclaims and
forks (§2 `run`); the at-most-one-active-run invariant as a partial
unique index; the parent-pin claim-record stamp for children of epics;
the T5 decision-park durability projection with first-accepted-answer
arbitration (§2 `decision_park`, §3.3); the T11 trusted-hook activity
projection (§2 `run_activity`); `field-change` events restoring the
full event-log reconstruction claim (§0.1, §3.2); the `TimelineReader`
access contract (§4); env-issue queue visibility (human decision queue
only when `needs-human`); token-borne actor trust (§0.8).

**Interim-board mechanisms that dissolve structurally here** (recorded
so the decomposing run doesn't port them): `pre-park:` meta was a build
forced by GitHub having no queryable event record — here the park
*event* is the record; comment-trust filtering (`authorAssociation`)
becomes the token-authenticated `actor_kind`; the parent-pin's
stripped-body contract hash becomes an event-log cursor; the mandatory
new-closure-package-comment-per-cycle protocol clause becomes automatic
(packages are immutable events — a "new package" is necessarily a new
event id, so the stale-stamp supersede hazard cannot arise).

## 0. Design rules the schema encodes

1. **Append-only events + mutable current state** (E2): every
   transition, park, answer, gate verdict, claim, and reclaim is an
   immutable `ticket_event` row; current state lives in mutable
   `ticket` columns. **Every mutable-field write (priority, `plan`,
   branch, PR, note, labels) also appends a `field-change` event**, so
   the reconstruction claim (E2 acceptance 7) holds for the whole board
   state — including claim/release history — not just workflow state.
   Reading current state never folds the log.
2. **Server-side legality as data** — a `(from_state, to_state)` table
   with per-EDGE note/PR requirements (E1 needs edge-keyed notes: v8's
   state-keyed `NOTE_REQUIRED` cannot express "note required on
   `in-design → ready-for-implementer` but not at birth into it").
3. **Workers never speak SQL** (A0 Plan 1 / managed-postgres-core §4):
   all worker writes go through the board API with a per-run bearer
   token scoped to the run's own ticket; the DB credential exists only
   in the API process, dispatcher, and mirror writers.
   Subagents-never-write (E2) is enforced by token scoping, not
   convention.
4. **Claim is ownership, not a state transition** (E1 acceptance: the
   worker's first board write is its gate verdict). Claim = `owner_run`
   + fence bump + a `claim` event, in one transaction.
5. **Heartbeat is derived, not written** (E2 zero-new-duties, extended
   to the lease): liveness = the cc-harness sessionStore's own append
   stream (`ccs_sessions.mtime`), joined via the run binding.
   `lease_expires_at` covers only the claim→session-bind window.
6. **Connection placement** (managed-postgres-core §2, substrate-
   independent): API + mirror writers on transaction-pooled connections
   (everything they run is single-statement or single-transaction);
   dispatcher/reconciler holds the only direct connections (LISTEN +
   level-triggered poll fallback); advisory locks only in
   `pg_advisory_xact_lock` form.
7. **Dispatch writes claims, never workflow state** (E2 v2): claim /
   bind / release / reclaim / supersede records are automation's duty —
   without them there is no ticket↔session attribution and no
   reconstructible claim history — but dispatch never moves a ticket
   between lanes; the worker's first WORKFLOW write is its own. Phase
   end (every lane-crossing or scope-ending transition) closes the run
   in the same transaction as the state write, executed by the
   transition endpoint itself.
8. **Actor trust is token-borne.** Every event's `actor_kind`/`actor`
   derives from the authenticated credential (per-run bearer / human
   session / automation identity) — never from caller-supplied fields.
   The interim board's comment-trust filtering and marker conventions
   map to this column, structurally.

## 1. State machine (v8 ∪ E1 v1.3.3)

States: `ready-for-architect`, `in-design`, `ready-for-implementer`,
`in-progress`, `in-review`, `confident-ready`, `needs-human`,
`needs-info`, `interactive-preferred`, `deferred`, `done`, `wontfix`.

- Birth states (registrar's lane classification, E1: unsure →
  implementer): `ready-for-architect`, `ready-for-implementer`,
  `needs-info`, `needs-human`, `interactive-preferred`, `deferred`.
  Birth-classification rules live API-side (the register endpoint), so
  every registrar path — worker, human, triage — classifies uniformly.
- Categories: `work` (default), `spike` (always born
  `ready-for-implementer`; category precedence over lane judgment is
  state-free, not birth-only — a spike moved into `ready-for-architect`
  by hand still dispatches on the spike protocol), `env-issue` (E2:
  non-blocking environmental friction; fire-and-continue registration
  by any worker via its existing `--spawned-by` authority; birth per
  the v2 rule in §3.5 — **`needs-human` default**).
- **Park semantics are three distinct contracts** (E1 v1.3.3 + E2 run
  map — not one resume rule):
  - `needs-human` — a PAUSE. The run stays open and bound; the answer
    relay resumes the same run into the **parking lane's in-flight
    state** (§3.3). Discriminant: a decision or real-world input only
    the human can provide.
  - `needs-info` — a SCOPE END. The run closes at park time;
    fold-and-recut: the answerer folds content into the body and
    routes the ticket lane-aware back to a queue state; the later
    dispatch is a fresh claim, never a resume.
  - `interactive-preferred` — a human-attended pause (run open); exits
    are human-authored. Unchanged v8 semantics.
  - The third address: missing or broken design an agent can author →
    `ready-for-architect` (an escalation edge, not a park).
- Terminal: `done`, `wontfix`.

Legality (seed data for `legal_transition`; **note** = note required on
the edge, **pr** = review artifact required):

| from \ to | notable edges |
|---|---|
| `ready-for-architect` | → `in-design` (architect gate pass, `[gate]` event); → parks per the discriminant (gate fail); → `wontfix`/`deferred` |
| `in-design` | → `ready-for-implementer` (completion, **note**, plus exactly ONE of: `plan` = `path@SHA` pin, `plan` = `pre-spec` sentinel, or the decompose exit — children exist and `plan` is null); → parks (**WIP banked** on the pushed branch per E1); → `done`/`wontfix` **epic-guarded** (scoped terminal authority — recomposition verdicts only, §1a); → `wontfix`/`deferred` |
| `ready-for-implementer` | → `in-progress` (implementer gate/DIRECT, or plan-execution first write); → `ready-for-architect` (gate escalation, **note**, convergence-counted); → parks; → `wontfix`/`deferred` |
| `in-progress` | → `in-review` (**pr** — leaf: PR URL; epic: closure-package event, §1a); → `ready-for-architect` (return park, **note**, convergence-counted); → parks (**note**); → `done` (non-PR work); → `wontfix`/`deferred` |
| `in-review` | → `in-progress` (fix waves); → `confident-ready`; → `done` (**epic-guarded for workers** — only a QAgent scale-review claim whose stamped closure-package id matches the epic's current one; a leaf reaches `done` from review via `confident-ready` or a human write, per E2's worker-never-closes doctrine); → **`ready-for-architect` (review impasse, **note**, convergence-counted — the QAgent's third-address edge, E1 v1.3)**; → `needs-human`/`needs-info` (**note**); → `wontfix`/`deferred` |
| `needs-human` | → `in-design` / `in-progress` / `in-review` (answer relay, lane-mapped — §3.3; the `in-review` return needs no fresh **pr**: the gate binds the `in-progress → in-review` edge only, per E1 v1.3.2); → other parks; → `done` (spike handoff, human); → `wontfix`/`deferred` |
| `needs-info` | fold-and-recut only: → `ready-for-implementer` / `ready-for-architect` (answerer's lane-aware routing; no resume) |
| `interactive-preferred` | human-authored exits (v8 semantics) |
| `confident-ready` | → `done` |
| `deferred` | → `ready-for-architect` / `ready-for-implementer` (revival, lane-aware: `plan`-attached or unsure → implementer; architect only by explicit judgment) |

**Bookkeeping edges live OUTSIDE the legality table** (reconciler /
dispatcher authority, `actor_kind='automation'`, always evented, never
convergence-counted): the recomposition-due return and the reconcile
return (epic's pulled in-flight state → `ready-for-architect`), and the
epic pull (a waiting epic → `in-progress` when its first child goes
active). These are the platform forms of `pull_epics` and the sweep's
returns.

Server-enforced rules that live in the transition function, not the
table:

- **Convergence rule (E1 T6, with reset):** before writing an
  escalation/return edge (`ready-for-implementer → ready-for-architect`,
  `in-progress → ready-for-architect`,
  `in-review → ready-for-architect`, or a down-shortcircuit ruling
  being re-contradicted), count prior **worker-authored**
  (`actor_kind='worker'`) `ticket_event` rows with the same
  `(from_state, to_state)` on this ticket **with `id` greater than the
  ticket's latest human-authored event** (the adjudication reset — a
  human-sanctioned re-traversal starts a fresh count). If ≥1 exists,
  the write is transmuted into a `needs-human` park carrying this
  traversal's position plus a pointer to the event trail (the
  mechanical substitution only ever has one side's note — E1 v1.3.2).
  Automation bookkeeping returns are excluded by `actor_kind`, so a
  second recomposition cycle never trips the counter (E2).
- **Down-shortcircuit binding (E1 T3):** `plan = 'pre-spec'` written on
  the `in-design → ready-for-implementer` edge is a persistent
  PLAN-NEED RULING binding every subsequent Implementer's plan-need
  check; the API surfaces it on claim.
- **The two `plan` values are two concepts** (E1 retrospective, lesson
  4): a `path@SHA` pin is an AUTHORIZATION EVENT (routes the
  Implementer to plan-execution; the Architect's handoff event is the
  review loop's authorization-time anchor); `pre-spec` is a plan-need
  ruling (the ticket still runs DIRECT and still gates). Any rule
  reading the field must say which it means; `null` = plan-less DIRECT.

### 1a. Epic lifecycle (Architect-bracketed, E2 v2)

Non-leaf nodes are bracketed by the architect lane — decompose at the
start, recompose at the end. No epic auto-close exists anywhere in this
schema.

- **Decompose exit:** mid-design decomposition leaves the parent via
  `in-design → ready-for-implementer` (note "decomposed", no `plan`);
  the parent now has children and is an epic. Epics are excluded from
  implementer-lane claims (§3.1); the first active child's pull moves
  the waiting epic to `in-progress` (bookkeeping).
- **Recomposition-due return:** all children terminal ("required" =
  every child; no optionality machinery) ⇒ the reconciler returns the
  parent from its pulled in-flight state to `ready-for-architect` with
  a `recomposition-due` note — never directly to done. All-wontfix
  epics wake recomposition too (the old at-least-one-done guard is
  retired): the Architect's verdict may be `wontfix`.
- **Epic dispatch carve-out:** epics are undispatchable EXCEPT in
  `ready-for-architect`, which dispatches to the architect lane only —
  recomposition and reconciliation claims. Routing is **state-based**
  (E2 campaign: the architect queue needs no is-epic branch; the
  dispatched Architect reads children itself).
- **Scoped terminal authority:** a recomposition Architect may write
  the epic's `done`/`wontfix` from `in-design` (epic-guarded edges —
  the transition function verifies the ticket has children and the
  writing run is an architect-lane claim). Leaf terminal writes keep
  the worker-never-closes doctrine.
- **Code-bearing integration parents** route `in-review` first: the
  pinned **closure package** — parent acceptance, child closing
  artifacts, exact base/head ranges, cross-child contracts,
  recomposition evidence — is an immutable `ticket_event`; its id in
  the `pr_url` slot satisfies the in-review gate (epics only). QAgent
  **scale review runs once per RECOMPOSITION CYCLE, keyed on the
  closure-package event id** — append-only makes a new cycle's package
  a new id by construction. Clean verdict ⇒ the QAgent closes the epic
  `done`; any defect ⇒ a corrective child ticket (no branch to
  fix-wave — the children are merged) and the parent waits again.
- **Upward revision (children change, parents must not go stale
  silently):** dispatch stamps a **parent pin** into every claim on a
  ticket with a parent — the parent id plus the parent's event-log
  cursor at dispatch time (and the spec `path@SHA` when the contract
  lives in a repo document). "What contract did this child execute" is
  always answerable; staleness = contract-relevant parent events after
  the pinned cursor. A child revises its own MEANS freely; discovery
  touching a parent-owned END becomes a **parent-impact proposal** — a
  structured event on the child's own ticket, within its own-ticket
  write authority. The reconciler's reconcile pass reads unconsumed
  proposals and performs the parent's `ready-for-architect` return
  BEFORE final recomposition when siblings are building against the
  stale contract; parked or terminal parents are skipped WITHOUT
  consuming the proposal (E2 implementation decision). The reconciling
  Architect's release exit is a `needs-info` park ("reconciled —
  waiting on children") — legal from `in-design`, pull-eligible, run
  closed. Asymmetric authority: evidence-compelled technical
  reconciliation is the Architect's; purpose changes, material
  acceptance reduction, and taste calls park `needs-human`.
- **Lineage check at recomposition:** the Architect reconciles every
  child against the final parent revision (child, pinned cursor, later
  changes, reconciled?, evidence); no advance to QAgent until every
  material change is incorporated, explicitly irrelevant, or carried by
  a corrective child. The QAgent package pins the parent cursor; a
  parent change mid-review restarts the review.

## 2. DDL draft

```sql
-- ── schema separation ──────────────────────────────────────────────
create schema if not exists board;    -- this file
-- sessionStore tables (ccs_entries / ccs_sessions) are created by the
-- cc-harness adapter's ensurePostgresSessionStoreSchema() under the
-- sessions role's search_path → schema "sessions" (the adapter does not
-- schema-qualify; search_path is the seam). See §4.

-- ── legality as data ───────────────────────────────────────────────
create table board.legal_transition (
  from_state   text not null,
  to_state     text not null,
  require_note boolean not null default false,
  require_pr   boolean not null default false,   -- in-progress→in-review only;
                                                 -- park-return edges never re-demand it
  primary key (from_state, to_state)
);

-- ── tickets: mutable current state (E2) ────────────────────────────
create table board.ticket (
  id           bigint generated always as identity primary key,
  title        text not null,
  body         text not null default '',   -- pre-spec sections (registrar-authored at register time)
  category     text not null default 'work'
               check (category in ('work','spike','env-issue')),
  state        text not null,
  priority     text not null default 'P2'
               check (priority in ('P0','P1','P2','P3')),
  park_note    text,                        -- current note (v8 --note), cleared on unpark
  plan         text,                        -- E1 plan meta: '<path>@<sha>' pin | 'pre-spec' | null
                                            -- (two concepts — §1; NOT a free path column)
  branch       text,
  pr_url       text,                        -- leaf: PR URL; epic: closure-package event id (§1a)
  owner_run    bigint,                      -- current claim; null = unowned; CLEARED at phase end (§3.2)
  fence        bigint not null default 0,   -- bumps on every claim
  parent       bigint references board.ticket(id),   -- decomposition epic
  spawned_by   bigint references board.ticket(id),   -- scope-out lineage (env-issue rides this)
  labels       jsonb not null default '{}'::jsonb,   -- engine:* opt-ins, env key, misc meta
                                                     -- (architect dispatch IGNORES engine:* — E1 X4 narrowing)
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index on board.ticket (state) where state like 'ready-%';
create index on board.ticket (category, state);
-- No pre_park column: the park event's from_state IS the durable
-- record here (the interim board's `pre-park:` meta was a build forced
-- by GitHub's lack of a queryable event log — do not port it).

-- ── edges beyond lineage ───────────────────────────────────────────
create table board.ticket_edge (
  a    bigint not null references board.ticket(id),
  b    bigint not null references board.ticket(id),
  kind text not null check (kind in ('blocked-by','relates')),
  primary key (a, b, kind)
);

-- ── append-only event log (E2; the durable human-answer record) ────
create table board.ticket_event (
  id         bigint generated always as identity primary key,
  ticket_id  bigint not null references board.ticket(id),
  at         timestamptz not null default now(),
  actor_kind text not null check (actor_kind in ('worker','human','automation')),
  actor      text not null,        -- run id / human handle / 'dispatch','reconciler','mirror'
                                   -- (derived from the authenticated credential — §0.8)
  run_id     bigint,               -- set for worker-authored events
  kind       text not null,        -- 'register','claim','bind','release','reclaim','supersede',
                                   -- 'gate','transition','park','answer','superseded-answer',
                                   -- 'field-change','note','comment','parent-impact',
                                   -- 'parent-impact-consumed','closure-package'
  from_state text,
  to_state   text,
  body       jsonb not null default '{}'::jsonb
               -- parks: numbered questions + recommended answers (the existing
               -- batch format — E3 renders it as preselected forms)
               -- answers: the human's numbered replies
               -- transitions: shortcircuit flag, orientation summary,
               --   recomposition-due / reconcile markers, etc.
               -- field-change: {field, old, new}
               -- parent-impact: {parent, clauses, evidence}
               -- parent-impact-consumed: {proposal_event_id}
);
create index on board.ticket_event (ticket_id, id);
-- Exactly one consumption per proposal, enforced structurally (the
-- proposal row is immutable — consumption is its own appended event):
create unique index ticket_event_one_consumption
  on board.ticket_event ((body->>'proposal_event_id'))
  where kind = 'parent-impact-consumed';
-- No UPDATE/DELETE grants exist on this table for ANY role (append-only
-- by privilege, not convention).

-- ── runs: claims, fencing, lease, and the session binding ──────────
create table board.run (
  id               bigint generated always as identity primary key,
  ticket_id        bigint not null references board.ticket(id),
  lane             text not null check (lane in
                     ('architect','implementer','qagent','spike','ops')),
  fence            bigint not null,
  token_hash       text not null,          -- sha256 of the per-run bearer token
  predecessor_run  bigint references board.run(id),
                                           -- reclaim/fork lineage (E2: a reclaim or fork is a NEW
                                           -- run with an explicit predecessor link; restart that
                                           -- keeps claim + session = same run)
  parent_pin       jsonb,                  -- children of a parent: {parent_id, parent_event_cursor,
                                           -- spec_path_at_sha?, section?} stamped by dispatch (§1a)
  -- the E2 binding: ticket → run → (store namespace, project_key, session_id).
  -- Verified against the real session identity at initialization by
  -- trusted automation — never a worker-prompt duty; recorded as a
  -- 'bind' event.
  store_ns         text,                   -- sessionStore namespace (schema / prefix / database)
  project_key      text,
  session_id       text,
  thread_id        text,                   -- appserver thread id
  pod              text,                   -- stable DNS name (Sandbox identity; P3 f.4 "board is the registry")
  virtual_key_id   text,                   -- LLM-gateway key id (revoked on reclaim)
  lease_expires_at timestamptz not null,   -- fallback window: claim → session-bind
  started_at       timestamptz not null default now(),
  ended_at         timestamptz,
  end_reason       text                    -- 'completed','worker-failed','lease-expired',
                                           -- 'cancelled','superseded'
);
create unique index run_one_active_per_ticket
  on board.run (ticket_id) where ended_at is null;   -- "at most one active run" (E2), as a constraint
create index on board.run (lease_expires_at) where ended_at is null;
create index on board.run (project_key, session_id) where ended_at is null;

-- ── decision parks: the T5 durability projection (E2 v2, DECIDED) ──
-- Every park — board-originated AND appserver SDK decisions — lands
-- here with a stable correlation id, so pod death never silently loses
-- a question and the unified queue is a pure board query.
create table board.decision_park (
  correlation_id  text primary key,        -- stable across re-raises (re-raise = idempotent upsert)
  ticket_id       bigint not null references board.ticket(id),
  run_id          bigint not null references board.run(id),
  species         text not null check (species in ('board','sdk-decision')),
  question        jsonb not null,          -- batch format / SDK decision payload
  raised_at       timestamptz not null default now(),
  answer_event_id bigint references board.ticket_event(id),  -- null = open
  answered_via    text check (answered_via in ('board','appserver'))
);
create index on board.decision_park (ticket_id) where answer_event_id is null;
-- First accepted answer wins: the answer transaction is a conditional
-- UPDATE ... WHERE answer_event_id IS NULL; a losing racer (board and
-- appserver answering the same question) is recorded as a
-- 'superseded-answer' ticket_event and rejected here — the worker
-- never observes two answers (E2 acceptance 8).

-- ── activity: the T11 trusted-hook projection (E2 source #3) ───────
-- The live intra-turn carrier: tool starts/ends, prompt boundaries.
-- Automation-authored (the trusted harness hook emitter), immutable,
-- worker- and UI-read-only. Per-source order only; source time and
-- observed time are distinct fields, never conflated (E2 ordering
-- semantics).
create table board.run_activity (
  id          bigint generated always as identity primary key,
  run_id      bigint not null references board.run(id),
  observed_at timestamptz not null default now(),
  source      text not null default 'hook',
  source_time timestamptz,
  cursor      text,                        -- source-local cursor (e.g. transcript entry id)
  kind        text not null,               -- 'tool-start','tool-end','prompt-boundary',...
  body        jsonb not null default '{}'::jsonb
);
create index on board.run_activity (run_id, id);
-- INSERT-only for the hook-emitter role; no UPDATE/DELETE for any role.

-- ── mirror plane: transactional outbox + external refs ─────────────
create table board.mirror_outbox (
  id              bigint generated always as identity primary key,
  mirror          text not null check (mirror in ('github','linear')),
  ticket_id       bigint not null references board.ticket(id),
  event_id        bigint not null references board.ticket_event(id),
  attempts        int not null default 0,
  next_attempt_at timestamptz not null default now(),
  delivered_at    timestamptz,
  error           text
);
create index on board.mirror_outbox (mirror, next_attempt_at)
  where delivered_at is null;

create table board.mirror_ref (
  ticket_id   bigint not null references board.ticket(id),
  mirror      text not null,
  external_id text not null,               -- GH issue number / Linear issue id
  last_state  text,                        -- last state asserted on the mirror
  synced_at   timestamptz,
  primary key (ticket_id, mirror)
);
```

## 3. The transaction shapes

### 3.1 Claim (lane-aware; pooler-safe single transaction)

```sql
begin;
-- per-lane concurrency cap, serialized without session state
-- (xact-scoped advisory lock is the pooling-safe variant — never
--  pg_advisory_lock under a transaction pooler). The architect lane's
--  cap is the Fable-spend lever (E1) and is set independently:
select pg_advisory_xact_lock(hashtext('lane:' || $lane));
-- refuse if the lane is at cap:
--   select count(*) from board.run where lane=$lane and ended_at is null;

with pick as (
  select t.id, t.fence from board.ticket t
  where t.state = $lane_state          -- 'ready-for-architect' | 'ready-for-implementer'
                                       -- | 'in-review' (qagent lane)
    and t.owner_run is null
    -- epics are never dispatchable on the implementer-side lanes (the
    -- decompose-exit parent rests in ready-for-implementer); the
    -- architect lane takes them in ready-for-architect (recomposition/
    -- reconciliation claims) and the qagent lane in in-review (scale
    -- review) — §1a:
    and ($lane in ('architect','qagent')
         or not exists (select 1 from board.ticket c where c.parent = t.id))
    and not exists (select 1 from board.ticket_edge e
                    join board.ticket blocker on blocker.id = e.b
                    where e.a = t.id and e.kind = 'blocked-by'
                      and blocker.state not in ('done','wontfix'))
  order by t.priority, t.created_at
  for update of t skip locked
  limit 1
)
-- same transaction: run INSERT (fence+1, token hash, lease, and — when
-- the ticket has a parent — the parent_pin stamp: parent id + the
-- parent's current max ticket_event id (+ spec path@SHA when the
-- contract lives in a repo doc); an extension of the claim-lifecycle
-- write authority, never a worker duty), ticket UPDATE (owner_run,
-- fence = fence+1, updated_at), ticket_event INSERT (kind='claim',
-- actor_kind='automation'), NOTIFY board_events.
commit;
```

Zero rows from `pick` = empty lane (dispatcher backs off). Ticket state
is NOT changed — the worker's first workflow write is its own (E1
acceptance 1; §0.7). Once the session exists, trusted automation
verifies the real session identity and records the binding as a `bind`
event with the composite locator `(store_ns, project_key, session_id)`.
`SKIP LOCKED` + same-transaction run/ticket/event writes is exactly the
pooler-safe pattern managed-postgres-core §2 verified; the A0 Plan-1
drill tests (two racing claims → one winner; zombie fence refused)
carry over as this schema's acceptance drills.

### 3.2 Transition (worker- or human-authored)

One transaction: legality lookup in `legal_transition` (missing row =
illegal, 409) → edge-keyed note/PR checks (the in-review gate takes a
PR URL for leaves, a closure-package event id for epics; the epic
terminal edges from `in-design` additionally verify children exist and
the writing run is an architect-lane claim — §1a; a worker-authored
`in-review → done` additionally verifies the ticket is an epic AND the
writing run is the QAgent scale-review claim whose stamped
closure-package id matches the current one — leaf reviews exit via
`confident-ready`) → convergence-rule
COUNT with the post-adjudication reset (§1: worker-authored traversals
since the ticket's latest human event; transmute the second into a
`needs-human` park) → conditional `UPDATE board.ticket SET state=$to
... WHERE id=$id AND state=$from AND ($fence is null OR fence=$fence)`
(0 rows = lost race, 409) → `ticket_event` INSERT (plus a
`field-change` event for every mutable-field write the call carries —
`plan`, branch, PR, priority, note) → `mirror_outbox` INSERT (if the
edge is mirror-relevant) → `NOTIFY board_events`.

Worker auth: bearer token hash → live run → run must own this ticket
AND carry the current fence.

**Phase end is this same transaction** (E2 — never a separate observer
that could lag or die between the two writes). The run-state map:

- `needs-human` / `interactive-preferred`: PAUSE — the run stays open
  and bound; the answered resume is the same run.
- `needs-info`, `deferred`, `wontfix`, `done`, and every lane crossing
  (E1 T2/T3/T4/T5, the QAgent escalation, the reconciliation release):
  SCOPE END — stamp `run.ended_at` (`end_reason='completed'`), **clear
  `ticket.owner_run`**, append a `release` event, all atomically with
  the state write. Binding releases; the next dispatch binds fresh.

Automation bookkeeping transitions (recomposition-due return, reconcile
return, epic pull — §1a) run through a reconciler-only path: exempt
from `legal_transition`, still fully evented (`actor_kind='automation'`
with a distinguishing body marker), still outbox-mirrored.

### 3.3 Park answer (E1 T7, v1.3.3 form)

**The relay serves `needs-human` only.** The answer API, in one
transaction: `SELECT … FOR UPDATE` the park's `decision_park` row; if
`answer_event_id` is already set (a first answer won the lock race),
append only a `superseded-answer` event and stop — the projection is
untouched and the worker never observes two answers (first accepted
wins, E2). Otherwise append the `answer` event (body = numbered
replies) FIRST, then bind its generated id — `UPDATE
board.decision_park SET answer_event_id = $new_event_id, answered_via
= $via WHERE correlation_id = $c` — and return the ticket to **the
parking lane's in-flight state**, mapped from the latest `park`
event's `from_state`. (The event INSERT must precede the projection
UPDATE: `answer_event_id`'s foreign key to the identity-generated
`ticket_event.id` makes the reverse order unsatisfiable.)

| park written from | returns to |
|---|---|
| `ready-for-architect`, `in-design` (architect lane — incl. gate-fail parks; the resumed session re-states its verdict) | `in-design` |
| `ready-for-implementer`, `in-progress` (implementer lane) | `in-progress` |
| `in-review` (QAgent) | `in-review` (no fresh PR demanded — the gate binds the `in-progress → in-review` edge only) |

In-flight, never the dispatchable queue: a `ready-for-*` return would
race the dispatcher onto a second worker in the window before the
resumed session shows liveness (E1 v1.3's race). A born-parked ticket
has no park event; its answer stays on the fold path and the answerer
assigns the lane per the birth rule. `needs-info` answers never touch
this endpoint: fold-and-recut (§1) — body edit (`field-change` event) +
lane-aware queue return by the answerer; the run already closed at park
time, so the later dispatch is a fresh claim.

SDK-originated parks (`species='sdk-decision'`) answer through the
appserver's respond path; the projection write-back and arbitration are
identical, so a re-raised decision after pod death correlates to the
original id idempotently and the log never shows an ambiguous outcome.

### 3.4 Reclaim (reconciler, direct connection)

A run is stale when BOTH signals are silent:

```sql
update board.run r
   set ended_at = now(), end_reason = 'lease-expired'
 where r.ended_at is null
   and r.lease_expires_at < now()                       -- pre-bind fallback window
   and not exists (                                     -- derived heartbeat (E2):
     select 1 from sessions.ccs_sessions s              -- adapter stamps mtime on
      where s.project_key = r.project_key               -- every append-batch fold
        and s.session_id  = r.session_id
        and to_timestamp(s.mtime / 1000.0) > now() - $lease_window)
returning ...
```

then, per E1's sweep split: for `ready-for-*` tickets clear `owner_run`
and append `reclaim` (fresh dispatch — cheap pre-verdict case); for
in-flight states (`in-design`, `in-progress`, `in-review`) the
dispatcher opens a **NEW run with `predecessor_run` set** (E2: a
reclaim is never the same run, even when it resumes the prior session)
and resumes-with-nudge on a fresh pod (`thread/resume` against the
shared sessionStore — P3 f.5's turn-level durability), never a fresh
dispatch that discards mid-design work. Open `decision_park` rows
survive by construction (the projection is board-owned — pod death
loses no question). Reclaim also revokes `virtual_key_id` at the LLM
gateway (spend-plane fencing). Fence stays untouched — the next claim's
bump is what invalidates the zombie (A0 Plan-1 semantics).

### 3.5 env-issue registration (E2 v2 birth rule)

Plain ticket INSERT with `category='env-issue'`, `spawned_by = filer's
ticket`, after the standard search-before-register dedup (API-side
similarity query). **Birth classification (API-side, inverted default —
this category only):**

> Can the registrar name a concrete repair path that some authorized
> agent of ours can execute in a repository or environment that agent
> controls? Yes ⇒ `ready-for-implementer` (or `ready-for-architect`
> when design-heavy). No / uncertain ⇒ **`needs-human`**.

A `needs-human` env-issue body carries: the observed friction, what the
worker attempted, why agent permissions cannot resolve it, the exact
human intervention requested, and a resolution check. Fire-and-continue:
the filer's own run/ticket is untouched — no park, no state change (E2
acceptance 1). Consumers: the ops-agent sweep and the human queue — but
the human DECISION queue includes an env-issue **only when it sits in
`needs-human`** (E2: agent-lane env issues belong to the ops/filter
view, or fire-and-continue taxes the attention it exists to protect).
`env-issue` is a category, not a lane state — no dedicated dispatch
route; the ops agent may preferentially claim the category.

### 3.6 Recomposition & reconciliation (reconciler bookkeeping, §1a)

- **Recomposition-due:** on child-terminal events, check `NOT EXISTS
  (children not in ('done','wontfix'))`; if the parent sits in its
  pulled in-flight state, return it to `ready-for-architect` with the
  `recomposition-due` marker (bookkeeping transition, evented,
  convergence-exempt by `actor_kind`).
- **Reconcile pass:** a proposal is unconsumed when NO
  `parent-impact-consumed` event references its event id — a
  `NOT EXISTS` anti-join, never a field on the immutable proposal row
  (which by construction can never change to record its own
  consumption). Unconsumed proposals whose parent is claimable or
  in-flight ⇒ the same bookkeeping return with a `reconcile` marker.
  Parked and terminal parents are skipped WITHOUT consuming the
  proposal — it fires on the tick after the park resolves (E2
  implementation decision). The reconciling Architect's claim appends
  one `parent-impact-consumed` event per proposal it folded; the
  partial unique index makes double-consumption a constraint violation,
  not a race.
- **Epic pull:** when a child goes active and its parent epic waits in
  a pull-eligible state (`ready-for-implementer` post-decompose,
  `needs-info` post-reconciliation, `deferred`), return the parent to
  `in-progress` (bookkeeping).
- **Scale-review dispatch:** an epic entering `in-review` with a
  closure-package event id dispatches ONE QAgent run per package id; a
  finished reviewer whose package id no longer matches the epic's
  current one is superseded (`end_reason='superseded'`) and review
  re-dispatches for the new cycle. Append-only ids make the interim
  board's stale-stamp hazard (in-place package edits) structurally
  impossible.

## 4. One-Postgres cohabitation (board + sessionStore)

Verified adapter facts this section rides (Class C, read from
`postgresSessionStore.ts` 2026-07-30): tables `<prefix>_entries` /
`<prefix>_sessions`; TEXT payloads (jsonb rejects U+0000/lone
surrogates); in-INSERT uuid dedup; seq-CAS summary folds; **no
BEGIN/COMMIT, no LISTEN, no session state — pooler-safe by
construction**; DDL exported via `postgresSessionStoreDDL(prefix)` for
migration tooling.

- **Schemas & roles.** `board` schema (this file) + `sessions` schema
  (adapter tables via the sessions role's `search_path = sessions` — the
  adapter doesn't schema-qualify, so search_path is the isolation seam).
  Roles: `board_api` (board schema DML; no DDL; no UPDATE/DELETE on
  `ticket_event` or `run_activity`), `sessions_writer` (INSERT/SELECT/
  UPDATE on `ccs_*` only — the adapter needs UPDATE for the sidecar CAS
  and DELETE only if session deletion is exposed), `activity_writer`
  (INSERT on `board.run_activity` only — the trusted hook emitter, T11),
  `park_mirror` (the cc-harness T5 projection writer: INSERT on
  `board.decision_park` + the idempotent re-raise upsert),
  `mirror_writer` (SELECT events + DML on outbox/refs), `reconciler`
  (direct connection; LISTEN; both schemas SELECT + run/ticket DML),
  `ui_reader` (SELECT both schemas — the E2 derived stream is read-only
  by construction because this role can't write anything).
  **No role has UPDATE/DELETE on `board.ticket_event` or
  `board.run_activity`.**
- **Connection budget.** API + mirror writers + sessions writers ride one
  transaction pooler (the two high-volume flows — appends and claims —
  are pooler-safe; adapter is pooler-safe by design). Direct connections:
  reconciler/dispatcher only (1–2), for `LISTEN board_events` and
  xact-advisory lane caps. This keeps total direct connections
  single-digit regardless of fleet size — every managed candidate's
  connection ceiling becomes irrelevant (managed-postgres-core §4).
- **Load separation.** Session appends dominate writes ~30–100× over
  board writes at A0 (managed-postgres-core §1); the adapter's
  fold-per-append does an O(session-length) indexed SELECT. Levers in
  escalation order: separate pooler pools per role sized so appends
  can't starve claims (day one) → per-role `statement_timeout` → time-
  partition `ccs_entries` → promote the session store to its own
  database/Redis behind the unchanged SessionStore interface (the
  standing promote-sessions-first trigger, managed-postgres-core §6.1).
  The board API contract never changes across any of these.
- **The E2 merged timeline is consumed through a logical
  `TimelineReader` interface, never raw cross-schema SQL** (E2 v2
  access contract). The initial implementation unions
  `board.ticket_event` + `board.run_activity` + the ticket's runs'
  `sessions.ccs_entries` rows via the composite locator `(store_ns,
  project_key, session_id)`; a later sessionStore promotion (separate
  DB, archive tier) must preserve the interface, not the join. Source
  hierarchy and trust order per E2: board events > sessionStore >
  hook activity > OTel (ops plane only — never a canonical timeline
  source). Per-source order only; every derived record carries source,
  source-local cursor, observed-at, and optional source time. Honest
  limitation: `entry` is TEXT (deliberately), so per-entry timestamps
  are parsed in the rendering service, not indexed in SQL; within a
  session, `id` order is the total order (adapter guarantee). Do NOT
  cast `entry::jsonb` in views — it will throw on legitimate payloads
  (U+0000-bearing tool results), the exact failure the adapter chose
  TEXT to avoid.
- **Retention.** `board.*`: permanent (the durable record; storage is
  trivial). `sessions.ccs_entries`: archival job promotes closed runs'
  entries older than ~14 days to object storage (pointer row remains;
  hot set ~100–300 GB target per managed-postgres-core §1.1);
  `ccs_sessions` sidecar rows are kept (they are the cheap summaries).
  Derived-stream and `run_activity` retention policy itself stays
  deferred per E2.

## 5. Mirror writers

One-way outbound only (Class A: edits on a mirror never mutate the SSOT —
no webhook intake exists at all). Per-mirror daemon loop, pooled
connection, `SELECT ... FOR UPDATE SKIP LOCKED` over `mirror_outbox`:

1. **Coalesce per ticket** before delivery: collapse to the newest state
   + batched comment content. Rate basis: GitHub's ~500 content-
   generating req/hr/actor secondary cap makes a raw event feed
   infeasible from mid-A0, while the coalesced human-relevant feed
   (~2–3 writes/run) fits one App actor at A0
   (`board-simplification-a0.md` §1.1–1.2 — re-verify the caps at
   implementation; they are vendor-mutable).
2. Map board states → mirror vocabulary (GH labels mirror the
   `status:*`/`priority:*` scheme the v8 board already renders; Linear
   states per its workflow map). `mirror_ref` holds the external id and
   `last_state` for drift detection; a periodic reconcile pass re-asserts
   board state over any mirror-side edit (repair, never ingest).
3. Failure isolation: `attempts`/`next_attempt_at` exponential backoff
   per row; a dead mirror stalls only its own outbox partition; the SSOT
   never waits on a mirror (outbox insert is in the board transaction,
   delivery is async).

## 6. Open items for the E3 decomposing run

1. **API surface** — Plan 1's ~6 endpoints extend to: lane-aware claim,
   transition, park/answer, comment, register (with dedup + birth
   classification), query/timeline (`TimelineReader`), reconcile,
   env-issue file, decision-park read (the unified queue), activity
   ingest. The decomposition should cut board-service vs gateway
   responsibilities here (P3's authorization gap means the appserver
   proxy needs per-thread authz that the board's run table can back).
2. **Auth tokens** — per-run bearer (hash-stored, Plan-1 pattern) vs
   short-lived JWTs the E3 gateway can also verify; one issuer must
   serve both board API and terminal-proxy authz.
3. **Registrar path for humans/triage** — the triaging-feedback
   registrar writes through the same API; birth-classification rules
   live API-side (E1 migration surface). Origin-less automation
   registration (no `spawned_by`) is platform work E2 deferred.
4. **Sweep/dispatcher process boundary** — reconciler and dispatcher are
   drafted here as one process holding the direct connections; E3 may
   split them (HA pair + leader election via xact-advisory or lease
   table).
5. **SDK-park correlation-id minting** — the T5 projection is DECIDED
   contract (v2; no longer a reserved maybe), but whether correlation
   ids are minted harness-side or board-side, and the exact re-raise
   idempotency wire, is the cc-harness co-design's remaining half (R1
   T5).
6. **Postgres hosting** — schema is host-agnostic by construction (only
   mainline features: identity columns, partial indexes, SKIP LOCKED,
   NOTIFY, advisory xact locks). The 07-23 host verdict (Supabase
   default) predates the GKE landing — Cloud SQL private-IP in the same
   VPC becomes the natural candidate if §1.3 of `r2-platform.md` sticks;
   R4 re-prices this with fresh numbers.
7. **Parent-pin cursor vs repo-doc pin** — the claim stamp records the
   parent's event-log cursor (platform-native staleness detection) plus
   the spec `path@SHA` when the contract lives in a repo document;
   whether the Architect's lineage check reads one, the other, or both
   per ticket class is the decomposing run's to fix.
8. **Liveness-source pluggability** (added 2026-08-04, Arkho roadmap
   review F1) — §0.5/§3.4 derive liveness solely from
   `ccs_sessions.mtime`; a pre-cluster plugin worker (local claude CLI
   session) produces no such feed, so the reclaim's `NOT EXISTS` is
   vacuously true and would fence live workers at lease expiry. The
   Arkho roadmap's X6 assigns A1 the fix: pluggable liveness — the
   sessionStore join when the binding names a store; an
   automation-renewed lease otherwise; any authenticated run write as
   evidence. Zero-new-duties survives: renewal is dispatch automation,
   never worker prose.
