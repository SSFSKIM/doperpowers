# Symphony ↔ doperpowers board pipeline — comparative analysis

> **Date:** 2026-07-11 (day after the codex-workers live shakedown; v7.11.0 cut).
> **Purpose.** OpenAI's Symphony and this fork's board pipeline are independent
> answers to the same problem: ticket-driven orchestration of coding agents,
> with human attention as the bottleneck. This doc maps the two systems
> component-by-component, judges superiority per axis (not overall), lists
> what is worth importing, and isolates the **non-trivial forked decisions**
> (§6) where both sides made a deliberate, defensible, *diverging* bet — the
> discussion agenda.
>
> **Sources — Symphony** (local mirror:
> `~/documents/github/agent-harness/docs/symphony-original/`):
> - `SPEC.md` — Symphony Service Specification, Draft v1, language-agnostic
>   (upstream: `github.com/openai/symphony/blob/main/SPEC.md`). Cited as
>   **SPEC §N**.
> - `WORKFLOW.md` — the reference worker contract (Linear + codex app-server,
>   high-trust posture). Cited as **WF step N**.
> - Blog: *"Codex 오케스트레이션을 위한 오픈소스 사양: Symphony"*
>   (openai.com/index/open-source-codex-orchestration-symphony, Kotliarskyi /
>   Zhu / Brock). Cited as **Blog**.
>
> **Sources — ours:**
> - Skills: `skills/issue-tracker/`, `skills/implementing-tickets/`,
>   `skills/reviewing-prs/`, `skills/orchestrating-daemons/` (+ their
>   `references/` protocols and engine blocks, `scripts/`).
> - Design docs: `docs/doperpowers/specs/2026-07-09-implement-worker-autonomy-design.md`,
>   `specs/2026-07-08-pr-review-loop-design.md`,
>   `specs/2026-07-10-codex-workers-design.md`.
> - Live evidence: `docs/doperpowers/2026-07-10-codex-workers-shakedown.md`
>   (SD-1/SD-3 passed, FU-3…FU-7), `docs/doperpowers/TECH-DEBT.md` (T1…T3).

---

## 0. Verdict up front

The two systems attack the same bottleneck from opposite directions:

- **Symphony reduces *supervision* cost.** An industrial scheduler — polling,
  claims, retry queue, stall detection, continuation turns, concurrency caps —
  with ALL work semantics delegated to one repo-owned prompt file. The tracker
  is dumb; the runtime is rich.
- **Ours reduces *review* cost.** A semantics-rich board — pre-code gate, three
  park states with a who-unparks discriminant, decomposition doctrine, a
  separate adversarial review species, tiered merge authority — with the
  runtime deliberately thin (no resident process; the board IS the state).

Per-axis superiority is clear and split:

| axis | winner | evidence anchor |
|---|---|---|
| Liveness / execution automation | **Symphony** | our T1/T2 tech-debt list ≈ their feature list (§2.1) |
| Work semantics (gate, parks, decomposition, review) | **ours** | Symphony's contract has no pre-code gate, one overloaded park, no decomposition criterion, no self-review (§2.3) |
| Safety posture | **ours** | SPEC punts to "implementation-defined"; reference impl is `approval_policy: never` (§2.6) |
| Engine/species extensibility | **ours** | app-server locks Symphony to codex; we run 2 species × 2 engines on one registry (§2.5) |
| Evidence richness *for humans* | **Symphony** | workpad, reproduction-first, video walkthroughs (§2.3, §4) |
| Operability at team/monorepo scale | **Symphony** | dashboard, token accounting, SSH pool, land loop (§2.7, SPEC App. A) |
| Operability for one person × N repos | **ours** | zero resident service; GitHub is the dashboard |

The right move is **not** to Symphony-ize (resident orchestrator + app-server)
but to import their liveness as a *watchdog* and their evidence richness as
*contract clauses*, keeping the no-orchestrator architecture (§4, §5).

---

## 1. The two bets

