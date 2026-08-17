---
name: brainstorming
description: "Use when starting any creative work — creating features, building components, adding functionality, or modifying behavior — before a design exists."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then grill in batched rounds to refine the idea. Once you understand what you're building, present the design and get approval.

**The gate:** no implementation — code, scaffolding, invoking implementation skills — until a design has been presented and your human partner has approved it. Simple projects too: the design may be three sentences, but it exists and gets a yes — "too simple to need a design" is where unexamined assumptions cause the most wasted work.

## The path

Work through these in order:

1. **Explore project context** — check files, docs, recent commits
2. **Grill** — batched rounds of clarifying questions per The Grill below; understand purpose/constraints/success criteria
3. **Recommend the track, then get confirmation** — controlled (continue below), autonomous (hand off to doperpowers:execplan), or direct (narrow scope, clear task definition: briefly design, then implement right away — steps 5–8 don't apply); see Choosing the Track below
4. **Present the design** — one holistic pass, attention-ranked, one approval (see Presenting the Design below)
5. **Write design doc** — in living-spec shape per doperpowers:execspec (purpose-first opening, behavior-phrased acceptance, living tail with the Decision Log seeded from the grill's resolved forks and the presentation's decisions); save to `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md` and commit
6. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope (see below)
7. **Independent spec review** — dispatch a spec reviewer subagent; evaluate its findings, fix what survives (see below)
8. **Transition to implementation** — invoke doperpowers:writing-plans (a goal routed to decomposing invokes doperpowers:decomposing here instead)

Three exits leave this skill: writing-plans (controlled), execplan (autonomous, on your human partner's explicit choice), or implementing directly in this session (direct track — no spec, no plan; the approved design is the contract, and test-driven-development still applies for testable logic). A fourth exit routes to doperpowers:decomposing when the goal fails its ownability gate — too big for one agent to reliably own as one unit — and WHEN it exits depends on coupling (see the scope bullet below): an uncoupled bundle exits at scope-assessment time, before any design; a coupled goal exits only after its design is matured and approved here, carrying that design as decomposing's input.

## The Process

**Understanding the idea:**

- Check out the current project state first (files, docs, recent commits)
- Before asking detailed questions, assess scope and coupling: brainstorming defines and matures one goal at a time, whatever its size. A goal too big for one agent to reliably own as one unit (the gate in doperpowers:decomposing) will be divided — but WHEN to hand it over depends on whether its pieces share a design surface. Pieces that don't interact — no shared data, contracts, or decisions that need the whole in view (e.g., "build a platform with chat, file storage, billing, and analytics" as four freestanding products) — are a bundle, not a whole: recommend doperpowers:decomposing immediately, since joint maturation would generate nothing; each child returns through this skill later with its parent section as pre-landed input. Pieces that DO interact are the reason to design before dividing: the interaction surface — shared models, contract shapes, decisions that come out differently with everything in view — is generated in this session or never. Run the full grill and design pass on the whole, regardless of size, and hand the approved design to doperpowers:decomposing, which derives the cut from it. Capture everything the session produces: the spec is the only durable memory this org has — a stale written decision is detectably wrong at child time and flows back, an uncaptured insight is silently gone. Confirm the route with your human partner before switching either way.
- For appropriately-scoped projects, run the grill below to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Focus on understanding: purpose, constraints, success criteria

**The Grill** — this is the clarification protocol:

> Interview relentlessly about every aspect of the initiative until you reach a shared understanding with your human partner. Map the initiative as a design tree — every decision branches into the decisions that hang off it.
>
> Work the tree in batched rounds. The frontier is every decision whose prerequisites are already settled — the questions you can ask now without guessing at answers you haven't heard yet. Ask the whole frontier in one round: each round's answers reshape the tree and push the frontier outward, and a question whose answer depends on another question still open in this round belongs to a later round. The grill is done when the frontier is empty — every branch of design tree visited, nothing left silently assumed. Act only after you confidently reached a shared understanding.
>
> Deliver each round by fit: clear multiple-choice questions ride AskUserQuestion, several at once; relatively open but still bounded questions go as prose inline in the chat. In a non-interactive context (a board ticket, a relay comment), the whole round is one numbered message.
>
> Finding facts is your job, never your human partner's: a question the codebase, filesystem, external information on web can answer is answered by exploring them; when you need more extensive exploration, run dedicated research exploring web, codebase, or whatever you need. Don't block a round on a running exploration — running exploration is an unsettled prerequisite, so only its downstream questions wait for it; ask the rest of the frontier now.


Three moves to use throughout:

- **Sharpen fuzzy terms** — propose a precise canonical term: "You're saying 'account' — do you mean the Customer or the User? Those are different things."
- **Stress-test with concrete scenarios** — invent scenarios that probe edge cases and force precision about the boundaries between concepts.
- **Cross-reference with code** — when your human partner states how something works, check whether the code agrees; surface contradictions.

One more move extends the grill's codebase rule outward — **situate at four radii**: a question the codebase can answer is answered by reading it; a question the codebase cannot answer but the world can (prior art, the literature, an external service's real behavior) is answered by research, not speculation; a question only an experiment can answer becomes a spike — run inline when small, registered as its own goal when not; and every idea is situated against the project's standing purpose (the top-level goal of the project). Explore, research, and spike are not separate ceremonies — they are this one rule at different radii.

Triage the grilling: grill what is fuzzy or important; don't grind an already-clear request to death. Depth has a stopping point, not a size limit: the design is mature when the remaining unknowns are empirical — answerable only by a spike, by implementation contact, or by watching the thing run — and no longer architectural (answerable now from the assembled picture). Answer everything the full view can answer; name the empirical residue in the design as delegated unknowns rather than leaving it implicit.

A design fork with genuinely sound alternatives is a grill question, not presentation material — put it to your human partner when it surfaces, with your recommendation, like any other question. By the time you present the design, the forks the grill could see are already settled; only forks that first emerge while composing the full design survive to the presentation, and those go to the top of its attention ranking.

**The contribution duty.** Your human partner's framing of the idea is a starting point, not the boundary of the design space — the partner who initiated it may not see it as fully as you can. You carry expert-level knowledge of nearly every domain an idea touches; spend it on the idea's substance, not only its clarification. Contemplate the idea from angles the framing didn't open and consider what your partner didn't seem to consider; situate it within the project and its standing purpose; illuminate the questions whose answers would most reshape the design; and offer reasoned opinions of your own that develop and mature the idea. The challenger duty below is this posture's sharpest form — the contribution itself runs throughout the grill.

**The challenger duty.** Converging the idea is half the grill; the other half is judging whether the idea as conceived deserves to converge. Run this assessment on every idea: hold it against the project's standing purpose — and not only for internal fit. Make the outward move your human partner cannot: compare the idea against the other levers the purpose itself suggests, including levers absent from the codebase (an absent obvious lever is often the prerequisite frame, not background to assume) and what the world already knows about this problem class. An idea can be perfectly coherent and still be dominated by an alternative nobody named. Voice what you find once, sharply, BEFORE convergence, grounded in this project's purpose, this codebase, or named sources.

**Choosing the Track (after the grill):**

Three tracks leave this skill. The controlled track is the rest of this skill: design → spec → doperpowers:writing-plans. The autonomous track hands off to doperpowers:execplan, which authors one self-contained ExecPlan and executes it with no mid-flight human gates. The direct track is for work too narrow to deserve either: present a brief design, get approval, then implement right away in this session — no spec, no plan. A goal that fails the ownability gate chooses none of these — its route is doperpowers:decomposing (see the scope bullet): a coupled goal still runs the design presentation and spec writing first; then step 8 becomes invoking doperpowers:decomposing, which extends that same spec with the roadmap sections.

**You recommend the track; your human partner confirms it.** Don't drift silently into controlled, and don't ask an open "which track do you want?" — assess the work, name the track that fits with a one-line reason, and get a yes. This is the same posture as the grill: recommend, then confirm.

- Read the shape of the work off the grill and recommend accordingly:
  - **Well-scoped and delegable** — the grill exhausted the open questions and the only remaining unknowns are feasibility ("we won't know until we try," which become prototyping milestones), not taste → **recommend autonomous**.
  - **Large, novel, taste-heavy, or high-stakes** — taste questions keep arising that can't be settled up front, or the work needs human judgment mid-flight → **recommend controlled**.
  - **Narrow and small** — a focused change an engineer would just do (a config tweak, a small bugfix, one thin feature slice), where a spec or ExecPlan would outweigh the work itself → **recommend direct**.
- State the recommendation and its reason in one message, then wait — e.g. *"This is well-scoped and the open questions are closed, so I'd take the autonomous track (execplan) and run it end to end. Good with that, or would you rather stay controlled?"*
- Routing still requires your human partner's explicit confirmation — never route silently, and never treat "just handle it" as the choice. Their explicit yes to autonomous is the approval the gate requires; doperpowers:execplan's contract governs from there.
- If they override your recommendation, follow their choice. On a confirmed controlled track (whether you recommended it or they chose it), continue this skill.

**Presenting the design:**

Once you believe you understand what you're building, present the whole design in one pass. The design itself — the description of the thing you intend to build — is the body of the presentation; the structure around it triages your human partner's attention, so they know which parts need their judgment and which they can skim:

1. **Open forks** (rare) — decisions that first emerged while composing the design and have genuinely sound alternatives. Present each with its candidates, trade-offs, and your recommendation; your human partner decides.
2. **The design itself** — architecture, components, data flow, error handling, and testing, described in sections scaled to their complexity: a few sentences if straightforward, up to 200-300 words if nuanced. Describe the thing, not just your choices about it — what each part does, how the parts fit together, and the reasoning behind the significant calls. Where a section turns on your human partner's taste or domain knowledge, mark it as one to review carefully.
3. **Silent decisions** — the trivial calls you made without asking, a skimmable line each, for transparency.

One approval covers the whole pass; revise conversationally, and be ready to go back and clarify if something doesn't make sense. Split the presentation into sequential rounds only when a real dependency forces it: an open fork that reshapes everything downstream is its own frontier — present it, get the decision, then present what hangs off it (the grill's frontier logic).

