# Codex Workflow Engine (M0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general `workflow` verb to the vendored codex-companion runtime: a JS orchestration script executor whose workers are codex threads — hooks `agent`/`review`/`parallel`/`pipeline`, per-run event journal with content-keyed resume, leaf-level concurrency semaphore, locked job-ledger writes, real cancel/liveness semantics.

**Architecture:** New `runtime/scripts/lib/workflow/` modules (validator, journal, engine) layered on the existing `codex.mjs` primitives; small additive extensions to the connect layer (per-worker config-override spawn) and `state.mjs` (atomic+locked writes). All engine tests run against a transport-faithful mock `codex` binary. Spec: `docs/doperpowers/specs/2026-08-03-codex-workflow-engine-design.md` (v2.2, APPROVED).

**Tech Stack:** Node ≥18 ESM (no new npm dependencies), bash test runners, existing JSON-RPC-over-stdio app-server protocol.

## Global Constraints

- No new npm dependencies anywhere; node core modules only.
- M0 is READ-ONLY: every worker turn uses `sandbox: "read-only"`; no `write` option exists.
- Existing verb contracts (`review`, `adversarial-review`, `task`, `status`, `result`, `cancel`) are untouched except: (a) `cancel`/`status`/`result` gain workflow-job awareness, (b) `state.json` mutation becomes atomic (tmp+rename) AND serialized (lock inside `updateState`) for ALL writers — same outputs, no lost records; the review verb's target resolution is extracted into an exported function it keeps calling.
- The engine never consults `CODEX_COMPANION_APP_SERVER_ENDPOINT`; every worker app-server is a direct child spawn with per-worker `-c` overrides.
- Default `--max-concurrency` is 6, enforced at leaf worker spawns (`agent`/`review`), never in combinators.
- Mock fidelity rule: the mock `codex` binary speaks the REAL JSON-RPC transport shape — derive every notification/response field from `lib/codex.mjs`'s `captureTurn` handlers (lines ~480–560) and `runAppServerTurn`/`runAppServerReview`, never from what the engine wants to consume.
- Test discrimination rule: every new assert must fail against the parent commit with a failure signature naming the defect (run the RED step and record the exact failure line).
- Shell scripts pass `scripts/lint-shell.sh`.
- Commit messages: conventional prefixes, no attribution trailers.
- All paths below are repo-relative; the skill base at runtime is `skills/codex-companion/`.

## File Structure

```
skills/codex-companion/runtime/scripts/lib/workflow/validate.mjs     (Task 2)
skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs      (Task 3)
skills/codex-companion/runtime/scripts/lib/workflow/engine.mjs       (Task 5)
skills/codex-companion/runtime/scripts/lib/app-server.mjs            (Task 4: configOverrides + onSpawn)
skills/codex-companion/runtime/scripts/lib/codex.mjs                 (Task 4: connect passthrough)
skills/codex-companion/runtime/scripts/lib/state.mjs                 (Task 6: atomic write + lock helper)
skills/codex-companion/runtime/scripts/codex-companion.mjs           (Task 6: workflow verb; cancel/status awareness)
skills/codex-companion/runtime/scripts/lib/args.mjs                  (Task 6: workflow flag set — only if verbs parse centrally; else inline)
skills/codex-companion/references/workflows.md                       (Task 8)
skills/codex-companion/SKILL.md                                      (Task 8: verb list line)
tests/codex-companion/mock/codex                                     (Task 1: mock binary)
tests/codex-companion/lib-mock.sh                                    (Task 1: shared test env setup)
tests/codex-companion/run-workflow-tests.sh                          (Task 1: runner)
tests/codex-companion/test-validate.mjs                              (Task 2)
tests/codex-companion/test-journal.mjs                               (Task 3)
tests/codex-companion/test-connect-overrides.mjs                     (Task 4)
tests/codex-companion/test-engine-hooks.mjs                          (Task 5)
tests/codex-companion/test-verb-e2e.sh                               (Task 6)
tests/codex-companion/test-resume.sh                                 (Task 7)
tests/codex-companion/fixtures/                                      (scenario JSONs + fixture scripts)
```

**Interfaces produced (used by Plan B):**
- CLI: `node runtime/scripts/codex-companion.mjs workflow --script <p> [--args json] [--max-concurrency N] [--cwd dir] [--resume run-id]`
- Script contract: `export default async function run({agent, review, parallel, pipeline, log, args}) → any`
- `agent(prompt, {model, effort, schema, label, cwd})` → string | validated object; rejects on hard failure
- `review({base, scope, model, effort, lens, cwd, label})` → `{reviewText, threadId, status}`
- `parallel(thunks)` → array with `null` for failed thunks; `pipeline(items, ...stages)` → per-item chains, thrown stage ⇒ `null` item

---

### Task 1: Mock codex app-server + test scaffold

**Files:**
- Create: `tests/codex-companion/mock/codex`
- Create: `tests/codex-companion/lib-mock.sh`
- Create: `tests/codex-companion/run-workflow-tests.sh`
- Create: `tests/codex-companion/test-mock-selftest.mjs`

**Interfaces:**
- Consumes: protocol shapes from `runtime/scripts/lib/codex.mjs` (captureTurn handlers ~480–560, `runAppServerTurn` ~1095, `runAppServerReview` ~1002) and `lib/app-server.mjs` (`SpawnedCodexAppServerClient.initialize` ~189: `initialize` request → `initialized` notify).
- Produces: a `codex` executable on PATH for all later tasks; scenario control via `CODEX_MOCK_DIR`.

- [ ] **Step 1: Read the real protocol surfaces.** Read `lib/codex.mjs:480-560` (notification cases: `thread/started`, `thread/name/updated`, `turn/started`, `item/started`, `item/completed`, `turn/completed` — record the EXACT field paths each handler reads, e.g. how `lastAgentMessage` and `reviewText` are extracted), `lib/codex.mjs:590-612` (turn/start response handling: `response.turn?.status`), `lib/codex.mjs:1002-1056` (review/start: `delivery`, `target`, `response.reviewThreadId`), and `lib/app-server.mjs:189-230`. Write the observed shapes as comments at the top of the mock.

- [ ] **Step 2: Write the mock binary** at `tests/codex-companion/mock/codex` (mode 755, `#!/usr/bin/env node`). Behavior:

