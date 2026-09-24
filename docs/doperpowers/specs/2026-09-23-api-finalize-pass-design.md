# API tick: a finalize pass closes a ticket whose PR merged at the reviewed head

Ticket #74 (https://arkho-board-service.onrender.com/tickets/74), TECH-DEBT.md
row 26. Branch `74-api-finalize`. This spec carries its own execution and is
run sequentially by one executor with no other context: everything the
executor needs is in this file and in the files it names.

## Purpose

On the API binding, a ticket whose pull request merges after its QA agent has
returned stays `in-review` until the recovery ladder nudges its idle owner
(45 minutes) and a re-dispatched agent finds the merge. Two paths reach that
state: an armed auto-merge whose checks outlast the agent's 20-minute wait,
and a merge by hand after an observation-mode park was answered. The gh
binding closes both through `board-sweep.sh`'s FINALIZE pass; the API tick
(`skills/issue-tracker/scripts/_sweep_api.sh`) has no equivalent. This spec
adds one: on every tick, a merged PR closes its ticket, under the same
evidence gate the server enforces on the owning run's close.

## Progress

- [ ] M1 — `board-transition.sh` honours `BOARD_PRINCIPAL`; `_sweep_api.sh` gains `phase_finalize` and the `finalize` arm, wired into `all` after review-recover.
- [ ] M2 — `tests/claude-code/board-api/test-sweep-finalize.sh` written and green; the suite listed in `run-skill-tests.sh`; every other `board-api/test-sweep-*.sh` and `test-sweep-renew-relay.sh` still green.
- [ ] M3 — `agents/qa-loop.md` and `agents/codex/qa-loop.toml` name the reviewed head in the trail and the API finalize pass beside gh's FINALIZE; `references/review-loop.md` names it; TECH-DEBT.md row 26 struck; `tests/issue-tracker/test-qa-loop-agent.sh` pins the new trail line.
- [ ] PR opened on `main` from `74-api-finalize`; report written to `.architect/74/plan-executor-report.md`.

## The state this pass exists for

The QA agent (`agents/qa-loop.md`, Escalate section) merges with
`gh pr merge <pr> <method> --match-head-commit <reviewed-head>`. When checks
are still running past its 20-minute wait it arms GitHub auto-merge on that
same pinned head and returns `DONE` with the second line
`auto-merge armed on <sha>; the board's finalize pass writes done`. Its
dispatcher (the owner seat) ends its turn. The ticket is `in-review`, its
`pr_url` names the PR, its `owner_run` is the owner's still-open run, and the
owner seat's registry record carries that run's bearer. Nobody is running.
When GitHub merges, nothing on the API board notices.

The gh tick's `pass_finalize` (board-sweep.sh:532) re-derives closed issues
with residual status labels from GitHub and re-runs the terminal transition.
The API board has no GitHub-side close to re-derive from (the API binding
writes no `Closes #N`), so the API pass reads the merge from GitHub and writes
`in-review → done` itself.

## What the server enforces, and what it does not

`in-review → done` on the board service (arkho `board-service/src/transitions.js`,
reviewer fold of 2026-09-21) is gated **for run actors only**: the run must
own the ticket (`run.id === tk.owner_run`), a leaf's `pr_url` must be a URL,
and a `review-trail` event **by that run** must exist after the ticket's
latest `transition` into `in-review` (a re-pin self-edge counts as an entry);
otherwise `epic-guard` 403 or `review-trail-required` 403. API.md §4.2 states
the other half in one clause: "a human's or an automation's terminal write is
unrestricted". So a `done` written as the automation principal is not gated
by the server at all.

