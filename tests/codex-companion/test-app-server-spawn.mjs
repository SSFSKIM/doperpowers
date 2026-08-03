// How the per-worker codex app-server is spawned.
//
// The config overrides a workflow worker passes are attacker-shaped data: a
// review lens is prose, written by whoever wrote the workflow script, and it is
// handed over as `developer_instructions=<lens>`. Spawning through a shell (as
// the win32 branch did) hands that prose to a command line — `$(…)`, backticks,
// `&&`, quotes, all interpreted before codex ever starts, which is either a
// startup failure or command execution outside the read-only Codex worker.
//
// No shell on any platform, and the argument reaches the process byte for byte.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { initGitRepo, makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCK_BIN_DIR = path.join(HERE, "mock");

const scratch = makeTempDir("codex-spawnopts-");
const mockDir = path.join(scratch, "mockstate");
fs.mkdirSync(mockDir, { recursive: true });
fs.writeFileSync(path.join(mockDir, "scenario.json"), JSON.stringify({ turns: [{ finalMessage: "ok" }] }));
process.env.CODEX_MOCK_DIR = mockDir;
process.env.PATH = `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const { appServerSpawnOptions } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/app-server.mjs"
);

// --- no platform gets a shell ------------------------------------------------
for (const platform of ["win32", "darwin", "linux"]) {
  const options = appServerSpawnOptions({ cwd: scratch, env: process.env, platform });
  assert.ok(!options.shell, `platform ${platform} must not spawn codex through a shell (got ${JSON.stringify(options.shell)})`);
  assert.equal(options.cwd, scratch);
  assert.equal(options.windowsHide, true);
}

// --- the lens reaches the process verbatim -----------------------------------
const repo = path.join(scratch, "repo");
fs.mkdirSync(repo, { recursive: true });
initGitRepo(repo);
fs.writeFileSync(path.join(repo, "tracked.txt"), "base\n");
run("git", ["add", "."], { cwd: repo });
run("git", ["commit", "-m", "base"], { cwd: repo });

const { runAppServerTurn } = await import("../../skills/codex-companion/runtime/scripts/lib/codex.mjs");

const canary = path.join(scratch, "canary");
const lens = `Review this. $(touch ${canary}) \`touch ${canary}\` && touch ${canary}; "quoted" 'single' %PATH%`;
let spawnedPid = null;
const turn = await runAppServerTurn(repo, {
  prompt: "hi",
  connect: {
    disableBroker: true,
    configOverrides: [`developer_instructions=${lens}`],
    onSpawn: (pid) => {
      spawnedPid = pid;
    }
  }
});

assert.equal(turn.finalMessage, "ok", "the turn still completes with a metacharacter-laden lens");
const spawnRecord = JSON.parse(fs.readFileSync(path.join(mockDir, `spawn-${spawnedPid}.json`), "utf8"));
assert.deepEqual(
  spawnRecord.argv,
  ["-c", `developer_instructions=${lens}`, "app-server"],
  "the lens arrives as one argument, unmangled and unexpanded"
);
assert.ok(!fs.existsSync(canary), "nothing in the lens may be executed");

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-app-server-spawn: ok");
