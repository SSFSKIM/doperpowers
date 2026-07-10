# Umbrella Sprint Spec — Skeleton

The proven section layout for an organizing-sprints spec (700–1000 lines at
full sprint scale). Save to `docs/<milestone>-sprint-spec.md` in the
consumer repo (its own conventions override). Section numbers are a
convention, not a contract — keep the order; compress or merge for small
dumps (SKILL.md, Scaling down).

## Header block (unnumbered, top of file)

A blockquote declaring:

- **Living document** — which sections stay current during the sprint
  (Progress, Decision Log, Surprises, Retrospective) and that every
  revision lands in Revision Notes with a reason. This is the selective
  transplant of ExecPlan discipline (PLANS.md / doperpowers:execspec) to
  umbrella scale: acceptance as observable behavior, living tail — but NO
  Concrete Steps. A delegated epic derives its own ExecPlan from this
  document.
- **Evidence sources** — the observation note (origin, date), the grill
  session (date, question range), the code explorations run.
- **Verification baseline** — the commit(s) every "verified current state"
  claim was checked against, and the sprint's integration branch.
- **Sister documents** — the prior sprint spec; where the next milestone's
  reservation lives (§16).

## Notation legend

Code-reality classes: `[BUILT]` · `[PARTIAL]` · `[NOT-BUILT]` · `[BUG]` ·
`[MISREAD]`. Decision markers: `[DECIDED]` grill-landed · `[DECIDED-AUTO]`
landed by code facts alone (alternatives dissolved) · `[EXTERNAL: owner]`
awaiting a named person. Work items: `(new)` new code · `(modify)` existing
code · `(promote)` already exists on a branch; promotion ships it.

## §0 How to read this document

One line per section group. Point readers at the footgun section (§5)
before they build anything.

## §1 Purpose / Big Picture

What the world gets when this sprint lands — one paragraph per user role,
phrased as behavior ("the student opens X and sees Y"). Close with the
smoke that re-enacts those paragraphs (accounts, steps): that smoke is the
sprint's final acceptance.

## §2 Sprint frame

Table: goal · period (+ mid-sprint checkpoint) · team and their tracks ·
scope principles (feature freeze: nothing outside this document enters the
sprint) · relationship to the previous milestone (what was declared closed,
what carried over, on what condition).

## §3 Definition of done

The gate list, all observable: P0 epics complete (their acceptance
criteria, not their commits), the role-smoke passes with zero regression,
integration branch promoted, migrations applied. State what P1
non-completion means (rolls over; doesn't block).

## §4 Context & orientation

Enough codebase orientation that a fresh joiner starts from this document
plus the repo's own instructions file. Later sprints reference the prior
spec's §4 and add only deltas.

## §5 Verification table — observation vs code reality

The footgun section; the note is never trusted past this point.

- **§5.1 Confirmed real bugs** — observation → diagnosis → evidence
  (file:line where the diagnosis is surprising or contested).
- **§5.2 Misreads corrected** — observation → what the code actually does →
  the real requirement extracted from under the misread.
- **§5.3 Missing or partial** — the sprint's real work, each row naming the
  epic that owns it.

## §6 Epic decomposition

Streams (thematic groups) → epics. Epic numbering continues across sprints
(EP-18 follows the prior sprint's EP-17) so epic ids stay unique in
tracking forever. Each epic carries, in order:

1. **Context** — where the observation came from, quoted.
2. **Decision log** — the decisions that shaped this epic, with rejected
   alternatives; `[DECIDED-AUTO]` marked as such.
3. **Verified current state** — pointer into §5 rows plus anything
   epic-local.
4. **Work items** — numbered, each tagged `(new)`/`(modify)`/`(promote)`,
   carrying its own priority where it differs from the epic's.
5. **Acceptance criteria** — observable behavior only: "this input produces
   this visible result", never "the structure was added".
6. **Dependencies** — ordering against other epics; shared files ("same
   file as EP-x — same owner, or layout merges first").

## §7 Priority cut

The P0 list (the sprint gate) as one table with a one-line reason each.
Everything else is P1 (rolls over) or P2 (opportunistic).

## §8 Dependency & parallelism map + assignment

Which epics chain, which parallelize, who owns which track. Group same-file
epics under one owner; layout/structural changes merge before features
stack on them.

## §9 Progress *(living)*

Checklist by epic, updated as work lands. Unfinished P1s recorded here at
close, for roll-over.

## §10 Decision Log *(living)*

The global grill record: every decision, its rationale, its rejected
alternatives and why each lost — auto-landed decisions included. Decisions
made mid-sprint are appended here, not scattered.

## §11 Open questions

Only externally-owned remainders survive authoring: item · owner ·
deadline. Everything else landed in §10 before v1.

## §12 Surprises & Discoveries *(living)*

Seeded at authoring with the grounding phase's finds (dead inputs, schema
drift, misreads); appended during the sprint. Each entry carries evidence.

## §13 Tracking map

The materialization contract and its record:

- Disposition of every pre-existing open ticket the sprint touches (absorb
  / defer / re-cut / close candidate), each with its reason.
- After materialization: epic → issue number mapping, milestone, edges cut,
  lint result. (Each materialized body cites its epic section back here —
  spec path + epic id — so ticket and spec point at each other.)

## §14 Risks

Risk · blast radius · mitigation. Include process risks (migration
ordering, same-file contention), not only product risks.

## §15 Interface contracts

Schemas, migrations, API shapes that multiple epics or workers share — the
things that break silently when two epics assume differently. Numbered
migrations note the repo's collision rule if it has one.

## §16 Deferred — the next milestone's reservation

Named epics reserved for the next milestone, each with why it is not this
sprint; bundles awaiting an external trigger. This section seeds the next
organizing-sprints run — and each entry is registered as a `deferred`
ticket at materialization time.

## §17 Outcomes & Retrospective

"Pending — written at finish." until the sprint closes; then what was
achieved against §1, gaps, lessons.

## Revision notes

Every post-v1 edit: date, what changed, why.