```js
#!/usr/bin/env node
// Mock codex app-server. Speaks the REAL JSON-RPC-over-stdio shapes
// (derived from lib/codex.mjs captureTurn + app-server.mjs — see Step 1
// comments). Controlled by CODEX_MOCK_DIR:
//   scenario.json  { turns: [ {finalMessage|finalRaw|die|hangMs|reviewText|turnStatus}... ] }
//                  consumed in global order via counter file (mkdir lock);
//                  turnStatus: "failed" ⇒ emit turn/completed with the FAILED
//                  status shape and NO error object (the false-green case)
//   turns.jsonl    one line per turn/start|review/start request: {method, params, pid}
//   spawn-<pid>.json   written on start: { argv, cwd }
//   live/<pid>         existence = live server (removed on exit)
//   peak               max simultaneous live/* observed at any turn/start
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

const MOCK = process.env.CODEX_MOCK_DIR;
if (!MOCK) { console.error("CODEX_MOCK_DIR unset"); process.exit(2); }
const args = process.argv.slice(2);
if (args[args.length - 1] !== "app-server") { console.error("mock: only app-server mode"); process.exit(2); }

fs.mkdirSync(path.join(MOCK, "live"), { recursive: true });
fs.writeFileSync(path.join(MOCK, `spawn-${process.pid}.json`),
  JSON.stringify({ argv: args, cwd: process.cwd() }));
const liveFile = path.join(MOCK, "live", String(process.pid));
fs.writeFileSync(liveFile, "");
function cleanup() { try { fs.rmSync(liveFile, { force: true }); } catch {} }
process.on("exit", cleanup);
process.on("SIGTERM", () => { cleanup(); process.exit(0); });

function nextTurnBehavior() {
  // global sequential counter under a mkdir lock
  const lockDir = path.join(MOCK, "counter.lock");
  for (let i = 0; i < 2000; i++) {
    try { fs.mkdirSync(lockDir); break; } catch { /* spin */ }
  }
  try {
    const cFile = path.join(MOCK, "counter");
    const n = fs.existsSync(cFile) ? Number(fs.readFileSync(cFile, "utf8")) : 0;
    fs.writeFileSync(cFile, String(n + 1));
    const scenario = JSON.parse(fs.readFileSync(path.join(MOCK, "scenario.json"), "utf8"));
    return scenario.turns[Math.min(n, scenario.turns.length - 1)] ?? {};
  } finally { fs.rmdirSync(lockDir); }
}

function recordPeak() {
  const live = fs.readdirSync(path.join(MOCK, "live")).length;
  const peakFile = path.join(MOCK, "peak");
  const prev = fs.existsSync(peakFile) ? Number(fs.readFileSync(peakFile, "utf8")) : 0;
  if (live > prev) fs.writeFileSync(peakFile, String(live));
}

let threadSeq = 0;
const send = (msg) => process.stdout.write(JSON.stringify(msg) + "\n");
const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  let msg; try { msg = JSON.parse(line); } catch { return; }
  if (msg.method === "initialize") return send({ id: msg.id, result: {} });
  if (msg.method === "initialized") return;
  if (msg.method === "thread/start" || msg.method === "thread/resume") {
    const id = msg.method === "thread/resume" ? msg.params.threadId : `t-${process.pid}-${++threadSeq}`;
    return send({ id: msg.id, result: { thread: { id } } });
  }
  if (msg.method === "thread/name/set") return send({ id: msg.id, result: {} });
  if (msg.method === "turn/start" || msg.method === "review/start") {
    recordPeak();
    fs.appendFileSync(path.join(MOCK, "turns.jsonl"),
      JSON.stringify({ method: msg.method, params: msg.params, pid: process.pid }) + "\n");
    const b = nextTurnBehavior();
    if (b.die) process.exit(1);
    const finish = () => {
      const threadId = msg.params.threadId;
      const turnId = `turn-${threadId}`;
      send({ method: "turn/started", params: { threadId, turn: { id: turnId, status: "inProgress" } } });
      // >>> Step 1 NOTE: emit the agent-message item and turn/completed with
      // the EXACT field paths captureTurn reads (fill from Step 1 findings).
      const text = msg.method === "review/start"
        ? (b.reviewText ?? "# Codex Review\n\nNo findings.")
        : (b.finalRaw ?? b.finalMessage ?? "mock final message");
      send({ method: "item/completed", params: { threadId, item: { type: "agentMessage", text } } });
      const finalStatus = b.turnStatus ?? "completed";
      send({ method: "turn/completed", params: { threadId, turn: { id: turnId, status: finalStatus } } });
      const result = msg.method === "review/start"
        ? { reviewThreadId: threadId, turn: { id: turnId, status: "completed" } }
        : { turn: { id: turnId, status: "completed" } };
      send({ id: msg.id, result });
    };
    if (b.hangMs) setTimeout(finish, b.hangMs); else finish();
    return;
  }
  send({ id: msg.id, error: { code: -32601, message: `mock: unsupported ${msg.method}` } });
});
```

  The `>>> Step 1 NOTE` line is a build-time instruction: replace the two `item/completed` / `turn/completed` emissions with the exact shapes the Step-1 read established (field names must match what `captureTurn` destructures — if it reads `item.details.text` or `turn.items`, the mock emits that). Delete the NOTE comment once aligned.

- [ ] **Step 3: Write `lib-mock.sh`** (sourced by shell tests):

```bash
#!/usr/bin/env bash
# Shared mock env for codex-companion workflow tests.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../.." && pwd)"
RUNTIME="$REPO_ROOT/skills/codex-companion/runtime/scripts/codex-companion.mjs"
mock_env() {  # $1 = scratch dir
  local scratch="$1"
  mkdir -p "$scratch/mockstate" "$scratch/data"
  export CODEX_MOCK_DIR="$scratch/mockstate"
  export PATH="$TESTS_DIR/mock:$PATH"
  export CLAUDE_PLUGIN_DATA="$scratch/data"
  export CODEX_COMPANION_SESSION_ID="wf-test"
  unset CODEX_COMPANION_APP_SERVER_ENDPOINT || true
}
```

- [ ] **Step 4: Write the runner** `run-workflow-tests.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
fail=0
for t in test-*.mjs; do
  echo "== node $t"; node "$t" || { echo "FAIL: $t"; fail=1; }
done
for t in test-*.sh; do
  echo "== bash $t"; bash "$t" || { echo "FAIL: $t"; fail=1; }
done
[ "$fail" -eq 0 ] && echo "all workflow tests passed"
exit "$fail"
```

- [ ] **Step 5: Write the self-test** `test-mock-selftest.mjs`: spawn the mock (`spawn(path-to-mock, ["-c","model_reasoning_effort=low","app-server"], {env: {...process.env, CODEX_MOCK_DIR: tmp}})` with a scenario `{turns:[{finalMessage:"hello"}]}`), speak raw JSON-RPC: initialize → thread/start → turn/start; assert (a) the final agent message text is `hello`, (b) `spawn-<pid>.json` records the `-c` pair, (c) `live/` empties after child kill. Use `node:assert` and exit non-zero on failure.

- [ ] **Step 6: RED/GREEN.** Run `bash tests/codex-companion/run-workflow-tests.sh`. Expected: self-test PASSES (the mock is self-contained). Discrimination check: temporarily corrupt one emitted field name in the mock (e.g. `turn/completed` → `turn/complete`), rerun, confirm the self-test FAILS naming the missing completion — then revert.

- [ ] **Step 7: Lint + commit.** `scripts/lint-shell.sh` (covers the two new .sh files). `git add tests/codex-companion && git commit -m "test(codex-companion): transport-faithful mock app-server + workflow test scaffold"`

### Task 2: Minimal JSON-schema validator

