#!/usr/bin/env python3
"""sminos_rl10 — this machine's endpoint (RL10): sminos under mawsd, local-only.

A machine whose `mawsd` endpoint serves RL10 writes `rl10.json` (O2's
literal paths, `path`): the endpoint's Unix socket, a token and the protocol's
major. The uplink child (`sminos daemon uplink`) then speaks RL10 to it in
place of DX2 to the hub: the same frames, newline-delimited JSON on the
socket, at most FRAME_LIMIT a line (larger text as DX2's `part`s), one
ordered stream with no codes. Nothing of the machine opens a connection to
the hub once it is cut over.

- Discovery (`find`): a regular file of mode 0600 owned by this uid, with
  `protocol` 1, a `token` of 64 hex characters and a `socket` path; anything
  else is no endpoint, said once in daemon.log. SMINOS_RL10 names the file
  for a test, else `$MAWS_USER_DATA/mawsd/endpoint/rl10.json` when
  MAWS_USER_DATA is set, else the platform's default.
- The connection (`Connection`): dialled within DIAL_TIMEOUT; `hello` with
  the token is its first line, and the first line back must be `welcome`
  within WELCOME_WAIT (`refuse`, a close or silence ends it: `Refused`).
  `Reader` then reads its lines for the uplink's main thread.
- The cutover (`welcomed`): every welcome whose identity is whole (org,
  hub, name, ref, enrolled: an endpoint enrolled and org-listed; anything
  less cuts nothing over) writes `daemon/identity.json`
  ({org, hub, name, former, ref, enrolled, cutover, build}, 0600, whole),
  whose presence is the cutover: from then on the machine's identity is read
  from it before hub.json (`sminos.enrollment`, `sminos.machine_identity`,
  `sminos_daemon.enrolled_at`, `hub show`), and the daemon runs the uplink in
  RL10 mode only. `former` is this machine's own map of names to the
  sessions it held under them (is_self's evidence), copied from hub.json at
  the first welcome; a welcome that renames the machine adds the sessions
  held under the old name (`sminos_hub.sessions_under`) before the identity
  is replaced, and a former name the welcome lists that the file lacks is
  added with what `sessions_under` finds now. `cutover` is the first
  welcome's time and never moves; former's sessions only grow.
- The revocation set (`keep_revoked`, `revoked`): `daemon/revoked.json`
  ({version, devices, members, keys}, 0600), written whole from the first
  set after each welcome and merged into from each later `revoked` frame,
  by version: one older than the file is ignored and said once. Every
  deliverer reads it (M6); a file present but unreadable raises
  RevokedUnreadable, never reads as an empty set. An event's stored signer
  (`verified.signer`) is revoked when the set names its `keyId`, its
  `device` or its `member` (`signer_revoked`, `event_revoked`); a legacy
  signer names none of them.
"""

import json
import os
import queue
import re
import socket
import stat
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402

PROTOCOL = {"major": 1, "minor": 0}
FRAME_LIMIT = 1 << 20     # a line, either way, at most 1 MiB of UTF-8 (O10 §D); larger text goes as parts
DIAL_TIMEOUT = 5.0
WELCOME_WAIT = 10.0
WRITE_TIMEOUT = 30.0      # a write the endpoint does not take within this is a lost connection
READ_POLL = 0.25          # how often a blocked read looks up for a close from this end
TOKEN_RE = re.compile(r"[0-9a-fA-F]{64}")
IDENTITY_FILE = "identity.json"
REVOKED_FILE = "revoked.json"
REVOKED_SETS = ("devices", "members", "keys")
_SAID = {"find": None, "revoked": None}


def log(line):
    sminos.daemon_log("rl10: " + line)


# ------------------------------------------------------------- discovery


