#!/usr/bin/env python3
"""sminos_uplink — the machine's connection to the desk hub (DC4 of the desk).

`sminos daemon uplink` is its own process, which `daemon run` starts as a
child and restarts when it exits; at most one runs per $SMINOS_HOME
(`daemon/uplink.lock`), and it ends when its parent does (the parent names
itself at spawn, so one already gone at startup counts). It reads the
machine's credential (`daemon/hub.json`, written by enrollment; without it
nothing connects) and holds DX2's connection, opened outbound: the stream
down — `GET /machine/stream`, Server-Sent Events — and frames up by `POST
/machine/frames`, each under the stream's generation. A stream silent for
three heartbeat periods is dead; the uplink reconnects with backoff.

Three threads: a reader that only reads the stream (the SSE parse, no
sminos call) into a queue, so the stream is drained whatever the rest is
doing; beside it the stream's acker, which answers each heartbeat with
`hb-ack` (no sminos call either), so the machine's lease at the hub never
waits on the main thread; and the process's main thread, which does every
sminos call and every other POST. sminos's per-invocation caches are module
globals no second thread may share, and a git phase of the tick loop, a
derivation, or this process's own delivery never holds the reader up. The
main thread takes whatever is queued as one batch, then ticks once: what the
batch imported is delivered once per project, so a burst from the hub costs
a tick, not a tick a frame.

The hub sends the org's directory down the stream (`org`: every project of
the org, with its kind and whether it is retired, and every enrolled
machine); the uplink keeps it at daemon/org.json and registers every project
of it it does not know (root ""), so the machine follows every project of
its org. On every stream, for every hub project of this machine's org known
here (hub_projects), the uplink sends `hello` with its vector — `follow` when
the machine has no checkout of it and no session in it, and again whenever
that changes — and, for a project it holds, its machine's presence (DX4
`machine`), then uploads its own writers' suffix past the hub's `have`, and
from then on what they append; it follows `resend`, says each `refused` in
daemon.log, and imports what the hub sends (sminos_hublog.py: each event's
code verified before it enters the log, a refused one reported up as
`rejected`). Every archive period it says `hello` again for each project it
opened, one POST each, so the hub's answer — whether this machine writes the
project's git archive (sminos_archive.py) — is never older than a period,
even on a stream that never drops. The session plane
(sminos_plane.py) rides the same stream: each session's presence after the
`hello` and whenever it changes, and the hub's subscriptions served as DX4
messages; a bridge's reader wakes the main thread, so what it read goes up
at once. The machine's policy (sminos_policy) goes up in `machine` on every
connect and again whenever it changes; the requests the bridges raise and
settle go up as DX4 `raised` and `settled` with their codes, and the
complete pending set after every connect (sminos_requests); what
delivery made of each event from outside, as DX4 `delivery`
(sminos_outcomes); and the RPCs the hub forwards, verified, executed at most
once, and answered as `rpc-result` until `rpc-ack` (sminos_rpc). A POST the
hub does not answer 200 ends the stream, and the next one redoes the
handshake: nothing posted is taken as landed without its answer. Frames
larger than a frame's bound travel as parts, both ways.
"""

import errno
import fcntl
import http.client
import itertools
import json
import os
import queue
import selectors
import signal
import socket
import ssl
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_archive as archive  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_plane as plane  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_requests as requests  # noqa: E402
import sminos_rpc as rpc  # noqa: E402

STREAM_PATH = "/machine/stream"
FRAMES_PATH = "/machine/frames"
HEARTBEAT_MS = 15000      # DX2's, until the stream's welcome says otherwise
SILENT_PERIODS = 3        # a stream silent this many heartbeats is dead
BACKOFF_MAX = 60
POLL = 0.25               # how often the main thread looks up from an idle stream
DRAIN_FRAMES = 1000       # what is queued is handled as one batch, then one tick: at most this many items
DRAIN_FOR = 1.0           # or this long of handling, so a burst neither starves the tick nor holds delivery
LINE_MAX = 2 << 20        # a frame is at most 1 MiB (DX2); its SSE line, a little more
LOOPBACK = ("127.0.0.1", "::1", "localhost")
FRAME_LIMIT = 1 << 20     # every frame, either way, at most 1 MiB of UTF-8 (DX2); a larger one goes as parts
POST_LIMIT = 4 << 20      # a POST's body
POST_TIMEOUT = 30
STAGGER = 0.25            # RFC 8305's connection attempt delay: the next address is tried this long after the last
ANSWER_MAX = 1 << 16
ACK_GAP = 1.0             # heartbeats are answered at most once a second, the newest: a burst is answered once
SCAN_EVERY = 2.0          # how often the projects known here are looked over for a hub project to open
UPLOAD_EVERY = 0.5        # how often this machine's writers are looked at for events to upload
CHECKOUTS_EVERY = 10.0    # how often the machine presence's checkouts are read again (the policy: every scan)


class CredentialBad(Exception):
    """daemon/hub.json is unreadable or incomplete."""


def credential_path():
    return daemon.daemon_path("hub.json")


def hub_admitted(hub):
    """Whether a hub URL may carry the service token: https, or http on this
    machine only (DX7's local runtime) — the token travels in every request."""
    try:
        url = urllib.parse.urlsplit(hub)
        url.port  # noqa: B018 — a port that is no number is no URL
    except ValueError:
        return False
    return bool(url.hostname) and (url.scheme == "https" or (url.scheme == "http" and url.hostname in LOOPBACK))


