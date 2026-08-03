import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { resolveWorkspaceRoot } from "./workspace.mjs";

const STATE_VERSION = 1;
const PLUGIN_DATA_ENV = "CLAUDE_PLUGIN_DATA";
const FALLBACK_STATE_ROOT_DIR = path.join(os.tmpdir(), "codex-companion");
const STATE_FILE_NAME = "state.json";
const JOBS_DIR_NAME = "jobs";
const MAX_JOBS = 50;
// The lock directory is the atomic primitive; the file inside it names the
// holder so a dead one can be broken instead of wedging every later writer.
const LOCK_HOLDER_FILE = "holder";
export const STATE_LOCK_TIMEOUT_MS = 5000;

function nowIso() {
  return new Date().toISOString();
}

function defaultState() {
  return {
    version: STATE_VERSION,
    config: {
      stopReviewGate: false
    },
    jobs: []
  };
}

export function resolveStateDir(cwd) {
  const workspaceRoot = resolveWorkspaceRoot(cwd);
  let canonicalWorkspaceRoot = workspaceRoot;
  try {
    canonicalWorkspaceRoot = fs.realpathSync.native(workspaceRoot);
  } catch {
    canonicalWorkspaceRoot = workspaceRoot;
  }

  const slugSource = path.basename(workspaceRoot) || "workspace";
  const slug = slugSource.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "workspace";
  const hash = createHash("sha256").update(canonicalWorkspaceRoot).digest("hex").slice(0, 16);
  const pluginDataDir = process.env[PLUGIN_DATA_ENV];
  const stateRoot = pluginDataDir ? path.join(pluginDataDir, "state") : FALLBACK_STATE_ROOT_DIR;
  return path.join(stateRoot, `${slug}-${hash}`);
}

// The plugin data root itself (state lives under `state/` inside it; workflow
// run directories live under `workflows/`).
function resolveDataRoot() {
  return process.env[PLUGIN_DATA_ENV] ?? FALLBACK_STATE_ROOT_DIR;
}

export function resolveWorkflowRunDir(runId) {
  return path.join(resolveDataRoot(), "workflows", runId);
}

export function resolveStateFile(cwd) {
  return path.join(resolveStateDir(cwd), STATE_FILE_NAME);
}

export function resolveJobsDir(cwd) {
  return path.join(resolveStateDir(cwd), JOBS_DIR_NAME);
}

export function ensureStateDir(cwd) {
  fs.mkdirSync(resolveJobsDir(cwd), { recursive: true });
}

export function loadState(cwd) {
  const stateFile = resolveStateFile(cwd);
  if (!fs.existsSync(stateFile)) {
    return defaultState();
  }

  try {
    const parsed = JSON.parse(fs.readFileSync(stateFile, "utf8"));
    return {
      ...defaultState(),
      ...parsed,
      config: {
        ...defaultState().config,
        ...(parsed.config ?? {})
      },
      jobs: Array.isArray(parsed.jobs) ? parsed.jobs : []
    };
  } catch {
    return defaultState();
  }
}

function pruneJobs(jobs) {
  return [...jobs]
    .sort((left, right) => String(right.updatedAt ?? "").localeCompare(String(left.updatedAt ?? "")))
    .slice(0, MAX_JOBS);
}

function removeFileIfExists(filePath) {
  if (filePath && fs.existsSync(filePath)) {
    fs.unlinkSync(filePath);
  }
}