**Files:**
- Create: `skills/codex-companion/runtime/scripts/lib/workflow/validate.mjs`
- Test: `tests/codex-companion/test-validate.mjs`

**Interfaces:**
- Produces: `validateSchema(value, schema, path="$") → string[]` (empty = valid). Supports exactly: `type` (`object|array|string|number|integer|boolean|null`), `properties`, `required`, `items`, `enum`. Unknown keywords are ignored (permissive by design — the schema also rides `outputSchema` server-side).

- [ ] **Step 1: Write the failing test** `test-validate.mjs` with `node:assert`:

```js
import assert from "node:assert";
import { validateSchema } from "../../skills/codex-companion/runtime/scripts/lib/workflow/validate.mjs";

const FINDER = {
  type: "object", required: ["findings"],
  properties: { findings: { type: "array", items: {
    type: "object", required: ["id", "verdict"],
    properties: { id: { type: "string" },
      verdict: { type: "string", enum: ["CONFIRMED", "REFUTED"] } } } } }
};
assert.deepEqual(validateSchema({ findings: [] }, FINDER), []);
assert.deepEqual(validateSchema({ findings: [{ id: "a", verdict: "CONFIRMED" }] }, FINDER), []);
// syntactically-valid JSON, wrong shape — the exact false-green from the spec review:
assert.ok(validateSchema({ finding: [] }, FINDER).some(e => e.includes("findings")));
assert.ok(validateSchema({ findings: [{ id: 1, verdict: "CONFIRMED" }] }, FINDER)
  .some(e => e.includes(".id") && e.includes("string")));
assert.ok(validateSchema({ findings: [{ id: "a", verdict: "MAYBE" }] }, FINDER)
  .some(e => e.includes("enum")));
assert.ok(validateSchema("nope", FINDER).some(e => e.includes("object")));
assert.deepEqual(validateSchema(3, { type: "integer" }), []);
assert.ok(validateSchema(3.5, { type: "integer" }).length === 1);
console.log("test-validate: ok");
```

- [ ] **Step 2: Run to verify it fails.** `node tests/codex-companion/test-validate.mjs` — Expected: `ERR_MODULE_NOT_FOUND` naming `validate.mjs`.

- [ ] **Step 3: Implement** `validate.mjs`:

```js
export function validateSchema(value, schema, path = "$") {
  const errors = [];
  if (!schema || typeof schema !== "object") return errors;
  if (schema.type) {
    const t = schema.type;
    const ok =
      (t === "object" && value !== null && typeof value === "object" && !Array.isArray(value)) ||
      (t === "array" && Array.isArray(value)) ||
      (t === "string" && typeof value === "string") ||
      (t === "boolean" && typeof value === "boolean") ||
      (t === "number" && typeof value === "number") ||
      (t === "integer" && Number.isInteger(value)) ||
      (t === "null" && value === null);
    if (!ok) { errors.push(`${path}: expected ${t}`); return errors; }
  }
  if (schema.enum && !schema.enum.includes(value)) {
    errors.push(`${path}: not in enum [${schema.enum.join(", ")}]`);
  }
  if (schema.type === "object") {
    for (const key of schema.required ?? []) {
      if (!(key in value)) errors.push(`${path}: missing required "${key}" (have: ${Object.keys(value).join(",") || "none"})`);
    }
    for (const [key, sub] of Object.entries(schema.properties ?? {})) {
      if (key in value) errors.push(...validateSchema(value[key], sub, `${path}.${key}`));
    }
  }
  if (schema.type === "array" && schema.items) {
    value.forEach((item, i) => errors.push(...validateSchema(item, schema.items, `${path}[${i}]`)));
  }
  return errors;
}
```

- [ ] **Step 4: Run to verify it passes.** `node tests/codex-companion/test-validate.mjs` — Expected: `test-validate: ok`.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(codex-companion): minimal structural schema validator for workflow agent() results"`

### Task 3: Event journal, lease, fingerprint

**Files:**
- Create: `skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs`
- Test: `tests/codex-companion/test-journal.mjs`

**Interfaces:**
- Produces:
  - `cacheKey(kind, label, payload) → string` — `kind|label|sha256hex(JSON.stringify(payload))`; caller appends `#<occurrence>`.
  - `appendEvent(journalPath, event)` — one JSON line, synchronous append.
  - `loadJournal(journalPath) → {events, finished: Map<key, event>}` — skips torn/unparseable lines; `started`-without-`finished` keys are NOT in `finished`.
  - `acquireLease(runDir) → {ok, holderPid?}` / `releaseLease(runDir)` — lockfile `lease.json` `{pid, at}`; dead-pid lease is broken automatically (probe with `process.kill(pid, 0)`).
  - `repoFingerprint(cwd) → string` — `sha256hex(HEAD + "\n" + git status --porcelain)`; `"no-git"` outside a repo.

- [ ] **Step 1: Write the failing test** `test-journal.mjs`:

```js
import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { cacheKey, appendEvent, loadJournal, acquireLease, releaseLease, repoFingerprint }
  from "../../skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wfj-"));
const j = path.join(dir, "journal.jsonl");

const k1 = cacheKey("agent", "finder", { prompt: "p1", opts: { effort: "high" } });
assert.equal(k1, cacheKey("agent", "finder", { prompt: "p1", opts: { effort: "high" } }));
assert.notEqual(k1, cacheKey("agent", "finder", { prompt: "p2", opts: { effort: "high" } }));

appendEvent(j, { type: "started", key: k1 + "#0" });
appendEvent(j, { type: "started", key: "agent|b|x#0" });
appendEvent(j, { type: "finished", key: "agent|b|x#0", result: "B" });   // out-of-order finish
appendEvent(j, { type: "finished", key: k1 + "#0", result: "A" });
fs.appendFileSync(j, '{"type":"finished","key":"torn');                   // torn tail
let loaded = loadJournal(j);
assert.equal(loaded.finished.get(k1 + "#0").result, "A");
assert.equal(loaded.finished.get("agent|b|x#0").result, "B");
assert.equal(loaded.finished.size, 2);                                    // torn line ignored
appendEvent(j, { type: "started", key: "agent|c|y#0" });                  // started, never finished
loaded = loadJournal(j);
assert.ok(!loaded.finished.has("agent|c|y#0"));

assert.deepEqual(acquireLease(dir), { ok: true });
assert.equal(acquireLease(dir).ok, false);                                // same live pid holds it
releaseLease(dir);
assert.equal(acquireLease(dir).ok, true);
releaseLease(dir);
fs.writeFileSync(path.join(dir, "lease.json"), JSON.stringify({ pid: 999999, at: 0 }));
assert.equal(acquireLease(dir).ok, true);                                 // dead-pid lease broken
releaseLease(dir);

// SIMULTANEOUS acquisition (the check-then-write race): two child
// processes spin-wait on a barrier file, then both call acquireLease on
// the same dir and print the result. Exactly ONE may win.
import { spawnSync, spawn } from "node:child_process";
const raceDir = fs.mkdtempSync(path.join(os.tmpdir(), "wfl-"));
const barrier = path.join(raceDir, "go");
const kid = `
  import { acquireLease } from ${JSON.stringify(new URL("../../skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs", import.meta.url).href)};
  import fs from "node:fs";
  while (!fs.existsSync(process.argv[2])) {}
  console.log(JSON.stringify(acquireLease(process.argv[1])));
