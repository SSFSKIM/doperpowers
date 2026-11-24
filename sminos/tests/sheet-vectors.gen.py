#!/usr/bin/env python3
"""Writes sminos/tests/sheet-vectors/: the step's vectors for what the published set (sminos/types/sheet/) does not
carry: `call`, `settle`, `landed`, `reroute`, the acknowledgement, the `agents` rule, a `start` beyond the two the
fixtures hold, and the context a start composes (plan docs/doperpowers/plans/2026-11-23-question-sheet-c2-sminos.md,
M2; "The state machine", I5, I6, I10). Each `after` and each answer is written here by hand from the plan's tables,
never computed by the step; the parts are the contract generator's own (sheet-contract.gen.py), read with runpy.

    python3 -B sheet-vectors.gen.py             # writes the vectors in place
    python3 -B sheet-vectors.gen.py --check     # the committed vectors are this generator's, byte for byte

A vector is one JSON file, `<name>.json`: {name, covers, session, now, tz, event, before, after, answer}. `before` and
`after` are a $SMINOS_HOME, {path: content}: an object is a JSON document (written as the set writes one), a string
a text file written as given (a JSON file holding a lone surrogate's escape is one), {"$base64": "..."} bytes. `answer` is what the step answers: {ok, code} for a refusal, {ok, effects} for
a step that ran. A replay ignores the record's lock file, which the step makes.
"""

import base64
import json
import os
import runpy
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
OUT = os.path.join(HERE, "sheet-vectors")
G = runpy.run_path(os.path.join(HERE, "sheet-contract.gen.py"))
record, question, opt, L, inbox, offset = G["record"], G["question"], G["opt"], G["L"], G["inbox"], G["offset"]
answer_out, dismiss_out, V = G["answer_out"], G["dismiss_out"], G["V"]
closed_answered, closed_other = G["closed_answered"], G["closed_other"]
owed_question, owed_answered, owed_closed = G["owed_question"], G["owed_answered"], G["owed_closed"]
q_auth, q_ship, q_empty, sha, PNG = G["q_auth"], G["q_ship"], G["q_empty"], G["sha"], G["PNG"]
AUTH, AUTH_OPTS, SHIP, YES_NO, REVIEWER = G["AUTH"], G["AUTH_OPTS"], G["SHIP"], G["YES_NO"], G["REVIEWER"]
CACHE = G["CACHE"]
EXPLORER = {"agentId": "a7c0ffee", "name": "explorer"}
NOW = "2026-11-24T10:00:00.000Z"
NO_SURFACE = "No surface can show these questions right now; they wait on the sheet and show when one returns."
SURFACE = {"sheet/surfaces/standin.json": {"v": 1, "name": "standin", "pid": 1, "url": "http://sheet.localhost:47590",
                                            "reach": "local", "heartbeatAt": "2026-11-24T09:59:55.000Z"}}
VECTORS = {}


def session(n):
    return "5eed0000-0000-4000-8000-0000000001%02d" % n


def rec(sess, state, lines=(), extra=None):
    """A record's files under sheet/<session>/."""
    out = {"sheet/%s/state.json" % sess: state, "sheet/%s/inbox.jsonl" % sess: inbox(lines)}
    for p, c in (extra or {}).items():
        out["sheet/%s/%s" % (sess, p)] = c
    return out


def staged(sess, call_id, files):
    return {"sheet/.staging/%s/%s/%s" % (sess, call_id, p): c for p, c in files.items()}


def ev(name, **f):
    e = {"event": name, "runner": "terminal", "remote": False, "acked": []}
    e.update(f)
    return e


def fx(applied=(), skipped=0, verdicts=None, owed=0, **f):
    out = {"applied": list(applied), "skipped": skipped, "verdicts": dict(verdicts or {}), "owed": owed}
    out.update(f)
    return out


def vector(name, covers, n, event, before, after, answer, now=NOW, surface=True):
    sess = session(n)
    s = dict(SURFACE) if surface else {}
    VECTORS[name] = {"name": name, "covers": covers, "session": sess, "now": now, "tz": "UTC", "event": event,
                     "before": dict(before, **s), "after": dict(after, **s), "answer": answer}


def receipt(sess, nonce, empty=None, imported=()):
    """What a start leaves in the staging for its own retry: its nonce, and what the record cannot give again."""
    return {"sheet/.staging/%s/.start-receipt.json" % sess: {"nonce": nonce, "empty": empty,
                                                               "imported": list(imported)}}


def started(before=(), empty=None, imported=()):
    return {"empty": empty, "before": list(before), "beforeCount": len(before), "imported": list(imported)}


def entry(q, **f):
    return dict({"question": q}, **f)


def asked(id_, q, call, options=(), header=None, asker="main", revision=1, refs=(), multi=False, context=None):
    """A question a call put on the sheet at NOW."""
    return question(id_, q, NOW, call, options, header, revision=revision, asker=asker, multi=multi,
                    context=context, refs=refs)


# ------------------------------------------------------------------ call: add, with references captured

S = session(1)
q1 = q_auth(1)
AUTH_LINES = "export const a = 40;\nexport const b = 41;\nexport const c = 42;\n"
E1 = entry(SHIP, header="Migration", options=[{"label": "Yes", "recommended": True}, {"label": "No"}])
E2 = entry("Is the session check in these lines the one to keep?", header="Session check",
           context="The two checks disagree on expiry.",
           references=[{"path": "src/auth.ts", "lines": [40, 42]}, {"path": "docs/login.png"}])
