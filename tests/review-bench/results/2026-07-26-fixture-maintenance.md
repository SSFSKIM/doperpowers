# Fixture maintenance after baseline-r1 / argus-high

Cleans the seeded fixtures so the next scored run cannot produce a finding that
is neither truth-matched nor a deliberate bait. Source of record: the
`genuine_unseeded_excluded` array in `results/2026-07-26-baseline-r1/scores.json`
and the per-case adjudication in the same directory's `notes.md`.

Rules applied: a defect that exists in `base/` only is out of review scope
(rubric criterion 4) and is fixed, never promoted; a patch-introduced defect is
fixed when the fix is local and cannot disturb a seeded bug, and promoted to a
`caseN-u*` truth entry when fixing would touch a line a seeded bug lives in or
depends on. **No seeded bug (`caseN-b*`) or its truth entry was changed** —
each one was re-triggered after the edits (evidence below).

## Per-item decisions

| # | Item (as adjudicated) | Decision | Edit made |
|---|---|---|---|
| 1 | case1: NaN/Infinity pass the new "must be a JSON number" check | **fix** | `records.py`: added `import math` and a second guard, `if isinstance(value, float) and not math.isfinite(value): raise MalformedReading(...)`; extended `parse_line`'s docstring, the README Conventions bullet and `intent.md` to say *finite* JSON number. Restricted to `float` so a huge int cannot raise `OverflowError` from the new line. |
| 2 | case4: `find -name` interprets glob metacharacters in unvalidated labels | **fix** | `prune.sh` `list_archives`: `find` now matches `-name '*.tar.gz'` and the label is matched by a `case "${file##*/}" in "$label"-*.tar.gz)` filter, which keeps `$label` literal exactly as the glob it replaced did. Label validation was deliberately *not* added — that would defuse seeded `case4-b3`. |
| 3 | case4: non-atomic replica publish contradicts its own comment | **promote** | New truth entry `case4-u1` (L1). Fixing means either rewriting `replicate()`'s ssh command (the exact line `case4-b3` lives on, quoted verbatim in b3's trigger) or replacing the comment with a claim that itself becomes a new bait. Promoted instead. |
| 4 | case4: emptiness probe fails open on `find` errors | **fix** | `snapshot.sh`: `if ! first_entry="$(find … -print -quit)"; then die "could not read source tree: …"; fi`, then the empty test on `$first_entry`. An unreadable tree now exits 1 instead of exit 3 ("nothing to do"). |
| 5 | case4: replica umask not established remotely | **promote** | New truth entry `case4-u2` (L4). The only fix is prepending `umask 077 &&` to the remote command string — again the line `case4-b3` lives on and quotes. Promoted instead. |
| 6 | case4: `BACKUP_FORCE` read before `load_config` | **fix (docs)** | The defect is a documentation claim, not the code: `BACKUP_FORCE` as an *environment* variable works. Removed the `BACKUP_FORCE` row from the README's config-file key table and said in the Usage paragraph that it is read at startup, before the config file, so it is env-only. `snapshot.sh`'s `FORCE="${BACKUP_FORCE:-0}"` was left untouched — `case4-b1`'s truth entry quotes that line. |
| 7 | case5: in-flight join ignores the configured timeout | **promote** | New truth entry `case5-u1` (L1). The fix wraps `await pending.wait()` — the line `case5-b2`'s trigger is written against ("every later caller … blocks on `await pending.wait()` forever"). Promoted rather than restate a seeded trigger. |
| 8 | case5: initial retry delay uncapped when `base_delay` > cap | **fix** | `jobqueue._run_job`: `delay = min(self._base_delay, MAX_BACKOFF_SECONDS)` with a comment saying the ceiling applies to the first delay too. |
| 9 | case5: first warm-up pass gated (warm-up throttle seed) | **fix** | `jobqueue`: `self._last_warm: Optional[float] = None` instead of `0.0`, and the throttle reads `if self._last_warm is not None and now - self._last_warm < WARM_INTERVAL_SECONDS`. `time.monotonic()`'s zero point is uptime, so `0.0` throttled the first ever pass on a freshly booted host. Side benefit: `case5-b4`'s trigger (`warm_stale_keys()` reaching the hit-rate gate) is now reached unconditionally. |

## Bait tightening (not truth changes)

