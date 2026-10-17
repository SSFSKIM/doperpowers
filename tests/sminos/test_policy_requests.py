#!/usr/bin/env python3
"""The machine's policy, its pending requests and their settlements, and the
outcomes of delivering what came from outside (DC7 M2 of the desk).

- The policy: `daemon/policy.json`, written through `sminos daemon policy`,
  read at every use; no file is the default (not read-only, the settings'
  ceiling), a file that is no policy reads as read-only.
- Delivery (`deliver_next`, the one boundary every delivery passes): on a
  read-only machine an event written outside it is settled undelivered and
  reported `refused-read-only`, while the machine's own deliver as before;
  every settled delivery of an outside-origin event of a hub project leaves
  its outcome for the uplink (`delivered`, `recorded`, `refused-read-only`,
  `failed`).
- Requests: what the bridges raise and settle (DC2's real child, its DX5
  stream) becomes DX4 `raised` and `settled` with DX1's codes, and the
  machine's complete pending set.
- Then the uplink against the hub stand-in, or DC3's local hub when DESK_HUB
  names its stand-in for Access: requests and settlements reach the hub with
  codes and the pending set is republished on a reconnect; delivery outcomes
  reach it with codes; the policy is published in `machine` and again when
  the owner changes it.

Hermetic: HOME and SMINOS_HOME are temporary (test_session_plane's); nothing
reaches beyond 127.0.0.1 and this directory.
"""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid as uuidlib
from unittest import mock

import test_session_plane as tsp  # noqa: E402 — first: it makes this run's HOME and SMINOS_HOME

import sminos  # noqa: E402
import sminos_codes as codes  # noqa: E402
import sminos_outcomes as outcomes  # noqa: E402
import sminos_policy as policy  # noqa: E402
import sminos_requests as requests  # noqa: E402

T = tsp.T
KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
KEY = codes.b64url_bytes(KEY_B64, 32)
CLI = os.path.join(tsp.SCRIPTS, "sminos")
MEMBER = "4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]


def cli(*args, stdin=None):
    return subprocess.run([CLI, *args], capture_output=True, text=True, input=stdin)


def wait_for(test, timeout=10.0, every=0.03):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = test()
        if got:
            return got
        time.sleep(every)
    return None


def make_project(name, hub_url="http://127.0.0.1:9", org="org-1"):
    """A git checkout whose .smns names a hub; (root, project id)."""
    root = os.path.join(T, name)
    subprocess.run(GIT + ["init", "-q", root], check=True)
    r = subprocess.run([CLI, "project", "init", "--name", name], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    smns = os.path.join(root, ".smns")
    with open(smns) as f:
        d = json.load(f)
    d["hub"] = {"url": hub_url, "org": org}
    with open(smns, "w") as f:
        json.dump(d, f, indent=2)
    return root, d["project"]


class Inbox(threading.Thread):
    """A live session's inbox socket: every frame it is sent, kept."""

    def __init__(self, path):
        super().__init__(daemon=True)
        self.path = path
        self.frames = []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if os.path.exists(path):
            os.unlink(path)
        self.sock.bind(path)
        self.sock.listen(16)
        self.start()

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            data = b""
            while True:
                chunk = c.recv(65536)
                if not chunk:
                    break
                data += chunk
            # Kept before the close: the sender returns once the connection
            # closes, and a test reads the frames as soon as it has.
            for line in data.decode().splitlines():
                if line.strip():
                    self.frames.append(json.loads(line)["message"]["content"])
            c.close()

    def texts(self):
        return "\n".join(self.frames)

    def close(self):
        self.sock.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class Session:
    """A session of this machine whose engine record names a live process
    (a `sleep`), with an inbox socket when `inbox`."""

    def __init__(self, root, inbox=True, sid=None):
        self.sid = sid or str(uuidlib.uuid4())
        self.holder = subprocess.Popen(["sleep", "3600"])
        self.inbox = Inbox(os.path.join(T, "in-%s.sock" % self.sid[:8])) if inbox else None
        self.path = os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % self.holder.pid)
        rec = {"pid": self.holder.pid, "sessionId": self.sid, "cwd": root, "kind": "interactive",
               "name": "s-" + self.sid[:4], "nameSource": "derived", "status": "idle"}
        if self.inbox:
            rec["messagingSocketPath"] = self.inbox.path
        with open(self.path, "w") as f:
            json.dump(rec, f)

    def end(self):
        self.holder.terminate()
        self.holder.wait(5)
        if self.inbox:
            self.inbox.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


def project_of(root):
    sminos.forget_caches()
    return sminos.resolve_project(root)


def member_of(project, sid):
    sminos.forget_caches()
    return next(m for m in sminos.view_of(project, titles=False).members if m.session == sid)


def set_policy(d):
    os.makedirs(os.path.dirname(policy.policy_path()), exist_ok=True)
    with open(policy.policy_path(), "w") as f:
        json.dump(d, f)


def clear_policy():
    try:
        os.unlink(policy.policy_path())
    except OSError:
        pass


def hub_human(key, project_id, sid, alias, text, seq):
    """A web `human` as the hub stores it: sealed by the browser, then given
    its writer, seq, and ts (DX1)."""
    draft = {"kind": "human", "from": "human", "member": MEMBER, "to": [{"session": sid, "alias": alias}],
             "text": text, "created": "2026-10-15T08:04:59.870Z"}
    sealed = codes.seal(key, "log", project_id, draft, codes.b64url(os.urandom(16)))
    return {**sealed, "writer": "hub/" + MEMBER, "seq": seq, "ts": "2026-10-15T08:05:%02d.000Z" % (seq % 60)}


# ---------------------------------------------------------------- the policy


class Policy(unittest.TestCase):
    def tearDown(self):
        clear_policy()
        settings = os.path.join(os.environ["HOME"], ".claude", "settings.json")
        if os.path.exists(settings):
            os.unlink(settings)

    def test_no_file_is_the_default(self):
        self.assertEqual(policy.machine_policy(), {"read_only": False, "ceiling": "default"})
        with open(os.path.join(os.environ["HOME"], ".claude", "settings.json"), "w") as f:
            json.dump({"permissions": {"defaultMode": "acceptEdits"}}, f)
        self.assertEqual(policy.machine_policy(), {"read_only": False, "ceiling": "acceptEdits"},
                         "the ceiling the user's own settings give")

    def test_the_verb_writes_it_and_every_use_reads_it(self):
        r = cli("daemon", "policy")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("read-only: no", r.stdout)
        self.assertIn("ceiling: default (from your settings' defaultMode)", r.stdout)
        r = cli("daemon", "policy", "--read-only", "on")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("read-only: yes", r.stdout)
        self.assertEqual(os.stat(policy.policy_path()).st_mode & 0o777, 0o600)
        self.assertEqual(policy.machine_policy(), {"read_only": True, "ceiling": "default"}, "read at its next use")
        r = cli("daemon", "policy", "--ceiling", "acceptEdits")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(policy.machine_policy(), {"read_only": True, "ceiling": "acceptEdits"},
                         "one field changed, the other kept")
        before = tsp.read(policy.policy_path())
        r = cli("daemon", "policy", "--ceiling", "yolo")
        self.assertEqual(r.returncode, 2)
        self.assertIn("the ceiling is one of", r.stderr)
        self.assertEqual(tsp.read(policy.policy_path()), before, "a refused change writes nothing")
        r = cli("daemon", "policy", "--read-only", "off", "--ceiling", "settings")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(policy.machine_policy(), {"read_only": False, "ceiling": "default"})

    def test_a_file_that_is_no_policy_reads_as_read_only(self):
        os.makedirs(os.path.dirname(policy.policy_path()), exist_ok=True)
        for bad in ("{not json", '{"read_only": "yes"}', '{"ceiling": "everything"}', "[]"):
            with open(policy.policy_path(), "w") as f:
                f.write(bad)
            self.assertTrue(policy.read_only(), "fails closed: %s" % bad)
        r = cli("daemon", "policy", "--ceiling", "plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(policy.machine_policy(), {"read_only": True, "ceiling": "plan"},
                         "a change over a broken file keeps it read-only unless it says otherwise")

    def test_outside_origin(self):
        sid = str(uuidlib.uuid4())
        self.assertFalse(policy.outside_origin({"writer": "testhost/" + sid}))
        self.assertFalse(policy.outside_origin({"writer": "testhost/human"}))
        self.assertTrue(policy.outside_origin({"writer": "otherhost/" + sid}))
        self.assertTrue(policy.outside_origin({"writer": "hub/" + MEMBER}))
        self.assertTrue(policy.outside_origin({"writer": "legacy/old"}))


