# A0 Reconciler — Breakers, Admission, Cost Meter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the A0 spec's failure posture and spend instrument on top of
Plan 1's board service: the cron-shaped reconciler tick (reclaim → kill
over-budget → evaluate breakers → drain Slack outbox), the dispatch-pause
flag with admission caps inside the claim transaction, the per-run usage
rows and monthly cost meter ($/run, $/ticket, cache-read ratio, infra:token
split, cache-broken-canary flagging), and the three-severity Slack outbox —
spec §2 (admission counters), §8 (cost meter), §9 (failure posture).

**Architecture:** Everything stays in the one Postgres and the one Node
process family from Plan 1. Three new tables (`board_flag`, `run_usage`,
`slack_outbox`). The claim transaction gains pause + admission checks (the
spec's circuit-breaker levers). A new tick entrypoint (`node src/tick.js`,
also exposed as admin `POST /tick` so any cron carrier can fire it) runs
one idempotent pass; all breaker state is conditional-UPDATE-shaped, so
overlapping or restarted ticks are safe. Slack delivery is an outbox drain:
rows are marked sent only after the webhook accepts them — no webhook, no
marking, never a fabricated send.

**Failure-class coverage (spec §9's five classes → mechanism):**
1. *Runaway run* — `killOverBudget` (Task 5) parks `needs-human` with a
   transcript pointer; tick queues a `next-block` outbox row (Task 8).
2. *Dead run* — Plan 1's `reclaimStale`, executed as tick step 1; no Slack
   (self-heals, per the spec table).
3. *Claim/dispatch storm* — admission caps in the claim transaction
   (Task 2) + the `start-storm` breaker (Task 6).
4. *Spend runaway* — the `spend-runaway` breaker over `run_usage` (Task 6);
   the Anthropic Console workspace spend cap is the provider-side backstop
   (spec §10 — commercial setting, no code).
5. *Provider outage / 429 storm* — board-side detection is the
   `failure-ratio` breaker (Task 6): a 429 storm surfaces as a burst of
   runs ended with non-`completed` reasons. The worker-side halves of this
   class (step-retry backoff, parking in-flight work as `stream-error`,
   auto-resume on canary success) belong to Plan 3's worker protocol and
   are explicitly NOT in this plan.

**Tech Stack:** Node 22 (ESM, `node:http`, `node:test`, `node:crypto`,
global `fetch`), `pg` (still the only npm dependency), PostgreSQL 15+
(local Docker for dev/test; Supabase in production per spec §5).

**Plan slicing (this is Plan 2 of 4 for the spec):**
1. Plan 1 (done) — T1 spike + schema + board service + claim path (spec §1, §2, §4 schema).
2. **This plan** — reconciler cron + breakers + admission + cost meter + Slack outbox (spec §2 counters, §8 meter, §9).
3. Substrate adapter + E2B dispatch + secrets placement (spec §3, §6).
4. Linear mirror, one-way authority / two-way visibility (spec §1 mirror).

## Global Constraints

- All Plan 1 constraints hold: Node ≥ 22, only npm dep `pg`, frozen ticket
  states, parks require a park note, tests against a REAL Postgres
  (`TEST_DATABASE_URL`) — the SQL semantics are the subject under test,
  never mock the database.
- Dev/test DB (same rig as Plan 1):
  `docker run -d --name a0-pg -e POSTGRES_PASSWORD=a0 -p 54329:5432 postgres:16`
  → `TEST_DATABASE_URL=postgres://postgres:a0@localhost:54329/postgres`
- EXTEND `infra/a0/schema.sql` (idempotent DDL) and
  `test/helpers.js` — do not fork or replace them.
- Cross-plan contract (Plans 3–4 are written against these exact names —
  do not rename): table `board_flag` with flag key `dispatch_paused` and
  value `{"paused": bool, "reason": text}`; tables `run_usage`,
  `slack_outbox`; routes `POST /flags`, `POST /runs/:id/usage`;
  `claimNext` returns `null | {refused} | {runId, ticketId, fence, token}`;
  `POST /claims` maps refusals to 423 (paused) / 429 (caps); tick
  entrypoint `node src/tick.js`.
- New env contract (defaults in parentheses; read at call time):
  `A0_MAX_CONCURRENCY` (200), `A0_MAX_STARTS_PER_MIN` (30),
  `A0_MAX_RUN_MINUTES` (45), `A0_DAILY_SPEND_CAP_USD` (2000),
  `A0_CACHE_RATIO_FLOOR` (0.5), `A0_MONTHLY_INFRA_USD` (0),
  `SLACK_WEBHOOK_URL` (unset ⇒ outbox rows stay unsent).
- Slack severities are exactly `fyi` / `next-block` / `today` (spec §9's
  FYI / next-work-block / Action-today). One breaker trip = ONE outbox row,
  even when several breakers fire in the same tick (highest severity wins);
  while paused, breaker evaluation is a no-op — this is what makes
  acceptance item 6's "posts one Slack message" true by construction.
- Tests never touch real Slack: the drain is tested against a local
  `node:http` fake webhook.

## File Structure

```
infra/a0/
  schema.sql                     — MODIFIED: + board_flag, run_usage, slack_outbox
  README.md                      — MODIFIED: + tick, cron carriers, env additions
  deploy/a0-tick.yml             — example GitHub Actions workflow (copied into
                                   .github/workflows/ at deploy time, not live here)
  board-service/
    src/flags.js                 — board_flag get/set (accepts Pool or client)
    src/claims.js                — MODIFIED: pause + admission checks in the claim tx
    src/server.js                — MODIFIED: /flags, /runs/:id/usage, /tick,
                                   /claims refusal mapping (423/429)
    src/reconcile.js             — MODIFIED: + killOverBudget
    src/breakers.js              — breaker evaluation → pause flag + outbox row
    src/slack.js                 — outbox drain (POST {text} to webhook)
    src/tick.js                  — reconciler tick orchestration + CLI
    src/meter.js                 — cost meter report + CLI
    test/helpers.js              — MODIFIED: truncate list + seedRuns + TEST_URL
    test/schema-extension.test.js
    test/admission.test.js
    test/server-controls.test.js
    test/meter.test.js
    test/overbudget.test.js
    test/breakers.test.js
    test/slack.test.js
    test/tick.test.js
```

---

### Task 1: Schema extension — board_flag, run_usage, slack_outbox

**Files:**
- Modify: `infra/a0/schema.sql`, `infra/a0/board-service/test/helpers.js`
- Create: `infra/a0/board-service/test/schema-extension.test.js`

**Interfaces:**
- Consumes: Plan 1's `makePool`/`applySchema` (`src/db.js`) and the `run`
  table (FK target).
- Produces (cross-plan contract, exact DDL):
  `board_flag(key text pk, value jsonb not null, updated_at timestamptz)`,
  `run_usage(run_id text pk → run(id), model, input_tokens, output_tokens,
  cache_read_tokens, cache_write_tokens, cost_usd numeric(10,4), recorded_at)`,
  `slack_outbox(id identity pk, severity check in fyi|next-block|today,
  message, created_at, sent_at)`. Also test helpers `TEST_URL` and
  `seedRuns(pool, n, {startedMinutesAgo, endedMinutesAgo, endReason})`
  (used by Tasks 5–8: breaker/tick tests need precise timestamps the claim
  path cannot produce).

- [ ] **Step 1: Write the failing schema test**

```js
// infra/a0/board-service/test/schema-extension.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool, seedRuns } from './helpers.js';

test('plan-2 tables exist', async () => {
  const pool = await testPool();
  const r = await pool.query(
    `select table_name from information_schema.tables
     where table_name in ('board_flag','run_usage','slack_outbox')`);
  assert.equal(r.rowCount, 3);
  await pool.end();
});

test('slack_outbox severity is constrained to the three spec severities', async () => {
  const pool = await testPool();
  await pool.query(
    `insert into slack_outbox (severity, message) values ('fyi','x')`);
  await assert.rejects(pool.query(
    `insert into slack_outbox (severity, message) values ('page','x')`));
  await pool.end();
});

test('run_usage requires an existing run', async () => {
  const pool = await testPool();
  await assert.rejects(pool.query(
    `insert into run_usage (run_id, model) values ('no-such-run','m')`));
  await pool.end();
});

test('seedRuns plants runs with controlled timestamps', async () => {
  const pool = await testPool();
  await seedRuns(pool, 3, { startedMinutesAgo: 20, endedMinutesAgo: 5,
                            endReason: 'completed' });
  const { rows } = await pool.query(
    `select count(*)::int as n from run
     where end_reason = 'completed' and ended_at > now() - interval '15 minutes'
       and started_at < now() - interval '10 minutes'`);
  assert.equal(rows[0].n, 3);
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `infra/a0/board-service/`): `npm test`
Expected: FAIL — the whole file errors at load (`helpers.js` does not yet
export `seedRuns`); after Step 4 alone it would still fail on `rowCount`
3 vs 0 until the DDL lands. Plan 1 suites still PASS.

- [ ] **Step 3: Append the DDL to schema.sql**

Append to the end of `infra/a0/schema.sql` (after the `ticket_comment`
block):

```sql
create table if not exists board_flag (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists run_usage (
  run_id             text primary key references run(id),
  model              text not null,
  input_tokens       bigint not null default 0,
  output_tokens      bigint not null default 0,
  cache_read_tokens  bigint not null default 0,
  cache_write_tokens bigint not null default 0,
  cost_usd           numeric(10,4) not null default 0,
  recorded_at        timestamptz not null default now()
);

create table if not exists slack_outbox (
  id         bigint generated always as identity primary key,
  severity   text not null check (severity in ('fyi','next-block','today')),
  message    text not null,
  created_at timestamptz not null default now(),
  sent_at    timestamptz
);
create index if not exists slack_outbox_unsent_idx on slack_outbox (id)
  where sent_at is null;
```

- [ ] **Step 4: Rewrite test/helpers.js (extend truncate list; add TEST_URL + seedRuns)**

Full new content of `infra/a0/board-service/test/helpers.js`:

```js
// infra/a0/board-service/test/helpers.js
import { makePool, applySchema } from '../src/db.js';

export const TEST_URL = process.env.TEST_DATABASE_URL
  ?? 'postgres://postgres:a0@localhost:54329/postgres';

export async function testPool() {
  const pool = makePool(TEST_URL);
  await applySchema(pool);
  await pool.query(
    `truncate session_event, ticket_comment, run_usage, slack_outbox,
              run, ticket, board_flag cascade`);
  return pool;
}

// Plant n run rows directly with controlled timestamps (breaker/tick tests
// need "started 20 min ago, ended 5 min ago" shapes the claim path cannot
// produce). Lease is left FRESH unless the run is ended — a stale lease
// would make reclaimStale eat the run before the code under test sees it.
export async function seedRuns(pool, n, { startedMinutesAgo = 0,
    endedMinutesAgo = null, endReason = null } = {}) {
  await pool.query(
    `insert into ticket (id, state) values ('seed-ticket', 'backlog')
     on conflict (id) do nothing`);
  for (let i = 0; i < n; i++) {
    await pool.query(
      `insert into run (id, ticket_id, fence, token_hash, lease_expires_at,
                        started_at, ended_at, end_reason)
       values (gen_random_uuid()::text, 'seed-ticket', 0, 'seed-hash',
               now() + interval '10 minutes',
               now() - make_interval(mins => $1),
               case when $2::int is null then null
                    else now() - make_interval(mins => $2::int) end,
               $3)`,
      [startedMinutesAgo, endedMinutesAgo, endReason]);
  }
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `npm test`
Expected: PASS — the four new tests green, all Plan 1 suites still green
(the truncate-list change is the only touch they feel).

- [ ] **Step 6: Commit**

```bash
git add infra/a0/schema.sql infra/a0/board-service/test/helpers.js infra/a0/board-service/test/schema-extension.test.js
git commit -m "feat(a0): plan-2 schema — board_flag, run_usage, slack_outbox"
```

---

### Task 2: Dispatch-pause flag + admission caps inside the claim transaction

**Files:**
- Create: `infra/a0/board-service/src/flags.js`,
  `infra/a0/board-service/test/admission.test.js`
- Modify: `infra/a0/board-service/src/claims.js`

**Interfaces:**
- Consumes: `withTx` (Plan 1 Task 2), `mintToken` (Plan 1 Task 4),
  `board_flag` (Task 1).
- Produces: `getFlag(q, key)` → jsonb value | null and
  `setFlag(q, {key, value})` → `{ok:true}` where `q` is a Pool OR a client
  (anything with `.query` — breakers need them inside a transaction).
- **CONTRACT CHANGE (Plan 3's dispatcher consumes this — exact shape):**
  `claimNext(pool, {leaseMinutes=10, maxConcurrency, maxStartsPerMin})` now
  returns one of:
  - `null` — queue empty, try later;
  - `{refused: 'paused', reason}` — `dispatch_paused` flag is set;
  - `{refused: 'concurrency-cap'}` — live runs (`ended_at is null`) ≥
    `A0_MAX_CONCURRENCY` (default 200);
  - `{refused: 'start-rate-cap'}` — runs started in the last 60s ≥
    `A0_MAX_STARTS_PER_MIN` (default 30);
  - `{runId, ticketId, fence, token}` — a claim (unchanged from Plan 1).
  Checks run in that order, inside the claim transaction, before the pick.
  Counts are read-committed: concurrent in-flight claims can overshoot a
  cap by at most the caller's own parallelism — acceptable because the spec
  treats these as circuit-breaker levers, not hard invariants (spec §2).

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/admission.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';
import { claimNext } from '../src/claims.js';
import { getFlag, setFlag } from '../src/flags.js';

test('flag round-trip upsert', async () => {
  const pool = await testPool();
  assert.equal(await getFlag(pool, 'dispatch_paused'), null);
  await setFlag(pool, { key: 'dispatch_paused',
                        value: { paused: true, reason: 'storm' } });
  assert.deepEqual(await getFlag(pool, 'dispatch_paused'),
    { paused: true, reason: 'storm' });
  await setFlag(pool, { key: 'dispatch_paused',
                        value: { paused: false, reason: '' } });
  assert.deepEqual(await getFlag(pool, 'dispatch_paused'),
    { paused: false, reason: '' });
  await pool.end();
});

test('paused flag refuses claims and carries the reason', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  await setFlag(pool, { key: 'dispatch_paused',
                        value: { paused: true, reason: 'spend-runaway' } });
  assert.deepEqual(await claimNext(pool, {}),
    { refused: 'paused', reason: 'spend-runaway' });
  const { rowCount } = await pool.query('select 1 from run');
  assert.equal(rowCount, 0, 'refusal must not create a run');
  await pool.end();
});

test('paused:false flag does not refuse', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  await setFlag(pool, { key: 'dispatch_paused',
                        value: { paused: false, reason: '' } });
  const c = await claimNext(pool, {});
  assert.equal(c.ticketId, 't1');
  await pool.end();
});

test('concurrency cap: live runs at the cap refuse the next claim', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values
    ('t1','ready-for-agent'), ('t2','ready-for-agent')`);
  const first = await claimNext(pool, {});
  assert.ok(first.runId);
  assert.deepEqual(await claimNext(pool, { maxConcurrency: 1 }),
    { refused: 'concurrency-cap' });
  await pool.end();
});

test('start-rate cap: starts inside the 60s window refuse; old starts do not', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values
    ('t1','ready-for-agent'), ('t2','ready-for-agent')`);
  await claimNext(pool, {});
  assert.deepEqual(await claimNext(pool, { maxStartsPerMin: 1 }),
    { refused: 'start-rate-cap' });
  await pool.query(`update run set started_at = now() - interval '2 minutes'`);
  const c = await claimNext(pool, { maxStartsPerMin: 1 });
  assert.equal(c.ticketId, 't2');
  await pool.end();
});

