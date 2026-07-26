# baseline-r1 adjudication notes (in progress)

Models: argus side ran `claude -p` with no model flag → user default
`model: "opus"` → **Claude Opus 5 at effortLevel "high"** (settings
default; no per-run override), inherited by the argus-reviewer agent
(`model: inherit`). This matches the C5 deployment condition (claude-route
daemon workers inherit the same defaults unless pinned). codex side:
**gpt-5.6-sol, effort xhigh** (the loop's production default) — one
reasoning-budget notch above the argus side.

## argus (plain, headless path, inherit model) — seeded cases

- **case1**: 3/3 (b1 L1 lateness [P0], b2 L3 flush [P1], b3 L5 reload [P2]). FP 0. Baits untouched.
- **case2**: 3/3 (b2 L2 cents [P0], b3 L3 guard [P0], b1 L1 tier bound [P1]). FP 0. Baits untouched.
- **case3**: 3/3 (b1 L4 authz [P0], b3 L1 pagination [P1], b2 L2 revision [P2]). FP 0. Baits untouched.
- **case4**: 3/4 — found b4 L2 manifest [P0], b1 L1 force-guard [P0], b2 L3 trap [P1]; **MISSED b3 L4 ssh command injection**. FP 0.
  - Two genuine-unseeded defects surfaced (excluded from both sides per X1 rules; fixture fixes due before the next run-id):
    1. `replicate()` comment claims partial-transfer safety the `cat > final-name` code does not deliver (no temp+rename).
    2. `FORCE="${BACKUP_FORCE:-0}"` resolves before `load_config`, so the README-documented `BACKUP_FORCE` config key is inert.
- **case5**: first run failed on Anthropic API 529 (transient); retried.

Interim seeded recall (case1-4): **12/13, FP 0**. Only miss is the L4
injection at plain level — consistent with plain having no dedicated
security lens (L4 exists only in the medium+ multi-agent ladder).

## Conduct observation (feeds C2/C4)

In the headless bench context (`--permission-mode auto`) the plain
argus-reviewer EXECUTED repository code to verify findings ("verified by
running the class directly", case1; "reproduced by executing the changed
code", case2) despite its conduct constraints prescribing read-only
commands. The argus-verifier's text explicitly forbids execution; the
reviewer's text lists read-only commands but lacks the verifier's "Never
EXECUTE" sentence. For the C4 engine this is a live arbitrary-code-
execution vector on untrusted PR code (the codex engine runs under a
seatbelt profile; a headless argus engine has no equivalent runtime
sandbox unless the worker imposes one). → C2: port the verifier's
no-execution sentence into argus-reviewer. → C4: engine invocation needs
a sandbox/permission posture decision, not just a prompt fix.

## argus — case5 retry + real PRs

- **case5** (retry after transient Anthropic 529): **4/4** (b3 L5
  lock-scope [P0], b1 L1 TTL-slide [P0], b2 L3 inflight [P0], b4 L2
  metrics [P1]). FP 0.
- **argus plain seeded FINAL: recall 16/17, FP 0.** Sole miss: case4-b3
  (L4 ssh injection).
- Real PRs (argus, fixed harness): pr12 → 2 [P2] doc-consistency
  findings; pr19 → 1 [P1] + 1 [P2] (rule-vs-legality-table
  reconciliation); pr21 → No findings / correct. All reviewed the true
  diffs (explicit merge-base SHA in the seed prompt).

## Real-PR harness bug #2 (upstream-preference collapse)

r1's codex pr19/pr21 outputs are INVALID: codex's base resolution prefers
a branch's upstream when ahead; the scratch clone's `main` tracked
origin/main, which already contains a merged PR's head, so the merge base
resolved to the head itself → "empty diff" verdicts. (pr12 escaped by
luck; its review is real and matches PR content.) argus was unaffected —
its seed pins the precomputed merge-base SHA. Fixed by removing the
origin remote in real-mode scratches (run-case.sh); codex r2's real-PR
runs use the fix and supply the codex side of the comparison.

## Harness fixes during r1

- real-PR mode: `checkout -b main` collided with the clone's own main;
  fixed to `checkout -B` (run-case.sh). First-run real-PR argus results
  are from the fixed harness (retry batch).
- argus timing (headless, per case, cases 1-4): ~2-4.5 min each — far
  below the 10-min probe datum (the probe's fixture-dir setup inflated
  it); well inside the loop's 45-min engine bound.

## codex (gpt-5.6-sol xhigh) — r1 adjudication

- **case1**: 3/3 (b1, b2, b3). +1 unseeded-excluded: NaN/Infinity pass the
  patch's new "must be a JSON number" check (claim/behavior mismatch —
  same pattern as case4's replicate() comment; fixture-fix due).
- **case2**: 3/3. FP 0.
- **case3**: 3/3. **FP 1**: TOCTOU race on the conditional write — the
  fixture has no threading or concurrent server anywhere; "two concurrent
  requests" is an unstated deployment assumption (rubric criteria 6/7).
- **case4**: **4/4 — including the L4 ssh injection argus plain missed.**
  +4 unseeded-excluded, all judged real on inspection: find -name
  interprets glob metachars in unvalidated labels (base's quoted glob was
  literal — introduced regression); non-atomic replica publish (comment
  claims otherwise); emptiness probe fails open on find errors; replica
  umask not established remotely. (The BACKUP_FORCE-before-load_config
  issue argus surfaced separately is folded into codex's b1 finding.)
- **case5**: 4/4. +2 unseeded-excluded (join path ignores configured
  timeout; initial retry delay uncapped when base_delay > cap) — both
  plausible-real, introduced by the patch's new features.

**codex r1 seeded totals: recall 17/17, FP 1.**
**argus r1 seeded so far (case5 retry pending): recall 12/13, FP 0.**

Early read for the C4 bar: codex xhigh at full strength beats argus PLAIN
on recall (the one gap is exactly plain's missing L4 lens); argus wins on
precision (0 vs 1 FP) and on surfacing nothing speculative. The
deployment-mode comparison that X1 actually gates is argus AT ITS
AUTO-ROUTED LEVEL (C3) — an argus `high` batch over the seeded set is the
next datum to collect (its L4 lens should close the injection gap).
Timing: codex 255-758 s/case (avg ~7 min).
