// One unparseable stdout line must not end a live turn.
//
// The app-server protocol is JSONL, but the process printing it is a CLI: a
// wrapper's banner, a deprecation warning, an unbuffered log line all land on
// the same stdout. Routing a parse error into the exit path (which is what the
// mid-turn-death fix made consequential) rejects every pending RPC and fails the
// turn while the server is alive and still streaming the answer.
//
// The banner here arrives BEFORE the turn's notifications, and the answer comes
// after a delay longer than the exit-drain window — so a client that treats the
// line as an exit has nothing left to salvage and fails the leaf.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { initGitRepo, makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCK_BIN_DIR = path.join(HERE, "mock");

const scratch = makeTempDir("codex-strayline-");
const mockDir = path.join(scratch, "mockstate");
const repo = path.join(scratch, "repo");
fs.mkdirSync(mockDir, { recursive: true });
fs.mkdirSync(repo, { recursive: true });
fs.writeFileSync(
  path.join(mockDir, "scenario.json"),
  JSON.stringify({
    turns: [
      {
        banner: "codex: a new version is available (2.0.0) — run `codex upgrade`",
        hangMs: 400,
        finalMessage: "answered anyway"
      }
    ]
  })
);
initGitRepo(repo);
fs.writeFileSync(path.join(repo, "tracked.txt"), "base\n");
run("git", ["add", "."], { cwd: repo });
run("git", ["commit", "-m", "base"], { cwd: repo });

process.env.CODEX_MOCK_DIR = mockDir;
process.env.PATH = `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const { runAppServerTurn } = await import("../../skills/codex-companion/runtime/scripts/lib/codex.mjs");

const turn = await runAppServerTurn(repo, {
  prompt: "hi",
  connect: { disableBroker: true }
});

assert.equal(turn.finalMessage, "answered anyway", "the turn completes across a stray stdout line");
assert.equal(turn.error, null, "…and the stray line is not reported as a failure");

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-stray-stdout-line: ok");
