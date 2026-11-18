#!/usr/bin/env python3
"""query-transcript: put a question to a haiku that holds one segment of a past
Claude Code session's transcript in its context.

A segment is the stretch of a session between two compactions, as the session
held it. The stretch is copied under a fresh session id into the project folder
of this tool's own work directory, resumed there headless (`claude -p --resume
<copy> --fork-session`) with no tools and no prompt cache, and asked the
question behind a frame that makes the answerer an investigator of the record.
Every blockquote in the answer is then looked up in the record and stamped with
its row's time and kind, or marked not found.

Design: docs/doperpowers/specs/2026-11-17-query-transcript-design.md.
"""

import argparse
import concurrent.futures
import datetime
import functools
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

MODEL = "haiku"
PRICE_PER_MTOK = 0.50          # the plan's ceiling, dollars per million tokens of segment
STALE_SECONDS = 24 * 3600      # a copy older than this in the work folder is a crashed run's
QUOTE_SHOWN = 110              # characters of a quote shown beside its stamp

FRAME = """\
You are not the model that worked in the conversation above, and that model's \
reasoning was never recorded: its thinking is not in this record. You are an \
investigator reading the record of that session as it stood at this point.

- Do not continue the session's task. Answer the question below and nothing else.
- Answer from the record only, in the third person: "the session" for the model \
that worked, "the human" for its user. Never speak as the session.
- Give evidence as verbatim quotes. Each quote is its own markdown blockquote \
(lines starting with "> ") holding one passage copied exactly from the record and \
nothing else: no paraphrase, translation, attribution or comment inside it. Mark \
an omission inside a passage with "...". Put any explanation outside the blockquote.
- Keep what the record shows apart from what you infer, and label inference as \
inference. A reason for a decision is inference unless the session stated it; \
then quote the statement.
- If the record does not hold the answer, say so plainly instead of guessing.
- The record shows you no clock. Do not estimate when or where in the \
conversation something happened beyond the order of events; the quotes are \
stamped with their times after you answer.
- The closing notices at the very end of the record that report a tool call \
interrupted, or background work (tasks, agents, shells) that failed, was killed \
or stopped when "the previous session ended", were added by this replay of the \
record. The session never saw them: do not report them as part of its history.
"""

class UsageError(Exception):
    """A usage error: exit 2."""


# ------------------------------------------------------------------ places


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def work_dir():
    return os.path.expanduser("~/.cache/query-transcript/work")


