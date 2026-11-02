"""The bridge child's gate client: a MAWS lane B session's observer on the
engine host's holder socket (O12 M4a; OX10, O16 Interfaces §E as its fix
wave corrected it), and the private relay between that socket and the bridge
mod, which owns the fence (hooks/mods/bridge-holder.tsx).

The child owns the socket; the mod owns the fence. The mod can neither open a
Unix stream nor read its own pid, so the child speaks OX10 for it and relays:
host frames go to the mod as lines on the child's stdout, and the mod's
readiness, its installed-arm acknowledgements and its turns come back as
POST /holder on a socket of this client's own. Nothing here touches the
bridge's ordinary work: not its HTTP server, its ingest or export, its lock,
a delivery-file lock, the long poll, or the startup that reads the seed. Only
the stdout lock is shared (one line at a time on fd 1), and only the relay
thread waits on it: a blocked stdout withholds an `armed` (the mod never sees
the arm), never an `hb`.

The gate (OX10; MAWS_HOLDER_SOCKET, newline-delimited JSON, discriminator `t`):

    observer → host   hello {protocol: 1, session, pid, childPid}   first, once per connection
                      hb                                           at once after welcome, then every HEARTBEAT_S
                      armed {fence}                                one per arm, after the mod installed it, in arm order
                      turn {fence, origin, delivery?}              as the mod asks
    host → observer   welcome {protocol: 1}; arm {fence, leaseMs}; disarm {fence};
                      proceed {fence}; stop {fence, reason}

`session` is the engine session the child serves (`--session`), `pid`
claude's (the child's parent), `childPid` the child's own. The client
connects only once the mod said it is ready and the lane verdict is `match`;
`mismatch` never connects, and `unresolved` waits for M3's retries. Every
connection opens the path anew, says hello, and serves only after a valid
welcome; a refused connect, a missing or invalid welcome (none within
WELCOME_WAIT_S), a close or a failed write ends it, and the next attempt
follows BACKOFF_S later with a fresh hello. There is no periodic hello and no
hello on a gap: on the fixed gate a later `hb` heals a silent row on the same
connection (R5).

Acknowledgements pair first in, first out (R1): the host pairs each `armed`
with the oldest unanswered `arm` of that fence on the same connection. So
every arm a connection carries is numbered (`arm`, 1, 2, … in the order
received) and relayed; the mod acknowledges each by its number once it has
installed it; and the client writes `armed {fence}` only for the oldest arms
that are acknowledged, in order: an acknowledgement for a later arm waits
until every earlier one is acknowledged, then all go together, one `armed`
per arm, never coalesced. An arm of a connection that has ended is never
acknowledged on another. A late `armed` (after the host's `proceed` or
`disarm`) is valid and changes nothing at the host (R4).

The private relay (the contract the mod consumes):

    stdout, first line of a child whose session is marked and whose
    environment names MAWS_HOLDER_SOCKET (unless its module already holds
    `mismatch`), written as soon as POST /holder answers and before the
    ordinary hello and its seed:
        {"op": "holder", "bootstrap": {"socket": <path of the /holder socket>,
                                       "nonce": <hex>, "generation": <hex>,
                                       "pid": <claude's pid>, "childPid": <this child's pid>,
                                       "processAge": <seconds claude's process has run, boot clock> | null}}
        (`processAge` is the mod's evidence of a fresh process, O12 M4b.)
    stdout, each host frame of a welcomed connection, in the order received:
        {"op": "holder", "epoch": E, "frame": {...}}            welcome, disarm, proceed, stop
        {"op": "holder", "epoch": E, "arm": N, "frame": {"t": "arm", "fence", "leaseMs"}}
    `generation` names this child and `epoch` one connection of it,
    "<generation>.<n>": unique across children and connections, so a fence
    is (epoch, fence), and a fence number reused by a restarted host, or by
    the next child, is another fence. None of these lines carries `id`: a
    line with one is a client's command, and `holder` is refused through
    POST /command (sminos_bridge.CHILD_LINES), so it is never one of these.

    POST /holder on bootstrap.socket, header X-Bridge-Nonce: bootstrap.nonce
    (409 {ok: false, code: "nonce"} without it), body an object naming this
    child's `generation` (409 code "generation" otherwise) and one `kind`:
        {kind: "ready", generation, launch?, upgrade?, observe?, retained?}
            the mod's fence receiver is installed: the client may connect
            (once the verdict is `match`). Idempotent. The first that names
            an activation (O12 M4b) is the one taken: before its first hello
            the client chooses the process's delivery mode
            (sminos_holder_deliveries): `activate` with `launch` (the
            process's, M7's) and `retained` (the receipt ids the live
            conversation holds, a resume's rows), or `observer_upgrade` when
            `upgrade` (a process a module ran in before this one: `legacy`,
            an M4a observer going on as before, or with `observe` false one
            no observer served staying unobserved: this child never says
            hello); a record that exists is kept as it is, and one that
            cannot be read leaves receipts off (said once), the observer
            connecting anyway.
            → 200 {ok: true, lane, epoch: <the welcomed connection's> | null, receipts: <the mode> | null}
        {kind: "armed", generation, epoch, arm, fence}
            the mod installed arm N of epoch E (fence must be that arm's).
            → 200 {ok: true, sent: <armed frames this call wrote>, waiting: <arms ahead still unacknowledged>}
              200 {ok: true, duplicate: true}      that arm was acknowledged already: nothing more goes
              409 {ok: false, code: "epoch"}       E is not the live welcomed connection: nothing goes, ever
              404 {ok: false, code: "arm"}         no arm N on E
              400 {ok: false, code: "shape"}       a malformed body, or a fence that is not arm N's
        {kind: "turn", generation, epoch, fence, origin, delivery?}
            origin is query | cron | task | peer | unknown; delivery, when present, an
            opaque string of 1 to DELIVERY_MAX characters (M4a's production turns omit it).
            → 200 {ok: true} once `turn` is written on E's connection;
              409 {ok: false, code: "epoch"} when E is not live (nothing was written)
            The host's answer (`proceed`, `stop`, or a `disarm`) comes back as a
            relay line of E, never in this answer.
        {kind: "wait", generation, ms}
            held until the relay writes its next line, or `ms` (at most
            WAIT_MAX_MS) has passed, or the client closes; then
            → 200 {ok: true, relayed: <whether a line went meanwhile>}
            A model request the mod holds at the fence keeps one of these in
            flight: the engine runs a hook's own budget (10 s) only while none
            of its calls is, and the observer's fallback (lease plus margin,
            15 s) is longer. It is a wait, not a channel: the answer it waits
            for is a relay line.
        {kind: "admit", generation, session, ids}
            the mod admitted a model request carrying these receipts' rows,
            in `session` (the one the report was made in: a /clear's replay
            names the old one). Recorded durably before the answer
            (sminos_holder_deliveries.admit): → 200 with its answer, `ok`
            false with code `storage` replayed by the mod, `legacy` ending
            the report. Until the activation's outcome is known (it waits on
            a deliverer's mode lock, or for the lane) a report waits up to
            ACTIVATION_WAIT_S, then is answered `ok` false with code
            `pending`, recording nothing: replayed, never taken for legacy.
        {kind: "release", generation, session, items: [{id, attempt, present}]}
            stopped attempts the mod found free to retry in this launch
            (sminos_holder_deliveries.release, the launch the activation's);
            → 200 with its answer, as admit's.

GET /status on the bridge's own socket adds `holder: {ready, epoch,
attempts, receipts?}`, for diagnosis only (`receipts`, the mode the
activation found, is read by no deliverer from here: each reads the record).
Every answer here but `wait`'s, `admit`'s and `release`'s comes at once: the
route waits on nothing but the gate connection's own write; those two wait
on the receipts' short lock, never on the gate or its heartbeat. A heartbeat is connection liveness, not permission
to signal: only an `armed` the mod caused grants that.
"""

