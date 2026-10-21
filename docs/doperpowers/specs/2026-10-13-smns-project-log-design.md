# `.smns` — the project as the unit of a swarm: identity, event log, host-less family, mirror

A project today is a set of long-lived interactive sessions, each in charge
of one part of it, plus the subagents each of them spawns for tasks. On this
machine right now MAWS has six such sessions and manim-master four, named by
hand after what they own ("현우진", "interactive learning"). Nothing ties them
together: sminos (`skills/sminos/SKILL.md`) sees only the seats it spawned,
grouped by the spawn tree; a session opened by the human is invisible to it
until a `seat add`; a session on the other Mac is invisible forever; what a
session sends its human (a `<message>` mark) lives only in that session's
transcript; and the harness's own ListAgents lists sessions by account and
machine, not by project, so a session run through a gateway or by a
collaborator never appears there.

After this change a project is identified by a committed `.smns` file, every
session working under it is a member of the project's family with no join
step, and everything that crosses sessions — a message to a peer, a message
to the human, a session joining, taking charge of something, spawning a
sibling, stopping — is one event in the project's append-only log. One file
per writer, so two machines never write the same file; the log is mirrored
through an ordinary git remote, and a small per-machine daemon delivers
remote messages to local sessions and publishes local liveness. The family
has no host seat: the human is the host, and a session's `<message>` is the
message to them. A session may spawn another session, which joins as a
sibling with its provenance recorded, not as a child.

To see it working: in a repository with a `.smns`, open two interactive
Claude Code sessions. `sminos list` shows both under the project's name with
their state and what each is in charge of. In one, `sminos say "@<other>
your change renames a column I read"` arrives in the other as a
`[sminos chat …]` frame; `sminos say "merged #12"` is recorded for everyone
and wakes no one; `sminos say "@all main is being rebased, stop pushing"`
wakes every live member. A `<message>…</message>` the first session writes
appears in `sminos chat --host` attributed to it. With a remote in `.smns`
and the daemon running on two machines, the same `say "@<other>"` crosses
machines.

## Progress

- [x] M1 — Project identity and the log (2026-10-14, reviewed clean after two fix waves; 7f3f8b9f..eb6a5ede)
- [x] M2 — The project family (2026-10-14, reviewed clean after two fix waves and two rulings; 5dd82ba4..0ed8f8fb)
- [x] M3 — Messages to the host and the in-charge line (2026-10-14, reviewed clean after three fix waves and two rulings; 09775a35..2fc95340)
- [x] M4 — The mirror and the daemon (2026-10-14, reviewed clean after one fix wave and one ruling; e4204b38..e7e55aef)
- [x] M5 — The skill and the preamble, as behavior (2026-10-14, reviewed clean after one fix wave; 7009154f..619308dc)
- [x] M6 — Docs, acceptance, version (2026-10-14, reviewed clean; live acceptance found and fixed F1–F3; c98ba037..9b8fc8b2)

## Terms

- **Project** — the unit of shared work state. Identified by a `.smns` file
  (below); a git repository without one is a *local project*, named as
  `derive_group` in `skills/sminos/scripts/sminos.py` names groups today
  (the owning repository of a linked worktree). A directory in no git
  repository is no project (§1).
- **`.smns`** — a committed JSON file at a repository's root:
  `{"project": "<uuid>", "name": "<display name>", "remote": "<git url or empty>"}`.
  Several repositories carrying the same `project` id are one project.
- **Member** — a session whose latest membership event in the log
  (`joined` or `retired`, §3) is `joined`, plus, on this machine, every live
  harness session and every seat whose working directory resolves to the
  project (they are reconciled into the log on sight, §2). Derived, never
  declared.
- **Occupancy** — the span from a session's `joined` to its `retired`. A
  seat is a position several sessions can occupy in turn (`fill`); each
  occupancy is one session's membership (§6).
- **Alias** — a member's display name: the harness's session name (what
  `~/.claude/sessions/<pid>.json` records as `name`, what the human sets with
  `/rename`, what a seat is spawned as). Not unique and not stable; an
  address is resolved from it at submission and stored as the session id (§2).
- **Short** — the first eight characters of a session's uuid, the stable
  disambiguator (`maws-45#e0ad139c`).
- **Host** — the project's humans, and any agent reading on their behalf
  (the chief-of-staff agent is deferred, §9). Not a seat. `human` stays the
  operator's identity as today.
- **Writer** — one appender of the log: `<machine>/<session-uuid>` for a
  session, `<machine>/human` for the operator on that machine,
  `legacy/<host-seat-id>` for imported family chats. `<machine>` is
  `host_name()` in sminos.py. A session's writer is also the **canonical
  writer of its lifecycle**: whoever writes a `joined`, `retired`,
  `renamed`, `state`, `in-charge`, or `status` for a session on its machine
  — the hook, `spawn`, `retire`, reconciliation, the daemon — appends it to
  that session's file under its lock, so a session's lifecycle has one
  sequence (§3).
- **Event** — one JSON line in a writer's file, identified by
  `(writer, seq)` (§3).
- **Log** — all writers' files of one project, under
  `$SMINOS_HOME/projects/<project-id>/log/`. When the project has a remote,
  that directory is a git working tree of it (the **mirror**).
- **Projection** — what reading the log plus local liveness yields: members,
  their state, in-charge line, provenance, and the chat. Computed on read.
- **Daemon** — `sminos daemon`, one process per machine: syncs mirrors,
  delivers events to local members, publishes local state changes.
- **Frame** — the text pushed into a session's inbox socket, as today:
  first line `[sminos chat …]`, then the message.
- **Internal fork** — a headless `claude -p --fork-session` run that sminos
  itself starts (`derive`, §5). Never a member, never recorded (§5).

## 1. The project and its identity

`sminos project init [--name N] [--remote URL]` writes `.smns` at the
repository root of the working directory with a fresh uuid; `sminos project
show` prints the resolved project for a directory. Resolution is one rule,
`resolve_project(cwd)`: walk up from the directory to the first `.smns` —
that project; else, if the directory is inside a git repository, the local
project named after the owning repository (a linked worktree under
`.claude/worktrees/<name>` carries `.smns` by checkout, and without one its
owning repository names it, so the main checkout and its worktrees resolve
alike); else **no project**: the operator's terminal in a home directory,
a `/tmp` scratch, a session there. Automatic discovery — the hook, the
reconciliation of harness sessions — does nothing where there is no
project. The one explicit exception is `spawn --cwd <dir>` into such a
directory, which registers a local project named after the directory's
basename for the seats spawned there (how the `bench` seats under
`/tmp/bench-browser` work today); those seats are members by their records,
and nothing else in that directory is.

The file is committed, not ignored, because a collaborator's clone must
land in the same project without configuration; that is the point of the
id. The alternative, keying projects on the repository's remote URL, was
rejected: it cannot express a project spanning two repositories, and a fork
or mirror of the repository would silently be the same project.

Every project known to a machine has `$SMINOS_HOME/projects/<id>/`:

    projects/<id>/
      project.json          copy of .smns as last resolved, plus "root": the directory it was found in
      log/                  the writers' files; a git working tree when .smns names a remote
        <machine>.<session-uuid>.jsonl
        <machine>.human.jsonl        legacy.<host-seat-id>.jsonl
        machines/<machine>.json         the machine's instance id, pushed at attach (§8)
        .sync.lock                      appenders shared, working-tree git phases exclusive (§8)
        .sync-op.lock                   one sync at a time (§8)
      cursors/<session-uuid>.json       what a reader has read: {"<writer>": <seq>}   (local only)
      cursors/export/<session-uuid>.json  the hook's export position in the transcript (§4)   (local only)      delivered/<session-uuid>.json     per writer, the settled prefix and the pending event (§4)   (local only)

and `$SMINOS_HOME/daemon/machine.json` holds this machine's random instance id,
written on first use, and `$SMINOS_HOME/internal/<pid>` marks an internal
fork's process (§5).

Resolution and appending never need the network. A project with a remote
is **attached** (`sminos project attach`, also run by the daemon on first
sight) by adopting the existing `log/`: `git init` when it is not yet a
repository, the first commit, the remote added, the remote fetched and
integrated so that local history is preserved (unrelated histories are
expected on first attach). An attach with the remote unreachable succeeds
up to the fetch, leaving the first sync to the daemon. The alternative, cloning
the remote into `log/`, was rejected because the normal path is a project
that mirrored nothing until the second machine arrived.

## 2. The family is the project

A member sees its whole project with `sminos list`, and a name resolves
inside the working directory's project; `<project-name>/<alias>` reaches
another project known locally, and from a directory that is no project a
name resolves across every project known locally. The former reach rule (a
family seat sees only parent, siblings, children) leaves, and with it the
preamble's "someone outside your family is reachable only through the
native tools" clause: the project is the reach.

**Addressing.** Aliases are display names and can collide: this machine's
registry has held two sessions named `cua_repl` in one project. So an
address is resolved when the message is submitted and stored as the
session id. A tag is `@name`, `@"name with spaces"`, `@name#short`, or `@short`;
`@project/name` crosses projects. A message goes to exactly one project's
log, its **destination**: the sender's project by default, or the project
the tags name, and a message whose tags name two projects is refused. The
event is appended under the sender's writer id, which is the same in any
project, and the sender reads the record with `chat <project>`; the sender
need not be a member of the destination (a session in one project telling
another's session that a shared plugin changed). A tag that matches more than
one member is refused with the candidates as `alias#short`, and a tag that
matches none is refused as unknown. `leading_tags` in sminos.py keeps its
rule — only the run of tags opening a message addresses anyone — and gains
the quoted and `#short` forms. A frame shows the alias; delivery, local or
remote, goes by the session id, so a rename or a replacement after
submission cannot misroute it.

**Reconciliation.** Two kinds of session on this machine are members on
sight: a *live* harness session (its pid alive, its record under
`~/.claude/sessions`) whose working directory resolves to the project and
whose latest membership event is absent or `retired` — a live process is
evidence of activation, which covers a session resumed outside sminos; and
a seat record in the project with no membership event at all and a status
other than `retired` — the seats that exist when this ships. Every CLI call
that reads the project (`list`, `say`, `chat`, `send`, `status`, `charge`)
first appends `joined` for them (`by` `""`, `name_source` from the
harness), so they appear in the log without a restart and reach other
machines through the mirror. A retired seat with no process is not
reconciled: it stays retired until `fill`, `resume`, or `send` revives it,
which appends `joined` (§3). The hook (§4) does the same at session start;
all of it is idempotent by the membership rule. Symmetrically, a seat-less
local member whose harness session is no longer live is retired by
reconciliation (`reason` `ended`): its activation is over, and a closed
session kept as a member would hold its alias ambiguous forever. Resuming
it re-joins it on sight. Only a harness session whose record's `kind` is
`interactive` or `bg`, and whose `entrypoint` does not start with `sdk`,
joins on sight, so another tool's headless run in the directory is not a
member — unless the host that launched it marks it one: `SMNS_MEMBER` in
the engine's environment, naming the pid that spawned the engine (MAWS
sets its own on every engine it launches). The record carries no
environment, so the mark is read only inside the session's own process
tree, and holds only while the pid it names is the engine's parent: a run
started from inside a marked session inherits the variable but not that
parent, and stays out. Its hook (§4) and its bridge's child join it, and
so does a verb its tools run (reconciliation there admits the session
`CLAUDE_CODE_SESSION_ID` names, never another SDK run it sees);
reconciliation anywhere else leaves it to them, and retires it `ended`
like any member once its process is gone. An internal fork (§5) stays out
whatever it inherits. A `retire` of a seat-less session holds for the life of the
process that was running when it was recorded. Nobody can stop the
terminal session the human opened, so reconciliation re-joins it only as
a different process (another pid, or a later start). A resume re-joins,
and the retire is not undone a moment later.

