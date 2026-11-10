#!/usr/bin/env python3
"""The org frame's `locations`, kept and acknowledged (the project registry's
M5; MAWS docs/doperpowers/plans/2026-11-10-project-registry.md, Interfaces
§D and §E.3): keep_org writes the directory, `locations` and `complete` in
one atomic write of daemon/org.json; a frame without `locations` keeps the
held ones, one with it replaces them; each kept frame is answered
`locations-kept {gen}` on its connection; the hello lists `locations`. And
the unknown state: on a machine whose endpoint's welcome lists `locations`
and whose org file holds none, a session keeps the project it is recorded in,
so over an upgrade, a daemon restart and a deleted org file no session moves
twice (design acceptance 11, sminos's part).

Hermetic: HOME, SMINOS_HOME and MAWS_USER_DATA are temporary, `claude` is a
stub, the endpoint is sminos's own stand-in on a Unix socket there.
Run: python3 -B -I sminos/tests/test_locations_kept.py
"""

import glob
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
T = os.path.realpath(tempfile.mkdtemp(prefix="smloc.", dir="/tmp"))   # short: a Unix socket's path is bounded
for k in ("SMINOS_RL10", "MAWS_USER_DATA", "CLAUDE_CODE_SESSION_ID", "DAEMON_HOME", "AGORA_HOME", "DAEMON_HOST",
          "MAWS_LANE", "SMNS_MEMBER", "SMNS_INTERNAL", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(k, None)
os.makedirs(os.path.join(T, "bin"))
with open(os.path.join(T, "bin", "claude"), "w") as f:
    f.write('#!/bin/sh\n[ "$1" = agents ] && echo "[]"\nexit 0\n')
os.chmod(os.path.join(T, "bin", "claude"), 0o755)
os.environ.update(PATH=os.path.join(T, "bin") + os.pathsep + os.environ.get("PATH", ""), SMINOS_DERIVE_EVERY="0")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "skills", "sminos", "scripts"))
sys.path.insert(0, HERE)
import endpoint_standin  # noqa: E402
import sminos  # noqa: E402
import sminos_audience as audience  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_rl10 as rl10  # noqa: E402
import sminos_uplink as uplink  # noqa: E402

ORG, MACHINE, URL = "org-1", "testhost", "http://127.0.0.1:9"
CRED = {"org": ORG, "hub": URL, "machine": MACHINE, "key": None}
MINTED = "11111111-1111-4111-8111-111111111111"
S1 = "6c000001-0000-4000-8000-0000000000c1"
S2 = "6c000002-0000-4000-8000-0000000000c2"
PROCS = []


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


def folder(base, name):
    d = os.path.join(base, "w", name)
    os.makedirs(d, exist_ok=True)
    return d


def minted(path, pid):
    st = os.stat(path)
    birth = sminos.birth_ns(getattr(st, "st_birthtime", 0))
    return {"path": sminos.canonical(path), "project": pid, "stated": "minted",
            "anchor": {"dev": str(st.st_dev), "ino": str(st.st_ino), "birth": str(int(birth or 0))}}


def org_frame(at=None, gen=1, complete=None):
    """An org frame naming MINTED, with `locations` {gen, at} where `at` is given."""
    frame = {"t": "org", "projects": [{"id": MINTED, "name": "plain", "kind": "hub", "retired": False}],
             "machines": [{"name": MACHINE, "online": False}]}
    if at is not None:
        frame["locations"] = {"gen": gen, "at": at}
    if complete is not None:
        frame["complete"] = complete
    return frame


def org_file():
    with open(sminos.org_path()) as f:
        return json.load(f)


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


