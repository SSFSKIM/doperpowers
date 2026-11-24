"""The question sheet's record: its door, its reader, the step's shell and the command's verbs (contracts X1 and X2
of MAWS's docs/doperpowers/specs/2026-11-23-question-sheet-design.md; this repository's plan
docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, I1 to I5).

One session's sheet is a directory, `$SMINOS_HOME/sheet/<session>/`: `state.json`, which only the tool's step
writes (by atomic replace, under the record's lock), and `inbox.jsonl`, to which every surface appends through
one door. The lock is `$SMINOS_HOME/sheet/<session>.lock` beside the record, `fcntl.flock`'d and never removed.

    sminos sheet put  (<member> | --session <id>) [--no-wait]    the door: JSON lines on stdin
    sminos sheet show (<member> | --session <id>) [--json [--keys <k,...>]]   the reader's model, or its text

From M2 (I3, I5):

    sminos sheet step  --session <id>              the tool's step: one JSON event on stdin, one answer on stdout
    sminos sheet probe --session <id> [--remote]   what the start choice asks of a record, read without the lock
    sminos sheet answer|dismiss|retract|remove (<member> | --session <id>) ...    the command's acts on a sheet
    sminos sheet surfaces [--json]                 the registrations, and which are alive

`<member>` is a member as the control verbs name one; where no member matches, a unique prefix (8 characters or
more) of a session that has a record names it, as the terminal's band prints it (`sminos sheet show <first 8>`).

The step's transitions and composers are sminos_sheet_step's pure function; this module is its shell (the lock,
the staging, the files, the replace).

`put` appends the lines whole or not at all, under the lock, then tells the session's bridge (`{"op": "sheet",
"keys": [...]}`) and prints one JSON object, `{session, results: [{key, state, ...verdict}]}`, `queued` for a key
no verdict came back for. Exits: 0 appended, 2 a line refused (nothing appended), 3 no record (`no sheet`), 75 the
lock not had in 10 s. `show` takes no lock: it reads `state.json`, the inbox past its offset up to the last
newline, and `state.json` again, starting over while `seq` moves. The published set (`sminos/types/sheet/`) is the
contract both are held to.
"""

import base64
import errno
import fcntl
import json
import math
import os
import re
import shutil
import stat
import sys
import time
import uuid

import sminos as S

LOCK_WAIT_S = 10
EXIT_NO_SHEET = 3
EXIT_BUSY = 75
DOOR_LINES = 50
KEYS_MAX = 50
# What a pending outcome carries in either form of `show --json`, each string at most (I4): an imported question
# has no input bounds, and the keyed form goes through a hook's process call.
CUT_QUESTION, CUT_LABEL, CUT_HEADER, CUT_NAME = 2000, 200, 60, 200
NUDGE_WAIT_MS = 10000
KEYED_TEXT = 500

KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
ID_RE = re.compile(r"^q[1-9][0-9]{0,8}$")       # an id names at most q999999999: bounded, never cut
TIME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")
UPLOAD_RE = re.compile(r"^uploads/[A-Za-z0-9._-]{1,250}\.(png|jpg|jpeg|gif|webp)$")
KINDS = ("answer", "dismiss", "retract", "delivered")
BYS = ("page", "maws", "desk", "cli")
FIELDS = ("v", "key", "kind", "id", "revision", "picks", "text", "images", "target", "keys", "batch", "by", "at")


class Busy(Exception):
    pass


# ------------------------------------------------------------------ where the record is


def sheet_root():
    return os.path.join(S.root(), "sheet")


def record_dir(session):
    return os.path.join(sheet_root(), session)


def lock_path(session):
    return os.path.join(sheet_root(), session + ".lock")


class Lock:
    """The record's lock: an exclusive flock on the file beside it, waited for at most LOCK_WAIT_S. The file is
    never unlinked: a process may hold its inode while another makes a new file at the path."""

    def __init__(self, session):
        self.path = lock_path(session)
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                    raise
            if time.monotonic() >= deadline:
                os.close(self.fd)
                raise Busy()
            time.sleep(0.02)

    def __exit__(self, *_):
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)


# ------------------------------------------------------------------ a line


def _count(v, least):
    """A JSON integer at least `least`: 1.0 is the integer 1, as JSON Schema counts it; a boolean, an infinity and
    NaN are none."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return (isinstance(v, int) or (math.isfinite(v) and v == int(v))) and v >= least


def _no_constant(name):
    raise ValueError("%s is not JSON" % name)


def loads(text):
    """JSON as a line is read: NaN and the infinities, which Python's decoder takes, are refused, and so is a value
    nested past what the decoder can follow."""
    try:
        return json.loads(text, parse_constant=_no_constant)
    except RecursionError:
        raise ValueError("nested too deep")


def _surrogate(v):
    """Whether a decoded JSON value holds a lone UTF-16 surrogate (an escape like \\ud83d without its pair)."""
    if isinstance(v, str):
        return any("\ud800" <= c <= "\udfff" for c in v)
    if isinstance(v, list):
        return any(_surrogate(x) for x in v)
    if isinstance(v, dict):
        return any(_surrogate(k) or _surrogate(x) for k, x in v.items())
    return False


def line_error(line):
    """Why an inbox line fails its schema (inbox-line.schema.json), or None."""
    if not isinstance(line, dict):
        return "a line is a JSON object"
    extra = sorted(set(line) - set(FIELDS))
    if extra:
        return "unknown field %s" % extra[0]
    if not (_count(line.get("v"), 1) and line["v"] == 1):
        return "v is 1"
    for f in ("key", "kind", "by"):
        if f not in line:
            return "%s is required" % f
    if not isinstance(line["key"], str) or not KEY_RE.fullmatch(line["key"]):
        return "key is 8 to 128 of [A-Za-z0-9._:-]"
    if line["kind"] not in KINDS:
        return "kind is one of %s" % ", ".join(KINDS)
    if line["by"] not in BYS:
        return "by is one of %s" % ", ".join(BYS)
    if "at" in line and not (isinstance(line["at"], str) and TIME_RE.fullmatch(line["at"])):
        return "at is a UTC time with milliseconds"
    if "id" in line and not (isinstance(line["id"], str) and ID_RE.fullmatch(line["id"])):
        return "id is q<n>, n at most 999999999"
    if "revision" in line and not _count(line["revision"], 1):
        return "revision is an integer from 1"
    if "picks" in line and not (isinstance(line["picks"], list) and len(line["picks"]) <= 12
                                and all(isinstance(p, str) for p in line["picks"])):
        return "picks are at most 12 labels"
    if "text" in line and not (isinstance(line["text"], str) and len(line["text"]) <= 20000):
        return "text is at most 20,000 characters"
    if "images" in line and not (isinstance(line["images"], list) and len(line["images"]) <= 8
                                 and all(isinstance(i, str) and UPLOAD_RE.fullmatch(i) for i in line["images"])):
        return "images are at most 8 uploads/<name>.png|jpg|jpeg|gif|webp, its name before the final dot 1 to 250 characters"
    for f in ("target", "batch"):
        if f in line and not (isinstance(line[f], str) and KEY_RE.fullmatch(line[f])):
            return "%s is a key" % f
    if "keys" in line and not (isinstance(line["keys"], list) and 1 <= len(line["keys"]) <= 200
                               and all(isinstance(k, str) and KEY_RE.fullmatch(k) for k in line["keys"])):
        return "keys are 1 to 200 keys"
    if _surrogate(line):          # last: every field is known by now, each a string or a list of strings
        return "a string holds a lone UTF-16 surrogate"
    kind = line["kind"]
    if kind == "answer":
        if "id" not in line or "revision" not in line:
            return "an answer names id and revision"
        if not line.get("picks") and not line.get("text"):
            return "an answer has picks or text"
    if kind == "dismiss" and "id" not in line:
        return "a dismissal names id"
    if kind == "retract" and "target" not in line:
        return "a retract names target"
    if kind == "delivered" and "keys" not in line:
        return "a delivered line names keys"
    return None


def pick_error(line, questions):
    """Why an answer's picks are no labels of the question it answers at its current revision, or more than one
    on a single-select question (U2), or None."""
    if line.get("kind") != "answer":
        return None
    q = next((q for q in questions if q.get("id") == line.get("id")), None)
    if q is None or q.get("revision") != line.get("revision"):
        return None
    labels = [o.get("label") for o in q.get("options") or []]
    for p in line.get("picks") or []:
        if p not in labels:
            return "%s has no option %s at revision %d" % (q["id"], json.dumps(p, ensure_ascii=False)[:210],
                                                          q["revision"])
    if len(line.get("picks") or []) > 1 and not q.get("multiSelect"):
        return "%s takes one pick" % q["id"]
    return None


# ------------------------------------------------------------------ the reader (I4)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _tail(rec, offset):
    """The inbox's lines from `offset` to its last newline: bytes after it are a write that did not finish."""
    try:
        with open(os.path.join(rec, "inbox.jsonl"), "rb") as f:
            f.seek(offset)
            data = f.read()
    except FileNotFoundError:
        return []
    end = data.rfind(b"\n")
    return data[:end].split(b"\n") if end >= 0 else []


