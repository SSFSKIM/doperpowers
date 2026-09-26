---
name: brainstorming
description: "Use when starting any creative work — creating features, building components, adding functionality, or modifying behavior — before a design exists."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs through natural collaborative dialogue: understand the project, explore what the idea should be and grill it in batched rounds until nothing is silently assumed, then present the design at a depth proportionate to the work.

One gate governs the whole skill: implementation waits when it would commit an unapproved product, taste, or substantive design decision — present those decisions in the design and get your human partner's approval first. When the work is already authorized and well-scoped, and the remaining choices are technical or mechanical consequences of that scope, state the brief design and proceed without another approval. Simple projects still get proportionate design thought; three sentences may be enough to expose an assumption before work.

## The path

1. Explore project context — files, docs, recent commits — and assess scope
2. Explore the purpose
3. Grill
4. Present the design
5. Build here, or hand to doperpowers:execspec

Every initiative runs steps 1–4: the design is presented whatever the size of the work. Step 5 is the route. An initiative complex and sizable enough that reliable execution needs a spec goes to doperpowers:execspec, which writes the living spec, reviews it, and executes it — one milestone in that session, several through a `doperpowers:plan-executor` subagent running doperpowers:subagent-driven-execution. Otherwise discuss the design with your human partner and, once the task is well scoped, build it here (doperpowers:test-driven-development still applies to testable logic). A goal too big for one agent to reliably own as one unit — doperpowers:decomposing's gate — leaves for that skill instead: at step 1 when its pieces are an uncoupled bundle, after the design when they are coupled (execspec writes the spec decomposing extends). Scope below says which.

## Scope and context

Explore the project state first, then assess scope and coupling before detailed questions. This skill defines and matures one goal at a time, whatever its size; what decides when an oversized goal hands over to doperpowers:decomposing is whether its pieces share a design surface. Pieces that don't interact — no shared data, contracts, or decisions that need the whole in view (e.g. "a platform with chat, file storage, billing, and analytics" as four freestanding products) — are a bundle, not a whole: route to decomposing now, since joint maturation would generate nothing, and each child returns through this skill later. Pieces that do interact are the reason to design before dividing: the interaction surface — shared models, contract shapes, decisions that come out differently with everything in view — is generated in this session or never. Run the full grill and design pass on the whole, and hand the matured design to decomposing, which derives the cut from it. State the route; ask for confirmation only when it carries a decision under the gate.

A goal that arrives as a child of a composite spec carries its section — purpose, acceptance, edges, contracts, graded design inheritance — as pre-landed design, and the composite's approval already covers it. Grill only the residue, against the code, and present only the residue; expand the child's section in place instead of writing a spec of its own, recording residue decisions in the parent's Decision Log under the child's id; doperpowers:execspec writes its standalone execution document. Its section's grain hint names its route — state it and apply the gate as for any other route. A residue design that trips decomposing's split signals means the child is itself a composite: route it there.

## Exploring the purpose

The grill works the decisions the initiative already poses; this is its sibling, run first and kept open beside it: exploring what the initiative should even be. How good the result can be is set by how far its purpose has been developed, and clarity is not the measure — a purpose can look clear and be narrow, its framing already closing off better versions nobody has named. What the design reaches for is the best possible manifestation of the initiative's intent and of the higher purpose it serves, explored downward into a system of goals and conditions rich enough that one result is right and the generic ones are wrong. Four questions carry the exploration, asked in the first round before any mechanism and kept open as the grill's answers reveal more:

- **What higher purpose it serves** — the project or way of working the initiative is in service of, discovered with its nuances first, since everything derived below inherits only the nuance it has.
- **What precisely it is for** — the intent behind the framing, discovered and sharpened rather than taken as given; the exploration may change what it should be.
- **What its best possible manifestation would look like** — the picture of it working at its best, and what you and your partner should want given that purpose, not only what was first said.
- **What it must not be** — the constraints and taste that make the result specific instead of generic, derived from the higher purpose and drawn from real-world context only your partner holds.

On an ambitious or open initiative most of this is latent — held by your human partner but unspoken, not yet clear even to them, or not yet thought of by anyone — and the more degrees of freedom the initiative has, the larger this space and the easier it is to declare it explored while most of it is untouched. It is carved between you, finished on neither side alone: contemplate from the higher purpose yourself and propose what you find, bring in research or another perspective, and above all interview your partner relentlessly for what only they hold. Much of that is taste they cannot state in the abstract, so put concrete things in front of them — a scene of it in use, alternatives that differ in what they treat as central — read the criterion out of their reaction, and propose again; options exist to reveal what matters, not to confine the answer to them. You drive the exploration; their judgment is for the calls that turn on taste and real-world context, and technical sophistication is yours to supply.

## The grill

Interview relentlessly about every aspect of the initiative until you and your human partner share one understanding. Map the initiative as a design tree — every decision branches into the decisions that hang off it — and work the tree in batched rounds. The frontier is every decision whose prerequisites are settled: the questions you can ask now without guessing at answers you haven't heard. Ask the whole frontier in one round; each round's answers reshape the tree and push the frontier outward, and a question that depends on another still open this round waits for the next. An empty frontier ends a round, not the grill.

Deliver each round by fit: clear multiple-choice questions ride AskUserQuestion, several at once; open but bounded questions go as prose inline. In a non-interactive context (a board ticket, a relay comment) the whole round is one numbered message.

