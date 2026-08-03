// repairDeadWorkflowJobs is what turns a phantom `running` row (SIGKILL, reboot,
// crashed harness) into a reported failure. It runs from every read path —
// status, result, cancel — so it races the one thing that legitimately revives a
// run: a `--resume`, which registers a NEW live pid for the same id.
//
// Reading the ledger outside the lock and then finalizing unconditionally loses
// that race: the read says dead, the resume registers, and the repair overwrites
// a LIVE run's record and ledger row as failed.
//
// The race is made deterministic with a helper process that holds the state lock
// while the repair is waiting for it, and registers the new pid inside that
// window — exactly the interleaving above, without depending on scheduling luck.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const scratch = makeTempDir("codex-repair-");
process.env.CLAUDE_PLUGIN_DATA = path.join(scratch, "data");
fs.mkdirSync(process.env.CLAUDE_PLUGIN_DATA, { recursive: true });

const { loadState, readJobFile, resolveJobFile, resolveStateFile, upsertJob, writeJobFile } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/state.mjs"
);
const { repairDeadWorkflowJobs, WORKFLOW_JOB_CLASS } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/workflow/job.mjs"
);

function deadPid() {
  const finished = run(process.execPath, ["-e", "process.exit(0)"]);
  assert.equal(finished.status, 0);
  return finished.pid;
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function plantRunningRun(workspace, id, pid) {
  const record = {
    id,
    runId: id,
    jobClass: WORKFLOW_JOB_CLASS,
    kind: "workflow",
    title: "Codex Workflow",
    status: "running",
    phase: "running",
    pid
  };
  writeJobFile(workspace, id, record);
  upsertJob(workspace, record);
  return record;
}

// --- an actually dead run is still repaired ---------------------------------
{
  const workspace = path.join(scratch, "plain");
  fs.mkdirSync(workspace, { recursive: true });
  plantRunningRun(workspace, "wf-dead", deadPid());

  repairDeadWorkflowJobs(workspace);

  const row = loadState(workspace).jobs.find((job) => job.id === "wf-dead");
  assert.equal(row.status, "failed", "a dead run's ledger row is finalized");
  assert.equal(readJobFile(resolveJobFile(workspace, "wf-dead")).status, "failed", "…and so is its record");
}

// --- a run that came back to life inside the lock window is left alone -------
{
  const workspace = path.join(scratch, "raced");
  fs.mkdirSync(workspace, { recursive: true });
  plantRunningRun(workspace, "wf-raced", deadPid());

  const stateFile = resolveStateFile(workspace);
  const readyFile = path.join(scratch, "lock-held");
  const helperSource = `
    import fs from "node:fs";
    import path from "node:path";
    const [stateFile, readyFile, livePid] = process.argv.slice(2);
    const lockDir = stateFile + ".lock";
    fs.mkdirSync(lockDir);
    fs.writeFileSync(path.join(lockDir, "holder"), String(process.pid), "utf8");
    fs.writeFileSync(readyFile, "1", "utf8");
    // The repair is now blocked on this lock. A resume lands inside the window:
    // the ledger row gets the resuming process's live pid.
    setTimeout(() => {
      const state = JSON.parse(fs.readFileSync(stateFile, "utf8"));
      for (const job of state.jobs) if (job.id === "wf-raced") job.pid = Number(livePid);
      fs.writeFileSync(stateFile, JSON.stringify(state, null, 2) + "\\n", "utf8");
      setTimeout(() => fs.rmSync(lockDir, { recursive: true, force: true }), 400);
    }, 300);
  `;
  const helperPath = path.join(scratch, "hold-lock.mjs");
  fs.writeFileSync(helperPath, helperSource, "utf8");
  const helper = spawn(process.execPath, [helperPath, stateFile, readyFile, String(process.pid)], {
    stdio: "inherit"
  });

  const deadline = Date.now() + 10_000;
  while (!fs.existsSync(readyFile) && Date.now() < deadline) sleep(20);
  assert.ok(fs.existsSync(readyFile), "the helper never took the lock");

  repairDeadWorkflowJobs(workspace);
  await new Promise((resolve) => helper.on("exit", resolve));

  const row = loadState(workspace).jobs.find((job) => job.id === "wf-raced");
  assert.equal(row.status, "running", "a run whose pid is live again must not be finalized as failed");
  assert.equal(row.pid, process.pid, "…and the resumer's pid must survive the repair pass");
  assert.equal(
    readJobFile(resolveJobFile(workspace, "wf-raced")).status,
    "running",
    "the live run's own record must not be overwritten either"
  );
}

// --- a poisoned row does not take the repair pass down with it ---------------
//
// A ledger written before run ids were validated can hold one that is not a path
// segment. Turning it into a per-job file path throws, and this pass runs from
// every status, result and cancel — so one such row would make the whole runtime
// unusable, including for the healthy runs beside it.
{
  const workspace = path.join(scratch, "poisoned");
  fs.mkdirSync(workspace, { recursive: true });
  plantRunningRun(workspace, "wf-healthy-dead", deadPid());

  const stateFile = resolveStateFile(workspace);
  const state = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  state.jobs.unshift({
    id: "../state",
    runId: "../state",
    jobClass: WORKFLOW_JOB_CLASS,
    status: "running",
    phase: "running",
    pid: deadPid(),
    updatedAt: "2026-01-01T00:00:00.000Z"
  });
  fs.writeFileSync(stateFile, `${JSON.stringify(state, null, 2)}\n`, "utf8");

  repairDeadWorkflowJobs(workspace);

  const jobs = loadState(workspace).jobs;
  assert.equal(
    jobs.find((job) => job.id === "wf-healthy-dead").status,
    "failed",
    "the repairable run beside the poisoned row is still repaired"
  );
  assert.equal(jobs.some((job) => job.id === "../state"), false, "and the row nothing can address is gone");
}

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-repair-race: ok");
