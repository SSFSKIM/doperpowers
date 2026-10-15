#!/usr/bin/env python3
"""sminos_uplink — the machine's connection to the desk hub (DC4 of the desk).

`sminos daemon uplink` is its own process, which `daemon run` starts as a
child and restarts when it exits; at most one runs per $SMINOS_HOME
(`daemon/uplink.lock`), and it ends when its parent does. It reads the
machine's credential (`daemon/hub.json`, written by enrollment; without it
nothing connects) and holds DX2's connection, opened outbound: the stream
down — `GET /machine/stream`, Server-Sent Events — and frames up by `POST
/machine/frames`, each under the stream's generation. A stream silent for
three heartbeat periods is dead; the uplink reconnects with backoff.

Two threads: a reader that only reads the stream (the SSE parse, no sminos
call) into a queue, so the stream is drained whatever the rest is doing; and
the process's main thread, which does every sminos call and every POST.
sminos's per-invocation caches are module globals no second thread may
share, and a git phase of the tick loop, a derivation, or this process's own
delivery never holds the reader up.

On every stream, for every hub project of this machine's org known here, the
uplink sends `hello` with its vector and its machine's presence (DX4
`machine`), then uploads its own writers' suffix past the hub's `have`, and
from then on what they append; it answers each heartbeat with `hb-ack`,
follows `resend`, says each `refused` in daemon.log, and imports what the hub
sends (sminos_hublog.py: each event's code verified before it enters the
log, a refused one reported up as `rejected`). The session plane
(sminos_plane.py) rides the same stream: each session's presence after the
`hello` and whenever it changes, and the hub's subscriptions served as DX4
messages; a bridge's reader wakes the main thread, so what it read goes up
at once. The machine's policy (sminos_policy) goes up in `machine` on every
connect and again whenever it changes; the requests the bridges raise and
settle go up as DX4 `raised` and `settled` with their codes, and the
complete pending set after every connect (sminos_requests); and what
delivery made of each event from outside, as DX4 `delivery`
(sminos_outcomes). A POST the hub does not answer
200 ends the stream, and the next one redoes the handshake: nothing posted is
taken as landed without its answer. Frames larger than a frame's bound travel
as parts, both ways.
"""

import fcntl
import http.client
import json
import os
import queue
import signal
import socket
import ssl
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_plane as plane  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_requests as requests  # noqa: E402

STREAM_PATH = "/machine/stream"
FRAMES_PATH = "/machine/frames"
HEARTBEAT_MS = 15000      # DX2's, until the stream's welcome says otherwise
SILENT_PERIODS = 3        # a stream silent this many heartbeats is dead
BACKOFF_MAX = 60
POLL = 0.25               # how often the main thread looks up from an idle stream
LINE_MAX = 2 << 20        # a frame is at most 1 MiB (DX2); its SSE line, a little more
LOOPBACK = ("127.0.0.1", "::1", "localhost")
FRAME_LIMIT = 1 << 20     # every frame, either way, at most 1 MiB of UTF-8 (DX2); a larger one goes as parts
POST_LIMIT = 4 << 20      # a POST's body
POST_TIMEOUT = 30
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


def connection(cred, timeout):
    url = urllib.parse.urlsplit(cred["hub"])
    if url.scheme == "https":
        return http.client.HTTPSConnection(url.hostname, url.port, timeout=timeout,
                                           context=ssl.create_default_context())
    return http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)


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


class Stream(threading.Thread):
    """One connection's reader: everything it reads goes to `items` as
    ("frame", event, data), and its end as ("closed", why). It calls nothing
    of sminos."""

    def __init__(self, cred):
        super().__init__(name="uplink-reader", daemon=True)
        self.cred = cred
        self.items = queue.Queue()
        self.conn = None
        self.sock = None
        self.closing = threading.Event()

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
            for event, data in sse_events(resp):
                self.items.put(("frame", event, data))
            self.items.put(("closed", "the hub ended the stream"))
        except Exception as e:  # noqa: BLE001 — a connection closed from this end raises from deep inside http.client
            self.items.put(("closed", "closed by this end" if self.closing.is_set() else str(e) or repr(e)))

    def silent_after(self, seconds):
        """The read bound once the stream's own heartbeat is known."""
        if self.sock is not None:
            self.sock.settimeout(seconds)

    def close(self):
        self.closing.set()
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
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


