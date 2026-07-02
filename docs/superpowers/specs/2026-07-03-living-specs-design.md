# Living Specs — Design

**Goal:** Import the living-document doctrine of Codex ExecPlans (PLANS.md) into the superpowers **spec layer**, so a spec stays truthful for the whole life of its feature: decisions carry their rationale and their rejected alternatives, execution-time discoveries flow back into the document, and every feature closes with a retrospective — while the plan layer and the execution machinery stay exactly as they are.

**This spec is itself the first living spec.** Its Decision Log, Surprises & Discoveries, and Outcomes & Retrospective sections below are live and must be maintained per the doctrine it defines.

## Problem

The superpowers pipeline has no structural home for three lifecycle functions, and it shows:

1. **Spec drift.** A spec is culturally frozen after approval. Concretely: the issue-tracker spec (§4) lists `board-register.sh <title> <category> <md>` where `<md>` is actually an *output*; the discrepancy was discovered during plan-writing the same day, recorded in the plan — and never flowed back. The spec has been wrong since day one.
2. **Lost rationale.** Brainstorming *generates* 2-3 competing approaches with trade-offs, but only the winner reaches the spec. The comparison evidence evaporates with the conversation, so rejected ideas get re-proposed.
3. **No retrospective.** `finishing-a-development-branch` ends at merge; nothing compares the outcome to the original purpose.

Upstream already practices the fix without a written norm: the strict-cost-SDD spec received 6 commits in 2 days recording experiment verdicts ("L2 final — died at gates"); the worktree-rototill spec was updated by a post-release bugfix commit. This design codifies that proven culture — the norms come verbatim from PLANS.md, the strongest existing articulation of them.

## Design Overview

One new skill plus four one-point hooks in existing skills:

- **`skills/living-specs/`** — the doctrine's home: `SKILL.md` (the adapter: dispositions, living-section formats, calibrations) and `references/PLANS.md` (the ExecPlan source document, vendored **char-for-char**, never edited — committed alongside this spec because the source text existed only in a conversation).
- **Hooks**: `brainstorming` (write specs in this shape; seed the Decision Log), `writing-plans` (planning is the first hostile read — fix spec drift when found), `subagent-driven-development` (route design-relevant discoveries into the spec during execution), `finishing-a-development-branch` (append the retrospective before merge).

The regime is uniform: a worker daemon is the same Claude Code session running the same workflow, so there is no separate "worker path", and no writer rules — in practice one spec has one working agent maintaining it.

## The Vendored Source and the Adapter

`references/PLANS.md` is scripture; `SKILL.md` is the commentary that says which parts bind at the spec layer. The vendored file is never modified — a future PLANS.md revision diffs cleanly against it. When the adapter adopts a section, agents follow the **original text**, not a paraphrase; paraphrase is how tuned details die.

### Disposition map

| PLANS.md section | Disposition | Why |
|---|---|---|
| Purpose and intent come first (Requirements ¶2) | **Adopt verbatim** | Spec must open with user-visible why |
| Non-negotiables: living document, define every term, demonstrably working behavior | **Adopt** | Core of the import |
| Non-negotiable: self-contained "for a novice" | **Adopt, recalibrated** | Bar becomes "a fresh session with no conversation history"; novice-grade duplication of repo knowledge invites its own drift |
| Guidelines: define jargon on first use; observable-outcome acceptance; full repo-relative paths | **Adopt verbatim** | Fixes uneven Verification quality across existing specs |
| Living plans and design decisions (Decision Log, Surprises & Discoveries, Outcomes & Retrospective; revision notes) | **Adopt verbatim — the heart** | Target document is the spec, not the plan |
| Prototyping milestones and parallel implementations | **Adopt** | Spec may declare spike milestones with promote/discard criteria; writing-plans turns them into spike tasks |
| Skeleton: journal-section formats (`Decision:/Rationale:/Date`, `Observation:/Evidence:`) | **Adopt (excerpted)** | Exact entry formats for the living tail |
| How to use: "do not prompt the user", resolve ambiguities autonomously | **Reject** | Human gates (design approval, spec review) are the validity spine we keep |
| Formatting: single fenced block, prose-first, no tables | **Reject** | Transport convention for chat-emitted plans; specs are files, and mixed notation (tables for state machines, JSON for schemas) beats prose-only for precision |
| Progress section (mandatory checklists, timestamps) | **Reject** | Ledger + git + plan checkboxes are externally verifiable; a Progress section is self-report born of gitless assumptions |
| Milestones narrative / Concrete Steps / Interfaces and Dependencies | **Reject** | `writing-plans` does this with complete code and exact commands — strictly stronger |
| Idempotence and Recovery | **Reject** | Worktrees + git provide it structurally |

