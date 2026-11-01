# Session manager — a read-only briefing session over the sessions doing the work

The owner runs initiatives that last days and span several sessions at once. P5 (the desk folded into MAWS) ran across "GUI AI agent workspace charter" (`37052769`, project MAWS), `p5-desk-track-owner` (`b4948247`) and `CI-opt` (`a45b97a3`, both project doperpowers), and early on `remote-architecture`. Coming back after hours away, the work has moved far, messages have stacked up in every session, and finding what is owed to whom means scrolling back through each one. What gets lost is the owner's side of the work: questions, decisions, judgments and actions the sessions are waiting on, blocking or not.

After this change the owner keeps one **manager session** open: a Claude session that has loaded the `/sminos:manager` skill. They tell it which sessions to follow and under which initiative, and whenever they come back they ask "update since 9am". It answers with what needs them first (blocking items, then optional ones, then older items still open) and then a written brief per initiative. They can ask follow-up questions, which it answers from the records, from the sessions' transcripts, or by putting the question to a fork of a session. The manager never writes to a working session, so the work it reports on is never interrupted or changed by it.

To see it working: open a new Claude session in any directory on the MacBook, run `/sminos:manager`, say "subscribe P5: GUI AI agent workspace charter, p5-desk-track-owner, CI-opt", then "update since 10 hours ago". The briefing names, for example, the PR merge a session asked you to decide and the `dasd` restart only you can do, each with the session, the time and the message it came from.

This is the semantic half of MAWS's Scene A ("Open MAWS and know within seconds where you are needed", `MAWS/docs/charter.md` §1). MAWS's attention table already covers the mechanical half (a pending permission prompt, a pending question). What sessions *said* they need from the owner, in prose, has no reader today.

A side effect ships with it: `sminos derive`, which forks a session every six hours to learn its in-charge line, moves onto the same fork path and becomes about seven times cheaper for live sessions.

## Progress

- [x] (2026-11-01 01:40Z) Design approved in the authoring session (doperpowers-9b, f89d7fb0); spec written.
- [ ] Independent spec review and buildability review.
- [ ] M1 — the `manager` command: transcript windows, pending items, subscriptions.
- [ ] M2 — queries: the shared fork, the fresh tail in `btw`, `derive` and `manager query` on it.
- [ ] M3 — the skill, the digest brief, the replay evaluation, and acceptance.
- [ ] Whole-branch review (review-code, high), retrospective, merge.

## Terms

- **Session, member.** A Claude Code session. sminos calls every session in a project a *member*; it is named by an alias (`CI-opt`), its short id (first eight hex digits), `@project/alias`, or its full UUID. A member can continue under new session ids (a resumed seat); sminos follows that chain as its *lineage*.
- **Transcript.** The engine's JSONL file for a session, `~/.claude/projects/<dir>/<session>.jsonl` (or under another config dir, which sminos records). The P5 sessions' transcripts are 283–668 MB each.
- **Host events.** What sessions sent their human, recorded by sminos: `message` (a call of `mcp__to-human__message` or a `<message>` span), `question` (an async `mcp__sminos__AskUserQuestion`) and `answered`. Read with `sminos chat <project> --host`.
- **Bridge.** The sminos mod running inside every session (`sminos/hooks/mods/bridge.tsx`), reachable on this machine at `$SMINOS_HOME/bridge/<session>.sock`. It serves the desk's controls, among them `btw`.
- **`btw` (side question).** A bridge op: one tool-less completion over the session's own last request (`$.model.fork`), with a question appended. It writes nothing into the conversation and runs beside a running turn (`sminos/hooks/mods/bridge-btw.tsx`).
- **Headless fork.** `claude -p --resume <session> --fork-session …`: a new process that loads the session's transcript, answers, and is thrown away. `derive_line` in `sminos/skills/sminos/scripts/sminos.py` is today's one user.
- **Digest subagent.** A subagent the manager dispatches for one subscribed session and one window. It reads that session's records and returns its needs, decisions and progress.

## What the owner can do afterward (acceptance)

Each item is checked on the MacBook against live sessions. Commands run from any directory; `manager` is the skill's command (`sminos/skills/manager/scripts/manager`, absolute path printed when the skill loads).

