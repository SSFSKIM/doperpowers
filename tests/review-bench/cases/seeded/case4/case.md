# case4 — bash snapshot/rotate toolchain gains off-host replication

**Scenario.** A four-file shell toolchain (`lib/common.sh`, `snapshot.sh`,
`prune.sh`, `run-backup.sh`) takes tar.gz snapshots of a directory and keeps
the newest N per label. The patch adds off-host replication over ssh, a
pre-flight free-space check with a `--force` override, moves staging and the
umask into the shared library, bumps the manifest to a v2 format with a
leading label column, and makes an empty source tree exit 3 instead of
writing an empty archive. **Seeded classes: L1, L2, L3, L4.** `case4-b1`
(L1) is the free-space guard that never fires, because `check_free_space`
tests `[ "$force" ]` while every caller passes the *string* `"0"` when force
is off. `case4-b2` (L3) is the `trap 'rm -rf "$STAGE"' EXIT INT TERM` that
was dropped when staging moved into `make_stage()`, leaving only a
success-path `rmdir` — so every failed or interrupted run now leaks a
full-size archive into `$TMPDIR`. `case4-b3` (L4) is command injection into
the replica: `replicate()` interpolates the label-derived archive name into
a string that ssh hands to a remote shell, and the single quotes around it
can be closed by the value itself. `case4-b4` (L2) is the cross-script
contract break: snapshot.sh, run-backup.sh and the README all moved to
manifest v2, but prune.sh still reads three tab-separated fields, so every
record fails its `[ -f "$path" ]` test and rotation silently stops.

**Baits (correct, do not report).** (1) `snapshot.sh` now exits **3** on an
empty source tree — this looks like broken exit-code handling, but it is
documented in the header comment and in intent.md, and `run-backup.sh`
explicitly consumes 3 as a success-with-no-work case. (2) `prune.sh`
replaces the `"$dir/$label"-*.tar.gz` glob with `find -maxdepth 1 -type f
-name '*.tar.gz' -print0` plus a literal `case` filter on the label; it looks
like a recursion/ordering change but the set and the newest-first ordering are
identical, and the motivation (ARG_MAX on directories with tens of thousands of
archives) is in the comment. (3)
`umask 077` moves from `snapshot.sh` into `lib/common.sh`, so it now also
applies to prune.sh and run-backup.sh — a real behavior change, intentional
and explained in the comment and intent.md. (4) The free-space check
deliberately compares against the *uncompressed* `du -sk` size of the source
rather than an estimated compressed size; that over-reserves on purpose and
says so in the comment. (5) `replicate` runs *before* `mv "$staged" "$archive"`,
so an unreachable replica aborts the run and no local archive is published that
night — which reads like an optional replica becoming a hard dependency, but it
is the explicit trade in intent.md and in the comment above the block (a local
archive that prune.sh can rotate against, with no replica behind it, is the
state the change exists to prevent). The seeded `case4-b2` depends on this
ordering; do not "fix" it.

**Promoted unseeded defects (real, count for recall).** `case4-u1` (L1) is
`replicate()`'s comment promising that `cat` cannot leave a partial file under
the archive's final name while the remote command redirects straight into that
name. `case4-u2` (L4) is the replica copy being created under the *replica's*
umask, so an archive that is 0600 on the origin lands world-readable off-host.
Both live in the same `replicate()` body as the seeded `case4-b3` injection, so
they were promoted rather than fixed — editing that ssh command would have
disturbed b3. See `results/2026-07-26-fixture-maintenance.md`.
