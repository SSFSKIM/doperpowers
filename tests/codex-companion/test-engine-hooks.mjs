// The workflow engine: the hooks a workflow script is handed (agent/parallel/
// pipeline/log), the leaf semaphore, the journal cache, and schema repair —
// driven end to end against the transport-faithful mock app-server.
//
// Everything here is asserted against artifacts the engine and the mock actually
// wrote (journal.jsonl, workers.json, the mock's counter / turns.jsonl / peak),
// never against the engine's own bookkeeping alone.
//
// DETERMINISM: the mock consumes scenario.turns in ONE global order via a shared
// counter file, so a case that needs a specific behavior to land on a specific
// call must serialize the calls (maxConcurrency: 1). Concurrency itself is
// covered by the cap case, which asserts on the mock's own `peak` file.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { initGitRepo, makeTempDir, run } from "./helpers.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "fixtures");
const MOCK_BIN_DIR = path.join(HERE, "mock");

process.env.PATH = `${MOCK_BIN_DIR}${path.delimiter}${process.env.PATH}`;
delete process.env.CODEX_COMPANION_APP_SERVER_ENDPOINT;

const { runWorkflow, WorkflowError } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/workflow/engine.mjs"
);
const { acquireLease, releaseLease, repoFingerprint } = await import(
  "../../skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs"
);

const scratches = [];

// Each case gets its own repo, run dir and mock state: the scenario counter,
// turns.jsonl and peak are all global to a mock dir.
function newCase(name, turns) {
  const scratch = makeTempDir(`codex-engine-${name}-`);
  scratches.push(scratch);
  const mockDir = path.join(scratch, "mockstate");
  const repo = path.join(scratch, "repo");
  // runDir lives OUTSIDE the repo on purpose: journal/lease/result files inside
  // the tree would move the repo fingerprint and make every resume a mismatch.
  const runDir = path.join(scratch, "run");
  fs.mkdirSync(mockDir, { recursive: true });
  fs.mkdirSync(repo, { recursive: true });
  fs.writeFileSync(path.join(mockDir, "scenario.json"), JSON.stringify({ turns }));
  initGitRepo(repo);
  fs.writeFileSync(path.join(repo, "tracked.txt"), "base\n");
  run("git", ["add", "."], { cwd: repo });
  run("git", ["commit", "-m", "base"], { cwd: repo });
  process.env.CODEX_MOCK_DIR = mockDir;
  return { scratch, mockDir, repo, runDir };
}

const counter = (mockDir) => {
  const p = path.join(mockDir, "counter");
  return fs.existsSync(p) ? Number(fs.readFileSync(p, "utf8")) : 0;
};
const peak = (mockDir) => {
  const p = path.join(mockDir, "peak");
  return fs.existsSync(p) ? Number(fs.readFileSync(p, "utf8")) : 0;
};
const turnRequests = (mockDir) => {
  const p = path.join(mockDir, "turns.jsonl");
  if (!fs.existsSync(p)) return [];
  return fs.readFileSync(p, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
};
const journal = (runDir) =>
  fs.readFileSync(path.join(runDir, "journal.jsonl"), "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
const workers = (runDir) => JSON.parse(fs.readFileSync(path.join(runDir, "workers.json"), "utf8"));
const spawnRecord = (mockDir, pid) => JSON.parse(fs.readFileSync(path.join(mockDir, `spawn-${pid}.json`), "utf8"));

// --- happy path: log, agent, parallel absorption, pipeline, transport retry ---
{
  const c = newCase("happy", [
    { finalMessage: "solo answer" },      // 1  solo
    { finalMessage: "p1 answer" },        // 2  parallel[0]
    { die: true },                        // 3  parallel[1] first attempt
    { die: true },                        // 4  parallel[1] retry
    { finalMessage: "p3 answer" },        // 5  parallel[2]
    { finalMessage: "s1-10 answer" },     // 6  pipeline item 10, stage 1
    { finalMessage: "s1-20 answer" }      // 7  pipeline item 20, stage 1
  ]);
  const lines = [];
  const out = await runWorkflow({
    scriptPath: path.join(FIXTURES, "fx-happy.mjs"),
    args: { n: 3 },
    cwd: c.repo,
    maxConcurrency: 1,
    runDir: c.runDir,
    emit: (l) => lines.push(l)
  });

  assert.equal(out.result.one, "solo answer", "a plain agent() resolves to the turn's final message");
  assert.deepEqual(
    out.result.par,
    ["p1 answer", null, "p3 answer"],
    "parallel keeps positional results and absorbs the killed worker to null"
  );
  assert.deepEqual(
    out.result.piped,
    ["s1-10 answer|10|0", null],
    "pipeline threads each item through the stages; a stage throw drops THAT item to null only"
  );
  assert.equal(out.result.n, 3, "spec.args reaches the script");
  assert.equal(out.agents, 6, "six leaf calls were issued (1 solo + 3 parallel + 2 pipeline stage-1)");
  assert.equal(counter(c.mockDir), 7, "seven mock turns consumed: the killed call burned two of them");
  assert.ok(out.durationMs >= 0, "runWorkflow reports a duration");
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(c.runDir, "result.json"), "utf8")),
    out.result,
    "result.json holds the script's return value"
  );

  const evs = journal(c.runDir);
  assert.equal(evs.filter((e) => e.type === "started").length, 6, "one started event per leaf call");
  assert.equal(evs.filter((e) => e.type === "finished").length, 6, "one finished event per leaf call");
  assert.equal(evs.filter((e) => e.type === "retry").length, 1, "exactly one transport retry (the killed worker)");
  assert.deepEqual(
    evs.filter((e) => e.type === "log").map((e) => e.message),
    ["starting"],
    "log() lands in the journal"
  );

  const boomKey = evs.find((e) => e.type === "started" && e.label === "boom").key;
  const boomFinished = evs.filter((e) => e.type === "finished" && e.key === boomKey);
  assert.equal(boomFinished.length, 1, "the killed worker finishes once, after its retry — not once per attempt");
  assert.ok(boomFinished[0].error, "the killed worker's finished record carries the error");
  assert.ok(!("result" in boomFinished[0]), "…and no result: a dead turn must never be cached as an answer");
  for (const label of ["solo", "p1", "p3", "s1-10", "s1-20"]) {
    const key = evs.find((e) => e.type === "started" && e.label === label).key;
    const fin = evs.find((e) => e.type === "finished" && e.key === key);
    assert.ok(fin && typeof fin.result === "string" && !fin.error, `${label} finished with a result`);
  }

  assert.deepEqual(workers(c.runDir), [], "no worker pids left tracked after a run that retried a dead worker");
  assert.ok(lines.includes("log starting"), "emit carries log lines");
  assert.ok(lines.includes("retry agent:boom"), "emit announces the retry");
  assert.ok(lines.includes("fail agent:boom"), "emit announces the terminal failure");
  assert.ok(lines.includes("done agent:solo"), "emit announces completion");
}

