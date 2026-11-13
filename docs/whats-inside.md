# What's inside

Everything the `doperpowers`, `sminos` and `to-human` plugins install, by what it is for. Skills trigger from their own descriptions; the ones marked *manual* run only when you type their slash command. The marketplace also carries `devcloud`, `web` and `ci-kit`, each documented in its own directory.

## doperpowers: skills

**Shape the work**

| Skill | What it does |
|---|---|
| [`brainstorming`](../skills/brainstorming/SKILL.md) | Before any creative work: explores what the work should be, grills you in batched rounds until nothing is silently assumed, presents the design, and routes it: built here, or handed to `execspec` |
| [`execspec`](../skills/execspec/SKILL.md) | Turns an approved design into the living spec (design, acceptance, plan of work as milestones, the record), reviews it, and runs it |
| [`decomposing`](../skills/decomposing/SKILL.md) | Splits a goal too big for one agent into child goals (a roadmap), and tends the tree as children land |
| [`architecture-mapping`](../skills/architecture-mapping/SKILL.md) | Writes and maintains a repo's `ARCHITECTURE.md`, the map sessions read before asking where things live |
| [`organizing-sprints`](../skills/organizing-sprints/SKILL.md) | *Manual* (`/organizing-sprints`). Turns a pile of raw observations (an idea dump, a walkthrough, a meeting transcript) into the next sprint, checked against the code |
| [`transcribing-meeting-recordings`](../skills/transcribing-meeting-recordings/SKILL.md) | *Manual* (`/transcribing-meeting-recordings`). Turns meeting or screen recordings into a diarized, visually grounded transcript, the input of `organizing-sprints` |

**Build it**

| Skill | What it does |
|---|---|
| [`test-driven-development`](../skills/test-driven-development/SKILL.md) | Red, green, refactor for any testable logic: the failing test comes first |
| [`subagent-driven-execution`](../skills/subagent-driven-execution/SKILL.md) | Runs a spec with several milestones: a fresh executor per milestone, reviews at dependency frontiers, fixes by resuming the executor, then the retrospective and the merge |

**Check it**

| Skill | What it does |
|---|---|
| [`review-code`](../skills/review-code/SKILL.md) | Independent review of a committed branch by another model family, routed by effort: one reviewer (low, medium, high) or a multi-lens panel with one binding verifier (xhigh, max) |
| [`codex-companion`](../skills/codex-companion/SKILL.md) | *Manual* (`/codex-companion`). Hands a review, a diagnosis or an implementation to OpenAI's Codex |
| [`present`](../skills/present/SKILL.md) | *Manual* (`/present`). An HTML explainer that leaves you understanding something end to end: work an agent shipped, a design, a spec, someone else's code |

**Keep the work going**

| Skill | What it does |
|---|---|
| [`issue-tracker`](../skills/issue-tracker/SKILL.md) | The board as a backlog, in GitHub issues or an Arkho board service: register, search, take the ticket you name, close it out |
| [`kairos`](../skills/kairos/SKILL.md) | *Manual* (`/kairos`, `/kairos off`). Proactive mode: the agent takes the next sound step without waiting for a go, and stops only at a real fork |
| [`writing-skills`](../skills/writing-skills/SKILL.md) | Writing and pressure-testing any authored agent behavior: a skill, an agent definition, a prompt for other agents |

## doperpowers: agents

Registered as `doperpowers:<name>` and dispatched by the skills above; you rarely call them yourself.

| Agent | Model | Role |
|---|---|---|
| [`reviewer-low`](../agents/reviewer-low.md) | sol, high | `review-code`'s low rung: a small, low-stakes diff |
| [`reviewer-medium`](../agents/reviewer-medium.md) | sol, xhigh | The default rung for a focused diff |
| [`reviewer-high`](../agents/reviewer-high.md) | astra, high | A focused diff whose stakes warrant the frontier model |
| [`adversarial-reviewer`](../agents/adversarial-reviewer.md) | astra, high | Tries to break confidence in a design, spec or change along a named focus |
| [`critique`](../agents/critique.md) | fable, xhigh | Attacks a matured design and its reasoning, then debates the session until the disagreement converges |
| [`plan-executor`](../agents/plan-executor.md) | opus, high | Runs a spec's plan of work on behalf of the session that wrote it |
| [`task-executor`](../agents/task-executor.md) | opus, high | Builds one milestone inside `subagent-driven-execution` |
| [`task-reviewer`](../agents/task-reviewer.md) | sol, xhigh | Reviews one milestone inside `subagent-driven-execution` |

