"""A stand-in for the desk hub's machine side (DX2), for tests only: what DC4
needs before DC3's local hub runs.

    python3 hub_standin.py <port-file> <client-id> <client-secret> [heartbeat-ms]

Serves, on 127.0.0.1 at a free port (written to <port-file>):

- `GET /machine/stream`: admitted only with the service token's
  `CF-Access-Client-Id` / `CF-Access-Client-Secret` (else 403
  `{"error": "not-enrolled"}`); an SSE stream whose first frame is `welcome`,
  then `hb` every heartbeat, and whatever the test sends. A new stream ends
  the previous one (the generation counts them).
- `POST /machine/frames`: accepted and kept (`GET /control/state` lists them).

The test's own hands:

- `POST /control/send` `{"frames": [...], "repeat": N}` writes the frames
  (N times over) to the current stream and answers once they are written —
  a reader that does not drain the stream holds the answer back —
  `{"generation", "written", "took"}`; 504 when no stream is open, or the
  write does not finish, within 20 seconds.
- `GET /control/state`: `{"generation", "connected", "posted"}`.
"""

import json
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT_FILE, CLIENT_ID, CLIENT_SECRET = sys.argv[1:4]
HEARTBEAT_MS = int(sys.argv[4]) if len(sys.argv) > 4 else 15000
WAIT = 20

lock = threading.Condition()
state = {"generation": 0, "stream": None, "posted": []}


def sse(frame):
    return ("event: %s\ndata: %s\n\n" % (frame.get("t", ""), json.dumps(frame, ensure_ascii=False))).encode()


class Stream:
    def __init__(self, generation):
        self.generation = generation
        self.queue = queue.Queue()
        self.ended = threading.Event()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

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
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def admitted(self):
        if (self.headers.get("CF-Access-Client-Id") == CLIENT_ID
                and self.headers.get("CF-Access-Client-Secret") == CLIENT_SECRET):
            return True
        self.reply(403, {"error": "not-enrolled"})
        return False

    def do_GET(self):
        if self.path == "/machine/stream":
            if self.admitted():
                self.stream()
        elif self.path == "/control/state":
            with lock:
                self.reply(200, {"generation": state["generation"], "connected": state["stream"] is not None,
                                 "posted": state["posted"]})
        else:
            self.reply(404, {"error": "not-found"})

    def do_POST(self):
        if self.path == "/machine/frames":
            if self.admitted():
                with lock:
                    state["posted"].append(self.body().decode())
                self.reply(200, {})
        elif self.path == "/control/send":
            self.send_frames(json.loads(self.body()))
        else:
            self.reply(404, {"error": "not-found"})

    def stream(self):
        with lock:
            if state["stream"] is not None:
                state["stream"].ended.set()
            state["generation"] += 1
            mine = state["stream"] = Stream(state["generation"])
            lock.notify_all()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(sse({"t": "welcome", "org": "org-1", "machine": "testhost",
                                  "generation": mine.generation, "heartbeat_ms": HEARTBEAT_MS}))
            self.wfile.flush()
            while not mine.ended.is_set():
                try:
                    frames, done = mine.queue.get(timeout=HEARTBEAT_MS / 1000)
                except queue.Empty:
                    self.wfile.write(sse({"t": "hb", "at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}))
                    self.wfile.flush()
                    continue
                for frame in frames:
                    self.wfile.write(sse(frame))
                self.wfile.flush()
                done.set()
        except OSError:
            pass
        finally:
            with lock:
                if state["stream"] is mine:
                    state["stream"] = None

    def send_frames(self, req):
        deadline = time.time() + WAIT
        with lock:
            while state["stream"] is None and time.time() < deadline:
                lock.wait(deadline - time.time())
            target = state["stream"]
        if target is None:
            self.reply(504, {"error": "no stream"})
            return
        frames = list(req.get("frames") or []) * int(req.get("repeat") or 1)
        done = threading.Event()
        started = time.time()
        target.queue.put((frames, done))
        if not done.wait(max(0.0, deadline - time.time())):
            self.reply(504, {"error": "the write did not finish", "generation": target.generation})
            return
        self.reply(200, {"generation": target.generation, "written": len(frames), "took": time.time() - started})


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
server.daemon_threads = True
with open(PORT_FILE + ".tmp", "w") as f:
    f.write(str(server.server_address[1]))
os.replace(PORT_FILE + ".tmp", PORT_FILE)
server.serve_forever()