The ticket's decision "the evidence-gated close is the guard" therefore holds
only on the run path. This pass carries the same predicate client-side and
applies it before **any** write, on both paths: a `review-trail` event after
the ticket's latest entry into `in-review`, and that trail naming the head
that was reviewed. On the run path the server re-checks its stricter form
(the trail must be the owning run's) and a `review-trail-required` refusal is
logged and left alone. On the automation path the client check is the whole
gate, which is why it is not optional and why it is drilled by its own cases.

A terminal write by any actor releases the owning run (transitions.js:378,
`SCOPE_END`): the run is ended, `owner_run` cleared, a `release` event
appended. The next tick's renew phase then sees `409 run-ended` and its
retire step retires the seat. Retiring is not this pass's work.

## Where the reviewed head comes from

Nothing on the ticket records the head the review approved: the `in-review`
transition carries `pr` and `branch`, the seat record carries a run, the
trail today is prose. The QA agent knows it exactly (it pins the merge to
it), so the trail carries it from now on as one line, verbatim:

    reviewed head: <full 40-hex sha>

The pass reads the **latest** `review-trail` event after the ticket's latest
entry into `in-review` and takes the first line matching
`^reviewed head: ([0-9a-f]{40})\s*$` (multiline). A trail without the line is
a review this pass cannot verify: logged, left for the owner. The QA agent
posts its final trail before the first operation that can make the PR
terminal (qa-loop.md, Escalate), so the latest trail is the one whose head
the merge was pinned to.

GitHub's side is `gh pr view <pr_url> --json mergedAt,mergeCommit,headRefOid`:
`mergedAt` null means unmerged; `headRefOid` is the PR branch head at merge
time, which is the commit `--match-head-commit` pinned, whatever the merge
method (a squash or rebase merge commit's parent is the base, so the merge
commit's parent is not the comparison — `headRefOid` is). `mergeCommit.oid`
names the commit that landed and goes into the note.

## The pass

`phase_finalize`, in `_sweep_api.sh`, placed directly after
`phase_review_recover` and before the `# ---- phase 2: answer relay` banner.
Invokable alone as `_sweep_api.sh finalize`; `all` runs it right after
`phase_review_recover || true` (a ticket closed here is not a stand-in
candidate when `phase_dispatch` runs later in the same tick).

Per tick:

1. `command -v gh` — absent: one stderr line, return 1.
2. Candidates: `A.tickets_all(states="in-review", principal="automation")`,
   keeping rows whose `pr_url` matches
   `^https://github\.com/[^/]+/[^/]+/pull/[0-9]+/?$`. An epic's `pr_url` is a
   closure-package event id and never matches; a ticket without a pin never
   matches. A list read that dies (the client dies on any refusal): one
   stderr line, return 1. Rows print as `id \x1f pr_url \x1f owner_run`
   (owner_run empty when null). The list is the candidate filter AND the
   read the write is based on: no by-id re-read — the transition itself is
   the authoritative act, and a ticket that moved in between is refused
   `illegal-transition` by the server and logged here.
3. For each candidate, `_budget_left` first (the same `tick budget exhausted`
   line the other phases print, then stop). Then:
   a. `gh pr view "$pr_url" --json mergedAt,mergeCommit,headRefOid` — a
      failing gh: stderr line, continue. Parse with python (`mergedAt`,
      `mergeCommit.oid`, `headRefOid`); `mergedAt` null or missing:
      **continue silently** (an open PR under review is the ordinary state
      and not worth a log line per tick).
   b. Evidence: `A.timeline(ticket, principal="automation")["records"]`,
      `source == "board"` only. `entry` = the highest cursor among records
      with `kind == "transition"` and `body.to == "in-review"` (0 when
      none). `trail` = the record with the highest cursor among
      `kind == "review-trail"` with cursor > `entry` (cursors are decimal
      strings; compare as ints). No trail → `no-trail`. Trail without the
      head line in `body.text` → `no-head`. Else the sha. A timeline read
      that dies: stderr line, continue.
   c. `merged_head != reviewed_head` → the `merged off the reviewed head`
      line, continue.
   d. Owner: `_metas_for_ticket "$ticket"` rows (`uuid \x1f bearer \x1f run
      \x1f fence`, confirmed binds first); pick the first whose `run` equals
      the row's `owner_run` and whose bearer is non-empty. If that seat's
      `status` (`_meta_field <path> status`; the path is
      `$DAEMON_HOME/<uuid>.json`) is `working` or `blocked`, the owner is
      mid-turn (its own QA agent may be verifying this very merge): log,
      continue. Otherwise write as the run:
      `BOARD_RUN_TOKEN="$bearer" BOARD_RUN_ID="$run" BOARD_RUN_FENCE="$fence" board-transition.sh <ticket> done "<note>"`.
      No seat resolves (owner_run null, or the owner lives in another
      machine's registry): write as automation:
      `BOARD_PRINCIPAL=automation BOARD_OWNER_OVERRIDE="sweep finalize: <pr_url> merged at the reviewed head; no owning run resolves in this registry" board-transition.sh <ticket> done "<note>"`.
      The override is the dp#63 fence's stated reason; it only ever prints
      when a mid-turn seat of some other run fences the ticket, and it is
      passed so the write is never refused for lack of one.
   e. Read the outcome: exit 0 → the success line. Output containing
      `review-trail-required` → the refusal line, no retry, continue. Any
      other failure → stderr line with the first line of the output.

The note on the transition, verbatim shape:

    finalize: <pr_url> merged as <mergeCommit.oid> at the reviewed head <sha>

Log lines (stdout unless marked; tests assert on them, so copy them exactly):

    finalize: #<t> — <pr_url> merged as <oid> at the reviewed head <sha>; done written as run <n>
    finalize: #<t> — <pr_url> merged as <oid> at the reviewed head <sha>; done written as automation
    finalize: #<t> — merged off the reviewed head: GitHub merged <merged_head>, the trail names <sha>; left for the owner
    finalize: #<t> — the board refused done (review-trail-required): <server message>; the ticket stays with the recovery ladder
    finalize: #<t> — merged, but no review-trail since the ticket last entered review; left for the owner
    finalize: #<t> — merged, but the latest review-trail names no reviewed head; left for the owner
    finalize: #<t> — merged, but its owner <uuid> is mid-turn; its own agent closes
    finalize: tick budget exhausted — the rest ride the next tick
    (stderr) finalize: #<t> — gh could not read <pr_url>; the next tick retries
    (stderr) finalize: #<t> — the timeline could not be read; nothing is written this tick
    (stderr) finalize: #<t> — the done transition failed: <first line of output>; the next tick retries
    (stderr) finalize: the board would not list its in-review tickets; nothing is closed this tick
    (stderr) finalize: gh is not on PATH; merged pull requests cannot be read and nothing is closed this tick

Two helpers keep the shell readable, in the file's existing style
(`_api_py - <<'PY'` with `T_*` env for arguments; no apostrophes inside a
heredoc that sits in a command substitution):

- `_finalize_candidates` — prints the candidate rows (step 2).
- `_finalize_evidence <ticket>` — prints `no-trail`, `no-head`, or the sha
  (step 3b); non-zero exit only when the timeline read died.

A gh-bound checkout never reaches any of this: `_sweep_api.sh` refuses at
source time (`runs only under an api binding`, line 131). The test asserts it
anyway, as `test-sweep-renew-relay.sh` does for renew.

## `BOARD_PRINCIPAL` on `board-transition.sh`

`board-transition.sh`'s API arm calls `A.transition(...)` with the client's
default principal, `human`. A run context (explicit `BOARD_RUN_TOKEN`, or the
session's own seat) always wins inside `token()`, so the default is reached
only by a caller with no run — an operator shell, or this tick. The tick is
automation (its header says so at length) and its close must be recorded as
such: `actor_kind: automation` on the timeline, and never a human-authored
event, which is the convergence rule's adjudication reset.

Change: the API arm reads `BOARD_PRINCIPAL` (values `human` | `automation`,
default `human`; any other value dies with `BOARD_PRINCIPAL must be human or
automation`) into the python heredoc as `T_PRINCIPAL` and passes it as
`principal=` to `A.transition`. Ignored whenever a run context exists (that
is `token()`'s own rule; nothing to add). One header comment line beside the
`BOARD_OWNER_OVERRIDE` paragraph (board-transition.sh:55) names it. Nothing
else in the script changes; the gh arm ignores it.

## Acceptance

Observable on the hermetic suite and on the live board:

1. `_sweep_api.sh finalize` and `all` (after review-recover) visit this
   board's `in-review` tickets whose `pr_url` is a GitHub PR URL, read
   `gh pr view <url> --json mergedAt,mergeCommit,headRefOid`, and for a
   merged PR whose `headRefOid` equals the `reviewed head:` line of the
   latest `review-trail` event after the ticket's latest entry into
   `in-review`, write `in-review → done` with the note above — as the
   owning run when a seat record on this machine carries that run's bearer
   and is not mid-turn, otherwise as the automation principal with
   `BOARD_OWNER_OVERRIDE` naming the pass.
2. A `done` the server refuses with `review-trail-required` is logged with
   the server's message and left alone: exactly one transition attempt per
   tick, no forced close, the ticket stays in-review.
3. A merged PR whose `headRefOid` differs from the trail's `reviewed head:`
   is not closed; the `merged off the reviewed head` line names both shas.
4. An unmerged PR is untouched and logs nothing. A merged PR with no trail
   since the latest entry into `in-review`, or whose latest trail names no
   head, is untouched and logged. A ticket whose owner seat is mid-turn is
   untouched and logged. An epic (numeric `pr_url`) is skipped without a gh
   call.
5. `tests/claude-code/board-api/test-sweep-finalize.sh` drills every case
   above plus the gh-bound refusal, hermetically (fixture mock, stub gh,
   stub sminos), and is listed in `run-skill-tests.sh`.
6. `qa-loop.md`'s Review Trail section requires the `reviewed head: <sha>`
   line; its armed-`DONE` passage names the API finalize pass beside gh's
   FINALIZE (the verbatim return line
   `auto-merge armed on <sha>; the board's finalize pass writes done` is
   unchanged — `test-qa-loop-agent.sh:223` pins it); `agents/codex/qa-loop.toml`
   mirrors both edits; `references/review-loop.md`'s Merge authority
   paragraph names the API pass; TECH-DEBT.md row 26 is struck.

## Plan of Work

### M1 — the knob and the phase

`skills/issue-tracker/scripts/board-transition.sh`: in the API arm (the
block beginning `if [ "$BOARD_BINDING" = api ]; then` around line 196), the
env prefix on the transition heredoc gains `T_PRINCIPAL="${BOARD_PRINCIPAL:-human}"`;
the python reads it, dies on a value outside `("human", "automation")`, and
passes `principal=env["T_PRINCIPAL"]` to `A.transition`. Add the validation
in shell before the heredoc rather than in python if that reads better —
either way the message is `BOARD_PRINCIPAL must be human or automation`. Add
one comment line to the header paragraph that documents
`BOARD_OWNER_OVERRIDE` (line 55): `BOARD_PRINCIPAL=automation` makes a
run-less caller's write the automation principal's (the sweep's finalize
pass rides it); a run context always wins.

`skills/issue-tracker/scripts/_sweep_api.sh`:

- Line 3's phase order becomes `renew → stall → review-recover → finalize →
  relay → resume-first → fresh claims`; line 5's usage gains `finalize`.
- A `FINALIZE` paragraph in the header's phase list, after `REVIEW RECOVER`,
  in that list's voice: the ticket whose PR merged after its QA agent
  returned; merge state from GitHub, the reviewed head from the trail, the
  close only when both agree; the server's gate binds run actors only, so
  the predicate is applied here before either write; refused closes are
  logged and left to the recovery ladder; the seat is the renew step's to
  retire.
- `_finalize_candidates`, `_finalize_evidence`, `phase_finalize` after
  `phase_review_recover` (ends at line 1574), exactly as § The pass
  describes. Mirror `phase_review_recover`'s idioms: `_budget_left` with a
  `budget_said` guard is not needed here since the loop breaks; `2>&1`
  capture of `board-transition.sh` output for the outcome read; `>&2` for
  the stderr lines.
- `finalize) phase_finalize ;;` in the case, and `phase_finalize || true`
  on the line after `phase_review_recover || true` in the `all` arm, with a
  two-line comment: it runs before relay and resume so a ticket it closes is
  neither resumed nor claimed by a stand-in later this tick, and after
  review-recover so a nudge and a close never target the same seat in one
  tick.
- The usage `die` at the bottom gains `finalize`.

Run `scripts/lint-shell.sh` after; the file is under shellcheck.

### M2 — the hermetic suite

`tests/claude-code/board-api/test-sweep-finalize.sh`, modelled line for line
on `test-sweep-retire-finished.sh` (header comment stating the state this
pass exists for and the pins; `free_port`/`wait_for_port`; `TDIR`; creds
`BOARD_AUTOMATION_TOKEN=a` / `BOARD_HUMAN_TOKEN=h`; fixture JSON; the mock;
`mkrepo` with an api `board.json`; a registry under `DH`; the sminos stub;
an `SW` runner). Three seams are new:

- A **stub gh** directory prepended to `PATH` in `SW`. The stub appends
  `GH $*` to `$TDIR/gh.log`, answers `pr view <url> --json …` from a case on
  the PR number parsed from the URL (`${url##*/}`), and exits 2 on any other
  verb. The fixture world, PR by PR (use one 40-hex sha per name;
  `printf 'a%.0s' {1..40}`-style constants are fine):
  - 80: merged; `headRefOid` = SHA80; `mergeCommit.oid` = M80.
  - 81: `mergedAt` null, `mergeCommit` null.
  - 82: merged at SHA82.
  - 83: merged; `headRefOid` = SHA83M (the trail will name SHA83R).
  - 85: merged at SHA85.
  - 86: merged at SHA86.
  - 87: merged at SHA87.
  - 88: merged at SHA88.
- The **list fixture**: `GET /tickets?limit=200&states=in-review` (the
  client appends `&repo=testrepo`; the mock matches by prefix) answering
  `{"items":[…],"next":null,"as_of":1}` with rows carrying `id`, `state`,
  `priority`, `title`, `pr_url`, `owner_run`:
  - 80 `https://github.com/o/r/pull/80`, owner_run 80 — the happy path, owner idle.
  - 81 `…/pull/81`, owner_run 81 — unmerged.
  - 82 `…/pull/82`, owner_run null — merged at the reviewed head, no seat; the server refuses.
  - 83 `…/pull/83`, owner_run 83 — merged off the reviewed head.
  - 84 `"512"`, owner_run 84 — an epic's package id.
  - 85 `…/pull/85`, owner_run 85 — trail without a head line.
  - 86 `…/pull/86`, owner_run 86 — the only trail predates the latest entry into in-review.
  - 87 `…/pull/87`, owner_run 87 — owner seat `working`.
  - 88 `…/pull/88`, owner_run null — merged at the reviewed head, no seat; the server accepts.
- **Timelines** (`GET /tickets/<n>/timeline`, each registered AHEAD of any
  `/tickets/<n>` prefix it shares, as review-recover's fixture notes):
  - 80, 82, 87, 88: `[transition to in-review (cursor 1), review-trail (cursor 2) with text "round 1 — level medium\nreviewed head: <SHA>"]`.
  - 83: the same with `reviewed head: SHA83R`.
  - 85: trail text `"round 1 — level medium"` (no head line).
  - 86: `[review-trail (cursor 1) naming SHA86, transition to in-review (cursor 2)]`.
  - 81 and 84 need none (never read).
  Transition record bodies carry `to` (the server folds `to_state` into the
  body: `{"note":"…","to":"in-review"}`); trail bodies carry `text`.
- **Transitions**: `POST /tickets/80/transition` → 200 `{"ok":true,"to":"done"}`;
  `/tickets/82/transition` → 403
  `{"error":{"code":"review-trail-required","message":"in-review → done needs a review-trail event by this run after the latest entry into in-review"}}`;
  `/tickets/88/transition` → 200. No fixture for any other ticket: an
  unexpected POST answers 404 and the assertion on the request log catches it.
- **Registry**: `u-80` idle, run 80, bearer `tok-80`, fence 1, ticket 80,
  `bind_confirmed` true, phase review; `u-81`, `u-83`, `u-85`, `u-86`
  likewise on their tickets; `u-87` the same but `status: working`. No seat
  for 82, 84, 88.

Assertions (with `t`/`nt` on `cat "$FIX.log"`, `cat "$TDIR/gh.log"`, and
the tick output):

- 80: a `POST /tickets/80/transition` whose `auth` is `Bearer tok-80`, whose body carries `"to": "done"` and a note containing `merged as M80 at the reviewed head SHA80`; the success line ends `done written as run 80`.
- 81: gh was asked about `pull/81`; no POST for 81; no `#81` line in the output.
- 82: exactly one POST for 82 (`grep -c`), `auth` `Bearer a`; the output carries `the board refused done (review-trail-required)`.
- 83: no POST; the output line names both `SHA83M` and `SHA83R`.
- 84: gh.log has no line containing `512`; no POST.
- 85: no POST; `names no reviewed head`.
- 86: no POST; `no review-trail since the ticket last entered review`.
- 87: no POST; `owner u-87 is mid-turn`.
- 88: a POST with `Bearer a` and the note; `done written as automation`.
- `all`: a second registry-free run is not needed; instead run `SW all`
  once against the same world and assert the 80 success line appears (the
  phase is wired into `all`); the renew/stall/relay/resume phases will log
  404s for their own routes — add the two empty-list fixtures
  `GET /answers/unrelayed → []` and `GET /runs/needing-resume → []`, and a
  `POST /runs/<n>/renew → 200 {"renewed":true}` per seated run (80, 81,
  83, 85, 86, 87), so the tick reaches finalize quietly, as
  review-recover's whole-tick drill does. Register the whole-tick drill
  AFTER the `finalize`-only assertions and reset `$FIX.log` between them,
  so the `grep -c` counts above stay exact.
- gh-bound: `wrong_binding` as in `test-sweep-renew-relay.sh:605` running
  `_sweep_api.sh finalize` from a repo with no api `board.json`; assert
  `runs only under an api binding`, and that `gh.log` did not grow.

Add `"board-api/test-sweep-finalize.sh"` to the list in
`tests/claude-code/run-skill-tests.sh` directly after
`"board-api/test-sweep-review-recover.sh"`.

Then run every sweep suite, not only the new one — the new phase runs under
`all`, and the existing whole-tick drills (`test-sweep-renew-relay.sh`'s
`board-sweep runs the api tick`, `test-sweep-review-recover.sh`'s whole-tick
candidate) now issue a `GET /tickets?limit=200&states=in-review…` their
fixtures do not answer. The list read dies, the phase logs its one stderr
line and `all` continues; confirm each suite still passes. If one fails on
that line, add an empty-list fixture for the route to that suite rather
than softening the phase.

### M3 — the agent, the manual, the tracker

`agents/qa-loop.md`:

- Review Trail section (the paragraph beginning `The review-trail comment
  records:`): after `the level and the auto-merge value you ran with;`
  insert `the reviewed head — the sha your merge is pinned to — on its own
  line as exactly `reviewed head: <sha>` (the API tick's finalize pass
  compares it with the head GitHub merged and closes the ticket only when
  they agree, so a trail without it leaves an armed merge to the recovery
  ladder);`.
- Escalate section, the armed path (the paragraph after the indented
  `auto-merge armed on <sha>; the board's finalize pass writes done` line,
  beginning `— the merge completes when the checks pass`): replace through
  `which is why `done` is not yours to write on this path.` with: `— the
  merge completes when the checks pass, and the board's finalize pass
  finishes what your ended turn cannot: on the gh binding the sweep's
  FINALIZE pass (the PR's `Closes` link closes the issue; the pass strips
  labels and runs the terminal sweeps), on the API binding the API tick's
  finalize pass, which reads the merge from GitHub and writes `done` when
  the merged head is your trail's `reviewed head:`. That is why `done` is
  not yours to write on this path, and why the head line in the trail is
  not optional.` Keep the sentence that follows about a repo refusing
  auto-merge.
- Nothing else in the file moves; run `tests/issue-tracker/test-qa-loop-agent.sh`
  before and after.

`agents/codex/qa-loop.toml`: the same two edits at the mirrored passages
(its Review Trail and Escalate text is the Markdown's verbatim; find them by
the same anchor strings).

`tests/issue-tracker/test-qa-loop-agent.sh`: beside the existing
`trail_section` assertions (line 234), add
`assert_text_contains "$trail_section" "reviewed head: <sha>" "the trail names the reviewed head for the API finalize pass" "Review Trail"`.

`skills/issue-tracker/references/review-loop.md`, Merge authority paragraph
(the parenthesis `pending checks arm GitHub auto-merge — when that merge
lands after the agent's turn ended, the board sweep's FINALIZE pass completes
the ticket bookkeeping the PR's `Closes` link cannot`): extend to `… the
board sweep's FINALIZE pass completes the ticket bookkeeping the PR's
`Closes` link cannot on the gh binding, and on the API binding the API tick's
finalize pass reads the merge from GitHub and writes `done` when the merged
head is the trail's `reviewed head:``.

`docs/doperpowers/TECH-DEBT.md` row 26: strike the description the way rows
1, 2 and 10 are struck — `~~An armed auto-merge never reaches `done` on the
API binding by itself …~~ **SHIPPED 2026-09-23** (`_sweep_api.sh` finalize
phase: PR merged at the trail's reviewed head → `in-review → done`; see
`docs/doperpowers/specs/2026-09-23-api-finalize-pass-design.md`)`, trigger
column `—`.

## Concrete Steps

Working directory: the worktree this spec sits in, branch `74-api-finalize`.

    # M1
    scripts/lint-shell.sh                                  # baseline, before edits
    # …edit board-transition.sh and _sweep_api.sh…
    scripts/lint-shell.sh                                  # must stay clean
    git add -A skills/issue-tracker/scripts && git commit -m "sweep(api): a finalize pass closes a ticket whose PR merged at the reviewed head"

    # M2
    bash tests/claude-code/board-api/test-sweep-finalize.sh
    # expect: ok lines for every case, ending "PASS test-sweep-finalize.sh"
    for s in tests/claude-code/board-api/test-sweep-*.sh; do bash "$s" | tail -1; done
    # expect: one PASS line per suite
    git add -A tests && git commit -m "tests: the api finalize pass, hermetic"

    # M3
    bash tests/issue-tracker/test-qa-loop-agent.sh | tail -3
    # expect: the summary with 0 failures
    git add -A agents skills/issue-tracker/references docs/doperpowers/TECH-DEBT.md tests/issue-tracker && git commit -m "qa-loop: the trail names the reviewed head; the API finalize pass beside gh's FINALIZE"

    # finish
    bash tests/claude-code/run-skill-tests.sh 2>&1 | tail -20   # the whole hermetic tier; integration suites skip without ARKHO_DIR
    git push -u origin 74-api-finalize
    gh pr create --base main --title "sweep(api): a finalize pass closes a ticket whose PR merged at the reviewed head" --body-file .architect/74/pr-body.md

Commit messages carry no attribution footer of any kind (the repository's
global rule: no `Co-Authored-By`, no `Generated with`, no session URL). The
PR body states the purpose, the server-gate finding (§ What the server
enforces), the new trail line, and the test command. `.architect/` is
untracked scratch: never `git add` it.

## Interfaces and Dependencies

- `skills/issue-tracker/scripts/_sweep_api.sh`: `phase_finalize()`,
  `_finalize_candidates()`, `_finalize_evidence <ticket>`; case arm
  `finalize`; wired into `all` after `phase_review_recover`.
- `skills/issue-tracker/scripts/board-transition.sh`: env `BOARD_PRINCIPAL`
  ∈ {`human`, `automation`}, default `human`, API arm only, ignored under a
  run context.
- The trail contract line, exact: `reviewed head: <sha>` — 40 lowercase hex,
  on its own line, in the text of the `review-trail` event the QA agent
  posts before merging or arming.
- The finalize note, exact shape:
  `finalize: <pr_url> merged as <oid> at the reviewed head <sha>`.
- Reads: `gh pr view <pr_url> --json mergedAt,mergeCommit,headRefOid`;
  `_board_api.tickets_all(states="in-review", principal="automation")`
  (rows carry `id`, `state`, `pr_url`, `owner_run`);
  `_board_api.timeline(tid, principal="automation")["records"]` (each:
  `source`, `cursor`, `kind`, `runId`, `body`; a transition's body carries
  `to`; a trail's body carries `text`).
- Writes: `board-transition.sh <ticket> done "<note>"` under either
  `BOARD_RUN_TOKEN`/`BOARD_RUN_ID`/`BOARD_RUN_FENCE` or
  `BOARD_PRINCIPAL=automation BOARD_OWNER_OVERRIDE="…"`.
- Registry: `_metas_for_ticket <ticket>` → `uuid \x1f bearer \x1f run \x1f fence`;
  `_meta_field "$DAEMON_HOME/<uuid>.json" status`.

## Decision Log

- Decision: The pass applies the evidence predicate client-side before any
  write, and still writes as the owning run whenever a local seat carries it.
  Rationale: the server gates `in-review → done` for run actors only
  (transitions.js, API.md §4.2 "a human's or an automation's terminal write
  is unrestricted"); the ticket's "the evidence-gated close is the guard"
  is true only on the run path. Carrying the predicate here keeps the
  ticket's intent — a close under the same gate — on both paths, and the
  run path gains the server's stricter by-this-run check for free. A
  technical correction within the approved intent, not a scope change.
  Rejected: run-path only (leaves the ownerless case — the human-merge
  path, whose owner is usually gone — exactly where it is today).
  Date/Author: 2026-09-23, Architect #74.
- Decision: The trail carries `reviewed head: <sha>` as a contract line and
  the pass fails closed without it.
  Rationale: nothing else on the ticket names the reviewed head; the QA
  agent knows it exactly and already posts the trail before the merge or
  the arm. Prose parsing of the existing trail is not a contract.
  Rejected: reading the head from the `in-review` transition (it carries
  none); trusting `--match-head-commit` alone (true for the armed path,
  false for a merge by hand).
  Date/Author: 2026-09-23, Architect #74.
- Decision: Compare GitHub's `headRefOid` with the trail's head, not the
  merge commit's parent.
  Rationale: `headRefOid` is the PR head at merge time under every merge
  method, and the head `--match-head-commit` pins; a squash or rebase merge
  commit's parent is the base. The ticket's "merge commit's parent head"
  wording is read as this.
  Date/Author: 2026-09-23, Architect #74.
- Decision: `BOARD_PRINCIPAL` on `board-transition.sh` rather than a direct
  client call from the tick.
  Rationale: the transition script owns the dp#63 fence, the seat's phase
  stamp and the board-map re-render; a direct `A.transition` would skip all
  three. The knob is three lines and is inert under a run context.
  Rejected: writing as the human default (a human-authored event is the
  convergence rule's adjudication reset, and misattributes the close).
  Date/Author: 2026-09-23, Architect #74.
- Decision: An owner seat that is mid-turn is left alone.
  Rationale: its own QA agent may be verifying the same merge and about to
  write `done`; racing it buys one `illegal-transition` line and nothing
  else. The retire step defers a working seat for the same reason.
  Date/Author: 2026-09-23, Architect #74.
- Decision: No by-id re-read between the list and the write; unmerged PRs
  log nothing.
  Rationale: the transition is the authoritative act and the server refuses
  a moved ticket; a log line per open PR per tick is noise.
  Date/Author: 2026-09-23, Architect #74.
- Decision: Verification is one independent spec review
  (`doperpowers:adversarial-reviewer`, focused on completeness against the
  ticket's acceptance and buildability by a zero-context executor) before
  the build edge, then the board's review loop on the PR at level `medium`.
  Rationale: bounded, mechanical work on a well-drilled file; the one
  novel finding (the server's principal asymmetry) is a fact from the
  server source, not a design fork.
  Date/Author: 2026-09-23, Architect #74.

## Surprises & Discoveries

- Observation: the server's `review-trail-required` gate binds run actors
  only; an automation or human `in-review → done` is unrestricted.
  Evidence: arkho `board-service/src/transitions.js` — the guard block is
  `if (actor.cls === 'run' && TERMINAL.includes(to))`; API.md §4.2:
  "Terminal-edge authority for run actors (a human's or an automation's
  terminal write is unrestricted)".
- Observation: no artifact on the ticket names the reviewed head today.
  Evidence: `board-transition.sh … in-review --pr <url> --branch <b>`
  carries no sha; `qa-loop.md`'s Review Trail list has no head entry; the
  only head is the `DONE` return's second line, which reaches the
  dispatcher's transcript and nothing durable.
- Observation: `board-transition.sh` writes as the human principal whenever
  no run context exists — including the review-recover cap park.
  Evidence: `A.transition(tid, …)` with `principal` defaulted to `"human"`;
  `token()` returns `BOARD_HUMAN_TOKEN` for it. Pre-existing; the finalize
  pass is the first caller that needs to say otherwise.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- 2026-09-23: first revision, authored from ticket #74 and the sweep, client,
  agent and server sources it names.