| Target | Edit |
|---|---|
| case3 — recurring TOCTOU false positive on the conditional write | An explicit single-threaded statement in three places a reviewer will hit: a new **`## Concurrency`** section in `base/README.md` ("no server, no thread pool, no `asyncio` loop, no `fork`; every read-then-write in `store.py` runs with no other writer in existence, and none of them takes a lock — deliberately"), a paragraph in `base/store.py`'s **module docstring** (the file both engines flagged), and, inside the diff itself, a sentence in the patched README's conditional-write paragraph plus one in `save_document`'s docstring. The claim is now refutable from the fixture instead of resting on an unstated deployment assumption. |
| case5 — bounded-retention bait | The bound is now stated in full where the buffer is written: `_record_result`'s comment gives the number (512 entries, oldest evicted first) *and* what one entry holds (one outcome — a value, or the exception it raised), and the README's Results section says the same. The argus-high flag was that only the entry count was stated while the bytes were not; the count bound and its per-entry content are now both explicit. |
| case4 — replication-before-publish (argus-high [P2], not in the excluded array) | Documented as bait (5) in `case.md`. It is already stated as the deliberate trade in `intent.md` and in the comment above the block, and `case4-b2`'s truth summary *depends* on this ordering ("it now holds a full-size finished archive, because replication happens before the archive is published"), so the code must not change. |

## Also fixed (real, patch-introduced, surfaced by argus-high but absent from the excluded array)

- **case4: `find` does not follow a symlinked archive directory** (`prune.sh:32`).
  The base glob `"$dir/$label"-*.tar.gz` expanded through a symlinked
  `BACKUP_ARCHIVE_DIR`; `find "$dir" -maxdepth 1 -type f` does not, so rotation
  silently listed nothing. Fixed in the same `list_archives` edit by using
  `find "$dir/"` (trailing slash), verified on macOS and explained in the
  comment.

## Effect on the scoring denominator

Seeded bug count is unchanged at **17** (`caseN-b*`). Three promoted entries
were added — `case4-u1`, `case4-u2`, `case5-u1` — so `truth.json` now holds
**20** entries: case1 3, case2 3, case3 3, case4 6, case5 5. A run scored after
this maintenance should report recall against 20 and, when comparing to the
r1/argus-high baselines, also against the 17 seeded ids, which are byte-identical
in behavior.

## Verification

Patch application (the harness path: copy `base/`, `git init`, commit as `main`,
`git apply patch.diff` on `bench-change`), run per case in a fresh scratch repo:

    case1: apply OK    case2: apply OK    case3: apply OK
    case4: apply OK    case5: apply OK

Every patch also round-trips: regenerating it with `git diff main bench-change`
from the applied tree reproduces the stored `patch.diff` byte-for-byte, so no
hunk drift was introduced. case2 was not edited and was verified unchanged.

Seeded bugs re-triggered after the edits, in the materialized post-patch tree:

- **case1** — b1 `dropped_late=1` for the ts=100/ts=90 pair at
  `allowed_lateness=30`; b2 batch 2 emits 2 rows where batch 1 emitted 1
  (the `[0,60)` window re-emitted); b3 `tenants.json` opened 50 times for 50
  readings.
- **case3** — b1 `GET /exports/all` with `tok-ines` (globex member) returns 200
  containing acme's documents; b2 `PUT` of 3 rows replies
  `{'revision': 3, 'etag': 'W/"3"'}` while the store holds revision 2; b3
  `limit=2` yields `[alpha, beta, delta]` then `[delta, epsilon, gamma]`.
- **case4** — all four scripts parse (`bash -n`); b1 `[ "$force" ]` and the
  `FORCE="${BACKUP_FORCE:-0}"` caller unchanged; b2 no `trap` on `$STAGE`;
  b3 `replicate()`'s ssh command byte-identical; b4 an end-to-end
  `run-backup.sh` run logs "manifest points at a missing archive" and rotates
  nothing.
- **case5** — b1 a key read 3 times returns the stale `v1` after a long idle;
  b2 the second caller after a raising factory still hangs (probe timed out at
  0.5 s by design); b4 `cache_hit_rate()` is 1.0 and `warm_stale_keys()`
  refreshes 0 keys with `cache.warm_throttled == 0`.

Fixes re-verified behaviorally: case1 rejects `NaN`/`Infinity`/`"12.5"`/`true`
and accepts `12.5` and `7`; case4 `list_archives` matches the label literally
(a label of `n*` returns only the `n*-…` archive) and lists through a symlinked
directory; case4 `snapshot.sh` exits 3 on an empty tree, 1 with "could not read
source tree" on an unreadable one, and 0 on a normal run; case5 retry sleeps
with `base_delay=60` stay under `MAX_BACKOFF_SECONDS`; case5's first
`warm_stale_keys()` pass is not throttled.

## Not handled

Nothing from the excluded array was left unaddressed. One judgment call worth
flagging for the next adjudicator: items 3, 5 and 7 were promoted rather than
fixed purely because their fixes intersect seeded-bug lines. If a future
run-id is willing to re-baseline, they are all small fixes and could be applied
then, at the cost of changing `case4-b3`'s and `case5-b2`'s quoted triggers.
