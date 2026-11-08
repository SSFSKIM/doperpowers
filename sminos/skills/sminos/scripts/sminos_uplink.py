#!/usr/bin/env python3
"""sminos_uplink — the machine's connection to its endpoint (RL10, MAWS's
`mawsd`; DC4 of the desk, the frames O10's Interfaces §D).

`sminos daemon uplink` is its own process, which `daemon run` starts as a
child on a machine cut over to its endpoint (sminos_rl10: daemon/identity.json)
and restarts when it exits; at most one runs per $SMINOS_HOME
(`daemon/uplink.lock`), and it ends when its parent does (the parent names
itself at spawn, so one already gone at startup counts). It dials the
endpoint rl10.json names, says `hello`, keeps the identity the welcome gives
(sminos_rl10.welcomed), and reconnects with backoff while rl10.json names
an endpoint. Before the cutover no uplink runs: the endpoint is only probed
(cmd_probe), and a whole welcome cuts the machine over.

The threads: a reader that only reads the socket (sminos_rl10.Reader, no
sminos call) into a queue, so the socket is drained whatever the rest is
doing; one lane (SocketLane), a thread that writes in order what the main
thread queues on it — the log plane's frames (the connect's bundle,
uploads, outcomes, rejections, the machine's presence, every re-`hello`),
the session plane's, the members', the requests' and the RPC results — so
an endpoint slow to read stops neither the pump nor the reader; and the
process's main thread, which does every sminos call and never waits on
the network. sminos's per-invocation caches are module globals no second
thread may share, and a git phase of the tick loop, a derivation, or this
process's own delivery never holds the reader up. The main thread takes
whatever is queued as one batch, then ticks once: what the batch imported
is delivered once per project, so a burst from the endpoint costs a tick,
not a tick a frame. The lane's continuations come back on the same queue
and run there, in order: the socket is one ordered stream with no
per-frame answer, so a frame written is a frame taken.

The endpoint sends the org's directory (`org`: every project of the org,
with its kind and whether it is retired, and every enrolled machine); the
uplink keeps it at daemon/org.json and registers every project of it it
does not know (root ""), so the machine follows every project of its org.
On every connection, for every hub project of this machine's org known
here (hub_projects), the uplink sends `hello` with its vector — `follow`
when the machine has no checkout of it and no session in it, and again
whenever that changes — and, for a project it holds, its machine's
presence (DX4 `machine`), then uploads its own writers' suffix past the
endpoint's `have`, and from then on what they append; it follows `resend`,
says each `refused` in daemon.log, and imports what the endpoint sends
(sminos_hublog.py: each event checked before it enters the log, a refused
one reported up as `rejected`). Every archive period it says `hello` again
for each project it opened, so the answer — whether this machine writes
the project's git archive (sminos_archive.py) — is never older than a
period, even on a connection that never drops. The session plane
(sminos_plane.py) rides the same connection: each session's presence
after the `hello` and whenever it changes, and the endpoint's
subscriptions served as DX4 messages; a bridge's reader wakes the main
thread, so what it read goes up at once. The plane's transcripts and its
warmer are the process's, kept across connections: the builds the warmer
keeps current for the live members are saved under daemon/plane/ as they
grow and once more at the uplink's stop (STOP_SAVE_SECONDS at most), and
loaded by the next process, which sweeps the ones past their keep as it
starts. The machine's policy (sminos_policy) goes up in `machine` on every
connect and again whenever it changes; the requests the bridges raise and
settle go up as DX4 `raised` and `settled`, and the complete pending set
after every connect (sminos_requests); what delivery made of each event
from outside, as DX4 `delivery` (sminos_outcomes); and the RPCs the
endpoint forwards, checked, executed at most once, and answered as
`rpc-result` until `rpc-ack` (sminos_rpc). A write that fails, or a lane
holding more than SEND_QUEUE_MAX unsent, ends the connection, and the next
one redoes the handshake: what the handshake heals is marked sent when
queued (the vector's reach, a complete pending set, an RPC result), and
what it does not (the presence tombstone, rejections reported, outcomes
dropped, settlements and compaction messages) only once its frame is
written, in flight meanwhile. Frames larger than FRAME_LIMIT travel as
parts, both ways.

Everything a reconnect restates goes again after each welcome, closed by
`restated {}` once the whole of it is queued (Link.restated_due): the
endpoint then withdraws whatever session the restatement left out. The
endpoint's own frames down — its policy, its revocation set, its ask for
the machine's old desk key (`legacy-key?`, answered from hub.json), a
device's `query` and `tombstone` of an operation, and `spent`, a position
it refused for good, recorded as one refused here (HubLog.spend) — are
handled in the Link. Up the socket go `member` frames too (O12 M6,
Link.members): every session of this machine, in every project known here
whether the endpoint relays it or not (the endpoint decides a person's
words from them), the whole set after each welcome, then each one that
changed, and `{session, gone: true}` for one that left. A revocation set
from the endpoint marks every event owed here that a revoked signer signed
(Link.mark_revoked: never delivered, its outcome up). And a person's words
are delivered here alone, on the endpoint's verdict: each tick's words pass
(Link.ask_words), behind its upload pass, asks `words?` about the first
owed event of each words-gated writer, naming the project whose log holds
it, and the `words` answer is carried out at once (on_words,
sminos.deliver_verdict). Where the welcome advertised `reach` (P5 O18
D3, D8) every peer push is delivered here alone too, on the endpoint's
answer: the same pass asks `reach?` about the first owed event of each
writer a push would hand over as a peer frame (sminos.reach_due), a
`peer` words verdict asks it again for its event, and a `deliver` is
carried out at once under a permit for that push alone
(sminos.deliver_reach); `refuse` settles `refused-reach` here, and no
answer leaves it owed. An endpoint rebuilding a lost policy cache asks
`snapshots?` of one project at a time, and each ask is answered with one
bounded page of the newest stored `joined` and `state` of each remote
session writer, plain and stream (on_snapshots, snapshot_page; O18 D7).
"""

import collections
import fcntl
import glob
import itertools
import json
import os
import queue
import re
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_archive as archive  # noqa: E402
import sminos_audience as audience  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_plane as plane  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_requests as requests  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_rpc as rpc  # noqa: E402
import sminos_visibility as setters  # noqa: E402

BACKOFF_MAX = 60
POLL = 0.25               # how often the main thread looks up from an idle stream
DRAIN_FRAMES = 1000       # what is queued is handled as one batch, then one tick: at most this many items
DRAIN_FOR = 1.0           # or this long of handling, so a burst neither starves the tick nor holds delivery
FRAME_LIMIT = 1 << 20     # every frame, either way, at most 1 MiB of UTF-8 a line; a larger one goes as parts
SCAN_EVERY = 2.0          # how often the projects known here are looked over for a hub project to open
UPLOAD_EVERY = 0.5        # how often this machine's writers are looked at for events to upload
CHECKOUTS_EVERY = 10.0    # how often the machine presence's checkouts are read again (the policy: every scan)
SEND_QUEUE_MAX = 16 << 20  # a lane holding more unsent than this: the endpoint is not taking frames, the connection ends
UPLOAD_AHEAD = 4 << 20    # an upload pass queues no more while the lane holds this much unsent
LANE_ENTRY = 256 * 1024    # RL10: the host and words passes queue lane entries of at most this many bytes
WORDS_WAIT = 10.0         # RL10: how long a `words?` waits for its verdict; past it, a failed attempt (O12 M6)
WORDS_EVERY = 10.0        # RL10: how often the words pass looks for owed words when nothing asked for one
REACH_WAIT = 10.0         # RL10: how long a `reach?` waits for its answer; past it, owed still, no attempt (P5 O18)
SNAPSHOT_PAGE = 200       # RL10: a `snapshots` page carries at most this many events, in at most LANE_ENTRY bytes
SNAPSHOT_KINDS = ("joined", "state")
# RL10: a file each words pass appends one line to ({at, wall, cpu, asks}), when set: the measurement
# O14's B2 gates the cutover on (sminos/tests/bench_scale.py run --rl10), and nothing else's
WORDS_TIMES = "SMINOS_WORDS_TIMES"


def legacy_key_path():
    """hub.json, as `legacy-key?` reads it: its `org` and DX1 `key`, nothing
    else (Link.on_legacy_key). No enrollment and no credential."""
    return daemon.daemon_path("hub.json")


