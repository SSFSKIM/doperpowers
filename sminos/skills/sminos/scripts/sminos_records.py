#!/usr/bin/env python3
"""sminos_records — each session's machine-held record (O12 M1; the remote
layer's RL6): who owns the session, how it started, and what inference it
runs on.

`$SMINOS_HOME/session-records/<session>.json`, mode 0600, written whole and
atomically (sminos._write_record) under one lock for every change here:

    {session, source, origin, owners, ownersProof, principal, inference,
     controller?, created, former}

- The provenance (`origin`, `owners`, `ownersProof`, `principal`,
  `inference`, `created`, `former`) rests on one kind of evidence, its
  `basis`, strongest first: `launch` (a pending launch claimed, or a desk or
  operator spawn), `lineage` (a predecessor's record, or the latest `joined`
  along the session's lineage that publishes), `hook` (the session's own
  environment, read by its hook or its bridge child, which speaks only for
  a session no launch and no lineage speaks for), `default` (nothing but
  the machine's defaults). `source` is the basis when the evidence is final
  and `default` when it is provisional: the defaults, or a launch or a
  continuation that copied a provisional record. A record is replaced, its
  `controller` kept, only by strictly stronger evidence (strength: the
  basis's rank, then final over provisional), so it moves up at most a few
  times and never back.
- `controller {lane, since}` is current state, not provenance: set at each
  launch by the bridge's lane verdict (set_controller) and never copied.
- `@machine`, as an owner or a principal, stands for this machine's owners,
  and as an owner it stands alone: a list that mixes it with member ids is
  refused by every writer here (checked_owners), since `joined` leaves the
  token off and its readers would lose the members beside it;
  the endpoint resolves it against the org state, and it never leaves the
  machine. Nothing here leaves the machine but `origin`, and `owners` that
  hold no `@machine`, on a final record's `joined` (sminos.published_provenance).
- No secret is ever in a record: a route names a file (the merged launch
  settings a seat ran with) or a gateway's scheme, host and port.

A spawn fixes its child's provenance before the child exists: it writes
`pending/<launch>.json` and launches with `SMINOS_LAUNCH=<launch>` in the
merged settings' `env`. The child's first SessionStart, a startup, binds the
launch to its session id with no lock (bind: `pending/<launch>.session`,
created whole by a link), and the claim (one rename to `<session>.json`) is
honoured for the bound session alone, whoever makes it: its hooks, until one
succeeds, or its spawner. A pending launch, or a binding, older than a day
is swept by the daemon (sweep_pending).

MAWS's engine host launches a session it spawned for a remote member with
`MAWS_LAUNCHED_BY` beside its member mark (O12 M11): the spawner, and a
proof file holding the sealed spawn action. The hook honours it for a
marked session alone (hook_provenance), and only for the first session of
its `appSessionId` (bind_launched: `launched/<sha256 of it>.jsonl`, created
whole by a link, later sessions appended under its lock); a later one is a
continuation of the latest before it.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
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
RANK = {"default": 0, "hook": 1, "lineage": 2, "launch": 3}   # a basis's strength
LANES = ("A", "B")
PROVENANCE = ("origin", "owners", "ownersProof", "principal", "inference")
PENDING_KEPT_S = 86400
LAUNCHED_ENV = "MAWS_LAUNCHED_BY"
LAUNCHED_KEYS = ("appSessionId", "member", "device", "opId", "proofFile")
PROOF_MAX = 5 * 1024 * 1024   # the sealed action carries a brief up to the channel's 4 MiB


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
    """The session's record, or None when it has none (or an unreadable one).
    Records are written whole, by rename, so a stat tells one unchanged
    (sminos.json_at): the daemon's tick asks for every member's."""
    if not sminos.UUID_RE.fullmatch(str(sid or "")):
        return None
    try:
        rec = sminos.json_at(record_path(sid))
    except (OSError, ValueError):
        return None
    return rec if _valid(rec) else None


def is_final(rec):
    return bool(rec) and rec.get("source") != "default"


def basis(rec):
    """The evidence a record or a provenance rests on (RANK)."""
    b = rec.get("basis")
    return b if b in RANK else (rec.get("source") if rec.get("source") in RANK else "default")


def strength(rec):
    return RANK[basis(rec)], is_final(rec)


def stronger(prov, have):
    """Whether `prov` may replace the record `have`: strictly stronger
    evidence only, so equal evidence read twice never flips a record."""
    return have is None or strength(prov) > strength(have)


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


def checked_owners(owners):
    """`owners` when it is a record's: a non-empty list of strings, either
    exactly `@machine` or member ids only; otherwise ValueError."""
    if not (isinstance(owners, list) and owners and all(isinstance(o, str) and o for o in owners)):
        raise ValueError("owners must be a non-empty list of strings: %r" % (owners,))
    if MACHINE in owners and owners != [MACHINE]:
        raise ValueError("owners mixes %s with member ids: %r" % (MACHINE, owners))
    return owners


def _record(sid, prov, created=None, controller=None):
    checked_owners(prov.get("owners"))
    rec = {"session": sid, "source": prov.get("source") or "default", "basis": basis(prov)}
    for k in PROVENANCE:
        rec[k] = prov[k]
    if controller:
        rec["controller"] = controller
    rec["created"] = created or prov.get("created") or sminos.now()
    rec["former"] = list(prov.get("former") or [])
    return rec


def establish(sid, prov, deadline=None):
    """(record, changed): the session's record, written from `prov` (a
    provenance: PROVENANCE's fields, `source`, `basis`, maybe `former`) when
    it has none or `prov` is stronger evidence than its own (stronger);
    otherwise the record it has, unchanged."""
    with _locked(deadline):
        have = read(sid)
        if not stronger(prov, have):
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


def binding_path(launch):
    return os.path.join(records_dir(), "pending", launch + ".session")


def bound_to(launch):
    """The session a launch is bound to, or "" for none (or one unreadable)."""
    if not LAUNCH_RE.fullmatch(str(launch or "")):
        return ""
    try:
        with open(binding_path(launch)) as f:
            sid = f.read().strip()
    except OSError:
        return ""
    return sid if sminos.UUID_RE.fullmatch(sid) else ""


def bind(launch, sid):
    """Binds a launch to the first session that asks: the seat's own
    SessionStart (before any tool of it runs), else its spawner once the
    harness names it. A file created whole by one link, no lock taken, so
    a claim that cannot have the records' lock still leaves the launch
    bound, and a session a seat's Bash starts later finds it bound to
    another. Returns the session it is bound to ("" when it cannot say)."""
    if not (LAUNCH_RE.fullmatch(str(launch or "")) and sminos.UUID_RE.fullmatch(str(sid or ""))):
        return ""
    path = binding_path(launch)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = "%s.%d.%s.tmp" % (path, os.getpid(), uuid.uuid4().hex[:8])
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(sid + "\n")
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return bound_to(launch)


def write_pending(launch, prov):
    """A launch's provenance, waiting for its session to claim it."""
    if not LAUNCH_RE.fullmatch(launch):
        raise ValueError("bad launch id: %r" % (launch,))
    checked_owners(prov.get("owners"))
    os.makedirs(os.path.dirname(pending_path(launch)), mode=0o700, exist_ok=True)
    sminos._write_record(pending_path(launch), {**prov, "created": prov.get("created") or sminos.now()})


