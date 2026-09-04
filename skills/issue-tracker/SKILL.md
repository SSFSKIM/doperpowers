---
name: issue-tracker
description: Use when managing the issue board — registering tickets, dispatching, working the wake queue, reconciling after time away, or asking what is in progress or parked. The board IS the repo's GitHub issues.
---

# Issue Tracker

A repo's issue board, stored where it cannot fork: **GitHub Issues is the
single source of truth.** Tickets are **purpose-units**: born as pre-specs
from an `organizing-sprints` materialization (or registered directly here),
gated and driven to a PR by autonomous Executor
workers (doperpowers:executing), reviewed to a confident merge by
Reviewer workers (doperpowers:qa-loops), tracked as GitHub issues with
typed edges (sub-issue = parent, dependency = blocked-by, provenance =
spawned-by).

There is no local board file, nothing to sync, and no worktree restriction —
every script talks to GitHub directly (`gh` required, fail-loud) and may run
from any checkout. `doperpowers/issue-tracker/` in the consumer repo survives
only as a gitignored render cache for `board-map.sh`.

**There is no orchestrator-judge.** Dispatch is mechanical (the ritual
below): it renders a protocol, spawns a worker, and writes nothing. Workers
write their own ticket's open states and register child/follow-up tickets
directly, under their protocol's authority rules. Everything that needs a
human lands on the board as a parked state and waits for the wake ritual.
All writes go through the scripts (the Hard Gate below).

## The Board Write Hard Gate (put this in the consumer CLAUDE.md)

> Board Write Hard Gate: issue creation and every state/edge change MUST go
> through the issue-tracker scripts — never raw `gh issue edit` for
> `status:*` labels or sub-issue/dependency edges. At registration, category +
> status + parent + blocked-by are each either set or consciously N/A —
> silence is not N/A.

The scripts are the schema: they enforce the state machine, mandatory notes,
PR gates, and cycle/deadlock checks that GitHub's API will not.
`board-lint.sh` catches what slips past (run it on wake; wire it to cron for
unattended repos).

## Who writes the board

| writer | writes | doctrine |
|---|---|---|
| **Architect Worker** (daemon, one ticket, Fable route) | its OWN ticket's open states through the design phase (`in-design`, handoff to `ready-for-implementer` with the `plan:` pin); NEW child/follow-up tickets; on an EPIC, the recomposition verdict — including that epic's terminal states, the one scoped exception to terminal authority | doperpowers:architecting |
| **Executor Worker** (daemon, one ticket; a SPIKE worker is the same species on a `spike` ticket) | its OWN ticket's open states; NEW child/follow-up tickets; architect-lane escalations | doperpowers:executing |
| **Reviewer Worker** (daemon, one PR) | its PR's ticket (`needs-human` / `ready-for-architect`); finding-tickets; the merge itself + post-merge finalize on a confident verdict; a scale review's clean `done` on a recomposition epic | doperpowers:qa-loops |
| **The human** (wake ritual) | everything else — unpark answers, `wontfix`, finalize, priorities, edge re-cuts | this file |
| **Board bookkeeping** (the scripts' own sweeps, incl. `board-sweep.sh`) | epic states nobody claims by hand — the in-flight pull (`in-design`/`in-progress` by the epic's lane) and the `ready-for-architect` recomposition/reconciliation returns (`[board-epic]` comments); dead-worker recovery parks | this file |
| **Dispatcher** (interim: a human-run ritual; next phase: an issue-event trigger) | NOTHING | the ritual below |

## Categories

`bug` | `enhancement` | `spike` | `env-issue`. The first two are GitHub's
own labels; the board manages the other two. `spike` is the exploration
lane — its deliverable is a findings comment, never a merge
(doperpowers:executing). `env-issue` is environmental friction a
worker hit and routed around (missing tool in the image, flaky registry,
broken fixture), filed as its own ticket so the report survives the
session that found it.

An `env-issue` defaults to `needs-human` — its birth rule is INVERTED
from every other category's. Elsewhere unsure means
`ready-for-implementer`; here unsure means the human, because friction an
authorized agent could have cleared would usually already be cleared, so
the Executor queue is the wrong default. Registration on that default
path REQUIRES `--note` naming the intervention being asked for (register
refuses without it). An explicit
`--state` is the registrar's positive claim that a concrete repair path
exists for some agent to execute; that claim is what buys a lane queue.
Filing is fire-and-continue authority for every worker protocol — the
reporter never parks its own ticket over friction it routed around.

## State vocabulary