def log(line):
    sminos.daemon_log("uplink: " + line)


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
    """The lines a frame travels as: its JSON text when within `limit`
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
    """A frame not written to the endpoint: nothing queued may be taken as landed."""


class Stopping(EndStream):
    """The uplink is ending (SIGTERM, or its daemon is gone) while it writes."""


# ------------------------------------------------------------- frames by project


def project_of(frame):
    """The project a frame up is of, when it says (a session message's, a
    pending set's, an RPC result's); else None."""
    pid = frame.get("project")
    if not isinstance(pid, str) and isinstance(frame.get("message"), dict):
        pid = frame["message"].get("project")
    return pid if isinstance(pid, str) else None


def by_project(frames):
    """The frames as runs of one project each, in the order each project
    first comes, each run in its own order."""
    runs = {}
    for frame in frames:
        runs.setdefault(project_of(frame), []).append(frame)
    return list(runs.values())


# ------------------------------------------------------------- RL10's lane


class SocketLane(threading.Thread):
    """RL10's one lane: a thread that writes, in FIFO order, what the main
    thread queues (`send`) on the endpoint's socket. The socket is one ordered
    stream with no per-frame answer, so a frame written is taken: once an
    entry's lines are written, ("sent", [then, ...]) goes on the transport's
    items for the main loop to run. A write that fails, or more than
    SEND_QUEUE_MAX unsent, ends the lane: ("closed", NotDelivered) is put
    once, and the connection ends."""

    def __init__(self, conn, put, ended):
        super().__init__(name="uplink-rl10-lane", daemon=True)
        self.conn, self.put = conn, put
        self.closing = threading.Event()
        self.ended = lambda: ended() or self.closing.is_set()
        self.cv = threading.Condition()
        self.entries = collections.deque()   # (bytes, then or None), in the order they go
        self.unsent = 0
        self.state = "idle"                  # idle | writing | closed

    def send(self, frames, then=None):
        data = b"".join(line.encode("utf-8") + b"\n" for frame in frames for line in to_wire(frame))
        with self.cv:
            if self.state == "closed":
                return
            self.entries.append((data, then))
            self.unsent += len(data)
            over = self.unsent > SEND_QUEUE_MAX
            self.cv.notify()
        if over:
            self.close()
            raise NotDelivered("the RL10 lane holds more than %d MiB unsent: the endpoint is not taking frames"
                               % (SEND_QUEUE_MAX >> 20))

    def posting(self):
        return self.state == "writing"

    def queued(self):
        return self.unsent

    def close(self):
        self.closing.set()
        with self.cv:
            self.state = "closed"
            self.entries.clear()
            self.unsent = 0
            self.cv.notify()

    def run(self):
        while True:
            with self.cv:
                while not self.entries and self.state != "closed" and not self.ended():
                    self.cv.wait(POLL)
                if self.state == "closed" or self.ended():
                    self.state = "closed"
                    return
                taken = list(self.entries)
                self.entries.clear()
                size = sum(len(data) for data, _ in taken)
                self.state = "writing"
            try:
                self.conn.write(b"".join(data for data, _ in taken))
            except OSError as e:
                with self.cv:
                    closed, self.state = self.state == "closed" or self.ended(), "closed"
                    self.entries.clear()
                    self.unsent = 0
                if not closed:
                    self.put(("closed", NotDelivered("a write to the endpoint failed: %s"
                                                     % (" ".join(str(e).split()) or type(e).__name__))))
                return
            with self.cv:
                self.unsent -= size
                if self.state == "writing":
                    self.state = "idle"
            thens = [then for _, then in taken if then is not None]
            if thens:
                self.put(("sent", thens))


class SocketTransport:
    """RL10's transport for a Link: the endpoint's connection, read by
    sminos_rl10's Reader onto `items` (the welcome already read is put first),
    and written by one SocketLane, made at the welcome. `number` counts the
    process's connections: the Link's generation."""

    numbers = itertools.count(1)

    def __init__(self, conn, welcome, ended):
        self.conn, self.ended = conn, ended
        self.number = next(self.numbers)
        self.reader = rl10.Reader(conn)
        self.items = self.reader.items
        self.items.put(("frame", "welcome", json.dumps(welcome), time.time()))
        self.lane_ = None

    def start(self):
        self.reader.start()

    def lane(self):
        if self.lane_ is not None:
            self.lane_.close()
        self.lane_ = SocketLane(self.conn, self.items.put, self.ended)
        self.lane_.start()
        return self.lane_

    def close(self):
        if self.lane_ is not None:
            self.lane_.close()
        self.conn.close()


# ------------------------------------------------------------- the projects


def hub_projects(cred):
    """{project id: project} of every project known here registered as one of
    this machine's org's (its project.json's hub names the org), rooted or
    not, but those the org's directory marks retired. Whether a root's .smns
    still names the project decides only whether this machine holds or
    follows it (Link.holds): the org's directory, not a checkout's file, says
    which projects exist, and a .smns edit on one checkout must not strand the
    retirements it causes."""
    out = {}
    for p in sminos.known_projects():
        if p.id in out or not (isinstance(p.hub, dict) and p.hub.get("org") == cred["org"]) \
                or sminos.org_retired(p.id):
            continue
        fresh = sminos.resolve_project(p.root) if p.root and not sminos.read_refused(p.root) \
            and os.path.isdir(p.root) else None
        out[p.id] = fresh if fresh is not None and fresh.id == p.id else p
    return out


def register_own(cred):
    """This machine's own project registered here (project.json), so it is
    hello'ed on every stream whether or not the hub has listed it yet — the
    hello is what registers it at a hub this machine enrolled at before
    machine projects existed."""
    sminos.project_path(sminos.machine_project(cred["org"], cred["machine"]), "log")


def keep_org(frame, cred):
    """The hub's `org` frame kept at daemon/org.json (its projects and
    machines, and when it came), and every project it names that is not
    retired and not known here registered as a followed one: the five fields
    project_path writes, root "", the hub the enrollment's. Whether the frame
    was one to keep."""
    projects, machines = frame.get("projects"), frame.get("machines")
    if not (isinstance(projects, list) and isinstance(machines, list)):
        return False
    projects = [p for p in projects if isinstance(p, dict) and isinstance(p.get("id"), str)
                and sminos.valid_name(p["id"]) and isinstance(p.get("name"), str) and p["name"].strip()
                and "\n" not in p["name"] and p.get("kind") in ("hub", "machine") and isinstance(p.get("retired"), bool)]
    machines = [m for m in machines if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"]
                and isinstance(m.get("online"), bool) and (m.get("seen") is None or isinstance(m.get("seen"), str))]
    path = sminos.org_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    sminos.write_json(path, {"projects": projects, "machines": machines, "at": sminos.now(ms=True)})
    hub = {"url": cred["hub"], "org": cred["org"]}
    for p in projects:
        if not p["retired"]:
            sminos.register_if_absent(sminos.make_project(p["id"], p["name"], "", "", hub))
    sminos.forget_caches()
    return True


def hub_project(pid, cred):
    """The project a frame names, when this machine knows it and its .smns
    names a hub of this machine's org; else None."""
    if not (isinstance(pid, str) and sminos.valid_name(pid)):
        return None
    return hub_projects(cred).get(pid)


def _snapshot_index(events):
    """{writer: {kind: its newest stored event}} of SNAPSHOT_KINDS, for every
    writer of a session (sminos.writer_session: plain and stream)."""
    out = {}
    for e in events:
        if e["kind"] in SNAPSHOT_KINDS and sminos.writer_session(e["writer"]):
            held = out.setdefault(e["writer"], {})
            if e["kind"] not in held or e["seq"] > held[e["kind"]]["seq"]:
                held[e["kind"]] = e
    return out


def snapshot_page(hl, after=None):
    """(events, next): one `snapshots` page of a project (O18 D7, Interfaces
    §B), the newest stored `joined` and `state` of each remote session
    writer (not this machine's under any of its names, HubLog.is_own), in
    writer order past `after` (the last writer of the page before), each as
    stored less `verified`, as `words?` sends one. A page holds whole
    writers, at most SNAPSHOT_PAGE events in at most LANE_ENTRY bytes (and
    at least one writer); `next` is its last writer while any remain, else
    None. Read from the merged log the readers keep (log_memo), so a
    rebuild's pages scan the log once while no file of it moves."""
    events = sminos._store_whole(hl.project, "log", shared=True)[1]
    index = sminos.log_memo(events, "snapshots", _snapshot_index)
    writers = sorted(w for w in index if not hl.is_own(w) and not (isinstance(after, str) and w <= after))
    page, size = [], 1024   # room for the frame around them: its id, project and cursor
    for i, w in enumerate(writers):
        these = [{k: v for k, v in e.items() if k != "verified"}
                 for e in sorted(index[w].values(), key=lambda e: e["seq"])]
        n = sum(len(json.dumps(e, ensure_ascii=False).encode("utf-8")) + 1 for e in these)
        if page and (len(page) + len(these) > SNAPSHOT_PAGE or size + n > LANE_ENTRY):
            return page, writers[i - 1]
        page += these
        size += n
    return page, None


def joined_dirs(here):
    """The directories a project's sessions joined from here, in order, as
    the plane's read holds them ({session: cwd}, Plane.here): what of that
    read the machine presence's checkouts are drawn from
    (policy.known_checkouts). None for a project not read."""
    return None if here is None else tuple(dict.fromkeys(here.values()))


# ------------------------------------------------------------- one stream


def member_frame(pid, m, launch=None, visibility=False):
    """RL10's `member` for a local member's row (Plane.member_rows): its record's
    provenance and ownership (sminos.session_record; the defaults, `@machine`
    and a terminal origin, with no principal or inference, while it has
    none), the lane — B when its controller says so, or when no controller
    is set yet and the engine host launched it (origin `maws`), else A —
    what the row says of it, and `launch`, the launch its bridge names (O12
    M7: what a remote action's context is fenced to), absent with no bridge.
    `visibility` (the endpoint's welcome advertised `access`, P5 O18 D9):
    the record's `access`, `shares` and `policyRev` too, the defaults where
    it says nothing (sminos_audience.policy_of); an older endpoint rejects a
    whole frame on a share grade it does not know, so none is sent to it.
    `principal` and `inference` cross because the endpoint is this machine;
    they never ride a log event."""
    rec = m.record or {}
    origin = rec.get("origin") if isinstance(rec.get("origin"), dict) else dict(sminos.DEFAULT_ORIGIN)
    controller = rec.get("controller") if isinstance(rec.get("controller"), dict) else None
    lane = "B" if (controller or {}).get("lane") == "B" or (controller is None and origin.get("kind") == "maws") \
        else "A"
    frame = {"t": "member", "session": m.session, "alias": m.alias, "project": pid, "lane": lane,
             "state": m.state}
    if m.title:
        frame["title"] = m.title
    frame["cwd"] = m.cwd
    if m.worktree:
        frame["worktree"] = m.worktree
    if launch is not None:
        frame["launch"] = launch
    frame["owners"] = list(rec["owners"]) if isinstance(rec.get("owners"), list) else list(sminos.DEFAULT_OWNERS)
    frame["ownersProof"] = list(rec["ownersProof"]) if isinstance(rec.get("ownersProof"), list) else []
    frame["origin"] = origin
    for key in ("principal", "inference", "controller"):
        if rec.get(key) is not None:
            frame[key] = rec[key]
    if visibility:
        frame["access"], frame["shares"], frame["policyRev"] = audience.policy_of(rec)
    return frame


class Here:
    """What the uplink knows of this machine, as an RPC's checks ask it
    (sminos_rpc), on the main thread."""

    def __init__(self, link):
        self.link = link

    def project(self, pid):
        return hub_project(pid, self.link.cred)

    def has_session(self, project, sid):
        plane_ = self.link.plane
        if sid not in plane_.here.get(project.id, {}):
            sminos.forget_caches()
            plane_.refresh(project)
        return sid in plane_.here.get(project.id, {})

    def record(self, sid):
        plane_ = self.link.plane
        plane_.live = plane_.records.scan()
        return plane_.live.get(sid) if plane_.running(sid) else None

    def checkouts(self, project):
        return policy.known_checkouts(project)


