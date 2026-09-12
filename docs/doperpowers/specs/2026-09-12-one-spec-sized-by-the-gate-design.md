# One spec, sized by the gate

This spec is a living document: `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` are kept current as the work proceeds, per `skills/brainstorming/references/living-spec.md`. The work is one unit, so this spec carries its own execution (`Plan of Work`, `Concrete Steps`) instead of pointing at an execution plan.

## Purpose

doperpowers has described itself as two development tracks, "controlled" and "autonomous". Since the Architect fold (v7.82.0) both run the same way: a grill closes the design questions while the human partner is present, execution proceeds without stopping, and a fork the plan does not cover returns to the plan's author. What still differed was the artifact (a spec plus an execution plan against a single ExecPlan) and the names, which promised a difference in human control that no longer existed.

After this change there is one primary artifact, the living spec, and one gate, decomposing's: can one agent reliably own the work as one unit? Work that is one unit gets a spec that carries its own execution and is run sequentially. Work that is several units gets the spec plus an execution plan and a fresh subagent per task. How much independent review the work gets is a separate call made from its stakes, not its size. The routing criteria brainstorming has used at step 4 stay verbatim; only their destinations are renamed.

Seeing it work: a session reading `skills/brainstorming/SKILL.md`, `skills/issue-tracker/references/architect-worker-protocol.md`, or `README.md` finds one method whose shape follows the size of the work and no track names; `ls skills/execplan` fails and `archive/execplan/SKILL.md` exists; `shasum -a 256 skills/brainstorming/references/PLANS.md` prints the checksum recorded in Concrete Steps; `tests/issue-tracker/test-protocol-content.sh` passes with its new assertions.

## Progress

- [ ] Milestone 1 — the artifact: living-spec.md binds the inline execution sections and conditions the superseded rows; PLANS.md moved byte-identical; execplan archived.
- [ ] Milestone 2 — brainstorming's path: renamed destinations at step 4 with criteria kept verbatim, the design presented on every route, the verification call, step 9 by route.
- [ ] Milestone 3 — consumers: writing-plans, plan-executor, Architect protocol, implement protocol, ticket-gate, issue-tracker SKILL, decomposing, organizing-sprints, CLAUDE.md.
- [ ] Milestone 4 — README pitch, skill list, flow section.
- [ ] Milestone 5 — validation: protocol-content assertions, stale-term sweep, routing check with fresh subagents, suites, lint, version bump.
- [ ] Exit — branch review at the high rung, retrospective, PR.

## Acceptance

1. `skills/brainstorming/SKILL.md` step 4 keeps its three criteria sentences ("Well-scoped and delegable…", "Large, novel, taste-heavy, or high-stakes…", "Narrow and small…") unchanged in wording, and their destinations read: a spec that carries its own execution, run sequentially; a spec plus an execution plan through doperpowers:writing-plans; direct. The words "controlled" and "autonomous" do not appear in the file.
2. The path paragraph states that every route runs steps 1–5 (the design is presented on every route) and that step 9 hands off by route; the single-unit route's execution contract is stated there: isolated workspace, Progress and living tail kept current, frequent commits, branch review at the rung the verification call named, retrospective, integration.
3. Step 4 also names the verification call with its defaults: one independent spec review by default; a critique debate when the design is novel or the cost of being wrong is high; the adversarial plan review whenever an execution plan exists; the branch review rung; recorded as a Decision Log entry in the spec.
4. `skills/brainstorming/references/living-spec.md` says that a spec for one unit of work binds PLANS.md's `Progress` (placed after the purpose), `Plan of Work`, and `Concrete Steps` as written, and `Interfaces and Dependencies` when the work defines new interfaces; its superseded table conditions the Progress and Milestones/Concrete Steps rows on an execution plan existing; its PLANS.md link resolves to `skills/brainstorming/references/PLANS.md`.
5. `skills/brainstorming/references/PLANS.md` exists with the checksum recorded in Concrete Steps; `skills/execplan/` does not exist; `archive/execplan/SKILL.md` exists.
6. `agents/plan-executor.md` `## Mode` describes the non-SDE file as a spec that carries its own execution, worked in order, and no longer says "ExecPlan".
7. `skills/issue-tracker/references/architect-worker-protocol.md` `## Design` has a size bullet (one unit: the spec carries its execution; several: spec plus execution plan) and a verification bullet with the defaults from item 3, replacing "Track judgment (council scaling)"; `## Build` names the artifact the brief carries (the spec, or the execution plan and its spec) and says a spec carrying its own execution runs sequentially. `tests/issue-tracker/test-protocol-content.sh` asserts the size and verification bullets are present and "Track judgment" is absent, and passes.
8. `skills/writing-plans/SKILL.md`'s description says it applies when the spec's work is several units; `skills/issue-tracker/references/implement-worker-protocol.md` resumes from the ledger or the spec's `Progress`; `skills/issue-tracker/references/ticket-gate.md` and `skills/issue-tracker/SKILL.md` no longer name an ExecPlan or a controlled-track build; `skills/decomposing/SKILL.md` calls the child hint the grain hint, says a leaf dispatches by its size, and its Common Mistakes has no ExecPlan row; `skills/organizing-sprints/` says an epic derives its own spec at dispatch time; `CLAUDE.md`'s repo map says 17 skills and describes plan-executor without "ExecPlan".
9. `README.md` opens with the sizing pitch in Decision Log entry 9, the diagram no longer labels CONTROLLED and AUTONOMOUS tracks, "Two tracks, one discipline" is replaced, the skill list has no `execplan` line and says seventeen skills, and "How the controlled track flows" is "How a change flows" with sizing as its first step.
10. `grep -rn -i -E 'controlled track|autonomous track|execplan' skills agents README.md CLAUDE.md tests/issue-tracker` returns only: `skills/brainstorming/references/PLANS.md` (the vendored source), `skills/sminos/SKILL.md:22` (cites existing dated files), `skills/issue-tracker/scripts/board-lint.sh` (a comment citing the design that produced it), and `tests/issue-tracker/test-protocol-content.sh:76` (asserts a retired mode is absent).
11. Routing check: three fresh subagents, each given the new `skills/brainstorming/SKILL.md` and one request (a one-unit change, a several-unit feature, a one-line fix), each name the expected route and artifact.
12. `tests/issue-tracker/test-protocol-content.sh`, `tests/issue-tracker/test-board-scripts.sh`, `tests/issue-tracker/test-execute-dispatch.sh`, `tests/issue-tracker/test-board-sweep.sh`, and `scripts/lint-shell.sh` pass; the version is bumped with `scripts/bump-version.sh` in the same PR.

