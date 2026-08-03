// An app-server that dies AFTER answering turn/start.
//
// By then there is no outstanding RPC left for the client's exit handler to
// reject, and the turn capture is waiting on a completion that only a turn
// notification can settle — one that will never arrive. The leaf, the semaphore
// slot it holds and the whole workflow wait forever.
//
// The watchdog below is the assertion for that: this test HANGS against the old
// behavior, so it fails on the clock rather than on a value.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { initGitRepo, makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCK_BIN_DIR = path.join(HERE, "mock");
const FIXTURES = path.join(HERE, "fixtures");

const watchdog = setTimeout(() => {
  console.error("test-exit-midturn: TIMED OUT — a leaf never learned its app-server was gone");
  process.exit(1);
}, 30_000);

const scratch = makeTempDir("codex-midturn-");
const mockDir = path.join(scratch, "mockstate");
const repo = path.join(scratch, "repo");
const runDir = path.join(scratch, "run");
fs.mkdirSync(mockDir, { recursive: true });
fs.mkdirSync(repo, { recursive: true });
fs.writeFileSync(
  path.join(mockDir, "scenario.json"),
  JSON.stringify({
    turns: [
      { dieMidTurn: true },              // 1  A, first attempt
      { dieMidTurn: true },              // 2  A, transport retry
      { finalMessage: "B-live" }         // 3  B — only reachable if A's slot came back
    ]
  })
);
initGitRepo(repo);
fs.writeFileSync(path.join(repo, "tracked.txt"), "base\n");
run("git", ["add", "."], { cwd: repo });
run("git", ["commit", "-m", "base"], { cwd: repo });

process.env.CODEX_MOCK_DIR = mockDir;
process.env.PATH = `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const { runWorkflow } = await import("../../skills/codex-companion/runtime/scripts/lib/workflow/engine.mjs");

const startedAt = Date.now();
const outcome = await runWorkflow({
  cwd: repo,
  runDir,
  scriptPath: path.join(FIXTURES, "fx-die-midturn.mjs"),
  maxConcurrency: 1,
  args: null
});
const elapsed = Date.now() - startedAt;

assert.match(String(outcome.result.a), /^A-failed: /, "the leaf must fail, not hang");
assert.equal(outcome.result.b, "B-live", "the next leaf still runs — the semaphore slot came back");
assert.ok(elapsed < 25_000, `the failure must be prompt (took ${elapsed}ms)`);

const journal = fs
  .readFileSync(path.join(runDir, "journal.jsonl"), "utf8")
  .trim()
  .split("\n")
  .filter(Boolean)
  .map((line) => JSON.parse(line));
const aRetries = journal.filter((event) => event.type === "retry" && event.key.startsWith("agent|A|"));
assert.equal(aRetries.length, 1, "the transport retry gets its ONE attempt, no more");
const aFinished = journal.filter((event) => event.type === "finished" && event.key.startsWith("agent|A|"));
assert.equal(aFinished.length, 1, "A finishes once, as a failure");
assert.ok(aFinished[0].error, "…and the journal records the error, not a result");

const counter = Number(fs.readFileSync(path.join(mockDir, "counter"), "utf8"));
assert.equal(counter, 3, "exactly three turns were paid for: A, A's retry, B");
assert.deepEqual(JSON.parse(fs.readFileSync(path.join(runDir, "workers.json"), "utf8")), [],
  "no worker pids left tracked after a mid-turn death");

clearTimeout(watchdog);
fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-exit-midturn: ok");
