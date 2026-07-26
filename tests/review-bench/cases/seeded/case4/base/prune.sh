#!/usr/bin/env bash
# prune.sh -- rotate old archives out.
#
# Reads snapshot.sh manifest records on stdin:
#     <epoch>\t<bytes>\t<archive-path>
# and for every label mentioned there keeps the newest BACKUP_KEEP archives
# in that archive directory, deleting the rest.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$HERE/lib/common.sh"

KEEP="${BACKUP_KEEP:-$DEFAULT_KEEP}"
case "$KEEP" in
  ''|*[!0-9]*) die "BACKUP_KEEP must be a non-negative integer, got: $KEEP" ;;
esac
[ "$KEEP" -ge 1 ] || die "BACKUP_KEEP must be at least 1"

# list_archives <dir> <label> -- archive paths for one label, newest first.
list_archives() {
  local dir="$1" label="$2" file
  for file in "$dir/$label"-*.tar.gz; do
    [ -f "$file" ] || continue
    printf '%s\t%s\n' "$(epoch_of "$file")" "$file"
  done | sort -rn | cut -f2-
}

# prune_label <dir> <label> <keep>
prune_label() {
  local dir="$1" label="$2" keep="$3" file
  local idx=0
  while IFS= read -r file; do
    idx=$((idx + 1))
    [ "$idx" -gt "$keep" ] || continue
    rm -f "$file"
    log "pruned $file"
  done < <(list_archives "$dir" "$label")
  log "label=$label kept up to $keep of $idx archives in $dir"
}

seen=""
while IFS=$'\t' read -r epoch bytes path; do
  [ -n "${path:-}" ] || continue
  log "manifest record: epoch=$epoch bytes=$bytes archive=$path"
  if [ ! -f "$path" ]; then
    log "manifest points at a missing archive, skipping: $path"
    continue
  fi
  dir="$(dirname "$path")"
  base="$(basename "$path")"
  label="${base%%-*}"
  # One run can emit several records for the same label; rotate once.
  case "$seen" in
    *"|$dir/$label|"*) continue ;;
  esac
  seen="$seen|$dir/$label|"
  prune_label "$dir" "$label" "$KEEP"
done
