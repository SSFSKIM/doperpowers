# The board's review loop on the native review lane

This spec is a living document: `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are kept current as the work proceeds, per `skills/brainstorming/references/living-spec.md`. The work is one unit, so this spec carries its own execution (`Plan of Work`, `Concrete Steps`) instead of pointing at an execution plan.

## Purpose

The board's Reviewer worker (doperpowers:qa-loops) is the last place a codex process runs in this repo's review path. Its START ENGINE step shells out to `skills/qa-loops/scripts/review-engine.sh`, which drives the codex app-server through the doperpowers:codex-companion runtime, and the protocol says so outright: "there is no second engine; the reviewer is codex-only." Every other review — SDE's task reviews and final review, the one-unit spec's exit, plan-executor's finish, the Architect's plan review — already runs on doperpowers:review-code's native lane: the registered reviewer agents (`doperpowers:reviewer-low|medium|high`, GPT models through the local gateway) and its panel workflow. The lane's design (`2026-09-09-review-code-lane-design.md`) recorded this port as its first follow-on. A second consequence of the gap: the verification call a spec records ("branch review at reviewer-high") reaches the board's loop only as "fan out more codex runs", not as the rung it names.

After this change the Reviewer worker dispatches the native lane itself — a rung agent through the Agent tool for low, medium, and high; the panel through the Workflow tool for xhigh and max — at a level it derives from the spec's verification entry, the operator's floor, and the diff's size. The codex script and its hermetic test move to the review bench, their only remaining consumer. Everything around the engine keeps its shape: the concurrent compliance audit, JOIN, the wave board, the round and wave caps, the `ENGINE-UNAVAILABLE` outage marker the sweep keys on, and the review trail.

Seeing it work: `grep -n -E 'codex|review-engine|CODEX_REVIEW' skills/qa-loops/SKILL.md` prints nothing; `ls skills/qa-loops/scripts` lists only `review-dispatch.sh`; `tests/qa-loops/test-skill-entrypoint.sh`, `tests/qa-loops/test-review-dispatch.sh`, `tests/qa-loops/test-bootstrap-parity.sh`, and `tests/review-bench/test-review-engine.sh` pass; a rendered reviewer prompt binds `REVIEW_LEVEL` and `REVIEW_CODE_DIR` and no `CODEX_REVIEW_*`.

## Progress

- [ ] Milestone 1 — the protocol: `skills/qa-loops/SKILL.md` START ENGINE rewritten on the native lane; ORIENT, JOIN, RE-REVIEW, ESCALATE, the scale section, AUTHORITY, and REVIEW TRAIL reworded where they named codex runs or `--base`/`--out` files.
- [ ] Milestone 2 — dispatch and references: `review-dispatch.sh` bindings (`REVIEW_LEVEL`, `REVIEW_CODE_DIR` replace `REVIEW_ENGINE`, `CODEX_REVIEW_MODEL`, `CODEX_REVIEW_EFFORT`), the bootstrap template, the operation manual, wave-board.
- [ ] Milestone 3 — relocation: `review-engine.sh` and `test-review-engine.sh` to `tests/review-bench/`; `run-case.sh` and the bench README follow.
- [ ] Milestone 4 — consumers and history: the implement protocol's one clause; Revision Notes on the review-code lane design, the PR review loop design, and the native-review recovery design.
- [ ] Milestone 5 — validation: tests updated and green, lint, the sweep in Acceptance 11, version bumped.
- [ ] Exit — branch review at `doperpowers:reviewer-high`, retrospective, PR.

## Acceptance

1. `skills/qa-loops/SKILL.md` START ENGINE names the lane as doperpowers:review-code's: `doperpowers:reviewer-low` / `-medium` / `-high` dispatched through the Agent tool for the single-reviewer levels, and the panel through `Workflow` on `{{REVIEW_CODE_DIR}}/workflows/code-review.js` for xhigh and max. It states the level rule — the highest of the rung the spec's verification entry names, the `{{REVIEW_LEVEL}}` binding, and review-code's size rule, ordered low < medium < high < xhigh < max, with a risk-surface hit or whole-branch scale as the worker's reason to go one rung up and nothing lowering a rung the spec named. It pins the range (`git merge-base origin/{{BASE_REF}} HEAD` and `HEAD`) into every brief, keeps lensed extra dispatches at single-reviewer levels only (one to three, `Lens for this review:` in the brief, diff-derived), runs the panel without a `repo` argument, saves each run's report to `<review-tmp>/findings-r<N>-<k>.md`, treats a hung run (45 minutes), a dispatch that dies before reporting, or a panel `interrupted` as a failed run with the sweep's failure failing the round, and reads the agents' `[P0]`/`[P1]` tags as the blocker classes. The words `codex`, `review-engine`, and `CODEX_REVIEW` do not appear in the file.
2. The runtime placeholder set of `skills/qa-loops/SKILL.md` and the bootstrap placeholder set of `skills/qa-loops/references/review-worker-bootstrap.md` contain `{{REVIEW_LEVEL}}` and `{{REVIEW_CODE_DIR}}` and none of `{{REVIEW_ENGINE}}`, `{{CODEX_REVIEW_MODEL}}`, `{{CODEX_REVIEW_EFFORT}}`; `tests/qa-loops/test-skill-entrypoint.sh` asserts both exact sets and passes.
3. `skills/qa-loops/scripts/review-dispatch.sh` defines no `CODEX_REVIEW_MODEL`, `CODEX_REVIEW_EFFORT`, or `REVIEW_ENGINE`; it resolves `REVIEW_LEVEL` from the environment (default `medium`, refusing any value outside `low|medium|high|xhigh|max` before any spawn) and `REVIEW_CODE_DIR` as the sibling `review-code` skill directory, and renders both at all three render sites (PR, scale, API). Its `ENGINE-UNAVAILABLE` handling is unchanged. `tests/qa-loops/test-review-dispatch.sh` asserts a rendered prompt binds `REVIEW_LEVEL` and `REVIEW_CODE_DIR`, carries no `review-engine.sh` or `CODEX_REVIEW`, and that an invalid `REVIEW_LEVEL` refuses to dispatch; it passes.
4. `skills/qa-loops/scripts/review-engine.sh` does not exist. `tests/review-bench/review-engine.sh` exists with the same contract, its companion path resolved as `$script_dir/../../skills/codex-companion`; `tests/review-bench/test-review-engine.sh` is the moved hermetic suite pointed at it and passes; `tests/review-bench/run-case.sh --engine codex` invokes the bench copy; the bench README says the codex baseline runs from the bench's own copy of the loop's former engine.
5. `skills/qa-loops/references/operation-manual.md` describes the engine as review-code's lane (overview, pieces table, the "Review engine + worker audit" section), lists the local gateway that serves the reviewer agents' models as the prerequisite in place of the codex CLI, and keeps the outage cap and marker semantics. `tests/qa-loops/test-skill-entrypoint.sh` asserts the manual no longer names `review-engine.sh` or `codex login`.
6. `skills/qa-loops/references/wave-board.md` says the worker saves the engine's findings into `<review-tmp>`; its fixer-boundary sentence ("You never: run the review engine or any review skill") is unchanged.
7. `skills/issue-tracker/references/implement-worker-protocol.md` describes the Reviewer's loop as review-code's lane plus fix waves, not an external engine.
8. Revision Notes: `2026-09-09-review-code-lane-design.md` records the follow-on as landed; `2026-07-08-pr-review-loop-design.md` records the engine swap; `2026-07-12-native-review-recovery-design.md` records that its "reviewer is codex-only" mandate was superseded by the human's direction of 2026-09-13.
9. `tests/qa-loops/test-skill-entrypoint.sh`, `tests/qa-loops/test-review-dispatch.sh`, `tests/qa-loops/test-bootstrap-parity.sh`, `tests/review-bench/test-review-engine.sh`, `tests/issue-tracker/test-protocol-content.sh`, and `scripts/lint-shell.sh` pass.
10. The version is bumped with `scripts/bump-version.sh minor` in the same PR.
11. `grep -rn -E 'review-engine|CODEX_REVIEW' skills agents scripts tests/qa-loops tests/issue-tracker tests/claude-code CLAUDE.md README.md docs/INSTALL-doperpowers.md` returns nothing; the bench directory and the dated design history are the only places the name survives.

## Design

**The engine is a role, not a binary.** qa-loops splits review three ways — the engine owns correctness of the whole range, fixers own edits, the worker owns audit, triage, grading, and the push chain. The port changes only who plays the engine: doperpowers:review-code's lane, dispatched by the worker from its own session. The word "engine", the START ENGINE section name, and the `ENGINE-UNAVAILABLE` marker stay: the dispatcher's outage streak, the sweep's re-dispatch, the manual's cap table, and four test suites key on the marker, and the role is what they describe.

**Why the worker dispatches, not a script.** A Reviewer worker is a sminos seat — a main session — so it has both tools the lane needs: the Agent tool for the rung agents and the Workflow tool for the panel (subagents lack the latter, probe-verified in the lane's design). A replacement script would have to run a headless `claude -p` around the workflow, and the bench found that a `-p` session cannot reliably wait on a background workflow. Dispatching in-session is also the shape every other consumer of the lane uses.

**Level.** Three signals, take the highest: the rung the spec behind the pin names in its verification entry (the pinned file itself, or the plan's `Spec:` header — its Decision Log's "branch review at reviewer-<rung>", or a panel level); the `REVIEW_LEVEL` binding, the operator's floor for the repo (default medium, review-code's own default); and review-code's size rule (xhigh once the diff is panel-sized). A risk-surface hit or whole-branch scale is the worker's reason to go one rung up. Nothing lowers a rung the spec named: the verification call was made from stakes by the author, before the work. This replaces the run-count knob (`CODEX_REVIEW_MODEL`/`EFFORT` plus 1–4 runs), which no longer maps onto anything.

**Fan-out.** At a single-reviewer level the lens-free dispatch is the required whole-range sweep; the worker may add one to three lensed dispatches of the same rung agent, each brief ending in `Lens for this review: <mandate>` (review-code's form), the mandate derived from the diff and the risk-surface manifest, never from the ticket or spec. That keeps the bench-validated lens cell (a lens recovered an authz defect two plain runs missed). At panel levels the deriver owns the lenses and the verifier dedups; the worker adds none. The panel runs without a `repo` argument: it reviews a fresh worktree at HEAD, so nothing it runs touches the worker's shared worktree, which stays read-only until JOIN as before.

**Findings.** Each run's report lands in the worker's context as the agents' `## Findings` / `## Verdict` (or the panel's result object). The worker writes it to `<review-tmp>/findings-r<N>-<k>.md` as it arrives, so the wave board's `source: native`, the trail's per-run record, and the tmp-cleanup rules are untouched. The agents tag priority `[P0]`–`[P3]`; P0 and P1 are the blocker classes the verdict sentence reads (the codex text said critical/high). Triage is still the worker's judgment.

