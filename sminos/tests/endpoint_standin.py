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
    python3 endpoint_standin.py hand <source directory> <dest directory>
    python3 endpoint_standin.py relay <directory> <directory>...

`serve` also listens on <directory>/ctl.sock, and writes it last, so its
presence says the stand-in is up. `ctl`'s ops: `state` (everything below,
as JSON), `send` {frames}, `set` {field: value} (the fields below), `drop`,
`restart`, `rl10` {field: value, mode?} (rl10.json rewritten with those
fields; `mode` its permission bits), `refuse` {project, writer, seq,
reason?}, `accepted` {project, after?} and `opened` (below), `unlink-rl10`,
`stop`.

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
  or `verdict` is set (a callable in-process: (frame) → verdict or None),
  and `refuse` for one naming no `project`, as the endpoint answers it;
  `reach?` (P5 O18 D3) likewise with `reach {id, verdict, reason?}` from
  `reach_verdicts` by id, else `reach_verdict` (a callable in-process:
  (frame) → verdict or None; a verdict is `deliver`, `refuse` — sent with
  reason `not-reachable` — or (`refuse`, reason)), silent when neither
  names one, as an endpoint that holds no record of the session is;
  `restated` (the end of sminos's restatement after a welcome) is kept.
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
`tombstone` (§D's frames, the RPC nested under `rpc` as DX2 nests it); a
`spent {project, writer, seq, reason}` is sent as any frame (`send`).

P5 O18 (message reach): `capabilities` is what the welcome advertises (an
O18 endpoint's `["access", "reach"]`; none by default, an older
endpoint), and `audiences` the bodies of the `audience {session, owners,
members, digest, policyRev}` frames sent after each welcome, only to an
sminos whose hello advertises `audience`, as the endpoint sends them
(`audience_frame` builds one); a later one is sent as any frame (`send`).

The hub's admission, as the endpoint passes the hub's `have` down unchanged
(P5 O18 D6): `admit` (on by default) off holds admission back — an upload is
taken (kept, so an echo can be built) but counts in no `have` until `admit`
is set on again; `withheld` ({project: {writer: [seq | [from, to], ...]}})
is the hub's tombstones, sent as the `have`'s `withheld` and counted in its
vector; `archive` (a boolean, or {project: boolean}) is the `have`'s archive
designation. `refuse_audience` (a list of writers) refuses each upload of
those writers `audience`, the writer's later events in the frame passed
over, as the endpoint refuses a stream it does not sign. `refuse_upload` (ctl
`refuse` {project, writer, seq, reason?}) sends `refused {project, refusal:
{reason, writer, seq}}`, `not-reachable` by default, with no message.

The hub's reach judgement (P5 O18 D5), in-process: `withhold`, a callable
(project, event in its upload form) → truthy, withholds the upload it holds
for at a position not yet held, as the hub withholds an event out of reach:
the position is added to `withheld` (so the next `have` lists it and counts
it), the body kept aside, and `refused {reason: not-reachable, writer, seq}`
sent with no message; the writer goes on. A resend there is refused
`not-reachable` again with the same body, `conflict` with another. None (the
default) withholds nothing.

Two machines, each its sminos and its stand-in (#153 M3d's compositions):
`accepted(project, after)` is what a stand-in took of a project, past
`after` ({writer: seq}) and up to what is admitted, each event in its
`echo` form, as the relay carries it to another machine's endpoint;
`opened()` the live connection's number and the projects its hellos opened.
`hand(source, dest, cursor)` (the `hand` command for two stand-ins `serve`
runs) is one pass of that relay: source's accepted events into dest's live
connection as arrivals, for each project it opened, past what its last hello
holds and what was handed since; the `relay` command is a pass each way
between every two of the stand-ins it names. What carries them between
endpoints in production is MAWS's relay; the hand-off carries the frames
themselves, never one written by hand.

Fields (constructor keywords, `set`'s keys): token, identity, policy,
revoked, org, build, state_version, refuse_reason, ask_legacy,
persist_legacy, answer_policy, ack_results, verdicts, verdict,
reach_verdicts, reach_verdict, relay, capabilities, audiences, admit,
withheld, archive, refuse_audience, withhold.
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
          "persist_legacy", "answer_policy", "ack_results", "verdicts", "verdict", "reach_verdicts", "reach_verdict",
          "relay", "capabilities",
          "audiences", "admit", "withheld", "archive", "refuse_audience", "withhold")
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


def audience_frame(session, owners, members=None, policy_rev=0, withdrawn=None):
    """An `audience` frame's body as the endpoint sends it (O18 Interfaces
    §B): members None for a listed session, its digest beside them; for a
    local session whose change at that policyRev withdrew members, those
    members as `withdrawn` (O18 M4's interface change: absent when it
    withdrew none)."""
    import hashlib
    digest = None if members is None else hashlib.sha256(
        json.dumps(sorted(set(members)), separators=(",", ":")).encode()).hexdigest()[:16]
    return {"session": session, "owners": list(owners), "members": None if members is None else sorted(set(members)),
            "digest": digest, "policyRev": policy_rev, **({"withdrawn": sorted(set(withdrawn))} if withdrawn else {})}


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
        self.reach_verdicts = {}
        self.reach_verdict = None
        self.members = {}   # session → its last `member` frame (the member state an action's context is read from)
        self.relay = True
        self.capabilities = []   # the welcome's (an O18 endpoint's: ["access", "reach"])
        self.audiences = []      # `audience` frames' bodies, sent after each welcome to an sminos whose hello says `audience`
        self.admit = True
        self.withheld = {}
        self.archive = False
        self.refuse_audience = []
        self.withhold = None
        self.withheld_bodies = {}   # (project id, writer, seq) → the body withheld there (withhold)
        self.unadmitted = {}    # project id → {writer: {seq}}: taken while admission was held back
        self.handler = None
        self.cv = threading.Condition()
        self.set(**fields)
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
        for k in fields:
            if k not in FIELDS:
                raise KeyError("no field %s" % k)
        with self.cv:
            for k, v in fields.items():
                setattr(self, k, v)
            if fields.get("admit") is True:
                self.unadmitted.clear()   # what was held back is admitted

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
            conn.write({"t": "welcome", "protocol": {"major": 1, "minor": 0}, "capabilities": list(self.capabilities),
                        "build": self.build, "identity": self.identity, "policy": self.policy,
                        "stateVersion": self.state_version})
            conn.write({"t": "revoked", **self.revoked})
            if self.org is not None:
                conn.write({"t": "org", **self.org})
            if self.ask_legacy and self.legacy() is None:
                conn.write({"t": "legacy-key?"})
            if "audience" in (hello.get("capabilities") or []):
                for body in self.audiences:
                    conn.write({"t": "audience", **body})
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
        elif t == "member" and isinstance(frame.get("session"), str):
            if frame.get("gone") is True:
                self.members.pop(frame["session"], None)
            else:
                self.members[frame["session"]] = frame
        elif t == "words?" and not isinstance(frame.get("project"), str):
            out.append({"t": "words", "id": frame.get("id"), "verdict": "refuse"})   # O10 M6: no project, no words
        elif t == "words?":
            verdict = self.verdicts.get(frame.get("id"))
            if verdict is None and self.verdict is not None:
                verdict = self.verdict(frame) if callable(self.verdict) else self.verdict
            if verdict is not None:
                out.append({"t": "words", "id": frame.get("id"), "verdict": verdict})
        elif t == "reach?":
            verdict = self.reach_verdicts.get(frame.get("id"))
            if verdict is None and self.reach_verdict is not None:
                verdict = self.reach_verdict(frame) if callable(self.reach_verdict) else self.reach_verdict
            if verdict is not None:
                verdict, reason = (verdict, "not-reachable") if isinstance(verdict, str) else tuple(verdict)
                out.append({"t": "reach", "id": frame.get("id"), "verdict": verdict,
                            **({"reason": reason} if verdict == "refuse" else {})})
        elif t == "hello" and isinstance(frame.get("project"), str) and self.relay:
            out.append(self.have(frame["project"]))
        elif t == "events" and isinstance(frame.get("project"), str) and isinstance(frame.get("events"), list):
            out += self.take(frame["project"], frame["events"])
        for f in out:
            conn.write(f)

    def have(self, project):
        """The `have` the hub answers a hello with, as the endpoint passes it
        down: its vector (an upload held back from admission not in it, a
        withheld position in it), the archive designation, its withheld
        positions."""
        with self.cv:
            held = self.logs.get(project, {})
            back = self.unadmitted.get(project, {})
            withheld = (self.withheld or {}).get(project) or {}
            vector = {}
            for w, ss in held.items():
                admitted = [s for s in ss if s not in back.get(w, ())]
                if admitted:
                    vector[w] = max(admitted)
            for w, runs in withheld.items():
                top = max((r if isinstance(r, int) else r[1] for r in runs), default=0)
                if top:
                    vector[w] = max(vector.get(w, 0), top)
            archive = self.archive.get(project, False) if isinstance(self.archive, dict) else bool(self.archive)
            return {"t": "have", "project": project, "have": vector, "archive": archive,
                    **({"withheld": withheld} if withheld else {})}

    def take(self, project, events):
        """Events uploaded: each kept in its upload form, or refused (the
        frames that say so)."""
        out, stopped = [], set()
        with self.cv:
            held = self.logs.setdefault(project, {})
            for e in events:
                form = upload_form(e) if isinstance(e, dict) else None
                writer, seq = (e.get("writer"), e.get("seq")) if isinstance(e, dict) else (None, None)
                if writer in stopped:
                    continue
                message = None
                if form is None:
                    reason = "malformed"
                elif writer in (self.refuse_audience or ()):
                    reason, message = "audience", "the stream's audience is not this session's"
                    stopped.add(writer)
                elif (project, writer, seq) in self.withheld_bodies:
                    # A withheld position sent again: the same body withheld again, another a conflict.
                    reason = "not-reachable" if self.withheld_bodies[(project, writer, seq)] == form else "conflict"
                elif seq in held.get(writer, {}) and held[writer][seq] != form:
                    reason = "conflict"
                elif seq not in held.get(writer, {}) and self.withhold is not None and self.withhold(project, form):
                    self.withheld_bodies[(project, writer, seq)] = form
                    self.withheld.setdefault(project, {}).setdefault(writer, []).append(seq)
                    reason = "not-reachable"
                else:
                    held.setdefault(writer, {})[seq] = form
                    if not self.admit:
                        self.unadmitted.setdefault(project, {}).setdefault(writer, set()).add(seq)
                    continue
                out.append({"t": "refused", "project": project,
                            "refusal": {"reason": reason, "writer": writer, "seq": seq,
                                        **({"message": message} if message else {})}})
        return out

    def refuse_upload(self, project, writer, seq, reason="not-reachable"):
        """The hub's refusal of an upload as the endpoint passes it down, with
        no message (a `not-reachable` never carries one). Sent, and returned.
        (Not `refused`: that is the list of the hellos refused.)"""
        frame = {"t": "refused", "project": project, "refusal": {"reason": reason, "writer": writer, "seq": seq}}
        self.send(frame)
        return frame

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
        `created` and `opCreated`; on a session (`args.session`), its
        context `{lane: 'A', session, launch}` with the launch the session's
        last `member` frame named, as the endpoint reads it from the member
        state (none there: no launch, which sminos refuses `bad-shape`);
        `fields` override any of them. Sent, and returned."""
        now = iso()
        rpc = {"rpc": name, "project": project, "machine": self.identity.get("name"), "member": "mem-1",
               "device": "dev-1", "created": now, "nonce": b64url(os.urandom(16)), "opId": b64url(os.urandom(18)),
               "opCreated": now, "args": args, "fingerprint": b64url(os.urandom(32))}
        sid = args.get("session") if isinstance(args, dict) else None
        if name != "spawn" and isinstance(sid, str):
            launch = (self.members.get(sid) or {}).get("launch")
            rpc["context"] = {"lane": "A", "session": sid, **({"launch": launch} if launch is not None else {})}
        rpc.update(fields)
        self.send({"t": "rpc", "rpc": rpc})
        return rpc

    def query(self, op, op_created=None):
        self.send({"t": "query", "opId": op, **({"opCreated": op_created} if op_created is not None else {})})

    def tombstone(self, op):
        self.send({"t": "tombstone", "opId": op})

    # ---------------------------------------------------- between two machines (hand)

    def accepted(self, project, after=None):
        """What this endpoint accepted of `project` as it would relay it to
        another machine's endpoint: each event held and admitted past
        `after` ({writer: seq}), in its `echo` form, writer by writer in seq
        order; a writer stops at a position held back from admission."""
        after = after or {}
        with self.cv:
            held = self.logs.get(project, {})
            back = self.unadmitted.get(project, {})
            positions = []
            for w in sorted(held):
                for s in sorted(held[w]):
                    if s in back.get(w, ()):
                        break
                    if s > after.get(w, 0):
                        positions.append((w, s))
        return [self.echo(project, w, s) for w, s in positions]

    def opened(self):
        """The live connection's number and the projects its hellos opened:
        {conn, projects: {project: {name, have, follow, at}}}, each the last
        hello of it (`at` its place among the frames received)."""
        with self.cv:
            conn = self.current.number if self.current is not None else None
            projects = {}
            for at, (n, f) in enumerate(self.received):
                if n == conn and f.get("t") == "hello" and isinstance(f.get("project"), str):
                    projects[f["project"]] = {"name": f.get("name"), "have": dict(f.get("have") or {}),
                                              "follow": f.get("follow") is True, "at": at}
            return {"conn": conn, "projects": projects}

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
    elif op == "refuse":
        ep.refuse_upload(arg["project"], arg["writer"], arg["seq"], arg.get("reason", "not-reachable"))
    elif op == "accepted":
        return {"events": ep.accepted(arg["project"], arg.get("after"))}
    elif op == "opened":
        return ep.opened()
    elif op == "unlink-rl10":
        os.unlink(ep.rl10_path())
    elif op == "stop":
        ep.stop()
    else:
        return {"error": "no op %r" % op}
    return {"ok": True}


def ctl_call(directory, op, arg):
    """One ctl request to the stand-in serving `directory`: its answer's text."""
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
    sock.close()
    return data.decode("utf-8").rstrip("\n")


def ctl_main(directory, op, arg):
    print(ctl_call(directory, op, arg))


# ------------------------------------------------------------- two machines


class Served:
    """A stand-in `serve` runs, through its ctl socket: the parts of an
    Endpoint that `hand` reads and sends through."""

    def __init__(self, directory):
        self.dir = directory

    def call(self, op, arg):
        answer = json.loads(ctl_call(self.dir, op, arg))
        if "error" in answer:
            raise RuntimeError("the stand-in at %s: %s" % (self.dir, answer["error"]))
        return answer

    def accepted(self, project, after=None):
        return self.call("accepted", {"project": project, "after": after or {}})["events"]

    def opened(self):
        return self.call("opened", {})

    def events(self, project, wrapped):
        self.call("send", {"frames": [{"t": "events", "project": project, "events": list(wrapped)}]})


def hand(source, dest, cursor_path):
    """One pass of the relay between two machines' endpoints, for the
    two-machine compositions (#153 M3d): what `source` accepted reaches the
    live connection of `dest` as arrivals, one `events` frame per project
    that connection opened, each event in the form source's `echo` gives
    it, past what the project's last hello said it holds and what was
    handed since that hello (kept at cursor_path, so a later pass sends
    only what is new; a new connection or a new hello starts again from
    its `have`, as the hub sends what a hello lacks). `source` and `dest`
    are Endpoints, or Served for a stand-in `serve` runs. How many events
    were handed."""
    opened = dest.opened()
    cursor = read_json(cursor_path) or {}
    if cursor.get("conn") != opened["conn"]:
        cursor = {"conn": opened["conn"], "projects": {}}
    handed = 0
    for project, hello in sorted(opened["projects"].items()):
        held = cursor["projects"].get(project)
        if held is None or held.get("at") != hello["at"]:
            held = {"at": hello["at"], "after": dict(hello["have"])}
        wrapped = source.accepted(project, held["after"])
        if wrapped:
            try:
                dest.events(project, wrapped)
            except (OSError, RuntimeError):
                break   # the connection went: the next pass reads the next one's hellos
            for w in wrapped:
                e = w["event"]
                held["after"][e["writer"]] = max(held["after"].get(e["writer"], 0), e["seq"])
            handed += len(wrapped)
        cursor["projects"][project] = held
    if opened["conn"] is not None:
        write_private(cursor_path, cursor)
    return handed


def hand_served(source_dir, dest_dir):
    """`hand` between two stand-ins `serve` runs, the cursor kept in dest's
    directory under source's path."""
    import hashlib
    tag = hashlib.sha256(os.path.abspath(source_dir).encode()).hexdigest()[:12]
    return hand(Served(source_dir), Served(dest_dir), os.path.join(dest_dir, "handed-%s.json" % tag))


def relay_main(directories):
    """`relay <directory>...`: one hand pass each way between every two, a
    pass whose connection went meanwhile skipped (the next relay hands it);
    the count printed."""
    handed = 0
    for source in directories:
        for dest in directories:
            if source != dest:
                try:
                    handed += hand_served(source, dest)
                except (OSError, RuntimeError, ValueError):
                    pass
    print(handed)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "serve":
        serve_main(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
    elif len(sys.argv) >= 4 and sys.argv[1] == "ctl":
        ctl_main(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]) if len(sys.argv) > 4 else {})
    elif len(sys.argv) == 4 and sys.argv[1] == "hand":
        print(hand_served(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "relay":
        relay_main(sys.argv[2:])
    else:
        sys.exit("usage: endpoint_standin.py serve <directory> [<config JSON>] | ctl <directory> <op> [<JSON>]"
                 " | hand <source directory> <dest directory> | relay <directory> <directory>...")
