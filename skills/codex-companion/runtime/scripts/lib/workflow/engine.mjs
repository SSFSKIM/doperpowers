// The workflow engine: it hands a workflow script a small set of hooks
// (agent/review/parallel/pipeline/log), caps how many Codex app-servers can be
// alive at once, and records every leaf call in a journal so an interrupted run
// can be resumed instead of re-paid for.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { runAppServerTurn, runAppServerReview, parseStructuredOutput, resolveReviewTarget } from "../codex.mjs";
import { validateSchema } from "./validate.mjs";
import { cacheKey, appendEvent, loadJournal, sealJournal, acquireLease, releaseLease, repoFingerprint } from "./journal.mjs";

export class WorkflowError extends Error {
  constructor(reason, message) { super(message); this.reason = reason; }
}

class Semaphore {
  constructor(n) { this.free = n; this.queue = []; }
  async acquire() {
    if (this.free > 0) { this.free -= 1; return; }
    await new Promise((res) => this.queue.push(res));
  }
  release() {
    const next = this.queue.shift();
    if (next) next(); else this.free += 1;
  }
}

// buildResultStatus (codex.mjs) is `finalTurn?.status === "completed" ? 0 : 1` —
// an exit-style code, so 0 is the ONLY success value. A turn that completed with
// status "failed", and a turn whose completion had to be inferred (finalTurn
// null), both report 1 with `error` still null: checking `.error` alone
// false-greens exactly those.
const isSuccessStatus = (status) => status === 0;

const REPAIR_PROMPT = (errors) =>
  `Your previous output failed schema validation: ${errors.join("; ")}. ` +
  `Re-emit ONLY the corrected JSON object, nothing else.`;

