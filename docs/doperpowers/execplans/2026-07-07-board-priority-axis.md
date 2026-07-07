# Add a priority axis to the issue-tracker board

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. It is maintained in accordance with the plugin's vendored ExecPlan doctrine at `skills/execspec/references/PLANS.md` (repository-relative path).

## Purpose / Big Picture

The issue-tracker board (the `doperpowers:issue-tracker` skill) manages a project's work as GitHub issues, and its whole point is answering "what should an agent or human pick up next?". Today the board can only say *which tickets are startable* (the ELIGIBLE computation in `board-list.sh`); it cannot say which startable ticket matters most. After this change, every ticket carries exactly one managed priority label — `priority:P0` (drop everything) through `priority:P3` (someday) — registration refuses a ticket without one, `board-list.sh` orders its output so the highest-priority work floats to the top, the rendered board (BOARD.md table and BOARD.html graph/kanban) displays each ticket's priority, and a one-line command re-prioritizes a ticket later. A human can see it working by registering a ticket without a priority (it fails with a usage error), registering one with `P1` (the GitHub issue is born with the `priority:P1` label), and running `board-list.sh` (P0/P1 rows print above P2/P3 and unprioritized rows).

## Progress

- [x] (2026-07-07 19:55Z) Grill completed with the human partner; five decisions recorded in the Decision Log below.
- [x] (2026-07-07 20:05Z) Worktree `worktree-board-priority-axis` created from `origin/main` (commit 96dc645, v7.5.1); this plan written and committed.
- [x] (2026-07-07 20:35Z) Milestone 1: data layer — `_board.py` constants, snapshot `priority` field, label filter, `ensure_labels` rename, `set_priority_label` mutation.
- [x] (2026-07-07 20:40Z) Milestone 2: registration forces priority (third positional arg) and creates the label at birth.
- [x] (2026-07-07 20:45Z) Milestone 3: new `board-priority.sh` re-prioritization command.
- [x] (2026-07-07 20:55Z) Milestone 4: surfacing — `board-list.sh` sort+column, lint WARN/FAIL rules, BOARD.md column, BOARD.html badge/detail/kanban-sort.
- [x] (2026-07-07 21:00Z) Milestone 5: SKILL.md contract updates (register signature, board-priority in toolkit table, dispatch-order guidance, lint rules list).
- [x] (2026-07-07 21:10Z) Milestone 6: tests — update existing register fixtures, add priority assertions, full suite green.
- [x] (2026-07-07 21:12Z) Version bump to 7.6.0, RELEASE-NOTES entry.
- [ ] Exit gate: Codex whole-branch review; fix confirmed findings; re-run suite; one re-review.
- [ ] Merge to origin/main, tag v7.6.0, retrospective written.

## Surprises & Discoveries

- Observation: the close path keeps the ticket's priority label by design, and the existing test `status labels stripped on close` asserted label-set equality, so it went red the moment registration started attaching `priority:*` — the one legitimately failing assertion in the whole arity migration. Updated it to expect `['enhancement', 'priority:P1']`, which now *documents* the keep-on-close decision.
  Evidence: suite run after Milestone 6 — single FAIL at `status labels stripped on close`, green after the expectation change.
- Observation: the two anticipated risks were real but pre-empted — `board-migrate-gh.sh`'s heredoc call site was caught by the raw-string grep (three call sites total: register, transition, migrate), and the kanban sort was written with an explicit rank function from the start.
  Evidence: `grep -rn 'ensure_status_labels'` listed board-migrate-gh.sh:61 alongside the two obvious callers.

## Decision Log

- Decision: single priority axis; no separate impact label.
  Rationale: the board's consumer picks a dispatch order; one axis IS that order, while impact×urgency matrices need a collapse rule anyway and rot in practice. Rejected: `priority`+`impact` two-label scheme (double annotation burden, undefined combined ordering); forced-priority-plus-optional-impact (optional fields go unused).
  Date/Author: 2026-07-07 / grill with human partner.
- Decision: scale is `P0`–`P3`, stored as labels `priority:P0`…`priority:P3`.
  Rationale: industry-standard reading; lexicographic string order equals priority order, so every sort in shell/python/JS is one comparison with no mapping table. Rejected: high/medium/low (h<l<m breaks lexicographic sorting); P0–P2 (no backlog grade, P2 becomes a dumping ground).
  Date/Author: 2026-07-07 / grill.