The architect lane's happy path is `ready-for-architect → in-design →
ready-for-implementer → in-progress → in-review → done`; a direct
ticket starts at `ready-for-implementer`. Under the review loop the
Reviewer worker's confident verdict merges the PR, and the merge itself
closes the ticket to `done`. (`ready-for-implementer` is the Executor
lane's label; the string keeps its legacy spelling because live boards
depend on it.)

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `ready-for-architect` | open + `status:ready-for-architect` | dispatchable to DESIGN: purpose + success criteria stated to the architect-lane bar (`references/ticket-gate.md` variant); the work needs design/plan authorship by an Architect (Fable route); on an EPIC this is the recomposition/reconciliation claim (Epics below) | — |
| `in-design` | open + `status:in-design` | the Architect's in-flight state — gate passed, grill/authoring underway; its parks return here (`pre-park:`). On an epic it also exits to `done`/`in-review` — the recomposition verdict; on a leaf those edges are refused | optional |
| `ready-for-implementer` | open + `status:ready-for-implementer` | dispatchable to EXECUTION: an Architect's plan attached (`plan:` pin), ruled pre-spec-sufficient (`plan: pre-spec`), or plan-less DIRECT (the gate — `references/ticket-gate.md` — runs at dispatch); the DEFAULT birth state (unsure → executor) | — |
| `in-progress` | open + `status:in-progress` | a worker passed the gate and is driving it (an executor-queued or `needs-info`-released epic is pulled here and stays while children run; the architect queue pulls to `in-design` instead, and the other three parks are never pulled) | optional |
| `needs-human` | open + `status:needs-human` | parked for the human **as themselves**: a decision only they can make, or a real-world input only they possess (credentials, auth, production data) | **required** |
| `needs-info` | open + `status:needs-info` | rare: the spec is unambiguous but lacks depth for a sophisticated result, or core decisions need substantial research first | **required** |
| `interactive-preferred` | open + `status:interactive-preferred` | rare: the work's CORE (architecture spine / product-core design) needs live steering — decisions too entangled for a question list (enumerable decisions are `needs-human`); never auto-dispatched; take it into a live doperpowers:brainstorming session | **required** |
| `in-review` | open + `status:in-review` | PR open (review rounds, conflicts, merge queue — all of it); on an epic, the recomposition closure package rides the same `pr:` slot and draws a scale review | PR link (epic: package link) |
| `done` | **closed — completed** | landed — normally arrives by the merge itself (PR body `Closes #N` auto-closes); manual flip for non-PR work only, verify it landed first | optional |
| `wontfix` | **closed — not planned** | rejected | **required** |
| `deferred` | open + `status:deferred` | tracked, not now | optional |

**Park discriminant — who unparks it?** This paragraph is the single
authoritative copy — worker protocols route here instead of restating it.
The human acting as themselves (a decision, or a real-world input) →
`needs-human`; the note is the crisp question list, each with a
recommended answer. Knowledge work that anyone could in principle do
(substantial research, spec-deepening) → `needs-info`; the note says what
is missing. Not one answer but ongoing steering of the work's core →
`interactive-preferred`; any ENUMERABLE set of open decisions, however
many and whatever the ticket's size, is `needs-human` — not steering.

The discriminant has a THIRD address: missing or broken design that an
AGENT can author → `ready-for-architect` — written by the Executor's
gate (plan-need), the Executor mid-build (a genuinely blocked plan),
and the Reviewer worker at a design-gap impasse; never by-passed into
`needs-human` (the human address is for what only a human can give).
The board counts these escalation edges: a second traversal of the same
edge on one ticket converts to `needs-human` mechanically.

Waiting on other tickets is NOT a park: dependencies are edges — cut
`blocked-by` and return the ticket to its lane queue
(`ready-for-implementer`, or `ready-for-architect` by your judgment of
the birth rule) (the note names any banked branch); the unblock sweep
re-surfaces it the moment its blockers land, which no park state does.
(`blocked` was retired in v8: its meaning was absorbed by `needs-human`;
lint names any legacy label with the migration FIX.)

Exactly one `status:*` label on every open issue; terminal states are the
close reason (no label). An issue outside this scheme is `untracked` (no
label) or `conflict` (2+ labels) — lint FAILs it; `board-transition.sh`
repairs it (any open state is reachable from either).

Ticket dependencies are **edges** (native GitHub dependencies), never states —
eligibility is computed. Edges are born at register time and re-cut later with
`board-edge.sh` (understanding changes; the graph follows). Notes
land twice: the current note in the issue's `board:meta` body block, the audit
trail as `[board]` comments.

