"""A stand-in for the desk hub's machine side (DX2, DX7), for tests only: what
DC4 needs hermetically, beside DC3's local hub (wrangler dev), which the
real-hub walks run against.

    python3 hub_standin.py <port-file> <client-id> <client-secret> [heartbeat-ms]

Serves, on 127.0.0.1 at a free port (written to <port-file>), for org `org-1`,
with one machine already enrolled and active: `testhost`, whose service token
is <client-id> / <client-secret>.

- `GET /machine/stream`: admitted only with an enrolled machine's service
  token (`CF-Access-Client-Id` / `CF-Access-Client-Secret`; else 403
  `{"error": "not-enrolled"}`); an SSE stream whose first frame is `welcome`,
  then `hb` every heartbeat, and whatever the hub writes. Each machine has its
  own stream; a machine's new stream ends its previous one, and its
  generation counts them.
- `POST /machine/frames`: admitted as the stream is; refused whole as `409
  stale-generation` unless `X-Desk-Generation` names the machine's current
  stream, `400 bad-shape` for a line that is not a JSON frame. Its frames are
  applied in order, as DC3's `Project` applies them: `hello` opens the
  project on this stream and answers `have` and the backlog (every writer's
  suffix past the machine's vector); `events` stores the machine's own
  writers' events once each at the next seq — a copy of a stored one passed
  over, a different payload at a stored position `refused` (`conflict`), a
  writer not the machine's `refused` (`writer-not-yours`), an event past
  1 MiB `refused` (`too-large`), a gap answered by `resend` — and fans what it stored out to every other machine that opened
  the project; `rejected` goes to the project's audit record; `session`
  messages and `hb-ack` are kept (each with when it was received: a session
  message's `received` and `at` alike, epoch seconds); `part`
  frames are joined. A machine's lease (DX2) starts at the first `hello` of
  a stream, is renewed by each `hb-ack` of that stream's generation, and
  lapses three heartbeats after the last renewal while its stream is open:
  `leases` says whether each machine's current one is online, `lapses`
  records each lapse. Events or a
  rejection for a project not opened on this stream are `refused`
  (`not-open`). The answer, `200 {"ok": true, "frames": n}`, comes once every
  reply is written down the stream.
- The org's directory (the org directory's M2): the Registry's projects —
  each machine's own project (`kind` `machine`, its id a UUID v5 of the org
  and its lower-cased name, registered for `testhost` at start and for a
  machine at its enrollment's confirmation), and every project a `hello`
  registers (`kind` `hub`, unless its id is an active machine's project) —
  and the machines with whether each is online (its lease fresh: started by
  a `hello`, renewed by `hb-ack`, lapsed or ended with its stream) and `seen`
  (when that last changed). It goes down a stream as `org` second, after
  `welcome`, and to every open stream whenever a project is registered,
  retired or reactivated, a machine is confirmed, or a machine's online
  state changes. `hello` takes `follow` (a boolean; anything else is
  `bad-shape`), kept per project and machine (`follow` in `projects`).
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

The test's own hands (the stand-in plays a hub that may lie):

- `POST /control/send` `{"frames": [...], "repeat": N, "machine"?}` writes the
  frames (N times over) to the machine's current stream (by default the
  stream opened last) and answers once they are written — a reader that does
  not drain the stream holds the answer back — `{"generation", "written",
  "took", "at"}` (`at`: the epoch time the write was flushed down the
  stream); 504 when no stream is open, or the write does not finish, within
  20 seconds.
- `POST /control/inject` `{"project", "events"}` stores events in a project's
  log as they are, at the positions they name, checking nothing (what a
  lying hub could hold), and fans them out to every machine that opened it.
- `POST /control/drop` `{"machine"?}` ends that machine's stream (every
  stream without one): a dropped connection.
- `POST /control/mute` `{"machine"}` stops the heartbeat on that machine's
  stream without closing it: a half-open stream.
- `POST /control/post-fault` `{"faults": [{"fault", "machine"?, "has"?}]}`
  replaces the faults the next frame POSTs meet, one each, in order: `503`
  (answered 503, nothing applied), `apply-502` (applied, its replies written,
  then answered 502: a hub whose answer was lost), `hold` (recorded as
  `held`, its answer held back until `POST /control/release`, then 503,
  nothing applied), `stall-headers` and `stall-body` (held the same way,
  after half a status head, or after a whole head announcing ten bytes and
  one of them, then the connection closed); with `machine`, only that machine's POSTs meet it, with
  `has`, only a POST carrying a frame of that `t`. `posted` records each
  POST's machine, generation, status, body, and `conn`: the connection it
  came on, numbered as they were accepted.
- `POST /control/post-delay` `{"seconds"}`: every frame POST from then on
  waits this long before it is looked at (a slow link, a fresh TLS
  connection each); 0 ends it.
- `POST /control/archive` `{"project", "machine"}` designates the project's
  archive machine (DX2's `have.archive`).
- `POST /control/register` `{"project", "name", "kind"?}` registers a
  project as another machine's `hello` would (`kind` `hub` by default), and
  `POST /control/retire` `{"project", "retired"}` marks one retired or
  active again: the org's directory goes to every open stream.
- `POST /control/enrollment` `{"ttl_s"?}`: a one-time token, as an admin's
  `POST /api/enrollments` gives it (`201 {"token", "org"}`).
- `POST /control/fault` `{"redeem": [<fault>, ...]}`: replaces the faults
  the next redemptions of a known token meet, one each, in order: `lose`
  (applied, then the connection closed with no answer), `busy` (409, nothing
  applied), `mint-failed` (502 after the name is reserved, as the hub's failed
  mint leaves it), `other-org` (applied, answered for another org),
  `truncate` (applied, then a 200 announcing its whole length that sends
  half of it and closes).
- `GET /control/state`: `{"generation" (of the stream opened last),
  "generations", "connected", "posted", "machines", "enrollments",
  "redemptions", "faults", "post_faults", "projects", "hb_acks", "sessions",
  "leases", "lapses", "registry", "online", "orgs"}` — `registry` the
  directory's projects, `online` each machine's `{online, seen}`, `orgs` how
  many `org` frames each machine's streams were sent
  — `machines` without their secrets, `redemptions` every body
  `/machine/enroll` received, `projects` each project's name, vector,
  events per writer, the machines that opened it, and its audit record.
- `GET /control/since?sessions=N&hb_acks=M`: `{"sessions", "hb_acks"}`, each
  list from that index on (a reader that polls takes only what is new).

The heartbeat goes on a timer, as the hub's alarm writes it, whether or not
frames are flowing down, its `at` to the millisecond.

It speaks HTTP/1.1, so a client may keep a connection across requests, as
the deployed hub's edge lets it: every answer carries its length, and a
connection closes only after the stream, a held POST (`hold` and the
stalls), a lost or truncated redemption, or a request whose body was left
unread.
"""

