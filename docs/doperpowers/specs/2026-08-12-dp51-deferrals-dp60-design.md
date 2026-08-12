# dp#51 deferrals + dp#60 — design

**Purpose.** Close out the tail of the A1/A2 board program: the five
non-consumption deferrals recorded on dp#51 after PR #61 shipped, plus
dp#60, the live gh-mode meta-truncation bug found during that work. Six
bounded items, each independently shippable; together they remove every
known correctness hole in the client toolkit short of the arkho-side
contract work they pin.

All six were investigated against the code before this spec was written;
every load-bearing claim below carries its file:line. Base:
`dp51-deferrals-dp60` branched from main `d8427d73` (v7.48.0).

---

## §1 dp#60 — gh-mode meta writes truncate marker-quoting bodies

**The bug.** `_board.META_RE` (`_board.py:189`) is
`\n?<!-- board:meta\n(.*?)\n-->\s*$` with `re.S`. `re.search` is
leftmost-first and the lazy `.*?` spans from the FIRST marker occurrence
to the trailing `-->` — so on a body whose PROSE quotes a
`<!-- board:meta` marker (documentation about the meta block), the match
starts at the quoted marker and swallows the real prose after it. Every
META_RE consumer inherits this:

- `parse_meta` (`:240`) parses the QUOTED block's lines instead of the
  real trailing block — silently wrong meta reads;
- `strip_meta` (`:257`, `META_RE.sub("")`) deletes everything from the
  quoted marker onward — the reproduced truncation;
- `contract_hash` (`:270`) and `render_body` (`:276`) go through
  `strip_meta`, so every gh-mode meta write (`update_meta`,
  `_board.py:749`) rewrites the body from the truncated base. One write
  destroys the prose permanently.

**The fix — one shared rightmost-match helper.** `board-body.sh:73-79`
already carries the proven pattern (walk `META_RE.search(body, pos)` with
`pos = m.start()+1` until exhausted; the LAST match is the real block —
`\s*$` anchors every match to end-of-string, so the rightmost start is
the true trailing block by construction). Hoist it into `_board.py`:

```python
def meta_match(body):
    """The RIGHTMOST META_RE match — the real trailing block. Leftmost-first
    search anchors on a marker QUOTED in the prose and spans to the real
    trailing `-->`; the rightmost start is the actual block (#60)."""
    m, pos = None, 0
    body = body or ""
    while True:
        nxt = META_RE.search(body, pos)
        if not nxt:
            return m
        m, pos = nxt, nxt.start() + 1
```

- `parse_meta`: `m = meta_match(body)` in place of `META_RE.search`.
- `strip_meta`: `m = meta_match(body)`; return
  `(body[:m.start()] if m else body or "").rstrip("\n")` — byte-offset
  slicing, no `.sub`. (`m.end() == len(body)` because `\s*$` consumes to
  the end, so slicing at `m.start()` is the whole removal.)
- `render_body`, `contract_hash`, `update_meta`: unchanged — they inherit
  correctness through `strip_meta`/`parse_meta`.
- `board-body.sh` gh half: replace its inline walk (`:73-79`) with
  `B.meta_match(old)` — same behavior, one author. The raw-splice
  property is untouched: the helper returns a match object; the splice
  keeps consuming `old[m.start():]` verbatim.

**Behavior preserved:** on bodies with zero or one marker the helper
finds the same match `META_RE.search` found; only multi-occurrence
bodies change, and for those the old answer was the bug.

