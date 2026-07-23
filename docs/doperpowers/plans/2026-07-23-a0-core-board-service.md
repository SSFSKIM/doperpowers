# A0 Core — Board Service + Dispatch Claim Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the A0 spec's first brick — the thin board service (ticket
SSOT with server-side transition legality, atomic claims, per-run bearer
tokens, session-event append with lease heartbeat, stale-lease reclaim) on
one Postgres — plus the T1 instrumentation spike that collapses the spec's
cost Fermis.

**Architecture:** One Node 22 process over one Postgres. Every worker write
goes through HTTP endpoints; workers never speak SQL. The claim is a single
transaction: `FOR UPDATE SKIP LOCKED` pick + conditional `UPDATE` of the
ticket + `INSERT` of the run row with an incremented fencing token — the
spec's same-transaction property. Transition legality is a data table
enforced as a conditional UPDATE (rows-affected=0 = lost race / illegal).

**Tech Stack:** Node 22 (ESM, `node:http`, `node:test`, `node:crypto`),
`pg` (only npm dependency), PostgreSQL 15+ (local via Docker for dev/test;
Supabase in production per spec §5).

**Plan slicing (this is Plan 1 of 4 for the spec):**
1. **This plan** — T1 spike + schema + board service + claim path (spec §1, §2, §4 schema).
2. Reconciler cron + circuit breakers + cost meter + Slack outbox (spec §8, §9).
3. Substrate adapter + E2B dispatch + secrets placement (spec §3, §6) — gated on spike T2 (E2B contract facts).
4. Linear mirror, one-way authority / two-way visibility (spec §1 mirror).

## Global Constraints

- Node ≥ 22 (built-in test runner, ESM). Only npm dependency: `pg`.
- Ticket states (frozen semantic layer — do not add or rename):
  `backlog`, `ready-for-agent`, `in-progress`, `in-review`,
  `needs-human`, `needs-info`, `interactive-preferred`,
  `confident-ready`, `done`.
- Park transitions (`needs-human`/`needs-info`/`interactive-preferred`)
  REQUIRE a non-empty park note; `in-review` REQUIRES a PR URL (spec §1 /
  symphony doctrine "End of scope = PR or park").
- Claim = one transaction: pick + ticket UPDATE + run INSERT (spec §2).
- Fencing: `ticket.fence` increments on every claim; run-authorized writes
  must carry a matching fence; stale fences are refused (spec §2).
- Session-event append IS the lease heartbeat (spec §2/§4).
- Store only SHA-256 hashes of bearer tokens, never raw tokens.
- Tests run against a real Postgres (`TEST_DATABASE_URL`); the conditional
  UPDATE and SKIP LOCKED semantics are the subject under test — never mock
  the database.
- Dev/test DB: `docker run -d --name a0-pg -e POSTGRES_PASSWORD=a0 -p 54329:5432 postgres:16`
  → `TEST_DATABASE_URL=postgres://postgres:a0@localhost:54329/postgres`

## File Structure

```
infra/a0/
  README.md                      — component map + run instructions
  schema.sql                     — the three-plane schema (idempotent DDL)
  tools/measure-runs.mjs         — T1 spike: transcript-derived cost/size metering
  board-service/
    package.json                 — name, type:module, deps: pg
    src/db.js                    — pool factory, withTx helper, applySchema
    src/transitions.js           — legality table + guard logic (pure)
    src/claims.js                — claimNext transaction
    src/events.js                — appendEvent (heartbeat), addComment
    src/auth.js                  — token mint/verify (run bearer + admin key)
    src/reconcile.js             — reclaimStale
    src/server.js                — node:http routing, JSON plumbing
    test/helpers.js              — test pool + truncate
    test/transitions.test.js
    test/claims.test.js
    test/events.test.js
    test/reconcile.test.js
    test/server.test.js
    Dockerfile
    render.yaml
```

---

### Task 1: T1 spike — measure real run costs and event sizes (knowledge deliverable)

**Question this spike answers (spec Adoption 1 / spike T1):** what are the
real per-run token cost, cache-read ratio, and session-event size on this
machine's actual Claude Code transcripts? The spec's Fermis span 4–6×
(tokens $0.8–3/run; events 2–8 KB) and "instrumentation precedes contracts."

**Files:**
- Create: `infra/a0/tools/measure-runs.mjs`

**Interfaces:**
- Produces: a per-session metrics table (JSON + stdout) — promoted into
  Plan 2's cost meter if the parse proves out (spec §8 cost meter).

- [ ] **Step 1: Write the measurement script**