CALL = {"asker": "main", "entries": [
    {"file": "entry-1.json", "captures": []},
    {"file": "entry-2.json", "captures": [
        {"ok": True, "abs": "/work/proj/src/auth.ts", "kind": "text", "file": "ref-2-1", "startLine": 40,
         "numLines": 3, "totalLines": 212, "size": 6120, "mtimeMs": 1763888400000},
        {"ok": True, "abs": "/work/proj/docs/login.png", "kind": "image", "file": "ref-2-2", "mediaType": "image/png",
         "size": len(PNG), "mtimeMs": 1763887000000}]}], "withdraw": []}
STAGE = staged(S, "toolu_v01", {"call.json": CALL, "entry-1.json": E1, "entry-2.json": E2, "ref-2-1": AUTH_LINES,
                                "ref-2-2": base64.b64encode(PNG).decode()})
P = {"q1": G["PROJECT"]}
nq2 = asked("q2", SHIP, "toolu_v01", [{"label": "Yes", "recommended": True}, {"label": "No"}], "Migration")
nq3 = asked("q3", E2["question"], "toolu_v01", header="Session check", context=E2["context"], refs=[
    {"path": "src/auth.ts", "lines": [40, 42], "abs": "/work/proj/src/auth.ts", "sha256": sha(AUTH_LINES),
     "bytes": len(AUTH_LINES.encode()), "kind": "text", "startLine": 40, "numLines": 3, "totalLines": 212,
     "size": 6120, "mtimeMs": 1763888400000},
    {"path": "docs/login.png", "abs": "/work/proj/docs/login.png", "sha256": sha(PNG), "bytes": len(PNG),
     "kind": "image", "mediaType": "image/png", "size": len(PNG), "mtimeMs": 1763887000000}])
vector("call-add", "a call adds two entries, staged with their captures: ids from nextId, each reference's body "
       "under refs/ by its hash, the log owed a question for each, the result in calls; the staging stays until "
       "acknowledged", 1, ev("call", call={"callId": "toolu_v01"}),
       {**rec(S, record(S, 3, 2, 0, [q1], projects=P)), **STAGE},
       {**rec(S, record(S, 4, 4, 0, [q1, nq2, nq3], log_next=4, projects=P,
                        owed=[owed_question(2, S, nq2), owed_question(3, S, nq3)],
                        calls=[{"callId": "toolu_v01", "result": "Added q2, q3."}]),
              extra={"refs/" + sha(AUTH_LINES): AUTH_LINES, "refs/" + sha(PNG): {"$base64": base64.b64encode(PNG)
                                                                                   .decode()}}), **STAGE},
       {"ok": True, "effects": fx(result="Added q2, q3.", owed=2)})

# call, its id already in calls: the recorded result again, nothing changed
S = session(2)
qa = q_auth(1)
qb = asked("q2", SHIP, "toolu_v02", YES_NO, "Migration")
before = {**rec(S, record(S, 5, 3, 0, [qa, qb], calls=[{"callId": "toolu_v02", "result": "Added q2."}])),
          **staged(S, "toolu_v02", {"call.json": {"asker": "main", "entries": [{"file": "entry-1.json",
                                                                                 "captures": []}]},
                                    "entry-1.json": entry(SHIP, header="Migration", options=YES_NO)})}
vector("call-again", "a call whose id is in calls (its answer was lost): nothing applied again, the recorded result",
       2, ev("call", call={"callId": "toolu_v02"}), before, before,
       {"ok": True, "effects": fx(result="Added q2.")})

# call, its staging gone and its id not in calls
S = session(3)
before = rec(S, record(S, 5, 2, 0, [q_auth(1)]))
vector("call-gone", "a call whose staging is gone (acknowledged, or cleared by a start): gone, nothing changed", 3,
       ev("call", call={"callId": "toolu_v03"}), before, before, {"ok": False, "code": "gone"})

# call: revise, an imported question's mark going with its old content
S = session(4)
qi = question("q2", "Which rollout gate?", "2026-11-22T18:00:00.000Z", "toolu_01Legacy",
              [opt("Every gate"), opt("No gate")], "Gate", imported={"callId": "toolu_01Legacy", "index": 0})
R1 = entry(AUTH, header="Auth method", options=[{"label": "OAuth"}, {"label": "Passkeys"}], id="q1")
R2 = entry("Which rollout gate, now that the beta is over?", options=[{"label": "Every gate"}, {"label": "None"}],
           id="q2")
STAGE = staged(S, "toolu_v04", {"call.json": {"asker": "main", "entries": [
    {"file": "entry-1.json", "captures": []}, {"file": "entry-2.json", "captures": []}]},
    "entry-1.json": R1, "entry-2.json": R2})