class Link:
    """One connection's conversation with the endpoint (RL10). Frames down
    are dispatched by `t`: the log plane's here, the session plane's to
    `self.plane`, the RPCs to `self.rpcs`, and the endpoint's own (its
    policy, revocations, verdicts, asks). Frames up go on the connection's
    one SocketLane (`log_lane` and `session_lane` name it both): the log
    plane's — the connect's bundle, uploads, delivery outcomes, rejections,
    the machine's presence and every re-`hello` — and the session plane's,
    the members', the requests' and the RPC results. A write that fails ends
    the connection: the next one redoes the handshake, which is idempotent,
    rather than assume anything landed. So a mark the handshake heals is
    placed when its frames are queued; one it does not — the presence
    tombstone, rejections reported, outcomes dropped — in the continuation
    that runs once the frame carrying them is written, its producer not
    taking the same again meanwhile (`reporting`, `delivering`); settlements
    and compaction messages, in flight from `sending`, leave their outbox in
    that continuation. A continuation clears its in-flight flags whatever
    its local writes meet; a write that fails is kept and done on a later
    pass (settle_marks), so a disk error never holds the network back.
    `wake` asks the main thread for a tick now."""

    def __init__(self, cred, logs, ended=lambda: False, wake=lambda: None, bridges=None, reqs=None, rpcs=None,
                 warmer=None, *, transport):
        self.cred = cred
        self.ended = ended
        self.transport = transport   # the endpoint's socket (SocketTransport), whose one lane carries everything
        self.policy_asked = None  # RL10: the policy-set last sent on this connection, until the endpoint's `policy`
        self.revoked_whole = False  # RL10: the next revocation set is the welcome's, kept whole
        self.revoked_due = False  # RL10: a revocation set was kept that the owed events have not been marked by
        self.members_sent = {}    # RL10: session → the `member` frame last sent on this connection
        self.visibility = False   # RL10: the endpoint's welcome advertised `access` (P5 O18 D9): member frames carry it
        self.reach = False        # RL10: it advertised `reach` (P5 O18 D3): every peer push here waits for its answer
        self.members_unsent = set()   # RL10: the sessions whose frame is due and not yet queued (publish_members)
        self.member_read_for = None   # RL10: the running sessions the projects known here were last listed for
        self.next_member_read = 0.0   # RL10: when they are read again (monotonic) when none came or went
        self.next_member_whole = 0.0  # RL10: when every one is read again, whatever its inputs (Plane.stale)
        self.member_known = {}    # RL10: project id → project, every project known here as last listed (members)
        self.transitions_failing = ""   # complete_transitions' failure as last said
        self.unlisted = set()     # RL10: (project id, session) a writer named and its rows did not, since that listing
        self.asks = {}            # RL10: a `words?` or `reach?` id → what it asked (ask_words), until answered or due
        self.asked = {}           # RL10: (project id, session, writer) → the id of its one ask out, of either kind
        self.reach_silent = set()  # RL10: the asked keys whose `reach?` went unanswered, said once in daemon.log
        self.words_due = True     # RL10: the words pass runs at the next tick (and every WORDS_EVERY)
        self.next_words = 0.0     # RL10: when it runs again unasked (monotonic)
        self.restating = False    # RL10: this connection's welcome began a restatement not closed by `restated` yet
        self.restate_scanned = False  # RL10: a whole scan (every hub project opened) ran since the welcome
        self.members_whole = False    # RL10: the whole member set was queued since the welcome
        self.logs = logs          # project id → HubLog, kept across streams
        self.generation = None
        self.opened = set()       # the projects `hello`ed on this stream
        self.parts = Parts()
        self.next_scan = self.next_upload = 0.0
        self.look_whole = True    # the next upload pass looks at every own writer (tick)
        self.next_confirm = 0.0   # when the opened projects are `hello`ed again (sminos_archive)
        self.nudge = daemon.nudged_at()
        self.passed = set()
        self.received = None      # when the reader took the frame being dispatched (epoch s), when known
        self.failing = self.plane_failing = ""
        self.plane = plane.Plane(cred["machine"], wake, bridges, warmer=warmer)   # the warmer kept across streams
        self.requests = reqs or requests.Requests(cred["machine"])  # kept across streams by the uplink
        self.requests.wake = wake
        self.rpcs = rpcs or rpc.Rpcs(cred["machine"])  # kept across streams by the uplink
        self.rpcs.wake = wake
        self.machine_sent = {}    # project id → the `machine` body last posted on this stream
        self.next_checkouts = 0.0
        self.own = sminos.machine_project_id(cred["org"], cred["machine"])  # always held: its strays are its members
        self.follows = {}         # project id → whether its last `hello` on this stream said `follow`
        self.checkouts = {}       # project id → whether it had a known checkout here when last read
        self.checkouts_from = {}  # project id → the joined_dirs its checkouts were last drawn from (draw_machine)
        self.imported = {}        # project id → HubLog: imports not yet delivered (deliver_imports)
        self.log_lane = self.session_lane = None  # the stream's senders, from its welcome on
        self.reporting = collections.Counter()   # project id → frames of its rejections not yet written
        self.delivering = set()   # project ids whose delivery outcomes are in a frame not yet written
        self.unrecorded = {}      # project id → rejections the hub took, their record not yet written
        self.undropped = {}       # project id → (outbox, lines) the hub took, their drop not yet done
        self.unsettled = {}       # (project id, what) → the failure last said (settle_marks)
        self.host_queued = {}     # RL10: project id → {writer: seq} of host events queued on this connection
        self.host_owed = {}       # RL10: project id → {(writer, seq): event} of an open's resend not queued yet
        self.handlers = {"welcome": self.on_welcome, "have": self.on_have,
                         "events": self.on_events, "resend": self.on_resend, "refused": self.on_refused,
                         "part": self.on_part, "subscribe": self.on_subscribe, "unsubscribe": self.on_unsubscribe,
                         "rows": self.on_rows, "diff": self.on_diff, "output": self.on_output, "read": self.on_read,
                         "rpc": self.on_rpc,
                         "rpc-ack": self.on_rpc_ack, "org": self.on_org,
                         # The endpoint's own (RL10, O10 Interfaces §D): its policy, its revocations, its ask
                         # for the machine's old desk key, a device's query and tombstone, the verdicts on words
                         # and reach, the positions it spent, an audience change and a snapshots ask.
                         "policy": self.on_policy, "revoked": self.on_revoked,
                         "legacy-key?": self.on_legacy_key, "query": self.on_query,
                         "tombstone": self.on_tombstone, "words": self.on_words, "reach": self.on_reach,
                         "spent": self.on_spent, "audience": self.on_audience,
                         "snapshots?": self.on_snapshots}

    def post_session(self, messages):
        if messages:
            self.session_lane.send([plane.frame(m) for m in messages])

    def ran(self, thens):
        """A lane's ("sent", thens): the continuations of what it wrote, in
        order. One that fails is that frame's failure, not the
        connection's."""
        for then in thens:
            try:
                then()
            except EndStream:
                raise
            except (Exception, SystemExit) as e:  # noqa: BLE001 — as a frame handler's
                log("the continuation of a write failed: %r" % e)

    def close_lanes(self):
        """Whether a lane was writing as they closed."""
        lanes = [lane for lane in (self.log_lane, self.session_lane) if lane is not None]
        posting = any(lane.posting() for lane in lanes)
        for lane in lanes:
            lane.close()
        self.log_lane = self.session_lane = None
        return posting

    def close(self):
        if self.close_lanes() and self.ended():
            log("the uplink is ending during a write: the connection is closed")
        self.plane.close()

    def dispatch(self, frame, stream):
        t = frame.get("t") if isinstance(frame, dict) else None
        if t not in ("events", "part", "org"):
            # Whatever this frame does comes after what the events before it
            # imported reached their members, as the frames came.
            self.deliver_imports()
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
        self.generation = self.transport.number
        self.opened.clear()
        self.machine_sent.clear()
        self.follows.clear()
        self.checkouts.clear()
        self.checkouts_from.clear()
        for hl in self.logs.values():
            hl.reset()
        self.plane.close()
        self.requests.reset()
        self.rpcs.reset()
        self.next_scan = 0.0
        sminos.forget_caches()   # a new stream's first scan reads the machine as it is now
        self.next_confirm = time.time() + archive.archive_every()
        self.close_lanes()
        self.reporting.clear()
        self.delivering.clear()
        self.members_sent = {}
        self.members_unsent = set()
        self.asks.clear()         # an ask is answered on its own connection, or never
        self.asked.clear()
        self.reach_silent.clear()
        self.words_due = True
        self.host_queued.clear()
        self.host_owed.clear()
        self.restating = True
        self.restate_scanned = self.members_whole = False
        self.log_lane = self.session_lane = self.transport.lane()
        log("connected to the endpoint (RL10, local-only) as %s (connection %d)"
            % (self.cred["machine"], self.generation))
        self.welcomed_rl10(frame)

    # ---------------------------------------------------- RL10's own frames down

    def welcomed_rl10(self, frame):
        """What an RL10 welcome carries beside the identity (kept before the
        Link was made, sminos_rl10.welcomed): the endpoint's policy, and the
        revocation set when it rides on the welcome; the set that follows
        is kept whole either way."""
        self.policy_asked = None
        self.revoked_whole = True
        # What the endpoint can do beyond RL10's major (OX1): with `access`, member frames carry the sessions'
        # visibility and the CLI's writers choose audience streams (P5 O18 D9), from the capabilities kept here.
        caps = frame.get("capabilities")
        caps = [c for c in caps if isinstance(c, str)] if isinstance(caps, list) else []
        self.visibility = "access" in caps
        self.reach = "reach" in caps
        try:
            audience.keep_capabilities(caps)
        except OSError as e:
            log("the endpoint's capabilities could not be kept (%s): this machine's writers read the last kept" % e)
        if isinstance(frame.get("revoked"), dict):
            self.on_revoked(frame["revoked"], None)
        self.on_policy(frame.get("policy"), None, welcome=True)

    def on_policy(self, frame, _stream, welcome=False):
        """The endpoint's policy, which is the machine's: kept in
        daemon/policy.json, the file deliver_next and the RPCs' admission
        read. A welcome's is not taken over a change made here since the
        endpoint's last word (`sminos daemon policy` while it was away),
        which goes up as policy-set instead and settles on its answer."""
        got = policy.endpoint_policy(frame)
        if got is None:
            if not welcome or frame is not None:
                log("a policy from the endpoint that is no policy: ignored")
            return
        if welcome and policy.unsent_change():
            self.sync_policy()
            return
        self.policy_asked = None
        policy.take_endpoint(got)
        self.next_checkouts = 0.0   # the presence's policy goes again (machine_presence)

    def sync_policy(self):
        """A change made here (`sminos daemon policy`) that the endpoint has
        not answered, sent up as policy-set with the fields that differ,
        once a connection unless it changes again."""
        change = policy.unsent_change()
        if change and change != self.policy_asked:
            self.policy_asked = change
            self.session_lane.send([{"t": "policy-set", **change}])
            log("the machine's policy changed here: asked the endpoint for %s" % json.dumps(change, sort_keys=True))

    def on_revoked(self, frame, _stream):
        """The endpoint's revocation set, kept in daemon/revoked.json: whole
        the first after a welcome, merged into after that (sminos_rl10);
        the owed events it names are marked at the next tick (mark_revoked),
        once the members' rows are read."""
        whole, self.revoked_whole = self.revoked_whole, False
        if rl10.keep_revoked(frame, whole):
            self.revoked_due = True

    def on_words(self, frame, _stream):
        """The endpoint's verdict on a `words?` (O12 M6), carried out at once
        (sminos.deliver_verdict: still the writer's first owed, its signer
        not revoked since), and the writer's next owed event asked at the next
        tick. An answer to no ask held here — one that expired and was asked
        again, one a revocation dropped — is no answer; one naming no verdict
        is a failed attempt, as silence is. Where the endpoint decides reach
        (P5 O18 D8) a `peer` verdict delivers nothing yet: the push it calls
        for asks `reach?` about the same event first (ask_peer), and the
        admission of the words never stands for it."""
        held = self.held_ask(frame, "words?")
        if held is None:
            return
        verdict = frame.get("verdict")
        if verdict not in sminos.WORDS_VERDICTS:
            log("the endpoint's answer on %s in %s names no verdict (%r): a failed attempt"
                % (sminos.event_ref(held["event"]), held["project"].name, verdict))
            sminos.words_unanswered(held["project"], held["member"], held["event"], "the endpoint named no verdict")
            return
        if verdict == "peer" and self.reach:
            self.ask_peer(held)
            return
        sminos.deliver_verdict(held["project"], held["member"], held["event"], verdict)
        self.next_upload = 0.0   # its outcome goes up on the next pass

    def held_ask(self, frame, kind):
        """The ask of this kind an answer names, no longer held (its key's
        ask out cleared, and the next pass due); None for an answer to no ask
        of this kind held here — one past its deadline, one a revocation
        dropped — which is no answer."""
        ask = frame.get("id")
        held = self.asks.get(ask) if isinstance(ask, str) else None
        if held is None or held.get("t", "words?") != kind:
            return None
        del self.asks[ask]
        self.asked.pop(held["key"], None)
        self.words_due = True
        return held

    def ask_peer(self, held):
        """A `peer` words verdict's push asked about first (P5 O18 D8: each
        push asks `reach?`, whatever admitted it before): the same event,
        remembered as the words pass's, under a new id. With the lane full
        nothing is asked now, and the event, still owed, is asked `words?`
        again by a later pass."""
        if self.session_lane.queued() >= UPLOAD_AHEAD:
            return
        e, project = held["event"], held["project"]
        ask = os.urandom(12).hex()
        self.queue_asks([(ask, {"key": held["key"], "project": project, "member": held["member"], "event": e,
                                "t": "reach?", "words": "peer"},
                          {"t": "reach?", "id": ask, "project": project.id, "session": held["member"].session,
                           "event": {k: v for k, v in e.items() if k != "verified"}})])

    def on_reach(self, frame, _stream):
        """The endpoint's answer on a `reach?` (P5 O18 D3), carried out at
        once (sminos.deliver_reach: still the writer's first owed, the same
        body): `deliver` the push it was asked for, under a permit for that
        push alone; `refuse` settled `refused-reach` here, with no outcome
        back. An answer to no ask held here, or one naming neither, is no
        answer: the event stays owed, asked again under a new id, no attempt
        counted."""
        held = self.held_ask(frame, "reach?")
        if held is None:
            return
        self.reach_silent.discard(held["key"])
        verdict = frame.get("verdict")
        if verdict not in sminos.REACH_VERDICTS:
            log("the endpoint's answer on the reach of %s in %s names no verdict (%r): it stays owed, asked again"
                % (sminos.event_ref(held["event"]), held["project"].name, verdict))
            return
        reason = frame.get("reason")
        reason = reason if isinstance(reason, str) and re.fullmatch(r"[a-z][a-z-]{0,39}", reason) else None
        sminos.deliver_reach(held["project"], held["member"], held["event"], verdict, reason)
        self.next_upload = 0.0   # its outcome goes up on the next pass

    def on_audience(self, frame, _stream):
        """The endpoint's word on one session's audience (P5 O18 D7): its
        owners, its members (none: listed) and policyRev, kept in
        daemon/audiences.json for the CLI's writers (sminos_audience). A
        frame that is no such frame is said and passed by. A local session's
        policy change pending at its policyRev (sminos_visibility) is
        completed around it: its `unlisted` notice before the audience is
        kept, so nothing goes under the new stream ahead of it, its snapshot
        after."""
        try:
            written = setters.notice_before(frame, self.visibility_project)
            if written is not None and written.id in self.logs:
                self.logs[written.id].undraw()   # drawn afresh, the notice's writer first (complete_transitions)
        except (Exception, SystemExit) as e:  # noqa: BLE001 — the tick's completion tries again
            log("the unlisted notice of session %r could not be written (%r): tried again"
                % (str(frame.get("session"))[:40], e))
        try:
            taken = audience.keep_audience(frame)
        except OSError as e:
            log("an audience frame could not be kept (%s): the writers read the last kept" % e)
            return
        if not taken:
            log("an audience frame from the endpoint that is none (session %r): passed by"
                % (str(frame.get("session"))[:40],))
            return
        self.complete_transitions({frame.get("session")})

    def visibility_project(self, sid):
        """The project a local session's policy change is told in: the one
        its member frame named, else the first whose rows hold it; None for
        a session that is no member here now."""
        pid = (self.members_sent.get(sid) or {}).get("project")
        if pid is None:
            pid = next((p for p, rows in sorted(self.plane.member_rows.items()) if sid in rows), None)
        if pid is None:
            return None
        return self.member_known.get(pid) or (self.logs[pid].project if pid in self.logs else None)

    def complete_transitions(self, sessions=None):
        """The pending policy changes whose audience the endpoint gave
        written (sminos_visibility.complete), what they wrote uploaded on
        the next pass; a failure said once while it holds, and tried again
        at the next tick.

        Each completed session's project has its upload drawn afresh
        (HubLog.undraw): a draw suspended between frames was sorted before
        the notice's writer existed and reads a writer's file only when it
        reaches it, so it could carry the snapshot, under a stream that
        already had events, ahead of the notice. A failure drops every
        project's draw: what it wrote is not known."""
        done = []
        try:
            try:
                done = setters.complete(self.visibility_project, sessions)
            except setters.TransitionFailed as e:
                done = e.done
                raise
            self.transitions_failing = ""
        except (Exception, SystemExit) as e:  # noqa: BLE001
            for hl in self.logs.values():
                hl.undraw()
            if repr(e) != self.transitions_failing:
                self.transitions_failing = repr(e)
                log("a policy change's notice and snapshot could not be written (%r): tried again" % e)
        for sid in done:
            project = self.visibility_project(sid)
            if project is not None and project.id in self.logs:
                self.logs[project.id].undraw()
        if done:
            self.next_upload = 0.0

    def on_snapshots(self, frame, _stream):
        """RL10's `snapshots? {id, project, after?}` (O18 D7): the endpoint
        rebuilding a lost policy cache, one project at a time, page after
        page, answered `snapshots {id, project, events, next, done}` with
        the page past `after` (snapshot_page), `done` on the project's last.
        A project that is no hub project of this org known here has none: one
        page, empty and done, said in daemon.log. sminos carries what it
        stored; the endpoint verifies each again before taking it."""
        ask, pid = frame.get("id"), frame.get("project")
        if not isinstance(ask, str):
            log("a snapshots? with no id (%r): not answered" % (ask,))
            return
        hl = self.logs[pid] if isinstance(pid, str) and pid in self.opened else self.log_of(pid)
        if hl is None:
            log("snapshots? for project %r, which is no hub project of org %s known here: answered with none"
                % (pid, self.cred["org"]))
            events, after = [], None
        else:
            events, after = snapshot_page(hl, frame.get("after"))
        self.session_lane.send([{"t": "snapshots", "id": ask, "project": pid, "events": events, "next": after,
                                 "done": after is None}])

    def on_legacy_key(self, _frame, _stream):
        """`legacy-key?`: hub.json's DX1 key handed to the endpoint, which
        welcomed this machine for the key's own org, as often as it asks
        while hub.json holds it (one logical handover: an endpoint that died
        before keeping it asks again). The key is in no log line."""
        try:
            with open(legacy_key_path()) as f:
                held = json.load(f)
        except FileNotFoundError:
            log("legacy-key?: this machine holds no DX1 key (no hub.json): not answered")
            return
        except (OSError, ValueError) as e:
            log("legacy-key?: hub.json cannot be read (%s): not answered" % type(e).__name__)
            return
        org = held.get("org") if isinstance(held, dict) else None
        key = held.get("key") if isinstance(held, dict) else None
        if not (isinstance(key, str) and codes.b64url_bytes(key, 32) is not None and isinstance(org, str)):
            log("legacy-key?: hub.json holds no DX1 key of 32 bytes: not answered")
            return
        if org != self.cred["org"]:
            log("legacy-key?: refused: the endpoint welcomed this machine for org %s, and hub.json's key is org %s's"
                % (self.cred["org"], org))
            return
        self.session_lane.send([{"t": "legacy-key", "org": org, "key": key}])
        log("legacy-key?: answered with hub.json's DX1 key of org %s" % org)

    def on_query(self, frame, _stream):
        """RL4's `query {opId, opCreated}`, which the endpoint asks for a
        device: the ledger's answer (Rpcs.query), up as `queried`."""
        op = frame.get("opId")
        if not (isinstance(op, str) and rpc.OP_ID_RE.fullmatch(op)):
            log("a query for no operation id (%r): not answered" % (op,))
            return
        view = self.rpcs.query(op, rpc.created_at(frame.get("opCreated")))
        self.session_lane.send([{"t": "queried", "opId": op, **view}])

    def on_tombstone(self, frame, _stream):
        """RL4's `tombstone {opId, opCreated?}`: the op given up, so a late
        copy never runs (Rpcs.tombstone), answered `tombstoned`."""
        op = frame.get("opId")
        if not (isinstance(op, str) and rpc.OP_ID_RE.fullmatch(op)):
            log("a tombstone for no operation id (%r): not answered" % (op,))
            return
        done = self.rpcs.tombstone(op, rpc.created_at(frame.get("opCreated")))
        self.session_lane.send([{"t": "tombstoned", "opId": op, **done}])

    def on_have(self, frame, _stream):
        hl = self.logs.get(frame.get("project"))
        if hl is not None and hl.project.id in self.opened:
            hl.on_have(frame)
            self.upload(hl)

    def on_events(self, frame, _stream):
        # A project open on this stream as the tick last registered it: each
        # frame of a burst looking every project over again (hub_projects)
        # was most of an import's cost, and an `org` frame taken ahead of the
        # queue must not drop the events the hub sent before it.
        pid = frame.get("project")
        hl = self.logs[pid] if isinstance(pid, str) and pid in self.opened else self.log_of(pid)
        if hl is None:
            log("events for project %r, which is no hub project of org %s known here: ignored"
                % (frame.get("project"), self.cred["org"]))
            return
        appended, rejections = hl.take(frame.get("events"))
        if appended:
            self.imported[hl.project.id] = hl
        if rejections and hl.project.id in self.opened:
            self.report(hl, rejections)

    def on_spent(self, frame, _stream):
        """RL10's `spent {project, writer, seq, reason}`: a position the
        endpoint refused for good, in stream order where its event would have
        come (O10 M6), recorded as one refused here (HubLog.spend)."""
        pid = frame.get("project")
        hl = self.logs[pid] if isinstance(pid, str) and pid in self.opened else self.log_of(pid)
        if hl is None:
            log("a spent position in project %r, which is no hub project of org %s known here: ignored"
                % (pid, self.cred["org"]))
            return
        hl.spend(frame.get("writer"), frame.get("seq"), frame.get("reason"))

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
        refusal = frame.get("refusal") if isinstance(frame.get("refusal"), dict) else {}
        if refusal.get("reason") == "not-open":
            # A refusal of a frame whose project this connection did not
            # hold open: passed by.
            return
        hl.on_refused(frame)

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
            self.post_session(self.plane.subscribe(project, frame, self.received))

    def on_unsubscribe(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.unsubscribe(frame.get("sub")))

    def on_rows(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.rows(frame))

    def on_diff(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.diff(frame))

    def on_output(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.output(frame))

    def on_read(self, frame, _stream):
        if self.opened_project(frame) is not None:
            self.post_session(self.plane.read(frame))

    def on_rpc(self, frame, _stream):
        self.rpcs.receive(frame.get("rpc"), Here(self), self.received)

    def on_rpc_ack(self, frame, _stream):
        self.rpcs.ack(frame)

    def on_org(self, frame, _stream):
        """The org's directory: kept, every project of it registered, and
        the projects looked over at once — a new one is followed, a retired
        one leaves (tick)."""
        if not keep_org(frame, self.cred):
            log("an org frame without its projects and machines: passed by")
            return
        self.next_scan = 0.0

    def deliver_imports(self):
        """What the frames handled since the last call imported, delivered
        once per project (sminos_hublog's `deliver`: a fresh read of the
        whole log), then the tick loop nudged once. The nudge is the tick
        loop's and every sender's: this uplink takes its own as seen, so
        what it imported costs its next tick no project scan, only the upload
        pass that sends what delivery made of it (`deliveries`). On RL10 the
        person's words it left owed are asked about by that tick's words
        pass, behind its upload pass (ask_words)."""
        if not self.imported:
            return
        imported, self.imported = self.imported, {}
        self.words_due = True
        for hl in imported.values():
            try:
                hl.deliver()
            except (Exception, SystemExit) as e:  # noqa: BLE001 — the daemon's tick delivers what is still owed
                log("delivering what was imported into %s failed: %r" % (hl.project.name, e))
        seen = daemon.nudged_at() == self.nudge
        sminos.nudge_daemon()
        if seen:
            # Only when no sender's nudge was waiting: that one is still this
            # uplink's to answer with a scan.
            self.nudge = daemon.nudged_at()
        self.next_upload = 0.0

    # ---------------------------------------------------- frames up

    def holds(self, pid):
        """Whether this machine holds the project rather than follows it: its
        own machine project, or one with a local member (the plane's) or a
        known checkout here (as last read)."""
        return pid == self.own or bool(self.plane.members.get(pid)) or self.checkouts.get(pid, False)

    def draw_machine(self, hl):
        """The project's `machine` presence (HubLog.presence), its checkouts
        drawn from the sessions the plane's last read found joined from here
        (Plane.here), so the view is not read again for them. Whether it has
        a checkout here is kept for holds, and the directories they were
        drawn from for machine_presence."""
        pid = hl.project.id
        here = self.plane.here.get(pid)
        machine = hl.presence(here)
        self.checkouts[pid] = bool(machine["message"]["body"]["checkouts"])
        self.checkouts_from[pid] = joined_dirs(here)
        return machine

    def open(self, hl):
        """`hello` for a project on this connection, with what is republished
        after every connect that is this child's — the machine's presence,
        for a project it holds — and the rejections not yet reported. A
        project it neither has a checkout of nor a session in is opened to
        follow (`follow`): no machine presence, and no session presence but
        the leavers'. A live member that joined under a former name of this
        machine joins again first, so the vector and the upload carry it.

        The bundle goes as one entry of the lane, ahead of whatever is queued
        behind it on the one ordered stream. Once it is written its
        continuation runs: the settlements it carried kept as relayed, the
        read its presence's leavers were drawn from marked taken (the
        tombstone mark), its rejections recorded as reported. What
        `deliveries` queues after it follows it on the same connection, so
        the endpoint takes it after the hello, and a write that fails ends
        the connection before any continuation behind it runs."""
        pid = hl.project.id
        hl.rejoin_former()
        unreported = [] if self.reporting[pid] else [f for f in hl.unreported()
                                                       if f not in self.unrecorded.get(pid, ())]
        self.plane.refresh(hl.project)
        machine = self.draw_machine(hl)
        follow = not self.holds(hl.project.id)
        sessions = [plane.frame(m) for m in self.plane.presence(hl.project.id, force=True)]
        read = self.plane.take_read(pid)
        # The project's bridges are followed before its set is drawn up: the
        # set goes now if they are read, else once they are (Requests.due).
        self.requests.follow(self.bridged(self.opened | {hl.project.id}))
        self.requests.take()
        owed = self.requests.opening(hl.project.id)
        results = self.rpcs.opening(hl.project.id)
        if unreported:
            self.reporting[pid] += 1
        self.requests.sending(owed)
        self.rpcs.sending(results)

        def answered():
            # Written behind the hello, the project open (a local write that fails is said, and costs a resend).
            self.requests.delivered(owed)
            self.rpcs.delivered(results)
            try:
                if read is not None:
                    self.plane.accepted(pid, read)   # these leavers were written: only later ones are said again
            finally:
                if unreported:
                    self.reported(hl, unreported)

        self.log_lane.send([hl.hello(follow)] + ([] if follow else [machine]) + sessions + unreported + owed + results,
                           then=answered)
        self.opened.add(pid)
        self.follows[pid] = follow
        if not follow:
            self.machine_sent[pid] = machine["message"]["body"]
        self.deliveries(hl)
        self.host_pass(hl, again=True)

    def report(self, hl, rejections):
        """Rejections up, reported once they are written."""
        self.reporting[hl.project.id] += 1
        self.log_lane.send(rejections, then=lambda: self.reported(hl, rejections))

    def reported(self, hl, rejections):
        """The rejections were written: no longer in flight, and recorded
        as reported (settle_marks)."""
        pid = hl.project.id
        self.reporting[pid] -= 1
        owed = self.unrecorded.setdefault(pid, [])
        owed.extend(f for f in rejections if f not in owed)
        self.settle_marks(hl)

    def settle_marks(self, hl):
        """What the hub took and this machine has yet to record, recorded:
        the rejections reported (uplink.json), the outcomes dropped (the
        outbox). A write that fails is said once and kept, and tried again on
        the next pass (`deliveries`, every upload pass); what it keeps is
        never posted again meanwhile."""
        pid = hl.project.id
        if self.unrecorded.get(pid):
            try:
                hl.reported(self.unrecorded[pid])
                del self.unrecorded[pid]
                self.unsettled.pop((pid, "reported"), None)
            except (Exception, SystemExit) as e:  # noqa: BLE001 — kept, and tried again
                self.unsettled_once((pid, "reported"), "recording the rejections of %s reported failed (%r): "
                                    "tried again" % (hl.project.name, e))
        if pid in self.undropped:
            box, lines = self.undropped[pid]
            try:
                box.drop(lines)
                del self.undropped[pid]
                self.unsettled.pop((pid, "dropped"), None)
            except (Exception, SystemExit) as e:  # noqa: BLE001 — kept, and tried again
                self.unsettled_once((pid, "dropped"), "dropping the outcomes of %s posted failed (%r): tried again"
                                    % (hl.project.name, e))

    def unsettled_once(self, key, line):
        if self.unsettled.get(key) != line:
            self.unsettled[key] = line
            log(line)

    def upload(self, hl, live=None):
        """The project's uploads queued, each its own entry, as far as the log
        lane holds less than UPLOAD_AHEAD unsent: the rest go on a later pass,
        so a long backlog paces itself instead of filling the lane past its
        bound. Each frame is drawn only once there is room for it, and the
        rest stays drawn where it was (HubLog.next_upload): a pass while the
        lane is full draws nothing, and no event is sealed twice. On RL10 the
        member frames of the sessions a drawn frame carries go first
        (members_before); while one cannot be queued yet, the frame is drawn
        again on a later pass (HubLog.undraw)."""
        while self.log_lane.queued() < UPLOAD_AHEAD:
            got = hl.next_upload(live)
            if got is None:
                return
            frame, reach = got
            try:
                out = self.members_before(hl.project, {sminos.writer_session(e["writer"]) for e in frame["events"]})
            except BaseException:
                hl.undraw()
                raise
            if not out:
                hl.undraw()
                return
            epochs = {w: hl.epoch(w) for w in reach}
            # Once written, taken (`taken`, what `daemon owed` reads) for each writer the upstream
            # neither refused nor asked again for since it was sent (HubLog.keep_taken's epochs).
            self.log_lane.send([frame], then=lambda reach=reach, epochs=epochs: hl.keep_taken(reach, epochs=epochs))
            hl.took(reach)

    def deliveries(self, hl):
        """What delivery made of the events from outside, as DX4 `delivery`
        messages as they go; dropped from the outbox once the frame that
        carried them is written, and not taken again meanwhile — nor while a drop that
        failed is still owed (settle_marks)."""
        pid = hl.project.id
        self.settle_marks(hl)
        if pid in self.delivering or pid in self.undropped:
            return
        box = outcomes.Outbox(hl.project)
        if not box.waiting():
            return
        records, lines = box.take()
        frames = [outcomes.message(self.cred["machine"], pid, r) for r in records]
        if not frames:
            self.undropped[pid] = (box, lines)
            self.settle_marks(hl)
            return
        self.delivering.add(pid)

        def answered():
            self.delivering.discard(pid)
            self.undropped[pid] = (box, lines)
            self.settle_marks(hl)

        self.log_lane.send(frames, then=answered)

    def host_pass(self, hl, again=False):
        """RL10: what the project's sessions sent their person (its host
        store, sminos.HOST_STORE) up the session lane, each event a sub-less
        `host` message {id: {writer, seq}, event}, whether or not anyone
        subscribes: the endpoint derives its `wrote` notification from these
        (O10 M3), and a session nobody watches is the one whose person needs
        it. What goes is what is past the project's cursor (HubLog.host_sent),
        which moves once it is written; `again`, on a project opened on a
        connection, owes each session's last plane.HOST_LAST again whatever
        the cursor, so an endpoint that died before keeping what it took
        loses nothing. The endpoint deduplicates by the id. Queued as the
        upload is, in entries of at most LANE_ENTRY, none while the lane holds
        UPLOAD_AHEAD unsent: a backlog (the endpoint was down) goes across
        passes, its cursor moving entry by entry, and never makes one entry
        the lane must refuse. Each writer's events go in seq order
        (sminos.host_order), so a pass that stops never leaves an unsent seq
        behind the cursor. The sessions' member frames go first, as for an
        upload (members_before): the endpoint lists, and notifies for, a
        session by its record."""
        pid = hl.project.id
        queued = self.host_queued.setdefault(pid, {})
        owed = self.host_owed.setdefault(pid, {})
        sent = hl.host_sent()
        by_writer = {}
        for path in sorted(glob.glob(os.path.join(glob.escape(hl.project.home), sminos.HOST_STORE, "*.jsonl"))):
            for e in sminos._log_file_events(path):
                if hl.is_own(e["writer"]) and sminos.writer_session(e["writer"]):
                    by_writer.setdefault(e["writer"], []).append(e)
        due = dict(owed)
        for writer, events in by_writer.items():
            at = max(sent.get(writer, 0), queued.get(writer, 0))
            due.update(((writer, e["seq"]), e) for e in events if e["seq"] > at)
        if again:
            by_session = {}
            for writer, events in by_writer.items():
                by_session.setdefault(sminos.writer_session(writer), []).extend(events)
            for events in by_session.values():
                last = {(e["writer"], e["seq"]): e for e in sminos.host_order(events)[-plane.HOST_LAST:]}
                owed.update(last)
                due.update(last)
        if due and (self.session_lane.queued() >= UPLOAD_AHEAD
                    or not self.members_before(hl.project, {sminos.writer_session(w) for w, _ in due})):
            return   # on a later pass, once the lane has room and its members are queued
        batch, size = [], 0
        for e in sminos.host_order(due.values()):
            if not batch and self.session_lane.queued() >= UPLOAD_AHEAD:
                return   # the rest on a later pass, owed or past the cursor
            frame = plane.frame(plane.envelope(pid, self.cred["machine"], sminos.writer_session(e["writer"]), "host",
                                               None, None, plane.host_body(e)))
            n = len(json.dumps(frame, ensure_ascii=False).encode("utf-8"))
            if batch and size + n > LANE_ENTRY:
                self.host_send(hl, batch)
                batch, size = [], 0
                if self.session_lane.queued() >= UPLOAD_AHEAD:
                    return
            batch.append((e, frame))
            size += n
        if batch:
            self.host_send(hl, batch)

    def host_send(self, hl, batch):
        """One entry of the host pass, [(event, frame)], queued: the events
        no longer owed, their writers queued up to them, and the cursor moved
        once it is written."""
        pid = hl.project.id
        queued, owed, reach = self.host_queued[pid], self.host_owed[pid], {}
        for e, _ in batch:
            key = (e["writer"], e["seq"])
            owed.pop(key, None)
            reach[key[0]] = max(key[1], reach.get(key[0], 0))
            queued[key[0]] = max(key[1], queued.get(key[0], 0))
        self.session_lane.send([frame for _, frame in batch], then=lambda: hl.keep_host_sent(reach))

    def machine_presence(self, now):
        """Each open project held or followed, as it is now, and the machine's
        presence in each it holds. At every scan a project whose local members
        came or went is hello'ed again — `follow` as it is now — with the
        machine's presence when it is held now (a follower posts none: the hub
        drops it); the checkouts are read again every CHECKOUTS_EVERY, or at
        once when the policy changed (a `daemon policy` nudges one), and a
        project's at once when the plane's read moved the directories its
        sessions joined from since they were drawn; `machine` goes again for
        each held project whose body changed."""
        current = policy.wire_policy()   # as HubLog.presence says it
        fresh = now >= self.next_checkouts or any(self.machine_sent.get(pid, {}).get("policy") != current
                                                  for pid in self.opened if not self.follows.get(pid))
        if fresh:
            self.next_checkouts = now + CHECKOUTS_EVERY
        for pid in sorted(self.opened):
            hl = self.logs[pid]
            machine = None
            # The checkouts come from the plane's last read (draw_machine),
            # which the plane's tick, after this scan, renews: a session's
            # new directory read since the last draw is drawn at this scan,
            # not left until the deadline that may have just gone by.
            if fresh or joined_dirs(self.plane.here.get(pid)) != self.checkouts_from.get(pid):
                machine = self.draw_machine(hl)
            follow = not self.holds(pid)
            if follow != self.follows.get(pid):
                frames = [hl.hello(follow)]
                if not follow:
                    machine = machine or self.draw_machine(hl)
                    frames.append(machine)
                self.log_lane.send(frames)
                self.follows[pid] = follow
                if follow:
                    self.machine_sent.pop(pid, None)
                else:
                    self.machine_sent[pid] = machine["message"]["body"]
                log("%s: %s" % (hl.project.name, "followed (no checkout and no session here)" if follow else
                                "held (a checkout or a session here)"))
            elif not follow and machine is not None and machine["message"]["body"] != self.machine_sent.get(pid):
                self.log_lane.send([machine])
                self.machine_sent[pid] = machine["message"]["body"]

    def bridged(self, pids):
        """{session: project id}: the members of these projects with a bridge
        endpoint here, whose requests are read: one listing of the bridges'
        directory, every POLL, rather than a look per member."""
        socks = plane.bridge_socks()
        return {sid: pid for pid in pids for sid in self.plane.members.get(pid, ()) if sid in socks}

    def relay_requests(self):
        """The requests of the open projects' bridged sessions: readers for
        them, and what they read, up — one entry per project, so each
        continuation follows the write of its own frames and no other
        project's. A settlement leaves the outbox, relayed, once its frame
        is written; a
        complete set is taken when queued (every connect sends one again)."""
        self.requests.follow(self.bridged(self.opened))
        self.requests.take()
        for frames in by_project(self.requests.due(self.opened)):
            self.requests.sending(frames)
            self.session_lane.send(frames, then=lambda f=frames: self.requests.delivered(f))

    def relay_rpcs(self):
        """The RPCs' results, their compactions' progress and their desk
        commands' runs, up, one entry per project: a result goes again on
        every stream until `rpc-ack`; a compact or op message is owed as a
        settlement is (sminos_owed). A `/reload-plugins` is finished by the
        plane's probe seeing its bridge answer from another child."""
        self.rpcs.compacted(self.requests.take_compacts())
        self.rpcs.ops(self.requests.take_ops())
        self.rpcs.effects(self.plane.bridges.answering)
        for frames in by_project(self.rpcs.due(self.opened)):
            self.rpcs.sending(frames)
            self.session_lane.send(frames, then=lambda f=frames: self.rpcs.delivered(f))

    def members(self, now):
        """RL10's `member` frames up (member_frame): this machine's sessions
        in every project known here, from the plane's rows, each with the
        launch its bridge names. When a session
        came or went, and every MEMBERS_EVERY (`now`, monotonic), the
        projects known here are listed again and those the plane does not
        read itself (not open on the stream) are read — at MEMBERS_EVERY only
        those whose inputs moved (Plane.stale), every one when a session came
        or went or MEMBERS_WHOLE went by — as is any never read; between,
        what the plane's own reads changed is sent. The whole set
        goes after each welcome (members_sent is new with the connection),
        then each frame that changed, and `{session, gone: true}` for a
        session no longer here; a session in two projects' rows is sent for
        the first. The projects known here ({id: project}), as last listed."""
        live = set(self.plane.live)
        if live != self.member_read_for or now >= self.next_member_read:
            whole = live != self.member_read_for or now >= self.next_member_whole
            self.member_read_for, self.next_member_read = live, now + plane.MEMBERS_EVERY
            if whole:
                self.next_member_whole = now + plane.MEMBERS_WHOLE
            self.member_known = {p.id: p for p in sminos.known_projects()}
            self.unlisted.clear()
            # Those whose inputs moved, as the plane reads its own (Plane.stale).
            stale = self.plane.stale({pid: p for pid, p in self.member_known.items()
                                      if pid not in self.opened or pid not in self.plane.member_rows}, whole)
            if stale:
                # Their inputs hold the engine's records as the plane last
                # scanned them, which the cache generation can predate (the
                # plane renews it in its tick, after this): a read kept
                # against them draws on records at least as new.
                sminos.forget_caches()
            for project, inputs in stale:
                self.plane.reread(project, inputs)
        self.publish_members(now)
        return self.member_known

    def publish_members(self, now):
        """The member frames of the plane's rows as they are now, each that
        differs from the last sent on this connection, and `gone` for each
        session no longer among them (members). Queued as the host pass
        queues, in entries of at most LANE_ENTRY, none while the lane holds
        UPLOAD_AHEAD unsent (a frame carries the record's proofs, which a
        lineage inherits): what is left is due at the next pass
        (members_unsent), and what depends on it waits for it."""
        current = {}
        socks = plane.bridge_socks()
        for pid in sorted(pid for pid, rows in self.plane.member_rows.items() if rows and pid in self.member_known):
            for sid, m in sorted(self.plane.member_rows[pid].items()):
                if sid not in current:
                    # The bridge's probe keeps its launch (the plane's
                    # presence carries it); asked here too, so a session of
                    # a project not open on the stream has it as well.
                    self.plane.bridges.answers(sid, now, socks)
                    frame = self.fresh_frame(pid, m)
                    if frame is None:
                        # An established record that cannot be read (P5 O18 D10): its policy is unknown, so no
                        # frame goes, and one sent before is withdrawn (`gone` below), until it reads again.
                        continue
                    current[sid] = frame
        frames = [f for sid, f in current.items() if self.members_sent.get(sid) != f]
        frames += [{"t": "member", "session": sid, "gone": True} for sid in self.members_sent if sid not in current]
        batch, size, unsent = [], 0, set()
        for f in frames:
            n = len(json.dumps(f, ensure_ascii=False).encode("utf-8"))
            if batch and size + n > LANE_ENTRY:
                self.send_members(batch)
                batch, size = [], 0
            if unsent or (not batch and self.session_lane.queued() >= UPLOAD_AHEAD):
                unsent.add(f["session"])
                continue
            batch.append(f)
            size += n
        if batch:
            self.send_members(batch)
        self.members_unsent = unsent
        if not unsent:
            self.members_whole = True

    def fresh_frame(self, pid, m):
        """The member frame of a plane row from its session's record as it
        reads now (the row's may be a stale one, from before a repair or a
        policy change), or None while the record file exists and cannot be
        read. One read serves both, so the frame never pairs a fresh check
        with an older record."""
        records = sminos.records_module()
        rec = records.read(m.session)
        if rec is None and sminos.UUID_RE.fullmatch(m.session) and os.path.lexists(records.record_path(m.session)):
            return None
        return member_frame(pid, m._replace(record=rec), self.plane.bridges.launch(m.session), self.visibility)

    def send_members(self, batch):
        """One entry of member frames queued, and taken as sent."""
        self.session_lane.send(batch)
        for f in batch:
            if f.get("gone"):
                self.members_sent.pop(f["session"], None)
            else:
                self.members_sent[f["session"]] = f

    def members_before(self, project, sessions):
        """Whether each of these sessions' `member` frame is on the lane, its
        record as it is now, so what of theirs depends on it may follow: the
        endpoint signs an upload when its `events` frame arrives, attesting
        it from the record its `member` frames gave it, and keeps that
        signature (O10 M6); it lists a host message's session, and decides a
        `words?`, by the same record. A session that joined since its project
        was last read, or whose record changed since, would otherwise go up
        attested from no record or an older one. A session among no member
        sent is looked for in the project's rows, read again for it once per
        listing (members); one not there (it left) has none to give. False
        while a frame is due and not queued (publish_members): the caller
        holds what depends on it for a later pass."""
        sessions = {sid for sid in sessions if sid}
        if not sessions:
            return True
        pid = project.id
        missing = {sid for sid in sessions if sid not in self.members_sent and (pid, sid) not in self.unlisted}
        if missing:
            sminos.forget_caches()   # the engine's records as they are now (Plane.tick)
            self.plane.refresh(project)
            self.member_known.setdefault(pid, project)
            self.unlisted.update((pid, sid) for sid in missing if sid not in self.plane.member_rows.get(pid, {}))
        changed = bool(missing)
        for sid in sessions:
            at = self.members_sent[sid]["project"] if sid in self.members_sent else pid
            rows = self.plane.member_rows.get(at, {})
            if sid in rows:
                rows[sid] = rows[sid]._replace(record=sminos.session_record(sid))
                changed = changed or self.members_sent.get(sid) != self.fresh_frame(at, rows[sid])
        if changed or sessions & self.members_unsent:
            self.publish_members(time.monotonic())
        return not sessions & self.members_unsent

    def mark_revoked(self, known):
        """The revocation set kept since the last tick applied to what is
        owed here: every event owed to a local member (the plane's rows) whose
        stored signer it names is marked revoked, its `refused-revoked`
        outcome recorded for the next upload pass (sminos.revoke_owed), and
        every `words?` out for an event it names dropped, so a verdict for
        it is no answer. The deliverers check the set themselves before each
        push; this is what stops an owed event at once, asked or not."""
        self.revoked_due = False
        try:
            revoked = rl10.revoked()
        except rl10.RevokedUnreadable as e:
            log("the revocation set cannot be read (%s): nothing owed is marked until the endpoint's next" % e)
            return
        if not any(revoked[k] for k in rl10.REVOKED_SETS):
            return
        for ask, held in list(self.asks.items()):
            if rl10.event_revoked(held["event"], revoked):
                del self.asks[ask]   # a verdict for it is no answer now
                self.asked.pop(held["key"], None)
        try:
            for pid, project in sorted(known.items()):
                for sid, m in sorted(self.plane.member_rows.get(pid, {}).items()):
                    for e in sminos.revoke_owed(project, m, revoked):
                        log("%s in %s is signed by a revoked key: marked refused-revoked for %s, never delivered"
                            % (sminos.event_ref(e), project.name, sid[:8]))
                        self.next_upload = 0.0
        except BaseException:
            self.revoked_due = True   # the next tick tries again
            raise

    def ask_words(self, known):
        """The words pass (RL10, O12 M6), after the tick's upload pass, so an
        own event that could go up has gone up on this socket before its
        `words?`: for each local member of every project known here, the
        first owed event of each words-gated writer not yet asked
        (sminos.words_due) is sent as `words? {id, project, session, event}`,
        `project` the one whose log holds it (a `say` copies one message into
        two projects' logs), the event as stored with the endpoint's verdict
        left out, its session's
        member frame first (members_before). Queued as the host pass queues,
        in entries of at most LANE_ENTRY, none while the lane holds
        UPLOAD_AHEAD unsent: a broadcast to many sessions is asked across
        passes, never in one entry the lane must refuse. Each ask is held
        from when it is queued, with a WORDS_WAIT deadline; one not queued
        yet is not held, and is no attempt. A deadline passed is a failed
        attempt (sminos.words_unanswered), the event asked again under a new
        id. One whose signer is revoked is marked instead
        (sminos.revoke_owed), and one carrying a signer is not asked while
        the set cannot be read.

        Where the welcome advertised `reach` (P5 O18 D3, D8) the same pass
        asks `reach? {id, project, session, event}` alike about the first owed
        event of each writer a push would hand over as a peer frame
        (sminos.reach_due), the sending session's member frame first too when
        it is this machine's; one key's one ask out at a time, of either
        kind, so no writer has both. Its deadline is REACH_WAIT, and passing
        it counts nothing (expire_asks)."""
        now = time.monotonic()
        self.words_due, self.next_words = False, now + WORDS_EVERY
        try:
            self.expire_asks(now)
            if self.session_lane.queued() >= UPLOAD_AHEAD:
                self.words_due = True   # asked once the lane has room
                return
            try:
                revoked = rl10.revoked()
            except rl10.RevokedUnreadable:
                revoked = None
            batch, size = [], 0
            for pid, project in sorted(known.items()):
                rows = self.plane.member_rows.get(pid) or {}
                if not rows:
                    continue
                members = [m for _, m in sorted(rows.items())]
                owed = [(sid, e, "words?") for sid, due in sorted(sminos.words_due(project, members).items())
                        for e in due]
                if self.reach:
                    owed += [(sid, e, "reach?") for sid, due in sorted(sminos.reach_due(project, members).items())
                             for e in due]
                # The endpoint decides by the recipient's record, a reach by the sending session's of this machine too.
                sessions = {sid for sid, _, _ in owed} | {
                    sminos.writer_session(e["writer"]) for _, e, kind in owed if kind == "reach?"
                    and sminos.writer_base(e["writer"]) == "%s/%s" % (sminos.host_name(),
                                                                      sminos.writer_session(e["writer"]))}
                if owed and not self.members_before(project, sessions):
                    if batch:
                        self.queue_asks(batch)
                    self.words_due = True   # asked once their members are queued
                    return
                for sid, e, kind in owed:
                    key = (pid, sid, e["writer"])
                    if key in self.asked:
                        continue
                    if isinstance(e.get("verified"), dict) and (revoked is None or rl10.event_revoked(e, revoked)):
                        if revoked is not None:
                            for x in sminos.revoke_owed(project, rows[sid], revoked):
                                log("%s in %s is signed by a revoked key: marked refused-revoked for %s, never "
                                    "delivered" % (sminos.event_ref(x), project.name, sid[:8]))
                                self.next_upload = 0.0
                        continue
                    ask = os.urandom(12).hex()
                    frame = {"t": kind, "id": ask, "project": pid, "session": sid,
                             "event": {k: v for k, v in e.items() if k != "verified"}}
                    n = len(json.dumps(frame, ensure_ascii=False).encode("utf-8"))
                    if batch and size + n > LANE_ENTRY:
                        self.queue_asks(batch)
                        batch, size = [], 0
                        if self.session_lane.queued() >= UPLOAD_AHEAD:
                            self.words_due = True   # the rest on a later pass
                            return
                    batch.append((ask, {"key": key, "project": project, "member": rows[sid], "event": e, "t": kind},
                                  frame))
                    size += n
            if batch:
                self.queue_asks(batch)
        except BaseException:
            self.words_due = True   # the next tick tries again
            raise

    def words_pass(self, known):
        """ask_words, timed into WORDS_TIMES's file when it names one."""
        path = os.environ.get(WORDS_TIMES)
        if not path:
            return self.ask_words(known)
        at, wall, cpu = time.time(), time.perf_counter(), time.thread_time()   # the main thread's own CPU
        try:
            self.ask_words(known)
        finally:
            with open(path, "a") as f:
                f.write(json.dumps({"at": at, "wall": time.perf_counter() - wall, "cpu": time.thread_time() - cpu,
                                    "asks": len(self.asks)}) + "\n")

    def queue_asks(self, batch):
        """One entry of the words pass, [(id, what it asks, frame)], queued,
        and each ask held from now until its answer or its deadline
        (WORDS_WAIT for a `words?`, REACH_WAIT for a `reach?`)."""
        self.session_lane.send([frame for _, _, frame in batch])
        now = time.monotonic()
        for ask, held, _ in batch:
            wait = REACH_WAIT if held.get("t") == "reach?" else WORDS_WAIT
            self.asks[ask] = {**held, "deadline": now + wait}
            self.asked[held["key"]] = ask

    def expire_asks(self, now):
        """Each ask past its deadline dropped; its event is asked again. A
        `words?` is counted a failed attempt (said in daemon.log at the
        first); a `reach?` is none: its delivery stays owed, never given up
        (P5 O18 D3, acceptance 5), said once while it goes unanswered."""
        for ask, held in sorted(self.asks.items(), key=lambda kv: kv[1]["deadline"]):
            if held["deadline"] > now:
                break
            del self.asks[ask]
            self.asked.pop(held["key"], None)
            if held.get("t") == "reach?":
                if held["key"] not in self.reach_silent:
                    self.reach_silent.add(held["key"])
                    log("the endpoint gave no answer on the reach of %s in %s within %g s: it stays owed, asked "
                        "again each pass" % (sminos.event_ref(held["event"]), held["project"].name, REACH_WAIT))
                continue
            attempts = sminos.words_unanswered(held["project"], held["member"], held["event"],
                                               "the endpoint gave no verdict within %g s" % WORDS_WAIT)
            if attempts == 1:
                log("the endpoint gave no verdict on %s in %s within %g s: it stays owed, asked again each pass"
                    % (sminos.event_ref(held["event"]), held["project"].name, WORDS_WAIT))
            self.next_upload = 0.0   # an attempt given up has its outcome to send

    def restated_due(self):
        """RL10: whether the restatement this connection's welcome began is
        whole on the lane, so `restated {}` may follow it (O10 M6: at
        `restated` the endpoint withdraws every session held before the
        welcome that the restatement left out, so it must never come early):
        the whole member set queued (members_whole, nothing of it waiting
        for room), every hub project known here opened by a scan — each
        `open` queues its hello, its machine and sessions' presence, its
        pending set when its bridges are read, and every result not yet
        acknowledged — each project's pending set that waited for its
        bridges sent since (Requests.stale), and the host events owed again
        at the open queued (host_owed)."""
        return self.restate_scanned and self.members_whole and not self.members_unsent \
            and not (self.requests.stale & self.opened) and not any(self.host_owed.values())

    def words_now(self, nudged):
        """Whether this tick runs the words pass: one was asked for (a nudge,
        an import, a verdict, a welcome), an ask's deadline passed, or
        WORDS_EVERY went by."""
        now = time.monotonic()
        return self.words_due or nudged or now >= self.next_words \
            or any(held["deadline"] <= now for held in self.asks.values())

    def tick(self):
        """Between frames: new hub projects opened, and what this machine's
        writers appended uploaded — at once when a sender nudged the daemon.
        On RL10, the member set first: every hello, upload and host message
        after it depends on the records the endpoint holds, so none goes
        while the set is not all queued (members_before keeps each upload's
        and host message's sessions current too); and
        the person's words owed here asked about after the upload pass
        (ask_words), behind the member frames the plane's reads changed."""
        if self.generation is None:
            return
        now = time.time()
        nudge = daemon.nudged_at()
        nudged, self.nudge = nudge != self.nudge, nudge
        words = self.words_now(nudged)
        held = True   # until the member set is published (a failure there holds the tick)
        try:
            scan = now >= self.next_scan or nudged
            if scan:
                self.next_scan = now + SCAN_EVERY
                self.look_whole = True
                if nudged:
                    # A sender asked: what it did is read as it is now. A
                    # scan it did not ask for reads within the cache
                    # generation the session plane renews (once a session
                    # came or went, else every MEMBERS_EVERY): forgetting
                    # every cache at each scan re-resolved every seat's
                    # project, launch directory and checkout every 2 s,
                    # most of an idle uplink's work on a machine with a
                    # history (2026-10-28).
                    sminos.forget_caches()
            self.members(time.monotonic())
            # The member set is published in bounded entries: until the
            # rest of it is queued, nothing that depends on it goes.
            held = bool(self.members_unsent)
            if held and scan:
                self.next_scan = 0.0
            self.complete_transitions()   # a policy change whose audience was kept before a restart
            if scan and not held:
                self.sync_policy()
                register_own(self.cred)
                known = hub_projects(self.cred)
                gone = sorted(self.opened - set(known))
                if gone:
                    # The org's directory retired it (a revoked machine's
                    # project): nothing more goes up, and a new stream, which
                    # opens only what is eligible, takes it out of the hub's
                    # fan-out to this machine (there is no frame that closes
                    # one project; a revocation is rare enough for a reconnect).
                    raise EndStream("no longer a hub project of org %s here: %s" % (
                        self.cred["org"], ", ".join(self.logs[pid].project.name for pid in gone)))
                for pid in self.opened:
                    # Each open project as it is registered now: a followed
                    # one whose checkout registered since has its root, which
                    # is what makes it held (machine_presence).
                    self.logs[pid].project = known[pid]
                for pid in sorted(set(known) - self.opened):
                    self.open(self.log_of(pid, known))
                self.machine_presence(time.monotonic())
                self.restate_scanned = True
            every = archive.archive_every()
            if every > 0 and now >= self.next_confirm and not held:
                # The hub reads the archive designation at each hello: asked
                # again, it answers with the designation as it is now. One
                # project per lane entry, as `open` sends them.
                self.next_confirm = now + every
                for pid in sorted(self.opened):
                    self.log_lane.send([self.logs[pid].hello(self.follows.get(pid, False))])
            if (now >= self.next_upload or nudged or words) and not held:
                self.next_upload = now + UPLOAD_EVERY
                # Every own writer looked at once after each scan, a nudge
                # and a words pass; the hot ones alone between (HubLog.hot).
                live = None if self.look_whole or nudged or words else set(self.plane.live)
                self.look_whole = False
                for pid in sorted(self.opened):
                    self.upload(self.logs[pid], live)
                    self.deliveries(self.logs[pid])
                    self.logs[pid].show_notices()   # what the hub withheld, told its sending session (P5 O18 D5)
                    self.host_pass(self.logs[pid])
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
            self.relay_rpcs()
            known = self.members(time.monotonic())
            if self.revoked_due:
                self.mark_revoked(known)
            if words and not held:
                self.words_pass(known)   # behind the upload pass, which a held tick did not run
            if self.restating and self.restated_due():
                self.session_lane.send([{"t": "restated"}])
                self.restating = False
            self.plane_failing = ""
        except EndStream:
            raise
        except (Exception, SystemExit) as e:  # noqa: BLE001 — said once while it keeps failing
            if repr(e) != self.plane_failing:
                self.plane_failing = repr(e)
                log("the session plane failed: %r" % e)


