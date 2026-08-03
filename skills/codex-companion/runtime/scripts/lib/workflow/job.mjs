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

import { currentPidStamp, pidInstanceAlive, pidInstanceVerified } from "../pid.mjs";
import { isPathSegment, listJobs, readJobFile, resolveJobFile, updateState, upsertJob, writeJobFile } from "../state.mjs";

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
      // The pid is stamped with this process's start time: after a reboot or a
      // pid wraparound the number alone would make a long-dead run read as
      // running, and cancel would signal whatever inherited it.
      return persist({
        status: "running",
        phase: "running",
        ...currentPidStamp(),
        startedAt: record.startedAt ?? nowIso()
      });
    },
    finalize(status, patch = {}) {
      return persist(finalizePatch(record, status, patch));
    }
  };
}

// The terminal patch for a record, shared by the lifecycle above and the lazy
// repair below (which cannot use the lifecycle: its writes have to happen inside
// the state lock, and persist() takes that lock itself).
function finalizePatch(record, status, patch = {}) {
  const next = {
    ...patch,
    status,
    phase: PHASE_BY_STATUS[status] ?? status,
    pid: null,
    pidStart: null,
    completedAt: nowIso()
  };
  // Rendered eagerly so `result` shows the run directory on every terminal
  // path, including the lazily repaired one where nothing else ran.
  next.rendered = renderWorkflowJobResult({ ...record, ...next });
  return next;
}

// Same rule as the state lock and the run lease (lib/pid.mjs): ESRCH or a
// start-time mismatch is death, everything else is life — so an unexplained
// answer can never finalize a live run as failed, and a reused pid can never
// keep a dead one alive. A row with no pidStart (written before stamps existed)
// stays pid-only.
const pidAlive = (pid, pidStart = null) => pidInstanceAlive(pid, pidStart);

// `--resume <run-id>` reuses the run's job id, so a resume of a run that is
// still going would overwrite that run's own record before the engine's lease
// check ever fires. The lease is the race-free guard; this is what keeps the
// ledger honest in the ordinary case.
export function isWorkflowRunActive(workspaceRoot, runId) {
  // The ledger row, not the per-job file: the ledger is written atomically under
  // a lock, so it can never be torn, and this must not throw on a record some
  // killed writer left half-finished.
  const job = listJobs(workspaceRoot).find((row) => row.id === runId);
  return Boolean(job) && job.status === "running" && pidAlive(job.pid, job.pidStart);
}

// A per-job file written by a process that died mid-write (and every file
// written before writeJobFile became atomic) can be empty or truncated. An
// unguarded parse here would throw on EVERY status/result/cancel, so the lazy
// repair below would never run and the phantom `running` row would be permanent.
function readStoredJobOrCorrupt(jobFile) {
  if (!fs.existsSync(jobFile)) {
    return { stored: {}, corrupt: false };
  }
  try {
    return { stored: readJobFile(jobFile), corrupt: false };
  } catch {
    return { stored: {}, corrupt: true };
  }
}

// An id that is not a path segment cannot become a per-job file, so this pass
// cannot repair such a row and must not throw trying: it runs from every status,
// result and cancel, and one poisoned row (a ledger written before ids were
// validated) would take the whole runtime down with it. saveState drops those
// rows on the next write.
function isDeadWorkflowRow(job) {
  return (
    job.jobClass === WORKFLOW_JOB_CLASS &&
    isPathSegment(job.id) &&
    (job.status === "running" || job.status === "queued") &&
    !pidAlive(job.pid, job.pidStart)
  );
}

// A workflow run is one process, so nothing else will ever finalize its record:
// SIGKILL, a reboot or a crashed harness leaves it `running` forever. The read
// paths repair it lazily rather than reporting a phantom run.
//
// The dead-check and the finalize are ONE locked step. Split, they lose the race
// against the one thing that legitimately revives a run: a `--resume` registers
// a new live pid for the same id, and a repair that decided "dead" before that
// registration would overwrite a running run's record and ledger row as failed.
export function repairDeadWorkflowJobs(workspaceRoot) {
  // Unlocked probe first: every status/result/cancel calls this, and the
  // overwhelmingly common answer is that there is nothing to repair. Its verdict
  // is never trusted for a write — the rows are re-read and re-verified inside
  // the lock below.
  if (!listJobs(workspaceRoot).some(isDeadWorkflowRow)) {
    return;
  }
  updateState(workspaceRoot, (state) => {
    state.jobs.forEach((job, index) => {
      if (!isDeadWorkflowRow(job)) {
        return;
      }
      const { stored, corrupt } = readStoredJobOrCorrupt(resolveJobFile(workspaceRoot, job.id));
      const record = { ...stored, ...job };
      // The per-job file is rewritten too, so a torn one is REPAIRED here rather
      // than left to break the next read. writeJobFile takes no lock of its own,
      // which is why this can run inside the mutation.
      const finalized = {
        ...record,
        ...finalizePatch(record, "failed", {
          errorMessage: `Workflow process ${job.pid ?? "(unrecorded)"} is gone; the run never finished.${
            corrupt ? " Its record file was unreadable and has been rewritten." : ""
          }`
        })
      };
      writeJobFile(workspaceRoot, job.id, finalized);
      state.jobs[index] = { ...ledgerRow(finalized), updatedAt: nowIso() };
    });
  });
}

// workers.json may be ABSENT rather than `[]` — a fully-cached resume never
// spawns a worker — and a recorded pid may already have exited. Neither is an
// error, and neither may throw: this runs from a signal handler.
//
// Entries are `{pid, pidStart}`. This is a KILL path, so it follows that rule
// (pidInstanceVerified): only an entry whose instance can be proven right now is
// signalled. A bare number (the pre-stamp format) and a pid on a platform with
// no readable start time prove nothing and are skipped — the run directory
// outlives a reboot, and the number in it may belong to a stranger by then.
export function killWorkflowWorkers(runDir, signal = "SIGTERM") {
  if (!runDir) {
    return [];
  }
  let entries;
  try {
    entries = JSON.parse(fs.readFileSync(path.join(runDir, "workers.json"), "utf8"));
  } catch {
    return [];
  }
  if (!Array.isArray(entries)) {
    return [];
  }
  const signalled = [];
  for (const entry of entries) {
    const pid = typeof entry === "number" ? entry : entry?.pid;
    const pidStart = typeof entry === "number" ? null : entry?.pidStart ?? null;
    if (typeof pid !== "number") {
      continue;
    }
    if (!pidInstanceVerified(pid, pidStart)) {
      continue; // gone, unprovable, or the number belongs to someone else now
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
