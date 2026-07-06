---
name: orchestrating-daemons
description: Use when you need to spawn, track, and autonomously drive several durable background `claude` sessions (daemons) that persist across turns and sessions and can be resumed later — kicking off long-running or independent tasks to run on their own and checking back, delegating to resumable headless sessions, or fanning out work that must survive this session ending. Not for ephemeral in-session subagents.
---

# Orchestrating Daemons

## Overview

A **daemon** is a durable background `claude` session, spawned with `claude --bg` so it runs as its own process, is visible in `claude agents`, and survives this session ending. You are the orchestrator: you spawn a fleet of them, read each reply, and for every reply make one call — **answer it yourself, queue it for the human, or wake the human now** — then resume it. The human can see the fleet in `claude agents` and `claude --resume <uuid>` any daemon.

**Every turn is a native background agent.** Resuming a daemon *forks* a new `--bg` agent that carries the full conversation forward — so every turn (the first and each resume) shows up in `claude agents` in real time. The registry chains the session ids under one stable identity (the daemon's original uuid): you always address a daemon by that id or by its name, even though its human-visible short id changes with every turn. Once a fork is confirmed, the superseded turn's session is **purged** via `claude rm` — the native deregister; deleting its files alone is not enough, because the supervisor re-materializes the entry on the next `claude attach` (observed live as a ghost "working" dashboard row). `claude rm` also deletes a CLEAN worktree along with its owning turn, so the purge dirty-guards the daemon's worktree with a sentinel file for the duration; the transcript is removed separately (the fork physically copies the full conversation forward). The agents view thus shows exactly one session per daemon instead of piling up completed turns; failure paths purge nothing, keeping the old session as the recovery point. The scripts hide the churn — don't hand-roll the `--bg --resume` fork yourself.

**This is not `dispatching-parallel-agents`.** That skill fans out *in-session* Task subagents that share your context and die with your turn. Daemons are separate `claude` processes with their own context windows, resumable across sessions. Use daemons when work must persist, be resumed later, or not consume your context.

## The loop

`daemon-spawn.sh` and `daemon-resume.sh` both block until the daemon's turn finishes. Never run them in the foreground. If your harness has a **Monitor** tool (streams a command's stdout into the conversation as events), run each turn under it — the scripts print the full reply on stdout when the turn ends, so the reply lands in your context with no read step. Otherwise run each in a **background shell** (Claude Code: the Bash tool with `run_in_background: true`) and Read the output file when its completion notification arrives.

1. **Spawn** each task: `scripts/daemon-spawn.sh "<name>" "<task>" [cwd] [worktree]` under a Monitor / background shell — pass a worktree name for any code-writing daemon (see *Isolating code daemons*).
2. **Read** the reply — it's the `--- reply ---` block in the turn output (delivered as a Monitor event, or via Read on the background shell's output file; `scripts/daemon-reply.sh <id>` re-prints it any time).
3. **Judge** it with the rubric below.
4. **Resume** with your answer: `scripts/daemon-resume.sh <uuid> "<message>"` under a Monitor / background shell — this forks a fresh `--bg` agent (new short, natively visible in `claude agents`) while keeping the daemon's stable id. Or, if you queued it, `scripts/daemon-mark.sh <uuid> awaiting-human "<why>"`.
5. **Track**: `scripts/daemon-list.sh` is your fleet view — show it when the human asks "what's running". Retire finished daemons with `scripts/daemon-retire.sh <uuid>`.

## Toolkit

Paths are relative to this skill's directory. The scripts hide every sharp edge (UUID handling, cwd-scoped resume, ANSI, JSON parsing, macOS timeout) — **use them; don't hand-roll `claude` invocations.**

| Script | Does |
|---|---|
| `daemon-spawn.sh <name> <task> [cwd] [worktree] [model]` | Spawn a `--bg` daemon, run turn 1, wait for it. Pass a `worktree` name to isolate it (see below). Launch in a bg shell. |
| `daemon-resume.sh <uuid> <message>` | Continue a daemon by **forking a new `--bg` turn** (`claude stop` the old turn, then `--bg --resume`) — natively visible in `claude agents`; the registry tracks the current session id. Launch in a bg shell. |
| `daemon-reply.sh <id>` | Print a daemon's latest full reply. |
| `daemon-list.sh [status]` | Fleet view; optional status filter. |
| `daemon-mark.sh <id> <status> [note]` | Record a judgment state (`awaiting-human`, `done`) + why. |
| `daemon-retire.sh <id> [purge]` | Drop from active fleet; transcript stays resumable. |

## Decide vs. escalate

When a daemon ends its turn with a question or decision point, **"needs a human" is not the same as "needs a human now."** Default to answering or queuing; reserve waking for genuine urgency.