def load_credential():
    """The machine's credential, `key` decoded; None when there is none (no
    enrollment). A hub reached over http must be on this machine (DX7's local
    runtime): the service token travels in every request."""
    try:
        with open(credential_path()) as f:
            d = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise CredentialBad("%s is unreadable: %s" % (credential_path(), e))
    fields = ("hub", "org", "machine", "client_id", "client_secret", "key")
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) and d[k] for k in fields):
        raise CredentialBad("%s lacks one of %s" % (credential_path(), ", ".join(fields)))
    key = codes.b64url_bytes(d["key"], 32)
    if key is None:
        raise CredentialBad("%s: the org key is not 32 bytes of base64url" % credential_path())
    if not hub_admitted(d["hub"]):
        raise CredentialBad("%s: the hub %s is neither https nor on this machine" % (credential_path(), d["hub"]))
    return {**d, "key": key}


def log(line):
    sminos.daemon_log("uplink: " + line)


def dial(address, timeout, source_address=None):
    """A TCP socket connected to address, (host, port), by RFC 8305's
    essentials (Happy Eyeballs): the resolved addresses interleaved by family,
    the next attempt started STAGGER after the last while earlier ones are
    still pending (at once when one fails), the first to connect taken and the
    rest closed. http.client dials with socket.create_connection, which tries
    one address after another with the whole timeout each: where IPv6
    resolves first and is dropped on the way (a global IPv6 address on a
    network that blackholes it), a connect waited out a timeout per IPv6
    address before it tried IPv4 — longer than a POST's deadline. The whole
    connect is bounded by `timeout` (seconds), the socket's I/O bound once
    connected. http.client's source_address is never set here."""
    host, port = address
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    first = [i for i in infos if i[0] == infos[0][0]]
    other = [i for i in infos if i[0] != infos[0][0]]
    todo = [i for pair in itertools.zip_longest(first, other) for i in pair if i]
    deadline = time.monotonic() + timeout
    attempts, failed = selectors.DefaultSelector(), []
    try:
        next_at = time.monotonic()
        while todo or attempts.get_map():
            now = time.monotonic()
            if now >= deadline:
                raise TimeoutError("no connection to %s port %s within %gs%s" % (
                    host, port, timeout, " (%s)" % "; ".join(failed) if failed else ""))
            if todo and now >= next_at:
                family, kind, proto, _, addr = todo.pop(0)
                try:
                    sock = socket.socket(family, kind, proto)
                except OSError as e:
                    failed.append("%s: %s" % (addr[0], e.strerror or e))
                    continue
                sock.setblocking(False)
                err = sock.connect_ex(addr)
                if err not in (0, errno.EINPROGRESS):
                    failed.append("%s: %s" % (addr[0], os.strerror(err)))
                    sock.close()
                    continue
                attempts.register(sock, selectors.EVENT_WRITE, addr)
                next_at = now + STAGGER
            wait = deadline - now if not todo else min(deadline, next_at) - now
            for key, _ in attempts.select(max(wait, 0)):
                sock = key.fileobj
                attempts.unregister(sock)
                err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if err == 0:
                    sock.settimeout(timeout)
                    return sock
                failed.append("%s: %s" % (key.data[0], os.strerror(err)))
                sock.close()
                next_at = time.monotonic()
        raise OSError("no connection to %s port %s: %s" % (host, port, "; ".join(failed) or "no address"))
    finally:
        for key in list(attempts.get_map().values()):
            key.fileobj.close()
        attempts.close()


class HTTPConnection(http.client.HTTPConnection):
    """http.client's connection, dialled by `dial`; TLS, its SNI and its
    certificate checks stay http.client's own."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = dial


class HTTPSConnection(HTTPConnection, http.client.HTTPSConnection):
    pass


def connection(cred, timeout):
    url = urllib.parse.urlsplit(cred["hub"])
    if url.scheme == "https":
        return HTTPSConnection(url.hostname, url.port, timeout=timeout, context=ssl.create_default_context())
    return HTTPConnection(url.hostname, url.port, timeout=timeout)


def admission(cred):
    return {"CF-Access-Client-Id": cred["client_id"], "CF-Access-Client-Secret": cred["client_secret"]}


# ------------------------------------------------------------- the stream


def sse_events(fp):
    """(event, data) for each event of a Server-Sent Events body; comments and
    other fields are skipped, several data lines joined by line feeds."""
    event, data = "", []
    while True:
        raw = fp.readline(LINE_MAX)
        if not raw:
            return
        if not raw.endswith(b"\n"):
            raise ValueError("a stream line past %d bytes, or a body cut mid-line" % LINE_MAX)
        line = raw.rstrip(b"\r\n").decode("utf-8")
        if not line:
            if data:
                yield event, "\n".join(data)
            event, data = "", []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)


def heartbeat_at(data):
    """The `at` of an `hb` event's data; None when it is no hb frame."""
    try:
        frame = json.loads(data)
    except ValueError:
        return None
    if not (isinstance(frame, dict) and frame.get("t") == "hb"):
        return None
    return frame["at"] if isinstance(frame.get("at"), str) else ""


