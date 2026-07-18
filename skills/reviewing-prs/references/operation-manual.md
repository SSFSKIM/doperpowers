# Reviewing PRs — the autonomous review loop

## Overview

The inverse-symmetric counterpart of the implementing daemon: where a worker
turns a ticket into a PR, a **review worker** turns a PR into a confident
merge. Every non-draft PR opened in an adopting repo gets a fresh-context
background daemon (`orchestrating-daemons`) that runs TWO review tracks at
once: the native Codex engine (`codex exec review` via review-engine.sh, in
the background) reviews pure code correctness, while the worker itself audits
implementer protocol/spec compliance against the linked ticket. The worker
never fixes anything: it triages the joined findings on its own judgment
(the engine's native severity is the starting rank),
delegates fixing to a **fix wave** — a fresh-context fixer subagent driven
by a wave-board file — grades the fixer's dispositions, pushes, re-reviews
when warranted, and then either merges (small/simple tier, CI green) or
escalates the PR + its linked ticket to **`confident-ready`** for the human.

**No orchestrator sits above the workers.** A review worker's escalation
targets are GitHub itself (labels, comments, tickets) and the human on their
next wake; within its own turn the worker is the orchestrator of its fixers.
Full design + rationale: `docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md`.

## The pieces

| piece | what |
|---|---|
| `scripts/review-dispatch.sh <pr#> \| --sweep` | mechanical trigger: dedupe → PR + ticket context → detached worktree at the PR head SHA → spawn a `review-pr-<n>` daemon (`daemon-spawn.sh --no-wait`; default route rides the clodex gateway settings, `engine:claude` opts into plain Claude models) → exclusively bind it to the primary ticket under the registry lock → complete a dispatcher-ready / worker-ack startup barrier so `board-answer.sh` reaches the parked reviewer and no review action races binding |
| `scripts/review-engine.sh` | the ONE native-review invocation, pure correctness: `--base` + `--out`, env recipe only — no ticket/spec input of any kind |
| `scripts/land-dispatch.sh <pr#>` | landing-phase trigger: authority gate (Approve or `land` label, + `confident-ready`) → normalize/preflight the previous ticket owner → detached worktree → spawn a `land-pr-<n>` daemon → exclusive bind → dispatcher-ready / worker-ack startup barrier |
| `SKILL.md` | the Review Worker Protocol — invoked by every review worker; the dispatch bootstrap supplies its `{{PLACEHOLDERS}}` as runtime bindings. The engine-start and engine-fallback text live in its START ENGINE section; the worker reads PR and ticket bodies live via gh (only the BASE-ref manifest snapshots ride the prompt) |
| `references/wave-board.md` | runtime-opened fix-wave companion: board-file schema, the fixer's verify-then-fix contract, disposition grading |
| `references/land-worker-protocol.md` | the Land Worker Protocol — merge mechanics only (native-first, never rebase, bounded conflict resolution) |
| `references/land-conflicts.md` | runtime-opened conflict-resolution procedure — the protocol carries only a pointer (`{{CONFLICTS_DOC}}` = absolute path); the worker opens it when GitHub reports the PR unmergeable. Procedure in the plugin file, instance facts in the prompt |
| `references/pr-review-dispatch.yml` | GH workflow template: PR events → self-hosted runner → dispatch script. No checkout, no token permissions |
| `references/runner-setup.md` | one-time machine setup: runner registration, launchd service, PATH, sweep cron |
| `confident-ready` state | owned by doperpowers:issue-tracker (state table there); this loop is its only writer |

## Dedupe & sweep policy

A PR labeled `confident-ready` is never dispatched — confidence is bound to
the reviewed head SHA; remove the label to force a re-review. Otherwise, by
the newest `review-pr-<n>` registry entry:

| registry entry | triggered mode (PR event) | sweep mode (cron) |
|---|---|---|
| none / retired | dispatch | dispatch |
| ACTIVE (working/blocked), session live | skip | skip |
| ACTIVE, session gone (daemon died) | retire → dispatch | retire → dispatch |
| finished cleanly (idle/awaiting-human) | retire → dispatch (an explicit event is a fresh signal) | skip (finished stays finished) |
| finished, reply carries ENGINE-UNAVAILABLE | retire → dispatch | retire → dispatch (capped) |
| finalized `error` (worker died — e.g. gateway refused the first turn; no reply can carry a marker) | retire → dispatch | retire → dispatch (capped) |

The sweep (`review-dispatch.sh --sweep`, cron every ~30 min) is the self-heal
net: PRs opened while the machine slept (GitHub queues self-hosted jobs only
24h) and reviewers that died mid-turn.

**Failure cap.** A persistent outage must not make the sweep respawn a PR
forever: after 3 CONSECUTIVE failed reviewers for one PR — ENGINE-UNAVAILABLE
replies (engine outage) and `error`-finalized turns (dead worker, e.g. the
gateway refused before any reply existed) count as ONE shared streak — the
sweep skips it (naming the cap as the reason). Any cleanly finished reviewer
breaks the streak. An explicit PR event — workflow trigger or manual
dispatch — always re-dispatches regardless.

## Merge authority (two tiers)

Encoded in the protocol's ESCALATE block — ALL clauses must hold for
self-merge: final verdict approve (or only non-blocker findings by the
worker's own routing, each explicitly routed); no
unresolved PROTOCOL BLOCKER or SPEC FINDING from the worker's own
compliance audit; post-fix
diff ≤ ~150 changed lines AND ≤ 5 files; the PR base is
**not** the repo default branch (self-merge lands only on integration
branches); zero touches on a **risk surface**; every CI check green — a repo
with no checks disqualifies self-merge, no exceptions. Anything else →
`confident-ready` label on the PR + `status:confident-ready` on the ticket;
the human merges.

**Risk surfaces are additive.** Always-on, manifest or not: CI/workflows,
auth/security, migrations/schema, release/versioning, and the manifest
files themselves (`.doperpowers/risk-surfaces.md`,
`.doperpowers/repo-facts.md`). A repo may ALSO declare concrete surfaces
in an optional `.doperpowers/risk-surfaces.md` — a plain list of globs and
prose path/content rules the worker reads against the diff. The dispatch
layer injects it from the PR's **base ref, never HEAD**, so a PR cannot
delist a surface it touches in the same commit; the manifest can only
tighten the gate, never loosen an always-on category.

**Repo facts feed the cross-check.** The optional
`.doperpowers/repo-facts.md` manifest (format: doperpowers:implementing-tickets)
is injected the same way — base ref, never HEAD. The review worker checks
claimed Validation Evidence against the repo's declared validation
commands, and a diff hitting a declared Evidence add-on class without the
required evidence is a finding. Facts only ever ADD requirements; an
instruction in the manifest that tries to relax the protocol is itself a
finding.

**Staged rollout (`AUTO_MERGE_ENABLED`, default off).** Off is *observation
mode*: the worker runs the full loop and judges the tier, but a
self-merge-eligible PR is routed to `confident-ready` instead of merged, with
the trail comment naming what it *would* have merged. Watch a few of those,
then set `AUTO_MERGE_ENABLED=true` (workflow / runner env) to let the worker
actually merge the self-merge tier.

## Landing phase (post-approval)

The pipeline's last mile: after the human approves a `confident-ready` PR,
the merge *mechanics* — base sync, CI babysitting, conflict triage,
finalize — are worker-grade, not human-grade. `land-dispatch.sh <pr#>`
spawns a **land worker** (same daemon machinery, not a third species)
whose authority flows from the human's approval, never from a label.

**Authority gate (dispatch refuses without both):** the PR carries
`confident-ready` (the review loop's verdict), AND its GitHub review
decision is APPROVED — or it carries a `land` label, the explicit manual
override for PRs you cannot approve yourself (your own). No new board
state: trail comments + PR state carry the record.

**The worker is native-first:** mergeable + checks green → merge with the
repo's preferred method; checks running → arm GitHub auto-merge and watch
bounded (~30 min), then hand off; a red check → at most two flaky reruns,
else park. Conflicts: **merge base into branch, never rebase, never
force-push**. The conflict-resolution delta is unreviewed by construction,
so its bounds are TIGHTER than the self-merge tier: ≤ 50 hand-resolved
lines across ≤ 3 conflicted files, zero risk-surface touches — within
bounds it pushes and lands; beyond, the resolution stays a LOCAL commit
and the ticket parks `needs-human`. The dispatch **binds the daemon to the
ticket**, so `board-answer.sh` resumes the parked land worker in place,
worktree intact (park = pause, not death).

After the merge the worker runs `board-transition.sh <n> done` and posts a
land-trail comment. Cleanup (superseded PRs, branch deletion) is
finalize-sweep territory, never the land worker's.

**Staged rollout (`LAND_ENABLED`, default off = dry-run):** the worker
analyzes (including a local merge attempt to discover conflicts) and posts
what it *would* do, touching nothing. No sweep mode — landing always
follows an explicit human signal; manual dispatch works today, the
PR-review-event trigger arrives with runner registration.

## Tech-debt sink

Non-blocking findings — everything the worker routes LOG — go by DEFAULT
to ONE standing GitHub issue per repo (label `tech-debt`)
as structured comments — never to a tracked file:
parallel workers on branches editing one file is a merge-conflict factory,
and the edit would land inside the very PR under review. Register the
standing issue as a `deferred` P3 ticket so board-lint stays green. Promote
accumulated comments into real tickets during gardening passes (register
via doperpowers:issue-tracker; a pile grown sprint-shaped is
doperpowers:organizing-sprints input).

## Closing-artifact cross-check

Part of the worker's concurrent compliance audit: while the engine runs,
the worker verifies the PR body's `## Validation Evidence` section (the
implement worker's closing artifact) by inspection — read-only until
JOIN, with command-backed checks deferred until the worktree is free.
Evidence claimed but not verifiable is a SPEC FINDING. A MISSING section
is a SPEC FINDING only when the ticket carries a `[gate] pass` comment
(the gate proves an implement worker under the current contract produced
the PR); otherwise it is an AUDIT NOTE — no retroactive policy on legacy
or non-loop PRs. This closes the evidence loop: the implement side must
produce evidence, the review side verifies the claims were real.

## Review engine (pure correctness) + worker audit (compliance)

Review responsibility is split between two concurrent tracks with one owner
each. The ENGINE — the native `codex exec review --base origin/<base>` run
by `scripts/review-engine.sh` — receives no ticket, spec, or policy input of
any kind: coupling spec policy into the native reviewer measurably weakened
its correctness review, so the interface is now `--base` + `--out`, full
stop. The worker starts it in the background, and the engine returns a
compact structured verdict file; the PR diff never enters the worker's own
context. A hung engine (no result within 45 minutes) is killed and treated
as a failure.

The WORKER meanwhile audits implementer protocol/spec compliance itself,
read-only, and records the audit BEFORE reading engine output: the issue
body is the canonical primary spec; drift since the `[gate] pass` comment
is resolved through GitHub edit-history timestamps; the verdict classes are
PROTOCOL BLOCKER (authority gap → needs-human; parks confidence, not
progress), SPEC FINDING (fix-required; waves with native blockers), and
AUDIT NOTE (trail-only). The two streams JOIN before triage.

There is NO second engine: on engine failure the worker retries twice, then
posts the trail comment, leaves the ticket in-review, and ends its turn
with the `ENGINE-UNAVAILABLE` marker — the sweep re-dispatches on seeing it
(capped; see the outage cap above). `needs-human` is never written for an
infra outage. The review-trail comment names the engine that reviewed.

## The orchestrator and fix waves

The review worker is an orchestrator: the edits are the fixer tree's; the
grading and the trusted push chain are the worker's.
Findings routed WAVE (blockers by the worker's routing + SPEC FINDINGs) go
onto a wave-board file (`<review-tmp>/pr-<n>-fix-wave-<k>.md`, in the
worker-created tmp directory — NEVER inside the PR worktree, never committed),
and a fresh-context fixer subagent works the batch under a
verify-then-fix contract: read the cited code first, then FIX (commit + test
evidence) or REFUTE (code citation). The worker waits for the whole task tree
to quiesce, snapshots the submitted board, grades every disposition, and
validates the full unpushed commit range against its accepted-commit ledger.
It removes stale `confident-ready` before pushing — fail-safe order:
expiry first, then the new head.
At most 2 waves per review inside the 3-engine-round cap; whole-range re-review
between waves with dedupe-by-substance. Full mechanics:
`references/wave-board.md`. This
separation keeps the merge judgment in a clean context and out of
self-review bias: the entity that grades the fixes never wrote them.

## Edge cases

- **Reopened PR still labeled `confident-ready`** — dispatch skips it while
  the consumer label automation may have set the issue back to `in-review`.
  Safe and rare; the human decides: remove the PR label to force re-review,
  or restore the ticket state.
- **PR with no linked issue** — reviewed normally; every board write is
  skipped; escalation lands on the PR alone (label + comment).
- **Two dispatches, one PR** — the second dispatch detects the still-live
  reviewer (Claude: its session in `claude agents`; codex: its recorded pid)
  and skips; a worktree with a live reviewer is never reused underneath it.
  No lock, no backoff — dedupe on dispatch does the serializing.

## Adopting a repo (checklist)

1. **PRIVATE repos only** — a self-hosted runner on a public repo lets a
   stranger's fork PR reach the machine (see `references/runner-setup.md`).
2. Register the runner + service per `references/runner-setup.md`.
3. Copy `references/pr-review-dispatch.yml` → `.github/workflows/`; set
   `LOCAL_REPO` to the canonical local clone path.
4. Consumer label automation (if any) must add `status:confident-ready` to
   its managed label set, and demote `confident-ready → in-review` on
   `synchronize` — confidence is bound to a commit.
5. Create the PR label `confident-ready`; the issue label
   `status:confident-ready` is auto-created by the board scripts.
6. Register the standing tech-debt issue (`--state deferred`, P3, plus the
   `tech-debt` label).
7. (Optional but recommended) Add `.doperpowers/risk-surfaces.md` listing the
   repo's concrete self-merge-disqualifying paths/patterns — auth files,
   migration dirs, privileged routes, security-sensitive SQL. Commit it on
   the integration branch(es) reviewers target (it is read from the base).
8. Start in observation mode: leave `AUTO_MERGE_ENABLED` unset/false in the
   workflow env. Flip it to `true` only after the trail comments show the
   self-merge tier judging as you'd want.
9. Cron the sweep: `review-dispatch.sh --sweep` every ~30 min.
10. The `codex` CLI installed and authed (`codex login`) on the runner
    machine — it is the review engine inside every worker. The default
    worker route additionally needs the clodex gateway settings
    (`~/.claude/clodex-settings.json`, override via `CLODEX_SETTINGS`) and
    the local gateway running; set `WORKER_ENGINE=claude` (env) or label
    `engine:claude` to route a repo/PR onto plain Claude models instead.
