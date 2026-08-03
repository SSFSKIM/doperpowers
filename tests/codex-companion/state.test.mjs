import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

import { makeTempDir, run } from "./helpers.mjs";
import {
  ensureStateDir,
  loadState,
  resolveJobFile,
  resolveJobLogFile,
  resolveStateDir,
  resolveStateFile,
  saveState,
  STATE_LOCK_TIMEOUT_MS,
  upsertJob
} from "../../skills/codex-companion/runtime/scripts/lib/state.mjs";

// Plants a lock directory as if a writer were holding it. `pid` null plants a
// lock with no holder stamp at all — the freshly-created / mid-break window.
function plantLock(workspace, pid) {
  ensureStateDir(workspace);
  const lockDir = `${resolveStateFile(workspace)}.lock`;
  fs.mkdirSync(lockDir);
  if (pid != null) {
    fs.writeFileSync(path.join(lockDir, "holder"), String(pid), "utf8");
  }
  return lockDir;
}

function deadPid() {
  const finished = run(process.execPath, ["-e", "process.exit(0)"]);
  assert.equal(finished.status, 0);
  return finished.pid;
}

test("resolveStateDir uses a temp-backed per-workspace directory", () => {
  const workspace = makeTempDir();
  const stateDir = resolveStateDir(workspace);

  assert.equal(stateDir.startsWith(os.tmpdir()), true);
  assert.match(path.basename(stateDir), /.+-[a-f0-9]{16}$/);
  assert.match(stateDir, new RegExp(`^${os.tmpdir().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
});

test("resolveStateDir uses CLAUDE_PLUGIN_DATA when it is provided", () => {
  const workspace = makeTempDir();
  const pluginDataDir = makeTempDir();
  const previousPluginDataDir = process.env.CLAUDE_PLUGIN_DATA;
  process.env.CLAUDE_PLUGIN_DATA = pluginDataDir;

  try {
    const stateDir = resolveStateDir(workspace);

    assert.equal(stateDir.startsWith(path.join(pluginDataDir, "state")), true);
    assert.match(path.basename(stateDir), /.+-[a-f0-9]{16}$/);
    assert.match(
      stateDir,
      new RegExp(`^${path.join(pluginDataDir, "state").replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`)
    );
  } finally {
    if (previousPluginDataDir == null) {
      delete process.env.CLAUDE_PLUGIN_DATA;
    } else {
      process.env.CLAUDE_PLUGIN_DATA = previousPluginDataDir;
    }
  }
});

test("saveState prunes dropped job artifacts when indexed jobs exceed the cap", () => {
  const workspace = makeTempDir();
  const stateFile = resolveStateFile(workspace);
  fs.mkdirSync(path.dirname(stateFile), { recursive: true });

  const jobs = Array.from({ length: 51 }, (_, index) => {
    const jobId = `job-${index}`;
    const updatedAt = new Date(Date.UTC(2026, 0, 1, 0, index, 0)).toISOString();
    const logFile = resolveJobLogFile(workspace, jobId);
    const jobFile = resolveJobFile(workspace, jobId);
    fs.writeFileSync(logFile, `log ${jobId}\n`, "utf8");
    fs.writeFileSync(jobFile, JSON.stringify({ id: jobId, status: "completed" }, null, 2), "utf8");
    return {
      id: jobId,
      status: "completed",
      logFile,
      updatedAt,
      createdAt: updatedAt
    };
  });

  fs.writeFileSync(
    stateFile,
    `${JSON.stringify(
      {
        version: 1,
        config: { stopReviewGate: false },
        jobs
      },
      null,
      2
    )}\n`,
    "utf8"
  );

  saveState(workspace, {
    version: 1,
    config: { stopReviewGate: false },
    jobs
  });

  const prunedJobFile = resolveJobFile(workspace, "job-0");
  const prunedLogFile = resolveJobLogFile(workspace, "job-0");
  const retainedJobFile = resolveJobFile(workspace, "job-50");
  const retainedLogFile = resolveJobLogFile(workspace, "job-50");
  const jobsDir = path.dirname(prunedJobFile);

  assert.equal(fs.existsSync(retainedJobFile), true);
  assert.equal(fs.existsSync(retainedLogFile), true);

  const savedState = JSON.parse(fs.readFileSync(stateFile, "utf8"));
  assert.equal(savedState.jobs.length, 50);
  assert.deepEqual(
    savedState.jobs.map((job) => job.id),
    Array.from({ length: 50 }, (_, index) => `job-${50 - index}`)
  );
  assert.deepEqual(
    fs.readdirSync(jobsDir).sort(),
    Array.from({ length: 50 }, (_, index) => `job-${index + 1}`)
      .flatMap((jobId) => [`${jobId}.json`, `${jobId}.log`])
      .sort()
  );
});

// A writer SIGKILLed inside the critical section leaves its lock behind. Without
// stale-lock breaking that wedges every later writer permanently, which the
// workflow verb's own SIGKILL path makes a routine occurrence rather than a
// theoretical one.
test("updateState breaks a lock whose holder is dead and lands the mutation", () => {
  const workspace = makeTempDir();
  const lockDir = plantLock(workspace, deadPid());

  upsertJob(workspace, { id: "job-after-break", status: "completed" });

  assert.deepEqual(
    loadState(workspace).jobs.map((job) => job.id),
    ["job-after-break"]
  );
  assert.equal(fs.existsSync(lockDir), false);
});

test("updateState waits out a live holder and fails loudly, naming the lock", () => {
  const workspace = makeTempDir();
  const lockDir = plantLock(workspace, process.pid);
  const startedAt = Date.now();

  assert.throws(
    () => upsertJob(workspace, { id: "job-never-written", status: "completed" }),
    (error) => error.message.includes(lockDir) && error.message.includes(`live pid ${process.pid}`)
  );

  assert.ok(Date.now() - startedAt >= STATE_LOCK_TIMEOUT_MS);
  assert.equal(fs.existsSync(lockDir), true, "a live holder's lock must survive");
  assert.deepEqual(loadState(workspace).jobs, []);
});

test("updateState never breaks a lock that carries no holder stamp", () => {
  const workspace = makeTempDir();
  const lockDir = plantLock(workspace, null);

  assert.throws(
    () => upsertJob(workspace, { id: "job-never-written", status: "completed" }),
    (error) => error.message.includes(lockDir) && error.message.includes("holder unknown")
  );

  assert.equal(fs.existsSync(lockDir), true, "an unstamped lock is contended, never breakable");
  assert.deepEqual(loadState(workspace).jobs, []);
});

// …but "never" cannot mean never: mkdirSync landing and the process being
// killed before the stamp write leaves an unstamped lock nobody can ever break,
// and every state mutation from then on times out until someone deletes it by
// hand. Contended for a moment, abandoned after a minute — the window between
// mkdir and one small file write is microseconds, so age settles which it is.
test("updateState breaks an unstamped lock that has been abandoned long enough", () => {
  const workspace = makeTempDir();
  const lockDir = plantLock(workspace, null);
  const longAgo = new Date(Date.now() - 10 * 60 * 1000);
  fs.utimesSync(lockDir, longAgo, longAgo);

  upsertJob(workspace, { id: "job-after-wedge", status: "completed" });

  assert.deepEqual(
    loadState(workspace).jobs.map((job) => job.id),
    ["job-after-wedge"]
  );
  assert.equal(fs.existsSync(lockDir), false, "the abandoned lock is gone");
});

// mkdirSync succeeding and the stamp write failing (ENOSPC, EACCES, a full
// inode table) would abandon an UNSTAMPED lock — unbreakable by design, which is
// exactly the permanent wedge the breaking mechanism exists to remove.
test("updateState gives the lock back when the holder stamp cannot be written", () => {
  const workspace = makeTempDir();
  const lockDir = `${resolveStateFile(workspace)}.lock`;
  const realWriteFileSync = fs.writeFileSync;
  fs.writeFileSync = (target, ...rest) => {
    if (String(target).endsWith(`${path.sep}holder`)) {
      throw Object.assign(new Error("EACCES: permission denied"), { code: "EACCES" });
    }
    return realWriteFileSync(target, ...rest);
  };

  try {
    assert.throws(() => upsertJob(workspace, { id: "job-not-written", status: "completed" }), /EACCES/);
  } finally {
    fs.writeFileSync = realWriteFileSync;
  }

  assert.equal(fs.existsSync(lockDir), false, "an unstampable lock must not be left behind");

  upsertJob(workspace, { id: "job-after-stamp-failure", status: "completed" });
  assert.deepEqual(
    loadState(workspace).jobs.map((job) => job.id),
    ["job-after-stamp-failure"]
  );
});
