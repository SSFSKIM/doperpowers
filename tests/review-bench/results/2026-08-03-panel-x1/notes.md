# panel-x1 — the review panel's first live X1 run (2026-08-03)

Engine: the codex review **panel** — `skills/codex-companion/workflows/code-review.mjs`
on the `workflow` verb, driven by the new `tests/review-bench/run-case-workflow.sh`.
Each case gets one lens-deriver (sol/medium), one lens-free native sweep plus
three or four diff-derived scalpel native reviews (sol/xhigh, all concurrent),
and one binding verifier (sol/high). codex-cli 0.146.0.

Baseline compared against: **2026-07-26-c2-codex-r3** (single codex through
`review-engine.sh`, sol/xhigh), scored in `results/2026-07-26-c2-scores.json`:
seeded 17/17, FP 0, promoted 3/3. It is the most recent codex run scored on the
current post-#36 fixtures, so the truth denominator matches.

## Result

| | seeded recall | FP | promoted | full 20 |
|---|---|---|---|---|
| codex baseline (c2-codex-r3) | 17/17 | 0 | 3/3 | 20/20 |
| **panel (this run)** | **17/17** | **1** | **3/3** | **20/20** |

**Bar: PASS.** Recall equals the baseline and the single false positive is
exactly the +1 the bar allows — no margin left.

Per case: case1 519s / 6 workers, case2 594s / 6, case3 417s / 7, case4 714s / 7,
case5 621s / 7. All five answered `incorrect`. Wall time for the whole set was
about 48 minutes run sequentially.

## The one false positive

case3, "Bound or stream the all-tenant export" (`app.py:219-224`): the panel
confirmed that `GET /exports/all` loads and renders every document on the node
with no bound. The endpoint's own docstring and the README say that is what it
is for ("every document on this node, for the warehouse loader"). This is not a
new candidate — argus-plain, argus-high and the built-in `/review` all RAISED
it, and every one of their verifiers **refuted** it on those fixture-stated
grounds. The panel's verifier, running at `high` while its finders ran at
`xhigh`, confirmed it instead. That is direct evidence for the spec's Open
Question 2 (verifier effort): the finders are recall-biased by design and the
verifier is the only thing standing between a plausible candidate and a
published finding, so it is the wrong stage to economize on.

## Genuine unseeded candidates (excluded from FP, per the X1 rule)

Two are already-adjudicated fixture issues from the C2 round, one of which the
codex baseline itself reported — so excluding them is symmetric:

- case4 source-dir symlink probe (`snapshot.sh:63`) — cross-engine convergent in C2.
- case4 staging-filesystem free-space gap (`snapshot.sh:75`) — C2 candidate.

Two are new and want fixture maintenance before the next scored run-id:

- **case1 `tenants.py` validation gap.** A `"default": null` entry makes
  `entry.get` raise, and a `NaN` `max_value` becomes `float('nan')`, after which
  `value > nan` is false for every reading and clipping is silently disabled.
  The same NaN hole the fixture already closed in `parse_line` during #36
  maintenance is open in the module the patch adds.
- **case4 prune label-prefix collision** (`prune.sh:40`). `list_archives`
  matches `"$label"-*.tar.gz`, so label `nightly` sweeps `nightly-db-*` archives
  into its own KEEP budget. The base glob had identical prefix semantics, so it
  is pre-existing — but this very change's README says the v2 manifest exists
  *because* labels may contain `-`, which is what makes the collision reachable.

Scoring sensitivity is recorded in `scores.json`: under the strictest reading
(every non-truth finding is an FP) the panel sits at 5 and the codex baseline at
2, and the panel fails. The scored reading is the X1 rule as written, applied to
both engines alike.

## Mechanics

- **Coverage: 22 finder lanes, all `ok`.** No dead worker, no extraction
  failure, no partial drift. 97 stubs parsed in total.
- **Verifier: zero repairs.** The postcondition check passed first time in all
  five cases — the contract (one verdict per candidate, resolvable `duplicateOf`
  graph) held live without the repair retry ever firing.
- **The clean sentinel was NOT exercised.** Every one of the 22 finders came
  back with at least two findings, so no lane ever had to render a clean review.
  The sentinel's positive direction (a genuinely clean finder emitting
  `No material findings.`) remains unvalidated live; its failure mode
  (clean prose mis-read as a dead lane) also never had the chance to occur.
  It still gates every `correct` verdict the panel can ever produce.
- The finders' rendering held: every finding came back as
  `- [P#] Title — path:line[-line]`, zero orphan `[P#]` lines.

## Live blocker found and fixed before the scored run

The panel's very first live invocation died on the lens-deriver with HTTP 400
`invalid_json_schema`. The API's structured-output mode is a strict dialect:
every object needs `additionalProperties: false`, and `required` must list every
property the object declares. Both panel schemas violated it, and no mock test
could have caught it — the mock never validates a schema server-side.

Fixed in this branch: both schemas closed; the verifier's optional `duplicateOf`
and `priority` re-spelled as required-and-nullable (everything downstream
already read them through falsy/nullish tests); the engine-side validator taught
to understand a union `type`; `references/workflows.md` now states the strict
contract; and `test-panel-flow.sh` pins all of it (its verdict fixtures now
carry the five-key shape a real strict verifier must emit).

## Reproducing

    tests/review-bench/run-case-workflow.sh \
      --case tests/review-bench/cases/seeded/case1 \
      --out results/<run-id>/case1.workflow.txt

Each case leaves three files: the rendered findings `.txt` (what adjudication
reads), the verb's `.json` stdout (verdict, findings, coverage, lenses), and the
`.events.log` progress stream. The `runId` inside the `.json` names the journal
directory under `$CLAUDE_PLUGIN_DATA/workflows/`, which holds every finder's raw
`reviewText` — the only place to audit sentinel compliance after the fact.