**Hand-off.** Sending an interactive session to the background
(`/background`, the agents view's ←) does not move its process: the
harness starts a job with `--resume <transcript> --fork-session` — a new
session id, a new process, a new bridge endpoint — lets the interactive
process exit, and appends `{"type": "continued-in", "continuedInSessionId":
<new>}` to the old transcript (its own `/resume` hides the old session by
it). The job is the same member: the old session is retired with `reason`
`continued` and `to` the new one, in its own file, and the projection
reads the new session as continuing it (`former`): what it has not set of
its own — alias, spawner, in-charge line, status, worktree — it carries on,
its chat cursor is copied, a seat that held the old session moves to it,
and a tag, `alias#short`, or full id naming the old session resolves to
it. The link is recorded when the job joins while the old process still
exits (the usual case: observed, it outlives the job's start by half a minute), else
when the old one's membership would end, and for a seat at every
reconciliation while the session it holds no longer runs (the harness
writes the record only once the job has started, so the job may join
first). The cursor is copied and the seat moved before the retirement is
recorded, so a hand-off cut short (a seat lock another command holds, a
hook out of time) leaves the old session joined and is done again whole.
The record is read as the harness reads it, the latest one with no turn
after it, so an old session resumed and worked in again is its own: it
re-joins, and a `joined` of its own after the `continued` retirement ends
the link, the job keeping what its own events hold. A `continued`
retirement holds against the exiting process as a `retire` does.

**Names the harness makes up.** The alias of a seat-less session is its
harness name, unless that name is one the harness made up (`nameSource`
`derived`: the directory's name and one random byte, drawn again by every
process; `auto`: a title it wrote; `collision`: a given name it suffixed)
and the log already holds an alias for the member. A resume therefore
keeps `maws-4d` rather than becoming `maws-3f`, and a job keeps the alias
of the session it continues rather than its generated title. A name
someone gives (`/rename`, `--name`) renames the member as before.

There is no host seat. A seat that spawns another is recorded as its
spawner (§6) and nothing more: it does not integrate the other's work, is
not woken by its reports, and retiring it leaves the other running. The
reasons: a session is in charge of a standing responsibility, which does not
expire with whoever started it; and a tree of sessions reproduces inside the
project the supervision this repository removed from the board loop. Work
that is not a separable standing responsibility is a subagent, not a
session, so the depth of large work stays inside one session.

The human is the host. The operator's `say` and `send` are recorded as
events from `human`, and a member's message to the host is its `<message>`
mark (§4), not a `say` tag. The alternative, a `@host` tag on `say`, was
rejected because two spellings of the same recipient put the same message
in two places; the mark already exists in every session running the
`to-human` output style and needs no CLI call.

**Locality.** A member on another machine is reached by `say` and `send`
(recorded, delivered by its machine's daemon) and described by `charge` and
`status` (events). `send --wait`, `reply`, `resume`, `fill`, `attach`,
`retire`, `meta`, and `derive` act on a process or a record this machine
holds; given a remote member they refuse with `<alias> is on <machine>`.
Remote control of a session's process is not in this design.

## 3. The log

One file per writer, append-only, each line one event:

```json
{"ts": "2026-10-13T08:01:02.123Z", "writer": "SK.local/e0ad139c-18bc-45bd-9489-be8653145f80", "seq": 42,
 "kind": "say", "from": "doperpowers-1e",
 "to": [{"session": "67646a1b-…", "alias": "maws-45"}], "text": "your change renames a column I read"}
```

`ts` carries milliseconds (`now()` in sminos.py gains them). `seq` is per
writer, starting at 1, assigned under a per-file `flock`
(`<file>.lock`; several processes on one machine write one session's
file: its own `sminos say` from the Bash tool, and the hook of §4), and
`(writer, seq)` identifies an event everywhere. Within a writer, `seq` is
authoritative: cursors, delivery, and the projection's "latest" are by
`seq`, never by `ts`, so a clock correction cannot reorder a writer's own
events. Across writers the display is a merge of per-writer streams, each in
`seq` order, the next line taken from whichever stream's head has the
earlier `(ts, writer)`; a writer's lines never cross even when its clock
stepped back. A session's lifecycle is one writer by construction (Terms),
so its latest `joined`/`retired` is by `seq`. The one place two writers can
contend for the same fact — a member's `charge` or `status` set by the
member and by the operator on different machines — takes the later `ts`: a wall-clock compromise, accepted because the
alternative, a vector clock per field, buys nothing a human cannot fix by
setting the line again. One file per writer is what makes the mirror
trivial (§8): a file has one writer, so replication is a copy and a merge
conflict cannot occur. The alternative, one file per project with a global
id, needs a lock or a server to assign ids and was rejected for that.

The kinds, and the fields each carries beyond `ts`, `writer`, `seq`:

| kind | fields | written by |
| --- | --- | --- |
| `say` | `from` alias, `to` `"*"` or a list of `{session, alias}`, `text`, `wake` true for `@all` (whose `to` is the list of members live at submission) | `sminos say`, a member's `send` |
| `human` | `from` `"human"`, `to` as `say`, `text`, `wake` true for `@all` | operator `say` / `send` |
| `message` | `from` alias, `to` `"host"`, `text`, `src` transcript record uuid plus span index | the hook, from a `<message>` mark — the one mark since 7.149.0; `<to-human>`, `<essential>`, `<need-input>`, `<insight>` read as its aliases |
| `question` | `from` alias, `to` `"host"`, `text` the question texts, `choices` the option labels, `src` the call's `tool_use_id` | the hook, from a `tool_use` of `mcp__doperpowers__AskUserQuestion` with `async` true whose paired `tool_result` is the tool's accepted result (`docs/doperpowers/specs/2026-10-13-ask-async-design.md`) |
| `answered` | `from` alias, `src` the call id, `text` the engine's result text | the hook, from the delivery row quoting `The human responded to your async AskUserQuestion (call <id>)` |
| `joined` | `session` uuid, `alias`, `name_source` `user`/`derived`/`seat`, `machine`, `cwd`, `worktree`, `role`, `seat` seat id or `""`, `by` alias or `""` | `spawn` (with `by`), `fill`/`resume` of a retired seat, the hook on session start, reconciliation, `seat add` |
| `retired` | `session`, `by`, `reason` `retire`/`replaced`/`ended` | `sminos retire`, `remove`; `spawn`/`fill` into an occupied seat; reconciliation, for a seat-less session no longer live (`ended`) |
| `in-charge` | `session`, `text`, `source` `set` or `derived`, and on a `derived` line of a session sminos may name, `name` the charge name proposed with it | `sminos charge`, `spawn --brief`, `sminos derive` |
| `status` | `session`, `text` | `sminos status` |
| `renamed` | `session`, `alias`, `name_source` | the daemon, on a harness name change, into the session's file |
| `state` | `session`, `state` word, `machine` | the daemon, on a liveness transition (§8), into the session's file |
| `titled` | `session`, `title` (never empty) | the daemon, in a project another machine reads, when the session's title (§5, source 4) moves from the last one published, into the session's file |

**Membership rule.** A session is a member while its latest `joined`/
`retired` event is `joined`. A fresh fill of a seat appends `retired`
(`reason` `replaced`) for the session it displaces and `joined` for the new
one; `fill --resume` or `resume` of a retired seat appends `joined` again
for the same uuid. The projection shows a replaced session under its seat's
history, not as a member.

Git and board events are not copied into the log: a message names a commit,
PR, or ticket by its id and the reader follows it. The log holds what
crosses sessions and nothing a session or the repository already keeps.

**Cursors.** A reader's cursor is a map writer → seq in
`cursors/<session-uuid>.json`. `sminos chat` with no flags prints what is
above the cursor (at most 30, then `+N earlier`) and advances it; `chat -n
N` tails the last N without moving it; `chat --since <ts>` reads from a
time. A pushed frame's `unread N` is the count above the cursor at push
time. The per-message `delivered` map rewritten in place today leaves: an
append-only file is never rewritten, and delivery is the deliverer's local
record (`delivered/`, §4), not the message's.

**Secrets.** The log carries no redaction layer. What reaches it is what
agents say to each other and to the human, and a secret does not get into
that: the plugin's secrets hook keeps an agent from reading or printing a
stored secret in the first place (a value is used only inside the shell
command that needs it, never read into the conversation), so a plaintext
credential in a `<message>` or a `say` is not a case this design guards
against. Earlier drafts carried a scanner at append and at attach; the
owner ruled it out on 2026-10-13 (Decision Log).

## 4. Speaking

`say` keeps its shape — `sminos say "<text with @tags>"`; tags address only
at the start — and its routing becomes the project's:

| sender | tags | recorded as | delivered to | starts a turn in an idle member | resumes a stopped member |
| --- | --- | --- | --- | --- | --- |
| member | none | `say` to `*` | nobody | no | no |
| member | `@a @b` | `say` to `[a, b]` by session id | a and b | yes | yes |
| member | `@all` | `say` to the live members at submission, `wake` true | those members | yes | no |
| operator | none (`--in <project>` or the cwd's) | `human` to `*` | nobody | no | no |
| operator | `@a` | `human` to `[a]` | a | yes | yes |
| operator | `@all` | `human` to the live members at submission, `wake` true | those members | yes | no |

An untagged message is a record: a member reads it at its next wake, when
its preamble has it read the chat, or when it chooses to. Only an address delivers, and `@all` is the address that means everyone
who is there now: at submission it resolves to the members the sender's
machine knows as live (local ones by `state()`, remote ones by their last
`state` event) and is recorded with that list as its `to` and `wake` true,
so the audience is in the event and no machine has to reconstruct who was
live when; an idle recipient starts a turn, a busy one reads at its next
tool round, and no stopped one is resumed — a sender who wants a stopped
member back tags it. A member that joined after the broadcast, or that a
disconnected machine did not yet know, is not in the list and never
receives it: the broadcast is for who was there. The alternative, delivering untagged messages to every live
member, was rejected on cost: a project with six idle sessions would start
six turns, each loading its context, for one line of status. The
alternative to the tag, a `--wake` flag, was rejected because a flag leaves
no trace in the message: the tag is in the text, so the record says which
messages woke everyone. The preamble says what `@all` is for — something
every member must act on now — and that status is untagged.

`sminos send <alias> "…"` stays the direct verb to one seat and is recorded
as `human` (operator) or `say` (member) to that session; it reaches a live
local member over its socket and resumes a stopped one, exactly as today.
Its delivery goes through the recipient's delivery record like any other
event's (below): the verb pushes at once and fails loudly, and an
interrupted or failed push stays owed.

**Delivery.** Delivery is a function of the log: an event is owed to a
member until the member's delivery record settles it, and settlement is
**in order per writer**. `delivered/<session-uuid>.json` holds, per
writer, the `seq` up to which every event is settled (the prefix) and,
when the next event failed, that event's `seq` with its attempt count; a
deliverer never settles an event while an earlier one of the same writer
is unsettled, so a later success cannot bury an earlier failure. Delivery to a member is one operation, `deliver_next`, which holds
`delivered/<session-uuid>.lock` from reading the record, through choosing
the next owed event of each writer (`settled + 1`, never beyond), the
push, and the settlement or failure note — so two deliverers cannot push
the same event, or a later one before an earlier pending one. The
sender's own call to it for each recipient, right after the append and
after every append lock is released, is the fast path (it may thereby
deliver an earlier pending event of the same writer first); the daemon's
deliver duty (§8) calls the same operation for whatever is still owed — a
remote event, a local one whose sender exited between the append and the
push, a failed one. Per event and recipient, the outcomes
of `push_member` in sminos.py map as: `sent` or `woken` → settled;
`failed` before anything was written → pending, retried on each daemon
tick, and after 60 attempts settled with a line in `$SMINOS_HOME/daemon.log`
naming the event and the member; uncertain after a write → settled. So
delivery is **at least once**: a frame carries the event id, and a member
that sees the same id twice reads it once. An event is owed to a member if its `to` names that member's session
and the member is not the sender (`@all` never lists its sender); an
addressed event to a `stopped` member resumes it, except a `wake` event,
which is settled without a push for a member that is `stopped`, `gone`,
or `retired` at delivery time. Nothing is owed to a session that no event
names, so a new member's delivery record starts empty and needs no
initialisation. A project without a
daemon has only the fast path, and a sender that dies between append and
push leaves the record for the member's next `chat`. The alternative,
exactly-once by acknowledgement over the socket, needs a protocol the
harness inbox does not offer.

**Messages to the host.** A new shell hook, `hooks/smns-record.sh`,
registered in `hooks/hooks.json` on `Stop` and on `SessionStart` (matcher
`startup|resume|clear|fork`), calls `sminos record` with the payload's
`session_id`, `cwd`, and `transcript_path`; it is `set -uo pipefail`, reads
the payload once with `read -r` as `hooks/to-human-stream.sh` does, exits 0
on every error so a logging failure never blocks a turn, and exits at once
when `SMNS_INTERNAL` is set in its environment (§5) or `cwd` resolves to no
project. On `Stop`, `record` reads the transcript from its end back to the record
named in `cursors/export/<session-uuid>.json` (a record uuid and its byte
offset; the whole file is never read — an architect session's reaches
155MB), extracts from the records above it the `<message>` spans of assistant
records, the async asks (a `tool_use` of `mcp__doperpowers__AskUserQuestion`
with `async` true and its accepted `tool_result` — the engine writes a
plugin tool's row only once the call resolves, which for an async ask is at
once, so the row is there when `Stop` fires) and their deliveries (the row
whose text carries the delivery head, in whichever form the ask design
stores it), appends them with `src` `<record-uuid>#<span-index>` for a
span and the call id for an ask or its answer — one record's spans
through `log_append_batch`, which takes the locks once, checks `(kind, src)`
inside them, and appends the spans together; the position advanced only
after the batch — and skips any `(kind, src)` already present (a `question` and its `answered` share the call id), so a Stop that fires twice, a turn
interrupted and resumed, or an export that died after the first span of a
record exports each mark once. Exports are serialised by `cursors/export/<session-uuid>.lock`. Locks are
taken in one order everywhere: the export lock, then `.sync.lock` shared,
then the writer's `<file>.lock`; `delivered/<session-uuid>.lock` is taken
only when none of those is held; the daemon's exclusive `.sync.lock`
phases hold no other lock. The export boundary is the position,
never "the last user record": peer frames arrive as user-role records and
would move such a boundary past a mark. The position is initialised at `SessionStart` to the transcript's current
end only when no position exists for the session, so nothing written
before the plugin arrived is exported; a `resume`, `clear`, or `fork`
start with a position keeps it, so a mark written before the process died
is exported at the next `Stop`; a `Stop` that finds no position (the
plugin installed mid-session, the file lost) exports the trailing run of
assistant records at the end of the file and sets the position there — a
bounded first-use policy, stated as such: a mark earlier in that one turn,
before a peer frame interrupted it, is not exported.

Mark extraction is a Python port of the grammar `hooks/mods/to-human.tsx`
applies for display, not its `TAG` regex alone: tags inside inline code
and fenced code are literal, nested marks are distinct runs, an unclosed
mark runs to the end of the text, and every alias reads as `message`.
Parity fixtures ported from `tests/mods/` pin it: a backticked
`<message>example</message>` is not a message to the host. A blocking ask
— the native `AskUserQuestion`, or the plugin's with `async` false — is not
an event: the session is `waiting`, which the daemon publishes as its
state, and the human goes to the session. `sminos chat --host` prints
`message`, `question`, and `answered` events, an open question marked as
such; it is the human's view of what every session sent them.

The output style itself does not change. Its first sentence, "The human does
not watch this session", stays as written: it is what keeps the working
record and the message apart, and a message that is also logged is still a
message.

## 5. The in-charge line

Every member has one line saying what it is in charge of, shown by `list`
beside its state. Sources, in order; the first present wins:

1. The latest `in-charge` event with `source` `set`: `sminos charge
   [<alias>] "one line"` from the session or the operator, or `spawn
   --brief`. Explicit, and more specific than a name.
2. The latest `in-charge` event with `source` `derived` (below).
3. The harness name, when the human set it (`name_source` `user`):
   "현우진", "interactive learning". A name is a responsibility more often
   than not, and the human chose it, so it stands as the line until the
   session's first derive; a derived line says more than a few words can
   (the charge names design, 2026-10-21).
4. The session's title, as the harness names it ("Session name" in
   `/status`): the latest `custom-title` record of its transcript (set by
   `/rename`; an empty one clears it), else the latest `ai-title`, which
   follows the conversation's topic rather than the responsibility — the
   "interactive learning" session's read "구글 테이크아웃 Gemini 대화 기록".
   A fallback, never preferred. On the session's machine it is read from the
   transcript; elsewhere it is the last `titled` its machine published (§8).
   The harness re-appends both records thousands of times a session, almost
   always unchanged (two of the owner's sessions, 2026-10-17: 1 535 and
   3 776 re-appends, one value each), so publishing only a change costs a
   few events a session.
5. Empty.

`sminos derive [<alias> | --all]` asks a session what it is in charge of
without interrupting it, by forking it headless:

    claude -p --resume <session-uuid> --fork-session --session-id <fork-uuid> --tools "" --output-format json \
      "In one line: what is this session in charge of in this project — its standing responsibility, not its latest step? Answer with the line only."

Verified 2026-10-13 on a live transcript (Surprises & Discoveries): the fork
answers from the session's context, with no tools, and leaves a copy of the
parent transcript as a new session file. The fork is an **internal fork**:
`derive` starts it with `SMNS_INTERNAL=1` in its environment, so the hook
records nothing for it, and writes `$SMINOS_HOME/internal/<pid>` before the
harness can register it, so reconciliation and `members()` ignore its
session record; `derive` deletes the fork's transcript after reading the
answer (`transcript_path()` in sminos.py locates it) and the marker with
it, and markers older than a day are swept on any `derive`. Without this a
derivation would join a phantom member and, since the fork runs under the
output style, record its answer as a host message. The answer is the
`result` field of the last JSON object on stdout, stripped of marks, first
line, at most 120 characters. `derive` runs only for a local member with no
`set` line, at least 10 tool calls by its model (the `tool_use` blocks of
its main conversation's assistant records), and no `derived` event in the
last six hours; `--all` applies that to every local member but one whose
fork failed within the hour, members with no derived line first and the
others oldest line first. The daemon runs `derive --all --refreshes 2`
every five minutes (§8): its forks run one after another, each up to two
minutes, so it forks at most two members that already have a line and
leaves the rest to the next run, and a member's first line comes within
minutes of its tenth tool call; a run that refuses everyone costs about a
second. The cost is one model
call that reads the parent's prompt cache when the session was active
within the cache's hour, and rebuilds it otherwise.

For a session whose name the engine made up, the same fork also proposes a
name after the line (the event's `name`), which the sminos plugin's name mod
applies with the engine's own `/rename` once the session is between turns;
an alias a member held before keeps
reaching it behind every current alias, with a note naming it now
(`docs/doperpowers/specs/2026-10-20-sminos-charge-names-design.md`).

## 6. Spawning siblings; retiring

`sminos spawn <alias> "<task>" [--role R] [--brief B] [--cwd DIR]
[--worktree NAME] [--model M] [--settings FILE] [--effort E] [--wait]`
from a member or the operator starts a session in the working directory's
project (or `--cwd`'s). `--group` and `--parent` leave: the project is the
group and there is no parent. The spawn records `joined` with `by` the
spawner's alias (`""` from the operator), `seat` the seat id, and, with
`--brief`, an `in-charge` of source `set`; spawning into a seat another
session occupies, or one retired, first appends `retired` (`replaced`) for
that session (§3, membership rule). `list` shows the provenance as a dim
`by <alias>` suffix; the chart draws no tree.

Every spawn renders `references/spawn-preamble.md`, rewritten for the
project family (M5): who the seat is and in which project; read the chat
first; untagged is recorded, `@alias` delivers, `@all` wakes every live
member and is for what all must act on now; `<message>` is how it reaches
the host; `sminos status` and `sminos charge`; spawn a sibling only for a
separable standing responsibility, a subagent for anything else. The board
pipeline's workers are spawned by `skills/issue-tracker/scripts/
execute-dispatch.sh` and `review-dispatch.sh`; their bootstraps are their
protocol, and the project preamble ahead of it is true for them too. Those
two scripts gain one argument each, `--brief "ticket #<n>: <title>"` and
`--brief "review PR #<n>"`, so a worker's in-charge line is its ticket; the
tests of those scripts stub sminos itself, so M2 adds a contract test
through the real CLI with the stub `claude`.

`sminos retire <seat> [--purge]` stops one seat and records `retired`;
`--cascade` leaves with the tree. `sminos status` records a `status` event
as well as the local `now` line (today it writes only the record).
`fill`, `resume`, `reply`, `attach`, `meta`, `sync` are unchanged in shape,
local-only (§2).

## 7. Views

`sminos list [<project>] [--all] [--state W] [--json]` prints one heading
per project (the working directory's by default; `--all` every project
known locally), newest member first:

    MAWS
      maws-fe     idle                GUI AI agent workspace: main app architect
      cua_repl#feb3e71e  busy         cua_repl browser and GUI tool          · now: fixture 8/8
      cua_repl#1ea561bc  idle         cua_repl bench runner
      maws-45     waiting             owner artifacts page                   · by maws-fe
      현우진       idle  @mini 3m      뉴런 교재 기반 문제 작성자 스킬

Columns: alias, with `#short` when another member of the project shares
the alias; state word (for a member on another machine, `@<machine>` and
the age of its last `state` event); the in-charge line; then `· now:` the
`status` line when set and `· by <alias>` the provenance. Seat-less
interactive sessions appear like any seat. `--json` carries every member
with `session`, `short`, `machine`, `state`, `charge`, `charge_source`,
`by`, `status`, `worktree`, `seat`. `chart` and `tui` draw the same rows
grouped by project, flat; `tui`'s `b` opens the project chat, and `Enter`
attaches to a local member as today. The chart's tree layout leaves with
the tree.

`sminos chat [<project>] [-n N] [--since TS] [--host] [--kind K] [--json]`
reads the merged log (§3); the member-facing frame becomes
`[sminos chat <project-name> <writer-short>:<seq> from <alias> → @you | unread N]`,
the id letting a member recognise a repeat (§4).

## 8. The mirror and the daemon

A project whose `.smns` names a remote has its `log/` attached to it (§1).
The remote is any git URL the machine can push to over SSH; a bare
repository on a machine the project's machines reach (the Tailscale host,
the Hetzner box) avoids any hosted API's limits, and GitHub works too. Each
machine writes only files named with its own machine name, so integrating
the remote never conflicts. Two machines with the same host name would:
`$SMINOS_HOME/daemon/machine.json` holds a random instance id, pushed at attach as
`log/machines/<machine>.json`; a daemon that finds its name claimed by
another instance id refuses to run and says so.

**The sync invariant.** Local events are committed before anything from
the remote is integrated, so no event is ever outside a commit; git never
rewrites `log/` while an appender writes, and an appender never writes
while git rewrites — `log/.sync.lock` is taken shared by `log_append` for
the append and exclusive by the daemon for each phase that touches the working tree and
for nothing else: fetch and push, the phases that wait on the network,
run outside it with a 30-second bound each, so an unreachable remote
never stalls a local `say` or a Stop export; and the integration phase,
under one exclusive hold, first commits whatever was appended during the
fetch and then integrates, never releasing between the two — an append
during the fetch would otherwise dirty the tree the rebase refuses (the
failure the invariant exists to remove, reproduced by the round-three
reviewer); a rejected push's retry fetches again and repeats that phase; one sync at a time per project
(`.sync-op.lock`); and a push rejected because the remote moved is
retried after another fetch and integration, bounded (three). The first draft's order, pull then commit,
fails on the first append after a file is tracked: `git pull --rebase`
refuses a dirty tree (reproduced by both reviewers, exit 128). Within the
invariant the executor chooses the git commands; `stash` is not among them
(an event in a stash is outside a commit). `log_read` reads only the
top-level `*.jsonl` of `log/`, so `machines/` is invisible to it.

`sminos daemon run [--interval 5]` loops `sminos daemon tick` over every
project known locally — the sync duties and the publishing of `state` and
`titled` only for those with a remote or a hub (a local view reads liveness
and titles directly, so publishing them in a local project would only grow
its log), the rest —
`renamed` included, the log's only record of a name change — for all, so a
remote-less project's owed deliveries are retried too —
`tick` being one iteration, used by tests;
`sminos daemon install` writes a launchd agent
(`~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist`, modelled on
`application-agents/triaging-feedback/infra/worker-host`, its
`EnvironmentVariables` carrying what `skills/issue-tracker/SKILL.md` says a
launchd-run sminos needs: `SMINOS_HOME` and the gateway route, since
`derive` runs `claude`); `sminos daemon status` prints the last tick per
project. Each tick, with the harness peer cache refreshed first (the
in-process caches in sminos.py are per invocation; `run` must refresh them
per tick):

1. **Integrate.** Under the invariant above: commit local changes, fetch,
   integrate. A failure is logged to `$SMINOS_HOME/daemon.log` and the tick
   continues on the stale mirror.
2. **Reconcile.** As every CLI call does (§2).
3. **Publish.** For each local member, compute `state()` as today; when it
   differs from the last `state` published for that session and differed on
   the previous tick too, append `state` (one tick of persistence drops the
   flip inside a tool round). When the harness name differs from the last
   known alias, append `renamed` with its `name_source`. When the session's
   title (§5, source 4) is not empty and differs from the last `titled`
   published for it, append `titled`: a member is named by it on the desk
   and on every other machine, its ended sessions and an offline machine's
   included. A transcript scanned every tick is read backward from its end
   and not again while it is unchanged. A session of this machine whose
   membership has ended is published the same way, looked at once per
   retirement for the life of the daemon's process, since its transcript
   has stopped changing: a session renamed and closed since the last tick
   is retired by this tick's reconciliation before it could be published
   as a member, and one that ended before the daemon ran never was one.
4. **Deliver.** For each local member, every event owed to it (§4), in
   writer order from its settled prefix: push a frame or resume, exactly as
   a local `say` would, and settle per §4.
5. **Push.** Commit what this tick appended and push, so a state published
   in this tick reaches the remote in this tick.
6. **Derive.** Every five minutes, start `derive --all --refreshes 2` (§5) as a child process and
   do not wait for it — a fork's model call can take minutes, and the
   delivery interval must not; one derivation in flight at a time.

A local project has no mirror; the daemon still delivers what the fast
path left owed, when it runs, because it visits every project. The alternative transport, a small server
with push notifications, was rejected for now: git gives replication,
history, SSH authentication, and offline operation for free, and a
five-second poll is inside what agent-to-agent messaging tolerates.
Nothing here forecloses a server later: the daemon's duties are the same
against any mirror.

The Cursor cloud-agent write-up (cursor.com, "cloud agent lessons") is the
nearest prior art: they decoupled the conversation state from the machine
running the agent into an append-only store streamed to clients. This log
is that layer for a project; the agent loop stays the Claude Code process,
which is why Temporal, their choice for the loop, has no place here.

## 9. What leaves, what stays, what this is not

Leaves: the host and family reach (`family_of`, `reach_of`,
`is_family_seat`, `--team`, `--parent`, `--group`, `retire --cascade`), the
per-host chat files under `chats/` and their in-place `delivered` maps,
`chat_seen` on seat records, the `groups/` directory. `sminos migrate`
imports each `chats/<host-seat-id>.jsonl` into the project of the host's
`cwd` under writer `legacy/<host-seat-id>` — a member's lines as `say`
events, the operator's as `human` (the routing table's kinds) — preserving
`ts`, `from`, and tags as `to` resolved against the seats of that time
(unresolvable tags stay as text); existing seat records keep working, their
project resolved from `cwd`, their sessions joined by reconciliation.

Stays: seat records and their locks under `$SMINOS_HOME` (machine-local
operational state: `current`, `short`, `gen`, worktree, settings, effort,
the reply cache); `state()` and the seven state words; `spawn`'s launch
path and gateway-route scrubbing; `send --wait`; `fill`, `resume`, `reply`,
`attach`; the board pipeline's dispatch scripts and bootstraps, except the
one `--brief` argument each (§6). The log is the source of truth for
everything two machines could disagree about; what only this machine needs
stays in its own files.

Not here: the chief-of-staff agent (a reader of the log on the human's
behalf; whether a resident session or a per-event routine is decided when
the log is in use), inbound Slack or mail, a human seat, remote control of
a session's process, any change to the board loop or to `decomposing`,
and the sessions MAWS launches. Under `MAWS_NATIVE_TO_HUMAN`, the plugin's
ask tool is not registered, and `mcp__maws__ask` (blocking false) carries
a session's async questions; the readers know its shape, read from MAWS's
transcripts (board #76: `question` at the acceptance, `answered` at the
`[MAWS ask <id>]` steer, `src` the call id). MAWS launches with an
`sdk-ts` entrypoint and marks its sessions members (`SMNS_MEMBER`, §2), so
such a session joins the project it works in and its messages and asks
record as a terminal session's do.

## Acceptance

Run from a scratch repository `R` with `sminos project init --name demo`
committed, `SMINOS_HOME` pointed at a temporary directory, and two
interactive sessions opened in `R`, the first renamed with `/rename a` and
the second left with its derived name (call it `b`), unless a step says
otherwise.

1. `sminos list` in `R` prints a `demo` heading with rows `a` and `b`, each
   with a state word, no `seat add` having been run.
2. In `a`: `sminos say "merged #12"`. `b`, idle, starts no turn; `sminos
   chat` in `b` prints the line attributed to `a`. In `a`: `sminos say "@b
   look at X"`. `b` starts a turn whose first content is a
   `[sminos chat demo … from a → @you …]` frame carrying `look at X`. In
   `a`: `sminos say "@all rebase in progress"`. Every live member but `a`
   starts a turn.
3. `a` writes `<message>done with the parser</message>` in a turn, and in
   the same turn `` `<message>not this</message>` `` inside backticks.
   After the turn, `sminos chat --host` prints `a: done with the parser`
   and nothing for the backticked one. `a` then calls
   `mcp__doperpowers__AskUserQuestion` with `async` true and one question
   with two options; `chat --host` shows the question with both labels,
   open; after the human answers, it shows the answer under it.
4. In `a`: `sminos spawn c "wait for instructions"`. `list` shows `c` with
   `· by a`. `sminos retire a` leaves `c` live in `list`. A third session
   renamed `/rename c` makes `list` show both as `c#<short>`, and `sminos
   say "@c hi"` is refused naming both.
5. `sminos charge b "owns the GUI tool"`; `list` shows that line for `b`
   with `charge_source` `set` in `--json`. `sminos charge a "parser"`;
   `list` shows `parser` as `a`'s line and `a` still as its alias. For a session with ≥10 prompts, a derived name, and no
   line, `sminos derive <alias>` prints a one-line answer, `list` shows it
   with `charge_source` `derived`, `list --json` has the same number of
   members before and after, `chat --host` has no new line, and the
   project's transcript directory holds the same number of files before
   and after.
6. With two homes on one machine — `HOME` and `SMINOS_HOME` each, their
   own `~/.claude/sessions` and inbox sockets, `DAEMON_HOST=h1` and `h2` —
   a local bare repository as `.smns`'s remote, `a` spawned under h1 and
   `b` under h2: after one h2 tick and one h1 tick, `sminos list` under h1
   shows `b` with `@h2`; `sminos say "@b hello"` from `a`, then one h1 tick, reaches no socket
   until h2 ticks, and then `b`'s socket receives the frame; a second h2
   tick delivers nothing more; after `b` goes idle for two h2
   ticks and one h1 tick, `list` under h1 shows `b idle @h2`. With `sminos daemon run --interval 1` under both homes and the bare
   repository on local disk, the same `say` lands within two seconds (the
   interval bounds the loop, not a fetch or push; over a network the bound
   is the interval plus those).
7. `tests/sminos/run-sminos-tests.sh` passes, and so do
   `tests/issue-tracker/test-execute-dispatch.sh` and
   `tests/issue-tracker/test-review-dispatch.sh`.

## Execution

Constraints binding every milestone: Python 3 standard library only in
`sminos.py`, as today; no new daemon framework; the stub-`claude` harness in
`tests/sminos/run-sminos-tests.sh` is the test substrate, extended, not
replaced; every verb keeps its exit codes (`EXIT_USAGE`, `EXIT_UNKNOWN`);
`$SMINOS_HOME`, `HOME`, and `DAEMON_HOST` remain the overrides tests use;
`skills/issue-tracker/scripts/execute-dispatch.sh` and `review-dispatch.sh`
change only by the `--brief` argument of §6. The spec is executed as one
spec by a `doperpowers:plan-executor`: six milestones in one CLI, one
hook, and one skill document.

### M1 — Project identity and the log

What exists at its end: `sminos project init|show|attach`;
`resolve_project` with its three outcomes (§1); the `projects/<id>/`
layout; `log_append` and `log_read` with per-writer `seq` under the file
lock and the shared `.sync.lock`, millisecond `ts`, `(ts, writer, seq)`
display merge; address resolution
(`resolve_tags`: the four tag forms, ambiguity and unknown refusals);
`say`, `send`, and `chat` writing and reading the project log with the
routing table of §4, the fast-path delivery record, and the cursor
semantics of §3; `migrate` importing `chats/`. Touches
`skills/sminos/scripts/sminos.py` (`derive_group` becomes the fallback of
`resolve_project`; `now`; `leading_tags`; `chat_*`, `seen_advance`,
`unread_for`, `compose_chat_frame`, `push_member`, `cmd_say`, `cmd_chat`,
`send_to_seat`, `migrate`), `tests/sminos/run-sminos-tests.sh`.
Interfaces: produces `Project`, `resolve_project`, `log_append`,
`log_read`, `cursor_load`, `cursor_save`, `delivered_load`,
`delivered_record`, `resolve_tags`. Decisions here: the writer
file name replaces `/` in the writer id with `.`; `seq` is read as the
last line's `seq` plus one under `flock` on `<file>.lock`; a malformed
line is skipped on read and never rewritten; `--in <project>` on the
operator's `say` accepts a project name or id; `attach` on a populated
`log/` integrates with unrelated histories allowed; in this milestone an address resolves among seat records whose `cwd`
resolves to the project, and M2 extends it to seat-less members; the
destination rule of §2 and the refusal of mixed-project tags; the delivery record's shape (settled prefix per writer, one pending event
with its attempt count) and `deliver_next` as the one delivery operation
for both paths; `log_append_batch` and the lock order of §4; `@all`
resolved to the live members at submission. Does not touch: membership (`list`
still prints today's groups until M2), the hook, the daemon. Proves:
acceptance 2 (local delivery), and tests pin: two writers' lines interleave
by `ts` while one writer's keep `seq` order under a backwards `ts`; `chat`
advances the cursor and `-n` does not; a `say` to `*` pushes nothing;
`@all` pushes to every live member and resumes none; a tag matching two
seats is refused naming both as `alias#short`; `@"two words"` resolves; `attach` with an unreachable remote succeeds and
preserves local files; a message tagged into
another project lands in that project's log and nowhere else, and tags
naming two projects are refused; when a writer's event 10 fails to push and its event 11 would succeed, 11
is not delivered before 10 and both arrive, in order, on a later attempt,
also when the sender's fast path and a daemon tick run at once; a `@all`
written before a member joined is never delivered to it, and never to its
sender.

### M2 — The project family

What exists at its end: members derived by the membership rule plus
reconciliation (§2), seat-less harness sessions included; `list`, `chart`,
`tui` flat per project with the columns of §7; reach is the project with
`project/alias` and the no-project case; `spawn` without
`--group`/`--parent`, recording `joined` with `by` and `seat`, `retired`
(`replaced`) for a displaced session, and `in-charge` from `--brief`;
`fill`/`resume` of a retired seat re-joining; `retire` without `--cascade`
recording `retired`; `status` recording its event; `seat add` recording
`joined`; the internal-fork marker honoured by `members()` (the marker is
written by `derive` in M3; `members()` ignores `$SMINOS_HOME/internal/`
pids from here); the two dispatch scripts passing `--brief`, with a
contract test through the real CLI and the stub `claude` asserting the
worker's charge, its spawn banner, and its seat identity as the board
consumes them. Touches `sminos.py` (`seats`, `find_seat`, `resolve_seat`,
`caller_seat`, `cmd_list`, `cmd_spawn`, `spawn_fresh`, `cmd_fill`,
`resume_session`, `cmd_retire`, `cmd_status`, `cmd_seat_add`, the removal
of `family_of`/`reach_of`/`is_family_seat`), `sminos_chart.py`,
`sminos_tui.py`, `skills/issue-tracker/scripts/execute-dispatch.sh`,
`review-dispatch.sh`, tests. Interfaces: produces `members`, `Member`,
`reconcile`; consumes `resolve_project`, `log_read`, `log_append`,
`resolve_tags`. Decisions: a harness session without a seat record is a
member with alias = harness name and `session` = its id, and `send` to it
uses its socket like a seat's; a member's `by` is the first non-empty `by`
among its `joined` events; `list` sorts by join time, newest first; a
retired member hides as today; `reconcile` runs at the start of every CLI
call that reads the project and costs one `log_read`. Does not touch: the
hook, `charge`/`derive`, the daemon, the preamble text (M5). Proves:
acceptance 1, 4; tests pin that a seat-less harness session in the
project's cwd lists, that `spawn --parent` is refused as unknown, that
retiring a spawner leaves the spawned seat live, that a fresh fill writes
`retired` (`replaced`) then `joined`, that `fill --resume` of a retired seat
re-joins with the same uuid, that a session running before the log existed is joined on the first
`list`, that a retired seat stays retired across repeated `list` and
`tick` calls and re-joins only when `fill --resume` revives it, that a
hook `joined` followed by an operator `retire` and a `resume` keep their
order under a clock stepped back (one writer, by `seq`), and that
`status` from one home is visible in `list --json` from the other after
a sync.

### M3 — Messages to the host and the in-charge line

What exists at its end: `hooks/smns-record.sh` on `Stop` and
`SessionStart`, `sminos record` with the export position and `src`
idempotency, the mark parser port with its parity fixtures, `chat --host`;
`sminos charge`; `sminos derive` with the precedence of §5, the internal
fork (environment marker, pid marker, transcript deletion), and the
`charge_of` resolution; `list` showing the in-charge line and its source.
Touches `hooks/hooks.json`, `hooks/smns-record.sh` (new), `sminos.py`
(`cmd_record`, `cmd_charge`, `cmd_derive`, `charge_of`, `extract_marks`),
tests (fixture transcripts with marks, including a backticked tag, a
fenced block, a nested alias mark inside a `message`, an unclosed mark, a
peer frame as a user-role record mid-turn, an async ask's `tool_use` and
`tool_result` with a later delivery row, and a blocking ask; the stub `claude` gains
`-p --resume --fork-session`, printing a JSON with `result` and
`session_id`, creating the fork's transcript file, and running the hook
script with a `SessionStart` and a `Stop` payload the way the harness
would). Interfaces: produces `charge_of`, `extract_marks`, `extract_asks`;
consumes `members`, `log_append_batch`. Decisions: the export position is the uuid and byte offset of the last
exported assistant record, initialised at `SessionStart` to the file's end
only when absent, kept across `resume`, and, when missing at `Stop`, set
by the trailing-run policy of §4; export consumes `log_append_batch`,
never nested single appends; `derive`'s fork runs with a 120-second timeout and a
failure prints the stderr tail and writes nothing. Does not touch: the
daemon; the output style. Proves: acceptance 3, 5; tests pin that a `<to-human>` span records as `message`, that an async
ask records `question` with its option labels and its delivery records
`answered` with the same `src` while a blocking ask records nothing, that
the backticked and fenced tags record nothing, that a Stop replayed over the same transcript appends nothing, that an export killed after the first of two spans in one record appends
only the second on retry, that a mark left unexported by a process that
died is exported once after `SessionStart(resume)` and the next `Stop`, that a first `Stop` with no position followed by a peer
frame exports the trailing run and nothing earlier, that a user-named
session is never derived, that `charge` beats a user-set name and the name
beats a derived line, and that `derive` leaves the member count and the
host stream unchanged and the fork's file deleted.

### M4 — The mirror and the daemon

What exists at its end: `sminos daemon run|tick|install|status` with the
five duties of §8 under the sync invariant; the instance-id claim; the
slow-path delivery with per-recipient records and the 60-tick give-up;
`state` and `renamed` publication; remote members in `list` with
`@<machine>` and age. Touches `sminos.py` (`cmd_project` for attach's
mirror half, `cmd_daemon`, `sync_mirror`, `deliver_owed`, `publish_state`,
`refresh_caches` per tick), a launchd plist template under
`skills/sminos/references/`, tests (two homes with `HOME`, `SMINOS_HOME`, stub agent state and inbox
sockets each, the stub `claude` extended to allot session uuids from a
counter shared across homes — today's stub derives them from a per-state
counter, so two empty homes would mint the same uuid — asserted distinct
before anything replicates; a bare repository; `daemon tick` driven phase
by phase, and one `daemon run --interval 1` process). Interfaces:
produces `tick`; consumes everything above. Decisions: git is invoked with `-C log`, `GIT_TERMINAL_PROMPT=0`, and a
30-second `timeout` on fetch and push; the exclusive `.sync.lock` covers
the commit and the integration and nothing that waits on the network;
`derive --all` is a `Popen` child whose pid the daemon remembers so a
second is not started while it runs; the tick's duty order is §8's. Does not touch: the dispatch scripts. Proves: acceptance 6;
tests pin that an append after a successful sync, while the other home
publishes, syncs on the next tick with both histories intact; that an
event to two local members with the second push failing is delivered to
the first once and to the second on a later tick; that a daemon restarted
between the push and the record delivers at most once more; that a stalled remote (a fetch that hangs) leaves a concurrent `say` and a
Stop export unblocked; that an append during a paused fetch is committed
and integrated in the same exclusive phase; that an owed event in a remote-less project is delivered by
`run`; that `run` keeps delivering while a derivation child sleeps; that a
state flip lasting one tick is not published; that a claimed machine name
refuses to run; and that `run` sees a session that appeared after it
started.

### M5 — The skill and the preamble, as behavior

What exists at its end: `skills/sminos/SKILL.md` rewritten for the project
model (overview, protocol, operator surface, spawning, project and mirror,
daemon, board pipeline), and `references/spawn-preamble.md` rewritten per
§6, both developed with `doperpowers:writing-skills` and its evaluation:
before/after scenarios run against the new text for (a) a status line
written untagged versus a blocking change tagged `@all`; (b) reporting to
the human through `<message>`, not `say`; (c) a separable standing
responsibility spawned as a sibling versus a bounded task run as a
subagent; (d) a board worker's escalation unchanged (park the ticket, not
`say`). Touches those two files and `tests/sminos/run-sminos-tests.sh`
(the preamble's rendered text). Decisions: the skill keeps the project's
voice and the "your human partner" phrasing; the preamble stays under 40
lines. Does not touch: code paths. Proves: the eval transcripts recorded
in this spec's Surprises & Discoveries with the scenario verdicts.

### M6 — Docs, acceptance, version

What exists at its end: `CLAUDE.md`'s repo map lines for `hooks/` (the new
hook) and sminos; a dated line in
`docs/doperpowers/specs/2026-09-26-sminos-family-chat-design.md`'s Decision
Log saying its deferred human seat and cross-machine family resumed here;
the acceptance section run as written and its transcript in this spec's
record; `scripts/bump-version.sh` to the next minor version in the same
commit. Touches those files and this spec. Proves: acceptance 7 and the
whole section.

### Concrete Steps

Working directory: the repository root, on the feature branch.

    tests/sminos/run-sminos-tests.sh            # expect: "... passed, 0 failed"
    tests/issue-tracker/test-execute-dispatch.sh && tests/issue-tracker/test-review-dispatch.sh
    scripts/lint-shell.sh

Acceptance 6 by hand, one machine (the test suite does the same with the
stub harness):

    git init --bare /tmp/smns-remote.git
    mkdir /tmp/R && cd /tmp/R && git init -q
    H1="HOME=/tmp/home1 SMINOS_HOME=/tmp/home1/sminos DAEMON_HOST=h1"; H2="HOME=/tmp/home2 SMINOS_HOME=/tmp/home2/sminos DAEMON_HOST=h2"
    env $H1 sminos project init --name demo --remote /tmp/smns-remote.git && git add .smns && git commit -qm smns
    env $H1 sminos spawn a "wait" ; env $H1 sminos daemon tick          # a joins under h1 and is pushed
    env $H2 sminos project attach ; env $H2 sminos spawn b "wait" ; env $H2 sminos daemon tick
    env $H1 sminos daemon tick ; env $H1 sminos list                     # expect: b  … @h2 <age>
    env $H1 sminos say "@b hello" ; env $H1 sminos daemon tick           # recorded and pushed to the remote
    env $H2 sminos daemon tick                                           # expect: "delivered 1 to b"
    env $H2 sminos daemon tick                                           # expect: "delivered 0"

### Interfaces and Dependencies

In `skills/sminos/scripts/sminos.py`:

```python
class Project(NamedTuple):
    id: str          # uuid from .smns, or "local-<name>"
    name: str
    remote: str      # "" for a local project
    root: str        # directory holding .smns, or the owning repository
    home: str        # $SMINOS_HOME/projects/<id>

def resolve_project(cwd: str) -> Project | None        # None: no project (§1)
def writer_id(session_uuid: str | None = None) -> str   # "<machine>/<uuid>" | "<machine>/human"; a session's lifecycle always under its own id
def log_append(project: Project, writer: str, kind: str, **fields) -> dict   # ts (ms), seq under the file lock, .sync.lock shared
def log_append_batch(project: Project, writer: str, events: list[dict], skip_src: bool = True) -> list[dict]   # the locks once; drops events whose (kind, src) is present
def log_read(project: Project, since: dict | None = None, kinds: tuple = (), to_session: str | None = None) -> list[dict]
def cursor_load(project: Project, session_uuid: str) -> dict
def cursor_save(project: Project, session_uuid: str, cursor: dict) -> None
def delivered_load(project: Project, session_uuid: str) -> dict           # {writer: {"settled": seq, "pending": seq|None, "attempts": int}}
def delivered_settle(project: Project, session_uuid: str, writer: str, seq: int) -> None   # refuses a seq that is not settled+1
def delivered_fail(project: Project, session_uuid: str, writer: str, seq: int) -> None
def owed(project: Project, member: "Member") -> list[dict]                   # in writer order from the settled prefix (§4)
def deliver_next(project: Project, member: "Member") -> dict                 # under delivered/<session>.lock: choose, push, settle or fail; {"delivered": int, "pending": int}
def resolve_tags(project: Project, text: str) -> tuple["Project", list[dict], str, bool]   # destination, recipients [{session, alias}], text, wake; raises on ambiguity/unknown/mixed projects

class Member(NamedTuple):
    session: str; short: str; alias: str; name_source: str; machine: str; local: bool
    state: str; state_age: float | None; charge: str; charge_source: str; status: str
    by: str; worktree: str; seat: dict | None

def members(project: Project) -> list[Member]          # ignores $SMINOS_HOME/internal/<pid> sessions
def reconcile(project: Project) -> int                 # joined events appended for unrecorded local sessions
def charge_of(member: Member, events: list[dict]) -> tuple[str, str]
def extract_marks(text: str) -> list[dict]             # [{"kind": "message", "text": str}], code-aware; every alias is a message
def extract_asks(records: list[dict]) -> list[dict]    # [{"kind": "question", "src": call id, "text": [str], "choices": [str]} | {"kind": "answered", "src": call id, "text": str}]
def tick(project: Project) -> dict                     # {"integrated": bool, "reconciled": int, "published": int, "delivered": int, "pushed": bool}
```

CLI verbs added: `project init|show|attach`, `charge`, `derive`, `record`,
`daemon run|tick|install|status`. Removed: `--group`, `--parent`, `--team`,
`retire --cascade`. Hook: `hooks/smns-record.sh`, events `Stop` and
`SessionStart`, calling `"$CLAUDE_PLUGIN_ROOT/skills/sminos/scripts/sminos" record`.
Dispatch scripts: one `--brief` each.

## Surprises & Discoveries

- Observation: a session can be asked what it is in charge of without
  touching it, by a headless fork; the fork copies the parent transcript.
  Evidence (2026-10-13, a 41-line demo session): `claude -p --resume <id>
  --fork-session --tools "" --output-format json "…"` answered `<message>This
  session has no standing task beyond showing you the to-human output
  style's marks on request…</message>`; usage `output_tokens 243,
  cache_creation 45613, cache_read 0`; a new transcript of 55 lines / 472K
  appeared beside the parent's 41 lines / 176K and was deleted by hand.
  The `<message>` wrapping is why the fork must be internal (§5).
- Observation: the harness keeps an `ai-title` per session and rewrites it
  as the topic moves, so it cannot stand for the responsibility.
  Evidence: the session the human named "interactive learning" carried
  `"aiTitle":"구글 테이크아웃 Gemini 대화 기록"` as its latest of 54 titles;
  the MAWS architect session carried 2,597 titles, the latest "GUI AI agent
  workspace charter".
- Observation: the harness's session registry already groups the fleet by
  project, implicitly, and aliases collide inside a project.
  Evidence: `~/.claude/sessions/*.json` on 2026-10-12 listed 26 live
  sessions whose `cwd` fell under six repositories, MAWS holding six and
  manim-master four, two user-named (`nameSource: "user"`), and two MAWS
  sessions both named `cua_repl`.
- Observation: `git pull --rebase` refuses the working tree an append-only
  log produces as soon as a tracked file grows.
  Evidence: both independent reviewers reproduced it on a scratch bare
  remote and clone — appending a second line to a committed writer file
  made the pull exit 128. The sync invariant (§8) commits first.
- Observation: the harness can start `Stop` hooks before the turn's last
  transcript record is written.
  Evidence: in the live acceptance run (2026-10-14), 1 mark in 24 was
  exported one `Stop` late, 73 s. Transcript writes are queued behind a
  100 ms flush (`FLUSH_INTERVAL_MS = 100`, bundle 2.1.292,
  `cli.pretty.js` near 819427), and the Stop hooks start without a
  flush. Before the F1 fix, a mark in a session's last turn would have
  waited for a resume.
- Observation: a `claude --bg` seat does not inherit its spawner's
  environment, so a non-default `SMINOS_HOME` did not reach it: its hook
  and CLI would have used the operator's real registry and run the
  one-way import there. This is the M1 incident's failure, at the spawn
  boundary.
  Evidence: a live probe in M6. A flagless `claude --bg --resume` does
  keep the launch's `--settings` and its env (2.1.299).
- Observation: `claude agents` lists an interactive session with `id:
  null`, so sminos has nothing it can stop. Evidence: the M6 live run,
  where `retire a` was undone by reconciliation 2 s later until F2.
- Observation: M5's eval. Four scenarios were run on the old text
  (commit af0511a2) and on the rewrite, with 30 opus subjects in all.
  Transcripts and verdicts are in
  `docs/doperpowers/specs/2026-10-13-smns-project-log-m5-evals.md`.

  | scenario | old | v1 | v2 | v3 | final |
  | --- | --- | --- | --- | --- | --- |
  | (a) untagged status, `@all` for a blocking change | 2/2 | 2/2 | | | 2/2 |
  | (b) the human through `<message>` | 2/2 | 2/2 | | | 2/2 |
  | (c) sibling for standing work, no session for bounded work | 0/2 | 2/2 | 2/2 (one misread) | 3/3 | 2/2 |
  | (d) a board worker escalates by parking | 1/2 | 0/2 | | | 3/3 |

  Evidence:
  - (a) and (b) already pass on the old text, because the old `@all`
    and the output style already produce the behavior. Final, a-final-2:
    "every live member has to act on it right away, so I sent it with
    @all", with the `<message>` to the human "since no tag reaches him".
  - (c) fails on the old text through parent framing. c-old-1: "maws-bench
    (my child seat …)"; c-old-2: "I spawned it as my own child … Fixture
    updates come to me to merge". Every subject on the rewrite spawned a
    sibling with `--brief` and claimed no parentage. c-v1-2: "A spawned
    session would leave a standing member behind after a one-afternoon
    job." A v2 misread ("a subagent of the session that owns it" read as
    the owner of the area) was fixed in v3. In 3 of the 7 rewrite runs,
    the bounded task went to the member already in charge of that area.
    Those are passes, not failures. §6's rule exists so that bounded
    work does not create new sessions, and handing it to the session
    that holds the area is the intended collaboration: a session is in
    charge of a responsibility, and a sibling stepping into that area
    with its own subagent would be the worse outcome.
  - (d) fails through a side channel that invites the answer outside the
    ticket. d-old-2: "Please ask Hyun and reply with his answer"; d-v1-1:
    "have the answer go on #231 or to me". The final text's conditional
    fixed it, 3/3. d-final-2: "please have the answer go on the ticket; I
    resume from there."

  Limit: each subject plays one simulated turn and states what it would
  do. No live seat has read the preamble yet.
  Added from the task review (619308dc): scenario (a2), routine news.
  api-gw merges a change that no peer has to act on now, and the chat
  shows a peer using `@all` for routine news. It is graded separately,
  because (a)'s subjects had passed through `status` or a `<message>`
  without issuing any untagged `say`. Old text: 0/3, all three used
  `@all`, each reasoning "I'm a root with no children, so an untagged
  `say` would reach nobody". Final text: 3/3 used an untagged `say`, with
  no words added: "an untagged say records the news without starting a
  turn in any member. @all or @maws-45 would interrupt sessions for
  nothing."
- Observation: `$SMINOS_HOME`'s root `*.json` files are the seat-record
  namespace, which sminos and the board scripts share, so no other kind
  of file may live there.
  Evidence: in an M4 test run, a root `machine.json` produced `sminos:
  migrated: stamped group on 1 record(s)` and a phantom `fleet` project.
- Observation: a frame's body is the event's whole text, leading tags
  included (`@b hello`).
- Observation: harness registration races the `SessionStart` hooks, so a
  hook can run before `~/.claude/sessions/<pid>.json` exists.
  Evidence: in bundle 2.1.292 (`cli.pretty.js` near line 16028), the
  registration `T8t(...)` is started without an `await` and is followed
  at once by `startSessionStartHooks()`.
- Observation: a headless `claude -p` run registers as a harness session
  with `kind: "interactive"`, and only `entrypoint` sets it apart.
  Evidence: 2026-10-14, harness 2.1.299. A `-p` run in /tmp wrote
  `~/.claude/sessions/<pid>.json` with `kind: "interactive", entrypoint:
  "sdk-cli"`. In the bundle, `kind` is `CLAUDE_CODE_SESSION_KIND`
  (`bg`/`daemon`/`daemon-worker`) or else `"interactive"`.
- Observation: `--session-id <uuid>` works together with `--fork-session`
  and pins the fork's id. `--tools` takes several values and swallows a
  prompt that follows it directly.
  Evidence: 2026-10-14, harness 2.1.299. The fork returned the pinned
  `session_id` and wrote `<uuid>.jsonl`. `claude -p --tools "" "<prompt>"`
  answered "Input must be provided either through stdin or as a prompt
  argument".
- Observation: a live async ask has exactly the transcript shapes
  `ask.tsx` reads. The `tool_use` carries `"async": true`, the
  `tool_result` content is `ASYNC_RESULT`, and the delivery row is a
  plugin prompt (`origin: {"kind": "plugin", "name": "doperpowers"}`)
  framed by the engine. `queue-operation` rows copy the delivery text and
  are not deliveries.
  Evidence: live rows from harness 2.1.296, read by the M3 executor.
- Observation: the hook takes about 110–130 ms a run, also on a 207 MB
  transcript, because it reads only the tail past the position.
- Observation: `migrate` runs before every verb, so any run of a working
  copy's CLI without a temporary `SMINOS_HOME` performs the one-way chat
  import on the operator's real registry.
  Evidence: 2026-10-13, an M1 self-check run of `sminos.py project show`
  without `SMINOS_HOME` renamed the two real `chats/*.jsonl` to
  `.imported` and created `projects/local-doperpowers/`. Restoring them
  was escalated to the human; restored 2026-10-14 on the human's
  approval. Every later dispatch isolates `HOME` and
  `SMINOS_HOME`, and M6's docs say the import is one-way.
- Observation: lifecycle events share a session's writer file with its
  messages, so a member's first message is not `seq` 1, and a seat added
  with `--session` holds `joined` at `seq` 1. M2 rewrote the M1
  assertions that pinned literal seqs to read the file's last seq.
- Observation: the dispatch suites inherit `CLAUDE_CODE_SESSION_ID` from
  the session running them, so through the real CLI `by` names that
  session. That is correct in production: `by` names whoever ran the
  dispatch. The contract tests unset it.
- Observation: a seat record written by board-bind is wider than 0600, so
  the next sminos call prints `migrated: tightened 1 file(s) to 0600`.
  This predates this work.
- Observation: `SMINOS_FAMILY_ONLY=1` (the suite's focused mode) was
  already broken at baseline. M1 fixed it: it now passes 314/314.
- Observation: `git rev-parse --git-common-dir` prints a relative path
  (`../../.git`) when run from a subdirectory. Resolution joins it with
  the directory given to `-C`.

- Observation: a mark written while a session was retired is exported at
  the first `Stop` after its resume: a resume keeps the export position
  (§4) and the hook exports nothing for a non-member. The event's `ts` is
  the export time; the mark's own time stays recoverable through `src`.
  Evidence: the second live pass, 2026-10-14 (acceptance record). Left as
  residue.
- Observation: the xhigh branch review (a sweep, four scalpels, one
  verifier) confirmed 11 findings, every one reproduced in a scratch
  registry, and all were contract edges the common path never crosses: a
  name bound to a session re-read as a seat under the lock; a delivery
  snapshot older than a retire; the export position set after a join that
  can time out; a flush wait satisfied by an earlier identical message; a
  session bound by another project's seat; a legacy chat imported without
  its lock; an install that never creates its own root; a stale git lock
  no tick removes; a rename recovery that strands the unpushed stream;
  view keys made of names. None contradicted the design. The round went
  to one fix wave of two workers split by file.

## Decision Log

- Decision: verification — one independent spec review by a general-purpose
  subagent (astra, per the owner's model preference), the
  `doperpowers:adversarial-reviewer` on the execution section (six
  milestones), and the branch reviewed at `doperpowers:review-code`'s
  xhigh rung at finish: the change rewrites the CLI the board pipeline
  spawns through.
  Rationale: the design rulings (host-less family, siblings, log-first
  delivery, git mirror) were settled in discussion with the human on
  2026-10-12–13 and recorded in the design sections with their
  alternatives; the risk left is buildability and regressions in a
  3,000-line CLI with a 2,500-line test suite.
  Date/Author: 2026-10-13, the authoring session.
- Decision: `@all` stays, as the one address meaning everyone — delivered
  to every live member, no stopped member resumed — carried in the log as
  `wake: true`.
  Rationale: the owner asked for a way to wake the whole project chat; a
  `--wake` flag was the alternative and lost because a tag is in the text
  and a flag is not, so only the tag leaves the record saying which
  messages woke everyone. The first draft had removed `@all` with the host.
  Date/Author: 2026-10-13, the owner and the authoring session.
- Decision: review round one (design: 14 findings; execution: 9) moved the
  document as follows, each change in its section. Addresses are session
  ids resolved at submission, with `#short` and quoted tag forms (§2).
  Membership is an occupancy with `retired` (`replaced`) and re-join (§3).
  Delivery is at-least-once with per-recipient records and the daemon as
  the slow path for local events too (§4). `joined`/`renamed` carry
  `name_source`; `status` is an event; reconciliation joins pre-existing
  sessions on sight (§2, §6). The derive fork is internal (§5). The hook
  exports by position with `src` idempotency and a code-aware parser port
  (§4). `ts` has milliseconds and `seq` is authoritative within a writer
  (§3). Lifecycle verbs are local-only (§2). Attach adopts the existing
  log and works offline (§1). Resolution has a "no project" outcome (§1).
  The in-charge precedence puts an explicit `charge` ahead of a user-set
  name (§5) — the authoring session's call, not the owner's; the acceptance
  as first written could not pass under the old order, and an explicit
  line is more specific than a name. Redaction targets credential-shaped
  values, not `SECRET_RE` (§3). The sync invariant replaces the pull-first
  order (§8). The dispatch scripts gain `--brief` (§6). The two-home test
  isolates `HOME` and runs a `daemon run` process (M4). The skill and
  preamble rewrite is its own behavior milestone with a `writing-skills`
  eval (M5).
  Rationale: the two blockers were real (a durable address on a mutable,
  colliding name; a sync order that fails on the first append), and the
  should-fix findings each named a decision the executor would otherwise
  have made alone. Dismissed: none. Deferred: remote control of a session's process (named
  in §9 as out of scope).
  Date/Author: 2026-10-13, the authoring session.
- Decision: review round two (one blocker, thirteen should-fix) moved:
  delivery settles in writer order with a settled prefix and one pending
  event per writer, a member's record initialised at join, broadcasts
  live-only and never to the sender (§4); reconciliation joins only live
  sessions and never-recorded non-retired seats, so a retirement holds
  (§2); a message has one destination project and mixed tags are refused
  (§2); `src` is record uuid plus span index, exported per record as a
  batch, with a first-use policy (§4); the sync lock covers only the
  working-tree phases and the network phases are bounded (§8); the daemon
  visits every project and syncs only mirrored ones (§8); derivation is a
  child process (§8); the display merge keeps each writer in `seq` order
  (§3); a session's lifecycle has one canonical writer (Terms, §3); attach
  preflights secrets (§1); the duty order pushes last so a published state
  crosses in the same tick (§8); the stub allots distinct uuids across
  homes (M4); acceptance 5 also sets a line on the user-named member.
  Rationale: the blocker was real (a single watermark forgets a failed
  earlier event once a later one lands); the rest were decisions the
  executor would have made alone, each with a failure the reviewer named.  Dismissed: none.
  Date/Author: 2026-10-13, the authoring session.
- Decision: review round three (one blocker, six should-fix) moved: the
  secret scan precedes attach's first commit, so no history carries an
  original (§1); `deliver_next` is the one delivery operation, holding the
  recipient's lock across choose, push, and settle (§4); `@all` carries
  its audience — the members live at submission — so no join cutoff is
  reconstructed and no delivery record is initialised (§4); a `resume`
  keeps the export position (§4); `log_append_batch` and one lock order
  (§4); the integration phase commits intervening appends and integrates
  under one hold (§8); acceptance 6 includes the sender's tick. The
  review loop stops here: three rounds went from 23 findings to 14 to 7,
  the last round's items were clarifications in the design's spirit, and
  the executor resolves what remains the same way (living-spec.md, "A gap
  or a contradiction the spec did not foresee").
  Rationale: the blocker was an ordering hole, not a new mechanism; the
  audience-in-the-event choice was the one semantic the reviewer asked
  the spec to make rather than leave, and it is the simplest of the
  options (no cross-writer time comparison, no initialisation state).  Dismissed: none.
  Date/Author: 2026-10-13, the authoring session.
- Revision: the `question` event (named `need-input` until this line). The `<need-input>` mark was
  retired in doperpowers 7.148.0 (PR #191) and `<insight>` in 7.149.0, so
  `<message>` is the one mark and the others its aliases; an async question
  is now a `tool_use` of `mcp__doperpowers__AskUserQuestion` with `async`
  true (`docs/doperpowers/specs/2026-10-13-ask-async-design.md`). The
  event keeps its name and fields (`text` the questions, `choices` the
  option labels) with `src` the call id, and gains a settlement, `answered`,
  from the delivery row. No decision changed; the source moved under the  spec. Noticed by the ask-async session and relayed to this one.
  Date/Author: 2026-10-13, the authoring session.
- Decision: no redaction anywhere — not at append, not at attach. The
  `redact` interface, the `attach --redact` preflight, and their tests
  leave; §3 says why.
  Rationale: the owner's ruling. A secret never reaches a `<message>` or a
  `say` as plaintext, because the plugin's secrets hook stops an agent from
  reading or printing a stored secret at all; the scanner guarded a case
  that does not arise and would have struck ordinary text. The round-one
  and round-three entries above record the scanner's history.
  Date/Author: 2026-10-13, the owner.
- Decision: the host-bound question event is `question`, not `need-input`:
  the mark it was named after is gone, and the event is a question.
  Date/Author: 2026-10-13, the owner.
- Decision: execution pre-flight (the controller, before M1). Four
  mandated tests name a mechanism a later milestone builds; each is pinned
  in its own milestone through what exists there and re-pinned when the
  mechanism lands. M1's "fast path and a daemon tick run at once" is two
  concurrent `deliver_next` calls for one recipient (the tick calls the
  same operation, §4); M4 repeats it through `daemon tick`. M2's "stays
  retired across repeated `list` and `tick` calls" uses the reading verbs
  in M2 and adds `tick` in M4. M2's "`status` from one home visible from
  the other after a sync" copies the writer's file between the homes'
  `log/` (replication is a copy, §3); M4 repeats it through the mirror.
  M2's "hook `joined` … under a clock stepped back" uses a reconciliation
  `joined` in M2 (same writer, same file) and the hook's once M3 lands.
  `project attach` is built whole in M1 (repository init, first commit,
  remote, fetch tolerated offline), since M1 pins its offline test; M4's
  "attach's mirror half" is the sync that follows it. The milestone text's
  `delivered_record` is the Interfaces section's `delivered_settle` /
  `delivered_fail` pair; the Interfaces section governs. In M1, before
  `Member` exists, a seat record stands in for a member wherever delivery
  needs one; M2 replaces it with `Member`.
  Rationale: each test's intent survives intact at its milestone, and no
  milestone builds ahead of its plan to satisfy a test.
  Date/Author: 2026-10-13, the plan-executor (controller).
  Re-pinned 2026-10-14 (M3, 09775a35): the clock-stepped-back ordering
  test now starts from the hook's real `joined`, sent as a `SessionStart`
  payload through `hooks/smns-record.sh`. The reconciliation stand-in was
  removed. The hook joins through the same `join_on_sight` function, so
  the stand-in proved nothing the real test does not.
- Decision: M1's gaps, resolved by its executor (detail in commit
  7f3f8b9f). `now(ms=True)` only for the log's `ts`: seat records keep
  whole seconds, because the board compares `updated` as strings and the
  dispatch scripts may change only by `--brief`. A seat recorded in a
  directory that is no project belongs to `local-<basename(cwd)>`: §1's
  `spawn --cwd` exception, read off the record. `send` appends before it
  delivers, and its event carries `direct: true` and is never owed: the
  verb delivers it itself, keeping `--wait` and its loud failure (M4
  records a `send` to a remote member without `direct`, so the remote
  daemon owes it). "`settled + 1`" (§4) is the next event in the
  member's owed sequence: an event not addressed to the member settles
  by passing. Legacy writers are never owed. The default `chat` and the
  frame's `unread` count `say` and `human` only (M3's `--host` adds the
  host kinds); cursor mode leaves out the reader's own events and
  advances past the whole log, while `-n` and `--since` leave the cursor
  where it is. The operator's cursor and delivery key is `human`. Tags:
  bare names are `[\w.-]+`, so Korean names work; `#short` matches a hex
  prefix; `@short` must be all eight characters; a match that is retired
  or vacant is refused with a hint. `--team` leaves `say` and `chat` now.
  `project show` exits 4 when there is no project. A malformed `.smns`
  warns and resolution walks on upward. `attach` keeps the lock files out
  through `.git/info/exclude`, commits as `sminos`, and uses the branch
  `main`. The legacy import writes the operator's lines as kind `human`
  (the routing table's kind; §9 says `say`), and leaves alone a chat
  whose host record is gone. The TUI chat panel reads the focused seat's
  project log.
  Rationale: each follows the nearest design decision; none changes a
  ruling.
  Date/Author: 2026-10-13, the M1 executor, folded by the controller.
- Revision: §9's import sentence now says what M1 built. A member's
  lines are imported as `say` and the operator's as `human`; the text
  had said every line was `say`.
  Rationale: the routing table of §4 makes `human` the operator's kind,
  and the design reads as one document only if §9 agrees with it.
  Date/Author: 2026-10-14, the controller, at the authoring session's request.
- Decision: M1's task review moved four things. (1) `send` no longer
  carries a `direct` exemption. Its event is owed and settled through the
  recipient's delivery record like any other, in writer order. The verb
  keeps its immediate push or resume, `--wait`, and its loud failure. A
  push the sender never made, or one that failed, stays owed for the
  daemon. This supersedes the `direct: true` line of the M1 entry above,
  and M4 needs no separate case for a remote recipient. (2) An append
  failure stops the verb before it delivers anything: a delivered message
  must be in the log. (3) The batch's idempotency key is `(kind, src)`,
  not `src`. A `question` and its `answered` share the call id, so `src`
  alone would have dropped every answer (§4 revised). (4) A cursor save
  merges the per-writer maxima with the file under its lock, so
  overlapping reads cannot move a cursor backwards. Also: an operator's
  `send --from X` keeps `from: "human"` in the log and carries `X`
  separately, and `attach` fails clearly when a local git step fails.
  Rationale: (1) and (2) are §4's "delivery is a function of the log"
  applied to the direct verb. The exemption had made a crash between
  append and push lose a message, and it let a send overtake an earlier
  pending event. (3) is a contradiction inside the spec that M3 would
  have hit.
  Date/Author: 2026-10-14, the controller, from the M1 task review.
- Decision: how the fix wave built (1), in commit d08376c1. An earlier
  pending event of the same sender rides in the send's own push (one
  socket write, or one resume), not in a separate push, under ordinary
  delivery's policy for the route taken: a resume leaves out a pending
  `@all` and settles it by passing. A send event
  carries `msg_id`, so a retry reuses the send's frame. A resume settles
  through an `on_launched` callback that fires before any `--wait`; a
  resume that returns no session id counts as uncertain and settles. A
  send that a concurrent deliverer already pushed is not pushed again,
  but its `--wait` still waits on the recorded id and prints the reply
  (fix wave 2, eb6a5ede, reversing wave 1's skip). A session's `send` to
  its own seat exits 2. Lock order for `send`: the seat's lifecycle lock, then
  `delivered/<session>.lock`. A deliverer coming the other way takes the
  lifecycle lock without blocking, so the two orders cannot deadlock.
  Date/Author: 2026-10-14, the M1 executor, folded by the controller.
- Decision: M2's gaps, resolved by its executor (commit 5dd82ba4).
  - Reconciliation never re-joins a session whose seat record is retired,
    even while its process still answers. `retire` stops the process
    asynchronously, and a `list` in that window would undo the retire.
    The seat record is this machine's verdict, and §2 already names
    `fill`, `resume`, and `send` as the ways back. The check repeats
    under the session file's lock, and `retire` writes the record before
    the event.
  - A seat's `group` stays as its alias namespace and lifecycle-lock key
    on this machine, derived from the cwd. `seat add <group> <alias>`
    keeps its positional argument, `group/alias` still addresses a seat
    (banners keep it; the board parses it), and `project/alias` is added
    beside it.
  - A bare name resolves only in the caller's project (the caller seat's
    project, else the cwd's), and across every project only from a
    directory that is no project. CLI targets (`send`, `status`,
    `retire`) do not take a bare eight-character short; tags do.
  - `retire` takes a seat-less member: it stops the session through its
    harness row and records `retired`. `--purge` is refused for one, and
    a remote member is refused as §2 says. `remove` records `retired`.
  - A seat-less member is never resumed. A tag to a stopped one is
    recorded, and `send` to one that is not live exits 4: resuming the
    human's interactive session as a background one would be wrong.
  - `status` set on a remote member goes into the caller's own writer
    file, and the later `ts` wins (§3).
  - Every spawn renders the preamble, filling `{{PROJECT}}`, `{{ALIAS}}`,
    `{{BY}}`, and `{{SMINOS_CLI}}` for M5's text.
  - A seat's brief becomes a `set` in-charge line for every session the
    seat launches.
  - `list` with no argument shows the caller's project, or every project
    from a directory that is no project; `--all` shows every project with
    nothing folded. The chart and the TUI select projects the same way.
  - A remote member with no published state shows `?`.
  - A seat record with no cwd belongs to `local-<group>`.
  - `by` is the caller seat's alias, else its harness name, and `""` for
    the operator.
  - The API lane briefs are `ticket #<n>`, `review ticket #<n>`, and
    `review epic #<n>`, because that lane has no title or PR number in
    hand.
  - `chat` reconciles before it reads.
  Date/Author: 2026-10-14, the M2 executor, folded by the controller.
- Decision: two rulings on M2's concerns (§2, §3 table revised).
  (1) A seat-less local member whose harness session is no longer live is
  retired by reconciliation with `reason` `ended`, and re-joins when it
  is resumed. Folding such members out of `list` was the alternative. It
  lost because a closed session that stays a member keeps its alias
  ambiguous for every later tag, and the §2 clause re-joining a resumed
  session already assumes a closed one is retired. (2) Only a harness
  record of `kind` `interactive` or `bg` joins on sight. The harness
  records `kind` (this machine, 2026-10-14: 21 `interactive`, 1 `bg`), so
  another tool's headless run in the repository does not become a
  member. The internal-fork marker stays for `derive`.
  Date/Author: 2026-10-14, the controller.
- Decision: M2's task review moved the following (fix commits faa23f6c,
  48721e99).
  - `send`, `status`, and `retire` resolve a bare name the way a tag
    resolves. They reconcile first, then match against every member and
    every vacant or retired seat, so a seat and a seat-less session that
    share an alias are refused as ambiguous instead of the seat being
    chosen silently. Matches are de-duplicated by seat id. A seat id, a
    session id, or `group/alias` still names a seat directly.
  - From inside a project, an unresolved bare name is refused, with a
    pointer to `<project>/<name>`. The unrecorded raw harness-name route
    is left only for a directory in no project, and only to sessions in
    no project, which have no log to record into.
  - Membership on sight, and its end (`ended`), follow the process: the
    pid is alive and is the recorded process. Delivery and a seat's state
    word still go by the socket.
  - `status` and the `set` in-charge line take each writer's latest
    event by `seq`, then the latest `ts` across those candidates (§3).
  - Chart and TUI boxes draw §7's facts: state as `list` prints it, the
    in-charge line, `now:` status, and `by`.
  - TUI Enter attaches to a seat-less member when the harness offers a
    non-interactive session for it, and otherwise says why it cannot.
  - A lifecycle append that fails makes `retire` and `remove` exit 1,
    saying the local operation completed and the log write failed: the
    retired seat record blocks repair by reconciliation. A `spawn` or a
    fresh `fill` instead warns loudly and exits 0. Its worker is already
    running, an exit 1 would make execute-dispatch release the run and
    leave the worker unbound, and reconciliation re-joins the seat on the
    next reading verb, without its `by` and its in-charge line.
  - The dispatch suites share one stub harness,
    `tests/issue-tracker/stub-harness/claude`, put on `PATH`.
  Deferred as minor: from a directory in no project, `list` shows a seat
  whose cwd moved after it joined under both projects.
  Date/Author: 2026-10-14, the controller, from the M2 task review.
- Decision: M2 fix wave 2 (0ed8f8fb).
  - Only a full seat or session id, or `group/alias` whose qualifier is
    no known project, names a seat directly. `<project>/<alias>`, by
    project name or id, resolves member-wide like a tag. A qualifier that
    is both a project and a group is read as the project first, and as
    the group only when the project has no match.
  - Once a resume on a `say` fan-out has launched with the frame, the
    delivery is settled and the fan-out continues. A failure to record
    the re-join is then only a warning. A direct `send` still exits 1, but
    only after settling.
  - The spawn warning names only the event that failed and what that
    event carries.
  Date/Author: 2026-10-14, the M2 executor, folded by the controller.
- Decision: M3's gaps, resolved by its executor (09775a35).
  - The hook passes the payload whole to `sminos record` on stdin. The
    shell reads only `cwd`, for the quick exit when there is no project.
  - When the harness record is missing at `SessionStart` (registration
    races the hooks, see Surprises), the hook sets the export position
    but does not join; `Stop` or any reading verb joins later. Polling
    for the record was rejected because it would delay every session's
    start.
  - The hook's membership test is reconciliation's (`joinable`,
    `join_on_sight`): a retired seat is not joined, and both the pid
    marker and `SMNS_INTERNAL` mark an internal fork.
  - Export is one `log_append_batch` per `Stop` over the whole range.
    The position is `{uuid, offset}`, with offset the start of that
    record's line. It advances to the last assistant record whose async
    asks all have their results in the range, so a question is never
    split from the result that accepts it. If the record is not at its
    offset, it is searched for from the end. A position that does not
    hold falls back to the trailing-run policy. The trailing run is
    everything after the last record of type `user`.
  - Sidechain records are never exported: a subagent's marks are not the
    session's message to its human.
  - `answered` is recorded for any delivery, even when its question is
    not in the log, with the engine's plugin-prompt framing cut off. An
    accepted ask is a non-error result whose text is exactly the tool's
    `ASYNC_RESULT`. `choices` is one flat list of labels and `text` the
    list of questions, as the Interfaces section types them.
  - `chat --host` is a view of the last 30 (with `-n`, `--since`, and
    `--json`) and never moves the chat cursor. A shared cursor would
    mark host messages read when a member's `chat` advanced past them.
    `--host --kind` is refused.
  - `charge_source` values: `set`, `derived`, `name` (§5 source 3, since
    the charge names design of 2026-10-21 put it behind `derived`),
    `title` (source 4), or `""`. An empty `set` or `derived` line counts
    as absent, so `charge <m> ""` clears it. `list` and the chart do not
    repeat a user-set name as the line; `--json` and the TUI carry it.
    `charge` with one argument sets the session's own line, with two it
    takes the member and the line, and with more it exits 2. A remote
    member's line goes into the caller's file.
  - `derive`: a member that does not qualify prints "not derived —
    <reason>" and exits 0. `--all` covers every local member of every
    project. The fork starts behind a shell gate, `read` then `exec`, so
    the pid marker is written before `claude` can register. It runs in
    the session's cwd so that `--resume` finds the transcript. A human
    prompt is a `user` record whose `origin` is absent or `human`, and
    which is not meta, not a sidechain, and not a tool result. (Since the
    charge names design of 2026-10-21 the threshold counts the model's
    tool calls instead, and an owner-named member is no longer refused:
    its line is derived and its name left alone.)
    `SMINOS_DERIVE_TIMEOUT` exists for tests. The `ai-title` lookup
    reads only the transcript's last 8 MiB.
  - The mark grammar is its own module, `sminos_marks.py`, checked
    against the mod's 47 parse fixtures.
  Date/Author: 2026-10-14, the M3 executor, folded by the controller.
- Decision: two rulings on M3's concerns.
  (1) A seat-less harness record whose `entrypoint` starts with `sdk`
  never joins on sight, whatever its `kind`, in reconciliation and in
  the hook. Evidence (2026-10-14, harness 2.1.299): a plain `claude -p`
  run registered `~/.claude/sessions/<pid>.json` with `kind:
  "interactive"` and `entrypoint: "sdk-cli"`. The harness writes `kind`
  as `CLAUDE_CODE_SESSION_KIND` or else `interactive`, so the M2 `kind`
  rule alone admitted headless runs.
  (2) `derive` mints the fork's uuid in advance and passes it as
  `--session-id` beside `--fork-session`. It deletes `<uuid>.jsonl`
  whatever the outcome. Evidence: the same harness returned the pinned
  `session_id` and wrote `<uuid>.jsonl`. Before this, a fork that
  crashed without printing JSON left its transcript behind. Also, the
  prompt must follow `--output-format json`: `--tools` takes several
  values, and a prompt placed right after `--tools ""` is swallowed
  ("Input must be provided…").
  As built (7788bd13), `derive` also deletes the transcript of the
  `session_id` the fork reports when it differs from the minted one,
  never the parent's.
  Date/Author: 2026-10-14, the controller.
- Decision: M3's task review moved three things (91b7cfa6).
  - `sminos record` runs under one timer for the whole call,
    `migrate()` included: `SMNS_RECORD_TIMEOUT`, 5 s by default. At the
    deadline it writes a line to `daemon.log` and exits 0, leaving the
    export position where it was, so the next `Stop` retries. The
    hook's "never blocks a turn" (§4) had been false under a held lock:
    the old hook hung for 554 s in the test. No other verb arms the
    timer. A timer was chosen over per-lock deadlines because
    `migrate()` takes its exclusive lock outside the shared helper.
  - `chat --host` applies its window (`-n`, default 30, or `--since`)
    to all host events before grouping. An answer whose question falls
    outside the window is shown in place, with its question as context.
  - `chat --host` reconciles before it reads.
  Revised by fix wave 2 (8136a2e8): the timer bounds only waiting, never
  a migration step. Under the alarm, `_append_board` could be cut off
  between appending posts and deleting their source, and the retry then
  duplicated the posts. `record` now takes migrate's lock with a bounded
  non-blocking retry and exits 0 if the lock is busy. The migration
  steps run with no alarm armed, and the alarm is armed only around the
  export, for whatever time is left. Fix wave 3 (2fc95340) closes the
  remaining gap. On the record path, the deadline also bounds each
  migration step's own lock: `.metalock` through `meta_set`, the
  node-file conversion, and `.sync.lock` for a chat import. A step that
  cannot take its lock is skipped before it mutates anything, logged to
  `daemon.log`, and redone by a later call. Callers that pass no deadline
  block as before.
  Date/Author: 2026-10-14, the controller, from the M3 task review.
- Decision: M4's gaps, resolved by its executor (e4204b38).
  - The daemon's machine-local files are under `$SMINOS_HOME/daemon/`:
    `machine.json`, `state.json`, `run.lock`, `nudge`. §1 and §8 are
    revised. A root `machine.json` was read as a seat record, because
    the root's `*.json` files are the seat records sminos and the board
    scripts glob. `daemon.log` stays at the root.
  - The mirror and the daemon are a sibling module, `sminos_daemon.py`
    (`sync_in`/`sync_out`, `deliver_owed`, `publish_state`). `tick`
    stays in `sminos.py` as a wrapper. Its result dict also carries `to`
    and `error`.
  - Publishing (duty 3) runs only for projects with a remote (§8
    revised). A member's first state is published at once; after that, a
    word must hold for two ticks before it is published, which filters
    flips but does not hold back the first word.
  - A `say` or `send` to a remote member touches `daemon/nudge`, and
    `run` ticks at once. Without the nudge, the worst case for acceptance
    6's two-second bound is two intervals plus git (2.3 s measured);
    with it, 0.8–1.0 s. A file's mtime was chosen over a signal, because
    a stale pid could signal an unrelated process.
  - `project attach` also pushes, so the machine claim crosses at attach.
    A tick pushes only if it integrated, so an unreachable remote costs
    one 30 s bound, not two. Integration merges and never rebases. Git
    runs with `-c commit.gpgsign=false` in its own process group, and a
    timeout kills the group, so a hung ssh child cannot outlive the bound.
  - The tick's views skip the transcript-title fallback.
  - `run` stops on SIGTERM after the tick in hand; the per-project
    handler had swallowed an exit raised mid-tick. The daemon drops
    `CLAUDE_CODE_SESSION_ID` from its environment. `daemon status`
    probes the run lock with a shared lock.
  - `daemon install` writes the plist and prints the `launchctl` lines
    without running them. The plist carries `SMINOS_HOME`, `PATH`,
    `DAEMON_HOST`, and the gateway route, with `KeepAlive` and a
    60-second `ThrottleInterval`. It is modelled on
    `skills/issue-tracker/references/sweep-setup.md`, because the
    `worker-host` §8 names no longer exists in the tree.
  - Test knobs: `SMINOS_GIT_TIMEOUT`, `SMINOS_DERIVE_EVERY`,
    `SMINOS_TRANSCRIPT=1` (prints acceptance 6 as a transcript), and
    the stub's `STUB_COUNTER` and `STUB_FORK_SLEEP`.
  Re-pins: M1's concurrent-delivery test now runs a real `daemon tick`
  beside the sender's fast path. The in-process stand-in is kept, because
  only it fails inside the race itself. M2's stays-retired test now runs
  `daemon tick` between its `list` calls. M2's cross-home `status` test
  now runs through the real mirror, and its file-copy stand-in is
  removed.
  Date/Author: 2026-10-14, the M4 executor, folded by the controller.
- Decision: the launchd plist runs a stable path. When the running CLI
  is under the plugin cache, `daemon install` points the plist at the
  marketplace clone (`installLocation` in
  `~/.claude/plugins/known_marketplaces.json`, auto-updated). A dev
  checkout keeps its own path. `daemon run` exits 0 after a tick once
  its own scripts' mtimes change, so `KeepAlive` restarts it on the new
  code. The plist holds the gateway values in plaintext at mode 0600.
  That is accepted: it is a local operator file, like the harness's own
  settings.
  Rationale: the cache path is versioned, so a plugin update would leave
  the daemon running the old code, or a path that no longer exists.
  Date/Author: 2026-10-14, the controller.
- Revision: only `state` is published just for projects with a remote.
  `renamed` is published for every project the daemon visits (§8
  revised). This narrows the M4 entry above.
  Rationale: a rename is rare and does not grow the log. It is also the
  only record of a name change, because an in-charge line taken from a
  user-set name leaves no `in-charge` row, and a later reader of a local
  project should still see it.
  Date/Author: 2026-10-14, the authoring session, folded by the controller.
- Decision: M4's task review moved three things (e7e55aef).
  - Two-tick persistence keeps the candidate word, in a session → word
    map in `projects/<id>/daemon.json`. A word is published only when
    it equals the previous tick's candidate. Before this, idle → busy →
    waiting published `waiting` after a single tick.
  - One derivation in flight per machine, across processes:
    `$SMINOS_HOME/daemon/derive.lock` is held across the eligibility
    check, the child's start, and the recording of its pid. Any
    process's check sees the live child by that pid. `daemon tick` does
    not take the run lock, so a lock local to one process was not
    enough.
  - `daemon install` run from the plugin cache, with no usable
    marketplace clone, exits 1 before it writes the plist. The message
    says what is missing and how to restore it. A fallback to the cache
    path would have reinstated the failure the stable-path ruling
    removes.
  Date/Author: 2026-10-14, the controller, from the M4 task review.
- Decision: M5's gaps, resolved by its executor (7009154f).
  - The preamble (39 lines) carries one rule §6 did not list. When the
    task names where its questions are answered (a ticket), the answer
    comes back there, and a `say` or `<message>` about the question
    points there. It is keyed to an observable fact, not a ban, and it
    took scenario (d) from 0/2 to 3/3.
  - In (c), the bar is that a bounded task starts no new session.
    Handing it to the member already in charge of that area passes ("to
    the owner"). It starts no session and keeps §2's ruling, so no text
    was added against it.
  - The examples are the spec's own, so a pass is not a copy of a
    scenario's answer. `seat add` is documented as optional. `spawn
    --stamp` and `--no-wait` are left to `--help` as pipeline internals.
  Left for M6: `render_preamble`'s dead `{{GROUP}}`/`{{PARENT}}`
  replacements and its stale docstring.
  Date/Author: 2026-10-14, the M5 executor, folded by the controller.
- Decision: M6. origin/main (7.152.1, 8 commits) was merged into the
  branch (c98ba037), not rebased. Nothing conflicted, and main changed
  neither the mark grammar, its fixtures, nor the three shapes
  `extract_asks` reads. Version 7.153.0. The sminos description went
  into CLAUDE.md's `skills/` row, which had no sminos line before.
  Acceptance ran live in tmux, in real sessions loading this branch with
  `--plugin-dir`, and is recorded in
  `docs/doperpowers/specs/2026-10-13-smns-project-log-acceptance.md`.
  Step 4 ran after step 5, so that `retire a` follows `charge a`. `retire
  a` was run from b, so that a did not stop its own process mid-tool.
  Date/Author: 2026-10-14, the M6 executor, folded by the controller.
- Decision: three defects found by the live acceptance run, fixed in
  38e94907.
  (F1) At `Stop`, `record` polls every 100 ms until the payload's
  `last_assistant_message` is on the transcript past the export
  position. It stops polling at 2 s, or 0.5 s before the record budget
  ends, then exports what it finds; the next `Stop` takes the rest.
  §4's "the row is there when `Stop` fires" was not reliable (see
  Surprises).
  (F2) The retirement holds for the life of the process `retire` saw
  (§2 revised). `retire` records that process's pid, and reconciliation
  and the hook re-join the session only when the harness shows a
  different pid or a later start. The hold applies only to `reason:
  retire`: an `ended` retirement means no process was seen, and holding
  it could lock out a live session after a misread of the sessions
  directory. The CLI prints "<alias>'s session keeps running in its
  terminal; it re-joins when resumed as a new process". Refusing the
  retire was the alternative. It lost because it would make `retire`
  mean one thing for seats and another for sessions, and acceptance 4
  retires an interactive session.
  (F3) `spawn` and a fresh `fill` launch the seat with settings that
  carry `env.SMINOS_HOME`. These are merged with any `--settings` the
  caller passed into one file under `$SMINOS_HOME/settings/`, named by
  its content. The spawner's `SMINOS_HOME` wins. The seat record keeps
  the caller's own settings. A flagless `claude --bg --resume` keeps the
  launch's settings and env (verified live on 2.1.299), so `resume`
  needs nothing more. The board's dispatch scripts launch through
  `sminos spawn` and are covered; their contract test asserts it. A seat
  spawned before this fix has no such settings, and a resume cannot add
  them.
  Date/Author: 2026-10-14, the controller's and the authoring session's
  rulings, built by the M6 executor.
- Decision: a name that binds a session binds it through the verb.
  `alias#short`, and a session id that is not the seat's own id, name a
  session (§2). `send` and `retire` check, under the seat's lifecycle lock,
  that the seat still holds it, and refuse with the reason when a refill put
  another session there. A bare alias or the seat's id names the seat, and
  the verb acts on whatever session the seat holds under the lock, as
  before. `retire` was included because it re-reads the seat under the same
  lock and had the same gap.
  Date/Author: 2026-10-14, the branch-review fix wave (review 1).
- Decision: a seat-less member whose own file shows it retired when an
  event is pushed gets no push, and the event settles as `recorded`. That
  is what a retired seat's owed event already did, and it follows §4: a
  seat-less session is never resumed, and a retired one reads the chat if it
  comes back. The check reads the session's own file at each push, under
  `delivered/<session>.lock`. The deliverer's member may be a snapshot
  taken before the retire, and retiring an interactive session leaves its
  process running (§2).
  Date/Author: 2026-10-14, the branch-review fix wave (review 2).
- Decision: F1's flush wait now matches only the turn's own answer. It
  ends when the transcript's last message, read from its end over
  main-chain user and assistant records, is an assistant message whose text
  blocks read the payload's `last_assistant_message`. A user-role record
  after it (a prompt, a tool result, a peer frame) means the answer is not
  on disk yet. Before this, the wait matched any equal message past the
  export position, so an earlier identical mark ended it while the answer
  was still in the queue. Looking only at the last assistant message would
  not fix that: the earlier mark is the last assistant message until the
  answer lands. The bounds are unchanged: 2 s, and 0.5 s before the record
  budget. A user-type record the harness wrote after the answer would cost
  the full 2 s, and nothing would be lost.
  Date/Author: 2026-10-14, the branch-review fix wave (review 4).
- Decision: in a project's projection, a session is bound by that
  project's own seat (one whose cwd resolves to it) when it has one.
  Reconciliation and the hook use the same rule. The legacy conversion keeps
  one session in seats of several groups, which can belong to different
  projects. A retired seat of another project therefore neither names the
  member, nor gives it its state, nor blocks the member's join on sight.
  When the project holds no seat for the session, the seat holding it
  elsewhere still binds it: a seat whose cwd moved keeps standing for its
  session, one seat one target (`find_target`). Binding only by the
  project's own seats was tried first. It made a moved seat's session a
  seat-less member in its old project, which no reconciliation retires
  while a seat holds it, and turned that seat's name ambiguous.
  Date/Author: 2026-10-14, the branch-review fix wave (review 5).
- Decision: a git lock file in a mirror's `.git` older than the git bound
  (30 s, `SMINOS_GIT_TIMEOUT`) is stale. It is removed at the start of
  each sync operation, under `.sync-op.lock`, with a line in
  `daemon.log`; a younger one is left alone. While `.sync-op.lock` is
  held no git of the daemon's runs in the mirror, so such a lock is left
  by a git killed mid-step: the bound's own kill, or a daemon killed in
  a commit. The cleanup runs before the fetch, not only before the
  commit, because a stale ref lock fails every later fetch and the
  commit is never reached.
  Date/Author: 2026-10-14, the branch-review fix wave.

- Decision: the branch review round. The xhigh panel on c90a0ed8 against
  main (58bd8273) returned 11 confirmed findings, all P2. Each was fixed
  in one wave with a test that fails before its fix: wave A on
  `sminos.py` (4ce9d92f..a6c65050), wave B on the daemon, chart and TUI
  (6935aa97..ed017197, merged at e2879418; its rename carry withdrawn,
  see below); the fixers' own decisions are
  the entries above. The fix range is re-reviewed at the high rung. Left
  for `docs/doperpowers/TECH-DEBT.md`: a `send` to a seat-less member has
  the retire race of review 2 in a shorter window; two seats of one
  project holding one session resolve to the one whose seat id sorts
  last; seat records keep `host` set to the old name after a machine
  rename; the refusal's other recovery (removing `machines/<name>.json`
  from the remote for a registry rebuilt under the same name) still
  conflicts when the rebuilt registry wrote same-named files before
  attaching; the carry adds about four git calls per commit of the
  mirror; a late export carries the export time as `ts`.
  Rationale: every finding was real, reproduced, and small enough to fix
  in place; what was left is bounded and named.
  Date/Author: 2026-10-14, the authoring session.

- Decision: the machine-rename carry (review finding scalpel-1#2) is
  withdrawn. The fix wave's carry rewrote unpushed writer files under the
  new name; the high-rung re-review reproduced four defects in it (a push
  acknowledged remotely but not locally rewritten and deleted; a first
  delivery in flight ignored by its reader exclusion; a crash between the
  file switch and the record migration leaving records that suppress
  another machine's events; carried lifecycle events appended after newer
  ones, undoing a retirement). The refusal now states the two recoveries
  that hold, and the collision goes to `docs/doperpowers/TECH-DEBT.md`. The
  durable fix is naming writer files by the machine's instance id rather
  than its name (§3), a design change for its own initiative. Rationale: a
  recovery that can lose or reorder events is worse than a stranded
  pre-attach stream reported honestly; two machines with one name is rare
  in the owner's fleet.
  Date/Author: 2026-10-14, the authoring session, from the high-rung re-review.

- Decision: a session's title is published, as its own kind `titled` in
  the session's file, and is the harness's "Session name" (`custom-title`,
  else `ai-title`), not the `ai-title` alone (§3, §5, §8). This reverses
  §5's "a remote view lacks it": the owner, working from the desk, could
  not tell sessions apart by alias and machine ("maws-4d @macbook" is the
  session they call "cua_repl"), and the desk's sidebar draws ended
  sessions and offline machines' from the log, which session presence
  cannot serve. "It changes every turn" was the record, not the value: the
  harness re-appends it, and only a change is published. A kind of its own
  rather than a field on `renamed` (which an older reader takes the alias
  from) or an `in-charge` with a new source (which the desk's projection
  draws as the in-charge line, whatever its source): every older reader,
  sminos's projection and the desk's, passes over a kind it does not know,
  and the hub verifies any kind.
  Date/Author: 2026-10-17, the desk's session-title change.

- Decision: a session sent to the background is the member it was (§2,
  Hand-off), linked by the harness's own `continued-in` record and carried
  in the log as a `retired` with `reason` `continued` and `to`; and a name
  the harness made up never replaces an alias the log holds. The owner saw
  a session's alias and socket change on every `/background` (MAWS,
  2026-10-17: `maws-fe` became "GUI AI agent workspace charter", a new
  session, and the old one was retired `ended`), and a resume rename a
  member (`maws-4d` → `maws-3f`, same session). Rejected: a member id
  apart from the session id, which would re-key every record sminos and
  the desk keep per session for a case the projection can fold; and a
  stable socket path per member, which would let one endpoint answer for
  two processes while both run. A retirement, not a new kind,
  so an older reader (the desk's projection) reads the old session as
  retired and the job as a member of its own, which is what it reads now.
  The desk folding the two is MAWS's follow-up.
  Date/Author: 2026-10-17, the hand-off change.

- Decision: a session its host marks as a member joins as a terminal
  session does, though its entrypoint is `sdk-*` (§2). The mark is
  `SMNS_MEMBER` in the engine's environment, naming the pid that spawned
  the engine (MAWS sets its own on every engine it launches), and it holds
  only while that pid is the engine's parent (`ps -o ppid=` of the record's
  pid). It is read only inside the session's own process tree: the hook
  and the bridge's child admit the session they run for, and a verb the
  session's tools run admits the one `CLAUDE_CODE_SESSION_ID` names. The
  owner chose the shape on 2026-10-18 (MAWS marks the sessions it launches,
  sminos admits a session carrying the mark, its own forks stay out): MAWS
  launches every engine with `CLAUDE_CODE_ENTRYPOINT=sdk-ts`, so nothing
  its sessions sent their human reached the log or the desk, and the
  reading of MAWS's ask (board #76) had no effect.
  Why the environment, and why the daemon never reads it: the harness
  record holds no environment, and the record fields a launcher could set
  through it are the engine's own (`entrypoint` is MAWS's probe identity,
  every one of its fixtures recorded under it). So the session joins
  itself, at its SessionStart hook (a `-p` engine's record is written by
  then) or at its bridge's first export, and reconciliation elsewhere only
  retires it `ended` once its process is gone, as it does any member; a
  resume re-joins it at its next SessionStart.
  Why the launcher's pid: a plain flag leaked. A run started from inside a
  marked session (a tool's `claude -p`, an agent SDK fan-out) inherits the
  variable, and the engine's child-session marker does not stop it
  registering a record, so its own hook joined it (e2e, below). The
  launch's session id was ruled out because MAWS clears a session inside
  its running engine (`/clear`, its `session-clear.ts`), which goes on
  under a new id. The spawner's pid binds the mark to the engine process
  itself: a `/clear` keeps the process and its parent, and an inherited
  copy names a process that is not the nested engine's parent. A launcher
  that wraps the engine's spawn (a shell, a process wrapper) would have to
  name the wrapper.
  Evidence (2026-10-18, harness 2.1.302, Agent SDK 0.3.259, the working
  copy installed as the temp HOME's plugin and loaded through MAWS's setting
  sources, under a temp HOME and SMINOS_HOME): the marked
  session (the mark the driver's pid, the engine's parent) was listed by
  `sminos list` from outside it after its first turn; its writer file
  holds `joined`, its `message`, the `question` of its `mcp__maws__ask`
  (blocking false) and the `answered` of the `[MAWS ask <id>]` steer, both
  under the call id, then `retired` `ended` once it exited. `sminos derive`
  run with its mark and session id inherited answered, and its internal
  fork wrote nothing. An unmarked sdk-ts session, one with `SMNS_INTERNAL`,
  and one standing for a nested run (the mark naming another pid, with
  `CLAUDECODE` and `CLAUDE_CODE_CHILD_SESSION` set: it registered a record,
  `kind` interactive, `entrypoint` sdk-ts) wrote no writer file and were
  never listed; with the plain flag, that nested run had joined. The
  bridge's socket answered in every session but the internal fork's, with
  or without `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` in the settings' env.
  Date/Author: 2026-10-18, the MAWS-member change.

## Outcomes & Retrospective

2026-10-14, at the end of execution and before the branch review.

**What shipped.** Everything §1–§8 promise, as revised by the Decision
Log, is built and passes:
- a project identified by a committed `.smns`;
- the per-writer append-only log, with in-order delivery for every
  sending path;
- the host-less family, with membership derived and reconciled on sight
  and ending with the process;
- the hook that turns `<message>` marks and async asks into host events,
  bounded so it never holds a turn;
- the in-charge line, with `charge` and a `derive` that leaves no trace;
- the git mirror and a per-machine daemon, with a stable launchd install;
- the skill and the preamble, rewritten and evaluated.

The dispatch scripts changed only by `--brief`. The sminos suite went
from 860 assertions to 1485. Both dispatch suites gained a contract test
that runs the real CLI. Version 7.153.0.

**Against the purpose.** The acceptance was run live in real interactive
sessions, not only on the stub. Steps 1–5 passed in tmux-driven
sessions that loaded this branch. The two-home daemon delivered 40 timed
messages, the slowest in 1.53 s, each exactly once (step 6 on the stub
harness, since a temporary HOME cannot authenticate a real `claude`).
The live run was the first time a session read the new preamble, and it
found three defects the stub could not show: the Stop/flush race (F1),
a retire that reconciliation undid (F2), and a seat that did not
inherit `SMINOS_HOME` (F3). All three are fixed and pinned by tests.
A second live pass on 2026-10-14 confirmed all three on the real
harness: 12 of 12 marks exported on their own Stop, a retire that held
across lists, a tick and the session's own Stop, and a spawned seat that
wrote only its spawner's registry.

**What the reviews moved.** Every milestone needed at least one fix
wave. The recurring theme was a contract that held in the common path
and broke at an edge:
- delivery order across the direct verb and the fan-out;
- the hook's promise never to block a turn, which took three waves to
  reach every lock it waits on;
- name resolution that silently preferred a seat;
- two-tick persistence that forgot its candidate word.

Only the controller's reviewers saw these; the design's three rounds of
spec review could not have. The design survived intact: no owner ruling
was reopened. The changes were revisions the design's intent settled,
each logged.

**The branch review.** The xhigh panel confirmed 11 findings on the
finished branch, all reproduced, all contract edges, none against the
design; one fix wave of two workers closed them with 61 new assertions,
and the fix range got its own review at the high rung.

**Lessons.**
- A dev run without an isolated `SMINOS_HOME` rewrote the operator's
  real registry in M1. The same failure reappeared at the spawn boundary
  in M6 (F3). A tool whose first run migrates state should make its
  home explicit at every process boundary it creates, not only at its
  own entry.
- Probing the real harness for a few seconds settled questions a
  bundle read left open: whether `-p` runs register (they do, as
  `interactive`), whether `--session-id` pins a fork, and whether
  `--tools` swallows a prompt.
- M5's eval showed that half the target behaviors already held on the
  old text, and that the one new rule the preamble needed was not in
  §6's list. It came from a failure the eval exposed (scenario d).

**Left behind.**
- The async questions of a MAWS session (§9). MAWS sessions are the ones
  most affected.
- A seat whose cwd moved after it joined is listed under both projects
  by a `list` run from a directory in no project.
- Seats spawned before F3 carry no `SMINOS_HOME` in their settings, and a
  resume cannot add it.
- The `~/.claude.json` trust entry that the acceptance run's trust
  dialog added for `/private/tmp/smns-acc/R` is the human's to remove.
- A late export (a mark written while retired, or one a Stop missed)
  carries the export time as `ts`; the mark's own time is in `src`.
- After a machine rename, seat records keep the old `host`; the
  rebuilt-registry recovery still conflicts; a `send` to a seat-less
  member keeps a short retire race. All in `docs/doperpowers/TECH-DEBT.md`.