import collections
import json
import os
import queue
import select
import socket
import socketserver
import sys
import threading
import time
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler

PROTOCOL = 1
SOCKET_ENV = "MAWS_HOLDER_SOCKET"
NONCE_HEADER = "X-Bridge-Nonce"
ORIGINS = ("query", "cron", "task", "peer", "unknown")
HOST_FRAMES = ("welcome", "arm", "disarm", "proceed", "stop")
LINE_MAX = 64 * 1024          # a host line longer than this is not OX10: the connection ends
BODY_MAX = 64 * 1024          # a POST /holder body
DELIVERY_MAX = 256            # characters of a turn's opaque delivery id
REPORT_MAX = 512              # receipts one admission or release report names
ID_MAX = 64                   # characters of a receipt id, a launch or a session a report names
ACTIVATION_WAIT_S = 1.0       # a report waits this long for the activation before it is answered `pending`
WAIT_MAX_MS = 20000           # a held wait, under the engine's 30-second bound on the mod's fetch
RELAY_QUEUED = 256            # host frames waiting for stdout; past it the connection ends (the mod is not reading)
WRITE_WAIT_S = 5.0            # a gate write that makes no progress this long ends the connection
READ_STEP_S = 0.25            # how often a reader waiting on the gate looks at whether it should stop