`;
const kids = [1, 2].map(() => spawn(process.execPath, ["--input-type=module", "-e", kid, raceDir, barrier]));
const outs = [];
await Promise.all(kids.map(k => new Promise(res => { let o = ""; k.stdout.on("data", d => o += d); k.on("exit", () => { outs.push(o); res(); }); })));
fs.writeFileSync(barrier, "");   // NOTE: write barrier BEFORE awaiting in real code — see step note
const wins = outs.filter(o => JSON.parse(o).ok === true).length;
assert.equal(wins, 1, `lease race: expected exactly 1 winner, got ${wins}`);

// releaseLease ownership: a process that does NOT hold the lease must not remove it
fs.writeFileSync(path.join(raceDir, "lease.json"), JSON.stringify({ pid: 999998, at: 0 }));
releaseLease(raceDir);            // not ours (pid differs) → must be a no-op
assert.ok(fs.existsSync(path.join(raceDir, "lease.json")), "releaseLease removed a lease it does not own");

// CONTENT-aware fingerprint: same porcelain status, different bytes ⇒ different fp
const repo = fs.mkdtempSync(path.join(os.tmpdir(), "wfr-"));
spawnSync("git", ["init", "-q", "-b", "main"], { cwd: repo });
fs.writeFileSync(path.join(repo, "f.txt"), "one");
spawnSync("git", ["add", "-A"], { cwd: repo });
spawnSync("git", ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c"], { cwd: repo });
fs.writeFileSync(path.join(repo, "f.txt"), "dirty-A");   // file now Modified
const fpA = repoFingerprint(repo);
fs.writeFileSync(path.join(repo, "f.txt"), "dirty-B");   // STILL just Modified in porcelain
assert.notEqual(repoFingerprint(repo), fpA, "fingerprint blind to content changes in already-dirty files");

const fp1 = repoFingerprint(process.cwd());
assert.equal(fp1, repoFingerprint(process.cwd()));
assert.equal(repoFingerprint(dir), "no-git");
console.log("test-journal: ok");
```

  (Step note: order the barrier write before awaiting the children in the actual test file; the snippet shows the assertions, the implementer arranges the async plumbing so both children are running before the barrier appears.)

- [ ] **Step 2: Run to verify it fails.** Expected: `ERR_MODULE_NOT_FOUND` naming `journal.mjs`.

- [ ] **Step 3: Implement** `journal.mjs`:

```js
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

export function cacheKey(kind, label, payload) {
  const h = crypto.createHash("sha256").update(JSON.stringify(payload)).digest("hex").slice(0, 16);
  return `${kind}|${label ?? ""}|${h}`;
}

export function appendEvent(journalPath, event) {
  fs.appendFileSync(journalPath, `${JSON.stringify({ at: new Date().toISOString(), ...event })}\n`);
}

export function loadJournal(journalPath) {
  const events = [];
  const finished = new Map();
  if (!fs.existsSync(journalPath)) return { events, finished };
  for (const line of fs.readFileSync(journalPath, "utf8").split("\n")) {
    if (!line.trim()) continue;
    let ev; try { ev = JSON.parse(line); } catch { continue; }   // torn tail tolerance
    events.push(ev);
    if (ev.type === "finished" && ev.key) finished.set(ev.key, ev);
  }
  return { events, finished };
}

function leasePath(runDir) { return path.join(runDir, "lease.json"); }

export function acquireLease(runDir) {
  const p = leasePath(runDir);
  // Atomic create ("wx") — the ONLY way in; never check-then-write.
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const fd = fs.openSync(p, "wx");
      fs.writeSync(fd, JSON.stringify({ pid: process.pid, at: Date.now() }));
      fs.closeSync(fd);
      return { ok: true };
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
      let holder = null;
      try { holder = JSON.parse(fs.readFileSync(p, "utf8")); } catch { holder = null; }
      if (holder?.pid) {
        try { process.kill(holder.pid, 0); return { ok: false, holderPid: holder.pid }; }
        catch { /* dead holder */ }
      }
      // dead or unreadable holder: remove and try the atomic create once more
      try { fs.rmSync(p, { force: true }); } catch {}
    }
  }
  return { ok: false };
}

export function releaseLease(runDir) {
  // Ownership check: only the holder may release.
  const p = leasePath(runDir);
  try {
    const holder = JSON.parse(fs.readFileSync(p, "utf8"));
    if (holder?.pid !== process.pid) return;
  } catch { return; }
  fs.rmSync(p, { force: true });
}

export function repoFingerprint(cwd, extraPaths = []) {
  // Content-aware: porcelain alone records paths+status, not bytes — a
  // dirty file edited again between runs would slip through. Hash HEAD,
  // the full content diff vs HEAD, every untracked file's blob hash, and
  // any extra file identities the caller cares about (workflow script).
  try {
    const run = (args) => execFileSync("git", args, { cwd, stdio: ["ignore", "pipe", "ignore"], maxBuffer: 64 * 1024 * 1024 }).toString();
    const head = run(["rev-parse", "HEAD"]);
    const diff = run(["diff", "HEAD"]);
    const untracked = run(["ls-files", "--others", "--exclude-standard"]).split("\n").filter(Boolean).sort();
    const untrackedHashes = untracked.map((f) => {
      try { return f + ":" + execFileSync("git", ["hash-object", "--", f], { cwd, stdio: ["ignore", "pipe", "ignore"] }).toString().trim(); }
      catch { return f + ":unreadable"; }
    });
    const extras = extraPaths.map((p) => {
      try { return p + ":" + crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex").slice(0, 12); }
      catch { return p + ":unreadable"; }
    });
    return crypto.createHash("sha256")
      .update([head, diff, untrackedHashes.join("\n"), extras.join("\n")].join("\x00"))
      .digest("hex").slice(0, 16);
  } catch {
    return "no-git";
  }
}
```

  The engine (Task 5) passes `extraPaths: [scriptPath]` so editing the workflow script itself also refuses stale-cache resume. Same-pid re-acquire returns `ok: false` (loud surfacing of a double-resume programming error); the cross-process case compares pids naturally.

- [ ] **Step 4: Run to verify it passes.** `node tests/codex-companion/test-journal.mjs` → `test-journal: ok`.

- [ ] **Step 5: Commit.** `git commit -am "feat(codex-companion): workflow event journal, run lease, repo fingerprint"`

### Task 4: Connect-layer passthrough (per-worker config overrides + pid tracking)

**Files:**
- Modify: `skills/codex-companion/runtime/scripts/lib/app-server.mjs` (SpawnedCodexAppServerClient.initialize ~190)
- Modify: `skills/codex-companion/runtime/scripts/lib/codex.mjs` (`withAppServer` ~613, `runAppServerTurn` ~1095, `runAppServerReview` ~1002)
- Test: `tests/codex-companion/test-connect-overrides.mjs`