def drop_pending(launch):
    for path in (pending_path(launch), binding_path(launch)):
        try:
            os.unlink(path)
        except OSError:
            pass


def claim(launch, sid, deadline=None):
    """The session's record from a pending launch: honoured only for the
    session the launch is bound to (bind), by one rename, and never over a
    record a launch already established. The claimed record, or None."""
    if not (LAUNCH_RE.fullmatch(str(launch or "")) and sminos.UUID_RE.fullmatch(str(sid or ""))):
        return None
    if bound_to(launch) != sid:
        return None
    with _locked(deadline):
        have = read(sid)
        if have is not None and basis(have) == "launch":
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
        try:
            if not (isinstance(prov, dict) and all(k in prov for k in PROVENANCE)):
                raise ValueError("not a provenance")
            checked_owners(prov["owners"])
        except ValueError:
            # Not a provenance this code wrote: the claim stands, its content does not.
            prov = default_provenance()
        rec = _record(sid, {**prov, "basis": "launch"}, controller=(have or {}).get("controller"))
        sminos._write_record(record_path(sid), rec)
        return rec


def sweep_pending(now=None):
    """Removes the pending launches no session claimed within
    PENDING_KEPT_S, and their bindings (those of claimed launches too);
    returns the ids of the launches removed."""
    now = time.time() if now is None else now
    d = os.path.dirname(pending_path("0" * 32))
    try:
        names = os.listdir(d)
    except OSError:
        return []
    gone = []
    for name in sorted(names):
        launch, ext = os.path.splitext(name)
        if ext not in (".json", ".session") or not LAUNCH_RE.fullmatch(launch):
            continue
        try:
            if now - os.stat(os.path.join(d, name)).st_mtime < PENDING_KEPT_S:
                continue
            os.unlink(os.path.join(d, name))
        except OSError:
            continue
        if ext == ".json":
            gone.append(launch)
    return gone


