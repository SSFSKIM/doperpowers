#!/usr/bin/env bash
# common.sh -- helpers shared by snapshot.sh, prune.sh and run-backup.sh.
# This file is sourced, never executed.

BACKUP_LIB_VERSION="1.4.0"

# Archives kept per label when BACKUP_KEEP is not set.
DEFAULT_KEEP=5

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

die() {
  log "FATAL: $*"
  exit 1
}

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 || die "required command not found: $cmd"
  done
}

# epoch_of <path> -- mtime in seconds since the epoch.
epoch_of() {
  local path="$1"
  case "$(uname -s)" in
    Darwin|*BSD) stat -f %m "$path" ;;
    *)           stat -c %Y "$path" ;;
  esac
}

# load_config <path> -- read KEY=VALUE lines and export the BACKUP_* ones.
# Anything else is reported and skipped, so a stray line in an operator's
# config file cannot overwrite PATH, HOME or IFS.
load_config() {
  local path="$1" key value
  [ -r "$path" ] || die "config not readable: $path"
  while IFS='=' read -r key value; do
    case "$key" in
      ''|\#*)   continue ;;
      BACKUP_*) ;;
      *)        log "ignoring non-BACKUP key in config: $key"; continue ;;
    esac
    export "$key=$value"
  done < "$path"
}
