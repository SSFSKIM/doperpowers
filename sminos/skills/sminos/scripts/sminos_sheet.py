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


SPACED = re.compile("\r\n|[\t\n\x0b\x0c\r\x85\u2028\u2029]")   # sheet-model.tsx's terminalText, as written there
CONTROLS = re.compile("[\x00-\x1f\x7f-\x9f]")


def terminal_safe(v):
    """A string written by someone else as a terminal may print it, as the mod draws one (sheet-model.tsx's
    terminalText): CRLF one break, each line break and a tab a space, every other C0, DEL and C1 character (ESC
    among them, so no escape sequence) taken out. For a human-facing print only; what is stored, and every JSON
    output, keep the string as written."""
    return CONTROLS.sub("", SPACED.sub(" ", v))


def text(m):
    """`show` without --json: a question a block, then what is hidden and what waits for delivery. What a model or a
    person wrote is printed terminal_safe, one line each, but for a question's own lines, kept and indented."""
    lines = []
    for q in m["open"]:
        head = q["handle"]
        if isinstance(q.get("asker"), dict):
            head += "  asked by the subagent %s (%s)" % (terminal_safe(q["asker"].get("name") or "?"),
                                                         terminal_safe(str(q["asker"].get("agentId"))))
        if q.get("header"):
            head += "  " + terminal_safe(q["header"])
        lines.append(head)
        # A question's own lines (LF) stay, where `show` is read in full; each after the first is indented under
        # it, so none can start a line that reads as a field or another question. A CR is dropped.
        first, *more = q["question"].replace("\r", "").split("\n")
        lines.append("  " + terminal_safe(first))
        lines += ["    " + terminal_safe(x) for x in more]
        for i, o in enumerate(q.get("options") or [], 1):
            lines.append("  %d. %s%s" % (i, terminal_safe(o["label"]),
                                         "  (recommended)" if o.get("recommended") else ""))
        if q.get("multiSelect"):
            lines.append("  (pick any number)")
        for r in q["references"]:
            where = r["path"] + (":%d-%d" % tuple(r["lines"]) if r.get("lines") else "")
            lines.append("  file: %s%s" % (terminal_safe(where), "  (changed since asked)" if r.get("changed") else ""))
        if q.get("queued"):
            x = q["queued"]
            said = ", ".join(terminal_safe(p) for p in x["picks"])
            if x["text"]:
                # Cleaned, then quoted: a line break is a space, never a literal \n.
                said += (" · " if said else "") + json.dumps(terminal_safe(x["text"]), ensure_ascii=False)
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


def append(session, lines, progress=None):
    """Appends the lines under the lock, whole or not at all. Returns the lines as written. `progress` (a dict), when
    given, holds `writing` True from the first byte written until the call is cut back again: a caller interrupted
    with it True cannot know whether the lines stay."""
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
                size, offset = st.st_size, state["inbox"]["offset"]
                if size < offset:
                    # Shorter than the offset the step committed (an unclean stop kept its last appends from the
                    # disk, every one of them applied): the call goes at the offset, the bytes before it blank
                    # lines, so the step reads it, and only it.
                    data = b"\n" * (offset - size) + data
                elif size > offset and os.pread(fd, 1, size - 1) != b"\n":
                    # What an unfinished write left becomes a line of its own. One below the offset (an inbox the
                    # step read from its cut end) is never read: the call goes at the offset as it is.
                    data = b"\n" + data
                # One write; should it come back short, the rest follows while the lock is still held, so no drain
                # sees part of the call. Should the file refuse more, it is cut back to its length before the call:
                # nothing of the call stays, and the caller is told so.
                done = 0
                if progress is not None:
                    progress["writing"] = True
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
                    if progress is not None:
                        progress["writing"] = False
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
    return told(session, append(session, read_lines(data)), wait)


def told(session, lines, wait=True):
    """What `put` prints for lines the door appended: each key's verdict from the session's bridge, `queued` for
    one none came back for."""
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


