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
and wakes no one. A `<message>…</message>` the first session writes appears
in `sminos chat --host` attributed to it. With a remote in `.smns` and the
daemon running on two machines, the same `say "@<other>"` crosses machines.

## Progress

- [ ] M1 — Project identity and the log
- [ ] M2 — The project family
- [ ] M3 — Messages to the host and the in-charge line
- [ ] M4 — The mirror and the daemon
- [ ] M5 — Docs, acceptance, version

## Terms

- **Project** — the unit of shared work state. Identified by a `.smns` file
  (below); a directory tree without one is a *local project*, named as
  `derive_group` in `skills/sminos/scripts/sminos.py` names groups today
  (the owning repository of a worktree, else the directory's basename).
- **`.smns`** — a committed JSON file at a repository's root:
  `{"project": "<uuid>", "name": "<display name>", "remote": "<git url or empty>"}`.
  Several repositories carrying the same `project` id are one project.
- **Member** — a session that belongs to a project: every harness session
  whose working directory resolves to the project, every sminos seat whose
  `cwd` does, and every session the log says joined and has not retired.
  Derived, never declared.
- **Alias** — a member's one name: the harness's session name (what
  `~/.claude/sessions/<pid>.json` records as `name`, what the human sets with
  `/rename`, what a seat is spawned as). Unchanged from the one-name design
  (`docs/doperpowers/specs/2026-09-29-sminos-one-name-one-state-design.md`).
- **Host** — the project's humans, and any agent reading on their behalf
  (the chief-of-staff agent is deferred, §9). Not a seat. `human` stays the
  operator's identity as today.
- **Writer** — one appender of the log: `<machine>/<session-uuid>` for a
  session, `<machine>/human` for the operator on that machine,
  `<machine>/daemon` for its daemon, `legacy/<host-seat-id>` for imported
  family chats. `<machine>` is `host_name()` in sminos.py.
- **Event** — one JSON line in a writer's file (§3).
- **Log** — all writers' files of one project, under
  `$SMINOS_HOME/projects/<project-id>/log/`. When the project has a remote,
  that directory is a git working tree of it (the **mirror**).
- **Projection** — what reading the log plus local liveness yields: members,
  their state, in-charge line, provenance, and the chat. Computed on read.
- **Daemon** — `sminos daemon`, one process per machine: syncs mirrors,
  delivers remote events to local members, publishes local state changes.
  Needed only for projects with a remote.
- **Frame** — the text pushed into a session's inbox socket, as today:
  first line `[sminos chat …]`, then the message.

## 1. The project and its identity

`sminos project init [--name N] [--remote URL]` writes `.smns` at the
repository root of the working directory with a fresh uuid; `sminos project
show` prints the resolved project for a directory. Resolution walks up from
the working directory to the first `.smns`; a linked worktree under
`.claude/worktrees/<name>` carries the file by checkout, so the main checkout
and its worktrees resolve to the same id. With no `.smns`, the project is
the local project `derive_group(cwd)` names, with id `local-<name>`.

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
        <machine>.human.jsonl
        <machine>.daemon.jsonl
        legacy.<host-seat-id>.jsonl
      cursors/<session-uuid>.json     what a reader has read: {"<writer>": <seq>}   (local only)
      delivered/<writer>.json          what the daemon has delivered from a remote writer   (local only)
## 2. The family is the project

A member sees its whole project with `sminos list`, and commands naming a
seat resolve inside the working directory's project first, then
`<project-name>/<alias>` reaches another project known locally. From a
directory that is no project — the operator's terminal in a home directory —
a name resolves across every project known locally, an ambiguity reported
as today. The former
reach rule (a family seat sees only parent, siblings, children) leaves, and
with it the preamble's "someone outside your family is reachable only
through the native tools" clause: the project is the reach.

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

## 3. The log

One file per writer, append-only, each line one event:

```json
{"ts": "2026-10-13T08:01:02.123Z", "writer": "SK.local/e0ad139c-18bc-45bd-9489-be8653145f80", "seq": 42,
 "kind": "say", "from": "doperpowers-1e", "to": ["maws-45"], "text": "your change renames a column I read"}
```

`seq` is per writer, starting at 1, assigned under a per-file `flock`
(several processes on one machine write one session's file: its own `sminos
say` from the Bash tool, and the hook of §4). Total order for reading is
`(ts, writer, seq)`: exact within a writer, approximate across machines,
whose clocks may differ by seconds; nothing in this design depends on
cross-machine order beyond display. One file per writer is what makes the
mirror trivial (§8): a file has one writer, so replication is a copy and a
merge conflict cannot occur. The alternative, one file per project with a
global id, needs a lock or a server to assign ids and was rejected for that.

The kinds, and the fields each carries beyond `ts`, `writer`, `seq`:

| kind | fields | written by |
| --- | --- | --- |
| `say` | `from` alias, `to` `"*"` or a list of aliases, `text` | `sminos say` |
| `human` | `from` `"human"`, `to` `"*"` or a list, `text` | operator `say` / `send` |
| `message` | `from` alias, `to` `"host"`, `text` | the hook, from a `<message>` mark (`<to-human>`, `<essential>` read as aliases) |
| `need-input` | `from` alias, `to` `"host"`, `text`, `choices` list of strings | the hook, from a `<need-input>` mark |
| `joined` | `session` uuid, `alias`, `machine`, `cwd`, `worktree`, `role`, `by` alias or `""` | `sminos spawn` (with `by`), the hook on session start (`by` `""`), `seat add` |
| `in-charge` | `session`, `text`, `source` `set` or `derived` | `sminos charge`, `spawn --brief`, `sminos derive` |
| `status` | `session`, `text` | `sminos status` |
| `renamed` | `session`, `alias` | the daemon, on a harness name change |
| `state` | `session`, `state` word, `machine` | the daemon, on a liveness transition (§8) |
| `retired` | `session`, `by` | `sminos retire` |

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
record (`delivered/`, §8), not the message's.

**Secrets.** For a project with a remote, `say` and the hook replace any
line of a text matching `SECRET_RE` in sminos.py with `[redacted]` and
print a warning: a mirrored log leaves the machine. A local project is
unaffected.

## 4. Speaking

`say` keeps its shape — `sminos say "<text with @tags>"`; tags address only
at the start — and its routing becomes the project's:

| sender | tags | recorded as | pushed to | starts a turn in an idle member | resumes a stopped member |
| --- | --- | --- | --- | --- | --- |
| member | none | `say` to `*` | nobody | no | no |
| member | `@a @b` | `say` to `[a, b]` | a and b | yes | yes |
| operator | none (`--in <project>` or the cwd's) | `human` to `*` | nobody | no | no |
| operator | `@a` | `human` to `[a]` | a | yes | yes |

An untagged message is a record: a member reads it at its next wake, when
its preamble has it read the chat, or when it chooses to. Only an address
pushes. The alternative, pushing untagged messages to every live member,
was rejected on cost: a project with six idle sessions would start six
turns, each loading its context, for one line of status. `@all` leaves
with the host; a member that wants everyone woken tags them.

`sminos send <alias> "…"` stays the direct verb to one seat and is recorded
as `human` (operator) or `say` (member) to `[alias]`; it reaches a live
local member over its socket and resumes a stopped one, exactly as today.
A member on another machine is reached by recording alone: that machine's
daemon delivers (§8). So delivery is a function of the log everywhere, and
the local push is the shortcut for the common case.

**Messages to the host.** A new shell hook, `hooks/smns-record.sh`,
registered in `hooks/hooks.json` on `Stop` and on `SessionStart` (matcher
`startup|resume|clear|fork`), calls `sminos record` with the payload's
`session_id`, `cwd`, and `transcript_path`. On `Stop` it reads the
assistant records of the turn that just ended (those after the last human
prompt — a `user` record whose content is text, not a tool result), extracts
every `<message>`, `<to-human>`, `<essential>` span as a `message` event and
every `<need-input>` span as a `need-input` event with its `<choice>` lines
lifted into `choices` (the same lifting `hooks/mods/to-human.tsx` does for
display), and appends them to the session's writer file. On `SessionStart`
it appends `joined` with `by` `""` unless the local log already has a
`joined` for that session id. A directory that resolves to no git
repository and no `.smns` is not a project, and the hook exits without
writing. `sminos chat --host` prints `message` and `need-input` events; it
is the human's view of what every session sent them.

The output style itself does not change. Its first sentence, "The human does
not watch this session", stays as written: it is what keeps the working
record and the message apart, and a message that is also logged is still a
message.

## 5. The in-charge line

Every member has one line saying what it is in charge of, shown by `list`
beside its state. Sources, in order; the first present wins:

1. The harness name, when the human set it (`nameSource` is `user` in the
   session's record): "현우진", "interactive learning".
2. The latest `in-charge` event with `source` `set`: `sminos charge
   [<alias>] "one line"` from the session or the operator, or `spawn
   --brief`.
3. The latest `in-charge` event with `source` `derived` (below).
4. The latest `ai-title` record in the session's transcript — the harness
   rewrites it as the conversation moves, so it is the current topic, not
   the responsibility: the "interactive learning" session's latest title
   read "구글 테이크아웃 Gemini 대화 기록". A fallback, never preferred.
5. Empty.

`sminos derive [<alias> | --all]` asks a session what it is in charge of
without interrupting it, by forking it headless:

    claude -p --resume <session-uuid> --fork-session --tools "" --output-format json \
      "In one line: what is this session in charge of in this project — its standing responsibility, not its latest step? Answer with the line only."

Verified 2026-10-13 on a live transcript (Surprises & Discoveries): the fork
answers from the session's context, with no tools, and leaves a copy of the
parent transcript as a new session file, which `derive` deletes after
reading the answer (`transcript_path()` in sminos.py locates it). The
answer is the `result` field of the last JSON object on stdout, stripped of
marks, first line, at most 120 characters. `derive` runs only for a local
member with no source 1–2 line, at least 10 human prompts in its
transcript, and no `derived` event in the last six hours; `--all` applies
that to every local member. The daemon runs `derive --all` hourly (§8). The
cost is one model call that reads the parent's prompt cache when the
session was active within the cache's hour, and rebuilds it otherwise.

## 6. Spawning siblings; retiring

`sminos spawn <alias> "<task>" [--role R] [--brief B] [--cwd DIR]
[--worktree NAME] [--model M] [--settings FILE] [--effort E] [--wait]`
from a member or the operator starts a session in the working directory's
project (or `--cwd`'s). `--group` and `--parent` leave: the project is the
group and there is no parent. The spawn records `joined` with `by` the
spawner's alias (`""` from the operator) and, with `--brief`, an `in-charge`
of source `set`. `list` shows the provenance as a dim `by <alias>` suffix;
the chart draws no tree.

Every spawn renders `references/spawn-preamble.md`, rewritten for the
project family: who the seat is and in which project; read the chat first;
untagged is recorded, `@alias` pushes; `<message>` is how it reaches the
host; `sminos status` and `sminos charge`; spawn a sibling only for a
separable standing responsibility, a subagent for anything else. The board
pipeline's workers are spawned by `skills/issue-tracker/scripts/
execute-dispatch.sh` and `review-dispatch.sh` without `--group` today and
keep spawning the same way; their bootstraps are their protocol, and the
project preamble ahead of it is true for them too (their in-charge line is
their ticket, from the dispatcher's `--brief`).

`sminos retire <seat> [--purge]` stops one seat and records `retired`;
`--cascade` leaves with the tree. `fill`, `resume`, `reply`, `attach`,
`status`, `meta`, `sync` are unchanged in shape.

## 7. Views

`sminos list [<project>] [--all] [--state W] [--json]` prints one heading
per project (the working directory's by default; `--all` every project
known locally), newest member first:

    MAWS
      maws-fe     idle                GUI AI agent workspace: main app architect
      cua_repl    busy                cua_repl browser and GUI tool          · now: fixture 8/8
      maws-45     waiting             owner artifacts page                   · by maws-fe
      현우진       idle  @mini 3m      뉴런 교재 기반 문제 작성자 스킬

Columns: alias, state word (for a member on another machine, `@<machine>`
and the age of its last `state` event), the in-charge line, then `· now:`
the `status` line when set and `· by <alias>` the provenance. Seat-less
interactive sessions appear like any seat. `--json` carries every member
with `session`, `machine`, `state`, `charge`, `charge_source`, `by`,
`status`, `worktree`. `chart` and `tui` draw the same rows grouped by
project, flat; `tui`'s `b` opens the project chat, and `Enter` attaches to
a local member as today. The chart's tree layout leaves with the tree.

`sminos chat [<project>] [-n N] [--since TS] [--host] [--kind K] [--json]`
reads the merged log (§3); the member-facing frame becomes
`[sminos chat <project-name> from <alias> → @you | unread N]`.

## 8. The mirror and the daemon

A project whose `.smns` names a remote has its `log/` as a clone of that
remote, made on first resolution (`sminos project attach` does it
explicitly). The remote is any git URL the machine can push to over SSH; a
bare repository on a machine the project's machines reach (the Tailscale
host, the Hetzner box) avoids any hosted API's limits, and GitHub works
too. Each machine writes only files named with its own machine name, so
`git pull --rebase` never conflicts. Two machines with the same host name
would: `$SMINOS_HOME/machine.json` holds a random instance id, written on
first use, and at attach the machine pushes it as
`log/machines/<machine>.json`; a daemon that finds its name claimed by
another instance id refuses to run and says so.

`sminos daemon run [--interval 5]` loops over every local project with a
remote; `sminos daemon install` writes a launchd agent
(`~/Library/LaunchAgents/com.doperpowers.sminos-daemon.plist`, modelled on
`application-agents/triaging-feedback/infra/worker-host`) that runs it;
`sminos daemon status` prints the last tick per project. Each tick:

1. **Sync.** `git pull --rebase -q`; if the working tree changed locally,
   `git add -A && git commit -qm "sync <machine> <ts>" && git push -q`,
   retrying a rejected push with another pull up to three times.
2. **Deliver.** For each event from a writer on another machine, above the
   `delivered/<writer>.json` watermark, whose `to` names a local member:
   push a frame or resume, exactly as a local `say` would (§4); then advance
   the watermark. An event to a member that is `gone` or `retired` here is
   skipped and the watermark advanced.
3. **Publish.** For each local member, compute `state()` as today; when it
   differs from the last `state` published for that session and differed on
   the previous tick too, append `state` (one tick of persistence drops the
   flip inside a tool round). When the harness name differs from the last
   known alias, append `renamed`.
4. **Derive.** Once an hour, `derive --all` (§5).

A local project has no daemon and no mirror; everything above is the
in-process path. The alternative transport, a small server with push
notifications, was rejected for now: git gives replication, history, SSH
authentication, and offline operation for free, and a five-second poll is
inside what agent-to-agent messaging tolerates. Nothing here forecloses a
server later: the daemon's three duties are the same against any mirror.

The Cursor cloud-agent write-up (cursor.com, "cloud agent lessons") is the
nearest prior art: they decoupled the conversation state from the machine
running the agent into an append-only store streamed to clients. This log
is that layer for a project; the agent loop stays the Claude Code process,
which is why Temporal, their choice for the loop, has no place here.

## 9. What leaves, what stays, what this is not

Leaves: the host and family reach (`family_of`, `reach_of`,
`is_family_seat`, `--team`, `@all`, `--parent`, `--group`, `retire
--cascade`), the per-host chat files under `chats/` and their in-place
`delivered` maps, `chat_seen` on seat records, the `groups/` directory. `sminos
migrate` imports each `chats/<host-seat-id>.jsonl` into the project of the
host's `cwd` as `say` events under writer `legacy/<host-seat-id>`,
preserving `ts`, `from`, and tags as `to`; existing seat records keep
working, their project resolved from `cwd`.

Stays: seat records and their locks under `$SMINOS_HOME` (machine-local
operational state: `current`, `short`, `gen`, worktree, settings, effort,
the reply cache); `state()` and the seven state words; `spawn`'s launch
path and gateway-route scrubbing; `send --wait`; `fill`, `resume`, `reply`,
`attach`; the board pipeline's dispatch scripts and bootstraps, untouched.
The log is the source of truth for everything two machines could disagree
about; what only this machine needs stays in its own files.

Not here: the chief-of-staff agent (a reader of the log on the human's
behalf; whether a resident session or a per-event routine is decided when
the log is in use), inbound Slack or mail, a human seat, any change to the
board loop or to `decomposing`.

## Acceptance

Run from a scratch repository `R` with `sminos project init --name demo`
committed, `SMINOS_HOME` pointed at a temporary directory, and two
interactive sessions `a` and `b` opened in `R` (named with `/rename a` and
`/rename b`), unless a step says otherwise.

1. `sminos list` in `R` prints a `demo` heading with rows `a` and `b`, each
   with a state word, no `seat add` having been run.
2. In `a`: `sminos say "merged #12"`. `b`, idle, starts no turn; `sminos
   chat` in `b` prints the line attributed to `a`. In `a`: `sminos say "@b
   look at X"`. `b` starts a turn whose first content is a
   `[sminos chat demo from a → @you …]` frame carrying `look at X`.
3. `a` writes `<message>done with the parser</message>` in a turn. After the
   turn, `sminos chat --host` prints `a: done with the parser`.
4. In `a`: `sminos spawn c "wait for instructions"`. `list` shows `c` with
   `· by a`. `sminos retire a` leaves `c` live in `list`.
5. `sminos charge b "owns the GUI tool"`; `list` shows that line for `b`.
   For a session with ≥10 prompts, a derived name, and no line, `sminos
   derive <alias>` prints a one-line answer, `list` shows it with
   `charge_source` `derived` in `--json`, and the project's transcript
   directory holds the same number of files before and after (the fork's
   was deleted).
6. With two `SMINOS_HOME`s on one machine, `DAEMON_HOST=h1` and `h2`, a
   local bare repository as `.smns`'s remote, and `sminos daemon run` under
   each: `sminos say "@b hello"` from `a` (joined under h1) is pushed to
   `b`'s socket (joined under h2) within two intervals, and `sminos list`
   under h1 shows `b` with `@h2` and its state.
7. `tests/sminos/run-sminos-tests.sh` passes, and so does
   `tests/issue-tracker/test-execute-dispatch.sh` and
   `tests/issue-tracker/test-review-dispatch.sh` (the dispatch scripts
   spawn through the same CLI).

## Execution

Constraints binding every milestone: Python 3 standard library only in
`sminos.py`, as today; no new daemon framework; the stub-`claude` harness in
`tests/sminos/run-sminos-tests.sh` is the test substrate, extended, not
replaced; every verb keeps its exit codes (`EXIT_USAGE`, `EXIT_UNKNOWN`);
`$SMINOS_HOME` and `DAEMON_HOST` remain the overrides tests use; nothing
under `skills/issue-tracker/scripts/` changes except where a removed flag
would break it (none is used there). The spec is executed as one spec by a
`doperpowers:plan-executor`: five milestones in one CLI, one hook, and one
skill document.

### M1 — Project identity and the log

What exists at its end: `sminos project init|show|attach`; resolution of a
directory to a project; the `projects/<id>/` layout; `log_append` and
`log_read` with per-writer `seq` under a file lock and `(ts, writer, seq)`
merge; `say`, `send`, and `chat` writing and reading the project log with
the routing table of §4 and the cursor semantics of §3; `migrate` importing
`chats/`. Touches `skills/sminos/scripts/sminos.py` (`derive_group` becomes
the fallback of `resolve_project`; `chat_*`, `seen_advance`, `unread_for`,
`compose_chat_frame`, `push_member`, `cmd_say`, `cmd_chat`, `send_to_seat`,
`migrate`), `tests/sminos/run-sminos-tests.sh`. Interfaces: produces
`Project`, `resolve_project`, `log_append`, `log_read`, `cursor_load`, `cursor_save`,
`redact` (Interfaces and Dependencies). Decisions here: the writer file name
replaces `/` in the writer id with `.`; `seq` is read as the last line's
`seq` plus one under `flock` on `<file>.lock`; a malformed line is skipped
on read and never rewritten; `--in <project>` on the operator's `say`
accepts a project name or id; the frame drops the message id; an address in `say` resolves, in this
milestone, among seat records whose `cwd` resolves to the project, and M2
extends it to seat-less members. Does not touch: membership (`list` still prints today's groups until M2), the hook,
the daemon. Proves: acceptance 2 (local push half), the merge order and
cursor behaviour pinned by tests: two writers' lines interleave by `ts`;
`chat` advances the cursor and `-n` does not; a `say` to `*` pushes nothing.

### M2 — The project family

What exists at its end: members derived from harness sessions, seat records,
and `joined` events; `list`, `chart`, `tui` flat per project with the
columns of §7; reach is the project; `spawn` without `--group`/`--parent`,
recording `joined` with `by` and `in-charge` from `--brief`; `retire`
without `--cascade` recording `retired`; the rewritten
`references/spawn-preamble.md`; `seat add` recording `joined`. Touches
`sminos.py` (`seats`, `find_seat`, `resolve_seat`, `caller_seat`,
`cmd_list`, `cmd_spawn`, `spawn_fresh`, `render_preamble`, `cmd_retire`,
`cmd_seat_add`, the removal of `family_of`/`reach_of`/`is_family_seat`),
`sminos_chart.py`, `sminos_tui.py`, `references/spawn-preamble.md`, tests.
Interfaces: produces `members`, `Member`; consumes `resolve_project`,
`log_read`, `log_append`. Decisions: a harness session without a seat record
is a member with alias = harness name and `session` = its id, and `send`
to it uses its socket like a seat's; a member's `by` is the first non-empty
`by` among its `joined` events (the hook's `joined` carries `""`, the
spawn's carries the spawner, whichever lands first); `list` sorts by join
time, newest first; a retired member hides as today. Does not touch: the
hook, `charge`/`derive`, the daemon. Proves: acceptance 1, 4; tests pin
that a seat-less harness session in the project's cwd lists, that
`spawn --parent` is refused as unknown, that retiring a spawner leaves the
spawned seat live.

### M3 — Messages to the host and the in-charge line

What exists at its end: `hooks/smns-record.sh` on `Stop` and
`SessionStart`, `sminos record`, `chat --host`; `sminos charge`; `sminos
derive` with the precedence of §5 and the fork mechanism, including the
fork transcript's deletion; `list` showing the in-charge line and its
source. Touches `hooks/hooks.json`, `hooks/smns-record.sh` (new),
`sminos.py` (`cmd_record`, `cmd_charge`, `cmd_derive`, `charge_of`),
tests (a fixture transcript with marks; the stub `claude` gains `-p
--resume --fork-session`, printing a JSON with `result` and `session_id`
and creating the fork's transcript file). Interfaces: produces `charge_of`,
`extract_marks`; consumes `members`, `log_append`. Decisions: the hook is
`set -uo pipefail`, exits 0 on every error so a logging failure never
blocks a turn, and reads the payload once with `read -r` as
`to-human-stream.sh` does; mark extraction is one regex over the
concatenated text blocks of the turn's assistant records, nested or
unclosed marks taken to the end of the text, matching `to-human.tsx`'s
`TAG`; the transcript is read from its end back to the last human prompt,
never whole (an architect session's file reaches 155MB); `derive`'s fork runs with a 120-second timeout and a failure prints
the stderr tail and writes nothing. Does not touch: the daemon; the output
style. Proves: acceptance 3, 5; tests pin that a `<to-human>` span records
as `message`, that `need-input` choices are lifted, that a user-named
session is never derived, and that the fork's file is deleted.

### M4 — The mirror and the daemon

What exists at its end: `project attach` cloning a remote into `log/`;
`machine.json` and the instance-id claim; `sminos daemon run|install|status`
with the four duties of §8; `delivered/` watermarks; `state` and `renamed`
publication; remote members in `list` with `@<machine>` and age. Touches
`sminos.py` (`cmd_project`, `cmd_daemon`, `sync_mirror`, `deliver_remote`,
`publish_state`), a launchd plist template under
`skills/sminos/references/`, tests (two homes, two `DAEMON_HOST`s, a bare
repository, one daemon tick driven by `sminos daemon tick` for
determinism). Interfaces: produces `tick`; consumes everything above.
Decisions: `daemon tick` runs one iteration and exits, and `run` loops it;
git is invoked with `-C log` and `GIT_TERMINAL_PROMPT=0`; `log_read` reads only
the top-level `*.jsonl` of `log/`, so `machines/` is invisible to it; the
plist's `EnvironmentVariables` carry what `skills/issue-tracker/SKILL.md`
says a launchd-run sminos needs (`SMINOS_HOME`, the gateway route), since
`derive` under the daemon runs `claude`; a sync failure is
logged to `$SMINOS_HOME/daemon.log` and the tick continues with the other
duties on the stale mirror; delivery to a `stopped` member resumes it as a
local `say @alias` would, and to a `busy` one pushes the frame. Does not
touch: the dispatch scripts. Proves: acceptance 6; tests pin that a second
tick re-delivers nothing, that a state flip lasting one tick is not
published, and that a claimed machine name refuses to run.

### M5 — Docs, acceptance, version

What exists at its end: `skills/sminos/SKILL.md` rewritten for the project
model (overview, protocol, operator surface, spawning, project and mirror,
daemon, board pipeline); `CLAUDE.md`'s repo map lines for `hooks/`
(the new hook) and sminos; a dated line in
`docs/doperpowers/specs/2026-09-26-sminos-family-chat-design.md`'s Decision
Log saying its deferred human seat and cross-machine family resumed here;
the acceptance section run as written and its transcript in this spec's
record; `scripts/bump-version.sh` to the next minor version in the same
commit. Touches those files and this spec. Proves: acceptance 7 and the
whole section.

### Concrete Steps

Working directory: the repository root, on the feature branch.

    tests/sminos/run-sminos-tests.sh            # expect: "... passed, 0 failed"    tests/issue-tracker/test-execute-dispatch.sh && tests/issue-tracker/test-review-dispatch.sh
    scripts/lint-shell.sh

Acceptance 6 by hand, one machine:

    git init --bare /tmp/smns-remote.git
    mkdir /tmp/R && cd /tmp/R && git init -q && SMINOS_HOME=/tmp/h1 DAEMON_HOST=h1 \
      sminos project init --name demo --remote /tmp/smns-remote.git && git add .smns && git commit -qm smns
    SMINOS_HOME=/tmp/h2 DAEMON_HOST=h2 sminos project attach        # clones the remote
    SMINOS_HOME=/tmp/h1 DAEMON_HOST=h1 sminos spawn a "wait"         # joins under h1
    SMINOS_HOME=/tmp/h2 DAEMON_HOST=h2 sminos spawn b "wait"         # joins under h2
    SMINOS_HOME=/tmp/h1 DAEMON_HOST=h1 sminos say "@b hello" ; SMINOS_HOME=/tmp/h1 DAEMON_HOST=h1 sminos daemon tick
    SMINOS_HOME=/tmp/h2 DAEMON_HOST=h2 sminos daemon tick            # expect: "delivered 1 to b"
    SMINOS_HOME=/tmp/h1 DAEMON_HOST=h1 sminos list                   # expect: b  idle  @h2 <age>

### Interfaces and Dependencies

In `skills/sminos/scripts/sminos.py`:

```python
class Project(NamedTuple):
    id: str          # uuid from .smns, or "local-<name>"
    name: str
    remote: str      # "" for a local project
    root: str        # directory holding .smns, or the cwd's owning repository
    home: str        # $SMINOS_HOME/projects/<id>

def resolve_project(cwd: str) -> Project
def writer_id(session_uuid: str | None = None) -> str      # "<machine>/<uuid>" | "<machine>/human" | "<machine>/daemon"
def log_append(project: Project, writer: str, kind: str, **fields) -> dict   # assigns ts, seq under the file lock; redacts for a remote project
def log_read(project: Project, since: dict | None = None, kinds: tuple = (), to: str | None = None) -> list[dict]
def cursor_load(project: Project, session_uuid: str) -> dict
def cursor_save(project: Project, session_uuid: str, cursor: dict) -> None
def redact(text: str) -> tuple[str, bool]

class Member(NamedTuple):
    session: str; alias: str; machine: str; local: bool; state: str; state_age: float | None
    charge: str; charge_source: str; status: str; by: str; worktree: str; seat: dict | None

def members(project: Project) -> list[Member]
def charge_of(member: Member, events: list[dict]) -> tuple[str, str]
def extract_marks(text: str) -> list[dict]        # [{"kind": "message"|"need-input", "text": str, "choices": [str]}]
def tick(project: Project) -> dict                # {"synced": bool, "delivered": int, "published": int}
```

CLI verbs added: `project init|show|attach`, `charge`, `derive`, `record`,
`daemon run|tick|install|status`. Removed: `--group`, `--parent`, `--team`,
`retire --cascade`, `@all`. Hook: `hooks/smns-record.sh`, events `Stop`
and `SessionStart`, calling `"$CLAUDE_PLUGIN_ROOT/skills/sminos/scripts/sminos" record`.

## Surprises & Discoveries

- Observation: a session can be asked what it is in charge of without
  touching it, by a headless fork; the fork copies the parent transcript.
  Evidence (2026-10-13, a 41-line demo session): `claude -p --resume <id>
  --fork-session --tools "" --output-format json "…"` answered `<message>This
  session has no standing task beyond showing you the to-human output
  style's marks on request…</message>`; usage `output_tokens 243,
  cache_creation 45613, cache_read 0`; a new transcript of 55 lines / 472K
  appeared beside the parent's 41 lines / 176K and was deleted by hand.
- Observation: the harness keeps an `ai-title` per session and rewrites it
  as the topic moves, so it cannot stand for the responsibility.
  Evidence: the session the human named "interactive learning" carried
  `"aiTitle":"구글 테이크아웃 Gemini 대화 기록"` as its latest of 54 titles;
  the MAWS architect session carried 2,597 titles, the latest "GUI AI agent
  workspace charter".
- Observation: the harness's session registry already groups the fleet by
  project, implicitly.
  Evidence: `~/.claude/sessions/*.json` on 2026-10-12 listed 26 live
  sessions whose `cwd` fell under six repositories, MAWS holding six and
  manim-master four, two of them user-named (`nameSource: "user"`).

## Decision Log

- Decision: verification — one independent spec review by a general-purpose
  subagent on fable (the design carries the weight), the
  `doperpowers:adversarial-reviewer` on the execution section (five
  milestones), and the branch reviewed at `doperpowers:review-code`'s
  xhigh rung at finish: the change rewrites the CLI the board pipeline
  spawns through.
  Rationale: the design rulings (host-less family, siblings, log-first
  delivery, git mirror) were settled in discussion with the human on
  2026-10-12–13 and recorded in the design sections with their
  alternatives; the risk left is buildability and regressions in a
  3,000-line CLI with a 2,500-line test suite.
  Date/Author: 2026-10-13, the authoring session.

## Outcomes & Retrospective

Pending — written at finish.
