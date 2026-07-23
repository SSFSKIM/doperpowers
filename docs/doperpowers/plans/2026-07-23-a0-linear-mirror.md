# A0 Linear Mirror — One-Way Authority, Two-Way Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the spec §1 Linear mirror: a coalesced one-way projection of
board state into Linear for humans (poll-forward with per-ticket debouncing
and a rate-budget guard), plus the back-edge — human edits in Linear arrive
as signed webhook events and are applied through the board's legality check,
with the board always winning conflicts — plus spike T3 (Linear
per-endpoint mutation caps: support email + controlled load test).

**Architecture:** One small Node process beside the board service. The
forward edge polls `GET /tickets` on the board (env `MIRROR_POLL_MS`) and
projects each ticket through `STATE_MAP` into a Linear workflow-state name;
agent-churn states (`backlog`/`ready-for-agent`/`in-progress`) collapse
into one "In Progress" lane so most of the ~8 board writes/run produce zero
Linear traffic. Changed tickets mirror only after `MIRROR_DEBOUNCE_MS` of
quiet — except human-blocking states (parks, `confident-ready`), which jump
the debounce. All Linear writes pass a token bucket capped at
`MIRROR_MAX_PER_HOUR`. The back-edge is a webhook receiver that validates
Linear's `Linear-Signature` HMAC, maps a human's issue-state change to a
`POST /tickets/:id/transition` attempt, and on 409 reverts the Linear issue
to the board's current state. Because Linear drops a webhook delivery after
3 failed retries with no ordering guarantee, a periodic batched reconcile
(`reconcileOnce`) is the drop-proof backstop. The mirror is stateless
across restarts by design — no DB, no local file: the board is the SSOT and
everything the mirror knows is re-derived by full comparison at boot.

**Tech Stack:** Node 22 (ESM, `node:http`, `node:test`, `node:crypto`,
built-in `fetch`). Zero npm dependencies. All tests run against an
in-process fake Linear GraphQL server — never the real API; the only
real-API touchpoints live in the T3 spike task behind a safety latch.

**Plan slicing (this is Plan 4 of 4 for the spec):**
1. Plan 1 (`2026-07-23-a0-core-board-service.md`) — board service + claim path. DONE first; this plan consumes its HTTP surface.
2. Plan 2 — reconciler cron + breakers + cost meter + Slack outbox.
3. Plan 3 — substrate adapter + E2B dispatch + secrets placement.
4. **This plan** — Linear mirror (spec §1 mirror paragraph) + spike T3.

## Global Constraints

- Node ≥ 22 (built-in test runner, ESM, global `fetch`). **Zero npm
  dependencies** — plain `fetch` for both Linear GraphQL and board HTTP.
- The 9 board states are frozen (Plan 1 Global Constraints). `STATE_MAP` is
  a *projection* of them into Linear lane names — it never adds, renames,
  or reinterprets a board state.
- **One-way authority:** the mirror never writes board state except by
  `POST /tickets/:id/transition` through the board's legality check; every
  conflict resolves to the board. The mirror may freely overwrite Linear
  (Linear is a view).
- **Credential note (accepted simplification, stated honestly):** at A0 the
  mirror authenticates to the board with `A0_ADMIN_KEY` — there is no third
  credential tier yet. The future split is a dedicated **mirror key**
  scoped to {`GET /tickets`, human-legal transitions}; named in the README
  and left for the post-A0 hardening pass. Workers never hold either key.
- Tests NEVER touch the real Linear API. The fake GraphQL server
  (`test/fakes.js`) is the only Linear the test suite sees. The T3 probe
  (`tools/t3-rate-probe.mjs`) is the only real-API artifact and refuses to
  run without `LINEAR_TEST_TEAM_ID` (throwaway team latch).
- Clocks are injectable (`now` parameters on the bucket and sync) so
  debounce/budget tests are deterministic — no `setTimeout` sleeps in
  tests.
- Scope boundaries: **no board-service source or schema changes** (its
  pure legality table is *imported* by the test fakes, read-only); no
  dispatcher/E2B (Plan 3); no breakers (Plan 2).
- Linear webhook facts this plan builds on (verified against
  linear.app/developers/webhooks, 2026-07-23): signature header is
  **`Linear-Signature`**, hex-encoded HMAC-SHA256 of the raw request body
  under the webhook signing secret; payload carries `webhookTimestamp`
  (Unix ms) with a recommended ~1-minute replay window; failed deliveries
  retry after 1 minute, 1 hour, 6 hours, then **drop** — no ordering
  guarantee.

## File Structure

```
infra/a0/
  mirror/
    package.json                 — name, type:module, zero deps
    README.md                    — env table, mirrored-team checklist, actor math
    render.yaml                  — Render blueprint (web service: webhook needs ingress)
    src/board-client.js          — thin client for the Plan 1 board HTTP surface
    src/linear-client.js         — minimal GraphQL client + STATE_MAP + [a0:] marker
    src/sync.js                  — syncOnce / reconcileOnce / makeBucket / makeSyncState
    src/backedge.js              — webhook receiver: verify, legality-gated apply, revert
    src/main.js                  — wires poll loop + reconcile loop + webhook server
    test/fakes.js                — in-process fake Linear GraphQL + fake board
    test/linear-client.test.js
    test/sync.test.js
    test/backedge.test.js
    test/e2e.test.js             — main wiring, property test, real-board opt-in drill
    tools/t3-support-email.md    — T3 spike: support disclosure request (draft)
    tools/t3-rate-probe.mjs      — T3 spike: controlled issueUpdate burst, header capture
```

---

### Task 1: Package scaffold + test fakes (fake Linear GraphQL, fake board)

The fakes are the test substrate for every later task, so they come first
and get their own smoke tests. The fake board reuses the REAL legality
table from Plan 1 (`isLegal`/`PARK_STATES` are pure exports — no pg, no
side effects), so back-edge tests exercise the true transition rules, not
a parallel reimplementation.

**Files:**
- Create: `infra/a0/mirror/package.json`, `infra/a0/mirror/test/fakes.js`,
  `infra/a0/mirror/test/fakes.test.js`

**Interfaces:**
- Consumes: `isLegal(from, to)`, `PARK_STATES` from
  `infra/a0/board-service/src/transitions.js` (Plan 1, read-only import).
- Produces:
  - `makeFakeLinear()` → `{url, issues: Map(issueId → {id, title,
    stateName}), writes: [{issueId, stateName}], comments: [{issueId,
    body}], requests (getter), setIssueState(id, stateName), close()}` —
    `writes` records EVERY state ever written (create + update), the
    observation channel for the property test.
  - `makeFakeBoard({adminKey='test-admin'})` → `{url, adminKey,
    tickets: Map(id → {id, state, owner_run, fence, pr_url, park_note}),
    down (settable boolean → 503s), addTicket(id, state),
    setState(id, state), close()}` — implements `GET /tickets?state=` and
    `POST /tickets/:id/transition` with Plan 1's status/error contract
    (200 `{ok:true}` / 409 `{error:'illegal-transition'|'lost-race'|
    'park-note-required'}` / 401).

- [ ] **Step 1: Write package.json**

```json
{
  "name": "a0-mirror",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22" },
  "scripts": { "test": "node --test test/", "start": "node src/main.js" }
}
```

- [ ] **Step 2: Write failing smoke tests for the fakes**

```js
// infra/a0/mirror/test/fakes.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { makeFakeLinear, makeFakeBoard, TEAM_STATES } from './fakes.js';

test('fake linear answers workflowStates, create, update, search, comment', async () => {
  const fl = await makeFakeLinear();
  const gql = (query, variables) => fetch(fl.url, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ query, variables }) }).then(r => r.json());

  const ws = await gql(`query { workflowStates { nodes { id name } } }`, {});
  assert.deepEqual(ws.data.workflowStates.nodes.map(n => n.name), TEAM_STATES);

  const created = await gql(
    `mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id } } }`,
    { input: { teamId: 'team-1', title: '[a0:t1] hello', stateId: 'ws-0' } });
  const id = created.data.issueCreate.issue.id;
  assert.equal(fl.issues.get(id).stateName, 'In Progress');
  assert.deepEqual(fl.writes, [{ issueId: id, stateName: 'In Progress' }]);

  await gql(
    `mutation($id: String!, $input: IssueUpdateInput!) { issueUpdate(id: $id, input: $input) { success } }`,
    { id, input: { stateId: 'ws-6' } });
  assert.equal(fl.issues.get(id).stateName, 'Done');
  assert.equal(fl.writes.length, 2);

  const found = await gql(
    `query($needle: String!) { issues(filter: { title: { contains: $needle } }, first: 200) { nodes { id title state { name } } } }`,
    { needle: '[a0:t1]' });
  assert.equal(found.data.issues.nodes.length, 1);

  await gql(
    `mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success } }`,
    { input: { issueId: id, body: 'hi' } });
  assert.deepEqual(fl.comments, [{ issueId: id, body: 'hi' }]);
  fl.close();
});

test('fake board enforces the real legality table and auth', async () => {
  const fb = await makeFakeBoard({});
  const admin = { 'authorization': 'Bearer test-admin',
                  'content-type': 'application/json' };
  fb.addTicket('t1', 'backlog');

  let r = await fetch(`${fb.url}/tickets`, { headers: admin });
  assert.equal(r.status, 200);
  assert.equal((await r.json())[0].state, 'backlog');

  r = await fetch(`${fb.url}/tickets`, { headers: { authorization: 'Bearer nope' } });
  assert.equal(r.status, 401);

  r = await fetch(`${fb.url}/tickets/t1/transition`, { method: 'POST', headers: admin,
    body: JSON.stringify({ from: 'backlog', to: 'done' }) });
  assert.equal(r.status, 409);
  assert.equal((await r.json()).error, 'illegal-transition');
  assert.equal(fb.tickets.get('t1').state, 'backlog');

  r = await fetch(`${fb.url}/tickets/t1/transition`, { method: 'POST', headers: admin,
    body: JSON.stringify({ from: 'ready-for-agent', to: 'in-progress' }) });
  assert.equal(r.status, 409);
  assert.equal((await r.json()).error, 'lost-race');

  r = await fetch(`${fb.url}/tickets/t1/transition`, { method: 'POST', headers: admin,
    body: JSON.stringify({ from: 'backlog', to: 'ready-for-agent' }) });
  assert.equal(r.status, 200);
  assert.equal(fb.tickets.get('t1').state, 'ready-for-agent');

  fb.down = true;
  r = await fetch(`${fb.url}/tickets`, { headers: admin });
  assert.equal(r.status, 503);
  fb.close();
});
```

