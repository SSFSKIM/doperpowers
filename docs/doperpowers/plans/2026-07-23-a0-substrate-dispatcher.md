# A0 Substrate Adapter + Dispatcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the A0 spec's compute plane — the thin create/exec/destroy
substrate adapter (E2B real + in-memory fake), the per-claim worker launch
plan with credentials placed per spec §6 (git token only inside the clone
remote URL, board/merge credentials structurally absent, Anthropic key as
the accepted bounded spend credential), and the dispatcher loop that claims
from the board service over HTTP, runs the worker in a sandbox, streams its
stdout into the session log (and to Axiom as a disposable view), and
destroys the sandbox — plus the T2 spike (E2B contract facts) that gates
real-vendor use and the conditional T4 spike (Northflank egress).

**Architecture:** One Node 22 process, no database. The dispatcher holds
exactly two outward credentials: `A0_ADMIN_KEY` (its board machine identity,
spec §6) and the substrate/vendor keys. It speaks board-service HTTP only —
`POST /claims`, `POST /runs/:id/events`, `POST /runs/:id/usage` — never SQL
(a spec property, enforced by test). Everything vendor-specific lives behind
the substrate adapter's three calls (`create`/`exec`/`destroy`), so swapping
sandbox vendors is a config change (spec §3, acceptance drill 7). The E2B
template name IS the environment key (spec §3) — same key, same template,
byte-identical toolchain (drill 9). Workers receive only
`{A0_BOARD_URL, A0_RUN_ID, A0_RUN_TOKEN, ANTHROPIC_API_KEY}`; the dispatcher
performs no ticket transitions (workers own those with their per-run token +
fence). A failed pass ends that attempt with a best-effort destroy; the
board's lease reclaim (Plan 1 reconciler) is the recovery path.

**Tech Stack:** Node 22 (ESM, `node:http`, `node:test`, global `fetch`),
`e2b` JS SDK v2 (only npm dependency; API surface verified against the
v2.0.2 SDK reference on 2026-07-23), FakeSubstrate + in-test `node:http`
board/Axiom servers for a fully offline test suite.

**Plan slicing (this is Plan 3 of 4 for the spec
`docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md`):**
1. Board service + claim path + T1 spike (spec §1, §2, §4 schema) —
   `2026-07-23-a0-core-board-service.md`, already written.
2. Reconciler cron + circuit breakers + cost meter + Slack outbox (spec §8,
   §9) — adds `POST /runs/:id/usage` and the 423/429 claim responses.
3. **This plan** — substrate adapter + E2B dispatch + secrets placement +
   log shipping sliver of §8 (spec §3, §6) — real-vendor use gated on
   spike T2.
4. Linear mirror, one-way authority / two-way visibility (spec §1 mirror).

## Global Constraints

- Node ≥ 22 (built-in test runner, ESM, global `fetch`). Only npm
  dependency: `e2b`. **No `pg`** — the dispatcher never touches the
  database; it speaks board-service HTTP only (enforced by
  `test/no-db.test.js`).
- Substrate adapter contract (frozen — the drill-7 seam):
  `createSubstrate(config)` → `{ create({templateId, env}) →
  Promise<{sandboxId}>, exec(sandboxId, cmd, {env={}, onStdout, onStderr,
  timeoutMs}) → Promise<{exitCode}>, destroy(sandboxId) → Promise<void> }`.
  Vendor selection by `config.kind: 'e2b' | 'fake'` only.
- Credentials placement (spec §6): the git push token appears ONLY inside
  the clone remote URL — never in any env object handed to the substrate,
  never in any logged or board-shipped line. `A0_ADMIN_KEY` never enters a
  sandbox. Board-write and merge credentials do not exist in this package
  at all. `ANTHROPIC_API_KEY` is injected per run — accepted spend
  credential; blast radius = the workspace's Console spend cap.
- Worker env is exactly `{A0_BOARD_URL, A0_RUN_ID, A0_RUN_TOKEN,
  ANTHROPIC_API_KEY}` — nothing more.
- The dispatcher only CALLs `POST /claims` and honors 423 (paused) / 429
  (capped) — breaker and admission logic itself is Plan 2; the Linear
  mirror is Plan 4; board-service source and schema are untouched.
- Errors in a pass must never kill the loop: best-effort destroy, `{error}`
  return, board lease reclaim recovers the run.
- All tests run offline against FakeSubstrate + in-test `node:http`
  servers. Anything touching real E2B is gated on spike T2 (Task 1) and
  marked post-T2 in Final Verification.
- Ticket states are Plan 1's frozen set; this plan never writes them.

## File Structure

```
infra/a0/dispatcher/
  package.json                 — name, type:module, deps: e2b
  README.md                    — deployment runbook: env contract + spec §6 secrets table
  Dockerfile                   — Render/Fly worker image
  render.yaml                  — Render background-worker blueprint (1 instance)
  templates/e2b.Dockerfile     — environment-key template recipe (name = env key)
  src/substrate.js             — adapter interface + vendor selection (config only)
  src/e2b.js                   — real substrate (e2b SDK)
  src/fake.js                  — in-memory substrate: test double + drill-7 proof
  src/worker-launch.js         — per-claim launch plan (env, init cmds, worker cmd)
  src/dispatcher.js            — runOnce pass, line sink (board + Axiom), main loop
  test/fake-board.js           — in-test board-service HTTP server (node:http)
  test/substrate.test.js
  test/no-db.test.js           — "dispatcher speaks HTTP only" property
  test/worker-launch.test.js
  test/dispatcher.test.js
  test/axiom.test.js
  test/config.test.js          — configFromEnv + vendor-swap drill
```

---

### Task 1: Spike T2 — E2B contract facts (knowledge deliverable; gates real-vendor use)

**Question this spike answers (spec §3 pre-contract action list / spike
T2):** what are E2B's unpublished paused-storage and extra-concurrency
prices, is a startup discount available off the ~$4.7k/month list bill, and
what is their SLA/incident posture (Mar-5-2026-style create/pause/resume
degradation)? These are BLOCKING the contract — no production `kind:'e2b'`
deployment until answered. All local development in Tasks 2–8 proceeds on
FakeSubstrate regardless.

**Files:** none in the repo except the spec's living tail (spike output
routes into the spec, not into a new report file).

**Interfaces:**
- Produces: written vendor answers + a go/no-go verdict recorded in the
  spec's `## Decision Log` / `## Surprises & Discoveries`.

- [ ] **Step 1: Re-verify the published E2B facts live, with dates**

The spec's standing lesson: "every vendor fact carries a verification date,
and any decisive tiebreaker is re-checked on the day of contract." Fetch and
record (date-stamped) the current values of:

- https://e2b.dev/pricing — Pro plan fee, per-second vCPU/RAM rates,
  base concurrency (research baseline: $150/mo; $0.1656 per
  2-vCPU/4-GiB run-hour; 100 base concurrency, purchasable to 1,100).
- https://e2b.dev/docs/sandbox/internet-access — domain allowlist +
  CIDR rules, runtime-updatable (the drill-3 containment control).
- https://e2b.dev/docs/sandbox/rate-limits — lifecycle op limits
  (baseline: 20,000 requests / 30 s).
- https://status.e2b.dev — incident record since Mar 2026.

If any figure moved against the research baseline, note it explicitly — a
moved decisive fact reopens Decision Log 2 before any contract.

- [ ] **Step 2: Draft the vendor outreach (full text below) and hand it to your human partner to send**

Sales outreach must come from the company account — this is a
human-in-the-loop handoff, not something to work around. Draft:

```
Subject: Startup evaluation — pricing questions before committing ~2 vCPU × 13–27.5k run-hours/month

Hi — we're a small AI-native startup evaluating E2B Pro as the sandbox
substrate for a fleet of coding agents. Expected steady-state load:
50–200 concurrent sandboxes (2 vCPU / 4 GiB), ~250–1,000 starts/hour
during work hours, ~13–27.5k run-hours/month. Before contracting we need
four things in writing:

1. Paused-sandbox storage pricing (not on the public pricing page).
2. Extra-concurrency pricing above the Pro base of 100, up to ~1,100.
3. Whether a startup discount applies — at list, our band prices at
   roughly $2.2–4.7k/month, the top of our infra budget.
4. Your SLA / incident-response posture for sandbox create/pause/resume
   degradation of the kind visible on your status page for Mar 5, 2026 —
   dispatch-blocking incidents are our main reliability concern.

Happy to get on a call. We can commit quickly once these are in writing.
```

- [ ] **Step 3: Record answers and the verdict into the spec's living tail**

When answers arrive, append to the spec's `## Surprises & Discoveries`:

```
- **T2 E2B contract facts (verified <date>):** paused storage $X/GiB-mo;
  extra concurrency $Y per <unit> above 100; discount: <terms | none>;
  SLA posture: <summary>. Published rates re-verified <date>:
  <moved | unchanged vs research baseline>. Verdict: <contract E2B |
  renegotiate | activate Daytona | fire T4>.
```

and, if the verdict changes or confirms the vendor decision, a dated entry
in `## Decision Log` referencing entry 2.

- [ ] **Step 4: Apply the promote-or-discard criteria (spec language, verbatim)**

PROMOTE (contract E2B; production sets `A0_SUBSTRATE=e2b`) when the spec
§3 pre-contract action list is satisfied:

> **Pre-contract action list (blocking, cheap):** get paused-storage and
> extra-concurrency pricing in writing (both unpublished); pressure-test for
> a startup discount (list price consumes the budget top); confirm the
> Mar-2026-style incident posture in the SLA conversation.

DISCARD/PIVOT per the spec §3 swap conditions and Decision Log 2 reopen
clause:

> **Swap conditions:** sustained ≥2× A0 run-hours (bill ≥$9k) → renegotiate,
> drop to Northflank (after spike T4 verifies its undocumented egress), or
> accept the Hetzner ops tax (~$0.5–0.65k + 0.1–0.2 FTE — reverses the
> zero-ops decision, so it is a posture change, not a line-item change).
> Measured CPU duty ≤15% → re-run the comparison against Vercel Sandbox's
> active-CPU billing if it ships egress control. ≥2 dispatch-blocking vendor
> incidents in a month → activate Daytona.

