---
name: brainstorming
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design and get user approval.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until you have presented a design and the user has approved it. This applies to EVERY project regardless of perceived simplicity.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A todo list, a single-function utility, a config change — all of them. "Simple" projects are where unexamined assumptions cause the most wasted work. The design can be short (a few sentences for truly simple projects), but you MUST present it and get approval.

## Checklist

You MUST create a task for each of these items and complete them in order:

1. **Explore project context** — check files, docs, recent commits
2. **Offer the visual companion just-in-time** — NOT upfront. The first time a question would genuinely be clearer shown than described, offer it then (its own message); on approval its browser tab opens for you. If no visual question ever arises, never offer it. See the Visual Companion section below.
3. **Grill** — clarifying questions one at a time per The Grill below; understand purpose/constraints/success criteria
4. **Recommend the track, then get confirmation** — assess the work and recommend controlled (continue below) or autonomous (hand off to doperpowers:execplan), then get your human partner's explicit yes; see Choosing the Track below
5. **Propose 2-3 approaches** — with trade-offs and your recommendation
6. **Present design** — in sections scaled to their complexity, get user approval after each section
7. **Write design doc** — in living-spec shape per doperpowers:execspec (purpose-first opening, behavior-phrased acceptance, living tail with the Decision Log seeded from step 5's alternatives); save to `docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md` and commit
8. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope (see below)
9. **User reviews written spec** — ask user to review the spec file before proceeding
10. **Transition to implementation** — invoke writing-plans skill to create implementation plan

## Process Flow

```dot
digraph brainstorming {
    "Explore project context" [shape=box];
    "Grill (clarifying questions)" [shape=box];
    "Recommend track,\nhuman confirms" [shape=diamond];
    "Invoke execplan skill" [shape=doublecircle];
    "Propose 2-3 approaches" [shape=box];
    "Present design sections" [shape=box];
    "User approves design?" [shape=diamond];
    "Write design doc" [shape=box];
    "Spec self-review\n(fix inline)" [shape=box];
    "User reviews spec?" [shape=diamond];
    "Invoke writing-plans skill" [shape=doublecircle];

    "Explore project context" -> "Grill (clarifying questions)";
    "Grill (clarifying questions)" -> "Recommend track,\nhuman confirms";
    "Recommend track,\nhuman confirms" -> "Invoke execplan skill" [label="autonomous (confirmed)"];
    "Recommend track,\nhuman confirms" -> "Propose 2-3 approaches" [label="controlled (confirmed)"];
    "Propose 2-3 approaches" -> "Present design sections";
    "Present design sections" -> "User approves design?";
    "User approves design?" -> "Present design sections" [label="no, revise"];
    "User approves design?" -> "Write design doc" [label="yes"];
    "Write design doc" -> "Spec self-review\n(fix inline)";
    "Spec self-review\n(fix inline)" -> "User reviews spec?";
    "User reviews spec?" -> "Write design doc" [label="changes requested"];
    "User reviews spec?" -> "Invoke writing-plans skill" [label="approved"];
}
```

**The terminal state is invoking writing-plans** — or doperpowers:execplan when your human partner explicitly chose the autonomous track. Do NOT invoke frontend-design, mcp-builder, or any other implementation skill. The ONLY skills you invoke after brainstorming are writing-plans (controlled track) and execplan (autonomous track, on your human partner's explicit choice). (One earlier exit exists at scope-assessment time, before any design: a goal that fails the gate's scope check — too big for one agent to reliably own as one unit — routes to doperpowers:decomposing-goals; see the scope bullet below.)

## The Process

**Understanding the idea:**

- Check out the current project state first (files, docs, recent commits)
- Before asking detailed questions, assess scope: brainstorming defines ONE goal at a time, whatever its size — but if the request describes a goal too big for one agent to reliably own as one unit (the gate in doperpowers:decomposing-goals; e.g., "build a platform with chat, file storage, billing, and analytics"), flag this immediately. Division belongs one skill over: recommend doperpowers:decomposing-goals — it cuts the goal into children with acceptance and edges, and each child then returns through this skill (or execplan) with its parent section as pre-landed input. Confirm the route with your human partner before switching; don't drift into grilling child-level details of a goal that needs dividing first.
- For appropriately-scoped projects, run the grill below to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Focus on understanding: purpose, constraints, success criteria

**The Grill** — vendored verbatim from Matt Pocock's `grilling` skill; this is the clarification protocol:

> Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.
>
> Ask the questions one at a time, waiting for feedback on each question before continuing. Asking multiple questions at once is bewildering. If a topic needs more exploration, break it into multiple questions.
>
> If a question can be answered by exploring the codebase, explore the codebase instead.

Three moves to use throughout (kept from his `domain-modeling` skill; its artifacts are not used here):

- **Sharpen fuzzy terms** — propose a precise canonical term: "You're saying 'account' — do you mean the Customer or the User? Those are different things."
- **Stress-test with concrete scenarios** — invent scenarios that probe edge cases and force precision about the boundaries between concepts.
- **Cross-reference with code** — when your human partner states how something works, check whether the code agrees; surface contradictions.

One more move extends the grill's codebase rule outward — **situate at four radii**: a question the codebase can answer is answered by reading it; a question the world can answer (prior art, the literature, an external service's real behavior) is answered by research, not speculation; a question only an experiment can answer becomes a spike — run inline when small, registered as its own goal when not; and every idea is situated against the project's standing purpose (the top-level goal in CLAUDE.md, and the root spec it routes to when the project keeps one). Explore, research, and spike are not separate ceremonies — they are this one rule at different radii.

