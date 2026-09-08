---
name: brainstorming
description: "Use when starting any creative work — creating features, building components, adding functionality, or modifying behavior — before a design exists."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue: understand the project, grill the idea in batched rounds until nothing is silently assumed, then present the design at a depth proportionate to the work.

One gate governs the whole skill: implementation waits when it would commit an unapproved product, taste, or substantive design decision — present those decisions in the design and get your human partner's approval first. When the work is already authorized and well-scoped, and the remaining choices are technical or mechanical consequences of that scope, state the brief design and proceed without another design or track approval. Simple projects still get proportionate design thought; three sentences may be enough to expose an assumption before work.

## The path

1. Explore project context — files, docs, recent commits — and assess scope
2. Grill
3. Choose and state the track
4. Present the design
5. Write the spec
6. Self-review the spec
7. Independent spec review
8. Hand off to doperpowers:writing-plans

The controlled track runs all eight. The autonomous track leaves after step 3 for doperpowers:execplan; the direct track leaves after step 4 and implements in this session (doperpowers:test-driven-development still applies to testable logic). A goal too big for one agent to reliably own as one unit — doperpowers:decomposing's gate — leaves for that skill instead: at step 1 when its pieces are an uncoupled bundle, at step 8 in place of writing-plans when they are coupled. Scope below says which.

## Scope and context

Explore the project state first, then assess scope and coupling before detailed questions. This skill defines and matures one goal at a time, whatever its size; what decides when an oversized goal hands over to doperpowers:decomposing is whether its pieces share a design surface. Pieces that don't interact — no shared data, contracts, or decisions that need the whole in view (e.g. "a platform with chat, file storage, billing, and analytics" as four freestanding products) — are a bundle, not a whole: route to decomposing now, since joint maturation would generate nothing, and each child returns through this skill later. Pieces that do interact are the reason to design before dividing: the interaction surface — shared models, contract shapes, decisions that come out differently with everything in view — is generated in this session or never. Run the full grill and design pass on the whole, and hand the matured design to decomposing, which derives the cut from it. State the route; ask for confirmation only when it carries a decision under the gate.

A goal that arrives as a child of a composite spec carries its section — purpose, acceptance, edges, contracts, graded design inheritance — as pre-landed design, and the composite's approval already covers it. Grill only the residue, against the code, and present only the residue; expand the child's section in place instead of writing a spec of its own, recording residue decisions in the parent's Decision Log under the child's id. Its section's track hint names its exit — state it and apply the gate as for any other track — and that track's own review covers the residue, so step 7 is skipped. A residue design that trips decomposing's split signals means the child is itself a composite: route it there.

## The grill

Interview relentlessly about every aspect of the initiative until you and your human partner share one understanding. Map the initiative as a design tree — every decision branches into the decisions that hang off it — and work the tree in batched rounds. The frontier is every decision whose prerequisites are settled: the questions you can ask now without guessing at answers you haven't heard. Ask the whole frontier in one round; each round's answers reshape the tree and push the frontier outward, and a question that depends on another still open this round waits for the next. An empty frontier ends a round, not the grill.

The tree grows from the initiative's purpose, and that is the part most often left thin: a tree grown from a vague purpose converges on a generic result while every branch looks visited. What the result can be is set by how clearly its purpose and the criteria for a good one are held — criteria that are formed as much as found, and that move when the work reveals a possibility nobody had in view — so the purpose is the first frontier, asked in the first round before mechanism, and it stays open as the decisions below reveal more of it:

- **What precisely it is for** — the intent behind the framing, and the higher purpose of the project it serves.
- **What its best possible manifestation would look like** — the picture of it working at its best, and what your partner should want given that purpose, not only what they first said.
- **What it must not be** — the constraints and taste, drawn from real-world context outside the codebase, that make the result specific instead of generic.

On an ambitious or open initiative most of this is latent — held by your human partner but unspoken, not yet clear even to them, or derivable from the higher purpose by nobody yet — and the more degrees of freedom the initiative has, the larger this space and the easier it is to declare it explored while most of it is untouched. Define it from three directions: reason from the project's purpose yourself and propose what you find, bring in research or another perspective, and interview your partner for what only they hold. Much of what they hold is taste they cannot state in the abstract, so put concrete things in front of them — a scene of it in use, alternatives that differ in what they treat as central — read the criterion out of their reaction, and propose again; options exist to reveal what matters, not to confine the answer to them. The labor of defining the problem is yours, not theirs. Technical sophistication is yours to supply; their judgment is for the calls that turn on taste and real-world context.

