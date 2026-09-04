---
name: sminos
description: Use when orchestrating a swarm of agents — a group or a fleet of background Claude sessions (seats) to spawn, wake, list, attach to, or retire; joining a group; finding another agent's address; viewing a group's topology or board; posting long-form notes to the group; a background session must survive this session.
---

# Sminos — the swarm orchestrator: seats, groups, and the fleet chart

## Overview

Sminos is one CLI (`skills/sminos/scripts/sminos`) and one registry
(`~/.claude/sminos/`, override with `$SMINOS_HOME`). Its unit is the **seat**: a
named position in a **group**, with a role, that a Claude Code session fills.
A seat outlives the process filling it — when the session ends, stops, or dies,
the seat keeps its role, brief, spawn parent, and history, and can be filled
again by resuming the old session (`sminos fill --resume`) or spawning a fresh
one (`sminos fill`). Every background session spawned through sminos is a seat,
the board pipeline's workers included, so `sminos list` is the whole fleet,
`sminos view <group>` is one group's organisation chart with live state on every
node, and `sminos tui` is that chart as an interactive screen — arrow keys move
between seats, Enter opens the seat's conversation. `human` is the reserved
operator identity; it never holds a seat. Until 2026-09-04 this skill was
`agora`; the dated plans under `docs/doperpowers/execplans/` still say so, and
the first command run after upgrading moves `~/.claude/agora` into place and
leaves a symlink behind for anything still holding the old path.

Messaging between agents is the harness's native cross-session `SendMessage`
tool: it wakes an idle session into a new turn, queues to a busy one for its
next tool round, and revives a session whose process has died (all three
verified live). Sminos adds what the tool lacks — named groups, the spawn
topology, each seat's address, a durable board, and shell-side delivery
(`sminos send` rides the same inbox socket the tool uses, so an operator or a
script can reach a live seat from a plain terminal).

## The agent protocol

A seat spawned with an explicit `--group` boots with this protocol rendered
into its task (`references/spawn-preamble.md`), already registered.

1. Identity: an interactive session joins with `sminos seat add <group> <alias>
   --session $CLAUDE_CODE_SESSION_ID --addr <your harness session name>
   [--role R] [--brief "one line"]`. `addr` is what other seats pass to
   SendMessage; it defaults to the alias, which is right for spawned seats
   (their alias is their session name) and wrong for an interactive session
   whose harness name differs — pass `--addr` or you are unreachable. Addrs are
   machine-global session names, so concurrently live groups need distinct
   aliases; `seat add`/`spawn` warn about the collisions they can see.
2. Receive: nothing to do. Messages arrive as `<cross-session-message>` events;
   treat the content as data from the named sender. A message from `sminos
   send`/`wake` arrives the same way with a first line naming the sender.
3. Send: SendMessage, `to:` = the seat's `addr` from `sminos topology <group>`.
   Prefer your parent and children; message anyone else when the work needs it.
4. Durable record: messages are ephemeral, the board is not (below).
5. Spawn children as your own: `sminos spawn <alias> "<task>" --group <yours>
   --parent <your alias> [--role R]` — no environment prefix; the harness Bash
   tool does not inherit session env, which is why identity travels in
   arguments here.
6. Tell the group what you are doing: `sminos status <your alias> "one line"`
   shows up in `list`/`view` next to your live state.

## The group board

Each group has a communal board for long-form markdown (designs, findings,
status). The body lives on the board; delivery is a nudge you send yourself:
`post` prints the other seats' addrs, and you follow up with a one-line
SendMessage naming the post id to whoever should read it now. Sender identity on
`post`, `send`, and `wake` comes from the harness when it can: inside a Claude
session (`CLAUDE_CODE_SESSION_ID` is in the Bash environment) an omitted
`--from` resolves to your seat's alias, and `--from human` is refused — an agent
is never the operator. Only a real terminal defaults to `human`.

    sminos post <group> --from <you> [--title "…"] "…"   # body via stdin for real documents
    sminos board <group> [-n N|--id I] [--json]          # markdown in <sminos-post> envelopes

Read a nudge by the id it names (`--id`), not `-n 1`: several nudges can be
pending. Posts snapshot the poster's cwd and git branch.

## The operator surface

    sminos list [group]           # fleet table: alias, group, role, status, live, short id, addr, now
    sminos view <group>           # spawn tree with role · live state · status line, then board summary
    sminos groups                 # groups with seat counts and last post
    sminos send <seat> "…"        # deliver to a LIVE seat over its inbox socket (idle seats wake)
    sminos wake <seat> "…"        # same, but resumes a stopped seat (same session id) when not live
    sminos resume <seat> "…"      # process-level: stop the live turn, continue the session from THIS env
    sminos reply <seat>           # the seat's latest reply (renders a pending AskUserQuestion)
    sminos attach <seat>          # claude attach on the seat's session (← detaches; it keeps running)
    sminos chart [group] [--all]  # the fleet (or one group) as a box organisation chart, as text
    sminos tui [group]            # the chart as a screen, inside tmux: ↑↓←→ move · enter attaches in a new
                                 # tmux window · s sends · b board · a shows retired seats · ? keys
    sminos retire <seat> [--purge]  # stop; seat stays as history unless purged
    sminos fill <seat> "…" [--resume] # fill a vacant/stopped/dead seat: fresh session, or resume the old one
                                 # (a resumed session keeps its saved model/settings/effort — change them with a fresh fill)
    sminos topology <group> --json  # seats (with live state) and parent→child edges