**Epics** (issues with sub-issues) ride their children: the first active
child pulls the parent in-flight (`in-design` from the architect queue,
`in-progress` from the executor queue or from a `needs-info` release —
that park is waiting on exactly this child activity), and it stays there
while they run. The other three parks are never pulled: `needs-human`
holds a bound session and a place in the wake queue, `interactive-preferred`
and `deferred` hold a claim on the human. An epic whose children are all terminal is never closed by
bookkeeping: it RETURNS to `ready-for-architect` (`recomposition-due`)
and an Architect closes it by verification — directly for non-code
parents, via `in-review` with a closure package for code-bearing ones.
Board bookkeeping writes on epics (recomposition/reconciliation returns)
post `[board-epic]` comments — a marker the convergence counter
deliberately never reads. Epics are dispatchable ONLY in
`ready-for-architect` (awaiting recomposition, or a reconciliation-due
return), never to implementation.

## API binding

A repo's board lives either in its GitHub issues (**gh binding**, the default)
or on an Arkho board service (**api binding**). `.doperpowers/board.json` says
which — it is committed, so every checkout and every linked worktree of the
repo resolves the same board:

```json
{ "binding": "api", "url": "https://…", "repo": "doperpowers" }
```

`repo` is the name the **board service** knows this repository by. One service
serves several repositories out of one ticket namespace, and a request that
names none is not repo-neutral — the server picks: its founding repo on a
write, *every* repo on a list read. So the key is required. An api binding
without it dies before any verb runs rather than falling back to the server's
pick or to the checkout's directory name; neither is this repo's identity on
the board, and a wrong one is silent (a register run from a neighbouring
checkout filed its ticket here, and a list from there printed this board's
tickets as its own).

`$BOARD_REPO` overrides the file, and means a different thing per binding: on
the **api** binding it is the board's repo key (a bare name); on the **gh**
binding it is `owner/name`, which `_lib.sh` resolves from the checkout when
unset. It is the value the Toolkit table below calls the target repo.

Credentials never live in the repo. The client reads
`~/.arkho-board/<main-checkout-dirname>.env` (the *main* checkout's directory
name, so a worktree reads the same file), with two lines:

```
BOARD_AUTOMATION_TOKEN=…    # the fleet: dispatch, claims, sweeps
BOARD_HUMAN_TOKEN=…         # your human partner: register, transition, answer
```

Those two are the operator's credentials. A dispatched **worker** speaks as its
*run* instead, and it is handed nothing to do so: the dispatcher claims the run
and `board-bind.sh` stamps the bearer, run id and fence onto that session's seat
record in the sminos registry, and the scripts resolve them back out of it by
matching `$CLAUDE_CODE_SESSION_ID` — the one thing a backgrounded session's own
shells reliably carry. An explicit `BOARD_RUN_TOKEN` in the environment still
wins where one survives; a record is used only if its bind confirmed and it was
bound on this checkout's board; otherwise there is no run context and the
credentials file above is what answers. A verb that resolved a run says so in
one line on stderr, naming the run and the seat and never the bearer.

Every read narrows to the bound repo, and so does every write. The two **browse**
verbs — `board-list.sh` and `board-search.sh` — take `--all-repos` to widen back
to the whole service. A widened listing says so in its header line and carries
the repo as a second column (`#<id> <repo> <state> <priority> <title>`): ticket
numbers are repo-local, so `#12` from another board is a different ticket here,
and every id-targeted verb takes a bare number. The narrowed default keeps its
original shape — there the repo is the binding, stated once rather than once per
row. Nothing else offers the flag: a checkout has no business sweeping, linting,
mapping, reconciling or dispatching another repo's tickets.

## Toolkit