// --- schema repair: one same-thread repair turn ------------------------------
{
  const c = newCase("schema", [
    { finalMessage: '{"okk":true}' },   // valid JSON, wrong shape
    { finalMessage: '{"ok":true}' }
  ]);
  const out = await runWorkflow({
    scriptPath: path.join(FIXTURES, "fx-schema.mjs"),
    args: {},
    cwd: c.repo,
    runDir: c.runDir
  });

  assert.deepEqual(out.result, { ok: true }, "the repaired payload is what the hook resolves to");
  assert.equal(counter(c.mockDir), 2, "one original turn + one repair turn");
  assert.equal(out.agents, 1, "a repair is part of the same leaf call, not a second one");

  const evs = journal(c.runDir);
  const retries = evs.filter((e) => e.type === "retry");
  assert.equal(retries.length, 1, "exactly one retry event for the repair");
  assert.deepEqual(retries[0].errors, ['$: missing required "ok" (have: okk)'], "the retry event records why");
  assert.equal(
    retries[0].key,
    evs.find((e) => e.type === "started" && e.label === "js").key,
    "the repair's retry event is keyed to the call it belongs to, so events correlate"
  );
  assert.equal(retries[0].reason, "schema-repair", "…and still says it was a schema repair, not a transport retry");

  const reqs = turnRequests(c.mockDir);
  assert.equal(reqs.length, 2, "two turn/start requests");
  assert.deepEqual(reqs.map((r) => r.method), ["turn/start", "turn/start"], "both are turns, not reviews");
  // Thread ids are minted per mock process (`t-<pid>-N`), so a repair that started
  // a FRESH thread could not possibly reuse the first turn's id. Same id across two
  // different server pids is the proof that the repair resumed the original thread.
  assert.notEqual(reqs[0].pid, reqs[1].pid, "the repair runs on its own app-server process");
  assert.equal(
    reqs[1].params.threadId,
    reqs[0].params.threadId,
    "the repair turn resumes the original thread — the model sees its own bad output"
  );
  assert.match(
    reqs[1].params.input[0].text,
    /^Your previous output failed schema validation: \$: missing required "ok"/,
    "the repair prompt names the validation failure"
  );
  assert.deepEqual(
    reqs[1].params.outputSchema,
    { type: "object", required: ["ok"], properties: { ok: { type: "boolean" } } },
    "the repair turn still carries the output schema"
  );
  assert.deepEqual(
    spawnRecord(c.mockDir, reqs[0].pid).argv,
    ["app-server"],
    "the agent lane passes no -c overrides: model and effort ride the turn params"
  );
  assert.deepEqual(workers(c.runDir), [], "both the original and the repair pid were untracked");
}