```js
// infra/a0/tools/measure-runs.mjs
// Usage: node measure-runs.mjs <transcript-dir> [limit]
// Parses Claude Code JSONL transcripts; per session: token totals by class,
// cost at Sonnet 4.6 rates, cache-read ratio, event count/size stats.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const RATES = { in: 3, out: 15, cacheRead: 0.3, cacheWrite: 3.75 }; // $/MTok, Sonnet 4.6
const dir = process.argv[2];
const limit = Number(process.argv[3] ?? 20);
if (!dir) { console.error('usage: node measure-runs.mjs <dir> [limit]'); process.exit(1); }

const files = readdirSync(dir).filter(f => f.endsWith('.jsonl'))
  .map(f => join(dir, f))
  .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)
  .slice(0, limit);

const sessions = [];
for (const file of files) {
  const s = { file, events: 0, bytes: 0, in: 0, out: 0, cacheRead: 0, cacheWrite: 0 };
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    s.events++; s.bytes += Buffer.byteLength(line);
    let obj; try { obj = JSON.parse(line); } catch { continue; }
    const u = obj?.message?.usage;
    if (!u) continue;
    s.in += u.input_tokens ?? 0;
    s.out += u.output_tokens ?? 0;
    s.cacheRead += u.cache_read_input_tokens ?? 0;
    s.cacheWrite += u.cache_creation_input_tokens ?? 0;
  }
  const cost = (s.in * RATES.in + s.out * RATES.out + s.cacheRead * RATES.cacheRead
    + s.cacheWrite * RATES.cacheWrite) / 1e6;
  const denom = s.in + s.cacheRead + s.cacheWrite;
  sessions.push({
    file: file.split('/').pop(),
    events: s.events,
    meanEventBytes: s.events ? Math.round(s.bytes / s.events) : 0,
    mbTotal: +(s.bytes / 1e6).toFixed(2),
    cost: +cost.toFixed(3),
    cacheReadRatio: denom ? +(s.cacheRead / denom).toFixed(3) : 0,
  });
}
console.table(sessions);
const agg = (k) => sessions.reduce((a, x) => a + x[k], 0) / (sessions.length || 1);
console.log(JSON.stringify({
  sessions: sessions.length,
  meanCost: +agg('cost').toFixed(3),
  meanEventBytes: Math.round(agg('meanEventBytes')),
  meanMb: +agg('mbTotal').toFixed(2),
  meanCacheReadRatio: +agg('cacheReadRatio').toFixed(3),
}, null, 2));
```

- [ ] **Step 2: Run it against real transcripts**

Run: `node infra/a0/tools/measure-runs.mjs ~/.claude/projects/-Users-new-Developer-GitHub-doperpowers 20`
Expected: a table of ≤20 recent sessions plus an aggregate JSON block. If
the directory has no `.jsonl`, point at another `~/.claude/projects/<slug>`
directory that does.

- [ ] **Step 3: Record the verdict in the spec (spike output routing)**

Append to `docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md`
`## Surprises & Discoveries` a bullet of the form:

```
- **T1 measurement (this machine, N sessions):** mean cost $X/session,
  cache-read ratio Y, mean event Z KB, mean session W MB — [inside |
  outside] the spec's Fermi bands ($0.8–3/run; 2–8 KB/event; 0.5–2 MB/run).
  Caveat: interactive+worker mix, not pure 12-min worker runs.
```

Promote-or-discard: the script is PROMOTED as the seed of Plan 2's cost
meter (per-run usage rows) if the parse works on real transcripts;
discarded only if the transcript format defeats it (then record that).

- [ ] **Step 4: Commit**

```bash
git add infra/a0/tools/measure-runs.mjs docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "feat(a0): T1 spike — transcript cost/size meter + measured Fermi check"
```

---

### Task 2: Schema + db helpers

**Files:**
- Create: `infra/a0/schema.sql`, `infra/a0/board-service/package.json`,
  `infra/a0/board-service/src/db.js`, `infra/a0/board-service/test/helpers.js`,
  `infra/a0/board-service/test/db.test.js`

**Interfaces:**
- Produces: `makePool(url)` → pg Pool; `withTx(pool, fn)` → runs fn(client)
  in BEGIN/COMMIT with ROLLBACK on throw; `applySchema(pool)`;
  tables `ticket(id, state, owner_run, fence, pr_url, park_note, payload, updated_at)`,
  `run(id, ticket_id, fence, token_hash, lease_expires_at, started_at, ended_at, end_reason)`,
  `session_event(run_id, seq, at, kind, body)`, `ticket_comment(id, ticket_id, run_id, body, at)`.

- [ ] **Step 1: Write package.json and schema**

```json
{
  "name": "a0-board-service",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22" },
  "scripts": { "test": "node --test test/", "start": "node src/server.js" },
  "dependencies": { "pg": "^8.12.0" }
}
```

```sql
-- infra/a0/schema.sql — idempotent
create table if not exists ticket (
  id         text primary key,
  state      text not null default 'backlog',
  owner_run  text,
  fence      bigint not null default 0,
  pr_url     text,
  park_note  text,
  payload    jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists run (
  id               text primary key,
  ticket_id        text not null references ticket(id),
  fence            bigint not null,
  token_hash       text not null,
  lease_expires_at timestamptz not null,
  started_at       timestamptz not null default now(),
  ended_at         timestamptz,
  end_reason       text
);
create index if not exists run_live_idx on run (lease_expires_at) where ended_at is null;

create table if not exists session_event (
  run_id text not null references run(id),
  seq    bigint not null,
  at     timestamptz not null default now(),
  kind   text not null,
  body   jsonb not null default '{}'::jsonb,
  primary key (run_id, seq)
);

create table if not exists ticket_comment (
  id        bigint generated always as identity primary key,
  ticket_id text not null references ticket(id),
  run_id    text,
  body      text not null,
  at        timestamptz not null default now()
);
```

- [ ] **Step 2: Write db.js**

```js
// infra/a0/board-service/src/db.js
import pg from 'pg';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export function makePool(url) {
  return new pg.Pool({ connectionString: url, max: 10 });
}

export async function withTx(pool, fn) {
  const client = await pool.connect();
  try {
    await client.query('begin');
    const out = await fn(client);
    await client.query('commit');
    return out;
  } catch (e) {
    await client.query('rollback');
    throw e;
  } finally {
    client.release();
  }
}

export async function applySchema(pool) {
  const sql = readFileSync(
    fileURLToPath(new URL('../../schema.sql', import.meta.url)), 'utf8');
  await pool.query(sql);
}
```

- [ ] **Step 3: Write test helper + failing schema test**

```js
// infra/a0/board-service/test/helpers.js
import { makePool, applySchema } from '../src/db.js';

export async function testPool() {
  const url = process.env.TEST_DATABASE_URL
    ?? 'postgres://postgres:a0@localhost:54329/postgres';
  const pool = makePool(url);
  await applySchema(pool);
  await pool.query('truncate session_event, ticket_comment, run, ticket cascade');
  return pool;
}
```

