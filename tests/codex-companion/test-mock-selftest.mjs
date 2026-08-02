// Self-test for the mock codex app-server (tests/codex-companion/mock/codex).
// Speaks raw JSON-RPC at the mock the way lib/app-server.mjs does, and asserts the
// exact field paths lib/codex.mjs reads. Every later workflow test trusts this mock,
// so a drifted field name has to fail HERE, by name.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCK_BIN = path.join(HERE, "mock", "codex");
const CONFIG_PAIR = ["-c", "model_reasoning_effort=low"];

const mockDir = fs.mkdtempSync(path.join(os.tmpdir(), "codex-wf-mock-"));
fs.writeFileSync(
  path.join(mockDir, "scenario.json"),
  JSON.stringify({ turns: [{ finalMessage: "hello" }] })
);

const child = spawn(MOCK_BIN, [...CONFIG_PAIR, "app-server"], {
  env: { ...process.env, CODEX_MOCK_DIR: mockDir },
  stdio: ["pipe", "pipe", "pipe"]
});
let stderr = "";
child.stderr.setEncoding("utf8");
child.stderr.on("data", (chunk) => { stderr += chunk; });

const pending = new Map();
const notifications = [];
const waiters = [];
let nextId = 1;

readline.createInterface({ input: child.stdout }).on("line", (line) => {
  if (!line.trim()) return;
  const message = JSON.parse(line);
  if (message.id !== undefined) {
    pending.get(message.id)?.(message);
    pending.delete(message.id);
    return;
  }
  notifications.push(message);
  for (const waiter of [...waiters]) {
    if (waiter.match(message)) {
      waiters.splice(waiters.indexOf(waiter), 1);
      waiter.resolve(message);
    }
  }
});

function request(method, params) {
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    child.stdin.write(`${JSON.stringify({ id, method, params })}\n`);
  });
}

function notify(method, params = {}) {
  child.stdin.write(`${JSON.stringify({ method, params })}\n`);
}

function waitFor(what, match, timeoutMs = 5000) {
  const seen = notifications.find(match);
  if (seen) return Promise.resolve(seen);
  return new Promise((resolve, reject) => {
    const waiter = { match, resolve };
    waiters.push(waiter);
    setTimeout(() => {
      const at = waiters.indexOf(waiter);
      if (at === -1) return;
      waiters.splice(at, 1);
      reject(new Error(
        `timed out waiting for ${what}; notifications seen: ${notifications.map((m) => m.method).join(", ") || "(none)"}`
      ));
    }, timeoutMs).unref();
  });
}

async function main() {
  const initialize = await request("initialize", { clientInfo: { name: "selftest" }, capabilities: {} });
  assert.ok(initialize.result, "initialize must answer with a result, not an error");
  notify("initialized", {});

  const started = await request("thread/start", {
    cwd: process.cwd(),
    model: null,
    approvalPolicy: "never",
    sandbox: "read-only",
    serviceName: "claude_code_codex_plugin",
    ephemeral: true
  });
  const threadId = started.result.thread.id;
  assert.ok(threadId, "thread/start must answer result.thread.id");

  const turnStart = await request("turn/start", {
    threadId,
    input: [{ type: "text", text: "hi", text_elements: [] }],
    model: null,
    effort: null,
    outputSchema: null
  });
  const turnId = turnStart.result.turn.id;
  assert.ok(turnId, "turn/start must answer result.turn.id");
  assert.equal(turnStart.result.turn.status, "inProgress", "turn/start answers an in-progress turn");

  // (a) the final agent message text
  const item = await waitFor(
    "item/completed with an agentMessage item",
    (m) => m.method === "item/completed" && m.params.item.type === "agentMessage"
  );
  assert.equal(item.params.threadId, threadId);
  assert.equal(item.params.turnId, turnId, "item notifications carry the turn id belongsToTurn() matches on");
  assert.equal(item.params.item.text, "hello", "scenario finalMessage lands at params.item.text");
  assert.equal(item.params.item.phase, "final_answer", "the final message carries phase final_answer");

  const completed = await waitFor("turn/completed", (m) => m.method === "turn/completed");
  assert.equal(completed.params.threadId, threadId);
  assert.equal(completed.params.turn.id, turnId);
  assert.equal(completed.params.turn.status, "completed", "a clean scenario turn completes");
  assert.equal(completed.params.turn.error, null);

  // (b) spawn-<pid>.json records argv (config overrides included) and cwd
  const spawnRecord = JSON.parse(fs.readFileSync(path.join(mockDir, `spawn-${child.pid}.json`), "utf8"));
  assert.deepEqual(spawnRecord.argv, [...CONFIG_PAIR, "app-server"], "spawn record keeps the -c pair in order");
  assert.equal(spawnRecord.cwd, process.cwd());

  const turns = fs.readFileSync(path.join(mockDir, "turns.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(turns.length, 1);
  assert.equal(turns[0].method, "turn/start");
  assert.equal(turns[0].pid, child.pid);
  assert.equal(turns[0].params.threadId, threadId);

  assert.equal(fs.readFileSync(path.join(mockDir, "peak"), "utf8"), "1");

  // (c) live/ empties once the server is gone
  assert.deepEqual(fs.readdirSync(path.join(mockDir, "live")), [String(child.pid)]);
  child.kill("SIGTERM");
  await once(child, "exit");
  assert.deepEqual(fs.readdirSync(path.join(mockDir, "live")), [], "live/ is empty after the server exits");
}

try {
  await main();
  console.log("test-mock-selftest: ok");
} catch (error) {
  console.error(error);
  if (stderr.trim()) console.error(`mock stderr:\n${stderr.trim()}`);
  process.exitCode = 1;
} finally {
  if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
  fs.rmSync(mockDir, { recursive: true, force: true });
}
