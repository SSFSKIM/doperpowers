---
name: brainstorming
description: "Verified guidance on directing creative work with your human partner — creating features, building components, adding functionality, changing behavior — for when what to build is still open and no design exists yet."
---

# Brainstorming Ideas Into Designs

Turn an idea into a design through dialogue with your human partner: read the project, explore what the idea should be, grill it in batched rounds until nothing is silently assumed, then present the design at a depth proportionate to the work.

## Scope, and where a design goes

Read the project state first (files, docs, recent commits) and size the work from it. This skill defines and matures one goal at a time, whatever its size, and a design leaves it one of three ways:

- **Built here** — once it is well scoped, one agent builds it in this session (a bugfix with its test; a `--json` mode across four commands with one serializer; a skill rewrite). There is no spec: a decision worth keeping is written into the spec that governs the area, when one exists, in the form that spec keeps, and the branch gets its doperpowers:review-code rung at the end.
- **doperpowers:execspec** — reliable execution needs a document: several milestones, an executor or a later sitting that is not you now, decisions and contracts other work will build on. Execspec writes the living spec from the design, reviews it, and executes it.
- **doperpowers:decomposing** — the goal is too big for one agent to reliably own as one unit (that skill's gate). When it leaves depends on whether its pieces share a design surface. Pieces that don't interact — no shared data, contracts, or decisions that need the whole in view (e.g. "a platform with chat, file storage, billing, and analytics" as four freestanding products) — are a bundle, not a whole: it goes to decomposing before any design, since joint maturation would generate nothing, and each child returns through this skill later. Pieces that do interact are the reason to design before dividing: the interaction surface — shared models, contract shapes, decisions that come out differently with everything in view — is generated in this session or never. Grill and present the whole; execspec writes its spec, and decomposing derives the cut from it.

Choosing the route comes with the authorization for the work: say which you took, and why, in a line.

A goal that arrives as a child of a composite spec carries its section — purpose, acceptance, edges, contracts, graded design inheritance — as pre-landed design, and the composite's approval already covers it. Grill only the residue, against the code, and present only the residue. It gets no spec of its own: the composite is shared by parallel siblings and has one writer, so the residue is recorded in the child's own document (for a plan child, the standalone execution document doperpowers:execspec writes) and that writer rewrites the child's section from it. The section's grain hint names the child's route. A residue design that trips decomposing's split signals means the child is itself a composite, and goes there.

## Exploring the purpose

The grill works the decisions the initiative already poses; this is its sibling, run first and kept open beside it: exploring what the initiative should even be. How good the result can be is set by how far its purpose has been developed, and clarity is not the measure — a purpose can look clear and be narrow, its framing already closing off better versions nobody has named. What the design reaches for is the best possible manifestation of the initiative's intent and of the higher purpose it serves, explored downward into a system of goals and conditions rich enough that one result is right and the generic ones are wrong. Four questions carry the exploration, asked in the first round before any mechanism and kept open as the grill's answers reveal more:

- **What higher purpose it serves** — the project or way of working the initiative is in service of, discovered with its nuances first, since everything derived below inherits only the nuance it has.
- **What precisely it is for** — the intent behind the framing, discovered and sharpened rather than taken as given; the exploration may change what it should be.
- **What its best possible manifestation would look like** — the picture of it working at its best, and what you and your partner should want given that purpose, not only what was first said.
- **What it must not be** — the constraints and taste that make the result specific instead of generic, derived from the higher purpose and drawn from real-world context only your partner holds.

On an ambitious or open initiative most of this is latent — held by your human partner but unspoken, not yet clear even to them, or not yet thought of by anyone — and the more degrees of freedom the initiative has, the larger this space and the easier it is to declare it explored while most of it is untouched. It is carved between you, finished on neither side alone: contemplate from the higher purpose yourself and propose what you find, bring in research or another perspective, and above all interview your partner relentlessly for what only they hold. Much of that is taste they cannot state in the abstract, so put concrete things in front of them — a scene of it in use, alternatives that differ in what they treat as central — read the criterion out of their reaction, and propose again; options exist to reveal what matters, not to confine the answer to them. You drive the exploration; their judgment is for the calls that turn on taste and real-world context, and technical sophistication is yours to supply.

## The grill

Interview relentlessly about every aspect of the initiative until you and your human partner share one understanding. Map the initiative as a design tree — every decision branches into the decisions that hang off it — and work the tree in batched rounds. The frontier is every decision whose prerequisites are settled: the questions you can ask now without guessing at answers you haven't heard. Ask the whole frontier in one round; each round's answers reshape the tree and push the frontier outward, and a question that depends on another still open this round waits for the next. An empty frontier ends a round, not the grill.

Deliver each round by fit: clear multiple-choice questions ride AskUserQuestion, several at once; open but bounded questions go as prose inline. In a non-interactive context the whole round is one numbered message.

Finding facts is your job, never your human partner's, and the rule reaches outward at four radii: a question the codebase can answer is answered by reading it, and what your partner says about how the code works is checked against it; one only the world can answer (prior art, the literature, an external service's real behavior) is answered by research, not speculation; one only an experiment can answer becomes a spike — run inline when small, registered as its own goal when not; and every idea is situated against the project's standing purpose. A running exploration is an unsettled prerequisite: only its downstream questions wait for it; ask the rest of the frontier now.