1. **Only the manager sees it.** `/sminos:manager` is offered in the slash menu. A fresh session's model-visible skill list has no `sminos:manager` entry. `sminos help` and the sminos skill are unchanged and mention none of `transcript`, `pending`, `query`, `subscriptions`.
2. **Subscriptions are the owner's.** `manager subscriptions add P5 CI-opt p5-desk-track-owner "GUI AI agent workspace charter"` then `manager subscriptions` lists the three under P5 with alias, short id and project. Subscribing the manager's own session is refused. Nothing is added except by this command.
3. **A window of a 668 MB transcript in seconds.** `manager transcript p5-desk-track-owner --since 10h` prints the window in under 10 seconds: entries oldest first, each labelled (`you`, `you·desk`, `you·steer`, `peer <alias>`, `session`, `→you`, `asked`, `answered`, `compacted`, `interrupted`, `tool`, `agent`, `notice`), no tool results, no thinking, no images. Its first entry is the first one at or after the time given.
4. **A cheap, current answer from a live session.** `manager query CI-opt "What are you waiting on from the human right now?"` answers and ends with a line naming `via btw` and the usage, where cache read is close to the session's context size and cache write is 0. The session's transcript has the same number of rows before and after.
5. **Current, not one step behind.** On an idle session whose last turn ended with a final message to the owner, `manager query <it> "Quote the first sentence of your last message to the human."` returns that last message, not the one before it.
6. **Read-only tools, enforced.** `manager query --tools <member> "What is the newest commit on your branch, and is the PR's CI green?"` answers using git and gh. A probe asking the fork to `touch /tmp/manager-probe` leaves no such file, and the `--json` output lists the denied call.
7. **Stopped sessions still answer.** `manager query <a stopped seat> "…"` answers and names `via fork`.
8. **The briefing.** In a manager session, "update since <T>" produces: *Needs you* (blocking, then optional, then still open from before T), each item with session, time raised, what is needed, why it has to be the owner, and the quoted source; then a prose brief per initiative (what happened, decisions taken on the owner's behalf, changes of plan, where it stands). On the replay window (M3) it finds every blocking item of the labelled list and at least 90% of all items.
9. **`derive` is cheaper and unchanged in output.** `sminos derive <a live member>` prints the member's line as before; the daemon's log shows it went `via btw` with cache read near the session's context. A stopped member's derive still runs the uncached headless fork.
10. **Nothing written.** After a briefing with queries, no subscribed session's main transcript has gained a row because of the manager, and no project log has gained an event from it other than the manager session's own messages to the owner and sminos's membership reconciliation (`joined`/`retired`), which any `sminos list` also performs.

## The design

### Shape

```
 working sessions (the pool)                    manager session
 ┌──────────────┐                               ┌──────────────────────────────┐
 │ CI-opt       │── transcript (read) ─────────▶│ /sminos:manager skill        │
 │ p5-desk-…    │── host events (read) ────────▶│  manager transcript|pending  │
 │ MAWS arch    │◀─ btw (fork, nothing kept) ───│  manager query               │
 └──────────────┘◀─ headless fork (thrown away)─│  digest subagents (Sonnet)   │
                                                └──────────────────────────────┘
```

Every arrow into a working session is a fork: the session's conversation is never appended to, its turn never interrupted, its files never touched by the manager.

### Packaging: a skill only the owner can load, with its own command

The manager is a second skill in the sminos plugin, `sminos/skills/manager/SKILL.md`, whose front matter sets `disable-model-invocation: true`. That field keeps a skill out of every model's skill list and leaves it in the slash menu: the designer plugin's `materialist` skill sets it, and it is absent from a session's listed skills. Its command, `manager`, lives in `sminos/skills/manager/scripts/` beside it and imports sminos's Python modules from `sminos/skills/sminos/scripts/`.

Why: `transcript`, `query` and the rest are needed by the manager alone. As sminos verbs they would sit in `sminos help` and in the sminos skill that every session reads, costing every session context and inviting sessions to fork each other. The strongest alternative, a separate plugin, lost because the command imports sminos's internals, and a plugin reaching into another plugin's versioned cache directory breaks at every update. The one piece sminos and the manager share is an internal function, the fork (§Queries), which `derive` uses too; it adds no verb.

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
| answered | its question has an `answered` event, or the owner's words after it in that session (typed, sent from the desk, or a steer) address it |
| overtaken | the session moved on without the owner: decided it itself, dropped it, or the need went away |
| open | anything else |

When the records leave the status unclear, the digest subagent asks the session through `manager query`.

**Digest subagents run on Sonnet.** Effort is medium or high, whichever the replay evaluation (M3) shows is enough; the skill states the one chosen. They are dispatched with the Agent tool as general-purpose subagents briefed from the reference file, not as a registered agent definition, which would be listed to every session and undo the packaging.

**Strictly read-only.** The manager and its subagents never send, steer, interrupt, answer, decide, compact, change a model, or write to a project log. Its only outward acts are its messages to the owner. This is a rule the skill states, not a lock: the manager needs its own tools to read, and nothing so far suggests a model breaks the rule.

**On demand only.** Nothing runs between the owner's requests: no schedule, no pushes.

### Transcript windows

A session's transcript is far too large to read as a whole (P5's are 283–668 MB, about 15 MB of prose each), so `manager transcript` returns a **condensed window**: what the owner and the session said and did, without what tools returned.

