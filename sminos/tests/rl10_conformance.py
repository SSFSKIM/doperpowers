#!/usr/bin/env python3
"""O10's RL10 conversation replayed against sminos (O12 M7b, M5's conformance
replay): rl10-conversation.json is MAWS's test/endpoint/rl10/conversation.json
copied byte for byte, its commit and git blob named beside it in
rl10-conversation.source.json, which the replay checks first.

This process stands in for the endpoint on a Unix socket in a temporary
HOME, SMINOS_HOME and MAWS_USER_DATA, and runs sminos's own uplink (the RL10
loop, `sminos_uplink.run_rl10`) in it, against one machine staged as the
conversation's: the projects P (relayed) and Q (local), the sessions S1-S5 as
the engine's registry records of live processes, each with its inbox served,
and the bridges' children of S1 and S2, each under its launch, the records, the log's events, the RPC
ledger. Cases run in order, each on the last's state. A `down` line is sent
as written, its bindings this run's; an `up` line is a line sminos must send
on that connection: the first not matched before that equals it, bindings
substituted and each `vary` path compared for presence. What sminos does with
a down line is checked where it shows (a file, a delivery, a spent position).
`scene` and `quiet` are the endpoint's, and passed by, but for the two
scenes that bind what later lines name (SCENES: `add-machine`, another
machine of the org, its ref and key id; `machine-event`, an event of one of
its sessions as the endpoint sends it down, signed and attested). A thread
id is minted here, so the fixture's literal at a `vary`'d `thread` stands
for the one sminos sent, and a later line naming it names that. A `words?`
the conversation does not stage is answered `refuse` at once, so a session's
later owed events are asked as the conversation stages them. The only
`reach?` lines the conversation stages are case 14's, about a channel's
requests, which are left for their steps; every other one sminos asks
before a peer push (P5 O18 D3: its endpoint advertises `reach`) is
answered `deliver` at once, the push the conversation expects then made.

One kind of line is not sminos's to send as written, named in a table below
with its reason: PROBES, lines the endpoint's suite plays as a sminos would
that misbehaves (another body at a stored position, a `created` of its own,
a `words?` naming no project, for a session not addressed or not a member,
or for a revoked signer's event). Neither the probe nor the endpoint's
answer to it is played here; what sminos does instead is checked over the
whole conversation: it never sends such a line. Every other line is
sminos's as written: the fixture carries the threads' lines (T1) and the
declared channel's (CH1's M6, its case 13, staged by registering the
channel under the fixture's id and name and placing S1 by its own change),
and a channel's requests across machines (CH1's M7, case 14, the
fifteenth, which CH1's review calls case 15, staged by narrowing S2 and
then S1 to private before the request naming each arrives), and a channel's
messages (CH2's M7, cases 15 to 18: S7 and S8, S10 and S9 staged as live
sessions of P, each but S7 placed in the channel by its own change and S10
and S9 given their reach in one change of the record; the three writes made
through sminos's own `say`, its clock held at the fixture's `ts`; a thread id
the fixture names for a session of this machine bound to the one sminos
minted for it, bind_threads), and the endpoint's `audience` for each local
session, sent down after the member frame that states it (its members and
digest as the fixture pins them: the member ids are the fixture's, and the
digest is the endpoint's input, never this code's to make), and nothing is
amended here. What is checked
over the whole conversation in place of the probes is rl10_probes.py's,
built for a conversation of several logs.

Prints one `ok` or `FAIL` line per line of the conversation it plays, for
run-sminos-tests.sh to count, and exits 1 when one fails.

    python3 -B rl10_conformance.py <skills/sminos/scripts> <rl10-conversation.json>
"""

import copy
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from unittest import mock

SCRIPTS = os.path.abspath(sys.argv[1])
FIXTURE = os.path.abspath(sys.argv[2])
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.realpath(tempfile.mkdtemp(prefix="smc.", dir="/tmp"))   # short: a Unix socket's path is bounded
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "SMINOS_LAUNCH",
            "SMINOS_DESK_MEMBER", "SMINOS_DESK_PROOF"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "h"), SMINOS_HOME=os.path.join(BASE, "s"),
                  MAWS_USER_DATA=os.path.join(BASE, "m"), SMINOS_DERIVE_EVERY="0")
# A desk spawn runs `claude --bg`: here a `claude` that refuses, so nothing real starts.
SHIMS = os.path.join(BASE, "bin")
os.makedirs(SHIMS)
with open(os.path.join(SHIMS, "claude"), "w") as f:
    f.write("#!/bin/sh\necho 'claude is not run by the conformance replay' >&2\nexit 1\n")
os.chmod(os.path.join(SHIMS, "claude"), 0o755)
os.environ["PATH"] = SHIMS + os.pathsep + os.environ.get("PATH", "")
for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
    os.makedirs(d, mode=0o700)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import endpoint_standin  # noqa: E402 — its connection's reads and writes
import rl10_probes as probes  # noqa: E402 — what is checked in place of the probes
import sminos  # noqa: E402
import sminos_bridge as bridge  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

CLI = os.path.join(SCRIPTS, "sminos")
WAIT = 30.0          # how long an `up` line is waited for
DEADLINE = 600.0     # the whole replay
STARTED = time.monotonic()
FAILED = []
CHILDREN = []        # processes this replay started, ended at its end


def say(status, name):
    for secret in ("token", "wrongToken", "legacyKey"):   # B, once the bindings are made
        if secret in globals().get("B", {}):
            name = name.replace(B[secret], "<%s>" % secret)
    print("%s %s" % (status, name), flush=True)
    if status == "FAIL":
        FAILED.append(name)


def iso(t=None):
    return endpoint_standin.iso(t)