**Symphony's origin** (Blog): a team that mandated "no human-written code in
the repo" hit its next bottleneck — context switching. Engineers could drive
3–5 interactive Codex sessions before productivity collapsed: *"에이전트는
빨랐지만 시스템의 병목은 인간의 주의력이었습니다."* Their answer: make the
issue tracker the control plane; every open ticket gets a continuously running
agent; humans manage work, not sessions. Notably, their own trajectory bent
toward autonomy: early versions had the harness own GitHub integration and
expected Codex to only edit code — *"하지만 그 접근은 너무 제한적이었습니다"* —
and they ended at *"엄격한 전이 대신 에이전트에게 목표를 부여"* (give goals,
not transitions).

**Our origin** (`2026-07-09-implement-worker-autonomy-design.md`): the same
no-judge conclusion, arrived at from the review side — nobody sits between a
worker and the board; escalation is a park state, not a message to a
supervisor. But where Symphony's answer to a mis-specified ticket is cheap
disposal (*"에이전트가 뭔가를 잘못하더라도 … 비용은 거의 0"* — Blog), ours is
prevention: the Ticket Gate makes under-specified work park *before* code
exists, because in a production repo the human's PR-review attention is the
scarce resource a wrong PR burns.

Symphony's endpoint (goals + tools, agent writes the tracker) is our starting
axiom; we add hard gates only where human values are at stake (taste forks,
terminal states, merge tiers). Their lesson trajectory validates the doctrine.

---

## 2. Component-by-component

### 2.1 Orchestrator (SPEC §7–8, §14) vs no-orchestrator (issue-tracker ritual)

