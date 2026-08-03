import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

export function cacheKey(kind, label, payload) {
  const h = crypto.createHash("sha256").update(JSON.stringify(payload)).digest("hex").slice(0, 16);
  // `|` is the field separator, so it is escaped in the fields: otherwise
  // ("agent|x","y") and ("agent","x|y") would be the same cache entry.
  const esc = (s) => String(s ?? "").replaceAll("|", "%7C");
  return `${esc(kind)}|${esc(label)}|${h}`;
}

export function appendEvent(journalPath, event) {
  fs.appendFileSync(journalPath, `${JSON.stringify({ at: new Date().toISOString(), ...event })}\n`);
}

// A run killed mid-append leaves a last line with no newline. loadJournal drops
// that torn line, but an append onto it would GLUE the next event to the wreck
// and lose that one too — the tolerance has to be contained to the torn line, so
// close it before anything else writes.
export function sealJournal(journalPath) {
  let fd;
  try { fd = fs.openSync(journalPath, "r+"); }
  catch { return; }                                    // nothing journaled yet
  try {
    const size = fs.fstatSync(fd).size;
    if (size === 0) return;
    const last = Buffer.alloc(1);
    fs.readSync(fd, last, 0, 1, size - 1);
    if (last[0] !== 0x0a) fs.writeSync(fd, "\n", size);
  } finally { fs.closeSync(fd); }
}

export function loadJournal(journalPath) {
  const events = [];
  const finished = new Map();
  if (!fs.existsSync(journalPath)) return { events, finished };
  for (const line of fs.readFileSync(journalPath, "utf8").split("\n")) {
    if (!line.trim()) continue;
    let ev; try { ev = JSON.parse(line); } catch { continue; }   // torn tail tolerance
    events.push(ev);
    if (ev.type === "finished" && ev.key) finished.set(ev.key, ev);
  }
  return { events, finished };
}

function leasePath(runDir) { return path.join(runDir, "lease.json"); }

function alive(pid) {
  try { process.kill(pid, 0); return true; }
  catch (err) { return err.code === "EPERM"; }   // EPERM: exists, owned by someone else
}

function readJson(p) {
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; }
}

// The four states a lease file can be in. "absent" must stay distinct from
// "corrupt": a lease that is momentarily gone is a breaker mid-swap, and
// treating that as breakable is how a fresh LIVE lease gets deleted.
function inspect(p) {
  let raw;
  try { raw = fs.readFileSync(p, "utf8"); }
  catch (err) { if (err.code === "ENOENT") return { state: "absent" }; throw err; }
  let rec = null;
  try { rec = JSON.parse(raw); } catch { /* corrupt */ }
  if (!rec?.pid) return { state: "corrupt" };
  return { state: alive(rec.pid) ? "live" : "dead", pid: rec.pid };
}

// Atomic create — the ONLY way to become the holder; never check-then-write.
// The record is written to a private temp file and hard-linked into place, so
// a racing reader can never observe a created-but-empty file (an O_EXCL create
// followed by a separate write leaves exactly that window, and a reader that
// found it unparseable would break a live lease).
function claim(p, tag) {
  const tmp = `${p}.${process.pid}.${tag}.tmp`;
  try {
    fs.writeFileSync(tmp, JSON.stringify({ pid: process.pid, at: Date.now() }), { flag: "wx" });
    fs.linkSync(tmp, p);
    return true;
  } catch (err) {
    if (err.code !== "EEXIST") throw err;
    return false;
  } finally {
    try { fs.rmSync(tmp, { force: true }); } catch { /* best effort */ }
  }
}

export function acquireLease(runDir) {
  const p = leasePath(runDir);
  for (let attempt = 0; attempt < 4; attempt++) {
    if (claim(p, attempt)) return { ok: true };
    const holder = inspect(p);
    if (holder.state === "live") return { ok: false, holderPid: holder.pid };
    if (holder.state === "absent") continue;   // vanished under us; just retry the claim

    // Holder is dead or corrupt. BREAKING MUST ALSO BE ATOMIC: two breakers
    // that both read the same dead pid would take turns deleting each other's
    // freshly linked LIVE lease, yielding two winners and a lease owned by the
    // loser. Serialize on a break token keyed to the observed holder, held
    // across the removal AND the relink.
    const token = `${p}.break-${holder.pid ?? "corrupt"}`;
    if (!claim(token, attempt)) {
      // Token held: its owner is breaking right now (retry and we will see
      // their lease) or died mid-break (clear the wedge so it cannot pin
      // acquisition forever).
      const breaker = readJson(token);
      if (!breaker?.pid || !alive(breaker.pid)) {
        try { fs.rmSync(token, { force: true }); } catch { /* another retrier cleared it */ }
      }
      continue;
    }
    try {
      // Re-inspect under the token: the lease may have been broken and retaken
      // since the read above. Only a still-dead/corrupt record may be removed.
      const current = inspect(p);
      if (current.state === "live") return { ok: false, holderPid: current.pid };
      if (current.state !== "absent") {
        try { fs.rmSync(p, { force: true }); } catch { /* already gone */ }
      }
      if (claim(p, `break${attempt}`)) return { ok: true };
    } finally {
      try { fs.rmSync(token, { force: true }); } catch { /* best effort */ }
    }
  }
  return { ok: false };
}

export function releaseLease(runDir) {
  // Ownership check: only the holder may release. The read and the unlink are
  // not one atomic step, but nobody may replace a lease whose pid is alive —
  // and ours is, since we are the one running — so the window is not reachable.
  const p = leasePath(runDir);
  try {
    const holder = JSON.parse(fs.readFileSync(p, "utf8"));
    if (holder?.pid !== process.pid) return;
  } catch { return; }
  fs.rmSync(p, { force: true });
}

export function repoFingerprint(cwd, extraPaths = []) {
  // Content-aware: porcelain alone records paths+status, not bytes — a
  // dirty file edited again between runs would slip through. Hash HEAD,
  // the full content diff vs HEAD, every untracked file's blob hash, and
  // any extra file identities the caller cares about (workflow script).
  try {
    const run = (args) => execFileSync("git", args, { cwd, stdio: ["ignore", "pipe", "ignore"], maxBuffer: 64 * 1024 * 1024 }).toString();
    const head = run(["rev-parse", "HEAD"]);
    const diff = run(["diff", "HEAD"]);
    const untracked = run(["ls-files", "--others", "--exclude-standard"]).split("\n").filter(Boolean).sort();
    const untrackedHashes = untracked.map((f) => {
      try { return f + ":" + execFileSync("git", ["hash-object", "--", f], { cwd, stdio: ["ignore", "pipe", "ignore"] }).toString().trim(); }
      catch { return f + ":unreadable"; }
    });
    const extras = extraPaths.map((p) => {
      try { return p + ":" + crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex").slice(0, 12); }
      catch { return p + ":unreadable"; }
    });
    return crypto.createHash("sha256")
      .update([head, diff, untrackedHashes.join("\n"), extras.join("\n")].join("\x00"))
      .digest("hex").slice(0, 16);
  } catch {
    return "no-git";
  }
}