r1 = asked("q1", AUTH, "toolu_v04", [{"label": "OAuth"}, {"label": "Passkeys"}], "Auth method", revision=2)
r2 = asked("q2", R2["question"], "toolu_v04", [{"label": "Every gate"}, {"label": "None"}], revision=2)
vector("call-revise", "a call revises two of its own questions: each replaced by its entry at revision + 1, its place "
       "kept, askedAt and callId the call's; an imported question revised is no longer marked imported; a revise "
       "owes the log nothing", 4, ev("call", call={"callId": "toolu_v04"}),
       {**rec(S, record(S, 2, 3, 0, [q_auth(1), qi])), **STAGE},
       {**rec(S, record(S, 3, 3, 0, [r1, r2], calls=[{"callId": "toolu_v04",
                                                       "result": "Revised q1 (revision 2), q2 (revision 2)."}])),
        **STAGE},
       {"ok": True, "effects": fx(result="Revised q1 (revision 2), q2 (revision 2).")})

# call, inline, partly refused: each entry stands alone, and every id carries its entry's place
S = session(5)
qa, qs = q_auth(1), q_ship(2)
qr = q_empty(3, asker=REVIEWER)
k2 = L("page-0502a001", "answer", "page", "2026-11-23T14:04:00.000Z", id="q2", revision=1, picks=["Yes"])
cl = {"q2": closed_answered(qs, k2, "2026-11-23T14:05:00.000Z")}
vs = {k2["key"]: V("applied", "answer", "2026-11-23T14:05:00.000Z", id="q2")}
CALL = {"callId": "toolu_v05", "asker": "main", "entries": [
    entry("Which log level in production?"),
    entry(SHIP, id="q2", options=YES_NO),
    entry(G["EMPTY_Q"], id="q3"),
    {"refused": "the reference src/x.ts could not be read: permission denied"},
    entry("Keep the export?", options=[{"label": "Yes"}, {"label": "Yes"}]),
    entry(AUTH, id="q1", header="Auth method", options=[{"label": "OAuth"}, {"label": "Passkeys"}])],
    "withdraw": ["q9"]}
RES = ("Added q4 (entry 1). Revised q1 (entry 6, revision 2).\nNot done: entry 2, q2 is not open (answered at 14:05). "
       "entry 3, q3 was asked by the subagent reviewer; only its asker revises it. entry 4, the reference src/x.ts "
       "could not be read: permission denied. entry 5, two options share the label \"Yes\". q9 is not open (never "
       "asked).")
n4 = asked("q4", "Which log level in production?", "toolu_v05")
n1 = asked("q1", AUTH, "toolu_v05", [{"label": "OAuth"}, {"label": "Passkeys"}], "Auth method", revision=2)
vector("call-refusals", "a call given inline (as a shell gives one), partly refused: an id not open, another asker's "
       "question, an entry the mod refused, two options with one label, a withdrawal of an id never asked; the "
       "rest applied; every added and revised id with its entry's place; the clauses in order", 5,
       ev("call", call=CALL),
       rec(S, record(S, 6, 4, 0, [qa, qr], closed=cl, verdicts=vs, log_next=5)),
       rec(S, record(S, 7, 5, 0, [n1, qr, n4], closed=cl, verdicts=vs, log_next=6,
                     projects={"q%d" % i: G["PROJECT"] for i in range(1, 4)},
                     owed=[owed_question(5, S, n4)], calls=[{"callId": "toolu_v05", "result": RES}])),
       {"ok": True, "effects": fx(result=RES, owed=1)})

# call: an entry's own rules (U14), which the step holds as the mod does
S = session(6)
SURR = '{"question": "Half an emoji: \\ud83d, then the rest?"}\n'
STAGE = staged(S, "toolu_v06", {
    "call.json": {"asker": "main", "entries": [
        {"file": "entry-1.json", "captures": []}, {"file": "entry-2.json", "captures": []},
        {"file": "entry-3.json", "captures": [{"ok": True, "abs": "/work/proj/a.ts", "kind": "text",
                                               "file": "ref-3-1", "startLine": 9, "numLines": 1, "totalLines": 20,
                                               "size": 400, "mtimeMs": 1763888400000}]},
        {"file": "entry-4.json", "captures": []}, {"file": "entry-5.json", "captures": []}]},
    "entry-1.json": entry("Which screens?", multiSelect=True,
                          options=[{"label": "Home", "preview": "## Home"}, {"label": "Settings"}]),
    "entry-2.json": entry("Anything else?", multiSelect=True),
    "entry-3.json": entry("Is this line right?", references=[{"path": "a.ts", "lines": [9, 2]}]),
    "ref-3-1": "export const x = 9;\n",
    "entry-4.json": SURR,
    "entry-5.json": entry(CACHE, options=[{"label": "Yes"}, {"label": "No"}])})
RES = ("Added q2 (entry 5).\nNot done: entry 1, an option's preview needs a single-select question. entry 2, "
       "multiSelect needs options. entry 3, lines must be [a, b] with 1 <= a <= b. entry 4, a string holds a lone "
       "UTF-16 surrogate.")
n2 = asked("q2", CACHE, "toolu_v06", [{"label": "Yes"}, {"label": "No"}])
vector("call-entry-rules", "U14: a preview on a multi-select question, multiSelect without options, a line range out "
       "of order and a lone UTF-16 surrogate each refuse their entry alone; nothing of a refused entry's capture is "
       "kept under refs/", 6, ev("call", call={"callId": "toolu_v06"}),
       {**rec(S, record(S, 2, 2, 0, [q_auth(1)])), **STAGE},
       {**rec(S, record(S, 3, 3, 0, [q_auth(1), n2], log_next=3, projects={"q1": G["PROJECT"]},
                        owed=[owed_question(2, S, n2)], calls=[{"callId": "toolu_v06", "result": RES}])), **STAGE},
       {"ok": True, "effects": fx(result=RES, owed=1)})