**Value grammar enforced (adversarial-review finding, reproduced).**
Rightmost matching is only correct when the real trailing block cannot
itself CONTAIN a marker — and today it can: `render_body`
(`_board.py:280`) writes values verbatim, so a `note` value carrying
`"\n<!-- board:meta\npr: …"` mints a second marker INSIDE the real
block; the rightmost match then starts there and `parse_meta` returns
the forged keys (reproduced: real block at offset 12, rightmost match
at 56, `pr` forged). Meta values are single-line by grammar —
`parse_meta` reads the block line-wise, so a multi-line value is
already silent corruption. Enforce it at the write: in `render_body`,
collapse every separator `str.splitlines()` recognizes — not `\r`/`\n`
alone; `\v`, `\f`, `\x1c`–`\x1e`, `\x85`, U+2028/U+2029 would remain
injectable as forged keys through `parse_meta`'s `splitlines()` (plan
review finding) — via `" ".join(value.splitlines())`, and `die` on a
value containing `<!-- board:meta` (unrepresentable in the block; loud
beats mangled). `-->` is NOT rejected (v1.2.1, task-review finding,
fuzz-proven): after the splitlines collapse every value sits behind its
`key: ` prefix, so a `-->` can never reach line start where `META_RE`
requires it — rejecting it would brick every pre-fix ticket whose
stored note carries an arrow (update_meta re-renders every parsed key
on every write) and was the only realistic trigger of a TORN WRITE in
`apply_state` (label already moved, meta write then dies). The
surviving marker check must run BEFORE any external write in
`apply_state`'s callers reaches GitHub — validate, then write. With
the grammar enforced, the rightmost match is the real block by
construction.

**Tests (RED against the parent commit):** a body whose prose quotes a
full marker-shaped example AND carries a real trailing block —
`parse_meta` returns the real block's keys; `strip_meta` keeps the prose
including the quoted example; an `update_meta` round-trip preserves the
prose byte-for-byte outside the block; `contract_hash` of that body
equals the hash of the prose. Home: `tests/issue-tracker/test-board-scripts.sh`
(the gh-mode pin) — plus the existing board-body drill keeps passing.

---

## §2 gh-path board-answer QAGENT role fallback

**The gap (three parts, all verified).**

1. `board-answer.sh:199` — the whole gh-leg role resolution:
   `ret = "in-design" if role == "ARCHITECT" else "in-progress"`. No
   QAGENT arm: even a stamped `role: QAGENT` returns `in-progress`.
2. gh-mode `review-dispatch.sh` never stamps `role` at all —
   `_spawn_reviewer` writes no role/lane (contrast: the api claim path
   stamps both at `review-dispatch.sh:1561`; gh `implement-dispatch.sh`
   stamps role at `:848-870`). So the meta is doubly silent.
3. Even with both fixed, `board-transition.sh:238-257` refuses
   `in-review` without `--pr` unless `pre-park == "in-review"` — and the
   fallback fires precisely when there is no recorded pre-park.

Live surface: parks that reach `needs-human` from outside `PRE_PARK`
(`_board.py:60-66`) — for a qagent, realistically
`in-review → needs-info → needs-human`. Damage when it fires: the ticket
lands at `in-progress`, the review sweep's stale-reviewer arm
(`review-dispatch.sh:1115-1160`) sees an off-review ticket and retires
the resumed qagent's meta out from under it.

**The fix — three small, matching pieces.**

1. **Stamp the role at gh reviewer spawn.** In `_spawn_reviewer`
   (`review-dispatch.sh:876`, after the `board-bind.sh` call at `:931`),
   write `role: QAGENT` into the registry meta — same non-fatal
   read-modify-write-under-lock shape as `implement-dispatch.sh:848-870`
   (role only; `lane` stays an api-claim concept). Applies to both
   `review-pr-*` and `review-epic-*` spawns — an epic scale reviewer is
   the same protocol.
2. **Add the QAGENT arm, with a legacy rung.** `board-answer.sh:199`
   becomes a three-way: `ARCHITECT → in-design`, `QAGENT → in-review`,
   else `in-progress` — where the role is resolved in two rungs: the
   `role:` meta first; when absent, infer QAGENT from the registry
   record's deterministic worker `name` (`review-pr-*` /
   `review-epic-*`; the registry JSON carries `"name"` at top level,
   verified live). The inference rung covers every reviewer parked
   before this version deploys and every spawn whose non-fatal stamp
   write failed — without it the fix is upgrade-gated
   (adversarial-review finding).
3. **Re-supply `--pr` from the ticket's own meta.** When the QAGENT arm
   selects `in-review`, `board-answer.sh` reads the ticket's `pr:` meta
   (`parse_meta(tickets[tid]["body"]).get("pr")` — it already parses
   this body for `pre-park`) and passes it as `--pr` to
   `board-transition.sh`. The gate at `board-transition.sh:238` is then
   satisfied on its own terms — no gate relaxation. A ticket that entered
   `in-review` via the gh path necessarily carries `pr:` (the `--pr`
   write stamps it); if it is nonetheless absent, keep the prior
   `in-progress` fallback and print a one-line warning naming the missing
   meta — fail-open to the old behavior, never a hard death on the
   answer path.

