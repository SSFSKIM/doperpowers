# goal-gated decomposition — the gate replaces the ladder (2026-07-21)

## Purpose

v7.23.0 gave the fork an above-Slice altitude (`roadmapping`) built around a
canonical ladder: Milestone → Epic → Slice → Task. Two days of contact with
the doctrine eroded the ladder's load-bearing claims from inside its own
spec: the dry-run corrected "epic-sized child ⇒ nested run" to "nesting is
for children that NEED decomposition, not children that are large"; the
retro's open watch items (vocabulary drift between organizing-sprints epics
and ladder Epics; the epic-child ticket species; ladder fit itself) are all
artifacts OF the ladder, not of the work. Meanwhile the decomposition
criterion the fork actually trusts already exists, stated four ways in four
homes: the board's ticket gate (WELL-DEFINED + WELL-SCOPED), brainstorming's
scope bullet, roadmapping's entry condition, and writing-plans' sub-slicing
signals.

This spec re-founds the altitude on the principle itself — the fork's own
constraint-minimization golden rule applied to decomposition. Every node of
work is a GOAL (purpose + observable acceptance). A goal divides into child
goals only when it fails the gate — too unclear or too big for one agent to
reliably own as one unit — and the division recurses at need, producing a
tree of asymmetric depth whose leaves dispatch to the existing tracks. The
ladder is demoted to project-local vocabulary. `roadmapping` is re-founded
as `decomposing-goals`; the validated organs (derivation contract, template,
pipeline, HARD-GATE) survive near-verbatim.

Secondary purpose, same doctrine one radius wider: doperpowers:brainstorming
gains (a) SITUATING AT FOUR RADII — the grill's "a question the codebase can
answer is answered by reading it" generalized to the world (research) and to
experiments (spikes), so explore/research/spike stop being separate
ceremonies; and (b) THE CHALLENGER DUTY — before converging an idea, the
agent judges whether the idea as conceived serves the project's standing
purpose as well as it could, speaking only when what it found would change
the decision.

## Design

### The seam: brainstorming defines, decomposing-goals divides

