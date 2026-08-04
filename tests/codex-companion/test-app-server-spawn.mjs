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

const { appServerSpawnOptions, resolveCodexSpawnTarget } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/app-server.mjs"
);

// --- no platform gets a shell ------------------------------------------------
for (const platform of ["win32", "darwin", "linux"]) {
  const options = appServerSpawnOptions({ cwd: scratch, env: process.env, platform });
  assert.ok(!options.shell, `platform ${platform} must not spawn codex through a shell (got ${JSON.stringify(options.shell)})`);
  assert.equal(options.cwd, scratch);
  assert.equal(options.windowsHide, true);
}

// --- win32: an npm .cmd shim is REFUSED, never routed through cmd.exe ---------
//
// Node >= 18.20 refuses to spawn a .cmd without a shell (EINVAL), and cmd.exe is
// the one interpreter that would take it: but cmd.exe re-parses its own command
// line, so `&`, `|` and `%VAR%` inside the lens become command separators and
// variable expansions no argv-element discipline can prevent. There is no safe
// way to reach the shim, so the shim is not reached at all.
const winArgs = ["-c", "developer_instructions=Review $(whoami) `id` && echo pwned", "app-server"];

for (const shim of ["C:\\Users\\dev\\AppData\\Roaming\\npm\\codex.cmd", "C:\\tools\\codex.BAT"]) {
  assert.throws(
    () => resolveCodexSpawnTarget({ args: winArgs, platform: "win32", which: () => shim }),
    /native codex binary/i,
    `the ${path.extname(shim)} shim must be refused, not interpreted`
  );
}

const viaExe = resolveCodexSpawnTarget({
  args: winArgs,
  platform: "win32",
  which: () => "C:\\Program Files\\codex\\codex.exe"
});
assert.equal(viaExe.command, "C:\\Program Files\\codex\\codex.exe", "a real executable needs no interpreter");
assert.deepEqual(viaExe.args, winArgs);

const viaScript = resolveCodexSpawnTarget({
  args: winArgs,
  platform: "win32",
  which: () => "C:\\Users\\dev\\AppData\\Roaming\\npm\\node_modules\\codex\\bin\\codex.js"
});
assert.equal(viaScript.command, process.execPath, "a .js entry point is run by node itself");
assert.deepEqual(viaScript.args, ["C:\\Users\\dev\\AppData\\Roaming\\npm\\node_modules\\codex\\bin\\codex.js", ...winArgs]);

const unresolvable = resolveCodexSpawnTarget({ args: winArgs, platform: "win32", which: () => null });
assert.equal(unresolvable.command, "codex", "an unresolvable name falls back to the plain spawn and its error");
assert.deepEqual(unresolvable.args, winArgs);

for (const platform of ["darwin", "linux"]) {
  const target = resolveCodexSpawnTarget({
    args: winArgs,
    platform,
    which: () => {
      throw new Error(`no resolution may be attempted on ${platform}`);
    }
  });
  assert.equal(target.command, "codex", `${platform} spawns codex directly, unchanged`);
  assert.deepEqual(target.args, winArgs);
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