def smns_hub(root_dir):
    """The `hub` field of the .smns at root_dir when it is a well-formed
    {url, org}, or None: a malformed hub is fed by no hub."""
    try:
        with open(os.path.join(root_dir, sminos.SMNS)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    hub = d.get("hub") if isinstance(d, dict) else None
    return hub if sminos.hub_wellformed(hub) else None


def hub_projects(cred):
    """{project id: project} of every project known here whose .smns, read as
    it is now, names a hub of this machine's org."""
    out = {}
    for p in sminos.known_projects():
        if p.id in out or not (p.root and os.path.isdir(p.root)):
            continue
        fresh = sminos.resolve_project(p.root)
        hub = smns_hub(fresh.root) if fresh is not None and fresh.id == p.id else None
        if hub and hub["org"] == cred["org"]:
            out[p.id] = fresh
    return out


def hub_project(pid, cred):
    """The project a frame names, when this machine knows it and its .smns
    names a hub of this machine's org; else None."""
    if not (isinstance(pid, str) and sminos.valid_name(pid)):
        return None
    return hub_projects(cred).get(pid)


# ------------------------------------------------------------- one stream


class Link:
    """One stream's conversation with the hub. Frames down are dispatched by
    `t`: the log plane's here, the session plane's to `self.plane`; the RPCs
    (DC7's) are not handled here yet and pass by. Frames up are posted under
    the stream's generation, and a POST not answered 200 ends the stream: the
    next one redoes the handshake, which is idempotent, rather than assume
    anything landed. `wake` asks the main thread for a tick now."""

    def __init__(self, cred, logs, ended=lambda: False, wake=lambda: None, bridges=None, reqs=None):
        self.cred = cred
        self.ended = ended
        self.logs = logs          # project id → HubLog, kept across streams
        self.generation = None
        self.opened = set()       # the projects `hello`ed on this stream
        self.parts = Parts()
        self.ack_due = None       # the newest heartbeat's `at`, while unanswered
        self.acked_at = 0.0
        self.next_scan = self.next_upload = 0.0
        self.nudge = daemon.nudged_at()
        self.passed = set()
        self.failing = self.plane_failing = ""
        self.plane = plane.Plane(cred["machine"], wake, bridges)
        self.requests = reqs or requests.Requests(cred["key"], cred["machine"])  # kept across streams by the uplink
        self.requests.wake = wake
        self.machine_sent = {}    # project id → the `machine` body last posted on this stream
        self.next_checkouts = 0.0
        self.handlers = {"welcome": self.on_welcome, "hb": self.on_hb, "have": self.on_have,
                         "events": self.on_events, "resend": self.on_resend, "refused": self.on_refused,
                         "part": self.on_part, "subscribe": self.on_subscribe, "unsubscribe": self.on_unsubscribe,
                         "rows": self.on_rows, "diff": self.on_diff}

    def post(self, frames):
        post(self.cred, self.generation, frames, self.ended)

    def post_session(self, messages):
        if messages:
            self.post([plane.frame(m) for m in messages])

    def close(self):
        self.plane.close()

    def dispatch(self, frame, stream):
        t = frame.get("t") if isinstance(frame, dict) else None
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
        generation, beat = frame.get("generation"), frame.get("heartbeat_ms")
        beat = beat if type(beat) is int and beat > 0 else HEARTBEAT_MS
        stream.silent_after(SILENT_PERIODS * beat / 1000)
        self.generation = generation if type(generation) is int else None
        self.opened.clear()
        self.machine_sent.clear()
        for hl in self.logs.values():
            hl.reset()
        self.plane.close()
        self.next_scan = 0.0
        log("connected to %s as %s (stream %s)" % (self.cred["hub"], frame.get("machine"), generation))

    def on_hb(self, frame, _stream):
        self.ack_due = frame.get("at") if isinstance(frame.get("at"), str) else ""

    def on_have(self, frame, _stream):
        hl = self.logs.get(frame.get("project"))
        if hl is not None and hl.project.id in self.opened:
            hl.on_have(frame)
            self.upload(hl)

    def on_events(self, frame, _stream):
        hl = self.log_of(frame.get("project"))
        if hl is None:
            log("events for project %r, which is no hub project of org %s known here: ignored"
                % (frame.get("project"), self.cred["org"]))
            return
        appended, rejections = hl.take(frame.get("events"))
        if appended:
            hl.deliver()
            sminos.nudge_daemon()
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
            self.post_session(self.plane.subscribe(project, frame))

    def on_unsubscribe(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.unsubscribe(frame.get("sub")))

    def on_rows(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.rows(frame))

    def on_diff(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.diff(frame))

    # ---------------------------------------------------- frames up

    def open(self, hl):
        """`hello` for a project on this stream, with what DX2 republishes
        after every connect that is this child's — the machine's presence —
        and the rejections not yet reported. A live member that joined under a
        former name of this machine joins again first, so the vector and the
        upload carry it."""
        hl.rejoin_former()
        unreported = hl.unreported()
        self.plane.refresh(hl.project)
        sessions = [plane.frame(m) for m in self.plane.presence(hl.project.id, force=True)]
        machine = hl.presence()
        # The project's bridges are followed before its set is drawn up: the
        # set goes now if they are read, else once they are (Requests.due).
        self.requests.follow(self.bridged(self.opened | {hl.project.id}))
        self.requests.take()
        owed = self.requests.opening(hl.project.id)
        self.post([hl.hello(), machine] + sessions + unreported + owed)
        self.opened.add(hl.project.id)
        self.machine_sent[hl.project.id] = machine["message"]["body"]
        hl.reported(unreported)
        self.requests.sent(owed)
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
        """`machine` again for each open project whose body changed: the
        policy is read at every scan (a `daemon policy` nudges one), the
        checkouts every CHECKOUTS_EVERY."""
        current = policy.machine_policy()
        if now < self.next_checkouts and all(self.machine_sent.get(pid, {}).get("policy") == current
                                             for pid in self.opened):
            return
        self.next_checkouts = now + CHECKOUTS_EVERY
        for pid in sorted(self.opened):
            m = self.logs[pid].presence()
            if m["message"]["body"] != self.machine_sent.get(pid):
                self.post([m])
                self.machine_sent[pid] = m["message"]["body"]

    def bridged(self, pids):
        """{session: project id}: the members of these projects with a bridge
        endpoint here, whose requests are read."""
        return {sid: pid for pid in pids for sid in self.plane.members.get(pid, ())
                if os.path.exists(plane.bridge.endpoint(sid))}

    def relay_requests(self):
        """The requests of the open projects' bridged sessions: readers for
        them, and what they read, up."""
        self.requests.follow(self.bridged(self.opened))
        self.requests.take()
        frames = self.requests.due(self.opened)
        if frames:
            self.post(frames)
            self.requests.sent(frames)

    def tick(self):
        """Between frames: the heartbeat answered, new hub projects opened,
        and what this machine's writers appended uploaded — at once when a
        sender nudged the daemon."""
        if self.generation is None:
            return
        now = time.time()
        if self.ack_due is not None and now - self.acked_at >= ACK_GAP:
            at, self.ack_due, self.acked_at = self.ack_due, None, now
            self.post([{"t": "hb-ack", "generation": self.generation, "at": at}])
        nudge = daemon.nudged_at()
        nudged, self.nudge = nudge != self.nudge, nudge
        try:
            if now >= self.next_scan or nudged:
                self.next_scan = now + SCAN_EVERY
                sminos.forget_caches()
                known = hub_projects(self.cred)
                gone = sorted(self.opened - set(known))
                if gone:
                    # Its .smns no longer names a hub of this org (or names
                    # another id): nothing more goes up, and a new stream,
                    # which opens only what is eligible, takes it out of the
                    # hub's fan-out to this machine.
                    raise EndStream("no longer a hub project of org %s here: %s" % (
                        self.cred["org"], ", ".join(self.logs[pid].project.name for pid in gone)))
                for pid in sorted(set(known) - self.opened):
                    self.open(self.log_of(pid, known))
                self.machine_presence(time.monotonic())
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
            self.plane_failing = ""
        except EndStream:
            raise
        except (Exception, SystemExit) as e:  # noqa: BLE001 — said once while it keeps failing
            if repr(e) != self.plane_failing:
                self.plane_failing = repr(e)
                log("the session plane failed: %r" % e)


def serve(stream, cred, ended, logs, bridges=None, reqs=None):
    """Handle one stream's frames until it closes, a POST is not delivered,
    or the uplink ends; whether the hub welcomed it. A wake (the session
    plane's readers) is a tick now, between frames; at most one waits."""
    woken = threading.Event()

    def wake():
        if not woken.is_set():
            woken.set()
            stream.items.put(("wake",))

    link = Link(cred, logs, ended, wake, bridges, reqs)
    try:
        return serve_link(link, stream, ended, woken)
    finally:
        link.close()


def serve_link(link, stream, ended, woken):
    """serve's loop, the stream's frames and the wakes in arrival order."""
    welcomed = False
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
            if item is not None and item[0] == "closed":
                log("the stream closed: %s" % item[1])
                return welcomed
            if item is not None and item[0] == "wake":
                woken.clear()
                item = None
            if item is not None:
                try:
                    frame = codes.loads(item[2])
                except ValueError as e:
                    log("a frame that is not JSON (%s): ignored" % e)
                    frame = None
                if isinstance(frame, dict) and frame.get("t") == "welcome":
                    welcomed = True
                if frame is not None:
                    link.dispatch(frame, stream)
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


def cmd_uplink(_a):
    """The uplink's process: one stream at a time, reconnecting with backoff
    (from 1 s, doubling to a minute, reset by a welcome), until SIGTERM or
    until its parent is gone — an uplink outlives no `daemon run`."""
    lf = take_lock()  # noqa: F841 — held for the process's life
    try:
        cred = load_credential()
    except CredentialBad as e:
        log(str(e))
        sminos.die(str(e), 1)
    if cred is None:
        log("no credential (%s): nothing to connect" % credential_path())
        return
    parent, halt = os.getppid(), threading.Event()
    # SIGTERM from its supervisor; SIGINT from a terminal's ^C, which reaches a
    # foreground `daemon run`'s whole process group.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: halt.set())

    def ended():
        return halt.is_set() or os.getppid() != parent

    log("started (pid %d) for %s as %s" % (os.getpid(), cred["hub"], cred["machine"]))
    backoff, logs, bridges = 1, {}, plane.Bridges()
    reqs = requests.Requests(cred["key"], cred["machine"])
    while not ended():
        stream = Stream(cred)
        stream.start()
        welcomed = serve(stream, cred, ended, logs, bridges, reqs)
        stream.close()
        backoff = 1 if welcomed else min(backoff * 2, BACKOFF_MAX)
        deadline = time.time() + backoff
        while not ended() and time.time() < deadline:
            halt.wait(POLL)
    reqs.close()
    log("stopped (pid %d)%s" % (os.getpid(), "" if halt.is_set() else ": its daemon is gone"))
