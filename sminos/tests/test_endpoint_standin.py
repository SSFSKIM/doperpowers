#!/usr/bin/env python3
"""endpoint_standin's hand-off between two machines' endpoints (#153 M3d),
which the shell suites' two-machine compositions stand on: what one
stand-in accepted (`accepted`, each event in its `echo` form), what the live
connection of another opened (`opened`), and `hand`, which carries the
first's into the second's live connection as arrivals, past what that
connection's hello said it holds and what was handed on it already. In
process, and through `serve`/`ctl` and the `hand` command as the shell
suites run them. Against the stand-ins alone, with a bare socket for the
connection sminos would hold.
Hermetic: everything is under a temporary directory.
Run: python3 -B sminos/tests/test_endpoint_standin.py
"""

import os.path, runpy  # noqa: E401 — devcloud kept out first (T1's M5), from this file's own directory, -I too
runpy.run_path(os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_isolation.py"))
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import endpoint_standin  # noqa: E402

BASE = tempfile.mkdtemp(prefix="smes-")
P, Q = "proj-1", "proj-2"
WA = "alpha/5a000001-0000-4000-8000-0000000000a1"


def ev(writer, seq, text="t"):
    return {"ts": "2026-11-07T00:00:%02d.000Z" % seq, "writer": writer, "seq": seq, "kind": "say", "text": text}


class Client:
    """A connection to a stand-in, as sminos's uplink holds one: its hello,
    then frames up, and every frame that came down kept."""

    def __init__(self, ep_dir, token, capabilities=(), **hello):
        d = endpoint_standin.read_json(os.path.join(ep_dir, "rl10.json"))
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(d["socket"])
        self.buf, self.down, self.asked = b"", [], 0
        self.up({"t": "hello", "token": token, "capabilities": list(capabilities), **hello})

    def up(self, *frames):
        self.sock.sendall(b"".join(json.dumps(f).encode() + b"\n" for f in frames))

    def read(self, pred, timeout=10):
        """The first frame down that pred holds for, reading until it comes."""
        deadline = time.monotonic() + timeout
        while True:
            for f in self.down:
                if pred(f):
                    return f
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("no such frame down")
            self.sock.settimeout(left)
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise EOFError("the connection closed")
            self.buf += chunk
            *lines, self.buf = self.buf.split(b"\n")
            self.down += [json.loads(line) for line in lines if line]

    def events(self, project, timeout=10):
        """The (writer, seq) of every arrival down for project so far, after
        a sentinel frame round-trips (so all that was sent before it is in)."""
        self.asked += 1
        sentinel = "sentinel-%d" % self.asked
        self.up({"t": "words?", "id": sentinel})   # no project: answered `words refuse` at once
        self.read(lambda f: f.get("t") == "words" and f.get("id") == sentinel, timeout)
        return [(a["event"]["writer"], a["event"]["seq"]) for f in self.down
                if f.get("t") == "events" and f.get("project") == project for a in f["events"]]

    def close(self):
        self.sock.close()


def started(name, **fields):
    ep = endpoint_standin.Endpoint(os.path.join(BASE, name), **fields)
    ep.start()
    return ep


class Accepted(unittest.TestCase):
    """`accepted`: what the stand-in took of a project, as it relays it to
    another machine's endpoint."""

    def setUp(self):
        self.ep = endpoint_standin.Endpoint(os.path.join(BASE, "acc-%s" % self._testMethodName[-20:]),
                                            identity={"org": "org-1", "hub": "h", "name": "alpha", "former": [],
                                                      "ref": "ref-alpha", "enrolled": endpoint_standin.iso()})

    def test_each_event_held_in_its_echo_form_writer_by_writer_in_order(self):
        wb = "alpha/human"
        self.ep.take(P, [ev(WA, 1), ev(wb, 1), ev(WA, 2, "two")])
        got = self.ep.accepted(P)
        self.assertEqual([(a["event"]["writer"], a["event"]["seq"]) for a in got], [(WA, 1), (WA, 2), (wb, 1)])
        self.assertEqual(got[1], self.ep.echo(P, WA, 2), "the echo's form: signed by the machine that uploaded it")
        self.assertEqual((got[1]["signer"]["kind"], got[1]["signer"]["name"], got[1]["event"]["text"]),
                         ("machine", "alpha", "two"))
        self.assertEqual(got[1]["event"]["created"], "2026-11-07T00:00:02.000Z")

    def test_only_past_after_and_never_past_a_position_held_back(self):
        self.ep.take(P, [ev(WA, 1), ev(WA, 2)])
        self.ep.set(admit=False)
        self.ep.take(P, [ev(WA, 3)])
        self.ep.set(admit=True)
        self.ep.set(admit=False)
        self.ep.take(P, [ev(WA, 4)])
        self.assertEqual([a["event"]["seq"] for a in self.ep.accepted(P, {WA: 1})], [2, 3],
                         "past after, and up to what is admitted")
        self.assertEqual(self.ep.accepted(Q), [], "a project it took nothing of: nothing")


class Opened(unittest.TestCase):
    """`opened`: the projects the live connection's hellos opened."""

    def test_the_last_hello_of_each_project_on_the_live_connection(self):
        ep = started("opened")
        try:
            self.assertEqual(ep.opened(), {"conn": None, "projects": {}}, "no connection: nothing open")
            c = Client(ep.dir, ep.token)
            c.up({"t": "hello", "project": P, "name": "p", "have": {WA: 2}},
                 {"t": "hello", "project": Q, "name": "q", "have": {}, "follow": True},
                 {"t": "hello", "project": P, "name": "p", "have": {WA: 3}})
            ep.wait_until(lambda: len([f for f in ep.frames("hello") if "project" in f]) == 3)
            got = ep.opened()
            self.assertEqual(got["conn"], 1)
            self.assertEqual({p: (o["name"], o["have"], o["follow"]) for p, o in got["projects"].items()},
                             {P: ("p", {WA: 3}, False), Q: ("q", {}, True)})
            c.close()
            c2 = Client(ep.dir, ep.token)
            c2.read(lambda f: f.get("t") == "welcome")
            ep.wait_until(lambda: ep.current is not None and ep.current.number == 2)
            self.assertEqual(ep.opened(), {"conn": 2, "projects": {}}, "a new connection opened nothing yet")
            c2.close()
        finally:
            ep.stop()


C1 = "5c2a9e10-7b3d-8f41-9a6c-2d4e6f8a0b1c"   # channels' ids (version 8)
C2 = "0123abcd-4567-8abc-a123-456789abcdef"
C3 = "9e8d7c6b-5a49-8382-b1a0-0f1e2d3c4b5a"
APP = "7d2b9c40-1f3e-4a6b-8c5d-9e0f1a2b3c4d"
S1, S2, S3 = ("6c00000%d-0000-4000-8000-0000000000c%d" % (n, n) for n in (1, 2, 3))


def member(sid, project=APP, lane="A", **fields):
    return {"t": "member", "session": sid, "alias": "m", "project": project, "lane": lane, "state": "idle",
            **fields}


class Known(unittest.TestCase):
    """`known`, MAWS's rule (its master at 8ae3b0843: the registry's
    #knownNow, rl10/members.ts's restatement and memberChannels): the logs
    the live connection opened without `follow` whose id a held member
    names, by its `project` and, while the hello listed `channels`, by a
    lane A member's `channels` (its distinct channels' ids, up to 128); a
    member frame whose project is a channel's id is that session gone. While
    no connection is live, or a welcome's restatement is not closed by
    `restated`, the last answer stands, and a held member the restatement
    left out is gone at its `restated`. And the welcome lists `channels`
    only to a hello that listed it."""

    def connect(self, ep, capabilities=("channels",), **hello):
        c = Client(ep.dir, ep.token, capabilities, **hello)
        self.addCleanup(c.close)
        welcome = c.read(lambda f: f.get("t") == "welcome")
        return c, welcome

    def settle(self, c, ep):
        """Every frame sent before it is taken (a words? with no project is answered at once, in order)."""
        c.asked += 1
        sentinel = "known-%d" % c.asked
        c.up({"t": "words?", "id": sentinel})
        c.read(lambda f: f.get("t") == "words" and f.get("id") == sentinel)

    def test_the_rule_on_hand_fed_frames(self):
        ep = started("known", capabilities=["access", "channels"])
        self.addCleanup(ep.stop)
        self.assertEqual(ep.known(), set(), "no connection and no answer yet: nothing known")
        c, welcome = self.connect(ep)
        self.assertEqual(welcome["capabilities"], ["access", "channels"])
        c.up({"t": "hello", "project": APP, "name": "app", "have": {}},
             {"t": "hello", "project": C1, "name": "desk", "have": {}},
             {"t": "hello", "project": C2, "name": "lobby", "have": {}, "follow": True},
             member(S1, channels=[C1, C2, C3, "not-a-channel", APP]))
        self.settle(c, ep)
        self.assertEqual(ep.known(), set(), "the restatement is open: the last answer stands")
        c.up({"t": "restated"})
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP, C1}, "its project and the channel opened without follow: not the "
                         "followed one, nor one not opened")
        self.assertEqual(ep.state()["known"], sorted([APP, C1]), "in its state, for the shell suites")
        c.up(member(S1))
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP}, "a member that states none no longer counts")
        c.up(member(S2, lane="B", channels=[C1]))
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP}, "a lane B member's channels never count")
        valid = ["%08x-0000-8000-8000-000000000000" % n for n in range(128)]
        c.up(member(S3, channels=valid + [C1]))
        self.settle(c, ep)
        self.assertNotIn(C1, ep.known(), "past 128 distinct channels' ids nothing counts")
        c.up(member(S3, channels=["not-a-channel"] * 100 + [valid[0]] * 40 + [C1]))
        self.settle(c, ep)
        self.assertIn(C1, ep.known(), "ids that are no channel's, and one id again, use none of the 128: past raw "
                      "slot 128, a valid id still counts")
        c.up(member(S3, channels=[C1]), member(S1, project=C1, channels=[C1]))
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP, C1}, "S3's counts")
        self.assertNotIn(S1, ep.members, "a member frame naming a channel as its project is that session gone")
        c.up({"t": "member", "session": S3, "gone": True})
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP}, "S2, lane B, still names the app; S3 gone")
        c.up({"t": "member", "session": S2, "gone": True})
        self.settle(c, ep)
        self.assertEqual(ep.known(), set(), "no member: nothing known")

    def test_without_the_capability_on_the_hello(self):
        ep = started("known-old", capabilities=["access", "channels"])
        self.addCleanup(ep.stop)
        c, welcome = self.connect(ep, capabilities=())
        self.assertEqual(welcome["capabilities"], ["access"], "the welcome lists channels only to a hello that did")
        c.up({"t": "hello", "project": APP, "name": "app", "have": {}},
             {"t": "hello", "project": C1, "name": "desk", "have": {}},
             member(S1, channels=[C1]), {"t": "restated"})
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP}, "a member's channels count only while the hello listed channels")

    def test_a_reconnection_keeps_the_last_answer_until_its_restatement_closes(self):
        ep = started("known-again", capabilities=["channels"])
        self.addCleanup(ep.stop)
        c, _ = self.connect(ep)
        c.up({"t": "hello", "project": APP, "name": "app", "have": {}},
             {"t": "hello", "project": C1, "name": "desk", "have": {}},
             member(S1, channels=[C1]), member(S3), {"t": "restated"})
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP, C1})
        c.close()
        ep.wait_until(lambda: ep.current is None)
        self.assertEqual(ep.known(), {APP, C1}, "away: the last answer stands, a restart is not every session ending")
        c2, _ = self.connect(ep)
        ep.wait_until(lambda: ep.current is not None and ep.current.number == 2)
        self.assertEqual(ep.known(), {APP, C1}, "restating, nothing opened yet: the last answer stands")
        c2.up({"t": "hello", "project": C1, "name": "desk", "have": {}, "follow": True},
              {"t": "hello", "project": APP, "name": "app", "have": {}}, member(S3))
        self.settle(c2, ep)
        self.assertEqual(ep.known(), {APP, C1}, "still restating: S1's frame not restated yet is no reason to change")
        c2.up({"t": "restated"})
        self.settle(c2, ep)
        self.assertNotIn(S1, ep.members, "S1, left out of the restatement, is gone at its restated")
        self.assertEqual(ep.known(), {APP}, "the desk, followed on this connection and named by no held member, "
                         "is known no more")
        c2.up({"t": "hello", "project": C1, "name": "desk", "have": {}}, member(S3, channels=[C1]))
        self.settle(c2, ep)
        self.assertEqual(ep.known(), {APP, C1}, "its last hello of each, and the members held, decide")

    def test_a_state_read_as_a_connection_is_installed_keeps_the_last_answer(self):
        """The new connection is `current` and its restatement open in one
        step: a read between the two (here, inside the policy's write, which
        runs before the welcome) never takes the new connection's empty
        hellos as the answer."""
        ep = started("known-gap", capabilities=["channels"])
        self.addCleanup(ep.stop)
        c, _ = self.connect(ep)
        c.up({"t": "hello", "project": APP, "name": "app", "have": {}}, member(S1), {"t": "restated"})
        self.settle(c, ep)
        self.assertEqual(ep.known(), {APP})
        c.close()
        ep.wait_until(lambda: ep.current is None)
        ep.policy = None   # so the next hello's policy is written, between its install and its welcome
        seen = []
        write = endpoint_standin.write_private

        def reading(path, data, mode=0o600):
            if path.endswith("policy.json"):
                seen.append((ep.current is not None, ep.state()["known"]))
            return write(path, data, mode)
        with mock.patch.object(endpoint_standin, "write_private", reading):
            c2, _ = self.connect(ep, policy={"read_only": False, "ceiling": "default"})
        self.assertEqual(seen, [(True, [APP])], "read in the gap: the last answer, the new connection installed")
        self.assertEqual(ep.known(), {APP}, "and still, the restatement open")
        c2.up({"t": "hello", "project": APP, "name": "app", "have": {}}, member(S1), {"t": "restated"})
        self.settle(c2, ep)
        self.assertEqual(ep.known(), {APP})

    def test_a_late_frame_of_the_replaced_connection_changes_nothing(self):
        """A member or `restated` still buffered on a connection a new one
        replaced is that connection's, and is not applied: it neither
        restates a member nor closes the new restatement."""
        ep = started("known-late", capabilities=["channels"])
        self.addCleanup(ep.stop)
        c, _ = self.connect(ep)
        c.up({"t": "hello", "project": APP, "name": "app", "have": {}}, member(S1), member(S3), {"t": "restated"})
        self.settle(c, ep)
        c2, _ = self.connect(ep)
        ep.wait_until(lambda: ep.current is not None and ep.current.number == 2)
        old = mock.Mock(number=1)
        ep.answer(old, member(S1, channels=[C1]))
        ep.answer(old, {"t": "restated"})
        self.assertEqual(ep.unrestated, {S1, S3}, "the new restatement is still open, neither member restated")
        self.assertFalse(ep.restatement_applied(2))
        self.assertNotIn("channels", ep.members[S1], "the old connection's frame was not taken")
        c2.up({"t": "hello", "project": APP, "name": "app", "have": {}}, member(S3), {"t": "restated"})
        self.settle(c2, ep)
        self.assertTrue(ep.restatement_applied(2))
        self.assertEqual((S1 in ep.members, ep.known()), (False, {APP}), "the new connection's restated decides")

    def test_a_connection_that_ends_before_its_restated_withdraws_nothing(self):
        ep = started("known-cut", capabilities=["channels"])
        self.addCleanup(ep.stop)
        c, _ = self.connect(ep)
        c.up({"t": "hello", "project": APP, "name": "app", "have": {}}, member(S1), {"t": "restated"})
        self.settle(c, ep)
        c.close()
        ep.wait_until(lambda: ep.current is None)
        c2, _ = self.connect(ep)
        ep.wait_until(lambda: ep.current is not None and ep.current.number == 2)
        c2.close()
        ep.wait_until(lambda: ep.current is None)
        self.assertIn(S1, ep.members, "a restatement cut short withdraws nothing")
        c3, _ = self.connect(ep)
        c3.up({"t": "hello", "project": APP, "name": "app", "have": {}}, {"t": "restated"})
        self.settle(c3, ep)
        self.assertEqual((S1 in ep.members, ep.known()), (False, set()), "the next one's restated does")