# call by a subagent: its own questions only
S = session(7)
qm, qx = q_auth(1), q_ship(2, asker=EXPLORER)
STAGE = staged(S, "toolu_v07", {"call.json": {
    "asker": EXPLORER, "entries": [{"file": "entry-1.json", "captures": []}, {"file": "entry-2.json", "captures": []}],
    "withdraw": ["q1", "q2"]},
    "entry-1.json": entry(CACHE, header="Cache key", options=[{"label": "Yes"}, {"label": "No"}]),
    "entry-2.json": entry(AUTH, id="q1", options=[{"label": "OAuth"}])})
RES = ("Added q3 (entry 1). Withdrew q2.\nNot done: entry 2, q1 was asked by the main conversation; only its asker "
       "revises it. q1 was asked by the main conversation; only its asker or the main conversation withdraws it.")
n3 = asked("q3", CACHE, "toolu_v07", [{"label": "Yes"}, {"label": "No"}], "Cache key", asker=EXPLORER)
vector("call-subagent", "a subagent calls: its question added with it as asker; the main conversation's question it "
       "may neither revise nor withdraw; its own it withdraws", 7, ev("call", call={"callId": "toolu_v07"}),
       {**rec(S, record(S, 4, 3, 0, [qm, qx])), **STAGE},
       {**rec(S, record(S, 5, 4, 0, [qm, n3], closed={"q2": closed_other(qx, "withdrawn", NOW)}, log_next=5,
                        projects={"q1": G["PROJECT"], "q2": G["PROJECT"]},
                        owed=[owed_question(3, S, n3), owed_closed(4, S, qx, "withdrawn")],
                        calls=[{"callId": "toolu_v07", "result": RES}])), **STAGE},
       {"ok": True, "effects": fx(result=RES, owed=2)})

# call: the main conversation withdraws a subagent's question, staged as call.json alone
S = session(8)
qm, qx = q_auth(1), q_ship(2, asker=REVIEWER)
STAGE = staged(S, "toolu_v08", {"call.json": {"asker": "main", "entries": [], "withdraw": ["q2"]}})
vector("call-withdraw-only", "a call that only withdraws, staged as call.json alone: the main conversation withdraws "
       "a subagent's question; a withdrawal makes no pending outcome (U5) and owes the log its closing", 8,
       ev("call", call={"callId": "toolu_v08"}),
       {**rec(S, record(S, 2, 3, 0, [qm, qx])), **STAGE},
       {**rec(S, record(S, 3, 3, 0, [qm], closed={"q2": closed_other(qx, "withdrawn", NOW)}, log_next=4,
                        owed=[owed_closed(3, S, qx, "withdrawn")],
                        calls=[{"callId": "toolu_v08", "result": "Withdrew q2."}])), **STAGE},
       {"ok": True, "effects": fx(result="Withdrew q2.", owed=1)})

# call: every entry refused by the mod, staged as call.json alone
S = session(9)
STAGE = staged(S, "toolu_v09", {"call.json": {"asker": "main", "entries": [
    {"refused": "the reference .env could not be read: denied by a rule in the settings"}]}})
RES = "Nothing done.\nNot done: entry 1, the reference .env could not be read: denied by a rule in the settings."
vector("call-all-refused", "a call every entry of which the mod refused, staged as call.json alone: Nothing done., "
       "its clause, the result kept in calls (U4)", 9, ev("call", call={"callId": "toolu_v09"}),
       {**rec(S, record(S, 2, 2, 0, [q_auth(1)])), **STAGE},
       {**rec(S, record(S, 3, 2, 0, [q_auth(1)], calls=[{"callId": "toolu_v09", "result": RES}])), **STAGE},
       {"ok": True, "effects": fx(result=RES)})

# call: the floor, on a record that has assigned no id
S = session(10)
CALL = {"callId": "toolu_v10", "floor": 11, "asker": "main", "entries": [entry(SHIP, options=YES_NO)]}
n12 = asked("q12", SHIP, "toolu_v10", YES_NO)
vector("call-floor", "a call carrying the conversation's floor to a record that has assigned no id: nextId first "
       "raised to floor + 1, so the new question is q12", 10, ev("call", call=CALL),
       rec(S, record(S, 1, 1, 0)),
       rec(S, record(S, 2, 13, 0, [n12], log_next=2, projects={}, owed=[owed_question(1, S, n12)],
                     calls=[{"callId": "toolu_v10", "result": "Added q12."}])),
       {"ok": True, "effects": fx(result="Added q12.", owed=1)})

# call: the drain first, so a revise never overtakes an answer already in the inbox
S = session(11)
qa = q_auth(1)
a = L("page-1101a001", "answer", "page", "2026-11-24T09:59:00.000Z", id="q1", revision=1, picks=["OAuth"])
STAGE = staged(S, "toolu_v11", {"call.json": {"asker": "main", "entries": [{"file": "entry-1.json",
                                                                             "captures": []}]},
                                "entry-1.json": entry(AUTH, id="q1", options=[{"label": "Passkeys"}])})