def snapshot(session):
    """(state, tail lines) read as one: state, inbox, state again, over while seq moved, three times at most;
    past that it raises Busy (the caller reads again). None when the session has no record."""
    rec = record_dir(session)
    path = os.path.join(rec, "state.json")
    state = tail = None
    for _ in range(4):
        try:
            first = _read_json(path)
        except FileNotFoundError:
            return None
        tail = _tail(rec, int(first["inbox"]["offset"]))
        try:
            state = _read_json(path)
        except FileNotFoundError:
            return None
        if state.get("seq") == first.get("seq"):
            return state, tail
    raise Busy()


def queued_lines(state, tail):
    """The tail's valid lines whose key has no verdict and did not occur earlier in the tail, in file order."""
    seen, out = set(state.get("verdicts") or {}), []
    for raw in tail:
        try:
            line = loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if line_error(line) or pick_error(line, state.get("questions") or []):
            continue
        if line["key"] in seen:
            continue
        seen.add(line["key"])
        out.append(line)
    return out


def changed(ref):
    try:
        st = os.stat(ref["abs"])
    except OSError:
        return True
    return st.st_size != ref.get("size") or st.st_mtime_ns // 1000000 != ref.get("mtimeMs")


def _asker(a):
    return dict(a, name=str(a.get("name", ""))[:CUT_NAME]) if isinstance(a, dict) else a


def bounded(outcome):
    """A pending outcome as `show --json` carries it (I4): an answer's picks also as `places`, integers from 1
    among the options of the answered revision, read from the whole snapshot before any label is cut, since two
    labels can share their first 200 characters; then each string cut, the question at 2,000, its header at 60,
    each label and each pick at 200, a subagent's name at 200."""
    o = dict(outcome)
    q = dict(o.get("question") or {})
    labels = [str(x) for x in q.get("options") or []]
    if o.get("kind") == "answer":
        o["places"] = [labels.index(p) + 1 for p in o.get("picks") or [] if p in labels]
        o["picks"] = [str(p)[:CUT_LABEL] for p in o.get("picks") or []]
    q["question"] = str(q.get("question", ""))[:CUT_QUESTION]
    if "header" in q:
        q["header"] = str(q["header"])[:CUT_HEADER]
    q["options"] = [x[:CUT_LABEL] for x in labels]
    q["asker"] = _asker(q.get("asker"))
    o["question"] = q
    return o


def keyed(outcome):
    """An outcome as the keyed form carries it: its text the first KEYED_TEXT characters, `textCut` when it was
    longer (the record's `textFile` names the whole where it has one), so fifty keys stay far under the 4 MiB a
    hook's process call returns."""
    o = dict(outcome)
    if len(o.get("text") or "") > KEYED_TEXT:
        o["text"], o["textCut"] = o["text"][:KEYED_TEXT], True
    return o


def model(session, keys=None):
    """What `show --json` prints (I4), or None for no record. `keys` holds `sent` and `pending` to those keys and
    leaves `open`, `hidden` and `closed` out."""
    got = snapshot(session)
    if got is None:
        return None
    state, tail = got
    queued = queued_lines(state, tail)
    retracted = {x["target"] for x in queued if x["kind"] == "retract"}
    cancelled = {x["key"] for x in queued if x["kind"] in ("answer", "dismiss") and x["key"] in retracted}
    live = [x for x in queued if x["key"] not in cancelled]
    pending_keys = {o["key"] for o in state.get("pending") or []}
    verdicts = state.get("verdicts") or {}

    sent = []
    for key in sorted(verdicts):
        v = verdicts[key]
        if key in pending_keys:
            st = "accepted"
        elif v.get("verdict") == "applied":
            st = "delivered"
        else:
            st = v.get("verdict")
        sent.append({"key": key, "state": st, **v})
    for x in queued:
        s = {"key": x["key"], "kind": x["kind"], "state": "queued"}
        # projected by kind, as show's schema tells the three apart: a line may carry a field of another kind's,
        # which the line's schema allows and no reader shows
        if x["kind"] in ("answer", "dismiss"):
            s["id"] = x["id"]
            if x["key"] in cancelled:
                s["cancelled"] = True
        elif x["kind"] == "retract":
            s["target"] = x["target"]
        sent.append(s)
    pending = [bounded(o) for o in state.get("pending") or []]
    out = {"v": 1, "session": state.get("session", session), "seq": state.get("seq")}
    if keys is not None:
        want = set(keys)
        out["sent"] = [s for s in sent if s["key"] in want]
        out["pending"] = [keyed(o) for o in pending if o["key"] in want]
        return out

    hidden, open_ = [], []
    for q in state.get("questions") or []:
        dismissal = next((x for x in live if x["kind"] == "dismiss" and x["id"] == q["id"]), None)
        if dismissal is not None:
            hidden.append({"id": q["id"], "key": dismissal["key"]})
            continue
        s = dict(q)
        s["references"] = [dict(r, changed=changed(r)) for r in q.get("references") or []]
        s["handle"] = q["id"] if q.get("revision") == 1 else "%s@%d" % (q["id"], q["revision"])
        ans = next((x for x in live if x["kind"] == "answer" and x["id"] == q["id"]), None)
        if ans is not None:
            s["queued"] = {"key": ans["key"], "kind": "answer", "picks": ans.get("picks", []),
                           "text": ans.get("text", ""), "images": ans.get("images", []),
                           "revision": ans["revision"], "by": ans["by"]}
            if "at" in ans:
                s["queued"]["at"] = ans["at"]
        open_.append(s)
    closed = {k: {f: c[f] for f in ("how", "at", "revision", "asker", "header", "receipt", "places", "deliveredAt")
                  if f in c}
              for k, c in (state.get("closed") or {}).items()}
    out.update({"open": open_, "hidden": hidden, "sent": sent, "pending": pending, "closed": closed})
    return out


