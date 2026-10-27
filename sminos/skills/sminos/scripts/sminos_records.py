#!/usr/bin/env python3
"""sminos_records — each session's machine-held record (O12 M1; the remote
layer's RL6): who owns the session, how it started, and what inference it
runs on.

`$SMINOS_HOME/session-records/<session>.json`, mode 0600, written whole and
atomically (sminos._write_record) under one lock for every change here:

    {session, source, origin, owners, ownersProof, principal, inference,
     controller?, created, former}

- The provenance (`origin`, `owners`, `ownersProof`, `principal`,
  `inference`, `created`, `former`) is written once. `source` says how it
  was established: `launch` (a pending launch claimed, or a desk or operator
  spawn), `hook` (the session's own environment, read by its hook or its
  bridge child), `lineage` (a predecessor's record, or the first `joined`
  along the session's lineage that carries owners), or `default` (nothing
  but the machine's defaults). A `default` record is provisional, and stays
  so when a continuation or a spawn copies it; it is replaced, its
  `controller` kept, once final evidence appears (establish). Every other
  record is final.
- `controller {lane, since}` is current state, not provenance: set at each
  launch by the bridge's lane verdict (set_controller) and never copied.
- `@machine`, as an owner or a principal, stands for this machine's owners;
  the endpoint resolves it against the org state, and it never leaves the
  machine. Nothing here leaves the machine but `owners` and `origin`, on a
  final record's `joined` (sminos.published_provenance).
- No secret is ever in a record: a route names a file (the merged launch
  settings a seat ran with) or a gateway's scheme, host and port.

A spawn fixes its child's provenance before the child exists: it writes
`pending/<launch>.json` and launches with `SMINOS_LAUNCH=<launch>` in the
merged settings' `env`; the child's first SessionStart, a startup, claims it
by one rename to `<session>.json` (claim). A pending launch nobody claimed in
a day is swept by the daemon (sweep_pending).
"""
import contextlib
import fcntl
import json
import os
import re
import sys
import time
import urllib.parse
import uuid

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sminos  # noqa: E402

LAUNCH_ENV = "SMINOS_LAUNCH"
LAUNCH_RE = re.compile(r"[0-9a-f]{32}")
MACHINE = "@machine"
SOURCES = ("launch", "hook", "lineage", "default")
LANES = ("A", "B")
PROVENANCE = ("origin", "owners", "ownersProof", "principal", "inference")
PENDING_KEPT_S = 86400


def records_dir():
    return os.path.join(sminos.root(), "session-records")


def record_path(sid):
    return os.path.join(records_dir(), sid + ".json")


def pending_path(launch):
    return os.path.join(records_dir(), "pending", launch + ".json")


def _valid(rec):
    return (isinstance(rec, dict) and isinstance(rec.get("owners"), list) and rec["owners"]
            and isinstance(rec.get("origin"), dict) and rec.get("source") in SOURCES)


def read(sid):
    """The session's record, or None when it has none (or an unreadable one)."""
    if not sminos.UUID_RE.fullmatch(str(sid or "")):
        return None
    try:
        with open(record_path(sid)) as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    return rec if _valid(rec) else None


def is_final(rec):
    return bool(rec) and rec.get("source") != "default"


@contextlib.contextmanager
def _locked(deadline=None):
    """Every change to the records, one at a time across processes; with a
    deadline (the record hook's), waited for only until then (LockBusy)."""
    os.makedirs(records_dir(), mode=0o700, exist_ok=True)
    with open(os.path.join(records_dir(), ".lock"), "a") as lf:
        sminos.flock_until(lf, deadline)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _record(sid, prov, created=None, controller=None):
    rec = {"session": sid, "source": prov.get("source") or "default"}
    for k in PROVENANCE:
        rec[k] = prov[k]
    if controller:
        rec["controller"] = controller
    rec["created"] = created or prov.get("created") or sminos.now()
    rec["former"] = list(prov.get("former") or [])
    return rec


def establish(sid, prov, deadline=None):
    """(record, changed): the session's record, written from `prov` (a
    provenance: PROVENANCE's fields, `source`, maybe `former`) when it has
    none, or when it has a provisional one and `prov` is final; otherwise
    the record it has, unchanged."""
    with _locked(deadline):
        have = read(sid)
        if is_final(have) or (have is not None and not is_final(prov)):
            return have, False
        rec = _record(sid, prov, controller=(have or {}).get("controller"))
        sminos._write_record(record_path(sid), rec)
        return rec, True


def set_controller(sid, lane, since=None):
    """The session's current controller, `{lane, since}`, on its existing
    record, its provenance untouched (the bridge's lane verdict, O12 M3).
    False when the session has no record yet."""
    if lane not in LANES:
        raise ValueError("lane is A or B: %r" % (lane,))
    with _locked():
        rec = read(sid)
        if rec is None:
            return False
        rec["controller"] = {"lane": lane, "since": since or sminos.now()}
        sminos._write_record(record_path(sid), rec)
        return True