```js
// infra/a0/board-service/test/db.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';

test('schema applies and core tables exist', async () => {
  const pool = await testPool();
  const r = await pool.query(
    `select table_name from information_schema.tables
     where table_name in ('ticket','run','session_event','ticket_comment')`);
  assert.equal(r.rowCount, 4);
  await pool.end();
});
```

- [ ] **Step 4: Run test to verify it fails, then passes**

Run (from `infra/a0/board-service/`): `npm install && npm test`
Expected first: FAIL if the Docker Postgres isn't up (start it with the
Global Constraints one-liner) — then PASS: `# pass 1`.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/schema.sql infra/a0/board-service
git commit -m "feat(a0): board schema + db helpers with real-postgres test rig"
```

---

### Task 3: Transition legality (pure logic + conditional UPDATE)

**Files:**
- Create: `infra/a0/board-service/src/transitions.js`,
  `infra/a0/board-service/test/transitions.test.js`

**Interfaces:**
- Consumes: `withTx` (Task 2).
- Produces: `LEGAL` map, `PARK_STATES`, `isLegal(from,to)`, and
  `transition(client, {ticketId, from, to, fence, prUrl, parkNote})` →
  `{ok:true}` | `{ok:false, error:'illegal-transition'|'pr-url-required'|'park-note-required'|'lost-race'}`.
  `fence` may be `null` (admin/human writes skip the fence check); when a
  ticket leaves worker ownership (`ready-for-agent`, `confident-ready`,
  `done`) `owner_run` clears.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/transitions.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';
import { transition, isLegal } from '../src/transitions.js';
import { withTx } from '../src/db.js';

async function seed(pool, state, fence = 0) {
  await pool.query(
    `insert into ticket (id, state, fence) values ('t1', $1, $2)`, [state, fence]);
}

test('legality table basics', () => {
  assert.equal(isLegal('ready-for-agent', 'in-progress'), true);
  assert.equal(isLegal('backlog', 'done'), false);
  assert.equal(isLegal('in-progress', 'needs-human'), true);
});

test('illegal transition returns error, never writes', async () => {
  const pool = await testPool();
  await seed(pool, 'backlog');
  const out = await withTx(pool, c =>
    transition(c, { ticketId: 't1', from: 'backlog', to: 'done' }));
  assert.deepEqual(out, { ok: false, error: 'illegal-transition' });
  const { rows } = await pool.query(`select state from ticket where id='t1'`);
  assert.equal(rows[0].state, 'backlog');
  await pool.end();
});

test('in-review requires pr_url; parks require note', async () => {
  const pool = await testPool();
  await seed(pool, 'in-progress');
  const noPr = await withTx(pool, c =>
    transition(c, { ticketId: 't1', from: 'in-progress', to: 'in-review' }));
  assert.equal(noPr.error, 'pr-url-required');
  const noNote = await withTx(pool, c =>
    transition(c, { ticketId: 't1', from: 'in-progress', to: 'needs-human' }));
  assert.equal(noNote.error, 'park-note-required');
  const ok = await withTx(pool, c =>
    transition(c, { ticketId: 't1', from: 'in-progress', to: 'needs-human',
                    parkNote: 'q1: which flag? recommend: --safe' }));
  assert.equal(ok.ok, true);
  await pool.end();
});

test('stale state loses the race (rows-affected=0)', async () => {
  const pool = await testPool();
  await seed(pool, 'done');
  const out = await withTx(pool, c =>
    transition(c, { ticketId: 't1', from: 'confident-ready', to: 'done' }));
  assert.deepEqual(out, { ok: false, error: 'lost-race' });
  await pool.end();
});

test('wrong fence is refused', async () => {
  const pool = await testPool();
  await seed(pool, 'in-progress', 3);
  const out = await withTx(pool, c =>
    transition(c, { ticketId: 't1', from: 'in-progress', to: 'in-review',
                    prUrl: 'https://x/pr/1', fence: 2 }));
  assert.deepEqual(out, { ok: false, error: 'lost-race' });
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/transitions.js'`.

- [ ] **Step 3: Implement**

```js
// infra/a0/board-service/src/transitions.js
export const LEGAL = {
  'backlog':               ['ready-for-agent'],
  'ready-for-agent':       ['in-progress'],
  'in-progress':           ['in-review', 'needs-human', 'needs-info',
                            'interactive-preferred', 'ready-for-agent'],
  'in-review':             ['confident-ready', 'in-progress', 'needs-human'],
  'needs-human':           ['ready-for-agent'],
  'needs-info':            ['ready-for-agent'],
  'interactive-preferred': ['ready-for-agent'],
  'confident-ready':       ['done'],
  'done':                  [],
};
export const PARK_STATES = ['needs-human', 'needs-info', 'interactive-preferred'];
export const UNOWNED_STATES = ['ready-for-agent', 'confident-ready', 'done',
                               ...PARK_STATES];
export function isLegal(from, to) { return (LEGAL[from] ?? []).includes(to); }

export async function transition(client, { ticketId, from, to, fence = null,
                                           prUrl = null, parkNote = null }) {
  if (!isLegal(from, to)) return { ok: false, error: 'illegal-transition' };
  if (to === 'in-review' && !prUrl) return { ok: false, error: 'pr-url-required' };
  if (PARK_STATES.includes(to) && !parkNote)
    return { ok: false, error: 'park-note-required' };
  const res = await client.query(
    `update ticket set
       state = $1,
       pr_url = coalesce($2, pr_url),
       park_note = $3,
       owner_run = case when $1 = any($7::text[]) then null else owner_run end,
       updated_at = now()
     where id = $4 and state = $5 and ($6::bigint is null or fence = $6)`,
    [to, prUrl, PARK_STATES.includes(to) ? parkNote : null,
     ticketId, from, fence, UNOWNED_STATES]);
  return res.rowCount === 1 ? { ok: true } : { ok: false, error: 'lost-race' };
}
```

