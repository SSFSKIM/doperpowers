#!/usr/bin/env node

import fs from "node:fs";
import process from "node:process";

import { pidInstanceVerified } from "./lib/pid.mjs";
import { terminateProcessTree } from "./lib/process.mjs";
import { killWorkflowWorkers, WORKFLOW_JOB_CLASS } from "./lib/workflow/job.mjs";
import { BROKER_ENDPOINT_ENV } from "./lib/app-server.mjs";
import {
  clearBrokerSession,
  LOG_FILE_ENV,
  loadBrokerSession,
  PID_FILE_ENV,
  sendBrokerShutdown,
  teardownBrokerSession
} from "./lib/broker-lifecycle.mjs";
import { loadState, resolveStateFile, updateState } from "./lib/state.mjs";
import { TRANSCRIPT_PATH_ENV } from "./lib/claude-session-transfer.mjs";
import { resolveWorkspaceRoot } from "./lib/workspace.mjs";

export const SESSION_ID_ENV = "CODEX_COMPANION_SESSION_ID";
const PLUGIN_DATA_ENV = "CLAUDE_PLUGIN_DATA";

function readHookInput() {
  const raw = fs.readFileSync(0, "utf8").trim();
  if (!raw) {
    return {};
  }
  return JSON.parse(raw);
}

function shellEscape(value) {
  return `'${String(value).replace(/'/g, `'\"'\"'`)}'`;
}

function appendEnvVar(name, value) {
  if (!process.env.CLAUDE_ENV_FILE || value == null || value === "") {
    return;
  }
  fs.appendFileSync(process.env.CLAUDE_ENV_FILE, `export ${name}=${shellEscape(value)}\n`, "utf8");
}

function cleanupSessionJobs(cwd, sessionId) {
  if (!cwd || !sessionId) {
    return;
  }

  const workspaceRoot = resolveWorkspaceRoot(cwd);
  const stateFile = resolveStateFile(workspaceRoot);
  if (!fs.existsSync(stateFile)) {
    return;
  }

  if (!loadState(workspaceRoot).jobs.some((job) => job.sessionId === sessionId)) {
    return;
  }

  // This is a ledger WRITER, so it takes the same lock every other writer takes.
  // An unlocked load-then-save could be renamed over a concurrent upsertJob's
  // ledger — and saveState's pruning pass would then delete the job record and
  // log that upsert had just added, reading them as dropped. The rows are
  // re-read inside the lock: the snapshot above is only a cheap "is there
  // anything to do at all".
  updateState(workspaceRoot, (state) => {
    for (const job of state.jobs) {
      if (job.sessionId !== sessionId) {
        continue;
      }
      const stillRunning = job.status === "queued" || job.status === "running";
      if (!stillRunning) {
        continue;
      }
      // Only a pid this row can PROVE is still its own process: terminateProcessTree
      // signals a whole process GROUP, and a row that outlived a reboot points at
      // whoever inherited the number. Unprovable (unstamped, or a platform with no
      // readable start time) is never signalled — the same rule every kill path here
      // follows.
      if (!pidInstanceVerified(job.pid ?? Number.NaN, job.pidStart ?? null)) {
        continue;
      }
      try {
        // A workflow run is a plain foreground child of whoever launched it, not a
        // process-group leader, so the group signal raises ESRCH and delivers
        // nothing. Dropping the row on that would leave the run — and its workers —
        // executing with nothing left addressing them, so this is the same direct
        // signal + worker sweep that `cancel` does.
        const outcome = terminateProcessTree(job.pid ?? Number.NaN);
        if (!outcome.delivered) {
          try {
            process.kill(job.pid, "SIGTERM");
          } catch {
            /* already gone */
          }
        }
      } catch {
        // Ignore teardown failures during session shutdown.
      }
      if (job.jobClass === WORKFLOW_JOB_CLASS) {
        killWorkflowWorkers(job.runDir ?? null);
      }
    }
    state.jobs = state.jobs.filter((job) => job.sessionId !== sessionId);
  });
}

function handleSessionStart(input) {
  appendEnvVar(SESSION_ID_ENV, input.session_id);
  appendEnvVar(TRANSCRIPT_PATH_ENV, input.transcript_path);
  appendEnvVar(PLUGIN_DATA_ENV, process.env[PLUGIN_DATA_ENV]);
}

async function handleSessionEnd(input) {
  const cwd = input.cwd || process.cwd();
  const brokerSession =
    loadBrokerSession(cwd) ??
    (process.env[BROKER_ENDPOINT_ENV]
      ? {
          endpoint: process.env[BROKER_ENDPOINT_ENV],
          pidFile: process.env[PID_FILE_ENV] ?? null,
          logFile: process.env[LOG_FILE_ENV] ?? null
        }
      : null);
  const brokerEndpoint = brokerSession?.endpoint ?? null;
  const pidFile = brokerSession?.pidFile ?? null;
  const logFile = brokerSession?.logFile ?? null;
  const sessionDir = brokerSession?.sessionDir ?? null;
  const pid = brokerSession?.pid ?? null;
  // Only the record that broker.json itself wrote can carry an instance stamp;
  // the env-var fallback below has a pid of null anyway.
  const pidStart = brokerSession?.pidStart ?? null;

  if (brokerEndpoint) {
    await sendBrokerShutdown(brokerEndpoint);
  }

  cleanupSessionJobs(cwd, input.session_id || process.env[SESSION_ID_ENV]);
  teardownBrokerSession({
    endpoint: brokerEndpoint,
    pidFile,
    logFile,
    sessionDir,
    pid,
    pidStart,
    killProcess: terminateProcessTree
  });
  clearBrokerSession(cwd);
}

async function main() {
  const input = readHookInput();
  const eventName = process.argv[2] ?? input.hook_event_name ?? "";

  if (eventName === "SessionStart") {
    handleSessionStart(input);
    return;
  }

  if (eventName === "SessionEnd") {
    await handleSessionEnd(input);
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
