"""The bridge's session endpoint and its local client (DC2, contract DX5).

`sminos bridge --session <id>` is the child the bridge mod
(hooks/mods/bridge.tsx) spawns for the life of a session. It serves the
session's endpoint, HTTP over the Unix socket $SMINOS_HOME/bridge/<id>.sock
in an owner-only directory:

    GET  /status          who serves here: session, pid, protocol, the mod's last word
    POST /events          the mod's events, a JSON array in the order they happened
    GET  /events          a subscription: one snapshot line, then every event, numbered n from 1
    POST /command[?wait=ms]  a command for the mod: relayed as one line on stdout

The mod reads the child's stdout line by line: first `{"op": "hello", ...}`
once the socket answers, then one JSON object per command, `id` first. It
answers a command with a `result` event carrying the same id, which the child
hands back to the client that waited for it. The socket answering is the
bridge-presence signal; a socket file nobody answers is stale, and whoever
finds it removes it (remove_stale). A newer child for the session takes the
path over (a module reload spawns one before the old one is gone), and the
older one, finding the path no longer its own, exits without removing it.

`sminos watch <member>` subscribes and prints the stream: the conversation as
it streams, subagents labelled; `--json`, the lines as they come.

What must outlive a module reload, which kills the child — the model chosen
for the session and the delivery keys already submitted — the child keeps in
$SMINOS_HOME/bridge/<id>.json from the mod's events, and hands back in its
hello. The file outlives the process too, so a session resumed under its id
(a seat's `--resume`) goes on with both.

Requests from outside (DC2 M3): the mod raises a permission prompt or a
question as `raised` and settles it as `settled`; the child keeps the pending
set and the recent settlements for the snapshot, takes a client's decision
(POST /requests/<id>/decision), and hands it to the mod's long-poll
(GET /requests/<id>/wait). The session record leaving `waiting` while a
request's dialog is drawn is the terminal's answer: the poll ends, and a
decision after it is refused. An async question's answer goes to the mod as
an `answer` command.

    GET  /requests                     the pending set and the recent settlements
    GET  /requests/<id>                one pending request (404 none, 410 settled)
    GET  /requests/<id>/wait?ms=       the mod's poll (200 a decision, 204 none yet, 410 ended)
    POST /requests/<id>/decision       a client's decision (200, 409 too late, 400, 404)
"""

import collections
import http.client
import json
import os
import queue
import signal
import socket
import socketserver
import sys
import threading
import time
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

import sminos as S

PROTOCOL = 1
SOCKET_PATH_MAX = 103          # sun_path on macOS (104 with the NUL); Linux allows 107
BODY_MAX = 32 * 1024 * 1024
SUBSCRIBER_BACKLOG = 10000     # a subscriber this far behind is cut off and resubscribes
COMMAND_WAIT_MAX = 25000       # ms: under the 30 s an engine fetch waits
AGENTS_KEPT = 200
WATCHDOG_EVERY = 0.5
POLL_HOLD_MAX = 20000          # ms: the mod's poll is held this long at most, under its 30 s fetch bound
SETTLED_KEPT = 100             # recent settlements a late subscriber still sees
PRESENCE_EVERY = 0.25          # s: how often the session record is read while a dialog may be open
WINDOW_MARGIN_MS = 200         # a background window's decision must reach the mod before its deadline
ANSWER_WAIT_MS = 5000          # an async question's answer, relayed to the mod
EXPORTS_QUEUED = 1000          # the mod's exports waiting for the log; past it, the Stop hook's export has them
STALE_TRIES, STALE_PAUSE = 3, 0.1  # a socket refused this many times, this far apart, is stale
NOTICES = ("block-row", "row-seen")   # each row the session keeps is named by one, in write order (the cut)
QUESTION_TOOLS = ("AskUserQuestion",)
# Who answered, as a client may not claim it: the terminal and the bridge settle on their own.
RESERVED_BY = ("terminal", "bridge")


def _ready_wait():
    """How long a subscription waits for the mod's first resync (s)."""
    try:
        return float(os.environ.get("SMINOS_BRIDGE_READY_WAIT") or 5)
    except ValueError:
        return 5.0


def _loop(agent):
    """A loop's key in the cut: `main`, or the subagent's id."""
    return "main" if agent is None else str(agent)


def bridge_dir():
    return os.path.join(S.root(), "bridge")


def endpoint(session):
    return os.path.join(bridge_dir(), session + ".sock")


def kept_path(session):
    return os.path.join(bridge_dir(), session + ".json")


def _no_kept():
    return {"override": None, "delivered": {}}