Note: parks keep `owner_run`? No — parks are pauses whose resume happens by
re-claim from the session log; ownership clears (UNOWNED_STATES includes the
parks) and the lease reclaim in Task 6/reconcile handles the live run row.

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all transitions tests green.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/transitions.js infra/a0/board-service/test/transitions.test.js
git commit -m "feat(a0): server-side transition legality as conditional UPDATE"
```

---

### Task 4: Atomic claim (same-transaction property) — acceptance drill 1

**Files:**
- Create: `infra/a0/board-service/src/claims.js`,
  `infra/a0/board-service/src/auth.js`,
  `infra/a0/board-service/test/claims.test.js`

**Interfaces:**
- Consumes: `withTx` (Task 2).
- Produces: `claimNext(pool, {leaseMinutes=10})` →
  `null` | `{runId, ticketId, fence, token, envKey}` (raw token returned
  once, only hash stored; `envKey` = ticket `payload.envKey ?? null` — Plan
  3's dispatcher maps it to the sandbox template); `mintToken()` → `{token, tokenHash}`;
  `verifyRunToken(pool, runId, token)` → boolean;
  `verifyAdmin(req)` → boolean (compares `Authorization: Bearer` against
  env `A0_ADMIN_KEY`, constant-time).

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/claims.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';
import { claimNext } from '../src/claims.js';
import { verifyRunToken } from '../src/auth.js';

test('claim moves ticket, bumps fence, mints verifiable token', async () => {
  const pool = await testPool();
  await pool.query(
    `insert into ticket (id, state, fence) values ('t1','ready-for-agent', 4)`);
  const c = await claimNext(pool, {});
  assert.equal(c.ticketId, 't1');
  assert.equal(c.fence, 5);
  const { rows } = await pool.query(`select state, owner_run, fence from ticket`);
  assert.deepEqual(rows[0], { state: 'in-progress', owner_run: c.runId, fence: '5' });
  assert.equal(await verifyRunToken(pool, c.runId, c.token), true);
  assert.equal(await verifyRunToken(pool, c.runId, 'wrong'), false);
  await pool.end();
});

test('drill 1: two racing claims on one ready ticket — exactly one winner', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const [a, b] = await Promise.all([claimNext(pool, {}), claimNext(pool, {})]);
  const winners = [a, b].filter(Boolean);
  assert.equal(winners.length, 1);
  await pool.end();
});

test('no ready ticket → null, nothing written', async () => {
  const pool = await testPool();
  assert.equal(await claimNext(pool, {}), null);
  const { rowCount } = await pool.query('select 1 from run');
  assert.equal(rowCount, 0);
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/claims.js'`.

- [ ] **Step 3: Implement auth.js and claims.js**

```js
// infra/a0/board-service/src/auth.js
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';

export function mintToken() {
  const token = randomBytes(32).toString('hex');
  return { token, tokenHash: sha256(token) };
}
export function sha256(s) {
  return createHash('sha256').update(s).digest('hex');
}
export async function verifyRunToken(pool, runId, token) {
  if (!token) return false;
  const { rows } = await pool.query(
    `select token_hash from run where id = $1 and ended_at is null`, [runId]);
  if (rows.length === 0) return false;
  const a = Buffer.from(rows[0].token_hash);
  const b = Buffer.from(sha256(token));
  return a.length === b.length && timingSafeEqual(a, b);
}
export function verifyAdmin(req) {
  const key = process.env.A0_ADMIN_KEY ?? '';
  const got = (req.headers['authorization'] ?? '').replace(/^Bearer /, '');
  if (!key || !got) return false;
  const a = Buffer.from(sha256(key)), b = Buffer.from(sha256(got));
  return timingSafeEqual(a, b);
}
```

