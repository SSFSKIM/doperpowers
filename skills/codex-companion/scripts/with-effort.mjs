#!/usr/bin/env node
// Runs a codex-companion verb against a codex app-server started with config
// overrides — the only way to choose reasoning effort for `review` /
// `adversarial-review`, whose app-server protocol has no effort field (effort
// is inherited from the app-server process's config). This is a call site,
// not a runtime patch: it serves a real unix socket and hands it to the
// runtime via CODEX_COMPANION_APP_SERVER_ENDPOINT, the env knob the runtime
// already honors. Each incoming connection gets its own
// `codex app-server -c key=value …` that dies with the connection, so
// nothing outlives this process.
//
// Usage:
//   node with-effort.mjs --effort <level> [-c key=value ...] -- <verb> [flags…]
//
// Example:
//   CLAUDE_PLUGIN_DATA=… node with-effort.mjs --effort medium -- review --base main

import net from "node:net";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { SANDBOX_FAILURE_MARKERS } from "../runtime/scripts/lib/sandbox.mjs";

const RUNTIME_ENTRY = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "runtime",
  "scripts",
  "codex-companion.mjs"
);

function usage(message) {
  console.error(message);
  console.error("Usage: with-effort.mjs --effort <level> [-c key=value ...] -- <verb> [flags…]");
  process.exit(2);
}

const overrides = [];
const argv = process.argv.slice(2);
let verbArgs = null;
for (let i = 0; i < argv.length; i++) {
  const arg = argv[i];
  if (arg === "--") {
    verbArgs = argv.slice(i + 1);
    break;
  }
  if (arg === "--effort") {
    const value = argv[++i];
    if (!value) usage("--effort requires a value.");
    overrides.push(`model_reasoning_effort=${value}`);
  } else if (arg === "-c" || arg === "--config") {
    const value = argv[++i];
    if (!value || !value.includes("=")) usage(`${arg} requires key=value.`);
    overrides.push(value);
  } else {
    usage(`Unknown argument before --: ${arg}`);
  }
}
if (overrides.length === 0) usage("Nothing to override — pass --effort or -c.");
if (!verbArgs || verbArgs.length === 0) usage("Missing verb: put the codex-companion arguments after --.");

const codexArgs = overrides.flatMap((kv) => ["-c", kv]).concat("app-server");
const socketPath = path.join(os.tmpdir(), `codex-effort-${process.pid}.sock`);
fs.rmSync(socketPath, { force: true });

let connections = 0;
// The private app-server's stderr is the only trace of the observed fs-sandbox
// failure (bwrap RTM_NEWADDR: codex exits 0 and renders findings anyway — see
// runtime/scripts/lib/sandbox.mjs). The verb's own client never sees a socket
// server's stderr, so THIS process owns the fail-closed check on that channel:
// forward the stream unchanged, and remember any marker line.
let sandboxMarkerLine = null;
const server = net.createServer((conn) => {
  connections += 1;
  const child = spawn("codex", codexArgs, {
    cwd: process.cwd(),
    stdio: ["pipe", "pipe", "pipe"]
  });
  let pending = "";
  child.stderr.on("data", (chunk) => {
    process.stderr.write(chunk);
    pending += chunk.toString();
    const lines = pending.split("\n");
    pending = lines.pop();
    for (const line of lines) {
      if (sandboxMarkerLine === null && SANDBOX_FAILURE_MARKERS.test(line)) sandboxMarkerLine = line;
    }
  });
  conn.pipe(child.stdin);
  child.stdout.pipe(conn);
  conn.on("close", () => child.kill("SIGTERM"));
  conn.on("error", () => child.kill("SIGTERM"));
  child.on("exit", () => conn.destroy());
  child.on("error", (error) => {
    console.error(`with-effort: failed to spawn codex app-server: ${error.message}`);
    conn.destroy();
  });
});

server.listen(socketPath, () => {
  const verb = spawn(process.execPath, [RUNTIME_ENTRY, ...verbArgs], {
    stdio: "inherit",
    env: {
      ...process.env,
      CODEX_COMPANION_APP_SERVER_ENDPOINT: `unix:${socketPath}`
    }
  });
  verb.on("exit", (code, signal) => {
    if (connections === 0) {
      console.error(
        "with-effort: WARNING — the verb never connected to the override app-server; it may have run at the default effort."
      );
    }
    server.close();
    fs.rmSync(socketPath, { force: true });
    // Fail closed: a clean verb exit over a broken sandbox is the false-clean
    // incident shape. Under an OUTER codex sandbox (CODEX_SANDBOX) confinement
    // is expected and the degraded render is documented behavior.
    if (code === 0 && !signal && sandboxMarkerLine !== null && !process.env.CODEX_SANDBOX) {
      console.error(
        `with-effort: fs sandbox unavailable during the run: ${sandboxMarkerLine.trim()} — ` +
        "findings would be untrustworthy; treat as an engine failure"
      );
      process.exit(3);
    }
    process.exit(signal ? 1 : code ?? 1);
  });
});