**Interfaces:**
- Produces: `runAppServerTurn(cwd, {..., connect})` and `runAppServerReview(cwd, {..., connect})` where `connect = {disableBroker: true, configOverrides: ["k=v", ...], onSpawn: (pid) => void}`. Absent `connect` ⇒ byte-identical behavior to today.

- [ ] **Step 1: Write the failing test** `test-connect-overrides.mjs`: with the mock on PATH and `CODEX_MOCK_DIR` set (scenario one happy turn), call `runAppServerTurn(tmpRepo, {prompt: "hi", connect: {disableBroker: true, configOverrides: ["model_reasoning_effort=xhigh", "developer_instructions=lens text"], onSpawn: (pid) => seen.push(pid)}})`. Assert: (a) result.finalMessage is the scenario text; (b) the mock's `spawn-*.json` argv equals `["-c","model_reasoning_effort=xhigh","-c","developer_instructions=lens text","app-server"]`; (c) `seen.length === 1` and the pid matches the spawn file's name; (d) a second call WITHOUT `connect` still succeeds (broker env unset ⇒ existing broker path spawns direct via `ensureBrokerSession` — set `CODEX_COMPANION_APP_SERVER_ENDPOINT=unix:/nonexistent` for this leg to force the documented no-broker fallback, mirroring production).

- [ ] **Step 2: Run to verify it fails.** Expected: assertion (b) fails — argv is `["app-server"]` (no overrides), and `onSpawn` never fires.

- [ ] **Step 3: Implement.**
  In `app-server.mjs` `SpawnedCodexAppServerClient.initialize`, replace the fixed spawn args:

```js
    const configArgs = (this.options.configOverrides ?? []).flatMap((kv) => ["-c", kv]);
    this.proc = spawn("codex", [...configArgs, "app-server"], {
```

  and after the spawn succeeds (immediately after `this.proc = spawn(...)`):

```js
    this.options.onSpawn?.(this.proc.pid);
```

  In `codex.mjs`, change `withAppServer(cwd, fn)` → `withAppServer(cwd, fn, connect = null)`; when `connect` is set, skip the broker logic entirely: `client = await CodexAppServerClient.connect(cwd, { disableBroker: true, ...connect })` with no broker-retry wrapper. Thread `options.connect` through `runAppServerTurn` and `runAppServerReview`'s `withAppServer(...)` call sites. No other call site changes.

  **Also in this task — export the review target resolver.** Read the review verb's target resolution (`codex-companion.mjs` ~358-420 and the target-building code it calls) and extract/export a pure function `resolveReviewTarget(cwd, {base, scope}) → target` in `codex.mjs` producing EXACTLY the object the verb sends as `review/start`'s `target` today (base wins; scope auto|working-tree|branch semantics unchanged). The verb's own path is refactored to call the same export (behavior-identical — verify by running the existing review-path tests). Extend `test-connect-overrides.mjs`: a `runAppServerReview(cwd, {target: resolveReviewTarget(...), connect})` call against the mock asserts the mock's `turns.jsonl` recorded the `review/start` request with that exact target object — a review that silently reviews the wrong thing must be impossible to miss.

- [ ] **Step 4: Run to verify it passes**, then run the WHOLE existing test surface that touches these files: `tests/claude-code/run-skill-tests.sh` (regression: existing verbs untouched) and `bash tests/codex-companion/run-workflow-tests.sh`.

- [ ] **Step 5: Commit.** `git commit -am "feat(codex-companion): per-worker app-server config overrides + spawn pid callback (additive connect option)"`

### Task 5: The engine — hooks, semaphore, journal integration

**Files:**
- Create: `skills/codex-companion/runtime/scripts/lib/workflow/engine.mjs`
- Test: `tests/codex-companion/test-engine-hooks.mjs`

**Interfaces:**
- Consumes: Tasks 2–4 exports.
- Produces: `runWorkflow(spec) → Promise<{result, agents, durationMs}>` where `spec = {scriptPath, args, cwd, maxConcurrency, runDir, resume, emit}`; `emit(line)` receives progress lines (the verb routes them to stderr + job log). Throws `WorkflowError` with `.reason` (`lease-held`, `fingerprint-mismatch`, `script-error`).

- [ ] **Step 1: Write the failing test** `test-engine-hooks.mjs`. Fixture scripts under `tests/codex-companion/fixtures/`:

  `fx-happy.mjs`:
```js
export default async function run({ agent, parallel, pipeline, log, args }) {
  log("starting");
  const one = await agent("solo", { label: "solo" });
  const par = await parallel([
    () => agent("p1", { label: "p1" }),
    () => agent("boom", { label: "boom" }),     // scenario kills this one twice
    () => agent("p3", { label: "p3" }),
  ]);
  const piped = await pipeline([10, 20],
    (x) => agent(`stage1-${x}`, { label: `s1-${x}` }),
    (prev, orig, i) => (orig === 20 ? (() => { throw new Error("drop"); })() : `${prev}|${orig}|${i}`));
  return { one, par, piped, n: args.n };
}
```

  `fx-schema.mjs`:
```js
const S = { type: "object", required: ["ok"], properties: { ok: { type: "boolean" } } };
export default async function run({ agent }) {
  return agent("give me json", { label: "js", schema: S });
}
```

  `fx-cap.mjs`:
```js
export default async function run({ agent }) {
  // bare Promise.all — the semaphore must still cap live servers
  return Promise.all(Array.from({ length: 10 }, (_, i) => agent(`c${i}`, { label: `c${i}` })));
}
```

  Test assertions:
  - happy: scenario = 6 ok turns + turn 2 (`boom`) configured `{die: true}` twice (engine retries once ⇒ two mock turns consumed ⇒ third scenario slot for it not needed — `par[1] === null`); `par[0]`, `par[2]` carry scenario texts; `piped` = `["<s1>|10|1?...", null]` — exactly: item 20's stage-2 throw ⇒ `piped[1] === null`, item 10's chain intact; `result.n === 3` (args passthrough); journal contains `started` and `finished` for every completed call and NO `finished` for the killed worker's attempts.
  - schema: scenario turn 1 returns `finalMessage: "{\"okk\":true}"` (valid JSON, wrong shape), turn 2 returns `finalMessage: "{\"ok\":true}"`; assert the hook resolves `{ok: true}`, the journal shows one `retry` event, and the SECOND mock turn's request was `thread/resume`-based (same thread repair — assert via mock spawn/threads: the repair turn reuses the same threadId; have the mock log turn/start params per call to `turns.jsonl` and assert both turns carry the same `threadId`).
  - cap: `maxConcurrency: 2`, 10 agents, scenario 10 slow turns (`hangMs: 150`); after run, mock `peak` file ≤ 2. RED expectation: with no semaphore, peak reaches ~10.
  - **failed-status turn (the false-green case):** scenario turn `{turnStatus: "failed", finalMessage: "looks fine"}` twice → the agent call REJECTS (both attempts consumed), `parallel` absorbs it to `null`; assert the journal's `finished` record carries an error, never a result. RED expectation against the unfixed hook: resolves with "looks fine".
  - **schema exhaustion is exactly two turns:** scenario `{finalMessage: '{"okk":true}'}`, `{finalMessage: '{"okkk":true}'}`, `{finalMessage: '{"ok":true}'}` — the call REJECTS and the mock `counter` shows exactly 2 turns consumed (a third valid response must never be reachable).
  - **no stale worker pids:** after the retry case and the schema-repair case, assert `workers.json` is `[]` — every spawned pid (including first attempts and repair turns) was untracked.

