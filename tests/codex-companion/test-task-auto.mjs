// The task verb's --auto lane: Codex's Auto preset (workspace-write sandbox +
// on-request approvals reviewed by the built-in auto_review guardian) instead
// of the headless default (approvalPolicy "never"). The reviewer rides the
// THREAD params — a `-c approvals_reviewer=...` process override is not
// enough, because thread/resume restores the reviewer persisted at thread
// creation, which beats process-level config (observed live: a plain-created
// thread resumed with --auto routed its approval RPC to this client, whose
// handleServerRequest rejects all server requests). Three things must hold:
//   --auto          → thread/start carries approvalPolicy "on-request",
//                     approvalsReviewer "auto_review", AND sandbox
//                     "workspace-write" (auto implies write).
//   --auto resume   → thread/resume carries the same three — including on a
//                     thread a plain task created.
//   --write alone   → byte-identical to today: approvalPolicy "never", no
//                     reviewer, plain ["app-server"] argv. --auto must not
//                     leak into the default lane.
// Everything is asserted against the mock app-server's own records
// (threads.jsonl params, spawn-<pid>.json argv), not the CLI's rendering.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { initGitRepo, makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCK_BIN_DIR = path.join(HERE, "mock");
const SCRIPT = path.join(HERE, "..", "..", "skills", "codex-companion", "runtime", "scripts", "codex-companion.mjs");

const scratch = makeTempDir("codex-task-auto-");
const mockDir = path.join(scratch, "mockstate");
fs.mkdirSync(mockDir, { recursive: true });
fs.writeFileSync(
  path.join(mockDir, "scenario.json"),
  JSON.stringify({
    turns: [
      { finalMessage: "plain answer" },
      { finalMessage: "auto follow-up answer" },
      { finalMessage: "auto fresh answer" },
      { finalMessage: "plain write answer" }
    ]
  })
);

const repo = path.join(scratch, "repo");
fs.mkdirSync(repo, { recursive: true });
initGitRepo(repo);
fs.writeFileSync(path.join(repo, "tracked.txt"), "base\n");
run("git", ["add", "."], { cwd: repo });
run("git", ["commit", "-m", "base"], { cwd: repo });

// The amigo call-site's environment: a session id scoping the job ledger and a
// no-broker endpoint, so every lane exercises the documented direct fallback
// rather than starting a real broker.
const env = {
  ...process.env,
  PATH: `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`,
  CODEX_MOCK_DIR: mockDir,
  CLAUDE_PLUGIN_DATA: path.join(scratch, "data"),
  CODEX_COMPANION_SESSION_ID: "task-auto-test",
  CODEX_COMPANION_APP_SERVER_ENDPOINT: `unix:${path.join(scratch, "no-broker.sock")}`
};

const threadRecords = () =>
  fs
    .readFileSync(path.join(mockDir, "threads.jsonl"), "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
const spawnArgv = (pid) => JSON.parse(fs.readFileSync(path.join(mockDir, `spawn-${pid}.json`), "utf8")).argv;

// The mock mints thread ids as t-<pid>-<seq>.
const threadIdOf = (startRecord) => `t-${startRecord.pid}-1`;

// --- plain task first: the thread --auto must later upgrade -----------------
const plainRun = run("node", [SCRIPT, "task", "--", "start a plain thread"], { cwd: repo, env });
assert.equal(plainRun.status, 0, plainRun.stderr);

const plainStart = threadRecords().at(-1);
assert.equal(plainStart.method, "thread/start", "a plain task starts a thread");
assert.equal(plainStart.params.approvalPolicy, "never", "a plain task keeps the headless default policy");
assert.equal(plainStart.params.approvalsReviewer, null, "…and names no reviewer");

// --- --auto --resume-last of that PLAIN thread ------------------------------
// The case the config-override design got wrong: the resumed thread restores
// its persisted reviewer unless the resume params override it.
const resumeRun = run("node", [SCRIPT, "task", "--auto", "--resume-last", "--", "upgrade to auto"], { cwd: repo, env });
assert.equal(resumeRun.status, 0, resumeRun.stderr);

const autoResume = threadRecords().at(-1);
assert.equal(autoResume.method, "thread/resume", "--resume-last resumes rather than starting fresh");
assert.equal(autoResume.params.threadId, threadIdOf(plainStart), "…the thread the plain task created");
assert.equal(autoResume.params.approvalPolicy, "on-request", "--auto re-asserts on-request approvals on resume");
assert.equal(autoResume.params.approvalsReviewer, "auto_review", "--auto overrides the thread's persisted reviewer");
assert.equal(autoResume.params.sandbox, "workspace-write", "--auto implies the workspace-write sandbox");

// --- --auto --fresh --------------------------------------------------------
const autoRun = run("node", [SCRIPT, "task", "--auto", "--fresh", "--", "fresh auto thread"], { cwd: repo, env });
assert.equal(autoRun.status, 0, autoRun.stderr);
assert.match(autoRun.stdout, /auto fresh answer/, "the auto lane still returns the turn's final message");

const autoStart = threadRecords().at(-1);
assert.equal(autoStart.method, "thread/start", "--fresh forces a new thread");
assert.equal(autoStart.params.approvalPolicy, "on-request", "--auto asks for on-request approvals");
assert.equal(autoStart.params.approvalsReviewer, "auto_review", "--auto routes approvals to the guardian reviewer");
assert.equal(autoStart.params.sandbox, "workspace-write", "--auto implies the workspace-write sandbox");

// --- --write alone: unchanged ----------------------------------------------
const writeRun = run("node", [SCRIPT, "task", "--write", "--fresh", "--", "plain write lane"], { cwd: repo, env });
assert.equal(writeRun.status, 0, writeRun.stderr);

const writeStart = threadRecords().at(-1);
assert.equal(writeStart.method, "thread/start", "--fresh forces a new thread");
assert.equal(writeStart.params.approvalPolicy, "never", "without --auto the headless default policy is untouched");
assert.equal(writeStart.params.approvalsReviewer, null, "without --auto no reviewer is named");
assert.equal(writeStart.params.sandbox, "workspace-write", "--write still selects the workspace-write sandbox");
assert.deepEqual(spawnArgv(writeStart.pid), ["app-server"], "the task lanes spawn with an untouched argv");

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-task-auto: ok");
