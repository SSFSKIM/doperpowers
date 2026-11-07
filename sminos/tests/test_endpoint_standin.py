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

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
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

    def __init__(self, ep_dir, token):
        d = json.load(open(os.path.join(ep_dir, "rl10.json")))
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(d["socket"])
        self.buf, self.down, self.asked = b"", [], 0
        self.up({"t": "hello", "token": token, "capabilities": []})

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
        up.close()
        down.close()


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