# ------------------------------------------------------------ provenance


def slot(env=None):
    """The config-dir slot an environment runs on: CLAUDE_CONFIG_DIR, else
    the default `~/.claude`."""
    return {"kind": "slot", "configDir": sminos.config_dir(env)}


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
    """The machine's defaults: its owners, a terminal origin, the default
    slot; final and resting on `source` when it is not `default`."""
    return {"origin": {"kind": "terminal"}, "owners": [MACHINE], "ownersProof": [], "principal": MACHINE,
            "inference": slot({}), "source": source, "basis": source}


def hook_provenance(marked, env=None, session=""):
    """A session nobody launched through sminos, from its own environment:
    MAWS's when its host marked it (sminos.member_mark), else a terminal's.
    A marked session whose MAWS_LAUNCHED_BY parses (launched_by) is its
    spawner's, with the proof file's action as its ownersProof when the file
    bears the spawn out (launched_proof)."""
    env = os.environ if env is None else env
    prov = {**default_provenance("hook"), "origin": {"kind": "maws" if marked else "terminal"},
            "inference": session_inference(env)}
    launched = launched_by(env) if marked else None
    if launched is None:
        return prov
    member = launched["member"]
    return {**prov, "owners": [member], "principal": member, "origin": {"kind": "maws", "requester": member},
            "ownersProof": launched_proof(launched, session)}


def launched_by(env=None):
    """MAWS_LAUNCHED_BY as a dict of its five non-empty strings
    (LAUNCHED_KEYS), or None when it is unset or does not parse so."""
    env = os.environ if env is None else env
    try:
        v = json.loads(env.get(LAUNCHED_ENV) or "")
    except ValueError:
        return None
    if not (isinstance(v, dict) and all(isinstance(v.get(k), str) and v[k] for k in LAUNCHED_KEYS)) \
            or v["member"] == MACHINE:
        return None
    return {k: v[k] for k in LAUNCHED_KEYS}