Triage the grilling: grill what is fuzzy or important; don't grind an already-clear request to death.

**The challenger duty.** Converging the idea is half the grill; the other half is judging whether the idea as conceived deserves to converge. Run this assessment always, on every idea: hold it against the project's standing purpose — and not only for internal fit. Make the outward move your human partner cannot: compare the idea against the other levers the purpose itself suggests, including levers absent from the codebase (an absent obvious lever is often the prerequisite frame, not background to assume) and what the world already knows about this problem class. An idea can be perfectly coherent and still be dominated by an alternative nobody named. Voice what you find ONLY when it would change the decision — a materially better or prerequisite frame, a consideration that shifts scope or approach — and say it once, sharply, BEFORE convergence, grounded in this project's purpose, this codebase, or named sources; a generic checklist ("have you considered scalability?") is not a challenge. The human's override is absolute: this is recommend-then-confirm applied to the idea itself — offer, not veto; overridden, proceed wholeheartedly.

**Choosing the Track (after the grill):**

Two tracks leave this skill. The controlled track — the rest of this skill: approaches → design → spec → doperpowers:writing-plans — keeps human gates throughout. The autonomous track hands off to doperpowers:execplan, which authors one self-contained ExecPlan and executes it with no mid-flight human gates.

**You recommend the track; your human partner confirms it.** Don't drift silently into controlled, and don't ask an open "which track do you want?" — assess the work, name the track that fits with a one-line reason, and get a yes. This is the same posture as the grill: recommend, then confirm.

- Read the shape of the work off the grill and recommend accordingly:
  - **Well-scoped and delegable** — the grill exhausted the open questions and the only remaining unknowns are feasibility ("we won't know until we try," which become prototyping milestones), not taste → **recommend autonomous**.
  - **Large, novel, taste-heavy, or high-stakes** — taste questions keep arising that can't be settled up front, or the work needs human judgment mid-flight → **recommend controlled**.
- State the recommendation and its reason in one message, then wait — e.g. *"This is well-scoped and the open questions are closed, so I'd take the autonomous track (execplan) and run it end to end. Good with that, or would you rather stay controlled?"*
- Routing still requires your human partner's explicit confirmation — never route silently, and never treat "just handle it" as the choice. Their explicit yes to autonomous is the approval the HARD-GATE requires; doperpowers:execplan's contract governs from there.
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
- Use elements-of-style:writing-clearly-and-concisely skill if available
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
After the spec review loop passes, ask the user to review the written spec before proceeding:

> "Spec written and committed to `<path>`. Please review it and let me know if you want to make any changes before we start writing out the implementation plan."

Wait for the user's response. If they request changes, make them and re-run the spec review loop. Only proceed once the user approves.

**Implementation:**

- Invoke the writing-plans skill to create a detailed implementation plan
- Do NOT invoke any other skill. writing-plans is the next step.

## Key Principles

- **One question at a time** - Don't overwhelm with multiple questions
- **Multiple choice preferred** - Easier to answer than open-ended when possible
- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Explore alternatives** - Always propose 2-3 approaches before settling
- **Incremental validation** - Present design, get approval before moving on
- **Be flexible** - Go back and clarify when something doesn't make sense

## Visual Companion

A browser-based companion for showing mockups, diagrams, and visual options during brainstorming. Available as a tool — not a mode. Accepting the companion means it's available for questions that benefit from visual treatment; it does NOT mean every question goes through the browser.

**Offering the companion (just-in-time):** Do NOT offer it upfront. Wait until a question would genuinely be clearer shown than told — a real mockup / layout / diagram question, not merely a UI *topic*. The first time that happens, offer it then, as its own message:
> "This next part might be easier if I show you — I can put together mockups, diagrams, and comparisons in a browser tab as we go. It's still new and can be token-intensive. Want me to? I'll open it for you."

**This offer MUST be its own message.** Only the offer — no clarifying question, summary, or other content. Wait for the user's response. If they accept, start the server with `--open` so their browser opens to the first screen automatically. If they decline, continue text-only and don't offer again unless they raise it.

**Per-question decision:** Even after the user accepts, decide FOR EACH QUESTION whether to use the browser or the terminal. The test: **would the user understand this better by seeing it than reading it?**

- **Use the browser** for content that IS visual — mockups, wireframes, layout comparisons, architecture diagrams, side-by-side visual designs
- **Use the terminal** for content that is text — requirements questions, conceptual choices, tradeoff lists, A/B/C/D text options, scope decisions

A question about a UI topic is not automatically a visual question. "What does personality mean in this context?" is a conceptual question — use the terminal. "Which wizard layout works better?" is a visual question — use the browser.

If they agree to the companion, read the detailed guide before proceeding:
`skills/brainstorming/visual-companion.md`
