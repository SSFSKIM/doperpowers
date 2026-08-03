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
  pidInstanceVerified,
  processStartTime
} from "../../skills/codex-companion/runtime/scripts/lib/pid.mjs";

const PID_SOURCE = new URL(
  "../../skills/codex-companion/runtime/scripts/lib/pid.mjs",
  import.meta.url
);

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

function fakeProc(pid, comm, starttime, bootId = null) {
  const root = makeTempDir("codex-fakeproc-");
  fs.mkdirSync(path.join(root, String(pid)));
  fs.writeFileSync(path.join(root, String(pid), "stat"), procStatLine(pid, comm, starttime), "utf8");
  if (bootId) {
    fs.mkdirSync(path.join(root, "sys", "kernel", "random"), { recursive: true });
    fs.writeFileSync(path.join(root, "sys", "kernel", "random", "boot_id"), `${bootId}\n`, "utf8");
  }
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

// The state lock's retry loop re-inspects its holder every ~15ms and cannot
// afford a syscall per attempt, so it (and only it) may ask for a cached answer.
// Nothing that SIGNALs or STAMPS may: a pid that exits and is reused inside the
// window would otherwise be authorized against its predecessor's token.
test("start-time reads are cached only when the caller asks, and failures are never cached", async () => {
  const root = fakeProc(4244, "codex", 111);
  const options = { platform: "linux", procRoot: root, cache: true };

  assert.equal(processStartTime(4244, options), "111");
  fs.writeFileSync(path.join(root, "4244", "stat"), procStatLine(4244, "codex", 222), "utf8");
  assert.equal(processStartTime(4244, options), "111", "a repeat read inside the window is served from the cache");
  assert.equal(
    processStartTime(4244, { platform: "linux", procRoot: root }),
    "222",
    "an uncached read — every kill decision and every spawn stamp — sees the pid as it is NOW"
  );

  await new Promise((resolve) => setTimeout(resolve, 300));
  assert.equal(processStartTime(4244, options), "222", "and the window is short");

  // A miss is never cached: the pid appearing a moment later must be readable.
  const late = makeTempDir("codex-lateproc-");
  const lateOptions = { platform: "linux", procRoot: late, cache: true };
  assert.equal(processStartTime(4245, lateOptions), null);
  fs.mkdirSync(path.join(late, "4245"));
  fs.writeFileSync(path.join(late, "4245", "stat"), procStatLine(4245, "codex", 333), "utf8");
  assert.equal(processStartTime(4245, lateOptions), "333", "a failed read left nothing behind to replay");
});

// Jiffies-since-boot restart at 0 on every boot, so a pre-reboot record can match
// the same pid at the same tick after one — the exact aliasing a start time is
// supposed to rule out. The kernel's boot id is the discriminator.
test("the linux token folds in the boot id, so a reboot can never alias", () => {
  const root = fakeProc(4246, "codex", 111, "boot-A");
  const token = processStartTime(4246, { platform: "linux", procRoot: root });
  assert.equal(token, "boot-A@111", "the token names the boot it was taken in");

  const rebooted = fakeProc(4246, "codex", 111, "boot-B");
  assert.notEqual(
    processStartTime(4246, { platform: "linux", procRoot: rebooted }),
    token,
    "the same pid at the same tick after a reboot is a DIFFERENT instance"
  );
});

test("a boot-id-less token still matches — the format upgrade must not read live processes as dead", () => {
  const root = fakeProc(process.pid, "node", 111, "boot-A");
  const options = { platform: "linux", procRoot: root };
  assert.equal(
    pidInstanceAlive(process.pid, "111", options),
    true,
    "a record written before the boot id was folded in is compared on what both formats share"
  );
  assert.equal(
    pidInstanceAlive(process.pid, "boot-Z@111", options),
    false,
    "…but two tokens that both name a boot are compared whole"
  );
});

// The kill-path rule, the same one teardownBrokerSession has always used: a
// record whose instance cannot be PROVEN is never signalled. An unstamped record
// (written before stamps existed, or on Windows, where no start time is
// readable) is a file to clean up, not a process to shoot at.
test("only a provable instance may be signalled", () => {
  const root = fakeProc(process.pid, "node", 111, "boot-A");
  const options = { platform: "linux", procRoot: root };

  assert.equal(pidInstanceVerified(process.pid, "boot-A@111", options), true, "our own stamped instance");
  assert.equal(pidInstanceVerified(process.pid, "boot-A@999", options), false, "a mismatched instance");
  assert.equal(pidInstanceVerified(process.pid, null, options), false, "an unstamped record proves nothing");
  assert.equal(
    pidInstanceVerified(process.pid, "boot-A@111", { platform: "win32" }),
    false,
    "a platform with no readable start time proves nothing either"
  );
  // Liveness keeps the opposite default: unverifiable means alive, so nobody
  // ever loses a lock, a lease or a run to an unexplained answer.
  assert.equal(pidInstanceAlive(process.pid, null), true);
});

// `file` reports pid.mjs as data and `git diff` as binary when the source
// carries raw NUL bytes, which hides every change to it from ordinary review.
test("the source stays text", () => {
  const source = fs.readFileSync(PID_SOURCE, "utf8");
  const nulAt = [...source].findIndex((ch) => ch.charCodeAt(0) === 0);
  assert.equal(nulAt, -1, "no raw NUL bytes in pid.mjs — escape them");
});

test("this platform can read its own start time, and it is stable across calls", () => {
  const first = processStartTime(process.pid);
  assert.ok(first, `no instance token on ${process.platform}`);
  assert.equal(processStartTime(process.pid), first);
});
