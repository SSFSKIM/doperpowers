// The workflow engine: it hands a workflow script a small set of hooks
// (agent/review/parallel/pipeline/log), caps how many Codex app-servers can be
// alive at once, and records every leaf call in a journal so an interrupted run
// can be resumed instead of re-paid for.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { runAppServerTurn, runAppServerReview, parseStructuredOutput, resolveReviewTarget } from "../codex.mjs";
import { validateSchema } from "./validate.mjs";
import {
  cacheKey, appendEvent, loadJournal, sealJournal, acquireLease, releaseLease,
  repoFingerprint, reviewTargetCommit, FINGERPRINT_ERROR_PREFIX
} from "./journal.mjs";

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

// "JSON value", not "JSON object": an array-root schema is supported (and
// documented in references/workflows.md), and demanding an object would tell the
// model to contradict its own schema — repairable output failing terminally.
const REPAIR_PROMPT = (errors) =>
  `Your previous output failed schema validation: ${errors.join("; ")}. ` +
  `Re-emit ONLY the corrected JSON value matching the schema, nothing else.`;

export async function runWorkflow(spec) {
  const t0 = Date.now();
  const runDir = spec.runDir;
  fs.mkdirSync(runDir, { recursive: true });
  const lease = acquireLease(runDir);
  if (!lease.ok) throw new WorkflowError("lease-held", `run is leased by pid ${lease.holderPid}`);
  const journalPath = path.join(runDir, "journal.jsonl");
  const workersPath = path.join(runDir, "workers.json");
  const fpPath = path.join(runDir, "fingerprint");
  // Once per run: repoFingerprint shells out per untracked file. The script
  // path rides extraPaths so editing an out-of-tree (ad-hoc) workflow script
  // also refuses a stale-cache resume; in-tree scripts are covered twice,
  // which is harmless.
  // A fingerprint that could not be TAKEN is recorded as such. It must never
  // compare equal to anything — including the identical failure on a later run,
  // which is exactly how a fail-open constant let a resume replay stale results.
  // The ARGS are part of the run's identity, not just of the script's inputs:
  // a leaf is keyed by its payload plus which occurrence of that identity it is
  // within this run, so args that drop an earlier identical call shift every
  // later occurrence down one and hand it a result generated for a different
  // call. Folding them in refuses that resume instead of mixing the two.
  let fp;
  try {
    const repo = repoFingerprint(spec.cwd, [path.resolve(spec.scriptPath)]);
    fp = crypto.createHash("sha256")
      .update([repo, JSON.stringify(spec.args ?? null)].join("\x00"))
      .digest("hex").slice(0, 16);
  } catch (err) {
    fp = `${FINGERPRINT_ERROR_PREFIX}${err?.message ?? err}`;
  }
  try {
    // The previous run may have died mid-append: close its half-written line
    // before this one starts appending, or the first event we write joins it.
    sealJournal(journalPath);
    const { events, finished } = loadJournal(journalPath);
    if (spec.resume) {
      const recorded = fs.existsSync(fpPath) ? fs.readFileSync(fpPath, "utf8") : null;
      const unusable = [recorded, fp].find((value) => value?.startsWith(FINGERPRINT_ERROR_PREFIX));
      if (unusable) {
        throw new WorkflowError("fingerprint-mismatch",
          `repository fingerprint is unavailable (${unusable}); re-run fresh instead of resuming`);
      }
      if (recorded && recorded !== fp) {
        throw new WorkflowError("fingerprint-mismatch",
          `repo, workflow script or args changed since the original run (${recorded} → ${fp}); re-run fresh instead of resuming`);
      }
      // No recorded fingerprint and a journal to replay: nothing says the code
      // behind those results is the code here now. Adopting the current
      // fingerprint would BLESS whatever this tree happens to be and then serve
      // successes produced against the old one — deleting one file would be the
      // whole attack. Re-fingerprinting is only honest when there is no history.
      if (!recorded && events.length > 0) {
        throw new WorkflowError("fingerprint-mismatch",
          "this run has journaled history but no recorded fingerprint, so the code behind it cannot be " +
          "confirmed; re-run fresh instead of resuming");
      }
      if (!recorded) fs.writeFileSync(fpPath, fp);
    } else {
      fs.writeFileSync(fpPath, fp);
    }
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

    // The run-level fingerprint covers spec.cwd only. A hook pointed at ANOTHER
    // repository through the documented per-call `cwd` would otherwise cache-hit
    // across every change to it, so that repository's identity rides the call's
    // own cache key. Memoized: repoFingerprint shells out once per untracked file.
    const perCwdFingerprints = new Map();
    const cwdFingerprint = (cwd) => {
      if (!cwd) return null;
      const resolved = path.resolve(cwd);
      if (resolved === path.resolve(spec.cwd)) return null; // already in the run fingerprint
      if (!perCwdFingerprints.has(resolved)) {
        let value;
        try {
          value = repoFingerprint(resolved);
        } catch (err) {
          value = `${FINGERPRINT_ERROR_PREFIX}${err?.message ?? err}`;
        }
        perCwdFingerprints.set(resolved, value);
      }
      return perCwdFingerprints.get(resolved);
    };

    // A call whose repository identity could not be ESTABLISHED must not be
    // cacheable at all. `error:<msg>` is a stable string, so a later run failing
    // the same way would key identically and be served a result produced from
    // files nobody can compare — the run-level guard refuses that resume
    // outright, and a per-call one has to be at least as strict. The nonce is
    // per-run, so no journal key written by any other run can ever match it.
    const runNonce = crypto.randomUUID();
    const degraded = (value) => typeof value === "string" && value.startsWith(FINGERPRINT_ERROR_PREFIX);
    const identify = (payload, label, cwd, resolveFailed = false) => {
      const fingerprint = cwdFingerprint(cwd);
      const stamped = { ...payload, cwdFingerprint: fingerprint };
      if (!degraded(fingerprint) && !resolveFailed) {
        return stamped;
      }
      emit(`fingerprint-degraded ${label ?? "(unlabeled)"}`);
      return { ...stamped, uncacheable: runNonce };
    };

    const hooks = {
      args: spec.args,
      log: (m) => { appendEvent(journalPath, { type: "log", message: String(m) }); emit(`log ${m}`); },

      agent: (prompt, opts = {}) =>
        leafCall("agent", opts.label, identify({ prompt, opts: sanitize(opts) }, opts.label, opts.cwd), async (onSpawn, key) => {
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

      review: (opts = {}) => {
        // Resolved BEFORE the cache key is built, not inside the call: a ref
        // moves, so `{base:"main"}` can name a completely different diff on a
        // later run while the opts object stays byte-identical. The resolved
        // commit is what the cache must be keyed on.
        // runAppServerReview sends options.target to review/start verbatim — it
        // has no base/scope params — so the hook resolves the target the same
        // way the /codex:review verb does.
        const reviewCwd = opts.cwd ?? spec.cwd;
        let target = null;
        let targetCommit = null;
        let resolveError = null;
        try {
          target = resolveReviewTarget(reviewCwd, { base: opts.base, scope: opts.scope });
          targetCommit = reviewTargetCommit(reviewCwd, target);
        } catch (err) {
          // Deferred, not thrown here: a resolution failure stays a LEAF failure,
          // journaled and retried like any other, exactly as it was when the
          // resolution lived inside the call.
          resolveError = err;
        }
        return leafCall("review", opts.label, identify(
          { opts: sanitize(opts), targetCommit },
          opts.label,
          opts.cwd,
          Boolean(resolveError)   // an unresolvable target is an unknown identity too
        ), async (onSpawn) => {
          if (resolveError) throw resolveError;
          const overrides = [];
          if (opts.effort) overrides.push(`model_reasoning_effort=${opts.effort}`);
          if (opts.lens) overrides.push(`developer_instructions=${opts.lens}`);
          const res = await runAppServerReview(opts.cwd ?? spec.cwd, {
            model: opts.model, target,
            connect: { disableBroker: true, configOverrides: overrides, onSpawn }
          });
          assertTurnUsable(res, "review");
          if (!res.reviewText?.trim()) throw new Error("review returned no output");
          // review/start takes the SYMBOLIC target — it has no commit parameter —
          // so the worker reviewed whatever the ref pointed at when it read the
          // diff, which need not be the commit this call is keyed on: the ref can
          // move during the semaphore wait, between transport attempts, or while
          // the worker runs. Re-resolve and fail the leaf rather than journal a
          // report about one range under a key that names another.
          const after = reviewTargetCommit(reviewCwd, target);
          if (after !== targetCommit) {
            throw new Error(
              `review target moved while the review ran (${targetCommit} → ${after}); ` +
              "the report describes a different range than this run journaled"
            );
          }
          return { reviewText: res.reviewText, threadId: res.threadId, status: res.status };
        });
      },

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
  // A full cryptographic hash, not length-plus-prefix: two schemas of the same
  // length differing after byte 64 collided, and a resume serves the cached
  // result BEFORE validating it against the current schema — so output valid
  // under the old schema would be handed back under the new one.
  return {
    ...rest,
    schemaHash: schema ? crypto.createHash("sha256").update(JSON.stringify(schema)).digest("hex") : null
  };
}