import json
import os
import queue
import uuid
import re
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT_FILE, CLIENT_ID, CLIENT_SECRET = sys.argv[1:4]
HEARTBEAT_MS = int(sys.argv[4]) if len(sys.argv) > 4 else 15000
LEASE = 3 * HEARTBEAT_MS / 1000  # DX2's LEASE_PERIODS of the heartbeat, in seconds
WAIT = 20
ORG = "org-1"
NAME_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
PROJECT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
B64URL = re.compile(r"[A-Za-z0-9_-]+")
BATCH = 200  # events per `events` frame of a backlog
HELD = ("hold", "stall-headers", "stall-body")  # POST faults whose answer waits for /control/release
FRAME_LIMIT = 1 << 20  # an event is at most 1 MiB of UTF-8, as every frame is (DX2)
TOO_LARGE = "an event is at most 1 MiB"

lock = threading.Condition()
state = {"generations": {}, "last": None, "streams": {}, "posted": [], "faults": [], "post_faults": [],
         "release": threading.Event(), "post_delay": 0.0,
         "redemptions": [], "projects": {}, "hb_acks": [], "sessions": [], "leases": {}, "lapses": [], "conns": 0,
         # name_key → {name, client_id, client_secret, state, enrollment}
         "machines": {"testhost": {"name": "testhost", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                                   "state": "active", "enrollment": ""}},
         # token → {id, state, machine, ttl_s, expires}
         "enrollments": {},
         # the org's directory: project id → {name, kind, machine?, retired}; machine name → {online, seen}
         "registry": {}, "online": {}, "orgs": {}}


def machine_project_id(machine):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "smns-machine:%s:%s" % (ORG, machine.lower())))


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%03dZ" % (t % 1 * 1000)