Finding facts is your job, never your human partner's, and the rule reaches outward at four radii: a question the codebase can answer is answered by reading it; one only the world can answer (prior art, the literature, an external service's real behavior) is answered by research, not speculation; one only an experiment can answer becomes a spike — run inline when small, registered as its own goal when not; and every idea is situated against the project's standing purpose. A running exploration is an unsettled prerequisite: only its downstream questions wait for it; ask the rest of the frontier now.

Three moves to use throughout:

- **Sharpen fuzzy terms** — propose a precise canonical term: "You're saying 'account' — do you mean the Customer or the User? Those are different things."
- **Stress-test with concrete scenarios** — invent scenarios that probe edge cases and force precision about the boundaries between concepts.
- **Cross-reference with code** — when your human partner states how something works, check whether the code agrees; surface contradictions.

Grill what is fuzzy or important; don't grind an already-clear request to death. Depth has a stopping point, not a size limit. The grill is done when the purpose and the system of goals and conditions under it are mature enough to justify the choices being made now, every branch has been visited with nothing silently assumed, and the remaining unknowns are empirical — answerable only by a spike, by implementation contact, or by watching the thing run — and no longer architectural. Answer everything the assembled picture can answer, and name the empirical residue in the design as delegated unknowns, each with the move that will resolve it — a spike, research, a prototype looked at together — rather than leaving it implicit.

A fork that turns on a decision under the gate is a grill question, not presentation material: put it to your human partner when it surfaces, with your recommendation. A fork among technical or mechanical means within authorized scope is yours — choose the best fit and record it as a silent decision. By presentation time the human-owned forks the grill could see are settled; only those that first emerge while composing the full design survive to the presentation.

Your human partner's framing is a starting point, not the boundary of the design space — whoever initiated the idea may not see it as fully as you can. You carry expert-level knowledge of nearly every domain it touches; spend it on the idea's substance, not only its clarification: angles the framing didn't open, what your partner didn't seem to consider, questions whose answers give the idea real insight, reasoned opinions of your own that mature it. And judge, for every idea, whether it deserves to converge as conceived. Make the outward move your human partner cannot: hold the idea against the project's standing purpose, compare it with the other levers that purpose suggests — including levers absent from the codebase, where an absent obvious lever is often the prerequisite frame rather than background to assume — and with what the world already knows about this problem class. An idea can be perfectly coherent and still be dominated by an alternative nobody named. Voice what you find once, sharply, before convergence, grounded in this project's purpose, this codebase, or named sources.

## Routing the work

Read the shape of the work off the grill and name the route that fits, with a one-line reason:

- **Build here** — the grill closed the design and, once the task is well scoped, one agent builds it in this session (a bugfix with its test; a `--json` mode across four commands with one serializer; a skill rewrite): a brief design, the gate when it applies, then implement — no spec. A decision worth keeping goes into the Decision Log of the spec that governs the area, when one exists. The verification call is the doperpowers:review-code rung the branch gets at the end.
- **doperpowers:execspec** — the initiative is complex and sizable enough that reliable execution needs a spec: several milestones, an executor or a later sitting that is not you now, decisions and contracts other work will build on. Hand over once the design is approved; execspec names the document's and the branch's verification and records it in the spec.

When the route follows from already-authorized scope, state it and continue: *"Design closed, well scoped — building it here."* When it would commit a decision under the gate, recommend a specific route and ask a focused confirmation rather than an open "which route do you want?". Start with building here; the choice ratchets one way, so a task that sprouts a design question, a hand-off, or hidden scope that turns a bounded change architectural upgrades to execspec and returns here for the design pass it now deserves. Authorization for the work includes choosing its route: "just handle it" is sufficient when no reserved decision remains.

## Presenting the design

Present the whole design in one pass. The design itself — the description of the thing you intend to build — is the body; the structure around it triages your human partner's attention, so they know which parts need their judgment and which they can skim:

1. **Open forks** (rare) — decisions under the gate that first emerged while composing the design and have genuinely sound alternatives, each with its candidates, trade-offs, and your recommendation. Your human partner decides.
2. **The design** — architecture, components, data flow, error handling, and testing, in sections scaled to their complexity: a few sentences if straightforward, up to 200–300 words if nuanced. Describe the thing, not just your choices about it — what each part does, how the parts fit together, the reasoning behind the significant calls — and mark the sections that turn on your partner's taste or domain knowledge as ones to review carefully.
3. **Silent decisions** — the trivial calls you made without asking, a skimmable line each.

When the gate applies, one approval covers the whole pass; revise conversationally. Split into sequential rounds only when a real dependency forces it: an open fork that reshapes everything downstream is its own frontier — present it, get the decision, then present what hangs off it.

Prefer small units with one clear purpose and a well-defined interface — you reason better about code you can hold in context at once, and edits to focused files are more reliable; a file that has grown large is usually doing too much. Follow the codebase's existing patterns, and where existing code has problems that affect the work (a file grown too large, unclear boundaries, tangled responsibilities), fold targeted improvements into the design the way a good developer improves the code they work in.

When the design is novel or the cost of being wrong is high, bring in a critic and debate until the discussion converges: adopt what survives, rebut what doesn't, and hand a disagreement that survives honest debate to your human partner as an open question. The critic is the `doperpowers:critique` agent: dispatch it with brief context and paths to the design artifacts, and debate via SendMessage.