class Stream(threading.Thread):
    """One connection's reader: everything it reads goes to `items` as
    ("frame", event, data, when it was read: epoch s), and its end as
    ("closed", why), but for the
    `org` frame, the latest of which waits aside (take_org) for the main
    thread to handle ahead of what is queued: it is the whole directory, and
    nothing queued depends on its order. It calls nothing of sminos.

    The heartbeats are answered here, not on the main thread: the hub renews
    the machine's lease only with an `hb-ack` of the stream's generation, and
    the main thread can be held far longer than the lease — a slow tick, a
    POST the hub holds, a frame that reads a large transcript, a backlog of
    frames queued ahead of the heartbeat. The reader hands each `hb` to the
    stream's acker, a thread that posts the answer and touches nothing of
    sminos, so the lease lasts exactly as long as the stream and this process
    do. A POST of an answer the hub does not take ends the stream, as any
    POST's does."""

    def __init__(self, cred, ended=lambda: False):
        super().__init__(name="uplink-reader", daemon=True)
        self.cred = cred
        self.ended = ended
        self.items = queue.Queue()
        self.org_lock = threading.Lock()
        self.org = None           # the latest `org` frame read and not yet taken (take_org)
        self.conn = None
        self.sock = None
        self.closing = threading.Event()
        self.generation = None    # the welcome's, once read
        self.beats = queue.Queue()  # the `at` of each heartbeat, for the acker; None ends it

    def connect(self):
        self.conn = connection(self.cred, SILENT_PERIODS * HEARTBEAT_MS / 1000)
        path = urllib.parse.urlsplit(self.cred["hub"]).path.rstrip("/") + STREAM_PATH
        self.conn.request("GET", path, headers={"Accept": "text/event-stream", "Cache-Control": "no-cache",
                                                **admission(self.cred)})
        # Held here: a response that ends with its connection (HTTP/1.0, or
        # Connection: close) takes the socket from `conn`, which forgets it.
        self.sock = self.conn.sock
        return self.conn.getresponse()

    def run(self):
        try:
            resp = self.connect()
            if resp.status != 200:
                body = resp.read(300).decode("utf-8", "replace")
                self.items.put(("closed", "the hub answered %d %s" % (resp.status, " ".join(body.split()))))
                return
            threading.Thread(target=self.ack, name="uplink-acker", daemon=True).start()
            for event, data in sse_events(resp):
                # DX2 names each event by its frame's `t`.
                if event == "hb" and self.generation is not None:
                    at = heartbeat_at(data)
                    if at is not None:
                        self.beats.put(at)
                        continue
                elif event == "welcome":
                    self.welcomed(data)
                elif event == "org":
                    # The whole directory, each frame replacing the last: kept
                    # aside for the main thread to take ahead of the queue
                    # (take_org), the item only waking it.
                    with self.org_lock:
                        self.org = data
                    self.items.put(("org",))
                    continue
                self.items.put(("frame", event, data, time.time()))
            self.items.put(("closed", "the hub ended the stream"))
        except Exception as e:  # noqa: BLE001 — a connection closed from this end raises from deep inside http.client
            self.items.put(("closed", "closed by this end" if self.closing.is_set() else str(e) or repr(e)))
        finally:
            self.beats.put(None)

    def welcomed(self, data):
        """The stream's generation, which every answer names, and its read
        bound once its own heartbeat is known."""
        try:
            frame = json.loads(data)
        except ValueError:
            return
        if not isinstance(frame, dict):
            return
        generation, beat = frame.get("generation"), frame.get("heartbeat_ms")
        self.generation = generation if type(generation) is int else None
        beat = beat if type(beat) is int and beat > 0 else HEARTBEAT_MS
        if self.sock is not None:
            self.sock.settimeout(SILENT_PERIODS * beat / 1000)

    def ack(self):
        """The acker: answers the newest heartbeat queued, at most once an
        ACK_GAP (a burst is answered once), until the stream ends."""
        last = 0.0
        while True:
            at = self.beats.get()
            if at is None:
                return
            gap = last + ACK_GAP - time.monotonic()
            if gap > 0 and self.closing.wait(gap):
                return
            while True:
                try:
                    newer = self.beats.get_nowait()
                except queue.Empty:
                    break
                if newer is None:
                    return
                at = newer
            last = time.monotonic()
            try:
                post(self.cred, self.generation, [{"t": "hb-ack", "generation": self.generation, "at": at}],
                     lambda: self.ended() or self.closing.is_set())
            except Stopping:
                return
            except NotDelivered as e:
                self.items.put(("closed", "an hb-ack was not delivered (%s)" % e))
                self.shut()
                return

    def take_org(self):
        """The latest `org` frame's data not yet taken, or None."""
        with self.org_lock:
            data, self.org = self.org, None
        return data

    def shut(self):
        self.closing.set()
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self):
        self.shut()
        if self.conn:
            self.conn.close()


# ------------------------------------------------------------- frames on the wire


def wire_text(frame):
    """A frame's JSON text, one line. A string UTF-8 cannot carry (a lone
    surrogate a lying hub sent, echoed in a report) is written escaped."""
    text = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = json.dumps(frame, separators=(",", ":"))
    return text


def escaped_size(ch):
    """The UTF-8 bytes a character of a frame's text takes once that text is
    a JSON string itself (a part's `data`)."""
    c = ord(ch)
    if ch in ('"', "\\"):
        return 2
    if c < 0x20:
        return 6
    if c < 0x80:
        return 1
    if c < 0x800:
        return 2
    return 4 if c > 0xFFFF else 3


def to_wire(frame, limit=FRAME_LIMIT):
    """The lines a frame travels as (DX2): its JSON text when within `limit`
    bytes, else `part` frames, each a slice of that text (parts.ts's toWire;
    a Python str holds whole code points, so no slice splits a pair)."""
    text = wire_text(frame)
    if len(text.encode("utf-8")) <= limit:
        return [text]
    pid = codes.b64url(os.urandom(codes.NONCE_BYTES))
    budget = limit - len(wire_text({"t": "part", "id": pid, "index": 999999999, "count": 999999999, "data": ""}))
    slices, start, used = [], 0, 0
    for i, ch in enumerate(text):
        cost = escaped_size(ch)
        if used + cost > budget:
            slices.append(text[start:i])
            start, used = i, 0
        used += cost
    slices.append(text[start:])
    return [wire_text({"t": "part", "id": pid, "index": i, "count": len(slices), "data": data})
            for i, data in enumerate(slices)]