class Hand(unittest.TestCase):
    """`hand`: alpha's accepted events into beta's live connection, past
    what its hello said it holds and what was handed on it already."""

    def setUp(self):
        name = self._testMethodName[-20:]
        self.a = started("a-" + name)
        self.b = started("b-" + name)
        self.cursor = os.path.join(BASE, "cursor-%s.json" % name)
        self.c = Client(self.b.dir, self.b.token)

    def tearDown(self):
        self.c.close()
        self.a.stop()
        self.b.stop()

    def hello(self, have, project=P):
        n = len([f for f in self.b.frames("hello") if f.get("project") == project])
        self.c.up({"t": "hello", "project": project, "name": "p", "have": have})
        self.b.wait_until(lambda: len([f for f in self.b.frames("hello") if f.get("project") == project]) > n)

    def hand(self):
        return endpoint_standin.hand(self.a, self.b, self.cursor)

    def test_past_the_hello_then_past_what_was_handed(self):
        self.a.take(P, [ev(WA, 1), ev(WA, 2), ev(WA, 3)])
        self.a.take(Q, [ev(WA, 1)])
        self.hello({WA: 1})
        self.assertEqual(self.hand(), 2)
        self.assertEqual(self.c.events(P), [(WA, 2), (WA, 3)], "what the hello holds is not sent again")
        self.assertEqual(self.c.events(Q), [], "a project the connection did not open: nothing")
        self.assertEqual(self.hand(), 0, "handed once")
        self.a.take(P, [ev(WA, 4)])
        self.assertEqual(self.hand(), 1)
        self.assertEqual(self.c.events(P)[-1], (WA, 4))
        arrival = next(a for f in self.c.down if f.get("t") == "events" for a in f["events"] if a["event"]["seq"] == 4)
        self.assertEqual(arrival, self.a.echo(P, WA, 4), "each as alpha's echo gives it")

    def test_a_new_hello_or_a_new_connection_is_sent_what_it_lacks_again(self):
        self.a.take(P, [ev(WA, 1), ev(WA, 2)])
        self.hello({})
        self.assertEqual(self.hand(), 2)
        self.hello({WA: 1})
        self.assertEqual(self.hand(), 1, "a hello again: from what it holds")
        self.assertEqual(self.c.events(P), [(WA, 1), (WA, 2), (WA, 2)])
        self.c.close()
        self.c = Client(self.b.dir, self.b.token)
        self.b.wait_until(lambda: self.b.current is not None and self.b.current.number == 2)
        self.assertEqual(self.hand(), 0, "a new connection is handed nothing before its hello")
        self.hello({WA: 2})
        self.a.take(P, [ev(WA, 3)])
        self.assertEqual(self.hand(), 1)
        self.assertEqual(self.c.events(P), [(WA, 3)])

    def test_no_live_connection_is_handed_nothing(self):
        self.a.take(P, [ev(WA, 1)])
        self.c.close()
        self.b.wait_until(lambda: self.b.current is None)
        self.assertEqual(self.hand(), 0)


