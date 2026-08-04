import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { reduceJournal, runState, renderFrame }
  from "../../skills/codex-companion/runtime/scripts/lib/workflow/watch.mjs";

const T0 = "2026-08-03T17:48:52.200Z";
const t = (offsetSec) => new Date(Date.parse(T0) + offsetSec * 1000).toISOString();

// --- reduceJournal: journal events → interleaved timeline ---------------------

const events = [
  { at: t(0), type: "started", key: "agent|deriver|aaaa#0", kind: "agent", label: "deriver" },
  { at: t(46), type: "finished", key: "agent|deriver|aaaa#0", result: { lenses: ["L1", "L2"] } },
  { at: t(46), type: "log", message: "panel: sweep + 2 scalpels" },
  { at: t(47), type: "started", key: "review|sweep|bbbb#0", kind: "review", label: "sweep" },
  { at: t(47), type: "started", key: "review|scalpel-1|cccc#0", kind: "review", label: "scalpel-1" },
  { at: t(50), type: "retry", key: "review|scalpel-1|cccc#0", error: "transport hiccup" },
  { at: t(90), type: "finished", key: "review|scalpel-1|cccc#0", error: "codex exited 1" }
];

const timeline = reduceJournal(events);
// First-appearance order, with the log line interleaved where it happened.
assert.deepEqual(
  timeline.map((it) => (it.type === "log" ? "log" : it.label)),
  ["deriver", "log", "sweep", "scalpel-1"]
);

const [deriver, logLine, sweep, scalpel] = timeline;
assert.equal(deriver.state, "done");
assert.equal(deriver.kind, "agent");
assert.equal(deriver.startedAt, t(0));
assert.equal(deriver.finishedAt, t(46));
assert.ok(deriver.resultPreview.includes("lenses"), "done rows carry a result preview");
assert.equal(logLine.message, "panel: sweep + 2 scalpels");
assert.equal(sweep.state, "running");
assert.equal(sweep.finishedAt, undefined);
assert.equal(scalpel.state, "failed");
assert.equal(scalpel.retries, 1);
assert.equal(scalpel.error, "codex exited 1");

// A resumed run re-runs a failed key: a second `started` for the same key must
// reset the row to running, and a later success must override the old failure.
const resumed = reduceJournal([
  ...events,
  { at: t(120), type: "started", key: "review|scalpel-1|cccc#0", kind: "review", label: "scalpel-1" },
  { at: t(180), type: "finished", key: "review|scalpel-1|cccc#0", result: { ok: true } }
]);
const scalpelRow = resumed.find((it) => it.label === "scalpel-1");
assert.equal(scalpelRow.state, "done");
assert.equal(scalpelRow.startedAt, t(120), "re-run resets the clock");
assert.equal(resumed.filter((it) => it.label === "scalpel-1").length, 1, "same key stays one row");

// --- runState: run-dir artifacts → running | completed | interrupted ----------

const root = fs.mkdtempSync(path.join(os.tmpdir(), "wfw-"));
const mkRun = (name) => { const d = path.join(root, name); fs.mkdirSync(d); return d; };

const done = mkRun("done");
fs.writeFileSync(path.join(done, "result.json"), JSON.stringify({ verdict: "correct" }));
assert.deepEqual(runState(done), { state: "completed", result: { verdict: "correct" } });

const live = mkRun("live");
fs.writeFileSync(path.join(live, "lease.json"), JSON.stringify({ pid: process.pid, at: Date.now() }));
assert.equal(runState(live).state, "running");

const deadPid = 999999; // far above pid_max on macOS/Linux defaults
const dead = mkRun("dead");
fs.writeFileSync(path.join(dead, "lease.json"), JSON.stringify({ pid: deadPid, at: Date.now() }));
assert.equal(runState(dead).state, "interrupted");

assert.equal(runState(mkRun("bare")).state, "interrupted");

// A run can complete and still have a stale lease file lying around mid-release:
// result.json is the stronger signal and must win.
const both = mkRun("both");
fs.writeFileSync(path.join(both, "result.json"), "null");
fs.writeFileSync(path.join(both, "lease.json"), JSON.stringify({ pid: process.pid, at: Date.now() }));
assert.equal(runState(both).state, "completed");

// --- renderFrame: deterministic plain-text frame -------------------------------

const frame = renderFrame({
  runId: "wf-test-123",
  state: "running",
  timeline,
  now: Date.parse(t(100)),
  width: 100,
  color: false
});
const lines = frame.split("\n");
assert.ok(lines[0].includes("wf-test-123"), "header names the run");
assert.ok(lines[0].includes("running"), "header carries the state");
assert.ok(lines[0].includes("1 done"), "header counts done rows");
assert.ok(lines[0].includes("1 running"), "header counts running rows");
assert.ok(lines[0].includes("1 failed"), "header counts failed rows");
assert.ok(frame.includes("deriver"), "rows carry labels");
assert.ok(frame.includes("panel: sweep + 2 scalpels"), "log lines render");
assert.ok(frame.includes("46s"), "finished rows show their duration");
assert.ok(frame.includes("codex exited 1"), "failed rows show the error");
assert.ok(/✓/.test(frame), "done glyph present");
assert.ok(/✗/.test(frame), "failed glyph present");
assert.ok(!/\x1b\[/.test(frame), "color=false yields no ANSI escapes");
for (const line of lines) assert.ok(line.length <= 100, `line exceeds width: ${line}`);

const colored = renderFrame({
  runId: "wf-test-123", state: "running", timeline,
  now: Date.parse(t(100)), width: 100, color: true
});
assert.ok(/\x1b\[/.test(colored), "color=true yields ANSI escapes");

// --- CLI: snapshot mode (non-TTY stdout prints one frame and exits) -----------

const cli = path.resolve("../../skills/codex-companion/runtime/scripts/codex-companion.mjs");
const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), "wfw-root-"));
const runDir = path.join(dataRoot, "workflows", "wf-snapshot-1");
fs.mkdirSync(runDir, { recursive: true });
for (const ev of events) fs.appendFileSync(path.join(runDir, "journal.jsonl"), JSON.stringify(ev) + "\n");
fs.writeFileSync(path.join(runDir, "result.json"), JSON.stringify({ verdict: "correct" }));

const snap = spawnSync("node", [cli, "watch", "wf-snapshot-1"], {
  encoding: "utf8",
  env: { ...process.env, CLAUDE_PLUGIN_DATA: dataRoot }
});
assert.equal(snap.status, 0, `watch exited ${snap.status}: ${snap.stderr}`);
assert.ok(snap.stdout.includes("wf-snapshot-1"));
assert.ok(snap.stdout.includes("completed"));
assert.ok(snap.stdout.includes("deriver"));

const missing = spawnSync("node", [cli, "watch", "wf-nope"], {
  encoding: "utf8",
  env: { ...process.env, CLAUDE_PLUGIN_DATA: dataRoot }
});
assert.equal(missing.status, 1);
assert.ok(missing.stderr.includes("wf-nope"), "error names the missing run id");

console.log("test-watch: ok");
