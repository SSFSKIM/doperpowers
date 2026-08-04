// The connect layer: a worker hands runAppServerTurn/runAppServerReview its own
// app-server (per-worker `-c` config overrides, its own pid) instead of sharing
// the session broker. Two things must hold at once:
//   WITH connect    → the spawned `codex` argv carries the overrides, in order,
//                     and onSpawn fires exactly once with that process's pid.
//   WITHOUT connect → byte-identical to today: argv is ["app-server"], the
//                     broker path (and its documented direct fallback) is used.
// Everything is asserted against the mock app-server's own records
// (spawn-<pid>.json argv, turns.jsonl), not against the runtime's return value.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { initGitRepo, makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MOCK_BIN_DIR = path.join(HERE, "mock");

const scratch = makeTempDir("codex-connect-");
const mockDir = path.join(scratch, "mockstate");
fs.mkdirSync(mockDir, { recursive: true });
fs.writeFileSync(
  path.join(mockDir, "scenario.json"),
  JSON.stringify({
    turns: [
      { finalMessage: "connect-lane answer" },
      { finalMessage: "broker-lane answer" },
      { reviewText: "# Mock Review\n\nlane split" }
    ]
  })
);

process.env.CODEX_MOCK_DIR = mockDir;
process.env.PATH = `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const repo = path.join(scratch, "repo");
fs.mkdirSync(repo, { recursive: true });
initGitRepo(repo);
fs.writeFileSync(path.join(repo, "tracked.txt"), "base\n");
run("git", ["add", "."], { cwd: repo });
run("git", ["commit", "-m", "base"], { cwd: repo });
fs.writeFileSync(path.join(repo, "dirty.txt"), "uncommitted\n");

// Imported after the mock is on PATH: the runtime probes `codex --version` at
// call time, but the import order keeps the setup honest either way.
const { resolveReviewTarget, runAppServerReview, runAppServerTurn } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/codex.mjs"
);

const spawnRecord = (pid) => JSON.parse(fs.readFileSync(path.join(mockDir, `spawn-${pid}.json`), "utf8"));
const spawnedPids = () =>
  fs
    .readdirSync(mockDir)
    .filter((name) => name.startsWith("spawn-"))
    .map((name) => Number(name.slice("spawn-".length, -".json".length)));
const turnRequests = () =>
  fs
    .readFileSync(path.join(mockDir, "turns.jsonl"), "utf8")
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));

// --- (a)(b)(c) with connect --------------------------------------------------
const seen = [];
const overrides = ["model_reasoning_effort=xhigh", "developer_instructions=lens text"];
const turn = await runAppServerTurn(repo, {
  prompt: "hi",
  connect: {
    disableBroker: true,
    configOverrides: overrides,
    onSpawn: (pid) => seen.push(pid)
  }
});

assert.equal(turn.finalMessage, "connect-lane answer", "the connect lane still returns the scenario's final message");
const connectPids = spawnedPids();
assert.equal(connectPids.length, 1, "the connect lane spawns exactly one app-server");
assert.deepEqual(
  spawnRecord(connectPids[0]).argv,
  ["-c", "model_reasoning_effort=xhigh", "-c", "developer_instructions=lens text", "app-server"],
  "each override becomes its own -c pair, in caller order, before the app-server subcommand"
);
assert.equal(seen.length, 1, `onSpawn must fire exactly once per connect turn (fired ${seen.length}x)`);
assert.equal(seen[0], connectPids[0], "onSpawn reports the pid of the process that wrote the spawn record");
assert.equal(spawnRecord(seen[0]).cwd, fs.realpathSync(repo), "the connect lane spawns in the caller's cwd");

// --- (d) without connect: unchanged --------------------------------------------
// Production's no-broker fallback: an endpoint is advertised, the broker is not
// actually there, withAppServer retries direct. Same shape as a session whose
// broker died — and the leg that proves connect changed nothing for it.
process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT = "unix:/nonexistent/codex-broker.sock";
const before = new Set(spawnedPids());
const plain = await runAppServerTurn(repo, { prompt: "hi again" });
assert.equal(plain.finalMessage, "broker-lane answer", "the no-connect lane still completes its turn");
assert.equal(seen.length, 1, "the no-connect lane must not reach the caller's onSpawn");
const plainPids = spawnedPids().filter((pid) => !before.has(pid));
assert.equal(plainPids.length, 1, "the no-connect lane spawns exactly one app-server");
assert.deepEqual(spawnRecord(plainPids[0]).argv, ["app-server"], "absent connect, argv is untouched");

// --- review/start carries the resolved target ---------------------------------
// A review that silently reviews the wrong thing is the expensive failure: it
// returns a clean-looking report about code nobody asked about. Pin the exact
// wire object, resolved the same way the /codex:review verb resolves it.
assert.deepEqual(
  resolveReviewTarget(repo, {}),
  { type: "uncommittedChanges" },
  "auto scope on a dirty tree reviews the working tree"
);
assert.deepEqual(
  resolveReviewTarget(repo, { scope: "working-tree" }),
  { type: "uncommittedChanges" },
  "explicit working-tree scope reviews the working tree"
);
assert.deepEqual(
  resolveReviewTarget(repo, { base: "main" }),
  { type: "baseBranch", branch: "main" },
  "an explicit base wins over the dirty working tree"
);

const reviewTarget = resolveReviewTarget(repo, { base: "main" });
const review = await runAppServerReview(repo, {
  target: reviewTarget,
  connect: { disableBroker: true, configOverrides: ["model_reasoning_effort=xhigh"], onSpawn: (pid) => seen.push(pid) }
});
assert.equal(review.reviewText, "# Mock Review\n\nlane split", "the connect lane returns the review text");
assert.equal(seen.length, 2, "the review lane fires onSpawn for its own app-server");

const requests = turnRequests();
const reviewRequest = requests.at(-1);
assert.equal(reviewRequest.method, "review/start", "the review lane sends review/start");
assert.deepEqual(
  reviewRequest.params.target,
  { type: "baseBranch", branch: "main" },
  "review/start carries exactly the resolved target — not a default, not the working tree"
);
assert.equal(reviewRequest.pid, seen[1], "the review ran on the app-server this worker spawned");
assert.deepEqual(
  spawnRecord(seen[1]).argv,
  ["-c", "model_reasoning_effort=xhigh", "app-server"],
  "the review lane's overrides reach its own app-server"
);

// --- a failed setup leaves no app-server behind --------------------------------
//
// connect() spawns the process and THEN initializes it. If anything between
// those two points throws — the caller's onSpawn, a rejected initialize — the
// caller never receives a client, so its own `finally` has nothing to close: the
// app-server stays alive for the rest of the session, holding a model connection
// nobody is reading. Whoever spawned it closes it.
const failing = [];
await assert.rejects(
  runAppServerTurn(repo, {
    prompt: "hi",
    connect: {
      disableBroker: true,
      onSpawn: (pid) => {
        failing.push(pid);
        throw new Error("setup exploded");
      }
    }
  }),
  /setup exploded/,
  "the setup failure still reaches the caller"
);
assert.equal(failing.length, 1, "the app-server was spawned before the failure");
const orphanDeadline = Date.now() + 5000;
const gone = (pid) => {
  try {
    process.kill(pid, 0);
    return false;
  } catch (error) {
    return error.code === "ESRCH";
  }
};
while (!gone(failing[0]) && Date.now() < orphanDeadline) {
  await new Promise((resolve) => setTimeout(resolve, 50));
}
assert.equal(gone(failing[0]), true, "…and it was closed rather than left running");

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-connect-overrides: ok");