Deliver each round by fit: clear multiple-choice questions ride AskUserQuestion, several at once; open but bounded questions go as prose inline. In a non-interactive context (a board ticket, a relay comment) the whole round is one numbered message.

Finding facts is your job, never your human partner's, and the rule reaches outward at four radii: a question the codebase can answer is answered by reading it; one only the world can answer (prior art, the literature, an external service's real behavior) is answered by research, not speculation; one only an experiment can answer becomes a spike — run inline when small, registered as its own goal when not; and every idea is situated against the project's standing purpose. A running exploration is an unsettled prerequisite: only its downstream questions wait for it; ask the rest of the frontier now.

Three moves to use throughout:

- **Sharpen fuzzy terms** — propose a precise canonical term: "You're saying 'account' — do you mean the Customer or the User? Those are different things."
- **Stress-test with concrete scenarios** — invent scenarios that probe edge cases and force precision about the boundaries between concepts.
- **Cross-reference with code** — when your human partner states how something works, check whether the code agrees; surface contradictions.

Grill what is fuzzy or important; don't grind an already-clear request to death. Depth has a stopping point, not a size limit. The grill is done when the purpose and its criteria are mature enough to justify the choices being made now, every branch has been visited with nothing silently assumed, and the remaining unknowns are empirical — answerable only by a spike, by implementation contact, or by watching the thing run — and no longer architectural. Answer everything the assembled picture can answer, and name the empirical residue in the design as delegated unknowns, each with the move that will resolve it — a spike, research, a prototype looked at together — rather than leaving it implicit.

A fork that turns on a decision under the gate is a grill question, not presentation material: put it to your human partner when it surfaces, with your recommendation. A fork among technical or mechanical means within authorized scope is yours — choose the best fit and record it as a silent decision. By presentation time the human-owned forks the grill could see are settled; only those that first emerge while composing the full design survive to the presentation.

Your human partner's framing is a starting point, not the boundary of the design space — whoever initiated the idea may not see it as fully as you can. You carry expert-level knowledge of nearly every domain it touches; spend it on the idea's substance, not only its clarification: angles the framing didn't open, what your partner didn't seem to consider, questions whose answers give the idea real insight, reasoned opinions of your own that mature it. And judge, for every idea, whether it deserves to converge as conceived. Make the outward move your human partner cannot: hold the idea against the project's standing purpose, compare it with the other levers that purpose suggests — including levers absent from the codebase, where an absent obvious lever is often the prerequisite frame rather than background to assume — and with what the world already knows about this problem class. An idea can be perfectly coherent and still be dominated by an alternative nobody named. Voice what you find once, sharply, before convergence, grounded in this project's purpose, this codebase, or named sources.

## Choosing the track

Read the shape of the work off the grill and name the track that fits, with a one-line reason:

- **Well-scoped and delegable** — the grill exhausted the open questions and the only remaining unknowns are feasibility ("we won't know until we try", which become prototyping milestones), not taste → autonomous: doperpowers:execplan authors one self-contained ExecPlan and executes it with no mid-flight human gates.
- **Large, novel, taste-heavy, or high-stakes** — taste questions keep arising that can't be settled up front, or the work needs human judgment mid-flight → controlled: the rest of this skill, design → spec → doperpowers:writing-plans.
- **Narrow and small** — a focused change an engineer would just do (a config tweak, a small bugfix, one thin feature slice), where a spec or ExecPlan would outweigh the work → direct: a brief design, the gate when it applies, then implement in this session — no spec, no plan.

When the route follows from already-authorized scope, state it and continue: *"This is well-scoped and the open questions are closed, so I'm taking the autonomous track and running it end to end."* When it would commit a decision under the gate, recommend a specific route and ask a focused confirmation rather than an open "which track do you want?". In doubt between two tracks, take the heavier; the choice ratchets one way, so complexity discovered mid-flight — a direct task that sprouts design questions, hidden scope that turns a bounded change architectural — upgrades the track and returns here for the design pass it now deserves. Authorization for the work includes choosing its technical route: "just handle it" is sufficient when no reserved decision remains, and doperpowers:execplan's contract governs once routed there.

