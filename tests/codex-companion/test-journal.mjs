import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync, spawn } from "node:child_process";
import { cacheKey, appendEvent, loadJournal, acquireLease, releaseLease, repoFingerprint }
  from "../../skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wfj-"));
const j = path.join(dir, "journal.jsonl");

const k1 = cacheKey("agent", "finder", { prompt: "p1", opts: { effort: "high" } });
assert.equal(k1, cacheKey("agent", "finder", { prompt: "p1", opts: { effort: "high" } }));
assert.notEqual(k1, cacheKey("agent", "finder", { prompt: "p2", opts: { effort: "high" } }));

appendEvent(j, { type: "started", key: k1 + "#0" });
appendEvent(j, { type: "started", key: "agent|b|x#0" });
appendEvent(j, { type: "finished", key: "agent|b|x#0", result: "B" });   // out-of-order finish
appendEvent(j, { type: "finished", key: k1 + "#0", result: "A" });
fs.appendFileSync(j, '{"type":"finished","key":"torn');                   // torn tail
let loaded = loadJournal(j);
assert.equal(loaded.finished.get(k1 + "#0").result, "A");
assert.equal(loaded.finished.get("agent|b|x#0").result, "B");
assert.equal(loaded.finished.size, 2);                                    // torn line ignored
appendEvent(j, { type: "started", key: "agent|c|y#0" });                  // started, never finished
loaded = loadJournal(j);
assert.ok(!loaded.finished.has("agent|c|y#0"));

assert.deepEqual(acquireLease(dir), { ok: true });
assert.equal(acquireLease(dir).ok, false);                                // same live pid holds it
releaseLease(dir);
assert.equal(acquireLease(dir).ok, true);
releaseLease(dir);
fs.writeFileSync(path.join(dir, "lease.json"), JSON.stringify({ pid: 999999, at: 0 }));
assert.equal(acquireLease(dir).ok, true);                                 // dead-pid lease broken
releaseLease(dir);

// SIMULTANEOUS acquisition (the check-then-write race): two child
// processes spin-wait on a barrier file, then both call acquireLease on
// the same dir and print the result. Exactly ONE may win.
const raceDir = fs.mkdtempSync(path.join(os.tmpdir(), "wfl-"));
const barrier = path.join(raceDir, "go");
const readyDir = path.join(raceDir, "ready");
fs.mkdirSync(readyDir);
const kid = `
  import { acquireLease } from ${JSON.stringify(new URL("../../skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs", import.meta.url).href)};
  import fs from "node:fs";
  import path from "node:path";
  fs.writeFileSync(path.join(process.argv[3], String(process.pid)), "");   // "I am spinning"
  while (!fs.existsSync(process.argv[2])) {}
  console.log(JSON.stringify(acquireLease(process.argv[1])));
`;
const kids = [1, 2].map(() =>
  spawn(process.execPath, ["--input-type=module", "-e", kid, raceDir, barrier, readyDir]));
const outs = [];
const errs = [];
let exited = 0;
const done = Promise.all(kids.map(k => new Promise(res => {
  let o = "", e = "";
  k.stdout.on("data", d => o += d);
  k.stderr.on("data", d => e += d);
  k.on("exit", () => { outs.push(o); errs.push(e); exited++; res(); });
})));
// Both children must already be spinning when the barrier appears — otherwise
// the "race" degenerates into two sequential acquisitions.
const deadline = Date.now() + 30_000;
while (fs.readdirSync(readyDir).length < 2 && exited === 0 && Date.now() < deadline) {
  await new Promise(res => setTimeout(res, 5));
}
assert.equal(fs.readdirSync(readyDir).length, 2,
  `both lease-race children must be spinning before the barrier; stderr: ${errs.join(" | ")}`);
fs.writeFileSync(barrier, "");
await done;
const wins = outs.filter(o => {
  assert.ok(o.trim(), `lease-race child produced no result; stderr: ${errs.join(" | ")}`);
  return JSON.parse(o).ok === true;
}).length;
assert.equal(wins, 1, `lease race: expected exactly 1 winner, got ${wins}`);

// releaseLease ownership: a process that does NOT hold the lease must not remove it
fs.writeFileSync(path.join(raceDir, "lease.json"), JSON.stringify({ pid: 999998, at: 0 }));
releaseLease(raceDir);            // not ours (pid differs) → must be a no-op
assert.ok(fs.existsSync(path.join(raceDir, "lease.json")), "releaseLease removed a lease it does not own");

// CONTENT-aware fingerprint: same porcelain status, different bytes ⇒ different fp
const repo = fs.mkdtempSync(path.join(os.tmpdir(), "wfr-"));
spawnSync("git", ["init", "-q", "-b", "main"], { cwd: repo });
fs.writeFileSync(path.join(repo, "f.txt"), "one");
spawnSync("git", ["add", "-A"], { cwd: repo });
spawnSync("git", ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c"], { cwd: repo });
fs.writeFileSync(path.join(repo, "f.txt"), "dirty-A");   // file now Modified
const fpA = repoFingerprint(repo);
fs.writeFileSync(path.join(repo, "f.txt"), "dirty-B");   // STILL just Modified in porcelain
assert.notEqual(repoFingerprint(repo), fpA, "fingerprint blind to content changes in already-dirty files");

const fp1 = repoFingerprint(process.cwd());
assert.equal(fp1, repoFingerprint(process.cwd()));
assert.equal(repoFingerprint(dir), "no-git");
console.log("test-journal: ok");
