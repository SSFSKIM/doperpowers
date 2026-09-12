# One spec, sized by the gate

This spec is a living document: `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are kept current as the work proceeds, per `skills/brainstorming/references/living-spec.md`. The work is one unit, so this spec carries its own execution (`Plan of Work`, `Concrete Steps`) instead of pointing at an execution plan.

## Purpose

doperpowers has described itself as two development tracks, "controlled" and "autonomous". Since the Architect fold (v7.82.0) both run the same way: a grill closes the design questions while the human partner is present, execution proceeds without stopping, and a fork the plan does not cover returns to the plan's author. What still differed was the artifact (a spec plus an execution plan against a single ExecPlan) and the names, which promised a difference in human control that no longer existed.

After this change there is one primary artifact, the living spec, and one gate, decomposing's: can one agent reliably own the work as one unit? Work that is one unit gets a spec that carries its own execution and is run sequentially. Work that is several units gets the spec plus an execution plan and a fresh subagent per task. How much independent review the work gets is a separate call made from its stakes, not its size. The routing criteria brainstorming has used at step 4 stay verbatim; only their destinations are renamed.

Seeing it work: a session reading `skills/brainstorming/SKILL.md`, `skills/issue-tracker/references/architect-worker-protocol.md`, or `README.md` finds one method whose shape follows the size of the work and no track names; `ls skills/execplan` fails and `archive/execplan/SKILL.md` exists; `shasum -a 256 skills/brainstorming/references/PLANS.md` prints the checksum recorded in Concrete Steps; `tests/issue-tracker/test-protocol-content.sh` passes with its new assertions.

## Progress

- [x] (2026-09-12 12:10Z) Milestone 1 — the artifact: living-spec.md binds the inline execution sections and conditions the superseded rows; PLANS.md moved byte-identical; execplan archived.
- [x] (2026-09-12 12:15Z) Milestone 2 — brainstorming's path: renamed destinations at step 4 with criteria kept verbatim, the design presented on every route, the verification call, step 9 by route.
- [x] (2026-09-12 12:50Z) Milestone 3 — consumers: writing-plans, plan-executor, Architect protocol, implement protocol, ticket-gate, issue-tracker SKILL, decomposing (+ composite template), organizing-sprints, SDE, execution-loop, triage protocol, CLAUDE.md.
- [x] (2026-09-12 12:35Z) Milestone 4 — README pitch, diagram, "One method, sized by the work", skill list, flow section.
- [x] (2026-09-12 13:05Z) Milestone 5 — validation: protocol-content assertions added; sweep clean; routing check passed (three of three, after the one-unit scenario was resized); suites and lint green; version bumped to 7.84.0.
- [x] (2026-09-12 13:40Z) Exit — branch review at the high rung (three findings, all addressed: route keys the hand-off; no task-boundary callback promise; stale two-track surfaces), retrospective written; PR #138 opened.
- [ ] Milestone 6 — board seams, from a peer session's review of #138: the review loop owns the whole-branch review on the board (plan-executor stops before it when the brief says so, and writes the retrospective); plan-executor's sequential mode states its exit; a small ticket builds in the Architect's session from its body over a `pre-spec` build edge; the plan route parks for the human's design approval; writing-plans registers residue as direct tickets.

## Acceptance

1. `skills/brainstorming/SKILL.md` step 4 keeps its three criteria sentences ("Well-scoped and delegable…", "Large, novel, taste-heavy, or high-stakes…", "Narrow and small…") unchanged in wording, and their destinations read: a spec that carries its own execution, run sequentially; a spec plus an execution plan through doperpowers:writing-plans; direct. The words "controlled" and "autonomous" do not appear in the file.
2. The path paragraph states that every route that stays in the skill runs steps 1–5 (the design is presented on every route) and that step 9 hands off by route; the single-unit route's execution contract is stated there: isolated workspace, the Plan of Work worked in order without stopping for next steps, Progress and living tail kept current, frequent commits, branch review at the rung the verification call named, retrospective, integration. The gate is the one stop during execution: a fork under it that the spec does not cover goes to the human partner; everything else is decided and logged. `living-spec.md`'s superseded table says the same of PLANS.md's "do not prompt for next steps" directive: superseded by the human gates at authoring, binding during execution of a spec that carries its own execution.
3. Step 4 also names the verification call with its defaults: one independent spec review by default; a critique debate when the design is novel or the cost of being wrong is high; the adversarial plan review whenever an execution plan exists; the branch review rung; recorded as a Decision Log entry in the spec.
4. `skills/brainstorming/references/living-spec.md` says that a spec brainstorming routed to carry its own execution (the route, not a re-derived unit count, is the condition) binds PLANS.md's `Progress` (placed after the purpose; "as written" includes PLANS.md's timestamps on completed items), `Plan of Work` (told as milestones per PLANS.md's Milestones section when the work has stages), and `Concrete Steps` as written, and `Interfaces and Dependencies` when the work defines new interfaces; its superseded table conditions the Progress and Milestones/Concrete Steps rows on an execution plan existing and the "do not prompt for next steps" row on authoring versus execution; its PLANS.md link resolves to `skills/brainstorming/references/PLANS.md`.
5. `skills/brainstorming/references/PLANS.md` exists with the checksum recorded in Concrete Steps; `skills/execplan/` does not exist; `archive/execplan/SKILL.md` exists.
6. `agents/plan-executor.md` `## Mode` describes the non-SDE file as a spec that carries its own execution, worked in order, and no longer says "ExecPlan".
7. `skills/issue-tracker/references/architect-worker-protocol.md` `## Design` has a route bullet ("Route the plan", by brainstorming's step 4 criteria: well-scoped and delegable → the spec carries its execution; large, novel, taste-heavy, or high-stakes → spec plus execution plan) and a verification bullet with the defaults from item 3, replacing "Track judgment (council scaling)"; `## Build` names the artifact the brief carries (the spec, or the execution plan and its spec) and says a spec carrying its own execution runs sequentially. `tests/issue-tracker/test-protocol-content.sh` asserts the route and verification bullets are present and "Track judgment" is absent, and passes.
8. `skills/writing-plans/SKILL.md`'s description no longer says "multi-step" or counts units — it applies when a spec needs an execution plan; `skills/issue-tracker/references/implement-worker-protocol.md` resumes from the ledger or the spec's `Progress`; `skills/issue-tracker/references/ticket-gate.md` and `skills/issue-tracker/SKILL.md` no longer name an ExecPlan or a controlled-track build; `skills/decomposing/SKILL.md` and `skills/decomposing/references/composite-spec-template.md` call the child hint the grain hint, the skill says a leaf dispatches by its route and no longer says the tracks execute the leaves, and its Common Mistakes has no ExecPlan row; `skills/organizing-sprints/` says an epic's Architect derives its plan at dispatch time (a sprint epic is a board ticket, so the Architect lane's artifact rule applies, not decomposing's leaf-child rule); `skills/subagent-driven-execution/SKILL.md`'s final whole-branch review runs at the rung the spec's verification entry names, or the level the branch warrants when none is recorded; `skills/issue-tracker/references/execution-loop.md` no longer says there is no in-daemon living-spec mode; `application-agents/triaging-feedback/references/triage-worker-protocol.md` sizes tickets by agent-ownable units, not ExecPlans; `CLAUDE.md`'s repo map says 17 skills and describes plan-executor without "ExecPlan".
9. `README.md` opens with the sizing pitch in Decision Log entry 9; the diagram shows idea → grill → design → spec forking into one unit and several units, with the board loop as the same method while nobody watches; "Two tracks, one discipline" becomes "One method, sized by the work" with three paragraphs — one unit, several units, and unattended (the board loop, review loop, seat registry, and feedback triage keep their home there); the skill list has no `execplan` line and says seventeen skills; "How the controlled track flows" is "How a change flows" with brainstorming routing by size as its first step.
10. `grep -rn -i -E 'controlled track|autonomous track|execplan|track hint' skills agents README.md CLAUDE.md tests/issue-tracker application-agents` returns only: `skills/brainstorming/references/PLANS.md` (the vendored source), `skills/brainstorming/references/living-spec.md:13` (names the doctrine's origin), `skills/sminos/SKILL.md:22` (cites existing dated files), `skills/issue-tracker/scripts/board-lint.sh` (a comment citing the design that produced it), `CLAUDE.md`'s archive row (the retired directory's name), and `tests/issue-tracker/test-protocol-content.sh:76` (asserts a retired mode is absent).
11. Routing check: three fresh subagents, each given the new `skills/brainstorming/SKILL.md` and one request, name the expected route and artifact: a one-unit change (a multi-file feature whose design is closed and that must land as one piece) → a spec that carries its own execution, run in this session; a several-unit feature with taste expected mid-flight → a spec plus doperpowers:writing-plans; a one-line fix → direct, no artifact.
12. `tests/issue-tracker/test-protocol-content.sh`, `tests/issue-tracker/test-board-scripts.sh`, `tests/issue-tracker/test-execute-dispatch.sh`, `tests/issue-tracker/test-board-sweep.sh`, and `scripts/lint-shell.sh` pass; the version is bumped with `scripts/bump-version.sh` in the same PR.

Milestone 6 (board seams):

13. `agents/plan-executor.md` has a `## Finishing` section: the whole-branch review and its fix loop are the executor's unless the brief says a review loop owns them, in which case it stops after the last frontier review or milestone; it writes the spec's `Outcomes & Retrospective` before the PR; a ticket body counts as a plan with no living sections; `## Closing` no longer says "final review is clean".
14. The Architect protocol's build brief says the review loop owns the whole-branch review; its down-shortcircuit takes the build edge `in-progress "direct: pre-spec suffices as the plan" --branch <b> --plan pre-spec` and dispatches plan-executor on the saved ticket body, with the `ready-for-implementer --plan pre-spec` handoff only when the edge is refused; the spec-plus-execution-plan route parks ONE needs-human question ("approve the design at <spec>@<sha>") before writing-plans; "If Resumed With Answers" says a design approval resumes into writing-plans. `test-protocol-content.sh` asserts all three.
15. `board-transition.sh` accepts `--plan pre-spec` on `in-design → in-progress` for a leaf when a branch is given or recorded, and refuses it with a message containing `needs --branch` otherwise, on both bindings' guards; `test-board-scripts.sh` covers the accept and the refusal, and the epic refusal stands.
16. `skills/qa-loops/SKILL.md` anchors a pre-spec pin minted on the build edge (`[board] in-progress: direct:`) on the ticket's `[gate] pass` like any pre-spec ticket; `skills/issue-tracker/SKILL.md`'s `in-design` and `ready-for-implementer` rows describe the sentinel on the build edge and the handoff as the refused-edge fallback.
17. `skills/writing-plans/SKILL.md`'s Execution Handoff says the executor's residue is registered as board tickets that a peer seat builds direct from the body.

## Design

**The principle.** One gate, decomposing's, applied at every altitude: a goal that fails it divides into children; a leaf whose work is several units gets an execution plan and per-task workers; one unit is one agent's sequential work. Verification depth is a separate call made from stakes. Execution at every altitude runs without stopping until it meets a decision the plan does not cover, which returns to that plan's author.

**The router stays.** Brainstorming's step 4 criteria read two signals off the grill: the size of the work and how much of the author's judgment the build will need. The plan shape carries that judgment into per-task briefs and reviews every task at its boundary before downstream work consumes it; the sequential shape has one review, at the end. (In an interactive session the SDE loop runs inside a plan-executor subagent and returns only on completion or BLOCKED — the author is not re-engaged at task boundaries, and the skills must not promise that.) Taste-heavy work therefore benefits from the plan shape even when it is one unit, and a large routine change can run as one sequential executor. The criteria have served well and are kept verbatim; only their destinations change name. Because the second criterion can select the plan shape for one-unit work, **the route step 4 named — not a re-derived unit count — keys the artifact and the hand-off** in brainstorming, living-spec, writing-plans' description, and the Architect protocol.

**The artifact.** The spec is always the primary document at `docs/doperpowers/specs/`. For one unit it also carries its execution: `Progress` after the purpose as its ledger, `Plan of Work`, `Concrete Steps`, and `Interfaces and Dependencies` when new interfaces are defined, all bound from PLANS.md as written at the living-spec bar (a fresh session with no history can continue). For several units doperpowers:writing-plans produces the execution plan, the SDE ledger tracks progress, and the spec's execution section is one line naming the plan file. A child of a composite spec is unchanged: its section is its spec and its ledger file or plan is its record, which is this same rule with the record externalized because the composite is shared by parallel siblings. A child also inherits the composite's verification call — the composite's spec review covered its design — and its route's own reviews cover its residue, which is why brainstorming skips step 8 for it. New single-unit specs go under `specs/`; `docs/doperpowers/execplans/` is history.

**Brainstorming's path.** Steps 1–3 unchanged. Step 4: route by the existing criteria and name the verification call. Step 5: present the design on every route that stays in the skill. Steps 6–8: the spec (with its execution inline for one unit), self-review, the independent spec review. Step 9 by route: several units → writing-plans; one unit → execute here under the contract in Acceptance 2; a coupled goal that fails the gate → decomposing. Direct implements after step 5 as today. Ordering of review and execution differs by who executes: in this session the author is the executor and can absorb review findings as they land, so the spec review may run while execution proceeds; a spec handed to a zero-context executor (the board's build edge) is reviewed before the handover, since that executor can only return BLOCKED.

**The verification call.** Defaults: one independent spec review; a critique debate when novel or high-cost; the adversarial plan review whenever a plan file exists; the branch review rung, which the SDE final review and the single-unit exit both read. Recorded as a Decision Log entry so the executor, the reviewer, and a recovering session read the same council.

**The board.** The Architect protocol's "Track judgment (council scaling)" splits into size and verification bullets. The build brief names the artifact the executor opens; the pin points at that file, so board-transition, the pin format, and qa-loops do not change. Plan-executor keeps its mode key: a header naming subagent-driven-execution makes it the controller, any other file it works in order. The Executor's recovery lane resumes from the SDE ledger or the spec's Progress.

**Retirements and renames.** execplan → `archive/execplan/`; PLANS.md → `skills/brainstorming/references/PLANS.md` byte-identical; the vocabulary changes listed in Acceptance 8; the README per Acceptance 9. Historical citations (board-lint's comment, sminos's line about dated files) stay.

## Plan of Work

Milestone 1, the artifact. Move `skills/execplan/references/PLANS.md` to `skills/brainstorming/references/PLANS.md` with `git mv` and confirm the checksum. Move `skills/execplan/SKILL.md` to `archive/execplan/SKILL.md` with `git mv` and add one line at its top saying it is retired and where its content went. Remove the empty `skills/execplan/references` and `skills/execplan` directories the moves leave behind. In `living-spec.md`: fix the source link; add a paragraph after "The bar" stating what a one-unit spec additionally binds; rewrite the Progress row and the Milestones/Concrete Steps row of the superseded table as conditional on an execution plan existing, and the "do not prompt for next steps" row as authoring-versus-execution; add one sentence to the living tail saying the verification call is a Decision Log entry.

Milestone 2, brainstorming. In `SKILL.md`: the path list (step 4 title, step 9 title), the paragraph after it (every route runs 1–5; direct implements after 5; one unit and several both write the spec; step 9 by route), the intro sentence "without another design or track approval", the child paragraph's "track hint" → "grain hint", the `## Choosing the track` section retitled and its destinations renamed with the criteria sentences untouched, the verification-call paragraph added there, the closing handoff paragraph in `## The spec` rewritten by route.

Milestone 3, consumers. `skills/writing-plans/SKILL.md` description. `agents/plan-executor.md` Mode paragraph. Architect protocol: Design bullets, Build brief and the sequential/controller sentence, the "ExecPlan's Progress" mention. Implement protocol lines 45 and 150. Ticket-gate line 38. Issue-tracker SKILL line 398. Decomposing: lines 16, 52, 57, 60–61, 105, 220, 252, 307, 321 (merge the ExecPlan row into the leaf-child row) and `references/composite-spec-template.md`'s two "track hint" lines. Organizing-sprints SKILL lines 16, 63, 185 and template lines 18–20. Subagent-driven-execution: the final whole-branch review's rung (step 7 and the Model selection close). `execution-loop.md`'s "no in-daemon living-spec mode" sentence. The triage worker protocol's ticket-sizing line. CLAUDE.md repo map: agents row, skills count, archive row.

Milestone 4, README. Diagram, pitch paragraph, the "Two tracks, one discipline" section, the skills list line and count, the flow section.

Milestone 5, validation. Extend `tests/issue-tracker/test-protocol-content.sh` per Acceptance 7. Run the sweep in Acceptance 10. Dispatch the three routing-check subagents. Run the suites and lint. Bump the version (minor).

Milestone 6, board seams (after #138 and #139; on a branch stacked on `fold-plans`). `agents/plan-executor.md`: name the ticket body as a third file kind in the intro, add `## Finishing` (review ownership keyed to the brief; retrospective before the PR), drop "the final whole-branch review" from the SDE controller list, reword `## Closing`. Architect protocol: a design-approval bullet after "Name the verification"; the down-shortcircuit bullet rewritten around the pre-spec build edge with the handoff as fallback; the build brief's review-ownership clause and the ticket-body file kind; the "other exits" paragraph; one sentence in "If Resumed With Answers". `board-transition.sh`: in both bindings' `--plan` guards, replace the pre-spec-on-build-edge refusal with a branch requirement. Tests per Acceptance 14–15. `qa-loops/SKILL.md` anchor sentence; `issue-tracker/SKILL.md` two vocabulary rows; `writing-plans/SKILL.md` residue sentence. Decision Log entries for the three policy choices. Version 7.86.0.

## Concrete Steps

Run from the worktree root.

    shasum -a 256 skills/execplan/references/PLANS.md      # record before the move
    git mv skills/execplan/references/PLANS.md skills/brainstorming/references/PLANS.md
    shasum -a 256 skills/brainstorming/references/PLANS.md  # must match
    mkdir -p archive/execplan && git mv skills/execplan/SKILL.md archive/execplan/SKILL.md
    rmdir skills/execplan/references skills/execplan          # git mv leaves the empty tree behind
    ls -d skills/*/ | wc -l                                    # expect 17

PLANS.md checksum (SHA-256) before the move: `86b545172b5830f1b454800b1ea2940266849f587e30c3b1e1fadce3351c3cf0`.

    grep -rn -i -E 'controlled track|autonomous track|execplan|track hint' skills agents README.md CLAUDE.md tests/issue-tracker application-agents
    # expect only the exemptions in Acceptance 10

    tests/issue-tracker/test-protocol-content.sh
    tests/issue-tracker/test-board-scripts.sh
    tests/issue-tracker/test-execute-dispatch.sh
    tests/issue-tracker/test-board-sweep.sh
    scripts/lint-shell.sh
    scripts/bump-version.sh minor

## Decision Log

- Decision: One primary artifact, the living spec, for every size of work; the ExecPlan file shape retires.
  Rationale: After the Architect fold the two tracks differed only in artifact and name. The spec is the document reviewers, the board, decomposing, and finishing all address; keeping a second file shape for one-unit work duplicated the living tail and split the vocabulary. This reverses the 2026-07-03 living-specs decision "ExecPlan enters as norms, never as envelope": that decision rested on human gates and layered docs that no longer distinguish the shapes, and on context economics, which is accepted here as a cost — a one-unit spec carrying Plan of Work and Concrete Steps is longer for every reader, and that is the price of one document being both the contract and the executor's memory.
  Rejected: keep two shapes and only rename — leaves two authoring guides and two directories for one kind of document.
  Date/Author: 2026-09-12 (human partner)

- Decision: The living-spec bar (a fresh session with no history can continue) governs one-unit specs too; PLANS.md's novice bar and prose-only formatting do not return.
  Rationale: One document, one bar. Novice-grade self-containment duplicates repo knowledge into the spec and drifts. PLANS.md stays vendored as the source of the norms that bind.
  Rejected: PLANS.md to the letter for the one-unit shape — two bars for one document class.
  Date/Author: 2026-09-12 (human partner)

- Decision: A one-unit spec binds PLANS.md's Progress (with its timestamps), Plan of Work (told as milestones per the Milestones section when the work has stages), Concrete Steps, and (when interfaces are defined) Interfaces and Dependencies, as written.
  Rationale: This reverses the 2026-07-03 decision "Do not import the Progress section", which reasoned from the SDE ledger's existence; a one-unit spec has no ledger, so Progress is its ledger. Binding by section name keeps living-spec's rule that details die in paraphrase. Milestones are not a separate section: PLANS.md's own text says milestones tell the story and Progress tracks the work, and the Plan of Work is where that story is told.
  Rejected: a single `## Execution` section of our own shape — paraphrases the norms living-spec vendors by name.
  Date/Author: 2026-09-12

- Decision: Brainstorming's step 4 routing criteria stay verbatim; only the destinations are renamed.
  Rationale: The criteria read both size and how much of the author's judgment the build will need, and the plan shape carries that judgment into per-task briefs and boundary reviews. They have routed well in practice and did not judge too early. Corollary (branch review, 2026-09-12): the route selected at step 4 keys the artifact and the hand-off downstream; re-testing unit count there would contradict the route for taste-heavy one-unit work.
  Rejected: replace the criteria with a pure unit-count sizing — drops the mid-flight-judgment signal the plan shape serves.
  Date/Author: 2026-09-12 (human partner)

- Decision: The design is presented on every route.
  Rationale: The presentation catches forks that first appear while composing the whole design; it costs one message. The autonomous route used to leave before it.
  Rejected: keep skipping it for one-unit work.
  Date/Author: 2026-09-12 (human partner)

- Decision: Verification depth is a separate call made from stakes, stated at step 4 and recorded as a Decision Log entry. Default: one independent spec review; critique debate when novel or high-cost; adversarial plan review whenever a plan file exists; the branch review rung named.
  Rationale: "Controlled versus autonomous" bundled size and stakes; the Architect protocol's council scaling tied review depth to artifact shape. A small high-stakes change and a large routine one need opposite treatment on each axis.
  Rejected: keep the council tied to shape; branch review only by default (defects would surface as BLOCKED from a zero-context executor instead of before execution).
  Date/Author: 2026-09-12 (human partner)

- Decision: Track names go; what is named is the artifact ("spec", "execution plan") and the route criteria. The execplan skill is archived; its authoring content lives in living-spec.md and its execution contract in brainstorming step 9 and plan-executor.
  Rationale: Once the artifact is one and the escalation rule is one, "track" has nothing left to name.
  Rejected: "single-unit / multi-unit" as shape names; keeping "ExecPlan" as the name of the inline shape.
  Date/Author: 2026-09-12 (human partner)

- Decision: A child of a composite spec is unchanged (section as spec; ledger file or plan as record).
  Rationale: The composite is shared by siblings on parallel branches and cannot carry per-child Progress; decomposing's ledger file already externalizes the execution record for exactly that reason.
  Date/Author: 2026-09-12

- Decision: README pitch, approved wording: "Most agent scaffolding is a single linear pipeline: you talk, it plans, it codes. doperpowers sizes the work first. Every change starts with a grill that closes the design questions while you are present, then a design you approve. From there the shape follows the size: a change one agent can own gets a spec that carries its own execution and runs sequentially; a larger one gets an execution plan and a fresh subagent per task, reviewed at every boundary. How much independent review the work gets is a separate call, made from its stakes rather than its size. Either way the agent runs without stopping until it meets a decision the design did not cover, and that comes back to you."
  Date/Author: 2026-09-12 (human partner)

- Decision: The pin names whatever file the executor opens; board mechanics do not change.
  Rationale: The executor brief already carries the plan path and spec path; qa-loops and board-transition are path-agnostic.
  Date/Author: 2026-09-12

- Decision: In an interactive session, one unit is executed inline by the author; several units dispatch a `doperpowers:plan-executor` subagent as the SDE controller. On the board the Architect dispatches plan-executor for both.
  Rationale: The author already holds the design and, for one unit, there is no controller loop to keep out of its context; dispatching would only add a hand-off. The SDE loop is the case where a separate context pays, and the board Architect must stay bound to the ticket either way. (Carried over from the Architect-fold session, 2026-09-10; previously recorded only in CLAUDE.md's repo-map row.)
  Date/Author: 2026-09-12

- Decision: Review-before-execution depends on who executes: in-session, the spec review may run during execution; on the board, the reviews the verification call names run before the build edge.
  Rationale: The in-session author absorbs findings as they land; a zero-context executor can only return BLOCKED, so its spec must be reviewed before it is handed over.
  Date/Author: 2026-09-12

- Decision: Verification for this work: no critique debate (the design was argued with the human partner directly over two rounds), one independent spec review in the background during execution, branch review at `doperpowers:reviewer-high`.
  Date/Author: 2026-09-12

- Decision: On the board, the review loop (doperpowers:qa-loops) owns the whole-branch review until the Reviewer fold; the Architect's brief tells plan-executor so, and it stops after its last frontier review or milestone, writes the spec's retrospective, and opens the PR. An interactive writing-plans dispatch says nothing, so SDE's final review still runs there, where no review loop follows.
  Rationale: A peer session's review of #138 found the architect lane reviewing twice (SDE step 7's loop, then qa-loops with its own engine and fix waves) while the implement lane tells its worker the loop is the Reviewer's. One rule for both lanes, keyed to the brief; phase 2 (the Reviewer folded into the Architect session) later makes the in-session review the merge review and removes the flag.
  Rejected: fold the Reviewer now — a larger change across qa-loops, the sweep, and the in-review state, out of this seam's scope.
  Date/Author: 2026-09-13 (human partner)

- Decision: A ticket that turns out small is built in the Architect's own session from its ticket body: the build edge accepts `--plan pre-spec` for a leaf (branch required), and plan-executor runs the saved body as a plan with no living sections. The `ready-for-implementer --plan pre-spec` handoff remains as the refused-edge fallback.
  Rationale: The peer review noted "one session owns the ticket from design to PR" held only for the two planned shapes. The ticket body is the brief a direct ticket needs, an Opus implementer can run from it at once, and the lane hop plus a fresh seat's orientation cost more than the small build holds the architect seat for. Reverses the 2026-09-10 "down-shortcircuit unchanged" call, which weighed the seat cost the other way before the executor was a subagent.
  Date/Author: 2026-09-13 (human partner)

- Decision: The board form of brainstorming's design-approval gate: on the spec-plus-execution-plan route the Architect parks ONE needs-human question (approve the design at the spec's pin) after the spec and its reviews, and continues into writing-plans on the answer. The well-scoped route builds without asking.
  Rationale: A daemon has no synchronous human; the board parks taste forks but left substantive design to the Architect plus critique, which is a policy choice rather than a mirror of the live gate. Large, novel, taste-heavy, or high-stakes work is exactly what a live session would not build unapproved. One park per such ticket is the intended autonomy setting for now.
  Date/Author: 2026-09-13 (human partner)

- Decision: Residue from an interactive plan-executor run is registered as board tickets and built direct from the body by a peer seat.
  Rationale: The Architect already does this on the board; writing-plans said nothing. Residue is bounded by construction, so the direct route fits.
  Date/Author: 2026-09-13 (human partner)

## Surprises & Discoveries

- Observation: Decomposing had already externalized the one-unit execution record for children (the ledger file), so the shared-composite case needed no new mechanism.
  Evidence: `skills/decomposing/SKILL.md` step 7, "a brief child opens `docs/doperpowers/ledgers/YYYY-MM-DD-<child-id>.md` … Progress as deliverables land, in-flight Decisions … Surprises".

- Observation: The boundary the routing criteria actually draw is between direct and the spec routes, not between the two spec routes. A one-script change with tests, grill closed, routed direct ("a spec would outweigh the change") — correctly, on reflection; the one-unit route begins where a spec pays for itself (multi-file, a design worth recording, must land as one piece), and a request of that shape routed to it cleanly, naming the review-during-execution ordering unprompted.
  Evidence: three fresh subagents reading the new `skills/brainstorming/SKILL.md`; the first one-unit scenario (RECOVER stall clock + test) answered "Direct … a spec would outweigh the change"; the resized scenario (a `--json` mode across four sminos commands with one serializer and a schema doc) answered "Route 1 … a spec carrying its own execution, run sequentially here".

- Observation: `git mv` of a directory's last files leaves the empty directory tree behind, so `ls -d skills/*/` still counted 18 until an explicit `rmdir`.
  Evidence: `ls skills/execplan` succeeded after both moves; `rmdir skills/execplan/references skills/execplan` brought the count to 17.

- Observation: Recent usage had already tilted to the one-unit shape: August 2026 produced 9 specs, 8 plan files, 4 ExecPlans; September to date 3 specs, 0 plan files, 3 ExecPlans.
  Evidence: `ls docs/doperpowers/{specs,plans,execplans}` grouped by month.

## Outcomes & Retrospective

Achieved against the purpose: the repo now describes one method. Brainstorming routes by its unchanged criteria into three shapes of one artifact; the living spec carries its own execution on the well-scoped route and points at an execution plan on the other; the Architect protocol, plan-executor, writing-plans, SDE, decomposing, organizing-sprints, the implement protocol, ticket-gate, execution-loop, the triage protocol, CLAUDE.md, README, and the plugin manifests all speak the new vocabulary; execplan is archived and PLANS.md sits beside living-spec byte-identical. Verification depth is a separate, recorded call. Every acceptance item holds on the final tree (suites, lint, sweep, routing check, both reviews).

What remains: the fourteen historical ExecPlans stay under `docs/doperpowers/execplans/`; arkho's board-service still lacks the `in-design → in-progress` edge (PR #136's follow-up, untouched here); the installed plugin must reach 7.84.0 before a session sees the new routing; the Reviewer fold (phase 2 of the Architect fold) is still open.

Lessons. (1) The spec review earned its default-on status on its first outing: it caught a contradiction between brainstorming and living-spec on the no-next-steps rule, a claim about SDE's review rung with no carrier, an empty directory `git mv` leaves behind, and four consumers the plan missed. (2) The branch review caught the two defects that mattered most and that no test could: downstream text re-deriving unit count where the route should have been the key, and a promise ("re-engages you at every task boundary") that the interactive plan-executor hand-off cannot keep. Prose-as-behavior repos need a reviewer reading for contradictions between files, not only a diff reader. (3) A routing check needs scenarios placed on the boundary being tested; the first one-unit scenario sat on the direct boundary instead and taught something else. (4) Executing this change as the first spec in its own shape worked: Progress, Plan of Work, and Concrete Steps were enough to resume from after each review round without re-reading the transcript.

## Revision Notes

- 2026-09-12: created from the brainstorming session that folded the two tracks into one spec sized by the gate.
- 2026-09-12: revised after the independent spec review — the one-unit execution contract now carries the no-next-steps rule and living-spec's matching row; SDE's final-review rung reads the spec's verification entry; the composite-spec template, decomposing line 16, execution-loop, and the triage protocol join the consumer list; the empty `skills/execplan` tree is removed; README's replacement content, the routing check's expected answers, Milestones-in-Plan-of-Work, the context-economics cost, children's verification, and two decisions (inline one-unit execution; review ordering by executor) are now stated. Brainstorming's third routing criterion lost the words "or ExecPlan" — a rename, not a change of criterion.
- 2026-09-12: revised after the high-rung branch review — the route step 4 names now keys the artifact and hand-off everywhere (brainstorming's path, spec step, and step 9; living-spec's binding condition; writing-plans' description; the Architect's "Route the plan" bullet), instead of a unit count re-derived downstream; the false promise that writing-plans' loop re-engages the author at task boundaries is replaced with what the plan shape provides; the codex plugin manifest, install doc, and other live surfaces that still said "two-track" are reworded.
- 2026-09-12 (follow-up, v7.85.0): PLANS.md moved on from `skills/brainstorming/references/` to `archive/execplan/references/` — same checksum — after living-spec.md became self-contained by quoting its binding sections verbatim; the decision and its reasons are in `2026-07-03-living-specs-design.md`'s Decision Log, which owns the vendoring question.
- 2026-09-13 (Milestone 6, v7.86.0): board seams from a peer session's review of #138 — review ownership on the board keyed to the brief, plan-executor's sequential exit and retrospective, the pre-spec build edge for small tickets, the human's design approval on the plan route, residue as direct tickets. Acceptance 13–17 and four Decision Log entries added; the "one session owns the ticket" claim now holds for the direct shape too.