def load_kept(session):
    """What a child kept for the session: {"override": {model, effort} | None,
    "delivered": {writer: seq}}; nothing kept reads as none."""
    try:
        with open(kept_path(session)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return _no_kept()
    if not isinstance(d, dict):
        return _no_kept()
    o = d.get("override")
    delivered = d.get("delivered")
    return {"override": o if isinstance(o, dict) else None,
            "delivered": {str(w): s for w, s in delivered.items() if type(s) is int}
            if isinstance(delivered, dict) else {}}


# ------------------------------------------------------------------ the client


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("bridge", timeout=timeout)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def request(path, method, url, body=None, timeout=10):
    """One request to an endpoint: (status, parsed JSON or None). Raises
    OSError when nothing answers."""
    c = _UnixConnection(path, timeout)
    try:
        data = None if body is None else json.dumps(body).encode()
        c.request(method, url, body=data, headers={"content-type": "application/json"})
        r = c.getresponse()
        text = r.read().decode()
        try:
            return r.status, json.loads(text) if text else None
        except ValueError:
            return r.status, None
    finally:
        c.close()


def probe(path):
    """The endpoint's /status when a bridge answers there, else None."""
    try:
        status, body = request(path, "GET", "/status", timeout=3)
    except (OSError, http.client.HTTPException):
        return None
    return body if status == 200 and isinstance(body, dict) else None


def remove_stale(path):
    """Removes a socket file nobody listens on, and only that file: the inode
    is read before the connect and checked again before the unlink, so a
    child that moved its socket into place meanwhile keeps it."""
    try:
        before = os.lstat(path).st_ino
    except OSError:
        return
    # A listener whose backlog is full refuses a connect too: only a socket
    # refused every time over a few tenths of a second is taken as dead.
    for attempt in range(STALE_TRIES):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            s.connect(path)
            return  # someone listens: not stale
        except OSError:
            pass
        finally:
            s.close()
        if attempt + 1 < STALE_TRIES:
            time.sleep(STALE_PAUSE)
    try:
        if os.lstat(path).st_ino == before:
            os.unlink(path)
    except OSError:
        pass


class NotReady(OSError):
    """The endpoint answers but has not had the session's state from the mod yet (503)."""


def subscribe(path):
    """The endpoint's stream: yields each line, parsed, until it ends. Raises
    OSError when nothing answers, NotReady when the child has not had the
    mod's first resync within its wait."""
    c = _UnixConnection(path, timeout=None)
    try:
        c.request("GET", "/events")
        r = c.getresponse()
        if r.status == 503:
            raise NotReady("the bridge has not had the session's state yet")
        if r.status != 200:
            raise OSError("the bridge refused the subscription (%d)" % r.status)
        while True:
            line = r.readline()
            if not line:
                return
            line = line.strip()
            if line:
                yield json.loads(line)
    finally:
        c.close()


# ------------------------------------------------------------------ the child


def _key(e):
    return "%s|%s|%s" % (e.get("turnId"), e.get("agentId"), e.get("step"))


def _now_ms():
    return int(time.time() * 1000)


def presence_path(session_pid):
    """The session record the engine writes for the session process: under
    the session's config dir, which the child inherits."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(S.home_dir(), ".claude")
    return os.path.join(cfg, "sessions", "%d.json" % session_pid)


def presence_status(path, session):
    """The session record's `status` (idle, busy, shell, waiting), or None
    when no record of this session can be read there."""
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("sessionId") != session:
        return None
    return d.get("status") if isinstance(d.get("status"), str) else None


# A block's kind as its chunks name it: an `input` chunk belongs to a tool call.
_BLOCK_KIND = {"text": "text", "thinking": "thinking", "tool": "tool", "input": "tool"}


def _message(e):
    """A streaming message as the snapshot carries it, from a step's start or
    a resync's entry: its blocks by index, the ones a block-row settled (a
    resync names them, so their late chunks stay ignored), and `upTo`, the
    last chunk applied to it."""
    settled = {i for i in e.get("settled") or [] if type(i) is int}
    blocks = {}
    for b in e.get("blocks") or []:
        if isinstance(b, dict) and isinstance(b.get("index"), int) and b["index"] not in settled:
            blocks[b["index"]] = dict(b)
    m = {"turnId": e.get("turnId"), "agentId": e.get("agentId"), "step": e.get("step"), "model": e.get("model"),
         "upTo": e.get("upTo") if isinstance(e.get("upTo"), int) else -1, "blocks": blocks, "settled": settled}
    return m


def _shown(m):
    """A streaming message as a snapshot shows it: its blocks without a
    block-row, in index order."""
    return {"turnId": m["turnId"], "agentId": m["agentId"], "step": m["step"], "model": m.get("model"),
            "upTo": m["upTo"], "blocks": [dict(m["blocks"][i]) for i in sorted(m["blocks"])]}


def _fold(m, index, e):
    """Applies a chunk that follows its message's upTo to its block."""
    chunk = e.get("chunk") or {}
    m["upTo"] = index
    block_index, kind = chunk.get("index"), _BLOCK_KIND.get(chunk.get("kind"))
    if not isinstance(block_index, int) or kind is None or block_index in m["settled"]:
        return
    b = m["blocks"].setdefault(block_index, {"index": block_index, "kind": kind, "text": "", "upTo": -1})
    if chunk.get("kind") in ("text", "thinking"):
        b["text"] += str(chunk.get("text") or "")
    elif chunk.get("kind") == "tool":
        b["id"], b["name"] = chunk.get("id"), chunk.get("name")
    else:
        b["text"] += str(chunk.get("json") or "")
    b["upTo"] = index


def is_question(raised):
    return raised.get("tool") in QUESTION_TOOLS or bool(raised.get("async"))


def _check_decision(raised, body):
    """Why a client's decision cannot be taken for this request, or None.
    A permission is allowed or denied as asked; a question's allow carries its
    answers, keyed by the questions it asks; an async question is answered,
    never denied."""
    if not isinstance(body, dict):
        return "a decision is an object"
    if body.get("behavior") not in ("allow", "deny"):
        return "behavior is allow or deny"
    by = body.get("by")
    if not isinstance(by, str) or not by.strip():
        return "by names who decided (cli, or the member's id)"
    if by in RESERVED_BY:
        return "%r is the bridge's own; a client answers as itself" % by
    if "message" in body and not isinstance(body["message"], str):
        return "message is text"
    updated = body.get("updatedInput")
    if not is_question(raised):
        if updated is not None:
            return "a permission is allowed or denied as asked: updatedInput carries a question's answers only"
        return None
    if body["behavior"] == "deny":
        return "an async question waits for an answer; it cannot be denied" if raised.get("async") else None
    answers = updated.get("answers") if isinstance(updated, dict) else None
    if not isinstance(answers, dict) or not answers:
        return "a question is allowed with its answers: updatedInput.answers, keyed by the question"
    asked = [q.get("question") for q in ((raised.get("input") or {}).get("questions") or []) if isinstance(q, dict)]
    for q, a in answers.items():
        if q not in asked:
            return "the request asks no question %r" % q
        if not isinstance(a, str):
            return "the answer to %r is not text" % q
    return None


