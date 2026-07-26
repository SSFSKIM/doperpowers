# argus plain r2 — v0.4.0 uplift, post-#36 fixtures (2026-07-26)

Engine: headless path, argus-review v0.4.0 (INVESTIGATION SWEEP + FP
exclusions + conventions check + no-execute conduct), Opus 5 effort high
inherited, level plain. Plugin version verified from the run transcript
(0.4.0 cache paths loaded).

## Scoring (truth-matched)

| case | seeded | promoted | time |
|---|---|---|---|
| case1 | b1 ✓ b2 ✓ b3 ✓ | — | 118 s |
| case2 | b1 ✓ b2 ✓ b3 ✓ | — | 138 s |
| case3 | b1 ✓ b2 ✓ b3 ✓ | — | 110 s |
| case4 | b1 ✓ b2 ✓ b4 ✓ — **b3 MISSED** | u1 ✗ u2 ✗ | 205 s |
| case5 | b1 ✓ b2 ✓ b3 ✓ b4 ✓ | u1 ✗ | 170 s |

**Totals: seeded 16/17, promoted 0/3. FP 0.**

Extra findings, adjudicated genuine-unseeded (not FP):
- case4 source-dir symlink probe [P1] — convergent with codex r3; real.
- case4 `list_archives` skips symlinked archive *files* [P3] (`find
  -type f` vs the old glob + `[ -f ]` which follows links) — argus-only,
  mechanism real; the #36 trailing-slash fix addressed the symlinked
  *directory*, not linked files. Genuine behavior change; carry to the
  fixture follow-up.

## The verdict on v0.4.0

Same sole seeded miss as the r1 rubric-verbatim baseline: case4-b3, the
remote-shell injection via the label-derived archive name. The sweep's
security family was present (version verified) and did not surface it —
consistent with correlated censorship under the plain level's precision
stance ("prefer outputting no findings"): argus high's recall-biased L4
finder caught this same bug in r1 with the same lens wording, and codex
flags it at P2 with "labels are otherwise unrestricted". The boundary the
native standard applies (unconstrained value interpolated into a
remote-shell command line = sink, regardless of the value's provenance)
was left implicit in v0.4.0's "fed by external input".

→ v0.4.1 codifies exactly that boundary in the security family (reviewer
sweep + L4 lens). Scored re-run: plain r3.