def org_frame():
    """The org's directory as the Registry sends it (the lock held)."""
    active = sorted(m["name"] for m in state["machines"].values() if m["state"] == "active")
    return {"t": "org",
            "projects": [{"id": pid, **r} for pid, r in state["registry"].items()],
            "machines": [{"name": n, "online": state["online"].get(n, {}).get("online", False),
                          "seen": state["online"].get(n, {}).get("seen")} for n in active]}


def directory_changed():
    """Every open stream is sent the directory whole (the lock held)."""
    frame = org_frame()
    for m, s in state["streams"].items():
        if not s.ended.is_set():
            s.put([frame])
            state["orgs"][m] = state["orgs"].get(m, 0) + 1


def register(pid, name, kind="hub"):
    """A project into the directory (the lock held): a machine's own by its
    id, whoever registers it first; a retired machine project whose machine
    is active again is reactivated. Whether the directory changed."""
    held = state["registry"].get(pid)
    owner = next((m["name"] for m in state["machines"].values()
                  if m["state"] == "active" and machine_project_id(m["name"]) == pid), None)
    if held is not None and not (held["retired"] and owner):
        return False
    if owner:
        state["registry"][pid] = {"name": owner, "kind": "machine", "machine": owner, "retired": False}
    else:
        state["registry"][pid] = {"name": name, "kind": kind, "retired": False}
    return True


def machine_online(machine):
    lease = state["leases"].get(machine)
    return lease is not None and not lease["lapsed"] and lease_live(machine, lease)


def refresh_online():
    """Each machine's online state as its lease says it now; a change goes
    out in the directory (the lock held)."""
    changed = False
    for m in state["machines"].values():
        if m["state"] != "active":
            continue
        online = machine_online(m["name"])
        held = state["online"].setdefault(m["name"], {"online": False, "seen": None})
        if held["online"] != online:
            held.update(online=online, seen=iso(time.time()))
            changed = True
    if changed:
        directory_changed()


register(machine_project_id("testhost"), "testhost")


def sse(frame):
    """One SSE event. A string no UTF-8 carries (a lone surrogate a lying hub
    sends) goes as its JSON escape."""
    text = json.dumps(frame, ensure_ascii=False)
    try:
        text.encode()
    except UnicodeEncodeError:
        text = json.dumps(frame)
    return ("event: %s\ndata: %s\n\n" % (frame.get("t", ""), text)).encode()


def is_machine_name(name):
    """DX7: ^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$, never hub or legacy in any case."""
    return (isinstance(name, str) and 1 <= len(name) <= 63 and set(name) <= NAME_CHARS
            and name[0] not in "._-" and name.lower() not in ("hub", "legacy"))


def same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class Stream:
    def __init__(self, generation, machine):
        self.generation = generation
        self.machine = machine
        self.queue = queue.Queue()
        self.ended = threading.Event()
        self.parts = {}
        self.muted = False  # a half-open stream: no heartbeat, nothing written, nothing closed

    def put(self, frames, done=None):
        self.queue.put((frames, done))

    def end(self):
        self.ended.set()
        self.queue.put((None, None))


def lease_live(machine, lease):
    """Whether the stream a lease belongs to is still open (lock held)."""
    s = state["streams"].get(machine)
    return s is not None and s.generation == lease["generation"] and not s.ended.is_set()


def sweep_leases():
    """The hub's alarm: the lease of a stream still open whose time ran out
    lapses, recorded once until a renewal."""
    while True:
        time.sleep(0.05)
        with lock:
            now = time.time()
            for machine, lease in state["leases"].items():
                if lease_live(machine, lease) and not lease["lapsed"] and now > lease["expires"]:
                    lease["lapsed"] = True
                    state["lapses"].append({"machine": machine, "generation": lease["generation"], "at": now})
            refresh_online()


def expire_lapsed(now):
    """A token past its time expires; a pending one releases its name."""
    for e in state["enrollments"].values():
        if e["state"] in ("open", "pending") and now > e["expires"]:
            if e["state"] == "pending":
                state["machines"].pop(e["machine"].lower(), None)
            e["state"] = "expired"


# ------------------------------------------------------------- the log plane (the lock held)


def project(pid):
    return state["projects"].setdefault(pid, {"name": "", "writers": {}, "open": {}, "audit": [], "archive": None})


def vector(p):
    return {w: evs[-1]["seq"] for w, evs in sorted(p["writers"].items()) if evs}