> Reopen: E2B refuses acceptable terms, or Daytona publishes a >500-vCPU
> tier.

If E2B refuses acceptable terms: activate the Daytona SDK path behind the
same adapter (a second `kind`), and/or fire spike T4 (final task of this
plan). Either way the code in Tasks 2–8 is unchanged — that is the point of
the adapter.

- [ ] **Step 5: Commit the spec update**

```bash
git add docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "docs(a0): T2 spike — E2B contract facts recorded in spec living tail"
```

---

### Task 2: Package scaffold + substrate adapter interface + FakeSubstrate

**Files:**
- Create: `infra/a0/dispatcher/package.json`,
  `infra/a0/dispatcher/src/substrate.js`,
  `infra/a0/dispatcher/src/fake.js`,
  `infra/a0/dispatcher/test/substrate.test.js`

**Interfaces:**
- Produces: `createSubstrate(config)` → substrate (selection by
  `config.kind` only; unknown kind throws). Substrate =
  `{ create({templateId, env}) → Promise<{sandboxId}>,
  exec(sandboxId, cmd, {env={}, onStdout, onStderr, timeoutMs}) →
  Promise<{exitCode}>, destroy(sandboxId) → Promise<void> }`.
  `createFakeSubstrate(config)` additionally exposes `calls` (recorded
  call list) and accepts `config.script.exec(call, execIndex)` →
  `{exitCode?, stdout?: string[], stderr?: string[], throw?: string}` and
  `config.script.createError`, `config.idPrefix`.

- [ ] **Step 1: Write package.json**

```json
{
  "name": "a0-dispatcher",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22" },
  "scripts": { "test": "node --test test/", "start": "node src/dispatcher.js" },
  "dependencies": {}
}
```

(The `e2b` dependency is added in Task 3, where it is first imported.)

- [ ] **Step 2: Write failing tests**

```js
// infra/a0/dispatcher/test/substrate.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createSubstrate } from '../src/substrate.js';

test('unknown substrate kind throws', () => {
  assert.throws(() => createSubstrate({ kind: 'daytona' }), /unknown substrate kind/);
  assert.throws(() => createSubstrate(undefined), /unknown substrate kind/);
});

test('fake substrate: create/exec/destroy recorded; scripted exit codes; stdout delivery', async () => {
  const s = createSubstrate({
    kind: 'fake',
    idPrefix: 'sbx',
    script: { exec: (call, i) => (i === 1
      ? { exitCode: 0, stdout: ['hello', 'world'] }
      : { exitCode: 7 }) },
  });
  const { sandboxId } = await s.create({ templateId: 'env-abc', env: { A: '1' } });
  assert.equal(sandboxId, 'sbx-1');

  const lines = [];
  const r1 = await s.exec(sandboxId, 'echo hi', {
    env: { B: '2' }, onStdout: (chunk) => lines.push(chunk), timeoutMs: 500 });
  assert.equal(r1.exitCode, 0);
  assert.deepEqual(lines, ['hello\n', 'world\n']);

  const r2 = await s.exec(sandboxId, 'false');
  assert.equal(r2.exitCode, 7);

  await s.destroy(sandboxId);
  assert.deepEqual(s.calls.map((c) => c.op), ['create', 'exec', 'exec', 'destroy']);
  assert.deepEqual(s.calls[0], { op: 'create', templateId: 'env-abc', env: { A: '1' } });
  assert.equal(s.calls[1].cmd, 'echo hi');
  assert.deepEqual(s.calls[1].env, { B: '2' });
  assert.equal(s.calls[1].timeoutMs, 500);
});

test('fake substrate: scriptable create error and exec throw', async () => {
  const bad = createSubstrate({ kind: 'fake', script: { createError: 'no capacity' } });
  await assert.rejects(() => bad.create({ templateId: 't', env: {} }), /no capacity/);

  const boom = createSubstrate({ kind: 'fake', script: { exec: () => ({ throw: 'network died' }) } });
  const { sandboxId } = await boom.create({ templateId: 't', env: {} });
  await assert.rejects(() => boom.exec(sandboxId, 'x'), /network died/);
});
```

- [ ] **Step 3: Run to verify failure**

Run (from `infra/a0/dispatcher/`): `npm test`
Expected: FAIL — `Cannot find module '../src/substrate.js'`.

- [ ] **Step 4: Implement substrate.js and fake.js**

```js
// infra/a0/dispatcher/src/substrate.js
// The substrate adapter — the spec's "one thin create/exec/destroy adapter"
// (§3). Everything vendor-specific lives behind these three calls; a vendor
// swap is a config change, not a worker-protocol change (acceptance drill 7).
//
// Contract:
//   createSubstrate(config) → {
//     create({ templateId, env })                            → Promise<{ sandboxId }>
//     exec(sandboxId, cmd, { env={}, onStdout, onStderr, timeoutMs })
//                                                            → Promise<{ exitCode }>
//     destroy(sandboxId)                                     → Promise<void>
//   }
// Selection is by config.kind ONLY ('e2b' | 'fake').
import { createFakeSubstrate } from './fake.js';

export function createSubstrate(config) {
  switch (config?.kind) {
    case 'fake': return createFakeSubstrate(config);
    default: throw new Error(`unknown substrate kind: ${config?.kind}`);
  }
}
```

```js
// infra/a0/dispatcher/src/fake.js
// In-memory substrate: the test double AND the living proof of acceptance
// drill 7 (a second "vendor" is another instance of this behind the same
// contract). Records every call; exec behavior is scriptable.
export function createFakeSubstrate(config = {}) {
  let nextId = 0;
  let execCount = 0;
  const calls = [];
  const script = config.script ?? {};
  return {
    kind: 'fake',
    calls,
    async create({ templateId, env = {} }) {
      calls.push({ op: 'create', templateId, env });
      if (script.createError) throw new Error(script.createError);
      nextId += 1;
      return { sandboxId: `${config.idPrefix ?? 'fake'}-${nextId}` };
    },
    async exec(sandboxId, cmd, { env = {}, onStdout, onStderr, timeoutMs } = {}) {
      const call = { op: 'exec', sandboxId, cmd, env, timeoutMs };
      calls.push(call);
      execCount += 1;
      const behavior = script.exec ? script.exec(call, execCount) : {};
      for (const line of behavior.stdout ?? []) onStdout?.(`${line}\n`);
      for (const line of behavior.stderr ?? []) onStderr?.(`${line}\n`);
      if (behavior.throw) throw new Error(behavior.throw);
      return { exitCode: behavior.exitCode ?? 0 };
    },
    async destroy(sandboxId) {
      calls.push({ op: 'destroy', sandboxId });
    },
  };
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `npm test` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add infra/a0/dispatcher/package.json infra/a0/dispatcher/src/substrate.js infra/a0/dispatcher/src/fake.js infra/a0/dispatcher/test/substrate.test.js
git commit -m "feat(a0): substrate adapter contract + scriptable FakeSubstrate"
```

---

### Task 3: E2B substrate behind the same contract

**Files:**
- Modify: `infra/a0/dispatcher/package.json` (add the `e2b` dependency),
  `infra/a0/dispatcher/src/substrate.js` (add the `'e2b'` case)
- Create: `infra/a0/dispatcher/src/e2b.js`
- Modify: `infra/a0/dispatcher/test/substrate.test.js` (add surface test)

**Interfaces:**
- Consumes: the `e2b` npm SDK v2 — surface verified against the JS SDK
  v2.0.2 reference (2026-07-23): `Sandbox.create(template?, opts)` with
  `envs`/`timeoutMs`, `Sandbox.connect(sandboxId, opts)` (auto-resumes a
  paused sandbox), `sandbox.commands.run(cmd, { envs, onStdout, onStderr,
  timeoutMs })` → `{ exitCode, stdout, stderr }`, `sandbox.kill()`,
  `sandbox.sandboxId`.
- Produces: `createE2bSubstrate(config)` implementing the Task 2 contract.
  Config: `{ kind:'e2b', apiKey?, sandboxTimeoutMs?, createOpts? }` —
  `apiKey` falls back to the SDK's own `E2B_API_KEY` env resolution;
  `createOpts` is the documented escape hatch for vendor-specific create
  options (e.g. E2B internet-access/egress settings) so they stay config
  and never widen the adapter contract.

- [ ] **Step 1: Add the dependency**

Edit `package.json` `"dependencies"` to:

```json
  "dependencies": { "e2b": "^2.0.2" }
```

Run: `npm install` — Expected: `e2b` installs cleanly on Node 22.

- [ ] **Step 2: Add a failing surface test**

Append to `test/substrate.test.js`:

```js
test('e2b adapter exposes the same three-call surface (no network at construction)', () => {
  const s = createSubstrate({ kind: 'e2b', apiKey: 'e2b_dummy_key' });
  assert.equal(s.kind, 'e2b');
  assert.equal(typeof s.create, 'function');
  assert.equal(typeof s.exec, 'function');
  assert.equal(typeof s.destroy, 'function');
});
```

Run: `npm test` — Expected: FAIL — `unknown substrate kind: e2b`.

- [ ] **Step 3: Implement e2b.js and wire the selection case**

