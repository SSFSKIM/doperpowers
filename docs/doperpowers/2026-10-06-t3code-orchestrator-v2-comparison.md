# T3 Code Orchestrator V2 ↔ sminos — comparative analysis

> **Date:** 2026-10-06 (three days after V2's first nightly; sminos at 7.135.0).
> **Purpose.** T3 Code's Orchestrator V2 and sminos are independent answers
> to the same question: how one person runs a tree of coding agents that
> outlive a terminal, talk to each other, and reach the human only when they
> must. This doc maps the two component-by-component, judges superiority per
> axis (not overall), lists what is worth importing, and isolates the
> **forked decisions** (§6) where both sides made a deliberate, defensible,
> *diverging* bet — the discussion agenda. Same shape as
> `2026-07-11-symphony-comparison.md`; that doc compared the *board pipeline*
> to a ticket scheduler, this one compares the *seat substrate* to a thread
> runtime.
>
> **Sources — T3 Code** (`github.com/pingdotgg/t3code`):
> - PR #2829 *feat(orchestrator): introduce new orchestrator* — opened
>   2026-05-27, merged 2026-10-02, +380,729 / −203,651 over 1,912 files. Its
>   body is a mechanism-by-mechanism "Closes" / "Supersedes" ledger of ~190
>   issues, each naming the V2 service that removes it. Cited as **PR**.
> - Release notes, `v0.0.46-nightly.20261003.2610`, the first V2 nightly.
>   Cited as **RN**. V2 is nightly-only; no stable release carries it; the
>   mobile app needs the V2 beta; the V1→V2 database migration is one-way.
> - Source digest: `research/2026-10-06-t3code-orchestrator-v2/digest.md`
>   (file paths, type definitions, RPC names). Cited as **D**.
> - Community CLI `@bvdm/t3code-cli` v0.3.0 (protocol 2 only), the skyflo
>   compare page, Theo's X posts via search snippets (x.com is not
>   fetchable).
>
> **Sources — ours:**
> - `skills/sminos/SKILL.md`, `references/spawn-preamble.md`,
>   `scripts/sminos.py` (≈3.1k lines; ≈4.4k with chart, TUI, lib),
>   `tests/sminos/run-sminos-tests.sh` (856 assertions).
> - Specs: `specs/2026-09-05-sminos-human-stream-design.md`,
>   `specs/2026-09-26-sminos-family-chat-design.md`,
>   `specs/2026-09-29-sminos-one-name-one-state-design.md` — each with its
>   Decision Log, Surprises, and live-proof evidence.
> - The layer above: `skills/issue-tracker/` (the board, sweeps, dispatch,
>   review loop), `hooks/mods/` (`to-human.tsx`, `agents.tsx`),
>   `output-styles/to-human.md`, afleet (`~/Developer/GitHub/afleet`, at C1
>   of a 17-step roadmap). `docs/doperpowers/TECH-DEBT.md` rows 27–30.
>
> **Status: agenda open.** §6's forked decisions await discussion.

---

## 0. Verdict up front

The two systems differ on one question and everything else follows from it:
**who owns the truth about a running agent?**

- **T3 Code: the server.** V2 is an event-sourced orchestrator — commands
  serialized per thread under a lock, each committing its events,
  projection updates, idempotency receipt, and outbox effects in one SQLite
  transaction (`EventSink.commitCommand`); provider output ingested as
  events directly (`ProviderEventIngestor`); a leased effect worker doing
  the provider work. Provider state is *reconciled against* the log, never
  trusted as the log. Every V2 feature
  (durable queue, settlement, lineage, restart recovery, limits, mobile
  steering, delegation across seven provider drivers and any ACP-registry
  agent) is a projection of that one
  decision, and so is its cost: a 380k-line rewrite, a one-way migration,
  and an adapter per provider whose races fill the PR's ledger.
- **sminos: the harness.** A seat's record carries only what Claude Code
  does not keep — its alias, group, role, parent, and the family chat. Its
  state word is read live from the harness's own session record
  (`~/.claude/sessions/<pid>.json`), one socket probe, and whether the
  transcript is on disk; delivery rides the harness's inbox socket; resume
  is `claude --bg --resume`; isolation is the harness's `--worktree`. The
  orchestrator is not a process. Every harness improvement arrives for free;
  everything the harness does not expose — a queue, a mid-turn interrupt,
  a usage-limit state, cross-provider handoff — does not exist.

Per-axis superiority is clear and split:

| axis | winner | evidence anchor |
|---|---|---|
| Runtime durability (restart, queue, limits, stuck states) | **T3** | the PR's ~190-issue ledger is V1's "derived state" failure class, closed by server-owned state (§2.2, §2.4) |
| Multi-harness | **T3** | seven built-in drivers, one of them a generic ACP-registry adapter, behind one adapter interface; sminos is Claude-only by a September decision (§2.5) |
| Agent-to-agent *conversation* | **ours** | a recorded, addressed, reach-scoped family chat read before acting; T3 children are read-only threads reached by point-to-point tools (§2.3) |
| Agent-to-agent *delegation* (a child on any provider, a typed result, fork + merge-back) | **T3** | `delegate_task` ends in a result the parent receives as such; sminos results are prose in a chat, Claude-only, no fork (§2.3). Their `wait` is not part of the lead: a pull model needs it, a push model does not (§5) |
| Human surface | **T3** | desktop/web/mobile, Working section, phone steering, lineage; ours is `list`/`chart`/`tui`, in-harness mods, afleet at C1 (§2.7) |
| Human-attention doctrine | **ours** | the agent decides what to send (`<to-human>`/`<essential>`/`<need-input>`, evaluated 5×5); T3's "needs attention" is runtime state (§2.7) |
| Work semantics above the runtime (tickets, gate, review, merge) | **ours** | the board; T3 has settle + linked PRs + schedules and no gate, no review species (§2.8) |
| Checkpoints, rollback, fork | **T3** | server-coordinated workspace + conversation rollback, fork from any finished run; ours is worktree + git, the harness's own rewind undriven (§2.6) |
| Coupling cost and upgrade path | **ours** | ≈4.4k lines over a handful of one harness's internals vs ≈380k lines of server + adapters + migrations (§2.10) |
| Safety for unattended agents | **parity, different shapes** | T3: persisted runtime requests, four permission levels, agents cannot self-approve; ours: `--permission-mode auto`, `waiting` + `reply` + `send`, gateway scrub (§2.9) |
| Scale evidence | **T3**, by orders of magnitude | a nightly user base that filed migration bugs within the weekend, a community CLI on protocol 2 the next day, 15k issues and PRs; ours is n=1 live proofs (§8) |