def path():
    """Where the endpoint's rl10.json is: SMINOS_RL10 (a test's), else under
    MAWS_USER_DATA, else O2's platform default."""
    forced = os.environ.get("SMINOS_RL10")
    if forced:
        return forced
    data = os.environ.get("MAWS_USER_DATA")
    if data:
        return os.path.join(data, "mawsd", "endpoint", "rl10.json")
    home = sminos.home_dir()
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support", "MAWS")
    else:
        base = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "MAWS")
    return os.path.join(base, "mawsd", "endpoint", "rl10.json")


def check():
    """(info, why): the endpoint rl10.json names — {socket, token, protocol,
    pid, build} — or None and why not; `why` is None when there is no file,
    the state of every machine without an endpoint."""
    where = path()
    try:
        fd = os.open(where, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, None
    except OSError as e:
        return None, "%s cannot be opened (%s)" % (where, e.strerror or e)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None, "%s is not a regular file" % where
        if stat.S_IMODE(st.st_mode) != 0o600:
            return None, "%s is mode %o, not 600" % (where, stat.S_IMODE(st.st_mode))
        if st.st_uid != os.getuid():
            return None, "%s is owned by uid %d, not this one (%d)" % (where, st.st_uid, os.getuid())
        with os.fdopen(fd, "rb", closefd=False) as f:
            raw = f.read(1 << 16)
    except OSError as e:
        return None, "%s cannot be read (%s)" % (where, e.strerror or e)
    finally:
        os.close(fd)
    try:
        d = json.loads(raw)
    except ValueError:
        return None, "%s is not JSON" % where
    if not isinstance(d, dict):
        return None, "%s is not a JSON object" % where
    if type(d.get("protocol")) is not int or d["protocol"] != PROTOCOL["major"]:
        return None, "%s speaks protocol %r, not %d" % (where, d.get("protocol"), PROTOCOL["major"])
    if not (isinstance(d.get("token"), str) and TOKEN_RE.fullmatch(d["token"])):
        return None, "%s has no token of 64 hex characters" % where
    if not (isinstance(d.get("socket"), str) and d["socket"]):
        return None, "%s names no socket" % where
    return {"socket": d["socket"], "token": d["token"], "protocol": d["protocol"], "pid": d.get("pid"),
            "build": d.get("build")}, None


def find():
    """The endpoint (check's info), or None; a file that names none is said
    once in daemon.log while it stays so (what it is not is never said for
    the token's sake: the token is never written anywhere)."""
    info, why = check()
    if why is not None and _SAID["find"] != why:
        _SAID["find"] = why
        log("no endpoint: %s" % why)
    elif why is None:
        _SAID["find"] = None
    return info


# ------------------------------------------------------------- the connection


class Refused(Exception):
    """The endpoint refused the hello, closed, or did not welcome in time."""


class Connection:
    """One RL10 socket: lines written whole (`write`) and read one at a time
    (`read_line`), each at most FRAME_LIMIT bytes and its newline. Reads poll
    READ_POLL so a `shut` from this end is seen; writes are bounded by
    WRITE_TIMEOUT in all."""

    def __init__(self, sock):
        self.sock = sock
        self.sock.settimeout(READ_POLL)
        self.buf = bytearray()
        self.closing = threading.Event()
        self.write_lock = threading.Lock()

    @classmethod
    def dial(cls, where, timeout=DIAL_TIMEOUT):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.connect(where)
        except BaseException:
            sock.close()
            raise
        return cls(sock)

    def write(self, data, timeout=WRITE_TIMEOUT):
        """Bytes written whole, or OSError (TimeoutError past `timeout`)."""
        deadline = time.monotonic() + timeout
        view = memoryview(data)
        with self.write_lock:
            while view:
                if self.closing.is_set():
                    raise OSError("the connection is closed from this end")
                try:
                    n = self.sock.send(view)
                except socket.timeout:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("the endpoint took no bytes for %gs" % timeout) from None
                    continue
                view = view[n:]

    def read_line(self, timeout=None):
        """The next line's text without its newline; None at the endpoint's
        close; TimeoutError past `timeout` (seconds, None: until a line, the
        close or a `shut`); ValueError for a line past FRAME_LIMIT."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            end = self.buf.find(b"\n")
            if end >= 0:
                line = bytes(self.buf[:end])
                del self.buf[:end + 1]
                if len(line) > FRAME_LIMIT:
                    raise ValueError("a line of %d bytes, past %d" % (len(line), FRAME_LIMIT))
                return line.decode("utf-8")
            if len(self.buf) > FRAME_LIMIT:
                raise ValueError("a line past %d bytes" % FRAME_LIMIT)
            if self.closing.is_set():
                raise OSError("the connection is closed from this end")
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("no line within %gs" % timeout)
            try:
                chunk = self.sock.recv(1 << 16)
            except socket.timeout:
                continue
            if not chunk:
                return None
            self.buf += chunk

    def handshake(self, hello, wait=WELCOME_WAIT):
        """`hello` written as the first line, and the welcome read: the first
        line back, a `welcome` frame, within `wait`; Refused otherwise."""
        try:
            self.write((json.dumps(hello, separators=(",", ":")) + "\n").encode("utf-8"))
            line = self.read_line(wait)
        except TimeoutError:
            raise Refused("no welcome within %gs" % wait) from None
        except (OSError, ValueError) as e:
            raise Refused(" ".join(str(e).split()) or type(e).__name__) from None
        if line is None:
            raise Refused("the endpoint closed the socket without a welcome (a token it does not hold?)")
        try:
            frame = json.loads(line)
        except ValueError:
            raise Refused("its first line is not JSON") from None
        if isinstance(frame, dict) and frame.get("t") == "refuse":
            raise Refused("the endpoint refused the hello: %s" % " ".join(str(frame.get("reason")).split())[:200])
        if not (isinstance(frame, dict) and frame.get("t") == "welcome"):
            raise Refused("its first line is no welcome")
        return frame

    def shut(self):
        """Ends the connection from this end: a read or write blocked in it
        returns within READ_POLL."""
        self.closing.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self):
        self.shut()
        self.sock.close()


def hello_frame(token, version, policy):
    """RL10's hello: the first line, carrying the token, this sminos's
    version, and the machine's policy as its file says (the endpoint takes it
    only when it holds none)."""
    return {"t": "hello", "protocol": dict(PROTOCOL), "capabilities": [], "token": token,
            "sminos": {"version": version}, "policy": policy}


class Reader(threading.Thread):
    """The connection's reader: each line read goes to `items` as ("frame",
    None, its text, when it was read: epoch s), the end as ("closed", why). It
    calls nothing of sminos, so the socket is drained whatever the main thread
    is doing."""

    def __init__(self, conn):
        super().__init__(name="rl10-reader", daemon=True)
        self.conn = conn
        self.items = queue.Queue()

    def run(self):
        try:
            while True:
                line = self.conn.read_line()
                if line is None:
                    self.items.put(("closed", "the endpoint closed the socket"))
                    return
                if line:
                    self.items.put(("frame", None, line, time.time()))
        except Exception as e:  # noqa: BLE001 — a close from this end, a line too long, a socket error
            self.items.put(("closed", "closed by this end" if self.conn.closing.is_set()
                            else " ".join(str(e).split()) or type(e).__name__))


# ------------------------------------------------------------- the identity


def identity_path():
    return os.path.join(sminos.root(), "daemon", IDENTITY_FILE)


def cut_over():
    """Whether this machine is cut over: identity.json is there, readable or
    not. Once it is, no DX2 uplink runs again; removing it undoes that."""
    return os.path.lexists(identity_path())


def valid_identity(d):
    """Whether a dict holds an identity's fields as identity.json keeps them."""
    return isinstance(d, dict) and all(isinstance(d.get(k), str) and d[k] for k in ("org", "hub", "name")) \
        and sminos.valid_name(d["name"]) and isinstance(d.get("former"), dict)