`sol` and `astra` are another model family, served to its maintainer through a local gateway; elsewhere, change the `model:` lines in the agent definitions and the `LADDER` in [`review-code`'s panel workflow](../skills/review-code/workflows/code-review.js), which pins them itself (its `deriverModel`, `finderModel` and `verifierModel` arguments override a lane per call). Reviewers are read-only and cannot start a review of their own.

## doperpowers: hooks

Shell hooks run everywhere. The function hooks (mods) load only under `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`; their design notes are in [`hooks/mods/README.md`](../hooks/mods/README.md).

| Hook | What it does |
|---|---|
| compact tool | `mcp__doperpowers__compact`: the model compacts its own context at a checkpoint it chooses, and is offered the chance as the context grows past 300k tokens |
| compaction note | Every compaction's summary is written as the note a reset self resumes from |
| kairos | The proactive mode's switch, kept across compaction and resume, with a button in the prompt footer |
| appeal | In auto mode, contests a block the agent thinks was wrong before an independent judge |
| interim filter | Drops the completion notices a subagent sends while its own background work still runs, which otherwise cost the parent a turn each |
| reload | Applies a plugin update another process installed to the running session once it is idle |
| fork guard | Keeps the read-only question forks the session manager asks through read-only |

## doperpowers: output style

[`to-human`](../output-styles/to-human.md), selected with `"outputStyle": "doperpowers:to-human"`, is for a session whose human reads a report instead of the transcript. The agent sends every message through `mcp__to-human__message`, opens with a critical notice when work was lost, degraded or blocked, explains its implementation choices briefly, and asks through the async question tool.

## sminos

The project family, standalone: nothing of doperpowers' is needed for it to run. Its [README](../sminos/README.md) covers installation and where everything lives.

| Part | What it does |
|---|---|
| [`sminos` skill and CLI](../sminos/skills/sminos/SKILL.md) | Who is here (`list`, `find`, `who`), speaking (`say`, `send`), driving another session (`watch`, `steer`, `interrupt`, `answer`, `decide`, `model`, `compact`), spawning and retiring background sessions (`spawn`), and a project's and machine's setup |
| [`manager` skill](../sminos/skills/manager/SKILL.md) | *Manual* (`/sminos:manager`). A read-only manager session: follows the sessions you name and tells you what they need from you and what you missed, in a ledger |
| bridge | Makes a session watchable and steerable from outside it: its live stream for a reader, its control for a client |
| ask tool | `mcp__sminos__AskUserQuestion`: the built-in question tool plus `async`, so a session asks and keeps working |
| address | Ends every commit and PR a session writes with its `Sminos-Session:` line, which `sminos who` reads back |
| names | Renames a session with a generated name after what it is in charge of, its line derived again after each compaction |
| daemon | Syncs a project's log across machines, through a git mirror or the desk hub (over RL10, through the machine's MAWS endpoint) |

## to-human

The report view for sessions under the `to-human` output style; it installs `sminos` with it.

| Part | What it does |
|---|---|
| message tool | `mcp__to-human__message`: how a message reaches the human, mid-turn or at the turn's end; `final: true` ends the turn with no request after it |
| report view | Folds each response to its messages and the working record (tool calls, scratch notes, other sessions' messages) behind one button per stretch, which reads the newest tool call while the stretch runs and a one-line summary of it (by Haiku) once it closed |
| `/to-human-dump` | Writes the report view's state (its rows' order, kinds and places, its unfolded runs, the versions) to a file under `to-human/dumps/` in the configuration directory, for a fold drawn wrong |
| edit folding | A run of file edits draws as one line, `Edited build.py +3 -1, created notes.md +12 ›`, unfolding on a click |
| notifications | Each message raises a notification through your own notification hooks |
| reminder | Puts the rule for sending back in front of the model in long contexts |

## Not loaded by any harness

- [`application-agents/triaging-feedback/`](../application-agents/triaging-feedback/): turns product feedback into grounded board tickets; deployed separately, none runs today.
- [`archive/`](../archive/): retired skills and agents, kept for reference with a note on where their surviving rules went.
- The board's automatic dispatch (the sweep, the dispatchers, the worker protocols) stays in `skills/issue-tracker/`, tested and armed nowhere since [2026-10-18](doperpowers/specs/2026-10-18-board-dispatch-dormant.md).