def launched_proof(launched, session=""):
    """[the sealed spawn action] when the proof file is a regular file of at
    most PROOF_MAX bytes holding the envelope {member, device, opId, action}
    whose member, device and opId are the variable's, and whose action names
    the same device and opId (it carries no member: the endpoint's binding
    is). Otherwise [], said in daemon.log without the file's content. The
    proof attests; the owners follow the variable either way, which the
    engine host set once the endpoint authorized the spawn."""
    why, data = None, b""
    try:
        fd = os.open(launched["proofFile"], os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        why = "cannot be opened (%s)" % (e.strerror or type(e).__name__)
    else:
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                why = "is not a regular file"
            elif st.st_size > PROOF_MAX:
                why = "is larger than %d bytes" % PROOF_MAX
            else:
                while len(data) <= PROOF_MAX and (chunk := os.read(fd, PROOF_MAX + 1 - len(data))):
                    data += chunk
                why = "is larger than %d bytes" % PROOF_MAX if len(data) > PROOF_MAX else None
        except OSError as e:
            why = "cannot be read (%s)" % (e.strerror or type(e).__name__)
        finally:
            os.close(fd)
        if why is None:
            try:
                env = json.loads(data)
            except ValueError:
                env = None
            action = env.get("action") if isinstance(env, dict) else None
            if not isinstance(env, dict):
                why = "does not parse as a JSON object"
            elif any(env.get(k) != launched[k] for k in ("member", "device", "opId")):
                why = "names another member, device or opId than %s" % LAUNCHED_ENV
            elif not isinstance(action, dict):
                why = "holds no action object"
            elif any(action.get(k) != launched[k] for k in ("device", "opId")):
                why = "holds an action for another device or opId"
            else:
                return [action]
    try:
        sminos.daemon_log("record: session %s: the spawner's proof %s: its ownersProof is []"
                          % (str(session)[:8] or "?", why))
    except OSError:
        pass
    return []


def launched_path(app):
    """The sessions bound to a MAWS appSessionId, one JSON line each in the
    order they claimed it; named by its hash, since MAWS's id is any
    non-empty string."""
    return os.path.join(records_dir(), "launched", hashlib.sha256(app.encode("utf-8")).hexdigest() + ".jsonl")


def _launched_sessions(text):
    out = []
    for line in text.splitlines():
        try:
            sid = json.loads(line).get("session")
        except (ValueError, AttributeError):
            continue   # a line torn by a crash
        if isinstance(sid, str) and sminos.UUID_RE.fullmatch(sid) and sid not in out:
            out.append(sid)
    return out


def bind_launched(app, sid, deadline=None):
    """The sessions bound to `app` before `sid`, newest first, binding `sid`
    when it is not yet: [] for its first session, which takes the variable.
    The first binding is a file created whole by one link (bind's rule), so
    of two claimants exactly one is first; a later session is appended under
    the file's lock (waited for until `deadline`, else LockBusy)."""
    path = launched_path(app)
    line = json.dumps({"appSessionId": app, "session": sid, "at": sminos.now()}) + "\n"
    try:
        with open(path) as f:
            have = _launched_sessions(f.read())
    except FileNotFoundError:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = "%s.%d.%s.tmp" % (path, os.getpid(), uuid.uuid4().hex[:8])
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(line)
            try:
                os.link(tmp, path)
                return []
            except FileExistsError:
                pass
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        have = []
    if sid in have:
        return list(reversed(have[:have.index(sid)]))
    with open(path, "a+") as f:
        sminos.flock_until(f, deadline)
        try:
            f.seek(0)
            text = f.read()
            have = _launched_sessions(text)
            if sid in have:
                return list(reversed(have[:have.index(sid)]))
            f.write(line if not text or text.endswith("\n") else "\n" + line)
            f.flush()
            return list(reversed(have))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def inherited(rec, former):
    """A continuation's provenance: its predecessor's record, provisional
    when that one is, with the sessions it continues (`former`, newest first)."""
    return {**{k: rec[k] for k in PROVENANCE}, "source": "lineage" if is_final(rec) else "default",
            "basis": "lineage", "former": list(dict.fromkeys(list(former) + list(rec.get("former") or [])))}


def from_joined(event, former=()):
    """A provenance from a `joined` that publishes: its owners and
    origin; the principal its requester's for a desk spawn, else the
    machine's; the default slot (the log carries no inference)."""
    origin = event["origin"] if isinstance(event.get("origin"), dict) else {"kind": "terminal"}
    requester = origin.get("requester") if origin.get("kind") == "maws" else None
    return {**default_provenance("lineage"), "origin": origin, "owners": list(event["owners"]),
            "principal": requester if isinstance(requester, str) and requester else MACHINE,
            "former": list(former)}
