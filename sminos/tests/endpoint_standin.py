"""A stand-in for the mawsd endpoint's RL10 side (O10 Interfaces §D), for
sminos's tests only: what sminos's uplink meets on a machine cut over to its
endpoint, hermetically and with no hub behind it. It is written to §D's
frames, name for name; O10's own conversation fixture, once copied, is the
conformance check (rl10_conformance.py), this the scriptable rig.

In-process (M6's test_words.py, test_rl10.py):

    ep = Endpoint(directory)          # rl10.json and rl10.sock in `directory`
    ep.start()                        # listening, rl10.json written (0600)
    ep.wait(lambda f: f["t"] == "hello" ...)   # frames sminos sent
    ep.send({"t": "revoked", ...})    # a frame down the live connection
    ep.drop() / ep.restart() / ep.stop()

As a subprocess (the shell suites):

    python3 endpoint_standin.py serve <directory> [<config JSON>]
    python3 endpoint_standin.py ctl <directory> <op> [<JSON>]

`serve` also listens on <directory>/ctl.sock, and writes it last, so its
presence says the stand-in is up. `ctl`'s ops: `state` (everything below,
as JSON), `send` {frames}, `set` {field: value} (the fields below), `drop`,
`restart`, `rl10` {field: value, mode?} (rl10.json rewritten with those
fields; `mode` its permission bits), `unlink-rl10`, `stop`.

What it does on each connection, one at a time (a new one replaces the last,
as sminos's reconnect does):
- the first line must be `hello` with `token` (else the connection closes
  with nothing written, as the endpoint does — or with `refuse {reason}`
  when `refuse_reason` is set — and the hello is kept in `refused`);
- then `welcome {protocol, capabilities, build, identity, policy,
  stateVersion}`, with `policy` the endpoint's: the hello's when it holds
  none (kept in policy.json), as §D says; `revoked` (the whole set), `org`
  when one is set, and `legacy-key?` when it holds no legacy.json and
  `ask_legacy` is set;
- every line after is kept (`received`, each with its connection's number),
  `part`s joined, and answered: `policy-set` with `policy` (its fields
  applied) unless `answer_policy` is off; `legacy-key` kept in legacy.json
  unless `persist_legacy` is off (an endpoint that dies before keeping it);
  `rpc-result` with `rpc-ack {opId, nonce}` when `ack_results` is on;
  `words?` with `words {id, verdict}` when `verdicts` names one for its id,
  or `verdict` is set (a callable in-process: (frame) → verdict or None).
  `handler`, in-process, is called with each frame first and may return
  frames to send (the later halves' hook).

The log plane, as O10 M6 relays it (with no hub behind it): a project's
`hello` is answered `have {project, have}` with what the stand-in holds of
it, unless `relay` is off (RL1 down: no `have`, so sminos uploads nothing).
Each event uploaded (`events` up) is taken in its upload form — the event
with `created` derived from its `ts` (`created_of`) — and kept in `logs`;
one carrying another `created`, or a `ts` of neither form, is refused
`malformed`, and another body at a position held is refused `conflict`
(`refused {project, refusal}` down). Every raw line received is kept in
`lines`. Down, for a test to send: `echo` (an own event as the endpoint
returns it, `created`, `sig` and `attest` added), `arriving` (another's
event wrapped `{event, signer, owners?}`), `resend`; and `rpc`, `query`,
`tombstone` (§D's frames, the RPC nested under `rpc` as DX2 nests it).

Fields (constructor keywords, `set`'s keys): token, identity, policy,
revoked, org, build, state_version, refuse_reason, ask_legacy,
persist_legacy, answer_policy, ack_results, verdicts, verdict, relay.
"""

import base64
import json
import os
import re
import secrets
import socket
import sys
import threading
import time

LINE_MAX = 1 << 20   # a line at most 1 MiB of UTF-8 (O10 §D); larger text goes as `part`s
FIELDS = ("token", "identity", "policy", "revoked", "org", "build", "state_version", "refuse_reason", "ask_legacy",
          "persist_legacy", "answer_policy", "ack_results", "verdicts", "verdict", "relay")