class Parts:
    """Joins `part` sets (parts.ts's PartAssembler): `add` returns the whole
    frame once its set is complete, in whatever order its parts came, and
    None before; ValueError for a malformed part."""

    def __init__(self):
        self.sets = {}

    def add(self, part):
        pid, index, count, data = part.get("id"), part.get("index"), part.get("count"), part.get("data")
        if not (isinstance(pid, str) and isinstance(data, str) and type(index) is int and type(count) is int
                and 0 <= index < count):
            raise ValueError("a malformed part")
        held = self.sets.setdefault(pid, {"count": count, "slices": {}})
        if held["count"] != count:
            raise ValueError("a part whose count differs within its set")
        held["slices"][index] = data
        if len(held["slices"]) < count:
            return None
        del self.sets[pid]
        return codes.loads("".join(held["slices"][i] for i in range(count)))


class EndStream(Exception):
    """This stream is done with: the next one starts over with `hello`."""


class NotDelivered(EndStream):
    """A POST the hub did not answer 200: nothing in it may be taken as landed."""


class Stopping(EndStream):
    """The uplink is ending (SIGTERM, or its daemon is gone) while it posts."""


def post(cred, generation, frames, ended=lambda: False):
    """Frames up (DX2's POST): NDJSON, each body at most POST_LIMIT bytes,
    under the stream's generation. NotDelivered unless the hub answers 200 —
    a POST of an older stream is refused stale-generation, and a hub whose
    replies failed to reach the stream answers something else. The hub holds
    its answer until its replies are on the stream, so each exchange is
    watched: Stopping, within POLL, once `ended()` (and before each body)."""
    bodies, body, size = [], [], 0
    for line in (line.encode("utf-8") for frame in frames for line in to_wire(frame)):
        if body and size + len(line) + 1 > POST_LIMIT:
            bodies.append(body)
            body, size = [], 0
        body.append(line)
        size += len(line) + 1
    if body:
        bodies.append(body)
    path = urllib.parse.urlsplit(cred["hub"]).path.rstrip("/") + FRAMES_PATH
    for lines in bodies:
        if ended():
            raise Stopping("the uplink is ending")
        status, answer = exchange(cred, path, generation, b"\n".join(lines) + b"\n", ended)
        if status != 200:
            raise NotDelivered("the hub answered %d %s" % (
                status, " ".join(answer.decode("utf-8", "replace").split())[:300]))


def exchange(cred, path, generation, body, ended):
    """One POST, (status, answer): the whole HTTP exchange — connect, the
    body sent, the head and the answer read — runs on a thread of its own,
    and this one watches it. Once `ended()`, within POLL whichever step it is
    blocked in, its socket is shut and Stopping raised (the exchange's
    thread, a daemon, dies with the process that is ending); NotDelivered on
    any failure, or when it outlasts twice the socket bound (a hub that
    answers a byte at a time)."""
    out = {}

    def run():
        conn = out["conn"] = connection(cred, POST_TIMEOUT)
        try:
            conn.request("POST", path, body=body, headers={
                "Content-Type": "application/x-ndjson", "X-Desk-Generation": str(generation), **admission(cred)})
            resp = conn.getresponse()
            out["answer"] = (resp.status, resp.read(ANSWER_MAX))
        except (OSError, http.client.HTTPException) as e:
            out["error"] = " ".join(str(e).split()) or type(e).__name__
        finally:
            conn.close()

    worker = threading.Thread(target=run, name="uplink-post", daemon=True)
    worker.start()
    deadline = time.time() + 2 * POST_TIMEOUT
    while True:
        worker.join(POLL)
        if not worker.is_alive():
            break
        late = time.time() > deadline
        if ended() or late:
            sock = out["conn"].sock if out.get("conn") else None
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            if late:
                raise NotDelivered("no whole answer within %ds" % (2 * POST_TIMEOUT))
            raise Stopping("the uplink is ending during a POST")
    if "error" in out:
        raise NotDelivered(out["error"])
    return out["answer"]


# ------------------------------------------------------------- the projects


def hub_projects(cred):
    """{project id: project} of every project known here registered as one of
    this machine's org's (its project.json's hub names the org), rooted or
    not, but those the org's directory marks retired. Whether a root's .smns
    still names the project decides only whether this machine holds or
    follows it (Link.holds): the org's directory, not a checkout's file, says
    which projects exist, and a .smns edit on one checkout must not strand the
    retirements it causes."""
    out = {}
    for p in sminos.known_projects():
        if p.id in out or not (isinstance(p.hub, dict) and p.hub.get("org") == cred["org"]) \
                or sminos.org_retired(p.id):
            continue
        fresh = sminos.resolve_project(p.root) if p.root and os.path.isdir(p.root) else None
        out[p.id] = fresh if fresh is not None and fresh.id == p.id else p
    return out


def register_own(cred):
    """This machine's own project registered here (project.json), so it is
    hello'ed on every stream whether or not the hub has listed it yet — the
    hello is what registers it at a hub this machine enrolled at before
    machine projects existed."""
    sminos.project_path(sminos.machine_project(cred["org"], cred["machine"]), "log")


def keep_org(frame, cred):
    """The hub's `org` frame kept at daemon/org.json (its projects and
    machines, and when it came), and every project it names that is not
    retired and not known here registered as a followed one: the five fields
    project_path writes, root "", the hub the enrollment's. Whether the frame
    was one to keep."""
    projects, machines = frame.get("projects"), frame.get("machines")
    if not (isinstance(projects, list) and isinstance(machines, list)):
        return False
    projects = [p for p in projects if isinstance(p, dict) and isinstance(p.get("id"), str)
                and sminos.valid_name(p["id"]) and isinstance(p.get("name"), str) and p["name"].strip()
                and "\n" not in p["name"] and p.get("kind") in ("hub", "machine") and isinstance(p.get("retired"), bool)]
    machines = [m for m in machines if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"]
                and isinstance(m.get("online"), bool) and (m.get("seen") is None or isinstance(m.get("seen"), str))]
    path = sminos.org_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    sminos.write_json(path, {"projects": projects, "machines": machines, "at": sminos.now(ms=True)})
    hub = {"url": cred["hub"], "org": cred["org"]}
    for p in projects:
        if not p["retired"]:
            sminos.register_if_absent(sminos.make_project(p["id"], p["name"], "", "", hub))
    sminos.forget_caches()
    return True


