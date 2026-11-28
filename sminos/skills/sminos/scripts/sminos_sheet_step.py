"""The question sheet's step, as a pure function, and what leaves the record composed from it (the plan
docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md: "The state machine", I5, I6, I7 and I10).

    apply(state, data, event, now, session, surface) -> (state, effects, writes)

takes a record's `state.json` (None for a session with none: only a `start` makes one), the inbox's bytes from the
recorded offset, an event already read whole (the shell, `sminos_sheet.run_step`, resolves what the mod staged into
the inline form below), the step's clock, the session's id and the surface that suits it (None for none). It
returns the new state (a copy: the input is not touched), the step's effects (I5) and the files the step owes the
record before its replace ({path under the record: bytes}: `refs/` bodies and `texts/` files). It reads no file and
writes none: the lock, the staging, the replace and the answer are the shell's.

A normalized event is I5's `in` with `call` holding the call's body: {callId, floor?, asker, entries, withdraw},
each entry {"refused": "<clause after 'entry <n>, '>"} or {"entry": <the tool's entry>, "captures": [Capture with
`body` bytes in place of its file]}; and `start.today.asks` holding the asks themselves.

The composers read a state and write nothing: `view` (I5's View), `envelope` (I7: one recipient's next envelope),
`context` (I10). Times a model reads are the machine's local time unless a zone is given.
"""

import copy
import datetime
import hashlib
import json

import sminos_sheet as SH

OPEN_MAX = 500                # U7
TEXT_FILE_PAST = 2000         # a text longer than this has a file under texts/ (I7)
ANSWER_KEPT = 32              # Closed.answer is kept on the questions answered last (I2, I13)
BUDGET = 60000                # an envelope's, and the context's, UTF-16 code units (I7)
ENVELOPE_KEYS = 200           # what one `delivered` line can name (I3)
BLOCK_TEXT = 500              # the block's text, and a filed text's head in the prose (I7)
PROSE_CUT = 200               # a question, a label, a name in the envelope's prose
VIEW_PENDING, VIEW_CLOSED, VIEW_READY = 200, 500, 4
BEFORE_KEYS = 200             # effects.start.before: the first of what was pending, beside its count
IMPORT_BUDGET = 10000         # the context's import summary, in UTF-16 units, inside the context's own budget
CUT_VIEW_QUESTION, CUT_VIEW_HEADER, CUT_VIEW_RECEIPT = 300, 60, 200
CLAUSE_PATH, CLAUSE_REASON, CLAUSE_MOD = 200, 500, 500     # a refusal clause's free text: a path, a reason, the mod's
NOT_DONE_MAX = 32000          # a result's `Not done:` line: every entry's clause, then the withdrawals' while they fit
RESULT_MAX = 40000            # what that makes a call's result at most, in characters (I6): 20 entries, 500 withdrawn
CONTEXT_QUESTION, CONTEXT_LABEL = 300, 80
EVENTS = ("start", "drain", "call", "settle", "landed", "reroute")
SOURCES = ("startup", "resume", "fork", "clear")

NO_SURFACE = "No surface can show these questions right now; they wait on the sheet and show when one returns."
SUBAGENT_OPENING = ("From the human, through the question tool, not from your coordinator: answers to questions "
                    "you put on the sheet.")
HEAD_ANSWERED = "[sheet v1] The human answered questions on your sheet."
HEAD_DISMISSED = "[sheet v1] The human dismissed questions on your sheet; no answer will come for them."
MORE = " More follows."
FORK_LINE = ("[sheet v1] This conversation is a copy: its question sheet starts empty. Questions asked before the "
             "copy belong to the conversation it was copied from, and their answers will not come here; ask again "
             "what you still need.")
LOST_LINE = ("[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked "
             "earlier are no longer open.")


class BadEvent(Exception):
    pass


# ------------------------------------------------------------------ small parts


def jstr(s):
    return json.dumps(s, ensure_ascii=False)


def units(text):
    """UTF-16 code units: the larger of the ways to count a string (K5)."""
    return len(text.encode("utf-16-le")) // 2


def mark(s, n):
    """The prose's cut: the first n characters and `…` (I7)."""
    return s[:n] + "…" if len(s) > n else s


def idnum(i):
    return int(i[1:])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same(a, b):
    """Two askers or recipients are one: both the main conversation, or both the agent with one id."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.get("agentId") == b.get("agentId")
    return a == b == "main"


def when(iso):
    return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=datetime.timezone.utc)


def local(iso, tz, fmt):
    """A record's UTC time in the machine's zone (tz None) or the one given, as a model reads it. A stored time the
    line's pattern let through that is no calendar time (2026-02-30) is written as it was stored: no composer fails
    on a record's time."""
    try:
        t = when(iso)
        return (t.astimezone(tz) if tz is not None else t.astimezone()).strftime(fmt)
    except (ValueError, OverflowError, OSError):
        return iso


def defuse(v):
    """A value with every lone UTF-16 surrogate written as U+FFFD: what an import keeps (M2)."""
    return SH.printable(v)


