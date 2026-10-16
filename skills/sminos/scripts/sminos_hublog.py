#!/usr/bin/env python3
"""sminos_hublog — one hub project's log plane on this machine (DC4 of the
desk: DX2's log handshake, DX1's codes).

The uplink (sminos_uplink.py) holds the stream and posts frames; what it says
about one project is drawn up here, and what the hub sends about one project
is taken in here. Everything runs on the uplink's main thread.

Up. `hello` carries this machine's vector — `{writer: max seq}` for every
writer its log of the project holds — and the hub answers `have` with its
own. The machine then uploads the suffix of its own writers (`<machine>/…`;
`legacy/…` too when the hub names it the project's archive machine) beyond
the hub's vector, and from then on whatever its writers append. An event is
stored here without a code; the uploader seals it as it goes, under a nonce
derived from the event itself with the org key (`nonce_for`), so the same
event always uploads byte for byte the same: inserts are idempotent on
(writer, seq) only when a second upload is the same payload, and a random
nonce would make every re-upload after a lost answer a conflict.

Down. An `events` frame is imported event by event, all or nothing each: an
event that is no log event sminos can read is refused `bad-shape`; one whose
code fails — a hub/ event whose position fails its shape and an event moved
from another project's feed included — `bad-code`; one carrying a nonce this
project's log already holds at another position `seen-nonce`. A refused event
never enters the log; it is reported up as DX2's `rejected`, named only by
what it carried, and its position is spent — a tombstone: nothing is ever
appended there, the writer's later events are not held back behind it (every
reader of a writer's file takes seqs by order, not by count, so the hole is
read past), and the vector no longer asks the hub for it, so it is reported
once. A position of this machine's own writers is spent under the writer
file's lock, only while no event of this machine's holds it, and its
appenders allocate past it (sminos._append): what this machine writes next
never lands where nothing can upload or import it. What passes is appended
verbatim, with its code, through the log's own locks: present already (the
same content at its (writer, seq)) it is skipped; a different content there
is refused; past a gap it waits for the hub to send what is missing. Then whatever was appended is delivered at
once and the tick loop nudged.

Its state between streams lives in the project's home, `uplink.json`: the
spent positions, the rejections not yet reported (a report whose POST
failed is sent again after the next `hello`), and whether the hub's latest
`have` named this machine the project's archive machine, with when it said
so (`archive`, `archive_at`: what sminos_archive runs on).
"""

import glob
import hashlib
import hmac
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_policy as policy  # noqa: E402

NONCE_DOMAIN = "smns-hub-nonce-v1"
STATE_FILE = sminos.UPLINK_STATE
LEGACY = "legacy/"
# Event JSON per `events` frame up, as the hub batches its own; a larger
# event travels alone (and as parts, past a frame's bound).
BATCH_BYTES = 256 * 1024
MESSAGE_MAX = 2000  # a rejection's message, as the hub admits it
# The reason an event that verifies is refused for its position (another event
# holds it here, or it is spent): DX2's `conflict`, which DC3's module admits
# only from its M3 — a reason it does not know yet would be refused, so until
# then such an event is reported as `bad-code`, its position read as false.
CONFLICT_REASON = "bad-code"


def log(line):
    sminos.daemon_log("uplink: " + line)


def nonce_for(key, project, event):
    """The nonce an event of this machine is sealed under (DX1's derived
    form): the first 16 bytes of HMAC-SHA256 with the org key over
    `smns-hub-nonce-v1` LF <project id> LF <JCS of the event without mac>.
    Unique to the event — its writer and seq are in it — unpredictable
    without the key, and the same at every upload."""
    draft = {k: v for k, v in event.items() if k != "mac"}
    data = (NONCE_DOMAIN + "\n" + project + "\n" + codes.canonical(draft)).encode("utf-8")
    return codes.b64url(hmac.new(key, data, hashlib.sha256).digest()[:codes.NONCE_BYTES])