## Presenting the design

Present the whole design in one pass. The design itself — the description of the thing you intend to build — is the body; the structure around it triages your human partner's attention, so they know which parts need their judgment and which they can skim:

1. **Open forks** (rare) — decisions under the gate that first emerged while composing the design and have genuinely sound alternatives, each with its candidates, trade-offs, and your recommendation. Your human partner decides.
2. **The design** — architecture, components, data flow, error handling, and testing, in sections scaled to their complexity: a few sentences if straightforward, up to 200–300 words if nuanced. Describe the thing, not just your choices about it — what each part does, how the parts fit together, the reasoning behind the significant calls — and mark the sections that turn on your partner's taste or domain knowledge as ones to review carefully.
3. **Silent decisions** — the trivial calls you made without asking, a skimmable line each.

When the gate applies, one approval covers the whole pass; revise conversationally. Split into sequential rounds only when a real dependency forces it: an open fork that reshapes everything downstream is its own frontier — present it, get the decision, then present what hangs off it.

Prefer small units with one clear purpose and a well-defined interface — you reason better about code you can hold in context at once, and edits to focused files are more reliable; a file that has grown large is usually doing too much. Follow the codebase's existing patterns, and where existing code has problems that affect the work (a file grown too large, unclear boundaries, tangled responsibilities), fold targeted improvements into the design the way a good developer improves the code they work in.

Peer review is optional. When the design genuinely matters — high-stakes, novel, or complex enough that an independent perspective would materially raise confidence — bring in a critic and debate until the discussion converges: adopt what survives, rebut what doesn't, and hand a disagreement that survives honest debate to your human partner as an open question. Route by the design's center of gravity. A technical-heavy design (protocols, concurrency, data models, failure semantics) goes to a Codex thread via doperpowers:codex-companion's `task` verb — cross-model eyes catch what same-model review is blind to; its references/amigo.md has the critic recipe, debated over `--resume-last`. A product-heavy, judgment-heavy, or still-open design goes to the `doperpowers:critique` agent with brief context and paths to the design artifacts, debated via SendMessage. Most designs don't need either.

## The spec

Write the design to `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md` in the shape [references/living-spec.md](references/living-spec.md) gives — purpose-first opening, acceptance phrased as observable behavior, the living tail — and commit it. Seed the Decision Log from the grill's resolved forks and the presentation's decisions, each choice with its strongest rejected alternative and why it lost; they are already generated, so capturing them is free. Capture everything the session produced: the spec is the only durable memory this work has — a stale written decision is detectably wrong later and flows back, an uncaptured insight is silently gone.

Then reread it with fresh eyes: placeholders, sections that contradict each other, requirements that read two ways, whether the scope still fits one execution plan, the living tail present. The check easiest to miss is traceability: every load-bearing declaration in the Decision Log or design prose — anything that says the artifact must carry X — needs a concrete section, slot, or instruction that carries it, and a declaration without a counterpart is a defect. Fix what you find inline and move on.

Report the committed spec path, then dispatch an independent spec review, routed by the same center-of-gravity rule as peer review: a design-heavy or still-open spec goes to a general-purpose subagent (model=fable) — 1–2 sentences of context and the spec path are enough; a technical-heavy spec goes to doperpowers:codex-companion's `adversarial-review` verb (model `gpt-6-astra`, effort `high` via its with-effort wrapper) with the spec path in the focus text. Evaluate the findings rather than accepting them wholesale, make the changes that survive, re-run the self-review, and stop when a round yields nothing worth changing. Once the gate is satisfied, what returns to your human partner is exceptions — a design-level fork the design doesn't cover, a finding that conflicts with the design itself, a blocker you can't resolve; everything resolvable within the design is fixed where it stands and logged in the Decision Log.

Then invoke doperpowers:writing-plans — or doperpowers:decomposing for a coupled goal that fails its gate, which extends this same spec with the roadmap sections.