Paths relative to this skill's `scripts/` directory. Ticket ids are issue
numbers (`42` or `#42`). Target repo = `$BOARD_REPO` — `owner/name` on the gh
binding (or the checkout's own repo), the board's repo key on the api binding
(see API binding above).

| script | does |
|---|---|
| `board-register.sh <title> <category> <priority> [--state S] [--note N] [--parent N] [--blocked-by N,N] [--spawned-by N] [--body-file F]` | open the issue with labels + typed edges; category is `bug`\|`enhancement`\|`spike`\|`env-issue` (Categories above owns their semantics — note an `env-issue` with no explicit `--state` is born `needs-human` and is REFUSED without `--note`); priority (`P0`…`P3`, P0 = drop everything) is REQUIRED and becomes the managed `priority:*` label; author the body at register time via `--body-file` (see The ticket body below — a skeleton birth is refused for a dispatchable lane state and demoted to `needs-info` otherwise); prints `<number> <url>` |
| `board-body.sh <n> --body-file F` | rewrite a ticket's statement of work (`F` may be `-` for stdin; an empty file is a legal edit — clearing it). Both bindings: the API route refuses `ticket-owned` while a run holds the ticket — the body IS the claim-time assignment, so an edit under an open run reaches nobody; enrichment for a BOUND park rides the park answer, never the body. The gh route is a meta-preserving read-modify-write — the trailing `board:meta` block is spliced back byte-for-byte, never parsed, which bare `gh issue edit` clobbers |
| `board-transition.sh <n> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes + the in-review PR gate; runs the epic/unblock sweeps; repairs untracked/conflict issues. Re-run `<n> done` on a merge-auto-closed ticket to **finalize** (strip the stale label + run the sweeps; idempotent). A ticket mid-turn under a live bound worker is fenced: only that worker's own session transitions it — retire the binding first, or overrule with `BOARD_OWNER_OVERRIDE="<why>"` |
| `board-edge.sh <n> --block N \| --unblock N \| --parent N \| --orphan` | re-cut edges after birth (one op per call): add/cut a dependency, move under another epic, or leave one. Rejects self-edges, cycles, ancestor-epic blockers; runs the same epic sweeps as transition |
| `board-relate.sh <a> <b> [--cut]` | symmetric relates annotation (board:meta) — rendered by board-map, no effect on eligibility |
| `board-surface.sh <n> --add NAME \| --remove NAME` | add/remove a `surface:*` label (see Surfaces below). `--add` validates against the registry; `--remove` never does — it is the cleanup for an orphaned label and the escape hatch for a false-positive match |
| `board-priority.sh <n> <P0..P3>` | re-prioritize: swap the `priority:*` label (repairs a double label); prints `#n: P2 → P0` |
| `board-list.sh [--all-repos] [state]` | board view in dispatch order (P0 rows first, unprioritized last); `ELIGIBLE` tag = dispatchable, `CLOSE?` tag = close candidate (see the ritual). API binding: rows in the server's own order (the header says so), and `--all-repos` widens past the bound repo, adding a repo column to every row (both flags are api-only) |
| `board-search.sh [--states s1,s2] [--bodies] [--all-repos] [--] <query>` | full-text search for the pre-registration dedup / prior-art check (see The ticket body). API binding: the board's `?q=` websearch (unquoted terms AND, `or`, `-` negation, quoted phrases) across ALL states in server order; `--states` narrows; `--bodies` prints the first ≤20 hits' bodies (one budgeted read); a query that leads with `-` rides behind `--`; `--all-repos` searches every repo the service holds and names each hit's repo in its row. gh binding: `gh issue list --state all --limit 200 -R <repo> --search` (`--states` refused; `--bodies` a stderr note — gh search already matches bodies). Claim-gated: a run context is refused before any request |
| `board-map.sh [--write\|--serve\|--stop]` | human telemetry. `--write` renders **`BOARD.html`** (interactive layered-DAG: pan/zoom, node detail, state filter, epic collapse — plus a kanban view toggle) and **`BOARD.md`** (table) into the gitignored render dir. `--serve` additionally serves the render dir on 127.0.0.1 (per-repo port; `$BOARD_PORT` overrides) and opens the board over http — served tabs **hot-reload**: every later render (explicit `--write`, or the automatic one each mutating script fires while the server is up) appears without a manual refresh. `--stop` kills the server. No argument prints the table. Prefer `--serve` when a human will keep the board open |
| `board-show.sh <n>` | one ticket in full. API binding: header row, the statement of work (body), then the server-side timeline — a run context sees `body: claim-served` (its body arrived in the claim payload). gh binding: node JSON + issue URL + bound daemon |
| `board-bind.sh <uuid> <n>` | record which daemon owns the ticket (in the daemon registry) |
| `board-answer.sh <n> <answers \| --posted>` | the wake ritual's `needs-human` relay: posts the answers as an `[answers]` comment (the ticket is the record), returns the ticket to the state it parked FROM — the `pre-park:` meta the park recorded, and when the park entered from a state `PRE_PARK` does not cover, the bound worker's own lane (`in-design` for an ARCHITECT, `in-review` for a QAGENT with the ticket's own `pr:` re-supplied, else `in-progress`) — and resumes the BOUND session with the answers verbatim — park = pause, not death. Refuses unbound / mid-turn sessions (fresh dispatch is the fallback), and refuses a review-lane return whose ticket carries no `pr:` (the answers still post; the ticket stays parked until the link is restored). Blocks for the worker's turn: bg shell |
| `board-answer.sh <n> <answers> --to <state>` | API binding only, and only for a park **nobody is bound to**: the server has no run whose lane it could return the ticket to, answers `409 no-return-mapping`, and `--to` is how the human names the disposition themselves (the server refuses it on a bound park — a bound park's return state is the server's) |
| `board-reconcile.sh` | read-only catch-up: the wake queue (parked tickets), orphaned tickets, dispatchables, then a lint pass |
| `board-sweep.sh` | the unattended tick (cron/launchd, ~5 min — arming: `references/sweep-setup.md`): bounded auto-recovery of dead/stalled workers (resume with a nudge, 3 attempts, then park `needs-human`), board-driven cancel of live workers on terminal tickets, `execute-dispatch.sh --sweep` + `review-dispatch.sh --sweep`, land dispatch on the human Approve signal, the `needs-human` answer relay (a fresh ticket comment resumes the bound worker — comment from anywhere, the sweep does the rest), then the reconcile report into its log |
| `board-lint.sh` | schema invariants over the live board: one status label per open issue, none on closed, notes where required (the park trio + wontfix), no dependency cycles, at most one priority label (missing priority is a WARN — backfill legacy tickets with `board-priority.sh`), the retired `status:blocked` / `status:ready-for-agent` labels each named with their migration FIX. Also WARNs close candidates. `FAIL … FIX: …` lines, exit 1 |
| `board-migrate-gh.sh [--board FILE] [--apply]` | one-shot v6→v7 migration: push a legacy `board.json` into GitHub (dry-run by default; legacy `blocked` lands as `needs-human`) |

## Remote board (hosted)

`board-map.sh --serve` renders locally on demand. For an always-current hosted
view, a workflow re-renders BOARD.html on every issue event (plus a cron safety
net — sub-issue/dependency edits fire no webhook) and deploys it. Hosted pages
hot-reload the same way served local tabs do (the page polls its own caching
headers), so a browser left open tracks each redeploy. Two templates,
pick by repo visibility:

- **Public repo → GitHub Pages.** Copy `references/board-pages.yml` into
  `.github/workflows/` and set Pages → Source to "GitHub Actions". Zero external
  accounts. Note: a Pages site is *public* even for a private repo on
  non-Enterprise plans — and on Free/most org plans, private-repo Pages is
  unavailable entirely.
- **Private repo → Cloudflare Pages + Access.** Copy
  `references/board-cloudflare-pages.yml`. It deploys to Cloudflare Pages behind
  Cloudflare Access, giving a **private, team-authenticated URL** (the only way
  to host a private board below GitHub Enterprise). Read the template header:
  set up Access *before* the first deploy, or there is a window where issue
  titles are public.

## The dispatch ritual (mechanical — no judgment)

1. `board-list.sh` → pick the TOP `ELIGIBLE` ticket — rows already print in
   dispatch order (P0 before P1 before …; unprioritized last). A row tagged
   `CLOSE?` is a **close candidate**: every linked PR merged/closed (≥1
   merged) yet the issue is open — usually a PR that skipped `Closes #N`.
   Triage it before spawning anything: if the work landed, walk it to `done`
   (or `wontfix "superseded by PR"`); if work genuinely remains, dispatch as
   normal. Derived from GitHub PR state on every snapshot — never a label,
   never auto-closed.
2. Resolve the ENGINE — ticket label `engine:claude`/`engine:codex` →
   `$WORKER_ENGINE` → default `claude`. Every worker is ONE species — a
   Claude-harness daemon; the engine names only its model route (`codex` =
   the clodex gateway settings, GPT models through the local proxy;
   `claude` = plain Claude models). Label `engine:codex` to put one ticket
   back on the gateway; `engine:claude` is redundant only while no
   `WORKER_ENGINE` override is set — under `WORKER_ENGINE=codex` it is the
   one per-ticket way back onto plain Claude, so it is never safe to strip.
   Render the spawn bootstrap
   (`doperpowers:executing` `references/worker-bootstrap.md` —
   the worker opens its protocol from the dispatcher-pinned file the
   bootstrap names, then reads its own ticket and the repo's
   `.doperpowers/repo-facts.md` itself). Substitute every
   `{{PLACEHOLDER}}`: `ROLE` = `ARCHITECT` when the state is
   `ready-for-architect` (that queue routes on STATE, and the state
   outranks category — every legal exit from it is an architect-lane
   exit), `SPIKE` when the category is `spike` (category selects a
   protocol only WITHIN the execution lane), else `IMPLEMENT`;
   `PROTOCOL_FILE` =
   the lane's protocol (spike → doperpowers:executing
   `references/spike-worker-protocol.md`; architect →
   doperpowers:architecting `SKILL.md`; else doperpowers:executing
   `SKILL.md`). The ARCHITECT dispatch ignores `engine:*` labels and
   `$WORKER_ENGINE` — plan authorship is never label-routed — and pins
   `${ARCHITECT_MODEL:-fable}` on the plain-Claude route; the
   engine resolution earlier in this step applies to the other roles.
   `ISSUE_NUMBER`, `ISSUE_URL`, `REPO`, `BOARD_SCRIPTS` = this skill's scripts dir,
   `ENGINE_NAME` = the engine, and `DECOMPOSE_DOC` = the ABSOLUTE path of
   executing's `references/implement-decompose.md` (a
   runtime-opened procedure: the prompt carries only the pointer; the
   worker opens it when Check-2 says decompose; "(none — spike lane)" for
   a spike).
