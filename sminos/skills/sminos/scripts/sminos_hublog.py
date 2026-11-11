#!/usr/bin/env python3
"""sminos_hublog — one hub project's log plane on this machine (DC4 of the
desk: the log handshake, carried over RL10 to the machine's endpoint).

The uplink (sminos_uplink.py) holds the endpoint's connection; what it says
about one project is drawn up here, and what the endpoint sends about one
project is taken in here. Everything runs on the uplink's main thread.

Up. `hello` carries this machine's vector — `{writer: max seq}` for every
writer its log of the project holds — and the upstream answers `have` with
its own. The machine then uploads the suffix of its own writers
(`<machine>/…`; `legacy/…` too when the hub names it the project's archive
machine) beyond that vector, and from then on whatever its writers append,
each event as stored (`ts`, no `mac`, no `created`: the endpoint derives the
`created` it signs from `ts`), so a re-upload is byte for byte the same.

Down. An `events` frame is imported event by event, all or nothing each.
Each comes wrapped `{event, signer, owners?}`, the endpoint having signed
and verified what passes it (O10 M6): a wrapper or an event that is no log
event sminos can read is refused `bad-shape`, and so is an `event` carrying
a `verified` key of its own (the verdict is the endpoint's to say). A
refused event never enters the log; it is reported up as `rejected`,
named only by what it carried, and its position is spent — a tombstone:
nothing is ever appended there, the writer's later events are not held back
behind it (every reader of a writer's file takes seqs by order, not by
count, so the hole is read past), and the vector no longer asks for it, so
it is reported once. A position of this machine's own writers is spent
under the writer file's lock, only while no event of this machine's holds
it, and its appenders allocate past it (sminos._append): what this machine
writes next never lands where nothing can upload or import it. What passes
is appended through the log's own locks with one key added, `verified:
{signer, owners}`, `owners` only when the endpoint sent them: present
already (the same content at its (writer, seq), `same_uncoded`) it is
skipped; a different content there, or a position spent before, is refused
`conflict`; past a gap it waits for the upstream to send what is missing.
The endpoint returns an own event only as the echo of what it signed at
that position, `created`, `sig` and `attest` added, which reads `present`.
An event the endpoint refused for good never comes down: its position
does, as `spent {project, writer, seq, reason}`, recorded as a position
refused here (`spend`), each said once in daemon.log. Then whatever was
appended is delivered — by the uplink, once per batch of the frames already
queued with it (`deliver`) — and the tick loop nudged.

Message reach (P5 O18 D5, D6). The endpoint only refuses: a `not-reachable`
refusal leaves a tombstone `{writer, seq, withheld: true}` at the position
and the writer goes on (it comes down as `spent withheld`, a spent position
here, never reported). An own position it withheld while this machine's
event holds it — the refusal, or its tombstone seen again on resync (`spent
withheld`, a `have`'s withheld list) — is recorded
withheld (`withheld`, for good; withhold_own): the event stays in its
writer file as what its session tried to send, the position counts as
uploaded, and the sending session is shown that the message was not
delivered (`notices`, until it is live, for NOTICE_KEPT); a session's own
`joined` or `state` is owed a restatement the daemon's next tick writes
(sminos_daemon.owe_restatement), once. A
`state-unavailable` refusal stops nothing (the endpoint rewinds); an
`audience` one — the stream the event went under is not its
session's now — stops the writer past the stream (`dead`), until an event
appended to it says the CLI chose it again: then each refused position goes
up as a content-free `void {ts, writer, seq, kind: void, of, audience?}`
(`voided`, for good; the local file keeps the body) and the rest as stored.

Its state between streams lives in the project's home, `uplink.json`: the
spent positions, the rejections not yet reported (a report whose write
failed is sent again after the next `hello`), the dead writers, the
voided and the withheld positions, the notices not yet shown, whether the
endpoint's latest `have` named this machine the
project's archive machine, with when it said so, and what that same `have`
admitted of this machine's own writers — its vector and its withheld
positions (`archive`, `archive_at`, `archive_have`: what sminos_archive
runs on, admitted_have). Beside it,
`uplink-taken.json` (TAKEN_FILE) holds what `sminos daemon owed` reads:
how far each of this machine's writers no longer has to be sent (`taken`),
never more than the uplink's own resume state — each opening `have` sets it
to what the upstream holds, down as well as up; each upload once written
and each later `have` raises it;
a writer the upstream refuses or asks again for (`resend`) is lowered and
bounded on the stream against answers and vectors that predate it (`bound`)
— and the positions where the upstream holds another event (`conflicts`,
from a `conflict` refusal: no handshake resolves one, so it is kept until
the upstream's echo of this machine's own event there reads `present`).
Its writes are best effort, never stopping the frame in hand; one that would
have lowered it removes the file instead (`keep`).
"""

import fnmatch
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sminos  # noqa: E402
import sminos_audience  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_rpc as rpc  # noqa: E402

STATE_FILE = sminos.UPLINK_STATE
# What the uplink no longer has to send of this machine's writers, beside the
# state file: {"taken": {writer: seq}, "conflicts": {writer: seq}} (`taken`,
# what `sminos daemon owed` reads).
TAKEN_FILE = "uplink-taken.json"
LEGACY = "legacy/"
# Event JSON per `events` frame up, as the hub batches its own; a larger
# event travels alone (and as parts, past a frame's bound).
BATCH_BYTES = 256 * 1024
MESSAGE_MAX = 2000  # a rejection's message, as the hub admits it
# The upload pass's hot looks (HubLog.writers): an own writer file changed, or
# whose session ran here, within HOT_FOR is looked at on every pass; a listing
# of the log directory is kept once the directory held still RACY_NS before it.
HOT_FOR = 600.0
RACY_NS = 1_000_000_000
RAN_KEEP = 256   # sessions past HOT_FOR the hot look's memory may hold before it is pruned
# The reason an event that verifies is refused for its position (another event
# holds it here, or it is spent).
CONFLICT_REASON = "conflict"
# What the endpoint adds to an event this machine wrote when it returns it
# (RL10): the `created` it derived from `ts` and signed, its signature, the
# owner attestation, the audience and policyRev it signs into every event
# (P5 O18; sminos never stores either itself); and `mac`, the old desk code
# an endpoint that still dual-codes adds.
ENDPOINT_ADDS = ("created", "mac", "sig", "attest", "audience", "policyRev")
# How long a notice of a message the hub withheld waits for its sending
# session to be live, from the message's own ts; past it the notice is
# dropped, said in daemon.log (show_notices).
NOTICE_KEPT = 86400.0


def log(line):
    sminos.daemon_log("uplink: " + line)


def glob_names(names, prefix):
    """The names of a directory listing that glob's `<prefix>*.jsonl` matches
    (the prefix literal), by glob's rule for hidden names: one is matched
    only by a hidden pattern."""
    pattern = glob.escape(prefix) + "*.jsonl"
    if not pattern.startswith("."):
        names = [n for n in names if not n.startswith(".")]
    return fnmatch.filter(names, pattern)