def hub_project(pid, cred):
    """The project a frame names, when this machine knows it and its .smns
    names a hub of this machine's org; else None."""
    if not (isinstance(pid, str) and sminos.valid_name(pid)):
        return None
    return hub_projects(cred).get(pid)


# ------------------------------------------------------------- one stream


class Here:
    """What the uplink knows of this machine, as an RPC's checks ask it
    (sminos_rpc), on the main thread."""

    def __init__(self, link):
        self.link = link

    def project(self, pid):
        return hub_project(pid, self.link.cred)

    def has_session(self, project, sid):
        plane_ = self.link.plane
        if sid not in plane_.here.get(project.id, {}):
            sminos.forget_caches()
            plane_.refresh(project)
        return sid in plane_.here.get(project.id, {})

    def record(self, sid):
        plane_ = self.link.plane
        plane_.live = plane_.records.scan()
        return plane_.live.get(sid) if plane_.running(sid) else None

    def checkouts(self, project):
        return policy.known_checkouts(project)

    def cwd(self, project, sid):
        """The working directory the session joined the project from here."""
        return self.link.plane.here.get(project.id, {}).get(sid) or ""


class Link:
    """One stream's conversation with the hub. Frames down are dispatched by
    `t`: the log plane's here, the session plane's to `self.plane`, the RPCs
    to `self.rpcs`. Frames up are posted under
    the stream's generation, and a POST not answered 200 ends the stream: the
    next one redoes the handshake, which is idempotent, rather than assume
    anything landed. `wake` asks the main thread for a tick now."""

    def __init__(self, cred, logs, ended=lambda: False, wake=lambda: None, bridges=None, reqs=None, rpcs=None):
        self.cred = cred
        self.ended = ended
        self.logs = logs          # project id → HubLog, kept across streams
        self.generation = None
        self.opened = set()       # the projects `hello`ed on this stream
        self.parts = Parts()
        self.next_scan = self.next_upload = 0.0
        self.next_confirm = 0.0   # when the opened projects are `hello`ed again (sminos_archive)
        self.nudge = daemon.nudged_at()
        self.passed = set()
        self.received = None      # when the reader took the frame being dispatched (epoch s), when known
        self.failing = self.plane_failing = ""
        self.plane = plane.Plane(cred["machine"], wake, bridges)
        self.requests = reqs or requests.Requests(cred["key"], cred["machine"])  # kept across streams by the uplink
        self.requests.wake = wake
        self.rpcs = rpcs or rpc.Rpcs(cred["key"], cred["machine"])  # kept across streams by the uplink
        self.rpcs.wake = wake
        self.machine_sent = {}    # project id → the `machine` body last posted on this stream
        self.next_checkouts = 0.0
        self.own = sminos.machine_project_id(cred["org"], cred["machine"])  # always held: its strays are its members
        self.follows = {}         # project id → whether its last `hello` on this stream said `follow`
        self.checkouts = {}       # project id → whether it had a known checkout here when last read
        self.imported = {}        # project id → HubLog: imports not yet delivered (deliver_imports)
        self.handlers = {"welcome": self.on_welcome, "hb": self.on_hb, "have": self.on_have,
                         "events": self.on_events, "resend": self.on_resend, "refused": self.on_refused,
                         "part": self.on_part, "subscribe": self.on_subscribe, "unsubscribe": self.on_unsubscribe,
                         "rows": self.on_rows, "diff": self.on_diff, "output": self.on_output, "rpc": self.on_rpc,
                         "rpc-ack": self.on_rpc_ack, "org": self.on_org}

    def post(self, frames):
        post(self.cred, self.generation, frames, self.ended)

    def post_session(self, messages):
        if messages:
            self.post([plane.frame(m) for m in messages])

    def close(self):
        self.plane.close()

    def dispatch(self, frame, stream):
        t = frame.get("t") if isinstance(frame, dict) else None
        if t not in ("events", "hb", "part", "org"):
            # Whatever this frame does comes after what the events before it
            # imported reached their members, as the frames came.
            self.deliver_imports()
        handler = self.handlers.get(t)
        if handler is None:
            if t not in self.passed:
                self.passed.add(t)
                log("%r frames are not handled here yet: passed by" % (t,))
            return
        try:
            handler(frame, stream)
        except EndStream:
            raise
        except (Exception, SystemExit) as e:  # noqa: BLE001 — one frame's failure is not the stream's
            log("handling a %r frame failed: %r" % (t, e))

    def log_of(self, pid, known=None):
        """The HubLog of a project known here as a hub project of this org, or None."""
        project = (known or {}).get(pid) or hub_project(pid, self.cred)
        if project is None:
            return None
        hl = self.logs.get(pid)
        if hl is None:
            hl = self.logs[pid] = hublog.HubLog(project, self.cred)
        hl.project = project
        return hl

    # ---------------------------------------------------- frames down

    def on_welcome(self, frame, stream):
        generation = frame.get("generation")
        self.generation = generation if type(generation) is int else None
        self.opened.clear()
        self.machine_sent.clear()
        self.follows.clear()
        self.checkouts.clear()
        for hl in self.logs.values():
            hl.reset()
        self.plane.close()
        self.rpcs.reset()
        self.next_scan = 0.0
        self.next_confirm = time.time() + archive.archive_every()
        log("connected to %s as %s (stream %s)" % (self.cred["hub"], frame.get("machine"), generation))

    def on_hb(self, _frame, _stream):
        """Answered by the stream's acker (Stream), never here."""

    def on_have(self, frame, _stream):
        hl = self.logs.get(frame.get("project"))
        if hl is not None and hl.project.id in self.opened:
            hl.on_have(frame)
            self.upload(hl)

    def on_events(self, frame, _stream):
        # A project open on this stream as the tick last registered it: each
        # frame of a burst looking every project over again (hub_projects)
        # was most of an import's cost, and an `org` frame taken ahead of the
        # queue must not drop the events the hub sent before it.
        pid = frame.get("project")
        hl = self.logs[pid] if isinstance(pid, str) and pid in self.opened else self.log_of(pid)
        if hl is None:
            log("events for project %r, which is no hub project of org %s known here: ignored"
                % (frame.get("project"), self.cred["org"]))
            return
        appended, rejections = hl.take(frame.get("events"))
        if appended:
            self.imported[hl.project.id] = hl
        if rejections and hl.project.id in self.opened:
            self.post(rejections)
            hl.reported(rejections)

    def on_resend(self, frame, _stream):
        hl = self.logs.get(frame.get("project"))
        if hl is not None and hl.project.id in self.opened:
            hl.on_resend(frame)
            self.upload(hl)

    def on_refused(self, frame, _stream):
        hl = self.logs.get(frame.get("project"))
        if hl is None:
            log("the hub refused: %s" % json.dumps(frame.get("refusal"), ensure_ascii=False)[:300])
            return
        hl.on_refused(frame)
        if hl.have is None and hl.project.id in self.opened:
            self.opened.discard(hl.project.id)
            self.open(hl)

    def on_part(self, frame, stream):
        whole = self.parts.add(frame)
        if whole is not None:
            self.dispatch(whole, stream)

    def opened_project(self, frame):
        """The project a session-plane frame names, when this stream opened
        it; else None (said in daemon.log)."""
        pid = frame.get("project")
        if pid in self.opened:
            return self.logs[pid].project
        log("a %r frame for project %r, not open on this stream: passed by" % (frame.get("t"), pid))
        return None

    def on_subscribe(self, frame, _stream):
        project = self.opened_project(frame)
        if project is not None:
            self.post_session(self.plane.subscribe(project, frame, self.received))

    def on_unsubscribe(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.unsubscribe(frame.get("sub")))

    def on_rows(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.rows(frame))

    def on_diff(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.diff(frame))

    def on_output(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.output(frame))

    def on_rpc(self, frame, _stream):
        self.rpcs.receive(frame.get("rpc"), Here(self), self.received)

    def on_rpc_ack(self, frame, _stream):
        self.rpcs.ack(frame)

    def on_org(self, frame, _stream):
        """The org's directory: kept, every project of it registered, and
        the projects looked over at once — a new one is followed, a retired
        one leaves (tick)."""
        if not keep_org(frame, self.cred):
            log("an org frame without its projects and machines: passed by")
            return
        self.next_scan = 0.0

    def deliver_imports(self):
        """What the frames handled since the last call imported, delivered
        once per project (sminos_hublog's `deliver`: a fresh read of the
        whole log), then the tick loop nudged once. The nudge is the tick
        loop's and every sender's: this uplink takes its own as seen, so
        what it imported costs its next tick no project scan, only the upload
        pass that sends what delivery made of it (`deliveries`)."""
        if not self.imported:
            return
        imported, self.imported = self.imported, {}
        for hl in imported.values():
            try:
                hl.deliver()
            except (Exception, SystemExit) as e:  # noqa: BLE001 — the daemon's tick delivers what is still owed
                log("delivering what was imported into %s failed: %r" % (hl.project.name, e))
        seen = daemon.nudged_at() == self.nudge
        sminos.nudge_daemon()
        if seen:
            # Only when no sender's nudge was waiting: that one is still this
            # uplink's to answer with a scan.
            self.nudge = daemon.nudged_at()
        self.next_upload = 0.0

    # ---------------------------------------------------- frames up

    def holds(self, pid):
        """Whether this machine holds the project rather than follows it: its
        own machine project, or one with a local member (the plane's) or a
        known checkout here (as last read)."""
        return pid == self.own or bool(self.plane.members.get(pid)) or self.checkouts.get(pid, False)

    def open(self, hl):
        """`hello` for a project on this stream, with what DX2 republishes
        after every connect that is this child's — the machine's presence,
        for a project it holds — and the rejections not yet reported. A
        project it neither has a checkout of nor a session in is opened to
        follow (`follow`): no machine presence, and no session presence but
        the leavers'. A live member that joined under a former name of this
        machine joins again first, so the vector and the upload carry it."""
        hl.rejoin_former()
        unreported = hl.unreported()
        self.plane.refresh(hl.project)
        machine = hl.presence()
        self.checkouts[hl.project.id] = bool(machine["message"]["body"]["checkouts"])
        follow = not self.holds(hl.project.id)
        sessions = [plane.frame(m) for m in self.plane.presence(hl.project.id, force=True)]
        # The project's bridges are followed before its set is drawn up: the
        # set goes now if they are read, else once they are (Requests.due).
        self.requests.follow(self.bridged(self.opened | {hl.project.id}))
        self.requests.take()
        owed = self.requests.opening(hl.project.id)
        results = self.rpcs.opening(hl.project.id)
        self.post([hl.hello(follow)] + ([] if follow else [machine]) + sessions + unreported + owed + results)
        self.plane.accepted(hl.project.id)   # the hub took the leavers' presence: only later ones are said again
        self.opened.add(hl.project.id)
        self.follows[hl.project.id] = follow
        if not follow:
            self.machine_sent[hl.project.id] = machine["message"]["body"]
        hl.reported(unreported)
        self.requests.sent(owed)
        self.rpcs.sent(results)
        self.deliveries(hl)

    def upload(self, hl):
        for frame, reach in hl.uploads():
            self.post([frame])
            hl.took(reach)

    def deliveries(self, hl):
        """What delivery made of the events from outside, as DX4 `delivery`
        messages sealed as they go; dropped from the outbox once the hub
        answered the POST that carried them."""
        box = outcomes.Outbox(hl.project)
        if not box.waiting():
            return
        records, lines = box.take()
        frames = [f for f in (outcomes.message(self.cred["key"], self.cred["machine"], hl.project.id, r)
                              for r in records) if f is not None]
        if frames:
            self.post(frames)
        box.drop(lines)

    def machine_presence(self, now):
        """Each open project held or followed, as it is now, and the machine's
        presence in each it holds. At every scan a project whose local members
        came or went is hello'ed again — `follow` as it is now — with the
        machine's presence when it is held now (a follower posts none: the hub
        drops it); the checkouts are read again every CHECKOUTS_EVERY, or at
        once when the policy changed (a `daemon policy` nudges one), and
        `machine` goes again for each held project whose body changed."""
        current = policy.machine_policy()
        fresh = now >= self.next_checkouts or any(self.machine_sent.get(pid, {}).get("policy") != current
                                                  for pid in self.opened if not self.follows.get(pid))
        if fresh:
            self.next_checkouts = now + CHECKOUTS_EVERY
        for pid in sorted(self.opened):
            hl = self.logs[pid]
            machine = None
            if fresh:
                machine = hl.presence()
                self.checkouts[pid] = bool(machine["message"]["body"]["checkouts"])
            follow = not self.holds(pid)
            if follow != self.follows.get(pid):
                frames = [hl.hello(follow)]
                if not follow:
                    machine = machine or hl.presence()
                    frames.append(machine)
                self.post(frames)
                self.follows[pid] = follow
                if follow:
                    self.machine_sent.pop(pid, None)
                else:
                    self.machine_sent[pid] = machine["message"]["body"]
                log("%s: %s" % (hl.project.name, "followed (no checkout and no session here)" if follow else
                                "held (a checkout or a session here)"))
            elif not follow and machine is not None and machine["message"]["body"] != self.machine_sent.get(pid):
                self.post([machine])
                self.machine_sent[pid] = machine["message"]["body"]

    def bridged(self, pids):
        """{session: project id}: the members of these projects with a bridge
        endpoint here, whose requests are read: one listing of the bridges'
        directory, every POLL, rather than a look per member."""
        socks = plane.bridge_socks()
        return {sid: pid for pid in pids for sid in self.plane.members.get(pid, ()) if sid in socks}

    def relay_requests(self):
        """The requests of the open projects' bridged sessions: readers for
        them, and what they read, up."""
        self.requests.follow(self.bridged(self.opened))
        self.requests.take()
        frames = self.requests.due(self.opened)
        if frames:
            self.post(frames)
            self.requests.sent(frames)

    def relay_rpcs(self):
        """The RPCs' results and their compactions' progress, up."""
        self.rpcs.compacted(self.requests.take_compacts())
        frames = self.rpcs.due(self.opened)
        if frames:
            self.post(frames)
            self.rpcs.sent(frames)

    def tick(self):
        """Between frames: new hub projects opened, and what this machine's
        writers appended uploaded — at once when a sender nudged the daemon."""
        if self.generation is None:
            return
        now = time.time()
        nudge = daemon.nudged_at()
        nudged, self.nudge = nudge != self.nudge, nudge
        try:
            if now >= self.next_scan or nudged:
                self.next_scan = now + SCAN_EVERY
                sminos.forget_caches()
                register_own(self.cred)
                known = hub_projects(self.cred)
                gone = sorted(self.opened - set(known))
                if gone:
                    # The org's directory retired it (a revoked machine's
                    # project): nothing more goes up, and a new stream, which
                    # opens only what is eligible, takes it out of the hub's
                    # fan-out to this machine (there is no frame that closes
                    # one project; a revocation is rare enough for a reconnect).
                    raise EndStream("no longer a hub project of org %s here: %s" % (
                        self.cred["org"], ", ".join(self.logs[pid].project.name for pid in gone)))
                for pid in self.opened:
                    # Each open project as it is registered now: a followed
                    # one whose checkout registered since has its root, which
                    # is what makes it held (machine_presence).
                    self.logs[pid].project = known[pid]
                for pid in sorted(set(known) - self.opened):
                    self.open(self.log_of(pid, known))
                self.machine_presence(time.monotonic())
            every = archive.archive_every()
            if every > 0 and now >= self.next_confirm:
                # The hub reads the archive designation at each hello: asked
                # again, it answers with the designation as it is now. One
                # project per POST, as `open` sends them: the deployed hub
                # answers 503 to a POST carrying the hellos of more than about
                # six projects, which dropped every machine's stream at its
                # first confirmation once its org held seven (2026-10-19).
                self.next_confirm = now + every
                for pid in sorted(self.opened):
                    self.post([self.logs[pid].hello(self.follows.get(pid, False))])
            if now >= self.next_upload or nudged:
                self.next_upload = now + UPLOAD_EVERY
                for pid in sorted(self.opened):
                    self.upload(self.logs[pid])
                    self.deliveries(self.logs[pid])
            self.failing = ""
        except EndStream:
            raise
        except (Exception, SystemExit) as e:  # noqa: BLE001 — said once while it keeps failing
            if repr(e) != self.failing:
                self.failing = repr(e)
                log("syncing failed: %r" % e)
        try:
            self.post_session(self.plane.tick({pid: self.logs[pid].project for pid in self.opened}))
            self.relay_requests()
            self.relay_rpcs()
            self.plane_failing = ""
        except EndStream:
            raise
        except (Exception, SystemExit) as e:  # noqa: BLE001 — said once while it keeps failing
            if repr(e) != self.plane_failing:
                self.plane_failing = repr(e)
                log("the session plane failed: %r" % e)


