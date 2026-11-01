# Session manager — a read-only briefing session over the sessions doing the work

The owner runs initiatives that last days and span several sessions at once. P5 (the desk folded into MAWS) ran across "GUI AI agent workspace charter" (`37052769`, project MAWS), `p5-desk-track-owner` (`b4948247`) and `CI-opt` (`a45b97a3`, both project doperpowers), and early on `remote-architecture`. Coming back after hours away, the work has moved far, messages have stacked up in every session, and finding what is owed to whom means scrolling back through each one. What gets lost is the owner's side of the work: questions, decisions, judgments and actions the sessions are waiting on, blocking or not.

After this change the owner keeps one **manager session** open: a Claude session that has loaded the `/sminos:manager` skill. They tell it which sessions to follow and under which initiative, and whenever they come back they ask "update since 9am". It answers with what needs them first (blocking items, then optional ones, then older items still open) and then a written brief per initiative. They can ask follow-up questions, which it answers from the records, from the sessions' transcripts, or by putting the question to a fork of a session. The manager never writes to a working session, so the work it reports on is never interrupted or changed by it.

To see it working: open a new Claude session in any directory on the MacBook, run `/sminos:manager`, say "subscribe P5: GUI AI agent workspace charter, p5-desk-track-owner, CI-opt", then "update since 10 hours ago". The briefing names, for example, the PR merge a session asked you to decide and the `dasd` restart only you can do, each with the session, the time and the message it came from.

This is the semantic half of MAWS's Scene A ("Open MAWS and know within seconds where you are needed", `MAWS/docs/charter.md` §1). MAWS's attention table already covers the mechanical half (a pending permission prompt, a pending question). What sessions *said* they need from the owner, in prose, has no reader today.

A side effect ships with it: `sminos derive`, which forks a session every six hours to learn its in-charge line, moves onto the bridge's cached side question for live sessions and becomes about seven times cheaper.

## Progress

- [x] (2026-11-01 01:40Z) Design approved in the authoring session (doperpowers-9b, f89d7fb0); spec written.
- [x] (2026-11-01 05:10Z) Independent spec review and buildability review: two rounds, converged (Decision Log).
- [x] (2026-11-01 03:30Z) Fork-agent spike: an in-session fork started by a mod reads the session's cache, runs read-only tools under a guard in another plugin, and leaves the session untouched (Surprises & Discoveries).
- [x] (2026-11-01 03:29Z) M1 — the `manager` command: transcript windows, pending items, subscriptions. Reviewed clean after two fix rounds; `sminos`, `sminos-suites` green on 3e93e0f1.
- [ ] M2 — the bridge's `ask` (an in-session fork agent) and the read-only guard.
- [ ] M3 — the shared fork code in sminos: `derive` on `btw`, `manager query` on `ask` with the headless fallback.
- [ ] M4 — the skill, the digest brief, the replay evaluation, versions, and acceptance.
- [ ] Whole-branch review (review-code, high), retrospective, merge.

## Terms

- **Session, member.** A Claude Code session. sminos calls every session in a project a *member*; it is named by an alias (`CI-opt`), its short id (first eight hex digits), `@project/alias`, or its full UUID. A member can continue under new session ids (a resumed seat); sminos follows that chain as its *lineage*.
- **Transcript.** The engine's JSONL file for a session, `~/.claude/projects/<dir>/<session>.jsonl` (or under another config dir, which sminos records). The P5 sessions' transcripts are 283–668 MB each.
- **Host events.** What sessions sent their human, recorded by sminos: `message` (a call of `mcp__to-human__message` or a `<message>` span), `question` (an async `mcp__sminos__AskUserQuestion`) and `answered`. Read with `sminos chat <project> --host`.
- **Mod.** A TypeScript module a plugin loads into every session's process (`hooks/mods/*.tsx` in a plugin), with hooks on the engine's events and calls into its API (`$`). Types: `<plugin>/.claude-plugin/types/claude-code/index.d.ts`.
- **Bridge.** The sminos mod running inside every session (`sminos/hooks/mods/bridge.tsx`), reachable on this machine at `$SMINOS_HOME/bridge/<session>.sock`. It serves the desk's controls, among them `btw`, and after this change `ask`.
- **`btw` (side question).** A bridge op: one tool-less completion over the session's own last request (`$.model.fork`), with a question appended. It writes nothing into the conversation, runs beside a running turn, and is invisible in the session (`sminos/hooks/mods/bridge-btw.tsx`).
- **Fork agent, `ask`.** A new bridge op: the bridge starts a forked subagent inside the session (`$.agent.spawn({ subagentType: 'fork' })`), which inherits the session's conversation and model, so its requests read the session's prompt cache. It can use tools, runs in the background beside the session's turn, and its answer comes back to the bridge, never into the session's conversation.
- **Read-only guard.** A mod in the doperpowers plugin (`hooks/mods/fork-guard.tsx`) that limits a sminos fork agent to reading files and read-only shell commands, refusing everything else, and refuses when in doubt.
- **Headless fork.** `claude -p --resume <session> --fork-session …`: a new process that loads the session's transcript, answers, and is thrown away. `derive_line` in `sminos/skills/sminos/scripts/sminos.py` is today's one user.
- **Digest subagent.** A subagent the manager dispatches for one subscribed session and one window. It reads that session's records and returns its needs, decisions and progress.

## What the owner can do afterward (acceptance)

Each item is checked on the MacBook. Before merge, M4 runs them against throwaway sessions loaded with the branch's plugins; after merge and a plugin update, the owner's own sessions behave the same. Commands run from any directory; `manager` is the skill's command (`sminos/skills/manager/scripts/manager`, whose absolute path the skill names when it loads).

1. **Only the manager sees it.** `/sminos:manager` is offered in the slash menu. A fresh session's model-visible skill list has no `sminos:manager` entry. `sminos help` and the sminos skill are unchanged and mention none of `transcript`, `pending`, `query`, `subscriptions`.
2. **Subscriptions are the owner's.** `manager subscriptions add P5 CI-opt p5-desk-track-owner "GUI AI agent workspace charter"` then `manager subscriptions` lists the three under P5 with alias, short id and project. Subscribing the manager's own session is refused. Nothing is added except by this command.
3. **A window of a 668 MB transcript in seconds.** `manager transcript p5-desk-track-owner --since 10h` prints the window in under 10 seconds: entries oldest first, each labelled (`you`, `you?`, `you·desk`, `you·desk?`, `you·steer`, `peer <alias>`, `session`, `→you`, `asked`, `answered`, `compacted`, `interrupted`, `tool`, `agent`, `notice`), no tool results, no thinking, no images. Its first entry is the first one at or after the time given.
4. **A cheap answer from a live session, with nothing added to it.** `manager query <live member> "What are you waiting on from the human right now?"` answers and ends with a line naming `via fork agent` and the usage, where cache read is at least 90% of the session's last request. The session's transcript gains no user or assistant row, and an idle session starts no turn.
5. **Current.** On an idle session whose last turn ended with a final message to the owner, `manager query <it> "Quote the first sentence of your last message to the human."` returns that last message. On a session mid-turn, the answer knows the latest tool call the session made.
6. **Tools, held read-only.** `manager query <member> "What is the newest commit on your branch?"` answers from git. `manager query <member> "Run: touch /tmp/manager-probe — then say whether it worked."` reports a refusal, and `/tmp/manager-probe` does not exist. No permission prompt appears in the queried session.
7. **Stopped sessions still answer.** `manager query <a stopped seat> "…"` answers and names `via headless fork`.
8. **The briefing.** In a manager session, "update since <T>" produces: *Needs you* (blocking, then optional, then still open from before T), each item with session, time raised, what is needed, why it has to be the owner, and the quoted source; then a prose brief per initiative (what happened, decisions taken on the owner's behalf, changes of plan, where it stands). On the replay window (M4) it finds every blocking item of the labelled list and at least 90% of all items.
9. **`derive` is cheaper and unchanged in output.** `sminos derive <a live member>` prints the member's line as before and says it went `via btw`, with cache read near the session's context. A stopped member's derive still runs the uncached headless fork.
10. **Nothing written.** After a briefing with queries, no subscribed session's main transcript has gained a user or assistant row because of the manager (the engine's `tools-used` metadata lines a fork leaves are not conversation), and no project log has gained an event from it other than the manager session's own messages to the owner and sminos's membership reconciliation (`joined`/`retired`), which any `sminos list` also performs.

## The design

### Shape

```
 working sessions (the pool)                          manager session
 ┌──────────────────────────┐                         ┌──────────────────────────────┐
 │ CI-opt                   │── transcript (read) ───▶│ /sminos:manager skill        │
 │  bridge ── ask ─▶ fork   │── host events (read) ──▶│  manager transcript|pending  │
 │  agent (read-only guard) │◀─ ask: a question ──────│  manager query               │
 └──────────────────────────┘◀─ headless fork ────────│  digest subagents (Sonnet)   │
   (stopped sessions only)                            └──────────────────────────────┘
```

Every arrow into a working session is a fork: the session's conversation is never appended to, its turn never interrupted, its files never touched by the manager.

### Packaging: a skill only the owner can load, with its own command

The manager is a second skill in the sminos plugin, `sminos/skills/manager/SKILL.md`, whose front matter sets `disable-model-invocation: true`. That field keeps a skill out of every model's skill list and leaves it in the slash menu: the designer plugin's `materialist` skill sets it, and it is absent from a session's listed skills. Its command, `manager`, lives in `sminos/skills/manager/scripts/` beside it and imports sminos's Python modules from `sminos/skills/sminos/scripts/`.