def printable(v):
    """A value as the reader prints it: a lone UTF-16 surrogate in any string written as U+FFFD, so a record's string
    never makes `show` fail (I4)."""
    if isinstance(v, str):
        return "".join("\ufffd" if "\ud800" <= c <= "\udfff" else c for c in v) if _surrogate(v) else v
    if isinstance(v, list):
        return [printable(x) for x in v]
    if isinstance(v, dict):
        return {printable(k): printable(x) for k, x in v.items()}
    return v


def text(m):
    """`show` without --json: a question a block, then what is hidden and what waits for delivery."""
    lines = []
    for q in m["open"]:
        head = q["handle"]
        if isinstance(q.get("asker"), dict):
            head += "  asked by the subagent %s (%s)" % (q["asker"].get("name") or "?", q["asker"].get("agentId"))
        if q.get("header"):
            head += "  " + q["header"]
        lines.append(head)
        lines += ["  " + x for x in q["question"].splitlines() or [""]]
        for i, o in enumerate(q.get("options") or [], 1):
            lines.append("  %d. %s%s" % (i, o["label"], "  (recommended)" if o.get("recommended") else ""))
        if q.get("multiSelect"):
            lines.append("  (pick any number)")
        for r in q["references"]:
            where = r["path"] + (":%d-%d" % tuple(r["lines"]) if r.get("lines") else "")
            lines.append("  file: %s%s" % (where, "  (changed since asked)" if r.get("changed") else ""))
        if q.get("queued"):
            x = q["queued"]
            said = ", ".join(x["picks"])
            if x["text"]:
                said += (" · " if said else "") + json.dumps(x["text"], ensure_ascii=False)
            lines.append("  queued (%s): %s" % (x["key"], said))
        lines.append("")
    if not m["open"]:
        lines += ["no open questions", ""]
    if m["hidden"]:
        lines.append("dismissed, not yet applied: %s" % ", ".join(h["id"] for h in m["hidden"]))
    if m["pending"]:
        lines.append("accepted, not yet delivered: %s" % ", ".join(o["id"] for o in m["pending"]))
    return "\n".join(lines).rstrip("\n")


# ------------------------------------------------------------------ the door (I3)


def _now_ms():
    return S.now(ms=True)


def read_lines(data):
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError:
        S.die("sheet put: stdin is not UTF-8")
    lines = []
    for n, chunk in enumerate(raw.split("\n"), 1):     # JSON lines: LF alone ends one (U+2028 is text)
        if not chunk.strip():
            continue
        try:
            lines.append(loads(chunk))
        except ValueError as e:
            S.die("sheet put: line %d is not JSON: %s" % (n, e))
    if not lines:
        S.die("sheet put: no lines on stdin (one JSON object a line)")
    if len(lines) > DOOR_LINES:
        S.die("sheet put: %d lines; a call of the door takes at most %d" % (len(lines), DOOR_LINES))
    return lines


def _regular(path):
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


# What a record holds at each of its own paths: a link, or another kind of file, there would carry a write (a
# human's answer, the state, a reference's body) outside the record.
RECORD_KINDS = (("inbox.jsonl", stat.S_ISREG, "file"), ("state.json", stat.S_ISREG, "file"),
                ("refs", stat.S_ISDIR, "directory"), ("texts", stat.S_ISDIR, "directory"),
                ("uploads", stat.S_ISDIR, "directory"))


def record_problem(rec):
    """Why the record at `rec` cannot be written as one, by lstat (no link followed): the record directory, or a
    file or directory of it, is a link or another kind than the record keeps there. None when it is sound, or not
    there yet. Checked under the lock, before anything is written."""
    try:
        if not stat.S_ISDIR(os.lstat(rec).st_mode):
            return "the record %s is not a directory" % rec
    except FileNotFoundError:
        return None
    for rel, kind, name in RECORD_KINDS:
        try:
            mode = os.lstat(os.path.join(rec, rel)).st_mode
        except FileNotFoundError:
            continue
        if not kind(mode):
            return "the record's %s is not a %s" % (rel, name)
    return None