The right move is **not** to T3-ize (an event-sourced server owning every
session) but to import two things their runtime proved matter and ours
lacks — a *usage-limit* state with a reset time and *restart continuity*
for family seats — as registry reads, keeping the harness-as-truth
architecture (§4, §5). The genuine
strategic fork is the human surface (FD-4): T3 Code is the surface we have
not built, and it cannot host sminos seats.

---

## 1. The two bets

**T3's origin.** T3 Code is an "agent harness control surface": the harness
(Claude Code, Codex, …) keeps its own loop and tools; T3 supplies the
unified interface, persistent threads, worktrees, checkpoints, and remote
access on top. V1's orchestrator derived thread state from provider streams,
and the PR's ledger is the bill: stuck "Thinking" states, duplicate
dispatch, lost queued messages, settled threads waking themselves,
subagent text spliced into the parent, usage-limit stops with no resume.
V2's answer is a database: *"you're not putting a new database under a
feature flag"* (a maintainer on why V2 shipped unflagged, quoted
second-hand). The design is an
event-sourcing core — `ThreadCommandExecutor` is a
`KeyedSerialExecutor<ThreadId>`; V1's decider was deleted (PR #14017) and
each command commits its own events, projections, receipt, and outbox in
one `sql.withTransaction`; `IdAllocator` mints ids so a projection never
keys on a provider-supplied one — with the provider behind an adapter
whose output is ingested as events. Their economics: a product
for many users who pay for several harness subscriptions, used from a phone
as much as a desk, where a thread that wedges is a support ticket.

**Our origin** (`orchestrating-daemons`, in place by July 2026; renamed
agora, then sminos): a Claude-run fleet of durable background sessions for
one operator.
The first version carried its own status (`working`/`blocked`/`done`/…),
addresses, and two delivery verbs; three September specs tore most of it
out in favor of what the harness already keeps. The one-name spec's
retrospective says the lesson: *"test the predicate behind a state word on
the real system before it names anything"* — `gone` was defined by the
harness's job list and had to be redefined by the transcript's presence,
because that is what a resume actually needs. The family-chat spec makes the
coordination bet explicit: a family is **derived** from the spawn tree, not
declared; the chat records *what was said* while the repository and its
specs hold *what was decided*; a seat sees only its family because *"an
agent that can list fifty seats will read fifty seats."* Our economics: one
operator, one harness, review attention as the bottleneck (the Symphony
doc's §1), and every line of runtime code a liability against a harness
that ships weekly.

The cleanest statement of the disagreement: **T3 builds the runtime it
wishes the harnesses had; sminos builds only what Claude Code's runtime
does not.** T3's bet is right when you must host several harnesses or many
users, because then no single harness can be the truth. Ours is right when
the harness is one and its internals are readable, because then owning a
second copy of its state is the race V1 lost.

A second, smaller disagreement sits inside the first: **delegation as a
tool call vs coordination as a conversation.** T3's parent calls
`delegate_task` and is woken with results; the child is a thread it can
read but that cannot address its siblings. A sminos host spawns, then
idles; a child's `say` wakes it; siblings tag each other; a re-filled seat
reads the chat first. Both wake the parent on completion (§7); they differ
on whether the children form a team or a result set.

---

## 2. Component-by-component

### 2.1 The unit: thread vs seat

**T3.** An app *thread* is the unit: it contains *runs* (the counted
turns), each run a tree of execution nodes, with native provider threads
attached as handles — one app thread may use several provider threads over
time, and one Codex session may host several app threads (D §1, §3). Run
state is the enum
`preparing|queued|starting|running|waiting|completed|interrupted|failed|cancelled|rolled_back`;
a thread has no status of its own — its shell status is `idle` or the
latest run's — and `settled`, `snoozed`, `pinned`, `archived` are timestamp
fields on the thread (D §1). A delegated child is a thread with its own
provider-native history; a *native* subagent (a Claude sidechain, a Codex
collab thread, an OpenCode child session, a Cursor task, a Grok task
envelope) is projected into the same lineage as a read-only child thread
with model, status, progress, result, duration (RN, PR:
`SubagentProjection`). Identity is server-minted (`IdAllocator`). Threads
carry server-side read state (`thread.visit` → `lastVisitedAt`,
`thread.mark-unread`), a linked-PR snapshot, a recorded `branch` and
`worktreePath`, and a title the server regenerates.

**Ours.** A *seat* is the unit: a named position in a group with a role,
which a session fills and outlives — `fill --resume` continues the saved
session, `fill` starts fresh in the same seat. The seat id is the first
session's uuid; the record is `$SMINOS_HOME/<seat-id>.json`; the harness
name of the session *is* the alias (`claude --bg -n <alias>`), so native
`SendMessage` and `@alias` tags and the operator all use one name, unique
per group. A native subagent (`Agent` tool) is not a seat; it is drawn by
the harness's own `[N subagents]` pane (`hooks/mods/agents.tsx`, a tree from
`$.agent.list()`'s `parentId`), not by sminos.

**Judgment.** Same shape — a durable, named unit a process fills, with
parent lineage and a workspace — reached independently. T3's is richer
(read state, pins, snooze, title, linked PR) because its unit must carry a
product's sidebar; ours carries a role and a brief because its reader is
the agent's `list`. One real difference: T3 projects *native* subagents
into the lineage; sminos leaves them to the harness. Right for us — the
harness draws them itself now — and a place T3 had to do work because it
hosts harnesses whose subagents it cannot otherwise see.

### 2.2 The runtime: event-sourced server vs the harness as runtime

**T3.** Per thread, commands are serialized under a lock;
`EventSink.commitCommand` commits events, projections, the idempotent
command receipt, and the outbox in one transaction; provider output writes
events directly through `ProviderEventIngestor` with no command; the
`EffectWorker` (leased) performs provider I/O and checkpointing from a
SQLite outbox whose effects are split into ones safe to replay after a
restart and ones tied to the lost process; `RunFinalizationService`
separates run finalization from provider turn completion;
`ProviderSessionManager` owns sessions keyed by provider instance + thread
(`orchestration_v2_projection_provider_sessions`);
`ProviderRuntimeRecoveryService` reconciles non-terminal runs against the
provider's actual inventory at startup and shutdown. On restart: queued
runs are held until the user resumes them, pending approvals become
`not_resumable`, delegated children are reconciled as their own threads,
and optional restart continuation goes through the outbox and respects a
Stop the user requested (D §8). History is read by keyset paging from the
append-only log; snapshots are bounded; text deltas are coalesced before
persistence. The V1 log is never replayed: `LegacyV1ThreadImporter` reads
projections from a copied `statev2.sqlite`. External clients speak
`orchestration.dispatchCommand`, `orchestration.launchThread`, and the
subscribe/get calls over a WebSocket that refuses an upgrade without
`?orchestrationProtocol=2` (HTTP 426); a scope middleware requires
`orchestration:operate` for writes and `orchestration:read` for reads
(D §10). (PR, D.)

**Ours.** No server. The runtime is Claude Code's: `claude --bg` (detached,
permission mode `auto`, display name = alias), the harness's per-session
record with `status` (`busy`/`idle`/`waiting`/`shell`), `waitingFor`, and
`messagingSocketPath`; the transcript at
`~/.claude/projects/<cwd-slug>/<session>.jsonl` as the durable record;
`claude --bg --resume <id>` as the continuation; the harness's own queue
for a frame that lands mid-turn (observed: `queue-operation enqueue` →
`absorbed_mid_turn` beside the next tool result, or `dequeue` into a new
turn at an idle session). sminos adds a registry under one `flock`, a
per-chat `flock`, atomic rewrites, and generation guards for `--wait`
watchers. The recorded status (`working`/`done`/…) still exists for the
board pipeline's seams and has left every human-facing surface.