def wait_for(pred, timeout=WAIT, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


def daemon_log():
    try:
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            return f.read()
    except OSError:
        return ""


# ------------------------------------------------------------- the fixture


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


with open(FIXTURE, "rb") as f:
    RAW = f.read()
with open(os.path.join(os.path.dirname(FIXTURE), "rl10-conversation.source.json")) as f:
    SOURCE = json.load(f)
if git_blob(RAW) == SOURCE["blob"]:
    say("ok", "the fixture is MAWS %s's %s, byte for byte (blob %s)" % (SOURCE["commit"][:9], SOURCE["path"],
                                                                         SOURCE["blob"][:9]))
else:
    say("FAIL", "the fixture is not MAWS %s's %s: its blob is %s, not %s" % (
        SOURCE["commit"][:9], SOURCE["path"], git_blob(RAW), SOURCE["blob"]))
CONVERSATION = json.loads(RAW)
CASES = CONVERSATION["cases"]


# ------------------------------------------------------------- bindings


B = dict(CONVERSATION["bindings"])   # the sample values; this run's replace them where they are its own
B.update(token=os.urandom(32).hex(), wrongToken=os.urandom(32).hex(),
         legacyKey=codes.b64url(os.urandom(32)))
# An RPC's time (`created:<as>`): its own when it goes down.
LAZY = tuple(sorted({k for k in B if k.startswith("created:")} |
                    {m.decode() for m in re.findall(rb"\{\{(created:[^}]+)\}\}", RAW)}))
for k in LAZY:
    B.pop(k, None)
IDS = {}   # a literal id the fixture names in a `vary`'d path → the id sminos sent


def subst(x):
    """A fixture value with this run's bindings: a string that is one binding
    whole takes the binding's value (an object, for words:b1); a string
    holding bindings has each replaced; a literal id a matched line bound
    (IDS) is the id sminos sent."""
    if isinstance(x, dict):
        return {subst(k): subst(v) for k, v in x.items()}
    if isinstance(x, list):
        return [subst(v) for v in x]
    if not isinstance(x, str):
        return x
    if x in IDS:
        return IDS[x]
    if x.startswith("{{") and x.endswith("}}") and x.count("{{") == 1:
        return copy.deepcopy(binding(x[2:-2]))
    while "{{" in x:
        start = x.index("{{")
        end = x.index("}}", start)
        x = x[:start] + str(binding(x[start + 2:end])) + x[end + 2:]
    return x


def binding(name):
    if name not in B and name in LAZY:
        B[name] = iso()
    return B[name]


def path_get(d, path):
    for part in path.split("."):
        if isinstance(d, list) and part.isdigit() and int(part) < len(d):
            d = d[int(part)]
        elif isinstance(d, dict) and part in d:
            d = d[part]
        else:
            raise KeyError(path)
    return d


def path_drop(d, path):
    """`d` without the value at `path` (a copy); KeyError when it has none."""
    d = copy.deepcopy(d)
    parts = path.split(".")
    parent = path_get(d, ".".join(parts[:-1])) if len(parts) > 1 else d
    last = parts[-1]
    if isinstance(parent, list) and last.isdigit() and int(last) < len(parent):
        parent[int(last)] = None
    elif isinstance(parent, dict) and last in parent:
        del parent[last]
    else:
        raise KeyError(path)
    return d


def matches(expected, actual, vary=()):
    """Whether a line sminos sent is the expected one: equal once each `vary`
    path is taken out of both, present in the line."""
    try:
        for p in vary:
            actual = path_drop(actual, p)
            try:
                expected = path_drop(expected, p)
            except KeyError:
                pass
    except KeyError:
        return False
    return expected == actual


# ------------------------------------------------------------- the endpoint's side


class Endpoint:
    """The replay's socket: every connection sminos makes, in order, each
    line it sends kept with its connection, parts joined."""

    def __init__(self):
        self.dir = os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint")
        os.makedirs(self.dir, mode=0o700)
        self.path = os.path.join(self.dir, "rl10.sock")
        self.cv = threading.Condition()
        self.accepted = []   # connections, in the order sminos made them
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.path)
        os.chmod(self.path, 0o600)
        self.listener.listen(8)
        threading.Thread(target=self.accept, daemon=True).start()

    def rl10(self, token):
        endpoint_standin.write_private(os.path.join(self.dir, "rl10.json"),
                                       {"socket": self.path, "pid": os.getpid(), "build": B["build"],
                                        "token": token, "protocol": 1})

    def accept(self):
        while True:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                return
            conn = endpoint_standin.Conn(len(self.accepted) + 1, sock)
            conn.frames = []
            with self.cv:
                self.accepted.append(conn)
                self.cv.notify_all()
            threading.Thread(target=self.read, args=(conn,), daemon=True).start()

    def read(self, conn):
        while True:
            try:
                line = conn.read_line()
            except (OSError, ValueError):
                line = None
            if line is None:
                return
            try:
                frame = conn.joined(json.loads(line))
            except ValueError:
                frame = {"t": None, "line": line}
            if frame is not None:
                with self.cv:
                    conn.frames.append(frame)
                    self.cv.notify_all()


EP = Endpoint()
CONNS = {}          # a conversation's connection name → the connection it names now
MATCHED = set()     # (connection number, index) of the lines matched
TAKEN = 0           # how many accepted connections the conversation has opened


def conn_of(step):
    return CONNS[step.get("conn", "main")]


def find(conn, pred, timeout=WAIT, after=-1):
    """The index of the first line on `conn` past `after`, not matched yet,
    that `pred` holds of, waiting for it; None at the timeout."""
    end = time.monotonic() + timeout
    with EP.cv:
        while True:
            for i, f in enumerate(conn.frames):
                if i > after and (conn.number, i) not in MATCHED and pred(f):
                    return i
            left = end - time.monotonic()
            if left <= 0:
                return None
            EP.cv.wait(min(left, 0.1))
            answer_unstaged(conn)


# ------------------------------------------------------------- the machine


class Mod:
    """A session's bridge module, as test_rpcs' stands in for bridge.tsx:
    the real bridge child (`sminos bridge --session --launch`), its commands
    answered — a delivery submitted, then entered as a row, a steer taken."""

    def __init__(self, sid, launch):
        self.sid, self.launch = sid, launch
        self.delivered = []
        self.entered = []   # the uuid of the row each delivery became
        self.ops = []
        self.proc = subprocess.Popen([CLI, "bridge", "--session", sid, "--launch=" + launch],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        CHILDREN.append(self.proc)
        hello = json.loads(self.proc.stdout.readline())
        self.sock, self.nonce = hello["socket"], hello["nonce"]
        threading.Thread(target=self.drain, daemon=True).start()
        self.post({"type": "session", "phase": "start", "session": sid, "cwd": "/", "t": 0},
                  {"type": "resync", "turns": [], "streaming": [], "agents": [], "cut": hello.get("seed") or {},
                   "t": 0})

    def drain(self):
        with self.proc.stdout:
            for line in self.proc.stdout:
                cmd = json.loads(line)
                op = cmd.get("op")
                self.ops.append(op)
                if op == "deliver":
                    self.delivered.append(cmd["text"])
                    self.post({"type": "delivered", "key": cmd["key"], "outcome": "submitted"},
                              {"type": "result", "id": cmd["id"], "op": op, "ok": True, "result": {"submitted": True}})
                    self.entered.append(str(uuid.uuid4()))
                    self.post({"type": "delivered", "key": cmd["key"], "outcome": "entered", "uuid": self.entered[-1]})
                elif op == "steer":
                    self.post({"type": "result", "id": cmd["id"], "op": op, "ok": True,
                               "result": {"row": str(uuid.uuid4())}})
                elif op == "read" and cmd.get("what") == "status":
                    self.post({"type": "result", "id": cmd["id"], "op": op, "ok": True,
                               "result": {"cwd": "/", "root": "/", "model": None}})
                elif op not in ("hello", "lane") and cmd.get("id") is not None:
                    self.post({"type": "result", "id": cmd["id"], "op": op, "ok": False, "error": "not here"})

    def post(self, *events):
        c = bridge._UnixConnection(self.sock, 10)
        try:
            c.request("POST", "/events", body=json.dumps(list(events)).encode(),
                      headers={"content-type": "application/json", bridge.NONCE_HEADER: self.nonce})
            c.getresponse().read()
        finally:
            c.close()

    def raise_(self, rid, tool, tool_input, at):
        self.post({"type": "raised", "request": rid, "tool": tool, "input": tool_input, "agentId": None,
                   "t": int(at * 1000)})

    def settle(self, rid):
        self.post({"type": "settled", "request": rid, "winner": "terminal", "outcome": "allow", "by": "terminal",
                   "t": int(time.time() * 1000)})

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)

    def texts(self):
        return "\n".join(self.delivered)


def git(*args, cwd=None):
    subprocess.run(["git", "-c", "init.defaultBranch=main", *args], cwd=cwd, check=True, capture_output=True)


