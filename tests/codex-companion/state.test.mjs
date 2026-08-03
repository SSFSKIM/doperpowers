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

// The window between mkdirSync landing and the stamp write is normally
// microseconds — but it is the same window the TTL above declares abandoned, so
// a claimer stalled long enough (a stop signal, a paused VM, a swapping host)
// wakes up to find its lock broken and RETAKEN. Its stamp must not land in the
// successor's directory: that is two writers inside one critical section, which
// is the exact thing the lock exists to prevent.
//
// `swapLockOnStamp` is that interleaving, forced: the successor's break-and-
// retake happens inside the stalled claimer's own holder write.
function swapLockOnStamp(lockDir, { stampSuccessor, thenThrow = null }) {
  const realWriteFileSync = fs.writeFileSync;
  let swapped = false;
  fs.writeFileSync = (target, ...rest) => {
    if (!swapped && String(target).endsWith(`${path.sep}holder`)) {
      swapped = true;
      fs.rmSync(lockDir, { recursive: true, force: true });
      fs.mkdirSync(lockDir);
      if (stampSuccessor) {
        // A LIVE successor: only its own stamp may be in this directory.
        realWriteFileSync(path.join(lockDir, "holder"), JSON.stringify({ pid: process.pid, pidStart: null }), "utf8");
      }
      if (thenThrow) {
        throw thenThrow;
      }
    }
    return realWriteFileSync(target, ...rest);
  };
  return () => {
    fs.writeFileSync = realWriteFileSync;
  };
}

test("a stalled claimer cannot stamp itself over a successor's lock", () => {
  const workspace = makeTempDir();
  const lockDir = `${resolveStateFile(workspace)}.lock`;
  const restore = swapLockOnStamp(lockDir, { stampSuccessor: true });

  try {
    assert.throws(
      () => upsertJob(workspace, { id: "job-from-the-stalled-writer", status: "completed" }),
      (error) => error.message.includes(lockDir) && error.message.includes(`live pid ${process.pid}`),
      "the stalled claimer lost the lock and must wait for it like anyone else"
    );
  } finally {
    restore();
  }

  assert.equal(fs.existsSync(lockDir), true, "the successor's lock survives");
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(lockDir, "holder"), "utf8")),
    { pid: process.pid, pidStart: null },
    "…and still names the successor, not the writer that lost the race"
  );
  assert.deepEqual(loadState(workspace).jobs, [], "no mutation entered behind the successor's back");
});

// Same race, one instant earlier: the successor has retaken the directory but
// has not stamped it yet, so the stalled claimer's stamp write SUCCEEDS. The
// directory it landed in is not the one it created, which is the only thing that
// can tell the two apart.
test("a stamp that lands in a directory we no longer own does not grant the lock", () => {
  const workspace = makeTempDir();
  const lockDir = `${resolveStateFile(workspace)}.lock`;
  const restore = swapLockOnStamp(lockDir, { stampSuccessor: false });

  try {
    assert.throws(
      () => upsertJob(workspace, { id: "job-from-the-stalled-writer", status: "completed" }),
      /state lock timeout/,
      "a lock directory we did not create is not ours to hold"
    );
  } finally {
    restore();
  }

  assert.deepEqual(loadState(workspace).jobs, [], "no mutation entered behind the successor's back");
});

// And the failure the same interleaving produces first: our directory is gone,
// so the stamp write fails with ENOENT. Removing "the lock" there removes the
// SUCCESSOR's — handing the critical section to a third writer while the
// successor is inside it.
test("a stamp that fails because our lock is gone never deletes the successor's", () => {
  const workspace = makeTempDir();
  const lockDir = `${resolveStateFile(workspace)}.lock`;
  const restore = swapLockOnStamp(lockDir, {
    stampSuccessor: true,
    thenThrow: Object.assign(new Error("ENOENT: no such file or directory"), { code: "ENOENT" })
  });

  try {
    assert.throws(
      () => upsertJob(workspace, { id: "job-from-the-stalled-writer", status: "completed" }),
      (error) => error.message.includes(lockDir) && error.message.includes(`live pid ${process.pid}`),
      "a vanished claim is a lost race, not an error to hand back"
    );
  } finally {
    restore();
  }

  assert.equal(fs.existsSync(lockDir), true, "the successor's lock survives");
  assert.deepEqual(loadState(workspace).jobs, []);
});

// A ledger written before ids were validated can contain one that is not a path
// segment — `--resume ../state` wrote exactly that. Every later mutation walks
// the prune pass, which turns each dropped id into a file path, and one throw
// there fails EVERY write from then on: the poisoned row cannot be removed by
// the mechanism whose job is removing rows. Drop it, touch nothing it names.
test("a ledger row whose id is not a path segment is dropped, not thrown on", () => {
  const workspace = makeTempDir();
  const stateFile = resolveStateFile(workspace);
  ensureStateDir(workspace);
  const bystander = path.join(path.dirname(stateFile), "bystander.json");
  fs.writeFileSync(bystander, "{}\n", "utf8");

  fs.writeFileSync(
    stateFile,
    `${JSON.stringify({
      version: 1,
      config: { stopReviewGate: true },
      jobs: [
        { id: "../bystander", status: "running", jobClass: "workflow", updatedAt: "2026-01-01T00:00:00.000Z" },
        { id: "job-real", status: "completed", updatedAt: "2026-01-02T00:00:00.000Z" }
      ]
    }, null, 2)}\n`,
    "utf8"
  );

  upsertJob(workspace, { id: "job-new", status: "running" });

  const jobs = loadState(workspace).jobs;
  assert.deepEqual(
    jobs.map((job) => job.id).sort(),
    ["job-new", "job-real"],
    "the poisoned row is gone and the healthy ones are untouched"
  );
  assert.equal(fs.existsSync(bystander), true, "…and nothing it pointed at was deleted");
  assert.equal(loadState(workspace).config.stopReviewGate, true, "the config survived the write");
});