```js
// infra/a0/board-service/src/claims.js
import { randomUUID } from 'node:crypto';
import { withTx } from './db.js';
import { mintToken } from './auth.js';

export async function claimNext(pool, { leaseMinutes = 10 } = {}) {
  return withTx(pool, async (client) => {
    const pick = await client.query(
      `select id, fence, payload from ticket where state = 'ready-for-agent'
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
    return { runId, ticketId: t.id, fence, token,
             envKey: t.payload?.envKey ?? null };
  });
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS including the racing-claims drill.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/claims.js infra/a0/board-service/src/auth.js infra/a0/board-service/test/claims.test.js
git commit -m "feat(a0): atomic claim — SKIP LOCKED pick + ticket update + run insert in one tx"
```

---

### Task 5: Session-event append = lease heartbeat; comments

**Files:**
- Create: `infra/a0/board-service/src/events.js`,
  `infra/a0/board-service/test/events.test.js`

**Interfaces:**
- Consumes: `claimNext` (Task 4) in tests.
- Produces: `appendEvent(pool, {runId, kind, body, leaseMinutes=10})` →
  `{ok:true, seq}` | `{ok:false, error:'run-not-live'}` (single UPDATE+INSERT
  statement; refreshes `lease_expires_at`); `addComment(pool, {ticketId,
  runId, body})` → `{ok:true, id}`; `endRun(pool, {runId, reason})` →
  `{ok:true}` | `{ok:false, error:'run-not-live'}` — sets `ended_at`/
  `end_reason` on a live run (Plan 3's dispatcher calls it with
  `'completed'` or `'worker-failed'` at run end, AFTER posting usage — Plan
  2's failure-ratio breaker reads these reasons). One writer per run is
  assumed (the run's own worker) — seq is max+1 within that assumption;
  note this in code.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/events.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';
import { claimNext } from '../src/claims.js';
import { appendEvent, addComment, endRun } from '../src/events.js';

test('append increments seq and refreshes the lease', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const c = await claimNext(pool, { leaseMinutes: 1 });
  const before = (await pool.query(
    `select lease_expires_at from run where id=$1`, [c.runId])).rows[0].lease_expires_at;
  const e1 = await appendEvent(pool, { runId: c.runId, kind: 'tool', body: { n: 1 } });
  const e2 = await appendEvent(pool, { runId: c.runId, kind: 'tool', body: { n: 2 } });
  assert.deepEqual([e1.seq, e2.seq], [1, 2]);
  const after = (await pool.query(
    `select lease_expires_at from run where id=$1`, [c.runId])).rows[0].lease_expires_at;
  assert.ok(new Date(after) > new Date(before), 'lease must be pushed forward');
  await pool.end();
});

test('append to ended run is refused', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const c = await claimNext(pool, {});
  await pool.query(`update run set ended_at = now() where id = $1`, [c.runId]);
  const out = await appendEvent(pool, { runId: c.runId, kind: 'x', body: {} });
  assert.deepEqual(out, { ok: false, error: 'run-not-live' });
  await pool.end();
});

test('endRun records reason once; second end refused', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const c = await claimNext(pool, {});
  const out = await endRun(pool, { runId: c.runId, reason: 'completed' });
  assert.deepEqual(out, { ok: true });
  const r = (await pool.query(`select end_reason from run where id=$1`, [c.runId])).rows[0];
  assert.equal(r.end_reason, 'completed');
  const again = await endRun(pool, { runId: c.runId, reason: 'worker-failed' });
  assert.deepEqual(again, { ok: false, error: 'run-not-live' });
  await pool.end();
});

test('comments attach to tickets', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','backlog')`);
  const out = await addComment(pool, { ticketId: 't1', runId: null, body: 'verdict: pass' });
  assert.equal(out.ok, true);
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

```js
// infra/a0/board-service/src/events.js
// seq = max+1 is safe under this system's contract: exactly one writer per
// run (the run's own worker) appends; concurrent same-run writers are a
// protocol violation upstream.
export async function appendEvent(pool, { runId, kind, body,
                                          leaseMinutes = 10 }) {
  const res = await pool.query(
    `with live as (
       update run set lease_expires_at = now() + make_interval(mins => $4)
       where id = $1 and ended_at is null
       returning id)
     insert into session_event (run_id, seq, kind, body)
     select live.id,
            coalesce((select max(seq) from session_event where run_id = live.id), 0) + 1,
            $2, $3
     from live
     returning seq`,
    [runId, kind, body ?? {}, leaseMinutes]);
  if (res.rowCount === 0) return { ok: false, error: 'run-not-live' };
  return { ok: true, seq: Number(res.rows[0].seq) };
}

export async function addComment(pool, { ticketId, runId, body }) {
  const res = await pool.query(
    `insert into ticket_comment (ticket_id, run_id, body)
     values ($1, $2, $3) returning id`,
    [ticketId, runId, body]);
  return { ok: true, id: Number(res.rows[0].id) };
}

export async function endRun(pool, { runId, reason }) {
  const res = await pool.query(
    `update run set ended_at = now(), end_reason = $2
     where id = $1 and ended_at is null`,
    [runId, reason]);
  return res.rowCount === 1 ? { ok: true }
                            : { ok: false, error: 'run-not-live' };
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/events.js infra/a0/board-service/test/events.test.js
git commit -m "feat(a0): session-event append doubles as lease heartbeat"
```

---

### Task 6: Stale-lease reclaim + fencing refusal — acceptance drill 2 (fencing half)

**Files:**
- Create: `infra/a0/board-service/src/reconcile.js`,
  `infra/a0/board-service/test/reconcile.test.js`

**Interfaces:**
- Consumes: `claimNext`, `transition`, `withTx`.
- Produces: `reclaimStale(pool)` → number of reclaimed runs. Semantics: end
  every live run whose lease expired (`end_reason='lease-expired'`), and
  return its ticket to `ready-for-agent` (ownership cleared, fence KEPT — the
  next claim bumps it, which is what invalidates the zombie).

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/board-service/test/reconcile.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { testPool } from './helpers.js';
import { claimNext } from '../src/claims.js';
import { reclaimStale } from '../src/reconcile.js';
import { transition } from '../src/transitions.js';
import { withTx } from '../src/db.js';

test('expired lease is reclaimed; ticket returns to ready-for-agent', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const c = await claimNext(pool, {});
  await pool.query(`update run set lease_expires_at = now() - interval '1 minute'
                    where id = $1`, [c.runId]);
  assert.equal(await reclaimStale(pool), 1);
  const t = (await pool.query(`select state, owner_run, fence from ticket`)).rows[0];
  assert.deepEqual(t, { state: 'ready-for-agent', owner_run: null, fence: '1' });
  const r = (await pool.query(`select end_reason from run where id=$1`, [c.runId])).rows[0];
  assert.equal(r.end_reason, 'lease-expired');
  await pool.end();
});

test('drill 2 fencing: superseded run cannot complete its old attempt', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  const zombie = await claimNext(pool, {});
  await pool.query(`update run set lease_expires_at = now() - interval '1 minute'
                    where id = $1`, [zombie.runId]);
  await reclaimStale(pool);
  const fresh = await claimNext(pool, {});
  assert.equal(fresh.fence, zombie.fence + 1);
  // zombie tries to finish with its stale fence
  const out = await withTx(pool, c => transition(c, {
    ticketId: 't1', from: 'in-progress', to: 'in-review',
    prUrl: 'https://x/pr/9', fence: zombie.fence }));
  assert.deepEqual(out, { ok: false, error: 'lost-race' });
  // fresh attempt with current fence succeeds
  const ok = await withTx(pool, c => transition(c, {
    ticketId: 't1', from: 'in-progress', to: 'in-review',
    prUrl: 'https://x/pr/10', fence: fresh.fence }));
  assert.equal(ok.ok, true);
  await pool.end();
});