def snapshot(q):
    """An outcome's copy of its question at the revision it answered (I2)."""
    s = {"asker": q["asker"], "question": q["question"], "options": [o["label"] for o in q["options"]],
         "multiSelect": q["multiSelect"], "askedAt": q["askedAt"]}
    if "header" in q:
        s["header"] = q["header"]
    return s


def said(snap, picks, text):
    """I7's line after the id, in its full-text form (no asker, no times): what Closed.answer (its first 2,000) and
    the log's `answered` event (whole) keep of an answer."""
    head = jstr(mark(snap["question"], PROSE_CUT)) + " → "
    labels = [mark(p, PROSE_CUT) for p in picks]
    if labels:
        return head + ", ".join(labels) + "." + (" Their text: " + jstr(text) if text else "")
    return head + "their text: " + jstr(text)


def places(snap, picks):
    labels = snap["options"]
    return [labels.index(p) + 1 for p in picks if p in labels]


def owe(st, entry):
    st["log"]["owed"].append(dict({"n": st["log"]["next"]}, **entry))
    st["log"]["next"] += 1


def src(session, id_):
    return "sheet:%s:%s" % (session, id_)


def owe_question(st, session, q):
    owe(st, {"kind": "question", "src": src(session, q["id"]), "text": [q["question"]],
             "choices": [o["label"] for o in q["options"]]})


def owe_closing(st, session, id_, how):
    owe(st, {"kind": "answered", "src": src(session, id_), "text": how, "closed": how})


def closed_base(q, how, now):
    c = {"how": how, "at": now, "revision": q["revision"], "asker": q["asker"], "question": q["question"][:200]}
    if "header" in q:
        c["header"] = q["header"]
    return c


def closed_order(st):
    """The closed questions' ids, oldest closing first: by when, then in the order they closed, which the record's
    `closed` keeps (a step adds a closing at its end and writes the object in order; a record written by another
    hand, sorted by key, breaks ties by that order instead)."""
    pos = {i: n for n, i in enumerate(st["closed"])}
    return sorted(st["closed"], key=lambda i: (st["closed"][i]["at"], pos[i]))


def find_open(st, id_):
    return next((q for q in st["questions"] if q["id"] == id_), None)


def empty_record(session):
    return {"v": 1, "session": session, "seq": 0, "nextId": 1, "inbox": {"offset": 0, "skipped": 0},
            "questions": [], "pending": [], "closed": {}, "verdicts": {}, "calls": [],
            "log": {"next": 1, "owed": [], "projects": {}}, "import": {"never": False, "calls": {}}}


# ------------------------------------------------------------------ the drain (§4.2, in the plan's order)


def drain(st, data, event, now, session, fx, writes, answered_now):
    end = data.rfind(b"\n")
    if end < 0:
        return
    raws = data[:end].split(b"\n")
    st["inbox"]["offset"] += end + 1      # just past the last newline: what follows is a write not finished
    asked = list(st["questions"])         # picks are judged as a reader judges them: against the questions read
    verdicts = st["verdicts"]
    seen, remaining, skipped = set(), [], 0
    for raw in raws:                      # 1. not valid: skipped (U2); 2. a key known or met: set aside
        try:
            line = SH.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            skipped += 1
            continue
        if SH.line_error(line) or SH.pick_error(line, asked):
            skipped += 1
            continue
        if line["key"] in verdicts or line["key"] in seen:
            seen.add(line["key"])
            continue
        seen.add(line["key"])
        remaining.append(line)
    st["inbox"]["skipped"] += skipped
    fx["skipped"] += skipped

    by_key = {x["key"]: x for x in remaining}
    cancelled = set()
    for r in remaining:                   # 3. retracts, before anything is applied
        if r["kind"] != "retract":
            continue
        k = r["target"]
        if k in verdicts or by_key.get(k, {}).get("kind") in ("retract", "delivered"):
            verdicts[r["key"]] = {"verdict": "too-late", "kind": "retract", "at": now, "target": k}
        elif k in by_key:
            cancelled.add(k)
            verdicts[k] = {"verdict": "retracted", "kind": by_key[k]["kind"], "at": now, "id": by_key[k]["id"]}
            verdicts[r["key"]] = {"verdict": "retracted", "kind": "retract", "at": now, "target": k}
        else:                             # U1: cancelled in advance, should it arrive
            verdicts[k] = {"verdict": "retracted", "kind": "unseen", "at": now, "by": r["key"]}
            verdicts[r["key"]] = {"verdict": "retracted", "kind": "retract", "at": now, "target": k}

    for line in remaining:                # 4. what remains, in file order
        if line["kind"] == "retract" or line["key"] in cancelled:
            continue
        key, kind = line["key"], line["kind"]
        if kind == "delivered":
            for k in line["keys"]:
                deliver(st, k, now)
            verdicts[key] = {"verdict": "applied", "kind": "delivered", "at": now}
            continue
        id_ = line["id"]
        q = find_open(st, id_)
        if q is None:
            how = st["closed"][id_]["how"] if id_ in st["closed"] else "unknown"
            verdicts[key] = {"verdict": "closed", "kind": kind, "at": now, "id": id_, "how": how}
        elif kind == "answer" and q["revision"] != line["revision"]:
            verdicts[key] = {"verdict": "stale", "kind": "answer", "at": now, "id": id_, "current": q["revision"]}
        else:
            accept(st, q, line, event, now, session, fx, writes, answered_now)
            verdicts[key] = {"verdict": "applied", "kind": kind, "at": now, "id": id_}


