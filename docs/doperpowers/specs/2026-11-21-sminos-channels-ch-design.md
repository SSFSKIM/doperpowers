# sminos: declared channels, child CH (2026-11-21)

> **Parent:** `docs/doperpowers/specs/2026-11-17-sminos-channels-and-threads-design.md`, child **CH** (Channels). **Parent pin:** `main` `1fdc73a0`, that file's blob `448486977dba760aeab6495b0b69b8e11d87b986`. **Consumes:** the parent's design (D3, D5, D6 and D7, binding where marked there), its contracts X1, X2, X4, X5, X6, X7 and X8, and the code map `docs/doperpowers/research/2026-11-17-sminos-channels/ch-code-map.md` (sminos 1.52.0 and MAWS's master read on 2026-11-21; every place named below is cited there with its line). MAWS's half of the wire (the parent's child MW) is on MAWS's master. This document is CH's own cut: what the code forced the design to settle before CH could be divided, and its two children. Children dispatch per their grain hint, each carrying its section as its spec; each child's artifact (plan, ledger, PR) opens by citing this document (path + child id + parent pin).

## Purpose

After T1 and T2 every member is a thread that keeps its identity and is woken. What is still wrong is the parent's first fault: the unit of coordination is the directory a session was launched in. CH adds the declared channel: a named set of threads that crosses repositories and machines, made with one command, in which threads are placed without acting, and in which they speak. It is the parent's Purpose, second bullet, and nothing wider: a channel owns nothing, leads nothing by default, bounds no one's reach, and has no surface but the CLI.

## Parent-Level Acceptance

CH closes when the parent's acceptance lines 1, 2 and 7 run across two of the owner's machines on released versions, line 8 holds for CH's surface, and the list under "CH: Channels" in the parent is observed item by item. Two of those items are sharpened here, because the code showed what they mean:

- "A machine that holds a member of a channel opens its log without `follow`" is observed at MAWS: the channel is in the `known` of each machine that holds a member and of no machine that holds none, and the org's directory lists it for every machine.
- "A bare `@alias` reaches a thread that shares only a declared channel with the sender" means the tag resolves; the message lands in the target's project log, as a message to another project does today (C5).
- "Two requests by one writer with the same seq in two channels" is met by a stronger form: a request has an id of its own, and each is answered once, by the statement that names its channel and that id (C2).

The children's acceptances below add up to that list. What only the whole can show is the scene itself, on two machines, with nothing staged: it is run once at the end, by the session holding this document, and is the recomposition check.

## Grounding Baseline

Read in code on 2026-11-21 (the code map; sminos 1.52.0 at `1fdc73a0`, MAWS's master at `1ae7f5c96`). `S/` is `sminos/skills/sminos/scripts/`, `T/` is `sminos/tests/`.

- **Already there.** The record's `channels` field and its writer (`set_channels`). A reader that skips an event kind it does not know: `_projection` skips every kind outside `LIFECYCLE` in this version, in 1.51.0 and in 1.27.10, the oldest copy the older-copy suite runs; delivery is blind to kind and keys on `to` alone, so a new kind that names no one in `to` is inert to every installed copy. Delivery state, the hold and the wake are keyed by (log, session) and need no new key. The chat frame already names the log a message is in. `confirmed` (the typed yes) and `advertised` (a kept capability) exist.
- **Membership of a log is a `joined` in it, everywhere.** Delivery (`deliver_owed`, `deliver_say`), tags (`match_members`), `@all`, the reach pass (`reach_due`), the uplink's `holds` and every publication of a member (`Plane.refresh`, `publish_members`, session presence) take "the members of this log" from `view_of(project).members`. A declared channel's log holds no `joined` (D3: membership is a statement in the member's project log). So as the code stands a message in a channel's log is owed to no one, a tag qualified by a channel finds no one, and the machine that holds a member only follows the channel.
- **A channel already reaches every machine as a project.** MAWS's org frame lists a channel as `kind: "hub"`, and every installed sminos registers what that frame lists as a followed project. Telling a channel from a project is done on receipt, by the id, or not at all.
- **MAWS lists a channel as known only when two things hold:** the log was opened without `follow`, and a held lane A member's frame names the channel in `channels`, counted only when the hello advertised `channels`. Today `holds` is false for a log with no local `joined`, and a log that is held is sent the machine's presence, which D6 forbids under a channel id.
- **The fixture.** MAWS's conversation fixture differs from sminos's copy in the capability lines, the thread lines T1's replay amends, one inserted step in case 11 (S4's member frame, which moves every later step of that case down by one), and a new case 13, the only one with `member.channels`. Hellos are matched whole, so the copy and the advertisement are one change. The inserted step states S4 as `gone`; sminos states a thread its human opened as `stopped` whatever its transcript, and `gone` only for a spawned thread with none; MAWS changes that step to `stopped` (Decision Log).
- **The hub's check.** The hub and the endpoint read an event's `session`, when it is not the writer's own, as a reference to a session being addressed, for every kind. The endpoint's `reach?` answers `deliver` when the sender shares an owner with the recipient or holds at least `list` on its record.
- **Sizes.** `S/sminos.py` is 19,141 lines; the uplink, the plane, the daemon and the threads module are 2,500 to 3,200 each.

## Design

The parent's D3, D5 and D6 are the design. What follows is what its cut needs settled with both halves in view. Marked **[binding]** where a child may not reopen it; the rest is advisory, and a child overturns it with evidence and a dated line in this document's Decision Log.

### C1. A channel has two readings of "its members", and they never mix

**[binding — both children read the same set for opposite purposes, and the wrong reader publishes a member under a channel id, which MAWS refuses, or writes a thread's fact into the wrong log]**

- **The roster** of a channel is derived and never stored: the threads whose membership (C2), read from each thread's own project log as the reader may read it, names the channel (D3). A row of it is the member's row in its own project's view and names that project, so a thread that went private, ended, or whose machine was retired is absent by the rules that already build that row.
- **The roster is a read of its own. A channel's view has no members.** `view_of` of a channel id returns none, as it does today, so every existing path that asks for the members of a log (delivery, tags, `@all`, the plane, the verbs that find a target) finds nothing under a channel id unless a child changes that path on purpose. A path that addresses through a channel takes the roster explicitly and keeps two things apart: the log an event is in, and the project of the thread it found.
- **A fact about a thread is written to the thread's own project,** whatever log the thread was found through: its lifecycle events, its in-charge line, its statements, its words to its human.
- **Nothing is published under a channel id.** No `member` frame names one as `project`, and there is no session presence, no machine presence, no checkout, no `joined`, no `state`, no restated snapshot, no `pending` set, no host frame and no word to a human (`message`, `question`, `answered`). A thread is published once, in its project, as today, and its frame there carries its channels (X5).
- **Whether this machine opens a channel's log without `follow`** is read from this machine's thread records and from nothing else: it does while a thread of this machine that has not ended names the channel in `channels`. That is one of the two things MAWS needs to list the channel as known; the other is that thread's `member` frame, which goes out by today's rules. sminos does not try to keep the two equal: while a thread's frame is withdrawn (its record unreadable, its lane changed), MAWS stops counting it and the hello stays as it is.
- **Whether a request names a thread of this machine** is likewise read from this machine's thread records.

The cache that holds a view is keyed on one log's files; a roster depends on other logs, and its cache says so.

*Alternative: a `joined` in the channel's log.* The parent rejected it (`known_checkouts` would make every member's directory a checkout of the channel, and membership would have two writers). *Alternative: `view_of` of a channel returns the roster,* so that delivery and tags work unchanged. It lost to the review: a verb that finds a thread through a log writes to that log (`find_target` returns the project searched, and `charge` appends there), and every publishing path would need an exclusion of its own.

### C2. The events

**[binding — X4 gives CH the names and shapes, and both children and every older reader meet them]**

Four kinds are added. None names anyone in `to`, so no installed copy delivers one or wakes a thread for it.

- **The statement,** kind `channels`, in the thread's project log, written by the thread's machine under the thread's current writer, stamped with `thread` as every lifecycle event is. Fields: `channels`, the whole set of declared channel ids, in the order they were added; and, when it answers a request, `answers` (`channel`, `id`), `result` (`applied` or `refused`) and, for a refusal, `reason`. A statement that refuses carries the set unchanged.
- **What a reader takes as a thread's membership** is the latest statement under the thread's current writer that follows that writer's `joined` in effect. A writer that has stated nothing since its `joined` states no channel. So a writer a thread returns to (a `join` back to a project, a reach that returns to an audience it had) never speaks with an old statement, and a thread in no channel needs none. The kind joins `LIFECYCLE`, so a view's row carries the set.
- **The request,** kind `channel-request`, in the channel's log, one event per target, written under the requester's writer there. Fields: `op` (`add` or `remove`); `session`, a session id the target thread has had, which is where the hub and the endpoint read whom an event addresses; `thread`, the target's thread id; and `id`, a value the requester mints for this request. A request that names a private thread is written under the stream of the two audiences' meet, by the split a message's recipients get today, and is refused by the endpoint or withheld by the hub otherwise. A thread that adds or removes itself writes no request, only a statement.
- **A machine added to the pool by hand,** kind `channel-env`, in the channel's log: `op` and `machine`. Honoured from a writer whose thread is in the roster when it is read; the last by merge order holds.
- **The lead,** kind `channel-lead`, in the channel's log: `thread`, or none. Honoured only under a machine's human writer.

A statement names the request it answers by the channel and the request's `id`, never by the request's writer: the writer holds the requester's session id, the statement is read by everyone who may read the target, and a private requester would be disclosed to them (the parent's reason for a thread id that is no session's id). The first child builds the first three kinds; the second builds the lead.

### C3. Carrying out a request

- **Where.** On the target's machine, by one function, under the thread's own transition lock, called from two places: a pass of the daemon over the logs of the channels it follows, and the command that wrote a request for a thread of its own machine. A machine carries out a request from elsewhere only while its endpoint advertises `channels`; without it the request stays pending.
- **Whom it names.** The thread whose id is the request's `thread`, if it is a thread of this machine that has not ended and has had the request's `session`. A session that has since become another thread is not that thread.
- **Who may ask** **[binding — the parent's rule, in the one form a check exists for; agreed with MAWS's architect]**. A request is honoured when its writer may message the thread: the endpoint answers `deliver` to `reach?` for the request and sminos holds the request's sender as verified, or the writer is one of this machine's own and shares the thread's owners. An unverified sender is refused, though the endpoint delivers such a sender's words to a thread that is not private: a word is shown marked unverified, and an act has no such mark. While the endpoint gives no answer (it holds no record of the thread yet) the request stays pending. The parent said "may converse with"; in MAWS `converse` is a rank above the one a message needs, and no check asks for it. A request that is not honoured gets a refusing statement with one reason: `not-reachable`, `read-only` (the machine admits nothing from outside) or `limit` (it would be the 129th channel).
- **One at a time, in order.** For one thread and one channel, requests are carried out in the order this machine reads them, and a request waits behind an earlier one for the same channel that still waits for its verdict. A request also waits while the thread's record has an open journal entry. The new set is computed from the record under the lock, never from an earlier read. The command says for each target what happened: applied, refused with the reason, or pending and why.
- **Once.** The thread's record keeps the requests it has answered (channel and id) for as long as a request can be pending, and a request it holds is not carried out again, whatever writer, project or absorbed record the answer was written under.
- **The record and the statement are one transition.** The record's `channels`, the answered request and the statement are written through the thread store's journal (X1: the record first, the event owed in `pending`, a replay finishing exactly that), not through `update`, whose contract is a change that owes no event. `set_channels` becomes the journal's operation.
- **The log is kept equal to the record.** Whenever the membership a reader would take from the log (C2) differs from the record's set, the thread's machine states the set. This is a reconciliation, run where the machine already reconciles a project, not a step attached to a `joined`: it holds after a continuation, a refill, a `join`, a return, a change of reach, a renamed machine, a `joined` an older copy wrote, and a stop between two writes. Between a `joined` and the statement that follows it, other machines read the thread as in no channel.
- **A provisional thread that is absorbed** gives its channels to the thread it continues: the continuing thread's set, then the job's additions, up to the limit; an addition past the limit is dropped and said in the daemon's log.
- **What the requester is told,** then and in `channel show`: *applied* or *refused* with the reason, from the statement that names its request; *refused: not reachable*, when the hub withheld the request at its own position; *pending*, with the machine the target was last seen on and since when, which covers a machine that is off, one whose sminos or MAWS predates channels, and an answer the requester may not read; and nothing, once the request is seven days old by its own timestamp, when it is expired and no longer carried out. A clock wrong by days misjudges that; it is accepted.
- **What is refused before anything is written.** `channel add` of a session that is no lane A thread, or of a thread that has ended, where the requester's machine can see that.
- **Adding wakes no one.** A request for a stopped thread is carried out by its machine's daemon while the thread stays stopped.

### C4. The wire

**[binding — the parent's X5 and D6, with what the code adds]**

- `is_channel_id` is MAWS's predicate, tested against the shared vectors' `ids`. It is applied wherever sminos takes or receives an id: the org frame's entries, `.smns`, `join`, `--project`, a selector, a name in a tag. A `.smns` that names a channel id is not a project: the session is filed in its machine's project and told why. `sminos join <channel>` is refused and names `channel add`, and a join override that names a channel is read as absent.
- A channel registered on this machine has a kind of its own, so that no code path that asks "is this a hub project" answers yes for it by default.
- `channels` is advertised in the hello, and `member.channels` is sent when the welcome lists it: the record's set, at most 128, and no key at all for a thread in none. The frame's cache takes the set into its key. The limit binds every path that grows a set.
- The fixture is copied byte for byte from MAWS in the change that advertises the capability, from the commit in which MAWS states S4 as `stopped` (Decision Log); the copy retires the replay's amendments. Nothing in the replay fails on a line that should not have been sent, so "nothing is published under a channel id" has a test of its own, on a first connection, on a reconnection and over a store an older copy wrote into.
- `channel create` and `channel add` are refused where the endpoint has not advertised `channels`.
- **Until CH2 ships, nothing is said into a channel.** CH1 refuses, before anything is appended, every form that would write a message into a channel's log: a tag qualified by a channel, `--in <channel>`, and a selector that names one.
- **Older copies** (D7). A copy from before CH follows a channel as a project and sends for it what it sends for any followed project (a hello with `follow`, an empty pending set); it skips the new kinds; it lists no channel. Run by hand, it can `join` a session into a channel's id: MAWS drops that member, and this version, at its next reconciliation, reads the override as absent and moves the session back to its project, its declared set untouched. Accepted until the older copies are gone.

### C5. Where a message lands

**[binding — the parent's timeline rule, with the cases the code raises]**

- A message is in a channel's log when it names the channel, by `--in` or by a tag qualified with it.
- **Only a member writes a message into a channel's log,** and the owner at a terminal. A thread outside the channel that tags `@<channel>/<alias>` is refused and told the two ways that work: add itself, or tag the thread plainly. So every message in a channel has a sender the roster holds, a reply by the frame's reply line always resolves there, no message in a channel carries `from_project`, and none leaves a copy in the sender's project log. *Alternative: a tagged message from outside, by today's rule for another project* (the parent's lean). It lost to the review: the reply would go to the outsider's project, against the timeline rule, and the outsider could not be addressed in the channel at all.
- A bare `@alias` resolves over the sender's project and the rosters of the channels the sender is in. It never puts a message in a channel's log: a target found only through a shared channel is written to as a thread of another project is today.
- **What a channel's log owes a thread follows its membership.** When a thread ends, what every channel it is in owes it is settled as its project's is, and not pushed if it returns. When a thread is removed from a channel, what that channel owes it is settled unpushed. The end, the return and the removal each say so in the same journaled transition that changes the record.
- The frame keeps T2's layout (the header at offset zero, the note last, the reply line after it on the inbox route), and its header keeps `→ @you` or `→ @all`, which the report view reads.
- **Between releases** (D7). A message a CH2 machine sends to a member whose machine still runs CH1 is owed and not pushed until that machine updates; the sender is told what it is told for any thread on another machine. Accepted: nothing is lost, and the alternative is to ship the receiving half before any test can send to it.

### C6. Listing

- Bare `sminos list` prints the caller's project and each channel it is in, each under a heading, a channel's as `# <name>`, with its roster and its stopped members shown. `--channel <name>` filters. `sminos channel show <name>` prints one channel: roster, requests and what became of them, pool.
- `list --json` keeps one row per session and gains a `channels` key; a channel's roster in JSON is `channel show --json`. *Alternative: a second row per channel.* It lost because every reader of that output today assumes a session appears once.
- A name that more than one log answers is refused, listing each with its kind and `name#short` (the parent). Today's refusal lists full ids and no kind; the first child rewrites it once, for every caller.

### Delegated unknowns

| Unknown | Settled by |
|---|---|
| How a thread whose reach is not the default writes into a channel's log, and what the channel's object at the hub needs to know that stream's policy | Settled 2026-11-21 by MAWS's architect (Decision Log): nothing of its own; the split a message's recipients get today works unchanged |
| What S4 stands for in the fixture's inserted step | Settled the same day: a session its human opened; MAWS changes the step to `stopped` |
| How sminos knows that a request's sender is verified (C3) | CH1's plan, from the code that holds a peer's event as verified today |
| What an older sminos's empty pending set under a channel id does at MAWS | Asked of MAWS's architect, 2026-11-21 |
| What a roster costs to read when channels number in the tens (the parent's risk) | CH2, measured in its live pass |
| Which name is listed for a session the engine renamed on a collision (E15) | CH2 |
| The marker of a machine's notice (X8: EN writes it, CH reads it) | Fixed in the parent's X8 by the session holding it, before CH2's plan is written |

## Children

### CH1: The channel and who is in it — plan

- **Purpose:** make a declared channel exist and hold members, on every machine of the org, with nothing said in it yet: the id and its rule, the channel's log and how machines follow and hold it, the statement, the request and its carrying out, the roster as a read, the `channel` verbs that change membership and the pool, and the listing that shows it.
- **Acceptance:**
  - `sminos channel create <name>` by a thread makes a channel with that thread as its member; by a person at a terminal, with the named thread of that machine. `sminos channel add <channel> <thread>...` and `channel remove` place and remove threads; with none named, the caller. A thread on the same machine is placed when the command returns; no session acts. A session that is no lane A thread, and a thread that has ended, are refused before anything is written.
  - `sminos list` run by a member shows `# <name>` with the roster, stopped members included; `--channel` filters; `channel show` prints the roster, each request and what became of it, and the pool; `channel env add|remove` changes the pool it prints, with the count of live and stopped threads per machine.
  - Across two machines (two homes joined as the suites join two machines today): a request to a thread on the other machine is listed pending with that machine and since when, is carried out when that machine's daemon runs, and the roster on both shows the thread. Each outcome of C3 is seen where it can be known: a refusing statement with its reason at the requester; a request the hub withheld, as refused and not reachable; a machine that never answers, as pending; a request seven days old, as gone and not carried out when it arrives.
  - Who may ask, case by case: the same owner on one machine; a verified sender the endpoint delivers for; a sender it refuses; an unverified sender it would deliver words for, refused; no answer yet, pending; an endpoint without `channels`, pending.
  - Order and identity: an add and a remove of one thread in one channel end as the later one says, whichever path (the command, the daemon) carried each and in whatever order the verdicts came; two requests in two channels are each answered once, by the statement that names its channel and id; a request read twice is carried out once, also after the thread changed writer or project, and after a record was absorbed; a request for a thread whose record has an open entry waits and is carried out after it; a stop between the record's write and the statement is finished by the next run; a request whose session has become another thread changes neither.
  - Membership as others read it: a thread that goes private leaves the roster of a reader that may no longer read it. A thread that ends leaves it; reopened, it is in the channels it was in. After a continuation, a refill, a `join`, a `join` back to a project it had left with another set, and a change of reach and back, every reader takes the record's set, the empty set included. After a `/clear` the thread it left is stopped and still in its channels, and resumes in them; the new thread is in none.
  - `channel remove` of a thread does not retire it. With two machines holding members and a third holding none: MAWS's stand-in lists the channel as known for the two and not the third; removing one machine's last member withdraws that machine alone; when the last member that has not ended is removed or ends, no machine holds the channel; a member that returns makes its machine hold it again.
  - `sminos join <channel>` is refused and names `channel add`. A `.smns` naming a channel id files the session in its machine's project and says why. `channel create` and `channel add` are refused where the endpoint lacks `channels`. A 129th channel is refused at `channel add` and at `channel create`, naming the limit, and an absorption does not pass it.
  - Nothing is said into a channel yet: a tag qualified by a channel, `--in <channel>` and a selector naming one are refused before anything is appended, from a session and from a terminal.
  - A verb that names a thread and writes a fact about it (`charge`, `status`, `retire`) writes to the thread's own project and never to a channel's log, however the thread was named.
  - On the wire: the conformance replay passes on MAWS's fixture copied byte for byte, with no amendment left; a machine that holds a member opens the channel's log without `follow`, and a thread's `member` frame carries `channels` only when the welcome listed the capability and never as an empty list; and a test of its own shows, on a first connection, a reconnection and a store an older copy wrote into, that nothing else is sent or written under a channel id (C1's list, the `pending` set and host frames included).
  - Parent line 8 for this surface: every suite that passed before passes, and a session in no channel sends and prints byte for byte what it did.
  - Older copies, on the same home: 1.27.10, 1.51.0 and 1.52.0 list and deliver as they did over a store that holds statements and a registered channel, and nothing they write changes a thread's channels; after one of them `join`s a session into a channel's id, this version's next reconciliation leaves the session a member of its one project, with its declared set as it was, and publishes nothing under the channel.
- **Edges:** blocked-by: T1 (landed), T2 (landed; the same functions). The copy of the fixture blocked-by the MAWS commit that states S4 as `stopped`. Its observation on the owner's fleet blocked-by MW (on MAWS's master, installed on the owner's machines). blocks: CH2; EN.G2 (`--channel`, `channel show`).
- **Contracts:** the parent's X1 (the `channels` field, its journal operation, and the answered requests), X2 (a request's `thread`), X4 (the kinds), X5 (sminos's half), X7 (a reader before its writer: this child ships every reader of membership CH needs, and its writers are inert to older copies). This document's Y1 and Y2 (owner).
- **Design inheritance:** C1 to C4 and C6 (binding where marked); D3's Creating, The id, Names, Membership and "A channel exists while"; D6; D7. Advisory, from the code map: its §8.2's list of functions for this half; `lifecycle` as the one place a statement is appended; where a project is reconciled today as the place the log is kept equal to the record; an assertion in `append_host` as a second guard against a word to a human under a channel id; `requests.opening` and the host pass as the publishers of the pending set and host frames; the backtick guard's hard-coded verb list (`sminos/hooks/mods/backticks.tsx`), which needs `channel`.
- **What it does not teach.** The session-start guide and the skill say nothing of channels until CH2: a session is not taught a place it cannot yet speak in. `sminos help` lists the verbs.
- **Required:** required for this unit's acceptance.
- **Status:** not-dispatched (dispatchable now).

### CH2: Speaking in a channel, and what sessions are taught — plan

- **Purpose:** make the channel a place to talk: a message into a channel's log, delivered to its roster and waking a stopped member; tags and aliases across channels; the reply that lands where the message came from; the lead; the reader that keeps a machine's notice from being taken for the owner's post; and the guide, the skill, the spawn preamble and the manager's skill rewritten in the words "thread" and "channel".
- **Acceptance:**
  - Parent line 2: `sminos say --in <channel> "@<B> ..."` by a member is delivered to B framed as from that channel, wakes B if it is stopped and may be woken, and B's reply by the frame's reply line lands in the channel's log. `@<channel>/<alias>` does the same. A `say` with neither lands where it does today. `--in <channel>` with a tag that resolves in another log is refused before anything is written.
  - In a channel `@all` reaches its live members and an untagged post prompts no one. A thread outside the channel is refused every form of message into it and told to add itself or to tag the thread plainly.
  - A bare `@alias` reaches a thread that shares only a declared channel with the sender; two answers are refused with `alias#short` for each; a name that a project and a channel both answer is refused the same way.
  - What a channel owes follows membership: a message held for a stopped thread in a channel is not pushed after the thread ended and returned, nor after it was removed from the channel; and it is pushed when the thread is woken or reopened while still a member.
  - The lead: `sminos channel lead <channel> <thread|none>` is refused inside a session and where there is no terminal, and takes a typed yes; an untagged post the owner types into the channel on that machine is addressed to the lead; a lead event under a session's writer changes nothing; a lead that ended or left is ignored; a machine's notice is never read as the owner's post.
  - No `message`, `question` or `answered` is written under a channel id by anything a session or the bridge does while its thread is in channels, and a stopped thread's questions are closed for its project alone.
  - What reads a session's exchanges reads a channel's too: the list of exchanges a session is given after a compaction or a resume names a peer it spoke with only in a channel, and the manager's window shows a channel exchange, with two events of the same writer and seq in two logs told apart.
  - On a real engine, under a scratch home: two sessions in different repositories, one channel, a message into it, a reply, a wake of the stopped one, and the roster's read cost with thirty channels registered.
  - The skill's evaluation: a fresh session creates a channel, places others and speaks in it, with no message in the wrong log; the manager's pressure scenarios pass on its rewritten skill.
  - Parent line 8 for this surface.
- **Edges:** blocked-by: CH1. blocks: EN.G2 (a notice in a channel's timeline). The parent's EN.G1 may run beside it.
- **Contracts:** the parent's X4 (the lead's kind), X6 (owner of the rewrite), X8 (the reader). This document's Y1 and Y2 (consumer), and it extends CH1's end, return and removal transitions with what C5 says a channel owes.
- **Design inheritance:** C1, C2 and C5 (binding where marked); D3's The timeline, The lead and Listing; D5. Advisory, from the code map: its §8.2's list for this half; `from_project` and `record_copy` in `cmd_say`; `say_scoped`, which makes a selector's project the log written to; late settlement, which proves a thread's end from a `retired` in the log that holds the debt, where a channel's log holds none; the tests that pin the guide's and the preamble's lines verbatim; the reply line's debt row in `docs/doperpowers/TECH-DEBT.md`, due in this child's skill work; the manager's regexes over the frame's grammar and its one project per subscription.
- **Required:** required for this unit's acceptance.
- **Status:** not-dispatched (blocked-by CH1).

## Cross-Child Contracts

- **Y1. The read interface.** Owner: CH1, which fixes the names in its plan's Interfaces before CH2's plan is written. CH2 consumes and does not change: the predicate for a channel id; finding a channel by name or id, with the one refusal for a name several logs answer; the roster of a channel as this machine may read it, each row naming its thread's own project; the channels of a thread; and whether this machine opens a channel without `follow`. C1 binds both: a channel's view has no members, CH2 gives each addressing path the roster explicitly and adds no publishing reader, and CH1's test that nothing is published under a channel id runs in CH2's suite.
- **Y2. The events.** C2's kinds and fields. Owner: CH1 for the statement, the request and `channel-env`, CH2 for `channel-lead`. A field is added only by its owner, and an older copy's reading of the kind (skipped, inert) is proved by the older-copy suite in the child that adds it. The marker of a machine's notice is the parent's X8, not this contract's: it marks an event of a kind every copy already reads.
- **Y3. The transitions.** CH1 owns the journal's operation for a membership and what an end, a return and a removal do to the record. CH2 adds to those same transitions the settlement of what a channel's log owes (C5) and to no other place.

## Ordering & Dependency Map

```
CH1 ──▶ CH2 ──▶ (recomposition: the scene on two machines)
  │        │
  └────────┴──▶ EN.G2          EN.G1: beside either
```

One after the other: both change `cmd_list` and the uplink, and CH2's plan is written against the names CH1 builds (Y1). The parent allows EN.G1 beside CH; it shares `S/sminos.py` and little else, and whether to run it beside CH1 is decided when its plan exists.

## Risks & Mitigations

- **A publishing reader that reads the roster** sends a member under a channel id, which MAWS drops as gone, or writes a thread's fact into a channel. C1 makes the roster a read no existing path reaches; CH1 lands the test that nothing is published under a channel id, and CH2's suite runs it again once delivery takes the roster.
- **The membership write has two files and a log.** The journal carries it (C3). CH1's plan names, for each new writer, the lock or the one process its writes go through (the parent's rule for every child that adds a writer).
- **A roster reads every project's log.** Views are cached by their files' signature and the daemon reads each project every tick already. Measured in CH2's live pass at thirty channels; the lever, if it is slow, is an index of statements kept beside the logs.
- **The fixture and the capability land together.** MAWS is changing the one step that would not replay; the copy waits for that commit.
- **Two release trains, and CH1 released alone.** CH1 advertises a capability MAWS already counts; it is inert until a thread is placed. Released alone it gives channels that hold members and refuse every message; C5 says what a CH2 sender meets on a machine still at CH1.
- **A concurrent store** (the parent's last risk): each plan puts a review of its whole range, with lenses that cross its milestones, at a frontier inside the build, and a pass on a real engine in a middle milestone where the engine is in the path (CH2).

## Deferred / Out of Scope

**Deferred (may return):** reading a thread's former names across logs, which the parent handed to CH (a thread refilled into another project is found under the names it has there only; nothing in CH's acceptance needs more, and the parent's Decision Log records the narrowing); an index of statements; a message into a channel from a thread outside it; `--in` a project for a session; the VM columns of `channel show` (EN); the app's view of channels (the parent).

**Explicitly out of scope:** the parent's standing exclusions, whole.

## Tracking Map

| Child | Artifact | Status |
|---|---|---|
| CH1 | its plan, `docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md` | not-dispatched |
| CH2 | — | not-dispatched; blocked-by CH1 |

## Surprises & Discoveries

- 2026-11-21 — **Membership of a log is read as a `joined` in it by every path that delivers, addresses or publishes** (the code map's headline). The parent moved membership out of the channel's log and named nothing that reads it back. C1 is the consequence.
- 2026-11-21 — **A channel already arrives on every machine as an ordinary project,** by the org frame, on every installed version. "Every machine follows every channel" is not built; telling the two apart on receipt is.
- 2026-11-21 — **`reach?` grants at `list`, and delivers an unverified sender's words to a thread that is not private,** so the parent's "may converse" named a rank no check asks for, and a verdict alone is not enough for an act (C3).
- 2026-11-21 — **`set_channels` writes through `update`,** whose contract is a change that owes no event, and an absorbed provisional thread's channels are dropped.
- 2026-11-21 — **A verb that finds a thread through a log writes to that log** (`find_target` returns the project it searched; `charge` appends there; a selector's project is the log `say` writes to). A roster served as a channel's members would have turned a lookup into a write in the wrong log (C1).
- 2026-11-21 — **Every opened log is sent a pending set,** channels included, by a publisher that reads no member (`requests.opening`).
- 2026-11-21 — **A statement that named its request by the request's writer would have published a private requester's session id** to everyone who may read the target (C2).
- 2026-11-21 — **A writer is reused:** a thread that returns to a project, or to an audience it had, appends under a file that already holds its older statements, so "the latest statement under the current writer" was not enough (C2).
- 2026-11-21 — **What a log owes a thread is settled, at its end, from a `retired` in that same log.** A channel's log has none (C5).

## Decision Log

- 2026-11-21 — **The verification.** This document: one review by `doperpowers:adversarial-reviewer` on the cut, the binding grades and C1 to C6 against the parent and the code map. Each child's plan: the same agent on its buildability, and `doperpowers:review-code` on its branch, three reviews a milestone (the owner's bound), a whole-range panel at a frontier inside the build, and the panel on the branch at the end.
- 2026-11-21 — **The cut: two children, membership first.** CH fails the gate as one unit: ten or so milestones over the uplink, the store, delivery, the CLI and three taught surfaces, with two verification strategies (a wire replay and suites; an evaluation of what sessions do). The seam is the parent's own hint, moved by the code map: the roster is built as a read in CH1 and given to delivery in CH2, so that the publishing paths are closed and tested before anything addresses through it. *Alternative: one machine first, the wire second.* It lost because `channel create` already needs the capability, and a channel that cannot be followed elsewhere is not the thing the owner asked for. *Alternative: the taught surface as a third child.* It lost for now: T1 and T2 each carried their own as a last milestone; if CH2's plan shows it tripping the gate, CH2 is cut then.
- 2026-11-21 — **What MAWS's architect answered** (the two projects' chat, against its master `1ae7f5c96`). S4 in the fixture's inserted step is a session its human opened, so the step's `gone` is wrong against sminos as built and MAWS changes it to `stopped`, with the scene after it; no step moves. "Who may ask" as the delivery of a message is right, with two conditions taken into C3: an unverified sender's request is not honoured, and the word is "may message", since `converse` is a rank. A request's `session` is read as an addressing reference by the hub and the endpoint whatever the kind; a request for a private thread goes under the stream of the meet or is refused; the hub's withholding comes back to the requester as not reachable, and its `state-unavailable` leaves the request to be sent again. The channel's object at the hub needs nothing of its own for a non-default writer: the policy registry is the org's, keyed by session, and a stream states its own audience at its first event in a log. Nothing in C4 reads differently at the endpoint; a member frame whose project is a channel id is treated as gone, and only a record that lists the id, never a hello alone, brings a retired row back.
- 2026-11-21 — **What the review of this document changed** (eighteen findings; fourteen taken, three taken in part, one answered by the record).
  - *The roster is a read of its own, and a channel's view has no members* (C1): a lookup through a channel could otherwise write a thread's fact into the channel, and each publisher would need its own exclusion. The `pending` set and host frames joined the list of what is never published.
  - *A request has an id of its own and names the target's thread* (C2): the statement no longer carries the requester's writer, and a session that became another thread is not placed in its stead.
  - *Membership is the latest statement after the writer's `joined`, and the log is kept equal to the record by reconciliation* (C2, C3): a reused writer, an older copy's `joined` and a stop between writes are all covered by one rule.
  - *One function carries out every request, in order per thread and channel, and the record keeps what it answered* (C3).
  - *The outcomes a requester can be told are listed, and a lane B session gets no statement* (C3): it has no thread to write one under; `channel add` refuses it beforehand where that can be seen.
  - *Opening without `follow` is read from records, and is not made equal to MAWS's `known`* (C1), with acceptance for two holders and a follower.
  - *The limit binds every path, an absorption included* (C3, C4).
  - *Only a member writes a message into a channel's log* (C5), which overturns the parent's lean for a tagged message from outside.
  - *What a channel owes follows membership* (C5, Y3).
  - *CH1 refuses every message into a channel until CH2* (C4), and a `/clear` leaves the old thread stopped in its channels (the owner's ruling, which this document's first draft misstated).
  - *Older copies:* 1.52.0 joined the list, with the recovery after an older `join` into a channel.
  - *Taken in part.* CH1 is not made to carry the receiving half ahead of CH2: a message from a CH2 machine to a member on a CH1 machine waits for that machine's update, as a request waits for a machine that predates channels (C5). Expiry stays on the request's own timestamp, and order across writers on the merged read, with a wrong clock's cost accepted (C3). The marker of a machine's notice stays EN's to write and is fixed in the parent's X8, not in Y2.
  - *Answered by the record.* Reading former names across logs is deferred with a line in the parent's Decision Log; no acceptance item rests on it.
- 2026-11-21 — **Decided without asking,** each a technical consequence: seven days for a pending request; the union at an absorption; a local target carried out by the command; one row per session in `list --json`; the guide silent on channels until CH2.

## Outcomes & Retrospective

Pending — written when the unit closes, after the scene of Parent-Level Acceptance runs on two machines.
