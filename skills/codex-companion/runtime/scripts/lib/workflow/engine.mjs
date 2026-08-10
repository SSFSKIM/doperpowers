// The workflow engine: it hands a workflow script a small set of hooks
// (agent/review/parallel/pipeline/log), caps how many Codex app-servers can be
// alive at once, and records every leaf call in a journal so an interrupted run
// can be resumed instead of re-paid for.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { runAppServerTurn, runAppServerReview, parseStructuredOutput, resolveReviewTarget } from "../codex.mjs";
import { assertSandboxUsable, sandboxFailureLines } from "../sandbox.mjs";
import { processStartTime } from "../pid.mjs";
import { validateSchema } from "./validate.mjs";
import {
  cacheKey, appendEvent, loadJournal, sealJournal, acquireLease, releaseLease,
  repoFingerprint, repoFingerprintParts, reviewTargetCommit,
  FINGERPRINT_ERROR_PREFIX, FINGERPRINT_NOGIT
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
  // The args the run was issued with, recorded so a resume can be given them
  // back: they are part of the run identity, so a resume that has to retype them
  // byte-for-byte is a refusal waiting to happen. The CLI reads this file when
  // `--resume` carries no `--args`.
  const argsPath = path.join(runDir, "args.json");
  // Per-run uniqueness, used wherever an identity could not be ESTABLISHED —
  // by the no-git run fingerprint below and by the per-call degraded key. No
  // journal written by any other run can ever match it.
  const runNonce = crypto.randomUUID();
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
  // Kept as NAMED COMPONENTS rather than one digest: these are four independent
  // causes of a refusal, and a resume that only says "something changed" leaves
  // its caller nothing to check.
  let fp;
  try {
    const repo = repoFingerprintParts(spec.cwd, workflowExtraPaths(spec.scriptPath));
    fp = {
      repoPath: repo.repoPath,
      // A directory with no git has no comparable content at all: the workers
      // read files nothing hashes, so its journaled successes must never be
      // served to a later run. Hashing an arbitrary tree is not worth its cost —
      // the run is stamped single-use instead, and every resume of it refuses.
      repoContent: repo.repoContent === FINGERPRINT_NOGIT
        ? `${FINGERPRINT_NOGIT}:${runNonce}`
        : repo.repoContent,
      code: repo.code,
      args: crypto.createHash("sha256").update(JSON.stringify(spec.args ?? null)).digest("hex").slice(0, 16)
    };
  } catch (err) {
    fp = `${FINGERPRINT_ERROR_PREFIX}${err?.message ?? err}`;
  }
  // Written together: the fingerprint the next resume is compared against, and
  // the args that resume will be handed if it names none.
  const armGuard = () => {
    fs.writeFileSync(fpPath, typeof fp === "string" ? fp : JSON.stringify(fp));
    fs.writeFileSync(argsPath, JSON.stringify(spec.args ?? null));
  };
  try {
    // The previous run may have died mid-append: close its half-written line
    // before this one starts appending, or the first event we write joins it.
    sealJournal(journalPath);
    const { finished } = loadJournal(journalPath);
    if (spec.resume) {
      const raw = fs.existsSync(fpPath) ? fs.readFileSync(fpPath, "utf8") : null;
      const unusable = [raw, fp].find((value) => typeof value === "string" && value.startsWith(FINGERPRINT_ERROR_PREFIX));
      if (unusable) {
        throw new WorkflowError("fingerprint-mismatch",
          `repository fingerprint is unavailable (${unusable}); re-run fresh instead of resuming`);
      }
      if (raw !== null) {
        assertFingerprintMatches(parseFingerprint(raw), fp);
      } else if ([...finished.values()].some((event) => !event.error)) {
        // No recorded fingerprint and journaled SUCCESSES to replay: nothing
        // says the code behind those results is the code here now. Adopting the
        // current fingerprint would BLESS whatever this tree happens to be and
        // then serve results produced against the old one — deleting one file
        // would be the whole attack. Log lines, started markers and journaled
        // failures are not that: a resume can serve none of them, so a journal
        // holding only those may still be re-fingerprinted.
        throw new WorkflowError("fingerprint-mismatch",
          "this run has journaled results but no recorded fingerprint, so the code behind them cannot be " +
          "confirmed; re-run fresh instead of resuming");
      } else {
        armGuard();
      }
    } else {
      armGuard();
    }
    const occurrences = new Map();          // base key → count issued this run
    // pid → its process start time: cancel reads this file, possibly long after
    // a reboot, and a bare pid there is a signal aimed at whoever inherited the
    // number. Stamped at spawn, while the worker is certainly the one we mean.
    const liveWorkers = new Map();
    const saveWorkers = () =>
      fs.writeFileSync(workersPath, JSON.stringify([...liveWorkers].map(([pid, pidStart]) => ({ pid, pidStart }))));
    const sem = new Semaphore(spec.maxConcurrency ?? 6);
    let agents = 0;
    const emit = spec.emit ?? (() => {});

    // A failed exec reports no pid; tracking that would leave a `null` in
    // workers.json for the cancel path to signal.
    const trackSpawn = (pid) => { if (typeof pid !== "number") return; liveWorkers.set(pid, processStartTime(pid)); saveWorkers(); };
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
          // A dead app-server's protocol error carries the child's buffered
          // stderr, so the same fail-closed guard applies to it: a sandbox
          // marker here is the structural failure, not a transport one, and
          // retrying it risks journaling a result the second turn produced
          // with the sandbox still broken.
          guardSandbox(label, String(e1?.message ?? e1));
          appendEvent(journalPath, { type: "retry", key, error: String(e1?.message ?? e1) });
          emit(`retry ${kind}:${label ?? ""}`);
          out = await attempt();                 // one automatic transport retry, fresh turn
        }
        appendEvent(journalPath, { type: "finished", key, result: out });
        emit(`done ${kind}:${label ?? ""}`);
        return out;
      } catch (err) {
        emitSandboxDiagnostics(label, String(err?.message ?? err));
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
    // cacheable at all. `error:<msg>` and `no-git:<digest>` are both stable
    // strings, so a later run in the same state would key identically and be
    // served a result produced from files nobody compared — a non-repository
    // directory hashes its path and the workflow script, never the files the
    // worker actually read there. The run-level guard refuses such a resume
    // outright, and a per-call one has to be at least as strict.
    const degraded = (value) => typeof value === "string"
      && (value.startsWith(FINGERPRINT_ERROR_PREFIX) || value.startsWith(`${FINGERPRINT_NOGIT}:`));
    const identify = (payload, label, cwd, resolveFailed = false) => {
      const fingerprint = cwdFingerprint(cwd);
      const stamped = { ...payload, cwdFingerprint: fingerprint };
      if (!degraded(fingerprint) && !resolveFailed) {
        return stamped;
      }
      emit(`fingerprint-degraded ${label ?? "(unlabeled)"}`);
      return { ...stamped, uncacheable: runNonce };
    };

    // The app-server buffers its child's stderr and surfaces it only on a
    // nonzero exit, but the observed fs-sandbox failure (bwrap RTM_NEWADDR —
    // ida-worker-1, 2026-08-09) exits 0 and renders findings anyway. Every
    // leaf therefore fails closed on that buffered stderr (lib/sandbox.mjs) —
    // checked BEFORE the leaf's own success check, so a "successful" turn
    // whose sandbox never worked becomes a terminal leaf failure instead of a
    // false-clean result. In the panel that failure surfaces as a lost lane,
    // i.e. an `interrupted` verdict, never `correct`.
    const emitSandboxDiagnostics = (label, text) => {
      for (const line of sandboxFailureLines(text)) emit(`sandbox-diagnostic ${label ?? ""}: ${line}`);
    };
    const guardSandbox = (label, stderr) =>
      assertSandboxUsable(label, stderr, {
        onDiagnostic: (line) => emit(`sandbox-diagnostic ${label ?? ""}: ${line}`)
      });

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
          guardSandbox(opts.label, turn.stderr);
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
          guardSandbox(opts.label, repair.stderr);
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
          guardSandbox(opts.label, res.stderr);
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
            // terminal: the automatic transport retry would re-resolve the same
            // moved ref and fail identically — a second review turn that can only
            // reach the same verdict, at a full review's cost.
            throw Object.assign(new Error(
              `review target moved while the review ran (${targetCommit} → ${after}); ` +
              "the report describes a different range than this run journaled"
            ), { terminal: true });
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

// What a caller can actually go and check when a resume is refused. The four
// components are independent causes, and the old single digest named all of them
// at once — "repo, workflow script or args changed" for a message that was true
// no matter which one moved.
const COMPONENT_NAMES = {
  repoPath: "the repository path",
  repoContent: "the repository content",
  code: "the workflow script or a helper beside it",
  args: "--args"
};

function parseFingerprint(raw) {
  let parsed = null;
  try { parsed = JSON.parse(raw); } catch { /* not a component record */ }
  if (!parsed || typeof parsed !== "object") {
    // A fingerprint file nobody can read is not a match — a run recorded by an
    // older engine, or a corrupted one, has no components to compare.
    throw new WorkflowError("fingerprint-mismatch",
      "the recorded fingerprint cannot be read, so nothing about the original run can be confirmed; " +
      "re-run fresh instead of resuming");
  }
  return parsed;
}

function assertFingerprintMatches(recorded, current) {
  const moved = Object.keys(COMPONENT_NAMES).filter((name) => recorded[name] !== current[name]);
  if (moved.length === 0) return;
  // A run taken outside a git repository is single-use by construction: its
  // repoContent carries a per-run nonce, so it never matches and the digest
  // difference below would be meaningless noise.
  if ([recorded.repoContent, current.repoContent].some((v) => String(v).startsWith(`${FINGERPRINT_NOGIT}:`))) {
    throw new WorkflowError("fingerprint-mismatch",
      "this run's --cwd is not inside a git repository, so nothing watched the files its workers read; " +
      "such a run cannot be resumed — re-run fresh");
  }
  const detail = moved.map((name) => `${COMPONENT_NAMES[name]} (${recorded[name]} → ${current[name]})`).join(", ");
  throw new WorkflowError("fingerprint-mismatch",
    `changed since the original run: ${detail}; re-run fresh instead of resuming`);
}

// What counts as "the workflow's own code" for the fingerprint. A script's
// helpers are orchestration code too: change `./lib/extract.mjs` and the leaf
// results in the journal were produced under semantics that no longer exist.
// Tracking the real import graph would mean resolving every specifier the
// script (and its imports) can reach, so this is a deliberate approximation —
// the modules beside the script plus everything under a `lib/` next to it,
// which is how the shipped workflows are laid out. Modules imported from
// anywhere else stay invisible, and references/workflows.md says so. Only
// JS module files: an ad-hoc script often shares a scratch directory with
// unrelated output files, and hashing those would refuse honest resumes.
const WORKFLOW_CODE = /\.(mjs|cjs|js)$/;

function workflowExtraPaths(scriptPath) {
  const resolved = path.resolve(scriptPath);
  const found = new Set([resolved]);
  const seen = new Set();                                 // realpaths, so a link loop cannot spin
  // statSync, not the dirent's own isFile()/isDirectory(): BOTH are false for a
  // symlink, and linking a shared helper (or a whole lib/) into a workflow
  // directory is exactly how orchestration code gets reused. Following the link
  // is also the honest read — the script imports the target's content.
  const kind = (full) => { try { return fs.statSync(full); } catch { return null; } };
  const walk = (dir, recurse) => {
    let real;
    try { real = fs.realpathSync(dir); } catch { return; }
    if (seen.has(real)) return;
    seen.add(real);
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      const stat = kind(full);
      if (!stat) continue;                                // a broken link points at no content
      if (stat.isFile()) { if (WORKFLOW_CODE.test(entry.name)) found.add(full); }
      else if (recurse && stat.isDirectory()) walk(full, true);
    }
  };
  walk(path.dirname(resolved), false);
  walk(path.join(path.dirname(resolved), "lib"), true);   // absent: realpath throws, nothing added
  return [...found].sort();                               // readdir order is not guaranteed stable
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