def project_folder(cwd):
    """The engine's project folder for a working directory: its real path with
    every character other than a letter or a digit made a dash."""
    return os.path.join(config_dir(), "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))


# ------------------------------------------------------------------ times


TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$")
UUID_PREFIX_RE = re.compile(r"^[0-9a-f][0-9a-f-]{3,35}$")


def parse_time(s):
    """An ISO time as an aware datetime; a time without a zone is UTC, as the
    record's are. None when `s` is not one."""
    if not isinstance(s, str) or not TIME_RE.match(s.strip()):
        return None
    s = s.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        t = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def show_time(ts):
    """A record's timestamp as shown: UTC to the second."""
    t = parse_time(ts) if isinstance(ts, str) else ts
    if t is None:
        return "?"
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ finding the transcript


def resolve(arg):
    """A transcript's path from a path, a session id or a unique prefix of one."""
    if arg.endswith(".jsonl") or os.sep in arg:
        if not os.path.isfile(arg):
            raise UsageError("no transcript at %s" % arg)
        return os.path.abspath(arg)
    if not re.fullmatch(r"[0-9A-Za-z-]+", arg):
        raise UsageError("not a session id or a transcript path: %s" % arg)
    own = os.path.realpath(project_folder(work_dir()))
    found = [p for p in glob.glob(os.path.join(config_dir(), "projects", "*", glob.escape(arg) + "*.jsonl"))
             if os.path.realpath(os.path.dirname(p)) != own]
    exact = [p for p in found if os.path.basename(p)[:-6] == arg]
    # A project folder can be a symlink to another (a moved checkout): one file, two names.
    real = {}
    for p in sorted(exact or found, key=lambda p: os.path.islink(os.path.dirname(p))):
        real.setdefault(os.path.realpath(p), p)
    found = list(real.values())
    if not found:
        raise UsageError("no session %s under %s" % (arg, os.path.join(config_dir(), "projects")))
    if len(found) > 1:
        raise UsageError("%s matches %d transcripts; name one:\n%s"
                         % (arg, len(found), "\n".join("  " + p for p in sorted(found))))
    return found[0]


# ------------------------------------------------------------------ the scan


class Segment:
    def __init__(self, n, start, end, start_ts, end_ts, tokens):
        self.n, self.start, self.end = n, start, end
        self.start_ts, self.end_ts, self.tokens = start_ts, end_ts, tokens

    def as_json(self):
        return {"segment": self.n, "start": show_time(self.start_ts), "end": show_time(self.end_ts),
                "tokens": self.tokens}


class Transcript:
    """One pass over a transcript: its compaction boundaries by byte offset, the
    times and token counts that bound each segment, and, when asked, the row a
    uuid prefix names. A last line without a newline is left out."""

    def __init__(self, path, uuid_prefix=None):
        self.path = path
        self.sidechain = os.path.basename(path).startswith("agent-")
        boundaries = []          # (offset, timestamp, preTokens)
        self.uuid_rows = {}      # uuid -> (offset, end offset), the rows uuid_prefix names
        first_ts = None
        usage_rows = []          # offsets of the last assistant rows that may carry a usage
        timed = []               # offsets of the last rows that carry a timestamp
        needle = b'"uuid":"' + uuid_prefix.encode() if uuid_prefix else None
        off = 0
        with open(path, "rb") as fh:
            for raw in fh:
                if not raw.endswith(b"\n"):
                    break
                if b'"compact_boundary"' in raw:
                    o = _load(raw)
                    if o and o.get("type") == "system" and o.get("subtype") == "compact_boundary":
                        boundaries.append((off, o.get("timestamp"),
                                           (o.get("compactMetadata") or {}).get("preTokens")))
                if first_ts is None and b'"timestamp"' in raw:
                    first_ts = (_load(raw) or {}).get("timestamp")
                if not self.sidechain and off == 0 and b'"isSidechain":true' in raw:
                    self.sidechain = True
                if b'"timestamp"' in raw:
                    timed.append(off)
                    if len(timed) > 64:
                        del timed[:32]
                if b'"type":"assistant"' in raw and b'"usage"' in raw:
                    usage_rows.append(off)
                    if len(usage_rows) > 64:
                        del usage_rows[:32]
                if needle and needle in raw:
                    o = _load(raw) or {}
                    u = o.get("uuid")
                    if isinstance(u, str) and u.startswith(uuid_prefix):
                        self.uuid_rows[u] = (off, off + len(raw))
                off += len(raw)
        self.size = off
        last_ts = None
        for o in reversed(timed):
            last_ts = (_load(_read(path, o)) or {}).get("timestamp")
            if last_ts:
                break
        last_tokens = None       # from the last real usage: an engine-made reply carries zeros
        for o in reversed(usage_rows):
            if boundaries and o < boundaries[-1][0]:
                break
            row = _load(_read(path, o)) or {}
            u = (row.get("message") or {}).get("usage") if row.get("type") == "assistant" else None
            if isinstance(u, dict):
                last_tokens = sum(int(u.get(k) or 0) for k in
                                  ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                                   "output_tokens")) or None
                if last_tokens:
                    break
        self.segments = []
        for k in range(len(boundaries) + 1):
            start = boundaries[k - 1][0] if k else 0
            start_ts = boundaries[k - 1][1] if k else first_ts
            if k < len(boundaries):
                end, end_ts, tokens = boundaries[k]
            else:
                end, end_ts, tokens = self.size, last_ts, last_tokens
            self.segments.append(Segment(k, start, end, start_ts, end_ts, tokens))


def _load(raw):
    try:
        o = json.loads(raw)
    except ValueError:
        return None
    return o if isinstance(o, dict) else None


def _read(path, off):
    with open(path, "rb") as fh:
        fh.seek(off)
        return fh.readline()


def stretch_lines(path, start, end):
    """The complete lines between two offsets, with each one's offset."""
    with open(path, "rb") as fh:
        fh.seek(start)
        off = start
        while off < end:
            raw = fh.readline()
            if not raw.endswith(b"\n"):
                break
            yield off, raw
            off += len(raw)


