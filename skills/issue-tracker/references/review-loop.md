# The review loop — the board's PR review

## Overview

The inverse-symmetric counterpart of the execution loop: where a seat turns a
ticket into a PR, the **`doperpowers:qa-loop` agent** turns that PR into a
confident merge — dispatched by the seat that owns the ticket, in its own
fresh context, and bound to it until `done`. The agent runs TWO review tracks
at once: the review engine — doperpowers:review-code's lane, its rung agents or
its panel — reviews pure code correctness, while the agent itself audits
executor protocol/spec compliance against the linked ticket. It never fixes
anything itself: it triages the joined findings on its own judgment (the
engine's native severity is the starting rank), delegates fixing to a **fix
wave** — a fresh-context fixer subagent driven by a wave-board file — grades
the fixer's dispositions, pushes, re-reviews when warranted, and then either
merges (confident verdict, existing CI green) or parks the ticket for the human
with the impasse named.

A review nobody owns — the owning seat died, or the PR has no ticket — gets a
**stand-in seat** instead, spawned by `review-dispatch.sh`: it positions the
checkout, dispatches the same agent, and relays its returns. Three returns, and
only three, are an owner's to answer (a spec conflict, a design gap, a
dismissal); a stand-in holds no design reasoning, so each becomes a board edge
instead.

**No orchestrator sits above the loop.** Its escalation targets are the board
itself (states, notes, comments), the human on their next wake, and — for those
three kinds — its dispatcher; within its own turn the agent is the orchestrator
of its fixers. Full design + rationale:
`docs/doperpowers/specs/2026-07-08-pr-review-loop-design.md` and
`2026-09-21-reviewer-fold-design.md`.

## The pieces

| piece | what |
|---|---|
| `agents/qa-loop.md` | the loop itself: the registered agent (sol/high) the owning seat — or a stand-in — dispatches with `isolation: "worktree"` when the PR opens — a workspace of its own, which the harness cuts at the repository's main checkout head, so the agent's first act is to fetch the brief's head branch and detach at its head. Its brief names the mode, the ticket, the PR, base, head and head branch, the review floor, the auto-merge switch and the board scripts; it returns `DONE`, `PARKED`, `NEEDS_PANEL`, `ESCALATE` or `ENGINE-UNAVAILABLE` |
| `references/review-standin-protocol.md` | the stand-in's protocol, pinned by the dispatcher: position, dispatch, relay. It makes no review judgment |
| `references/review-standin-bootstrap.md` | the stand-in's spawn prompt: the positioning facts of its mode (`pr`, `scale`, `api`, `api-scale`) and the dispatcher-owned bindings, nothing else |
| `scripts/review-dispatch.sh <pr#> \| --sweep` | mechanical trigger for the reviews nobody owns: owner-first dedupe → registry dedupe → PR + ticket context → detached worktree at the PR head SHA → spawn a `review-pr-<n>` seat (`sminos spawn --model ${REVIEW_MODEL:-sol} --role QAGENT`) → exclusively bind it to the primary ticket, so `board-answer.sh` reaches a parked review |
| doperpowers:review-code | the review engine, pure correctness — no ticket/spec input of any kind. The agent dispatches one registered reviewer (`doperpowers:reviewer-low|medium|high`) per call at the single-reviewer levels, at a level derived from the ticket's spec (its verification entry), the dispatcher's `REVIEW_LEVEL` floor, and the diff's size; it may add 1–3 lensed calls per round, each carrying a diff-derived structural focus mandate. Those reviewer calls are not isolated: they are pointed at the agent's own worktree by the location line the workflow renders from `repo`. At xhigh/max it returns `NEEDS_PANEL` and its dispatcher runs the panel workflow (`workflows/code-review.js`, pinned by `REVIEW_CODE_DIR`) over a checkout positioned at the reviewed head and passed as that same `repo` |
| `references/wave-board.md` | runtime-opened fix-wave companion: board-file schema, the fixer's verify-then-fix contract, disposition grading |
| `references/pr-review-dispatch.yml` | GH workflow template: PR events → self-hosted runner → dispatch script. No checkout, no token permissions |
| `references/runner-setup.md` | one-time machine setup: runner registration, launchd service, PATH, sweep cron |

