// broker.json is DURABLE state — it lives in the plugin's state directory and
// outlives reboots. The pid in it is what SessionEnd and the next
// ensureBrokerSession hand to terminateProcessTree, which on POSIX signals a
// process GROUP (the broker is spawned detached, so it is a group leader, so the
// group signal is real). After a reboot that number belongs to somebody else,
// the endpoint check fails on the very first invocation, and teardown SIGTERMs a
// stranger's process tree.
//
// So: the record carries the broker's process start time, and teardown signals
// only a pid it can PROVE is still that broker. Anything else is just a stale
// file to delete.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import test from "node:test";

import { makeTempDir } from "./helpers.mjs";
import {
  ensureBrokerSession,
  loadBrokerSession,
  saveBrokerSession,
  teardownBrokerSession
} from "../../skills/codex-companion/runtime/scripts/lib/broker-lifecycle.mjs";
import { processStartTime } from "../../skills/codex-companion/runtime/scripts/lib/pid.mjs";

// A broker script that exits at once: the endpoint never opens, so
// ensureBrokerSession takes its "could not start" path and returns null. That
// keeps the test on the teardown code and off a real app-server.
function deadBrokerScript() {
  const dir = makeTempDir("codex-brokerscript-");
  const scriptPath = path.join(dir, "instant-exit.mjs");
  fs.writeFileSync(scriptPath, "process.exit(0);\n", "utf8");
  return scriptPath;
}

function plantStaleSession(workspace, extra) {
  const sessionDir = makeTempDir("codex-brokersession-");
  const session = {
    endpoint: `unix:${path.join(sessionDir, "broker.sock")}`,
    pidFile: path.join(sessionDir, "broker.pid"),
    logFile: path.join(sessionDir, "broker.log"),
    sessionDir,
    ...extra
  };
  saveBrokerSession(workspace, session);
  return session;
}

function withPluginData(fn) {
  const previous = process.env.CLAUDE_PLUGIN_DATA;
  process.env.CLAUDE_PLUGIN_DATA = makeTempDir("codex-brokerdata-");
  try {
    return fn();
  } finally {
    if (previous == null) {
      delete process.env.CLAUDE_PLUGIN_DATA;
    } else {
      process.env.CLAUDE_PLUGIN_DATA = previous;
    }
  }
}

test("a broker record whose instance no longer matches is deleted, never signalled", async () => {
  await withPluginData(async () => {
    const workspace = makeTempDir("codex-brokerws-");
    // This process is alive and its pid is real — only the recorded start time
    // says the number belongs to a different process now. That is exactly the
    // post-reboot shape.
    const stale = plantStaleSession(workspace, { pid: process.pid, pidStart: "not-this-process" });
    const killed = [];

    const session = await ensureBrokerSession(workspace, {
      killProcess: (pid) => killed.push(pid),
      scriptPath: deadBrokerScript(),
      timeoutMs: 300
    });

    assert.equal(session, null, "the dead endpoint could not be replaced in this test");
    assert.ok(!killed.includes(stale.pid), `a mismatched instance must never be signalled (killed ${killed})`);
    assert.equal(loadBrokerSession(workspace), null, "…the stale record is simply gone");
  });
});

test("a broker record with no instance stamp at all is deleted, never signalled", async () => {
  await withPluginData(async () => {
    const workspace = makeTempDir("codex-brokerws-");
    // Written before stamps existed. Nothing about it can be verified, and an
    // unverifiable group-kill is the thing being prevented.
    const stale = plantStaleSession(workspace, { pid: process.pid });
    const killed = [];

    await ensureBrokerSession(workspace, {
      killProcess: (pid) => killed.push(pid),
      scriptPath: deadBrokerScript(),
      timeoutMs: 300
    });

    assert.ok(!killed.includes(stale.pid), `an unverifiable instance must never be signalled (killed ${killed})`);
    assert.equal(loadBrokerSession(workspace), null);
  });
});

// The gate has to still let the real case through, or it is just a disabled
// teardown.
test("a broker record that still names its own process is torn down", () => {
  const sessionDir = makeTempDir("codex-brokersession-");
  const killed = [];

  teardownBrokerSession({
    endpoint: null,
    pidFile: path.join(sessionDir, "broker.pid"),
    logFile: path.join(sessionDir, "broker.log"),
    sessionDir,
    pid: process.pid,
    pidStart: processStartTime(process.pid),
    killProcess: (pid) => killed.push(pid)
  });

  assert.deepEqual(killed, [process.pid], "a verified instance is still signalled");
});

// The gap a mismatch cannot expose: a stored stamp that is genuine, a pid that
// answers signal 0, and a CURRENT start time that cannot be read right now.
// Liveness answers "alive" there deliberately — ignorance must never cost a live
// process its lock or its lease — but teardown SIGNALS, and terminateProcessTree
// signals a whole process GROUP. If the durable broker pid has since been
// reused, that same ignorance is what authorizes killing a stranger's tree.
// `platform: "win32"` is how this suite says "no start time is readable here"
// (pid.test.mjs uses it for exactly that).
test("a broker record whose current instance cannot be read is deleted, never signalled", () => {
  const sessionDir = makeTempDir("codex-brokersession-");
  const pidFile = path.join(sessionDir, "broker.pid");
  const logFile = path.join(sessionDir, "broker.log");
  fs.writeFileSync(pidFile, `${process.pid}\n`, "utf8");
  fs.writeFileSync(logFile, "", "utf8");
  const killed = [];

  teardownBrokerSession({
    endpoint: null,
    pidFile,
    logFile,
    sessionDir,
    pid: process.pid,
    pidStart: processStartTime(process.pid),
    killProcess: (pid) => killed.push(pid),
    pidOptions: { platform: "win32" }
  });

  assert.deepEqual(killed, [], "an unreadable current instance is unprovable, and unprovable is never signalled");
  assert.equal(fs.existsSync(pidFile), false, "…the record is still torn down, it is just never signalled");
  assert.equal(fs.existsSync(logFile), false);
});

test("a live broker's record carries the instance that answers for its pid", async () => {
  await withPluginData(async () => {
    const workspace = makeTempDir("codex-brokerws-");
    // A broker that opens its endpoint and stays up long enough to be recorded.
    const dir = makeTempDir("codex-brokerscript-");
    const scriptPath = path.join(dir, "listen.mjs");
    fs.writeFileSync(
      scriptPath,
      [
        "import net from 'node:net';",
        "const endpoint = process.argv[process.argv.indexOf('--endpoint') + 1];",
        "net.createServer(() => {}).listen(endpoint.slice('unix:'.length));",
        "setTimeout(() => process.exit(0), 5000);"
      ].join("\n"),
      "utf8"
    );

    const session = await ensureBrokerSession(workspace, { scriptPath, timeoutMs: 3000 });
    assert.ok(session, "the fake broker should have come up");
    try {
      assert.equal(typeof session.pid, "number");
      assert.equal(session.pidStart, processStartTime(session.pid), "the record names the instance, not just the number");
      assert.equal(loadBrokerSession(workspace).pidStart, session.pidStart);
    } finally {
      try {
        process.kill(session.pid, "SIGKILL");
      } catch {
        /* already gone */
      }
    }
  });
});