// --- schema exhaustion is terminal: exactly two turns, never three -----------
{
  const c = newCase("exhaust", [
    { finalMessage: '{"okk":true}' },
    { finalMessage: '{"okkk":true}' },
    { finalMessage: '{"ok":true}' }      // a third turn must never reach this
  ]);
  await assert.rejects(
    runWorkflow({ scriptPath: path.join(FIXTURES, "fx-schema.mjs"), args: {}, cwd: c.repo, runDir: c.runDir }),
    /schema validation failed after repair/,
    "an unrepairable schema failure propagates out of the workflow"
  );
  assert.equal(
    counter(c.mockDir),
    2,
    "exactly two turns: the transport retry must not grant a third attempt after a terminal failure"
  );
  assert.deepEqual(workers(c.runDir), [], "no pids left tracked after a terminal failure");
}

// --- failed-status turn: status, not error, is the signal --------------------
{
  const c = newCase("status", [
    { turnStatus: "failed", finalMessage: "looks fine" },
    { turnStatus: "failed", finalMessage: "looks fine" }
  ]);
  const out = await runWorkflow({
    scriptPath: path.join(FIXTURES, "fx-status.mjs"),
    args: {},
    cwd: c.repo,
    runDir: c.runDir
  });

  assert.deepEqual(
    out.result,
    [null],
    "a turn that completed UNSUCCESSFULLY rejects — its final message is not an answer"
  );
  assert.equal(counter(c.mockDir), 2, "both attempts ran: the failure is retried once like any transport failure");

  const evs = journal(c.runDir);
  const fin = evs.filter((e) => e.type === "finished");
  assert.equal(fin.length, 1, "one finished record for the one leaf call");
  assert.match(fin[0].error, /completed unsuccessfully/, "the finished record explains the status rejection");
  assert.ok(!("result" in fin[0]), "the plausible-looking final message is never recorded as a result");
  assert.deepEqual(workers(c.runDir), [], "no pids left tracked");
}

// --- the review hook ---------------------------------------------------------
// The panel rides on this hook. A review that silently reviews the wrong thing,
// or that loses its lens, returns a clean-looking report about the wrong code.
{
  const c = newCase("review", [{ reviewText: "# Sweep\n\nauth looks wrong" }]);
  const lines = [];
  const out = await runWorkflow({
    scriptPath: path.join(FIXTURES, "fx-review.mjs"),
    args: {},
    cwd: c.repo,
    runDir: c.runDir,
    emit: (l) => lines.push(l)
  });

  const reqs = turnRequests(c.mockDir);
  assert.equal(reqs.length, 1, "one review request");
  assert.equal(reqs[0].method, "review/start", "the hook drives review/start, not a turn");
  assert.deepEqual(
    reqs[0].params.target,
    { type: "baseBranch", branch: "main" },
    "review/start carries the resolved WIRE target — an explicit base becomes a baseBranch target"
  );
  assert.deepEqual(
    spawnRecord(c.mockDir, reqs[0].pid).argv,
    ["-c", "model_reasoning_effort=xhigh", "-c", "developer_instructions=watch the auth paths.", "app-server"],
    "effort and lens reach this worker's own app-server as -c overrides, in that order"
  );
  assert.deepEqual(
    out.result,
    { reviewText: "# Sweep\n\nauth looks wrong", threadId: reqs[0].params.threadId, status: 0 },
    "the hook returns the review text with the thread it ran on and a success status"
  );
  assert.equal(out.agents, 1, "a review is one leaf call");

  const evs = journal(c.runDir);
  const started = evs.find((e) => e.type === "started");
  assert.equal(started.kind, "review", "the journal records the call as a review");
  assert.equal(started.label, "sweep", "…under its label");
  assert.deepEqual(
    evs.find((e) => e.type === "finished").result,
    out.result,
    "the review result is journaled and therefore cacheable across a resume"
  );
  assert.ok(lines.includes("start review:sweep") && lines.includes("done review:sweep"), "emit names the review lane");
  assert.deepEqual(workers(c.runDir), [], "no pids left tracked");
}

// --- a review whose turn failed is not a review ------------------------------
{
  const c = newCase("review-fail", [
    { turnStatus: "failed", reviewText: "# Sweep\n\nno findings" },
    { turnStatus: "failed", reviewText: "# Sweep\n\nno findings" }
  ]);
  const out = await runWorkflow({
    scriptPath: path.join(FIXTURES, "fx-review-fail.mjs"),
    args: {},
    cwd: c.repo,
    runDir: c.runDir
  });

  assert.deepEqual(out.result, [null], "a failed review turn rejects — a clean-looking report is not a result");
  assert.equal(counter(c.mockDir), 2, "both attempts ran");
  const fin = journal(c.runDir).filter((e) => e.type === "finished");
  assert.equal(fin.length, 1, "one finished record");
  assert.match(fin[0].error, /review completed unsuccessfully/, "the status gate is what rejected it");
  assert.ok(!("result" in fin[0]), "the review text is never recorded as a result");
  assert.deepEqual(workers(c.runDir), [], "no pids left tracked");
}

