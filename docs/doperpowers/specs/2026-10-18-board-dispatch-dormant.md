# Board dispatch goes dormant: the owner's ruling (2026-10-18)

## Ruling

The board's automatic dispatch is dormant. Nothing starts a session from
the board: no sweep, no issue or pull-request event trigger, no Architect,
Executor, spike or review stand-in seat, and no QA agent run by a seat that
owns a ticket.

Two things stay.

- **The workflow those seats ran — architect → executor → reviewer.** It
  still drives most complex work, attended: the session that talks with
  the human designs (doperpowers:brainstorming, doperpowers:execspec), a
  `plan-executor` or task subagents build, doperpowers:review-code reviews,
  and the session merges.
- **The board as the backlog**, as the 2026-10-09 ruling already described
  it (`2026-10-09-attended-orchestration-ruling.md`): tickets hold the state
  of future work. The human names tickets to work, and a session may also
  take a ticket that is ready to implement on its own initiative — not
  every ticket needs the owner's approval (the owner, later the same day).
  Whoever takes a ticket runs it through the workflow above.

If board-driven spawning comes back, it will very likely be a mirror of the
attended workflow run automatically: the same architect → executor →
reviewer path a session runs with its human, started by a trigger instead
of by the human's word. It would not be the separate doctrine of worker
protocols, lanes, parks and relays the pipeline had. Re-arming the current
machinery as it stands is not the way back.

This supersedes item 3 of the 2026-10-09 ruling, which kept the
decentralized dispatch doctrine as written on the ground that a large
production board might still need mechanical dispatch.

## Why

- **Unsupervised, unattended work proved unreliable and slow.** A session
  that talks with the human directly settles a fork in minutes; a seat that
  parks its ticket waits for the human's next wake, a relay, and a resume.
  The 2026-10-09 ruling already found that the human has to fill gaps no
  design articulates; this ruling draws the consequence for dispatch.
- **sminos redefined multi-session work.** Sessions in a project are
  members that message each other and their humans directly (the project
  log, the desk). The coordination the board's park → answer → resume
  carried now happens in conversation.
- **One session can own a large unit.** doperpowers:decomposing and MAWS
  showed it: one interactive session with a subagent tree built a whole
  product, 29 plan-executors of 4–16 hours each under it (evidence in the
  2026-10-09 ruling). Work the pipeline cut into tickets for separate seats
  fits inside one session.
- **Left looking live, the pipeline's doctrine misled sessions.** They read
  the issue-tracker skill, the `qa-loop` agent and old memory notes as
  current and proposed board seats, dispatches and park/resume for work the
  human was directing in the conversation. For example, 2026-10-15: "The
  follow-up tickets — when should we dispatch the workers?" drew a board
  seat proposal; the owner answered "we won't do the board seat, just do
  the sub agent."

## What is dormant

The code stays where it is, unchanged, with its tests still in CI. Nothing
arms it.

- doperpowers:issue-tracker, dispatch: `scripts/execute-dispatch.sh`,
  `scripts/review-dispatch.sh`, `scripts/board-sweep.sh` with
  `_sweep_api.sh`, `scripts/board-bind.sh`, the bound-session relay in
  `scripts/board-answer.sh`, and surfaces' one-worker-per-surface
  serialization.
- doperpowers:issue-tracker, worker doctrine: `references/worker-bootstrap.md`,
  `architect-worker-protocol.md`, `implement-worker-protocol.md`,
  `implement-decompose.md`, `spike-worker-protocol.md`, `ticket-gate.md`.
- The seats' review loop: `agents/qa-loop.md` (still registered; its
  description says it is dormant) and its Codex port,
  `references/review-loop.md`, `review-standin-protocol.md`,
  `review-standin-bootstrap.md`, `wave-board.md`.
- Operator manuals and triggers: `references/execution-loop.md`,
  `sweep-setup.md`, `runner-setup.md`, `issue-dispatch.yml`,
  `pr-review-dispatch.yml`, `infra/board-sweep/`, `infra/worker-host/`.

The documents sessions read were rewritten so that none routes work into
the pipeline: the issue-tracker skill now describes the backlog and how an
attended session takes a ticket (its text before the ruling, with the
dispatch and wake rituals: `git show d4393039:skills/issue-tracker/SKILL.md`), and doperpowers:execspec,
doperpowers:decomposing, doperpowers:sminos, the `plan-executor` agent, the
README and the repository's CLAUDE.md lost the sentences that sent work to
seats.

## Live state at the ruling

- MacBook: no sweep job is loaded.
- Mac mini: the sweep's LaunchAgent was already
  `com.user.doperpowers-board-sweep.plist.disabled`. The ida-solution
  self-hosted Actions runner (label `claude-review`, the only runner of the
  PR-review dispatch workflow; last job 2026-08-26) was stopped on the
  owner's word, its LaunchAgent renamed
  `actions.runner.IDA-solution-ida-solution.Mac-mini-claude.plist.disabled-20261018`.
  `launchctl load` on the original name restores it. MAWS's ci-kit runner
  on the same machine was not touched.
- Hetzner: no worker host. The only server is `session-mirror`.
- GitHub: no dispatch workflow in SSFSKIM/doperpowers, MAWS, cua or arkho.
  ida-solution's workflows can no longer be read from this account (404);
  all of them were disabled on 2026-08-02.
- Still running, and neither of them dispatch: the Arkho board service,
  which stores the backlog of doperpowers and its sibling repositories,
  and possibly ida-solution's "Feedback Triaging" cloud routine, which
  files tickets on that repository's board from in-app feedback (not
  verified here; it belongs to ida-solution).
