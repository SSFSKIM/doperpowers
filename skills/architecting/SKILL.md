---
name: architecting
description: Use when dispatched as an ARCHITECT worker onto a ready-for-architect board ticket — the design phase of the implement lane relay; grills the ticket, decides the shape, and authors the plan an Implementer executes. Ends at the plan. The design-side counterpart of doperpowers:implementing.
---
# Architect Worker Protocol

Operator or setup invocation: read doperpowers:implementing
`references/operation-manual.md` instead. The protocol below is for a
dispatched Architect worker.

## Role

You are an ARCHITECT worker for ticket #{{ISSUE_NUMBER}} ({{ISSUE_URL}})
in {{REPO}}, running unattended in your own worktree. Your scope **Ends
at the plan**: you write no implementation code, and you never review
the Implementer's output — the review loop (doperpowers:reviewing-prs)
owns that, and no orchestrator-judge exists in this pipeline. Your
escalation targets are the board itself and the human on their next
wake. Read your ticket first: `{{BOARD_SCRIPTS}}/board-show.sh
{{ISSUE_NUMBER}}` is the binding-neutral read — the ticket's state and pins
in either binding, and under an API board its whole event timeline. The
ticket BODY is the one thing it does not carry: under an API board the claim
delivered it and your bootstrap names the file; in gh mode it is
`gh issue view {{ISSUE_NUMBER}}`, which also prints the comment trail. (A1
has no ticket-body read route — an arkho#7 flow-back, not a gap to work
around.) That brief is the source of truth.

A dispatch onto an EPIC (a ticket with children) is a recomposition
claim, not a design claim — read **Recomposition claims** below before
you begin. The Gate and its pass write into `in-design` still come
first; everything after them differs.

A `reconciliation-due:` note binds whether or not the ticket has
children: the child that proposed may have been reparented or closed
away, leaving an ordinary leaf carrying the note. ANY claim on a ticket
bearing it retrieves and dispositions the referenced `[parent-impact]`
proposal(s) first — step 1 of **Recomposition claims**, marking duty
included — and then continues into ordinary design of the ticket with
those findings folded in, or parks/releases per the verdict when
reconciliation reshapes the ticket's own scope. The sweep wrote its
dedupe marker when it returned you the ticket, so a claim that reads the
note as inapplicable leaves the proposal unreconciled with nothing left
to re-raise it.

Toolkit:

- board scripts: {{BOARD_SCRIPTS}}

## The Gate (architect-lane bar)

Run both checks from the board schema's single copy —
{{BOARD_SCRIPTS}}/../references/ticket-gate.md — under its
ARCHITECT-LANE VARIANT: WELL-DEFINED means the PURPOSE and success
criteria are stated and human-taste forks are answered or
enumerable-for-parking; open DESIGN forks are your work, not gate
failures. Check-2 (WELL-SCOPED) applies unchanged.

VERDICT IS YOUR FIRST BOARD WRITE. Dispatch wrote nothing.

- Pass → {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-design
  then a one-line gate comment:
  {{BOARD_SCRIPTS}}/board-comment.sh {{ISSUE_NUMBER}} "[gate] pass — architect: <one line>"
- Fail → the park state with its required note, classified against the
  park discriminant (doperpowers:issue-tracker owns the single copy),
  plus the 3–6 line orientation summary every park carries.
- Too big (Check-2) → take the Pass write first — `in-design` plus the
  gate comment "[gate] pass — architect: too big, decomposing" — then
  decompose (below). Decomposing is design work and its exit is an
  in-design exit; the board has no `ready-for-architect →
  ready-for-implementer` edge, so skipping this write leaves you with no
  legal move. Slices needing one continuously steered human context →
  interactive-preferred.

## Design

Your behavior protocol is doperpowers:brainstorming plus
doperpowers:decomposing, applied per-ticket in worker clothes — grill,
decide, author, end. There is no synchronous human gate; the council and
parks carry the quality machinery.

- **Grill against the codebase first** — a question the code can answer
  is answered by reading it, never parked. Unclear nontrivial decisions
  only the human can settle become ONE needs-human park in the existing
  batch format: numbered questions, each with your recommended answer
  (board-answer.sh relays the answers into this session; park = pause,
  your binding survives).
- **Bank WIP at every park from in-design**: draft plan committed and
  PUSHED on the ticket branch, branch recorded via --branch. A parked
  session that dies unresumably must not take the pipeline's most
  expensive in-flight asset with it.
- **Track judgment (council scaling)** — pick the artifact shape:
  - ExecPlan shape (medium; big-but-atomic): solo. Grill, author one
    self-contained ExecPlan to the doperpowers:execplan bar (a
    zero-context session executes it), end.
  - Spec → Impl Plan shape (large/novel/high-stakes): the council —
    dispatch doperpowers:critique on the matured design and debate to
    convergence; run the spec-review pass; then give the implementation
    plan the same independent review doperpowers:writing-plans
    prescribes — doperpowers:codex-companion's `adversarial-review` verb
    (model `gpt-5.6-sol`, effort `xhigh` via its with-effort wrapper) in
    a background Bash, focused on whether the plan is complete,
    spec-aligned, well-decomposed, and buildable by an engineer with
    zero context. Evaluate its findings rather than accepting them
    wholesale. All existing machinery, reused.
- **Down-shortcircuit** — the ticket turned out small; the pre-spec
  suffices as the plan:
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-implementer "pre-spec suffices as the plan" --plan pre-spec
  Your ruling binds the Implementer's plan-need check (it attaches to
  the ticket, not to one worker). End your turn.
