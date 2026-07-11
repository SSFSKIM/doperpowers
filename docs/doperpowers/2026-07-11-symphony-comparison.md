# Doperpowers board pipeline vs OpenAI Symphony — a component-level comparison

> **What this is.** A judgment-bearing comparison of two ticket-driven agent
> orchestration systems: OpenAI's **Symphony** (SPEC.md draft v1 +
> WORKFLOW.md reference contract + launch essay, read 2026-07-11 from
> `agent-harness/docs/symphony-original/`) and **this fork's board pipeline**
> (issue-tracker + implementing-tickets + reviewing-prs + orchestrating-daemons,
> as of v7.11.0, one live shakedown in). Not a parity checklist — each section
> ends with a verdict and, where we lose, what to steal.
>
> Honesty note on evidence: Symphony claims 6× merged-PR throughput on some
> OpenAI teams over 3 weeks; our evidence is one live shakedown (SD-1
> implement×codex, SD-3 review×codex) plus the v7.10.0-era claude-daemon
> history. Their coordination layer is battle-tested at fleet scale; ours is
> not yet armed for unattended operation (TECH-DEBT T1).

## 0. TL;DR — the two systems invert each other

**Symphony is an industrial coordination layer wrapped around a thin
judgment layer.** A long-running orchestrator service guarantees liveness
(every active ticket has a running agent — poll, dispatch, retry with
backoff, stall-kill, reconcile), while the worker contract assumes every
dispatched ticket is buildable and pushes through it; the only park is one
overloaded state (`Human Review`) and the only reviewer is the human.

**Doperpowers is a thick judgment layer wrapped around a deliberately thin
coordination layer.** There is no orchestrator process at all — dispatch is
a mechanical ritual (interim: human-run; next phase: issue-event trigger),
liveness recovery is manual (TECH-DEBT T1) — while the judgment machinery is
deep: a pre-code Ticket Gate, a three-way park taxonomy routed by *who can
unpark it*, landability-based decomposition, an evidence ladder, a second
autonomous **review species** with a self-merge rubric, risk surfaces, and
staged rollout.

Neither dominates. Symphony optimizes **throughput of a trusted fleet on a
well-groomed board**; we optimize **correct routing of scarce human
attention plus autonomous quality control**. The actionable conclusion:
steal Symphony's coordination patterns for our trigger phase (bounded
auto-resume, stall detection, concurrency caps, the land loop) without
importing the always-on service — our review loop's event-trigger + cron
sweep already proved that shape at near-zero infrastructure.

## 1. Architecture mapping

| Symphony component | Doperpowers counterpart | Structural difference |
|---|---|---|
| Orchestrator (long-running service, poll tick, in-memory claims/retries) | **None by design.** Dispatch ritual + review-side event trigger & sweep; the board itself is the claim store | They centralize scheduling state in a process; we externalize it into GitHub labels + the daemon registry |
| Workflow Loader (`WORKFLOW.md` = YAML config + Liquid prompt, hot-reload) | Protocol markdown + engine blocks in the versioned plugin, rendered by placeholder substitution at spawn | Theirs is per-repo config; ours is cross-repo versioned methodology |
| Config Layer (typed getters, `$VAR`, validation, dynamic reload) | Env vars (`WORKER_ENGINE`, `CODEX_MODEL/EFFORT`, `AUTO_MERGE_ENABLED`, `BOARD_REPO`) + ticket labels | They configure a service; we parameterize scripts |
| Issue Tracker Client (Linear GraphQL, read-only, normalization) | `gh` + `_board.py` against GitHub Issues (read **and** write, schema-enforcing) | Their tracker is a queue the orchestrator reads; our tracker IS the state machine, enforced at write time |
| Workspace Manager (dir-per-issue + shell hooks, containment invariants) | Git worktrees per ticket + vendored skills (`.agents/skills`) | Clone-per-issue directories vs worktrees off the local clone |
| Agent Runner (Codex **app-server**, stdio JSON-RPC, thread/turn loop, streaming events) | `codex exec --json` one-shot + `codex exec resume` / `claude --bg` | Persistent protocol client vs CLI spawn-and-resume |
| Worker contract (WORKFLOW.md prompt body: workpad, status map, feedback sweep, land skill) | Implement Worker Protocol + Review Worker Protocol (+ Ticket Gate, park taxonomy, evidence ladder) | Theirs: one species, execution-focused. Ours: two species, judgment-focused |
| Status surface (HTTP dashboard, `/api/v1/state`, token/rate-limit totals) | `daemon-list.sh`, `board-map.sh --serve` (board telemetry, not runtime telemetry) | They watch the *fleet*; we watch the *work* |
| — (no counterpart) | **Review worker species** (reviewing-prs): findings, fix-in-place, self-merge tier, `confident-ready` | Symphony ships no autonomous reviewer; the human is the review engine |

