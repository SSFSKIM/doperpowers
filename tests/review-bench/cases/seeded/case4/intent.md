feat(backup): replicate archives off-host, and refuse to run out of disk

Two incidents in the last month, one change:

* A file server filled its archive filesystem overnight. The snapshot ran,
  tar filled the disk, and the partial archive was left where prune.sh
  counted it as a good backup. Add a pre-flight check: work out how much the
  source tree occupies and refuse to start when the archive filesystem does
  not have at least that much free. `--force` (or `BACKUP_FORCE=1`)
  downgrades the refusal to a warning for the case where an operator knows a
  large archive is about to rotate out on the same run.

* We still have exactly one copy of every backup. Add optional replication:
  when `BACKUP_REMOTE` is set, snapshot.sh streams the finished archive to
  that host before publishing it locally. Replicating from the staging copy
  is deliberate — the archive is not visible to prune.sh until the replica
  has it, so a failed transfer aborts the run rather than rotating a good
  archive out in favour of one that only exists locally.

Supporting changes:

* Staging moves into `lib/common.sh` as `make_stage()`; both the space check
  and replication need a scratch area, and it was snapshot.sh-private.
* `umask 077` moves up into the library with it. prune.sh and run-backup.sh
  create files too (the manifest spool) and were running with whatever umask
  cron handed them.
* Manifest bumps to v2 with an explicit label column. Recovering the label
  from the archive filename breaks as soon as a label contains a `-`, and
  the label is about to matter more now that replication is per-label.
* snapshot.sh exits 3 on an empty source tree instead of writing an empty
  archive. run-backup.sh reads 3 as "nothing to do" and skips rotation; a
  host that has not produced data yet was rotating its last good archive out
  behind a week of empty ones.
* prune.sh lists archives with `find -maxdepth 1 -print0` instead of a glob.
  Two of the file servers now hold tens of thousands of archives in one
  directory and the expanded glob was overrunning the command line. Same
  set, same order.