**Out of scope (recorded, not built):** the adjacent wrong-pre-park case
— a qagent that bounces `in-review → ready-for-architect` and then parks
records `pre-park: in-design`, which the role fallback never reaches.
That is a PRE_PARK design question, not a fallback bug; noted for the
issue.

**Tests (RED first):** in `tests/issue-tracker/test-board-scripts.sh`'s
Finding-D section (`:957-999`): a `role: QAGENT` meta with no pre-park
and a `pr:` meta → `status:in-review` without the caller supplying
`--pr`; a `role: QAGENT` meta with no `pr:` meta → `status:in-progress`
plus the warning line; amend the `:987` wording ("a non-architect role
falls back on in-progress") to name IMPLEMENT. In
`tests/reviewing-prs/test-review-dispatch.sh`: the spawned reviewer's
registry meta carries `"role": "QAGENT"` (today nothing asserts any role
there).

---

## §3 successor-claim escalation

**The gap (verified).** `_resume_one` (`_sweep_api.sh:1084`) charges the
existing per-ticket counter (`_attempts`, `:1393`;
`$SUPPRESS_DIR/.attempts-<tid>`) only at four post-grant exits
(`:1186,1248,1300,1325`). Both claim-failure exits bypass it:

- (a) claim errored (`:1157-1161`) — `return 1`, journal deliberately
  kept (the claim may have landed);
- (b) `claimed:false` (`:1163-1167`) — `return 0`, journal removed.

A ticket whose claim persistently errors churns forever, and worse: the
kept journal is re-classified `replay` by `_reconcile_successors`
(`:971`) next tick while the feed ALSO re-serves the same ticket with a
fresh nonce — two claims and one leaked journal file per tick.

**Rulings.**

1. **Type the claim errors before counting (adversarial-review
   finding, both codes verified in arkho source).** Not every claim
   error is a substrate fault — arkho answers two typed 409s that mean
   "this JOURNAL is obsolete", not "the substrate is sick":
   - `nonce-consumed` (`claims.js` nonceReplay: "a nonce on an ended
     run is spent, not replayable") — the predecessor's run ended;
     replaying this nonce is doomed forever. Action: DROP the journal
     (`rm` it), no cycle charged, `return 0` — the feed re-serves the
     ticket with a fresh nonce next tick.
   - `stale-resume` (`claims.js:393`) — the ticket moved after the
     feed read. Action: DROP the journal, no cycle charged, `return 0`
     — the ticket's new state governs; ordinary dispatch handles it.
   Everything else on the error exit — transport death after retries,
   5xx, malformed grant (missing runId/fence/bearer), untyped
   refusals — IS a fault: charge `_attempts "$tid" fail` (no run
   argument; there is nothing to release) and KEEP the journal as
   today. Client plumbing: `_board_api.py` already routes one typed 409
   (`RunEnded`, `:24,:104,:124`); extend the same pattern so
   `claim_successor` surfaces `nonce-consumed` and `stale-resume` to
   the sweep distinguishably.
   Path (b) `claimed:false` stays uncounted: it is the server's
   backpressure (lane cap, eligibility), a healthy wait state.
   Escalating it would write a suppression whose documented effect
   (`:744-761`, `:1535`, `:1572`) is to remove a healthy ticket from
   BOTH the resume and dispatch phases until a human closes an
   env-issue — strictly worse than the churn. With (b) uncounted, no
   reset-on-grant is needed: the counter keeps its existing reset at
   full delivery (`:1343`), and every counted event is a real fault.
2. **One attempt per ticket per tick.** `_reconcile_successors` runs
   before `phase_resume` (`:1509`); when it replays a nonce for ticket
   T, `phase_resume` must skip T this tick (record replayed tids in a
   tick-scoped temp file, consult it in the feed loop — same shape as
   the suppression skip at `:1535`). This kills both the double-charge
   and the journal-per-tick leak in one move.
3. **Reconcile honors suppression — and lift runs FIRST.**
   `_reconcile_successors` currently replays through a suppression (it
   runs before the skip). It gains the same `_suppressed` check
   `phase_resume` has: a suppressed ticket's journal is left in place,
   untouched, until the suppression lifts. The phase order moves to
   lift → reconcile → feed (today reconcile runs first,
   `_sweep_api.sh:1511`): with suppression-aware reconcile in the OLD
   order, a suppression lifting mid-tick would skip the journal in
   reconcile, lift, and then claim a FRESH nonce from the feed —
   stranding the old journal to replay beside the new successor later
   (plan review finding). Lift-first lets a just-lifted ticket replay
   its own standing journal.
4. **Generalize the escalation wording.** `_escalate`'s env-issue title
   stays (deterministic-title dedupe depends on it); the body's "Three
   resume and fresh-spawn cycles failed" becomes "Three recovery cycles
   failed (successor claim, resume, or fresh spawn)" — true for every
   counted cause.

**`_attempts fail` without a run:** the current implementation releases
the undeliverable run (`:1403-1412`); with no second argument it must
skip the release cleanly. Guard, don't refactor.

**Tests (RED first), in `test-sweep-resume.sh`:** a `claim-successor`
fixture answering 500 → "recovery cycle 1 of 3" printed, journal KEPT;
a 409 `nonce-consumed` fixture → journal REMOVED, no cycle, exit 0; a
409 `stale-resume` fixture → journal REMOVED, no cycle, exit 0; a
`claimed:false` fixture → no cycle charged, journal removed, exit 0
(the untested exits at `:1160`/`:1166` get their first fixtures, and
both typed 409s get one each); a replayed nonce + the same ticket on
the feed in one tick → exactly one claim POST on the wire; a suppressed
ticket with a standing journal → reconcile leaves it alone, no claim
POST.

---

## §4 list-read truncation & the pagination contract

**Headline correction (verified):** the deferral's premise was inverted.
`_sweep_api.sh` never reads `/queue/*`; the capped endpoints
(`limit 500`) are `/answers/unrelayed` (drained correctly in a loop,
`:604-608`) and `/runs/needing-resume` (single level-triggered read per
tick — safe; backlog >500 is unreachable short of a multi-day sweep
outage). The endpoints the client reads whole — `/queue/decisions`
(`server.js:404-424`) and `/tickets` (`tickets.js:299-307`) — have NO
server cap today, return bare arrays with no envelope, and arkho's
API.md defers real paging to "A2/A3 contract territory" twice
(`API.md:383-384`, `:900-903`).

**Rulings.**

1. **No cursor-follow is built.** There is no cursor on the wire to
   follow; building against an imagined contract is speculation. The
   timeline `cursor` field (`timeline.js:64`) is the designated growth
   seam when arkho takes it up.
2. **Pin the contract outward.** File an arkho issue stating the
   contract A2 relies on: `/queue/decisions` and `/tickets` are read
   whole and MUST stay unbounded until a paged read exists — any future
   cap must arrive with a response envelope (cursor/total) so truncation
   is detectable, plus a note that `API.md`'s "Boundary bounds" table
   omits the two existing 500-caps. The issue body quotes the two
   "A2/A3 contract territory" lines back at the server — arkho invited
   this pin.
3. **Fix the one silently destructive consumer.** `_check_lift`
   (`_sweep_api.sh:753-755`): a ticket absent from the `/tickets` read
   makes `rows.get(...)` return `None`, so BOTH lift conditions fire —
   the suppression lifts, the ladder re-runs, and a fresh env-issue is
   minted every three cycles. This is the exact bug class the write-site
   guard at `:1438-1450` documents ("AN EMPTY READ IS NOT A STATE").
   Mirror it at the read site: an absent ticket row means UNKNOWN —
   keep the suppression this tick (the env-issue row absent means the
   same; treat `None` as "not closed"). One guard, both `.get` sites.
4. **Nothing else changes.** The other truncation-fragile consumers
   (`board-show.sh:26`'s "no ticket #N", `board-lint.sh:54`, the map)
   are honest against today's contract — the contract pin in (2) is what
   keeps them honest tomorrow. No length-sentinel: on an unbounded
   route, an exactly-500 response is a legal board size, and a sentinel
   would cry wolf on it.

**Tests (RED first), in `test-sweep-resume.sh`:** a suppression record
whose ticket is MISSING from the `/tickets` fixture → the suppression
survives the tick (no lift, no rm), and the sweep prints nothing louder
than its normal line. (The arkho issue is an action, not a test.)

---

## §5 bootstrap-prompt comparison fence

**The hazard (verified).** The review bootstrap is one template
(`review-worker-bootstrap.md`, 203 lines) with four mutually exclusive
`<!-- mode:X -->` blocks — gh (`pr`, `scale`) and api (`api`,
`api-scale`) framings authored separately around a SHARED tail (skill
pin `:126-129`, worktree caveat `:152-156`, bindings roster, manifest
snapshots `:199-203`) that is interleaved with mode blocks, not one
contiguous slice. Nothing compares a gh render to an api render; the
relay-prompt drill (`test-transcript-diff.sh:230-283`) exists because
this exact two-authors drift already happened in an 8-line prompt — this
one is 203 lines. Bonus asymmetry: `review-dispatch.sh:866` renders
unknown `{{X}}` as EMPTY, while `implement-dispatch.sh:109-114` hard-errors.

**Piece 1 — the renderer fails closed (production change).**
`review-dispatch.sh:866` substitutes unknown `{{X}}` with `""` — a
binding a mode block forgot renders as a silent blank, and no
downstream assertion can tell "empty by design" from "erased". Bring it
to parity with the implement renderer (`implement-dispatch.sh:109-114`,
which lists the unresolved names and exits 1). Both existing dispatch
suites already capture rendered prompts through their `daemon-spawn`
stubs (`test-review-dispatch.sh:78`, `test-review-dispatch-claim.sh:54`)
— those suites gain assertions that the CRITICAL bindings render
non-empty at the real call sites (`BIND_READY_FILE`, `SKILL_FILE`,
`IMPLEMENT_PROTOCOL_FILE`, `BOARD_SCRIPTS`, plus `TICKET_BODY_FILE` on
the api side), so a call site that stops supplying one now dies loudly
in the dispatcher AND fails a test. All four render call sites
(`:625`, `:776`, `:1512` ×2 modes) must be verified to supply their
full placeholder set before the hard-fail lands.

**Piece 2 — a revised static fence, no dispatcher.** The render is a
pure function of template + `P_*` env (`_render_prompt`,
`review-dispatch.sh:848-868`). New file
`tests/reviewing-prs/test-bootstrap-parity.sh`:

- Carry a minimal copy of the renderer (mode-fence regex + placeholder
  substitution), driven over the REAL template file with one fixed
  `P_*` fixture; render all four modes. **Honesty pins on the copy:**
  assert the dispatcher still points at the same template path
  (`BOOTSTRAP_TEMPLATE=`, `review-dispatch.sh:136` — the
  `test-skill-entrypoint.sh:302` idiom) and still carries the
  mode-fence regex and the `{{(\w+)}}` substitution literally.
- **Load-bearing sentences pinned in EVERY mode's render** — the relay
  drill's idiom (`test-transcript-diff.sh:252-268`) applied here: the
  skill-pin sentence ("dispatcher-pinned copy", the "over any
  same-named skill" precedence clause), the read-it-live rule (each of
  the four separately-authored rewordings pinned t/nt in both
  directions, so two-authors drift stays visible instead of silent —
  this is where the drift lives, and a shared-tail diff cannot see it),
  and the worktree-bootstrap caveat.
- **Roster relation:** the gh render's `- \`NAME\`:` binding names
  minus `PR_NUMBER/PR_URL/HEAD_REF/HEAD_SHA` must be a subset of the
  api render's; the api render adds exactly `TICKET_BODY_FILE` (+
  `CLOSURE_PACKAGE`/`INTEGRATION_REF` on the scale pair). Anything else
  fails.
- **Block-boundary check:** after stripping mode-owned lines and
  binding lines, the remaining tail of the two renders in a pair must
  be identical. This is NOT an authorship fence (the tail is one source
  region — same source, same output); it pins the block BOUNDARIES: a
  shared line accidentally swallowed into one mode's fence (the
  gating-error class §8-of-#61 hit with the eligibility chip) surfaces
  here and nowhere else.
- **No cross-contamination / nothing unrendered:** no `mode:` fence
  survives any render; no `{{` survives any render (meaningful now
  that unknowns hard-fail rather than blank).
- **Implement lane, same file, small section:** render
  `worker-bootstrap.md` with and without the `api-only` region and
  assert everything outside the region identical, roster relation
  `+TICKET_BODY_FILE +PARENT_PIN`.

What legitimately differs (mode-block prose beyond the pinned
sentences, `BASE_REF` sentinel vs branch, `TECH_DEBT_ISSUE=none`) is
either inside stripped blocks or an explicitly pinned difference — the
fence pins nothing that is supposed to vary.

---

## §6 drill cosmetics

All in the suite's own idioms (verified inventory; the two literal
numerics plus ~16 interpolated-id substrings, `helpers.sh:9-21` `t`/`nt`
being unanchored `grep -qF`):

1. `test-transcript-diff.sh:151` — `t "…registered a ticket" "1" …` is
   satisfied by any id containing `1`; replace with a non-empty check +
   exact-line assertion in the file's own style (`[ -n … ]` as at
   `:236`).