**Peer review (optional).** When the design genuinely matters — high-stakes,
novel, or complex enough that an independent perspective would materially
raise confidence in it — bring in a critic and debate until the discussion
converges: evaluate each finding, adopt what survives, rebut what doesn't.
A disagreement that survives honest debate goes to your human partner as an
open question. Route by the design's center of gravity: a technical-heavy
design (protocols, concurrency, data models, failure semantics) goes to a
Codex thread via doperpowers:codex-companion's `task` verb — cross-model
eyes catch what same-model review is blind to; its references/amigo.md has
the critic recipe, debated over `--resume-last`. A product-heavy,
judgment-heavy, or still-open design goes to the `doperpowers:critique`
agent with brief context and paths to the design artifacts, debated via
SendMessage. Whether to fire either is your call; most designs don't
need it.

**Design for isolation and clarity:**

- Break the system into smaller units that each have one clear purpose, communicate through well-defined interfaces, and can be understood and tested independently
- For each unit, you should be able to answer: what does it do, how do you use it, and what does it depend on?
- Can someone understand what a unit does without reading its internals? Can you change the internals without breaking consumers? If not, the boundaries need work.
- Smaller, well-bounded units are also easier for you to work with - you reason better about code you can hold in context at once, and your edits are more reliable when files are focused. When a file grows large, that's often a signal that it's doing too much.