- Decision: registration takes priority as a third positional argument — `board-register.sh <title> <category> <priority>`.
  Rationale: mirrors how `category` is already forced; omitting it fails structurally. Rejected: required `--priority` flag (a mandatory flag contradicts flag conventions and splits the contract style); default-P2 (silent default converges to "everything is P2", zero information).
  Date/Author: 2026-07-07 / grill.
- Decision: re-prioritization via a new dedicated `board-priority.sh <n> <P0..P3>`.
  Rationale: one job, one command; managed label swap mirrors `set_state_label`'s philosophy. Rejected: `--priority` option on `board-transition.sh` (forces a fake state transition to change only priority); documenting raw `gh issue edit` (manual swaps create two-label conflicts).
  Date/Author: 2026-07-07 / grill.
- Decision: lint treats a missing priority on an open ticket as WARN, and two-plus `priority:*` labels as FAIL. Closed tickets are not checked.
  Rationale: the real consumer (ida-solution) has dozens of open tickets with no priority; a FAIL would flip its board lint red on day one and break workflows that gate on exit code. WARN lists them for gradual backfill while registration forces the label on all new tickets, so the gap converges to zero. A double label is an invariant violation regardless of history → FAIL. Rejected: FAIL both (forces an immediate mass backfill session); no check (manual label edits would drift silently).
  Date/Author: 2026-07-07 / grill.
- Decision: `board-list.sh` sorts every row by (priority rank, issue number), missing priority ranking after P3; the per-state filter argument is unchanged.
  Rationale: the list's job after this change is dispatch order; number order survives as the tiebreaker. Delegated to the implementer during the grill.
  Date/Author: 2026-07-07 / implementer.
- Decision: rename `_board.py:ensure_status_labels()` to `ensure_labels()` and have it ensure both `status:*` and `priority:*` labels in the same single `gh label list` pass; update every caller.
  Rationale: every write path that needs one family needs the other; two functions would double the `gh label list` round-trip on registration. The old name would lie about the function's scope.
  Date/Author: 2026-07-07 / implementer.
- Decision: closed tickets may keep their priority label (no lint rule, no strip on close).
  Rationale: unlike `status:*` (where a stale label contradicts the derived done/wontfix state), a priority on a closed ticket is inert history; stripping it would add write traffic for zero invariant value.
  Date/Author: 2026-07-07 / implementer.

## Outcomes & Retrospective

Pending — written at finish.

## Context and Orientation

This repository is `doperpowers`, a plugin of agent skills. One skill, `skills/issue-tracker/`, manages a project's work items ("tickets") as GitHub issues — the issues ARE the board; there is no local state file. The skill ships shell scripts in `skills/issue-tracker/scripts/` that read and mutate the board through the GitHub CLI (`gh`). A shared python module `skills/issue-tracker/scripts/_board.py` is the only data layer: its `snapshot()` function fetches every issue with one paginated GraphQL query and normalizes each into a python dict (a "ticket"); its mutation helpers (`edit_labels`, `set_state_label`, `close`, `comment`, `update_meta`) are the only write path. Shell scripts source `skills/issue-tracker/scripts/_lib.sh` (which resolves the target repo into `$BOARD_REPO`) and run inline python with `_board` importable.

Ticket *state* (ready-for-agent, in-progress, blocked, …) is already expressed as managed labels with the prefix `status:` — "managed" means scripts create the labels if missing (`ensure_status_labels()` in `_board.py`, using `STATUS_COLORS` at the top of the file) and swap them atomically (`set_state_label`), and `board-lint.sh` fails the board when an issue carries zero or two-plus `status:*` labels. This plan clones that exact philosophy for a new `priority:` label family.