UUID_FIELD = re.compile(rb'"uuid":"([0-9a-f-]{36})"')
_ROW_INDEX = {}             # path -> {uuid: offset of the first row carrying it}
_ROW_INDEX_LOCK = threading.Lock()
_KEPT = {}                  # (path, segment) -> the rows its compaction kept


def row_index(path):
    """Where each uuid's row is, from one pass over the file, built the first
    time a segment past the first needs its kept rows and shared after."""
    with _ROW_INDEX_LOCK:
        if path not in _ROW_INDEX:
            index = {}
            for off, raw in stretch_lines(path, 0, os.path.getsize(path)):
                for m in UUID_FIELD.finditer(raw):
                    index.setdefault(m.group(1).decode(), off)
            _ROW_INDEX[path] = index
        return _ROW_INDEX[path]


def _row(path, index, u, before):
    """The row whose own uuid is `u`, from before offset `before`, or None."""
    off = index.get(u)
    if off is None or off >= before:
        return None
    o = _load(_read(path, off))
    return o if o and o.get("uuid") == u else None


def preserved(path, seg):
    """The rows from before segment `seg`'s boundary that its compaction kept,
    in file order: the ones `compactMetadata.preservedMessages` lists, and the
    chain `preservedSegment` names by its ends (walked from its tail to its
    head by parentUuid). The resume puts them back after the summary, so the
    session held them in this segment."""
    if seg.n == 0:
        return []
    key = (path, seg.n)
    if key in _KEPT:
        return _KEPT[key]
    meta = (_load(_read(path, seg.start)) or {}).get("compactMetadata") or {}
    kept = meta.get("preservedMessages")
    if isinstance(kept, str):
        kept = _load(kept)
    chain = meta.get("preservedSegment")
    wanted = set()
    if isinstance(kept, dict):
        for k in ("uuids", "allUuids"):
            wanted.update(u for u in kept.get(k) or [] if isinstance(u, str))
    rows = {}
    if wanted or isinstance(chain, dict):
        index = row_index(path)
        for u in wanted:
            o = _row(path, index, u, seg.start)
            if o:
                rows[u] = index[u]
        if isinstance(chain, dict) and chain.get("tailUuid") and chain.get("headUuid"):
            # Taken only when the walk reaches the head: a broken chain adds nothing.
            u, walk = chain["tailUuid"], {}
            while u and u not in walk and len(walk) < 10000:
                o = _row(path, index, u, seg.start)
                if not o:
                    break
                walk[u] = index[u]
                if u == chain["headUuid"]:
                    rows.update(walk)
                    break
                u = o.get("parentUuid")
    _KEPT[key] = [_read(path, off) for off in sorted(rows.values())]
    return _KEPT[key]


def segment_rows(path, seg, end):
    """What segment `seg` held up to `end`, row by row: the rows its compaction
    kept, then the stretch from its boundary (or the file's start)."""
    yield from preserved(path, seg)
    for _, raw in stretch_lines(path, seg.start, end):
        yield raw


def cut_at_time(path, seg, t):
    """The end offset of segment `seg` cut at time `t`: the end of its last row
    stamped at or before `t` (a transcript's stamps are not in file order
    everywhere), or None when it has none."""
    end = None
    for off, raw in stretch_lines(path, seg.start, seg.end):
        if b'"timestamp"' in raw:
            ts = parse_time((_load(raw) or {}).get("timestamp"))
            if ts and ts <= t:
                end = off + len(raw)
    return end


# ------------------------------------------------------------------ the copy and the fork


SESSION_FIELD = re.compile(rb'"sessionId":"[^"]*"')


def write_copy(rows, dest, new_id, sidechain):
    """The stretch as a transcript of session `new_id`: the session id in every
    row replaced and, for a subagent's transcript, the sidechain flag cleared.
    The engine's cost rows are left out: a resume adds the session's running
    cost from them to the fork's, and the fork's own is what is reported."""
    field = b'"sessionId":"' + new_id.encode() + b'"'
    with open(dest, "wb") as out:
        for raw in rows:
            if raw.startswith(b'{"type":"cost-state"'):
                continue
            raw = SESSION_FIELD.sub(field, raw)
            if sidechain:
                raw = raw.replace(b'"isSidechain":true', b'"isSidechain":false')
            out.write(raw)