def recipient_of(q, event):
    """A subagent asker running and reachable directly takes its own outcome; anything else is the main
    conversation's."""
    agents = event.get("agents") or {}
    a = q["asker"]
    if isinstance(a, dict) and agents.get("direct") and a["agentId"] in (agents.get("running") or []):
        return {"agentId": a["agentId"]}, True
    return "main", False


def accept(st, q, line, event, now, session, fx, writes, answered_now):
    snap = snapshot(q)
    recipient, taken = recipient_of(q, event)
    o = {"key": line["key"], "kind": line["kind"], "id": q["id"], "revision": q["revision"], "by": line["by"],
         "at": line.get("at", now), "acceptedAt": now, "recipient": recipient, "taken": taken,
         "acrossStop": event["event"] == "start", "question": snap}
    if "batch" in line:
        o["batch"] = line["batch"]
    st["questions"].remove(q)
    if line["kind"] == "answer":
        picks, text = list(line.get("picks") or []), line.get("text") or ""
        o.update(picks=picks, text=text, images=list(line.get("images") or []))
        if len(text) > TEXT_FILE_PAST:
            o["textFile"] = "texts/%s.txt" % sha(text.encode())
            writes[o["textFile"]] = text.encode()
        line_after = said(snap, picks, text)
        c = closed_base(q, "answered", now)
        c.update(receipt=", ".join(picks) if picks else text[:80], places=places(snap, picks), key=line["key"],
                 answer=line_after[:2000])
        st["closed"][q["id"]] = c
        answered_now.append(q["id"])
        owe(st, {"kind": "answered", "src": src(session, q["id"]), "text": line_after})
    else:
        st["closed"][q["id"]] = dict(closed_base(q, "dismissed", now), key=line["key"])
        owe_closing(st, session, q["id"], "dismissed")
    st["pending"].append(o)
    fx["applied"].append(line["key"])


def deliver(st, key, now):
    o = next((x for x in st["pending"] if x["key"] == key), None)
    if o is None:
        return
    st["pending"].remove(o)
    if o["id"] in st["closed"]:
        st["closed"][o["id"]]["deliveredAt"] = now


def keep_answers(st, answered_now):
    """The answer's line stays on the 32 questions answered last; the oldest of more lose it (I2)."""
    holders = [i for i in closed_order(st) if "answer" in st["closed"][i] and i not in answered_now] + answered_now
    for i in holders[:max(0, len(holders) - ANSWER_KEPT)]:
        del st["closed"][i]["answer"]


# ------------------------------------------------------------------ a call (I6)


def entry_problem(e):
    """An entry's own refusal (U14), as the clause after `entry <n>, `, or None."""
    if SH._surrogate(e):
        return "a string holds a lone UTF-16 surrogate"
    labels = [o["label"] for o in e.get("options") or []]
    seen = set()
    for label in labels:
        if label in seen:
            return 'two options share the label "%s"' % label[:200]
        seen.add(label)
    if e.get("multiSelect") and any("preview" in o for o in e.get("options") or []):
        return "an option's preview needs a single-select question"
    if e.get("multiSelect") and not labels:
        return "multiSelect needs options"
    for r in e.get("references") or []:
        if "lines" in r and not (1 <= r["lines"][0] <= r["lines"][1]):
            return "lines must be [a, b] with 1 <= a <= b"
    return None


def _str(v):
    return isinstance(v, str)


def _int(v, least=0):
    return isinstance(v, int) and not isinstance(v, bool) and v >= least


def entry_shape_error(e):
    """Why an entry is not the tool's entry in structure (the mod validated the whole call; a shell's inline call
    meets this instead), or None. Bounds are the input's, checked by the mod (I6): a record states structure."""
    if not isinstance(e, dict):
        return "an entry is an object"
    extra = set(e) - {"id", "question", "header", "options", "multiSelect", "context", "references"}
    if extra:
        return "an entry has no field %s" % sorted(extra)[0]
    if "id" in e and not (_str(e["id"]) and SH.ID_RE.fullmatch(e["id"])):
        return "an entry's id is q<n>"
    if not (_str(e.get("question")) and e["question"]):
        return "an entry has a question"
    for f in ("header", "context"):
        if f in e and not _str(e[f]):
            return "an entry's %s is a string" % f
    if "multiSelect" in e and not isinstance(e["multiSelect"], bool):
        return "multiSelect is a boolean"
    opts = e.get("options", [])
    if not isinstance(opts, list):
        return "options are a list"
    for o in opts:
        if not (isinstance(o, dict) and _str(o.get("label")) and set(o) <= {"label", "description", "preview",
                                                                            "recommended"}
                and all(_str(o[f]) for f in ("description", "preview") if f in o)
                and isinstance(o.get("recommended", False), bool)):
            return "an option is {label, description?, preview?, recommended?}"
    refs = e.get("references", [])
    if not isinstance(refs, list):
        return "references are a list"
    for r in refs:
        if not (isinstance(r, dict) and _str(r.get("path")) and r["path"] and set(r) <= {"path", "lines"}):
            return "a reference is {path, lines?}"
        if "lines" in r and not (isinstance(r["lines"], list) and len(r["lines"]) == 2
                                 and all(isinstance(n, int) and not isinstance(n, bool) for n in r["lines"])):
            return "a reference's lines are two integers"
    return None


