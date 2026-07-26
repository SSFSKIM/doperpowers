# review-bench — the X1 review benchmark

The fixed, re-runnable benchmark contract **X1** of
`docs/doperpowers/specs/2026-07-26-claude-review-stack-roadmap.md`.
It measures a review engine's defect-finding quality so the roadmap's
"no regression" claims (C2, C4) are checkable instead of vibes.
Built by C1 (doperpowers#28); consumed by C2 (#29) and C4 (#31).

## Cases

- `cases/seeded/case1..case5` — synthetic changes with **known ground
  truth**: each has `base/` (clean codebase), `patch.diff` (a plausible
  change that introduces the bugs), `truth.json` (the seeded bugs:
  id, file, approx lines, class L1–L5 per the argus lens taxonomy,
  trigger), `intent.md` (the change's stated intent — reviewers may see
  it), and `case.md` (answer key notes: seeded classes + FP baits).
  Baits are deliberate: changes that look suspicious but are correct;
  flagging one costs a false positive.
- `cases/real/pr12|pr19|pr21` — real previously-merged doperpowers PRs
  (`case.json`: repo + head/base SHAs). No ground truth; scored
  comparatively (see below).

## Running

One case, one engine (from anywhere; scratch repos are ephemeral):

    tests/review-bench/run-case.sh --case cases/seeded/case1 \
        --engine codex|argus --out results/<run-id>/case1.<engine>.txt

Both engines review the identical committed `bench-change` branch
against `main` in a materialized scratch repo. The codex engine runs
through the loop's own `review-engine.sh` (env `CODEX_REVIEW_MODEL`,
`CODEX_REVIEW_EFFORT` pass through; defaults match the live loop). The
argus engine ALWAYS runs through the headless invocation path (`claude
-p` slash invocation, `--permission-mode auto` — the C1.G3 probe
mechanism), because that is the context C4 deploys; benching argus
interactively would measure the wrong thing.

## Scoring

- **Seeded recall** = seeded bugs matched by at least one finding /
  total seeded bugs. A finding matches a truth entry when it identifies
  the same defect (same file, overlapping mechanism) — file+line overlap
  is evidence, the mechanism match is the criterion.
- **False positives** = findings that match no truth entry and are not
  independently verified real defects. Baits that get flagged are FPs by
  construction. A finding that surfaces a GENUINE unseeded defect is
  credited to neither side (recorded, excluded from FP) — fixture bugs
  happen; record them in the run notes and fix the fixture for the next
  run-id.
- **Matching is adjudicated, not string-matched**: the runner collects
  raw findings; a human-or-LLM adjudication pass maps findings ↔ truth
  entries and records the mapping in `results/<run-id>/scores.json`.
  Adjudication rules: one finding may match at most one truth entry;
  duplicate findings of the same defect count once for recall and zero
  FP; severity tags are not scored (P-level calibration is a findings-doc
  observation, not an X1 metric).
- **Real-PR cases**: side-by-side finding lists per engine, adjudicated
  into (both found / only A / only B / FP-judged) — comparative evidence,
  no recall denominator.

## The bar (fixed by X1 — later children re-litigate none of this)

- Baseline stability: the codex engine's seeded recall must be stable
  across two runs (same set) before the baseline counts; if the two runs
  disagree by more than one seeded bug, grow the case set and re-run.
- **Non-regression** (C2 vs baseline argus, C4 vs baseline codex):
  seeded recall at least equal, AND no *meaningful* false-positive
  growth, defined as: FP total may exceed the baseline by at most 1
  across the whole seeded set. Real-PR cases inform judgment but only
  seeded cases gate.

## Results

`results/<run-id>/` — one dir per run batch (`YYYY-MM-DD-<label>`),
containing raw findings files, `scores.json`, and `notes.md` (deviations,
genuine-unseeded-defect credits, timing). Baseline run-ids are recorded
in the C1 findings document and on doperpowers#28.
