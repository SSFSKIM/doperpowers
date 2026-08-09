#!/usr/bin/env bash
# board-bind.sh — bind one spawned daemon exclusively to a ticket.
#
# Usage: board-bind.sh <daemon-uuid-or-prefix> <ticket-number>
#
# Serializes registry ownership on the daemon metadata lock. Existing active
# owners and parked needs-human owners are stable; otherwise old bindings are
# stripped first and the target is bound last. The registry is the ONLY home
# of the binding: machine-lifetime data never touches the issue.
#
# API mode additionally requires BOARD_RUN_ID in the environment (the
# dispatcher exports it, alongside BOARD_RUN_FENCE and BOARD_RUN_TOKEN): the
# run's session LOCATOR is posted to the board, and the registry meta gains
# run_id / fence / run_bearer / bind_confirmed — the local half a later resume
# rehydrates the worker from. Owner stability is the server's call there, so
# the two gh-mode stability rules do not apply.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ $# -eq 2 ] || { usage_from_header "$0" >&2; exit 2; }

T_Q="$1" T_ID="$2" T_DHOME="$DAEMON_HOME" T_NOW="$(_now)" _py - <<'PY'
import fcntl
import glob
import json
import os
import _board as B

env = os.environ


def write_meta(path, meta):
    """Rewrite a registry meta atomically, PRESERVING its mode. A bound meta
    carries the run bearer at 0600; a bookkeeping write that recreated it at
    the default umask would republish that secret world-readable."""
    mode = os.stat(path).st_mode & 0o777
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(meta, f, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


# API mode: the SERVER adjudicates who owns a ticket. bind runs immediately
# after a granted claim, so there is no local verdict left to reach — and no
# board snapshot to reach it from, since gh is never invoked in API mode.
API = env.get("BOARD_BINDING") == "api"
lock = open(os.path.join(env["T_DHOME"], ".metalock"), "a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX)
    # Park stability is decided under the same lock as registry mutation. A
    # pre-lock snapshot can go stale while waiting and steal a newly parked
    # ticket from its owner.
    if API:
        tid = str(env["T_ID"]).lstrip("#")
        if not tid.isdigit():
            B.die("not an issue number: %s" % env["T_ID"])
        ticket = {}
    else:
        tickets = B.snapshot()
        tid = B.resolve(env["T_ID"], tickets)
        ticket = tickets[tid]
    hits = []
    metas = []
    for path in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
        if path.endswith(".reply.json"):
            continue
        try:
            meta = json.load(open(path))
        except Exception:
            continue
        metas.append((path, meta))
        uuid = os.path.basename(path)[:-5]
        if uuid == env["T_Q"] or uuid.startswith(env["T_Q"]):
            hits.append((path, meta))
    if len(hits) != 1:
        B.die("%d daemons match '%s'" % (len(hits), env["T_Q"]))

    target, target_meta = hits[0]
    owners = [(path, meta) for path, meta in metas
              if path != target and str(meta.get("ticket", "")).lstrip("#") == tid]
    # Both stability rules are gh-mode LOCAL adjudication, and both are wrong
    # under a server that already decided. A successor claim exists precisely
    # because the predecessor run was reaped: its meta is routinely still
    # marked working and still holding the ticket, so the live-owner rule
    # would refuse the very handover the board just authorized. The park rule
    # reads a snapshot state that is not fetchable here at all.
    if not API:
        for _, owner in owners:
            if owner.get("status") in ("working", "blocked"):
                B.die("#%s is owned by active daemon %s" %
                      (tid, owner.get("name") or owner.get("uuid") or "unknown"))
        if ticket.get("state") == "needs-human" and owners:
            owner = owners[0][1]
            B.die("#%s is parked for daemon %s — answer/resume it before rebinding" %
                  (tid, owner.get("name") or owner.get("uuid") or "unknown"))

    # Fail-safe order: old owners are stripped first; target is bound last.
    # A mid-operation failure may leave no owner, never duplicate owners.
    for path, old in owners:
        del old["ticket"]
        write_meta(path, old)

    target_meta["ticket"] = tid
    target_meta["updated"] = env["T_NOW"]
    write_meta(target, target_meta)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()

print("bound #%s ← %s" % (tid, os.path.basename(target)[:-5]))
PY

# API mode: the registry write above is only the local half. The board also
# needs the session LOCATOR — which machine holds the transcript, which
# checkout, which session — and the meta needs the run identity a later
# resume re-injects into the worker it forks.
if [ "$BOARD_BINDING" = api ]; then
  [ -n "${BOARD_RUN_ID:-}" ] || die "API mode bind needs BOARD_RUN_ID in env (the dispatcher exports it)"
  T_Q="$1" T_RUN="$BOARD_RUN_ID" T_FENCE="${BOARD_RUN_FENCE:-}" \
  T_DHOME="$DAEMON_HOME" T_ROOT="$BOARD_ROOT" _api_py - <<'PY'
import fcntl
import glob
import json
import os
import socket
import _board_api as A

env = os.environ
# Same resolution rule as the ownership write above (which already proved it
# matches exactly one daemon): the meta FILENAME is the daemon's stable uuid,
# and the argument may be a prefix of it. The locator must carry the resolved
# uuid — a prefix names no session the board could ever reach.
target = None
for path in glob.glob(os.path.join(env["T_DHOME"], "*.json")):
    if path.endswith(".reply.json"):
        continue
    stem = os.path.basename(path)[:-5]
    if stem == env["T_Q"] or stem.startswith(env["T_Q"]):
        target = path
        break
if target is None:
    A.die("no daemon meta matches '%s'" % env["T_Q"])
uuid = os.path.basename(target)[:-5]

A.bind(env["T_RUN"], "local:" + socket.gethostname(),
       os.path.basename(env["T_ROOT"]), uuid)

# Only now — bind_confirmed is a claim about what the SERVER accepted, and a
# resume rehydrates from it. Written under the same lock as the ownership
# write, and mode 0600 before the file is in place: it carries a bearer.
lock = open(os.path.join(env["T_DHOME"], ".metalock"), "a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX)
    with open(target) as f:
        meta = json.load(f)
    meta["run_id"] = int(env["T_RUN"])
    if env["T_FENCE"]:
        meta["fence"] = int(env["T_FENCE"])
    if env.get("BOARD_RUN_TOKEN"):
        # Bearer at rest for resume rehydration: daemon-resume forks a fresh
        # process from the CALLER's env, so every later resume (relay,
        # successor, inline) re-injects BOARD_RUN_* from this meta. Local
        # plaintext, 0600 — the same posture as the session transcripts
        # beside it.
        meta["run_bearer"] = env["BOARD_RUN_TOKEN"]
    meta["bind_confirmed"] = True
    tmp = target + ".tmp"
    # 0600 from creation rather than after the write: the bearer must never
    # exist on disk world-readable, not even for the width of one write.
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(meta, f, indent=2)
    os.chmod(tmp, 0o600)   # a tmp left by an earlier crash keeps its old mode
    os.replace(tmp, target)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
PY
fi

_rerender_if_serving
