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

function startBroker(idleTimeoutMs) {
  const binDir = makeTempDir();
  installFakeCodex(binDir);
  const workspace = makeTempDir();
  initGitRepo(workspace);
  const sessionDir = makeTempDir();
  const endpoint = createBrokerEndpoint(sessionDir);
  const pidFile = path.join(sessionDir, "broker.pid");
  const logFile = path.join(sessionDir, "broker.log");
  const env = buildEnv(binDir);
  if (idleTimeoutMs !== undefined) {
    env.CODEX_COMPANION_BROKER_IDLE_TIMEOUT_MS = String(idleTimeoutMs);
  }
  const child = spawnBrokerProcess({ scriptPath: BROKER_SCRIPT, cwd: workspace, endpoint, pidFile, logFile, env });
  return { pid: child.pid, endpoint, pidFile, logFile };
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