test('healthy leases are untouched', async () => {
  const pool = await testPool();
  await pool.query(`insert into ticket (id, state) values ('t1','ready-for-agent')`);
  await claimNext(pool, {});
  assert.equal(await reclaimStale(pool), 0);
  await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test` — Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

```js
// infra/a0/board-service/src/reconcile.js
// One idempotent statement: end stale runs, free their tickets. Fence is
// deliberately NOT changed here — the next claim increments it, which is
// what fences out the zombie's late writes.
export async function reclaimStale(pool) {
  const res = await pool.query(
    `with dead as (
       update run set ended_at = now(), end_reason = 'lease-expired'
       where ended_at is null and lease_expires_at < now()
       returning id, ticket_id)
     update ticket t
       set state = 'ready-for-agent', owner_run = null, updated_at = now()
     from dead d
     where t.id = d.ticket_id and t.owner_run = d.id and t.state = 'in-progress'
     returning t.id`);
  return res.rowCount;
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/reconcile.js infra/a0/board-service/test/reconcile.test.js
git commit -m "feat(a0): stale-lease reclaim; fencing refuses superseded attempts"
```

---

### Task 7: HTTP surface (the ~6 endpoints)

**Files:**
- Create: `infra/a0/board-service/src/server.js`,
  `infra/a0/board-service/test/server.test.js`

**Interfaces:**
- Consumes: everything above.
- Produces: `makeServer(pool)` → `node:http` Server, and a `main()` that
  listens on `process.env.PORT ?? 8080`. Routes (JSON in/out):
  - `POST /tickets` (admin) `{id, payload?}` → 201 ticket in `backlog`
  - `POST /tickets/:id/transition` `{from, to, fence?, prUrl?, parkNote?, runId?}`
    — admin key OR run bearer token; for run auth, fence is REQUIRED and the
    run must OWN this ticket (`run.ticket_id = :id` — the spec's "token
    scoped to this ticket's transitions"); 200 `{ok:true}` / 403
    `{error:'not-your-ticket'}` / 409 `{error}`
  - `POST /claims` (admin/dispatcher) → 200 claim JSON or 204
  - `POST /runs/:id/events` (run bearer) `{kind, body}` → 200 `{seq}` / 409
  - `POST /runs/:id/end` (run bearer or admin) `{reason}` → 200 `{ok:true}`
    / 409 `{error:'run-not-live'}` — dispatcher records `'completed'` /
    `'worker-failed'` here at run end (after posting usage)
  - `POST /tickets/:id/comments` (admin or run bearer) `{body}` → 201
  - `GET /tickets?state=S` (admin) → 200 `[{id,state,owner_run,fence,...}]`
  - `POST /reconcile` (admin) → 200 `{reclaimed: n}`
  - anything unauthenticated → 401; unknown route → 404.

- [ ] **Step 1: Write failing tests (drive the routes end-to-end)**

```js
// infra/a0/board-service/test/server.test.js
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

test('end-to-end: create → ready → claim → events → in-review', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);

  let r = await fetch(`${base}/tickets`, { method: 'POST', headers: admin,
    body: JSON.stringify({ id: 't1' }) });
  assert.equal(r.status, 201);

  r = await fetch(`${base}/tickets/t1/transition`, { method: 'POST', headers: admin,
    body: JSON.stringify({ from: 'backlog', to: 'ready-for-agent' }) });
  assert.equal(r.status, 200);

  r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
  assert.equal(r.status, 200);
  const claim = await j(r);

  const runAuth = { 'authorization': `Bearer ${claim.token}`,
                    'content-type': 'application/json' };
  r = await fetch(`${base}/runs/${claim.runId}/events`, { method: 'POST',
    headers: runAuth, body: JSON.stringify({ kind: 'tool', body: { x: 1 } }) });
  assert.equal(r.status, 200);
  assert.equal((await j(r)).seq, 1);

  r = await fetch(`${base}/tickets/t1/transition`, { method: 'POST', headers: runAuth,
    body: JSON.stringify({ from: 'in-progress', to: 'in-review',
      fence: claim.fence, prUrl: 'https://x/pr/1', runId: claim.runId }) });
  assert.equal(r.status, 200);

  server.close(); await pool.end();
});

test('drill 4: illegal transition → 409 legality error; board never shows it', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  await fetch(`${base}/tickets`, { method: 'POST', headers: admin,
    body: JSON.stringify({ id: 't1' }) });
  const r = await fetch(`${base}/tickets/t1/transition`, { method: 'POST',
    headers: admin, body: JSON.stringify({ from: 'backlog', to: 'done' }) });
  assert.equal(r.status, 409);
  assert.equal((await j(r)).error, 'illegal-transition');
  const q = await fetch(`${base}/tickets?state=done`, { headers: admin });
  assert.deepEqual(await j(q), []);
  server.close(); await pool.end();
});

test('run token cannot transition a ticket it does not own', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  for (const id of ['t1', 't2']) {
    await fetch(`${base}/tickets`, { method: 'POST', headers: admin,
      body: JSON.stringify({ id }) });
    await fetch(`${base}/tickets/${id}/transition`, { method: 'POST', headers: admin,
      body: JSON.stringify({ from: 'backlog', to: 'ready-for-agent' }) });
  }
  const claim = await j(await fetch(`${base}/claims`, { method: 'POST', headers: admin }));
  const otherId = claim.ticketId === 't1' ? 't2' : 't1';
  const r = await fetch(`${base}/tickets/${otherId}/transition`, { method: 'POST',
    headers: { 'authorization': `Bearer ${claim.token}`,
               'content-type': 'application/json' },
    body: JSON.stringify({ from: 'ready-for-agent', to: 'in-progress',
      fence: claim.fence, runId: claim.runId }) });
  assert.equal(r.status, 403);
  assert.equal((await j(r)).error, 'not-your-ticket');
  server.close(); await pool.end();
});

