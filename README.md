# doperpowers

**A methodology your coding agent actually follows** — not a pile of prompts, but a set of skills that trigger themselves at the right moment and keep the agent honest from first idea to merged branch.

```text
                          d o p e r p o w e r s

   what you're building  ─┬─▶  CONTROLLED  · you sign off at every gate
                          │      brainstorm → spec → plan → subagent-TDD → review → ship
                          │
                          └─▶  AUTONOMOUS  · it runs while you're away
                                 board → dispatch → build → review → merge
```

Most agent scaffolding is a single linear pipeline: you talk, it plans, it codes. doperpowers splits that in two. When the work needs your judgement, the **controlled track** shows you the design in readable chunks and stops for your approval at each seam. When the work is well-scoped and delegable, the **autonomous track** takes a ticket off the board and drives it to a reviewed pull request without waking you up. The skills route between the two based on what you actually asked for.

Because every skill declares when it applies, you don't invoke any of this by hand. The agent checks for a relevant skill before it starts a task, and the right workflow just happens.

---

## Two tracks, one discipline

Both tracks enforce the same non-negotiables — design before code, tests before implementation, evidence before "done." They differ only in where the human sits.

**Controlled** — for work where taste and intent matter.
The agent refuses to jump straight to code. It interviews you (`brainstorming`), turns the conversation into a living design spec (`execspec`), breaks that into tasks small enough for an unsupervised junior to follow (`writing-plans`), then executes each one through a fresh subagent with two-stage review — spec compliance, then code quality (`subagent-driven-development`). You approve each gate.

**Autonomous** — for work that's already well-scoped.
A single self-contained plan (`execplan`) front-loads every decision so the agent can run to the letter without mid-flight questions. At larger scale, the board loop takes over: tickets live as GitHub issues (`issue-tracker`), workers pick them up and build (`implementing-tickets`), a review loop lands the PRs (`reviewing-prs`), and durable background sessions keep it all running (`orchestrating-daemons`). Product feedback can even feed the board directly (`triaging-feedback`).

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

A Codex plugin manifest ships in [`.codex-plugin/`](.codex-plugin/) and is distributed to the Codex plugins repository by [`scripts/sync-to-codex-plugin.sh`](scripts/sync-to-codex-plugin.sh). This is a maintainer sync, not a public marketplace search — run the script to publish a new version.

---

## The skills

Twenty-one skills, grouped by what they're for. Each one auto-triggers from its description; you rarely name them yourself.

**Shape the work**
- `brainstorming` — Socratic design refinement before any code is written
- `execspec` — living design specs: decision log, rejected alternatives, retrospective
- `codebase-design` — deep-module interface design and where to put a seam
- `domain-modeling` — pin down the ubiquitous language and record ADRs
- `writing-plans` — break a spec into bite-sized, exactly-specified tasks
- `organizing-sprints` — turn a pile of raw observations into the next sprint

**Build it**
- `test-driven-development` — RED → GREEN → REFACTOR, no code before a failing test
- `subagent-driven-development` — one fresh subagent per task, two-stage review
- `executing-plans` — batch execution with human checkpoints
- `execplan` — the autonomous single-plan track, gates front-loaded
- `dispatching-parallel-agents` — fan independent work out concurrently
- `using-git-worktrees` — isolated workspaces so parallel work never clashes

**Keep it honest**
- `systematic-debugging` — four-phase root-cause process, not guess-and-check
- `verification-before-completion` — run the check, show the output, then claim success

**Run it unattended**
- `issue-tracker` — the board, backed by GitHub issues
- `implementing-tickets` — dispatch workers onto tickets, gate before building
- `reviewing-prs` — the autonomous PR-review and self-merge loop
- `orchestrating-daemons` — durable background sessions that survive the session ending
- `triaging-feedback` — turn product feedback into grounded board tickets
- `finishing-a-development-branch` — verify, then decide merge / PR / keep / discard

**Extend it**
- `writing-skills` — create and test new skills that shape agent behavior

---

## How the controlled track flows

1. **brainstorming** — Activates before writing code. Refines rough ideas through questions, explores alternatives, presents the design in sections short enough to actually read.
2. **using-git-worktrees** — Activates after design approval. Creates an isolated workspace on a new branch and verifies a clean test baseline.
3. **writing-plans** — Breaks the approved design into tasks of a few minutes each, every one with exact file paths, complete code, and verification steps.
4. **subagent-driven-development** / **executing-plans** — Dispatches a fresh subagent per task with two-stage review, or runs in batches with human checkpoints.
5. **test-driven-development** — Enforces the RED-GREEN-REFACTOR cycle throughout and deletes any code written before its test.
6. **verification-before-completion** — Before anything is called done, runs the check and shows the output; evidence, not assertions.
7. **finishing-a-development-branch** — Verifies tests, presents merge/PR/keep/discard, cleans up the worktree.

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