def _seconds(name, default):
    """A timing in seconds; production's unless a test scales it."""
    try:
        v = float(os.environ.get(name) or default)
    except ValueError:
        return default
    return v if v > 0 else default


HEARTBEAT_S = _seconds("SMINOS_HOLDER_HEARTBEAT", 5.0)
BACKOFF_S = _seconds("SMINOS_HOLDER_BACKOFF", 5.0)
WELCOME_WAIT_S = _seconds("SMINOS_HOLDER_WELCOME_WAIT", 10.0)


def gate_path():
    """The engine host's holder socket, as its launch named it, or None."""
    return os.environ.get(SOCKET_ENV) or None


def _is_int(v, least=0):
    return type(v) is int and v >= least


def _is_id(v):
    """A string a report may name (a receipt id, a session): its checks are the receipts module's."""
    return isinstance(v, str) and 0 < len(v) <= ID_MAX


def _host_frame(frame):
    """Whether a host line is one of OX10's host frames in its shape."""
    if not isinstance(frame, dict) or frame.get("t") not in HOST_FRAMES:
        return False
    t = frame["t"]
    if t == "welcome":
        return frame.get("protocol") == PROTOCOL
    if not _is_int(frame.get("fence")):
        return False
    if t == "arm":
        return _is_int(frame.get("leaseMs"), 1)
    if t == "stop":
        return isinstance(frame.get("reason"), str)
    return True


class _Conn:
    """One gate connection: its socket, its epoch, the arms it carried in
    the order received (number → {fence, acked}), and how far `armed` has
    gone. `lock` orders every write on the socket and guards the arms."""

    def __init__(self, sock, epoch):
        self.sock = sock
        self.epoch = epoch
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.arms = collections.OrderedDict()
        self.received = 0     # arms numbered so far
        self.answered = 0     # arms whose `armed` was written, the oldest first