def capture_error(c):
    if not isinstance(c, dict):
        return "a capture is an object"
    if c.get("ok") is False:
        return None if _str(c.get("reason")) else "a refused capture names its reason"
    if not (_str(c.get("abs")) and c["abs"] and c.get("kind") in ("text", "image") and isinstance(c.get("body"), bytes)
            and isinstance(c.get("size"), (int, float)) and isinstance(c.get("mtimeMs"), (int, float))):
        return "a capture is {ok, abs, kind, body, size, mtimeMs}"
    if c["kind"] == "text" and not all(_int(c.get(f), 0) for f in ("startLine", "numLines", "totalLines")):
        return "a text capture has startLine, numLines and totalLines"
    if c["kind"] == "image" and not _str(c.get("mediaType")):
        return "an image capture has mediaType"
    return None


def asker_name(a):
    return "the main conversation" if a == "main" else "the subagent %s" % mark(a.get("name", a.get("agentId")),
                                                                              PROSE_CUT)


def not_open(st, id_, tz):
    c = st["closed"].get(id_)
    if c is None:
        return "%s is not open (never asked)" % id_
    return "%s is not open (%s at %s)" % (id_, c["how"], local(c["at"], tz, "%H:%M"))


def reference(ref, cap, writes):
    body = cap["body"]
    h = sha(body)
    writes["refs/" + h] = body
    r = {"path": ref["path"], "abs": cap["abs"], "sha256": h, "bytes": len(body), "kind": cap["kind"],
         "size": int(cap["size"]), "mtimeMs": int(cap["mtimeMs"])}
    if "lines" in ref:
        r["lines"] = list(ref["lines"])
    if cap["kind"] == "text":
        r.update(startLine=cap["startLine"], numLines=cap["numLines"], totalLines=cap["totalLines"])
    else:
        r["mediaType"] = cap["mediaType"]
    return r


def question_of(e, id_, revision, asker, now, call_id, refs):
    q = {"id": id_, "revision": revision, "asker": asker, "question": e["question"],
         "options": [{f: o[f] for f in ("label", "description", "preview", "recommended") if f in o}
                     for o in e.get("options") or []],
         "multiSelect": bool(e.get("multiSelect", False)), "references": refs, "askedAt": now, "callId": call_id}
    for f in ("header", "context"):
        if f in e:
            q[f] = e[f]
    return q


def run_call(st, call, now, session, surface, tz, fx, writes):
    call_id, asker = call["callId"], call["asker"]
    if not st["questions"] and not st["closed"] and call.get("floor") is not None:
        st["nextId"] = max(st["nextId"], call["floor"] + 1)     # the conversation's ids are not used again
    added, revised, withdrew, clauses, refusals = [], [], [], [], []
    for n, item in enumerate(call["entries"], 1):
        if "refused" in item:
            clauses.append("entry %d, %s" % (n, mark(item["refused"], CLAUSE_MOD)))
            continue
        e, caps = item["entry"], item["captures"]
        why = entry_problem(e) or next(("the reference %s could not be read: %s"
                                        % (mark(r["path"], CLAUSE_PATH), mark(c["reason"], CLAUSE_REASON))
                                        for r, c in zip(e.get("references") or [], caps) if c.get("ok") is False),
                                       None)
        if why is None and "id" in e:
            q = find_open(st, e["id"])
            if q is None:
                why = not_open(st, e["id"], tz)
            elif not same(q["asker"], asker):
                why = "%s was asked by %s; only its asker revises it" % (e["id"], asker_name(q["asker"]))
        elif why is None and len(st["questions"]) >= OPEN_MAX:
            why = "the sheet holds %d open questions" % OPEN_MAX
        if why is not None:
            clauses.append("entry %d, %s" % (n, why))
            continue
        refs = [reference(r, c, writes) for r, c in zip(e.get("references") or [], caps)]
        if "id" in e:
            q = find_open(st, e["id"])
            new = question_of(e, q["id"], q["revision"] + 1, q["asker"], now, call_id, refs)
            st["questions"][st["questions"].index(q)] = new
            revised.append((new["id"], n, new["revision"]))
        else:
            new = question_of(e, "q%d" % st["nextId"], 1, asker, now, call_id, refs)
            st["nextId"] += 1
            st["questions"].append(new)
            owe_question(st, session, new)
            added.append((new["id"], n))
    for id_ in call.get("withdraw") or []:
        q = find_open(st, id_)
        if q is None:
            refusals.append(not_open(st, id_, tz))
        elif not (same(q["asker"], asker) or asker == "main"):
            refusals.append("%s was asked by %s; only its asker or the main conversation withdraws it"
                            % (id_, asker_name(q["asker"])))
        else:
            st["questions"].remove(q)
            st["closed"][id_] = closed_base(q, "withdrawn", now)
            owe_closing(st, session, id_, "withdrawn")
            withdrew.append(id_)
    numbered = bool(clauses or refusals)
    sentences = []
    if added:
        sentences.append("Added %s." % ", ".join(i + (" (entry %d)" % n if numbered else "") for i, n in added))
    if revised:
        sentences.append("Revised %s." % ", ".join("%s (%srevision %d)" % (i, "entry %d, " % n if numbered else "", r)
                                                   for i, n, r in revised))
    if withdrew:
        sentences.append("Withdrew %s." % ", ".join(withdrew))
    lines = [" ".join(sentences) or "Nothing done."]
    if clauses or refusals:
        # Every entry's clause, each bounded; then the withdrawals' while the line holds, and how many more.
        line = "Not done: " + " ".join(c + "." for c in clauses)
        k = 0
        while k < len(refusals) and len(line) + 2 + len(refusals[k]) <= NOT_DONE_MAX:
            line += (" " if clauses or k else "") + refusals[k] + "."
            k += 1
        if k < len(refusals):
            line += " And %d more withdrawals not done." % (len(refusals) - k)
        lines.append(line)
    if surface is None:
        lines.append(NO_SURFACE)
    result = "\n".join(lines)
    st["calls"].append({"callId": call_id, "result": result})
    return result