def _holds(path, body):
    """Whether the file at `path` holds `body`, read whole (a body is a few MiB at most): a `refs/` or `texts/`
    file named by its digest is reused only when it is those bytes, since an unclean stop can leave one damaged
    at its full length."""
    try:
        if os.path.getsize(path) != len(body):
            return False
        with open(path, "rb") as f:
            return f.read() == body
    except OSError:
        return False


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
            if n == RECEIPT and d == stage:
                continue                  # the last start's receipt outlives the expiry: its count is a witness's
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
    data, read, size = b"", state, 0
    try:
        with open(os.path.join(rec, "inbox.jsonl"), "rb") as f:
            size = os.fstat(f.fileno()).st_size
            if state is not None:
                if state["inbox"]["offset"] > size:
                    # Everything below a committed offset was applied: an inbox shorter than it lost appends an
                    # unclean stop kept from the disk, and is read from its end (the door appends from the offset).
                    state = dict(state, inbox=dict(state["inbox"], offset=size))
                f.seek(state["inbox"]["offset"])
                data = f.read()
    except FileNotFoundError:
        pass
    regs = surfaces(now)
    surface, alive = suiting(regs, event.get("remote", False))
    new, fx, writes = STEP_.apply(state, data, norm, now, session, surface, tz)
    if state is None:
        # The door never appends without a state: an inbox already there is what an earlier record left, applied
        # or not, and none of it is this record's.
        new["inbox"]["offset"] = size
    unchanged = read is not None and dict(new, seq=read["seq"]) == read
    new["seq"] = read["seq"] if unchanged else (read["seq"] if read is not None else 0) + 1

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
        # Every start is counted (`started`, past the last count and never below the start's time in ms, so a
        # receipt lost or unreadable starts above any count a witness took): a /clear's witness binds it (start_mark).
        prior = _start_count(stage)
        counted = {"started": max((prior or 0) + 1, int(STEP_.when(now).timestamp() * 1000))}
        os.makedirs(stage, mode=0o700, exist_ok=True)
        if "nonce" in norm["start"]:
            _write_file(stage, RECEIPT, _dumps(dict({"nonce": norm["start"]["nonce"], "empty": fx["start"]["empty"],
                                                     "imported": fx["start"]["imported"]}, **counted)).encode())
        else:
            _write_file(stage, RECEIPT, _dumps(counted).encode())   # no nonce: no retry of it is known, only its count

    if state is None:
        os.makedirs(rec, mode=0o700, exist_ok=True)
        if not os.path.exists(os.path.join(rec, "inbox.jsonl")):
            _write_file(rec, "inbox.jsonl", b"")
    for rel, body in writes.items():
        if not _holds(os.path.join(rec, rel), body):
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


# ------------------------------------------------------------------ the project log (I12)

LOG_REMOVED = "removed with its sheet"    # the closing a removal writes for a question still open


class LogFailed(Exception):
    """The project log refused what the projection gave it: what it took is no longer owed, the rest is."""


def has_record(session):
    return os.path.isfile(os.path.join(record_dir(session), "state.json"))


def _log_problem(rec):
    """Why the projection may not read and replace the record's state (no link followed), or None."""
    try:
        if not stat.S_ISDIR(os.lstat(rec).st_mode):
            return "the record %s is not a directory" % rec
        if not stat.S_ISREG(os.lstat(os.path.join(rec, "state.json")).st_mode):
            return "the record's state.json is not a file"
    except FileNotFoundError:
        return None
    return None


def _question_from(project, session, src, here):
    """The `from` a question's later event carries: the question's own, as the log holds it (close_questions does
    the same), else the alias the session goes by where it is now, else its short id."""
    for store in ("log", S.HOST_STORE):
        for e in S._own_events(project, session, store):
            if e["kind"] == "question" and e.get("src") == src and e.get("from"):
                return e["from"]
    now = here()
    return now[1] if now is not None and now[0].id == project.id else session[:8]


def _read_state(rec):
    try:
        return _read_json(os.path.join(rec, "state.json"))
    except FileNotFoundError:
        return None


INCARNATION = ".incarnation"
NONCE_RE = re.compile(rb"[0-9a-f]{32}\n?")   # what a minter writes: 32 hex digits and a newline
NONCE_READ = 64                               # bytes of `.incarnation` read: a minted one is 33