def sweep_stale(folder):
    """Remove what a crashed run left in the work folder: anything older than a day."""
    now = time.time()
    for p in glob.glob(os.path.join(folder, "*")):
        try:
            if now - os.lstat(p).st_mtime > STALE_SECONDS:
                _remove(p)
        except OSError:
            pass


def _remove(p):
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p, ignore_errors=True)
    elif os.path.lexists(p):
        os.unlink(p)


def fork_command(copy_id, fork_id, prompt):
    # The prompt comes last: --tools takes several values and would swallow it.
    return ["claude", "-p", "--resume", copy_id, "--fork-session", "--session-id", fork_id, "--safe-mode",
            "--no-session-persistence", "--model", MODEL, "--effort", "high", "--tools", "",
            "--output-format", "json", prompt]


class ForkFailed(Exception):
    pass


LIVE = set()            # the forks running now, killed on an interrupt so each run's cleanup runs
LIVE_LOCK = threading.Lock()
STOPPING = threading.Event()


def ask(transcript, seg, end, prompt, timeout):
    """Copy the stretch, ask the fork, and remove the copy and anything the fork
    wrote whatever the outcome. The fork's result object, or ForkFailed."""
    folder = project_folder(work_dir())
    copy_id, fork_id = str(uuid.uuid4()), str(uuid.uuid4())
    copy = os.path.join(folder, copy_id + ".jsonl")
    env = {**os.environ, "SMNS_INTERNAL": "1", "DISABLE_PROMPT_CACHING": "1"}
    obj = None
    try:
        write_copy(segment_rows(transcript.path, seg, end), copy, copy_id, transcript.sidechain)
        try:
            proc = subprocess.Popen(fork_command(copy_id, fork_id, prompt), cwd=work_dir(), env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, start_new_session=True)
        except OSError as e:
            raise ForkFailed("claude did not start: %s" % e)
        with LIVE_LOCK:
            LIVE.add(proc)
        if STOPPING.is_set():
            _kill(proc)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill(proc)
            proc.communicate()
            raise ForkFailed("timed out after %ds" % timeout)
        finally:
            with LIVE_LOCK:
                LIVE.discard(proc)
        if STOPPING.is_set():
            raise ForkFailed("interrupted")
        for raw in reversed((out or "").splitlines()):
            if raw.strip().startswith("{"):
                d = _load(raw)
                if d is not None:
                    obj = d
                    break
        if proc.returncode != 0 or obj is None or obj.get("is_error"):
            raise ForkFailed("claude failed (exit %d)%s" % (proc.returncode, _why(obj, err)))
        if not str(obj.get("result") or "").strip():
            raise ForkFailed("claude answered nothing")
        return obj
    finally:
        for sid in {copy_id, fork_id, str((obj or {}).get("session_id") or "")}:
            if re.fullmatch(r"[0-9a-f-]{36}", sid):
                for p in (os.path.join(folder, sid + ".jsonl"), os.path.join(folder, sid)):
                    try:
                        _remove(p)
                    except OSError:
                        pass


def _kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        proc.kill()


def _why(obj, err):
    said = []
    if obj and obj.get("is_error"):
        errors = obj.get("errors")
        said = [str(obj.get("result") or "")] + ([str(e) for e in errors] if isinstance(errors, list) else [])
    text = " ".join(" ".join(said).split()) or " ".join((err or "").split())
    return ": " + text[:300] if text else ""


# ------------------------------------------------------------------ the quote check


CONVERSATION = {"user", "assistant", "attachment", "system"}
CONVERSATION_HEADS = tuple(b'{"type":"%s"' % t.encode() for t in CONVERSATION)
SKIPPED_KEYS = {"signature"}
ELLIPSIS = re.compile(r"\s*(?:\[\s*(?:\.\.\.|…)\s*\]|\.\.\.+|…)\s*")
OUTER = "\"'`“”‘’"
# Typographic quote marks only: markdown's `*` and backticks are code in a command
# or an expression (`2 ** 3`, `echo \`id\``), so a quote that drops them is not the record.
LOOSE = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'"})


def _norm(s):
    return " ".join(s.split())


def _loose(s):
    return _norm(s.translate(LOOSE))


