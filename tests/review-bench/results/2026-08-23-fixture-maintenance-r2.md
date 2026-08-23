# Fixture maintenance round 2, after the C2 campaign

The second maintenance pass over the seeded fixtures (doperpowers#40). It
clears the candidates the C2 runs surfaced but did not score, so the next
scored run cannot produce a finding that is neither truth-matched nor a
deliberate bait.

Source of record: the `new_unseeded_candidates_excluded` array in
`results/2026-07-26-c2-scores.json`, read against the per-case findings in
`results/2026-07-26-c2-codex-r3/` (codex `gpt-5.6-sol` at xhigh, production
`review-engine.sh` path) and `results/2026-07-26-c2-high-r2/` (argus-review
v0.4.1 at level high, headless path) and their `notes.md`.

Rules applied are the ones the #36 round set, in
`results/2026-07-26-fixture-maintenance.md`: a defect that exists in `base/`
only is out of review scope and is fixed, never promoted; a patch-introduced
defect is fixed when the fix is local and cannot disturb a seeded bug, and
promoted to a `caseN-u*` truth entry when fixing would touch a line a seeded
bug lives in or depends on. **No seeded bug (`caseN-b*`), no promoted entry
(`case4-u1`, `case4-u2`, `case5-u1`) and no `truth.json` was changed** — every
seeded bug of an edited case was re-triggered after the edits (evidence below).

All six candidates this round are patch-side: none of the defect sites exists
in `base/`, so no `base/` tree was touched. Each edit was made on the
materialized post-patch tree and `patch.diff` was regenerated from it.

## Per-item decisions

| # | Item (as adjudicated) | Decision | Edit made |
|---|---|---|---|
| 1 | case4: source-dir symlink probe — cross-engine convergent (codex r3, plain r2, high r2 [P1]) | **fix** | `snapshot.sh`: the emptiness probe is now `find "$BACKUP_SOURCE_DIR/" -mindepth 1 -print -quit` and the sizing is `du -sk "$BACKUP_SOURCE_DIR/"`, both with the trailing slash. Without it `find` does not descend a symlinked start point, so a `BACKUP_SOURCE_DIR` that is a symlink to the volume actually holding the data probed as empty and exited 3 ("nothing to archive") on every run, while `du` sized the link rather than the tree. The probe's comment block gained a sentence naming the slash and pointing at the same shape already documented in `prune.sh`'s `list_archives`. `[ -d "$BACKUP_SOURCE_DIR" ]` and the `check_free_space` call were left alone — `case4-b1` territory. |
| 2 | case4: staging-filesystem free-space gap (high r2 [P2] PLAUSIBLE) | **fix** | `snapshot.sh`: a second `check_free_space "${TMPDIR:-/tmp}" "$need_kb" "$FORCE"` immediately after the existing archive-directory call, with a comment saying why (tar writes the whole archive into staging and it only moves to the archive directory after replication, and staging is routinely a different, smaller filesystem). `check_free_space` itself was **not** modified — `case4-b1` lives inside it and `[ "$force" ]` must stay — and neither were `make_stage`, `STAGE="$(make_stage)"` or `rmdir "$STAGE"`, which are `case4-b2` territory. |
| 3 | case4: `find -type f` drops symlinked archive files (plain r2 [P3], high r2 [P3]) | **fix** | `prune.sh` `list_archives`: the find is now `find "$dir/" -maxdepth 1 \( -type f -o -type l \) -name '*.tar.gz' -print0`. The glob this find replaced matched a symlinked `.tar.gz` (its `[ -f "$file" ]` test dereferences; `find -type f` does not), so symlinked archives were never counted toward `BACKUP_KEEP` and never rotated. The function's comment went from "Two details" to "Three details" and the new one explains the parity, including that rotation's `rm -f` removes the link and leaves its target alone. Nothing else in `prune.sh` changed — the three-field manifest reader is `case4-b4`. case4's `case.md` bait (2), which quotes this find verbatim, was updated to the new command; its claim (same set, same newest-first ordering as the glob) is what the fix restores. |
| 4 | case3: explicit-null `expected_revision` skips validation (codex r3 [P2]) | **fix** | `app.py` `handle_put_document`: the guard is now keyed on presence, `if "expected_revision" in body and (expected is None or isinstance(expected, bool) or not isinstance(expected, int))`. `body.get(...)` made present-but-null indistinguishable from absent, so `{"expected_revision": null}` silently became an unconditional write — the one thing the conditional-write contract exists to prevent. The docstring gained a sentence: omitting the field is what asks for an unconditional write, and an explicit `null` is rejected rather than treated as absent. The `store.save_document(...)` call and the `return Response(200, …)` line were not touched — `case3-b2` quotes them and must keep returning the row count bound to `revision`. |
| 5 | case1: null/non-dict config entry crashes `load_tenant_limits` (high r2 [P3] PLAUSIBLE) | **fix** | `tenants.py`: after the default-tenant fallback, `if not isinstance(entry, dict): entry = {}`, with a comment tying it back to the docstring's contract — a missing config is an empty entry is no limits, and a malformed one is not allowed to be the exception that aborts the whole ingest instead. A `"default": null` line (or an entry written as a bare scalar) survived both `.get`s as a non-mapping and raised `AttributeError` on `entry.get("max_value")`. The function stays cache-free and is still called once per reading, which is the mechanism `case1-b3` measures at the `pipeline.py` call site. |
| 6 | case1: explicit-null tenant stringified to `"None"` (high r2 [P3] PLAUSIBLE) | **fix** | `records.py`: `raw_tenant = payload.get("tenant", DEFAULT_TENANT)` followed by `tenant=DEFAULT_TENANT if raw_tenant is None else str(raw_tenant)`, plus a comment. `{"tenant": null}` produced the phantom tenant `"None"` — a partition that exists in no config and matches nothing the README documents — where the README says a reading with no tenant belongs to the `default` tenant. Non-null non-strings are still stringified, as before. `parse_line`'s NaN/Infinity guard is #36's fix and was left as it stands. |

## The u2 adjudication (documentation only — no code or truth change)

`2026-07-26-c2-scores.json` carries the note "u2 (remote umask) actively
refuted by an argus verifier while codex finds it — carry to next fixture
pass", and `2026-07-26-c2-high-r2/notes.md` scores case4 as
`u1 ✓ [P2], u2 ✗ (refuted)`. **That score line is a mapping error.** The
run's own transcript, `2026-07-26-c2-high-r2/case4.argus.txt`, opens with:

> All 5 verifiers returned complete verdicts. Synthesis: 8 findings survive
> (5 confirmed, 3 plausible); 3 candidates were refuted (the `du -sk`
> traversal cost, the `BACKUP_REMOTE` leading-dash injection, and the
> `umask` relocation).

The refuted candidate is *the `umask` relocation* — the local hoist of
`umask 077` from `snapshot.sh` into `lib/common.sh` — not `case4-u2`, which is
about the copy the **replica** creates under its own account's default umask.
No local umask governs that copy, so the refutation of the one says nothing
about the other. codex r3 reports u2 independently and in its own terms
(`case4.codex.txt`: "On replicas whose noninteractive SSH shell uses the
common `022` umask … this redirection creates a `0644` archive, exposing
potentially sensitive backup contents to other remote users despite the local
`077` policy"). **`case4-u2` remains truth and was not touched.**

The refuted candidate itself is now written down as a known non-defect, so a
future run that raises it is scored as the false positive it is. It went into
case4's `case.md` as an extension of bait (3) rather than a sixth numbered
bait, because it is the same code change bait (3) already covers — the sharper
form of it. In full: the hoist makes the umask apply at library *source* time,
so `mkdir -p "$BACKUP_ARCHIVE_DIR"` now creates the archive directory 0700
where the base created it 0755. That is not a defect. In the base, archive
*files* were already written 0600 under the very same `umask 077`, which was
set before `mktemp -d` and tar and survives the publishing `mv` (which
preserves the mode), so no other account could ever read an archive's
contents. The only capability the hoist removes is listing and stat-ing the
names of files that were already unreadable, and no consumer of that
capability exists anywhere in the toolchain. The comment above the umask
states the move is deliberate.

## Effect on the scoring denominator

**Unchanged.** No entry was promoted this round and none was removed:
`truth.json` still holds **20** entries — 17 seeded (`caseN-b*`) plus the 3
promoted in #36 (`case4-u1`, `case4-u2`, `case5-u1`) — distributed case1 3,
case2 3, case3 3, case4 6, case5 5. All 17 seeded bugs are byte-identical in
behavior, so C2's scores stay directly comparable to a run scored after this
pass.

## Verification

Patch application, run per case in a fresh scratch repo through the harness
path (`cp -R base/.`, `git init -b main`, commit, `checkout -b bench-change`,
`git apply patch.diff`, commit):

    case1: apply OK    case2: apply OK    case3: apply OK
    case4: apply OK    case5: apply OK

Every patch also round-trips: regenerating it with `git diff main
bench-change` from the applied tree reproduces the stored `patch.diff`
byte-for-byte (`cmp` clean), so no hunk drift was introduced. case2 and case5
were not edited and were verified unchanged. The same round-trip was run
against the *pre-edit* fixtures first, to establish that the regeneration
procedure is byte-faithful before any edit relied on it.

### Seeded bugs re-triggered after the edits

Every drill below ran against the tree materialized from the fixture's **new**
`patch.diff`.

**case1**

- **b1** — `summarize_file` over `[ts=100, ts=90]` for one tenant at
  `allowed_lateness=30`: `dropped_late=1`, and the surviving window is
  `[(60, 1)]` — the ts=90 reading, 10 s behind the watermark and inside the
  grace period, is still discarded.
- **b2** — `summarize_files(["a.ndjson", "b.ndjson"], 60)` with one reading at
  ts=10 and one at ts=70: batch 1 emits 1 row (`starts=[0]`), batch 2 emits 2
  (`starts=[0, 60]`) — the `[0,60)` window is re-emitted.
- **b3** — a 50-reading file opens `tenants.json` 50 times (counted by
  wrapping `builtins.open`): `readings=50 tenants.json opens=50`.

**case3**

- **b1** — `GET /exports/all` with `tok-ines` (a globex member) returns
  **200** and the body carries acme's documents and their rendered contents
  (`{'exports': [{'tenant': 'acme', 'name': 'alpha', 'revision': 1, 'content':
  'n\nalpha\n'}, …]`).
- **b2** — a document at revision 1, `PUT` of 3 rows: the reply is
  `{'name': 'alpha', 'revision': 3, 'etag': 'W/"3"'}` while the store moves
  1 → 2.
- **b3** — `limit=2` pagination returns `['alpha', 'beta', 'delta']` then
  `['delta', 'epsilon', 'gamma']`.

**case4**

- All four scripts parse: `bash -n` OK on `lib/common.sh`, `snapshot.sh`,
  `prune.sh`, `run-backup.sh`.
- **b1** — a real `snapshot.sh` run with `BACKUP_FORCE` unset (force off) onto
  a short filesystem, simulated with a `df` stub earlier on `PATH` reporting
  1 KB available, logs
  `only 1KB free in …/arch, wanted 196KB -- continuing anyway` and exits **0**.
  The guard is still unreachable. (The staging check added as item 2 logs the
  same line for `$TMPDIR` on that run, which is the fix working, not a second
  bug.) `lib/common.sh:81` is still `if [ "$force" ]; then`.
- **b2** — no `trap` occurs anywhere in `snapshot.sh` (`grep -n trap` returns
  nothing).
- **b3** — `lib/common.sh` was not edited at all this round:
  `git diff --stat` across the maintenance commit lists only `prune.sh` and
  `snapshot.sh`; a diff of `replicate()`'s body between the pre-edit and
  post-edit trees is empty; the ssh line is still
  `"mkdir -p '$BACKUP_REMOTE_DIR' && cat > '$BACKUP_REMOTE_DIR/$name'"`; and
  the stored `patch.diff` carries the identical blob pair for the file before
  and after (`index 743590c..caa7ec3 100644`). `case4-u1` and `case4-u2`,
  which live in the same body, are untouched for the same reason.
- **b4** — an end-to-end `./run-backup.sh --label nightly` in a sandbox
  directory with three archives already present logs
  `manifest points at a missing archive, skipping: 200661<TAB>…/nightly-….tar.gz`
  and rotates nothing (4 archives on disk afterwards, `BACKUP_KEEP=1`).

### Fixes verified behaviorally, and against the pre-edit tree

Each fix was run on both the post-edit and the pre-edit tree, so the drill is
known to discriminate rather than merely to pass.

| Fix | Post-edit | Pre-edit (discrimination) |
|---|---|---|
| 1 — symlinked source dir | `BACKUP_SOURCE_DIR` a symlink: exit **0**, manifest record written, `wrote …/nightly-….tar.gz (120629 bytes)`. `du -sk` on the link reads **0 KB** without the slash and **120 KB** with it. | exit **3**, `source tree is empty, nothing to archive` — the host silently stops backing up. |
| 2 — staging free-space check | `grep -n check_free_space snapshot.sh` → 2 calls (line 82 archive dir, line 88 `${TMPDIR:-/tmp}`); with the `df` stub both fire, the `$TMPDIR` one naming the real temp filesystem. Constructing a genuinely full filesystem was skipped on macOS in favour of the stub, as the brief allows. | 1 call. |
| 3 — symlinked archive file | `list_archives` returns **4** paths including the symlinked `nightly-20190101T000000Z.tar.gz`; a `prune.sh` run at `BACKUP_KEEP=2` logs `kept up to 2 of 4 archives` and prunes the symlink among them, leaving its off-volume target `old.tar.gz` in place. | `list_archives` returns 3; `kept up to 2 of 3 archives`; the symlink survives rotation forever. |
| 4 — explicit-null `expected_revision` | `PUT` with `{"expected_revision": null, "rows": […]}` → **400** `expected_revision must be an integer`. Absent field still **200**, matching int still **200**, `"2"` as a string still **400**, stale int still **409**. | (present-but-null took the unconditional-write path.) |
| 5 — null/non-dict config entry | `{"default": null, "acme": 17}` loads without raising: `default`, `acme` and an unknown tenant all come back `max_value=None`. | `AttributeError: 'NoneType' object has no attribute 'get'`, aborting the ingest. |
| 6 — explicit-null tenant | `{"tenant": null}` parses to `tenant='default'`, the same as a line that omits the key; a non-string `7` is still stringified to `'7'`; the reading lands in the `default` tenant's window in the report. | `tenant='None'`. |

## Not handled

Nothing from `new_unseeded_candidates_excluded` was left unaddressed; all six
were fixable without touching a seeded bug's lines, so nothing was promoted
and the denominator did not move.

Two carry-forwards for the next adjudicator:

- The #36 doc's own carry-forward still stands: `case4-u1`, `case4-u2` and
  `case5-u1` were promoted purely because their fixes intersect seeded-bug
  lines. They remain small fixes available to any run-id willing to
  re-baseline, at the cost of changing `case4-b3`'s and `case5-b2`'s quoted
  triggers.
- `epoch_of()` uses `stat -f %m` / `stat -c %Y`, which report a *symlink's*
  own mtime rather than its target's. With item 3 admitting symlinks into
  `list_archives`, a relocated archive now sorts by the age of its link. This
  was deliberately not changed: the glob that `find` replaced handed
  `epoch_of` the same symlink path and got the same answer, so the set *and*
  its ordering still match the base behavior exactly, which is what the
  function's comment claims. Teaching `epoch_of` to dereference (`stat -L`)
  would be a change *away* from that parity, not toward it — worth raising as
  its own candidate if a future run flags the ordering, but not something to
  smuggle into a maintenance pass.
