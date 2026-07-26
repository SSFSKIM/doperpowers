#!/usr/bin/env bash
# snapshot.sh -- create one compressed snapshot of BACKUP_SOURCE_DIR.
#
# Prints exactly one manifest record on stdout:
#     <epoch>\t<bytes>\t<archive-path>
# Everything else (progress, warnings) goes to stderr so the record can be
# piped straight into prune.sh.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$HERE/lib/common.sh"

CONFIG="${BACKUP_CONFIG:-$HERE/backup.conf}"
LABEL="daily"

usage() {
  cat >&2 <<'EOF'
usage: snapshot.sh [--label LABEL] [--config PATH]

  --label   name prefix for the archive (default: daily)
  --config  config file to load (default: $BACKUP_CONFIG or ./backup.conf)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --label)   LABEL="${2:-}"; shift 2 ;;
    --config)  CONFIG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)         usage; die "unknown argument: $1" ;;
  esac
done

[ -n "$LABEL" ] || die "--label may not be empty"

load_config "$CONFIG"
require_cmd tar gzip

: "${BACKUP_SOURCE_DIR:?BACKUP_SOURCE_DIR must be set in $CONFIG}"
: "${BACKUP_ARCHIVE_DIR:?BACKUP_ARCHIVE_DIR must be set in $CONFIG}"

[ -d "$BACKUP_SOURCE_DIR" ] || die "source directory missing: $BACKUP_SOURCE_DIR"
mkdir -p "$BACKUP_ARCHIVE_DIR"

# Archives can contain anything the source directory contained, so keep
# both the staging area and the finished archive private to this user.
umask 077

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/snapshot.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT INT TERM

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$BACKUP_ARCHIVE_DIR/${LABEL}-${stamp}.tar.gz"

log "archiving $BACKUP_SOURCE_DIR -> $archive"
tar -czf "$STAGE/payload.tar.gz" -C "$BACKUP_SOURCE_DIR" .

# Only publish the archive once tar has finished, so a crash mid-run never
# leaves a truncated archive where prune.sh can count it as a good one.
mv "$STAGE/payload.tar.gz" "$archive"

bytes="$(wc -c < "$archive" | tr -d '[:space:]')"
printf '%s\t%s\t%s\n' "$(epoch_of "$archive")" "$bytes" "$archive"
log "wrote $archive ($bytes bytes)"