class Bridge:
    """The session's live state as the mod's events build it, and the
    subscribers and command waiters it serves. One lock: an event is applied
    and handed to every subscriber in one step, and a snapshot is taken and a
    subscriber added in one step, so a subscriber misses nothing and sees
    nothing twice (subscribe before snapshot, DX4)."""

    def __init__(self, session, sock):
        self.session = session
        self.socket = sock
        self.started = time.time()
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)   # a request was decided, settled, or closed
        self.out_lock = threading.Lock()
        self.subscribers = set()
        self.pending = {}        # request id → {"raised", "decided", "handed", "closed", "saw_waiting"}
        self.settled = collections.OrderedDict()   # request id → its settlement, the last SETTLED_KEPT
        self.presence = None     # the session record's path, once serve() knows the session's process
        self.streaming = {}      # turnId|agentId|step → the message as streamed so far, by block
        self.broken = set()      # messages a chunk was missing from: left out until a resync
        self.turns = {}          # turnId → the open turn
        self.agents = {}         # agentId → what its spawn said, and whether it runs
        self.session_info = None
        self.usage = None
        self.mod_events = 0
        self.mod_last = None
        self.waiters = {}        # command id → [threading.Event, result event]
        self.closing = threading.Event()
        self.kept = load_kept(session)
        self.saved = self.kept    # what the file holds: kept is written until it is
        self.exports = queue.Queue(EXPORTS_QUEUED)   # (cwd, records) for the log, appended in order (run_exports)
        # The mod's first resync applied: until then the state is not the
        # session's, and a subscription waits for it (DX5's readiness).
        self.ready = False
        # Per loop, the uuid of the last row whose notice was applied (null:
        # none since the module loaded), under the lock that guards streaming.
        self.cut = {"main": None}
        self.failing = False     # the last write failed (said once, and again when one succeeds)

    # -- the mod's events

    def ingest(self, events):
        with self.lock:
            self.mod_events += len(events)
            self.mod_last = time.time()
            for e in events:
                if e.get("type") == "export":
                    self._export(e)
                    continue
                self._apply(e)
                if e.get("type") == "resync":
                    # The first makes the child ready; any later one replaced
                    # what every subscriber's snapshot was built from, so each
                    # subscription ends and takes a fresh snapshot: the stream
                    # ending is the one discontinuity a subscriber sees.
                    if self.ready:
                        self._end_subscribers()
                    self.ready = True
                    self.changed.notify_all()
                    continue
                self._fan_out(e)
            # Whatever the batch did, what is kept and not yet on disk is
            # written now: an event that moves nothing still retries a failed
            # write.
            note = self._save()
            if note is not None:
                self._fan_out(note)

    def _end_subscribers(self):
        for sub in list(self.subscribers):
            self.subscribers.discard(sub)
            sub.cut = True
            try:
                sub.put_nowait(None)   # its writer stops here, after what came before
            except queue.Full:
                pass                   # it drains the backlog, then ends on the cut

    def wait_ready(self, seconds):
        with self.lock:
            return self.changed.wait_for(lambda: self.ready, seconds)

    def _fan_out(self, e):
        for sub in list(self.subscribers):
            try:
                sub.put_nowait(e)
            except queue.Full:   # its writer drains the backlog, then ends it
                self.subscribers.discard(sub)
                sub.cut = True

    def _apply(self, e):
        kind, phase = e.get("type"), e.get("phase")
        if kind == "chunk":
            # A message's blocks are only ever whole up to its upTo: a chunk
            # that does not follow the last one (a post lost, a start missed)
            # takes the message out of the snapshot until the mod's resync.
            k = _key(e)
            m = self.streaming.get(k)
            index = e.get("chunkIndex")
            if k in self.broken:
                return
            if m is None and index == 0:
                m = self.streaming[k] = _message(e)
            if m is None or index != m["upTo"] + 1:
                self.streaming.pop(k, None)
                self.broken.add(k)
                return
            _fold(m, index, e)
        elif kind in NOTICES:
            # A row is about to be written: its loop's cut moves to it. A
            # response row's notice (block-row) also settles its block, which
            # leaves the snapshot under this same lock (DX4): no block is
            # still streaming whose row is at or before the cut.
            if isinstance(e.get("uuid"), str) and e["uuid"]:
                self.cut[_loop(e.get("agentId"))] = e["uuid"]
            m = self.streaming.get(_key(e)) if kind == "block-row" else None
            if m is not None and isinstance(e.get("index"), int):
                m["blocks"].pop(e["index"], None)
                m["settled"].add(e["index"])
        elif kind == "raised":
            rid = e.get("request")
            if isinstance(rid, str) and rid not in self.settled:
                old = self.pending.get(rid) or {}
                self.pending[rid] = {**self._fresh_request(), **old,
                                     "raised": {k: v for k, v in e.items() if k not in ("type", "n")}}
                self.changed.notify_all()
        elif kind == "settled":
            rid = e.get("request")
            if isinstance(rid, str):
                self.pending.pop(rid, None)
                self._remember(rid, {k: v for k, v in e.items() if k not in ("type", "n")})
                self.changed.notify_all()
        elif kind == "resync":
            # The mod's own copy of the live state, whole: it replaces this one,
            # and what is kept for the session with it.
            self.turns = {t.get("turnId"): dict(t) for t in e.get("turns") or []}
            streaming = {}
            for entry in e.get("streaming") or []:
                m = _message(entry)
                # A block this child saw settled stays settled, whatever the copy says.
                old = self.streaming.get(_key(entry))
                if old is not None:
                    m["settled"] |= old["settled"]
                    for i in old["settled"]:
                        m["blocks"].pop(i, None)
                streaming[_key(entry)] = m
            self.streaming = streaming
            self.agents = {a.get("agentId"): dict(a) for a in e.get("agents") or []}
            self.broken = set()
            cut = e.get("cut") if isinstance(e.get("cut"), dict) else {}
            self.cut = {"main": None, **{str(k): v for k, v in cut.items() if v is None or isinstance(v, str)}}
            if isinstance(e.get("pending"), list):
                pending = {}
                for r in e["pending"]:
                    rid = r.get("request") if isinstance(r, dict) else None
                    if isinstance(rid, str):
                        pending[rid] = {**self._fresh_request(), **(self.pending.get(rid) or {}),
                                        "raised": {k: v for k, v in r.items() if k not in ("type", "n")}}
                self.pending = pending
            for s in e.get("settled") or []:
                if isinstance(s, dict) and isinstance(s.get("request"), str) and s["request"] not in self.settled:
                    self._remember(s["request"], {k: v for k, v in s.items() if k not in ("type", "n")})
            self.changed.notify_all()
            kept = dict(self.kept)
            if "override" in e:
                kept["override"] = e["override"] if isinstance(e["override"], dict) else None
            if isinstance(e.get("delivered"), dict):
                kept["delivered"] = {str(w): s for w, s in e["delivered"].items() if type(s) is int}
            self._keep(kept)
        elif kind == "model":
            o = {"model": e.get("model"), "effort": e.get("effort")}
            self._keep({**self.kept, "override": o if o["model"] is not None or o["effort"] is not None else None})
        elif kind == "delivered" and e.get("outcome") == "submitted":
            key = e.get("key") or {}
            writer, seq = key.get("writer"), key.get("seq")
            if isinstance(writer, str) and type(seq) is int and seq > self.kept["delivered"].get(writer, 0):
                self._keep({**self.kept, "delivered": {**self.kept["delivered"], writer: seq}})
        elif kind == "step" and phase == "start":
            self.broken.discard(_key(e))
            self.streaming[_key(e)] = _message({k: v for k, v in e.items() if k in ("turnId", "agentId", "step", "model")})
        elif kind == "step" and phase == "end":
            self.streaming.pop(_key(e), None)
            self.broken.discard(_key(e))
        elif kind == "turn" and phase == "start":
            self.turns[e.get("turnId")] = {"turnId": e.get("turnId"), "agentId": e.get("agentId"), "t": e.get("t")}
        elif kind == "turn" and phase == "complete":
            self.turns.pop(e.get("turnId"), None)
            for k in [k for k, m in self.streaming.items() if m["turnId"] == e.get("turnId")]:
                del self.streaming[k]
            self.broken = {k for k in self.broken if not k.startswith("%s|" % e.get("turnId"))}
        elif kind == "agent":
            a = self.agents.setdefault(e.get("agentId"), {"agentId": e.get("agentId")})
            a.update({k: v for k, v in e.items() if k not in ("type", "phase", "n")})
            a["running"] = phase != "stop"
            if len(self.agents) > AGENTS_KEPT:
                done = [k for k, v in self.agents.items() if not v["running"]]
                for k in done[:len(self.agents) - AGENTS_KEPT]:
                    del self.agents[k]
        elif kind == "session" and phase == "start":
            self.session_info = {k: v for k, v in e.items() if k not in ("type", "phase")}
        elif kind == "session":
            self.session_info = {**(self.session_info or {}), "ended": e.get("reason")}
        elif kind == "usage":
            self.usage = dict(e)
        elif kind == "result":
            w = self.waiters.get(e.get("id"))
            if w is not None:
                w[1] = e
                w[0].set()

    def _export(self, e):
        """Rows the mod hands over for the project's log (DC2 G4): queued for
        run_exports, in the order they came; never handed to subscribers, who
        have the same text from the stream, and the log has the result."""
        records = e.get("records")
        cwd = (self.session_info or {}).get("cwd")
        if not (isinstance(records, list) and all(isinstance(r, dict) for r in records) and isinstance(cwd, str) and cwd):
            return
        try:
            self.exports.put_nowait((cwd, records))
        except queue.Full:
            sys.stderr.write("sminos bridge: an export was dropped (%d waiting); the Stop hook's export has it\n"
                             % EXPORTS_QUEUED)

    def run_exports(self):
        """Appends what the mod exports through the record path's own writer
        (sminos.export_live), one export at a time and in order, apart from the
        lock that serves the stream: the log's locks may be held a while (the
        daemon's sync), and a slow append must not hold up the session's events.
        A failure is the Stop hook's to make good: its export appends whatever
        of the same rows the log does not hold."""
        while not self.closing.is_set():
            try:
                cwd, records = self.exports.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                project = S.resolve_project(cwd)
                if project is not None:
                    S.export_live(project, self.session, records)
            except (Exception, SystemExit) as err:  # noqa: BLE001 — the next export must still run
                sys.stderr.write("sminos bridge: export to the log failed: %s: %s\n" % (type(err).__name__, err))

    def _keep(self, kept):
        """What is kept for the session: the mod's copy, written at the end of
        the batch that changed it (_save)."""
        self.kept = kept

    @staticmethod
    def _fresh_request():
        # decided: a client's decision, not yet handed to the mod's poll (or
        # handed: then the engine has it); closed: the terminal answered it.
        return {"raised": {}, "decided": None, "handed": False, "closed": False, "saw_waiting": False}

    def _remember(self, rid, settlement):
        self.settled.pop(rid, None)
        self.settled[rid] = settlement
        while len(self.settled) > SETTLED_KEPT:
            self.settled.popitem(last=False)

    def _save(self):
        """Writes what is kept, whole, while it differs from what the file
        holds (under the lock, at the end of each batch of the mod's events).
        `saved` moves only once a write succeeded, so a failed write is tried
        again with the next batch, whatever it carries. The child's own `kept`
        event says when writing starts to fail and when it works again; None
        when there is nothing to say."""
        if self.kept == self.saved:
            return None
        path = kept_path(self.session)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self.kept, f)
            os.replace(tmp, path)
        except OSError as err:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            sys.stderr.write("sminos bridge: %s not kept: %s\n" % (path, err))
            if self.failing:
                return None
            self.failing = True
            return {"type": "kept", "ok": False, "error": "%s not written: %s" % (path, err),
                    "t": int(time.time() * 1000)}
        self.saved = self.kept
        if not self.failing:
            return None
        self.failing = False
        return {"type": "kept", "ok": True, "t": int(time.time() * 1000)}

    def snapshot(self):
        return {"type": "snapshot", "session": self.session, "protocol": PROTOCOL, "pid": os.getpid(),
                "sessionInfo": self.session_info, "turns": list(self.turns.values()),
                "streaming": [_shown(m) for m in self.streaming.values()],
                "agents": list(self.agents.values()), "usage": self.usage,
                "override": self.kept["override"],
                # Per loop, the last row whose notice is applied: every row up
                # to it is the transcript's, none of them still streaming.
                "cut": dict(self.cut),
                # The requests pending in the session, and the ones settled
                # recently, so a subscriber that arrives after a request
                # settled sees it settled rather than still raised.
                "pending": [dict(p["raised"]) for p in self.pending.values()],
                "settled": list(self.settled.values())}

    # -- requests from outside

    def _dialog_drawn(self, raised, now_ms):
        """Whether the request's dialog is drawn in the terminal: always, but
        for a background subagent's window, before whose deadline the engine
        awaits the hooks and draws nothing."""
        deadline = raised.get("deadline")
        return not isinstance(deadline, (int, float)) or now_ms >= deadline

    def requests(self):
        with self.lock:
            return {"pending": [dict(p["raised"]) for p in self.pending.values()],
                    "settled": list(self.settled.values())}

    def request_info(self, rid):
        with self.lock:
            p = self.pending.get(rid)
            if p is not None:
                return 200, {**p["raised"], "session": self.session}
            if rid in self.settled:
                return 410, {"error": "settled", "settled": self.settled[rid]}
        return 404, {"error": "no request %s is pending in this session" % rid}

    def watch_presence(self):
        """While a request's dialog may be open, reads the session record: a
        record that was `waiting` while the dialog was drawn and is no longer
        says the terminal answered it, which ends the mod's poll."""
        while not self.closing.wait(PRESENCE_EVERY):
            with self.lock:
                watched = any(not p["closed"] and not p["raised"].get("async") for p in self.pending.values())
            if not watched or self.presence is None:
                continue
            status = presence_status(self.presence, self.session)
            if status is None:
                continue
            now = _now_ms()
            with self.lock:
                for p in self.pending.values():
                    if p["closed"] or p["raised"].get("async") or not self._dialog_drawn(p["raised"], now):
                        continue
                    if status == "waiting":
                        p["saw_waiting"] = True
                    elif p["saw_waiting"]:
                        p["closed"] = True
                        self.changed.notify_all()

    def wait_decision(self, rid, ms):
        """The mod's poll: a client's decision once there is one (handed out
        once), 410 once the request is settled or the terminal answered it,
        204 when the hold runs out. A request not raised yet (its `raised`
        still on its way) is waited for."""
        deadline = time.monotonic() + max(0, min(ms, POLL_HOLD_MAX)) / 1000.0
        with self.lock:
            while True:
                p = self.pending.get(rid)
                if p is None and rid in self.settled:
                    return 410, {"reason": "settled", "settled": self.settled[rid]}
                if p is not None:
                    if p["decided"] is not None and not p["handed"]:
                        p["handed"] = True
                        return 200, dict(p["decided"])
                    if p["closed"] and not p["handed"]:
                        return 410, {"reason": "terminal"}
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.closing.is_set():
                    return 204, None
                self.changed.wait(min(remaining, 1.0))

    def decide(self, rid, body):
        """A client's decision: (status, answer). Taken once, while the
        request is pending, its dialog not answered in the terminal, and a
        background window not past its deadline; an async question's answer
        goes to the mod at once."""
        # The record is read before the lock: a dialog the terminal closed
        # since the last look is the terminal's.
        status = presence_status(self.presence, self.session) if self.presence else None
        with self.lock:
            p = self.pending.get(rid)
            if p is None:
                if rid in self.settled:
                    return 409, {"error": "already settled", "settled": self.settled[rid]}
                return 404, {"error": "no request %s is pending in this session" % rid}
            raised = p["raised"]
            why = _check_decision(raised, body)
            if why:
                return 400, {"error": why}
            if p["decided"] is not None:
                return 409, {"error": "already answered by %s; its settlement follows" % p["decided"]["by"]}
            deadline = raised.get("deadline")
            if isinstance(deadline, (int, float)):
                if _now_ms() >= deadline - WINDOW_MARGIN_MS:
                    return 409, {"error": "the window for answering it from outside closed; the terminal answers it",
                                 "terminalOnly": True}
            elif not raised.get("async") and status is not None:
                # Its dialog is drawn: a record seen waiting since the request
                # was raised, and waiting no more, is the terminal's answer.
                if status == "waiting":
                    p["saw_waiting"] = True
                elif p["saw_waiting"]:
                    p["closed"] = True
                    self.changed.notify_all()
            if p["closed"]:
                return 409, {"error": "the terminal answered it; its settlement follows"}
            decision = {"behavior": body["behavior"]}
            for k in ("message", "updatedInput"):
                if k in body:
                    decision[k] = body[k]
            p["decided"] = {"decision": decision, "by": body["by"]}
            if not raised.get("async"):
                self.changed.notify_all()
                return 200, {"accepted": True, "request": rid}
        # An async question has no hook polling for it: its answer goes to the
        # mod as a command, which hands it to the ask mod.
        try:
            code, out = self.command({"op": "answer", "request": rid, "answers": body["updatedInput"]["answers"],
                                      "by": body["by"]}, ANSWER_WAIT_MS)
        except OSError:
            code, out = 503, {"error": "the session is gone"}
        if code == 200 and out.get("ok"):
            return 200, {"accepted": True, "request": rid}
        with self.lock:
            p = self.pending.get(rid)
            if p is not None:
                p["decided"] = None
        if code == 200:
            return 409, {"error": out.get("error") or "the session refused the answer"}
        return code, out

    def subscribe(self):
        q = queue.Queue(SUBSCRIBER_BACKLOG)
        q.cut = False
        with self.lock:
            snap = self.snapshot()
            self.subscribers.add(q)
        return snap, q

    def unsubscribe(self, q):
        with self.lock:
            self.subscribers.discard(q)

    def status(self):
        with self.lock:
            return {"session": self.session, "pid": os.getpid(), "protocol": PROTOCOL, "socket": self.socket,
                    "started": self.started, "ready": self.ready, "subscribers": len(self.subscribers),
                    "mod": {"events": self.mod_events, "last": self.mod_last}}

    # -- the mod's input: one line on stdout

    def emit(self, obj):
        data = (json.dumps(obj) + "\n").encode()
        with self.out_lock:
            try:
                while data:
                    data = data[os.write(1, data):]
            except OSError:   # the mod is gone: so is the session
                self.closing.set()
                raise

    def command(self, body, wait_ms):
        cid = uuidlib.uuid4().hex
        line = {"id": cid, **{k: v for k, v in body.items() if k != "id"}}
        w = [threading.Event(), None]
        if wait_ms > 0:
            with self.lock:
                self.waiters[cid] = w
        try:
            self.emit(line)
            self.ingest([{"type": "command", "id": cid, "op": body["op"], "t": int(time.time() * 1000)}])
            if wait_ms <= 0:
                return 202, {"id": cid, "status": "sent"}
            if not w[0].wait(wait_ms / 1000.0):
                return 504, {"id": cid, "error": "the session did not answer within %d ms" % wait_ms}
            r = w[1]
            out = {"id": cid, "ok": bool(r.get("ok"))}
            for k in ("result", "error"):
                if k in r:
                    out[k] = r[k]
            return 200, out
        finally:
            with self.lock:
                self.waiters.pop(cid, None)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "sminos-bridge/%d" % PROTOCOL

    def log_message(self, *_args):
        pass

    def address_string(self):
        return "local"

    def _send(self, status, body=None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > BODY_MAX:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"null")

    def do_GET(self):
        bridge = self.server.bridge
        url = urlparse(self.path)
        route = url.path
        if route == "/status":
            return self._send(200, bridge.status())
        if route == "/events":
            return self._stream(bridge)
        if route == "/requests":
            return self._send(200, bridge.requests())
        parts = route.split("/")
        if len(parts) == 3 and parts[1] == "requests" and parts[2]:
            return self._send(*bridge.request_info(unquote(parts[2])))
        if len(parts) == 4 and parts[1] == "requests" and parts[2] and parts[3] == "wait":
            q = parse_qs(url.query)
            try:
                ms = int((q.get("ms") or [str(POLL_HOLD_MAX)])[0])
            except ValueError:
                return self._send(400, {"error": "ms is milliseconds"})
            return self._send(*bridge.wait_decision(unquote(parts[2]), ms))
        return self._send(404, {"error": "no route %s" % route})

    def do_POST(self):
        bridge = self.server.bridge
        url = urlparse(self.path)
        try:
            body = self._body()
        except ValueError as e:
            return self._send(400, {"error": "the body is not JSON: %s" % e})
        if url.path == "/events":
            events = body if isinstance(body, list) else [body]
            if not all(isinstance(e, dict) and isinstance(e.get("type"), str) for e in events):
                return self._send(400, {"error": "each event is an object with a type"})
            bridge.ingest(events)
            return self._send(204)
        if url.path == "/command":
            if not isinstance(body, dict) or not isinstance(body.get("op"), str) or not body["op"] \
                    or body["op"] == "hello":
                return self._send(400, {"error": "a command is an object with an op (not hello)"})
            try:
                wait = int((parse_qs(url.query).get("wait") or ["0"])[0])
            except ValueError:
                return self._send(400, {"error": "wait is milliseconds"})
            try:
                status, out = bridge.command(body, max(0, min(wait, COMMAND_WAIT_MAX)))
            except OSError:
                return self._send(503, {"error": "the session is gone"})
            return self._send(status, out)
        parts = url.path.split("/")
        if len(parts) == 4 and parts[1] == "requests" and parts[2] and parts[3] == "decision":
            return self._send(*bridge.decide(unquote(parts[2]), body))
        return self._send(404, {"error": "no route %s" % url.path})

    def _stream(self, bridge):
        """Close-delimited NDJSON: the snapshot line, then each event with its
        n. Held until the mod's first resync is applied (503 past the wait).
        A subscriber that falls SUBSCRIBER_BACKLOG events behind is cut off,
        and every subscription ends when a later resync replaces the state;
        it subscribes again for a fresh snapshot (DX4's rule on a gap)."""
        if not bridge.wait_ready(_ready_wait()):
            return self._send(503, {"error": "the session's state has not reached its bridge yet"})
        snap, q = bridge.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write((json.dumps(snap) + "\n").encode())
            self.wfile.flush()
            n = 0
            while not bridge.closing.is_set():
                try:
                    e = q.get(timeout=1)
                except queue.Empty:
                    if q.cut:
                        return
                    continue
                if e is None:
                    return
                n += 1
                self.wfile.write((json.dumps({"n": n, **e}) + "\n").encode())
                self.wfile.flush()
        except OSError:
            pass
        finally:
            bridge.unsubscribe(q)
            self.close_connection = True


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False
    # Every subscriber reconnects at once when a resync ends the streams; a
    # full backlog refuses a connect as a dead socket would (remove_stale).
    request_queue_size = 128

    def handle_error(self, request, client_address):
        # A client that hung up mid-answer (a watcher closed, a session that
        # ended mid-post) is no error of the bridge's.
        if isinstance(sys.exc_info()[1], OSError):
            return
        super().handle_error(request, client_address)