2. `test-transcript-diff.sh:214` — anchor `"4242"` into the refusal
   phrase actually printed (`"#4242"` + trailing token), the way `:215`
   already asserts a full phrase.
3. **Delimit the emitters once, fix four drills:** `row()`
   (`test-human-verbs.sh:64-65`) already brackets its list fields —
   extend the same delimiter to its scalar fields and to `owner_line()`
   (`test-protocol-walk.sh:73`), then anchor the consuming assertions
   (`owner=$RUN` → closed form) across `test-protocol-walk.sh:74,96`,
   `test-crash-boundaries.sh:122,135,154`, `test-resume-first.sh:103`,
   `test-human-verbs.sh:162`.
4. JSON-body ids: close with the next JSON token —
   `"\"ticketId\":$T1,"` shape — at `test-protocol-walk.sh:97`,
   `test-crash-boundaries.sh:76,86`, `test-escalation.sh:107`; regex
   form `\"ticketId\":$T_TID[,}]` for the real `grep -q` at
   `test-escalation.sh:76`.
5. `test-resume-first.sh:95-96` — the `nt` on `BOARD_RUN_ID=$RUN` fails
   for the WRONG reason if a longer id contains `$RUN`; close both with
   the line's trailing delimiter.
6. **Argv comparator:** record the walk's argv UNSUBSTITUTED (`%T`
   kept) alongside the executed argv in `test-transcript-diff.sh:100-115`,
   and compare the unsubstituted form in `transcript-compare.py:103` —
   the per-side ticket id never enters the compared surface, while the
   deliberate literal `4242` (step 6) stays literal. No blanket
   `\d+ → <N>` normalizer: it would erase the known-ticket /
   unknown-ticket distinction the step-6 probe tests.