def recorded(st, call_id):
    return next((c for c in st["calls"] if c["callId"] == call_id), None)


def call_effects(fx, c):
    if c.get("foreclosed"):
        fx["foreclosed"] = True
    else:
        fx["result"] = c["result"]


# ------------------------------------------------------------------ a start (and today's asks)


def import_asks(st, asks, session, fx):
    for ask in asks:
        call_id = ask["callId"]
        if call_id in st["import"]["calls"]:
            continue
        ids = []
        for i, x in enumerate(ask.get("questions") or []):
            x = defuse(x)
            q = {"id": "q%d" % st["nextId"], "revision": 1, "asker": "main", "question": str(x.get("question", "")),
                 "options": [{f: o[f] for f in ("label", "description", "preview", "recommended") if f in o}
                             for o in x.get("options") or [] if isinstance(o, dict) and _str(o.get("label"))],
                 "multiSelect": bool(x.get("multiSelect", False)), "references": [],
                 "askedAt": ask["askedAt"], "callId": call_id, "importedFrom": {"callId": call_id, "index": i}}
            if _str(x.get("header")):
                q["header"] = x["header"]
            st["nextId"] += 1
            st["questions"].append(q)
            owe_question(st, session, q)
            ids.append(q["id"])
        st["import"]["calls"][call_id] = ids
        fx["start"]["imported"].append({"callId": call_id, "ids": ids})


def run_start(st, start, new, session, fx):
    floor = start.get("floor")
    if floor is not None and not st["questions"] and not st["closed"]:
        st["nextId"] = max(st["nextId"], floor + 1)
    if new and start["source"] == "fork":
        st["import"]["never"] = True
    if new and start["source"] == "fork":
        fx["start"]["empty"] = "fork"
    elif new and start["source"] == "resume" and floor:
        fx["start"]["empty"] = "lost"
    st["calls"] = []
    for o in st["pending"]:
        o.update(acrossStop=True, recipient="main", taken=False)
    today = start.get("today") or {}
    # With the conversation's ids unknown (the mod's floor search failed: `floorUnknown`, which no published event
    # carries), an import goes only into a record whose next id is past them, one that has assigned an id; otherwise
    # nothing is imported or recorded, and the next start reads again.
    if today.get("definite") and not st["import"]["never"] and not (today.get("floorUnknown") and st["nextId"] == 1):
        import_asks(st, today.get("asks") or [], session, fx)
    again = start.get("again")
    if again is not None:
        # The same start ordered again (its nonce is the receipt's): what the record cannot say again comes from the
        # receipt, the empty sheet the first found and what it imported, where the record still holds those ids.
        # What this attempt imported itself (the first's replace never landed) stands; `before` is never the receipt's.
        fx["start"]["empty"] = again["empty"]
        mine = {x["callId"] for x in fx["start"]["imported"]}
        fx["start"]["imported"] += [x for x in again["imported"] if x["callId"] not in mine
                                    and st["import"]["calls"].get(x["callId"]) == x["ids"]]


# ------------------------------------------------------------------ the step


