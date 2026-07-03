# ExecPlan Track — Design

**Goal:** A second, autonomous development track alongside the controlled pipeline: front-load all human judgment into one relentless grilling session, then author a single self-contained ExecPlan (per the vendored PLANS.md, followed to the letter) and execute it without mid-flight human gates. For well-scoped, delegable work whose ambiguity a grill can exhaust up front — and a natural fit for daemon workers, whose only inheritable memory is one self-contained document.

## The track

```
grill (Matt Pocock's grilling, vendored; domain-modeling's interview moves absorbed)
  → one ExecPlan (skills/execspec/references/PLANS.md followed TO THE LETTER)
  → autonomous execution in a worktree (living updates, milestones, frequent commits)
  → exit gate: final whole-branch review → merge
```

One new skill, `skills/execplan/SKILL.md`, carries the whole track. No hooks into existing skills — the track is an alternative *entry*, not a modification of the default pipeline.

- **Grill step**: MP's grilling text vendored verbatim (10 lines, attributed), plus three interview moves kept from domain-modeling (sharpen fuzzy terms, stress-test with concrete scenarios, cross-reference claims with code). All output lands in the ExecPlan: definitions inline, decisions in its Decision Log. No CONTEXT.md, no ADRs.
- **Authoring step**: the SAME vendored PLANS.md that execspec adapts is here consumed unmodified — including the clauses the execspec adapter supersedes for the controlled track (Progress, milestones, novice-grade self-containment, autonomous ambiguity resolution). One vendor point, two consumption modes. ExecPlans live at `docs/superpowers/execplans/YYYY-MM-DD-<topic>.md`.
- **Execution step**: PLANS.md's implementing contract as written — no next-step prompts, living sections current at every stopping point, frequent commits — in an isolated worktree. Daemon-compatible by construction (the ExecPlan is exactly what a spawn prompt can carry and survives context death); v1 notes the fit, mandates nothing.
- **Exit gate**: exactly one — the final whole-branch review before merge; finishing's retrospective step writes into the ExecPlan's own `Outcomes & Retrospective` section (the ExecPlan is this track's spec-equivalent).

**Routing.** Controlled track (brainstorming → execspec spec → writing-plans → SDD): taste-heavy, novel, high-stakes work where design judgment keeps arising mid-flight. Autonomous track (this): the grill can exhaust the ambiguity space up front. Test during the grill: repeatedly hitting "can't know until we try" on *taste* questions (not feasibility — those become prototyping milestones) means route to the controlled track.

## What does NOT change

The execspec pipeline and its four hooks; the vendored PLANS.md (still one copy, still never edited); brainstorming (no cross-pointer — each track triggers on its own description).

## Verification

- `ls skills/execplan/` → `SKILL.md`
- `grep -c "execspec/references/PLANS.md" skills/execplan/SKILL.md` → at least 1 (shared vendor point, no second copy)
- `grep -c "one at a time" skills/execplan/SKILL.md` → 1 (vendored grill text present verbatim)
- Behavioral, on first real use: a session pointed at a well-scoped task produces one file under `docs/superpowers/execplans/` containing PLANS.md's living sections (`Progress`, `Surprises & Discoveries`, `Decision Log`, `Outcomes & Retrospective`) and executes it to a reviewed merge without asking "should I proceed?" mid-flight.

## Decision Log

- Decision: ExecPlan-only — no CONTEXT.md, no ADRs (rejecting the artifact half of MP's grill-with-docs; keeping its interview moves).
  Rationale: The track's identity is one self-contained document; a repo-persistent glossary is a second source of truth that drifts. Routing already filters: work that churns repo-lifetime domain decisions belongs in the controlled track. MP himself ships the no-docs variant (grill-me) and a lazy-creation principle — promote a term/decision to CONTEXT.md/ADR when it recurs across features, not on first use. Accepted cost: cross-feature term divergence; mitigated by PLANS.md's checked-in-prior-ExecPlan reference clause and grilling's explore-the-codebase-instead rule.
  Date/Author: 2026-07-03 (human partner proposed; assessed and adopted)

- Decision: Exit gate = one final whole-branch review before merge (rejecting pure end-to-end autonomy).
  Rationale: Cheapest piece of the validity architecture, placed where it cannot interrupt the autonomous flow. Human partner accepted the recommended default.
  Date/Author: 2026-07-03

- Decision: Vendor MP's grilling text verbatim into the skill (rejecting a runtime reference to the user-scope /grilling skill).
  Rationale: The plugin must work where MP's user-scope skills aren't installed; the text is 10 lines; the high-fidelity-vendor principle from the execspec work applies (details die in paraphrase). Attributed.
  Date/Author: 2026-07-03

- Decision: Share `skills/execspec/references/PLANS.md` as the single vendored source; execplan consumes it unmodified while execspec reads it through an adapter.
  Rationale: One vendor point cannot fork; the difference between tracks is consumption mode, not source text. The clauses execspec "rejected" were track-mismatches, not defects — this track is where they run as written.
  Date/Author: 2026-07-03

- Decision: This feature itself ships with a short spec and no implementation plan.
  Rationale: Single-file task — a plan would exceed the work (writing-plans is for multi-step tasks). The spec exists because the conversation produced real rejected alternatives that must survive (the fold-in challenge earlier today demonstrated the cost of undocumented rationale); it is deliberately short.
  Date/Author: 2026-07-03 (human partner questioned the ceremony; right-sized together)

## Surprises & Discoveries

- Observation: MP's grilling skill is 10 lines and grill-with-docs is one sentence — extreme empirical support for the "smart models need prose, not guardrails" premise driving this fork's methodology work.
  Evidence: `~/.claude/skills/grilling/SKILL.md` (10 lines), `grill-with-docs/SKILL.md` ("Run a /grilling session, using the /domain-modeling skill.").

- Observation: ExecPlan's most dangerous clause ("do not prompt the user; resolve ambiguities autonomously") becomes safe when the human gate is front-loaded rather than removed — the grill exhausts the ambiguity space while the human is present.
  Evidence: The validity gaps identified in the original superpowers-vs-ExecPlan analysis (no elicitation protocol, no term-definition method, undifferentiated decision lifetimes) map one-to-one onto grilling, domain-modeling's glossary moves, and the ADR three-condition test.

## Outcomes & Retrospective

**2026-07-03, at finish.** Shipped as designed, same conversation: `skills/execplan/SKILL.md` (grill vendored verbatim with attribution, three domain-modeling moves absorbed, authoring bound to the shared vendored PLANS.md to the letter, worktree execution, single exit gate). All structural verification passed on the first run (`ls`, both greps = 1). Right-sizing held: no plan was written and none was missed — the skill file was a single transcription-grade artifact.

The methodology portfolio is now two-track: controlled (execspec pipeline, gates throughout) and autonomous (this, gate front-loaded into the grill). Remains: the behavioral acceptance — first real use driving a task from grill to reviewed merge without mid-flight prompts; and the noted-but-unmandated daemon integration, to be wired only if real usage asks for it. Lesson: the fastest design sessions are the ones where every rejected alternative gets written down at rejection time — this spec's Decision Log was pure transcription because the conversation had already done the work.

## Revision Notes

- 2026-07-03: Initial version — terminal artifact of the grill-shaped design conversation (ExecPlan-only resolution, exit-gate default, right-sizing decision).
- 2026-07-03: Outcomes & Retrospective written at finish; structural verification results recorded.
