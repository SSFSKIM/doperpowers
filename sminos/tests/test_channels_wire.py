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
import fcntl
import re
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

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
import sminos_channels as channels  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_records as records  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_threads as threads  # noqa: E402
import sminos_uplink as uplink  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import test_threads as T1  # noqa: E402 — its fixtures by module
from test_channels_requests import OTHER, SAME_ID, SIGNER, Requests  # noqa: E402
from test_channels_delivery import FAR, W1, W2, Receipts  # noqa: E402
from test_channels_delivery import Channel as Delivering  # noqa: E402
import uuid as uuidlib  # noqa: E402

LIMIT = threads.CHANNEL_LIMIT

ORG, MACHINE, URL = "org-1", "testhost", "http://127.0.0.1:9"
CRED = {"org": ORG, "hub": URL, "machine": MACHINE, "key": None}
DESK = "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"     # a channel a record of this machine names
LOBBY = "0123abcd-4567-8abc-a123-456789abcdef"    # a channel no record names, where an older copy joined a session
APP = "7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"
ELSEWHERE = "3e4f5a6b-7c8d-4e9f-a0b1-c2d3e4f5a6b7"
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

    def test_an_events_frame_of_a_channel_left_out_of_the_list(self):
        got = wire.published([self.events(DESK, ev(W, 1, "joined", session=S2, alias="w", machine=MACHINE))],
                             [LOBBY], self.before)
        self.assertEqual(len(got), 1, "a channel id is a channel's by its form, as in every other branch")
        self.assertIn("'joined' event under channel %s" % DESK, got[0])
        self.assertEqual(wire.published([self.events(APP, self.joined)], [LOBBY], self.before), [], "a project's")

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
            session("delivery", body={"event": {"writer": W, "seq": 1}, "outcome": "sent"}),
            {"t": "pending", "project": DESK, "pending": []},
            {"t": "words?", "id": "w", "project": DESK, "session": S1, "event": {"kind": "say"}},
            {"t": "words?", "id": "w", "project": DESK, "session": S1, "event": {"kind": "channel-request"}},
            {"t": "reach?", "id": "r", "project": DESK, "session": S1, "event": {"kind": "channel-env"}},
            {"t": "reach?", "id": "r", "project": DESK, "session": S1, "event": {"kind": "channel-lead"}},
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

    def test_what_is_said_in_a_channel_is_allowed_with_the_spoken_kinds(self):
        """CH2's M4: a message in a channel's log, a member's and an outsider's, a person's and a notice."""
        to = [{"session": S1, "alias": "w", "thread": S2}]
        spoken = [ev(W, 5, "say", to=to, text="x", thread=S1), ev(W, 6, "say", to="*", text="y", thread=S1),
                  ev(W, 7, "say", to=to, text="z", thread=S1, from_project=APP),
                  ev("%s/human" % MACHINE, 2, "human", to=to, text="h"),
                  ev("%s/human" % MACHINE, 3, "human", to="*", text="n", notice="devcloud")]
        self.assertEqual(wire.published([self.events(DESK, *spoken)], [DESK], {}, allowed=wire.ALLOWED_SPOKEN), [])
        self.assertEqual(len(wire.published([self.events(DESK, *spoken)], [DESK], {})), len(spoken),
                         "each a breach under CH1's kinds")

    def test_the_questions_about_a_message_under_a_channels_id(self):
        """CH2's M6 (its §8): a `words?` about a `human`, and a `reach?` about a `say`, a `human` or a request, under
        a channel's id, are allowed; about anything else each is a breach (test_each_frame_of_the_breach_list)."""
        asked = [{"t": "words?", "id": "w", "project": DESK, "session": S1, "event": {"kind": "human"}}] + [
            {"t": "reach?", "id": "r", "project": DESK, "session": S1, "event": {"kind": k}}
            for k in ("say", "human", "channel-request")]
        self.assertEqual(wire.published(asked, [DESK], {}, allowed=wire.ALLOWED_SPOKEN), [])
        self.assertEqual(wire.published(asked, [DESK], {}), [], "a rule of the checker's, not of its arguments")

    def test_a_frame_of_a_shape_it_does_not_know_is_refused(self):
        """CH2's M5 found the stand-in's control `state()["received"]` (dicts of `conn` and `frame`) read as bare
        frames, each passing unchecked: a frame is a dict with a `t`, or a stand-in's (number, frame); anything else
        is refused, never passed by."""
        member = {"t": "member", "session": S1, "project": DESK}
        self.assertEqual(len(wire.published([member], [DESK])), 1)
        self.assertEqual(len(wire.published([(1, member)], [DESK])), 1)
        for shape in ({"conn": 1, "frame": member}, [1, member], (1, member, 2), "member", None, {"t": 7}):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                wire.published([shape], [DESK])

    def test_each_breach_of_a_spoken_event_on_the_wire_and_on_disk(self):
        to = [{"session": S1, "alias": "w", "thread": S2}]
        human = "%s/human" % MACHINE
        breaches = {
            "copy": ev(W, 5, "say", to=to, text="x", copy="%s:%s:1" % (APP, W)),
            "from_project": ev(human, 2, "human", to=to, text="h", from_project=APP),
            "a lead's from_project": ev(human, 3, "channel-lead", thread=S2, session=S1, from_project=APP),
            "no thread": ev(W, 6, "say", to=[{"session": S1, "alias": "w"}], text="x"),
            "a thread of no string": ev(human, 4, "human", to=[{"session": S1, "alias": "w", "thread": 7}], text="x"),
        }
        for why, e in breaches.items():
            got = wire.published([self.events(DESK, e)], [DESK], {}, allowed=wire.ALLOWED_SPOKEN)
            self.assertEqual(len(got), 1, (why, got))
            home = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, home)
            log = os.path.join(home, "projects", DESK, "log")
            os.makedirs(log)
            with open(os.path.join(log, "w.jsonl"), "w") as f:
                f.write(json.dumps(e) + "\n")
            got = wire.written(home, [DESK], MACHINE, {}, allowed=wire.ALLOWED_SPOKEN, deliveries=False)
            self.assertEqual(len(got), 1, (why, got))

    def test_the_older_copy_suites_upload_order_is_first_receipt(self):
        """older_channel_wire.first_received (test-older-cli.sh's wire check) reads the order the stand-in first
        received each position in, across frames and within one: a `retired` sent before the older `joined`
        reads so, and a position sent again counts where it first came."""
        import older_channel_wire
        joined, retired = ev(W, 1, "joined", session=S2), ev(W, 2, "retired", session=S2, reason="moved")

        class Ep:
            cv = threading.Lock()

            def __init__(self, *frames):
                self.received = [(1, {"t": "events", "project": LOBBY, "events": list(f)}) for f in frames]
        self.assertEqual(older_channel_wire.first_received(Ep([joined, retired]), LOBBY), [(W, ["joined", "retired"])])
        self.assertEqual(older_channel_wire.first_received(Ep([retired, joined]), LOBBY), [(W, ["retired", "joined"])])
        self.assertEqual(older_channel_wire.first_received(Ep([retired], [joined, retired]), LOBBY),
                         [(W, ["retired", "joined"])])
        self.assertEqual(older_channel_wire.first_received(Ep([joined]), DESK), [])

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
        self.assertEqual(len(wire.written(home, [DESK, LOBBY], MACHINE, before, deliveries=False)), 3,
                         "an empty file is no record of writer entries")

    def test_a_channels_delivery_records_under_deliveries_false(self):
        """CH2's M2: allowed with deliveries=False is a thread's record, by its id, and its lock; a file named
        by anything else (a person's, `human.json`), or one that is no record, is a breach either way."""
        self.assertEqual(wire.PUSHED, sminos.PUSHED, "the checker's copy of what a pushed note may say")
        home = tempfile.mkdtemp(dir=BASE)
        d = os.path.join(home, "projects", DESK, "delivered")
        os.makedirs(d)
        for name, body in ((S1 + ".json", {"%s/x" % MACHINE: {"settled": 2, "pending": 3, "attempts": 1,
                                                               "pushed": [3, "sent"], "revoked": [5],
                                                               "held": [[4, S1]]}}),
                           (S2 + ".json", {}), (S1 + ".lock", None)):
            with open(os.path.join(d, name), "w") as f:
                if body is not None:
                    json.dump(body, f)
        self.assertEqual(wire.written(home, [DESK], MACHINE, deliveries=False), [])
        self.assertEqual(len(wire.written(home, [DESK], MACHINE)), 1, "CH1's rule, the default: any record")
        for name, body in (("human.json", "{}"), ("x.tmp", ""), (S2 + ".json", "[]"), (S2 + ".json", '{"w": 3}'),
                           (S2 + ".json", "{torn"), (S2 + ".json", '{"w": {"settled": "x"}}'),
                           (S2 + ".json", '{"w": {}}'), (S2 + ".json", '{"w": {"settled": null, "pending": null, '
                                                                   '"attempts": 0}}'),
                           (S2 + ".json", '{"w": {"settled": 1, "pending": null, "attempts": 0, "revoked": "2"}}'),
                           (S2 + ".json", '{"w": {"settled": 1, "pending": null, "attempts": 0, "held": [[2]]}}')):
            with self.subTest(name=name, body=body):
                with open(os.path.join(d, name), "w") as f:
                    f.write(body)
                got = wire.written(home, [DESK], MACHINE, deliveries=False)
                self.assertEqual(len(got), 1, got)
                if name != S2 + ".json":
                    os.unlink(os.path.join(d, name))
                else:
                    with open(os.path.join(d, name), "w") as f:
                        f.write("{}")


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
        self.org = {"projects": [{"id": APP, "name": "app", "kind": "hub", "retired": False}] + (
                        [{"id": DESK, "name": "desk-integration", "kind": "hub", "retired": False},
                         {"id": LOBBY, "name": "lobby", "kind": "hub", "retired": False}]
                        if getattr(self, "channels_in_org", True) else []),
                    "machines": [{"name": MACHINE, "online": False}], "complete": True}
        self.assertTrue(uplink.keep_org(self.org, CRED))
        self.root = os.path.join(home, "app")
        os.makedirs(self.root)
        with open(os.path.join(self.root, ".smns"), "w") as f:
            json.dump({"project": APP, "name": "app", "hub": {"org": ORG}}, f)
        sminos.forget_caches()
        self.app, self.lobby = sminos.known_project(APP), sminos.known_project(LOBBY)   # no lobby without channels
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
        ep.wait_until(lambda: ep.restatement_applied(2))   # applied, not only received
        time.sleep(0.5)   # what a tick after the restatement sends
        self.assertEqual(wire.published(ep.received, ids, before), [],
                         "a welcome that listed no channels: no member frame carries the key")
        self.assertEqual(wire.written(os.environ["SMINOS_HOME"], ids, MACHINE, before), [])
        self.assertFalse([f for f in ep.frames("session") if f["message"].get("project") in ids
                          and f["message"].get("kind") != "end"])



# ------------------------------------------------------------- M6: the member frame's channels


class Lane:
    """A Link's lane that keeps what it is sent, written as taken at once."""

    def __init__(self):
        self.sent = []

    def send(self, frames, then=None):
        self.sent += frames
        if then is not None:
            then()

    def posting(self):
        return False

    def queued(self):
        return 0

    def close(self):
        pass


def set_record(sid, **fields):
    """The record of the thread whose current session `sid` is, its fields
    written as given (staged: the tests of M2 hold the operation's own)."""
    t = threads.thread_of(sid)
    path = os.path.join(threads.store_dir(), t["thread"] + ".json")
    with open(path) as f:
        rec = json.load(f)
    rec.update(fields)
    sminos.write_json(path, rec)
    sminos.forget_caches()
    return t["thread"]


class Frame(unittest.TestCase):
    """member_frame's `channels`: given and lane A, the frame's last key, a
    list; otherwise no key, never an empty list."""

    def member(self, record):
        return sminos.Member(session=S1, short=S1[:8], alias="w", name_source="user", machine=MACHINE, local=True,
                             state="idle", state_age=None, charge="", charge_source="", status="", by="", worktree="",
                             seat=None, record=record)

    def test_the_key_last_for_lane_a_and_absent_otherwise(self):
        lane_a = {"owners": ["@machine"], "origin": {"kind": "terminal"}}
        frame = uplink.member_frame(APP, self.member(lane_a), "launch-1", True, (DESK, LOBBY))
        self.assertEqual(list(frame)[-1], "channels")
        self.assertEqual(frame["channels"], [DESK, LOBBY])
        self.assertEqual(frame["project"], APP, "the thread's own project, never a channel")
        self.assertNotIn("channels", uplink.member_frame(APP, self.member(lane_a), None, True, ()))
        self.assertNotIn("channels", uplink.member_frame(APP, self.member(lane_a)), "by default none")
        lane_b = {**lane_a, "controller": {"lane": "B", "since": "2026-11-21T00:00:00Z"}}
        self.assertNotIn("channels", uplink.member_frame(APP, self.member(lane_b), None, True, (DESK,)),
                         "a lane B session is no thread of a channel")
        self.assertEqual(uplink.member_frame(APP, self.member(lane_a), None, True, ()),
                         uplink.member_frame(APP, self.member(lane_a), None, True),
                         "a thread in none: today's frame")


