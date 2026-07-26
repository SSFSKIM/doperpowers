# Builtin engines round — /review and /code-review medium (2026-07-27)

Claude Code's built-in review commands measured on the post-#36 fixtures as
the same-model control cell for the C4 gap-attribution question: both run
claude-opus-5 in a NATIVE harness with execution allowed, so they separate
"what the model can reach" from "what the argus skill text reaches".

Invocation: fresh `claude --bg` background session per case from the
materialized scratch repo (NOT headless -p — human direction), prompt
`/code-review medium main...bench-change` / bare `/review` (which
self-adapts: no PR exists, so it reviews the branch diff directly).
Findings recovered from the session transcript (ReportFindings tool call +
longest assistant text; `extract-bg-findings.py`). Both engines ran ZERO
subagents in every case (transcript-verified) and verified findings by
EXECUTING the code (live repros, measured tables, fake clocks).

Operational scar: two run-batch wrapper kills took their process group's
bg sessions and job dirs with them; three cases were recovered from
surviving transcripts, three relaunched detached. See the ops-gotchas
memory note.

## Scoring (truth-matched, denominator 20 = 17 seeded + 3 promoted)

### /code-review medium

| case | seeded | promoted | notes |
|---|---|---|---|
| case1 | 3/3 | — | + watermark now read-only property (unseeded cand.) |
| case2 | 3/3 | — | + per-promo Math.ceil stacking over-credit (unseeded cand.) |
| case3 | 3/3 | — | 2 considered-and-excluded notes, explicitly not counted |
| case4 | 4/4 (b3 [P3-equiv PLAUSIBLE]) | u1 ✓, u2 ✗ | + staging-FS gap, symlink archives, umask→archive-dir 0700 (all cand.) |
| case5 | 4/4 | u1 ✓ | + README error-result memory bound (unseeded cand.) |

**Total: 17/17 seeded + 2/3 promoted = 19/20, FP 0.**

### /review

| case | seeded | promoted | notes |
|---|---|---|---|
| case1 | 3/3 | — | + clipped-misnomer (naming note), explicit-null tenant (known cand.) |
| case2 | 3/3 | — | + resolvePromos param narrowing (unseeded cand.); traced -5 → clean $0 total |
| case3 | 3/3 | — | reproduced with stock tokens |
| case4 | 4/4 (b3 lower-severity) | u1 ✓, u2 ✗ | + source-symlink no-op AS BLOCKER (known cand.), replica-failure-destroys-local (design), du-failure-swallowed (new, verified), umask local 0700, staging-FS, symlink archives |
| case5 | 4/4 | u1 ✗ | + retained-exception traceback pinning (≈ code-review's README bound cand.), seq-gap, _lookup-mutates-on-probe |

**Total: 17/17 seeded + 1/3 promoted = 18/20, FP 0.**

## The full C4-attribution scoreboard (2026-07-27)

| engine | model/harness | subagents | exec | full 20 | misses |
|---|---|---|---|---|---|
| codex r3 | gpt-5.6-sol xhigh, native | 0 | (sandboxed) | **20/20** | — |
| /code-review medium | Opus 5, native | 0 | yes | **19/20** | case4-u2 |
| argus high r2 (v0.4.1) | Opus 5, skill | 5-7/case | no | **19/20** | case4-u2 (refuted) |
| /review | Opus 5, native | 0 | yes | **18/20** | case4-u2, case5-u1 |
| argus plain r4 (v0.4.2) | Opus 5, skill | 0 | yes | **18/20** | case4-u2, case5-u1 |
| argus plain r3 (v0.4.1) | Opus 5, skill | 0 | no | 17/20 | u1 u2 u5-u1 |

FP 0 on every row.

## Attribution conclusions

1. **Model-superiority hypothesis weakened further**: Opus reaches 19/20 in
   a native single-context engine. The codex margin is exactly case4-u2.
2. **Execution asymmetry confirmed as real but partial**: lifting the argus
   ban (v0.4.2) moved plain 17→18 (case4-u1 now demonstrated, not
   suppressed) and landed plain EXACTLY on /review parity — same score,
   same miss set. Single-agent Claude engines with execution converge at 18.
3. **The last mile is stance/attention, not tools**: /code-review medium's
   +1 (case5-u1) shows the same model+exec in one pass CAN report the
   join-path timeout as its own finding. plain r4 found the keylock timeout
   defeat, treated the "timeout broken" thread as closed, and never probed
   the cache join path — a sweep-coverage gap, C3 rearchitecture input.
4. **case4-u2 is now a pure cross-model disagreement**: every Claude engine
   misses the remote umask gap (or actively refutes it — high r2) while
   codex finds it every run; both builtins caught the LOCAL side of the
   same relocation (archive dir born 0700). Carried on #40.
