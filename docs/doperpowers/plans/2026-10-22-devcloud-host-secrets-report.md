# devcloud host secrets: withdrawn secret files and the sminos daemon's output (board tickets 89 and 91)

Branch `devcloud-host-secrets`, rebased onto main's `55083c19`. Final head `ce51870d`; devcloud
0.9.4. PR: #350. Built by a plan-executor run on astra, at the person's instruction to keep
subagents off the Claude weekly limits. The coordinating session wrote this file from the run's
final report, because the astra role does not write report files.

## #89: a withdrawn secret's file leaves the host

Boot step 7 (`devcloud/boot/devcloudlib/secrets.py`) keeps a root-owned record of the files it
actually wrote, beside the status file (`/var/lib/devcloud/secrets-manifest.json`). For each file it
records the `lstat` identity: device, inode, change and modification times, size, mode and owner.
The record holds no values and no hashes of values.

When an entry leaves `secrets.toml`, the next boot or reconcile:
- removes the entry's file only while that identity still matches;
- drops the entry's line from `/etc/devcloud/env`, which is rebuilt from the current declarations.

A file the person created, edited or replaced survives, even with the same content, and so does a
symlink or anything that isn't a regular file. Files written through an unchanged symlinked parent,
such as a `.config` that links into a dotfiles checkout, are cleaned up normally. A failed removal
keeps its record, so the next run retries.

A missing, unreadable or invalid record means devcloud owns nothing yet. The step's status says so,
and the secrets are still written. If the record can't be saved, the credentials are still written
and the status warns that later cleanup may be incomplete.

The lifecycle's credential ledger stays separate and unchanged. It lists paths before they are
written, so it can't show that the file now at a path is the one devcloud wrote.

**Upgrade boundary.** On a host that predates this change, a file is claimed only once devcloud
actually rewrites it. Until then a withdrawn entry's old file stays. This is deliberate: without
proof of ownership, a file could be the person's.

### The simplification before merge

The first implementation also pinned every parent directory on a file's route, through opened
directory descriptors and per-parent records. The coordinating session had it removed. Cleanup
runs as the user, not as root, so a same-user race on the route isn't a privilege boundary. The
recorded file identity already settles ownership, whatever route reaches the file. The parent
records were also what caused the review's finding on an unchanged symlinked `.config`. The removal
also took out a failure mode: an invalid record no longer blocks every secret on the host.

## #91: the sminos daemon's output is scrubbed

**Ownership: devcloud.** Step 11 already writes a drop-in for the daemon's user unit
(`devcloud/boot/devcloudlib/sminos_host.py`). The drop-in now wraps the command
`sminos daemon install` wrote in `devcloud run-scrubbed`, the way every other host service runs.

What stays sminos's:
- sminos's unit isn't copied;
- the output destination, the restart policy and `KillMode=process` are unchanged;
- standalone sminos hosts and the Macs are untouched.

The alternative, sminos never logging values, rested on discipline. It wouldn't cover a library's
or a traceback's output.

**The ticket's premise, corrected.** The daemon's unit writes to `$SMINOS_HOME/daemon.out`, not
journald. sminos's setup guide sends people there to read the daemon's errors, so the destination
was kept, and the proof checks both `daemon.out` and the unit's journal.

**Child lifetime.** With `KillMode=process`, a force-killed scrubber would have orphaned the daemon,
which would then run on unscrubbed. The scrubber arms the Linux parent-death signal (SIGKILL) in the
child, then checks the parent PID to close the race between fork and arming. The signal is cleared
on fork, so sessions the daemon starts don't inherit it and survive as before. The daemon is spawned
on the scrubber's main thread, which lives as long as the scrubber. The signal follows the forking
thread, not the process.

The spec's Decision Log (`docs/doperpowers/specs/2026-10-15-devcloud-design.md`) records:
- the ownership decision;
- the premise correction;
- the identity-only design that doesn't block on bookkeeping.

## Verification

- **#89 unit tests.** The focused secrets tests failed first on each missing behavior, then passed
  28 of 28. They cover:
  - withdrawal and the env line;
  - a user's replacement surviving;
  - symlinked parents;
  - the retry;
  - partial writes;
  - a missing or invalid record.
- **#91 daemon tests.** The focused tests pass 18 of 18.
- **The forced-stop regression, red then green.**
  - RED: `ci-gate --gates devcloud-systemd` on a test-only commit (2d9dcc11, run 39763706558). Its
    only failure was "the daemon survived timeout". Setup, enrollment and the other cases passed.
  - GREEN, with the fix: run 39764483337, then again on the final head.
  - What it exercises: timeout escalation, the wrapper's own death, the daemon lock being
    reacquired, and an independently started session surviving.
- **Scrubbing.** In the systemd gate's container, made-up values that the daemon printed on stdout
  and stderr appear only scrubbed in `daemon.out`, and not at all in the user unit's journal. No
  keep VM was needed.
- **The final head.** `ci-gate` on `ce51870d` (run 39766322160) passed 8 of 8, with 738 unit tests.

## Review

doperpowers:review-code at the medium rung, in three passes:
1. **The first implementation.** Two findings:
   - a force-killed scrubber orphaned the daemon;
   - cleanup refused a file under an unchanged symlinked parent and dropped its record.

   One astra fix wave fixed both.
2. **The re-review.** Correct, no material findings.
3. **The simplification.** A delta review (`4e1f4ae8..1dc02d65`): correct, no material findings.

The rebase onto `55083c19` carried the reviewed commits unchanged; only the Decision Log's context
moved.

## Friction

- The devcloud-host gate failed once before any host booted. The fixture's stand-ins seeded a state
  file before their state directory existed (run 39766022963). The next run passed with no change.
  Logged in friction tracker #304. The coordinating session fixed it on this branch: the stand-ins
  now seed `secrets.json` after the fakes answer, by which time they have made `/srv/fakes`.
- Rows in #304 were updated for the stale PR template and for Write/Edit losing their read state
  across background and worktree context updates.

## Residue

- A missing record shows its status note on every fresh host's first boot as well. The note only
  means something on an upgraded host. Logged as tech debt.