def append(session, lines):
    """Appends the lines under the lock, whole or not at all. Returns the lines as written."""
    batch = uuid.uuid4().hex if len(lines) > 1 else None
    stamped = []
    for n, line in enumerate(lines, 1):
        why = line_error(line)
        if why:
            S.die("sheet put: line %d refused: %s; nothing appended" % (n, why))
        line = dict(line)
        line.setdefault("at", _now_ms())
        if "revision" in line:
            line["revision"] = int(line["revision"])
        if batch is not None:
            line["batch"] = batch
        stamped.append({f: line[f] for f in FIELDS if f in line})
    rec = record_dir(session)
    try:
        with Lock(session):
            why = record_problem(rec)
            if why:
                S.die("sheet put: %s; nothing appended" % why, 1)
            try:
                state = _read_json(os.path.join(rec, "state.json"))
            except FileNotFoundError:
                S.die("no sheet: %s has no question sheet on this machine" % session, EXIT_NO_SHEET)
            uploads = os.path.join(rec, "uploads")
            for n, line in enumerate(stamped, 1):
                why = pick_error(line, state.get("questions") or [])
                if why is None and line.get("images") and os.path.islink(uploads):
                    why = "uploads/ is not a directory of the record"
                for img in line.get("images") or []:
                    if why is None and not _regular(os.path.join(rec, img)):
                        why = "%s is not a file in the record" % img
                if why:
                    S.die("sheet put: line %d refused: %s; nothing appended" % (n, why))
            data = "".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in stamped).encode()
            try:
                fd = os.open(os.path.join(rec, "inbox.jsonl"),
                             os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            except OSError as e:
                S.die("sheet put: the inbox could not be opened (%s); nothing appended" % e, 1)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    S.die("sheet put: the record's inbox.jsonl is not a file; nothing appended", 1)
                size = st.st_size
                if size and os.pread(fd, 1, size - 1) != b"\n":
                    data = b"\n" + data       # what an unfinished write left becomes a line of its own
                # One write; should it come back short, the rest follows while the lock is still held, so no drain
                # sees part of the call. Should the file refuse more, it is cut back to its length before the call:
                # nothing of the call stays, and the caller is told so.
                done = 0
                try:
                    while done < len(data):
                        n = os.write(fd, data[done:])
                        if n <= 0:
                            raise OSError(errno.EIO, "the inbox took no more bytes")
                        done += n
                    os.fsync(fd)
                except OSError as e:
                    os.ftruncate(fd, size)
                    os.fsync(fd)
                    S.die("sheet put: the inbox could not be written (%s); nothing appended" % e, 1)
            finally:
                os.close(fd)
    except Busy:
        S.die("sheet put: %s's sheet is busy (its lock was not had in %d s); send again" % (session, LOCK_WAIT_S),
              EXIT_BUSY)
    return stamped


def nudge(session, keys):
    """The session's verdicts for `keys` from its bridge's `sheet` op: {key: Verdict}, empty when none came (no
    bridge, a bridge that does not know the op, a session not under the sheet, no answer in time). The bridge's
    client is imported only when a socket is there, so a stopped session's door imports neither."""
    sock = os.path.join(S.root(), "bridge", session + ".sock")
    if not os.path.exists(sock):
        return {}
    C = S.control_module()
    try:
        r = C.post_command(sock, {"op": "sheet", "keys": keys}, NUDGE_WAIT_MS)
    except C.Unanswered:
        return {}
    if r is None:
        return {}
    status, out = r
    if status != 200 or not isinstance(out, dict) or not out.get("ok"):
        return {}
    verdicts = (out.get("result") or {}).get("verdicts")
    return {k: v for k, v in verdicts.items() if isinstance(v, dict) and isinstance(v.get("verdict"), str)} \
        if isinstance(verdicts, dict) else {}


def put(session, data, wait=True):
    lines = append(session, read_lines(data))
    keys = list(dict.fromkeys(x["key"] for x in lines))
    verdicts = nudge(session, keys) if wait else {}
    results = []
    for x in lines:
        v = verdicts.get(x["key"])
        results.append({"key": x["key"], "state": "queued"} if v is None
                       else {"key": x["key"], "state": v["verdict"], **v})
    return {"session": session, "results": results}


# ------------------------------------------------------------------ surfaces (X4; I8)

SURFACE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
HEARTBEAT_S = 30
SURFACE_URL_MAX = 2000


def surfaces_dir():
    return os.path.join(sheet_root(), "surfaces")


def _running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def surfaces(now=None):
    """Every well-formed registration, each with `alive`: its heartbeat at most 30 s old and its process running
    (I8, "Reading the registrations"). Only names ending in `.json` are read, so a writer's temporary file is not; a
    file that vanishes between the listing and the read, or is half-written, is passed over. The order is fixed:
    `mawsd` first, then the others by name, never the directory's. `url` is the origin with one trailing slash taken
    off, so a surface's link is `<url>/s/<session>`."""
    t = STEP().when(now or _now_ms())
    out = []
    try:
        names = sorted(os.listdir(surfaces_dir()))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            r = _read_json(os.path.join(surfaces_dir(), n))
        except (OSError, ValueError):     # gone since the listing, half-written, not JSON: not alive
            continue
        if not (isinstance(r, dict) and r.get("v") == 1 and isinstance(r.get("name"), str)
                and SURFACE_NAME_RE.fullmatch(r["name"]) and _count(r.get("pid"), 1)
                and isinstance(r.get("url"), str) and 0 < len(r["url"]) <= SURFACE_URL_MAX
                and r.get("reach") in ("local", "remote") and isinstance(r.get("heartbeatAt"), str)
                and TIME_RE.fullmatch(r["heartbeatAt"])):
            continue
        reg = {f: r[f] for f in ("v", "name", "pid", "url", "reach", "heartbeatAt")}
        if reg["url"].endswith("/") and len(reg["url"]) > 1:
            reg["url"] = reg["url"][:-1]
        try:                              # a well-shaped date that is no date, a pid the platform cannot hold
            age = (t - STEP().when(r["heartbeatAt"])).total_seconds()
            reg["alive"] = age <= HEARTBEAT_S and _running(int(r["pid"]))
        except (ValueError, OverflowError, OSError):
            reg["alive"] = False
        out.append((r["name"] != "mawsd", r["name"], n, reg))
    return [x[-1] for x in sorted(out, key=lambda x: x[:3])]


def suiting(regs, remote):
    """The first alive registration whose reach suits the session (a `local` one does not, under SSH_CONNECTION),
    or None; and how many are alive."""
    alive = [r for r in regs if r["alive"]]
    return next((r for r in alive if r["reach"] == "remote" or not remote), None), len(alive)


# ------------------------------------------------------------------ the step's shell (I5)

STAGED_AGE_S = 86400
CALL_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,256}$")
EVENT_KEYS = 200
RECEIPT = ".start-receipt.json"       # in the session's staging: what the last start found, for its retry
REMOVED = ".removed-"                 # in sheet/: a removed sheet detached, `.removed-<epoch s>-<uuid>`
REMOVED_AGE_S = 60                    # past this, a detached sheet no removal is deleting is deleted by the next
CALL_ENTRIES = 20                     # the tool's own limit (tool-input.schema.json), for a shell's inline call
GONE = ".gone-"                       # a staging directory made unavailable, deleted after the replace


def _call_id_ok(c):
    """A call id names a directory of the staging: never one of the names the staging keeps for itself."""
    return isinstance(c, str) and bool(CALL_ID_RE.fullmatch(c)) and not c.startswith((".", "start-"))


def STEP():
    return S.sibling_module("sminos_sheet_step")


def staging_dir(session):
    return os.path.join(sheet_root(), ".staging", session)


class Gone(Exception):
    pass


def _bad(code, error):
    return {"ok": False, "code": code, "error": error}


def _write_file(rec, rel, data):
    """A file of the record, whole or not at all: a temporary file in the record, synced, then replaced into place.
    A `.tmp-` file a death leaves is removed by the next step."""
    path = os.path.join(rec, rel)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = os.path.join(rec, ".tmp-" + uuid.uuid4().hex)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _sweep(rec, stage):
    """What a step that died left: `.tmp-` files in the record; staged files older than a day."""
    try:
        for n in os.listdir(rec):
            if n.startswith(".tmp-"):
                os.unlink(os.path.join(rec, n))
    except OSError:
        pass
    try:
        for n in os.listdir(stage):
            if n.startswith(GONE):
                _rmtree(os.path.join(stage, n))
    except OSError:
        pass
    cutoff = time.time() - STAGED_AGE_S
    for d, _, names in os.walk(stage):
        for n in names:
            p = os.path.join(d, n)
            try:
                if os.lstat(p).st_mtime < cutoff:
                    os.unlink(p)
            except OSError:
                pass