class Keeping(unittest.TestCase):
    """keep_org through the Link's `org` handler, its lane kept."""

    @classmethod
    def setUpClass(cls):
        cls.base = machine("keep")
        cls.plain = folder(cls.base, "plain")

    def setUp(self):
        self.link = uplink.Link(CRED, {}, transport=mock.Mock(number=1))
        self.addCleanup(self.link.close)
        self.link.generation = 1
        self.link.log_lane = self.link.session_lane = Lane()

    def org(self, frame):
        self.link.dispatch(frame, None)
        return [f for f in self.link.log_lane.sent if f.get("t") == "locations-kept"]

    def test_a_the_file_holds_the_directory_and_the_locations_together_and_the_ack_names_the_gen(self):
        at = [minted(self.plain, MINTED)]
        acks = self.org(org_frame(at, gen=1731200000000, complete=True))
        d = org_file()
        self.assertEqual([p["id"] for p in d["projects"]], [MINTED])
        self.assertEqual(d["locations"], {"gen": 1731200000000, "at": at})
        self.assertIs(d["complete"], True)
        self.assertEqual(acks, [{"t": "locations-kept", "gen": 1731200000000}])
        self.assertEqual(sminos.resolve_project(self.plain).id, MINTED, "the statement decides at once")

    def test_b_a_frame_without_the_field_keeps_the_held_locations(self):
        at = [minted(self.plain, MINTED)]
        self.org(org_frame(at, gen=5, complete=True))
        self.link.log_lane.sent.clear()
        acks = self.org(org_frame(None))
        d = org_file()
        self.assertEqual(d["locations"], {"gen": 5, "at": at}, "kept")
        self.assertNotIn("complete", d, "complete is the frame's alone")
        self.assertEqual(acks, [], "nothing to acknowledge")
        self.assertEqual(sminos.resolve_project(self.plain).id, MINTED)
        # A `locations` of another shape keeps them too, unacknowledged.
        self.assertEqual(self.org(dict(org_frame(None), locations={"gen": "6", "at": []})), [])
        self.assertEqual(org_file()["locations"], {"gen": 5, "at": at})
        # One with it replaces them whole.
        self.assertEqual(self.org(org_frame([], gen=7)), [{"t": "locations-kept", "gen": 7}])
        self.assertEqual(org_file()["locations"], {"gen": 7, "at": []})

    def test_c_a_same_path_anchor_change_is_a_new_ack_and_resolves_at_once(self):
        """'Use this folder' at the same path: the record is as it was, the
        anchor is the new folder's, and the gen a new one."""
        path = folder(self.base, "reused")
        self.assertEqual(self.org(org_frame([minted(path, MINTED)], gen=10)), [{"t": "locations-kept", "gen": 10}])
        self.assertEqual(sminos.resolve_project(path).id, MINTED)
        os.rename(path, path + ".old")   # another folder at the path: the old one's inode is still held
        os.makedirs(path)
        sminos.forget_caches()
        self.assertEqual(sminos.resolve_project(path).id, sminos.own_machine_project().id,
                         "the old anchor names another folder: the statement does not count")
        self.link.log_lane.sent.clear()
        self.assertEqual(self.org(org_frame([minted(path, MINTED)], gen=11)), [{"t": "locations-kept", "gen": 11}])
        self.assertEqual(sminos.resolve_project(path).id, MINTED, "the new anchor, at once")


class Wire(unittest.TestCase):
    """The real uplink against the endpoint stand-in."""

    def setUp(self):
        machine("wire-%d" % time.monotonic_ns())
        self.ep = endpoint_standin.Endpoint(os.path.join(os.environ["MAWS_USER_DATA"], "mawsd", "endpoint"))
        self.ep.capabilities = ["locations"]
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

    def test_the_hello_lists_locations_and_a_kept_frame_is_acknowledged_on_its_connection(self):
        hello = self.ep.wait(lambda f: f["t"] == "hello" and "capabilities" in f)
        self.assertIn("locations", hello["capabilities"])
        self.ep.wait(lambda f: f["t"] == "restated")
        plain = folder(os.path.dirname(os.environ["HOME"]), "plain")
        at = [minted(plain, MINTED)]
        self.ep.send(dict(org_frame(at, gen=42, complete=False)))
        ack = self.ep.wait(lambda f: f["t"] == "locations-kept")
        self.assertEqual(ack, {"t": "locations-kept", "gen": 42})
        d = org_file()
        self.assertEqual((d["locations"], d["complete"]), ({"gen": 42, "at": at}, False))
        with self.ep.cv:
            conns = {n for n, f in self.ep.received if f.get("t") in ("hello", "locations-kept")}
        self.assertEqual(len(conns), 1, "acknowledged on the connection the frame came on")


