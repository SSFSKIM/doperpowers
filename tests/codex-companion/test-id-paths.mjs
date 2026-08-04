// An id that becomes a path. Run ids and job ids are joined into directory and
// file paths (the run directory, the per-job record, the job log), so an id that
// is not a bare path segment escapes the directory it is meant to name.
//
// The one that costs real state: `--resume ../state` resolves the run directory
// to the plugin's state root — which exists, so the "nothing to resume" guard
// passes — and then resolveJobFile normalizes `jobs/../state.json` onto the
// workspace LEDGER. lifecycle.register replaces that ledger with a single job
// record, and the upsert behind it rebuilds a ledger with every other job and
// the whole config gone.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RUNTIME = path.join(HERE, "..", "..", "skills", "codex-companion", "runtime", "scripts", "codex-companion.mjs");
const MOCK_BIN_DIR = path.join(HERE, "mock");
const FIXTURES = path.join(HERE, "fixtures");

const scratch = makeTempDir("codex-idpath-");
const dataDir = path.join(scratch, "data");
const mockDir = path.join(scratch, "mockstate");
fs.mkdirSync(dataDir, { recursive: true });
fs.mkdirSync(mockDir, { recursive: true });
fs.writeFileSync(path.join(mockDir, "scenario.json"), JSON.stringify({ turns: [{ finalMessage: "x" }] }));

process.env.CLAUDE_PLUGIN_DATA = dataDir;
process.env.CODEX_MOCK_DIR = mockDir;
process.env.PATH = `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const { resolveJobFile, resolveJobLogFile, resolveStateFile, resolveWorkflowRunDir, setConfig, upsertJob } =
  await import("../../skills/codex-companion/runtime/scripts/lib/state.mjs");

// --- unit: every id→path entry point refuses a non-segment -------------------
const ESCAPES = ["../state", "..", ".", "", "a/b", "/abs", "nested/../../x"];
for (const bad of ESCAPES) {
  for (const [name, resolve] of [
    ["resolveWorkflowRunDir", () => resolveWorkflowRunDir(bad)],
    ["resolveJobFile", () => resolveJobFile(scratch, bad)],
    ["resolveJobLogFile", () => resolveJobLogFile(scratch, bad)]
  ]) {
    assert.throws(resolve, /single path segment|Invalid/, `${name} accepted ${JSON.stringify(bad)}`);
  }
}
// …and still accepts the ids the runtime actually generates.
assert.ok(resolveWorkflowRunDir("wf-abc-123").endsWith(path.join("workflows", "wf-abc-123")));
assert.ok(resolveJobFile(scratch, "wf-abc-123").endsWith("wf-abc-123.json"));

// --- end to end: the ledger survives a traversal resume ----------------------
const workspace = path.join(scratch, "repo");
fs.mkdirSync(workspace, { recursive: true });
setConfig(workspace, "stopReviewGate", true);
upsertJob(workspace, { id: "job-precious", status: "completed", summary: "must survive" });

const stateFile = resolveStateFile(workspace);
const before = fs.readFileSync(stateFile, "utf8");

const result = run(process.execPath, [
  RUNTIME, "workflow",
  "--script", path.join(FIXTURES, "fx-solo.mjs"),
  "--cwd", workspace,
  "--resume", "../state"
], { env: process.env });

assert.notEqual(result.status, 0, "a traversal run id must be refused");
assert.match(
  `${result.stdout ?? ""}${result.stderr ?? ""}`,
  /single path segment|Invalid run id/,
  "the refusal has to name the reason"
);
assert.equal(fs.readFileSync(stateFile, "utf8"), before, "the workspace ledger must be untouched");
const stateRoot = path.join(dataDir, "state");
assert.ok(!fs.existsSync(path.join(stateRoot, "lease.json")), "no lease may be planted in the state root");
assert.ok(!fs.existsSync(path.join(stateRoot, "journal.jsonl")), "no run artifacts in the state root");

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-id-paths: ok");