## Design

**The principle.** One gate, decomposing's, applied at every altitude: a goal that fails it divides into children; a leaf whose work is several units gets an execution plan and per-task workers; one unit is one agent's sequential work. Verification depth is a separate call made from stakes. Execution at every altitude runs without stopping until it meets a decision the plan does not cover, which returns to that plan's author.

**The router stays.** Brainstorming's step 4 criteria read two signals off the grill: the size of the work and how often the author's judgment will need to re-enter mid-flight. The per-task loop re-engages the author at every task boundary (brief, report, review adjudication); the sequential shape returns only on BLOCKED or completion. Taste-heavy work therefore benefits from the plan shape even when it is one unit, and a large routine change can run as one sequential executor. The criteria have served well and are kept verbatim; only their destinations change name.

**The artifact.** The spec is always the primary document at `docs/doperpowers/specs/`. For one unit it also carries its execution: `Progress` after the purpose as its ledger, `Plan of Work`, `Concrete Steps`, and `Interfaces and Dependencies` when new interfaces are defined, all bound from PLANS.md as written at the living-spec bar (a fresh session with no history can continue). For several units doperpowers:writing-plans produces the execution plan, the SDE ledger tracks progress, and the spec's execution section is one line naming the plan file. A child of a composite spec is unchanged: its section is its spec and its ledger file or plan is its record, which is this same rule with the record externalized because the composite is shared by parallel siblings. New single-unit specs go under `specs/`; `docs/doperpowers/execplans/` is history.

**Brainstorming's path.** Steps 1–3 unchanged. Step 4: route by the existing criteria and name the verification call. Step 5: present the design on every route. Steps 6–8: the spec (with its execution inline for one unit), self-review, the independent spec review. Step 9 by route: several units → writing-plans; one unit → execute here under the contract in Acceptance 2; a coupled goal that fails the gate → decomposing. Direct implements after step 5 as today.

**The verification call.** Defaults: one independent spec review; a critique debate when novel or high-cost; the adversarial plan review whenever a plan file exists; the branch review rung, which the SDE final review and the single-unit exit both read. Recorded as a Decision Log entry so the executor, the reviewer, and a recovering session read the same council.

**The board.** The Architect protocol's "Track judgment (council scaling)" splits into size and verification bullets. The build brief names the artifact the executor opens; the pin points at that file, so board-transition, the pin format, and qa-loops do not change. Plan-executor keeps its mode key: a header naming subagent-driven-execution makes it the controller, any other file it works in order. The Executor's recovery lane resumes from the SDE ledger or the spec's Progress.

**Retirements and renames.** execplan → `archive/execplan/`; PLANS.md → `skills/brainstorming/references/PLANS.md` byte-identical; the vocabulary changes listed in Acceptance 8; the README per Acceptance 9. Historical citations (board-lint's comment, sminos's line about dated files) stay.

## Plan of Work

Milestone 1, the artifact. Move `skills/execplan/references/PLANS.md` to `skills/brainstorming/references/PLANS.md` with `git mv` and confirm the checksum. Move `skills/execplan/SKILL.md` to `archive/execplan/SKILL.md` with `git mv` and add one line at its top saying it is retired and where its content went. In `living-spec.md`: fix the source link; add a paragraph after "The bar" stating what a one-unit spec additionally binds; rewrite the Progress row and the Milestones/Concrete Steps row of the superseded table as conditional on an execution plan existing; add one sentence to the living tail saying the verification call is a Decision Log entry.

