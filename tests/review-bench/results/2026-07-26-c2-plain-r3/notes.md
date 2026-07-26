# argus plain r3 — v0.4.1, post-#36 fixtures (2026-07-26) — G1 SCORED RUN

Engine: headless path, argus-review v0.4.1 (v0.4.0 uplift + the native
injection-sink boundary codified in the security family), Opus 5 effort
high inherited, level plain.

## Scoring (truth-matched)

| case | seeded | promoted | time |
|---|---|---|---|
| case1 | b1 ✓ b2 ✓ b3 ✓ | — | 95 s |
| case2 | b1 ✓ b2 ✓ b3 ✓ | — | 104 s |
| case3 | b1 ✓ b2 ✓ b3 ✓ | — | 97 s |
| case4 | b1 ✓ b2 ✓ **b3 ✓ [P2]** b4 ✓ | u1 ✗ u2 ✗ | 142 s |
| case5 | b1 ✓ b2 ✓ b3 ✓ b4 ✓ | u1 ✗ | 148 s |

**Totals: seeded 17/17, FP 0. Promoted 0/3.**

## G1 bar verdict

- Bar: single-agent plain recall ≥ codex baseline on the seeded set, no
  meaningful FP growth.
- codex r3 (same fixtures): seeded 17/17, FP 0.
- **plain r3: 17/17, FP 0 → BAR MET.** The case4-b3 remote-shell
  injection that both the r1 rubric-verbatim baseline and the v0.4.0 r2
  run missed is now found, at the same P2 severity codex assigns it.
- Timing: 95–148 s/case — faster than both the r1 plain baseline
  (140–270 s) and codex xhigh r3 (102–493 s).

## Honest deltas (informational, for C4)

- The three promoted u-entries (case4 non-atomic replica publish, case4
  remote umask, case5 in-flight join timeout) are found by codex (3/3)
  and not by plain (0/3): on the full 20-defect denominator codex r3 is
  20/20 vs plain r3 17/20. These are the subtle second-tier defects the
  multi-agent ladder exists for (argus high r1 surfaced two of the three
  as unseeded candidates). The engine-context escalation dial (C3) and
  the high-level re-run (G2) are the intended answer, not further plain
  prompt growth.
- Single-run result; codex's 17/17 is now 3-run stable. A stability
  re-run of plain can ride any future fixture-maintenance run-id.