3. Spawn via `sminos spawn "<n>-<slug>" "<prompt>" --cwd <repo> --worktree <n>-<slug>`
   — always a worktree; workers write code.
   The claude route — the default — passes no gateway env, and pins the
   lane's model with `--model`: `${ARCHITECT_MODEL:-fable}` on the architect
   lane, `${IMPLEMENT_MODEL:-opus}` on implement and spike. Both lanes
   pin rather than inherit, so the operator's own session model never
   silently collapses the split's two model economies onto one price.
   Since `sminos spawn` writes no settings/effort into the seat record, these
   wakes stay plain. The codex route prefixes the gateway env and pins
   the gateway's model alias:
   `DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" sminos spawn … --model fable`
   (`sminos spawn` persists settings/effort into the seat record;
   `sminos resume` restores them on every resume — without that a gateway
   worker silently reverts to plain models on its first resume).
4. `board-bind.sh <uuid> <n>`. Write NOTHING else: the worker's first board
   write is its gate verdict — `in-progress` (+ a `[gate]` comment) for an
   Executor, `in-design` (+ a `[gate]` comment) for an Architect, or
   (PLAN-EXECUTION) `in-progress` with no gate comment; a park state means
   it failed.

Nobody judges turn-ends. Parked tickets wait for the wake ritual; opened PRs
are picked up by the review loop (doperpowers:qa-loops). The ritual is
mechanized end-to-end by doperpowers:executing
`scripts/execute-dispatch.sh` (`<n>` triggered, `--sweep` catch-up —
same steps, registry-first dedupe, cap-bounded); unattended, `board-sweep.sh`
invokes it on a timer. Running the ritual by hand stays valid — the sweep's
dedupe sees a hand-dispatched worker's binding like any other.