## 2. Coordination layer — orchestrator, liveness, retries

**What they have.** A single-authority orchestrator: poll every
`interval_ms`, reconcile running issues against tracker state (terminal →
kill + clean; non-active → kill; stalled past `stall_timeout_ms` since last
event → kill + retry), dispatch by priority into global and per-state
concurrency caps, exponential backoff on abnormal exits
(`10s·2^(n−1)` capped at 5 min), a 1-second *continuation retry* after every
normal exit so a still-active ticket immediately gets another worker, and an
in-worker turn loop (`max_turns`, default 20) that re-checks ticket state
after each turn and re-prompts the same live thread. Restart recovery is
tracker+filesystem-driven; scheduler state is intentionally in-memory only.

**What we have.** Nothing sits between workers and the board. Claims are
`status:in-progress` + `board-bind.sh`; death is discovered by
`board-reconcile.sh` naming orphans; recovery is a human running
`codex-resume.sh`/`daemon-resume.sh`. The review side already has the
event-shaped equivalent: PR events → `review-dispatch.sh` on a self-hosted
runner, plus a ~30-min cron sweep with registry-based dedupe. The implement
side's trigger is unbuilt (`implementing-tickets/scripts/` is empty).

**Verdict: Symphony wins this layer today, and it is exactly our named
debt.** Their retry taxonomy (transient vs real, bounded backoff), stall
detection keyed on last-event timestamps, and per-state concurrency caps are
precisely what TECH-DEBT T1 #1/#2 and the trigger phase must answer. Two
counterpoints keep this from being a rout:

1. **Their liveness costs an always-on stateful service** (the reference
   implementation is an Elixir app on a dev box) whose scheduler state dies
   with the process and which assumes single-instance operation (claims are
   in-memory — two orchestrators would double-dispatch). Our review loop
   demonstrates the same liveness guarantee as *event trigger + idempotent
   sweep + registry dedupe* — no resident process, safe across restarts
   because the "orchestrator state" lives in GitHub and the registry.
2. **Their transient-death recovery loses the thread.** A worker that dies
   mid-run is re-dispatched fresh (attempt N, workspace + workpad comment as
   the only carried context). Our `codex exec resume` recovers the actual
   session from disk — proven three times in the live shakedown — which is
   strictly better for the model-at-capacity / stream-disconnect class.

**Steal for the trigger phase:** the transient-vs-real failure split with
bounded auto-resume (resume, not re-dispatch); stall detection computed from
the `codex exec --json` event stream we already record; global + per-state
concurrency caps; the 1-second continuation recheck after clean exits
(ours: worker turn ended but the ticket is still `in-progress` → resume with
continuation guidance, up to a turn cap).

## 3. Workflow loader + config layer

**What they have.** One repo-owned `WORKFLOW.md`: YAML front matter (typed,
validated, `$VAR` indirection, defaults) + a Liquid prompt body rendered
**strictly** — unknown variables or filters fail the render. The file is
watched; edits hot-reload config and prompt without restarting the service.
Preflight validation gates every dispatch tick.

**What we have.** The worker contract lives in the plugin
(`implement-worker-protocol.md` + engine blocks), versioned and released
across all consumer repos at once; per-repo knobs are env vars, labels, and
`.doperpowers/risk-surfaces.md`. Rendering is manual placeholder
substitution — which already bit us once (the FU-4 render-order bug:
`{{ISSUE_NUMBER}}` inside `{{EXECUTION_BLOCK}}` had to be substituted in the
right order), and nothing fails loudly if a `{{PLACEHOLDER}}` survives into
the spawn prompt.

**Verdict: split.** Their loader is better *engineering* (typed config,
strict templates, hot reload — all real); our model is a better
*distribution strategy* for a methodology maintained as a product: one
plugin version bump upgrades every repo's workers, instead of N drifting
WORKFLOW.md copies. The tension is per-repo customization, which we
deliberately route through small surfaces (labels, env, risk-surfaces
manifest) rather than letting each repo fork the whole contract.

