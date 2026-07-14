# PR Review Loop — autonomous review workers for opened PRs

## Purpose

Today the board pipeline has exactly one unguarded edge: `in-review → done`
happens by merge with no rigor gate. A daemon opens a PR and nothing stands
between that PR and the human's merge button except the human's own reading
time. After this change, every non-draft PR opened in a consumer repo is
picked up within minutes by a fresh-context **review worker** — a background
`claude` daemon that runs a Codex review against the PR's base, verifies each
finding against the code, applies the valid fixes, re-reviews when the fixes
warrant it, and then either merges the PR itself (small/simple tier, CI
green) or escalates it as **`confident-ready`** — a new board state meaning
"rigorously reviewed; merge with confidence."

The loop is the inverse-symmetric counterpart of the implementing daemon:
where an implementing worker turns a ticket into a PR, a review worker turns
a PR into a confident merge. Unlike the implement-dispatch loop, **this loop
has no orchestrator** — the review worker's escalation targets are GitHub
itself (labels, comments, tickets) and the human on their next wake.

How to see it working: open a non-draft PR in ida-solution; within ~2 minutes
`daemon-list.sh` shows a `review-pr-<n>` daemon working; when it finishes, the
PR is either merged with a review-trail comment or wearing a `confident-ready`
label with its linked issue at `status:confident-ready`.

**Terms of art.** *Review worker*: a background daemon spawned per PR whose
only job is reviewing that PR. *confident-ready*: the new board state (open +
`status:confident-ready` on the issue; plain `confident-ready` label on the
PR) between `in-review` and `done`. *Self-merge tier*: the class of PRs the
review worker may merge itself, defined by Rubric 3. *Standing tech-debt
issue*: one pinned GitHub issue per consumer repo, labeled `tech-debt`, where
small non-blocking findings accumulate as comments. *Review engine*: whichever
reviewer produced the findings — Codex (default) or the Claude fallback.

## Architecture

```
PR opened / ready_for_review (ida-solution)
  → GH workflow job on self-hosted runner (the Mac)      [trigger — mechanical]
    → review-dispatch.sh <pr#>                           [assembler — mechanical]
        dedupe → gather PR body + linked issue → detached
        worktree at PR head SHA → spawn worker --no-wait
      → review worker (Claude or Codex, fresh context)   [worker — judgment]
          start native Codex correctness review in background
          ∥ audit implementer gate/spec/decision discipline directly
          → join both streams → verify → route (fix / ticket /
            tech-debt / rebut / needs-human) → push fixes
          → re-review? → escalate:
            small + simple + CI green → SELF-MERGE       [autonomous tier]
            else → confident-ready or needs-human        [human tier]
        → human handles escalated PRs on wake            [human — big/decision tier]
```

Load-bearing properties:

- **The runner job never executes PR code.** The workflow has no
  `actions/checkout`; the job only calls the locally installed dispatch
  script with a PR number. Untrusted code runs solely inside the daemon's
  worktree behind `--permission-mode auto` (a gated op becomes a `blocked`
  escalation; never `--dangerously-skip-permissions`).
- **The dispatch layer is entirely mechanical** — zero tokens until the
  daemon starts.
- **Confidence is bound to a commit.** A `synchronize` event (new push) on a
  confident-ready PR demotes the linked issue back to `status:in-review`.
- **Missed events self-heal.** GitHub queues runner jobs up to 24h;
  `review-dispatch.sh --sweep` (cron-able) catches open non-draft PRs with no
  bound reviewer — the same script, one code path.

## Components

### 1. `skills/orchestrating-daemons/scripts/daemon-spawn.sh` — `--no-wait` mode

New flag: spawn the `--bg` daemon, resolve its UUID from `claude agents`,
record the registry entry with `status=working`, and exit immediately instead
of polling for the first turn. Rationale: the blocking watcher would hold the
runner slot for the whole review turn, and a self-hosted runner processes one
job at a time — the next PR's trigger would queue behind a running review.
Reply capture still works afterward via `daemon-reply.sh` (it reads the live
transcript).

### 2. `skills/issue-tracker` — `confident-ready` state (schema only)

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `confident-ready` | open + `status:confident-ready` | PR rigorously reviewed; merge/close with confidence | optional (review summary) |