**The sminos CLI (doperpowers:sminos) is the spawn substrate this ritual
calls, not a parallel doctrine.** For your own work: in-session fan-out is
native subagents; a raw ad-hoc
seat is reserved for work that must survive your session with no board to
hold it. Board pipeline workers' doctrine is executing /
qa-loops, and nobody sits between them and the board.

## The wake ritual (the human's catch-up)

1. `board-reconcile.sh` — the wake queue (parked tickets with notes),
   orphaned in-progress tickets, dispatchables, then a lint pass.
2. Answer the parks, on the ticket (answers belong in the body/comments —
   the next worker reads the ticket, not your chat):
   - `needs-human` → relay the answers to the parked worker's bound session:
     `board-answer.sh <n> "<answers>"` (bg shell — it blocks for the turn)
     posts them as an `[answers]` comment, returns the ticket to
     `in-progress`, and resumes the session. Park = pause, not death: the
     worker keeps its orientation and re-states its gate verdict against
     the answers before proceeding. Fallback — no/dead bound session, or
     answers that reshape the ticket's scope: answer in a comment (or edit
     the body), then `board-transition.sh <n> ready-for-implementer` (or
     `ready-for-architect` per the birth rule when the scope answer
     invalidates a standing plan — that edge clears any `plan:` pin
     automatically, since entering the lane means the design is being
     re-cut) — the next dispatch runs the lane's protocol against the
     enriched ticket from fresh context. An answered park with a live
     bound session returns to its `pre-park:` state automatically.
   - a spike's `needs-human "findings ready: …"` is a handoff, not a
     blockage: read the `[findings]` comment, then close (`done` — the
     manual flip for non-PR work), relay a follow-up question
     (`board-answer.sh`, the bound session explores and re-parks), or
     graduate (the worker already registered clear-cut graduation tickets
     `--spawned-by`; register the rest yourself).
   - `needs-info` → do (or delegate) the research; fold the findings into
     the body; back to its lane queue (`ready-for-implementer`, or
     `ready-for-architect` by your judgment of the birth rule).
   - `interactive-preferred` → take it into a live doperpowers:brainstorming
     session (the note says which decision areas need steering); the session
     ends in a controlled-track build, a decomposition into gate-passing
     children, or a re-spec back to its lane queue (`ready-for-implementer`,
     or `ready-for-architect` by your judgment of the birth rule).
