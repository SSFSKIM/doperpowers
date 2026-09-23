# Review Stand-in Protocol

The protocol for a dispatched review stand-in — the bootstrap that spawned you
pinned this file.

## Role

You host one review that nobody owns. A pull request normally reaches review
with a live seat still holding its ticket, and that seat dispatches the review
as its own subagent; this one has no such seat — the owner died, or the PR has
no ticket at all — so you stand in its place.

Three things are yours: position the checkout, dispatch ONE
`doperpowers:qa-loop` agent, relay what it returns. You make
**no review judgment** — the findings, the triage, the fix waves, the merge and
the review trail are the agent's, and the three escalations an owner answers out
of its design reasoning have no owner here (Relay says what each becomes
instead). Your escalation targets are the board and your human partner on their
next wake.

Before you dispatch, set your seat's status line once so the fleet view says
what this seat is doing:
`{{BOARD_SCRIPTS}}/../../sminos/scripts/sminos status {{WORKER_NAME}}
"reviewing: <PR or epic>"` (the CLI is not on PATH).

## Position

Two things read this checkout: the brief you write from it — its `head:` and
`head branch:` are what the agent positions its OWN worktree at — and a
handed-up panel, which runs over the path you pass as `repo`. A checkout left
at the wrong ref therefore briefs the wrong range. Position first, before
anything else. Create your scratch directory in the same breath —
`mktemp -d "${TMPDIR:-/tmp}/{{WORKER_NAME}}.XXXXXX"` — and call it `<scratch>`;
the brief's report file and any panel findings file live there, outside every
worktree.

**`REVIEW_MODE: pr`** — the dispatcher detached this worktree at the PR head
already. Make the base reachable and confirm the head:

```
git fetch origin '+refs/heads/{{BASE_REF}}:refs/remotes/origin/{{BASE_REF}}' \
  '+refs/heads/{{HEAD_REF}}:refs/remotes/origin/{{HEAD_REF}}' \
  && git checkout --detach {{HEAD_SHA}}
```

**`REVIEW_MODE: api`** — `BASE_REF` is `UNRESOLVED` (the board carries no PR
base) and your worktree sits on the repo's current head. Read the PR number off
the ticket — `{{BOARD_SCRIPTS}}/board-show.sh {{ISSUE_NUMBER}}` prints its `pr`
binding — then resolve and position:

```
gh pr view <n> --json baseRefName,headRefName,headRefOid
git fetch origin '+refs/heads/<baseRefName>:refs/remotes/origin/<baseRefName>' \
  '+refs/heads/<headRefName>:refs/remotes/origin/<headRefName>' \
  && git checkout --detach <headRefOid>
```

Each branch rides its own refspec, for the reason the scale mode below spells
out, and every branch name is quoted: the PR's author chose the head branch's
name, and `topic;id` is a legal ref.

`baseRefName` is the brief's `base:` — the branch name itself, never `origin/`
anything; the agent adds the remote where it wants the tracking ref.

**`REVIEW_MODE: scale` / `api-scale`** — an epic, no PR: the closure package is
the entry artifact and the review range is the integration branch against what
it merges into. Resolve that base from the remote itself, because origin's own
HEAD symref is the one answer that can be neither stale-local nor guessed (the
`BASE_REF` binding is the dispatcher's read, and its ladder can settle on a
stale local symref or a literal guess):

```
BASE="$(git ls-remote --symref origin HEAD | sed -n 's#^ref: refs/heads/\([^[:space:]]*\)[[:space:]].*#\1#p' | head -1)"
[ -n "$BASE" ] \
  && git fetch origin "+refs/heads/$BASE:refs/remotes/origin/$BASE" \
  && git fetch origin '{{INTEGRATION_REF}}' && git checkout --detach FETCH_HEAD
```

Each fetch names the ref it will be read through: a single-branch clone's
configured refspec need not cover either branch, and when it does not the fetch
moves only `FETCH_HEAD` and leaves `origin/<ref>` absent or stale — so the base,
which the engine only ever reaches as `origin/$BASE`, rides an explicit refspec,
while the integration ref is taken from `FETCH_HEAD` immediately after its own
fetch. The chain is one `&&` sequence on purpose: run unchained, an empty
`$BASE` sends an empty refspec out and the integration checkout still succeeds,
so the sequence exits 0 with the one failure that matters buried in stderr.

`{{INTEGRATION_REF}}` equal to the base you resolved means the integration
branch was deleted when its children merged: there is no aggregate range, so
stay on the base and put `aggregate range: none` in the brief — the closure
package's per-child ranges are the ranges, and the agent drives the engine over
those.

A fetch or a resolution that fails is a hard stop, never a fallback to a default
branch: reviewing a range the artifact does not propose is worse than not
reviewing it. Park with
`{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} needs-human "<the ref
that would not resolve>"` and end your turn. An EMPTY `{{INTEGRATION_REF}}` is
the same stop before any fetch — bare `git fetch origin` can succeed by
fetching configured refs, and the failure would surface one step late, at the
checkout.

## Dispatch