class HandThroughCtl(unittest.TestCase):
    """The same through `serve`, `ctl accepted`/`ctl opened` and the `hand`
    command, as the shell suites run them."""

    def serve(self, name, identity):
        d = os.path.join(BASE, name)
        p = subprocess.Popen([sys.executable, "-B", str(HERE / "endpoint_standin.py"), "serve", d,
                              json.dumps({"identity": identity})])
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        deadline = time.monotonic() + 10
        while not os.path.exists(os.path.join(d, "ctl.sock")):
            self.assertLess(time.monotonic(), deadline, "the stand-in came up")
            time.sleep(0.02)
        return d

    def ctl(self, d, op, arg=None):
        return json.loads(endpoint_standin.ctl_call(d, op, arg or {}))

    def test_hand_carries_alpha_s_uploads_to_beta_s_connection(self):
        ident = {"org": "org-1", "hub": "h", "name": "alpha", "former": [], "ref": "ref-alpha", "enrolled": "x"}
        a = self.serve("ctl-a", ident)
        b = self.serve("ctl-b", {**ident, "name": "beta", "ref": "ref-beta"})
        up = Client(a, self.ctl(a, "state")["token"])
        up.up({"t": "hello", "project": P, "name": "p", "have": {}},
              {"t": "events", "project": P, "events": [ev(WA, 1), ev(WA, 2)]})
        down = Client(b, self.ctl(b, "state")["token"])
        down.up({"t": "hello", "project": P, "name": "p", "have": {}})
        deadline = time.monotonic() + 10
        while len(self.ctl(a, "accepted", {"project": P})["events"]) < 2 or P not in self.ctl(b, "opened")["projects"]:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        self.assertEqual(self.ctl(a, "accepted", {"project": P, "after": {WA: 1}})["events"][0]["event"]["seq"], 2)
        out = subprocess.run([sys.executable, "-B", str(HERE / "endpoint_standin.py"), "hand", a, b],
                             capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "2")
        self.assertEqual(down.events(P), [(WA, 1), (WA, 2)])
        self.assertEqual({a["signer"]["name"] for f in down.down if f.get("t") == "events" for a in f["events"]},
                         {"alpha"}, "signed by the machine that uploaded them")
        again = subprocess.run([sys.executable, "-B", str(HERE / "endpoint_standin.py"), "hand", a, b],
                               capture_output=True, text=True, check=True)
        self.assertEqual(again.stdout.strip(), "0", "the cursor is kept between runs")
        up.up({"t": "events", "project": P, "events": [ev(WA, 3)]})
        down.up({"t": "events", "project": P, "events": [ev("beta/human", 1)]})
        deadline = time.monotonic() + 10
        while len(self.ctl(a, "accepted", {"project": P})["events"]) < 3 \
                or not self.ctl(b, "accepted", {"project": P})["events"]:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        back = Client(a, self.ctl(a, "state")["token"])   # alpha reconnects: its own connection opens nothing yet
        while self.ctl(a, "opened")["conn"] != 2:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        both = subprocess.run([sys.executable, "-B", str(HERE / "endpoint_standin.py"), "relay", a, b],
                              capture_output=True, text=True, check=True)
        self.assertEqual(both.stdout.strip(), "1", "relay: each way, alpha's to beta's connection; beta's waits "
                                                   "for a hello on alpha's")
        self.assertEqual(down.events(P), [(WA, 1), (WA, 2), (WA, 3)])
        back.up({"t": "hello", "project": P, "name": "p", "have": {WA: 3}})
        while P not in self.ctl(a, "opened")["projects"]:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        both = subprocess.run([sys.executable, "-B", str(HERE / "endpoint_standin.py"), "relay", a, b],
                              capture_output=True, text=True, check=True)
        self.assertEqual(both.stdout.strip(), "1")
        self.assertEqual(back.events(P), [("beta/human", 1)], "beta's upload reaches alpha's new connection")
        for c in (up, down, back):
            c.close()


