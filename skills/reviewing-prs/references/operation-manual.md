# Reviewing PRs — the autonomous review loop

## Overview

The inverse-symmetric counterpart of the implementing daemon: where a worker
turns a ticket into a PR, a **review worker** turns a PR into a confident
merge. Every non-draft PR opened in an adopting repo gets a fresh-context
background daemon (`orchestrating-daemons`) that reviews it with the native
Codex reviewer (`codex exec review` via review-engine.sh), verifies every finding
against the code, applies the valid fixes, re-reviews
when the fixes warrant it, and then either merges it (small/simple tier, CI
green) or escalates the PR + its linked ticket to **`confident-ready`** for
the human.

**This loop has NO orchestrator.** A review worker's escalation targets are
GitHub itself (labels, comments, tickets) and the human on their next wake.
Full design + rationale: `docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md`.

## The pieces

| piece | what |
|---|---|
| `scripts/review-dispatch.sh <pr#> \| --sweep` | mechanical trigger: dedupe → PR + ticket context → detached worktree at the PR head SHA → spawn a `review-pr-<n>` daemon (`daemon-spawn.sh --no-wait`) |
| `scripts/review-engine.sh` | the pure native-correctness invocation and proven nested environment recipe; both worker species call it while the outer worker owns spec/protocol audit |
| `scripts/land-dispatch.sh <pr#>` | landing-phase trigger: authority gate (Approve or `land` label, + `confident-ready`) → detached worktree → spawn a `land-pr-<n>` daemon → bind it to the ticket |
| `SKILL.md` | the Review Worker Protocol — invoked by every review worker; the dispatch bootstrap supplies its `{{PLACEHOLDERS}}` as runtime bindings |
| `references/review-worker-bootstrap.md` | thin skill invocation + runtime bindings; also carries the same installed version's absolute `SKILL.md` fallback when a consumer-owned `.agents/skills` prevents native discovery |
| `references/land-worker-protocol.md` | the Land Worker Protocol — merge mechanics only (native-first, never rebase, bounded conflict resolution) |
| `references/land-conflicts.md` | runtime-opened conflict-resolution procedure — the protocol carries only a pointer (`{{CONFLICTS_DOC}}` = absolute path); the worker opens it when GitHub reports the PR unmergeable. Procedure in the plugin file, instance facts in the prompt |
| `references/pr-review-dispatch.yml` | GH workflow template: PR events → self-hosted runner → dispatch script. No checkout, no token permissions |
| `references/runner-setup.md` | one-time machine setup: runner registration, launchd service, PATH, sweep cron |
| `references/engine-blocks/` | engine block + the single shared fallback block; `review-dispatch.sh` resolves the worker engine (label → `WORKER_ENGINE` → codex) |
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
| finished (idle/error/awaiting-human) | retire → dispatch (an explicit event is a fresh signal) | skip (finished stays finished) |
| finished, reply carries ENGINE-UNAVAILABLE | retire → dispatch | retire → dispatch |

The sweep (`review-dispatch.sh --sweep`, cron every ~30 min) is the self-heal
net: PRs opened while the machine slept (GitHub queues self-hosted jobs only
24h) and reviewers that died mid-turn.

## Merge authority (two tiers)

Encoded in the protocol's ESCALATE block — ALL clauses must hold for
self-merge: final verdict approve (or only low findings, each explicitly
routed); post-fix diff ≤ ~150 changed lines AND ≤ 5 files; the PR base is
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

Non-blocking findings — everything below the engine's critical/high class
— go by DEFAULT to ONE standing GitHub issue per repo (label `tech-debt`)
as structured comments — never to a tracked file:
parallel workers on branches editing one file is a merge-conflict factory,
and the edit would land inside the very PR under review. Register the
standing issue as a `deferred` P3 ticket so board-lint stays green. Promote
accumulated comments into real tickets during gardening passes (register
via doperpowers:issue-tracker; a pile grown sprint-shaped is
doperpowers:organizing-sprints input).

## Closing-artifact cross-check

After starting the native review in the background, the worker verifies the
PR body's `## Validation Evidence` section (the implement worker's closing
artifact) against the diff, the repo, and CI while Codex runs. Evidence
claimed but not verifiable is itself a finding; a missing section is only an
`AUDIT NOTE`. This closes the evidence loop without keeping the outer worker
idle: the implement side produces evidence, and the review side verifies the
claims independently of the native correctness verdict.

## Review engine and protocol audit

The loop has two concurrent review tracks with separate owners.

The native track is `codex exec review --base origin/<base>` run by
`scripts/review-engine.sh`. It is the pure native correctness reviewer: no
criteria file, custom prompt, or developer instructions carry ticket text or
spec policy into Codex. The script owns only the compact findings output and
the proven environment recipe. Species differ only in nesting: a Codex
worker's call runs inside its own sandbox (the script skips the inner
self-profiling step while the outer workspace-write profile still confines
it), and a Claude worker's call runs on the host.

The outer Review Worker starts that process in the background and directly
performs the implementer-protocol audit. The linked issue body is the
canonical primary specification; only documents it explicitly references
are secondary specification evidence. The worker checks whether implementation
started only after `ready-for-agent`, whether the issue was substantively
implementation-ready, whether settled requirements were implemented, and
whether the Implement Worker stopped instead of silently
choosing a human-grade scope/product/taste fork. It records this audit before
reading Codex's findings, then joins the two streams.

Audit output has three forms. A `PROTOCOL BLOCKER` is a substantive gate
failure or unauthorized human-grade decision; it prevents confidence and
routes `needs-human`. A `SPEC FINDING` is a clear settled requirement the
implementation violates; it is fix-required rather than severity-derived.
An `AUDIT NOTE` records weak process evidence when the ticket was otherwise
ready and no unauthorized decision exists; it appears in the trail but does
not block merge by itself. Native severity remains the blocker bit only for
native correctness findings.

There is NO second correctness engine. On native engine failure the worker
retries twice, posts the trail comment, leaves the ticket in-review, and ends
with `ENGINE-UNAVAILABLE`; the sweep re-dispatches when it sees the marker.
`needs-human` is never written for an infrastructure outage. The review trail
records both tracks, their findings or notes, and the final routing decision.

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
10. Codex workers (the default engine): `codex` CLI installed and authed
    (`codex login`) on the runner machine; set `WORKER_ENGINE=claude` (env) or
    label `engine:claude` to opt a repo/PR out.