test('empty queue is still null, not a refusal', async () => {
  const pool = await testPool();
  assert.equal(await claimNext(pool, {}), null);
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/flags.js'`.

- [ ] **Step 3: Implement flags.js and the new claims.js**

```js
// infra/a0/board-service/src/flags.js
// q is a pg Pool OR a checked-out client — both expose .query, and the
// breakers need to write the flag inside the same transaction as the
// outbox row.
export async function getFlag(q, key) {
  const { rows } = await q.query(
    `select value from board_flag where key = $1`, [key]);
  return rows[0]?.value ?? null;
}

export async function setFlag(q, { key, value }) {
  await q.query(
    `insert into board_flag (key, value) values ($1, $2)
     on conflict (key) do update set value = $2, updated_at = now()`,
    [key, value]);
  return { ok: true };
}
```

Full new content of `infra/a0/board-service/src/claims.js` (replaces the
Plan 1 version; the pick/update/insert tail is unchanged):

```js
// infra/a0/board-service/src/claims.js
import { randomUUID } from 'node:crypto';
import { withTx } from './db.js';
import { mintToken } from './auth.js';

// Return contract (consumed by Plan 3's dispatcher — do not change shape):
//   null                              — queue empty, try later
//   { refused: 'paused', reason }     — dispatch_paused flag is set
//   { refused: 'concurrency-cap' }    — live runs ≥ A0_MAX_CONCURRENCY
//   { refused: 'start-rate-cap' }     — starts in last 60s ≥ A0_MAX_STARTS_PER_MIN
//   { runId, ticketId, fence, token } — a claim
// Admission counts are read inside the claim transaction (read committed):
// concurrent in-flight claims can overshoot a cap by at most the caller's
// own parallelism — fine for what the spec treats as circuit-breaker
// levers, not hard invariants (spec §2).
export async function claimNext(pool, {
  leaseMinutes = 10,
  maxConcurrency = Number(process.env.A0_MAX_CONCURRENCY ?? 200),
  maxStartsPerMin = Number(process.env.A0_MAX_STARTS_PER_MIN ?? 30),
} = {}) {
  return withTx(pool, async (client) => {
    const flag = await client.query(
      `select value from board_flag where key = 'dispatch_paused'`);
    if (flag.rows[0]?.value?.paused === true)
      return { refused: 'paused', reason: flag.rows[0].value.reason ?? '' };
    const live = await client.query(
      `select count(*)::int as n from run where ended_at is null`);
    if (live.rows[0].n >= maxConcurrency)
      return { refused: 'concurrency-cap' };
    const recent = await client.query(
      `select count(*)::int as n from run
       where started_at > now() - interval '60 seconds'`);
    if (recent.rows[0].n >= maxStartsPerMin)
      return { refused: 'start-rate-cap' };

    const pick = await client.query(
      `select id, fence from ticket where state = 'ready-for-agent'
       order by updated_at for update skip locked limit 1`);
    if (pick.rowCount === 0) return null;
    const t = pick.rows[0];
    const runId = randomUUID();
    const { token, tokenHash } = mintToken();
    const fence = Number(t.fence) + 1;
    await client.query(
      `update ticket set state='in-progress', owner_run=$1, fence=$2,
         park_note=null, updated_at=now() where id=$3`,
      [runId, fence, t.id]);
    await client.query(
      `insert into run (id, ticket_id, fence, token_hash, lease_expires_at)
       values ($1, $2, $3, $4, now() + make_interval(mins => $5))`,
      [runId, t.id, fence, tokenHash, leaseMinutes]);
    return { runId, ticketId: t.id, fence, token };
  });
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all admission tests green; Plan 1's `claims.test.js` still
green (no flag set + tiny counts ⇒ old behavior unchanged).

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/flags.js infra/a0/board-service/src/claims.js infra/a0/board-service/test/admission.test.js
git commit -m "feat(a0): dispatch-pause flag + admission caps inside the claim transaction"
```

---

### Task 3: HTTP controls — /flags, claim refusal mapping, per-run usage upsert

**Files:**
- Create: `infra/a0/board-service/test/server-controls.test.js`
- Modify: `infra/a0/board-service/src/server.js`

**Interfaces:**
- Consumes: `setFlag` (Task 2), `claimNext` new contract (Task 2),
  `verifyRunToken`/`verifyAdmin` (Plan 1 Task 4), `run_usage` (Task 1).
- Produces (cross-plan contract):
  - `POST /flags` (admin) `{key, value}` → 200 `{ok:true}` (upsert; the
    unpause is `{key:'dispatch_paused', value:{paused:false, reason:''}}`);
    400 if key or value missing; 401 non-admin.
  - `POST /claims` mapping: claim → 200; `null` → 204;
    `{refused:'paused'}` → **423** `{error:'dispatch-paused', reason}`;
    `{refused:'concurrency-cap'|'start-rate-cap'}` → **429** `{error:<refusal>}`.
  - `POST /runs/:id/usage` (run bearer token, same auth pattern as
    `/events`) → 200 `{ok:true}`; upserts the `run_usage` row keyed on
    `run_id`. Body keys are snake_case, matching the Anthropic API usage
    field names so workers can pass usage through verbatim:
    `{model, input_tokens, output_tokens, cache_read_tokens,
    cache_write_tokens, cost_usd}`; `model` required (400 if missing),
    token fields default 0. Because `verifyRunToken` requires the run to be
    live, usage must be posted before the run ends — Plan 3's worker
    protocol posts usage as its last act before the final transition.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/server-controls.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';
import { makeServer } from '../src/server.js';

process.env.A0_ADMIN_KEY = 'test-admin';
const admin = { 'authorization': 'Bearer test-admin',
                'content-type': 'application/json' };

async function start(pool) {
  const server = makeServer(pool);
  await new Promise(r => server.listen(0, r));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { server, base };
}
const j = (r) => r.json();

async function readyTicket(base, id) {
  await fetch(`${base}/tickets`, { method: 'POST', headers: admin,
    body: JSON.stringify({ id }) });
  await fetch(`${base}/tickets/${id}/transition`, { method: 'POST',
    headers: admin,
    body: JSON.stringify({ from: 'backlog', to: 'ready-for-agent' }) });
}

test('pause via /flags → claims 423; single flag-flip unpause → claims flow', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  await readyTicket(base, 't1');

  let r = await fetch(`${base}/flags`, { method: 'POST', headers: admin,
    body: JSON.stringify({ key: 'dispatch_paused',
                           value: { paused: true, reason: 'storm' } }) });
  assert.equal(r.status, 200);

  r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
  assert.equal(r.status, 423);
  assert.deepEqual(await j(r), { error: 'dispatch-paused', reason: 'storm' });

  r = await fetch(`${base}/flags`, { method: 'POST', headers: admin,
    body: JSON.stringify({ key: 'dispatch_paused',
                           value: { paused: false, reason: '' } }) });
  assert.equal(r.status, 200);

  r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
  assert.equal(r.status, 200);
  assert.equal((await j(r)).ticketId, 't1');
  server.close(); await pool.end();
});

test('cap refusals map to 429 with the refusal name', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  await readyTicket(base, 't1');
  await readyTicket(base, 't2');
  process.env.A0_MAX_CONCURRENCY = '1';
  try {
    let r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
    assert.equal(r.status, 200);
    r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
    assert.equal(r.status, 429);
    assert.deepEqual(await j(r), { error: 'concurrency-cap' });
  } finally {
    delete process.env.A0_MAX_CONCURRENCY;
  }
  server.close(); await pool.end();
});

