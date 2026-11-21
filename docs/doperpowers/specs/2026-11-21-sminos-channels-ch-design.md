# sminos: declared channels, child CH (2026-11-21)

> **Parent:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, child **CH** (Channels). **Parent pin:** `main` `1fdc73a0`, that file's blob `448486977dba760aeab6495b0b69b8e11d87b986`. **Consumes:** the parent's design (D3, D5, D6 and D7, binding where marked there), its contracts X1, X2, X4, X5, X6, X7 and X8, and the code map `docs/doperpowers/research/2026-11-17-sminos-channels/ch-code-map.md` (sminos 1.52.0 and MAWS's master read on 2026-11-21; every place named below is cited there with its line). MAWS's half of the wire (the parent's child MW) is on MAWS's master. This document is CH's own cut: what the code forced the design to settle before CH could be divided, and its two children. Children dispatch per their grain hint, each carrying its section as its spec; each child's artifact (plan, ledger, PR) opens by citing this document (path + child id + parent pin).

## Purpose

After T1 and T2 every member is a thread that keeps its identity and is woken. What is still wrong is the parent's first fault: the unit of coordination is the directory a session was launched in. CH adds the declared channel: a named set of threads that crosses repositories and machines, made with one command, in which threads are placed without acting, and in which they speak. It is the parent's Purpose, second bullet, and nothing wider: a channel owns nothing, leads nothing by default, bounds no one's reach, and has no surface but the CLI.

## Parent-Level Acceptance

CH closes when the parent's acceptance lines 1, 2 and 7 run across two of the owner's machines on released versions, line 8 holds for CH's surface, and the list under "CH: Channels" in the parent is observed item by item. Two of those items are sharpened here, because the code showed what they mean:

- "A machine that holds a member of a channel opens its log without `follow`" is observed at MAWS: the channel is in that machine's `known` and in no other machine's, and the org's directory lists it for every machine.
- "A bare `@alias` reaches a thread that shares only a declared channel with the sender" means the tag resolves; the message lands in the target's project log, as a message to another project does today (Design, "Where a message lands").

The children's acceptances below add up to that list. What only the whole can show is the scene itself, on two machines, with nothing staged: it is run once at the end, by the session holding this document, and is the recomposition check.

## Grounding Baseline

Read in code on 2026-11-21 (the code map; sminos 1.52.0 at `1fdc73a0`, MAWS's master at `1ae7f5c96`). `S/` is `sminos/skills/sminos/scripts/`, `T/` is `sminos/tests/`.

- **Already there.** The record's `channels` field and its writer (`set_channels`). A reader that skips an event kind it does not know: `_projection` skips every kind outside `LIFECYCLE` in this version, in 1.51.0 and in 1.27.10, the oldest copy the older-copy suite runs; delivery is blind to kind and keys on `to` alone, so a new kind that names no one in `to` is inert to every installed copy. Delivery state, the hold and the wake are keyed by (log, session) and need no new key. The chat frame already names the log a message is in. `confirmed` (the typed yes) and `advertised` (a kept capability) exist.
- **Membership of a log is a `joined` in it, everywhere.** Delivery (`deliver_owed`, `deliver_say`), tags (`match_members`), `@all`, the reach pass (`reach_due`), the uplink's `holds` and every publication of a member (`Plane.refresh`, `publish_members`, session presence) take "the members of this log" from `view_of(project).members`. A declared channel's log holds no `joined` (D3: membership is a statement in the member's project log). So as the code stands a message in a channel's log is owed to no one, a tag qualified by a channel finds no one, and the machine that holds a member only follows the channel.
- **A channel already reaches every machine as a project.** MAWS's org frame lists a channel as `kind: "hub"`, and every installed sminos registers what that frame lists as a followed project. Telling a channel from a project is done on receipt, by the id, or not at all.
- **MAWS lists a channel as known only when two things hold:** the log was opened without `follow`, and a held lane A member's frame names the channel in `channels`, counted only when the hello advertised `channels`. Today `holds` is false for a log with no local `joined`, and a log that is held is sent the machine's presence, which D6 forbids under a channel id.
- **The fixture.** MAWS's conversation fixture differs from sminos's copy in the capability lines, the thread lines T1's replay amends, one inserted step in case 11 (S4's member frame, which moves every later step of that case down by one), and a new case 13, the only one with `member.channels`. Hellos are matched whole, so the copy and the advertisement are one change. The inserted step states S4 as `gone`; sminos states a thread its human opened as `stopped` whatever its transcript, and `gone` only for a spawned thread with none (asked of MAWS's architect, Decision Log).
- **The hub's check.** The hub and the endpoint read an event's `session`, when it is not the writer's own, as a reference to a session being addressed, for every kind. The endpoint's `reach?` answers `deliver` when the sender shares an owner with the recipient or holds at least `list` on its record.
- **Sizes.** `S/sminos.py` is 19,141 lines; the uplink, the plane, the daemon and the threads module are 2,500 to 3,200 each.

## Design

The parent's D3, D5 and D6 are the design. What follows is what its cut needs settled with both halves in view. Marked **[binding]** where a child may not reopen it; the rest is advisory, and a child overturns it with evidence and a dated line in this document's Decision Log.

### C1. A channel has two readings of "its members", and they never mix

**[binding — both children read the same set for opposite purposes, and the wrong reader publishes a member under a channel id, which MAWS refuses]**

- **The roster** of a channel is derived and never stored: the threads whose membership, read from each thread's own project log as the reader may read it, names the channel (D3). A row of it is the member's row in its own project's view, so a thread that went private, ended, or whose machine was retired is absent by the rules that already build that row.
- **Readers that address** take the roster: listing, tag resolution, `@all`, delivery and the wake for an event in the channel's log, the reach pass, and whether a request names a thread of this machine.
- **Readers that publish** never see it. For a channel id there is no `member` frame naming it as `project`, no session presence, no machine presence, no checkout, no `joined`, no `state`, no restatement of a withheld snapshot, and no word to a human (`message`, `question`, `answered`). A thread is published once, in its project, as today, and its frame there carries its channels (X5).
- **Whether a machine holds a channel** is read from this machine's thread records and from nothing else: it holds the channel while a lane A thread of this machine that has not ended names it in `channels`. Holding means the hello goes without `follow`. It does not mean presence.

Where the roster is computed (inside `view_of` for a channel id, or beside it) is the first child's to choose. The cache that holds a view is keyed on one log's files; a roster depends on other logs, and its cache says so.

*Alternative: a `joined` in the channel's log.* The parent rejected it (`known_checkouts` would make every member's directory a checkout of the channel, and membership would have two writers). The code map shows what the rejection costs, which is this section.

### C2. The events

**[binding — X4 gives CH the names and shapes, and both children and every older reader meet them]**

Four kinds are added. None names anyone in `to`, so no installed copy delivers one or wakes a thread for it.

- **The statement,** kind `channels`, in the thread's project log, written by the thread's machine under the thread's current writer, stamped with `thread` as every lifecycle event is. Fields: `channels`, the whole set of declared channel ids, in the order they were added; and, when it answers a request, `answers` (`channel`, `writer`, `seq`), `result` (`applied` or `refused`) and, for a refusal, `reason`. A statement that refuses carries the set unchanged. The thread's membership is its latest statement under its current writer; a thread with none is in no declared channel. The kind joins `LIFECYCLE`, so a view's row carries the set.
- **The request,** kind `channel-request`, in the channel's log, one event per target, written under the requester's writer there. Fields: `op` (`add` or `remove`) and `session`, a session id the target thread has had. A thread that adds or removes itself writes no request, only a statement.
- **A machine added to the pool by hand,** kind `channel-env`, in the channel's log: `op` and `machine`. Honoured from a writer whose thread is in the roster when it is read; the last by merge order holds.
- **The lead,** kind `channel-lead`, in the channel's log: `thread`, or none. Honoured only under a machine's human writer.

The first child builds the first three; the second builds the lead and fixes the marker of a machine's notice (X8) that its reader skips.

### C3. Carrying out a request

- **Where.** The target's machine, in a pass of its daemon over the channels' logs it follows: a request that names a session one of this machine's lane A threads has had, and that no statement of that thread names. A request made on the target's own machine is carried out by the command that wrote it, through the same function, so that `channel add` of a local thread is done when the command returns.
- **Who may ask** **[binding — the parent's rule, given its only possible meaning]**. A request is honoured when a message from its writer to the thread would be delivered: the endpoint's answer to `reach?` for the request, or one of the two cases sminos already decides without asking (the same owner's sessions on one machine; an endpoint with no reach gate). The parent says "may converse with"; the endpoint is the one authority on reach and answers one question, which it grants at `list`. A request that is not honoured gets a refusing statement with one reason from a fixed list: `not-reachable`, `read-only` (the machine admits nothing from outside), `lane-b`, `limit` (it would be the 129th channel, X5).
- **Once, and in order.** Requests are applied in the order this machine read them from the channel's log. A statement names the request it answers by channel, writer and seq, and a request so named by any statement of the thread, under any writer it has had, is not applied again.
- **The record and the statement are one transition.** The record's `channels` and the statement that states it are written through the thread store's journal (X1: the record first, the event owed in `pending`, a replay finishing exactly that), not through `update`, whose contract is a change that owes no event. `set_channels` becomes the journal's operation.
- **Restated on a new writer.** A `joined` written under a writer that holds no statement, for a thread whose record names a channel, is followed by a statement of the whole set. Every `joined` goes through `lifecycle`, so this is one rule in one place and covers a continuation, a refill, a `join`, a return, a change of reach and a renamed machine.
- **A provisional thread that is absorbed** (a background job that joined before the engine's hand-off was seen) gives its channels to the thread it continues: the union, in the continuing thread's order with the job's additions after.
- **Pending and expiry.** A request no statement names is pending until it is seven days old by its own timestamp, then expired: not applied if it arrives later, and not listed. Seven days is the hub's own period for a channel's row, and longer than the three days after which a stopped thread ends. A pending request is listed with the machine the target was last seen on and since when.
- **Adding wakes no one.** A request for a stopped thread is applied by its machine's daemon while the thread stays stopped. A thread that has ended gets no statement; `channel add` refuses an ended thread when it can see that it ended.

### C4. The wire

**[binding — the parent's X5 and D6, with what the code adds]**

- `is_channel_id` is MAWS's predicate, tested against the shared vectors' `ids`. It is applied wherever sminos takes or receives an id: the org frame's entries, `.smns`, `join`, `--project`, a name in a tag. A `.smns` that names a channel id is not a project: the session is filed in its machine's project and told why. `sminos join <channel>` is refused and names `channel add`, and a join override that names a channel (an older copy wrote it) is read as absent.
- A channel registered on this machine has a kind of its own, so that no code path that asks "is this a hub project" answers yes for it by default.
- `channels` is advertised in the hello, and `member.channels` is sent when the welcome lists it: the record's set, at most 128, and no key at all for a thread in none. The frame's cache takes the set into its key.
- The fixture is copied byte for byte from MAWS in the change that advertises the capability; the copy retires the replay's amendments. Nothing in the replay fails on a line that should not have been sent, so "nothing is published under a channel id" has a test of its own.
- `channel create` and `channel add` are refused where the endpoint has not advertised `channels`.

### C5. Where a message lands

**[binding — the parent's timeline rule, with the cases the code raises]**

- A message is in a channel's log when it names the channel, by `--in` or by a tag qualified with it. `--in <channel>` is open to a session that is in the channel's roster; `--in <project>` stays an operator's.
- A bare `@alias` resolves over the sender's project and the rosters of the channels the sender is in. It never puts a message in a channel's log: a target found only through a shared channel is written to as a thread of another project is today (in the target's project log, a copy in the sender's).
- An untagged post and `@all` in a channel are a member's. A tagged message into a channel from a thread outside it follows today's rule for a message into another project.
- A message in a channel's log from one of its members carries no `from_project` and leaves no copy in the sender's project log: the reply line names the channel, so the reply lands there, and the sender reads the channel's log itself. A message from outside keeps both, as a cross-project message does today.
- The frame keeps T2's layout (the header at offset zero, the note last, the reply line after it on the inbox route), and its header keeps `→ @you` or `→ @all`, which the report view reads.

### C6. Listing

- Bare `sminos list` prints the caller's project and each channel it is in, each under a heading, a channel's as `# <name>`, with its roster and its stopped members shown. `--channel <name>` filters. `sminos channel show <name>` prints one channel: roster, pending requests, pool.
- `list --json` keeps one row per session and gains a `channels` key; a channel's roster in JSON is `channel show --json`. *Alternative: a second row per channel.* It lost because every reader of that output today assumes a session appears once.
- A name that more than one log answers is refused, listing each with its kind and `name#short` (the parent). Today's refusal lists full ids and no kind; the first child rewrites it once, for every caller.

### Delegated unknowns

| Unknown | Settled by |
|---|---|
| How a thread whose reach is not the default writes into a channel's log (a request it makes, a message it says), and what the channel's object at the hub needs to know that stream's policy | Asked of MAWS's architect on 2026-11-21 (Decision Log). The request's half binds CH1; the message's half CH2 |
| What S4 stands for in the fixture's inserted step | The same question, same day; CH1 |
| What a roster costs to read when channels number in the tens (the parent's risk: every machine follows every channel's log) | CH2, measured in its live pass |
| Which name is listed for a session the engine renamed on a collision (E15) | CH2 |

## Children

### CH1: The channel and who is in it — plan

- **Purpose:** make a declared channel exist and hold members, on every machine of the org, with nothing said in it yet: the id and its rule, the channel's log and how machines follow and hold it, the statement, the request and its carrying out, the roster as a read, the `channel` verbs that change membership and the pool, and the listing that shows it.
- **Acceptance:**
  - `sminos channel create <name>` by a thread makes a channel with that thread as its member; by a person at a terminal, with the named thread of that machine. `sminos channel add <channel> <thread>...` and `channel remove` place and remove threads; with none named, the caller. A thread on the same machine is placed when the command returns; no session acts.
  - `sminos list` run by a member shows `# <name>` with the roster, stopped members included; `--channel` filters; `channel show` prints the roster, pending requests and the pool; `channel env add|remove` changes the pool it prints, with the count of live and stopped threads per machine.
  - Across two machines (two homes under one hub stand-in, as the suites stage two machines today): a request to a thread on the other machine is listed pending with that machine and since when, is applied when that machine's daemon runs, and the roster on both shows the thread. A request the target's machine does not honour is answered by a refusing statement, and the requester's `channel show` says so with the reason.
  - Two requests by one writer with the same seq in two channels are each answered once, by the statement that names its channel. A request read twice is applied once. A request older than seven days is not applied.
  - A thread that goes private leaves the roster of a reader that may no longer read it. A thread that ends leaves it; reopened, it is in the channels it was in. A thread that gets a new writer (a `/clear` aside, which ends it: each of a continuation, a refill, a `join`, a change of reach) is still in its channels for every reader.
  - `channel remove` of a thread does not retire it. When the last member that has not ended is removed or ends, this machine stops holding the channel.
  - `sminos join <channel>` is refused and names `channel add`. A `.smns` naming a channel id files the session in its machine's project and says why. `channel create` and `channel add` are refused where the endpoint lacks `channels`. A 129th channel is refused at `channel add`, naming the limit.
  - On the wire: the conformance replay passes on MAWS's fixture copied byte for byte, with no amendment left; a machine that holds a member opens the channel's log without `follow`, and a thread's `member` frame carries `channels` only when the welcome listed the capability and never as an empty list; and a test of its own shows that nothing else is sent or written under a channel id (no `member` with it as project, no presence, no checkout, no `joined`, `state`, `message`, `question` or `answered`).
  - Parent line 8 for this surface: every suite that passed before passes, and a session in no channel sends and prints byte for byte what it did.
  - Older copies: 1.27.10 and 1.51.0, run on a store that holds statements and a registered channel, list and deliver as they did, and nothing they write changes a thread's channels.
- **Edges:** blocked-by: T1 (landed), T2 (landed; the same functions). Its cross-machine observation on the owner's fleet blocked-by MW (on MAWS's master, installed on the owner's machines). blocks: CH2; EN.G2 (`--channel`, `channel show`).
- **Contracts:** the parent's X1 (the `channels` field and its journal operation), X4 (the kinds), X5 (sminos's half), X7 (a reader before its writer: this child ships every reader CH needs, and its writers are inert to older copies). This document's Y1 and Y2 (owner).
- **Design inheritance:** C1 to C4 and C6 (binding where marked); D3's Creating, The id, Names, Membership and "A channel exists while"; D6; D7. Advisory, from the code map: its §8.2's list of functions for this half; the statement's place in `lifecycle`; `follow` in the thread store for a request met while a record has an open entry; an assertion in `append_host` as a second guard against a word to a human under a channel id; the backtick guard's hard-coded verb list (`sminos/hooks/mods/backticks.tsx`), which needs `channel`.
- **What it does not teach.** The session-start guide and the skill say nothing of channels until CH2: a session is not taught a place it cannot yet speak in. `sminos help` lists the verbs.
- **Required:** required for this unit's acceptance.
- **Status:** not-dispatched (dispatchable now).

### CH2: Speaking in a channel, and what sessions are taught — plan

- **Purpose:** make the channel a place to talk: a message into a channel's log, delivered to its roster and waking a stopped member; tags and aliases across channels; the reply that lands where the message came from; the lead; the reader that keeps a machine's notice from being taken for the owner's post; and the guide, the skill, the spawn preamble and the manager's skill rewritten in the words "thread" and "channel".
- **Acceptance:**
  - Parent line 2: `sminos say --in <channel> "@<B> ..."` is delivered to B framed as from that channel, wakes B if it is stopped and may be woken, and B's reply by the frame's reply line lands in the channel's log. `@<channel>/<alias>` does the same. A `say` with neither lands where it does today.
  - In a channel `@all` reaches its live members and an untagged post prompts no one. A thread outside the channel may not post untagged or to `@all` there and is told so.
  - A bare `@alias` reaches a thread that shares only a declared channel with the sender; two answers are refused with `alias#short` for each; a name that a project and a channel both answer is refused the same way.
  - The lead: `sminos channel lead <channel> <thread|none>` is refused inside a session and where there is no terminal, and takes a typed yes; an untagged post the owner types into the channel on that machine is addressed to the lead; a lead event under a session's writer changes nothing; a lead that ended or left is ignored; a machine's notice is never read as the owner's post.
  - No `message`, `question` or `answered` is written under a channel id by anything a session or the bridge does while its thread is in channels, and a stopped thread's questions are closed for its project alone.
  - On a real engine, under a scratch home: two sessions in different repositories, one channel, a message into it, a reply, a wake of the stopped one, and the roster's read cost with thirty channels registered.
  - The skill's evaluation: a fresh session creates a channel, places others and speaks in it, with no message in the wrong log; the manager's pressure scenarios pass on its rewritten skill.
  - Parent line 8 for this surface.
- **Edges:** blocked-by: CH1. blocks: EN.G2 (a notice in a channel's timeline). The parent's EN.G1 may run beside it.
- **Contracts:** the parent's X4 (the lead's kind), X6 (owner of the rewrite), X8 (the reader, and the marker's shape, which EN's writer follows). This document's Y1 and Y2 (consumer).
- **Design inheritance:** C1, C2 and C5 (binding where marked); D3's The timeline, The lead and Listing; D5. Advisory, from the code map: its §8.2's list for this half; `from_project` and `record_copy` in `cmd_say`; the tests that pin the guide's and the preamble's lines verbatim; the reply line's debt row in `docs/doperpowers/TECH-DEBT.md` (a double-quoted body under an absolute path), due in this child's skill work; former names resolving within one project's projection, which a roster built from project views inherits; the manager's regexes over the frame's grammar and its one project per subscription.
- **Required:** required for this unit's acceptance.
- **Status:** not-dispatched (blocked-by CH1).

## Cross-Child Contracts

- **Y1. The read interface.** Owner: CH1, which fixes the names in its plan's Interfaces before CH2's plan is written. CH2 consumes and does not change: the predicate for a channel id; finding a channel by name or id, with the one refusal for a name several logs answer; the roster of a channel as this machine may read it; the channels of a thread; and whether this machine holds a channel. C1's rule binds both: CH2 gives the addressing readers the roster and adds no publishing reader.
- **Y2. The events.** C2's kinds and fields. Owner: CH1 for the statement, the request and `channel-env`, CH2 for `channel-lead` and the notice's marker. A field is added only by its owner, and an older copy's reading of the kind (skipped, inert) is proved by the older-copy suite in the child that adds it.

The parent's contracts stand as written there, with two corrections recorded in its Decision Log from this cut: X5's sentence that MAWS's fixture holds a stopped thread's frame as T1 sends it, and D3's "may converse" (C3).

## Ordering & Dependency Map

```
CH1 ──▶ CH2 ──▶ (recomposition: the scene on two machines)
  │        │
  └────────┴──▶ EN.G2          EN.G1: beside either
```

One after the other: both change `cmd_list`, `view_of` and the uplink, and CH2's plan is written against the names CH1 builds (Y1). The parent allows EN.G1 beside CH; it shares `S/sminos.py` and little else, and whether to run it beside CH1 is decided when its plan exists.

## Risks & Mitigations

- **A publishing reader that reads the roster** sends a member under a channel id, which MAWS drops as gone, or presence under one. C1 names the two classes; CH1 lands the test that nothing is published under a channel id before CH2 gives delivery the roster, and CH2's suite runs it again.
- **The membership write has two files and a log.** The journal carries it (C3). CH1's plan names, for each new writer, the lock or the one process its writes go through (the parent's rule for every child that adds a writer).
- **A roster reads every project's log.** Views are cached by their files' signature and the daemon reads each project every tick already. Measured in CH2's live pass at thirty channels; the lever, if it is slow, is an index of statements kept beside the logs.
- **The fixture and the capability land together** and the copy may not replay (S4). Settled with MAWS before CH1's milestone that copies it; if the fixture changes there, the copy waits for that commit.
- **Two release trains.** CH1 advertises a capability MAWS already counts; it is inert until a thread is placed. CH1 is releasable alone: channels that hold members and say nothing.
- **A concurrent store** (the parent's last risk): each plan puts a review of its whole range, with lenses that cross its milestones, at a frontier inside the build, and a pass on a real engine in a middle milestone where the engine is in the path (CH2).

## Deferred / Out of Scope

**Deferred (may return):** reading a thread's former names across logs (a thread refilled into another project is found under its names there only); an index of statements; `--in` a project for a session; the VM columns of `channel show` (EN); the app's view of channels (the parent).

**Explicitly out of scope:** the parent's standing exclusions, whole.

## Tracking Map

| Child | Artifact | Status |
|---|---|---|
| CH1 | its plan, `docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md` | not-dispatched |
| CH2 | — | not-dispatched; blocked-by CH1 |

## Surprises & Discoveries

- 2026-11-21 — **Membership of a log is read as a `joined` in it by every path that delivers, addresses or publishes** (the code map's headline). The parent moved membership out of the channel's log and named nothing that reads it back. C1 is the consequence.
- 2026-11-21 — **A channel already arrives on every machine as an ordinary project,** by the org frame, on every installed version. "Every machine follows every channel" is not built; telling the two apart on receipt is.
- 2026-11-21 — **`reach?` grants at `list`,** so the parent's "may converse" names a grade no check answers for (C3).
- 2026-11-21 — **`set_channels` writes through `update`,** whose contract is a change that owes no event, and an absorbed provisional thread's channels are dropped.
- 2026-11-21 — **A reply to a message sent into another log goes to the sender's project,** by `from_project`: unchanged, a reply to a channel message would leave the channel (C5).

## Decision Log

- 2026-11-21 — **The verification.** This document: one review by `doperpowers:adversarial-reviewer` on the cut, the binding grades and C1 to C6 against the parent and the code map. Each child's plan: the same agent on its buildability, and `doperpowers:review-code` on its branch, three reviews a milestone (the owner's bound), a whole-range panel at a frontier inside the build, and the panel on the branch at the end.
- 2026-11-21 — **The cut: two children, membership first.** CH fails the gate as one unit: ten or so milestones over the uplink, the store, delivery, the CLI and three taught surfaces, with two verification strategies (a wire replay and suites; an evaluation of what sessions do). The seam is the parent's own hint, moved by the code map: the roster is built as a read in CH1 and given to delivery in CH2, so that the publishing paths are closed and tested before anything addresses through it. *Alternative: one machine first, the wire second.* It lost because `channel create` already needs the capability, and a channel that cannot be followed elsewhere is not the thing the owner asked for. *Alternative: the taught surface as a third child.* It lost for now: T1 and T2 each carried their own as a last milestone; if CH2's plan shows it tripping the gate, CH2 is cut then.
- 2026-11-21 — **Asked of MAWS's architect** (the two projects' chat): what S4 stands for in the fixture's inserted step; whether "who may ask" as the delivery of a message is acceptable; that a request names its target in `session`, with what the hub and the endpoint then do for a private target and what the requester is told; what the hub needs to know the policy of a non-default writer's stream in a channel's log; and whether anything in C4 reads differently at the endpoint. Answers are folded here and into the plans.
- 2026-11-21 — **Decided without asking,** each a technical consequence: seven days for a pending request; the union at an absorption; a local target carried out by the command; one row per session in `list --json`; no copy and no `from_project` for a member's message in its channel; the guide silent on channels until CH2.

## Outcomes & Retrospective

Pending — written when the unit closes, after the scene of Parent-Level Acceptance runs on two machines.
