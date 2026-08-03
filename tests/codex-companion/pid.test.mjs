// The process-instance token: what makes a persisted pid an identity.
//
// Two things are being pinned here. First, the token has to be STABLE for the
// life of the process — a token that moves under a live process makes every
// stamped record read as dead, which breaks live locks, breaks live leases and
// finalizes live runs. Second, a failed read is not an answer: it must never be
// remembered as one.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import test from "node:test";

import { makeTempDir } from "./helpers.mjs";
import {
  currentPidStamp,
  pidInstanceAlive,
  processStartTime
} from "../../skills/codex-companion/runtime/scripts/lib/pid.mjs";

// A /proc/<pid>/stat line. The comm field is the process name AS THE KERNEL HAS
// IT — unquoted, in parentheses, and free to contain spaces and parentheses of
// its own, which is why field 22 can only be counted from the LAST ')'.
function procStatLine(pid, comm, starttime) {
  const afterComm = [
    "S", "1", "1", "0", "-1", "4194304", "1234", "0", "0", "0", // fields 3-12
    "11", "22", "0", "0", "20", "0", "1", "0", "0",             // fields 13-21
    String(starttime)                                            // field 22
  ];
  return `${pid} (${comm}) ${afterComm.join(" ")} 9999 8888 7777\n`;
}

function fakeProc(pid, comm, starttime) {
  const root = makeTempDir("codex-fakeproc-");
  fs.mkdirSync(path.join(root, String(pid)));
  fs.writeFileSync(path.join(root, String(pid), "stat"), procStatLine(pid, comm, starttime), "utf8");
  return root;
}

// FIRST, before anything memoizes a good stamp: a read that fails must not be
// remembered. `ps` failing once (a fork that could not be taken, a PATH without
// it) would otherwise leave this process writing unstamped records forever.
test("currentPidStamp never memoizes a failed start-time read", () => {
  const empty = makeTempDir("codex-noproc-");

  const failed = currentPidStamp({ platform: "linux", procRoot: empty });
  assert.equal(failed.pid, process.pid);
  assert.equal(failed.pidStart, null, "an unreadable start time is no stamp at all");

  const recovered = currentPidStamp();
  assert.ok(recovered.pidStart, "the very next call must read again, not replay the failure");
  assert.equal(recovered.pid, process.pid);
});

// On Linux `ps -o lstart=` is derived from /proc/stat's btime plus the wall
// clock, so an NTP step or a suspend/resume MOVES it under a live process. The
// kernel's own field 22 is jiffies since boot: it cannot move.
test("the linux instance token is /proc/<pid>/stat field 22", () => {
  const root = fakeProc(4242, "codex", 987654);
  assert.equal(processStartTime(4242, { platform: "linux", procRoot: root }), "987654");
});

test("field 22 is counted from the last ')', so a comm with spaces and parens still parses", () => {
  const root = fakeProc(4243, "code x) (server", 5150);
  assert.equal(processStartTime(4243, { platform: "linux", procRoot: root }), "5150");
});

test("an unreadable /proc entry is no answer, not a claim of death", () => {
  const root = makeTempDir("codex-noproc-");
  assert.equal(processStartTime(9999, { platform: "linux", procRoot: root }), null);
  // …and a record that cannot be verified keeps the pid-only behavior.
  assert.equal(pidInstanceAlive(process.pid, null), true);
  assert.equal(pidInstanceAlive(process.pid, processStartTime(process.pid)), true);
});

// Every state-lock retry (~15ms), every worker spawn and every entry in the
// SIGTERM sweep asks for a start time. Reading the same pid twice in the same
// instant is the same answer.
test("start-time reads are cached for a short window, and failures are not cached", async () => {
  const root = fakeProc(4244, "codex", 111);
  const options = { platform: "linux", procRoot: root };

  assert.equal(processStartTime(4244, options), "111");
  fs.writeFileSync(path.join(root, "4244", "stat"), procStatLine(4244, "codex", 222), "utf8");
  assert.equal(processStartTime(4244, options), "111", "a repeat read inside the window is served from the cache");

  await new Promise((resolve) => setTimeout(resolve, 300));
  assert.equal(processStartTime(4244, options), "222", "and the window is short");

  // A miss is never cached: the pid appearing a moment later must be readable.
  const late = makeTempDir("codex-lateproc-");
  const lateOptions = { platform: "linux", procRoot: late };
  assert.equal(processStartTime(4245, lateOptions), null);
  fs.mkdirSync(path.join(late, "4245"));
  fs.writeFileSync(path.join(late, "4245", "stat"), procStatLine(4245, "codex", 333), "utf8");
  assert.equal(processStartTime(4245, lateOptions), "333", "a failed read left nothing behind to replay");
});

test("this platform can read its own start time, and it is stable across calls", () => {
  const first = processStartTime(process.pid);
  assert.ok(first, `no instance token on ${process.platform}`);
  assert.equal(processStartTime(process.pid), first);
});
