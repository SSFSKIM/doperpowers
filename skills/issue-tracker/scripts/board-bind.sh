#!/usr/bin/env bash
# board-bind.sh — bind one spawned daemon exclusively to a ticket.
#
# Usage: board-bind.sh <daemon-uuid-or-prefix> <ticket-number>
#
# Serializes registry ownership on the daemon metadata lock. Existing active
# owners and parked needs-human owners are stable; otherwise old bindings are
# stripped first and the target is bound last. The registry is the ONLY home
# of the binding: machine-lifetime data never touches the issue.
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
lock = open(os.path.join(env["T_DHOME"], ".metalock"), "a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX)
    # Park stability is decided under the same lock as registry mutation. A
    # pre-lock snapshot can go stale while waiting and steal a newly parked
    # ticket from its owner.
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
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(old, f, indent=2)
        os.replace(tmp, path)

    target_meta["ticket"] = tid
    target_meta["updated"] = env["T_NOW"]
    tmp = target + ".tmp"
    with open(tmp, "w") as f:
        json.dump(target_meta, f, indent=2)
    os.replace(tmp, target)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()

print("bound #%s ← %s" % (tid, os.path.basename(target)[:-5]))
PY

_rerender_if_serving