// --- a review whose target moved under it is not a result --------------------
// The cache key names a resolved commit, but `review/start` takes a symbolic
// branch. Between keying the call and the worker reading the diff — a semaphore
// wait, a transport retry, someone else's push — the ref can move, and the
// worker then reviews a range the key does not describe. Journaling that under
// the old commit key is exactly the stale-replay the key exists to prevent.
{
  const c = newCase("movingref", [
    { reviewText: "# R\n\nagainst the moved range" },
    { reviewText: "# R\n\nstill moved" }
  ]);
  const commit = (name, body) => {
    fs.writeFileSync(path.join(c.repo, name), body);
    run("git", ["add", "."], { cwd: c.repo });
    run("git", ["commit", "-m", name], { cwd: c.repo });
    return run("git", ["rev-parse", "HEAD"], { cwd: c.repo }).stdout.trim();
  };
  run("git", ["checkout", "-b", "feature"], { cwd: c.repo });
  const midpoint = commit("b.txt", "B\n");
  commit("c.txt", "C\n");

  await assert.rejects(
    runWorkflow({
      scriptPath: path.join(FIXTURES, "fx-review-moving.mjs"),
      args: { repo: c.repo, moveTo: midpoint },
      cwd: c.repo,
      runDir: c.runDir
    }),
    (err) => /review target moved/.test(err.message),
    "a review whose base ref moved under it is returned as a result anyway"
  );
  assert.equal(counter(c.mockDir), 2, "both attempts ran: the moved target is a leaf failure like any other");
  const fin = journal(c.runDir).filter((e) => e.type === "finished");
  assert.equal(fin.length, 1, "one finished record");
  assert.ok(!("result" in fin[0]), "no review text is journaled under a commit key it does not describe");
  assert.match(fin[0].error, /review target moved/, "the journal says why");
}

// --- the leaf semaphore caps a bare Promise.all ------------------------------
{
  const c = newCase("cap", Array.from({ length: 10 }, (_, i) => ({ finalMessage: `c${i} answer`, hangMs: 150 })));
  const out = await runWorkflow({
    scriptPath: path.join(FIXTURES, "fx-cap.mjs"),
    args: {},
    cwd: c.repo,
    maxConcurrency: 2,
    runDir: c.runDir
  });

  assert.equal(out.result.length, 10, "all ten agents resolved");
  assert.equal(counter(c.mockDir), 10, "ten turns consumed");
  assert.ok(
    peak(c.mockDir) <= 2,
    `the semaphore caps live app-servers at maxConcurrency even under a bare Promise.all (peak was ${peak(c.mockDir)})`
  );
  assert.deepEqual(workers(c.runDir), [], "no pids left tracked");
}

// --- content-keyed cache with per-run occurrence counters --------------------
{
  const c = newCase("cache", [
    { finalMessage: "first" },
    { finalMessage: "second" },
    { finalMessage: "MUST-NOT-BE-REACHED" }
  ]);
  const spec = {
    scriptPath: path.join(FIXTURES, "fx-twice.mjs"),
    args: {},
    cwd: c.repo,
    runDir: c.runDir
  };
  const first = await runWorkflow(spec);
  assert.deepEqual(first.result, ["first", "second"], "two identical calls get their own turns");
  assert.equal(counter(c.mockDir), 2, "two turns consumed on the fresh run");

  const lines = [];
  const resumed = await runWorkflow({ ...spec, resume: true, emit: (l) => lines.push(l) });
  assert.deepEqual(
    resumed.result,
    ["first", "second"],
    "a resume replays both identical calls in order — the occurrence counter keeps them apart"
  );
  assert.equal(counter(c.mockDir), 2, "a fully cached resume spawns nothing");
  assert.equal(resumed.agents, 0, "no leaf call was issued on the resume");
  assert.deepEqual(lines.filter((l) => l.startsWith("cache ")), ["cache agent:dup", "cache agent:dup"], "both hits are announced");

  // A journal whose fingerprint is GONE has nothing to compare against, and
  // there is cacheable history to serve. Recording the CURRENT fingerprint
  // there blesses whatever the tree looks like now and then replays successes
  // produced against the old one — deleting one file would be all it takes.
  const fpFile = path.join(c.runDir, "fingerprint");
  const recorded = fs.readFileSync(fpFile, "utf8");
  fs.rmSync(fpFile);
  await assert.rejects(
    runWorkflow({ ...spec, resume: true }),
    (err) => err instanceof WorkflowError && err.reason === "fingerprint-mismatch"
      && /no recorded fingerprint/.test(err.message),
    "a journal with no fingerprint is replayed against a repo nobody blessed"
  );
  assert.ok(!fs.existsSync(fpFile), "the refused resume adopted the current repo state anyway");
  assert.equal(counter(c.mockDir), 2, "the refused resume never reached the script");
  fs.writeFileSync(fpFile, recorded);

  // fingerprint guard: the same run dir against a changed repo must refuse.
  fs.writeFileSync(path.join(c.repo, "new-untracked.txt"), "drift\n");
  await assert.rejects(
    runWorkflow({ ...spec, resume: true }),
    (err) => err instanceof WorkflowError && err.reason === "fingerprint-mismatch",
    "resuming against a changed repo is refused, not silently replayed"
  );
}