- [ ] **Step 3: Run to verify failure**

Run (from `infra/a0/mirror/`): `npm test`
Expected: FAIL — `Cannot find module './fakes.js'`.

- [ ] **Step 4: Implement the fakes**

```js
// infra/a0/mirror/test/fakes.js
// In-process fakes. The fake Linear speaks exactly the GraphQL subset the
// client under test issues (matched by substring — this is a test double,
// not a GraphQL engine). The fake board reuses the REAL legality table
// from Plan 1 (pure import, no pg), so back-edge tests exercise the true
// rules. Its `down` flag simulates a board outage with 503s.
import http from 'node:http';
import { isLegal, PARK_STATES } from '../../board-service/src/transitions.js';

export const TEAM_STATES = ['In Progress', 'In Review', 'Needs Human',
  'Needs Info', 'Interactive Preferred', 'Confident Ready', 'Done'];

export async function makeFakeLinear() {
  const issues = new Map();   // issueId -> { id, title, stateName }
  const writes = [];          // every state ever written (create + update)
  const comments = [];
  let nextId = 1;
  let requests = 0;
  const stateNameById = (id) => TEAM_STATES[Number(id.replace('ws-', ''))];

  const server = http.createServer(async (req, res) => {
    let raw = '';
    for await (const c of req) raw += c;
    requests++;
    const { query, variables: v = {} } = JSON.parse(raw);
    const send = (data) => {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ data }));
    };
    if (query.includes('workflowStates')) {
      return send({ workflowStates: { nodes:
        TEAM_STATES.map((name, i) => ({ id: `ws-${i}`, name })) } });
    }
    if (query.includes('issueCreate')) {
      const id = `issue-${nextId++}`;
      const stateName = stateNameById(v.input.stateId);
      issues.set(id, { id, title: v.input.title, stateName });
      writes.push({ issueId: id, stateName });
      return send({ issueCreate: { success: true, issue: { id } } });
    }
    if (query.includes('issueUpdate')) {
      const issue = issues.get(v.id);
      issue.stateName = stateNameById(v.input.stateId);
      writes.push({ issueId: v.id, stateName: issue.stateName });
      return send({ issueUpdate: { success: true } });
    }
    if (query.includes('commentCreate')) {
      comments.push({ issueId: v.input.issueId, body: v.input.body });
      return send({ commentCreate: { success: true } });
    }
    if (query.includes('issues(')) {
      const nodes = [...issues.values()]
        .filter(i => i.title.includes(v.needle))
        .map(i => ({ id: i.id, title: i.title, state: { name: i.stateName } }));
      return send({ issues: { nodes } });
    }
    res.writeHead(400);
    res.end('unhandled query: ' + query.slice(0, 80));
  });
  await new Promise(r => server.listen(0, r));
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    issues, writes, comments,
    get requests() { return requests; },
    setIssueState(id, stateName) { issues.get(id).stateName = stateName; },
    close: () => server.close(),
  };
}

export async function makeFakeBoard({ adminKey = 'test-admin' } = {}) {
  const tickets = new Map(); // id -> {id, state, owner_run, fence, pr_url, park_note}
  const fake = {
    adminKey, tickets, down: false,
    addTicket(id, state) {
      tickets.set(id, { id, state, owner_run: null, fence: 0,
                        pr_url: null, park_note: null });
    },
    setState(id, state) { tickets.get(id).state = state; },
  };
  const server = http.createServer(async (req, res) => {
    const send = (code, obj) => {
      res.writeHead(code, { 'content-type': 'application/json' });
      res.end(JSON.stringify(obj));
    };
    if (fake.down) return send(503, { error: 'down' });
    if ((req.headers['authorization'] ?? '') !== `Bearer ${adminKey}`)
      return send(401, { error: 'unauthorized' });
    const url = new URL(req.url, 'http://x');
    const p = url.pathname.split('/').filter(Boolean);
    if (req.method === 'GET' && p.length === 1 && p[0] === 'tickets') {
      const s = url.searchParams.get('state');
      return send(200, [...tickets.values()].filter(t => !s || t.state === s));
    }
    if (req.method === 'POST' && p.length === 3 && p[0] === 'tickets'
        && p[2] === 'transition') {
      let raw = '';
      for await (const c of req) raw += c;
      const b = JSON.parse(raw);
      const t = tickets.get(p[1]);
      if (!isLegal(b.from, b.to)) return send(409, { error: 'illegal-transition' });
      if (PARK_STATES.includes(b.to) && !b.parkNote)
        return send(409, { error: 'park-note-required' });
      if (!t || t.state !== b.from) return send(409, { error: 'lost-race' });
      t.state = b.to;
      if (b.prUrl) t.pr_url = b.prUrl;
      t.park_note = PARK_STATES.includes(b.to) ? b.parkNote : null;
      return send(200, { ok: true });
    }
    return send(404, { error: 'not-found' });
  });
  await new Promise(r => server.listen(0, r));
  fake.url = `http://127.0.0.1:${server.address().port}`;
  fake.close = () => server.close();
  return fake;
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `npm test`
Expected: PASS — both fakes tests green.

- [ ] **Step 6: Commit**

```bash
git add infra/a0/mirror/package.json infra/a0/mirror/test/fakes.js infra/a0/mirror/test/fakes.test.js
git commit -m "feat(a0-mirror): scaffold + test fakes — in-process Linear GraphQL, board with real legality table"
```

---

### Task 2: Linear GraphQL client + STATE_MAP (the coalesced projection)

**Files:**
- Create: `infra/a0/mirror/src/linear-client.js`,
  `infra/a0/mirror/test/linear-client.test.js`

**Interfaces:**
- Consumes: fake Linear (Task 1) in tests; env `LINEAR_URL`,
  `LINEAR_TOKEN`, `LINEAR_TEAM_ID`, `LINEAR_STATE_MAP`.
- Produces:
  - `STATE_MAP` — board state → Linear workflow-state NAME (all 9 states;
    env-overridable); `loadStateMap()` (re-reads env, exported for tests);
    `HUMAN_RELEVANT` — the 6 states that move an issue between lanes.
  - `marker(ticketId)` → `` `[a0:${ticketId}]` `` and
    `ticketIdFromTitle(title)` → `ticketId | null`.
  - `makeLinear({url='https://api.linear.app/graphql', token, teamId})` →
    `{ stateIdFor(stateName) → id,
       findIssueByTicketId(ticketId) → {issueId, stateName} | null,
       listMirroredIssues() → [{issueId, ticketId, stateName}],
       createIssue({ticketId, title, stateName}) → {issueId},
       updateIssueState(issueId, stateName) → {ok:true},
       comment(issueId, body) → {ok:true} }`.

**Conventions this task pins down:**
- **Ticket↔issue linkage:** every mirrored issue's title starts with the
  marker `[a0:<ticketId>]`. The marker is the join key; Linear issue IDs
  are never persisted anywhere (stateless mirror — the board is the SSOT,
  everything else derives).