Sits between `in-review` and `done` in the state table. Changes:
`board-transition.sh` legality (`in-review → confident-ready` and repair
reachability like every open state), `board-lint.sh` known-label set,
`board-list.sh` / `board-map.sh` rendering (table, DAG, kanban column).
Additionally, `in-review` gains `needs-info` and `blocked` as legal targets —
the reviewer protocol's safety valves (impasse at the round cap, push
conflicts, precondition blocks) fire while the ticket is at `in-review`, and
the pre-existing table rejected those transitions (found at the final
whole-branch review; the escalation would have died at the board write).

### 3. New skill `skills/reviewing-prs/` — the product

- **`SKILL.md`** — the canonical Review Worker Protocol. Every dispatched
  worker explicitly invokes this skill; the bootstrap supplies its per-PR
  placeholders as runtime bindings.
- **`references/operation-manual.md`** — loop doctrine, setup, operating
  policy, the rubrics, authority model, tech-debt sink, and adoption checklist.
- **`references/review-worker-bootstrap.md`** — the thin per-PR spawn prompt:
  skill invocation plus dispatcher-owned runtime bindings and context.
- **`scripts/review-dispatch.sh <pr#> | --sweep`** — dedupe (a live daemon
  registry entry named `review-pr-<n>` means skip); context gathering
  (`gh pr view --json title,body,baseRefName,headRefName,headRefOid,url,labels`
  + linked issues as the union of `closingIssuesReferences` and close-keyword
  parsing of title/body — the same semantics as ida-solution's
  `issue-status-labels.yml`, which exists because stacked PRs onto integration
  branches leave `closingIssuesReferences` empty); detached worktree
  (`git worktree add --detach <repo>/.claude/worktrees/review-pr-<n> <headRefOid>`
  after fetching; a stale worktree with no live daemon is force-removed and
  re-added); bootstrap assembly (explicit `doperpowers:reviewing-prs`
  invocation + runtime bindings, PR body, and linked issue body); then a
  no-wait spawn:
  `daemon-spawn.sh "review-pr-<n>" "<prompt>" <worktree-path>` with the
  no-wait mode selected (exact surface — flag before positionals or
  `DAEMON_NOWAIT=1` env — decided at implementation; it must not collide
  with the existing positional `worktree`/`model` args).
  `--sweep` scans all open non-draft PRs and
  dispatches any with no live bound reviewer (also the respawn path for dead
  reviewer daemons).
- **`references/pr-review-dispatch.yml`** — workflow template:
  `pull_request: [opened, reopened, ready_for_review]`,
  `runs-on: [self-hosted, claude-review]`, gates (`draft == false`, actor
  allowlist = the repo owner — daemon PRs are authored with the owner's `gh`
  auth, so one entry covers the fleet), no checkout, calls the dispatch
  script via
  `${DOPERPOWERS_HOME:-$HOME/.claude/plugins/marketplaces/doperpowers}/skills/reviewing-prs/scripts/review-dispatch.sh`,
  `LOCAL_REPO` env for the canonical local clone.
- **`references/runner-setup.md`** — one-time Mac setup: runner registration,
  launchd service (`./svc.sh install && ./svc.sh start`), PATH requirements
  (node, claude, gh), `LOCAL_REPO`, runner label `claude-review`.

### 4. ida-solution deployment (consumer)

- Copy `pr-review-dispatch.yml` into `.github/workflows/`.
- `issue-status-labels.yml`: add `status:confident-ready` to `MANAGED`
  (single-label invariant), and add `synchronize` to the `pull_request`
  trigger with the demotion rule: linked issue currently
  `status:confident-ready` → assert `status:in-review`.
- Create labels `status:confident-ready` (issues) and `confident-ready` (PRs
  — deliberately unprefixed: `status:*` is board-node vocabulary and a PR is
  not a board node; sharing the repo-wide label namespace with the board
  would let PR labels leak into board queries).
- Create the standing pinned tech-debt issue (label `tech-debt`).
- Register the self-hosted runner per `runner-setup.md`.

Deployment scope is **ida-solution only** (private repo). doperpowers itself
(public) ships the skill and templates but gets no live runner — a
`pull_request`-triggered workflow on a self-hosted runner attached to a
public repo would let a stranger's fork PR reach the Mac.

## Review Worker Protocol (draft — final wording lands in SKILL.md)