Milestone 2, brainstorming. In `SKILL.md`: the path list (step 4 title, step 9 title), the paragraph after it (every route runs 1–5; direct implements after 5; one unit and several both write the spec; step 9 by route), the intro sentence "without another design or track approval", the child paragraph's "track hint" → "grain hint", the `## Choosing the track` section retitled and its destinations renamed with the criteria sentences untouched, the verification-call paragraph added there, the closing handoff paragraph in `## The spec` rewritten by route.

Milestone 3, consumers. `skills/writing-plans/SKILL.md` description. `agents/plan-executor.md` Mode paragraph. Architect protocol: Design bullets, Build brief and the sequential/controller sentence, the "ExecPlan's Progress" mention. Implement protocol lines 45 and 150. Ticket-gate line 38. Issue-tracker SKILL line 398. Decomposing: lines 52, 57, 60–61, 105, 220, 252, 307, 321 (merge the ExecPlan row into the leaf-child row). Organizing-sprints SKILL lines 16, 63, 185 and template lines 18–20. CLAUDE.md repo map: agents row, skills count.

Milestone 4, README. Diagram, pitch paragraph, the "Two tracks, one discipline" section, the skills list line and count, the flow section.

Milestone 5, validation. Extend `tests/issue-tracker/test-protocol-content.sh` per Acceptance 7. Run the sweep in Acceptance 10. Dispatch the three routing-check subagents. Run the suites and lint. Bump the version (minor).

## Concrete Steps

Run from the worktree root.

    shasum -a 256 skills/execplan/references/PLANS.md      # record before the move
    git mv skills/execplan/references/PLANS.md skills/brainstorming/references/PLANS.md
    shasum -a 256 skills/brainstorming/references/PLANS.md  # must match
    mkdir -p archive/execplan && git mv skills/execplan/SKILL.md archive/execplan/SKILL.md

PLANS.md checksum before the move: (recorded at Milestone 1).

    grep -rn -i -E 'controlled track|autonomous track|execplan' skills agents README.md CLAUDE.md tests/issue-tracker
    # expect only the four exemptions in Acceptance 10

    tests/issue-tracker/test-protocol-content.sh
    tests/issue-tracker/test-board-scripts.sh
    tests/issue-tracker/test-execute-dispatch.sh
    tests/issue-tracker/test-board-sweep.sh
    scripts/lint-shell.sh
    scripts/bump-version.sh minor

## Decision Log

- Decision: One primary artifact, the living spec, for every size of work; the ExecPlan file shape retires.
  Rationale: After the Architect fold the two tracks differed only in artifact and name. The spec is the document reviewers, the board, decomposing, and finishing all address; keeping a second file shape for one-unit work duplicated the living tail and split the vocabulary. This reverses the 2026-07-03 living-specs decision "ExecPlan enters as norms, never as envelope": that decision rested on human gates and layered docs that no longer distinguish the shapes.
  Rejected: keep two shapes and only rename — leaves two authoring guides and two directories for one kind of document.
  Date/Author: 2026-09-12 (human partner)

- Decision: The living-spec bar (a fresh session with no history can continue) governs one-unit specs too; PLANS.md's novice bar and prose-only formatting do not return.
  Rationale: One document, one bar. Novice-grade self-containment duplicates repo knowledge into the spec and drifts. PLANS.md stays vendored as the source of the norms that bind.
  Rejected: PLANS.md to the letter for the one-unit shape — two bars for one document class.
  Date/Author: 2026-09-12 (human partner)

- Decision: A one-unit spec binds PLANS.md's Progress, Plan of Work, Concrete Steps, and (when interfaces are defined) Interfaces and Dependencies, as written.
  Rationale: This reverses the 2026-07-03 decision "Do not import the Progress section", which reasoned from the SDE ledger's existence; a one-unit spec has no ledger, so Progress is its ledger. Binding by section name keeps living-spec's rule that details die in paraphrase.
  Rejected: a single `## Execution` section of our own shape — paraphrases the norms living-spec vendors by name.
  Date/Author: 2026-09-12

- Decision: Brainstorming's step 4 routing criteria stay verbatim; only the destinations are renamed.
  Rationale: The criteria read both size and the expected density of mid-flight author judgment, and the per-task loop is the shape that re-engages the author most often. They have routed well in practice and did not judge too early.
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

- Decision: Verification for this work: no critique debate (the design was argued with the human partner directly over two rounds), one independent spec review in the background during execution, branch review at `doperpowers:reviewer-high`.
  Date/Author: 2026-09-12

## Surprises & Discoveries

- Observation: Decomposing had already externalized the one-unit execution record for children (the ledger file), so the shared-composite case needed no new mechanism.
  Evidence: `skills/decomposing/SKILL.md` step 7, "a brief child opens `docs/doperpowers/ledgers/YYYY-MM-DD-<child-id>.md` … Progress as deliverables land, in-flight Decisions … Surprises".

- Observation: Recent usage had already tilted to the one-unit shape: August 2026 produced 9 specs, 8 plan files, 4 ExecPlans; September to date 3 specs, 0 plan files, 3 ExecPlans.
  Evidence: `ls docs/doperpowers/{specs,plans,execplans}` grouped by month.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-09-12: created from the brainstorming session that folded the two tracks into one spec sized by the gate.
