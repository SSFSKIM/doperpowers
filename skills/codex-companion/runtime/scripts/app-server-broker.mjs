#!/usr/bin/env node

import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import process from "node:process";

import { parseArgs } from "./lib/args.mjs";
import { BROKER_BUSY_RPC_CODE, CodexAppServerClient } from "./lib/app-server.mjs";
import { parseBrokerEndpoint } from "./lib/broker-endpoint.mjs";
import { clearBrokerSession, loadBrokerSession } from "./lib/broker-lifecycle.mjs";

const STREAMING_METHODS = new Set(["turn/start", "review/start", "thread/compact/start"]);

function buildStreamThreadIds(method, params, result) {
  const threadIds = new Set();
  if (params?.threadId) {
    threadIds.add(params.threadId);
  }
  if (method === "review/start" && result?.reviewThreadId) {
    threadIds.add(result.reviewThreadId);
  }
  return threadIds;
}

function buildJsonRpcError(code, message, data) {
  return data === undefined ? { code, message } : { code, message, data };
}

function send(socket, message) {
  if (socket.destroyed) {
    return;
  }
  socket.write(`${JSON.stringify(message)}\n`);
}

function isInterruptRequest(message) {
  return message?.method === "turn/interrupt";
}

// The broker is workspace-scoped and spawned detached, so a session that dies
// mid-run — or a review worktree that gets deleted — orphans a live broker +
// codex app-server pair forever: its socket stays healthy, and nobody who could
// reach its workspace's broker.json exists anymore (19h55m pairs observed,
// dp#56). Whether anyone still wants this broker is knowledge only it has — a
// client holds its connection open for as long as it is being served, and the
// OS closes that socket the instant the client dies. So: no client connection
// for this long ⇒ shut down cleanly, taking the app-server child along.
const DEFAULT_IDLE_TIMEOUT_MS = 30 * 60 * 1000;

// Unparseable input falls back to the default rather than disabling — a typo
// must not silently resurrect the leak. Only an explicit 0 (or negative)
// switches the reaper off.
function resolveIdleTimeoutMs(env) {
  const raw = env.CODEX_COMPANION_BROKER_IDLE_TIMEOUT_MS;
  if (raw === undefined || raw === "") {
    return DEFAULT_IDLE_TIMEOUT_MS;
  }
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    return DEFAULT_IDLE_TIMEOUT_MS;
  }
  return value > 0 ? value : 0;
}

function writePidFile(pidFile) {
  if (!pidFile) {
    return;
  }
  fs.mkdirSync(path.dirname(pidFile), { recursive: true });
  fs.writeFileSync(pidFile, `${process.pid}\n`, "utf8");
}