def _rmtree(path):
    shutil.rmtree(path, ignore_errors=True)


def _inside(base, rel):
    """A staged path named relative to `base`, refused when it leaves it."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        raise ValueError("a staged file is named relative to the staging")
    path = os.path.normpath(os.path.join(base, rel))
    if not path.startswith(os.path.normpath(base) + os.sep):
        raise ValueError("a staged file stays in the staging")
    return path


def _staged_json(base, rel):
    with open(_inside(base, rel), encoding="utf-8") as f:
        return loads(f.read())


def _capture(c, base):
    """A capture as the pure step takes it: its body as bytes, read from its staged file (a text's content, an
    image's base64) or given inline (`content`, `base64`)."""
    if not isinstance(c, dict) or c.get("ok") is False:
        return c
    c = dict(c)
    if "file" in c:
        with open(_inside(base, c.pop("file")), "rb") as f:
            raw = f.read()
        body = raw if c.get("kind") == "text" else base64.b64decode(raw, validate=True)
    elif isinstance(c.get("content"), str):
        body = c.pop("content").encode()
    elif isinstance(c.get("base64"), str):
        body = base64.b64decode(c.pop("base64"), validate=True)
    else:
        raise ValueError("a capture names its body: a staged file, content or base64")
    if c.get("kind") == "text":
        body.decode("utf-8")
    c["body"] = body
    return c


def _entry(item, base):
    if isinstance(item, dict) and "refused" in item:
        if not isinstance(item["refused"], str) or not item["refused"]:
            raise ValueError("a refused entry names its clause")
        return {"refused": item["refused"]}
    if isinstance(item, dict) and "file" in item:
        e, caps = _staged_json(base, item["file"]), item.get("captures", [])
    elif isinstance(item, dict) and "entry" in item:
        e, caps = item["entry"], item.get("captures", [])
    else:
        e, caps = item, []
    STEP_ = STEP()
    why = STEP_.entry_shape_error(e)
    if why:
        raise ValueError(why)
    if not isinstance(caps, list) or len(caps) != len(e.get("references") or []):
        raise ValueError("an entry has one capture for each reference")
    caps = [_capture(c, base) for c in caps]
    for c in caps:
        why = STEP_.capture_error(c)
        if why:
            raise ValueError(why)
    return {"entry": e, "captures": caps}


def _asker_ok(a):
    return a == "main" or (isinstance(a, dict) and set(a) == {"agentId", "name"} and isinstance(a["agentId"], str)
                           and 0 < len(a["agentId"]) <= 128 and isinstance(a["name"], str))


def _call_body(call, base):
    if not _asker_ok(call.get("asker")):
        raise ValueError("a call's asker is \"main\" or {agentId, name}")
    entries, withdraw = call.get("entries", []), call.get("withdraw", [])
    if not isinstance(entries, list) or not isinstance(withdraw, list) \
            or not all(isinstance(i, str) and ID_RE.fullmatch(i) for i in withdraw):
        raise ValueError("a call's entries are a list, its withdraw a list of ids")
    if len(entries) > CALL_ENTRIES:
        raise ValueError("a call has at most %d entries" % CALL_ENTRIES)
    return {"asker": call["asker"], "entries": [_entry(x, base) for x in entries], "withdraw": withdraw}


def _event_error(e):
    STEP_ = STEP()
    if not isinstance(e, dict) or e.get("event") not in STEP_.EVENTS:
        return "event is one of %s" % ", ".join(STEP_.EVENTS)
    if e.get("runner", "terminal") not in ("terminal", "maws"):
        return "runner is terminal or maws"
    if not isinstance(e.get("remote", False), bool):
        return "remote is a boolean"
    for f in ("acked", "keys"):
        if not (isinstance(e.get(f, []), list) and all(isinstance(x, str) for x in e.get(f, []))):
            return "%s is a list of strings" % f
    if len(e.get("keys", [])) > EVENT_KEYS:
        return "keys are at most %d" % EVENT_KEYS
    if "agents" in e:
        a = e["agents"]
        if not (isinstance(a, dict) and isinstance(a.get("running", []), list)
                and all(isinstance(x, str) for x in a.get("running", [])) and isinstance(a.get("direct", False), bool)):
            return "agents is {running: [agentId], direct}"
    if "context" in e and e["context"] != "compact":
        return "context is compact"
    if e["event"] in ("call", "settle"):
        c = e.get("call")
        if not (isinstance(c, dict) and _call_id_ok(c.get("callId"))
                and (c.get("floor") is None or _count(c["floor"], 0))):
            return "call is {callId, floor?}"
        if c["callId"] in e.get("acked", []):
            return "a call is not acknowledged in its own step"
    if e["event"] == "start":
        s = e.get("start")
        if not (isinstance(s, dict) and s.get("source") in STEP_.SOURCES
                and (s.get("floor") is None or _count(s["floor"], 0))
                and ("nonce" not in s or _call_id_ok(s["nonce"]))):
            return "start is {source, floor?, nonce?, today?}"
        t = s.get("today", {})
        if not (isinstance(t, dict) and isinstance(t.get("definite", False), bool)
                and isinstance(t.get("asks", []), list) and isinstance(t.get("floorUnknown", False), bool)):
            return "today is {definite, asks, floorUnknown?}"
    return None


def _ask(x, stage):
    a = _staged_json(stage, x["file"]) if isinstance(x, dict) and "file" in x else x
    if not (isinstance(a, dict) and isinstance(a.get("callId"), str) and a["callId"]
            and isinstance(a.get("askedAt"), str) and TIME_RE.fullmatch(a["askedAt"])
            and isinstance(a.get("questions"), list) and all(isinstance(q, dict) for q in a["questions"])):
        raise ValueError("an ask is {callId, askedAt, questions}")
    return a


def _normalize(event, stage, state):
    """The event with what the mod staged read in (I5), or given inline by a shell. Raises Gone for a call whose
    staging is gone (the mod acknowledged it, or a start cleared it), ValueError for input that is not the event's
    shape."""
    e = dict(event)
    if e["event"] in ("call", "settle"):
        e["call"] = dict(e["call"], floor=e["call"].get("floor"))
    if e["event"] == "call":
        c = e["call"]
        if any(f in c for f in ("asker", "entries", "withdraw")):
            e["call"] = dict(c, **_call_body(c, stage))
        elif state is not None and any(x["callId"] == c["callId"] for x in state["calls"]):
            pass                          # its outcome is recorded; what it staged is not read again
        else:
            base = os.path.join(stage, c["callId"])
            if not os.path.isdir(base):
                raise Gone()
            e["call"] = dict(c, **_call_body(_staged_json(base, "call.json"), base))
    if e["event"] == "start":
        s = dict(e["start"])
        t = dict(s.get("today") or {"definite": False, "asks": []})
        raw = t.get("asks") or []
        s["files"] = [x["file"] for x in raw if isinstance(x, dict) and isinstance(x.get("file"), str)]
        t["asks"] = [_ask(x, stage) for x in raw]
        s["today"] = t
        e["start"] = s
    return e


def _dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


ANSWER_MAX = 3 << 20


def _bounded(out):
    """An answer under 3 MiB as it is printed (I5): ready envelopes left out from the last recipient back, then
    closed entries from the oldest, then open questions from the newest, until it is. Each cut is estimated, then the
    whole is measured again."""
    v = out["view"]
    size = len(_dumps(out).encode())
    while size > ANSWER_MAX:
        over = size - ANSWER_MAX
        if v["ready"]:
            parts = [v["ready"]]
        elif v["closed"]:
            parts = [v["closed"]]
        elif v["open"]:
            parts = [v["open"]]
        elif v["answered"]:
            parts = [v["answered"]]
        else:
            break
        part = parts[0]
        while over > 0 and part:
            if isinstance(part, dict):
                k = next(iter(part))
                over -= len(_dumps({k: part.pop(k)}).encode())
            else:
                over -= len(_dumps(part.pop()).encode())
        size = len(_dumps(out).encode())
    # With the view gone, what is left has a hard maximum far under the bound: a call's result (RESULT_MAX), the
    # context (I7's budget), at most 200 keys in `before` and in `verdicts`, and what one drain applied.
    assert size <= ANSWER_MAX, "the effects alone are %d bytes" % size
    return out


def run_step(session, raw, now=None, tz=None):
    """One step (I5): the event's JSON in, the answer out. `now` and `tz` are the clock and the zone a test fixes;
    the command passes neither."""
    try:
        event = loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (ValueError, UnicodeDecodeError) as e:
        return _bad("bad-event", "the event is not JSON: %s" % e)
    why = _event_error(event)
    if why:
        return _bad("bad-event", why)
    now = now or _now_ms()
    try:
        with Lock(session):
            return _step_locked(session, event, now, tz)
    except Busy:
        return _bad("busy", "the sheet's lock was not had in %d s" % LOCK_WAIT_S)


def _receipt(stage, event):
    """What the last start found that the record cannot give again (an empty sheet, what it imported), when this start
    is that start ordered again: its nonce is the receipt's. A start with no nonce (a shell's) is always new."""
    nonce = event["start"].get("nonce")
    if nonce is None:
        return None
    try:
        r = _read_json(os.path.join(stage, RECEIPT))
    except (OSError, ValueError):
        return None
    return r if isinstance(r, dict) and r.get("nonce") == nonce else None


def _hide(stage, name):
    """A staging directory made unavailable at once (renamed), to be deleted after the replace."""
    try:
        os.rename(os.path.join(stage, name), os.path.join(stage, GONE + uuid.uuid4().hex))
    except FileNotFoundError:
        pass


def _start_dirs(norm):
    """The start-<nonce> directories this start's asks were staged in: kept for its retry until the next start."""
    keep = {x.split("/", 1)[0] for x in norm["start"].get("files", [])}
    if "nonce" in norm["start"]:
        keep.add("start-" + norm["start"]["nonce"])
    return keep


def _step_locked(session, event, now, tz):
    STEP_ = STEP()
    rec, stage = record_dir(session), staging_dir(session)
    why = record_problem(rec)
    if why:
        # Nothing read through it, nothing written: the record is not one this step can keep.
        return _bad("bad-record", why)
    _sweep(rec, stage)
    path = os.path.join(rec, "state.json")
    try:
        state = _read_json(path)
    except FileNotFoundError:
        state = None
    name = event["event"]
    if state is None and name != "start":
        return _bad("no-record", "%s has no question sheet: only a start makes one" % session)
    try:
        norm = _normalize(event, stage, state)
    except Gone:
        return _bad("gone", "call %s: its staging is gone (acknowledged, or cleared by a start)"
                    % event["call"]["callId"])
    except (OSError, ValueError) as e:
        return _bad("bad-event", str(e))
    if name == "start":
        again = _receipt(stage, event)
        if again is not None:
            norm["start"]["again"] = again
    data = b""
    if state is not None:
        try:
            with open(os.path.join(rec, "inbox.jsonl"), "rb") as f:
                f.seek(state["inbox"]["offset"])
                data = f.read()
        except FileNotFoundError:
            pass
    regs = surfaces(now)
    surface, alive = suiting(regs, event.get("remote", False))
    new, fx, writes = STEP_.apply(state, data, norm, now, session, surface, tz)
    unchanged = state is not None and dict(new, seq=state["seq"]) == state
    new["seq"] = state["seq"] if unchanged else (state["seq"] if state is not None else 0) + 1

    # The whole answer is composed before anything is written: no composer's failure follows a committed state.
    running = (event.get("agents") or {}).get("running") or []
    where = os.path.abspath(rec)
    if name == "start" or event.get("context") == "compact":
        after = {"resume": "a resume"}.get(norm["start"]["source"], "a start") if name == "start" \
            else "a compaction"
        st = fx.get("start") or {}
        fx["context"] = STEP_.context(new, session, after, st.get("empty"),
                                      floor_known=name == "start" and norm["start"].get("floor") is not None,
                                      imported=[x["callId"] for x in st.get("imported", [])])
    view = STEP_.view(new, event.get("runner", "terminal"), where, surface, alive, tz, running)
    out = _bounded({"ok": True, "seq": new["seq"], "view": view, "effects": fx})

    # What the replace forgets is made unavailable first: an acknowledged call's staging, and at a start every call's.
    # A death between the two leaves the outcome in `calls`, which answers a late step of that call; after the
    # replace, a late step finds no staging and is gone.
    for call_id in event.get("acked") or []:
        if _call_id_ok(call_id):
            _hide(stage, call_id)
    if name == "start":
        keep = _start_dirs(norm)
        try:
            listed = os.listdir(stage)
        except FileNotFoundError:
            listed = []
        for n in listed:
            if n != RECEIPT and not n.startswith(GONE) and n not in keep:
                _hide(stage, n)
        if "nonce" in norm["start"]:
            os.makedirs(stage, mode=0o700, exist_ok=True)
            _write_file(stage, RECEIPT, _dumps({"nonce": norm["start"]["nonce"], "empty": fx["start"]["empty"],
                                                "imported": fx["start"]["imported"]}).encode())
        else:
            try:
                os.unlink(os.path.join(stage, RECEIPT))
            except FileNotFoundError:
                pass

    if state is None:
        os.makedirs(rec, mode=0o700, exist_ok=True)
        if not os.path.exists(os.path.join(rec, "inbox.jsonl")):
            _write_file(rec, "inbox.jsonl", b"")
    for rel, body in writes.items():
        p = os.path.join(rec, rel)
        if not (os.path.isfile(p) and os.path.getsize(p) == len(body)):
            _write_file(rec, rel, body)
    if not unchanged:
        _write_file(rec, "state.json", _dumps(new).encode())
    try:
        for n in os.listdir(stage):
            if n.startswith(GONE):
                _rmtree(os.path.join(stage, n))
    except FileNotFoundError:
        pass
    return out


def probe(session, remote=False):
    """What the start choice asks of a record (I5, I8): a few hundred bytes whatever the record holds."""
    surface, alive = suiting(surfaces(), remote)
    out = {"record": False, "open": 0, "pending": 0, "queued": 0,
           "surface": None if surface is None else {f: surface[f] for f in ("name", "url", "reach")},
           "surfaces": alive}
    got = snapshot(session)
    if got is not None:
        state, tail = got
        out.update(record=True, open=len(state.get("questions") or []), pending=len(state.get("pending") or []),
                   queued=len(queued_lines(state, tail)))
    return out


# ------------------------------------------------------------------ the command's acts on a sheet (I3)

HANDLE_RE = re.compile(r"^(q[1-9][0-9]{0,8})(?:@([1-9][0-9]*))?$")
IMAGE_EXTS = ("png", "jpg", "jpeg", "gif", "webp")


def _new_key():
    return "cli-" + uuid.uuid4().hex[:16]


def _own(session, verb):
    """U12: a session does not act on its own sheet; its human does, from a surface."""
    if os.environ.get("CLAUDE_CODE_SESSION_ID") == session:
        S.die("sheet %s: a session does not %s its own sheet; its human does, from a surface" % (verb, verb), 2)


def _model_or_die(session, verb):
    try:
        m = model(session)
    except Busy:
        S.die("sheet %s: %s's record kept changing while it was read; try again" % (verb, session), EXIT_BUSY)
    if m is None:
        S.die("no sheet: %s has no question sheet on this machine" % session, EXIT_NO_SHEET)
    return m


def _resolve_pick(q, word):
    """A pick as `answer` takes one: a place among the options (from 1), or a label in any case."""
    labels = [o["label"] for o in q.get("options") or []]
    w = word.strip()
    if re.fullmatch(r"[0-9]+", w) and 1 <= int(w) <= len(labels):
        return labels[int(w) - 1]
    exact = [x for x in labels if x == w]
    folded = [x for x in labels if x.lower() == w.lower()]
    if exact or len(folded) == 1:
        return (exact or folded)[0]
    return None


def cli_answer(session, handle, picks, text):
    """The line `answer` sends, read against what the human saw: a bare id only at revision 1, a handle's revision
    the current one."""
    m = _model_or_die(session, "answer")
    hm = HANDLE_RE.fullmatch(handle)
    if not hm:
        S.die("sheet answer: %s is no question's handle (q7, or q7@2 after a revise)" % handle, 2)
    id_, rev = hm.group(1), int(hm.group(2)) if hm.group(2) else 1
    q = next((x for x in m["open"] if x["id"] == id_), None)
    if q is None:
        hidden = any(h["id"] == id_ for h in m["hidden"])
        S.die("sheet answer: %s is not open%s" % (id_, " (a dismissal of it is queued)" if hidden else ""), 2)
    if rev != q["revision"]:
        S.die("sheet answer: %s is at revision %d: show it again, then answer %s@%d"
              % (id_, q["revision"], id_, q["revision"]), 2)
    labels = []
    for w in picks:
        label = _resolve_pick(q, w)
        if label is None:
            S.die("sheet answer: %s has no option %s at revision %d" % (q["handle"], json.dumps(w, ensure_ascii=False),
                                                                       q["revision"]), 2)
        labels.append(label)
    if len(labels) > 1 and not q.get("multiSelect"):
        S.die("sheet answer: %s takes one pick" % q["handle"], 2)
    if not labels and not text:
        S.die("sheet answer: give --pick or --text", 2)
    line = {"v": 1, "key": _new_key(), "kind": "answer", "id": id_, "revision": q["revision"]}
    if labels:
        line["picks"] = labels
    if text:
        line["text"] = text
    line["by"] = "cli"
    return line


def copy_upload(session, src):
    """An image copied into the record's uploads/ under a name of its own, for an answer to name."""
    ext = os.path.splitext(src)[1][1:].lower()
    if ext not in IMAGE_EXTS:
        S.die("sheet answer: --image takes a %s file" % ", ".join(IMAGE_EXTS), 2)
    if not os.path.isfile(src):
        S.die("sheet answer: %s is not a file" % src, 2)
    rec = record_dir(session)
    why = record_problem(rec)
    if why:
        S.die("sheet answer: %s; nothing copied" % why, 1)
    if not os.path.isfile(os.path.join(rec, "state.json")):
        S.die("no sheet: %s has no question sheet on this machine" % session, EXIT_NO_SHEET)
    uploads = os.path.join(rec, "uploads")
    if os.path.islink(uploads):
        S.die("sheet answer: uploads/ is not a directory of the record", 2)
    os.makedirs(uploads, mode=0o700, exist_ok=True)
    name = "uploads/cli-%s.%s" % (uuid.uuid4().hex[:16], ext)
    tmp = os.path.join(uploads, ".tmp-" + uuid.uuid4().hex)
    shutil.copyfile(src, tmp)
    os.replace(tmp, os.path.join(rec, name))
    return name


def _send(session, lines):
    """Lines through the door, as one call: the door's own output, printed."""
    data = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines).encode()
    print(json.dumps(put(session, data), ensure_ascii=False))


