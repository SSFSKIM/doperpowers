// The workflow run's job record. `runTrackedJob` is deliberately not reused:
// its lifecycle assumes a codex turn (threadId/turnId, exitStatus, a rendered
// final message), and a workflow run has none of those. This module is the
// SINGLE writer of a workflow record — every transition updates BOTH the shared
// ledger row (through the locked updateState in state.mjs) and the per-job file
// that `result` reads; a ledger row alone would make `result` render nothing.
//
// Statuses are exactly the ones the read paths in job-control.mjs recognize:
// running / completed / failed / cancelled. Note the spelling — `cancelled`
// with two Ls is what enrichJob, resolveResultJob and inferLegacyJobPhase
// match on; `canceled` would silently read as an unknown, never-finished job.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import { listJobs, readJobFile, resolveJobFile, upsertJob, writeJobFile } from "../state.mjs";

export const WORKFLOW_JOB_CLASS = "workflow";

const PHASE_BY_STATUS = {
  running: "running",
  completed: "done",
  failed: "failed",
  cancelled: "cancelled"
};

// The bulky payloads stay in the per-job file: the ledger is re-read and
// re-written by every verb invocation and capped at MAX_JOBS records.
const LEDGER_OMITTED_FIELDS = new Set(["result", "rendered"]);

function nowIso() {
  return new Date().toISOString();
}

export function renderWorkflowJobResult(record) {
  const lines = [
    `# ${record.title ?? "Codex Workflow"}`,
    "",
    `Run: ${record.runId ?? record.id}`,
    `Status: ${record.status}`
  ];
  if (record.runDir) {
    lines.push(`Run directory: ${record.runDir}`);
  }
  if (record.journalPath) {
    lines.push(`Journal: ${record.journalPath}`);
  }
  if (record.agents != null) {
    lines.push(`Agents: ${record.agents}`);
  }
  if (record.durationMs != null) {
    lines.push(`Duration: ${Math.round(record.durationMs / 1000)}s`);
  }
  if (record.errorMessage) {
    lines.push("", record.errorMessage);
  }
  return `${lines.join("\n")}\n`;
}

function ledgerRow(record) {
  return Object.fromEntries(Object.entries(record).filter(([key]) => !LEDGER_OMITTED_FIELDS.has(key)));
}

export function workflowJobLifecycle(workspaceRoot, job) {
  let record = { ...job, jobClass: WORKFLOW_JOB_CLASS, kindLabel: "workflow" };

  function persist(patch) {
    record = { ...record, ...patch };
    writeJobFile(workspaceRoot, record.id, record);
    upsertJob(workspaceRoot, ledgerRow(record));
    return record;
  }

  return {
    get record() {
      return record;
    },
    register() {
      return persist({
        status: "running",
        phase: "running",
        pid: process.pid,
        startedAt: record.startedAt ?? nowIso()
      });
    },
    finalize(status, patch = {}) {
      const next = {
        ...patch,
        status,
        phase: PHASE_BY_STATUS[status] ?? status,
        pid: null,
        completedAt: nowIso()
      };
      // Rendered eagerly so `result` shows the run directory on every terminal
      // path, including the lazily repaired one below where nothing else ran.
      next.rendered = renderWorkflowJobResult({ ...record, ...next });
      return persist(next);
    }
  };
}

function pidAlive(pid) {
  if (typeof pid !== "number" || !Number.isInteger(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === "EPERM"; // exists, owned by another user
  }
}

// `--resume <run-id>` reuses the run's job id, so a resume of a run that is
// still going would overwrite that run's own record before the engine's lease
// check ever fires. The lease is the race-free guard; this is what keeps the
// ledger honest in the ordinary case.
export function isWorkflowRunActive(workspaceRoot, runId) {
  const jobFile = resolveJobFile(workspaceRoot, runId);
  if (!fs.existsSync(jobFile)) {
    return false;
  }
  const stored = readJobFile(jobFile);
  return stored.status === "running" && pidAlive(stored.pid);
}

// A workflow run is one process, so nothing else will ever finalize its record:
// SIGKILL, a reboot or a crashed harness leaves it `running` forever. The read
// paths repair it lazily rather than reporting a phantom run.
export function repairDeadWorkflowJobs(workspaceRoot) {
  for (const job of listJobs(workspaceRoot)) {
    if (job.jobClass !== WORKFLOW_JOB_CLASS) {
      continue;
    }
    if (job.status !== "running" && job.status !== "queued") {
      continue;
    }
    if (pidAlive(job.pid)) {
      continue;
    }
    const jobFile = resolveJobFile(workspaceRoot, job.id);
    const stored = fs.existsSync(jobFile) ? readJobFile(jobFile) : {};
    workflowJobLifecycle(workspaceRoot, { ...stored, ...job }).finalize("failed", {
      errorMessage: `Workflow process ${job.pid ?? "(unrecorded)"} is gone; the run never finished.`
    });
  }
}

// workers.json may be ABSENT rather than `[]` — a fully-cached resume never
// spawns a worker — and a recorded pid may already have exited. Neither is an
// error, and neither may throw: this runs from a signal handler.
export function killWorkflowWorkers(runDir, signal = "SIGTERM") {
  if (!runDir) {
    return [];
  }
  let pids;
  try {
    pids = JSON.parse(fs.readFileSync(path.join(runDir, "workers.json"), "utf8"));
  } catch {
    return [];
  }
  if (!Array.isArray(pids)) {
    return [];
  }
  const signalled = [];
  for (const pid of pids) {
    if (typeof pid !== "number") {
      continue;
    }
    try {
      process.kill(pid, signal);
      signalled.push(pid);
    } catch {
      /* already gone */
    }
  }
  return signalled;
}