def seal(key, project, event):
    """An event of this machine as it uploads: its code added (DX1); one that
    arrived with a code keeps it."""
    if isinstance(event.get("mac"), dict):
        return event
    draft = {k: v for k, v in event.items() if k != "mac"}
    return codes.seal(key, "log", project, draft, nonce_for(key, project, draft))


def rejected(project, e, reason, message):
    """DX2's `rejected` for an event refused on import, naming it only by what
    it carried: `event` its writer and seq as they came when the writer was a
    string and the seq a number (else null), `nonce` its mac.nonce when that
    was a string."""
    writer, seq = (e.get("writer"), e.get("seq")) if isinstance(e, dict) else (None, None)
    numeric = isinstance(seq, (int, float)) and not isinstance(seq, bool)
    mac = e.get("mac") if isinstance(e, dict) else None
    frame = {"t": "rejected", "project": project,
             "event": {"writer": writer, "seq": seq} if isinstance(writer, str) and numeric else None,
             "reason": reason, "message": message[:MESSAGE_MAX]}
    if isinstance(mac, dict) and isinstance(mac.get("nonce"), str):
        frame["nonce"] = mac["nonce"]
    return frame


def position(e):
    if not isinstance(e, dict):
        return "an entry that is not an event"
    nonce = e.get("mac", {}).get("nonce") if isinstance(e.get("mac"), dict) else None
    return "%r:%r%s" % (e.get("writer"), e.get("seq"), " (nonce %r)" % nonce if nonce is not None else "")


def refusal(key, project, e):
    """(DX2's reason, what was wrong) for an event from the hub that may not
    enter this project's log; (None, "") when its shape and code pass."""
    if not isinstance(e, dict):
        return "bad-shape", "not a log event"
    writer = e.get("writer")
    if not (isinstance(writer, str) and "/" in writer.strip("/") and writer.isprintable() and " " not in writer):
        return "bad-shape", "its writer is not one a log holds"
    if not (codes.is_log_seq(e.get("seq")) and isinstance(e.get("ts"), str) and isinstance(e.get("kind"), str)):
        return "bad-shape", "it is not a log event (seq, ts, kind)"
    why = {
        "encoding": "its code or nonce is not the canonical base64url of 32 and 16 bytes",
        "position": "a hub/ event whose writer, seq, or ts fails its shape",
        "code": "its code does not verify for project %s" % project.id,
    }.get(codes.failure(key, "log", project.id, e))
    return ("bad-code", why) if why else (None, "")


def same_event(held, e):
    """Whether the event at a (writer, seq) is the one arriving: their
    canonical forms agree on everything both carry — the code too when the
    copy here has one; an event this machine wrote is stored without one, and
    the code it uploaded under is derived from the rest."""
    try:
        if isinstance(held.get("mac"), dict):
            return codes.canonical(held) == codes.canonical(e)
        return codes.canonical(held) == codes.canonical({k: v for k, v in e.items() if k != "mac"})
    except codes.NotCanonical:
        return False


def frontier(last, spent):
    """A writer's last seq here, carried past the spent positions that follow it."""
    while last + 1 in spent:
        last += 1
    return last