def serve(stream, cred, ended, logs, bridges=None, reqs=None, rpcs=None):
    """Handle one stream's frames until it closes, a POST is not delivered,
    or the uplink ends; whether the hub welcomed it. A wake (the session
    plane's readers) is a tick after the batch in hand; at most one waits."""
    woken = threading.Event()

    def wake():
        if not woken.is_set():
            woken.set()
            stream.items.put(("wake",))

    link = Link(cred, logs, ended, wake, bridges, reqs, rpcs)
    try:
        return serve_link(link, stream, ended, woken)
    finally:
        link.close()


def serve_link(link, stream, ended, woken):
    """serve's loop, the stream's frames and the wakes in arrival order. What
    is queued when the main thread looks up is one batch (DRAIN_FRAMES,
    DRAIN_FOR), its imports delivered once, then one tick: a tick can be
    slow (its POSTs, its reads of the fleet), and one a frame would let a
    burst from the hub queue for minutes. The org's directory is handled
    before each item, ahead of whatever is queued (Stream.take_org)."""
    welcomed = False

    def org_now():
        data = stream.take_org()
        if data is not None:
            try:
                link.dispatch(codes.loads(data), stream)
            except ValueError as e:
                log("an org frame that is not JSON (%s): ignored" % e)

    while True:
        # Before every frame, not only when the stream is quiet: a hub that
        # never pauses must not keep an orphan or a stopped uplink alive.
        if ended():
            return welcomed
        try:
            item = stream.items.get(timeout=POLL)
        except queue.Empty:
            item = None
        try:
            try:
                taken, until = 0, time.monotonic() + DRAIN_FOR
                while item is not None:
                    org_now()
                    if item[0] == "closed":
                        log("the stream closed: %s" % item[1])
                        return welcomed
                    if item[0] == "wake":
                        woken.clear()
                    elif item[0] == "org":
                        pass   # taken just now
                    else:
                        try:
                            frame = codes.loads(item[2])
                        except ValueError as e:
                            log("a frame that is not JSON (%s): ignored" % e)
                            frame = None
                        if isinstance(frame, dict) and frame.get("t") == "welcome":
                            welcomed = True
                        if frame is not None:
                            link.received = item[3] if len(item) > 3 else None
                            link.dispatch(frame, stream)
                    taken += 1
                    if taken >= DRAIN_FRAMES or time.monotonic() >= until or ended():
                        break
                    try:
                        item = stream.items.get_nowait()
                    except queue.Empty:
                        item = None
            finally:
                # What the batch imported reaches its members whatever ended
                # it: a POST that failed, the stream's close, the uplink's end.
                link.deliver_imports()
            link.tick()
        except NotDelivered as e:
            log("a POST was not delivered (%s): reconnecting, to redo the handshake" % e)
            return welcomed
        except Stopping as e:
            log("%s: the stream is closed" % e)
            return welcomed
        except EndStream as e:
            log("%s: reconnecting" % e)
            return welcomed