TS_MS = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z")
TS_S = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def iso(t=None):
    t = time.time() if t is None else t
    return time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime(t)) + "%03dZ" % int((t % 1) * 1000)


def write_private(path, data, mode=0o600):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(data, f)
        f.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def created_of(ts):
    """The signed `created` the endpoint derives from an event's `ts` (O10
    M6's upload form): verbatim with milliseconds, `.000` added to a whole
    second; None for any other form."""
    if isinstance(ts, str) and TS_MS.fullmatch(ts):
        return ts
    if isinstance(ts, str) and TS_S.fullmatch(ts):
        return ts[:-1] + ".000Z"
    return None


def upload_form(e):
    """An event as the endpoint signs it: `created` derived from its `ts`;
    None when it carries another `created`, or a `ts` of neither form."""
    created = created_of(e.get("ts"))
    if created is None or e.get("created", created) != created:
        return None
    return {**e, "created": created}


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def lines_of(frame):
    """The lines a frame goes as: its JSON, or `part`s of it past LINE_MAX."""
    text = json.dumps(frame, separators=(",", ":"))
    if len(text.encode("utf-8")) <= LINE_MAX:
        return [text]
    pid, step = secrets.token_urlsafe(16), (LINE_MAX - 256) // 6
    pieces = [text[i:i + step] for i in range(0, len(text), step)]
    return [json.dumps({"t": "part", "id": pid, "index": i, "count": len(pieces), "data": p}, separators=(",", ":"))
            for i, p in enumerate(pieces)]


