// Process identity, not just a process number.
//
// Everything durable in this runtime records a pid: the workflow run lease, the
// state lock's holder stamp, workers.json, and the job row that `status`,
// `--resume` and `cancel` all act on. Pids are REUSED — trivially across a
// reboot, eventually through wraparound on a long-lived machine — so a bare pid
// cannot answer "is the process I recorded still alive". Two ways that hurts:
// a stale lease or lock reads as live and nothing can ever break it (every later
// writer times out), and cancel SIGTERMs whatever now owns the number.
//
// The process start time is the cheap instance discriminator: one `ps` read, no
// privileges, no bookkeeping, and stable for the life of the process. Its
// one-second granularity is not a weakness here — for a false match a machine
// would have to reissue the same pid within the same second.
import { execFileSync } from "node:child_process";
import process from "node:process";

const START_TIME_PLATFORMS = new Set(["darwin", "linux"]);

// Never memoized for other pids: the answer changes precisely when a pid is
// reused, which is the thing being detected.
export function processStartTime(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return null;
  }
  if (!START_TIME_PLATFORMS.has(process.platform)) {
    return null; // unknown here ⇒ no stamp is written, and liveness stays pid-only
  }
  try {
    const out = execFileSync("ps", ["-o", "lstart=", "-p", String(pid)], {
      stdio: ["ignore", "pipe", "ignore"],
      encoding: "utf8"
    }).trim();
    return out || null;
  } catch {
    return null; // the process is gone, or `ps` is unavailable: no claim either way
  }
}

let selfStamp = null;

// What a writer stamps its own records with. Memoized: our own start time cannot
// change, and this is on the path of every job registration.
export function currentPidStamp() {
  if (!selfStamp) {
    selfStamp = { pid: process.pid, pidStart: processStartTime(process.pid) };
  }
  return { ...selfStamp };
}

// The one liveness rule for every persisted pid in the runtime.
//
// ESRCH is the ONLY proof of death by signal: EPERM means the process exists and
// belongs to someone else, and any other errno is unexplained — both count as
// alive, so an unexplained answer can never cost anyone their lock, lease or run.
// A start-time MISMATCH is the second proof of death, and a real one: the number
// is in use, but not by the process that was recorded.
//
// A record with no start time (written before stamps existed, or on a platform
// that cannot read one) keeps the old pid-only behavior — old on-disk state must
// not start reading as dead.
export function pidInstanceAlive(pid, pidStart = null) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
  } catch (err) {
    if (err.code === "ESRCH") {
      return false;
    }
  }
  if (!pidStart) {
    return true;
  }
  const current = processStartTime(pid);
  if (!current) {
    return true; // could not tell: never claim death on ignorance
  }
  return current === pidStart;
}