Files you will touch, all repository-relative:

    skills/issue-tracker/scripts/_board.py            data layer: constants, snapshot(), mutations
    skills/issue-tracker/scripts/board-register.sh    opens a ticket; currently `<title> <category>` positional
    skills/issue-tracker/scripts/board-priority.sh    NEW: swap a ticket's priority label
    skills/issue-tracker/scripts/board-list.sh        flat board view with ELIGIBLE computation
    skills/issue-tracker/scripts/board-lint.sh        invariant checker; FAIL exits 1, WARN exits 0
    skills/issue-tracker/scripts/board-map.sh         renders BOARD.md (table) + BOARD.html (graph/kanban)
    skills/issue-tracker/scripts/board-map.template.html  the HTML/JS template board-map.sh fills
    skills/issue-tracker/scripts/board-migrate-gh.sh  v6→v7 importer — calls ensure_status_labels in a heredoc
    skills/issue-tracker/SKILL.md                     the skill contract agents read
    tests/issue-tracker/test-board-scripts.sh         mock-backed integration suite
    tests/issue-tracker/mock-gh/gh                    fake `gh` used by the suite (already supports label list/create and issue edit --add-label/--remove-label; no mock changes are expected)

Orientation inside `_board.py` (line numbers as of commit 96dc645): `STATUS_PREFIX`/`STATUS_COLORS` sit near line 42; `snapshot()` builds the ticket dict near line 190 — note its `labels` field filters out `STATUS_PREFIX` and the category names, and must additionally filter the new priority prefix; `ensure_status_labels()` is near line 251; `set_state_label` near line 273. `board-register.sh` validates category in its inline python ("category must be bug|enhancement") and calls `B.ensure_status_labels()` just before `gh issue create --label …`. `board-list.sh` iterates `sorted(tickets, key=int)` and prints one row per ticket. `board-lint.sh` accumulates `FAIL`/`WARN` lines and exits 1 iff any FAIL. In `board-map.template.html`, ticket cards are built in two places (graph card near the `bits.push` cluster around line 251, kanban card around line 353), the detail panel rows in `showDetail`, and kanban columns are assembled near line 372.

Versioning: `scripts/bump-version.sh <ver>` updates every manifest listed in `.version-bump.json` and audits for stragglers; releases get an entry at the top of `RELEASE-NOTES.md` and an annotated-style lightweight tag `vX.Y.Z`. The `.codex-plugin/` directory contains only a manifest (bump handles it); no sync script needs to run for a release.

## Plan of Work

Milestone 1, data layer. In `_board.py`, next to `STATUS_PREFIX`, add `PRIORITY_PREFIX = "priority:"`, `PRIORITIES = ("P0", "P1", "P2", "P3")`, and `PRIORITY_COLORS = {"P0": "b60205", "P1": "d93f0b", "P2": "fbca04", "P3": "c2e0c6"}` (GitHub label hex without `#`; red → orange → yellow → pale green, matching the loudness of each grade). Rename `ensure_status_labels()` to `ensure_labels()` and extend its single pass to also create missing `priority:*` labels from `PRIORITY_COLORS` with description "issue-tracker board priority"; update every caller — grep for the *string* `ensure_status_labels` across the whole repo because `board-migrate-gh.sh` calls it inside a python heredoc that a syntax-aware search misses. In `snapshot()`, derive `prios = [l[len(PRIORITY_PREFIX):] for l in labels if l.startswith(PRIORITY_PREFIX)]`, then store `"priority": prios[0] if len(prios) == 1 and prios[0] in PRIORITIES else None` and `"priority_labels": prios` (the second field lets lint distinguish "missing" from "conflicted" exactly as `status_labels` does for state). Extend the ticket's `labels` passthrough filter to also exclude `PRIORITY_PREFIX`-prefixed names. Add a mutation `set_priority_label(num, node, to)` mirroring `set_state_label`: remove every label in `node["priority_labels"]` (prefixed back), add `PRIORITY_PREFIX + to`, one `edit_labels` call.

Milestone 2, forced registration. In `board-register.sh`, shift the positional contract to `<title> <category> <priority>`: assign `priority="$3"` before the option loop starts consuming from `$4`, pass it into the inline python environment, and validate there with `if priority not in B.PRIORITIES: B.die("priority must be one of %s" % "|".join(B.PRIORITIES))` right after the category check. Include `priority:` + the grade in the `--label` argument of `gh issue create` so the ticket is born labeled. Update the usage header comment. The call to the renamed `ensure_labels()` already guarantees the label exists.