class Conn:
    """One accepted connection: its number, its socket, its reads and writes."""

    def __init__(self, number, sock):
        self.number, self.sock = number, sock
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.closed = False
        self.parts = {}

    def write(self, frame):
        data = b"".join(line.encode("utf-8") + b"\n" for line in lines_of(frame))
        with self.lock:
            if self.closed:
                raise OSError("the connection is closed")
            self.sock.sendall(data)

    def read_line(self, timeout=None):
        self.sock.settimeout(timeout)
        while b"\n" not in self.buf:
            if len(self.buf) > LINE_MAX:
                raise ValueError("a line past 1 MiB")
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                return None
            self.buf += chunk
        end = self.buf.index(b"\n")
        line = bytes(self.buf[:end])
        del self.buf[:end + 1]
        if len(line) > LINE_MAX:
            raise ValueError("a line past 1 MiB")
        return line.decode("utf-8")

    def joined(self, frame):
        """A whole frame: this one, or the one its `part` completes; else None."""
        if frame.get("t") != "part":
            return frame
        held = self.parts.setdefault(frame["id"], {})
        held[frame["index"]] = frame["data"]
        if len(held) < frame["count"]:
            return None
        del self.parts[frame["id"]]
        return json.loads("".join(held[i] for i in range(frame["count"])))

    def close(self):
        with self.lock:
            self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class Endpoint:
    """The stand-in: a Unix socket in `directory` (or `socket_path`), the
    endpoint's state files beside it (policy.json, legacy.json), rl10.json
    naming the socket. See the module's docstring for what it does."""

    def __init__(self, directory, socket_path=None, **fields):
        self.dir = directory
        os.makedirs(directory, mode=0o700, exist_ok=True)
        self.socket_path = socket_path or os.path.join(directory, "rl10.sock")
        self.token = secrets.token_hex(32)
        self.identity = {"org": "org-1", "hub": "http://127.0.0.1:9", "name": "testhost", "former": [],
                         "ref": "machine-ref-1", "enrolled": iso()}
        self.policy = None
        self.revoked = {"version": 1, "devices": [], "members": [], "keys": []}
        self.org = None
        self.build = "endpoint-standin"
        self.state_version = 1
        self.refuse_reason = None
        self.ask_legacy = True
        self.persist_legacy = True
        self.answer_policy = True
        self.ack_results = True
        self.verdicts = {}
        self.verdict = None
        self.relay = True
        self.handler = None
        self.set(**fields)
        self.cv = threading.Condition()
        self.received = []      # [(connection number, frame)], in order, hellos included
        self.lines = []         # [(connection number, line)]: every line after a connection's hello, as it came
        self.logs = {}          # project id → {writer: {seq: the event in its upload form}}
        self.hellos = []        # [(connection number, hello)] accepted
        self.refused = []       # [(connection number, first line as JSON or text)] refused
        self.conns = 0
        self.current = None
        self.listener = None
        self.stopping = False
        self.load()

    # ---------------------------------------------------- its files

    def load(self):
        """What the endpoint keeps on disk, read again (a restart)."""
        held = read_json(os.path.join(self.dir, "policy.json"))
        if isinstance(held, dict):
            self.policy = held

    def legacy(self):
        return read_json(os.path.join(self.dir, "legacy.json"))

    def rl10_path(self):
        return os.path.join(self.dir, "rl10.json")

    def write_rl10(self, mode=0o600, **override):
        d = {"socket": self.socket_path, "pid": os.getpid(), "build": self.build, "token": self.token,
             "protocol": 1, **override}
        write_private(self.rl10_path(), d, mode)

    def set(self, **fields):
        for k, v in fields.items():
            if k not in FIELDS:
                raise KeyError("no field %s" % k)
            setattr(self, k, v)

    # ---------------------------------------------------- running

    def start(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        self.listener.listen(8)
        threading.Thread(target=self.accept, name="endpoint-accept", daemon=True).start()
        self.write_rl10()
        return self

    def stop(self):
        self.stopping = True
        self.drop()
        if self.listener is not None:
            self.listener.close()
        for path in (self.socket_path, self.rl10_path()):
            try:
                os.unlink(path)
            except OSError:
                pass

    def accept(self):
        while not self.stopping:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                return
            with self.cv:
                self.conns += 1
                conn = Conn(self.conns, sock)
            threading.Thread(target=self.serve, args=(conn,), name="endpoint-conn", daemon=True).start()

    def drop(self):
        """The live connection closed, as an endpoint's crash closes it."""
        with self.cv:
            conn, self.current = self.current, None
        if conn is not None:
            conn.close()

    def restart(self):
        """A crash and a restart: the connection dropped, and what was held
        only in memory forgotten (the policy read again from its file)."""
        self.drop()
        self.policy = None
        self.load()

    def send(self, *frames):
        with self.cv:
            conn = self.current
        if conn is None:
            raise OSError("no connection to send on")
        for frame in frames:
            conn.write(frame)

    # ---------------------------------------------------- one connection

    def serve(self, conn):
        try:
            try:
                line = conn.read_line(10)
            except (OSError, ValueError):
                line = None
            hello = None
            if line is not None:
                try:
                    hello = json.loads(line)
                except ValueError:
                    hello = None
            if not (isinstance(hello, dict) and hello.get("t") == "hello" and hello.get("token") == self.token):
                with self.cv:
                    self.refused.append((conn.number, hello if hello is not None else line))
                    self.cv.notify_all()
                if self.refuse_reason:
                    try:
                        conn.write({"t": "refuse", "reason": self.refuse_reason})
                    except OSError:
                        pass
                return
            old = None
            with self.cv:
                old, self.current = self.current, conn
                self.hellos.append((conn.number, hello))
                self.received.append((conn.number, hello))
                self.cv.notify_all()
            if old is not None:
                old.close()
            if self.policy is None and isinstance(hello.get("policy"), dict):
                self.policy = hello["policy"]
                write_private(os.path.join(self.dir, "policy.json"), self.policy)
            conn.write({"t": "welcome", "protocol": {"major": 1, "minor": 0}, "capabilities": [], "build": self.build,
                        "identity": self.identity, "policy": self.policy, "stateVersion": self.state_version})
            conn.write({"t": "revoked", **self.revoked})
            if self.org is not None:
                conn.write({"t": "org", **self.org})
            if self.ask_legacy and self.legacy() is None:
                conn.write({"t": "legacy-key?"})
            while True:
                line = conn.read_line()
                if line is None:
                    return
                with self.cv:
                    self.lines.append((conn.number, line))
                frame = conn.joined(json.loads(line))
                if frame is None:
                    continue
                with self.cv:
                    self.received.append((conn.number, frame))
                    self.cv.notify_all()
                self.answer(conn, frame)
        except (OSError, ValueError):
            return
        finally:
            with self.cv:
                if self.current is conn:
                    self.current = None
                self.cv.notify_all()
            conn.close()

    def answer(self, conn, frame):
        t = frame.get("t")
        out = list(self.handler(frame) or []) if self.handler is not None else []
        if t == "policy-set" and self.answer_policy:
            self.policy = {**(self.policy or {}), **{k: frame[k] for k in ("read_only", "ceiling") if k in frame}}
            write_private(os.path.join(self.dir, "policy.json"), self.policy)
            out.append({"t": "policy", **self.policy})
        elif t == "legacy-key" and self.persist_legacy:
            write_private(os.path.join(self.dir, "legacy.json"), {"org": frame.get("org"), "key": frame.get("key")})
        elif t == "rpc-result" and self.ack_results:
            out.append({"t": "rpc-ack", "opId": frame.get("opId"), "nonce": frame.get("nonce")})
        elif t == "words?":
            verdict = self.verdicts.get(frame.get("id"))
            if verdict is None and self.verdict is not None:
                verdict = self.verdict(frame) if callable(self.verdict) else self.verdict
            if verdict is not None:
                out.append({"t": "words", "id": frame.get("id"), "verdict": verdict})
        elif t == "hello" and isinstance(frame.get("project"), str) and self.relay:
            held = self.logs.get(frame["project"], {})
            out.append({"t": "have", "project": frame["project"], "have": {w: max(ss) for w, ss in held.items() if ss}})
        elif t == "events" and isinstance(frame.get("project"), str) and isinstance(frame.get("events"), list):
            out += self.take(frame["project"], frame["events"])
        for f in out:
            conn.write(f)

    def take(self, project, events):
        """Events uploaded: each kept in its upload form, or refused (the
        frames that say so)."""
        out = []
        with self.cv:
            held = self.logs.setdefault(project, {})
            for e in events:
                form = upload_form(e) if isinstance(e, dict) else None
                writer, seq = (e.get("writer"), e.get("seq")) if isinstance(e, dict) else (None, None)
                if form is None:
                    reason = "malformed"
                elif seq in held.get(writer, {}) and held[writer][seq] != form:
                    reason = "conflict"
                else:
                    held.setdefault(writer, {})[seq] = form
                    continue
                out.append({"t": "refused", "project": project,
                            "refusal": {"reason": reason, "writer": writer, "seq": seq}})
        return out

    # ---------------------------------------------------- frames down, built for a test

    def echo(self, project, writer, seq, **changes):
        """An event of this machine's, held here, as the endpoint returns it
        down (the ledger's echo): its upload form with `sig` and `attest`
        added, signed by this machine; `changes` alter its body."""
        with self.cv:
            form = dict(self.logs[project][writer][seq])
        event = {**form, "sig": {"kid": "k-machine", "sig": b64url(b"\x01" * 64)},
                 "attest": {"owners": [], "ownersProof": [], "origin": {"kind": "terminal"}, "stateVersion": 1},
                 **changes}
        return {"event": event, "signer": {"kind": "machine", "ref": self.identity.get("ref"),
                                           "name": self.identity.get("name"), "keyId": "k-machine"}, "owners": []}

    @staticmethod
    def arriving(event, signer=None, owners=None):
        """Another's event as the endpoint sends it down, verified."""
        out = {"event": event, "signer": signer or {"kind": "device", "member": "mem-1", "device": "dev-1",
                                                     "keyId": "k-dev-1"}}
        if owners is not None:
            out["owners"] = owners
        return out

    def events(self, project, wrapped):
        self.send({"t": "events", "project": project, "events": list(wrapped)})

    def resend(self, project, writer, start):
        self.send({"t": "resend", "project": project, "writer": writer, "from": start})

    def rpc(self, name, project, args, **fields):
        """An authorized lane A action as §D sends it down: DX6's Rpc nested
        under `rpc`, `machine` the welcome's name, a fresh `nonce`, `opId`,
        `created` and `opCreated`; `fields` override any of them. Sent, and
        returned."""
        now = iso()
        rpc = {"rpc": name, "project": project, "machine": self.identity.get("name"), "member": "mem-1",
               "device": "dev-1", "created": now, "nonce": b64url(os.urandom(16)), "opId": b64url(os.urandom(18)),
               "opCreated": now, "args": args, "fingerprint": b64url(os.urandom(32)), **fields}
        self.send({"t": "rpc", "rpc": rpc})
        return rpc

    def query(self, op, op_created=None):
        self.send({"t": "query", "opId": op, **({"opCreated": op_created} if op_created is not None else {})})

    def tombstone(self, op):
        self.send({"t": "tombstone", "opId": op})

    # ---------------------------------------------------- the test's reads

    def frames(self, t=None, conn=None):
        with self.cv:
            return [f for n, f in self.received if (t is None or f.get("t") == t) and (conn is None or n == conn)]

    def wait(self, pred, timeout=30):
        """The first frame received that `pred` holds for, waiting for it."""
        deadline = time.monotonic() + timeout
        with self.cv:
            while True:
                for _, f in self.received:
                    if pred(f):
                        return f
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("no such frame within %gs" % timeout)
                self.cv.wait(left)

    def wait_until(self, pred, timeout=30):
        """Waits until pred() holds of the stand-in's state."""
        deadline = time.monotonic() + timeout
        with self.cv:
            while not pred():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("not within %gs" % timeout)
                self.cv.wait(min(left, 0.1))

    def state(self):
        with self.cv:
            return {"conns": self.conns, "connected": self.current is not None,
                    "current": self.current.number if self.current else None,
                    "hellos": [{"conn": n, "hello": h} for n, h in self.hellos],
                    "refused": [{"conn": n, "first": f} for n, f in self.refused],
                    "received": [{"conn": n, "frame": f} for n, f in self.received],
                    "identity": self.identity, "policy": self.policy, "revoked": self.revoked,
                    "legacy": self.legacy(), "token": self.token}


# ------------------------------------------------------------- the subprocess


def serve_main(directory, config):
    ep = Endpoint(directory, **config)
    ep.start()
    ctl_path = os.path.join(directory, "ctl.sock")
    if os.path.exists(ctl_path):
        os.unlink(ctl_path)
    ctl = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    ctl.bind(ctl_path + ".tmp")
    ctl.listen(8)
    os.replace(ctl_path + ".tmp", ctl_path)
    while not ep.stopping:
        sock, _ = ctl.accept()
        with sock:
            conn = Conn(0, sock)
            try:
                req = json.loads(conn.read_line(30) or "{}")
                answer = control(ep, req)
            except Exception as e:  # noqa: BLE001 — said to the test
                answer = {"error": repr(e)}
            try:
                sock.sendall((json.dumps(answer) + "\n").encode("utf-8"))
            except OSError:
                pass   # the test's ctl went away: the stand-in serves on
    ctl.close()
    os.unlink(ctl_path)


def control(ep, req):
    op, arg = req.get("op"), req.get("arg") or {}
    if op == "state":
        return ep.state()
    if op == "send":
        ep.send(*arg["frames"])
    elif op == "set":
        ep.set(**arg)
    elif op == "drop":
        ep.drop()
    elif op == "restart":
        ep.restart()
    elif op == "rl10":
        mode = int(str(arg.pop("mode", "600")), 8)
        ep.write_rl10(mode, **arg)
    elif op == "unlink-rl10":
        os.unlink(ep.rl10_path())
    elif op == "stop":
        ep.stop()
    else:
        return {"error": "no op %r" % op}
    return {"ok": True}


def ctl_main(directory, op, arg):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(os.path.join(directory, "ctl.sock"))
    sock.sendall((json.dumps({"op": op, "arg": arg}) + "\n").encode("utf-8"))
    # The answer is read whole, to the stand-in's close: a state holding the
    # uploads of a machine's projects is past RL10's line bound, which is no
    # bound of this test-only channel.
    sock.settimeout(60)
    data = bytearray()
    while True:
        chunk = sock.recv(1 << 16)
        if not chunk:
            break
        data += chunk
    print(data.decode("utf-8").rstrip("\n"))
    sock.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "serve":
        serve_main(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
    elif len(sys.argv) >= 4 and sys.argv[1] == "ctl":
        ctl_main(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]) if len(sys.argv) > 4 else {})
    else:
        sys.exit("usage: endpoint_standin.py serve <directory> [<config JSON>] | ctl <directory> <op> [<JSON>]")
