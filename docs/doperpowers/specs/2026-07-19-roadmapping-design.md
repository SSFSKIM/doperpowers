# roadmapping — an altitude-recursive parent-roadmap workflow above the Slice (2026-07-19)

## Purpose

doperpowers' workflow ceiling is the Slice: brainstorming → spec →
writing-plans (controlled) or execplan (autonomous) each drive exactly one
slice. Above that altitude only one path exists, and it is reactive:
organizing-sprints turns a raw multi-observation dump into a sprint of
epics. There is no *deliberate, top-down* path — "here is an epic or
milestone of planned work; produce the parent roadmap that slice-level
work derives from." Brainstorming's current answer is one paragraph
("decompose into sub-projects") with no artifact, no derivation contract,
and no parent-child spec relationship.

This spec adds that path: a new sibling skill, `roadmapping`, that plans
one parent unit at any altitude above the Slice, decomposing it into
children exactly one level down — plus a third route out of brainstorming's
scope assessment. The ultimate aim is that the same discipline covers Epic,
Milestone, and eventually enterprise-scale roadmapping without new
per-level machinery.

## Vocabulary (canonical ladder)

**Milestone → Epic → Slice → Task.**

- **Slice** remains the unit of one spec or one ExecPlan. **Task** is a
  plan task (controlled) or an ExecPlan milestone M_n (autonomous). Below
  the Slice, decomposition belongs to writing-plans' Conditional
  Sub-Slicing (companion spec, same date) — a roadmap never reaches below
  slice boundaries.
- **"Phase" is a project-local alias, not a canonical level.** ida-solution's
  "M5 Phase 4" places Phase inside Milestone playing the Epic role; other
  projects may use it as a strategic tier *above* Milestone. The skill names
  the alias explicitly and does not design the above-Milestone tier
  (reserved, undesigned).
- Projects drop levels freely by size; a small project may run
  Milestone → Slice directly. Altitude count is an output, never a target.

## Design

### The skill: `skills/roadmapping/`

`SKILL.md` + `references/roadmap-spec-template.md` (layout convention of
organizing-sprints). Frontmatter description triggers on deliberate
multi-slice initiatives and routes away both neighbors: a single idea →
doperpowers:brainstorming; a pile of raw ungrounded observations →
doperpowers:organizing-sprints.

**Altitude recursion.** One run plans ONE parent unit at ONE altitude,
decomposing into children one level down. An epic-sized child of a
milestone roadmap gets its own roadmapping run at dispatch; a slice-sized
child goes to brainstorming or execplan. The Milestone workflow is not a
second skill — it is the same run one level up.

**Pipeline** (task per phase, in order):

1. **Ground the initiative** — explore the code/repo state the initiative
   touches. Lighter than organizing-sprints' verification table (intent
   here is trusted, not testimony to be verified), but "a question the
   codebase can answer is answered by reading" holds.
2. **Tentative child cut** — propose children as purpose-units with
   ordering; get the human's reaction BEFORE deep grilling (over-merge
   hides independent shippables; over-split loses coherence — ask when
   unsure).
3. **Grill** — one question at a time, recommended answer each: boundaries,
   edges, cross-child contracts, deferrals/reservations for the next unit.
4. **Author the roadmap spec** — per the template, born landed, execspec
   living tail.
5. **Self-review + human review gate** — placeholder/consistency/traceability
   scan, commit, human approves the document.
6. **Materialize onto the board (OPTIONAL)** — same shape as
   organizing-sprints' phase: children as tickets with typed edges via
   issue-tracker scripts, hard-gated on the human's spec approval. Used
   when the project runs the board pipeline; skipped for document-only
   projects. The tracking map is the handoff contract either way.
7. **Dispatch and keep alive** — children dispatch to their own tracks;
   the parent's Progress/Decision Log/Surprises stay current as children
   land; the retrospective closes the parent unit.

**Derivation contract** (the load-bearing seam). Each child section fixes:

- purpose (one paragraph),
- observable acceptance,
- dependency edges (blocked-by),
- cross-child contracts (shared interfaces, invariants, ordering rules),
- a track hint (controlled / autonomous / another roadmapping run).

At dispatch, the child treats its section as pre-landed grill input: it
grills only the residue and never re-litigates landed decisions. The parent
never sketches the child's technical approach — means belong to the child
(the case evidence: high-altitude briefs miss concurrency-level depth, and
approach sketches go stale as early children land). Discoveries that
contradict the parent flow back into its Revision Notes — never silent
divergence. This is the execspec discipline one level up.

### Template: `references/roadmap-spec-template.md`

Purpose-first opening + altitude declaration (which parent unit this
roadmap itself belongs to, if any) → children (id, purpose, acceptance,
edges, track hint, status) → cross-child contracts → ordering/dependency
map → deferred reservations for the next unit → tracking map (child →
spec path / ticket / status) → living tail (Decision Log, Surprises &
Discoveries, Outcomes & Retrospective, Revision Notes).

### Brainstorming's third route

Replace the scope-assessment bullet in `skills/brainstorming/SKILL.md`
(near-final wording):

