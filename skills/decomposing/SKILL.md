---
name: decomposing
description: Verified guidance on dividing a goal too big for one agent to own as one unit into child goals (a roadmap), and on tending a live goal tree as children land.
---

# Decomposing

## Overview

Work is a tree of goals. Every node is a goal — a purpose with observable
acceptance — whatever the project calls it: milestone, epic, phase, slice,
ticket. doperpowers:brainstorming defines one goal at a time, whatever its
size, and for a goal whose pieces interact it matures the joint design
before handing it here; this skill divides a goal that fails the gate
below into child goals one level down, and tends the tree as children
land; the leaves are executed by their routes.

The product of one run is a **composite spec**
(`references/composite-spec-template.md`): a living spec
([../execspec/references/living-spec.md](../execspec/references/living-spec.md))
with the roadmap — children, edges, ordering — embedded as sections under
the design, not a separate document type. A composite's child can itself
be a composite, at every altitude, and the document tree is the composite
tree: one spec per composite, none per leaf. A leaf's contract is its
section in the composite; what it adds are execution artifacts — its brief
or plan and the ledger that records its run, or a spike's findings.

doperpowers:organizing-sprints is the sibling with the other intake. It
turns raw *testimony* (an ideadump that may misread the code) into a
sprint; this skill divides trusted *intent*, so it keeps no verification
table, though the cut is still grounded in the code.

## The Gate

One criterion decides division, at every altitude — two checks:

- **Well-defined** — every fork the work will hit has an owner or an
  answer: purpose stated, acceptance observable, load-bearing decisions
  made. When it fails, what is missing is knowledge: grill it
  (doperpowers:brainstorming) when a conversation can close it; make it a
  child whose deliverable is findings (a spike or research goal) when it
  needs real work.
- **Well-scoped** — one agent can reliably own it as one unit. "One
  agent" means one accountable context: an owner may marshal subagent
  workers (the milestone workers of doperpowers:subagent-driven-execution) without
  that being decomposition — execution mechanics live below the tree's
  resolution. When it fails, divide into work-children.

A goal that passes the gate is a leaf whatever its size — it goes to its
route, and this skill's reach ends. Reliably-ownable is a moving
envelope, not a size class: big-but-coherent work that one context can
carry is one leaf. Depth is an output of the gate, never a target, and it
is asymmetric by nature: one branch bottoms out in a single one-unit spec
while its sibling divides twice more. A cut that yields one child is the
gate misfiring: the goal was already a leaf, or the cut found no seam
where children land independently.

**Split signals** (any altitude): parts with different state owners,
invariants, failure modes, or verification strategies; acceptance you can
only phrase by chaining unrelated behaviors with "and"; grill forks whose
answers keep depending on other unanswered forks. **Keep together:**
splitting would create an invalid intermediate state; parts must land in
the same transaction or cutover; neither part is meaningful or verifiable
alone. Below the slice the same signals govern splitting inside one spec —
the milestone sizing in doperpowers:execspec's
references/living-spec.md is this list applied there.

## The Tree

- Decomposition is a tree: every child has exactly one parent — its
  reason to exist and its flow-back address. A subgoal two parents need is
  hoisted to their common ancestor as its own child; the shared need
  becomes dependency edges, never a second parent.
- Dependencies are edges, not structure: typed (`blocked-by`,
  `conditional-on`, `external:<condition>`), cross-branch allowed,
  acyclic. The tree says what adds up to what; the edges say what waits
  for what.
- Levels have no canonical names. Milestone, Epic, Phase, Sprint are
  project vocabulary: annotate nodes with the project's words, and keep
  them out of the doctrine.
- The root is the project's standing purpose. Convention: CLAUDE.md
  states the top-level goal as short prose; a project that keeps a
  standing root spec routes to it from that line. Every new goal enters
  the tree by being situated against the root or an existing node —
  brainstorming's job, not this skill's.
- No OR-branches: the tree records the chosen division; a cut that was
  seriously weighed and lost is named with the division's reason.