Why: `transcript`, `query` and the rest are needed by the manager alone. As sminos verbs they would sit in `sminos help` and in the sminos skill that every session reads, costing every session context and inviting sessions to fork each other. The strongest alternative, a separate plugin, lost because the command imports sminos's internals, and a plugin reaching into another plugin's versioned cache directory breaks at every update. What sminos and the manager share is internal and adds no verb: the fork code in `sminos/skills/sminos/scripts/sminos_fork.py`, which `derive` uses too, and the bridge's new `ask` op (§Queries), which appears in the bridge's capabilities, not in `sminos help`.

### Subscriptions and the manager's state

The owner names the sessions to follow and the initiative each belongs to. The manager may suggest sessions (from in-charge lines, or sessions that message each other or name the same work) but subscribes none on its own. A subscription records the member's session id at the time and follows its lineage, so a seat that continued under a new id stays followed.

State lives in `$SMINOS_HOME/managers/<name>.json` (default name `default`; `--name` picks another for a second manager). It holds the subscriptions and the **carry list**: the items the last briefing left open, each with its session and source, so the next briefing rechecks them. Keeping these in a file, not only in the manager's conversation, means a compaction or a fresh manager session loses nothing; see the Decision Log entry of 2026-11-01.

### The briefing

The owner asks for an update since a time (`9am`, `10h`, an ISO time; local time). The manager:

1. Runs `manager pending` for the mechanical signals across every subscription: async questions with no answer (any age) and sessions in the `waiting` state (a permission prompt or a native question on screen).
2. Dispatches one digest subagent per subscribed session, in parallel, each with its member, the window, that session's carry-list items and the digest brief (`sminos/skills/manager/references/digest-brief.md`).
3. Merges their reports and writes the briefing; updates the carry list.

The briefing, in this order:

- **Needs you.** Blocking first, then optional, then *older*: items raised before the window and still open. Each item: session (alias), when raised, what exactly is needed, why it has to be the owner, and a short quote of the source with its time.
- **A written brief per initiative.** Prose: what happened, the decisions sessions took on the owner's behalf, where plans changed, where things stand now.

**Blocking** means some work is stopped, or will stop, until the owner acts: a question the session waits on, a password, login or permission, a merge or publish gate the session will not pass on its own, an explicit "waiting on you". **Optional** is everything else the owner is asked for: offers the session parked ("If you'd rather see the cost first, I can measure it on the mini"), confirmations deferred to pickup, defaults chosen pending the owner's word. The to-human style makes sessions put every place they need the owner in italics; in the Oct 29–31 sample 231 of 377 messages carried such spans, which makes them the digest's first lead, not its only one.

An item's status:

| Status | When |
|---|---|
| answered | its question has an `answered` event, or the owner's words after it in that session (typed, sent from the desk, or a steer) address it; when the only evidence is an unverified row (`you?`, `you·desk?`), the briefing says "answered (unverified)" and quotes it |
| overtaken | the session moved on without the owner: decided it itself, dropped it, or the need went away |
| open | anything else |

When the records leave the status unclear, the digest subagent asks the session through `manager query`.

**Digest subagents run on Sonnet.** Effort is medium or high, whichever the replay evaluation (M4) shows is enough; the skill states the one chosen. They are dispatched with the Agent tool as general-purpose subagents briefed from the reference file, not as a registered agent definition, which would be listed to every session and undo the packaging.

**Strictly read-only.** The manager and its subagents never send, steer, interrupt, answer, decide, compact, change a model, or write to a project log. Its only outward acts are its messages to the owner. This is a rule the skill states, not a lock: the manager needs its own tools to read, and nothing so far suggests a model breaks the rule.

**On demand only.** Nothing runs between the owner's requests: no schedule, no pushes.

### Transcript windows

A session's transcript is far too large to read as a whole (P5's are 283–668 MB, about 15 MB of prose each), so `manager transcript` returns a **condensed window**: what the owner and the session said and did, without what tools returned.

Kept, oldest first: the owner's prompts (labelled by source: typed `you`, from the desk `you·desk`, a steer `you·steer`; a row that reads as typed but whose provenance the transcript does not record is `you?`, unverified), messages from other sessions (`peer <alias>`), the session's prose (`session`), its messages to the owner (`→you`, whole), its questions with their options (`asked`) and answers (`answered`), compaction summaries (`compacted`), interrupts (`interrupted`), one line per tool call (`tool`: name and a short argument), each subagent spawn with its description and the first lines of its result (`agent`), and one line per task notification (`notice`). Left out: tool results, thinking, images, system reminders and attachments.

The window starts at the first row at or after `--since` (and stops at `--until`), found by binary search on the rows' timestamps, never by reading the file from its start. It walks the member's lineage in order, marking where one session id ends and the next begins. Output is text by default and `--json` for scripts; past `--max-chars` (default 400,000) it stops with a line saying where it stopped and how to narrow the window.

The row classification is the part most likely to be subtly wrong (a peer's delivery read as the owner's words would invent instructions the owner never gave), so it reuses sminos's existing readers of these frames wherever they exist (M1 names them) and is pinned by fixtures of every frame kind.

### Queries

`manager query <member> "<question>"` puts a question to a fork of the session and prints the answer and its cost. There is one interface for a live session and one fallback:

| Path | When | Tools | Cache |
|---|---|---|---|
| **fork agent** (`ask` through the bridge) | the session is live and its bridge offers `ask` | the session's own, held read-only by the guard | reads the session's cache: 99.9% of the last request on the fork's first request (spike, haiku, ~27k tokens) |
| **headless fork** | the session is not running, or its bridge cannot run a guarded fork agent (no `ask`, or refused `no-guard`) | Read, Grep, Glob, Bash under `--permission-mode auto` | cannot read the session's cache: ≈$0.40 per 100k tokens on the first question; caching on, a repeat within the hour reads the fork's own entry (measured $0.02 at ~88k) |

**Why a fork agent.** The owner asked for one call that keeps the cache, has tools, stays read-only, and interrupts nothing. Three mechanisms were measured against that:

- **`btw`** (`$.model.fork`) reads the session's whole cache and is invisible, but it is one completion with every tool denied, the plugin API cannot continue it with tool results, and it replays the session's *last request*: on an idle session it misses the turn's final response, usually the final message to the owner. Two consecutive `btw`s on the authoring session both stopped at the request before the one in flight.
- **A headless fork** (`claude -p --resume --fork-session`) has tools but never reads the session's cache: `claude -p` builds a different system prompt and tool list from the interactive session (safe mode drops the plugins; to-human's message tool registers only interactively), and the prompt cache matches tools, then system prompt, then messages, as one exact prefix. Four variants read 0 or 10,334 tokens of a ~100k conversation.
- **A fork agent** (`$.agent.spawn({ subagentType: 'fork' })` from the bridge) inherits the session's conversation and model, so its first request read 99.9% of the session's last request from cache; it runs the session's tools; and in the spike nothing entered the session's conversation, no notification was delivered, an idle session started no turn, a running `sleep 20` finished on schedule, and the session's requests during the fork carried nothing about it. Its answer reaches the spawning mod through `turn.complete`, matched by the agent's id.

So a live session is asked through the fork agent; the headless fork remains for sessions that are not running, where there is no process to fork inside, and for a live session that cannot run a guarded fork agent (an older sminos, no guard loaded).

