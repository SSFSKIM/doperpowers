#!/usr/bin/env python3
"""Writes sminos/types/tasks/: the Task Board's published set (contracts X1, X2, X3 and X6 of
docs/doperpowers/specs/2026-11-27-task-board-design.md; its child B1's execution document
docs/doperpowers/plans/2026-11-27-task-board-b1.md, §1 to §3 and §5, gate G1). MAWS's children pin a copy.

Every store, every `after`, every verdict, every reader's answer and every text here is written by hand from the
composite and the execution document, never computed by sminos_tasks or any command: the set is what the commands
are held to, not their output (the house rule of sheet-contract.gen.py and dx4-jobs.gen.py). What the generator
does compute is bookkeeping a hand would only get wrong: a line's digest, a file's SHA-256, the manifest. It is
deterministic: fixed session ids, thread ids, keys and times.

    python3 -B tasks-contract.gen.py                 # writes the set in place (sminos/types/tasks/)
    python3 -B tasks-contract.gen.py --out <dir>     # writes it into <dir> (made empty first)
    python3 -B tasks-contract.gen.py --check         # the committed set is this generator's, byte for byte

Each prints `tasks-contract: <n> cases, digest <sha256>`.
"""

import copy
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
SET = os.path.join(os.path.dirname(HERE), "types", "tasks")
FILES = {}               # path in the set -> bytes
CASES = []


# ------------------------------------------------------------------ serialization