test('auth walls: no key → 401; run token cannot use admin routes', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  let r = await fetch(`${base}/claims`, { method: 'POST' });
  assert.equal(r.status, 401);
  r = await fetch(`${base}/tickets?state=backlog`,
    { headers: { authorization: 'Bearer not-admin' } });
  assert.equal(r.status, 401);
  server.close(); await pool.end();
});

test('empty queue claim → 204', async () => {
  const pool = await testPool();
  const { server, base } = await start(pool);
  const r = await fetch(`${base}/claims`, { method: 'POST', headers: admin });
  assert.equal(r.status, 204);
  server.close(); await pool.end();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test` — Expected: FAIL, `makeServer` not found.

- [ ] **Step 3: Implement server.js**

```js
// infra/a0/board-service/src/server.js
import http from 'node:http';
import { makePool, withTx, applySchema } from './db.js';
import { transition } from './transitions.js';
import { claimNext } from './claims.js';
import { appendEvent, addComment, endRun } from './events.js';
import { reclaimStale } from './reconcile.js';
import { verifyAdmin, verifyRunToken } from './auth.js';

async function body(req) {
  let raw = '';
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}
function send(res, code, obj) {
  res.writeHead(code, { 'content-type': 'application/json' });
  res.end(obj === undefined ? '' : JSON.stringify(obj));
}
function bearer(req) {
  return (req.headers['authorization'] ?? '').replace(/^Bearer /, '');
}

export function makeServer(pool) {
  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://x');
      const p = url.pathname.split('/').filter(Boolean);
      const isAdmin = verifyAdmin(req);

      // POST /tickets
      if (req.method === 'POST' && p.length === 1 && p[0] === 'tickets') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        const b = await body(req);
        await pool.query(
          `insert into ticket (id, payload) values ($1, $2)`,
          [b.id, b.payload ?? {}]);
        return send(res, 201, { id: b.id, state: 'backlog' });
      }

      // POST /tickets/:id/transition
      if (req.method === 'POST' && p.length === 3 && p[0] === 'tickets'
          && p[2] === 'transition') {
        const b = await body(req);
        if (!isAdmin) {
          const okRun = b.runId && b.fence != null
            && await verifyRunToken(pool, b.runId, bearer(req));
          if (!okRun) return send(res, 401, { error: 'unauthorized' });
          const owns = await pool.query(
            `select 1 from run where id = $1 and ticket_id = $2`,
            [b.runId, p[1]]);
          if (owns.rowCount === 0)
            return send(res, 403, { error: 'not-your-ticket' });
        }
        const out = await withTx(pool, c => transition(c, {
          ticketId: p[1], from: b.from, to: b.to,
          fence: isAdmin ? (b.fence ?? null) : b.fence,
          prUrl: b.prUrl ?? null, parkNote: b.parkNote ?? null }));
        return send(res, out.ok ? 200 : 409, out);
      }

      // POST /claims
      if (req.method === 'POST' && p.length === 1 && p[0] === 'claims') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        const c = await claimNext(pool, {});
        return c ? send(res, 200, c) : send(res, 204);
      }

      // POST /runs/:id/events
      if (req.method === 'POST' && p.length === 3 && p[0] === 'runs'
          && p[2] === 'events') {
        if (!(await verifyRunToken(pool, p[1], bearer(req))))
          return send(res, 401, { error: 'unauthorized' });
        const b = await body(req);
        const out = await appendEvent(pool, { runId: p[1], kind: b.kind, body: b.body });
        return send(res, out.ok ? 200 : 409, out);
      }

      // POST /runs/:id/end
      if (req.method === 'POST' && p.length === 3 && p[0] === 'runs'
          && p[2] === 'end') {
        const okRun = await verifyRunToken(pool, p[1], bearer(req));
        if (!isAdmin && !okRun) return send(res, 401, { error: 'unauthorized' });
        const b = await body(req);
        const out = await endRun(pool, { runId: p[1], reason: b.reason });
        return send(res, out.ok ? 200 : 409, out);
      }

      // POST /tickets/:id/comments
      if (req.method === 'POST' && p.length === 3 && p[0] === 'tickets'
          && p[2] === 'comments') {
        const b = await body(req);
        const okRun = b.runId && await verifyRunToken(pool, b.runId, bearer(req));
        if (!isAdmin && !okRun) return send(res, 401, { error: 'unauthorized' });
        const out = await addComment(pool, {
          ticketId: p[1], runId: b.runId ?? null, body: b.body });
        return send(res, 201, out);
      }

      // GET /tickets?state=
      if (req.method === 'GET' && p.length === 1 && p[0] === 'tickets') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        const state = url.searchParams.get('state');
        const { rows } = await pool.query(
          state
            ? { text: `select id, state, owner_run, fence, pr_url, park_note
                       from ticket where state = $1 order by updated_at`,
                values: [state] }
            : { text: `select id, state, owner_run, fence, pr_url, park_note
                       from ticket order by updated_at`, values: [] });
        return send(res, 200, rows);
      }

      // POST /reconcile
      if (req.method === 'POST' && p.length === 1 && p[0] === 'reconcile') {
        if (!isAdmin) return send(res, 401, { error: 'unauthorized' });
        return send(res, 200, { reclaimed: await reclaimStale(pool) });
      }

      return send(res, 404, { error: 'not-found' });
    } catch (e) {
      return send(res, 500, { error: 'internal', detail: String(e.message) });
    }
  });
}

