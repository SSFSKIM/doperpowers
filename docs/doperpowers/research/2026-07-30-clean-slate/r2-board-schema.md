# R2 — Board-service schema draft (2026-07-30)

> Sibling deliverable to `r2-platform.md` §6; **the input to the E3
> platform decomposing run** (`specs/2026-07-30-control-plane-product-design.md`
> gates its division on this). This is a DRAFT for design consumption —
> a schema to decompose against, not a migration to run. Lineage: A0 Plan 1
> (`plans/2026-07-23-a0-core-board-service.md`) extended with the E1 lane
> states (`specs/2026-07-30-implement-lane-split-design.md`), the E2 ledger
> doctrine (`specs/2026-07-30-ticket-ledger-observability-design.md`), the
> live v8 vocabulary (`skills/issue-tracker/scripts/_board.py`), the
> managed-postgres-core connection facts, and the shipped cc-harness
> Postgres sessionStore adapter (verified 2026-07-30 at
> `CC-to-SDK/harness/src/store/postgresSessionStore.ts`).

## 0. Design rules the schema encodes

1. **Append-only events + mutable current state** (E2): every transition,
   park, answer, gate verdict, claim, and reclaim is an immutable
   `ticket_event` row; current state lives in mutable `ticket` columns.
   Acceptance: any past board state reconstructs from the event log alone;
   reading current state never folds the log.
2. **Server-side legality as data** — a `(from_state, to_state)` table
   with per-EDGE note/PR requirements (E1 needs edge-keyed notes: v8's
   state-keyed `NOTE_REQUIRED` cannot express "note required on
   `in-design → ready-for-implementer` but not at birth into it").
3. **Workers never speak SQL** (A0 Plan 1 / managed-postgres-core §4):
   all worker writes go through the board API with a per-run bearer token
   scoped to the run's own ticket; the DB credential exists only in the
   API process, dispatcher, and mirror writers. Subagents-never-write
   (E2) is enforced by token scoping, not convention.
4. **Claim is ownership, not a state transition** (E1 acceptance: the
   worker's first board write is its gate verdict). Claim = `owner_run` +
   fence bump + a `claim` event, in one transaction.
5. **Heartbeat is derived, not written** (E2 zero-new-duties, extended to
   the lease): liveness = the cc-harness sessionStore's own append stream
   (`ccs_sessions.mtime`), joined via the run binding. `lease_expires_at`
   covers only the claim→session-bind window.
6. **Connection placement** (managed-postgres-core §2, substrate-
   independent): API + mirror writers on transaction-pooled connections
   (everything they run is single-statement or single-transaction);
   dispatcher/reconciler holds the only direct connections (LISTEN +
   level-triggered poll fallback); advisory locks only in
   `pg_advisory_xact_lock` form.

## 1. State machine (v8 ∪ E1)

States: `ready-for-architect`, `in-design`, `ready-for-implementer`,
`in-progress`, `in-review`, `confident-ready`, `needs-human`,
`needs-info`, `interactive-preferred`, `deferred`, `done`, `wontfix`.

- Birth states (registrar's lane classification, E1: unsure →
  implementer): `ready-for-architect`, `ready-for-implementer`,
  `needs-info`, `needs-human`, `interactive-preferred`, `deferred`.
- Categories: `work` (default), `spike` (always born
  `ready-for-implementer`; category precedence over lane judgment, E1),
  `env-issue` (E2: non-blocking environmental friction; fire-and-continue
  registration by any worker via its existing `--spawned-by` authority;
  consumed by the R3 ops-agent sweep and the human queue).
- Park trio semantics unchanged (three-address discriminant per E1:
  human-only decision → `needs-human`; researchable → `needs-info`;
  agent-authorable design → `ready-for-architect`).
- Terminal: `done`, `wontfix`.

Legality (seed data for `legal_transition`; `note` = note required on the
edge, `pr` = PR URL required):

| from \ to | notable edges |
|---|---|
| `ready-for-architect` | → `in-design` (architect gate pass, `[gate]` event); → parks (gate fail); → `wontfix`/`deferred` |
| `in-design` | → `ready-for-implementer` (completion, **note**, and either `plan_path` set or the down-shortcircuit marker); → parks; → `wontfix`/`deferred` |
| `ready-for-implementer` | → `in-progress` (implementer gate/DIRECT); → `ready-for-architect` (gate escalation, **note**); → parks; → `wontfix`/`deferred` |
| `in-progress` | → `in-review` (**pr**); → `ready-for-architect` (return park, **note**); → parks (**note**); → `done` (non-PR work); → `wontfix`/`deferred` |
| `in-review` | → `in-progress`; → `confident-ready`; → `done`; → `needs-human`/`needs-info` (**note**); → `wontfix`/`deferred` |
| `needs-human`/`needs-info`/`interactive-preferred` | → pre-park state on answer (E1 T7 — the server reads it from the park event's `from_state`, generalizing `board-answer.sh`'s hardcoded `in-progress`); → `done` (spike handoff, human); → other parks; → `wontfix`/`deferred` |
| `confident-ready` | → `done` |
| `deferred` | → `ready-for-architect`/`ready-for-implementer` |

Two server-enforced rules that live in the transition function, not the
table:

- **Convergence rule (E1 T6):** before writing an escalation/return edge
  (`ready-for-implementer→ready-for-architect`,
  `in-progress→ready-for-architect`, or an architect down-shortcircuit
  being re-contradicted), count prior `ticket_event` rows with the same
  `(from_state, to_state)` on this ticket; if ≥1 exists, the write is
  transmuted into a `needs-human` park carrying both notes. The
  append-only log makes this one COUNT — no extra bookkeeping column.
- **Down-shortcircuit binding (E1 T3):** an `in-design →
  ready-for-implementer` event with `body.shortcircuit = true` binds the
  next implementer gate's plan-need check; the API surfaces it on claim.

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
  require_pr   boolean not null default false,
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
  plan_path    text,                        -- E1 'plan:' meta field (machine-readable plan attachment)
  branch       text,
  pr_url       text,
  owner_run    bigint,                      -- current claim; null = unowned
  fence        bigint not null default 0,   -- bumps on every claim
  parent       bigint references board.ticket(id),   -- decomposition epic
  spawned_by   bigint references board.ticket(id),   -- scope-out lineage (env-issue rides this)
  labels       jsonb not null default '{}'::jsonb,   -- engine:* opt-ins, env key, misc meta
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index on board.ticket (state) where state like 'ready-%';
create index on board.ticket (category, state);

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
  actor      text not null,        -- run id / human handle / 'dispatch','sweep','mirror'
  run_id     bigint,               -- set for worker-authored events
  kind       text not null,        -- 'register','claim','reclaim','gate','transition',
                                   -- 'park','answer','note','comment','close'
  from_state text,
  to_state   text,
  body       jsonb not null default '{}'::jsonb
               -- parks: numbered questions + recommended answers (the existing
               -- batch format — E3 renders it as preselected forms)
               -- answers: the human's numbered replies
               -- transitions: shortcircuit flag, orientation summary, etc.
);
create index on board.ticket_event (ticket_id, id);
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
  -- the E2 derived-stream / heartbeat binding:
  project_key      text,                   -- sessionStore join key
  session_id       text,                   -- SDK session id (set once known)
  thread_id        text,                   -- appserver thread id
  pod              text,                   -- stable DNS name (Sandbox identity; P3 f.4 "board is the registry")
  virtual_key_id   text,                   -- LLM-gateway key id (revoked on reclaim)
  lease_expires_at timestamptz not null,   -- fallback window: claim → session-bind
  started_at       timestamptz not null default now(),
  ended_at         timestamptz,
  end_reason       text                    -- 'completed','worker-failed','lease-expired',
                                           -- 'cancelled','superseded'
);
create index on board.run (lease_expires_at) where ended_at is null;
create index on board.run (project_key, session_id) where ended_at is null;

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
--  pg_advisory_lock under a transaction pooler):
select pg_advisory_xact_lock(hashtext('lane:' || $lane));
-- refuse if the lane is at cap:
--   select count(*) from board.run where lane=$lane and ended_at is null;