def project(name, hub):
    root = os.path.join(BASE, "w-" + name)
    git("init", "-q", root)
    r = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, "sminos.py"), "project", "init", "--name", name],
                       cwd=root, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("project init %s: %s" % (name, r.stderr))
    if hub:
        smns = os.path.join(root, ".smns")
        with open(smns) as f:
            d = json.load(f)
        d["hub"] = {"url": B["hub"], "org": B["org"]}
        with open(smns, "w") as f:
            json.dump(d, f)
    sminos.forget_caches()
    p = sminos.resolve_project(root)
    sminos.project_path(p, "log")
    return p


SESSIONS = {}   # session → (its processes, its registry record's path)
STAGED = []     # every session staged on this machine, in order, an ended one too: the members a words? may name


def session(p, sid, alias):
    """A live session: its process, and its inbox served (inbox_standin.py),
    which is what makes a peer live to delivery (sminos.peer_live)."""
    proc = subprocess.Popen(["sleep", "3600"])
    sock = os.path.join(BASE, "in-%s.sock" % sid[:8])
    inbox = subprocess.Popen([sys.executable, "-B", os.path.join(HERE, "inbox_standin.py"), sock, sock + ".received"])
    CHILDREN.extend((proc, inbox))
    if not wait_for(lambda: os.path.exists(sock), timeout=10):
        raise RuntimeError("%s's inbox never listened" % alias)
    path = os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % proc.pid)
    with open(path, "w") as f:
        json.dump({"pid": proc.pid, "sessionId": sid, "name": alias, "nameSource": "user", "cwd": p.root,
                   "kind": "interactive", "status": "idle", "messagingSocketPath": sock}, f)
    SESSIONS[sid] = ((proc, inbox), path)
    STAGED.append(sid)


def end_session(sid):
    procs, path = SESSIONS.pop(sid)
    for proc in procs:
        proc.kill()
        proc.wait(10)
    os.unlink(path)


def append_at(p, writer, ts, kind, **fields):
    """An event as `_append` writes it (its receipt too), at the time the
    fixture names: sminos's clock held there for the one append."""
    with mock.patch.object(sminos, "now", lambda ms=False: ts):
        return sminos.log_append(p, writer, kind, **fields)


def own(writer_rest):
    return "%s/%s" % (B["name"], writer_rest)


def held(p, writer):
    path = sminos.writer_path(p, writer)
    return hublog.read_events(path) if os.path.exists(path) else []


def spent(p):
    return hublog.HubLog(p, {"key": None, "machine": B["name"]}).spent()


def stage_machine():
    """The conversation's machine before its first connection: named
    rl10-host (DAEMON_HOST, set before any project or writer is made, since
    no identity.json names it until the welcome), hub.json holding the DX1
    key the endpoint asks for (org-local), P (relayed, named maws, its
    checkout on main) and Q (local), S1-S5 with their records, titles and
    bridges, P's own events of case 4, the ledger's entry from before RL10."""
    os.environ["DAEMON_HOST"] = B["name"]
    sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json"),
                      {"hub": B["hub"], "org": B["org"], "machine": B["name"], "client_id": "c", "client_secret": "s",
                       "key": B["legacyKey"], "former": {}, "enrolled": B["enrolled"]}, mode=0o600)
    sminos.forget_caches()
    P = project("maws", hub=True)
    Q = project("local", hub=False)
    B.update({"repo": os.path.basename(P.root), "checkout:Q": Q.root, "configDir": os.path.join(os.environ["HOME"], ".claude")})
    B.update({"project:P": P.id, "project:Q": Q.id, "checkout": P.root,
              "project:machine": sminos.machine_project_id(B["org"], B["name"])})
    for name, alias in (("S1", "main"), ("S2", "bob"), ("S3", "lane-b"), ("S4", "unbridged")):
        session(P, B["session:" + name], alias)
    session(Q, B["session:S5"], "local")
    records = sminos.records_module()
    records.establish(B["session:S2"], {**records.default_provenance("launch"), "owners": [B["member:B"]],
                                        "principal": B["member:B"],
                                        "origin": {"kind": "maws", "requester": B["member:B"]}})
    records.establish(B["session:S3"], {**records.default_provenance("hook"), "origin": {"kind": "maws"}})
    sminos.reconcile(P)
    sminos.reconcile(Q)
    sminos.lifecycle(P, B["session:S1"], "titled", title="the main session")
    MODS["S1"] = Mod(B["session:S1"], B["launch:L1"])
    MODS["S2"] = Mod(B["session:S2"], B["launch:L2"])
    # Each bridge child relays its launch's lane to the record on a thread of its own: S2, the engine host's
    # launch (lane B at its join), turns lane A, and the reconciliation after adopts it as a thread with a second
    # joined, stamped (case 4's upload).
    for name in ("S1", "S2"):
        if not wait_for(lambda name=name: (records.read(B["session:" + name]) or {}).get("controller"), timeout=10):
            raise RuntimeError("%s's bridge never relayed its lane" % name)
    sminos.forget_caches()
    sminos.reconcile(P)
    # Case 4's own events: the operator's words to S1, as _append writes
    # them (the fixture's, "taken from a real sminos log"), and S1's say.
    append_at(P, own("human"), "2026-10-27T18:02:11.482Z", "human",
              **{"from": "human", "to": [{"session": B["session:S1"], "alias": "main"}], "text": "run the tests"})
    append_at(P, sminos.writer_id(B["session:S1"]), "2026-10-27T18:02:12.001Z", "say",
              **{"from": "main", "to": "*", "text": "tests pass"})
    # An entry an older daemon wrote, before RL10: no binding (case 10).
    now = time.time()
    sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", "rpcs.json"), {
        "ZHgyLWVyYS1vcC0wMDAwMDAwMQ": {"project": P.id, "rpc": "steer", "session": B["session:S1"], "created": now,
                                       "at": now, "nonce": "ZHgyLWVyYS1ub25jZQAAAA", "op_created": now,
                                       "outcome": {"state": "done", "result": {}}, "done_at": now, "acked": True}})
    return P, Q


MODS = {}


def device_words(seq, device, text, to):
    """A person's words, signed by one of member B's devices, as the endpoint
    sends them down (the event with its sig): the binding words:<device>."""
    return {"ts": "2026-10-27T18:04:%02d.000Z" % seq, "writer": "hub/" + B["member:B"], "seq": seq, "kind": "human",
            "from": "human", "member": B["member:B"], "to": to, "text": text,
            "created": "2026-10-27T18:04:%02d.000Z" % seq, "sig": {"kid": B["kid:" + device], "value": "AQ"}}


# ------------------------------------------------------------- the staging, step by step


def stage_open_main():
    EP.rl10(B["token"])


def stage_read_only(on):
    def stage():
        r = subprocess.run([CLI, "daemon", "policy", "--read-only", "on" if on else "off"], capture_output=True,
                           text=True)
        if r.returncode:
            raise RuntimeError("daemon policy: %s" % r.stderr)
    return stage


def stage_whole_second():
    append_at(P_, own("human"), "2026-10-27T18:02:13Z", "human",
              **{"from": "human", "to": "*", "text": "an older log's whole second"})


def recipients(name, alias):
    return [{"session": B["session:" + name], "alias": alias}]