Each anchoring change must be shown to still PASS (they are
tightenings, not behavior changes) and at least one representative per
class shown to catch its wrong-reason pass (mutate the emitter/id in a
scratch copy — discrimination probe, not a committed test).

---

## Acceptance

- `printf` a body that quotes a `<!-- board:meta` example in prose and
  carries a real trailing block; run any gh-mode meta write
  (`update_meta` via a stubbed verb); the body's prose survives
  byte-for-byte and `parse_meta` reads the real block. dp#60 closed with
  a comment naming the helper.
- A gh-mode qagent park with no `pre-park:` answered via
  `board-answer.sh` lands the ticket at `in-review` without the caller
  passing `--pr`; with no `pr:` meta it lands at `in-progress` with a
  warning.
- A `claim-successor` fixture that always 500s escalates an env-issue on
  the third tick; a `claimed:false` fixture never does; one ticket never
  produces two claim POSTs in one tick.
- A suppression whose ticket is missing from the `/tickets` read
  survives the tick. An arkho issue exists pinning
  `/queue/decisions` + `/tickets` as unbounded-until-enveloped.
- `tests/reviewing-prs/test-bootstrap-parity.sh` passes, and a scratch
  one-word edit to the shared tail of ONE mode pair makes it fail.
- The full suites: `tests/claude-code/run-skill-tests.sh` board-api
  section, `tests/issue-tracker/test-board-scripts.sh`,
  `tests/reviewing-prs/*`, `scripts/lint-shell.sh` — green.