**Judgment.** T3's runtime is objectively the more capable artifact, and
its value is conditional on owning the session — which is the one thing we
decided not to do. The Symphony comparison's §2.5 verdict transfers
verbatim: a resident consumer is what makes streamed events, a queue, and a
stall detector possible, and we removed that process deliberately. What is
new since July is that the harness itself closed most of the gap we felt
then: background sessions, an inbox socket with a documented-in-code
injection recipe, a sessions registry, native worktrees, a subagent tree
pane. sminos's September work was mostly *deleting* runtime (the board
verbs, two status columns, `addr`, `wake`, the codex process arm) because
the harness now keeps that state. T3 had the opposite experience with the
same harnesses: its V1 derived state from them and broke; V2 stopped
trusting them. Both are correct responses to "the provider's state is not
your state" — one by not keeping a copy, one by keeping the only copy.

What we lack that they have, concretely: (a) a **queue** of messages to a
busy seat that survives restart and can be edited (the harness absorbs
mid-turn or starts a turn; nothing is held); (b) **restart continuity**
(after a reboot every seat reads `stopped`; the board sweep resumes bound
workers, family seats wait for a `send`); (c) a **usage-limit** state with
a reset time (today a limit ends the turn — this doc's own digest agent,
on an astra gateway route, died with `400 … at its usage limit until
Oct 9` and read as a failed agent, not a limited one); (d) **mid-turn
interrupt** short of `resume`
(which stops the turn and relaunches). What we have that they do not: no
migration ever, and a seat that resumes from the harness's transcript with
context intact — the same recovery verb the Symphony doc found strictly
better than re-dispatch, which T3 also chose (native resume with
`excludeTurns`, and a "budgeted context handoff" rebuild only when the
native session is gone).

### 2.3 Delegation and coordination: `delegate_task` + thread MCP vs `spawn` + family chat