def record_identity(rec, mint=False):
    """Which record a path names, so a projection, a removal or a /clear's note acts on the record it began from and
    never on one made at the same path since: (st_dev, st_ino, nonce) of the record directory, or None for none
    there. A filesystem may give a new directory the inode of one just removed, so the nonce, `.incarnation` in the
    record (not in state.json, and no part of what a step writes), tells them apart: minted once, by the first
    reader that binds to the record (`mint`, and smns-cleared.sh), with a no-clobber link, so concurrent minters
    read one. The nonce is "" while none is minted, and None when `.incarnation` holds anything but the minted 32
    hex digits or cannot be read (an unclean stop can leave it empty): not known, never an identity (same_record).
    At most NONCE_READ bytes are read, as bytes."""
    try:
        st = os.lstat(rec)
    except FileNotFoundError:
        return None
    path = os.path.join(rec, INCARNATION)
    if mint and stat.S_ISDIR(st.st_mode) and not os.path.lexists(path):
        tmp = os.path.join(rec, ".tmp-" + uuid.uuid4().hex)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(uuid.uuid4().hex + "\n")
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
        finally:
            os.unlink(tmp)
    try:
        with open(path, "rb") as f:
            raw = f.read(NONCE_READ)
        nonce = raw[:32].decode("ascii") if NONCE_RE.fullmatch(raw) else None
    except FileNotFoundError:
        nonce = ""
    except OSError:
        nonce = None
    return st.st_dev, st.st_ino, nonce


IDENTITY_RE = re.compile(r"([0-9]+):([0-9]+):([0-9a-f]{32})")


def identity_text(identity):
    """An identity as a witness writes it (`sheet witness`, smns-cleared.sh): `<st_dev>:<st_ino>:<nonce>`."""
    return "%d:%d:%s" % identity


def parse_identity(text):
    """A witness's identity, or None when the text is no identity (no minted nonce in it)."""
    m = IDENTITY_RE.fullmatch(text or "")
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else None


WITNESS_RE = re.compile(r"([0-9]+):([0-9]+):([0-9a-f]{32}):([0-9]{0,20})")


def _start_count(stage):
    """How far the record's starts were counted (the receipt's `started`, which every start raises): 0 for no
    receipt, or one written before starts were counted; None when the receipt cannot be read."""
    try:
        r = _read_json(os.path.join(stage, RECEIPT))
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    n = r.get("started", 0)
    return n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None


def start_mark(session):
    """Which start the session's record last had, as a /clear's witness binds it: the count of its starts, from the
    receipt in the staging (every start raises it, a replay of an earlier start's nonce included); "" for none
    counted; None when it cannot be read (not known: no witness, and a removal keeps)."""
    n = _start_count(staging_dir(session))
    return None if n is None else str(n) if n else ""


def witness_text(identity, start):
    """A /clear's witness as `sheet witness` prints it: the record's identity and the start it had,
    `<st_dev>:<st_ino>:<nonce>:<start count>`."""
    return "%s:%s" % (identity_text(identity), start)


def parse_witness(text):
    """A /clear's witness: (identity, start count), or None when the text is none."""
    m = WITNESS_RE.fullmatch(text or "")
    return ((int(m.group(1)), int(m.group(2)), m.group(3)), m.group(4)) if m else None


def same_record(identity, witnessed):
    """Whether the record whose identity is `identity` (record_identity, now) is the one `witnessed` was: True only
    when both hold a minted nonce and agree; False when it is known not to be (no record there, another directory,
    another nonce, or no nonce where the witnessed record had one: a nonce is never taken away); None when it
    cannot be told (a nonce not read, or neither minted: the inode alone tells nothing). Only True acts."""
    if identity is None:
        return False
    if not isinstance(witnessed, tuple) or len(witnessed) != 3:
        return None
    if tuple(identity[:2]) != tuple(witnessed[:2]):
        return False
    now, then = identity[2], witnessed[2]
    if now and then:
        return now == then
    if now == "" and then:
        return False
    return None


