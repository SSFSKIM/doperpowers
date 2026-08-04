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
omitted, and the run's own recorded value when resuming — see below).
`--max-concurrency` defaults to 6 and bounds live Codex app-servers,
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
lines are also appended to the job log. Exit codes: 0 on success; 130 on
SIGINT/SIGTERM, after the run has signalled its workers; 2 for an engine
refusal, which names its reason on stderr (`fingerprint-mismatch`,
`script-error`, or `lease-held`); and 1 for everything the verb itself rejects —
a missing `--script`, a bad `--args`, an error escaping the script, and the
ordinary "run is still active" refusal when you resume a run that has not
finished. Do NOT read 2 as "the refusal code": the common resume refusal is 1,
and `lease-held` reaches 2 only when the ledger's liveness check could not see
the live run (a resume from a different workspace, say) and the engine's lease
was the last guard standing.

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
  two turns, never a third. A schema with no `type` at its root validates
  nothing, silently — give the root a `type` (`object` and `array` roots both
  recurse into `properties`/`items`). The server side is STRICT and rejects the
  turn with a 400 before the model runs: every object needs
  `additionalProperties: false`, and `required` must list every property that
  object declares. An OPTIONAL field is therefore a required one whose type
  admits null — `{type: ["string", "null"]}`, and an `enum` beside it must carry
  `null` as a member. The engine-side validator understands that union, so the
  same schema serves both checks.
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

Both worker hooks take a per-call `cwd` that overrides `--cwd` for that worker
alone. It is handed to the spawn as given, so a RELATIVE one resolves against
the process's own working directory, not against `--cwd` — pass absolute paths
unless the two are the same place.

Concurrency is the engine's, not the script's: bare `Promise.all` over fifty
`agent` calls is fine, because the semaphore inside every leaf call is what
holds the live worker count at `--max-concurrency`. Each leaf call also gets one
automatic transport retry on a fresh turn — the schema-repair exhaustion above
is exempt, so it never buys a third model turn.

## Run state and `--resume`

Everything about a run lives in `$CLAUDE_PLUGIN_DATA/workflows/<run-id>/`:
`journal.jsonl` (the event log — every leaf call's start, retry and outcome,
appended as it happens), `result.json`, `fingerprint`, `args.json` (the
`--args` the run was issued with), `lease.json` while the run holds the
directory, and `workers.json` tracking live worker pids (each with the worker's
process start time, so a `cancel` after a reboot cannot signal whatever
inherited the number). The run
id IS the job id, so `status <run-id>`, `result <run-id>` and `cancel <run-id>`
work exactly as in references/jobs.md; the job statuses are `running`,
`completed`, `failed` and `cancelled`. Run directories are global under the
state root, but the job RECORD is filed per workspace — the one resolved from
`--cwd` — so the job verbs need the same `--cwd` (or the same working directory)
the run used, or they will not find it. A run killed hard (SIGKILL, reboot)
leaves its record `running` forever; the read paths repair it to `failed` when
they next look, so `result` reports the death instead of a phantom, and that
repair also signals whatever workers the dead run left running. A `--resume`
sweeps the same list before it starts, so a replayed leaf never runs alongside
the copy the crashed run left behind.

Every path that signals a recorded pid — `cancel`, that sweep, the SessionEnd
teardown — signals only a pid whose process instance it can prove (the recorded
start time still matches). A record with no start time proves nothing and is
cleaned up without a signal, which is the whole story on Windows: no start time
is readable there, so process teardown is best-effort and a leaked worker is
preferred over signalling whatever inherited the number.

`--resume <run-id>` re-runs the script against the same journal. The cache is
content-keyed — a call is identified by its kind, its label and a hash of its
arguments, plus which occurrence of that identity it is — so the script has to
issue the same calls in the same order for its earlier work to be recognized. Only
SUCCESSES are served from the journal; a journaled failure re-runs live, because
resume exists to recover a crashed run and replaying a dead worker's failure
would make the lost result unrecoverable. Two guards sit in front of it. The
lease: one process holds the run directory at a time, and a lease whose holder
is provably gone is broken atomically, so a resume of a run that is still going
is refused rather than racing it. The fingerprint: four named components, each
of which refuses the resume by name when it moves — the canonical repository
path; the repository content (HEAD, the full content diff against HEAD including
dirty submodule contents, every untracked file's blob and every untracked file
inside a submodule — content, not just paths); the `--args` value; and the
workflow script's own content along with its sibling `.mjs`/`.js`/`.cjs` files
and everything under a `lib/` directory next to it, symlinked entries included,
so editing even an out-of-tree ad-hoc script or a helper it imports refuses the
resume too. That last part is a deliberate approximation: the engine does not
walk the import graph, so a module imported from somewhere ELSE entirely (or a
change to the engine itself) will not invalidate a journal — keep a workflow's
helpers beside it or under its `lib/`. The same approximation cuts the other
way: writing a SECOND `.mjs` file into an ad-hoc script's own directory between
a run and its resume also refuses the first script's resume, since that file is
now one of its siblings. Give an ad-hoc workflow its own directory. A resume
against any changed component is refused outright, since the cached results
describe inputs that no longer exist. Re-run fresh instead.

Ignored files are deliberately outside the repository-content component. They
are conventionally derived artifacts — build output, caches, local env files —
and hashing them would turn every rebuild between a run and its resume into a
refusal. A worker that reads an ignored fixture and a resume that follows an
edit to it is therefore the one input change the fingerprint does not catch.

Two states are un-resumable rather than compared. A `--cwd` that is not inside a
git repository has no content anything can watch — the workers read files the
fingerprint never hashes — so such a run is single-use and every resume of it is
refused; the same goes for a per-call `cwd` outside a repository, whose calls are
never served from the cache. And a fingerprint that could not be TAKEN (a git
read that failed — an unreadable object, or a submodule pointer bump whose
`--submodule=diff` output exceeds the engine's 64 MiB buffer) permanently marks
that run unresumable: it fails closed rather than comparing two failures as
equal.

`--args` are recorded in the run directory, so `--resume <run-id>` on its own
replays the args the run was issued with. Passing `--args` on a resume is still
allowed and is compared: a different value refuses the resume and says so by
name. The comparison is over the serialized JSON, so re-ordering the keys counts
as a change.

A fully-cached resume spawns no workers at all, so `workers.json` may be absent
rather than empty — `cancel` tolerates that.
