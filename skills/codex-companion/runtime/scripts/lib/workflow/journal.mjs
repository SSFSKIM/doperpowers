import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

export function cacheKey(kind, label, payload) {
  const h = crypto.createHash("sha256").update(JSON.stringify(payload)).digest("hex").slice(0, 16);
  return `${kind}|${label ?? ""}|${h}`;
}

export function appendEvent(journalPath, event) {
  fs.appendFileSync(journalPath, `${JSON.stringify({ at: new Date().toISOString(), ...event })}\n`);
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

export function acquireLease(runDir) {
  const p = leasePath(runDir);
  // Atomic create — the ONLY way in; never check-then-write. The lease is
  // written to a private temp file first and hard-linked into place, so a
  // racing reader can never observe a created-but-empty lease (an O_EXCL
  // create followed by a separate write leaves exactly that window, and a
  // reader that finds it unparseable would break a live lease).
  for (let attempt = 0; attempt < 2; attempt++) {
    const tmp = `${p}.${process.pid}.${attempt}.tmp`;
    try {
      fs.writeFileSync(tmp, JSON.stringify({ pid: process.pid, at: Date.now() }), { flag: "wx" });
      fs.linkSync(tmp, p);
      return { ok: true };
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
      let holder = null;
      try { holder = JSON.parse(fs.readFileSync(p, "utf8")); } catch { holder = null; }
      if (holder?.pid && alive(holder.pid)) return { ok: false, holderPid: holder.pid };
      // dead or corrupt holder: remove and try the atomic create once more
      try { fs.rmSync(p, { force: true }); } catch { /* another breaker won */ }
    } finally {
      try { fs.rmSync(tmp, { force: true }); } catch { /* best effort */ }
    }
  }
  return { ok: false };
}

export function releaseLease(runDir) {
  // Ownership check: only the holder may release.
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
