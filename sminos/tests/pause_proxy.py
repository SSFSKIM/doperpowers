"""A TCP proxy between the uplink and a hub that can stop the hub's stream to
the uplink, for the instruments only (the desk open-fast spec, M1 and A4's
pair proof): the reply chain blocked for real, through the real hub code.

    python3 pause_proxy.py <hub-url> <port-file>

Listens on 127.0.0.1 at a free port and forwards every connection to the hub
(plain http: the local hub or the stand-in). A connection whose first line is
`GET /machine/stream` is the stream; every other connection passes as it is,
paused or not. The stream's frames are found in its body as the client
reads it: through the chunked framing when the hub sends it chunked (the
local hub's runtime does, and cuts a frame's JSON across chunks), the bytes
forwarded as they came. Writes `{"proxy": <port>, "control": <port>}` to
<port-file> once both listen.

Its controls, on their own port:

- `POST /control/arm` `{"on": "next-events" | "now", "seconds"}`, answered
  once armed: on the next `"t":"events"` frame it forwards down the stream
  (the frame forwarded whole), or at once, it stops reading the hub's side of
  the stream connection for `seconds`, so the hub's writes back up once the
  socket buffers fill; then it reads and forwards again. Armed with no stream
  connection open, it applies to the next one.
- `POST /control/resume`: reads again now.
- `GET /control/state`: `{"state": "idle" | "armed" | "paused" | "resumed",
  "held", "paused_at", "resumed_at", "streams", "forwarded"}` — `held` the
  bytes of the hub's writes held back now (read and not forwarded, plus
  what waits unread in the socket), or when it resumed, the most it held;
  `paused_at` and `resumed_at` epoch seconds; `streams` the stream
  connections seen; `forwarded` the bytes of the stream sent to the client.
"""

import fcntl
import json
import os
import re
import socket
import struct
import sys
import termios
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EVENTS = re.compile(rb'"t"\s*:\s*"events"')
TAIL = 64          # bytes of what was forwarded kept to find a frame cut across reads
BLOCK = 65536


class Pause:
    """The stream's pause, shared by the stream's pump and the controls."""

    def __init__(self):
        self.cond = threading.Condition()
        self.state = "idle"
        self.on = None            # "next-events" | "now", while armed
        self.seconds = 0.0
        self.until = None         # monotonic, while paused
        self.paused_at = self.resumed_at = None
        self.held = 0
        self.streams = 0
        self.forwarded = 0
        self.current = None       # the stream connection's hub-side socket, and its buffer, while paused
        self.buffer = b""

    def snapshot(self):
        with self.cond:
            held = self.held
            if self.state == "paused":
                held = len(self.buffer) + pending(self.current)
                self.held = max(self.held, held)
            return {"state": self.state, "held": held, "paused_at": self.paused_at, "resumed_at": self.resumed_at,
                    "streams": self.streams, "forwarded": self.forwarded}


PAUSE = Pause()


class Body:
    """The stream response's body as the client reads it, fed the raw bytes
    as they come: `feed(data)` answers [(offset in data, body bytes)], the
    head and any chunked framing left out."""

    def __init__(self):
        self.head, self.in_head, self.chunked = b"", True, False
        self.state, self.line, self.left = "size", b"", 0

    def feed(self, data):
        segs, i, n = [], 0, len(data)
        if self.in_head:
            self.head += data
            k = self.head.find(b"\r\n\r\n")
            if k < 0:
                return segs
            self.chunked = b"transfer-encoding: chunked" in self.head[:k].lower()
            i = n - (len(self.head) - (k + 4))
            self.in_head, self.head = False, b""
        if not self.chunked:
            return segs + ([(i, data[i:])] if i < n else [])
        while i < n and self.state != "done":
            if self.state == "size":
                j = data.find(b"\n", i)
                if j < 0:
                    self.line += data[i:]
                    break
                size = int((self.line + data[i:j]).split(b";")[0].strip() or b"0", 16)
                self.line, i = b"", j + 1
                self.left, self.state = size, "data" if size else "done"
            elif self.state == "data":
                take = min(self.left, n - i)
                segs.append((i, data[i:i + take]))
                i, self.left = i + take, self.left - take
                if self.left == 0:
                    self.state, self.left = "crlf", 2
            else:   # the CRLF after a chunk's data
                take = min(self.left, n - i)
                i, self.left = i + take, self.left - take
                if self.left == 0:
                    self.state = "size"
        return segs


def raw_offset(segs, at):
    """The offset in the raw read of body byte `at` of that read's segments."""
    seen = 0
    for off, b in segs:
        if at <= seen + len(b):
            return off + (at - seen)
        seen += len(b)
    return None


def pending(sock):
    """The bytes waiting unread in a socket's receive buffer."""
    if sock is None:
        return 0
    try:
        return struct.unpack("i", fcntl.ioctl(sock.fileno(), termios.FIONREAD, b"\0\0\0\0"))[0]
    except OSError:
        return 0