def _removed_leftovers(now_s):
    """Detached sheets an earlier removal left (it died, or could not delete them): deleted once older than a minute,
    so a removal in progress elsewhere keeps its own."""
    root = sheet_root()
    try:
        names = os.listdir(root)
    except FileNotFoundError:
        return
    for n in names:
        if n.startswith(REMOVED):
            try:
                at = int(n[len(REMOVED):].split("-", 1)[0])
            except ValueError:
                at = 0
            if now_s - at > REMOVED_AGE_S:
                shutil.rmtree(os.path.join(root, n), ignore_errors=True)


def remove(session, cleared=False):
    """A stopped session's record and its staging (I1, M2). Liveness is checked before the lock and again under it (a
    session resumed while this waited); under the lock the staging, then the record, are detached, each by one rename
    inside sheet/, so no reader or step sees part of a removal, and a record that cannot be detached gets its staging
    back; then they are deleted, and what could not be is said (the next removal deletes it). The lock file stays."""
    if not cleared and S.session_running(session):
        S.die("sheet remove: %s runs; its sheet goes when it stops (or with --cleared, after a /clear)" % session, 2)
    _removed_leftovers(int(time.time()))
    detached = []
    try:
        with Lock(session):
            rec = record_dir(session)
            # The record directory itself a link (or not a directory): refused before anything is detached, every
            # path left as it was. A real one holding a link is removed: the removal unlinks the link, never what it
            # points to (rmtree follows no link).
            try:
                is_dir = stat.S_ISDIR(os.lstat(rec).st_mode)
            except FileNotFoundError:
                is_dir = True
            if not is_dir:
                S.die("sheet remove: the record %s is not a directory; nothing removed" % rec, 1)
            if not os.path.isfile(os.path.join(rec, "state.json")):
                S.die("no sheet: %s has no question sheet on this machine" % session, EXIT_NO_SHEET)
            if not cleared and S.running_now(session):
                S.die("sheet remove: %s started while this waited; its sheet stays" % session, 2)
            for d in (staging_dir(session), rec):
                if os.path.exists(d):
                    to = os.path.join(sheet_root(), "%s%d-%s" % (REMOVED, int(time.time()), uuid.uuid4().hex))
                    try:
                        os.rename(d, to)
                    except OSError as e:
                        for back, was in reversed(detached):
                            os.rename(was, back)
                        S.die("sheet remove: %s could not be detached (%s); the sheet is still there" % (d, e), 1)
                    detached.append((d, to))
    except Busy:
        S.die("sheet remove: %s's sheet is busy; try again" % session, EXIT_BUSY)
    left = []
    for _, d in detached:
        try:
            shutil.rmtree(d)
        except OSError as e:
            left.append("%s (%s)" % (d, e))
    if left:
        S.die("sheet remove: %s's sheet is removed, but these could not be deleted (the next removal deletes them): "
              "%s" % (session, "; ".join(left)), 1)