class FrameKey(unittest.TestCase):
    """What the frame carries is the record's set as channels_of reads it
    (frame_channels), and the frame is built again when that set changes,
    and only then; without the welcome's word nothing of it is read."""

    setUp = Wire.setUp
    stop_all = Wire.stop_all
    live = Wire.live

    def row(self, sid):
        sminos.forget_caches()
        return next(m for m in sminos.view_of(self.app).members if m.session == sid)

    def link(self, serves=True):
        link = uplink.Link(CRED, {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.serves_channels = serves
        return link

    def test_frame_channels_is_channels_of_as_the_frame_carries_it(self):
        self.live(S1, "worker")
        self.row(S1)
        self.assertEqual(channels.frame_channels(S1), (), "a thread in no channel")
        set_record(S1, channels=[DESK, "not-a-channel", APP, LOBBY])
        self.assertEqual(channels.frame_channels(S1), (DESK, LOBBY), "the entries that are channels' ids")
        self.assertEqual(channels.frame_channels(S1), tuple(c for c in channels.channels_of(S1)
                                                            if sminos.is_channel_id(c)))
        many = ["%08x-0000-8000-8000-000000000000" % n for n in range(LIMIT + 2)]
        set_record(S1, channels=many)
        self.assertEqual(channels.frame_channels(S1), tuple(many[:LIMIT]), "the first 128")
        set_record(S1, channels=[DESK], ended="2026-11-21T00:00:00.000Z")
        self.assertEqual(channels.frame_channels(S1), (), "an ended thread's set is not carried")
        self.assertEqual(channels.frame_channels(S2), (), "a session that is no thread")
        self.assertEqual(channels.frame_channels(""), ())

    def test_built_again_when_the_set_changes_and_only_then(self):
        self.live(S1, "worker")
        link = self.link()

        def build():
            with mock.patch.object(uplink, "member_frame", wraps=uplink.member_frame) as built:
                frame = link.fresh_frame(APP, self.row(S1))
            return built.call_count, frame

        n, frame = build()
        self.assertEqual((n, "channels" in frame), (1, False), "a thread in none: no key")
        self.assertEqual(build()[0], 0, "nothing moved: not built again")
        set_record(S1, channels=[DESK])
        n, frame = build()
        self.assertEqual((n, frame.get("channels")), (1, [DESK]), "its set changed: built again, carrying it")
        self.assertEqual(build()[0], 0)
        set_record(S1, channels=[])
        n, frame = build()
        self.assertEqual((n, "channels" in frame), (1, False), "emptied: no key, never an empty list")

    def test_without_the_welcome_s_word_no_key_and_nothing_read(self):
        self.live(S1, "worker")
        self.row(S1)
        set_record(S1, channels=[DESK])
        link = self.link(serves=False)
        with mock.patch.object(channels, "frame_channels", side_effect=AssertionError("read")) as read:
            frame = link.fresh_frame(APP, self.row(S1))
        self.assertNotIn("channels", frame)
        self.assertEqual(read.call_count, 0, "a welcome that lists no channels costs the frame nothing")
        self.assertEqual(self.link().fresh_frame(APP, self.row(S1))["channels"], [DESK])

    def test_the_welcome_s_word(self):
        link = self.link(serves=False)
        with mock.patch.object(uplink.audience, "keep_capabilities"), \
                mock.patch.object(link, "on_policy"):
            link.welcomed_rl10({"capabilities": ["access", "channels"]})
            self.assertTrue(link.serves_channels)
            link.welcomed_rl10({"capabilities": ["access"]})
            self.assertFalse(link.serves_channels)
            link.welcomed_rl10({})
            self.assertFalse(link.serves_channels)


class NoChannelHere(unittest.TestCase):
    """The holder's ruling on the idle cost: under a welcome that lists
    `channels`, a machine where no channel is registered asks for no
    thread's set at a publish (sminos.channels_here first: a thread's set
    names channels registered here); once one is, the set is read."""

    channels_in_org = False
    setUp = Wire.setUp
    stop_all = Wire.stop_all
    live = Wire.live
    row = FrameKey.row
    link = FrameKey.link

    def publish(self, link):
        link.member_known = {APP: self.app}
        link.plane.member_rows = {APP: {S1: self.row(S1)}}
        with mock.patch.object(threads, "set_holders", wraps=threads.set_holders) as asked:
            link.publish_members(0.0)
            link.fresh_frame(APP, self.row(S1))
        return asked.call_count

    def test_no_holders_asked_on_a_machine_with_no_channel(self):
        self.live(S1, "worker")
        self.row(S1)
        self.assertFalse(sminos.known_channels())
        link = self.link(serves=True)
        self.assertEqual(self.publish(link), 0, "no channel registered: no thread's set looked up")
        self.assertNotIn("channels", link.session_lane.sent[-1])
        channels.register(DESK, "desk-integration")
        set_record(S1, channels=[DESK])
        self.assertGreater(self.publish(link), 0, "a channel registered here: the holders are read")
        self.assertEqual([f.get("channels") for f in link.session_lane.sent if f.get("session") == S1][-1], [DESK])


class WireWithChannels(unittest.TestCase):
    """A real uplink against a stand-in that serves channels: the thread's
    member frame carries its set while its welcome listed `channels`; a
    channel's hello loses and gains `follow` as the last record naming it
    goes and returns, with no `machine` frame either way; and the checker
    passes over a first connection and a reconnection."""

    setUp = Wire.setUp
    stop_all = Wire.stop_all
    live = Wire.live
    uplink = Wire.uplink
    hellos = Wire.hellos

    def endpoint(self):
        ep = endpoint_standin.Endpoint(os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint"),
                                       org=self.org, capabilities=["channels"])
        ep.start()
        self.addCleanup(ep.stop)
        return ep

    def channel_hellos(self, ep):
        return [(n, f.get("follow") is True) for n, f in ep.received if f.get("t") == "hello"
                and f.get("project") == DESK]

    def test_the_set_on_the_frame_and_the_channel_s_hello(self):
        self.live(S1, "worker")
        self.live(S2, "other")
        sminos.view_of(self.app)
        set_record(S1, channels=[DESK])
        ids = [DESK, LOBBY]
        before = wire.baseline(os.environ["SMINOS_HOME"], ids)
        ep = self.endpoint()
        self.uplink()
        ep.wait_until(lambda: self.hellos(ep, 1).keys() >= {APP, DESK, LOBBY})
        self.assertFalse(self.hellos(ep, 1)[DESK], "the desk opened without follow")
        frame = ep.wait(lambda f: f["t"] == "member" and f.get("session") == S1)
        self.assertEqual((frame["project"], frame["channels"]), (APP, [DESK]))
        other = ep.wait(lambda f: f["t"] == "member" and f.get("session") == S2)
        self.assertNotIn("channels", other, "a thread in none carries no key")
        ep.wait_until(lambda: ep.restatement_applied(1))   # applied, not only received
        self.assertEqual(ep.known(), {APP, DESK}, "the stand-in counts the desk as known")
        # The last record naming the desk lets it go: followed again, and the frame without the key.
        set_record(S1, channels=[])
        uplink_nudge()
        ep.wait_until(lambda: self.channel_hellos(ep)[-1:] == [(1, True)])
        ep.wait(lambda f: f["t"] == "member" and f.get("session") == S1 and "channels" not in f)
        ep.wait_until(lambda: DESK not in ep.known())
        set_record(S1, channels=[DESK])
        uplink_nudge()
        ep.wait_until(lambda: self.channel_hellos(ep)[-1:] == [(1, False)])
        ep.wait_until(lambda: DESK in ep.known())
        self.assertEqual([h for h in self.channel_hellos(ep)], [(1, False), (1, True), (1, False)])
        ep.drop()
        ep.wait_until(lambda: self.hellos(ep, 2).get(DESK) is False)
        ep.wait_until(lambda: on(ep, 2, lambda f: f["t"] == "member" and f.get("session") == S1
                                 and f.get("channels") == [DESK]))
        ep.wait_until(lambda: ep.restatement_applied(2))   # applied, not only received
        self.assertIn(DESK, ep.known(), "after connection 2's own restatement, from its own frames")
        time.sleep(0.5)
        welcomed = {n for n, w in ep.welcomes if "channels" in w["capabilities"]}
        self.assertEqual(welcomed, {1, 2})
        self.assertEqual(wire.published(ep.received, ids, before, welcomed=welcomed), [])
        self.assertEqual(wire.written(os.environ["SMINOS_HOME"], ids, MACHINE, before), [])
        self.assertFalse([f for f in ep.frames("session") if f["message"].get("project") in ids
                          and f["message"].get("kind") != "end"], "no machine frame, no presence, either way")
        self.assertFalse([f for f in ep.frames("member") if f.get("channels") == []], "never an empty list")


# ------------------------------------------------------------- M7: requests across machines, the endpoint's word


class Asks(Requests, T1.Sessions):
    """The ask pass's requests and the answer's path (M7), a Link's own over
    a real store: one `reach?` per request the pass left pending `endpoint`,
    after its thread's member frame, under the event it asks about; the
    answer handed to carry_due under that key and binding, used once."""

    def setUp(self):
        os.environ.pop("MAWS_USER_DATA", None)
        super().setUp()

    def link(self, reach=True, serves=True, open_desk=True):
        link = uplink.Link(dict(CRED, machine=sminos.host_name()), {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.reach, link.serves_channels = reach, serves
        if open_desk:
            link.logs[DESK] = hublog.HubLog(self.chan(DESK), link.cred)
            link.opened.add(DESK)
            link.channels.add(DESK)
        return link

    def ask_pass(self, link):
        """One tick's ask pass, as Link.tick runs it: the members the plane reads (Link.members, a reconciling read,
        due now), then the words pass. The ask itself reads frames as they are (C1)."""
        sminos.forget_caches()
        link.next_member_read = 0.0
        link.members(time.monotonic())
        sminos.forget_caches()
        link.ask_words({})

    def asks(self, link):
        return [f for f in link.session_lane.sent if f.get("t") == "reach?"]

    def answer(self, link, ask, verdict, carried=True, **more):
        """The endpoint's answer on `ask`, and (`carried`) the requests' pass it makes due, which uses the word
        (the receive loop only keeps it: A7)."""
        sminos.forget_caches()
        link.on_reach({"t": "reach", "id": ask["id"], "verdict": verdict, **more}, None)
        if carried:
            sminos.forget_caches()
            link.ask_requests()

    def test_one_ask_per_request_due_and_none_for_one_that_needs_no_word(self):
        tid, sid, _ = self.human()
        tid2, sid2, _ = self.human()
        own = self.request(DESK, "add", sid, tid)                    # this machine's person: honoured, no word
        e = self.remote(DESK, "add", sid2, tid2)                     # another machine's session: the endpoint's word
        self.remote(DESK, "add", sid2, tid2, ts="2026-11-01T00:00:00.000Z")   # expired: never asked
        self.remote(DESK, "add", sid, "f" * 32)                      # names no thread here: never asked
        link = self.link()
        self.ask_pass(link)
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.assertEqual(self.held(tid), [DESK], "the pass carried out what needed no word")
        self.assertEqual(ask["project"], DESK)
        self.assertEqual(ask["session"], sid2, "the thread's current session")
        self.assertEqual(ask["event"], {k: v for k, v in e.items() if k != "verified"}, "the request, as stored")
        self.assertNotEqual(own["id"], e["id"])
        at = link.session_lane.sent.index(ask)
        members = [f for f in link.session_lane.sent[:at] if f.get("t") == "member" and f.get("session") == sid2]
        self.assertEqual([f["project"] for f in members], [self.p.id], "its member frame first, under its project")
        held = link.asks[ask["id"]]
        self.assertEqual(held["key"], channels.event_key(self.chan(DESK), e))
        self.assertEqual(held["request"], self.asked(sid2), "the session and reach it was put for")
        self.assertEqual(self.held(tid2), [], "nothing for it until the word")

    def test_the_word_answers_the_event_asked_about_once(self):
        tid, sid, _ = self.human()
        first = self.remote(DESK, "add", sid, tid, rid=SAME_ID)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.assertEqual(link.asks[ask["id"]]["key"], channels.event_key(self.chan(DESK), first))
        # A second writer's request under the same id, imported while the first one's question is outstanding.
        second = self.request(DESK, "remove", sid, tid, writer="third/" + OTHER, rid=SAME_ID,
                              verified={"signer": SIGNER})
        self.answer(link, ask, "deliver")
        self.assertEqual(self.held(tid), [DESK], "the first one's add, and not the second one's remove")
        self.assertEqual(self.answers(sid), [(DESK, SAME_ID, "applied", None, (DESK,))])
        self.answer(link, ask, "deliver")   # again: no ask is held under its id now
        self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 1, "the second is a duplicate: never asked about")
        self.assertEqual(len(self.answers(sid)), 1, "used once")
        later = self.remote(DESK, "remove", sid, tid)
        self.answer(link, ask, "deliver")
        self.assertEqual(self.held(tid), [DESK], "an old answer carries no later request")
        self.ask_pass(link)
        asks = self.asks(link)
        self.assertEqual([a["event"]["id"] for a in asks], [SAME_ID, later["id"]])
        self.answer(link, asks[-1], "deliver")
        self.assertEqual(self.held(tid), [])
        self.assertEqual(second["id"], SAME_ID)

    def test_two_requests_for_one_thread_and_channel_are_asked_one_at_a_time_in_order(self):
        tid, sid, _ = self.human()
        add = self.remote(DESK, "add", sid, tid)
        remove = self.remote(DESK, "remove", sid, tid)
        link = self.link()
        self.ask_pass(link)
        self.assertEqual([a["event"]["id"] for a in self.asks(link)], [add["id"]], "the later one waits behind it")
        self.answer(link, self.asks(link)[0], "deliver")
        self.assertEqual(self.held(tid), [DESK])
        self.ask_pass(link)
        self.assertEqual([a["event"]["id"] for a in self.asks(link)], [add["id"], remove["id"]])
        self.answer(link, self.asks(link)[1], "deliver")
        self.assertEqual(self.held(tid), [])
        self.assertEqual([a[:3] for a in self.answers(sid)], [(DESK, add["id"], "applied"),
                                                              (DESK, remove["id"], "applied")])

    def test_a_word_after_a_hand_off_or_a_change_of_reach_is_not_recorded_and_the_request_asked_again(self):
        for word in ("deliver", "refuse"):
            with self.subTest(word, after="hand-off"):
                old, oproc, tid = T1.Sessions.member(self, name="handy-" + word)   # not Store.member
                e = self.remote(DESK, "add", old, tid)
                link = self.link()
                self.ask_pass(link)
                [ask] = self.asks(link)
                self.assertEqual(ask["session"], old)
                job, _ = self.job(old, name="job-" + word)
                self.reconcile()
                self.end(oproc)
                self.reconcile()
                self.assertEqual(threads.get(tid)["current"], job, "handed off")
                self.answer(link, ask, word)
                self.assertEqual((self.held(tid), self.answered(tid)), ([], []), "neither recorded")
                self.ask_pass(link)
                asks = self.asks(link)
                self.assertEqual([a["session"] for a in asks], [old, job], "asked again, for the job's session")
                self.answer(link, asks[-1], word)
                self.assertEqual(self.answered(tid), [(DESK, e["id"])])
                self.assertEqual(self.held(tid), [DESK] if word == "deliver" else [])
            with self.subTest(word, after="a change of reach"):
                tid2, sid2, _ = self.human()
                e2 = self.remote(DESK, "add", sid2, tid2)
                link = self.link()
                self.ask_pass(link)
                [ask] = self.asks(link)
                self.bump(sid2)
                self.answer(link, ask, word)
                self.assertEqual((self.held(tid2), self.answered(tid2)), ([], []), "neither recorded")
                self.ask_pass(link)
                asks = self.asks(link)
                self.assertEqual(len(asks), 2, "asked again")
                self.assertEqual(link.asks[asks[-1]["id"]]["request"], self.asked(sid2), "for the reach it has now")
                self.answer(link, asks[-1], word)
                self.assertEqual(self.answered(tid2), [(DESK, e2["id"])])

    def test_a_stopped_thread_is_asked_about_and_placed_while_it_stays_stopped(self):
        for kind in ("spawned", "human"):
            with self.subTest(kind):
                tid, sid, proc = self.spawned() if kind == "spawned" else self.human()
                self.end(proc)
                self.reconcile()
                self.remote(DESK, "add", sid, tid)
                link = self.link()
                with mock.patch.object(sminos, "hold_now", return_value=True):   # the message asks' filter drops it
                    self.ask_pass(link)
                    [ask] = self.asks(link)
                    self.answer(link, ask, "deliver")
                self.assertEqual(self.held(tid), [DESK])
                self.assertFalse(sminos.running_now(sid), "placed while it stays stopped")

    def test_no_answer_within_reach_wait_is_none_and_the_request_is_asked_again_with_nothing_counted(self):
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        with mock.patch.object(sminos, "words_unanswered", side_effect=AssertionError("an attempt counted")):
            link.expire_asks(time.monotonic() + uplink.REACH_WAIT + 1)
        self.answer(link, ask, "deliver")
        self.assertEqual(self.held(tid), [], "an answer past its wait is none")
        self.ask_pass(link)
        asks = self.asks(link)
        self.assertEqual(len(asks), 2)
        self.assertNotEqual(asks[0]["id"], asks[1]["id"], "under a new id")
        self.answer(link, asks[1], "deliver")
        self.assertEqual(self.held(tid), [DESK])

    def test_an_overdue_answer_that_arrives_while_its_ask_is_still_held_is_none(self):
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        overdue = link.asks[ask["id"]]["deadline"] + 1
        with mock.patch.object(uplink.time, "monotonic", return_value=overdue):
            self.answer(link, ask, "deliver")   # no expire_asks has run: the ask is still held as it lands
        self.assertNotIn(ask["id"], link.asks)
        self.assertEqual((self.held(tid), self.answered(tid)), ([], []), "an answer past its wait is none")
        self.ask_pass(link)
        asks = self.asks(link)
        self.assertEqual(len(asks), 2, "asked again")
        self.answer(link, asks[1], "deliver")
        self.assertEqual(self.held(tid), [DESK])

    def test_the_ask_follows_a_frame_under_the_threads_own_project_when_the_plane_lags_its_move(self):
        tid, sid, proc = self.human()
        link = self.link()
        self.assertTrue(link.members_before(self.p, {sid}))   # its frame on the lane, under the project it was in
        self.assertEqual(link.members_sent[sid]["project"], self.p.id)
        root = self.repo("elsewhere")
        with open(os.path.join(root, ".smns"), "w") as f:
            json.dump({"project": ELSEWHERE, "name": "elsewhere", "hub": {"org": ORG}}, f)
        other = self.project_of(root)
        self.assertNotEqual(other.id, self.p.id)
        self.peer_set(proc, cwd=root)   # the session went on in the other project's directory
        self.reconcile(other)
        self.reconcile()
        self.assertEqual(sminos.last_project(sid).id, other.id, "it moved; the plane has not read that")
        self.assertIn(sid, link.plane.member_rows[self.p.id])
        e = self.remote(DESK, "add", sid, tid)
        self.ask_pass(link)
        [ask] = self.asks(link)
        at = link.session_lane.sent.index(ask)
        frames = [f for f in link.session_lane.sent[:at] if f.get("t") == "member" and f.get("session") == sid]
        self.assertEqual(frames[-1].get("project"), other.id, "its own project's frame, not the one it left")
        self.answer(link, ask, "deliver")
        self.assertEqual(self.held(tid), [DESK])
        self.assertEqual(self.answers(sid, other), [(DESK, e["id"], "applied", None, (DESK,))])

    def test_a_refusal_is_a_refusal_whatever_its_reason_word(self):
        for reason in ("not-reachable", "unverified", "a-word-not-known-here", None, 7):
            with self.subTest(reason):
                tid, sid, _ = self.human()
                e = self.remote(DESK, "add", sid, tid)
                link = self.link()
                self.ask_pass(link)
                [ask] = self.asks(link)
                self.answer(link, ask, "refuse", **({} if reason is None else {"reason": reason}))
                self.assertEqual(self.answers(sid), [(DESK, e["id"], "refused", "not-reachable", ())],
                                 "refused, its reason the one sminos records")
                self.ask_pass(link)
                self.assertEqual(len(self.asks(link)), 1, "answered: never asked again")

    def test_a_frame_still_missing_after_the_refresh_waits_for_the_ordinary_pass(self):
        """Only a frame queued behind lane capacity asks for the next tick at once (words_due, which also makes
        that tick's upload pass a whole look); a row that is not there waits for the timed or nudged pass."""
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        with mock.patch.object(link, "member_on_lane", return_value=False):
            self.ask_pass(link)
        self.assertEqual(self.asks(link), [])
        self.assertFalse(link.words_due, "no row: not asked again at every tick")
        link.members_unsent = {sid}
        with mock.patch.object(link, "member_on_lane", return_value=False), \
                mock.patch.object(link, "publish_members"):
            self.ask_pass(link)
        self.assertTrue(link.words_due, "its frame waits for the lane: asked as soon as it is queued")
        link.members_unsent = set()
        self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 1)

    def test_an_answer_that_names_no_verdict_is_none(self):
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.answer(link, ask, "maybe")
        self.assertEqual((self.held(tid), self.answered(tid)), ([], []))
        self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 1, "held still, asked again at its deadline (C8)")

    def test_the_pass_needs_reach_and_channels_and_reads_nothing_without_an_open_channel(self):
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        for why, link in (("no reach", self.link(reach=False)), ("no channels", self.link(serves=False)),
                          ("no channel open", self.link(open_desk=False))):
            with self.subTest(why):
                with mock.patch.object(channels, "carry_due", side_effect=AssertionError("carried")):
                    self.ask_pass(link)
                self.assertEqual(self.asks(link), [])

    def test_an_import_of_a_channels_log_marks_the_ask_pass_due_and_nudges_the_daemon(self):
        link = self.link()
        link.words_due = False
        before = daemon.nudged_at()
        time.sleep(0.01)
        link.imported[DESK] = link.logs[DESK]
        link.deliver_imports()
        self.assertTrue(link.words_due)
        self.assertNotEqual(daemon.nudged_at(), before)

    def test_the_hub_withheld_it_is_read_at_the_requester(self):
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, "a" * 32)   # for a thread of another machine, as a verb writes it
        c = self.chan(DESK)
        self.assertEqual([r["state"] for r in channels.requests_shown(c)], ["pending"])
        sminos.write_json(os.path.join(c.home, sminos.UPLINK_STATE), {"withheld": {e["writer"]: [e["seq"]]}})
        before = os.stat(os.path.join(c.home, sminos.UPLINK_STATE))
        self.assertEqual(hublog.withheld_of(c), {e["writer"]: {e["seq"]}})
        [shown] = channels.requests_shown(c)
        self.assertEqual((shown["state"], shown["reason"]), ("withheld", "not-reachable"))
        self.assertEqual(channels._request_line(shown)[-1], "refused: not reachable (the hub withheld it)")
        after = os.stat(os.path.join(c.home, sminos.UPLINK_STATE))
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns), "read, unchanged")


    # -- the frontier review, round 1 (the holder's fix wave)

    def uploaded(self, link):
        """Each `events` frame the link sent and the member frames before it: [(frame, [member frames before])]."""
        sent, out = link.log_lane.sent, []
        for i, f in enumerate(sent):
            if f.get("t") == "events":
                out.append((f, [m for m in sent[:i] if m.get("t") == "member"]))
        return out

    def test_a1_a_request_goes_up_after_its_senders_member_frame_under_the_senders_own_project(self):
        """The sender joined its project since the plane last read it: its frame is looked for under its own
        project (a channel's rows are empty by design), and the request waits until that frame is on the lane."""
        tid, sid, _ = self.human()
        _, sender, _ = self.human()
        link = self.link()
        hl = link.logs[DESK]
        hl.on_have({"t": "have", "project": DESK, "have": {}})
        e = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(sender))
        sminos.forget_caches()
        real = link.publish_members

        def lane_full(now):
            link.members_unsent = set(link.members_unsent) | {sender}   # the frame is due and not queued yet
        with mock.patch.object(link, "publish_members", lane_full):
            link.upload(hl)
        self.assertEqual(self.uploaded(link), [], "not uploaded while the sender's frame is not on the lane")
        link.members_unsent = set()
        link.publish_members = real
        link.upload(hl)
        [(frame, members)] = self.uploaded(link)
        self.assertEqual([x["seq"] for x in frame["events"]], [e["seq"]])
        self.assertEqual([m["project"] for m in members if m.get("session") == sender], [self.p.id],
                         "the sender's frame first, under its own project")

    def test_a6_a_channel_with_a_request_written_here_outstanding_does_not_leave(self):
        """No thread of this machine is in it, so the leaving rule reaches it; a request this machine wrote there
        that nothing has answered keeps it (and brings back one that left: Leaving's `stays` is may_leave's
        negation) until the request is answered, the hub withheld it, or its lifetime is out."""
        tid, sid, _ = self.human()
        link = self.link()
        c = self.chan(DESK)
        self.assertTrue(link.may_leave(c), "nothing outstanding: it may leave")
        e = self.request(DESK, "add", sid, "a" * 32)   # for a thread of another machine, as a verb writes it
        sminos.forget_caches()
        self.assertFalse(link.may_leave(c), "a request of this machine's, for a thread of another, outstanding")
        sminos.write_json(os.path.join(c.home, sminos.UPLINK_STATE), {"withheld": {e["writer"]: [e["seq"]]}})
        sminos.forget_caches()
        self.assertTrue(link.may_leave(c), "the hub withheld it: nothing comes of it")
        os.unlink(os.path.join(c.home, sminos.UPLINK_STATE))
        sminos.forget_caches()
        self.assertFalse(link.may_leave(c))
        with mock.patch.object(channels, "request_ttl", return_value=0.0):
            self.assertTrue(link.may_leave(c), "expired: nothing outstanding")
        f = self.request(LOBBY, "remove", sid, tid)   # this machine's own thread, not in it
        sminos.forget_caches()
        self.assertFalse(link.may_leave(self.chan(LOBBY)), "not answered yet")
        self.assertEqual(self.carry(LOBBY, also=[f])[f["id"]], channels.Outcome("applied", "unchanged"))
        sminos.forget_caches()
        self.assertTrue(link.may_leave(self.chan(LOBBY)), "answered")

    def test_a_channel_with_a_message_written_here_not_taken_does_not_leave(self):
        """CH2's M6: a machine that only wrote into a channel keeps its log open until what it wrote has gone up
        (sminos_channels.unsent: past the upstream's `taken`, or queued), and a channel that left comes back for it
        (Leaving's `stays` is may_leave's negation); a request alone keeps its own rule (outstanding)."""
        tid, sid, _ = self.human()
        link = self.link()
        c = self.chan(DESK)
        self.assertTrue(link.may_leave(c), "nothing written: it may leave")
        w = "%s/%s" % (sminos.host_name(), sid)
        e = sminos.log_append(c, w, "say", to="*", text="a note", thread=tid)
        sminos.forget_caches()
        self.assertTrue(channels.unsent(c))
        self.assertFalse(link.may_leave(c), "a message written here, not taken by the upstream")
        hublog.HubLog(c, link.cred).write_taken({"taken": {w: e["seq"]}})
        sminos.forget_caches()
        self.assertFalse(channels.unsent(c))
        self.assertTrue(link.may_leave(c), "gone up: it may leave")
        os.makedirs(os.path.join(c.home, sminos.QUEUED), exist_ok=True)
        with open(sminos.queued_path(c, "%s/human" % sminos.host_name()), "w") as f:
            f.write(json.dumps({"ts": sminos.now(ms=True), "writer": "%s/human" % sminos.host_name(), "kind": "human",
                                "to": "*", "text": "waits for its head"}) + "\n")
        sminos.forget_caches()
        self.assertFalse(link.may_leave(c), "a person's message still queued here")

    def test_a7_an_answer_waits_on_no_lock_and_the_pass_that_carries_requests_uses_it(self):
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        with open(os.path.join(threads.store_dir(), ".lock"), "a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            at = time.monotonic()
            self.answer(link, ask, "deliver", carried=False)
            took = time.monotonic() - at
            fcntl.flock(held, fcntl.LOCK_UN)
        self.assertLess(took, 0.5, "the receive loop waited on the store's lock")
        self.assertEqual(self.held(tid), [], "nothing carried on the receive loop")
        self.assertTrue(link.words_due, "the next pass is due, to use the word")
        self.ask_pass(link)
        self.assertEqual(self.held(tid), [DESK], "the pass carried it out on the word")
        self.assertEqual(len(self.asks(link)), 1, "not asked again")

    def test_a11_a_word_that_could_not_be_committed_waits_for_the_ordinary_interval(self):
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        with open(sminos.wake_lock_path(tid), "a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)   # a wake of the thread in flight in another process
            self.answer(link, ask, "deliver", carried=False)
            self.ask_pass(link)
            self.assertEqual(self.held(tid), [])
            self.assertEqual(len(self.asks(link)), 1, "not asked again at the endpoint's speed")
            self.assertFalse(link.words_due, "nothing makes the next pass due at once")
            fcntl.flock(held, fcntl.LOCK_UN)
        self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 1, "a pass before the ordinary interval asks nothing")
        self.ordinary_pass(link)
        self.assertEqual(len(self.asks(link)), 2, "asked again at the ordinary interval")
        self.answer(link, self.asks(link)[-1], "deliver")
        self.assertEqual(self.held(tid), [DESK])

    def ordinary_pass(self, link):
        """An ask pass one ordinary words interval later."""
        later = time.monotonic() + uplink.WORDS_EVERY + 1
        with mock.patch.object(uplink.time, "monotonic", return_value=later):
            self.ask_pass(link)

    # -- the fix wave's review, round 1

    def test_a1_a_sender_whose_frame_cannot_be_made_yet_holds_the_upload_and_one_in_no_project_does_not(self):
        tid, sid, _ = self.human()
        _, sender, _ = self.human()
        link = self.link()
        hl = link.logs[DESK]
        hl.on_have({"t": "have", "project": DESK, "have": {}})
        e = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(sender))
        path = records.record_path(sender)
        with open(path) as f:
            kept = f.read()
        with open(path, "w") as f:
            f.write("not a record")   # its record cannot make a frame now: not available yet
        sminos.forget_caches()
        link.upload(hl)
        self.assertEqual(self.uploaded(link), [], "the request waits for its sender's frame")
        with open(path, "w") as f:
            f.write(kept)
        sminos.forget_caches()
        link.upload(hl)
        [(frame, members)] = self.uploaded(link)
        self.assertEqual([x["seq"] for x in frame["events"]], [e["seq"]])
        self.assertEqual([m["project"] for m in members if m.get("session") == sender and not m.get("gone")][-1:],
                         [self.p.id], "after its frame, under its own project")
        # A sender in no project now has no frame owed: its request goes.
        _, gone, _ = self.human()
        later = self.request(DESK, "remove", sid, tid, writer=sminos.writer_id(gone))
        self.write_own(gone, [{"kind": "retired", "reason": "moved", "project": "", "thread": threads.stamp(gone)}])
        sminos.forget_caches()
        self.assertIsNone(sminos.last_project(gone))
        link.upload(hl)
        self.assertEqual([x["seq"] for f, _ in self.uploaded(link) for x in f["events"]
                          if x["writer"] == later["writer"]], [later["seq"]])

    def test_a6_a_request_written_here_stays_outstanding_across_a_rename(self):
        tid, sid, _ = self.human()
        link = self.link()
        before = sminos.machine_name_now()
        e = self.request(DESK, "add", sid, "a" * 32)   # receipted under the name then
        c, lobby = self.chan(DESK), self.chan(LOBBY)
        sminos._queue(lobby, "oldname/human", [{"kind": "channel-request", "op": "add", "session": sid,
                                                "thread": "b" * 32, "id": "0f" * 16}])
        self.identity("newname", {before: [], "oldname": []})
        sminos.forget_caches()
        self.assertNotEqual(sminos.machine_name_now(), sminos.writer_base(e["writer"]).rpartition("/")[0])
        self.assertFalse(link.may_leave(c), "its receipt says this machine wrote it")
        self.assertFalse(link.may_leave(lobby), "a former name's queue needs the log open to be released")

    def test_a6_the_leaving_rule_reads_no_other_log_and_hears_a_remote_targets_answer(self):
        tid, sid, _ = self.human()
        link = self.link()
        c, lobby = self.chan(DESK), self.chan(LOBBY)
        e = self.request(DESK, "add", sid, "a" * 32)    # a thread of another machine
        local = self.request(LOBBY, "remove", sid, tid)  # this machine's own thread, not in it
        sminos.forget_caches()
        every = mock.patch.object(channels, "_answer_index", side_effect=AssertionError("every project's log read"))
        roster = mock.patch.object(channels, "_sweep", side_effect=AssertionError("the roster read"))
        with every, roster:
            self.assertFalse(link.may_leave(c))
            self.assertFalse(link.may_leave(lobby))
        self.assertEqual(self.carry(LOBBY, also=[local])[local["id"]], channels.Outcome("applied", "unchanged"))
        sminos.forget_caches()
        with every, roster:
            self.assertTrue(link.may_leave(lobby), "answered, by its record")
        # The remote target's answer, imported in its own project's log, is heard as it arrives.
        pid = "9a9a9a9a-0000-4000-8000-00000000009a"
        sminos.register_if_absent(sminos.make_project(pid, "theirs", "", "", {"url": URL, "org": ORG}))
        sminos.forget_caches()
        link.logs[pid] = hublog.HubLog(sminos.known_project(pid), link.cred)
        link.opened.add(pid)
        them = "6e000001-0000-4000-8000-0000000000e1"
        joined = self.joined_there(them, 1, "a" * 32)
        statement = {"ts": sminos.now(ms=True), "writer": "other/" + them, "seq": 2, "kind": "channels",
                     "session": them, "thread": "a" * 32, "op": "add", "channels": [DESK],
                     "answers": {"channel": DESK, "id": e["id"]}, "result": "applied"}
        self.imported(link, pid, joined, statement)
        self.assertTrue(os.path.exists(sminos.writer_path(sminos.known_project(pid), "other/" + them)), "imported")
        sminos.forget_caches()
        with every, roster:
            self.assertTrue(link.may_leave(c), "its answer heard")

    def test_a7_the_pass_waits_on_no_lock_so_the_next_frame_is_dispatched(self):
        ta, sa, _ = self.human()
        tb, sb, _ = self.human()
        self.remote(DESK, "add", sa, ta)
        self.remote(LOBBY, "add", sb, tb)
        link = self.link()
        link.logs[LOBBY] = hublog.HubLog(self.chan(LOBBY), link.cred)
        link.opened.add(LOBBY)
        link.channels.add(LOBBY)
        self.ask_pass(link)
        asks = {a["session"]: a for a in self.asks(link)}
        self.assertEqual(set(asks), {sa, sb})
        path = os.path.join(threads.store_dir(), ".finish", ta + ".lock")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a+") as held, mock.patch.object(sminos, "warn"):
            fcntl.flock(held, fcntl.LOCK_EX)   # A's finisher, in another process
            at = time.monotonic()
            self.answer(link, asks[sa], "deliver")   # and the tick's pass, on the consumer's thread
            took = time.monotonic() - at
            self.answer(link, asks[sb], "deliver")   # the next frame, dispatched
            fcntl.flock(held, fcntl.LOCK_UN)
        self.assertLess(took, 1.0, "the pass waited on A's finisher lock")
        self.assertEqual(self.held(ta), [DESK], "recorded; its statement left to the replay")
        self.assertEqual(self.held(tb), [LOBBY])

    def test_a11_another_requests_reply_does_not_retry_one_that_could_not_commit_early(self):
        ta, sa, _ = self.human()
        tb, sb, _ = self.human()
        self.remote(DESK, "add", sa, ta)
        self.remote(DESK, "add", sb, tb)
        link = self.link()
        self.ask_pass(link)
        asks = {a["session"]: a for a in self.asks(link)}
        self.assertEqual(set(asks), {sa, sb})
        with open(sminos.wake_lock_path(ta), "a+") as la, open(sminos.wake_lock_path(tb), "a+") as lb:
            fcntl.flock(la, fcntl.LOCK_EX)
            fcntl.flock(lb, fcntl.LOCK_EX)
            self.answer(link, asks[sa], "deliver", carried=False)
            self.ask_pass(link)
            self.assertEqual(len(self.asks(link)), 2)
            self.answer(link, asks[sb], "deliver", carried=False)
            self.ask_pass(link)   # due for B's reply
            self.assertEqual(len(self.asks(link)), 2, "B's reply does not retry A before its interval")
            fcntl.flock(la, fcntl.LOCK_UN)
            fcntl.flock(lb, fcntl.LOCK_UN)
        self.ordinary_pass(link)
        again = self.asks(link)[2:]
        self.assertEqual(sorted(a["session"] for a in again), sorted([sa, sb]), "each at its own interval")
        for a in again:
            self.answer(link, a, "deliver")
        self.assertEqual((self.held(ta), self.held(tb)), ([DESK], [DESK]))

    def test_a10_a_request_the_endpoint_refused_audience_is_shown_withheld_for_its_audience(self):
        tid, sid, _ = self.human()
        e = self.request(DESK, "add", sid, "a" * 32)   # for a thread of another machine, as a verb writes it
        c = self.chan(DESK)
        for state in ({"dead": {e["writer"]: {"at": [e["seq"]], "last": e["seq"]}}},
                      {"voided": {e["writer"]: [e["seq"]]}}):
            with self.subTest(state=sorted(state)):
                sminos.write_json(os.path.join(c.home, sminos.UPLINK_STATE), state)
                [shown] = channels.requests_shown(c)
                self.assertEqual((shown["state"], shown["reason"]), ("withheld", "audience"))
                self.assertEqual(channels._request_line(shown)[-1], "refused: " + channels.WORDS["audience"])
                self.assertTrue(self.link().may_leave(c), "nothing comes of it: nothing outstanding")

    # -- the fix wave's review, round 2

    def test_a1_a_sender_retired_since_its_request_owes_no_frame_and_its_batch_goes_whole(self):
        """`retire` between the request and its upload: last_project still names the project the sender retired
        from, but its own events there leave it no member, so no frame is owed and nothing waits for one; a frame
        that carries its request beside another sender's event goes, the other's frame first."""
        tid, sid, _ = self.human()
        _, sender, _ = self.human()
        _, other, _ = self.human()
        link = self.link()
        hl = link.logs[DESK]
        hl.on_have({"t": "have", "project": DESK, "have": {}})
        e = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(sender))
        f = self.request(DESK, "remove", sid, tid, writer=sminos.writer_id(other))
        code, out = self.cli("retire", sender)
        self.assertEqual(code, 0, out)
        sminos.forget_caches()
        self.assertEqual(getattr(sminos.last_project(sender), "id", None), self.p.id, "it names the project still")
        link.upload(hl)
        [(frame, members)] = self.uploaded(link)
        self.assertEqual(sorted((x["writer"], x["seq"]) for x in frame["events"]),
                         sorted([(e["writer"], e["seq"]), (f["writer"], f["seq"])]), "one batch, both writers")
        self.assertEqual([m["project"] for m in members if m.get("session") == other], [self.p.id])

    def hub_project(self, pid, name):
        sminos.register_if_absent(sminos.make_project(pid, name, "", "", {"url": URL, "org": ORG}))
        sminos.forget_caches()
        return sminos.known_project(pid)

    def joined_there(self, session, seq, thread):
        """Another machine's session's `joined`, stamped with `thread`, as it arrives."""
        return {"ts": sminos.now(ms=True), "writer": "other/" + session, "seq": seq, "kind": "joined",
                "session": session, "thread": thread, "alias": "faraway", "name_source": "user", "machine": "other",
                "cwd": "/d", "worktree": "", "role": "", "seat": "", "by": ""}

    def imported(self, link, pid, *events):
        """`events` of another machine's, arriving in `pid`'s log."""
        machine = {"kind": "machine", "ref": "ref-other", "name": "other", "keyId": "k-other"}
        link.on_events({"t": "events", "project": pid,
                        "events": [endpoint_standin.Endpoint.arriving(e, machine) for e in events]}, None)
        sminos.forget_caches()

    def test_a6_an_answer_is_heard_only_once_stored_and_only_from_a_session_its_thread_had(self):
        """What the leaving rule hears of an import is its stored events alone (a statement held back on a seq gap
        is no answer yet), each by answer_of's rule of its writer: a statement whose writer's own `joined` in that
        log is stamped with its thread; the stamp alone is a field any writer can set."""
        tid, sid, _ = self.human()
        link = self.link()
        c = self.chan(DESK)
        e = self.request(DESK, "add", sid, "a" * 32)   # a thread of another machine
        pid = "9a9a9a9a-0000-4000-8000-00000000009b"
        p = self.hub_project(pid, "theirs")
        link.logs[pid] = hublog.HubLog(p, link.cred)
        link.opened.add(pid)
        them, stranger = "6e000001-0000-4000-8000-0000000000e2", "6e000001-0000-4000-8000-0000000000e3"
        joined = self.joined_there

        def statement(session, seq):
            return {"ts": sminos.now(ms=True), "writer": "other/" + session, "seq": seq, "kind": "channels",
                    "session": session, "thread": "a" * 32, "op": "s%d" % seq, "channels": [DESK],
                    "answers": {"channel": DESK, "id": e["id"]}, "result": "applied"}
        stored = os.path.join(p.home, "log", "other.%s.jsonl" % them)
        self.imported(link, pid, joined(them, 1, "a" * 32), statement(them, 3))   # seq 2 not here: held back
        with open(stored) as fh:
            self.assertEqual([json.loads(x)["seq"] for x in fh if x.strip()], [1], "the statement was held back")
        self.assertFalse(link.may_leave(c), "a held-back statement is not heard")
        self.imported(link, pid, joined(stranger, 1, "b" * 32), statement(stranger, 2))
        self.assertFalse(link.may_leave(c), "its writer's session never joined as the thread")
        self.imported(link, pid, statement(them, 2))
        self.assertTrue(link.may_leave(c), "stored, from a session the thread had: heard")

    def test_a7_the_pass_waits_on_no_writer_lock_and_the_statement_is_left_to_the_replay(self):
        """The finisher's append takes the writer file's locks bounded too: a statement whose writer another
        process holds is left in the record's open entry, and the next frame is dispatched."""
        ta, sa, _ = self.human()
        tb, sb, _ = self.human()
        self.remote(DESK, "add", sa, ta)
        self.remote(LOBBY, "add", sb, tb)
        link = self.link()
        link.logs[LOBBY] = hublog.HubLog(self.chan(LOBBY), link.cred)
        link.opened.add(LOBBY)
        link.channels.add(LOBBY)
        self.ask_pass(link)
        asks = {a["session"]: a for a in self.asks(link)}
        self.assertEqual(set(asks), {sa, sb})
        path = sminos.writer_path(self.p, sminos.own_stream(self.p, sa)[0]) + ".lock"
        with open(path, "a+") as held, mock.patch.object(sminos, "warn"):
            fcntl.flock(held, fcntl.LOCK_EX)   # A's writer file, appended to by another process
            at = time.monotonic()
            self.answer(link, asks[sa], "deliver")
            took = time.monotonic() - at
            self.answer(link, asks[sb], "deliver")   # the next frame, dispatched
            fcntl.flock(held, fcntl.LOCK_UN)
        self.assertLess(took, 1.0, "the pass waited on A's writer lock")
        self.assertEqual(self.held(ta), [DESK], "recorded")
        self.assertTrue(threads.get(ta).get("pending"), "its statement owed by the open entry")
        self.assertEqual(self.statements(sa), [], "not appended while its writer was held")
        self.assertEqual(self.held(tb), [LOBBY])
        sminos.forget_caches()
        self.assertTrue(sminos.finish_thread(ta), "the replay appends it")
        self.assertEqual([s["channels"] for s in self.statements(sa)], [[DESK]])

    def test_a11_a_word_whose_request_could_not_be_read_waits_for_the_ordinary_interval(self):
        """A pass that cannot read the channel's input evaluates no request and returns no outcome: each word it
        took is still one that could not commit, so another request's reply does not retry it early."""
        ta, sa, _ = self.human()
        tb, sb, _ = self.human()
        self.remote(DESK, "add", sa, ta)
        self.remote(DESK, "add", sb, tb)
        link = self.link()
        self.ask_pass(link)
        asks = {a["session"]: a for a in self.asks(link)}
        self.assertEqual(set(asks), {sa, sb})
        where = os.path.join(self.chan(DESK).home, "log")
        real = os.listdir

        def listing(p=".", *a, **k):
            if os.path.abspath(os.fspath(p)) == os.path.abspath(where):
                raise PermissionError(13, "Permission denied", p)
            return real(p, *a, **k)
        with mock.patch("os.listdir", listing), mock.patch.object(channels.sminos, "daemon_log"):
            sminos._MERGED.clear()
            self.answer(link, asks[sa], "deliver")   # its pass reads nothing of the channel
        self.assertEqual(self.held(ta), [])
        self.answer(link, asks[sb], "deliver")   # B's reply makes a pass due
        self.assertEqual(self.held(tb), [DESK])
        self.assertEqual([a["session"] for a in self.asks(link)[2:]], [], "A is not asked again before its interval")
        self.ordinary_pass(link)
        self.assertEqual([a["session"] for a in self.asks(link)[2:]], [sa], "asked again at the ordinary interval")
        self.answer(link, self.asks(link)[-1], "deliver")
        self.assertEqual(self.held(ta), [DESK])

    # -- the fix wave's review, round 3

    def test_a1_a_sender_that_moved_since_its_project_was_cached_waits_for_its_frame_under_the_destination(self):
        """last_project's answer is kept per cache generation: one taken before a move names the source, where the
        sender's own events now say `retired moved`. That is no retirement into nothing: the sender's project is
        read again, fresh, and its frame there goes first."""
        tid, sid, _ = self.human()
        _, sender, _ = self.human()
        other = self.hub_project("9a9a9a9a-0000-4000-8000-00000000009c", "elsewhere")
        link = self.link()
        hl = link.logs[DESK]
        hl.on_have({"t": "have", "project": DESK, "have": {}})
        e = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(sender))
        stamp = threads.stamp(sender)
        self.write_own(sender, [{"kind": "retired", "reason": "moved", "project": other.id, "thread": stamp}])
        self.write_own(sender, [self.old_joined(sender, alias="mover", thread=stamp)], p=other)
        sminos.forget_caches()
        sminos._LAST[sender] = self.p   # the generation's answer, taken before the move
        sent = []
        real = link.member_under

        def under(project, session):
            sent.append((project.id, session))
            return real(project, session)
        with mock.patch.object(link, "member_under", under):
            link.upload(hl)
        self.assertIn((other.id, sender), sent, "its frame looked for under the destination")
        for frame, members in self.uploaded(link):
            if any(x["writer"] == e["writer"] for x in frame["events"]):
                self.assertIn(other.id, [m["project"] for m in members if m.get("session") == sender],
                              "uploaded only after its frame under the destination")

    def test_a7_the_pass_finishes_no_open_entry_so_a_held_cursor_lock_holds_no_frame(self):
        """A thread whose record holds an open entry of another operation (a hand-off cut after its record's
        write) is pending `entry` to the uplink's pass, which finishes nothing of it there: the carry's cursor
        lock, held by another process, never stops the consumer; the reconciliation off that thread finishes it."""
        tb, sb, _ = self.human()
        link = self.link()
        link.logs[LOBBY] = hublog.HubLog(self.chan(LOBBY), link.cred)
        link.opened.add(LOBBY)
        link.channels.add(LOBBY)
        # B's member frame on the lane already: its ask reads no row again, so the plane's refresh (which
        # reconciles the project, and replays its open entries, as every tick's does) is not what is tested here.
        self.assertTrue(link.member_under(self.p, sb))
        old, oproc, tid = T1.Sessions.member(self)   # (Store's member() reads a row)
        job, _ = self.job(old)
        self.end(oproc)
        with self.kill_after_begin(), self.assertRaises(T1.Killed):
            self.reconcile()
        self.assertEqual(threads.get(tid)["pending"]["op"], "advance")
        a = self.remote(DESK, "add", job, tid)
        self.remote(LOBBY, "add", sb, tb)
        path = sminos.project_path(self.p, "cursors", sminos.reader_key(job) + ".json")[:-len(".json")] + ".lock"
        with open(path, "a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)   # the successor's cursor, written by another process
            at = time.monotonic()
            sminos.forget_caches()
            link.ask_words({})   # the ask alone: the plane's own read (Link.members) is the older hang's, not this
            took = time.monotonic() - at
            fcntl.flock(held, fcntl.LOCK_UN)
        self.assertLess(took, 1.0, "the pass waited on the hand-off's cursor lock")
        self.assertEqual(threads.get(tid)["pending"]["op"], "advance", "left to the reconciliation")
        self.assertEqual([x["session"] for x in self.asks(link)], [sb], "the next request asked about")
        self.assertEqual(self.carry(DESK, wake_until=time.time())[a["id"]].why, "endpoint",
                         "the daemon's pass finishes the entry first, as before")
        self.assertIsNone(threads.get(tid).get("pending"))

    # -- the frontier review, round 2 (the holder's second fix wave)

    def held_for(self, path, seconds):
        """`path`'s lock taken as another process takes it (its own open file, on a thread here), let go after
        `seconds`."""
        taken = threading.Event()

        def hold():
            with open(path, "a+") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                taken.set()
                time.sleep(seconds)
                fcntl.flock(f, fcntl.LOCK_UN)
        t = threading.Thread(target=hold, daemon=True)
        t.start()
        self.assertTrue(taken.wait(5))
        self.addCleanup(t.join)
        return t

    def cut_hand_off(self, old=None, oproc=None, tid=None):
        """A thread whose record holds a hand-off's open entry (an advance cut after its record's write): (its
        thread id, the path of the cursor lock its carry takes)."""
        if old is None:
            old, oproc, tid = T1.Sessions.member(self)   # (Store's member() reads a row)
        job, _ = self.job(old)
        self.end(oproc)
        with self.kill_after_begin(), self.assertRaises(T1.Killed):
            self.reconcile()
        self.assertEqual(threads.get(tid)["pending"]["op"], "advance")
        return tid, sminos.project_path(self.p, "cursors", sminos.reader_key(job) + ".json")[:-len(".json")] + ".lock"

    def test_c1_the_ask_pass_reads_frames_as_they_are_and_reconciles_nothing(self):
        """A target whose member frame is not on the lane is pending until the plane's own read publishes it: the
        ask pass reads no view, which would reconcile the project and replay its open entries (a hand-off's carry
        waits on the successor's cursor lock with no deadline), so a lock another process holds stops no frame."""
        tb, sb, _ = self.human()
        tid, path = self.cut_hand_off()
        self.remote(DESK, "add", sb, tb)
        link = self.link()
        t = self.held_for(path, 2.0)
        sminos.forget_caches()
        at = time.monotonic()
        link.ask_words({})
        took = time.monotonic() - at
        self.assertLess(took, 1.0, "the ask pass waited on the hand-off's cursor lock")
        self.assertEqual(self.asks(link), [], "its frame not on the lane: nothing asked")
        self.assertFalse(link.words_due, "nor asked at every tick: the plane's read publishes the frame")
        self.assertEqual(threads.get(tid)["pending"]["op"], "advance", "nothing of the project replayed")
        t.join()
        self.ask_pass(link)   # the tick's members first (Link.members, a reconciling read), then the ask
        [ask] = self.asks(link)
        self.assertEqual(ask["session"], sb)
        at = link.session_lane.sent.index(ask)
        self.assertIn(self.p.id, [f["project"] for f in link.session_lane.sent[:at]
                                  if f.get("t") == "member" and f.get("session") == sb], "its frame first")

    def test_c1_a_stale_frame_is_sent_again_from_the_row_as_it_is_and_one_under_another_project_waits(self):
        """What the ask needs of the frame is read without a view: the row the plane last read, its record read now,
        sent again when it changed; a frame that names another project (the session moved since the plane read it)
        waits for the plane's next read, nothing asked meanwhile."""
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        link.members(time.monotonic())
        sent = dict(link.members_sent[sid])
        self.record(sid, owners=["@machine", "member-9"])   # its owners changed: the frame on the lane is stale
        sminos.forget_caches()
        with mock.patch.object(link.plane, "refresh", side_effect=AssertionError("a view was read")):
            link.ask_words({})
        [ask] = self.asks(link)
        self.assertNotEqual(link.members_sent[sid], sent, "sent again from the row, its record read now")
        at = link.session_lane.sent.index(ask)
        self.assertEqual([f for f in link.session_lane.sent[:at] if f.get("t") == "member"
                          and f.get("session") == sid][-1], link.members_sent[sid], "the current frame first")
        tid2, sid2, _ = self.human()
        self.remote(DESK, "add", sid2, tid2)
        link.members(time.monotonic() + 2 * uplink.plane.MEMBERS_WHOLE)
        link.members_sent[sid2] = {**link.members_sent[sid2], "project": ELSEWHERE}   # read before it moved
        sminos.forget_caches()
        with mock.patch.object(link.plane, "refresh", side_effect=AssertionError("a view was read")), \
                mock.patch.object(link, "publish_members"):
            link.ask_words({})
        self.assertEqual([a["session"] for a in self.asks(link)], [sid], "the moved one waits")

    def test_c1_the_requests_finish_finishes_only_the_entry_it_committed(self):
        """Between the request's commit and its finish another process finishes the statement and commits a hand-off
        of the thread: the request's finish call leaves that entry to the reconciliation, and never waits on its
        carry's cursor lock."""
        old, oproc, tid = T1.Sessions.member(self, owned=False)
        self.assertTrue(channels.machine_owns(old), "the machine's owners: row 10 needs no word")
        e = self.request(DESK, "add", old, tid)   # this machine's own, for a thread of its own
        real, overtaken = threads.set_channels, []

        def committed_then_overtaken(thread_id, decide, **kw):
            entry = real(thread_id, decide, **kw)
            if entry is not None and not overtaken:
                sminos.finish_thread(thread_id)   # the statement, by another finisher
                self.held_for(self.cut_hand_off(old, oproc, tid)[1], 2.0)
                overtaken.append(time.monotonic())
            return entry
        with mock.patch.object(threads, "set_channels", committed_then_overtaken):
            sminos.forget_caches()
            now = time.time()
            got = {r["id"]: o for r, o in channels.carry_due(self.chan(DESK), lock_until=now, wake_until=now,
                                                              finishes=False)}
            waited = time.monotonic() - overtaken[0] if overtaken else None
        self.assertEqual(got[e["id"]], channels.Outcome("applied"))
        self.assertLess(waited, 1.0, "the request's finish waited on the hand-off's cursor lock")
        self.assertEqual(threads.get(tid)["pending"]["op"], "advance", "the hand-off's left to the reconciliation")

    def test_c8_a_malformed_reach_reply_keeps_the_ask_held_until_its_deadline(self):
        """A reply that names no verdict is no answer, and consumes nothing: the ask stays held, nothing marks the next
        pass due, and it is asked again once its deadline passes (the ordinary timer), never at the reply's speed."""
        tid, sid, _ = self.human()
        self.remote(DESK, "add", sid, tid)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        link.words_due = False
        self.answer(link, ask, "maybe", carried=False)
        self.assertIn(ask["id"], link.asks, "still held")
        self.assertFalse(link.words_due, "no pass made due")
        self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 1, "not asked again before its deadline")
        later = link.asks[ask["id"]]["deadline"] + 1
        link.expire_asks(later)
        with mock.patch.object(uplink.time, "monotonic", return_value=later):
            self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 2, "asked again once its deadline passed")
        self.answer(link, self.asks(link)[-1], "deliver")
        self.assertEqual(self.held(tid), [DESK])

    def test_c9_a_sender_that_joined_its_destination_before_retiring_from_its_source_owes_its_frame_there(self):
        """A move whose destination's `joined` comes before the source's `retired moved` naming it is a membership
        of the destination (a dual membership of one tick, then the move): the request goes after the sender's
        frame there, never without it."""
        tid, sid, _ = self.human()
        _, sender, _ = self.human()
        other = self.hub_project("9a9a9a9a-0000-4000-8000-00000000009d", "further")
        link = self.link()
        hl = link.logs[DESK]
        hl.on_have({"t": "have", "project": DESK, "have": {}})
        e = self.request(DESK, "add", sid, tid, writer=sminos.writer_id(sender))
        stamp = threads.stamp(sender)
        sminos.write_override(sender, other.id)   # its `join further`: the session's project is the destination now
        self.write_own(sender, [self.old_joined(sender, alias="mover", thread=stamp)], p=other)
        time.sleep(0.005)
        self.write_own(sender, [{"kind": "retired", "reason": "moved", "project": other.id, "thread": stamp}])
        sminos.forget_caches()
        self.assertEqual(getattr(sminos.member_project_now(sender), "id", None), other.id)
        sent = []
        real = link.member_under

        def under(project, session):
            sent.append((project.id, session))
            return real(project, session)
        with mock.patch.object(link, "member_under", under):
            link.upload(hl)
        self.assertIn((other.id, sender), sent, "its frame looked for under the destination")
        uploads = [(f, ms) for f, ms in self.uploaded(link) if any(x["writer"] == e["writer"] for x in f["events"])]
        self.assertTrue(uploads)
        for frame, members in uploads:
            self.assertIn(other.id, [m["project"] for m in members if m.get("session") == sender],
                          "uploaded only after its frame under the destination")


