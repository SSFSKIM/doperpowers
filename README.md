# doperpowers

**A methodology your coding agent actually follows** — not a pile of prompts, but a set of skills that trigger themselves at the right moment and keep the agent honest from first idea to merged branch.

```text
                          d o p e r p o w e r s

   what you're building  ─┬─▶  CONTROLLED  · you sign off on the design
                          │      brainstorm → spec → plan → subagent-TDD → review → ship
                          │
                          └─▶  AUTONOMOUS  · it runs while you're away
                                 board → dispatch → build → review → merge
```

Most agent scaffolding is a single linear pipeline: you talk, it plans, it codes. doperpowers splits that in two. When the work needs your judgement, the **controlled track** shows you the design in readable chunks and stops for your approval before anything is built. When the work is well-scoped and delegable, the **autonomous track** takes a ticket off the board and drives it to a reviewed pull request without waking you up. The skills route between the two based on what you actually asked for.

Because every skill declares when it applies, you don't invoke any of this by hand. The agent checks for a relevant skill before it starts a task, and the right workflow just happens.

---

## Two tracks, one discipline

Both tracks enforce the same non-negotiables — design before code, tests before implementation, evidence before "done." They differ only in where the human sits.

**Controlled** — for work where taste and intent matter.
The agent refuses to jump straight to code. It interviews you (`brainstorming`), turns the conversation into a living design spec, breaks that into tasks an executor can own from one self-contained brief (`writing-plans`), then executes each one through a fresh subagent, reviewed at dependency frontiers — spec compliance, then code quality (`subagent-driven-execution`). You approve the design; independent reviews gate the rest.

**Autonomous** — for work that's already well-scoped.
A single self-contained plan (`execplan`) front-loads every decision so the agent can run to the letter without mid-flight questions. At larger scale, the board loop takes over: tickets live as GitHub issues and gated workers pick them up and build (`issue-tracker`), a review loop lands the PRs (`qa-loops`), and the fleet of durable background sessions doing it is one registry of seats (`sminos`). Product feedback can even feed the board directly (`triaging-feedback`).

---

## Install

### Claude Code

doperpowers ships as a Claude Code plugin from a self-hosted marketplace in this repo. It installs side by side with anything else you have.

```text
/plugin marketplace add SSFSKIM/doperpowers
/plugin install doperpowers@doperpowers
```

> Add it with the `owner/repo` form above, not a raw URL to `marketplace.json`. The plugin's source is the repo root, so Claude clones the whole repository for that path to resolve.

Update later:

```text
/plugin marketplace update doperpowers
/plugin install doperpowers@doperpowers
```

Full details, including how it coexists with other marketplaces: [`docs/INSTALL-doperpowers.md`](docs/INSTALL-doperpowers.md).

### Codex

A Codex plugin manifest ships in [`.codex-plugin/`](.codex-plugin/) for local installs. (The external sync to the Codex plugins repository was retired in v7.23.0; the script lives in git history if ever needed again.)

---

## The skills

Twenty-two skills, grouped by what they're for. Each one auto-triggers from its description; you rarely name them yourself.

**Shape the work**
- `brainstorming` — Socratic design refinement before any code is written
- `architecture-mapping` — author and maintain ARCHITECTURE.md, the repo's spine map with citable invariants
- `domain-modeling` — pin down the ubiquitous language, map bounded contexts, record ADRs
- `decomposing` — carve a large goal into a tree of well-scoped tickets
- `writing-plans` — break a spec into tasks an executor can own from one brief: files, interfaces, deliverables, tests, decisions
- `organizing-sprints` — turn a pile of raw observations into the next sprint
- `transcribing-meeting-recordings` — diarized, visually grounded transcripts from meeting recordings

**Build it**
- `test-driven-development` — RED → GREEN → REFACTOR, no code before a failing test
- `subagent-driven-execution` — one fresh subagent per task, reviews at dependency frontiers
- `execplan` — the autonomous single-plan track, gates front-loaded

**Keep it honest**
- `systematic-debugging` — four-phase root-cause process, not guess-and-check
- `review-code` — the Claude-native code-review path: effort-routed to registered reviewer agents on GPT through the local gateway (low/medium/high) or a multi-lens panel workflow (xhigh/max)
- `codex-companion` — drive OpenAI Codex models for independent reviews and delegated work
- `codex-migration` — move a Claude Code session into Codex as a resumable, app-visible thread (manual `/codex-migration`)

**Run it unattended**
- `issue-tracker` — the board, backed by GitHub issues, plus the execution loop that dispatches Architect and Executor workers onto tickets (gate before building; the design lane authors the plan)
- `qa-loops` — the autonomous PR-review and self-merge loop
- `sminos` — the fleet registry: seats (durable background sessions with a role, in a group), spawn/wake/attach, topology, and the group board

**Deployed alongside, not a skill**
- `application-agents/triaging-feedback/` — the feedback→triage poller: turns product feedback into grounded board tickets

**Extend it**
- `writing-skills` — create and test new skills that shape agent behavior

**Output style**
- `to-human` — for a session whose human reads a report stream rather than the transcript: the agent wraps what the human should read in `<to-human>` (what is essential in `<essential>`, input it needs in `<need-input>`) and a reader shows only that; explanatory insights kept. Select per launch with `"outputStyle": "to-human"`.

---

## How the controlled track flows

1. **brainstorming** — Activates before writing code. Refines rough ideas through questions, explores alternatives, presents the design in sections short enough to actually read.
2. **writing-plans** — Breaks the approved design into tasks an executor can own from one brief, every one with exact file paths, the interfaces it consumes and produces, the behaviors its tests assert, and the decisions already settled — code only where the code is a decision.
3. **subagent-driven-execution** — Sets up an isolated checkout, dispatches a fresh subagent per task, reviews at dependency frontiers, and fixes by resuming the executor. After the final review it writes the spec's retrospective and integrates the branch.
4. **test-driven-development** — Enforces the RED-GREEN-REFACTOR cycle throughout and deletes any code written before its test.

These are mandatory workflows, not suggestions. The agent checks for a relevant skill before any task.

---

## Philosophy

- **Design before code** — understand the problem before proposing a solution.
- **Test-driven** — write the failing test first, always.
- **Systematic over ad-hoc** — a repeatable process beats guessing.
- **Simplicity as a goal** — the minimum that solves the problem, captured with all its real complexity.
- **Evidence over claims** — verify before declaring anything done.

---

## Contributing

This is a personal fork, tuned to how its maintainer actually works. Skills are behavior-shaping code, not prose — changing one changes what the agent does, so use the `writing-skills` skill and test the change before relying on it. Issues and ideas: [github.com/SSFSKIM/doperpowers/issues](https://github.com/SSFSKIM/doperpowers/issues).

## License

MIT — see [`LICENSE`](LICENSE). Attribution for the upstream work this derives from is recorded in [`NOTICE`](NOTICE) and [`LICENSE-FORK`](LICENSE-FORK).