3. Finalize merges: `board-transition.sh <n> done` on merge-auto-closed
   tickets (lint's FIX line says the same). Workers registered their own
   follow-ups at PR time — verify against the PR's FOLLOW-UPS section; a
   follow-up not registered does not exist.
4. Triage `CLOSE?` rows: verify & close (`done` / `wontfix`), or re-scope.
5. `wontfix` recommendations arrive as `needs-human` parks with the
   recommendation in the note — the close is yours, never a worker's.

## Worker protocols

Both loops keep their protocol in the skill file and spawn through a short
bootstrap that names the dispatcher-owned protocol path and supplies the
runtime bindings: the execution-side protocols are doperpowers:executing
itself (`SKILL.md`; spike lane → its `references/spike-worker-protocol.md`)
and, on the architect lane, doperpowers:architecting itself (`SKILL.md`) —
all three share the execution-side bootstrap
(`references/worker-bootstrap.md`). The review-side protocol is
doperpowers:qa-loops itself (`SKILL.md`; bootstrap
`references/review-worker-bootstrap.md`). This file owns only the schema
they write against.

## The ticket body (pre-spec)

Before registering, run the pre-registration search — and search by
SEAM: the identifiers your ticket touches (file paths, function/RPC
names, table names). Title-keyword search may not be enough — different
authors word the same work differently. Query each seam identifier with
`board-search.sh "<function-or-file-name>"` — one route, both bindings
(the verb owns the branch: gh-bound repos ride gh's body-matching issue
search, API-bound repos the board's `?q=` full-text filter). Where a
title is not enough to judge a hit, `--bodies` prints the first ≤20
hits' statements of work. A worker in a run context cannot search
(claim-gated by design) — there the server's registration-time dedupe
stays the guard. Then triage the hits:

- **Same defect or scope** → comment your evidence on the existing
  ticket instead of registering a duplicate — parallel workers hit the
  same base regressions blind.
- **Same seam, different defect** → register, but in the same breath
  `board-relate.sh` your new ticket to every open ticket on that seam
  (both bindings, but the API route admits the human principal only — a
  worker writing under its run token is refused; there, name the
  seam-mates in your ticket body instead and move on).
- **Cluster tripwire**: if your registration would put a THIRD
  non-terminal ticket onto the same function or contract body, that
  seam has outgrown patch-wise work — parallel rewrites of one body
  revert each other silently (different files, zero git conflicts).
  Parks COUNT: a needs-human/needs-info rewrite resumes into its lane
  without re-running this search; only `deferred` and closed tickets
  are out of the race. Register your finding, then raise consolidation:
  a ticket born `ready-for-architect` that names every member and owns
  the unified contract, with the members related. Member disposition
  belongs to the consolidation ticket itself — each member is re-cut as
  a slice of the unified contract or closed with a reason. Do not reach
  for `--blocked-by` on the existing members: re-cutting other tickets'
  edges is not a worker's write, and a block merely defers the
  collision — the moment the consolidation lands, the unblock sweep
  frees the stale rewrites to overwrite it.
  (For a REGISTERED surface — see Surfaces below — the sweep's
  queue-depth watch raises this mechanically; this manual duty is how a
  seam the registry does not know yet gets caught.)

Whoever registers a ticket authors
its body AT REGISTER TIME — write the sections to a temp file and pass
`--body-file` in the same step. The
registrar is the person who knows the most about the work at that moment;
"register now, fill in later" loses exactly that context (the fill-in
step is skipped under pressure, and register refuses/demotes a skeleton
anyway). Sections: Problem & intent / Constraints / Success criteria /
Open questions / Decision log — plus, on a decomposed parent, Roadmap
(the one sanctioned form of "ticket that doesn't exist yet"). A terminal
outcome comment updates the record at close. The trailing
`<!-- board:meta … -->` block is script-owned (spawned-by / relates-to /
branch / pr / note) — edit around it, never inside it. Note that the
meta block is an HTML comment: INVISIBLE on the rendered issue page —
`--note` is a one-line status summary, never the spec's home.

## Surfaces (contested seams, serialized dispatch)

A surface is a named contested code seam the consumer repo declares in
`.doperpowers/surfaces.md` — read from the DEFAULT branch, so an entry
takes effect when its PR lands, never from a working tree. No file → the
whole feature is inert. Entries are born from incidents (a consolidation
ticket's design deliverable includes the entry), not speculation. Entry
shape: a `## <kebab-name>` heading with `- paths:` (comma-separated
globs; `*` stays inside a path segment, `**` crosses), `- identifiers:`
(whole-word title/body matches), `- born-of:`, `- note:`.

On the board a surface is the managed label `surface:<name>` — a CLOSED
vocabulary (lint FAILs a label with no entry). Labels arrive at three
matching moments, all automatic: registration (identifiers + `--surface`
hints), a transition into a dispatchable lane state (re-match of the
current body), and the sweep's SURFACE pass (open linked PR diffs;
add-only — a label is never removed automatically, a stale one is a lint
WARN a human clears via `board-surface.sh --remove`).

What the label DOES: execute-dispatch runs at most ONE implement-lane
worker per surface at a time (the skip is logged;
`SURFACE_OVERRIDE=1` bypasses loudly). The architect lane is
never blocked but its in-flight tickets occupy — patch work waits while
a consolidation redesign runs; spike-lane work neither waits nor
occupies. When three
or more open implement tickets pile onto one surface with no architect
ticket carrying it, the sweep registers a consolidation ticket
(`ready-for-architect`) naming the members — the surface label on that
ticket is what suppresses a second registration.

## Scope-outs become tickets (deferral rule)

Work deliberately deferred out of scope — during a grill, a brainstorm, an
organizing-sprints session, a worker's gate/decomposition, or a worker's PR-time
follow-ups — is registered on the board THE MOMENT the deferral is decided,
by whoever decided it (v8: workers register directly; there is no proposal
queue), with its lineage as edges:

- `--parent <epic>` — decomposition children (they ARE the parent's content,
  sliced) and work that belongs to an existing epic
- `--spawned-by <origin>` — scope-outs and follow-ups discovered during work
- `--blocked-by <numbers>` — what must land first

Deferral without a ticket is silent scope loss: the decision exists only in
the design conversation and dies with the session. The ticket's Decision log
records *why* it was cut, so nobody re-litigates it later.

PR landing is a deferral point like any other. A PR that addresses its
ticket but leaves work behind still closes the ticket (`Closes #N` stays in
the body: done means the PR landed, not that every idea it surfaced died).
The worker registers the residue as tickets (`--spawned-by <n>`) BEFORE its
turn-end message and lists the numbers in its FOLLOW-UPS section — a
follow-up not registered does not exist. (A few-line residual inside the
PR's own diff is in-scope polish the PR absorbs, not residue — see the
executing skill's Closing Artifact.)

## Edge cases

- A merged PR auto-closed its ticket (`Closes #N`) → the board already reads
  it `done`; the stale status label and unswept epics are what's left. Run
  `board-transition.sh <n> done` to finalize — reconcile's lint pass names
  these tickets.
- A merged PR did NOT close its ticket (no `Closes #N`) → the ticket becomes
  a **close candidate**: lint WARNs it, `board-list.sh` tags it `CLOSE?`, and
  the kanban view pulls it into a close-candidate column (in-progress /
  in-review tickets stay put — a merged part-1 PR mid-flight is normal, they
  only carry the mark). Human verifies and closes; never auto-closed.
- `orphaned` in reconcile → the worker died: respawn (the fresh worker
  re-runs the gate from scratch — prior `[gate]` comments are context, not
  inherited trust), re-bind, resume the ticket.
- A wontfix blocker makes a dependent `STUCK` — re-cut the edge
  (`board-edge.sh <n> --unblock <blocker>`) or wontfix the dependent; that is
  a human call.
- An issue labeled by hand (or by external automation) lands `untracked` /
  `conflict` → lint names it; `board-transition.sh` repairs it. A legacy `status:blocked`
  label is a special case of conflict — lint's FIX line carries the
  `needs-human` migration.
- Consumer label automation that already speaks `status:*` (e.g. assign →
  `status:in-progress`) is a legitimate board writer — same store, same
  vocabulary, no sync. Its managed-label set must track the v9 vocabulary
  (the two lane-queue labels replace the single pre-v9 agent-queue label).