def serve(session):
    """The child's life: bind beside the endpoint, listen, move the socket
    into place (so the path never names a socket nobody listens on yet), say
    hello, serve until the parent (the session) is gone, the path is another
    child's, or a signal; then remove the socket if it is still this child's."""
    path = endpoint(session)
    if len(path.encode()) > SOCKET_PATH_MAX:
        S.die("the endpoint's path is too long for a Unix socket (%d bytes, at most %d): %s — "
              "a shorter SMINOS_HOME fixes it" % (len(path.encode()), SOCKET_PATH_MAX, path), 1)
    d = bridge_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    tmp = os.path.join(d, ".%s.%d.sock" % (session[:8], os.getpid()))
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    server = _Server(tmp, _Handler, bind_and_activate=False)
    server.server_bind()
    os.chmod(tmp, 0o600)
    server.server_activate()
    # This child's identity is its own socket's inode, read before the move:
    # read after it, a newer child that moved its socket in meanwhile would
    # pass for this one, which would then take its path at exit.
    mine = os.lstat(tmp).st_ino
    os.replace(tmp, path)
    bridge = server.bridge = Bridge(session, path)
    parent = os.getppid()
    bridge.presence = presence_path(parent)

    def watchdog():
        while not bridge.closing.wait(WATCHDOG_EVERY):
            try:
                ours = os.lstat(path).st_ino == mine
            except OSError:
                ours = False
            if os.getppid() != parent or not ours:
                bridge.closing.set()
        server.shutdown()

    def on_signal(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGHUP, on_signal)
    try:
        bridge.emit({"op": "hello", "session": session, "pid": os.getpid(), "socket": path, "protocol": PROTOCOL,
                     "kept": bridge.kept})
        threading.Thread(target=watchdog, daemon=True).start()
        threading.Thread(target=bridge.watch_presence, daemon=True).start()
        threading.Thread(target=bridge.run_exports, daemon=True).start()
        server.serve_forever(poll_interval=0.25)
    except (OSError, KeyboardInterrupt):
        pass
    finally:
        bridge.closing.set()
        try:
            if os.lstat(path).st_ino == mine:
                os.unlink(path)
        except OSError:
            pass
        server.server_close()


