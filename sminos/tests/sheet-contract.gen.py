#!/usr/bin/env python3
"""Writes sminos/types/sheet/: the question sheet's published set (contracts X1, X2, X3, X4 and X7 of MAWS's
docs/doperpowers/specs/2026-11-23-question-sheet-design.md; this repository's plan
docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md, I1 to I7 and M1). MAWS pins a copy of the set.

Every record, every `after`, every `show.*.json` and every envelope here is written by hand from the composite's
§4.2 and the plan's tables and I7's rules, never computed by sminos_sheet or any composer: the set is the contract
the step (M2), sminos's reader and MAWS's reader are all held to, not the output of any of them (the house rule of
dx4-jobs.gen.py). What the generator does compute is bookkeeping a hand would only get wrong: a byte offset, a
file's SHA-256, the manifest. It is deterministic: fixed session ids, times and keys.

    python3 -B sheet-contract.gen.py                 # writes the set in place (sminos/types/sheet/)
    python3 -B sheet-contract.gen.py --out <dir>     # writes it into <dir> (made empty first)
    python3 -B sheet-contract.gen.py --check         # the committed set is this generator's, byte for byte

Each prints `sheet-contract: <n> cases, <m> examples, digest <sha256>`.
"""

import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
SET = os.path.join(os.path.dirname(HERE), "types", "sheet")
HOME = "{HOME}"          # stands for $SMINOS_HOME in an envelope (I7)
PROJECT = "1c0de000-0000-5000-8000-0000000000aa"    # the project every question's `question` event went to
FILES = {}               # path in the set -> bytes


# ------------------------------------------------------------------ serialization


def dump(obj):
    """The generator's serialization of a JSON document: what M2's step output is compared in."""
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def jline(obj):
    """One inbox line as a surface writes it: compact, its keys in the order given."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def jstr(s):
    """A JSON string in an envelope's prose."""
    return json.dumps(s, ensure_ascii=False)


def block(obj):
    """The <sheet-delivery> block (I7): compact JSON, its keys as given, < > & U+2028 U+2029 escaped."""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(ch, esc)
    return "<sheet-delivery>" + text + "</sheet-delivery>"


def put(path, data):
    FILES[path] = data if isinstance(data, bytes) else data.encode()


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


# A 1x1 white PNG: what a surface saves under uploads/ for a pasted image. Literal bytes, so no zlib build changes
# them; the suite checks each chunk's CRC and inflates its data.
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000b4944415478da63f80f040009fb03fd68fa1ccc0000000049454e44ae426082")


# ------------------------------------------------------------------ schemas (I1: JSON Schema 2020-12, a subset)

