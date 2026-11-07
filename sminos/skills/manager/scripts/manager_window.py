"""A condensed window of a session's transcript: what the owner and the session said and did, oldest first,
without what tools returned (the manager's `transcript` command).

The transcript is never read whole. A window starts at the first row stamped at or after `since`, found by
bisection on the rows' timestamps (sminos_subagents.offset_since over an mmap), and the scan forward passes the
engine's request records (`api-request` lines, which repeat the conversation and are most of a large file)
without parsing them.

Each row is classified into one entry kind (KINDS) from the frames sminos's own readers know: the async ask's
questions and deliveries (sminos._ask_events), the message tools (sminos._sent_text), `<message>` spans
(sminos.extract_marks), task notifications (sminos_jobs._plain_notification), the bridge's notes
(sminos_jobs.STOP_NOTE, INTERRUPT_ORIGINS) and tool summaries (sminos_bridge._tool_summary). Where no reader
exists the classifier keys on the constants the bridge writes (hooks/mods/bridge.tsx: STEER_LINE, WAKE_LINE,
INTERRUPT_MARKER, CUT_OFF_LINE) and on the engine's row origins. A row it cannot place is left out: the worst
error this reader can make is inventing the owner's words, so nothing reads as `you` without an origin that
affirmatively says the owner typed it.
"""

import datetime
import json
import mmap
import os
import re

import sminos as S
import sminos_bridge as B
import sminos_jobs as jobs
import sminos_marks
import sminos_subagents as SA

DEFAULT_MAX_CHARS = 400_000
KINDS = ("you", "you?", "you·desk", "you·desk?", "you·steer", "peer", "session", "→you", "asked", "answered",
         "compacted", "interrupted", "tool", "agent", "notice", "boundary")

# What the bridge writes (sminos/hooks/mods/bridge.tsx, bridge-state.tsx): no Python reader holds these.
STEER_LINE = "[sminos steer from human]"
WAKE_LINE = "[sminos bridge]"
INTERRUPT_MARKER = "[Request interrupted by user]"
CUT_OFF_LINE = "The interrupt cut off the reply you were writing."
AGENT_STOP_RE = re.compile(r"Agent \S+ was stopped by the person (?:from the desk|from outside the terminal): ")
# The bridge lived in the doperpowers plugin before it moved to sminos; transcripts hold both.
BRIDGE_PLUGINS = ("sminos", "doperpowers")
# Origins that affirmatively say the owner typed the row: the composer, or the owner's own Remote Control client.
OWNER_ORIGINS = ("composer", "human", "bridge")
# A MAWS launch (its entrypoint): the owner's words there come through MAWS's composer.
MAWS_ENTRYPOINT = "sdk-ts"
AGENT_TOOLS = ("Agent", "Task", "Workflow")
NATIVE_ASK = "AskUserQuestion"

TOOL_CHARS = 160
AGENT_RESULT_CHARS = 600
CUT_OFF_SHOWN = 300
# What the owner's `!` shell mode records after its `<bash-input>` row: the command's output, a tool result.
SHELL_OUTPUT_TAGS = ("<bash-stdout>", "<bash-stderr>")
LABEL_WIDTH = 10

PEER_OPEN = "Another Claude session sent a message:\n"
# The engine follows the closing tag with its own guidance for the model, which is left out.
ENVELOPE_RE = re.compile(r"<cross-session-message\b([^>]*)>\n?(.*)\n?</cross-session-message>", re.S)
FROM_NAME_RE = re.compile(r'\bfrom-name="([^"]*)"')
REPLY_LINE_RE = re.compile(r"\n\[To reply, run in Bash: [^\n]*\]\s*\Z")
# The frames sminos delivers (sminos.compose_chat_frame, compose_frame), at a line's start.
CHAT_FRAME_RE = re.compile(r"^\[sminos chat (\S+) (\S+) from (.+?) → ([^\]\n]*?)(?: \| unread \d+)?\]\n", re.M)
MESSAGE_FRAME_RE = re.compile(r"^\[sminos message from (.+?) id=(\S+)\]\n", re.M)
# The clause sminos.sender_labels puts after a sender's alias.
SENDER_LABEL_RE = re.compile(r"(?:, owned by .*| \((?:owners unverified|unverified(?:, legacy)?|signed by a revoked key)\))\Z")