```
You are a REVIEW worker for PR #<PR> (<url>) in <repo>, running unattended in
a detached worktree at the PR head. There is NO orchestrator in this loop:
your escalation targets are GitHub itself (labels, comments, tickets) and the
human on their next wake. The PR brief and its linked ticket brief are below.

ORIENT before anything else: the PR diff against its base
(git diff origin/<base>...HEAD), the PR body, and ticket #<N>'s brief.

REVIEW ENGINE: run the codex reviewer from the worktree root:
  node <codex-companion-path> adversarial-review --wait --base origin/<base> \
    "Review PR #<PR>: <title>"
(adversarial-review, not review: only that subcommand returns the structured
verdict/severity output the rubrics key on — stdout carries a "Verdict:
approve|needs-attention" line and "- [severity] title (file:lines)" findings.)
If it refuses because a review is already in progress, retry with backoff up
to 30 minutes, then fall back to a fresh Claude reviewer subagent at high
effort over the same diff. Record in the review-trail comment which engine
reviewed. NEVER run /codex:cancel — a busy lock may be another worker's live
review; you cannot distinguish wedged from busy.

EVALUATE every finding against codebase reality before acting:
- Never implement from the finding text alone — read the code it names first.
- Rebut with technical evidence: a rejected finding cites the code that
  refutes it.
- A finding you cannot verify is an escalation (needs-info), never a
  shrug-and-proceed.
- YAGNI-check scope-inflating suggestions ("implement this properly"): grep
  for actual usage before accepting the scope.
- Fix one finding at a time; test each before the next.

ROUTE each finding to exactly one bin:
- FIX NOW — valid and within this PR's scope: fix, test, commit, push
  (git push origin HEAD:<head-branch>; you are on a detached HEAD).
- TOO BIG — valid but new scope (a design fork, a new subsystem, or more than
  about half the original PR's size): register a ticket —
  board-register.sh "<title>" <category> --spawned-by <N> [--blocked-by ...]
  — and flesh out its pre-spec body. NEVER fix it in this PR.
- TOO SMALL — valid, non-blocking, and fixing it costs momentum or an
  unwarranted re-review round: append a structured comment to the standing
  tech-debt issue #<TD>.
- INVALID — does not hold against the code: rebuttal comment on the PR citing
  the refuting code.

RE-REVIEW (max 3 codex rounds total) when ANY: a critical/high finding led to
a fix; cumulative fixes exceed ~50 changed lines or 3 files; any fix changed
behavior (not comments/docs/renames). Skip when fixes were trivial or none.
At the cap with unresolved critical/high findings: do NOT grant confidence —
set ticket #<N> to needs-info with an impasse summary and end your turn.

ESCALATE when review is complete:
- SELF-MERGE tier — ALL must hold: final verdict approve (or only low
  findings, each explicitly routed); post-fix diff ≤ ~150 changed lines AND
  ≤ 5 files; zero touches on risk surfaces (CI/workflows, auth/security,
  migrations/schema, release/versioning); every CI check green — a repo with
  no checks disqualifies self-merge, no exceptions. Then merge with the
  repo's default method, post the review-trail comment, and finalize:
  board-transition.sh <N> done.
- HUMAN tier — anything else: label the PR confident-ready, run
  board-transition.sh <N> confident-ready "<review summary>", post the
  review-trail comment, end your turn.

YOUR AUTHORITY: ticket #<N>'s open states via board-transition.sh
(confident-ready / needs-info / blocked — note required for the latter two);
registering finding-tickets; merging ONLY in the self-merge tier; done ONLY
as post-merge finalize. NEVER: wontfix, other tickets' states, force-push,
opening your own PRs, /codex:cancel. Escalation discriminant: waiting on an
action/precondition → blocked; on knowledge or a human taste/product
decision → needs-info.

The review-trail comment on the PR records: engine and rounds run, every
finding with its bin and a one-line disposition, and the tier judgment with
the rubric clauses it satisfied.
```

A PR with no linked issue is still reviewed; every board write is simply
skipped and escalation lands on the PR alone (label + comment).

All thresholds (~50/~150 lines, 3 files / 5 files, 3 rounds, 30-minute
backoff, risk-surface list) are starting values living in one place — the
protocol text — and are expected to be tuned from shakedown evidence.

## Error handling