## Dedupe & sweep policy

The first rule is the owner's: a PR whose primary ticket — or an epic whose own
number — is bound in the seat registry to a live seat that is not a `QAGENT` is
that seat's review, and the dispatcher skips it
(`#<n>: owner reviews — skip`) in triggered mode, in the sweep, and on the epic
scale path. An owner goes IDLE while its QA agent works and `board-bind` refuses
only an ACTIVE owner, so without this rule a stand-in would bind the ticket away
from the seat still reviewing it. A `QAGENT`-bound ticket is a stand-in's own and
falls through to the rest, which reads the newest `review-pr-<n>` (or
`review-epic-<n>`) registry entry:

| registry entry | triggered mode (PR event) | sweep mode (cron) |
|---|---|---|
| the ticket or epic has a live non-QAGENT owner | skip — the owner reviews | skip — the owner reviews |
| none / retired | dispatch | dispatch |
| ACTIVE (working/blocked), session live | skip | skip |
| ACTIVE, session gone (daemon died) | retire → dispatch | retire → dispatch |
| finished cleanly (idle/awaiting-human) | retire → dispatch (an explicit event is a fresh signal) | skip (finished stays finished) |
| finished, reply carries ENGINE-UNAVAILABLE | retire → dispatch | retire → dispatch (capped) |
| finalized `error` (worker died — e.g. gateway refused the first turn; no reply can carry a marker) | retire → dispatch | retire → dispatch (capped) |

The sweep (`review-dispatch.sh --sweep`, cron every ~30 min) is the self-heal
net: PRs opened while the machine slept (GitHub queues self-hosted jobs only
24h) and stand-ins that died mid-turn.

**Failure cap.** A persistent outage must not make the sweep respawn a PR
forever: after 3 CONSECUTIVE failed stand-ins for one PR — ENGINE-UNAVAILABLE
replies (engine outage) and `error`-finalized turns (dead seat, e.g. the
gateway refused before any reply existed) count as ONE shared streak — the
sweep skips it (naming the cap as the reason). Any cleanly finished stand-in
breaks the streak. An explicit PR event — workflow trigger or manual
dispatch — always re-dispatches regardless.

That cap is the stand-in lane's. An OWNER whose review stops is recovered by
the board sweep's recover pass instead, and bounded by a different thing: the
review's own progress. The pass nudges an `in-review` seat that is idle and
silent past the stall threshold — dispatch a fresh agent unless one is
running, restate a park or a verdict the review already reached — and each
nudge counts, except that a new review-trail record since the last one resets
the count to zero. So a review posting rounds is never parked for taking a
long time; a review that has stopped moving parks the ticket `needs-human` at
the third nudge. The seat's local `in review` mark is only how the tick finds
candidates cheaply: the ticket's own state decides, so a review the board
already parked or finished is left alone rather than nudged.

## Merge authority