def serve(stream, cred, ended, logs, bridges=None, reqs=None, rpcs=None, warmer=None):
    """Handle one connection's frames until it closes, a write is not
    delivered, or the uplink ends; whether the endpoint welcomed it. A wake
    (the session plane's readers) is a tick after the batch in hand; at most
    one waits. `stream` is RL10's SocketTransport, its welcome first."""
    woken = threading.Event()

    def wake():
        if not woken.is_set():
            woken.set()
            stream.items.put(("wake",))

    link = Link(cred, logs, ended, wake, bridges, reqs, rpcs, warmer, transport=stream)
    try:
        return serve_link(link, stream, ended, woken)
    finally:
        link.close()


def serve_link(link, stream, ended, woken):
    """serve's loop: the connection's frames, the wakes and the lane's
    answers in arrival order — ("sent", thens) runs the continuations of what
    was written, ("closed", NotDelivered) ends the connection. What is queued
    when the main thread looks up is one batch (DRAIN_FRAMES, DRAIN_FOR), its
    imports delivered once, then one tick: a tick can be slow (its reads of
    the fleet, a delivery to a slow session), and one a frame would let a
    burst queue for minutes."""
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
            try:
                taken, until = 0, time.monotonic() + DRAIN_FOR
                while item is not None:
                    if item[0] == "closed":
                        if isinstance(item[1], EndStream):
                            raise item[1]   # a lane's write not delivered
                        log("the stream closed: %s" % item[1])
                        return welcomed
                    if item[0] == "sent":
                        link.ran(item[1])
                    elif item[0] == "wake":
                        woken.clear()
                    else:
                        try:
                            frame = codes.loads(item[2])
                        except ValueError as e:
                            log("a frame that is not JSON (%s): ignored" % e)
                            frame = None
                        if isinstance(frame, dict) and frame.get("t") == "welcome":
                            welcomed = True
                        if frame is not None:
                            link.received = item[3] if len(item) > 3 else None
                            link.dispatch(frame, stream)
                    taken += 1
                    if taken >= DRAIN_FRAMES or time.monotonic() >= until or ended():
                        break
                    try:
                        item = stream.items.get_nowait()
                    except queue.Empty:
                        item = None
            finally:
                # What the batch imported reaches its members whatever ended
                # it: a write that failed, the connection's close, the uplink's end.
                link.deliver_imports()
            link.tick()
        except NotDelivered as e:
            log("a write was not delivered (%s): reconnecting, to redo the handshake" % e)
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