test('/flags requires admin; bad body is 400', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  let r = await fetch(`${base}/flags`, { method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ key: 'x', value: {} }) });
  assert.equal(r.status, 401);
  r = await fetch(`${base}/flags`, { method: 'POST', headers: admin,
    body: JSON.stringify({ key: 'x' }) });
  assert.equal(r.status, 400);
  server.close(); await pool.end();
});

test('run posts usage; upsert replaces; wrong token 401; missing model 400', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  await readyTicket(base, 't1');
  const claim = await j(await fetch(`${base}/claims`,
    { method: 'POST', headers: admin }));
  const runAuth = { 'authorization': `Bearer ${claim.token}`,
                    'content-type': 'application/json' };

  let r = await fetch(`${base}/runs/${claim.runId}/usage`, { method: 'POST',
    headers: runAuth,
    body: JSON.stringify({ model: 'claude-sonnet-4-6', input_tokens: 1000,
      output_tokens: 200, cache_read_tokens: 50000, cache_write_tokens: 1500,
      cost_usd: 0.42 }) });
  assert.equal(r.status, 200);

  r = await fetch(`${base}/runs/${claim.runId}/usage`, { method: 'POST',
    headers: runAuth,
    body: JSON.stringify({ model: 'claude-sonnet-4-6', input_tokens: 1200,
      output_tokens: 300, cache_read_tokens: 61000, cache_write_tokens: 1500,
      cost_usd: 0.55 }) });
  assert.equal(r.status, 200);
  const { rows } = await pool.query(
    `select model, input_tokens::int as inp, cost_usd::float as usd
     from run_usage where run_id = $1`, [claim.runId]);
  assert.equal(rows.length, 1, 'upsert must keep one row per run');
  assert.deepEqual(rows[0],
    { model: 'claude-sonnet-4-6', inp: 1200, usd: 0.55 });

  r = await fetch(`${base}/runs/${claim.runId}/usage`, { method: 'POST',
    headers: { 'authorization': 'Bearer wrong',
               'content-type': 'application/json' },
    body: JSON.stringify({ model: 'm' }) });
  assert.equal(r.status, 401);

  r = await fetch(`${base}/runs/${claim.runId}/usage`, { method: 'POST',
    headers: runAuth, body: JSON.stringify({ input_tokens: 5 }) });
  assert.equal(r.status, 400);
  assert.deepEqual(await j(r), { error: 'model-required' });
  server.close(); await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `/flags` and `/runs/:id/usage` return 404 (the pause test
dies asserting 200 on its first `POST /flags`). Were the flag set by hand,
the unmodified `/claims` route would also mis-serve the refusal object as
a 200 claim — the mapping in Step 3 fixes both.

- [ ] **Step 3: Modify server.js**

Three edits, exact code:

(a) Extend the imports at the top of `src/server.js` — replace

```js
import { verifyAdmin, verifyRunToken } from './auth.js';
```

with

```js
import { verifyAdmin, verifyRunToken } from './auth.js';
import { setFlag } from './flags.js';
```

(b) Replace the whole `// POST /claims` block

```js
      // POST /claims
      if (req.method === 'POST' && p.length === 1 && p[0] === 'claims') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        const c = await claimNext(pool, {});
        return c ? send(res, 200, c) : send(res, 204);
      }
```

with

```js
      // POST /claims — 200 claim | 204 empty queue | 423 paused | 429 capped
      if (req.method === 'POST' && p.length === 1 && p[0] === 'claims') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        const c = await claimNext(pool, {});
        if (c === null) return send(res, 204);
        if (c.refused === 'paused')
          return send(res, 423, { error: 'dispatch-paused', reason: c.reason });
        if (c.refused) return send(res, 429, { error: c.refused });
        return send(res, 200, c);
      }
```

(c) Insert two new route blocks directly after the `// POST /runs/:id/events`
block (after its closing `}`):

```js
      // POST /runs/:id/usage — run bearer; upsert the run's usage row.
      // Body keys mirror Anthropic API usage fields (snake_case) so the
      // worker passes usage through verbatim. Must be posted while the run
      // is live (verifyRunToken requires ended_at is null).
      if (req.method === 'POST' && p.length === 3 && p[0] === 'runs'
          && p[2] === 'usage') {
        if (!(await verifyRunToken(pool, p[1], bearer(req))))
          return send(res, 401, { error: 'unauthorized' });
        const b = await body(req);
        if (!b.model) return send(res, 400, { error: 'model-required' });
        await pool.query(
          `insert into run_usage (run_id, model, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, cost_usd)
           values ($1, $2, $3, $4, $5, $6, $7)
           on conflict (run_id) do update set
             model = excluded.model,
             input_tokens = excluded.input_tokens,
             output_tokens = excluded.output_tokens,
             cache_read_tokens = excluded.cache_read_tokens,
             cache_write_tokens = excluded.cache_write_tokens,
             cost_usd = excluded.cost_usd,
             recorded_at = now()`,
          [p[1], b.model, b.input_tokens ?? 0, b.output_tokens ?? 0,
           b.cache_read_tokens ?? 0, b.cache_write_tokens ?? 0,
           b.cost_usd ?? 0]);
        return send(res, 200, { ok: true });
      }

      // POST /flags (admin) — {key, value} upsert. The dispatch-pause flag
      // is key 'dispatch_paused', value {paused: bool, reason: text};
      // unpausing is a single flip to {paused:false, reason:''}.
      if (req.method === 'POST' && p.length === 1 && p[0] === 'flags') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        const b = await body(req);
        if (!b.key || b.value === undefined)
          return send(res, 400, { error: 'key-and-value-required' });
        return send(res, 200, await setFlag(pool, { key: b.key, value: b.value }));
      }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all four control tests green; Plan 1's `server.test.js`
still green (the 204/200 paths are byte-identical for an unpaused board).

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/server.js infra/a0/board-service/test/server-controls.test.js
git commit -m "feat(a0): HTTP controls — /flags, claim refusal mapping 423/429, per-run usage upsert"
```

---

### Task 4: Cost meter — meterReport + CLI (acceptance drill 8)

**Files:**
- Create: `infra/a0/board-service/src/meter.js`,
  `infra/a0/board-service/test/meter.test.js`

**Interfaces:**
- Consumes: `run_usage` + `run` (ticket grouping), `makePool`/`applySchema`
  for the CLI. Format precedent: Plan 1's T1 spike
  `infra/a0/tools/measure-runs.mjs` (same cache-ratio denominator:
  `input + cache_read + cache_write`).
- Produces: `meterReport(pool, {sinceDays=30, cacheRatioFloor, infraUsd})` →
  `{runs, totalCostUsd, perRun, perTicket, cacheReadRatio, flagged,
  infraUsd, tokenInfraRatio}` where `perRun`/`perTicket` are averages over
  the window, `cacheReadRatio` is fleet-wide, `flagged` is the array of
  run ids whose PER-RUN cache-read ratio < `cacheRatioFloor` (env
  `A0_CACHE_RATIO_FLOOR`, default 0.5), and `infraUsd` (env
  `A0_MONTHLY_INFRA_USD`, default 0) / `tokenInfraRatio`
  (`totalCostUsd / infraUsd`, null when infra is 0) carry the spec's
  infra:token split. CLI: `node src/meter.js` prints the report JSON
  (needs `DATABASE_URL`).

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/meter.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { testPool, TEST_URL } from './helpers.js';
import { claimNext } from '../src/claims.js';
import { meterReport } from '../src/meter.js';

// Two real claimed runs on two tickets: one cache-disciplined, one
// deliberately cache-broken canary (zero cache reads, all input fresh).
async function seedUsage(pool) {
  await pool.query(`insert into ticket (id, state) values
    ('t-normal','ready-for-agent'), ('t-canary','ready-for-agent')`);
  const c1 = await claimNext(pool, {});
  const c2 = await claimNext(pool, {});
  const byTicket = Object.fromEntries([c1, c2].map(c => [c.ticketId, c]));
  const normal = byTicket['t-normal'].runId;
  const canary = byTicket['t-canary'].runId;
  await pool.query(
    `insert into run_usage (run_id, model, input_tokens, output_tokens,
       cache_read_tokens, cache_write_tokens, cost_usd)
     values ($1, 'claude-sonnet-4-6', 1000, 2000, 40000, 2000, 0.5)`,
    [normal]);
  await pool.query(
    `insert into run_usage (run_id, model, input_tokens, output_tokens,
       cache_read_tokens, cache_write_tokens, cost_usd)
     values ($1, 'claude-sonnet-4-6', 30000, 2000, 0, 500, 2.1)`,
    [canary]);
  return { normal, canary };
}

test('drill 8: $/run, $/ticket, cache ratio; the cache-broken canary is flagged', async () => {
  const pool = await testPool();
  const { normal, canary } = await seedUsage(pool);
  const rep = await meterReport(pool, { sinceDays: 30, infraUsd: 3300 });
  assert.equal(rep.runs, 2);
  assert.equal(rep.totalCostUsd, 2.6);
  assert.equal(rep.perRun, 1.3);
  assert.equal(rep.perTicket, 1.3);
  // fleet ratio: 40000 / (31000 + 40000 + 2500) = 0.544
  assert.equal(rep.cacheReadRatio, 0.544);
  assert.deepEqual(rep.flagged, [canary],
    'only the cache-broken canary is flagged');
  assert.ok(!rep.flagged.includes(normal));
  assert.equal(rep.infraUsd, 3300);
  assert.equal(typeof rep.tokenInfraRatio, 'number');
  await pool.end();
});

test('window: usage recorded outside sinceDays is excluded', async () => {
  const pool = await testPool();
  const { canary } = await seedUsage(pool);
  await pool.query(`update run_usage set recorded_at = now() - interval '40 days'
                    where run_id = $1`, [canary]);
  const rep = await meterReport(pool, { sinceDays: 30 });
  assert.equal(rep.runs, 1);
  assert.equal(rep.totalCostUsd, 0.5);
  assert.deepEqual(rep.flagged, []);
  await pool.end();
});

test('empty window: zeros and null ratio, never NaN', async () => {
  const pool = await testPool();
  const rep = await meterReport(pool, {});
  assert.deepEqual(rep, { runs: 0, totalCostUsd: 0, perRun: 0, perTicket: 0,
    cacheReadRatio: 0, flagged: [], infraUsd: 0, tokenInfraRatio: null });
  await pool.end();
});

test('CLI prints the report JSON', async () => {
  const pool = await testPool();
  await seedUsage(pool);
  await pool.end();
  const cwd = fileURLToPath(new URL('..', import.meta.url));
  const { stdout } = await promisify(execFile)(
    process.execPath, ['src/meter.js'],
    { cwd, env: { ...process.env, DATABASE_URL: TEST_URL } });
  const rep = JSON.parse(stdout);
  assert.equal(rep.runs, 2);
  assert.equal(rep.flagged.length, 1);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/meter.js'`.

- [ ] **Step 3: Implement meter.js**

```js
// infra/a0/board-service/src/meter.js
// The cost meter (spec §8): SQL over run_usage (join run for ticket
// grouping). Per-run cache-read ratio uses the same denominator as the T1
// spike (tools/measure-runs.mjs): cache_read / (input + cache_read +
// cache_write). Runs below the floor are the "cache-broken canary" signal
// — a fleet-wide cache regression is a five-figure monthly event that
// looks like nothing else (spec §10 lever 2).
import { makePool, applySchema } from './db.js';

export async function meterReport(pool, {
  sinceDays = 30,
  cacheRatioFloor = Number(process.env.A0_CACHE_RATIO_FLOOR ?? 0.5),
  infraUsd = Number(process.env.A0_MONTHLY_INFRA_USD ?? 0),
} = {}) {
  const { rows } = await pool.query(
    `select u.run_id, r.ticket_id, u.cost_usd::float as cost,
            u.input_tokens::float as inp, u.cache_read_tokens::float as cr,
            u.cache_write_tokens::float as cw
     from run_usage u join run r on r.id = u.run_id
     where u.recorded_at > now() - make_interval(days => $1)
     order by u.run_id`, [sinceDays]);
  const runs = rows.length;
  const totalCostUsd = +rows.reduce((a, x) => a + x.cost, 0).toFixed(4);
  const tickets = new Set(rows.map(x => x.ticket_id)).size;
  const ratio = (x) => { const d = x.inp + x.cr + x.cw; return d ? x.cr / d : 0; };
  const denomAll = rows.reduce((a, x) => a + x.inp + x.cr + x.cw, 0);
  const crAll = rows.reduce((a, x) => a + x.cr, 0);
  return {
    runs,
    totalCostUsd,
    perRun: runs ? +(totalCostUsd / runs).toFixed(4) : 0,
    perTicket: tickets ? +(totalCostUsd / tickets).toFixed(4) : 0,
    cacheReadRatio: denomAll ? +(crAll / denomAll).toFixed(3) : 0,
    flagged: rows.filter(x => ratio(x) < cacheRatioFloor).map(x => x.run_id),
    infraUsd,
    tokenInfraRatio: infraUsd ? +(totalCostUsd / infraUsd).toFixed(3) : null,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const pool = makePool(process.env.DATABASE_URL);
  await applySchema(pool);
  console.log(JSON.stringify(await meterReport(pool), null, 2));
  await pool.end();
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all four meter tests green. Note the drill-8 arithmetic is
asserted exactly (2.6 / 1.3 / 1.3 / 0.544), so a formula drift fails loudly.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/meter.js infra/a0/board-service/test/meter.test.js
git commit -m "feat(a0): cost meter — \$/run, \$/ticket, cache-read ratio, canary flagging"
```

---

### Task 5: Over-budget kill — runaway runs end and park needs-human

**Files:**
- Create: `infra/a0/board-service/test/overbudget.test.js`
- Modify: `infra/a0/board-service/src/reconcile.js`

**Interfaces:**
- Consumes: `run`/`ticket` tables; `claimNext` and `transition` in tests.
- Produces: `killOverBudget(pool, {maxRunMinutes})` → number of tickets
  parked (env `A0_MAX_RUN_MINUTES`, default 45). Semantics (spec §9 failure
  class 1, "runaway run"): every LIVE run older than the wall-clock budget
  is ended with `end_reason='over-budget'`, and its ticket moves
  `in-progress → needs-human` with a park note citing the budget and the
  run id (the transcript pointer — the session log is keyed by run id).
  Same one-statement conditional-UPDATE shape as Plan 1's `reclaimStale`.
- Semantic note (tick ordering, Task 8): a run that stopped heartbeating
  is reclaimed by `reclaimStale` FIRST (lease expired ⇒ dead run,
  self-heals to `ready-for-agent`). `killOverBudget` therefore only ever
  reaches runs that are still heartbeating but running too long — exactly
  the "alive and chewing tokens" class that must park for a human, not
  silently retry.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/overbudget.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';
import { claimNext } from '../src/claims.js';
import { killOverBudget } from '../src/reconcile.js';
import { transition } from '../src/transitions.js';
import { withTx } from '../src/db.js';

test('a heartbeating run past the wall-clock budget is killed and parked', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const c = await claimNext(pool, {});
  // 60 minutes old but still heartbeating (fresh lease) — the runaway
  // class; reclaimStale would NOT touch this run.
  await pool.query(
    `update run set started_at = now() - interval '60 minutes',
                    lease_expires_at = now() + interval '5 minutes'
     where id = $1`, [c.runId]);
  assert.equal(await killOverBudget(pool, { maxRunMinutes: 45 }), 1);
  const r = (await pool.query(
    `select ended_at, end_reason from run where id = $1`, [c.runId])).rows[0];
  assert.equal(r.end_reason, 'over-budget');
  assert.ok(r.ended_at);
  const t = (await pool.query(
    `select state, owner_run, park_note from ticket where id='t1'`)).rows[0];
  assert.equal(t.state, 'needs-human');
  assert.equal(t.owner_run, null);
  assert.match(t.park_note, new RegExp(c.runId), 'note cites the run id');
  assert.match(t.park_note, /45/, 'note cites the budget');
  await pool.end();
});

test('the park is resumable: needs-human → ready-for-agent → fresh claim, fence bumped', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const old = await claimNext(pool, {});
  await pool.query(
    `update run set started_at = now() - interval '60 minutes',
                    lease_expires_at = now() + interval '5 minutes'
     where id = $1`, [old.runId]);
  await killOverBudget(pool, { maxRunMinutes: 45 });
  const ok = await withTx(pool, cl => transition(cl, {
    ticketId: 't1', from: 'needs-human', to: 'ready-for-agent' }));
  assert.equal(ok.ok, true);
  const fresh = await claimNext(pool, {});
  assert.equal(fresh.ticketId, 't1');
  assert.equal(fresh.fence, old.fence + 1, 'zombie is fenced out');
  await pool.end();
});

test('healthy in-budget runs are untouched', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  await claimNext(pool, {});
  assert.equal(await killOverBudget(pool, { maxRunMinutes: 45 }), 0);
  const { rows } = await pool.query(`select state from ticket where id='t1'`);
  assert.equal(rows[0].state, 'in-progress');
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `killOverBudget` is not exported from `../src/reconcile.js`.

- [ ] **Step 3: Implement — append to reconcile.js**

Append to `infra/a0/board-service/src/reconcile.js` (below `reclaimStale`,
which is unchanged):

```js
// Spec §9 failure class 1 (runaway run): live runs past the wall-clock
// budget are ended and their tickets park needs-human with a transcript
// pointer (the run id keys the session log). Runs that stopped
// heartbeating never reach here — reclaimStale (run first in the tick)
// already reclaimed them as dead runs. Same conditional-UPDATE shape as
// reclaimStale: idempotent, restart-safe.
export async function killOverBudget(pool, {
  maxRunMinutes = Number(process.env.A0_MAX_RUN_MINUTES ?? 45),
} = {}) {
  const res = await pool.query(
    `with dead as (
       update run set ended_at = now(), end_reason = 'over-budget'
       where ended_at is null
         and started_at < now() - make_interval(mins => $1)
       returning id, ticket_id)
     update ticket t
       set state = 'needs-human', owner_run = null,
           park_note = 'over-budget: run ' || d.id || ' exceeded ' ||
                       $1::text || ' min wall-clock budget; transcript: ' ||
                       'session_event rows for run_id=' || d.id,
           updated_at = now()
     from dead d
     where t.id = d.ticket_id and t.owner_run = d.id and t.state = 'in-progress'
     returning t.id`);
  return res.rowCount;
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all three over-budget tests green; Plan 1's
`reconcile.test.js` still green.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/reconcile.js infra/a0/board-service/test/overbudget.test.js
git commit -m "feat(a0): over-budget kill — runaway runs end and park needs-human"
```

---

### Task 6: Circuit breakers — storm / spend / failure-ratio trip to paused + outbox

**Files:**
- Create: `infra/a0/board-service/src/breakers.js`,
  `infra/a0/board-service/test/breakers.test.js`

**Interfaces:**
- Consumes: `getFlag`/`setFlag` (Task 2 — client-capable), `withTx`
  (flag + outbox row commit in one transaction, the same-transaction
  property applied to the breaker itself), `run`/`run_usage`/`slack_outbox`.
- Produces: `evaluateBreakers(pool, {maxStartsPerMin, dailySpendCapUsd})` →
  `{tripped: [names], alreadyPaused: bool}`. The three breakers (spec §9):
  - `start-storm` — runs started in the last minute > `A0_MAX_STARTS_PER_MIN`
    (default 30); severity `next-block`.
  - `spend-runaway` — `sum(run_usage.cost_usd)` recorded today (UTC day) >
    `A0_DAILY_SPEND_CAP_USD` (default 2000); severity `today`.
  - `failure-ratio` — of runs ended in the last 15 minutes, ≥5 total AND
    >50% with `end_reason` not in `('completed')`; severity `next-block`.
  On any trip: set `dispatch_paused` to
  `{paused:true, reason:'<name>: <detail>; …'}` and insert EXACTLY ONE
  `slack_outbox` row (all tripped breakers in one message, severity = the
  highest tripped). When already paused, evaluation returns immediately
  with `{tripped: [], alreadyPaused: true}` and writes nothing — the
  no-repeat guarantee behind acceptance item 6's "posts one Slack message".
  (`end_reason='completed'` is written by Plan 3's dispatcher at normal run
  end; this plan only reads it, and seeds it directly in tests.)

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/breakers.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool, seedRuns } from './helpers.js';
import { evaluateBreakers } from '../src/breakers.js';
import { getFlag } from '../src/flags.js';

async function outboxRows(pool) {
  return (await pool.query(
    `select severity, message from slack_outbox order by id`)).rows;
}

test('quiet board: nothing trips, no flag, no outbox row', async () => {
  const pool = await testPool();
  const out = await evaluateBreakers(pool, {});
  assert.deepEqual(out, { tripped: [], alreadyPaused: false });
  assert.equal(await getFlag(pool, 'dispatch_paused'), null);
  assert.deepEqual(await outboxRows(pool), []);
  await pool.end();
});

test('start storm trips: pause flag + one next-block message', async () => {
  const pool = await testPool();
  // 31 starts in the last minute, all ended cleanly (so ONLY the storm
  // breaker trips: failed=0 keeps failure-ratio quiet).
  await seedRuns(pool, 31, { startedMinutesAgo: 0, endedMinutesAgo: 0,
                             endReason: 'completed' });
  const out = await evaluateBreakers(pool, { maxStartsPerMin: 30 });
  assert.deepEqual(out.tripped, ['start-storm']);
  const flag = await getFlag(pool, 'dispatch_paused');
  assert.equal(flag.paused, true);
  assert.match(flag.reason, /start-storm/);
  const rows = await outboxRows(pool);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].severity, 'next-block');
  assert.match(rows[0].message, /start-storm/);
  await pool.end();
});