**Steal (cheap):** strict rendering — after substitution, grep the spawn
prompt for `{{[A-Z_]*}}` and abort the dispatch on any survivor. One line in
the ritual/dispatch script; kills the FU-4 bug class permanently.

## 4. Worker contract — WORKFLOW.md prompt vs the two protocols

**Their contract's strengths** (genuinely good, worth acknowledging
specifically):

- **The workpad**: exactly one persistent tracker comment per issue
  (`## Codex Workpad`) holding plan checkboxes, acceptance criteria,
  validation requirements, notes, an environment stamp
  (`host:path@sha`), and a `Confusions` section. It is the single source of
  truth for progress and the context-death survival mechanism — their
  ExecPlan-equivalent, living in the tracker instead of the repo.
- **PR feedback sweep protocol**: every actionable reviewer comment (human
  or bot, top-level or inline) is blocking until addressed or explicitly
  pushed back on, re-swept until zero remain.
- **Ticket-authored `Validation`/`Test Plan` sections are non-negotiable
  acceptance input** — mirrored into the workpad as required checkboxes.
- **Temporary proof edits** are allowed for validation confidence but must
  be reverted before commit and documented in the workpad.
- **The land skill**: once a human approves (`Merging`), the agent babysits
  the PR to main — rebase, conflict resolution, CI monitoring, flaky-check
  retries — in a loop until merged.