**Symphony.** A resident service owns a poll tick (default 30s): reconcile →
validate → fetch candidates → dispatch until slots exhausted (SPEC §8.1).
Internal claim states (`Unclaimed/Claimed/Running/RetryQueued/Released`, §7.1)
live in a single-authority in-memory map. Failure-driven retries back off as
`delay = min(10000 * 2^(attempt-1), max_retry_backoff_ms)` (§8.4); clean exits
get a 1s *continuation retry* so the same ticket is re-checked and re-entered
until it leaves the active states (§7.1: *"A successful worker exit does not
mean the issue is done forever"*). Stall detection kills sessions silent past
`stall_timeout_ms` (default 5m, §8.5A). Reconciliation refreshes tracker state
for every running issue each tick and **terminates workers whose ticket left
the active set** (§8.5B) — the human cancels work by moving a ticket. Restart
recovery is deliberately stateless: *"No retry timers are restored … Service
recovers by … fresh polling"* (§14.3); their own roadmap lists "Persist retry
queue … across restarts" as a TODO (§18.2).

**Ours.** No resident process, as doctrine: *"There is NO orchestrator …
escalation targets are the board itself … and the human on their next wake"*
(implement-worker-protocol.md; issue-tracker SKILL.md "There is no
orchestrator-judge"). Scheduler state maps onto durable stores: claim =
`status:in-progress` label; running = registry entry + pid/session liveness;
retry queue = **nothing** (T1-1: transient-death recovery is manual — the
shakedown recovered 3 transient deaths only because an operator ran
`codex-resume.sh`); reconciliation = `board-reconcile.sh` (read-only,
human-run) + the review sweep cron. Dispatch is a mechanical ritual (render →
spawn → bind, write nothing) that an issue-event trigger will invoke next
phase without changing.

**Judgment.** Symphony's orchestrator value decomposes almost entirely into
*liveness*, not judgment — dead→retry, silent→kill, ineligible→stop. Liveness
is importable as a watchdog (bounded auto-resume + sweep + caps: exactly
T1's planned answer) without accepting the costs: a per-team service to build
and babysit, volatile scheduler state, and a resident process standing where
our doctrine says nobody stands. What we genuinely lack today and they have:
**(a)** automatic transient recovery (T1-1), **(b)** stall detection,
**(c)** board-driven cancellation of a running worker (→ FD-8),
**(d)** concurrency caps (`max_concurrent_agents`, per-state caps — SPEC
§5.3.5; required for our unattended phase). What we have and they don't:
scheduler state that survives restarts *because it never lived in memory*,
and a claim/verdict trail (`[gate]`, `[board]` comments) visible to the whole
team instead of one devbox's RAM.

### 2.2 Workflow loader + config layer (SPEC §5–6) vs plugin-owned protocol

**Symphony.** One repo-owned `WORKFLOW.md`: YAML front matter (typed config —
tracker, polling, workspace, hooks, agent, codex; `$VAR` indirection; defaults;
validation, §5.3/§6.1) + a Liquid prompt body rendered **strictly** — unknown
variables/filters fail the render (§5.4). Dynamic reload is REQUIRED (§6.2):
edit the file, the running service re-applies config and prompt without
restart. Elegant, coherent, and self-contained (§5.2 design note).

**Ours.** Protocol templates are **plugin-owned** (`references/*.md`, engine
blocks composed at render time), substituted with `{{PLACEHOLDER}}`s by the
dispatch ritual; config is env (`WORKER_ENGINE`, `CODEX_MODEL`,
`AUTO_MERGE_ENABLED`, `BOARD_REPO`) + labels (`engine:*`, `priority:*`) + one
narrow repo-owned manifest (`.doperpowers/risk-surfaces.md`, injected from the
PR **base ref** so a PR cannot delist a surface it touches). No hot reload —
nothing resident to reload. No strict templating — the FU-4 render-order bug
(`{{ISSUE_NUMBER}}` inside the execution block) is exactly the defect class
strict rendering catches; our test pins (`test-protocol-content.sh`) cover it
statically, not at render time.

**Judgment.** Symphony wins on config coherence (one typed, validated,
hot-reloading file). But the deeper fork is *ownership*: repo-owned means
every team forks the whole behavioral contract — divergence, no central
upgrades, prompt quality varies per team. Plugin-owned means v7.11.0 shipped
the evidence ladder + EXECPLAN policy to every consumer repo at once. For one
operator × N repos, central wins; for heterogeneous org teams, repo-owned
wins. The synthesis worth discussing is a **narrow repo-owned config file**
(bootstrap hooks, evidence add-ons) under a plugin-owned protocol — FD-3.

### 2.3 Worker contract: WF (one generic worker) vs our two protocols

**Symphony's WORKFLOW.md** (~330 lines) drives ONE worker species through the
whole ticket lifecycle via a prompt-embedded status map (WF "Status map",
steps 0–4): `Todo → In Progress → Human Review → Merging → Rework → Done`.
Notable machinery:

- **Workpad** (WF step 1): exactly one persistent tracker comment per issue —
  plan checklist, Acceptance Criteria, Validation, Notes, an environment stamp
  (`<host>:<abs-workdir>@<short-sha>`), and a **Confusions** section (*"only
  include when something was confusing during execution"*). All progress goes
  there; separate "done" comments are banned.
- **Reproduction-first** (WF step 1.8): *"capture a concrete reproduction
  signal and record it … before implementing."*
- **Ticket-authored validation is non-negotiable** (WF Default posture):
  `Validation`/`Test Plan` sections mirror into the workpad as required
  checkboxes.
- **PR feedback sweep** (WF protocol section): every actionable reviewer
  comment is blocking until addressed or explicitly pushed back on; loop until
  none remain and checks are green.
- **App-touching changes require runtime validation + captured media** (WF
  step 2.5: `launch-app`, `github-pr-media`) — video walkthroughs reach the
  human reviewer (Blog: PMs/designers *"기능이 작동하는 모습을 담은 비디오
  워크스루를 포함한 검토 패키지를 받게 됩니다"*).
- **Land loop** (WF step 3.5): on `Merging`, follow the `land` skill until
  merged — monitor CI, rebase, resolve conflicts, retry flaky checks; *"Do
  not call `gh pr merge` directly."*
- **Rework = full reset** (WF step 4): close the PR, delete the workpad,
  fresh branch from `origin/main`, restart from planning.
- **One park state**: the blocked-access escape hatch routes ALL blockage to
  `Human Review` with a blocker brief (WF "Blocked-access escape hatch") —
  the same state that means "PR ready for review." *"GitHub is not a valid
  blocker by default."*
- **Follow-ups become issues** (WF Default posture): out-of-scope discoveries
  are filed as Backlog issues with `related`/`blockedBy` links — convergent
  with our `--spawned-by` rule.

**Ours** splits the lifecycle across two species with a rigor gate at each
seam (implementing-tickets SKILL.md: review's gate at the END, implement's at
the START):

- **The Ticket Gate** before any source file opens: Check 1 *well-defined*
  (fork classification: mechanical → worker's call, parking it is a protocol
  violation; architecture → ticket+codebase or gate-fail; taste **major or
  minor** → ticket or gate-fail — "even minor taste is never your call");
  Check 2 *well-scoped* (landability: decompose only children that could land
  on main independently; big-but-atomic is ONE unit → ExecPlan).
- **Three park states by who-unparks** (issue-tracker state table): the human
  as themselves → `needs-human` (question list + recommended answers);
  substantial anyone-could-do knowledge work → `needs-info`; entangled
  steering of the work's core → `interactive-preferred` (summons a live
  brainstorming session; "any ENUMERABLE set of open decisions … is
  needs-human"). Notes are schema-required; the wake ritual consumes them.
- **Decomposition doctrine**: children as self-contained pre-specs NOW,
  `--parent`/`--blocked-by` typed edges, honest per-child gate-triage,
  contingent phases as parent `## Roadmap`; the decomposing worker writes no
  code.
- **Evidence ladder** (engine blocks): every claim of done carries evidence —
  testable logic → failing-test-first; UI → build + run rendered behavior (no
  test theater); config/docs → the relevant check. Work-alone: no subagents,
  no collab threads.
- **End of scope = PR or park.** `in-review` requires the PR URL
  (`board-transition.sh` gate); PR body carries `Closes #N`; residuals are
  registered `--spawned-by` BEFORE turn-end ("a follow-up not registered does
  not exist"). From the PR on, **reviewing-prs owns the path to merge**:
  fresh-context adversarial review (native codex criteria), per-finding
  verification, fix application, two-tier merge authority (self-merge iff
  approve ∧ ≤150 lines ∧ ≤5 files ∧ non-default-branch base ∧ zero risk
  surfaces ∧ all CI green; else `confident-ready` for the human), observation
  mode (`AUTO_MERGE_ENABLED` default off), tech-debt sink issue.

**Judgment.** Where we are ahead: the gate (Symphony has none — a Todo goes
straight to implementation; their answer to bad output is disposal, which
prices human review attention at zero), the park discriminant (their single
escape hatch overloads `Human Review` with two meanings — a modeling flaw),
the decomposition criterion, and the existence of an adversarial review
species at all (their merge confidence = CI + human + bots; nobody re-reviews
the agent's work with fresh context). Where they are ahead, concretely worth
importing (§4): the workpad (our trail is scattered across `[gate]` comments,
`[board]` notes, and PR bodies; theirs is one readable artifact — and
Confusions is a free harness-improvement feedback channel), reproduction-first
(our ladder evidences *done*, not *understood*), media evidence for UI work,
the rework doctrine (we can re-dispatch via `ready-for-agent` but no clause
tells the next worker the old PR is non-reusable), and the land loop (our
self-merge tier covers only trivial PRs; humans handle conflicts manually).

### 2.4 Workspace manager (SPEC §9) vs worktrees

**Symphony.** Per-issue directory under `workspace.root`
(`<root>/<sanitized-identifier>`), persistent across runs, containment
invariants (§9.5: cwd == workspace_path; path under root; sanitized names).
Population is not built in — hooks do it (§9.3): `after_create` (fatal on
fail), `before_run` (fatal), `after_run` (ignored), `before_remove` (ignored),
each a repo-owned shell script with a timeout (§9.4). The reference WF clones
the repo and runs `mise`/`mix deps.get` in `after_create`. Terminal issues get
workspace cleanup (startup sweep + reconciliation).

**Ours.** Git worktrees, always, for anything that writes code
(orchestrating-daemons "Isolating code daemons"): claude native `--worktree`,
codex worktree + Seatbelt `workspace-write`; the branch IS the deliverable
("a committed branch, not merged"); review workers get detached worktrees at
the PR head SHA. Codex workspaces get skills vendored
(`.agents/skills` symlink, FU-4) — single source since the plugin uninstall.
Cleanup ties to daemon lifecycle (purge dirty-guards; `daemon-retire.sh`
never deletes a worktree).

**Judgment.** Near-parity, different substrate. Worktrees get us cheap
isolation (shared object store, no clone, no network) and native merge
integration; their bare-dir+hooks model is more general (multi-repo tickets,
pure-research tickets — Blog: *"어떤 이슈는 … 코드베이스를 전혀 건드리지 않는
순수한 조사"*; ours handles that as a no-worktree research daemon, less
first-class). Their genuinely better piece is the **declarative per-repo
bootstrap hook**: our equivalent knowledge (e.g. ida-solution's arm64 `npm
ci` requirement) lives in memory files and prose, not machine-run config —
import candidate (§4.5, FD-3).

### 2.5 Agent runner: app-server (SPEC §10) vs `codex exec` / `claude --bg`

**Symphony.** Each worker launches `codex app-server` (via `bash -lc`, cwd =
workspace, §10.1) and speaks the app-server stdio protocol: streamed events
(§10.4: `session_started`, `turn_completed`, `turn_input_required`,
`approval_auto_approved`, token usage, rate limits), turn-level control
(read/turn/stall timeouts §10.6; mid-run cancellation via reconciliation),
multi-turn threads kept alive across continuation turns (§10.3), and
**client-side tool injection** — `linear_graphql` executes tracker mutations
with orchestrator-held auth: *"do not require the coding agent to read raw
tokens from disk"* (§10.5). The protocol is codex-version-owned; the spec
defers to it and warns of drift (§10 preamble).

**Ours.** Detached processes: `codex exec --json` (one session id for life,
`codex exec resume` to continue; sandbox + approvals flags per
`_codex_lib.sh`) and `claude --bg` (each turn forks a new agent; registry
chains session ids under one stable identity). Liveness = pid / `claude
agents`; durability = transcripts + the board; status = registry. No event
streaming (nobody listens), no token accounting, no stall detection, no
mid-turn cancel short of killing the pid, no tool injection (workers get
`GH_TOKEN` in env instead — FU-3, accepted note T3-9).

**Judgment — the direct answer to "is our way better than app-server?"**
App-server is objectively the richer runtime interface, **and its value is
conditional on a resident consumer**: streamed events need a listener, stall
detection needs a watchdog process, turn loops need a driver, injected tools
need a broker holding auth. We removed that process deliberately, so exec/bg
is not the inferior option — it is the right-sized one, and it buys something
app-server structurally cannot: **engine plurality**. The app-server protocol
locks Symphony to codex; our substrate runs two engines under one registry
and proved two species × two engines live (shakedown SD-1/SD-3). The two
capabilities whose absence we actually felt — transient-death auto-recovery,
stall detection — are watchdog features, not runner features; importing them
via the trigger-phase watchdog (T1) gets ~80% of app-server's operational
value at ~5% of its machinery, with zero standing judgment. Revisit only if
we ever adopt a resident supervisor — which the doctrine rejects.

### 2.6 Safety (SPEC §15) — ours is concrete, theirs is documented-away

Symphony's spec explicitly declines a posture: approval/sandbox/operator
confirmation are implementation-defined (§1, §10.5); the reference WF runs
high-trust (`approval_policy: never`, `workspace-write`, network on). §15.5
(Harness Hardening Guidance) is a good *threat-model narrative* — tracker
data, repo contents, and tool args are not trustworthy — but lists hardening
as SHOULDs. Ours is enforced at spawn: Seatbelt `workspace-write`; approvals
auto-reviewer fail-closed (a codex daemon is never `blocked` — a declined
escalation is a failed command it works around or parks over);
`features.hooks=false` always (a checked-out PR could ship
`.codex/hooks.json`); risk-surfaces injected from the base ref; and the twin
bans (`--dangerously-skip-permissions` / `--yolo` /
`--dangerously-bypass-approvals-and-sandbox`) written into the skills. Their
§15.5 prose is worth emulating in our docs; their posture is not.

### 2.7 Observability (SPEC §13)

Symphony: structured logs with required context fields, runtime snapshot,
optional HTTP dashboard (`/api/v1/state`: running rows, retry queue, token
totals, rate limits — §13.7), humanized event summaries. Ours: `daemon-list`,
`board-reconcile`, BOARD.html (layered DAG + kanban, hot-reload, hosted via
Pages/Cloudflare-Access). Different objects: they observe *sessions*, we
observe *work*. Their token/rate-limit accounting has no equivalent on our
side (codex `--json` emits usage; we drop it) — a cheap registry field worth
adding when the fleet grows. Their `turn_count`/stall telemetry belongs to
the watchdog import.

---

## 3. Settled axes (no discussion needed)

- **Liveness automation: Symphony.** Settled not by adopting their
  orchestrator but by T1's watchdog plan (bounded auto-resume distinguishing
  transient from real failures, sweep, caps). Their retry-queue design is the
  reference to steal from (backoff formula, continuation-vs-failure retry
  distinction, stall timeout).
- **Work semantics: ours.** Gate, parks, decomposition, review species, merge
  tiers — Symphony's contract simply doesn't attempt these; their blog's
  cheap-disposal economics is the honest alternative and it prices review
  attention at zero.
- **Safety: ours.** Enforced beats documented.
- **Dual-engine substrate: ours.** Proven live; structurally impossible on
  app-server.
- **Scale evidence: theirs, by orders of magnitude.** Blog: merged PRs +500%
  overall, 6× in the first 3 weeks on some teams; Linear's cofounder noted a
  workspace surge. Ours: SD-1/SD-3 at n=1 each, claude engine branch untested
  (T2-3). Our claims above are design-superiority claims, not
  scale-validation claims.

---

## 4. Import candidates (prioritized)

1. **Workpad** — one persistent structured issue comment (plan checklist /
   AC / validation evidence / **Confusions**) written by the implement worker.
   Where: implement-worker-protocol.md clause + a `[workpad]` comment
   convention. Cheap; consolidates our scattered trail; Confusions feeds
   harness improvement. (WF step 1, workpad template.)
2. **Reproduction-first rung** — for bug-category tickets, capture the
   failure signal before changing code; record it in the workpad. Extends the
   evidence ladder from *done* to *understood*. (WF step 1.8.)
3. **Rework clause** — when a human review rejects the approach: close the
   old PR, fresh branch from origin/main, prior branch non-reusable, full
   reset. Where: implement protocol edge case + issue-tracker wake ritual.
   (WF step 4.)
4. **Watchdog details for T1** — backoff formula, transient-vs-real
   distinction, stall timeout, `max_concurrent_agents` (+ per-state caps).
   (SPEC §8.4, §8.5, §5.3.5.) Also FD-8's cancellation sweep if adopted.
5. **Per-repo bootstrap hook** — a narrow `.doperpowers/workspace-hooks`
   (after-create/before-run analog) so consumer-repo setup (npm ci lesson)
   is declarative, not tribal. (SPEC §9.4.) Scope carefully — FD-3.
6. **UI media evidence** (pilot) — app-touching tickets attach a runtime
   capture to the PR. (WF step 2.5.) Raises human-review confidence for the
   exact tier that stays human (FD-7).
7. **Token accounting** (later) — usage fields from `codex exec --json` into
   the registry; surface in daemon-list. (SPEC §13.5.)

## 5. Deliberate non-imports

- **Resident orchestrator** — replaced by watchdog + event trigger; doctrine
  (no judge between worker and board) and durability both argue against.
- **app-server runner** — value conditional on a resident consumer; kills
  dual-engine (§2.5).
- **Repo-owned full prompt** — kills central upgrades; keep repo ownership to
  narrow manifests (risk-surfaces, maybe workspace-hooks).
- **Polling** — the event trigger + sweep cron covers it with less machinery;
  GitHub events beat 30s polls for our scale.
- **Liquid strict templating wholesale** — but add a cheap render-time check:
  fail dispatch if any `{{...}}` survives substitution (the FU-4 class).
- **`Human Review` overloading** — their single park state is the flaw our
  discriminant fixes; nothing to take.

---

## 6. Forked decisions for discussion (non-trivial, skewed, both defensible)

> Each FD names the fork, both bets, the skew (why the trade is asymmetric),
> and the open question. These are the agenda items — settled axes (§3) are
> deliberately excluded.

### FD-1 · Worker lifetime: continuous attachment vs episodic dispatch

**Symphony:** one worker + workspace + live thread rides the ticket's whole
active life — continuation turns re-check the tracker after every turn and
keep going (SPEC §7.1, §16.5; WF: *"Do not end the turn while the issue
remains in an active state"*), up to `max_turns` 20; a 1s continuation retry
re-enters after clean exits. Re-orientation cost ≈ 0; the workpad carries
state forward. **Ours:** 1 dispatch = 1 scope (gate → PR | park); every
re-dispatch is fresh context and re-runs the gate ("prior `[gate]` comments
are context, not inherited trust"). Anchoring/context-rot resistance; honest
re-evaluation; but every wake pays full re-orientation, and the seam between
dispatches is where state gets lost (hence their workpad matters more to us,
not less). **Skew:** they pay tokens continuously to hold context; we pay
tokens repeatedly to rebuild it. Notably *they* chose fresh-start for rework
specifically — evidence the fresh-context bet is right at decision seams.
**Open:** is there any seam where we want continuation semantics (same
session resumed) instead of re-dispatch — e.g. a `needs-human` answered
within minutes, where the parked worker's context is fresher than any
re-orientation could be? (`codex exec resume` makes this mechanically free
for the codex species.)

### FD-2 · State machine ownership: prompt+config (soft) vs scripts/schema (hard)

**Symphony:** tracker states are config lists (`active_states`,
`terminal_states`); the transition map is prose in the prompt; nothing
enforces legality; hot-reload lets an operator reshape the workflow by
editing one file mid-flight (SPEC §6.2). **Ours:** `_board.py` owns a legal
transition graph, required notes, the in-review PR gate, cycle checks;
illegal transitions fail loudly; changing the machine means changing the
plugin (a release, with tests). **Skew:** their flexibility is also their
fragility — a prompt-described state machine drifts per repo and nothing
catches a worker writing an illegal state; our rigidity is also our friction
(T3-6 two-hop restore exists *because* the schema refuses a
`needs-human → in-review` edge). **Open:** where is the line between
schema-worthy invariants and workflow choices a consumer repo should be able
to reshape without a plugin release?

### FD-3 · Contract ownership boundary: repo-owned WORKFLOW.md vs plugin-owned protocol

**Symphony:** the whole contract (prompt + config + hooks) is versioned with
the consumer repo — teams tune it like code, and the blog credits rapid
guardrail iteration for their success (*"결과를 수동으로 수정하는 대신 …
가드레일과 역량을 추가했습니다"*). **Ours:** doctrine is central (one release
upgrades every repo); repo-specific knowledge is confined to narrow manifests
(risk-surfaces today). **Skew:** central ownership optimizes for one operator
× N repos and protocol quality; repo ownership optimizes for per-team
iteration speed and heterogeneity. The costs surface differently: theirs as
drift and fork-divergence, ours as "the plugin release train gates every
workflow tweak." **Open:** which contract pieces should migrate to repo
ownership? Candidates: workspace bootstrap hooks (§4.5), per-repo evidence
add-ons (UI media required? which commands prove "build passes"?), per-repo
park-note templates. Anti-candidates: the gate, the discriminant, merge
tiers.

### FD-4 · The last mile: land-loop automation vs human-click merge

**Symphony:** human approval is *one state transition* (`Human Review →
Merging`); the agent owns everything after — rebase, conflict resolution,
flaky-check retries, merge-queue babysitting (WF step 3.5, land skill; Blog:
monorepo landing as a core strength). The human never touches git. **Ours:**
self-merge only for the trivial tier on non-default branches; everything else
is `confident-ready` + a human performing the merge mechanics themselves,
conflicts included. **Skew:** their design treats landing mechanics as
worker-grade (it is — no taste, no irreversibility beyond what approval
already authorized); ours currently conflates "the human decides" with "the
human operates." Our own discriminant argues their way: the *decision* is
human-grade, the *mechanics* are not. **Open:** add a post-approval landing
phase — human approves `confident-ready`, a land-worker (or the review worker
resumed) executes rebase/CI-retry/merge? Preconditions: runner registration
(T2-5), auto-merge observation maturing, and a real conflict-resolution
policy (a rebase that hits semantic conflicts is new code → whose review?).

### FD-5 · Exploration economics: gate-always vs cheap speculative tickets

**Symphony:** *"추측성 작업을 띄우는 일이 아주 쉬워졌습니다"* — file a vague
ticket, let the agent explore, discard failures at ~zero cost; PMs/designers
file features directly and get review packages back. The gate would park most
of those tickets on our board. **Ours:** the gate taxes exactly this use
case — deliberately, because our consumer repos' merge lane is
attention-priced, and a wrong PR is not free. **Skew:** the gate's value
scales with the cost of a wrong PR; exploration's value scales with the cost
of NOT trying ideas. These coexist in one org but not in one lane. **Open:**
do we want an explicit **spike lane** — e.g. a `spike` category whose gate
relaxes Check-1 taste (output is information, not product), whose deliverable
is a findings comment + optional draft PR, and which is hard-barred from
merge? Or is "run it as an ad-hoc research daemon / interactive session" the
honest answer and the board should stay production-only?

### FD-6 · Credential topology: broker-held auth vs worker-env tokens

**Symphony:** the orchestrator holds tracker auth and exposes a narrow
injected tool (`linear_graphql`, one operation per call, §10.5): *"do not
require the coding agent to read raw tokens from disk."* The agent never
sees the token; the tool can be scoped (§15.5 suggests project-scoping).
**Ours:** FU-3 exports `GH_TOKEN` into the worker env (accepted note T3-9,
parity with claude's keychain reach); the worker wields full `gh` with the
operator's identity. **Skew:** their design has a *place* to put mediation (a
resident process); ours doesn't, so the token travels or the worker can't
write the board — and unattended dispatch (T1) will widen exposure (tokens in
env on a machine nobody is watching). **Open:** at which phase does a broker
become worth its machinery — fine-grained PAT per repo now? a local
credential-broker proxy at the unattended phase? never (Seatbelt + fail-closed
approvals is enough)?

### FD-7 · Evidence audience: machine-checkable discipline vs human-consumable richness

**Symphony:** evidence targets the human reviewer's eyes — workpad checklists,
mirrored ticket validation, complexity analysis, **video walkthroughs** (Blog,
WF step 2.5). **Ours:** evidence targets the pipeline — the ladder disciplines
the worker's *claims*, and the review worker verifies findings mechanically;
the human at `confident-ready` gets a trail comment, a PR diff, and CI. **Skew:**
we made the human the merge authority for everything non-trivial (FD-4), yet
our evidence investment flows to the machine tier; Symphony's flows to the
human tier they also gate on. If the human stays our expensive tier, their
allocation is arguably more rational than ours. **Open:** how much of §4.1/.2/.6
(workpad, reproduction-first, UI media) to mandate vs leave repo-optional
(ties into FD-3's boundary) — and does the review worker *consume* the workpad
(cross-checking claimed validation against the diff) or only the human?

### FD-8 · Board-driven cancellation: reconciliation kills vs kill-by-hand

**Symphony:** move a ticket out of the active states and reconciliation
terminates its running worker within one tick (terminal → also cleans the
workspace; §8.5B). The board is a *control* plane in both directions.
**Ours:** the board only *records*; a running worker consults its ticket at
gate time, not continuously — a human who wontfixes/parks a ticket mid-build
changes nothing until the worker's next board write collides. Killing means
finding the daemon and killing the pid by hand. **Skew:** read-only
reconciliation was the right MVP (no resident process to do the killing), but
it breaks the "board is the single interface" story exactly at the moment a
human most wants it (runaway or obsolete work). **Open:** should the sweep
cron gain a cancellation pass (ticket left open-active states → retire the
bound daemon, comment the termination)? What are the semantics for the
in-flight worktree (keep as WIP branch, per "committed branch not merged")?

---

## 7. Convergences worth noting (independent evolution, same answer)

Both systems, independently: workers write the tracker themselves (SPEC
§11.5 boundary ≈ our worker authority); success = a handoff state, not Done
(SPEC §1: *"A successful run can end at a workflow-defined handoff state (for
example `Human Review`)"* ≈ our in-review/park endings); out-of-scope
discoveries become linked issues at the moment of discovery (WF Default
posture ≈ our `--spawned-by` deferral rule); the tracker is the control
plane; state machines for agents should carry goals, not micro-transitions
(their blog lesson ≈ our no-judge doctrine). Convergence under independent
evolution is evidence the problem shape, not fashion, dictates these — and
it localizes the genuine disagreements to §6's eight forks.
