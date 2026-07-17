---
name: issue-tracker
description: Use when managing the issue board — registering tickets, running the mechanical dispatch ritual, working the wake queue (needs-human / needs-info / interactive-preferred), reconciling the board after time away, or asking what is in progress / parked / dispatchable. The board IS the repo's GitHub issues; the toolkit lives in this skill's scripts/.
---

# Issue Tracker

A repo's issue board, stored where it cannot fork: **GitHub Issues is the
single source of truth.** Tickets are **purpose-units**: born as pre-specs
from an `organizing-sprints` materialization (or registered directly here),
gated and driven to a PR by autonomous implement
workers (doperpowers:implementing-tickets), reviewed to a confident merge by
review workers (doperpowers:reviewing-prs), tracked as GitHub issues with
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
| **Implement worker** (daemon, one ticket; a SPIKE worker is the same species on a `spike` ticket) | its OWN ticket's open states; NEW child/follow-up tickets | doperpowers:implementing-tickets |
| **Review worker** (daemon, one PR) | its PR's ticket (`confident-ready` / `needs-human`); finding-tickets; post-merge finalize | doperpowers:reviewing-prs |
| **The human** (wake ritual) | everything else — unpark answers, `wontfix`, finalize, priorities, edge re-cuts | this file |
| **Dispatcher** (interim: a human-run ritual; next phase: an issue-event trigger) | NOTHING | the ritual below |

## State vocabulary

`ready-for-agent → in-progress → in-review → done` is the happy path; under
the review loop (doperpowers:reviewing-prs) a PR passes through
`confident-ready` between `in-review` and `done`.

| state | GitHub encoding | meaning | note |
|---|---|---|---|
| `ready-for-agent` | open + `status:ready-for-agent` | pre-spec complete; dispatchable once blockers are done | — |
| `in-progress` | open + `status:in-progress` | a worker passed the gate and is driving it (an epic stays here while children run) | optional |
| `needs-human` | open + `status:needs-human` | parked for the human **as themselves**: a decision only they can make, or a real-world input only they possess (credentials, auth, production data) | **required** |
| `needs-info` | open + `status:needs-info` | rare: the spec is unambiguous but lacks depth for a sophisticated result, or core decisions need substantial research first | **required** |
| `interactive-preferred` | open + `status:interactive-preferred` | rare: the work's CORE (architecture spine / product-core design) needs live steering — decisions too entangled for a question list (enumerable decisions are `needs-human`); never auto-dispatched; take it into a live doperpowers:brainstorming session | **required** |
| `in-review` | open + `status:in-review` | PR open (review rounds, conflicts, merge queue — all of it) | PR link |
| `confident-ready` | open + `status:confident-ready` | PR rigorously reviewed (reviewing-prs loop); merge/close with confidence | optional |
| `done` | **closed — completed** | landed — normally arrives by the merge itself (PR body `Closes #N` auto-closes); manual flip for non-PR work only, verify it landed first | optional |
| `wontfix` | **closed — not planned** | rejected | **required** |
| `deferred` | open + `status:deferred` | tracked, not now | optional |

**Park discriminant — who unparks it?** The human acting as themselves (a
decision, or a real-world input) → `needs-human`. Knowledge work that anyone
could in principle do (substantial research, spec-deepening) → `needs-info`.
Not one answer but ongoing steering → `interactive-preferred`. (`blocked`
was retired in v8: its meaning was absorbed by `needs-human`; lint names any
legacy label with the migration FIX.)

Exactly one `status:*` label on every open issue; terminal states are the
close reason (no label). An issue outside this scheme is `untracked` (no
label) or `conflict` (2+ labels) — lint FAILs it; `board-transition.sh`
repairs it (any open state is reachable from either).

Ticket dependencies are **edges** (native GitHub dependencies), never states —
eligibility is computed. Edges are born at register time and re-cut later with
`board-edge.sh` (understanding changes; the graph follows). Epics (issues with
sub-issues) are never dispatched; the sweep moves them automatically. Notes
land twice: the current note in the issue's `board:meta` body block, the audit
trail as `[board]` comments.

## Toolkit

Paths relative to this skill's `scripts/` directory. Ticket ids are issue
numbers (`42` or `#42`). Target repo = `$BOARD_REPO` (owner/name) or the
checkout's repo.