**Their contract's structural gap:** it assumes every dispatched ticket is
buildable. There is no gate; the escape hatch exists only for missing
tools/auth ("GitHub is not a valid blocker"), and underspecification has no
routing — the agent builds *something*, and the essay owns the consequence
("sometimes the agent produced completely off-target results… that too was
useful information"). Failure is treated as cheap exploration. `Rework` is a
full reset: close the PR, delete the workpad, fresh branch, start over.

**Our contract's strengths:** the Ticket Gate (well-defined + well-scoped)
runs before any source file opens, with the fork-class table deciding what a
worker may answer itself (mechanical forks: parking them is a protocol
violation) versus what gate-fails (unanswered architecture, any product
taste). Parks route by *who can unpark them*: `needs-human` (a decision or
real-world input only the human possesses — with recommended answers
attached), `needs-info` (delegable research), `interactive-preferred`
(entangled architecture-core steering; enumerable decision lists never
qualify). Decomposition is landability-based with typed edges and honest
gate-triage of each child. Execution carries the evidence ladder (no claim
of done on reasoning alone; testable logic → failing-test-first; UI →
rendered behavior; config/docs → the relevant check), EXECPLAN mode for
context-death-surviving work, and the work-alone clause. Authority rules are
explicit: never terminal states, `wontfix` is recommended not decided,
cross-ticket writes are comments.

**Verdict: ours is the stronger contract for unattended real product work;
theirs is the stronger contract for high-throughput exploration.** The gate
prevents the off-target class Symphony accepts as a cost of doing business —
and on a personal/consumer codebase where a human reviews every
non-trivial merge, a wasted end-to-end build is *not* nearly free; it costs
the scarce resource (human review attention) both systems claim to protect.
Symphony's bet makes sense at OpenAI's fleet scale with harness-engineered
repos and dedicated groomers; ours makes sense where the board is the
human's own backlog.

**Steal:** the land loop, as a third small behavior — after the human
approves a `confident-ready` PR, a worker (or the review worker's final act)
babysits merge: rebase, conflict resolve, CI green, retry flaky, merge.
Today that gap is invisible (small repos, fast CI) but it is the exact
last-mile Symphony calls out as disproportionately painful in monorepos.
Also worth copying cheaply: treating ticket-authored `Validation` sections
as required acceptance checkboxes (our gate reads success criteria but the
protocol doesn't make ticket-supplied test plans mandatory-verbatim), and
the `Confusions` section — a per-run friction ledger is how our shakedown
FU-list happened; institutionalizing it in the turn-end message costs
nothing. The workpad-as-single-comment is *optional* for us: our progress
artifacts live in the repo (ExecPlan doc, branch, PR body) by design —
better for engineering review, slightly worse for phone-glanceable boards.

## 5. Workspace manager

Theirs: `<workspace.root>/<sanitized-issue-id>` directories, populated by
repo-owned shell hooks (`after_create`: `git clone --depth 1 …`;
`before_run`/`after_run`/`before_remove`), 60s hook timeouts, containment
invariants (cwd == workspace path, path under root, sanitized names),
workspaces preserved across runs and cleaned on terminal states.

Ours: a git worktree per ticket off the local clone (instant, shared object
store, branch-native, no re-clone, auto-cleaned when unchanged), plus
`_codex_vendor_skills` symlinking the doctrine into `.agents/skills` with a
git-exclude, plus the sandbox env repairs (GH_TOKEN injection,
SSL_CERT_FILE) the shakedown forced.

**Verdict: ours wins on substance** — worktrees are simply the better
primitive for same-host workers (their shallow-clone-per-issue re-downloads
and diverges from local state). **Theirs wins on extensibility**: the
four-hook lifecycle is a clean, repo-owned seam for dependency bootstrap
(`npm ci`, mise, codegen) that we currently hard-code or handle ad hoc (the
ida-solution arm64/x64 `npm ci` note is exactly an `after_create` hook
wanting to exist). Steal the *seam*, not the machinery: an optional
per-consumer-repo `after-create` hook script that spawn scripts run in a
fresh worktree would close it in ~10 lines. Their startup terminal-workspace
cleanup also answers our FU-2 residue (un-swept run scratch) — fold a sweep
into the trigger phase.

## 6. Agent runner — app-server vs `codex exec` + resume (the direct question)

Symphony launches `codex app-server` per worker: a persistent stdio JSON-RPC
subprocess speaking the thread/turn protocol — streaming events, token and
rate-limit telemetry, turn timeouts, mid-run cancellation, and cheap
continuation turns on the same live thread without re-serializing context.

We launch `codex exec --json` one-shot per turn and `codex exec resume` (with
config-space sandbox args) for continuation, under Seatbelt
`workspace-write`; events land in `.jsonl` transcripts; the registry holds
pid/state.

**Is our way better than app-server for the implementer? For our
architecture, yes — and the reasons are structural, not taste:**

1. **App-server's value is realized by a supervisor.** Streaming telemetry,
   stall detection, turn cancellation, and the in-process turn loop all
   assume a resident process consuming the stream and making scheduling
   decisions. We deliberately have no such process; a protocol client with
   nobody watching it is dead weight plus a protocol-drift liability (the
   spec itself defers every schema question to "the targeted app-server
   version").
2. **Durability inverts the comparison.** An app-server thread lives in the
   subprocess; when the worker or orchestrator dies, Symphony's recovery is
   re-dispatch-fresh with only the workspace and workpad as carried context.
   Our resume rehydrates the actual session from codex's on-disk state —
   context intact. For the dominant failure class we actually observed
   (upstream transients), CLI-resume is *stronger* than app-server.
3. **What we genuinely give up:** live token/rate-limit accounting,
   sub-turn-latency stall detection, and mid-turn cancellation
   (reconciliation-style "ticket went terminal, kill the worker now"). All
   three become relevant only in the unattended phase — and all three are
   recoverable from the `--json` event stream + `kill` on the recorded pid,
   without adopting the protocol client.

So: not parity-with-excuses — the two runners are each locally optimal for
their coordination layer, and swapping either across would make that system
worse. Revisit only if the trigger phase's monitoring wants event-level
granularity that transcript-tailing can't provide.

## 7. Review, merge authority, and the missing species

Symphony's pipeline after the PR opens: the worker sweeps feedback written
by others, a **human** reviews (`Human Review`), the human approves
(`Merging`), the agent lands it. The system ships no reviewer — "proof of
work" (CI status, complexity analysis, walkthrough videos) is decoration on
a human review. Rework is a from-scratch reset.

Ours: every non-draft PR gets a fresh-context review worker — native-Codex
review criteria (correctness + spec-compliance against the linked ticket's
acceptance), every finding verified against the code before it counts,
valid fixes applied in place, re-review when warranted, then either
self-merge (two-tier rubric: approve verdict, ≤150 lines/≤5 files,
non-default-branch base, zero risk-surface touches, all CI green — with
risk surfaces read from the base ref so a PR can't delist what it touches)
or escalation to `confident-ready` for a one-glance human merge. Staged
rollout via observation mode. Findings that don't block go to the tech-debt
sink.

**Verdict: ours wins outright — this is a whole pipeline stage Symphony
doesn't have.** Their human reviews N× more PRs (their own 6× number makes
the human the new bottleneck; the essay's cabin-wifi anecdote is charming
precisely because review-from-phone only works when someone else did the
rigor). `confident-ready` is our answer to exactly that bottleneck. The one
sub-piece where they're ahead inside this stage is the post-approval land
loop (§4), which composes cleanly with our `confident-ready`: human
approves, land worker babysits.

## 8. Observability

Symphony: structured logs with issue/session context, live session rows
(turn counts, last event, token totals, rate limits), an optional HTTP
dashboard + `/api/v1/state` + per-issue debug endpoint. Ours:
`daemon-list.sh` (registry truth), `board-map.sh --serve` (interactive DAG /
kanban of the *work*), codex `.jsonl` transcripts, `[board]` audit comments.

**Verdict: Symphony wins runtime telemetry; we win work telemetry.** Their
dashboard answers "what are my agents doing right now / what is this fleet
costing"; our board map answers "what is the state of the work and what
needs me". At our current scale (single-digit concurrent workers,
operator-paced) runtime telemetry is a nice-to-have; it becomes T1-adjacent
the day the trigger phase arms unattended dispatch. When it does, derive it
from what we already record (registry + transcripts) rather than a resident
server — a `daemon-list --watch` or a static page next to BOARD.html.

## 9. Philosophy — the deepest agreement, and the real disagreement

The essay's hardest-won lesson — *"treating agents as rigid nodes in a state
machine doesn't work; give them goals, tools, and context, like a good
manager"* — is a lesson **both** systems now embody: their workers own all
tracker writes; our workers own their ticket's open states, register their
own children and follow-ups, and answer mechanical forks themselves under an
authority contract. Convergent evolution from opposite starting points.

The real disagreement is **where scarce human attention goes**:

- Symphony spends it on **reviewing output** (accept/reject finished work;
  failure is cheap, so overproduce and filter).
- Doperpowers spends it on **answering questions** (parks with recommended
  answers, confident-ready one-glance merges; failure is not cheap because
  the human reviews what survives).

Which is right depends on the ratio of agent cost to review cost. At
OpenAI's scale — free-ish tokens, harness-engineered repos, PMs filing
tickets — overproduce-and-filter is rational. For a solo operator whose
review bandwidth IS the bottleneck, gate-first + autonomous review is
rational. Our design fits our deployment; theirs fits theirs. The
architectures are honest about their respective bets.

## 10. Adoption list (concrete, tiered against TECH-DEBT.md)

| # | Steal | Where it lands | Tier |
|---|---|---|---|
| 1 | Transient-vs-real failure taxonomy + bounded auto-**resume** (not re-dispatch) + stall detection from recorded event timestamps | Trigger phase spec (TECH-DEBT T1 #1/#2) | T1 — already gated on that phase; Symphony §7–8 is the reference design |
| 2 | Global + per-state concurrency caps and priority-ordered dispatch under them | Trigger phase | T1-adjacent |
| 3 | Strict render check: abort dispatch if any `{{PLACEHOLDER}}` survives substitution | Dispatch ritual / future `implement-dispatch.sh` + `review-dispatch.sh` | cheap, do at next touch |
| 4 | Post-approval **land loop** for `confident-ready` PRs (rebase, CI babysit, flaky retry, merge) | reviewing-prs (new small behavior or protocol block) | T2 — valuable as consumer repos grow CI |
| 5 | Optional per-repo `after-create` worktree hook (dependency bootstrap seam) | orchestrating-daemons spawn scripts | T3 — the ida-solution `npm ci` note is the first customer |
| 6 | Ticket-authored `Validation`/`Test Plan` sections as mandatory acceptance checkboxes | implement-worker-protocol | cheap prompt addition |
| 7 | `Confusions`/frictions section in worker turn-end messages | both worker protocols | cheap prompt addition |
| 8 | Terminal-workspace sweep at trigger startup (FU-2 residue) | trigger phase | T3 |

**Do not adopt:** the resident orchestrator service (our event+sweep shape
reaches the same liveness without a process to keep alive), the app-server
protocol client (§6), per-repo WORKFLOW.md forks of the contract (our
plugin-versioned distribution is the point), full-reset Rework semantics
(our fix-in-place review loop is cheaper for the common case; a human can
always order a reset), and Linear (the board being GitHub Issues — same
store as the PRs, zero extra SaaS — is a feature).