def append_verbatim(project, e, spent=()):
    """Append an imported event to its writer's file as it came, under the
    locks every appender takes (`.sync.lock` shared, the file's own lock):
    "appended"; "present" when that (writer, seq) holds the same content;
    "conflict" when it holds another; "spent" when an event was refused there
    (a tombstone: nothing is ever appended at it, whatever arrives); "gap"
    when seq is not one past the last (carried past the writer's `spent`
    positions)."""
    if e["seq"] in spent:
        return "spent"
    if e["kind"] in sminos.LIFECYCLE:
        sminos._VIEWS.pop(project.id, None)
    path = sminos.writer_path(project, e["writer"])
    with sminos.flocked(os.path.join(os.path.dirname(path), ".sync.lock"), exclusive=False), \
            sminos.flocked(path + ".lock"):
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "r+b") as f:
            last = sminos._last_seq(f)
            if e["seq"] > frontier(last, spent) + 1:
                return "gap"
            if e["seq"] <= last:
                f.seek(0)
                for line in f.read().decode("utf-8", "replace").split("\n"):
                    x = sminos.parse_event(line) if line.strip() else None
                    if x and x["seq"] == e["seq"]:
                        return "present" if same_event(x, e) else "conflict"
                return "conflict"
            end = f.seek(0, os.SEEK_END)
            if end:
                f.seek(end - 1)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write((json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8"))
    return "appended"


def read_events(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [e for e in map(sminos.parse_event, f) if e]
    except OSError:
        return []


def writer_and_last(path):
    """A writer file's writer (its first event's) and last seq (its last
    well-formed line's, as an appender reads it); ("", 0) when it holds none."""
    try:
        with open(path, "rb") as f:
            for line in f:
                e = sminos.parse_event(line.decode("utf-8", "replace")) if line.strip() else None
                if e:
                    return e["writer"], sminos._last_seq(f)
    except OSError:
        pass
    return "", 0


def machine_policy():
    """The machine's policy as DX4's `machine` presence carries it (DX6's,
    which DC7 owns: sminos_policy, read at every use)."""
    return policy.machine_policy()


class HubLog:
    """One hub project's log plane: what this machine says of it up the
    stream, and how it takes what the hub sends of it."""

    def __init__(self, project, cred):
        self.project = project
        self.key = cred["key"]
        self.machine = cred["machine"]
        self.files = {}      # path → (size, mtime_ns, writer, last): the vector's reads, kept while a file holds
        self.nonces = None   # nonce → (writer, seq) of every coded event the log holds, read on first import
        self.reset()

    def reset(self):
        """A new stream: nothing is known of the hub's vector until `have`."""
        self.have = None     # the hub's vector, from `have`
        self.sent = {}       # own writer → the last seq the hub holds or took in a POST answered 200
        self.stuck = set()   # own writers the hub refused: not uploaded again on this stream
        self.refused = {}    # own writer → the lowest seq the hub refused on this stream (0: the writer itself)
        self.archive = False

    # ---------------------------------------------------- what is held here

    @property
    def log_dir(self):
        return os.path.join(self.project.home, "log")

    def state(self):
        try:
            with open(os.path.join(self.project.home, STATE_FILE)) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, d):
        """Written whole, by rename, and ASCII only: a writer or a nonce the
        hub sent is kept as it arrived, and a lone surrogate in it (a lying
        hub's JSON can carry one) round-trips only as an escape."""
        path = sminos.project_path(self.project, STATE_FILE)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="ascii") as f:
            json.dump(d, f, ensure_ascii=True)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def spent(self):
        """{writer: {seq}}: the positions of events refused here."""
        raw = self.state().get("spent")
        return {w: {s for s in ss if type(s) is int} for w, ss in raw.items() if isinstance(ss, list)} \
            if isinstance(raw, dict) else {}

    def writers(self):
        """{writer: (last seq, path)} of the writer files the log holds (each
        read from its end, again only once it changed)."""
        out, seen = {}, set()
        for path in glob.glob(os.path.join(glob.escape(self.log_dir), "*.jsonl")):
            seen.add(path)
            try:
                st = os.stat(path)
            except OSError:
                continue
            held = self.files.get(path)
            if not held or held[:2] != (st.st_size, st.st_mtime_ns):
                held = self.files[path] = (st.st_size, st.st_mtime_ns, *writer_and_last(path))
            if held[2]:
                out[held[2]] = (held[3], path)
        for path in set(self.files) - seen:
            del self.files[path]
        return out

    def vector(self):
        """{writer: max seq} as `hello` carries it: each writer's last seq
        here, carried past its spent positions."""
        spent = self.spent()
        out = {w: frontier(last, spent.get(w, ())) for w, (last, _) in self.writers().items()}
        for w, ss in spent.items():
            if w not in out:
                at = frontier(0, ss)
                if at:
                    out[w] = at
        return out

    # ---------------------------------------------------- up

    def hello(self):
        return {"t": "hello", "project": self.project.id, "name": self.project.name, "have": self.vector()}

    def presence(self):
        """DX4's `machine` message for this project: online (the hub's word,
        from the lease), the policy, and the project's known checkouts here."""
        try:
            checkouts = policy.known_checkouts(self.project)
        except (OSError, SystemExit) as e:
            log("the checkouts of %s could not be read: %r" % (self.project.name, e))
            checkouts = [{"path": self.project.root, "branch": policy.git_branch(self.project.root)}] \
                if self.project.root and os.path.isdir(self.project.root) else []
        return {"t": "session", "message": {
            "project": self.project.id, "machine": self.machine, "session": None, "kind": "machine",
            "sub": None, "n": None,
            "body": {"online": True, "policy": machine_policy(), "checkouts": checkouts}}}

    def unreported(self):
        raw = self.state().get("unreported")
        return [f for f in raw if isinstance(f, dict)] if isinstance(raw, list) else []

    def reported(self, frames):
        """The rejections in `frames` reached the hub (a POST answered 200)."""
        if not frames:
            return
        d = self.state()
        left = [f for f in self.unreported() if f not in frames]
        d["unreported"] = left
        self.save(d)

    def rejoin_former(self):
        """Each live local member whose latest `joined` this machine wrote
        under a former name joins again under its name now, once: the hub
        takes only `<machine>/…` writers, so otherwise no other machine and
        no browser would see it. Its earlier history stays here — a rename or
        a state published under the former name included — so the new writer
        starts from what the member is now: its alias and name source in the
        `joined`, and its state after it (publish_renames and publish_state
        compare against those former events and would find nothing to say)."""
        if not sminos.machine_identity()[1]:
            return 0
        view = sminos.view_of(self.project, titles=False)
        n = 0
        for m in view.members:
            if not (m.local and m.session):
                continue
            j = (view.info.get(m.session) or {}).get("joined") or {}
            if not j or j.get("writer") == sminos.writer_id(m.session):
                continue

            def guard(evs, mine=sminos.writer_id(m.session)):
                last = next((e for e in reversed(evs) if e["kind"] in sminos.MEMBERSHIP), None)
                return last is not None and last["kind"] == "joined" and last["writer"] != mine

            got = sminos.lifecycle(self.project, m.session, "joined", guard=guard, required=False,
                                   **sminos.joined_fields(m.alias, m.name_source, *(
                                       j.get(k, "") for k in ("cwd", "worktree", "role", "seat", "by"))))
            if got:
                n += 1
                if m.state:
                    sminos.lifecycle(self.project, m.session, "state", required=False, state=m.state,
                                     machine=sminos.host_name())
                log("%s in %s joined again as %s (it had joined as %s)"
                    % (m.alias, self.project.name, self.machine, j.get("machine")))
        return n

    def on_have(self, frame):
        have = frame.get("have")
        have = {w: s for w, s in have.items() if type(s) is int} if isinstance(have, dict) else {}
        opening, self.have = self.have is None, have
        self.archive = frame.get("archive") is True
        if opening:
            # The handshake: upload from the hub's vector, every writer free.
            self.sent = {w: s for w, s in have.items() if self.own(w)}
            self.stuck, self.refused = set(), {}
        else:
            # A `have` answering a `hello` repeated on an open stream (the
            # uplink's periodic one, which refreshes the designation): the
            # upload goes on as it was. `sent` only moves forward — an older
            # vector still queued must not bring back what the hub has taken
            # since — and a writer the hub refused stays stopped until a new
            # stream, or a `resend` from before what it refused, frees it.
            for w, s in have.items():
                if self.own(w) and s > self.sent.get(w, 0):
                    self.sent[w] = s
        # The designation as the hub said it now: the tick loop's archive
        # duty (sminos_archive) runs on it.
        d = self.state()
        if d.get("archive") != self.archive:
            log("the hub says this machine %s the archive of %s" % ("writes" if self.archive else "does not write",
                                                                   self.project.name))
        d.update(archive=self.archive, archive_at=time.time())
        self.save(d)

    def on_resend(self, frame):
        """The hub lacks a writer's events from `from` on. Every batch is
        posted before the replies are read, so a resend may be queued behind
        a refusal of the same writer — drawn by a later batch, whose events
        follow the refused one: a resend at or past the refused position would
        send that event again, to be refused again, forever. The refusal wins
        on this stream; a resend from before it is followed."""
        writer, start = frame.get("writer"), frame.get("from")
        if isinstance(writer, str) and self.own(writer) and type(start) is int and start >= 1:
            if writer in self.refused and start >= self.refused[writer]:
                log("the hub asks %s of %s again from %d, where it refused it or past that (at %d): not followed on "
                    "this stream" % (writer, self.project.name, start, self.refused[writer]))
                return
            self.sent[writer] = start - 1
            self.stuck.discard(writer)
            log("the hub asks %s of %s again from %d" % (writer, self.project.name, start))

    def on_refused(self, frame):
        """The hub refused what this machine sent; said in daemon.log. A
        writer refused stops uploading on this stream (sending it again would
        be refused again); `not-open` asks for `hello` first."""
        r = frame.get("refusal") if isinstance(frame.get("refusal"), dict) else {}
        reason, writer = r.get("reason"), r.get("writer")
        log("the hub refused in %s: %s%s%s" % (
            self.project.name, reason, " %s:%s" % (writer, r.get("seq")) if writer else "",
            " — %s" % " ".join(str(r.get("message") or "").split())[:300] if r.get("message") else ""))
        if isinstance(writer, str) and self.own(writer) and reason in ("conflict", "writer-not-yours", "bad-shape",
                                                                        "too-large"):
            self.stuck.add(writer)
            seq = r.get("seq")
            at = seq if type(seq) is int and seq >= 1 else 0
            self.refused[writer] = min(at, self.refused.get(writer, at))
        if reason == "not-open":
            self.have = None

    def own(self, writer):
        return writer.startswith(self.machine + "/") or (self.archive and writer.startswith(LEGACY))

    def uploads(self):
        """`events` frames of this machine's writers the hub lacks, each with
        the (writer, seq) it brings the hub to: [(frame, {writer: seq})]."""
        if self.have is None:
            return []
        out, batch, reach, size = [], [], {}, 0

        def flush():
            nonlocal batch, reach, size
            if batch:
                out.append(({"t": "events", "project": self.project.id, "events": batch}, reach))
            batch, reach, size = [], {}, 0

        for writer, (last, path) in sorted(self.writers().items()):
            if not self.own(writer) or writer in self.stuck or last <= self.sent.get(writer, 0):
                continue
            for e in sorted((e for e in read_events(path) if e["seq"] > self.sent.get(writer, 0)),
                            key=lambda e: e["seq"]):
                try:
                    sealed = seal(self.key, self.project.id, e)
                    n = len(codes.canonical(sealed).encode("utf-8"))
                except codes.NotCanonical as err:
                    log("%s:%d in %s has no canonical form (%s): it and the rest of its writer stay here"
                        % (writer, e["seq"], self.project.name, err))
                    self.stuck.add(writer)
                    break
                if batch and size + n > BATCH_BYTES:
                    flush()
                batch.append(sealed)
                reach[writer] = e["seq"]
                size += n
        flush()
        return out

    def took(self, reach):
        """A POST of uploads was answered 200."""
        for writer, seq in reach.items():
            self.sent[writer] = max(self.sent.get(writer, 0), seq)

    # ---------------------------------------------------- down

    def nonce_index(self):
        if self.nonces is None:
            self.nonces = {}
            for path in glob.glob(os.path.join(glob.escape(self.log_dir), "*.jsonl")):
                for e in read_events(path):
                    mac = e.get("mac")
                    if isinstance(mac, dict) and isinstance(mac.get("nonce"), str):
                        self.nonces.setdefault(mac["nonce"], (e["writer"], e["seq"]))
        return self.nonces

    def take(self, events):
        """An `events` frame from the hub: each event verified and appended,
        or refused. Returns (how many were appended, the `rejected` frames)."""
        if not isinstance(events, list):
            log("an events frame for %s without a list of events: ignored" % self.project.name)
            return 0, []
        appended, out, spent = 0, [], self.spent()
        newly = {}
        for raw in events:
            e = raw
            reason, why = refusal(self.key, self.project, e)
            if reason is None:
                # JSON's 3.0 is the number 3; the log's readers take an int.
                # The code's canonical form is the same for both.
                e = {**e, "seq": int(e["seq"])}
                at = self.nonce_index().get(e["mac"]["nonce"])
                if at is not None and at != (e["writer"], e["seq"]):
                    reason, why = "seen-nonce", "its nonce is held here by %s:%d" % at
            if reason is None:
                outcome = append_verbatim(self.project, e, spent.get(e["writer"], set()) | newly.get(e["writer"], set()))
                if outcome == "appended":
                    appended += 1
                    self.nonces.setdefault(e["mac"]["nonce"], (e["writer"], e["seq"]))
                elif outcome == "gap":
                    log("held back %s in %s: its seq is not one past the writer's last (the hub sends what is "
                        "missing at the next hello)" % (position(e), self.project.name))
                elif outcome == "conflict":
                    reason, why = CONFLICT_REASON, "%s:%d holds another event here" % (e["writer"], e["seq"])
                elif outcome == "spent":
                    reason, why = CONFLICT_REASON, "%s:%d was refused here before: nothing is appended there" % (
                        e["writer"], e["seq"])
            if reason is None:
                continue
            log("refused %s in %s: %s" % (position(raw), self.project.name, why))
            out.append(rejected(self.project.id, raw, reason, why))
            if isinstance(raw, dict) and isinstance(raw.get("writer"), str) and codes.is_log_seq(raw.get("seq")):
                if reason != "bad-shape" and self.allocated_here(raw["writer"]):
                    if self.spend_own(raw["writer"], int(raw["seq"])):
                        newly.setdefault(raw["writer"], set()).add(int(raw["seq"]))
                else:
                    newly.setdefault(raw["writer"], set()).add(int(raw["seq"]))
        if out:
            d = self.state()
            held = d.get("spent") if isinstance(d.get("spent"), dict) else {}
            for w, ss in newly.items():
                held[w] = sorted(set(held.get(w) or []) | ss)
            d["spent"] = held
            d["unreported"] = self.unreported() + out
            self.save(d)
        return appended, out

    def allocated_here(self, writer):
        """Whether this machine's appenders allocate `writer`: its operator
        writer or one of its sessions' (`sminos.writer_id`), exactly
        `<machine>/human` or `<machine>/<session uuid>`. Any other name, even
        one under this machine's prefix, is no file the allocator opens."""
        prefix = self.machine + "/"
        if not writer.startswith(prefix):
            return False
        rest = writer[len(prefix):]
        return rest == "human" or bool(sminos.UUID_RE.match(rest))

    def spend_own(self, writer, seq):
        """A refused position of one of this machine's own writers
        (`allocated_here`), which its appenders allocate here (sminos._append skips spent positions): spent
        under the writer file's lock, as the allocator reads it, and only while
        no event of this machine's holds it — a position its own event took
        first is that event's. Whether it was spent."""
        path = sminos.writer_path(self.project, writer)
        with sminos.flocked(os.path.join(os.path.dirname(path), ".sync.lock"), exclusive=False), \
                sminos.flocked(path + ".lock"):
            try:
                with open(path, "rb") as f:
                    last = sminos._last_seq(f)
            except FileNotFoundError:
                last = 0
            if seq <= last:
                return False
            d = self.state()
            held = d.get("spent") if isinstance(d.get("spent"), dict) else {}
            held[writer] = sorted(set(held.get(writer) or []) | {seq})
            d["spent"] = held
            self.save(d)
        return True

    def deliver(self):
        """What an import made owed to this machine's members, delivered now."""
        sminos.forget_caches()
        total, reached = daemon.deliver_owed(self.project, sminos.view_of(self.project, titles=False))
        if total:
            log("delivered %d in %s to %s" % (total, self.project.name, ", ".join(reached)))
