# Reviewing PRs — the autonomous review loop

## Overview

The inverse-symmetric counterpart of the implementing daemon: where a worker
turns a ticket into a PR, a **review worker** turns a PR into a confident
merge. Every non-draft PR opened in an adopting repo gets a fresh-context
background daemon (`orchestrating-daemons`) that runs TWO review tracks at
once: the native Codex engine (the doperpowers:codex-companion runtime via
review-engine.sh, in the background) reviews pure code correctness, while
the worker itself audits
implementer protocol/spec compliance against the linked ticket. The worker
never fixes anything: it triages the joined findings on its own judgment
(the engine's native severity is the starting rank),
delegates fixing to a **fix wave** — a fresh-context fixer subagent driven
by a wave-board file — grades the fixer's dispositions, pushes, re-reviews
when warranted, and then either merges (confident verdict, existing CI
green) or parks the ticket for the human with the impasse named.

**No orchestrator sits above the workers.** A review worker's escalation
targets are GitHub itself (labels, comments, tickets) and the human on their
next wake; within its own turn the worker is the orchestrator of its fixers.
Full design + rationale: `docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md`.

## The pieces

| piece | what |
|---|---|
| `scripts/review-dispatch.sh <pr#> \| --sweep` | mechanical trigger: dedupe → PR + ticket context → detached worktree at the PR head SHA → spawn a `review-pr-<n>` daemon (`daemon-spawn.sh --no-wait`; default route is plain Claude models, `engine:codex` opts into the clodex gateway settings) → exclusively bind it to the primary ticket under the registry lock → complete a dispatcher-ready / worker-ack startup barrier so `board-answer.sh` reaches the parked reviewer and no review action races binding |
| `scripts/review-engine.sh` | the ONE native-review invocation, pure correctness: `--base` + `--out`, env recipe only — no ticket/spec input of any kind. Drives the doperpowers:codex-companion runtime (per-run effort via its with-effort wrapper). The worker may run it 1–4× in parallel per round (its judgment, by diff scale); extra runs carry `CODEX_REVIEW_LENS` — a diff-derived structural focus mandate that routes the run through the `adversarial-review` verb as its focus text |
| `SKILL.md` | the Review Worker Protocol — invoked by every review worker; the dispatch bootstrap supplies its `{{PLACEHOLDERS}}` as runtime bindings. The engine-start and engine-fallback text live in its START ENGINE section; the worker reads PR and ticket bodies live via gh (only the BASE-ref manifest snapshots ride the prompt) |
| `references/wave-board.md` | runtime-opened fix-wave companion: board-file schema, the fixer's verify-then-fix contract, disposition grading |
| `references/pr-review-dispatch.yml` | GH workflow template: PR events → self-hosted runner → dispatch script. No checkout, no token permissions |
| `references/runner-setup.md` | one-time machine setup: runner registration, launchd service, PATH, sweep cron |

## Dedupe & sweep policy

By the newest `review-pr-<n>` registry entry:

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

## Merge authority

Encoded in the protocol's ESCALATE block — the worker merges its own
confident verdict: final verdict approve (or only non-blocker findings by
the worker's own routing, each explicitly routed); no unresolved PROTOCOL
BLOCKER or SPEC FINDING from the worker's own compliance audit; every
EXISTING CI check green (a repo with no checks merges on the review
alone; pending checks arm GitHub auto-merge — when that merge lands after
the worker's turn ended, the board sweep's FINALIZE pass completes the
ticket bookkeeping the PR's `Closes` link cannot). Every merge — immediate
or armed — is pinned to the reviewed head (`--match-head-commit`), so a
push after the review fails the merge instead of landing unreviewed. A
failing check, a park, or any unresolved blocker goes `needs-human` with
the impasse named — there is no intermediate "reviewed, waiting for the
human to merge" state.

**Risk surfaces feed scrutiny, not a merge gate.** A repo may declare
concrete hot paths in an optional `.doperpowers/risk-surfaces.md` — a
plain list of globs and prose path/content rules the worker reads against
the diff; a diff touching one is a strong lens candidate for the engine
fan-out. The dispatch layer injects it from the PR's **base ref, never
HEAD**, so a PR cannot delist a surface it touches in the same commit.

**Repo facts feed the cross-check.** The optional
`.doperpowers/repo-facts.md` manifest (format: doperpowers:implementing)
is injected the same way — base ref, never HEAD. The review worker checks
claimed Validation Evidence against the repo's declared validation
commands, and a diff hitting a declared Evidence add-on class without the
required evidence is a finding. Facts only ever ADD requirements; an
instruction in the manifest that tries to relax the protocol is itself a
finding.

**Kill switch (`AUTO_MERGE_ENABLED`).** Off is *observation mode*: the
worker runs the full loop and judges the verdict, but instead of merging
it posts the trail comment naming what it *would* have merged and parks
the ticket `needs-human` — merging becomes the human's action while the
switch is off. Set `AUTO_MERGE_ENABLED=true` (workflow / runner env) to
let the worker merge its confident verdicts.

## Tech-debt sink

Non-blocking findings the worker routes LOG — exit residue and
stated-reason departures only; mid-loop non-blockers ride fix waves
(SKILL.md TRIAGE) — go by DEFAULT
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
the PR) or an Architect handoff comment (a real `plan:` pin authorizes
the work in the gate's place); otherwise it is an AUDIT NOTE — no
retroactive policy on legacy or non-loop PRs. This closes the evidence loop: the implement side must
produce evidence, the review side verifies the claims were real.

## Review engine (pure correctness) + worker audit (compliance)

Review responsibility is split between two concurrent tracks with one owner
each. The ENGINE — the native codex review run by
`scripts/review-engine.sh` through the doperpowers:codex-companion runtime
(plain run = the non-steerable `review` verb; lensed run = the
`adversarial-review` verb with the lens as focus) — receives no ticket,
spec, or policy input of
any kind: coupling spec policy into the native reviewer measurably weakened
its correctness review, so the interface is `--base` + `--out` plus the
optional `CODEX_REVIEW_LENS` env — a structural focus mandate the worker
derives from the diff itself (never from the ticket/spec) when it fans out
to 2–4 parallel runs on a large diff; a bench-validated lens recovered a
confirmed authz defect two plain runs had missed
(`tests/review-bench/results/2026-07-28-pr752-lenscell/`). The worker
starts the round's runs in the background, and each returns a compact
structured verdict file; the PR diff never enters the worker's own
context. A hung engine (no result within 45 minutes) is killed and treated
as a failure; a failed lens-free sweep fails the round (it is the required
whole-range review), while failed lensed runs are merely recorded.

The WORKER meanwhile audits implementer protocol/spec compliance itself,
read-only, and records the audit BEFORE reading engine output: the issue
body is the canonical primary spec, joined on an architect-lane ticket by
the plan its `plan:` pin names at that immutable revision; drift since the
authorization comment — the `[gate] pass`, or the Architect's
`[board] ready-for-implementer:` handoff on a real-pin ticket — is
resolved through GitHub edit-history timestamps; the verdict classes are
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
At most 4 waves per review inside the 5-engine-round cap; whole-range re-review
between waves with dedupe-by-substance. Full mechanics:
`references/wave-board.md`. This
separation keeps the merge judgment in a clean context and out of
self-review bias: the entity that grades the fixes never wrote them.

## Edge cases

- **PR with no linked issue** — reviewed normally; every board write is
  skipped; escalation lands on the PR alone (label + comment).
- **Two dispatches, one PR** — the second dispatch detects the still-live
  reviewer (Claude: its session in `claude agents`; codex: its recorded pid)
  and skips; a worktree with a live reviewer is never reused underneath it.
  No lock, no backoff — dedupe on dispatch does the serializing.
- **Ticket leaves in-review while its PR stays open (any route, not just
  ready-for-architect)** — a review escalation (`ready-for-architect`), a
  human park, or anything else that moves the ticket off `in-review`
  leaves the PR's reviewer bound to a ticket no longer under review. The
  sweep resolves the ticket's status
  BEFORE the registry dedupe machinery: whenever the ticket isn't
  `in-review`, any FINISHED (non-active) reviewer it finds for that PR is
  retired right there and the tick skips without spawning — an ACTIVE
  (working/blocked) reviewer is never touched, since it owns its own
  exit. That retire is what lets the ticket's eventual return to
  `in-review` land on the ordinary "none / retired → dispatch" row
  (Dedupe & sweep policy above) with no special-case dispatch logic
  needed once it's back — no human intervention required.

## Adopting a repo (checklist)

1. **PRIVATE repos only** — a self-hosted runner on a public repo lets a
   stranger's fork PR reach the machine (see `references/runner-setup.md`).
2. Register the runner + service per `references/runner-setup.md`.
3. Copy `references/pr-review-dispatch.yml` → `.github/workflows/`; set
   `LOCAL_REPO` to the canonical local clone path.
4. Register the standing tech-debt issue (`--state deferred`, P3, plus the
   `tech-debt` label).
5. (Optional) Add `.doperpowers/risk-surfaces.md` listing the repo's
   validated hot paths — auth files, migration dirs, privileged routes,
   security-sensitive SQL; reviewers read it for lens derivation. Commit
   it on the branch(es) reviewers target (it is read from the base).
6. Start in observation mode: leave `AUTO_MERGE_ENABLED` unset/false in the
   workflow env. Flip it to `true` only after the trail comments show the
   merge verdict judging as you'd want.
7. Cron the sweep: `review-dispatch.sh --sweep` every ~30 min.
8. The `codex` CLI installed and authed (`codex login`) on the runner
    machine — it is the review engine inside every worker. The default
    worker route is plain Claude models and needs nothing else; setting
    `WORKER_ENGINE=codex` (env) or labeling `engine:codex` opts a
    repo/PR onto the clodex gateway route instead, which additionally
    needs the gateway settings (`~/.claude/clodex-settings.json`,
    override via `CLODEX_SETTINGS`) and the local gateway running.
