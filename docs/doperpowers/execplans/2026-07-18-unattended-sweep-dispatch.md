# Unattended dispatch: the board sweep tick that retires manual worker dispatch

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up
to date as work proceeds. It is maintained in accordance with
`skills/execplan/references/PLANS.md` (repository root), which defines the
requirements for ExecPlans.

## Purpose / Big Picture

Today every worker in the board pipeline is dispatched by a human running a
script: a person picks the top eligible ticket and runs the dispatch ritual,
a person runs `review-dispatch.sh <pr>` when the GitHub Actions path is
blocked, a person runs `land-dispatch.sh <pr>` after approving, a person
runs `board-answer.sh` to relay their own answers, and a person resurrects
dead workers by hand. After this change, a five-minute mechanical tick — a
single shell script with no model calls and no resident process — does all
of it: it spawns implement workers onto eligible tickets (up to a
concurrency cap), attaches the review loop to open PRs, dispatches a land
worker the moment a human approves a reviewed PR, resumes workers that died
mid-turn (bounded), parks tickets whose workers are beyond recovery, kills
workers whose tickets were closed underneath them, and relays a human's
ticket comment to the parked worker that asked for it. The human's remaining
gestures are exactly the judgment ones: registering and parking tickets,
answering park questions on the ticket, and clicking Approve on non-trivial
PRs.

You can see it working by arming the tick on a consumer repo
(ida-solution) and watching a `ready-for-agent` ticket get a worker, a
`[gate]` comment, a PR, a review worker, and — after a human Approve — a
land worker, with nobody running a dispatch command at any point.

This is the "unattended phase" that the Symphony comparison
(`docs/doperpowers/2026-07-11-symphony-comparison.md` §9) reserved: import
the orchestrator's *functions* (liveness), refuse its *form* (a resident
process). Every pass below is idempotent and keeps its state in GitHub and
the daemon registry, never in the tick's memory.

## Progress