## Deferred

- The wrong-pre-park case for a qagent that bounced through
  `ready-for-architect` before parking (§2) — PRE_PARK vocabulary
  question, recorded on dp#51.
- Cursor-follow / paged reads — blocked on arkho growing an envelope;
  the filed issue is the contract seam.
- gh-scale DEFAULT_BRANCH ladder (pre-existing, gh has the
  authoritative `gh repo view` rung).

## Decision Log

- **§1 helper over regex surgery** — an anchored-rightmost regex (e.g.
  tempered dot) was rejected: the walk is 6 lines, proven in
  production (`board-body.sh`), and readable; a cleverer regex is a new
  thing to get wrong.
- **§2 re-supply `--pr` from meta, not gate relaxation** — relaxing
  `board-transition.sh:238` to trust a role stamp weakens an invariant
  every other caller relies on; the ticket's own `pr:` meta is the
  recorded fact the gate wants. Fail-open (old `in-progress` fallback +
  warning) when `pr:` is absent, because the answer path must never
  hard-die on bookkeeping.
- **§2 stamp role only, not lane** — gh mode has no claim lanes; `lane`
  is what the api cap counts (`review-dispatch.sh:1558-1573`). Mirroring
  `implement-dispatch.sh`'s gh-side role-only write keeps the four
  dispatcher×binding meta subsets explicable.
