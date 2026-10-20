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

The threads: a reader that only reads the stream (the SSE parse, no sminos
call) into a queue, so the stream is drained whatever the rest is doing;
beside it the stream's acker, which answers each heartbeat with `hb-ack` on a
connection of its own (no sminos call either), so the machine's lease at the
hub never waits on the main thread; two sender lanes (Sender), each a thread
with one persistent connection to the hub, which post in order what the main
thread queues for them — the log lane the log plane's frames (the connect's
bundle, uploads, outcomes, rejections, the machine's presence, every
re-`hello`), the session lane the session plane's, the requests' and the RPC
results, its frames of a project held until that project's `hello` was
answered — so a POST the hub holds, or a fresh TLS handshake, stops neither
the pump nor the other lane; and the process's main thread, which does every
sminos call and never waits on the network. sminos's per-invocation caches
are module globals no second thread may share, and a git phase of the tick
loop, a derivation, or this process's own delivery never holds the reader
up. The main thread takes whatever is queued as one batch, then ticks once:
what the batch imported is delivered once per project, so a burst from the
hub costs a tick, not a tick a frame. A lane's answers come back on the same
queue: after a 200 the continuations of what it carried run there, in
order. Each lane says in daemon.log every connection it dials and closes,
with how many POSTs each carried, and any POST slower than
SLOW_POST_SECONDS.

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
at once. The plane's transcripts and its warmer are the process's, kept
across streams: the builds the warmer keeps current for the live members
are saved under daemon/plane/ as they grow and once more at the uplink's
stop (STOP_SAVE_SECONDS at most), and loaded by the next process, which
sweeps the ones past their keep as it starts. The machine's policy (sminos_policy) goes up in `machine` on every
connect and again whenever it changes; the requests the bridges raise and
settle go up as DX4 `raised` and `settled` with their codes, and the
complete pending set after every connect (sminos_requests); what
delivery made of each event from outside, as DX4 `delivery`
(sminos_outcomes); and the RPCs the hub forwards, verified, executed at most
once, and answered as `rpc-result` until `rpc-ack` (sminos_rpc). A POST the
hub does not answer 200 ends the stream, and the next one redoes the
handshake: what the handshake heals is marked sent when queued (the vector's
reach, a complete pending set, an RPC result), and what it does not (the
presence tombstone, rejections reported, outcomes dropped) only once the hub
answered 200, in flight meanwhile. Settlements and compaction messages wait
longer (sminos_flights): the hub answers 200 even to a session frame it
refuses `not-open`, so they are the hub's only once a confirmation of their
project queued after that 200 was answered too — the project's probe, an
empty `events` frame on the log lane CONFIRM_AFTER after the first of them
was answered — and a `not-open` owes them again.
Frames larger than a frame's bound travel as parts, both ways.
"""

import collections
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
IDLE_CLOSE = 60.0         # a lane's connection idle this long is closed by the lane (SMINOS_IDLE_CLOSE, for a test)
SEND_QUEUE_MAX = 16 << 20  # a lane holding more unsent than this: the hub is not taking frames, the stream ends
SLOW_POST_SECONDS = 5.0   # a lane's POST slower than this is said in daemon.log
UPLOAD_AHEAD = POST_LIMIT  # an upload pass queues no more while the log lane holds this much unsent
CONFIRM_AFTER = 2.0       # s: a project's answered settlements are confirmed by a probe this long after the first
CONNECTIONS = itertools.count(1)  # the lanes' connections, numbered across the process's streams
# What a reused connection's send raises when the hub closed it while idle:
# nothing of the request reached it, so it goes once more on a fresh one.
STALE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


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
    delivery to a session slow to take its frames, a frame that reads a large
    transcript, a backlog of frames queued ahead of the heartbeat — and a
    lane by a POST the hub holds. The reader hands each `hb` to the
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


def frame_headers(cred, generation):
    return {"Content-Type": "application/x-ndjson", "X-Desk-Generation": str(generation), **admission(cred)}


def post(cred, generation, frames, ended=lambda: False):
    """Frames up (DX2's POST) on a connection of their own, the acker's path:
    NDJSON, each body at most POST_LIMIT bytes, under the stream's
    generation. NotDelivered unless the hub answers 200 — a POST of an older
    stream is refused stale-generation, and a hub whose replies failed to
    reach the stream answers something else. The hub holds its answer until
    its replies are on the stream, so each exchange is watched: Stopping,
    within POLL, once `ended()` (and before each body)."""
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


def shut(sock):
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def watched(work, sock_of, ended):
    """work() — one HTTP exchange, (status, answer): connect, the body sent,
    the head and the answer read — run on a thread of its own, this one
    watching it. Once `ended()`, within POLL whichever step it is blocked
    in, the socket sock_of() names is shut and Stopping raised (the
    exchange's thread, a daemon, dies with the process that is ending);
    NotDelivered on any failure, or when it outlasts twice the socket bound
    (a hub that answers a byte at a time)."""
    out = {}

    def run():
        try:
            out["answer"] = work()
        except (OSError, http.client.HTTPException) as e:
            out["error"] = " ".join(str(e).split()) or type(e).__name__

    worker = threading.Thread(target=run, name="uplink-post", daemon=True)
    worker.start()
    deadline = time.time() + 2 * POST_TIMEOUT
    while True:
        worker.join(POLL)
        if not worker.is_alive():
            break
        late = time.time() > deadline
        if ended() or late:
            shut(sock_of())
            if late:
                raise NotDelivered("no whole answer within %gs" % (2 * POST_TIMEOUT))
            raise Stopping("the uplink is ending during a POST")
    if "error" in out:
        raise NotDelivered(out["error"])
    return out["answer"]


def exchange(cred, path, generation, body, ended):
    """One POST on a connection of its own, (status, answer), watched: the
    acker's."""
    held = {}

    def work():
        conn = held["conn"] = connection(cred, POST_TIMEOUT)
        try:
            conn.request("POST", path, body=body, headers=frame_headers(cred, generation))
            resp = conn.getresponse()
            return resp.status, resp.read(ANSWER_MAX)
        finally:
            conn.close()

    return watched(work, lambda: held["conn"].sock if "conn" in held else None, ended)


# ------------------------------------------------------------- the sender lanes


def readable(sock):
    """Whether a kept connection has something to read while no request is
    out on it: its end (the hub closed it while it was idle), or bytes no
    answer accounts for. Either way it is not reused."""
    with selectors.DefaultSelector() as sel:
        sel.register(sock, selectors.EVENT_READ)
        return bool(sel.select(0))


def idle_close():
    try:
        return float(os.environ.get("SMINOS_IDLE_CLOSE") or IDLE_CLOSE)
    except ValueError:
        return IDLE_CLOSE


def project_of(frame):
    """The project a frame up is of, when it says (a session message's, a
    pending set's, an RPC result's); else None."""
    pid = frame.get("project")
    if not isinstance(pid, str) and isinstance(frame.get("message"), dict):
        pid = frame["message"].get("project")
    return pid if isinstance(pid, str) else None


def by_project(frames):
    """The frames as runs of one project each, in the order each project
    first comes, each run in its own order."""
    runs = {}
    for frame in frames:
        runs.setdefault(project_of(frame), []).append(frame)
    return list(runs.values())


class Entry:
    """Wire lines queued on a lane — on the session lane, of one project —
    and the `send` they came from: `join` is [its entries not yet taken into
    a body, its continuation], which is due with the body that takes the
    last."""

    def __init__(self, project, join):
        self.project, self.join = project, join
        self.lines = collections.deque()
        self.size = 0

    def add(self, lines):
        for line in lines:
            self.lines.append(line)
            self.size += len(line) + 1


class Sender(threading.Thread):
    """A sender lane: a thread with one persistent connection to the hub,
    posting in FIFO order what the main thread queues (`send`), so the main
    thread never waits on the network. Made at the stream's welcome, closed
    with the stream.

    `send` converts the frames to wire lines on the caller's thread and
    queues them as one entry. The log lane posts each entry as its own body
    or bodies, never two entries in one body (each call site sends one
    project's reply-owing frames per entry); the session lane takes
    everything queued as bodies of at most POST_LIMIT, and holds a project's
    entries aside, in order, until `release` says that project's `hello` was
    answered (the hub refuses a frame of a project it has not opened
    `not-open`), the other projects' going meanwhile. After a body's 200 the
    lane puts ("sent", [then, ...]) on the stream's items, for the main loop
    to run in order. A non-200 answer, a failure, a POST that outlasts
    2 × POST_TIMEOUT, or more than SEND_QUEUE_MAX unsent ends the lane:
    ("closed", NotDelivered) is put once (for the bound, raised from `send`),
    its queue dropped, and the stream ends as for any lost POST. `close()` and
    the uplink's end stop it silently, its blocked exchange shut.

    The connection is kept across POSTs, each answer read whole. One the hub
    answered `Connection: close` on, one whose socket reads its end before a
    request (the hub closed it idle), and one idle IDLE_CLOSE are closed, and
    the next POST dials afresh; `warm` dials ahead of a POST about to come.
    A send that fails on a reused connection is retried once on a fresh one
    (nothing of it reached the hub); a failure once the request went out is
    a loss — the hub may have applied it, and the next stream's handshake
    heals it. Each dial and each close is a daemon.log line with the
    connection's number, a close with how many POSTs it carried and why, and
    a POST slower than SLOW_POST_SECONDS a line of its own."""

    def __init__(self, lane, cred, generation, put, ended):
        super().__init__(name="uplink-%s-lane" % lane, daemon=True)
        self.lane, self.cred, self.generation, self.put = lane, cred, generation, put
        self.path = urllib.parse.urlsplit(cred["hub"]).path.rstrip("/") + FRAMES_PATH
        self.idle_for = idle_close()
        self.closing = threading.Event()
        self.ended = lambda: ended() or self.closing.is_set()
        self.cv = threading.Condition()
        self.entries = collections.deque()  # Entry, in the order they go
        self.aside = {}                     # project → [Entry]: the session lane's, until `release`
        self.released = set()
        self.unsent = 0                     # bytes queued or aside, not yet taken into a body
        self.state = "idle"                 # idle | posting | closed
        self.warming = False
        self.conn_lock = threading.Lock()
        self.conn = None
        self.number = 0                     # the connection's, of CONNECTIONS
        self.posts = 0                      # POSTs answered on it
        self.used = 0.0                     # when it was dialled or last answered (monotonic)

    # ---------------------------------------------------- the main thread's

    def send(self, frames, then=None):
        """Queues frames as one entry (on the session lane, one per run of a
        project's frames, in order); `then` runs on the main thread once all
        of them were answered 200, never when the lane fails first. Dropped
        once the lane is closed. NotDelivered past SEND_QUEUE_MAX."""
        join, entries = [0, then], []
        for frame in frames:
            pid = project_of(frame) if self.lane == "session" else None
            if not entries or entries[-1].project != pid:
                entries.append(Entry(pid, join))
            entries[-1].add(line.encode("utf-8") for line in to_wire(frame))
        join[0] = len(entries)
        with self.cv:
            if self.state == "closed":
                return
            if not entries:
                if then is not None:
                    self.put(("sent", [then]))
                return
            for e in entries:
                held = self.lane == "session" and e.project is not None and e.project not in self.released
                (self.aside.setdefault(e.project, []) if held else self.entries).append(e)
                self.unsent += e.size
            over = self.unsent > SEND_QUEUE_MAX
            self.cv.notify()
        if over:
            self.close()
            raise NotDelivered("the %s lane holds more than %d MiB unsent: the hub is not taking frames" % (
                self.lane, SEND_QUEUE_MAX >> 20))

    def warm(self):
        """Dial now, when no connection is held, so the handshake is done by
        the time what is about to be posted is."""
        with self.cv:
            if self.conn is None and self.state == "idle":
                self.warming = True
                self.cv.notify()

    def release(self, project):
        """The session lane: the project's `hello` was answered; its entries go."""
        with self.cv:
            self.released.add(project)
            self.entries.extend(self.aside.pop(project, ()))
            self.cv.notify()

    def hold(self, project):
        """The session lane: the project is being opened again (its `hello`
        sent anew); its entries not yet taken into a body go back aside,
        ahead of those that follow, until the next `release`."""
        with self.cv:
            self.released.discard(project)
            mine = [e for e in self.entries if e.project == project]
            if mine:
                self.entries = collections.deque(e for e in self.entries if e.project != project)
                self.aside[project] = mine + self.aside.get(project, [])

    def posting(self):
        return self.state == "posting"

    def queued(self):
        """Bytes queued and not yet taken into a body."""
        return self.unsent

    def close(self):
        """The stream is done with: what is queued dropped, a blocked
        exchange shut, the thread ended; nothing put."""
        self.closing.set()
        with self.cv:
            self.state = "closed"
            self.entries.clear()
            self.aside.clear()
            self.unsent = 0
            self.cv.notify()
        shut(self.sock())

    # ---------------------------------------------------- the lane's thread

    def run(self):
        try:
            while True:
                job = self.next_job()
                if job is None:
                    return
                if job == "idle":
                    self.drop("idle")
                elif job == "warm":
                    self.dial_ahead()
                elif not self.post_body(*job):
                    return
        finally:
            self.drop("the stream ended")

    def next_job(self):
        """What the lane does next, once there is something: (body, thens)
        to post, "warm", or "idle" (its connection's idle time is up); None
        once it is closed."""
        with self.cv:
            while True:
                if self.state == "closed" or self.ended():
                    self.state = "closed"
                    return None
                if self.entries:
                    self.state = "posting"
                    return self.take()
                if self.warming:
                    self.warming = False
                    if self.conn is None:
                        return "warm"
                    continue
                wait = None
                if self.conn is not None:
                    wait = self.used + self.idle_for - time.monotonic()
                    if wait <= 0:
                        return "idle"
                self.cv.wait(wait)

    def take(self):
        """The next body and the continuations it completes: on the log lane
        the head entry's lines up to POST_LIMIT (a larger entry goes as
        several bodies, its continuation with the last), on the session lane
        every queued entry's up to POST_LIMIT. Under the lock."""
        lines, size, thens = [], 0, []
        while self.entries:
            e = self.entries[0]
            while e.lines:
                n = len(e.lines[0]) + 1
                if lines and size + n > POST_LIMIT:
                    return b"\n".join(lines) + b"\n", thens
                lines.append(e.lines.popleft())
                size += n
                self.unsent -= n
            self.entries.popleft()
            e.join[0] -= 1
            if e.join[0] == 0 and e.join[1] is not None:
                thens.append(e.join[1])
            if self.lane == "log":
                break
        return b"\n".join(lines) + b"\n", thens

    def post_body(self, body, thens):
        """One body posted and answered; whether the lane goes on."""
        started = time.monotonic()
        try:
            status, answer, closes = watched(lambda: self.exchange(body), self.sock, self.ended)
        except Stopping:
            return False
        except NotDelivered as e:
            self.drop("failed: %s" % e)
            self.lost(str(e))
            return False
        took = time.monotonic() - started
        if took > SLOW_POST_SECONDS:
            log("a %s lane POST took %.1f s" % (self.lane, took))
        if status != 200:
            why = "the hub answered %d %s" % (status, " ".join(answer.decode("utf-8", "replace").split())[:300])
            self.drop("failed: %s" % why)
            self.lost(why)
            return False
        if closes:
            self.drop("the hub closed it")
        with self.cv:
            if self.state == "closed":
                return False
            self.state = "idle"
        if thens:
            self.put(("sent", thens))
        return True

    def lost(self, why):
        """A POST of the lane was not delivered: said once on the items,
        unless the lane was closed from this end meanwhile."""
        with self.cv:
            if self.state == "closed" or self.ended():
                return
            self.state = "closed"
            self.entries.clear()
            self.aside.clear()
            self.unsent = 0
        self.put(("closed", NotDelivered(why)))

    def sock(self):
        conn = self.conn
        return conn.sock if conn is not None else None

    def exchange(self, body):
        """One POST on the lane's connection, (status, the answer whole,
        whether the answer closes the connection); on the exchange's thread
        (`watched`). The caller drops a closing connection once it read the
        status, so a failed POST's close says it failed."""
        for retry in (False, True):
            reused = self.connect()
            try:
                self.conn.request("POST", self.path, body=body, headers=frame_headers(self.cred, self.generation))
                break
            except STALE as e:
                if not reused or retry:
                    raise
                self.drop("failed: %s" % (" ".join(str(e).split()) or type(e).__name__))
        resp = self.conn.getresponse()
        answer = resp.read()
        self.posts += 1
        self.used = time.monotonic()
        return resp.status, answer, resp.will_close

    def connect(self):
        """The connection a request goes on: the one held, unless it reads
        its end (the hub closed it idle), else one dialled now. Whether it
        was reused."""
        if self.conn is not None and readable(self.conn.sock):
            self.drop("the hub closed it")
        if self.conn is not None:
            return True
        conn = connection(self.cred, POST_TIMEOUT)
        conn.connect()
        if self.ended():
            # The lane closed while the dial was out: nothing holds it now.
            conn.close()
            raise OSError("the lane closed during its dial")
        with self.conn_lock:
            self.conn, self.number, self.posts, self.used = conn, next(CONNECTIONS), 0, time.monotonic()
        log("%s lane dialled the hub (connection #%d)" % (self.lane, self.number))
        return False

    def dial_ahead(self):
        """`warm`'s dial, on the lane's thread; a failure is the next POST's to meet."""
        try:
            watched(lambda: self.connect() and None, self.sock, self.ended)
        except (Stopping, NotDelivered) as e:
            if not self.ended():
                log("the %s lane could not dial the hub ahead of its POST (%s)" % (self.lane, e))

    def drop(self, why):
        with self.conn_lock:
            conn, self.conn = self.conn, None
        if conn is None:
            return
        conn.close()
        log("%s lane closed connection #%d after %d POSTs (%s)" % (self.lane, self.number, self.posts, why))


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
    to `self.rpcs`. Frames up go on the stream's two sender lanes (Sender),
    under its generation: the log lane carries the log plane's — the
    connect's bundle, uploads, delivery outcomes, rejections, the machine's
    presence and every re-`hello` — and the session lane the session plane's,
    the requests' and the RPC results. A POST not answered 200 ends the
    stream: the next one redoes the handshake, which is idempotent, rather
    than assume anything landed. So a mark the handshake heals is placed
    when its frames are queued; one it does not — the presence tombstone,
    rejections reported, outcomes dropped — in the continuation that runs
    after the 200 of the POST that carried them, its producer not taking the
    same again meanwhile (`reporting`, `delivering`); settlements and
    compaction messages, in flight from `sending`, leave their outbox in that
    continuation and are the hub's once a confirmation of their project
    queued after it is answered (`confirm_held`), a `not-open` owing them
    again. A continuation
    clears its in-flight flags and opens the session gate whatever its local
    writes meet; a write that fails is kept and done on a later pass
    (settle_marks), so a disk error never holds the network back. `wake` asks the main thread for a tick
    now."""

    def __init__(self, cred, logs, ended=lambda: False, wake=lambda: None, bridges=None, reqs=None, rpcs=None,
                 warmer=None):
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
        self.plane = plane.Plane(cred["machine"], wake, bridges, warmer=warmer)   # the warmer kept across streams
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
        self.log_lane = self.session_lane = None  # the stream's senders, from its welcome on
        self.reporting = collections.Counter()   # project id → POSTs of its rejections not yet answered
        self.delivering = set()   # project ids whose delivery outcomes are in a POST not yet answered
        self.opening = set()      # project ids whose `hello` is out: a refusal does not open them again
        self.probing = set()      # project ids whose confirmation probe is out (confirm_held)
        self.unrecorded = {}      # project id → rejections the hub took, their record not yet written
        self.undropped = {}       # project id → (outbox, lines) the hub took, their drop not yet done
        self.unsettled = {}       # (project id, what) → the failure last said (settle_marks)
        self.handlers = {"welcome": self.on_welcome, "hb": self.on_hb, "have": self.on_have,
                         "events": self.on_events, "resend": self.on_resend, "refused": self.on_refused,
                         "part": self.on_part, "subscribe": self.on_subscribe, "unsubscribe": self.on_unsubscribe,
                         "rows": self.on_rows, "diff": self.on_diff, "output": self.on_output, "rpc": self.on_rpc,
                         "rpc-ack": self.on_rpc_ack, "org": self.on_org}

    def post_session(self, messages):
        if messages:
            self.session_lane.send([plane.frame(m) for m in messages])

    def ran(self, thens):
        """A lane's ("sent", thens): the continuations of what the hub
        answered 200, in order. One that fails is that frame's failure, not
        the stream's."""
        for then in thens:
            try:
                then()
            except EndStream:
                raise
            except (Exception, SystemExit) as e:  # noqa: BLE001 — as a frame handler's
                log("the continuation of a POST failed: %r" % e)

    def close_lanes(self):
        """Whether a lane was in a POST as they closed."""
        lanes = [lane for lane in (self.log_lane, self.session_lane) if lane is not None]
        posting = any(lane.posting() for lane in lanes)
        for lane in lanes:
            lane.close()
        self.log_lane = self.session_lane = None
        return posting

    def close(self):
        if self.close_lanes() and self.ended():
            log("the uplink is ending during a POST: the stream is closed")
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
        self.requests.reset()
        self.rpcs.reset()
        self.next_scan = 0.0
        self.next_confirm = time.time() + archive.archive_every()
        self.close_lanes()
        self.reporting.clear()
        self.delivering.clear()
        self.opening.clear()
        if self.generation is not None:
            # The generation every POST names is known from here on: nothing is posted before it.
            self.log_lane, self.session_lane = (Sender(lane, self.cred, self.generation, stream.items.put, self.ended)
                                                for lane in ("log", "session"))
            self.log_lane.start()
            self.session_lane.start()
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
            self.report(hl, rejections)

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
        refusal = frame.get("refusal") if isinstance(frame.get("refusal"), dict) else {}
        if refusal.get("reason") == "not-open" and hl.project.id in self.opened:
            # The hub answers 200 to a session frame it refuses, and says so
            # down the stream before that answer or after it: what of the
            # project is in flight, or answered and not confirmed, is owed
            # again, and goes with the re-open or after it.
            self.requests.refused(hl.project.id)
            self.rpcs.refused(hl.project.id)
        if refusal.get("reason") == "not-open" and hl.project.id in self.opening:
            # A hello of it is out, so the frame refused went before that hello
            # (the hub's chains answer apart: its `have` may be here already),
            # and the hello opens it again. Its vector stands; a loss after
            # it is refused again once the hello is answered, and handled then.
            log("the hub refused in %s: not-open, while a hello of it is out: that hello opens it" %
                hl.project.name)
            return
        hl.on_refused(frame)
        if hl.have is None and hl.project.id in self.opened and hl.project.id not in self.opening:
            # The hub no longer has it open (`not-open`): opened anew, once
            # while a hello of it is out, its session messages held meanwhile.
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
            # A connection ready by the time the snapshot is: the dial overlaps the build.
            self.session_lane.warm()
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
        machine joins again first, so the vector and the upload carry it.

        The bundle goes as one entry of the log lane, and the project's
        session messages wait (the session lane's gate, closed again on a
        project opened anew) until the hub answered it. Then the gate opens,
        before any local bookkeeping, and the bookkeeping follows: the
        settlements answered before it (and those it carried) kept as
        relayed, the read its presence's leavers were drawn from marked taken
        (the tombstone mark), its rejections recorded as reported. What
        `deliveries` posts after it follows it on the same connection, so the
        hub applies it after the hello, and a hello that fails ends the
        stream before any continuation behind it runs. While a hello of the project is out
        (`opening`), a refusal does not open it again."""
        pid = hl.project.id
        self.opening.add(pid)
        self.session_lane.hold(pid)
        hl.rejoin_former()
        unreported = [] if self.reporting[pid] else [f for f in hl.unreported()
                                                       if f not in self.unrecorded.get(pid, ())]
        self.plane.refresh(hl.project)
        machine = hl.presence()
        self.checkouts[hl.project.id] = bool(machine["message"]["body"]["checkouts"])
        follow = not self.holds(hl.project.id)
        sessions = [plane.frame(m) for m in self.plane.presence(hl.project.id, force=True)]
        read = self.plane.take_read(pid)
        # The project's bridges are followed before its set is drawn up: the
        # set goes now if they are read, else once they are (Requests.due).
        self.requests.follow(self.bridged(self.opened | {hl.project.id}))
        self.requests.take()
        owed = self.requests.opening(hl.project.id)
        results = self.rpcs.opening(hl.project.id)
        if unreported:
            self.reporting[pid] += 1
        attempt = self.requests.sending(owed)
        self.rpcs.sending(results)
        confirm = self.confirming(pid)

        def answered():
            self.opening.discard(pid)
            self.session_lane.release(pid)   # the hub has it open: what the network waited for comes first
            # Applied behind the hello, the project open: the hub's (a write that fails is said, and costs a resend).
            self.requests.delivered(owed, attempt, confirmed=True)
            confirm()
            try:
                if read is not None:
                    self.plane.accepted(pid, read)   # the hub took these leavers: only later ones are said again
            finally:
                if unreported:
                    self.reported(hl, unreported)

        self.log_lane.send([hl.hello(follow)] + ([] if follow else [machine]) + sessions + unreported + owed + results,
                           then=answered)
        self.opened.add(pid)
        self.follows[pid] = follow
        if not follow:
            self.machine_sent[pid] = machine["message"]["body"]
        self.deliveries(hl)

    def confirming(self, pid):
        """The continuation of a confirmation of the project queued now (its
        probe, or a hello that opens it): once it is answered, the
        settlements and compaction messages answered before now are the
        hub's (sminos_flights)."""
        marks = self.requests.mark(), self.rpcs.mark()

        def answered():
            self.requests.confirmed(pid, marks[0])
            self.rpcs.confirmed(pid, marks[1])
        return answered

    def confirm_held(self):
        """Each open project holding settlements or compaction messages the
        hub answered 200 for CONFIRM_AFTER, and no probe out: its probe on
        the log lane, an empty `events` frame. The hub refuses it `not-open`
        before answering when it does not hold the project open (the refusal
        owes them again), and does nothing else with it. What is held is
        confirmed within CONFIRM_AFTER, plus the probe's wait in the log
        lane's queue (it goes behind the uploads and any log POST the hub
        holds; UPLOAD_AHEAD gives it no priority), plus its exchange —
        archive period or not. Not proof: the probe's refusal, written before
        its answer, can still be unread by the stream's reader when the
        answer's continuation runs (sminos_flights)."""
        now = time.monotonic()
        for pid in sorted(self.opened - self.opening - self.probing):
            since = [t for t in (self.requests.flights.held_since(pid), self.rpcs.flights.held_since(pid))
                     if t is not None]
            if not since or now - min(since) < CONFIRM_AFTER:
                continue
            self.probing.add(pid)
            confirm = self.confirming(pid)

            def answered(pid=pid, confirm=confirm):
                self.probing.discard(pid)
                confirm()
            self.log_lane.send([{"t": "events", "project": pid, "events": []}], then=answered)

    def report(self, hl, rejections):
        """Rejections up, reported once the hub answered them."""
        self.reporting[hl.project.id] += 1
        self.log_lane.send(rejections, then=lambda: self.reported(hl, rejections))

    def reported(self, hl, rejections):
        """The hub answered the rejections: no longer in flight, and recorded
        as reported (settle_marks)."""
        pid = hl.project.id
        self.reporting[pid] -= 1
        owed = self.unrecorded.setdefault(pid, [])
        owed.extend(f for f in rejections if f not in owed)
        self.settle_marks(hl)

    def settle_marks(self, hl):
        """What the hub took and this machine has yet to record, recorded:
        the rejections reported (uplink.json), the outcomes dropped (the
        outbox). A write that fails is said once and kept, and tried again on
        the next pass (`deliveries`, every upload pass); what it keeps is
        never posted again meanwhile."""
        pid = hl.project.id
        if self.unrecorded.get(pid):
            try:
                hl.reported(self.unrecorded[pid])
                del self.unrecorded[pid]
                self.unsettled.pop((pid, "reported"), None)
            except (Exception, SystemExit) as e:  # noqa: BLE001 — kept, and tried again
                self.unsettled_once((pid, "reported"), "recording the rejections of %s reported failed (%r): "
                                    "tried again" % (hl.project.name, e))
        if pid in self.undropped:
            box, lines = self.undropped[pid]
            try:
                box.drop(lines)
                del self.undropped[pid]
                self.unsettled.pop((pid, "dropped"), None)
            except (Exception, SystemExit) as e:  # noqa: BLE001 — kept, and tried again
                self.unsettled_once((pid, "dropped"), "dropping the outcomes of %s posted failed (%r): tried again"
                                    % (hl.project.name, e))

    def unsettled_once(self, key, line):
        if self.unsettled.get(key) != line:
            self.unsettled[key] = line
            log(line)

    def upload(self, hl):
        """The project's uploads queued, each its own entry, as far as the log
        lane holds less than UPLOAD_AHEAD unsent: the rest go on a later pass,
        so a long backlog paces itself instead of filling the lane past its
        bound. Each frame is drawn only once there is room for it, and the
        rest stays drawn where it was (HubLog.next_upload): a pass while the
        lane is full draws nothing, and no event is sealed twice."""
        while self.log_lane.queued() < UPLOAD_AHEAD:
            got = hl.next_upload()
            if got is None:
                return
            frame, reach = got
            self.log_lane.send([frame])
            hl.took(reach)

    def deliveries(self, hl):
        """What delivery made of the events from outside, as DX4 `delivery`
        messages sealed as they go; dropped from the outbox once the hub
        answered the POST that carried them, and not taken again meanwhile —
        nor while a drop that failed is still owed (settle_marks)."""
        pid = hl.project.id
        self.settle_marks(hl)
        if pid in self.delivering or pid in self.undropped:
            return
        box = outcomes.Outbox(hl.project)
        if not box.waiting():
            return
        records, lines = box.take()
        frames = [f for f in (outcomes.message(self.cred["key"], self.cred["machine"], pid, r)
                              for r in records) if f is not None]
        if not frames:
            self.undropped[pid] = (box, lines)
            self.settle_marks(hl)
            return
        self.delivering.add(pid)

        def answered():
            self.delivering.discard(pid)
            self.undropped[pid] = (box, lines)
            self.settle_marks(hl)

        self.log_lane.send(frames, then=answered)

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
                self.log_lane.send(frames)
                self.follows[pid] = follow
                if follow:
                    self.machine_sent.pop(pid, None)
                else:
                    self.machine_sent[pid] = machine["message"]["body"]
                log("%s: %s" % (hl.project.name, "followed (no checkout and no session here)" if follow else
                                "held (a checkout or a session here)"))
            elif not follow and machine is not None and machine["message"]["body"] != self.machine_sent.get(pid):
                self.log_lane.send([machine])
                self.machine_sent[pid] = machine["message"]["body"]

    def bridged(self, pids):
        """{session: project id}: the members of these projects with a bridge
        endpoint here, whose requests are read: one listing of the bridges'
        directory, every POLL, rather than a look per member."""
        socks = plane.bridge_socks()
        return {sid: pid for pid in pids for sid in self.plane.members.get(pid, ()) if sid in socks}

    def relay_requests(self):
        """The requests of the open projects' bridged sessions: readers for
        them, and what they read, up — one entry per project, so each
        continuation follows the POST that carried its own frames and no
        other project's gate. A settlement leaves the outbox once that POST
        was answered and is relayed once a confirmation queued after that is
        (confirm_held);
        a complete set is taken when queued (every connect sends one
        again)."""
        self.requests.follow(self.bridged(self.opened))
        self.requests.take()
        for frames in by_project(self.requests.due(self.opened)):
            attempt = self.requests.sending(frames)
            self.session_lane.send(frames, then=lambda f=frames, a=attempt: self.requests.delivered(f, a))

    def relay_rpcs(self):
        """The RPCs' results and their compactions' progress, up, one entry
        per project: a result goes again on every stream until `rpc-ack`; a
        compact message is owed as a settlement is (sminos_flights)."""
        self.rpcs.compacted(self.requests.take_compacts())
        for frames in by_project(self.rpcs.due(self.opened)):
            attempt = self.rpcs.sending(frames)
            self.session_lane.send(frames, then=lambda f=frames, a=attempt: self.rpcs.delivered(f, a))

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
                # project per POST, as `open` sends them (the log lane posts
                # each entry alone): the deployed hub answered 503 to a POST
                # carrying the hellos of more than about six projects, which
                # dropped every machine's stream at its first confirmation
                # once its org held seven (2026-10-19). A hello the hub holds
                # holds the log lane alone.
                self.next_confirm = now + every
                for pid in sorted(self.opened):
                    self.log_lane.send([self.logs[pid].hello(self.follows.get(pid, False))])
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
            self.confirm_held()
            self.plane_failing = ""
        except EndStream:
            raise
        except (Exception, SystemExit) as e:  # noqa: BLE001 — said once while it keeps failing
            if repr(e) != self.plane_failing:
                self.plane_failing = repr(e)
                log("the session plane failed: %r" % e)


def serve(stream, cred, ended, logs, bridges=None, reqs=None, rpcs=None, warmer=None):
    """Handle one stream's frames until it closes, a POST is not delivered,
    or the uplink ends; whether the hub welcomed it. A wake (the session
    plane's readers) is a tick after the batch in hand; at most one waits."""
    woken = threading.Event()

    def wake():
        if not woken.is_set():
            woken.set()
            stream.items.put(("wake",))

    link = Link(cred, logs, ended, wake, bridges, reqs, rpcs, warmer)
    try:
        return serve_link(link, stream, ended, woken)
    finally:
        link.close()


def serve_link(link, stream, ended, woken):
    """serve's loop: the stream's frames, the wakes and the lanes' answers in
    arrival order — ("sent", thens) runs the continuations of what the hub
    answered 200, ("closed", NotDelivered) ends the stream. What is queued
    when the main thread looks up is one batch (DRAIN_FRAMES, DRAIN_FOR), its
    imports delivered once, then one tick: a tick can be slow (its reads of
    the fleet, a delivery to a slow session), and one a frame would let a
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
                        if isinstance(item[1], EndStream):
                            raise item[1]   # a lane's POST not delivered
                        log("the stream closed: %s" % item[1])
                        return welcomed
                    if item[0] == "sent":
                        link.ran(item[1])
                    elif item[0] == "wake":
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
    plane.sweep_builds()
    backoff, logs, bridges, warmer = 1, {}, plane.Bridges(), plane.Warmer()
    reqs = requests.Requests(cred["key"], cred["machine"])
    rpcs = rpc.Rpcs(cred["key"], cred["machine"])
    while not ended():
        stream = Stream(cred, ended)
        stream.start()
        welcomed = serve(stream, cred, ended, logs, bridges, reqs, rpcs, warmer)
        stream.close()
        backoff = 1 if welcomed else min(backoff * 2, BACKOFF_MAX)
        deadline = time.time() + backoff
        while not ended() and time.time() < deadline:
            halt.wait(POLL)
    reqs.close()
    at = time.monotonic()
    saved, held = plane.TRANSCRIPTS.save_all()
    if held:
        log("the builds held: %d of %d saved or already current in %.2f s" % (saved, held, time.monotonic() - at))
    log("stopped (pid %d)%s" % (os.getpid(), "" if halt.is_set() else ": its daemon is gone"))