def supervisor():
    """The pid of the `daemon run` that spawned this uplink, as it said at
    spawn; for an uplink started by hand, this process's parent now."""
    said_ = os.environ.pop(daemon.UPLINK_PARENT_ENV, "")
    return int(said_) if said_.isdigit() else os.getppid()


class Kept:
    """What the uplink keeps across its connections: the projects' log
    planes, the bridges' followers, the plane's warmer, the requests and the
    RPCs, for the identity `cred` names. `adopt` takes another (RL10: a
    welcome that renamed the machine): the log planes, which hold no thread
    and no file of their own beyond each project's, start over under the new
    name; the requests and the RPCs are renamed in place, never replaced,
    since each is the one owner of its file under daemon/ (the RPC ledger,
    what is owed) and of the threads that write it — an RPC's worker may be
    inside its checks across the welcome, and a second owner would run its
    op again."""

    def __init__(self, cred):
        self.bridges, self.warmer = plane.Bridges(), plane.Warmer()
        self.cred = None
        self.reqs = requests.Requests(cred["machine"])
        self.rpcs = rpc.Rpcs(cred["machine"])
        self.adopt(cred)

    def adopt(self, cred):
        if self.cred is not None and (self.cred["machine"], self.cred["org"]) == (cred["machine"], cred["org"]):
            self.cred = cred
            return
        self.cred, self.logs = cred, {}
        self.reqs.rename(cred["machine"])
        self.rpcs.rename(cred["machine"])

    def close(self):
        self.reqs.close()