- **Coalescing rationale (the spec's ~2–3-of-8):**
  `backlog`/`ready-for-agent`/`in-progress` all map to one "In Progress"
  lane because those transitions are agent churn — claims, bounces, lease
  reclaims, the bulk of the ~8 board writes/run — and carry no human
  decision. A same-lane change therefore produces zero Linear traffic by
  construction; only the 6 `HUMAN_RELEVANT` states generate writes.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/mirror/test/linear-client.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { makeFakeLinear } from './fakes.js';
import { makeLinear, STATE_MAP, loadStateMap, HUMAN_RELEVANT,
         marker, ticketIdFromTitle } from '../src/linear-client.js';

test('STATE_MAP maps all 9 frozen states; agent churn shares one lane', () => {
  const states = ['backlog', 'ready-for-agent', 'in-progress', 'in-review',
    'needs-human', 'needs-info', 'interactive-preferred',
    'confident-ready', 'done'];
  for (const s of states) assert.equal(typeof STATE_MAP[s], 'string');
  assert.equal(new Set([STATE_MAP['backlog'], STATE_MAP['ready-for-agent'],
    STATE_MAP['in-progress']]).size, 1);
  assert.deepEqual(HUMAN_RELEVANT, ['in-review', 'needs-human', 'needs-info',
    'interactive-preferred', 'confident-ready', 'done']);
});

test('LINEAR_STATE_MAP env override merges over defaults', () => {
  process.env.LINEAR_STATE_MAP = JSON.stringify({ done: 'Shipped' });
  const m = loadStateMap();
  delete process.env.LINEAR_STATE_MAP;
  assert.equal(m['done'], 'Shipped');
  assert.equal(m['in-review'], 'In Review');
});

test('marker round-trips through a title', () => {
  assert.equal(marker('t42'), '[a0:t42]');
  assert.equal(ticketIdFromTitle('[a0:t42] Fix flaky test'), 't42');
  assert.equal(ticketIdFromTitle('unrelated issue'), null);
  assert.equal(ticketIdFromTitle(undefined), null);
});

test('client: create → find by marker → update → comment → list', async () => {
  const fl = await makeFakeLinear();
  const linear = makeLinear({ url: fl.url, token: 'tok', teamId: 'team-1' });

  const { issueId } = await linear.createIssue({
    ticketId: 't9', title: 'Fix the flaky test', stateName: 'In Review' });
  assert.ok(fl.issues.get(issueId).title.startsWith('[a0:t9]'));

  const found = await linear.findIssueByTicketId('t9');
  assert.deepEqual(found, { issueId, stateName: 'In Review' });
  assert.equal(await linear.findIssueByTicketId('nope'), null);

  await linear.updateIssueState(issueId, 'Done');
  assert.equal(fl.issues.get(issueId).stateName, 'Done');

  await linear.comment(issueId, 'parked: needs a human decision');
  assert.deepEqual(fl.comments,
    [{ issueId, body: 'parked: needs a human decision' }]);

  assert.deepEqual(await linear.listMirroredIssues(),
    [{ issueId, ticketId: 't9', stateName: 'Done' }]);

  await assert.rejects(() => linear.updateIssueState(issueId, 'No Such Lane'),
    /no Linear workflow state/);
  fl.close();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/linear-client.js'`.

- [ ] **Step 3: Implement**

```js
// infra/a0/mirror/src/linear-client.js
// Minimal Linear GraphQL client — plain fetch, no SDK, no npm deps.
//
// Ticket↔issue linkage convention: every mirrored issue's title starts
// with the marker `[a0:<ticketId>]`. The marker is the join key — Linear
// issue IDs are never stored anywhere. The mirror is stateless across
// restarts by design: the board is the SSOT; everything derives.

// Human-relevant board states — the only ones that move an issue between
// Linear lanes. backlog / ready-for-agent / in-progress all share one
// "In Progress" lane: those transitions are agent churn (claims, bounces,
// lease reclaims — the bulk of the ~8 board writes/run) and carry no
// human decision. Collapsing them is the spec's ~2–3-of-8 coalescing:
// a same-lane change produces zero Linear traffic by construction.
export const HUMAN_RELEVANT = ['in-review', 'needs-human', 'needs-info',
  'interactive-preferred', 'confident-ready', 'done'];

export function loadStateMap() {
  const dflt = {
    'backlog': 'In Progress',
    'ready-for-agent': 'In Progress',
    'in-progress': 'In Progress',
    'in-review': 'In Review',
    'needs-human': 'Needs Human',
    'needs-info': 'Needs Info',
    'interactive-preferred': 'Interactive Preferred',
    'confident-ready': 'Confident Ready',
    'done': 'Done',
  };
  return process.env.LINEAR_STATE_MAP
    ? { ...dflt, ...JSON.parse(process.env.LINEAR_STATE_MAP) }
    : dflt;
}
export const STATE_MAP = loadStateMap();

export const marker = (ticketId) => `[a0:${ticketId}]`;
export function ticketIdFromTitle(title) {
  const m = /\[a0:([^\]]+)\]/.exec(title ?? '');
  return m ? m[1] : null;
}

export function makeLinear({
  url = process.env.LINEAR_URL ?? 'https://api.linear.app/graphql',
  token = process.env.LINEAR_TOKEN,
  teamId = process.env.LINEAR_TEAM_ID,
} = {}) {
  let stateIds = null; // lane name -> workflow-state id, fetched once

  async function gql(query, variables) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'authorization': token },
      body: JSON.stringify({ query, variables }),
    });
    if (!r.ok) throw new Error(`linear http ${r.status}`);
    const out = await r.json();
    if (out.errors) throw new Error(`linear gql: ${JSON.stringify(out.errors)}`);
    return out.data;
  }

  async function stateIdFor(stateName) {
    if (!stateIds) {
      const d = await gql(
        `query($teamId: String!) {
           workflowStates(filter: { team: { id: { eq: $teamId } } }) {
             nodes { id name } } }`, { teamId });
      stateIds = Object.fromEntries(
        d.workflowStates.nodes.map(n => [n.name, n.id]));
    }
    const id = stateIds[stateName];
    if (!id) throw new Error(`no Linear workflow state named '${stateName}'`);
    return id;
  }

  async function searchIssues(needle) {
    const d = await gql(
      `query($needle: String!) {
         issues(filter: { title: { contains: $needle } }, first: 200) {
           nodes { id title state { name } } } }`, { needle });
    return d.issues.nodes;
  }

  return {
    stateIdFor,
    async findIssueByTicketId(ticketId) {
      const hits = await searchIssues(marker(ticketId));
      if (hits.length === 0) return null;
      return { issueId: hits[0].id, stateName: hits[0].state.name };
    },
    async listMirroredIssues() {
      return (await searchIssues('[a0:')).map(i => ({
        issueId: i.id,
        ticketId: ticketIdFromTitle(i.title),
        stateName: i.state.name,
      }));
    },
    async createIssue({ ticketId, title, stateName }) {
      const stateId = await stateIdFor(stateName);
      const d = await gql(
        `mutation($input: IssueCreateInput!) {
           issueCreate(input: $input) { success issue { id } } }`,
        { input: { teamId, title: `${marker(ticketId)} ${title}`, stateId } });
      return { issueId: d.issueCreate.issue.id };
    },
    async updateIssueState(issueId, stateName) {
      const stateId = await stateIdFor(stateName);
      await gql(
        `mutation($id: String!, $input: IssueUpdateInput!) {
           issueUpdate(id: $id, input: $input) { success } }`,
        { id: issueId, input: { stateId } });
      return { ok: true };
    },
    async comment(issueId, body) {
      await gql(
        `mutation($input: CommentCreateInput!) {
           commentCreate(input: $input) { success } }`,
        { input: { issueId, body } });
      return { ok: true };
    },
  };
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — fakes + linear-client tests green.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/mirror/src/linear-client.js infra/a0/mirror/test/linear-client.test.js
git commit -m "feat(a0-mirror): Linear GraphQL client + STATE_MAP coalesced projection with [a0:] marker"
```

---

### Task 3: Forward sync — debounce, park jump, budget bucket, reconcile backstop

**Files:**
- Create: `infra/a0/mirror/src/board-client.js`, `infra/a0/mirror/src/sync.js`,
  `infra/a0/mirror/test/sync.test.js`

**Interfaces:**
- Consumes: `makeLinear`, `STATE_MAP`, `marker` (Task 2); Plan 1 board HTTP
  contract: `GET /tickets` (admin bearer) →
  `[{id, state, owner_run, fence, pr_url, park_note}]`,
  `POST /tickets/:id/transition` → 200/409.
- Produces:
  - `makeBoard({url=env A0_BOARD_URL, adminKey=env A0_ADMIN_KEY})` →
    `{ listTickets() → rows (throws on non-200),
       transition(ticketId, body) → {status, body} }`.
  - `JUMP_STATES` — `['needs-human','needs-info','interactive-preferred',
    'confident-ready']` (human-blocking: park + landable — the spec's
    "Action-next-work-block" spirit; these skip the debounce).
  - `makeBucket({maxPerHour=env MIRROR_MAX_PER_HOUR ?? 2500, now})` →
    `{ take({force=false, now}) → boolean, skipped }` — token bucket,
    hourly refill rate; `force` (parks/reverts) always passes and may
    drive the balance negative (debt repaid by refill); non-forced takes
    on an empty bucket return false and increment `skipped`.
  - `makeSyncState()` → `Map(ticketId → {issueId, mirrored, dirtyAt})`.
  - `syncOnce({board, linear, state, bucket, now=Date.now(),
    debounceMs=env MIRROR_DEBOUNCE_MS ?? 5000})` →
    `{created, written, skipped, deferred}`.
  - `reconcileOnce({board, linear, state, bucket, now=Date.now()})` →
    `{reverted}` — the drop-proof backstop: one batched Linear read,
    revert any Linear-side drift to the board's state.

**Design notes to carry into the code comments:**
- Polling is deliberate: webhooks are the back-edge, but Linear drops a
  delivery after 3 failed retries with no ordering guarantee, so a
  periodic full poll is required anyway (research doc §2.1) — and once you
  must poll, polling as the forward edge keeps one code path.
- Stateless across restarts BY DESIGN: no DB, no local file. `state` is a
  pure in-memory cache rebuilt by full comparison on first sight of each
  ticket (`findIssueByTicketId`). Losing it costs at most one extra Linear
  read per ticket. Why: the board is the SSOT; the mirror derives
  everything, so persisting mirror state would only create a second thing
  to reconcile.
- Budget guard default 2500/hr = 50% of one OAuth App-User actor's
  5,000/hr — headroom for the back-edge reverts, reconcile reads, and a
  human margin. When exhausted, coalesce harder: skip non-park updates
  (they stay dirty and retry next tick) and count skips.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/mirror/test/sync.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { makeFakeLinear, makeFakeBoard } from './fakes.js';
import { makeLinear } from '../src/linear-client.js';
import { makeBoard } from '../src/board-client.js';
import { makeBucket, makeSyncState, syncOnce, reconcileOnce }
  from '../src/sync.js';

async function rig({ maxPerHour = 100000 } = {}) {
  const fl = await makeFakeLinear();
  const fb = await makeFakeBoard({});
  return {
    fl, fb,
    linear: makeLinear({ url: fl.url, token: 'tok', teamId: 'team-1' }),
    board: makeBoard({ url: fb.url, adminKey: 'test-admin' }),
    state: makeSyncState(),
    bucket: makeBucket({ maxPerHour, now: 0 }),
    close() { fl.close(); fb.close(); },
  };
}

test('create-on-first-sight: new ticket gets an issue with the [a0:] marker', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'backlog');
  const out = await syncOnce({ ...r, now: 0 });
  assert.equal(out.created, 1);
  const issue = [...r.fl.issues.values()][0];
  assert.ok(issue.title.startsWith('[a0:t1]'));
  assert.equal(issue.stateName, 'In Progress');
  r.close();
});

test('agent churn coalesces: backlog→ready→in-progress adds zero writes', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'backlog');
  await syncOnce({ ...r, now: 0 });
  const before = r.fl.writes.length; // 1 — the create
  let now = 0;
  for (const s of ['ready-for-agent', 'in-progress']) {
    r.fb.setState('t1', s);
    now += 60000;
    await syncOnce({ ...r, now });
  }
  assert.equal(r.fl.writes.length, before);
  r.close();
});

test('debounce: fast consecutive changes → one Linear write, final state only', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'in-progress');
  await syncOnce({ ...r, now: 0 });          // create in the In Progress lane
  const before = r.fl.writes.length;
  r.fb.setState('t1', 'in-review');
  await syncOnce({ ...r, now: 1000 });       // dirty, inside debounce
  r.fb.setState('t1', 'done');
  await syncOnce({ ...r, now: 2000 });       // still inside debounce
  assert.equal(r.fl.writes.length, before);  // nothing mirrored yet
  await syncOnce({ ...r, now: 7000 });       // 7000-1000 ≥ 5000 → flush once
  assert.equal(r.fl.writes.length, before + 1);
  assert.equal(r.fl.writes.at(-1).stateName, 'Done'); // 'In Review' never shown
  r.close();
});

test('park jumps the debounce: needs-human mirrors immediately', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'in-progress');
  await syncOnce({ ...r, now: 0 });
  r.fb.setState('t1', 'needs-human');
  const out = await syncOnce({ ...r, now: 100 }); // well inside the 5000ms window
  assert.equal(out.written, 1);
  assert.equal(r.fl.writes.at(-1).stateName, 'Needs Human');
  r.close();
});

