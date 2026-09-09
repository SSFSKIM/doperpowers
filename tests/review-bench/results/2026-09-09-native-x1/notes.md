# native-x1 — the review-code lane's first scored X1 run (2026-09-09)

Engine: `skills/review-code/workflows/code-review.js` on the harness's native
Workflow tool, reviewers = `agents/reviewer-*.md` (codex's review rubric on
GPT through the local gateway). Two rungs scored: **medium** (one reviewer,
sol/xhigh — the rung the codex baseline ran at) and **xhigh** (the panel:
deriver sol/high, finders sol/xhigh, verifier sol/xhigh).

Baseline: `2026-07-26-c2-codex-r3` (single codex, sol/xhigh): 17/17, FP 0,
promoted 3/3. Also compared: `2026-08-03-panel-x1` (codex panel): 17/17, FP 1.

## Result

| | seeded | FP | promoted | full 20 |
|---|---|---|---|---|
| codex baseline (single) | 17/17 | 0 | 3/3 | 20/20 |
| codex panel (2026-08-03) | 17/17 | 1 | 3/3 | 20/20 |
| **native medium** (single) | **17/17** | **0** | **3/3** | **20/20** |
| **native xhigh** (panel) | **17/17** | **2** | **3/3** | **20/20** |

**medium: PASS**, equal to the baseline on every axis, and the fastest engine
recorded here (7–11 min per case headless, gateway shared with other runs).

**xhigh: FAIL by one FP.** Recall equal; two false positives, both
intent-documented design choices a finder raised and the verifier
CONFIRMED: case3's "bound or stream the node-wide export" (the fixture
documents the whole-node dump as the feature; the codex panel confirmed the
same candidate) and case4's `du -sk` free-space reservation (bait 4: deliberate
over-reservation, stated in the comment). The verifier prompt already says the
code's documentation and the change's stated intent count as refuting
evidence; a Sol verifier at xhigh still confirmed both. A max-rung re-run of
cases 3 and 4 (astra verifier) is recorded below.

## max re-run of cases 3 and 4 (astra finders, astra verifier)

| | seeded | promoted | FP | agents | wall |
|---|---|---|---|---|---|
| case3 max | 3/3 | – | 0 | 7 | 233 s |
| case4 max | 4/4 | 2/2 | 0 | 8 | 390 s |

Exactly the truth set on both — the two candidates the xhigh panel published
as FPs were never raised by the astra finders (15 and 32 candidates in the
pools, every lane converging on the seeded defects), so at max the precision
comes from the finders, not from a stricter verifier. On this seeded set the
panel cannot show a recall gain over medium (both saturate at 17/17); the
panel's recall case rests on the large real-PR evidence in the roadmap, and
what the seeded set shows is the precision cost of Sol finders under a Sol
verifier at xhigh versus none at max.

## Unseeded candidates (excluded from FP per the X1 rule)

- case1: `tenants.py` `max_value` validation / NaN hole — prior-adjudicated
  genuine in panel-x1; and an explicit-null tenant entry read as absent
  (same module, same class).
- case3: page number silently clamped to 10,000 (`app.py:94`) — introduced by
  the change, undocumented, minor.
- case4: prune label truncated at the first hyphen (`prune.sh:79`) —
  prior-adjudicated genuine class (panel-x1's "label-prefix collision");
  `BACKUP_REMOTE` beginning with `-` parsed as an ssh option — plausible,
  operator-controlled input; `find` failures inside a process substitution not
  propagated — minor.
- case5: refcount leak on `CancelledError` during the new timed acquire
  (`keylock.py:49-54`) — introduced, real.

Under the strictest reading (every non-truth finding an FP) medium sits at 0
and xhigh at 8; the codex panel sat at 5 under the same reading.

## Mechanics

- **Headless orchestration is unreliable.** `run-case.sh --engine native`
  drives a `claude -p` session that calls the Workflow tool; a session that
  writes any text before the completion notification ends and kills the run.
  Five of nine headless runs did exactly that, even with the prompt saying
  to write nothing. The scored runs for case4-medium and every xhigh case
  were therefore made from an interactive session against the same
  materialized scratch repos (`--engine materialize` now prints the pin for
  that). Medium cases 1, 2, 3, 5 are the headless runs that did complete.
- **Gateway stream errors** ("The Codex stream ended before completion")
  killed one lane in three of the five xhigh runs; the script's one-retry
  recovered two (verifier via the repair round), and case3's scalpel-3 died
  on the retry too — reported honestly as `coverage partial`, verdict still
  `incorrect`. Runs overlapped with other gateway traffic; case4-xhigh took
  2.5 h wall for that reason.
- **Verifier contract held**: no postcondition violation in any run; the
  repair round fired only for dead verifiers.
- **Isolation** was off (`repo` set) for every scored run; the worktree
  isolation path was exercised by the smoke runs only.
- `case1.native-panel.in-session.json` is a pre-ladder smoke run (astra
  deriver/verifier, reviewer at astra/high): 3/3, FP 0, 305 s.
