"""The question sheet's record: its door and its reader (contracts X1 and X2 of MAWS's
docs/doperpowers/specs/2026-11-23-question-sheet-design.md; this repository's plan
docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, I1, I3 and I4).

One session's sheet is a directory, `$SMINOS_HOME/sheet/<session>/`: `state.json`, which only the tool's step
writes (by atomic replace, under the record's lock), and `inbox.jsonl`, to which every surface appends through
one door. The lock is `$SMINOS_HOME/sheet/<session>.lock` beside the record, `fcntl.flock`'d and never removed.

    sminos sheet put  (<member> | --session <id>) [--no-wait]    the door: JSON lines on stdin
    sminos sheet show (<member> | --session <id>) [--json [--keys <k,...>]]   the reader's model, or its text

`put` appends the lines whole or not at all, under the lock, then tells the session's bridge (`{"op": "sheet",
"keys": [...]}`) and prints one JSON object, `{session, results: [{key, state, ...verdict}]}`, `queued` for a key
no verdict came back for. Exits: 0 appended, 2 a line refused (nothing appended), 3 no record (`no sheet`), 75 the
lock not had in 10 s. `show` takes no lock: it reads `state.json`, the inbox past its offset up to the last
newline, and `state.json` again, starting over while `seq` moves. The published set (`sminos/types/sheet/`) is the
contract both are held to.
"""

import errno
import fcntl
import json
import math
import os
import re
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
ID_RE = re.compile(r"^q[1-9][0-9]*$")
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
    """JSON as a line is read: NaN and the infinities, which Python's decoder takes, are refused."""
    return json.loads(text, parse_constant=_no_constant)


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
    if _surrogate(line):
        return "a string holds a lone UTF-16 surrogate"
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
        return "id is q<n>"
    if "revision" in line and not _count(line["revision"], 1):
        return "revision is an integer from 1"
    if "picks" in line and not (isinstance(line["picks"], list) and len(line["picks"]) <= 12
                                and all(isinstance(p, str) for p in line["picks"])):
        return "picks are at most 12 labels"
    if "text" in line and not (isinstance(line["text"], str) and len(line["text"]) <= 20000):
        return "text is at most 20,000 characters"
    if "images" in line and not (isinstance(line["images"], list) and len(line["images"]) <= 8
                                 and all(isinstance(i, str) and UPLOAD_RE.fullmatch(i) for i in line["images"])):
        return "images are at most 8 uploads/<name>.png|jpg|jpeg|gif|webp, a name of at most 250 characters"
    for f in ("target", "batch"):
        if f in line and not (isinstance(line[f], str) and KEY_RE.fullmatch(line[f])):
            return "%s is a key" % f
    if "keys" in line and not (isinstance(line["keys"], list) and 1 <= len(line["keys"]) <= 200
                               and all(isinstance(k, str) and KEY_RE.fullmatch(k) for k in line["keys"])):
        return "keys are 1 to 200 keys"
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
        for f in ("id", "target"):
            if f in x:
                s[f] = x[f]
        if x["key"] in cancelled:
            s["cancelled"] = True
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
            fd = os.open(os.path.join(rec, "inbox.jsonl"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                size = os.fstat(fd).st_size
                if size:
                    with open(os.path.join(rec, "inbox.jsonl"), "rb") as f:
                        f.seek(size - 1)
                        if f.read(1) != b"\n":
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


# ------------------------------------------------------------------ the verbs


def resolve(a, verb):
    """The session a verb names: --session as given (no registry read), else the member as the control verbs
    resolve one."""
    if bool(a.member) == bool(a.session):
        S.die("usage: sminos sheet %s (<member> | --session <id>)" % verb)
    if a.session:
        if not S.UUID_RE.fullmatch(a.session):
            S.die("sheet %s: --session takes an engine session id" % verb)
        return a.session
    return S.bridge_module().watch_session(a.member)


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
        print(json.dumps(m, ensure_ascii=False) if a.json else text(m))
        return
    S.die("usage: sminos sheet put|show (<member> | --session <id>) ...")