// --- an EMPTY journal may still be re-fingerprinted ---------------------------
// The refusal above is about replaying history against unblessed code. A run
// dir with nothing journaled has no history to replay, so arming the guard with
// the current fingerprint is honest — and refusing here would strand a run that
// died before it wrote its first event.
{
  const c = newCase("nojournal", [{ finalMessage: "fresh" }]);
  fs.mkdirSync(c.runDir, { recursive: true });
  const spec = { scriptPath: path.join(FIXTURES, "fx-solo.mjs"), args: {}, cwd: c.repo, runDir: c.runDir };
  const out = await runWorkflow({ ...spec, resume: true });
  assert.equal(out.result.one, "fresh", "a resume with nothing journaled runs the script live");
  assert.ok(
    fs.existsSync(path.join(c.runDir, "fingerprint")),
    "a resume with no history arms the guard instead of leaving it off"
  );
  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 1, "…and the guard it armed lets the next resume cache-hit");
}

// --- resume recovers a failed call, keeps a successful one cached ------------
// The cache serves SUCCESSES only. Replaying a journaled failure would mean a
// crashed run can never regain a worker it lost to a transient death; a
// genuinely deterministic failure just re-fails, bounded by the transport retry.
{
  const c = newCase("recover", [
    { finalMessage: "good answer" },        // 1  run 1: the call that sticks
    { die: true },                          // 2  run 1: risky, first attempt
    { die: true },                          // 3  run 1: risky, retry
    { finalMessage: "risky recovered" }     // 4  run 2: risky, re-run live
  ]);
  const spec = {
    scriptPath: path.join(FIXTURES, "fx-recover.mjs"),
    args: {},
    cwd: c.repo,
    runDir: c.runDir
  };
  const first = await runWorkflow(spec);
  assert.deepEqual(first.result, { good: "good answer", risky: null }, "run 1 loses the risky call");
  assert.equal(counter(c.mockDir), 3, "run 1 burned one turn on the good call and two on the dead one");

  const lines = [];
  const second = await runWorkflow({ ...spec, resume: true, emit: (l) => lines.push(l) });
  assert.deepEqual(
    second.result,
    { good: "good answer", risky: "risky recovered" },
    "the resume serves the cached success and re-runs the failure to a real answer"
  );
  assert.equal(counter(c.mockDir), 4, "exactly one new turn: the failure re-ran live, the success did not");
  assert.equal(second.agents, 1, "only the previously-failed call was issued again");
  assert.ok(lines.includes("cache agent:good"), "the successful call is announced as a cache hit");
  assert.ok(lines.includes("cache-skip agent:risky"), "the failed call is announced as a deliberate cache miss");
  assert.ok(!lines.includes("cache agent:risky"), "a failed record is never served as a hit");
  assert.ok(!lines.includes("start agent:good"), "the cached success never reaches a live turn");

  const evs = journal(c.runDir);
  const riskyKey = evs.find((e) => e.type === "started" && e.label === "risky").key;
  const riskyFinished = evs.filter((e) => e.type === "finished" && e.key === riskyKey);
  assert.equal(riskyFinished.length, 2, "both the failure and the recovery are journaled under the same key");
  assert.ok(riskyFinished[0].error, "the first record is the failure");
  assert.equal(riskyFinished[1].result, "risky recovered", "the last record wins, so a third run cache-hits the success");
  const goodKey = evs.find((e) => e.type === "started" && e.label === "good").key;
  assert.equal(
    evs.filter((e) => e.type === "started" && e.key === goodKey).length,
    1,
    "the successful call was never started a second time"
  );
  assert.deepEqual(workers(c.runDir), [], "no pids left tracked");
}