RES = "Nothing done.\nNot done: entry 1, q1 is not open (answered at 10:00)."
out = answer_out(a, qa, NOW)
vector("call-drains-first", "a call drains before it applies its entries: the queued answer is applied, and the "
       "revise that follows finds its question answered", 11, ev("call", call={"callId": "toolu_v11"}),
       {**rec(S, record(S, 2, 2, 0, [qa]), [a]), **STAGE},
       {**rec(S, record(S, 3, 2, offset(a), [], [out], {"q1": closed_answered(qa, a, NOW)},
                        {a["key"]: V("applied", "answer", NOW, id="q1")}, 3, [owed_answered(2, S, qa, a)],
                        calls=[{"callId": "toolu_v11", "result": RES}]), [a]), **STAGE},
       {"ok": True, "effects": fx([a["key"]], result=RES, owed=1)})

# call with no surface alive: the result's last line
S = session(12)
CALL = {"callId": "toolu_v12", "asker": "main", "entries": [entry(SHIP, options=YES_NO)]}
n2 = asked("q2", SHIP, "toolu_v12", YES_NO)
vector("call-no-surface", "a call where no surface is alive: the result ends with the sentence that says so (I6)", 12,
       ev("call", call=CALL), rec(S, record(S, 2, 2, 0, [q_auth(1)])),
       rec(S, record(S, 3, 3, 0, [q_auth(1), n2], log_next=3, projects={"q1": G["PROJECT"]},
                     owed=[owed_question(2, S, n2)], calls=[{"callId": "toolu_v12",
                                                             "result": "Added q2.\n" + NO_SURFACE}])),
       {"ok": True, "effects": fx(result="Added q2.\n" + NO_SURFACE, owed=1)}, surface=False)

# ------------------------------------------------------------------ settle

S = session(13)
before = rec(S, record(S, 4, 3, 0, [q_auth(1), q_ship(2)], calls=[{"callId": "toolu_s01", "result": "Added q2."}]))
vector("settle-recorded", "settle of a call that committed (its answer lost): the recorded result, nothing changed",
       13, ev("settle", call={"callId": "toolu_s01"}), before, before, {"ok": True, "effects": fx(result="Added q2.")})

S = session(14)
STAGE = staged(S, "toolu_s02", {"call.json": {"asker": "main", "entries": [{"file": "entry-1.json",
                                                                             "captures": []}]},
                                "entry-1.json": entry(SHIP, options=YES_NO)})
vector("settle-forecloses", "settle of a call with no outcome: the id joins calls as foreclosed, so its step, should "
       "it run late, commits nothing; the staging stays until acknowledged", 14,
       ev("settle", call={"callId": "toolu_s02"}),
       {**rec(S, record(S, 4, 2, 0, [q_auth(1)])), **STAGE},
       {**rec(S, record(S, 5, 2, 0, [q_auth(1)], calls=[{"callId": "toolu_s02", "foreclosed": True}])), **STAGE},
       {"ok": True, "effects": fx(foreclosed=True)})

S = session(15)
STAGE = staged(S, "toolu_s03", {"call.json": {"asker": "main", "entries": [{"file": "entry-1.json",
                                                                             "captures": []}]},
                                "entry-1.json": entry(SHIP, options=YES_NO)})
before = {**rec(S, record(S, 5, 2, 0, [q_auth(1)], calls=[{"callId": "toolu_s03", "foreclosed": True}])), **STAGE}
vector("call-after-settle", "the call's own step running after settle foreclosed it: it commits nothing and answers "
       "foreclosed", 15, ev("call", call={"callId": "toolu_s03"}), before, before,
       {"ok": True, "effects": fx(foreclosed=True)})

# ------------------------------------------------------------------ landed, reroute, the acknowledgement, agents

S = session(16)
T1 = "2026-11-24T09:50:00.000Z"
qa, qs = q_auth(1), q_ship(2)
ka = L("page-1601a001", "answer", "page", "2026-11-24T09:49:00.000Z", id="q1", revision=1, picks=["OAuth"])
ks = L("page-1601a002", "answer", "page", "2026-11-24T09:49:30.000Z", id="q2", revision=1, picks=["No"])
oa, os_ = answer_out(ka, qa, T1), answer_out(ks, qs, T1)
cl = {"q1": closed_answered(qa, ka, T1), "q2": closed_answered(qs, ks, T1)}
vs = {ka["key"]: V("applied", "answer", T1, id="q1"), ks["key"]: V("applied", "answer", T1, id="q2")}
vector("landed", "landed: a key pending leaves pending and its question has deliveredAt; a key that is not pending "
       "is left alone", 16, ev("landed", keys=[ka["key"], "page-16010bad"]),
       rec(S, record(S, 6, 3, offset(ka, ks), [], [oa, os_], cl, vs, 5), [ka, ks]),
       rec(S, record(S, 7, 3, offset(ka, ks), [], [os_], dict(cl, q1=dict(cl["q1"], deliveredAt=NOW)), vs, 5),
           [ka, ks]),
       {"ok": True, "effects": fx(verdicts={ka["key"]: vs[ka["key"]]})})

