# Real-PR round 1 — argus plain v0.4.3 vs codex review on ida-solution PRs 756/754/752 (2026-07-27)

First live-PR head-to-head after the X1 parity result (both engines 19-20/20
on seeded cases). Same single-agent mechanics, real diffs, no truth file —
scoring by post-hoc adjudication: three subagents (2 fable, 1 opus) verified
all 13 distinct findings against the code, read-only, with quoted evidence.

## Setup

- Cases: `cases-real/pr{756,754,752}/case.json` → local ida-solution clone,
  PR heads pinned as `bench-pr-*` branches, shared merge base `f7bb8b5`
  (= main at run time). Runner's real-case layout, first live use.
- codex: `review-engine.sh` → `codex exec review`, gpt-5.6-sol, xhigh.
- argus: headless X1 path, plain pinned, v0.4.3 (pure-deletion conduct).

## Raw matrix

| PR | size | codex | argus plain | overlap |
|---|---|---|---|---|
| 756 (wrongnotes card mount) | 5 files +377 | 0 findings (221 s) | 0 findings (189 s) | agree-clean |
| 754 (timetable week nav) | 6 files +517 | 1 (P2) (302 s) | 1 (P3) (183 s) | 0 |
| 752 (grade promotion event) | 22 files +2101 | **10 (6 P1, 4 P2)** (668 s) | 2 (P3) (341 s) | 1 |

## Adjudicated verdicts (13 distinct findings)

codex PR752: C1 cohort re-derivation CONFIRMED (but restates the PR's own
`lib/promotion.ts:12-17` disclosed limitation; D-day sub-claim wrong);
C2 backfill imprint CONFIRMED (severity overstated P1→~P3; live data 299
rows); C3 AI-classification g5/g9 mixing CONFIRMED; C4 display/comparison
paths CONFIRMED (roadmap chips, parents API, GradeComparison all exposed);
C5 non-atomic history insert CONFIRMED; C6 fail-open onboarding guard
CONFIRMED; C7 write-before-validate CONFIRMED; C8 revert-as-correction
CONFIRMED (severity overstated P2→P3 — server recomputes `isRevertOfLatest`,
impact is UI-label only); C9 stale profile page CONFIRMED; C10 dead
fingerprint wiring PLAUSIBLE (suffix genuinely always empty, but no
app-reachable stale-plan sequence exists).

argus PR752: revert-as-correction CONFIRMED (the overlap — argus's P3
framing judged MORE accurate than codex's P2); rate-limit bucket
selectable by request shape CONFIRMED (codex missed it).

PR754: codex digestion-card-no-refresh CONFIRMED (no remount escape — the
panel stays mounted hidden); argus retry-shows-empty-state CONFIRMED.
Each engine missed the other's finding.

## Scoreboard (union of 13 real issues: 12 CONFIRMED + 1 PLAUSIBLE, FP 0 both)

- **codex: 11/13** (missed argus's rate-limit bypass and retry-flash).
- **argus plain: 3/13** (missed 10, including all six confirmed P1-class
  defects on the big PR).

## Conclusions

1. **X1 parity did NOT transfer to the large real PR.** On ≤600-line diffs
   the engines converge (0-vs-0, 1-vs-1 disjoint). On the 2,101-line diff
   codex found 10 real issues to argus's 2 — a recall collapse, not a
   precision difference (both FP 0). This is the sweep-coverage lesson
   (case5-u1) at scale: single-context argus saturates on breadth long
   before codex does. Strongest evidence yet FOR the C3 multi-lens
   rearchitecture (diff partitioning restores breadth).
2. **"codex findings are never refuted" survived its first adversarial
   test: 0 of 10 refuted** (9 CONFIRMED, 1 PLAUSIBLE). Its failure mode is
   severity inflation (3 of 10 overstated) and flagging a disclosed
   limitation, never invented mechanisms.
3. **argus's verdict prose made false global-correctness claims**: "type
   was previously immutable" (disproven by the merge-base onboarding
   upsert) and "cross-system suppression is well tested" (tests cover
   goal-grade paths, none of the three exposed display paths). The Verdict
   Explanation invites asserting unexamined areas at confidence 0.85 —
   a prompt defect distinct from recall: unverified positive assertions
   are worse than silence. C3 input.
4. **v0.4.3 execution-as-ordinary-means, live**: the PR756 reviewer
   spontaneously ran `npm ci` + full vitest (1,883 tests) + tsc + eslint
   with zero encouragement text — claim empirically verified (exact 223/1883
   match on rerun; npm ci 10 s + vitest 9 s fits its 167 s budget). The
   PR754 reviewer declined to install deps. Initiative varies per run;
   honesty held in both.
5. Severity calibration on the one overlap favored argus (P3 right, codex
   P2 wrong) — argus wins depth-per-finding, codex wins breadth.

Artifacts: pr*.{codex,argus}.md (+ .events.jsonl, logs) in this dir;
adjudication transcripts in session 3ca5aed9's agent outputs.