def stage_operator_words():
    # Seqs 3-6 to no one (the fixture's 3 was refused, never stored), past
    # the spent 7 and 8 to 9.
    for n in range(3, 7):
        append_at(P_, own("human"), "2026-10-27T18:02:%02d.000Z" % (20 + n), "human",
                  **{"from": "human", "to": [], "text": "nobody's %d" % n})
    e = append_at(P_, own("human"), "2026-10-27T18:03:00.000Z", "human",
                  **{"from": "human", "to": recipients("S1", "main"), "text": "asked while RL1 is down"})
    if e["seq"] != 9:
        raise RuntimeError("the operator's words went to seq %d, not 9" % e["seq"])


def stage_unrelayed():
    append_at(Q_, own("human"), "2026-10-27T18:03:01.000Z", "human",
              **{"from": "human", "to": recipients("S5", "local"), "text": "a project the endpoint doesn't relay"})


def stage_device_words():
    B["words:b1"] = device_words(1, "b1", "from b1", [{"session": B["session:S2"], "alias": "bob"},
                                                      {"session": B["session:S1"], "alias": "main"}])
    B["words:b2"] = device_words(4, "b2", "from b2", [{"session": B["session:S2"], "alias": "bob"}])
    B["words:b3"] = device_words(6, "b3", "from b3", [{"session": B["session:S2"], "alias": "bob"}])


def stage_host():
    writer = sminos.writer_id(B["session:S1"])
    path = sminos.store_path(P_, sminos.HOST_STORE, writer)
    with open(path, "a") as f:
        f.write(json.dumps({"ts": "2026-10-27T18:06:00.000Z", "writer": writer, "seq": 1, "kind": "message",
                            "from": "main", "text": "the build is green"}) + "\n")


def stage_raise():
    MODS["S1"].raise_("req-1", "Bash", {"command": "ls"}, sminos._ts_epoch("2026-10-27T18:06:01.000Z"))


def stage_relaunch():
    """S1 relaunched under L1b with its request pending again, after the
    decision was admitted: the new launch's child holds the request the
    digest names, so the decision reaches its fence."""
    MODS["S1"].stop()
    MODS["S1"] = Mod(B["session:S1"], B["launch:L1b"])
    MODS["S1"].raise_("req-1", "Bash", {"command": "ls"}, time.time())
    B["proof:spawn"] = {"t": "action", "action": "sminos.spawn", "member": B["member:A"], "device": B["device:a1"],
                        "args": {"checkout": B["checkout"], "brief": "fix the flake"}, "sig": {"kid": "k-a1",
                                                                                              "value": "AQ"}}


def stage_restart():
    """While the endpoint is down: S1's request settled, S3 and S4 ended."""
    MODS["S1"].settle("req-1")
    for name in ("S3", "S4"):
        end_session(B["session:" + name])


def stage_ask(rid):
    """Case 12: S1 raises a question with its project open, each going up alone."""
    return lambda: MODS["S1"].raise_(rid, "Bash", {"command": "ls"}, time.time())


def stage_answer(rid):
    return lambda: MODS["S1"].settle(rid)


PLACE = r"""
import sys
sys.path.insert(0, sys.argv[1])
import sminos, sminos_channels as channels, sminos_threads as threads
cid, name, op, sid = sys.argv[2:6]
if sminos.known_project(cid) is None:
    channels.register(cid, name)
t = threads.current_record(sid)
out = channels.change(t["thread"], cid, op, sid)
if out.state != "applied":
    sys.exit("%s %s" % out)
"""


