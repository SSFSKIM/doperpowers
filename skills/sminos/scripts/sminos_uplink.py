#!/usr/bin/env python3
"""sminos_uplink — the machine's connection to the desk hub (DC4 of the desk).

`sminos daemon uplink` is its own process, which `daemon run` starts as a
child and restarts when it exits; at most one runs per $SMINOS_HOME
(`daemon/uplink.lock`), and it ends when its parent does. It reads the
machine's credential (`daemon/hub.json`, written by enrollment; without it
nothing connects) and holds DX2's stream down — `GET /machine/stream`,
Server-Sent Events — opened outbound, reconnecting with backoff.

Two threads: a reader that only reads the stream (the SSE parse, no sminos
call) into a queue, so the stream is drained whatever the rest is doing; and
the process's main thread, which does every sminos call. sminos's
per-invocation caches are module globals no second thread may share, and a
git phase of the tick loop, a derivation, or this process's own delivery
never holds the reader up.

An `events` frame is imported into a project known here whose .smns names a
hub of this machine's org. Each event is all or nothing: its code verified
against that project (DX1, with a `hub/` event's position checked by shape),
then appended verbatim through the log's own locks; an event at an existing
(writer, seq) with the same content is skipped, with another content refused,
and one past a gap is not appended. A refused event is logged to daemon.log
and never enters the log. Whatever was appended is delivered at once by this
process — the same deliver_next the sender's fast path and the tick call,
under the same per-session lock — and the tick loop is nudged.
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

STREAM_PATH = "/machine/stream"
HEARTBEAT_MS = 15000      # DX2's, until the stream's welcome says otherwise
SILENT_PERIODS = 3        # a stream silent this many heartbeats is dead
BACKOFF_MAX = 60
POLL = 0.25               # how often the main thread looks up from an idle stream
LINE_MAX = 2 << 20        # a frame is at most 1 MiB (DX2); its SSE line, a little more
LOOPBACK = ("127.0.0.1", "::1", "localhost")


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
        self.closing = threading.Event()

    def connect(self):
        url = urllib.parse.urlsplit(self.cred["hub"])
        timeout = SILENT_PERIODS * HEARTBEAT_MS / 1000
        if url.scheme == "https":
            conn = http.client.HTTPSConnection(url.hostname, url.port, timeout=timeout,
                                               context=ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
        self.conn = conn
        conn.request("GET", url.path.rstrip("/") + STREAM_PATH, headers={
            "Accept": "text/event-stream", "Cache-Control": "no-cache",
            "CF-Access-Client-Id": self.cred["client_id"], "CF-Access-Client-Secret": self.cred["client_secret"]})
        return conn.getresponse()

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
        except (OSError, http.client.HTTPException, ValueError) as e:
            self.items.put(("closed", "closed by this end" if self.closing.is_set() else str(e) or repr(e)))

    def silent_after(self, seconds):
        """The read bound once the stream's own heartbeat is known."""
        sock = self.conn.sock if self.conn else None
        if sock is not None:
            sock.settimeout(seconds)

    def close(self):
        self.closing.set()
        sock = self.conn.sock if self.conn else None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.conn:
            self.conn.close()


# ------------------------------------------------------------- import


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


def hub_project(pid, cred):
    """The project an `events` frame names, when this machine knows it and its
    .smns names a hub of this machine's org; else None."""
    if not (isinstance(pid, str) and sminos.valid_name(pid)):
        return None
    for p in sminos.known_projects():
        if p.id != pid or not (p.root and os.path.isdir(p.root)):
            continue
        fresh = sminos.resolve_project(p.root)
        hub = smns_hub(fresh.root) if fresh is not None and fresh.id == pid else None
        if hub and hub["org"] == cred["org"]:
            return fresh
    return None


def position(e):
    if not isinstance(e, dict):
        return "an entry that is not an event"
    nonce = e.get("mac", {}).get("nonce") if isinstance(e.get("mac"), dict) else None
    return "%r:%r%s" % (e.get("writer"), e.get("seq"), " (nonce %r)" % nonce if nonce is not None else "")


def refusal(key, project, e):
    """Why an event from the hub may not enter this project's log, or ""."""
    if not isinstance(e, dict):
        return "not a log event"
    writer = e.get("writer")
    if not (isinstance(writer, str) and "/" in writer.strip("/") and writer.isprintable() and " " not in writer):
        return "its writer is not one a log holds"
    if not (codes.is_log_seq(e.get("seq")) and isinstance(e.get("ts"), str) and isinstance(e.get("kind"), str)):
        return "it is not a log event (seq, ts, kind)"
    return {
        None: "",
        "encoding": "its code or nonce is not the canonical base64url of 32 and 16 bytes",
        "position": "a hub/ event whose writer, seq, or ts fails its shape",
        "code": "its code does not verify for project %s" % project.id,
    }[codes.failure(key, "log", project.id, e)]