def dump(obj):
    """The set's serialization of a JSON document, a store's state.json included: what a step's result is compared
    in once the command's own bytes are read and written again this way."""
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def jline(obj):
    """A door's line or a verdict as the commands print one: compact, its keys in the order given."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def digest(line):
    """`applied[key].digest`: the SHA-256 of the line as canonical JSON (keys sorted, compact, UTF-8)."""
    return sha(json.dumps(line, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def put(path, data):
    FILES[path] = data if isinstance(data, bytes) else data.encode()


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


# ------------------------------------------------------------------ schemas (JSON Schema 2020-12, the sheet's subset)

T_TIME = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{3}Z$"}
T_UUID = {"type": "string", "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"}
T_TASK = {"type": "string", "pattern": "^t[1-9][0-9]*$"}
T_OKEY = {"type": "string", "pattern": "^t[1-9][0-9]*\\.[1-9][0-9]*$"}
T_DATE = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
T_TAG = {"type": "string", "pattern": "^[a-z0-9-]{1,32}$"}
T_SHA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
T_INT0 = {"type": "integer", "minimum": 0}
T_INT1 = {"type": "integer", "minimum": 1}
T_STR = {"type": "string"}
NULL = {"type": "null"}
STATES = ["open", "done", "declined", "withdrawn"]
CLASSES = ["blocking", "needed", "optional"]
TOLD = ["now", "wake", "next-start", "ended", "maws"]
ACTS = ["done", "decline", "comment", "seen", "shown"]
WHY_NONE = ["not-addressable", "no-writer", "log-refused"]


def obj(props, required, extra=False):
    """A closed object, or (extra=None) one whose unknown fields are allowed: a store's objects keep every field
    they do not know (D3), so their schema refuses none."""
    out = {"type": "object", "properties": props, "required": required}
    if extra is not None:
        out["additionalProperties"] = extra
    return out


def open_obj(props, required):
    return obj(props, required, extra=None)


def arr(items, **bounds):
    return {"type": "array", "items": items, **bounds}


def one_of(*shapes):
    return {"oneOf": list(shapes)}


def ref(name):
    return {"$ref": "#/$defs/" + name}


AGENT = open_obj({"id": {"type": "string", "pattern": "^[A-Za-z0-9_.@-]{1,128}$"},
                  "name": one_of({"type": "string", "pattern": "^[A-Za-z0-9_.-]{1,64}$"}, NULL)}, ["id", "name"])
ASKER = open_obj({"thread": one_of(ref("uuid"), NULL), "session": ref("uuid"), "alias": one_of(T_STR, NULL),
                  "agent": one_of(ref("agent"), NULL)}, ["thread", "session", "alias", "agent"])
BY_AGENT = open_obj({"session": ref("uuid"), "alias": one_of(T_STR, NULL), "agent": one_of(ref("agent"), NULL)},
                    ["session", "alias", "agent"])
COMMENT = open_obj({"n": T_INT1, "seq": T_INT1, "by": one_of({"type": "string", "const": "human"}, BY_AGENT),
                    "at": ref("time"), "text": {"type": "string", "minLength": 1, "maxLength": 10000},
                    "outcome": one_of(ref("outcomeKey"), NULL)}, ["n", "seq", "by", "at", "text", "outcome"])
CLOSED = open_obj({"how": {"type": "string", "enum": ["done", "declined", "withdrawn"]}, "seq": T_INT1,
                   "at": ref("time"), "text": {"type": "string", "maxLength": 10000}}, ["how", "seq", "at", "text"])
SEND = one_of(
    NULL,
    open_obj({"state": {"type": "string", "const": "due"}, "since": ref("time")}, ["state", "since"]),
    open_obj({"state": {"type": "string", "const": "sent"}, "how": {"type": "string", "enum": ["tell", "notice"]},
              "at": ref("time"), "session": ref("uuid"), "agent": one_of(T_STR, NULL), "liveOnly": {"type": "boolean"},
              "project": one_of(T_STR, NULL), "answer": T_STR},
             ["state", "how", "at", "session", "agent", "liveOnly", "project", "answer"]),
    open_obj({"state": {"type": "string", "const": "none"}, "at": ref("time"),
              "why": {"type": "string", "enum": WHY_NONE}}, ["state", "at", "why"]))
SHOWN = one_of(NULL, open_obj({"at": ref("time"), "session": ref("uuid")}, ["at", "session"]))
OUTCOME = open_obj({"key": ref("outcomeKey"), "seq": T_INT1,
                    "kind": {"type": "string", "enum": ["done", "declined", "comment"]}, "at": ref("time"),
                    "revision": T_INT1, "text": {"type": "string", "maxLength": 10000}, "wake": {"type": "boolean"},
                    "shown": SHOWN, "send": ref("send"), "endedLine": one_of(ref("time"), NULL)},
                   ["key", "seq", "kind", "at", "revision", "text", "wake", "shown", "send", "endedLine"])
TASK_PROPS = {
    "id": ref("taskId"), "revision": T_INT1, "state": {"type": "string", "enum": STATES},
    "class": {"type": "string", "enum": CLASSES},
    "title": {"type": "string", "minLength": 1, "maxLength": 200}, "body": {"type": "string", "maxLength": 20000},
    "due": one_of(T_DATE, NULL), "tags": arr(T_TAG, maxItems=8), "project": one_of(T_STR, NULL),
    "askers": arr(ref("asker"), minItems=1), "born": T_INT1, "createdAt": ref("time"), "agentSeq": T_INT1,
    "seenSeq": T_INT0, "comments": arr(ref("comment")), "closed": one_of(ref("closed"), NULL), "acts": T_INT0,
    "outcomes": arr(ref("outcome"))}
TASK_REQ = list(TASK_PROPS)
TASK = open_obj(TASK_PROPS, TASK_REQ)
TARGET = obj({"session": ref("uuid"), "thread": one_of(ref("uuid"), NULL), "project": one_of(T_STR, NULL),
              "state": {"type": "string", "enum": ["running", "stopped", "ended", "gone", "unknown"]},
              "runner": {"type": "string", "enum": ["terminal", "maws"]},
              "wake": one_of({"type": "string", "enum": ["woken", "held"]}, NULL), "why": T_STR,
              "via": {"type": "string", "enum": ["self", "cleared"]}},
             ["session", "thread", "project", "state", "runner", "wake", "why", "via"])
READER_TASK = open_obj({**TASK_PROPS, "target": ref("target"), "updated": {"type": "boolean"}},
                       TASK_REQ + ["target", "updated"])

V1 = {"type": "integer", "const": 1}
HEAD = {"v": V1, "key": ref("uuid")}


def verdict(acts, verdict_word, fields, required):
    act = {"type": "string", "const": acts[0]} if len(acts) == 1 else {"type": "string", "enum": acts}
    return obj({**HEAD, "act": act, "verdict": {"type": "string", "const": verdict_word}, **fields},
               ["v", "key", "act", "verdict"] + required)


TRS = {"task": ref("taskId"), "revision": T_INT1, "state": {"type": "string", "enum": STATES}}
VERDICT = one_of(
    verdict(["done", "decline", "comment"], "applied",
            {**TRS, "outcome": ref("outcomeKey"), "told": {"type": "string", "enum": TOLD}},
            ["task", "revision", "state", "outcome", "told"]),
    verdict(["seen"], "applied", TRS, ["task", "revision", "state"]),
    verdict(["shown"], "applied", {**TRS, "keys": arr(ref("outcomeKey"))}, ["task", "revision", "state", "keys"]),
    verdict(["done", "decline"], "stale", TRS, ["task", "revision", "state"]),
    verdict(["done", "decline", "comment"], "closed", TRS, ["task", "revision", "state"]),
    verdict(ACTS, "unknown", {"task": ref("taskId")}, ["task"]),
    verdict(ACTS, "refused", {"reason": {"type": "string", "enum": ["key-reused"]}}, ["reason"]))
APPLIED = open_obj({"task": ref("taskId"), "at": ref("time"), "digest": T_SHA, "verdict": ref("verdict")},
                   ["task", "at", "digest", "verdict"])
SUCCESSOR = open_obj({"session": ref("uuid"), "thread": one_of(ref("uuid"), NULL), "at": ref("time")},
                     ["session", "thread", "at"])
WAKE_CHOICE = one_of({"type": "boolean"}, NULL)
TEXT = {"type": "string", "maxLength": 10000}
SAID = {"type": "string", "minLength": 1, "maxLength": 10000}


def line(act, fields):
    return obj({**HEAD, "act": {"type": "string", "const": act}, "task": ref("taskId"), **fields},
               ["v", "key", "act", "task"] + list(fields))


LINE = one_of(
    line("done", {"revision": T_INT1, "text": TEXT, "wake": WAKE_CHOICE}),
    line("decline", {"revision": T_INT1, "text": SAID, "wake": WAKE_CHOICE}),
    line("comment", {"text": SAID, "wake": WAKE_CHOICE}),
    line("seen", {"seq": T_INT0}),
    line("shown", {"session": ref("uuid"), "keys": arr(ref("outcomeKey"), minItems=1, maxItems=1000)}))
WAITING_ROW = obj({"key": ref("outcomeKey"), "task": ref("taskId"), "state": {"type": "string", "enum": STATES},
                   "kind": {"type": "string", "enum": ["done", "declined", "comment"]}, "seq": T_INT1,
                   "at": ref("time"), "wake": {"type": "boolean"}, "send": ref("send"), "target": ref("target")},
                  ["key", "task", "state", "kind", "seq", "at", "wake", "send", "target"])

DEFS = {"time": T_TIME, "uuid": T_UUID, "taskId": T_TASK, "outcomeKey": T_OKEY, "agent": AGENT, "asker": ASKER,
        "comment": COMMENT, "closed": CLOSED, "send": SEND, "outcome": OUTCOME, "task": TASK, "verdict": VERDICT,
        "target": TARGET, "readerTask": READER_TASK}


def schema(title, body, names):
    defs = {}
    todo = list(names) + refs(body)
    while todo:     # the defs a schema reaches, and only those
        n = todo.pop()
        if n in defs:
            continue
        defs[n] = DEFS[n]
        todo += [r for r in refs(DEFS[n]) if r not in defs]
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": title, **body,
            "$defs": dict(sorted(defs.items()))}


def refs(node):
    if isinstance(node, dict):
        out = [node["$ref"][len("#/$defs/"):]] if "$ref" in node else []
        return out + [r for v in node.values() for r in refs(v)]
    if isinstance(node, list):
        return [r for v in node for r in refs(v)]
    return []


STATE_SCHEMA = schema("The Task Board's store, $SMINOS_HOME/tasks/state.json (X1; §1)", open_obj(
    {"v": V1, "version": V1, "seq": T_INT0, "nextId": T_INT1,
     "tasks": {"type": "object", "additionalProperties": ref("task")},
     "applied": {"type": "object", "additionalProperties": APPLIED},
     "successors": {"type": "object", "additionalProperties": SUCCESSOR}},
    ["v", "version", "seq", "nextId", "tasks", "applied", "successors"]), ["task", "verdict"])
LINE_SCHEMA = schema("One line of the door, sminos task act (X2; §3)", LINE, ["uuid"])
VERDICT_SCHEMA = schema("One verdict the door prints (X2; §3)", ref("verdict"), ["verdict"])
LIST_SCHEMA = schema("sminos task list --json (X3; §3)",
                     obj({"v": V1, "seq": T_INT0, "tasks": arr(ref("readerTask"))}, ["v", "seq", "tasks"]),
                     ["readerTask"])
SHOW_SCHEMA = schema("sminos task show --json (X3; §3)",
                     obj({"v": V1, "seq": T_INT0, "task": ref("readerTask")}, ["v", "seq", "task"]), ["readerTask"])
WAITING_SCHEMA = schema("sminos task waiting --json (X3; §3)",
                        obj({"v": V1, "seq": T_INT0, "waiting": arr(WAITING_ROW)}, ["v", "seq", "waiting"]),
                        ["target", "send", "outcomeKey", "taskId", "time"])


# ------------------------------------------------------------------ the stand-ins

def sid(n):
    return "5eed0000-0000-4000-8000-0000000000%s" % n


def tid(n):
    return "7d000000-0000-4000-8000-0000000000%s" % n


def key(n):
    return "5eed0000-0000-4000-8000-00000000c%03d" % n


S1, S2, S3, S9 = sid("a1"), sid("a2"), sid("a3"), sid("a9")      # the asker, a successor, a third, another
T1, T2 = tid("b1"), tid("b2")                                      # the asker's thread, the successor's
PROJECT = "1c0de000-0000-5000-8000-0000000000aa"
AGENT_ID = "a1b2c3d4e5f60718"
TIMES = ["2026-11-27T16:%02d:00.000Z" % m for m in range(0, 60, 5)]   # TIMES[i], one a step


def at(i):
    return TIMES[i]


BODY1 = "Open the console and sign in. Done when the dashboard loads."
TITLE1 = "Log in to the console"
TITLE2 = "Rotate the signing key"


def asker(session=S1, thread=None, alias=None, agent=None):
    return {"thread": thread, "session": session, "alias": alias, "agent": agent}


def task(id_, cls, title, born, created, body="", due=None, tags=(), project=None, askers=None, **f):
    t = {"id": id_, "revision": 1, "state": "open", "class": cls, "title": title, "body": body, "due": due,
         "tags": list(tags), "project": project, "askers": askers or [asker()], "born": born, "createdAt": created,
         "agentSeq": born, "seenSeq": born, "comments": [], "closed": None, "acts": 0, "outcomes": []}
    t.update(f)
    return t


def outcome(key_, seq, kind, at_, revision, text, wake, shown=None, send=None, ended_line=None):
    return {"key": key_, "seq": seq, "kind": kind, "at": at_, "revision": revision, "text": text, "wake": wake,
            "shown": shown, "send": send, "endedLine": ended_line}


def store(seq, next_id, tasks, applied=None, successors=None, **f):
    s = {"v": 1, "version": 1, "seq": seq, "nextId": next_id, "tasks": {t["id"]: t for t in tasks},
         "applied": applied or {}, "successors": successors or {}}
    s.update(f)
    return s


def applied(line_, task_id, at_, verdict_):
    return {line_["key"]: {"task": task_id, "at": at_, "digest": digest(line_), "verdict": verdict_}}


def thread_record(thread, current, sessions, ended=None):
    """A thread its human opened, as sminos_threads keeps it under $SMINOS_HOME/threads/ (the fields the store's
    reader asks of it: its current session, and whether it has ended)."""
    r = {"thread": thread, "opened": "human", "current": current, "sessions": list(sessions), "alias": "alpha",
         "launch": {"cwd": "{HOME}/work"}, "channels": [], "created": "2026-11-27T15:00:00Z",
         "updated": "2026-11-27T15:00:00Z"}
    if ended:
        r["ended"] = ended
    return r


def case(name, covers, now, argv, before, after, stdout, exit_=0, session=None, stdin=None, stderr="",
         threads=None):
    """One step: `before` and `after` are a $SMINOS_HOME each (`tasks/state.json`, and the thread records the
    step reads, which no step changes); None for no store."""
    CASES.append(name)
    base = "fixtures/%s/" % name
    put(base + "case.json", dump({"name": name, "covers": covers, "now": now, "session": session, "argv": argv,
                                  "stdin": stdin, "exit": exit_, "stdout": stdout, "stderr": stderr}))
    for side, st in (("before", before), ("after", after)):
        if st is not None:
            put(base + side + "/tasks/state.json", dump(st))
        for t in threads or ():
            put(base + side + "/threads/%s.json" % t["thread"], dump(t))


def act(line_):
    return ["task", "act"], jline(line_) + "\n"


# ------------------------------------------------------------------ the chain of the first fixtures

T1_NEW = task("t1", "blocking", TITLE1, 1, at(0), body=BODY1)
A1 = store(1, 2, [T1_NEW])
T2_NEW = task("t2", "needed", TITLE2, 2, at(1), due="2027-01-05", tags=["keys"])
A2 = store(2, 3, [T1_NEW, T2_NEW])
T1_REV = dict(T1_NEW, title="Log in to the cloud console", revision=2, agentSeq=3)
REV = store(3, 3, [T1_REV, T2_NEW])

case("assign-makes-the-store", "an assign that makes the store: t1, revision 1, open, born at seq 1", at(0),
     ["task", "assign", "--class", "blocking", "--title", TITLE1, "--body-file", "-"], None, A1,
     't1 blocking "Log in to the console"\n', session=S1, stdin=BODY1 + "\n")
case("assign-a-second", "a second assign: the next id, a due date and a tag", at(1),
     ["task", "assign", "--class", "needed", "--title", TITLE2, "--due", "2027-01-05", "--tag", "keys"], A1, A2,
     't2 needed "Rotate the signing key"\n', session=S1)
case("revise", "the asker revises: the fields given, revision + 1, agentSeq", at(2),
     ["task", "revise", "t1", "--title", "Log in to the cloud console"], A2, REV, "t1 revision 2\n", session=S1)

DONE_LINE = {"v": 1, "key": key(1), "act": "done", "task": "t1", "revision": 2, "text": "logged in with account B",
             "wake": None}
DONE_VERDICT = {"v": 1, "key": key(1), "act": "done", "verdict": "applied", "task": "t1", "revision": 2,
                "state": "done", "outcome": "t1.1", "told": "next-start"}
T1_DONE = dict(T1_REV, state="done", acts=1,
               closed={"how": "done", "seq": 4, "at": at(3), "text": "logged in with account B"},
               outcomes=[outcome("t1.1", 4, "done", at(3), 2, "logged in with account B", True)])
DONE = store(4, 3, [T1_DONE, T2_NEW], applied=applied(DONE_LINE, "t1", at(3), DONE_VERDICT))
argv, stdin = act(DONE_LINE)
case("done-current", "a done at the current revision: applied, its outcome waiting, its wake the blocking default; "
     "nothing sent until M2 (told next-start, send null)", at(3), argv, REV, DONE, jline(DONE_VERDICT) + "\n",
     stdin=stdin)

STALE_LINE = dict(DONE_LINE, key=key(2), revision=1)
STALE_VERDICT = {"v": 1, "key": key(2), "act": "done", "verdict": "stale", "task": "t1", "revision": 2,
                 "state": "open"}
argv, stdin = act(STALE_LINE)
case("done-stale", "a done at an old revision: stale, with the current revision; the task is untouched and the "
     "verdict kept by its key", at(3), argv, REV,
     store(4, 3, [T1_REV, T2_NEW], applied=applied(STALE_LINE, "t1", at(3), STALE_VERDICT)),
     jline(STALE_VERDICT) + "\n", stdin=stdin)

DECLINE_LINE = {"v": 1, "key": key(3), "act": "decline", "task": "t2", "revision": 1,
                "text": "the key is not mine to rotate", "wake": None}
DECLINE_VERDICT = {"v": 1, "key": key(3), "act": "decline", "verdict": "applied", "task": "t2", "revision": 1,
                   "state": "declined", "outcome": "t2.1", "told": "next-start"}
T2_DECLINED = dict(T2_NEW, state="declined", acts=1,
                   closed={"how": "declined", "seq": 4, "at": at(3), "text": "the key is not mine to rotate"},
                   outcomes=[outcome("t2.1", 4, "declined", at(3), 1, "the key is not mine to rotate", False)])
argv, stdin = act(DECLINE_LINE)
case("decline", "a decline: its reason kept, its wake false for a task that is not blocking", at(3), argv, REV,
     store(4, 3, [T1_REV, T2_DECLINED], applied=applied(DECLINE_LINE, "t2", at(3), DECLINE_VERDICT)),
     jline(DECLINE_VERDICT) + "\n", stdin=stdin)

COMMENT_LINE = {"v": 1, "key": key(4), "act": "comment", "task": "t1", "text": "which account?", "wake": None}
COMMENT_VERDICT = {"v": 1, "key": key(4), "act": "comment", "verdict": "applied", "task": "t1", "revision": 2,
                   "state": "open", "outcome": "t1.1", "told": "next-start"}
T1_COMMENTED = dict(T1_REV, acts=1,
                    comments=[{"n": 1, "seq": 4, "by": "human", "at": at(3), "text": "which account?",
                               "outcome": "t1.1"}],
                    outcomes=[outcome("t1.1", 4, "comment", at(3), 2, "which account?", True)])
argv, stdin = act(COMMENT_LINE)
case("comment-by-the-human", "the human's comment: a comment naming its outcome and the outcome, sharing one seq; "
     "the task stays open", at(3), argv, REV,
     store(4, 3, [T1_COMMENTED, T2_NEW], applied=applied(COMMENT_LINE, "t1", at(3), COMMENT_VERDICT)),
     jline(COMMENT_VERDICT) + "\n", stdin=stdin)

argv, stdin = act(DONE_LINE)
case("same-line-twice", "the same line again under its key: the first verdict, told included, and nothing changes",
     at(5), argv, DONE, DONE, jline(DONE_VERDICT) + "\n", stdin=stdin)

argv, stdin = act(dict(DECLINE_LINE, key=key(1)))
case("key-reused", "another line under a key already used: refused, key-reused, and nothing changes", at(5), argv,
     DONE, DONE, jline({"v": 1, "key": key(1), "act": "decline", "verdict": "refused", "reason": "key-reused"}) + "\n",
     stdin=stdin)

SEEN_LINE = {"v": 1, "key": key(5), "act": "seen", "task": "t1", "seq": 2}
SEEN_VERDICT = {"v": 1, "key": key(5), "act": "seen", "verdict": "applied", "task": "t1", "revision": 2,
                "state": "open"}
argv, stdin = act(SEEN_LINE)
case("seen-older", "a seen naming a snapshot older than a later revise: seenSeq rises to it, and the task stays "
     "Updated (agentSeq 3 above seenSeq 2)", at(3), argv, REV,
     store(4, 3, [dict(T1_REV, seenSeq=2), T2_NEW], applied=applied(SEEN_LINE, "t1", at(3), SEEN_VERDICT)),
     jline(SEEN_VERDICT) + "\n", stdin=stdin)

# The door's shown across a real change of target, every step of the store reachable: t1 asked from the thread T1
# (its current session S1); the human's comment t1.1 while S1 was the target, shown to S1 at its start; a witnessed
# /clear of S1 into S2, whose pair is bound to S2's thread T2 in the same step; then a comment t1.2 and a done t1.3,
# each kept by its key. A shown for S2 takes t1.2 and t1.3 and passes over t1.1, S1's.
D_T1, D_T2 = thread_record(T1, S1, [S1]), thread_record(T2, S2, [S2])
D_LINES = [{"v": 1, "key": key(20), "act": "comment", "task": "t1", "text": "which account?", "wake": None},
           {"v": 1, "key": key(21), "act": "comment", "task": "t1", "text": "the one with the hardware key",
            "wake": None},
           {"v": 1, "key": key(22), "act": "done", "task": "t1", "revision": 1, "text": "", "wake": None}]
D_VERDICTS = [{"v": 1, "key": key(20), "act": "comment", "verdict": "applied", "task": "t1", "revision": 1,
               "state": "open", "outcome": "t1.1", "told": "next-start"},
              {"v": 1, "key": key(21), "act": "comment", "verdict": "applied", "task": "t1", "revision": 1,
               "state": "open", "outcome": "t1.2", "told": "next-start"},
              {"v": 1, "key": key(22), "act": "done", "verdict": "applied", "task": "t1", "revision": 1,
               "state": "done", "outcome": "t1.3", "told": "next-start"}]
D_AT = [at(1), at(4), at(4)]
D_APPLIED = {}
for line_, v, when in zip(D_LINES, D_VERDICTS, D_AT):
    D_APPLIED.update(applied(line_, "t1", when, v))
D_TASK = task("t1", "blocking", TITLE1, 1, at(0), body=BODY1, askers=[asker(thread=T1)], acts=3, comments=[
    {"n": 1, "seq": 2, "by": "human", "at": at(1), "text": "which account?", "outcome": "t1.1"},
    {"n": 2, "seq": 5, "by": "human", "at": at(4), "text": "the one with the hardware key", "outcome": "t1.2"}],
    state="done", closed={"how": "done", "seq": 6, "at": at(4), "text": ""},
    outcomes=[outcome("t1.1", 2, "comment", at(1), 1, "which account?", True, shown={"at": at(2), "session": S1}),
              outcome("t1.2", 5, "comment", at(4), 1, "the one with the hardware key", True),
              outcome("t1.3", 6, "done", at(4), 1, "", True)])
D_PAIR = {S1: {"session": S2, "thread": T2, "at": at(3)}}
D_BEFORE = store(6, 2, [D_TASK], applied=D_APPLIED, successors=D_PAIR)
SHOWN_LINE = {"v": 1, "key": key(6), "act": "shown", "task": "t1", "session": S2, "keys": ["t1.1", "t1.2", "t1.3"]}
SHOWN_VERDICT = {"v": 1, "key": key(6), "act": "shown", "verdict": "applied", "task": "t1", "revision": 1,
                 "state": "done", "keys": ["t1.2", "t1.3"]}
D_TASK_SHOWN = copy.deepcopy(D_TASK)
for o in D_TASK_SHOWN["outcomes"][1:]:
    o["shown"] = {"at": at(5), "session": S2}
argv, stdin = act(SHOWN_LINE)
case("shown-by-a-deliverer", "the door's shown after a /clear moved the task's target: the keys whose target is "
     "the session told are marked, and one already shown to the session before the clear, another session's, is "
     "passed over", at(5), argv, D_BEFORE,
     store(7, 2, [D_TASK_SHOWN], applied={**D_APPLIED, **applied(SHOWN_LINE, "t1", at(5), SHOWN_VERDICT)},
           successors=D_PAIR),
     jline(SHOWN_VERDICT) + "\n", stdin=stdin, threads=[D_T1, D_T2])

case("withdraw", "the asker withdraws: state withdrawn, closed with the reason", at(3),
     ["task", "withdraw", "t2", "--reason", "not needed after all"], REV,
     store(4, 3, [T1_REV, dict(T2_NEW, state="withdrawn",
                               closed={"how": "withdrawn", "seq": 4, "at": at(3), "text": "not needed after all"})]),
     "t2 withdrawn\n", session=S1)

T1_REOPENED = dict(T1_DONE, state="open", closed=None, revision=3, agentSeq=5, comments=[
    {"n": 1, "seq": 5, "by": {"session": S1, "alias": None, "agent": None}, "at": at(4),
     "text": "the console still asks for a login", "outcome": None}])
case("reopen", "the asker reopens a done task with a comment: open again, closed null, revision + 1", at(4),
     ["task", "reopen", "t1", "--comment", "the console still asks for a login"], DONE,
     store(5, 3, [T1_REOPENED, T2_NEW], applied=DONE["applied"]), "t1 reopened: revision 3\n", session=S1)

LATE_LINE = dict(DONE_LINE, key=key(7))
LATE_VERDICT = {"v": 1, "key": key(7), "act": "done", "verdict": "closed", "task": "t1", "revision": 2,
                "state": "done"}
argv, stdin = act(LATE_LINE)
case("act-on-a-closed-task", "a done on a task no longer open: closed, with its state, the verdict kept by its key",
     at(5), argv, DONE, store(5, 3, [T1_DONE, T2_NEW], applied={**DONE["applied"],
                                                               **applied(LATE_LINE, "t1", at(5), LATE_VERDICT)}),
     jline(LATE_VERDICT) + "\n", stdin=stdin)
CLOSED_KEPT = store(5, 3, [T1_DONE, T2_NEW], applied={**DONE["applied"], **applied(LATE_LINE, "t1", at(5),
                                                                                  LATE_VERDICT)})
T1_REOPENED_LATE = dict(T1_DONE, state="open", closed=None, revision=3, agentSeq=6, comments=[
    {"n": 1, "seq": 6, "by": {"session": S1, "alias": None, "agent": None}, "at": at(6),
     "text": "the console still asks for a login", "outcome": None}])
REOPENED_LATE = store(6, 3, [T1_REOPENED_LATE, T2_NEW], applied=CLOSED_KEPT["applied"])
case("refused-then-reopened", "the same line refused closed, again after the asker reopened: the kept verdict, "
     "closed, and nothing applied", at(7), argv, REOPENED_LATE, REOPENED_LATE, jline(LATE_VERDICT) + "\n",
     stdin=stdin)

UNKNOWN_LINE = dict(DONE_LINE, key=key(8), task="t99")
UNKNOWN_VERDICT = {"v": 1, "key": key(8), "act": "done", "verdict": "unknown", "task": "t99"}
argv, stdin = act(UNKNOWN_LINE)
case("unknown-id", "an act on an id the store does not hold: unknown, kept by its key under the id it named",
     at(3), argv, REV, store(4, 3, [T1_REV, T2_NEW], applied=applied(UNKNOWN_LINE, "t99", at(3), UNKNOWN_VERDICT)),
     jline(UNKNOWN_VERDICT) + "\n", stdin=stdin)

FUTURE = store(3, 3, [dict(T1_REV, future=["kept"]), T2_NEW], future={"written by": "a later sminos"})
FUTURE_AFTER = store(4, 3, [dict(T1_REV, future=["kept"], agentSeq=4, comments=[
    {"n": 1, "seq": 4, "by": {"session": S1, "alias": None, "agent": None}, "at": at(3),
     "text": "checking the key too", "outcome": None}]), T2_NEW], future={"written by": "a later sminos"})
case("unknown-fields-kept", "a field this version does not know, at the top and on a task, kept through a write "
     "(an agent's comment)", at(3), ["task", "comment", "t1", "checking the key too"], FUTURE, FUTURE_AFTER,
     "t1 comment 1\n", session=S1)


# ------------------------------------------------------------------ the target: a thread, a /clear's pair

TH1 = thread_record(T1, S1, [S1])
B_OPEN = task("t1", "blocking", TITLE1, 1, at(0), body=BODY1, askers=[asker(thread=T1)])
UNBOUND = {S1: {"session": S2, "thread": None, "at": at(1)}}
BOUND = {S1: {"session": S2, "thread": T2, "at": at(1)}}
TH2 = thread_record(T2, S2, [S2])
TH2_ON = thread_record(T2, S3, [S2, S3])

case("successor-unbound-then-bound", "a /clear's pair not bound yet; the successor's remind binds it to the "
     "thread whose current session it is, and the task is the successor's: its start line counts it", at(2),
     ["task", "remind", "--session", S2], store(2, 2, [B_OPEN], successors=UNBOUND),
     store(3, 2, [B_OPEN], successors=BOUND), "\nTasks you assigned to the human: 1 open (1 blocking).\n",
     session=S2, threads=[TH1, TH2])
B_REVISED = dict(B_OPEN, revision=2, **{"class": "needed"}, agentSeq=3)
case("successor-bound", "a bound pair: the successor is the target, and may revise", at(2),
     ["task", "revise", "t1", "--class", "needed"], store(2, 2, [B_OPEN], successors=BOUND),
     store(3, 2, [B_REVISED], successors=BOUND), "t1 revision 2\n", session=S2, threads=[TH1, TH2])
case("successor-handed-off", "the successor's thread went on in a third session: that session is the target and "
     "may revise", at(2), ["task", "revise", "t1", "--class", "needed"], store(2, 2, [B_OPEN], successors=BOUND),
     store(3, 2, [B_REVISED], successors=BOUND), "t1 revision 2\n", session=S3, threads=[TH1, TH2_ON])
case("successor-purged", "a bound successor whose thread's record is gone (purged) is no target: the task falls "
     "back to the asker's thread", at(2), ["task", "remind", "--session", S1],
     store(2, 2, [B_OPEN], successors=BOUND), store(2, 2, [B_OPEN], successors=BOUND),
     "\nTasks you assigned to the human: 1 open (1 blocking).\n", session=S1, threads=[TH1])


# ------------------------------------------------------------------ the start line: remind, then shown --keys

R_T1 = dict(T1_NEW, state="done", acts=1, closed={"how": "done", "seq": 3, "at": at(2), "text": "logged in"},
            outcomes=[outcome("t1.1", 3, "done", at(2), 1, "logged in", True)])
R_LINE = {"v": 1, "key": key(14), "act": "done", "task": "t1", "revision": 1, "text": "logged in", "wake": None}
R_APPLIED = applied(R_LINE, "t1", at(2), dict(DONE_VERDICT, key=key(14), revision=1))
R_BEFORE = store(3, 3, [R_T1, T2_NEW], applied=R_APPLIED)
R_T1_SHOWN = copy.deepcopy(R_T1)
R_T1_SHOWN["outcomes"][0]["shown"] = {"at": at(3), "session": S1}
START = ("t1.1\nTasks you assigned to the human: 1 open (0 blocking).\n"
         "The human acted on tasks you assigned: marked t1 done. Read one: sminos task show t1\n")
case("remind", "the start hook's first call: the keys it is about to name, then the start line; it marks nothing",
     at(3), ["task", "remind", "--session", S1, "--source", "startup"], R_BEFORE, R_BEFORE, START, session=S1)
case("shown-keys", "the start hook's second call: exactly the keys remind named, marked shown to that session",
     at(3), ["task", "shown", "--session", S1, "--keys", "t1.1"], R_BEFORE, store(4, 3, [R_T1_SHOWN, T2_NEW], applied=R_APPLIED),
     "t1.1\n", session=S1)


# ------------------------------------------------------------------ examples: every value, every shape

T3, T9 = tid("b3"), tid("b9")                                      # a thread that ended, a thread a /clear left
S4 = sid("a4")                                                     # the ended thread's last session
TARGET_RUNNING = {"session": S1, "thread": T1, "project": PROJECT, "state": "running", "runner": "terminal",
                  "wake": None, "why": "", "via": "self"}
TARGET_ENDED = {"session": S4, "thread": T3, "project": PROJECT, "state": "ended", "runner": "terminal",
                "wake": None, "why": "", "via": "self"}
TARGET_MAWS = {"session": S3, "thread": None, "project": None, "state": "gone", "runner": "maws", "wake": None,
               "why": "", "via": "self"}
TARGET_HELD = {"session": S2, "thread": T2, "project": PROJECT, "state": "stopped", "runner": "terminal",
               "wake": "held", "why": "mode", "via": "cleared"}


def every_value():
    """A store with an outcome for each `told` (in `applied`) and each value of `send`, so what M2 fills is in the
    schema now: each pair of them one a step can reach (§3's table). A send is made only for `now` and `wake`: a
    tell, and a notice for a running target, are `now`, a notice that may wake (not live-only) is `wake`, a send
    still due is `now`, and one found to have no way is either; `next-start`, `ended` and `maws` send nothing, and
    an `ended` outcome's line is written or not yet. Each asker is what its `told` implies: the thread T1 running,
    the thread T3 ended, a MAWS session with no thread."""
    sent_tell = {"state": "sent", "how": "tell", "at": at(4), "session": S1, "agent": AGENT_ID, "liveOnly": True,
                 "project": None, "answer": "queued"}
    sent_live = {"state": "sent", "how": "notice", "at": at(4), "session": S1, "agent": None, "liveOnly": True,
                 "project": PROJECT, "answer": "sent"}
    sent_wake = dict(sent_live, liveOnly=False, answer="woken")
    none = {w: {"state": "none", "at": at(4), "why": w} for w in WHY_NONE}
    in_t1, in_t3, in_maws = asker(thread=T1, alias="alpha"), asker(session=S4, thread=T3, alias="gamma"), \
        asker(session=S3)
    combos = [   # (told, send, endedLine, the asker)
        ("next-start", None, None, in_t1),
        ("now", {"state": "due", "since": at(4)}, None, in_t1),
        ("now", sent_tell, None, dict(in_t1, agent={"id": AGENT_ID, "name": "reviewer"})),
        ("now", sent_live, None, in_t1),
        ("wake", sent_wake, None, in_t1),
        ("now", none["not-addressable"], None, in_t1),
        ("wake", none["no-writer"], None, in_t1),
        ("now", none["log-refused"], None, in_t1),
        ("ended", None, at(4), in_t3),
        ("ended", None, None, in_t3),
        ("maws", None, None, in_maws)]
    tasks, applied_ = [], {}
    for n, (told, send, ended_line, who) in enumerate(combos, 1):
        k = "t%d.1" % n
        # A notice for the live alone is what an outcome that may not wake gets: the human said so on the line.
        live_only = send is sent_live
        line_ = {"v": 1, "key": key(100 + n), "act": "done", "task": "t%d" % n, "revision": 1, "text": "",
                 "wake": False if live_only else None}
        v = {"v": 1, "key": key(100 + n), "act": "done", "verdict": "applied", "task": "t%d" % n, "revision": 1,
             "state": "done", "outcome": k, "told": told}
        applied_.update(applied(line_, "t%d" % n, at(3), v))
        tasks.append(task("t%d" % n, "blocking", "Task %d" % n, n, at(0), project=PROJECT, askers=[who],
                          state="done", acts=1, closed={"how": "done", "seq": 20 + n, "at": at(3), "text": ""},
                          outcomes=[outcome(k, 20 + n, "done", at(3), 1, "", not live_only, send=send,
                                            ended_line=ended_line,
                                            shown={"at": at(5), "session": S1} if live_only else None)]))
    # The store's seq: its last act's, and one more for the start that marked the live notice's outcome shown.
    seq = max(o["seq"] for t in tasks for o in t["outcomes"]) + 1
    # The two shapes of a /clear's pair, bound and not yet, each left by a session no task here names.
    return store(seq, len(combos) + 1, tasks, applied=applied_,
                 successors={S9: {"session": S2, "thread": T2, "at": at(1)},
                             sid("a5"): {"session": sid("a6"), "thread": None, "at": at(2)}})


EVERY = every_value()
put("examples/state.json", dump(EVERY))
# A reader's target, as §2 finds it: a task with no thread is its asker's session's; one whose thread a /clear left
# goes to the successor (S9's pair above, bound to T2).
put("examples/list.json", dump({"v": 1, "seq": 3, "tasks": [
    dict(T1_REV, target=dict(TARGET_RUNNING, thread=None), updated=True),
    dict(T2_NEW, askers=[asker(session=S9, thread=T9)], target=TARGET_HELD, updated=False)]}))
put("examples/show.json", dump({"v": 1, "seq": 4, "task": dict(T1_DONE, askers=[asker(session=S3)],
                                                                target=TARGET_MAWS, updated=True)}))
WAITING_TARGET = {T1: TARGET_RUNNING, T3: TARGET_ENDED, None: TARGET_MAWS}
put("examples/waiting.json", dump({"v": 1, "seq": EVERY["seq"], "waiting": [
    {"key": o["key"], "task": t["id"], "state": t["state"], "kind": o["kind"], "seq": o["seq"], "at": o["at"],
     "wake": o["wake"], "send": o["send"], "target": WAITING_TARGET[t["askers"][0]["thread"]]}
    for t in EVERY["tasks"].values() for o in t["outcomes"] if o["shown"] is None]}))
put("examples/lines.json", dump([DONE_LINE, DECLINE_LINE, COMMENT_LINE, SEEN_LINE, SHOWN_LINE,
                                 dict(DONE_LINE, key=key(9), wake=True), dict(COMMENT_LINE, key=key(10), wake=False)]))
# Lines the schema takes and the door refuses (exit 2, nothing applied): its two wire rules the subset cannot say.
# Each is JSON text as a writer would send it, over the store `fixtures/revise/after/` holds (t1 at revision 2).
REJECTED = [
    ("an integer written with a fraction", '"revision":2.0', "done"),
    ("an integer written with an exponent", '"revision":2e0', "done"),
    ("v written with a fraction", None, "v"),
    ("a seq written with a fraction", None, "seen"),
    ("a lone high surrogate in a text", '"text":"logged in \\ud800"', "comment"),
    ("a lone low surrogate in a text", '"text":"\\udfff"', "decline")]


def rejected():
    out = []
    for n, (why, field, form) in enumerate(REJECTED):
        k = key(200 + n)
        if form == "done":
            text = '{"v":1,"key":"%s","act":"done","task":"t1",%s,"text":"","wake":null}' % (k, field)
        elif form == "v":
            text = '{"v":1.0,"key":"%s","act":"done","task":"t1","revision":2,"text":"","wake":null}' % k
        elif form == "seen":
            text = '{"v":1,"key":"%s","act":"seen","task":"t1","seq":2.0}' % k
        elif form == "comment":
            text = '{"v":1,"key":"%s","act":"comment","task":"t1",%s,"wake":null}' % (k, field)
        else:
            text = '{"v":1,"key":"%s","act":"decline","task":"t1","revision":2,%s,"wake":null}' % (k, field)
        out.append({"why": why, "home": "fixtures/revise/after", "line": text})
    return out


put("examples/rejected.json", dump(rejected()))
put("examples/verdicts.json", dump(
    [DONE_VERDICT, DECLINE_VERDICT, COMMENT_VERDICT, SEEN_VERDICT, SHOWN_VERDICT] +
    [dict(DONE_VERDICT, key=key(11 + i), told=t) for i, t in enumerate(TOLD)] +
    [{"v": 1, "key": key(2), "act": "done", "verdict": "stale", "task": "t1", "revision": 2, "state": "open"},
     {"v": 1, "key": key(7), "act": "done", "verdict": "closed", "task": "t1", "revision": 2, "state": "done"},
     {"v": 1, "key": key(8), "act": "done", "verdict": "unknown", "task": "t99"},
     {"v": 1, "key": key(1), "act": "decline", "verdict": "refused", "reason": "key-reused"}]))


# ------------------------------------------------------------------ the texts (X6; §5), word for word

def word(kind, id_):
    return {"done": "marked %s done", "declined": "declined %s", "comment": "commented on %s"}[kind] % id_


NOTICE = {
    "asker": "[tasks v1] The human %s, a task you assigned. Read it: sminos task show %s",
    "successor": "[tasks v1] The human %s, a task assigned by the conversation this one replaced at a /clear. "
                 "Read it: sminos task show %s",
    "subagent": "[tasks v1] The human %s, a task your subagent %s assigned. Read it: sminos task show %s"}
ENDED = "tasks: %s was %s; the conversation that assigned it has ended. It is on the board: sminos task show %s"
FORK = ("This conversation is a fork: the tasks the conversation it was forked from assigned to the human stay "
        "with that conversation, and what the human does on them is told there, not here.")
EXAMPLES = []
for kind, id_ in (("done", "t7"), ("declined", "t9"), ("comment", "t4")):
    EXAMPLES.append({"form": "notice", "clause": "asker", "kind": kind, "task": id_, "agent": None,
                     "text": NOTICE["asker"] % (word(kind, id_), id_)})
EXAMPLES.append({"form": "notice", "clause": "successor", "kind": "done", "task": "t7", "agent": None,
                 "text": NOTICE["successor"] % (word("done", "t7"), "t7")})
EXAMPLES.append({"form": "notice", "clause": "subagent", "kind": "comment", "task": "t4", "agent": AGENT_ID,
                 "text": NOTICE["subagent"] % (word("comment", "t4"), AGENT_ID, "t4")})
for kind, how in (("done", "completed"), ("declined", "declined"), ("comment", "commented on")):
    EXAMPLES.append({"form": "ended", "kind": kind, "task": "t7", "text": ENDED % ("t7", how, "t7")})
for open_, blocking, words, more, text in (
        (2, 1, [], 0, "Tasks you assigned to the human: 2 open (1 blocking)."),
        (0, 0, [("done", "t7"), ("declined", "t9")], 0,
         "The human acted on tasks you assigned: marked t7 done; declined t9. Read one: sminos task show t7"),
        (1, 0, [("comment", "t4")], 0,
         "Tasks you assigned to the human: 1 open (0 blocking).\n"
         "The human acted on tasks you assigned: commented on t4. Read one: sminos task show t4"),
        (3, 3, [("done", "t%d" % n) for n in range(1, 21)], 5,
         "Tasks you assigned to the human: 3 open (3 blocking).\n"
         "The human acted on tasks you assigned: " + "; ".join("marked t%d done" % n for n in range(1, 21)) +
         " (and 5 more: sminos task waiting --mine). Read one: sminos task show t1"),
        (0, 0, [], 0, "")):
    EXAMPLES.append({"form": "start", "open": open_, "blocking": blocking,
                     "outcomes": [{"kind": k, "task": t} for k, t in words], "more": more, "text": text})
EXAMPLES.append({"form": "fork", "text": FORK})
put("grammar/texts.examples.json", dump(EXAMPLES))

put("grammar/texts.md", r"""# The texts (X6; the execution document's §5)

Every text the board writes for an agent is built from these fixed words, a task's id, the outcome's word and a
subagent's id, and nothing else: no title, no body, no agent's comment, no subagent's name, no alias, no note of
the human's (D5). `texts.examples.json` holds an example of each form, with the fields it was built from.

    id      = "t" pos
    pos     = %x31-39 *DIGIT                       ; a positive integer, no leading zero, no cap
    word    = "marked " id " done" / "declined " id / "commented on " id
    agent   = 1*128( ALPHA / DIGIT / "_" / "." / "@" / "-" )

## The notice (`[tasks v1]`, from the program `tasks`)

    notice-asker     = "[tasks v1] The human " word ", a task you assigned. Read it: sminos task show " id
    notice-successor = "[tasks v1] The human " word ", a task assigned by the conversation this one replaced at"
                       " a /clear. Read it: sminos task show " id
    notice-subagent  = "[tasks v1] The human " word ", a task your subagent " agent " assigned. Read it: sminos"
                       " task show " id

The message to a running subagent is `notice-asker`. Which clause a notice takes: the target reached through a
successor's pair (`via: "cleared"`), the successor's, whether or not a subagent assigned the task; else, for a task
that names a subagent, the subagent's; else the asker's. The id after `show` is the word's.

A reader recognizes one (ECMAScript and Python `re` alike, whole):

    ^\[tasks v1\] The human (?:marked (t[1-9][0-9]*) done|declined (t[1-9][0-9]*)|commented on (t[1-9][0-9]*)), a task (?:you assigned|assigned by the conversation this one replaced at a /clear|your subagent [A-Za-z0-9_.@-]{1,128} assigned)\. Read it: sminos task show (t[1-9][0-9]*)$

## The ended line (to the log of the project the thread ended in, no addressee)

    ended = "tasks: " id " was " ( "completed" / "declined" / "commented on" ) "; the conversation that assigned"
            " it has ended. It is on the board: sminos task show " id

## The start line (the SessionStart hook's, from the store)

    start      = [ count ] [ LF ] [ acted ]          ; count when the target has open tasks, acted when outcomes
                                                     ; wait; LF only between the two
    count      = "Tasks you assigned to the human: " n " open (" n " blocking)."
    acted      = "The human acted on tasks you assigned: " word *( "; " word ) [ more ] ". Read one: sminos task"
                 " show " id
    more       = " (and " n " more: sminos task waiting --mine)"
    n          = 1*DIGIT

`acted` names the first twenty waiting outcomes of the target's tasks by the store's `seq`, and `more` counts the
rest; the id after `Read one` is the first outcome's task. With neither part the start line is empty.

    fork = "This conversation is a fork: the tasks the conversation it was forked from assigned to the human"
           " stay with that conversation, and what the human does on them is told there, not here."

`fork` is printed after the start line, on a line of its own, at a start whose source is `fork`, when the store
holds any open task.

## What `remind` prints

    remind = keys LF [ start LF ] [ fork LF ]
    keys   = [ okey *( " " okey ) ]                  ; an empty line for none
    okey   = id "." pos                       ; the outcome's task, then its number

The first line is the keys of the outcomes `acted` names, in its order, which the hook hands to
`sminos task shown --keys` once the rest is printed; the hook prints everything after it.
""")


# ------------------------------------------------------------------ the schemas, the README, the manifest

for name, body in (("state", STATE_SCHEMA), ("act-line", LINE_SCHEMA), ("verdict", VERDICT_SCHEMA),
                   ("list", LIST_SCHEMA), ("show", SHOW_SCHEMA), ("waiting", WAITING_SCHEMA)):
    put("schema/%s.schema.json" % name, dump(body))

put("README.md", """# The Task Board's published set

What a second repository reads of the Task Board, frozen at one revision of doperpowers (contracts X1, X2, X3 and
X6 of `docs/doperpowers/specs/2026-11-27-task-board-design.md`; its child B1's execution document
`docs/doperpowers/plans/2026-11-27-task-board-b1.md`, §1 to §3 and §5, gate G1). Every file here is written by
`sminos/tests/tasks-contract.gen.py`, by hand from those documents, never by an implementation;
`sminos/tests/test_tasks_contract.py` holds sminos to it. A change after the set is published is a ruling of the
composite's writer, and raises `version` in `MANIFEST.json`.

## Files

| path | what it is |
|---|---|
| `MANIFEST.json` | `{v, version, files: {path: sha256}, digest}`; `digest` is the SHA-256 of the lines `<sha256>  <path>\\n` of every other file, sorted by path |
| `schema/state.schema.json` | the store, `$SMINOS_HOME/tasks/state.json` (§1) |
| `schema/act-line.schema.json` | one line of the door, `sminos task act` (§3) |
| `schema/verdict.schema.json` | one verdict the door prints, and `applied[key].verdict` (§3) |
| `schema/list.schema.json`, `show.schema.json`, `waiting.schema.json` | the readers' `--json` (§3) |
| `examples/state.json` | a store holding an outcome for each value of `send` and a verdict for each `told` |
| `examples/lines.json`, `verdicts.json`, `list.json`, `show.json`, `waiting.json` | one of each shape |
| `examples/rejected.json` | lines the schema takes and the door refuses (exit 2, nothing applied), each as the JSON text sent, with the home it is sent to |
| `grammar/texts.md` | the notice, the ended line, the start line and what `remind` prints: their grammar and the pattern a reader matches |
| `grammar/texts.examples.json` | each form with the fields it was built from |
| `fixtures/<case>/` | one step: `case.json` `{name, covers, now, session, argv, stdin, exit, stdout, stderr}`, `before/` and `after/` (each a `$SMINOS_HOME`) |

The schemas are JSON Schema 2020-12 held to the question sheet's subset (`type`, `properties`, `required`,
`additionalProperties`, `enum`, `const`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `minimum`,
`pattern`, `oneOf`, `$ref` into the same file's `$defs`; lengths in code points); a `pattern` is ECMA-262 with no
flags, anchored `^...$`, `$` the end of input. The store's objects leave `additionalProperties` unstated: every
writer keeps a field it does not know (D3), so a later version's field is no error. A line, a verdict, a target and
a reader's `waiting` row are closed; a line with a field its act does not list is refused.

## Reading the fixtures

- `argv` follows `sminos`; `session` is the caller's `CLAUDE_CODE_SESSION_ID` (null: none, a terminal that is no
  session); `stdin` what the command reads (null: nothing); `now` the step's clock, which stamps every `at`.