- **§3 count claim ERRORS, not `claimed:false`** — backpressure is a
  healthy wait; suppression removes a ticket from two phases until a
  human acts, which is worse than the churn it would cure. Rejected:
  counting both with a higher threshold (two thresholds to explain, and
  lane-cap waits can legitimately outlast any threshold).
- **§3 dedupe at the tick, not reset-on-grant** — the double-charge
  comes from replay+feed overlap, so the fix is one-attempt-per-tick;
  reset-on-grant was rejected as it would erase real fault counts when
  faults alternate with grants.
- **§4 no cursor-follow, no length-sentinel** — no cursor exists to
  follow; a sentinel on an unbounded route false-positives on a
  legal 500-row board. The contract pin (arkho issue) + the one
  destructive-consumer guard are the whole defensible surface.
- **§5 copied renderer with honesty pins over sourcing the dispatcher**
  — `review-dispatch.sh` cannot be sourced (set -e, cd, git-repo
  requirement, tail dispatch); the copy is 20 lines and the pins
  (template path + regex literals asserted against the dispatcher
  source) keep it from drifting.
- **§6 unsubstituted argv over targeted normalizer** — recording `%T`
  keeps the judge (`transcript-compare.py`) blind to per-side ids
  without teaching it which ids are "known"; the normalizer alternative
  put walk knowledge inside the judge.
- **§1 enforce the value grammar rather than harden the reader
  further** (v1.1) — the reviewer's forged-marker reproduction showed
  rightmost matching alone still loses to a marker INSIDE the block;
  encoding schemes (escaping markers) were rejected because
  `parse_meta` line-wise reading makes multi-line values corrupt
  already — normalize CR/LF, die on marker tokens, and the block is
  clean by construction. (Both clauses superseded: v1.2 widened the
  normalization to every splitlines() separator; v1.2.1 narrowed the
  die to the opening marker only — see §1.)
- **§2 name-inference rung over required-stamp-before-barrier**
  (v1.1) — making the stamp a hard gate before the startup barrier
  turns a bookkeeping write into a spawn blocker (against the
  non-fatal precedent at `implement-dispatch.sh:848`); the
  deterministic `review-pr-*`/`review-epic-*` name is already in the
  registry record and covers legacy AND failed-stamp cases with zero
  new failure modes. A locked migration was rejected as touching every
  registry file for a fallback path.
- **§3 typed 409s drop the journal instead of charging** (v1.1) —
  `nonce-consumed` and `stale-resume` mean the JOURNAL is obsolete,
  not the substrate sick; counting them would escalate and suppress
  valid work, and closing the env-issue would replay the same doomed
  nonce forever (reviewer finding, both codes verified in arkho
  source).
- **§5 hard-fail renderer + sentence pins over shared-tail-diff-only**
  (v1.1) — the tail diff is tautological for authorship drift (one
  source region) and the blank-on-unknown renderer made "no `{{`"
  vacuous; the revised fence pins the four separately-authored
  rewordings directly and makes unknown placeholders a dispatcher
  error, which also upgrades the existing suites' captured-prompt
  assertions from shape to content.

## Surprises & Discoveries