| script | does |
|---|---|
| `board-register.sh <title> <category> <priority> [--state S] [--note N] [--parent N] [--blocked-by N,N] [--spawned-by N] [--body-file F]` | open the issue with labels + typed edges; category is `bug`\|`enhancement`\|`spike` (spike = the exploration lane: deliverable is findings, never a merge — doperpowers:implementing-tickets); priority (`P0`…`P3`, P0 = drop everything) is REQUIRED and becomes the managed `priority:*` label; author the body at register time via `--body-file` (see The ticket body below — a skeleton birth is refused for `ready-for-agent` and demoted to `needs-info` otherwise); prints `<number> <url>` |
| `board-transition.sh <n> <state> [note] [--branch B] [--pr URL]` | apply a state change; enforces legality + notes + the in-review PR gate; runs the epic/unblock sweeps; repairs untracked/conflict issues. Re-run `<n> done` on a merge-auto-closed ticket to **finalize** (strip the stale label + run the sweeps; idempotent) |
| `board-edge.sh <n> --block N \| --unblock N \| --parent N \| --orphan` | re-cut edges after birth (one op per call): add/cut a dependency, move under another epic, or leave one. Rejects self-edges, cycles, ancestor-epic blockers; runs the same epic sweeps as transition |
| `board-relate.sh <a> <b> [--cut]` | symmetric relates annotation (board:meta) — rendered by board-map, no effect on eligibility |
| `board-priority.sh <n> <P0..P3>` | re-prioritize: swap the `priority:*` label (repairs a double label); prints `#n: P2 → P0` |
| `board-list.sh [state]` | board view in dispatch order (P0 rows first, unprioritized last); `ELIGIBLE` tag = dispatchable, `CLOSE?` tag = close candidate (see the ritual) |
| `board-map.sh [--write\|--serve\|--stop]` | human telemetry. `--write` renders **`BOARD.html`** (interactive layered-DAG: pan/zoom, node detail, state filter, epic collapse — plus a kanban view toggle) and **`BOARD.md`** (table) into the gitignored render dir. `--serve` additionally serves the render dir on 127.0.0.1 (per-repo port; `$BOARD_PORT` overrides) and opens the board over http — served tabs **hot-reload**: every later render (explicit `--write`, or the automatic one each mutating script fires while the server is up) appears without a manual refresh. `--stop` kills the server. No argument prints the table. Prefer `--serve` when a human will keep the board open |
| `board-show.sh <n>` | node + issue URL + bound daemon |
| `board-bind.sh <uuid> <n>` | record which daemon owns the ticket (in the daemon registry) |
| `board-answer.sh <n> <answers \| --posted>` | the wake ritual's `needs-human` relay: posts the answers as an `[answers]` comment (the ticket is the record), returns the ticket to `in-progress`, and resumes the BOUND session with the answers verbatim — park = pause, not death. Refuses unbound / mid-turn sessions (fresh dispatch is the fallback). Blocks for the worker's turn: bg shell |
| `board-reconcile.sh` | read-only catch-up: the wake queue (parked tickets), orphaned tickets, dispatchables, then a lint pass |
| `board-lint.sh` | schema invariants over the live board: one status label per open issue, none on closed, notes where required (the park trio + wontfix), no dependency cycles, at most one priority label (missing priority is a WARN — backfill legacy tickets with `board-priority.sh`), the retired `status:blocked` label named with its migration FIX. Also WARNs close candidates. `FAIL … FIX: …` lines, exit 1 |
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
   `$WORKER_ENGINE` → default `codex`. Every worker is ONE species — a
   Claude-harness daemon; the engine names only its model route (`codex` =
   the clodex gateway settings, GPT models through the local proxy;
   `claude` = plain Claude models). Render the worker protocol
   (`doperpowers:implementing-tickets`): category `spike` →
   `references/spike-worker-protocol.md`, else
   `references/implement-worker-protocol.md`. Substitute every
   `{{PLACEHOLDER}}` (`ISSUE_NUMBER`, `ISSUE_URL`, `ISSUE_TITLE`, `REPO`,
   `BOARD_SCRIPTS` = this skill's scripts dir, `ISSUE_BODY` = the full
   issue body from `gh issue view <n> --json body`, `ENGINE_NAME` = the
   engine, `REPO_FACTS` = `git show origin/<default-branch>:.doperpowers/repo-facts.md`
   (or a "(no repo-facts manifest)" note when absent), and — implement
   protocol only — `EXECUTION_BLOCK` = implementing-tickets'
   `references/engine-blocks/execution.md` (one block, both routes) and
   `DECOMPOSE_DOC` = the ABSOLUTE path of implementing-tickets'
   `references/implement-decompose.md` (a runtime-opened procedure: the
   prompt carries only the pointer; the worker opens it when Check-2
   says decompose).
3. Spawn via `daemon-spawn.sh "<n>-<slug>" "<prompt>" <repo> <worktree-name>`
   from `orchestrating-daemons` — always a worktree; workers write code.
   The codex route prefixes the gateway env and pins the gateway's model
   alias as arg 5:
   `DAEMON_CLAUDE_SETTINGS="${CLODEX_SETTINGS:-$HOME/.claude/clodex-settings.json}" DAEMON_CLAUDE_EFFORT="${CLODEX_EFFORT:-xhigh}" daemon-spawn.sh … fable`
   (daemon-spawn persists settings/effort into the registry meta;
   daemon-resume restores them on every fork — without that a gateway
   worker silently reverts to plain models on its first resume). The
   claude route passes no gateway env; the model inherits unless pinned.
4. `board-bind.sh <uuid> <n>`. Write NOTHING else: the worker's first board
   write is its gate verdict — `in-progress` (+ a `[gate]` comment) means
   the gate passed; a park state means it failed.

Nobody judges turn-ends. Parked tickets wait for the wake ritual; opened PRs
are picked up by the review loop (doperpowers:reviewing-prs). The next phase
replaces step 3's invoker with an issue-event trigger
(doperpowers:implementing-tickets `scripts/`, when it lands) — the ritual
itself does not change.

**doperpowers:orchestrating-daemons is the spawn substrate this ritual
calls, not a parallel doctrine.** For your own work: in-session fan-out is
native subagents (doperpowers:dispatching-parallel-agents); a raw ad-hoc
daemon is reserved for work that must survive your session with no board to
hold it. Board pipeline workers' doctrine is implementing-tickets /
reviewing-prs, and nobody sits between them and the board.

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
     the body), then `board-transition.sh <n> ready-for-agent` — the next
     dispatch re-runs the gate against the enriched ticket from fresh
     context.
   - a spike's `needs-human "findings ready: …"` is a handoff, not a
     blockage: read the `[findings]` comment, then close (`done` — the
     manual flip for non-PR work), relay a follow-up question
     (`board-answer.sh`, the bound session explores and re-parks), or
     graduate (the worker already registered clear-cut graduation tickets
     `--spawned-by`; register the rest yourself).
   - `needs-info` → do (or delegate) the research; fold the findings into
     the body; back to `ready-for-agent`.
   - `interactive-preferred` → take it into a live doperpowers:brainstorming
     session (the note says which decision areas need steering); the session
     ends in a controlled-track build, a decomposition into gate-passing
     children, or a re-spec back to `ready-for-agent`.
3. Finalize merges: `board-transition.sh <n> done` on merge-auto-closed
   tickets (lint's FIX line says the same). Workers registered their own
   follow-ups at PR time — verify against the PR's FOLLOW-UPS section; a
   follow-up not registered does not exist.
4. Triage `CLOSE?` rows: verify & close (`done` / `wontfix`), or re-scope.
5. `wontfix` recommendations arrive as `needs-human` parks with the
   recommendation in the note — the close is yours, never a worker's.

## Worker protocols

The implement-side protocol lives in doperpowers:implementing-tickets
(`references/implement-worker-protocol.md`) and is embedded verbatim in its
spawn prompts. The review-side protocol is doperpowers:reviewing-prs itself
(`SKILL.md`); its spawn bootstrap invokes the skill and supplies runtime
bindings. This file owns only the schema they write against.

## The ticket body (pre-spec)

Whoever registers a ticket authors its body AT REGISTER TIME — write the
sections to a temp file and pass `--body-file` in the same step. The
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
follow-up not registered does not exist.

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
  vocabulary, no sync. Its managed-label set must track the v8 vocabulary
  (add `status:needs-human` / `status:interactive-preferred`, drop the
  retired `status:blocked`).
