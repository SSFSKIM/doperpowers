// A bare pid is not an identity.
//
// Pids are reused — after a reboot, and after wraparound on a long-lived box —
// so "pid 4711 answers signal 0" is not "the process I recorded is still alive".
// Every persisted pid in this runtime carries that assumption: the run lease,
// the state lock's holder stamp, workers.json, and the job row a resume and a
// cancel both act on. Reuse makes a stale lease and a stale lock read as live
// (nothing can be broken, every later writer times out) and makes cancel SIGTERM
// whatever now owns the number.
//
// A recorded process start time next to the pid settles it. Reuse is simulated
// here by stamping a LIVE pid with a start time that is not its own — which is
// precisely what a reused pid looks like from a record's point of view.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const scratch = makeTempDir("codex-pid-");
process.env.CLAUDE_PLUGIN_DATA = path.join(scratch, "data");
fs.mkdirSync(process.env.CLAUDE_PLUGIN_DATA, { recursive: true });

const { currentPidStamp, pidInstanceAlive, processStartTime } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/pid.mjs"
);
const { acquireLease, releaseLease } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs"
);
const { ensureStateDir, loadState, resolveStateFile, upsertJob, writeJobFile } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/state.mjs"
);
const { isWorkflowRunActive, killWorkflowWorkers, repairDeadWorkflowJobs, WORKFLOW_JOB_CLASS } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/workflow/job.mjs"
);

const STALE = "Thu Jan  1 00:00:00 2000";
const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

// --- the primitive ------------------------------------------------------------
const self = currentPidStamp();
assert.equal(self.pid, process.pid);
assert.ok(self.pidStart, "this platform must yield a start time for a live pid");
assert.equal(pidInstanceAlive(process.pid, self.pidStart), true, "our own instance is alive");
assert.equal(pidInstanceAlive(process.pid, STALE), false, "a reused pid is NOT the recorded process");
assert.equal(pidInstanceAlive(process.pid, null), true, "an unstamped record falls back to pid-only liveness");
const finished = run(process.execPath, ["-e", "process.exit(0)"]);
assert.equal(pidInstanceAlive(finished.pid, null), false, "a dead pid is dead with or without a stamp");

// --- the run lease -------------------------------------------------------------
{
  const runDir = path.join(scratch, "lease-run");
  fs.mkdirSync(runDir, { recursive: true });
  fs.writeFileSync(
    path.join(runDir, "lease.json"),
    JSON.stringify({ pid: process.pid, pidStart: STALE, at: Date.now() })
  );
  assert.equal(acquireLease(runDir).ok, true, "a lease stamped to a different instance must be breakable");
  const holder = JSON.parse(fs.readFileSync(path.join(runDir, "lease.json"), "utf8"));
  assert.equal(holder.pid, process.pid);
  assert.equal(holder.pidStart, self.pidStart, "the lease we take records OUR instance");
  releaseLease(runDir);
}

// --- the state lock ------------------------------------------------------------
{
  const workspace = path.join(scratch, "lock-ws");
  fs.mkdirSync(workspace, { recursive: true });
  ensureStateDir(workspace);
  const lockDir = `${resolveStateFile(workspace)}.lock`;
  fs.mkdirSync(lockDir);
  fs.writeFileSync(
    path.join(lockDir, "holder"),
    JSON.stringify({ pid: process.pid, pidStart: STALE }),
    "utf8"
  );

  upsertJob(workspace, { id: "job-after-reuse", status: "completed" });
  assert.deepEqual(
    loadState(workspace).jobs.map((job) => job.id),
    ["job-after-reuse"],
    "a lock held by a reused pid must be broken, not waited out forever"
  );
  assert.equal(fs.existsSync(lockDir), false);
}

// --- the job row a resume and a cancel act on -----------------------------------
{
  const workspace = path.join(scratch, "job-ws");
  fs.mkdirSync(workspace, { recursive: true });
  const record = {
    id: "wf-reused",
    runId: "wf-reused",
    jobClass: WORKFLOW_JOB_CLASS,
    kind: "workflow",
    title: "Codex Workflow",
    status: "running",
    phase: "running",
    pid: process.pid,
    pidStart: STALE
  };
  writeJobFile(workspace, record.id, record);
  upsertJob(workspace, record);

  assert.equal(
    isWorkflowRunActive(workspace, "wf-reused"),
    false,
    "a run whose pid was reused is not active — a resume must not be refused by it"
  );
  repairDeadWorkflowJobs(workspace);
  assert.equal(
    loadState(workspace).jobs.find((job) => job.id === "wf-reused").status,
    "failed",
    "…and the phantom row is repaired"
  );

  // The live run it would be confused with: same pid, its OWN stamp.
  const liveRecord = { ...record, id: "wf-live", runId: "wf-live", status: "running", pidStart: self.pidStart };
  writeJobFile(workspace, liveRecord.id, liveRecord);
  upsertJob(workspace, liveRecord);
  assert.equal(isWorkflowRunActive(workspace, "wf-live"), true, "a genuinely live run is still live");
  repairDeadWorkflowJobs(workspace);
  assert.equal(
    loadState(workspace).jobs.find((job) => job.id === "wf-live").status,
    "running",
    "…and is never repaired out from under itself"
  );
}

// --- workers.json: cancel must not signal a reused pid ---------------------------
function spawnVictim() {
  const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 60000)"], { stdio: "ignore" });
  const deadline = Date.now() + 5000;
  while (!processStartTime(child.pid) && Date.now() < deadline) sleep(20);
  return child;
}

{
  const runDir = path.join(scratch, "workers-run");
  fs.mkdirSync(runDir, { recursive: true });
  const victim = spawnVictim();
  const exited = new Promise((resolve) => victim.on("exit", resolve));

  fs.writeFileSync(
    path.join(runDir, "workers.json"),
    JSON.stringify([{ pid: victim.pid, pidStart: STALE }])
  );
  assert.deepEqual(killWorkflowWorkers(runDir), [], "a worker pid that was reused must not be signalled");
  sleep(300);
  assert.equal(victim.exitCode, null, "…and the innocent process is still running");

  fs.writeFileSync(
    path.join(runDir, "workers.json"),
    JSON.stringify([{ pid: victim.pid, pidStart: processStartTime(victim.pid) }])
  );
  assert.deepEqual(killWorkflowWorkers(runDir), [victim.pid], "the real worker is still signalled");
  await exited;
}

{
  // An UNSTAMPED entry proves nothing. A bare number is the pre-stamp format,
  // and on Windows no start time is readable at all, so every entry looks like
  // this — but the same run directory outlives a reboot, and the number in it
  // may now be a stranger's. Every kill path in this runtime (cancel, the worker
  // sweep, the SessionEnd teardown, the broker teardown) refuses what it cannot
  // prove: the cost is a leaked worker that was already unreachable.
  const runDir = path.join(scratch, "workers-legacy");
  fs.mkdirSync(runDir, { recursive: true });
  const victim = spawnVictim();
  fs.writeFileSync(path.join(runDir, "workers.json"), JSON.stringify([victim.pid]));
  assert.deepEqual(killWorkflowWorkers(runDir), [], "an unstamped worker entry is never signalled");
  sleep(300);
  assert.equal(victim.exitCode, null, "…and the process it names keeps running");
  victim.kill("SIGKILL");
  await new Promise((resolve) => victim.on("exit", resolve));
}

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-pid-identity: ok");