- [ ] **Step 2: Run to verify it fails.** Expected: `ERR_MODULE_NOT_FOUND` naming `engine.mjs`.

- [ ] **Step 3: Implement `engine.mjs`.** Core structure (complete except where it references Task 2–4 exports):

```js
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { runAppServerTurn, runAppServerReview, parseStructuredOutput } from "../codex.mjs";
import { validateSchema } from "./validate.mjs";
import { cacheKey, appendEvent, loadJournal, acquireLease, releaseLease, repoFingerprint } from "./journal.mjs";

export class WorkflowError extends Error {
  constructor(reason, message) { super(message); this.reason = reason; }
}

class Semaphore {
  constructor(n) { this.free = n; this.queue = []; }
  async acquire() {
    if (this.free > 0) { this.free -= 1; return; }
    await new Promise((res) => this.queue.push(res));
  }
  release() {
    const next = this.queue.shift();
    if (next) next(); else this.free += 1;
  }
}

const REPAIR_PROMPT = (errors) =>
  `Your previous output failed schema validation: ${errors.join("; ")}. ` +
  `Re-emit ONLY the corrected JSON object, nothing else.`;

export async function runWorkflow(spec) {
  const t0 = Date.now();
  const runDir = spec.runDir;
  fs.mkdirSync(runDir, { recursive: true });
  const lease = acquireLease(runDir);
  if (!lease.ok) throw new WorkflowError("lease-held", `run is leased by pid ${lease.holderPid}`);
  const journalPath = path.join(runDir, "journal.jsonl");
  const workersPath = path.join(runDir, "workers.json");
  const fpPath = path.join(runDir, "fingerprint");
  const fp = repoFingerprint(spec.cwd);
  try {
    if (spec.resume) {
      const recorded = fs.existsSync(fpPath) ? fs.readFileSync(fpPath, "utf8") : null;
      if (recorded && recorded !== fp) {
        throw new WorkflowError("fingerprint-mismatch",
          `repo changed since the original run (${recorded} → ${fp}); re-run fresh instead of resuming`);
      }
    } else {
      fs.writeFileSync(fpPath, fp);
    }
    const { finished } = loadJournal(journalPath);
    const occurrences = new Map();          // base key → count issued this run
    const liveWorkers = new Set();
    const saveWorkers = () => fs.writeFileSync(workersPath, JSON.stringify([...liveWorkers]));
    const sem = new Semaphore(spec.maxConcurrency ?? 6);
    let agents = 0;
    const emit = spec.emit ?? (() => {});

    const trackSpawn = (pid) => { liveWorkers.add(pid); saveWorkers(); };
    const untrack = (pid) => { liveWorkers.delete(pid); saveWorkers(); };

    async function leafCall(kind, label, payload, exec) {
      const base = cacheKey(kind, label, payload);
      const n = occurrences.get(base) ?? 0;
      occurrences.set(base, n + 1);
      const key = `${base}#${n}`;
      if (finished.has(key)) {
        emit(`cache ${kind}:${label ?? ""}`);
        const hit = finished.get(key);
        if (hit.error) throw Object.assign(new Error(hit.error), { cached: true });
        return hit.result;
      }
      await sem.acquire();
      appendEvent(journalPath, { type: "started", key, kind, label });
      agents += 1;
      emit(`start ${kind}:${label ?? ""}`);
      const callPids = [];                       // EVERY spawn of this call (retries + repair turns)
      const onSpawn = (pid) => { callPids.push(pid); trackSpawn(pid); };
      try {
        const attempt = () => exec(onSpawn);
        let out;
        try {
          out = await attempt();
        } catch (e1) {
          if (e1?.terminal) throw e1;            // schema-repair exhaustion etc: NEVER a third attempt
          appendEvent(journalPath, { type: "retry", key, error: String(e1?.message ?? e1) });
          emit(`retry ${kind}:${label ?? ""}`);
          out = await attempt();                 // one automatic transport retry, fresh turn
        }
        appendEvent(journalPath, { type: "finished", key, result: out });
        emit(`done ${kind}:${label ?? ""}`);
        return out;
      } catch (err) {
        appendEvent(journalPath, { type: "finished", key, error: String(err?.message ?? err) });
        emit(`fail ${kind}:${label ?? ""}`);
        throw err;
      } finally {
        for (const pid of callPids) untrack(pid);  // no stale pids: cancel must never signal a reused pid
        sem.release();
      }
    }

    function assertTurnUsable(turn, what) {
      // The runtime reports unsuccessful completed turns via status with
      // error possibly null (see buildResultStatus in codex.mjs) — checking
      // .error alone false-greens failed turns. Read buildResultStatus and
      // gate on ITS success value, not on error presence.
      if (turn.error) throw new Error(turn.error.message ?? `${what} failed`);
      if (!isSuccessStatus(turn.status)) throw new Error(`${what} completed unsuccessfully (status ${JSON.stringify(turn.status)})`);
    }
    // isSuccessStatus: implement by reading buildResultStatus (codex.mjs) —
    // whatever shape it returns for a clean completed turn is the ONLY
    // success value; everything else throws.

    const hooks = {
      args: spec.args,
      log: (m) => { appendEvent(journalPath, { type: "log", message: String(m) }); emit(`log ${m}`); },

      agent: (prompt, opts = {}) =>
        leafCall("agent", opts.label, { prompt, opts: sanitize(opts) }, async (onSpawn) => {
          const overrides = [];
          const connect = { disableBroker: true, configOverrides: overrides, onSpawn };
          const turn = await runAppServerTurn(opts.cwd ?? spec.cwd, {
            prompt, model: opts.model, effort: opts.effort,
            sandbox: "read-only", persistThread: true,
            outputSchema: opts.schema ?? null, connect
          });
          assertTurnUsable(turn, "agent turn");
          if (!opts.schema) {
            if (!turn.finalMessage?.trim()) throw new Error("agent turn returned no output");
            return turn.finalMessage;
          }
          let parsed = parseStructuredOutput(turn.finalMessage);
          let errors = parsed.parseError ? [parsed.parseError] : validateSchema(parsed.parsed, opts.schema);
          if (errors.length === 0) return parsed.parsed;
          appendEvent(journalPath, { type: "retry", key: "schema-repair", label: opts.label, errors });
          const repair = await runAppServerTurn(opts.cwd ?? spec.cwd, {
            prompt: REPAIR_PROMPT(errors), resumeThreadId: turn.threadId,
            model: opts.model, effort: opts.effort, sandbox: "read-only",
            outputSchema: opts.schema, connect
          });
          assertTurnUsable(repair, "schema repair turn");
          parsed = parseStructuredOutput(repair.finalMessage);
          errors = parsed.parseError ? [parsed.parseError] : validateSchema(parsed.parsed, opts.schema);
          if (errors.length > 0) {
            throw Object.assign(
              new Error(`schema validation failed after repair: ${errors.join("; ")}`),
              { terminal: true });   // exactly two turns — the transport retry must NOT grant a third
          }
          return parsed.parsed;
        }),

      review: (opts = {}) =>
        leafCall("review", opts.label, { opts: sanitize(opts) }, async (onSpawn) => {
          const overrides = [];
          if (opts.effort) overrides.push(`model_reasoning_effort=${opts.effort}`);
          if (opts.lens) overrides.push(`developer_instructions=${opts.lens}`);
          // TARGET CONTRACT: runAppServerReview sends options.target to
          // review/start verbatim — it has no base/scope params. Task 4
          // exports resolveReviewTarget(cwd, {base, scope}) (extracted from
          // the review verb's existing resolution code, same module) and the
          // hook uses it; the mock test asserts the review/start request
          // carried the resolved target (e.g. {type:"baseBranch", branch}).
          const target = resolveReviewTarget(opts.cwd ?? spec.cwd, { base: opts.base, scope: opts.scope });
          const res = await runAppServerReview(opts.cwd ?? spec.cwd, {
            model: opts.model, target,
            connect: { disableBroker: true, configOverrides: overrides, onSpawn }
          });
          assertTurnUsable(res, "review");
          if (!res.reviewText?.trim()) throw new Error("review returned no output");
          return { reviewText: res.reviewText, threadId: res.threadId, status: res.status };
        }),

      parallel: (thunks) => Promise.all(thunks.map((t) =>
        Promise.resolve().then(t).catch(() => null))),

      pipeline: async (items, ...stages) => Promise.all(items.map(async (item, index) => {
        let acc = item;
        for (const stage of stages) {
          try { acc = await stage(acc, item, index); }
          catch { return null; }
        }
        return acc;
      })),
    };

    const mod = await import(pathToFileURL(path.resolve(spec.scriptPath)).href);
    if (typeof mod.default !== "function") {
      throw new WorkflowError("script-error", "workflow script must export a default async function");
    }
    const result = await mod.default(hooks);
    fs.writeFileSync(path.join(runDir, "result.json"), JSON.stringify(result ?? null, null, 2));
    return { result: result ?? null, agents, durationMs: Date.now() - t0 };
  } finally {
    releaseLease(runDir);
  }
}

