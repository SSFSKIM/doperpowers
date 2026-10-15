"""A stand-in for the desk hub's machine side (DX2, DX7), for tests only: what
DC4 needs before DC3's local hub runs.

    python3 hub_standin.py <port-file> <client-id> <client-secret> [heartbeat-ms]

Serves, on 127.0.0.1 at a free port (written to <port-file>), for org `org-1`,
with one machine already enrolled and active: `testhost`, whose service token
is <client-id> / <client-secret>.

- `GET /machine/stream`: admitted only with an enrolled machine's service
  token (`CF-Access-Client-Id` / `CF-Access-Client-Secret`; else 403
  `{"error": "not-enrolled"}`); an SSE stream whose first frame is `welcome`,
  then `hb` every heartbeat, and whatever the test sends. A new stream ends
  the previous one (the generation counts them).
- `POST /machine/frames`: admitted as the stream is; accepted and kept
  (`GET /control/state` lists them).
- `POST /machine/enroll` `{token, machine}`: DX7's redemption. A token is
  `open` until redeemed, then `pending` (the name reserved, a service token
  minted and answered once: `{org, machine, client_id, client_secret}`), then
  `confirmed` at its machine's first admitted request. Redeeming again while
  pending, under the same name, rotates the credential (the old one stops
  admitting); under another name it is `token-used`. A name another machine
  holds, compared without case, is `name-taken` and binds nothing. A token
  past its `ttl_s` is `expired`, releasing a pending name. Every error is
  `{"error", "message"}` with DX7's status.

Any other request is admitted as Access would admit nothing: 404.

The test's own hands:

- `POST /control/send` `{"frames": [...], "repeat": N}` writes the frames
  (N times over) to the current stream and answers once they are written —
  a reader that does not drain the stream holds the answer back —
  `{"generation", "written", "took"}`; 504 when no stream is open, or the
  write does not finish, within 20 seconds.
- `POST /control/enrollment` `{"ttl_s"?}`: a one-time token, as an admin's
  `POST /api/enrollments` gives it (`201 {"token", "org"}`).
- `POST /control/fault` `{"redeem": [<fault>, ...]}`: replaces the faults
  the next redemptions of a known token meet, one each, in order: `lose`
  (applied, then the connection closed with no answer), `busy` (409, nothing
  applied), `mint-failed` (502 after the name is reserved, as the hub's failed
  mint leaves it), `other-org` (applied, answered for another org),
  `truncate` (applied, then a 200 announcing its whole length that sends
  half of it and closes).
- `GET /control/state`: `{"generation", "connected", "posted", "machines",
  "enrollments", "redemptions", "faults"}` — `machines` without their
  secrets, `redemptions` every body `/machine/enroll` received, `faults`
  those still queued.
"""

import json
import os
import queue
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT_FILE, CLIENT_ID, CLIENT_SECRET = sys.argv[1:4]
HEARTBEAT_MS = int(sys.argv[4]) if len(sys.argv) > 4 else 15000
WAIT = 20
ORG = "org-1"
NAME_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")

lock = threading.Condition()
state = {"generation": 0, "stream": None, "posted": [], "faults": [], "redemptions": [],
         # name_key → {name, client_id, client_secret, state, enrollment}
         "machines": {"testhost": {"name": "testhost", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                                   "state": "active", "enrollment": ""}},
         # token → {id, state, machine, ttl_s, expires}
         "enrollments": {}}


def sse(frame):
    return ("event: %s\ndata: %s\n\n" % (frame.get("t", ""), json.dumps(frame, ensure_ascii=False))).encode()


def is_machine_name(name):
    """DX7: ^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$, never hub or legacy in any case."""
    return (isinstance(name, str) and 1 <= len(name) <= 63 and set(name) <= NAME_CHARS
            and name[0] not in "._-" and name.lower() not in ("hub", "legacy"))


class Stream:
    def __init__(self, generation, machine):
        self.generation = generation
        self.machine = machine
        self.queue = queue.Queue()
        self.ended = threading.Event()