def row_kind(o):
    """What a conversation row is, as a reader of the record would name it."""
    t = o.get("type")
    if t == "assistant":
        return "session"
    if t == "system":
        return "notice"
    if t == "attachment":
        a = o.get("attachment") or {}
        if a.get("type") == "queued_command":
            return _origin_kind(a.get("origin"), a.get("prompt"))
        return "notice"
    if o.get("isCompactSummary"):
        return "summary"
    content = (o.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return "tool result"
    origin = o.get("origin")
    if isinstance(origin, dict) and origin.get("kind") == "peer":
        return "peer message"  # the engine marks another session's message meta
    if o.get("isMeta"):
        return "notice"
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return _origin_kind(o.get("origin"), content)


def _origin_kind(origin, text):
    kind = origin.get("kind") if isinstance(origin, dict) else None
    if kind == "human":
        return "human"
    if kind == "peer":
        return "peer message"
    if kind:
        return "notice"
    text = text if isinstance(text, str) else ""
    if re.match(r"\s*<(task-notification|cross-session-message|agent-message)", text):
        return "notice" if "task-notification" in text[:40] else "peer message"
    return "human"


def _strings(v, out):
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, dict):
        for k, x in v.items():
            if k not in SKIPPED_KEYS:
                _strings(x, out)
    elif isinstance(v, list):
        for x in v:
            _strings(x, out)


class Record:
    """The stretch's conversation rows as searchable text: each row's strings,
    whitespace collapsed, with its time, kind and uuid. The engine's request
    log rows, which repeat these without a time, are left out."""

    def __init__(self, rows):
        self.rows = []
        for raw in rows:
            if raw.startswith(b'{"type":"') and not raw.startswith(CONVERSATION_HEADS):
                continue
            o = _load(raw)
            if not o or o.get("type") not in CONVERSATION:
                continue
            parts = []
            _strings(o.get("message") if o.get("type") in ("user", "assistant") else o, parts)
            text = _norm("\n".join(parts))
            self.rows.append((text, None, o.get("timestamp"), row_kind(o), o.get("uuid") or ""))

    def find(self, pieces, loose=False):
        hits = []
        for i, (text, lz, ts, kind, u) in enumerate(self.rows):
            if loose:
                if lz is None:
                    lz = _loose(text)
                    self.rows[i] = (text, lz, ts, kind, u)
                text = lz
            pos = 0
            for p in pieces:
                j = text.find(p, pos)
                if j < 0:
                    break
                pos = j + len(p)
            else:
                hits.append((ts, kind, u))
        return hits


def blockquotes(answer):
    """The answer's blockquotes, each joined into one passage; fenced code is skipped."""
    out, cur, fenced = [], [], False
    for line in answer.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        m = None if fenced else re.match(r"^\s*>\s?(.*)$", line)
        if m:
            cur.append(m.group(1))
            continue
        if cur:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return [q for q in (_norm(q) for q in out) if q]


def check_quotes(answer, record):
    """Every blockquote of the answer, found in the record (its first row's time,
    kind and uuid, and how many rows more hold it) or not."""
    checked = []
    for q in blockquotes(answer):
        hits = []
        for loose in (False, True):
            f = _loose if loose else _norm
            pieces = [f(p.strip(OUTER + " ")) for p in ELLIPSIS.split(q.strip(OUTER + " "))]
            pieces = [p for p in pieces if p]
            if pieces:
                hits = record.find(pieces, loose)
            if hits:
                break
        if hits:
            ts, kind, u = hits[0]
            checked.append({"quote": q, "found": True, "time": show_time(ts), "kind": kind, "uuid": u,
                            "more": len(hits) - 1})
        else:
            checked.append({"quote": q, "found": False})
    return checked


# ------------------------------------------------------------------ one segment


