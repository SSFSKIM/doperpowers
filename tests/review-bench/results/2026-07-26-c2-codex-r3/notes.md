# codex r3 — fresh baseline on post-#36 fixtures (2026-07-26)

Engine: production path (`review-engine.sh`), gpt-5.6-sol xhigh. Purpose:
re-baseline FP on the maintained fixtures (truth denominator now 20:
17 seeded + 3 promoted u-entries) so C2's argus runs compare like-for-like.

## Scoring (truth-matched)

| case | seeded | promoted | verdict |
|---|---|---|---|
| case1 | b1 ✓ b2 ✓ b3 ✓ | — | 3/3 |
| case2 | b1 ✓ b2 ✓ b3 ✓ | — | 3/3 |
| case3 | b1 ✓ b2 ✓ b3 ✓ | — | 3/3 (+1 new unseeded candidate, below) |
| case4 | b1 ✓ b2 ✓ b3 ✓ (quote-remote-paths, P2) b4 ✓ | u1 ✓ u2 ✓ | 6/6 (+1 new unseeded, below) |
| case5 | b1 ✓ b2 ✓ b3 ✓ b4 ✓ | u1 ✓ | 5/5 |

**Totals: seeded 17/17, promoted 3/3 → 20/20. FP 0.**

- The r1 TOCTOU false positive is GONE: case3's explicit single-threaded
  statement (#36 bait tightening) made it refutable, and codex no longer
  flags it. The #36 acceptance ("no finding that is neither truth-matched
  nor a deliberate bait") holds for codex modulo the two new candidates
  below, which are new genuine defects, not noise.

## New unseeded candidates (excluded from FP on both sides)

1. **case4: source-dir symlink probe** — `find "$BACKUP_SOURCE_DIR"
   -mindepth 1` doesn't descend a symlinked source (and `du -sk` sizes the
   link), so a symlinked source tree reads as empty → exit 3 "nothing to
   archive" forever. Found by BOTH codex r3 and argus plain r2 →
   adjudicated genuine (cross-engine convergence). Introduced by the
   patch's emptiness probe; the #36 pass fixed the *archive*-dir symlink
   in prune.sh but this source-dir instance was not in the excluded array.
2. **case3: `expected_revision: null` skips validation** (codex only) —
   present-but-null passes `body.get` and reaches `save_document` as an
   unconditional write instead of a 400. Plausible-genuine; needs one more
   adjudication pass before fixing/promoting.

Fixture follow-up: fold both into the fixtures the same way #36 did
(fix or promote) before the NEXT scored run-id.

## Stability

Third consecutive codex run at 17/17 seeded (r1, r2 baseline runs, r3
post-maintenance). FP profile improved 1 → 0 with the bait tightened —
the r1 FP was the fixture's fault, not the engine's.