def payload(e):
    """An event's content for comparison: its canonical form without its code
    (an event this machine wrote is stored without one)."""
    try:
        return codes.canonical({k: v for k, v in e.items() if k != "mac"})
    except codes.NotCanonical:
        return None


def append_verbatim(project, e):
    """Append an imported event to its writer's file as it came, under the
    locks every appender takes (`.sync.lock` shared, the file's own lock):
    "appended"; "present" when that (writer, seq) holds the same content;
    "conflict" when it holds another; "gap" when seq is not one past the last."""
    if e["kind"] in sminos.LIFECYCLE:
        sminos._VIEWS.pop(project.id, None)
    path = sminos.writer_path(project, e["writer"])
    with sminos.flocked(os.path.join(os.path.dirname(path), ".sync.lock"), exclusive=False), \
            sminos.flocked(path + ".lock"):
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "r+b") as f:
            last = sminos._last_seq(f)
            if e["seq"] > last + 1:
                return "gap"
            if e["seq"] <= last:
                f.seek(0)
                for line in f.read().decode("utf-8", "replace").split("\n"):
                    x = sminos.parse_event(line) if line.strip() else None
                    if x and x["seq"] == e["seq"]:
                        return "present" if payload(x) == payload(e) else "conflict"
                return "conflict"
            end = f.seek(0, os.SEEK_END)
            if end:
                f.seek(end - 1)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write((json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8"))
    return "appended"


def import_events(cred, frame):
    """An `events` frame: verify and append each event, then deliver."""
    project = hub_project(frame.get("project"), cred)
    if project is None:
        log("events for project %r, which is no hub project of org %s known here: ignored"
            % (frame.get("project"), cred["org"]))
        return
    events = frame.get("events")
    if not isinstance(events, list):
        log("an events frame for %s without a list of events: ignored" % project.name)
        return
    appended = 0
    for e in events:
        why = refusal(cred["key"], project, e)
        if why:
            log("refused %s in %s: %s" % (position(e), project.name, why))
            continue
        # JSON's 3.0 is the number 3; the log's readers take an int. The code's
        # canonical form is the same for both.
        e = {**e, "seq": int(e["seq"])}
        outcome = append_verbatim(project, e)
        if outcome == "appended":
            appended += 1
        elif outcome != "present":
            log("refused %s in %s: %s" % (position(e), project.name, {
                "conflict": "another event holds that (writer, seq)",
                "gap": "its seq is not one past the writer's last"}[outcome]))
    if appended:
        deliver(project)
        sminos.nudge_daemon()


def deliver(project):
    """What the import made owed to this machine's members, delivered now."""
    sminos.forget_caches()
    total, reached = daemon.deliver_owed(project, sminos.view_of(project, titles=False))
    if total:
        log("delivered %d in %s to %s" % (total, project.name, ", ".join(reached)))


# ------------------------------------------------------------- the loop


def serve(stream, cred, ended):
    """Handle one stream's frames until it closes or the uplink ends; whether
    the hub welcomed it."""
    welcomed = False
    while True:
        # Before every frame, not only when the stream is quiet: a hub that
        # never pauses must not keep an orphan or a stopped uplink alive.
        if ended():
            return welcomed
        try:
            item = stream.items.get(timeout=POLL)
        except queue.Empty:
            continue
        if item[0] == "closed":
            log("the stream closed: %s" % item[1])
            return welcomed
        try:
            frame = codes.loads(item[2])
        except ValueError as e:
            log("a frame that is not JSON (%s): ignored" % e)
            continue
        t = frame.get("t") if isinstance(frame, dict) else None
        try:
            if t == "welcome":
                welcomed = True
                beat = frame.get("heartbeat_ms")
                beat = beat if isinstance(beat, int) and not isinstance(beat, bool) and beat > 0 else HEARTBEAT_MS
                stream.silent_after(SILENT_PERIODS * beat / 1000)
                log("connected to %s as %s (stream %s)" % (cred["hub"], frame.get("machine"), frame.get("generation")))
            elif t == "events":
                import_events(cred, frame)
            # `hb` keeps the read bound from lapsing; answering it, `have`,
            # `resend`, `refused`, `part`, and the session plane's frames are
            # later milestones' (DX2), and an unknown `t` is left for them.
        except (Exception, SystemExit) as e:  # noqa: BLE001 — one frame's failure is not the stream's
            log("handling a %r frame failed: %r" % (t, e))


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
    backoff = 1
    while not ended():
        stream = Stream(cred)
        stream.start()
        welcomed = serve(stream, cred, ended)
        stream.close()
        backoff = 1 if welcomed else min(backoff * 2, BACKOFF_MAX)
        deadline = time.time() + backoff
        while not ended() and time.time() < deadline:
            halt.wait(POLL)
    log("stopped (pid %d)%s" % (os.getpid(), "" if halt.is_set() else ": its daemon is gone"))