// --- lease and script-error refusals -----------------------------------------
{
  const c = newCase("refuse", [{ finalMessage: "unused" }]);
  fs.mkdirSync(c.runDir, { recursive: true });
  // pid 1 — always alive, never us. It used to be process.pid here, but the
  // lease is now re-entrant for the SAME process (the CLI takes it before
  // replacing a resumed run's record, then hands off to the engine), so only a
  // FOREIGN live holder proves the refusal.
  fs.writeFileSync(path.join(c.runDir, "lease.json"), JSON.stringify({ pid: 1, at: Date.now() }));
  await assert.rejects(
    runWorkflow({ scriptPath: path.join(FIXTURES, "fx-happy.mjs"), args: {}, cwd: c.repo, runDir: c.runDir }),
    (err) => err instanceof WorkflowError && err.reason === "lease-held" && /pid \d+/.test(err.message),
    "a run dir held by a live FOREIGN process is refused, naming the holder"
  );

  // ...and the same-pid case is the one the resume path depends on: a lease this
  // process already holds must not refuse its own engine hand-off.
  fs.rmSync(path.join(c.runDir, "lease.json"), { force: true });
  assert.deepEqual(acquireLease(c.runDir), { ok: true });
  assert.deepEqual(acquireLease(c.runDir), { ok: true }, "the lease is re-entrant for its own holder");
  releaseLease(c.runDir);   // leaves the run dir lease-free for the next case
  assert.equal(counter(c.mockDir), 0, "a refused run never reaches the workflow script");

  await assert.rejects(
    runWorkflow({ scriptPath: path.join(FIXTURES, "fx-nodefault.mjs"), args: {}, cwd: c.repo, runDir: c.runDir }),
    (err) => err instanceof WorkflowError && err.reason === "script-error",
    "a script with no default export is a script-error"
  );
  // The lease is released even when the run throws, so the next run can proceed.
  assert.ok(!fs.existsSync(path.join(c.runDir, "lease.json")), "the lease is released on the failure path");
}

// --- cache identity: what a resume is allowed to reuse ------------------------
// Every case here runs, then RESUMES the same run dir and reads the mock's
// global turn counter: an unchanged input must cost 0 new turns (cache hit) and
// a changed one must cost a fresh turn (cache miss). The counter is the mock's
// own file, not the engine's bookkeeping.
{
  // (a) A hook pointed at ANOTHER repository through opts.cwd. The run-level
  // fingerprint only ever covered spec.cwd, so changes over there were invisible.
  const c = newCase("percwd", [{ finalMessage: "one" }, { finalMessage: "two" }]);
  const other = path.join(c.scratch, "other");
  fs.mkdirSync(other, { recursive: true });
  initGitRepo(other);
  fs.writeFileSync(path.join(other, "f.txt"), "before\n");
  run("git", ["add", "."], { cwd: other });
  run("git", ["commit", "-m", "base"], { cwd: other });

  const spec = { scriptPath: path.join(FIXTURES, "fx-percwd.mjs"), args: { cwd: other }, cwd: c.repo, runDir: c.runDir };
  await runWorkflow(spec);
  assert.equal(counter(c.mockDir), 1);

  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 1, "an unchanged per-call repo cache-hits");

  fs.writeFileSync(path.join(other, "f.txt"), "after\n");   // dirty the OTHER repo only
  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 2, "a changed per-call repo must MISS the cache");
}

{
  // (b) A review whose base ref MOVES. The opts are byte-identical across runs;
  // only the commit the ref resolves to changed.
  const c = newCase("movedref", [{ reviewText: "# R\n\nfirst" }, { reviewText: "# R\n\nsecond" }]);
  const commit = (name, body) => {
    fs.writeFileSync(path.join(c.repo, name), body);
    run("git", ["add", "."], { cwd: c.repo });
    run("git", ["commit", "-m", name], { cwd: c.repo });
    return run("git", ["rev-parse", "HEAD"], { cwd: c.repo }).stdout.trim();
  };
  run("git", ["checkout", "-b", "feature"], { cwd: c.repo });
  const midpoint = commit("b.txt", "B\n");
  commit("c.txt", "C\n");

  const spec = { scriptPath: path.join(FIXTURES, "fx-review.mjs"), args: {}, cwd: c.repo, runDir: c.runDir };
  await runWorkflow(spec);
  assert.equal(counter(c.mockDir), 1);

  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 1, "an unmoved base ref cache-hits");

  // Move `main` forward along feature's own history. HEAD, the working tree and
  // the untracked set are all untouched, so the RUN fingerprint is byte-identical
  // — but merge-base(main, HEAD) is now a different commit, so the review is
  // against a different diff. Only a target-aware cache key can see this.
  const before = repoFingerprint(c.repo, [path.join(FIXTURES, "fx-review.mjs")]);
  run("git", ["branch", "-f", "main", midpoint], { cwd: c.repo });
  assert.equal(
    repoFingerprint(c.repo, [path.join(FIXTURES, "fx-review.mjs")]), before,
    "the run fingerprint must be unchanged, or this case proves nothing"
  );
  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 2, "a moved review target must MISS the cache");
}

