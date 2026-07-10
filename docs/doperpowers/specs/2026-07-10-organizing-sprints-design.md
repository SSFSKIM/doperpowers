# organizing-sprints — restructuring issue-register around real sprint usage (2026-07-10)

## Purpose

`issue-register` (cluster many raw ideas → grill each to pre-spec → register
tickets, hard-gated against writing any spec) never matched how
multi-observation dumps were actually processed. Across two real milestones
of the consumer project ida-solution (M4 from a ~3-hour meeting transcript,
M4.5 from a team E2E-walkthrough ideadump), the human hand-drove a richer
pipeline every time: atomize the note → ground every observation in the
codebase → grill until all questions land → author a 700–1000-line umbrella
sprint spec (streams → epics with decision logs, verified current state,
observable acceptance criteria, dependency maps, deferred-milestone
reservations) → materialize the spec onto the GitHub board (18–45 tickets
with milestone, epic labels, `--parent`/`--blocked-by` edges, dispositions
of existing tickets, board-lint 0 FAIL).

This spec renames and restructures the skill to encode that pipeline:
`skills/issue-register` → `skills/organizing-sprints`.

## What real usage showed

- **The old hard gate was the wrong seam.** "Do NOT write a spec" is
  precisely what real usage crossed every time — the umbrella spec IS the
  product; the board derives from it. The seam that actually held is
  different: the umbrella carries observable acceptance criteria but no
  per-epic implementation plans (delegated epics derive their own ExecPlan
  from the document at dispatch time).
- **Grill sequencing matters.** M4 authored v1 then needed a grill-confirmed
  v2 ("그릴 확정판"); M4.5 grilled first and v1 was born landed ("그릴 선행
  확정판"). The improvement is encoded as ordering, not advice.
- **Grounding is load-bearing.** Observations misread code reality: a
  weekly-view observation described the current layout as the opposite of
  what the code renders (building from the note would have shipped the
  reverse of the requirement); onboarding inputs believed consumed were dead
  (collected, never stored, never read); features assumed built were absent.
  The verification table (bug / misread / built / partial / not-built, with
  file:line evidence) became the spec section everything else builds on.
- **The register was a fragment, not a product.** M4.5's own Decision Log
  (#18) rejected re-running issue-register on already-materialized tickets
  as "duplicate process" — the sprint pipeline had already done the
  clustering, grounding, grilling, and registration that skill described.

## Design (summary — the skill body is the source of truth)

- Eight-phase pipeline: atomize → ground in code → tentative
  streams/epics (present before grilling) → grill to landed decisions →
  author the umbrella spec → self-review + human review gate → materialize
  onto the board → hand off with the spec alive through the sprint.
- Two hard gates: MULTIPLE observations only (kept; single idea →
  brainstorming), and materialization gated on the human approving the
  written spec (new; replaces stop-at-pre-spec).
- `references/sprint-spec-template.md` carries the 17-section skeleton
  distilled from the two real specs, including the notation legend
  (`[BUILT]/[PARTIAL]/[NOT-BUILT]/[BUG]/[MISREAD]`,
  `[DECIDED]/[DECIDED-AUTO]/[EXTERNAL: owner]`, `(new)/(modify)/(promote)`)
  and the epic anatomy (context → decision log → verified state → work
  items → observable acceptance → dependencies).
- The pre-spec bar survives at ticket-body granularity: materialized bodies
  stay self-contained (a fresh-context worker gates from the body alone) —
  doperpowers:implementing-tickets' gate is unchanged.
- Cross-references updated: issue-tracker (birth channel ×1, deferral rule
  ×1), reviewing-prs (tech-debt gardening), orchestrating-daemons (routing
  table now points registration at issue-tracker).

## Acceptance

- A session handed a multi-observation note triggers organizing-sprints
  (not brainstorming, not raw issue-tracker registration), produces a spec
  containing a verification table and a Decision Log with rejected
  alternatives BEFORE any board write, and never registers tickets before
  the human approves the spec document.
- `grep -r "issue-register" skills/` returns only the deliberate successor
  note in organizing-sprints' own overview (so agents grepping the old name
  find the successor).
- All existing test suites pass (no test pinned issue-register content).

## Decision Log

1. **Name: `organizing-sprints`.** Rejected: `organize-sprint` (the human's
   working name) — repo convention is verb-first gerund
   (implementing-tickets, reviewing-prs, writing-plans). Rejected: keeping
   `issue-register` with a new body — the name anchors the old telos
   ("register issues"), but registration is now the last phase, not the
   product.
2. **The spec is the primary artifact; the board derives from it.**
   Rejected: tickets-primary with an optional spec — every real usage
   produced the spec, and downstream ExecPlans, sprint tracking, and
   retrospectives need a document, not a board.
3. **Grill-before-author as ordering, not advice.** Evidence: M4 v2 vs
   M4.5 v1 (born landed).
4. **Materialization stays inside this skill as a human-gated final phase**
   using issue-tracker's scripts. Rejected: splitting materialization into
   a separate skill — the seam is an approval gate, not a knowledge
   boundary, and the spec's tracking-map section already makes the phase
   session-portable.
5. **Mandatory verification table with file:line evidence.** Rejected:
   "explore the codebase" as soft guidance (the old skill's form) — the
   observed failure is building from a misread note, which soft guidance
   does not block; the table is a structural requirement (Match the Form to
   the Failure: omitted element → required slot).
6. **Verification approach: live shakedown on the next real organizing run**
   (M5 is already reserved in ida-solution's M4.5 §16), mirroring
   implementing-tickets' pending shakedown. The three hand-driven runs are
   the baseline (RED) evidence — the failure mode (the old skill going
   unused, its workflow hand-prompted instead) was demonstrated by reality,
   not synthesized. Rejected: synthetic pressure scenarios before release —
   they would re-test what real usage already demonstrated, and the skill's
   riskiest content (the template) is reference-shaped, not
   discipline-shaped.

## Surprises & Discoveries

- The consumer project had already discovered the skill boundary was wrong:
  M4.5 Decision #18 ("issue-register 재실행은 중복 프로세스") documents the
  rejection in the wild, before this redesign existed.
- No test in this repo pinned issue-register content — the rename ripples
  through prose cross-references only (4 sites in 3 skills).

## Outcomes & Retrospective

Pending — completed after the first live organizing run (expected: the M5
"moat maker" sprint organization in ida-solution).

## Revision Notes

- **2026-07-10 (same day, post-release review with the human).** Three
  adjustments. (1) Evidence granularity softened: the verification table
  stays a structural requirement (Decision 5's core stands), but the
  blanket per-row file:line demand is demoted to judgment — a surprising or
  contested classification cites file:line; an obvious one doesn't. The
  human's rationale: trust capable models to cite as needed; the observed
  failure was skipping *classification*, not skipping *citations*.
  (2) Materialized ticket bodies now cite their spec epic section (path +
  epic id) so ticket and spec point at each other — self-containment
  unchanged. (3) Restored three issue-register carryovers the rewrite had
  dropped: prefer multiple-choice grill questions where options are
  enumerable; ask when unsure whether two observations are one epic or two
  (over-merge vs over-split); the tunnel-vision warning against treating
  the whole dump as one project.
