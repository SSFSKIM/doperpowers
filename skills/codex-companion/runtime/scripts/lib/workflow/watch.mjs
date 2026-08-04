import fs from "node:fs";
import path from "node:path";
import { loadJournal } from "./journal.mjs";

// Read-only viewer over a workflow run directory. Everything here derives from
// the artifacts the engine already writes — journal.jsonl, lease.json,
// result.json — so watching never touches the lease and is safe against a live
// run, and the same code renders a finished run post-mortem.

export function reduceJournal(events) {
  const timeline = [];
  const byKey = new Map();
  for (const ev of events) {
    if (ev.type === "log") {
      timeline.push({ type: "log", at: ev.at, message: ev.message });
      continue;
    }
    if (!ev.key) continue;
    let row = byKey.get(ev.key);
    if (!row) {
      row = { type: "call", key: ev.key, kind: ev.kind, label: ev.label, retries: 0 };
      byKey.set(ev.key, row);
      timeline.push(row);
    }
    switch (ev.type) {
      case "started":
        // A resume re-runs a journaled failure under the same key: the fresh
        // `started` supersedes the old outcome, so the row goes back to running
        // and the clock restarts.
        row.state = "running";
        row.startedAt = ev.at;
        row.finishedAt = undefined;
        row.error = undefined;
        row.resultPreview = undefined;
        if (ev.kind) row.kind = ev.kind;
        if (ev.label !== undefined) row.label = ev.label;
        break;
      case "retry":
        row.retries += 1;
        break;
      case "finished":
        row.finishedAt = ev.at;
        if (ev.error !== undefined) {
          row.state = "failed";
          row.error = String(ev.error);
        } else {
          row.state = "done";
          row.resultPreview = previewOf(ev.result);
        }
        break;
    }
  }
  return timeline;
}

function previewOf(result) {
  if (result === undefined) return "";
  if (typeof result === "string") return result.replace(/\s+/g, " ").trim();
  try { return JSON.stringify(result); } catch { return String(result); }
}

export function runState(runDir) {
  const resultPath = path.join(runDir, "result.json");
  if (fs.existsSync(resultPath)) {
    // result.json is written exactly once, when the script returned — a stale
    // lease next to it just means we looked mid-release. Completed wins.
    let result = null;
    try { result = JSON.parse(fs.readFileSync(resultPath, "utf8")); } catch { /* torn write */ }
    return { state: "completed", result };
  }
  let lease = null;
  try { lease = JSON.parse(fs.readFileSync(path.join(runDir, "lease.json"), "utf8")); } catch { /* absent/corrupt */ }
  if (lease?.pid && pidAlive(lease.pid)) return { state: "running" };
  return { state: "interrupted" };
}

function pidAlive(pid) {
  try { process.kill(pid, 0); return true; }
  catch (err) { return err.code === "EPERM"; }   // exists, owned by someone else
}

const SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const COLORS = { green: "32", red: "31", yellow: "33", cyan: "36", dim: "2" };

export function renderFrame({ runId, state, timeline, now, width = 100, color = false }) {
  const paint = (text, c) => (color ? `\x1b[${COLORS[c]}m${text}\x1b[0m` : text);
  const spin = SPINNER[Math.floor(now / 100) % SPINNER.length];

  const calls = timeline.filter((it) => it.type === "call");
  const counts = { done: 0, running: 0, failed: 0 };
  for (const c of calls) counts[c.state] = (counts[c.state] ?? 0) + 1;

  const firstAt = timeline.find((it) => it.at ?? it.startedAt);
  const startMs = Date.parse(calls[0]?.startedAt ?? firstAt?.at ?? "") || now;
  const stateColor = state === "completed" ? "green" : state === "running" ? "cyan" : "yellow";
  const header =
    `${runId}  ${paint(state, stateColor)}  ${fmtDur(now - startMs)}  ` +
    `[${counts.done} done · ${counts.running} running · ${counts.failed} failed]`;

  const lines = [header];
  const labelWidth = Math.min(24, Math.max(5, ...calls.map((c) => String(c.label ?? "").length)));
  for (const item of timeline) {
    if (item.type === "log") {
      lines.push(paint(`  ── ${item.message}`, "dim"));
      continue;
    }
    const glyph =
      item.state === "done" ? paint("✓", "green")
      : item.state === "failed" ? paint("✗", "red")
      : paint(spin, "cyan");
    const elapsed = fmtDur(
      (item.finishedAt ? Date.parse(item.finishedAt) : now) - Date.parse(item.startedAt)
    );
    const retryMark = item.retries ? paint(` ↻${item.retries}`, "yellow") : "";
    const tail = item.state === "failed" ? paint(item.error ?? "", "red") : (item.resultPreview ?? "");
    const row =
      `  ${glyph} ${String(item.label ?? "").padEnd(labelWidth)} ` +
      `${String(item.kind ?? "").padEnd(6)} ${fmtDur.pad(elapsed)}${retryMark}  ${tail}`;
    lines.push(row);
  }
  return lines.map((l) => truncate(l, width, color)).join("\n");
}

function fmtDur(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return `${m}:${String(r).padStart(2, "0")}`;
  const h = Math.floor(m / 60);
  return `${h}:${String(m % 60).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}
fmtDur.pad = (str) => str.padStart(7);

// Width control that never cuts an ANSI sequence in half: measure and slice on
// visible characters, then re-close the paint at the cut.
function truncate(line, width, color) {
  if (!color) return line.length <= width ? line : `${line.slice(0, width - 1)}…`;
  let visible = 0, out = "", i = 0, cut = false;
  while (i < line.length) {
    if (line[i] === "\x1b") {
      const end = line.indexOf("m", i);
      if (end === -1) break;
      out += line.slice(i, end + 1);
      i = end + 1;
      continue;
    }
    if (visible >= width - 1) { cut = true; break; }
    out += line[i];
    visible += 1;
    i += 1;
  }
  return cut ? `${out}…\x1b[0m` : out;
}

export async function watchLoop({ runDir, runId, out, intervalMs = 500, once = false }) {
  const journalPath = path.join(runDir, "journal.jsonl");
  const isTty = Boolean(out.isTTY);
  const width = isTty ? (out.columns ?? 100) : 200;
  let prevLines = 0;

  const frameOnce = () => {
    const { state } = runState(runDir);
    const timeline = reduceJournal(loadJournal(journalPath).events);
    const frame = renderFrame({ runId, state, timeline, now: Date.now(), width, color: isTty });
    if (isTty && prevLines > 0) out.write(`\x1b[${prevLines}A\x1b[0J`);
    out.write(frame + "\n");
    prevLines = frame.split("\n").length;
    return state;
  };

  let state = frameOnce();
  if (once || !isTty) return state;
  while (state === "running") {
    await new Promise((r) => setTimeout(r, intervalMs));
    state = frameOnce();
  }
  return state;
}