def to_machine(machine, generation, frames):
    """Queue frames for a machine's stream of `generation`; False when that
    stream is gone (the machine leaves the project's fan-out)."""
    s = state["streams"].get(machine)
    if s is None or s.generation != generation or s.ended.is_set():
        return False
    s.put(frames)
    return True


def fan_out(pid, p, events, sender=None):
    for m, gen in list(p["open"].items()):
        if m != sender and not to_machine(m, gen, [{"t": "events", "project": pid, "events": events}]):
            del p["open"][m]


def shape_error(e):
    if not isinstance(e, dict):
        return "an event is a JSON object"
    w = e.get("writer")
    if not (isinstance(w, str) and re.fullmatch(r"[^/]+/.+", w) and not any(ord(c) < 32 or ord(c) == 127 for c in w)):
        return "writer is <machine>/<feed>, without control characters"
    if not (type(e.get("seq")) is int and e["seq"] >= 1):
        return "seq is a positive integer"
    if not (isinstance(e.get("ts"), str) and isinstance(e.get("kind"), str)):
        return "ts and kind are strings"
    mac = e.get("mac")
    if not (isinstance(mac, dict) and all(isinstance(mac.get(k), str) and B64URL.fullmatch(mac[k])
                                          for k in ("nonce", "value"))):
        return "mac is {nonce, value}"
    if len(json.dumps(e, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")) > FRAME_LIMIT:
        return TOO_LARGE
    return None


def apply(machine, s, frame, replies):
    """One frame up, as DC3's Project applies it; replies to this machine go
    to `replies`, in order."""
    t = frame.get("t")
    if t == "hb-ack":
        state["hb_acks"].append({"machine": machine, "generation": frame.get("generation"), "at": frame.get("at"),
                                 "received": time.time()})
        lease = state["leases"].get(machine)
        if lease is not None and frame.get("generation") == s.generation == lease["generation"]:
            lease.update(expires=time.time() + LEASE, lapsed=False)
            refresh_online()
        return
    if t == "session":
        now = time.time()
        state["sessions"].append({"machine": machine, "generation": s.generation, "message": frame.get("message"),
                                  "received": now, "at": now})
        return
    pid = frame.get("project")
    if not (isinstance(pid, str) and PROJECT_ID.fullmatch(pid)):
        replies.append({"t": "refused", "project": str(pid),
                        "refusal": {"reason": "bad-shape", "message": "the frame names no .smns project id"}})
        return
    p = project(pid)
    p.setdefault("follow", {})

    def refuse(refusal):
        replies.append({"t": "refused", "project": pid, "refusal": refusal})
        p["audit"].append({"kind": "refused", "machine": machine, **refusal})

    if t == "hello":
        have = frame.get("have")
        if not (isinstance(frame.get("name"), str) and frame["name"] and isinstance(have, dict)
                and all(type(v) is int and v >= 0 for v in have.values())
                and isinstance(frame.get("follow", False), bool)):
            return refuse({"reason": "bad-shape", "message": "hello is {project, name, have: {writer: seq}, follow?: boolean}"})
        p["name"] = p["name"] or frame["name"]
        p["open"][machine] = s.generation
        p["follow"][machine] = frame.get("follow", False)
        if register(pid, frame["name"]):
            directory_changed()
        if state["leases"].get(machine, {}).get("generation") != s.generation:
            state["leases"][machine] = {"generation": s.generation, "expires": time.time() + LEASE, "lapsed": False}
            refresh_online()
        replies.append({"t": "have", "project": pid, "have": vector(p), "archive": p["archive"] == machine})
        for w, evs in sorted(p["writers"].items()):
            suffix = [e for e in evs if e["seq"] > have.get(w, 0)]
            for i in range(0, len(suffix), BATCH):
                replies.append({"t": "events", "project": pid, "events": suffix[i:i + BATCH]})
        return
    if p["open"].get(machine) != s.generation:
        return refuse({"reason": "not-open", "message": "send hello for this project on this stream first"})
    if t == "rejected":
        p["audit"].append({"kind": "rejected", "machine": machine,
                           **{k: v for k, v in frame.items() if k in ("event", "nonce", "reason", "message")}})
        return
    if t != "events":
        return
    events = frame.get("events")
    if not isinstance(events, list):
        return refuse({"reason": "bad-shape", "message": "events is a list"})
    accepted, stopped = [], set()
    for e in events:
        problem = shape_error(e)
        if problem:
            # As DC3's Project: the refusal names the position the event
            # carried, and stops its writer for the rest of the frame.
            position = {}
            if isinstance(e, dict) and isinstance(e.get("writer"), str):
                position["writer"] = e["writer"]
            if isinstance(e, dict) and isinstance(e.get("seq"), (int, float)) and not isinstance(e.get("seq"), bool):
                position["seq"] = e["seq"]
            if "writer" in position:
                if position["writer"] in stopped:
                    continue
                stopped.add(position["writer"])
            refuse({"reason": "too-large" if problem == TOO_LARGE else "bad-shape", **position, "message": problem})
            continue
        w, seq = e["writer"], e["seq"]
        if w in stopped:
            continue
        head = w.split("/", 1)[0]
        mine = (head == machine) or (head == "legacy" and p["archive"] == machine)
        if not mine or head == "hub":
            stopped.add(w)
            refuse({"reason": "writer-not-yours", "writer": w, "seq": seq, "message": "%s writes only %s/…" % (machine, machine)})
            continue
        evs = p["writers"].setdefault(w, [])
        last = evs[-1]["seq"] if evs else 0
        if seq <= last:
            held = next((x for x in evs if x["seq"] == seq), None)
            if held is None or not same(held, e):
                stopped.add(w)
                refuse({"reason": "conflict", "writer": w, "seq": seq, "message": "a different payload is stored at this position"})
        elif seq == last + 1:
            evs.append(e)
            accepted.append(e)
        else:
            stopped.add(w)
            replies.append({"t": "resend", "project": pid, "writer": w, "from": last + 1})
    if accepted:
        fan_out(pid, p, accepted, sender=machine)


def join_part(s, frame):
    """A part's whole frame once its set is complete, else None."""
    pid, index, count, data = frame.get("id"), frame.get("index"), frame.get("count"), frame.get("data")
    if not (isinstance(pid, str) and isinstance(data, str) and type(count) is int and type(index) is int
            and 0 <= index < count):
        raise ValueError("a malformed part")
    held = s.parts.setdefault(pid, {"count": count, "slices": {}})
    if held["count"] != count:
        raise ValueError("count differs within its set")
    held["slices"][index] = data
    if len(held["slices"]) < count:
        return None
    del s.parts[pid]
    return json.loads("".join(held["slices"][i] for i in range(count)))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        with lock:
            state["conns"] += 1
            self.conn = state["conns"]   # this connection's number, on every POST it carries

    def log_message(self, *_args):
        pass

    def parse_request(self):
        self.consumed = False   # whether this request's body was read
        return super().parse_request()

    def reply(self, status, body, close=False):
        """A JSON answer; the connection closes after it when asked, or when
        the request's body was not read (the next request would start in it)."""
        close = close or (not self.consumed and int(self.headers.get("Content-Length") or 0) > 0)
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, code, message):
        self.reply(status, {"error": code, "message": message})

    def body(self):
        self.consumed = True
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
                        register(machine_project_id(m["name"]), m["name"])
                        directory_changed()
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
                last = state["last"]
                self.reply(200, {
                    "generation": last.generation if last else 0, "generations": state["generations"],
                    "connected": any(not s.ended.is_set() for s in state["streams"].values()),
                    "posted": state["posted"], "redemptions": state["redemptions"], "faults": state["faults"],
                    "post_faults": state["post_faults"], "hb_acks": state["hb_acks"], "sessions": state["sessions"],
                    "leases": {m: {"generation": lease["generation"],
                                   "online": not lease["lapsed"] and lease_live(m, lease)}
                               for m, lease in state["leases"].items()},
                    "lapses": state["lapses"],
                    "projects": {pid: {"name": p["name"], "vector": vector(p), "writers": p["writers"],
                                       "open": p["open"], "audit": p["audit"], "follow": p.get("follow", {})}
                                 for pid, p in state["projects"].items()},
                    "registry": state["registry"], "online": state["online"], "orgs": state["orgs"],
                    "machines": [{k: v for k, v in m.items() if k != "client_secret"}
                                 for m in state["machines"].values()],
                    "enrollments": [{k: v for k, v in e.items()} for e in state["enrollments"].values()]})
        elif self.path.startswith("/control/since?"):
            q = urllib.parse.parse_qs(self.path.split("?", 1)[1])
            with lock:
                self.reply(200, {k: state[k][int(q.get(k, ["0"])[0]):] for k in ("sessions", "hb_acks")})
        else:
            self.reply(404, {"error": "not-found"})

    def do_POST(self):
        if self.path == "/machine/frames":
            machine = self.admitted()
            if machine:
                self.frames(machine)
        elif self.path == "/machine/enroll":
            self.redeem()
        elif self.path == "/control/send":
            self.send_frames(json.loads(self.body()))
        elif self.path == "/control/inject":
            req = json.loads(self.body())
            with lock:
                p = project(req["project"])
                for e in req["events"]:
                    evs = p["writers"].setdefault(e["writer"], [])
                    evs.append(e)
                    evs.sort(key=lambda x: x["seq"])
                fan_out(req["project"], p, req["events"])
            self.reply(200, {"injected": len(req["events"])})
        elif self.path == "/control/drop":
            req = json.loads(self.body() or b"{}")
            with lock:
                dropped = [m for m, s in state["streams"].items()
                           if req.get("machine") in (None, m) and not s.ended.is_set()]
                for m in dropped:
                    state["streams"][m].end()
            self.reply(200, {"dropped": dropped})
        elif self.path == "/control/release":
            with lock:
                held, state["release"] = state["release"], threading.Event()
            held.set()
            self.reply(200, {})
        elif self.path == "/control/mute":
            req = json.loads(self.body())
            with lock:
                s = state["streams"].get(req["machine"])
                if s is not None:
                    s.muted = True
            self.reply(200, {"muted": s is not None})
        elif self.path == "/control/post-fault":
            with lock:
                state["post_faults"] = list(json.loads(self.body()).get("faults", []))
            self.reply(200, {"faults": state["post_faults"]})
        elif self.path == "/control/post-delay":
            with lock:
                state["post_delay"] = float(json.loads(self.body()).get("seconds") or 0)
            self.reply(200, {"seconds": state["post_delay"]})
        elif self.path == "/control/archive":
            req = json.loads(self.body())
            with lock:
                project(req["project"])["archive"] = req["machine"]
            self.reply(200, {})
        elif self.path == "/control/register":
            req = json.loads(self.body())
            with lock:
                if register(req["project"], req["name"], req.get("kind", "hub")):
                    directory_changed()
            self.reply(200, {})
        elif self.path == "/control/retire":
            req = json.loads(self.body())
            with lock:
                held = state["registry"][req["project"]]
                if held["retired"] != bool(req["retired"]):
                    held["retired"] = bool(req["retired"])
                    directory_changed()
            self.reply(200, {})
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

    def frames(self, machine):
        """DX2's POST: refused whole, or applied frame by frame, answered once
        its replies are on the stream."""
        text = self.body().decode("utf-8", "replace")
        with lock:
            delay = state["post_delay"]
        time.sleep(delay)
        done = threading.Event()
        with lock:
            s = state["streams"].get(machine)
            record = {"machine": machine, "generation": self.headers.get("X-Desk-Generation"), "body": text,
                      "conn": self.conn}
            if s is None or s.ended.is_set() or self.headers.get("X-Desk-Generation") != str(s.generation):
                state["posted"].append({**record, "status": 409})
                return self.reply(409, {"error": "stale-generation", "message": "the POST names no current stream"})
            fault = next((f for f in state["post_faults"] if f.get("machine") in (None, machine)
                          and ('"t":"%s"' % f["has"] if f.get("has") else "") in text.replace(" ", "")), None)
            if fault is not None:
                state["post_faults"].remove(fault)
                fault = fault["fault"]
            if fault == "503":
                state["posted"].append({**record, "status": 503})
                return self.reply(503, {"error": "unavailable"})
            if fault in HELD:
                state["posted"].append({**record, "status": "held", "fault": fault})
                release = state["release"]
        if fault in HELD:
            try:
                if fault == "stall-headers":  # half a head, then nothing
                    self.wfile.write(b"HTTP/1.0 200 OK\r\nContent-")
                    self.wfile.flush()
                elif fault == "stall-body":  # a whole head, one byte of its ten, then nothing
                    self.send_response(200)
                    self.send_header("Content-Length", "10")
                    self.end_headers()
                    self.wfile.write(b"{")
                    self.wfile.flush()
                release.wait(60)
                if fault == "hold":
                    self.reply(503, {"error": "held, then released unapplied"}, close=True)
            except OSError:
                pass  # the poster gave up on it
            self.close_connection = True
            return None
        with lock:
            frames = []
            for i, line in enumerate(text.split("\n")):
                if not line.strip():
                    continue
                try:
                    frame = json.loads(line)
                except ValueError:
                    frame = None
                if not (isinstance(frame, dict) and isinstance(frame.get("t"), str)):
                    state["posted"].append({**record, "status": 400})
                    return self.reply(400, {"error": "bad-shape", "line": i})
                frames.append(frame)
            replies = []
            for frame in frames:
                if frame["t"] == "part":
                    try:
                        frame = join_part(s, frame)
                    except ValueError:
                        state["posted"].append({**record, "status": 400})
                        return self.reply(400, {"error": "bad-shape", "message": "a malformed part"})
                    if frame is None:
                        continue
                apply(machine, s, frame, replies)
            status = 502 if fault == "apply-502" else 200
            state["posted"].append({**record, "status": status})
            s.put(replies, done)
        done.wait(WAIT)
        if status != 200:
            return self.reply(status, {"error": "bad-gateway"})
        return self.reply(200, {"ok": True, "frames": len(frames)})

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
            if machine in state["streams"]:
                state["streams"][machine].end()
            generation = state["generations"].get(machine, 0) + 1
            state["generations"][machine] = generation
            mine = state["streams"][machine] = state["last"] = Stream(generation, machine)
            mine.put([{"t": "welcome", "org": ORG, "machine": machine, "generation": generation,
                       "heartbeat_ms": HEARTBEAT_MS}, org_frame()])
            state["orgs"][machine] = state["orgs"].get(machine, 0) + 1
            refresh_online()   # the old stream's lease ended with it
            lock.notify_all()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")   # no length: the stream ends with its connection
        self.close_connection = True
        self.end_headers()
        period = HEARTBEAT_MS / 1000
        beat = time.monotonic() + period
        try:
            while not mine.ended.is_set():
                # On a timer, as the hub's alarm writes it: frames flowing
                # down do not put the heartbeat off.
                if time.monotonic() >= beat:
                    beat = time.monotonic() + period
                    if not mine.muted:
                        now = time.time()
                        at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + ".%03dZ" % (now % 1 * 1000)
                        self.wfile.write(sse({"t": "hb", "at": at}))
                        self.wfile.flush()
                try:
                    frames, done = mine.queue.get(timeout=max(0.0, beat - time.monotonic()))
                except queue.Empty:
                    continue
                if frames is None:
                    break
                # Half-open: the hub's write completes, and nothing arrives.
                if not mine.muted:
                    for frame in frames:
                        self.wfile.write(sse(frame))
                    self.wfile.flush()
                if done is not None:
                    done.at = time.time()
                    done.set()
        except OSError:
            pass
        finally:
            mine.ended.set()
            with lock:
                refresh_online()
            # Anyone waiting on a write to this stream is let go.
            while True:
                try:
                    _, done = mine.queue.get_nowait()
                except queue.Empty:
                    break
                if done is not None:
                    done.set()

    def send_frames(self, req):
        deadline = time.time() + WAIT
        with lock:
            def target():
                s = state["streams"].get(req["machine"]) if req.get("machine") else state["last"]
                return s if s is not None and not s.ended.is_set() else None
            while target() is None and time.time() < deadline:
                lock.wait(deadline - time.time())
            s = target()
        if s is None:
            self.reply(504, {"error": "no stream"})
            return
        frames = list(req.get("frames") or []) * int(req.get("repeat") or 1)
        done = threading.Event()
        started = time.time()
        s.put(frames, done)
        if not done.wait(max(0.0, deadline - time.time())):
            self.reply(504, {"error": "the write did not finish", "generation": s.generation})
            return
        self.reply(200, {"generation": s.generation, "written": len(frames), "took": time.time() - started,
                         "at": getattr(done, "at", None)})


threading.Thread(target=sweep_leases, daemon=True).start()
server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
server.daemon_threads = True
with open(PORT_FILE + ".tmp", "w") as f:
    f.write(str(server.server_address[1]))
os.replace(PORT_FILE + ".tmp", PORT_FILE)
server.serve_forever()