{
  // (c) A schema that changes AFTER byte 64 without changing its length. The old
  // key was length + the first 64 chars, so these two collided — and a resume
  // serves the cached result before validating it against the current schema.
  const c = newCase("schemahash", [{ finalRaw: '{"a":1}' }, { finalRaw: '{"a":1}' }]);
  const schemaWith = (tail) => ({
    type: "object",
    properties: { a: { type: "number" } },
    required: ["a"],
    additionalProperties: false,
    description: tail            // same length, differs well past byte 64
  });
  // The schema arrives through a file OUTSIDE the repo and outside the script's
  // directory, so it moves without touching the run fingerprint: this case is
  // about the leaf cache key alone.
  const schemaPath = path.join(c.scratch, "schema.json");
  const spec = {
    scriptPath: path.join(FIXTURES, "fx-schema-file.mjs"), args: { schemaPath },
    cwd: c.repo, runDir: c.runDir
  };
  const a = schemaWith("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
  const b = schemaWith("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB");
  assert.equal(JSON.stringify(a).length, JSON.stringify(b).length, "the two schemas must be the same length");
  assert.equal(JSON.stringify(a).slice(0, 64), JSON.stringify(b).slice(0, 64), "...and share their first 64 bytes");

  fs.writeFileSync(schemaPath, JSON.stringify(a));
  await runWorkflow(spec);
  assert.equal(counter(c.mockDir), 1);
  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 1, "the same schema cache-hits");
  fs.writeFileSync(schemaPath, JSON.stringify(b));
  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 2, "a schema differing after byte 64 must MISS the cache");
}

{
  // (c2) The workflow ARGS decide which calls the script makes, and a leaf is
  // keyed by its payload plus which occurrence of that identity it is within
  // THIS run. Args that drop an earlier identical call therefore shift a later
  // logical call onto `#0` and serve it the earlier call's result. Args ride
  // the run fingerprint, so a changed --args refuses the resume outright.
  const c = newCase("argsident", [{ finalMessage: "first" }, { finalMessage: "second" }]);
  const spec = { scriptPath: path.join(FIXTURES, "fx-args-count.mjs"), cwd: c.repo, runDir: c.runDir };

  const out = await runWorkflow({ ...spec, args: { n: 2 } });
  assert.deepEqual(out.result, ["first", "second"], "two calls, two independent answers");
  assert.equal(counter(c.mockDir), 2);

  await runWorkflow({ ...spec, args: { n: 2 }, resume: true });
  assert.equal(counter(c.mockDir), 2, "unchanged args still cache-hit — the guard is not blanket");

  await assert.rejects(
    runWorkflow({ ...spec, args: { n: 1 }, resume: true }),
    (err) => err instanceof WorkflowError && err.reason === "fingerprint-mismatch",
    "changed args are replayed against a journal whose call sequence they no longer match"
  );
  assert.equal(counter(c.mockDir), 2, "the refused resume never reached the script");
}

{
  // (d) Fingerprinting that FAILS is not the same as a directory that is not a
  // repository. A corrupt HEAD makes every git read after the work-tree probe
  // fail; both runs would previously have recorded the "no-git" constant and
  // compared equal, waving a resume through against unknown code.
  const c = newCase("fpfail", [{ finalMessage: "one" }]);

  // A directory that is not a repository at all: still the stable constant.
  const plain = path.join(c.scratch, "plain");
  fs.mkdirSync(plain, { recursive: true });
  assert.ok(repoFingerprint(plain).startsWith("no-git:"), "a non-repository is still marked no-git");

  // A real repository whose git reads FAIL. A commitless repo is the cheapest
  // faithful instance: `rev-parse --is-inside-work-tree` succeeds, and every
  // read after it (rev-parse HEAD, diff HEAD) fails. The 64 MiB-diff ENOBUFS
  // case the review named takes the same path — execFileSync is a named ESM
  // import here and cannot be monkeypatched, so this is the honest stand-in.
  const empty = path.join(c.scratch, "empty");
  fs.mkdirSync(empty, { recursive: true });
  initGitRepo(empty);
  assert.throws(() => repoFingerprint(empty), "a failed git read must throw, never collapse to 'no-git'");

  const spec = { scriptPath: path.join(FIXTURES, "fx-solo.mjs"), args: {}, cwd: empty, runDir: c.runDir };
  await runWorkflow(spec);   // a FRESH run still proceeds, recording the failure
  assert.equal(counter(c.mockDir), 1);
  assert.match(fs.readFileSync(path.join(c.runDir, "fingerprint"), "utf8"), /^error:/);

  await assert.rejects(
    runWorkflow({ ...spec, resume: true }),
    (err) => err instanceof WorkflowError && err.reason === "fingerprint-mismatch" && /unavailable/.test(err.message),
    "a resume whose fingerprint cannot be taken is refused, not waved through"
  );
  assert.equal(counter(c.mockDir), 1, "the refused resume never reached the script");
}