test('daily spend over the cap trips at severity today', async () => {
  const pool = await testPool();
  await seedRuns(pool, 1, { startedMinutesAgo: 30, endedMinutesAgo: 20,
                            endReason: 'completed' });
  const { rows } = await pool.query(`select id from run limit 1`);
  await pool.query(
    `insert into run_usage (run_id, model, cost_usd)
     values ($1, 'claude-sonnet-4-6', 2500)`, [rows[0].id]);
  const out = await evaluateBreakers(pool, {});
  assert.deepEqual(out.tripped, ['spend-runaway']);
  const [row] = await outboxRows(pool);
  assert.equal(row.severity, 'today');
  await pool.end();
});

test('failure ratio trips at >50% failed with ≥5 ended runs', async () => {
  const pool = await testPool();
  await seedRuns(pool, 4, { startedMinutesAgo: 20, endedMinutesAgo: 5,
                            endReason: 'lease-expired' });
  await seedRuns(pool, 2, { startedMinutesAgo: 20, endedMinutesAgo: 5,
                            endReason: 'completed' });
  const out = await evaluateBreakers(pool, {});
  assert.deepEqual(out.tripped, ['failure-ratio']);
  await pool.end();
});

test('failure ratio needs at least 5 ended runs', async () => {
  const pool = await testPool();
  await seedRuns(pool, 4, { startedMinutesAgo: 20, endedMinutesAgo: 5,
                            endReason: 'over-budget' });
  const out = await evaluateBreakers(pool, {});
  assert.deepEqual(out.tripped, []);
  await pool.end();
});

