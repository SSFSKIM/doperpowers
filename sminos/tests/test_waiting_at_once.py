#!/usr/bin/env python3
"""A session's `waiting` reaches another machine at once: a person acts on
that word, so it and the word that ends it are published on the daemon's
first tick that sees them, where a change between busy and idle waits for a
second tick (the flip inside a tool round); and the uplink's session plane,
which looks at the engine's records five times a second, asks the daemon for
that tick at any look that finds a session's word entered or left
`waiting`, its first look and its last included — one nudge a look,
however many sessions moved. Hermetic: HOME and
SMINOS_HOME are temporary.
Run: python3 -B sminos/tests/test_waiting_at_once.py
"""

import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")
T = os.path.realpath(tempfile.mkdtemp(prefix="smw.", dir="/tmp"))
for k in ("CLAUDE_CODE_SESSION_ID", "SMNS_INTERNAL", "DAEMON_HOME", "AGORA_HOME", "CLAUDE_CONFIG_DIR", "MAWS_LANE",
          "SMINOS_RL10", "MAWS_USER_DATA", "SMNS_MEMBER", "XDG_CONFIG_HOME"):
    os.environ.pop(k, None)
os.environ.update(HOME=os.path.join(T, "home"), SMINOS_HOME=os.path.join(T, "s"), DAEMON_HOST="testhost",
                  CLAUDE_CODE_TMPDIR=os.path.join(T, "tmp"))
SESSIONS = os.path.join(os.environ["HOME"], ".claude", "sessions")
os.makedirs(SESSIONS)
os.makedirs(os.environ["SMINOS_HOME"])
sys.path.insert(0, SCRIPTS)

import sminos_daemon as daemon  # noqa: E402
import sminos_plane as plane  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

A = "6f00000a-0000-4000-8000-0000000000aa"


class Publish(unittest.TestCase):
    """publish_state over the ticks of one local member, each tick's view
    holding the word last published for it, as the log would."""

    def setUp(self):
        self.published, self.record = None, {}

    def tick(self, word):
        """One tick seeing `word`: what it published, or None."""
        info = {A: {"state": {"state": self.published}}} if self.published else {}
        view = types.SimpleNamespace(members=[types.SimpleNamespace(local=True, session=A, state=word)], info=info)
        out = []

        def lifecycle(project, session, kind, required=True, **body):
            out.append(body["state"])
            return [body]
        with mock.patch.object(daemon.sminos, "lifecycle", side_effect=lifecycle):
            n = daemon.publish_state(None, view, self.record)
        self.assertEqual(n, len(out))
        if out:
            self.published = out[-1]
        return out[-1] if out else None

    def test_busy_and_idle_wait_for_a_second_tick(self):
        self.assertEqual(self.tick("busy"), "busy", "the first word at once")
        self.assertIsNone(self.tick("idle"), "one tick of idle publishes nothing")
        self.assertIsNone(self.tick("busy"), "the flip back, nothing")
        self.assertIsNone(self.tick("idle"))
        self.assertEqual(self.tick("idle"), "idle", "held for a second tick")

    def test_entering_waiting_is_published_at_once(self):
        self.tick("busy")
        self.assertEqual(self.tick("waiting"), "waiting")

    def test_entering_waiting_over_a_held_candidate(self):
        self.tick("idle")
        self.assertIsNone(self.tick("busy"), "busy, a candidate")
        self.assertEqual(self.tick("waiting"), "waiting")

    def test_the_word_after_waiting_is_published_at_once(self):
        self.tick("busy")
        self.tick("waiting")
        self.assertEqual(self.tick("busy"), "busy", "answered: busy at once")
        self.tick("waiting")
        self.assertEqual(self.tick("idle"), "idle", "or idle at once")

    def test_a_waiting_of_one_tick_is_published_and_so_is_its_end(self):
        self.tick("busy")
        self.assertEqual([self.tick(w) for w in ("waiting", "busy")], ["waiting", "busy"])

    def test_after_waiting_busy_and_idle_wait_again(self):
        self.tick("waiting")
        self.tick("busy")
        self.assertIsNone(self.tick("idle"))
        self.assertEqual(self.tick("idle"), "idle")

    def test_a_held_word_is_not_published_again(self):
        self.tick("waiting")
        self.assertIsNone(self.tick("waiting"))
        self.assertEqual(self.record.get("candidates"), {})