class Moves(unittest.TestCase):
    """A session in a declared plain folder, over both orders of the
    upgrade's steps, a daemon restart, a deleted org file and a session
    started while the statements are not known: each moves at most once,
    by the reconcile the daemon already has."""

    @classmethod
    def setUpClass(cls):
        cls.base = machine("moves")
        cls.plain = folder(cls.base, "plain")
        cls.own = sminos.machine_project_id(ORG, MACHINE)

    def session(self, name, sid):
        p = subprocess.Popen(["sleep", "600"])
        PROCS.append(p)
        home = os.environ["HOME"]
        with open(os.path.join(home, ".claude", "sessions", name + ".json"), "w") as f:
            json.dump({"pid": p.pid, "sessionId": sid, "name": name, "nameSource": "user", "kind": "interactive",
                       "status": "idle", "cwd": self.plain}, f)
        tx = os.path.join(home, ".claude", "projects", "p-" + sid, sid + ".jsonl")
        os.makedirs(os.path.dirname(tx))
        with open(tx, "w") as f:
            f.write(json.dumps({"type": "user", "uuid": sid[:8] + "-u1", "isSidechain": False, "sessionId": sid,
                                "cwd": self.plain, "origin": {"kind": "human"},
                                "message": {"role": "user", "content": "go"}}) + "\n")

    @staticmethod
    def welcome(caps):
        audience.keep_capabilities(caps)

    @staticmethod
    def frame(at=None, gen=1):
        uplink.keep_org(org_frame(at, gen=gen, complete=True), CRED)

    @staticmethod
    def tick():
        daemon.tick_all(quiet=True)

    @staticmethod
    def membership(sid):
        """(the projects whose log holds `sid` joined now, its `moved` count)."""
        joined, moved = [], 0
        for home in sorted(glob.glob(os.path.join(sminos.projects_root(), "*"))):
            events = []
            for path in glob.glob(os.path.join(home, "log", "*.jsonl")):
                with open(path) as f:
                    events += [e for e in map(json.loads, f) if e.get("session") == sid
                               and e.get("kind") in ("joined", "retired")]
            events.sort(key=lambda e: (e["writer"], e["seq"]))
            moved += sum(1 for e in events if e["kind"] == "retired" and e.get("reason") == "moved")
            if events and events[-1]["kind"] == "joined":
                joined.append(os.path.basename(home))
        return joined, moved

    def test_no_session_moves_twice(self):
        # Beside an older endpoint: no capability, no `locations`: files alone, as today.
        self.welcome(["access", "reach", "record"])
        self.frame()
        self.session("one", S1)
        self.tick()
        self.assertFalse(sminos.locations_unknown())
        self.assertEqual(self.membership(S1), ([self.own], 0), "a session beside an older mawsd resolves")
        # The endpoint upgraded first: its welcome lists `locations`, no frame has come.
        self.welcome(["access", "locations", "reach", "record"])
        self.tick()
        self.assertTrue(sminos.locations_unknown())
        self.assertEqual(self.membership(S1), ([self.own], 0))
        # The frame comes: the declared folder is minted, and its session moves, once.
        at = [minted(self.plain, MINTED)]
        self.frame(at, gen=1)
        self.tick()
        self.assertFalse(sminos.locations_unknown())
        self.assertEqual(self.membership(S1), ([MINTED], 1), "moved by the reconcile, once")
        self.tick()
        self.assertEqual(self.membership(S1), ([MINTED], 1))
        # A daemon restart: a welcome again, the org file as it was.
        self.welcome(["access", "locations", "reach", "record"])
        self.tick()
        self.assertEqual(self.membership(S1), ([MINTED], 1))
        # The org file deleted: unknown, so the session keeps its recorded
        # project rather than files alone moving it to the machine's.
        os.remove(sminos.org_path())
        self.tick()
        self.assertTrue(sminos.locations_unknown())
        self.assertEqual(self.membership(S1), ([MINTED], 1), "kept where it is recorded")
        self.assertEqual(sminos.resolve_project(self.plain).id, self.own, "the directory alone says otherwise")
        # A session started meanwhile, recorded nowhere, joins by files.
        self.session("two", S2)
        self.tick()
        self.assertEqual(self.membership(S2), ([self.own], 0))
        # The frame again: the first moves no more, the second once.
        self.frame(at, gen=2)
        self.tick()
        self.tick()
        self.assertEqual(self.membership(S1), ([MINTED], 1))
        self.assertEqual(self.membership(S2), ([MINTED], 1))

    def test_z_beside_an_endpoint_listing_no_such_capability_nothing_is_held(self):
        self.welcome(["access", "reach", "record"])
        self.frame()
        os.remove(sminos.org_path())
        sminos.forget_caches()
        self.assertFalse(sminos.locations_unknown())


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        for p in PROCS:
            p.kill()
            p.wait()
        shutil.rmtree(T, ignore_errors=True)