def cutover():
    """daemon/identity.json, or None when there is none (or it cannot be read
    as one)."""
    try:
        with open(identity_path()) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not valid_identity(d):
        return None
    d["former"] = {n: sorted(s for s in ss if isinstance(s, str) and s)
                   for n, ss in d["former"].items() if isinstance(n, str) and n and isinstance(ss, list)}
    return d


class NotEnrolled(ValueError):
    """A welcome whose identity is not whole: the endpoint is not enrolled
    (org-listed) yet, and nothing cuts over on it."""


def welcome_identity(frame):
    """A welcome's identity, checked: {org, hub, name, former: [names], ref,
    enrolled}, each of org, hub, name, ref and enrolled present. A welcome
    missing one is an endpoint not enrolled yet (NotEnrolled); ValueError
    naming anything else wrong."""
    proto = frame.get("protocol")
    if not (isinstance(proto, dict) and proto.get("major") == PROTOCOL["major"]):
        raise ValueError("a welcome of protocol %r, not %d" % (proto, PROTOCOL["major"]))
    ident = frame.get("identity")
    if not isinstance(ident, dict):
        raise NotEnrolled("a welcome without an identity: the endpoint is not enrolled")
    missing = [k for k in ("org", "hub", "name", "ref", "enrolled") if not (isinstance(ident.get(k), str) and ident[k])]
    if missing:
        raise NotEnrolled("a welcome whose identity has no %s: the endpoint is not enrolled" % ", ".join(missing))
    if not sminos.valid_name(ident["name"]):
        raise ValueError("a welcome whose identity names no machine sminos can write as")
    former = ident.get("former", [])
    if not (isinstance(former, list) and all(isinstance(n, str) and sminos.valid_name(n) for n in former)):
        raise ValueError("a welcome whose identity's former is not a list of names")
    return {"org": ident["org"], "hub": ident["hub"], "name": ident["name"], "former": list(former),
            "ref": ident["ref"], "enrolled": ident["enrolled"]}