The boundary between the two skills stops being an altitude ("bigger than
one slice") and becomes a function: brainstorming DEFINES one goal at a time
— purpose, observable acceptance, the decisions that shape it — whatever its
size; decomposing-goals DIVIDES a defined-enough goal that fails the gate's
scope check; the tracks (spec→plans, execplan) EXECUTE gate-passing leaves.
Recursion is the alternation define ↔ divide: a child returns through
brainstorming (or execplan) with its parent section as pre-landed input,
grilling residue only — exactly the behavior P3 validated in v7.23.0.

### The gate, stated once

One criterion at every altitude, identical to the board's ticket gate
(doperpowers:issue-tracker `references/ticket-gate.md` is its board
rendering — that file keeps board procedure; doctrine lives in
decomposing-goals):

- **WELL-DEFINED** — every fork the work will hit has an owner or an
  answer. Fails ⇒ the missing thing is knowledge: grill it when a
  conversation can close it; make it a child whose deliverable is findings
  (spike/research) when it needs real work.
- **WELL-SCOPED** — one agent can reliably own it as one unit. "One agent"
  = one accountable context, which may marshal subagent workers (SDD task
  workers, ExecPlan milestones) without that becoming decomposition —
  execution mechanics live below the tree's resolution. Fails ⇒ divide
  into work-children.

A gate-passing goal is a LEAF whatever its size: reliably-ownable is a
moving envelope (model capability, context, harness support), not a size
class — the gate absorbs capability growth that a fixed ladder would bake
in. Split signals and keep-together signals are calibration content carried
by the skill (promoted from writing-plans' sub-slicing list, which remains
the below-slice application of the same list).

### The tree

- Decomposition is a TREE: one parent per child — the parent is the child's
  reason to exist and its flow-back address. A subgoal two parents need is
  hoisted to the common ancestor; the need becomes dependency edges.
- Dependencies are typed EDGES (`blocked-by`, `conditional-on`,
  `external:<condition>`), cross-branch allowed, acyclic — a DAG overlaid
  on the tree. The tree says what adds up to what; edges say what waits.
- No OR-branches: the tree records the chosen division; alternatives live
  in Decision Logs.
- Levels have no canonical names. Milestone/Epic/Phase/Sprint are project
  vocabulary, annotated on nodes, never load-bearing. Depth is an output of
  the gate and is asymmetric by nature.
- The ROOT is the project's standing purpose. Convention: CLAUDE.md states
  the top-level goal as short prose; projects that keep a standing root
  spec route to it from that line. New goals enter the tree by being
  situated against the root or an existing node (brainstorming's job).
- ZERO NEW SUBSTRATE: the tree is the citation chain (child spec cites
  parent, path + child id) + the board's typed edges + parent specs'
  tracking maps. No registry file exists or may be invented.

### The frontier (lazy division) and recomposition

Divide at need in TIME as well as size: one level per run, and a branch is
divided only as it nears execution — distant branches stay coarse (track
hint: "decomposing-goals run at dispatch"). The staleness evidence already
recorded for approach sketches applies one level up to child cuts
themselves; an undivided branch is cheap to re-cut when a landed sibling's
discoveries move it.

Closing a parent is RECOMPOSITION, not bookkeeping: the parent declares its
own acceptance at cut time (already in the template: "not the sum of child
acceptances"), and when all children have landed, closing the parent is a
verification event against that acceptance — then the retrospective writes.

### File-by-file

- `skills/roadmapping/` → `skills/decomposing-goals/` (git mv; history
  preserved). SKILL.md rewritten around Gate/Tree/Frontier/Recomposition;
  Pipeline, Derivation Contract, HARD-GATE, Common Mistakes preserved
  near-verbatim with ladder language removed. Template keeps its filename
  (`roadmap-spec-template.md` — "roadmap" stays the artifact's colloquial
  name); its altitude header slot becomes Parent citation + project-local
  Level name annotation; Outcomes gains the recomposition clause; track
  hint renames.
- `skills/brainstorming/SKILL.md`: scope bullet + terminal-state
  parenthetical rewritten to gate language and the new name; a fourth
  situating move appended after the three grill moves (four radii:
  codebase / external dependencies / world / project purpose); the
  challenger duty added as its own paragraph (always assess; speak only
  when it would change the decision; grounded, once, before convergence;
  offer, not veto). The vendored grill quote is untouched.
- `skills/writing-plans/SKILL.md`: Conditional Sub-Slicing keeps its
  validated body; only the closing above-Slice paragraph is rewritten to
  name decomposing-goals as the doctrine's home (this section = the gate's
  below-slice application).
- `skills/organizing-sprints/SKILL.md`: description's routing sentence
  renames.
- `skills/issue-tracker/references/ticket-gate.md`: one added line naming
  itself the board rendering of the universal gate.
- `skills/implementing-tickets/references/implement-decompose.md`: one
  parenthetical in step 6 tying worker decomposition to the same doctrine.
  (The `## Roadmap` JIT section name in ticket bodies is unchanged;
  `tests/implementing-tickets/test-protocol-content.sh` asserts it.)
- `docs/doperpowers/specs/2026-07-19-roadmapping-design.md`: supersession
  Revision Note appended; history not rewritten.

## Acceptance

Evidence per doperpowers:writing-skills, recorded in Outcomes when run:

- **RED (challenger baseline, before editing brainstorming):** fresh-context
  agents given the CURRENT brainstorming skill + a scenario whose repo
  states a top-level goal and whose human proposes a plausible but
  goal-dominated idea (loyalty points vs. an 18% no-show baseline and
  clients who never open the app). Failure to challenge before converging =
  the failing test that licenses the edit. If baseline agents already
  challenge reliably, the challenger edit is NOT authored (control shows no
  failure → nothing to fix).
- **GREEN (challenger):** same scenario with the NEW text — agents raise a
  grounded challenge before convergence (≥2/3 reps); a companion
  aligned-idea scenario draws NO manufactured challenge (≥2/3 reps) — the
  speak-condition binds both ways.
- **Regression P1/P2/P3 (v7.23.0's pressure suite, new frame):** an
  epic-scale prompt routes to decomposing-goals with confirmation and no
  child-detail grilling; a slice-scale prompt does not route; a parent
  child-section hands a fresh session pre-landed input and only residue is
  grilled.
- **P5 (gate calibration, new):** a big-but-coherent goal (epic-sized
  mechanical migration) is judged a LEAF — no forced division; routes to a
  single track.
- **P4 (clarity before size, adopted from the parallel spec):** a
  big-and-fuzzy prompt ("rebuild the whole data layer — event-sourced,
  real-time, multi-region; not sure exactly what we need yet — decompose
  it into workstreams") — the session refuses to divide, names the two
  remedies and pursues clarity, rather than cutting children of an
  unclear goal.
- **P6 (recursive gate at child dispatch, adopted from the parallel
  spec):** a parent child-section whose residue reveals multiple
  independent purpose-units — the fresh session re-runs the gate on the
  child, fails it on scope, and divides again, citing the parent without
  re-litigating landed contracts: asymmetric tree depth demonstrated
  live.
- **Template re-expression:** a synthetic milestone with feature parity to
  the M5.5 stress set (8 children; a conditional child; a two-gate child
  with required/conditional flags; an `external:<condition>` edge; shared
  definitions in contracts; both Deferred kinds; grounding numbers; risks)
  authored through the revised template by a fresh agent. Pass =
  fits-without-contortion verdict; every friction becomes a template fix.
  Honest label: synthetic feature-parity, not a second live milestone.
- Release rides the fork process: `scripts/bump-version.sh` minor, push.

## Decision Log

1. **Figure-ground inversion: the gate is canonical; the ladder becomes
   project-local annotation.** Overturns v7.23.0 Decision 1, whose recorded
   rejection reason ("no shared vocabulary") is answered by keeping names
   as annotations, not strata. Rejected: keep the canonical ladder — its
   own dry-run eroded it and three of four retro watch items are artifacts
   of it. Rejected: delete the skill outright — the derivation contract,
   template, and pipeline are validated organs the new frame still needs.
2. **Name: `decomposing-goals`.** Verb-object gerund per repo convention
   (organizing-sprints, implementing-tickets); "decompose" is the verb the
   board vocabulary already uses (DECOMPOSE outcome, decompose procedure).
   Rejected: keeping `roadmapping` (human chose a rename; the old name
   names the artifact, not the act). Rejected: `dividing-goals` /
   `mapping-goals` (no existing vocabulary anchor). Lineage across the
   parallel sessions: `decomposition`, then bare `decomposing`, were
   each chosen under spec A's pure-doctrine packaging (a noun, then a
   bare gerund); when the skill regained its pipeline, the verb-object
   workflow convention applied and both fell.
3. **Seam = define/divide (functional), not slice-altitude.** Brainstorming
   defines one goal of any size; decomposing-goals divides. Rejected:
   merging division into brainstorming — v7.23.0 Decision 4's reason
   stands (highest-frequency skill carrying rarely-used weight).
4. **Gate canonical in decomposing-goals; ticket-gate.md stays the board
   rendering.** Rejected: moving/graduating ticket-gate.md — battle-tested
   board schema isn't moved for structural reasons (echoes v7.23.0
   Decision 6). Rejected: a third "verifiable" check — observable
   acceptance is part of WELL-DEFINED.
5. **Tree + typed-edge DAG overlay; single parent; hoist shared subgoals;
   no persisted OR-branches.** Rejected: multi-parent decomposition — it
   splits the flow-back address and ownership. Rejected: HTN-style
   persisted alternatives — a roadmap is a commitment record, not a search
   space; alternatives live in Decision Logs.
6. **Lazy frontier: a branch divides only as it nears execution.**
   Rejected: upfront full decomposition — the recorded staleness evidence
   for approach sketches applies to child cuts one level up.
7. **Recomposition: closing a parent is verification against its own
   acceptance.** Rejected: leaf-only verification — all-children-green ≠
   parent-achieved; composition risk would accumulate silently.
8. **Zero new substrate.** Rejected: a tree registry file — the citation
   chain + board edges + tracking maps already carry the tree; a registry
   would violate the fork's simplicity doctrine and drift.
9. **Challenger: always assess, speak only when it would change the
   decision; grounded; once; before convergence; offer-not-veto; the
   human's override is absolute.** Chosen by the human. Rejected:
   always-voice (noise; generic-consultant checklists). Rejected:
   challenge-as-approval-gate (substitutes agent taste for human taste).
   Root-purpose referent: CLAUDE.md short-prose top goal, routing to a
   standing root spec where the project keeps one (human's convention).
10. **Situating at four radii added as a fourth move; the vendored grill
    quote untouched.** Rejected: editing the vendored quote — it is marked
    vendored verbatim and shared with execplan's reference to it.
11. **Evidence = RED challenger baseline + GREEN suite + regression
    P1/P2/P3 + P5 + synthetic template re-expression now** (P4/P6
    joined at the cross-session synthesis — Decision 13), rather than
    waiting for a first live roadmapping run. The dry-run validated the
    template and contract, not the ladder-vs-gate question; the rewrite
    preserves the validated organs and re-runs their suite. Rejected: full
    evals harness (v7.23.0 Decision 7 reason stands). Honest limitation
    recorded: the re-expression is synthetic feature-parity, not live.
12. **writing-plans keeps its sub-slicing body.** The v7.23.1-trimmed text
    is validated; only ownership/pointer language changes. Rejected:
    hollowing it to a bare cross-reference — plan-writers shouldn't open a
    second skill for a four-item list they apply constantly.
13. **Cross-session seam synthesis: spec A's in-session Topology Mode
    rejected; define/divide stands; the ordering clause declined on
    evidence.** A parallel spec of the same initiative ("spec A": the
    skill dissolved to a one-page doctrine, the template to execspec,
    session behavior folded into brainstorming as an in-session Topology
    Mode) was refuted by its own implementation plan: its hostile read
    had to patch brainstorming's checklist with a "bend note" because
    checklist steps 4 and 10 are leaf-shaped — a wrong-boundary smell
    the define/divide seam does not produce. Carried from spec A's
    lineage: the one-child misfire's second diagnosis (a cut that found
    no independently-landable seam — an arm that routes to a
    keep-together verdict, big-but-atomic staying one leaf, not back to
    brainstorming; the ceremony arm was already v7.23.0's rule) and
    pressure scenarios P4/P6.
    DECLINED from the parallel text: the explicit clarity-before-size
    ordering clause ("the checks run in order") — the parallel session's
    own P4 run scored 2/2 PASS against the SHIPPED clause-less v7.24.0
    text, so the control shows no failure and the guidance is not
    authored (doperpowers:writing-skills' rule); the ordering is
    emergent from the two checks' distinct remedies, corroborated by
    P5's agent articulating it unprompted. Leaf-size anchor resolved for
    consistency: doctrine keeps the moving-envelope language; the board
    rendering's battle-tested "roughly 1–2 ExecPlans" stays the only
    numeric anchor.
14. **Name resolved to the bare gerund: `decomposing-goals` →
    `decomposing` (2026-07-24, v7.24.2).** The human re-opened the three
    synthesis forks (seam, dissolution, name) for discussion against the
    archived lineage originals; the first two stood, this one flipped.
    Rationale: the repo's naming grammar — compound gerunds exist to
    discriminate within a family (writing-plans vs writing-skills;
    organizing-sprints; implementing-tickets), while a unique act takes
    the bare gerund, and brainstorming, this skill's seam peer, is the
    precedent (brainstorming DEFINES, decomposing DIVIDES — morphological
    peers). No decomposing-* family exists, so "goals" was doing only
    pedagogical work already carried by the description's first clause
    and the body's first sentence ("Work is a tree of goals"). The
    parallel lineage's human had resolved the same fork to `decomposing`
    once before. Rejected: keeping `decomposing-goals` — thesis-in-name
    pedagogy judged redundant; the misfire risk on code-decomposition
    prompts ("decompose this monolith") is gated by the description,
    which is what routing actually reads. Rejected in lineage:
    `decomposition` (breaks the gerund convention).

## Surprises & Discoveries

- The ladder's own acceptance run had already begun converting it to the
  gate: the round-1 dry-run fix ("nesting is for children that need
  decomposition, not children that are large") IS the gate criterion,
  discovered under contact and recorded as a wording fix.
- Three of the four v7.23.0 retro watch items dissolve by construction in
  the level-free model (vocabulary drift; the epic-child ticket species;
  ladder fit). The fourth (contract staleness across in-flight children)
  survives and is mitigated by the lazy frontier — fewer pre-cut in-flight
  contracts exist at any moment.
- KAOS goal-refinement terminates refinement at "assignable to an
  individual agent" — the gate's WELL-SCOPED check with 1990s agents;
  rolling-wave planning is the frontier principle under a PMI name. The
  proposal has independent prior art on both new axes.
- Three parallel sessions independently converged on gate-replaces-
  ladder; the divergences were one taste fork (the name — resolved
  `decomposition` → `decomposing` → `decomposing-goals`) and one
  structural fork (seam placement — settled by the checklist-bend
  evidence, Decision 13). The gate's own fork taxonomy classified the
  meta-process's forks correctly: the structural fork fell to evidence;
  only taste needed the human.
- The parallel spec legislated clarity-before-size as an explicit
  ordering clause; the shipped clause-less text passed its P4 2/2 — the
  ordering is EMERGENT from the two remedies being different. A live
  demonstration of the constraint-minimization doctrine: the rule was
  real, the hard wording was unnecessary.

## Outcomes & Retrospective

**2026-07-21 — acceptance run (RED licensed the challenger edit; GREEN
suite 10/10 PASS at first run; template round 1 NO → nine fixes → round 2
YES + four refinements).**

- **RED (challenger baseline, current brainstorming, 2 reps):** both reps
  challenged the idea's internal fit against the stated top goal
  (visibility problem, grounded in the root spec) but stayed inside the
  proposed frame — 0/2 surfaced the dominant adjacent levers (SMS
  reminders, deposits), and both ASSUMED an existing reminder channel
  ("the confirmation and reminder messages you send") when the scenario's
  repo has none. The failing test: the outward move is absent at
  baseline; the challenger wording was aimed at exactly this gap.
- **GREEN challenger-speak (3/3 PASS):** every rep challenged once,
  before convergence, grounded three ways — the root-spec fact (clients
  never open the app), the codebase absence (no reminder mechanism
  exists: the exact fact baseline papered over), and world priors (the
  appointment-reminder literature) — each ending in recommend-then-
  confirm with the override explicit. Low variance: all three converged
  on the same shape (reframe to SMS reminders; loyalty parked or
  re-scoped phone-first).
- **GREEN challenger-silent (3/3 PASS):** every rep declared the idea
  on-goal in a sentence and went straight to the load-bearing residue
  (the cancel/refund policy fork). No manufactured challenge.
- **P1 (epic routes up) PASS:** flagged four purpose-units, recommended
  decomposing-goals with confirmation, grilled no child details; bonus
  grounding catch (the missing driver foundation as likely first child).
- **P2 (slice stays) PASS:** no route-up; grill proceeded. Noted: the
  challenger fired on the scenario's genuine goal-tension (CSV export vs
  the anti-spreadsheet purpose) — grounded and decision-relevant, so
  within contract, but recorded as the over-firing watch item below.
- **P3 (pre-landed child) PASS:** listed the parent's landed decisions
  as settled (purpose/acceptance, X1, X2, the C1 edge, track hint),
  grilled residue only (partial refunds first; window and trigger-rights
  queued).
- **P5 (gate calibration) PASS:** refused to divide a 400-file
  migration under "this feels huge" pressure; walked the split signals
  and rejected each; located the real failure in WELL-DEFINED (assertion
  and landing strategy forks) and routed it to the grill; classified
  batch fan-out as execution mechanics below tree resolution; rejected
  the tempting infra/specs cut on keep-together grounds and named the
  one-child no-op.
- **Template re-expression round 1** (synthetic feature-parity with the
  M5.5 stress set — labeled synthetic, not a live milestone): verdict
  "fits without contortion: NO" — ~90% fit, nine frictions, all applied
  as template fixes: backward citation for pre-landed children; a spike
  track hint; authority-vs-content contracts (delegated content names
  its owner and delivering gate); disjunctive parent acceptance gets a
  named home; contracts that outlive the unit declare it (promotion is
  a closing-time action); the early-close rule moved into the Tracking
  Map; not-dispatched status annotates dispatchable / blocked /
  waiting-external; the Consumes-vs-child tiebreak (participates in
  contracts or edges ⇒ child); decomposing-goals children may state
  acceptance coarsely.
- **Template re-expression round 2** (revised template, same brief):
  **"fits without contortion — YES."** The reviewer noted the template
  "explicitly anticipated the hard cases" (backward citation, the
  conditional spike + parent-level disjunction, delegated contract
  content, the external precondition, the coarse decomposing-goals
  child, outliving contracts). Four vocabulary-level refinements
  applied from its report, per the v7.23.0 round-2 precedent:
  `blocked-by` admits `external:<condition>` as a start-time gate and
  `C_n.G_k` for gate-level precision (the old grammar conflated WHETHER
  a child runs with WHEN it may start); the not-dispatched status
  admits "deliberately late — see Ordering"; a named CLAUSE of a
  contract may outlive the unit, not only whole contracts. Noted
  without action: a conditional child restates its conditionality in
  four fields — redundancy with drift risk, no contradiction.

- **P4 2/2 PASS and P6 2/2 PASS — run by the parallel session against
  the SHIPPED v7.24.0 text** (post-release confirmation archived on the
  `decomposing-gate` branch, commit dad1f4d; this session's duplicate
  runs were stopped by the human as redundant). P4: both reps caught
  the WELL-DEFINED failure under size pressure and drew the
  grill-vs-spike line correctly — with no ordering clause in the text,
  which is why Decision 13 declines to author one. The challenger also
  fired appropriately (event-sourcing serves the auditability purpose;
  real-time/multi-region flagged as unjustified means) — first
  counter-evidence against the over-firing watch item. P6: both reps
  re-ran the gate at child dispatch, failed it on WELL-SCOPED, divided
  that branch one level deeper than its leaf sibling, kept the parent's
  contracts landed, and held the parent-level reconciliation acceptance
  as recomposition rather than inventing a fourth child.

Retro watch items: challenger over-firing on borderline goal-tension
(P2's CSV question — watch in live use; P4 later supplied first
counter-evidence of appropriate firing under a means-heavy prompt); the
first live decomposing-goals run (carried over from v7.23.0's retro —
still pending); contract staleness across in-flight children (carried;
structurally mitigated by the lazy frontier, unproven until a live run);
the declined ordering clause's contingency — if live use ever shows a
fuzzy goal carved into children, the parallel lineage's one-sentence fix
sits ready on `archive/decomposing-gate-synthesis` (Decision 13 flips on
that observation, no new design needed).

## Revision Notes

- **2026-07-21 (cross-session synthesis, post-7.24.0 — released as
  7.24.1).** A parallel session's spec of the same initiative (~90%
  identical architecture; lineage archived on
  `archive/decomposing-gate-synthesis`, its post-release P4/P6
  confirmation on `decomposing-gate` @ dad1f4d) was synthesized in
  after release. Adopted: the one-child misfire second diagnosis
  (SKILL.md Common Mistakes), scenarios P4/P6 with the parallel
  session's 2/2 + 2/2 shipped-text evidence, the name lineage
  (Decision 2), and the Topology Mode rejection record (Decision 13).
  Declined with evidence: the explicit clarity-before-size ordering
  clause (Decision 13). This document remains the initiative's design
  of record.
- **2026-07-24 (synthesis re-litigation — released as 7.24.2).** The
  human re-opened the three synthesis forks against the archived
  originals (`archive/decomposing-gate-synthesis`). The seam verdict and
  re-founding stood, with two record corrections: spec A never
  pointer-ized writing-plans' sub-slicing (body preservation was a
  shared decision, explicit even in its 8b214e5 original), and
  dissolution preserved the artifact organs (template moved
  near-verbatim to execspec, flow-back rules carried verbatim) — what it
  lacked an address for was the PROCESS organs: full pipeline resolution
  and the tend/recomposition lifecycle. The name fork flipped per
  Decision 14: skill directory renamed to `skills/decomposing/`, all
  call sites swept (brainstorming, organizing-sprints, writing-plans,
  ticket-gate, implement-decompose, the template's track-hint enum, and
  the live swarm-campaign roadmap spec + cloud-scale research docs).
  Body text above retains the shipped-era name where it narrates
  v7.24.0/7.24.1 history.
