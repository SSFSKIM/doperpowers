# PR752 model cells — model×effort×engine decomposition on one real PR (2026-07-27)

Human direction after the real-PR round: the diff-size explanation is
incomplete (codex sees the same diff in one context), so isolate the MODEL.
One target (ida-solution PR752, 22 files +2,101, merge base f7bb8b5), one
skill (argus-review v0.4.3 plain), one harness (Claude Code) — model/effort
varied via `ARGUS_CLAUDE_ARGS` (new run-case.sh passthrough, also applied to
the `claude --bg` builtin path). Upstream models verified: gateway alias
`claude-fable-5` → `gpt-5.6-sol` (cliproxyapi `oauth-model-alias`,
force-mapping) — cell A really ran Sol; cells B–D verified from transcript
model fields.

## Results (union of adjudicated real issues on PR752 = 13: 12 CONFIRMED + 1 PLAUSIBLE, FP 0 in every cell)

| cell | engine | model·effort | secs | findings | union hits | exclusives |
|---|---|---|---|---|---|---|
| — (r1) | codex CLI | Sol xhigh | 668 | 10 | **10/13** | C1, C7 |
| A | argus plain | Sol xhigh (gateway) | 825 | 9 | **8/13** | **N1** (new, P1/P2) |
| D | /code-review medium | Opus xhigh session | 684 | 5 | 4/13 (+1 lint-minor) | **N2** (new, P2) |
| B | argus plain | Opus xhigh | 720 | 4 | 4/13 | — |
| C | argus plain | Fable high | 426 | 4 | 4/13 | — |
| — (r1) | argus plain | Opus default | 341 | 2 | 2/13 | — |

Union key: C1 cohort re-derivation (disclosed-in-code), C2 backfill imprint,
C3 classifier mixing, C4 display paths, C5 non-atomic history, C6 fail-open
onboarding guard, C7 write-before-validate, F1 revert-as-correction,
F2 stale profile page, C10 dead fingerprint wiring (PLAUSIBLE), F3
rate-limit bucket bypass, N1 backdated-grade mis-stamping (argus-Sol only),
N2 goal-gap over-suppression (medium only).

New candidates adjudicated this round (fable adjudicator, quoted evidence):
- **N1 CONFIRMED (P1/P2)**: both grade-write routes stamp from CURRENT type
  while accepting a backdated `grade_level` the UI freely offers; a
  promoted student entering prior-period 내신 gets contradictory provenance
  vs the promotion route's own old-type stamping, plus 6-9 grades accepted
  for a g5 period. The p143 header itself concedes the premise dies with
  #208. codex missed it.
- **N2 CONFIRMED (P2)**: `stampGradeSystem` marks all mock rows g9 while
  고1·2 currentSystem is g5, so the new crossSystem suppression nulls the
  목표 갭 for essentially every mock subject of the whole g5 cohort —
  same-scale target was computable from the same file (`targetGradeFor`).
  Every other engine missed it; argus's r1 verdict had called this area
  "well tested".

## Conclusions

1. **The gap is mostly MODEL, and it is large.** Same skill, same harness,
   same prompt: Opus default 2 → Opus xhigh 4 → Sol xhigh 8(+1 exclusive).
   Sol doubles the best Claude cell; effort buys ~+2, the model swap ~+4-6.
   Fable high == Opus xhigh in count (different mix).
2. **Harness residual is small: codex CLI 10 vs argus-Sol 8 at the same
   model·effort** — and the symmetric difference is 4 (codex-only C1+C7 vs
   argus-Sol-only N1+F3), so quality-adjusted (C1 = disclosed-limitation
   restatement) the scaffold advantage is thin. The 10-vs-2 spectacle of r1
   was ~80% model.
3. **Claude has a stable attention signature**: every Claude cell caught
   F1+F3 (authz-shape + UI-contract issues; codex missed F3 in both its
   runs' families), and both xhigh Claude cells caught C10 (dead wiring)
   which plain missed. Claude cells go deep on wiring/authz; Sol-class
   models sweep provenance consumers broadly.
4. **No single engine exceeded 10/13; the 6-cell union is 13.** Ensemble
   coverage on a real PR is materially better than any engine alone —
   directly relevant to C3's multi-lens design and to the engine-mix
   question in C4 (a Claude lens adds exclusives even next to Sol).
5. `/code-review medium` on Opus xhigh: 5 findings incl. the day's best
   exclusive (N2) and F2 which all argus-Claude cells missed — the minimal
   symmetric-stance prompt again punches above its size; honest about not
   running tests (no node_modules).

Follow-ups: N1/N2 belong in any report to ida-solution (both P2+, both
merge-relevant). X1 fixture round 2 (#40) gains two real-PR-sourced
candidate patterns (backdated-write provenance; suppression-vs-lookup).