def pipe(src, dst):
    """Bytes one way until either side ends."""
    try:
        while True:
            data = src.recv(BLOCK)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def stream_down(hub, client):
    """The hub's side of the stream to the client, paused as armed. While
    paused nothing more is forwarded: a read already under way when the pause
    began is held with the rest."""
    tail = b""             # the body's last bytes read: a frame cut across two reads is still found
    awaiting_end = False   # the events frame that triggers the pause is not whole yet
    body = Body()
    try:
        while True:
            with PAUSE.cond:
                if PAUSE.state == "armed" and PAUSE.on == "now":
                    pause_now(hub, b"")
                while PAUSE.state == "paused":
                    left = PAUSE.until - time.monotonic()
                    if left <= 0:
                        resume_now()
                        break
                    PAUSE.cond.wait(left)
                held, PAUSE.buffer = PAUSE.buffer, b""
            if held:
                client.sendall(held)
                with PAUSE.cond:
                    PAUSE.forwarded += len(held)
            data = hub.recv(BLOCK)
            if not data:
                break
            segs = body.feed(data)
            text = b"".join(b for _, b in segs)
            with PAUSE.cond:
                if PAUSE.state == "paused":
                    PAUSE.buffer += data
                    tail = (tail + text)[-TAIL:]
                    continue
                armed = PAUSE.state == "armed" and PAUSE.on == "next-events"
            cut = None
            if armed or awaiting_end:
                window = tail + text
                if awaiting_end:
                    end = window.find(b"\n\n", max(0, len(tail) - 1))
                else:
                    # A match that ends in what was read before is a frame sent before the arming.
                    m = next((m for m in EVENTS.finditer(window) if m.end() > len(tail)), None)
                    end = window.find(b"\n\n", m.end()) if m else -1
                    awaiting_end = m is not None and end < 0
                if end >= 0:
                    cut = raw_offset(segs, end + 2 - len(tail))
                    if body.chunked and cut is not None:
                        # The rest of the chunk's framing up to its next data goes with the frame.
                        cut = next((off for off, _ in segs if off >= cut), cut)
                    awaiting_end = False
            tail = (tail + text)[-TAIL:]
            out, rest = (data, b"") if cut is None else (data[:cut], data[cut:])
            client.sendall(out)
            with PAUSE.cond:
                PAUSE.forwarded += len(out)
                if cut is not None and PAUSE.state == "armed":
                    pause_now(hub, rest)
                else:
                    PAUSE.buffer += rest
    except OSError:
        pass
    finally:
        with PAUSE.cond:
            if PAUSE.current is hub:
                if PAUSE.state == "paused":
                    resume_now()
                PAUSE.current = None
        for s in (hub, client):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def pause_now(hub, rest):
    """Under the lock: stop reading the hub's side, holding `rest`."""
    PAUSE.state, PAUSE.on = "paused", None
    PAUSE.current, PAUSE.buffer = hub, rest
    PAUSE.paused_at, PAUSE.resumed_at = time.time(), None
    PAUSE.until = time.monotonic() + PAUSE.seconds
    PAUSE.held = len(rest)
    PAUSE.cond.notify_all()


def resume_now():
    """Under the lock: read again; `held` keeps the most it held."""
    PAUSE.held = max(PAUSE.held, len(PAUSE.buffer) + pending(PAUSE.current))
    PAUSE.state, PAUSE.until, PAUSE.resumed_at = "resumed", None, time.time()
    PAUSE.cond.notify_all()


def serve(client, hub_addr):
    try:
        hub = socket.create_connection(hub_addr)
    except OSError:
        client.close()
        return
    try:
        first = client.recv(BLOCK)
    except OSError:
        first = b""
    if not first:
        client.close()
        hub.close()
        return
    hub.sendall(first)
    if first.startswith(b"GET /machine/stream"):
        with PAUSE.cond:
            PAUSE.streams += 1
            PAUSE.current = hub
        threading.Thread(target=pipe, args=(client, hub), daemon=True).start()
        stream_down(hub, client)
    else:
        threading.Thread(target=pipe, args=(client, hub), daemon=True).start()
        pipe(hub, client)


class Control(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        if self.path == "/control/state":
            return self.reply(200, PAUSE.snapshot())
        return self.reply(404, {"error": "not-found"})

    def do_POST(self):
        req = self.body()
        if self.path == "/control/arm":
            on, seconds = req.get("on"), req.get("seconds")
            if on not in ("next-events", "now") or not isinstance(seconds, (int, float)) or seconds <= 0:
                return self.reply(400, {"error": "bad-shape", "message": 'on is "next-events" or "now"; seconds > 0'})
            with PAUSE.cond:
                PAUSE.state, PAUSE.on, PAUSE.seconds = "armed", on, float(seconds)
                PAUSE.held, PAUSE.paused_at, PAUSE.resumed_at = 0, None, None
                if on == "now" and PAUSE.current is not None:
                    pause_now(PAUSE.current, b"")   # with no stream open, the next one's pump applies it
            return self.reply(200, PAUSE.snapshot())
        if self.path == "/control/resume":
            with PAUSE.cond:
                if PAUSE.state == "paused":
                    PAUSE.until = time.monotonic()
                    PAUSE.cond.notify_all()
            return self.reply(200, PAUSE.snapshot())
        return self.reply(404, {"error": "not-found"})


def main():
    hub_url, port_file = sys.argv[1:3]
    u = urllib.parse.urlsplit(hub_url)
    hub_addr = (u.hostname, u.port or 80)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(64)
    control = ThreadingHTTPServer(("127.0.0.1", 0), Control)
    control.daemon_threads = True
    threading.Thread(target=control.serve_forever, daemon=True).start()
    with open(port_file + ".tmp", "w") as f:
        json.dump({"proxy": listener.getsockname()[1], "control": control.server_address[1]}, f)
    os.replace(port_file + ".tmp", port_file)
    while True:
        client, _ = listener.accept()
        threading.Thread(target=serve, args=(client, hub_addr), daemon=True).start()


if __name__ == "__main__":
    main()