S = session(17)
qr = q_ship(1, asker=REVIEWER)
kr = L("page-1701a001", "answer", "page", "2026-11-24T09:49:00.000Z", id="q1", revision=1, picks=["Yes"])
o_taken = answer_out(kr, qr, T1, recipient={"agentId": "a1b2c3"}, taken=True)
cl = {"q1": closed_answered(qr, kr, T1)}
vs = {kr["key"]: V("applied", "answer", T1, id="q1")}
vector("reroute", "reroute: an outcome a subagent's send did not take goes to the main conversation", 17,
       ev("reroute", keys=[kr["key"]]),
       rec(S, record(S, 3, 2, offset(kr), [], [o_taken], cl, vs, 3), [kr]),
       rec(S, record(S, 4, 2, offset(kr), [], [dict(o_taken, recipient="main", taken=False)], cl, vs, 3), [kr]),
       {"ok": True, "effects": fx(verdicts={kr["key"]: vs[kr["key"]]})})

S = session(18)
A1 = staged(S, "toolu_a1", {"call.json": {"asker": "main", "entries": [], "withdraw": ["q9"]}})
A2 = staged(S, "toolu_a2", {"call.json": {"asker": "main", "entries": [], "withdraw": ["q8"]}})
calls = [{"callId": "toolu_a1", "result": "Nothing done.\nNot done: q9 is not open (never asked)."},
         {"callId": "toolu_a2", "foreclosed": True}]
vector("acked", "a step's acknowledgement: each acknowledged call leaves calls and its staging is deleted; another "
       "call's stays", 18, ev("drain", acked=["toolu_a1"]),
       {**rec(S, record(S, 7, 2, 0, [q_auth(1)], calls=calls)), **A1, **A2},
       {**rec(S, record(S, 8, 2, 0, [q_auth(1)], calls=calls[1:])), **A2},
       {"ok": True, "effects": fx()})

S = session(19)
vector("agents-ended", "the agents every step carries: a pending outcome whose subagent is no longer running goes to "
       "the main conversation", 19, ev("drain", agents={"running": ["a7c0ffee"], "direct": True}),
       rec(S, record(S, 3, 2, offset(kr), [], [o_taken], cl, vs, 3), [kr]),
       rec(S, record(S, 4, 2, offset(kr), [], [dict(o_taken, recipient="main", taken=False)], cl, vs, 3), [kr]),
       {"ok": True, "effects": fx()})

S = session(20)
q1r, q2x = q_auth(1, asker=REVIEWER), q_ship(2, asker=EXPLORER)
a1 = L("page-2001a001", "answer", "page", "2026-11-24T09:59:00.000Z", id="q1", revision=1, picks=["OAuth"])
a2 = L("page-2001a002", "answer", "page", "2026-11-24T09:59:01.000Z", id="q2", revision=1, picks=["No"])
outs = [answer_out(a1, q1r, NOW, recipient={"agentId": "a1b2c3"}, taken=True), answer_out(a2, q2x, NOW)]
vs = {a1["key"]: V("applied", "answer", NOW, id="q1"), a2["key"]: V("applied", "answer", NOW, id="q2")}
cl = {"q1": closed_answered(q1r, a1, NOW), "q2": closed_answered(q2x, a2, NOW)}
vector("recipient-running", "an answer's recipient: the subagent that asked when it is running and reachable "
       "directly (taken); the main conversation for one not running", 20,
       ev("drain", agents={"running": ["a1b2c3"], "direct": True}, keys=[a1["key"], a2["key"]]),
       rec(S, record(S, 2, 3, 0, [q1r, q2x]), [a1, a2]),
       rec(S, record(S, 3, 3, offset(a1, a2), [], outs, cl, vs, 5,
                     [owed_answered(3, S, q1r, a1), owed_answered(4, S, q2x, a2)]), [a1, a2]),
       {"ok": True, "effects": fx([a1["key"], a2["key"]], verdicts=vs, owed=2)})

S = session(21)
outs = [answer_out(a1, q1r, NOW), answer_out(a2, q2x, NOW)]
vector("recipient-indirect", "an answer's recipient when a subagent cannot be reached directly: the main "
       "conversation, the asker running or not", 21,
       ev("drain", agents={"running": ["a1b2c3", "a7c0ffee"], "direct": False}),
       rec(S, record(S, 2, 3, 0, [q1r, q2x]), [a1, a2]),
       rec(S, record(S, 3, 3, offset(a1, a2), [], outs, cl, vs, 5,
                     [owed_answered(3, S, q1r, a1), owed_answered(4, S, q2x, a2)]), [a1, a2]),
       {"ok": True, "effects": fx([a1["key"], a2["key"]], owed=2)})

# ------------------------------------------------------------------ start

