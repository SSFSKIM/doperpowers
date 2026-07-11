---
name: reviewing-prs
description: Use when operating or setting up the autonomous PR-review loop — dispatching review workers onto opened PRs, the confident-ready escalation state, the Review Worker Protocol, the self-merge rubric, sweep/dedupe policy, or the self-hosted-runner trigger. The inverse of the issue-tracker dispatch loop, reviewing PRs instead of implementing tickets.
---

# Reviewing PRs — the autonomous review loop

## Overview

The inverse-symmetric counterpart of the implementing daemon: where a worker
turns a ticket into a PR, a **review worker** turns a PR into a confident
merge. Every non-draft PR opened in an adopting repo gets a fresh-context
background daemon (`orchestrating-daemons`) that reviews it with a native
Codex reviewer (`codex exec` self-diffing the PR), verifies every finding
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
| `references/review-worker-protocol.md` | the Review Worker Protocol — rendered (`{{PLACEHOLDERS}}`) into every spawn prompt |
| `references/pr-review-dispatch.yml` | GH workflow template: PR events → self-hosted runner → dispatch script. No checkout, no token permissions |
| `references/runner-setup.md` | one-time machine setup: runner registration, launchd service, PATH, sweep cron |
| `references/engine-blocks/` | engine + per-species fallback blocks; `review-dispatch.sh` resolves the worker engine (label → `WORKER_ENGINE` → codex) |
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
auth/security, migrations/schema, release/versioning, and the manifest file
itself. A repo may ALSO declare concrete surfaces in an optional
`.doperpowers/risk-surfaces.md` — a plain list of globs and prose
path/content rules the worker reads against the diff. The dispatch layer
injects it from the PR's **base ref, never HEAD**, so a PR cannot delist a
surface it touches in the same commit; the manifest can only tighten the
gate, never loosen an always-on category.

**Staged rollout (`AUTO_MERGE_ENABLED`, default off).** Off is *observation
mode*: the worker runs the full loop and judges the tier, but a
self-merge-eligible PR is routed to `confident-ready` instead of merged, with
the trail comment naming what it *would* have merged. Watch a few of those,
then set `AUTO_MERGE_ENABLED=true` (workflow / runner env) to let the worker
actually merge the self-merge tier.

## Tech-debt sink

Small valid-but-non-blocking findings go to ONE standing GitHub issue per
repo (label `tech-debt`) as structured comments — never to a tracked file:
parallel workers on branches editing one file is a merge-conflict factory,
and the edit would land inside the very PR under review. Register the
standing issue as a `deferred` P3 ticket so board-lint stays green. Promote
accumulated comments into real tickets during gardening passes (register
via doperpowers:issue-tracker; a pile grown sprint-shaped is
doperpowers:organizing-sprints input).

## Review engine

Both worker species apply the same native-Codex REVIEW CRITERIA — self-diff
the PR against its base (`git diff origin/<base>...HEAD`), correctness
discipline AND spec-compliance criteria (the linked ticket's acceptance) —
no companion, no shared lock. Who runs the engine differs by species: a
**Codex worker IS the engine** and reviews in-thread itself (codex-in-codex
nesting is structurally broken under the worker sandbox — no seatbelt
`sandbox_apply`, no keychain TLS trust — and the work-alone rule forbids
nested agents anyway); a **Claude worker calls the engine** via the cookbook
plain-`codex exec` form, which is not nested. (The `codex exec review`
subcommand can't take custom criteria — its target flags reject a stdin
prompt — so the cookbook form carries both.) The Claude species falls back
to a fresh Claude high-effort reviewer subagent when codex is unavailable;
the Codex species has no second engine and parks `needs-human` instead. The
review-trail comment names the engine that reviewed.

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