def project_log(session, here=None, closing=False, rec=None):
    """The projection (I12): what the record at `rec` (the session's own by default; a removal's, detached) owes the
    project log, appended under the session's writer through append_host, whose (kind, src) rule appends nothing
    twice, then taken off `log.owed` by a replace under the lock. Each question's destination is decided once and
    recorded before anything of it is appended (`log.projects`, first decision kept, under the lock): the project
    the session is in now and a member of (`here(session)`: (project, alias), or None while it is in none or no
    member: the question waits, and every later event of it), so a retry after a death, or a projection overlapping
    a move to another project, sends it and every later event of it to the same project. `closing` (a removal): a
    closing for each question still open goes after what is owed, and is owed nothing; a destination recorded but
    not known here any more is then a debt (LogFailed), where otherwise it waits. The lock is held to read and to
    replace, never while the log is written. Returns {written, owed}, None for no record; raises LogFailed when the
    log refused a project's events (the others are taken, after the replace) or the session's place could not be
    read. Each reread under the lock is of the record the projection began from (its directory's identity, a
    positive match; a detached record, whose path is never made again, also when it cannot be told): one removed
    meanwhile, one made at its path since, and one that cannot be told from such, are changed in nothing."""
    here_of = here or (lambda s: S.held_member(s))
    rec = rec or record_dir(session)
    detached = rec != record_dir(session)

    def still(identity):
        # The record it began from: a positive match. A detached record's path is its own (`.removed-<epoch>-<uuid>`,
        # never made again), so there one whose nonce was never minted, or cannot be read, is still it.
        same = same_record(identity, began)
        return same is True or detached and same is None
    with Lock(session):
        why = _log_problem(rec)
        if why:
            raise LogFailed(why)
        began = record_identity(rec, mint=rec == record_dir(session))
        state = _read_state(rec)
        if state is None:
            return None
        owed = [dict(e) for e in state["log"]["owed"]]
        projects = dict(state["log"]["projects"])
        if closing:
            owed += [{"kind": "answered", "src": STEP().src(session, q["id"]), "text": LOG_REMOVED,
                      "closed": "removed"} for q in state["questions"]]
    if not owed:
        return {"written": 0, "owed": 0}
    cache = []

    def now():
        if not cache:
            try:
                cache.append(here_of(session))
            except (OSError, S.LockBusy) as e:
                raise LogFailed("where the session is could not be read: %s" % e)
        return cache[0]

    def id_of(e):
        return e["src"].rsplit(":", 1)[1]
    unplaced = [id_of(e) for e in owed if e["kind"] == "question" and id_of(e) not in projects]
    if unplaced and now() is not None:
        with Lock(session):
            state = _read_state(rec) if still(record_identity(rec)) else None
            if state is None:
                return None
            kept = state["log"]["projects"]
            placed = {i: now()[0].id for i in unplaced if i not in kept}
            if placed:
                kept.update(placed)
                state["seq"] += 1
                _write_file(rec, "state.json", _dumps(state).encode())
            projects = dict(kept)
    batches, froms, failed, debts = {}, {}, [], []
    for e in owed:
        id_ = id_of(e)
        pid = projects.get(id_)
        if pid is None:
            continue   # its question has no destination yet: it, and every later event of it, waits
        project = S.known_project(pid)
        if project is None:
            debts.append("%s's project %s is not known here" % (id_, pid))
            continue
        if e["kind"] == "question":
            where = now()
            alias = where[1] if where is not None and where[0].id == pid else S.alias_in(project, session)
            froms[e["src"]] = alias
            event = {"kind": "question", "from": alias, "to": "host", "text": e["text"], "choices": e["choices"],
                     "src": e["src"]}
        else:
            if e["src"] not in froms:
                froms[e["src"]] = _question_from(project, session, e["src"], now)
            event = {"kind": "answered", "from": froms[e["src"]], "src": e["src"], "text": e["text"]}
            if "closed" in e:
                event["closed"] = e["closed"]
        batches.setdefault(project.id, (project, []))[1].append((e.get("n"), event))
    written = set()
    for project, batch in batches.values():
        try:
            S.append_host(project, session, [event for _, event in batch])
        except (OSError, S.LockBusy, S.LogWriteFailed) as e:
            failed.append("%s: %s" % (project.name, e))
            continue
        written |= {n for n, _ in batch if n is not None}
    left = len([e for e in owed if "n" in e])
    if written:
        with Lock(session):
            state = _read_state(rec) if still(record_identity(rec)) else None
            if state is not None:
                log = state["log"]
                log["owed"] = [e for e in log["owed"] if e["n"] not in written]
                state["seq"] += 1
                _write_file(rec, "state.json", _dumps(state).encode())
                left = len(log["owed"])
    if failed or (closing and debts):
        raise LogFailed("; ".join(failed + (debts if closing else [])))
    return {"written": len(written), "owed": left}


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
    """A pick as `answer` takes one: a place among the options (from 1), or a label: as written first, then the one
    label it names with surrounding whitespace forgiven, then in any case. Two labels a forgiving match names are
    neither."""
    labels = [o["label"] for o in q.get("options") or []]
    w = word.strip()
    if re.fullmatch(r"[0-9]+", w) and 1 <= int(w) <= len(labels):
        return labels[int(w) - 1]
    if word in labels:
        return word
    for same in (lambda x: x.strip() == w, lambda x: x.strip().lower() == w.lower()):
        found = [x for x in labels if same(x)]
        if found:
            return found[0] if len(found) == 1 else None
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