class RelayFailures(unittest.TestCase):
    """Only a connection that went is passed over; any other failure of a
    stand-in's control or of its answer fails the hand-off, saying why."""

    def test_a_connection_gone_mid_pass_is_passed_over(self):
        a = started("gone-a")
        self.addCleanup(a.stop)
        a.take(P, [ev(WA, 1)])

        class Gone:
            def opened(self):
                return {"conn": 1, "projects": {P: {"name": "p", "have": {}, "follow": False, "at": 0}}}

            def events(self, project, wrapped):
                raise endpoint_standin.Disconnected("the connection is closed")

        self.assertEqual(endpoint_standin.hand(a, Gone(), os.path.join(BASE, "gone-cursor.json")), 0)

    def answering(self, name, answer):
        """A ctl socket that answers every request with `answer`."""
        d = os.path.join(BASE, name)
        os.makedirs(d, exist_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(os.path.join(d, "ctl.sock"))
        srv.listen(8)
        self.addCleanup(srv.close)

        def serve():
            while True:
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                with c:
                    c.recv(1 << 16)
                    c.sendall(answer)
        threading.Thread(target=serve, daemon=True).start()
        return d

    def relay(self, *dirs):
        return subprocess.run([sys.executable, "-B", str(HERE / "endpoint_standin.py"), "relay", *dirs],
                              capture_output=True, text=True)

    def test_a_control_error_or_an_answer_that_is_no_json_fails_the_relay(self):
        a = self.answering("err-a", b'{"error": "KeyError(\'project\')"}\n')
        b = self.answering("err-b", b'{"conn": 1, "projects": {}}\n')
        out = self.relay(a, b)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("KeyError", out.stderr)
        c = self.answering("garbled", b"not json\n")
        out = self.relay(c, b)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("JSONDecodeError", out.stderr)

    def test_a_stand_in_not_there_fails_the_relay(self):
        b = self.answering("there", b'{"conn": null, "projects": {}}\n')
        out = self.relay(os.path.join(BASE, "nowhere"), b)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("nowhere", out.stderr + out.stdout)


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