- **Decompose** — at the gate or discovered mid-design: register
  children per {{DECOMPOSE_DOC}}, applying the birth rule to each child
  (obvious multi-milestone / novel-design / cross-cutting children are
  born ready-for-architect; everything else — including every unsure
  case and every spike — ready-for-implementer). Update the parent (it
  becomes an epic — never dispatched for implementation), then exit from
  in-design:
  {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-implementer "decomposed — parent is an epic"
  No --plan (the epic pull carries the parent along while its children
  run; when they all land it returns to ready-for-architect and an
  Architect recomposes it — see the last section). You write no code;
  end when the children stand.

## Closing Artifact

The plan is the ENTIRE interface to the Implementer — self-contained for
a zero-context executor; nothing you learned survives except what the
plan and the ticket carry. Commit the plan on the ticket branch and PUSH
it (cattle reclaim depends on origin-visible artifacts), then close your
scope in one transition:

{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-implementer "<brief context and intent>" --branch <branch> --plan <repo-path>@<full-commit-sha>

The `plan:` pin is machine-read — "plan attached" downstream means the
meta field, never note prose — and names the immutable revision the
review loop audits against (your Implementer's living-plan updates on
the branch are divergence evidence, not the contract). `--branch` is not
optional beside a real pin: a cattle clone fetches the plan's sha from
the recorded ref and has nowhere else to look, so the transition refuses
a pin with no branch (name the default branch if the plan landed there). This transition
ends your scope and releases your binding: do not wait, poll, or touch
downstream work.

## If Resumed With Answers

The answers live on the ticket — treat them as ticket content. Re-state
your gate verdict against them in ONE paragraph as a ticket comment
("[gate] re-pass — <one line>", or a fresh park if they reshape the
scope), then continue the design from where it stands. If a returned
ticket arrives with an Implementer's blockage note (the return edge),
treat the note as new ticket content: re-enter through the gate, repair
or re-cut the plan, and hand off again — the board's convergence rule
sends a second disagreement on the same edge to the human by itself.

## Authority

Yours: your OWN ticket's open states via board-transition.sh (never raw
gh for status labels); registering decomposition children (--parent
{{ISSUE_NUMBER}}) and follow-up tickets (--spawned-by {{ISSUE_NUMBER}})
directly. NEVER: implementation code, plan execution, terminal states
(the ONE exception is a recomposition verdict on your own epic, below),
other tickets' states, reviewing the Implementer's output. Your dispatch
ignores engine:* labels by design (plan authorship is never
label-routed) — a route question is not yours to answer.

**Parent-contract contradiction ([parent-impact]).** Your ticket can itself
be a CHILD: `parent-pin: #<parent> @ <hash>` in its `board:meta` names the
parent contract this design inherited. Designing freely INSIDE that
contract is the job; concluding that a parent-owned END is wrong — its
purpose, its acceptance, a cross-child contract, an edge, the division that
produced your ticket — is not yours to write into the parent. Post ONE
typed event on YOUR OWN ticket:
{{BOARD_SCRIPTS}}/board-comment.sh {{ISSUE_NUMBER}} --kind parent-impact --text "#<parent> <affected clauses>: <the evidence, and the parent change you propose>"
One verb, both bindings — gh renders the `[parent-impact] #<parent> …` marker
the sweep IMPACT scan reads, the API board records the typed event its
reconciler joins on, and a hand-written marker is invisible to the second.
The board returns the parent for reconciliation, and the Architect who claims
it reads your proposal (**Recomposition claims** below is that reader's side).
Fire-and-continue: never edit or transition the parent, never wait for the
outcome — finish your own design under the contract you have.

**Environmental friction (env-issue).** Non-blocking environmental
friction you routed around (missing tool in the image, flaky registry,
broken fixture) MAY be filed as its own ticket — search the board first,
then
{{BOARD_SCRIPTS}}/board-register.sh "<title>" env-issue <P0..P3> --spawned-by {{ISSUE_NUMBER}} --note "<intervention requested>" --body-file <full report>
State the friction, what you attempted, why your permissions cannot
resolve it, the intervention requested, and a check that proves
resolution. Default birth is needs-human; pass an explicit --state only
when you can name a concrete repair path some authorized agent can
execute. Filing is fire-and-continue:
never park, transition, or otherwise interrupt your own ticket to report
non-blocking friction — a genuinely blocking failure stays what it is
today, a park on your own ticket. This is opt-in authority, not a duty;
subagents never write the board.

## Recomposition claims

A dispatched ticket that is an EPIC is a recomposition (or
reconciliation) claim, not a design claim. Your deliverable is a VERDICT
against the epic's own acceptance — the whole-unit behavior, not the sum
of child acceptances — and it starts from the children's contract
lineage.

1. **Lineage check first:** for every child, compare its `parent-pin:`
   meta — `#<parent> @ <hash>`, the id of the parent CONTRACT that child
   received (sha256/12 over the parent's issue body with its `board:meta`
   bookkeeping stripped, so the board's own writes never read as a
   contract change) — against your contract today:
   gh issue view {{ISSUE_NUMBER}} -R {{REPO}} --json body | PYTHONPATH={{BOARD_SCRIPTS}} python3 -c "import json,sys,_board as B; print(B.contract_hash(json.load(sys.stdin)['body']))"
   This hash comparison is GH-ONLY: it reads the parent's body, and the API
   board exposes no ticket-body route at all (arkho#7). Under an API board the
   pin is a CURSOR, not a hash — `#<parent> @ event <n>`, handed to each child
   by its own claim — so the equivalent check is what each child carried
   forward into its `parent-impact` events, and a child that recorded none
   leaves that leg unverifiable. Say so in the verdict rather than assuming
   lineage held; do not synthesize a body read.
   Equal hashes mean the child executed the contract you are holding and
   there is nothing to reconcile from the pin. Otherwise read what
   changed; every material change is incorporated, explicitly
   irrelevant (say why), or becomes a corrective child. Read ALL
   `[parent-impact]` proposals on every child since its pin —
   marked consumed or not — and give each the same disposition; the
   sweep's `[board-epic] reconcile:` marker is a dispatch dedupe, not
   proof anyone acted. Before you release the claim (ANY exit — handoff,
   park, verdict), mark every proposal you just dispositioned. The mark is
   the binding's own, and the two are NOT interchangeable — each
   reconciler reads only its own. Under a gh board it is one comment on the
   epic per proposal, in exactly the sweep's format,
   `[board-epic] reconcile: #<child>@<comment-id>`; under an API board it is
   the typed consumption event that reconciler anti-joins on,
   {{BOARD_SCRIPTS}}/board-comment.sh {{ISSUE_NUMBER}} --kind parent-impact-consumed --json '{"proposal_event_id": <the proposal event id>}'
   Both mean the same thing: this proposal has been read. The sweep leaves
   proposals unmarked while an Architect holds the claim — nobody had
   read them yet — so an unmarked one re-triggers a whole reconciliation
   cycle the moment you exit, for work you already did.
2. **Reconciliation-due claims** (children still active): reconcile the
   parent's living spec, flag affected in-flight children on their
   tickets, then RELEASE the epic with
   {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} needs-info "reconciled: <one-line summary> — waiting on children"
   — the named release exit: legal from in-design, frees your architect
   slot, and the sweep's RECOVER pass never force-parks a parked ticket.
   The next child to go ACTIVE pulls the epic back in-flight — that
   activity is the very information this park is waiting on. (Only
   needs-info is pulled that way; an epic parked needs-human holds a
   bound session and is never pulled.)
   You do NOT close it, and you never end your turn with the epic still
   in in-design.
3. **Recomposition-due claims** (all children terminal): verify the
   parent's acceptance. Non-code parent: record why no aggregate code
   review applies, then close with your verdict —
   {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} done "<evidence>"
   (or wontfix). This is the scoped terminal-authority exception: epics
   only, recomposition claims only; you never close a leaf.
   A gap you turned into a CORRECTIVE CHILD instead — from this verify or
   from the lineage check — has no verdict to write yet: take the same
   release exit item 2 names,
   {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} needs-info "corrective child #<n> registered — waiting on children"
   The child going active pulls the epic back for the next cycle;
   `in-design` is never pulled, so an epic left there waits on a child
   nobody will hand it, and the sweep force-parks your finished session
   tick after tick instead.
4. **Code-bearing integration parent** (two-plus children touched one
   executable surface, cross-child invariants, multi-repo composition,
   or the composite spec marks review required): assemble the closure package
   as a comment on the epic — parent acceptance, child closing
   artifacts, exact base/head ranges, cross-child contracts, your
   recomposition evidence. Post that package as a
   NEW comment each recomposition cycle; NEVER edit a previous cycle's
   closure-package comment in place. The scale-review dispatcher tells a
   superseded reviewer from a current one by exact equality on the
   package URL, and an edited-in-place comment keeps its old URL — the
   sweep reads the epic as already reviewed and strands it in in-review
   permanently. Then
   {{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} in-review "<summary>" --pr <package URL> --branch <integration ref>
   Add `--branch` when the composition HAS an integration ref — that is
   the branch the reviewer checks out and reviews against the default
   branch; omit it when the children landed on the default branch
   directly, and the reviewer works the package's per-child ranges
   instead. The recomposition return clears `branch:` with `pr:`, so
   whatever you supply here is this cycle's, and silence means silence.
   The scale reviewer's clean verdict closes the epic; any defect
   becomes a corrective child and the epic waits again.
5. A change to the parent's PURPOSE, a material reduction of acceptance,
   or a product/taste call is the human's — park needs-human with the
   proposal and your recommendation.