def take_lock():
    lf = open(daemon.daemon_path("uplink.lock"), "a+")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lf.seek(0)
        sminos.die("an uplink already runs for %s (%s)" % (sminos.root(), lf.read().strip() or "pid unknown"), 1)
    lf.seek(0)
    lf.truncate()
    lf.write("pid %d since %s" % (os.getpid(), sminos.now()))
    lf.flush()
    return lf


def supervisor():
    """The pid of the `daemon run` that spawned this uplink, as it said at
    spawn; for an uplink started by hand, this process's parent now."""
    said_ = os.environ.pop(daemon.UPLINK_PARENT_ENV, "")
    return int(said_) if said_.isdigit() else os.getppid()


def cmd_uplink(_a):
    """The uplink's process: one stream at a time, reconnecting with backoff
    (from 1 s, doubling to a minute, reset by a welcome), until SIGTERM or
    until its parent is not the `daemon run` that spawned it — an uplink
    outlives no `daemon run`, even one gone before this process could look."""
    parent = supervisor()
    if os.getppid() != parent:
        log("not started (pid %d): its daemon (pid %d) is gone" % (os.getpid(), parent))
        return
    lf = take_lock()  # noqa: F841 — held for the process's life
    try:
        cred = load_credential()
    except CredentialBad as e:
        log(str(e))
        sminos.die(str(e), 1)
    if cred is None:
        log("no credential (%s): nothing to connect" % credential_path())
        return
    halt = threading.Event()
    # SIGTERM from its supervisor; SIGINT from a terminal's ^C, which reaches a
    # foreground `daemon run`'s whole process group.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: halt.set())

    def ended():
        return halt.is_set() or os.getppid() != parent

    log("started (pid %d) for %s as %s" % (os.getpid(), cred["hub"], cred["machine"]))
    backoff, logs, bridges = 1, {}, plane.Bridges()
    reqs = requests.Requests(cred["key"], cred["machine"])
    rpcs = rpc.Rpcs(cred["key"], cred["machine"])
    while not ended():
        stream = Stream(cred, ended)
        stream.start()
        welcomed = serve(stream, cred, ended, logs, bridges, reqs, rpcs)
        stream.close()
        backoff = 1 if welcomed else min(backoff * 2, BACKOFF_MAX)
        deadline = time.time() + backoff
        while not ended() and time.time() < deadline:
            halt.wait(POLL)
    reqs.close()
    log("stopped (pid %d)%s" % (os.getpid(), "" if halt.is_set() else ": its daemon is gone"))