class PlaneNudge(unittest.TestCase):
    """The plane's look at the engine's records nudges the daemon when a
    live session's word entered or left `waiting` since its last look."""

    def setUp(self):
        self.holders, self.records = [], {}
        self.p = plane.Plane("testhost", lambda: None, transcripts=plane.Transcripts(), disk=plane.Disk())
        self.addCleanup(self.p.close)
        self.mtime = 1_700_000_000_000_000_000

    def tearDown(self):
        for h in self.holders:
            h.kill()
            h.wait(5)
        for path in self.records.values():
            os.unlink(path)

    def session(self, status):
        sid = str(uuid.uuid4())
        h = subprocess.Popen(["sleep", "3600"])
        self.holders.append(h)
        self.records[sid] = os.path.join(SESSIONS, "%d.json" % h.pid)
        self.pids = getattr(self, "pids", {})
        self.pids[sid] = h.pid
        self.status(sid, status)
        return sid

    def status(self, sid, word):
        path = self.records[sid]
        with open(path, "w") as f:
            json.dump({"pid": self.pids[sid], "sessionId": sid, "cwd": T, "kind": "interactive", "status": word}, f)
        self.mtime += 1_000_000_000
        os.utime(path, ns=(self.mtime, self.mtime))   # a rewrite of the same size is still a change

    def look(self):
        """One look of the plane: how many nudges it made."""
        self.p.next_scan = 0.0
        with mock.patch.object(plane.sminos, "nudge_daemon") as nudge:
            self.p.tick({})
        return nudge.call_count

    def test_entering_and_leaving_waiting_nudge(self):
        a = self.session("busy")
        self.assertEqual(self.look(), 0, "a first look with nobody waiting")
        self.assertIn(a, self.p.live)
        self.status(a, "waiting")
        self.assertEqual(self.look(), 1, "entered waiting")
        self.assertEqual(self.look(), 0, "still waiting: no other nudge")
        self.status(a, "busy")
        self.assertEqual(self.look(), 1, "left waiting")
        self.status(a, "waiting")
        self.look()
        self.status(a, "idle")
        self.assertEqual(self.look(), 1, "left waiting for idle")

    def test_busy_and_idle_do_not_nudge(self):
        a = self.session("busy")
        self.look()
        self.status(a, "idle")
        self.assertEqual(self.look(), 0)
        self.status(a, "busy")
        self.assertEqual(self.look(), 0)

    def test_a_look_outside_the_tick_nudges_too(self):
        """A forced presence (a project opened on the stream) takes the
        records itself: the move it sees is nudged there, not lost to the
        tick's next look, which compares against it."""
        a = self.session("busy")
        self.look()
        self.status(a, "waiting")
        with mock.patch.object(plane.sminos, "nudge_daemon") as nudge:
            self.p.presence("0d9e8f7a-6b5c-4d3e-a2f1-0e9d8c7b6a59", force=True)
        self.assertEqual(nudge.call_count, 1)
        self.assertEqual(self.look(), 0, "the tick's next look has nothing new")

    def test_a_session_rpc_s_look_nudges_too(self):
        """An RPC's admission reads the session's record afresh: a move it
        sees is nudged there, not lost to the plane's next look."""
        a = self.session("busy")
        self.look()
        self.status(a, "waiting")
        with mock.patch.object(plane.sminos, "nudge_daemon") as nudge:
            uplink.Here(types.SimpleNamespace(plane=self.p)).record(a)
        self.assertEqual(nudge.call_count, 1)
        self.assertEqual(self.look(), 0, "the plane's next look has nothing new")

    def test_a_session_first_seen_waiting_nudges(self):
        self.session("busy")
        self.look()
        self.session("waiting")
        self.assertEqual(self.look(), 1, "a new or resumed session stopped on a prompt at once")
        self.session("busy")
        self.assertEqual(self.look(), 0, "one first seen busy does not")

    def test_a_session_that_ends_waiting_nudges(self):
        a, b = self.session("waiting"), self.session("busy")
        self.look()
        for sid in (a, b):
            h = next(h for h in self.holders if h.pid == self.pids[sid])
            h.kill()
            h.wait(5)
            if sid == a:
                self.assertEqual(self.look(), 1, "its word is stopped or gone now")
            else:
                self.assertEqual(self.look(), 0, "one that ends busy does not")

    def test_a_first_look_with_a_session_waiting_nudges_once(self):
        """A new stream's plane: whatever waits then is published at once."""
        self.session("waiting")
        self.session("busy")
        self.assertEqual(self.look(), 1)
        self.assertEqual(self.look(), 0)

    def test_one_nudge_a_look_however_many_moved(self):
        a, b, c = self.session("busy"), self.session("idle"), self.session("waiting")
        self.look()
        self.status(a, "waiting")
        self.status(b, "waiting")
        self.status(c, "busy")
        self.assertEqual(self.look(), 1)


if __name__ == "__main__":
    unittest.main()
