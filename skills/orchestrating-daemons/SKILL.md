---
name: orchestrating-daemons
description: Use when spawning, resuming, tracking, or debugging durable background `claude` sessions (daemons) — the process substrate the board pipeline's dispatchers call, or the rare ad-hoc task that must survive this session ending and has no board to hold it. NOT the default for fanning out work: ticket-shaped work goes to the board (doperpowers:implementing-tickets), in-session fan-out is native subagents (doperpowers:dispatching-parallel-agents).
---

# Daemons — the durable-session substrate

## Overview

A **daemon** is a durable background `claude` session, spawned with `claude --bg` so it runs as its own process, is visible in `claude agents`, and survives this session ending. This skill is the *substrate*: the scripts that spawn, resume, track, and retire daemons, and the mechanics that make those operations safe. It is not an orchestration doctrine — the fleets that used to be driven from here now live in the board pipeline, where workers escalate via park states and nobody judges their turn-ends.

**Where work goes** (decide this before spawning anything):

| the work is… | it goes to… |
|---|---|
| ticket-shaped, or must survive your session | the board — register it (doperpowers:issue-register); implement workers (doperpowers:implementing-tickets) and review workers (doperpowers:reviewing-prs) are daemons the *dispatch rituals* spawn through this substrate |
| needing the human's live steering | the board, parked `interactive-preferred` |
| ephemeral fan-out inside this session | native subagents (doperpowers:dispatching-parallel-agents) — they share your session's lifetime, and that's fine because the work does too |
| must survive your session AND there is no board to hold it (a repo without issue-tracker, an overnight run in a bare directory) | a raw ad-hoc daemon — the escape hatch this skill's hand-driven loop below exists for |

That last row is rare by design. "Must survive my session" is practically the definition of "worth a ticket": durable work wants durable state, and the board is the durable state layer. Reach for a raw daemon only when there is genuinely no board.

## Every turn is a native background agent

Resuming a daemon *forks* a new `--bg` agent that carries the full conversation forward — so every turn (the first and each resume) shows up in `claude agents` in real time. The registry chains the session ids under one stable identity (the daemon's original uuid): you always address a daemon by that id or by its name, even though its human-visible short id changes with every turn. Once a fork is confirmed, the superseded turn's session is **purged** via `claude rm` — the native deregister; deleting its files alone is not enough, because the supervisor re-materializes the entry on the next `claude attach` (observed live as a ghost "working" dashboard row). `claude rm` also deletes a CLEAN worktree along with its owning turn, so the purge dirty-guards the daemon's worktree with a sentinel file for the duration; the transcript is removed separately (the fork physically copies the full conversation forward). The agents view thus shows exactly one session per daemon instead of piling up completed turns; failure paths purge nothing, keeping the old session as the recovery point. The scripts hide the churn — don't hand-roll the `--bg --resume` fork yourself.

## Toolkit

Paths are relative to this skill's directory. The scripts hide every sharp edge (UUID handling, cwd-scoped resume, ANSI, JSON parsing, macOS timeout) — **use them; don't hand-roll `claude` invocations.** The board pipeline's dispatchers (`issue-tracker`'s dispatch ritual, `reviewing-prs`' `review-dispatch.sh`) call `daemon-spawn.sh` mechanically and hard-code this location; the registry (`~/.claude/orchestrating-daemons`) is shared with the board scripts (`board-bind.sh`, `board-reconcile.sh`).

| Script | Does |
|---|---|
| `daemon-spawn.sh <name> <task> [cwd] [worktree] [model]` | Spawn a `--bg` daemon, run turn 1, wait for it. Pass a `worktree` name to isolate it (see below). Launch in a bg shell. |
| `daemon-resume.sh <uuid> <message>` | Continue a daemon by **forking a new `--bg` turn** (`claude stop` the old turn, then `--bg --resume`) — natively visible in `claude agents`; the registry tracks the current session id. Launch in a bg shell. |
| `daemon-reply.sh <id>` | Print a daemon's latest full reply. |
| `daemon-list.sh [status]` | Fleet view; optional status filter. |
| `daemon-mark.sh <id> <status> [note]` | Record a judgment state (`awaiting-human`, `done`) + why. |
| `daemon-retire.sh <id> [purge]` | Drop from active fleet; transcript stays resumable. |

## Driving an ad-hoc daemon by hand

For the escape-hatch case only — pipeline workers are spawned by their dispatch rituals and never hand-driven. `daemon-spawn.sh` and `daemon-resume.sh` both block until the daemon's turn finishes. Never run them in the foreground. If your harness has a **Monitor** tool (streams a command's stdout into the conversation as events), run each turn under it — the scripts print the full reply on stdout when the turn ends, so the reply lands in your context with no read step. Otherwise run each in a **background shell** (Claude Code: the Bash tool with `run_in_background: true`) and Read the output file when its completion notification arrives.

1. **Spawn**: `scripts/daemon-spawn.sh "<name>" "<task>" [cwd] [worktree]` under a Monitor / background shell — pass a worktree name for any code-writing daemon (see *Isolating code daemons*).
2. **Read** the reply — it's the `--- reply ---` block in the turn output (delivered as a Monitor event, or via Read on the background shell's output file; `scripts/daemon-reply.sh <id>` re-prints it any time).
3. **Resume** with your answer: `scripts/daemon-resume.sh <uuid> "<message>"` under a Monitor / background shell.
4. **Track**: `scripts/daemon-list.sh` is your fleet view — show it when the human asks "what's running". Retire finished daemons with `scripts/daemon-retire.sh <uuid>`.

## Escalation

