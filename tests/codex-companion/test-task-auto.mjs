// The task verb's --auto lane: Codex's Auto preset (workspace-write sandbox +
// on-request approvals reviewed by the built-in auto_review guardian) instead
// of the headless default (approvalPolicy "never"). Three things must hold:
//   --auto          → thread/start carries approvalPolicy "on-request" AND
//                     sandbox "workspace-write" (auto implies write), and the
//                     task spawns its own app-server whose argv carries
//                     `-c approvals_reviewer=auto_review` — the reviewer is a
//                     config-level setting, not a thread param.
//   --auto resume   → thread/resume re-asserts the same policy on the thread
//                     it picks up.
//   --write alone   → byte-identical to today: approvalPolicy "never", plain
//                     ["app-server"] argv. --auto must not leak into the
//                     default lane.
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
      { finalMessage: "auto answer" },
      { finalMessage: "auto follow-up answer" },
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
// no-broker endpoint, so the non-connect lane exercises the documented direct
// fallback rather than starting a real broker.
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

// --- --auto: fresh thread -------------------------------------------------
const autoRun = run("node", [SCRIPT, "task", "--auto", "--", "try the auto lane"], { cwd: repo, env });
assert.equal(autoRun.status, 0, autoRun.stderr);
assert.match(autoRun.stdout, /auto answer/, "the auto lane still returns the turn's final message");

const autoStart = threadRecords().at(-1);
assert.equal(autoStart.method, "thread/start", "a fresh --auto task starts a thread");
assert.equal(autoStart.params.approvalPolicy, "on-request", "--auto asks for on-request approvals");
assert.equal(autoStart.params.sandbox, "workspace-write", "--auto implies the workspace-write sandbox");
assert.deepEqual(
  spawnArgv(autoStart.pid),
  ["-c", "approvals_reviewer=auto_review", "app-server"],
  "the auto task's own app-server carries the guardian reviewer override"
);

// --- --auto --resume-last: the resumed thread keeps the policy ------------
const resumeRun = run("node", [SCRIPT, "task", "--auto", "--resume-last", "--", "keep going"], { cwd: repo, env });
assert.equal(resumeRun.status, 0, resumeRun.stderr);

const autoResume = threadRecords().at(-1);
assert.equal(autoResume.method, "thread/resume", "--resume-last resumes rather than starting fresh");
assert.equal(autoResume.params.threadId, threadIdOf(autoStart), "…the thread the first auto task created");
assert.equal(autoResume.params.approvalPolicy, "on-request", "the resumed turn re-asserts on-request approvals");
assert.equal(autoResume.params.sandbox, "workspace-write", "…and the workspace-write sandbox");
assert.deepEqual(
  spawnArgv(autoResume.pid),
  ["-c", "approvals_reviewer=auto_review", "app-server"],
  "the resumed auto task also owns a reviewer-configured app-server"
);

// The mock mints thread ids as t-<pid>-<seq>; recover the id the first run's
// start actually produced from the resume request having targeted it.
function threadIdOf(startRecord) {
  return `t-${startRecord.pid}-1`;
}

// --- --write alone: unchanged --------------------------------------------
const writeRun = run("node", [SCRIPT, "task", "--write", "--fresh", "--", "plain write lane"], { cwd: repo, env });
assert.equal(writeRun.status, 0, writeRun.stderr);

const plainStart = threadRecords().at(-1);
assert.equal(plainStart.method, "thread/start", "--fresh forces a new thread");
assert.equal(plainStart.params.approvalPolicy, "never", "without --auto the headless default policy is untouched");
assert.equal(plainStart.params.sandbox, "workspace-write", "--write still selects the workspace-write sandbox");
assert.deepEqual(spawnArgv(plainStart.pid), ["app-server"], "without --auto, argv carries no overrides");

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-task-auto: ok");