def rejected(project, e, reason, message):
    """`rejected` for an event refused on import, naming it only by what
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


def refusal(project, e):
    """(the refusal's reason, what was wrong) for an arriving event that may not
    enter this project's log by its shape; (None, "") when it passes."""
    if not isinstance(e, dict):
        return "bad-shape", "not a log event"
    writer = e.get("writer")
    if not (isinstance(writer, str) and "/" in writer.strip("/") and writer.isprintable() and " " not in writer):
        return "bad-shape", "its writer is not one a log holds"
    if not (codes.is_log_seq(e.get("seq")) and isinstance(e.get("ts"), str) and isinstance(e.get("kind"), str)):
        return "bad-shape", "it is not a log event (seq, ts, kind)"
    return None, ""


def unwrapped(raw):
    """An arriving event on RL10, `{event, signer, owners?}`: (the event, or
    what stands for it in a rejection; its `verified` key; the refusal's reason and
    what was wrong, or None and "")."""
    if not isinstance(raw, dict) or not isinstance(raw.get("event"), dict):
        return raw.get("event") if isinstance(raw, dict) else None, None, "bad-shape", \
            "not an event as the endpoint wraps it ({event, signer, owners?})"
    e = raw["event"]
    signer, owners = raw.get("signer"), raw.get("owners")
    if not (isinstance(signer, dict) and isinstance(signer.get("kind"), str)):
        return e, None, "bad-shape", "it carries no signer"
    if "owners" in raw and not (isinstance(owners, list) and all(
            isinstance(o, dict) and isinstance(o.get("id"), str) for o in owners)):
        return e, None, "bad-shape", "its owners are not a list of {id, email}"
    if "verified" in e:
        return e, None, "bad-shape", "its event carries a verified key of its own, which only the endpoint says"
    return e, {"signer": signer, **({"owners": owners} if "owners" in raw else {})}, None, ""


def same_uncoded(held, e, own=False):
    """Whether the event at a (writer, seq) is the one arriving (RL10): the
    canonical forms with the endpoint's verdict
    (`verified`) left out of both; for an event this machine wrote (`own`),
    what the endpoint adds when it returns it (ENDPOINT_ADDS) left out too,
    of both copies, so an echo of the stored event is the stored event."""
    drop = ("verified",) + (ENDPOINT_ADDS if own else ())
    try:
        return codes.canonical({k: v for k, v in held.items() if k not in drop}) == \
            codes.canonical({k: v for k, v in e.items() if k not in drop})
    except codes.NotCanonical:
        return False


def frontier(last, spent):
    """A writer's last seq here, carried past the spent positions that follow it."""
    while last + 1 in spent:
        last += 1
    return last


def tombstone(writer, seq):
    """The line the archive holds at a position the hub withheld, or this
    machine recorded refused or voided."""
    return {"writer": writer, "seq": seq, "withheld": True}


def notice_text(to):
    """What the sending session is shown of its message the hub withheld
    (P5 O18 D5): one word of why, and whom it was to — never its text."""
    return "[sminos: your message to %s was not delivered: not-reachable]" % to


def addressed_to(e):
    """The aliases a message names, as its notice says them: its `to`'s, in
    order, each once and joined (a copy or a broadcast names several), and
    `all` for one to everyone (`*`); None for an event that is no message
    (sminos.CHAT_KINDS), or none held."""
    if not isinstance(e, dict) or e.get("kind") not in sminos.CHAT_KINDS:
        return None
    to = e.get("to")
    if not isinstance(to, list):
        return "all"
    aliases = [r["alias"] for r in to if isinstance(r, dict) and isinstance(r.get("alias"), str) and r["alias"]]
    return ", ".join(" ".join(a.split())[:64] for a in dict.fromkeys(aliases)) or "all"


def notices_in(d):
    """The notices an uplink.json holds (HubLog.withhold_own), each
    {writer, seq, session, to, ts}; any other entry left out."""
    raw = d.get("notices")
    return [n for n in raw if isinstance(n, dict) and isinstance(n.get("writer"), str) and type(n.get("seq")) is int
            and isinstance(n.get("session"), str) and isinstance(n.get("to"), str) and isinstance(n.get("ts"), str)] \
        if isinstance(raw, list) else []


def runs_of(raw):
    """A withheld list as the hub's `have` carries it, `[seq | [from, to],
    ...]`, as sorted (from, to) runs; ValueError for anything else."""
    if not isinstance(raw, list):
        raise ValueError("not a list")
    out = []
    for r in raw:
        if codes.is_log_seq(r):
            out.append((int(r), int(r)))
        elif isinstance(r, list) and len(r) == 2 and all(codes.is_log_seq(x) for x in r) and r[0] <= r[1]:
            out.append((int(r[0]), int(r[1])))
        else:
            raise ValueError("%r is no seq or [from, to]" % (r,))
    return sorted(out)


def in_runs(seq, runs):
    return any(a <= seq <= b for a, b in runs)


def admitted_have(have, raw, own):
    """What a `have` confirms of this machine's own writers for the archive
    (D6): (`archive_have` — {have: {writer: seq}, withheld: {writer: [seq |
    [from, to], ...]}}, the own writers alone, `own` telling — or None, why
    not). The hub lists the positions it withheld whole, in the one frame
    (withheldOf), and a frame arrives whole or not at all: its parts are
    joined into the frame they carry, the endpoint passes the hub's `have`
    down unchanged, and an assembler that cannot hold a frame (the endpoint's
    and the hub's, 16 MiB) drops it whole. So a list that does arrive is the
    hub's whole list, and a list too large for one frame never arrives: no
    `have`, no confirmation, and the archive does not run. What sminos can
    still tell is a list that disagrees with the vector beside it — not a
    list of seqs and runs, or a position past its writer's head in that
    same `have` (a withheld position is held, as its tombstone, and counted
    there) — and such a `have` confirms nothing: the run it would start
    fails, never taking a cut or garbled list as complete."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return None, "its withheld is not {writer: [seq | [from, to], ...]}"
    withheld = {}
    for w, entries in raw.items():
        if not (isinstance(w, str) and own(w)):
            continue
        try:
            runs = runs_of(entries)
        except ValueError as e:
            return None, "its withheld list of %s is not seqs and [from, to] runs (%s)" % (w, e)
        if runs and runs[-1][1] > have.get(w, 0):
            return None, "it withholds %s:%d, past that writer's head in the same have (%d)" % (
                w, runs[-1][1], have.get(w, 0))
        if runs:
            withheld[w] = [a if a == b else [a, b] for a, b in runs]
    return {"have": {w: s for w, s in have.items() if own(w)}, "withheld": withheld}, ""


def append_verbatim(project, e, spent=(), same=same_uncoded):
    """Append an imported event to its writer's file as it came, under the
    locks every appender takes (`.sync.lock` shared, the file's own lock):
    "appended"; "present" when that (writer, seq) holds the same content
    (`same` tells); "conflict" when it holds another; "spent" when an event
    was refused there (a tombstone: nothing is ever appended at it, whatever
    arrives); "gap"
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
                        return "present" if same(x, e) else "conflict"
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
    """A writer file's writer (its first event's), last seq (its last
    well-formed line's, as an appender reads it) and first event's kind;
    ("", 0, "") when it holds none."""
    try:
        with open(path, "rb") as f:
            for line in f:
                e = sminos.parse_event(line.decode("utf-8", "replace")) if line.strip() else None
                if e:
                    return e["writer"], sminos._last_seq(f), e["kind"]
    except OSError:
        pass
    return "", 0, ""


PLUGIN_MANIFEST = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", ".claude-plugin",
                               "plugin.json")


def desk():
    """What this machine's daemon can do itself for the desk (DX4
    `machine.desk`, the desk control surface's M0): the sminos version it
    runs from, the RPCs it executes (the endpoint's, RL10_RPC_NAMES), and
    the reads it answers without a bridge (none yet). The manifest is read
    by stat (sminos.json_at), not once a process: the daemon restarts its
    uplink when a script changes, and a version bump alone changes none."""
    try:
        version = sminos.json_at(PLUGIN_MANIFEST).get("version")
    except (OSError, ValueError, AttributeError):
        version = None
    return {"sminos": version if isinstance(version, str) else "unknown", "rpcs": list(rpc.RL10_RPC_NAMES), "reads": []}


class HubLog:
    """One hub project's log plane: what this machine says of it up the
    stream, and how it takes what the hub sends of it."""

    def __init__(self, project, cred):
        self.project = project
        self.machine = cred["machine"]
        self.files = {}      # path → (size, mtime_ns, writer, last, first kind): the vector's reads, kept while a file holds
        self.listing = None  # (log dir mtime_ns, prefixes, paths): the own writers' files as last listed (own_paths)
        self.ran = {}        # session → when (monotonic) a hot look last found it running here
        self.epochs = {}     # own writer → how many bounds were set on it (bound), across streams: an upload's mark
        self.taken_failing = None   # TAKEN_FILE's write failure as last said (keep)
        self.notices_owed = None    # whether uplink.json holds notices to show (show_notices); None: not yet read
        self.host_files = {}  # host file → (its _log_file_held key, {session writer: its last seq}) as the uplink's
        #                       host pass last walked it (Link.host_pass)
        self.own_names = None  # (machine, machine_identity() it was built from, the own names): is_own's
        self.reset()

    def reset(self):
        """A new stream: nothing is known of the hub's vector until `have`."""
        self.have = None     # the hub's vector, from `have`
        self.sent = {}       # own writer → the last seq the hub holds or was queued an upload of on this stream
        self.stuck = set()   # own writers the hub refused: not uploaded again on this stream
        self.refused = {}    # own writer → the lowest seq the hub refused on this stream (0: the writer itself)
        self.archive = False
        self.drawing = None  # the uploads drawn and not yet taken (next_upload), kept between the uplink's passes
        self.bounds = {}     # own writer → the seq `taken` may not pass on this stream (bound), until an upload sent
        #                      after it is answered
        self.head_waits = True   # an operator writer may wait for its head (release_heads): False once none does

    # ---------------------------------------------------- what is held here

    @property
    def log_dir(self):
        return os.path.join(self.project.home, "log")

    def state(self):
        """uplink.json as it is now, a new dict the caller may change and
        save; {} when it is missing or holds no JSON object. Read by stat
        (sminos.json_at) while it holds still: save writes it whole, by
        rename, so a write moves its inode, and the upload pass asks every
        open project's each UPLOAD_EVERY."""
        try:
            d = sminos.json_at(os.path.join(self.project.home, STATE_FILE))
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

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

    def dead(self, d=None):
        """{writer: {"at": {seq}, "last": seq}}: this machine's writers the
        upstream refused `audience` (P5 O18: the stream is not the session's
        now), each stopped for good at the refused positions until an event
        is appended to it past `last`, its file's last seq when it was
        stopped (stop_dead; revive). `d`: the state as the caller read it."""
        raw = (self.state() if d is None else d).get("dead")
        out = {}
        for w, held in (raw.items() if isinstance(raw, dict) else ()):
            if isinstance(held, dict) and isinstance(held.get("at"), list) and type(held.get("last")) is int:
                at = {s for s in held["at"] if type(s) is int and s >= 1}
                if at:
                    out[w] = {"at": at, "last": held["last"], **({"final": True} if held.get("final") else {})}
        return out

    def voided(self, d=None):
        """{writer: {seq}}: the positions of this machine's writers it
        uploaded a content-free `void` at in place of the event its file
        holds there (revive), kept for good: every upload of the position
        sends the void again, its echo reads present, and the archive holds
        its tombstone. `d`: the state as the caller read it."""
        raw = (self.state() if d is None else d).get("voided")
        return {w: {s for s in ss if type(s) is int} for w, ss in raw.items() if isinstance(ss, list)} \
            if isinstance(raw, dict) else {}

    def withheld(self):
        """{writer: {seq}}: the positions of this machine's writers the hub
        withheld while an event of this machine's held them (withhold_own),
        kept for good: the file keeps the event, the hub a tombstone, and
        the archive copies the tombstone."""
        raw = self.state().get("withheld")
        return {w: {s for s in ss if type(s) is int} for w, ss in raw.items() if isinstance(ss, list)} \
            if isinstance(raw, dict) else {}

    def writers(self, own=False, live=None):
        """{writer: (last seq, path)} of the writer files the log holds (each
        read from its end, again only once it changed); `own`: only the files
        named as this machine's writers would be (and the legacy ones, while
        it writes the archive) — every UPLOAD_EVERY, the others' are no
        upload's, and a project another machine is busy in holds hundreds.

        `live` (own only: the sessions running here) makes it a hot look: a
        file is looked at again only while it is hot (hot), the rest read as
        last looked at. A machine's history is hundreds of writers of sessions
        that ended long ago, which nothing appends to; looking at every one of
        them every UPLOAD_EVERY was most of an idle uplink's work. The caller
        alternates: a whole look at every scan, hot looks between. A look
        that lists the directory again (it changed) is whole too: a file
        there may have been replaced."""
        whole = live is None
        if own:
            paths, listed = self.own_paths()
            whole = whole or listed
        else:
            paths = glob.glob(os.path.join(glob.escape(self.log_dir), "*.jsonl"))
        if live is not None:
            mono = time.monotonic()
            self.ran.update(dict.fromkeys(live, mono))
            if len(self.ran) > len(live) + RAN_KEEP:
                self.ran = {s: at for s, at in self.ran.items() if mono - at < HOT_FOR}
            wall = time.time_ns()
        out, seen = {}, set()
        for path in paths:
            seen.add(path)
            held = self.files.get(path)
            if not whole and held is not None and not self.hot(held, wall, mono):
                if held[2]:
                    out[held[2]] = (held[3], path)
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            if not held or held[:2] != (st.st_size, st.st_mtime_ns):
                held = self.files[path] = (st.st_size, st.st_mtime_ns, *writer_and_last(path))
            if held[2]:
                out[held[2]] = (held[3], path)
        if not own:
            for path in set(self.files) - seen:
                del self.files[path]
        return out

    def own_paths(self):
        """(The own writers' files (writers' `own`), whether they were listed
        just now): listed again only once the directory changed, since a
        file made or removed there moves its mtime. A listing is kept only
        when the directory had held still RACY before it, so an entry made in
        the same tick of a coarse clock (Linux takes a file's times from the
        timer tick) is never hidden behind an unchanged mtime. A listing
        that failed is no empty directory (glob would take EMFILE, in a
        process of many threads and sockets, for one): nothing of it is
        kept, and the next look lists again."""
        prefixes = [self.machine.replace("/", ".") + "."] + ([LEGACY.replace("/", ".")] if self.archive else [])
        before = time.time_ns()
        try:
            mtime = os.stat(self.log_dir).st_mtime_ns
        except OSError:
            mtime = None
        held = self.listing
        if held is not None and held[:2] == (mtime, prefixes):
            return held[2], False
        try:
            names = os.listdir(self.log_dir)
        except OSError:
            self.listing = None
            return [], True
        paths = [os.path.join(self.log_dir, name) for prefix in prefixes for name in glob_names(names, prefix)]
        self.listing = (mtime, prefixes, paths) if mtime is not None and before - mtime >= RACY_NS else None
        return paths, True

    def hot(self, held, wall, mono):
        """Whether a look between scans looks at this own writer file again:
        one it holds nothing of yet, one of no session (the operator's
        `<name>/human`), one of a session that ran here within HOT_FOR (an
        ended session's last events — the daemon's `retired` — come after it
        stopped), or one that changed within HOT_FOR. Any other append, to a
        writer quiet longer than that, is seen by the next scan's whole look,
        or at once when its sender nudged the daemon."""
        mtime_ns, writer = held[1], held[2]
        session = sminos.writer_session(writer) if writer else ""
        if not session:
            return True
        if mono - self.ran.get(session, -HOT_FOR) < HOT_FOR:
            return True
        return wall - mtime_ns < HOT_FOR * 1e9

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

    def hello(self, follow=False):
        """The project's `hello`; `follow` when this machine holds no checkout and no
        session of the project and opens it only to read and deliver (the
        org's directory): its lease then counts toward none of the project's
        machines. Without it the machine holds the project."""
        frame = {"t": "hello", "project": self.project.id, "name": self.project.name, "have": self.vector()}
        if follow:
            frame["follow"] = True
        return frame

    def presence(self, here=None):
        """DX4's `machine` message for this project: online (the hub's word,
        from the lease), the policy (on RL10 as RL10 says it, wire_policy),
        the project's known checkouts here, and what this machine's daemon
        can do itself (`desk`). `here`: known_checkouts' sessions, when the
        caller holds them."""
        try:
            checkouts = policy.known_checkouts(self.project, here)
        except (OSError, SystemExit) as e:
            log("the checkouts of %s could not be read: %r" % (self.project.name, e))
            checkouts = [{"path": self.project.root, "branch": policy.git_branch(self.project.root)}] \
                if self.project.root and not sminos.read_refused(self.project.root) \
                and os.path.isdir(self.project.root) else []
        return {"t": "session", "message": {
            "project": self.project.id, "machine": self.machine, "session": None, "kind": "machine",
            "sub": None, "n": None,
            "body": {"online": True, "policy": policy.wire_policy(), "checkouts": checkouts, "desk": desk()}}}

    def host_sent(self, d=None):
        """RL10: {writer: seq}, how far each writer of the project's host
        store (sminos.HOST_STORE) went up as sub-less `host` messages: where
        the uplink's next host pass starts. `d`: the state as the caller
        read it."""
        raw = (self.state() if d is None else d).get("host_sent")
        return {w: s for w, s in raw.items() if isinstance(w, str) and type(s) is int} \
            if isinstance(raw, dict) else {}

    def keep_host_sent(self, reach):
        """The host events up to `reach` ({writer: seq}) were written to the
        endpoint: the cursor moves there, never back."""
        d = self.state()
        held = self.host_sent(d)
        for w, seq in reach.items():
            held[w] = max(seq, held.get(w, 0))
        d["host_sent"] = held
        self.save(d)

    # ---------------------------------------------------- taken (daemon owed's evidence)

    def taken_held(self):
        try:
            with open(os.path.join(self.project.home, TAKEN_FILE)) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    @staticmethod
    def seqs(raw):
        return {w: s for w, s in raw.items() if isinstance(w, str) and type(s) is int} \
            if isinstance(raw, dict) else {}

    def taken(self):
        """{writer: seq}: how far each of this machine's writers no longer has
        to be sent (the module's `taken`)."""
        return self.seqs(self.taken_held().get("taken"))

    def conflicts(self):
        """{writer: seq}: the lowest position of each of this machine's
        writers where the upstream holds another event (a `conflict`
        refusal): no handshake resolves it, so it is kept until the
        upstream is seen holding this machine's own event there."""
        return self.seqs(self.taken_held().get("conflicts"))

    def write_taken(self, d):
        path = sminos.project_path(self.project, TAKEN_FILE)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="ascii") as f:
            json.dump(d, f, ensure_ascii=True)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def keep(self, taken, conflicts, lowering):
        """The file written whole, best effort: a write that fails is said
        once while it keeps failing and never stops the frame being handled.
        One that would have said more is owed (`lowering`) takes the file
        away instead, so it never says less is owed than is: with none,
        nothing is taken (an unlink needs no room)."""
        try:
            self.write_taken({"taken": taken, "conflicts": conflicts})
            if self.taken_failing is not None:
                log("%s of %s is written again" % (TAKEN_FILE, self.project.name))
            self.taken_failing = None
            return
        except OSError as e:
            why = "%s: %s" % (type(e).__name__, e.strerror or e)
        gone = ""
        if lowering:
            try:
                os.unlink(os.path.join(self.project.home, TAKEN_FILE))
                gone = ", so it is removed: nothing reads as taken until it is written again"
            except FileNotFoundError:
                gone = ""
            except OSError as e:
                gone = ", and it could not be removed (%s): `daemon owed` may read too little owed" % e
        if self.taken_failing != why:
            log("%s of %s could not be written (%s)%s" % (TAKEN_FILE, self.project.name, why, gone))
        self.taken_failing = why

    def epoch(self, writer):
        return self.epochs.get(writer, 0)

    def ceiling(self, writer, conflicts):
        """How far the writer may read as taken: below its unresolved bound
        on this stream and below a conflict kept."""
        out = self.bounds.get(writer)
        if writer in conflicts:
            out = min(conflicts[writer] - 1, conflicts[writer] - 1 if out is None else out)
        return out

    def keep_taken(self, reach, epochs=None):
        """The writers in `reach` ({writer: seq}) taken up to there: each
        moves forward only. An upload's answer passes `epochs`, each
        writer's epoch when the upload was sent: a writer bounded since takes
        nothing from it (the answer says the frame arrived, not that the
        upstream kept every event in it), and one bounded before has its
        bound resolved up to there. A vector (a periodic `have`) passes
        none, and moves no writer past its bound. Neither passes a
        conflict kept."""
        held, conflicts = self.taken(), self.conflicts()
        moved = {}
        for w, s in reach.items():
            if not self.own(w):
                continue
            if epochs is not None:
                if epochs.get(w, 0) != self.epoch(w):
                    continue
                if w in self.bounds:
                    self.bounds[w] = max(self.bounds[w], s)
            top = self.ceiling(w, conflicts)
            if top is not None:
                s = min(s, top)
            if s > held.get(w, 0):
                moved[w] = s
        if moved:
            self.keep({**held, **moved}, conflicts, lowering=False)

    def resume_taken(self, have):
        """An opening `have`, the stream's resume point: each of this
        machine's writers reads as taken exactly as far as the upstream says
        it holds it — down as well as up (an endpoint that died before
        keeping what was written to it) — but never past a conflict kept."""
        held, conflicts = self.taken(), self.conflicts()
        now = {}
        for w in set(held) | {w for w in have if self.own(w)}:
            s = have.get(w, 0) if self.own(w) else held[w]
            if w in conflicts:
                s = min(s, conflicts[w] - 1)
            if s > 0:
                now[w] = s
        if now != held:
            self.keep(now, conflicts, lowering=any(now.get(w, 0) < s for w, s in held.items()))

    def bound(self, writer, seq, conflict=False):
        """The upstream refused the writer at seq + 1 or asks it again from
        there (a refusal, a `resend`): `taken` is lowered to seq and held
        there on this stream, whatever an upload sent before it answers
        (its epoch moved) or a vector says, until an upload sent after it
        is answered, or a new stream's handshake says what the upstream
        holds. A `conflict` is kept past the stream (conflicts)."""
        self.epochs[writer] = self.epoch(writer) + 1
        self.bounds[writer] = min(seq, self.bounds.get(writer, seq))
        held, conflicts = self.taken(), self.conflicts()
        add = conflict and conflicts.get(writer, seq + 2) > seq + 1
        if add:
            conflicts = {**conflicts, writer: seq + 1}
        if held.get(writer, 0) > seq or add:
            self.keep({**held, writer: min(seq, held.get(writer, 0))} if writer in held else held, conflicts,
                      lowering=True)

    def resolved(self, writer, seq):
        """The upstream is seen holding this machine's own event at a
        conflict kept (its echo read `present`): the conflict is gone."""
        conflicts = self.conflicts()
        if conflicts.get(writer) == seq:
            del conflicts[writer]
            log("%s:%d of %s is held upstream as written here: its conflict is resolved"
                % (writer, seq, self.project.name))
            self.keep(self.taken(), conflicts, lowering=False)

    def unreported(self):
        raw = self.state().get("unreported")
        return [f for f in raw if isinstance(f, dict)] if isinstance(raw, list) else []

    def reported(self, frames):
        """The rejections in `frames` reached the endpoint (their frame written)."""
        if not frames:
            return
        d = self.state()
        left = [f for f in self.unreported() if f not in frames]
        d["unreported"] = left
        self.save(d)

    def rejoin_former(self):
        """The daemon's rejoin_former for this project, as the stream opens
        it: a member joined under a former name of this machine joins again
        under its name now, so the vector and the upload carry it."""
        return daemon.rejoin_former(self.project)

    def on_have(self, frame):
        have = frame.get("have")
        have = {w: s for w, s in have.items() if type(s) is int} if isinstance(have, dict) else {}
        opening, self.have = self.have is None, have
        self.drawing = None   # drawn again from what the hub holds now
        self.archive = frame.get("archive") is True
        if opening:
            # The handshake: upload from the hub's vector, every writer free.
            self.sent = {w: s for w, s in have.items() if self.own(w)}
            self.stuck, self.refused, self.bounds = set(), {}, {}
            self.resume_taken(have)
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
        # The designation as the hub said it now, and what the same `have`
        # admitted of this machine's own writers (archive_have, D6): the tick
        # loop's archive duty (sminos_archive) runs on both, never on `sent`
        # or `taken`.
        if not opening:
            self.keep_taken(have)   # what the hub holds of this machine's writers is taken, up to its bounds
        admitted, why = admitted_have(have, frame.get("withheld"), self.is_own)
        d = self.state()
        prev = d.get("archive_have") if isinstance(d.get("archive_have"), dict) else None
        if admitted is not None:
            # The hub lists the withheld positions of this machine's name now alone (withheldOf), so its vector says
            # nothing the archive may copy by for a former name's writer: a position withheld there, its refusal
            # lost to a disconnect before a `have` listed it, would be copied as admitted. A former name's entry,
            # vector and withheld alike, stays as the last `have` saved it while that name was listed (carried
            # from one saved entry to the next); with none saved, its writer is not copied. A former name gets
            # no new appends, so freezing it loses nothing.
            def former(w):
                return isinstance(w, str) and w.split("/", 1)[0] != self.machine and self.is_own(w)
            for part in ("have", "withheld"):
                kept = prev.get(part) if prev is not None and isinstance(prev.get(part), dict) else {}
                admitted[part] = {**{w: s for w, s in admitted[part].items() if not former(w)},
                                  **{w: s for w, s in kept.items() if former(w)}}
        if d.get("archive") != self.archive:
            log("the hub says this machine %s the archive of %s" % ("writes" if self.archive else "does not write",
                                                                   self.project.name))
        if why and d.get("archive_have_error") != why:
            log("the hub's have for %s confirms nothing for the archive: %s" % (self.project.name, why))
        d.update(archive=self.archive, archive_at=time.time(), archive_have=admitted)
        if why:
            d["archive_have_error"] = why
        else:
            d.pop("archive_have_error", None)
        self.save(d)
        if admitted is not None:
            self.withhold_listed(admitted["withheld"])
        self.release_heads()

    def withhold_listed(self, listed):
        """The positions a `have` lists withheld (its `withheld`, as
        admitted_have kept it) of this machine's writers under its name now,
        each an event of this machine's holds here and not yet recorded so:
        settled withheld (withhold_own), so a refusal lost to a dropped
        connection still reaches its sender, once."""
        held, lasts = self.withheld(), None
        for w, raw in sorted(listed.items()):
            if not self.allocated_here(w):
                continue
            if lasts is None:
                lasts = self.writers(own=True)
            last = lasts.get(w, (0, None))[0]
            for a, b in runs_of(raw):
                for seq in range(a, min(b, last) + 1):
                    if seq not in held.get(w, ()):
                        self.withhold_own(w, seq)

    def release_heads(self):
        """This machine's operator writers — `<machine>/human` and each
        audience stream of it, `<machine>/human~<digest>` (P5 O18 D6) — each
        waiting for the upstream's head (sminos.waits_for_head, #147), are
        released one by one once this stream's `have` said that writer's
        head and the log reached it — the upstream's events imported, or
        the positions the endpoint refused spent: what waited is
        appended above the head, and the next upload carries it. Looked at
        are the operator writers the `have` names, those the log holds and
        those queued, a former name's queue into its namesake under the name
        now; the first `have` of the enrolment is kept as the writers it
        named a head for (sminos.keep_headed). Run after a `have`, an import
        and a spent position."""
        me = self.machine + "/human"
        if self.have is None or sminos.host_name() != self.machine:
            return   # an uplink outliving a re-enrolment under another name releases nothing of the new one
        # A queue can still appear once nothing waits: a command that began
        # before a rename queues under the name it read then.
        queues = sminos.queued_operators(self.project)
        if not (self.head_waits or queues):
            return
        if self.head_waits:
            sminos.keep_headed(self.project, [w for w, s in self.have.items() if sminos.writer_base(w) == me and s > 0])
        lasts, spent = self.writers(own=True), self.spent()
        into = {sminos.namesake(w, self.machine) for w in queues}
        waiting = False
        for writer in sorted({w for w in set(self.have) | set(lasts) if sminos.writer_base(w) == me} | into):
            if writer not in into and not sminos.waits_for_head(self.project, writer):
                continue
            head = self.have.get(writer, 0)
            if frontier(lasts.get(writer, (0, None))[0], spent.get(writer, set())) < head:
                waiting = True
                continue
            released = sminos.release_queued(self.project, writer)
            self.drawing = None
            log("%s of %s is at the upstream's head (%d): it takes its seqs here from now on%s" % (
                writer, self.project.name, head,
                "; the %d that waited for it are appended above it" % len(released) if released else ""))
            if released:
                sminos.nudge_daemon()   # their delivery here, which waited with them
        # The enrolment's rule, which only an enrolment (a new uplink) changes: once nothing waits, a writer
        # the kept `have` did not name never will.
        self.head_waits = waiting

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
            else:
                self.sent[writer] = start - 1
                self.stuck.discard(writer)
                self.drawing = None
                log("the hub asks %s of %s again from %d" % (writer, self.project.name, start))
            self.bound(writer, start - 1)   # the hub lacks it from `start`, whatever an answer said before

    def on_refused(self, frame):
        """The hub refused what this machine sent; said in daemon.log. A
        writer refused stops uploading on this stream (sending it again would
        be refused again). An `audience` refusal (P5 O18: the stream the
        event went under is not its session's now) stops the writer past the
        stream (stop_dead). A `state-unavailable` one (the policy registry
        could not check the event) stops nothing: the endpoint rewinds. A
        `not-reachable` one
        (the hub withheld the event, a tombstone in its place) stops
        nothing: the writer goes on at the next seq, and the position is
        settled withheld here (withhold_own)."""
        r = frame.get("refusal") if isinstance(frame.get("refusal"), dict) else {}
        reason, writer = r.get("reason"), r.get("writer")
        self.drawing = None   # what was drawn may hold a writer stopped now
        log("the hub refused in %s: %s%s%s" % (
            self.project.name, reason, " %s:%s" % (writer, r.get("seq")) if writer else "",
            " — %s" % " ".join(str(r.get("message") or "").split())[:300] if r.get("message") else ""))
        stops = ("conflict", "writer-not-yours", "bad-shape", "too-large", "audience", "malformed")
        seq = r.get("seq")
        at = seq if type(seq) is int and seq >= 1 else 0
        if isinstance(writer, str) and self.own(writer) and reason in stops:
            self.stuck.add(writer)
            self.refused[writer] = min(at, self.refused.get(writer, at))
            # Owed again from what it refused; a conflict (the upstream holds another event there) past the stream.
            self.bound(writer, max(at - 1, 0), conflict=reason == "conflict")
            if reason == "audience" and at:
                self.stop_dead(writer, at)
            elif reason == "conflict" and at and at in self.voided().get(writer, ()):
                # The endpoint signed another body at a position the hub then refused `audience`: its ledger
                # refuses the void there for good (MAWS O18 M2), so the writer can never go on past it.
                self.stop_dead(writer, at, final=True)
        elif isinstance(writer, str) and self.own(writer) and reason == "not-reachable" and at:
            self.withhold_own(writer, at)

    def stop_dead(self, writer, seq, final=False):
        """An `audience` refusal of an own writer at seq: the writer is dead
        (dead) — never uploaded again, on this stream or a later one, while
        its stream is not its session's — until an event is appended to it
        after this (the CLI's stream choice chose it again: revive). Kept in
        uplink.json with the file's last seq now."""
        try:
            with open(sminos.writer_path(self.project, writer), "rb") as f:
                last = sminos._last_seq(f)
        except OSError:
            last = 0
        d = self.state()
        dead = d.get("dead") if isinstance(d.get("dead"), dict) else {}
        held = self.dead().get(writer, {"at": set(), "last": 0})
        dead[writer] = {"at": sorted(held["at"] | {seq}), "last": max(last, held["last"]),
                        **({"final": True} if final or held.get("final") else {})}
        d["dead"] = dead
        self.save(d)
        if final:
            log("%s of %s: the void at %d was refused conflict, where the endpoint signed another body: the writer "
                "stops there for good" % (writer, self.project.name, seq))
        else:
            log("%s of %s was refused audience at %d: not uploaded again until an event is appended to it"
                % (writer, self.project.name, seq))

    def revive(self, writer, held):
        """A dead writer that took an event since it was stopped: current
        again. Its refused positions go up as `void`s (voided, for good), the
        rest of it as stored, from the first of them on."""
        d = self.state()
        dead = d.get("dead") if isinstance(d.get("dead"), dict) else {}
        dead.pop(writer, None)
        voided = d.get("voided") if isinstance(d.get("voided"), dict) else {}
        voided[writer] = sorted(self.voided().get(writer, set()) | held["at"])
        d.update(dead=dead, voided=voided)
        self.save(d)
        self.sent[writer] = min(self.sent.get(writer, 0), min(held["at"]) - 1)
        self.stuck.discard(writer)
        self.refused.pop(writer, None)
        log("%s of %s took an event since it was refused audience: it goes up again, a void at %s"
            % (writer, self.project.name, ", ".join(map(str, sorted(held["at"])))))
        return set(voided[writer])

    def void_of(self, e):
        """The content-free event uploaded at a voided position in place of
        the event the file holds there: `{ts, writer, seq, kind: void, of,
        audience}`, `audience` this machine's claim of its stream's audience
        (sminos_audience.stream_audience, kept when the stream's first event
        was written), none under a plain writer. None when a stream's
        audience is not known here."""
        v = {"ts": e["ts"], "writer": e["writer"], "seq": e["seq"], "kind": "void", "of": e["seq"]}
        if sminos.is_stream(e["writer"]):
            audience = sminos_audience.stream_audience(self.project, e["writer"])
            if audience is None:
                return None
            v["audience"] = audience
        return v

    def withhold_own(self, writer, seq):
        """An own position the hub withheld (P5 O18 D5: its `not-reachable`
        refusal, or its tombstone seen on resync) while the event this
        machine's session wrote holds it here. spend_own keeps such a
        position the event's, rightly for every reason it serves; here the
        hub holds a tombstone in its place and the writer goes on past it.
        Recorded withheld for good (withheld), the event left in its writer
        file as this machine's record of what its session tried to send,
        and counted as uploaded: taken, never stopped or bounded, so the
        writer's next events go up and nothing waits behind it (`sent` is
        left as it is: an upload of it again, a `resend` from before it, is
        withheld again for the same body). The sending session's notice is
        queued (show_notices); the operator's writer has no session, so its
        notice is the daemon.log line alone. The session's own `joined` or
        `state` is owed a restatement (sminos_daemon.owe_restatement: the
        hub's registry moves only on those), unless it was the restatement,
        which owes nothing more: owed before the position is settled, and
        settled even when the debt cannot be recorded. A position withheld
        already queues nothing.
        Whether it was recorded now."""
        if seq in self.withheld().get(writer, ()):
            return False
        e = next((x for x in read_events(sminos.writer_path(self.project, writer)) if x["seq"] == seq), None)
        d = self.state()
        held = d.get("withheld") if isinstance(d.get("withheld"), dict) else {}
        held[writer] = sorted(set(held.get(writer) or []) | {seq})
        d["withheld"] = held
        to, session = addressed_to(e), sminos.writer_session(writer)
        at = sminos._ts_epoch(e.get("ts")) if e is not None else None
        if to is None:
            told = ""
        elif not session:
            told = "; the operator's message to %s was not delivered" % to
        elif at is None or time.time() - at > NOTICE_KEPT:
            told = "; the message is too old for its session %s to be told" % session[:8]
        else:
            d["notices"] = notices_in(d) + [{"writer": writer, "seq": seq, "session": session, "to": to,
                                             "ts": e["ts"]}]
            self.notices_owed = True
            told = "; its session %s is told" % session[:8]
        # The debt before the settlement: a settled position returns early above, so a debt recorded after it
        # would be lost to a process that died between the two; owed first, a refusal seen again repairs it.
        try:
            owed = daemon.owe_restatement(self.project, writer, seq, e)
        except OSError as err:
            owed = None
            told += "; its restatement could not be recorded as owed (%s)" % err
        self.save(d)
        self.keep_taken({writer: seq})
        if owed == "owed":
            told += "; its %s is owed a restatement, at the daemon's next tick" % e["kind"]
        elif owed == "again":
            told += ("; it restated session %s's %s, which the hub withheld again: not restated again, a cause "
                     "that holds (a session bound to another machine) is not repaired by republishing, and "
                     "its next %s is the next try" % (session[:8], e["kind"], e["kind"]))
        log("the hub withheld %s:%d of %s (not-reachable): settled here, the writer goes on past it%s"
            % (writer, seq, self.project.name, told))
        return True

    def show_notices(self):
        """The notices withhold_own queued, each pushed to its sending
        session while that session is live, as a frame no log holds (no
        peer log event, so no reach is asked for it), and dropped once
        pushed, once a push may have reached it, or NOTICE_KEPT past its
        message's ts (said in daemon.log); a session not live keeps its
        notice. Run on the uplink's upload pass; uplink.json is read only
        while it holds some."""
        if self.notices_owed is False:
            return
        d = self.state()
        queued = notices_in(d)
        left = []
        for n in queued:
            at = sminos._ts_epoch(n["ts"])
            if at is None or time.time() - at > NOTICE_KEPT:
                log("the notice of %s:%d of %s was not shown: its session %s was not live within %d h of the "
                    "message" % (n["writer"], n["seq"], self.project.name, n["session"][:8], NOTICE_KEPT // 3600))
                continue
            peer = sminos.peer_for_session(n["session"])
            if not peer:
                left.append(n)
                continue
            try:
                sminos.control_module().push_live(peer, n["session"], notice_text(n["to"]))
            except sminos.SendFailed as e:
                if e.phase == "before":
                    left.append(n)
                    continue
                log("the notice of %s:%d of %s may have reached its session %s (%s): not pushed again"
                    % (n["writer"], n["seq"], self.project.name, n["session"][:8], e))
        if left != queued:
            d["notices"] = left
            self.save(d)
        self.notices_owed = bool(left)

    def own(self, writer):
        return writer.startswith(self.machine + "/") or (self.archive and writer.startswith(LEGACY))

    def uploads(self, live=None, state=None):
        """`events` frames of this machine's writers the hub lacks, each with
        the (writer, seq) it brings the hub to, drawn as they are taken: each
        writer's file is read, and its events sealed, only once the frames
        before them were taken. Yields (frame, {writer: seq}). `live`: a hot
        look (writers); `state`: uplink.json as the caller read it just
        now."""
        if self.have is None:
            return
        batch, reach, size = [], {}, 0
        state = self.state() if state is None else state
        dead, voided = self.dead(state), self.voided(state)

        def frame():
            return {"t": "events", "project": self.project.id, "events": batch}, reach

        # A writer whose first event is an `unlisted` notice (a notice's stream holds nothing else, P5 O18 D6)
        # goes first: the hub judges a notice against its registry as it stood before the batch, so the snapshot
        # of the change it announces must never go up in an earlier one (sminos_visibility).
        own = self.writers(own=True, live=live)
        notices = {held[2] for held in self.files.values() if held[4] == "unlisted"}
        for writer, (last, path) in sorted(own.items(), key=lambda kv: (kv[0] not in notices, kv[0])):
            if not self.own(writer):
                continue
            if writer in dead:
                if dead[writer].get("final") or last <= dead[writer]["last"]:
                    continue
                voided[writer] = self.revive(writer, dead[writer])
            if writer in self.stuck or last <= self.sent.get(writer, 0):
                continue
            voids = voided.get(writer, ())
            for e in sorted((e for e in read_events(path) if e["seq"] > self.sent.get(writer, 0)),
                            key=lambda e: e["seq"]):
                if e["seq"] in voids:
                    e = self.void_of(e)
                    if e is None:
                        log("%s of %s: its stream's audience is not known here, so no void can stand at a position "
                            "it refused; it and the rest of its writer stay here" % (writer, self.project.name))
                        self.stuck.add(writer)
                        break
                try:
                    sealed = self.as_uploaded(e)
                    n = len(codes.canonical(sealed).encode("utf-8"))
                except codes.NotCanonical as err:
                    log("%s:%d in %s has no canonical form (%s): it and the rest of its writer stay here"
                        % (writer, e["seq"], self.project.name, err))
                    self.stuck.add(writer)
                    break
                if batch and size + n > BATCH_BYTES:
                    yield frame()
                    batch, reach, size = [], {}, 0
                batch.append(sealed)
                reach[writer] = e["seq"]
                size += n
        if batch:
            yield frame()

    def undraw(self):
        """The draw dropped: a frame drawn and not sent is drawn again, from
        what was taken, at the next call (RL10's member frames held it)."""
        self.drawing = None

    @staticmethod
    def as_uploaded(e):
        """An event of this machine as it goes up RL10: as stored (this
        machine's own carry no code and no `created`), but never with the
        endpoint's verdict, which an echo kept here would carry."""
        return {k: v for k, v in e.items() if k != "verified"}

    def next_upload(self, live=None, state=None):
        """The next upload, (frame, {writer: seq}), or None when nothing is
        owed now. A pass the uplink paces (it stops while its lane is full)
        leaves the rest of its draw here, not yet read or sealed, and the
        next pass goes on from there, so a long backlog is read and sealed
        once, not once a pass. What would change the draw — a `have`, a `resend`, a refusal,
        a new stream — drops it, and the next call draws afresh. `live`: a
        fresh draw looks at the hot writers alone (writers); `state`:
        uplink.json as the caller read it just now, for a fresh draw."""
        if self.drawing is None:
            self.drawing = self.uploads(live, state)
        try:
            got = next(self.drawing, None)
        except BaseException:
            self.drawing = None
            raise
        if got is None:
            self.drawing = None
        return got

    def took(self, reach):
        """An upload was queued: the next `have` puts `sent` right should
        its frame be lost."""
        for writer, seq in reach.items():
            self.sent[writer] = max(self.sent.get(writer, 0), seq)

    # ---------------------------------------------------- down

    def is_own(self, writer):
        """Whether a writer is one of this machine's, under its name or a
        former one (RL10: the endpoint returns those only as echoes). The
        names are built again only once the identity they came from is
        another (a welcome that renames forgets the caches, and the next
        machine_identity is a new tuple)."""
        ident, held = sminos.machine_identity(), self.own_names
        if held is None or held[0] != self.machine or held[1] is not ident:
            held = self.own_names = (self.machine, ident, frozenset({self.machine, *ident[1]}))
        return writer.split("/", 1)[0] in held[2]

    def same(self, held, e):
        """Whether an arriving event is the one held at its position: an own
        voided position holds the event this machine's session wrote, and the
        `void` uploaded in its place is its copy upstream."""
        if e.get("kind") == "void" and e.get("of") == e["seq"] and self.is_own(e["writer"]) \
                and e["seq"] in self.voided().get(e["writer"], ()):
            return True
        return same_uncoded(held, e, self.is_own(e["writer"]))

    def take(self, events):
        """An `events` frame from the endpoint: each event, wrapped and
        verified by the endpoint (`unwrapped`), checked by its shape and
        appended with its `verified` key, or refused. Returns (how many were
        appended, the `rejected` frames)."""
        if not isinstance(events, list):
            log("an events frame for %s without a list of events: ignored" % self.project.name)
            return 0, []
        appended, out, spent = 0, [], self.spent()
        newly, conflicts = {}, self.conflicts()
        for raw in events:
            # What a rejection names is the event, not its wrapper.
            named, verified, reason, why = unwrapped(raw)
            if reason is None:
                reason, why = refusal(self.project, named)
            e = named
            if reason is None:
                # JSON's 3.0 is the number 3; the log's readers take an int.
                e = {**e, "seq": int(e["seq"]), "verified": verified}
            if reason is None:
                outcome = append_verbatim(self.project, e, spent.get(e["writer"], set()) | newly.get(e["writer"], set()),
                                          self.same)
                if outcome == "appended":
                    appended += 1
                elif outcome == "gap":
                    log("held back %s in %s: its seq is not one past the writer's last (the hub sends what is "
                        "missing at the next hello)" % (position(e), self.project.name))
                elif outcome == "present" and conflicts.get(e["writer"]) == e["seq"] and self.is_own(e["writer"]):
                    self.resolved(e["writer"], e["seq"])
                elif outcome == "conflict":
                    reason, why = CONFLICT_REASON, "%s:%d holds another event here" % (e["writer"], e["seq"])
                elif outcome == "spent":
                    reason, why = CONFLICT_REASON, "%s:%d was refused here before: nothing is appended there" % (
                        e["writer"], e["seq"])
            if reason is None:
                continue
            log("refused %s in %s: %s" % (position(named), self.project.name, why))
            out.append(rejected(self.project.id, named, reason, why))
            if isinstance(named, dict) and isinstance(named.get("writer"), str) and codes.is_log_seq(named.get("seq")):
                if self.allocated_here(named["writer"]):
                    if self.spend_own(named["writer"], int(named["seq"])):
                        newly.setdefault(named["writer"], set()).add(int(named["seq"]))
                else:
                    newly.setdefault(named["writer"], set()).add(int(named["seq"]))
        if out:
            d = self.state()
            held = d.get("spent") if isinstance(d.get("spent"), dict) else {}
            for w, ss in newly.items():
                held[w] = sorted(set(held.get(w) or []) | ss)
            d["spent"] = held
            d["unreported"] = self.unreported() + out
            self.save(d)
        self.release_heads()
        return appended, out

    def allocated_here(self, writer):
        """Whether this machine's appenders allocate `writer`: its operator
        writer or one of its sessions' (`sminos.writer_id`), exactly
        `<machine>/human` or `<machine>/<session uuid>`, or an audience
        stream of either (`<writer>~<digest>`, P5 O18 D6). Any other name,
        even one under this machine's prefix, is no file the allocator
        opens."""
        prefix = self.machine + "/"
        if not writer.startswith(prefix):
            return False
        rest = sminos.writer_base(writer)[len(prefix):]
        return rest == "human" or bool(sminos.UUID_RE.fullmatch(rest))

    def spend_own(self, writer, seq):
        """A refused position of one of this machine's own writers (is_own:
        under its name, which its appenders allocate — sminos._append skips
        spent positions — or a former one): spent under the writer file's
        lock, as the allocator reads it, and only while no event of this
        machine's holds it — a position its own event took first is that
        event's. Whether it was spent."""
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

    def spend(self, writer, seq, reason, by="the endpoint"):
        """RL10's `spent {project, writer, seq, reason}`: the endpoint refused
        an arriving event for good (rejected up to the hub already) and sends
        its position with no content (O10 M6). Recorded as a position refused
        here is (`take`): an own writer's, under this machine's name or a
        former one, through `spend_own`, so a position an event of this
        machine holds stays that event's (a lost endpoint ledger answers this
        machine's own echoes `conflict`) — and, the hub's tombstone there
        (`withheld`), is settled withheld (withhold_own); any other's
        added to the spent positions. Nothing is reported up. Each position
        is said once in daemon.log, with its project and the endpoint's
        reason. Whether it was spent now."""
        if not (isinstance(writer, str) and "/" in writer.strip("/") and writer.isprintable() and " " not in writer
                and codes.is_log_seq(seq)):
            log("a spent frame for %s names no position (%r:%r): ignored" % (self.project.name, writer, seq))
            return False
        seq = int(seq)
        why = " ".join(reason.split())[:100] if isinstance(reason, str) else "no reason given"
        where = "%s:%d in %s (%s)" % (writer, seq, self.project.name, self.project.id)
        if seq in self.spent().get(writer, ()):
            return False   # said when it was spent
        if self.is_own(writer):
            if not self.spend_own(writer, seq):
                if reason == "withheld":
                    # The hub's tombstone of what this machine sent (D5), seen on resync: settled as its refusal is.
                    self.withhold_own(writer, seq)
                    return False
                log("%s spent %s: %s; an event of this machine holds that position, so it is not spent"
                    % (by, where, why))
                return False
        else:
            d = self.state()
            held = d.get("spent") if isinstance(d.get("spent"), dict) else {}
            held[writer] = sorted(set(held.get(writer) or []) | {seq})
            d["spent"] = held
            self.save(d)
        log("%s spent %s: %s; refused for good, never stored or delivered here, and the writer's later "
            "events are not held behind it" % (by, where, why))
        self.release_heads()
        return True

    def deliver(self):
        """What an import made owed to this machine's members, delivered now."""
        sminos.forget_caches()
        total, reached = daemon.deliver_owed(self.project, sminos.view_of(self.project, titles=False))
        if total:
            log("delivered %d in %s to %s" % (total, self.project.name, ", ".join(reached)))
