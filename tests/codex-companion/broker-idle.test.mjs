// A broker is workspace-scoped and spawned detached, so a session that dies
// mid-run — or a review worktree that gets deleted — leaves a live broker +
// codex app-server pair with nobody left who can reach its workspace's
// broker.json (19h55m pairs observed live, dp#56). No sweep can safely reap
// those from the outside: their sockets are healthy, and whether anyone still
// wants them is knowledge only the broker itself has — a client holds its
// socket open for as long as it is being served. So the broker reaps itself:
// no client connection for the idle window ⇒ clean shutdown, taking the
// app-server child with it (appClient.close) and unlinking socket + pid file
// so the next ensureBrokerSession respawns from a clean probe failure.
import assert from "node:assert/strict";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import process from "node:process";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { buildEnv, installFakeCodex } from "./fake-codex-fixture.mjs";
import { initGitRepo, makeTempDir } from "./helpers.mjs";
import {
  loadBrokerSession,
  saveBrokerSession,
  spawnBrokerProcess,
  waitForBrokerEndpoint
} from "../../skills/codex-companion/runtime/scripts/lib/broker-lifecycle.mjs";
import { createBrokerEndpoint, parseBrokerEndpoint } from "../../skills/codex-companion/runtime/scripts/lib/broker-endpoint.mjs";

const BROKER_SCRIPT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../skills/codex-companion/runtime/scripts/app-server-broker.mjs"
);

function processAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code !== "ESRCH";
  }
}

async function waitFor(predicate, { timeoutMs = 8000, intervalMs = 50 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await predicate()) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return false;
}

// `beforeSpawn` runs once the workspace and endpoint are chosen but before the
// process exists, so a test that plants a broker.json cannot lose a race with
// the reap it is about to observe.
function startBroker(idleTimeoutMs, { env: envOverrides = {}, beforeSpawn = null } = {}) {
  const binDir = makeTempDir();
  installFakeCodex(binDir);
  const workspace = makeTempDir();
  initGitRepo(workspace);
  const sessionDir = makeTempDir();
  const endpoint = createBrokerEndpoint(sessionDir);
  const pidFile = path.join(sessionDir, "broker.pid");
  const logFile = path.join(sessionDir, "broker.log");
  const env = { ...buildEnv(binDir), ...envOverrides };
  if (idleTimeoutMs !== undefined) {
    env.CODEX_COMPANION_BROKER_IDLE_TIMEOUT_MS = String(idleTimeoutMs);
  }
  if (beforeSpawn) {
    beforeSpawn({ workspace, endpoint, sessionDir, pidFile, logFile });
  }
  const child = spawnBrokerProcess({ scriptPath: BROKER_SCRIPT, cwd: workspace, endpoint, pidFile, logFile, env });
  return { pid: child.pid, endpoint, pidFile, logFile, workspace, sessionDir };
}

// The state root has to be the same one on both sides: this process resolves it
// from its own environment (save/load), the broker from the env it was spawned
// with. The await matters — restoring on the way out of a synchronous call would
// hand the assertions back their original root.
async function withPluginData(fn) {
  const previous = process.env.CLAUDE_PLUGIN_DATA;
  const dataDir = makeTempDir("codex-brokerdata-");
  process.env.CLAUDE_PLUGIN_DATA = dataDir;
  try {
    return await fn(dataDir);
  } finally {
    if (previous == null) {
      delete process.env.CLAUDE_PLUGIN_DATA;
    } else {
      process.env.CLAUDE_PLUGIN_DATA = previous;
    }
  }
}

function stopBroker(pid) {
  if (pid && processAlive(pid)) {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // already gone
    }
  }
}