PREFIX_RE = re.compile(r"^[0-9a-f][0-9a-f-]{7,34}$")


def recorded(prefix):
    """The sessions with a record under sheet/ whose id begins with `prefix`, in order."""
    try:
        names = os.listdir(sheet_root())
    except OSError:
        return []
    return sorted(n for n in names if n.startswith(prefix) and S.UUID_RE.fullmatch(n)
                  and os.path.isfile(os.path.join(record_dir(n), "state.json")))


def resolve(a, verb):
    """The session a verb names: --session as given (no registry read), else the member as the control verbs
    resolve one; where no member matches, a unique prefix of 8 characters or more of a session that has a record
    (what the band prints, `sminos sheet show <first 8>`, M5: a sheet's session need not be a member)."""
    if bool(a.member) == bool(a.session):
        S.die("usage: sminos sheet %s (<member> | --session <id>)" % verb)
    if a.session:
        if not S.UUID_RE.fullmatch(a.session):
            S.die("sheet %s: --session takes an engine session id" % verb)
        return a.session
    target = None
    if PREFIX_RE.fullmatch(a.member):
        target = S.find_target(a.member)
        found = recorded(a.member) if target[0] == "none" else []
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            S.die("sheet %s: '%s' begins more than one sheet's session: %s; name it whole with --session"
                  % (verb, a.member, ", ".join(found)), S.EXIT_UNKNOWN)
    return S.bridge_module().watch_session(a.member, target)


