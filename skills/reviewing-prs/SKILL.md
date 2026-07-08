---
name: reviewing-prs
description: Use when operating or setting up the autonomous PR-review loop — dispatching review workers onto opened PRs, the confident-ready escalation state, the Review Worker Protocol, the self-merge rubric, sweep/dedupe policy, or the self-hosted-runner trigger. The inverse of the issue-tracker dispatch loop, reviewing PRs instead of implementing tickets.
---

# Reviewing PRs — the autonomous review loop

## Overview

The inverse-symmetric counterpart of the implementing daemon: where a worker
turns a ticket into a PR, a **review worker** turns a PR into a confident
merge. Every non-draft PR opened in an adopting repo gets a fresh-context
background daemon (`orchestrating-daemons`) that reviews it with codex,
verifies every finding against the code, applies the valid fixes, re-reviews
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

Encoded as Rubric 3 in the protocol — ALL clauses must hold for self-merge:
final verdict approve (or only low findings, each explicitly routed);
post-fix diff ≤ ~150 changed lines AND ≤ 5 files; zero touches on risk
surfaces (CI/workflows, auth/security, migrations/schema,
release/versioning); every CI check green — a repo with no checks
disqualifies self-merge, no exceptions. Anything else → `confident-ready`
label on the PR + `status:confident-ready` on the ticket; the human merges.

## Tech-debt sink

Small valid-but-non-blocking findings go to ONE standing GitHub issue per
repo (label `tech-debt`) as structured comments — never to a tracked file:
parallel workers on branches editing one file is a merge-conflict factory,
and the edit would land inside the very PR under review. Register the
standing issue as a `deferred` P3 ticket so board-lint stays green. Promote
accumulated comments into real tickets during gardening passes
(doperpowers:issue-register).

## Codex-lock handling

The codex companion serializes ALL jobs behind one machine-wide lock with no
dead-holder detection. Workers therefore retry with backoff up to ~30 min,
then fall back to a fresh Claude high-effort reviewer subagent — and NEVER
run `/codex:cancel` (a busy lock may be another worker's live review; only
the human cancels).

## Edge cases

- **Reopened PR still labeled `confident-ready`** — dispatch skips it while
  the consumer label automation may have set the issue back to `in-review`.
  Safe and rare; the human decides: remove the PR label to force re-review,
  or restore the ticket state.
- **PR with no linked issue** — reviewed normally; every board write is
  skipped; escalation lands on the PR alone (label + comment).
- **Two reviewers, one codex lock** — parallel review daemons contend; the
  backoff serializes them. Expected, not an error.

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
7. Cron the sweep: `review-dispatch.sh --sweep` every ~30 min.
