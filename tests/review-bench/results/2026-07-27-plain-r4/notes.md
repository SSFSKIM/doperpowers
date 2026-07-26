# argus plain r4 — v0.4.2 (execution ban lifted), case4+case5 only (2026-07-27)

Discriminating experiment for the C4 gap-attribution question: v0.4.2's only
change over v0.4.1 is the CONDUCT rewrite — the "Never EXECUTE the code under
review" hard gate replaced by unrestricted read/search/execute inside a
mutation-only boundary (human direction; provenance deviation 10). Cases 1-3
were not rerun (v0.4.1 plain r3 already had them at 3/3 each with no
execution-sensitive misses); composite full-denominator figures below carry
those r3 cells forward.

Engine: headless X1 path (`claude -p` slash, per the C1.G3 contract),
claude-opus-5 inherited, level plain pinned.

## Scoring (truth-matched)

| case | seeded | promoted | time | notes |
|---|---|---|---|---|
| case4 | b1 ✓ b2 ✓ b3 ✓ [P2] b4 ✓ | **u1 ✓ [P2]** (first plain catch), u2 ✗ | 243 s | all findings truth-mapped, FP 0 |
| case5 | b1 ✓ b2 ✓ b3 ✓ b4 ✓ | u1 ✗ | 191 s | verdict text: "Each was confirmed by executing the changed code"; fake-clock TTL repro, 2-worker queue-hang repro, measured timeout defeat |

**Composite plain r4 (r3 cells for case1-3): 17/17 seeded + 1/3 promoted =
18/20 full denominator, FP 0** (r3 was 17/20).

## Interpretation

- The execution unban moved plain +1 on the promoted tier (case4-u1: the
  reviewer now demonstrates the truncated-file-under-final-name failure
  instead of suppressing the borderline candidate) and visibly changed the
  reviewer's method on already-caught bugs (live repros throughout, higher
  verdict confidence 0.95).
- It did NOT recover case5-u1 (join-path unbounded wait) — the same-model
  native `/code-review medium` reports it as a distinct finding, so the
  residual is not execution access but attention/stance: plain's single pass
  treats the timeout defeat it DID find (keylock guard) as closing the
  "timeout broken" thread, and never separately probes the cache join path.
- case4-u2 (remote umask gap) remains uncaught by every Claude engine
  (plain, high, /review, /code-review) while codex finds it every run —
  the cross-engine disagreement carried on doperpowers#40.
