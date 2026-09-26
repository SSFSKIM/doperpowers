---
name: execspec
description: Use after doperpowers:brainstorming closed a design and your human partner approved it, when the initiative is complex and sizable enough that reliable execution needs a spec — to write the living spec, review it, and execute it; also to revise a spec that already exists. A new spec is written only after brainstorming ran, never straight from a request; revising an existing spec needs no brainstorm.
---

# Execspec — the spec and its execution

You arrive with an approved design: doperpowers:brainstorming explored the purpose, grilled the initiative, and presented the design your human partner approved. This skill turns it into the one document the initiative has — the living spec — reviews it, and executes it. The document's shape, and everything it binds, is [references/living-spec.md](references/living-spec.md): the purpose-first opening, Progress, acceptance as observable behavior, the execution section (the constraints that bind every milestone, the Plan of Work as milestones, Concrete Steps, Interfaces), and the record.

## The path

1. Write the spec
2. Self-review
3. Independent review
4. Execute

A goal that arrives as a child of a composite spec carries its section as its design, and the composite's approval covers it: you write only its standalone execution document (living-spec.md, "A child of a composite spec"), record residue decisions in the parent's Decision Log under the child's id, and skip step 3 — its route's own review covers the residue.

## 1. Write the spec

Write the design to `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md` in the shape living-spec.md gives, and commit it. Reasoning lives in the design: where a section makes a decision it says why and names the strongest alternative and why it lost; the grill and the presentation already generated them, so capturing them is free. Capture everything the session produced: the spec is the only durable memory this work has — a stale written decision is detectably wrong later and flows back, an uncaptured insight is silently gone.

Name the verification and record it as the Decision Log's one entry at authoring, so whoever executes, reviews, or recovers the work reads the same council. It follows from the stakes, not the size: the default is one independent spec review (step 3); an execution section of more than one milestone also gets the `doperpowers:adversarial-reviewer` agent's buildability review; and name the rung doperpowers:review-code will run on the branch at the end. A critique debate on the design belongs to brainstorming's presentation and has already happened when the design was novel or the cost of being wrong high.

The execution section is written after the design is approved, never before: in an interactive session, now, with the rest of the spec; on the board, after the approval park when the ticket carries one (the Architect protocol). Writing it is the first hostile read of the design.

## 2. Self-review

Reread the spec with fresh eyes: placeholders, sections that contradict each other, requirements that read two ways, whether the scope still fits the route named, the record present. Then the execution section against the design: every acceptance behavior has a milestone whose proof covers it; every interface a milestone consumes is one an earlier milestone produces, under the same name; nothing is left to "as in M2" or "add validation"; and where writing the milestones proved a design statement wrong — an argument that is actually an output, an infeasible constraint, a misnamed path — fix the design, with a dated line in the Decision Log. The check easiest to miss is traceability: every load-bearing declaration in the design prose — anything that says the artifact must carry X — needs a concrete section, slot, or instruction that carries it, and a declaration without a counterpart is a defect. Fix what you find inline and move on.

## 3. Independent review

Report the committed spec path, then dispatch an independent spec review, routed by the same center-of-gravity rule as peer review: a design-heavy or still-open spec goes to a general-purpose subagent (model=fable) — 1–2 sentences of context and the spec path are enough; a technical-heavy spec goes to the `doperpowers:adversarial-reviewer` agent (gpt-6-astra through the gateway) with the spec path and its purpose in the brief. When the execution section has more than one milestone, dispatch the `doperpowers:adversarial-reviewer` agent on it in the same round: *Review the execution section of the spec at [SPEC PATH] against its design. Verify the milestones are complete, aligned with the design, well-decomposed, and buildable by an engineer with zero context beyond this document and the code.* Evaluate the findings rather than accepting them wholesale, make the changes that survive, re-run the self-review, and stop when a round yields nothing worth changing. What returns to your human partner is exceptions — a design-level fork the design doesn't cover, a finding that conflicts with the design itself, a blocker you can't resolve; everything resolvable within the design is fixed where it stands, with the Decision Log's dated line.

In this session the review may run while you execute — you are the executor and can absorb its findings as they land; a spec handed to a zero-context executor (the board's build edge) is reviewed before it is handed over.

## 4. Execute

Execute in an isolated workspace ([../subagent-driven-execution/isolated-workspace.md](../subagent-driven-execution/isolated-workspace.md)). One milestone: work it here — in order, without stopping for next steps, Progress and the record current at every stopping point, frequent commits; at the end, the whole-branch review through doperpowers:review-code at the rung the verification call named, the retrospective, and integration per that reference's finish rules. Several milestones: dispatch one `doperpowers:plan-executor` subagent briefed with the spec path, the branch, and a report file path under the spec's directory. It invokes doperpowers:subagent-driven-execution and runs that loop — fresh executor per milestone, reviews at dependency frontiers, fixes resuming the executor — in its own context, so yours stays the design session. It returns on completion with the PR URL, or on a `BLOCKED` that names the spec text at issue: repair the spec or answer, or escalate to your human partner when only they can, then continue the same subagent with SendMessage. It also messages you at the checkpoints it judges meaningful, without stopping; read each against the spec and reply through SendMessage with a confirmation or a correction. The residue in its return — work left behind that deserves its own ticket — is registered as board tickets through doperpowers:issue-tracker; it is bounded by construction, so a peer seat builds each one direct from the ticket body.

A coupled goal that fails doperpowers:decomposing's gate goes to that skill after step 3 instead of executing: it extends this same spec with the roadmap sections, and each child returns through brainstorming and this skill.

## Revising a spec

A spec changes whenever course changes — during execution, from a review finding, in a later sitting. Revise the design sections so the document stays consistent as a whole, add the dated Decision Log entry with the alternative rejected then, route an observation into Surprises & Discoveries, and keep Progress current (living-spec.md, "Where reasoning lives"). A change to a product, taste, or substantive design decision your human partner approved goes back to them first.
