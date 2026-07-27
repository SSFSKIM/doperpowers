# argus plain r5 — v0.4.3 (pure deletion), case4+case5 (2026-07-27)

v0.4.3's only change over v0.4.2: the conduct section's permission/
encouragement language ("your means are unrestricted", "run code
empirically", exploration-move framing, "name what you ran") is DELETED,
leaving pure boundary statements (repo/git-state untouched, post nothing,
no delegation, no web). Human hypothesis: Bash in the tool list suffices;
granting language is itself residual framing. Expected: no big change.

Engine: headless X1 path, v0.4.3 (transcript-verified cache path in both
parent JSONLs), claude-opus-5, plain pinned.

## Scoring (truth-matched)

| case | seeded | promoted | time | notes |
|---|---|---|---|---|
| case4 | b1 ✓ b2 ✓ b3 ✓ [P2] b4 ✓ | u1 ✓ [P2], u2 ✗ | 145 s | + symlink-archives candidate; FP 0 |
| case5 | b1 ✓ b2 ✓ b3 ✓ b4 ✓ | **u1 ✓ [P2]** — first plain catch; r4 missed it | 184 s | all 5 findings truth-mapped; FP 0 |

**Composite plain r5 (r3 cells for case1-3): 17/17 seeded + 2/3 promoted =
19/20 full denominator, FP 0** — equal to /code-review medium and argus
high r2, one behind codex, as a single reviewer agent. (r3: 17/20; r4: 18/20.)

## Interpretation (n=1 caveat applies)

- The deletion OUTPERFORMED the encouragement: r5 caught case5-u1 (the
  join-path timeout gap) which r4 — with explicit empirical-run
  encouragement — missed. One run per config, so treat as consistent-with
  rather than proven; but the direction matches the native prior art (the
  medium reviewer's prompt says nothing about execution and scores 19).
- Method note: r4's findings carried explicit live-repro claims; r5's
  output claims no executions (whether it silently executed is
  unverifiable — the reviewer-subagent transcript is not persisted). The
  r4→r5 gain is therefore NOT attributable to more execution; plausibly
  the encouragement text pulled attention into repro work on
  already-caught bugs at the expense of coverage breadth.
- Both u2 misses persist (the pure cross-model residual, #40).