def cmd_bridge(a):
    if not S.UUID_RE.match(a.session or ""):
        S.die("bridge: %r is not a session id" % (a.session or ""))
    serve(a.session)


# ------------------------------------------------------------------ watch


def watch_session(q):
    """The session a member name names here, or exit 4 saying why not. A full
    session id is taken as given."""
    if S.UUID_RE.match(q):
        return q
    target = S.find_target(q)
    if target[0] == "none":
        S.die("no member matching '%s'" % q, S.EXIT_UNKNOWN)
    if target[0] == "seat":
        s = target[1]
        session = target[2] or s.get("current") or ""
        if not session:
            S.die("%s/%s holds no session" % (s["group"], s["alias"]), S.EXIT_UNKNOWN)
        return session
    m = target[2]
    if not m.local:
        S.die("%s runs on %s; its bridge is that machine's" % (q, m.machine or "another machine"), S.EXIT_UNKNOWN)
    return m.session


def _first_line(text, width=160):
    line = str(text or "").strip().split("\n", 1)[0]
    return line if len(line) <= width else line[:width - 1] + "…"


def _tool_summary(tool, value):
    if isinstance(value, dict):
        for k in ("command", "file_path", "path", "pattern", "url", "query", "description", "prompt"):
            if isinstance(value.get(k), str) and value[k]:
                return _first_line(value[k], 120)
        return _first_line(json.dumps(value, ensure_ascii=False), 120)
    return ""