def apply(state, data, event, now, session, surface=None, tz=None):
    name = event["event"]
    new = state is None
    st = empty_record(session) if new else copy.deepcopy(state)
    fx = {"applied": [], "skipped": 0, "verdicts": {}}
    writes, answered_now = {}, []
    if name == "start":
        before = [o["key"] for o in st["pending"]]
        fx["start"] = {"empty": None, "before": before[:BEFORE_KEYS], "beforeCount": len(before), "imported": []}
    drain(st, data, event, now, session, fx, writes, answered_now)
    keep_answers(st, answered_now)
    acked = set(event.get("acked") or [])
    st["calls"] = [c for c in st["calls"] if c["callId"] not in acked]
    keys = event.get("keys") or []
    if name == "call":
        c = recorded(st, event["call"]["callId"])
        if c is not None:
            call_effects(fx, c)
        else:
            fx["result"] = run_call(st, event["call"], now, session, surface, tz, fx, writes)
    elif name == "settle":
        call_id = event["call"]["callId"]
        c = recorded(st, call_id)
        if c is None:
            c = {"callId": call_id, "foreclosed": True}
            st["calls"].append(c)
        call_effects(fx, c)
    elif name == "landed":
        for k in keys:
            deliver(st, k, now)
    elif name == "reroute":
        for o in st["pending"]:
            if o["key"] in keys:
                o.update(recipient="main", taken=False)
    elif name == "start":
        run_start(st, event["start"], new, session, fx)
    if "agents" in event:
        running = set(event["agents"].get("running") or [])
        for o in st["pending"]:
            if isinstance(o["recipient"], dict) and o["recipient"]["agentId"] not in running:
                o.update(recipient="main", taken=False)
    fx["verdicts"] = {k: st["verdicts"][k] for k in keys if k in st["verdicts"]}
    fx["owed"] = len(st["log"]["owed"])
    return st, fx, writes


# ------------------------------------------------------------------ the envelope (I7)


def mine(st, recipient):
    return [o for o in st["pending"] if same(o["recipient"], recipient)]


def wakes(o):
    return o["kind"] == "answer" and not o["acrossStop"]


def is_answer(o):
    return o["kind"] == "answer"


def batches(outs, answers_first=False):
    """What is pending for one recipient as batches (an outcome with no batch is one alone), those that hold an
    outcome that wakes first, or with `answers_first` those that hold an answer, each group in the order accepted."""
    groups, order = {}, []
    for o in outs:
        b = o.get("batch") or ("\0" + o["key"])
        if b not in groups:
            groups[b] = []
            order.append(b)
        groups[b].append(o)
    out = [groups[b] for b in order]
    leads = is_answer if answers_first else wakes
    return [g for g in out if any(leads(o) for o in g)] + [g for g in out if not any(leads(o) for o in g)]


def block(obj):
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"),
                    (" ", "\\u2029")):
        text = text.replace(ch, esc)
    return "<sheet-delivery>" + text + "</sheet-delivery>"


def answer_line(o, recipient, filed, where, tz, running):
    s = o["id"]
    q = o["question"]
    a = q["asker"]
    if recipient == "main" and isinstance(a, dict):
        s += " (from the subagent %s, %s, %s)" % (mark(str(a.get("name", "")), PROSE_CUT), a["agentId"],
                                                  "which could not be sent it" if a["agentId"] in running
                                                  else "which has ended")
    if o["acrossStop"]:
        s += " (asked %s, answered %s, while this session was stopped)" % (
            local(q["askedAt"], tz, "%Y-%m-%d %H:%M"), local(o["at"], tz, "%Y-%m-%d %H:%M"))
    labels = [mark(p, PROSE_CUT) for p in o["picks"]]
    text = o["text"]
    if o["key"] in filed:
        tail = "their text, {:,} characters, is in {} and begins: {}".format(
            len(text), where + "/" + o["textFile"], jstr(text[:BLOCK_TEXT] + "…"))
        body = ", ".join(labels) + ". T" + tail[1:] if labels else tail
    elif labels:
        body = ", ".join(labels) + "." + (" Their text: " + jstr(text) if text else "")
    else:
        body = "their text: " + jstr(text)
    return "%s %s → %s" % (s, jstr(mark(q["question"], PROSE_CUT)), body)


def envelope_text(outs, filed, recipient, more, where, tz, running):
    ans = sorted((o for o in outs if o["kind"] == "answer"), key=lambda o: idnum(o["id"]))
    dis = sorted((o for o in outs if o["kind"] == "dismiss"), key=lambda o: idnum(o["id"]))
    lines = [] if recipient == "main" else [SUBAGENT_OPENING]
    lines.append((HEAD_ANSWERED if ans else HEAD_DISMISSED) + (MORE if more else ""))
    answered = []
    for o in ans:
        lines.append(answer_line(o, recipient, filed, where, tz, running))
        images = [where + "/" + i for i in o["images"]]
        lines += ["[Image source: %s]" % i for i in images]
        b = {"id": o["id"], "revision": o["revision"], "picks": places(o["question"], o["picks"]),
             "text": o["text"][:BLOCK_TEXT]}
        if len(o["text"]) > BLOCK_TEXT:
            b["textCut"] = True
        if "textFile" in o:
            b["textFile"] = where + "/" + o["textFile"]
        b["images"] = images
        answered.append(b)
    if dis:
        lines.append("Dismissed: %s." % ", ".join(o["id"] for o in dis))
    blk = {"v": 1, "keys": [o["key"] for o in ans] + [o["key"] for o in dis], "answered": answered,
           "dismissed": [o["id"] for o in dis]}
    if more:
        blk["more"] = True
    lines.append(block(blk))
    return "\n".join(lines)