| Failure | Handling |
|---|---|
| Codex lock busy (parallel reviewer) | Bounded backoff ≤ ~30 min → Claude high-effort fallback reviewer; trail comment names the engine |
| Codex lock wedged (dead holder) | Same path — workers never cancel; `/codex:cancel` stays human |
| Runner offline > 24h | `review-dispatch.sh --sweep` on cron catches unbound PRs |
| Reviewer daemon dies mid-review | Sweep detects bound-but-dead session → fresh respawn from current head |
| Push rejected (head moved) | Fetch, rebase onto new head, retry once; repeated conflict → `needs-info` |
| Stale worktree, no live daemon | `git worktree remove --force` + re-add |
| Ambiguity above scope (taste/product fork in a finding) | `needs-info` with the question as the note; end turn |

## Acceptance (observable behavior)

1. **Trigger**: open a non-draft PR in ida-solution linked to a ticket. Within
   ~2 minutes, `daemon-list.sh` shows `review-pr-<n> … working`, and the
   Actions job that dispatched it completed in seconds.
2. **Self-merge tier**: a trivial PR (few lines, no risk surfaces, CI green)
   ends merged without human action; the PR carries a review-trail comment;
   the linked issue is closed (reason: completed); `board-lint.sh` exits 0.
3. **Human tier**: a sizable PR with planted critical-severity findings ends
   open with fix commits pushed by the worker, a `confident-ready` PR label,
   the issue at `status:confident-ready` (`board-list.sh confident-ready`
   shows it), and a review-trail comment recording ≥2 review rounds (the
   critical fix triggers Rubric 2).
4. **Too-big routing**: a planted architectural finding produces a new issue
   whose `board:meta` records `spawned-by: <reviewed ticket>`, and no fix for
   it appears in the PR.
5. **Too-small routing**: a planted nit produces a new comment on the
   standing tech-debt issue, not a PR commit.
6. **Confidence invalidation**: pushing a new commit to a confident-ready PR
   flips the linked issue back to `status:in-review` (workflow `synchronize`
   rule).
7. **Self-heal**: kill a working reviewer daemon; `review-dispatch.sh --sweep`
   spawns a replacement bound to the same PR.
8. **Schema**: `board-transition.sh <n> confident-ready "note"` succeeds from
   `in-review`, appears in `board-list.sh`/`BOARD.md`, and `board-lint.sh`
   passes with the new state present.

## Assumptions to verify at plan time

- ~~`codex-companion.mjs review` emits the structured JSON of
  `schemas/review-output.schema.json`~~ — RESOLVED at plan time: it does not;
  `adversarial-review` does (see Surprises & Discoveries). The protocol uses
  `adversarial-review`.
- The openai-codex plugin's companion script path is resolvable from a daemon
  session (newest version under
  `~/.claude/plugins/cache/openai-codex/codex/*/scripts/`).
- `gh` auth on the runner/daemons has repo scope for label creation, merge,
  and issue writes on ida-solution.

## Decision Log

- Decision: Approach B — new sibling skill `reviewing-prs` + minimal schema
  change in issue-tracker; rejected A (fold everything into issue-tracker)
  and C (resume the implementing daemon for review).
  Rationale: issue-tracker's SKILL.md is the orchestrator's manual and this
  loop has no orchestrator — different actor set, different lifecycle. C dies
  on author bias (the worker judging findings about its own code — the exact
  bias fresh-context review exists to fight), near-compaction context doing
  the judging, and zero coverage of PRs whose daemon is retired or never
  existed.
  Date/Author: 2026-07-08 / brainstorm session (human + Claude)

- Decision: Trigger via a self-hosted GitHub Actions runner on the Mac;
  rejected local-poll cron (mechanical, zero-token, but minutes of lag and no
  GitHub-visible trigger state), labels+poll, and fully-in-CI
  (claude-code-action + codex auth in CI — diverges from the local fleet).
  Rationale: human's explicit choice for true event-driven triggering; the
  security cost is contained by private-repo-only deployment, actor gating,
  and a no-checkout workflow.
  Date/Author: 2026-07-08 / human

- Decision: Two-tier merge authority, review workers only — self-merge for
  small/simple/low-stakes PRs with CI green; `confident-ready` tag + human
  merge for important/sizable PRs. No orchestrator judgment layer in this
  loop. Rejected: orchestrator-merges-on-wake; human-only merges.
  Rationale: human's explicit design — full autonomy where stakes are low,
  human authority where they are not; Rubric 3 encodes the tier split.
  Date/Author: 2026-07-08 / human