| The daemon is asking about… | You… |
|---|---|
| Something technical/mechanical with an obvious best answer (naming, which test, a bug fix, a retry, a clarification you can infer) | **Answer it yourself** and resume. |
| Whether to exceed the scope it was given | **Answer "stay in scope"** and resume; note the suggestion for the human's next check-in. |
| A genuine product / design / brand / taste fork, or approval for something large or irreversible (implement a recommendation, deploy, spend, delete) — but nothing is blocked or unsafe *right now* | **Queue it**: `daemon-mark.sh <id> awaiting-human`, have the daemon produce every option / a decision-ready writeup, and surface it at the next check-in. Don't wake. |
| Something destructive/irreversible about to happen, a security / data-loss / production risk, or a hard blocker where every path needs info only the human has **and** it can't wait | **Wake the human now** (send a PushNotification). |

You are trusted to answer on the human's behalf for technical and mechanical calls. Escalate *judgment*, not *work*.

## Isolating code daemons

Parallel daemons that edit files will clobber each other in a shared directory. **Spawn any daemon that writes code with a worktree name** (the 4th arg) so it runs isolated:

```
daemon-spawn.sh "rename-auth" "<task>" /path/to/repo rename-auth
```

This uses `claude`'s native `--worktree` flag (per `using-git-worktrees`: prefer native worktree tools over hand-rolled `git worktree add`) to run the daemon in `<repo>/.claude/worktrees/rename-auth` on branch `worktree-rename-auth`. Resume, reply-reading, and tracking follow the worktree automatically. **Skip the worktree for read-only/research daemons** — they don't write, and may not even be in a git repo.

An isolated daemon's finished work is a *committed branch, not merged*. Integrating it is a separate decision: surface it (queue/escalate per the rubric) and use `finishing-a-development-branch` to merge. `daemon-retire.sh` never deletes a worktree or branch.

If the consumer repo tracks work on an `issue-tracker` board, a code daemon that owns a ticket can move **its own** ticket from inside its worktree — `board-transition.sh <id> in-progress` at start, `board-transition.sh <id> in-review "<note>" --pr <URL>` when it opens the PR (that single-ticket script is worktree-safe; bulk board ops still run from the main checkout). Tell the daemon its ticket id in the spawn prompt so it can, instead of routing every state nudge back through you.

## Spawn-prompt hygiene

Daemons run unattended, so the prompt does the guardrail work. In every spawn prompt: **state the scope explicitly, name the deliverable, and tell the daemon to END ITS TURN clearly stating any decision that is above its scope rather than guessing.** A daemon that stops and asks cleanly is one whose reply you can classify in seconds.

## Long turns

Autonomous work runs as long as it needs — never pace a daemon around a timer. The toolkit **never kills a turn**: every turn (spawn and resume alike) runs as an independent `--bg` process that keeps working even if this orchestrator session ends. `DAEMON_TIMEOUT` (default 18000s = 5h, `0` = watch forever) bounds only how long the spawn/resume *watcher* polls — not the turn itself. Notes for long turns:

- On a very long turn the watcher just stops watching; the daemon keeps working, and `daemon-reply.sh <id>` reads the reply straight from the transcript once the turn lands.
- Running a turn under a non-persistent **Monitor**? Its own cap maxes out at 1h — arm it with `persistent: true` for anything longer.

## Permissions

The scripts spawn with `--permission-mode auto` — the LLM classifier auto-approves safe tool use and gates genuinely unsafe ops. **Do not add `--dangerously-skip-permissions` to dodge overnight prompts.** A gated op is a *feature*: the daemon goes `blocked` (the scripts report `status=blocked`), which your rubric turns into an escalation. Bypassing hands an unattended process the power to do something irreversible with no one watching.

A daemon also goes `blocked` when it calls **AskUserQuestion** — headless, nobody can click an option. The recorded reply renders the pending question and its options; answer it as plain text with `daemon-resume.sh <id> "<answer>"` (the pending tool call is interrupted and your text arrives as the next user message — daemons handle this fine).

A daemon can also block on a **harness permission prompt** that holds a tool call before it ever reaches the transcript (observed live: an AskUserQuestion call stuck at the permission layer). The recorded reply then carries a `[blocked on a harness prompt …]` marker instead of a rendered question — the daemon's last text states what it wanted; resume with your answer/instruction (the pending call is interrupted), or `claude attach` the session to approve it interactively.

## Common mistakes

- **Hand-rolling `claude --bg --resume` to continue a daemon** — it forks a new agent but leaves the registry behind: the new short/uuid aren't chained into `current`, so `daemon-reply.sh` / `daemon-list.sh` / `daemon-retire.sh` lose track of the live turn. Always go through `daemon-resume.sh`, which forks *and* updates the chain.
- **Resuming from the wrong directory** — `claude --resume` is scoped to the daemon's cwd/project. The scripts record and restore cwd; hand-rolled resumes fail with "No conversation found".
- **Running a daemon turn in the foreground** — it blocks your main loop for the whole turn. Always launch spawn/resume under a Monitor or in a background shell.
- **Waking the human for scope or "should I do more?" questions** — those are yours to answer. Queue the taste/approval forks; wake only for the last row of the rubric.
- **Reading an OLD short id after a resume** — each resume forks a new `--bg` agent, so `claude agents` shows the current turn under a *new* short and the old one drops out of the active view. Don't cache a short across turns; `daemon-list.sh` maps each daemon name to its current short, and every script call also accepts the daemon's stable id (its original uuid).