def welcomed(frame):
    """The welcome's identity kept in daemon/identity.json, and returned as
    written. The first welcome cuts the machine over (`cutover` its time),
    and only a whole one does (NotEnrolled otherwise: nothing is written);
    a welcome naming the machine otherwise than this machine is named now is
    a rename the endpoint made, and the sessions held under the old name go
    into `former` first (is_self keeps them this machine's). ValueError for
    a welcome whose identity cannot be kept."""
    ident = welcome_identity(frame)
    hub_mod = sminos.sibling_module("sminos_hub")
    with hub_mod.credential_lock():
        held = cutover()
        if held is None:
            # The first welcome: the name and the former names are hub.json's
            # (or the host's), read before identity.json exists.
            sminos.forget_caches()
            local, former_now = sminos.machine_identity()
            former = {n: sorted(s) for n, s in former_now.items()}
            at = sminos.now()
        else:
            local, former, at = held["name"], held["former"], held.get("cutover") or sminos.now()
        if local != ident["name"]:
            former[local] = sorted(set(former.get(local, ())) | set(hub_mod.sessions_under(local)))
        for name in ident["former"]:
            if name not in former and name != ident["name"]:
                former[name] = sorted(hub_mod.sessions_under(name))
        former.pop(ident["name"], None)
        written = {"org": ident["org"], "hub": ident["hub"], "name": ident["name"], "former": former,
                   "ref": ident["ref"], "enrolled": ident["enrolled"], "cutover": at,
                   "build": frame.get("build") if isinstance(frame.get("build"), str) else ""}
        os.makedirs(os.path.dirname(identity_path()), mode=0o700, exist_ok=True)
        sminos.write_json(identity_path(), written, mode=0o600)
        if held is None or local != ident["name"] or held.get("enrolled") != ident["enrolled"]:
            # A new enrolment of this machine's name: its operator writer
            # waits for the endpoint's head of it (sminos.waits_for_head).
            sminos.mark_enrolled(ident["name"], ident["enrolled"])
    sminos.forget_caches()
    if held is None:
        log("cut over: this machine is %s of org %s through its endpoint from now on (%s)"
            % (ident["name"], ident["org"], identity_path()))
    if local != ident["name"]:
        log("the endpoint renamed this machine %s (it was %s); the sessions it held as %s stay its own"
            % (ident["name"], local, local))
    return written


