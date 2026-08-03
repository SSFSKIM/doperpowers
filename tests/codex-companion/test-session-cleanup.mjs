// SessionEnd cleanup is a ledger WRITER, so it has to go through the same lock
// every other writer takes. It used to loadState and then saveState unlocked:
// a concurrent locked upsertJob (a background task registering, a workflow
// finalizing) could be renamed straight over by the hook's stale snapshot, and
// saveState's pruning pass would then delete the newly added job's record and
// log as "dropped".
//
// A live-held lock is the deterministic stand-in for that concurrency: an
// unlocked writer walks past it, a locked one cannot.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HOOK = path.join(HERE, "..", "..", "skills", "codex-companion", "runtime", "scripts", "session-lifecycle-hook.mjs");

const scratch = makeTempDir("codex-sessend-");
const dataDir = path.join(scratch, "data");
fs.mkdirSync(dataDir, { recursive: true });
process.env.CLAUDE_PLUGIN_DATA = dataDir;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const { ensureStateDir, loadState, resolveStateFile, upsertJob } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/state.mjs"
);

const workspace = path.join(scratch, "repo");
fs.mkdirSync(workspace, { recursive: true });

function endSession(sessionId) {
  return run(process.execPath, [HOOK, "SessionEnd"], {
    env: process.env,
    input: JSON.stringify({ hook_event_name: "SessionEnd", session_id: sessionId, cwd: workspace })
  });
}

// --- a live holder's lock is respected ---------------------------------------
upsertJob(workspace, { id: "job-mine", sessionId: "S1", status: "completed" });
upsertJob(workspace, { id: "job-theirs", sessionId: "S2", status: "completed" });

ensureStateDir(workspace);
const lockDir = `${resolveStateFile(workspace)}.lock`;
fs.mkdirSync(lockDir);
fs.writeFileSync(path.join(lockDir, "holder"), String(process.pid), "utf8");

const contended = endSession("S1");
assert.notEqual(contended.status, 0, "a hook that could not take the lock must not report success");
assert.deepEqual(
  loadState(workspace).jobs.map((job) => job.id).sort(),
  ["job-mine", "job-theirs"],
  "the ledger must be untouched while another writer holds the lock"
);

fs.rmSync(lockDir, { recursive: true, force: true });

// --- and the cleanup itself still works --------------------------------------
const released = endSession("S1");
assert.equal(released.status, 0, `the hook must succeed once the lock is free: ${released.stderr}`);
assert.deepEqual(
  loadState(workspace).jobs.map((job) => job.id),
  ["job-theirs"],
  "the ending session's jobs are dropped and everyone else's are kept"
);

fs.rmSync(scratch, { recursive: true, force: true });
console.log("test-session-cleanup: ok");