function sanitize(opts) {
  const { schema, ...rest } = opts;   // schema objects can be large; hash their JSON separately
  return { ...rest, schemaHash: schema ? JSON.stringify(schema).length + ":" + JSON.stringify(schema).slice(0, 64) : null };
}
```

  Engine imports: `import { runAppServerTurn, runAppServerReview, parseStructuredOutput, resolveReviewTarget } from "../codex.mjs";` — `resolveReviewTarget` is the Task-4 export.

- [ ] **Step 4: Run to verify it passes.** All three fixture tests green; re-run full `run-workflow-tests.sh`.

- [ ] **Step 5: Commit.** `git commit -am "feat(codex-companion): workflow engine core — hooks, leaf semaphore, journal cache, schema repair"`

### Task 6: The `workflow` verb — CLI, job record, signals, cancel/status awareness

**Files:**
- Modify: `skills/codex-companion/runtime/scripts/codex-companion.mjs` (new `case "workflow"` in main() switch ~1031; cancel/status/result workflow-awareness)
- Modify: `skills/codex-companion/runtime/scripts/lib/state.mjs` (atomic save + lock helper)
- Test: `tests/codex-companion/test-verb-e2e.sh`

**Interfaces:**
- Consumes: Task 5 `runWorkflow`; existing `runTrackedJob` (tracked-jobs.mjs:142), `parseArgs` (args.mjs), state helpers.
- Produces: the CLI contract from the spec §1 (stdout JSON only; `[workflow]` stderr; one summary job; run dir under `$CLAUDE_PLUGIN_DATA/workflows/<run-id>/`).

- [ ] **Step 1: state.mjs hardening — atomic AND serialized for EVERY writer.** Locking only the workflow's own writes would still let the unlocked `task`/`review` paths overwrite a workflow record (lost load-mutate-write). Put both properties inside the shared mutation API so all writers get them:

  In `saveState` (state.mjs:~114), replace the direct `writeFileSync(resolveStateFile(cwd), ...)` with write-temp-then-rename:

```js
  const target = resolveStateFile(cwd);
  const tmp = `${target}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, `${JSON.stringify(nextState, null, 2)}\n`, "utf8");
  fs.renameSync(tmp, target);
```

  Wrap `updateState` itself (the single load-mutate-write choke point) in a lock:

```js
function withStateLock(cwd, fn) {
  ensureStateDir(cwd);                       // parent must exist BEFORE the lock — read the
                                             // module for the real dir-ensure helper name
  const lockDir = `${resolveStateFile(cwd)}.lock`;
  const deadline = Date.now() + 5000;
  for (;;) {
    try { fs.mkdirSync(lockDir); break; }
    catch (err) {
      if (err.code !== "EEXIST") throw err;  // ENOENT etc must propagate, never spin
      if (Date.now() > deadline) throw new Error(`state lock timeout: ${lockDir} (stale lock?)`);
      const buf = new SharedArrayBuffer(4);  // bounded sync backoff, ~15ms
      Atomics.wait(new Int32Array(buf), 0, 0, 15);
    }
  }
  try { return fn(); } finally { try { fs.rmdirSync(lockDir); } catch {} }
}

export function updateState(cwd, mutate) {
  return withStateLock(cwd, () => {
    const state = loadState(cwd);
    mutate(state);
    return saveState(cwd, state);
  });
}
```

  Every existing writer (`upsertJob`, progress updates) flows through `updateState`, so this is one change, all writers serialized, zero call-site edits. Verify no existing caller nests `updateState` inside `updateState` (grep; a nested call would deadlock — if one exists, refactor that caller to a single mutation).

- [ ] **Step 2: Write the failing e2e test** `test-verb-e2e.sh` (sources `lib-mock.sh`): scenario 3 ok turns; run
  `node "$RUNTIME" workflow --script fixtures/fx-happy-small.mjs --args '{"n":1}' --cwd "$scratch/repo" > out.json 2> err.log`
  (fx-happy-small: one agent + a two-thunk parallel). Assert with `jq`/grep:
  - `out.json` parses; `.result.n == 1`; `.runId` non-empty; `.agents == 3`; NOTHING else on stdout.
  - `err.log` contains `[workflow] start agent:` lines and no JSON.
  - run dir exists under `$CLAUDE_PLUGIN_DATA/workflows/<runId>/` with `journal.jsonl`, `result.json`.
  - `node "$RUNTIME" status` shows the job with status success (workflow job registered + finalized).
  - **Overlap case:** launch two workflows concurrently (scenario with `hangMs`), wait both; `status` lists BOTH summary records (the lock+rename kept both).
  - **Mixed-verb overlap case:** launch one slow workflow AND one plain `task` verb run concurrently (both against the mock); after both finish, `status` lists BOTH records — the legacy writer can no longer clobber the workflow record (this is the case the workflow-only lock could not fix).
  - **Result case:** after a successful run, `node "$RUNTIME" result <job-id>` prints the run's stored outcome (per-job file intact) including the runDir path; after the SIGKILL case below, `result <job-id>` reports the failure rather than a phantom running job.
  - **Cancel case:** launch one with long `hangMs`, `kill -TERM` the verb pid; assert all mock `live/*` files disappear ≤ 2s and `status` shows the job `canceled`.
  - **Liveness case:** launch one, `kill -9` it; run `status`; assert the job is finalized `failed` (lazy repair), not stuck `running`.