Milestone 3, re-prioritization. Create `skills/issue-tracker/scripts/board-priority.sh` (mode 755), shaped like the other small scripts (`board-relate.sh` is the closest template): source `_lib.sh`, usage-die on wrong arity, `T_ID="$1" T_P="$2" _py - <<'PY' … PY` resolving the ticket via `B.resolve`, validating the grade against `B.PRIORITIES`, calling `B.set_priority_label`, and printing the transition as `#12: P2 → P0` — when the ticket had no priority, print `none` on the left side. Re-running with the same grade is a no-op that still prints (idempotent).

Milestone 4, surfacing. `board-list.sh`: compute `rank = B.PRIORITIES.index(p) if p in B.PRIORITIES else len(B.PRIORITIES)` and iterate `sorted(tickets, key=lambda t: (rank(t), int(t)))`; print the priority (or `-`) as a fixed-width column right after the state column. `board-lint.sh`: for open tickets, `len(priority_labels) == 0` → WARN `no priority label` with FIX hint `board-priority.sh <n> <P0..P3>`; `len >= 2` → FAIL `2+ priority labels (<bare grades>)` with a FIX hint whose argument is a bare grade (e.g. `board-priority.sh 12 P0`), never the raw label name — the command takes grades, not label names. `board-map.sh`: add a `priority` column to the BOARD.md fallback table (empty cell when unset) and a `"priority": n.get("priority")` entry in the HTML node payload. `board-map.template.html`: in both card builders push the priority into the existing `bits` badge row when present; in `showDetail` add a `priority` row; in the kanban assembly sort each column's tickets with an explicit rank function (`P0`→0 … `P3`→3, missing→4, then by numeric id) — do not compare `n.priority` strings directly, because `null` versus string comparison in JS coerces and mis-sorts. `board-show.sh` needs no edit: it dumps the whole ticket dict, so the new `priority` key appears automatically.

Milestone 5, contract. In `skills/issue-tracker/SKILL.md`: every `board-register.sh` example gains the priority argument; the toolkit script table gains a `board-priority.sh` row; the section describing how a dispatcher picks work states the rule "among ELIGIBLE tickets, take the lowest P first (P0 before P1 …); `board-list.sh` already presents them in that order"; the lint rules list gains the WARN/FAIL pair.

