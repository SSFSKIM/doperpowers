#!/usr/bin/env bash
# daemon-reply.sh <short-or-full-uuid>
#
# Print a daemon's latest full reply (clean text). This is the "message from the
# daemon" you read before deciding whether to answer it yourself or escalate.

set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"
# shellcheck source=_codex_lib.sh
source "$DIR/_codex_lib.sh"

uuid="$(_resolve_uuid "${1:?usage: daemon-reply.sh <short-or-full-uuid>}")"
echo "$(_meta_get "$uuid" name)  [$uuid]  status=$(_meta_get "$uuid" status)  turns=$(_meta_get "$uuid" turns)"
echo "task: $(_meta_get "$uuid" task)"
echo "--- latest reply ---"
cur="$(_meta_get "$uuid" current)"; [ -n "$cur" ] || cur="$uuid"
if [ "$(_meta_get "$uuid" engine)" = "codex" ]; then
  # Codex daemons have no claude transcript: a finished turn's reply is the
  # recorded reply file; a live turn's best truth is the event log so far.
  if [ "$(_meta_get "$uuid" status)" = "working" ]; then
    live="$(_codex_last_message "$(_meta_get "$uuid" event_log)")"
    if [ -n "$live" ]; then printf '%s\n' "$live"; else echo "(turn in progress — no message yet)"; fi
  else
    _reply_text "$uuid"
  fi
  exit 0
fi
if [ "$(_meta_get "$uuid" status)" = "working" ]; then
  # A turn is in flight (or a watcher expired on it): the recorded reply file
  # belongs to a PREVIOUS turn — the live truth is the current session's
  # transcript. This is the recovery path resume points at after a watcher
  # timeout; without it a stale reply file would shadow the finished turn.
  reply="$(_transcript_reply "$cur")"
  if [ -n "$reply" ]; then printf '%s\n' "$reply"; else _reply_text "$uuid"; fi
else
  # The recorded reply file can still be stale/empty when the SPAWN watcher gave
  # up before the first turn finished — fall back to the current transcript.
  reply="$(_reply_text "$uuid")"
  if [ -n "$reply" ] && [ "$reply" != "(no reply yet)" ]; then
    printf '%s\n' "$reply"
  else
    _transcript_reply "$cur"
  fi
fi