{
  // (e) A per-call cwd that cannot be fingerprinted makes that call UNCACHEABLE.
  // `error:<msg>` is stable, so keying on it would let a resume that fails the
  // same way be served a result computed from files nobody can compare.
  const c = newCase("degraded", [{ finalMessage: "one" }, { finalMessage: "two" }]);
  const unborn = path.join(c.scratch, "unborn");
  fs.mkdirSync(unborn, { recursive: true });
  initGitRepo(unborn);                       // a repo with no commits: every read after the probe fails
  assert.throws(() => repoFingerprint(unborn));

  const emitted = [];
  const spec = {
    scriptPath: path.join(FIXTURES, "fx-percwd.mjs"), args: { cwd: unborn },
    cwd: c.repo, runDir: c.runDir, emit: (line) => emitted.push(line)
  };
  await runWorkflow(spec);
  assert.equal(counter(c.mockDir), 1);
  assert.ok(emitted.some((l) => l.startsWith("fingerprint-degraded other")),
    "a degraded call announces itself on the progress channel");
  assert.ok(
    journal(c.runDir).some((e) => e.type === "finished" && !e.error),
    "the run still journaled a success, so only the KEY may prevent the hit"
  );

  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 2, "a degraded call must re-run live, never cache-hit");
}

{
  // (e2) A workflow script's HELPERS are orchestration code too. Only the entry
  // script used to ride the fingerprint, so an ad-hoc script's `./lib/extract.mjs`
  // could change between runs and the journal would mix results produced under
  // the old semantics with fresh ones. The widening is deliberately pragmatic —
  // the script's own directory plus a `lib/` beside it, not the import graph.
  const c = newCase("helperdrift", [{ finalMessage: "one" }, { finalMessage: "MUST-NOT-BE-REACHED" }]);
  const wfDir = path.join(c.scratch, "wf");
  fs.mkdirSync(path.join(wfDir, "lib"), { recursive: true });
  const script = path.join(wfDir, "entry.mjs");
  const helper = path.join(wfDir, "lib", "helper.mjs");
  const sibling = path.join(wfDir, "sibling.mjs");
  fs.writeFileSync(helper, 'export const note = "inspect";\n');
  fs.writeFileSync(sibling, "export const unused = 1;\n");
  fs.writeFileSync(script,
    'import { note } from "./lib/helper.mjs";\n' +
    "export default async function run({ agent }) { return agent(note, { label: \"solo\" }); }\n");

  const spec = { scriptPath: script, args: {}, cwd: c.repo, runDir: c.runDir };
  await runWorkflow(spec);
  assert.equal(counter(c.mockDir), 1);
  await runWorkflow({ ...spec, resume: true });
  assert.equal(counter(c.mockDir), 1, "an untouched workflow directory still resumes — the guard is not blanket");

  fs.writeFileSync(helper, 'export const note = "inspect harder";\n');
  await assert.rejects(
    runWorkflow({ ...spec, resume: true }),
    (err) => err instanceof WorkflowError && err.reason === "fingerprint-mismatch",
    "an edited lib/ helper leaves the journal replayable under different orchestration code"
  );

  fs.writeFileSync(helper, 'export const note = "inspect";\n');          // back to the blessed state
  fs.writeFileSync(sibling, "export const unused = 2;\n");
  await assert.rejects(
    runWorkflow({ ...spec, resume: true }),
    (err) => err instanceof WorkflowError && err.reason === "fingerprint-mismatch",
    "an edited sibling module beside the script is invisible to the guard"
  );
  assert.equal(counter(c.mockDir), 1, "no refused resume reached the script");
}

{
  // (f) An ARRAY-root schema whose first response needs repair. The repair prompt
  // used to demand a "JSON object", contradicting the schema it was repairing
  // against, so a repairable array failed terminally.
  const c = newCase("arrayschema", [{ finalRaw: '{"a":1}' }, { finalRaw: '[{"a":1}]' }]);
  const schema = { type: "array", items: { type: "object", properties: { a: { type: "number" } }, required: ["a"] } };
  const out = await runWorkflow({
    scriptPath: path.join(FIXTURES, "fx-schema-args.mjs"), args: { schema },
    cwd: c.repo, runDir: c.runDir, maxConcurrency: 1
  });
  assert.deepEqual(out.result, [{ a: 1 }], "the repaired array is returned, not a terminal failure");
  assert.equal(counter(c.mockDir), 2, "exactly two turns: the invalid one and its repair");
  const repairPrompt = turnRequests(c.mockDir)[1].params.input[0].text;
  assert.match(repairPrompt, /corrected JSON value matching the schema/);
  assert.doesNotMatch(repairPrompt, /JSON object/, "the prompt must not contradict an array-root schema");
}

for (const s of scratches) fs.rmSync(s, { recursive: true, force: true });
console.log("test-engine-hooks: ok");
