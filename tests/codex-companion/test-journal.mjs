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
// A break token abandoned by a breaker that crashed must not wedge acquisition.
fs.writeFileSync(path.join(dir, "lease.json"), JSON.stringify({ pid: 999999, at: 0 }));
fs.writeFileSync(path.join(dir, "lease.json.break-999999"), JSON.stringify({ pid: 999997, at: 0 }));
assert.equal(acquireLease(dir).ok, true);
assert.ok(!fs.existsSync(path.join(dir, "lease.json.break-999999")), "stale break token not cleared");
releaseLease(dir);

// cacheKey must not alias across the field separator
assert.notEqual(cacheKey("agent|x", "y", 1), cacheKey("agent", "x|y", 1));

// SIMULTANEOUS acquisition (the check-then-write race): N child processes
// spin-wait on a barrier file, then all call acquireLease on the same dir
// and print the result. Exactly ONE may win, and the lease left on disk
// must belong to that winner.
// argv: [runDir, barrier, readyDir, holdFile]. The child announces itself,
// spins until the barrier appears, acquires — and then KEEPS RUNNING until
// released. A winner that exited immediately would leave a lease owned by a
// dead pid, which any later contender may legitimately break; the race would
// then report two "winners" for a perfectly correct implementation.
const kid = `
  import { acquireLease } from ${JSON.stringify(new URL("../../skills/codex-companion/runtime/scripts/lib/workflow/journal.mjs", import.meta.url).href)};
  import fs from "node:fs";
  import path from "node:path";
  fs.writeFileSync(path.join(process.argv[3], String(process.pid)), "");   // "I am spinning"
  while (!fs.existsSync(process.argv[2])) {}
  const res = acquireLease(process.argv[1]);
  console.log(JSON.stringify({ pid: process.pid, res }));
  while (!fs.existsSync(process.argv[4])) {}                               // hold the lease
`;

async function leaseRace(n, preseed) {
  const raceDir = fs.mkdtempSync(path.join(os.tmpdir(), "wfl-"));
  const barrier = path.join(raceDir, "go");
  const hold = path.join(raceDir, "release");
  const readyDir = path.join(raceDir, "ready");
  fs.mkdirSync(readyDir);
  if (preseed) fs.writeFileSync(path.join(raceDir, "lease.json"), JSON.stringify(preseed));
  const kids = Array.from({ length: n }, () =>
    spawn(process.execPath, ["--input-type=module", "-e", kid, raceDir, barrier, readyDir, hold]));
  const outs = [];
  const errs = [];
  let exited = 0;
  const done = Promise.all(kids.map(k => new Promise(res => {
    k.stdout.on("data", d => { k.out = (k.out ?? "") + d; });
    k.stderr.on("data", d => { k.err = (k.err ?? "") + d; });
    k.on("exit", () => { outs.push(k.out ?? ""); errs.push(k.err ?? ""); exited++; res(); });
  })));
  // Every child must already be spinning when the barrier appears — otherwise
  // the "race" degenerates into sequential acquisitions.
  const deadline = Date.now() + 30_000;
  while (fs.readdirSync(readyDir).length < n && exited === 0 && Date.now() < deadline) {
    await new Promise(res => setTimeout(res, 5));
  }
  assert.equal(fs.readdirSync(readyDir).length, n,
    `all ${n} lease-race children must be spinning before the barrier; stderr: ${errs.join(" | ")}`);
  fs.writeFileSync(barrier, "");
  // Every child must have ANSWERED before any of them may exit.
  while (kids.filter(k => (k.out ?? "").includes("\n")).length < n && exited === 0 && Date.now() < deadline) {
    await new Promise(res => setTimeout(res, 5));
  }
  const answered = kids.map(k => k.out ?? "").filter(o => o.includes("\n"));
  assert.equal(answered.length, n,
    `all ${n} children must answer while holding; stderr: ${kids.map(k => k.err ?? "").join(" | ")}`);
  const results = answered.map(o => JSON.parse(o));
  const leaseFileEarly = path.join(raceDir, "lease.json");
  const leasePidEarly = fs.existsSync(leaseFileEarly)
    ? JSON.parse(fs.readFileSync(leaseFileEarly, "utf8")).pid : null;
  const tokensEarly = fs.readdirSync(raceDir).filter(f => f.includes(".break-"));
  fs.writeFileSync(hold, "");
  await done;
  const winners = results.filter(r => r.res.ok === true).map(r => r.pid);
  // Lease + token state is read while every child is still holding, so the
  // observation is of the race's real end state, not of post-exit debris.
  return { raceDir, winners, leasePid: leasePidEarly, tokens: tokensEarly };
}

// Repeat locally with LEASE_RACE_ITERS to hunt low-probability interleavings.
const ITERS = Number(process.env.LEASE_RACE_ITERS || 2);
for (let i = 0; i < ITERS; i++) {
  const r = await leaseRace(2, null);
  assert.equal(r.winners.length, 1, `lease race: expected exactly 1 winner, got ${r.winners.length}`);
  assert.equal(r.leasePid, r.winners[0], "surviving lease does not belong to the declared winner");

  // Preseeded DEAD lease: every child must break it, and the break itself must
  // be atomic — two breakers that each delete the other's fresh live lease
  // produce two winners and a lease owned by the loser.
  const d = await leaseRace(6, { pid: 999999, at: 0 });
  assert.equal(d.winners.length, 1, `dead-lease break race: expected exactly 1 winner, got ${d.winners.length}`);
  assert.equal(d.leasePid, d.winners[0], "surviving lease does not belong to the declared winner");
  assert.deepEqual(d.tokens, [], "break token left behind");
}

// releaseLease ownership: a process that does NOT hold the lease must not remove it
const ownDir = fs.mkdtempSync(path.join(os.tmpdir(), "wfo-"));
fs.writeFileSync(path.join(ownDir, "lease.json"), JSON.stringify({ pid: 999998, at: 0 }));
releaseLease(ownDir);             // not ours (pid differs) → must be a no-op
assert.ok(fs.existsSync(path.join(ownDir, "lease.json")), "releaseLease removed a lease it does not own");

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