def stage_channel(op):
    """Case 13: the channel registered under the fixture's own id and name, as
    the org's directory registers one, and S1 placed in it (`add`) or taken
    out (`remove`) by its own change (sminos_channels.change), in a process
    of its own, as a verb runs: a statement in P's log and nothing in the
    channel's, whose hello's `have` is {}."""
    def stage():
        r = subprocess.run([sys.executable, "-B", "-c", PLACE, SCRIPTS, B["channel:C"], "desk-integration", op,
                            B["session:S1"]], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("S1's own %s of the channel: %s" % (op, r.stderr.strip()))
    return stage


def stage_private(name):
    """Case 14: S2, then S1, made private with no share by a terminal's
    narrowing (`sminos access`), before the request naming it arrives: its
    member frame then carries the reach the endpoint judges the request by."""
    def stage():
        alias = {"S1": "main", "S2": "bob"}[name]
        r = subprocess.run([CLI, "access", alias, "private"], capture_output=True, text=True, cwd=P_.root)
        if r.returncode:
            raise RuntimeError("sminos access %s private: %s" % (alias, r.stderr.strip()))
    return stage


SAY = r"""
import sys
sys.path.insert(0, sys.argv[1])
import sminos
ts = sys.argv[2]
sminos.now = lambda ms=False: ts
sminos.main(sys.argv[3:])
"""

REACH = r"""
import sys
sys.path.insert(0, sys.argv[1])
import sminos
sid, access, member, grade = sys.argv[2:6]
sminos.sibling_module("sminos_visibility").set_visibility(sid, access=access, share=(member, grade) if member else None,
                                                          operator=True)
"""


def say_at(ts, args, sid=None):
    """A `sminos say` through its own door, as a session (`sid`) or a person
    at a terminal runs it, in a process of its own, sminos's clock held at
    the fixture's `ts` for it (append_at's hold, for a verb)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
    if sid:
        env["CLAUDE_CODE_SESSION_ID"] = sid
    r = subprocess.run([sys.executable, "-B", "-c", SAY, SCRIPTS, ts, "say", *args], capture_output=True, text=True,
                       cwd=P_.root, env=env)
    if r.returncode:
        raise RuntimeError("sminos say %r: %s" % (args, r.stderr.strip()))


def stage_member(name, alias, placed=True, access=None, share=None):
    """Cases 16 to 18: a live session of P (session()), joined as a thread,
    placed in the channel by its own change when `placed`, then its reach
    set in one change of the record (set_visibility, as the app's record
    act sets it: one policyRev), when `access` is given."""
    def stage():
        sid = B["session:" + name]
        session(P_, sid, alias)
        sminos.forget_caches()
        sminos.reconcile(P_)
        if placed:
            r = subprocess.run([sys.executable, "-B", "-c", PLACE, SCRIPTS, B["channel:C"], "desk-integration", "add",
                                sid], capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError("%s's own add to the channel: %s" % (name, r.stderr.strip()))
        if access:
            member, grade = share or ("", "")
            r = subprocess.run([sys.executable, "-B", "-c", REACH, SCRIPTS, sid, access, member, grade],
                               capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError("%s's reach: %s" % (name, r.stderr.strip()))
    return stage


CARRY = r"""
import sys
sys.path.insert(0, sys.argv[1])
import sminos
sminos.channels_module().carry_words(sminos.known_project(sys.argv[2]))
"""


def stage_carried():
    """The words the uplink kept for the channel's messages carried out, as
    the daemon's channel pass carries them (sminos_channels.carry_words), in
    a process of its own: the replay runs the uplink alone, and a writer's
    next message to a thread is asked about only once its last is settled."""
    r = subprocess.run([sys.executable, "-B", "-c", CARRY, SCRIPTS, B["channel:C"]], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("carrying out the channel's kept words: %s" % r.stderr.strip())


def stage_both(*stages):
    return lambda: [stage() for stage in stages]


STAGE = {(0, 3): stage_open_main, (2, 0): stage_read_only(True), (2, 2): stage_read_only(False),
         (4, 13): stage_whole_second, (6, 6): stage_operator_words, (6, 8): stage_unrelayed,
         (8, 0): stage_host, (8, 2): stage_raise, (9, 5): stage_relaunch,
         (11, 3): stage_restart, (12, 0): stage_ask("req-3"), (12, 2): stage_ask("req-4"),
         (12, 4): stage_answer("req-3"), (12, 6): stage_answer("req-4"),
         (13, 0): stage_channel("add"), (13, 4): stage_channel("remove"),
         (14, 3): stage_private("S2"), (14, 9): stage_private("S1"),
         (15, 0): stage_both(stage_member("S8", "integrator"), stage_member("S7", "scout", placed=False)),
         (15, 4): lambda: say_at("2026-10-27T18:10:00.000Z",
                                 ["--in", "desk-integration", "@integrator the fixture case is ready for review"],
                                 B["session:S7"]),
         (16, 4): stage_member("S10", "solo", access="private"),
         (17, 0): stage_member("S9", "review", access="private", share=(B["member:B"], "converse")),
         (17, 10): lambda: say_at("2026-10-27T18:11:00.000Z",
                                 ["--in", "desk-integration", "@integrator pick up the channel's review"]),
         (18, 0): stage_both(stage_carried,
                             lambda: say_at("2026-10-27T18:12:00.000Z",
                                            ["--notice", "ci-watch", "--in", "desk-integration",
                                             "@integrator the integration build failed"]))}


# The endpoint's scenes that bind what later lines name: another machine of
# the org (its ref and key id) and an event of one of its sessions, signed
# over a log and attested, as the endpoint sends it down (the binding the
# scene names). Every other scene is the endpoint's alone, and passed by.
def scene_add_machine(step):
    B["ref:" + step["name"]] = codes.b64url(os.urandom(16))
    B["kid:" + step["name"]] = codes.b64url(os.urandom(16))


def scene_machine_event(step):
    B[step["binding"]] = probes.machine_event(step, iso(), B["kid:" + step["machine"]])


def scene_device_words(step):
    """A person's words written into a channel's log by one of member B's
    devices, as the endpoint sends them down, owed to the scene's thread
    when it names one (case 18). The device words of cases 7 and 11, in P's
    log, are bound before the replay begins (stage_device_words)."""
    if "project" not in step:
        return
    at = iso()
    entry = {"session": step["session"], "alias": step["alias"], **({"thread": step["thread"]} if "thread" in step else {})}
    B[step["binding"]] = {"ts": at, "writer": "hub/" + B["member:B"], "seq": step["seq"], "kind": "human",
                          "from": "human", "member": B["member:B"], "to": [entry],
                          "text": "@%s from %s, into the channel" % (step["alias"], step["device"]), "created": at,
                          "sig": {"kid": B["kid:" + step["device"]], "value": "AQ"}}


SCENES = {"add-machine": scene_add_machine, "machine-event": scene_machine_event, "device-words": scene_device_words}


def bind_threads(x):
    """A thread id the fixture names for a session of this machine (an entry
    of `to`: its `session` and `thread`; an event: its `writer`'s session and
    `thread`) stands for the one sminos minted for that session's thread, as
    a `vary`'d `thread` does (IDS); another machine's literal stays as it is."""
    if isinstance(x, list):
        for v in x:
            bind_threads(v)
        return
    if not isinstance(x, dict):
        return
    for v in x.values():
        bind_threads(v)
    lit = x.get("thread")
    if not isinstance(lit, str) or "{{" in lit or lit in IDS:
        return
    ref = x.get("session")
    if not isinstance(ref, str) and isinstance(x.get("writer"), str):
        ref = x["writer"].rpartition("/")[2]
    try:
        sid = subst(ref) if isinstance(ref, str) else None
    except KeyError:
        return
    if sid in STAGED:
        t = sminos.threads_module().current_record(sid, fresh=True)
        if t is not None:
            IDS[lit] = t["thread"]


# ------------------------------------------------------------- what sminos did with a down line


def check_no_identity():
    time.sleep(0.5)
    return not os.path.exists(rl10.identity_path()), "no identity.json after a closed connection"


def check_identity():
    got = wait_for(lambda: os.path.exists(rl10.identity_path()) and json.load(open(rl10.identity_path())))
    want = {"org": B["org"], "hub": B["hub"], "name": B["name"], "ref": B["ref"], "enrolled": B["enrolled"],
            "former": {}}
    return got and {k: got.get(k) for k in want} == want, "identity.json is the welcome's: %r" % got


def check_revoked(version, devices=()):
    def check():
        got = wait_for(lambda: (rl10.revoked().get("version") == version and rl10.revoked()) or None, timeout=10)
        return got and set(devices) <= set(got["devices"]), "revoked.json at version %d: %r" % (version, got)
    return check


def check_org():
    got = wait_for(lambda: os.path.exists(sminos.org_path()) and json.load(open(sminos.org_path())))
    return got and [p["id"] for p in got["projects"]] == [B["project:machine"]], "org.json: %r" % got


def check_policy(read_only):
    def check():
        return wait_for(lambda: policy.machine_policy()["read_only"] is read_only, timeout=10), \
            "the machine's policy is the endpoint's: read_only %s" % read_only
    return check


def check_present():
    before = open(sminos.writer_path(P_, own("human")), "rb").read()
    time.sleep(0.5)
    rejected = [f for f in CONNS["main"].frames if f.get("t") == "rejected"]
    return open(sminos.writer_path(P_, own("human")), "rb").read() == before and not rejected, \
        "the echo is present: the log as it was, nothing rejected"


def check_spent(p, writer, seq):
    def check():
        # Both waited on: the spend saves the position before it writes its line.
        line = "%s:%d in %s" % (writer, seq, p.name)
        got = wait_for(lambda: seq in spent(p).get(writer, set()) and line in daemon_log(), timeout=10)
        return got, "%s spent, said in daemon.log" % line
    return check


def check_delivered(name, text):
    def check():
        return wait_for(lambda: text in MODS[name].texts(), timeout=10), \
            "%s's bridge took %r as the person's words (it took %r; its ops %r)" % (
                name, text, MODS[name].delivered, MODS[name].ops)
    return check


def check_stored(writer, seq, signer_kind):
    def check():
        got = wait_for(lambda: next((e for e in held(P_, writer) if e["seq"] == seq), None), timeout=10)
        return got and got.get("verified", {}).get("signer", {}).get("kind") == signer_kind, \
            "%s:%d stored with its verified signer: %r" % (writer, seq, got)
    return check


def check_vector(writer, seq):
    def check():
        return wait_for(lambda: hublog.HubLog(P_, {"key": None, "machine": B["name"]})
                        .vector().get(writer, 0) >= seq, timeout=10), "the vector of %s is past %d" % (writer, seq)
    return check


def check_spawn():
    def entry():
        try:
            return json.load(open(os.path.join(os.environ["SMINOS_HOME"], "daemon", "rpcs.json"))).get(B["opId:spawn"])
        except (OSError, ValueError):
            return None
    got = wait_for(entry, timeout=10)
    want = {"member": B["member:A"], "device": B["device:a1"], "fingerprint": B["fingerprint:spawn"],
            "target": {"kind": "machine"}, "proof": B["proof:spawn"]}
    return got and {k: got.get(k) for k in want} == want, "the spawn's ledger entry is bound to its sender: %r" % (
        got and {k: got.get(k) for k in want})


def check_send_entered():
    """The send's outcome (a `vary` the fixture leaves open) is the row it
    became: S1's bridge took the text once, under the send's writer, and
    the result names the uuid its `delivered` gave."""
    conn, i = STEPS[(9, 13)]
    got = CONNS["main"].frames[i]["outcome"] if CONNS["main"].number == conn else None
    mod = MODS["S1"]
    want = {"state": "done", "result": {"entered": True, "uuid": mod.entered[-1] if mod.entered else None}}
    return got == want and mod.delivered.count("and count them") == 1, \
        "answered %r, S1 took %r" % (got, mod.delivered)


def check_request(name, binding, placed):
    """Case 14: what the endpoint's word did, in the target's record (its
    statement waits for the private session's audience): the request
    answered there, and the thread in the channel exactly when it was
    `deliver`."""
    def check():
        import sminos_threads as threads

        def answered():
            t = threads.current_record(B["session:" + name], fresh=True)
            ids = [a[1] for a in (t or {}).get("answered") or [] if isinstance(a, list) and a[0] == B["channel:C"]]
            return t if B[binding]["id"] in ids else None
        t = wait_for(answered, timeout=10)
        return t is not None and (B["channel:C"] in threads.held_set(t)) is placed, \
            "%s's record answered %s, %s the channel: %r" % (
                name, binding, "in" if placed else "not in", t and (t.get("channels"), t.get("answered")))
    return check


CHECK = {(0, 2): check_no_identity, (0, 5): check_identity, (0, 6): check_revoked(3), (0, 7): check_org,
         (2, 1): check_policy(True), (2, 3): check_policy(False), (5, 1): check_present,
         (6, 1): check_delivered("S1", "run the tests"), (6, 7): check_delivered("S1", "asked while RL1 is down"),
         (7, 13): check_delivered("S2", "from b1"), (11, 42): check_delivered("S2", "from b2"),
         (11, 7): check_revoked(3), (11, 32): check_revoked(4),
         (11, 35): check_revoked(5, ["b1"]), (9, 13): check_send_entered, (14, 1): check_revoked(6, ["b1"]),
         (14, 7): check_request("S2", "request:R1", True), (14, 13): check_request("S1", "request:R2", False)}


def late_checks(P):
    hub_b = "hub/" + B["member:B"]
    CHECK.update({(5, 3): check_spent(P, own("human"), 7), (5, 7): check_spent(P, own("human"), 8),
                  (7, 1): check_stored(hub_b, 1, "device"), (7, 3): check_spent(P, hub_b, 2),
                  (7, 7): check_stored("old-mini/human", 1, "legacy"), (7, 9): check_spent(P, hub_b, 3),
                  (9, 10): check_spawn, (11, 25): check_vector(hub_b, 5),
                  (11, 33): check_stored(hub_b, 6, "device"), (11, 37): check_spent(P, hub_b, 7)})


# ------------------------------------------------------------- probes


def words_lines():
    return [(c.number, f) for c in EP.accepted for f in c.frames if f.get("t") == "words?"]


def uploads():
    """(log id, event) of every event sminos uploaded, under the log its frame named."""
    return [(f.get("project"), e) for c in EP.accepted for f in c.frames if f.get("t") == "events"
            for e in f.get("events", [])]


def upload_events():
    return [e for _, e in uploads()]


def probe_one_body():
    twice = probes.bodies_twice(uploads())
    return not twice, "every position sminos uploaded carries one body (%d positions)%s" % (
        len({(log, e["writer"], e["seq"]) for log, e in uploads()}), "; more than one at %r" % twice if twice else "")


def logs_here():
    """{log id: (writer, seq) → the event this machine stores there, or None}, every log known here."""
    sminos.forget_caches()
    return {p.id: (lambda w, s, p=p: next((e for e in held(p, w) if e["seq"] == s), None))
            for p in sminos.known_logs()}


def probe_no_created():
    carrying = [(e["writer"], e["seq"]) for e in upload_events() if "created" in e]
    return not carrying, "no event sminos uploaded carries a created of its own%s" % (
        ": %r" % carrying if carrying else "")


def addressed(f):
    to = f["event"].get("to")
    return isinstance(to, list) and any(t.get("session") == f["session"] for t in to)


def probe_addressed():
    out = [f["id"] for _, f in words_lines() if not addressed(f)]
    return not out, "every words? names a session the event addresses (%d asked)%s" % (
        len(words_lines()), ": not %r" % out if out else "")


def probe_as_stored():
    wrong = probes.not_as_stored([f for _, f in words_lines()], logs_here())
    return not wrong, "every words? carries its event exactly as stored, its verdict left out%s" % (
        ": not %r" % wrong if wrong else "")


def probe_project():
    out = probes.not_in_its_log([f for _, f in words_lines()], logs_here())
    return not out, "every words? names the project whose log holds its event%s" % (": not %r" % out if out else "")


def probe_members():
    out = probes.not_members([f for _, f in words_lines()], STAGED)
    return not out, "every words? names a member of this machine%s" % (": not %r" % out if out else "")


def probe_revoked():
    restart = EP.accepted[-1].number
    out = probes.asked_again([f for n, f in words_lines() if n == restart], P_.id, "hub/" + B["member:B"], 1)
    return not out, "b1's words are never asked after its device is revoked%s" % (": %r" % out if out else "")


# (case, step) → what sminos does instead, checked over the whole conversation.
PROBES = {
    (4, 11): ("another body at a stored position", probe_one_body),
    (4, 12): ("the endpoint's refusal of it", None),
    (4, 15): ("an event carrying a created of its own", probe_no_created),
    (4, 16): ("the endpoint's refusal of it", None),
    (6, 2): ("an own event asked for a session it does not address", probe_addressed),
    (6, 3): ("the endpoint's answer to it", None),
    (6, 4): ("another body than the one stored", probe_as_stored),
    (6, 5): ("the endpoint's answer to it", None),
    (6, 10): ("a words? naming no project", probe_project),
    (6, 11): ("the endpoint's answer to it", None),
    (7, 16): ("a words? for a session with no member here", probe_members),
    (7, 17): ("the endpoint's answer to it", None),
    (11, 39): ("a revoked signer's words asked again", probe_revoked),
    (11, 40): ("the endpoint's answer to it", None),
}

# A line that says what sminos sent after other lines were: matched only past
# the latest of theirs on its connection. Case 13's frame with no channels
# key is S1's after its removal, not one of the same shape it sent before it
# was placed. A channel's lines wait for what the fixture puts before them
# (probes.order_edges): a session's member frame before an upload to or from
# it and before an ask about it, an own event's upload before an ask about
# it; read off the lines, so a line inserted between them leaves them.
AFTER = {(13, 4): [(13, 2)]}
for _at, _deps in probes.order_edges(CASES).items():
    AFTER[_at] = sorted(set(AFTER.get(_at, [])) | set(_deps))


# ------------------------------------------------------------- unstaged asks


def planned_asks():
    """(project, session, writer, seq) of every words? the conversation has
    sminos send: left for its step."""
    out = set()
    for ci, case in enumerate(CASES):
        for si, step in enumerate(case["steps"]):
            up = step.get("up")
            if isinstance(up, dict) and up.get("t") == "words?" and (ci, si) not in PROBES:
                try:
                    f = subst(up)
                except KeyError:
                    continue
                if isinstance(f.get("event"), dict):
                    out.add((f.get("project"), f["session"], f["event"]["writer"], f["event"]["seq"]))
    return out


def planned_reaches():
    """(project, session) of every reach? the conversation stages (case 14's,
    about a channel's requests): left for its step, never answered here."""
    return {(subst(s["up"].get("project")), subst(s["up"].get("session")))
            for case in CASES for s in case["steps"] if isinstance(s.get("up"), dict) and s["up"].get("t") == "reach?"}


PLANNED = set()
PLANNED_REACH = set()
ANSWERED = set()


def answer_unstaged(conn):
    """Each words? the conversation does not stage, answered `refuse`: its
    event settles, and the session's next owed event is asked. Each reach?,
    which it never stages, answered `deliver`."""
    for i, f in enumerate(conn.frames):
        if f.get("t") == "reach?" and (conn.number, i) not in ANSWERED \
                and (f.get("project"), f.get("session")) not in PLANNED_REACH:
            ANSWERED.add((conn.number, i))
            try:
                conn.write({"t": "reach", "id": f["id"], "verdict": "deliver"})
            except OSError:
                pass
            continue
        if f.get("t") != "words?" or (conn.number, i) in ANSWERED or (conn.number, i) in MATCHED:
            continue
        e = f.get("event") or {}
        if (f.get("project"), f.get("session"), e.get("writer"), e.get("seq")) in PLANNED:
            continue
        ANSWERED.add((conn.number, i))
        try:
            conn.write({"t": "words", "id": f["id"], "verdict": "refuse"})
        except OSError:
            pass


# ------------------------------------------------------------- the replay


def name_of(ci, si, step):
    kind = next(k for k in ("up", "down", "open", "closed") if k in step)
    v = step[kind]
    what = v.get("t") if isinstance(v, dict) else v
    note = step.get("note") or ""
    return "%d.%d %s %s%s" % (ci, si, kind, what, ": " + note if note else "")


def up(ci, si, step, opts):
    conn = conn_of(step)
    want = subst(step["up"])
    vary = step.get("vary", [])
    pred = opts.get("pred") or (lambda f: f.get("t") == want["t"] and matches(want, f, vary))
    i = find(conn, pred, after=probes.after_index(AFTER.get((ci, si), []), STEPS, conn.number))
    if i is None:
        near = [f for f in conn.frames if f.get("t") == want["t"]]
        return False, "no such line on connection %d; expected %s; of its kind sminos sent %s" % (
            conn.number, json.dumps(want)[:600], json.dumps(near[-3:])[:900])
    MATCHED.add((conn.number, i))
    if "id" in vary and isinstance(step["up"].get("id"), str):
        IDS[step["up"]["id"]] = conn.frames[i]["id"]
    for p in vary:
        # A thread's id is minted here: the fixture's literal at a `vary`'d
        # `thread` stands for the one sminos sent, which a later line names.
        if p.rsplit(".", 1)[-1] == "thread":
            literal = path_get(step["up"], p)
            if isinstance(literal, str) and "{{" not in literal:
                IDS[literal] = path_get(conn.frames[i], p)
    STEPS[(ci, si)] = (conn.number, i)
    return True, ""


STEPS = {}   # (case, step) → (connection, index) of the line it matched


def down(step):
    conn = conn_of(step)
    conn.write(subst(step["down"]))
    return True, ""


def open_(step):
    global TAKEN
    with EP.cv:
        while len(EP.accepted) <= TAKEN:
            if not EP.cv.wait(WAIT):
                return False, "sminos made no connection"
        CONNS[step["open"]] = EP.accepted[TAKEN]
        TAKEN += 1
    return True, ""


def closed(step):
    CONNS[step["closed"]].close()
    return True, ""


def check_restated(ci, si):
    """`restated` follows every line of its case's restatement on its
    connection."""
    conn, at = STEPS[(ci, si)]
    later = [k for k, (n, i) in STEPS.items() if k[0] == ci and n == conn and i > at and k != (ci, si)]
    if later:
        return False, "the case's restatement is before restated: not %r" % later
    return True, "the case's restatement is before restated"


def replay():
    global P_, Q_
    P_, Q_ = stage_machine()
    stage_device_words()
    late_checks(P_)
    PLANNED.update(planned_asks())
    PLANNED_REACH.update(planned_reaches())
    EP.rl10(B["wrongToken"])
    halt = threading.Event()
    box = {}
    uplink.WORDS_WAIT = 600.0   # the replay's own pace answers an ask, not a timer
    # The uplink runs in this process; a daemon runs it as a child whose standard error is daemon.log (its
    # supervisor's), so what sminos warns or notes from here on goes there as it would, not into the replay's
    # lines: case 14's private targets, with no audience at their policyRev, have their answers' statements
    # waiting, which sminos says in a warning.
    for name, word in (("warn", "warning"), ("note", "note")):
        mock.patch.object(sminos, name,
                          lambda msg, word=word: sminos.daemon_log("sminos: %s: %s" % (word, msg))).start()
    threading.Thread(target=lambda: box.update(kept=uplink.run_rl10(halt.is_set, halt)), daemon=True).start()
    try:
        for ci, case in enumerate(CASES):
            for si, step in enumerate(case["steps"]):
                if time.monotonic() - STARTED > DEADLINE:
                    say("FAIL", "the replay took more than %d s: stopped at %d.%d" % (DEADLINE, ci, si))
                    return
                if (ci, si) in STAGE:
                    STAGE[(ci, si)]()
                bind_threads(step)
                if "scene" in step or "quiet" in step:
                    if step.get("scene") in SCENES:
                        SCENES[step["scene"]](subst(step))
                        PLANNED.update(planned_asks())   # an ask about the event the scene bound is the conversation's
                    continue
                name = name_of(ci, si, step)
                if (ci, si) in PROBES:
                    continue   # said at the end, with what sminos does instead
                if "up" in step:
                    ok, fail = up(ci, si, step, {})
                elif "down" in step:
                    ok, fail = down(step)
                elif "open" in step:
                    ok, fail = open_(step)
                else:
                    ok, fail = closed(step)
                checked = CHECK.get((ci, si))
                if ok and checked is not None:
                    ok, said = checked()
                    fail = "" if ok else said
                if ok and step.get("up", {}).get("t") == "restated":
                    ok, said = check_restated(ci, si)
                    fail = "" if ok else said
                say("ok" if ok else "FAIL", name + (" — " + fail if not ok else ""))
        time.sleep(1.0)
        for (ci, si), (why, probe) in sorted(PROBES.items()):
            step = CASES[ci]["steps"][si]
            if probe is None:
                say("ok", "%s — the endpoint's alone: its answer to the line before, which sminos never sends"
                    % name_of(ci, si, step))
                continue
            ok, said = probe()
            say("ok" if ok else "FAIL", "%s — the endpoint's alone (%s): %s" % (name_of(ci, si, step), why, said))
        if not FAILED:
            replay_beyond()   # while the uplink still runs: its reads are what is checked
    finally:
        halt.set()


def replay_beyond():
    """M5's pinned case beyond the fixture's lines, for an event `_append`
    writes now (`ts` with milliseconds) and one with an older whole-second
    `ts`: each, addressed to S1, goes up as stored, goes again byte-identical
    after a `resend`, comes back as the endpoint's echo (`created` derived
    from its `ts`, `sig` and `attest` added) and reads present, and is asked
    as `words?` with the stored line; answered `words`, S1's bridge takes it
    as the person's words."""
    for ts, created, what in (("2026-10-27T18:10:00.250Z", "2026-10-27T18:10:00.250Z", "with milliseconds"),
                              ("2026-10-27T18:10:01Z", "2026-10-27T18:10:01.000Z", "of whole seconds")):
        ok, said = round_trip(ts, created, "an event %s, addressed" % what)
        say("ok" if ok else "FAIL", "beyond the fixture: an event _append wrote, ts %s and no created: %s" % (
            what, said))
        if not ok:
            return
    ok, said = sends_in_order()
    say("ok" if ok else "FAIL", "beyond the fixture: two devices' sends to S1, the first stalled before its lock: %s"
        % said)


def send_down(text, device):
    """A lane A `send` as O9 §E has the endpoint send it down, to S1 under
    its launch now; its opId."""
    created = iso()
    op = codes.b64url(os.urandom(18))
    CONNS["main"].write({"t": "rpc", "rpc": {
        "rpc": "send", "project": B["project:P"], "machine": B["name"], "member": B["member:A"], "device": device,
        "created": created, "nonce": codes.b64url(os.urandom(16)), "opId": op, "opCreated": created,
        "args": {"session": B["session:S1"], "text": text},
        "context": {"lane": "A", "session": B["session:S1"], "launch": B["launch:L1b"]},
        "fingerprint": "fp-" + op[:8]}})
    return op


def sends_in_order():
    """O9 §E's order through the RL10 receive path: each send's seq is
    reserved as its frame arrives; the first's worker is stalled before its
    claim and its lock, and the second, from another device, waits behind
    it; released, both enter, in arrival order, each answered with its
    row."""
    import sminos_rpc
    conn, mod = CONNS["main"], MODS["S1"]
    reached, gate = threading.Event(), threading.Event()
    plan = sminos_rpc.Rpcs.plan

    def stalled(self, rpc, facts):
        if rpc["args"].get("text") == "the first send":
            reached.set()
            gate.wait(20)
        return plan(self, rpc, facts)

    before = len(mod.delivered)
    with mock.patch.object(sminos_rpc.Rpcs, "plan", stalled):
        try:
            first = send_down("the first send", B["device:b1"])
            if not reached.wait(WAIT):
                return False, "the first send's worker never ran"
            second = send_down("the second send", B["device:b2"])
            time.sleep(1.5)
            if mod.delivered[before:]:
                return False, "the second went ahead of the stalled first: %r" % mod.delivered[before:]
        finally:
            gate.set()
        got = {}
        for op in (first, second):
            i = find(conn, lambda f, op=op: f.get("t") == "rpc-result" and f.get("opId") == op)
            if i is None:
                return False, "no rpc-result for %s" % op
            MATCHED.add((conn.number, i))
            got[op] = conn.frames[i]["outcome"]
            conn.write({"t": "rpc-ack", "opId": op, "nonce": conn.frames[i]["nonce"]})
    if mod.delivered[before:] != ["the first send", "the second send"]:
        return False, "delivered %r" % mod.delivered[before:]
    want = [{"state": "done", "result": {"entered": True, "uuid": u}} for u in mod.entered[-2:]]
    if [got[first], got[second]] != want:
        return False, "answered %r, not %r" % ([got[first], got[second]], want)
    return True, "the second waited, then both entered in arrival order, each answered with its row"


def round_trip(ts, created, text):
    conn = CONNS["main"]
    writer = own("human")
    seq = held(P_, writer)[-1]["seq"] + 1
    PLANNED.add((P_.id, B["session:S1"], writer, seq))   # asked here, not refused by answer_unstaged
    e = append_at(P_, writer, ts, "human", **{"from": "human", "to": recipients("S1", "main"), "text": text})
    if e["seq"] != seq:
        return False, "it went to seq %d, not %d" % (e["seq"], seq)
    stored = held(P_, writer)[-1]
    if "created" in stored or stored["ts"] != ts:
        return False, "it is stored as %r" % stored

    def carrying(f):
        return f.get("t") == "events" and f.get("project") == P_.id and stored in f.get("events", [])

    def body(i):
        return next(json.dumps(x, ensure_ascii=False) for x in conn.frames[i]["events"] if x == stored)
    first = find(conn, carrying)
    if first is None:
        return False, "it never went up as stored"
    conn.write({"t": "resend", "project": P_.id, "writer": writer, "from": seq})
    again = find(conn, carrying, after=first)
    if again is None:
        return False, "a resend from its seq never sent it again"
    if body(again) != body(first):
        return False, "the resend's body differs: %s, then %s" % (body(first), body(again))
    path = sminos.writer_path(P_, writer)
    before = open(path, "rb").read()
    rejected = len([f for f in conn.frames if f.get("t") == "rejected"])
    echo = {**stored, "created": created, "sig": {"kid": B["kid:machine"], "value": "AQ"},
            "attest": {"owners": [], "ownersProof": [], "origin": {"kind": "terminal"}, "stateVersion": 3}}
    conn.write({"t": "events", "project": P_.id, "events": [
        {"event": echo, "signer": {"kind": "machine", "ref": B["ref"], "name": B["name"], "keyId": B["kid:machine"]}}]})
    # A query after it, answered read-only, is its barrier: the frames down
    # are handled in order, and a `rejected` goes up before the `queried`.
    barrier = "cm91bmQtdHJpcC1iYXJyaWVy%s" % seq
    conn.write({"t": "query", "opId": barrier, "opCreated": iso()})
    if find(conn, lambda f: f.get("t") == "queried" and f.get("opId") == barrier) is None:
        return False, "the query behind its echo was never answered"
    if open(path, "rb").read() != before or len([f for f in conn.frames if f.get("t") == "rejected"]) != rejected:
        return False, "its echo did not read present"
    asked = find(conn, lambda f: f.get("t") == "words?" and f.get("event") == stored)
    if asked is None:
        return False, "it was never asked as words? with the stored line"
    MATCHED.add((conn.number, asked))
    conn.write({"t": "words", "id": conn.frames[asked]["id"], "verdict": "words"})
    if not wait_for(lambda: text in MODS["S1"].texts(), timeout=10):
        return False, "answered words, S1's bridge never took it (it took %r)" % MODS["S1"].delivered
    return True, "up as stored, resent byte-identical, its echo present, asked as words? and delivered as words"


def main():
    signal.signal(signal.SIGALRM, lambda *_: (say("FAIL", "the replay hung: stopped"), os._exit(1)))
    signal.alarm(int(DEADLINE) + 120)
    try:
        replay()
    except Exception as e:  # noqa: BLE001 — said as the replay's failure
        say("FAIL", "the replay stopped: %r" % e)
    finally:
        for proc in CHILDREN:
            if proc.poll() is None:
                proc.kill()
                proc.wait(10)
        for mod in MODS.values():
            try:
                mod.proc.kill()
            except OSError:
                pass
        if os.environ.get("SMINOS_CONFORMANCE_KEEP"):
            say("FAIL" if FAILED else "ok", "kept for a look: %s" % BASE)
        else:
            shutil.rmtree(BASE, ignore_errors=True)
    signal.alarm(0)


P_ = Q_ = None
main()
sys.exit(1 if FAILED else 0)