Fleet-of-workers escalation lives in the board pipeline: implement and review workers park their own tickets (`needs-human` / `needs-info` / `interactive-preferred`, per the who-unparks discriminant in doperpowers:implementing-tickets), the human answers on the ticket at their next wake, and nobody sits between a worker and the board.

For a hand-driven ad-hoc daemon: answer mechanical/technical questions yourself and resume — you are trusted for those calls. A genuine product/taste/approval fork is the signal the work was ticket-shaped after all — register it on the board and park it `needs-human` with the question as the note. Only in a truly board-less context, `daemon-mark.sh <id> awaiting-human "<why>"` queues it for the human's next check-in; wake the human now (PushNotification) only for something destructive/irreversible about to happen or a security / data-loss / production risk that can't wait.

## Isolating code daemons

Parallel daemons that edit files will clobber each other in a shared directory. **Spawn any daemon that writes code with a worktree name** (the 4th arg) so it runs isolated:

```
daemon-spawn.sh "rename-auth" "<task>" /path/to/repo rename-auth
```

This uses `claude`'s native `--worktree` flag (per `using-git-worktrees`: prefer native worktree tools over hand-rolled `git worktree add`) to run the daemon in `<repo>/.claude/worktrees/rename-auth` on branch `worktree-rename-auth`. Resume, reply-reading, and tracking follow the worktree automatically. **Skip the worktree for read-only/research daemons** — they don't write, and may not even be in a git repo.

An isolated daemon's finished work is a *committed branch, not merged*. Integrating it is a separate decision: surface it to the human and use `finishing-a-development-branch` to merge. `daemon-retire.sh` never deletes a worktree or branch.

If the consumer repo tracks work on an `issue-tracker` board (the board IS the repo's GitHub issues), a code daemon that owns a ticket moves **its own** ticket from inside its worktree — `board-transition.sh <n> in-progress` at start, `board-transition.sh <n> in-review "<note>" --pr <URL>` when it opens the PR (every board script is worktree-safe; the board lives on GitHub, not in a git file). The pipeline's rendered protocols already carry the issue number; give an ad-hoc daemon its issue number in the spawn prompt for the same reason.

## Spawn-prompt hygiene

Daemons run unattended, so the prompt does the guardrail work. In every spawn prompt: **state the scope explicitly, name the deliverable, and tell the daemon to END ITS TURN clearly stating any decision that is above its scope rather than guessing.** A daemon that stops and asks cleanly is one whose turn-end you can act on in seconds. (Pipeline workers get this from their rendered protocols; this is for ad-hoc spawn prompts.)

## Long turns

Autonomous work runs as long as it needs — never pace a daemon around a timer. The toolkit **never kills a turn**: every turn (spawn and resume alike) runs as an independent `--bg` process that keeps working even if this orchestrator session ends. `DAEMON_TIMEOUT` (default 18000s = 5h, `0` = watch forever) bounds only how long the spawn/resume *watcher* polls — not the turn itself. Notes for long turns:

- On a very long turn the watcher just stops watching; the daemon keeps working, and `daemon-reply.sh <id>` reads the reply straight from the transcript once the turn lands.
- Running a turn under a non-persistent **Monitor**? Its own cap maxes out at 1h — arm it with `persistent: true` for anything longer.

## Permissions

The scripts spawn with `--permission-mode auto` — the LLM classifier auto-approves safe tool use and gates genuinely unsafe ops. **Do not add `--dangerously-skip-permissions` to dodge overnight prompts.** A gated op is a *feature*: the daemon goes `blocked` (the scripts report `status=blocked`), which is an escalation — a pipeline worker's park, or an ad-hoc daemon's queue-for-the-human. Bypassing hands an unattended process the power to do something irreversible with no one watching.

A daemon also goes `blocked` when it calls **AskUserQuestion** — headless, nobody can click an option. The recorded reply renders the pending question and its options; answer it as plain text with `daemon-resume.sh <id> "<answer>"` (the pending tool call is interrupted and your text arrives as the next user message — daemons handle this fine).

A daemon can also block on a **harness permission prompt** that holds a tool call before it ever reaches the transcript (observed live: an AskUserQuestion call stuck at the permission layer). The recorded reply then carries a `[blocked on a harness prompt …]` marker instead of a rendered question — the daemon's last text states what it wanted; resume with your answer/instruction (the pending call is interrupted), or `claude attach` the session to approve it interactively.

## Common mistakes

- **Defaulting to a daemon to fan out work** — ticket-shaped work belongs on the board (registered, gated, parked there); in-session parallelism is native subagents (doperpowers:dispatching-parallel-agents). A raw daemon is for work that must survive this session and has no board to hold it.
- **Hand-rolling `claude --bg --resume` to continue a daemon** — it forks a new agent but leaves the registry behind: the new short/uuid aren't chained into `current`, so `daemon-reply.sh` / `daemon-list.sh` / `daemon-retire.sh` lose track of the live turn. Always go through `daemon-resume.sh`, which forks *and* updates the chain.
- **Resuming from the wrong directory** — `claude --resume` is scoped to the daemon's cwd/project. The scripts record and restore cwd; hand-rolled resumes fail with "No conversation found".
- **Running a daemon turn in the foreground** — it blocks your main loop for the whole turn. Always launch spawn/resume under a Monitor or in a background shell.
- **Hand-driving a pipeline worker** — board workers are spawned by their dispatch rituals and escalate via park states; resuming one with your own answers reintroduces the judge the pipeline removed. Answers to a parked ticket belong on the ticket.
- **Reading an OLD short id after a resume** — each resume forks a new `--bg` agent, so `claude agents` shows the current turn under a *new* short and the old one drops out of the active view. Don't cache a short across turns; `daemon-list.sh` maps each daemon name to its current short, and every script call also accepts the daemon's stable id (its original uuid).