test('budget guard: exhausted bucket skips non-park writes; park forces through', async () => {
  const r = await rig({ maxPerHour: 1 });
  r.fb.addTicket('t1', 'in-progress');
  r.fb.addTicket('t2', 'in-progress');
  await syncOnce({ ...r, now: 0 });       // t1 create takes the only token; t2 skipped
  assert.equal(r.bucket.skipped, 1);
  assert.equal(r.fl.issues.size, 1);
  r.fb.setState('t1', 'needs-human');     // human-blocking: forced despite empty bucket
  const out = await syncOnce({ ...r, now: 10 });
  assert.equal(out.written, 1);
  assert.equal(r.fl.writes.at(-1).stateName, 'Needs Human');
  assert.equal(r.bucket.skipped, 2);      // t2 create skipped again
  r.close();
});

test('reconcile backstop: Linear-side drift reverts to the board state', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'in-progress');
  await syncOnce({ ...r, now: 0 });
  const issueId = [...r.fl.issues.keys()][0];
  r.fl.setIssueState(issueId, 'Done');    // human edit whose webhook was dropped
  const out = await reconcileOnce({ ...r, now: 1000 });
  assert.equal(out.reverted, 1);
  assert.equal(r.fl.issues.get(issueId).stateName, 'In Progress');
  r.close();
});

test('board down: sync fails closed, Linear keeps last mirrored state; recovery is normal ticks', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'confident-ready');
  await syncOnce({ ...r, now: 0 });
  const frozen = [...r.fl.issues.values()][0].stateName;
  assert.equal(frozen, 'Confident Ready');

  r.fb.down = true;
  await assert.rejects(() => syncOnce({ ...r, now: 60000 }));
  assert.equal([...r.fl.issues.values()][0].stateName, frozen); // humans still read it

  r.fb.tickets.get('t1').state = 'done';  // change from just before the outage
  r.fb.down = false;
  await syncOnce({ ...r, now: 120000 });  // first tick after recovery: marks dirty
  await syncOnce({ ...r, now: 130000 });  // debounce elapsed → converged
  assert.equal([...r.fl.issues.values()][0].stateName, 'Done');
  r.close();
});

test('boot rebuild: existing in-sync issue produces no write; drifted issue is fixed', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'in-review');
  await syncOnce({ ...r, now: 0 });                      // creates in 'In Review'
  const writesBefore = r.fl.writes.length;
  const state2 = makeSyncState();                        // simulate a mirror restart
  await syncOnce({ ...r, state: state2, now: 10000 });
  assert.equal(r.fl.writes.length, writesBefore);        // in sync → no write
  const issueId = [...r.fl.issues.keys()][0];
  r.fl.setIssueState(issueId, 'Done');                   // drift while restarted
  const state3 = makeSyncState();
  await syncOnce({ ...r, state: state3, now: 20000 });   // differs → overdue now
  assert.equal(r.fl.issues.get(issueId).stateName, 'In Review');
  r.close();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/board-client.js'`.

- [ ] **Step 3: Implement board-client.js and sync.js**

```js
// infra/a0/mirror/src/board-client.js
// Thin client for the Plan 1 board service HTTP surface. At A0 the mirror
// authenticates with A0_ADMIN_KEY — an accepted simplification (no third
// credential tier yet). The future split is a dedicated "mirror key"
// scoped to {GET /tickets, human-legal transitions}; see README. Workers
// never hold either key.
export function makeBoard({ url = process.env.A0_BOARD_URL,
                            adminKey = process.env.A0_ADMIN_KEY } = {}) {
  const headers = { 'authorization': `Bearer ${adminKey}`,
                    'content-type': 'application/json' };
  return {
    async listTickets() {
      const r = await fetch(`${url}/tickets`, { headers });
      if (!r.ok) throw new Error(`board list failed: ${r.status}`);
      return r.json();
    },
    async transition(ticketId, body) {
      const r = await fetch(`${url}/tickets/${ticketId}/transition`,
        { method: 'POST', headers, body: JSON.stringify(body) });
      return { status: r.status, body: await r.json() };
    },
  };
}
```

```js
// infra/a0/mirror/src/sync.js
// Forward edge: board → Linear, poll-based. Polling is deliberate — the
// webhook back-edge covers human edits, but Linear drops a delivery after
// 3 failed retries (1 min / 1 hr / 6 hrs) with no ordering guarantee, so
// a periodic full poll is the required backstop; once you must poll
// anyway, polling as the forward edge keeps one code path.
//
// Stateless across restarts BY DESIGN: no DB, no local file. The board is
// the SSOT; `state` is a pure in-memory cache rebuilt by full comparison
// on first sight of each ticket. Losing it costs one extra Linear read
// per ticket — persisting it would only create a second thing to
// reconcile.
import { STATE_MAP } from './linear-client.js';

// Human-blocking states jump the debounce (the spec's
// "Action-next-work-block" spirit): a parked or landable ticket must
// surface to humans immediately, not after a quiet window.
export const JUMP_STATES = ['needs-human', 'needs-info',
  'interactive-preferred', 'confident-ready'];

// Token bucket over the mirror's Linear write budget. Default 2500/hr =
// 50% of one OAuth App-User actor's 5,000/hr (spec §1 honest budget
// math), leaving headroom for back-edge reverts, reconcile reads, and
// margin. `force` (parks, reverts) always passes — those are rare,
// human-blocking or correctness writes — and may drive the balance
// negative; the refill repays the debt before non-forced writes resume.
export function makeBucket({
  maxPerHour = Number(process.env.MIRROR_MAX_PER_HOUR ?? 2500),
  now = Date.now(),
} = {}) {
  let tokens = maxPerHour;
  let last = now;
  const b = {
    skipped: 0,
    take({ force = false, now = Date.now() } = {}) {
      tokens = Math.min(maxPerHour,
        tokens + (now - last) * (maxPerHour / 3_600_000));
      last = now;
      if (tokens >= 1 || force) { tokens -= 1; return true; }
      b.skipped++;
      return false;
    },
  };
  return b;
}

export function makeSyncState() {
  return new Map(); // ticketId -> { issueId, mirrored, dirtyAt }
}

export async function syncOnce({ board, linear, state, bucket,
  now = Date.now(),
  debounceMs = Number(process.env.MIRROR_DEBOUNCE_MS ?? 5000),
}) {
  const out = { created: 0, written: 0, skipped: 0, deferred: 0 };
  const tickets = await board.listTickets(); // board down → throws: fail closed
  for (const t of tickets) {
    const desired = STATE_MAP[t.state];
    const jump = JUMP_STATES.includes(t.state);
    let e = state.get(t.id);

    if (!e) {
      // First sight (boot rebuild or new ticket): full comparison.
      const found = await linear.findIssueByTicketId(t.id);
      if (!found) {
        if (bucket.take({ force: jump, now })) {
          const { issueId } = await linear.createIssue({
            ticketId: t.id, title: t.payload?.title ?? t.id,
            stateName: desired });
          state.set(t.id, { issueId, mirrored: t.state, dirtyAt: null });
          out.created++;
        } else out.skipped++;
        continue;
      }
      e = found.stateName === desired
        ? { issueId: found.issueId, mirrored: t.state, dirtyAt: null }
        // differs → overdue immediately (board wins after a restart)
        : { issueId: found.issueId, mirrored: null, dirtyAt: now - debounceMs };
      state.set(t.id, e);
    }

    if (e.mirrored !== null && STATE_MAP[e.mirrored] === desired) {
      e.mirrored = t.state; // same lane: coalesced — nothing to write
      e.dirtyAt = null;
      continue;
    }
    if (e.dirtyAt === null) e.dirtyAt = now;
    if (!jump && now - e.dirtyAt < debounceMs) { out.deferred++; continue; }
    if (!bucket.take({ force: jump, now })) { out.skipped++; continue; }
    await linear.updateIssueState(e.issueId, desired);
    e.mirrored = t.state;
    e.dirtyAt = null;
    out.written++;
  }
  return out;
}

// The drop-proof backstop: one batched Linear read; revert any drift the
// webhook path missed (board always wins). Heals human edits whose
// delivery Linear dropped after its 3 retries. Reverts are correctness
// writes → forced through the bucket.
export async function reconcileOnce({ board, linear, state, bucket,
                                      now = Date.now() }) {
  const out = { reverted: 0 };
  const [tickets, mirrored] = await Promise.all(
    [board.listTickets(), linear.listMirroredIssues()]);
  const byTicket = new Map(tickets.map(t => [t.id, t]));
  for (const m of mirrored) {
    const t = byTicket.get(m.ticketId);
    if (!t) continue; // issue for an unknown ticket: leave for humans
    const desired = STATE_MAP[t.state];
    if (m.stateName === desired) continue;
    bucket.take({ force: true, now });
    await linear.updateIssueState(m.issueId, desired);
    const e = state.get(t.id);
    if (e) { e.mirrored = t.state; e.dirtyAt = null; }
    out.reverted++;
  }
  return out;
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all sync tests green, including debounce, park jump,
budget guard, reconcile, board-down, and boot-rebuild.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/mirror/src/board-client.js infra/a0/mirror/src/sync.js infra/a0/mirror/test/sync.test.js
git commit -m "feat(a0-mirror): forward sync — debounce, park jump, budget bucket, reconcile backstop"
```

---

### Task 4: Back-edge — signed webhook receiver, legality-gated apply, board-wins revert

**Files:**
- Create: `infra/a0/mirror/src/backedge.js`,
  `infra/a0/mirror/test/backedge.test.js`

**Interfaces:**
- Consumes: `makeBoard` (Task 3), `makeLinear`/`STATE_MAP`/
  `ticketIdFromTitle` (Task 2); env `LINEAR_WEBHOOK_SECRET`.
- Produces:
  - `verifySignature(rawBody, signatureHeader, secret)` → boolean —
    hex HMAC-SHA256 of the raw body, constant-time compare.
  - `reverseState(stateName)` → board state | null — reverse of
    `STATE_MAP` for human intent: unique lanes reverse exactly; the shared
    "In Progress" lane reverses to `ready-for-agent` (the one
    human-meaningful way to put a ticket back in front of agents — the
    unpark gesture); unknown lane names → null (ignored).
  - `makeBackedge({board, linear, secret=env LINEAR_WEBHOOK_SECRET,
    toleranceMs=60000, now=() => Date.now()})` → `node:http` Server.
    POST-only; responds 200 to everything it handled (including reverts —
    so Linear does not retry), 401 on bad signature or stale
    `webhookTimestamp`, 500 on board unreachability (so Linear DOES retry
    on its 1 min / 1 hr / 6 hr ladder; after that, `reconcileOnce` is the
    backstop).