Rejections are recorded here so nobody re-proposes them without new evidence (the same function upstream's "tested-and-declined, with data" sections serve).

## What a Living Spec Looks Like

The **front of the spec stays untemplated** — across the 15 existing specs no heading structure repeats, and that variance is a feature: form fits problem. The doctrine constrains only:

1. **Opening**: purpose first — what someone can do after this change that they could not before (PLANS.md Requirements ¶2, verbatim standard).
2. **Verification/Acceptance section**: phrased as observable behavior with exact commands and expected output, not internal attributes (PLANS.md "Anchor the plan with observable outcomes", verbatim standard).
3. **The living tail** — four sections at the end of every spec:
   - `## Decision Log` — every design decision, in PLANS.md skeleton format: `Decision: / Rationale: / Date`. Seeded at brainstorm time with the chosen approach **and the rejected alternatives** with why each lost. Extended whenever course changes.
   - `## Surprises & Discoveries` — `Observation: / Evidence:` entries for anything that changed design understanding. Incidental implementation noise stays in commit messages.
   - `## Outcomes & Retrospective` — written at finish: outcome vs. original purpose, gaps, lessons. Until then a single line: "Pending — written at finish."
   - `## Revision Notes` — one dated line per spec revision saying what changed and why (PLANS.md's bottom-note rule).
4. **Spike declarations** (only when unknowns are large): a prototyping milestone with run/observe instructions and promote-or-discard criteria.

## Workflow Hooks

Each hook is one small insertion; exact anchor text lives in the implementation plan.

1. **`brainstorming/SKILL.md`** — checklist item 6 and the "After the Design > Documentation" section: write the design doc in living-specs shape (reference `superpowers:living-specs`); seed the Decision Log from the approaches step — the 2-3 alternatives with trade-offs are already generated, capturing them is free.
2. **`writing-plans/SKILL.md`** — Self-Review gains check 4, **Spec drift**: planning is the first hostile read of the spec; if a spec statement proved wrong while planning (an argument that is actually an output, an infeasible constraint), fix the spec now and add a Revision Note — never let the plan silently diverge.
3. **`subagent-driven-development/SKILL.md`** — Durable Progress: in the same bookkeeping message as the ledger append, route anything from the task's report that changes design understanding (assumption proved false, constraint discovered, mid-course decision) into the spec's Surprises & Discoveries or Decision Log.
4. **`finishing-a-development-branch/SKILL.md`** — after Step 1's tests pass, before presenting options: append the Outcomes & Retrospective entry to the spec and commit it, so the retrospective rides the branch into the merge.

## What Does NOT Change

- **The plan layer.** Plans stay frozen, dense, complete-code contracts. Their density is load-bearing: transcription-grade tasks run on the cheapest models, and reviewers get constraints verbatim. No journal prose enters plans.
- **Progress tracking.** Ledger + git + plan checkboxes, unchanged.
- **Human gates.** Design approval, spec review, execution choice — all kept; ExecPlan's autonomy directives are explicitly not imported.
- **No permissions or writer rules.** Whoever drives the session maintains the spec.
- **Existing specs.** Not retrofitted; the regime applies to new specs (optionally backfill a living tail when an old spec is next touched).

## Verification

Structural (run from repo root; all must hold after implementation):

- `ls skills/living-specs/` → `SKILL.md  references/`
- `git log --oneline -- skills/living-specs/references/PLANS.md` after implementation → exactly one commit, the spec commit (vendored file never touched again; a plain `git diff HEAD` would pass even if a later task modified and committed it)
- `grep -l "living-specs" skills/brainstorming/SKILL.md skills/writing-plans/SKILL.md skills/subagent-driven-development/SKILL.md skills/finishing-a-development-branch/SKILL.md` → prints all four paths

Behavioral (observed on the next real feature, this one included):

- A brainstorm's design doc ends with the four living-tail sections, and its Decision Log names at least one rejected alternative with a reason.
- When plan-writing finds a spec error, the spec gets fixed in the same session with a Revision Note (the issue-tracker `<md>` case would have been caught).
- Finishing a branch appends a retrospective entry to the spec before the merge options are presented — this very spec's "Pending" line being replaced is the first acceptance instance.

## Out of Scope

- Eval-harness runs (personal fork; sanity-tested on real use instead).
- Upstream contribution.
- Any change to plan format, the ledger, review templates, or the issue-tracker/board.
- Retrofitting the 15 existing specs.

## Decision Log

- Decision: Host layer for the ExecPlan import is the **spec**, not the plan.
  Rationale: Audience (controllers, humans, future sessions — not cheap transcription implementers), lifetime (specs survive merge as design history; plans are consumables), and culture (upstream already maintains specs as living docs with no written norm).
  Date: 2026-07-03

- Decision: Base document is the superpowers spec; ExecPlan enters as **norms**, never as envelope.
  Rationale: ExecPlan's autonomy, single-document, and formatting rules conflict head-on with the validity architecture being kept (human gates, layered docs, context economics).
  Date: 2026-07-03

- Decision: Vendor PLANS.md **char-for-char** plus a separate adapter; adopted guidance is consumed from the original text — short verbatim excerpts in the adapter are allowed, rewording is not.
  Rationale: Human partner's requirement — details must survive at high confidence. Matches this repo's own philosophy that behavior-shaping prose is tuned content. Keeps future upstream-PLANS.md diffs clean.
  Date: 2026-07-03 (human partner)

- Decision: Do **not** import the Progress section.
  Rationale: Ledger + git + plan checkboxes are externally verifiable evidence; ExecPlan's Progress is self-report designed for a world without them.
  Date: 2026-07-03

- Decision: Do **not** import Idempotence and Recovery.
  Rationale: Worktree isolation + git already provide recovery structurally.
  Date: 2026-07-03

- Decision: No main-session/daemon split and no single-writer rule.
  Rationale: Human partner's call — a worker daemon *is* a normal Claude Code session running the same dev workflow; one spec has ~one working agent, so writer rules are dead weight, and in-repo measurement shows nuance clauses degrade winning recipes.
  Date: 2026-07-03 (human partner)

- Decision: Self-containment recalibrated from "complete novice" to "a fresh session with no conversation history".
  Rationale: Novice-grade self-containment duplicates repo knowledge into the spec, and the duplicate drifts; the smart-model premise makes "define terms, reference repo common knowledge" the right calibration.
  Date: 2026-07-03

- Decision: Commit the vendored PLANS.md together with this spec, before any plan exists.
  Rationale: The source text existed only in the conversation; it had to be persisted before compaction could lose it.
  Date: 2026-07-03

- Decision: The front of a spec remains untemplated; only the opening standard, acceptance standard, and living tail are constrained.
  Rationale: Measured genre variance across all 15 existing specs (no repeated heading structure) is a feature — form fits problem.
  Date: 2026-07-03

- Decision: `living-specs` stays a separate skill rather than folding the doctrine into brainstorming (challenged post-implementation; re-affirmed).
  Rationale: Folding is mechanically viable — the four hooks are deliberately self-contained one-liners. But brainstorming is only the *producer*; the spec has four consumer moments across different sessions, and three of them (plan-writing, execution bookkeeping, finish) never load brainstorming — pointing them at it would inject its HARD-GATE "do not implement" language into implementation contexts. A separate skill also gives ad-hoc spec revision an auto-trigger, keeps ~90 doctrine lines out of every brainstorm's always-loaded context (a references-file split would recreate the same indirection minus the trigger), and names the reference by what it governs: a document class, not a process. General rule applied: one producer + many cross-session consumers → neutral module (same reason code-reviewer.md lives in requesting-code-review, not copied into SDD).
  Date/Author: 2026-07-03 (human partner challenged; discussed and re-affirmed)

## Surprises & Discoveries

- Observation: Upstream already maintains method specs as living documents, with no written norm requiring it.
  Evidence: `git log` — strict-cost-SDD spec: 6 commits in 2 days ("L2 final — died at gates; explicit escalation holds at sonnet…"); SDD-review-dispatch spec: 6 commits ("Spec: record iterations 4-5"); worktree-rototill spec updated by post-release fix #1476.

- Observation: Without the norm, spec drift happens within a single day.
  Evidence: issue-tracker spec §4 still lists `<md>` as an argument to `board-register.sh`; the plan (Task 1, Interfaces note) identified it as an output on the same date and the spec was never corrected.

- Observation: Current-generation models need fewer composition guardrails — measured in this repo, supporting the "prose over guardrails" premise of this design.
  Evidence: positive-instruction-redesign spec: 40/40 generated plans clean of placeholders under deliberate pressure; disposition "leave the No Placeholders section exactly as it is… do NOT open the follow-up PR."

## Outcomes & Retrospective

**2026-07-03, at finish.** Everything in the design shipped, same-day: the vendored `references/PLANS.md` (char-for-char; its git history shows exactly one commit), the `living-specs` adapter skill with the disposition map, and all four hooks (`brainstorming`, `writing-plans`, `subagent-driven-development`, `finishing-a-development-branch`) — every structural verification check passed on the first sweep.

The doctrine proved itself before its own implementation finished: plan-writing's "first hostile read" caught an ineffective verification check in this very spec (`git diff HEAD` passes even after a modifying commit — see Revision Notes), which is precisely the same-day-drift failure class (the issue-tracker `<md>` case) that motivated the feature. This retrospective entry, replacing the "Pending" line via the new finishing hook, is the first acceptance instance the Verification section called for.

Remains: behavioral acceptance on the next real brainstorm (does a fresh session produce a spec in living shape unprompted?); the 15 existing specs stay un-retrofitted by design. Lesson: a plan whose tasks are pure transcription made inline execution the right call — the SDD machinery would have been overhead, exactly as the model-selection doctrine predicts.

## Revision Notes

- 2026-07-03: Initial version — terminal artifact of the brainstorm (conversation: superpowers-vs-ExecPlan comparative analysis → synthesis design). Vendored `skills/living-specs/references/PLANS.md` committed alongside.
- 2026-07-03: Verification hardened during plan-writing (the first hostile read, as the doctrine predicts): the vendored-file check `git diff HEAD` was ineffective — it passes even after a modifying commit — replaced with a `git log` single-commit check.
- 2026-07-03: Outcomes & Retrospective written at finish via the newly installed finishing hook — the feature closing its own loop.
- 2026-07-03: Decision Log extended — separate-skill-vs-fold-into-brainstorming challenged by the human partner after implementation; rationale for the standing choice was undocumented (exactly the gap this regime exists to close), now recorded.