class Holder:
    """The gate client and its private route, for one bridge child."""

    def __init__(self, session, gate, route, emit, log=None, launch=None):
        self.session = session
        self.launch = launch              # the process's (the child's --launch); the mod's ready names it too
        self.gate = gate                  # the engine host's socket path
        self.route = route                # this client's /holder socket path
        self.emit = emit                  # writes one line on stdout (the bridge's, under its lock)
        self.log = log or (lambda text: sys.stderr.write("sminos bridge: holder: %s\n" % text))
        self.generation = uuidlib.uuid4().hex[:16]
        self.nonce = uuidlib.uuid4().hex
        self.pid = os.getppid()           # claude
        self.child_pid = os.getpid()
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.closing = threading.Event()
        self.ready = False                # the mod's fence receiver is installed
        self.lane = None                  # match | mismatch | unresolved, as the child knows it
        self.conn = None                  # the welcomed connection, while there is one
        self.attempts = 0                 # connections tried, for /status
        self.relay = queue.Queue(RELAY_QUEUED)
        self.relayed = threading.Condition()
        self.lines_out = 0                # relay lines written on stdout, for a held wait
        self.server = None
        self.said = None
        # Receipt activation (O12 M4b): what the mod's first ready asked, and
        # the process's delivery mode once the gate thread chose it, before
        # its first hello: gate | legacy | unknown (unreadable: fail closed);
        # None while not activated (no ready yet, or no launch to activate with).
        self.activation = None
        self.activated = False
        self.settled = threading.Event()  # the activation's outcome is known: reports may be answered
        self.receipts = None

    # -- life

    def start(self):
        """Serves the route, says the bootstrap, and starts the gate and the
        relay. The bootstrap goes only once POST /holder can answer."""
        try:
            os.unlink(self.route)
        except FileNotFoundError:
            pass
        server = _Server(self.route, _Handler, bind_and_activate=False)
        server.holder = self
        server.server_bind()
        os.chmod(self.route, 0o600)
        server.server_activate()
        self.server = server
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True).start()
        self.emit({"op": "holder", "bootstrap": {"socket": self.route, "nonce": self.nonce,
                                                 "generation": self.generation,
                                                 "pid": self.pid, "childPid": self.child_pid,
                                                 "processAge": self._process_age()}})
        threading.Thread(target=self._run_relay, daemon=True).start()
        threading.Thread(target=self._run_gate, daemon=True).start()
        return self

    def _process_age(self):
        """Seconds claude's process has run, on the boot clock no wall-clock
        step moves (sminos_holder_deliveries.process): the mod's evidence
        that its module is the process's first. None when unreadable."""
        try:
            import sminos_holder_deliveries as D
            proc = D.process(self.pid)
        except Exception:  # noqa: BLE001 — no evidence, which the mod takes as an existing process
            return None
        age = proc["age"] if proc is not None else None
        return round(age, 3) if isinstance(age, (int, float)) and age != float("inf") else None

    def close(self):
        self.closing.set()
        with self.lock:
            conn, self.conn = self.conn, None
            self.wake.notify_all()
        with self.relayed:
            self.relayed.notify_all()
        if conn is not None:
            self._end(conn, None)
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        try:
            os.unlink(self.route)
        except OSError:
            pass

    def set_lane(self, lane):
        with self.lock:
            self.lane = lane
            self.wake.notify_all()

    def status(self):
        """What /status says of the gate, for diagnosis only: the delivery
        mode it reports is the record's, read by no deliverer from here."""
        with self.lock:
            conn = self.conn
            return {"ready": self.ready, "epoch": conn.epoch if conn is not None else None,
                    "attempts": self.attempts, **({"receipts": self.receipts} if self.receipts is not None else {})}

    def _say(self, text):
        """A state worth a line in the mod's debug log, once while it lasts."""
        if text != self.said:
            self.said = text
            self.log(text)

    def _orphaned(self):
        """claude is gone: this child serves no one, and its gate says so by
        closing. Takes no lock: the gate's wait calls it holding its own."""
        if os.getppid() != self.pid:
            self.closing.set()
            return True
        return False

    # -- the gate

    def _run_gate(self):
        while not self.closing.is_set():
            with self.lock:
                while not (self.ready and self.lane == "match") and not self.closing.is_set():
                    self.wake.wait(1.0)
                    if self._orphaned():
                        break
                if self.closing.is_set():
                    return
            if not self.activated:
                self._activate()
            if (self.activation or {}).get("observe") is False:
                self.log("receipts: an existing process no observer served: it stays unobserved, no hello")
                return
            with self.lock:
                self.attempts += 1
                epoch = "%s.%d" % (self.generation, self.attempts)
            try:
                self._connect(epoch)
            except Exception as err:  # noqa: BLE001 — the gate must keep trying, whatever one attempt met
                self._say("the connection failed: %s: %s" % (type(err).__name__, err))
            if self.closing.wait(BACKOFF_S):
                return

    def _activate(self):
        """The process's delivery mode, chosen once per child before its first
        hello (O12 M4b; sminos_holder_deliveries holds the record): `gate`
        with the mod's launch on a fresh process, `legacy` for an M4a
        observer's (`upgrade`), the record as it is when one exists (a
        reload, a child restart, a /clear, a deliverer's first handoff). One
        that cannot be read or written is said and leaves receipts off; the
        observer connects either way: observing is not settling."""
        self.activated = True
        try:
            self._choose_mode()
        finally:
            self.settled.set()

    def _choose_mode(self):
        act = self.activation or {}
        if not act.get("upgrade") and not act.get("launch"):
            self.log("receipts: the mod named no launch: none activated")
            return
        try:
            import sminos_holder_deliveries as D
            if act.get("upgrade"):
                rec = D.observer_upgrade(self.pid)
            else:
                rec = D.activate(self.pid, act["launch"], self.session, retained=act.get("retained") or ())
            self.receipts = rec["mode"]
            self.log("receipts: process %d is %s (%s)" % (self.pid, rec["mode"], rec.get("by")))
        except Exception as err:  # noqa: BLE001 — unreadable, unwritable or unknown: fail closed, keep observing
            self.receipts = "unknown"
            self.log("receipts: not activated, deliveries to this process fail closed: %s: %s" % (
                type(err).__name__, err))

    def _connect(self, epoch):
        """One connection's life: hello, welcome, then its frames until it ends."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(WRITE_WAIT_S)
        try:
            sock.connect(self.gate)
        except OSError as err:
            sock.close()
            self._say("no gate answers at %s (%s); again in %gs" % (self.gate, err, BACKOFF_S))
            return
        conn = _Conn(sock, epoch)
        try:
            if not self._write(conn, {"t": "hello", "protocol": PROTOCOL, "session": self.session,
                                      "pid": self.pid, "childPid": self.child_pid}):
                return
            lines = _Lines(sock)
            first = lines.next(WELCOME_WAIT_S, self.closing)
            if not _host_frame(first) or first.get("t") != "welcome":
                self._say("the gate gave no welcome (%s); again in %gs" % (
                    "closed" if first is None else json.dumps(first)[:200], BACKOFF_S))
                return
            with self.lock:
                if self.closing.is_set():
                    return
                self.conn = conn
            self._say("welcomed (epoch %s)" % epoch)
            self._relay({"op": "holder", "epoch": epoch, "frame": first}, conn)
            threading.Thread(target=self._beat, args=(conn,), daemon=True).start()
            while not conn.closed.is_set():
                frame = lines.next(None, conn.closed)
                if frame is None:
                    if not conn.closed.is_set():
                        self._say("the gate closed epoch %s; again in %gs" % (epoch, BACKOFF_S))
                    return
                self._take(conn, frame)
        finally:
            self._end(conn, None)

    def _take(self, conn, frame):
        """A host frame of a welcomed connection, relayed to the mod; an arm
        is numbered first, in the order received."""
        if not _host_frame(frame) or frame["t"] == "welcome":
            self.log("a frame that is not OX10's host vocabulary was dropped: %s" % json.dumps(frame)[:200])
            return
        line = {"op": "holder", "epoch": conn.epoch, "frame": frame}
        if frame["t"] == "arm":
            with conn.lock:
                conn.received += 1
                conn.arms[conn.received] = {"fence": frame["fence"], "acked": False}
                line = {"op": "holder", "epoch": conn.epoch, "arm": conn.received, "frame": frame}
        self._relay(line, conn)

    def _beat(self, conn):
        """`hb` at once, then every HEARTBEAT_S, while the connection lives:
        its own thread, waiting on nothing but the connection's write."""
        while not conn.closed.is_set():
            if self._orphaned():
                self._end(conn, "claude is gone")
                return
            if not self._write(conn, {"t": "hb"}):
                return
            conn.closed.wait(HEARTBEAT_S)

    def _write(self, conn, frame):
        with conn.lock:
            return self._write_locked(conn, frame)

    def _write_locked(self, conn, frame):
        if conn.closed.is_set():
            return False
        try:
            conn.sock.sendall((json.dumps(frame) + "\n").encode())
            return True
        except OSError as err:
            self._end(conn, "a write failed (%s)" % err)
            return False

    def _end(self, conn, why):
        if why is not None and not conn.closed.is_set():
            self._say("epoch %s ended: %s; again in %gs" % (conn.epoch, why, BACKOFF_S))
        conn.closed.set()
        with self.lock:
            if self.conn is conn:
                self.conn = None
        try:
            conn.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conn.sock.close()

    # -- the relay to the mod

    def _relay(self, line, conn):
        try:
            self.relay.put_nowait(line)
        except queue.Full:
            # The mod has not read a line in RELAY_QUEUED host frames: the
            # connection ends rather than lose one, which would break the
            # pairing of acknowledgements with arms (R1).
            self._end(conn, "the mod is not reading the relay (%d lines waiting)" % RELAY_QUEUED)

    def _run_relay(self):
        """Writes the relayed lines on stdout in order: the one thread here
        that waits on the stdout the bridge shares."""
        while True:
            line = self.relay.get()
            try:
                self.emit(line)
            except OSError:   # stdout is gone, and with it the mod
                return
            with self.relayed:
                self.lines_out += 1
                self.relayed.notify_all()

    # -- the route

    def post(self, nonce, body):
        """POST /holder: (status, answer)."""
        if nonce != self.nonce:
            return 409, {"ok": False, "code": "nonce", "error": "this route is another child's"}
        if not isinstance(body, dict) or body.get("generation") != self.generation:
            return 409, {"ok": False, "code": "generation", "error": "this child is generation %s" % self.generation}
        kind = body.get("kind")
        if kind == "ready":
            return self._ready(body)
        if kind == "armed":
            return self._armed(body)
        if kind == "turn":
            return self._turn(body)
        if kind == "wait":
            return self._wait(body)
        if kind == "admit":
            return self._admit(body)
        if kind == "release":
            return self._release(body)
        return 400, {"ok": False, "code": "shape", "error": "kind is ready, armed, turn, wait, admit or release"}

    def _ready(self, body):
        launch, upgrade, retained = body.get("launch"), body.get("upgrade"), body.get("retained")
        observe = body.get("observe")
        if not ((launch is None or (isinstance(launch, str) and 0 < len(launch) <= ID_MAX))
                and upgrade in (None, True, False) and observe in (None, True, False)
                and (retained is None or (isinstance(retained, list) and len(retained) <= REPORT_MAX
                                          and all(_is_id(r) for r in retained)))):
            return 400, {"ok": False, "code": "shape",
                         "error": "ready names maybe a launch, upgrade and observe (booleans) and retained receipt ids"}
        with self.lock:
            # The first ready that names an activation is the one taken: the
            # gate thread activates once, before its first hello.
            if self.activation is None and (launch is not None or upgrade is not None):
                self.activation = {"launch": launch or self.launch, "upgrade": upgrade is True,
                                   "retained": list(retained or ()), "observe": observe is not False}
            self.ready = True
            self.wake.notify_all()
            conn = self.conn
            return 200, {"ok": True, "lane": self.lane, "epoch": conn.epoch if conn is not None else None,
                         "receipts": self.receipts}

    def _pending(self):
        """A report before the activation's outcome is known (it waits on a
        deliverer's mode lock, or on the lane): answered retryably, never as
        the `legacy` a missing record would read as."""
        if self.settled.wait(ACTIVATION_WAIT_S):
            return None
        return 200, {"ok": False, "code": "pending", "error": "receipts are not activated yet: replay the report"}

    def _admit(self, body):
        """The mod admitted a model request carrying these receipts' rows:
        recorded durably before the answer (sminos_holder_deliveries.admit),
        whose `ok` false with code `storage` the mod replays."""
        ids, session = body.get("ids"), body.get("session", self.session)
        if not (isinstance(ids, list) and 0 < len(ids) <= REPORT_MAX and all(_is_id(i) for i in ids)
                and _is_id(session)):
            return 400, {"ok": False, "code": "shape", "error": "admit names receipt ids and their session"}
        pending = self._pending()
        if pending is not None:
            return pending
        import sminos_holder_deliveries as D
        return 200, D.admit(ids, self.pid, session)

    def _release(self, body):
        """A stopped attempt the mod found free to retry in this launch
        (sminos_holder_deliveries.release), recorded as admit is."""
        items, session = body.get("items"), body.get("session", self.session)
        if not (isinstance(items, list) and 0 < len(items) <= REPORT_MAX and _is_id(session)
                and all(isinstance(i, dict) and _is_id(i.get("id")) and _is_int(i.get("attempt"), 1)
                        and type(i.get("present")) is bool for i in items)):
            return 400, {"ok": False, "code": "shape",
                         "error": "release names items {id, attempt, present} and their session"}
        pending = self._pending()
        if pending is not None:
            return pending
        launch = (self.activation or {}).get("launch") or self.launch
        if not launch:
            return 409, {"ok": False, "code": "launch", "error": "this child knows no launch of its process"}
        import sminos_holder_deliveries as D
        return 200, D.release([{"id": i["id"], "attempt": i["attempt"], "present": i["present"]} for i in items],
                              self.pid, launch, session)

    def _wait(self, body):
        """Held until the relay writes a line, `ms` passes or the client
        closes: the call the mod keeps in flight while a request waits."""
        ms = body.get("ms")
        if not _is_int(ms, 1):
            return 400, {"ok": False, "code": "shape", "error": "wait names ms, a positive integer"}
        deadline = time.monotonic() + min(ms, WAIT_MAX_MS) / 1000.0
        with self.relayed:
            seen = self.lines_out
            while self.lines_out == seen and not self.closing.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.relayed.wait(min(remaining, READ_STEP_S))
            return 200, {"ok": True, "relayed": self.lines_out != seen}

    def _live(self, epoch):
        with self.lock:
            conn = self.conn
        return conn if conn is not None and conn.epoch == epoch and not conn.closed.is_set() else None

    def _armed(self, body):
        epoch, arm, fence = body.get("epoch"), body.get("arm"), body.get("fence")
        if not (isinstance(epoch, str) and _is_int(arm, 1) and _is_int(fence)):
            return 400, {"ok": False, "code": "shape", "error": "armed names an epoch, an arm and its fence"}
        conn = self._live(epoch)
        if conn is None:
            return 409, {"ok": False, "code": "epoch", "error": "epoch %s is not the gate's connection" % epoch}
        with conn.lock:
            if conn.closed.is_set():
                return 409, {"ok": False, "code": "epoch", "error": "epoch %s ended" % epoch}
            if arm <= conn.answered:
                return 200, {"ok": True, "duplicate": True}
            entry = conn.arms.get(arm)
            if entry is None:
                return 404, {"ok": False, "code": "arm", "error": "epoch %s carried no arm %d" % (epoch, arm)}
            if entry["fence"] != fence:
                return 400, {"ok": False, "code": "shape",
                             "error": "arm %d is fence %d's, not %d's" % (arm, entry["fence"], fence)}
            if entry["acked"]:
                return 200, {"ok": True, "duplicate": True}
            entry["acked"] = True
            sent = 0
            while conn.answered + 1 in conn.arms and conn.arms[conn.answered + 1]["acked"]:
                head = conn.arms.pop(conn.answered + 1)
                if not self._write_locked(conn, {"t": "armed", "fence": head["fence"]}):
                    return 409, {"ok": False, "code": "epoch", "error": "epoch %s ended" % epoch}
                conn.answered += 1
                sent += 1
            waiting = sum(1 for n, e in conn.arms.items() if n < arm and not e["acked"])
            return 200, {"ok": True, "sent": sent, "waiting": waiting}

    def _turn(self, body):
        epoch, fence, origin, delivery = body.get("epoch"), body.get("fence"), body.get("origin"), body.get("delivery")
        if not (isinstance(epoch, str) and _is_int(fence) and origin in ORIGINS
                and (delivery is None or (isinstance(delivery, str) and 0 < len(delivery) <= DELIVERY_MAX))):
            return 400, {"ok": False, "code": "shape",
                         "error": "turn names an epoch, a fence, an origin (%s) and maybe a delivery" % "|".join(ORIGINS)}
        conn = self._live(epoch)
        frame = {"t": "turn", "fence": fence, "origin": origin, **({"delivery": delivery} if delivery is not None else {})}
        if conn is None or not self._write(conn, frame):
            return 409, {"ok": False, "code": "epoch", "error": "epoch %s is not the gate's connection" % epoch}
        return 200, {"ok": True}