- The deferral text for §4 named the wrong endpoints — `_sweep_api.sh`
  never reads `/queue/*`; the real capped feeds were already handled
  (one drained, one level-triggered), and the real risk is the
  UNCAPPED routes' bare-array shape plus one destructive consumer.
- `parse_meta` shares dp#60's leftmost flaw (not just `strip_meta`) —
  wrong meta READS, not only wrong writes.
- gh-mode `review-dispatch.sh` writes no role at all — the deferral
  assumed a fallback bug, but the meta the fallback reads was never
  written on the review lane.
- `board-transition.sh`'s `--pr` gate makes the naive §2 fix a hard
  failure — the three-part fix shape came from that discovery.
- The claim-failure exits of `_resume_one` are completely untested —
  no `claim-successor` fixture in the repo returns `claimed:false` or a
  non-200.

## Outcomes & Retrospective

Pending — written at finish.

## Revision Notes

- v1.0 (2026-08-12): initial spec from four parallel code
  investigations (qagent role, escalation counter, pagination reality,
  fence/drill inventory).
- v1.2.3 (2026-08-13, final-panel flow-back): §1's rightmost rule is
  refined to a content-based candidate walk. Two panel findings, both
  confirmed: (1) a LEGACY body whose pre-grammar client stored a marker
  inside a meta value (shape B) made the rightmost walk pick the nested
  opener — parse forged keys, and strip_meta left the outer block's
  head behind as prose, a regression against the old leftmost strip
  boundary; (2) the per-marker end-anchored rescan was O(N²) (1.77s at
  4000 markers; snapshot() runs parse_meta per issue). One rewrite
  fixes both: candidates are line-start openers from the leftmost
  match onward; walking left to right, a candidate is the real opener
  iff every line between it and the next candidate is a known-key
  `key: value` line (blank or prose lines disqualify — a real block
  interior contains only its own entries); two regex scans total. On a
  poisoned legacy body the guarantee is the STRIP boundary and rewrite
  round-trip stability — the forged key inside the block's own lines
  is that body's actual content and is not recoverable.
- v1.2.2 (2026-08-13, Task 9 review flow-back): §5 Piece 2's roster
  parenthetical was wrong — `CLOSURE_PACKAGE`/`INTEGRATION_REF` are
  carried by BOTH members of the scale pair (they are scale-mode
  bindings, not api additions); the api side adds exactly
  `TICKET_BODY_FILE` on both pairs. The landed fence pins the stronger
  truth; this note corrects the spec to match.
- v1.2.1 (2026-08-13, Task 1 review flow-back): the `-->` half of the
  value grammar is dropped — fuzz-proven harmless (8 keys × 8
  arrow-values × 4 prose shapes, zero mismatches: the collapsed value
  always sits behind `key: `, never at line start), and rejecting it
  bricked pre-fix arrow-bearing notes on every `update_meta`
  read-modify-write AND was the only realistic trigger of a torn write
  (`apply_state` moves the label before the meta write dies). The
  `<!-- board:meta` check stays and must run before any external write.
- v1.2 (2026-08-12): codex plan review (3 findings, all adopted): §1
  value normalization covers every `splitlines()` separator, not
  CR/LF alone (U+2028-class injection); §3 phase order becomes
  lift → reconcile → feed (old order + suppression-aware reconcile
  strands journals across a mid-tick lift); the §2 `--pr` handoff
  crosses the python→shell boundary as an explicit sixth field (plan
  detail, recorded here because the spec's "single conditional argv
  append" implied shell scope it did not have).
- v1.1 (2026-08-12): codex adversarial review (gpt-5.6-sol xhigh),
  four findings, all adopted after verification: §1 gains the value
  grammar (forged-marker reproduction confirmed — rightmost matching
  alone is insufficient); §3 types the claim errors
  (`nonce-consumed`/`stale-resume` drop the journal uncharged, both
  verified in arkho claims.js; only ambiguous faults count); §2 gains
  the legacy name-inference rung (registry `"name"` field verified
  live); §5 redesigned — the review renderer fails closed on unknown
  placeholders, the existing suites assert critical bindings
  non-empty, and the static fence pins per-mode load-bearing sentences
  instead of relying on the (tautological) shared-tail diff, which is
  retained only as a block-boundary check.