**T3.** Agents reach the orchestrator through an authenticated MCP server
named `t3-code`. Its orchestrator toolkit has 16 tools: `delegate_task`,
`task_status`, `task_cancel`, `create_threads`,
`t3_thread_list/read/update/send/wait/interrupt`, `schedule_task` and its
siblings, and `request_secret`; workspace, PR, and thread tools
(`t3_thread_fork` and merge-back, `t3_worktree_handoff/status/list`,
metadata, previews) sit in separate toolkits (D §4, PR). `delegate_task`
hands work to a child agent *on any provider or model* — cross-provider
children are its explicit purpose — with its own options and role; the
child **gets only the task prompt**; its permission and interaction modes
inherit the parent's as a ceiling and **can only narrow**; it is a thread
with provider-native history and ends with a *result*. There is **no
follow-up API for a task** — each review round is a new `delegate_task`
(D §4). Completion reaches the parent as a **durable mailbox wake**, not a
tool result (except in `mode:"wait"`): the server starts a run on the
parent saying "Delegated task X reached a terminal state. Use
`task_status`…", steered into the active turn where the provider supports
it, queued otherwise, with delivery tracked per task
(`pending → claimed → acknowledged | delivered | disposed`) (D §4). A
parent can read *any* thread's transcript with `t3_thread_read`. Subagent
threads are read-only: *"message the parent instead"* (RN). Nesting is
unbounded (every child sees `delegate_task`). Attach a thread as context
with `@thread-name`. Native `/goal` exists for Codex and Claude (PR
#15592).

**Ours.** From a family seat, `spawn <alias> "<task>" [--role] [--worktree]`
makes a child in the caller's group with the caller as parent; the child
boots with `spawn-preamble.md` rendered into its task and its first
instruction is `sminos chat -n 30`. `say` writes one message to one chat
(the host's or the caller's own) and *pushes* by tag: untagged flows to the
host (a report up) or, from a host, to its children (a direction down);
`@alias` targets a member and *resumes a stopped one*; `@all` pushes to
live members without resuming. The frame's first line carries the chat,
id, sender, targets, and `unread n` computed from a read watermark
(`chat_seen`) and the record's `delivered` map. A seat reaches only its
parent, siblings, and children; anything else is the native
`ListAgents`/`SendMessage`, unrecorded. A host idles between events; a
child's `say` starts its turn; when its children are done it integrates and
`retire --cascade`s. Live proof (2026-09-27): a three-level family, the
report up woke the idle host, the tagged answer reached both children, the
grandchild was refused an uncle, the cascade retired the tree in order;
≈$0.20 of sonnet per seat.

**Judgment.** This is the axis where the two systems are most different
and each is ahead on half of it.

*Where T3 is ahead:* **typed results, any provider, fork.** A
`delegate_task` child ends with a *result* the parent receives as such —
in `mode:"wait"` as the tool's return, otherwise as a mailbox wake carrying
batched results; ours is the child's last untagged `say`, prose in the
chat. **Cross-provider children** (Claude plans, Codex implements) and
**fork + merge-back** of a thread's context have no counterpart here.

What is *not* part of their lead, though it reads like one: the wait.
`t3_thread_wait` and `mode:"wait"` exist because a T3 parent is otherwise
a tool-calling agent that would poll `task_status`; the mailbox wake is
their answer to that, bolted onto a pull model. A sminos host is pushed:
a child's `say` is a frame on the host's socket — an idle host starts a
turn on it, a busy one absorbs it at its next tool round (observed:
`absorbed_mid_turn`), and two frames in the same second split between the
two paths without loss. The host's "join" is its judgment on each wake,
with `chat -n 30` showing which children have reported. A `wait` verb
would be a long-blocked tool call inside the host's turn — the seat reads
`busy` while it does nothing, the Bash tool's timeout bounds it, and the
operator cannot tell waiting from working — which is the shape the push
model exists to avoid. The one cost of push, N reports = N host turns, is
the price the family-chat design accepted on purpose; and the strict
"fan out N, collect N" shape is what this plugin routes to *native
subagents* (SDE's per-milestone dispatch, review-code's panel), whose
completion the harness already returns as a result.

*Where we are ahead:* **the team is a conversation, not a result set.**
Siblings address each other (`@b your migration renames a column I read`);
the record is shared memory a re-filled or newly spawned seat reads before
acting, where a T3 child starts with *only its task prompt* and a handoff
is a budgeted selection of verbatim messages (16k tokens by default, D §2);
a host follows up with `say @child …` or `send`, where T3 has no follow-up
on a task and starts a new one per round; who is pushed — and who is
*resumed* — follows the message's shape, so a tag means "I need you" and a
broadcast never starts a paid turn; reach is enforced in the CLI so the
tree is the agent's whole world. T3's child cannot reach its siblings and
has no group record; what the parent learns is what each child returns.
Their read-only-child rule and our reach rule are the same instinct
("message the parent") — ours keeps one more edge (sibling) that the live
proof showed is used. Their completion *mechanism* — a durable mailbox
wake with per-task delivery states, steered mid-turn or queued — is the
same thing our `say` to a host is (a frame the harness absorbs mid-turn
or dequeues into a turn, recorded with a `delivered` outcome per member);
they built the queue, we observed the harness's.

*Convergent:* the parent is woken by a child's completion in both; the
child is a full session in both, never text spliced into the parent (T3
closed three issues on exactly that splice). No import on this axis; the
wait was considered and dropped (§5).

### 2.4 Liveness, state words, and recovery

**T3.** A thread's shell status is `idle` or its latest run's state
(§2.1's enum); `waiting` carries pending `approval_request` /
`user_input_request` runtime requests, persisted and restart-surviving;
**Limited** is a usage-limit stop with resume-at-reset or
snooze-until-reset by `UsageLimitRecoveryWorker`; a failed turn stays a
transcript item instead of wedging the thread. A thread **requires
attention** when it has a pending approval or question, an actionable plan
in plan mode, or a finished or failed run; everything else active, a PR
watch included, folds into the Working section (D §5). **Wake** means two
things: un-snooze, or a server-generated run — a background notification,
a delegated result, PR-watch news, a restart continuation (D §1).
**Settle** is an auto-settle sweep: after three idle days or a merged or
closed PR, never with a pending approval, a live run, or background
subagent/monitor work (D §1). Liveness is a projection
(`provider-session.attached/updated/detached`); idle provider sessions are
detached and rebuilt on the next turn. Interrupt is a serialized command
that handles runs still in `preparing`/`starting`. Stop also covers
background work after the foreground turn ends. "Continue threads after
restarts" resumes interrupted threads after an update, crash, or reboot;
the agent is told which background work died. (RN, PR, D.)

**Ours.** One state word of seven — `busy`, `idle`, `waiting`, `stopped`,
`gone`, `vacant`, `retired` — read in that order from the seat record, the
harness's session record plus one socket connect, and the transcript's
presence; `list` on the real registry answers in 0.45 s and never runs
`claude agents`. `waiting` carries `waitingFor`; `sminos reply` renders the
pending question or the `[blocked on a harness prompt …]` marker; `send`
answers it, resumes a `stopped` seat, and refuses `vacant`/`retired`/`gone`
in one line pointing at the verb that reaches it. Recovery of *pipeline*
seats is the board sweep's (launchd, 5 min): bounded auto-resume with a
nudge, three attempts, then park `needs-human`; board-driven cancel of a
live worker on a terminal ticket. A *family* seat that dies mid-turn reads
`stopped` until its host or the operator sends to it.

**Judgment.** Our state vocabulary is the harness's own and it is honest —
the September work's point was that a word must not promise a resume that
fails. T3's vocabulary has two words we need and cannot derive today:
**Limited** (the reset time is in the error text the harness returns, and
the board sweep's three blind retries are the wrong policy for a limit
that lifts at a known hour) and the restart-continuity notion of "this
seat was mid-turn when the machine went down" (the transcript's last
record shows it; nothing reads it). Both are registry reads, not runtime
(§4.1, §4.2). What T3 cannot do that we can: nothing on this axis — except
that our `stopped` seat resumes with the harness's full context, where T3
documents a lossy rebuild when the native session is gone.

### 2.5 Providers: adapters vs one harness

**T3.** Seven built-in V2 drivers — Codex (generated app-server schemas;
sessions shared across threads; async questions persisted), the Claude
Agent SDK (`permissionModeForClaudeRuntimePolicy`, `compact_boundary` →
context usage), Cursor (official `@cursor/sdk`, ACP transport dropped),
OpenCode / OpenCode 2 (native steering, forks, rollback, child sessions;
an admission state machine for prompt races), Grok, Pi (native
resume/fork/rollback/steering), and a generic ACP Registry adapter of
which Antigravity and Devin are flavors (Cline, Kimi, Droid, … install
from the registry); no Gemini adapter (D §3). Minimum versions enforced
(Claude Code 2.1.280+, Codex 0.159+, …). Native sessions do not map 1:1 to
threads (§2.1). Provider can be switched between turns; the handoff is one
context-transfer primitive shared with fork, merge-back, and subagent
spawn/result — a budgeted selection of verbatim messages (16k tokens by
default), not a summary — and **lossy**: the new provider gets messages,
not the old one's reasoning, tool calls, results, or attachments; the
release notes themselves say to prefer `delegate_task` for mixing
harnesses. (RN, PR, D §2.)

**Ours.** Claude Code only. The family-chat spec's M2 removed the legacy
codex *process* handling (`wait_codex_rc`, the codex arm of `stop_session`)
and quarantines any such record at the boundary; what remains is `send` to
a Codex thread through `codex queue` (message-only, read between turns).
Multi-*model* under one harness is the gateway route: `--settings`/`--effort`
select a route (astra, sol, fable, opus, …), recorded so `fill --resume` and
`send` restore it, and a plain-route spawn scrubs the gateway's transport
variables so a seat cannot start on one provider and silently continue on
another.

**Judgment.** T3 wins the axis outright and pays for it outright: read the
PR's ledger and count how many closed issues are adapter races (OpenCode
admission, Cursor ACP drops, Codex turn mapping, Grok continuation
dedupe). That is the moat and the maintenance. For one operator on one
harness the adapter layer is pure cost, and the Symphony doc's "dual-engine
substrate: ours" win from July was, in retrospect, a cost we chose to stop
paying in September. Our honest multi-model answer is the gateway, which
gives model plurality *inside* one session's context instead of a lossy
handoff between harnesses — a strictly better shape for the case T3 warns
about, and no shape at all for the case T3 serves (a Codex subscription you
also want to spend). FD-3 records the fork.