**Semantics (state in code comments, verbatim spirit):**
- A webhook is a REQUEST to the board, never authority. The event's issue
  state is reversed to a board state, submitted as
  `POST /tickets/:id/transition {from: <board's current state>, to}`; on
  200 the human's edit stands; on 409 (illegal / lost race) the Linear
  issue is reverted to `STATE_MAP[board's current state]` — board wins.
- Park targets get an auto `parkNote` (`"parked by human via Linear
  (issue <id>)"`) because the board rightly refuses note-less parks; the
  human's real note lives in Linear, which they are already using.
- Self-echo suppression: our own mirror writes trigger webhooks too; the
  `already-in-sync` guard (event state name equals `STATE_MAP[board
  state]`) makes them no-ops without a board round-trip.
- **The honest window:** between an illegal human edit and its revert,
  Linear briefly shows a state the board never held. The revert lands
  within one webhook delivery (~seconds); if Linear drops the delivery,
  `reconcileOnce` heals it on its next tick. "The Linear mirror never
  shows a state the board didn't hold" is therefore *eventually* true
  within one sync/reconcile tick — that is the exact claim the property
  and reconcile tests verify, and the wording used in Final Verification.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/mirror/test/backedge.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { makeFakeLinear, makeFakeBoard } from './fakes.js';
import { makeLinear } from '../src/linear-client.js';
import { makeBoard } from '../src/board-client.js';
import { makeBackedge, verifySignature, reverseState } from '../src/backedge.js';

const SECRET = 'whsec-test';
const sign = (raw) => createHmac('sha256', SECRET).update(raw).digest('hex');

function payload({ issueId, title, stateName, ts = Date.now() }) {
  return { type: 'Issue', action: 'update', webhookTimestamp: ts,
           data: { id: issueId, title, state: { name: stateName } },
           updatedFrom: { stateId: 'ws-old' } };
}
async function deliver(base, p, sig) {
  const raw = JSON.stringify(p);
  return fetch(base, { method: 'POST',
    headers: { 'content-type': 'application/json',
               'linear-signature': sig ?? sign(raw) },
    body: raw });
}

async function rig() {
  const fl = await makeFakeLinear();
  const fb = await makeFakeBoard({});
  const linear = makeLinear({ url: fl.url, token: 'tok', teamId: 'team-1' });
  const board = makeBoard({ url: fb.url, adminKey: 'test-admin' });
  const server = makeBackedge({ board, linear, secret: SECRET });
  await new Promise(r => server.listen(0, r));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { fl, fb, linear, board, base,
           close() { server.close(); fl.close(); fb.close(); } };
}

test('reverseState: unique lanes reverse; In Progress means ready-for-agent; unknown → null', () => {
  assert.equal(reverseState('Done'), 'done');
  assert.equal(reverseState('Needs Human'), 'needs-human');
  assert.equal(reverseState('In Progress'), 'ready-for-agent');
  assert.equal(reverseState('Some Custom Lane'), null);
});

test('verifySignature accepts the right HMAC and rejects the rest', () => {
  assert.equal(verifySignature('body', sign('body'), SECRET), true);
  assert.equal(verifySignature('body', sign('tampered'), SECRET), false);
  assert.equal(verifySignature('body', undefined, SECRET), false);
  assert.equal(verifySignature('body', sign('body'), ''), false);
});

test('bad signature → 401, board untouched', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'confident-ready');
  const res = await deliver(r.base,
    payload({ issueId: 'i1', title: '[a0:t1] x', stateName: 'Done' }),
    'deadbeef');
  assert.equal(res.status, 401);
  assert.equal(r.fb.tickets.get('t1').state, 'confident-ready');
  r.close();
});

test('stale webhookTimestamp → 401 (replay guard)', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'confident-ready');
  const res = await deliver(r.base, payload({ issueId: 'i1',
    title: '[a0:t1] x', stateName: 'Done', ts: Date.now() - 120000 }));
  assert.equal(res.status, 401);
  r.close();
});

test('legal human transition flows through: confident-ready → done', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'confident-ready');
  const res = await deliver(r.base,
    payload({ issueId: 'i1', title: '[a0:t1] ship it', stateName: 'Done' }));
  assert.equal(res.status, 200);
  assert.deepEqual((await res.json()).applied,
    { from: 'confident-ready', to: 'done' });
  assert.equal(r.fb.tickets.get('t1').state, 'done');
  r.close();
});

test('unpark: drag from Needs Human to In Progress lands as ready-for-agent', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'needs-human');
  const res = await deliver(r.base, payload({ issueId: 'i1',
    title: '[a0:t1] blocked q', stateName: 'In Progress' }));
  assert.equal(res.status, 200);
  assert.equal(r.fb.tickets.get('t1').state, 'ready-for-agent');
  r.close();
});

test('human park gets an auto parkNote (board refuses note-less parks)', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'in-progress');
  const res = await deliver(r.base, payload({ issueId: 'i1',
    title: '[a0:t1] q', stateName: 'Needs Human' }));
  assert.equal(res.status, 200);
  assert.equal(r.fb.tickets.get('t1').state, 'needs-human');
  assert.match(r.fb.tickets.get('t1').park_note, /via Linear/);
  r.close();
});

test('illegal human edit → board 409 → Linear reverted to the board state', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'backlog');
  const { issueId } = await r.linear.createIssue({
    ticketId: 't1', title: 'x', stateName: 'In Progress' });
  r.fl.setIssueState(issueId, 'Done'); // the human's illegal drag
  const res = await deliver(r.base, payload({ issueId,
    title: `[a0:t1] x`, stateName: 'Done' }));
  assert.equal(res.status, 200);       // handled — Linear must not retry
  assert.equal((await res.json()).reverted.error, 'illegal-transition');
  assert.equal(r.fb.tickets.get('t1').state, 'backlog');          // board wins
  assert.equal(r.fl.issues.get(issueId).stateName, 'In Progress'); // reverted
  r.close();
});

test('non-mirrored issue (no marker) and non-state-change events are ignored', async () => {
  const r = await rig();
  let res = await deliver(r.base, payload({ issueId: 'i1',
    title: 'ordinary human issue', stateName: 'Done' }));
  assert.equal(res.status, 200);
  assert.equal((await res.json()).ignored, 'not-mirrored');
  const p = payload({ issueId: 'i1', title: '[a0:t1] x', stateName: 'Done' });
  delete p.updatedFrom;
  res = await deliver(r.base, p);
  assert.equal((await res.json()).ignored, 'not-a-state-change');
  r.close();
});

test('self-echo of our own mirror write is a no-op', async () => {
  const r = await rig();
  r.fb.addTicket('t1', 'done');
  const res = await deliver(r.base, payload({ issueId: 'i1',
    title: '[a0:t1] x', stateName: 'Done' })); // event state == mapped board state
  assert.equal((await res.json()).ignored, 'already-in-sync');
  r.close();
});

