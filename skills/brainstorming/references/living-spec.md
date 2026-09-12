# Living Specs

The design spec written at the end of doperpowers:brainstorming
(`docs/doperpowers/specs/YYYY-MM-DD-<topic>-design.md`) is not a snapshot of
an approval — it is the design's single source of truth for the whole life
of its feature. Decisions carry their rationale and their rejected
alternatives, discoveries made while planning and building flow back into
the document, and the feature closes with a retrospective. Whoever drives
the session maintains it: brainstorming writes it, writing-plans fixes what
planning proves wrong, execution routes discoveries into its tail, and
finishing writes the retrospective.

The norms come from Codex's ExecPlan doctrine, PLANS.md. The sections that
bind at the spec layer are quoted below char-for-char — follow the quoted
text, not a paraphrase; details die in paraphrase. Where the source says
"ExecPlan" or "plan", read "spec". What is not quoted does not bind (see
"What does NOT bind" below); the full source stays at
`archive/execplan/references/PLANS.md`, and the reasons behind each
rejection are in `docs/doperpowers/specs/2026-07-03-living-specs-design.md`
(disposition map and Decision Log).

**The bar (recalibrated from PLANS.md's novice standard):** a fresh session
with no conversation history can pick up the spec and continue the work —
decisions, their whys, and everything learned so far included. Define terms
of art; reference repo common knowledge instead of duplicating it.

## What binds

**Purpose and intent come first.**

> Purpose and intent come first. Begin by explaining, in a few sentences, why the work matters from a user's perspective: what someone can do after this change that they could not do before, and how to see it working. Then guide the reader through the exact steps to achieve that outcome, including what to edit, what to run, and what they should observe.

**Non-negotiables** (the two about a complete novice are recalibrated to the bar above; these three bind as written):

> * Every ExecPlan is a living document. Contributors are required to revise it as progress is made, as discoveries occur, and as design decisions are finalized. Each revision must remain fully self-contained.
> * Every ExecPlan must produce a demonstrably working behavior, not merely code changes to "meet a definition".
> * Every ExecPlan must define every term of art in plain language or do not use it.

**Self-containment and plain language.** An excerpt: the paragraph goes on to ask for repetition ("even if you repeat yourself"), which the bar above recalibrates; the rule itself binds:

> Self-containment and plain language are paramount. If you introduce a phrase that is not ordinary English ("daemon", "middleware", "RPC gateway", "filter graph"), define it immediately and remind the reader how it manifests in this repository (for example, by naming the files or commands where it appears).

**Avoid common failure modes.**

> Avoid common failure modes. Do not rely on undefined jargon. Do not describe "the letter of a feature" so narrowly that the resulting code compiles but does nothing meaningful. Do not outsource key decisions to the reader. When ambiguity exists, resolve it in the plan itself and explain why you chose that path. Err on the side of over-explaining user-visible effects and under-specifying incidental implementation details.

**Anchor the plan with observable outcomes.** This is the acceptance section's standard:

> Anchor the plan with observable outcomes. State what the user can do after implementation, the commands to run, and the outputs they should see. Acceptance should be phrased as behavior a human can verify ("after starting the server, navigating to [http://localhost:8080/health](http://localhost:8080/health) returns HTTP 200 with body OK") rather than internal attributes ("added a HealthCheck struct"). If a change is internal, explain how its impact can still be demonstrated (for example, by running tests that fail before and pass after, and by showing a scenario that uses the new behavior).

**Specify repository context explicitly.**

> Specify repository context explicitly. Name files with full repository-relative paths, name functions and modules precisely, and describe where new files should be created. If touching multiple areas, include a short orientation paragraph that explains how those parts fit together so a novice can navigate confidently. When running commands, show the working directory and exact command line. When outcomes depend on environment, state the assumptions and provide alternatives when reasonable.

**Validation is not optional.**

> Validation is not optional. Include instructions to run tests, to start the system if applicable, and to observe it doing something useful. Describe comprehensive testing for any new features or capabilities. Include expected outputs and error messages so a novice can tell success from failure. Where possible, show how to prove that the change is effective beyond compilation (for example, through a small end-to-end scenario, a CLI invocation, or an HTTP request/response transcript). State the exact test commands appropriate to the project’s toolchain and how to interpret their results.

**Living plans and design decisions** — all five bullets, with the spec as the target document (Progress excepted when an execution plan exists; see below):

> * ExecPlans are living documents. As you make key design decisions, update the plan to record both the decision and the thinking behind it. Record all decisions in the `Decision Log` section.
> * ExecPlans must contain and maintain a `Progress` section, a `Surprises & Discoveries` section, a `Decision Log`, and an `Outcomes & Retrospective` section. These are not optional.
> * When you discover optimizer behavior, performance tradeoffs, unexpected bugs, or inverse/unapply semantics that shaped your approach, capture those observations in the `Surprises & Discoveries` section with short evidence snippets (test output is ideal).
> * If you change course mid-implementation, document why in the `Decision Log` and reflect the implications in `Progress`. Plans are guides for the next contributor as much as checklists for you.
> * At completion of a major task or the full plan, write an `Outcomes & Retrospective` entry summarizing what was achieved, what remains, and lessons learned.

**Prototyping milestones and parallel implementations.** When unknowns are large, the spec declares spike milestones; doperpowers:writing-plans turns them into spike tasks.

> It is acceptable—-and often encouraged—-to include explicit prototyping milestones when they de-risk a larger change. Examples: adding a low-level operator to a dependency to validate feasibility, or exploring two composition orders while measuring optimizer effects. Keep prototypes additive and testable. Clearly label the scope as “prototyping”; describe how to run and observe results; and state the criteria for promoting or discarding the prototype.
>
> Prefer additive code changes followed by subtractions that keep tests passing. Parallel implementations (e.g., keeping an adapter alongside an older path during migration) are fine when they reduce risk or enable tests to continue passing during a large migration. Describe how to validate both paths and how to retire one safely with tests. When working with multiple new libraries or feature areas, consider creating spikes that evaluate the feasibility of these features _independently_ of one another, proving that the external library performs as expected and implements the features we need in isolation.

## When the spec carries its own execution

When brainstorming routed the work to a spec that carries its own execution
— its well-scoped-and-delegable route: one agent can reliably own the work,
and it runs sequentially — the spec also carries the execution sections
below, in PLANS.md's skeleton wording: `Progress`, placed right after the
purpose (it is this spec's ledger, kept current at every stopping point),
`Plan of Work` (told as milestones when the work has stages), `Concrete
Steps`, and `Interfaces and Dependencies` when the work defines new
interfaces. On the spec-plus-execution-plan route, those live in the
execution plan doperpowers:writing-plans writes and in the SDE ledger, and
the spec's execution section is one line naming the plan file.

    ## Progress

    Use a list with checkboxes to summarize granular steps. Every stopping point must be documented here, even if it requires splitting a partially completed task into two (“done” vs. “remaining”). This section must always reflect the actual current state of the work.

    - [x] (2025-10-01 13:00Z) Example completed step.
    - [ ] Example incomplete step.
    - [ ] Example partially completed step (completed: X; remaining: Y).

    Use timestamps to measure rates of progress.

    ## Plan of Work

    Describe, in prose, the sequence of edits and additions. For each edit, name the file and location (function, module) and what to insert or change. Keep it concrete and minimal.

    ## Concrete Steps

    State the exact commands to run and where to run them (working directory). When a command generates output, show a short expected transcript so the reader can compare. This section must be updated as work proceeds.

    ## Interfaces and Dependencies

    Be prescriptive. Name the libraries, modules, and services to use and why. Specify the types, traits/interfaces, and function signatures that must exist at the end of the milestone. Prefer stable names and paths such as `crate::module::function` or `package.submodule.Interface`. E.g.:

    In crates/foo/planner.rs, define:

        pub trait Planner {
            fn plan(&self, observed: &Observed) -> Vec<Action>;
        }

**Milestones** shape the Plan of Work when the work has stages:

> Milestones are narrative, not bureaucracy. If you break the work into milestones, introduce each with a brief paragraph that describes the scope, what will exist at the end of the milestone that did not exist before, the commands to run, and the acceptance you expect to observe. Keep it readable as a story: goal, work, result, proof. Progress and milestones are distinct: milestones tell the story, progress tracks granular work. Both must exist. Never abbreviate a milestone merely for the sake of brevity, do not leave out details that could be crucial to a future implementation.
>
> Each milestone must be independently verifiable and incrementally implement the overall goal of the execution plan.

**While such a spec is being executed**, PLANS.md's implementing rule binds, with brainstorming's gate as the one stop: a fork under it that the spec does not cover goes to your human partner; everything else is decided and logged.

> When implementing an executable specification (ExecPlan), do not prompt the user for "next steps"; simply proceed to the next milestone. Keep all sections up to date, add or split entries in the list at every stopping point to affirmatively state the progress made and next steps. Resolve ambiguities autonomously, and commit frequently.

## What does NOT bind

Not quoted above, and superseded by doperpowers machinery: the single fenced code block, prose-first, no-tables formatting (specs are files, not chat payloads — use tables, JSON, or diagrams wherever they beat prose for precision); novice-grade self-containment (the bar above); the Idempotence and Recovery section (worktree isolation + git); Artifacts and Notes and "capture evidence" inside the fence (the living tail's evidence snippets); "do not prompt the user for next steps" at authoring time (the human gates — design approval and spec review in doperpowers:brainstorming — come first; the rule binds only during execution, as above); and, when an execution plan exists, Progress and the Milestones/Concrete Steps/Interfaces sections (the SDE ledger + git + plan checkboxes, and doperpowers:writing-plans at contract resolution). These rejections carry rationale — read the Decision Log in `docs/doperpowers/specs/2026-07-03-living-specs-design.md` before re-proposing one; the execution-plan-conditioned ones were narrowed for the one-unit shape in `docs/doperpowers/specs/2026-09-12-one-spec-sized-by-the-gate-design.md`.

## The living tail

Every spec ends with these four sections, in this order, headed exactly as shown.

**`## Decision Log`** — every design decision, in PLANS.md's skeleton format:

    - Decision: …
      Rationale: …
      Date/Author: …

Seed it at brainstorm time with the chosen approach AND each rejected alternative with why it lost — the approaches step already generated them; capturing them is free and stops re-proposals. Extend it whenever course changes mid-feature. The verification call brainstorming makes when it routes the work — which independent reviews the work gets and the branch review rung — is one of these entries, so the executor, the reviewer, and a recovering session read the same council.

**`## Surprises & Discoveries`** — in PLANS.md's skeleton format:

    - Observation: …
      Evidence: …

For anything that changed design understanding: an assumption that proved false, a measured behavior, a constraint discovered during planning or execution. Short evidence snippets — test output is ideal. Incidental implementation noise belongs in commit messages, not here.

**`## Outcomes & Retrospective`** — until finish, exactly the line "Pending — written at finish." At finish (after the whole-branch review), summarize what was achieved against the spec's original purpose, what remains, and lessons learned.

**`## Revision Notes`** — one dated line per spec revision describing what changed and why (PLANS.md's bottom-note rule: "you must write a note at the bottom of the plan describing the change and the reason why"). When you revise, keep the whole document consistent — reflect the change across sections, not just where convenient.

## Front of the spec

Untemplated on purpose: across this repo's existing specs no heading structure repeats, and that variance is a feature — form fits problem (state tables for state machines, JSON for schemas, prose for concepts). Only three things are required: the purpose-first opening, an acceptance section phrased as observable behavior, and the living tail — plus the execution sections above when the spec carries its own execution.