### 2.6 Workspaces, checkpoints, forks

**T3.** A thread runs in the project checkout or a worktree created per
launch under a temporary `t3/<hash>` branch (configurable names, per
project), after which the setup script runs; the thread records `branch`
and `worktreePath`; `ProviderTurnStartService` recreates a missing
worktree at the thread's branch before a turn; a failed preparation is
retried with `prepared-run.retry`; `t3_worktree_handoff` moves a thread
into a worktree with a queued continuation prompt; there is no per-workspace
dev-server service — a dev server is agent background work or a terminal
(D §7). **Checkpoints**: a hidden git ref
(`refs/t3/orchestration-v2/checkpoints`) captured per run by the effect
worker (the turn starts even if capture fails); `checkpoint.rollback` rolls
the native conversation back through the adapter and restores files unless
`restoreFiles` is false, and refuses to restore a workspace shared with
another thread; `CheckpointRestoreSafety` re-validates at admission and
again before provider work, comparing `realPath`s (D §2). **Fork** any
thread from any finished run (failed, interrupted, limited included),
resolved lazily — native fork where the provider has it (Codex, Claude, Pi,
OpenCode 2), portable context otherwise — with merge-back. (RN, PR, D.)

**Ours.** `--worktree NAME` → the harness's native worktree at
`<repo>/.claude/worktrees/NAME` on `worktree-NAME`; `fill`/`send`/`reply`/
`attach` follow it; the deliverable is a committed branch, never merged by
the seat; `retire` never deletes a worktree. No checkpoint, no rollback, no
fork in sminos: git is the checkpoint, review is the gate, and the harness's
own per-session rewind (files + conversation) exists but nothing in sminos
drives it.

**Judgment.** T3 is ahead; the gap matters less for us than it looks. Their
rollback and fork are *interactive* affordances — undo that turn, branch
this conversation and try another model — for a human sitting at the app.
An unattended seat's checkpoint is its branch, and its "fork" is a sibling
seat spawned from the same spec. The one thing worth noting: the harness
already has the rewind primitive T3 built a service for; if a steering
surface for seats ever exists (FD-4), it is a free affordance there.
Near-parity on worktrees, including the recreate-missing-worktree
behavior (`send` follows a seat's worktree; a deleted one is an error we
surface rather than repair — minor).

### 2.7 Human surface and attention

**T3.** Desktop (Electron), web, and mobile apps, V2-only clients. The
sidebar's status is real state (working, waiting, limited, failed); a
thread-details panel holds workspace, git, scripts, linked PRs, automations,
lineage; a **Working section** (beta, mobile) keeps busy threads out of the
way *until they need attention* — attention being runtime state: a pending
approval or question, a limit, a failure; settlement hides the finished.
Steering from the phone: queued sends, steer-vs-queue per message, answer a
question, bulk settle/un-settle/wake. Subagent transcripts are readable
(the V2 feature Theo promised in August). A live context meter. (RN.)