test("an idle broker reaps itself: process exits, socket and pid file are gone", async () => {
  const broker = startBroker(500);
  try {
    assert.ok(await waitForBrokerEndpoint(broker.endpoint, 8000), "broker never came up");
    const exited = await waitFor(() => !processAlive(broker.pid));
    assert.ok(exited, "broker did not exit after its idle window");
    assert.ok(!fs.existsSync(parseBrokerEndpoint(broker.endpoint).path), "socket file survived the idle shutdown");
    assert.ok(!fs.existsSync(broker.pidFile), "pid file survived the idle shutdown");
  } finally {
    stopBroker(broker.pid);
  }
});

test("a held client connection is service, not idleness — the window opens only when it closes", async () => {
  const broker = startBroker(700);
  let socket = null;
  try {
    assert.ok(await waitForBrokerEndpoint(broker.endpoint, 8000), "broker never came up");
    socket = net.createConnection({ path: parseBrokerEndpoint(broker.endpoint).path });
    await new Promise((resolve, reject) => {
      socket.on("connect", resolve);
      socket.on("error", reject);
    });

    // Well past the idle window with the connection held open: still serving.
    await new Promise((resolve) => setTimeout(resolve, 1600));
    assert.ok(processAlive(broker.pid), "broker died while a client held its connection");

    socket.end();
    socket = null;
    const exited = await waitFor(() => !processAlive(broker.pid));
    assert.ok(exited, "broker did not exit after its last client left");
  } finally {
    if (socket) {
      socket.destroy();
    }
    stopBroker(broker.pid);
  }
});

// broker.json is read WITHOUT a probe: `status` calls a recorded endpoint a live
// shared session, and `setup`'s auth path dials it and blames auth when it is
// dead. A reap that leaves the record behind therefore lies about the runtime
// until some later work verb sweeps it.
test("a reaped broker deletes the workspace record that names it", async () => {
  await withPluginData(async (pluginData) => {
    const broker = startBroker(500, {
      env: { CLAUDE_PLUGIN_DATA: pluginData },
      beforeSpawn: ({ workspace, endpoint, sessionDir, pidFile, logFile }) =>
        saveBrokerSession(workspace, { endpoint, pidFile, logFile, sessionDir, pid: null, pidStart: null })
    });
    try {
      assert.ok(await waitForBrokerEndpoint(broker.endpoint, 8000), "broker never came up");
      const exited = await waitFor(() => !processAlive(broker.pid));
      assert.ok(exited, "broker did not exit after its idle window");
      assert.equal(loadBrokerSession(broker.workspace), null, "the reap left a record pointing at a dead broker");
    } finally {
      stopBroker(broker.pid);
    }
  });
});

// ensureBrokerSession can replace the record before a doomed broker finishes
// exiting; deleting a successor's record would strand a live broker.
test("a record naming a different endpoint survives the reap", async () => {
  await withPluginData(async (pluginData) => {
    let successor = null;
    const broker = startBroker(500, {
      env: { CLAUDE_PLUGIN_DATA: pluginData },
      beforeSpawn: ({ workspace }) => {
        successor = {
          endpoint: `unix:${path.join(makeTempDir(), "broker.sock")}`,
          pidFile: null,
          logFile: null,
          sessionDir: null,
          pid: null,
          pidStart: null
        };
        saveBrokerSession(workspace, successor);
      }
    });
    try {
      assert.ok(await waitForBrokerEndpoint(broker.endpoint, 8000), "broker never came up");
      const exited = await waitFor(() => !processAlive(broker.pid));
      assert.ok(exited, "broker did not exit after its idle window");
      assert.deepEqual(
        loadBrokerSession(broker.workspace),
        successor,
        "the reap deleted a record that belonged to another broker"
      );
    } finally {
      stopBroker(broker.pid);
    }
  });
});

test("idle timeout 0 disables the reaper", async () => {
  const broker = startBroker(0);
  try {
    assert.ok(await waitForBrokerEndpoint(broker.endpoint, 8000), "broker never came up");
    await new Promise((resolve) => setTimeout(resolve, 1200));
    assert.ok(processAlive(broker.pid), "a disabled reaper must never fire");
  } finally {
    stopBroker(broker.pid);
  }
});