T_TIME = {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{3}Z$"}
T_ID = {"type": "string", "pattern": "^q[1-9][0-9]{0,8}$"}
T_KEY = {"type": "string", "pattern": "^[A-Za-z0-9._:-]{8,128}$"}
T_UPLOAD = {"type": "string", "pattern": "^uploads/[A-Za-z0-9._-]{1,250}\\.(png|jpg|jpeg|gif|webp)$"}
T_SHA = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
T_BY = {"type": "string", "enum": ["page", "maws", "desk", "cli"]}
T_INT0 = {"type": "integer", "minimum": 0}
T_INT1 = {"type": "integer", "minimum": 1}


def obj(props, required, extra=False):
    return {"type": "object", "properties": props, "required": required, "additionalProperties": extra}


def arr(items, **bounds):
    return {"type": "array", "items": items, **bounds}


T_AGENT = {"type": "string", "minLength": 1, "maxLength": 128}     # an agent id: the contract's bound, never cut
ASKER = {"oneOf": [{"type": "string", "const": "main"},
                   obj({"agentId": T_AGENT, "name": {"type": "string"}}, ["agentId", "name"])]}
RECIPIENT = {"oneOf": [{"type": "string", "const": "main"}, obj({"agentId": T_AGENT}, ["agentId"])]}
OPTION = obj({"label": {"type": "string"}, "description": {"type": "string"}, "preview": {"type": "string"},
              "recommended": {"type": "boolean"}}, ["label"])
REFERENCE_PROPS = {
    "path": {"type": "string", "minLength": 1}, "lines": arr(T_INT1, minItems=2, maxItems=2),
    "abs": {"type": "string", "minLength": 1}, "sha256": T_SHA, "bytes": T_INT0,
    "kind": {"type": "string", "enum": ["text", "image"]}, "mediaType": {"type": "string"},
    "startLine": T_INT1, "numLines": T_INT0, "totalLines": T_INT0, "size": T_INT0, "mtimeMs": T_INT0}
REFERENCE_REQ = ["path", "abs", "sha256", "bytes", "kind", "size", "mtimeMs"]
QUESTION_PROPS = {
    "id": {"$ref": "#/$defs/id"}, "revision": T_INT1, "asker": {"$ref": "#/$defs/asker"},
    "header": {"type": "string"}, "question": {"type": "string"}, "options": arr({"$ref": "#/$defs/option"}),
    "multiSelect": {"type": "boolean"}, "context": {"type": "string"},
    "references": arr({"$ref": "#/$defs/reference"}), "askedAt": {"$ref": "#/$defs/time"},
    "callId": {"type": "string", "minLength": 1},
    "importedFrom": obj({"callId": {"type": "string", "minLength": 1}, "index": T_INT0}, ["callId", "index"])}
QUESTION_REQ = ["id", "revision", "asker", "question", "options", "multiSelect", "references", "askedAt", "callId"]
SNAPSHOT = obj({"asker": {"$ref": "#/$defs/asker"}, "header": {"type": "string"}, "question": {"type": "string"},
                "options": arr({"type": "string"}), "multiSelect": {"type": "boolean"},
                "askedAt": {"$ref": "#/$defs/time"}}, ["asker", "question", "options", "multiSelect", "askedAt"])
def variants(common, required, shapes):
    """A discriminated shape: one closed object for each variant, the variant's own fields beside the common ones,
    so a field that belongs to another variant is refused."""
    return {"oneOf": [obj({**common, **extra}, required + extra_req) for extra, extra_req in shapes]}


OUTCOME_COMMON = {
    "key": {"$ref": "#/$defs/key"}, "id": {"$ref": "#/$defs/id"}, "revision": T_INT1, "by": T_BY,
    "at": {"$ref": "#/$defs/time"}, "acceptedAt": {"$ref": "#/$defs/time"}, "batch": {"$ref": "#/$defs/key"},
    "recipient": {"$ref": "#/$defs/recipient"}, "taken": {"type": "boolean"}, "acrossStop": {"type": "boolean"},
    "question": {"$ref": "#/$defs/snapshot"}}
OUTCOME_REQ = ["key", "kind", "id", "revision", "by", "at", "acceptedAt", "recipient", "taken", "acrossStop",
               "question"]
ANSWER_FIELDS = {"kind": {"type": "string", "const": "answer"}, "picks": arr({"type": "string"}),
                 "text": {"type": "string"}, "textFile": {"type": "string", "pattern": "^texts/[0-9a-f]{64}\\.txt$"},
                 "images": arr(T_UPLOAD)}
DISMISS_FIELDS = {"kind": {"type": "string", "const": "dismiss"}}
OUTCOME = variants(OUTCOME_COMMON, OUTCOME_REQ, [(ANSWER_FIELDS, ["picks", "text", "images"]), (DISMISS_FIELDS, [])])
# show's pending outcome: an answer's picks also as places, and in the keyed form a text cut to 500 (I4)
SHOW_OUTCOME = variants(OUTCOME_COMMON, OUTCOME_REQ, [
    ({**ANSWER_FIELDS, "picks": arr({"type": "string", "maxLength": 200}),
      "text": {"type": "string", "maxLength": 20000}, "places": arr(T_INT1),
      "textCut": {"type": "boolean", "const": True}}, ["picks", "text", "images", "places"]), (DISMISS_FIELDS, [])])
# ...and its question as the reader cuts it (I4, step 7): the state schema keeps the record's strings unbounded
CUT_ASKER = {"oneOf": [{"type": "string", "const": "main"},
                       obj({"agentId": T_AGENT, "name": {"type": "string", "maxLength": 200}}, ["agentId", "name"])]}
CUT_SNAPSHOT = obj({"asker": {"$ref": "#/$defs/cutAsker"}, "header": {"type": "string", "maxLength": 60},
                    "question": {"type": "string", "maxLength": 2000},
                    "options": arr({"type": "string", "maxLength": 200}), "multiSelect": {"type": "boolean"},
                    "askedAt": {"$ref": "#/$defs/time"}}, ["asker", "question", "options", "multiSelect", "askedAt"])
HOW = {"type": "string", "enum": ["answered", "dismissed", "withdrawn"]}
CLOSED_COMMON = {"at": {"$ref": "#/$defs/time"}, "revision": T_INT1, "asker": {"$ref": "#/$defs/asker"},
                 "header": {"type": "string"}, "question": {"type": "string"}}
DELIVERED_AT = {"deliveredAt": {"$ref": "#/$defs/time"}}      # an answer and a dismissal are delivered; no withdrawal
CLOSED = variants(CLOSED_COMMON, ["how", "at", "revision", "asker", "question"], [
    ({"how": {"type": "string", "const": "answered"}, "receipt": {"type": "string"}, "places": arr(T_INT1),
      "key": {"$ref": "#/$defs/key"}, "answer": {"type": "string"}, **DELIVERED_AT}, ["receipt", "places", "key"]),
    ({"how": {"type": "string", "const": "dismissed"}, "key": {"$ref": "#/$defs/key"}, **DELIVERED_AT}, ["key"]),
    ({"how": {"type": "string", "const": "withdrawn"}}, [])])
SHOW_CLOSED = variants({k: v for k, v in CLOSED_COMMON.items() if k != "question"}, ["how", "at", "revision", "asker"], [
    ({"how": {"type": "string", "const": "answered"}, "receipt": {"type": "string"}, "places": arr(T_INT1),
      **DELIVERED_AT}, ["receipt", "places"]),
    ({"how": {"type": "string", "const": "dismissed"}, **DELIVERED_AT}, []),
    ({"how": {"type": "string", "const": "withdrawn"}}, [])])


def verdict_shapes(extra=None, states=None):
    """The verdicts, one closed shape for each (verdict, kind) pair, its own fields required (I2): what a reader is
    owed for each refusal. `extra` adds fields to every shape; `states` maps a verdict to what `sent` reads."""
    one = lambda v, kinds, own, req: (  # noqa: E731
        {"verdict": {"type": "string", "const": v},
         "kind": {"type": "string", "enum": kinds} if len(kinds) > 1 else {"type": "string", "const": kinds[0]},
         **own, **({} if extra is None else extra),
         **({} if states is None else {"state": states.get((v, kinds[0]), states.get(v))})}, req)
    ID, KEYREF = {"id": {"$ref": "#/$defs/id"}}, {"$ref": "#/$defs/key"}
    return [one("applied", ["answer", "dismiss"], ID, ["id"]),
            one("applied", ["delivered"], {}, []),
            one("stale", ["answer"], {**ID, "current": T_INT1}, ["id", "current"]),
            one("closed", ["answer", "dismiss"],
                {**ID, "how": {"type": "string", "enum": ["answered", "dismissed", "withdrawn", "unknown"]}},
                ["id", "how"]),
            one("retracted", ["answer", "dismiss"], ID, ["id"]),
            one("retracted", ["retract"], {"target": KEYREF}, ["target"]),
            one("retracted", ["unseen"], {"by": KEYREF}, ["by"]),
            one("too-late", ["retract"], {"target": KEYREF}, ["target"])]


VERDICT = variants({"at": {"$ref": "#/$defs/time"}}, ["verdict", "kind", "at"], verdict_shapes())
QUEUED_STATE = {"state": {"type": "string", "const": "queued"}}
SENT = variants({"key": {"$ref": "#/$defs/key"}}, ["key", "kind", "state"], [
    # a queued line, by its kind: an answer or a dismissal names its question and may be cancelled; a retract names
    # its target; a delivered line names neither
    ({"kind": {"type": "string", "enum": ["answer", "dismiss"]}, "id": {"$ref": "#/$defs/id"},
      "cancelled": {"type": "boolean", "const": True}, **QUEUED_STATE}, ["id"]),
    ({"kind": {"type": "string", "const": "retract"}, "target": {"$ref": "#/$defs/key"}, **QUEUED_STATE}, ["target"]),
    ({"kind": {"type": "string", "const": "delivered"}, **QUEUED_STATE}, [])]
    + [(shape, req + ["verdict", "at"]) for shape, req in verdict_shapes(
        {"at": {"$ref": "#/$defs/time"}},
        {"applied": {"type": "string", "enum": ["accepted", "delivered"]},
         ("applied", "delivered"): {"type": "string", "const": "delivered"},     # its own key is never pending
         **{v: {"type": "string", "const": v} for v in ("stale", "closed", "retracted", "too-late")}})])

COMMON_DEFS = {"time": T_TIME, "id": T_ID, "key": T_KEY, "asker": ASKER, "recipient": RECIPIENT, "option": OPTION,
               "snapshot": SNAPSHOT}


def schema(title, body, defs):
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": title, **body, "$defs": defs}


REFERENCE_KINDS = [{"properties": {"kind": {"const": "text"}}, "required": ["startLine", "numLines", "totalLines"]},
                   {"properties": {"kind": {"const": "image"}}, "required": ["mediaType"]}]
STATE_SCHEMA = schema(
    "state.json: one session's sheet (plan I2). Structure, not the tool input's bounds.",
    obj({
        "v": {"type": "integer", "const": 1}, "session": {"type": "string", "minLength": 1}, "seq": T_INT0,
        "nextId": T_INT1, "inbox": obj({"offset": T_INT0, "skipped": T_INT0}, ["offset", "skipped"]),
        "questions": arr({"$ref": "#/$defs/question"}), "pending": arr({"$ref": "#/$defs/outcome"}),
        "closed": {"type": "object", "additionalProperties": {"$ref": "#/$defs/closed"}},
        "verdicts": {"type": "object", "additionalProperties": {"$ref": "#/$defs/verdict"}},
        "calls": arr({"oneOf": [obj({"callId": {"type": "string", "minLength": 1}, "result": {"type": "string"}},
                                    ["callId", "result"]),
                                obj({"callId": {"type": "string", "minLength": 1},
                                     "foreclosed": {"type": "boolean", "const": True}}, ["callId", "foreclosed"])]}),
        "log": obj({"next": T_INT1,
                    "owed": arr(obj({"n": T_INT1, "kind": {"type": "string", "enum": ["question", "answered"]},
                                     "src": {"type": "string", "pattern": "^sheet:[^:]+:q[1-9][0-9]{0,8}$"},
                                     "text": {"type": ["string", "array"], "items": {"type": "string"}},
                                     "choices": arr({"type": "string"}),
                                     "closed": {"type": "string", "enum": ["dismissed", "withdrawn", "removed"]}},
                                    ["n", "kind", "src", "text"])),
                    "projects": {"type": "object", "additionalProperties": {"type": "string"}}},
                   ["next", "owed", "projects"]),
        "import": obj({"never": {"type": "boolean"},
                       "calls": {"type": "object", "additionalProperties": arr({"$ref": "#/$defs/id"})}},
                      ["never", "calls"])},
        ["v", "session", "seq", "nextId", "inbox", "questions", "pending", "closed", "verdicts", "calls", "log",
         "import"]),
    {**COMMON_DEFS, "reference": {**obj(REFERENCE_PROPS, REFERENCE_REQ), "oneOf": REFERENCE_KINDS},
     "question": obj(QUESTION_PROPS, QUESTION_REQ), "outcome": OUTCOME, "closed": CLOSED,
     "verdict": VERDICT})

LINE_PROPS = {
    "v": {"type": "integer", "const": 1}, "key": {"$ref": "#/$defs/key"},
    "kind": {"type": "string", "enum": ["answer", "dismiss", "retract", "delivered"]},
    "id": {"$ref": "#/$defs/id"}, "revision": T_INT1, "picks": arr({"type": "string"}, maxItems=12),
    "text": {"type": "string", "maxLength": 20000}, "images": arr(T_UPLOAD, maxItems=8),
    "target": {"$ref": "#/$defs/key"}, "keys": arr({"$ref": "#/$defs/key"}, minItems=1, maxItems=200),
    "batch": {"$ref": "#/$defs/key"}, "by": T_BY, "at": {"$ref": "#/$defs/time"}}
INBOX_SCHEMA = schema(
    "One inbox.jsonl line (composite §4.1; plan I3). The door takes at most 50 lines a call.",
    {"type": "object", "properties": LINE_PROPS, "required": ["v", "key", "kind", "by"],
     "additionalProperties": False,
     "oneOf": [
         {"properties": {"kind": {"const": "answer"}}, "required": ["id", "revision"],
          "oneOf": [{"properties": {"picks": {"minItems": 1}, "text": {"minLength": 1}}, "required": ["picks", "text"]},
                    {"properties": {"picks": {"minItems": 1}, "text": {"maxLength": 0}}, "required": ["picks"]},
                    {"properties": {"picks": {"maxItems": 0}, "text": {"minLength": 1}}, "required": ["text"]}]},
         {"properties": {"kind": {"const": "dismiss"}}, "required": ["id"]},
         {"properties": {"kind": {"const": "retract"}}, "required": ["target"]},
         {"properties": {"kind": {"const": "delivered"}}, "required": ["keys"]}]},
    {"time": T_TIME, "id": T_ID, "key": T_KEY})

SHOW_REFERENCE = {**obj({**REFERENCE_PROPS, "changed": {"type": ["boolean", "null"]}}, REFERENCE_REQ + ["changed"]),
                  "oneOf": REFERENCE_KINDS}
QUEUED = obj({"key": {"$ref": "#/$defs/key"}, "kind": {"type": "string", "const": "answer"},
              "picks": arr({"type": "string"}), "text": {"type": "string"}, "images": arr(T_UPLOAD),
              "revision": T_INT1, "by": T_BY, "at": {"$ref": "#/$defs/time"}},
             ["key", "kind", "picks", "text", "images", "revision", "by"])
SHOW_SCHEMA = schema(
    "What `sminos sheet show --json` prints (plan I4). With --keys, `open`, `hidden` and `closed` are left out and "
    "each pending outcome's `text` is its first 500 characters, with `textCut` when it was longer.",
    obj({
        "v": {"type": "integer", "const": 1}, "session": {"type": "string", "minLength": 1}, "seq": T_INT0,
        "open": arr(obj({**QUESTION_PROPS, "references": arr({"$ref": "#/$defs/reference"}),
                         "handle": {"type": "string", "pattern": "^q[1-9][0-9]{0,8}(@[1-9][0-9]*)?$"},
                         "queued": {"$ref": "#/$defs/queued"}}, QUESTION_REQ + ["handle"])),
        "hidden": arr(obj({"id": {"$ref": "#/$defs/id"}, "key": {"$ref": "#/$defs/key"}}, ["id", "key"])),
        "sent": arr({"$ref": "#/$defs/sent"}),
        "pending": arr({"$ref": "#/$defs/outcome"}),
        "closed": {"type": "object", "additionalProperties": {"$ref": "#/$defs/closed"}}},
        ["v", "session", "seq", "sent", "pending"]),
    {**COMMON_DEFS, "reference": SHOW_REFERENCE, "queued": QUEUED, "outcome": SHOW_OUTCOME, "closed": SHOW_CLOSED,
     "sent": SENT, "snapshot": CUT_SNAPSHOT, "cutAsker": CUT_ASKER})

DELIVERY_SCHEMA = schema(
    "The <sheet-delivery> block (plan I7): the last line of an envelope, terminal form and steer form alike.",
    obj({"v": {"type": "integer", "const": 1}, "keys": arr({"$ref": "#/$defs/key"}, maxItems=200),
         "answered": arr(obj({"id": {"$ref": "#/$defs/id"}, "revision": T_INT1, "picks": arr(T_INT1),
                              "text": {"type": "string", "maxLength": 500},
                              "textCut": {"type": "boolean", "const": True},
                              "textFile": {"type": "string", "minLength": 1},
                              "images": arr({"type": "string", "minLength": 1})},
                             ["id", "revision", "picks", "text", "images"])),
         "dismissed": arr({"$ref": "#/$defs/id"}), "more": {"type": "boolean", "const": True}},
        ["v", "keys", "answered", "dismissed"]),
    {"id": T_ID, "key": T_KEY})

SURFACE_SCHEMA = schema(
    "A surface's registration, $SMINOS_HOME/sheet/surfaces/<name>.json (composite §7; plan I8).",
    obj({"v": {"type": "integer", "const": 1}, "name": {"type": "string", "pattern": "^[A-Za-z0-9._-]{1,64}$"},
         "pid": T_INT1, "url": {"type": "string", "minLength": 1},
         "reach": {"type": "string", "enum": ["local", "remote"]}, "heartbeatAt": T_TIME},
        ["v", "name", "pid", "url", "reach", "heartbeatAt"]),
    {})

TOOL_INPUT_SCHEMA = schema(
    "The tool's input (composite §2.1 with §1's limits), without descriptions. Two rules of the whole call are "
    "not stated here: at least one of `ask` and `withdraw` non-empty, and an id at most once across both. An "
    "entry's own rules (U14: unique labels, a preview only without multiSelect, multiSelect only with options, "
    "lines in order) refuse that entry alone and are not stated here either (plan I6).",
    obj({"ask": arr({"$ref": "#/$defs/entry"}, minItems=1, maxItems=20),
         "withdraw": arr({"$ref": "#/$defs/id"}, minItems=1)}, []),
    {"id": T_ID,
     "entry": obj({"id": {"$ref": "#/$defs/id"}, "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                   "header": {"type": "string", "maxLength": 60},
                   "options": arr({"$ref": "#/$defs/option"}, maxItems=12), "multiSelect": {"type": "boolean"},
                   "context": {"type": "string", "maxLength": 8000},
                   "references": arr({"$ref": "#/$defs/reference"}, maxItems=8)}, ["question"]),
     "option": obj({"label": {"type": "string", "minLength": 1, "maxLength": 200},
                    "description": {"type": "string", "maxLength": 500},
                    "preview": {"type": "string", "maxLength": 8000}, "recommended": {"type": "boolean"}}, ["label"]),
     "reference": obj({"path": {"type": "string", "minLength": 1},
                       "lines": arr({"type": "integer"}, minItems=2, maxItems=2)}, ["path"])})


# ------------------------------------------------------------------ the record's parts, written out


def session(n):
    return "5eed0000-0000-4000-8000-0000000000%02d" % n


def opt(label, description=None, recommended=False, preview=None):
    o = {"label": label}
    if description is not None:
        o["description"] = description
    if preview is not None:
        o["preview"] = preview
    if recommended:
        o["recommended"] = True
    return o


def question(id_, q, asked, call, options=(), header=None, revision=1, asker="main", multi=False, context=None,
             refs=(), imported=None):
    out = {"id": id_, "revision": revision, "asker": asker, "question": q, "options": list(options),
           "multiSelect": multi, "references": list(refs), "askedAt": asked, "callId": call}
    if header is not None:
        out["header"] = header
    if context is not None:
        out["context"] = context
    if imported is not None:
        out["importedFrom"] = imported
    return out


def snapshot(qn):
    """An outcome's copy of its question: the asker, header, text and labels at the answered revision."""
    s = {"asker": qn["asker"], "question": qn["question"], "options": [o["label"] for o in qn["options"]],
         "multiSelect": qn["multiSelect"], "askedAt": qn["askedAt"]}
    if "header" in qn:
        s["header"] = qn["header"]
    return s


def answer_out(line, qn, accepted, recipient="main", taken=False, across=False, text_file=None):
    o = {"key": line["key"], "kind": "answer", "id": qn["id"], "revision": line["revision"],
         "picks": line.get("picks", []), "text": line.get("text", ""), "images": line.get("images", []),
         "by": line["by"], "at": line["at"], "acceptedAt": accepted, "recipient": recipient, "taken": taken,
         "acrossStop": across, "question": snapshot(qn)}
    if "batch" in line:
        o["batch"] = line["batch"]
    if text_file is not None:
        o["textFile"] = text_file
    return o


def dismiss_out(line, qn, accepted, recipient="main", taken=False, across=False):
    o = {"key": line["key"], "kind": "dismiss", "id": qn["id"], "revision": qn["revision"], "by": line["by"],
         "at": line["at"], "acceptedAt": accepted, "recipient": recipient, "taken": taken, "acrossStop": across,
         "question": snapshot(qn)}
    if "batch" in line:
        o["batch"] = line["batch"]
    return o


def said(qn, picks, text):
    """I7's line after the id, in its full-text form (no asker, no times): what Closed.answer (cut to 2,000) and the
    log's `answered` event (whole) keep of an answer."""
    head = jstr(qn["question"][:200] + ("…" if len(qn["question"]) > 200 else "")) + " → "
    labels = [p[:200] + ("…" if len(p) > 200 else "") for p in picks]
    if labels:
        return head + ", ".join(labels) + "." + (" Their text: " + jstr(text) if text else "")
    return head + "their text: " + jstr(text)


def closed_answered(qn, line, at):
    picks, text = line.get("picks", []), line.get("text", "")
    labels = [o["label"] for o in qn["options"]]
    c = {"how": "answered", "at": at, "revision": line["revision"], "asker": qn["asker"],
         "question": qn["question"][:200], "receipt": ", ".join(picks) if picks else text[:80],
         "places": [labels.index(p) + 1 for p in picks], "key": line["key"], "answer": said(qn, picks, text)[:2000]}
    if "header" in qn:
        c["header"] = qn["header"]
    return c


def closed_other(qn, how, at, key=None):
    c = {"how": how, "at": at, "revision": qn["revision"], "asker": qn["asker"], "question": qn["question"][:200]}
    if "header" in qn:
        c["header"] = qn["header"]
    if key is not None:
        c["key"] = key
    return c


def V(verdict, kind, at, **f):
    return {"verdict": verdict, "kind": kind, "at": at, **f}


def owed_question(n, sess, qn):
    return {"n": n, "kind": "question", "src": "sheet:%s:%s" % (sess, qn["id"]), "text": [qn["question"]],
            "choices": [o["label"] for o in qn["options"]]}


def owed_answered(n, sess, qn, line):
    return {"n": n, "kind": "answered", "src": "sheet:%s:%s" % (sess, qn["id"]),
            "text": said(qn, line.get("picks", []), line.get("text", ""))}


def owed_closed(n, sess, qn, how):
    return {"n": n, "kind": "answered", "src": "sheet:%s:%s" % (sess, qn["id"]), "text": how, "closed": how}


def record(sess, seq, next_id, offset, questions=(), pending=(), closed=None, verdicts=None, log_next=None,
           owed=(), projects=None, calls=(), skipped=0, never=False, imports=None):
    return {"v": 1, "session": sess, "seq": seq, "nextId": next_id, "inbox": {"offset": offset, "skipped": skipped},
            "questions": list(questions), "pending": list(pending), "closed": dict(closed or {}),
            "verdicts": dict(verdicts or {}), "calls": list(calls),
            "log": {"next": log_next if log_next is not None else next_id, "owed": list(owed),
                    "projects": dict(projects if projects is not None else
                                     {"q%d" % i: PROJECT for i in range(1, next_id)})},
            "import": {"never": never, "calls": dict(imports or {})}}


def L(key, kind, by, at, **f):
    """An inbox line, its keys in the order a surface writes them."""
    out = {"v": 1, "key": key, "kind": kind}
    for k in ("id", "revision", "picks", "text", "images", "target", "keys", "batch"):
        if k in f:
            out[k] = f[k]
    out["by"], out["at"] = by, at
    return out


def inbox(lines):
    return "".join(x if isinstance(x, str) else jline(x) + "\n" for x in lines)


def drain(keys, running=()):
    return {"event": "drain", "runner": "terminal", "remote": False,
            "agents": {"running": list(running), "direct": True}, "acked": [], "keys": list(keys)}


def start(source, asks=(), floor=None):
    s = {"source": source, "today": {"definite": True, "asks": list(asks)}}
    if floor is not None:
        s["floor"] = floor
    return {"event": "start", "runner": "terminal", "remote": False, "agents": {"running": [], "direct": True},
            "acked": [], "start": s}


# What `show --json` prints for one: written per case below, from these parts.

def shown(qn, queued=None):
    s = dict(qn)
    s["references"] = [dict(r, changed=True) for r in qn["references"]]    # the fixtures' files exist nowhere
    s["handle"] = qn["id"] if qn["revision"] == 1 else "%s@%d" % (qn["id"], qn["revision"])
    if queued is not None:
        s["queued"] = {"key": queued["key"], "kind": "answer", "picks": queued.get("picks", []),
                       "text": queued.get("text", ""), "images": queued.get("images", []),
                       "revision": queued["revision"], "by": queued["by"]}
        if "at" in queued:
            s["queued"]["at"] = queued["at"]
    return s


def q_sent(line, cancelled=False):
    s = {"key": line["key"], "kind": line["kind"], "state": "queued"}
    if "id" in line:
        s["id"] = line["id"]
    if "target" in line:
        s["target"] = line["target"]
    if cancelled:
        s["cancelled"] = True
    return s


def v_sent(key, state, verdict):
    return {"key": key, "state": state, **verdict}


def shown_closed(c):
    return {k: c[k] for k in ("how", "at", "revision", "asker", "header", "receipt", "places", "deliveredAt") if k in c}


def shown_pending(o):
    """A pending outcome as show prints it: an answer's picks also as places; each string under its cut (I4), which
    none of the fixtures' outcomes reaches."""
    s = dict(o)
    if o["kind"] == "answer":
        s["places"] = [o["question"]["options"].index(p) + 1 for p in o["picks"]]
    return s


def show(sess, seq, open_=(), hidden=(), sent=(), pending=(), closed=None):
    return {"v": 1, "session": sess, "seq": seq, "open": list(open_), "hidden": list(hidden),
            "sent": sorted([s for s in sent if s["state"] != "queued"], key=lambda s: s["key"])
            + [s for s in sent if s["state"] == "queued"],
            "pending": [shown_pending(o) for o in pending],
            "closed": {k: shown_closed(v) for k, v in (closed or {}).items()}}


CASES = []


def case(name, covers, n, now, event, verdicts, before, after, show_before, show_after):
    """One fixture. `before` and `after`: {path under sheet/<session>/: bytes or a document}, or None for a $SMINOS_HOME
    with no record."""
    sess = session(n)
    CASES.append(name)
    base = "fixtures/%s/" % name
    put(base + "case.json", dump({"name": name, "covers": covers, "session": sess, "now": now, "event": event,
                                  "verdicts": verdicts}))
    for side, files in (("before", before), ("after", after)):
        for path, data in sorted((files or {}).items()):
            put("%s%s/sheet/%s/%s" % (base, side, sess, path),
                dump(data) if isinstance(data, dict) else data)
    put(base + "show.before.json", dump(show_before))
    put(base + "show.after.json", dump(show_after))


def offset(*parts):
    return len(inbox(parts).encode())


# ------------------------------------------------------------------ the fixtures (plan M1's table)

AUTH = "Which auth method should the login use?"
AUTH_OPTS = [opt("OAuth", "The provider's flow; nothing stored here.", recommended=True),
             opt("Passkeys", "WebAuthn; needs a fallback on old devices."), opt("Magic link")]
SHIP = "Ship the migration today?"
YES_NO = [opt("Yes", recommended=True), opt("No")]
EMPTY_Q = "What should the empty state say?"
CACHE = "Should the cache key include the locale?"


def q_auth(n=1, revision=1, asker="main", multi=False):
    return question("q%d" % n, AUTH, "2026-11-23T09:01:00.000Z", "toolu_01Auth%04d" % n, AUTH_OPTS, "Auth method",
                    revision=revision, asker=asker, multi=multi)


def q_ship(n=2, revision=1, asker="main"):
    return question("q%d" % n, SHIP, "2026-11-23T09:02:00.000Z", "toolu_01Ship%04d" % n, YES_NO, "Migration",
                    revision=revision, asker=asker)


def q_empty(n=3, revision=1, asker="main"):
    return question("q%d" % n, EMPTY_Q, "2026-11-23T09:03:00.000Z", "toolu_01Empt%04d" % n, (), "Empty state",
                    revision=revision, asker=asker)


# 1 · empty
S = session(1)
NOW = "2026-11-23T09:00:00.000Z"
case("empty", "a new record: a start on a session with none", 1, NOW, start("startup"), {},
     None, {"state.json": record(S, 1, 1, 0), "inbox.jsonl": b""}, None,
     show(S, 1))

# 2 · answer-applied
S, NOW = session(2), "2026-11-23T10:00:00.000Z"
q1, q2 = q_auth(1), q_ship(2)
a = L("page-0201a001", "answer", "page", "2026-11-23T09:59:58.120Z", id="q1", revision=1, picks=["OAuth"],
      text="OAuth first; passkeys later.", images=["uploads/sketch.png"])
off = offset(a)
before = {"state.json": record(S, 4, 3, 0, [q1, q2]), "inbox.jsonl": inbox([a]), "uploads/sketch.png": PNG}
out = answer_out(a, q1, NOW)
after = {"state.json": record(S, 5, 3, off, [q2], [out], {"q1": closed_answered(q1, a, NOW)},
                              {a["key"]: V("applied", "answer", NOW, id="q1")}, 4, [owed_answered(3, S, q1, a)]),
         "inbox.jsonl": inbox([a]), "uploads/sketch.png": PNG}
case("answer-applied", "§4.2 row 1: an answer to an open question at its revision, a pick with text and an image",
     2, NOW, drain([a["key"]]), {a["key"]: V("applied", "answer", NOW, id="q1")}, before, after,
     show(S, 4, [shown(q1, a), shown(q2)], sent=[q_sent(a)]),
     show(S, 5, [shown(q2)], sent=[v_sent(a["key"], "accepted", V("applied", "answer", NOW, id="q1"))],
          pending=[out], closed={"q1": closed_answered(q1, a, NOW)}))

# 3 · answer-stale
S, NOW = session(3), "2026-11-23T10:00:00.000Z"
q1 = question("q1", AUTH, "2026-11-23T09:30:00.000Z", "toolu_01Auth0003", AUTH_OPTS[:2], "Auth method", revision=2)
a = L("page-0301a001", "answer", "page", "2026-11-23T09:59:58.000Z", id="q1", revision=1, picks=["OAuth"])
before = {"state.json": record(S, 6, 2, 0, [q1]), "inbox.jsonl": inbox([a])}
vd = V("stale", "answer", NOW, id="q1", current=2)
after = {"state.json": record(S, 7, 2, offset(a), [q1], verdicts={a["key"]: vd}), "inbox.jsonl": inbox([a])}
case("answer-stale", "§4.2 row 2: an answer to revision 1 of a question at revision 2", 3, NOW, drain([a["key"]]),
     {a["key"]: vd}, before, after,
     show(S, 6, [shown(q1, a)], sent=[q_sent(a)]),
     show(S, 7, [shown(q1)], sent=[v_sent(a["key"], "stale", vd)]))

# 4 · two-surfaces
S, NOW = session(4), "2026-11-23T10:00:00.000Z"
q1 = q_ship(1)
a = L("page-0401a001", "answer", "page", "2026-11-23T09:59:50.000Z", id="q1", revision=1, picks=["Yes"])
b = L("cli-0401b002", "answer", "cli", "2026-11-23T09:59:55.000Z", id="q1", revision=1, picks=["No"],
      text="not before the review")
before = {"state.json": record(S, 2, 2, 0, [q1]), "inbox.jsonl": inbox([a, b])}
out = answer_out(a, q1, NOW)
va, vb = V("applied", "answer", NOW, id="q1"), V("closed", "answer", NOW, id="q1", how="answered")
after = {"state.json": record(S, 3, 2, offset(a, b), [], [out], {"q1": closed_answered(q1, a, NOW)},
                              {a["key"]: va, b["key"]: vb}, 3, [owed_answered(2, S, q1, a)]),
         "inbox.jsonl": inbox([a, b])}
case("two-surfaces", "§4.2 rows 1 and 3: two answers to one question in one tail, from page and cli; the first "
     "applied wins", 4, NOW, drain([a["key"], b["key"]]), {a["key"]: va, b["key"]: vb}, before, after,
     show(S, 2, [shown(q1, a)], sent=[q_sent(a), q_sent(b)]),
     show(S, 3, [], sent=[v_sent(a["key"], "accepted", va), v_sent(b["key"], "closed", vb)], pending=[out],
          closed={"q1": closed_answered(q1, a, NOW)}))

# 5 · closed-withdrawn
S, NOW = session(5), "2026-11-23T10:00:00.000Z"
q1, q2, q3 = q_auth(1), q_ship(2), q_empty(3)
cl = {"q2": closed_other(q2, "withdrawn", "2026-11-23T09:20:00.000Z"),
      "q3": closed_other(q3, "withdrawn", "2026-11-23T09:21:00.000Z")}
a = L("page-0501a001", "answer", "page", "2026-11-23T09:59:50.000Z", id="q2", revision=1, picks=["Yes"])
d = L("page-0501a002", "dismiss", "page", "2026-11-23T09:59:51.000Z", id="q2")
before = {"state.json": record(S, 5, 4, 0, [q1], closed=cl, log_next=6), "inbox.jsonl": inbox([a, d])}
va = V("closed", "answer", NOW, id="q2", how="withdrawn")
vd = V("closed", "dismiss", NOW, id="q2", how="withdrawn")
after = {"state.json": record(S, 6, 4, offset(a, d), [q1], closed=cl, verdicts={a["key"]: va, d["key"]: vd},
                              log_next=6),
         "inbox.jsonl": inbox([a, d])}
case("closed-withdrawn", "§4.2 row 3: an answer and a dismissal for a withdrawn question; show's closed reads "
     "withdrawn for q3, which no line ever touched", 5, NOW, drain([a["key"], d["key"]]),
     {a["key"]: va, d["key"]: vd}, before, after,
     show(S, 5, [shown(q1)], sent=[q_sent(a), q_sent(d)], closed=cl),
     show(S, 6, [shown(q1)], sent=[v_sent(a["key"], "closed", va), v_sent(d["key"], "closed", vd)], closed=cl))

# 6 · dismiss-applied
S, NOW = session(6), "2026-11-23T10:00:00.000Z"
q1 = question("q1", AUTH, "2026-11-23T09:30:00.000Z", "toolu_01Auth0006", AUTH_OPTS, "Auth method", revision=2)
q2 = q_ship(2)
d = L("page-0601d001", "dismiss", "page", "2026-11-23T09:59:58.000Z", id="q1")
before = {"state.json": record(S, 7, 3, 0, [q1, q2]), "inbox.jsonl": inbox([d])}
out = dismiss_out(d, q1, NOW)
vd = V("applied", "dismiss", NOW, id="q1")
cl = {"q1": closed_other(q1, "dismissed", NOW, d["key"])}
after = {"state.json": record(S, 8, 3, offset(d), [q2], [out], cl, {d["key"]: vd}, 4,
                              [owed_closed(3, S, q1, "dismissed")]),
         "inbox.jsonl": inbox([d])}
case("dismiss-applied", "§4.2 row 4: a dismissal of an open question, whatever its revision; hidden while queued",
     6, NOW, drain([d["key"]]), {d["key"]: vd}, before, after,
     show(S, 7, [shown(q2)], [{"id": "q1", "key": d["key"]}], [q_sent(d)]),
     show(S, 8, [shown(q2)], sent=[v_sent(d["key"], "accepted", vd)], pending=[out], closed=cl))

# 7 · retract-queued
S, NOW = session(7), "2026-11-23T10:00:00.000Z"
q1, q2 = q_auth(1), q_ship(2)
a1 = L("page-0701a001", "answer", "page", "2026-11-23T09:59:40.000Z", id="q1", revision=1, picks=["Passkeys"])
r1 = L("page-0701r002", "retract", "page", "2026-11-23T09:59:41.000Z", target=a1["key"])
a2 = L("page-0701a003", "answer", "page", "2026-11-23T09:59:42.000Z", id="q2", revision=1, picks=["Yes"])
r2 = L("page-0701r004", "retract", "page", "2026-11-23T09:59:43.000Z", target=a2["key"])
a3 = L("page-0701a005", "answer", "page", "2026-11-23T09:59:44.000Z", id="q2", revision=1, picks=["No"],
       text="after the freeze")
tail = [a1, r1, a2, r2, a3]
before = {"state.json": record(S, 3, 3, 0, [q1, q2]), "inbox.jsonl": inbox(tail)}
out = answer_out(a3, q2, NOW)
vs = {a1["key"]: V("retracted", "answer", NOW, id="q1"), r1["key"]: V("retracted", "retract", NOW, target=a1["key"]),
      a2["key"]: V("retracted", "answer", NOW, id="q2"), r2["key"]: V("retracted", "retract", NOW, target=a2["key"]),
      a3["key"]: V("applied", "answer", NOW, id="q2")}
cl = {"q2": closed_answered(q2, a3, NOW)}
after = {"state.json": record(S, 4, 3, offset(*tail), [q1], [out], cl, vs, 4, [owed_answered(3, S, q2, a3)]),
         "inbox.jsonl": inbox(tail)}
case("retract-queued", "§4.2 row 5: a retract after its target (cancelled before the step), and an edit (a retract "
     "and a new answer)", 7, NOW, drain([x["key"] for x in tail]), vs, before, after,
     show(S, 3, [shown(q1), shown(q2, a3)],
          sent=[q_sent(a1, True), q_sent(r1), q_sent(a2, True), q_sent(r2), q_sent(a3)]),
     show(S, 4, [shown(q1)], sent=[v_sent(k, "accepted" if k == a3["key"] else "retracted", v) for k, v in vs.items()],
          pending=[out], closed=cl))

# 8 · retract-too-late
S, NOW = session(8), "2026-11-23T10:00:00.000Z"
q1, q2 = q_auth(1), question("q2", SHIP, "2026-11-23T09:30:00.000Z", "toolu_01Ship0008", YES_NO, "Migration",
                             revision=2)
T0 = "2026-11-23T09:40:00.000Z"
k1 = L("page-0801a001", "answer", "page", "2026-11-23T09:39:00.000Z", id="q1", revision=1, picks=["OAuth"])
k2 = L("page-0801a002", "answer", "page", "2026-11-23T09:39:10.000Z", id="q2", revision=1, picks=["Yes"])
r1 = L("page-0801r003", "retract", "page", "2026-11-23T09:59:40.000Z", target=k1["key"])
r2 = L("page-0801r004", "retract", "page", "2026-11-23T09:59:41.000Z", target=k2["key"])
dl = L("maws-0801d005", "delivered", "maws", "2026-11-23T09:59:42.000Z", keys=[k1["key"]])
r3 = L("page-0801r006", "retract", "page", "2026-11-23T09:59:43.000Z", target=dl["key"])
r4 = L("page-0801r007", "retract", "page", "2026-11-23T09:59:44.000Z", target=r1["key"])
tail = [r1, r2, dl, r3, r4]
out1 = answer_out(k1, q1, T0)
vk1, vk2 = V("applied", "answer", T0, id="q1"), V("stale", "answer", T0, id="q2", current=2)
cl0 = {"q1": closed_answered(q1, k1, T0)}
before = {"state.json": record(S, 9, 3, offset(k1, k2), [q2], [out1], cl0, {k1["key"]: vk1, k2["key"]: vk2}, 4),
          "inbox.jsonl": inbox([k1, k2] + tail)}
vs = {r1["key"]: V("too-late", "retract", NOW, target=k1["key"]),
      r2["key"]: V("too-late", "retract", NOW, target=k2["key"]),
      dl["key"]: V("applied", "delivered", NOW),
      r3["key"]: V("too-late", "retract", NOW, target=dl["key"]),
      r4["key"]: V("too-late", "retract", NOW, target=r1["key"])}
cl1 = {"q1": dict(closed_answered(q1, k1, T0), deliveredAt=NOW)}
after = {"state.json": record(S, 10, 3, offset(k1, k2, *tail), [q2], [], cl1,
                              {k1["key"]: vk1, k2["key"]: vk2, **vs}, 4),
         "inbox.jsonl": inbox([k1, k2] + tail)}
case("retract-too-late", "§4.2 row 6: a retract of a target an earlier step applied, and of one it refused as "
     "stale; a retract that names a retract, and one that names a delivered line, both too-late", 8, NOW,
     drain([x["key"] for x in tail]), vs, before, after,
     show(S, 9, [shown(q2)], sent=[v_sent(k1["key"], "accepted", vk1), v_sent(k2["key"], "stale", vk2)]
          + [q_sent(x) for x in tail], pending=[out1], closed=cl0),
     show(S, 10, [shown(q2)], sent=[v_sent(k1["key"], "delivered", vk1), v_sent(k2["key"], "stale", vk2)]
          + [v_sent(k, "delivered" if k == dl["key"] else "too-late", v) for k, v in vs.items()], closed=cl1))

# 9 · retract-unseen
S, NOW = session(9), "2026-11-23T10:00:00.000Z"
q1 = q_auth(1)
KX = "page-0901a0ff"
r = L("page-0901r001", "retract", "page", "2026-11-23T09:59:40.000Z", target=KX)
before = {"state.json": record(S, 2, 2, 0, [q1]), "inbox.jsonl": inbox([r])}
vs = {KX: V("retracted", "unseen", NOW, by=r["key"]), r["key"]: V("retracted", "retract", NOW, target=KX)}
after = {"state.json": record(S, 3, 2, offset(r), [q1], verdicts=vs), "inbox.jsonl": inbox([r])}
case("retract-unseen", "U1: a retract whose target no line carried cancels it in advance: the target's own "
     "verdict, kind unseen, and its entry in sent", 9, NOW, drain([r["key"], KX]), vs, before, after,
     show(S, 2, [shown(q1)], sent=[q_sent(r)]),
     show(S, 3, [shown(q1)], sent=[v_sent(k, "retracted", v) for k, v in vs.items()]))

# 10 · retract-unseen-late
S, NOW = session(10), "2026-11-23T10:05:00.000Z"
T0 = "2026-11-23T10:00:00.000Z"
q1 = q_auth(1)
KX = "page-1001a0ff"
r = L("page-1001r001", "retract", "page", "2026-11-23T09:59:40.000Z", target=KX)
x = L(KX, "answer", "page", "2026-11-23T09:59:30.000Z", id="q1", revision=1, picks=["OAuth"])
r2 = L("page-1001r002", "retract", "page", "2026-11-23T10:04:00.000Z", target=KX)
v0 = {KX: V("retracted", "unseen", T0, by=r["key"]), r["key"]: V("retracted", "retract", T0, target=KX)}
before = {"state.json": record(S, 3, 2, offset(r), [q1], verdicts=v0), "inbox.jsonl": inbox([r, x, r2])}
vr2 = V("too-late", "retract", NOW, target=KX)
after = {"state.json": record(S, 4, 2, offset(r, x, r2), [q1], verdicts={**v0, r2["key"]: vr2}),
         "inbox.jsonl": inbox([r, x, r2])}
case("retract-unseen-late", "U1, from the state retract-unseen leaves: the target's line arrives and is set aside, "
     "its verdict unchanged and its question still open; a second retract of it reads too-late", 10, NOW,
     drain([KX, r2["key"]]), {KX: v0[KX], r2["key"]: vr2}, before, after,
     show(S, 3, [shown(q1)], sent=[v_sent(k, "retracted", v) for k, v in v0.items()] + [q_sent(r2)]),
     show(S, 4, [shown(q1)], sent=[v_sent(k, "retracted", v) for k, v in v0.items()]
          + [v_sent(r2["key"], "too-late", vr2)]))

# 11 · delivered-mixed
S, NOW = session(11), "2026-11-23T10:00:00.000Z"
q1, q2, q3 = q_auth(1), q_ship(2), q_empty(3)
T1, T2 = "2026-11-23T09:30:00.000Z", "2026-11-23T09:35:00.000Z"
k1 = L("page-1101a001", "answer", "page", "2026-11-23T09:29:00.000Z", id="q1", revision=1, picks=["OAuth"])
k2 = L("page-1101a002", "answer", "page", "2026-11-23T09:29:30.000Z", id="q2", revision=1, picks=["Yes"])
dl = L("maws-1101d003", "delivered", "maws", "2026-11-23T09:59:50.000Z",
       keys=[k1["key"], k2["key"], "page-1101beef"])
out1 = answer_out(k1, q1, T1)
v0 = {k1["key"]: V("applied", "answer", T1, id="q1"), k2["key"]: V("applied", "answer", T1, id="q2")}
cl0 = {"q1": closed_answered(q1, k1, T1), "q2": dict(closed_answered(q2, k2, T1), deliveredAt=T2)}
before = {"state.json": record(S, 8, 4, offset(k1, k2), [q3], [out1], cl0, v0, 6),
          "inbox.jsonl": inbox([k1, k2, dl])}
vdl = V("applied", "delivered", NOW)
cl1 = {"q1": dict(cl0["q1"], deliveredAt=NOW), "q2": cl0["q2"]}
after = {"state.json": record(S, 9, 4, offset(k1, k2, dl), [q3], [], cl1, {**v0, dl["key"]: vdl}, 6),
         "inbox.jsonl": inbox([k1, k2, dl])}
case("delivered-mixed", "§4.2 row 7: a delivered line naming one key pending, one delivered before and one unknown; "
     "after it show's closed holds the delivered answer's receipt and pending holds it no longer", 11, NOW,
     drain([dl["key"]]), {dl["key"]: vdl}, before, after,
     show(S, 8, [shown(q3)], sent=[v_sent(k1["key"], "accepted", v0[k1["key"]]),
                                   v_sent(k2["key"], "delivered", v0[k2["key"]]), q_sent(dl)],
          pending=[out1], closed=cl0),
     show(S, 9, [shown(q3)], sent=[v_sent(k, "delivered", v) for k, v in {**v0, dl["key"]: vdl}.items()],
          closed=cl1))

# 12 · resent-key
S, NOW = session(12), "2026-11-23T10:00:00.000Z"
q1, q2 = q_auth(1), q_ship(2)
T1 = "2026-11-23T09:30:00.000Z"
k = L("page-1201a001", "answer", "page", "2026-11-23T09:29:00.000Z", id="q1", revision=1, picks=["Passkeys"])
out = answer_out(k, q1, T1)
vk = V("applied", "answer", T1, id="q1")
cl = {"q1": closed_answered(q1, k, T1)}
before = {"state.json": record(S, 5, 3, offset(k), [q2], [out], cl, {k["key"]: vk}, 4), "inbox.jsonl": inbox([k, k])}
after = {"state.json": record(S, 6, 3, offset(k, k), [q2], [out], cl, {k["key"]: vk}, 4), "inbox.jsonl": inbox([k, k])}
case("resent-key", "§4.2 row 8: a resent copy of an applied line is set aside: the first verdict again", 12, NOW,
     drain([k["key"]]), {k["key"]: vk}, before, after,
     show(S, 5, [shown(q2)], sent=[v_sent(k["key"], "accepted", vk)], pending=[out], closed=cl),
     show(S, 6, [shown(q2)], sent=[v_sent(k["key"], "accepted", vk)], pending=[out], closed=cl))

# 13 · resent-then-retract
S, NOW = session(13), "2026-11-23T10:00:00.000Z"
q1, q2 = q_auth(1), q_ship(2)
T1 = "2026-11-23T09:30:00.000Z"
k = L("page-1301a001", "answer", "page", "2026-11-23T09:29:00.000Z", id="q1", revision=1, picks=["OAuth"])
r = L("page-1301r002", "retract", "page", "2026-11-23T09:59:50.000Z", target=k["key"])
out = answer_out(k, q1, T1)
vk = V("applied", "answer", T1, id="q1")
cl = {"q1": closed_answered(q1, k, T1)}
before = {"state.json": record(S, 5, 3, offset(k), [q2], [out], cl, {k["key"]: vk}, 4),
          "inbox.jsonl": inbox([k, k, r])}
vr = V("too-late", "retract", NOW, target=k["key"])
after = {"state.json": record(S, 6, 3, offset(k, k, r), [q2], [out], cl, {k["key"]: vk, r["key"]: vr}, 4),
         "inbox.jsonl": inbox([k, k, r])}
case("resent-then-retract", "a resent copy of an applied line, then a retract of it: the copy set aside, the retract "
     "too-late, the answer still pending", 13, NOW, drain([k["key"], r["key"]]), {k["key"]: vk, r["key"]: vr},
     before, after,
     show(S, 5, [shown(q2)], sent=[v_sent(k["key"], "accepted", vk), q_sent(r)], pending=[out], closed=cl),
     show(S, 6, [shown(q2)], sent=[v_sent(k["key"], "accepted", vk), v_sent(r["key"], "too-late", vr)],
          pending=[out], closed=cl))

# 14 · batch
S, NOW = session(14), "2026-11-23T10:00:00.000Z"
REVIEWER = {"agentId": "a1b2c3", "name": "reviewer"}
q1, q2, q3 = q_auth(1), q_ship(2, asker=REVIEWER), q_empty(3)
B = "page-b1400001"
a1 = L("page-1401a001", "answer", "page", "2026-11-23T09:59:50.000Z", id="q1", revision=1, picks=["OAuth"], batch=B)
a2 = L("page-1401a002", "answer", "page", "2026-11-23T09:59:50.000Z", id="q2", revision=1, picks=["No"],
       text="wait for the backup", batch=B)
d3 = L("page-1401d003", "dismiss", "page", "2026-11-23T09:59:50.000Z", id="q3", batch=B)
tail = [a1, a2, d3]
before = {"state.json": record(S, 4, 4, 0, [q1, q2, q3]), "inbox.jsonl": inbox(tail)}
outs = [answer_out(a1, q1, NOW), answer_out(a2, q2, NOW, recipient={"agentId": "a1b2c3"}, taken=True),
        dismiss_out(d3, q3, NOW)]
vs = {a1["key"]: V("applied", "answer", NOW, id="q1"), a2["key"]: V("applied", "answer", NOW, id="q2"),
      d3["key"]: V("applied", "dismiss", NOW, id="q3")}
cl = {"q1": closed_answered(q1, a1, NOW), "q2": closed_answered(q2, a2, NOW),
      "q3": closed_other(q3, "dismissed", NOW, d3["key"])}
after = {"state.json": record(S, 5, 4, offset(*tail), [], outs, cl, vs, 7,
                              [owed_answered(4, S, q1, a1), owed_answered(5, S, q2, a2),
                               owed_closed(6, S, q3, "dismissed")]),
         "inbox.jsonl": inbox(tail)}
case("batch", "one Send of three lines (two answers and a dismissal) applied whole: the main conversation's outcomes "
     "and a running subagent's, taken", 14, NOW, drain([x["key"] for x in tail], running=["a1b2c3"]), vs,
     before, after,
     show(S, 4, [shown(q1, a1), shown(q2, a2)], [{"id": "q3", "key": d3["key"]}], [q_sent(x) for x in tail]),
     show(S, 5, [], sent=[v_sent(k, "accepted", v) for k, v in vs.items()], pending=outs, closed=cl))

# 15 · long-text
S, NOW = session(15), "2026-11-23T10:00:00.000Z"
q1 = question("q1", "What does the onboarding email need to say?", "2026-11-23T09:01:00.000Z", "toolu_01Mail0015",
              header="Onboarding")
PARA = ("The first message is the one people read. Say what the account is for, what happens next, and who to ask; "
        "keep the café example, it is what support sees most. ")
LONG = (PARA * 200)[:18214]
LONG_FILE = "texts/%s.txt" % sha(LONG)
a = L("page-1501a001", "answer", "page", "2026-11-23T09:59:00.000Z", id="q1", revision=1, text=LONG)
before = {"state.json": record(S, 2, 2, 0, [q1]), "inbox.jsonl": inbox([a])}
out = answer_out(a, q1, NOW, text_file=LONG_FILE)
va = V("applied", "answer", NOW, id="q1")
cl = {"q1": closed_answered(q1, a, NOW)}
after = {"state.json": record(S, 3, 2, offset(a), [], [out], cl, {a["key"]: va}, 3, [owed_answered(2, S, q1, a)]),
         "inbox.jsonl": inbox([a]), LONG_FILE: LONG}
case("long-text", "an answer of 18,214 characters: its outcome's textFile and the file under texts/, named by the "
     "hash of its UTF-8 bytes", 15, NOW, drain([a["key"]]), {a["key"]: va}, before, after,
     show(S, 2, [shown(q1, a)], sent=[q_sent(a)]),
     show(S, 3, [], sent=[v_sent(a["key"], "accepted", va)], pending=[out], closed=cl))

# 16 · stopped-queue
S, NOW = session(16), "2026-11-23T11:00:00.000Z"
T1 = "2026-11-23T09:30:00.000Z"
q1, q2, q3 = q_auth(1), q_ship(2), q_empty(3)
q4 = question("q4", CACHE, "2026-11-23T09:10:00.000Z", "toolu_01Cach0016", [opt("Yes"), opt("No")], "Cache key",
              asker=REVIEWER)
k4 = L("page-1601a000", "answer", "page", "2026-11-23T09:29:00.000Z", id="q4", revision=1, picks=["Yes"])
out4 = answer_out(k4, q4, T1, recipient={"agentId": "a1b2c3"}, taken=True)
v4 = V("applied", "answer", T1, id="q4")
a1 = L("page-1601a001", "answer", "page", "2026-11-23T10:20:00.000Z", id="q1", revision=1, picks=["OAuth"])
d2 = L("page-1601d002", "dismiss", "page", "2026-11-23T10:21:00.000Z", id="q2")
a3 = L("page-1601a003", "answer", "page", "2026-11-23T10:22:00.000Z", id="q3", revision=1,
       text="Nothing waiting for you.")
r3 = L("page-1601r004", "retract", "page", "2026-11-23T10:23:00.000Z", target=a3["key"])
tail = [a1, d2, a3, r3]
cl0 = {"q4": closed_answered(q4, k4, T1)}
before = {"state.json": record(S, 7, 5, offset(k4), [q1, q2, q3], [out4], cl0, {k4["key"]: v4}, 6,
                               calls=[{"callId": "toolu_01Empt0016", "result": "Added q3."}]),
          "inbox.jsonl": inbox([k4] + tail)}
outs = [dict(out4, recipient="main", taken=False, acrossStop=True), answer_out(a1, q1, NOW, across=True),
        dismiss_out(d2, q2, NOW, across=True)]
vs = {a1["key"]: V("applied", "answer", NOW, id="q1"), d2["key"]: V("applied", "dismiss", NOW, id="q2"),
      a3["key"]: V("retracted", "answer", NOW, id="q3"), r3["key"]: V("retracted", "retract", NOW, target=a3["key"])}
cl1 = {**cl0, "q1": closed_answered(q1, a1, NOW), "q2": closed_other(q2, "dismissed", NOW, d2["key"])}
after = {"state.json": record(S, 8, 5, offset(k4, *tail), [q3], outs, cl1, {k4["key"]: v4, **vs}, 8,
                              [owed_answered(6, S, q1, a1), owed_closed(7, S, q2, "dismissed")]),
         "inbox.jsonl": inbox([k4] + tail)}
case("stopped-queue", "event start: what was queued while the session was stopped (an answer, a dismissal whose "
     "question is hidden, an answer retracted) is applied, every pending outcome owed across a stop and given to the "
     "main conversation, the unacknowledged calls forgotten", 16, NOW, start("resume"), vs, before, after,
     show(S, 7, [shown(q1, a1), shown(q3)], [{"id": "q2", "key": d2["key"]}],
          [v_sent(k4["key"], "accepted", v4), q_sent(a1), q_sent(d2), q_sent(a3, True), q_sent(r3)],
          [out4], cl0),
     show(S, 8, [shown(q3)], sent=[v_sent(k4["key"], "accepted", v4)]
          + [v_sent(k, "accepted" if v["verdict"] == "applied" else "retracted", v) for k, v in vs.items()],
          pending=outs, closed=cl1))

# 17 · imported-legacy
S, NOW = session(17), "2026-11-23T10:00:00.000Z"
LEGACY_Q = (("Which of the rollout plans in the design note should we follow, given everything listed below? " * 30)
            [:2001])
LEGACY_LABEL = ("Roll out to the internal org first, then to the beta cohort, then to everyone, each step gated on "
                "the error budget and on the support queue staying under its usual size for a whole week, no less, "
                "and no sooner")[:201]
assert len(LEGACY_Q) == 2001 and len(LEGACY_LABEL) == 201
ASK_CALL = "toolu_01Legacy00017"
ASK_AT = "2026-11-22T18:00:00.000Z"
legacy = [{"question": LEGACY_Q, "header": "Rollout",
           "options": [opt("As written", "The note's plan, step by step."), opt("Faster", "Skip the beta cohort.")],
           "multiSelect": False},
          {"question": "Which rollout gate?", "header": "Gate",
           "options": [opt(LEGACY_LABEL, "Every gate the note lists."), opt("No gate", "Ship to everyone at once.")],
           "multiSelect": False},
          {"question": "Which screens get the new layout?", "header": "Screens",
           "options": [opt("Home", "The landing screen.", preview="## Home\n\nThe new grid."),
                       opt("Settings", "The account screens.")], "multiSelect": True}]
ask = {"callId": ASK_CALL, "askedAt": ASK_AT, "questions": legacy}
imp = [question("q%d" % (i + 1), x["question"], ASK_AT, ASK_CALL, x["options"], x["header"], multi=x["multiSelect"],
                imported={"callId": ASK_CALL, "index": i}) for i, x in enumerate(legacy)]
after = {"state.json": record(S, 1, 4, 0, imp, log_next=4, owed=[owed_question(i + 1, S, x) for i, x in enumerate(imp)],
                              projects={}, imports={ASK_CALL: ["q1", "q2", "q3"]}),
         "inbox.jsonl": b""}
case("imported-legacy", "event start carrying an ask only today's tool accepts (a 2,001-character question, a "
     "201-character label, a preview on a multi-select question): the three kept as questions, unchanged, marked "
     "importedFrom", 17, NOW, start("resume", [ask]), {}, None, after, None,
     show(S, 1, [shown(x) for x in imp]))

# 18 · skipped-and-unknown
S, NOW = session(18), "2026-11-23T10:00:00.000Z"
q1 = q_ship(1)
bad = ["not json at all\n",
       jline({"v": 1, "kind": "dismiss", "id": "q1", "by": "page", "at": "2026-11-23T09:59:00.000Z"}) + "\n",
       jline(L("page-1801a003", "answer", "page", "2026-11-23T09:59:01.000Z", id="q1")) + "\n",
       jline(L("page-1801a004", "answer", "page", "2026-11-23T09:59:02.000Z", id="q1", revision=1,
               picks=["Maybe"])) + "\n",
       jline(L("page-1801a007", "answer", "page", "2026-11-23T09:59:02.500Z", id="q1", revision=1,
               text="half an emoji: \ud83d")).replace("\ud83d", "\\ud83d") + "\n",
       jline(L("page-1801a008", "answer", "page", "2026-11-23T09:59:02.700Z", id="q1", revision=1,
               picks=["Yes", "No"])) + "\n"]
u1 = L("page-1801a005", "answer", "page", "2026-11-23T09:59:03.000Z", id="q99", revision=1, text="whenever")
u2 = L("page-1801d006", "dismiss", "page", "2026-11-23T09:59:04.000Z", id="q42")
tail = bad + [u1, u2]
before = {"state.json": record(S, 2, 2, 0, [q1]), "inbox.jsonl": inbox(tail)}
vs = {u1["key"]: V("closed", "answer", NOW, id="q99", how="unknown"),
      u2["key"]: V("closed", "dismiss", NOW, id="q42", how="unknown")}
after = {"state.json": record(S, 3, 2, offset(*tail), [q1], verdicts=vs, skipped=6), "inbox.jsonl": inbox(tail)}
case("skipped-and-unknown", "U2: a line that is not JSON, one with no key, one that fails the line's schema, one "
     "that picks no label of its question, one whose text holds a lone UTF-16 surrogate and one with two picks on a "
     "single-select question are skipped with no verdict, inbox.skipped raised by six; U3: an answer "
     "and a dismissal naming ids the record never assigned read closed, how unknown", 18, NOW,
     drain([u1["key"], u2["key"]]), vs, before, after,
     show(S, 2, [shown(q1)], sent=[q_sent(u1), q_sent(u2)]),
     show(S, 3, [shown(q1)], sent=[v_sent(k, "closed", v) for k, v in vs.items()]))

# 19 · references
S, NOW = session(19), "2026-11-23T10:00:00.000Z"
AUTH_TS = "".join("export const line%d = %d;\n" % (n, n) for n in range(40, 81))
README = "# proj\n\nThe login service.\n"
refs = [{"path": "src/auth.ts", "lines": [40, 80], "abs": "/Users/me/work/proj/src/auth.ts", "sha256": sha(AUTH_TS),
         "bytes": len(AUTH_TS.encode()), "kind": "text", "startLine": 40, "numLines": 41, "totalLines": 212,
         "size": 6120, "mtimeMs": 1763888400000},
        {"path": "README.md", "abs": "/Users/me/work/proj/README.md", "sha256": sha(README),
         "bytes": len(README.encode()), "kind": "text", "startLine": 1, "numLines": 3, "totalLines": 3,
         "size": len(README.encode()), "mtimeMs": 1763888000000},
        {"path": "docs/login.png", "abs": "/Users/me/work/proj/docs/login.png", "sha256": sha(PNG), "bytes": len(PNG),
         "kind": "image", "mediaType": "image/png", "size": len(PNG), "mtimeMs": 1763887000000}]
q1 = question("q1", "Is the session check in these lines the one to keep?", "2026-11-23T09:01:00.000Z",
              "toolu_01Refs0019", YES_NO, "Session check", context="The two checks disagree on expiry.", refs=refs)
q2 = q_ship(2)
a = L("cli-1901a001", "answer", "cli", "2026-11-23T09:59:00.000Z", id="q2", revision=1, picks=["Yes"])
bodies = {"refs/" + sha(AUTH_TS): AUTH_TS, "refs/" + sha(README): README, "refs/" + sha(PNG): PNG}
before = {"state.json": record(S, 2, 3, 0, [q1, q2]), "inbox.jsonl": inbox([a]), **bodies}
out = answer_out(a, q2, NOW)
va = V("applied", "answer", NOW, id="q2")
cl = {"q2": closed_answered(q2, a, NOW)}
after = {"state.json": record(S, 3, 3, offset(a), [q1], [out], cl, {a["key"]: va}, 4, [owed_answered(3, S, q2, a)]),
         "inbox.jsonl": inbox([a]), **bodies}
case("references", "a text reference with lines, one without, an image: their bodies under refs/, named by their "
     "hash; a reader marks each changed where the file at abs is missing", 19, NOW, drain([a["key"]]),
     {a["key"]: va}, before, after,
     show(S, 2, [shown(q1), shown(q2, a)], sent=[q_sent(a)]),
     show(S, 3, [shown(q1)], sent=[v_sent(a["key"], "accepted", va)], pending=[out], closed=cl))

# 20 · torn-tail
S, NOW = session(20), "2026-11-23T10:00:00.000Z"
q1 = q_ship(1)
a = L("page-2001a001", "answer", "page", "2026-11-23T09:59:00.000Z", id="q1", revision=1, picks=["Yes"])
torn = jline(a)                       # a whole object, its newline never written
before = {"state.json": record(S, 2, 2, 0, [q1]), "inbox.jsonl": torn}
case("torn-tail", "an inbox that ends in bytes without a newline (a whole answer that lacks only it): no reader "
     "lists it, the drain applies nothing, the offset stays at the last newline and nothing is replaced", 20, NOW,
     drain([a["key"]]), {}, before, before,
     show(S, 2, [shown(q1)]), show(S, 2, [shown(q1)]))

# 21 · torn-tail-resent
S, NOW = session(21), "2026-11-23T10:00:00.000Z"
q1 = q_ship(1)
a = L("page-2101a001", "answer", "page", "2026-11-23T09:59:00.000Z", id="q1", revision=1, picks=["Yes"])
again = dict(a, at="2026-11-23T09:59:30.000Z")    # the resend, under the same key, stamped when it was sent
data = jline(a) + "\n" + jline(again) + "\n"  # the resend's door ended the fragment with a newline, then appended
before = {"state.json": record(S, 2, 2, 0, [q1]), "inbox.jsonl": data}
out = answer_out(a, q1, NOW)
va = V("applied", "answer", NOW, id="q1")
cl = {"q1": closed_answered(q1, a, NOW)}
after = {"state.json": record(S, 3, 2, len(data.encode()), [], [out], cl, {a["key"]: va}, 3,
                              [owed_answered(2, S, q1, a)]),
         "inbox.jsonl": data}
case("torn-tail-resent", "torn-tail after the surface sent again: a newline, then the answer under the same key; the "
     "first copy is applied, the second set aside, one verdict", 21, NOW, drain([a["key"]]), {a["key"]: va},
     before, after,
     show(S, 2, [shown(q1, a)], sent=[q_sent(a)]),
     show(S, 3, [], sent=[v_sent(a["key"], "accepted", va)], pending=[out], closed=cl))


# ------------------------------------------------------------------ the envelopes (I7), each with its record

EXAMPLES = []


def example(name, n, recipient, rec, extra, envelope, more=None):
    sess = "5eed0000-0000-4000-8000-0000000000e%d" % n
    EXAMPLES.append(name)
    base = "examples/%s/" % name
    put(base + "case.json", dump({"recipient": recipient, "runner": "terminal", "tz": "UTC"}))
    put("%sinput/sheet/%s/state.json" % (base, sess), dump(rec))
    for path, data in sorted(extra.items()):
        put("%sinput/sheet/%s/%s" % (base, sess, path), data)
    put(base + "envelope.txt", envelope)
    for path, data in (more or {}).items():
        put(base + path, data)


# terminal: the plan's own example, and its steer
S = "5eed0000-0000-4000-8000-0000000000e1"
UP = "%s/sheet/%s/uploads/sketch.png" % (HOME, S)
q7 = question("q7", AUTH, "2026-11-23T15:10:00.000Z", "toolu_01Auth00e1", AUTH_OPTS, "Auth method", revision=2,
              multi=True)
q8 = question("q8", EMPTY_Q, "2026-11-23T14:02:11.000Z", "toolu_01Empt00e1", (), "Empty state")
q9 = question("q9", "Keep the legacy export button?", "2026-11-23T14:05:00.000Z", "toolu_01Expo00e1", YES_NO,
              "Export")
q10 = question("q10", "Which log level in production?", "2026-11-23T14:06:00.000Z", "toolu_01Logs00e1",
               [opt("info", recommended=True), opt("debug")], "Log level")
q11 = question("q11", "Rename the settings page?", "2026-11-23T14:07:00.000Z", "toolu_01Name00e1", YES_NO, "Naming")
q12 = question("q12", SHIP, "2026-11-23T15:30:00.000Z", "toolu_01Ship00e1", YES_NO, "Migration", asker=REVIEWER)
l8 = L("page-7f3a91c3", "answer", "page", "2026-11-23T16:40:05.000Z", id="q8", revision=1,
       text="Nothing waiting for you.")
BT = "page-b7f3a91c"
l7 = L("page-7f3a91c2", "answer", "page", "2026-11-23T17:09:58.000Z", id="q7", revision=2,
       picks=["OAuth", "Passkeys"], text="passkeys only on mobile", images=["uploads/sketch.png"], batch=BT)
l9 = L("page-7f3a91c4", "dismiss", "page", "2026-11-23T17:09:58.000Z", id="q9", batch=BT)
l12 = L("cli-20c41d07", "answer", "cli", "2026-11-23T17:12:00.000Z", id="q12", revision=1, picks=["Yes"])
l11 = L("page-7f3a91c5", "dismiss", "page", "2026-11-23T17:15:00.000Z", id="q11")
A8, A7, A12, A11 = ("2026-11-23T17:02:00.000Z", "2026-11-23T17:10:00.000Z", "2026-11-23T17:12:01.000Z",
                    "2026-11-23T17:15:01.000Z")
pend = [answer_out(l8, q8, A8, across=True), answer_out(l7, q7, A7), dismiss_out(l9, q9, A7),
        answer_out(l12, q12, A12), dismiss_out(l11, q11, A11)]
rec = record(S, 23, 13, 0, [q10], pend,
             {"q7": closed_answered(q7, l7, A7), "q8": closed_answered(q8, l8, A8),
              "q9": closed_other(q9, "dismissed", A7, l9["key"]), "q11": closed_other(q11, "dismissed", A11, l11["key"]),
              "q12": closed_answered(q12, l12, A12)},
             {l8["key"]: V("applied", "answer", A8, id="q8"), l7["key"]: V("applied", "answer", A7, id="q7"),
              l9["key"]: V("applied", "dismiss", A7, id="q9"), l12["key"]: V("applied", "answer", A12, id="q12"),
              l11["key"]: V("applied", "dismiss", A11, id="q11")}, 18)
KEYS = ["page-7f3a91c2", "page-7f3a91c3", "cli-20c41d07", "page-7f3a91c4", "page-7f3a91c5"]
BLK = block({"v": 1, "keys": KEYS, "answered": [
    {"id": "q7", "revision": 2, "picks": [1, 2], "text": "passkeys only on mobile", "images": [UP]},
    {"id": "q8", "revision": 1, "picks": [], "text": "Nothing waiting for you.", "images": []},
    {"id": "q12", "revision": 1, "picks": [1], "text": "", "images": []}], "dismissed": ["q9", "q11"]})
example("terminal", 1, "main", rec, {"uploads/sketch.png": PNG}, "\n".join([
    "[sheet v1] The human answered questions on your sheet.",
    'q7 "Which auth method should the login use?" → OAuth, Passkeys. Their text: "passkeys only on mobile"',
    "[Image source: %s]" % UP,
    'q8 (asked 2026-11-23 14:02, answered 2026-11-23 16:40, while this session was stopped) "What should the empty '
    'state say?" → their text: "Nothing waiting for you."',
    'q12 (from the subagent reviewer, a1b2c3, which has ended) "Ship the migration today?" → Yes.',
    "Dismissed: q9, q11.",
    BLK]), {"steer.txt": "\n".join([
        "[sheet v1] The human answered questions on your sheet.",
        'q7 → option 1, option 2. Their text: "passkeys only on mobile"',
        'q8 → their text: "Nothing waiting for you."',
        "q12 (asked by the subagent a1b2c3, which has ended) → option 1.",
        "Dismissed: q9, q11.",
        BLK])})

# long: one Send of four answers of 20,000 characters
S = "5eed0000-0000-4000-8000-0000000000e2"
WORDS = ["alpha", "bravo", "charlie", "delta"]
LONGS = [(("Answer %d, about %s: the whole of it matters, every part of this text. " % (i + 1, w)) * 400)[:20000]
         for i, w in enumerate(WORDS)]
qs = [question("q%d" % (i + 1), "What should section %d of the guide cover?" % (i + 1), "2026-11-23T09:0%d:00.000Z" % i,
               "toolu_01Guid%04d" % i, header="Guide %d" % (i + 1)) for i in range(4)]
BL = "page-b2000001"
ls = [L("page-e2a0000%d" % (i + 1), "answer", "page", "2026-11-23T10:00:00.000Z", id="q%d" % (i + 1), revision=1,
        text=LONGS[i], batch=BL) for i in range(4)]
AC = "2026-11-23T10:00:01.000Z"
TF = ["texts/%s.txt" % sha(t) for t in LONGS]
rec = record(S, 5, 5, 0, [], [answer_out(ls[i], qs[i], AC, text_file=TF[i]) for i in range(4)],
             {"q%d" % (i + 1): closed_answered(qs[i], ls[i], AC) for i in range(4)},
             {ls[i]["key"]: V("applied", "answer", AC, id="q%d" % (i + 1)) for i in range(4)}, 9)
ABS = ["%s/sheet/%s/%s" % (HOME, S, f) for f in TF]
example("long", 2, "main", rec, {TF[i]: LONGS[i] for i in range(4)}, "\n".join([
    "[sheet v1] The human answered questions on your sheet.",
    'q1 "What should section 1 of the guide cover?" → their text, 20,000 characters, is in %s and begins: %s'
    % (ABS[0], jstr(LONGS[0][:500] + "…")),
    'q2 "What should section 2 of the guide cover?" → their text, 20,000 characters, is in %s and begins: %s'
    % (ABS[1], jstr(LONGS[1][:500] + "…")),
    'q3 "What should section 3 of the guide cover?" → their text: %s' % jstr(LONGS[2]),
    'q4 "What should section 4 of the guide cover?" → their text: %s' % jstr(LONGS[3]),
    block({"v": 1, "keys": [x["key"] for x in ls], "answered": [
        {"id": "q%d" % (i + 1), "revision": 1, "picks": [], "text": LONGS[i][:500], "textCut": True,
         "textFile": ABS[i], "images": []} for i in range(4)], "dismissed": []})]))

# more: five Sends of fifty dismissals
S = "5eed0000-0000-4000-8000-0000000000e3"
qs = [question("q%d" % n, "Keep test fixture %d?" % n, "2026-11-23T09:00:00.000Z", "toolu_01Fixt%04d" % ((n - 1) // 20),
               YES_NO) for n in range(1, 251)]
ds = [L("page-e3d%04d" % n, "dismiss", "page", "2026-11-23T10:0%d:00.000Z" % ((n - 1) // 50), id="q%d" % n,
        batch="page-b300000%d" % ((n - 1) // 50 + 1)) for n in range(1, 251)]
ACS = ["2026-11-23T10:0%d:01.000Z" % s for s in range(5)]
rec = record(S, 6, 251, 0, [], [dismiss_out(ds[n], qs[n], ACS[n // 50]) for n in range(250)],
             {"q%d" % (n + 1): closed_other(qs[n], "dismissed", ACS[n // 50], ds[n]["key"]) for n in range(250)},
             {ds[n]["key"]: V("applied", "dismiss", ACS[n // 50], id="q%d" % (n + 1)) for n in range(250)}, 501)
example("more", 3, "main", rec, {}, "\n".join([
    "[sheet v1] The human dismissed questions on your sheet; no answer will come for them. More follows.",
    "Dismissed: %s." % ", ".join("q%d" % n for n in range(1, 201)),
    block({"v": 1, "keys": [d["key"] for d in ds[:200]], "answered": [],
           "dismissed": ["q%d" % n for n in range(1, 201)], "more": True})]))

# imported: a pick of an imported question's 201-character label
S = "5eed0000-0000-4000-8000-0000000000e4"
TWIN_LABEL = LEGACY_LABEL[:200] + ", and a second look"     # shares its first 200 characters with LEGACY_LABEL
qi = question("q1", "Which rollout gate?", ASK_AT, ASK_CALL,
              [opt("No gate", "Ship to everyone at once."), opt(LEGACY_LABEL, "Every gate the note lists."),
               opt(TWIN_LABEL, "Every gate, then a review.")], "Gate", imported={"callId": ASK_CALL, "index": 0})
li = L("page-e4a00001", "answer", "page", "2026-11-23T10:00:00.000Z", id="q1", revision=1, picks=[TWIN_LABEL])
AC = "2026-11-23T10:00:01.000Z"
rec = record(S, 3, 2, 0, [], [answer_out(li, qi, AC)], {"q1": closed_answered(qi, li, AC)},
             {li["key"]: V("applied", "answer", AC, id="q1")}, 3, imports={ASK_CALL: ["q1"]})
example("imported", 4, "main", rec, {}, "\n".join([
    "[sheet v1] The human answered questions on your sheet.",
    'q1 "Which rollout gate?" → %s….' % TWIN_LABEL[:200],
    block({"v": 1, "keys": [li["key"]], "answered": [{"id": "q1", "revision": 1, "picks": [3], "text": "",
                                                     "images": []}], "dismissed": []})]))

# subagent: one answer for a running subagent, taken; the main conversation's own outcome is not its
S = "5eed0000-0000-4000-8000-0000000000e5"
EXPLORER = {"agentId": "a7c0ffee", "name": "explorer"}
q3 = question("q3", CACHE, "2026-11-23T09:40:00.000Z", "toolu_01Cach00e5", [opt("Yes"), opt("No")], "Cache key",
              asker=EXPLORER)
q4 = q_ship(4)
l3 = L("page-e5a00003", "answer", "page", "2026-11-23T10:00:00.000Z", id="q3", revision=1, picks=["Yes"],
       text="and the region")
l4 = L("page-e5a00004", "answer", "page", "2026-11-23T10:00:30.000Z", id="q4", revision=1, picks=["No"])
A3, A4 = "2026-11-23T10:00:01.000Z", "2026-11-23T10:00:31.000Z"
rec = record(S, 6, 5, 0, [], [answer_out(l3, q3, A3, recipient={"agentId": "a7c0ffee"}, taken=True),
                              answer_out(l4, q4, A4)],
             {"q3": closed_answered(q3, l3, A3), "q4": closed_answered(q4, l4, A4)},
             {l3["key"]: V("applied", "answer", A3, id="q3"), l4["key"]: V("applied", "answer", A4, id="q4")}, 7)
example("subagent", 5, {"agentId": "a7c0ffee"}, rec, {}, "\n".join([
    "From the human, through the question tool, not from your coordinator: answers to questions you put on the sheet.",
    "[sheet v1] The human answered questions on your sheet.",
    'q3 "Should the cache key include the locale?" → Yes. Their text: "and the region"',
    block({"v": 1, "keys": [l3["key"]], "answered": [{"id": "q3", "revision": 1, "picks": [1],
                                                     "text": "and the region", "images": []}], "dismissed": []})]))

# split: one Send that no file can shrink leaves in two envelopes. Forty answers of exactly 2,000 characters each
# (a text has a file only past 2,000, so packing rule 2 carries nothing), one call of the door; rule 3 takes the
# batch's outcomes in order while they fit: twenty-two, then, once those landed, the other eighteen.
S = "5eed0000-0000-4000-8000-0000000000e6"
SPLIT_FIRST = 22
qs = [question("q%d" % n, "Which wording for message %d?" % n, "2026-11-23T09:00:00.000Z", "toolu_01Word0006")
      for n in range(1, 41)]
WORDING = [(("Wording %d: say it plainly, once, and stop. " % n) * 100)[:2000] for n in range(1, 41)]
assert all(len(t) == 2000 for t in WORDING)
ls = [L("page-e6a%04d" % n, "answer", "page", "2026-11-23T10:00:00.000Z", id="q%d" % n, revision=1,
        text=WORDING[n - 1], batch="page-b6000001") for n in range(1, 41)]
AC, LANDED = "2026-11-23T10:00:01.000Z", "2026-11-23T10:00:05.000Z"
outs = [answer_out(ls[i], qs[i], AC) for i in range(40)]
vs = {x["key"]: V("applied", "answer", AC, id=x["id"]) for x in ls}
cl = {"q%d" % (i + 1): closed_answered(qs[i], ls[i], AC) for i in range(40)}
for i in range(8):                    # the 32 answered last keep their answer's line (I2): one replace accepted all 40
    del cl["q%d" % (i + 1)]["answer"]
rec = record(S, 2, 41, 0, [], outs, cl, vs, 81)
landed = record(S, 3, 41, 0, [], outs[SPLIT_FIRST:],
                {k: dict(c, deliveredAt=LANDED) if int(k[1:]) <= SPLIT_FIRST else c for k, c in cl.items()}, vs, 81)


def split_line(i):
    return "q%d %s → their text: %s" % (i + 1, jstr(qs[i]["question"]), jstr(WORDING[i]))


def split_block(span, more):
    return block({"v": 1, "keys": [ls[i]["key"] for i in span], "answered": [
        {"id": "q%d" % (i + 1), "revision": 1, "picks": [], "text": WORDING[i][:500], "textCut": True, "images": []}
        for i in span], "dismissed": [], **({"more": True} if more else {})})


def split_first(n):
    return "\n".join(["[sheet v1] The human answered questions on your sheet. More follows."]
                     + [split_line(i) for i in range(n)] + [split_block(range(n), True)])


def u16(text):
    return len(text.encode("utf-16-le")) // 2


assert u16(split_first(SPLIT_FIRST)) <= 60000 < u16(split_first(SPLIT_FIRST + 1)), "twenty-two fit, twenty-three do not"
second = "\n".join(["[sheet v1] The human answered questions on your sheet."]
                   + [split_line(i) for i in range(SPLIT_FIRST, 40)] + [split_block(range(SPLIT_FIRST, 40), False)])
example("split", 6, "main", rec, {}, split_first(SPLIT_FIRST), {
    "then/case.json": dump({"recipient": "main", "runner": "terminal", "tz": "UTC"}),
    "then/input/sheet/%s/state.json" % S: dump(landed),
    "then/envelope.txt": second})

put("examples/surface.json", dump({"v": 1, "name": "mawsd", "pid": 4321, "url": "http://sheet.localhost:47590",
                                   "reach": "local", "heartbeatAt": "2026-11-23T10:00:00.000Z"}))


# ------------------------------------------------------------------ the result's grammar (I6, X7)

def call(input_, result, parsed):
    return {"input": input_, "result": result, "parsed": parsed}


def entry(q, **f):
    return {"question": q, **f}


NOSURFACE = "No surface can show these questions right now; they wait on the sheet and show when one returns."
RESULTS = [
    call({"ask": [entry("Which auth method should the login use?", header="Auth method",
                        options=[{"label": "OAuth", "recommended": True}, {"label": "Passkeys"}],
                        references=[{"path": "src/auth.ts", "lines": [40, 80]}])]
          + [entry("Question %d of the batch?" % n) for n in range(2, 9)]},
         "Added q1, q2, q3, q4, q5, q6, q7, q8.",
         {"form": "sentences", "added": [{"id": "q%d" % n} for n in range(1, 9)], "revised": [], "withdrew": []}),
    call({"ask": [entry("Which log level in production?"), entry("Ship the migration today?", id="q3"),
                  entry("Rename the settings page?")], "withdraw": ["q2"]},
         "Added q7, q8. Revised q3 (revision 2). Withdrew q2.\n" + NOSURFACE,
         {"form": "sentences", "added": [{"id": "q7"}, {"id": "q8"}], "revised": [{"id": "q3", "revision": 2}],
          "withdrew": ["q2"]}),
    call({"ask": [entry("Which log level in production?"), entry("Ship the migration today?", id="q3"),
                  entry("Is this check right?", references=[{"path": "src/x.ts"}]),
                  entry("Rename the settings page?")], "withdraw": ["q5"]},
         "Added q7 (entry 1), q8 (entry 4). Revised q3 (entry 2, revision 2).\n"
         "Not done: entry 3, the reference src/x.ts could not be read: permission denied. "
         "q5 is not open (answered at 14:05).",
         {"form": "sentences", "added": [{"id": "q7", "entry": 1}, {"id": "q8", "entry": 4}],
          "revised": [{"id": "q3", "entry": 2, "revision": 2}], "withdrew": []}),
    call({"ask": [entry("Keep the export?", options=[{"label": "Yes"}, {"label": "Yes"}]),
                  entry("Which log level in production?")]},
         'Added q4 (entry 2).\nNot done: entry 1, two options share the label "Yes".',
         {"form": "sentences", "added": [{"id": "q4", "entry": 2}], "revised": [], "withdrew": []}),
    call({"withdraw": ["q3"]},
         "Nothing done.\nNot done: q3 is not open (withdrawn at 09:12).",
         {"form": "nothing"}),
    call({"ask": [entry("Ship the migration today?")]},
         "Nothing done.\nNot done: the sheet could not be written (no step answered); call again.",
         {"form": "nothing"}),
    call({"ask": [entry("Ship the migration today?")]},
         "Outcome not known yet.\nThe sheet did not answer. Do not repeat this call: what it did will be told to you.",
         {"form": "unknown"}),
]
put("grammar/result.examples.json", dump(RESULTS))

ITEM = r"q[0-9]+(?: \(entry [0-9]+\))?"
RITEM = r"q[0-9]+ \((?:entry [0-9]+, )?revision [0-9]+\)"
WID = r"q[0-9]+"
ADDED, REVISED, WITHDREW = ("Added %s(?:, %s)*\\." % (ITEM, ITEM), "Revised %s(?:, %s)*\\." % (RITEM, RITEM),
                            "Withdrew %s(?:, %s)*\\." % (WID, WID))
FIRST_LINE = "^(?:Nothing done\\.|Outcome not known yet\\.|%s(?: %s)?(?: %s)?|%s(?: %s)?|%s)$" % (
    ADDED, REVISED, WITHDREW, REVISED, WITHDREW, WITHDREW)

put("grammar/result.md", """# A call's result (contract X7; plan I6)

The tool's result is text. Its first line has a fixed grammar, so a stored call is read from its input and this
line alone, long after the sheet's record is gone.

    first-line = sentences / "Nothing done." / "Outcome not known yet."
    sentences  = sentence *( " " sentence )
    sentence   = added / revised / withdrew              ; in this order, each at most once
    added      = "Added " item *( ", " item ) "."
    revised    = "Revised " ritem *( ", " ritem ) "."
    withdrew   = "Withdrew " id *( ", " id ) "."
    item       = id [ " (entry " n ")" ]
    ritem      = id " (" [ "entry " n ", " ] "revision " n ")"
    id         = "q" 1*DIGIT        n = 1*DIGIT

- The sentences: what a call changed. Ids stand in the order of the call's entries; `n` is an entry's place in
  `ask`, from 1, and every `item` and `ritem` carries it exactly when some entry or withdrawal of the call was
  refused.
- `Nothing done.`: every part of the call was refused, or the call was foreclosed. The sheet is as it was.
- `Outcome not known yet.`: neither the call's step nor its settling answered. The second line reads `The sheet
  did not answer. Do not repeat this call: what it did will be told to you.` A reader draws no ids for such a call
  and does not look for the notice that follows it.

A second line, present when anything was refused, reads `Not done: ` and one clause per refusal, each closed by a
period. A last line, when no surface can show the questions:
`%s`

A denial (the whole call refused before any step) is the engine's error result and has none of these lines.

## The pattern a reader matches

The first line, whole (ECMAScript and Python `re` alike):

    %s

Parsed, as `result.examples.json` holds it under `parsed`:

    { "form": "sentences", "added": [ { "id", "entry"? } ], "revised": [ { "id", "entry"?, "revision" } ],
      "withdrew": [ id ] }
    { "form": "nothing" }           { "form": "unknown" }

## The clauses of `Not done:`

    entry <n>, the reference <path> could not be read: <reason>
    entry <n>, two options share the label "<label>"
    entry <n>, an option's preview needs a single-select question
    entry <n>, multiSelect needs options
    entry <n>, lines must be [a, b] with 1 <= a <= b
    entry <n>, <id> is not open (<how> at <HH:MM>)             how: answered, dismissed, withdrawn, never asked
    entry <n>, <id> was asked by <the main conversation | the subagent <name>>; only its asker revises it
    entry <n>, the sheet holds 500 open questions
    <id> is not open (<how> at <HH:MM>)
    <id> was asked by <...>; only its asker or the main conversation withdraws it
    the sheet could not be written (<why>); call again                 a foreclosed call's one clause

A label in a clause is cut at 200 characters; a time is the session machine's local time.
""" % (NOSURFACE, FIRST_LINE))


# ------------------------------------------------------------------ the schemas, the README, the manifest

for name, body in (("state", STATE_SCHEMA), ("inbox-line", INBOX_SCHEMA), ("show", SHOW_SCHEMA),
                   ("delivery", DELIVERY_SCHEMA), ("surface", SURFACE_SCHEMA), ("tool-input", TOOL_INPUT_SCHEMA)):
    put("schema/%s.schema.json" % name, dump(body))

put("README.md", """# The question sheet's published set

What a second repository reads of the question sheet, frozen at one revision of doperpowers (contracts X1, X2, X3,
X4 and X7 of MAWS's `docs/doperpowers/specs/2026-11-23-question-sheet-design.md`; the execution plan
`docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md` in this repository, I1 to I7). Every file here is
written by `sminos/tests/sheet-contract.gen.py`, by hand from the composite's §4.2 and the plan's tables, never by
an implementation; `sminos/tests/test_sheet_contract.py` holds sminos to it. A change after the set is published is a
ruling of the composite's writer, and raises `version` in `MANIFEST.json`.

## Files

| path | what it is |
|---|---|
| `MANIFEST.json` | `{v, version, files: {path: sha256}, digest}`; `digest` is the SHA-256 of the lines `<sha256>  <path>\\n` of every other file, sorted by path |
| `schema/state.schema.json` | a record's `state.json` (I2): structure, not the tool input's bounds |
| `schema/inbox-line.schema.json` | one line of `inbox.jsonl` (I3) |
| `schema/show.schema.json` | what `sminos sheet show --json` prints (I4) |
| `schema/delivery.schema.json` | the `<sheet-delivery>` block, terminal and steer form alike (I7) |
| `schema/surface.schema.json` | a surface's registration (composite §7) |
| `schema/tool-input.schema.json` | the tool's input (composite §2.1 with §1's limits), without descriptions |
| `examples/<name>/` | an envelope (`envelope.txt`) with the record it was composed from (`input/sheet/<session>/`) and `case.json` `{recipient, runner, tz}`; `terminal/` also has `steer.txt`; `split/then/` is the second envelope of `split`'s Send, composed from its record once the first envelope landed |
| `examples/surface.json` | a registration |
| `grammar/result.md` | the first line of a call's result: its grammar and the pattern a reader matches |
| `grammar/result.examples.json` | stored calls, `[{input, result, parsed}]` |
| `fixtures/<case>/` | one step of the record: `case.json` `{name, covers, session, now, event, verdicts}`, `before/` and `after/` (each a `$SMINOS_HOME`: `sheet/<session>/...`), `show.before.json`, `show.after.json` |

The schemas are JSON Schema 2020-12 held to `type`, `properties`, `required`, `additionalProperties`, `enum`,
`const`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `minimum`, `pattern`, `oneOf` and `$ref` into
the same file's `$defs` (lengths in code points); any validator takes them. A `pattern` is ECMA-262, as JSON Schema
says, with no flags: each is anchored `^...$` and `$` is the end of input, so a string with a newline after it does
not match. A Python reader matches the whole string (`re.fullmatch`, or `\\Z` for `$`); a Python JSON Schema
validator that reads `$` as Python does lets a value with a newline after it through (a known limit: the door checks
strictly). A verdict, an outcome and
a closed question are discriminated shapes: each variant is a closed object with its own fields required, so a field
that belongs to another variant is refused.

## Reading the fixtures

- `event` is the step's input (I5) given inline; `now` is the step's clock, which stamps `at` and `acceptedAt`.
  `verdicts` is the verdict each key of the tail ends with.
- A side with no record has no directory: `before/` is absent where the step makes the record (`empty`,
  `imported-legacy`), and its `show.before.json` is `null` (`sminos sheet show` exits 3, `no sheet`).
- `after/` equals `before/` where the step changed nothing (`torn-tail`): nothing is replaced and `seq` stays.
- A reference's file exists nowhere (`/Users/me/...`), so a reader on any machine reads `changed: true`.

## Reading the examples

- `envelope.txt` holds the envelope exactly, with no newline after its block; `{HOME}` stands for the
  `$SMINOS_HOME` the composer runs with. Times are in the zone `case.json` names.
- An example's record holds what the composer reads; its inbox is left out.

## Readings fixed with the set

Where the plan's shapes left a choice, the set takes one, the same in the plan's interfaces:

- **Serialization** (I1). A JSON document of the set is Python's `json.dumps(obj, sort_keys=True, indent=1,
  ensure_ascii=False)` and a newline, and a step's output is compared after the same serialization. An inbox line
  is compact JSON, its keys in the order its writer gave them.
- **A fixture's clock** (I1). `case.json` carries `now`, the step's time, beside the five fields I1 lists.
- **Always present** (I2). `import` is always `{never, calls}` and `log` always `{next, owed, projects}`; `calls`
  is a list. An answer's outcome always carries `picks`, `text` and `images` (`[]`, `""`, `[]` when the line had
  none); a dismissal's carries none of the three, and its `revision` is the question's at the dismissal. A record
  a `start` makes has an empty `inbox.jsonl` beside `state.json`.
- **`Verdict.at`** (I2) is when the step gave the verdict, for every verdict. When a question closed is
  `closed[id].at`, which `show` prints.
- **Cuts.** The envelope's prose cuts "at N with `…`" as the first N characters and `…`. Every cut of data is the
  first N characters with no mark: `Closed.question` (200), the receipt's text (80), `Closed.answer` (2,000), and
  `show`'s pending question (2,000) and labels (200).
- **What an answer leaves** (I2, I12). `Closed.answer` and the `answered` event the log is owed hold I7's line
  after the id in its full-text form: the question, `→`, the labels and `Their text:`, with no asker and no times
  (those belong to a delivery). The log's is whole; `Closed.answer` is its first 2,000 characters. `receipt` is
  written for an answered question only. A closed question keeps the `key` of the line that closed it.
- **A `delivered` line** (I2) sets `closed[id].deliveredAt` for each key it takes out of `pending`, as `landed`
  does. Only an answered or a dismissed question has a `deliveredAt`: a withdrawal is delivered to nobody (U5).
- **`sent`** (I4) lists the keys with a verdict, sorted by key, then the queued lines in inbox order. A queued
  retract carries its `target`. A `delivered` line's own key reads `delivered` (verdict `applied`, never pending).
- **A line a reader drops** (I4) is one a drain skips (U2): it is not JSON (NaN and the infinities are not), it
  fails the line's schema, a string in it holds a lone UTF-16 surrogate, or it answers an open question at its
  current revision with a pick that is no label of it, or with two picks on a single-select question.
- **The door** (I3) refuses each of those it can see, exit 2 with nothing appended. An upload's name has a stem, the
  part before its final dot, of 1 to 250 characters. Its one `write`, should it come back short, is completed while
  the lock is held (a reader that takes no lock can see the call's first lines in the instant between a short write
  and the rest, or a rollback: a known limit); a write the file
  refuses is cut back to the file's length before the call, and the door exits 1 with nothing appended.
- **Picks by place** (I2, I4). A closed answered question keeps `places`, its picks as integers from 1 among the
  options of the answered revision, as the block carries them. `show --json` carries `places` on each pending answer
  too, read from the whole snapshot before any label is cut: two imported labels can share their first 200
  characters (the `imported` example's do). The cut labels stay beside them for display; the inbox line keeps
  labels.
- **A reader that cannot pair** (I4). The reader reads `state.json`, the inbox, `state.json` again, at most four
  times; if `seq` moved every time it returns nothing unverified: `sminos sheet show` exits 75, and a reader reads
  again.
- **Cuts in `show`'s pending outcomes** (I4), in both forms: the question at 2,000 characters, its header at 60,
  each label and each pick at 200, a subagent's name at 200. An agent id is at most 128 characters, a bound of this
  contract (the engine's ids are far shorter), and is never cut; nor is a question's id, which is at most
  `q999999999`.
- **A reader never fails on a record's strings** (I4). A lone UTF-16 surrogate in anything `show` prints is written
  as U+FFFD. A writer keeps them out: the door refuses them in a line (I3), the step refuses an entry whose strings
  hold one (its own refusal, U14) and an import replaces each with U+FFFD.
- **`show`'s own limits** (I4). The show schema states the cuts the reader makes (a pending outcome's question,
  header, labels, picks and asker's name); the state schema keeps the record's strings unbounded. A queued `sent`
  entry is discriminated by kind: an answer or dismissal carries its `id`, a retract its `target`, a `delivered` line
  neither. A handle's pattern bounds the question's id, not its revision.
- **No record** (I4). `show` exits 3 (`no sheet`); a fixture writes that as `null`.
- **The keyed form** (I4). `show --json --keys` (at most 50 keys) carries each pending outcome under the cuts
  above and its `text` as its first 500 characters, with `textCut: true` when it was longer and the record's
  `textFile` where it has one: every string it carries is bounded, and a hook reads it through a process call that
  returns at most 4 MiB. The unkeyed form carries texts whole.
- **A start's asks** (I5), inline or staged: `{callId, askedAt, questions}`, `questions` today's tool's objects as
  it held them.
- **The input schema** (I6) states neither the call's two rules nor an entry's own (U14): a preview on a
  multi-select question passes the schema and is refused by the entry check, alone.
- **Inside an envelope** (I7), `answered` and `dismissed` each list their questions by the id's number (q8 before
  q12). Which outcomes an envelope carries is the packing's; their order is the ids'.
- **The block** (I7) places `textCut` and `textFile` after `text`, and `more` after `dismissed`, each present only
  when true or when the text has a file.

## Pinning

MAWS copies this directory whole into its tree beside a provenance note naming the doperpowers merge commit, the
sminos version and `digest`, and recomputes the digest over its copy.
""")


def manifest():
    files = {p: sha(d) for p, d in sorted(FILES.items()) if p != "MANIFEST.json"}
    digest = sha("".join("%s  %s\n" % (h, p) for p, h in sorted(files.items())))
    FILES["MANIFEST.json"] = dump({"v": 1, "version": 1, "files": files, "digest": digest})
    return digest


def write(out):
    if os.path.isdir(out) and os.listdir(out):
        if os.path.realpath(out) != os.path.realpath(SET):
            sys.exit("sheet-contract: %s is not empty; --out takes a new or empty directory" % out)
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
    digest = manifest()
    line = "sheet-contract: %d cases, %d examples, digest %s" % (len(CASES), len(EXAMPLES), digest)
    if "--check" in argv:
        have = listing(SET) if os.path.isdir(SET) else {}
        wrong = sorted(p for p in set(have) | set(FILES) if have.get(p) != FILES.get(p))
        print(line)
        if wrong:
            for p in wrong[:20]:
                print("  differs: %s" % p, file=sys.stderr)
            print("sheet-contract: the committed set is not this generator's (%d files)" % len(wrong), file=sys.stderr)
            return 1
        return 0
    out = argv[argv.index("--out") + 1] if "--out" in argv else SET
    write(out)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