export async function main() {
  const pool = makePool(process.env.DATABASE_URL);
  await applySchema(pool);
  const server = makeServer(pool);
  server.listen(Number(process.env.PORT ?? 8080), () =>
    console.log(`a0 board service on :${process.env.PORT ?? 8080}`));
}

if (import.meta.url === `file://${process.argv[1]}`) await main();
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test` — Expected: PASS, all files.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/board-service/src/server.js infra/a0/board-service/test/server.test.js
git commit -m "feat(a0): board service HTTP surface — claim/transition/events/comments/query/reconcile"
```

---

### Task 8: Deployment artifacts (Render default, Fly alternate) + README

**Files:**
- Create: `infra/a0/board-service/Dockerfile`,
  `infra/a0/board-service/render.yaml`, `infra/a0/README.md`

**Interfaces:**
- Consumes: `main()` (Task 7); env contract `DATABASE_URL`, `A0_ADMIN_KEY`, `PORT`.

- [ ] **Step 1: Write Dockerfile and render.yaml**

```dockerfile
# infra/a0/board-service/Dockerfile
# Build context is infra/a0/ (one level up), so schema.sql lands where
# db.js resolves it: docker build -f board-service/Dockerfile infra/a0/
FROM node:22-slim
WORKDIR /app/board-service
COPY board-service/package.json ./
RUN npm install --omit=dev
COPY board-service/src ./src
COPY schema.sql ../schema.sql
ENV NODE_ENV=production
CMD ["node", "src/server.js"]
```

```yaml
# infra/a0/board-service/render.yaml
services:
  - type: web
    name: a0-board-service
    runtime: docker
    dockerfilePath: ./board-service/Dockerfile
    dockerContext: ..
    plan: starter
    numInstances: 2
    envVars:
      - key: DATABASE_URL
        sync: false          # set in dashboard: Supabase transaction-pooler URL (spec §2/§5)
      - key: A0_ADMIN_KEY
        sync: false
```

- [ ] **Step 2: Write infra/a0/README.md**

```markdown
# A0 infrastructure — board service (Plan 1 of 4)

Implements spec §1/§2/§4 core:
`docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md`.

## Run locally
docker run -d --name a0-pg -e POSTGRES_PASSWORD=a0 -p 54329:5432 postgres:16
cd board-service && npm install && npm test
A0_ADMIN_KEY=dev DATABASE_URL=postgres://postgres:a0@localhost:54329/postgres npm start

## Env contract
- DATABASE_URL — Supabase transaction-mode pooler URL in prod (direct
  connections are reserved for the future resident controller; spec §2
  pooling placement rule)
- A0_ADMIN_KEY — dispatcher/human credential; NEVER given to workers
- Workers hold only their per-run bearer token from POST /claims

## Endpoints
claim / transition (park = transition to a park state with parkNote) /
comments / runs-events (heartbeat) / tickets query / reconcile — see
src/server.js routes.
```

- [ ] **Step 3: Verify the container builds and boots**

Run: `docker build -t a0-board -f infra/a0/board-service/Dockerfile infra/a0/ && docker run --rm -e A0_ADMIN_KEY=dev -e DATABASE_URL=postgres://postgres:a0@host.docker.internal:54329/postgres -p 8080:8080 a0-board &` then
`sleep 3 && curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8080/claims -H 'Authorization: Bearer dev'`
Expected: `204` (empty queue) — then stop the container.

- [ ] **Step 4: Commit**

```bash
git add infra/a0/board-service/Dockerfile infra/a0/board-service/render.yaml infra/a0/README.md
git commit -m "feat(a0): deployment artifacts — Docker + Render blueprint, env contract"
```

---

### Task 9: Final verification — spec acceptance drills covered by this plan

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run (from `infra/a0/board-service/`): `npm test`
Expected: all tests PASS.

- [ ] **Step 2: Execute the spec's acceptance items this plan owns, as written**

From spec `## Acceptance (behavior-phrased)`:

> 1. Two workers racing one ready ticket: exactly one claim succeeds; the
>    loser observes rows-affected=0 and walks away without a wasted run.

Covered by `claims.test.js` "drill 1" — re-run and confirm:
`node --test test/claims.test.js` → PASS.

> 2. A worker killed mid-run: within one reconciler tick its lease is
>    reclaimed, the run resumes from the session log on a fresh sandbox, and
>    the superseded sandbox's late writes are refused by fencing token.

Fencing/reclaim half covered by `reconcile.test.js` "drill 2 fencing" —
re-run and confirm: `node --test test/reconcile.test.js` → PASS. (The
"resumes on a fresh sandbox" half belongs to Plan 3.)

> 4. An illegal transition submitted directly to the board service returns a
>    legality error; no illegal state is ever observable in the board [...]

Covered by `server.test.js` "drill 4" → PASS. (The Linear-mirror half
belongs to Plan 4.)

> 10. The board service down for an hour: workers fail closed (no local
>     claims) [...]

Structural here: workers can only claim via `POST /claims`; with the
service down there is no other write path (workers hold no DB credential —
verify by inspection that no worker-facing artifact in this plan contains
`DATABASE_URL`). Full drill lands with Plans 3–4.

- [ ] **Step 3: Record coverage in the spec's living tail**

Append to the spec `## Revision Notes`:

```
- <date>: Plan 1 (a0-core-board-service) implemented — acceptance 1, 2
  (fencing half), 4 (service half) verified by test; 10 structurally
  satisfied pending Plans 3–4.
```

- [ ] **Step 4: Commit**

```bash
git add docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "docs(a0): record Plan 1 acceptance coverage in spec living tail"
```