def envelope(st, recipient, where, tz=None, running=(), answers_first=False):
    """The next envelope for one recipient (I7), packed from what is pending for it, or None: {recipient, keys, text,
    wakes, more}. `where` is the record's absolute path, which names its texts and images. `answers_first` packs the
    batches that hold an answer first, and a first batch that has to be cut its answers before its dismissals: what
    a MAWS-run session's main conversation is given (MAWS's C5, F33), so its envelope names an answer while one is
    pending, which is what fills MAWS's ring; nothing else asks for it."""
    outs = mine(st, recipient)
    if not outs:
        return None
    running = set(running)
    total = len(outs)

    def fits(chosen, filed):
        more = len(chosen) < total
        text = envelope_text(chosen, filed, recipient, more, where, tz, running)
        return text if units(text) <= BUDGET and len(chosen) <= ENVELOPE_KEYS else None

    chosen, filed, text = [], set(), None
    for i, b in enumerate(batches(outs, answers_first)):
        t = fits(chosen + b, filed)
        if t is not None:
            chosen, text = chosen + b, t
            continue
        if i == 0:
            # 2. the first batch does not fit whole: its longest texts that have a file go by head and file
            for o in sorted((o for o in b if "textFile" in o), key=lambda o: -len(o["text"])):
                filed.add(o["key"])
                t = fits(b, filed)
                if t is not None:
                    chosen, text = b, t
                    break
            else:
                # 3. still not: the batch's outcomes in order while they fit (one always does), its answers first where
                # they are to lead
                for o in (sorted(b, key=lambda o: not is_answer(o)) if answers_first else b):
                    t = fits(chosen + [o], filed)
                    if t is None and chosen:
                        break
                    chosen, text = chosen + [o], t
                if text is None:
                    text = envelope_text(chosen, filed, recipient, len(chosen) < total, where, tz, running)
        break
    ans = sorted((o for o in chosen if o["kind"] == "answer"), key=lambda o: idnum(o["id"]))
    dis = sorted((o for o in chosen if o["kind"] == "dismiss"), key=lambda o: idnum(o["id"]))
    return {"recipient": recipient, "keys": [o["key"] for o in ans + dis], "text": text,
            "wakes": any(wakes(o) for o in chosen), "more": len(chosen) < total}


def ready(st, runner, where, tz=None, running=()):
    """The ready envelopes: the main conversation's, then each subagent's that has outcomes taken; at most four
    recipients. In both runners the tool delivers (MAWS's C5, F8); under runner `maws` the main conversation's
    envelope leads with its answers (F33)."""
    recipients = ["main"]
    for o in st["pending"]:
        r = o["recipient"]
        if isinstance(r, dict) and o["taken"] and not any(same(r, x) for x in recipients):
            recipients.append({"agentId": r["agentId"]})
    out = []
    for r in recipients:
        if len(out) == VIEW_READY:
            break
        e = envelope(st, r, where, tz, running, answers_first=runner == "maws" and r == "main")
        if e is not None:
            out.append(e)
    return out


# ------------------------------------------------------------------ the view (I5)


def view(st, runner, where, surface, alive, tz=None, running=()):
    def asker(a):
        return a if a == "main" else {"agentId": a["agentId"], "name": str(a.get("name", ""))[:200]}

    opened = []
    for q in st["questions"]:
        v = {"id": q["id"], "revision": q["revision"], "asker": asker(q["asker"]),
             "question": q["question"][:CUT_VIEW_QUESTION], "askedAt": q["askedAt"]}
        if "header" in q:
            v["header"] = q["header"][:CUT_VIEW_HEADER]
        opened.append(v)
    order = closed_order(st)
    closed = {}
    for i in order[-VIEW_CLOSED:]:
        c = st["closed"][i]
        v = {"how": c["how"], "revision": c["revision"]}
        if "header" in c:
            v["header"] = c["header"][:CUT_VIEW_HEADER]
        if "receipt" in c:
            v["receipt"] = c["receipt"][:CUT_VIEW_RECEIPT]
        closed[i] = v
    answered = []
    for i in [i for i in order if "answer" in st["closed"][i]][-ANSWER_KEPT:]:
        c = st["closed"][i]
        v = {"id": i, "question": c["question"][:CUT_VIEW_QUESTION], "answer": c["answer"]}
        if "header" in c:
            v["header"] = c["header"][:CUT_VIEW_HEADER]
        answered.append(v)
    return {"seq": st["seq"], "offset": st["inbox"]["offset"], "nextId": st["nextId"], "open": opened,
            "pending": [{"key": o["key"], "id": o["id"], "kind": o["kind"], "recipient": o["recipient"],
                         "taken": o["taken"], "acrossStop": o["acrossStop"]} for o in st["pending"][:VIEW_PENDING]],
            "pendingCount": len(st["pending"]),
            "owedAcrossStop": sum(1 for o in st["pending"] if o["acrossStop"]),
            "closed": closed, "answered": answered,
            "answeredCount": sum(1 for c in st["closed"].values() if c["how"] == "answered"),
            "ready": ready(st, runner, where, tz, running),
            "surface": None if surface is None else {f: surface[f] for f in ("name", "url", "reach")},
            "surfaces": alive}