def rl10_connection(info, kept, ended):
    """One connection to the endpoint (RL10): dialled, `hello` and its
    welcome, the identity kept (sminos_rl10.welcomed: the cutover), then its
    frames served until it closes; whether it was welcomed. `kept` is
    adopted for the identity the welcome gave."""
    try:
        conn = rl10.Connection.dial(info["socket"])
    except OSError as e:
        log("the endpoint does not answer at %s (%s)" % (info["socket"], " ".join(str(e).split()) or type(e).__name__))
        return False
    try:
        welcome = conn.handshake(rl10.hello_frame(info["token"], hublog.desk()["sminos"], policy.wire_policy()))
        identity = rl10.welcomed(welcome)
    except (rl10.Refused, ValueError) as e:
        log("the endpoint did not welcome this machine: %s" % e)
        conn.close()
        return False
    except OSError as e:
        log("the endpoint's welcome could not be kept (%s): the connection is closed" % e)
        conn.close()
        return False
    cred = rl10.credential(identity)
    if kept is None:
        kept = Kept(cred)
    else:
        kept.adopt(cred)
    transport = SocketTransport(conn, welcome, ended)
    transport.start()
    try:
        serve(transport, cred, ended, kept.logs, kept.bridges, kept.reqs, kept.rpcs, kept.warmer)
    finally:
        transport.close()
    return kept


