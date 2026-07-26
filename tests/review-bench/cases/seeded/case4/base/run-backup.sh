#!/usr/bin/env bash
# run-backup.sh -- cron entry point: snapshot, then rotate.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$HERE/lib/common.sh"

CONFIG="${BACKUP_CONFIG:-$HERE/backup.conf}"
LABEL="daily"

usage() {
  cat >&2 <<'EOF'
usage: run-backup.sh [--label LABEL] [--config PATH]
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

manifest="$(mktemp "${TMPDIR:-/tmp}/backup-manifest.XXXXXX")"
trap 'rm -f "$manifest"' EXIT INT TERM

log "backup starting (lib $BACKUP_LIB_VERSION) label=$LABEL config=$CONFIG"

"$HERE/snapshot.sh" --label "$LABEL" --config "$CONFIG" >"$manifest"

while IFS=$'\t' read -r epoch bytes path; do
  log "snapshot done: epoch=$epoch bytes=$bytes archive=$path"
done <"$manifest"

"$HERE/prune.sh" <"$manifest"

log "backup complete label=$LABEL"