def _upload_ext(src):
    """An image `answer` may copy: its extension, or the refusal."""
    ext = os.path.splitext(src)[1][1:].lower()
    if ext not in IMAGE_EXTS:
        S.die("sheet answer: --image takes a %s file" % ", ".join(IMAGE_EXTS), 2)
    if not os.path.isfile(src):
        S.die("sheet answer: %s is not a file" % src, 2)
    return ext


def copy_upload(session, src):
    """An image copied into the record's uploads/ under a name of its own, for an answer to name."""
    ext = _upload_ext(src)
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
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, os.path.join(rec, name))
    except BaseException:
        try:
            os.unlink(tmp)                # a copy cut short (a full disk) leaves nothing behind
        except OSError:
            pass
        raise
    return name


def _send(session, lines):
    """Lines through the door, as one call: the door's own output, printed."""
    data = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines).encode()
    print(json.dumps(put(session, data), ensure_ascii=False))


def finish_removed(now_s=None):
    """What earlier removals left in sheet/ (a death, a deletion that failed, a record whose closings the log did not
    take), once older than a minute, so a removal in progress elsewhere keeps its own: a detached record's log is
    projected (what it owes, and its open questions closed), then it is deleted; one whose log the projection could
    not write stays for the next removal or sweep. Anything else is deleted. Returns what stays, as reasons."""
    root = sheet_root()
    now_s = time.time() if now_s is None else now_s
    try:
        names = os.listdir(root)
    except FileNotFoundError:
        return []
    stays = []
    for n in names:
        if not n.startswith(REMOVED):
            continue
        try:
            at = int(n[len(REMOVED):].split("-", 1)[0])
        except ValueError:
            at = 0
        if now_s - at <= REMOVED_AGE_S:
            continue
        path = os.path.join(root, n)
        why = _project_detached(path)
        if why:
            stays.append("%s: %s" % (path, why))
            continue
        shutil.rmtree(path, ignore_errors=True)
    return stays


def _project_detached(path):
    """A detached record's log written (project_log with `closing`), or why not, so it stays. None, to be deleted:
    no path, a staging or a record with no state.json (nothing it holds is owed), one whose state.json is a link
    (no state the sheet wrote). A state.json that cannot be read, or reads as no record's, is a why: a record whose
    debts cannot be known stays. Whatever else fails stays too, said; it fails for this one alone."""
    if not path:
        return None
    try:
        if _log_problem(path) is not None:
            return None
    except OSError as e:
        return "it could not be looked at: %s" % e
    try:
        state = _read_state(path)
    except (OSError, ValueError) as e:
        return "its state.json could not be read: %s" % e
    if state is None:
        return None
    session = state.get("session") if isinstance(state, dict) else None
    if not isinstance(session, str) or not S.UUID_RE.fullmatch(session):
        return "its state.json names no session"
    try:
        project_log(session, closing=True, rec=path)
    except LogFailed as e:
        return str(e)
    except Busy:
        return "its sheet's lock was busy"
    except Exception as e:  # noqa: BLE001 — one leftover's failure is not the others'
        return "%s: %s" % (type(e).__name__, e)
    return None


