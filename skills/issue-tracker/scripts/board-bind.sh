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
# the two gh-mode stability rules do not apply, and the SERVER'S VERDICT COMES
# FIRST: the POST happens inside the same locked section as the registry
# writes, ahead of them, so a refusal leaves ownership exactly where it was.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$SCRIPT_DIR/_lib.sh"
[ $# -eq 2 ] || { usage_from_header "$0" >&2; exit 2; }

# One python process, one lock, both modes. The API branch needs the client's
# env (url + credentials file) on top of the module path, so it runs under
# _api_py; gh mode keeps _py. Everything else — daemon resolution, the
# ownership strip, the meta writes — is one body rather than two, because
# splitting it is what opened the gap between the server's answer and the
# local handover.
if [ "$BOARD_BINDING" = api ]; then
  [ -n "${BOARD_RUN_ID:-}" ] || die "API mode bind needs BOARD_RUN_ID in env (the dispatcher exports it)"
  _bind_py=_api_py
else
  _bind_py=_py
fi

T_Q="$1" T_ID="$2" T_DHOME="$DAEMON_HOME" T_NOW="$(_now)" T_ROOT="$BOARD_ROOT" \
T_RUN="${BOARD_RUN_ID:-}" T_FENCE="${BOARD_RUN_FENCE:-}" "$_bind_py" - <<'PY'
import fcntl
import glob
import json
import os
import re
import socket

env = os.environ
# API mode: the SERVER adjudicates who owns a ticket. bind runs immediately
# after a granted claim, so there is no local verdict left to reach — and no
# board snapshot to reach it from, since gh is never invoked in API mode.
API = env.get("BOARD_BINDING") == "api"
if API:
    import _board_api as B
else:
    import _board as B
# The registry predicate is PURE and lives in the API client only because that
# is where it was first needed — it takes the identity rather than resolving
# one, so gh mode imports it just as safely (_py puts BOARD_SCRIPTS on the path
# in both bindings).
from _board_api import meta_is_mine as _meta_is_mine


def _board_ident():
    """This binding's identity as the registry spells it. ONE spelling, used
    both to STAMP a meta below and to recognize our own above — two copies of
    this expression is how a stamp and its reader drift apart."""
    if API:
        # rstrip: _board_api.url() normalizes the same way — one spelling
        # per board.
        return ("api:" + env.get("BOARD_API_URL", "").rstrip("/"),
                env.get("BOARD_REPO", ""))
    # gh mode needs no repo dimension: the owner/name inside the key IS it.
    return ("gh:" + B.repo(), "")


def MINE(meta):
    board, repo_key = _board_ident()
    return _meta_is_mine(meta, board, repo_key)


def write_meta(path, meta):
    """Rewrite a registry meta atomically. A meta carrying the run bearer is
    0600 from creation — the secret must never exist on disk world-readable,
    not even for the width of one write. Any other meta keeps the mode it
    already had: a bookkeeping write that recreated a bearer meta at the
    default umask would republish that secret."""
    mode = 0o600 if meta.get("run_bearer") else os.stat(path).st_mode & 0o777
    tmp = path + ".tmp"
    # The mode argument applies only to an inode this open CREATES. A .tmp left
    # by an earlier crash is an EXISTING inode at whatever mode it had (0644
    # under the default umask): it would be truncated, handed the run bearer,
    # and only chmod'ed afterwards — a disclosure window, and a permanent
    # exposure if the process dies mid-write. Unlink first, create exclusively.
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "w") as f:
        json.dump(meta, f, indent=2)
    os.chmod(tmp, mode)   # umask narrowing
    os.replace(tmp, path)


def _cur_boot():
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except OSError:
        out = os.popen("sysctl -n kern.boottime 2>/dev/null").read()
        m = re.search(r"sec = (\d+)", out)
        return m.group(1) if m else ""


HOST = socket.gethostname()
CUR_BOOT = _cur_boot()


