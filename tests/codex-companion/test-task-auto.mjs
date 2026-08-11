// The task verb's writer lane IS Codex's Auto preset: --write selects the
// workspace-write sandbox AND guardian-reviewed escalation (approvalPolicy
// "on-request", approvalsReviewer "auto_review"), while read-only tasks keep
// the headless "never" policy. The reviewer rides the THREAD params — a
// `-c approvals_reviewer=...` process override is not enough, because
// thread/resume restores the reviewer persisted at thread creation, which
// beats process-level config (observed live: a plain-created thread resumed
// into the auto lane routed its approval RPC to this client, whose
// handleServerRequest rejects all server requests). Three things must hold:
//   --write         → thread/start carries approvalPolicy "on-request",
//                     approvalsReviewer "auto_review", sandbox
//                     "workspace-write".
//   --write resume  → thread/resume carries the same three — including on a
//                     thread a read-only task created.
//   no flag         → read-only, approvalPolicy "never", no reviewer, plain
//                     ["app-server"] argv. The auto preset must not leak
//                     into the read-only lane.
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
      { finalMessage: "read-only answer" },
      { finalMessage: "write follow-up answer" },
      { finalMessage: "write fresh answer" }
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

// --- read-only task first: the thread --write must later upgrade ------------
const plainRun = run("node", [SCRIPT, "task", "--", "start a read-only thread"], { cwd: repo, env });
assert.equal(plainRun.status, 0, plainRun.stderr);

const plainStart = threadRecords().at(-1);
assert.equal(plainStart.method, "thread/start", "a read-only task starts a thread");
assert.equal(plainStart.params.sandbox, "read-only", "a task without --write stays read-only");
assert.equal(plainStart.params.approvalPolicy, "never", "…keeps the headless default policy");
assert.equal(plainStart.params.approvalsReviewer, null, "…and names no reviewer");
assert.deepEqual(spawnArgv(plainStart.pid), ["app-server"], "the task lanes spawn with an untouched argv");

// --- --write --resume-last of that read-only thread -------------------------
// The case the config-override design got wrong: the resumed thread restores
// its persisted reviewer unless the resume params override it.
const resumeRun = run("node", [SCRIPT, "task", "--write", "--resume-last", "--", "now apply the fix"], { cwd: repo, env });
assert.equal(resumeRun.status, 0, resumeRun.stderr);

const writeResume = threadRecords().at(-1);
assert.equal(writeResume.method, "thread/resume", "--resume-last resumes rather than starting fresh");
assert.equal(writeResume.params.threadId, threadIdOf(plainStart), "…the thread the read-only task created");
assert.equal(writeResume.params.approvalPolicy, "on-request", "--write asserts on-request approvals on resume");
assert.equal(writeResume.params.approvalsReviewer, "auto_review", "--write overrides the thread's persisted reviewer");
assert.equal(writeResume.params.sandbox, "workspace-write", "--write selects the workspace-write sandbox");

// --- --write --fresh --------------------------------------------------------
const writeRun = run("node", [SCRIPT, "task", "--write", "--fresh", "--", "fresh write thread"], { cwd: repo, env });
assert.equal(writeRun.status, 0, writeRun.stderr);
assert.match(writeRun.stdout, /write fresh answer/, "the write lane still returns the turn's final message");

const writeStart = threadRecords().at(-1);
assert.equal(writeStart.method, "thread/start", "--fresh forces a new thread");
assert.equal(writeStart.params.approvalPolicy, "on-request", "--write asks for on-request approvals");
assert.equal(writeStart.params.approvalsReviewer, "auto_review", "--write routes approvals to the guardian reviewer");
assert.equal(writeStart.params.sandbox, "workspace-write", "--write selects the workspace-write sandbox");

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-task-auto: ok");