**Working in existing codebases:**

- Explore the current structure before proposing changes. Follow existing patterns.
- Where existing code has problems that affect the work (e.g., a file that's grown too large, unclear boundaries, tangled responsibilities), include targeted improvements as part of the design - the way a good developer improves code they're working in.
- Don't propose unrelated refactoring. Stay focused on what serves the current goal.

## After the Design

**Documentation:**

- Write the validated design (spec) to `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md`
  - (User preferences for spec location override this default)
- Shape it per doperpowers:execspec: purpose-first opening, acceptance phrased as observable behavior, and the living tail (`## Decision Log`, `## Surprises & Discoveries`, `## Outcomes & Retrospective` reading "Pending — written at finish.", `## Revision Notes`)
- Seed the Decision Log from the grill's resolved forks and the presentation's decisions — each choice with its rejected alternatives and why they lost; they are already generated, capturing them is free
- Commit the design document to git

**Spec Self-Review:**
After writing the spec document, look at it with fresh eyes:

1. **Placeholder scan:** Any "TBD", "TODO", incomplete sections, or vague requirements? Fix them.
2. **Internal consistency:** Do any sections contradict each other? Does the architecture match the feature descriptions?
3. **Scope check:** Is this focused enough for a single implementation plan, or does it need decomposition?
4. **Ambiguity check:** Could any requirement be interpreted two different ways? If so, pick one and make it explicit.
5. **Living tail:** Are `## Decision Log` (with at least one rejected alternative), `## Surprises & Discoveries`, `## Outcomes & Retrospective` ("Pending — written at finish."), and `## Revision Notes` all present?
6. **Traceability:** For every load-bearing declaration in the Decision Log or design prose — anything that says the artifact must carry X — point to the concrete section, slot, or instruction that carries it. A declaration without a counterpart is a defect.

Fix any issues inline. No need to re-review — just fix and move on.

**Independent Spec Review:**
After the spec self-review passes, report the committed spec path, then dispatch an independent spec review, routed by the same center-of-gravity rule as the peer-review layer: a design-heavy or still-open spec goes to a general-purpose subagent (model=fable) — a brief prompt with 1-2 sentences of context and the spec path is enough; a technical-heavy spec goes to doperpowers:codex-companion's `adversarial-review` verb (model `gpt-5.6-sol`, effort `xhigh` via its with-effort wrapper) with the spec path in the focus text. Evaluate the findings rather than accepting them wholesale, make the changes that survive, and re-run the spec self-review.

From design approval onward, what returns to your human partner is exceptions: a design-level fork the approved design doesn't cover, a finding that conflicts with the design itself, or a blocker you can't resolve. Everything resolvable within the approved design is fixed where it stands and logged in the spec's Decision Log.

**Implementation:**

Invoke doperpowers:writing-plans to create the implementation plan — the next step on the controlled track.