def alive_here(meta):
    """working/blocked is only ACTIVE if the meta can name a process that
    still exists: same host, same boot (the daemon liveness rule). A meta
    from another boot is a daemon that died without finalizing — its ticket
    may have crossed into a state no recovery pass owns (in-review), where
    this check is the only thing standing between the successor and a
    permanent refusal. Missing identity fields = assume alive (legacy metas
    predate the stamp)."""
    mh, mb = str(meta.get("host") or ""), str(meta.get("boot_id") or "")
    if mh and mh != HOST:
        return False
    if mb and CUR_BOOT and mb != CUR_BOOT:
        return False
    return True


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
        # A BIND STRIPS THE TICKET OFF ITS PRIOR OWNERS, and ticket numbers are
        # board-local while this registry is machine-global — so an unfiltered
        # scan would strip a NEIGHBOUR's owner of ITS #9 while binding ours,
        # silently unbinding a live worker on a board this checkout cannot see.
        if not MINE(meta):
            continue
        metas.append((path, meta))
        # The meta FILENAME is the daemon's stable uuid, and the argument may
        # be a prefix of it. The locator posted below must carry the RESOLVED
        # uuid — a prefix names no session the board could ever reach.
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
            if owner.get("status") in ("working", "blocked") and alive_here(owner):
                B.die("#%s is owned by active daemon %s" %
                      (tid, owner.get("name") or owner.get("uuid") or "unknown"))
        # The park rule deliberately does NOT apply alive_here: a parked
        # ticket's owner meta is a wake target, and what it protects is
        # RESUMABILITY (the transcript survives a reboot; board-answer
        # respawns from it), not process liveness.
        if ticket.get("state") == "needs-human" and owners:
            owner = owners[0][1]
            B.die("#%s is parked for daemon %s — answer/resume it before rebinding" %
                  (tid, owner.get("name") or owner.get("uuid") or "unknown"))
    else:
        # THE SERVER ANSWERS BEFORE ANYTHING LOCAL MOVES. The board also needs
        # the session LOCATOR — which machine holds the transcript, which
        # checkout, which session. A refusal (fence-stale, run-ended, …) exits
        # from here with the registry untouched: an incumbent owner keeps its
        # ticket, and the refused caller is handed nothing. The run id is
        # converted first, so a malformed one never reaches the wire either.
        #
        # NO BEARER, NO BIND. bind_confirmed is a claim that this meta is
        # COMPLETE — that a later relay or successor can rehydrate the worker
        # out of it — and a meta holding no run bearer can do none of that:
        # every resume of that run would speak as somebody else, or as nobody.
        # Written anyway, the claim silenced the one repair path that could have
        # noticed. Refused loudly instead, before anything reaches the wire; the
        # lease expiring and a successor taking the ticket IS the recovery.
        if not env.get("BOARD_RUN_TOKEN"):
            B.die("bind refused for run %s: no run bearer in the environment. "
                  "Confirming this bind would declare %s.json complete while "
                  "every later resume of the run could not speak as it — let "
                  "the lease expire and take a successor instead."
                  % (env["T_RUN"], os.path.basename(target)[:-5]))
        run_id = int(env["T_RUN"])
        B.bind(run_id, "local:" + socket.gethostname(),
               os.path.basename(env["T_ROOT"]), os.path.basename(target)[:-5])

    # Fail-safe order: old owners are stripped first; target is bound last.
    # A mid-operation failure may leave no owner, never duplicate owners.
    for path, old in owners:
        del old["ticket"]
        write_meta(path, old)

    target_meta["ticket"] = tid
    target_meta["updated"] = env["T_NOW"]
    # The BOARD the ticket number belongs to. Ticket numbers are board-local
    # but this registry is machine-global, so the transition fence (dp#63)
    # needs the pair to adjudicate — a live worker on another board's #9 says
    # nothing about this board's #9. Same shape the fence computes for itself.
    target_meta["board"], _stamp_repo = _board_ident()
    if API:
        # ...AND WHICH REPO ON THAT BOARD. One service serves several repos out
        # of one ticket namespace, so `board` alone does not separate two repos'
        # daemons in this machine-global registry — their url is the same one.
        # Every registry scan reads this to leave a neighbour's workers alone;
        # without it a sweep renewed and RE-BOUND them, and a re-bind overwrites
        # that run's session locator with this repo's projectKey.
        target_meta["board_repo"] = _stamp_repo
    if API:
        # bind_confirmed is a claim about what the SERVER accepted, and a
        # resume rehydrates from it — so it is written only on this side of
        # the POST, in the same locked section that stamped the ownership.
        target_meta["run_id"] = run_id
        if env["T_FENCE"]:
            target_meta["fence"] = int(env["T_FENCE"])
        if env.get("BOARD_RUN_TOKEN"):
            # Bearer at rest for resume rehydration: daemon-resume forks a
            # fresh process from the CALLER's env, so every later resume
            # (relay, successor, inline) re-injects BOARD_RUN_* from this
            # meta. Local plaintext, 0600 — the same posture as the session
            # transcripts beside it.
            target_meta["run_bearer"] = env["BOARD_RUN_TOKEN"]
        target_meta["bind_confirmed"] = True
    write_meta(target, target_meta)
finally:
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()

print("bound #%s ← %s" % (tid, os.path.basename(target)[:-5]))
PY

_rerender_if_serving