Grill what is fuzzy or important; don't grind an already-clear request to death. Depth has a stopping point, not a size limit. The grill is done when the purpose and the system of goals and conditions under it are mature enough to justify the choices being made now, every branch has been visited with nothing silently assumed, and the remaining unknowns are empirical — answerable only by a spike, by implementation contact, or by watching the thing run — and no longer architectural. Answer everything the assembled picture can answer, and name the empirical residue in the design as delegated unknowns, each with the move that will resolve it — a spike, research, a prototype looked at together — rather than leaving it implicit.

Product, taste, and substantive design decisions are your human partner's. A fork that turns on one is a grill question, not presentation material: put it to them when it surfaces, with your recommendation, so that by presentation time only the forks that first emerge while composing the full design are still open. A fork among technical or mechanical means inside a scope they authorized is yours: choose the best fit and record it as a silent decision.

Your human partner's framing is a starting point, not the boundary of the design space — whoever initiated the idea may not see it as fully as you can. You carry expert-level knowledge of nearly every domain it touches; spend it on the idea's substance, not only its clarification: angles the framing didn't open, what your partner didn't seem to consider, questions whose answers give the idea real insight, reasoned opinions of your own that mature it. And judge, for every idea, whether it deserves to converge as conceived. Make the outward move your human partner cannot: hold the idea against the project's standing purpose, compare it with the other levers that purpose suggests — including levers absent from the codebase, where an absent obvious lever is often the prerequisite frame rather than background to assume — and with what the world already knows about this problem class. An idea can be perfectly coherent and still be dominated by an alternative nobody named. Voice what you find once, sharply, before convergence, grounded in this project's purpose, this codebase, or named sources.

## Presenting the design

Your human partner wants the design presented before it is built, whatever the size of the work: composing the whole design surfaces forks that no single question raised, and reading it costs them one message. For a small piece of work three sentences may be the whole of it. A design that carries a decision of theirs they have not made waits for their approval, one approval covering the whole pass; a design whose remaining choices are all technical or mechanical consequences of a scope they authorized is stated, and the work continues.

Present the whole design in one pass. The design itself — the description of the thing you intend to build — is the body; the structure around it triages your human partner's attention, so they know which parts need their judgment and which they can skim:

1. **Open forks** (rare) — decisions of your partner's that first emerged while composing the design and have genuinely sound alternatives, each with its candidates, trade-offs, and your recommendation. Your human partner decides.
2. **The design** — architecture, components, data flow, error handling, and testing, in sections scaled to their complexity. Describe the thing, not just your choices about it — what each part does, how the parts fit together, the reasoning behind the significant calls — and mark the sections that turn on your partner's taste or domain knowledge as ones to review carefully.
3. **Silent decisions** — the trivial calls you made without asking, a skimmable line each.

Revise conversationally. Split into sequential rounds only when a real dependency forces it: an open fork that reshapes everything downstream is its own frontier — present it, get the decision, then present what hangs off it.

When the design is novel or the cost of being wrong is high, the `doperpowers:critique` agent debates it with you until the disagreement converges; a disagreement that survives honest debate goes to your human partner as an open question.