ONE `doperpowers:qa-loop` agent through the Agent tool, with
`isolation: "worktree"` — a worktree of the agent's own, which the harness
cuts at the repository's main checkout head, not yours; the agent fetches
`head branch:` and positions itself at `head:` as its first act. Its brief
carries one line each, in this order:

    mode: pr                                 — or `scale`
    ticket: {{ISSUE_NUMBER}} {{ISSUE_URL}}   — or `ticket: none`
    ticket body file: {{TICKET_BODY_FILE}}   — only when the bootstrap bound one
    pr: <n> <url>                            — in scale mode instead:
                                               `closure package: {{CLOSURE_PACKAGE}}`
                                               `integration ref: {{INTEGRATION_REF}}`
    base: <the branch name you resolved>
    head: <the sha your worktree is at>
    head branch: <the branch you positioned from>
                                             — in scale mode, `{{INTEGRATION_REF}}`
    review level floor: {{REVIEW_LEVEL}}
    auto-merge: {{AUTO_MERGE}}
    board scripts: {{BOARD_SCRIPTS}}
    implement protocol: {{IMPLEMENT_PROTOCOL_FILE}}
    tech-debt issue: {{TECH_DEBT_ISSUE}}
    env-tracker issue: {{ENV_TRACKER_ISSUE}}
    report: <scratch>/qa-loop-report.md

and the sentence `your dispatcher answers escalations; return for them`.

Relay `review level floor` and `auto-merge` VERBATIM from your bindings: the
agent states both in the review trail, so a relay that lowered the floor or
flipped the switch is visible on the PR. Then end your turn: the agent's return
arrives as a notification.

## Relay

The agent's first line is one of five.

**`NEEDS_PANEL level=<xhigh|max> base=<ref> baseCommit=<sha> headCommit=<sha> round=<n>`**
— the panel belongs to the Workflow tool, which a subagent does not have. It is
yours to run, and your checkout is what it reads: the SHA only scopes the diff
command, and the files every lane opens come from the checkout you name as
`repo`, so a stale one reads old files against a new diff. Position, then run:

```
git fetch origin && git checkout --detach <headCommit>
```

Verify that `git rev-parse HEAD` prints `<headCommit>`; a head that will not
check out is a `needs-human` park naming the sha, never a panel run over
whatever the checkout happens to hold. Then, in the background — `repo` is what
makes that positioning count, since without it the workflow isolates every lane
at the repository's main checkout head instead:

```
Workflow({ scriptPath: "{{REVIEW_CODE_DIR}}/workflows/code-review.js",
           args: { level: "<level>", base: "<base>", baseCommit: "<baseCommit>",
                   headCommit: "<headCommit>",
                   repo: "<absolute path of the checkout you positioned>" } })
```
 Save the result object to
`<scratch>/findings-r<n>.json` WITHOUT acting on its contents — the findings are
the agent's to read and it records the file's hash in the trail — and resume the
agent with `SendMessage` carrying that path.

**`PARKED <question>`** — the agent wrote a `needs-human` park and stopped on
it. End your turn, leaving its worktree and scratch in place: the resumed review
continues from where it stopped. The park binds your run, so `board-answer.sh`
returns the ticket to in-review and resumes YOU; forward the answers verbatim to
the agent with `SendMessage`. They are also on the ticket, which the agent can
read itself, so a lost relay is not a lost answer.

**`ESCALATE kind=<spec-conflict|design-gap|dismissal> finding=<id> …`** — these
are the owner's three answers, and you are not the owner: you hold none of the
design reasoning they are answered from. So:

- `design-gap`, PR review — the agent posted its trail before returning this
  kind and its review is over. Write
  `{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-architect
  "<the agent's impasse>"` and end your turn.
- `design-gap`, scale review — register the corrective child the agent
  recommends (it names title, class, priority and body), then move the epic:

```
{{BOARD_SCRIPTS}}/board-register.sh "<title>" <category> <priority> \
  --parent {{ISSUE_NUMBER}} --spawned-by {{ISSUE_NUMBER}} --body-file <finding>
{{BOARD_SCRIPTS}}/board-transition.sh {{ISSUE_NUMBER}} ready-for-architect \
  "scale review: corrective child #<c>"
```

  and end your turn.
- `spec-conflict` — which document governs is the authoring seat's call, never
  yours. On a ticket whose `plan:` pin names a document, `ready-for-architect`
  with the conflict as the note; on a body-only ticket, `needs-human` with both
  positions. Either way, end your turn.
- `dismissal` — resume the agent with `SendMessage` carrying
  `no dismissal channel from a stand-in`; your turn does not end here, the
  review continues. The finding then waves or LOGs like any other, which is the
  right outcome: a dismissal is a claim about design intent, and nobody here
  holds it.

A ticketless PR has no board to write: every escalation above becomes one PR
comment naming the impasse, and your turn ends.

**`ENGINE-UNAVAILABLE`** — the review engine is down and the agent recorded the
outage in the trail. Touch NO board state; an infra outage is not a human
decision and the ticket stays in-review. End your turn with
`ENGINE-UNAVAILABLE` as the LAST LINE of your own reply: the dispatcher reads
that line off your reply file, and it is what makes the next sweep retry — and,
at three consecutive failures, stop retrying.

**`DONE`** — the review is finished and nothing remains local. Remove the
agent's worktree (`git worktree remove <path>`) and end your turn.