class Refused(Exception):
    """A removal refused or left unfinished: what to say, and the command's exit code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def remove(session, cleared=False, witnessed=None, clearing=None, started=None):
    """remove_record for the command: a refusal is its exit."""
    try:
        remove_record(session, cleared, witnessed=witnessed, clearing=clearing, started=started)
    except Refused as e:
        S.die(str(e), e.code)


def remove_record(session, cleared=False, witnessed=None, touched=None, confirm=None, clearing=None, started=None):
    """A stopped session's record and its staging (I1, M2), and its log (I12, M6). Liveness is checked before the lock
    and again under it (a session resumed while this waited; not with `cleared`, the session a /clear left); under
    the lock the staging, then the record, are detached, each by one rename inside sheet/, so no reader or step sees
    part of a removal, and a record that cannot be detached gets its staging back. Only then, the removal decided, is
    the detached record's log projected: what it still owes, then a closing for each question still open; a refusal
    before it publishes nothing. A record whose log could not all be written stays detached (Refused, 1) and the next
    removal or the daemon's sweep finishes it (finish_removed); otherwise both are deleted, and what could not be is
    said. `witnessed` (the daemon's sweep, and a /clear's removal, which checks no liveness) and `touched` (the
    sweep): the record's identity (record_identity) and its state.json's st_mtime_ns the removal was decided on,
    looked at again under the lock; another record there, one that cannot be told from another (same_record), or
    one changed since, is refused (2); `confirm`, a check the removal rests on (the sweep's: the transcript gone,
    or what a /clear's note describes), is run again there, and anything but True, or a failure, refuses (2).
    `clearing` (a /clear's removal: the pid of the process that cleared): under the lock, a session another process
    runs (a resume of the session left) is refused (2), and so is one whose liveness cannot be told. `started` (with
    a /clear's witness): the start the record had then (start_mark); one started since (a resume, even one that
    has stopped again), or whose start cannot be read, is refused (2). The lock file stays."""
    if not cleared and S.session_running(session):
        raise Refused("sheet remove: %s runs; its sheet goes when it stops" % session, 2)
    finish_removed()
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
                raise Refused("sheet remove: the record %s is not a directory; nothing removed" % rec, 1)
            if not os.path.isfile(os.path.join(rec, "state.json")):
                raise Refused("no sheet: %s has no question sheet on this machine" % session, EXIT_NO_SHEET)
            if not cleared and S.running_now(session):
                raise Refused("sheet remove: %s started while this waited; its sheet stays" % session, 2)
            if clearing is not None:
                try:
                    other = S.running_elsewhere(session, clearing)
                except OSError as e:
                    raise Refused("sheet remove: whether another process runs %s could not be told (%s); its sheet "
                                  "stays" % (session, e), 2)
                if other is not None:
                    raise Refused("sheet remove: %s runs in another process (pid %s) since the /clear; its sheet "
                                  "stays" % (session, other.get("pid")), 2)
            if witnessed is not None:
                same = same_record(record_identity(rec), tuple(witnessed))
                if same is None:
                    raise Refused("sheet remove: whether %s's sheet is the record the removal was decided on could "
                                  "not be told (its .incarnation holds no nonce that can be read); it stays"
                                  % session, 2)
                if not same or touched is not None \
                        and os.stat(os.path.join(rec, "state.json")).st_mtime_ns != touched:
                    raise Refused("sheet remove: %s's sheet is not the record the removal was decided on, or changed "
                                  "since; it stays" % session, 2)
            if started is not None:
                now = start_mark(session)
                if now is None:
                    raise Refused("sheet remove: which start %s's sheet last had could not be told; it stays"
                                  % session, 2)
                if now != started:
                    raise Refused("sheet remove: %s's sheet was started since the /clear (a resume); it stays"
                                  % session, 2)
            if confirm is not None:
                try:
                    confirmed = confirm() is True
                except Exception as e:  # noqa: BLE001 — what it rests on not known: the sheet stays
                    raise Refused("sheet remove: what %s's removal rests on could not be looked at again (%s); it "
                                  "stays" % (session, e), 2)
                if not confirmed:
                    raise Refused("sheet remove: what %s's removal rests on holds no more; it stays" % session, 2)
            for d in (staging_dir(session), rec):
                if os.path.exists(d):
                    to = os.path.join(sheet_root(), "%s%d-%s" % (REMOVED, int(time.time()), uuid.uuid4().hex))
                    try:
                        os.rename(d, to)
                    except OSError as e:
                        for back, was in reversed(detached):
                            os.rename(was, back)
                        raise Refused("sheet remove: %s could not be detached (%s); the sheet is still there"
                                      % (d, e), 1)
                    detached.append((d, to))
    except Busy:
        raise Refused("sheet remove: %s's sheet is busy; try again" % session, EXIT_BUSY)
    stays = _project_detached(dict(detached).get(rec, ""))
    left = []
    for d, to in detached:
        if d == rec and stays:
            continue
        try:
            shutil.rmtree(to)
        except OSError as e:
            left.append("%s (%s)" % (to, e))
    if stays:
        raise Refused("sheet remove: %s's sheet is removed, but its project log could not be written (%s); it is kept "
                      "aside, and the next removal or the daemon's sweep writes it" % (session, stays), 1)
    if left:
        raise Refused("sheet remove: %s's sheet is removed, but these could not be deleted (the next removal deletes "
                      "them): %s" % (session, "; ".join(left)), 1)


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
        for f in a.image:
            _upload_ext(f)
        images, progress = [], {}
        try:
            for f in a.image:
                images.append(copy_upload(session, f))
            if images:
                by = line.pop("by")
                line.update(images=images, by=by)
            appended = append(session, [line], progress)
        except BaseException:
            # Anything that stops this call before the door wrote (a refusal, a full disk, a copy that failed), or
            # after it cut its write back, takes its uploads back. Once the door began to write and was not cut
            # back (an interrupt at or after the write), the line may name them: they stay. Once appended, the
            # line names them: what fails after keeps them.
            if progress.get("writing"):
                raise
            for name in images:
                try:
                    os.unlink(os.path.join(record_dir(session), name))
                except OSError:
                    pass
            raise
        print(json.dumps(told(session, appended), ensure_ascii=False))
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
        witnessed = started = None
        if a.cleared:
            # What a /clear left goes with no liveness check (the clearing process may still be on record as running
            # it), so only the record witnessed at the clear may go: never one a resume of that session made since.
            # Nor while another process runs it (a resume during a retry): only the clearing process is excused.
            witness = parse_witness(a.witness)
            if witness is None:
                S.die("sheet remove: --cleared takes --witness, the record the /clear left as `sminos sheet witness` "
                      "printed it then; nothing removed", 2)
            witnessed, started = witness
            if a.clearing is None or a.clearing < 1:
                S.die("sheet remove: --cleared takes --clearing <pid>, the process that cleared; nothing removed", 2)
        elif a.witness is not None or a.clearing is not None:
            S.die("sheet remove: --witness and --clearing go with --cleared", 2)
        remove(session, cleared=a.cleared, witnessed=witnessed, clearing=a.clearing,
               started=started if a.cleared else None)
        print("removed %s's question sheet" % session)
        return
    if op == "surfaces":
        regs = surfaces()
        if a.json:
            print(json.dumps({"surfaces": regs}, ensure_ascii=False))
        else:
            print("\n".join("%s  %s  %s  %s" % (r["name"], terminal_safe(r["url"]), r["reach"],
                                                 "alive" if r["alive"] else "stale")
                            for r in regs) or "no surface registered")
        return
    if op in ("step", "probe", "log", "witness"):
        if not a.session or not S.UUID_RE.fullmatch(a.session):
            S.die("sheet %s: the question sheet's own verb, not for people; --session takes an engine session id"
                  % op)
        if op == "witness":
            # The record's identity now, its nonce minted if none is (as smns-cleared.sh does): what the mod takes
            # at a /clear and hands each removal of the record left (`remove --cleared --witness`).
            rec = record_dir(a.session)
            try:
                identity = record_identity(rec, mint=True) if has_record(a.session) else None
            except OSError as e:
                S.die("sheet witness: %s's sheet could not be looked at: %s" % (a.session, e), 1)
            if identity is None:
                S.die("no sheet: %s has no question sheet on this machine" % a.session, EXIT_NO_SHEET)
            if not identity[2]:
                S.die("sheet witness: %s's sheet holds no nonce that can be read; it has no identity" % a.session, 1)
            start = start_mark(a.session)
            if start is None:
                S.die("sheet witness: which start %s's sheet last had could not be read; it has no witness"
                      % a.session, 1)
            print(witness_text(identity, start))
        elif op == "step":
            print(_dumps(run_step(a.session, sys.stdin.buffer.read())))
        elif op == "log":
            try:
                out = project_log(a.session)
            except Busy:
                S.die("sheet log: %s's sheet is busy; the next projection writes it" % a.session, EXIT_BUSY)
            except LogFailed as e:
                S.die("sheet log: %s's project log could not be written: %s" % (a.session, e), 1)
            if out is None:
                S.die("no sheet: %s has no question sheet on this machine" % a.session, EXIT_NO_SHEET)
            print(json.dumps(dict({"session": a.session}, **out)))
        else:
            try:
                out = probe(a.session, remote=a.remote)
            except Busy:
                S.die("sheet probe: %s's record kept changing while it was read" % a.session, EXIT_BUSY)
            print(json.dumps(out, ensure_ascii=False))
        return
    S.die("usage: sminos sheet show|answer|dismiss|retract|put|remove (<member> | --session <id>) ... | surfaces")
