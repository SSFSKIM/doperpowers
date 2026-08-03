// SessionEnd cleanup is a ledger WRITER, so it has to go through the same lock
// every other writer takes. It used to loadState and then saveState unlocked:
// a concurrent locked upsertJob (a background task registering, a workflow
// finalizing) could be renamed straight over by the hook's stale snapshot, and
// saveState's pruning pass would then delete the newly added job's record and
// log as "dropped".
//
// A live-held lock is the deterministic stand-in for that concurrency: an
// unlocked writer walks past it, a locked one cannot.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOOK = path.join(HERE, "..", "..", "skills", "codex-companion", "runtime", "scripts", "session-lifecycle-hook.mjs");

const scratch = makeTempDir("codex-sessend-");
const dataDir = path.join(scratch, "data");
fs.mkdirSync(dataDir, { recursive: true });
process.env.CLAUDE_PLUGIN_DATA = dataDir;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const { ensureStateDir, loadState, resolveStateFile, upsertJob } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/state.mjs"
);
const { processStartTime } = await import("../../skills/codex-companion/runtime/scripts/lib/pid.mjs");

const workspace = path.join(scratch, "repo");
fs.mkdirSync(workspace, { recursive: true });

function endSession(sessionId) {
  return run(process.execPath, [HOOK, "SessionEnd"], {
    env: process.env,
    input: JSON.stringify({ hook_event_name: "SessionEnd", session_id: sessionId, cwd: workspace })
  });
}

// --- a live holder's lock is respected ---------------------------------------
upsertJob(workspace, { id: "job-mine", sessionId: "S1", status: "completed" });
upsertJob(workspace, { id: "job-theirs", sessionId: "S2", status: "completed" });

ensureStateDir(workspace);
const lockDir = `${resolveStateFile(workspace)}.lock`;
fs.mkdirSync(lockDir);
fs.writeFileSync(path.join(lockDir, "holder"), String(process.pid), "utf8");

const contended = endSession("S1");
assert.notEqual(contended.status, 0, "a hook that could not take the lock must not report success");
assert.deepEqual(
  loadState(workspace).jobs.map((job) => job.id).sort(),
  ["job-mine", "job-theirs"],
  "the ledger must be untouched while another writer holds the lock"
);

fs.rmSync(lockDir, { recursive: true, force: true });

// --- and the cleanup itself still works --------------------------------------
const released = endSession("S1");
assert.equal(released.status, 0, `the hook must succeed once the lock is free: ${released.stderr}`);
assert.deepEqual(
  loadState(workspace).jobs.map((job) => job.id),
  ["job-theirs"],
  "the ending session's jobs are dropped and everyone else's are kept"
);

// --- a foreground workflow run is actually terminated -------------------------
//
// terminateProcessTree signals a process GROUP, and a workflow run is a plain
// foreground child of whoever launched it — not a group leader. The group signal
// raises ESRCH and reports delivered:false, and the hook used to drop the ledger
// row anyway: the run kept going with nothing left addressing it, and its
// workers with it. cancel has always signalled the pid directly and swept
// workers.json after the group attempt; SessionEnd is the same teardown.
const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

function spawnVictim() {
  const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 60000)"], { stdio: "ignore" });
  const deadline = Date.now() + 5000;
  while (!processStartTime(child.pid) && Date.now() < deadline) sleep(20);
  return child;
}

const runDir = path.join(scratch, "wf-run");
fs.mkdirSync(runDir, { recursive: true });
const runProc = spawnVictim();
const worker = spawnVictim();
const unprovable = spawnVictim();
const exited = (child) => child.exitCode !== null || child.signalCode !== null;
async function waitForExit(child, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (!exited(child) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return exited(child);
}

fs.writeFileSync(
  path.join(runDir, "workers.json"),
  JSON.stringify([{ pid: worker.pid, pidStart: processStartTime(worker.pid) }])
);
upsertJob(workspace, {
  id: "wf-session",
  sessionId: "S3",
  jobClass: "workflow",
  status: "running",
  pid: runProc.pid,
  pidStart: processStartTime(runProc.pid),
  runDir
});
// No stamp: nothing here can prove this number is still the process the row
// named, so the hook must clean the record up WITHOUT signalling anyone.
upsertJob(workspace, { id: "task-unstamped", sessionId: "S3", status: "running", pid: unprovable.pid });

const ended = endSession("S3");
assert.equal(ended.status, 0, `the hook must succeed: ${ended.stderr}`);
assert.equal(await waitForExit(runProc), true, "the workflow run process was terminated");
assert.equal(await waitForExit(worker), true, "…and so were the workers it left tracked");
assert.equal(exited(unprovable), false, "an unprovable pid is never signalled");
assert.deepEqual(
  loadState(workspace).jobs.map((job) => job.id),
  ["job-theirs"],
  "the ending session's rows are still dropped"
);
unprovable.kill("SIGKILL");
await new Promise((resolve) => unprovable.on("exit", resolve));

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-session-cleanup: ok");