def run_rl10(ended, halt):
    """The endpoint's connections (RL10), one at a time, reconnecting with
    backoff from 1 s to BACKOFF_MAX (reset by a welcome), while rl10.json
    names an endpoint; the uplink ends once it names none (the supervisor
    says what follows: waiting for it). The daemon runs it on a cut-over
    machine only; its welcome would cut one over, as a probe's does."""
    log("started (pid %d) for the endpoint (RL10, local-only)" % os.getpid())
    plane.sweep_builds()
    backoff, kept = 1, None
    while not ended():
        info, why = rl10.check()   # the supervisor says what is wrong with it
        if info is None:
            log("no endpoint (%s): nothing to connect" % (why or "none at %s" % rl10.path()))
            break
        got = rl10_connection(info, kept, ended)
        if got:
            kept, backoff = got, 1
        else:
            backoff = min(backoff * 2, BACKOFF_MAX)
        deadline = time.time() + backoff
        while not ended() and time.time() < deadline:
            halt.wait(POLL)
    return kept


def cmd_probe(_a):
    """`daemon probe`, the supervisor's look at an endpoint before the
    cutover, while no uplink runs: the endpoint
    rl10.json names dialled, `hello`, and its welcome; a whole welcome cuts
    the machine over (sminos_rl10.welcomed) and exits 0, anything else exits
    1, and nothing else is done on the connection either way. The outcome is
    one line on stdout, which the supervisor says in daemon.log."""
    if rl10.cut_over():
        print("this machine is cut over already")
        return
    info, why = rl10.check()
    if info is None:
        print("no endpoint: %s" % (why or "none at %s" % rl10.path()))
        sys.exit(1)
    try:
        conn = rl10.Connection.dial(info["socket"])
    except OSError as e:
        print("it does not answer at %s (%s)" % (info["socket"], " ".join(str(e).split()) or type(e).__name__))
        sys.exit(1)
    try:
        welcome = conn.handshake(rl10.hello_frame(info["token"], hublog.desk()["sminos"], policy.wire_policy()))
        identity = rl10.welcomed(welcome)
    except rl10.NotEnrolled as e:
        print("present but not enrolled (%s): this machine is not cut over" % e)
        sys.exit(1)
    except (rl10.Refused, ValueError, OSError) as e:
        print("it did not welcome this machine (%s): this machine is not cut over" % e)
        sys.exit(1)
    finally:
        conn.close()
    print("welcomed as %s of org %s: this machine is cut over" % (identity["name"], identity["org"]))