export function saveState(cwd, state) {
  const previousJobs = loadState(cwd).jobs;
  ensureStateDir(cwd);
  const nextJobs = pruneJobs(state.jobs ?? []);
  const nextState = {
    version: STATE_VERSION,
    config: {
      ...defaultState().config,
      ...(state.config ?? {})
    },
    jobs: nextJobs
  };

  const retainedIds = new Set(nextJobs.map((job) => job.id));
  for (const job of previousJobs) {
    if (retainedIds.has(job.id)) {
      continue;
    }
    removeJobFile(resolveJobFile(cwd, job.id));
    removeFileIfExists(job.logFile);
  }

  // Write-then-rename: a reader (status/result/cancel in another process) must
  // never observe a half-written ledger, and a crash mid-write must not truncate
  // the one it had.
  const target = resolveStateFile(cwd);
  const tmp = `${target}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, `${JSON.stringify(nextState, null, 2)}\n`, "utf8");
  fs.renameSync(tmp, target);
  return nextState;
}

// updateState is the single load-mutate-write choke point every writer flows
// through (upsertJob, setConfig, and so every verb). Serializing HERE — rather
// than around one verb's own writes — is what stops two concurrent runs from
// losing each other's job records: an unlocked legacy writer would happily
// overwrite a workflow's row with a ledger it loaded before that row existed.
function readPidFile(filePath) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, "utf8");
  } catch (err) {
    if (err.code === "ENOENT") {
      return null;
    }
    throw err;
  }
  const pid = Number(raw.trim());
  return Number.isInteger(pid) && pid > 0 ? pid : null;
}

// ESRCH is the ONLY proof of death. EPERM means the process exists and belongs
// to someone else, and any other errno is unexplained — both count as alive, so
// an unexplained answer can never cost anyone their lock.
function pidIsDead(pid) {
  try {
    process.kill(pid, 0);
    return false;
  } catch (err) {
    return err.code === "ESRCH";
  }
}

// The four states a held lock can be in. Only "dead" may ever be broken:
// "unstamped" is the one-syscall window between mkdir and the stamp landing (or
// a lock being broken right now), and "corrupt" is a stamp nobody has proven
// dead — both are contended, so a wrong read costs a wait, never a lock.
function inspectLock(lockDir) {
  const pid = readPidFile(path.join(lockDir, LOCK_HOLDER_FILE));
  if (pid == null) {
    if (!fs.existsSync(lockDir)) {
      return { state: "absent" };
    }
    return { state: fs.existsSync(path.join(lockDir, LOCK_HOLDER_FILE)) ? "corrupt" : "unstamped" };
  }
  return { state: pidIsDead(pid) ? "dead" : "live", pid };
}

// Atomic create — the only way to own a break token.
function claimToken(tokenPath) {
  try {
    fs.writeFileSync(tokenPath, String(process.pid), { flag: "wx" });
    return true;
  } catch (err) {
    if (err.code !== "EEXIST") {
      throw err;
    }
    return false;
  }
}

// A holder SIGKILLed inside the critical section leaves its lock behind, and
// without this every later writer blocks to the deadline and then fails —
// forever. BREAKING MUST ALSO BE SERIALIZED: two breakers that both read the
// same dead pid would take turns deleting each other's freshly created LIVE
// lock. Same fix as the workflow run lease (workflow/journal.mjs): a break
// token keyed to the observed holder, and a re-inspect UNDER that token so only
// a still-dead lock is ever removed.
function breakDeadLock(lockDir, observed) {
  const tokenPath = `${lockDir}.break-${observed.pid}`;
  if (!claimToken(tokenPath)) {
    // Token held: its owner is breaking right now (retry and we will see their
    // lock), or it died mid-break — clear that wedge so a dead breaker cannot
    // pin acquisition forever.
    const breaker = readPidFile(tokenPath);
    if (breaker == null || pidIsDead(breaker)) {
      fs.rmSync(tokenPath, { force: true });
    }
    return false;
  }
  try {
    if (inspectLock(lockDir).state !== "dead") {
      return false; // broken and retaken since the read that sent us here
    }
    fs.rmSync(lockDir, { recursive: true, force: true });
    return true;
  } finally {
    fs.rmSync(tokenPath, { force: true });
  }
}

function withStateLock(cwd, fn) {
  ensureStateDir(cwd);
  const lockDir = `${resolveStateFile(cwd)}.lock`;
  const holderPath = path.join(lockDir, LOCK_HOLDER_FILE);
  const deadline = Date.now() + STATE_LOCK_TIMEOUT_MS;
  for (;;) {
    let acquired = false;
    try {
      fs.mkdirSync(lockDir);
      acquired = true;
    } catch (err) {
      if (err.code !== "EEXIST") {
        throw err;
      }
    }

    if (acquired) {
      // Stamped immediately: until this lands the lock reads as "unstamped",
      // which is unbreakable — the safe direction while we are alive to finish
      // the job. But an unstamped lock we ABANDON is the permanent wedge this
      // whole mechanism exists to remove, so a failed stamp gives the lock back
      // before the error propagates.
      try {
        fs.writeFileSync(holderPath, String(process.pid), "utf8");
      } catch (err) {
        fs.rmSync(lockDir, { recursive: true, force: true });
        throw err;
      }
      break;
    }

    const observed = inspectLock(lockDir);
    if (observed.state === "dead" && breakDeadLock(lockDir, observed)) {
      continue; // retake through the same atomic mkdir every contender uses
    }
    if (Date.now() > deadline) {
      const holder = readPidFile(holderPath);
      throw new Error(
        `state lock timeout: ${lockDir} (${holder ? `held by live pid ${holder}` : "holder unknown"})`
      );
    }
    // Bounded synchronous backoff: the whole mutation API is sync, so there is
    // no event loop to yield to.
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 15);
  }
  try {
    return fn();
  } finally {
    try {
      fs.rmSync(lockDir, { recursive: true, force: true });
    } catch {
      /* already released */
    }
  }
}

export function updateState(cwd, mutate) {
  return withStateLock(cwd, () => {
    const state = loadState(cwd);
    mutate(state);
    return saveState(cwd, state);
  });
}

export function generateJobId(prefix = "job") {
  const random = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${Date.now().toString(36)}-${random}`;
}

export function upsertJob(cwd, jobPatch) {
  return updateState(cwd, (state) => {
    const timestamp = nowIso();
    const existingIndex = state.jobs.findIndex((job) => job.id === jobPatch.id);
    if (existingIndex === -1) {
      state.jobs.unshift({
        createdAt: timestamp,
        updatedAt: timestamp,
        ...jobPatch
      });
      return;
    }
    state.jobs[existingIndex] = {
      ...state.jobs[existingIndex],
      ...jobPatch,
      updatedAt: timestamp
    };
  });
}

export function listJobs(cwd) {
  return loadState(cwd).jobs;
}

export function setConfig(cwd, key, value) {
  return updateState(cwd, (state) => {
    state.config = {
      ...state.config,
      [key]: value
    };
  });
}

export function getConfig(cwd) {
  return loadState(cwd).config;
}

export function writeJobFile(cwd, jobId, payload) {
  ensureStateDir(cwd);
  const jobFile = resolveJobFile(cwd, jobId);
  fs.writeFileSync(jobFile, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return jobFile;
}

export function readJobFile(jobFile) {
  return JSON.parse(fs.readFileSync(jobFile, "utf8"));
}

function removeJobFile(jobFile) {
  if (fs.existsSync(jobFile)) {
    fs.unlinkSync(jobFile);
  }
}

export function resolveJobLogFile(cwd, jobId) {
  ensureStateDir(cwd);
  return path.join(resolveJobsDir(cwd), `${jobId}.log`);
}

export function resolveJobFile(cwd, jobId) {
  ensureStateDir(cwd);
  return path.join(resolveJobsDir(cwd), `${jobId}.json`);
}