def new_launch():
    return uuid.uuid4().hex


def write_pending(launch, prov):
    """A launch's provenance, waiting for its session to claim it."""
    if not LAUNCH_RE.fullmatch(launch):
        raise ValueError("bad launch id: %r" % (launch,))
    os.makedirs(os.path.dirname(pending_path(launch)), mode=0o700, exist_ok=True)
    sminos._write_record(pending_path(launch), {**prov, "created": prov.get("created") or sminos.now()})


def drop_pending(launch):
    try:
        os.unlink(pending_path(launch))
    except OSError:
        pass


def claim(launch, sid, deadline=None):
    """The session's record from a pending launch: one rename, so of two
    claimants only one finds it, and only by a session with no final record
    of its own. The claimed record, or None."""
    if not (LAUNCH_RE.fullmatch(str(launch or "")) and sminos.UUID_RE.fullmatch(str(sid or ""))):
        return None
    with _locked(deadline):
        have = read(sid)
        if is_final(have):
            return None
        try:
            os.replace(pending_path(launch), record_path(sid))
        except FileNotFoundError:
            return None
        try:
            with open(record_path(sid)) as f:
                prov = json.load(f)
        except (OSError, ValueError):
            prov = None
        if not (isinstance(prov, dict) and all(k in prov for k in PROVENANCE)):
            # Not a provenance this code wrote: the claim stands, its content does not.
            prov = default_provenance()
        rec = _record(sid, prov, controller=(have or {}).get("controller"))
        sminos._write_record(record_path(sid), rec)
        return rec


def sweep_pending(now=None):
    """Removes the pending launches no session claimed within
    PENDING_KEPT_S; returns their ids."""
    now = time.time() if now is None else now
    d = os.path.dirname(pending_path("0" * 32))
    try:
        names = os.listdir(d)
    except OSError:
        return []
    gone = []
    for name in sorted(names):
        launch, ext = os.path.splitext(name)
        if ext != ".json" or not LAUNCH_RE.fullmatch(launch):
            continue
        try:
            if now - os.stat(os.path.join(d, name)).st_mtime < PENDING_KEPT_S:
                continue
            os.unlink(os.path.join(d, name))
        except OSError:
            continue
        gone.append(launch)
    return gone


# ------------------------------------------------------------ provenance


def slot(env=None):
    """The config-dir slot an environment runs on: CLAUDE_CONFIG_DIR, else
    the default `~/.claude`."""
    env = os.environ if env is None else env
    d = env.get("CLAUDE_CONFIG_DIR") or os.path.join(sminos.home_dir(), ".claude")
    return {"kind": "slot", "configDir": os.path.abspath(os.path.expanduser(d))}


def base_url_ref(url):
    """`base-url:<scheme>://<host>[:<port>]` for a gateway's base URL (no
    credentials, path or query), or None for one that names no host."""
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
        host, port = p.hostname, p.port
    except ValueError:
        return None
    if not (p.scheme and host):
        return None
    host = "[%s]" % host if ":" in host else host
    return "base-url:%s://%s%s" % (p.scheme.lower(), host, ":%d" % port if port else "")


def session_inference(env=None):
    """The inference a session's own environment shows: the gateway its
    ANTHROPIC_BASE_URL names (as MAWS's gateway launches set it), else its slot."""
    env = os.environ if env is None else env
    ref = base_url_ref(env.get("ANTHROPIC_BASE_URL")) if env.get("ANTHROPIC_BASE_URL") else None
    return {"kind": "route", "settingsRef": ref} if ref else slot(env)


def default_provenance(source="default"):
    """The machine's defaults: its owners, a terminal origin, the default slot."""
    return {"origin": {"kind": "terminal"}, "owners": [MACHINE], "ownersProof": [], "principal": MACHINE,
            "inference": slot({}), "source": source}


def hook_provenance(marked, env=None):
    """A session nobody launched through sminos, from its own environment:
    MAWS's when its host marked it (sminos.member_mark), else a terminal's."""
    return {**default_provenance("hook"), "origin": {"kind": "maws" if marked else "terminal"},
            "inference": session_inference(env)}


def inherited(rec, former):
    """A continuation's provenance: its predecessor's record, provisional
    when that one is, with the sessions it continues (`former`, newest first)."""
    return {**{k: rec[k] for k in PROVENANCE}, "source": "lineage" if is_final(rec) else "default",
            "former": list(dict.fromkeys(list(former) + list(rec.get("former") or [])))}


def from_joined(event, former=()):
    """A provenance from a `joined` that carries owners: its owners and
    origin; the principal its requester's for a desk spawn, else the
    machine's; the default slot (the log carries no inference)."""
    origin = event["origin"] if isinstance(event.get("origin"), dict) else {"kind": "terminal"}
    requester = origin.get("requester") if origin.get("kind") == "maws" else None
    return {**default_provenance("lineage"), "origin": origin, "owners": list(event["owners"]),
            "principal": requester if isinstance(requester, str) and requester else MACHINE,
            "former": list(former)}