# ------------------------------------------------------------------ the context at a start (I10)


def question_line(lead, id_, revision, asker, header, question, labels, qcut=None, lcut=None):
    s = "%s %s (revision %d)" % (lead, id_, revision)
    if isinstance(asker, dict):
        s += ", asked by the subagent %s (%s)" % (mark(str(asker.get("name", "")), PROSE_CUT), asker["agentId"])
    if header is not None:
        s += " " + jstr(header)
    s += " — " + jstr(mark(question, qcut) if qcut else question)
    if labels:
        s += " Options: %s." % "; ".join("%d. %s" % (n, mark(x, lcut) if lcut else x) for n, x in enumerate(labels, 1))
    else:
        s += " No options: answered in text."
    return s


def moved(qs, session):
    """The import's summary line, at most IMPORT_BUDGET units: each question while they fit, then how many more and
    where they are read."""
    lead = "Moved onto the sheet from the earlier question tool: "
    items = ["%s %s (call %s, question %d)" % (q["id"], jstr(mark(q["question"], PROSE_CUT)),
                                               q["importedFrom"]["callId"], q["importedFrom"]["index"] + 1) for q in qs]
    whole = lead + ", ".join(items) + "."
    if units(whole) <= IMPORT_BUDGET:
        return whole

    def rest(k):
        left = qs[k:]
        span = left[0]["id"] if len(left) == 1 else "%s to %s" % (left[0]["id"], left[-1]["id"])
        return "and %d more, %s: sminos sheet show --session %s prints them." % (len(left), span, session)

    k, used = 0, units(lead)             # the whole did not fit, so the last item never ends the list: something is left
    while k + 1 < len(items) and used + units(items[k]) + 2 + units(rest(k + 1)) <= IMPORT_BUDGET:
        used += units(items[k]) + 2
        k += 1
    return lead + "".join(x + ", " for x in items[:k]) + rest(k)


def context(st, session, after, empty=None, floor_known=False, imported=()):
    """I10's text for the main conversation at a start (`after`: "a resume", "a compaction", "a start"), or "" when
    the sheet has nothing to say."""
    pend = [o for o in st["pending"] if o["recipient"] == "main"]
    if not st["questions"] and not pend:
        if empty == "fork":
            return FORK_LINE + (" New ids start at q%d." % st["nextId"] if floor_known else "")
        if empty == "lost":
            return LOST_LINE + " New ids start at q%d." % st["nextId"]
        return ""

    def items(qcut=None, lcut=None):
        out = []
        for q in st["questions"]:
            out.append((q["id"], question_line("Open:", q["id"], q["revision"], q["asker"], q.get("header"),
                                               q["question"], [o["label"] for o in q["options"]], qcut, lcut)))
        for o in pend:
            s = o["question"]
            lead = ("Answered, the answer not yet delivered to you:" if o["kind"] == "answer"
                    else "Dismissed, not yet told to you:")
            out.append((o["id"], question_line(lead, o["id"], o["revision"], s["asker"], s.get("header"),
                                               s["question"], s["options"], qcut, lcut)))
        return out

    head = "[sheet v1] Your question sheet, after %s." % after
    foot = []
    if imported:
        foot.append(moved([q for q in st["questions"] if q.get("importedFrom", {}).get("callId") in imported],
                          session))
    foot.append("New ids continue from q%d." % st["nextId"])
    whole = "\n".join([head] + [x for _, x in items()] + foot)
    if units(whole) <= BUDGET:
        return whole
    cut = items(CONTEXT_QUESTION, CONTEXT_LABEL)
    whole = "\n".join([head] + [x for _, x in cut] + foot)
    if units(whole) <= BUDGET:
        return whole
    # past the budget even cut: the list stops where the budget does, and says what it left out
    def more(rest):
        span = rest[0][0] if len(rest) == 1 else "%s to %s" % (rest[0][0], rest[-1][0])
        return "and %d more open, %s: sminos sheet show --session %s prints them." % (len(rest), span, session)

    fixed = units(head) + sum(units(x) + 1 for x in foot)
    sizes = [units(x) + 1 for _, x in cut]
    k, acc = len(cut), sum(sizes)
    while k > 0:
        k -= 1
        acc -= sizes[k]
        if fixed + acc + units(more(cut[k:])) + 1 <= BUDGET:
            break
    return "\n".join([head] + [x for _, x in cut[:k]] + [more(cut[k:])] + foot)