```js
// infra/a0/dispatcher/src/e2b.js
// Real substrate: E2B (spec §3). SDK surface verified against the E2B JS
// SDK v2.0.2 reference, 2026-07-23. Template name IS the environment key
// (spec §3): create-from-template is exact-match restore by construction.
import { Sandbox } from 'e2b';

export function createE2bSubstrate(config = {}) {
  const auth = () => (config.apiKey ? { apiKey: config.apiKey } : {});

  return {
    kind: 'e2b',
    async create({ templateId, env = {} }) {
      const sandbox = await Sandbox.create(templateId, {
        ...auth(),
        envs: env,
        // Sandbox lifetime ceiling: the dispatcher destroys explicitly;
        // this is the backstop against leaked sandboxes (default 75 min
        // > workerTimeoutMs default of 60 min).
        timeoutMs: config.sandboxTimeoutMs ?? 75 * 60_000,
        // Vendor-specific create options (e.g. egress/internet-access
        // settings) pass through here from config — the adapter contract
        // stays three calls wide (acceptance drill 7).
        ...(config.createOpts ?? {}),
      });
      return { sandboxId: sandbox.sandboxId };
    },
    async exec(sandboxId, cmd, { env = {}, onStdout, onStderr, timeoutMs } = {}) {
      const sandbox = await Sandbox.connect(sandboxId, auth());
      try {
        const result = await sandbox.commands.run(cmd, {
          envs: env, onStdout, onStderr, timeoutMs });
        return { exitCode: result.exitCode };
      } catch (e) {
        // The e2b SDK throws on nonzero exit; the adapter contract reports
        // exit codes instead — the dispatcher decides what nonzero means.
        if (typeof e?.exitCode === 'number') return { exitCode: e.exitCode };
        throw e;
      }
    },
    async destroy(sandboxId) {
      // connect + instance kill: stays on the SDK surface verified above
      // (connect also resumes a paused sandbox, so kill always lands).
      const sandbox = await Sandbox.connect(sandboxId, auth());
      await sandbox.kill();
    },
  };
}
```

Update `src/substrate.js` in full:

```js
// infra/a0/dispatcher/src/substrate.js
// The substrate adapter — the spec's "one thin create/exec/destroy adapter"
// (§3). Everything vendor-specific lives behind these three calls; a vendor
// swap is a config change, not a worker-protocol change (acceptance drill 7).
//
// Contract:
//   createSubstrate(config) → {
//     create({ templateId, env })                            → Promise<{ sandboxId }>
//     exec(sandboxId, cmd, { env={}, onStdout, onStderr, timeoutMs })
//                                                            → Promise<{ exitCode }>
//     destroy(sandboxId)                                     → Promise<void>
//   }
// Selection is by config.kind ONLY ('e2b' | 'fake').
import { createE2bSubstrate } from './e2b.js';
import { createFakeSubstrate } from './fake.js';

export function createSubstrate(config) {
  switch (config?.kind) {
    case 'e2b': return createE2bSubstrate(config);
    case 'fake': return createFakeSubstrate(config);
    default: throw new Error(`unknown substrate kind: ${config?.kind}`);
  }
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test` — Expected: PASS. (Live create/exec/destroy against a real
E2B sandbox, egress-allowlist behavior, and the SDK's actual
throw-vs-return on nonzero exit are post-T2 checks — listed in Final
Verification, Task 9.)

- [ ] **Step 5: Commit**

```bash
git add infra/a0/dispatcher/package.json infra/a0/dispatcher/package-lock.json infra/a0/dispatcher/src/e2b.js infra/a0/dispatcher/src/substrate.js infra/a0/dispatcher/test/substrate.test.js
git commit -m "feat(a0): E2B substrate behind the adapter contract (SDK v2, template = env key)"
```

---

### Task 4: Worker launch plan — credentials placement (spec §6) + template mapping

**Files:**
- Create: `infra/a0/dispatcher/src/worker-launch.js`,
  `infra/a0/dispatcher/test/worker-launch.test.js`

**Interfaces:**
- Consumes: a claim `{runId, ticketId, fence, token}` (Plan 1
  `POST /claims`) and dispatcher config.
- Produces:
  - `templateFor(claim, config)` → string — `claim.envKey ??
    config.defaultTemplate`. Note: Plan 1's claim response does not carry
    `envKey` yet; when the board later includes ticket `payload.envKey` in
    the claim response (a Plan-1-side one-liner, out of scope here per the
    no-board-changes boundary) it is honored automatically; until then
    every run uses `A0_DEFAULT_TEMPLATE`.
  - `buildLaunchPlan({claim, config})` → `{ env, initCmds, workerCmd,
    usagePath }` where `env` is exactly `{A0_BOARD_URL, A0_RUN_ID,
    A0_RUN_TOKEN, ANTHROPIC_API_KEY}`, `initCmds` is
    `[{cmd, log}]` (`cmd` = real command, `log` = redacted form safe to
    ship), `workerCmd` is the configured (or default) worker invocation
    prefixed with `cd` into the clone, `usagePath` =
    `'/tmp/a0-usage.json'`.
  - Constants `USAGE_PATH`, `WORKDIR`.
- Usage convention (documented here, consumed in Task 5): the worker MAY
  write a JSON object of token-usage fields to `/tmp/a0-usage.json` before
  exiting; the dispatcher `cat`s it and posts it as the Plan 2 usage row.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/dispatcher/test/worker-launch.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildLaunchPlan, templateFor, USAGE_PATH, WORKDIR } from '../src/worker-launch.js';

const claim = { runId: 'r1', ticketId: 't1', fence: 3, token: 'run-token-abc' };
const config = {
  boardUrl: 'https://board.example',
  anthropicApiKey: 'sk-ant-workspace-capped',
  gitToken: 'ghs_SECRETSECRETSECRET',
  repo: 'acme/product',
  defaultTemplate: 'env-default-0000',
  workerCmd: null,
};

test('worker env is exactly the four allowed keys — and never the git token (spec §6)', () => {
  const plan = buildLaunchPlan({ claim, config });
  assert.deepEqual(Object.keys(plan.env).sort(),
    ['A0_BOARD_URL', 'A0_RUN_ID', 'A0_RUN_TOKEN', 'ANTHROPIC_API_KEY']);
  assert.deepEqual(plan.env, {
    A0_BOARD_URL: 'https://board.example',
    A0_RUN_ID: 'r1',
    A0_RUN_TOKEN: 'run-token-abc',
    ANTHROPIC_API_KEY: 'sk-ant-workspace-capped',
  });
  assert.ok(!JSON.stringify(plan.env).includes(config.gitToken),
    'git token must never appear in the worker env');
});

test('git token lives ONLY in the clone remote URL; the loggable form is redacted', () => {
  const plan = buildLaunchPlan({ claim, config });
  const clone = plan.initCmds[0];
  assert.ok(clone.cmd.includes(
    `https://x-access-token:${config.gitToken}@github.com/acme/product.git`));
  assert.ok(!clone.log.includes(config.gitToken),
    'the loggable form of the clone command must not contain the token');
  assert.ok(clone.log.includes('x-access-token:***@github.com/acme/product.git'));
  assert.ok(!plan.workerCmd.includes(config.gitToken));
});

test('worker command: sensible headless default, overridable via config', () => {
  const plan = buildLaunchPlan({ claim, config });
  assert.ok(plan.workerCmd.startsWith(`cd ${WORKDIR} && claude -p `));
  const custom = buildLaunchPlan({ claim,
    config: { ...config, workerCmd: 'codex exec --full-auto work-ticket' } });
  assert.equal(custom.workerCmd, `cd ${WORKDIR} && codex exec --full-auto work-ticket`);
});

test('usage path convention is exported and stable', () => {
  const plan = buildLaunchPlan({ claim, config });
  assert.equal(plan.usagePath, USAGE_PATH);
  assert.equal(USAGE_PATH, '/tmp/a0-usage.json');
});