def expire_lapsed(now):
    """A token past its time expires; a pending one releases its name."""
    for e in state["enrollments"].values():
        if e["state"] in ("open", "pending") and now > e["expires"]:
            if e["state"] == "pending":
                state["machines"].pop(e["machine"].lower(), None)
            e["state"] = "expired"


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

    def error(self, status, code, message):
        self.reply(status, {"error": code, "message": message})

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def admitted(self):
        """The enrolled machine whose service token this request carries, or
        None (refused). A pending machine's first admitted request confirms it."""
        cid, secret = self.headers.get("CF-Access-Client-Id"), self.headers.get("CF-Access-Client-Secret")
        with lock:
            for m in state["machines"].values():
                if cid and m["client_id"] == cid and m["client_secret"] == secret:
                    if m["state"] == "pending":
                        m["state"] = "active"
                        for e in state["enrollments"].values():
                            if e["id"] == m["enrollment"]:
                                e["state"] = "confirmed"
                    return m["name"]
        self.reply(403, {"error": "not-enrolled"})
        return None

    def do_GET(self):
        if self.path == "/machine/stream":
            machine = self.admitted()
            if machine:
                self.stream(machine)
        elif self.path == "/control/state":
            with lock:
                self.reply(200, {
                    "generation": state["generation"], "connected": state["stream"] is not None,
                    "posted": state["posted"], "redemptions": state["redemptions"], "faults": state["faults"],
                    "machines": [{k: v for k, v in m.items() if k != "client_secret"}
                                 for m in state["machines"].values()],
                    "enrollments": [{k: v for k, v in e.items()} for e in state["enrollments"].values()]})
        else:
            self.reply(404, {"error": "not-found"})

    def do_POST(self):
        if self.path == "/machine/frames":
            if self.admitted():
                with lock:
                    state["posted"].append(self.body().decode())
                self.reply(200, {})
        elif self.path == "/machine/enroll":
            self.redeem()
        elif self.path == "/control/send":
            self.send_frames(json.loads(self.body()))
        elif self.path == "/control/enrollment":
            req = json.loads(self.body() or b"{}")
            token = secrets.token_urlsafe(32)
            with lock:
                state["enrollments"][token] = {"id": secrets.token_hex(8), "state": "open", "machine": None,
                                               "ttl_s": req.get("ttl_s", 900),
                                               "expires": time.time() + req.get("ttl_s", 900)}
            self.reply(201, {"token": token, "org": ORG})
        elif self.path == "/control/fault":
            with lock:
                state["faults"] = list(json.loads(self.body()).get("redeem", []))
            self.reply(200, {"faults": state["faults"]})
        else:
            self.reply(404, {"error": "not-found"})

    def redeem(self):
        """DX7's redemption, in the hub's order of checks (registry.ts)."""
        try:
            req = json.loads(self.body())
        except ValueError:
            req = None
        with lock:
            state["redemptions"].append(req)
            token, machine = (req.get("token"), req.get("machine")) if isinstance(req, dict) else (None, None)
            if not (isinstance(token, str) and token and isinstance(machine, str)):
                return self.error(400, "bad-shape", "the body is {token, machine}")
            if not is_machine_name(machine):
                return self.error(400, "bad-name", '"%s" is not an admitted machine name' % machine)
            expire_lapsed(time.time())
            e = state["enrollments"].get(token)
            if e is None:
                return self.error(404, "unknown-token", "no such token")
            fault = state["faults"].pop(0) if state["faults"] else None
            if fault == "busy":
                return self.error(409, "busy", "a redemption of this token is in flight; try again")
            if e["state"] == "expired":
                return self.error(410, "expired", "this token has expired; ask for a new one")
            if e["state"] == "confirmed":
                return self.error(409, "confirmed", "this token enrolled its machine, which has connected; "
                                                    "ask for a new one")
            if e["state"] == "pending" and e["machine"] != machine:
                return self.error(409, "token-used", 'this token is bound to the machine "%s"' % e["machine"])
            if e["state"] == "open":
                taken = state["machines"].get(machine.lower())
                if taken:
                    return self.error(409, "name-taken", 'a machine named "%s" is enrolled in this org; pick another '
                                                         "name and redeem this token under it" % taken["name"])
                e.update(state="pending", machine=machine)
                state["machines"][machine.lower()] = {"name": machine, "client_id": None, "client_secret": None,
                                                      "state": "pending", "enrollment": e["id"]}
            e["expires"] = time.time() + e["ttl_s"]
            held = state["machines"][machine.lower()]
            held.update(client_id=None, client_secret=None)  # a rotation stops the old credential at once
            if fault == "mint-failed":
                return self.error(502, "mint-failed", "the stand-in's API failed; redeem again")
            held.update(client_id="cid-" + secrets.token_hex(8), client_secret=secrets.token_urlsafe(24))
            answer = {"org": "org-2" if fault == "other-org" else ORG, "machine": machine, "client_id": held["client_id"],
                      "client_secret": held["client_secret"]}
        if fault == "lose":
            self.close_connection = True
            return None
        if fault == "truncate":
            data = json.dumps(answer).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data[:len(data) // 2])
            self.close_connection = True
            return None
        return self.reply(200, answer)

    def stream(self, machine):
        with lock:
            if state["stream"] is not None:
                state["stream"].ended.set()
            state["generation"] += 1
            mine = state["stream"] = Stream(state["generation"], machine)
            lock.notify_all()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(sse({"t": "welcome", "org": ORG, "machine": machine,
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