test('simultaneous trips: one message at the highest severity', async () => {
  const pool = await testPool();
  // storm + failure-ratio (31 fresh failed runs) + spend in one board state
  await seedRuns(pool, 31, { startedMinutesAgo: 0, endedMinutesAgo: 0,
                             endReason: 'lease-expired' });
  const { rows } = await pool.query(`select id from run limit 1`);
  await pool.query(
    `insert into run_usage (run_id, model, cost_usd)
     values ($1, 'claude-sonnet-4-6', 9999)`, [rows[0].id]);
  const out = await evaluateBreakers(pool, {});
  assert.deepEqual(out.tripped,
    ['start-storm', 'spend-runaway', 'failure-ratio']);
  const rows2 = await outboxRows(pool);
  assert.equal(rows2.length, 1, 'one trip = one message');
  assert.equal(rows2[0].severity, 'today');
  await pool.end();
});

test('already paused: evaluation is a no-op, no duplicate message', async () => {
  const pool = await testPool();
  await seedRuns(pool, 31, { startedMinutesAgo: 0, endedMinutesAgo: 0,
                             endReason: 'completed' });
  await evaluateBreakers(pool, {});
  const again = await evaluateBreakers(pool, {});
  assert.deepEqual(again, { tripped: [], alreadyPaused: true });
  assert.equal((await outboxRows(pool)).length, 1);
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/breakers.js'`.

- [ ] **Step 3: Implement breakers.js**

```js
// infra/a0/board-service/src/breakers.js
// Spec §9 breakers, evaluated once per reconciler tick. Governing rule:
// bounded things fail into paused + Slack + parked — so a trip writes the
// dispatch_paused flag and ONE slack_outbox row in one transaction, and a
// paused board short-circuits evaluation (no repeat messages; unpausing is
// the human's single flag-flip via POST /flags).
import { withTx } from './db.js';
import { getFlag, setFlag } from './flags.js';

const SEVERITY_RANK = { 'fyi': 0, 'next-block': 1, 'today': 2 };

export async function evaluateBreakers(pool, {
  maxStartsPerMin = Number(process.env.A0_MAX_STARTS_PER_MIN ?? 30),
  dailySpendCapUsd = Number(process.env.A0_DAILY_SPEND_CAP_USD ?? 2000),
} = {}) {
  const flag = await getFlag(pool, 'dispatch_paused');
  if (flag?.paused === true) return { tripped: [], alreadyPaused: true };

  const tripped = [];

  const starts = await pool.query(
    `select count(*)::int as n from run
     where started_at > now() - interval '60 seconds'`);
  if (starts.rows[0].n > maxStartsPerMin)
    tripped.push({ name: 'start-storm', severity: 'next-block',
      detail: `${starts.rows[0].n} starts in the last minute (cap ${maxStartsPerMin}/min)` });

  const spend = await pool.query(
    `select coalesce(sum(cost_usd), 0)::float as usd from run_usage
     where recorded_at >= date_trunc('day', now())`);
  if (spend.rows[0].usd > dailySpendCapUsd)
    tripped.push({ name: 'spend-runaway', severity: 'today',
      detail: `$${spend.rows[0].usd.toFixed(2)} recorded today (cap $${dailySpendCapUsd})` });

  const fails = await pool.query(
    `select count(*)::int as total,
            (count(*) filter (where end_reason is distinct from 'completed'))::int as failed
     from run where ended_at > now() - interval '15 minutes'`);
  const f = fails.rows[0];
  if (f.total >= 5 && f.failed / f.total > 0.5)
    tripped.push({ name: 'failure-ratio', severity: 'next-block',
      detail: `${f.failed}/${f.total} runs failed in the last 15 min` });

  if (tripped.length === 0) return { tripped: [], alreadyPaused: false };

  const reason = tripped.map(t => `${t.name}: ${t.detail}`).join('; ');
  const severity = tripped.reduce(
    (top, t) => SEVERITY_RANK[t.severity] > SEVERITY_RANK[top] ? t.severity : top,
    'fyi');
  await withTx(pool, async (client) => {
    await setFlag(client, { key: 'dispatch_paused',
                            value: { paused: true, reason } });
    await client.query(
      `insert into slack_outbox (severity, message) values ($1, $2)`,
      [severity,
       `Dispatch PAUSED — ${reason}. Unpause: POST /flags ` +
       `{"key":"dispatch_paused","value":{"paused":false,"reason":""}}`]);
  });
  return { tripped: tripped.map(t => t.name), alreadyPaused: false };
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all seven breaker tests green.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/breakers.js infra/a0/board-service/test/breakers.test.js
git commit -m "feat(a0): circuit breakers — storm/spend/failure-ratio trip to paused + one outbox row"
```

---

### Task 7: Slack outbox drain — deliver-then-mark against a fake webhook

**Files:**
- Create: `infra/a0/board-service/src/slack.js`,
  `infra/a0/board-service/test/slack.test.js`

**Interfaces:**
- Consumes: `slack_outbox` (Task 1); global `fetch` (Node 22).
- Produces: `drainOutbox(pool, {webhookUrl})` → `{sent, remaining}`.
  Semantics (spec §9 / cross-plan contract): POST each unsent row (id
  order) to the webhook as `{text: message}`; mark `sent_at` only after
  the webhook accepts (2xx). If `webhookUrl` is unset/empty, rows stay
  unsent — NEVER marked. On a delivery failure, stop and leave the rest
  for the next tick (ordering preserved, at-least-once delivery). Tests
  use a local `node:http` fake webhook, never real Slack.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/slack.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { testPool } from './helpers.js';
import { drainOutbox } from '../src/slack.js';

function fakeSlack(status = 200) {
  const bodies = [];
  const server = http.createServer(async (req, res) => {
    let raw = '';
    for await (const c of req) raw += c;
    bodies.push(JSON.parse(raw));
    res.writeHead(status);
    res.end('ok');
  });
  return new Promise(resolve => server.listen(0, () =>
    resolve({ server, bodies,
      url: `http://127.0.0.1:${server.address().port}/services/T/hook` })));
}

test('drains unsent rows in id order as {text} and marks sent_at', async () => {
  const pool = await testPool();
  const { server, bodies, url } = await fakeSlack();
  await pool.query(`insert into slack_outbox (severity, message)
                    values ('fyi','msg-1'), ('today','msg-2')`);
  const out = await drainOutbox(pool, { webhookUrl: url });
  assert.deepEqual(out, { sent: 2, remaining: 0 });
  assert.deepEqual(bodies, [{ text: 'msg-1' }, { text: 'msg-2' }]);
  const { rowCount } = await pool.query(
    `select 1 from slack_outbox where sent_at is null`);
  assert.equal(rowCount, 0);
  server.close(); await pool.end();
});

test('no webhook configured: rows stay unsent, never marked', async () => {
  const pool = await testPool();
  await pool.query(`insert into slack_outbox (severity, message) values ('fyi','m')`);
  const out = await drainOutbox(pool, {});
  assert.deepEqual(out, { sent: 0, remaining: 1 });
  const { rowCount } = await pool.query(
    `select 1 from slack_outbox where sent_at is null`);
  assert.equal(rowCount, 1);
  await pool.end();
});

test('webhook failure leaves rows unsent for the next tick', async () => {
  const pool = await testPool();
  const { server, url } = await fakeSlack(500);
  await pool.query(`insert into slack_outbox (severity, message) values ('fyi','m')`);
  const out = await drainOutbox(pool, { webhookUrl: url });
  assert.deepEqual(out, { sent: 0, remaining: 1 });
  const { rowCount } = await pool.query(
    `select 1 from slack_outbox where sent_at is null`);
  assert.equal(rowCount, 1);
  server.close(); await pool.end();
});

test('already-sent rows are not re-posted', async () => {
  const pool = await testPool();
  const { server, bodies, url } = await fakeSlack();
  await pool.query(`insert into slack_outbox (severity, message, sent_at)
                    values ('fyi','old', now())`);
  const out = await drainOutbox(pool, { webhookUrl: url });
  assert.deepEqual(out, { sent: 0, remaining: 0 });
  assert.equal(bodies.length, 0);
  server.close(); await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/slack.js'`.

- [ ] **Step 3: Implement slack.js**

```js
// infra/a0/board-service/src/slack.js
// Outbox drain: deliver, THEN mark. A row is marked sent only after the
// webhook returns 2xx; with no webhook configured nothing is marked (the
// rows are the truth that a notification is owed). On failure, stop —
// remaining rows go out on the next tick, in id order (at-least-once).
export async function drainOutbox(pool, { webhookUrl } = {}) {
  const { rows } = await pool.query(
    `select id, message from slack_outbox where sent_at is null order by id`);
  if (!webhookUrl) return { sent: 0, remaining: rows.length };
  let sent = 0;
  for (const row of rows) {
    let ok = false;
    try {
      const res = await fetch(webhookUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text: row.message }),
      });
      ok = res.ok;
    } catch {
      ok = false;
    }
    if (!ok) break;
    await pool.query(
      `update slack_outbox set sent_at = now() where id = $1`, [row.id]);
    sent++;
  }
  return { sent, remaining: rows.length - sent };
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all four drain tests green.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/slack.js infra/a0/board-service/test/slack.test.js
git commit -m "feat(a0): slack outbox drain — deliver-then-mark, honest when webhook is absent"
```

---

### Task 8: The reconciler tick — src/tick.js + POST /tick (acceptance drill 6)

**Files:**
- Create: `infra/a0/board-service/src/tick.js`,
  `infra/a0/board-service/test/tick.test.js`
- Modify: `infra/a0/board-service/src/server.js`

**Interfaces:**
- Consumes: `reclaimStale` + `killOverBudget` (Task 5), `evaluateBreakers`
  (Task 6), `drainOutbox` (Task 7), `makePool`/`applySchema`.
- Produces (cross-plan contract): `runTick(pool, {maxRunMinutes,
  maxStartsPerMin, dailySpendCapUsd, webhookUrl})` →
  `{reclaimed, killed, tripped, sent, unsent}` running the spec §9
  sequence: (1) reclaim stale leases; (2) kill over-budget runs (and queue
  one `next-block` outbox row when any were killed — spec §9 class 1's
  "next work-block" human column); (3) evaluate breakers; (4) drain the
  Slack outbox. CLI: `node src/tick.js` (env `DATABASE_URL`, optional
  `SLACK_WEBHOOK_URL`), exits 0, prints the summary JSON. Also a new admin
  route `POST /tick` → 200 with the same summary, so every cron carrier
  (Task 9) fires the identical pass with only an HTTP credential.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/tick.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { testPool, seedRuns, TEST_URL } from './helpers.js';
import { runTick } from '../src/tick.js';
import { claimNext } from '../src/claims.js';
import { makeServer } from '../src/server.js';

process.env.A0_ADMIN_KEY = 'test-admin';
const admin = { 'authorization': 'Bearer test-admin',
                'content-type': 'application/json' };

async function start(pool) {
  const server = makeServer(pool);
  await new Promise(r => server.listen(0, r));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { server, base };
}

function fakeSlack(status = 200) {
  const bodies = [];
  const server = http.createServer(async (req, res) => {
    let raw = '';
    for await (const c of req) raw += c;
    bodies.push(JSON.parse(raw));
    res.writeHead(status);
    res.end('ok');
  });
  return new Promise(resolve => server.listen(0, () =>
    resolve({ server, bodies,
      url: `http://127.0.0.1:${server.address().port}/services/T/hook` })));
}

test('one tick: reclaims the dead run, kills the runaway, park is resumable', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values
    ('dead','ready-for-agent'), ('runaway','ready-for-agent')`);
  const c1 = await claimNext(pool, {});
  const c2 = await claimNext(pool, {});
  const byTicket = Object.fromEntries([c1, c2].map(c => [c.ticketId, c]));
  // dead worker: stopped heartbeating (lease expired), started recently
  await pool.query(
    `update run set lease_expires_at = now() - interval '1 minute'
     where id = $1`, [byTicket['dead'].runId]);
  // runaway: still heartbeating (fresh lease) but 60 minutes old
  await pool.query(
    `update run set started_at = now() - interval '60 minutes',
                    lease_expires_at = now() + interval '5 minutes'
     where id = $1`, [byTicket['runaway'].runId]);

  const out = await runTick(pool, { webhookUrl: undefined });
  assert.equal(out.reclaimed, 1);
  assert.equal(out.killed, 1);
  assert.ok(out.unsent >= 1, 'over-budget kill queues an outbox row');

  const state = async (id) => (await pool.query(
    `select state, park_note from ticket where id = $1`, [id])).rows[0];
  assert.equal((await state('dead')).state, 'ready-for-agent');
  const runaway = await state('runaway');
  assert.equal(runaway.state, 'needs-human');
  assert.match(runaway.park_note, new RegExp(byTicket['runaway'].runId));

  const { rows } = await pool.query(
    `select severity from slack_outbox where message like 'Over-budget%'`);
  assert.deepEqual(rows, [{ severity: 'next-block' }]);
  await pool.end();
});

test('drill 6: breaker trip → pause within one tick, one Slack message, single flag-flip unpause', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  const { server: slack, bodies, url } = await fakeSlack();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  // start storm: 31 starts inside the last minute, all ended cleanly
  await seedRuns(pool, 31, { startedMinutesAgo: 0, endedMinutesAgo: 0,
                             endReason: 'completed' });

  // tick 1: trips, pauses, posts exactly one Slack message
  const t1 = await runTick(pool, { webhookUrl: url });
  assert.deepEqual(t1.tripped, ['start-storm']);
  assert.equal(t1.sent, 1);
  assert.equal(bodies.length, 1);
  assert.match(bodies[0].text, /start-storm/);

  // new dispatch is halted
  let r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
  assert.equal(r.status, 423);
  assert.equal((await r.json()).error, 'dispatch-paused');

  // tick 2 while paused: no second message
  const t2 = await runTick(pool, { webhookUrl: url });
  assert.deepEqual(t2.tripped, []);
  assert.equal(bodies.length, 1, 'exactly one Slack message per trip');

  // the storm subsides (starts age out of the 60s admission window) …
  await pool.query(`update run set started_at = now() - interval '5 minutes'`);
  // … and unpausing is a single human flag-flip
  r = await fetch(`${base}/flags`, { method: 'POST', headers: admin,
    body: JSON.stringify({ key: 'dispatch_paused',
                           value: { paused: false, reason: '' } }) });
  assert.equal(r.status, 200);
  r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
  assert.equal(r.status, 200);
  assert.equal((await r.json()).ticketId, 't1');
  slack.close(); server.close(); await pool.end();
});

test('POST /tick runs a full pass (admin only)', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  let r = await fetch(`${base}/tick`, { method: 'POST' });
  assert.equal(r.status, 401);
  r = await fetch(`${base}/tick`, { method: 'POST', headers: admin });
  assert.equal(r.status, 200);
  const out = await r.json();
  assert.deepEqual(Object.keys(out).sort(),
    ['killed', 'reclaimed', 'sent', 'tripped', 'unsent']);
  server.close(); await pool.end();
});

test('CLI: node src/tick.js exits 0 and prints the summary JSON', async () => {
  const pool = await testPool(); // resets the DB for a quiet pass
  await pool.end();
  const cwd = fileURLToPath(new URL('..', import.meta.url));
  const { stdout } = await promisify(execFile)(
    process.execPath, ['src/tick.js'],
    { cwd, env: { ...process.env, DATABASE_URL: TEST_URL,
                  SLACK_WEBHOOK_URL: '' } });
  const out = JSON.parse(stdout);
  assert.equal(out.reclaimed, 0);
  assert.equal(out.killed, 0);
  assert.deepEqual(out.tripped, []);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/tick.js'` (and `/tick` 404s).

- [ ] **Step 3: Implement tick.js and the /tick route**

```js
// infra/a0/board-service/src/tick.js
// The reconciler is a cron, not a resident controller (spec §9): one
// idempotent pass every 1–5 minutes — reclaim stale leases → kill
// over-budget runs → evaluate breakers → drain the Slack outbox. All
// state lives in Postgres as conditional UPDATEs, so overlapping or
// restarted ticks are safe. Carriers (see infra/a0/README.md): GitHub
// Actions / pg_cron hitting POST /tick, or this CLI on any scheduler.
import { makePool, applySchema } from './db.js';
import { reclaimStale, killOverBudget } from './reconcile.js';
import { evaluateBreakers } from './breakers.js';
import { drainOutbox } from './slack.js';

export async function runTick(pool, {
  maxRunMinutes = Number(process.env.A0_MAX_RUN_MINUTES ?? 45),
  maxStartsPerMin = Number(process.env.A0_MAX_STARTS_PER_MIN ?? 30),
  dailySpendCapUsd = Number(process.env.A0_DAILY_SPEND_CAP_USD ?? 2000),
  webhookUrl = process.env.SLACK_WEBHOOK_URL,
} = {}) {
  const reclaimed = await reclaimStale(pool);
  const killed = await killOverBudget(pool, { maxRunMinutes });
  if (killed > 0) {
    // spec §9 class 1: runaway runs park for the next work-block
    await pool.query(
      `insert into slack_outbox (severity, message) values ('next-block', $1)`,
      [`Over-budget: killed ${killed} run(s) past ${maxRunMinutes} min; ` +
       `ticket(s) parked needs-human with transcript pointers`]);
  }
  const breakers = await evaluateBreakers(pool,
    { maxStartsPerMin, dailySpendCapUsd });
  const drained = await drainOutbox(pool, { webhookUrl });
  return { reclaimed, killed, tripped: breakers.tripped,
           sent: drained.sent, unsent: drained.remaining };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const pool = makePool(process.env.DATABASE_URL);
  await applySchema(pool);
  console.log(JSON.stringify(await runTick(pool)));
  await pool.end();
}
```

Two edits to `src/server.js`:

(a) Extend the imports — replace

```js
import { setFlag } from './flags.js';
```

with

```js
import { setFlag } from './flags.js';
import { runTick } from './tick.js';
```

(b) Insert directly after the `// POST /reconcile` block (after its
closing `}`):

```js
      // POST /tick (admin) — one full reconciler pass; carrier-agnostic
      // (GitHub Actions / pg_cron+pg_net fire this with only the admin key)
      if (req.method === 'POST' && p.length === 1 && p[0] === 'tick') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        return send(res, 200, await runTick(pool));
      }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all four tick tests green, including drill 6 end-to-end
and the CLI process exiting 0.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/tick.js infra/a0/board-service/src/server.js infra/a0/board-service/test/tick.test.js
git commit -m "feat(a0): reconciler tick — reclaim, over-budget kill, breakers, outbox drain (CLI + /tick)"
```

---

### Task 9: Cron carrier — deployment note + example GitHub Actions workflow

**Files:**
- Create: `infra/a0/deploy/a0-tick.yml`
- Modify: `infra/a0/README.md`

**Interfaces:**
- Consumes: `POST /tick` (Task 8), env contract (Global Constraints).
- Produces: deployment documentation only — the spec §9 carrier decision
  (all three options documented; GitHub Actions `schedule:` chosen as the
  repo-native default WITH its honest ~5-minute-granularity caveat) plus
  one example workflow. The example lives under `infra/a0/deploy/`, NOT
  `.github/workflows/` — this repo's board service is not deployed, so a
  live workflow would fire against nothing.

- [ ] **Step 1: Write the example workflow**

```yaml
# infra/a0/deploy/a0-tick.yml
# Reconciler cron carrier — GitHub Actions variant (repo-native default).
# Copy into .github/workflows/ at deploy time and set repo secrets
# A0_BOARD_URL (e.g. https://a0-board.onrender.com) and A0_ADMIN_KEY.
#
# HONEST CAVEAT (spec §9 wants a 1–5 min cadence): Actions cron is
# best-effort with ~5-minute minimum granularity, and ticks can be delayed
# or occasionally skipped under GitHub load — this sits at the SLOW edge of
# the band. Fine at A0 (leases are minutes-scale and every pass is
# idempotent); switch to pg_cron or a Fly Machine (see infra/a0/README.md)
# when reclaim latency starts costing queue time (spec §11 cron row).
name: a0-reconciler-tick
on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch: {}
jobs:
  tick:
    runs-on: ubuntu-latest
    steps:
      - name: POST /tick
        env:
          A0_BOARD_URL: ${{ secrets.A0_BOARD_URL }}
          A0_ADMIN_KEY: ${{ secrets.A0_ADMIN_KEY }}
        run: |
          code=$(curl -s -o /tmp/tick.json -w '%{http_code}' -X POST \
            "$A0_BOARD_URL/tick" -H "Authorization: Bearer $A0_ADMIN_KEY")
          cat /tmp/tick.json
          test "$code" = "200"
```

- [ ] **Step 2: Append the carrier + env documentation to infra/a0/README.md**

Append to the end of `infra/a0/README.md`:

```markdown
## Reconciler tick (Plan 2)

One idempotent pass every 1–5 minutes (spec §9): reclaim stale leases →
kill over-budget runs → evaluate breakers (start-storm / spend-runaway /
failure-ratio → dispatch pause + one Slack message) → drain the Slack
outbox. Run it any of three ways — all hit the same logic:

- `node board-service/src/tick.js` (env: DATABASE_URL, optional SLACK_WEBHOOK_URL)
- `POST /tick` on the board service (admin bearer)
- a cron carrier below

### Cron carrier options (spec §9)

1. **GitHub Actions `schedule:` — repo-native default.** Copy
   `deploy/a0-tick.yml` into `.github/workflows/` and set repo secrets
   `A0_BOARD_URL` + `A0_ADMIN_KEY`. Honest caveat: Actions cron is
   best-effort with ~5-minute minimum granularity and can delay or skip
   ticks under load — the slow edge of the 1–5 min band. Acceptable at A0;
   move down this list when reclaim latency costs queue time (spec §11).
2. **Supabase pg_cron + pg_net — zero extra vendors, firm 1-min cadence:**
   `select cron.schedule('a0-tick', '* * * * *', $$
      select net.http_post(
        url     := 'https://<board-service>/tick',
        headers := jsonb_build_object('Authorization', 'Bearer <A0_ADMIN_KEY>'))
    $$);`
   Keep the admin key in Supabase Vault rather than inline in `cron.job`
   (the job table is readable by the postgres role).
3. **Fly Machine (~$2/mo):** Fly's native `--schedule` is hourly at its
   finest, so for minutes-cadence run a `shared-cpu-1x` machine executing
   `while true; do node src/tick.js; sleep 60; done`
   (env: DATABASE_URL, SLACK_WEBHOOK_URL).

### Env contract additions (Plan 2)

- A0_MAX_CONCURRENCY (200) — admission: max live runs per claim tx
- A0_MAX_STARTS_PER_MIN (30) — admission cap AND start-storm breaker
- A0_MAX_RUN_MINUTES (45) — over-budget wall-clock kill
- A0_DAILY_SPEND_CAP_USD (2000) — spend-runaway breaker
- A0_CACHE_RATIO_FLOOR (0.5) — meter flags runs below this cache-read ratio
- A0_MONTHLY_INFRA_USD (0) — infra side of the meter's infra:token split
- SLACK_WEBHOOK_URL — unset ⇒ outbox rows accumulate unsent (never marked)

### Cost meter

`node board-service/src/meter.js` (env: DATABASE_URL) prints the 30-day
report: runs, totalCostUsd, perRun, perTicket, cacheReadRatio, flagged
(cache-broken runs), infraUsd, tokenInfraRatio. Workers feed it via
`POST /runs/:id/usage` before their final transition.
```

- [ ] **Step 3: Verify the artifacts**

Run: `test -f infra/a0/deploy/a0-tick.yml && grep -q 'workflow_dispatch' infra/a0/deploy/a0-tick.yml && grep -q 'Cron carrier options' infra/a0/README.md && echo OK`
Expected: `OK`. (The curl shape the workflow uses is exercised for real by
Task 8's `POST /tick` test.)

- [ ] **Step 4: Commit**

```bash
git add infra/a0/deploy/a0-tick.yml infra/a0/README.md
git commit -m "docs(a0): cron carrier options + example GitHub Actions tick workflow"
```

---

### Task 10: Final verification — spec acceptance items this plan owns

**Files:** none (verification only, plus the spec living-tail note).

- [ ] **Step 1: Full suite**

Run (from `infra/a0/board-service/`): `npm test`
Expected: all tests PASS — Plan 1's five suites plus this plan's eight.

- [ ] **Step 2: Execute acceptance item 6, as written**

From spec `## Acceptance (behavior-phrased)`:

> 6. Tripping any breaker (storm, spend, failure-ratio) halts new dispatch
>    within one tick, posts one Slack message, parks in-flight work
>    resumable, and unpausing is a single human flag-flip.

Run: `node --test test/tick.test.js test/breakers.test.js test/overbudget.test.js`
Expected: PASS. Clause coverage:
- *any breaker (storm, spend, failure-ratio)* — `breakers.test.js` trips
  each of the three individually and all three at once;
- *halts new dispatch within one tick* — `tick.test.js` drill 6: one
  `runTick` call, then `POST /claims` → 423;
- *posts one Slack message* — drill 6 asserts the fake webhook received
  exactly one body across two ticks (and `breakers.test.js` asserts the
  already-paused no-op and one-row-per-trip);
- *parks in-flight work resumable* — `overbudget.test.js` + tick test:
  the parked ticket transitions `needs-human → ready-for-agent` and is
  re-claimed with a bumped fence (session log untouched, zombie fenced);
- *unpausing is a single human flag-flip* — drill 6: one `POST /flags`
  with `{paused:false}`, next claim returns 200.

- [ ] **Step 3: Execute acceptance item 8, as written**

> 8. The monthly cost meter reports $/run, $/ticket, cache-read ratio, and
>    infra:token split without manual collation; a deliberately
>    cache-broken canary run is visibly flagged by the ratio metric.

Run: `node --test test/meter.test.js`
Expected: PASS. Clause coverage:
- *$/run, $/ticket, cache-read ratio, infra:token split* — one
  `meterReport` call returns all four from SQL over `run_usage` (usage
  arrives via `POST /runs/:id/usage`, so no manual collation anywhere);
- *without manual collation* — the CLI test proves `node src/meter.js`
  alone produces the full report;
- *cache-broken canary visibly flagged* — the seeded zero-cache-read run
  appears in `flagged`, the disciplined run does not.

Then demonstrate the CLI live against the test DB (the meter suite's CLI
test runs last and leaves its two seeded usage rows in place):
`node --test test/meter.test.js && DATABASE_URL=${TEST_DATABASE_URL:-postgres://postgres:a0@localhost:54329/postgres} node src/meter.js`
Expected: the second command prints the report JSON — `runs: 2`,
`flagged` holding the one canary run id — produced by the CLI alone, no
collation.

- [ ] **Step 4: Note the shared-ownership items**

Acceptance item 2's reclaim/fencing half is already covered by Plan 1
(`reconcile.test.js`); this plan's tick makes the "within one reconciler
tick" clause literal (`runTick` step 1 IS `reclaimStale`) — the
resume-on-fresh-sandbox half remains with Plan 3. The §2 admission
counters (this plan) become Plan 3's dispatcher backpressure via the
423/429 mapping.

- [ ] **Step 5: Record coverage in the spec's living tail**

Append to `docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md`
`## Revision Notes`:

```
- <date>: Plan 2 (a0-reconciler-breakers-meter) implemented — acceptance 6
  and 8 verified by test (tick/breakers/meter suites); item 2's "within one
  reconciler tick" clause now runs inside runTick; admission counters (§2)
  live inside the claim transaction with the 423/429 contract for Plan 3.
```

- [ ] **Step 6: Commit**

```bash
git add docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "docs(a0): record Plan 2 acceptance coverage in spec living tail"
```