- A side with no store has no `tasks/state.json`: `before/` lacks it where the step makes the store.
- `before/` and `after/` are a `$SMINOS_HOME` each, with the thread records the step reads (`threads/<id>.json`),
  which no step changes. A replay runs with that home, a `HOME` of its own with no engine records (no process holds
  any session) and the fixture's clock, and compares `tasks/state.json` after reading and serializing it again.
- `after/` equals `before/` where the step changed nothing: nothing is replaced and `seq` stays.

## Readings fixed with the set

- **Serialization.** A JSON document of the set is Python's `json.dumps(obj, sort_keys=True, indent=1,
  ensure_ascii=False)` and a newline. A line and a verdict are printed compact, their keys in §3's order.
- **Always present.** Every field of §1 is on every task and outcome, null where it has no value: `due`,
  `project`, `alias`, `agent`, `closed`, `shown`, `send`, `endedLine`. `body` is `""` when none was given, `tags`
  `[]`. An agent's `name` is null when none was given. An outcome's `text` is the note, the reason or the
  comment, `""` for a done with no note.
- **A new task** has `agentSeq` and `seenSeq` both at its `born`: it is not Updated.
- **Every line's first verdict is kept by its key**, whatever it was: `applied` (`seen` and `shown` too), `stale`,
  `closed` and `unknown`, each with the line's digest, and keeping it is one change of the store (`seq` + 1) even
  where nothing else changed. The same line again answers that verdict and changes nothing, whatever the store
  became since: a line refused `closed` stays refused after a reopen, one refused `unknown` after its id is made.
  An entry's `task` is the id the line named, held or not. `refused` (`key-reused`) answers a key already kept and
  is not kept itself. A door line where there is no store makes it, to keep its verdict. A human who wants to act
  again after a refusal does so under a new key, which the convenience verbs (`done`, `decline`, the human's
  `comment`) mint by default: a surface retries under the same key only a line whose verdict it did not see.
- **What the door checks** is what the schema says, and no more loosely: a task's id is `t` and a positive integer
  with no leading zero and no cap (`^t[1-9][0-9]*$`), an outcome's key that id, `.` and another; a revision is a
  positive integer. A field is of its type exactly: a boolean is no integer, an integer no boolean, and an integer
  is written without a fraction or exponent (`1`, never `1.0` or `1e0`). A text holds no lone surrogate (a `\\ud800`
  to `\\udfff` escape that pairs with nothing). A text that must say something is any string but `""`: whitespace is
  text. A line that breaks any of it refuses the whole call (exit 2), and nothing is applied. The schema's subset
  cannot say the two wire rules (the fraction and the lone surrogate): `examples/rejected.json` holds lines it takes
  and the door refuses.
- **The order of the refusals.** A key already used comes first (the stored verdict, or `key-reused`); then an
  unknown id; then a task no longer open (`closed`); then a revision that is not current (`stale`).
- **`seen`** raises `seenSeq` to the line's `seq`, never lowers it, and never past the store's `seq` before the
  step.
- **An outcome's `revision`** is the task's at the act; its key is `<id>.<acts>`, `acts` counted after the act.
- **A comment's `n`** counts the task's comments from 1, the human's and the agents' alike. The human's names its
  outcome; an agent's has `outcome: null`.
- **`wake`** is resolved at the act: the line's when it is not null, else whether the task is blocking.
- **Until M2** every outcome is written with `send: null` and `endedLine: null`, and `told` is `next-start` but for
  `ended` and `maws`; the schemas carry every value M2 fills (`examples/state.json`, where each `told` is paired
  with a `send` a step can reach: a send only with `now` or `wake`).
- **The readers.** `list --json` gives the tasks in the order of their ids' numbers, `waiting --json` the outcomes
  by `seq`; the text forms order as §3 says. `list --closed` is the closed tasks whose `closed.at` is within 30
  days, `--all` those and the open ones.
- **What `remind` prints** is `grammar/texts.md`'s `remind`: the keys line is empty when nothing waits, and a
  start line with neither part prints nothing after it.

## Pinning

A consumer copies this directory whole into its tree beside a provenance note naming the doperpowers merge commit,
the sminos version and `digest`, and recomputes the digest over its copy.
""")


def manifest():
    files = {p: sha(d) for p, d in sorted(FILES.items()) if p != "MANIFEST.json"}
    dig = sha("".join("%s  %s\n" % (h, p) for p, h in sorted(files.items())))
    FILES["MANIFEST.json"] = dump({"v": 1, "version": 1, "files": files, "digest": dig})
    return dig


def write(out):
    if os.path.isdir(out) and os.listdir(out):
        if os.path.realpath(out) != os.path.realpath(SET):
            sys.exit("tasks-contract: %s is not empty; --out takes a new or empty directory" % out)
        shutil.rmtree(out)
    for path, data in FILES.items():
        full = os.path.join(out, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)


def listing(root):
    out = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            full = os.path.join(dirpath, n)
            with open(full, "rb") as f:
                out[os.path.relpath(full, root)] = f.read()
    return out


def main(argv):
    dig = manifest()
    line_ = "tasks-contract: %d cases, digest %s" % (len(CASES), dig)
    if "--check" in argv:
        have = listing(SET) if os.path.isdir(SET) else {}
        wrong = sorted(p for p in set(have) | set(FILES) if have.get(p) != FILES.get(p))
        print(line_)
        if wrong:
            for p in wrong[:20]:
                print("  differs: %s" % p, file=sys.stderr)
            print("tasks-contract: the committed set is not this generator's (%d files)" % len(wrong), file=sys.stderr)
            return 1
        return 0
    out = argv[argv.index("--out") + 1] if "--out" in argv else SET
    write(out)
    print(line_)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