def run_segment(transcript, seg, end, until, query, timeout):
    """Ask one segment; its result as a dict (answer, quotes, usage, or error)."""
    res = seg.as_json()
    if until is not None:
        res["until"] = until
    # Every segment gets the same prompt, a single segment's: offered a "nothing
    # relevant" reply for the segments without the answer, haiku gave it to every
    # segment, at once and without thinking, the one holding the answer included.
    prompt = FRAME + "\nThe question:\n\n" + query
    t0 = time.time()
    try:
        obj = ask(transcript, seg, end, prompt, timeout)
    except ForkFailed as e:
        res["error"] = str(e)
        res["seconds"] = round(time.time() - t0)
        return res
    answer = str(obj.get("result") or "").strip()
    u = obj.get("usage") or {}
    res["usage"] = {
        "model": MODEL,
        "input": sum(int(u.get(k) or 0) for k in
                     ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
        "output": int(u.get("output_tokens") or 0),
        "cost": obj.get("total_cost_usd"),
        "seconds": round(time.time() - t0),
    }
    res["answer"] = answer
    res["quotes"] = check_quotes(answer, Record(segment_rows(transcript.path, seg, end)))
    return res


# ------------------------------------------------------------------ output


def _range(r):
    s = "segment %d · %s → %s" % (r["segment"], r["start"], r["end"])
    if r.get("until"):
        s += " · until %s" % r["until"]
    return s


def _usage_line(u):
    cost = u.get("cost")
    return "via %s · %s in · %s out · %s · %d s" % (
        u["model"], format(u["input"], ","), format(u["output"], ","),
        "$%.2f" % cost if isinstance(cost, (int, float)) else "$?", u["seconds"])


def render(r):
    if r.get("error"):
        return "== %s · FAILED: %s\n" % (_range(r), r["error"])
    lines = ["== " + _range(r), "", r["answer"], ""]
    if r["quotes"]:
        lines.append("Quotes checked against the record:")
        for q in r["quotes"]:
            shown = q["quote"] if len(q["quote"]) <= QUOTE_SHOWN else q["quote"][:QUOTE_SHOWN - 1] + "…"
            if q["found"]:
                more = " (+%d more)" % q["more"] if q["more"] else ""
                lines.append("  %s  %s  %s%s  \"%s\"" % (q["time"], q["kind"], q["uuid"][:8], more, shown))
            else:
                lines.append("  not found in the record  \"%s\"" % shown)
        lines.append("")
    lines.append(_usage_line(r["usage"]))
    return "\n".join(lines) + "\n"


def list_segments(t, as_json):
    total = sum(s.tokens or 0 for s in t.segments)
    if as_json:
        print(json.dumps({"transcript": t.path, "segments": [s.as_json() for s in t.segments],
                          "tokens": total}, ensure_ascii=False, indent=1))
        return
    print("%-8s %-21s %-21s %s" % ("segment", "start", "end", "tokens at end"))
    for s in t.segments:
        print("%-8d %-21s %-21s %s" % (s.n, show_time(s.start_ts), show_time(s.end_ts),
                                         format(s.tokens, ",") if s.tokens else "?"))
    print("%d segment%s · %s tokens in all · --all costs at most $%.2f"
          % (len(t.segments), "" if len(t.segments) == 1 else "s", format(total, ","),
             total * PRICE_PER_MTOK / 1e6))


# ------------------------------------------------------------------ the command


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="query-transcript",
        description="Put a question to a haiku holding one segment of a past Claude Code session "
                    "(the stretch between two compactions) in its context. It answers as an investigator "
                    "of the record, with quotes this tool checks and stamps with their times.")
    p.add_argument("session", help="a session id, a unique prefix of one, or a transcript path "
                                   "(a subagent's agent-*.jsonl included)")
    p.add_argument("query", nargs="?", help="the question (several questions about one stretch go in one query)")
    p.add_argument("--list", action="store_true", help="list the segments: number, time range, tokens at the end")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--segment", type=int, metavar="N", help="the segment to ask (default: the last)")
    g.add_argument("--segments", metavar="A-B", help="a range of segments, each asked on its own")
    g.add_argument("--all", action="store_true", help="every segment, each asked on its own")
    p.add_argument("--until", metavar="T", help="end the context at a time (ISO; UTC unless zoned) or at a "
                                                "row's uuid or unique prefix; picks its segment without --segment")
    p.add_argument("--jobs", type=int, default=6, metavar="N", help="segments asked at once (default 6)")
    p.add_argument("--timeout", type=int, default=600, metavar="S", help="seconds per segment (default 600)")
    p.add_argument("--json", action="store_true", help="print one JSON object instead of text")
    a = p.parse_intermixed_args(argv)
    if not a.list and not a.query:
        p.error("a query is required (or --list)")
    if a.until and (a.segments or a.all):
        p.error("--until goes with one segment, not --segments or --all")
    if a.jobs < 1 or a.timeout < 1:
        p.error("--jobs and --timeout take a positive number")
    return a