Kept, oldest first: the owner's prompts (labelled by source: typed `you`, from the desk `you·desk`, a steer `you·steer`), messages from other sessions (`peer <alias>`), the session's prose (`session`), its messages to the owner (`→you`, whole), its questions with their options (`asked`) and answers (`answered`), compaction summaries (`compacted`), interrupts (`interrupted`), one line per tool call (`tool`: name and a short argument), each subagent spawn with its description and the first lines of its result (`agent`), and one line per task notification (`notice`). Left out: tool results, thinking, images, system reminders and attachments.

The window starts at the first row at or after `--since` (and stops at `--until`), found by binary search on the rows' timestamps, never by reading the file from its start. It walks the member's lineage in order, marking where one session id ends and the next begins. Output is text by default and `--json` for scripts; past `--max-chars` (default 400,000) it stops with a line saying where it stopped and how to narrow the window.

The row classification is the part most likely to be subtly wrong (a peer's delivery read as the owner's words would invent instructions the owner never gave), so it reuses sminos's existing readers of these frames wherever they exist (M1 names them) and is pinned by fixtures of every frame kind.

### Queries

`manager query <member> "<question>"` puts a question to a fork of the session and prints the answer and its cost. Three paths, chosen in this order:

| Path | When | Tools | Cache (measured 2026-11-01 on a ~100–120k session) |
|---|---|---|---|
| `btw` through the bridge | the session is live and its bridge offers `btw` | none | reads the session's own cache: 120,027 read, 0 written, ≈$0.06 |
| headless fork, no tools | no bridge (stopped, bridgeless) | none | cannot read the session's cache: ≈$0.40 per 100k tokens uncached; caching on, a repeat within the hour reads the fork's own entry ($0.02) |
| headless fork, read-only tools | `--tools` given | Read, Grep, Glob, allowlisted Bash | as above, plus the tool loop: $1.03 measured uncached |