def cmd_uplink(_a):
    """The uplink's process: one connection at a time, reconnecting with
    backoff (from 1 s, doubling to a minute, reset by a welcome), until
    SIGTERM or until its parent is not the `daemon run` that spawned it — an
    uplink outlives no `daemon run`, even one gone before this process could
    look. It speaks RL10 to the endpoint of a machine cut over to it
    (sminos_rl10), and runs on nothing before: a machine not cut over has
    nothing to connect to (its endpoint is the supervisor's to probe,
    cmd_probe, and only a whole welcome cuts it over); a hub.json changes
    nothing."""
    parent = supervisor()
    if os.getppid() != parent:
        log("not started (pid %d): its daemon (pid %d) is gone" % (os.getpid(), parent))
        return
    lock = take_lock()   # held for the process's life, released as it ends (below)
    if not rl10.cut_over():
        log("this machine is not cut over to an endpoint (no %s): nothing to connect" % rl10.identity_path())
        return
    if rl10.check()[0] is None:
        log("this machine is cut over to its endpoint, which is not running (no endpoint at %s): nothing to "
            "connect" % rl10.path())
        return
    halt = threading.Event()
    # SIGTERM from its supervisor; SIGINT from a terminal's ^C, which reaches a
    # foreground `daemon run`'s whole process group.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: halt.set())

    def ended():
        return halt.is_set() or os.getppid() != parent

    kept = run_rl10(ended, halt)
    if kept is not None:
        kept.close()
    at = time.monotonic()
    saved, held = plane.TRANSCRIPTS.save_all()
    if held:
        log("the builds held: %d of %d saved or already current in %.2f s" % (saved, held, time.monotonic() - at))
    log("stopped (pid %d)%s" % (os.getpid(), "" if halt.is_set() or not ended() else ": its daemon is gone"))
    lock.close()
