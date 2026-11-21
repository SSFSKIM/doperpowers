#!/usr/bin/env python3
"""Nothing is published under a channel id (CH1's M1:
docs/doperpowers/plans/2026-11-21-sminos-channels-ch1.md, the constraint of
that name, Interfaces §7 and §9).

- The checker (channel_wire.py) names each breach it is fed: a position the
  baseline holds for one channel with another event, or under a second
  channel; a `retired` under a channel with no older `joined` of its
  session there, or with a reason other than `moved`; and each frame and
  file of its breach list.
- A real uplink (sminos_uplink.run_rl10, in this process) against the
  endpoint stand-in, in process too, over a store an older copy's `join`
  wrote a `joined` into under a channel, the baseline taken before this code
  read it: a first connection and a reconnection, a channel a record of
  this machine names (opened without `follow`) and one none does (with
  `follow`), a `snapshots?` answered with one empty page and a `subscribe`
  with the `end` a session not held gets; the checker passes over the
  frames and the store, and the older `joined` goes up followed by this
  code's `retired`.

Hermetic: HOME, SMINOS_HOME and MAWS_USER_DATA are temporary; nothing
listens beyond a Unix socket there; the live sessions are `sleep`s.
Run: python3 -B sminos/tests/test_channels_wire.py
"""
import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")
BASE = tempfile.mkdtemp(prefix="smcw.", dir="/tmp")   # short: a Unix socket's path is bounded
for var in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
            "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR", "SMINOS_LAUNCH",
            "CLAUDE_PID", "MAWS_LAUNCHED_BY"):
    os.environ.pop(var, None)