with pick as (
  select t.id, t.fence from board.ticket t
  where t.state = $lane_state          -- 'ready-for-architect' | 'ready-for-implementer'
    and t.owner_run is null
    and not exists (select 1 from board.ticket_edge e
                    join board.ticket blocker on blocker.id = e.b
                    where e.a = t.id and e.kind = 'blocked-by'
                      and blocker.state not in ('done','wontfix'))
  order by t.priority, t.created_at
  for update of t skip locked
  limit 1
)
-- same transaction: run INSERT (fence+1, token hash, lease), ticket UPDATE
-- (owner_run, fence = fence+1, updated_at), ticket_event INSERT
-- (kind='claim', actor_kind='automation'), NOTIFY board_events.
commit;
```

Zero rows from `pick` = empty lane (dispatcher backs off). Ticket state is
NOT changed — the worker's gate verdict is its first board write (E1
acceptance 1). `SKIP LOCKED` + same-transaction run/ticket/event writes is
exactly the pooler-safe pattern managed-postgres-core §2 verified; the A0
Plan-1 drill tests (two racing claims → one winner; zombie fence refused)
carry over as this schema's acceptance drills.

### 3.2 Transition (worker- or human-authored)

One transaction: legality lookup in `legal_transition` (missing row =
illegal, 409) → edge-keyed note/PR checks → convergence-rule COUNT (E1 T6)
→ conditional `UPDATE board.ticket SET state=$to ... WHERE id=$id AND
state=$from AND ($fence is null OR fence=$fence)` (0 rows = lost race, 409)
→ `ticket_event` INSERT → `mirror_outbox` INSERT (if the edge is
mirror-relevant) → `NOTIFY board_events`. Worker auth: bearer token hash →
live run → run must own this ticket AND carry the current fence.
Lane-crossing transitions (E1 T2/T3/T4/T5) also stamp `run.ended_at`
(`end_reason='completed'`) — binding releases, next dispatch binds fresh
(E1 T8).

### 3.3 Park answer (E1 T7)

The answer API appends an `answer` event (body = numbered replies) and
returns the ticket to its pre-park state, read as the `from_state` of the
latest `park`/`gate-fail` event — `in-design` for an architect park,
`in-progress` for an implementer park. This is the generalization that
makes an answered architect park legally resumable.

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

then, per E1's sweep split: for `ready-for-*` tickets just clear
`owner_run` (fresh dispatch); for in-flight states (`in-design`,
`in-progress`) emit a `reclaim` event that the dispatcher turns into
resume-with-nudge on a fresh pod (`thread/resume` against the shared
sessionStore — P3 f.5's turn-level durability), never a fresh dispatch
that discards mid-design work. Reclaim also revokes `virtual_key_id` at
the LLM gateway (spend-plane fencing). Fence stays untouched — the next
claim's bump is what invalidates the zombie (A0 Plan-1 semantics).

### 3.5 env-issue registration (E2)

Plain ticket INSERT with `category='env-issue'`, `spawned_by = filer's
ticket`, birth state `ready-for-implementer` (lane `ops` consumers pull by
category), after the standard search-before-register dedup (API-side
similarity query). Fire-and-continue: the filer's own run/ticket is
untouched — no park, no state change (E2 acceptance 2).

## 4. One-Postgres cohabitation (board + sessionStore)

Verified adapter facts this section rides (Class C, read from
`postgresSessionStore.ts` 2026-07-30): tables `<prefix>_entries` /
`<prefix>_sessions`; TEXT payloads (jsonb rejects U+0000/lone surrogates);
in-INSERT uuid dedup; seq-CAS summary folds; **no BEGIN/COMMIT, no
LISTEN, no session state — pooler-safe by construction**; DDL exported via
`postgresSessionStoreDDL(prefix)` for migration tooling.

- **Schemas & roles.** `board` schema (this file) + `sessions` schema
  (adapter tables via the sessions role's `search_path = sessions` — the
  adapter doesn't schema-qualify, so search_path is the isolation seam).
  Roles: `board_api` (board schema DML; no DDL), `sessions_writer`
  (INSERT/SELECT/UPDATE on `ccs_*` only — the adapter needs UPDATE for
  the sidecar CAS and DELETE only if session deletion is exposed),
  `mirror_writer` (SELECT events + DML on outbox/refs), `reconciler`
  (direct connection; LISTEN; both schemas SELECT + run/ticket DML),
  `ui_reader` (SELECT both schemas — the E2 derived stream is read-only
  by construction because this role can't write anything).
  **No role has UPDATE/DELETE on `board.ticket_event`.**
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
- **The E2 merged timeline** (decision + derived streams) joins on the
  run binding: `board.ticket_event` rows UNION the ticket's runs'
  `sessions.ccs_entries` rows via `(project_key, session_id)`. Honest
  limitation: `entry` is TEXT (deliberately), so per-entry timestamps are
  parsed in the E3 rendering service, not indexed in SQL; within a
  session, `id` order is the total order (adapter guarantee). Do NOT cast
  `entry::jsonb` in views — it will throw on legitimate payloads
  (U+0000-bearing tool results), the exact failure the adapter chose TEXT
  to avoid.
- **Retention.** `board.*`: permanent (the durable record; storage is
  trivial). `sessions.ccs_entries`: archival job promotes closed runs'
  entries older than ~14 days to object storage (pointer row remains;
  hot set ~100–300 GB target per managed-postgres-core §1.1);
  `ccs_sessions` sidecar rows are kept (they are the cheap summaries).
  Derived-stream retention policy itself stays deferred per E2.

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
   classification), query/timeline, reconcile, env-issue file. The
   decomposition should cut board-service vs gateway responsibilities
   here (P3's authorization gap means the appserver proxy needs
   per-thread authz that the board's run table can back).
2. **Auth tokens** — per-run bearer (hash-stored, Plan-1 pattern) vs
   short-lived JWTs the E3 gateway can also verify; one issuer must
   serve both board API and terminal-proxy authz.
3. **Registrar path for humans/triage** — the triaging-feedback
   registrar writes through the same API; birth-classification rules
   live API-side (E1 migration surface).
4. **Sweep/dispatcher process boundary** — reconciler and dispatcher are
   drafted here as one process holding the direct connections; E3 may
   split them (HA pair + leader election via xact-advisory or lease
   table).
5. **Appserver park mirroring** — whether SDK decision parks get
   mirrored into `ticket_event` (making the unified queue a pure board
   query) is a cc-harness co-design question (R1), not a schema one; the
   schema reserves `kind='park'` with `body.species='sdk-decision'` if it
   lands.
6. **Postgres hosting** — schema is host-agnostic by construction (only
   mainline features: identity columns, partial indexes, SKIP LOCKED,
   NOTIFY, advisory xact locks). The 07-23 host verdict (Supabase
   default) predates the GKE landing — Cloud SQL private-IP in the same
   VPC becomes the natural candidate if §1.3 of `r2-platform.md` sticks;
   R4 re-prices this with fresh numbers.
