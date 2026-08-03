# Workflows: the `workflow` verb

`workflow` runs a JavaScript orchestration script you write. The script gets a
handful of hooks and calls them however it likes; each call becomes a Codex
worker — an `agent` turn or a native `review` — and the engine caps how many are
alive at once, journals every one, and can resume the run where it stopped. It
is ONE foreground process — nothing detaches, no broker outlives it — so a real
fan-out belongs in a harness background Bash call like every other work verb
(references/jobs.md). Every worker runs read-only; there is no write option
anywhere on this lane.

    CLAUDE_PLUGIN_DATA="$HOME/.claude/doperpowers/codex-companion" \
    CODEX_COMPANION_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
      node "<skill-base>/runtime/scripts/codex-companion.mjs" workflow \
      --script <path.mjs> [--args <json>] [--max-concurrency N] [--cwd <dir>] [--resume <run-id>]

`--cwd` is the repo the workers read and the base every relative path resolves
against, the process cwd by default; `--script` is resolved against it and must
exist. `--args` is any JSON value, handed to the script as `args` (`{}` when
omitted). `--max-concurrency` defaults to 6 and bounds live Codex app-servers,
not script promises. `--resume <run-id>` re-enters an existing run (see below).

The two env prefixes carry the same meaning as everywhere else in this skill:
`CLAUDE_PLUGIN_DATA` pins the state root — run directories live at
`$CLAUDE_PLUGIN_DATA/workflows/<run-id>/`, so unset it and the whole run lands
in a purgeable tmpdir with nothing to resume — and `CODEX_COMPANION_SESSION_ID`
stamps the run's job record so `status`/`result` scope to this session.
`CODEX_COMPANION_APP_SERVER_ENDPOINT` is the exception: leave it OFF. The
engine connects every worker with `disableBroker`, which short-circuits before
the endpoint env is ever read, so each call spawns its own app-server that dies
with the call. The broker kill-switch has nothing to switch off here, and
setting it changes nothing.

Output is split like the other work verbs, and stricter: stdout carries EXACTLY
one JSON object, `{runId, result, agents, durationMs}`, where `result` is
whatever the script returned; stderr streams `[workflow]` progress — one line
per leaf call (`start`/`done`/`fail`/`retry`/`cache`/`cache-skip`) plus anything
the script sent to `log`. On a fan-out of any size that stream dwarfs the
result, so redirect it (`2> <scratch>.events.log`) and parse stdout. The same
lines are also appended to the job log. Exit codes: 0 on success, 2 for an
engine refusal (`lease-held`, `fingerprint-mismatch`, `script-error` — the
reason is printed to stderr), 1 for an error escaping the script, 130 on
SIGINT/SIGTERM after the run has signalled its workers.

## The script

An ES module with a default async function. It receives one object and returns
anything JSON-serializable:

```js
// review-then-summarize.mjs
export default async function run({ agent, review, parallel, pipeline, log, args }) {
  log(`reviewing ${args.base}`);
  const { reviewText } = await review({ base: args.base, effort: "high" });

  const takes = await parallel(
    ["security", "performance"].map((lens) =>
      () => agent(`Read the diff against ${args.base} and report ${lens} risks.`,
                  { label: lens, effort: "medium" }))
  );

  return agent(
    `Merge these into one verdict:\n${reviewText}\n${takes.filter(Boolean).join("\n")}`,
    { label: "synthesis", schema: {
        type: "object", additionalProperties: false,
        required: ["verdict", "issues"],
        properties: {
          verdict: { type: "string" },
          issues: { type: "array", items: { type: "string" } }
        } } }
  );
}
```

Hooks:

- `agent(prompt, {model, effort, schema, label, cwd})` → the final message as a
  string, or the parsed object when `schema` is given. The turn is read-only and
  its thread persists so the repair turn below can reuse it. `schema` goes to Codex as
  the turn's output schema AND is re-checked engine-side; a failing result gets
  ONE repair turn on the same thread, and a second failure is terminal — exactly
  two turns, never a third. A schema without `type: "object"` at the root
  validates nothing, silently.
- `review({base, scope, model, effort, lens, label, cwd})` →
  `{reviewText, threadId, status}`. Target selection matches the `review` verb
  (`base`, or `scope` of `auto`/`working-tree`/`branch` — see
  references/reviews.md). This is Codex's native reviewer, so `lens` is not a
  prompt: it rides `developer_instructions` on that worker's private
  app-server, alongside the review protocol rather than replacing it. Keep a
  lens to at most two plain sentences; longer mandates compete with the
  protocol instead of steering it.
- `parallel(thunks)` → results in order, with a rejected thunk absorbed as
  `null`. Nothing short-circuits: every thunk runs to completion.
- `pipeline(items, ...stages)` → each item threaded through the stages
  (`stage(acc, item, index)`), all items concurrently; a throw anywhere in one
  item's chain yields `null` for that item and leaves the others alone.
- `log(message)` → journals the line and emits it on stderr.
- `args` → the parsed `--args` value.

Concurrency is the engine's, not the script's: bare `Promise.all` over fifty
`agent` calls is fine, because the semaphore inside every leaf call is what
holds the live worker count at `--max-concurrency`. Each leaf call also gets one
automatic transport retry on a fresh turn — the schema-repair exhaustion above
is exempt, so it never buys a third model turn.

## Run state and `--resume`

Everything about a run lives in `$CLAUDE_PLUGIN_DATA/workflows/<run-id>/`:
`journal.jsonl` (the event log — every leaf call's start, retry and outcome,
appended as it happens), `result.json`, `fingerprint`, `lease.json` while the
run holds the directory, and `workers.json` tracking live worker pids. The run
id IS the job id, so `status <run-id>`, `result <run-id>` and `cancel <run-id>`
work exactly as in references/jobs.md; the job statuses are `running`,
`completed`, `failed` and `cancelled`. A run killed hard (SIGKILL, reboot)
leaves its record `running` forever; the read paths repair it to `failed` when
they next look, so `result` reports the death instead of a phantom.

`--resume <run-id>` re-runs the script against the same journal. The cache is
content-keyed — a call is identified by its kind, its label and a hash of its
arguments, plus which occurrence of that identity it is — so the script has to
issue the same calls in the same order for its earlier work to be recognized. Only
SUCCESSES are served from the journal; a journaled failure re-runs live, because
resume exists to recover a crashed run and replaying a dead worker's failure
would make the lost result unrecoverable. Two guards sit in front of it. The
lease: one process holds the run directory at a time, and a lease whose holder
is provably gone is broken atomically, so a resume of a run that is still going
is refused rather than racing it. The fingerprint: it hashes HEAD, the full
content diff against HEAD and every untracked file's blob — content, not just
paths — and a resume against a changed repo is refused outright, since the
cached findings describe code that no longer exists. Re-run fresh instead. (In a
directory with no git, the fingerprint is a constant and that guard is off.)

A fully-cached resume spawns no workers at all, so `workers.json` may be absent
rather than empty — `cancel` tolerates that.
