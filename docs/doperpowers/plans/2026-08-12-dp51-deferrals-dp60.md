# dp#51 deferrals + dp#60 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use doperpowers:subagent-driven-development (recommended) or doperpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six items of spec `docs/doperpowers/specs/2026-08-12-dp51-deferrals-dp60-design.md` (v1.1): the dp#60 meta-truncation bug, the gh-path QAGENT answer return, typed successor-claim escalation, list-read truncation hardening + the arkho contract pin, the bootstrap parity fence, and drill assertion anchoring.

**Architecture:** All client-side shell/python in `skills/issue-tracker/scripts/` and `skills/reviewing-prs/scripts/`, plus tests. No arkho code changes (one arkho ISSUE is filed). Items are independent; tasks are ordered so §1's helper lands before its consumer.

**Tech Stack:** bash 3.2-compatible shell, python3 heredocs, the repo's fixture mock (`tests/claude-code/board-api/mock-server.py`), `t`/`nt` helpers.

## Global Constraints

- The spec is authoritative: `docs/doperpowers/specs/2026-08-12-dp51-deferrals-dp60-design.md` v1.1. Read your task's spec section before coding.
- Every new test assertion must be shown RED against the task's parent commit before the fix lands (stash the source change or render from `git show <parent>:<file>`).
- bash 3.2: no `${var:+...}` with quotes inside heredoc-adjacent expansions, no associative arrays, herestrings for `grep -Fq` (pipefail SIGPIPE).
- Board tokens never in fixtures, logs, or committed files.
- Commits: conventional style, NO Co-Authored-By or attribution lines.
- Thin client invariant (`_board_api.py` header): client checks only cheap argv validation; the server owns legality.
- Mock fixture discipline: mock external responses from real observed shapes; nested error envelope is `{"error":{"code":"...","message":"..."}}`.

---

### Task 1: §1 value grammar + `meta_match` helper in `_board.py`

**Files:**
- Modify: `skills/issue-tracker/scripts/_board.py` (META_RE block, `parse_meta` `:238-251`, `strip_meta` `:254-257`, `render_body` `:273-281`)
- Test: `tests/issue-tracker/test-board-scripts.sh`

**Interfaces:**
- Produces: `B.meta_match(body)` → rightmost `re.Match` of `META_RE` or `None`. `B.render_body(body, meta)` now normalizes `\r`/`\n` in values to a single space and calls `B.die(...)` when a value contains `<!-- board:meta` or `-->`.