class WireAsks(unittest.TestCase):
    """A real uplink against a stand-in that serves `reach` and `channels`:
    a request another machine's session wrote for a thread here, imported
    as the endpoint relays it, is asked about and carried out on the
    endpoint's word, with no turn of any session: a verified sender it
    delivers for is applied, one it refuses refused; an unverified sender
    it would deliver words for is refused by sminos, never asked; with no
    answer it stays pending and is asked again; a request that arrives
    expired is never asked about; an endpoint without `channels`, or
    without `reach`, is asked nothing and leaves it pending. The checker
    passes over the frames and the store."""

    setUp = Wire.setUp
    stop_all = Wire.stop_all
    live = Wire.live
    uplink = Wire.uplink
    hellos = Wire.hellos

    def endpoint(self, capabilities=("channels", "reach"), verdicts=None):
        verdicts = verdicts if verdicts is not None else {}
        ep = endpoint_standin.Endpoint(os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint"),
                                       org=self.org, capabilities=list(capabilities),
                                       reach_verdict=lambda f: verdicts.get(f["event"].get("thread")))
        ep.start()
        self.addCleanup(ep.stop)
        return ep

    def thread(self, sid, name):
        self.live(sid, name)
        sminos.view_of(self.app)
        return threads.thread_of(sid)["thread"]

    def request(self, seq, sid, tid, signer=None, ts=None, op="add"):
        e = {"ts": ts or sminos.now(ms=True), "writer": "other/" + OTHER, "seq": seq, "kind": "channel-request",
             "op": op, "session": sid, "thread": tid, "id": os.urandom(16).hex()}
        return e, endpoint_standin.Endpoint.arriving(e, signer or {"kind": "machine", "ref": "ref-other",
                                                                   "name": "other", "keyId": "k-other"})

    def statements(self, ep, tid):
        return [e for e in ep.logs.get(APP, {}).get("%s/%s" % (MACHINE, self.sid_of(tid)), {}).values()
                if e.get("kind") == "channels"]

    def sid_of(self, tid):
        return threads.get(tid)["current"]

    def asked(self, ep, tid):
        return [f for f in ep.frames("reach?") if f["event"].get("thread") == tid]

    def test_the_endpoints_word_on_the_path(self):
        sids = ["6c00000%d-0000-4000-8000-0000000000c%d" % (n, n) for n in range(3, 8)]
        tids = [self.thread(sid, "t%d" % n) for n, sid in enumerate(sids)]
        deliver, refuse, unverified, silent, late = tids
        verdicts = {deliver: "deliver", refuse: ("refuse", "unverified"), unverified: "deliver"}
        ids = [DESK, LOBBY]
        before = wire.baseline(os.environ["SMINOS_HOME"], ids)
        ep = self.endpoint(verdicts=verdicts)
        with mock.patch.object(uplink, "REACH_WAIT", 1.0):
            self.uplink()
            ep.wait_until(lambda: self.hellos(ep, 1).get(DESK) is True)
            ep.wait_until(lambda: ep.restatement_applied(1))
            reqs = {}
            for n, tid in enumerate(tids, 1):
                old = tid == late
                e, wrapped = self.request(n, self.sid_of(tid), tid,
                                          signer={"kind": "legacy"} if tid == unverified else None,
                                          ts="2026-11-01T00:00:00.000Z" if old else None)
                reqs[tid] = e
                ep.events(DESK, [wrapped])
            ep.wait_until(lambda: len(self.statements(ep, deliver)) == 1 and len(self.statements(ep, refuse)) == 1
                          and len(self.statements(ep, unverified)) == 1)
            ep.wait_until(lambda: len(self.asked(ep, silent)) >= 2, timeout=15)
        [s] = self.statements(ep, deliver)
        self.assertEqual((s["channels"], s["answers"], s["result"]), ([DESK], {"channel": DESK, "id": reqs[deliver]["id"]},
                                                                    "applied"))
        [s] = self.statements(ep, refuse)
        self.assertEqual((s["channels"], s["result"], s["reason"]), ([], "refused", "not-reachable"))
        [s] = self.statements(ep, unverified)
        self.assertEqual((s["channels"], s["result"], s["reason"]), ([], "refused", "not-reachable"),
                         "refused by sminos though the endpoint would deliver its words")
        self.assertEqual(self.asked(ep, unverified), [], "never asked about")
        [a] = self.asked(ep, deliver)
        self.assertEqual((a["project"], a["session"], a["event"]), (DESK, self.sid_of(deliver), reqs[deliver]))
        member = next(n for n, (_, f) in enumerate(ep.received) if f.get("t") == "member"
                      and f.get("session") == a["session"])
        ask_at = next(n for n, (_, f) in enumerate(ep.received) if f.get("t") == "reach?" and f["id"] == a["id"])
        self.assertLess(member, ask_at, "its member frame first")
        silent_asks = self.asked(ep, silent)
        self.assertNotEqual(silent_asks[0]["id"], silent_asks[1]["id"], "no answer: asked again, under a new id")
        self.assertEqual(self.statements(ep, silent), [], "pending: nothing written")
        self.assertEqual(threads.get(silent).get("channels"), [])
        self.assertEqual(self.asked(ep, late), [], "an expired request is never asked about")
        self.assertEqual((threads.get(late).get("channels"), self.statements(ep, late)), ([], []))
        self.assertEqual(threads.get(deliver)["channels"], [DESK])
        ep.wait_until(lambda: self.hellos(ep, 1).get(DESK) is False)   # a thread here is in it: held
        time.sleep(0.5)
        self.assertEqual(wire.published(ep.received, ids, before, welcomed={1}), [])
        self.assertEqual(wire.written(os.environ["SMINOS_HOME"], ids, MACHINE, before), [])

    def asked_nothing(self, caps, why):
        tid = self.thread(S1, "worker")
        ep = self.endpoint(capabilities=caps, verdicts={tid: "deliver"})
        self.uplink()
        ep.wait_until(lambda: ep.restatement_applied(1))
        e, wrapped = self.request(1, S1, tid)
        ep.events(DESK, [wrapped])
        desk = sminos.known_project(DESK)
        ep.wait_until(lambda: any(r["id"] == e["id"] for r in channels.requests_of(desk)[1]))
        time.sleep(1.0)   # the ask pass the import marked due
        self.assertEqual(ep.frames("reach?"), [])
        sminos.forget_caches()
        self.assertEqual([(r["id"], o) for r, o in channels.carry_due(desk)], [(e["id"], channels.Outcome("pending",
                                                                                                         why))])
        self.assertEqual(threads.get(tid)["channels"], [])

    def test_an_endpoint_without_channels_is_asked_nothing_and_the_request_waits(self):
        self.asked_nothing(("reach",), "no-channels")

    def test_an_endpoint_without_reach_is_asked_nothing_and_the_request_waits(self):
        self.asked_nothing(("channels",), "endpoint")


