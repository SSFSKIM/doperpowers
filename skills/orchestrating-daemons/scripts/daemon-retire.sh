#!/usr/bin/env bash
# daemon-retire.sh <short-or-full-uuid> [purge]
#
# Retire a daemon from the active fleet. By default marks it status=retired but
# keeps its registry record. Pass `purge` to also delete the registry files
# (metadata/reply/err). The underlying claude session transcript on disk is NEVER
# touched — the human can still `claude --resume <uuid>` it interactively.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

uuid="$(_resolve_uuid "${1:?usage: daemon-retire.sh <uuid> [purge]}")"
name="$(_meta_get "$uuid" name)"
short="$(_meta_get "$uuid" short)"

# Stop the bg process if it is still live (idempotent).
[ -n "$short" ] && claude stop "$short" >/dev/null 2>&1 || true

if [ "${2:-}" = "purge" ]; then
  rm -f "$(_meta_path "$uuid")" "$(_reply_path "$uuid")" "$(_err_path "$uuid")"
  echo "purged $name [$uuid] from registry (session transcript left intact; resume with: claude --resume $uuid)"
else
  _meta_set "$uuid" status "retired" updated "$(_now)"
  echo "retired $name [$uuid] (still resumable: claude --resume $uuid)"
fi