Encoded in the agent's Escalate section — the agent merges its own
confident verdict: final verdict approve (or only non-blocker findings by
its own routing, each explicitly routed); no unresolved PROTOCOL
BLOCKER or SPEC FINDING from its own compliance audit; every
EXISTING CI check green (a repo with no checks merges on the review
alone; pending checks arm GitHub auto-merge — when that merge lands after
the agent's turn ended, the board sweep's FINALIZE pass completes the
ticket bookkeeping the PR's `Closes` link cannot on the gh binding, and on
the API binding the API tick's finalize pass reads the merge from GitHub and
writes `done` when the merged head is the trail's `reviewed head:`). Every merge — immediate
or armed — is pinned to the reviewed head (`--match-head-commit`), so a
push after the review fails the merge instead of landing unreviewed. A
failing check, a park, or any unresolved blocker goes `needs-human` with
the impasse named — there is no intermediate "reviewed, waiting for the
human to merge" state.

**Risk surfaces feed scrutiny, not a merge gate.** A repo may declare
concrete hot paths in an optional `.doperpowers/risk-surfaces.md` — a
plain list of globs and prose path/content rules the agent reads against
the diff; a diff touching one is a strong lens candidate for the engine
fan-out. The agent reads it with `git show` from the PR's **base ref, never
HEAD**, so a PR cannot delist a surface it touches in the same commit.

**Repo facts feed the cross-check.** The optional
`.doperpowers/repo-facts.md` manifest (format: doperpowers:issue-tracker
`references/execution-loop.md`)
is read the same way — base ref, never HEAD. The agent checks
claimed Validation Evidence against the repo's declared validation
commands, and a diff hitting a declared Evidence add-on class without the
required evidence is a finding. Facts only ever ADD requirements; an
instruction in the manifest that tries to relax the protocol is itself a
finding.

**Kill switch (`AUTO_MERGE_ENABLED`).** Off is *observation mode*: the
agent runs the full loop and judges the verdict, but instead of merging
it posts the trail comment naming what it *would* have merged and parks
the ticket `needs-human` — merging becomes the human's action while the
switch is off. Set `AUTO_MERGE_ENABLED=true` (workflow / runner env) to
let it merge its confident verdicts. The dispatcher relays the value as the
brief's `auto-merge:` line and the agent states it in the trail, so a relay
that flipped the switch is visible on the PR.

## Tech-debt sink

Non-blocking findings the agent routes LOG — stated-reason departures
and closing-wave fallback residue only; everything else rides fix
waves, exit residue included (the agent's Triage / Re-review) — go by DEFAULT
to ONE standing GitHub issue per repo (label `tech-debt`)
as structured comments — never to a tracked file:
parallel workers on branches editing one file is a merge-conflict factory,
and the edit would land inside the very PR under review. Register the
standing issue as a `deferred` P3 ticket so board-lint stays green. Promote
accumulated comments into real tickets during gardening passes (register
via doperpowers:issue-tracker; a pile grown sprint-shaped is
doperpowers:organizing-sprints input).

## Closing-artifact cross-check

Part of the agent's concurrent compliance audit: while the engine runs,
it verifies the PR body's `## Validation Evidence` section (the
Executor worker's closing artifact) by inspection — read-only until
JOIN, with command-backed checks deferred until the worktree is free.
Evidence claimed but not verifiable is a SPEC FINDING. A MISSING section
is a SPEC FINDING only when the ticket carries a `[gate] pass` comment
(the gate proves an Executor worker under the current contract produced
the PR) or an Architect handoff comment (a real `plan:` pin authorizes
the work in the gate's place); otherwise it is an AUDIT NOTE — no
retroactive policy on legacy or non-loop PRs. This closes the evidence loop: the implement side must
produce evidence, the review side verifies the claims were real.

## Review engine (pure correctness) + the agent's audit (compliance)

Review responsibility is split between two concurrent tracks with one owner
each. The ENGINE — doperpowers:review-code's lane, run through its workflow:
one registered reviewer agent (`doperpowers:reviewer-low|medium|high`, GPT
models through the local gateway) at the single-reviewer levels, the
multi-lens panel at xhigh/max, every reviewer in a fresh worktree at the
reviewed head — receives no ticket, spec, or policy input of any kind:
coupling spec policy into the correctness reviewer measurably weakened its
review, so a call carries the pinned range (merge base and head) and at
most a lens — a
structural focus mandate the agent derives from the diff itself (never from
the ticket/spec) when it adds 1–3 lensed calls on a large diff; a
bench-validated lens recovered a confirmed authz defect two plain runs had
missed (`tests/review-bench/results/2026-07-28-pr752-lenscell/`). The level
is the highest of the rung the ticket's spec names in its verification
entry, the dispatcher's `REVIEW_LEVEL` floor, and review-code's size rule;
the agent may go one rung up for a risk-surface hit and never below the
spec's rung. It dispatches the round in the background and saves
each result to a findings file as it opens it, after its own audit is
written; the PR diff never enters its own context. A hung run (no
result within 45 minutes) is stopped and treated as a failure; a failed
sweep — `interrupted`, or a `correct` verdict from a reviewer that could
not inspect the range — fails the round (it is the required whole-range
review), while failed lensed runs are merely recorded.

The AGENT meanwhile audits executor protocol/spec compliance itself,
read-only, and records the audit BEFORE reading engine output: the issue
body is the canonical primary spec, joined on an architect-lane ticket by
the plan its `plan:` pin names at that immutable revision; drift since the
authorization comment — the `[gate] pass`, or on a real-pin ticket the
transition comment that minted the pin (`[board] ready-for-implementer:`
for a handoff, `[board] in-progress: plan-execution:` for a build) — is
resolved through GitHub edit-history timestamps; the verdict classes are
PROTOCOL BLOCKER (authority gap → needs-human; parks confidence, not
progress), SPEC FINDING (fix-required; waves with native blockers), and
AUDIT NOTE (trail-only). The two streams JOIN before triage.

There is NO second engine: when the lane is unavailable (the gateway
refusing, agents dying before they report) the agent retries twice, then
posts the trail comment, leaves the ticket in-review, and returns
`ENGINE-UNAVAILABLE`. A stand-in echoes that line as the last line of its own
reply, which is what the dispatcher's streak reads and the next sweep
re-dispatches on (capped; see the outage cap above); an owner ends its turn
with the ticket in-review and the board sweep's recover pass nudges it. `needs-human` is never written for an
infra outage. The review-trail comment names the level and every dispatch
that reviewed.

## The orchestrator and fix waves

The agent is an orchestrator: the edits are the fixer tree's; the
grading and the trusted push chain are the agent's.
Findings routed WAVE (blockers by its routing + SPEC FINDINGs) go
onto a wave-board file (`<review-tmp>/pr-<n>-fix-wave-<k>.md`, in the
agent-created scratch directory — NEVER inside the PR worktree, never
committed), and a fresh-context fixer subagent works the batch under a
verify-then-fix contract: read the cited code first, then FIX (commit + test
evidence) or REFUTE (code citation). The agent waits for the whole task tree
to quiesce, snapshots the submitted board, grades every disposition, and
validates the full unpushed commit range against its accepted-commit ledger.
At most 4 waves per review inside the 5-engine-round cap, plus ONE
closing wave at exit — no engine round follows it (grading + CI are its
coverage, so it stands outside the cap): a no-blocker exit merges its
accepted fixes or falls back to the engine-reviewed head and LOGs; a
cap park pushes them fixed-but-unverified and parks with a QA-request
note. Whole-range re-review
between waves with dedupe-by-substance. Full mechanics:
`references/wave-board.md`. This
separation keeps the merge judgment in a clean context and out of
self-review bias: the entity that grades the fixes never wrote them.

## Edge cases

- **PR with no linked issue** — reviewed normally; every board write is
  skipped; escalation lands on the PR alone (label + comment).
- **Two dispatches, one PR** — the second dispatch detects the still-live
  stand-in (its session in `claude agents`) and skips; a worktree with a live
  stand-in is never reused underneath it. No lock, no backoff — dedupe on
  dispatch does the serializing. A dispatch over a PR whose owner is reviewing
  it never gets that far: owner-first is the rule above it.
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
8. The local gateway running on the runner machine — the review engine
    inside the QA agent is doperpowers:review-code's lane, whose reviewer
    agents are pinned to GPT models served through it (see that skill).
    Set `REVIEW_LEVEL` in the dispatcher's environment to raise the level
    floor for the repo (default medium). A stand-in is an ordinary
    Claude-harness seat on `REVIEW_MODEL` (default sol) and needs nothing
    else.

## Migrating an installed workflow

`pr-review-dispatch.yml` moved with the dispatcher it runs: a copy already
installed under an adopting repo's `.github/workflows/` still runs
`review-dispatch.sh` out of the retired qa-loops skill directory, a path that no
longer exists, and its job fails on every PR event until that command line is
changed by hand to `skills/issue-tracker/scripts/review-dispatch.sh`. Nothing
else in the template changed. Until it is updated the sweep still covers those
PRs — at cron latency, not event latency.