S = session(22)
qa, qr, qe = q_auth(1), q_ship(2, asker=REVIEWER), q_empty(3)
ka = L("page-2201a001", "answer", "page", "2026-11-24T09:40:00.000Z", id="q1", revision=1, picks=["OAuth"])
kr = L("page-2201a002", "answer", "page", "2026-11-24T09:41:00.000Z", id="q2", revision=1, picks=["Yes"])
T1 = "2026-11-24T09:42:00.000Z"
oa, orr = answer_out(ka, qa, T1), answer_out(kr, qr, T1, recipient={"agentId": "a1b2c3"}, taken=True)
cl = {"q1": closed_answered(qa, ka, T1), "q2": closed_answered(qr, kr, T1)}
vs = {ka["key"]: V("applied", "answer", T1, id="q1"), kr["key"]: V("applied", "answer", T1, id="q2")}
STAGE = {**staged(S, "toolu_x1", {"call.json": {"asker": "main", "entries": [], "withdraw": ["q7"]}}),
         **staged(S, "start-0001", {"ask-1.json": {"callId": "toolu_q", "askedAt": T1, "questions": []}})}
CONTEXT = "\n".join([
    "[sheet v1] Your question sheet, after a resume.",
    'Open: q3 (revision 1) "Empty state" — "What should the empty state say?" No options: answered in text.',
    'Answered, the answer not yet delivered to you: q1 (revision 1) "Auth method" — "Which auth method should the '
    'login use?" Options: 1. OAuth; 2. Passkeys; 3. Magic link.',
    'Answered, the answer not yet delivered to you: q2 (revision 1), asked by the subagent reviewer (a1b2c3) '
    '"Migration" — "Ship the migration today?" Options: 1. Yes; 2. No.',
    "New ids continue from q4."])
vector("start-existing", "a start on a record that exists: calls forgotten and every call's staging, and an earlier "
       "start's, made unavailable; every pending outcome owed across a stop and the main conversation's; the "
       "context names what is open and what is owed; what it found kept under its nonce for its retry",
       22, ev("start", agents={"running": ["a1b2c3"], "direct": True},
              start={"source": "resume", "nonce": "0002", "today": {"definite": False, "asks": []}}),
       {**rec(S, record(S, 9, 4, offset(ka, kr), [qe], [oa, orr], cl, vs, 6,
                        calls=[{"callId": "toolu_x1", "result": "Nothing done.\nNot done: q7 is not open (never "
                                                                "asked)."}]), [ka, kr]), **STAGE},
       {**rec(S, record(S, 10, 4, offset(ka, kr), [qe], [dict(oa, acrossStop=True),
                                                         dict(orr, recipient="main", taken=False, acrossStop=True)],
                        cl, vs, 6), [ka, kr]),
        **receipt(S, "0002")},
       {"ok": True, "effects": fx(start=started([ka["key"], kr["key"]]), context=CONTEXT)})

S = session(23)
ASK = {"callId": "toolu_f1", "askedAt": "2026-11-24T09:00:00.000Z",
       "questions": [{"question": SHIP, "header": "Migration", "options": [opt("Yes", "Now."), opt("No", "Later.")],
                      "multiSelect": False}]}
FORK = ("[sheet v1] This conversation is a copy: its question sheet starts empty. Questions asked before the copy "
        "belong to the conversation it was copied from, and their answers will not come here; ask again what you "
        "still need. New ids start at q12.")
vector("start-fork", "a fork's first start: a new record taking the floor and import.never, so today's asks the event "
       "carries are not imported, now or later; the context says the sheet starts empty and where ids start; its own "
       "staged asks kept for its retry", 23,
       ev("start", start={"source": "fork", "floor": 11, "nonce": "0001", "today": {"definite": True,
                                                                   "asks": [{"file": "start-0001/ask-1.json"}]}}),
       staged(S, "start-0001", {"ask-1.json": ASK}),
       {**rec(S, record(S, 1, 12, 0, log_next=1, projects={}, never=True)), **staged(S, "start-0001", {"ask-1.json": ASK}),
        **receipt(S, "0001", "fork")},
       {"ok": True, "effects": fx(start=started(empty="fork"), context=FORK)})

S = session(24)
LOST = ("[sheet v1] The question sheet's record was not found, so the sheet starts empty; questions asked earlier "
        "are no longer open. New ids start at q8.")
vector("start-lost", "a resume whose conversation holds the sheet's ids (a floor) and whose record is gone: a new "
       "record from the floor, and the context says so", 24,
       ev("start", start={"source": "resume", "floor": 7, "nonce": "0001", "today": {"definite": True, "asks": []}}),
       {}, {**rec(S, record(S, 1, 8, 0, log_next=1, projects={})), **receipt(S, "0001", "lost")},
       {"ok": True, "effects": fx(start=started(empty="lost"), context=LOST)})

S = session(25)
qi = question("q1", "Which rollout gate?", "2026-11-22T18:00:00.000Z", "toolu_A", [opt("Every gate"), opt("No gate")],
              "Gate", imported={"callId": "toolu_A", "index": 0})
ASK_A = {"callId": "toolu_A", "askedAt": "2026-11-22T18:00:00.000Z",
         "questions": [{"question": "Which rollout gate?", "header": "Gate",
                        "options": [opt("Every gate"), opt("No gate")], "multiSelect": False}]}
ASK_B = ('{"callId": "toolu_B", "askedAt": "2026-11-23T08:00:00.000Z", "questions": ['
         '{"question": "Which screens get the new layout?", "header": "Screens \\udc00", "options": '
         '[{"label": "Home", "description": "The landing screen.", "preview": "## Home"}, {"label": "Settings"}], '
         '"multiSelect": true}, {"question": "Anything to add?", "options": []}]}\n')
