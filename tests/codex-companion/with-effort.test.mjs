import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { initGitRepo, makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WRAPPER = path.resolve(HERE, "../../skills/codex-companion/scripts/with-effort.mjs");
const MOCK_BIN_DIR = path.join(HERE, "mock");

test("with-effort routes Luna at max through the task app-server", (t) => {
  const scratch = makeTempDir("codex-with-effort-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));

  const mockDir = path.join(scratch, "mockstate");
  const dataDir = path.join(scratch, "data");
  const repo = path.join(scratch, "repo");
  fs.mkdirSync(mockDir, { recursive: true });
  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(repo, { recursive: true });
  fs.writeFileSync(
    path.join(mockDir, "scenario.json"),
    JSON.stringify({ turns: [{ finalMessage: "tier-three-ok" }] })
  );
  initGitRepo(repo);

  const env = {
    ...process.env,
    PATH: `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`,
    CODEX_MOCK_DIR: mockDir,
    CLAUDE_PLUGIN_DATA: dataDir,
    CODEX_COMPANION_SESSION_ID: "with-effort-test"
  };
  delete env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

  const result = run(
    "node",
    [
      WRAPPER,
      "--effort",
      "max",
      "--",
      "task",
      "--model",
      "gpt-5.6-luna",
      "--",
      "process the mechanical fanout"
    ],
    { cwd: repo, env }
  );

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /tier-three-ok/);

  const spawnFiles = fs.readdirSync(mockDir).filter((name) => name.startsWith("spawn-"));
  assert.equal(spawnFiles.length, 1);
  const spawn = JSON.parse(fs.readFileSync(path.join(mockDir, spawnFiles[0]), "utf8"));
  assert.deepEqual(spawn.argv, ["-c", "model_reasoning_effort=max", "app-server"]);

  const thread = JSON.parse(fs.readFileSync(path.join(mockDir, "threads.jsonl"), "utf8").trim());
  assert.equal(thread.params.model, "gpt-5.6-luna");
});