class Renderer:
    """The stream as a person reads it: text as it streams under its loop's
    label, one line for each thing that happened between."""

    def __init__(self, out):
        self.out = out
        self.at_start = True
        self.source = None
        self.thinking = set()
        self.labels = {}

    def label(self, agent):
        if agent is None:
            return "main"
        return self.labels.get(agent) or "agent %s" % str(agent)[:12]

    def write(self, text):
        self.out.write(text)
        self.out.flush()
        if text:
            self.at_start = text.endswith("\n")

    def line(self, text):
        if not self.at_start:
            self.write("\n")
        self.source = None
        self.write(text + "\n")

    def stream(self, key, agent, text):
        if self.source != key:
            if not self.at_start:
                self.write("\n")
            self.write("[%s] " % self.label(agent))
            self.source = key
        self.write(text)

    def feed(self, e):
        kind, phase, agent = e.get("type"), e.get("phase"), e.get("agentId")
        if kind == "snapshot":
            for a in e.get("agents") or []:
                self._name(a)
            self.line("· watching session %s (bridge pid %s)" % (e.get("session"), e.get("pid")))
            for r in e.get("pending") or []:
                self._raised(r)
            for m in e.get("streaming") or []:
                text = "".join(b.get("text") or "" for b in m.get("blocks") or [] if b.get("kind") == "text")
                if text:
                    self.stream(_key(m), m.get("agentId"), text)
        elif kind == "chunk":
            chunk = e.get("chunk") or {}
            if chunk.get("kind") == "text" and chunk.get("text"):
                self.stream(_key(e), agent, chunk["text"])
            elif chunk.get("kind") == "thinking" and (_key(e), chunk.get("index")) not in self.thinking:
                self.thinking.add((_key(e), chunk.get("index")))
                self.line("· [%s] thinking…" % self.label(agent))
        elif kind == "turn" and phase == "start":
            if agent is None:
                self.line("» %s" % (_first_line(e.get("text")) or "(a turn with no prompt)"))
            else:
                self.line("· [%s] turn started" % self.label(agent))
        elif kind == "turn" and phase == "complete":
            self.line("· [%s] turn ended: %s" % (self.label(agent), e.get("reason")))
        elif kind == "tool" and phase == "call":
            self.line("· [%s] %s %s" % (self.label(agent), e.get("tool"), _tool_summary(e.get("tool"), e.get("input"))))
        elif kind == "tool" and phase == "result" and (e.get("isError") or e.get("denied")):
            self.line("  ⎿ [%s] %s failed: %s" % (self.label(agent), e.get("tool"),
                                                  _first_line(e.get("denied") or e.get("text"))))
        elif kind == "agent" and phase == "spawn":
            self._name(e)
            self.line("· agent %s started: %s" % (self.label(agent), _first_line(e.get("description"), 100)))
        elif kind == "agent" and phase == "stop":
            self.line("· agent %s stopped" % self.label(agent))
        elif kind == "session":
            if phase == "start":
                self.line("· session started · %s" % (e.get("model") or "?"))
            else:
                self.line("· session ended (%s)" % e.get("reason"))
        elif kind == "usage":
            c = e.get("context") or {}
            if c.get("tokens") is not None and c.get("window"):
                self.line("· context %s of %s tokens" % (format(c["tokens"], ","), format(c["window"], ",")))
        elif kind == "result":
            self.line("· %s → %s" % (e.get("op"), "ok" if e.get("ok") else "refused: %s" % e.get("error")))
        elif kind == "model":
            self.line("· model %s, effort %s (this session)" % (e.get("model") or "the session's own",
                                                                e.get("effort") or "the session's own"))
        elif kind == "compact":
            self.line("· compaction %s" % ("started" if phase == "start" else _compact_outcome(e)))
        elif kind == "delivered" and e.get("outcome") != "duplicate":
            k = e.get("key") or {}
            self.line("· delivered %s:%s %s" % (k.get("writer"), k.get("seq"), e.get("outcome")))
        elif kind == "gap":
            self.line("· %s events were lost on the way from the session" % e.get("dropped"))
        elif kind == "kept":
            self.line("· the bridge keeps its state on disk again" if e.get("ok") else
                      "· the bridge could not keep its state on disk: %s" % e.get("error"))
        elif kind == "raised":
            self._raised(e)
        elif kind == "settled":
            self.line("· request %s settled: %s (%s)" % (e.get("request"), e.get("outcome"), e.get("by")))

    def _raised(self, e):
        """A pending request: what it asks, and its id to answer it by."""
        agent = e.get("agentId")
        value = e.get("input") if isinstance(e.get("input"), dict) else {}
        if is_question(e):
            asked = "; ".join("%s [%s]" % (q.get("question"), " / ".join(str(o.get("label")) for o in q.get("options") or []))
                              for q in value.get("questions") or [] if isinstance(q, dict))
            what = "%squestion: %s" % ("async " if e.get("async") else "", _first_line(asked, 160))
        else:
            what = "permission: %s %s" % (e.get("tool"), _tool_summary(e.get("tool"), value))
        window = ""
        if isinstance(e.get("deadline"), (int, float)):
            window = ", answerable from outside until %s" % time.strftime("%H:%M:%S", time.localtime(e["deadline"] / 1000))
        self.line("· [%s] %s — request %s%s" % (self.label(agent), what, e.get("request"), window))

    def _name(self, a):
        if a.get("agentId"):
            self.labels[a["agentId"]] = "%s %s" % (a.get("subagentType") or "agent", str(a["agentId"])[:12])