**Failure.** A run that has neither completed nor failed 45 minutes after dispatch is stopped (TaskStop) and counted failed. A dispatch that dies before reporting — the gateway refusing, an agent returning no report — or a panel that returns `interrupted` on its sweep or verifier is a failed sweep, and a failed sweep fails the round. The fallback is unchanged: retry twice with a short backoff, then post the trail comment, touch no board state, and end with `ENGINE-UNAVAILABLE` on the last line. `needs-human` stays reserved for judgment.

**Bindings.** `REVIEW_ENGINE`, `CODEX_REVIEW_MODEL`, and `CODEX_REVIEW_EFFORT` leave the dispatcher, the bootstrap, and the skill. `REVIEW_LEVEL` (validated at dispatch) and `REVIEW_CODE_DIR` (the sibling skill directory, pinned by the dispatcher the way `IMPLEMENT_PROTOCOL_FILE` is) replace them. The worker's own model route (`engine:claude` / `engine:codex` labels, the clodex gateway settings) is about the worker and is untouched.

**The codex engine's new home.** `review-engine.sh` and its hermetic suite move to `tests/review-bench/`, where `run-case.sh --engine codex` is their only consumer: the bench's scored codex baselines remain re-runnable. The script's one edit is its companion path. codex-companion itself is untouched (human direction, 2026-09-09); deleting its panel is the lane design's own later follow-on.