Milestone 6, tests. In `tests/issue-tracker/test-board-scripts.sh`: append a grade to every existing `board-register.sh` invocation (vary the grades so ordering is testable — make ticket #9's grade P1 and give at least one later ticket P0). Add assertions: `assert_fails run board-register.sh "X" bug` (missing priority) and `assert_fails run board-register.sh "X" bug P9` (bad grade); after a register, `assert_contains "$(state "s['issues']['1']['labels']")" "priority:"`; a `board-priority:` section running `board-priority.sh 1 P0` asserting the `→ P0` report and the label swap in mock state, plus a no-priority ticket (strip the label via a one-line python edit of `$MOCK_GH_STATE`) asserting the `none → P2` report; a lint section asserting WARN on a stripped ticket (exit stays 0 when no FAILs) and FAIL on a hand-added second priority label; a list section asserting the P0 row prints above the P1 row. Run the full suite until `all tests passed`.

Release. `scripts/bump-version.sh 7.6.0`, prepend a RELEASE-NOTES.md entry (what the axis is, the forced register contract change — this is breaking for register callers — the lint policy, the backfill path), commit, then the exit gate below.

## Concrete Steps

All commands run from the worktree root `/Users/new/Documents/GitHub/doperpowers/.claude/worktrees/board-priority-axis` (any checkout of this branch works; paths below are repo-relative).

Implement milestones 1–5 as edits to the files named above. Then:

    tests/issue-tracker/test-board-scripts.sh

Expected tail of output:

    board-priority:
      [PASS] register is born labeled
      [PASS] swap reported as #1: P1 → P0
      [PASS] unset reported as none
      [PASS] lint WARNs missing priority
      [PASS] lint FAILs duplicate priority
      [PASS] list floats P0 above P1
    all tests passed

(Exact PASS labels may differ; `all tests passed` and exit 0 are the contract.) Then:

    scripts/lint-shell.sh                # shellcheck baseline must stay clean
    scripts/bump-version.sh 7.6.0        # ends with "All clear."
    git add -A && git commit             # feature commit(s), Korean message, no Co-Authored-By

Exit gate (one, at the end): dispatch a whole-branch review to Codex via the codex:rescue subagent (`--model gpt-5.5 --effort high`), diffing `origin/main...HEAD`, asking for correctness bugs and contract mismatches; fix what is confirmed, re-run the suite, re-review once. Then merge: push the branch, fast-forward or merge into `origin/main` directly (this fork allows it), tag `v7.6.0`, push tag, remove the worktree.

## Validation and Acceptance

Acceptance is behavioral. In a repo using the board (the mock suite simulates one): running `board-register.sh "Fix crash" bug` (no priority) exits non-zero printing `priority must be one of P0|P1|P2|P3`; running `board-register.sh "Fix crash" bug P1` prints the new issue number and URL, and `gh issue view` (or the mock state) shows labels `bug`, `status:ready-for-agent`, `priority:P1`; running `board-priority.sh <n> P0` prints `#<n>: P1 → P0` and the issue now carries exactly `priority:P0`; `board-list.sh` prints that ticket's row above any P1 row and shows `P0` in its priority column; `board-lint.sh` on a board with one unprioritized open ticket prints one WARN and exits 0, and after adding a second priority label by hand it prints a FAIL and exits 1; `board-map.sh --write` renders a BOARD.md whose table has a priority column and a BOARD.html whose node payload contains `"priority": "P0"`. The full suite `tests/issue-tracker/test-board-scripts.sh` prints `all tests passed` and exits 0.

## Idempotence and Recovery

Every step is re-runnable: label creation is guarded by a list-then-create pass (`ensure_labels`), `set_priority_label` removes-then-adds so a re-run converges, the test suite provisions a fresh temp repo per run, and `bump-version.sh` is a plain overwrite with a built-in audit. If a milestone leaves the suite red, `git checkout -- <file>` restores the last committed state of any single file; the worktree isolates everything from the diverged local `main`, so aborting is `git worktree remove` with no cleanup elsewhere. The only shared mutable surface is `origin/main` at the final merge; if the push races another session's push, `git pull --rebase origin main` in the worktree and re-run the suite before retrying.

## Artifacts and Notes

Expected shape of the suite's tail after Milestone 6 (to be replaced with the real transcript once it exists):

    board-register:
      [PASS] prints number + url
      [PASS] refused: run board-register.sh X bug          (missing priority)
      [PASS] refused: run board-register.sh X bug P9       (bad grade)
    board-priority:
      [PASS] #1: P1 → P0 reported and label swapped
      [PASS] none → P2 on unprioritized ticket
    board-lint:
      [PASS] WARN no priority label (exit 0)
      [PASS] FAIL 2+ priority labels (exit 1)
    board-list:
      [PASS] P0 row above P1 row
    all tests passed

## Interfaces and Dependencies

No new external dependencies; everything rides the existing `gh` CLI plumbing. At the end of the work these interfaces exist:

In `skills/issue-tracker/scripts/_board.py`:

    PRIORITY_PREFIX = "priority:"
    PRIORITIES = ("P0", "P1", "P2", "P3")
    PRIORITY_COLORS: dict[str, str]           # grade -> label hex
    def ensure_labels() -> None               # replaces ensure_status_labels; ensures status:* AND priority:*
    def set_priority_label(num, node, to) -> None
    # snapshot() tickets additionally carry:
    #   "priority": str | None                # the single valid grade, else None
    #   "priority_labels": list[str]          # raw grades found (for lint's missing-vs-conflict split)

In `skills/issue-tracker/scripts/`:

    board-register.sh <title> <category> <priority> [--state S] [--note TEXT] [--parent N] [--blocked-by N[,N...]] [--spawned-by N] [--body-file F]
    board-priority.sh <number> <P0|P1|P2|P3>   # prints "#N: <old|none> → <new>"

## Revision Notes

- 2026-07-07: Initial authoring after the grill; Decision Log seeded with the five human-approved decisions plus three implementer decisions (list sort order, ensure_labels rename, closed-ticket priority retention). Execution has not started; Progress beyond plan-authoring is unchecked.