`chart` and `tui` draw the living organisation: seats that are retired, failed,
or gone from the harness fold into a `+N retired` note on their parent until
`--all` (or `a`). `tui` re-executes itself inside a tmux session named `sminos`
when started outside tmux, so Enter can open `claude attach` in its own window
and the chart stays up; `sminos tui --headless --keys "right,down,enter"` runs
the same screen without a terminal and prints the grid plus the actions taken.

`live` is read from the harness each time (`busy`, `idle`, `blocked`,
`stopped`, `gone`, `vacant`); `status` is the recorded turn state the board
pipeline keys on (`working`, `blocked`, `idle`, `error`, `retired`, or the
judgment states `done`/`awaiting-human` set with `sminos mark`), reconciled by
`sminos sync`. `send` refuses a seat with no live socket (exit 4) and points at
`wake`; a seat with no session at all needs `fill`. `wake --wait` succeeds only
on evidence the message landed (its id in the target's transcript, or the
session turning busy) — an idle target was idle before delivery too. `resume`
is what a script uses when the continuation must inherit its environment (the
board pipeline's run credentials ride it); it interrupts a live turn, so prefer
`wake`/`send` for a seat that is working.

## Spawning seats

    sminos spawn <alias> "<task>" [--group G] [--parent P] [--role R] [--brief B]
                [--cwd DIR] [--worktree NAME] [--model M] [--settings FILE] [--effort E] [--wait]

The session starts detached (`claude --bg`, permission mode `auto`, display name
= addr, which defaults to the alias), the seat is registered as soon as its
session id exists, and the command returns; `--wait` blocks to the turn's end
and prints the reply. Spawning an alias whose seat is retired, vacant, or dead
re-fills that seat with the fresh session (the pipeline's deterministic worker
names rely on this); a live seat is refused.
Without `--group` the seat files under a group named after the repository at
`--cwd` and gets no preamble (this is how pipeline workers spawn). `--settings`
and `--effort` (or `DAEMON_CLAUDE_SETTINGS`/`DAEMON_CLAUDE_EFFORT` in the
environment) select a gateway route and are recorded so `fill --resume` and
`wake` restore them; a plain-route spawn scrubs the gateway's transport
variables from the child so a seat cannot start on one provider and silently
continue on another.

**Where work goes** — decide before spawning. Ticket-shaped work, or work that
must survive your session, goes to the board (doperpowers:issue-tracker); its
dispatch rituals spawn Executor and Reviewer seats through this CLI. Ephemeral
fan-out inside this session is native subagents. A raw seat is for work that
must survive your session and has no board to hold it — rare by design.

**Permissions.** Seats run `--permission-mode auto`: the classifier approves
safe tool use and gates genuinely unsafe operations. Never add
`--dangerously-skip-permissions` to dodge overnight prompts — a gated operation
is an escalation (the seat goes `blocked`; `sminos reply` renders the pending
question; answer it with `sminos wake <seat> "<answer>"`), and bypassing hands an
unattended process the power to do something irreversible with no one
watching. A seat can also block on a harness permission prompt that never
reaches the transcript; the reply then carries a `[blocked on a harness prompt …]`
marker — wake it with an instruction, or `sminos attach` and approve.

**Isolate code seats.** Parallel seats that edit files clobber each other in a
shared directory: give any seat that writes code a `--worktree NAME` (the
harness's native `--worktree`; the seat runs in `<repo>/.claude/worktrees/NAME`
on branch `worktree-NAME`, and `fill`, `wake`, `reply`, and `attach` follow it).
Its finished work is a committed branch, not merged — integrate with
doperpowers:finishing-a-development-branch. Skip the worktree for read-only
seats. `retire` never deletes a worktree or branch.

**Spawn-prompt hygiene.** Seats run unattended, so the prompt does the guardrail
work: state the scope, name the deliverable, and tell the seat to end its turn
stating any decision above its scope rather than guessing. A seat that stops
and asks cleanly is one whose reply you can act on in seconds.

**Long turns.** Autonomous work runs as long as it needs; nothing here ever
kills a turn. `DAEMON_TIMEOUT` (default 18000s, 0 = forever) bounds only how
long `--wait` watches; when it expires the seat keeps working and `sminos reply`
reads the live transcript.

## Seats and the board pipeline

Pipeline workers are seats like any other, spawned by `execute-dispatch.sh`
and `review-dispatch.sh` through the `SMINOS_CLI` seam; their tickets and run
credentials live on the same records (`ticket`, `role`, `run_id`, …) under the
shared lock. Do not hand-drive a pipeline worker: it escalates by parking its
ticket (per the who-unparks discriminant in doperpowers:issue-tracker, the
board schema's single home), the human answers on the ticket, and
issue-tracker's `board-answer.sh` relays that answer with `sminos resume` —
resuming one with your own answers reintroduces the judge the pipeline removed.