def credential(identity):
    """What the uplink's Link runs on in RL10 mode: the identity's hub, org
    and name, and no key."""
    return {"hub": identity["hub"], "org": identity["org"], "machine": identity["name"], "key": None}


# ------------------------------------------------------------- the revocation set


class RevokedUnreadable(ValueError):
    """daemon/revoked.json is there and is not a revocation set: a deliverer
    must not read it as an empty one."""


def revoked_path():
    return os.path.join(sminos.root(), "daemon", REVOKED_FILE)


def revocation(d):
    """A revocation set as frames and the file carry it, checked: {version,
    devices, members, keys}, each set a list; None when it is not one."""
    if not (isinstance(d, dict) and type(d.get("version")) is int and d["version"] >= 0
            and all(isinstance(d.get(k), list) for k in REVOKED_SETS)):
        return None
    return {"version": d["version"], **{k: list(d[k]) for k in REVOKED_SETS}}


def revoked():
    """The revocation set this machine keeps: {version, devices, members,
    keys}, empty sets (version 0) when none was ever kept; RevokedUnreadable
    when the file is there and holds none."""
    try:
        with open(revoked_path()) as f:
            d = revocation(json.load(f))
    except FileNotFoundError:
        return {"version": 0, **{k: [] for k in REVOKED_SETS}}
    except (OSError, ValueError) as e:
        raise RevokedUnreadable("%s cannot be read: %s" % (revoked_path(), e)) from None
    if d is None:
        raise RevokedUnreadable("%s holds no revocation set" % revoked_path())
    return d


def union(a, b):
    """The entries of two lists, each once, a's order first."""
    seen, out = set(), []
    for x in list(a) + list(b):
        key = json.dumps(x, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def keep_revoked(frame, whole):
    """A revocation set from the endpoint kept in daemon/revoked.json:
    `whole` (the first after a welcome) replaces the file, a later one is
    merged into it; either only when its version is not older than the
    file's, else ignored and said once. Whether it was kept."""
    got = revocation(frame)
    if got is None:
        log("a revocation set that is not one: ignored")
        return False
    try:
        held = revoked()
    except RevokedUnreadable as e:
        log("%s: replaced by the endpoint's" % e)
        held, whole = None, True
    if held is not None and got["version"] < held["version"]:
        said = (got["version"], held["version"])
        if _SAID["revoked"] != said:
            _SAID["revoked"] = said
            log("a revocation set of version %d, older than the one kept (%d): ignored" % said)
        return False
    if whole or held is None:
        kept = got
    else:
        kept = {"version": got["version"], **{k: union(held[k], got[k]) for k in REVOKED_SETS}}
    os.makedirs(os.path.dirname(revoked_path()), mode=0o700, exist_ok=True)
    sminos.write_json(revoked_path(), kept, mode=0o600)
    return True


def signer_revoked(signer, revoked):
    """Whether a stored signer is in the revocation set: by its key id, its
    device or its member, whichever it names (a machine names a key alone,
    an older signer no key id, a legacy one nothing)."""
    if not isinstance(signer, dict):
        return False
    return any(isinstance(signer.get(field), str) and signer[field] in revoked[kind]
               for kind, field in (("keys", "keyId"), ("devices", "device"), ("members", "member")))


def event_revoked(e, revoked):
    """Whether a stored event's verdict (`verified`, which the uplink added
    as it took the event from the endpoint) names a revoked signer."""
    verified = e.get("verified")
    return isinstance(verified, dict) and signer_revoked(verified.get("signer"), revoked)