# ------------------------------------------------------------- CH2's M6: a channel's messages, asked and kept


HOLDER = ("import fcntl, sys\n"
          "fs = [open(p, 'a') for p in sys.argv[1:]]\n"
          "for f in fs:\n"
          "    fcntl.flock(f, fcntl.LOCK_EX)\n"
          "print('held', flush=True)\n"
          "sys.stdin.read()\n")

CUT_OVER = ("import json, sys; sys.path.insert(0, %r); from unittest import mock; import sminos, sminos_channels; "
            "mock.patch.object(sminos.sibling_module('sminos_rl10'), 'cut_over', return_value=True).start(); "
            "mock.patch.object(sminos.audience_module(), 'reach_capable', return_value=True).start(); ")


class Messages(Delivering):
    """The uplink's asks about a channel's messages and the daemon's carrying out of the word (CH2's M6, the plan's
    §4), a Link's own over a real store on a machine cut over to an endpoint that decides reach: the uplink chooses
    by M2's selection, asks, and keeps the answer in a file; the daemon's channel pass carries it out. Every case of
    the consumer thread's seam holds its lock in another real process (HOLDER)."""

    def setUp(self):
        os.environ.pop("MAWS_USER_DATA", None)
        super().setUp()
        self.cut_over()

    def cut_over(self, reach=True):
        for target, name, value in ((sminos.sibling_module("sminos_rl10"), "cut_over", True),
                                    (sminos.audience_module(), "reach_capable", reach)):
            patcher = mock.patch.object(target, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        sminos.forget_caches()

    def link(self, serves=True, reach=True):
        link = uplink.Link(dict(CRED, machine=sminos.host_name()), {}, transport=mock.Mock(number=1))
        self.addCleanup(link.close)
        link.generation = 1
        link.log_lane = link.session_lane = Lane()
        link.reach, link.serves_channels = reach, serves
        link.logs[DESK] = hublog.HubLog(self.chan(DESK), link.cred)
        link.opened.add(DESK)
        link.channels.add(DESK)
        return link

    def ask_pass(self, link):
        """One tick's ask pass, as Link.tick runs it: the members the plane reads, then the words pass. The time it
        took."""
        sminos.forget_caches()
        link.next_member_read = 0.0
        link.members(time.monotonic())
        sminos.forget_caches()
        at = time.monotonic()
        link.ask_words({})
        return time.monotonic() - at

    def asks(self, link, t=("words?", "reach?")):
        return [f for f in link.session_lane.sent if f.get("t") in t and f.get("project") == DESK]

    def answer(self, link, ask, verdict, **more):
        """The endpoint's answer on `ask`, as the consumer thread dispatches it: the time it took."""
        sminos.forget_caches()
        at = time.monotonic()
        link.dispatch({"t": "words" if ask["t"] == "words?" else "reach", "id": ask["id"], "verdict": verdict,
                       **more}, None)
        return time.monotonic() - at

    def kept(self):
        d = os.path.join(self.chan(DESK).home, channels.WORDS_DIR)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def carry(self):
        """The daemon's channel pass, in this process: the kept words carried out, then the delivery."""
        sminos.forget_caches()
        got = channels.carry_words(self.chan(DESK))
        sminos.forget_caches()
        channels.deliver(self.chan(DESK))
        return got

    def held_elsewhere(self, *paths):
        """Each lock file of `paths` taken by another real process and kept until the function returned is called."""
        for path in paths:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        proc = subprocess.Popen([sys.executable, "-c", HOLDER, *paths], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                text=True)
        self.assertEqual(proc.stdout.readline().strip(), "held")

        def release():
            if proc.poll() is None:
                proc.stdin.close()
                proc.wait(10)
            proc.stdout.close()
        self.addCleanup(release)
        return release

    def delivery_lock(self, tid):
        return os.path.join(self.chan(DESK).home, "delivered", tid + ".lock")

    def record_exists(self, tid):
        return os.path.exists(os.path.join(self.chan(DESK).home, "delivered", tid + ".json"))

    # -- the path, end to end

    def test_a_message_is_asked_about_once_its_word_kept_and_the_daemon_carries_it_out(self):
        tid, sid, received = self.live()
        e = self.message((str(uuidlib.uuid4()), tid), text="across machines")   # its entry names another session
        link = self.link()
        self.ask_pass(link)
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.assertEqual((ask["t"], ask["project"], ask["session"]), ("reach?", DESK, sid),
                         "under the channel's id, to the thread's current session, whatever session the entry names")
        self.assertEqual(ask["event"], {k: v for k, v in e.items() if k != "verified"})
        at = link.session_lane.sent.index(ask)
        self.assertIn(sid, [f.get("session") for f in link.session_lane.sent[:at] if f.get("t") == "member"],
                      "its member frame first, under its own project")
        self.assertLess(self.answer(link, ask, "deliver"), 1.0)
        self.assertEqual(self.received(received), [], "the uplink pushes nothing")
        [name] = self.kept()
        self.assertTrue(name.startswith(tid + "."), name)
        self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 1, "a kept word is asked about nothing more")
        self.assertEqual(self.carry(), 1)
        self.assertEqual(len(self.got(received, "across machines")), 1)
        self.assertEqual(self.settled(tid, W1), e["seq"])
        self.assertEqual(self.kept(), [], "taken by its carrier")
        self.carry()
        self.assertEqual(len(self.got(received, "across machines")), 1, "once")
        outbox = os.path.join(self.chan(DESK).home, sminos.sibling_module("sminos_outcomes").OUTBOX)
        self.assertFalse(os.path.exists(outbox), "no outcome kept for the uplink under a channel's id")

    def test_one_ask_at_a_time_for_a_thread_and_a_writer_and_a_silent_head_holds_back_that_writer_alone(self):
        tid, sid, received = self.live()
        a1 = self.message((sid, tid), text="w1 first")
        self.message((sid, tid), text="w1 second")
        b1 = self.message((sid, tid), writer=W2, text="w2 first")
        link = self.link()
        self.ask_pass(link)
        self.ask_pass(link)
        self.assertEqual(sorted((f["event"]["writer"], f["event"]["seq"]) for f in self.asks(link)),
                         sorted([(W1, a1["seq"]), (W2, b1["seq"])]), "each writer's head, once")
        [w2] = [f for f in self.asks(link) if f["event"]["writer"] == W2]
        self.answer(link, w2, "deliver")
        self.carry()
        self.assertEqual(len(self.got(received, "w2 first")), 1, "another writer's message goes")
        self.assertEqual(self.got(received, "w1 first") + self.got(received, "w1 second"), [],
                         "the unanswered head holds back its own writer's next message")

    def test_a_refusal_is_settled_here_with_no_frame_back_and_a_peer_word_on_a_persons_message_asks_reach(self):
        tid, sid, received = self.live()
        refused = self.message((sid, tid), text="refused")
        words = self.message((sid, tid), writer="%s/human" % FAR, kind="human", text="a person's words")
        link = self.link()
        self.ask_pass(link)
        by = {f["event"]["writer"]: f for f in self.asks(link)}
        self.assertEqual(by[W1]["t"], "reach?")
        self.assertEqual(by["%s/human" % FAR]["t"], "words?", "a person's words are asked about as words")
        self.answer(link, by[W1], "refuse", reason="not-reachable")
        self.answer(link, by["%s/human" % FAR], "peer")
        self.assertEqual(self.kept(), [tid + "." + by[W1]["id"] + ".json"], "the peer word is not kept")
        [reach] = [f for f in self.asks(link, ("reach?",)) if f["event"]["writer"] == "%s/human" % FAR]
        self.assertEqual(reach["event"], by["%s/human" % FAR]["event"], "the same event, asked reach")
        self.answer(link, reach, "deliver")
        before = len(link.session_lane.sent)
        self.carry()
        self.assertEqual(self.got(received, "refused"), [])
        self.assertEqual(self.settled(tid, W1), refused["seq"], "settled refused-reach on this machine")
        self.assertEqual(len(self.got(received, "a person's words")), 1, "pushed as a peer's")
        self.assertEqual(self.settled(tid, "%s/human" % FAR), words["seq"])
        self.assertEqual(link.session_lane.sent[before:], [], "nothing goes back")

    def test_a_held_recipient_and_a_thread_whose_record_holds_an_open_entry_are_asked_nothing(self):
        tid, sid = self.stopped(mode="plan")   # not woken: held for its mode
        self.message((sid, tid), text="to a held thread")
        link = self.link()
        self.ask_pass(link)
        self.assertEqual(self.asks(link), [], "a held session is asked about nothing")
        tid2, sid2, _ = self.live(name="term-b")
        self.message((sid2, tid2), text="over an open entry")
        record = threads.get(tid2)
        with mock.patch.object(threads, "set_holders", lambda: {sid2: dict(record, pending={"op": "advance"})}):
            self.ask_pass(link)
        self.assertEqual(self.asks(link), [], "nothing asked over an open entry")

    def test_a_word_older_than_word_kept_is_carried_out_by_no_one_and_its_message_asked_again(self):
        tid, sid, received = self.live()
        self.message((sid, tid), text="too late")
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.answer(link, ask, "deliver")
        with mock.patch.object(channels.time, "time", lambda real=time.time: real() + channels.WORD_KEPT + 1):
            self.assertEqual(self.carry(), 0)
        self.assertEqual(self.got(received, "too late"), [])
        self.assertEqual(self.kept(), [], "discarded where it was found")
        with mock.patch.object(uplink.time, "monotonic", lambda real=time.monotonic: real() + channels.WORD_KEPT + 1):
            link.ask_words({})
        self.assertEqual(len(self.asks(link)), 2, "asked again once the uplink's memory of it is out")

    def test_two_words_for_one_event_push_it_once(self):
        tid, sid, received = self.live()
        e = self.message((sid, tid), text="asked twice")
        first, second = self.link(), self.link()   # the uplink restarted between: two words for one event
        for link in (first, second):
            self.ask_pass(link)
            [ask] = self.asks(link)
            self.answer(link, ask, "deliver")
        self.assertEqual(len(self.kept()), 2)
        self.carry()
        self.carry()
        self.assertEqual(len(self.got(received, "asked twice")), 1)
        self.assertEqual(self.settled(tid, W1), e["seq"])
        self.assertEqual(self.kept(), [])

    def test_two_real_processes_carrying_one_word_push_one_frame_and_neither_hangs(self):
        tid, sid, received = self.live()
        self.message((sid, tid), text="two carriers")
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.answer(link, ask, "deliver")
        code = CUT_OVER % SCRIPTS + "print(sminos_channels.carry_words(sminos.known_project(%r)))" % DESK
        procs = [subprocess.Popen([sys.executable, "-B", "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for _ in range(2)]
        outs = [p.communicate(timeout=60) for p in procs]
        self.assertEqual([p.returncode for p in procs], [0, 0], [err for _, err in outs])
        self.assertEqual(sorted(out.strip() for out, _ in outs), ["0", "1"], "one carried it, the other nothing")
        self.assertEqual(len(self.got(received, "two carriers")), 1)

    def test_a_notice_tagged_to_a_member_is_delivered_on_the_word_as_a_peers_frame_from_its_program(self):
        tid, sid, received = self.live()
        self.message((sid, tid), writer="%s/human" % FAR, kind="human", text="lease ends", notice="devcloud")
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.assertEqual(ask["t"], "words?")
        self.answer(link, ask, "words")   # sminos's own guard: a notice is nobody's words, whatever the word
        self.carry()
        [frame] = self.got(received, "lease ends")
        self.assertIn("from devcloud@%s" % FAR, frame.splitlines()[1])
        self.assertNotIn("To reply", frame, "a notice has no reply line")

    # -- the consumer thread: every lock held by another process

    def test_an_answer_writes_its_file_and_waits_on_no_lock_while_a_launch_is_stalled(self):
        tid, sid = self.stopped()
        self.message((sid, tid), text="woken on the word")
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.switch("barrier")   # a launch would stall at the engine's barrier
        release = self.held_elsewhere(os.path.join(threads.store_dir(), ".lock"),
                                      os.path.join(sminos.root(), ".metalock"), self.delivery_lock(tid),
                                      os.path.join(self.chan(DESK).home, "project.json.lock"))
        self.assertLess(self.answer(link, ask, "deliver"), 1.0, "the answer waited")
        self.assertLess(self.ask_pass(link), 1.0, "the next pass waited")
        self.assertEqual(len(self.kept()), 1, "its file is there")
        self.assertEqual((self.launches(), self.woken_got(sid, "woken on the word")), (0, []), "nothing launched")
        self.assertEqual(self.owed_to(tid), [(W1, 1)], "still owed")
        release()
        os.unlink(os.path.join(self.state, "barrier"))
        self.assertEqual(self.carry(), 1)
        self.assertTrue(wait_for(lambda: len(self.woken_got(sid, "woken on the word")) == 1), self.frames(sid))
        self.assertEqual(self.launches(), 1)

    def test_the_receipts_lock_busy_leaves_an_event_with_a_receipt_for_a_later_pass(self):
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="handed before")
        Receipts.receipt(self, DESK, sid, e, tid)
        link = self.link()
        release = self.held_elsewhere(os.path.join(sminos.holder_module().home(), "receipts.lock"))
        self.assertLess(self.ask_pass(link), 1.0, "the pass waited on the receipts' lock")
        self.assertEqual(self.asks(link), [], "not asked this pass")
        release()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.assertEqual(ask["event"]["seq"], e["seq"], "asked about on a later pass")

    def test_a_stopped_threads_receipt_left_by_a_gone_process_is_asked_about_and_woken_for_once(self):
        """test_wake_delivery's Awaiting, in a channel where the endpoint decides reach: the push would retry
        (holder_due), so the ask goes."""
        tid, sid = self.stopped()
        e = self.message((sid, tid), text="handed to a process that is gone")
        Receipts.receipt(self, DESK, sid, e, tid)
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.answer(link, ask, "deliver")
        self.carry()
        self.assertTrue(wait_for(lambda: self.woken_got(sid, "handed to a process that is gone")), self.frames(sid))
        self.assertEqual(self.launches(), 1, "woken once")
        self.carry()
        self.assertEqual(self.launches(), 1)
        self.assertEqual(self.settled(tid, W1), e["seq"])

    def test_an_ask_never_answered_is_dropped_writes_nothing_and_is_asked_again(self):
        tid, sid, _ = self.live()
        self.message((sid, tid), text="never answered")
        self.message((sid, tid), writer="%s/human" % FAR, kind="human", text="nor these words")
        link = self.link()
        self.ask_pass(link)
        first = {f["t"]: f["id"] for f in self.asks(link)}
        self.assertEqual(set(first), {"words?", "reach?"})
        release = self.held_elsewhere(self.delivery_lock(tid))
        with mock.patch.object(uplink.time, "monotonic", lambda real=time.monotonic: real() + uplink.WORDS_WAIT + 1):
            at = time.monotonic()
            link.ask_words({})
            self.assertLess(time.monotonic() - at, 1.0, "the expiry waited")
        self.assertFalse(self.record_exists(tid), "no delivery record written")
        again = [f for f in self.asks(link) if f["id"] not in first.values()]
        self.assertEqual(sorted(f["t"] for f in again), ["reach?", "words?"], "each asked again, under a new id")
        release()

    def test_a_recipient_the_plane_has_no_row_for_is_passed_by_and_asked_after_its_next_read(self):
        tid, sid, _ = self.live()
        self.message((sid, tid), text="to a new row")
        link = self.link()
        release = self.held_elsewhere(os.path.join(threads.store_dir(), ".finish", tid + ".lock"))
        link.plane.member_rows.clear()   # its session joined since the plane last read its project
        with mock.patch.object(sminos, "view_of", side_effect=AssertionError("a view read")), \
                mock.patch.object(channels, "own_row", side_effect=AssertionError("a row looked up")), \
                mock.patch.object(channels, "owing", side_effect=AssertionError("owing asked")):
            at = time.monotonic()
            link.ask_words({})
            self.assertLess(time.monotonic() - at, 1.0)
        self.assertEqual(self.asks(link), [], "passed by before owing is asked")
        release()
        self.ask_pass(link)
        self.assertEqual(len(self.asks(link)), 1, "asked after the plane's next ordinary read")

    def test_a_removal_between_the_choice_and_the_queuing_sends_no_question(self):
        tid, sid, _ = self.live()
        self.message((sid, tid), text="removed meanwhile")
        link = self.link()
        real = link.queue_asks

        def queue(batch):
            self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
            sminos.forget_caches()
            return real(batch)
        with mock.patch.object(link, "queue_asks", queue):
            self.ask_pass(link)
        self.assertEqual(self.asks(link), [])

    # -- what the word was asked for

    def released_after(self, meanwhile, again=True):
        """A message asked about, its answer kept back while meanwhile() runs, then released: (the thread, its
        session now, the inbox file or None, the link)."""
        tid, sid, proc, received = self.live_member()
        self.message((sid, tid), text="a late word")
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        got = meanwhile(tid, sid, proc)
        sminos.forget_caches()
        self.answer(link, ask, "deliver")
        self.carry()
        return tid, ask, got, link, received

    def test_a_word_released_after_a_removal_or_a_removal_and_an_add_pushes_nothing_and_is_not_owed(self):
        for add in (False, True):
            with self.subTest(add=add):
                def meanwhile(tid, sid, proc):
                    self.assertEqual(channels.change(tid, DESK, "remove", sid).state, "applied")
                    if add:
                        self.add(tid, sid, DESK)
                tid, ask, _, link, received = self.released_after(meanwhile)
                self.assertEqual(self.got(received, "a late word"), [], "dropped unused")
                self.assertEqual(self.launches(), 0)
                self.assertEqual(self.kept(), [])
                self.assertIn(self.owed_to(tid), (None, []), "not owed")

    def test_a_word_released_after_a_change_of_access_is_dropped_and_the_message_asked_again(self):
        def meanwhile(tid, sid, proc):
            records.set_policy(sid, lambda access, shares: ("private", []))
        tid, ask, _, link, received = self.released_after(meanwhile)
        self.assertEqual(self.got(received, "a late word"), [], "dropped unused")
        self.ask_pass(link)
        [again] = [f for f in self.asks(link) if f["id"] != ask["id"]]
        self.answer(link, again, "deliver")
        self.carry()
        self.assertEqual(len(self.got(received, "a late word")), 1, "delivered on the answer for the reach now")

    def test_a_word_released_after_a_hand_off_is_dropped_and_the_message_asked_for_the_job(self):
        handed = {}

        def meanwhile(tid, sid, proc):
            job, jproc = T1.Sessions.job(self, sid)
            handed["inbox"] = self.inbox(job, jproc, "j")
            self.reconcile()
            self.end(proc)
            self.reconcile()
            handed["job"] = job
        tid, ask, _, link, received = self.released_after(meanwhile)
        self.assertEqual(threads.get(tid)["current"], handed["job"])
        self.assertEqual(self.got(received, "a late word") + self.got(handed["inbox"], "a late word"), [],
                         "dropped unused")
        self.ask_pass(link)
        [again] = [f for f in self.asks(link) if f["id"] != ask["id"]]
        self.assertEqual(again["session"], handed["job"], "asked for the session that continues the thread")
        self.answer(link, again, "deliver")
        self.carry()
        self.assertEqual(len(self.got(handed["inbox"], "a late word")), 1)

    # -- a word and a launch

    def test_a_word_carried_across_a_launch_and_a_change_of_access_hands_nothing_over_and_launches_once(self):
        tid, sid = self.stopped()
        self.message((sid, tid), text="across the launch")
        link = self.link()
        self.ask_pass(link)
        [ask] = self.asks(link)
        self.answer(link, ask, "deliver")
        self.switch("barrier")
        code = CUT_OVER % SCRIPTS + "print(sminos_channels.carry_words(sminos.known_project(%r)))" % DESK
        p = subprocess.Popen([sys.executable, "-B", "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
        self.assertTrue(wait_for(lambda: self.launches() >= 1, timeout=30), "the launch entered")
        try:
            records.set_policy(sid, lambda access, shares: ("private", []))
        finally:
            os.unlink(os.path.join(self.state, "barrier"))
        _, err = p.communicate(timeout=120)
        self.assertEqual(p.returncode, 0, err)
        self.assertEqual(self.woken_got(sid, "across the launch"), [], "no text handed over on that word")
        self.assertEqual(self.owed_to(tid), [(W1, 1)])
        self.ask_pass(link)
        [again] = [f for f in self.asks(link) if f["id"] != ask["id"]]
        self.answer(link, again, "deliver")
        self.carry()
        self.assertTrue(wait_for(lambda: len(self.woken_got(sid, "across the launch")) == 1), self.frames(sid))
        self.assertEqual(self.launches(), 1, "no second launch")

    # -- sending and the wire (M4's seam)

    def test_a_messages_upload_waits_for_its_senders_row_and_a_retired_senders_goes_with_no_frame(self):
        sender, rproc, tid = self.member(name="speaker")
        self.add(tid, sender, DESK)
        link = self.link()
        hl = link.logs[DESK]
        hl.have = {}
        to = [{"session": str(uuidlib.uuid4()), "alias": "far", "thread": str(uuidlib.uuid4())}]
        sminos.log_append(self.chan(DESK), "%s/%s" % (sminos.host_name(), sender), "say", to=to,
                          text="uploaded after its frame", thread=tid)
        sminos.forget_caches()
        link.plane.member_rows.clear()   # its session joined since the plane last read its project
        with mock.patch.object(sminos, "view_of", side_effect=AssertionError("a view read")), \
                mock.patch.object(link.plane, "refresh", side_effect=AssertionError("a reconciliation")):
            at = time.monotonic()
            link.upload(hl)
            self.assertLess(time.monotonic() - at, 1.0)
        self.assertEqual([f for f in link.log_lane.sent if f.get("t") == "events"], [], "the frame waits")
        link.next_member_read = 0.0
        link.members(time.monotonic())
        link.upload(hl)
        sent = link.log_lane.sent
        [up] = [n for n, f in enumerate(sent) if f.get("t") == "events"]
        self.assertIn(sender, [f.get("session") for f in sent[:up] if f.get("t") == "member"],
                      "the sender's member frame first, under its own project")
        self.assertNotIn(DESK, [f.get("project") for f in sent if f.get("t") == "member"])
        # A sender retired since it wrote owes no frame: its message goes up, row or no row.
        self.assertEqual(self.cli("retire", sender)[0], 0)
        sminos.log_append(self.chan(DESK), "%s/%s" % (sminos.host_name(), sender), "say", to=to,
                          text="after its retirement", thread=tid)
        sminos.forget_caches()
        link.plane.member_rows.clear()
        hl.undraw()
        link.upload(hl)
        self.assertTrue(any(e.get("text") == "after its retirement" for f in link.log_lane.sent
                            if f.get("t") == "events" for e in f["events"]), "it went with no frame")

class WireSameAsBase(unittest.TestCase):
    """B11 on the wire (CH2's M6): on a machine that knows no channel, the uplink's frames — the member set, the
    project's hello and presence, the uploads, the `words?` and `reach?` asks and what their answers carry out, an
    unanswered ask asked again — and what each inbox receives are, but for ids, times and paths, what the merge
    base's code produces for the same scene (wire_scene.py, driven tick by tick in one process)."""

    def scene(self, scripts):
        home = tempfile.mkdtemp(prefix="smws.", dir="/tmp")   # short: an inbox's socket path is bounded
        self.addCleanup(shutil.rmtree, home, True)
        got = subprocess.run([sys.executable, "-B", os.path.join(HERE, "wire_scene.py"), scripts, home],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(got.returncode, 0, got.stderr[-3000:])
        text = got.stdout
        for path in (os.path.realpath(home), home, os.path.realpath(scripts), scripts):
            text = text.replace(path, "<%s>" % ("home" if "smws." in path else "scripts"))
        text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", "<ts>", text)
        keep = {"6c000b01-0000-4000-8000-0000000000b1", "6c000b02-0000-4000-8000-0000000000b2", APP}
        text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                      lambda m: m.group(0) if m.group(0) in keep else "<id>", text)
        text = re.sub(r"\b[0-9a-f]{16,64}\b", "<hex>", text)
        return json.loads(text)

    def test_the_frames_of_a_machine_with_no_channel_are_the_merge_bases(self):
        from test_channels_say import MERGE_BASE, extracted
        tmp = tempfile.mkdtemp(dir=BASE)
        base = os.path.dirname(extracted(MERGE_BASE, tmp))
        mine = self.scene(SCRIPTS)
        kinds = [f.get("t") for f in mine["frames"]]
        for t in ("member", "hello", "events", "words?", "reach?"):
            self.assertIn(t, kinds, "the scene sends what it is to compare")
        self.assertEqual(len([f for f in mine["frames"] if f.get("t") == "words?"]), 3,
                         "the person's words asked, and the unanswered one asked again")
        self.assertEqual({k: len(v) for k, v in mine["inboxes"].items()}, {"ann": 1, "bee": 1})
        theirs = self.scene(base)
        if mine != theirs:
            import difflib
            a, b = (json.dumps(x, indent=1, sort_keys=True).splitlines() for x in (theirs, mine))
            self.fail("this tree's frames differ from the merge base's:\n"
                      + "\n".join(difflib.unified_diff(a, b, "merge base", "this tree", lineterm="", n=2)))


def on(ep, conn, pred):
    """Whether the stand-in took a frame `pred` holds of on that connection."""
    with ep.cv:
        return any(n == conn and pred(f) for n, f in ep.received)


def uplink_nudge():
    """The daemon's nudge, as a write of the operation leaves it: the
    uplink scans again within its tick."""
    sminos.nudge_daemon()


if __name__ == "__main__":
    unittest.main()
