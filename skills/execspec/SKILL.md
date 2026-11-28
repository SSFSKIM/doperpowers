---
name: execspec
description: Verified guidance on the living spec — writing it from a design, reviewing it, executing it, revising it — for work that needs a document an executor, a later sitting, or other work will read.
---

# Execspec — the spec and its execution

The living spec is the one document an initiative has: the design with its reasoning, the acceptance, the execution, and where the work stands. This skill writes it from a design, reviews it, and executes it. The design it records carries your human partner's approval wherever it carries their decisions; doperpowers:brainstorming is where a design is usually explored, grilled, and presented. The document's shape — its sections, what a milestone carries, how it is kept current — is [references/living-spec.md](references/living-spec.md).

A goal that arrives as a child of a composite spec carries its section as its design, and the composite's approval covers it: you write only its standalone execution document (living-spec.md, "A child of a composite spec"); what your residue decisions change in the composite reaches its writer through that document's last section.

## Writing the spec

Write the design to `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md` in the shape living-spec.md gives, and commit it as approved, before any review alters it: that commit is the baseline every later change is read against. Capture everything the session produced, each thing in the section it bears on: the spec is the only durable memory this work has — a stale written decision is detectably wrong later and flows back, an uncaptured insight is silently gone.

The execution section is written now, with the rest of the spec, from the design as approved: writing the milestones is the first hostile read of the design, and a design statement they prove wrong — an argument that is actually an output, an infeasible constraint, a misnamed path — is fixed in the design.

Name the verification in the paragraph that opens the execution section — the independent reviews the spec gets (below) and the doperpowers:review-code rung the branch gets at the end — so whoever executes, reviews, or recovers the work reads the same council. It follows from the stakes, not the size. A critique debate on the design belongs to brainstorming's presentation and has already happened when the design was novel or the cost of being wrong high.

## Reading it back

Before anyone else reads the spec, read its execution section against its design: every acceptance behavior has a milestone whose proof covers it, and every interface a milestone consumes is one an earlier milestone produces, under the same name. The check easiest to miss is traceability: every load-bearing declaration in the design prose — anything that says the artifact must carry X — needs a concrete section, slot, or instruction that carries it, and a declaration without a counterpart is a defect.

## Independent review

Your human partner's default is one independent review of every spec, and a buildability review as well when its execution section has more than one milestone: an author's reread rarely finds the contradiction between the spec and the files it governs, the claim nothing carries, or the consumer the plan missed.

Report the committed spec path, then dispatch the spec review by the spec's center of gravity: a design-heavy or still-open spec goes to a general-purpose subagent on the frontier model (`fable`), with a sentence or two of context and the spec path; a technical-heavy spec goes to the `doperpowers:adversarial-reviewer` agent, with the spec path and its purpose. The buildability review is the adversarial-reviewer's too, dispatched in the same round: *Review the execution section of the spec at [SPEC PATH] against its design. Verify the milestones are complete, aligned with the design, well-decomposed, and buildable by an engineer with zero context beyond this document and the code.*

Weigh the findings, make the changes that survive, and stop when a round yields nothing worth changing, each round's changes in a commit that says what moved and why. What returns to your human partner is exceptions — a design-level fork the design doesn't cover, a finding that conflicts with the design itself, a blocker you can't resolve; everything resolvable within the design is fixed where it stands.

In this session the review may run while you execute — you are the executor and can absorb its findings as they land; a spec handed to a zero-context executor is reviewed before it is handed over.

## Executing

Execute in an isolated workspace ([../subagent-driven-execution/isolated-workspace.md](../subagent-driven-execution/isolated-workspace.md)).

A spec with one milestone is worked here: in order, without stopping for next steps, the spec current at every stopping point, frequent commits. At the end come the whole-branch review through doperpowers:review-code at the rung the verification named, its brief naming the spec and its approved commit as doperpowers:subagent-driven-execution's final review does, then the retrospective, and integration per the workspace reference's finish rules.

A spec with several milestones goes to one `doperpowers:plan-executor` subagent, briefed with the spec path, the branch, and a report file path under the spec's directory. It runs doperpowers:subagent-driven-execution in its own context, so yours stays the design session. Dispatch it at its pin, with no model or effort of your own, and leave its workers' pins to it, whatever model wrote the spec: the pins in the agent definitions are your human partner's ruling — the frontier's work is the design and the spec, running the plan and building its milestones is close-frontier work — and one changes only when they say so.

The plan-executor returns on completion with the PR URL, or on a `BLOCKED` that names the spec text at issue: repair the spec or answer, or escalate to your human partner when only they can, then continue the same subagent with SendMessage. While it runs it also messages you, without stopping, when it holds something you need — a decision to check against the design, an input it will need, a surprise or fact other work depends on — and with a report on where the plan stands when two or three milestones have landed in silence. Read each against the spec and reply through SendMessage when you have a correction, an answer, or news of your own: it reads no reply as proceed.

When it returns, read what changed in the spec since approval (`git diff --word-diff <approved commit> -- <spec>`) against the design before the merge: a reduced acceptance item or a changed decision is yours to accept or to take to your human partner. The residue in its return — work left behind that deserves its own ticket — is registered as board tickets through doperpowers:issue-tracker; it is bounded by construction, so a peer seat builds each one direct from the ticket body.

A coupled goal that fails doperpowers:decomposing's gate goes to that skill once its spec is reviewed, instead of executing: decomposing extends this same spec with the roadmap sections, and each child returns through brainstorming and this skill.

## Revising a spec

A spec changes whenever course changes — during execution, from a review finding, in a later sitting — as living-spec.md's "Keeping the spec current" says: every section the change touches is rewritten so the document reads as if it had always said this, Progress shows the work the change adds or reopens, and the change is committed apart from other work, its message carrying who ruled, in whose words, and what the text said before. A change to a product, taste, or substantive design decision your human partner approved goes back to them first.
