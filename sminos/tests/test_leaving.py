#!/usr/bin/env python3
"""Leaving a project (the project registry's M6; MAWS
docs/doperpowers/plans/2026-11-10-project-registry.md, Interfaces §E.4): a
followed project with no folder here that complete org frames lack for
LEAVE_AFTER_S of counted time leaves, out of both the uplink's subscription
(hub_projects) and `sminos list --org`, its log directory kept; time
disconnected, under an incomplete frame or one without `complete` adds
nothing; a frame that lists it sets the count to zero and follows it again;
a project held here never leaves; the count and the set survive a restart.
The counting clock is the test's (uplink.leave_clock).

Hermetic: HOME, SMINOS_HOME and MAWS_USER_DATA are temporary, `claude` is a
stub, the endpoint is sminos's own stand-in on a Unix socket there.
Run: python3 -B -I sminos/tests/test_leaving.py
"""

import json
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
T = os.path.realpath(tempfile.mkdtemp(prefix="smleave.", dir="/tmp"))   # short: a Unix socket's path is bounded
for k in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
          "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(k, None)
os.makedirs(os.path.join(T, "bin"))
with open(os.path.join(T, "bin", "claude"), "w") as f:
    f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
os.chmod(os.path.join(T, "bin", "claude"), 0o755)
os.environ.update(PATH=os.path.join(T, "bin") + os.pathsep + os.environ.get("PATH", ""), SMINOS_DERIVE_EVERY="0")
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

ORG, MACHINE, URL = "org-1", "testhost", "http://127.0.0.1:9"
CRED = {"org": ORG, "hub": URL, "machine": MACHINE, "key": None}
GONE = "2a000001-0000-4000-8000-0000000000a1"     # followed here, no folder: the one that can leave
STAYS = "2a000002-0000-4000-8000-0000000000a2"    # listed in every frame
ROOTED = "2a000003-0000-4000-8000-0000000000a3"   # a folder of it here
DECL = "2a000004-0000-4000-8000-0000000000a4"     # a declared location here
HELD = "2a000005-0000-4000-8000-0000000000a5"     # a session of it here
STALE = "2a000006-0000-4000-8000-0000000000a6"    # registered at a folder that is gone
REMOTE_SID = "2b000001-0000-4000-8000-0000000000b1"
DAY = uplink.LEAVE_AFTER_S


def machine(name):
    """A fresh installation under T/<name>, cut over as MACHINE of ORG."""
    base = os.path.join(T, name)
    os.environ.update(HOME=os.path.join(base, "h"), SMINOS_HOME=os.path.join(base, "s"),
                      MAWS_USER_DATA=os.path.join(base, "m"))
    for d in (os.path.join(base, "h", ".claude", "sessions"), os.path.join(base, "s", "daemon")):
        os.makedirs(d, mode=0o700)
    sminos.write_json(rl10.identity_path(), {
        "org": ORG, "hub": URL, "name": MACHINE, "former": {}, "ref": "machine-ref-1",
        "enrolled": "2026-11-10T00:00:00.000Z", "cutover": "2026-11-10T00:00:01.000Z", "build": "b"}, mode=0o600)
    sminos.forget_caches()
    return base


def entry(pid, name, kind="hub"):
    return {"id": pid, "name": name, "kind": kind, "retired": False}


def org_frame(*pids, complete=True, locations=None):
    """An org frame listing `pids` (each named after its id's first group)."""
    frame = {"t": "org", "projects": [entry(p, "p" + p[:8]) for p in pids],
             "machines": [{"name": MACHINE, "online": False}]}
    if complete is not None:
        frame["complete"] = complete
    if locations is not None:
        frame["locations"] = locations
    return frame


def leaving_file():
    try:
        with open(sminos.leaving_path()) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"counted": {}, "left": []}