async function main() {
  const [subcommand, ...argv] = process.argv.slice(2);
  if (subcommand !== "serve") {
    throw new Error("Usage: node scripts/app-server-broker.mjs serve --endpoint <value> [--cwd <path>] [--pid-file <path>]");
  }

  const { options } = parseArgs(argv, {
    valueOptions: ["cwd", "pid-file", "endpoint"]
  });

  if (!options.endpoint) {
    throw new Error("Missing required --endpoint.");
  }

  const cwd = options.cwd ? path.resolve(process.cwd(), options.cwd) : process.cwd();
  const endpoint = String(options.endpoint);
  const listenTarget = parseBrokerEndpoint(endpoint);
  const pidFile = options["pid-file"] ? path.resolve(options["pid-file"]) : null;
  writePidFile(pidFile);

  const idleTimeoutMs = resolveIdleTimeoutMs(process.env);
  const appClient = await CodexAppServerClient.connect(cwd, { disableBroker: true });
  let activeRequestSocket = null;
  let activeStreamSocket = null;
  let activeStreamThreadIds = null;
  const sockets = new Set();
  let shuttingDown = false;

  function clearSocketOwnership(socket) {
    if (activeRequestSocket === socket) {
      activeRequestSocket = null;
    }
    if (activeStreamSocket === socket) {
      activeStreamSocket = null;
      activeStreamThreadIds = null;
    }
  }

  function routeNotification(message) {
    const target = activeRequestSocket ?? activeStreamSocket;
    if (!target) {
      return;
    }
    send(target, message);
    if (message.method === "turn/completed" && activeStreamSocket === target) {
      const threadId = message.params?.threadId ?? null;
      if (!threadId || !activeStreamThreadIds || activeStreamThreadIds.has(threadId)) {
        activeStreamSocket = null;
        activeStreamThreadIds = null;
        if (activeRequestSocket === target) {
          activeRequestSocket = null;
        }
      }
    }
  }

  async function shutdown(server) {
    shuttingDown = true;
    for (const socket of sockets) {
      socket.end();
    }
    await appClient.close().catch(() => {});
    await new Promise((resolve) => server.close(resolve));
    if (listenTarget.kind === "unix" && fs.existsSync(listenTarget.path)) {
      fs.unlinkSync(listenTarget.path);
    }
    if (pidFile && fs.existsSync(pidFile)) {
      fs.unlinkSync(pidFile);
    }
    // The workspace's broker.json outlives the socket, and the readers that
    // matter never probe it: `status` calls it a live shared session on the
    // strength of the record alone, and `setup`'s auth path then dials the dead
    // endpoint and reports an auth failure — until some work verb's
    // ensureBrokerSession finally sweeps it. So a broker that reaps itself takes
    // its own record with it. Only its OWN: ensureBrokerSession may already have
    // replaced the record with a successor's, and deleting that would strand a
    // live broker. resolveStateDir reads CLAUDE_PLUGIN_DATA from the env we
    // inherited from the spawner, so this is the same file the spawner wrote.
    try {
      if (loadBrokerSession(cwd)?.endpoint === endpoint) {
        clearBrokerSession(cwd);
      }
    } catch {
      // The record is advisory; never let its cleanup break shutdown.
    }
  }

  appClient.setNotificationHandler(routeNotification);

  // Armed whenever the broker has no client connections (including from boot:
  // a broker whose spawner dies before ever connecting is the orphan case too).
  // The callback re-checks sockets.size — a connection can land after the timer
  // fires but before the callback runs, and that client is owed service.
  let idleTimer = null;
  function cancelIdleTimer() {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
  }
  function armIdleTimer(server) {
    if (!idleTimeoutMs) {
      return;
    }
    cancelIdleTimer();
    idleTimer = setTimeout(async () => {
      if (sockets.size > 0) {
        return;
      }
      await shutdown(server);
      process.exit(0);
    }, idleTimeoutMs);
  }

  const server = net.createServer((socket) => {
    // The listener keeps accepting until server.close() runs, which is several
    // awaits into shutdown() — so a client can land after the idle timer read
    // sockets.size as 0. That socket missed shutdown's end-loop, its requests
    // would reach an already-closing app client, and holding it open can stall
    // server.close indefinitely. Refuse it instead: the client sees a failed
    // probe, which ensureBrokerSession already answers by respawning.
    if (shuttingDown) {
      socket.destroy();
      return;
    }
    cancelIdleTimer();
    sockets.add(socket);
    socket.setEncoding("utf8");
    let buffer = "";

    socket.on("data", async (chunk) => {
      buffer += chunk;
      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex !== -1) {
        const line = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf("\n");

        if (!line.trim()) {
          continue;
        }

        let message;
        try {
          message = JSON.parse(line);
        } catch (error) {
          send(socket, {
            id: null,
            error: buildJsonRpcError(-32700, `Invalid JSON: ${error.message}`)
          });
          continue;
        }

        if (message.id !== undefined && message.method === "initialize") {
          send(socket, {
            id: message.id,
            result: {
              userAgent: "codex-companion-broker"
            }
          });
          continue;
        }

        if (message.method === "initialized" && message.id === undefined) {
          continue;
        }

        if (message.id !== undefined && message.method === "broker/shutdown") {
          send(socket, { id: message.id, result: {} });
          await shutdown(server);
          process.exit(0);
        }

        if (message.id === undefined) {
          continue;
        }

        const allowInterruptDuringActiveStream =
          isInterruptRequest(message) && activeStreamSocket && activeStreamSocket !== socket && !activeRequestSocket;

        if (
          ((activeRequestSocket && activeRequestSocket !== socket) || (activeStreamSocket && activeStreamSocket !== socket)) &&
          !allowInterruptDuringActiveStream
        ) {
          send(socket, {
            id: message.id,
            error: buildJsonRpcError(BROKER_BUSY_RPC_CODE, "Shared Codex broker is busy.")
          });
          continue;
        }

        if (allowInterruptDuringActiveStream) {
          try {
            const result = await appClient.request(message.method, message.params ?? {});
            send(socket, { id: message.id, result });
          } catch (error) {
            send(socket, {
              id: message.id,
              error: buildJsonRpcError(error.rpcCode ?? -32000, error.message)
            });
          }
          continue;
        }

        const isStreaming = STREAMING_METHODS.has(message.method);
        activeRequestSocket = socket;

        try {
          const result = await appClient.request(message.method, message.params ?? {});
          send(socket, { id: message.id, result });
          if (isStreaming) {
            activeStreamSocket = socket;
            activeStreamThreadIds = buildStreamThreadIds(message.method, message.params ?? {}, result);
          }
          if (activeRequestSocket === socket) {
            activeRequestSocket = null;
          }
        } catch (error) {
          send(socket, {
            id: message.id,
            error: buildJsonRpcError(error.rpcCode ?? -32000, error.message)
          });
          if (activeRequestSocket === socket) {
            activeRequestSocket = null;
          }
          if (activeStreamSocket === socket && !isStreaming) {
            activeStreamSocket = null;
          }
        }
      }
    });

    socket.on("close", () => {
      sockets.delete(socket);
      clearSocketOwnership(socket);
      if (sockets.size === 0) {
        armIdleTimer(server);
      }
    });

    socket.on("error", () => {
      sockets.delete(socket);
      clearSocketOwnership(socket);
      if (sockets.size === 0) {
        armIdleTimer(server);
      }
    });
  });

  process.on("SIGTERM", async () => {
    await shutdown(server);
    process.exit(0);
  });

  process.on("SIGINT", async () => {
    await shutdown(server);
    process.exit(0);
  });

  server.listen(listenTarget.path);
  armIdleTimer(server);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