**Freshness.** An idle session's fork agent sees the whole conversation, the last response included. Mid-turn, it sees the conversation up to the main loop's last request (the response in flight and its tool calls are not yet the fork's context). So when the main loop is mid-turn the bridge adds, under the question, the main-loop messages kept after that request, rendered as text (assistant text, tool calls with their arguments, tool results cut short), the newest kept when the rendering passes 32 KiB. An idle session gets no tail.

**Read-only.** The fork agent inherits the session's tools and permission mode, so read-only has to be enforced, not asked for: a fork carries the session's whole task in its context, and forks have been measured continuing the open task when not told otherwise (the `btw` frame exists for that reason, `bridge-btw.tsx`). The guard enforces it in two layers, both in a plugin whose hooks see the fork's calls (below):

- **At `tool.call`, a fixed tool surface.** A fork may call `Read`, `Grep`, `Glob` and `Bash`, nothing else. `isReadOnly` alone is not an effect boundary: the engine marks `Agent` read-only (the spike's guard log records it), and its contract warns that sending and delegating tools can claim the flag, so a fork that spawned a general-purpose child would escape a guard keyed on forks. And `tool.check` comes too late for plugin tools: a plugin can serve its tool inside its own `tool.call` hook without ever reaching `tool.check` (the web plugin's fetch writes its cache that way, for subagents too). So the surface is decided at `tool.call`, ahead of every user-tier plugin's handler, by name.
- **At `tool.check`, read-only Bash.** A `Bash` call runs only when the engine marks that input `isReadOnly`; the guard answers `allow` for it, so a fork never raises a permission prompt in the working session, and `deny` otherwise, which overrides both the core's `allow` and its `ask`. Measured: Read, `ls`, `cat`, `echo`, `sleep` ran; Edit, Write, `touch`, a `>` redirect and a Python write were refused; nothing was written.

The guard fails closed. The engine skips a hook that throws, overruns its budget or answers an invalid shape, and runs what is beneath it, which for a fork would be the session's ordinary permissions; so each guard registration carries a `.catch` that refuses, and a subagent call made while the agent list cannot be read (it rejects, or answers something not a list) is refused rather than passed. An id the list does not name passes: the engine gives a workflow's agents and its own forks (compaction, memory) ids no list names, and a fork the bridge spawns is listed from its spawn on (Decision Log, 2026-10-31).

**The guard lives in another plugin.** A subagent a mod spawns from outside a hook (the bridge spawns from its command listener) bypasses every hook of the spawning plugin; only its `turn.complete` reaches it. Spawned from inside a hook it bypasses only that hook. The bridge receives `ask` on its listener, never inside a hook (an idle session raises none), so the guard cannot be a sminos hook. It is a mod of the doperpowers plugin, `hooks/mods/fork-guard.tsx`, which acts only on agents whose `$.agent.list()` entry is `type: 'fork'` with `spawnedBy: 'sminos'`; every other agent of the session is untouched. The bridge refuses `ask` (`no-guard`) when it cannot confirm the guard is loaded in the session, so a session without doperpowers never gets an unguarded fork agent; `manager query` then takes the headless path. The alternative home, the to-human plugin (it already depends on sminos), lost because its purpose is how sessions talk to the owner, not what forks may do. Raising one of sminos's own hooks on purpose so the spawn happens inside a hook frame lost as a contortion that depends on undocumented event semantics.

**What the session's person sees.** The fork appears in the session's agent strip, `/tasks` and `$.agent.list()` while it runs, described as `manager query`, and the desk would show it too; it interrupts nothing. The engine also appends `tools-used` metadata lines to the session's transcript file, which the model never reads. The bridge spawns from its listener, never from a slash command, which would write two `local_command` user rows into the conversation.

**One at a time.** A session runs at most one `ask` fork; a second `ask` while one is open is refused (`busy`). Several forks at once, an Esc in the session during a fork, and a compaction during a fork were not exercised by the spike; one at a time keeps the untested surface small, and the M2 live check covers Esc and compaction.

**The headless fallback.** `claude -p --resume <session> --fork-session --session-id <new> --safe-mode --no-session-persistence --permission-mode auto --tools Read,Grep,Glob,Bash`, marked internal as `derive` marks its forks, caching on so follow-up questions within the hour are cheap. The owner chose auto mode over a `dontAsk` allowlist: auto mode refuses what it judges risky, not every write, so a harmless write such as `touch` would pass; read-only there rests on the frame, which the owner judged enough for a session that is not running.

**The frame.** Both paths put the question under the same frame, an exact string fixed in Interfaces: the fork is told it is a read-only fork started by the owner's manager to answer one question, that the session never sees the exchange, not to continue the session's task, that it may use read-only tools to check facts and that changes are refused, and to answer and stop.

### `derive` on `btw`

`derive_line` today always runs an uncached headless fork, deliberately: the fork cannot read the session's cache, and the next derive of the same session is six hours away, after any entry it wrote has expired. That costs full input price every time: one derive-style fork of the authoring session read 104,990 tokens for $0.42, and this Mac's daemon ran 39–77 derives a day over Oct 27–31. Derive only runs on sessions active in the last hours, whose cache is usually warm, so through `btw` the same question costs about a seventh ($0.06 measured for a 120k session). `derive_line` asks through `btw` when the member's bridge offers it, else runs the uncached headless fork it runs today. Its prompt, its parsing, its failure stamps and its timeouts stay as they are. `btw`, not the fork agent: derive needs no tools, `btw` is invisible in the session where a fork agent would show in its agent strip every six hours, and `btw`'s one-step lag does not matter to "what are you in charge of".

### What is left to measure

- Whether Sonnet at medium effort sorts blocking from optional as well as at high: the replay evaluation decides (M4).
- The fork agent on a session past 100k tokens (caching should not depend on length), under an Esc in the session, and across a compaction: the M2 live check, recorded in Surprises & Discoveries.
- How the bridge confirms the guard is loaded (M2, below).
- What one briefing costs, ten hours across four sessions: recorded during M4.

## Execution

### Constraints that bind every milestone

- **Read-only toward working sessions.** No code path of the `manager` command appends to a session's conversation, interrupts its turn, edits its files, or writes an event to a project log. It never runs, or calls the functions behind, sminos's `say`, `send`, `steer`, `interrupt`, `answer`, `decide`, `compact`, `model`, `charge`, `status` or a cursor-advancing `chat`. The one exception it inherits is sminos's own membership reconciliation, which any sminos read (`list`, `chat`, `find_target`) may perform.
- **This Mac only.** A member whose session runs on another machine is refused with a message naming the machine (`manager: CI-opt runs on mini; this version reads sessions on this machine only`). Cross-machine reading is out of scope.
- **sminos's conventions.** Detail beside code: the new skill's command gets its own `sminos/skills/manager/scripts/CLAUDE.md`; `sminos/CLAUDE.md` gains one sentence pointing at it; the bridge's and derive's notes in the existing nested CLAUDE.md files are updated where their behavior changes. No CLAUDE.md is placed where a loader reads every `.md`.
- **Tests run in isolation.** Every test isolates `HOME` and `SMINOS_HOME` as `sminos/tests/run-sminos-tests.sh` does; none touches the real `~/.claude/sminos` or a live session. Live checks run only against throwaway sessions with an isolated config (the M2 live check, the M4 acceptance run), never against the owner's sessions before merge.
- **Versions.** On the branch, one bump of the sminos plugin (`scripts/bump-version.sh --plugin sminos`) and one of the doperpowers plugin (`scripts/bump-version.sh`, for the guard), both in M4.
- **Verification.** Before a milestone is reported done: its tests pass locally (one focused file while iterating is fine), and `ci-gate` from the worktree is green on the committed HEAD for the gates its files touch: `sminos`, `sminos-suites`, `sminos-mods`, `mods-types`, and `mods` once the guard exists.

### Orientation

Paths below are repository-relative. The sminos CLI is `sminos/skills/sminos/scripts/sminos.py` with sibling modules in the same directory (`sminos_bridge.py`, `sminos_control.py`, `sminos_subagents.py`, `sminos_jobs.py`, …); its nested `CLAUDE.md` describes each. Sibling modules import it by plain name (`import sminos as S`) after putting the scripts directory on `sys.path` (`sminos_rpc.py` and `sminos_plane.py` show the pattern). The bridge mod is TypeScript under `sminos/hooks/mods/`. Tests: `sminos/tests/run-sminos-tests.sh` (a fake `claude` binary on `PATH`, `HOME` and `SMINOS_HOME` isolated; it has no discovery: each test file is called by name from `run_suites()`), and `sminos/tests/mods/run.sh` for the mods (`claude plugin test`).

### Interfaces and Dependencies

**Files (new).**

    sminos/skills/manager/SKILL.md                    # M4
    sminos/skills/manager/references/digest-brief.md  # M4
    sminos/skills/manager/scripts/manager             # M1: sh launcher, as sminos's own
    sminos/skills/manager/scripts/manager.py          # M1: the CLI
    sminos/skills/manager/scripts/manager_window.py   # M1: transcript window reader and row classifier
    sminos/skills/manager/scripts/CLAUDE.md           # M1, extended in M3 and M4
    sminos/tests/test_manager.py                      # M1, extended in M3

`manager.py` puts `realpath(<its dir>/../../sminos/scripts)` on `sys.path` and imports `sminos`, `sminos_bridge`, `sminos_subagents`. It never calls `sminos.main()`; it calls `sminos.forget_caches()` only if it ever runs more than one resolution per process.

**Commands.** Every command takes `--json`; text output is for the manager model to read, JSON for tests and scripts. Exit codes follow sminos's: 0 success, 1 failure with a message on stderr, 2 usage, 4 an unknown or ambiguous member (as `find_target` exits).

    manager transcript <member> --since T [--until T] [--max-chars N]
    manager pending [--until T] [--name N]
    manager subscriptions [--name N]
    manager subscriptions add <initiative> <member>... [--name N]
    manager subscriptions remove <member>... [--name N]
    manager carry [--name N]
    manager carry set (--file PATH | -) [--name N]

`T` is local time: `9am`, `14:30` (today; a clock time later than now means yesterday), a duration back from now (`10h`, `90m`, `2d`), or an ISO-8601 time.

**Member resolution.** The manager resolves names across every project on this machine, not only the project of the directory it runs in: subscriptions span projects (P5 is in MAWS and doperpowers) and the manager runs from any directory, while `sminos.find_target(q)` resolves a bare alias only in the caller's project (its cross-project fallback matches shorts alone). Order: a full uuid, a short, `alias#short` and `<project>/<alias>` go to `find_target` as they are; a bare alias goes to `find_target` first and, when that finds nothing, to an exact alias match among the local members of every known project (`sminos.members(project)` over the projects sminos knows); two or more matches exit 4 listing each as `<project>/<alias>` so the owner can pick. A seat resolves to its member through `sminos.members(project)`.

Membership is not a precondition for reading. sminos retires a seat-less terminal session once its process ends, and `find_target` then no longer finds it, even by uuid; its transcript and host events stay on disk. So a subscription, which stores its project and session id, and a full uuid given on the command line resolve historically when `find_target` does not: the session's transcript by `sminos.transcript_path`, its host events by `sminos._own_events(project, sid, …)`, its continuation by `sminos.continued_in` / `sminos_bridge.successor`, and `manager query` takes the headless fork (the session is not running). Nothing revives the session. The member's sessions, oldest first, are `reversed([m.session] + list(m.former))`. A member whose `local` is false is refused (constraint "This Mac only"). `find_target` may let sminos reconcile the project's membership (append `joined`/`retired` events), as `sminos list` does; that is sminos's own bookkeeping, not a manager write.

**`manager transcript --json`:**

    {
      "member": "p5-desk-track-owner",
      "sessions": ["b4948247-…", "…"],          // the lineage walked, oldest first
      "since": "2026-10-31T14:00:00+09:00",
      "until": null,
      "truncated": false,                      // true when --max-chars stopped it; the text output says where and how to narrow
      "entries": [
        {"ts": "2026-10-31T05:02:11.204Z", "session": "b4948247", "kind": "you", "text": "…"},
        {"ts": "…", "session": "b4948247", "kind": "tool", "text": "Bash: git log --oneline -5"},
        {"ts": "…", "session": "b4948247", "kind": "→you", "text": "…whole message…"}
      ]
    }

Entry kinds, and what each is read from:

| kind | what it is | how it is recognized |
|---|---|---|
| `you` | the owner typed it | a non-meta user row whose `origin.kind` affirmatively says the composer or the owner's own Remote Control client (`composer`, `human`, `bridge`), that is not a slash-command echo, or a `queued_command` attachment typed mid-turn. Not `sminos._is_human`, which treats a missing origin as human |
| `you?` | a user row that reads as typed but carries no origin stamp | older transcripts written before the engine stamped origins: shown, labelled unverified, never merged into `you` |
| `you·desk` | the owner's words sent through the desk or MAWS, corroborated | a bridge delivery row **whose text matches a `human` event of the project's log** (writer `<machine>/human` or `hub/<member>`) delivered to this session; MAWS steers (`sminos._maws_steer_texts`) |
| `you·desk?` | a bridge delivery the records cannot corroborate | a bridge delivery row with no matching log event: MAWS's RL10 `send`, which delivers under the `rl10-send` key and never logs the text (`sminos_rpc.py`), and any delivery whose event is not found. Kept, labelled unverified |

A *bridge delivery row* takes one of the forms `bridge.tsx` writes: an idle session's prompt (origin `plugin` `sminos`, `asUser`), or, during a running turn and for an idle prompt refused after an Esc, a row the bridge appends (`session.append`, a plugin-origin meta row). M1 reads `bridge.tsx`'s delivery code for the exact marks of each form. The same plugin origin also carries the bridge's own generated wakes (`wakeForSteer`, rows opening with `[sminos bridge]`), which are `notice`, never a delivery.
| `you·steer` | an owner steer | user row whose first line is `[sminos steer from human]` (`STEER_LINE`, `sminos/hooks/mods/bridge.tsx`) |
| `peer <alias>` | another session's message | `[sminos chat …]` / `[sminos message from …]` frames (`compose_chat_frame`, `compose_frame`), the engine's `cross-session-message` envelope (`PEER_TAG`) |
| `session` | the session's prose | assistant text blocks, except the response a hook made up (`answeredWithoutRequest`) |
| `→you` | a message to the owner, whole | message-tool calls (`MESSAGE_TOOLS`, read as `sminos._sent_text` does) and `<message>` spans (`sminos.extract_marks`) |
| `asked` / `answered` | a question to the owner and its answer | `sminos._ask_events`, `sminos._deliveries` |
| `compacted` | a compaction summary | user rows with `isCompactSummary` |
| `interrupted` | an Esc or a bridge interrupt | `[Request interrupted by user]` (`INTERRUPT_MARKER`), the bridge's cut-off row (`CUT_OFF_LINE`) |
| `tool` | one line per tool call | `tool_use` blocks: name and its most telling argument (a command, a path, a pattern, a description), cut to 160 characters |
| `agent` | a subagent spawned | `Agent`/`Workflow` calls: description and type; the first 600 characters of its result |
| `notice` | a background task finished, or a wake sminos generated | rows of origin `task-notification` (`sminos_jobs._plain_notification`); the bridge's wakes (`[sminos bridge]`, `WAKE_LINE`) |
| `boundary` | the lineage moved to the next session id | emitted by the walker |

Everything else (tool results other than an agent's, thinking, images, system reminders, hook context, attachments not listed) is left out. A row the classifier cannot place is left out, never guessed into `you`: inventing the owner's words is the worst error this reader can make.

The window's start is found with `sminos_subagents.offset_since(mm, t)` on an mmap of the transcript (it returns a line start at or before the first row stamped at or after `t`, within 1 MiB, or 0), then rows before `t` are skipped while scanning forward. The whole file is never parsed: `sminos.transcript_rows` reads the whole file and must not be used here.

**`manager pending --json`:**

    {"unanswered": [{"member": "CI-opt", "session": "a45b97a3-…", "asked": "…Z", "question": "…", "src": "toolu_…"}],
     "waiting":    [{"member": "p5-desk-track-owner", "session": "…", "since": "…Z"}]}

`unanswered`: `question` host events of every subscribed session (any age) with no `answered` event of the same `src`; with `--until T`, only questions asked before `T` and answers given before `T` count, so a past moment can be replayed. Read both places a host event can live, the log and the host store (`sminos._own_events(project, sid, "log")` and `(project, sid, sminos.HOST_STORE)`); an answer can sit under the asker's writer. `waiting`: subscribed members whose `Member.state` is `waiting`.

**State file** `$SMINOS_HOME/managers/<name>.json` (mode 0600, written whole through a temporary file and a rename):

    {
      "version": 1,
      "initiatives": [
        {"name": "P5", "sessions": [
          {"session": "b4948247-…", "alias": "p5-desk-track-owner", "project": "doperpowers", "added": "…Z"}]}
      ],
      "carry": [
        {"session": "a45b97a3-…", "member": "CI-opt", "raised": "…Z", "need": "…", "blocking": true, "source": "…quote…"}
      ],
      "briefed": "…Z"
    }

`subscriptions add` refuses the manager's own session (`CLAUDE_CODE_SESSION_ID` in its environment) and members on another machine; adding a member already subscribed under another initiative moves it. `carry set` replaces `carry` and stamps `briefed`; it is how the skill records what a briefing left open.

**More new files (M2–M4).**

    sminos/hooks/mods/bridge-ask.tsx                  # M2: the `ask` op, imported by bridge.tsx as bridge-btw.tsx is
    sminos/tests/mods/bridge-ask.test.ts              # M2 (ask.test.ts already exists: it tests the async question tool)
    hooks/mods/fork-guard.tsx                         # M2: doperpowers plugin, registered from hooks/mods/register.tsx
    tests/mods/fork-guard.test.ts                     # M2
    sminos/tests/mods/live-ask-check.py               # M2: live check against throwaway sessions, run by hand, not a gate
    sminos/skills/sminos/scripts/sminos_fork.py       # M3: the shared fork code

**The bridge's `ask` op** (an extension of the bridge protocol DX5, `docs/doperpowers/plans/2026-10-15-arkho-desk-c2-bridge.md`; local to this machine — no hub RPC carries it in this initiative).

    request   {"op": "ask", "prompt": "<the question>"}
    answer    {"ok": true,  "result": {"started": true, "id": "<op id>", "agentId": "<fork's agent id>"}}
            | {"ok": false, "code": "no-guard" | "busy" | "nothing-to-fork" | "bad-prompt", "error": "<why>"}
    stream    {"type": "ask", "phase": "start", "id", "agentId"}
              {"type": "ask", "phase": "end", "id", "agentId",
               "text"?: string, "truncated"?: true,                      // the fork's answer, cut to 64 KiB as btw's is
               "usage"?: {"input", "output", "cacheRead", "cacheWrite"},  // the whole fork's, from turn.complete
               "reason"?: "aborted" | "empty-reply" | "failed", "error"?: string}

`OPS` and the bridge's `capabilities.controls` gain `ask`. The open asks are kept in `$.state` under `{plugin: 'sminos', key: 'bridgeAsk'}`, a key and type of their own (`{plugin: 'sminos', key: 'ask'}` is the async question tool's `AskSnapshot`, which `ask.tsx` writes on every change and the reload mod observes), from before the answer until the child took the end, and the module that loads after a reload ends any it finds there `aborted`, exactly as `bridge-btw.tsx` does for `btw`. The bridge child (`sminos/skills/sminos/scripts/sminos_bridge.py`) relays `ask` events to stream subscribers and re-posts an untaken end after a resync as it does for `btw` (`OUTCOME_EVENTS`).

The spawn: `$.agent.spawn({ subagentType: 'fork', description: 'manager query', prompt: askPrompt(tail, question) })`, called from the command listener (not from a hook, never from a slash command). The answer is the fork's own `turn.complete`, matched by `agentId`.

The fork's prompt (the frame is an exact string; `ASK_FRAME`, exported from `bridge-ask.tsx` and copied verbatim as `FORK_FRAME` in `sminos_fork.py` for the headless path, a test in each pinning the text):

    ASK_FRAME = "You are a read-only fork of this session, started by the owner's manager session to answer one question. The session itself never sees this exchange, and nothing you do here reaches it. Do not continue the session's task. You may use read-only tools (reading and searching files, read-only shell commands such as git log, git status or gh pr view) to check facts; anything that would change a file or any state is refused. Answer the question directly, then stop."

    askPrompt(tail, question) =
      ASK_FRAME
      + (tail ? "\n\nSince the last request this fork continues from, the session's conversation went on as follows (oldest first):\n\n" + tail : "")
      + "\n\nThe question:\n\n" + question

The tail exists only while the main loop is mid-turn: the bridge records a boundary at each main-loop `turn.step` whose response completed (a `stop` chunk with usage passed up through its hook), the identity of that response's rows rather than a `messageCount` (which counts API messages, not the transcript rows `$.session.messages()` returns; Decision Log, 2026-10-31), and the tail is `$.session.messages()` after that response, rendered as text — assistant text, each tool call as `name(input)`, each tool result cut to 2,000 characters — keeping the newest 32 KiB.

**The read-only guard** (`hooks/mods/fork-guard.tsx`, doperpowers plugin), registered in `hooks/mods/register.tsx` ahead of `appeal.tsx` so its hooks are outer to appeal's and an appeal pass can never apply to a fork's call. The doperpowers plugin's hooks sit outside every user-tier plugin's (`prependPlugins`), so its `tool.call` runs before any user-tier plugin serves a tool; the two plugins outside it are to-human, whose message tool refuses subagents, and sminos, whose hooks a bridge-spawned fork bypasses.

    FORK_TOOLS        = ['Read', 'Grep', 'Glob', 'Bash']
    FORK_GUARD_REASON = "This is a read-only fork (manager query): calls that change files or state are refused."

- **Identity.** A call is a *managed fork's* when its `agentId` names an agent that `$.agent.list()` lists with `type: 'fork'` and `spawnedBy: 'sminos'`. The guard remembers each agent id's verdict once resolved (ids are not reused), so most calls need no lookup. A main-loop call (no `agentId`) is never a managed fork's and passes untouched without a lookup. A subagent call while the list rejects (or answers something not a list) is refused, never passed; an id a readable list does not hold is not a managed fork's and passes, never remembered, so a listing that came late is found at the next call.
- **`tool.call`.** For a managed fork's call whose tool is not in `FORK_TOOLS`, answer a refusal carrying `FORK_GUARD_REASON` without calling `next`. Every other call goes to `next(e)` untouched.
- **`tool.check`.** For a managed fork's `Bash` call: `{decision: 'allow'}` when `e.isReadOnly`, else `{decision: 'deny', reason: FORK_GUARD_REASON}`, never calling `next`. For its `Read`, `Grep`, `Glob`: `{decision: 'allow'}`. Every other call: `next(e)` untouched.
- **Fail closed.** Each registration carries a `.catch` that refuses (the engine's prescribed form for a guard), so a throw or an overrun budget refuses the call instead of skipping the guard.

**Guard presence.** `ask` refuses `no-guard` unless the bridge can confirm, in this session, that the guard is registered now: evidence the current guard module produces, not a plugin version or a marker an earlier load left behind (a reload that drops the guard must turn `ask` into `no-guard`). The mechanism is M2's to choose from what the engine offers and to pin in a test.

**`sminos_fork.py`** (sminos's internal fork code; no CLI verb):

    class ForkAnswer(NamedTuple):
        text: str
        via: str            # "btw" | "fork agent" | "headless fork"
        usage: dict         # {"input", "output", "cacheRead", "cacheWrite"}; headless: from the result's usage
        truncated: bool

    class ForkFailed(Exception):        # reason: one line, as derive's fork_failure builds it; stderr kept
        def __init__(self, reason: str, stderr: str = "", code: str = ""): ...

    def ask_btw(session: str, prompt: str, timeout: float = 120) -> ForkAnswer
    def ask_fork_agent(session: str, prompt: str, timeout: float = 300) -> ForkAnswer
    def headless_fork(project, m, prompt: str, *, tools: bool, cache: bool, timeout: float) -> ForkAnswer
    def bridge_offers(session: str, op: str) -> bool     # the bridge answers and its capabilities list `op`

`ask_btw` and `ask_fork_agent` follow the session's bridge stream (`sminos_control.follow_stream`), post the op (`sminos_control.post_command` to `sminos_bridge.endpoint(session)`), and wait for the matching `end` by id; a refusal raises `ForkFailed` with its `code`; a silence past `timeout` raises `ForkFailed("… gave no answer within N s")` and leaves the fork to finish on its own (stopping it through the bridge's `stop-agent` would leave a note in the session's conversation). `headless_fork` is `derive_line`'s process code moved and generalized: the gate, the internal marker, `--safe-mode`, `--no-session-persistence`, `--fork-session --session-id <new>`, `cwd=member_cwd`, the cleanup in `finally`; `tools=False` passes `--tools ""` and `tools=True` passes `--permission-mode auto --tools Read,Grep,Glob,Bash`; `cache=False` sets `DISABLE_PROMPT_CACHING=1`; the prompt is always last, after `--output-format json` (a prompt right after `--tools ""` is read as a tool name).

**`manager query`:**

    manager query <member> "<question>" [--timeout S]

Text output: the answer, then one line `via fork agent · cache read N · cache write N · input N · output N` (or `via headless fork · …`). `--json`: `{"member", "via", "text", "truncated", "usage"}`. It asks through `ask_fork_agent` with the question under no extra frame (the bridge adds `ASK_FRAME`) when `bridge_offers(session, "ask")`; otherwise through `headless_fork(…, FORK_FRAME + "\n\nThe question:\n\n" + question, tools=True, cache=True)`: a session that is not running, a bridge that does not offer `ask` (an older sminos), and an `ask` refused `no-guard` all take the headless path, at the read-only level the owner accepted for it, and the output's `via` says which path answered. An `ask` refused `busy` (another manager query is running in that session) or `nothing-to-fork` (the session has made no request yet) is reported, exit 1. A session under another config dir is refused for the headless path as `derive` refuses it (`foreign_config`).

### M1 — The `manager` command: windows, pending items, subscriptions

At the end of M1 the owner (or a session) can run `manager transcript <member> --since 10h` on any local session and read its condensed window in seconds, `manager pending` for unanswered questions and waiting sessions, and `manager subscriptions …` / `manager carry …` to keep the manager's state. Nothing yet asks a session anything.

- **Touches:** `sminos/skills/manager/scripts/` (new), `sminos/tests/test_manager.py` (new), `sminos/tests/run-sminos-tests.sh` (`run_suites()` calls the new test file), `sminos/CLAUDE.md` (one sentence pointing at the manager's `scripts/CLAUDE.md`).
- **Exposes:** the commands, JSON shapes, entry kinds and state file in Interfaces.
- **Decisions:**
  - The classifier lives in `manager_window.py` and reuses sminos's readers named in the entry-kind table instead of re-deriving frame formats; where no reader exists (compaction summaries, interrupts, steers, the `[sminos chat` frames), it keys on the constants named there and its fixtures pin them.
  - Lineage boundaries are emitted as `boundary` entries so a reader sees where a session continued.
  - A subscription is resolved by the session id it stored, not its alias (aliases recur and change): the stored id goes through `find_target` as a full uuid and on to the session it continued in (`sminos_bridge.successor`), so a resumed seat stays followed; `subscriptions` shows the current alias beside the stored one when they differ.
  - `--max-chars` defaults to 400,000 characters of rendered text; past it the walk stops and says the last timestamp reached and suggests a later `--since` or an `--until`.
  - Speed target: a 10-hour window of a ~670 MB transcript renders in under 10 seconds on the MacBook (acceptance 3). If `offset_since`'s 1 MiB granularity or the forward scan misses it, measure before optimizing and record the figure in Surprises & Discoveries.
- **Does not touch:** the sminos CLI's verbs, `sminos help`, the sminos skill, the bridge, `derive`.
- **Proves:** acceptance 2 and 3. Tests pin: each entry kind from a fixture row of that kind; a peer frame never classified as `you`; each bridge delivery form (an idle log-backed delivery, an idle RL10 send with no log event, a delivery appended during a running turn, one appended after an Esc refused the prompt) is `you·desk` when a log `human` event matches its text and `you·desk?` otherwise, and a `[sminos bridge]` wake under the same origin is `notice`; a user row with no origin stamp is `you?`, never `you`; a subscribed seat-less terminal session whose process ended (retired from membership) still yields its window and its pending questions; an `answeredWithoutRequest` row dropped; an unknown row dropped; the window starting at the first row at or after `T` in a generated file of at least 50 MB; a two-session lineage walked oldest first with one `boundary`; time parsing of each `T` form, including a clock time later than now meaning yesterday; `--max-chars` truncation; `pending` matching questions to answers by `src` across the log and the host store, and `--until` ignoring both after `T`; a bare alias of a member in another project resolving from a caller whose own project has members, two same-named members in different projects exiting 4 with both qualified names; `subscriptions add` refusing the manager's own session and a remote member; the state file written 0600 and replaced whole.

### M2 — The bridge's `ask` and the read-only guard

At the end of M2 a live session running the branch's sminos and doperpowers plugins answers a bridge `ask` through a fork agent inside it: the fork reads the session's cache, uses read-only tools, is refused anything else, and leaves the session's conversation and turn untouched. `sminos/tests/mods/live-ask-check.py` shows each of these on throwaway sessions.

- **Touches:** `sminos/hooks/mods/bridge-ask.tsx` (new), `sminos/hooks/mods/bridge.tsx` (`OPS`, `capabilities.controls`, routing the op, recording the main loop's last completed response (its tool-call ids and text blocks), matching `turn.complete` to open asks), `sminos/types/sminos.d.ts` (the `bridgeAsk` state key and its type), `sminos/skills/sminos/scripts/sminos_bridge.py` (`OUTCOME_EVENTS`), `sminos/tests/mods/bridge-ask.test.ts` (new), `sminos/tests/test-bridge-control.sh` where the child's relay of `ask` is pinned; `hooks/mods/fork-guard.tsx` (new), `hooks/mods/register.tsx`, `tests/mods/fork-guard.test.ts` (new); `sminos/tests/mods/live-ask-check.py` (new); `sminos/hooks/mods/CLAUDE.md` and `hooks/mods/CLAUDE.md` (and `hooks/mods/README.md`, the mods' manual) for what changed.
- **Exposes:** the `ask` op, `ASK_FRAME`, `askPrompt`, the guard and `FORK_GUARD_REASON`, the guard-presence check (Interfaces).
- **Consumes:** nothing from M1.
- **Decisions:**
  - `bridge-ask.tsx` mirrors `bridge-btw.tsx`'s structure (answer at once, start and end on the stream after the answer, open ids kept in `$.state` across a reload, orphans ended `aborted`), so the desk-facing machinery the child already has for `btw` carries `ask` unchanged.
  - The guard-presence mechanism is this milestone's to choose; whichever it is, `bridge-ask.test.ts` pins that a session without it refuses `no-guard`, and the live check runs a session without the doperpowers plugin to prove it.
  - `spawnedBy` is the spawning plugin's name as the engine reports it (`forkprobe` in the spike); the live check confirms it reads `sminos` for the bridge's forks before the guard keys on it.
  - The guard caches nothing across calls it cannot re-derive: `$.agent.list()` is read per `tool.check` of a subagent loop (the main loop's calls, which carry no `agentId`, pass through without a lookup).
  - Live checks follow the spike's harness (`~/.local/share/session-manager/spikes/fork-agent-probe/run_probe2.py`, `analyze.py`, and `fork-agent-findings.md` beside it): an isolated config dir, sessions on haiku rooted outside `~` (a session rooted under `~` loads `~/.claude/CLAUDE.md`; friction entry `general/conditional/isolated-claude-home-under-user-home-inherits-ancestor-claude-md.md`), the branch's plugins loaded from the worktree. Do not copy the engine into a fake `HOME`.
- **Does not touch:** `btw`'s behavior, `derive`, the `manager` command, `sminos_rpc.py` and the hub's RPC set, the desk.
- **Proves:** acceptance 4, 5 and 6 at the bridge (M4 repeats them through `manager query`). Unit tests pin: `ask` refused `bad-prompt`, `busy`, `no-guard`, `nothing-to-fork`; `ASK_FRAME`'s exact text; `askPrompt` with and without a tail; the tail rendered from the messages after the last completed response (a text-only one included), tool results cut to 2,000 characters, the newest 32 KiB kept; the end's text cut to 64 KiB; an end matched to its own `agentId` only; an orphaned ask ended `aborted` after a reload, and a fork still running after any number of reloads keeping `ask` busy; open asks kept under `bridgeAsk` beside a pending async question's `AskSnapshot` under `ask`, neither overwriting the other across a reload; the guard, for a managed fork: refusing at `tool.call` every tool outside `FORK_TOOLS` (`Agent`, `SendMessage`, an MCP tool, a stand-in plugin tool whose `tool.call` handler would write a probe file — the file is not written), allowing `Read`/`Grep`/`Glob`, allowing read-only `Bash` and denying the rest at `tool.check`; refusing when `$.agent.list()` rejects, passing an id a readable list lacks, and when a guard handler throws (the registration's `.catch`); passing through untouched for another plugin's fork, a non-fork subagent and the main loop; answering before `appeal.tsx`'s pass can apply; guard presence turning false when the guard module is unloaded, so `ask` answers `no-guard`. The live check records, into Surprises & Discoveries: an idle session's ask (cache read as a share of the last request, the quoted last message, the main transcript's user and assistant row counts before and after, no turn started); an ask during a main-loop `sleep 20` (the sleep's duration, the tail naming the latest tool call); `touch` refused with no file and no permission prompt, in `auto` and in `default` permission mode; a fork told to spawn an `Agent` or to message the main session refused; the managed fork identified on its first tool call; a sminos reload during an ask (whether the fork survives); `busy`; `no-guard`; a session past 100k tokens (cache share); an Esc in the session during an ask and a compaction during an ask (what the fork and the end do).

### M3 — The shared fork code: `derive` on `btw`, `manager query`

At the end of M3, `sminos derive` asks a live member through `btw` and a stopped one through the uncached headless fork as before, with the same printed line; `manager query <member> "<question>"` answers from a live session through its fork agent and from a stopped one through the headless fork, and says which.

- **Touches:** `sminos/skills/sminos/scripts/sminos_fork.py` (new), `sminos/skills/sminos/scripts/sminos.py` (`derive_line` moves its process code into `sminos_fork.headless_fork` and asks `ask_btw` first), `sminos/skills/manager/scripts/manager.py` (`query`), `sminos/tests/run-sminos-tests.sh` (the stub `claude` records the `--permission-mode` and `--tools` values it was given in `calls.log`; derive's cases), `sminos/tests/test_manager.py`, a Python bridge stand-in that answers `btw` and `ask` (extend `sminos/tests/test_policy_requests.py`'s `Bridge` or `test_rpcs.py`'s `Mod`), `sminos/skills/sminos/scripts/CLAUDE.md` (derive's note, `sminos_fork.py`), `sminos/skills/manager/scripts/CLAUDE.md`.
- **Exposes:** `sminos_fork` (Interfaces), `manager query`.
- **Consumes:** the `ask` op and `ASK_FRAME` (M2); the `manager` command's resolution and output conventions (M1).
- **Decisions:**
  - `derive_line` asks `ask_btw(m.session, prompt, timeout=SMINOS_DERIVE_TIMEOUT)` when `bridge_offers(m.session, "btw")`; on any `ForkFailed` from it (refused, an API error, aborted, silent past the timeout) it runs the headless fork once, so derive's success rate never drops below today's. The headless call is `headless_fork(project, m, prompt, tools=False, cache=False, timeout=…)`: exactly today's flags and environment. `DeriveFailed` keeps its meaning and its stamps: `derive_line` turns the last `ForkFailed` into `DeriveFailed(reason, stderr)`.
  - Derive's printed line does not change. How it asked (`via btw` or `via headless fork`, with cache read and input tokens) goes to stderr beside its other diagnostics, which is where acceptance 9 reads it.
  - `btw` gets derive's prompt as it is; the bridge adds `BTW_FRAME`.
  - `manager query`'s routing is the table in Interfaces; its timeout default is 300 s for the fork agent and the headless fork alike.
- **Does not touch:** the TypeScript mods (M2 is done), the skill.
- **Proves:** acceptance 7 and 9 at the stub level, and `manager query`'s routing. Tests pin: derive with a live bridge stand-in offering `btw` asks through it and starts no fork process; derive with a refused or failing `btw` falls back to the headless fork; derive with no bridge runs the headless fork with `--tools ""` and `DISABLE_PROMPT_CACHING=1`, prompt last; `manager query` with a stand-in offering `ask` returns its end's text and usage and names `via fork agent`; `busy` and `nothing-to-fork` exit 1 with the reason; `no-guard`, an `ask`-less bridge and a stopped session take the headless fork with `--permission-mode auto --tools Read,Grep,Glob,Bash`, caching on, `FORK_FRAME` before the question, prompt last; a remote member and a foreign config dir refused; a silent bridge past `--timeout` exits 1 saying so.

### M4 — The skill, the digest brief, the replay evaluation, and acceptance

At the end of M4 the owner can run `/sminos:manager` in a fresh session, subscribe sessions, and ask for an update since a time, and get the briefing the design describes; the digest subagents' effort is chosen on evidence; both plugins carry new versions; and every acceptance item has been run.

- **Touches:** `sminos/skills/manager/SKILL.md` (new), `sminos/skills/manager/references/digest-brief.md` (new), `docs/doperpowers/specs/2026-10-31-session-manager-replay.md` (new: the labelled list and the scores), `sminos/skills/manager/scripts/CLAUDE.md` (final), `sminos/CLAUDE.md` (the pointer, if M1 did not add it), the plugins' versions through `scripts/bump-version.sh --plugin sminos` and `scripts/bump-version.sh`, this spec's Progress and record.
- **Consumes:** every command from M1 and M3.
- **Decisions:**
  - Write and test the skill with `doperpowers:writing-skills`. `SKILL.md`'s front matter is `name: manager`, a one-sentence `description` for the slash menu (what it does for the owner: a read-only briefing of what their subscribed sessions need from them and what happened since a time), and `disable-model-invocation: true`. Its body carries what the manager model cannot derive: the purpose (the owner's side of the work), the commands (named from the skill's base directory), the briefing's order and item fields, blocking and optional, the status rules, the digest dispatch (general-purpose subagents, `model: sonnet`, the chosen effort, one per subscribed session, in parallel, briefed from `references/digest-brief.md`), recording the carry list with `manager carry set` after each briefing, subscriptions only on the owner's word (it may suggest), strictly read-only, and the query costs that tell it when a query is worth it (a fork agent costs a fraction of a headless fork). The design section of this spec is the source; the skill does not point at the spec, since the manager model will not have it.
  - `digest-brief.md` is the brief a digest subagent gets: its member, its window, its carry items; to read with `manager transcript` and ask with `manager query` when the records leave an item's status unclear; to return, per need, what is needed, why it has to be the owner, blocking or optional, when raised, status with its evidence, and the quoted source, then the session's decisions taken on the owner's behalf, changes of plan and progress, as prose for the manager to merge.
  - **The replay evaluation.** Window: 2026-10-30 00:00 to 2026-10-31 23:59 KST over the P5 sessions `37052769`, `b4948247`, `a45b97a3`, and `1ea561bc` (the MAWS session that asked to merge cua PR #240). The labelled list is made first, independently of the skill: an Opus subagent at high effort reads the window's host events and `manager transcript` windows and lists every item the owner was asked for, with its blocking or optional label and its status at the window's end; the executor checks each item against the transcripts and writes the list to the replay file. Then the briefing procedure runs on the same window twice, digest subagents at Sonnet medium and at Sonnet high, and each is scored: blocking items found, all items found, items invented, statuses right. Medium is chosen if it finds every blocking item high finds and its total recall is within 5 points of high's; the choice goes into `SKILL.md` and the Decision Log, the scores into the replay file and Surprises & Discoveries, with each run's cost. The chosen effort must also meet acceptance 8 on this input: every blocking item found and at least 90% of all items.
  - **The replay is frozen at its cutoff.** The labelled list judges status as of 2026-10-31 23:59 KST, so nothing either run reads may come from after it: transcripts are read with `--until` the cutoff, `manager pending --until` the cutoff, and the digest subagents are told not to query (a query reads the session as it is now, with later answers in it) and to settle every item from the records up to the cutoff. Each run starts from its own empty state (`--name replay-medium`, `--name replay-high`), so neither reads the other's carry list. Querying is exercised separately, on throwaway sessions, in M2's live check and the acceptance run.
  - **Pressure scenarios** for the skill (writing-skills), on a throwaway manager session: the owner says "tell CI-opt yes, merge it" (it does not relay; it says where to answer); the owner says "subscribe whatever looks relevant" (it lists suggestions and subscribes only what the owner then names); a digest finds an item it cannot settle from the records (it queries rather than guesses); the owner asks a follow-up about one item (it answers from the briefing, the transcript or a query, without re-running the briefing).
  - **Acceptance run.** Items 4–7 and 9 need the new bridge inside the queried session, so before merge they run against throwaway sessions loaded with the branch's plugins, as M2's live check does. Items 1–3 and 8 run as written on the owner's real records: the `manager` commands read transcripts and host events and change nothing, and item 8 is the frozen replay above. Item 10 is checked on the throwaway sessions the queries went to, and on the real sessions' transcripts for the reads. After merge and a plugin update, the finish step repeats item 4 against one of the owner's own live sessions.
- **Does not touch:** code beyond what an acceptance failure forces (a failure found here is fixed in the milestone's own files and recorded).
- **Proves:** acceptance 1–10; the replay scores and the effort choice; the pressure scenarios' outcomes.

### Concrete Steps

All from the worktree, `/Users/new/Developer/GitHub/doperpowers/.claude/worktrees/session-manager`.

    python3 sminos/tests/test_manager.py                    # M1, M3: the manager command
    bash sminos/tests/run-sminos-tests.sh                   # every sminos suite; SMINOS_PART=core or suites for half
    bash sminos/tests/mods/run.sh                           # M2: the sminos mods, bridge-ask.test.ts among them
    bash tests/mods/run-mods-tests.sh                       # M2: the doperpowers mods, fork-guard.test.ts among them
    bash tests/mods/typecheck.sh                            # every plugin's mods and tests typecheck
    ci-gate --gates sminos,sminos-suites,sminos-mods,mods-types,mods   # on the committed HEAD
    python3 sminos/tests/mods/live-ask-check.py             # M2: live, throwaway haiku sessions; prints one verdict line per check

Expected shapes (illustrative values):

    $ sminos/skills/manager/scripts/manager transcript p5-desk-track-owner --since 10h | head -4
    2026-10-31 14:02  you        merge it once CI is green
    2026-10-31 14:02  tool       Bash: gh pr checks 452
    2026-10-31 14:05  →you       PR #452 is merged. …
    2026-10-31 14:06  peer CI-opt  [sminos chat doperpowers …] the runner image moved

    $ sminos/skills/manager/scripts/manager query CI-opt "What are you waiting on from the human?"
    Nothing blocking. One optional item: …
    via fork agent · cache read 412,330 · cache write 1,204 · input 96 · output 388

    $ sminos/skills/manager/scripts/manager query some-stopped-seat "What did you finish last?"
    …
    via headless fork · cache read 0 · cache write 88,102 · input 2 · output 310

A failure reads as one line on stderr and exit 1, for example `manager: CI-opt runs on mini; this version reads sessions on this machine only` or `manager: CI-opt is already answering another manager query (busy)`.

## Surprises & Discoveries

- Observation: A headless fork never reads the forked session's prompt cache for the conversation, with or without plugins and tools.
  Evidence: on f89d7fb0 (~100k tokens, Opus 5.5, cache warm), `--safe-mode --no-session-persistence --tools ""`: read 0, write 87,792, $0.70; plugins on, `--tools ""`: read 0, write 98,791; plugins on, all tools: read 10,334, write 83,069.
- Observation: Two headless forks with identical flags share their own cache entry for an hour.
  Evidence: the same `derive` flags a minute later: read 87,792, write 0, $0.02.
- Observation: `btw` reads the session's whole cache and writes nothing; forks do not build on each other, but each lags one response behind the transcript.
  Evidence: `btw` on f89d7fb0: input 156, cache read 120,027, write 0. Two `btw`s in one shell call, asked for the last user-role turn and last tool call, both returned the result of the call before the one in flight; the second did not mention the first.
- Observation: The forked session's own cache is not disturbed by forks.
  Evidence: f89d7fb0's requests after the forks: cache read 111,277 → 119,284, writes only the new turn (856–3,132 tokens).
- Observation: `dontAsk` with an allowlist enforces read-only in a headless fork; plan mode does not.
  Evidence: `dontAsk`: `permission_denials` lists `touch /tmp/fork-write-probe-dontAsk`; Write not offered; no probe file. Plan mode: the model declined both writes itself, `permission_denials` empty.
- Observation: `--tools` takes several values, so a prompt placed right after `--tools ""` is read as a tool name; with `--resume` the error is "No deferred tool marker found in the resumed session".
  Evidence: three failed fork runs; fixed by putting `--output-format json` between them. Friction entry `~/.claude/friction-tracker/general/live/claude-p-tools-empty-takes-prompt-as-tool-name.md`.
- Observation: An uncached derive-style fork costs about $0.40 per 100k tokens of context; this Mac runs dozens a day.
  Evidence: 104,990 input tokens, $0.4225. daemon.log, successful derives per day Oct 27–31: 77, 58, 39, 61, 48 (the parser may double-count a few two-line answers).
- Observation: Two days of P5 host events are about 140k tokens; most messages carry italic needs-you spans.
  Evidence: MAWS + doperpowers projects, Oct 29–31: 507 host events, ~565k characters; 231 of 377 messages with italic spans; all 62 questions answered.
- Observation: A fork agent a mod spawns (`$.agent.spawn({ subagentType: 'fork' })`) reads the session's cache on its first request.
  Evidence: spike (haiku, engine 2.1.316, `~/.local/share/session-manager/spikes/fork-agent-findings.md`): first-request cache read 27,169 of 27,196, 27,315 of 27,317, 27,208 of 27,235 tokens. One idle fork read 22,214 of 27,113, and the main loop's own next request read the same 22,214 (the session's first-turn miss, not the fork's). The main loop wrote about 121 tokens per step while a fork ran.
- Observation: The fork agent leaves the session's conversation and turn untouched; its answer reaches only the spawning mod.
  Evidence: main transcript rows 33 before an idle fork, 38 during (five `tools-used` metadata lines), 38 when done, 38 25 s later; no task-notification, `prompt.submit` or `session.receive`; no turn started. A fork spawned during the main loop's `sleep 20` left it to run 20.1 s. Main requests during the fork carried only `total_tokens_reminder`. The answer, reason and usage arrived at the spawning plugin's `turn.complete`, matched by `agentId`.
- Observation: A fork spawned outside a hook bypasses every hook of the spawning plugin; spawned inside a hook it bypasses only that hook. A separate plugin's `tool.check` sees every fork call and its deny overrides core's allow and ask.
  Evidence: timer spawn: the spawning plugin's `tool.call`, `tool.check`, `turn.step`, `turn.start`, `prompt.attachment` saw nothing, `turn.complete` arrived. Spawn from a `tool.call` hook: that hook missed the fork's calls, the same plugin's other `tool.call` hook denied Edit and `touch`. A separate plugin's `tool.check` (`isReadOnly` false → deny) let Read, `ls`, `cat`, `echo`, `sleep` run and refused Edit, Write, a `>` redirect, `touch` and a Python write; `/tmp/fork-probe-x`, `-y`, `-z` absent.
- Observation: An idle session's fork agent sees the last response; mid-turn it stops at the main loop's last request.
  Evidence: idle forks quoted the last assistant message (`PELICAN`, `SLEEP-DONE`); a mid-turn fork's context excluded the in-flight `sleep` call.
- Observation: Spawning a fork agent from a slash command writes rows into the conversation; it is visible in the session's agent strip and `/tasks`.
  Evidence: two `local_command` user rows per command spawn; footer `◯ fork  fork probe idle  5s · ↓ 28.8k tokens`; `$.agent.list()` `type: fork, status: running`, then `completed`, `spawnedBy: forkprobe`.
- Observation: Reading a window of a 669 MB transcript takes ~0.35 s; resolving the member is the cost of `manager transcript`, 2–10 s depending on how it is named.
  Evidence: M1, b4948247 (669,398,962 bytes), `--since 10h`: by alias from a doperpowers session 2.43 s and 2.72 s; from a directory with no session id 5.44 s; by short id from inside a session 7.95 s (1.1 s CPU). Profile: `find_target`'s org-wide short pass builds 91 projects' views (~6.7 s under cProfile) and `caller_scope` runs `claude agents --json` (~2.4 s). Acceptance 3 is stated by alias, which holds with margin.
- Observation: The P5 transcripts hold no `you·desk`/`you·desk?` rows over three days; mid-turn prompts are `queued_command` attachments carrying their own `origin`; task notifications appear both as origin-`task-notification` user rows and as `queued_command` attachments.
  Evidence: M1's survey of the three P5 transcripts; the delivery forms are pinned by fixtures built from `bridge.tsx`'s code.
- Observation: In MAWS-launched transcripts (`entrypoint: "sdk-ts"`) only composer submissions carry the `human` origin stamp, so decision (f) holds without log corroboration. 1ea561bc and 37052769 are terminal launches (`entrypoint: "cli"`), not MAWS ones.
  Evidence: M1 fix wave, read-only over the 90 `sdk-ts` transcripts on this Mac (mostly MAWS scratch and acceptance sessions): 199 human-stamped user rows, all composer submissions (`promptSource: "sdk"`, `turnOrigin: "human"`): prompts, element comments, mark-ups, one MAWS ask steer. SDK context, plugin rows, notifications and peer messages are stamped `plugin`, `task-notification`, `peer` or nothing. `manager transcript` on 720e2008 (the one owner-driven sitting, 2026-10-19): `you·desk` 33, no `you`/`you?`; its `[MAWS ask …]` answer steer is `answered` only, paired with its `asked`. Caveat: the owner-driven sample is essentially one session.

## Decision Log

- Decision: Verification. One independent spec review (technical-heavy: `doperpowers:adversarial-reviewer`) and, since the execution has four milestones, the adversarial reviewer's buildability review of the execution section, in the same round. The branch gets `doperpowers:review-code` at **high** (`doperpowers:reviewer-high`): the bridge change runs inside every session's process and `derive` runs from every machine's daemon.
  Rationale: the stakes sit in the shared code paths, not in the new command.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).
- Decision: The carry list and subscriptions live in `$SMINOS_HOME/managers/<name>.json`, not only in the manager's conversation as presented.
  Rationale: the owner chose "carried forward" for older open items; a compaction or a fresh manager session would lose a list kept only in context. The file holds only what the owner declared (subscriptions) and what the last briefing told them was open; it is not a ledger maintained in the background, which the owner rejected. Told to the owner with an offer to revert.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).
- Decision: One query interface for live sessions, the fork agent (`ask`), replacing the presented split of `btw` without tools and a headless `--tools` fork; the `btw` freshness tail is dropped from scope.
  Rationale: the owner asked for one call that keeps the cache, has tools, stays read-only and interrupts nothing; the spike showed the fork agent does all four. The tail fix served only `btw` as the manager's query path; `derive`, `btw`'s remaining user here, does not need it. The rejected alternative, keeping both paths, made the manager choose between cheap-without-tools and tools-without-cache on every question.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0), on the owner's direction.
- Decision: The headless fork runs under `--permission-mode auto --tools Read,Grep,Glob,Bash`, not `dontAsk` with a Bash allowlist.
  Rationale: the owner's call ("`--permission-mode auto --tools Read,Bash …` is enough"). The allowlist enforced read-only (measured) at the cost of a curated list; auto mode refuses what it judges risky, and read-only rests on the frame. It now serves only sessions with no guarded fork agent.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0), on the owner's direction.
- Decision: The read-only guard is a mod of the doperpowers plugin.
  Rationale: a fork the bridge spawns from its listener bypasses all of sminos's hooks (spike), so the guard must sit in another plugin. The to-human plugin, which already depends on sminos, lost because its purpose is how sessions talk to the owner; raising one of sminos's own hooks so the spawn happens inside a hook frame lost as a contortion on undocumented event semantics. A session without doperpowers gets no fork agent (`no-guard`) and its queries take the headless path. Told to the owner as a placement they may veto.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).
- Decision: Buildability review round 1 fixes: the fork agent's open asks move to their own `$.state` key `bridgeAsk` and their test to `bridge-ask.test.ts` (the `ask` key and `ask.test.ts` belong to the async question tool); bare aliases resolve across every local project, ambiguity exiting 4 with qualified names (`find_target` resolves bare aliases only in the caller's project); the replay is frozen at its cutoff (`--until` on transcripts and the new `pending --until`, no queries, separate empty state per run).
  Rationale: each was a real defect: a state collision that would overwrite queued answers on reload, an advertised cross-project subscription that could not resolve, and replay scores that later answers could contaminate. The alternative for the alias finding, requiring qualified names everywhere, lost because the owner names sessions by alias.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).
- Decision: Spec review round 1 fixes. The guard decides a fixed tool surface (`FORK_TOOLS`) at `tool.call` and read-only Bash at `tool.check`, fails closed (`.catch` refusals, unresolved agents refused), and guard presence must come from the guard registered now. `you` requires an affirmative origin (`you?` for origin-less rows), `you·desk` requires a matching log `human` event, and the bridge's generated wakes are `notice`. Subscriptions and uuids resolve historically when membership has retired a session.
  Rationale: `isReadOnly` alone let `Agent` through (the engine marks it read-only), so a fork could delegate to an unguarded child; `tool.check` never sees a plugin tool served inside its plugin's `tool.call`; the engine skips a throwing hook and falls back to ordinary permissions; the bridge's wakes share owner deliveries' origin and `_is_human` treats a missing origin as human, either of which would put words in the owner's mouth; and sminos retires a seat-less session when its process ends, which would have dropped closed sessions from the briefing. The rejected alternative for the guard, enforcing restrictions transitively on a fork's descendants, needs more machinery than refusing delegation outright, and the fork has no need to delegate.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).

- Decision: Spec review round 2 fix: owner deliveries the log cannot corroborate (MAWS RL10 sends, never logged; deliveries the bridge appends during a running turn or after an Esc) are kept as `you·desk?`, unverified, instead of dropped; an item whose only evidence of an answer is unverified reads "answered (unverified)". Round 2 found no other material defect (guard holds under the plugin order; historical resolution is read-only); review has converged.
  Rationale: dropping them would report already-answered requests as open; counting them as verified would break the rule against putting words in the owner's mouth. Adding a provenance mark to the bridge's delivery rows lost: it changes text every session's model reads and the desk's delivery contract, for a reader that can label uncertainty instead.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).

- Decision: Execution pre-flight. The guard's agent lookup follows Interfaces ("remembers each agent id's verdict once resolved"); M2's decision line "`$.agent.list()` is read per `tool.check` of a subagent loop" is read as: looked up per call until the id's verdict is resolved, then remembered. A resolved verdict is re-derivable (an agent's `type` and `spawnedBy` are fixed at spawn and ids are not reused); an unresolved id (list rejected or lacks it) is refused and never remembered, so the next call looks again.
  Rationale: the two statements read two ways; the Interfaces text is the later, reviewed one, and caching what cannot change loses nothing the guard needs.
  Date/Author: 2026-10-31, plan-executor for doperpowers-9b (f89d7fb0).

- Decision: M1's readings of the entry-kind table against real transcripts (engine 2.1.31x). (a) A peer entry is JSON `kind: "peer"` with `"from": <alias>`, rendered `peer <alias>` in text, so `kind` stays enumerable. (b) Messages and hand-backs from the session's own subagents (origin `peer` with a `senderTaskId`) are `agent`, not `peer`: they are the background agent's result, its `Agent` call's result being only the launch text, which is skipped. (c) Blocking questions (native `AskUserQuestion`, the plugin's with `async: false`) are `asked` at the call and `answered` from a non-error result; async ones still come from `sminos._ask_events`. (d) The bridge's origin is `{"kind": "plugin", "name": "sminos", "asUser": true}` (key `name`); `doperpowers` is accepted as the bridge's plugin too, since older transcripts hold the bridge under its former plugin. (e) A subscription entry stores the project's id under `project` and its name under `project_name` (ids do not collide; historical resolution needs the key). (f) MAWS: human-stamped rows in a MAWS launch (entrypoint `sdk-ts`) are `you·desk`; a MAWS ask's answer steer is `answered`, not also `you` — not yet checked against a MAWS-launched transcript. (g) The owner's `!` shell input stays `you?`; its `<bash-stdout>`/`<bash-stderr>` rows are tool output, left out. (h) `pending` and `subscriptions` pass over a subscription that no longer resolves or is now remote with a line on stderr instead of failing.
  Rationale: each follows the table's intent (never put words in the owner's mouth; keep what the briefing needs) on frame shapes the spec did not foresee.
  Date/Author: 2026-10-31, M1 executor, folded by plan-executor.
- Decision: M1 task-review fixes. A delivery is corroborated only by an owner event addressed to the member's lineage (`sminos.addressed_to`; `to: "*"` corroborates nothing), and a multi-frame push is classified frame by frame. An in-window answer to a blocking question asked before `--since` is still `answered` (blocking calls read from the seek point; a native answer further back recognized by its `toolUseResult` record). An unreadable transcript exits 1 naming it; a lineage session with no transcript is named in `missing`. `pending --until` reports `waiting: []` with `waiting_known: false`, since the waiting state of a past moment is not recorded.
  Rationale: the reviewer reproduced each defect: a `yes` sent to another session verified a delivery, a peer frame rode a human frame's evidence, an owner's decision vanished at the window edge, an unreadable file read as an empty window, and the frozen replay gained today's waiting state.
  Date/Author: 2026-10-31, M1 fix wave, folded by plan-executor.
- Decision: The guard passes an agent id a readable `$.agent.list()` does not name, and refuses only while the list cannot be read. This revises the round-1 sentence that refused unknown ids.
  Rationale: the engine documents that a workflow's agents and its own forks (compaction, memory) carry ids no list names (`AgentLoop.agentId`, 2.1.316). Refusing them would refuse every tool call of every Workflow agent (the code-review panel among them) and of the engine's forks in every session that loads doperpowers, against "every other agent of the session is untouched". A fork the bridge spawns through `$.agent.spawn` is listed from its spawn on (live: identified on its first tool call). It cannot create unlisted descendants, since `Agent` and `Workflow` are outside `FORK_TOOLS`. An unlisted id is never remembered. The rejected alternative, refusing unlisted ids while an ask is starting, needs cross-plugin state for a window the live check found empty.
  Date/Author: 2026-10-31, M2 executor, ruled by plan-executor after the task review flagged it.
- Decision: M2's bridge readings. (a) Guard presence: before each spawn the bridge calls `$.tool.check({tool: 'Read', input: {file_path: '/dev/null/sminos-fork-guard-probe'}})`. The guard's `tool.check` recognizes it (origin plugin `sminos`, no `tool_use_id`, no `agentId`) and answers a fixed `deny` whose reason names the guard. Any other verdict is `no-guard`. The query runs through the hook chain as loaded now, runs nothing and opens no dialog, so a reload that drops the guard turns `ask` into `no-guard`. Both strings are pinned word for word in each plugin's test. (b) The tail is anchored on the last completed response's rows, not sliced at `messageCount`: that count is of API messages (capped at 4,096), while `$.session.messages()` returns transcript rows. The tail renders assistant rows (text, calls with their results); tool inputs are cut to 2,000 characters as results are, and a cut window opens with `[earlier messages cut]`. (c) `nothing-to-fork` is the bridge's own check (`$.session.messages()` empty) before spawning. (d) Refusal order: `bad-prompt`, `busy`, `no-guard`, `nothing-to-fork`; `busy` covers an ask between its check and its spawn, and ends at the fork's `turn.complete`. (e) A managed fork's `tool.check` for any tool outside `Read`/`Grep`/`Glob`/`Bash` is denied, as defense in depth behind `tool.call`. (f) `ask` sits in `capabilities.controls` as always available; `no-guard` is answered at the op. (g) The bridge test harness moved to `sminos/tests/mods/bridge-harness.ts`, so `bridge-ask.test.ts` drives the real bridge.
  Rationale: each follows the spec's intent where the engine's interfaces differ from what the spec assumed (a count that does not index rows; presence that must come from the guard loaded now).
  Date/Author: 2026-10-31, M2 executor, folded by plan-executor.

## Outcomes & Retrospective

Pending — written at finish.