**What does not change.** ORIENT's anchor rules, the compliance audit and its classes, JOIN's ordering, triage bins, the wave board and fixer contract, the 4-wave and 5-round caps, the closing wave, ESCALATE's merge gate (its mechanical-conflict rule needs "one lens-free sweep", now one lens-free dispatch at the review's level), the scale review (same lane; per-child ranges when the epic has no aggregate range, one dispatch per range with the brief's explicit-range form), AUTHORITY, and the trail's contents.

## Plan of Work

Milestone 1, the protocol. In `skills/qa-loops/SKILL.md`: the Role paragraph's "above all in START ENGINE's `--base origin/{{BASE_REF}}`" becomes the base every brief names; ORIENT keeps "the engine may be running its own"; START ENGINE is rewritten per the Design (level, brief, fan-out, panel call, JOIN bound, findings files, verdict sentence, fallback); JOIN's first sentence names background tasks rather than engine tasks with `--out` files; RE-REVIEW's "rerun the engine … fresh --out files" becomes fresh findings files at the same level; ESCALATE's conflict rule says one lens-free dispatch; the scale section's "whole-range codex runs" and "START ENGINE's `--base origin/{{BASE_REF}}`" become the lane and the brief's base, with per-child ranges as explicit-range briefs; AUTHORITY's "an engine outage stays ENGINE-UNAVAILABLE" stands; REVIEW TRAIL records the level and every dispatch.

Milestone 2, dispatch and references. `review-dispatch.sh`: the env comment block (drop the two `CODEX_REVIEW_*` lines, add `REVIEW_LEVEL` and its validation); lines 250–252 become `REVIEW_LEVEL` (validated) and `REVIEW_CODE_DIR`; the three render sites pass `P_REVIEW_LEVEL` and `P_REVIEW_CODE_DIR` instead of the three old bindings; the comment at 980–983 ("the codex CLI survives only as the review engine inside the worker") is corrected. `review-worker-bootstrap.md`: the three binding lines become two. `operation-manual.md`: overview sentence, the `review-engine.sh` row of the pieces table becomes a doperpowers:review-code row, the "Review engine (pure correctness) + worker audit" section, setup step 8. `wave-board.md` line 12.

Milestone 3, relocation. `git mv skills/qa-loops/scripts/review-engine.sh tests/review-bench/review-engine.sh`; edit its `companion=` line; `git mv tests/qa-loops/test-review-engine.sh tests/review-bench/test-review-engine.sh`; edit its `ENGINE=` line and header comment; `tests/review-bench/run-case.sh` codex branch path; `tests/review-bench/README.md` running paragraph.

Milestone 4, consumers and history. `implement-worker-protocol.md` line 158. Revision Notes on the three specs named in Acceptance 8; the 2026-09-09 spec's Outcomes gain a line that the follow-on landed.

Milestone 5, validation. `test-skill-entrypoint.sh`: the two placeholder lists; new assertions per Acceptance 1, 2, 5, 6. `test-review-dispatch.sh`: the assertions at 519–521, 1718, 1736 replaced per Acceptance 3, plus the invalid-level refusal. Run the suites in Acceptance 9, the sweep in Acceptance 11, `scripts/bump-version.sh minor`.

## Concrete Steps

Run from the worktree root.

    git mv skills/qa-loops/scripts/review-engine.sh tests/review-bench/review-engine.sh
    git mv tests/qa-loops/test-review-engine.sh tests/review-bench/test-review-engine.sh
    ls skills/qa-loops/scripts                      # expect: review-dispatch.sh

    tests/qa-loops/test-skill-entrypoint.sh
    tests/qa-loops/test-bootstrap-parity.sh
    tests/qa-loops/test-review-dispatch.sh
    tests/review-bench/test-review-engine.sh
    tests/issue-tracker/test-protocol-content.sh
    scripts/lint-shell.sh

    grep -rn -E 'review-engine|CODEX_REVIEW' skills agents scripts tests/qa-loops tests/issue-tracker tests/claude-code CLAUDE.md README.md docs/INSTALL-doperpowers.md
    # expect no output

    scripts/bump-version.sh minor

## Decision Log

- Decision: The Reviewer worker dispatches doperpowers:review-code's lane from its own session — the rung agents through the Agent tool, the panel through the Workflow tool — instead of a script that wraps the lane.
  Rationale: A Reviewer worker is a main session and has both tools; a wrapper script would need a headless `claude -p` around the workflow, which the bench found cannot reliably wait on a background workflow. Every other consumer of the lane dispatches it this way.
  Rejected: a new `review-engine.sh` that shells to `claude -p`; keeping a script boundary "for testability" — the seam that remains testable is the dispatcher's bindings, and those are tested.
  Date/Author: 2026-09-13

- Decision: The review level is the highest of the spec's verification rung, the operator's `REVIEW_LEVEL` floor (default medium), and review-code's size rule; the worker may raise it one rung for a risk-surface hit or whole-branch scale and never lowers a rung the spec named.
  Rationale: The verification call is the author's stakes call, made before the work; the operator's floor is the repo's; the size rule is the lane's own default. The old knob — a codex model and effort plus a 1–4 run count — maps onto none of these.
  Rejected: carrying `CODEX_REVIEW_MODEL`/`EFFORT` over as a model override — review-code pins models per level on purpose ("you never choose them").
  Date/Author: 2026-09-13

- Decision: "Engine" stays the name of the correctness-review role, START ENGINE stays the section name, and `ENGINE-UNAVAILABLE` stays the outage marker.
  Rationale: The dispatcher's outage streak, the sweep's re-dispatch verdict, the manual's cap table, and the qa-loops suites all key on the marker; the role is unchanged, only its player. A rename would touch every one of them for no behavior.
  Rejected: `REVIEW-UNAVAILABLE` and "START REVIEW".
  Date/Author: 2026-09-13

- Decision: Lensed fan-out survives at single-reviewer levels (one to three extra dispatches of the same rung agent with `Lens for this review:` in the brief); at panel levels the worker adds no lenses.
  Rationale: The lens cell is bench-validated (`tests/review-bench/results/2026-07-28-pr752-lenscell/`); review-code's brief has the slot. The panel's deriver and verifier already own lenses and dedup.
  Date/Author: 2026-09-13

- Decision: The panel runs without a `repo` argument.
  Rationale: Without it the workflow reviews a fresh worktree at HEAD, so nothing it runs can touch the worker's shared worktree; the worker's own worktree is a detached checkout of the same repo, so the fresh worktree is cut from the same object store at the same head.
  Date/Author: 2026-09-13

- Decision: `review-engine.sh` and its hermetic suite move to `tests/review-bench/`; codex-companion is untouched.
  Rationale: The bench's `--engine codex` is the script's only consumer after the port, and its scored codex baselines are evidence the lane design cites. The lane design already schedules the codex panel's deletion as a later follow-on, after the native lane has carried real reviews; this port is what lets it carry them on the board.
  Rejected: delete the script now (loses the re-runnable baseline); leave it in `skills/qa-loops/scripts` unused (a loaded skill carrying a dead path).
  Date/Author: 2026-09-13

- Decision: This reverses the 2026-07-12 mandate "the reviewer is codex-only" (`2026-07-12-native-review-recovery-design.md`).
  Rationale: The human's direction of 2026-09-13 ("go ahead and do the qa loop porting"), after the lane design of 2026-09-09 moved every other review onto the native lane and recorded this port as its follow-on. The 2026-07-12 mandate answered a Claude-subagent fallback that reviewed on Claude models; the native lane reviews on the same GPT models through the gateway, so the cross-model second opinion that mandate protected is kept.
  Date/Author: 2026-09-13 (human partner)

- Decision: Verification for this work: one independent spec review by `doperpowers:adversarial-reviewer` in the background during execution; branch review at `doperpowers:reviewer-high` (the loop is deployed and owns the merge path).
  Date/Author: 2026-09-13

## Surprises & Discoveries

- (pending — filled as the work proceeds)

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-09-13: created from the human partner's direction to port the review loop onto the native lane, after the state-of-the-repo check that found qa-loops the last codex consumer in the review path.