> Before asking detailed questions, assess scope: if the request describes
> multiple independent purpose-units (e.g., "build a platform with chat,
> file storage, billing, and analytics"), flag this immediately. Work
> bigger than one slice belongs one altitude up: recommend
> doperpowers:roadmapping — it decomposes the initiative into children
> with acceptance and edges, and each child then returns through this
> skill (or execplan) with its parent section as pre-landed input. Confirm
> the route with your human partner before switching; don't drift into
> grilling slice details of an epic-scale request.

Plus one clarifying line near the terminal-state rule: the roadmapping
exit happens at scope-assessment time, before design; the after-design
exits remain writing-plans/execplan only.

### Cross-references

- organizing-sprints frontmatter description gains one routing sentence in
  its existing pattern: "For a deliberate top-down initiative use
  doperpowers:roadmapping." No other organizing-sprints content changes.
- roadmapping's description carries the reverse pointers (single idea →
  brainstorming; raw dump → organizing-sprints).
- writing-plans' Conditional Sub-Slicing and roadmapping reference each
  other as the below-Slice / above-Slice halves of the decomposition
  doctrine.

## Acceptance

- **Template dry-run:** one real ida-solution milestone (candidate: the M5
  material the vault documents; final pick at implementation) re-expressed
  as a roadmap spec using the template. Pass = it fits without contortion;
  every friction found becomes a template fix before release.
- **Pressure scenarios** (fresh-context sessions, writing-skills style):
  - an epic-scale prompt to brainstorming yields the roadmapping route
    offered and confirmed — not a slice-grill of the whole initiative;
  - a slice-scale prompt does NOT route up (false-positive check);
  - a roadmapping run's child section, handed to a fresh brainstorming
    session, is treated as pre-landed input — the session grills residue
    only.
- Release rides the normal fork process: `scripts/bump-version.sh`,
  codex-plugin sync.

## Decision Log

1. **Canonical ladder is 4 levels (Milestone→Epic→Slice→Task); "Phase" is a
   documented project-local alias.** Rejected: 5-level canonical ladder
   with Phase on top — designs a tier no current project uses and keeps
   "Phase" overloaded against ida-solution's real usage (M5 Phase 4 =
   Milestone containing Phase-as-Epic). Rejected: altitude-agnostic
   unnamed levels — maximally flexible but gives roadmap documents no
   shared vocabulary.
2. **One altitude-recursive workflow; v1 worked at Epic→Slice.** Rejected:
   Epic-level only with Milestone deferred — rediscovers the same document
   shape later. Rejected: distinct per-level workflows/templates —
   speculative ceremony for an altitude only exercised reactively so far.
3. **Derivation contract = purpose + observable acceptance + edges +
   cross-child contracts; children grill only the residue.** Rejected:
   parent sketches child approaches — front-loads design where detail is
   least known (the Task 8 depth lesson) and goes stale. Rejected: thin
   parent (names + order only) — loses the cross-child contracts and
   parent-level acceptance that make a roadmap load-bearing.
4. **Entry: brainstorming routes up as a third confirmed route; protocol
   lives in its own skill; direct invocation possible.** Rejected:
   deliberate direct entry only — epic-scale ideas arriving through the
   front door would stay unrouted. Rejected: protocol inside brainstorming
   — the highest-frequency skill would carry rarely-used weight, and
   Milestone→Epic recursion reads wrong inside an idea-stage skill.
5. **Board materialization is an optional closing phase, organizing-sprints-
   shaped, hard-gated on spec approval.** Rejected: mandatory
   materialization — a hard gate without a validated failure state, forced
   onto projects that don't run the board. Rejected: document-only —
   discards the proven materialization path for the projects that do
   (ida-solution).
6. **Sibling skill, self-contained template (approach A).** Rejected:
   shared parent-spec template refactor — modifies battle-tested
   organizing-sprints content for structural rather than behavioral
   reasons, and forces two genuinely different documents (verification-
   table-hearted vs derivation-contract-hearted) through one mold.
   Rejected: merging organizing-sprints in as a reactive intake — a
   speculative rewrite of tuned content; the seam that matters is intake
   shape (testimony-to-verify vs trusted intent), not output shape; can
   merge later if practice converges.
7. **Validation: dry-run + pressure scenarios.** Rejected: design-review
   only — first real use of a roadmap skill is an expensive place to
   discover template failure. Rejected: full superpowers-evals harness —
   geared to upstream compliance judging; marginal signal over targeted
   pressure tests is small for fork-local additions.
8. **Name: `roadmapping`.** Matches the repo's gerund convention
   (brainstorming, writing-plans, organizing-sprints).

## Surprises & Discoveries

- The initiating request itself carried the Phase/Milestone ordering
  contradiction (Phase→Milestone in the enterprise ladder vs
  Milestone→Phase in ida-solution) — surfaced by the grill and resolved as
  the alias rule (Decision 1) rather than picking a winner.
- organizing-sprints already occupies the Milestone altitude *reactively*
  (a sprint of epics IS a milestone roadmap grown from a dump), which is
  what made the sibling seam obvious: the two skills differ at intake
  (testimony vs intent), not at output shape.

## Outcomes & Retrospective

Pending — written after the template dry-run, the pressure scenarios, and
the first live roadmapping run.

## Revision Notes

(none yet)
