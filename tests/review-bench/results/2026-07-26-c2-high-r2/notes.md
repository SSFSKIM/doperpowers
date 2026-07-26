# argus high r2 — v0.4.1 repriced economy, post-#36 fixtures (2026-07-26) — G2 SCORED RUN

Engine: headless path, argus-review v0.4.1, Opus 5 effort high inherited,
level high (diff-proportional fleet + packed verifiers).

## Scoring (truth-matched)

| case | seeded | promoted | finders | verifiers | time |
|---|---|---|---|---|---|
| case1 | b1 ✓ b2 ✓ b3 ✓ | — | 2 | 3–5 | 416 s |
| case2 | b1 ✓ b2 ✓ b3 ✓ | — | 2 | 3–5 | 417 s |
| case3 | b1 ✓ b2 ✓ b3 ✓ | — | 2 | 3–5 | 322 s |
| case4 | b1 ✓ b2 ✓ b3 ✓ [P3] b4 ✓ | u1 ✓ [P2], u2 ✗ (refuted) | 2 | 3–5 | 581 s |
| case5 | b1 ✓ b2 ✓ b3 ✓ b4 ✓ | u1 ✓ [P2] | 2 | 3–5 | 503 s |

(Per-transcript dispatch counts: finders=2 in every case; verifiers 3, 3,
3, 4, 5 across the five cases — pairing to cases not individually
tracked; totals per case 5–7 subagents.)

**Totals: seeded 17/17, FP 0. Promoted 2/3.**

## G2 bar verdict

- Bar: subagent spend proportional to the diff (no fixed large fleet) AND
  no recall loss at high vs baseline high.
- Recall: **17/17 = baseline high r1's 17/17 — no loss.** The lens
  bundling (5 lenses on 2 finders at these diff sizes) did not cost a
  seeded bug.
- Economy: finder wave 5 → 2 per case (the `ceil(lines/150)` budget
  clamps to the floor of 2 on these 100–300-line diffs); verifiers packed
  (3–5 per case). Total 5–7 subagents/case against r1's fixed 5 finders +
  one verifier per group (announced scale 6–12). Wall time 322–581 s vs
  r1's 579–1133 s — roughly halved.
- FP: 0 vs r1's 2 [P3]. Both r1 FPs (case3 TOCTOU, case5 retention bait)
  were defused by #36's bait tightening; the two new case1 [P3]
  PLAUSIBLE findings (null config entry crash; explicit-null tenant
  stringified to "None" against the documented default-tenant contract)
  are adjudicated genuine-unseeded under the r1 standard (real mechanism,
  nameable trigger, introduced by the patch), not FP.

## Honest deltas / carry-forwards

- u2 (remote umask, promoted from codex r1) was actively REFUTED by a
  verifier this run while codex r3 finds it — a genuine cross-engine
  disagreement to revisit at the next fixture pass (the defect is real;
  the refutation reasoning should be pulled from the transcript before
  deciding whether the verifier text needs a nudge).
- New genuine-unseeded candidates for the next fixture round: case4
  staging-filesystem free-space gap [P2 PLAUSIBLE], case4 symlinked
  archive *files* dropped by `find -type f` [P3], case1's two [P3]s
  above, the cross-engine case4 source-dir symlink probe [P1], and codex
  r3's case3 `expected_revision: null` candidate.
- b3 severity: argus high tags the remote-shell interpolation [P3
  PLAUSIBLE] where codex r3 and plain r3 tag it [P2]. Verdict-neutral in
  the loop either way.