os.environ.update(HOME=os.path.join(BASE, "home"), SMINOS_HOME=os.path.join(BASE, "s"), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import channel_wire as wire  # noqa: E402
import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_threads as threads  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

ORG, MACHINE, URL = "org-1", "testhost", "http://127.0.0.1:9"
CRED = {"org": ORG, "hub": URL, "machine": MACHINE, "key": None}
DESK = "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"     # a channel a record of this machine names
LOBBY = "0123abcd-4567-8abc-a123-456789abcdef"    # a channel no record names, where an older copy joined a session
APP = "7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"
S1 = "6c000001-0000-4000-8000-0000000000c1"
S2 = "6c000002-0000-4000-8000-0000000000c2"
W = "%s/%s" % (MACHINE, S2)


def ev(writer, seq, kind, **fields):
    return {"ts": "2026-11-21T00:00:%02d.000Z" % seq, "writer": writer, "seq": seq, "kind": kind, **fields}


# ------------------------------------------------------------- the checker's own


class Checker(unittest.TestCase):
    """Fed breaches, it names each; fed what is allowed, nothing."""

    joined = ev(W, 1, "joined", session=S2, alias="w", machine=MACHINE)
    before = {(LOBBY, W, 1): joined}

    def events(self, cid, *events):
        return {"t": "events", "project": cid, "events": list(events)}

    def test_what_is_allowed(self):
        retired = ev(W, 2, "retired", session=S2, reason="moved", project=APP)
        frames = [self.events(LOBBY, self.joined, retired, ev("%s/human" % MACHINE, 1, "channel-request", op="add"),
                              ev(W, 3, "void", of="x"), ev(W, 4, "channel-env", op="add")),
                  {"t": "hello", "project": LOBBY, "name": "lobby", "have": {}, "follow": True},
                  {"t": "member", "session": S1, "project": APP, "lane": "A", "state": "idle"},
                  {"t": "session", "message": {"project": DESK, "machine": MACHINE, "session": S1, "kind": "end",
                                               "sub": "s1", "n": 0, "body": {"reason": "error", "message": "no"}}},
                  {"t": "snapshots", "id": "a", "project": DESK, "events": [], "next": None, "done": True},
                  {"t": "reach?", "id": "r", "project": LOBBY, "session": S1, "event": {"kind": "channel-request"}},
                  (3, {"t": "member", "session": S1, "project": APP, "channels": [DESK]})]
        self.assertEqual(wire.published(frames, [DESK, LOBBY], self.before, welcomed={3}), [])

    def test_a_held_position_with_another_event_or_under_another_channel(self):
        other = dict(self.joined, alias="changed")
        got = wire.published([self.events(LOBBY, other)], [DESK, LOBBY], self.before)
        self.assertEqual(len(got), 1)
        self.assertIn("'joined' event under channel %s" % LOBBY, got[0])
        got = wire.published([self.events(DESK, self.joined)], [DESK, LOBBY], self.before)
        self.assertEqual(len(got), 1, "the baseline holds it for the lobby, not the desk")

    def test_a_retired_that_undoes_no_older_joined(self):
        for cid, retired in ((DESK, ev(W, 2, "retired", session=S2, reason="moved", project=APP)),
                             (LOBBY, ev(W, 2, "retired", session=S2, reason="ended")),
                             (LOBBY, ev(W, 2, "retired", session=S1, reason="moved", project=APP))):
            got = wire.published([self.events(cid, retired)], [DESK, LOBBY], self.before)
            self.assertEqual(len(got), 1, retired)
            self.assertIn("undoes no older joined", got[0])
        undone = dict(self.before)
        undone[(LOBBY, W, 2)] = ev(W, 2, "retired", session=S2, reason="moved", project=APP)
        got = wire.published([self.events(LOBBY, ev(W, 3, "retired", session=S2, reason="moved", project=APP))],
                             [LOBBY], undone)
        self.assertEqual(len(got), 1, "one already undone is no older joined")

    def test_each_frame_of_the_breach_list(self):
        def session(kind, pid=DESK, body=None):
            return {"t": "session", "message": {"project": pid, "machine": MACHINE, "session": S1, "kind": kind,
                                                "sub": None, "n": None, "body": body or {}}}
        breaches = [
            {"t": "member", "session": S1, "project": DESK, "lane": "A", "state": "idle"},
            session("presence"), session("machine"), session("host"), session("rows"), session("settled"),
            session("end", body={"reason": "unsubscribed"}),
            {"t": "pending", "project": DESK, "pending": []},
            {"t": "words?", "id": "w", "project": DESK, "session": S1, "event": {"kind": "human"}},
            {"t": "reach?", "id": "r", "project": DESK, "session": S1, "event": {"kind": "say"}},
            {"t": "snapshots", "id": "a", "project": DESK, "events": [self.joined], "next": None, "done": True},
            self.events(DESK, ev(W, 9, "say", text="x")),
            self.events(DESK, ev(W, 9, "channels", channels=[])),
            (1, {"t": "member", "session": S1, "project": APP, "channels": []}),
            (1, {"t": "member", "session": S1, "project": APP, "channels": [DESK] * 129}),
            (1, {"t": "member", "session": S1, "project": APP, "channels": [APP]}),
            (2, {"t": "member", "session": S1, "project": APP, "channels": [DESK]}),
        ]
        for f in breaches:
            got = wire.published([f], [DESK, LOBBY], self.before, welcomed={1})
            self.assertEqual(len(got), 1, (f, got))

    def test_the_store(self):
        home = tempfile.mkdtemp(dir=BASE)
        log = os.path.join(home, "projects", LOBBY, "log")
        os.makedirs(log)
        with open(os.path.join(log, "%s.%s.jsonl" % (MACHINE, S2)), "w") as f:
            f.write(json.dumps(self.joined) + "\n")
        before = wire.baseline(home, [DESK, LOBBY])
        self.assertEqual(before, self.before)
        self.assertEqual(wire.written(home, [DESK, LOBBY], MACHINE, before), [])
        with open(os.path.join(log, "%s.%s.jsonl" % (MACHINE, S2)), "a") as f:
            f.write(json.dumps(ev(W, 2, "retired", session=S2, reason="moved", project=APP)) + "\n")
        with open(os.path.join(log, "other.%s.jsonl" % S1), "w") as f:
            f.write(json.dumps(ev("other/" + S1, 1, "say", text="another machine's")) + "\n")
        self.assertEqual(wire.written(home, [DESK, LOBBY], MACHINE, before), [], "the undo; another machine's writer")
        self.assertEqual(len(wire.written(home, [DESK, LOBBY], ("x", "other"), before)), 1, "a name it held before")
        with open(os.path.join(log, "%s.%s.jsonl" % (MACHINE, S1)), "w") as f:
            f.write(json.dumps(ev("%s/%s" % (MACHINE, S1), 1, "state", session=S1, state="idle")) + "\n")
        for d, name in (("host", "%s.%s.jsonl" % (MACHINE, S1)), ("delivered", S1 + ".json")):
            os.makedirs(os.path.join(home, "projects", LOBBY, d))
            open(os.path.join(home, "projects", LOBBY, d, name), "w").close()
        got = wire.written(home, [DESK, LOBBY], MACHINE, before)
        self.assertEqual(len(got), 3, got)
        self.assertEqual(len(wire.written(home, [DESK, LOBBY], MACHINE, before, deliveries=False)), 2)


# ------------------------------------------------------------- a real uplink


def wait_for(pred, timeout=30, step=0.05):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(step)
    return pred()


class Wire(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp(dir=BASE)
        os.environ.update(HOME=os.path.join(home, "h"), SMINOS_HOME=os.path.join(home, "s"),
                          MAWS_USER_DATA=os.path.join(home, "m"), DAEMON_HOST=MACHINE)
        for d in (os.environ["HOME"] + "/.claude/sessions", os.environ["SMINOS_HOME"] + "/daemon"):
            os.makedirs(d, mode=0o700)
        self.home = home
        self.procs = []
        self.addCleanup(self.stop_all)
        sminos.write_json(rl10.identity_path(), {
            "org": ORG, "hub": URL, "name": MACHINE, "former": {}, "ref": "machine-ref-1",
            "enrolled": "2026-11-10T00:00:00.000Z", "cutover": "2026-11-10T00:00:01.000Z", "build": "b"}, mode=0o600)
        sminos.forget_caches()
        self.org = {"projects": [{"id": APP, "name": "app", "kind": "hub", "retired": False},
                                 {"id": DESK, "name": "desk-integration", "kind": "hub", "retired": False},
                                 {"id": LOBBY, "name": "lobby", "kind": "hub", "retired": False}],
                    "machines": [{"name": MACHINE, "online": False}], "complete": True}
        self.assertTrue(uplink.keep_org(self.org, CRED))
        self.root = os.path.join(home, "app")
        os.makedirs(self.root)
        with open(os.path.join(self.root, ".smns"), "w") as f:
            json.dump({"project": APP, "name": "app", "hub": {"org": ORG}}, f)
        sminos.forget_caches()
        self.app, self.lobby = sminos.known_project(APP), sminos.known_project(LOBBY)
        sminos.project_path(sminos.resolve_project(self.root), "log")

    def stop_all(self):
        for proc in self.procs:
            proc.kill()
            proc.wait()
        sminos.forget_caches()

    def live(self, sid, name):
        proc = subprocess.Popen(["sleep", "600"])
        self.procs.append(proc)
        with open(os.path.join(os.environ["HOME"], ".claude", "sessions", "%d.json" % proc.pid), "w") as f:
            json.dump({"pid": proc.pid, "sessionId": sid, "cwd": self.root, "kind": "interactive", "name": name,
                       "nameSource": "user", "status": "idle"}, f)
        sminos.forget_caches()

    def endpoint(self):
        ep = endpoint_standin.Endpoint(os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint"),
                                       org=self.org)
        ep.start()
        self.addCleanup(ep.stop)
        return ep

    def uplink(self):
        halt, box = threading.Event(), {}
        thread = threading.Thread(target=lambda: box.update(kept=uplink.run_rl10(halt.is_set, halt)), daemon=True)
        thread.start()

        def stop():
            halt.set()
            thread.join(30)
            if box.get("kept") is not None:
                box["kept"].close()
        self.addCleanup(stop)
        return stop

    def hellos(self, ep, conn):
        return {pid: p["follow"] for pid, p in ep.opened()["projects"].items()} if ep.opened()["conn"] == conn else {}

    def test_an_uplink_over_a_store_an_older_copy_joined_into_a_channel(self):
        # An older copy's `sminos join lobby` of a running session: its override, and a joined in the channel.
        self.live(S2, "older")
        sminos.write_override(S2, LOBBY)
        sminos.log_append(self.lobby, W, "joined", session=S2, alias="older", name_source="user", machine=MACHINE,
                          cwd=self.root, worktree="", role="", seat="", by="join")
        ids = [DESK, LOBBY]
        before = wire.baseline(os.environ["SMINOS_HOME"], ids)
        self.assertEqual(len(before), 1)
        # A thread of this machine in the desk, staged in its record.
        self.live(S1, "worker")
        sminos.view_of(self.app)
        t = threads.thread_of(S1)
        path = os.path.join(threads.store_dir(), t["thread"] + ".json")
        with open(path) as f:
            rec = json.load(f)
        rec["channels"] = [DESK]
        sminos.write_json(path, rec)
        sminos.forget_caches()
        with contextlib.redirect_stdout(io.StringIO()):
            daemon.tick_all(quiet=True)   # the channel pass undoes the older joined
        ep = self.endpoint()
        self.uplink()
        ep.wait_until(lambda: self.hellos(ep, 1).keys() >= {APP, DESK, LOBBY})
        self.assertEqual({k: v for k, v in self.hellos(ep, 1).items() if k in ids}, {DESK: False, LOBBY: True},
                         "the desk opened without follow, a thread here being in it; the lobby followed")
        ep.wait_until(lambda: 2 in ep.logs.get(LOBBY, {}).get(W, {}))
        self.assertEqual([ep.logs[LOBBY][W][n]["kind"] for n in (1, 2)], ["joined", "retired"],
                         "the older joined goes up in its writer's order, this code's retired after it")
        member = ep.wait(lambda f: f["t"] == "member" and f.get("session") == S1)
        self.assertEqual(member["project"], APP)
        ep.send({"t": "snapshots?", "id": "snap-1", "project": DESK})
        snap = ep.wait(lambda f: f["t"] == "snapshots" and f.get("id") == "snap-1")
        self.assertEqual((snap["events"], snap["next"], snap["done"]), ([], None, True))
        ep.send({"t": "snapshots?", "id": "snap-2", "project": LOBBY})
        snap = ep.wait(lambda f: f["t"] == "snapshots" and f.get("id") == "snap-2")
        self.assertEqual(snap["events"], [], "an older copy's joined there is no member's snapshot")
        ep.send({"t": "subscribe", "project": DESK, "session": S1, "sub": "sub-1", "agentId": None})
        end = ep.wait(lambda f: f["t"] == "session" and f["message"].get("sub") == "sub-1")
        self.assertEqual((end["message"]["kind"], end["message"]["body"]["reason"]), ("end", "error"))
        # A reconnection restates everything: the same holds.
        ep.drop()
        ep.wait_until(lambda: self.hellos(ep, 2).keys() >= {APP, DESK, LOBBY})
        self.assertEqual({k: v for k, v in self.hellos(ep, 2).items() if k in ids}, {DESK: False, LOBBY: True})
        ep.wait(lambda f: f["t"] == "restated")
        time.sleep(0.5)   # what a tick after the restatement sends
        self.assertEqual(wire.published(ep.received, ids, before), [])
        self.assertEqual(wire.written(os.environ["SMINOS_HOME"], ids, MACHINE, before), [])
        self.assertFalse([f for f in ep.frames("session") if f["message"].get("project") in ids
                          and f["message"].get("kind") != "end"])


if __name__ == "__main__":
    unittest.main()