- The tree is not a registry file. It is the citation chain (each
  child's artifact — brief, plan, ledger, PR body, ticket, or a composite
  child's own spec — opens by citing its parent), the board's typed
  edges, and the composite specs' tracking maps.

## The Frontier

The frontier governs commitment, not capture. Divide one level per run,
and cut a branch only as it nears execution: child boundaries, gates,
and binding contracts drawn today for far-off work go stale as landed
siblings move them, and an undivided branch is cheap to re-cut. A child
whose own division can wait carries the grain hint "decomposing run at
dispatch" and nothing more. Design prose is the opposite case — whatever
the joint view produced about a distant branch stays in the parent at
the depth it was produced, as advisory inheritance (see the Derivation
Contract): expected to be revised by the time the branch nears execution,
and cheap to revise precisely because it was written down. A composite
spec is binding near the frontier and advisory in the distance;
staleness in advisory content costs a rewrite, while an uncaptured
insight is unrecoverable.

## A run

Intake has two shapes. A coupled goal arrives as a matured, approved
design — doperpowers:brainstorming matured it precisely because its
pieces interact (one that arrives undesigned goes there first: its
interaction surface is designable only with everything in view). That
design document is the run's primary input, and the roadmap sections
extend it in place: one document, design up top, roadmap below. An
uncoupled bundle arrives undesigned — its pieces share no design surface,
so there was nothing to mature jointly; the defining work happens here,
and the design sections stay thin.

What a run produces:

- **A cut grounded in the code.** Intent is trusted here, but a question
  the codebase can answer is answered by reading; for matured intake,
  verify the design's load-bearing code claims rather than re-deriving
  them. From a matured design, derive children along its natural seams.
  For an uncoupled bundle, propose tentative children as goals with
  ordering and get your human partner's reaction before deep grilling.
  Either way, check each child against the code for already-built or
  partially-built reality: deliberate initiatives assume greenfield more
  often than the code is. Over-merging hides independent shippables;
  over-splitting loses coherence — ask when unsure.
- **The residue, grilled** in batched frontier rounds, each question with
  your recommended answer (doperpowers:brainstorming's grill): child
  boundaries, dependency edges, cross-child contracts, authority grades,
  and reservations that belong to a later cut rather than this one. A
  matured design has already answered its architectural questions; an
  uncoupled bundle needs each piece's purpose and acceptance grilled
  here.
- **The composite spec**, per `references/composite-spec-template.md`,
  born landed: v1 already carries the design and the grill's decisions,
  each design decision graded for authority (the Derivation Contract),
  and it is kept current as
  [../execspec/references/living-spec.md](../execspec/references/living-spec.md)
  says. The check easiest to miss before anyone reads it is traceability:
  every load-bearing declaration in the design has a counterpart slot in
  the children, contracts, or acceptance sections.
- **Your human partner's approval of the committed spec**, before
  children start: the cut, the grades and the contracts bind every child.
  The Tracking Map names the approved commit. A design already approved
  in brainstorming needs their eyes only on what this run added.
- **Tickets, when the project keeps its backlog on the board**: children
  as tickets with typed edges through doperpowers:issue-tracker's
  scripts, bodies fleshed to the pre-spec bar and citing the composite
  (path + child id). They are registered from the approved spec: a batch
  cut from a draft has to be closed ticket by ticket. Deferred entries
  that are real work may register as parked tickets citing the composite,
  so overflow from the design session outlives the Deferred list. A
  document-only project has none — the tracking map is the handoff
  contract either way.

## Tending

Children go to their routes per their grain hint, each carrying its
section as pre-landed design and writing no spec of its own: a brief child
implements against its section and a dispatch brief; a plan child grills only its
residue (doperpowers:brainstorming) and writes its standalone execution
document (living-spec.md, "A child of a composite spec"); a spike writes
findings; a composite child runs this skill at its own dispatch.

Every child keeps a ledger. A plan child's record is its committed
execution document and the doperpowers:subagent-driven-execution ledger.
A brief child opens `docs/doperpowers/ledgers/YYYY-MM-DD-<child-id>.md` on
its branch at dispatch: it cites the composite (path + child id +
parent pin), carries the brief verbatim, and then Progress as deliverables
land, in-flight Decisions with their rationale, Surprises, and the
flow-back raised; its outcome section, written at close, is the child's
retrospective, and the Tracking Map points at it.

As children land, the tracking map and the sections their work touched
stay current (a composite in the earlier form continues its Decision Log
and Surprises, as living-spec.md says under "Keeping the spec current").
The Deferred section seeds the next cut.

Siblings authored or executed at the same time share the composite, so it
has one writer — the session running this skill: parallel authors editing
one file drop each other's commits. A child's author records its residue
in the child's own document, and that writer rewrites what it changes into
the child's section. When more than one child extends a contract before
any of them lands, open an interface ledger beside the execution
documents — every added name with its owner and consumers, the shared
files and the order they land in — reconciled before the first executor
starts and kept current as children land, so the interim contract siblings
code against is one document rather than several that disagree.

## Upward Revision

A child reads the parent's current state at dispatch, never a frozen
snapshot, and records the parent pin — the composite's commit as the
child received its section — in the citation that opens its artifacts, so
"what contract did this child execute" stays answerable. A child revises
its own means freely, and overturning advisory inheritance is revising
means: the child states what it chose in its own document, lists the
inherited sentence with its replacement for the parent's writer (evidence
in a line), and moves on, no reconciliation.

Discovery that touches a parent-owned end — purpose, acceptance, a
cross-child contract, an edge, a binding design decision, the division
itself — goes back to the session holding the composite, in the child's
escalation or report, with the evidence and the affected clauses (where
the parent is a board ticket, also as a `[parent-impact]` comment on it);
binding content the child never edits. That session judges materiality,
rewrites the parent, and tells the in-flight children whose contract the
rewrite touches. Purpose changes and material acceptance reductions go to
your human partner.

## Recomposition

All children green does not close a parent. The parent declares its own
acceptance at cut time — the observable state that closes the unit as a
whole, not the sum of child acceptances — and when the children have
landed, the session holding the composite verifies that acceptance
(integration seams, end-to-end behavior) and runs the lineage check: every
child's pin against the final parent revision (`git diff <the pin's
commit> -- <composite>`, read against what the child built) — incorporated,
explicitly irrelevant, or a corrective child. Only then is the
retrospective written.

A non-code parent closes on its verification evidence. A code-bearing
one — children that touched one executable surface, cross-child
invariants, multi-repo composition, or a composite that marks review
required — also gets the independent review its Verification section
names, on the integrated result (doperpowers:review-code); a defect that
review finds becomes a corrective child, and the parent recomposes again
when it lands.

Where the children are board tickets, bookkeeping returns the parent to
`ready-for-architect` (`recomposition-due`) when its last child goes
terminal instead of closing it, and the session holding the composite
records the verdict there: `done` for a non-code parent; a closure
package and `in-review` for a code-bearing one while its review runs, then
`done` (doperpowers:issue-tracker, Epics).

## The Derivation Contract

Each child section of the composite spec fixes:

- **Purpose** — one paragraph, the child's reason to exist;
- **Observable acceptance** — behavior, not implementation;
- **Dependency edges** — what blocks it, what it blocks;
- **Cross-child contracts** — the shared interfaces, invariants, and
  ordering rules it participates in;
- **Design inheritance** — the parent design content that bears on this
  child, each piece carrying its authority grade;
- **Grain hint** — brief (the section plus a dispatch brief is the
  whole contract), plan (a standalone execution document at milestone
  grain — the spec's execution section on its own, per
  doperpowers:execspec's references/living-spec.md), spike (deliverable
  is findings, never a merge), or another decomposing run at dispatch.
  Every child's executor is a fresh context, so the hint names the grain
  of the brief, never who runs it. The grain follows what the child
  needs, not the parent's scale: a child of one milestone, or a bundle of
  small items each clear from its section, needs no documents.
  Weigh the effort of writing a document and keeping it current against
  what it does for the work. Write the plans and specifications the work
  deserves: sizable, long-running work with several milestones, or a
  composite of several such specs, needs a document for reliable
  long-horizon execution; work that is scoped and clearly defined can run
  from a brief.

Everything the parent hands a child carries one of two authority
grades:

- **Binding** — what only the joint view could settle: purpose,
  acceptance, edges, cross-child contracts, and any design decision
  that would come out differently without the whole picture in view
  (shared data models, interface shapes, failure semantics that span
  children). Children do not re-litigate binding content; discovery that
  contradicts it flows back (Upward Revision) and is not overridden
  locally.
- **Advisory** — the parent's best full-picture thinking on matters
  local to one child: approach sketches, sequencing suggestions,
  anticipated pitfalls. The child inherits it as pre-landed grill
  input — it starts there instead of from a blank page — and may
  overturn it with evidence; the overturn is stated in the child's own
  document and listed for the parent's writer, not a reconciliation event.

Advisory is the default grade; content is binding because the composite
spec marks it so, with the joint-view reason attached. Capture is not
commitment: the parent records everything the design session produced —
the spec is the only durable memory this org has, and a stale written
decision is detectably wrong at child time while an uncaptured insight
is silently gone — but it binds only what the joint view actually
settled. A parent that binds child-local means converts every child
discovery into reconciliation traffic; a parent that withholds design
to "let the child figure it out" throws away decisions that were only
makeable with everything on the table.

The child treats its section and its design inheritance as pre-landed
grill input: it grills only the residue and does not re-litigate landed
decisions. Its section is its spec. A leaf whose residue design trips the
gate's split signals is a composite in disguise and gets its own composite
spec instead. The child's artifacts — its brief or plan, its ledger, its
PR or ticket — open by citing this composite spec (path + child id +
parent pin); that citation is what keeps the flow-back channel alive when
there is no board.