def pick(t, a):
    """The segments to ask, as (segment, end offset, until shown) triples."""
    last = len(t.segments) - 1
    if a.all:
        return [(s, s.end, None) for s in t.segments]
    if a.segments:
        m = re.fullmatch(r"(\d+)-(\d*)", a.segments)
        if not m:
            raise UsageError("--segments takes A-B (or A- for A to the last)")
        lo, hi = int(m.group(1)), int(m.group(2)) if m.group(2) else last
        if lo > hi or hi > last:
            raise UsageError("--segments %s: the segments are 0-%d" % (a.segments, last))
        return [(s, s.end, None) for s in t.segments[lo:hi + 1]]
    if a.segment is not None and not 0 <= a.segment <= last:
        raise UsageError("no segment %d: the segments are 0-%d" % (a.segment, last))
    if not a.until:
        s = t.segments[last if a.segment is None else a.segment]
        return [(s, s.end, None)]
    when = parse_time(a.until)
    if when is not None:
        # The segment whose compaction came last at or before it; segment 0 before any.
        s = ([x for x in t.segments[1:] if (parse_time(x.start_ts) or when) <= when] or t.segments[:1])[-1]
        if a.segment is not None and a.segment != s.n:
            raise UsageError("--until %s is in segment %d (%s → %s), not %d"
                             % (a.until, s.n, show_time(s.start_ts), show_time(s.end_ts), a.segment))
        end = cut_at_time(t.path, s, when)
        if end is None:
            raise UsageError("--until %s is before the session's first row" % a.until)
        return [(s, end, show_time(when))]
    rows = t.uuid_rows
    if not rows:
        raise UsageError("--until %s is neither a time nor a row's uuid in this transcript" % a.until)
    if len(rows) > 1:
        raise UsageError("--until %s matches %d rows: %s" % (a.until, len(rows), ", ".join(sorted(rows))))
    u, (off, end) = next(iter(rows.items()))
    held = [s for s in t.segments if s.start <= off < s.end] or [t.segments[-1]]
    s = held[0] if a.segment is None else t.segments[a.segment]
    if s is not held[0]:
        raise UsageError("--until %s is in segment %d, not %d" % (a.until, held[0].n, s.n))
    return [(s, end, u)]


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    try:
        a = parse_args(sys.argv[1:] if argv is None else argv)
        path = resolve(a.session)
        prefix = a.until if a.until and parse_time(a.until) is None and UUID_PREFIX_RE.match(a.until) else None
        t = Transcript(path, prefix)
        if a.list:
            list_segments(t, a.json)
            return 0
        chosen = pick(t, a)
    except UsageError as e:
        print("query-transcript: %s" % e, file=sys.stderr)
        return 2
    if len(chosen) > 1:
        tokens = sum(s.tokens or 0 for s, _, _ in chosen)
        print("query-transcript: %d segments, %s tokens, at most $%.2f at $%.2f per million; %d at a time"
              % (len(chosen), format(tokens, ","), tokens * PRICE_PER_MTOK / 1e6, PRICE_PER_MTOK,
                 min(a.jobs, len(chosen))), file=sys.stderr)
    os.makedirs(work_dir(), exist_ok=True)
    folder = project_folder(work_dir())
    os.makedirs(folder, exist_ok=True)
    sweep_stale(folder)
    signal.signal(signal.SIGTERM, _interrupt)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(a.jobs, len(chosen))) as pool:
        futures = [pool.submit(run_segment, t, s, end, until, a.query, a.timeout)
                   for s, end, until in chosen]
        try:
            for f in futures:
                r = f.result()
                results.append(r)
                if not a.json:
                    sys.stdout.write(("\n" if len(results) > 1 else "") + render(r))
                    sys.stdout.flush()
        except KeyboardInterrupt:
            STOPPING.set()
            for f in futures:
                f.cancel()
            with LIVE_LOCK:
                for proc in list(LIVE):
                    _kill(proc)
            raise
    if a.json:
        sid = os.path.basename(path)[:-6] if path.endswith(".jsonl") else path
        print(json.dumps({"session": sid, "transcript": path, "segments": results}, ensure_ascii=False, indent=1))
    return 1 if any(r.get("error") for r in results) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("query-transcript: interrupted", file=sys.stderr)
        sys.exit(130)