**Ours.** Three layers. (1) The terminal: `list` (alias, state word, the
seat's own status line or what it waits for or its latest reply), `chart`
(a box organisation chart), `tui` (interactive; `b` opens the focused
seat's chat; Enter attaches). (2) The harness's own UI, through mods: the
`to-human` output style makes the agent *send* messages to a human who
does not watch — `<to-human>`, `<essential>`, `<need-input>` with
`<choice>` buttons, `<insight>` beside — and `to-human.tsx` draws them,
folding the working record behind one button; `agents.tsx` draws the
session's subagent tree. The doctrine is three lines; its one revision was
evidence-driven (the "send a message" framing cut unwanted progress
reports from 2/5 runs to 0/5). (3) afleet, a macOS app hosting the
unmodified engine over stream-json and presenting every session like
Slack — at C1 (probe suite, golden fixtures) of a 17-step roadmap. The
cross-session reader the stream was designed for (`sminos inbox`) is
deferred until afleet plumbs it.

**Judgment.** T3 wins the surface by the whole product; we win the
doctrine. Theirs decides *what needs attention* from runtime state, which
is exactly right for approvals, limits, and failures and says nothing
about the message an agent would compose for a person who is away. Ours
decided that the agent composes it, that the marks divide the human's
attention rather than the content's kind, and that the transcript stays
the one record so the stream and the log cannot disagree — and then
deferred the reader. The honest position: the stream is plumbing for a
consumer that is early, and today its only reader is the harness's own
terminal through the mod. T3's Working section is the thing afleet's
default view was designed to be. FD-4 is the strategic fork: build afleet,
or concede the surface to a product that cannot host our seats.

### 2.8 Scheduling, triggers, settlement — and the board above sminos

**T3.** Scheduled tasks — interval, fixed time, or webhook with HMAC
signing — run on a five-second scheduler tick with idempotent command ids;
a task either launches a fresh thread or queues into its bound thread
(D §6). PR watching polls every two minutes and wakes the agent on a
failing check, required checks passing, a new outside comment or review,
or a base conflict (D §6). Native `/goal` for Codex and Claude.
**Settlement** is server-owned: the auto-settle sweep settles after three
idle days or a merged/closed PR and never while pinned, with pending
background tasks or live activity, a pending approval, or a linked PR
snapshot missing or still open; settling detaches the idle provider
session; snooze and bulk sidebar sweeps exist. Linked PRs are discovered by
`ThreadPullRequestService` (skipping settled threads). (RN, PR, D.)

**Ours.** Scheduling and triggers are not sminos's; they are the board's.
`board-sweep.sh` on launchd every five minutes: bounded auto-recovery,
board-driven cancel, `execute-dispatch.sh --sweep`, `review-dispatch.sh
--sweep`, land dispatch on the human's Approve, the `needs-human` answer
relay. The event path: PR events → self-hosted runner → dispatch script
(`pr-review-dispatch.yml`), private repos only. Above that, the work
semantics the Symphony doc already judged — the ticket gate, three park
states, decomposition, an adversarial review species, tiered merge. A
seat has no "settled": a pipeline seat's finish is its ticket's `done`
via `Closes #N`; a family seat's finish is its host's `retire`.

**Judgment.** Different objects, as with Symphony: T3 schedules
*prompts into threads* and settles *threads by their PRs*; we schedule
*ticks over a board* and close *tickets by their PRs*. The convergence —
PR events wake agents; a thread/ticket is not done while its PR is open —
is the same one the Symphony doc found, now three for three. T3's general
scheduler is a real capability we lack at the seat level (the harness's
own `CronCreate` exists and nothing in sminos wraps it); the board's sweep
is the work-shaped version and covers what we actually run unattended.
Their settlement is a sidebar-hygiene concept; ours is the board's state
machine, which is the richer object. No import beyond §4.6.

### 2.9 Safety

**T3.** Four permission modes —
`approval-required|auto-accept-edits|auto|full-access`, **full access the
default** — mapped onto each provider's own approval mode: for Claude,
`default|acceptEdits|auto|bypassPermissions`, so T3's default on a Claude
thread is `bypassPermissions` (D §9); for Codex, approval and sandbox
settings; Cursor's sandbox off only under full access; Grok loses
auto-accept. For an unattended thread nothing is auto-approved beyond the
mode. Approval and user-input requests are persisted runtime requests that
survive turn end, provider exit, and restart; a restart marks them
`not_resumable` with a message rather than leaving them dangling. Agents
cannot approve their own permission requests. A delegated child's modes
inherit the parent's as a ceiling and can only narrow (D §4) — which is
also why a parent switched to full access widens the ceiling of every
later child, as a plugin author noted on day one. `request_secret` returns
a one-use `secretRef`, never the value (D §9). (RN, PR, D.)

**Ours.** `--permission-mode auto` on every seat: the classifier approves
safe tool use and gates the rest; a gated operation is an escalation (the
seat goes `waiting`, `reply` renders it, `send` answers it);
`--dangerously-skip-permissions` is banned in the skill with the reason
("hands an unattended process the power to do something irreversible with
no one watching"). The record never carries a credential on a
model-facing surface (`public_seat` strips `bearer|token|secret`); the
gateway scrub keeps a seat on one provider; registry files are 0600 under
umask 077. The harness's own safeguard dialog can pause an unattended
fable seat (TECH-DEBT 27: 18 minutes until a person attached).

**Judgment.** Parity, different shapes. T3's persisted runtime requests
are the better *mechanism* — a question survives a restart and is
answerable from a phone; ours survives because the transcript does, and
is answerable with `send` from a terminal. T3's four levels with "full
access" as the default — on a Claude thread, the `bypassPermissions` our
skill bans by name — and a ceiling inherited down the tree is the weaker
*posture* for unattended trees; ours is one mode with a classifier. Their
`request_secret` (a one-use reference, never the value) is the broker the
Symphony doc's FD-6 deferred to the unattended phase; its reopen trigger
is unchanged, and this is the reference shape when it fires. Their
"agents cannot approve their own requests" is structural here — a
`waiting` seat runs no turn, so it cannot invoke anything, and the answer
arrives from a person or its host through `send` — and could be stated.

### 2.10 Size and coupling

| | T3 Orchestrator V2 | sminos |
|---|---|---|
| core | `apps/server/src/orchestration-v2/` — `Orchestrator.ts` alone is 415 KB and `ProjectionStore.ts` 269 KB (D); the PR is +380,729 / −203,651 over 1,912 files | `sminos.py` ≈3.1k lines (138 KB); chart + TUI + lib ≈1.3k; `SKILL.md` 214 lines; preamble 34 |
| persistence | SQLite event log + projections, one-way V1 migration, migration-id divergence checks | JSON per seat + JSONL per chat, no schema version, `migrate` imports the former registry |
| what it couples to | seven provider drivers (SDKs, app-server schemas, ACP) with minimum versions | one harness's sessions registry, inbox socket recipe (documented in the binary's log strings), `--bg`/`--resume`/`--worktree`, transcript layout |
| tests | replay fixtures per provider, integration tests, a fake Claude CLI | 856 hermetic assertions (stub `claude`, real unix socket server) + live proofs on the real harness |
| upgrade path | migrate the database; adapters chase provider releases | read the next harness release's session record |

**Judgment.** The ratio is roughly 80:1 in lines for overlapping
function, and the reason is §0's question. Our coupling is narrower but
not shallower: the sessions registry and the socket injection recipe are
undocumented internals (the human-stream spec records reading them from
the 2.1.259 binary), and a harness release that changes the record's
fields breaks `state()` on that day. T3's coupling is to seven drivers with
version floors they enforce; ours is to one with none. We should pin the
harness version floor we read against (§4.5).

---

## 3. Settled axes (no discussion needed)

- **Runtime durability: T3.** Settled not by building a server but by
  reading the harness for the two states we lack (Limited, interrupted
  mid-turn) and keeping resume as the recovery verb.
- **Multi-harness: T3.** We stopped paying for it on purpose; the gateway
  is our multi-model answer. Reopen only if a second harness subscription
  must be spent (FD-3's trigger).
- **Conversation semantics: ours.** Family chat, reach, tag-decides-push,
  chat-first boot. T3's children are read-only and sibling-blind by
  design; nothing to take — their wait is a pull model's necessity (§5).
- **Work semantics: ours.** The board, the gate, the review species, the
  merge tiers — T3 has settle and schedules; it does not attempt these.
- **Human surface: T3.** By the whole product. What to do about it is
  FD-4, not an import.
- **Scale evidence: T3, by orders of magnitude.** A nightly user base
  that filed three migration bugs the same weekend, 47 reactions on the
  release, a third-party CLI ported to protocol 2 the next day. Ours:
  three live proofs at n=1 and one unattended fleet.

---

## 4. Import candidates (prioritized)

1. **Limited as a reading** — when a seat's turn ended on a usage-limit
   error, `list`'s now column reads `limited until <time>` (parsed from the
   reply, the way `waiting` reads `waitingFor`), and the board sweep's
   recovery schedules the resume at the reset instead of three attempts.
   A registry read plus one sweep branch. (PR `UsageLimitRecoveryWorker`;
   today's digest-agent failure as the local evidence.)
2. **Restart continuity for family seats** — a seat whose transcript's last
   record is a running turn with no end reads `interrupted`, not `stopped`
   (a sub-case of `stopped`: `send` resumes it the same way); a host's
   `list` shows it; `sminos sync --continue` resumes every interrupted
   child of a host with a one-line nudge. (RN "Continue threads after
   restarts"; PR `ProviderRuntimeRecoveryService`.) Decide the word
   carefully — the one-name spec's lesson is to test the predicate on the
   real harness first.
3. **State the self-approval rule** — one sentence in `SKILL.md`: a seat's
   permission prompt is answered by a person or by its host, never by the
   seat (a `waiting` seat runs no turn). Already structural; worth a
   sentence because a host reading the skill should know it may answer a
   child's prompt and what that makes it responsible for. (RN.)
4. **Model and cost in `list --json`** — the model the seat runs and the
   transcript's `cost-state`, for a host integrating children; already in
   the transcript, one read. (RN lineage shows model/duration.)
5. **A harness version floor** — `sminos` records the harness version it
   last read a session record from and warns when the record's fields
   change; T3 enforces `Claude Code 2.1.280+`. Cheap insurance against
   the coupling §2.10 names.
6. **Settle-as-hide** (later) — `list`/`chart` fold an `idle` seat whose
   host has retired or whose last reply is older than a day, as `retired`
   and `gone` are folded today. Sidebar hygiene; only if `list` grows noisy.

## 5. Deliberate non-imports

- **A wait-for-children verb** — proposed in this doc's first draft as
  `sminos wait [@a @b] --all`, dropped on the human partner's objection
  (2026-10-08): the family chat is push. A child's `say` lands on the
  host's socket and the harness starts or absorbs a turn; a host that
  blocks in a tool call until N children report is a seat that reads
  `busy` while doing nothing, bounded by the tool's timeout, indistinct
  from working. T3 needs the wait because its parent would otherwise poll
  `task_status`; ours is the message's recipient. N reports costing N
  host turns is the family-chat design's accepted price, and the strict
  join shape belongs to native subagents (§2.3).
- **A server / event log** — the answer to §0's question is the harness;
  a second copy of its state is V1's race.
- **Provider adapters and mid-thread provider switch** — one harness; the
  gateway is the model switch, lossless inside one context. T3's own notes
  call their switch lossy.
- **Checkpoint/rollback/fork services** — git + review for unattended
  seats; the harness's rewind for a human at the keyboard.
- **A settlement service** — the board's state machine is the richer
  object; a family seat is retired by its host.
- **A scheduler in sminos** — the board sweep is the work-shaped one; the
  harness has `CronCreate` natively if a seat ever needs a timer.
- **Projecting native subagents into the registry** — the harness draws
  its own tree (`agents.tsx`).
- **A product app as the surface** — not a non-import but a fork; FD-4.

---

## 6. Forked decisions for discussion (non-trivial, skewed, both defensible)

> Each FD names the fork, both bets, the skew, and the open question.
> Settled axes (§3) are excluded.

### FD-1 · Truth ownership: the server's event log vs the harness's own records

**T3:** every thread fact is an event the orchestrator committed; provider
state is reconciled against it; ids are minted by the orchestrator; the
provider is an adapter that reports. **Ours:** sminos keeps only what the
harness does not (seat identity, role, parent, chat) and reads the rest
live from the harness's session record, socket, and transcript; the
September specs *deleted* every field that duplicated a harness fact.
**Skew:** T3's choice is what made every other V2 feature possible and
what cost 380k lines plus a migration; ours is what keeps sminos at 4k
lines and inherits each harness release — and what makes a queue, an
interrupt, a limit state, and a context meter impossible to *own*, only
to *read*. The coupling is not symmetric either: they bind to documented
SDKs with version floors; we bind to one harness's undocumented record
and socket recipe. **Open:** is there a fact about a seat that the
harness will never keep and that we need durably? Candidates so far —
`limited-until`, `interrupted` — are both readable from the transcript,
which keeps the answer "no" one more time. The reopen trigger is the
first fact that is not.

### FD-2 · Coordination primitive: delegate-and-collect vs a family that talks

**T3:** `delegate_task` → a child thread that starts with only its task
prompt and ends with a result; the parent waits or is woken by a mailbox
run; there is no follow-up on a task; children are read-only threads and
cannot address siblings; nesting is unbounded under the parent's mode as
a ceiling. **Ours:** `spawn` → a child seat that reads the family chat
first and can be followed up by `say`/`send` for as long as it lives;
`say` with tags deciding who is pushed and who is resumed; siblings talk;
the host idles until a child speaks. **Skew:** theirs is the right
primitive for a fan-out whose outputs are results (a reviewer panel, a
per-milestone executor — the shapes our skills already run on *native
subagents*, not seats); ours is the right one for a team whose members
must know what the others said (a lead integrating two children whose
changes collide — the live proof's exact scenario). Theirs has no group
record; ours has no typed result (and needs no wait: the host is pushed,
§5). **Open:** should a *result* be a first-class thing in the
chat — a message kind the host can act on — or is "the child's last
untagged message after its turn ends" already that, and typing it the
kind taxonomy the human-stream spec refused? The human-stream precedent
(no kinds; marks divide attention, not content) argues for the latter.

### FD-3 · Harness plurality: seven drivers vs one harness and a gateway

**T3:** eight providers and a registry; cross-provider `delegate_task`;
lossy switch. **Ours:** one harness; multi-*model* through the gateway
inside one context; codex reachable as a message target only; the codex
process arm removed 2026-09-26. **Skew:** their adapter layer is both
the moat and the bulk of the ledger; for one operator who spends one
subscription it is pure cost — but a second subscription (Codex at full
allowance, a Cursor seat) is the one thing the gateway cannot spend. The
Symphony doc counted dual-engine as our win in July; we dropped it in
September on the merits. **Open:** none while one subscription is the
budget. Reopen trigger: a second harness subscription worth spending
unattended — at which point the honest shape is a *seat kind*, not an
adapter: a Codex thread registered as a seat with `send` through
`codex queue` and a state word read from Codex's own session store, the
same harness-as-truth bet applied to a second harness.

### FD-4 · The human surface: a product app vs the harness's UI, a doctrine, and afleet

**T3:** desktop, web, mobile; Working section; phone steering; lineage;
subagent transcripts; settle. **Ours:** terminal verbs; the harness's own
terminal through mods (to-human spans, the subagent tree); a stream
doctrine whose cross-session reader is deferred; afleet at C1 of 17.
**Skew:** this is the only axis where their lead is a *product* and not a
mechanism, and the only one where "import" is not available: T3 Code
cannot host a sminos seat (it owns the session lifecycle; a seat is a
`claude --bg` the harness owns), and sminos cannot draw T3's threads. The
two are mutually exclusive surfaces for the same sessions. Our stream
doctrine is the thing their Working section computes from state and ours
asks the agent to compose; the eval (5×5 on the premise wording) is the
only evidence either side has on what a human should be sent. **Open:**
three regimes — (a) build afleet to its §17 roadmap and keep the harness
as runtime (the current bet); (b) a minimal reader first — `sminos inbox`
over the transcripts, which the stream spec already designed and deferred
"until something reads it" — and a phone-readable rendering of it, before
the app; (c) adopt T3 Code for the *interactive* half (threads a person
steers) and keep sminos for the *unattended* half (seats the board
dispatches), accepting two surfaces. (b) is cheap and tests the doctrine
against a real reader, which is the evidence the spec said it was waiting
for; (c) is the one that spends no build on a surface at all. The
recommendation here is (b) now, (a) as planned; (c) is the fallback if
afleet stalls.

### FD-5 · Finished: server-settled threads vs host-retired seats

**T3:** a thread settles itself when idle, unpinned, with no background
work and no open linked PR; settling detaches the provider session; the
sidebar hides it; a person can snooze or un-settle. **Ours:** a seat is
`idle` until someone retires it; a host retires its children when it
integrates their work; a pipeline seat's finish is its ticket's `done`.
**Skew:** theirs is a hygiene rule computed from PR state so a sidebar of
hundreds stays readable; ours puts the decision on a host or the board,
which is right while a human or a host reads `list` and wrong the day
`list` holds a hundred idle seats nobody retired (the real registry
already held 21 `gone` seats from other hosts when the one-name spec was
written). **Open:** is "finished" a seat fact or a view fold? §4.6 says
fold; a seat fact would need a word, and the one-name spec's rule is that
a word must be tested on the real harness before it names anything.

### FD-6 · Unattended permission posture: four levels with inheritance vs one classifier mode

**T3:** `approval-required` / `auto-accept-edits` / `auto` / `full-access`,
full access the default (Claude's `bypassPermissions`), the parent's mode
a ceiling for delegated children; persisted requests answerable from a
phone; no self-approval. **Ours:** `auto` with the
classifier on every seat; the twin ban; `waiting` + `reply` + `send`;
no phone. **Skew:** their mechanism is better (a question outlives a
restart and is answerable anywhere); their default is worse for a tree
(a parent's full access widens every later child, as a plugin author
noted within the first day). Ours has the safer default and the poorer
reach — the 18-minute safeguard-dialog stall (TECH-DEBT 27) is what "no
phone" costs. **Open:** the reach half is FD-4's; the posture half is
settled on our side unless a seat kind ever needs a wider mode, and then
it should be per-spawn and non-inherited.

---

## 7. Convergences worth noting (independent evolution, same answer)

- **The parent is woken by a child's completion**, and the child is a full
  session with its own history, never text spliced into the parent (T3
  closed #2477, #5395, #10575 on the splice; our seats were always
  sessions).
- **Message the parent, not the child's peers** as the default
  (read-only subagent threads ↔ the reach rule).
- **A durable record of what was said, with ids and a read watermark**
  (`thread.visit`/`lastVisitedAt`/`mark-unread` ↔ `chat_seen`, `unread n`).
- **One live state word in the sidebar** (working/waiting/limited/failed ↔
  busy/idle/waiting/stopped/gone), and both learned the same lesson the
  hard way: *do not derive a state from the provider's stream* — their
  entire V1→V2 ledger; our `blocked`-without-a-process and `gone`-by-the-
  job-list defects, each fixed by reading the thing a resume actually
  needs.
- **A message to a busy agent is held, not dropped** (their server queue
  with steer/queue ↔ the harness's `absorbed_mid_turn`, which we observed
  rather than built).
- **A worktree per unit with a recorded branch**, recreated or followed
  rather than assumed.
- **PR events wake agents; a unit is not finished while its PR is open.**
- **The recovery verb is native resume**, with a rebuild only when the
  native session is gone (their `excludeTurns` resume + budgeted handoff ↔
  `--bg --resume` + `fill` fresh for `gone`).

Convergence under independent evolution is evidence the problem shape,
not fashion, dictates these — and it localizes the real disagreements to
§6's six forks.

---

## 8. Caveats on evidence

- V2 is three days old in nightly. The PR's ledger describes mechanisms
  present on the branch; whether they hold in the field is what Theo's
  Oct 4 feedback thread is asking. Two migration bugs (#15017, #15003)
  and one usage-attribution gap (a fork's PR #166) were filed in the
  first weekend.
- The digest (D) is a read of the source at `main` `e65063cc`
  (2026-10-06) through the GitHub tree API and raw file URLs — the shallow
  clone failed partway — and the two largest files (`Orchestrator.ts`,
  `ProjectionStore.ts`) were searched, not read whole. Nothing was
  executed. RPC names and state enums cited from D should be re-checked
  against the file paths it gives before any import is built; D ends with
  its own list of what it could not determine.
- Our side's evidence is three live proofs (one family of four seats, one
  one-name proof with three seats, one stream eval of ten runs) and one
  unattended fleet on the board. The per-axis claims above are design
  claims where they favor us, not scale claims.
- Theo's design rationale is known only through search snippets of X
  posts; the one maintainer quote ("not putting a new database under a
  feature flag") is second-hand via the skyflo page.