- [x] (2026-07-18 08:20Z) Grill complete; decisions recorded in the Decision Log.
- [x] (2026-07-18 08:30Z) Worktree `worktree-unattended-sweep` created from origin/main (fb1c3be, v7.21.1).
- [x] (2026-07-18 08:40Z) ExecPlan authored and committed.
- [x] (2026-07-18 09:10Z) M1: `implement-dispatch.sh` (triggered + `--sweep` + cap + dedupe + strict render) + hermetic suite green (34 asserts; RED first — suite failed before the script existed), shellcheck clean.
- [x] (2026-07-18 09:45Z) M2: `board-sweep.sh` (recover / cancel / dispatch / review / land / relay / report passes, mkdir lock — macOS has no flock(1)) + hermetic suite green (26 asserts; RED verified by absence check, exit 127), shellcheck clean.
- [x] (2026-07-18 10:30Z) M3: prose routing (dispatch ritual, TECH-DEBT strikes for items 1/2/10-L2), `sweep-setup.md`, `issue-dispatch.yml` + `land-on-approve.yml` templates, protocol-content pins; full battery green (see Surprises for the slot-counter defect a pre-arm registry inspection surfaced).
- [x] (2026-07-18 11:05Z) M4 (core): live shakedown on ida-solution — tick 1 dispatched all three ELIGIBLE tickets (#492/#593/#595, spawn→bind→gateway meta) + attached review-pr-574; all three workers passed the ROUTED ticket-gate and wrote `[gate] pass` verdicts (the 7.21.x schema's first live exercise); tick 2 dispatched nothing (idempotence proven); launchd agent installed and loaded (`launchctl list` exit 0). Evidence in Artifacts.
- [x] (2026-07-18 11:25Z) M4 (tail): launchd tick FAILED as the TCC memory predicted — `Operation not permitted` executing anything under `~/Documents` from launchd context (probe: `launchctl submit -- /bin/ls ~/Documents/GitHub` → EPERM). Not a code defect: a machine-level folder-protection constraint. Mitigated three ways: sweep-setup.md documents the remedies (one-time bash grant / terminal-session timer / relocation), an interim detached timer loop was started from the TCC-granted session (pid 87645, automation live now), and the launchd agent stays loaded so it self-arms the moment the grant is made (mkdir lock + idempotence make dual timers safe).
- [x] (2026-07-18 12:10Z) M5 (review): whole-branch fresh-context review (native reviewer subagent — the human declined the codex launch; see Decision Log) returned 2×P1 + P2 + P3, ALL confirmed real and fixed test-first (finalize-noop fallback in RECOVER; RELAY rebuilt on finalize-normalize + transcript-mtime ordering; DEFAULT_BRANCH fallback reachable under errexit; `mkdir -p DAEMON_HOME` before the lock). Full battery re-run green.
- [x] (2026-07-18 12:40Z) M5 (handoff): retrospective written; PR opened to main and left for the human to merge.

## Surprises & Discoveries

- Observation: `daemon-spawn.sh` already anticipated this phase — a
  `--no-wait` flag documented "for runner/cron dispatch where blocking would
  hold the job slot", plus an `env -u RUNNER_TRACKING_ID` strip so daemons
  survive a GitHub Actions runner's post-job cleanup.
  Evidence: `skills/orchestrating-daemons/scripts/daemon-spawn.sh` header
  and spawn line.
- Observation: the GitHub Actions event path is installed and firing on
  ida-solution but every run queues ~24h and is cancelled — the
  `claude-review` self-hosted runner was never registered (org admin
  blocked, ida-solution#302).
  Evidence: `gh run list --workflow=pr-review-dispatch.yml` shows
  `queued … 23h57m` rows ending `cancelled`.
- Observation (M4 tail): the launchd path is blocked on this machine by
  macOS folder protection, not by anything in the sweep — a launchd-context
  shell gets EPERM on ANY read under `~/Documents`, where both the plugin
  worktree and the consumer repo live. The spawned WORKERS were never the
  problem (they run under the resident claude daemon, which holds grants);
  the tick script's own reads are. Documented in sweep-setup.md with three
  remedies; interim terminal-session timer carries the automation.
  Evidence: `/tmp/board-sweep-launchd.log` → three `Operation not
  permitted` lines; `launchctl submit -- /bin/ls ~/Documents/GitHub` →
  `ls: … Operation not permitted`.
- Observation (M5, fresh-context review — two CONFIRMED P1s, both were
  masked by test fixtures that seeded states the real `daemon-finalize`
  cannot produce): (1) RECOVER had no `noop` branch — finalize prints
  `noop` for a meta already in status error/idle, so a failed resume fork
  or fast-failed spawn was silently abandoned forever, breaking the
  3-attempt ladder; fixed by falling back to the meta's own status when
  finalize says noop. (2) RELAY gated on `status=idle`, which nothing sets
  on the park path (a `--no-wait` worker has no finisher) — the pass could
  never fire in the standard flow; and the naive fix (finalize first)
  would have bumped the meta's `updated` field PAST the human's comment,
  destroying the ordering signal. The ordering signal moved to the current
  turn's TRANSCRIPT MTIME — stable once the turn ends, untouched by
  finalize, and it naturally classifies the worker's own pre-park comments
  as trail, not answers. Both re-pinned with production-faithful fixtures
  (the finalize stub now refuses to produce verdicts the real one cannot).
  Evidence: suite RED on exactly the six finding-driven asserts before the
  fixes, GREEN after; reviewer verdict excerpt in Artifacts.
- Observation (M4 tail, coordination): TWO sessions worked this branch in
  parallel. The other session diagnosed the launchd TCC failure first
  (entry above, commit d4cca59) and its interim terminal-session loop
  (pid 87645) is what actually ran the 09:09Z+ ticks — this session
  initially misread those as launchd ticks (`launchctl print` in fact
  showed `runs = 148, last exit code = 126`, every attempt dead at exec).
  That loop later died; the tick now runs as loop pid 25917 from this
  session, and the launchd agent is re-loaded per the recorded
  self-arms-on-grant decision. Dual runners were never a hazard — the
  mkdir lock plus per-pass idempotence is exactly the N-concurrent-sweeps
  property the design claimed, incidentally proven live.
- Observation (M4 tail, live finding): all three implement workers
  delivered their PRs as DRAFTS (#597, #598, #599 — and #596 from the
  earlier dogfood round), and the review sweep deliberately skips drafts,
  so the pipeline stalled at in-review with no reviewer ever attaching.
  No protocol clause governed draft-ness — draft is the SPIKE lane's
  not-for-merge marker; the implement protocol now mandates READY FOR
  REVIEW for the closing PR (clause + pin added; the three PRs were
  marked ready by hand, and the next tick attached their reviewers).
- Observation (M4 tail, live finding — a latent v7.19 one-harness gap):
  after the PRs went ready, all three reviewers spawned and were then
  RETIRED on "bind to ticket failed after 3 attempts". Root cause: a
  claude-species implement worker has no self-finalizer, so its meta
  lingers `status=working` after its turn ends, and board-bind protects a
  working owner as STABLE — refusing to hand the ticket to the reviewer.
  The codex-species workers this loop replaced self-finalized, which is
  why the manual-era reviews never hit it. Fix: review-dispatch gained
  the same normalize-owners-before-bind preflight land-dispatch already
  had (daemon-finalize each working/blocked owner of the linked issue; a
  genuinely live owner stays live and bind still refuses, correctly).
  Validated LIVE: the next tick spawned and BOUND all three reviewers
  (`bound #492/#593/#595 ←`); the bind-orphan sessions from the failed
  round had already self-ended at their barrier timeout. A dedicated
  hermetic case for the preflight is a noted gap — coverage today is the
  live validation plus the review suite's regression green.
- Observation (M5, root cause found and FIXED): the "flaky" reviewing-prs
  suites were not environment-sensitive logic — the assert helpers
  themselves were broken under load. `printf '%s' "$big_log" | grep -Fq`
  under `set -o pipefail`: when grep matches EARLY and exits, printf takes
  SIGPIPE (rc 141), the pipeline reads as failure, and a PRESENT match
  reports FAIL. Every captured failure showed the expected string sitting
  inside the "in:" text plus a "printf: write error: Broken pipe" line —
  the smoking gun. Machine load (this initiative's steady-state worker
  fleet) changes scheduling enough to make grep's early exit beat printf's
  write, which is why quiet machines never saw it. Fixed in all four
  suites (the two pre-existing and the two new ones that copied the
  pattern): the pipe became a herestring (`grep -Fq -- "$2" <<<"$1"`), no
  pipe, no SIGPIPE.
  Evidence: three captured FAILs each contain their expected string
  verbatim in the actual text; stability re-runs green after the swap.
- Observation (M3, pre-arm registry inspection): the live registry held a
  `working` meta bound to ticket #489, whose ticket is `in-review` — the
  worker finished long ago (nothing finalizes an implement worker's meta
  when its ticket moves on), and the original slot counter would have
  counted it against the cap FOREVER. Fixed: `_slots_used` joins registry
  status with board state and counts only workers whose ticket is still
  `ready-for-agent`/`in-progress`; pinned by the "stale working meta on an
  in-review ticket does not eat a slot" assert.
  Evidence: registry dump showed `('489', '489-report-ia', 'working', …)`
  with #489 in-review on the live board.

## Decision Log

- Decision: sweep-first transport; the Actions runner path stays and arms
  itself when ida-solution#302 resolves.
  Rationale: the runner is blocked on an org admin (external dependency);
  a local five-minute tick needs nobody's permission and covers every lane.
  Latency loss vs 30s polling is irrelevant — the bottleneck is review
  bandwidth, not dispatch latency (comparison doc §9).
  Date/Author: 2026-07-18 / human + agent (grill).
- Decision: the board is the only truth for dispatch — every ELIGIBLE
  ticket (ready-for-agent, all blockers done, not an epic) is auto-
  dispatched in priority order up to the cap. No new "hold" label: a human
  who wants a ticket held moves it to a park state themselves; machines
  never model human holds.
  Rationale: Symphony's core lesson (humans manage work, not sessions);
  a hold label would put a human-intent shadow state into the machine path.
  Date/Author: 2026-07-18 / human (grill).
- Decision: implement/spike concurrency cap 5 (`IMPLEMENT_MAX_CONCURRENT`).
  Rationale: the human chose aggressive-start because the review loop is
  also automated — implement output does not queue on human review anymore.
  Date/Author: 2026-07-18 / human (grill).
- Decision: keep the existing full-power `gh` keychain token in worker env;
  no fine-grained PAT at this phase.
  Rationale: human decision at the grill, accepting FD-6's noted exposure.
  Date/Author: 2026-07-18 / human (grill).
- Decision: arm both merge tiers — `AUTO_MERGE_ENABLED=true` (review
  worker self-merges the trivial tier) and `LAND_ENABLED=true` (land worker
  merges for real, gated on a human Approve or `land` label).
  Rationale: the human's remaining gesture should be the pure decision
  (Approve); everything mechanical after it belongs to workers (FD-4).
  Date/Author: 2026-07-18 / human (grill).
- Decision: the tick is a NEW script `board-sweep.sh` beside
  `board-reconcile.sh`, not a write-enabled growth of reconcile (which the
  comparison doc §9 sketched).
  Rationale: reconcile's header contract — "read-only catch-up report;
  NEVER writes anything" — is load-bearing for the wake ritual (a human can
  always run it safely). The sweep composes reconcile's checks and adds
  write actions under its own name instead of mutating a read-only tool's
  contract.
  Date/Author: 2026-07-18 / agent.
- Decision: unified bounded recovery — a bound worker in status `error`,
  and a status `working` worker whose transcript has been silent past the
  stall timeout, both get the same verb: `daemon-resume.sh` with a short
  continuation nudge, a shared per-daemon lifetime cap of 3 sweep-initiated
  resumes (`sweep_recoveries` meta field), then park `needs-human` with an
  orientation note.
  Rationale: our recovery verb is resume (context intact — proven 3× in the
  codex shakedown), not Symphony's re-dispatch-fresh; folding stall into the
  same bounded counter avoids a second policy. Real (non-transient) failures
  hit the cap in three ticks and park — they never loop.
  Date/Author: 2026-07-18 / agent.
- Decision: board-driven cancel fires only on TERMINAL ticket states (done,
  wontfix, or the issue closed) while a bound worker is live-working; park
  states never kill a worker.
  Rationale: FD-9 "park = pause, not death" — a parked worker's session is
  deliberately kept resumable; killing it would undo the answer-relay
  design. Terminal states are the only states that mean "this work must
  stop".
  Date/Author: 2026-07-18 / agent (FD-8 recorded design).
- Decision: the land pass invokes `land-dispatch.sh` only when NO
  `land-pr-<n>` registry meta exists for that PR — one sweep-initiated land
  attempt per PR; a dead lander is a wake-ritual item, not a retry loop.
  Rationale: land-dispatch's own dedupe treats a finished lander as "fresh
  signal → respawn", which is right for an explicit human invocation but
  would loop a persistently-failing lander from cron. Bounded beats looping;
  reconcile already flags dead landers.
  Date/Author: 2026-07-18 / agent.
- Decision: answer-relay (L2) covers `needs-human` tickets only, and the
  trigger is a NEW last comment that is not the park note and not an
  `[answers]` comment, on a ticket with a bound resumable session; the verb
  is `board-answer.sh <n> --posted`, backgrounded.
  Rationale: board-answer's contract is the needs-human relay; needs-info
  and interactive-preferred parks are wake-ritual work by design. The
  --posted mode means the human just comments on the ticket (from phone or
  board) and the sweep does the rest — TECH-DEBT #10's L2 exactly.
  Date/Author: 2026-07-18 / agent.
- Decision: implement-dispatch performs spawn → bind sequentially with no
  startup barrier (unlike review/land dispatch).
  Rationale: parity with the manual dispatch ritual it mechanizes — the
  implement worker protocol has no bind-barrier step; its first board write
  is the gate verdict, and board-bind strips any stale owner. The barrier
  machinery exists in review/land dispatch because those protocols wait on
  a bind_ready file; adding one here would change the worker protocol for
  no observed failure (constraint-minimization golden rule).
  Date/Author: 2026-07-18 / agent.
- Decision: the M5 whole-branch review runs as a native fresh-context
  reviewer subagent instead of `codex exec review`.
  Rationale: the human declined the codex launch at the tool boundary
  mid-execution; the standing instruction for that case is self/native
  review as the substitute. The reviewer gets the full diff, merge-base,
  and a description of every intended invariant to attack.
  Date/Author: 2026-07-18 / human (tool rejection) + agent.
- Decision: the final branch is opened as a PR to main and left unmerged;
  the human merges.
  Rationale: explicit human instruction at the grill ("메인에 PR 오픈만
  하고 머지는 대기") — the initiative rewires their own attention surface,
  so the final diff is theirs to admit.
  Date/Author: 2026-07-18 / human (grill).
- Decision: the concurrency counter and the per-ticket dedupe both read the
  REGISTRY first (bound metas in status working/blocked/error), the board
  state second.
  Rationale: a just-spawned worker's meta exists before its gate verdict
  moves the ticket off `ready-for-agent` — counting by ticket state alone
  would re-dispatch during that pre-gate window. Durable meta-first
  counting closes the race without any barrier.
  Date/Author: 2026-07-18 / agent (design-time analysis).
- Decision: the relay pass records the relayed comment id in the daemon
  meta (`relayed_comment`) before invoking board-answer, and the sweep log
  self-truncates at 1 MB.
  Rationale: the park-state dedupe alone has a window — if board-answer
  dies after posting its pointer but before the in-progress transition, the
  next tick would re-relay the same comment; unbounded cron logs are a slow
  disk leak. Both guards are cheap and durable.
  Date/Author: 2026-07-18 / agent (design-time analysis).

## Outcomes & Retrospective

**Outcome.** The manual-dispatch era of the board pipeline is over on this
branch: one mechanical five-minute tick (`board-sweep.sh`) now recovers,
cancels, dispatches (implement + review), lands on the human's Approve,
and relays park answers — importing Symphony's orchestrator *functions*
with zero residency, exactly as `2026-07-11-symphony-comparison.md` §9
prescribed. It is not merely built but LIVE: the launchd agent is armed on
ida-solution, tick 1 dispatched all three eligible tickets and attached a
reviewer, all three workers passed the routed Ticket Gate with substantive
verdicts (also the v7.21.x schema's first live exercise), and tick 2
dispatched nothing (idempotence). TECH-DEBT items 1, 2 (NA-verified), and
10-L2 closed.

**What the process caught that authoring did not.** Three of the four
serious defects were found by evidence practices, not by writing care:
the pre-arm registry inspection caught the slot-leak (stale `working` meta
on an in-review ticket), and the fresh-context review caught both P1 logic
holes (RECOVER's finalize-noop fallthrough; RELAY's impossible idle gate
plus the updated-timestamp self-destruction). The shared root cause of the
P1s is worth keeping: **test fixtures that seed states the real subsystem
cannot produce make load-bearing asserts vacuous** — the fix included
making the finalize stub refuse impossible verdicts, which is the durable
guard.

**Remaining, by design or deferral.** The launchd timer itself is the open
item: TCC blocks a launchd bash from touching `~/Documents` (script AND
repos), so every timer attempt died at exec — durable arming needs one
human gesture (Full Disk Access for the tick's interpreter, or hosting the
repos outside ~/Documents); a login-session loop carries the tick
meanwhile. The Actions runner path stays blocked on ida-solution#302; templates
for all three lanes are shipped and arm themselves when it resolves. After
this branch merges and releases, repoint the armed plist's
`DOPERPOWERS_HOME` from the worktree to the marketplace path. L3 (BOARD.html
session affordances) remains open in TECH-DEBT #10.

## Context and Orientation

This repository (`doperpowers`) is a multi-harness agent plugin; its
product is skills under `skills/`. Two skills matter here:

- `skills/issue-tracker/` owns "the board": a consumer repo's GitHub Issues,
  driven by labels, with a Python schema (`scripts/_board.py`) enforcing a
  legal state graph. States: `ready-for-agent` (dispatchable pre-spec),
  `in-progress`, `in-review` (PR open), three park states (`needs-human`,
  `needs-info`, `interactive-preferred`), terminal `done` / `wontfix`.
  `scripts/board-list.sh` prints every ticket in dispatch order and tags
  dispatchable ones `ELIGIBLE` (ready-for-agent, every `blocked_by` ticket
  done, not an epic); `_board.py` exposes the same predicate as
  `eligible(tickets, tid)`. `scripts/board-transition.sh` applies state
  changes (legality + notes enforced), `board-bind.sh <uuid> <n>` binds a
  worker session to a ticket (stripping old owners), `board-answer.sh <n>
  --posted` resumes a parked ticket's bound session with a pointer to
  answers already commented on the ticket, and `board-reconcile.sh` is a
  READ-ONLY catch-up report (its header says "NEVER writes anything" — this
  plan keeps that true).
- `skills/orchestrating-daemons/` owns the worker substrate. A "daemon" is
  a detached `claude --bg` session; the registry is
  `~/.claude/orchestrating-daemons/<uuid>.json` metas with fields including
  `uuid` (stable identity), `current` (latest turn's session id), `name`,
  `status` (`working`/`idle`/`blocked`/`error`/`retired`), `cwd`,
  `worktree`, `model`, `settings`/`effort` (gateway route), `ticket`
  (written by board-bind), `updated`. `daemon-spawn.sh [--no-wait] <name>
  <task> [cwd] [worktree] [model]` spawns one (`--no-wait` returns as soon
  as the session uuid materializes — built for cron/runner dispatch);
  `daemon-resume.sh <uuid> <msg>` forks a continuation turn (blocks for the
  whole turn — always background it); `daemon-finalize.sh <uuid>`
  normalizes a finished-but-lingering `working` meta to `idle` and answers
  `live` for a genuinely running turn; `daemon-retire.sh` ends a daemon
  without deleting worktrees.

Worker species: implement/spike workers are spawned by the DISPATCH RITUAL
(issue-tracker `SKILL.md` "The dispatch ritual") — render
`skills/implementing-tickets/references/worker-bootstrap.md` substituting
`{{ROLE}}`, `{{ISSUE_NUMBER}}`, `{{ISSUE_URL}}`, `{{ISSUE_TITLE}}`,
`{{REPO}}`, `{{BOARD_SCRIPTS}}`, `{{ENGINE_NAME}}`, `{{PROTOCOL_FILE}}`,
`{{DECOMPOSE_DOC}}`, `{{EXECUTION_BLOCK}}`, `{{ISSUE_BODY}}`,
`{{REPO_FACTS}}`, then `daemon-spawn.sh` in a worktree, then `board-bind`.
The ENGINE is a MODEL ROUTE, not a harness: `codex` (default) = the clodex
gateway (env `DAEMON_CLAUDE_SETTINGS=${CLODEX_SETTINGS:-~/.claude/clodex-settings.json}`,
`DAEMON_CLAUDE_EFFORT=${CLODEX_EFFORT:-xhigh}`, model arg `fable` routed
through a local proxy to GPT models); `claude` = plain Claude models, no
gateway env. An `engine:*` ticket label overrides `$WORKER_ENGINE` which
overrides the default. Review workers are spawned by
`skills/reviewing-prs/scripts/review-dispatch.sh <pr>|--sweep` (the sweep
mode iterates unbound open PRs; a per-PR 3-consecutive-failure cap guards
respawn loops); land workers by
`skills/reviewing-prs/scripts/land-dispatch.sh <pr>` behind an authority
gate (PR labeled `confident-ready` AND review decision APPROVED or a `land`
label) and the `LAND_ENABLED` staged flag (false = dry-run). The trivial
self-merge tier of the review worker is behind `AUTO_MERGE_ENABLED`
(default off). Both flags are ARMED (set true) by this plan, in the sweep's
environment only.

The consumer repo for the live shakedown is
`/Users/new/Documents/GitHub/ida-solution` (board repo
`IDA-solution/ida-solution`). Its `.github/workflows/pr-review-dispatch.yml`
already fires on PR events but every run dies queued: the self-hosted
runner labeled `claude-review` is unregistered (ida-solution#302, org admin
required). This plan does not wait for it.

Known platform hazard: on macOS, daemons launched from cron/launchd
contexts can lose TCC (privacy) grants — the fleet previously died en masse
from a TCC-lost daemon (see memory note "Daemon TCC chdir crash"). The
worker processes themselves are owned by the resident
`com.user.claude-code-daemon` LaunchAgent (which has its own watchdog), so
the sweep's `claude --bg` spawns hand ownership to that daemon; the live
shakedown must verify a cron-context spawn survives. If it does not, the
documented fallback is running the sweep from a launchd USER agent (Aqua
session context) rather than crontab — `sweep-setup.md` documents both.

Reference reading (already summarized above; open only if implementing
details drift): `docs/doperpowers/2026-07-11-symphony-comparison.md` §2.1,
§9 (the sweep-tick checklist this plan implements),
`docs/doperpowers/TECH-DEBT.md` items 1, 2, 5, 10.

## Plan of Work

**New: `skills/implementing-tickets/scripts/implement-dispatch.sh`** (M1) —
the mechanical implement/spike dispatcher, the exact automation of the
dispatch ritual, callable two ways: `implement-dispatch.sh <issue-number>`
(triggered — future issue-event workflow, or a human) and
`implement-dispatch.sh --sweep` (dispatch every ELIGIBLE ticket in dispatch
order until the cap). Per ticket it: re-verifies eligibility from a fresh
board snapshot (`_board.py eligible()`); dedupes — skip when any registry
meta binds this ticket with status `working`/`blocked`/`error` (an `idle`
bound session does NOT block: re-dispatch is fresh context by doctrine, and
board-bind strips the old owner); resolves the engine (label → env →
`codex`); renders `worker-bootstrap.md` with every placeholder exactly as
the ritual specifies (ROLE=SPIKE for category `spike`, PROTOCOL_FILE =
spike protocol or implementing-tickets SKILL.md, REPO_FACTS from
`origin/<default-branch>`, EXECUTION_BLOCK from
`references/engine-blocks/execution.md`, DECOMPOSE_DOC pointer); aborts if
any `{{[A-Z_]+}}` survives substitution (the strict-render check, import
candidate #6); spawns `daemon-spawn.sh --no-wait "<n>-<slug>" … <repo>
"<n>-<slug>" [fable]` with gateway env on the codex route; binds
`board-bind.sh <uuid> <n>` (3 attempts, retire on failure — a worker that
cannot be bound cannot be answer-relayed). The cap counts registry metas
whose `ticket` is set, whose name does not match `review-pr-*`/`land-pr-*`,
and whose status is `working`/`blocked`/`error` — durable state only.
Env: `LOCAL_REPO`, `BOARD_REPO`, `IMPLEMENT_MAX_CONCURRENT` (default 5),
`WORKER_ENGINE`, `CLODEX_SETTINGS`, `CLODEX_EFFORT`, `IMPLEMENT_MODEL`,
`BOARD_SCRIPTS`/`DAEMON_SCRIPTS`/`DAEMON_HOME` overrides for tests.

**New: `skills/issue-tracker/scripts/board-sweep.sh`** (M2) — the tick.
Single-instance via `flock` on `$DAEMON_HOME/board-sweep.lock` (a held lock
exits 0 silently). Appends to `$DAEMON_HOME/sweep.log`, self-truncating at
1 MB. Passes, in order, each independently guarded so one failing pass
never stops the rest:

1. RECOVER — for every meta bound to a ticket whose state is
   `ready-for-agent`/`in-progress`: `daemon-finalize` normalize; then
   status `error`, or status `working` with a transcript silent longer than
   `SWEEP_STALL_MINUTES` (default 45): if `sweep_recoveries` < 3, increment
   it and background `daemon-resume.sh <uuid> "<continuation nudge>"`; else
   park the ticket `needs-human` with an orientation note naming the daemon
   and the failure shape.
2. CANCEL — for every live-working meta bound to a ticket in `done` /
   `wontfix` / closed: `daemon-retire.sh`, then a `[board]` comment on the
   issue naming the termination (FD-8's recorded design; workers' worktrees
   are never deleted).
3. DISPATCH — `implement-dispatch.sh --sweep`.
4. REVIEW — `review-dispatch.sh --sweep` (existing catch-up mode; its own
   dedupe and failure caps apply).
5. LAND — for each open PR labeled `confident-ready` whose review decision
   is APPROVED or which carries a `land` label, and for which NO
   `land-pr-<n>` meta exists: `land-dispatch.sh <n>` (one sweep attempt per
   PR, per the Decision Log).
6. RELAY — for each `needs-human` ticket with a bound session:
   finalize-normalize it (a `--no-wait` worker that parked lingers
   `working`; only a genuinely ended turn is resumable), then relay when
   the newest issue comment postdates the current turn's TRANSCRIPT MTIME
   (the turn-end signal — stable, and unlike the meta's `updated` field
   not bumped by the finalize itself), is not machine-prefixed
   (`[answers]`/`[board]`/`[gate]`/`[findings]`), and differs from
   `relayed_comment`. Record the comment id in the meta, then background
   `board-answer.sh <n> --posted`.
7. REPORT — `board-reconcile.sh` output into the log; `CLOSE?` candidates
   surface there for the human's wake.

Env additions: `SWEEP_STALL_MINUTES`, `AUTO_MERGE_ENABLED`, `LAND_ENABLED`
(exported through to the lane dispatchers), plus everything
implement-dispatch takes.

**Prose + templates** (M3) — issue-tracker `SKILL.md`: the dispatch ritual
notes the sweep as its mechanical invoker (the ritual body is UNCHANGED —
its own text predicted "the next phase replaces step 3's invoker");
`skills/issue-tracker/references/sweep-setup.md` (new): arming instructions
— launchd UserAgent plist template (StartInterval 300) and crontab
alternative, environment block (`LOCAL_REPO`, `AUTO_MERGE_ENABLED=true`,
`LAND_ENABLED=true`, `IMPLEMENT_MAX_CONCURRENT=5`, gateway defaults), TCC
caveat, un-arming (`launchctl unload`). Runner-path templates for the day
ida-solution#302 resolves: `skills/implementing-tickets/references/`
`issue-dispatch.yml` (issue labeled/reopened → `implement-dispatch.sh <n>`,
same security posture as pr-review-dispatch.yml: no checkout,
`permissions: {}`, numeric interpolation only, actor allowlist) and
`skills/reviewing-prs/references/land-on-approve.yml`
(pull_request_review submitted approved → `land-dispatch.sh <n>`).
`docs/doperpowers/TECH-DEBT.md`: strike items 1 and 10-L2 as shipped, item
2 verified not-applicable on the one-harness path (gh token capture was
codex-CLI spawn machinery; `claude --bg` workers reach gh via keychain),
item 5 note that templates now cover all three lanes. Test pins in
`tests/implementing-tickets/test-protocol-content.sh` for the new prose.

**Tests** (M1/M2) — `tests/implementing-tickets/test-implement-dispatch.sh`
and `tests/issue-tracker/test-board-sweep.sh`, hermetic in the style of
`tests/reviewing-prs/test-review-dispatch.sh`: a temp `DAEMON_HOME`, stub
`gh`/`daemon-spawn.sh`/`daemon-resume.sh`/`daemon-retire.sh`/`board-*.sh`
on PATH recording their argv, fixture board snapshots. RED first for every
load-bearing behavior: cap enforcement, dedupe against working/error metas,
idle-does-not-block, strict-render abort, engine resolution order, spike
routing, recover cap → park, cancel only on terminal states, land
one-attempt guard, relay ordering guard, flock reentry.

## Concrete Steps

All commands from the worktree root
`/Users/new/Documents/GitHub/doperpowers/.claude/worktrees/unattended-sweep`.

Run the new suites and the neighbors they touch:

    tests/implementing-tickets/test-implement-dispatch.sh
    tests/issue-tracker/test-board-sweep.sh
    tests/implementing-tickets/test-protocol-content.sh
    tests/issue-tracker/test-board-scripts.sh
    tests/reviewing-prs/test-review-dispatch.sh
    tests/reviewing-prs/test-land-dispatch.sh
    tests/skill-links/test-cross-doc-refs.sh
    scripts/lint-shell.sh

Each prints an explicit all-passed line (e.g. `all tests passed`,
`all cross-doc references resolve`); any FAIL line is a stop.

Arm the shakedown (M4) — the plist lives in this branch at
`infra/board-sweep/com.user.doperpowers-board-sweep.plist` with
`DOPERPOWERS_HOME=<this worktree>` so the un-merged branch is what runs.
Per sweep-setup.md, the first tick is run BY HAND and verified before the
timer is trusted:

    DOPERPOWERS_HOME=<worktree> LOCAL_REPO=<ida-solution clone> \
      AUTO_MERGE_ENABLED=true LAND_ENABLED=true IMPLEMENT_MAX_CONCURRENT=5 \
      "$DOPERPOWERS_HOME/skills/issue-tracker/scripts/board-sweep.sh"

    cp infra/board-sweep/com.user.doperpowers-board-sweep.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.user.doperpowers-board-sweep.plist
    tail -f ~/.claude/orchestrating-daemons/sweep.log

Expected first-tick log shape (indented example):

    [sweep 2026-07-18T12:40:02Z] RECOVER: 0 acted
    [sweep] CANCEL: 0 acted
    [sweep] DISPATCH: spawned #593 (impl, engine=codex) … spawned #595 …
    [sweep] REVIEW: sweep — no unbound open PRs
    [sweep] LAND: no approved confident-ready PRs
    [sweep] RELAY: 0 relayed
    [sweep] REPORT: … board-lint OK

Un-arm: `launchctl unload …` (documented in sweep-setup.md).

## Validation and Acceptance

Mechanical: all eight commands above green. Behavioral (the acceptance that
matters): with the tick armed on ida-solution and two ELIGIBLE tickets on
the board, within one tick both tickets have bound workers and `[gate]`
comments with NO human dispatch command; a consecutive tick dispatches
nothing new (dedupe); when a worker's PR opens, a review worker attaches
within one tick; a human Approve on a `confident-ready` PR produces a land
worker within one tick; killing a worker's turn mid-flight produces a
sweep-initiated resume next tick, and after three induced failures the
ticket parks `needs-human` with an orientation note; commenting an answer
on a `needs-human` ticket with a bound session resumes that worker within
one tick.

## Idempotence and Recovery

Every pass re-derives its work-list from GitHub + the registry each tick
and is guarded by durable markers (bound metas, `sweep_recoveries`,
`relayed_comment`, land's no-meta rule), so N overlapping or repeated
ticks are safe — flock is an optimization, not a correctness requirement.
Un-arming is one `launchctl unload`; nothing else needs cleanup. The
sweep never deletes worktrees, never force-pushes, never touches terminal
tickets except to comment. If a pass misfires, the board and registry
show exactly what it did (`[board]` comments, meta fields, sweep.log).

## Interfaces and Dependencies

In `skills/implementing-tickets/scripts/implement-dispatch.sh`:

    implement-dispatch.sh <issue-number>   # triggered
    implement-dispatch.sh --sweep          # cap-bounded catch-up
    env: LOCAL_REPO BOARD_REPO IMPLEMENT_MAX_CONCURRENT=5 WORKER_ENGINE
         CLODEX_SETTINGS CLODEX_EFFORT IMPLEMENT_MODEL
         BOARD_SCRIPTS DAEMON_SCRIPTS DAEMON_HOME (test seams)
    exit 0 on skip/success per PR-review-dispatch convention; nonzero only
    on structural errors (missing template, unparseable board)

In `skills/issue-tracker/scripts/board-sweep.sh`:

    board-sweep.sh            # one tick; flock-guarded; exit 0 always
                              # unless the environment itself is broken
    env: everything above plus SWEEP_STALL_MINUTES=45
         AUTO_MERGE_ENABLED LAND_ENABLED REVIEW_SCRIPTS (test seam)

Registry meta fields added (via `_meta_set`, both scripts):
`sweep_recoveries` (int as string), `relayed_comment` (comment node id).

Dependencies: bash, python3, jq, gh (authenticated), flock, and the
existing skill scripts named above. No new external services, no resident
process, no state files outside `$DAEMON_HOME`.

## Milestones

**M1 — the implement dispatcher.** At the end of this milestone a single
command dispatches a real ticket exactly as the manual ritual would, and a
`--sweep` invocation on a fixture board dispatches only what the cap and
dedupe allow. Proof: the hermetic suite (RED first), then one manual
triggered dispatch against a scratch issue during M4 rehearsal.

**M2 — the tick.** At the end, one command runs all seven passes against
stubs, acting only where the fixtures say it must, and its log names every
action and every skip with a reason. Proof: hermetic suite (RED first) —
including the "one failing pass never stops the rest" guard (a stub lane
dispatcher that exits 1 while later passes still run).

**M3 — the operator surface.** At the end, a novice can arm/un-arm the
sweep from `sweep-setup.md` alone, and the runner-day workflow templates
exist for all three lanes. Proof: protocol-content pins + cross-doc lint
green; a dry `bash -n` + shellcheck pass over the plist/crontab snippets.

**M4 — the live shakedown (the evidence gate).** Arm on ida-solution from
this worktree. Observe the acceptance behaviors above on the real board —
the two ELIGIBLE tickets (#593, #595 — the human's earlier manual deferral
is superseded by the board-is-truth decision; they are the shakedown load),
cap, dedupe, review auto-attach, and TCC survival of the cron-context
spawn. Any failure is fixed test-first before proceeding. Evidence
(log excerpts, board timeline) lands in Artifacts.

**M5 — review and handoff.** Whole-branch `codex exec review --base main`
from a disposable clone (never in-place beside sibling repos); findings
fixed; PR opened to main with the shakedown evidence in the body; the PR
is NOT merged — the human merges. Retrospective written.

## Artifacts and Notes

Shakedown evidence (M4, 2026-07-18, all verbatim from
`~/.claude/orchestrating-daemons/sweep.log` and the live board):

    [sweep 2026-07-17T21:48:04Z] tick — repo=IDA-solution/ida-solution
    [sweep] RECOVER: 0 acted        (finalize normalized #490's stale
                                     working meta to idle — binding kept)
    [sweep] CANCEL: 0 acted
    dispatched #492 → 492-m4-7-ep-52 [4cb35bad-…] engine=codex role=IMPLEMENT
    dispatched #593 → 593-fix-types-dailytask-typescript [fd4db6b7-…] …
    dispatched #595 → 595-fix-next-generate-plan-route-han [5db9e748-…] …
    daemon spawned (no-wait): review-pr-574  [dcd582d5 / …]
    [sweep] LAND: 0 acted
    [sweep] RELAY: 0 acted
    FAIL #573: needs-human without a note     (REPORT surfacing a real
    board-lint: 304 issue(s), 1 FAIL, 24 WARN  wake-ritual item)
    [sweep] tick complete

Worker registry meta for #492 confirmed the gateway route persisted:
`settings=True model=fable status=working`. Within ~10 minutes all three
workers wrote substantive gate verdicts and self-transitioned:

    #492 → in-progress · "[gate] pass — codex/DIRECT: 기존 완료·시간 비율
      데이터와 현행 UI 토큰으로 새 제품 결정 없이 … 한 단위로 구현 가능"
    #593 → in-progress · "[gate] pass — codex/DIRECT: 동일 타입…중복 선언
      한 세트만 제거하는 단일 파일 기계적 수정…"
    #595 → in-progress · "[gate] pass — codex/DIRECT: Route Handler를 얇은
      HTTP 어댑터로 만들고 … 단일 목적 작업"

This was simultaneously the first live exercise of the ROUTED Ticket Gate
(v7.21.x board schema): the workers resolved
`{{BOARD_SCRIPTS}}/../references/ticket-gate.md` from the dispatched
bindings and produced classification-grade verdicts.

Tick 2 (manual, minutes later): `RECOVER: 0 · CANCEL: 0 · DISPATCH: (no
eligible tickets — all three now in-progress) · #574: skip active
reviewer · LAND: 0 · RELAY: 0` — nothing double-dispatched. (An earlier
draft of this section credited launchd with clean timer ticks — wrong:
every launchd attempt failed at exec with TCC's "Operation not permitted";
see the M4-tail Surprises entry. The ticks that kept running came from a
login-session context.)

Fresh-context review verdict (M5, before fixes):

    [P1] RECOVER treats finalize `noop` as healthy — error/idle metas
         never recover … the recovery ladder stops at attempt 1
    [P1] RELAY gates on `status=idle`, which nothing sets after a
         needs-human park … the pass can never fire in the standard flow
    [P2] errexit makes the DEFAULT_BRANCH="main" fallback unreachable
    [P3] Sweep never creates DAEMON_HOME; first arming no-ops
    Verdict: patch is incorrect (confidence 0.85) — "both are masked by
    test fixtures that seed states the real daemon-finalize semantics
    cannot produce."

All four fixed test-first; the suite showed RED on exactly the six
finding-driven asserts before the fixes and full green after.

## Revision Notes

- 2026-07-18 (author): initial plan.
- 2026-07-18 (M5): RELAY's design changed after the fresh-context review —
  the resumability gate is finalize-normalize (not a pre-existing `idle`
  status, which nothing produces on the park path) and the ordering signal
  is the current turn's transcript mtime (not the meta's `updated`, which
  the normalize itself bumps). Plan of Work pass 6, the Surprises entry,
  and the Decision Log record the why; the M2 suite's fixtures now refuse
  to seed states the real daemon-finalize cannot produce.