test('board unreachable → 500 so Linear retries', async () => {
  const r = await rig();
  r.fb.down = true;
  const res = await deliver(r.base, payload({ issueId: 'i1',
    title: '[a0:t1] x', stateName: 'Done' }));
  assert.equal(res.status, 500);
  r.close();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/backedge.js'`.

- [ ] **Step 3: Implement**

```js
// infra/a0/mirror/src/backedge.js
// Back-edge: human edits in Linear → webhook → the board's legality
// check. Authority never flows this way — a webhook is a REQUEST to the
// board; on 409 the Linear issue is reverted to the board's current
// state (board wins).
//
// Signature (verified against linear.app/developers/webhooks,
// 2026-07-23): Linear sends `Linear-Signature` = hex HMAC-SHA256 of the
// raw request body under the webhook signing secret, and the payload
// carries `webhookTimestamp` (Unix ms) to check against a ~1-minute
// replay window.
//
// The honest window: between an illegal human edit and its revert,
// Linear briefly shows a state the board never held. The revert lands
// within one webhook delivery (~seconds); if Linear drops the delivery
// (3 failed retries, no ordering guarantee), reconcileOnce heals it on
// its next tick. "Never shows a state the board didn't hold" is
// eventually true within one sync/reconcile tick.
import http from 'node:http';
import { createHmac, timingSafeEqual } from 'node:crypto';
import { STATE_MAP, ticketIdFromTitle } from './linear-client.js';

const PARKS = ['needs-human', 'needs-info', 'interactive-preferred'];

export function verifySignature(rawBody, signatureHeader, secret) {
  if (!signatureHeader || !secret) return false;
  const expected = createHmac('sha256', secret).update(rawBody).digest('hex');
  const a = Buffer.from(expected);
  const b = Buffer.from(signatureHeader);
  return a.length === b.length && timingSafeEqual(a, b);
}

// Reverse map for human intent. Unique lanes reverse exactly; the shared
// "In Progress" lane reverses to ready-for-agent — the one
// human-meaningful way to put a ticket back in front of agents (the
// unpark gesture). Unknown lanes → null (ignored).
export function reverseState(stateName) {
  if (stateName === STATE_MAP['ready-for-agent']) return 'ready-for-agent';
  for (const [board, name] of Object.entries(STATE_MAP)) {
    if (name === stateName && !['backlog', 'in-progress'].includes(board))
      return board;
  }
  return null;
}

export function makeBackedge({ board, linear,
                               secret = process.env.LINEAR_WEBHOOK_SECRET,
                               toleranceMs = 60_000,
                               now = () => Date.now() }) {
  return http.createServer(async (req, res) => {
    const send = (code, obj) => {
      res.writeHead(code, { 'content-type': 'application/json' });
      res.end(JSON.stringify(obj));
    };
    try {
      if (req.method !== 'POST') return send(404, { error: 'not-found' });
      let raw = '';
      for await (const c of req) raw += c;
      if (!verifySignature(raw, req.headers['linear-signature'], secret))
        return send(401, { error: 'bad-signature' });
      const p = JSON.parse(raw);
      if (Math.abs(now() - (p.webhookTimestamp ?? 0)) > toleranceMs)
        return send(401, { error: 'stale-timestamp' });

      // Only Issue state changes matter; ack everything else so Linear
      // does not retry noise.
      if (p.type !== 'Issue' || p.action !== 'update'
          || p.updatedFrom?.stateId === undefined)
        return send(200, { ok: true, ignored: 'not-a-state-change' });
      const ticketId = ticketIdFromTitle(p.data?.title);
      if (!ticketId) return send(200, { ok: true, ignored: 'not-mirrored' });

      const tickets = await board.listTickets(); // board down → catch → 500
      const t = tickets.find(x => x.id === ticketId);
      if (!t) return send(200, { ok: true, ignored: 'unknown-ticket' });

      const desired = STATE_MAP[t.state];
      // Self-echo suppression: our own mirror writes come back as
      // webhooks; if the event state already equals the mapped board
      // state there is nothing to apply.
      if (p.data.state.name === desired)
        return send(200, { ok: true, ignored: 'already-in-sync' });
      const to = reverseState(p.data.state.name);
      if (to === null)
        return send(200, { ok: true, ignored: 'unmapped-lane' });

      const r = await board.transition(ticketId, {
        from: t.state, to,
        ...(PARKS.includes(to)
          ? { parkNote: `parked by human via Linear (issue ${p.data.id})` }
          : {}),
      });
      if (r.status === 200)
        return send(200, { ok: true, applied: { from: t.state, to } });

      // 409 (illegal / lost race): board wins — revert the Linear issue.
      await linear.updateIssueState(p.data.id, desired);
      return send(200, { ok: true,
        reverted: { boardState: t.state, error: r.body.error } });
    } catch (e) {
      // 500 → Linear retries (1 min / 1 hr / 6 hr); after that,
      // reconcileOnce is the backstop.
      return send(500, { error: 'internal', detail: String(e.message) });
    }
  });
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — all backedge tests green.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/mirror/src/backedge.js infra/a0/mirror/test/backedge.test.js
git commit -m "feat(a0-mirror): back-edge webhook — HMAC verify, legality-gated apply, board-wins revert"
```

---

### Task 5: main wiring + end-to-end + mirror-never-invents-states property test

**Files:**
- Create: `infra/a0/mirror/src/main.js`, `infra/a0/mirror/test/e2e.test.js`

**Interfaces:**
- Consumes: everything above; env `MIRROR_POLL_MS` (default 10000),
  `MIRROR_RECONCILE_MS` (default 600000), `PORT` (default 8090).
- Produces: `start({board, linear, pollMs, reconcileMs, port})` →
  `{ready (promise: webhook server listening), server, state, bucket,
  tick() (one manual syncOnce), reconcile() (one manual reconcileOnce),
  stop()}` — timers + webhook server on one wiring; `tick`/`reconcile`
  exposed so tests (and Plan 2's future ops hooks) can drive it without
  timers. Sync failures are logged and swallowed (fail closed, retry next
  tick) — a board outage must not crash the mirror, because Linear's last
  mirrored state is exactly what humans keep reading during the outage.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/mirror/test/e2e.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { makeFakeLinear, makeFakeBoard } from './fakes.js';
import { makeLinear, STATE_MAP } from '../src/linear-client.js';
import { makeBoard } from '../src/board-client.js';
import { makeBucket, makeSyncState, syncOnce } from '../src/sync.js';
import { start } from '../src/main.js';
import { LEGAL } from '../../board-service/src/transitions.js';

test('end to end through main: forward mirror + back-edge on one wiring', async () => {
  const fl = await makeFakeLinear();
  const fb = await makeFakeBoard({});
  process.env.LINEAR_WEBHOOK_SECRET = 'whsec-e2e';
  const app = start({
    board: makeBoard({ url: fb.url, adminKey: 'test-admin' }),
    linear: makeLinear({ url: fl.url, token: 'tok', teamId: 'team-1' }),
    pollMs: 3_600_000, reconcileMs: 3_600_000, port: 0, // timers inert in test
  });
  await app.ready;

  fb.addTicket('t1', 'needs-human');
  await app.tick(); // forward edge: create straight into the Needs Human lane
  const issue = [...fl.issues.values()][0];
  assert.equal(issue.stateName, 'Needs Human');

  // human unparks in Linear → back-edge → board legality → ready-for-agent
  const base = `http://127.0.0.1:${app.server.address().port}`;
  const p = { type: 'Issue', action: 'update', webhookTimestamp: Date.now(),
    data: { id: issue.id, title: issue.title,
            state: { name: 'In Progress' } },
    updatedFrom: { stateId: 'ws-old' } };
  const raw = JSON.stringify(p);
  const res = await fetch(base, { method: 'POST',
    headers: { 'content-type': 'application/json',
      'linear-signature':
        createHmac('sha256', 'whsec-e2e').update(raw).digest('hex') },
    body: raw });
  assert.equal(res.status, 200);
  assert.equal(fb.tickets.get('t1').state, 'ready-for-agent');

  app.stop(); fl.close(); fb.close();
  delete process.env.LINEAR_WEBHOOK_SECRET;
});

test('property: the mirror never invents a state the board did not hold', async () => {
  const fl = await makeFakeLinear();
  const fb = await makeFakeBoard({});
  const linear = makeLinear({ url: fl.url, token: 'tok', teamId: 'team-1' });
  const board = makeBoard({ url: fb.url, adminKey: 'test-admin' });
  const state = makeSyncState();
  const bucket = makeBucket({ maxPerHour: 1_000_000, now: 0 });

  fb.addTicket('t1', 'backlog');
  const held = new Set(['backlog']);
  let now = 0;
  await syncOnce({ board, linear, state, bucket, now, debounceMs: 5000 });

  for (let i = 0; i < 200; i++) {
    const cur = fb.tickets.get('t1').state;
    const nexts = LEGAL[cur];
    const to = nexts.length === 0
      ? 'backlog' // done is terminal: recycle so the walk keeps moving
      : nexts[Math.floor(Math.random() * nexts.length)];
    fb.setState('t1', to);
    held.add(to);
    now += Math.floor(Math.random() * 8000); // sometimes inside, sometimes past debounce
    await syncOnce({ board, linear, state, bucket, now, debounceMs: 5000 });
  }
  now += 10_000;
  await syncOnce({ board, linear, state, bucket, now, debounceMs: 5000 });

  // Every Linear state ever observed corresponds to a state the board held.
  const allowed = new Set([...held].map(s => STATE_MAP[s]));
  for (const w of fl.writes)
    assert.ok(allowed.has(w.stateName),
      `Linear observed '${w.stateName}' — not the projection of any state the board held`);
  // And after the final flush the mirror converged on the board's state.
  assert.equal([...fl.issues.values()][0].stateName,
    STATE_MAP[fb.tickets.get('t1').state]);
  fl.close(); fb.close();
});

// Opt-in drill against the REAL Plan 1 board service (fake Linear stays).
// Run: start the board service (see Final Verification), then
//   A0_BOARD_URL=http://127.0.0.1:8080 A0_ADMIN_KEY=dev npm test
test('item-10 mirror half against the real board service',
  { skip: !process.env.A0_BOARD_URL }, async () => {
  const fl = await makeFakeLinear();
  const linear = makeLinear({ url: fl.url, token: 'tok', teamId: 'team-1' });
  const board = makeBoard({ url: process.env.A0_BOARD_URL,
                            adminKey: process.env.A0_ADMIN_KEY });
  const admin = { 'authorization': `Bearer ${process.env.A0_ADMIN_KEY}`,
                  'content-type': 'application/json' };
  const state = makeSyncState();
  const bucket = makeBucket({ maxPerHour: 1_000_000, now: 0 });
  const id = `t-mirror-${Date.now()}`; // unique per run: real DB persists

  await fetch(`${process.env.A0_BOARD_URL}/tickets`, { method: 'POST',
    headers: admin, body: JSON.stringify({ id }) });
  await board.transition(id, { from: 'backlog', to: 'ready-for-agent' });
  await syncOnce({ board, linear, state, bucket, now: 0 });
  const mine = () => [...fl.issues.values()]
    .find(i => i.title.includes(`[a0:${id}]`));
  assert.equal(mine().stateName, 'In Progress');

  await board.transition(id, { from: 'ready-for-agent', to: 'in-progress' });
  await board.transition(id, { from: 'in-progress', to: 'needs-human',
    parkNote: 'q: which flag? recommend --safe' });
  await syncOnce({ board, linear, state, bucket, now: 10 }); // park jumps debounce
  assert.equal(mine().stateName, 'Needs Human');

  // "Board down": unreachable URL. Mirror fails closed; Linear keeps
  // the last mirrored state for humans.
  const deadBoard = makeBoard({ url: 'http://127.0.0.1:1',
                                adminKey: process.env.A0_ADMIN_KEY });
  await assert.rejects(() =>
    syncOnce({ board: deadBoard, linear, state, bucket, now: 1000 }));
  assert.equal(mine().stateName, 'Needs Human');

  // Recovery: normal ticks only — no special reconciliation.
  await board.transition(id, { from: 'needs-human', to: 'ready-for-agent' });
  await syncOnce({ board, linear, state, bucket, now: 2000 });
  await syncOnce({ board, linear, state, bucket, now: 8000 }); // debounce elapsed
  assert.equal(mine().stateName, 'In Progress');
  fl.close();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: FAIL — `Cannot find module '../src/main.js'` (the real-board
test reports SKIP unless `A0_BOARD_URL` is set).

- [ ] **Step 3: Implement main.js**

```js
// infra/a0/mirror/src/main.js
// Wires the three loops of the mirror onto one process:
//   forward sync   — every MIRROR_POLL_MS      (default 10 s)
//   reconcile      — every MIRROR_RECONCILE_MS (default 10 min; the
//                    drop-proof backstop for webhook deliveries Linear
//                    dropped after 3 retries)
//   back-edge      — webhook server on PORT     (default 8090)
// Sync failures are logged and swallowed: the mirror fails closed and
// retries next tick. During a board outage Linear simply keeps showing
// the last mirrored state — which is exactly the spec's item-10 behavior.
import { makeLinear } from './linear-client.js';
import { makeBoard } from './board-client.js';
import { makeBucket, makeSyncState, syncOnce, reconcileOnce } from './sync.js';
import { makeBackedge } from './backedge.js';

export function start({
  board = makeBoard(),
  linear = makeLinear(),
  pollMs = Number(process.env.MIRROR_POLL_MS ?? 10_000),
  reconcileMs = Number(process.env.MIRROR_RECONCILE_MS ?? 600_000),
  port = Number(process.env.PORT ?? 8090),
} = {}) {
  const state = makeSyncState();
  const bucket = makeBucket({});
  const tick = async () => {
    try {
      const r = await syncOnce({ board, linear, state, bucket });
      if (r.created || r.written || r.skipped)
        console.log(`sync: ${JSON.stringify(r)} (bucket skips total: ${bucket.skipped})`);
    } catch (e) {
      console.error(`sync failed (fail closed, retry next tick): ${e.message}`);
    }
  };
  const reconcile = async () => {
    try {
      const r = await reconcileOnce({ board, linear, state, bucket });
      if (r.reverted) console.log(`reconcile: reverted ${r.reverted} drifted issue(s)`);
    } catch (e) {
      console.error(`reconcile failed (retry next tick): ${e.message}`);
    }
  };
  const timers = [setInterval(tick, pollMs), setInterval(reconcile, reconcileMs)];
  const server = makeBackedge({ board, linear });
  const ready = new Promise(r => server.listen(port, () => {
    console.log(`a0 mirror back-edge on :${server.address().port}`);
    r();
  }));
  return {
    ready, server, state, bucket, tick, reconcile,
    stop() { timers.forEach(clearInterval); server.close(); },
  };
}

if (import.meta.url === `file://${process.argv[1]}`) start();
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test`
Expected: PASS — e2e + property green; real-board test SKIPPED (no
`A0_BOARD_URL`). Run the property test a few times to let the random walk
vary: `node --test test/e2e.test.js && node --test test/e2e.test.js`.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/mirror/src/main.js infra/a0/mirror/test/e2e.test.js
git commit -m "feat(a0-mirror): main wiring + e2e + never-invents-states property test"
```

---

### Task 6: SPIKE T3 — Linear per-endpoint mutation caps (knowledge deliverable)

**Question this spike answers (spec Adoption 2 / spike T3):** what are
Linear's unpublished per-endpoint mutation caps for `issueUpdate` /
`issueCreate` / `commentCreate` at the mirror's write rates? The research
doc calls this "the only number that could retroactively break" the
design, surfaced only via response headers, with support raises offered
"case by case". Two probes, cheap and parallel: a support email asking for
disclosure, and one controlled load test.

**Deliverable is knowledge, not code to keep:** the verdict routes into
the spec's `## Surprises & Discoveries`. The promote-or-discard criterion
is the spec's mirror budget sentence, verbatim:

> Honest budget math: that is 500–3,000 req/hr across the A0 band —
> **10–60% of one OAuth App-User actor's 5,000/hr**, not a rounding
> error — so run one actor at low A0, and at the high end add per-ticket
> debouncing (at most one mirror write per ticket per short window) or a
> second App-User actor, both inside Linear's documented model.

If the disclosed/measured per-endpoint caps clear the band's write rates,
the mirror's final shape stands as built (one actor low-A0, debounce at
the top). If they clip it, the verdict decides **whether high-A0 needs a
second App-User actor or heavier coalescing** (raise
`MIRROR_DEBOUNCE_MS`, tighten `MIRROR_MAX_PER_HOUR`) — both knobs already
exist in Task 3; no redesign either way.

**Files:**
- Create: `infra/a0/mirror/tools/t3-support-email.md`,
  `infra/a0/mirror/tools/t3-rate-probe.mjs`

**Interfaces:**
- Consumes: real Linear GraphQL API (the ONLY real-API touchpoint in this
  plan), env `LINEAR_TOKEN`, `LINEAR_TEST_TEAM_ID` (safety latch).
- Produces: a verdict bullet in the spec's `## Surprises & Discoveries`.

- [ ] **Step 1: Write the support email draft**

```markdown
# T3 — Linear support email (draft)

To: support@linear.app
Subject: Per-endpoint mutation rate limits for an OAuth App-User integration

Hi Linear team,

We are building a one-way mirror that projects an internal ticket board
into a Linear team for human visibility, authenticating as an OAuth
App-User actor (actor=app), on a workspace with 10–20 paid seats.

Your rate-limiting page notes that "some queries and mutations have
individual request rate limits that are lower than the global request
limit", surfaced via response headers, but the numbers are unpublished.
Before we finalize the integration's shape, could you disclose or confirm:

1. The per-endpoint request limits (per actor, per hour and any per-minute
   burst component) for these mutations:
   - `issueUpdate` — our steady state is roughly 500–3,000 requests/hour
     workspace-wide across our growth band, coalesced to at most one
     write per issue per few-second window, bursts up to ~10/minute.
   - `issueCreate` — tens per hour steady, bursts up to ~30 in a minute
     after a bulk ticket import.
   - `commentCreate` — tens per hour.
2. The exact response header names that surface per-endpoint limit state,
   so our budget guard can read them.
3. Whether the "dynamically increase rate limits for workspace level
   OAuth apps using Actor Authorization based on number of paid users"
   scaling applies to these per-endpoint caps or only to the global
   5,000 requests/hour/actor budget — and, if you can share it, the
   multiplier at our seat count.
4. A documentation clarification: your rate-limiting page's prose says
   API keys get "up to 5,000 requests/hour" while the limits table reads
   2,500/hour — which figure governs? (We plan on OAuth actors either
   way; asking so we can size fallbacks honestly.)
5. If our stated rates would need a case-by-case raise, what you need
   from us to grant one.

Thanks — happy to share the integration design if useful.
```

- [ ] **Step 2: Write the load-test probe**

```js
// infra/a0/mirror/tools/t3-rate-probe.mjs
// T3 spike (knowledge deliverable): probe Linear's unpublished
// per-endpoint mutation caps by issuing a controlled burst of issueUpdate
// mutations against a THROWAWAY test team, printing every X-RateLimit-*
// (and any per-endpoint) response header, stopping on the first 429 or
// GraphQL rate error. This is the ONLY real-API artifact in this plan.
//
// SAFETY LATCH: refuses to run without LINEAR_TEST_TEAM_ID. Never point
// this at a team humans use — it creates and mutates a probe issue.
//
// Usage:
//   LINEAR_TOKEN=... LINEAR_TEST_TEAM_ID=... \
//     node tools/t3-rate-probe.mjs [count=120] [perSecond=2]

const token = process.env.LINEAR_TOKEN;
const teamId = process.env.LINEAR_TEST_TEAM_ID;
if (!teamId) {
  console.error('REFUSING to run: set LINEAR_TEST_TEAM_ID to a THROWAWAY '
    + 'test team. This script creates and mutates issues.');
  process.exit(1);
}
if (!token) { console.error('set LINEAR_TOKEN'); process.exit(1); }
const count = Number(process.argv[2] ?? 120);
const perSecond = Number(process.argv[3] ?? 2);
const url = 'https://api.linear.app/graphql';

async function gql(query, variables) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: token },
    body: JSON.stringify({ query, variables }),
  });
  const headers = {};
  for (const [k, v] of r.headers)
    if (/ratelimit|complexity|retry-after|endpoint/i.test(k)) headers[k] = v;
  const body = await r.json().catch(() => ({}));
  return { status: r.status, headers, body };
}

const ws = await gql(
  `query($teamId: String!) {
     workflowStates(filter: { team: { id: { eq: $teamId } } }) {
       nodes { id name } } }`, { teamId });
const nodes = ws.body?.data?.workflowStates?.nodes ?? [];
if (nodes.length < 2) {
  console.error('test team needs >=2 workflow states; got',
    JSON.stringify(ws.body));
  process.exit(1);
}

const created = await gql(
  `mutation($input: IssueCreateInput!) {
     issueCreate(input: $input) { success issue { id } } }`,
  { input: { teamId, stateId: nodes[0].id,
             title: '[a0-t3-probe] rate-limit probe (safe to delete)' } });
const issueId = created.body.data.issueCreate.issue.id;
console.log(`probe issue ${issueId}; burst: ${count} issueUpdate at ${perSecond}/s`);
console.log(`initial headers: ${JSON.stringify(created.headers)}`);

let lastHeaders = '';
for (let i = 0; i < count; i++) {
  const r = await gql(
    `mutation($id: String!, $input: IssueUpdateInput!) {
       issueUpdate(id: $id, input: $input) { success } }`,
    { id: issueId, input: { stateId: nodes[i % 2 === 0 ? 1 : 0].id } });
  const h = JSON.stringify(r.headers);
  if (h !== lastHeaders) { console.log(`#${i} status=${r.status} ${h}`); lastHeaders = h; }
  if (r.status === 429 || r.body.errors) {
    console.log(`STOP at #${i}: status=${r.status} `
      + `errors=${JSON.stringify(r.body.errors ?? null)} headers=${h}`);
    break;
  }
  await new Promise(res => setTimeout(res, 1000 / perSecond));
}
console.log('done. Delete the probe issue in the Linear UI '
  + '(its [a0-t3-probe] title marks it), or leave it in the throwaway team.');
```

- [ ] **Step 3: Commit the spike tools**

```bash
git add infra/a0/mirror/tools/t3-support-email.md infra/a0/mirror/tools/t3-rate-probe.mjs
git commit -m "feat(a0-mirror): T3 spike tools — mutation-cap probe (test-team latch) + support email draft"
```

- [ ] **Step 4: Execute — send the email, run the probe (needs real credentials)**

Send the email via the workspace's Linear support channel. Then, on a
throwaway team created for this purpose:

Run: `LINEAR_TOKEN=<token> LINEAR_TEST_TEAM_ID=<throwaway-team-id> node infra/a0/mirror/tools/t3-rate-probe.mjs 120 2`
Expected: 120 update mutations at 2/s (≈7,200/hr pace — above the whole
mirror band) with per-response header lines; either no 429 (caps clear
the band) or a STOP line whose headers name the binding per-endpoint
limit. If credentials are not yet provisioned, this step BLOCKS the
spike's verdict but nothing else in the plan — record that state
honestly in Step 5 instead of a verdict.

- [ ] **Step 5: Record the verdict in the spec (spike output routing)**

Append to `docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md`
`## Surprises & Discoveries` a bullet of the form:

```
- **T3 verdict (Linear per-endpoint mutation caps):** probe of N
  issueUpdate mutations at R/s [hit no per-endpoint limit | was clipped
  at ~X/min per the `<header>` header]; support [disclosed caps of … |
  has not answered as of <date>]. Against the spec's mirror budget
  ("10–60% of one OAuth App-User actor's 5,000/hr"), the high-A0 shape
  is [one actor + default debounce | heavier coalescing (debounce →
  Xs) | a second App-User actor]. Probe script kept at
  infra/a0/mirror/tools/t3-rate-probe.mjs for contract-day re-runs.
```

Then commit:

```bash
git add docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "docs(a0): T3 spike verdict — Linear per-endpoint mutation caps"
```

---

### Task 7: Deployment — README env contract, Render blueprint, mirrored-team checklist

**Files:**
- Create: `infra/a0/mirror/README.md`, `infra/a0/mirror/render.yaml`

**Interfaces:**
- Consumes: `start()` (Task 5); the full env contract accumulated above.

- [ ] **Step 1: Write README.md**

```markdown
# A0 Linear mirror (Plan 4 of 4)

Implements the spec §1 "Linear mirror (human surface) — one-way
authority, two-way visibility" paragraph:
`docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md`.

One small process beside the board service. Forward edge: poll the board,
project through STATE_MAP, per-ticket debounce, budget bucket. Back edge:
Linear webhook -> board legality check; on 409 the Linear issue reverts
to the board state (board always wins). Periodic reconcile is the
backstop for webhook deliveries Linear drops after 3 failed retries.
Humans work in Linear daily; agents never read it.

## Run locally

    cd infra/a0/mirror && npm test        # fakes only, no network
    A0_BOARD_URL=http://127.0.0.1:8080 A0_ADMIN_KEY=dev \
      LINEAR_TOKEN=... LINEAR_TEAM_ID=... LINEAR_WEBHOOK_SECRET=... \
      npm start

## Env contract

| var | default | meaning |
|---|---|---|
| A0_BOARD_URL | (required) | Plan 1 board service base URL |
| A0_ADMIN_KEY | (required) | board admin bearer. ACCEPTED SIMPLIFICATION: no third credential tier at A0; the future split is a "mirror key" scoped to GET /tickets + human-legal transitions. Workers never hold this. |
| LINEAR_TOKEN | (required) | OAuth App-User actor token (actor=app) — NOT a human's key: machine writes under human identities muddy the audit record |
| LINEAR_TEAM_ID | (required) | the mirrored team |
| LINEAR_URL | api.linear.app/graphql | override for the fake in tests |
| LINEAR_WEBHOOK_SECRET | (required) | webhook signing secret (Linear-Signature HMAC) |
| LINEAR_STATE_MAP | built-in | JSON overriding board-state -> lane-name mapping |
| MIRROR_POLL_MS | 10000 | forward-edge poll interval |
| MIRROR_RECONCILE_MS | 600000 | drop-proof backstop interval |
| MIRROR_DEBOUNCE_MS | 5000 | per-ticket quiet window (parks/confident-ready jump it) |
| MIRROR_MAX_PER_HOUR | 2500 | Linear write budget = 50% of one actor's 5,000/hr |
| PORT | 8090 | webhook receiver port |

## Mirrored-team setup checklist

1. Create (or pick) the Linear team; ensure its workflow states include
   the seven lane names in STATE_MAP (or set LINEAR_STATE_MAP).
2. **Disable Linear's GitHub PR automations on the mirrored team.** They
   are a second uncoordinated writer against the board's authority
   (spec §1; same hazard class as Projects v2 automations).
3. Create the OAuth App-User actor, grab its token -> LINEAR_TOKEN.
4. Create a webhook pointed at https://<mirror-host>/ subscribed to
   Issue events; copy its signing secret -> LINEAR_WEBHOOK_SECRET.
5. Confirm the T3 spike verdict (per-endpoint mutation caps) is recorded
   in the spec before scaling past low-A0.

## Actor math per A0 band (spec §1, honest)

Mirror traffic is 500–3,000 req/hr across the band — 10–60% of one OAuth
App-User actor's 5,000/hr, not a rounding error.

- Low A0 (~250 starts/hr): ONE actor, defaults as shipped.
- High A0 (~1,000 starts/hr): raise MIRROR_DEBOUNCE_MS (heavier
  coalescing — at most one mirror write per ticket per window) or add a
  second App-User actor. Both are inside Linear's documented model;
  which one is the T3 verdict's call.

## Audit note

Linear retains issue history for 90 days. No nightly export job is
needed here — the BOARD is the permanent record (append-only tickets,
comments, session events in Postgres); Linear is a disposable view of
it. Deleting every mirrored issue loses nothing the system needs.
```

- [ ] **Step 2: Write render.yaml**

```yaml
# infra/a0/mirror/render.yaml
# Web service (not worker): the back-edge webhook needs public ingress.
# Runs beside the Plan 1 board service (same Render account/region).
services:
  - type: web
    name: a0-mirror
    runtime: node
    rootDir: infra/a0/mirror
    buildCommand: "true"          # zero dependencies — nothing to install
    startCommand: node src/main.js
    plan: starter
    numInstances: 1               # exactly one: two mirrors = two writers against one actor budget
    envVars:
      - key: A0_BOARD_URL
        sync: false               # internal URL of the a0-board-service
      - key: A0_ADMIN_KEY
        sync: false
      - key: LINEAR_TOKEN
        sync: false               # OAuth App-User actor token
      - key: LINEAR_TEAM_ID
        sync: false
      - key: LINEAR_WEBHOOK_SECRET
        sync: false
```

- [ ] **Step 3: Sanity-boot against local fakes**

Run (from `infra/a0/mirror/`):
`node --input-type=module -e "import('./test/fakes.js').then(async ({makeFakeLinear, makeFakeBoard}) => { const fl = await makeFakeLinear(); const fb = await makeFakeBoard({}); process.env.LINEAR_WEBHOOK_SECRET='dev'; const { start } = await import('./src/main.js'); const app = start({ board: (await import('./src/board-client.js')).makeBoard({url: fb.url, adminKey: 'test-admin'}), linear: (await import('./src/linear-client.js')).makeLinear({url: fl.url, token: 't', teamId: 'team-1'}), pollMs: 200, reconcileMs: 1000, port: 0 }); await app.ready; fb.addTicket('t1','needs-human'); await new Promise(r => setTimeout(r, 500)); console.log('mirrored:', [...fl.issues.values()][0]?.stateName); app.stop(); fl.close(); fb.close(); })"`
Expected: logs `a0 mirror back-edge on :<port>` then `mirrored: Needs Human`.

- [ ] **Step 4: Commit**

```bash
git add infra/a0/mirror/README.md infra/a0/mirror/render.yaml
git commit -m "feat(a0-mirror): deployment — README env contract, Render blueprint, mirrored-team checklist"
```

---

### Task 8: Final verification — spec acceptance items this plan owns

**Files:** none (verification only; one spec living-tail append).

- [ ] **Step 1: Full suite**

Run (from `infra/a0/mirror/`): `npm test`
Expected: all tests PASS (real-board test SKIPPED in this pass).

- [ ] **Step 2: Execute the spec's acceptance items this plan owns, as written**

From spec `## Acceptance (behavior-phrased)` — this plan owns the MIRROR
half of items 4 and 10 (Plan 1 verified their board halves):

> 4. An illegal transition submitted directly to the board service returns a
>    legality error; no illegal state is ever observable in the board, and
>    the Linear mirror never shows a state the board didn't hold.

Mirror half, covered three ways — re-run and confirm each:
- `node --test test/e2e.test.js` → the property test drives 200 random
  board transitions and asserts every Linear state ever written is the
  projection of a state the board held → PASS.
- `node --test test/backedge.test.js` → the illegal-human-edit test
  asserts the 409 revert restores the board's state on the Linear issue
  → PASS.
- `node --test test/sync.test.js` → the reconcile-backstop test asserts
  dropped-webhook drift is reverted on the next reconcile tick → PASS.

Honest scope note (record verbatim in the revision bullet): the guarantee
is *eventual within one sync/reconcile tick* — a human's illegal edit is
visible in Linear for the seconds between the edit and the webhook revert
(or, if Linear drops the delivery after 3 retries, until the next
reconcile tick). The board itself never holds the state at any moment.

> 10. The board service down for an hour: workers fail closed (no local
>     claims), humans keep reading Linear's last mirrored state, and recovery
>     requires no reconciliation beyond the reconciler's normal tick.

Mirror half ("humans keep reading Linear's last mirrored state" +
"recovery requires no reconciliation beyond the reconciler's normal
tick"), covered against the fake board by the board-down test in
`test/sync.test.js` → PASS — and against the REAL Plan 1 board service:

```bash
docker start a0-pg || docker run -d --name a0-pg -e POSTGRES_PASSWORD=a0 -p 54329:5432 postgres:16
(cd ../board-service && A0_ADMIN_KEY=dev DATABASE_URL=postgres://postgres:a0@localhost:54329/postgres PORT=8080 npm start &)
sleep 2
A0_BOARD_URL=http://127.0.0.1:8080 A0_ADMIN_KEY=dev node --test test/e2e.test.js
```

Expected: the `item-10 mirror half against the real board service` test
runs (not skipped) and PASSES: mirror creates the issue on the real
board's tickets, the park jumps the debounce, the dead-board sync
rejects while the fake Linear retains `Needs Human` for humans, and
recovery converges through ordinary `syncOnce` ticks with no special
reconciliation path. Stop the board service process afterwards.

(The workers-fail-closed half of item 10 was verified structurally in
Plan 1 Task 9; nothing in this plan gives workers a new write path —
verify by inspection that `infra/a0/mirror/` never reads `DATABASE_URL`
and that no mirror credential is delivered to sandboxes.)

- [ ] **Step 3: Record coverage in the spec's living tail**

Append to the spec `## Revision Notes`:

```
- <date>: Plan 4 (a0-linear-mirror) implemented — acceptance 4 (mirror
  half: property test + 409-revert + reconcile backstop; guarantee is
  eventual within one sync/reconcile tick, stated honestly) and 10
  (mirror half: board-down freeze + normal-tick recovery, verified
  against the real board service) covered. Mirror authenticates with
  A0_ADMIN_KEY — accepted simplification; future "mirror key" tier named
  in infra/a0/mirror/README.md. T3 verdict tracked separately (Task 6).
```

- [ ] **Step 4: Commit**

```bash
git add docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "docs(a0): record Plan 4 acceptance coverage in spec living tail"
```