class _Lines:
    """A connection's lines, parsed: None once it closed, failed, sent a
    line that is not JSON or longer than LINE_MAX, or (with a wait) gave
    nothing in time, or once `stop` is set."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def next(self, wait, stop):
        deadline = None if wait is None else time.monotonic() + wait
        while b"\n" not in self.buf:
            if len(self.buf) > LINE_MAX or stop.is_set():
                return None
            step = READ_STEP_S if deadline is None else min(READ_STEP_S, deadline - time.monotonic())
            if step <= 0:
                return None
            try:
                readable, _, _ = select.select([self.sock], [], [], step)
                if not readable:
                    continue
                chunk = self.sock.recv(65536)
            except (OSError, ValueError):   # ValueError: the socket was closed under the select
                return None
            if not chunk:
                return None
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        if len(line) > LINE_MAX:   # its newline came in the chunk that crossed the bound
            return None
        try:
            return json.loads(line)
        except ValueError:
            return None


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "sminos-holder/%d" % PROTOCOL

    def log_message(self, *_args):
        pass

    def address_string(self):
        return "local"

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self):
        self._send(404, {"ok": False, "error": "this socket serves POST /holder alone"})

    def do_POST(self):
        if self.path != "/holder":
            return self._send(404, {"ok": False, "error": "this socket serves POST /holder alone"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > BODY_MAX:
                raise ValueError("body too large")
            body = json.loads(self.rfile.read(n) or b"null")
        except ValueError as e:
            return self._send(400, {"ok": False, "code": "shape", "error": "the body is not JSON: %s" % e})
        self._send(*self.server.holder.post(self.headers.get(NONCE_HEADER), body))


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], OSError):
            return
        super().handle_error(request, client_address)