def _text(content):
    """A row's text blocks, joined; a string content is its text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


def _cut(text, n):
    return text if len(text) <= n else text[:n - 1] + "…"


def _outside_marks(text):
    """The text with its `<message>` regions taken out (the spans themselves are read by extract_marks). The
    tags are the ones the marks parse reads (sminos_marks.tag_tokens), so a literal tag in code stays prose."""
    out, depth, at = [], 0, 0
    for m in sminos_marks.tag_tokens(text):
        if depth == 0:
            out.append(text[at:m.start()])
        depth = max(depth + (-1 if m.group(1) else 1), 0)
        at = m.end()
    if depth == 0:
        out.append(text[at:])
    return "".join(out)


def _sender(raw):
    return SENDER_LABEL_RE.sub("", raw.strip())


def frames(text):
    """[(kind, sender, ref, body, whole)] for each sminos frame in a delivered text, in order: kind `chat` (ref
    its event's `writer:seq`) or `message` (ref its message id); `whole` the frame's own text, header line and
    body. [] for a text that opens with none."""
    heads = sorted([("chat", m) for m in CHAT_FRAME_RE.finditer(text)] +
                   [("message", m) for m in MESSAGE_FRAME_RE.finditer(text)], key=lambda h: h[1].start())
    if not heads or heads[0][1].start() != 0:
        return []
    out = []
    for i, (kind, m) in enumerate(heads):
        end = heads[i + 1][1].start() if i + 1 < len(heads) else len(text)
        body, whole = text[m.end():end].rstrip("\n"), text[m.start():end].rstrip("\n")
        if kind == "chat":
            out.append(("chat", _sender(m.group(3)), m.group(2), body, whole))
        else:
            out.append(("message", _sender(m.group(1)), m.group(2), body, whole))
    return out


class OwnerWords:
    """The owner's words a project's log holds for one lineage (sminos.owner_event: `human` events of
    `<machine>/human` or `hub/<member>`, addressed to one of `sessions` by sminos.addressed_to), to corroborate
    what the bridge delivered to that session as the owner's."""

    def __init__(self, events, sessions):
        self.by_ref, self.texts = {}, set()
        for e in events:
            if S.owner_event(e) and isinstance(e.get("text"), str) and any(S.addressed_to(e, s) for s in sessions):
                self.by_ref[S.event_ref(e)] = e["text"].strip()
                self.texts.add(e["text"].strip())

    def corroborates(self, text):
        """Whether one delivered frame from the owner, or a bare text, is the owner's words to this lineage as
        the log holds them: a chat frame names, by its ref, such an event with exactly its text; a message frame
        or a bare text (MAWS's RL10 send, which never logs) is such an event's whole text. A text of several
        frames is classified frame by frame, never corroborated whole."""
        fs = frames(text)
        if not fs:
            return text.strip() in self.texts
        if len(fs) != 1 or fs[0][1] != "human":
            return False
        kind, _, ref, body, _ = fs[0]
        return self.by_ref.get(ref) == body.strip() if kind == "chat" else body.strip() in self.texts


def _local(ts):
    t = SA._epoch(ts)
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t is not None else "????-??-?? ??:??"


def label(entry):
    return "peer %s" % entry.get("from", "?") if entry["kind"] == "peer" else entry["kind"]


def render(entry):
    """One entry as the text output prints it: local time, its label, its text, continuation lines indented."""
    head = "%s  %s " % (_local(entry["ts"]), label(entry).ljust(LABEL_WIDTH))
    return head + entry["text"].replace("\n", "\n" + " " * len(head))


class Classifier:
    """One session's rows, fed oldest first, into entries. A tool call's result settles it later in the feed:
    a message tool's call is the owner's message from its call (its input's text, as sminos._sent_text reads
    it), withdrawn when its result is an error; an agent's line takes the first characters of its result; a
    blocking question its answer (`answered`, source `blocking`). The async ask's questions and answers are read
    at the end over the rows that can hold them (sminos._ask_events; source `async`). A `you·desk` entry says
    how it came (`via`: `composer`, a MAWS launch's composer; `bridge`, a bridge delivery).
    `chars`: the rendered size of the entries so far, for the window's budget."""

    def __init__(self, session, corroborate=None, lookup=None):
        self.short = session[:8]
        self.corroborate = corroborate or (lambda text: False)
        self.lookup = lookup     # row uuid -> the row, searched for before the window's seek point; or None
        self.out = []            # (row seq, sub, entry)
        self.pending = {}        # tool id -> (what, row seq, sub, the call's block or entry, its time)
        self.ask_rows = []       # (row seq, row) for _ask_events
        self.ask_calls = set()
        self.calls = set()       # every tool call id seen, before the window or in it
        self.seq = 0
        self.chars = 0

    def _add(self, sub, ts, kind, text, seq=None, **extra):
        entry = {"ts": ts, "session": self.short, "kind": kind, "text": text, **extra}
        self.out.append((self.seq if seq is None else seq, sub, entry))
        self.chars += len(render(entry)) + 1
        return entry

    def _ask_row(self, row):
        """The row kept for _ask_events, once."""
        if not self.ask_rows or self.ask_rows[-1][0] != self.seq:
            self.ask_rows.append((self.seq, row))

    def feed(self, row):
        self.seq += 1
        kind = row.get("type")
        if kind == "assistant":
            self._assistant(row)
        elif kind == "user":
            self._user(row)
        elif kind == "attachment":
            self._attachment(row)

    def finish(self):
        """The entries, in row order."""
        if self.ask_rows:
            for i, e in S._ask_events([r for _, r in self.ask_rows]):
                seq, row = self.ask_rows[i]
                text = _question(e["text"], e.get("choices")) if e["kind"] == "question" else e["text"]
                entry = {"ts": row.get("timestamp"), "session": self.short,
                         "kind": "asked" if e["kind"] == "question" else "answered", "text": text}
                if e["kind"] != "question":
                    entry["source"] = "async"
                self.out.append((seq, -1, entry))
        self.out.sort(key=lambda x: (x[0], x[1]))
        return [e for _, _, e in self.out]

    # ---- the model's rows

    def _assistant(self, row):
        if row.get("answeredWithoutRequest") is True:
            return
        ts, asks = row.get("timestamp"), False
        for n, b in enumerate(S._blocks(row)):
            kind = b.get("type")
            if kind == "text":
                text = str(b.get("text") or "")
                marks = S.extract_marks(text)
                prose = (_outside_marks(text) if marks else text).strip()
                if prose:
                    self._add(n, ts, "session", prose)
                for m in marks:
                    self._add(n, ts, "→you", m["text"])
            elif kind == "tool_use":
                name, cid, inp = str(b.get("name") or ""), str(b.get("id") or ""), b.get("input")
                inp = inp if isinstance(inp, dict) else {}
                self.calls.add(cid)
                if name in S.MESSAGE_TOOLS:
                    # The owner's message at its call, so a window edge between the call and its result cannot
                    # lose it; an error result in the window withdraws it (_settle).
                    text = inp.get("text")
                    if isinstance(text, str) and text.strip():
                        self.pending[cid] = ("message", self.seq, n, self._add(n, ts, "→you", text), ts)
                elif name in S.ASK_TOOLS or name == S.MAWS_ASK_TOOL or name == NATIVE_ASK:
                    if not _blocking_ask(b):
                        self.ask_calls.add(cid)    # an async ask: _ask_events reads it
                        asks = True
                    else:
                        qs = [q for q in inp.get("questions") or [] if isinstance(q, dict)]
                        self._add(n, ts, "asked", _question([str(q.get("question") or "") for q in qs],
                                                            [str(o.get("label") or "") for q in qs
                                                             for o in q.get("options") or [] if isinstance(o, dict)]))
                        self.pending[cid] = ("ask", self.seq, n, None, ts)
                elif name in AGENT_TOOLS:
                    what = inp.get("description") or inp.get("name") or inp.get("scriptPath") or ""
                    kind_of = inp.get("subagent_type") or name
                    entry = self._add(n, ts, "agent", _cut("%s: %s" % (kind_of, what), TOOL_CHARS))
                    self.pending[cid] = ("agent", self.seq, n, entry, ts)
                else:
                    summary = B._tool_summary(name, inp)
                    self._add(n, ts, "tool", _cut("%s: %s" % (name, summary) if summary else name, TOOL_CHARS))
        if asks:
            self._ask_row(row)

    def prior(self, row):
        """A row between the seek point and the window, read only for its tool calls: a blocking question's
        answer in the window is still known as one. It adds no entry."""
        if row.get("type") != "assistant":
            return
        for n, b in enumerate(S._blocks(row, "tool_use")):
            cid = str(b.get("id") or "")
            self.calls.add(cid)
            if _blocking_ask(b):
                self.pending[cid] = ("ask", 0, n, None, row.get("timestamp"))

    def _distant_answer(self, block, row, cid):
        """Whether a result whose call this classifier never saw (it lies before the window's seek point) is a
        blocking question's answer. The row names its call (`sourceToolAssistantUUID`), which is found by an
        exact search back from the seek point; a row that names none is an answer only when its record says so
        itself: the engine's native record (`toolUseResult` with `questions` and `answers`), or MAWS's answered
        result, which names this call (`{"status": "answered", "askId": <the call>}`)."""
        if block.get("is_error") is True or cid in self.calls:
            return False
        src = row.get("sourceToolAssistantUUID")
        if self.lookup is not None and isinstance(src, str) and S.UUID_RE.fullmatch(src):
            call = self.lookup(src)
            if call is not None:
                return any(b.get("id") == cid and _blocking_ask(b) for b in S._blocks(call, "tool_use"))
        record = row.get("toolUseResult")
        if isinstance(record, dict) and "questions" in record and "answers" in record:
            return True
        try:
            result = json.loads(S._result_text(block.get("content")))
        except ValueError:
            return False
        return isinstance(result, dict) and result.get("status") == "answered" and result.get("askId") == cid

    def _settle(self, block, ts, row):
        cid = str(block.get("tool_use_id") or "")
        held = self.pending.pop(cid, None)
        if held is None:
            if self._distant_answer(block, row, cid):
                text = S._result_text(block.get("content")).strip()
                if text:
                    self._add(0, ts, "answered", text, source="blocking")
            return
        what, seq, sub, call, called = held
        if block.get("is_error") is True:
            if what == "message":    # refused, failed or interrupted: it sent nothing
                self.out = [x for x in self.out if x[2] is not call]
                self.chars -= len(render(call)) + 1
            return
        elif what == "agent":
            result = S._result_text(block.get("content")).strip()
            # A background agent's launch says only that it started; its report comes later, as a hand-back.
            if result and not jobs._launch_text(result):
                before = len(render(call)) + 1
                call["text"] += "\n→ " + result[:AGENT_RESULT_CHARS]
                self.chars += len(render(call)) + 1 - before
        elif what == "ask":
            text = S._result_text(block.get("content")).strip()
            if text:
                self._add(0, ts, "answered", text, source="blocking")

    # ---- user rows

    def _user(self, row):
        ts, content = row.get("timestamp"), (row.get("message") or {}).get("content")
        if row.get("isCompactSummary") is True:
            text = _text(content).strip()
            if text:
                self._add(0, ts, "compacted", text)
            return
        results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"] \
            if isinstance(content, list) else []
        for b in results:
            if str(b.get("tool_use_id") or "") in self.ask_calls:
                self._ask_row(row)
                break
        for b in results:
            self._settle(b, ts, row)
        if any(S.DELIVERY_RE.search(t) for t in S._delivery_texts(row)):
            self._ask_row(row)    # an async ask's answer
            return
        text = _text(content)
        if not text.strip():
            return
        origin = row.get("origin") if isinstance(row.get("origin"), dict) else None
        kind = origin.get("kind") if origin else None
        if kind == "task-notification":
            self._notification(ts, jobs._plain_notification(row, content) or text)
        elif kind == "peer":
            self._peer(ts, origin, text)
        elif kind == "plugin":
            if origin.get("name") in BRIDGE_PLUGINS:
                self._bridge_row(ts, text, origin.get("asUser") is True, row.get("isMeta") is True)
        elif row.get("isMeta") is True:
            return
        elif kind in OWNER_ORIGINS:
            self._owner(row, ts, text)
        elif kind is None:
            self._unstamped(ts, text)

    def _attachment(self, row):
        att = row.get("attachment") if isinstance(row.get("attachment"), dict) else {}
        ts = row.get("timestamp")
        if att.get("type") == "hook_additional_context":
            if any(S.DELIVERY_RE.search(t) for t in S._delivery_texts(row)):
                self._ask_row(row)
            return
        if att.get("type") != "queued_command":
            return
        prompt = att.get("prompt")
        text = prompt if isinstance(prompt, str) else S._result_text(prompt)
        if not text.strip():
            return
        origin = att.get("origin") if isinstance(att.get("origin"), dict) else None
        kind = origin.get("kind") if origin else None
        if att.get("commandMode") == "task-notification" or kind == "task-notification":
            self._notification(ts, text)
        elif att.get("commandMode") != "prompt":
            return
        elif kind == "peer":
            self._peer(ts, origin, text)
        elif kind in OWNER_ORIGINS:
            self._owner(row, ts, text)
        elif kind is None:
            self._unstamped(ts, text)

    def _owner(self, row, ts, text):
        """A row an affirmative origin says the owner typed."""
        if text.lstrip().startswith(S.COMMAND_ROW_TAGS):
            return
        if any(S._maws_answer(t) for t in S._maws_steer_texts(row)):
            self._ask_row(row)    # a MAWS ask's answer: `answered`
            return
        if row.get("entrypoint") == MAWS_ENTRYPOINT:
            self._add(0, ts, "you·desk", text.strip(), via="composer")
        else:
            self._add(0, ts, "you", text.strip())

    def _unstamped(self, ts, text):
        """A row with no origin stamp: an older transcript's typed prompt reads as one only unverified (`you?`),
        after every frame a row of that era can carry is recognized."""
        stripped = text.strip()
        if stripped.startswith(INTERRUPT_MARKER):
            self._add(0, ts, "interrupted", stripped)
        elif stripped.startswith(S.COMMAND_ROW_TAGS + S.PLUGIN_PROMPTS + SHELL_OUTPUT_TAGS):
            return
        elif stripped.startswith("<task-notification>"):
            self._notification(ts, stripped)
        elif text.startswith(PEER_OPEN) or stripped.startswith("<cross-session-message") or frames(stripped):
            self._peer(ts, None, text)
        elif stripped.split("\n", 1)[0] == STEER_LINE:
            self._add(0, ts, "you·steer", stripped.split("\n", 1)[1].strip() if "\n" in stripped else "")
        else:
            self._add(0, ts, "you?", stripped)

    def _peer(self, ts, origin, text):
        """Another session's message, or a subagent's (a message or hand-back, which the engine also stamps
        `peer`, with the agent's task id): never the owner's."""
        origin = origin or {}
        if origin.get("senderTaskId"):
            report = origin.get("handbackReportText") or origin.get("body") or text
            self._add(0, ts, "agent", "%s: %s" % (origin.get("name") or "subagent", str(report)[:AGENT_RESULT_CHARS]))
            return
        body = text[len(PEER_OPEN):] if text.startswith(PEER_OPEN) else text
        name = origin.get("name") or ""
        m = ENVELOPE_RE.search(body)
        if m:
            name = name or (FROM_NAME_RE.search(m.group(1)) or [None, ""])[1]
            body = m.group(2)
        body = REPLY_LINE_RE.sub("", body).strip()
        fs = frames(body)
        if fs and not name:
            name = fs[0][1]
        self._add(0, ts, "peer", body, **{"from": name or "?"})

    def _bridge_row(self, ts, text, as_user, meta):
        """A row the bridge wrote: a prompt it submitted (`asUser`) or a row it appended into a turn (isMeta):
        a steer, an interrupt's record, a stop's note, a wake, or a delivery."""
        stripped = text.strip()
        first, _, rest = stripped.partition("\n")
        if first == STEER_LINE:
            self._add(0, ts, "you·steer", rest.strip())
        elif stripped == INTERRUPT_MARKER or first in jobs.INTERRUPT_ORIGINS:
            self._add(0, ts, "interrupted", stripped)
        elif stripped.startswith(CUT_OFF_LINE):
            self._add(0, ts, "interrupted", "The interrupt cut off the reply: " + _cut(rest.strip(), CUT_OFF_SHOWN))
        elif jobs.STOP_NOTE.fullmatch(stripped) or AGENT_STOP_RE.match(stripped):
            self._add(0, ts, "notice", stripped)
        elif first == WAKE_LINE:
            self._add(0, ts, "notice", _cut(rest.strip(), TOOL_CHARS))
        elif not (as_user or meta) or stripped.startswith(S.COMMAND_ROW_TAGS + S.PLUGIN_PROMPTS) \
                or stripped.startswith(("<system-reminder>", "(no content)")):
            return
        elif not frames(stripped):
            self._add(0, ts, "you·desk" if self.corroborate(stripped) else "you·desk?", stripped, via="bridge")
        else:
            # One push can carry several frames, each its own sender's: each is classified on its own, so one
            # frame's evidence never vouches for another sender's words.
            for n, (_, sender, _, body, whole) in enumerate(frames(stripped)):
                if sender != "human":
                    self._add(n, ts, "peer", whole, **{"from": sender})
                else:
                    self._add(n, ts, "you·desk" if self.corroborate(whole) else "you·desk?", body.strip(),
                              via="bridge")

    def _notification(self, ts, text):
        summary = jobs._element(text, "summary") or jobs._element(text, "status")
        self._add(0, ts, "notice", _cut(summary or text.strip().split("\n", 1)[0], TOOL_CHARS * 2))


def _blocking_ask(block):
    """Whether a tool call is a question the session waits on: the native AskUserQuestion, the plugin's ask
    called with `async: false`, MAWS's ask unless called with `blocking: false`."""
    name, inp = block.get("name"), block.get("input") if isinstance(block.get("input"), dict) else {}
    return name == NATIVE_ASK or (name in S.ASK_TOOLS and inp.get("async") is False) or \
        (name == S.MAWS_ASK_TOOL and inp.get("blocking") is not False)


def owner_present(entry):
    """Whether an entry shows the owner in the session's own window, for its seen mark: words typed there (`you`,
    a MAWS composer submission) or an answer to a blocking question. Unverified rows, bridge deliveries, steers
    and async answers can come from a phone or another session's view, so they do not count."""
    kind = entry.get("kind")
    return kind == "you" or (kind == "you·desk" and entry.get("via") == "composer") or \
        (kind == "answered" and entry.get("source") == "blocking")


def _question(questions, choices):
    text = "\n".join(q for q in questions if q)
    return text + (" [%s]" % " | ".join(c for c in choices if c) if any(choices) else "")


def classify(rows, session, corroborate=None):
    """The entries of a run of one session's rows (all of them; no budget)."""
    c = Classifier(session, corroborate)
    for row in rows:
        c.feed(row)
    return c.finish()


class Unreadable(Exception):
    """A transcript that could not be opened or mapped (an empty one is not: it holds no rows)."""

    def __init__(self, path, error):
        super().__init__("%s: %s" % (path, error))
        self.path, self.error = path, error


def _map(path):
    """The transcript mapped for reading; None when it is empty; Unreadable when it cannot be read."""
    try:
        with open(path, "rb") as f:
            if os.fstat(f.fileno()).st_size == 0:
                return None
            return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    except (OSError, ValueError) as e:
        raise Unreadable(path, e)


def _rows(mm, start, since, until=None, before=None):
    """The mapped transcript's rows from the seek point `start` stamped at or after `since` and before `until`
    (epoch seconds), in file order; request records and attachments no entry reads passed over unparsed. The
    rows from the seek point up to `since` go to `before` (Classifier.prior) when it is given."""
    pos, end_of = start, len(mm)
    while pos < end_of:
        end = mm.find(b"\n", pos)
        end = end_of if end < 0 else end
        line = mm[pos:end]
        pos = end + 1
        if not line or line.startswith(jobs.REQUEST_RECORD):
            continue
        if b'"type":"attachment"' in line and b'"queued_command"' not in line \
                and b'"hook_additional_context"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        t = SA._epoch(row.get("timestamp"))
        if t is None:
            continue
        if t < since:
            if before is not None:
                before(row)
            continue
        if until is not None and t >= until:
            break
        yield row


def _row_back(mm, uuid, end):
    """The row whose own `uuid` is `uuid`, found by a byte search back from `end` (the seek point), with only
    the line found parsed: request records, which repeat the conversation, and lines that merely quote the id
    are passed over. None when no such row is there."""
    needle, at = ('"uuid":"%s"' % uuid).encode(), end
    while True:
        i = mm.rfind(needle, 0, at)
        if i < 0:
            return None
        start = mm.rfind(b"\n", 0, i) + 1
        if mm[start:start + len(jobs.REQUEST_RECORD)] != jobs.REQUEST_RECORD:
            stop = mm.find(b"\n", i)
            try:
                row = json.loads(mm[start:len(mm) if stop < 0 else stop])
            except ValueError:
                row = None
            if isinstance(row, dict) and row.get("uuid") == uuid:
                return row
        at = start


def _first_epoch(path):
    """The time of a transcript's first stamped row; None when it holds none."""
    mm = _map(path)
    if mm is None:
        return None
    try:
        first = next(_rows(mm, 0, float("-inf")), None)
    finally:
        mm.close()
    return SA._epoch(first.get("timestamp")) if first is not None else None


def ended_before(sessions, i, since):
    """Whether the records prove the lineage's session `i` ended before `since`: a later session of the lineage
    has a transcript whose first row is at or before it, so the lineage had moved on before the window began
    (the engine prunes old transcripts, so a long-lived lineage loses its oldest ones)."""
    for _, path in sessions[i + 1:]:
        if path:
            first = _first_epoch(path)
            if first is not None and first <= since:
                return True
    return False


def window(sessions, since, until=None, max_chars=DEFAULT_MAX_CHARS, corroborate=None):
    """{"entries", "truncated", "stopped_at", "missing"}: the window over a lineage (`sessions`: (session id,
    transcript path or ""), oldest first), a `boundary` entry where it moves to the next session id, cut where
    the rendered text would pass `max_chars` (stopped_at: the last entry's time; missing: the lineage's sessions
    with no transcript on this machine that the window could include, those proven to have ended before `since`
    left out). A transcript that cannot be read raises Unreadable."""
    entries, used, truncated, previous = [], 0, False, None
    missing = [sid for i, (sid, path) in enumerate(sessions) if not path and not ended_before(sessions, i, since)]
    for sid, path in sessions:
        if not path:
            continue
        mm = _map(path)
        if mm is None:
            continue
        try:
            start = SA.offset_since(mm, since)
            c = Classifier(sid, corroborate, lookup=lambda uuid, mm=mm, start=start: _row_back(mm, uuid, start))
            for row in _rows(mm, start, since, until, before=c.prior):
                c.feed(row)
                if used + c.chars > max_chars:
                    truncated = True
                    break
            got = c.finish()
        finally:
            mm.close()
        if got:
            if previous is not None:
                b = {"ts": got[0]["ts"], "session": sid[:8], "kind": "boundary",
                     "text": "continued in %s (from %s)" % (sid[:8], previous[:8])}
                entries.append(b)
                used += len(render(b)) + 1
            entries += got
            used += sum(len(render(e)) + 1 for e in got)
            previous = sid
        if truncated:
            break
    out, size = [], 0
    for e in entries:
        n = len(render(e)) + 1
        if size + n > max_chars:
            truncated = True
            break
        out.append(e)
        size += n
    return {"entries": out, "truncated": truncated, "stopped_at": out[-1]["ts"] if truncated and out else None,
            "missing": missing}