def _split_who(a, verb):
    """For a verb whose other words follow the session (`dismiss`): the member is the first word unless --session
    names the session."""
    words = list(a.words)
    if not a.session:
        if not words:
            S.die("usage: sminos sheet %s (<member> | --session <id>) ..." % verb)
        a.member = words.pop(0)
    else:
        a.member = ""
    return resolve(a, verb), words


def cmd_sheet(a):
    op = getattr(a, "sheet_op", None)
    if op == "put":
        session = resolve(a, "put")
        print(json.dumps(put(session, sys.stdin.buffer.read(), wait=not a.no_wait), ensure_ascii=False))
        return
    if op == "show":
        session = resolve(a, "show")
        keys = None
        if a.keys is not None:
            if not a.json:
                S.die("sheet show: --keys goes with --json")
            keys = [k for k in a.keys.split(",") if k]
            if not keys or len(keys) > KEYS_MAX or not all(KEY_RE.fullmatch(k) for k in keys):
                S.die("sheet show: --keys takes 1 to %d keys, comma-separated" % KEYS_MAX)
        try:
            m = model(session, keys)
        except Busy:
            S.die("sheet show: %s's record kept changing while it was read; read again" % session, EXIT_BUSY)
        if m is None:
            S.die("no sheet: %s has no question sheet on this machine" % session, EXIT_NO_SHEET)
        m = printable(m)
        print(json.dumps(m, ensure_ascii=False) if a.json else text(m))
        return
    if op == "answer":
        session = resolve(a, "answer")
        _own(session, "answer")
        if a.text and len(a.text) > 20000:
            S.die("sheet answer: --text is at most 20,000 characters", 2)
        if len(a.image) > 8:
            S.die("sheet answer: at most 8 images", 2)
        line = cli_answer(session, a.handle, a.pick, a.text or "")     # refused before anything is copied
        images = [copy_upload(session, f) for f in a.image]
        if images:
            by = line.pop("by")
            line.update(images=images, by=by)
        _send(session, [line])
        return
    if op == "dismiss":
        session, ids = _split_who(a, "dismiss")
        _own(session, "dismiss")
        if not ids:
            S.die("usage: sminos sheet dismiss (<member> | --session <id>) <q>...")
        m = _model_or_die(session, "dismiss")
        listed = {q["id"] for q in m["open"]} | {h["id"] for h in m["hidden"]}
        lines = []
        for w in ids:
            hm = HANDLE_RE.fullmatch(w)
            if not hm:
                S.die("sheet dismiss: %s is no question's id" % w, 2)
            if hm.group(1) not in listed:
                S.die("sheet dismiss: %s is not open" % hm.group(1), 2)
            lines.append({"v": 1, "key": _new_key(), "kind": "dismiss", "id": hm.group(1), "by": "cli"})
        _send(session, lines)
        return
    if op == "retract":
        session = resolve(a, "retract")
        _own(session, "retract")
        if not KEY_RE.fullmatch(a.target):
            S.die("sheet retract: %s is no key" % a.target, 2)
        _send(session, [{"v": 1, "key": _new_key(), "kind": "retract", "target": a.target, "by": "cli"}])
        return
    if op == "remove":
        session = resolve(a, "remove")
        remove(session, cleared=a.cleared)
        print("removed %s's question sheet" % session)
        return
    if op == "surfaces":
        regs = surfaces()
        if a.json:
            print(json.dumps({"surfaces": regs}, ensure_ascii=False))
        else:
            print("\n".join("%s  %s  %s  %s" % (r["name"], r["url"], r["reach"], "alive" if r["alive"] else "stale")
                            for r in regs) or "no surface registered")
        return
    if op in ("step", "probe"):
        if not a.session or not S.UUID_RE.fullmatch(a.session):
            S.die("sheet %s: --session takes an engine session id" % op)
        if op == "step":
            print(_dumps(run_step(a.session, sys.stdin.buffer.read())))
        else:
            try:
                out = probe(a.session, remote=a.remote)
            except Busy:
                S.die("sheet probe: %s's record kept changing while it was read" % a.session, EXIT_BUSY)
            print(json.dumps(out, ensure_ascii=False))
        return
    S.die("usage: sminos sheet show|answer|dismiss|retract|put|remove (<member> | --session <id>) ... | surfaces")