# ---------------------------------------------------------------- delivery


class Delivery(unittest.TestCase):
    """deliver_next on a hub project, in this process."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.pid = make_project("deliv")
        cls.live = Session(cls.root)
        cls.project = project_of(cls.root)
        sminos.reconcile(cls.project)
        cls.alias = member_of(cls.project, cls.live.sid).alias
        cls.far = "otherhost/" + str(uuidlib.uuid4())
        cls.hub_seq = 0

    @classmethod
    def tearDownClass(cls):
        cls.live.end()

    def tearDown(self):
        clear_policy()

    def outbox(self):
        return outcomes.Outbox(self.project).read()

    def say_from_far(self, text, to=None):
        return sminos.log_append(self.project, self.far, "say",
                                 **{"from": "far", "to": [to or {"session": self.live.sid, "alias": self.alias}],
                                    "text": text})

    def human_from_hub(self, text):
        Delivery.hub_seq += 1
        e = hub_human(KEY, self.pid, self.live.sid, self.alias, text, self.hub_seq)
        path = sminos.writer_path(self.project, e["writer"])
        with open(path, "a") as f:
            f.write(json.dumps(e) + "\n")
        return e

    def human_here(self, text):
        return sminos.log_append(self.project, sminos.writer_id(), "human",
                                 **{"from": "human", "to": [{"session": self.live.sid, "alias": self.alias}],
                                    "text": text})

    def deliver(self):
        return sminos.deliver_next(self.project, member_of(self.project, self.live.sid))

    def outcome_of(self, e, session=None):
        found = [o for o in self.outbox() if o["event"] == {"writer": e["writer"], "seq": e["seq"]}
                 and o["session"] == (session or self.live.sid)]
        return found[-1] if found else None

    def test_outside_origin_delivered_leaves_its_outcome(self):
        e = self.say_from_far("from far away")
        h = self.human_from_hub("from the web")
        self.deliver()
        self.assertIn("from far away", self.live.inbox.texts())
        self.assertIn("from the web", self.live.inbox.texts())
        for ev in (e, h):
            o = self.outcome_of(ev)
            self.assertIsNotNone(o, "an outcome for %s:%d" % (ev["writer"], ev["seq"]))
            self.assertEqual(o["outcome"], "delivered")
            self.assertIsInstance(o["reason"], str)

    def test_local_origin_leaves_none(self):
        e = self.human_here("from this machine")
        self.deliver()
        self.assertIn("from this machine", self.live.inbox.texts())
        self.assertIsNone(self.outcome_of(e), "events written here are not reported")

    def test_read_only_refuses_outside_origin_and_delivers_its_own(self):
        set_policy({"read_only": True})
        before = len(self.live.inbox.frames)
        e = self.say_from_far("not while read-only")
        h = self.human_from_hub("nor this")
        mine = self.human_here("but this, written here")
        self.deliver()
        self.assertNotIn("not while read-only", self.live.inbox.texts())
        self.assertNotIn("nor this", self.live.inbox.texts())
        self.assertIn("but this, written here", self.live.inbox.texts(), "the machine's own deliver as before")
        self.assertEqual(len(self.live.inbox.frames), before + 1)
        for ev in (e, h):
            self.assertEqual(self.outcome_of(ev)["outcome"], "refused-read-only")
        self.assertIsNone(self.outcome_of(mine))
        self.assertEqual(sminos.owed(self.project, member_of(self.project, self.live.sid)), [],
                         "settled undelivered")
        clear_policy()
        self.deliver()
        self.assertNotIn("not while read-only", self.live.inbox.texts(), "and never delivered later")

    def test_a_closed_session_is_recorded(self):
        gone = Session(self.root, inbox=False)
        try:
            project = project_of(self.root)
            sminos.reconcile(project)
            snapshot = member_of(project, gone.sid)  # taken while it ran
            gone.end()
            sminos.forget_caches()
            e = sminos.log_append(project, self.far, "say",
                                  **{"from": "far", "to": [{"session": gone.sid, "alias": snapshot.alias}],
                                     "text": "to a closed session"})
            sminos.deliver_next(project, snapshot)
            o = self.outcome_of(e, gone.sid)
            self.assertEqual(o["outcome"], "recorded")
            self.assertIn("not running", o["reason"])
        finally:
            gone.end() if gone.holder.poll() is None else None

    def test_a_push_taken_and_never_answered_is_uncertain(self):
        e = self.say_from_far("taken, unanswered")
        with mock.patch.object(sminos, "push_event", return_value="sent?"):
            self.deliver()
        o = self.outcome_of(e)
        self.assertEqual(o["outcome"], "uncertain")
        self.assertEqual(sminos.owed(self.project, member_of(self.project, self.live.sid)), [],
                         "settled: never pushed again")

    def test_an_outcome_that_cannot_be_written_leaves_the_event_owed(self):
        e = self.say_from_far("its outcome first")
        with mock.patch.object(outcomes.Outbox, "record", side_effect=OSError("disk full")):
            self.deliver()
        self.assertIsNone(self.outcome_of(e))
        self.assertIn(e["seq"], [x["seq"] for x in sminos.owed(self.project, member_of(self.project, self.live.sid))
                                 if x["writer"] == e["writer"]], "not settled without its outcome")
        self.deliver()
        self.assertEqual(self.outcome_of(e)["outcome"], "delivered", "the next pass delivers and records it")
        self.assertEqual(sminos.owed(self.project, member_of(self.project, self.live.sid)), [])

    def test_a_closed_terminal_session_is_reported_recorded_until_it_is_back(self):
        """A session whose process ended is no member: an event sent to it
        is reported `recorded` once, stays owed, and when the session comes
        back (Resume, M4; here its process again) is delivered, `delivered`
        following for the same key."""
        import sminos_daemon as daemon
        gone = Session(self.root)
        sid = gone.sid
        try:
            project = project_of(self.root)
            sminos.reconcile(project)
            alias = member_of(project, sid).alias
            gone.end()
            sminos.forget_caches()
            view = sminos.view_of(project, titles=False)
            self.assertNotIn(sid, [m.session for m in view.members], "its membership ended with its process")
            e = sminos.log_append(project, self.far, "say",
                                  **{"from": "far", "to": [{"session": sid, "alias": alias}],
                                     "text": "to a closed terminal session"})
            for _ in range(2):
                sminos.forget_caches()
                daemon.deliver_owed(project, sminos.view_of(project, titles=False))
            mine = [o for o in self.outbox() if o["event"] == {"writer": e["writer"], "seq": e["seq"]}
                    and o["session"] == sid]
            self.assertEqual([o["outcome"] for o in mine], ["recorded"], "once, however many passes")
            self.assertEqual([x["seq"] for x in sminos._owed(sminos.log_read(project), sid,
                                                             sminos.delivered_load(project, sid))], [e["seq"]],
                             "and it stays owed")
            back = Session(self.root, sid=sid)
            try:
                sminos.forget_caches()
                daemon.deliver_owed(project, sminos.view_of(project, titles=False))
                self.assertIn("to a closed terminal session", back.inbox.texts(), "delivered once it is back")
                self.assertEqual(self.outcome_of(e, sid)["outcome"], "delivered", "the same key, now delivered")
            finally:
                back.end()
        finally:
            if gone.holder.poll() is None:
                gone.end()

    def test_a_closed_terminal_session_on_a_read_only_machine_is_refused_and_settled(self):
        """A closed session is no member, so deliver_next never sees what is
        owed to it: the closed report applies the policy itself. On a
        read-only machine an event from outside owed to it is settled
        undelivered, `refused-read-only`, and is not delivered when the
        machine is writable again and the session comes back; the machine's
        own events stay owed and are."""
        import sminos_daemon as daemon
        gone = Session(self.root)
        sid = gone.sid
        try:
            project = project_of(self.root)
            sminos.reconcile(project)
            alias = member_of(project, sid).alias
            gone.end()
            sminos.forget_caches()
            sminos.view_of(project, titles=False)
            set_policy({"read_only": True})
            e = sminos.log_append(project, self.far, "say",
                                  **{"from": "far", "to": [{"session": sid, "alias": alias}],
                                     "text": "from outside, while read-only"})
            mine = sminos.log_append(project, sminos.writer_id(), "human",
                                     **{"from": "human", "to": [{"session": sid, "alias": alias}],
                                        "text": "written here, while read-only"})
            sminos.forget_caches()
            daemon.deliver_owed(project, sminos.view_of(project, titles=False))
            self.assertEqual(self.outcome_of(e, sid)["outcome"], "refused-read-only")
            owed = [(x["writer"], x["seq"]) for x in sminos._owed(sminos.log_read(project), sid,
                                                                  sminos.delivered_load(project, sid))]
            self.assertNotIn((e["writer"], e["seq"]), owed, "settled undelivered")
            self.assertIn((mine["writer"], mine["seq"]), owed, "the machine's own stays owed")
            clear_policy()
            back = Session(self.root, sid=sid)
            try:
                sminos.forget_caches()
                daemon.deliver_owed(project, sminos.view_of(project, titles=False))
                self.assertIn("written here, while read-only", back.inbox.texts())
                self.assertNotIn("from outside, while read-only", back.inbox.texts(),
                                 "never delivered once read-only is lifted")
                self.assertEqual(self.outcome_of(e, sid)["outcome"], "refused-read-only", "and its outcome stands")
            finally:
                back.end()
        finally:
            clear_policy()
            if gone.holder.poll() is None:
                gone.end()

    def test_a_closed_report_and_the_delivery_after_it_are_serialized(self):
        """The reporter reads the settled prefix; the session comes back and
        delivery runs meanwhile. Delivery waits for the reporter's lock, so
        `recorded` is never written after `delivered` (the hub keeps the
        latest)."""
        import sminos_daemon as daemon
        gone = Session(self.root)
        sid = gone.sid
        back = None
        try:
            project = project_of(self.root)
            sminos.reconcile(project)
            alias = member_of(project, sid).alias
            gone.end()
            sminos.forget_caches()
            view = sminos.view_of(project, titles=False)
            e = sminos.log_append(project, self.far, "say",
                                  **{"from": "far", "to": [{"session": sid, "alias": alias}], "text": "raced"})
            view = sminos.view_of(project, titles=False)
            read, go = threading.Event(), threading.Event()
            real = sminos.delivered_load

            def paused(project_, session):
                got = real(project_, session)
                if threading.current_thread().name == "reporter" and session == sid:
                    read.set()
                    go.wait(10)
                return got

            with mock.patch.object(sminos, "delivered_load", side_effect=paused):
                reporter = threading.Thread(target=outcomes.report_closed, args=(project, view), name="reporter")
                reporter.start()
                self.assertTrue(read.wait(10), "the reporter read the settled prefix")
                back = Session(self.root, sid=sid)
                sminos.forget_caches()
                member = member_of(project, sid)  # it is back: a member again
                deliverer = threading.Thread(target=sminos.deliver_next, args=(project, member))
                deliverer.start()
                deliverer.join(0.5)
                self.assertTrue(deliverer.is_alive(), "delivery waits for the reporter's lock")
                go.set()
                reporter.join(10)
                deliverer.join(10)
            mine = [o["outcome"] for o in self.outbox() if o["event"] == {"writer": e["writer"], "seq": e["seq"]}
                    and o["session"] == sid]
            self.assertEqual(mine, ["recorded", "delivered"], "the latest is the delivery")
            self.assertIn("raced", back.inbox.texts())
        finally:
            if back is not None:
                back.end()
            if gone.holder.poll() is None:
                gone.end()

    def test_a_delivery_given_up_is_failed(self):
        e = self.say_from_far("never lands")
        with mock.patch.object(sminos, "push_event", return_value="failed:the socket refused"), \
                mock.patch.object(sminos, "DELIVERY_ATTEMPTS", 2):
            self.deliver()
            self.assertIsNone(self.outcome_of(e), "a failure still retried is not settled: no outcome yet")
            self.deliver()
        o = self.outcome_of(e)
        self.assertEqual(o["outcome"], "failed")
        self.assertIn("the socket refused", o["reason"])


# ---------------------------------------------------------------- requests


class Bridge:
    """DC2's bridge child for a session (`sminos bridge --session`), this
    process its parent; events posted as the mod posts them, and a delivery
    (`deliver`) answered as the mod answers one it submitted."""

    def __init__(self, sid, ready=True):
        self.sid = sid
        self.delivered = []
        # A reason here: each delivery is then dropped by the engine after
        # it was submitted, as the mod reports a PromptSubmitResult.drop.
        self.refusing = None
        # True: the post carrying each refusal is lost, and the mod recovers
        # as it does (bridge-stream.tsx, lose): a gap, then a resync of its
        # state, which carries the refusals no answered post has.
        self.losing_refusals = False
        self.proc = subprocess.Popen([CLI, "bridge", "--session", sid], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
        hello = json.loads(self.proc.stdout.readline())
        assert hello.get("op") == "hello", hello
        self.sock = hello["socket"]
        self.nonce = hello["nonce"]  # DX5 M4: a post without the hello's nonce is another module's (409)
        threading.Thread(target=self.drain, daemon=True).start()
        if ready:
            # The mod's first posts to a child: the session's start, then its
            # state with the hello's seed as the cut; the child serves no
            # snapshot before that resync (DX5 M4).
            self.post({"type": "session", "phase": "start", "session": sid, "cwd": "/", "t": 0},
                      {"type": "resync", "turns": [], "streaming": [], "agents": [], "cut": hello.get("seed") or {},
                       "t": 0})

    def drain(self):
        with self.proc.stdout:
            for line in self.proc.stdout:
                cmd = json.loads(line)
                if cmd.get("op") == "deliver":
                    self.delivered.append(cmd["text"])
                    self.post({"type": "delivered", "key": cmd["key"], "outcome": "submitted"},
                              {"type": "result", "id": cmd["id"], "op": "deliver", "ok": True,
                               "result": {"submitted": True}})
                    if self.refusing is not None and self.losing_refusals:
                        self.post({"type": "gap", "dropped": 1, "t": 0},
                                  {"type": "resync", "turns": [], "streaming": [], "agents": [], "override": None,
                                   "delivered": {cmd["key"]["writer"]: cmd["key"]["seq"]},
                                   "refused": [{"key": cmd["key"], "reason": self.refusing}], "t": 0})
                    elif self.refusing is not None:
                        self.post({"type": "delivered", "key": cmd["key"], "outcome": "refused",
                                   "reason": self.refusing})

    def texts(self):
        return "\n".join(self.delivered)

    def post(self, *events):
        import sminos_bridge as bridge
        c = bridge._UnixConnection(self.sock, 10)
        try:
            c.request("POST", "/events", body=json.dumps(list(events)).encode(),
                      headers={"content-type": "application/json", bridge.NONCE_HEADER: self.nonce})
            status = c.getresponse().status
        finally:
            c.close()
        assert status == 204, status

    def raise_(self, rid, tool="Bash", input_=None, **extra):
        self.post({"type": "raised", "request": rid, "tool": tool, "input": input_ or {"command": "ls"},
                   "agentId": None, **extra, "t": int(time.time() * 1000)})

    def settle(self, rid, outcome="allow", winner="terminal", by="terminal"):
        self.post({"type": "settled", "request": rid, "winner": winner, "outcome": outcome, "by": by,
                   "t": int(time.time() * 1000)})

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)


def messages(frames, kind=None):
    return [f["message"] for f in frames if f.get("t") == "session" and kind in (None, f["message"]["kind"])]


# ---------------------------------------------------------------- a submission refused


class Refusals(unittest.TestCase):
    """A delivery the bridge answered `submitted` that the engine then
    dropped (DC8.G5): the child keeps the bridge's `delivered {outcome:
    "refused", reason}` with its key, and the delivery path's next pass
    records a second outcome for the key and session, `failed` with that
    reason, once. Against the real bridge child."""

    @classmethod
    def setUpClass(cls):
        import sminos_daemon as daemon
        cls.daemon = daemon
        cls.root, cls.pid = make_project("refus")
        cls.live = Session(cls.root)
        cls.sid = cls.live.sid
        cls.bridge = Bridge(cls.sid)
        cls.project = project_of(cls.root)
        sminos.reconcile(cls.project)
        cls.alias = member_of(cls.project, cls.sid).alias
        cls.hub_seq = 0

    @classmethod
    def tearDownClass(cls):
        cls.bridge.stop()
        cls.live.end()

    def tearDown(self):
        self.bridge.refusing = None
        self.bridge.losing_refusals = False

    def human_from_hub(self, text, sid=None, alias=None):
        Refusals.hub_seq += 1
        e = hub_human(KEY, self.pid, sid or self.sid, alias or self.alias, text, self.hub_seq)
        with open(sminos.writer_path(self.project, e["writer"]), "a") as f:
            f.write(json.dumps(e) + "\n")
        return e

    def kept_refused(self, sid=None):
        import sminos_bridge as bridge
        return bridge.load_kept(sid or self.sid).get("refused") or []

    def outcomes_of(self, e, sid=None):
        return [(o["outcome"], o["reason"]) for o in outcomes.Outbox(self.project).read()
                if o["event"] == {"writer": e["writer"], "seq": e["seq"]} and o["session"] == (sid or self.sid)]

    def deliver(self):
        return sminos.deliver_next(self.project, member_of(self.project, self.sid))

    def a_pass(self):
        sminos.forget_caches()
        return self.daemon.deliver_owed(self.project, sminos.view_of(self.project, titles=False))

    def test_a_the_child_keeps_each_refusal_with_its_key_bounded(self):
        import sminos_bridge as bridge
        key = {"writer": "hub/" + MEMBER, "seq": 9001}
        self.bridge.post({"type": "delivered", "key": key, "outcome": "submitted"},
                         {"type": "delivered", "key": key, "outcome": "refused", "reason": "a Stop hook stands"})
        self.assertEqual(self.kept_refused(), [{"key": key, "reason": "a Stop hook stands"}])
        self.bridge.post({"type": "resync", "turns": [], "streaming": [], "agents": [], "override": None,
                          "delivered": {"hub/" + MEMBER: 9001}, "t": 0})
        self.assertEqual(self.kept_refused(), [{"key": key, "reason": "a Stop hook stands"}],
                         "the mod's resync, which carries none, keeps them")
        self.bridge.post({"type": "delivered", "key": key, "outcome": "refused", "reason": "again"})
        self.assertEqual(len(self.kept_refused()), 1, "a key is kept once")
        self.bridge.post(*[{"type": "delivered", "key": {"writer": "hub/" + MEMBER, "seq": 9100 + i},
                            "outcome": "refused", "reason": "x" * 5000} for i in range(bridge.REFUSED_KEPT + 5)])
        kept = self.kept_refused()
        self.assertEqual(len(kept), bridge.REFUSED_KEPT, "bounded")
        self.assertEqual(kept[-1]["key"]["seq"], 9100 + bridge.REFUSED_KEPT + 4, "the newest kept")
        self.assertLessEqual(len(kept[-1]["reason"]), bridge.REASON_MAX)
        self.assertEqual(outcomes.report_refused(self.project, sminos.view_of(self.project, titles=False)), 0,
                         "keys no event of the log has are not reported")

    def test_b_a_web_send_dropped_after_submitted_is_reported_failed_once(self):
        self.bridge.refusing = "a Stop hook stands"
        e = self.human_from_hub("dropped after it was taken")
        self.deliver()
        self.assertIn("dropped after it was taken", self.bridge.texts())
        self.assertEqual([o for o, _ in self.outcomes_of(e)], ["delivered"])
        key = {"writer": e["writer"], "seq": e["seq"]}
        self.assertTrue(wait_for(lambda: [r for r in self.kept_refused() if r["key"] == key]),
                        "the child kept the refusal")
        self.a_pass()
        got = self.outcomes_of(e)
        self.assertEqual([o for o, _ in got], ["delivered", "failed"], "a second outcome for the key, after the first")
        self.assertIn("a Stop hook stands", got[-1][1], "with the bridge's reason")
        self.a_pass()
        self.assertEqual([o for o, _ in self.outcomes_of(e)], ["delivered", "failed"], "recorded once")

    def test_b2_a_refusal_whose_post_was_lost_is_reported_from_the_resync(self):
        """The mod's post carrying the refusal fails; its recovery's resync
        carries the refusal with its reason, which the child keeps beside
        any it holds, once per key, so the `failed` still reaches the
        outbox."""
        import sminos_bridge as bridge
        self.bridge.refusing = "the prompt queue was cleared"
        self.bridge.losing_refusals = True
        e = self.human_from_hub("dropped, and its refusal's post lost")
        self.deliver()
        self.assertIn("dropped, and its refusal's post lost", self.bridge.texts())
        key = {"writer": e["writer"], "seq": e["seq"]}
        self.assertTrue(wait_for(lambda: [r for r in self.kept_refused() if r["key"] == key]),
                        "the child kept the refusal from the resync")
        self.bridge.post({"type": "resync", "turns": [], "streaming": [], "agents": [], "override": None,
                          "refused": [{"key": key, "reason": "the prompt queue was cleared"},
                                      {"key": {"writer": "hub/" + MEMBER, "seq": 9300}, "reason": "y" * 5000}],
                          "t": 0})
        kept = self.kept_refused()
        self.assertEqual([r["key"] for r in kept].count(key), 1, "a key the child holds is kept once")
        self.assertEqual(kept[-1]["key"], {"writer": "hub/" + MEMBER, "seq": 9300}, "a new one after the rest")
        self.assertLessEqual(len(kept[-1]["reason"]), bridge.REASON_MAX)
        self.assertLessEqual(len(kept), bridge.REFUSED_KEPT, "bounded")
        self.a_pass()
        got = self.outcomes_of(e)
        self.assertEqual([o for o, _ in got], ["delivered", "failed"])
        self.assertIn("the prompt queue was cleared", got[-1][1], "with the bridge's reason")

    def test_c_a_refusal_of_an_event_written_here_is_not_reported(self):
        self.bridge.refusing = "a Stop hook stands"
        e = sminos.log_append(self.project, sminos.writer_id(), "human",
                              **{"from": "human", "to": [{"session": self.sid, "alias": self.alias}],
                                 "text": "written here, dropped"})
        self.deliver()
        key = {"writer": e["writer"], "seq": e["seq"]}
        self.assertTrue(wait_for(lambda: [r for r in self.kept_refused() if r["key"] == key]))
        self.a_pass()
        self.assertEqual(self.outcomes_of(e), [], "nothing from outside, nothing reported")

    def test_e_a_marker_that_cannot_be_written_is_said_once_and_held_by_the_process(self):
        """The record comes first, then the marker (at least once, as the
        outbox is): a marker write that fails is said once in daemon.log,
        and this process does not record the same `failed` again."""
        self.bridge.refusing = "dropped, marker unwritable"
        e = self.human_from_hub("its marker will not be kept")
        self.deliver()
        key = {"writer": e["writer"], "seq": e["seq"]}
        self.assertTrue(wait_for(lambda: [r for r in self.kept_refused() if r["key"] == key]))
        real = sminos.write_json

        def refuse_markers(path, *a, **k):
            if os.sep + "refused" + os.sep in path:
                raise OSError("read-only file system")
            return real(path, *a, **k)

        with mock.patch.object(sminos, "write_json", side_effect=refuse_markers), \
                mock.patch.object(sminos, "daemon_log") as log:
            for _ in range(3):
                self.a_pass()
        self.assertEqual([o for o, _ in self.outcomes_of(e)], ["delivered", "failed"], "recorded once")
        said = [c.args[0] for c in log.call_args_list if "refusals could not be kept" in c.args[0]]
        self.assertEqual(len(said), 1, "said once: %s" % said)
        self.a_pass()
        self.assertEqual([o for o, _ in self.outcomes_of(e)], ["delivered", "failed"])
        self.assertEqual(outcomes._UNWRITTEN, {}, "the marker is written once it can be")

    def test_d_a_refusal_is_reported_only_once_its_first_outcome_is_recorded(self):
        """The `failed` must follow the `delivered` (the hub keeps the
        latest): a refusal naming an event still owed to the session waits
        until delivery has recorded and settled it. Here the session has no
        bridge running and its kept file is written as a child writes it."""
        import sminos_bridge as bridge
        other = Session(self.root)
        try:
            sminos.reconcile(self.project)
            alias = member_of(self.project, other.sid).alias
            e = self.human_from_hub("not delivered yet", other.sid, alias)
            key = {"writer": e["writer"], "seq": e["seq"]}
            with open(bridge.kept_path(other.sid), "w") as f:
                json.dump({"override": None, "delivered": {}, "refused": [{"key": key, "reason": "dropped"}]}, f)
            sminos.forget_caches()
            self.assertEqual(outcomes.report_refused(self.project, sminos.view_of(self.project, titles=False)), 0)
            self.assertEqual(self.outcomes_of(e, other.sid), [], "not before its delivery")
            self.a_pass()
            self.assertIn("not delivered yet", other.inbox.texts())
            self.assertEqual([o for o, _ in self.outcomes_of(e, other.sid)], ["delivered", "failed"])
        finally:
            other.end()
            try:
                os.unlink(bridge.kept_path(other.sid))
            except OSError:
                pass


class Requests(unittest.TestCase):
    """The relay of requests, against the real bridge child."""

    PID = "6f1c0a8e-3b2d-4c5e-9f70-8a1b2c3d4e5f"

    def setUp(self):
        self.sid = str(uuidlib.uuid4())
        self.bridge = Bridge(self.sid)
        self.r = requests.Requests(KEY, "testhost")
        self.r.follow({self.sid: self.PID})

    def tearDown(self):
        self.r.close()
        self.bridge.stop()

    def due(self, test, timeout=10.0):
        """The frames due once `test(frames)` holds (taken, not yet sent)."""
        def ready():
            self.r.take()
            frames = self.r.due({self.PID})
            return frames if test(frames) else None
        got = wait_for(ready, timeout)
        self.assertIsNotNone(got, "the frames came: %s" % self.r.due({self.PID}))
        return got

    def test_raised_and_settled_with_their_codes(self):
        self.bridge.raise_("toolu_01", input_={"command": "pnpm e2e", "timeout": 0.5})
        frames = self.due(lambda fs: messages(fs, "raised"))
        m = messages(frames, "raised")[0]
        self.assertEqual((m["project"], m["machine"], m["session"], m["sub"], m["n"]),
                         (self.PID, "testhost", self.sid, None, None))
        body = m["body"]
        self.assertEqual({k: v for k, v in body.items() if k != "mac"},
                         {"request": "toolu_01", "session": self.sid, "tool": "Bash",
                          "input": {"command": "pnpm e2e", "timeout": 0.5}})
        self.assertTrue(codes.verifies(KEY, "raised", self.PID, body), "DX1's code, smns-hub-raised-v1")
        self.r.sent(frames)
        self.assertEqual(self.r.due({self.PID}), [], "sent once")
        self.assertEqual([x["request"] for x in self.r.pending_frame(self.PID)["raised"]], ["toolu_01"])
        self.bridge.settle("toolu_01", outcome="deny", winner="web", by=MEMBER)
        frames = self.due(lambda fs: messages(fs, "settled"))
        s = messages(frames, "settled")[0]["body"]
        self.assertEqual({k: v for k, v in s.items() if k != "mac"},
                         {"request": "toolu_01", "winner": "web", "outcome": "deny", "by": MEMBER},
                         "as the bridge reported it")
        self.assertTrue(codes.verifies(KEY, "settled", self.PID, s))
        self.r.sent(frames)
        self.assertEqual(self.r.pending_frame(self.PID), {"t": "pending", "project": self.PID, "raised": []})

    def test_a_background_deadline_and_an_async_question(self):
        deadline = 1792022400123  # 2026-10-15T00:00:00.123Z
        self.bridge.raise_("toolu_bg", agentId="a7", deadline=deadline)
        self.bridge.raise_("toolu_plugin_q", tool="mcp__doperpowers__AskUserQuestion",
                           input_={"questions": [{"question": "Which?", "options": []}]}, **{"async": True},
                           truncated=True)
        frames = self.due(lambda fs: len(messages(fs, "raised")) == 2)
        bg, q = (m["body"] for m in messages(frames, "raised"))
        self.assertEqual(bg["deadline"], "2026-10-15T00:00:00.123Z", "DX4's deadline: ISO 8601 UTC, milliseconds")
        self.assertNotIn("async", bg)
        self.assertIs(q["async"], True)
        self.assertEqual(bg["agentId"], "a7", "a subagent's request names it")
        self.assertNotIn("agentId", q, "the main thread's names none")
        self.assertIs(q["truncated"], True)
        self.assertNotIn("truncated", bg, "truncated only as true")
        for b in (bg, q):
            self.assertTrue(codes.verifies(KEY, "raised", self.PID, b), "the code covers every field")
            self.assertNotIn("t", b)

    def test_the_ask_mods_dialog_carries_its_calls_tool_use_id(self):
        """DX5 `raised.toolUseId` (composite 43a27604): the call a dialog of
        the ask mod belongs to, carried into DX4 `raised` under the code, only
        where it differs from `request`."""
        q = {"questions": [{"question": "Which?", "options": [{"label": "a"}]}]}
        self.bridge.raise_("toolu_plugin_7", tool="AskUserQuestion", input_=q, toolUseId="toolu_01outer")
        self.bridge.raise_("toolu_01same", tool="AskUserQuestion", input_=q, toolUseId="toolu_01same")
        self.bridge.raise_("toolu_01bad", tool="AskUserQuestion", input_=q, toolUseId="")
        frames = self.due(lambda fs: len(messages(fs, "raised")) == 3)
        dialog, same, bad = (m["body"] for m in messages(frames, "raised"))
        self.assertEqual((dialog["request"], dialog["toolUseId"]), ("toolu_plugin_7", "toolu_01outer"))
        self.assertTrue(codes.verifies(KEY, "raised", self.PID, dialog), "the code covers it")
        self.assertNotIn("toolUseId", same, "only where it differs from request")
        self.assertNotIn("toolUseId", bad, "only a non-empty string")
        self.assertEqual([r.get("toolUseId") for r in self.r.pending_frame(self.PID)["raised"]
                          if r["request"] == "toolu_plugin_7"], ["toolu_01outer"], "the pending set carries it")

    def test_a_reconnect_to_the_bridge_reconciles(self):
        """A module reload: a new child takes the endpoint over and the mod
        hands it its whole state (`resync`) before the child serves its
        first subscriber (DX5, DC2's M4); meanwhile one request settled and
        another was raised. The reader's stream ends with the old child, and
        the new child's snapshot is reconciled with what was held."""
        self.bridge.raise_("toolu_a")
        self.bridge.raise_("toolu_b")
        self.r.sent(self.due(lambda fs: len(messages(fs, "raised")) == 2))
        old, self.bridge = self.bridge, Bridge(self.sid, ready=False)
        self.bridge.post({"type": "resync", "turns": [], "streaming": [], "agents": [], "override": None,
                          "delivered": {},
                          "pending": [{"request": "toolu_b", "tool": "Bash", "input": {"command": "ls"},
                                       "agentId": None, "t": 1},
                                      {"request": "toolu_c", "tool": "Bash", "input": {"command": "ls"},
                                       "agentId": None, "t": 2}],
                          "settled": [{"request": "toolu_a", "winner": "other", "outcome": "allow", "by": "cli",
                                       "t": 3}]})
        self.assertIsNotNone(wait_for(lambda: old.proc.poll() is not None), "the old child leaves")
        frames = self.due(lambda fs: messages(fs, "settled") and messages(fs, "raised"))
        self.assertEqual([m["body"]["request"] for m in messages(frames, "settled")], ["toolu_a"],
                         "a settlement the snapshot lists, for a request held pending")
        self.assertEqual([m["body"]["request"] for m in messages(frames, "raised")], ["toolu_c"],
                         "a request raised meanwhile")
        self.r.sent(frames)
        self.assertEqual(sorted(x["request"] for x in self.r.pending_frame(self.PID)["raised"]),
                         ["toolu_b", "toolu_c"])

    def test_a_bridge_gone_drops_its_requests_from_the_set(self):
        self.bridge.raise_("toolu_x")
        self.r.sent(self.due(lambda fs: messages(fs, "raised")))
        self.bridge.stop()
        self.r.follow({})  # its bridge answers no more
        frames = self.due(lambda fs: [f for f in fs if f.get("t") == "pending"])
        self.assertEqual([f for f in frames if f.get("t") == "pending"],
                         [{"t": "pending", "project": self.PID, "raised": []}],
                         "the complete set, without it: the hub drops it; nothing is settled in the bridge's name")
        self.assertEqual(messages(frames, "settled"), [])

    def test_a_settlement_made_while_unread_is_relayed_once(self):
        """Raised and settled while no reader held the bridge: the snapshot's
        recent settlements carry it, and it goes up once — not again on the
        next snapshot, nor from a Requests that starts anew (a restart)."""
        self.r.close()
        self.r = requests.Requests(KEY, "testhost")
        self.bridge.raise_("toolu_quick")
        self.bridge.settle("toolu_quick", outcome="allow", winner="other", by="cli")
        self.r.follow({self.sid: self.PID})
        frames = self.due(lambda fs: messages(fs, "settled"))
        self.assertEqual([m["body"]["request"] for m in messages(frames, "settled")], ["toolu_quick"])
        self.assertEqual(messages(frames, "raised"), [])
        self.r.sent(frames)
        again = requests.Requests(KEY, "testhost")
        try:
            again.follow({self.sid: self.PID})
            self.assertTrue(wait_for(lambda: again.take() or self.sid in again.synced))
            self.assertEqual(messages(again.due({self.PID})), [], "the hub took it: not sent again")
        finally:
            again.close()

    def test_the_outbox_keeps_every_settlement(self):
        with mock.patch.object(requests, "OUTBOX_MAX", 4):
            for i in range(3):
                self.bridge.raise_("toolu_r%d" % i)
                self.bridge.settle("toolu_r%d" % i)
            for i in range(3, 6):
                self.bridge.raise_("toolu_r%d" % i)
            frames = self.due(lambda fs: len(messages(fs, "settled")) == 3 and
                              "toolu_r5" in [m["body"]["request"] for m in messages(fs, "raised")])
        self.assertEqual([m["body"]["request"] for m in messages(frames, "settled")],
                         ["toolu_r0", "toolu_r1", "toolu_r2"], "an overflow drops no settlement")
        self.assertLess(len(messages(frames, "raised")), 6, "only raises, which the set rebuilds")
        self.assertEqual(sorted(x["request"] for x in self.r.pending_frame(self.PID)["raised"]),
                         ["toolu_r3", "toolu_r4", "toolu_r5"], "the set still holds every pending one")

    def test_a_raise_dropped_by_the_cap_is_repaired_on_the_open_stream(self):
        with mock.patch.object(requests, "OUTBOX_MAX", 4):
            for i in range(5):
                self.bridge.raise_("toolu_o%d" % i)
            frames = self.due(lambda fs: "toolu_o4" in [m["body"]["request"] for m in messages(fs, "raised")])
        self.assertEqual(len(messages(frames, "raised")), 4, "one raise dropped")
        sets = [f for f in frames if f.get("t") == "pending"]
        self.assertEqual(len(sets), 1, "and the complete set follows, with no reconnect")
        self.assertEqual(sorted(x["request"] for x in sets[0]["raised"]), ["toolu_o%d" % i for i in range(5)])
        self.assertIs(frames[-1], sets[0], "after the raises")
        self.r.sent(frames)
        self.assertEqual(self.r.due({self.PID}), [])

    def test_the_set_waits_for_the_bridges_snapshots(self):
        """An uplink starting with a request already pending: the complete
        set does not go empty before the bridge is read."""
        self.r.close()
        self.bridge.raise_("toolu_before")
        clock = [100.0]
        self.r = requests.Requests(KEY, "testhost", clock=lambda: clock[0])
        self.r.follow({self.sid: self.PID})
        first = self.r.opening(self.PID)
        self.assertEqual([f for f in first if f.get("t") == "pending"], [], "no set before its bridge is read")
        frames = self.due(lambda fs: [f for f in fs if f.get("t") == "pending"])
        self.assertEqual([x["request"] for f in frames if f.get("t") == "pending" for x in f["raised"]],
                         ["toolu_before"], "the set, once read, holds it")
        self.r.sent(frames)
        # A bridge that never gives a snapshot holds the set at most HOLD_MAX.
        stalled_sid = str(uuidlib.uuid4())
        stalled = tsp.fake_session.stalled_socket(os.path.join(os.environ["SMINOS_HOME"], "bridge",
                                                               stalled_sid + ".sock"))
        try:
            self.r.follow({self.sid: self.PID, stalled_sid: self.PID})
            self.assertEqual([f for f in self.r.opening(self.PID) if f.get("t") == "pending"], [])
            clock[0] += requests.HOLD_MAX + 1
            self.assertEqual([x["request"] for f in self.r.due({self.PID}) if f.get("t") == "pending"
                              for x in f["raised"]], ["toolu_before"], "then it goes with what is known")
        finally:
            stalled.close()
            os.unlink(os.path.join(os.environ["SMINOS_HOME"], "bridge", stalled_sid + ".sock"))

    def test_opening_a_project_republishes_the_set(self):
        self.bridge.raise_("toolu_p")
        self.due(lambda fs: messages(fs, "raised"))
        self.bridge.raise_("toolu_q")
        self.bridge.settle("toolu_p")
        self.due(lambda fs: len(messages(fs)) == 3)
        frames = self.r.opening(self.PID)
        self.assertEqual([f.get("t") if f.get("t") != "session" else f["message"]["kind"] for f in frames],
                         ["settled", "pending"],
                         "settlements not yet sent, then the complete set (raised ones it covers are not sent)")
        self.assertEqual([x["request"] for x in frames[-1]["raised"]], ["toolu_q"])
        self.r.sent(frames)
        self.assertEqual(self.r.due({self.PID}), [])


# ---------------------------------------------------------------- the uplink


class Uplink(unittest.TestCase):
    """Against the hub stand-in, or DC3's local hub when DESK_HUB is set."""

    @classmethod
    def setUpClass(cls):
        cls.procs = []
        bindir = os.path.join(T, "bin-pr")
        os.makedirs(bindir, exist_ok=True)
        with open(os.path.join(bindir, "claude"), "w") as f:
            f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
        os.chmod(os.path.join(bindir, "claude"), 0o755)
        os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        os.environ["SMINOS_DERIVE_EVERY"] = "0"
        cls.hub = tsp.make_hub(cls.spawn)
        cls.hub.enroll(CLI)
        with open(os.path.join(os.environ["SMINOS_HOME"], "daemon", "hub.json")) as f:
            cls.key = codes.b64url_bytes(json.load(f)["key"], 32)
        cls.root, cls.project = make_project("uplinked", cls.hub.url, cls.hub.org)
        subprocess.run(GIT + ["-C", cls.root, "commit", "-q", "--allow-empty", "-m", "base"], check=True)
        cls.session = Session(cls.root)
        cls.sid = cls.session.sid
        cls.bridge = Bridge(cls.sid)
        r = cli("daemon", "tick")
        assert r.returncode == 0, r.stderr
        cls.alias = member_of(project_of(cls.root), cls.sid).alias
        cls.uplink = cls.spawn([CLI, "daemon", "uplink"])
        cls.hub.follow(cls.project)
        ok = cls.hub.wait(lambda ms: any(m["kind"] == "presence" and m["session"] == cls.sid
                                         and m["body"]["bridge"] for m in ms), timeout=20)
        assert ok is not None, "the uplink connected and said the session's bridge"

    @classmethod
    def spawn(cls, argv):
        p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.procs.append(p)
        return p

    @classmethod
    def tearDownClass(cls):
        clear_policy()
        cls.bridge.stop()
        if isinstance(cls.hub, tsp.LocalHub):
            cls.hub.close()
        for p in reversed(cls.procs):
            p.terminate()
        for p in cls.procs:
            p.wait(10)
        cls.session.end()

    def tearDown(self):
        clear_policy()

    def local(self):
        return isinstance(self.hub, tsp.LocalHub)

    def mine(self, ms, kind):
        return [m for m in ms if m["kind"] == kind and m.get("session") == self.sid]

    def pending_sets(self):
        """The pending sets the hub holds for this machine, in order: from
        DX2 `pending` frames the uplink posted (the stand-in), or DX3
        `pending` frames a browser was sent (the local hub)."""
        if self.local():
            return [[r["raised"]["request"] for r in f["requests"] if r["machine"] == self.hub.machine]
                    for f in self.hub.socket.received() if f.get("t") == "pending"]
        out = []
        for p in self.hub.state()["posted"]:
            for line in p["body"].splitlines():
                f = json.loads(line) if line.strip() else {}
                if f.get("t") == "pending" and f.get("project") == self.project and p["status"] == 200:
                    out.append([r["request"] for r in f["raised"]])
        return out

    def test_a_requests_and_settlements_reach_the_hub_and_are_republished(self):
        count = len(self.hub.messages())
        self.bridge.raise_("toolu_up1", input_={"command": "make deploy"}, agentId="a7", truncated=True)
        ms = self.hub.wait(lambda ms: self.mine(ms[count:], "raised"))
        self.assertIsNotNone(ms, "raised reaches the hub")
        raised = self.mine(ms[count:], "raised")[0]["body"]
        self.assertEqual((raised["request"], raised["agentId"], raised["truncated"]), ("toolu_up1", "a7", True),
                         "a subagent's, its input capped: the hub takes both fields")
        self.assertTrue(codes.verifies(self.key, "raised", self.project, raised), "with its code")
        self.bridge.settle("toolu_up1", outcome="deny", winner="terminal", by="terminal")
        ms = self.hub.wait(lambda ms: self.mine(ms[count:], "settled"))
        self.assertIsNotNone(ms, "settled reaches the hub")
        settled = self.mine(ms[count:], "settled")[0]["body"]
        self.assertTrue(codes.verifies(self.key, "settled", self.project, settled))
        self.assertEqual((settled["request"], settled["outcome"]), ("toolu_up1", "deny"))
        self.bridge.raise_("toolu_up2")
        self.assertIsNotNone(self.hub.wait(lambda ms: [m for m in self.mine(ms[count:], "raised")
                                                       if m["body"]["request"] == "toolu_up2"]))
        # The stream drops while the uplink is held still, and a request is
        # raised meanwhile: the raise the uplink then tries to post belongs to
        # a stream that is over (refused stale-generation), so the hub learns
        # of it only from the complete set the next stream carries.
        sets = len(self.pending_sets())
        os.kill(self.uplink.pid, signal.SIGSTOP)
        try:
            self.hub.drop()
            self.bridge.raise_("toolu_up3")
        finally:
            os.kill(self.uplink.pid, signal.SIGCONT)
        got = wait_for(lambda: [s for s in self.pending_sets()[sets:] if "toolu_up3" in s], timeout=20)
        self.assertTrue(got, "the complete pending set, republished on the reconnect: %s" % self.pending_sets()[sets:])
        self.assertEqual(sorted(got[-1]), ["toolu_up2", "toolu_up3"], "everything still pending, and only that")
        self.assertEqual([m for m in self.mine(self.hub.messages(), "raised") if m["body"]["request"] == "toolu_up3"],
                         [], "carried by the set, not by a raise of its own")
        self.bridge.settle("toolu_up2")
        self.bridge.settle("toolu_up3")

    def test_d_the_ask_mods_dialog_reaches_the_hub_with_its_calls_tool_use_id(self):
        count = len(self.hub.messages())
        self.bridge.raise_("toolu_plugin_up", tool="AskUserQuestion",
                           input_={"questions": [{"question": "Ship it?", "options": [{"label": "yes"}]}]},
                           toolUseId="toolu_01up")
        ms = self.hub.wait(lambda ms: [m for m in self.mine(ms[count:], "raised")
                                       if m["body"]["request"] == "toolu_plugin_up"])
        self.assertIsNotNone(ms, "raised reaches the hub")
        raised = [m for m in self.mine(ms[count:], "raised") if m["body"]["request"] == "toolu_plugin_up"][0]["body"]
        self.assertEqual(raised["toolUseId"], "toolu_01up", "the hub relays it as received")
        self.assertTrue(codes.verifies(self.key, "raised", self.project, raised), "under the machine's code")
        self.bridge.settle("toolu_plugin_up", outcome="answered")

    def presences(self, ms):
        return [m["body"] for m in ms if m["kind"] == "presence" and m["session"] == self.sid]

    def test_c_an_uplink_restart_keeps_what_is_pending(self):
        """The uplink restarts (a daemon restart) while a request is
        pending: the first set the new process publishes holds it."""
        self.bridge.raise_("toolu_kept")
        self.assertIsNotNone(self.hub.wait(lambda ms: [m for m in self.mine(ms, "raised")
                                                       if m["body"]["request"] == "toolu_kept"]))
        sets = len(self.pending_sets())
        old = Uplink.uplink
        old.terminate()
        old.wait(10)
        count = len(self.hub.messages())
        Uplink.uplink = self.spawn([CLI, "daemon", "uplink"])
        self.assertIsNotNone(self.hub.wait(lambda ms: [m for m in ms[count:] if m["kind"] == "presence"
                                                       and m["session"] == self.sid], timeout=20),
                             "the new uplink is connected")
        if not self.local():
            got = wait_for(lambda: self.pending_sets()[sets:], timeout=15)
            self.assertTrue(got, "a set was published")
        time.sleep(1.0)
        after = self.pending_sets()[sets:]
        self.assertTrue(all("toolu_kept" in s for s in after),
                        "no set after the restart lacks it: %s" % after)
        self.bridge.settle("toolu_kept")

    def deliver_from_outside(self, text):
        """An outside-origin `human` to the session: through a browser of
        the local hub, or stored at the stand-in as the hub would store it."""
        if self.local():
            member = next(f["member"] for f in self.hub.socket.received() if f.get("t") == "welcome")
            draft = {"kind": "human", "from": "human", "member": member, "text": text,
                     "to": [{"session": self.sid, "alias": self.alias}], "created": sminos.now(ms=True)}
            sealed = codes.seal(self.key, "log", self.project, draft, codes.b64url(os.urandom(16)))
            self.hub.socket.send({"t": "human", "event": sealed})
            ack = wait_for(lambda: [f for f in self.hub.socket.received()
                                    if f.get("t") == "human-ack" and f["nonce"] == sealed["mac"]["nonce"]])
            self.assertTrue(ack, "the hub stored it")
            return {"writer": ack[0]["writer"], "seq": ack[0]["seq"]}
        Uplink.seq = getattr(Uplink, "seq", 0) + 1
        e = hub_human(self.key, self.project, self.sid, self.alias, text, Uplink.seq)
        status, body = tsp.call(self.hub.url, "POST", "/control/inject", {"project": self.project, "events": [e]})
        self.assertEqual(status, 200, body)
        return {"writer": e["writer"], "seq": e["seq"]}

    def test_b_delivery_outcomes_and_the_policy(self):
        count = len(self.hub.messages())
        key = self.deliver_from_outside("hello from the web")
        ms = self.hub.wait(lambda ms: [m for m in self.mine(ms[count:], "delivery") if m["body"]["event"] == key],
                           timeout=15)
        self.assertIsNotNone(ms, "a delivery outcome reaches the hub")
        d = [m for m in self.mine(ms[count:], "delivery") if m["body"]["event"] == key][0]["body"]
        self.assertEqual(d["outcome"], "delivered")
        self.assertTrue(codes.verifies(self.key, "delivery", self.project, d), "with its code")
        self.assertEqual(d["reason"], "pushed to the live session")
        self.assertIn("hello from the web", self.bridge.texts(), "through its bridge")

        count = len(self.hub.messages())
        r = cli("daemon", "policy", "--read-only", "on")
        self.assertEqual(r.returncode, 0, r.stderr)
        ms = self.hub.wait(lambda ms: [m for m in ms[count:] if m["kind"] == "machine"
                                       and m["body"]["policy"]["read_only"]], timeout=10)
        self.assertIsNotNone(ms, "the policy changed is published at once")
        key = self.deliver_from_outside("not on a read-only machine")
        ms = self.hub.wait(lambda ms: [m for m in self.mine(ms[count:], "delivery") if m["body"]["event"] == key],
                           timeout=15)
        self.assertIsNotNone(ms)
        d = [m for m in self.mine(ms[count:], "delivery") if m["body"]["event"] == key][0]["body"]
        self.assertEqual(d["outcome"], "refused-read-only")
        self.assertTrue(codes.verifies(self.key, "delivery", self.project, d))
        self.assertNotIn("not on a read-only machine", self.bridge.texts() + self.session.inbox.texts(),
                         "nothing delivered")

    def test_e_a_send_the_engine_dropped_after_submitted_reaches_the_hub_failed(self):
        """DC8.G5 end to end: the bridge answered `submitted` (DX4
        `delivered`), then reported the engine's drop; the next pass of the
        delivery path sends a second `delivery` for the same key, `failed`
        with the bridge's reason, under the machine's code."""
        import sminos_bridge as bridge
        self.bridge.refusing = "a Stop hook stands"
        try:
            count = len(self.hub.messages())
            key = self.deliver_from_outside("taken, then dropped")
            ofkey = lambda ms: [m["body"] for m in self.mine(ms[count:], "delivery") if m["body"]["event"] == key]  # noqa: E731
            self.assertIsNotNone(self.hub.wait(ofkey, timeout=15), "delivered first")
            self.assertTrue(wait_for(lambda: [r for r in bridge.load_kept(self.sid).get("refused") or []
                                              if r["key"] == key]), "the child kept the refusal")
            r = cli("daemon", "tick")
            self.assertEqual(r.returncode, 0, r.stderr)
            ms = self.hub.wait(lambda ms: [d for d in ofkey(ms) if d["outcome"] == "failed"], timeout=15)
            self.assertIsNotNone(ms, "a failed outcome for the same key reaches the hub")
            got = ofkey(ms)
            self.assertEqual([d["outcome"] for d in got], ["delivered", "failed"])
            self.assertIn("a Stop hook stands", got[-1]["reason"])
            self.assertEqual(got[-1]["session"], self.sid)
            self.assertTrue(codes.verifies(self.key, "delivery", self.project, got[-1]), "with its code")
        finally:
            self.bridge.refusing = None


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