qb1 = question("q2", "Which screens get the new layout?", "2026-11-23T08:00:00.000Z", "toolu_B",
               [opt("Home", "The landing screen.", preview="## Home"), opt("Settings")], "Screens �", multi=True,
               imported={"callId": "toolu_B", "index": 0})
qb2 = question("q3", "Anything to add?", "2026-11-23T08:00:00.000Z", "toolu_B",
               imported={"callId": "toolu_B", "index": 1})
CONTEXT = "\n".join([
    "[sheet v1] Your question sheet, after a resume.",
    'Open: q1 (revision 1) "Gate" — "Which rollout gate?" Options: 1. Every gate; 2. No gate.',
    'Open: q2 (revision 1) "Screens �" — "Which screens get the new layout?" Options: 1. Home; 2. Settings.',
    'Open: q3 (revision 1) — "Anything to add?" No options: answered in text.',
    'Moved onto the sheet from the earlier question tool: q2 "Which screens get the new layout?" (call toolu_B, '
    'question 1), q3 "Anything to add?" (call toolu_B, question 2).',
    "New ids continue from q4."])
vector("start-import", "a start's import of today's asks, read definitely: an ask already imported is not imported "
       "again; a new one becomes one question for each of its questions, kept as asked (a preview on a multi-select "
       "question), a lone surrogate written as U+FFFD; the log owed a question for each; the context tells it", 25,
       ev("start", start={"source": "resume", "nonce": "0002", "today": {"definite": True, "asks": [
           {"file": "start-0002/ask-1.json"}, {"file": "start-0002/ask-2.json"}]}}),
       {**rec(S, record(S, 3, 2, 0, [qi], log_next=2, imports={"toolu_A": ["q1"]})),
        **staged(S, "start-0002", {"ask-1.json": ASK_A, "ask-2.json": ASK_B})},
       {**rec(S, record(S, 4, 4, 0, [qi, qb1, qb2], log_next=4, projects={"q1": G["PROJECT"]},
                        owed=[owed_question(2, S, qb1), owed_question(3, S, qb2)],
                        imports={"toolu_A": ["q1"], "toolu_B": ["q2", "q3"]})),
        **staged(S, "start-0002", {"ask-1.json": ASK_A, "ask-2.json": ASK_B}),
        **receipt(S, "0002", imported=[{"callId": "toolu_B", "ids": ["q2", "q3"]}])},
       {"ok": True, "effects": fx(start=started(imported=[{"callId": "toolu_B", "ids": ["q2", "q3"]}]),
                                  context=CONTEXT, owed=2)})

S = session(26)
vector("start-indefinite", "a start whose read of today's asks was not definite: nothing imported and nothing "
       "recorded, so the next start reads again; the floor raises a record that has assigned no id; a start with no "
       "nonce (a shell's) is always new and leaves no receipt", 26,
       ev("start", start={"source": "resume", "floor": 5, "today": {"definite": False, "asks": [ASK_A]}}),
       rec(S, record(S, 1, 1, 0, log_next=1, projects={})),
       rec(S, record(S, 2, 6, 0, log_next=1, projects={})),
       {"ok": True, "effects": fx(start=started(), context="")})

# ------------------------------------------------------------------ a compaction's context; no record

S = session(27)
qa = q_auth(1, revision=2)
qx = question("q2", "Which cache?", "2026-11-23T09:05:00.000Z", "toolu_01Cach", [], asker=EXPLORER)
CONTEXT = "\n".join([
    "[sheet v1] Your question sheet, after a compaction.",
    'Open: q1 (revision 2) "Auth method" — "Which auth method should the login use?" Options: 1. OAuth; 2. Passkeys; '
    '3. Magic link.',
    'Open: q2 (revision 1), asked by the subagent explorer (a7c0ffee) — "Which cache?" No options: answered in text.',
    "New ids continue from q3."])
before = rec(S, record(S, 4, 3, 0, [qa, qx]))
vector("drain-context", "a drain after a compaction composes I10's context: each open question with its revision, "
       "asker, header, text and labels in order, and where ids continue", 27, ev("drain", context="compact"),
       before, before, {"ok": True, "effects": fx(context=CONTEXT)})

vector("no-record", "any event but start on a session with no record answers no-record and makes none", 28,
       ev("drain"), {}, {}, {"ok": False, "code": "no-record"})


# ------------------------------------------------------------------ writing


def text():
    return {name + ".json": json.dumps(v, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
            for name, v in sorted(VECTORS.items())}


def main(argv):
    files = text()
    line = "sheet-vectors: %d vectors" % len(files)
    if "--check" in argv:
        have = {}
        if os.path.isdir(OUT):
            for n in os.listdir(OUT):
                with open(os.path.join(OUT, n), encoding="utf-8") as f:
                    have[n] = f.read()
        wrong = sorted(n for n in set(have) | set(files) if have.get(n) != files.get(n))
        print(line)
        for n in wrong:
            print("  differs: %s" % n, file=sys.stderr)
        return 1 if wrong else 0
    os.makedirs(OUT, exist_ok=True)
    for n in os.listdir(OUT):
        os.unlink(os.path.join(OUT, n))
    for n, data in files.items():
        with open(os.path.join(OUT, n), "w", encoding="utf-8") as f:
            f.write(data)
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
