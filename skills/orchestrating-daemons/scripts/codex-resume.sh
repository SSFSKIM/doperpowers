#!/usr/bin/env bash
# codex-resume.sh <uuid-or-prefix-or-name-short> <message>
#
# Continue a CODEX daemon: `codex exec resume <session-id>` — the codex sibling
# of daemon-resume.sh. Unlike claude, codex keeps ONE session id across
# resumes: no forking, no purge, `current` never changes. NEVER RUN IN THE
# FOREGROUND (blocks while the turn runs) — Monitor or background shell.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$DIR/_lib.sh"
# shellcheck source=_codex_lib.sh
source "$DIR/_codex_lib.sh"
CODEX_LIB_DIR="$DIR"; export CODEX_LIB_DIR

uuid="$(_resolve_uuid "${1:?usage: codex-resume.sh <id> <message>}")"
msg="${2:?missing message}"

[ "$(_meta_get "$uuid" engine)" = "codex" ] \
  || { echo "codex-resume: $uuid is not a codex daemon — use daemon-resume.sh" >&2; exit 1; }

# One turn per daemon at a time (same invariant as claude daemons).
if [ "$(_meta_get "$uuid" status)" = "working" ]; then
  pid="$(_meta_get "$uuid" pid)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "codex-resume: a turn is still running (pid $pid) — wait for it or retire" >&2
    exit 1
  fi
  # The pid is dead, but liveness (pid) and the registry write that finalizes
  # a turn (status) are two different signals read non-atomically: the prior
  # turn's _codex_launch wrapper can still be finalizing (_meta_set landing
  # AFTER our writes below would flip the registry back to a stale terminal
  # status mid-flight). The wrapper's rc file is its completion barrier — it
  # is written LAST, once the registry + reply are already finalized (see
  # _codex_launch) — so derive it from this meta's event_log
  # ("<run>.events.jsonl" -> "<run>.rc") and wait a bounded window for it.
  # If it appears, finalization is done (re-read status below rather than
  # trust the value read above); if it never appears, the previous wrapper
  # died mid-flight and there is nothing left to wait for — proceed.
  prev_log="$(_meta_get "$uuid" event_log)"
  if [ -n "$prev_log" ]; then
    prev_rc="${prev_log%.events.jsonl}.rc"
    bound="${CODEX_RC_BARRIER_WAIT:-10}"
    j=0
    while [ ! -f "$prev_rc" ] && [ "$j" -lt "$bound" ]; do sleep 1; j=$((j + 1)); done
  fi
fi

cwd="$(_meta_get "$uuid" cwd)"; [ -d "$cwd" ] || cwd="$PWD"
model="$(_meta_get "$uuid" model)"; [ -n "$model" ] || model="${CODEX_MODEL:-gpt-5.6-sol}"
effort="$(_meta_get "$uuid" effort)"; [ -n "$effort" ] || effort="${CODEX_EFFORT:-high}"

runs="$DAEMON_HOME/runs"; mkdir -p "$runs"
run="$(mktemp "$runs/codex-run.XXXXXX")"; rm -f "$run"
taskf="$run.task.txt"
printf '%s' "$msg" > "$taskf"

# Resume-specific flags: `codex exec resume` has no --sandbox option at all
# (rc=2, no JSON — see _codex_resume_flags). Everything else (-m, effort,
# network, hooks, approvals) is unchanged from a fresh spawn.
_codex_resume_flags "$model" "$effort"
addroot="$(_codex_main_root "$cwd")"
[ -n "$addroot" ] && CODEX_FLAGS=( "${CODEX_FLAGS[@]}" --add-dir "$addroot" )

_codex_launch "$cwd" "$taskf" "$run" exec resume "$uuid" "${CODEX_FLAGS[@]}"

# Wait for the new pid (catches a `cd` failure, which never even backgrounds
# codex and writes an rc file directly instead).
i=0
while [ ! -f "$run.pid" ]; do
  if [ -f "$run.rc" ]; then break; fi
  i=$((i + 1)); [ "$i" -ge 15 ] && break
  sleep 1
done

# Early-failure detection (mirrors codex-spawn.sh's no-session-id guard): a
# CLI-argument-level failure (rc=2 — e.g. an unsupported flag, or the `cd`
# failure above) exits before ever emitting this uuid's thread.started event,
# so its rc file can appear while the event log still shows no activity at
# all. Only treat the resume as a real turn — and only THEN bump turns —
# once we see that activity, or a short bounded wait for it runs out (at
# which point a turn is presumably genuinely underway and just slow to log).
i=0; max="${DAEMON_UUID_POLL:-30}"; started=""
while :; do
  if [ -n "$(_codex_thread_id "$run.events.jsonl")" ]; then started=1; break; fi
  if [ -f "$run.rc" ]; then break; fi
  i=$((i + 1)); [ "$i" -ge "$max" ] && { started=1; break; }
  sleep 2
done

if [ -z "$started" ]; then
  rc="$(cat "$run.rc" 2>/dev/null || printf '1')"
  echo "codex-resume: turn failed to start (rc=$rc) — turns not incremented:" >&2
  tail -5 "$run.err" >&2 2>/dev/null || true
  exit 1
fi

turns="$(_meta_get "$uuid" turns)"; turns=$((${turns:-1} + 1))
_meta_set "$uuid" pid "$(cat "$run.pid" 2>/dev/null || printf '')" \
  event_log "$run.events.jsonl" status "working" turns "$turns" updated "$(_now)"
[ -f "$run.rc" ] && _meta_set "$uuid" \
  status "$(_codex_final_status "$(cat "$run.rc")" "$run.events.jsonl")" updated "$(_now)"

# Blocking wait (same bound + semantics as codex-spawn — rc IS the completion
# barrier: _codex_launch writes it last, after the registry/reply are already
# finalized, so no post-loop settle sleep is needed here).
i=0; max=$((DAEMON_TIMEOUT / 2)); [ "$max" -le 0 ] && max=0
while [ ! -f "$run.rc" ]; do
  i=$((i + 1))
  if [ "$max" -gt 0 ] && [ "$i" -ge "$max" ]; then
    echo "resumed: [codex $uuid] status=working (watcher timeout — turn continues)"
    exit 0
  fi
  sleep 2
done
echo "resumed: [codex $(printf '%.8s' "$uuid")] status=$(_meta_get "$uuid" status)"
echo "--- reply ---"
_reply_text "$uuid"