test('drill 9 (mapping half): same envKey always resolves to the same template', () => {
  assert.equal(templateFor({ ...claim, envKey: 'env-abc123' }, config),
               templateFor({ ...claim, envKey: 'env-abc123' }, config));
  assert.equal(templateFor({ ...claim, envKey: 'env-abc123' }, config), 'env-abc123');
  assert.equal(templateFor(claim, config), 'env-default-0000');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test` — Expected: FAIL — `Cannot find module '../src/worker-launch.js'`.

- [ ] **Step 3: Implement**

```js
// infra/a0/dispatcher/src/worker-launch.js
// Builds the per-claim sandbox launch plan. Credentials placement (spec §6):
// - The git push token appears ONLY inside the clone remote URL — never in
//   any env object handed to the substrate. Env is what a prompt-injected
//   worker reads trivially; the remote URL is reachable by-shape only, and
//   the token is contents-scoped + contained by the sandbox egress
//   allowlist (acceptance drill 3).
// - Board admin (A0_ADMIN_KEY) and merge credentials never appear here:
//   they are absent from the sandbox by construction.
// - ANTHROPIC_API_KEY is the accepted spend credential — per-run injection
//   from a workspace key whose Console spend limit bounds the blast radius.
export const USAGE_PATH = '/tmp/a0-usage.json';
export const WORKDIR = '/home/user/repo';

// Default is a deliberately minimal headless invocation. Real deployments
// override via config.workerCmd (env A0_WORKER_CMD) — harness choice and
// flags are deployment policy, not dispatcher code.
const DEFAULT_WORKER_CMD =
  "claude -p 'You are an A0 board worker. Work your claimed ticket per the doperpowers implementing-tickets protocol: gate it, then implement or park; end at a PR or a park transition.'";

export function templateFor(claim, config) {
  // Template name IS the environment key (spec §3): a deterministic
  // mapping, so the same key always restores the same template
  // (acceptance drill 9). Plan 1's claim response does not carry envKey
  // yet; until the board forwards ticket payload.envKey, the configured
  // default template is used for every run.
  return claim.envKey ?? config.defaultTemplate;
}

export function buildLaunchPlan({ claim, config }) {
  const env = {
    A0_BOARD_URL: config.boardUrl,
    A0_RUN_ID: claim.runId,
    A0_RUN_TOKEN: claim.token,
    ANTHROPIC_API_KEY: config.anthropicApiKey,
  };
  const repoPath = `github.com/${config.repo}.git`;
  const cloneUrl = `https://x-access-token:${config.gitToken}@${repoPath}`;
  const initCmds = [
    {
      cmd: `git clone --depth 50 ${cloneUrl} ${WORKDIR}`,
      log: `git clone --depth 50 https://x-access-token:***@${repoPath} ${WORKDIR}`,
    },
  ];
  const workerCmd = `cd ${WORKDIR} && ${config.workerCmd ?? DEFAULT_WORKER_CMD}`;
  return { env, initCmds, workerCmd, usagePath: USAGE_PATH };
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/dispatcher/src/worker-launch.js infra/a0/dispatcher/test/worker-launch.test.js
git commit -m "feat(a0): worker launch plan — git token in remote URL only, four-key worker env"
```

---

### Task 5: Dispatcher `runOnce` — claim → sandbox → stream → usage → end → destroy

**Files:**
- Create: `infra/a0/dispatcher/src/dispatcher.js`,
  `infra/a0/dispatcher/test/fake-board.js`,
  `infra/a0/dispatcher/test/dispatcher.test.js`,
  `infra/a0/dispatcher/test/no-db.test.js`

**Interfaces:**
- Consumes: Plan 1 board HTTP — `POST /claims` (admin bearer
  `A0_ADMIN_KEY`; 200 `{runId,ticketId,fence,token}` | 204 empty | 423
  paused | 429 capped — the 423/429 arrive with Plan 2's breakers; honored
  from day one), `POST /runs/:id/events` (run bearer; `{kind,body}` →
  `{seq}`), `POST /runs/:id/usage` (run bearer; added by Plan 2 — 404
  until then, tolerated), `POST /runs/:id/end` (run bearer; `{reason:
  'completed'|'worker-failed'}` — Plan 1's run-completion record, posted
  AFTER usage because run-token auth requires a live run; Plan 2's
  failure-ratio breaker reads these reasons). Also: substrate (Task 2/3),
  launch plan (Task 4).
- Produces:
  - `runOnce({config, substrate})` → `{idle:'empty'|'paused'|'capped'}` |
    `{done:true, runId, ticketId, exitCode, shipErrors}` |
    `{error, runId?}` — one testable pass.
  - `makeLineSink({boardUrl, runId, ticketId, token})` → `{ write(chunk),
    close() → Promise<{errors}> }` — buffers partial lines, coalesces each
    stdout/stderr chunk into one `POST /runs/:id/events {kind:'log',
    body:{lines:[...]}}` (Axiom shipping added in Task 6).
  - Config shape (object; env mapping arrives in Task 7): `{ boardUrl,
    adminKey, defaultTemplate, repo, gitToken, anthropicApiKey, workerCmd,
    axiom, initTimeoutMs, workerTimeoutMs }`.

- [ ] **Step 1: Write the fake board server (test helper)**

```js
// infra/a0/dispatcher/test/fake-board.js
// In-test board-service double speaking Plan 1's HTTP contract. The
// dispatcher is fully testable with zero external services: this + the
// FakeSubstrate is the whole world.
import http from 'node:http';

export async function startFakeBoard({ claims = [] } = {}) {
  const events = [];
  const usage = [];
  const ends = [];
  const requests = [];
  const server = http.createServer(async (req, res) => {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    const body = raw ? JSON.parse(raw) : {};
    const auth = (req.headers.authorization ?? '').replace(/^Bearer /, '');
    requests.push({ method: req.method, url: req.url, auth, body });
    const send = (code, obj) => {
      res.writeHead(code, { 'content-type': 'application/json' });
      res.end(obj === undefined ? '' : JSON.stringify(obj));
    };
    const p = req.url.split('?')[0].split('/').filter(Boolean);
    if (req.method === 'POST' && p.length === 1 && p[0] === 'claims') {
      const next = claims.shift() ?? { status: 204 };
      return send(next.status, next.body);
    }
    if (req.method === 'POST' && p.length === 3 && p[0] === 'runs' && p[2] === 'events') {
      events.push({ runId: p[1], auth, kind: body.kind, body: body.body });
      return send(200, { seq: events.length });
    }
    if (req.method === 'POST' && p.length === 3 && p[0] === 'runs' && p[2] === 'usage') {
      usage.push({ runId: p[1], auth, body });
      return send(200, { ok: true });
    }
    if (req.method === 'POST' && p.length === 3 && p[0] === 'runs' && p[2] === 'end') {
      ends.push({ runId: p[1], auth, reason: body.reason });
      return send(200, { ok: true });
    }
    return send(404, { error: 'not-found' });
  });
  await new Promise((r) => server.listen(0, r));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { base, events, usage, ends, requests,
           close: () => new Promise((r) => server.close(r)) };
}
```

- [ ] **Step 2: Write failing tests**

```js
// infra/a0/dispatcher/test/dispatcher.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { runOnce } from '../src/dispatcher.js';
import { createSubstrate } from '../src/substrate.js';
import { startFakeBoard } from './fake-board.js';

export function testConfig(base, overrides = {}) {
  return {
    boardUrl: base,
    adminKey: 'admin-key-1',
    defaultTemplate: 'env-default-0000',
    repo: 'acme/product',
    gitToken: 'ghs_SECRETSECRETSECRET',
    anthropicApiKey: 'sk-ant-workspace-capped',
    workerCmd: null,
    axiom: null,
    initTimeoutMs: 1000,
    workerTimeoutMs: 1000,
    ...overrides,
  };
}

const claimBody = { runId: 'r1', ticketId: 't1', fence: 1, token: 'run-token-1' };

// Scripted vendor behavior shared by the happy-path tests.
export const happyScript = { exec: (call) => {
  if (call.cmd.startsWith('git clone')) return { exitCode: 0 };
  if (call.cmd.startsWith('cat ')) return { exitCode: 0,
    stdout: ['{"input_tokens":100,"output_tokens":7,"cache_read_input_tokens":900}'] };
  return { exitCode: 0, stdout: ['worker line one', 'worker line two'] };
} };

test('idle paths: 204 empty / 423 paused / 429 capped — no sandbox is ever created', async () => {
  const board = await startFakeBoard({ claims: [
    { status: 204 }, { status: 423 }, { status: 429 }] });
  const substrate = createSubstrate({ kind: 'fake' });
  const config = testConfig(board.base);
  assert.deepEqual(await runOnce({ config, substrate }), { idle: 'empty' });
  assert.deepEqual(await runOnce({ config, substrate }), { idle: 'paused' });
  assert.deepEqual(await runOnce({ config, substrate }), { idle: 'capped' });
  assert.equal(substrate.calls.length, 0);
  assert.ok(board.requests.every((r) => r.auth === 'admin-key-1'));
  await board.close();
});

test('happy path: claim → create(template) → init → worker streamed to events → usage → destroy', async () => {
  const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
  const substrate = createSubstrate({ kind: 'fake', script: happyScript });
  const out = await runOnce({ config: testConfig(board.base), substrate });
  assert.equal(out.done, true);
  assert.equal(out.runId, 'r1');
  assert.equal(out.exitCode, 0);
  assert.equal(out.shipErrors, 0);

  const create = substrate.calls.find((c) => c.op === 'create');
  assert.equal(create.templateId, 'env-default-0000');

  const logEvents = board.events.filter((e) => e.kind === 'log');
  const lines = logEvents.flatMap((e) => e.body.lines);
  assert.deepEqual(lines, ['worker line one', 'worker line two']);
  assert.ok(logEvents.every((e) => e.auth === 'run-token-1'),
    'events must use the per-run bearer, never the admin key');

  assert.equal(board.usage.length, 1);
  assert.equal(board.usage[0].runId, 'r1');
  assert.equal(board.usage[0].auth, 'run-token-1');
  assert.equal(board.usage[0].body.input_tokens, 100);

  assert.deepEqual(board.ends,
    [{ runId: 'r1', auth: 'run-token-1', reason: 'completed' }],
    'run end must be recorded after usage, with the run token');

  assert.equal(substrate.calls.at(-1).op, 'destroy');
  await board.close();
});

test('drill 3 (inspection half): git token reaches no substrate env and no board-shipped byte', async () => {
  const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
  const substrate = createSubstrate({ kind: 'fake', script: happyScript });
  const config = testConfig(board.base);
  await runOnce({ config, substrate });

  for (const call of substrate.calls) {
    assert.ok(!JSON.stringify(call.env ?? {}).includes(config.gitToken),
      `git token leaked into ${call.op} env`);
  }
  const workerExec = substrate.calls.find((c) => c.op === 'exec' && c.env?.A0_RUN_TOKEN);
  assert.deepEqual(Object.keys(workerExec.env).sort(),
    ['A0_BOARD_URL', 'A0_RUN_ID', 'A0_RUN_TOKEN', 'ANTHROPIC_API_KEY']);
  assert.ok(!JSON.stringify(workerExec.env).includes(config.adminKey),
    'board admin key must be absent from the sandbox');
  // The clone command itself carries the token — by design, remote URL only:
  assert.ok(substrate.calls.some((c) => c.op === 'exec' && c.cmd.includes(config.gitToken)));
  // ...but nothing shipped to the board ever does:
  assert.ok(!JSON.stringify(board.requests).includes(config.gitToken));
  await board.close();
});

test('init failure: redacted event, error return, sandbox destroyed', async () => {
  const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
  const substrate = createSubstrate({ kind: 'fake', script: { exec: (call) =>
    call.cmd.startsWith('git clone') ? { exitCode: 128 } : { exitCode: 0 } } });
  const config = testConfig(board.base);
  const out = await runOnce({ config, substrate });
  assert.equal(out.error, 'init-failed');
  assert.equal(substrate.calls.at(-1).op, 'destroy');
  const line = board.events[0].body.lines[0];
  assert.ok(line.includes('init failed'));
  assert.ok(!line.includes(config.gitToken), 'failure event must use the redacted form');
  await board.close();
});

test('destroy-on-error: a throwing exec ends the attempt, destroys, and returns {error}', async () => {
  const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
  const substrate = createSubstrate({ kind: 'fake', script: { exec: (call) =>
    call.cmd.startsWith('git clone') ? { exitCode: 0 } : { throw: 'sandbox network died' } } });
  const out = await runOnce({ config: testConfig(board.base), substrate });
  assert.match(out.error, /sandbox network died/);
  assert.equal(out.runId, 'r1');
  assert.equal(substrate.calls.at(-1).op, 'destroy');
  await board.close();
});

test('create failure surfaces as {error} without a destroy call (nothing to destroy)', async () => {
  const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
  const substrate = createSubstrate({ kind: 'fake', script: { createError: 'no capacity' } });
  const out = await runOnce({ config: testConfig(board.base), substrate });
  assert.match(out.error, /no capacity/);
  assert.ok(!substrate.calls.some((c) => c.op === 'destroy'));
  await board.close();
});

test('unparseable usage file: run still completes; no usage row posted', async () => {
  const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
  const substrate = createSubstrate({ kind: 'fake', script: { exec: (call) => {
    if (call.cmd.startsWith('git clone')) return { exitCode: 0 };
    if (call.cmd.startsWith('cat ')) return { exitCode: 1, stderr: ['No such file'] };
    return { exitCode: 0 };
  } } });
  const out = await runOnce({ config: testConfig(board.base), substrate });
  assert.equal(out.done, true);
  assert.equal(board.usage.length, 0);
  await board.close();
});
```

```js
// infra/a0/dispatcher/test/no-db.test.js
// Spec property, worth a test: the dispatcher NEVER touches the database.
// Its only board credential is A0_ADMIN_KEY over HTTP (spec §1/§2/§6).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

test('dispatcher speaks board HTTP only: no pg dependency, no DATABASE_URL anywhere', () => {
  const pkg = JSON.parse(readFileSync(
    fileURLToPath(new URL('../package.json', import.meta.url)), 'utf8'));
  assert.deepEqual(Object.keys(pkg.dependencies), ['e2b']);
  const srcDir = fileURLToPath(new URL('../src', import.meta.url));
  for (const f of readdirSync(srcDir)) {
    const text = readFileSync(join(srcDir, f), 'utf8');
    assert.ok(!text.includes('DATABASE_URL'), `${f} references DATABASE_URL`);
    assert.ok(!/from ['"]pg['"]/.test(text), `${f} imports pg`);
  }
});
```

- [ ] **Step 3: Run to verify failure**

Run: `npm test`
Expected: `dispatcher.test.js` FAILS with
`Cannot find module '../src/dispatcher.js'`. (`no-db.test.js` passes
already — after Task 3 the dependency list is exactly `['e2b']` and no
source file references `pg` or `DATABASE_URL`; it exists to keep that true
forever, and it is the red bar if anyone ever adds a DB path.)

- [ ] **Step 4: Implement dispatcher.js (runOnce + line sink)**

```js
// infra/a0/dispatcher/src/dispatcher.js
// The dispatch loop (spec §2/§3). One pass = claim → create sandbox from
// the environment-key template → init (clone; token only in the remote
// URL) → run the worker streaming stdout/stderr into the session log →
// collect the optional usage file → destroy. The dispatcher performs NO
// ticket transitions: workers own those with their per-run token + fence.
// A failed pass ends that attempt only — the board's lease reclaim
// (Plan 1 reconciler) is the recovery path, resuming from the session log
// on a fresh claim.
import { buildLaunchPlan, templateFor } from './worker-launch.js';
import { createSubstrate } from './substrate.js';

async function post(url, bearer, body) {
  return fetch(url, {
    method: 'POST',
    headers: { authorization: `Bearer ${bearer}`,
               'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// Coalesces stream chunks into line batches; each batch is one
// POST /runs/:id/events {kind:'log', body:{lines}} — the session-event
// append that doubles as the lease heartbeat (spec §2/§4). Ship failures
// are counted, not fatal: if the board is unreachable the lease expires
// and the reconciler reclaims — that is the designed recovery, not a
// dispatcher concern.
export function makeLineSink({ boardUrl, runId, ticketId, token }) {
  let buf = '';
  let errors = 0;
  let chain = Promise.resolve();

  function shipBatch(lines) {
    if (lines.length === 0) return;
    chain = chain.then(async () => {
      try {
        const res = await post(`${boardUrl}/runs/${runId}/events`, token,
          { kind: 'log', body: { lines } });
        if (res.status !== 200) errors += 1;
      } catch {
        errors += 1;
      }
    });
  }

  return {
    write(chunk) {
      buf += chunk;
      const parts = buf.split('\n');
      buf = parts.pop();
      shipBatch(parts.filter((l) => l.length > 0));
    },
    async close() {
      if (buf.length > 0) { shipBatch([buf]); buf = ''; }
      await chain;
      return { errors };
    },
  };
}

export async function runOnce({ config, substrate }) {
  const claimRes = await post(`${config.boardUrl}/claims`, config.adminKey);
  if (claimRes.status === 204) return { idle: 'empty' };
  if (claimRes.status === 423) return { idle: 'paused' };  // breaker pause (Plan 2)
  if (claimRes.status === 429) return { idle: 'capped' };  // admission cap (Plan 2)
  if (claimRes.status !== 200)
    return { error: `POST /claims: unexpected status ${claimRes.status}` };
  const claim = await claimRes.json();

  let sandboxId = null;
  try {
    ({ sandboxId } = await substrate.create({
      templateId: templateFor(claim, config), env: {} }));
    const plan = buildLaunchPlan({ claim, config });

    for (const init of plan.initCmds) {
      const r = await substrate.exec(sandboxId, init.cmd,
        { timeoutMs: config.initTimeoutMs });
      if (r.exitCode !== 0) {
        // Ship the REDACTED form only — init.cmd carries the git token.
        await post(`${config.boardUrl}/runs/${claim.runId}/events`, claim.token,
          { kind: 'log', body: { lines:
            [`dispatcher: init failed exit=${r.exitCode} cmd=${init.log}`] } })
          .catch(() => {});
        return { error: 'init-failed', runId: claim.runId };
      }
    }

    const sink = makeLineSink({ boardUrl: config.boardUrl, runId: claim.runId,
      ticketId: claim.ticketId, token: claim.token, axiom: config.axiom });
    const worker = await substrate.exec(sandboxId, plan.workerCmd, {
      env: plan.env,
      onStdout: (chunk) => sink.write(chunk),
      onStderr: (chunk) => sink.write(chunk),
      timeoutMs: config.workerTimeoutMs,
    });
    const { errors: shipErrors } = await sink.close();

    // Usage convention: the worker MAY write token-usage JSON to
    // /tmp/a0-usage.json before exiting. POST /runs/:id/usage is Plan 2's
    // cost-meter endpoint; until it lands the board answers 404 and the
    // row is simply not recorded — best-effort by design.
    let usageRaw = '';
    const catRes = await substrate.exec(sandboxId, `cat ${plan.usagePath}`, {
      onStdout: (chunk) => { usageRaw += chunk; }, timeoutMs: 30_000 });
    if (catRes.exitCode === 0) {
      let parsed = null;
      try { parsed = JSON.parse(usageRaw); } catch { parsed = null; }
      if (parsed) {
        await post(`${config.boardUrl}/runs/${claim.runId}/usage`,
          claim.token, parsed).catch(() => {});
      }
    }

    // Record run completion (Plan 1 POST /runs/:id/end) — AFTER usage,
    // because run-token auth requires a live run. Plan 2's failure-ratio
    // breaker reads these reasons; abnormal passes (init-failed, thrown
    // exec) deliberately skip this and resolve via lease reclaim
    // ('lease-expired'), which the breaker also counts as failure.
    await post(`${config.boardUrl}/runs/${claim.runId}/end`, claim.token,
      { reason: worker.exitCode === 0 ? 'completed' : 'worker-failed' })
      .catch(() => {});

    return { done: true, runId: claim.runId, ticketId: claim.ticketId,
             exitCode: worker.exitCode, shipErrors };
  } catch (e) {
    return { error: String(e?.message ?? e), runId: claim.runId };
  } finally {
    if (sandboxId) await substrate.destroy(sandboxId).catch(() => {});
  }
}
```

(`makeLineSink` accepts and currently ignores `axiom` and `ticketId` extras
passed by `runOnce`; Task 6 puts both to use. `main()` and `configFromEnv`
arrive in Task 7 — until then the module is library-only, which is exactly
what the tests exercise.)

- [ ] **Step 5: Run tests to verify pass**

Run: `npm test` — Expected: PASS, all files.

- [ ] **Step 6: Commit**

```bash
git add infra/a0/dispatcher/src/dispatcher.js infra/a0/dispatcher/test/fake-board.js infra/a0/dispatcher/test/dispatcher.test.js infra/a0/dispatcher/test/no-db.test.js
git commit -m "feat(a0): dispatcher runOnce — claim, sandbox lifecycle, event streaming, usage, destroy"
```

---

### Task 6: Axiom log shipping — observability as a disposable view (spec §8, drill 5)

**Files:**
- Modify: `infra/a0/dispatcher/src/dispatcher.js` (`makeLineSink` gains the
  Axiom branch)
- Create: `infra/a0/dispatcher/test/axiom.test.js`

**Interfaces:**
- Consumes: Axiom HTTP ingest —
  `POST {axiom.url}/v1/datasets/{axiom.dataset}/ingest` with bearer
  `axiom.token`, body = JSON array of records; every record stamped
  `run_id` / `ticket_id` / `line` (spec §8: per-run trace is one query).
- Produces: `makeLineSink({boardUrl, runId, ticketId, token, axiom})` —
  same surface; when `axiom` is null the branch is skipped entirely. Axiom
  failures are swallowed (view doctrine): they never count as ship errors
  and never affect the run.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/dispatcher/test/axiom.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { runOnce } from '../src/dispatcher.js';
import { createSubstrate } from '../src/substrate.js';
import { startFakeBoard } from './fake-board.js';
import { testConfig, happyScript } from './dispatcher.test.js';

async function startFakeAxiom() {
  const ingested = [];
  const server = http.createServer(async (req, res) => {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    ingested.push({ url: req.url,
      auth: (req.headers.authorization ?? '').replace(/^Bearer /, ''),
      records: JSON.parse(raw) });
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('{}');
  });
  await new Promise((r) => server.listen(0, r));
  return { base: `http://127.0.0.1:${server.address().port}`, ingested,
           close: () => new Promise((r) => server.close(r)) };
}

const claimBody = { runId: 'r1', ticketId: 't1', fence: 1, token: 'run-token-1' };

test('with AXIOM configured, every log line ships to the dataset stamped run_id/ticket_id', async () => {
  const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
  const axiom = await startFakeAxiom();
  const substrate = createSubstrate({ kind: 'fake', script: happyScript });
  const config = testConfig(board.base, {
    axiom: { token: 'axiom-token', dataset: 'a0-logs', url: axiom.base } });
  const out = await runOnce({ config, substrate });
  assert.equal(out.done, true);

  const records = axiom.ingested.flatMap((i) => i.records);
  assert.deepEqual(records.map((r) => r.line),
    ['worker line one', 'worker line two']);
  assert.ok(records.every((r) => r.run_id === 'r1' && r.ticket_id === 't1'));
  assert.ok(axiom.ingested.every((i) =>
    i.url === '/v1/datasets/a0-logs/ingest' && i.auth === 'axiom-token'));
  await board.close(); await axiom.close();
});

test('drill 5 (view half): the session log is identical with Axiom on, off, or dead', async () => {
  const outcomes = [];
  const axiomConfigs = [
    null,                                                              // off
    'live',                                                            // on
    { token: 'axiom-token', dataset: 'a0-logs',
      url: 'http://127.0.0.1:9' },                                     // dead endpoint
  ];
  for (const mode of axiomConfigs) {
    const board = await startFakeBoard({ claims: [{ status: 200, body: claimBody }] });
    const axiom = mode === 'live' ? await startFakeAxiom() : null;
    const substrate = createSubstrate({ kind: 'fake', script: happyScript });
    const config = testConfig(board.base, {
      axiom: mode === 'live'
        ? { token: 'axiom-token', dataset: 'a0-logs', url: axiom.base }
        : mode });
    const out = await runOnce({ config, substrate });
    outcomes.push({
      done: out.done, exitCode: out.exitCode, shipErrors: out.shipErrors,
      events: board.events.map((e) => ({ kind: e.kind, body: e.body })),
      usage: board.usage.map((u) => u.body),
    });
    await board.close();
    if (axiom) await axiom.close();
  }
  assert.deepEqual(outcomes[0], outcomes[1]);
  assert.deepEqual(outcomes[0], outcomes[2],
    'a dead Axiom endpoint must not change the run outcome or the session log');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test`
Expected: `axiom.test.js` FAILS — the first test finds `ingested` empty
(the sink ignores `axiom` so nothing ships). The drill-5 test may already
pass; the feature test is the driver.

- [ ] **Step 3: Implement — replace `makeLineSink` in `src/dispatcher.js` with**

```js
// Coalesces stream chunks into line batches; each batch is one
// POST /runs/:id/events {kind:'log', body:{lines}} — the session-event
// append that doubles as the lease heartbeat (spec §2/§4) — and, when
// Axiom is configured, one ingest call with every record stamped
// run_id/ticket_id (spec §8). Board ship failures are counted (lease
// expiry + reclaim is the designed recovery). Axiom failures are silently
// dropped: observability data is a disposable view — deleting all of it
// loses nothing (spec §8 doctrine, acceptance drill 5).
export function makeLineSink({ boardUrl, runId, ticketId, token, axiom = null }) {
  let buf = '';
  let errors = 0;
  let chain = Promise.resolve();

  function shipBatch(lines) {
    if (lines.length === 0) return;
    chain = chain.then(async () => {
      try {
        const res = await post(`${boardUrl}/runs/${runId}/events`, token,
          { kind: 'log', body: { lines } });
        if (res.status !== 200) errors += 1;
      } catch {
        errors += 1;
      }
      if (axiom) {
        try {
          await fetch(`${axiom.url}/v1/datasets/${axiom.dataset}/ingest`, {
            method: 'POST',
            headers: { authorization: `Bearer ${axiom.token}`,
                       'content-type': 'application/json' },
            body: JSON.stringify(lines.map((line) => ({
              run_id: runId, ticket_id: ticketId, line }))),
          });
        } catch { /* view only — drop */ }
      }
    });
  }

  return {
    write(chunk) {
      buf += chunk;
      const parts = buf.split('\n');
      buf = parts.pop();
      shipBatch(parts.filter((l) => l.length > 0));
    },
    async close() {
      if (buf.length > 0) { shipBatch([buf]); buf = ''; }
      await chain;
      return { errors };
    },
  };
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test` — Expected: PASS, all files (the dead-endpoint case may
take ~1 s on the refused connection; that is the test working).

- [ ] **Step 5: Commit**

```bash
git add infra/a0/dispatcher/src/dispatcher.js infra/a0/dispatcher/test/axiom.test.js
git commit -m "feat(a0): Axiom log shipping as disposable view — session log unchanged with Axiom on/off/dead"
```

---

### Task 7: Config from env, `main()` loop, and the vendor-swap drill

**Files:**
- Modify: `infra/a0/dispatcher/src/dispatcher.js` (append `configFromEnv`,
  `loop`, `main`)
- Create: `infra/a0/dispatcher/test/config.test.js`

**Interfaces:**
- Consumes: process env.
- Produces:
  - `configFromEnv(env = process.env)` → the Task 5 config object plus
    `{ substrate: {kind, apiKey}, pollMs, concurrency }`. Env contract:
    `A0_BOARD_URL`, `A0_ADMIN_KEY`, `A0_SUBSTRATE` (default `e2b`),
    `E2B_API_KEY`, `A0_DEFAULT_TEMPLATE`, `A0_REPO`, `A0_GIT_TOKEN`,
    `ANTHROPIC_API_KEY`, `A0_WORKER_CMD` (optional), `A0_POLL_MS`
    (default 2000), `A0_CONCURRENCY` (default 1), `A0_INIT_TIMEOUT_MS`
    (default 300000), `A0_WORKER_TIMEOUT_MS` (default 3600000),
    `AXIOM_TOKEN` + `AXIOM_DATASET` (+ optional `AXIOM_URL`, default
    `https://api.axiom.co`) — Axiom config is null unless BOTH are set.
  - `main()` — starts `A0_CONCURRENCY` independent `runOnce` loops.
    Level-triggered polling per spec §2 (no LISTEN): sleep `pollMs` after
    an idle or error pass; claim again immediately after a completed run.
    Errors in a pass never kill the loop.

- [ ] **Step 1: Write failing tests**

```js
// infra/a0/dispatcher/test/config.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { configFromEnv, runOnce } from '../src/dispatcher.js';
import { createSubstrate } from '../src/substrate.js';
import { startFakeBoard } from './fake-board.js';
import { testConfig, happyScript } from './dispatcher.test.js';

test('configFromEnv: full mapping with defaults', () => {
  const c = configFromEnv({
    A0_BOARD_URL: 'https://board.example',
    A0_ADMIN_KEY: 'admin-1',
    A0_DEFAULT_TEMPLATE: 'env-default-0000',
    A0_REPO: 'acme/product',
    A0_GIT_TOKEN: 'ghs_x',
    ANTHROPIC_API_KEY: 'sk-ant-x',
    E2B_API_KEY: 'e2b_x',
  });
  assert.equal(c.boardUrl, 'https://board.example');
  assert.equal(c.adminKey, 'admin-1');
  assert.deepEqual(c.substrate, { kind: 'e2b', apiKey: 'e2b_x' });
  assert.equal(c.defaultTemplate, 'env-default-0000');
  assert.equal(c.repo, 'acme/product');
  assert.equal(c.gitToken, 'ghs_x');
  assert.equal(c.anthropicApiKey, 'sk-ant-x');
  assert.equal(c.workerCmd, null);
  assert.equal(c.pollMs, 2000);
  assert.equal(c.concurrency, 1);
  assert.equal(c.initTimeoutMs, 300000);
  assert.equal(c.workerTimeoutMs, 3600000);
  assert.equal(c.axiom, null);
});

test('configFromEnv: axiom only when BOTH token and dataset are set; overrides honored', () => {
  const base = {
    A0_BOARD_URL: 'u', A0_ADMIN_KEY: 'k', A0_DEFAULT_TEMPLATE: 't',
    A0_REPO: 'r/r', A0_GIT_TOKEN: 'g', ANTHROPIC_API_KEY: 'a',
  };
  assert.equal(configFromEnv({ ...base, AXIOM_TOKEN: 'x' }).axiom, null);
  assert.deepEqual(
    configFromEnv({ ...base, AXIOM_TOKEN: 'x', AXIOM_DATASET: 'd' }).axiom,
    { token: 'x', dataset: 'd', url: 'https://api.axiom.co' });
  const c = configFromEnv({ ...base, A0_SUBSTRATE: 'fake',
    A0_POLL_MS: '500', A0_CONCURRENCY: '8', A0_WORKER_CMD: 'codex exec x' });
  assert.equal(c.substrate.kind, 'fake');
  assert.equal(c.pollMs, 500);
  assert.equal(c.concurrency, 8);
  assert.equal(c.workerCmd, 'codex exec x');
});

test('drill 7 (local half): flipping ONLY the substrate config swaps vendors; board traffic is byte-identical', async () => {
  const claim = { runId: 'r1', ticketId: 't1', fence: 1, token: 'run-token-1' };
  const results = [];
  // Two distinct substrate instances behind the one contract — vendor A and
  // the stand-in for the Daytona-shaped vendor B. Nothing else varies.
  for (const substrateConfig of [
    { kind: 'fake', idPrefix: 'vendorA', script: happyScript },
    { kind: 'fake', idPrefix: 'vendorB', script: happyScript },
  ]) {
    const board = await startFakeBoard({ claims: [{ status: 200, body: claim }] });
    const substrate = createSubstrate(substrateConfig);
    const out = await runOnce({ config: testConfig(board.base), substrate });
    results.push({
      done: out.done, exitCode: out.exitCode,
      events: board.events.map((e) => ({ kind: e.kind, body: e.body })),
      usage: board.usage.map((u) => u.body),
      workerEnvKeys: Object.keys(
        substrate.calls.find((c) => c.op === 'exec' && c.env?.A0_RUN_TOKEN).env).sort(),
    });
    await board.close();
  }
  assert.deepEqual(results[0], results[1],
    'worker protocol, session-log traffic, and usage rows must not vary by vendor');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm test` — Expected: FAIL —
`The requested module '../src/dispatcher.js' does not provide an export named 'configFromEnv'`.

- [ ] **Step 3: Implement — append to `src/dispatcher.js`**

```js
export function configFromEnv(env = process.env) {
  return {
    boardUrl: env.A0_BOARD_URL,
    adminKey: env.A0_ADMIN_KEY,
    substrate: { kind: env.A0_SUBSTRATE ?? 'e2b', apiKey: env.E2B_API_KEY },
    defaultTemplate: env.A0_DEFAULT_TEMPLATE,
    repo: env.A0_REPO,
    gitToken: env.A0_GIT_TOKEN,
    anthropicApiKey: env.ANTHROPIC_API_KEY,
    workerCmd: env.A0_WORKER_CMD ?? null,
    pollMs: Number(env.A0_POLL_MS ?? 2000),
    concurrency: Number(env.A0_CONCURRENCY ?? 1),
    initTimeoutMs: Number(env.A0_INIT_TIMEOUT_MS ?? 300_000),
    workerTimeoutMs: Number(env.A0_WORKER_TIMEOUT_MS ?? 3_600_000),
    axiom: env.AXIOM_TOKEN && env.AXIOM_DATASET
      ? { token: env.AXIOM_TOKEN, dataset: env.AXIOM_DATASET,
          url: env.AXIOM_URL ?? 'https://api.axiom.co' }
      : null,
  };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function loop(deps, pollMs) {
  for (;;) {
    let out;
    try {
      out = await runOnce(deps);
    } catch (e) {
      out = { error: String(e?.message ?? e) };
    }
    if (out.error) console.error('a0-dispatcher: pass failed:', out.error, out.runId ?? '');
    if (out.done) console.log(
      `a0-dispatcher: run ${out.runId} done exit=${out.exitCode} shipErrors=${out.shipErrors}`);
    // Level-triggered polling (spec §2, no LISTEN): back off only when
    // idle or errored; after a completed run, claim again immediately.
    if (out.idle || out.error) await sleep(pollMs);
  }
}

export async function main() {
  const config = configFromEnv();
  const substrate = createSubstrate(config.substrate);
  console.log(`a0-dispatcher: substrate=${config.substrate.kind} ` +
    `board=${config.boardUrl} concurrency=${config.concurrency} pollMs=${config.pollMs}`);
  // N independent claim loops in one process. Safe at any N: claims are
  // serialized by the board's atomic claim transaction (Plan 1), so loops
  // never double-claim — concurrency here is just how many runs this
  // process shepherds at once.
  await Promise.all(Array.from({ length: config.concurrency },
    () => loop({ config, substrate }, config.pollMs)));
}

if (import.meta.url === `file://${process.argv[1]}`) await main();
```

- [ ] **Step 4: Run tests to verify pass**

Run: `npm test` — Expected: PASS, all files.

- [ ] **Step 5: Commit**

```bash
git add infra/a0/dispatcher/src/dispatcher.js infra/a0/dispatcher/test/config.test.js
git commit -m "feat(a0): env config + level-triggered main loop; vendor-swap drill green"
```

---

### Task 8: Deployment note — runbook, secrets placement, template recipe, Render blueprint

**Files:**
- Create: `infra/a0/dispatcher/README.md`,
  `infra/a0/dispatcher/Dockerfile`,
  `infra/a0/dispatcher/render.yaml`,
  `infra/a0/dispatcher/templates/e2b.Dockerfile`

**Interfaces:**
- Consumes: `main()` (Task 7) and its env contract.

- [ ] **Step 1: Write README.md (the runbook)**

```markdown
# A0 dispatcher (Plan 3 of 4)

Implements spec §3 (compute plane) + §6 (credentials placement) + the §8
log-shipping sliver: `docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md`.

One small always-on process next to the board service (Render/Fly, spec §1
deployment posture). **One instance is enough and is the default**: claims
are already serialized by the board's atomic claim transaction, so a second
instance would be safe (it just races claims and loses politely) but buys
nothing at A0. Scale within the instance via `A0_CONCURRENCY`.

The dispatcher never touches the database — board-service HTTP only
(enforced by `test/no-db.test.js`). It performs no ticket transitions;
workers own those with their per-run token + fence. A failed pass ends that
attempt (best-effort sandbox destroy); the board's lease reclaim is the
recovery path.

## Run locally (zero external services)

    npm install && npm test          # FakeSubstrate + in-test board server

Against a live local board (Plan 1) with the fake substrate:

    A0_SUBSTRATE=fake A0_BOARD_URL=http://localhost:8080 A0_ADMIN_KEY=dev \
    A0_DEFAULT_TEMPLATE=env-dev A0_REPO=acme/product A0_GIT_TOKEN=dummy \
    ANTHROPIC_API_KEY=dummy npm start

## Env contract

| var | required | meaning |
|---|---|---|
| `A0_BOARD_URL` | yes | board service base URL |
| `A0_ADMIN_KEY` | yes | dispatcher's board credential (machine identity, spec §6) — NEVER enters a sandbox |
| `A0_SUBSTRATE` | no (`e2b`) | substrate kind: `e2b` or `fake` — the drill-7 swap lever |
| `E2B_API_KEY` | for e2b | vendor key |
| `A0_DEFAULT_TEMPLATE` | yes | template (= environment key) used when a claim carries no `envKey` |
| `A0_REPO` | yes | `owner/name` of the repo workers clone |
| `A0_GIT_TOKEN` | yes | contents-scoped push token; injected ONLY into the clone remote URL |
| `ANTHROPIC_API_KEY` | yes | workspace key with a Console spend limit — the bounded spend credential handed to workers |
| `A0_WORKER_CMD` | no | worker invocation run inside the clone; default is a minimal `claude -p` headless call |
| `A0_POLL_MS` | no (2000) | idle/error backoff between passes (level-triggered polling) |
| `A0_CONCURRENCY` | no (1) | parallel claim loops in this process |
| `A0_INIT_TIMEOUT_MS` | no (300000) | clone/init exec timeout |
| `A0_WORKER_TIMEOUT_MS` | no (3600000) | worker exec timeout (sandbox lifetime backstop is 75 min) |
| `AXIOM_TOKEN` + `AXIOM_DATASET` | no | when BOTH set, log lines also ship to Axiom (disposable view — spec §8); `AXIOM_URL` optional |

## Secrets placement (spec §6, reproduced — this table IS the runbook)

| credential | lives | worker can reach? |
|---|---|---|
| git push token (contents-only, branch-protection on) | bundled into the remote URL at sandbox init | by-shape only; contained by scope + E2B egress allowlist |
| board-write credential | board service / reconciler only | no — structurally |
| merge credential | landing path (Actions/runner) only | no — structurally |
| Anthropic API key | injected per run from a workspace key with a Console spend limit | yes — accepted: spend credential, blast radius = the cap |
| DB/observability admin | humans + reconciler | no |

Delivery is platform env (Render/Fly/E2B) — delivery only, never the source
of truth (spec §6: 1Password Service Accounts or Infisical free tier).

## Environment-key templates (spec §3)

One E2B template per environment key; the template NAME is the key
(hash(env-spec) ⊕ hash(lockfiles) ⊕ toolchain digest, computed by the env
certification step). Build from `templates/e2b.Dockerfile`:

    e2b template build --name "$ENV_KEY" --dockerfile templates/e2b.Dockerfile \
      --build-arg BASE_IMAGE="$PINNED_BASE" --build-arg CLAUDE_CODE_VERSION="$PINNED_VERSION"

Every pin (base image digest, harness version) is an input hashed into the
key — same key, same image, byte-identical toolchain (acceptance drill 9;
drift impossible rather than detected). Configure the E2B egress allowlist
(allow github.com + api.anthropic.com + package registries, deny the rest)
on the template/sandbox per the internet-access docs — that allowlist is
the containment half of acceptance drill 3.
```

- [ ] **Step 2: Write Dockerfile, render.yaml, and the template recipe**

```dockerfile
# infra/a0/dispatcher/Dockerfile
# Build context is infra/a0/dispatcher/:
#   docker build -t a0-dispatcher infra/a0/dispatcher/
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src ./src
ENV NODE_ENV=production
CMD ["node", "src/dispatcher.js"]
```

```yaml
# infra/a0/dispatcher/render.yaml
services:
  - type: worker
    name: a0-dispatcher
    runtime: docker
    dockerfilePath: ./Dockerfile
    plan: starter
    numInstances: 1        # claims are serialized by the board; see README
    envVars:
      - key: A0_BOARD_URL
        sync: false
      - key: A0_ADMIN_KEY
        sync: false        # dispatcher machine identity (spec §6)
      - key: A0_SUBSTRATE
        value: e2b
      - key: E2B_API_KEY
        sync: false
      - key: A0_DEFAULT_TEMPLATE
        sync: false
      - key: A0_REPO
        sync: false
      - key: A0_GIT_TOKEN
        sync: false        # contents-scoped; enters sandboxes via clone URL only
      - key: ANTHROPIC_API_KEY
        sync: false        # workspace key with Console spend limit (spec §6)
      - key: A0_CONCURRENCY
        value: "4"
      - key: AXIOM_TOKEN
        sync: false
      - key: AXIOM_DATASET
        sync: false
```

```dockerfile
# infra/a0/dispatcher/templates/e2b.Dockerfile
# Environment-key template recipe (spec §3). Template NAME = environment
# key. Every input here is pinned BY THE CALLER via build args, and those
# pins are part of the hashed env spec — same key, same image,
# byte-identical toolchain (acceptance drill 9).
#   e2b template build --name "$ENV_KEY" --dockerfile templates/e2b.Dockerfile \
#     --build-arg BASE_IMAGE=<digest-pinned base> \
#     --build-arg CLAUDE_CODE_VERSION=<exact version>
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG CLAUDE_CODE_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}
# Project toolchain layers (runtime versions, lockfile-driven dependency
# warmup, the doperpowers plugin) are appended per env spec by the
# certification step that computes the key — this file is the common trunk.
```

- [ ] **Step 3: Verify the container builds and refuses to run half-configured**

Run:
`docker build -t a0-dispatcher infra/a0/dispatcher/ && docker run --rm -e A0_SUBSTRATE=nope a0-dispatcher; echo "exit=$?"`
Expected: image builds; the process exits nonzero with
`unknown substrate kind: nope` (config errors fail loudly at boot, before
any claim).

- [ ] **Step 4: Commit**

```bash
git add infra/a0/dispatcher/README.md infra/a0/dispatcher/Dockerfile infra/a0/dispatcher/render.yaml infra/a0/dispatcher/templates/e2b.Dockerfile
git commit -m "feat(a0): dispatcher deployment runbook — env contract, spec §6 secrets table, template recipe"
```

---

### Task 9: Final verification — spec acceptance drills owned by this plan

**Files:** none except the spec's `## Revision Notes` (coverage record).

- [ ] **Step 1: Full offline suite**

Run (from `infra/a0/dispatcher/`): `npm test`
Expected: all tests PASS with zero external services (FakeSubstrate +
in-test HTTP servers only).

- [ ] **Step 2: Execute the spec's acceptance items this plan owns, as written**

From spec `## Acceptance (behavior-phrased)`:

> 3. A prompt-injected worker attempting to exfiltrate its git token reaches
>    only allowlisted domains; the token cannot touch protected branches or
>    merge anything — its honest blast radius is pushes to unprotected
>    branches, bounded by attempt-key provenance at review and fencing at
>    landing; board-write and merge credentials are absent from the sandbox
>    by inspection.

Local (runs now): the inspection half — `dispatcher.test.js`
"drill 3 (inspection half)" proves the worker env is exactly the four
allowed keys, the git token appears in no substrate env and no
board-shipped byte, and `A0_ADMIN_KEY` never enters the sandbox; the merge
credential does not exist in this package at all (`grep -ri "merge"
infra/a0/dispatcher/src` finds no credential). Re-run:
`node --test test/dispatcher.test.js` → PASS.
POST-T2 (live E2B): configure the egress allowlist on a real sandbox and
verify `curl https://github.com` succeeds while `curl https://example.com`
fails from inside; verify the token is contents-scoped and branch
protection blocks a protected-branch push. (The token's branch-protection
and landing-fence bounds are Plan 1/landing-path properties, verified
there.)

> 7. Swapping the sandbox vendor in the adapter config (E2B→Daytona)
>    requires zero changes to worker protocol, board schema, or session-log
>    format.

Local (runs now): `config.test.js` "drill 7 (local half)" — two distinct
substrate instances behind one contract produce byte-identical board
traffic with only the substrate config varying. Re-run:
`node --test test/config.test.js` → PASS.
POST-T2 (live): the real swap is `A0_SUBSTRATE` + a Daytona adapter file
registered in `substrate.js` (kept warm per spec §3); worker protocol,
board schema, and session-log format files are untouched by construction.

> 9. Restoring the same environment key twice yields byte-identical
>    toolchains (drift impossible by construction).

Local (runs now): `worker-launch.test.js` "drill 9 (mapping half)" — the
key→template mapping is deterministic. Re-run:
`node --test test/worker-launch.test.js` → PASS.
POST-T2 (live E2B): build a template from `templates/e2b.Dockerfile` with
pinned args, create two sandboxes from that template name, and compare
toolchain fingerprints:
`node --version && git --version && claude --version && sha256sum $(which claude)`
must be byte-identical across both sandboxes.

> 5. Deleting the entire Axiom dataset loses no ability to resume, audit, or
>    re-derive any run (observability is a view; the session log is
>    identity).

Local (runs now): `axiom.test.js` "drill 5 (view half)" — the session log
and run outcome are byte-identical with Axiom on, off, or dead; and
structurally, no code path in `src/` reads from Axiom (write-only ingest —
verify by inspection: `grep -r "axiom" infra/a0/dispatcher/src` shows only
the ingest POST). Deleting the dataset therefore cannot affect resume,
audit, or re-derivation, which all read the board's session log. Re-run:
`node --test test/axiom.test.js` → PASS.

- [ ] **Step 3: Cross-plan integration smoke (requires Plan 1 landed; skip if not)**

With the Plan 1 board service running locally
(`docker run -d --name a0-pg -e POSTGRES_PASSWORD=a0 -p 54329:5432 postgres:16`,
then from `infra/a0/board-service/`: `A0_ADMIN_KEY=dev
DATABASE_URL=postgres://postgres:a0@localhost:54329/postgres npm start`):

```bash
curl -s -X POST localhost:8080/tickets -H 'Authorization: Bearer dev' \
  -H 'content-type: application/json' -d '{"id":"smoke-1"}'
curl -s -X POST localhost:8080/tickets/smoke-1/transition -H 'Authorization: Bearer dev' \
  -H 'content-type: application/json' -d '{"from":"backlog","to":"ready-for-agent"}'
cd infra/a0/dispatcher && A0_BOARD_URL=http://localhost:8080 A0_ADMIN_KEY=dev \
A0_DEFAULT_TEMPLATE=env-dev A0_REPO=acme/product A0_GIT_TOKEN=dummy \
ANTHROPIC_API_KEY=dummy node --input-type=module -e "
import { runOnce, configFromEnv } from './src/dispatcher.js';
import { createSubstrate } from './src/substrate.js';
const substrate = createSubstrate({ kind: 'fake', script: { exec: (c) =>
  c.cmd.startsWith('cat') ? { exitCode: 1 } : { exitCode: 0, stdout: ['smoke line'] } } });
console.log(JSON.stringify(await runOnce({ config: configFromEnv(), substrate })));
"
```

Expected: `{"done":true,"runId":"...","ticketId":"smoke-1","exitCode":0,"shipErrors":0}`
and the streamed line is in the real session log:
`docker exec a0-pg psql -U postgres -c "select kind, body from session_event"` →
one `log` row containing `smoke line`.

- [ ] **Step 4: Record coverage in the spec's living tail**

Append to the spec `## Revision Notes`:

```
- <date>: Plan 3 (a0-substrate-dispatcher) implemented — acceptance 3
  (inspection half), 5 (view half), 7 (local half), 9 (mapping half)
  verified by test; live E2B halves of 3/7/9 staged behind spike T2's
  contract verdict. Dispatcher is board-HTTP-only by test (no pg, no
  DATABASE_URL).
```

- [ ] **Step 5: Commit**

```bash
git add docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "docs(a0): record Plan 3 acceptance coverage in spec living tail"
```

---

### Task 10 (CONDITIONAL — fire only on T2 failure or budget hatch): Spike T4 — Northflank egress verification

**Trigger (spec Spikes list, verbatim):**

> **T4** Northflank egress verification (fires only if E2B negotiation
> fails or the budget hatch is needed).

Do NOT execute this task in the normal course of the plan. It activates
only when Task 1's verdict is discard/pivot on price, or when the spec §3
swap condition fires:

> sustained ≥2× A0 run-hours (bill ≥$9k) → renegotiate, drop to Northflank
> (after spike T4 verifies its undocumented egress), or accept the Hetzner
> ops tax

**Question this spike answers:** can Northflank's managed sandboxes express
the containment allowlist — "allow github.com + api.anthropic.com + package
registries, deny everything else" — per sandbox, without BYOC? The research
report (`research/2026-07-23-startup-scale/sandbox-substrate-a0.md` §2.4)
records this as an absence of evidence, and its verdict sets the bar:

> **Budget escape hatch: Northflank (~$1.8k/mo)** if the bill must sit
> mid-budget rather than at the top — accepting undocumented egress control
> and a younger sandbox API (verify both in a spike before committing).

**Files:** none except the spec's living tail.

- [ ] **Step 1: Build the probe**

Create a Northflank trial account, deploy one sandbox/service from a
minimal image (`node:22-slim` suffices), and locate any per-workload egress
policy surface in the dashboard/API (their docs may have moved since
2026-07-23 — search "network policy", "egress", "firewall" in current docs
first).

- [ ] **Step 2: Run and observe**

From inside the sandbox, with the strictest expressible policy applied,
record the outcome of each:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://github.com          # must succeed
curl -sS -o /dev/null -w '%{http_code}\n' https://api.anthropic.com   # must succeed (any HTTP status; connection is the test)
curl -sS -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org  # must succeed
curl -sS --max-time 10 -o /dev/null -w '%{http_code}\n' https://example.com  # MUST FAIL (timeout/refused)
```

Also record: whether the policy is domain-based or CIDR-only, whether it is
per-sandbox or org-wide, and whether it can change at runtime.

- [ ] **Step 3: Record the verdict into the spec's living tail**

Append to the spec `## Surprises & Discoveries`:

```
- **T4 Northflank egress (verified <date>):** allowlist <expressible |
  not expressible> — mechanism: <domain/CIDR/none>, scope:
  <per-sandbox/org>, runtime changes: <yes/no>. Probe results: github
  <ok/fail>, anthropic <ok/fail>, npm <ok/fail>, example.com
  <blocked/open>. Verdict: <Northflank viable as budget hatch |
  eliminated — falls to Daytona/Hetzner per Decision Log 1>.
```

and a dated `## Decision Log` entry updating entry 1 ("Reopen: L via spike
T4").

- [ ] **Step 4: Apply the promote-or-discard criteria**

PROMOTE (Northflank becomes the active budget hatch; write a
`northflank.js` adapter behind the Task 2 contract as its own follow-up
task) only if all four probes pass with a per-sandbox, domain-capable
policy — the security property is "the control that makes
short-lived-token git isolation actually contain a prompt-injected worker"
(spec §3). DISCARD (record and fall back to Daytona or the Hetzner posture
change per spec Decision Log 1) if the allowlist is inexpressible — an
open-egress substrate fails acceptance drill 3 by construction and is not
eligible at any price.

- [ ] **Step 5: Commit the spec update**

```bash
git add docs/doperpowers/specs/2026-07-23-startup-scale-a0-design.md
git commit -m "docs(a0): T4 spike — Northflank egress verdict recorded in spec living tail"
```