export async function runWorkflow(spec) {
  const t0 = Date.now();
  const runDir = spec.runDir;
  fs.mkdirSync(runDir, { recursive: true });
  const lease = acquireLease(runDir);
  if (!lease.ok) throw new WorkflowError("lease-held", `run is leased by pid ${lease.holderPid}`);
  const journalPath = path.join(runDir, "journal.jsonl");
  const workersPath = path.join(runDir, "workers.json");
  const fpPath = path.join(runDir, "fingerprint");
  // Once per run: repoFingerprint shells out per untracked file.
  const fp = repoFingerprint(spec.cwd);
  try {
    if (spec.resume) {
      const recorded = fs.existsSync(fpPath) ? fs.readFileSync(fpPath, "utf8") : null;
      if (recorded && recorded !== fp) {
        throw new WorkflowError("fingerprint-mismatch",
          `repo changed since the original run (${recorded} → ${fp}); re-run fresh instead of resuming`);
      }
      // A run interrupted before it recorded a fingerprint has nothing to compare
      // against. Record the current one now rather than leaving the drift guard
      // off for every later resume of this run dir.
      if (!recorded) fs.writeFileSync(fpPath, fp);
    } else {
      fs.writeFileSync(fpPath, fp);
    }
    // The previous run may have died mid-append: close its half-written line
    // before this one starts appending, or the first event we write joins it.
    sealJournal(journalPath);
    const { finished } = loadJournal(journalPath);
    const occurrences = new Map();          // base key → count issued this run
    const liveWorkers = new Set();
    const saveWorkers = () => fs.writeFileSync(workersPath, JSON.stringify([...liveWorkers]));
    const sem = new Semaphore(spec.maxConcurrency ?? 6);
    let agents = 0;
    const emit = spec.emit ?? (() => {});

    // A failed exec reports no pid; tracking that would leave a `null` in
    // workers.json for the cancel path to signal.
    const trackSpawn = (pid) => { if (typeof pid !== "number") return; liveWorkers.add(pid); saveWorkers(); };
    const untrack = (pid) => { if (typeof pid !== "number") return; liveWorkers.delete(pid); saveWorkers(); };

    async function leafCall(kind, label, payload, exec) {
      const base = cacheKey(kind, label, payload);
      const n = occurrences.get(base) ?? 0;
      occurrences.set(base, n + 1);
      const key = `${base}#${n}`;
      // The cache serves SUCCESSES only. A journaled failure falls through to a
      // live re-run: resume exists to recover a crashed run, and replaying a
      // transient worker death would mean a lost result can never be regained.
      // A deterministic failure merely re-fails, bounded by the transport retry.
      // The occurrence counter above still consumed this key either way, so
      // later identical calls stay aligned with the journal.
      if (finished.has(key)) {
        const hit = finished.get(key);
        if (!hit.error) {
          emit(`cache ${kind}:${label ?? ""}`);
          return hit.result;
        }
        emit(`cache-skip ${kind}:${label ?? ""}`);
      }
      await sem.acquire();
      appendEvent(journalPath, { type: "started", key, kind, label });
      agents += 1;
      emit(`start ${kind}:${label ?? ""}`);
      const callPids = [];                       // EVERY spawn of this call (retries + repair turns)
      const onSpawn = (pid) => { callPids.push(pid); trackSpawn(pid); };
      try {
        const attempt = () => exec(onSpawn, key);
        let out;
        try {
          out = await attempt();
        } catch (e1) {
          if (e1?.terminal) throw e1;            // schema-repair exhaustion etc: NEVER a third attempt
          appendEvent(journalPath, { type: "retry", key, error: String(e1?.message ?? e1) });
          emit(`retry ${kind}:${label ?? ""}`);
          out = await attempt();                 // one automatic transport retry, fresh turn
        }
        appendEvent(journalPath, { type: "finished", key, result: out });
        emit(`done ${kind}:${label ?? ""}`);
        return out;
      } catch (err) {
        appendEvent(journalPath, { type: "finished", key, error: String(err?.message ?? err) });
        emit(`fail ${kind}:${label ?? ""}`);
        throw err;
      } finally {
        for (const pid of callPids) untrack(pid);  // no stale pids: cancel must never signal a reused pid
        sem.release();
      }
    }

    function assertTurnUsable(turn, what) {
      if (turn.error) throw new Error(turn.error.message ?? `${what} failed`);
      if (!isSuccessStatus(turn.status)) throw new Error(`${what} completed unsuccessfully (status ${JSON.stringify(turn.status)})`);
    }

    const hooks = {
      args: spec.args,
      log: (m) => { appendEvent(journalPath, { type: "log", message: String(m) }); emit(`log ${m}`); },

      agent: (prompt, opts = {}) =>
        leafCall("agent", opts.label, { prompt, opts: sanitize(opts) }, async (onSpawn, key) => {
          // No -c overrides on this lane: model and effort ride the turn params.
          const connect = { disableBroker: true, onSpawn };
          const turn = await runAppServerTurn(opts.cwd ?? spec.cwd, {
            prompt, model: opts.model, effort: opts.effort,
            sandbox: "read-only", persistThread: true,
            outputSchema: opts.schema ?? null, connect
          });
          assertTurnUsable(turn, "agent turn");
          if (!opts.schema) {
            if (!turn.finalMessage?.trim()) throw new Error("agent turn returned no output");
            return turn.finalMessage;
          }
          let parsed = parseStructuredOutput(turn.finalMessage);
          let errors = parsed.parseError ? [parsed.parseError] : validateSchema(parsed.parsed, opts.schema);
          if (errors.length === 0) return parsed.parsed;
          appendEvent(journalPath, { type: "retry", key, reason: "schema-repair", label: opts.label, errors });
          const repair = await runAppServerTurn(opts.cwd ?? spec.cwd, {
            prompt: REPAIR_PROMPT(errors), resumeThreadId: turn.threadId,
            model: opts.model, effort: opts.effort, sandbox: "read-only",
            outputSchema: opts.schema, connect
          });
          assertTurnUsable(repair, "schema repair turn");
          parsed = parseStructuredOutput(repair.finalMessage);
          errors = parsed.parseError ? [parsed.parseError] : validateSchema(parsed.parsed, opts.schema);
          if (errors.length > 0) {
            throw Object.assign(
              new Error(`schema validation failed after repair: ${errors.join("; ")}`),
              { terminal: true });   // exactly two turns — the transport retry must NOT grant a third
          }
          return parsed.parsed;
        }),

      review: (opts = {}) =>
        leafCall("review", opts.label, { opts: sanitize(opts) }, async (onSpawn) => {
          const overrides = [];
          if (opts.effort) overrides.push(`model_reasoning_effort=${opts.effort}`);
          if (opts.lens) overrides.push(`developer_instructions=${opts.lens}`);
          // runAppServerReview sends options.target to review/start verbatim — it
          // has no base/scope params — so the hook resolves the target the same
          // way the /codex:review verb does.
          const target = resolveReviewTarget(opts.cwd ?? spec.cwd, { base: opts.base, scope: opts.scope });
          const res = await runAppServerReview(opts.cwd ?? spec.cwd, {
            model: opts.model, target,
            connect: { disableBroker: true, configOverrides: overrides, onSpawn }
          });
          assertTurnUsable(res, "review");
          if (!res.reviewText?.trim()) throw new Error("review returned no output");
          return { reviewText: res.reviewText, threadId: res.threadId, status: res.status };
        }),

      parallel: (thunks) => Promise.all(thunks.map((t) =>
        Promise.resolve().then(t).catch(() => null))),

      pipeline: async (items, ...stages) => Promise.all(items.map(async (item, index) => {
        let acc = item;
        for (const stage of stages) {
          try { acc = await stage(acc, item, index); }
          catch { return null; }
        }
        return acc;
      })),
    };

    const mod = await import(pathToFileURL(path.resolve(spec.scriptPath)).href);
    if (typeof mod.default !== "function") {
      throw new WorkflowError("script-error", "workflow script must export a default async function");
    }
    const result = await mod.default(hooks);
    fs.writeFileSync(path.join(runDir, "result.json"), JSON.stringify(result ?? null, null, 2));
    return { result: result ?? null, agents, durationMs: Date.now() - t0 };
  } finally {
    releaseLease(runDir);
  }
}

function sanitize(opts) {
  const { schema, ...rest } = opts;   // schema objects can be large; hash their JSON separately
  return { ...rest, schemaHash: schema ? JSON.stringify(schema).length + ":" + JSON.stringify(schema).slice(0, 64) : null };
}
