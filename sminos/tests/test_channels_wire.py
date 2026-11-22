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
import os
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
import sminos_rl10 as rl10  # noqa: E402
import sminos_threads as threads  # noqa: E402
import sminos_uplink as uplink  # noqa: E402
import sminos_hublog as hublog  # noqa: E402
import test_threads as T1  # noqa: E402 — its fixtures by module
from test_channels_requests import OTHER, SAME_ID, SIGNER, Requests  # noqa: E402

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
        with mock.patch.object(link, "member_under", return_value=False):
            self.ask_pass(link)
        self.assertEqual(self.asks(link), [])
        self.assertFalse(link.words_due, "no row: not asked again at every tick")
        link.members_unsent = {sid}
        with mock.patch.object(link, "member_under", return_value=False):
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
        self.assertEqual(len(self.asks(link)), 2, "asked again")

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
        self.ask_pass(link)   # the ordinary pass
        self.assertEqual(len(self.asks(link)), 2, "asked again at the ordinary interval")
        self.answer(link, self.asks(link)[-1], "deliver")
        self.ask_pass(link)
        self.assertEqual(self.held(tid), [DESK])

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