**Why `btw` first.** The prompt cache matches tools, then the system prompt, then the messages, as one exact prefix. `claude -p` rebuilds the system prompt and tool list differently from the interactive session (safe mode drops the plugins; to-human's message tool registers only interactively), so no headless variant reads the session's conversation from cache; `btw` resends the session's last request byte for byte. Measured: four headless variants read 0 or 10,334 tokens of cache; `btw` read all of it. The session's own cache is untouched by any fork: its next requests kept reading their whole prefix.

**The fresh tail.** `$.model.fork` replays the main thread's *last request*, which cannot contain that request's own response or anything after it. On a busy session a `btw` is one step behind; on an idle session it misses the turn's last response, usually the final message to the owner, and every `btw` while the session stays idle forks from that same point. Measured: two consecutive `btw`s on the authoring session both described the session as of the request before the one in flight, and the second did not see the first (forks do not build on each other). The bridge therefore appends to the fork's prompt the messages the session kept after the request the fork replays, rendered as text under a heading saying what they are. The replayed prefix is unchanged, so the cache still serves it; only the tail is billed fresh. This applies to every `btw`, the desk's included, since a fresher answer is better for both.

**Read-only tools.** `$.model.fork` is one completion with every tool denied, and the plugin API has no way to continue it with tool results, so `btw` cannot have tools. `--tools` uses a headless fork in `dontAsk` permission mode with a fixed allowlist: anything not listed is refused by the harness and reported in the result's `permission_denials`. Measured: `git log` and Read ran; `touch` was denied by the harness; Write was not offered; no file appeared. Plan mode, the alternative, only told the model it was planning: the model declined the writes itself, which proves nothing. The allowlist guards against accidental writes by a cooperative model, not against a hostile one (`git diff --output=<file>` would still write); that residue is accepted.

The question is framed so the fork answers as a fork: it is told it is a read-only copy asked by the owner's manager, that the session never sees the exchange, and (without `--tools`) to answer from the conversation without tools or continuing its task.

### `derive` on the shared fork

`derive_line` today always runs an uncached headless fork, deliberately: the fork cannot read the session's cache, and the next derive of the same session is six hours away, after any entry it wrote has expired. That costs full input price every time: one derive-style fork of the authoring session read 104,990 tokens for $0.42, and this Mac's daemon ran 39–77 derives a day over Oct 27–31. Derive only runs on sessions active in the last hours, whose cache is usually warm, so through `btw` the same question costs about a seventh. `derive_line` moves onto the shared fork: `btw` when the member's bridge answers, else the uncached headless fork it runs today. Its prompt, its parsing, its failure stamps and its timeouts stay as they are.

### What is left to measure

- Whether Sonnet at medium effort sorts blocking from optional as well as at high: the replay evaluation decides (M3).
- What a `btw` costs when the session's cache has lapsed (idle over an hour): recorded in Surprises & Discoveries during M2.
- What one briefing costs, ten hours across four sessions: recorded during M3.

## Execution

### Constraints that bind every milestone

- **Read-only toward working sessions.** No code path of the `manager` command appends to a session's conversation, interrupts its turn, edits its files, or writes an event to a project log. It never runs, or calls the functions behind, sminos's `say`, `send`, `steer`, `interrupt`, `answer`, `decide`, `compact`, `model`, `charge`, `status` or a cursor-advancing `chat`. The one exception it inherits is sminos's own membership reconciliation, which any sminos read (`list`, `chat`, `find_target`) may perform.
- **This Mac only.** A member whose session runs on another machine is refused with a message naming the machine (`manager: CI-opt runs on mini; this version reads sessions on this machine only`). Cross-machine reading is out of scope.
- **sminos's conventions.** Detail beside code: the new skill's command gets its own `sminos/skills/manager/scripts/CLAUDE.md`; `sminos/CLAUDE.md` gains one sentence pointing at it; the bridge's and derive's notes in the existing nested CLAUDE.md files are updated where their behavior changes. No CLAUDE.md is placed where a loader reads every `.md`.
- **Tests run in isolation.** Every test isolates `HOME` and `SMINOS_HOME` as `sminos/tests/run-sminos-tests.sh` does; none touches the real `~/.claude/sminos` or a live session. Live checks happen only in the acceptance run (M3).
- **Version.** One bump of the sminos plugin on the branch, in M3, with `scripts/bump-version.sh --plugin sminos`.
- **Verification.** Before a milestone is reported done: its tests pass locally (one focused file while iterating is fine), and `ci-gate` from the worktree is green for the `sminos`, `sminos-suites`, `sminos-mods` and `mods-types` gates on the committed HEAD.

### Orientation

Paths below are repository-relative. The sminos CLI is `sminos/skills/sminos/scripts/sminos.py` with sibling modules in the same directory (`sminos_bridge.py`, `sminos_control.py`, `sminos_subagents.py`, `sminos_jobs.py`, …); its nested `CLAUDE.md` describes each. Sibling modules import it by plain name (`import sminos as S`) after putting the scripts directory on `sys.path` (`sminos_rpc.py` and `sminos_plane.py` show the pattern). The bridge mod is TypeScript under `sminos/hooks/mods/`. Tests: `sminos/tests/run-sminos-tests.sh` (a fake `claude` binary on `PATH`, `HOME` and `SMINOS_HOME` isolated; it has no discovery: each test file is called by name from `run_suites()`), and `sminos/tests/mods/run.sh` for the mods (`claude plugin test`).

### Interfaces and Dependencies

**Files (new).**

    sminos/skills/manager/SKILL.md                    # M3
    sminos/skills/manager/references/digest-brief.md  # M3
    sminos/skills/manager/scripts/manager             # M1: sh launcher, as sminos's own
    sminos/skills/manager/scripts/manager.py          # M1: the CLI
    sminos/skills/manager/scripts/manager_window.py   # M1: transcript window reader and row classifier
    sminos/skills/manager/scripts/CLAUDE.md           # M1, extended in M2 and M3
    sminos/tests/test_manager.py                      # M1, extended in M2

`manager.py` puts `realpath(<its dir>/../../sminos/scripts)` on `sys.path` and imports `sminos`, `sminos_bridge`, `sminos_subagents`. It never calls `sminos.main()`; it calls `sminos.forget_caches()` only if it ever runs more than one resolution per process.

**Commands.** Every command takes `--json`; text output is for the manager model to read, JSON for tests and scripts. Exit codes follow sminos's: 0 success, 1 failure with a message on stderr, 2 usage, 4 an unknown or ambiguous member (as `find_target` exits).

    manager transcript <member> --since T [--until T] [--max-chars N]
    manager pending [--name N]
    manager subscriptions [--name N]
    manager subscriptions add <initiative> <member>... [--name N]
    manager subscriptions remove <member>... [--name N]
    manager carry [--name N]
    manager carry set (--file PATH | -) [--name N]

`T` is local time: `9am`, `14:30` (today; a clock time later than now means yesterday), a duration back from now (`10h`, `90m`, `2d`), or an ISO-8601 time.

**Member resolution.** `sminos.find_target(q)` (it accepts alias, short, `alias#short`, `<project>/<alias>`, full uuid). A seat resolves to its member through `sminos.members(project)`. The member's sessions, oldest first, are `reversed([m.session] + list(m.former))`. A member whose `local` is false is refused (constraint "This Mac only"). `find_target` may let sminos reconcile the project's membership (append `joined`/`retired` events), as `sminos list` does; that is sminos's own bookkeeping, not a manager write.

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
| `you` | the owner typed it | a non-meta user row of human/composer origin that is not a slash-command echo (`sminos.is_turn_record`, `sminos._is_human`), or a `queued_command` attachment typed mid-turn |
| `you·desk` | the owner's words sent through the desk or MAWS | the bridge's delivery of an owner event (user row, origin `plugin` `sminos`, `asUser`), MAWS steers (`sminos._maws_steer_texts`) |
| `you·steer` | an owner steer | user row whose first line is `[sminos steer from human]` (`STEER_LINE`, `sminos/hooks/mods/bridge.tsx`) |
| `peer <alias>` | another session's message | `[sminos chat …]` / `[sminos message from …]` frames (`compose_chat_frame`, `compose_frame`), the engine's `cross-session-message` envelope (`PEER_TAG`) |
| `session` | the session's prose | assistant text blocks, except the response a hook made up (`answeredWithoutRequest`) |
| `→you` | a message to the owner, whole | message-tool calls (`MESSAGE_TOOLS`, read as `sminos._sent_text` does) and `<message>` spans (`sminos.extract_marks`) |
| `asked` / `answered` | a question to the owner and its answer | `sminos._ask_events`, `sminos._deliveries` |
| `compacted` | a compaction summary | user rows with `isCompactSummary` |
| `interrupted` | an Esc or a bridge interrupt | `[Request interrupted by user]` (`INTERRUPT_MARKER`), the bridge's cut-off row (`CUT_OFF_LINE`) |
| `tool` | one line per tool call | `tool_use` blocks: name and its most telling argument (a command, a path, a pattern, a description), cut to 160 characters |
| `agent` | a subagent spawned | `Agent`/`Workflow` calls: description and type; the first 600 characters of its result |
| `notice` | a background task finished | rows of origin `task-notification` (`sminos_jobs._plain_notification`) |
| `boundary` | the lineage moved to the next session id | emitted by the walker |

Everything else (tool results other than an agent's, thinking, images, system reminders, hook context, attachments not listed) is left out. A row the classifier cannot place is left out, never guessed into `you`: inventing the owner's words is the worst error this reader can make.

The window's start is found with `sminos_subagents.offset_since(mm, t)` on an mmap of the transcript (it returns a line start at or before the first row stamped at or after `t`, within 1 MiB, or 0), then rows before `t` are skipped while scanning forward. The whole file is never parsed: `sminos.transcript_rows` reads the whole file and must not be used here.

**`manager pending --json`:**

    {"unanswered": [{"member": "CI-opt", "session": "a45b97a3-…", "asked": "…Z", "question": "…", "src": "toolu_…"}],
     "waiting":    [{"member": "p5-desk-track-owner", "session": "…", "since": "…Z"}]}

`unanswered`: `question` host events of every subscribed session (any age) with no `answered` event of the same `src`. Read both places a host event can live, the log and the host store (`sminos._own_events(project, sid, "log")` and `(project, sid, sminos.HOST_STORE)`); an answer can sit under the asker's writer. `waiting`: subscribed members whose `Member.state` is `waiting`.

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

QUERY_INTERFACES_PENDING_SPIKE

### M1 — The `manager` command: windows, pending items, subscriptions

At the end of M1 the owner (or a session) can run `manager transcript <member> --since 10h` on any local session and read its condensed window in seconds, `manager pending` for unanswered questions and waiting sessions, and `manager subscriptions …` / `manager carry …` to keep the manager's state. Nothing yet asks a session anything.

- **Touches:** `sminos/skills/manager/scripts/` (new), `sminos/tests/test_manager.py` (new), `sminos/tests/run-sminos-tests.sh` (`run_suites()` calls the new test file), `sminos/CLAUDE.md` (one sentence pointing at the manager's `scripts/CLAUDE.md`).
- **Exposes:** the commands, JSON shapes, entry kinds and state file in Interfaces.
- **Decisions:**
  - The classifier lives in `manager_window.py` and reuses sminos's readers named in the entry-kind table instead of re-deriving frame formats; where no reader exists (compaction summaries, interrupts, steers, the `[sminos chat` frames), it keys on the constants named there and its fixtures pin them.
  - Lineage boundaries are emitted as `boundary` entries so a reader sees where a session continued.
  - `--max-chars` defaults to 400,000 characters of rendered text; past it the walk stops and says the last timestamp reached and suggests a later `--since` or an `--until`.
  - Speed target: a 10-hour window of a ~670 MB transcript renders in under 10 seconds on the MacBook (acceptance 3). If `offset_since`'s 1 MiB granularity or the forward scan misses it, measure before optimizing and record the figure in Surprises & Discoveries.
- **Does not touch:** the sminos CLI's verbs, `sminos help`, the sminos skill, the bridge, `derive`.
- **Proves:** acceptance 2 and 3. Tests pin: each entry kind from a fixture row of that kind; a peer frame never classified as `you`; an `answeredWithoutRequest` row dropped; an unknown row dropped; the window starting at the first row at or after `T` in a generated file of at least 50 MB; a two-session lineage walked oldest first with one `boundary`; time parsing of each `T` form, including a clock time later than now meaning yesterday; `--max-chars` truncation; `pending` matching questions to answers by `src` across the log and the host store; `subscriptions add` refusing the manager's own session and a remote member; the state file written 0600 and replaced whole.

QUERY_AND_SKILL_MILESTONES_PENDING_SPIKE

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

## Decision Log

- Decision: Verification. One independent spec review (technical-heavy: `doperpowers:adversarial-reviewer`) and, since the execution has three milestones, the adversarial reviewer's buildability review of the execution section, in the same round. The branch gets `doperpowers:review-code` at **high** (`doperpowers:reviewer-high`): the bridge change runs inside every session's process and `derive` runs from every machine's daemon.
  Rationale: the stakes sit in the shared code paths, not in the new command.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).
- Decision: The carry list and subscriptions live in `$SMINOS_HOME/managers/<name>.json`, not only in the manager's conversation as presented.
  Rationale: the owner chose "carried forward" for older open items; a compaction or a fresh manager session would lose a list kept only in context. The file holds only what the owner declared (subscriptions) and what the last briefing told them was open; it is not a ledger maintained in the background, which the owner rejected.
  Date/Author: 2026-11-01, doperpowers-9b (f89d7fb0).

## Outcomes & Retrospective

Pending — written at finish.