- [ ] **Step 3: Run to verify it fails.** Expected: `Unknown subcommand: workflow` (or the switch's default error) — record exact text.

- [ ] **Step 4: Implement the verb — via ONE workflow job-lifecycle helper.** First read `lib/tracked-jobs.mjs` and `lib/job-control.mjs` end to end and record: (a) the exact status vocabulary the read paths recognize (`completed`/`failed`/`cancelled` — note the spelling; use EXACTLY the canonical strings found, never invent `canceled` if the codebase reads `cancelled`), (b) how `result` locates per-job data (`readJobFile`/`writeJobFile` — the ledger row alone is NOT enough).

  Write a small helper (in the verb module or `lib/workflow/job.mjs`): `workflowJobLifecycle(cwd, job)` exposing `register()`, `finalize(status, payload)` — each call updates BOTH the ledger row (through the now-locked `updateState`) AND the per-job file (`writeJobFile`) with `{runId, runDir, journalPath, resultPath, logFile}` metadata, using only canonical statuses. `runTrackedJob` is NOT reused for the workflow (its lifecycle assumptions differ); the helper is the single writer.

  Then the verb: parse flags (`script` required, `args` JSON, `max-concurrency` int, `cwd`, `resume`); runId via `generateJobId("wf")`; runDir = `path.join(dataRoot, "workflows", runId)` (reuse the existing CLAUDE_PLUGIN_DATA resolution — read how `state.mjs` resolves the data root); `register()`; install `SIGTERM`/`SIGINT` handlers that read `workers.json`, `process.kill` each live pid, `finalize("cancelled", …)`, `process.exit(130)`; call `runWorkflow({scriptPath, args, cwd, maxConcurrency, runDir, resume, emit: (l) => process.stderr.write(`[workflow] ${l}\n`)})`; on success print exactly one JSON object `{runId, ...engineResult}` to stdout and `finalize("completed", …)`; on WorkflowError print the reason to stderr, `finalize("failed", …)`, exit 2.
  In the `status`/`result` read path: for workflow-class jobs still `running`, probe `process.kill(pid, 0)`; on ESRCH `finalize("failed", …)` before rendering.
  In `cancel`: after the existing group-signal attempt, if the job is a workflow job, also read its runDir `workers.json` and signal each recorded pid (ESRCH tolerated).

- [ ] **Step 5: Run to verify it passes**, plus the full runner and `scripts/lint-shell.sh`.

- [ ] **Step 6: Commit.** `git commit -am "feat(codex-companion): workflow verb — CLI contract, locked job records, signal cleanup, cancel/liveness awareness"`

### Task 7: Resume — adversarial integration tests

**Files:**
- Test: `tests/codex-companion/test-resume.sh` (+ fixture `fx-resume.mjs`)

**Interfaces:** Consumes Tasks 5–6. No production code expected; any failure here is a Task 5/6 bug fixed in place.

- [ ] **Step 1: Write the failing test.** `fx-resume.mjs`: `agent A; parallel(B slow, C fast); agent D`. Scenario: A ok, B `hangMs: 60000`, C ok, D ok.
  Sequence:
  1. Launch the verb; poll the journal until `finished` records exist for A and C while B is only `started`; `kill -9` the verb; kill surviving mock pids.
  2. Assert journal has `finished` A, `finished` C, `started`-only B (out-of-order completion persisted).
  3. Append a torn line (`echo -n '{"type":"finis' >> journal.jsonl`).
  4. Re-run with `--resume <runId>` and a fresh scenario where ALL turns are ok with distinctive texts; assert: mock consumed exactly 2 turns (B and D — A and C came from cache; count via mock `counter`), and final `result.json` composes cached A/C values with live B/D values.
  5. **Lease:** while a slow resumed run is live, a second `--resume` exits non-zero with `lease` in stderr.
  6. **Fingerprint:** `git commit --allow-empty` in the target repo, then `--resume` again → exits non-zero naming the fingerprint mismatch.

- [ ] **Step 2: Run — verify current behavior.** Expected: PASS if Tasks 5–6 are correct; any RED here names a real defect (e.g. resume re-running A means the cache key drifted). Fix in `engine.mjs`, never by weakening the test.

- [ ] **Step 3: Commit.** `git commit -am "test(codex-companion): adversarial resume — out-of-order, torn tail, lease, fingerprint"`

### Task 8: Docs + final verification

**Files:**
- Create: `skills/codex-companion/references/workflows.md`
- Modify: `skills/codex-companion/SKILL.md` (add the verb line to the verb list)

- [ ] **Step 1: Write `references/workflows.md`**: the CLI contract (env vars: CLAUDE_PLUGIN_DATA + SESSION_ID; APP_SERVER_ENDPOINT explicitly NOT consulted), the script contract with a complete minimal example, hook semantics table (including `review` `lens` ≤ 2-sentence guidance and the read-only rule), run-dir layout, resume semantics (content-keyed, lease, fingerprint refusal), and the `2>` stderr redirect note matching the house output contract. Keep the voice consistent with references/reviews.md and jobs.md.

- [ ] **Step 2: SKILL.md verb list** — one line following the existing pattern:
  `- \`workflow\` — run a JS orchestration script fanning out codex workers (agents + native reviews) as ONE process; read-only, resumable → references/workflows.md`

- [ ] **Step 3: Final verification — the spec's acceptance, verbatim mapping.** Run and record output of each:
  - Acceptance 1: `bash tests/codex-companion/run-workflow-tests.sh` (happy-path case inside test-verb-e2e.sh) → all green.
  - Acceptance 2: schema-repair case in test-engine-hooks.mjs → green.
  - Acceptance 3: `bash tests/codex-companion/test-resume.sh` → green.
  - Acceptance 4: cap case in test-engine-hooks.mjs (peak ≤ 2) → green.
  - Acceptance 5: cancel/liveness/overlap cases in test-verb-e2e.sh → green.
  - Regression: `tests/claude-code/run-skill-tests.sh` STATUS: PASSED; `scripts/lint-shell.sh` clean.
  (Acceptances 6–8 belong to Plan B.)

- [ ] **Step 4: Commit.** `git commit -am "docs(codex-companion): workflow verb reference + skill index line"`