def _compact_outcome(e):
    if e.get("error"):
        return "failed: %s" % e["error"]
    if e.get("skip"):
        return "skipped: %s" % e["skip"]
    if e.get("tokensBefore") is not None and e.get("tokensAfter") is not None:
        return "done: %s → %s tokens" % (format(e["tokensBefore"], ","), format(e["tokensAfter"], ","))
    return "done"


def _reconnect_window():
    try:
        return float(os.environ.get("SMINOS_BRIDGE_RECONNECT") or 5)
    except ValueError:
        return 5.0


def cmd_watch(a):
    session = watch_session(a.member)
    path = endpoint(session)
    if probe(path) is None:
        remove_stale(path)
        S.die("%s has no bridge on this machine (no session endpoint answers at %s)" % (a.member, path),
              S.EXIT_UNKNOWN)
    render = None if a.json else Renderer(sys.stdout)

    def show(e):
        if render is None:
            sys.stdout.write(json.dumps(e) + "\n")
            sys.stdout.flush()
        else:
            render.feed(e)

    def say(text):
        (render.line if render else lambda t: sys.stderr.write(t + "\n"))(text)

    ended = False
    pid = None
    try:
        while True:
            lost = False
            try:
                for e in subscribe(path):
                    if e.get("type") == "snapshot":
                        pid = e.get("pid")
                    show(e)
                    if e.get("type") == "session" and e.get("phase") == "end" and e.get("reason") != "clear":
                        ended = True
                    # What was printed misses the lost events: a fresh snapshot
                    # (DX4's rule on a gap) prints each message whole again.
                    # --json passes the gap on; its stream ends at the resync.
                    if e.get("type") == "gap" and render is not None:
                        lost = True
                        break
            except (OSError, http.client.HTTPException, ValueError):
                pass
            if ended:
                say("· the session ended")
                return
            if lost and probe(path) is not None:
                continue
            # The stream ended: the child replaced its state from the mod (a
            # resync), restarted (a module reload), or is gone. Followed while
            # an endpoint answers there again within the window.
            deadline = time.time() + _reconnect_window()
            while time.time() < deadline and probe(path) is None:
                time.sleep(0.1)
            now = probe(path)
            if now is None:
                remove_stale(path)
                say("· the bridge ended")
                sys.exit(1)
            say("· the session's state was sent again; resubscribed" if now.get("pid") == pid
                else "· the bridge restarted; reconnected")
    except KeyboardInterrupt:
        return
