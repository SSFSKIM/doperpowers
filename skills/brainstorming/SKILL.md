---
name: brainstorming
description: "Use when starting any creative work — creating features, building components, adding functionality, or modifying behavior — before a design exists."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design and get approval.

**The gate:** no implementation — code, scaffolding, invoking implementation skills — until a design has been presented and your human partner has approved it. Simple projects too: the design may be three sentences, but it exists and gets a yes — "too simple to need a design" is where unexamined assumptions cause the most wasted work.

## The path

Work through these in order:

1. **Explore project context** — check files, docs, recent commits
2. **Grill** — clarifying questions one at a time per The Grill below; understand purpose/constraints/success criteria
3. **Recommend the track, then get confirmation** — controlled (continue below), autonomous (hand off to doperpowers:execplan), or direct (narrow scope, clear task definition: briefly design, then implement right away — steps 6–9 don't apply); see Choosing the Track below
4. **Propose 2-3 approaches** — with trade-offs and your recommendation
5. **Present design** — in sections scaled to their complexity, approval after each section
6. **Write design doc** — in living-spec shape per doperpowers:execspec (purpose-first opening, behavior-phrased acceptance, living tail with the Decision Log seeded from step 4's alternatives); save to `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md` and commit
7. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope (see below)
8. **User reviews written spec** — ask your human partner to review the spec file before proceeding
9. **Transition to implementation** — invoke doperpowers:writing-plans

Three exits leave this skill: writing-plans (controlled), execplan (autonomous, on your human partner's explicit choice), or implementing directly in this session (direct track — no spec, no plan; the approved design is the contract, and test-driven-development still applies for testable logic). One earlier exit exists at scope-assessment time, before any design: a goal that fails the scope check — too big for one agent to reliably own as one unit — routes to doperpowers:decomposing; see the scope bullet below.

## The Process

**Understanding the idea:**

- Check out the current project state first (files, docs, recent commits)
- Before asking detailed questions, assess scope: brainstorming defines a goal/purpose at a time, whatever its size — but if the request describes a goal too big for one agent to reliably own as one unit (the gate in doperpowers:decomposing; e.g., "build a platform with chat, file storage, billing, and analytics"), flag this immediately. Division belongs one skill over: recommend doperpowers:decomposing — it cuts the goal into children with acceptance and edges, and each child then returns through this skill with its parent section as pre-landed input. Confirm the route with your human partner before switching; don't drift into grilling child-level details of a goal that needs dividing first.
- For appropriately-scoped projects, run the grill below to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Focus on understanding: purpose, constraints, success criteria

**The Grill** — this is the clarification protocol:

> Interview relentlessly about every aspect of the initiative until you reach a shared understanding with your human partner. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.
>
> Ask the questions one at a time, waiting for feedback on each question before continuing. Asking multiple questions at once is bewildering. If a topic needs more exploration, break it into multiple questions.
>
> If a question can be answered by exploring the codebase, explore the codebase instead. If it can't be answered for lack of information, run research.

Three moves to use throughout:

- **Sharpen fuzzy terms** — propose a precise canonical term: "You're saying 'account' — do you mean the Customer or the User? Those are different things."
- **Stress-test with concrete scenarios** — invent scenarios that probe edge cases and force precision about the boundaries between concepts.
- **Cross-reference with code** — when your human partner states how something works, check whether the code agrees; surface contradictions.

One more move extends the grill's codebase rule outward — **situate at four radii**: a question the codebase can answer is answered by reading it; a question the codebase cannot answer but the world can (prior art, the literature, an external service's real behavior) is answered by research, not speculation; a question only an experiment can answer becomes a spike — run inline when small, registered as its own goal when not; and every idea is situated against the project's standing purpose (the top-level goal of the project). Explore, research, and spike are not separate ceremonies — they are this one rule at different radii.

Triage the grilling: grill what is fuzzy or important; don't grind an already-clear request to death.

**The challenger duty.** Converging the idea is half the grill; the other half is judging whether the idea as conceived deserves to converge. Run this assessment on every idea: hold it against the project's standing purpose — and not only for internal fit. Make the outward move your human partner cannot: compare the idea against the other levers the purpose itself suggests, including levers absent from the codebase (an absent obvious lever is often the prerequisite frame, not background to assume) and what the world already knows about this problem class. An idea can be perfectly coherent and still be dominated by an alternative nobody named. Voice what you find ONLY when it would change the decision — a materially better or prerequisite frame, a consideration that shifts scope or approach — and say it once, sharply, BEFORE convergence, grounded in this project's purpose, this codebase, or named sources.

**Choosing the Track (after the grill):**

Three tracks leave this skill. The controlled track — the rest of this skill: approaches → design → spec → doperpowers:writing-plans — keeps human gates until your human partner types `<agent-ready>`; from that signal on, run the remaining steps autonomously. The autonomous track hands off to doperpowers:execplan, which authors one self-contained ExecPlan and executes it with no mid-flight human gates. The direct track is for work too narrow to deserve either: present a brief design, get approval, then implement right away in this session — no spec, no plan.

**You recommend the track; your human partner confirms it.** Don't drift silently into controlled, and don't ask an open "which track do you want?" — assess the work, name the track that fits with a one-line reason, and get a yes. This is the same posture as the grill: recommend, then confirm.

- Read the shape of the work off the grill and recommend accordingly:
  - **Well-scoped and delegable** — the grill exhausted the open questions and the only remaining unknowns are feasibility ("we won't know until we try," which become prototyping milestones), not taste → **recommend autonomous**.
  - **Large, novel, taste-heavy, or high-stakes** — taste questions keep arising that can't be settled up front, or the work needs human judgment mid-flight → **recommend controlled**.
  - **Narrow and small** — a focused change an engineer would just do (a config tweak, a small bugfix, one thin feature slice), where a spec or ExecPlan would outweigh the work itself → **recommend direct**.
- State the recommendation and its reason in one message, then wait — e.g. *"This is well-scoped and the open questions are closed, so I'd take the autonomous track (execplan) and run it end to end. Good with that, or would you rather stay controlled?"*
- Routing still requires your human partner's explicit confirmation — never route silently, and never treat "just handle it" as the choice. Their explicit yes to autonomous is the approval the gate requires; doperpowers:execplan's contract governs from there.
- If they override your recommendation, follow their choice. On a confirmed controlled track (whether you recommended it or they chose it), continue this skill.

**Exploring approaches:**

- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

**Presenting the design:**

- Once you believe you understand what you're building, present the design
- Scale each section to its complexity: a few sentences if straightforward, up to 200-300 words if nuanced
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

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
- Seed the Decision Log with the chosen approach and each rejected alternative from the approaches step, with why it lost — they are already generated; capturing them is free
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

**User Review Gate:**
After the spec self-review passes, ask your human partner to review the written spec before proceeding:

> "Spec written and committed to `<path>`. Please review it and let me know if you want to make any changes before we start writing out the implementation plan."

While waiting for their response, dispatch a general-purpose subagent (model=fable) for an independent spec review — a brief prompt with 1-2 sentences of context and the spec path is enough. Evaluate its findings rather than accepting them wholesale, make the changes that survive, and re-run the spec self-review. Handle requested changes from your human partner the same way. Proceed once they approve.

**Implementation:**

Invoke doperpowers:writing-plans to create the implementation plan — the next step on the controlled track.