def org_listed(pid):
    """Whether `sminos list --org --json` (the real CLI) shows the remote
    session of project `pid`."""
    r = subprocess.run([sys.executable, "-B", "-I", os.path.join(SCRIPTS, "sminos.py"), "list", "--org", "--json"],
                       cwd=os.environ["HOME"], env=dict(os.environ), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    return any(row.get("project_id") == pid for row in json.loads(r.stdout))


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.t

    def add(self, s):
        with self.lock:
            self.t += s


class Lane:
    """A Link's lane that keeps what it is sent, written as taken."""

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


class Counting(unittest.TestCase):
    """Through a Link's `org` handler and its scan's look (leave_pass), the
    clock the test's."""

    def setUp(self):
        self.base = machine("count-%d" % time.monotonic_ns())
        self.clock = Clock()
        patch = mock.patch.object(uplink, "leave_clock", self.clock)
        patch.start()
        self.addCleanup(patch.stop)
        self.link = None
        self.connect()
        self.org(org_frame(GONE, STAYS))
        self.scan()
        p = sminos.find_project("p" + GONE[:8])
        sminos.log_append(p, "other/%s" % REMOTE_SID, "joined", session=REMOTE_SID, alias="faraway",
                          name_source="user", machine="other", cwd="/d", worktree="", role="", seat="", by="")
        sminos.forget_caches()

    def connect(self):
        """A new connection (a new Link, as serve makes one), the last one closed."""
        self.disconnect()
        self.link = uplink.Link(CRED, {}, transport=mock.Mock(number=1))
        self.link.generation = 1
        self.link.log_lane = self.link.session_lane = Lane()

    def disconnect(self):
        if self.link is not None:
            self.link.close()
            self.link = None

    def tearDown(self):
        self.disconnect()

    def org(self, frame):
        self.link.dispatch(frame, None)

    def scan(self):
        """The tick's scan: the hub projects as listed, then the look; the ids that left."""
        sminos.forget_caches()
        self.link.member_known = {p.id: p for p in sminos.known_projects()}
        known = uplink.hub_projects(CRED)
        return self.link.leave_pass(known)[0]

    def run_for(self, seconds, step=30):
        """`seconds` of the clock, a scan's look every `step`; the ids that left."""
        gone = []
        while seconds > 0:
            self.clock.add(min(step, seconds))
            seconds -= step
            gone += self.scan()
        return gone

    def counted(self):
        return self.link.leaving.counted.get(GONE, 0.0)

    def test_a_project_complete_frames_lack_for_the_period_leaves_and_comes_back_when_listed(self):
        self.assertIn(GONE, uplink.hub_projects(CRED))
        self.assertTrue(org_listed(GONE), "the remote session is listed while followed")
        self.org(org_frame(STAYS))
        self.assertEqual(self.run_for(DAY - 60, step=60), [])
        self.assertIn(GONE, uplink.hub_projects(CRED), "not yet")
        self.assertEqual(self.run_for(60), [GONE])
        sminos.forget_caches()
        self.assertNotIn(GONE, uplink.hub_projects(CRED), "out of the subscription")
        self.assertNotIn(GONE, {p.id for p in sminos.org_scope()}, "out of the org scope")
        self.assertFalse(org_listed(GONE), "out of list --org")
        self.assertTrue(os.path.isdir(os.path.join(sminos.projects_root(), GONE, "log")), "its log stays")
        self.assertEqual(leaving_file()["left"], [GONE])
        self.assertIn(STAYS, uplink.hub_projects(CRED), "a listed project is never counted")
        # A restart: the set is the file's.
        self.connect()
        sminos.forget_caches()
        self.assertNotIn(GONE, uplink.hub_projects(CRED))
        # A frame that lists it again: out of the set, followed again.
        self.org(org_frame(GONE, STAYS))
        sminos.forget_caches()
        self.assertIn(GONE, uplink.hub_projects(CRED))
        self.assertTrue(org_listed(GONE))
        self.assertEqual(leaving_file(), {"counted": {}, "left": []})

    def test_disconnected_incomplete_or_silent_time_adds_nothing(self):
        self.org(org_frame(STAYS))
        self.run_for(600)
        self.assertEqual(self.counted(), 600)
        # Disconnected: no Link at all, then a connection before its first frame.
        self.disconnect()
        self.clock.add(5 * DAY)
        self.connect()
        self.run_for(600)
        self.assertEqual(self.counted(), 600, "kept over the restart, still while no frame came")
        # An incomplete frame, and one that says nothing of `complete`.
        self.org(org_frame(STAYS, complete=False))
        self.run_for(3 * DAY, step=60)
        self.org(org_frame(STAYS, complete=None))
        self.run_for(3 * DAY, step=60)
        self.assertEqual(self.counted(), 600)
        self.assertIn(GONE, uplink.hub_projects(CRED))
        # Complete again: it runs from where it stood.
        self.org(org_frame(STAYS))
        self.run_for(300)
        self.assertEqual(self.counted(), 900)
        # A gap no look saw (a machine asleep) counts at most LEAVE_STEP_MAX.
        self.clock.add(2 * DAY)
        self.scan()
        self.assertEqual(self.counted(), 900 + uplink.LEAVE_STEP_MAX)
        self.assertIn(GONE, uplink.hub_projects(CRED))

    def test_a_frame_that_lists_it_sets_the_count_to_zero(self):
        self.org(org_frame(STAYS))
        self.run_for(DAY - 120, step=60)
        self.org(org_frame(GONE, STAYS))
        self.assertEqual(self.counted(), 0)
        self.assertNotIn(GONE, leaving_file()["counted"], "the reset is kept")
        self.org(org_frame(STAYS))
        self.assertEqual(self.run_for(DAY - 120, step=60), [], "counted from zero")
        self.assertIn(GONE, uplink.hub_projects(CRED))
        # Kept across a restart while it runs (the file at most LEAVE_SAVE_EVERY behind).
        before = self.counted()
        self.connect()
        self.assertGreaterEqual(self.link.leaving.counted.get(GONE, 0.0), before - uplink.LEAVE_SAVE_EVERY)

    def test_a_project_held_here_never_leaves(self):
        own = sminos.machine_project_id(ORG, MACHINE)
        other_machine = sminos.machine_project_id(ORG, "delta")
        rooted = os.path.join(self.base, "w", "rooted")
        decl = os.path.join(self.base, "w", "decl")
        for d in (rooted, decl):
            os.makedirs(d)
        with open(os.path.join(rooted, ".smns"), "w") as f:
            json.dump({"project": ROOTED, "name": "rooted", "hub": {"org": ORG}}, f)
        st = os.stat(decl)
        birth = sminos.birth_ns(getattr(st, "st_birthtime", 0))
        at = [{"path": sminos.canonical(decl), "project": DECL, "stated": "minted",
               "anchor": {"dev": str(st.st_dev), "ino": str(st.st_ino), "birth": str(int(birth or 0))}}]
        frame = org_frame(GONE, STAYS, ROOTED, DECL, HELD, locations={"gen": 1, "at": at})
        frame["projects"] += [entry(own, MACHINE, "machine"), entry(other_machine, "delta", "machine")]
        self.org(frame)
        hub = {"url": URL, "org": ORG}
        sminos.project_path(sminos.make_project(ROOTED, "rooted", "", rooted, hub), "log")
        uplink.register_own(CRED)
        self.scan()
        self.link.plane.members[HELD] = {REMOTE_SID}   # a session of it here
        known = uplink.hub_projects(CRED)
        for pid in (own, other_machine, ROOTED, DECL, HELD):
            self.assertIn(pid, known)
        # Every frame from now lacks them all.
        self.org(org_frame(STAYS, locations={"gen": 2, "at": at}))
        self.assertEqual(self.run_for(2 * DAY, step=60), [GONE])
        known = uplink.hub_projects(CRED)
        for pid in (own, other_machine, ROOTED, DECL, HELD):
            self.assertIn(pid, known, pid)
            self.assertNotIn(pid, self.link.leaving.counted, pid)
        self.assertNotIn(GONE, known)
        # One that left and is held now (a session joined it here) comes back, its count gone.
        self.link.plane.members[GONE] = {REMOTE_SID}
        self.scan()
        sminos.forget_caches()
        self.assertIn(GONE, uplink.hub_projects(CRED))
        self.assertEqual(leaving_file()["left"], [])
        # A count that ran stops and drops once the project is held.
        del self.link.plane.members[GONE]
        self.scan()   # the look that finds it followed again: what came before was held time
        self.run_for(600)
        self.assertEqual(self.counted(), 600)
        self.link.plane.members[GONE] = {REMOTE_SID}
        self.run_for(600)
        self.assertNotIn(GONE, self.link.leaving.counted)


    def test_a_registered_root_that_is_gone_is_no_folder_here(self):
        gone_root = os.path.join(self.base, "w", "was-here")
        os.makedirs(gone_root)
        with open(os.path.join(gone_root, ".smns"), "w") as f:
            json.dump({"project": STALE, "name": "stale", "hub": {"org": ORG}}, f)
        self.org(org_frame(GONE, STAYS, STALE))
        sminos.project_path(sminos.make_project(STALE, "stale", "", gone_root, {"url": URL, "org": ORG}), "log")
        self.scan()
        self.org(org_frame(GONE, STAYS))
        self.run_for(600)
        self.assertNotIn(STALE, self.link.leaving.counted, "its folder is here: held")
        shutil.rmtree(gone_root)
        self.assertEqual(self.run_for(DAY + 60, step=60), [STALE], "GONE is listed")
        # Its folder back: it comes back at the next look, the set written at once.
        os.makedirs(gone_root)
        with open(os.path.join(gone_root, ".smns"), "w") as f:
            json.dump({"project": STALE, "name": "stale", "hub": {"org": ORG}}, f)
        self.scan()
        self.assertEqual(leaving_file()["left"], [])
        sminos.forget_caches()
        self.assertIn(STALE, uplink.hub_projects(CRED))

    def test_a_frame_counts_from_when_it_was_taken_and_whether_or_not_it_is_kept(self):
        self.org(org_frame(STAYS))
        self.run_for(600)
        # An incomplete frame the reader took 30 s ago, handled only now (a tick stalled):
        # the 30 s counted since are taken back.
        self.clock.add(30)
        self.scan()
        self.assertEqual(self.counted(), 630)
        self.link.received = time.time() - 30
        self.org(org_frame(STAYS, complete=False))
        self.link.received = None
        self.assertAlmostEqual(self.counted(), 600, delta=1)
        # One whose write fails still stops the count: it is the connection's last frame.
        self.org(org_frame(STAYS))
        self.run_for(300)
        before = self.counted()
        with mock.patch.object(uplink.sminos, "write_json", side_effect=OSError(28, "No space left on device")):
            self.org(org_frame(STAYS, complete=False))
        self.run_for(3 * DAY, step=60)
        self.assertEqual(self.counted(), before)


class Wire(unittest.TestCase):
    """The real uplink against the endpoint stand-in: a project that leaves
    is out of the next connection's hellos, and a frame that lists it opens
    it again."""

    def setUp(self):
        machine("wire-%d" % time.monotonic_ns())
        self.clock = Clock()
        for patch in (mock.patch.object(uplink, "leave_clock", self.clock),
                      mock.patch.object(uplink, "LEAVE_STEP_MAX", 10.0 * DAY)):
            patch.start()
            self.addCleanup(patch.stop)
        self.ep = endpoint_standin.Endpoint(os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint"))
        self.ep.org = {k: v for k, v in org_frame(GONE, STAYS).items() if k != "t"}
        self.ep.start()
        self.addCleanup(self.ep.stop)
        halt, box = threading.Event(), {}
        thread = threading.Thread(target=lambda: box.update(kept=uplink.run_rl10(halt.is_set, halt)), daemon=True)
        thread.start()

        def stop():
            halt.set()
            thread.join(30)
            if box.get("kept") is not None:
                box["kept"].close()
        self.addCleanup(stop)

    def hello_of(self, pid):
        self.ep.wait_until(lambda: pid in self.ep.opened()["projects"])
        return self.ep.opened()["projects"][pid]

    def test_the_subscription_leaves_it_and_takes_it_back(self):
        self.assertTrue(self.hello_of(GONE)["follow"])
        first = self.ep.opened()["conn"]
        self.ep.org = {k: v for k, v in org_frame(STAYS).items() if k != "t"}
        self.ep.send(dict(org_frame(STAYS)))
        deadline = time.monotonic() + 30
        while GONE not in leaving_file()["left"]:
            # Jumps until one lands after the frame was taken (one before it counts under the frame before).
            self.assertLess(time.monotonic(), deadline, "it did not leave")
            self.clock.add(DAY)
            time.sleep(0.5)
        self.ep.wait_until(lambda: self.ep.opened()["conn"] not in (None, first)
                           and STAYS in self.ep.opened()["projects"])
        self.ep.wait_until(lambda: any(f.get("t") == "restated"
                                       for f in self.ep.frames(conn=self.ep.opened()["conn"])))
        self.assertNotIn(GONE, self.ep.opened()["projects"], "the next connection does not open it")
        self.assertTrue(os.path.isdir(os.path.join(sminos.projects_root(), GONE, "log")))
        self.ep.send(dict(org_frame(GONE, STAYS)))
        self.assertTrue(self.hello_of(GONE)["follow"], "followed again")


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(T, ignore_errors=True)
