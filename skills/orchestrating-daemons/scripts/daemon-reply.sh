#!/usr/bin/env bash
# daemon-reply.sh <short-or-full-uuid>
#
# Print a daemon's latest full reply (clean text). This is the "message from the
# daemon" you read before deciding whether to answer it yourself or escalate.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"

uuid="$(_resolve_uuid "${1:?usage: daemon-reply.sh <short-or-full-uuid>}")"
echo "$(_meta_get "$uuid" name)  [$uuid]  status=$(_meta_get "$uuid" status)  turns=$(_meta_get "$uuid" turns)"
echo "task: $(_meta_get "$uuid" task)"
echo "--- latest reply ---"
# The recorded reply file can be stale/empty when the spawn watcher gave up
# before a long first turn finished — fall back to the live transcript.
reply="$(_reply_text "$uuid")"
if [ -n "$reply" ] && [ "$reply" != "(no reply yet)" ]; then
  printf '%s\n' "$reply"
else
  _transcript_reply "$uuid"
fi