- [ ] **Step 1: Write the failing tests.** In `tests/issue-tracker/test-board-scripts.sh`, add a `meta-grammar:` section (follow the file's existing section style — direct `_py` heredocs are fine where the file already does that). Cases:

```bash
# (a) dp#60 reproduction: a body whose PROSE quotes a marker example keeps
#     its prose across a meta write, and parse_meta reads the REAL block.
# Build the body in python to control bytes exactly:
#   prose = "Docs about the block:\n\n    <!-- board:meta\n    pr: fake\n    -->\n\nMore prose."
#   body  = B.render_body(prose, {"pr": "https://real/1"})
#   assert B.parse_meta(body) == {"pr": "https://real/1"}
#   assert "More prose." in B.strip_meta(body)
#   assert B.strip_meta(body).rstrip() == prose.rstrip()
# (b) round-trip: B.render_body(B.strip_meta(body), B.parse_meta(body)) == body
# (c) contract_hash(body) == contract_hash of a body with DIFFERENT meta,
#     same prose (hash covers prose only)
# (d) grammar: render_body({"note": "line1\nline2"}) renders "note: line1 line2"
# (e) grammar: render_body({"note": "x\n<!-- board:meta"}) exits nonzero with
#     a message naming the offending key
```

Note case (a)'s quoted example is INDENTED (four spaces) — `META_RE` requires the marker at line start after `\n?`, so also add case (a2) with the marker example at column 0 (the reproduced dp#60 shape).

- [ ] **Step 2: Run the section, verify the dp#60 cases FAIL** against current `_board.py` (a2 fails: parse_meta returns `{"pr": "fake"}`; d/e fail: no normalization). Record the failure lines.

- [ ] **Step 3: Implement.** In `_board.py`, after `META_RE`:

```python
def meta_match(body):
    """The RIGHTMOST META_RE match — the real trailing block. A leftmost-first
    search anchors on a marker QUOTED in the prose and its lazy middle spans
    to the real trailing `-->` (#60); every match ends at end-of-string
    (`\\s*$`), so the rightmost START is the actual block. render_body's value
    grammar (single-line, no marker tokens) is what makes this sound: the
    block itself can never contain a marker."""
    m, pos = None, 0
    body = body or ""
    while True:
        nxt = META_RE.search(body, pos)
        if not nxt:
            return m
        m, pos = nxt, nxt.start() + 1
```

`parse_meta`: replace `m = META_RE.search(body or "")` with `m = meta_match(body)`.
`strip_meta`:

```python
def strip_meta(body):
    """The body WITHOUT its trailing board:meta block — the ticket's own text,
    with the board's bookkeeping removed."""
    m = meta_match(body)
    return ((body or "")[:m.start()] if m else (body or "")).rstrip("\n")
```

`render_body`: before building the block —

```python
    clean = {}
    for k, v in meta.items():
        if not v:
            continue
        v = re.sub(r"[\r\n]+", " ", str(v))
        if "<!-- board:meta" in v or "-->" in v:
            die("meta value %r cannot carry a board:meta marker token" % k)
        clean[k] = v
    meta = clean
```

(replacing the existing `meta = {k: v for k, v in meta.items() if v}` line).

- [ ] **Step 4: Run the new section AND the full `tests/issue-tracker/test-board-scripts.sh`** — all green (the file has many existing meta round-trip pins; they must survive).

- [ ] **Step 5: Commit** `fix(board): rightmost meta block + value grammar — gh meta writes stop truncating marker-quoting bodies (#60)`.

### Task 2: §1 `board-body.sh` uses the shared helper

**Files:**
- Modify: `skills/issue-tracker/scripts/board-body.sh:64-83` (the gh-half inline walk)
- Test: `tests/claude-code/board-api/test-edge-verbs.sh` (existing pins)

**Interfaces:**
- Consumes: `B.meta_match` from Task 1.

- [ ] **Step 1:** Replace the inline `while True` walk (`board-body.sh:73-79`) with `m = B.meta_match(old)`, keeping the splice line and the comment's first paragraph (trim the now-redundant leftmost-first explanation to a pointer: "the helper walks to the rightmost match — see _board.meta_match (#60)").
- [ ] **Step 2:** Run `tests/claude-code/board-api/test-edge-verbs.sh` — the meta-splice pins ("keeps the TRAILING meta block byte-for-byte", "the quoted marker example did not survive as a splice point") stay green.
- [ ] **Step 3: Commit** `refactor(board-body): splice via the shared meta_match helper`.

### Task 3: §2 QAGENT role — stamp, three-way arm, `--pr` re-supply

**Files:**
- Modify: `skills/reviewing-prs/scripts/review-dispatch.sh` (`_spawn_reviewer`, after the `board-bind.sh` call at `:931`)
- Modify: `skills/issue-tracker/scripts/board-answer.sh` (`:185-209`)
- Test: `tests/issue-tracker/test-board-scripts.sh` (Finding-D section `:957-999`), `tests/reviewing-prs/test-review-dispatch.sh`

**Interfaces:**
- Consumes: registry meta JSON has top-level `"name"` (verified); `implement-dispatch.sh:848-870` is the stamp pattern to mirror.
- Produces: gh-spawned reviewer metas carry `role: QAGENT`; `board-answer.sh` returns qagent parks to `in-review`.

- [ ] **Step 1: Failing tests (board-answer side).** In `test-board-scripts.sh` after the existing Finding-D cases:

```bash
# QAGENT with pr: meta → in-review, no --pr from the caller
#   (fixture meta: role: QAGENT, no pre-park; ticket meta carries pr: https://…)
#   → assert status:in-review
# QAGENT with NO pr: meta → in-progress + warning
#   → assert status:in-progress AND output contains "no pr: meta"
# legacy meta with NO role but registry name review-pr-<n> → in-review
#   (name-inference rung)
```

Also amend the `:987` assertion text: "an unrecorded pre-park with an IMPLEMENT role falls back on in-progress".

- [ ] **Step 2: Run — all three FAIL** (current code returns in-progress everywhere).

- [ ] **Step 3: Implement board-answer.sh.** Replace `:199`'s single line with:

```python
    role = (meta.get("role") or "").upper()
    if not role and str(meta.get("name") or "").startswith(("review-pr-", "review-epic-")):
        role = "QAGENT"   # pre-stamp reviewers: the deterministic worker
                          # name is the only role record they carry
    if role == "ARCHITECT":
        ret = "in-design"
    elif role == "QAGENT":
        ret = "in-review"
    else:
        ret = "in-progress"
```

CHECK FIRST how `meta` is loaded (`board-answer.sh:104-160`): if the dict is the registry-file JSON, `name` is already a key; if it is a sub-object, read the name from the enclosing record and thread it through the same tab-separated line (`:200-201`) — extend that line rather than re-reading files.

Then at the transition call (`:204-209`): when `ret == "in-review"`, read `pr = B.parse_meta(tickets[tid]["body"]).get("pr")` (the body is already fetched for pre-park); if present, append `--pr "$pr"` to the `board-transition.sh` argv; if absent, demote `ret` to `in-progress` and print `relay: #<tid> — QAGENT return wants in-review but the ticket has no pr: meta; falling back to in-progress` on stderr. The demotion happens where `ret` is computed (python), so the shell side stays a single conditional argv append.

- [ ] **Step 4: Run the section — green.** Run the whole `test-board-scripts.sh`.

- [ ] **Step 5: Failing test (stamp side).** In `tests/reviewing-prs/test-review-dispatch.sh`, at the existing bound-meta assertion (`:418` area), add: the spawned reviewer's registry meta carries `"role": "QAGENT"`. Verify RED (nothing stamps it), then implement in `_spawn_reviewer` after `board-bind.sh` succeeds (`review-dispatch.sh:931`), mirroring `implement-dispatch.sh:848-870`:

```bash
  # Persist role: QAGENT into the registry meta — board-answer.sh's
  # needs-human fallback reads it to return a qagent park to in-review
  # instead of in-progress. Non-fatal, same shape as implement-dispatch's
  # gh-side role write; pre-stamp metas are covered by the name-inference
  # rung in board-answer.sh.
  T_UUID="$uuid" DAEMON_HOME="$DAEMON_HOME" python3 - <<'PY' \
    || echo "$name: role meta write failed (non-fatal)" >&2
  ... (read-modify-write-under-lock; m["role"] = "QAGENT")
PY
```

Copy the lock discipline from `implement-dispatch.sh:848-870` exactly.

- [ ] **Step 6: Run `tests/reviewing-prs/test-review-dispatch.sh` — green. Commit** `fix(board-answer): qagent parks return to in-review — role stamp, name inference, pr re-supply`.

### Task 4: §3 typed claim errors + counting

**Files:**
- Modify: `skills/issue-tracker/scripts/_board_api.py` (`claim_successor` `:145`, near `RunEnded` `:24`)
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh` (`_resume_one` exits `:1157-1167`, `_attempts` `:1393-1412`, `_escalate` body text)
- Test: `tests/claude-code/board-api/test-sweep-resume.sh`

**Interfaces:**
- Consumes: arkho answers 409 `{"error":{"code":"nonce-consumed",...}}` and `{"error":{"code":"stale-resume",...}}` (verified in claims.js).
- Produces: `claim_successor` distinguishable outcomes; `_attempts fail` callable with no run argument.

- [ ] **Step 1: Failing tests.** Four new fixtures/scenarios in `test-sweep-resume.sh` (follow its `"once":true` fixture idiom, `:65-94`):

```bash
# (a) claim-successor → 500 {"error":{"code":"internal","message":"boom"}}
#     → t "a claim ERROR charges a recovery cycle" "recovery cycle 1 of 3"
#       t "and the journal is kept as the replay handle"  (journal file exists)
# (b) claim-successor → 409 {"error":{"code":"nonce-consumed",...}}
#     → nt (no "recovery cycle"); journal file REMOVED; sweep exits 0
# (c) claim-successor → 409 {"error":{"code":"stale-resume",...}}
#     → same as (b)
# (d) claim-successor → 200 {"claimed":false}
#     → nt (no "recovery cycle"); journal removed; exit 0  (pins the
#       existing behavior the spec keeps)
```

- [ ] **Step 2: Verify (a) FAILS** (no cycle charged today) and (b)/(c) fail on the journal assertion (today both die and keep it). (d) may already pass — keep it as the guard pin.

- [ ] **Step 3: Implement client typing.** In `_board_api.py`, mirror the `RunEnded` pattern: a `ClaimObsolete(Exception)` carrying `.code`, raised by `claim_successor` when the 409 envelope's `error.code` is `nonce-consumed` or `stale-resume`. Do it inside `claim_successor` (catch the die path — if `request()` structure makes that awkward, add an `on_codes={...}` hook to `request()` in the same style `run-ended` is special-cased; keep the change minimal and local).

- [ ] **Step 4: Implement sweep routing.** In `_resume_one`'s claim block, the python that calls `A.claim_successor` prints a typed sentinel for the two obsolete codes (e.g. `OBSOLETE <code>` on stdout) instead of dying; the shell exit `:1157-1161` becomes:

```bash
# obsolete journal (nonce-consumed / stale-resume): the JOURNAL is done,
# not the substrate — drop it uncharged; the feed re-serves the ticket
# with a fresh nonce (nonce-consumed) or its new state governs (stale-resume).
# Any OTHER claim error is a fault: charge the cycle, keep the journal.
```

with three arms: obsolete → `rm -f "$CLAIMS_DIR/$nonce.json"`, log, `return 0`; error → `_attempts "$tid" fail`, journal kept, `return 1`; granted → continue. `_attempts` (`:1393`): guard the run-release block (`:1403-1412`) with `[ -n "${2:-}" ]` — wait, signature is `_attempts <tid> fail <run>`; make the third argument optional and skip `A.end_run` when absent.

- [ ] **Step 5: `_escalate` wording.** Body text: "Three recovery cycles failed for ticket #%s (successor claim, resume, or fresh spawn)…" — title unchanged (dedupe key).

- [ ] **Step 6: Run the full `test-sweep-resume.sh` — green** (the existing cycle-1/2/3 pins at `:464-501` must survive the `_attempts` signature change). **Commit** `fix(sweep): type the successor-claim failures — obsolete journals drop uncharged, faults count (#51)`.

### Task 5: §3 one attempt per ticket per tick + reconcile honors suppression

**Files:**
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh` (`_reconcile_successors` `:971-1038`, `phase_resume` `:1505-1535`)
- Test: `tests/claude-code/board-api/test-sweep-resume.sh`

- [ ] **Step 1: Failing tests.** (a) one ticket with a kept journal (replay) AND on the needing-resume feed in the same tick → count claim POSTs in the mock log, assert exactly 1 (today: 2). (b) a suppressed ticket with a standing journal → reconcile makes NO claim POST and the journal file survives.
- [ ] **Step 2: Implement.** `_reconcile_successors`: skip (leave journal untouched) when `_suppressed "$tid"`; when it DOES replay a ticket, append the tid to a tick-scoped file (e.g. `$dir/resumed-tids`, where `$dir` is the phase temp dir — check how reconcile and phase_resume share scope; if they don't share a dir, thread one variable). `phase_resume`'s feed loop: skip tids present in that file (same style as the `_suppressed` skip at `:1535`), logging `resume: #$tid — already replayed this tick`.
- [ ] **Step 3: Green + full file. Commit** `fix(sweep): one recovery attempt per ticket per tick; reconcile honors suppression`.

### Task 6: §4 `_check_lift` absent-row guard

**Files:**
- Modify: `skills/issue-tracker/scripts/_sweep_api.sh:744-761` (`_check_lift`)
- Test: `tests/claude-code/board-api/test-sweep-resume.sh`

- [ ] **Step 1: Failing test.** A suppression record for a ticket that is MISSING from the `/tickets` fixture → the suppression record file survives the tick (today: both lift conditions fire and it is removed).
- [ ] **Step 2: Implement.** In the `_check_lift` python (`:753-755`): absent rows are UNKNOWN, not moved/closed —

```python
cur = rows.get(str(rec["ticket"]))
moved = cur is not None and cur != rec["state"]
env = rows.get(str(rec["env_issue"]))
closed = env in ("done", "wontfix")   # absent env-issue: unknown, keep waiting
```

Add the mirror of the write-site comment (`:1438`): "AN ABSENT ROW IS NOT A STATE — a truncated or partial /tickets read must never lift a suppression."
- [ ] **Step 3: Green + full file. Commit** `fix(sweep): an absent /tickets row never lifts a suppression`.

### Task 7: §4 arkho contract issue

**Files:** none (outward action).

- [ ] **Step 1:** `gh issue create -R SSFSKIM/arkho-a1-board-service` — title: `contract pin (A2): /queue/decisions and /tickets are read whole — unbounded until a paged envelope exists`. Body: the client reads both routes whole (`_board_api.py queue_decisions/tickets`); the destructive-consumer example (`_check_lift`, now guarded client-side); quote `API.md:383-384`/`:900-903` ("A2/A3 contract territory") as the invitation; ask that (1) any future cap on these two routes arrive WITH a response envelope (cursor/total) so truncation is detectable, (2) the existing 500-caps on `/answers/unrelayed` and `/runs/needing-resume` be added to API.md's "Boundary bounds" table. Reference doperpowers#51.
- [ ] **Step 2:** Record the issue URL in the SDD ledger and in the spec's `## Outcomes & Retrospective` material notes.

### Task 8: §5 renderer fails closed + call-site binding assertions

**Files:**
- Modify: `skills/reviewing-prs/scripts/review-dispatch.sh:848-868` (`_render_prompt`)
- Test: `tests/reviewing-prs/test-review-dispatch.sh`, `tests/claude-code/board-api/test-review-dispatch-claim.sh`

- [ ] **Step 1:** Enumerate every `{{NAME}}` in `review-worker-bootstrap.md` per mode (after mode-strip) and diff against the `P_*` sets at the four call sites (`:625`, `:776`, `:1512`). Fix any call site that omits a placeholder its mode renders (expect none — but this step is the proof).
- [ ] **Step 2: Failing test.** In `test-review-dispatch.sh`: a render driven with one `P_*` deliberately unset → dispatcher exits nonzero naming the placeholder (drive `_render_prompt` the way the suite drives dispatch; if only reachable through a full dispatch, assert the dispatch fails loudly). Verify RED (today it renders blank and succeeds).
- [ ] **Step 3: Implement.** Port `implement-dispatch.sh:109-114`'s unresolved-placeholder check into `_render_prompt` (`review-dispatch.sh:866`): substitute known, collect unknown, print `unrendered placeholders: <names>` to stderr and exit 1.
- [ ] **Step 4:** Add captured-prompt content assertions in both suites: gh (`test-review-dispatch.sh`, prompt file from the stub `:78`) asserts `BIND_READY_FILE`/`SKILL_FILE`/`IMPLEMENT_PROTOCOL_FILE`/`BOARD_SCRIPTS` lines are non-empty; api (`test-review-dispatch-claim.sh`, `prompt()` `:235`) additionally `TICKET_BODY_FILE`. Non-empty = the binding line has a value after the colon (anchor on the rendered line shape).
- [ ] **Step 5: Both suites green. Commit** `fix(review-dispatch): unresolved bootstrap placeholders fail the render; suites pin critical bindings non-empty`.

### Task 9: §5 static parity fence

**Files:**
- Create: `tests/reviewing-prs/test-bootstrap-parity.sh`
- Modify: `tests/reviewing-prs/` runner registration (see how sibling tests are invoked — `tests/claude-code/run-skill-tests.sh` and/or a local runner)

- [ ] **Step 1:** Write the fence per spec §5 piece 2, all assertions in one new file (use `t`/`nt`-style local helpers or the `assert_contains` idiom from `test-skill-entrypoint.sh:17-45`):
  - honesty pins: `BOOTSTRAP_TEMPLATE=` path literal in `review-dispatch.sh`; mode-fence regex literal; `{{(\w+)}}` substitution literal;
  - render all four modes via a local ~20-line python renderer over the real template with a complete fixture (every placeholder set to `X-<NAME>` so emptiness is impossible and value-tracing trivial);
  - load-bearing sentences in every mode's render: the skill-pin sentence, the precedence clause, the worktree caveat, and each mode's read-it-live rewording pinned `t` in its own render and `nt` in the other pair-member's;
  - roster relation (gh ⊂ api modulo the pinned four; api adds exactly its pinned extras);
  - block-boundary tail check (strip mode-owned + binding lines; remainder identical within each pair);
  - no `mode:` fence and no `{{` in any render;
  - implement lane: `worker-bootstrap.md` with/without `api-only`, outside-region identity, roster `+TICKET_BODY_FILE +PARENT_PIN`.
- [ ] **Step 2: Prove the fence bites:** scratch-edit one shared-tail word inside a single mode block copy (temporary file), rerun, watch it fail; discard the scratch. Also temporarily gate a shared binding line into one mode fence in a template COPY and watch the boundary check fail.
- [ ] **Step 3: Register in the runner, run, green. Commit** `test(reviewing-prs): bootstrap parity fence — four modes, pinned sentences, roster and boundary checks`.

### Task 10: §6 drill cosmetics

**Files:**
- Modify: `tests/claude-code/board-api/integration/test-transcript-diff.sh` (`:151`, `:214`, `:100-115`), `test-protocol-walk.sh` (`:73-74,79,96-97`), `test-crash-boundaries.sh` (`:76,86,122,135,154`), `test-resume-first.sh` (`:95-96,103`), `test-escalation.sh` (`:76,107,114`), `test-human-verbs.sh` (`:162,175`), `transcript-compare.py` (`:103`)

- [ ] **Step 1:** Apply the spec §6 list: delimit `owner_line()`/`row()` scalar output (bracket or trailing `.`), anchor every listed assertion to the closed form; JSON ids closed with `,`/`}`; the `grep -q` regex at `test-escalation.sh:76` anchored `[,}]`; `:151` → non-empty + exact match; `:214` → `#4242` phrase; record `%T`-unsubstituted argv alongside executed argv in the walk capture and compare THAT in `transcript-compare.py:103`.
- [ ] **Step 2:** These are tightenings — every touched drill must still PASS as-is (unit-runnable parts; the integration drills need `ARKHO_DIR` + docker — run what the environment allows, and say exactly which drills ran).
- [ ] **Step 3:** Discrimination probe (not committed): in a scratch copy, offset one ticket id (e.g. make the walk register twice so ids differ) and confirm the anchored assertions now FAIL where the old substrings passed; note the probe result in the task report.
- [ ] **Step 4: Commit** `test(drills): anchor id assertions; compare unsubstituted argv (#51 cosmetics)`.

### Task 11: Final verification

- [ ] **Step 1:** Full suites: `tests/issue-tracker/test-board-scripts.sh`; every `tests/claude-code/board-api/test-*.sh`; `tests/reviewing-prs/test-review-dispatch.sh`, `test-skill-entrypoint.sh`, `test-bootstrap-parity.sh`; `tests/claude-code/board-api/integration/` drills if `ARKHO_DIR`+docker available (exit 77 = SKIP is acceptable, say so); `scripts/lint-shell.sh`.
- [ ] **Step 2:** Execute the spec's `## Acceptance` items as written (the marker-quoting body write; the qagent park answer walk; the 500-fixture escalation; the missing-row suppression survival; the parity-fence scratch-edit bite check).
- [ ] **Step 3:** Report each acceptance item's actual command + output in the task report.