- Decision: Deploy to ida-solution only; doperpowers ships skill + templates
  but no live runner.
  Rationale: GitHub's own guidance — self-hosted runners on public repos
  expose the machine to fork PRs.
  Date/Author: 2026-07-08 / human

- Decision: Review workers register finding-tickets directly
  (`board-register.sh --spawned-by`), deviating from the implementing-worker
  propose-only policy.
  Rationale: propose-only requires an orchestrator to receive the proposal;
  this loop has none, and the deferral rule ("scope-outs become tickets the
  moment the deferral is decided") argues for immediate registration.
  Registration is additive and reversible — low blast radius.
  Date/Author: 2026-07-08 / Claude (flagged), human-approved via design

- Decision: Tech-debt sink = one standing pinned GitHub issue per consumer
  repo (comments as entries); rejected a tracked
  `docs/doperpowers/tech-debt-tracker.md` file (the agent-harness pattern).
  Rationale: parallel review workers on different branches editing one
  tracked file is a merge-conflict factory, and the edit lands inside the PR
  being reviewed — review bookkeeping polluting the reviewed diff.
  GitHub-native also matches the v7 board's single-source-of-truth doctrine.
  `issue-register` can promote comments to real tickets in gardening passes.
  Date/Author: 2026-07-08 / Claude (judgment delegated by human)

- Decision: The protocol embeds five distilled review-evaluation lines inline
  and does NOT invoke `receiving-code-review` at runtime.
  Rationale (human's amendment): that skill is author-seat, conversational
  doctrine — its STOP-and-ASK reflex is anti-autonomous in a no-orchestrator
  loop (turns end with questions nobody answers), and its core enemy
  (performative agreement toward a person) is absent when the worker didn't
  write the code and the reviewer is a one-shot structured report. The five
  transferable lines (verify against code; rebut with evidence; unverifiable
  → needs-info; YAGNI-check scope inflation; one fix at a time) are embedded
  with this provenance note. Structurally, Rubric 1's four-bin routing forces
  the verification step mechanically — a finding cannot be binned without
  judging validity against code.
  Date/Author: 2026-07-08 / human

- Decision: Detached worktree at the PR head SHA; fixes pushed via
  `git push origin HEAD:<branch>`. Rejected: native `--worktree` spawn flag;
  checking out the PR branch.
  Rationale: the native flag always creates a fresh `worktree-<name>` branch,
  and the PR branch is typically still checked out in the implementer's
  worktree — git's one-branch-one-worktree rule forbids a second checkout.
  Detached HEAD sidesteps the rule; the explicit refspec updates the remote
  without owning the branch locally.
  Date/Author: 2026-07-08 / Claude

- Decision: Workers never run `/codex:cancel`; lock contention resolves by
  backoff then Claude-fallback.
  Rationale: the codex-companion lock is machine-wide with no dead-holder
  detection — a worker cannot distinguish a wedged lock from another worker's
  live review, and cancelling would kill it.
  Date/Author: 2026-07-08 / Claude

- Decision: PR-side label is unprefixed `confident-ready`; issue-side is
  `status:confident-ready`.
  Rationale: labels are repo-wide and PRs share the namespace; `status:*` is
  board-node vocabulary and a PR is not a board node — reusing it would leak
  PR labels into board queries.
  Date/Author: 2026-07-08 / Claude

- Decision: Self-merge risk surfaces are additive — always-on categories
  (CI/workflows, auth, migrations, release, and the manifest file itself)
  PLUS an optional per-repo `.doperpowers/risk-surfaces.md` of concrete
  path/content rules, read from the PR's BASE ref (never HEAD). Self-merge is
  also forbidden onto the repo default branch, and gated behind
  `AUTO_MERGE_ENABLED` (default off = observation mode). Rejected: hardcoding
  concrete paths into the protocol (domain-specific, violates core's
  general-purpose rule); reading the manifest from HEAD (a PR could delist a
  surface it touches in the same commit); auto-merge on by default (no
  observation period before trusting the tier).
  Rationale: borrowed from ida-solution PR #282's PR-review-automation design
  after a head-to-head comparison — its concrete path-based Gate-A
  classification, explicit main-exclusion, and staged rollout flag were
  strictly better safety defaults than the original generic risk-surface
  list. Adapted to this loop's architecture: doperpowers core ships the
  MECHANISM (manifest read + injection, base-not-HEAD, additive-only, the
  two gates); the consumer repo ships the concrete surfaces. The
  base-not-HEAD read and "manifest file itself is always a risk surface"
  together close the self-delisting attack. #282's own contributions this
  loop deliberately did NOT adopt: hosted-Routine review (no verify-then-rebut
  discipline, no board integration), and deterministic-classifier-as-reviewer
  (this loop's reviewer is a fresh-context judgment agent, not a regex gate).
  Date/Author: 2026-07-09 / human (directive) + Claude (design)

## Surprises & Discoveries

- Observation: `/codex:review` cannot be invoked by the daemon as a slash
  command — the worker must call the companion script directly.
  Evidence: `commands/review.md` frontmatter carries
  `disable-model-invocation: true` (openai-codex plugin 1.0.5).

- Observation: the codex-companion serializes ALL reviews behind one
  machine-wide lock with no dead-holder detection; a wedged job silently
  blocks every subsequent review until a human cancels.
  Evidence: agent-harness `docs/exec-plans/tech-debt-tracker.md` records a
  resume job whose process died holding the lock ~2h51m, every later dispatch
  refused, cleared only by `/codex:cancel`.

- Observation: `daemon-spawn.sh`'s worktree flag cannot check out a PR
  branch — native `--worktree` always creates branch `worktree-<name>` — and
  the PR branch is usually already checked out in the implementer's worktree,
  which git forbids duplicating.
  Evidence: `skills/orchestrating-daemons/scripts/daemon-spawn.sh:37-40`;
  git's one-branch-one-worktree rule.

- Observation: the codex companion's plain `review` subcommand (what
  `/codex:review` runs) returns free text only; the structured
  verdict/severity JSON of `schemas/review-output.schema.json` is produced
  solely by `adversarial-review`, whose rendered stdout carries a parseable
  `Verdict: approve|needs-attention` line and `- [severity] title
  (file:lines)` finding lines.
  Evidence: `codex-companion.mjs:415` passes `outputSchema` only on the
  adversarial path; `lib/render.mjs` `renderReviewResult` prints the
  `Verdict:` / `[severity]` lines (openai-codex plugin 1.0.5).

- Observation: ambient `set -euo pipefail` is not an error-handling strategy
  for a per-item loop body. The plan's original sweep loop let one PR's
  failure abort the whole pass; the first fix (`run_for … || report`)
  suspended errexit through the entire call tree — so a mid-dispatch
  `gh pr view` failure then dispatched a daemon with the PREVIOUS PR's head
  SHA and an empty prompt (cross-PR contamination), while `set -u` (not
  suspended by `||`) still killed the pass when the FIRST PR failed. The
  shipped design guards every critical step in `dispatch_one` explicitly
  (capture-before-eval, per-step `|| return 1`, empty-prompt refusal).
  Evidence: task-5 review rounds 1–3, reproduced live against the committed
  script each round; regression sections "sweep failure isolation" and
  "dispatch guards" in tests/reviewing-prs/test-review-dispatch.sh.

- Observation: a hermetic test suite that `export`s an env var its script
  merely assigns can mask a production-only failure class. `review-dispatch.sh`
  assigned (never exported) `DAEMON_HOME`; its registry-scan python read
  `os.environ["DAEMON_HOME"]`; the test suite exported the var, so 37 asserts
  ran green while both production invocation paths (launchd runner, cron
  sweep) would KeyError — silently degrading dedupe to always-dispatch
  (duplicate reviewers every sweep). Regression test now runs the dispatcher
  under `env -u DAEMON_HOME`.
  Evidence: final whole-branch review (Opus fallback) finding #1, reproduced
  on the runner host; fix commit 4aa7623.

- Observation: the codex-companion dead-holder failure mode is real and was
  observed during this very build — the final whole-branch review job's
  process died ~40 min in while companion status reported "running" for 4.5+
  hours, wedging the machine-wide lock until a human cancelled. This
  validates the protocol's rule that workers NEVER run /codex:cancel and
  must backoff-then-fallback to a Claude reviewer: the wedge is
  indistinguishable from a long-running live review from the inside.
  Evidence: job task-mrc3w7vc-0nhtj6 (log mtime 22:24 vs 02:44 status check,
  no live process); partial findings salvaged and confirmed/extended by the
  fallback reviewer.

- Observation: ida-solution stacks PRs onto integration branches
  (`feat/mN-*`), so GitHub's `closingIssuesReferences` is empty for them and
  native auto-close never fires; PR base refs vary per PR.
  Evidence: header comments and `linkedIssues()` implementation in
  ida-solution `.github/workflows/issue-status-labels.yml`.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-07-08: Initial spec from brainstorm (controlled track). Decision Log
  seeded with the approach fork, trigger fork, merge-authority design,
  deploy scope, and the receiving-code-review amendment.
- 2026-07-08 (plan-writing): review engine corrected `review` →
  `adversarial-review` — plan-time code inspection showed only the
  adversarial path returns the structured verdict/severity the rubrics need.
  Assumption resolved, protocol draft updated, discovery recorded.
- 2026-07-09 (final review): `in-review` gains `needs-info`/`blocked` legal
  edges (component 2 amended) — the protocol's escalations were illegal
  against the pre-existing table. Two Surprises added: the unexported
  DAEMON_HOME production gap, and the codex dead-holder wedge observed live
  during this build's own final review.
- 2026-07-09 (post-ship, v7.9.1): adopted two safety defaults from
  ida-solution PR #282's competing design — a per-repo additive
  risk-surface manifest (base-not-HEAD read) and staged-rollout self-merge
  (main-exclusion + `AUTO_MERGE_ENABLED`, default off). Protocol ESCALATE
  block, `review-dispatch.sh` (4 new injected placeholders), SKILL.md merge
  authority + adopting checklist, workflow/runner templates, and the dispatch
  test suite (+5 asserts incl. the base-not-HEAD self-delisting repro) all
  updated. See the new Decision Log entry dated 2026-07-09. Opus review pass:
  READY — verified the base-not-HEAD security core, errexit/nounset safety,
  and placeholder integrity all hold; fixed its one MEDIUM (the AUTHORITY
  recap could be read as licensing a merge in observation mode → now gated on
  "auto-merge is on", pinned by a regression assert) and two LOW (off-state
  prose wording; full-clone requirement for the base read, now documented).
- 2026-07-13 (fix-forward routing): flipped the finding-routing default,
  adopting agent-harness's burden-of-proof direction after SD-5 showed the
  old default in action (7/7 findings routed FIX NOW, 3 engine rounds).
  The engine's native severity is now the blocker bit: critical/high (P1
  class) → FIX NOW; everything below → new LOG bin (renamed from
  TOO SMALL), deferred to the standing tech-debt issue by default —
  promoting a non-blocker to an in-loop fix is the argued exception, the
  reverse of the old triple-condition deferral. RE-REVIEW gains a
  statelessness clause: re-flagged already-logged findings are matched by
  file+substance, not re-fixed/re-logged/re-counted; exit = no NEW
  blocker, not a clean report. SELF-MERGE wording aligned ("non-blocker
  findings, each explicitly routed"). Protocol + SKILL.md tech-debt sink
  updated; spec body §Review Worker Protocol left as the historical draft.
- 2026-07-14 (skill-entrypoint restructure): restored the runtime boundary the
  original design intended. `SKILL.md` is now the canonical Review Worker
  Protocol; `review-dispatch.sh` emits a thin bootstrap that explicitly invokes
  the skill and supplies all instance placeholders as runtime bindings. The
  former operator-oriented skill body moved intact to
  `references/operation-manual.md`. Review policy and routing are unchanged.
- 2026-07-14 (split review responsibilities): native Codex review returned to
  pure correctness with no ticket criteria or custom developer instructions.
  The outer Review Worker now starts Codex in the background, independently
  audits whether the Implement Worker passed the substantive ticket gate and
  escalated human-grade forks, records that audit before reading Codex output,
  then joins both streams. The linked issue body is primary specification;
  only documents it explicitly references are secondary, resolved from the PR
  base or another immutable revision rather than PR head. Human answers
  recorded on a parked ticket before resume are authoritative ticket content
  for the answered fork. Protocol blockers route `needs-human`, settled
  requirement mismatches are fix-required, weak process evidence alone is a
  non-blocking audit note, and unverifiable claimed validation is a separate
  confidence-blocking evidence finding even on ticketless PRs. Direct review also
  exposed that consumer-owned `.agents/skills` can prevent native discovery;
  the bootstrap now binds the same installed version's absolute `SKILL.md` as
  a canonical fallback rather than duplicating the protocol. See
  `docs/doperpowers/execplans/2026-07-14-split-review-responsibilities.md`.
