# snapshot toolchain

Three small scripts plus a shared library that take periodic compressed
snapshots of a directory and rotate old ones out.

    lib/common.sh    logging, config loading, small portability helpers
    snapshot.sh      makes one archive, prints one manifest record
    prune.sh         reads manifest records, rotates old archives out
    run-backup.sh    runs snapshot.sh, feeds its manifest to prune.sh

## Usage

    ./run-backup.sh --label nightly --config /etc/backup.conf

`run-backup.sh` is the only entry point cron needs. `snapshot.sh` and
`prune.sh` are usable on their own, which is why each one loads its own
config and validates its own inputs instead of trusting the caller.

## Config file

`load_config` reads `KEY=VALUE` lines and exports only keys beginning with
`BACKUP_`; anything else is logged and skipped so a typo in the config
cannot clobber `PATH`. Recognised keys:

    BACKUP_SOURCE_DIR    directory to snapshot            (required)
    BACKUP_ARCHIVE_DIR   where archives are written       (required)
    BACKUP_KEEP          archives kept per label          (default 5)

## Manifest format

`snapshot.sh` writes exactly one tab-separated record to stdout:

    <epoch>\t<bytes>\t<archive-path>

`prune.sh` consumes those records on stdin. It uses the record only to
learn which directory and which label to rotate; the rotation decision is
made from what is actually on disk, so a stale manifest can never delete
an archive that a later run created.

## Archive naming

    <archive-dir>/<label>-<UTC timestamp>.tar.gz

The label is everything before the first `-`, which is how `prune.sh`
recovers it from a path.
